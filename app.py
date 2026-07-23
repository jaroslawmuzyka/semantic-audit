import os
import io
import zipfile
import streamlit as st
import pandas as pd

from utils.jina_api import fetch_url
from utils.openai_llm import generate_keyword_from_url
from utils.audit_pipeline import run_audit, fetch_and_audit, SERP_LOCALES, AVAILABLE_MODELS, calculate_cost
from utils.excel_generator import generate_excel_report, generate_master_excel_report, create_zip_archive
from utils.html_generator import generate_single_html_report, generate_master_html_report
from utils.themes import THEMES, THEME_KEYS
from utils import eeat_patch
from utils.naming import safe_filename

st.set_page_config(page_title="AI Content Auditor", page_icon="📝", layout="wide")

# ----------------------------- Helpers -----------------------------

def _get_secret(name: str):
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return value or os.environ.get(name)


def normalize_cell(value) -> str:
    """Zamienia None/NaN/'nan'/'None' z tabeli na pusty string."""
    s = str(value).strip()
    return "" if s.lower() in ("", "nan", "none") else s


def extract_jina_content(data):
    """Zwraca (content, title, error) z odpowiedzi JINA."""
    if not data:
        return None, None, "Brak odpowiedzi z JINA."
    if "error" in data:
        return None, None, data["error"]
    content = data.get("data", {}).get("content", "")
    title = data.get("data", {}).get("title", "") or "Raport Audytu AI"
    if not content.strip():
        return None, None, "JINA zwróciła pustą treść."
    return content, title, None


def build_report_files(url, title, keyword, source_content, result):
    """Generuje raporty XLSX i HTML we wszystkich motywach brandowych."""
    excel_by_theme, html_by_theme = {}, {}
    for tk in THEME_KEYS:
        excel_by_theme[tk] = generate_excel_report(
            result["gap_analysis"], result["scores"], result["report"],
            source_content, result["consolidated_competitors"], theme_key=tk,
        )
        html_by_theme[tk] = generate_single_html_report(
            url, title, keyword,
            result["gap_analysis"], result["scores"], result["report"], theme_key=tk,
        )
    return excel_by_theme, html_by_theme


def render_branded_downloads(excel_by_theme, html_by_theme, prefix="audit_report"):
    cols = st.columns(len(THEME_KEYS))
    for col, tk in zip(cols, THEME_KEYS):
        theme = THEMES[tk]
        with col:
            st.markdown(f"**Branding: {theme['label']}**")
            st.download_button(
                f"Pobierz XLSX ({tk})", data=excel_by_theme[tk],
                file_name=f"{prefix}_{tk.lower()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, key=f"dl_xlsx_{prefix}_{tk}",
            )
            st.download_button(
                f"Pobierz HTML ({tk})", data=html_by_theme[tk],
                file_name=f"{prefix}_{tk.lower()}.html",
                mime="text/html",
                use_container_width=True, key=f"dl_html_{prefix}_{tk}",
            )


def rebuild_mass_archives():
    """Odświeża raporty zbiorcze (oba brandingi) i paczkę ZIP po każdym wierszu."""
    results = st.session_state.mass_results
    if not results:
        st.session_state.mass_zip = None
        return

    first_domain = results[0]["url"].split('//')[-1].split('/')[0].replace("www.", "")
    zip_files = dict(st.session_state.mass_files)
    masters_xlsx, masters_html = {}, {}
    for tk in THEME_KEYS:
        masters_xlsx[tk] = generate_master_excel_report(results, theme_key=tk)
        masters_html[tk] = generate_master_html_report(results, theme_key=tk)
        zip_files[f"{tk}/analiza zbiorcza/master_report_{first_domain}.xlsx"] = masters_xlsx[tk]
        zip_files[f"{tk}/analiza zbiorcza/master_report_{first_domain}.html"] = masters_html[tk]

    if st.session_state.mass_errors:
        skipped_txt = "\n".join(f"{e['url']} — {e['reason']}" for e in st.session_state.mass_errors)
        zip_files["pominiete_adresy.txt"] = skipped_txt.encode("utf-8")

    if st.session_state.mass_warnings:
        warn_lines = [f"{w['url']} — {w['reason']}" for w in st.session_state.mass_warnings]
        warn_txt = (
            "Te adresy MAJĄ wygenerowany raport, ale jest niepełny — któryś z etapów "
            "(SERP/Nodeshub albo pobieranie treści konkurentów przez JINA) nie powiódł się mimo "
            "ponownych prób, więc analiza konkurencji (Matrix EAV) może być pusta lub okrojona.\n\n"
        ) + "\n".join(warn_lines)
        zip_files["bledy_eksportu.txt"] = warn_txt.encode("utf-8")

    st.session_state.mass_master = masters_xlsx
    st.session_state.mass_master_html = masters_html
    st.session_state.mass_zip = create_zip_archive(zip_files)


def process_mass_row(url, keyword, title, source_content, model, prompts, language, user_context, hl, gl, remove_selector, serp_provider):
    result = run_audit(
        source_content, keyword, model, prompts, language, user_context,
        hl=hl, gl=gl, remove_selector=remove_selector, serp_provider=serp_provider,
    )
    for w in result["warnings"]:
        st.warning(f"{url}: {w}")
        st.session_state.mass_warnings.append({"url": url, "reason": w})

    safe_url = safe_filename(url)
    for tk in THEME_KEYS:
        st.session_state.mass_files[f"{tk}/analiza indywidualna/audit_{safe_url}.xlsx"] = generate_excel_report(
            result["gap_analysis"], result["scores"], result["report"],
            source_content, result["consolidated_competitors"], theme_key=tk,
        )
        st.session_state.mass_files[f"{tk}/analiza indywidualna/audit_{safe_url}.html"] = generate_single_html_report(
            url, title, keyword,
            result["gap_analysis"], result["scores"], result["report"], theme_key=tk,
        )

    st.session_state.mass_results.append({
        "url": url,
        "keyword": keyword,
        "report": result["report"],
        "scores": result["scores"],
        "gap_analysis": result["gap_analysis"],
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "cost": result["cost"],
    })
    st.session_state.total_tokens["in"] += result["tokens_in"]
    st.session_state.total_tokens["out"] += result["tokens_out"]
    st.session_state.total_cost += result["cost"]

    rebuild_mass_archives()


# ----------------------------- Session State -----------------------------

