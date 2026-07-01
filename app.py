import streamlit as st
import time

from utils.jina_api import fetch_url, fetch_competitors_batch
from utils.nodeshub_api import search
from utils.openai_llm import analyze_competitor_gaps, score_content, generate_audit_report
from utils.excel_generator import generate_excel_report

st.set_page_config(page_title="AI Content Auditor", page_icon="📝", layout="wide")

st.title("📝 AI Content Auditor Pipeline")
st.markdown("Audyt semantyczny treści za pomocą Jina, Nodeshub i OpenAI.")

with st.sidebar:
    st.header("Konfiguracja")
    st.info("Klucze API powinny być skonfigurowane w `.streamlit/secrets.toml`.")
    st.markdown("""
    - **OpenAI API Key**
    - **Jina API Key**
    - **Nodeshub API Key**
    """)

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

    # Progress reporting
    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # Step 1: Fetch source content
        status_text.text("Krok 1: Pobieranie treści analizowanego artykułu (Jina)...")
        source_data = fetch_url(url_input)
        if not source_data:
            st.error("Nie udało się pobrać treści artykułu.")
            st.stop()
        
        source_title = source_data.get("data", {}).get("title", "")
        source_content = source_data.get("data", {}).get("content", "")
        
        if len(source_content.split()) < 200:
            st.warning("Uwaga: Artykuł wydaje się bardzo krótki (poniżej 200 słów).")
            
        progress_bar.progress(15)

        consolidated_competitors = ""
        
        # Step 2 & 3: Competitor fetching
        if keyword_input:
            status_text.text(f"Krok 2: Pobieranie wyników SERP dla '{keyword_input}' (Nodeshub)...")
            serp_data = search(keyword_input)
            
            if "error" in serp_data:
                st.error(f"Błąd Nodeshub: {serp_data['error']}")
                st.stop()
                
            competitor_urls = serp_data.get("urls", [])
            st.write(f"Znaleziono {len(competitor_urls)} organicznych wyników w Top 10.")
            progress_bar.progress(30)
            
            status_text.text("Krok 3: Pobieranie treści konkurentów (Jina Batch)...")
            batch_result = fetch_competitors_batch(competitor_urls)
            consolidated_competitors = batch_result["consolidated_markdown"]
            st.write(f"Pomyślnie pobrano treść od {batch_result['ok_count']} konkurentów.")
            progress_bar.progress(45)

        # Step 4: Gap Analysis
        status_text.text("Krok 4: Analiza luk i EAV konkurencji (OpenAI)...")
        if not consolidated_competitors:
            st.warning("Brak treści konkurentów. Pomijam analizę SERP (Tryb Content-only).")
            # Create a dummy gap analysis for the content-only mode
            from utils.openai_llm import GapAnalysisResult
            gap_analysis = GapAnalysisResult(eav_matrix=[], top_3_gaps_p1=[], root_attributes=[], unique_opportunities=[])
        else:
            gap_analysis = analyze_competitor_gaps(keyword_input, consolidated_competitors)
        progress_bar.progress(60)

        # Step 5: Scoring
        status_text.text("Krok 5: Ocenianie wymiarów jakości (OpenAI)...")
        scores = score_content(source_content, gap_analysis)
        progress_bar.progress(75)

        # Step 6: Final Report
        status_text.text("Krok 6: Generowanie ostatecznych rekomendacji i CQS (OpenAI)...")
        report = generate_audit_report(source_content, gap_analysis, scores)
        progress_bar.progress(90)

        # Step 7: Excel Export
        status_text.text("Krok 7: Generowanie pliku XLSX...")
        excel_bytes = generate_excel_report(gap_analysis, scores, report)
        progress_bar.progress(100)
        status_text.text("Audyt zakończony sukcesem!")

        # Display Results
        st.success("Raport gotowy do pobrania!")
        
        col_cqs, col_ai = st.columns(2)
        col_cqs.metric("Content Quality Score (CQS)", f"{report.cqs_score}/100")
        col_ai.metric("AI Citability Score", f"{report.ai_citability_score}/10")
        
        st.subheader("Executive Summary")
        st.write(report.executive_summary)
        
        st.download_button(
            label="Pobierz pełny raport audytu (XLSX)",
            data=excel_bytes,
            file_name=f"audit_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
        
        with st.expander("Zobacz główne rekomendacje"):
            for rec in report.recommendations:
                st.markdown(f"**[{rec.priority}] {rec.title}** (Wpływ: +{rec.impact_cqs} pkt)")
                st.markdown(f"*{rec.context}*")
                st.text(f"BEFORE:\n{rec.before_quote}")
                st.text(f"AFTER:\n{rec.after_generated}")
                st.divider()

    except Exception as e:
        st.error(f"Wystąpił błąd podczas analizy: {e}")
        status_text.text("Błąd.")
