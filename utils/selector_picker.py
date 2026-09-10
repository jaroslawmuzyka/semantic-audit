"""Backend interaktywnego podglądu do wybierania selektorów JINA (X-Remove-Selector /
X-Target-Selector) przez klikanie w wyrenderowaną stronę, zamiast pisania CSS ręcznie.

Cała logika parsowania/filtrowania/oznaczania HTML-a mieszka tu — utils/assets/
selector_picker/index.html to tylko statyczny frontend (komponent Streamlit), a app.py
tylko wywołuje funkcje z tego modułu i wpina wynik w pola formularza.

Przepływ:
1. fetch_html_raw() (utils/jina_api.py) pobiera surowy HTML strony — RAZ, cache'owany
   w session_state (patrz app.py), żeby dalsze kliknięcia/zmiany selektorów nie kosztowały
   kolejnych zapytań do JINA.
2. build_preview_fragment() filtruje ten HTML dokładnie tak, jak zrobiłaby to JINA z
   AKTUALNĄ zawartością pól "Usuń selektory"/"Celuj w selektory" (żeby podgląd pokazywał
   to, co NAPRAWDĘ zostałoby wysłane do analizy), czyści go z niebezpiecznych/zbędnych
   elementów (script/style/obrazki), i oznacza KAŻDY węzeł atrybutem data-sel (gotowy
   selektor CSS) oraz data-label (czytelna etykieta do okruszków/breadcrumbów).
3. Komponent frontendowy renderuje to, obsługuje hover/breadcrumb/klik i odsyła wybrany
   selektor + akcję (exclude/target) z powrotem do Pythona.
"""
from bs4 import BeautifulSoup, Comment

# Tagi usuwane w całości — albo niebezpieczne (mogłyby wykonać JS w podglądzie),
# albo nieistotne dla wyboru selektorów (obrazki/media, tak jak w reszcie pipeline'u
# X-Retain-Images: none).
_STRIP_TAGS = [
    "script", "style", "noscript", "template", "link",
    "iframe", "object", "embed",
    "img", "picture", "svg", "video", "audio", "source",
]

# Puste/samodomykające się tagi, których nie warto oznaczać jako klikalne cele
# (nic sensownego nie da się w nich "wykluczyć").
_SKIP_ANNOTATE_TAGS = {"br", "hr", "wbr", "meta", "head", "html"}

# Twardy limit oznaczanych węzłów — zabezpieczenie przed bardzo dużymi/głębokimi
# stronami, żeby przeglądarka użytkownika nie ugrzęzła.
MAX_ANNOTATED_NODES = 4000


def _strip_dangerous_and_noisy(soup: BeautifulSoup) -> None:
    for tag_name in _STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Komentarze HTML — bez znaczenia dla wyboru selektorów, tylko zaśmiecają.
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Atrybuty on*="..." (onclick, onload...) i javascript: w href/src — na wszelki
    # wypadek, mimo że <script> już usunięty (inline handlery to osobny wektor).
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower().startswith("on"):
                del tag.attrs[attr]
        for attr in ("href", "src"):
            val = tag.attrs.get(attr)
            if isinstance(val, str) and val.strip().lower().startswith("javascript:"):
                del tag.attrs[attr]


def _human_label(tag) -> str:
    parts = [tag.name]
    if tag.get("id"):
        parts.append(f'#{tag["id"]}')
    classes = tag.get("class") or []
    if classes:
        parts.append("." + ".".join(classes[:2]))
    text = " ".join(tag.stripped_strings)[:40].strip()
    label = "".join(parts)
    if text:
        label += f': "{text}{"…" if len(" ".join(tag.stripped_strings)) > 40 else ""}"'
    return label


def compute_selector(tag) -> str:
    """Praktyczny, czytelny selektor CSS dla węzła — nie gwarantuje globalnej
    unikalności (nie jest to potrzebne: to selektor do wykluczenia/celowania,
    analogiczny do tego, co użytkownik wpisałby ręcznie), ale w normalnych
    przypadkach (id/klasa) trafia dokładnie w oczekiwany element/grupę elementów.
    """
    if tag.get("id"):
        return f'#{tag["id"]}'
    classes = tag.get("class") or []
    if classes:
        return tag.name + "." + ".".join(classes[:3])
    parent = tag.parent
    if parent is None or not hasattr(parent, "find_all"):
        return tag.name
    siblings = parent.find_all(tag.name, recursive=False)
    try:
        idx = siblings.index(tag) + 1
    except ValueError:
        idx = 1
    return f"{tag.name}:nth-of-type({idx})"


def _annotate(soup: BeautifulSoup) -> int:
    """Dopisuje data-sel/data-label do każdego sensownego węzła. Zwraca liczbę oznaczonych węzłów."""
    count = 0
    for tag in soup.find_all(True):
        if count >= MAX_ANNOTATED_NODES:
            break
        if tag.name in _SKIP_ANNOTATE_TAGS:
            continue
        if not tag.get_text(strip=True) and not tag.find(True):
            continue  # pusty węzeł bez tekstu i bez dzieci — nic do kliknięcia
        tag["data-sel"] = compute_selector(tag)
        tag["data-label"] = _human_label(tag)
        count += 1
    return count


def build_preview_fragment(raw_html: str, remove_selector: str = "", target_selector: str = "") -> dict:
    """Filtruje surowy HTML dokładnie tak, jak zrobiłaby to JINA z podanymi selektorami,
    czyści go i oznacza węzły do interaktywnego podglądu.

    Zwraca dict: {"html": <fragment do wstrzyknięcia w komponent>, "node_count": int,
    "truncated": bool} — "truncated" mówi, czy zadziałał MAX_ANNOTATED_NODES.
    """
    soup = BeautifulSoup(raw_html or "", "html.parser")

    root = soup.body or soup
    if target_selector and target_selector.strip():
        try:
            matches = root.select(target_selector)
        except Exception:
            matches = []
        if matches:
            new_root = soup.new_tag("div")
            for m in matches:
                new_root.append(m.extract())
            root = new_root

    if remove_selector and remove_selector.strip():
        try:
            for el in root.select(remove_selector):
                el.decompose()
        except Exception:
            pass  # niepoprawny selektor w polu — po prostu nic nie usuwamy z podglądu

    _strip_dangerous_and_noisy(root if hasattr(root, "find_all") else soup)
    node_count = _annotate(root if hasattr(root, "find_all") else soup)

    fragment = root.decode_contents() if hasattr(root, "decode_contents") else str(root)
    return {
        "html": fragment,
        "node_count": node_count,
        "truncated": node_count >= MAX_ANNOTATED_NODES,
    }


def merge_selector(existing: str, new_selector: str) -> str:
    """Dokleja nowy selektor do istniejącej, przecinkowej listy — bez duplikatów."""
    parts = [p.strip() for p in (existing or "").split(",") if p.strip()]
    if new_selector not in parts:
        parts.append(new_selector)
    return ", ".join(parts)
