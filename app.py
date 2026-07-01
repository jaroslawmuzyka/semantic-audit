import streamlit as st
import time

from utils.jina_api import fetch_url, fetch_competitors_batch
from utils.nodeshub_api import search
from utils.openai_llm import analyze_competitor_gaps, score_content, generate_audit_report
from utils.excel_generator import generate_excel_report

st.set_page_config(page_title="AI Content Auditor", page_icon="📝", layout="wide")

# Initialize Session State
if "audit_completed" not in st.session_state:
    st.session_state.audit_completed = False
if "excel_bytes" not in st.session_state:
    st.session_state.excel_bytes = None
if "report" not in st.session_state:
    st.session_state.report = None
if "logs" not in st.session_state:
    st.session_state.logs = []

st.title("📝 AI Content Auditor Pipeline")
st.markdown("Audyt semantyczny treści za pomocą Jina, Nodeshub i OpenAI.")

# Sidebar Settings
with st.sidebar:
    st.header("Konfiguracja API")
    st.info("Klucze API powinny być skonfigurowane w `.streamlit/secrets.toml`.")
    st.markdown("""
    - **OpenAI API Key**
    - **Jina API Key**
    - **Nodeshub API Key**
    """)
    
    st.divider()
    st.header("Ustawienia Zaawansowane")
    selected_model = st.selectbox("Model OpenAI", ["gpt-4o", "chatgpt-4o-latest", "gpt-4-turbo", "gpt-4o-mini", "gpt-5.4-mini", "gpt-5-mini", "gpt-5.4-nano"], index=0)
    
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

# Input
col1, col2 = st.columns(2)
with col1:
    url_input = st.text_input("URL artykułu do audytu", placeholder="https://twojadomena.pl/artykul")
with col2:
    keyword_input = st.text_input("Fraza kluczowa", placeholder="np. baseny ogrodowe")

