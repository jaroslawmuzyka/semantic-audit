# Motywy brandowe raportów (HTML + XLSX).
# PG:  paleta z artur-pg-report-flex/config/branding.yaml
# WPP: paleta ze skilla wpp-branding (references/wpp-html-branding.md);
#      zgodnie ze spec HTML używa fontów Sora + DM Sans (fonty WPP OTF/WOFF są do PPTX).

THEMES = {
    "PG": {
        "key": "PG",
        "label": "Performance Group",
        "font_link": "https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap",
        "font_heading": "'Manrope', sans-serif",
        "font_body": "'Manrope', sans-serif",
        # Kolory bazowe
        "navy": "#191C62",
        "navy2": "#2D307C",
        "text_main": "#191C62",
        "muted": "#666699",
        "accent": "#FF7D33",
        "accent2": "#EE492E",
        # Statusy
        "good": "#2DAB66",
        "warn": "#F4B400",
        "bad": "#EE492E",
        # Tła i obramowania
        "body_bg": "background-color: #F1F1F7;",
        "card_bg": "#FFFFFF",
        "card_soft": "#F1F1F7",
        "card_soft_border": "#D9E2F3",
        "line": "#D9E2F3",
        "dots_overlay": False,
        # Pasek brandowy u góry raportu
        "header_bg": "linear-gradient(90deg, #191C62, #2D307C)",
        "brand_html": (
            "<span style=\"color:#FFFFFF;\">Performance</span>"
            "<span style=\"color:#FF7D33;\">&nbsp;Group</span>"
        ),
        # Wykres radarowy
        "chart_fill": "rgba(25, 28, 98, 0.15)",
        "chart_border": "rgba(25, 28, 98, 0.85)",
        "chart_point": "#FF7D33",
        # Tabele HTML
        "table_header_bg": "#191C62",
        "table_header_text": "#FFFFFF",
        # Excel
        "excel_header_fill": "191C62",
        "excel_alt_row_fill": "D9E2F3",
        "excel_font": "Manrope",
    },
    "WPP": {
        "key": "WPP",
        "label": "WPP Media",
        "font_link": (
            "https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800"
            "&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&display=swap"
        ),
        "font_heading": "'Sora', sans-serif",
        "font_body": "'DM Sans', sans-serif",
        # Kolory bazowe
        "navy": "#0a1a4f",
        "navy2": "#15267e",
        "text_main": "#10224f",
        "muted": "#5a6a8a",
        "accent": "#19d3d6",
        "accent2": "#9be15d",
        # Statusy
        "good": "#2f9e6e",
        "warn": "#e09a2f",
        "bad": "#e0556b",
        # Tła i obramowania (gradient signature WPP)
        "body_bg": (
            "background:"
            " radial-gradient(ellipse at 0% 0%, rgba(155, 225, 93, 0.18) 0%, transparent 60%),"
            " radial-gradient(ellipse at 100% 0%, rgba(91, 124, 255, 0.18) 0%, transparent 60%),"
            " radial-gradient(ellipse at 50% 50%, rgba(25, 211, 214, 0.10) 0%, transparent 70%),"
            " radial-gradient(ellipse at 100% 100%, rgba(123, 108, 255, 0.15) 0%, transparent 60%),"
            " linear-gradient(135deg, #eaf6f3 0%, #e7f0ff 50%, #eef9ec 100%);"
            " background-attachment: fixed;"
        ),
        "card_bg": "rgba(255, 255, 255, 0.74)",
        "card_soft": "#E1ECF6",
        "card_soft_border": "rgba(10, 26, 79, 0.10)",
        "line": "rgba(10, 26, 79, 0.10)",
        "dots_overlay": True,
        # Pasek brandowy u góry raportu
        "header_bg": "linear-gradient(90deg, #0a1a4f, #15267e)",
        "brand_html": (
            "<span style=\"color:#FFFFFF;\">WPP</span>"
            "<span style=\"color:#9be15d;\">&nbsp;Media</span>"
        ),
        # Wykres radarowy
        "chart_fill": "rgba(25, 211, 214, 0.2)",
        "chart_border": "rgba(25, 211, 214, 0.9)",
        "chart_point": "#9be15d",
        # Tabele HTML
        "table_header_bg": "#0a1a4f",
        "table_header_text": "#FFFFFF",
        # Excel
        "excel_header_fill": "0A1A4F",
        "excel_alt_row_fill": "E1ECF6",
        "excel_font": "DM Sans",
    },
}

THEME_KEYS = list(THEMES.keys())


def get_theme(key: str) -> dict:
    return THEMES[key]