_DEFAULT_STATE = {
    "audit_completed": False,
    "excel_bytes": None,          # dict {theme_key: bytes}
    "html_bytes": None,           # dict {theme_key: bytes}
    "report": None,
    "intermediate_logs": {},
    "total_cost": 0.0,
    "total_tokens": {"in": 0, "out": 0},
    "audit_step": 0,
    "source_content": "",
    "source_title": "Raport Audytu AI",
    # Audyt masowy
    "mass_df": None,
    "mass_step": 0,
    "mass_idx": 0,
    "mass_results": [],
    "mass_jina_content": None,
    "mass_jina_title": None,
    "mass_zip": None,
    "mass_master": None,          # dict {theme_key: bytes}
    "mass_master_html": None,     # dict {theme_key: bytes}
    "mass_files": {},
    "mass_errors": [],
    "mass_warnings": [],
    "mass_retry_queue": [],
    "mass_retry_idx": 0,
    "last_uploaded_file": None,
    # Popraw raport (regeneracja E-E-A-T)
    "fix_output_zip": None,
    "fix_output_files": None,
    "fix_errors_result": [],
    "fix_cost_result": (0, 0, 0.0),
}
for key, default in _DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default


def reset_mass_state(clear_table=False):
    st.session_state.mass_step = 0
    st.session_state.mass_idx = 0
    st.session_state.mass_results = []
    st.session_state.mass_files = {}
    st.session_state.mass_zip = None
    st.session_state.mass_master = None
    st.session_state.mass_master_html = None
    st.session_state.mass_jina_content = None
    st.session_state.mass_jina_title = None
    st.session_state.mass_errors = []
    st.session_state.mass_warnings = []
    st.session_state.mass_retry_queue = []
    st.session_state.mass_retry_idx = 0
    if clear_table:
        st.session_state.mass_df = None


st.title("📝 AI Content Auditor Pipeline")
st.markdown("Audyt semantyczny treści za pomocą Jina, Nodeshub i OpenAI.")

# ----------------------------- Sidebar -----------------------------

with st.sidebar:
    st.header("Ustawienia zaawansowane")

    serp_provider = st.selectbox("Dostawca danych SERP", ["Nodeshub", "Data4SEO"], index=0)

    required_keys = ["OPENAI_API_KEY", "JINA_API_KEY"]
    if serp_provider == "Nodeshub":
        required_keys.append("NODESHUB_API_KEY")
    else:
        required_keys += ["DATA4SEO_LOGIN", "DATA4SEO_PASSWORD"]
    missing_keys = [k for k in required_keys if not _get_secret(k)]
    if missing_keys:
        st.warning("Brakujące klucze API: " + ", ".join(missing_keys) + ". Uzupełnij `.streamlit/secrets.toml`.")

    selected_model = st.selectbox("Model OpenAI", AVAILABLE_MODELS, index=0)
    jina_remove_selectors = st.text_input("Usuń selektory przed analizą (JINA)", value=".cky-consent-container")
    jina_target_selectors = st.text_input("Celuj w selektory w JINA (X-Target-Selector)", value="", placeholder="np. body, .class, #id")

    with st.expander("Edytuj Prompty Systemowe", expanded=False):
        prompt_gap_analysis = st.text_area(
            "Krok 4: Analiza luk i konkurentów",
            value="Analizuj konkurencję: treść → EAV → klasyfikacja URR → gap analysis.\n1. EAV Extraction: Wyciągnij trójki Entity-Attribute-Value bezpośrednio z tekstu.\n2. Klasyfikacja URR:\n- UNIQUE: W 1-2 z 10 konkurentów lub brak u nikogo (H1/Lead - wyróżnik)\n- ROOT: W 5+ z 10 konkurentów (H2 - obowiązkowy)\n- RARE: W 3-4 konkurentów, niszowy (H3/FAQ - opcjonalny)\n3. Gap Analysis: COVERED / GAP / UNIQUE.\nPriorytetyzacja gaps:\n- P1: ROOT atrybut w 7+ z 10 konkurentów (musisz mieć)\n- P2: ROOT atrybut w 5-6 konkurentów + PAA\n- P3: RARE atrybut z PAA/Related\n- P4: RARE atrybut w 1-2 konkurentów",
            height=250
        )
        prompt_scoring = st.text_area(
            "Krok 5: Ocena wymiarów (Scoring)",
            value="Oceń artykuł w 9 wymiarach (0-10): CSI Alignment, BLUF, Chunk Quality, URR Placement, Cost of Retrieval, Information Density, SRL Salience, TF-IDF Quality, EEAT (Experience, Expertise, Authority, Trust).\nDla każdego wymiaru zidentyfikuj top problem i podaj surowy cytat (BEFORE).\nWymagane kroki:\n- EEAT detail: Oceń OSOBNO i NIEZALEŻNIE każdy z 4 wymiarów E-E-A-T (Experience, Expertise, Authority, Trust) — dla każdego z nich podaj własną ocenę, obecne sygnały i brakujące sygnały. Nigdy nie łącz kilku wymiarów w jeden wpis i nie skracaj nazw wymiarów (np. do samego \"EEAT\" albo pojedynczej litery) — każdy wymiar musi zostać opisany osobno, własną, konkretną treścią.\n- SRL: Zidentyfikuj zdania, gdzie Central Entity (CE) jest Patient (zamiast Agent).\n- TF-IDF: Wypisz brakujące terminy.\nNie generuj sugestii AFTER na tym etapie. Skup się wyłącznie na rygorystycznej ocenie i wyciągnięciu bezpośrednich dowodów z tekstu.",
            height=250
        )
        prompt_report = st.text_area(
            "Krok 6: Raport i Rekomendacje",
            value="Jesteś głównym strategiem treści. Na bazie surowych wyników wygeneruj profesjonalny raport audytu.\n1. BEFORE/AFTER: Stwórz ulepszoną wersję każdego problematycznego fragmentu (AFTER).\n2. SRL transformacje: Przekształć zdania z Patient na Agent.\n3. Struktura docelowa: używaj tagów [H1], [H2], [H3] (zamiast znaków #) z oznaczeniami [OK]/[ZMIEŃ]/[NOWA] + jednozdaniowy BLUF dla każdego nagłówka.\n4. E-E-A-T: Wygeneruj gotowe bloki tekstu (Bio, disclaimer, data).\n5. Rekomendacje z priorytetami:\n- KRYTYCZNE: Wysoki wpływ, Niski wysiłek\n- WYSOKIE: Wysoki wpływ, Średni wysiłek\n- ŚREDNIE: Wysoki wpływ, Wysoki wysiłek\nOblicz CQS (Content Quality Score) na podstawie ocen cząstkowych i podaj szacowany wpływ (+pkt) dla każdej rekomendacji.",
            height=250
        )

    st.divider()
    st.markdown("### Koszty API")
    cost_placeholder = st.empty()
    cost_placeholder.metric(
        "Całkowity Koszt Sesji",
        f"${st.session_state.total_cost:.4f}",
        f"{st.session_state.total_tokens['in']} in / {st.session_state.total_tokens['out']} out",
    )

prompts = {"gap": prompt_gap_analysis, "scoring": prompt_scoring, "report": prompt_report}

tab1, tab2, tab3 = st.tabs(["Pojedynczy Audyt", "Audyt Masowy (Excel)", "🔄 Popraw raport (E-E-A-T)"])

