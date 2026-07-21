"""Wspólny pipeline audytu używany przez audyt pojedynczy i masowy.

Kolejność kroków: SERP (Nodeshub) -> treści konkurentów (JINA batch)
-> analiza luk EAV -> scoring -> raport końcowy (OpenAI).
"""

from utils.jina_api import fetch_competitors_batch, fetch_url
from utils.nodeshub_api import search
from utils.openai_llm import (
    GapAnalysisResult,
    analyze_competitor_gaps,
    score_content,
    generate_audit_report,
)

SERP_LOCALES = {
    "Polska (PL)": ("pl", "pl"),
    "USA (EN)": ("en", "us"),
    "Niemcy (DE)": ("de", "de"),
}

MODEL_PRICING = {
    "gpt-5.4-mini": {"in": 0.75, "out": 4.50},
    "gpt-5-mini": {"in": 0.25, "out": 2.00},
    "gpt-5.4-nano": {"in": 0.20, "out": 1.25},
    "gpt-4o": {"in": 5.00, "out": 15.00},
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
}

# Tylko modele wspierające Structured Outputs (response_format z JSON Schema).
AVAILABLE_MODELS = list(MODEL_PRICING.keys())


def empty_gap_analysis() -> GapAnalysisResult:
    return GapAnalysisResult(
        eav_matrix=[], top_3_gaps_p1=[], root_attributes=[], unique_opportunities=[]
    )


def calculate_cost(model_name: str, tokens_in: int, tokens_out: int) -> float:
    p = MODEL_PRICING.get(model_name, {"in": 5.0, "out": 15.0})
    return (tokens_in / 1_000_000) * p["in"] + (tokens_out / 1_000_000) * p["out"]


def run_audit(
    source_content: str,
    keyword: str,
    model_name: str,
    prompts: dict,
    language: str,
    user_context: str = "",
    hl: str = "pl",
    gl: str = "pl",
    remove_selector: str = None,
    on_progress=None,
) -> dict:
    """Uruchamia pełny audyt dla pojedynczej treści.

    prompts: dict z kluczami "gap", "scoring", "report".
    on_progress: opcjonalny callback(etap: str) do aktualizacji UI.
    Zwraca dict z wynikami, licznikami tokenów i listą ostrzeżeń.
    """

    def notify(stage):
        if on_progress:
            on_progress(stage)

    total_in, total_out = 0, 0
    warnings = []
    competitor_urls = []
    consolidated_competitors = ""

    if keyword and keyword.strip():
        notify("Krok 2: Pobieranie wyników SERP...")
        serp_data = search(keyword, hl=hl, gl=gl)
        if "error" in serp_data:
            warnings.append(
                f"Nodeshub SERP: {serp_data['error']} — audyt bez analizy konkurencji."
            )
        else:
            competitor_urls = serp_data.get("urls", [])
            notify("Krok 3: Pobieranie treści konkurentów...")
            batch_result = fetch_competitors_batch(
                competitor_urls, remove_selector=remove_selector
            )
            if batch_result["ok_count"] > 0:
                consolidated_competitors = batch_result["consolidated_markdown"]
            else:
                warnings.append(
                    "Nie udało się pobrać treści żadnego konkurenta — audyt bez analizy luk."
                )

    notify("Krok 4: Analiza luk EAV (OpenAI)...")
    if consolidated_competitors:
        gap_analysis, u = analyze_competitor_gaps(
            keyword, consolidated_competitors, model_name,
            prompts["gap"], language, user_context,
        )
        total_in += u.prompt_tokens
        total_out += u.completion_tokens
    else:
        gap_analysis = empty_gap_analysis()

    notify("Krok 5: Ocenianie treści (Scoring)...")
    scores, u = score_content(
        source_content, gap_analysis, model_name,
        prompts["scoring"], language, user_context,
    )
    total_in += u.prompt_tokens
    total_out += u.completion_tokens

    notify("Krok 6: Raport i rekomendacje...")
    report, u = generate_audit_report(
        source_content, gap_analysis, scores, model_name,
        prompts["report"], language, user_context,
    )
    total_in += u.prompt_tokens
    total_out += u.completion_tokens

    return {
        "gap_analysis": gap_analysis,
        "scores": scores,
        "report": report,
        "competitor_urls": competitor_urls,
        "consolidated_competitors": consolidated_competitors,
        "tokens_in": total_in,
        "tokens_out": total_out,
        "cost": calculate_cost(model_name, total_in, total_out),
        "warnings": warnings,
    }


def fetch_and_audit(
    url: str,
    keyword: str,
    model_name: str,
    prompts: dict,
    language: str,
    user_context: str = "",
    hl: str = "pl",
    gl: str = "pl",
    remove_selector: str = None,
    target_selector: str = None,
) -> dict:
    """Pobiera treść artykułu z URL-a (JINA) i uruchamia dla niej pełny audyt od zera.

    Używane do (re)audytu całego adresu — zarówno przy automatycznej powtórce
    nieudanych wierszy na końcu audytu masowego, jak i przy ręcznej "pełnej
    ponownej analizie" konkretnego URL-a w zakładce Popraw raport.

    Zwraca dict jak run_audit() rozszerzony o 'url', 'keyword', 'title', 'source_content'.
    Rzuca ValueError z czytelnym powodem, jeśli pobranie treści się nie powiedzie.
    """
    data = fetch_url(url, remove_selector=remove_selector, target_selector=target_selector)
    if not data or "error" in data:
        raise ValueError(f"JINA: {data.get('error') if data else 'brak odpowiedzi'}")

    content = data.get("data", {}).get("content", "")
    title = data.get("data", {}).get("title", "") or "Raport Audytu AI"
    if not content.strip():
        raise ValueError("JINA zwróciła pustą treść.")

    result = run_audit(
        content, keyword, model_name, prompts, language, user_context,
        hl=hl, gl=gl, remove_selector=remove_selector,
    )
    result["url"] = url
    result["keyword"] = keyword
    result["title"] = title
    result["source_content"] = content
    return result
