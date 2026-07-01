import streamlit as st
import time
import pandas as pd
import io

from utils.jina_api import fetch_url, fetch_competitors_batch
from utils.nodeshub_api import search
from utils.openai_llm import analyze_competitor_gaps, score_content, generate_audit_report, generate_keyword_from_url
from utils.excel_generator import generate_excel_report, generate_master_excel_report, create_zip_archive

st.set_page_config(page_title="AI Content Auditor", page_icon="📝", layout="wide")

# Initialize Session State
if "audit_completed" not in st.session_state:
    st.session_state.audit_completed = False
if "excel_bytes" not in st.session_state:
    st.session_state.excel_bytes = None
if "report" not in st.session_state:
    st.session_state.report = None
if "intermediate_logs" not in st.session_state:
    st.session_state.intermediate_logs = {}
if "total_cost" not in st.session_state:
    st.session_state.total_cost = 0.0
if "total_tokens" not in st.session_state:
    st.session_state.total_tokens = {"in": 0, "out": 0}
if "audit_step" not in st.session_state:
    st.session_state.audit_step = 0
if "source_content" not in st.session_state:
    st.session_state.source_content = ""

# Mass Audit State
if "mass_df" not in st.session_state:
    st.session_state.mass_df = None
if "mass_step" not in st.session_state:
    st.session_state.mass_step = 0
if "mass_idx" not in st.session_state:
    st.session_state.mass_idx = 0
if "mass_results" not in st.session_state:
    st.session_state.mass_results = []
if "mass_jina_content" not in st.session_state:
    st.session_state.mass_jina_content = None
if "mass_zip" not in st.session_state:
    st.session_state.mass_zip = None
if "mass_master" not in st.session_state:
    st.session_state.mass_master = None
if "mass_files" not in st.session_state:
    st.session_state.mass_files = {}

st.title("📝 AI Content Auditor Pipeline")
st.markdown("Audyt semantyczny treści za pomocą Jina, Nodeshub i OpenAI.")

# Sidebar Settings
with st.sidebar:
    st.header("Ustawienia Zaawansowane")
    selected_model = st.selectbox("Model OpenAI", ["gpt-4o", "chatgpt-4o-latest", "gpt-4-turbo", "gpt-4o-mini", "gpt-5.4-mini", "gpt-5-mini", "gpt-5.4-nano"], index=4)
    
    jina_remove_selectors = st.text_input("Wyklucz selektory w JINA (np. header, .class)", placeholder="header, .cky-consent-container, #footer")
    
    with st.expander("Edytuj Prompty Systemowe", expanded=False):
        prompt_gap_analysis = st.text_area(
            "Krok 4: Analiza luk i konkurentów", 
            value="Analizuj konkurencję: treść → EAV → klasyfikacja URR → gap analysis.\n1. EAV Extraction: Wyciągnij trójki Entity-Attribute-Value bezpośrednio z tekstu.\n2. Klasyfikacja URR:\n- UNIQUE: W 1-2 z 10 konkurentów lub brak u nikogo (H1/Lead - wyróżnik)\n- ROOT: W 5+ z 10 konkurentów (H2 - obowiązkowy)\n- RARE: W 3-4 konkurentów, niszowy (H3/FAQ - opcjonalny)\n3. Gap Analysis: COVERED / GAP / UNIQUE.\nPriorytetyzacja gaps:\n- P1: ROOT atrybut w 7+ z 10 konkurentów (musisz mieć)\n- P2: ROOT atrybut w 5-6 konkurentów + PAA\n- P3: RARE atrybut z PAA/Related\n- P4: RARE atrybut w 1-2 konkurentów",
            height=250
        )
        prompt_scoring = st.text_area(
            "Krok 5: Ocena wymiarów (Scoring)", 
            value="Oceń artykuł w 9 wymiarach (0-10): CSI Alignment, BLUF, Chunk Quality, URR Placement, Cost of Retrieval, Information Density, SRL Salience, TF-IDF Quality, EEAT (Experience, Expertise, Authority, Trust).\nDla każdego wymiaru zidentyfikuj top problem i podaj surowy cytat (BEFORE).\nWymagane kroki:\n- EEAT detail: Zidentyfikuj obecne i brakujące sygnały.\n- SRL: Zidentyfikuj zdania, gdzie Central Entity (CE) jest Patient (zamiast Agent).\n- TF-IDF: Wypisz brakujące terminy.\nNie generuj sugestii AFTER na tym etapie. Skup się wyłącznie na rygorystycznej ocenie i wyciągnięciu bezpośrednich dowodów z tekstu.",
            height=250
        )
        prompt_report = st.text_area(
            "Krok 6: Raport i Rekomendacje", 
            value="Jesteś głównym strategiem treści. Na bazie surowych wyników wygeneruj profesjonalny raport audytu.\n1. BEFORE/AFTER: Stwórz ulepszoną wersję każdego problematycznego fragmentu (AFTER).\n2. SRL transformacje: Przekształć zdania z Patient na Agent.\n3. Struktura docelowa: H1/H2/H3 z oznaczeniami [OK]/[ZMIEŃ]/[NOWA] + jednozdaniowy BLUF dla każdego H2.\n4. E-E-A-T: Wygeneruj gotowe bloki tekstu (Bio, disclaimer, data).\n5. Rekomendacje z priorytetami:\n- KRYTYCZNE: Wysoki wpływ, Niski wysiłek\n- WYSOKIE: Wysoki wpływ, Średni wysiłek\n- ŚREDNIE: Wysoki wpływ, Wysoki wysiłek\nOblicz CQS (Content Quality Score) na podstawie ocen cząstkowych i podaj szacowany wpływ (+pkt) dla każdej rekomendacji.",
            height=250
        )