# ----------------------------- Pojedynczy Audyt -----------------------------

with tab1:
    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    with col1:
        url_input = st.text_input("URL artykułu do audytu", placeholder="https://twojadomena.pl/artykul")
    with col2:
        keyword_input = st.text_input("Fraza kluczowa", placeholder="np. baseny ogrodowe")
    with col3:
        serp_input = st.selectbox("Ustawienia SERP", list(SERP_LOCALES.keys()), index=0)
    with col4:
        audit_lang_input = st.selectbox("Język audytu", ["Polski", "English", "Deutsch"], index=0)

    hl, gl = SERP_LOCALES[serp_input]
    language_name = audit_lang_input
    user_context_input = st.text_area("Dodatkowy kontekst dla AI (opcjonalnie)", placeholder="np. Nie wspominaj o marce X...", height=100)

    input_mode = st.radio("Sposób wprowadzania treści", ["Pobierz treść z URL", "Wklej własną treść (Markdown)"], horizontal=True)
    if input_mode == "Wklej własną treść (Markdown)":
        custom_markdown_input = st.text_area("Wklej treść w formacie Markdown", height=300)
    else:
        custom_markdown_input = ""

    if st.session_state.audit_step == 0:
        c_krok1, c_test = st.columns([1, 1])
        with c_krok1:
            btn_krok1 = st.button("Krok 1: Pobierz treść do analizy (JINA)", type="primary", use_container_width=True)
        with c_test:
            btn_test = st.button("Przetestuj JINA (Szybki Podgląd)", use_container_width=True)

        if btn_test:
            if input_mode == "Pobierz treść z URL":
                if not url_input:
                    st.error("Proszę podać URL artykułu.")
                else:
                    with st.spinner("Pobieranie JINA..."):
                        data = fetch_url(url_input, remove_selector=jina_remove_selectors, target_selector=jina_target_selectors)
                    content, _, err = extract_jina_content(data)
                    if err:
                        st.error(f"Nie udało się pobrać treści: {err}")
                    else:
                        st.success("Pobrano poprawnie.")
                        with st.expander("Podgląd JINA", expanded=True):
                            st.markdown(content)
            else:
                st.info("Testowanie JINA dotyczy tylko pobierania z URL.")

        if btn_krok1:
            if input_mode == "Pobierz treść z URL" and not url_input:
                st.error("Proszę podać URL artykułu.")
                st.stop()
            elif input_mode == "Wklej własną treść (Markdown)" and not custom_markdown_input.strip():
                st.error("Proszę wkleić treść w formacie Markdown.")
                st.stop()

            st.session_state.audit_completed = False
            st.session_state.excel_bytes = None
            st.session_state.html_bytes = None
            st.session_state.report = None
            st.session_state.intermediate_logs = {}
            st.session_state.total_cost = 0.0
            st.session_state.total_tokens = {"in": 0, "out": 0}

            if input_mode == "Pobierz treść z URL":
                with st.spinner("Krok 1: Pobieranie treści..."):
                    source_data = fetch_url(url_input, remove_selector=jina_remove_selectors, target_selector=jina_target_selectors)
                content, title, err = extract_jina_content(source_data)
                if err:
                    st.error(f"Nie udało się pobrać treści artykułu: {err}")
                else:
                    st.session_state.source_content = content
                    st.session_state.source_title = title
                    st.session_state.audit_step = 1
                    st.rerun()
            else:
                st.session_state.source_content = custom_markdown_input
                st.session_state.source_title = "Własny tekst (Markdown)"
                st.session_state.audit_step = 1
                st.rerun()

    elif st.session_state.audit_step == 1:
        st.info("Krok 1 zakończony. Sprawdź pobraną treść. Jeśli wszystko się zgadza, zatwierdź.")
        with st.expander("Pobrana treść z JINA", expanded=True):
            st.markdown(st.session_state.source_content)

        col_ok, col_cancel = st.columns(2)
        with col_ok:
            if st.button("Zatwierdź i kontynuuj audyt", type="primary"):
                st.session_state.audit_step = 2
                st.rerun()
        with col_cancel:
            if st.button("Anuluj i cofnij"):
                st.session_state.audit_step = 0
                st.session_state.source_content = ""
                st.rerun()

    if st.session_state.audit_step == 2:
        source_content = st.session_state.source_content

        try:
            with st.status("Audyt w toku...", expanded=True) as status:
                def on_progress(stage):
                    status.update(label=stage)

                result = run_audit(
                    source_content, keyword_input, selected_model, prompts,
                    language_name, user_context_input,
                    hl=hl, gl=gl, remove_selector=jina_remove_selectors, serp_provider=serp_provider,
                )
                for w in result["warnings"]:
                    st.warning(w)

                status.update(label="Krok 7: Generowanie raportów XLSX i HTML...")
                final_url = url_input if url_input else "wlasny-tekst"
                title = st.session_state.source_title
                excel_by_theme, html_by_theme = build_report_files(
                    final_url, title, keyword_input, source_content, result
                )
                status.update(label="Audyt zakończony.", state="complete", expanded=False)

            st.success("Audyt zakończony sukcesem!")
            st.session_state.audit_completed = True
            st.session_state.excel_bytes = excel_by_theme
            st.session_state.html_bytes = html_by_theme
            st.session_state.report = result["report"]
            st.session_state.total_cost = result["cost"]
            st.session_state.total_tokens = {"in": result["tokens_in"], "out": result["tokens_out"]}
            cost_placeholder.metric(
                "Całkowity Koszt Sesji",
                f"${st.session_state.total_cost:.4f}",
                f"{result['tokens_in']} in / {result['tokens_out']} out",
            )
            st.session_state.intermediate_logs = {
                "source_content": source_content,
                "competitor_urls": result["competitor_urls"],
                "consolidated_competitors": result["consolidated_competitors"],
                "gap_analysis": result["gap_analysis"].model_dump(),
                "scores": result["scores"].model_dump(),
            }
            st.session_state.audit_step = 0

        except Exception as e:
            st.error(f"Wystąpił błąd podczas analizy: {e}")
            st.session_state.audit_step = 0

    if st.session_state.audit_completed and st.session_state.report is not None:
        report = st.session_state.report
        st.divider()
        st.subheader("📊 Wyniki Audytu")

        col_cqs, col_ai = st.columns(2)
        col_cqs.metric("Content Quality Score (CQS)", f"{report.cqs_score}/100")
        col_ai.metric("AI Citability Score", f"{report.ai_citability_score}/10")

        st.markdown("### Executive Summary")
        st.write(report.executive_summary)

        st.markdown("### Pobierz raporty")
        render_branded_downloads(st.session_state.excel_bytes, st.session_state.html_bytes)

        with st.expander("Zobacz główne rekomendacje", expanded=True):
            for rec in report.recommendations:
                st.markdown(f"**[{rec.priority}] {rec.title}** (Wpływ: +{rec.impact_cqs} pkt)")
                st.markdown(f"*{rec.context}*")
                st.text(f"BEFORE:\n{rec.before_quote}")
                st.text(f"AFTER:\n{rec.after_generated}")
                st.divider()

        st.divider()
        st.subheader("🛠️ Logi i Wyniki Pośrednie")
        logs = st.session_state.intermediate_logs
        with st.expander("Podgląd pobranej treści artykułu (JINA)"): st.markdown(logs.get("source_content", ""))
        with st.expander("Podgląd adresów konkurencji (SERP)"): st.json(logs.get("competitor_urls", []))
        with st.expander("Podgląd połączonej treści konkurentów"): st.markdown(logs.get("consolidated_competitors", ""))
        with st.expander("Podgląd surowego wyniku EAV (OpenAI)"): st.json(logs.get("gap_analysis", {}))
        with st.expander("Podgląd surowych punktacji (OpenAI)"): st.json(logs.get("scores", {}))

