import os
import requests
import time
import streamlit as st

API_BASE = "https://api.nodeshub.io/v1/search"

def get_api_key():
    try:
        return st.secrets.get("NODESHUB_API_KEY")
    except Exception:
        return os.environ.get("NODESHUB_API_KEY")

def _search_impl(keyword, hl="pl", gl="pl", max_retries=3):
    api_key = get_api_key()
    if not api_key:
        return {"error": "NODESHUB_API_KEY is missing"}

    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"keyword": keyword, "hl": hl, "gl": gl}

    for attempt in range(max_retries):
        try:
            resp = requests.get(API_BASE, headers=headers, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                return extract_relevant_data(data)
            elif resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
            else:
                return {"error": f"API returned {resp.status_code}: {resp.text}"}
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                return {"error": str(e)}

    return {"error": "Max retries exceeded"}


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
    results = data.get("data", {}).get("results", {})
    if not results.get("success"):
        return {"error": "Search was not successful."}

    organic = results.get("organic_results", [])
    urls = [r.get("url") for r in organic if r.get("url")]

    snippets = results.get("snippets", {})
    paa = snippets.get("people_also_ask", {}).get("questions", [])
    paa_texts = [q.get("text") for q in paa if q.get("text")]

    related = snippets.get("related_searches", {}).get("queries", [])
    
    return {
        "urls": urls[:10], # Top 10
        "organic_results": organic[:10],
        "paa": paa_texts,
        "related_searches": related
    }