pricing = {
    "gpt-5.4-mini": {"in": 0.75, "out": 4.50},
    "gpt-5-mini": {"in": 0.25, "out": 2.00},
    "gpt-5.4-nano": {"in": 0.20, "out": 1.25},
    "gpt-4o": {"in": 5.00, "out": 15.00},
    "chatgpt-4o-latest": {"in": 5.00, "out": 15.00},
    "gpt-4-turbo": {"in": 10.00, "out": 30.00},
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
}
p_cost = pricing.get(selected_model, {"in": 5.0, "out": 15.0})

tab1, tab2 = st.tabs(["Pojedynczy Audyt", "Audyt Masowy (Excel)"])

with tab1:
    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    with col1:
        url_input = st.text_input("URL artykułu do audytu", placeholder="https://twojadomena.pl/artykul")
    with col2:
        keyword_input = st.text_input("Fraza kluczowa", placeholder="np. baseny ogrodowe")
    with col3:
        serp_input = st.selectbox("Ustawienia SERP", ["Polska (PL)", "USA (EN)", "Niemcy (DE)"], index=0)
    with col4:
        audit_lang_input = st.selectbox("Język audytu", ["Polski", "English", "Deutsch"], index=0)
        
    if serp_input == "Polska (PL)":
        hl, gl = "pl", "pl"
    elif serp_input == "USA (EN)":
        hl, gl = "en", "us"
    elif serp_input == "Niemcy (DE)":
        hl, gl = "de", "de"

    language_name = audit_lang_input
    user_context_input = st.text_area("Dodatkowy kontekst dla AI (opcjonalnie)", placeholder="np. Nie wspominaj o marce X...", height=100)

    if st.session_state.audit_step == 0:
        if st.button("Krok 1: Pobierz treść do analizy (JINA)", type="primary"):
            if not url_input:
                st.error("Proszę podać URL artykułu.")
                st.stop()
                
            st.session_state.audit_completed = False
            st.session_state.excel_bytes = None
            st.session_state.report = None
            st.session_state.intermediate_logs = {}
            st.session_state.total_cost = 0.0
            st.session_state.total_tokens = {"in": 0, "out": 0}
            
            try:
                with st.status("Krok 1: Pobieranie treści...", expanded=True) as status:
                    source_data = fetch_url(url_input, remove_selector=jina_remove_selectors)
                    if not source_data:
                        st.error("Nie udało się pobrać treści artykułu.")
                        st.stop()
                    
                    source_content = source_data.get("data", {}).get("content", "")
                    st.session_state.source_content = source_content
                    st.session_state.audit_step = 1
                    status.update(label="Krok 1: Zakończono.", state="complete", expanded=False)
                    st.rerun()
            except Exception as e:
                st.error(f"Wystąpił błąd: {e}")

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
        progress_bar = st.progress(15)
        
        total_in, total_out = 0, 0
        source_content = st.session_state.source_content
        consolidated_competitors = ""
        
        try:
            if keyword_input:
                with st.status(f"Krok 2: SERP dla '{keyword_input}'...", expanded=True) as status:
                    serp_data = search(keyword_input, hl=hl, gl=gl)
                    if "error" in serp_data:
                        st.error(f"Błąd Nodeshub: {serp_data['error']}")
                        st.stop()
                    competitor_urls = serp_data.get("urls", [])
                    status.update(label="Krok 2: Zakończono.", state="complete", expanded=False)
                    
                progress_bar.progress(30)
                
                with st.status("Krok 3: Treści konkurentów (Jina Batch)...", expanded=True) as status:
                    batch_result = fetch_competitors_batch(competitor_urls, remove_selector=jina_remove_selectors)
                    consolidated_competitors = batch_result["consolidated_markdown"]
                    status.update(label="Krok 3: Zakończono.", state="complete", expanded=False)
                    
                progress_bar.progress(45)

            with st.status("Krok 4: Analiza luk EAV (OpenAI)...", expanded=True) as status:
                if not consolidated_competitors:
                    from utils.openai_llm import GapAnalysisResult
                    gap_analysis = GapAnalysisResult(eav_matrix=[], top_3_gaps_p1=[], root_attributes=[], unique_opportunities=[])
                else:
                    gap_analysis, u = analyze_competitor_gaps(keyword_input, consolidated_competitors, selected_model, prompt_gap_analysis, language_name, user_context_input)
                    total_in += u.prompt_tokens; total_out += u.completion_tokens
                status.update(label="Krok 4: Zakończono.", state="complete", expanded=False)
                
            progress_bar.progress(60)

            with st.status("Krok 5: Ocenianie (Scoring)...", expanded=True) as status:
                scores, u = score_content(source_content, gap_analysis, selected_model, prompt_scoring, language_name, user_context_input)
                total_in += u.prompt_tokens; total_out += u.completion_tokens
                status.update(label="Krok 5: Zakończono.", state="complete", expanded=False)
                
            progress_bar.progress(75)

            with st.status("Krok 6: Raport i Rekomendacje...", expanded=True) as status:
                report, u = generate_audit_report(source_content, gap_analysis, scores, selected_model, prompt_report, language_name, user_context_input)
                total_in += u.prompt_tokens; total_out += u.completion_tokens
                status.update(label="Krok 6: Zakończono.", state="complete", expanded=False)
                
            progress_bar.progress(90)

            with st.status("Krok 7: XLSX...", expanded=True) as status:
                excel_bytes = generate_excel_report(gap_analysis, scores, report, source_content, consolidated_competitors)
                status.update(label="Krok 7: Gotowy.", state="complete", expanded=False)
                
            progress_bar.progress(100)
            
            cost = (total_in / 1_000_000) * p_cost["in"] + (total_out / 1_000_000) * p_cost["out"]
            
            st.success("Audyt zakończony sukcesem!")
            st.session_state.audit_completed = True
            st.session_state.excel_bytes = excel_bytes
            st.session_state.report = report
            st.session_state.total_cost = cost
            st.session_state.total_tokens = {"in": total_in, "out": total_out}
            st.session_state.intermediate_logs = {
                "source_content": source_content,
                "competitor_urls": competitor_urls if keyword_input else [],
                "consolidated_competitors": consolidated_competitors,
                "gap_analysis": gap_analysis.model_dump(),
                "scores": scores.model_dump()
            }
            st.session_state.audit_step = 0

        except Exception as e:
            st.error(f"Wystąpił błąd podczas analizy: {e}")
            st.session_state.audit_step = 0

    if st.session_state.audit_completed and st.session_state.report is not None:
        report = st.session_state.report
        excel_bytes = st.session_state.excel_bytes
        st.divider()
        st.subheader("📊 Wyniki Audytu")
        
        col_cqs, col_ai, col_cost = st.columns(3)
        col_cqs.metric("Content Quality Score (CQS)", f"{report.cqs_score}/100")
        col_ai.metric("AI Citability Score", f"{report.ai_citability_score}/10")
        col_cost.metric("Koszt Analizy", f"${st.session_state.total_cost:.4f}", f"{st.session_state.total_tokens['in']} in / {st.session_state.total_tokens['out']} out tokens")
        
        st.markdown("### Executive Summary")
        st.write(report.executive_summary)
        
        st.download_button("Pobierz pełny raport audytu (XLSX)", data=excel_bytes, file_name="audit_report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
        
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

with tab2:
    st.subheader("Import Masowy z pliku Excel")
    st.markdown("Wgraj plik z kolumnami: `URL`, `Fraza` (opcjonalnie), `Title` (opcjonalnie).")
    
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        mass_serp_input = st.selectbox("Ustawienia SERP (Masowo)", ["Polska (PL)", "USA (EN)", "Niemcy (DE)"], index=0)
    with col_s2:
        mass_lang_input = st.selectbox("Język audytu (Masowo)", ["Polski", "English", "Deutsch"], index=0)
    with col_s3:
        mass_manual_review = st.checkbox("Zatwierdzanie manualne po JINA", value=False)
        
    mass_user_context = st.text_area("Dodatkowy kontekst dla wszystkich URLi", height=100)

    if mass_serp_input == "Polska (PL)": mass_hl, mass_gl = "pl", "pl"
    elif mass_serp_input == "USA (EN)": mass_hl, mass_gl = "en", "us"
    elif mass_serp_input == "Niemcy (DE)": mass_hl, mass_gl = "de", "de"
    
    uploaded_file = st.file_uploader("Opcjonalnie: Wgraj plik XLSX (lub wpisz dane ręcznie poniżej)", type=["xlsx"])
    
    if "last_uploaded_file" not in st.session_state:
        st.session_state.last_uploaded_file = None

    if uploaded_file is not None and st.session_state.last_uploaded_file != uploaded_file.name:
        df = pd.read_excel(uploaded_file)
        for col in ["URL", "Fraza", "Title"]:
            if col not in df.columns: 
                df[col] = ""
            # Force column to string dtype so we don't get float assignment errors on empty columns
            df[col] = df[col].fillna("").astype(str)
        st.session_state.mass_df = df
        st.session_state.last_uploaded_file = uploaded_file.name

    if st.session_state.mass_df is None:
        st.session_state.mass_df = pd.DataFrame(columns=["URL", "Fraza", "Title"])
        
    st.markdown("### Tabela adresów (edytowalna)")
    st.caption("Kliknij dwukrotnie w komórkę, aby ją edytować. Użyj plusa (+) na dole tabeli, aby dodać nowy wiersz.")
    st.session_state.mass_df = st.data_editor(st.session_state.mass_df, num_rows="dynamic", use_container_width=True)
    
    col_btn1, col_btn2 = st.columns([1, 2])
    with col_btn1:
        if st.button("Wygeneruj brakujące frazy (AI)", use_container_width=True):
            df = st.session_state.mass_df
            for idx, row in df.iterrows():
                url = row.get("URL")
                fraza = row.get("Fraza")
                if pd.isna(fraza) or str(fraza).strip() == "":
                    if pd.notna(url) and str(url).strip() != "":
                        with st.spinner(f"Generowanie frazy dla {url}..."):
                            try:
                                title = row.get("Title", "")
                                kw, _ = generate_keyword_from_url(str(url), str(title), selected_model)
                                df.at[idx, "Fraza"] = kw
                            except Exception as e:
                                st.error(f"Błąd dla {url}: {e}")
            st.session_state.mass_df = df
            st.rerun()
            
    with col_btn2:
        if st.session_state.mass_step == 0:
            if st.button("Rozpocznij Audyt Masowy", type="primary", use_container_width=True):
                st.session_state.mass_step = 1
                st.session_state.mass_idx = 0
                st.session_state.mass_results = []
                st.session_state.mass_files = {}
                st.session_state.total_cost = 0.0
                st.session_state.total_tokens = {"in": 0, "out": 0}
                st.session_state.mass_zip = None
                st.session_state.mass_master = None
                st.session_state.mass_jina_content = None
                st.rerun()

    if st.session_state.mass_step == 1:
        df = st.session_state.mass_df
            
            if mass_manual_review:
                idx = st.session_state.mass_idx
                if idx >= len(df):
                    st.success("Zakończono audyt masowy wszystkich adresów!")
                    st.session_state.mass_zip = create_zip_archive(st.session_state.mass_files)
                    st.session_state.mass_master = generate_master_excel_report(st.session_state.mass_results)
                    st.session_state.mass_step = 2
                    st.rerun()
                else:
                    row = df.iloc[idx]
                    url = str(row.get("URL", ""))
                    keyword = str(row.get("Fraza", ""))
                    
                    if pd.isna(url) or url.strip() == "":
                        st.session_state.mass_idx += 1
                        st.rerun()
                        
                    st.write(f"### Przetwarzanie wiersza {idx+1}/{len(df)}: {url}")
                    
                    if st.session_state.mass_jina_content is None:
                        with st.spinner("Pobieranie JINA..."):
                            source_data = fetch_url(url, remove_selector=jina_remove_selectors)
                            if source_data:
                                st.session_state.mass_jina_content = source_data.get("data", {}).get("content", "")
                            else:
                                st.error(f"Nie udało się pobrać treści dla {url}. Pomijam.")
                                st.session_state.mass_idx += 1
                                st.rerun()
                    
                    with st.expander(f"Pobrana treść JINA ({url})", expanded=True):
                        st.markdown(st.session_state.mass_jina_content)
                        
                    c1, c2 = st.columns(2)
                    if c1.button("Zatwierdź i analizuj ten adres", key=f"btn_ok_{idx}"):
                        pass # proceed
                    elif c2.button("Pomiń ten adres", key=f"btn_skip_{idx}"):
                        st.session_state.mass_jina_content = None
                        st.session_state.mass_idx += 1
                        st.rerun()
                    else:
                        st.stop() # Wait for interaction
                    
                    with st.spinner("Analiza w toku (SERP, Gap, Scoring, Report)..."):
                        try:
                            total_in, total_out = 0, 0
                            source_content = st.session_state.mass_jina_content
                            consolidated_competitors = ""
                            
                            if keyword and keyword.strip() != "":
                                serp_data = search(keyword, hl=mass_hl, gl=mass_gl)
                                competitor_urls = serp_data.get("urls", []) if not "error" in serp_data else []
                                batch_result = fetch_competitors_batch(competitor_urls, remove_selector=jina_remove_selectors)
                                consolidated_competitors = batch_result["consolidated_markdown"]
                                
                            if not consolidated_competitors:
                                from utils.openai_llm import GapAnalysisResult
                                gap_analysis = GapAnalysisResult(eav_matrix=[], top_3_gaps_p1=[], root_attributes=[], unique_opportunities=[])
                            else:
                                gap_analysis, u = analyze_competitor_gaps(keyword, consolidated_competitors, selected_model, prompt_gap_analysis, mass_lang_input, mass_user_context)
                                total_in += u.prompt_tokens; total_out += u.completion_tokens
                                
                            scores, u = score_content(source_content, gap_analysis, selected_model, prompt_scoring, mass_lang_input, mass_user_context)
                            total_in += u.prompt_tokens; total_out += u.completion_tokens
                            
                            report, u = generate_audit_report(source_content, gap_analysis, scores, selected_model, prompt_report, mass_lang_input, mass_user_context)
                            total_in += u.prompt_tokens; total_out += u.completion_tokens
                            
                            excel_bytes = generate_excel_report(gap_analysis, scores, report, source_content, consolidated_competitors)
                            filename = f"audit_{idx+1}_{url.split('//')[-1].split('/')[0]}.xlsx".replace("www.", "")
                            
                            st.session_state.mass_files[filename] = excel_bytes
                            st.session_state.mass_results.append({
                                "url": url,
                                "keyword": keyword,
                                "report": report,
                                "scores": scores,
                                "gap_analysis": gap_analysis
                            })
                            
                            st.session_state.total_tokens["in"] += total_in
                            st.session_state.total_tokens["out"] += total_out
                            st.session_state.total_cost += (total_in / 1_000_000) * p_cost["in"] + (total_out / 1_000_000) * p_cost["out"]
                            
                        except Exception as e:
                            st.error(f"Błąd przy analizie {url}: {e}")
                    
                    st.session_state.mass_jina_content = None
                    st.session_state.mass_idx += 1
                    st.rerun()
            else:
                # Automatyczny tryb masowy (bez zatrzymywania)
                mass_prog = st.progress(0)
                mass_status = st.empty()
                
                for idx, row in df.iterrows():
                    url = str(row.get("URL", ""))
                    keyword = str(row.get("Fraza", ""))
                    
                    if pd.isna(url) or url.strip() == "":
                        continue
                        
                    mass_status.write(f"Analiza wiersza {idx+1}/{len(df)}: {url}")
                    
                    try:
                        source_data = fetch_url(url, remove_selector=jina_remove_selectors)
                        if not source_data:
                            continue
                        source_content = source_data.get("data", {}).get("content", "")
                        
                        total_in, total_out = 0, 0
                        consolidated_competitors = ""
                        
                        if keyword and keyword.strip() != "":
                            serp_data = search(keyword, hl=mass_hl, gl=mass_gl)
                            competitor_urls = serp_data.get("urls", []) if not "error" in serp_data else []
                            batch_result = fetch_competitors_batch(competitor_urls, remove_selector=jina_remove_selectors)
                            consolidated_competitors = batch_result["consolidated_markdown"]
                            
                        if not consolidated_competitors:
                            from utils.openai_llm import GapAnalysisResult
                            gap_analysis = GapAnalysisResult(eav_matrix=[], top_3_gaps_p1=[], root_attributes=[], unique_opportunities=[])
                        else:
                            gap_analysis, u = analyze_competitor_gaps(keyword, consolidated_competitors, selected_model, prompt_gap_analysis, mass_lang_input, mass_user_context)
                            total_in += u.prompt_tokens; total_out += u.completion_tokens
                            
                        scores, u = score_content(source_content, gap_analysis, selected_model, prompt_scoring, mass_lang_input, mass_user_context)
                        total_in += u.prompt_tokens; total_out += u.completion_tokens
                        
                        report, u = generate_audit_report(source_content, gap_analysis, scores, selected_model, prompt_report, mass_lang_input, mass_user_context)
                        total_in += u.prompt_tokens; total_out += u.completion_tokens
                        
                        excel_bytes = generate_excel_report(gap_analysis, scores, report, source_content, consolidated_competitors)
                        filename = f"audit_{idx+1}_{url.split('//')[-1].split('/')[0]}.xlsx".replace("www.", "")
                        
                        st.session_state.mass_files[filename] = excel_bytes
                        st.session_state.mass_results.append({
                            "url": url,
                            "keyword": keyword,
                            "report": report,
                            "scores": scores,
                            "gap_analysis": gap_analysis
                        })
                        
                        st.session_state.total_tokens["in"] += total_in
                        st.session_state.total_tokens["out"] += total_out
                        st.session_state.total_cost += (total_in / 1_000_000) * p_cost["in"] + (total_out / 1_000_000) * p_cost["out"]
                        
                    except Exception as e:
                        st.error(f"Błąd przy analizie {url}: {e}")
                        
                    mass_prog.progress(int(((idx+1) / len(df)) * 100))
                    
                st.success("Zakończono audyt masowy wszystkich adresów!")
                st.session_state.mass_zip = create_zip_archive(st.session_state.mass_files)
                st.session_state.mass_master = generate_master_excel_report(st.session_state.mass_results)
                st.session_state.mass_step = 2
                st.rerun()

        if st.session_state.mass_step == 2:
            st.success("Proces masowy zakończony.")
            st.metric("Łączny Koszt", f"${st.session_state.total_cost:.4f}", f"{st.session_state.total_tokens['in']} in / {st.session_state.total_tokens['out']} out")
            
            c1, c2 = st.columns(2)
            with c1:
                st.download_button("Pobierz paczkę ZIP (wszystkie analizy osobno)", data=st.session_state.mass_zip, file_name="audyty_masowe.zip", mime="application/zip", type="primary")
            with c2:
                st.download_button("Pobierz Master Excel (zbiorczy raport)", data=st.session_state.mass_master, file_name="master_report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
            
            if st.button("Zresetuj i rozpocznij od nowa"):
                st.session_state.mass_step = 0
                st.session_state.mass_df = None
                st.rerun()
