"""Przeregenerowanie i patchowanie WYŁĄCZNIE sekcji E-E-A-T w już istniejących
raportach (XLSX/HTML, pojedynczych i masowych).

Nie przebudowuje plików od zera — otwiera dokładnie ten plik, który użytkownik
wgrał, i nadpisuje tylko komórki/fragmenty HTML dotyczące E-E-A-T. Cała
reszta pliku (formatowanie, inne arkusze/sekcje, branding) zostaje bez zmian.
"""
import io
import re
import html as html_lib

import openpyxl
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

from utils.openai_llm import analyze_eeat_only
from utils.naming import safe_filename

EEAT_ORDER = ["Experience", "Expertise", "Authority", "Trust"]

_ALIGN_TOP_WRAP = Alignment(vertical="top", wrap_text=True)


# --------------------------------------------------------------------------
# Detekcja typu pliku
# --------------------------------------------------------------------------

def detect_file_kind(filename: str, file_bytes: bytes) -> str:
    """Zwraca 'xlsx_single', 'xlsx_master', 'html_single', 'html_master' albo 'unknown'."""
    name = filename.lower()
    if name.endswith(".xlsx"):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
        except Exception:
            return "unknown"
        sheets = set(wb.sheetnames)
        if "Rekomendacje (Actionable)" in sheets or "Pełny Raport" in sheets:
            return "xlsx_master"
        if "EEAT Analysis" in sheets:
            return "xlsx_single"
        return "unknown"
    if name.endswith(".html") or name.endswith(".htm"):
        text = file_bytes.decode("utf-8", errors="ignore")
        if 'class="url-details"' in text:
            return "html_master"
        if "Braki E-E-A-T" in text:
            return "html_single"
        return "unknown"
    return "unknown"


# --------------------------------------------------------------------------
# Ekstrakcja URL-i / treści źródłowej z wgranych plików
# --------------------------------------------------------------------------

def _unique_keep_order(items):
    seen = set()
    out = []
    for i in items:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def extract_urls_from_master_xlsx(file_bytes: bytes) -> list:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    for sheet_name in ("Rekomendacje (Actionable)", "Pełny Raport"):
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        rows = ws.iter_rows(values_only=True)
        headers = list(next(rows, []))
        if "URL" not in headers:
            continue
        url_idx = headers.index("URL")
        urls = [str(r[url_idx]).strip() for r in rows if r and r[url_idx] and str(r[url_idx]).strip()]
        return _unique_keep_order(urls)
    return []


def extract_urls_from_master_html(file_bytes: bytes) -> list:
    text = file_bytes.decode("utf-8", errors="ignore")
    raw = re.findall(r'<span class="s-url">(.*?)</span>', text, re.DOTALL)
    return _unique_keep_order(html_lib.unescape(r).strip() for r in raw)


def extract_url_from_single_html(file_bytes: bytes) -> str:
    text = file_bytes.decode("utf-8", errors="ignore")
    m = re.search(r'<strong>URL:</strong>\s*<a href="([^"]*)"', text)
    return html_lib.unescape(m.group(1)).strip() if m else ""


def guess_url_for_individual_file(filename: str, known_urls: list) -> str:
    """Odgaduje URL dla pliku indywidualnego XLSX (który nie ma wbudowanego URL-a)
    na podstawie konwencji nazewnictwa 'audit_{safe_filename(url)}.xlsx' używanej
    przy eksporcie (patrz safe_filename() w utils/naming.py). Zwraca dopasowany
    URL albo pusty string, jeśli żaden ze znanych adresów nie pasuje do nazwy.
    """
    base = filename.rsplit("/", 1)[-1]
    stem = re.sub(r"\.(xlsx|html?)$", "", base, flags=re.IGNORECASE)
    if stem.startswith("audit_"):
        stem = stem[len("audit_"):]
    for url in known_urls:
        if safe_filename(url) == stem:
            return url
    return ""


