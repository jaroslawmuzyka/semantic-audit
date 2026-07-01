import os
import requests
import re
import time
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed

API_BASE = "https://r.jina.ai/"

def get_api_key():
    try:
        return st.secrets.get("JINA_API_KEY")
    except Exception:
        return os.environ.get("JINA_API_KEY")

def clean_content(text):
    text = re.sub(r'\[!\[[^\]]*\]\([^\)]*\)\]\([^\)]*\)', '', text)
    text = re.sub(r'!\[[^\]]*\]\([^\)]*\)', '', text)
    lines = text.split('\n')
    cleaned_lines = []
    nav_buffer = []

    for line in lines:
        stripped = line.strip()
        is_nav_item = bool(re.match(r'^[*\-]\s+\[', stripped)) or bool(re.match(r'^\*\s+\[', stripped))

        if is_nav_item:
            nav_buffer.append(line)
        else:
            if len(nav_buffer) >= 3:
                pass
            else:
                cleaned_lines.extend(nav_buffer)
            nav_buffer = []
            cleaned_lines.append(line)

    if len(nav_buffer) < 3:
        cleaned_lines.extend(nav_buffer)

    text = '\n'.join(cleaned_lines)
    lines = text.split('\n')
    lines = [l for l in lines if len(re.findall(r'\[[^\]]*\]\([^\)]*\)', l)) < 3]
    text = '\n'.join(lines)
    text = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', text)

    boilerplate = re.compile(
        r'do koszyka|zaloguj się|zaloguj$|utwórz konto|załóż konto|cookie|'
        r'polityka prywatności|regulamin serwisu|'
        r'edytuj kod źródłowy|edytuj sekcję|edytuj linki|'
        r'strony specjalne|ostatnie zmiany|'
        r'prześlij plik|wersja do druku|'
        r'narzędzia osobiste|menu główne|'
        r'przejdź do zawartości|spis treści|'
        r'przypnij ukryj|przełącz podsekcję|przełącz stan|'
        r'linkujące|zmiany w linkowanych|'
        r'cytowanie tego|skrócony adres|pobierz kod qr|'
        r'utwórz książkę|pobierz jako pdf|'
        r'multimedia w wikimedia|hasło w wikisłowniku|'
        r'element wikidanych|w innych projektach|'
        r'wyszukaj produkt|brak podpowiedzi|pokaż wszystkie|'
        r'darmowa dostawa|zamknij menu|'
        r'^\s*zamknij\s*$|^\s*menu\s*$|^\s*szukaj\s*$|'
        r'portal pacjenta|umów wizytę|'
        r'zobacz pełną listę|katalog wszystkich|'
        r'strona główna$|poradnik o zdrowiu$|'
        r'aplikacja mobilna|zlecenia nfz|szczepienia online|'
        r'wspomóż wikipedię|dla wikipedystów|'
        r'nawigacja\s*$|dla czytelników\s*$|'
        r'^\s*\- \[x\]|'
        r'^\s*logowanie\s*$|^\s*wygląd\s*$|'
        r'^\s*\d+\s+języ',
        re.IGNORECASE
    )
    lines = text.split('\n')
    lines = [l for l in lines if not boilerplate.search(l)]
    lines = [l for l in lines if not re.match(r'^\s*[-=]{3,}\s*$', l)]
    lines = [l for l in lines if not re.match(r'^\s*\|[\s\-|]*\|\s*$', l)]
    
    def is_ui_fragment(line):
        s = line.strip()
        if not s or s.startswith('#'):
            return False
        words = s.split()
        if len(words) <= 2 and not any(c.isdigit() for c in s):
            if any(c in s for c in '°%±≤≥<>'):
                return False
            return True
        return False

    lines = [l for l in lines if not is_ui_fragment(l)]
    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def truncate_content(content, max_words=1500):
    words = content.split()
    if len(words) <= max_words:
        return content
    return ' '.join(words[:max_words]) + '\n\n[... treść skrócona do 1500 słów ...]'

def fetch_url(url, max_retries=3, remove_selector=None):
    headers = {
        "Accept": "application/json",
        "X-Return-Format": "markdown",
    }
    if remove_selector:
        headers["X-Remove-Selector"] = remove_selector
    
    api_key = get_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request_url = f"{API_BASE}{url}"
    
    for attempt in range(max_retries):
        try:
            resp = requests.get(request_url, headers=headers, timeout=60)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
            else:
                return None
        except requests.exceptions.RequestException:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                return None
    return None

def process_single_url(url, clean=True, remove_selector=None):
    data = fetch_url(url, remove_selector=remove_selector)
    if not data:
        return {"url": url, "status": "ERROR", "content": None, "title": None, "word_count": 0}
        
    title = data.get("data", {}).get("title", "")
    content = data.get("data", {}).get("content", "")
    
    if clean:
        content = clean_content(content)
        
    word_count = len(content.split())
    status = "OK" if word_count >= 200 else "SKIP"
    
    return {
        "url": url,
        "title": title,
        "content": content,
        "word_count": word_count,
        "status": status
    }

def fetch_competitors_batch(urls, max_words_per_competitor=1500, max_workers=5, remove_selector=None):
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_single_url, url, True, remove_selector): url for url in urls}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception:
                pass
                
    ok_results = [r for r in results if r["status"] == "OK"]
    
    consolidated_lines = []
    consolidated_lines.append(f"Competitors: {len(ok_results)} OK\n")
    
    for i, r in enumerate(ok_results, 1):
        truncated = truncate_content(r["content"], max_words_per_competitor)
        consolidated_lines.append(f"## K{i}: {r['title']}")
        consolidated_lines.append(f"**Source:** {r['url']}")
        consolidated_lines.append(f"**Words:** {r['word_count']}\n")
        consolidated_lines.append(truncated)
        consolidated_lines.append("\n---\n")
        
    return {
        "results": results,
        "consolidated_markdown": "\n".join(consolidated_lines),
        "ok_count": len(ok_results)
    }