# ----------------------------- Audyt Masowy -----------------------------

with tab2:
    st.subheader("Import Masowy z pliku Excel")
    st.markdown("Wgraj plik z kolumnami: `URL`, `Fraza` (opcjonalnie), `Title` (opcjonalnie).")

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        mass_serp_input = st.selectbox("Ustawienia SERP (Masowo)", list(SERP_LOCALES.keys()), index=0)
    with col_s2:
        mass_lang_input = st.selectbox("Język audytu (Masowo)", ["Polski", "English", "Deutsch"], index=0)
    with col_s3:
        mass_manual_review = st.checkbox("Zatwierdzanie manualne po JINA", value=False)

    mass_user_context = st.text_area("Dodatkowy kontekst dla wszystkich URLi", height=100)
    mass_hl, mass_gl = SERP_LOCALES[mass_serp_input]

    uploaded_file = st.file_uploader("Opcjonalnie: Wgraj plik XLSX (lub wpisz dane ręcznie poniżej)", type=["xlsx"])

    if uploaded_file is not None and st.session_state.last_uploaded_file != uploaded_file.name:
        df = pd.read_excel(uploaded_file)
        for col in ["URL", "Fraza", "Title"]:
            if col not in df.columns:
                df[col] = ""
            # Force column to string dtype so we don't get float assignment errors on empty columns
            df[col] = df[col].fillna("").astype(str)
        st.session_state.mass_df = df.reset_index(drop=True)
        st.session_state.last_uploaded_file = uploaded_file.name

    if st.session_state.mass_df is None:
        st.session_state.mass_df = pd.DataFrame(columns=["URL", "Fraza", "Title"])

    st.markdown("### Tabela adresów (edytowalna)")
    st.caption("Kliknij dwukrotnie w komórkę, aby ją edytować. Użyj plusa (+) na dole tabeli, aby dodać nowy wiersz.")
    st.session_state.mass_df = st.data_editor(st.session_state.mass_df, num_rows="dynamic", use_container_width=True)

    with st.expander("Przetestuj JINA na adresie (Podgląd)", expanded=False):
        test_url = st.text_input("Podaj adres URL do testu", key="mass_test_url")
        if st.button("Przetestuj URL", key="btn_test_mass_jina"):
            if test_url:
                with st.spinner("Pobieranie JINA..."):
                    data = fetch_url(test_url, remove_selector=jina_remove_selectors, target_selector=jina_target_selectors)
                content, _, err = extract_jina_content(data)
                if err:
                    st.error(f"Błąd pobierania: {err}")
                else:
                    st.success("Pobrano poprawnie.")
                    st.markdown(content)

    col_btn1, col_btn2 = st.columns([1, 2])
    with col_btn1:
        if st.button("Wygeneruj brakujące frazy (AI)", use_container_width=True):
            df = st.session_state.mass_df
            for idx, row in df.iterrows():
                url = normalize_cell(row.get("URL"))
                fraza = normalize_cell(row.get("Fraza"))
                if not fraza and url:
                    with st.spinner(f"Generowanie frazy dla {url}..."):
                        try:
                            title = normalize_cell(row.get("Title"))
                            kw, _ = generate_keyword_from_url(url, title, selected_model)
                            df.at[idx, "Fraza"] = kw
                        except Exception as e:
                            st.error(f"Błąd dla {url}: {e}")
            st.session_state.mass_df = df
            st.rerun()

    with col_btn2:
        if st.session_state.mass_step == 0:
            if st.button("Rozpocznij Audyt Masowy", type="primary", use_container_width=True):
                reset_mass_state()
                st.session_state.mass_step = 1
                st.session_state.total_cost = 0.0
                st.session_state.total_tokens = {"in": 0, "out": 0}
                st.rerun()

    if st.session_state.mass_results:
        st.success(f"Ukończono {len(st.session_state.mass_results)} analiz. Możesz pobrać dotychczasowe wyniki w każdej chwili.")
        if st.session_state.mass_zip:
            st.download_button(
                "Pobierz paczkę ZIP (raporty w obu brandingach: PG + WPP)",
                data=st.session_state.mass_zip, file_name="audyty_masowe.zip",
                mime="application/zip", use_container_width=True,
            )
        master_cols = st.columns(len(THEME_KEYS))
        for col, tk in zip(master_cols, THEME_KEYS):
            with col:
                st.markdown(f"**Master raport — {THEMES[tk]['label']}**")
                if st.session_state.mass_master and st.session_state.mass_master.get(tk):
                    st.download_button(
                        f"Master Excel ({tk})", data=st.session_state.mass_master[tk],
                        file_name=f"master_report_{tk.lower()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True, key=f"dl_master_xlsx_{tk}",
                    )
                if st.session_state.mass_master_html and st.session_state.mass_master_html.get(tk):
                    st.download_button(
                        f"Master HTML ({tk})", data=st.session_state.mass_master_html[tk],
                        file_name=f"master_report_{tk.lower()}.html",
                        mime="text/html",
                        use_container_width=True, key=f"dl_master_html_{tk}",
                    )
        if st.button("Zresetuj analizę masową", use_container_width=True):
            reset_mass_state()
            st.rerun()
        st.divider()

    if st.session_state.mass_errors:
        with st.expander(f"Pominięte adresy ({len(st.session_state.mass_errors)})"):
            for e in st.session_state.mass_errors:
                st.markdown(f"- `{e['url']}` — {e['reason']}")

    if st.session_state.mass_warnings:
        with st.expander(f"⚠️ Raporty niepełne ({len(st.session_state.mass_warnings)}) — patrz też bledy_eksportu.txt w ZIP-ie"):
            for w in st.session_state.mass_warnings:
                st.markdown(f"- `{w['url']}` — {w['reason']}")

    if st.session_state.mass_step == 1:
        # Maszyna stanów: jeden wiersz na jeden przebieg skryptu (odporne na rerun,
        # brak duplikatów przy przerwaniu, działa dla trybu manualnego i automatycznego).
        df = st.session_state.mass_df
        n_rows = len(df)
        idx = st.session_state.mass_idx

        if idx >= n_rows:
            if st.session_state.mass_warnings:
                # Kolejka do ponownej, pełnej próby — unikalne URL-e, w kolejności wystąpienia.
                st.session_state.mass_retry_queue = list(dict.fromkeys(w["url"] for w in st.session_state.mass_warnings))
                st.session_state.mass_retry_idx = 0
                st.session_state.mass_step = 3
            else:
                st.session_state.mass_step = 2
            st.rerun()

        st.progress(min(idx / n_rows, 1.0) if n_rows else 0.0, text=f"Postęp audytu: {idx}/{n_rows}")

        row = df.iloc[idx]
        url = normalize_cell(row.get("URL", ""))
        keyword = normalize_cell(row.get("Fraza", ""))

        if not url:
            st.session_state.mass_idx += 1
            st.rerun()

        st.write(f"### Przetwarzanie wiersza {idx+1}/{n_rows}: {url}")

        if st.session_state.mass_jina_content is None:
            with st.spinner(f"Pobieranie JINA: {url}"):
                source_data = fetch_url(url, remove_selector=jina_remove_selectors, target_selector=jina_target_selectors)
            content, title, err = extract_jina_content(source_data)
            if err:
                st.error(f"Nie udało się pobrać treści dla {url}: {err}. Pomijam.")
                st.session_state.mass_errors.append({"url": url, "reason": f"JINA: {err}"})
                st.session_state.mass_jina_content = None
                st.session_state.mass_idx += 1
                st.rerun()
            st.session_state.mass_jina_content = content
            st.session_state.mass_jina_title = title

        if mass_manual_review:
            with st.expander(f"Pobrana treść JINA ({url})", expanded=True):
                st.markdown(st.session_state.mass_jina_content)

            c1, c2 = st.columns(2)
            approved = c1.button("Zatwierdź i analizuj ten adres", key=f"btn_ok_{idx}", type="primary")
            skipped = c2.button("Pomiń ten adres", key=f"btn_skip_{idx}")
            if skipped:
                st.session_state.mass_errors.append({"url": url, "reason": "Pominięty ręcznie"})
                st.session_state.mass_jina_content = None
                st.session_state.mass_jina_title = None
                st.session_state.mass_idx += 1
                st.rerun()
            if not approved:
                st.stop()  # czekamy na decyzję użytkownika

        with st.spinner(f"Analiza w toku ({url}): SERP, Gap, Scoring, Report..."):
            try:
                process_mass_row(
                    url, keyword,
                    st.session_state.mass_jina_title or "Raport Audytu AI",
                    st.session_state.mass_jina_content,
                    selected_model, prompts, mass_lang_input, mass_user_context,
                    mass_hl, mass_gl, jina_remove_selectors, serp_provider,
                )
            except Exception as e:
                st.error(f"Błąd przy analizie {url}: {e}")
                st.session_state.mass_errors.append({"url": url, "reason": str(e)})

        st.session_state.mass_jina_content = None
        st.session_state.mass_jina_title = None
        st.session_state.mass_idx += 1
        st.rerun()

    if st.session_state.mass_step == 3:
        # Druga runda: adresy, które za pierwszym razem dostały niepełny raport
        # (np. chwilowy błąd Nodeshub/JINA), dostają jedną pełną, ponowną próbę.
        queue = st.session_state.mass_retry_queue
        n_retry = len(queue)
        ridx = st.session_state.mass_retry_idx

        if ridx >= n_retry:
            st.session_state.mass_step = 2
            st.rerun()

        st.progress(min(ridx / n_retry, 1.0) if n_retry else 0.0, text=f"Ponowna próba dla niepełnych raportów: {ridx}/{n_retry}")

        url = queue[ridx]
        keyword = next((r["keyword"] for r in st.session_state.mass_results if r["url"] == url), "")
        st.write(f"### Ponowna, pełna analiza {ridx+1}/{n_retry}: {url}")

        with st.spinner(f"Pobieranie treści i pełna reanaliza ({url})..."):
            try:
                result = fetch_and_audit(
                    url, keyword, selected_model, prompts, mass_lang_input, mass_user_context,
                    hl=mass_hl, gl=mass_gl, remove_selector=jina_remove_selectors, target_selector=jina_target_selectors,
                    serp_provider=serp_provider,
                )
            except Exception as e:
                st.warning(f"Ponowna próba nadal nieudana dla {url}: {e}")
                st.session_state.mass_warnings = [w for w in st.session_state.mass_warnings if w["url"] != url]
                st.session_state.mass_warnings.append({"url": url, "reason": f"(po ponownej próbie) {e}"})
                st.session_state.mass_retry_idx += 1
                st.rerun()

        for i, r in enumerate(st.session_state.mass_results):
            if r["url"] == url:
                st.session_state.mass_results[i] = {
                    "url": url, "keyword": keyword, "report": result["report"], "scores": result["scores"],
                    "gap_analysis": result["gap_analysis"], "tokens_in": result["tokens_in"],
                    "tokens_out": result["tokens_out"], "cost": result["cost"],
                }
                break

        safe_url = safe_filename(url)
        for tk in THEME_KEYS:
            st.session_state.mass_files[f"{tk}/analiza indywidualna/audit_{safe_url}.xlsx"] = generate_excel_report(
                result["gap_analysis"], result["scores"], result["report"],
                result["source_content"], result["consolidated_competitors"], theme_key=tk,
            )
            st.session_state.mass_files[f"{tk}/analiza indywidualna/audit_{safe_url}.html"] = generate_single_html_report(
                url, result["title"], keyword, result["gap_analysis"], result["scores"], result["report"], theme_key=tk,
            )

        st.session_state.total_tokens["in"] += result["tokens_in"]
        st.session_state.total_tokens["out"] += result["tokens_out"]
        st.session_state.total_cost += result["cost"]

        st.session_state.mass_warnings = [w for w in st.session_state.mass_warnings if w["url"] != url]
        if result["warnings"]:
            for w in result["warnings"]:
                st.session_state.mass_warnings.append({"url": url, "reason": f"(po ponownej próbie) {w}"})
            st.warning(f"Ponowna próba nadal niepełna dla {url}: {'; '.join(result['warnings'])}")
        else:
            st.success(f"Ponowna próba udana: {url} — raport teraz pełny.")

        rebuild_mass_archives()
        st.session_state.mass_retry_idx += 1
        st.rerun()

    if st.session_state.mass_step == 2:
        st.success("Zakończono audyt masowy wszystkich adresów!")
        st.metric(
            "Łączny Koszt",
            f"${st.session_state.total_cost:.4f}",
            f"{st.session_state.total_tokens['in']} in / {st.session_state.total_tokens['out']} out",
        )
        if st.button("Zresetuj i rozpocznij od nowa"):
            reset_mass_state(clear_table=True)
            st.rerun()