def extract_source_content_from_single_xlsx(file_bytes: bytes) -> str:
    """Skleja z powrotem 'Raw Source Content' (dzielone na wiersze przy eksporcie limitem 32k)."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    if "Raw Source Content" not in wb.sheetnames:
        return ""
    ws = wb["Raw Source Content"]
    chunks = []
    for row in ws.iter_rows(min_row=2, max_col=1, values_only=True):
        if row and row[0]:
            chunks.append(str(row[0]))
    return "".join(chunks)


# --------------------------------------------------------------------------
# Regeneracja przez OpenAI
# --------------------------------------------------------------------------

def regenerate_eeat(source_content, language, user_context, system_prompt, model_name):
    """Zwraca (lista dokładnie 4 EEATSignal w kolejności EEAT_ORDER, usage)."""
    breakdown, usage = analyze_eeat_only(source_content, system_prompt, language, user_context, model_name)
    return breakdown.as_list(), usage


def eeat_missing_lines(eeat_list) -> list:
    return [f"[{e.dimension}]: {e.missing_signals}" for e in eeat_list if e.missing_signals and e.missing_signals.strip()]


# --------------------------------------------------------------------------
# Patchowanie XLSX
# --------------------------------------------------------------------------

def _autofit_column(ws, col_idx, max_width=80, min_width=15):
    col_letter = get_column_letter(col_idx)
    max_len = 0
    for row in range(1, ws.max_row + 1):
        val = ws.cell(row=row, column=col_idx).value
        if val is None:
            continue
        line_len = max(len(line) for line in str(val).split("\n"))
        max_len = max(max_len, line_len)
    if max_len > max_width:
        ws.column_dimensions[col_letter].width = max_width
    elif max_len > min_width:
        ws.column_dimensions[col_letter].width = max_len + 2
    else:
        ws.column_dimensions[col_letter].width = min_width


def patch_single_xlsx(file_bytes: bytes, eeat_list: list) -> bytes:
    """Nadpisuje arkusz 'EEAT Analysis' (dokładnie 4 wiersze), reszta pliku bez zmian."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
    if "EEAT Analysis" not in wb.sheetnames:
        raise ValueError("Nie znaleziono arkusza 'EEAT Analysis' w tym pliku.")
    ws = wb["EEAT Analysis"]

    if ws.max_row > 5:
        ws.delete_rows(6, ws.max_row - 5)

    for i, e in enumerate(eeat_list, start=2):
        ws.cell(row=i, column=1, value=e.dimension).alignment = _ALIGN_TOP_WRAP
        ws.cell(row=i, column=2, value=e.score).alignment = _ALIGN_TOP_WRAP
        ws.cell(row=i, column=3, value=e.present_signals).alignment = _ALIGN_TOP_WRAP
        ws.cell(row=i, column=4, value=e.missing_signals).alignment = _ALIGN_TOP_WRAP

    for col in range(1, 5):
        _autofit_column(ws, col)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def patch_master_xlsx(file_bytes: bytes, url_to_eeat: dict) -> bytes:
    """Nadpisuje tylko wiersze wskazane w url_to_eeat (klucz = URL) w:
    - 'Rekomendacje (Actionable)' -> kolumna 'Braki E-E-A-T'
    - 'Pełny Raport' -> kanoniczne kolumny 'EEAT {Wymiar} Score/Missing' (dodane, jeśli brakuje)
    Pozostałe wiersze i arkusze zostają bez zmian.
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))

    if "Rekomendacje (Actionable)" in wb.sheetnames:
        ws = wb["Rekomendacje (Actionable)"]
        headers = [c.value for c in ws[1]]
        if "URL" in headers and "Braki E-E-A-T" in headers:
            url_col = headers.index("URL") + 1
            eeat_col = headers.index("Braki E-E-A-T") + 1
            for row in range(2, ws.max_row + 1):
                url_val = ws.cell(row=row, column=url_col).value
                key = str(url_val).strip() if url_val else ""
                if key in url_to_eeat:
                    lines = eeat_missing_lines(url_to_eeat[key])
                    cell = ws.cell(row=row, column=eeat_col, value="\n".join(lines) if lines else "Brak")
                    cell.alignment = _ALIGN_TOP_WRAP
            _autofit_column(ws, eeat_col)

    if "Pełny Raport" in wb.sheetnames:
        ws = wb["Pełny Raport"]
        headers = [c.value for c in ws[1]]
        if "URL" in headers:
            url_col = headers.index("URL") + 1
            header_style_src = ws.cell(row=1, column=1)

            col_index = {}
            next_col = ws.max_column
            for dim in EEAT_ORDER:
                for suffix in ("Score", "Missing"):
                    name = f"EEAT {dim} {suffix}"
                    if name in headers:
                        col_index[name] = headers.index(name) + 1
                    else:
                        next_col += 1
                        header_cell = ws.cell(row=1, column=next_col, value=name)
                        header_cell.font = header_style_src.font
                        header_cell.fill = header_style_src.fill
                        header_cell.alignment = header_style_src.alignment
                        col_index[name] = next_col
                        headers.append(name)

            for row in range(2, ws.max_row + 1):
                url_val = ws.cell(row=row, column=url_col).value
                key = str(url_val).strip() if url_val else ""
                if key not in url_to_eeat:
                    continue
                by_dim = {e.dimension: e for e in url_to_eeat[key]}
                for dim in EEAT_ORDER:
                    e = by_dim.get(dim)
                    if not e:
                        continue
                    sc = ws.cell(row=row, column=col_index[f"EEAT {dim} Score"], value=e.score)
                    sc.alignment = _ALIGN_TOP_WRAP
                    mc = ws.cell(row=row, column=col_index[f"EEAT {dim} Missing"], value=e.missing_signals)
                    mc.alignment = _ALIGN_TOP_WRAP

            for name, idx in col_index.items():
                _autofit_column(ws, idx)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# --------------------------------------------------------------------------
# Patchowanie HTML
# --------------------------------------------------------------------------

def _eeat_li_html(eeat_list, empty_text) -> str:
    lines = [
        f"<li>[{html_lib.escape(e.dimension)}]: {html_lib.escape(e.missing_signals)}</li>"
        for e in eeat_list if e.missing_signals and e.missing_signals.strip()
    ]
    return "".join(lines) if lines else empty_text


def patch_single_html(file_bytes: bytes, eeat_list: list) -> bytes:
    text = file_bytes.decode("utf-8")
    new_inner = _eeat_li_html(eeat_list, "<li>Brak istotnych braków w sygnałach E-E-A-T.</li>")

    marker_re = re.compile(
        r"(<!--EEAT_BLOCK:START-->\s*<ul>\s*)(.*?)(\s*</ul>\s*<!--EEAT_BLOCK:END-->)", re.DOTALL
    )
    if marker_re.search(text):
        text = marker_re.sub(lambda m: m.group(1) + new_inner + m.group(3), text, count=1)
    else:
        fallback_re = re.compile(r"(<h4>Braki E-E-A-T</h4>\s*<ul>\s*)(.*?)(\s*</ul>)", re.DOTALL)
        if not fallback_re.search(text):
            raise ValueError("Nie znaleziono sekcji 'Braki E-E-A-T' w tym pliku HTML.")
        text = fallback_re.sub(lambda m: m.group(1) + new_inner + m.group(3), text, count=1)

    return text.encode("utf-8")


def patch_master_html(file_bytes: bytes, url_to_eeat: dict) -> bytes:
    text = file_bytes.decode("utf-8")
    block_re = re.compile(r'<details class="url-details">.*?</details>', re.DOTALL)

    def patch_block(m):
        block = m.group(0)
        url_m = re.search(r'<span class="s-url">(.*?)</span>', block, re.DOTALL)
        if not url_m:
            return block
        key = html_lib.unescape(url_m.group(1)).strip()
        if key not in url_to_eeat:
            return block

        new_inner = _eeat_li_html(url_to_eeat[key], "<li>Brak</li>")
        esc_url = re.escape(html_lib.escape(key))
        marker_re = re.compile(
            r"(<!--EEAT_BLOCK:START:" + esc_url + r'-->\s*<ul class="data-list">\s*)(.*?)'
            r"(\s*</ul>\s*<!--EEAT_BLOCK:END:" + esc_url + r"-->)",
            re.DOTALL,
        )
        if marker_re.search(block):
            return marker_re.sub(lambda mm: mm.group(1) + new_inner + mm.group(3), block, count=1)

        fallback_re = re.compile(r'(<h4>Braki E-E-A-T:</h4>\s*<ul class="data-list">\s*)(.*?)(\s*</ul>)', re.DOTALL)
        return fallback_re.sub(lambda mm: mm.group(1) + new_inner + mm.group(3), block, count=1)

    new_text = block_re.sub(patch_block, text)
    return new_text.encode("utf-8")
