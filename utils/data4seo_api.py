"""Alternatywne źródło danych SERP — DataForSEO (Live Google Organic SERP Advanced).

Ma dokładnie ten sam interfejs co utils/nodeshub_api.py (search(keyword, hl, gl) ->
dict z kluczem "urls" albo {"error": "..."}), żeby dało się go podstawić jako
zamiennik bez zmiany reszty pipeline'u (patrz SERP_PROVIDERS w utils/audit_pipeline.py).

Zwraca WYŁĄCZNIE wyniki oznaczone w odpowiedzi API jako "type": "organic", top 10.
"""
import os
import time
import requests
import streamlit as st

API_URL = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"

# location_code DataForSEO (= Google Ads geotargeting criteria ID) dla krajów
# używanych w SERP_LOCALES (utils/audit_pipeline.py).
LOCATION_CODES = {
    "pl": 2616,  # Polska
    "us": 2840,  # USA
    "de": 2276,  # Niemcy
}


def get_credentials():
    try:
        login = st.secrets.get("DATA4SEO_LOGIN")
        password = st.secrets.get("DATA4SEO_PASSWORD")
    except Exception:
        login = password = None
    login = login or os.environ.get("DATA4SEO_LOGIN")
    password = password or os.environ.get("DATA4SEO_PASSWORD")
    return login, password


def _search_impl(keyword, hl="pl", gl="pl", max_retries=3):
    login, password = get_credentials()
    if not login or not password:
        return {"error": "Brak danych logowania DATA4SEO_LOGIN / DATA4SEO_PASSWORD w secrets."}

    post_data = [{
        "language_code": hl,
        "location_code": LOCATION_CODES.get(gl, LOCATION_CODES["pl"]),
        "keyword": keyword,
        "device": "mobile",
        "depth": 10,
    }]

    last_error = "Nieznany błąd"
    for attempt in range(max_retries):
        try:
            resp = requests.post(API_URL, auth=(login, password), json=post_data, timeout=30)
            if resp.status_code == 200:
                return extract_relevant_data(resp.json())
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except requests.exceptions.RequestException as e:
            last_error = str(e)

        if attempt < max_retries - 1:
            time.sleep(3)

    return {"error": last_error}


@st.cache_data(ttl=3600, show_spinner=False)
def _search_cached(keyword, hl, gl):
    result = _search_impl(keyword, hl=hl, gl=gl)
    if "error" in result:
        # Wyjątek zapobiega zapisaniu błędu w cache — kolejna próba trafi w API.
        raise RuntimeError(result["error"])
    return result


def search(keyword, hl="pl", gl="pl"):
    try:
        return _search_cached(keyword, hl, gl)
    except RuntimeError as e:
        return {"error": str(e)}


def extract_relevant_data(data):
    if data.get("status_code") != 20000:
        return {"error": f"DataForSEO: {data.get('status_message', 'nieznany błąd')}"}

    tasks = data.get("tasks") or []
    if not tasks:
        return {"error": "DataForSEO: brak zadania w odpowiedzi."}

    task = tasks[0]
    if task.get("status_code") != 20000:
        return {"error": f"DataForSEO (task): {task.get('status_message', 'nieznany błąd')}"}

    results = task.get("result") or []
    if not results or not results[0]:
        return {"error": "DataForSEO: brak wyników (result)."}

    items = results[0].get("items") or []
    organic = [item for item in items if item.get("type") == "organic"]
    urls = [item["url"] for item in organic if item.get("url")][:10]

    return {"urls": urls}