# ----------------------------- Popraw raport (E-E-A-T) -----------------------------

with tab3:
    st.subheader("Przeregeneruj wybrane wartości w już gotowych raportach")
    st.markdown(
        "Wgraj pliki wynikowe, które już masz (raporty **indywidualne** i/lub **masowe**, "
        "**XLSX** i/lub **HTML**, dowolny branding PG/WPP). Zaznacz, dla których adresów chcesz "
        "świeżą ocenę **Braki E-E-A-T**. Reszta każdego pliku (rekomendacje, EAV, formatowanie, "
        "branding) zostaje bez zmian — modyfikowane są tylko sekcje/komórki E-E-A-T."
    )

    FIX_MODE_EEAT = "Tylko Braki E-E-A-T (szybkie)"
    FIX_MODE_FULL = "Pełna ponowna analiza (SERP + Gap + Scoring + Report)"
    FIX_MODE_DELETE = "Usuń wybrane adresy z raportu"
    fix_mode = st.radio(
        "Co przeregenerować?", [FIX_MODE_EEAT, FIX_MODE_FULL, FIX_MODE_DELETE], key="fix_mode", horizontal=True,
    )
    if fix_mode == FIX_MODE_FULL:
        st.caption(
            "Pełna reanaliza pobiera treść na nowo i uruchamia CAŁY audyt (SERP, konkurencja, EAV, scoring, "
            "raport) dla wybranych adresów — przydatne, gdy poprzednia próba skończyła się niepełnym raportem "
            "(np. chwilowy błąd Nodeshub/JINA). Wolniejsze i droższe niż regeneracja samego E-E-A-T."
        )
    elif fix_mode == FIX_MODE_DELETE:
        st.caption(
            "Usuwa zaznaczone adresy z raportu masowego (wszystkie arkusze XLSX + sekcje HTML, oba brandingi) "
            "i pomija ich pliki indywidualne w wyniku. Nie modyfikuje wgranych przez Ciebie oryginałów — dostajesz "
            "nowy plik/ZIP bez tych adresów. Bez wywołań AI/JINA."
        )

    fix_lang, fix_user_context, fix_serp_input = "Polski", "", list(SERP_LOCALES.keys())[0]
    if fix_mode != FIX_MODE_DELETE:
        fix_col1, fix_col2, fix_col3 = st.columns(3)
        with fix_col1:
            fix_lang = st.selectbox("Język regeneracji", ["Polski", "English", "Deutsch"], index=0, key="fix_lang")
        with fix_col2:
            fix_user_context = st.text_input("Dodatkowy kontekst dla AI (opcjonalnie)", key="fix_user_context")
        with fix_col3:
            if fix_mode == FIX_MODE_FULL:
                fix_serp_input = st.selectbox("Ustawienia SERP", list(SERP_LOCALES.keys()), index=0, key="fix_serp")

    fix_uploaded = st.file_uploader(
        "Wgraj ZIP z całą paczką (tak jak pobrany z audytu masowego) i/lub pojedyncze pliki XLSX / HTML",
        type=["xlsx", "html", "htm", "zip"], accept_multiple_files=True, key="fix_uploader",
    )
    st.caption(
        "Wgrywając ZIP nie musisz nic rozpakowywać — struktura folderów (PG/WPP, "
        "„analiza indywidualna”/„analiza zbiorcza”) zostanie zachowana w pliku wynikowym."
    )

    if fix_uploaded:
        file_records = {}
        for f in fix_uploaded:
            b = f.getvalue()
            if f.name.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(b)) as zf:
                        for info in zf.infolist():
                            if info.is_dir():
                                continue
                            entry_name = info.filename.replace("\\", "/")
                            entry_bytes = zf.read(info.filename)
                            file_records[entry_name] = {
                                "bytes": entry_bytes,
                                "kind": eeat_patch.detect_file_kind(entry_name, entry_bytes),
                            }
                except zipfile.BadZipFile:
                    st.error(f"Nie udało się otworzyć pliku ZIP: {f.name} (uszkodzony lub niepoprawny format).")
            else:
                file_records[f.name] = {"bytes": b, "kind": eeat_patch.detect_file_kind(f.name, b)}

        unknown = [n for n, r in file_records.items() if r["kind"] == "unknown"]
        if unknown:
            st.warning("Nie rozpoznano typu tych plików (zostaną przepisane bez zmian): " + ", ".join(unknown))

        known_urls = []
        known_keywords = {}
        for name, rec in file_records.items():
            if rec["kind"] == "xlsx_master":
                known_urls += eeat_patch.extract_urls_from_master_xlsx(rec["bytes"])
                known_keywords.update({
                    u: kw for u, kw in eeat_patch.extract_keywords_from_master_xlsx(rec["bytes"]).items() if kw
                })
            elif rec["kind"] == "html_master":
                known_urls += eeat_patch.extract_urls_from_master_html(rec["bytes"])
            elif rec["kind"] == "html_single":
                u = eeat_patch.extract_url_from_single_html(rec["bytes"])
                if u:
                    known_urls.append(u)
        known_urls = sorted(set(known_urls))

        single_xlsx_names = [n for n, r in file_records.items() if r["kind"] == "xlsx_single"]

        # Plik XLSX raportu pojedynczego nie ma zapisanego URL-a w środku, ale nazwa pliku
        # (audit_{safe_filename(url)}.xlsx) jest tworzona z URL-a w sposób deterministyczny —
        # więc najpierw próbujemy dopasować automatycznie po nazwie, zamiast pytać o każdy plik.
        url_overrides = {}
        unmatched_single_xlsx = []
        for name in single_xlsx_names:
            guessed = eeat_patch.guess_url_for_individual_file(name, known_urls)
            if guessed:
                url_overrides[name] = guessed
            else:
                unmatched_single_xlsx.append(name)

        if single_xlsx_names:
            matched_count = len(single_xlsx_names) - len(unmatched_single_xlsx)
            st.caption(f"Dopasowano automatycznie po nazwie pliku: {matched_count}/{len(single_xlsx_names)} plików XLSX.")

        if unmatched_single_xlsx:
            st.markdown("#### Powiąż pozostałe pliki XLSX z adresem URL")
            st.caption(
                "Tych plików nie udało się automatycznie dopasować po nazwie (np. zostały zmienione/przemianowane, "
                "albo w wgranej paczce brakuje pliku, z którego można by odczytać ich URL). Podaj/wybierz URL ręcznie "
                "— albo zostaw bez powiązania, plik zostanie poprawiony samodzielnie."
            )
            for name in unmatched_single_xlsx:
                options = ["— (bez powiązania) —"] + known_urls + ["Wpisz inny URL..."]
                choice = st.selectbox(f"URL dla `{name}`", options, key=f"fix_map_{name}")
                if choice == "Wpisz inny URL...":
                    url_overrides[name] = st.text_input(f"Podaj URL dla `{name}`", key=f"fix_map_custom_{name}").strip()
                elif choice != "— (bez powiązania) —":
                    url_overrides[name] = choice
                else:
                    url_overrides[name] = ""

        # Zbuduj listę pozycji do przeregenerowania (klucz = URL albo plik samodzielny)
        work_items = {}

        def add_work_item(key, label):
            if key not in work_items:
                work_items[key] = {"label": label, "content": None, "source": None}

        for url in known_urls:
            add_work_item(url, url)
        for name in single_xlsx_names:
            mapped = url_overrides.get(name, "")
            key = mapped if mapped else f"__standalone__{name}"
            add_work_item(key, mapped if mapped else f"{name} (plik samodzielny)")

        for name in single_xlsx_names:
            mapped = url_overrides.get(name, "")
            key = mapped if mapped else f"__standalone__{name}"
            content = eeat_patch.extract_source_content_from_single_xlsx(file_records[name]["bytes"])
            if content:
                work_items[key]["content"] = content
                work_items[key]["source"] = "embedded"

        for key, item in work_items.items():
            if item["content"] is None and key.startswith("http"):
                item["source"] = "fetch"

        if not work_items:
            st.info("Nie znaleziono żadnych adresów ani plików możliwych do przeregenerowania.")
        else:
            st.markdown("#### Wybierz, co przeregenerować")
            source_labels = {"embedded": "treść z pliku ✅", "fetch": "pobranie z JINA 🌐", None: "brak treści źródłowej ❌"}
            selected_keys = []
            skipped_no_url = []
            for key, item in sorted(work_items.items(), key=lambda kv: kv[1]["label"]):
                if fix_mode == FIX_MODE_FULL and not key.startswith("http"):
                    skipped_no_url.append(item["label"])
                    continue
                if fix_mode == FIX_MODE_FULL:
                    kw = known_keywords.get(key, "")
                    suffix = f"— fraza: „{kw}”" if kw else "— ⚠️ brak frazy w paczce, trzeba będzie podać ręcznie"
                    label = f"{item['label']}  {suffix}"
                elif fix_mode == FIX_MODE_DELETE:
                    label = item["label"]
                else:
                    label = f"{item['label']}  —  _{source_labels[item['source']]}_"
                checked = st.checkbox(label, value=False, key=f"fix_sel_{key}")
                if checked:
                    selected_keys.append(key)

            if fix_mode == FIX_MODE_FULL and skipped_no_url:
                st.caption(
                    "Pominięto (brak przypisanego URL-a, pełna reanaliza go wymaga): " + ", ".join(skipped_no_url)
                )

            fix_manual_keywords = {}
            if fix_mode == FIX_MODE_FULL:
                missing_kw_keys = [k for k in selected_keys if not known_keywords.get(k)]
                if missing_kw_keys:
                    st.markdown("##### Podaj frazę kluczową (brak jej w wgranej paczce)")
                    for k in missing_kw_keys:
                        fix_manual_keywords[k] = st.text_input(f"Fraza dla `{k}`", key=f"fix_kw_{k}")

            btn_labels = {
                FIX_MODE_EEAT: "Przeregeneruj zaznaczone (E-E-A-T)",
                FIX_MODE_FULL: "Przeregeneruj zaznaczone (pełna analiza)",
                FIX_MODE_DELETE: "Usuń zaznaczone adresy z raportu",
            }
            if st.button(btn_labels[fix_mode], type="primary", disabled=not selected_keys, use_container_width=True):
                fix_errors = []
                total_in, total_out, total_cost = 0, 0, 0.0
                output_files = {}

                if fix_mode == FIX_MODE_EEAT:
                    computed = {}
                    with st.spinner("Przeregenerowywanie E-E-A-T..."):
                        for key in selected_keys:
                            item = work_items[key]
                            content = item["content"]
                            if content is None and item["source"] == "fetch":
                                data = fetch_url(key, remove_selector=jina_remove_selectors, target_selector=jina_target_selectors)
                                content, _, err = extract_jina_content(data)
                                if err:
                                    fix_errors.append({"url": key, "reason": f"JINA: {err}"})
                                    continue
                            if not content:
                                fix_errors.append({"url": key, "reason": "Brak treści źródłowej — pominięto."})
                                continue
                            try:
                                eeat_list, usage = eeat_patch.regenerate_eeat(
                                    content, fix_lang, fix_user_context, prompts["scoring"], selected_model,
                                )
                            except Exception as e:
                                fix_errors.append({"url": key, "reason": f"OpenAI: {e}"})
                                continue
                            computed[key] = eeat_list
                            total_in += usage.prompt_tokens
                            total_out += usage.completion_tokens
                            total_cost += calculate_cost(selected_model, usage.prompt_tokens, usage.completion_tokens)

                    for name, rec in file_records.items():
                        b, kind = rec["bytes"], rec["kind"]
                        try:
                            if kind == "xlsx_master":
                                output_files[name] = eeat_patch.patch_master_xlsx(b, computed)
                            elif kind == "html_master":
                                output_files[name] = eeat_patch.patch_master_html(b, computed)
                            elif kind == "xlsx_single":
                                mapped = url_overrides.get(name, "")
                                key = mapped if mapped else f"__standalone__{name}"
                                output_files[name] = eeat_patch.patch_single_xlsx(b, computed[key]) if key in computed else b
                            elif kind == "html_single":
                                u = eeat_patch.extract_url_from_single_html(b)
                                output_files[name] = eeat_patch.patch_single_html(b, computed[u]) if u in computed else b
                            else:
                                output_files[name] = b
                        except Exception as e:
                            fix_errors.append({"url": name, "reason": f"Patchowanie pliku: {e}"})
                            output_files[name] = b

                elif fix_mode == FIX_MODE_FULL:
                    fix_hl, fix_gl = SERP_LOCALES[fix_serp_input]
                    fresh_results = {}
                    with st.spinner("Pełna ponowna analiza w toku (to może potrwać dłużej)..."):
                        for key in selected_keys:
                            keyword = known_keywords.get(key) or fix_manual_keywords.get(key, "")
                            try:
                                result = fetch_and_audit(
                                    key, keyword, selected_model, prompts, fix_lang, fix_user_context,
                                    hl=fix_hl, gl=fix_gl, remove_selector=jina_remove_selectors, target_selector=jina_target_selectors,
                                    serp_provider=serp_provider,
                                )
                            except Exception as e:
                                fix_errors.append({"url": key, "reason": str(e)})
                                continue
                            fresh_results[key] = result
                            total_in += result["tokens_in"]
                            total_out += result["tokens_out"]
                            total_cost += result["cost"]
                            if result["warnings"]:
                                fix_errors.append({"url": key, "reason": "Nadal niepełne: " + "; ".join(result["warnings"])})

                    def _theme_of(name, b):
                        return eeat_patch.guess_theme_from_path(name, b)

                    for name, rec in file_records.items():
                        b, kind = rec["bytes"], rec["kind"]
                        try:
                            if kind == "xlsx_master":
                                if fresh_results:
                                    reconstructed = eeat_patch.reconstruct_results_from_master_xlsx(b)
                                    merged = eeat_patch.merge_fresh_results_into_master(reconstructed, fresh_results)
                                    output_files[name] = generate_master_excel_report(merged, theme_key=_theme_of(name, b))
                                else:
                                    output_files[name] = b
                            elif kind == "html_master":
                                theme = _theme_of(name, b)
                                sibling = next(
                                    (n for n, r in file_records.items()
                                     if r["kind"] == "xlsx_master" and _theme_of(n, r["bytes"]) == theme),
                                    None,
                                )
                                if fresh_results and sibling:
                                    reconstructed = eeat_patch.reconstruct_results_from_master_xlsx(file_records[sibling]["bytes"])
                                    merged = eeat_patch.merge_fresh_results_into_master(reconstructed, fresh_results)
                                    output_files[name] = generate_master_html_report(merged, theme_key=theme)
                                else:
                                    output_files[name] = b
                                    if fresh_results and not sibling:
                                        fix_errors.append({
                                            "url": name,
                                            "reason": "Brak pasującego master XLSX tego samego brandingu w paczce — HTML pozostawiony bez zmian.",
                                        })
                            elif kind == "xlsx_single":
                                mapped = url_overrides.get(name, "")
                                if mapped in fresh_results:
                                    fresh = fresh_results[mapped]
                                    output_files[name] = generate_excel_report(
                                        fresh["gap_analysis"], fresh["scores"], fresh["report"],
                                        fresh["source_content"], fresh["consolidated_competitors"],
                                        theme_key=_theme_of(name, b),
                                    )
                                else:
                                    output_files[name] = b
                            elif kind == "html_single":
                                u = eeat_patch.extract_url_from_single_html(b)
                                if u in fresh_results:
                                    fresh = fresh_results[u]
                                    output_files[name] = generate_single_html_report(
                                        u, fresh["title"], fresh["keyword"], fresh["gap_analysis"], fresh["scores"], fresh["report"],
                                        theme_key=_theme_of(name, b),
                                    )
                                else:
                                    output_files[name] = b
                            else:
                                output_files[name] = b
                        except Exception as e:
                            fix_errors.append({"url": name, "reason": f"Przebudowa pliku: {e}"})
                            output_files[name] = b

                else:  # FIX_MODE_DELETE
                    urls_to_delete = {k for k in selected_keys if k.startswith("http")}

                    # Pliki indywidualne (xlsx bez wbudowanego URL-a, dopasowane po nazwie/mapowaniu
                    # ręcznym, oraz html z wbudowanym URL-em) odpowiadające usuwanym adresom — pomijamy
                    # je całkowicie w wyniku, zamiast je przebudowywać.
                    files_to_drop = set()
                    for name in single_xlsx_names:
                        mapped = url_overrides.get(name, "")
                        key = mapped if mapped else f"__standalone__{name}"
                        if key in selected_keys:
                            files_to_drop.add(name)
                    for name, rec in file_records.items():
                        if rec["kind"] == "html_single" and eeat_patch.extract_url_from_single_html(rec["bytes"]) in urls_to_delete:
                            files_to_drop.add(name)

                    def _theme_of(name, b):
                        return eeat_patch.guess_theme_from_path(name, b)

                    for name, rec in file_records.items():
                        if name in files_to_drop:
                            continue
                        b, kind = rec["bytes"], rec["kind"]
                        try:
                            if kind == "xlsx_master":
                                reconstructed = eeat_patch.reconstruct_results_from_master_xlsx(b)
                                remaining = {u: r for u, r in reconstructed.items() if u not in urls_to_delete}
                                if len(remaining) != len(reconstructed):
                                    output_files[name] = generate_master_excel_report(list(remaining.values()), theme_key=_theme_of(name, b))
                                else:
                                    output_files[name] = b
                            elif kind == "html_master":
                                theme = _theme_of(name, b)
                                sibling = next(
                                    (n for n, r in file_records.items()
                                     if r["kind"] == "xlsx_master" and _theme_of(n, r["bytes"]) == theme),
                                    None,
                                )
                                if sibling:
                                    reconstructed = eeat_patch.reconstruct_results_from_master_xlsx(file_records[sibling]["bytes"])
                                    remaining = {u: r for u, r in reconstructed.items() if u not in urls_to_delete}
                                    if len(remaining) != len(reconstructed):
                                        output_files[name] = generate_master_html_report(list(remaining.values()), theme_key=theme)
                                    else:
                                        output_files[name] = b
                                else:
                                    output_files[name] = b
                            else:
                                output_files[name] = b
                        except Exception as e:
                            fix_errors.append({"url": name, "reason": f"Usuwanie adresu: {e}"})
                            output_files[name] = b

                if fix_errors:
                    err_txt = "\n".join(f"{e['url']} — {e['reason']}" for e in fix_errors)
                    output_files["bledy_eksportu.txt"] = err_txt.encode("utf-8")

                st.session_state.fix_output_zip = create_zip_archive(output_files)
                st.session_state.fix_output_files = output_files
                st.session_state.fix_errors_result = fix_errors
                st.session_state.fix_cost_result = (total_in, total_out, total_cost)
                st.session_state.total_tokens["in"] += total_in
                st.session_state.total_tokens["out"] += total_out
                st.session_state.total_cost += total_cost
                st.rerun()

    if st.session_state.fix_output_files:
        st.divider()
        st.success(f"Poprawiono {len(st.session_state.fix_output_files)} plik(ów).")
        t_in, t_out, t_cost = st.session_state.fix_cost_result
        st.metric("Koszt tej regeneracji", f"${t_cost:.4f}", f"{t_in} in / {t_out} out")
        st.download_button(
            "Pobierz poprawione pliki (ZIP)", data=st.session_state.fix_output_zip,
            file_name="raporty_poprawione_eeat.zip", mime="application/zip",
            use_container_width=True,
        )
        with st.expander("Pobierz pojedynczo"):
            for name, b in st.session_state.fix_output_files.items():
                base_name = name.rsplit("/", 1)[-1]
                st.download_button(f"Pobierz {name}", data=b, file_name=base_name, key=f"fix_dl_{name}")
        if st.session_state.fix_errors_result:
            with st.expander(f"Pominięte / błędy ({len(st.session_state.fix_errors_result)})"):
                for e in st.session_state.fix_errors_result:
                    st.markdown(f"- `{e['url']}` — {e['reason']}")