if st.button("Rozpocznij Audyt", type="primary"):
    if not url_input:
        st.error("Proszę podać URL artykułu.")
        st.stop()
        
    # Reset state for new run
    st.session_state.audit_completed = False
    st.session_state.excel_bytes = None
    st.session_state.report = None
    st.session_state.logs = []

    progress_bar = st.progress(0)
    
    try:
        # Step 1: Fetch source content
        with st.status("Krok 1: Pobieranie treści analizowanego artykułu (Jina)...", expanded=True) as status:
            source_data = fetch_url(url_input, remove_selector=jina_remove_selectors)
            if not source_data:
                st.error("Nie udało się pobrać treści artykułu.")
                st.stop()
            
            source_title = source_data.get("data", {}).get("title", "")
            source_content = source_data.get("data", {}).get("content", "")
            
            if len(source_content.split()) < 200:
                st.warning("Uwaga: Artykuł wydaje się bardzo krótki (poniżej 200 słów).")
            
            with st.expander("Podgląd pobranej treści (JINA)"):
                st.markdown(source_content)
                
            status.update(label="Krok 1: Zakończono pobieranie artykułu.", state="complete", expanded=False)
            
        progress_bar.progress(15)

        consolidated_competitors = ""
        
        # Step 2 & 3: Competitor fetching
        if keyword_input:
            with st.status(f"Krok 2: Pobieranie wyników SERP dla '{keyword_input}' (Nodeshub)...", expanded=True) as status:
                serp_data = search(keyword_input)
                
                if "error" in serp_data:
                    st.error(f"Błąd Nodeshub: {serp_data['error']}")
                    st.stop()
                    
                competitor_urls = serp_data.get("urls", [])
                st.write(f"Znaleziono {len(competitor_urls)} organicznych wyników w Top 10.")
                
                with st.expander("Podgląd adresów konkurencji (SERP)"):
                    st.json(competitor_urls)
                    
                status.update(label="Krok 2: Wyniki SERP pobrane.", state="complete", expanded=False)
                
            progress_bar.progress(30)
            
            with st.status("Krok 3: Pobieranie treści konkurentów (Jina Batch)...", expanded=True) as status:
                batch_result = fetch_competitors_batch(competitor_urls, remove_selector=jina_remove_selectors)
                consolidated_competitors = batch_result["consolidated_markdown"]
                st.write(f"Pomyślnie pobrano treść od {batch_result['ok_count']} konkurentów.")
                
                with st.expander("Podgląd połączonej treści konkurentów"):
                    st.markdown(consolidated_competitors)
                
                status.update(label="Krok 3: Treści konkurentów pobrane.", state="complete", expanded=False)
                
            progress_bar.progress(45)

        # Step 4: Gap Analysis
        with st.status("Krok 4: Analiza luk i EAV konkurencji (OpenAI)...", expanded=True) as status:
            if not consolidated_competitors:
                st.warning("Brak treści konkurentów. Pomijam analizę SERP (Tryb Content-only).")
                from utils.openai_llm import GapAnalysisResult
                gap_analysis = GapAnalysisResult(eav_matrix=[], top_3_gaps_p1=[], root_attributes=[], unique_opportunities=[])
            else:
                gap_analysis = analyze_competitor_gaps(keyword_input, consolidated_competitors, selected_model, prompt_gap_analysis)
                
            with st.expander("Podgląd wyniku analizy EAV"):
                st.json(gap_analysis.model_dump())
                
            status.update(label="Krok 4: Analiza EAV zakończona.", state="complete", expanded=False)
            
        progress_bar.progress(60)

        # Step 5: Scoring
        with st.status("Krok 5: Ocenianie wymiarów jakości (OpenAI)...", expanded=True) as status:
            scores = score_content(source_content, gap_analysis, selected_model, prompt_scoring)
            
            with st.expander("Podgląd surowych punktacji"):
                st.json(scores.model_dump())
                
            status.update(label="Krok 5: Ocenianie zakończone.", state="complete", expanded=False)
            
        progress_bar.progress(75)

        # Step 6: Final Report
        with st.status("Krok 6: Generowanie ostatecznych rekomendacji i CQS (OpenAI)...", expanded=True) as status:
            report = generate_audit_report(source_content, gap_analysis, scores, selected_model, prompt_report)
            status.update(label="Krok 6: Raport wygenerowany.", state="complete", expanded=False)
            
        progress_bar.progress(90)

        # Step 7: Excel Export
        with st.status("Krok 7: Generowanie pliku XLSX...", expanded=True) as status:
            excel_bytes = generate_excel_report(gap_analysis, scores, report)
            status.update(label="Krok 7: XLSX gotowy.", state="complete", expanded=False)
            
        progress_bar.progress(100)
        st.success("Audyt zakończony sukcesem!")

        # Save to Session State so it persists
        st.session_state.audit_completed = True
        st.session_state.excel_bytes = excel_bytes
        st.session_state.report = report

    except Exception as e:
        st.error(f"Wystąpił błąd podczas analizy: {e}")

# Display Results if audit is completed (persists across reruns)
if st.session_state.audit_completed and st.session_state.report is not None:
    report = st.session_state.report
    excel_bytes = st.session_state.excel_bytes
    
    st.divider()
    st.subheader("📊 Wyniki Audytu")
    
    col_cqs, col_ai = st.columns(2)
    col_cqs.metric("Content Quality Score (CQS)", f"{report.cqs_score}/100")
    col_ai.metric("AI Citability Score", f"{report.ai_citability_score}/10")
    
    st.markdown("### Executive Summary")
    st.write(report.executive_summary)
    
    st.download_button(
        label="Pobierz pełny raport audytu (XLSX)",
        data=excel_bytes,
        file_name="audit_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
    
    with st.expander("Zobacz główne rekomendacje", expanded=True):
        for rec in report.recommendations:
            st.markdown(f"**[{rec.priority}] {rec.title}** (Wpływ: +{rec.impact_cqs} pkt)")
            st.markdown(f"*{rec.context}*")
            st.text(f"BEFORE:\n{rec.before_quote}")
            st.text(f"AFTER:\n{rec.after_generated}")
            st.divider()
