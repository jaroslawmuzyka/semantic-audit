import json
import html as html_lib
from functools import lru_cache
from pathlib import Path
from utils.openai_llm import GapAnalysisResult, ContentScores, AuditReport
from utils.themes import get_theme

_CHARTJS_PATH = Path(__file__).parent / "assets" / "chart.umd.min.js"


@lru_cache(maxsize=1)
def _chartjs_inline() -> str:
    """Osadza Chart.js w raporcie, żeby wykresy działały offline (bez CDN)."""
    try:
        return f"<script>{_CHARTJS_PATH.read_text(encoding='utf-8')}</script>"
    except OSError:
        # Fallback na CDN, gdyby plik zniknął z repo.
        return '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>'


def esc(value) -> str:
    """Escapuje treści dynamiczne (LLM / scraping) przed wstawieniem do HTML."""
    return html_lib.escape(str(value if value is not None else ""))


WSTEP_INNER = """
    <div style="margin-top: 20px; font-size: 15px; line-height: 1.6;">
        <h3 style="margin-top: 0;">Wstęp do Audytu Semantycznego: Jak Google i AI "czytają" Twoje treści?</h3>
        <p>Celem tego audytu nie jest tylko sprawdzenie, czy tekst "dobrze się czyta" ludziom. Naszym głównym zadaniem jest dostosowanie treści do sposobu, w jaki analizują ją <strong>algorytmy Google oraz nowoczesne modele AI</strong> (takie jak ChatGPT czy Google AI Overviews).</p>
        <p>Audyt składa się z <strong>3 głównych filarów</strong>, które sprawdzają treść pod kątem co najmniej 12 kluczowych kryteriów:</p>
        <ol>
        <li><strong>Zgodność z Central Search Intent (CSI)</strong> – czy algorytm rozumie, o czym dokładnie piszesz i dla kogo?</li>
        <li><strong>Jakość treści</strong> – jak kosztowna i trudna w interpretacji jest Twoja strona dla robota?</li>
        <li><strong>Ocena E-E-A-T</strong> – czy Google uważa Cię za wiarygodnego eksperta?</li>
        </ol>

        <hr class="wstep-hr">

        <h4 class="wstep-h4">1. Zgodność z Central Search Intent (CSI)</h4>
        <p><em>(Analiza: EAV GAP + BLUF + Chunk + URR)</em><br>
        Tutaj sprawdzamy, czy Twój artykuł odpowiada na intencję użytkownika i czy jest zbudowany tak, aby maszyna mogła bezbłędnie zidentyfikować temat przewodni.</p>
        <ul>
        <li><strong>Central Search Intent (CSI):</strong> To matematyczne połączenie tematu (Encji) z kontekstem źródła. Algorytm musi wiedzieć, z jakiej perspektywy opisujesz temat.</li>
        <li><strong>Entity-Attribute-Value (EAV):</strong> Google dąży do wyekstrahowania z tekstu "suchych faktów" i zapisania ich w tabeli (Grafie Wiedzy). Sprawdzimy, czy Twój tekst to "lita ściana tekstu", czy ustrukturyzowana baza wiedzy.</li>
        <li><strong>BLUF (Bottom Line Up Front):</strong> Najważniejsza informacja musi znaleźć się na początku. Google i AI często skanują tylko początek sekcji.</li>
        <li><strong>CHUNK (Fragmentacja pod RAG):</strong> Każda sekcja pod nagłówkiem powinna być samodzielną, wyczerpującą odpowiedzią na dany problem.</li>
        <li><strong>URR (Unique, Root, Rare):</strong> Aby content był uznany za wybitny, musisz ułożyć atrybuty encji w odpowiedniej hierarchii (definiujące, wyróżniające, niszowe).</li>
        </ul>

        <hr class="wstep-hr">

        <h4 class="wstep-h4">2. Jakość treści</h4>
        <p><em>(Analiza: CoR + Information Density + SRL + TF-IDF)</em><br>
        W tej sekcji mierzymy efektywność Twojego tekstu. Czy dostarczasz wiedzę szybko i konkretnie, czy zmuszasz Google do "marnowania prądu"?</p>
        <ul>
        <li><strong>CoR (Cost of Retrieval):</strong> Wydatek obliczeniowy, jaki wyszukiwarka ponosi na przeczytanie Twojej strony. Google wybierze konkurencję, która dostarczy tę samą wiedzę "taniej".</li>
        <li><strong>Information Density (Gęstość Informacji):</strong> Stosunek konkretnych faktów do "puchu" (fluff). Im więcej faktów i konkretów, tym wyższa ocena.</li>
        <li><strong>SRL (Semantic Role Labeling):</strong> To gramatyka dla robotów. Wskazanie: Kto? Co robi? Komu? Należy usuwać stronę bierną, aby Twoja Encja była "Bohaterem" zdania.</li>
        <li><strong>TF-IDF (Trafność terminologiczna):</strong> Ocena używania specjalistycznego i rzadkiego słownictwa (IDF), które daje silny sygnał bycia ekspertem.</li>
        </ul>

        <hr class="wstep-hr">

        <h4 class="wstep-h4">3. Ocena E-E-A-T</h4>
        <p><em>(Experience, Expertise, Authoritativeness, Trustworthiness)</em><br>
        System, którym Google ocenia wiarygodność Twoją i Twojej strony (krytyczne dla branż YMYL).</p>
        <ul>
        <li><strong>Experience:</strong> Czy widać dowody używania produktu/przeżycia doświadczenia (własne zdjęcia, opis odczuć)?</li>
        <li><strong>Expertise:</strong> Czy autor ma wiedzę formalną?</li>
        <li><strong>Authoritativeness:</strong> Czy inni eksperci cytują tę stronę?</li>
        <li><strong>Trust:</strong> Czy strona jest bezpieczna i prawdziwa?</li>
        </ul>
    </div>
"""


def _wstep_html(theme: dict) -> str:
    return f"""
    <details class="wstep-details">
        <summary>Wstęp i definicje (Rozwiń)</summary>
        {WSTEP_INNER}
    </details>
    """


def _brand_header(theme: dict) -> str:
    return f"""
    <div class="brand-bar">
        <span class="brand-logo">{theme['brand_html']}</span>
        <span class="brand-sub">&middot; Audyt Semantyczny Treści</span>
    </div>
    """


def _brand_footer(theme: dict) -> str:
    return f"""
    <footer class="brand-footer">
        Raport przygotowany przez <strong>{esc(theme['label'])}</strong> &middot; Audyt Semantyczny Treści
    </footer>
    """


def _base_css(theme: dict) -> str:
    dots_css = ""
    if theme["dots_overlay"]:
        dots_css = """
            .dots {
                position: fixed; inset: 0; pointer-events: none; z-index: 0;
                background-image: radial-gradient(circle, rgba(10,26,79,0.06) 1px, transparent 1px);
                background-size: 28px 28px;
            }
        """
    return f"""
        @import url('{theme['font_link']}');

        :root {{
            --navy: {theme['navy']};
            --navy2: {theme['navy2']};
            --text-main: {theme['text_main']};
            --muted: {theme['muted']};
            --accent: {theme['accent']};
            --accent2: {theme['accent2']};
            --good: {theme['good']};
            --warn: {theme['warn']};
            --bad: {theme['bad']};
            --card-bg: {theme['card_bg']};
            --card-soft: {theme['card_soft']};
            --card-soft-border: {theme['card_soft_border']};
            --line: {theme['line']};
        }}
        body {{
            font-family: {theme['font_body']};
            {theme['body_bg']}
            color: var(--text-main);
            margin: 0;
            padding: 0 20px 40px 20px;
        }}
        h1, h2, h3, h4, .score-value, .stat-val, .brand-logo {{
            font-family: {theme['font_heading']};
        }}
        {dots_css}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            position: relative;
            z-index: 1;
        }}
        .brand-bar {{
            background: {theme['header_bg']};
            margin: 0 -20px 30px -20px;
            padding: 18px 40px;
            display: flex;
            align-items: baseline;
            gap: 10px;
        }}
        .brand-logo {{
            font-size: 22px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }}
        .brand-sub {{
            color: rgba(255,255,255,0.75);
            font-size: 14px;
        }}
        .brand-footer {{
            margin-top: 40px;
            padding: 20px;
            text-align: center;
            font-size: 13px;
            color: var(--muted);
            border-top: 1px solid var(--line);
        }}
        .brand-footer strong {{
            color: var(--navy);
        }}
        .wstep-details {{
            background: var(--card-bg);
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 25px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.03);
            border-left: 4px solid var(--navy);
        }}
        .wstep-details summary {{
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            color: var(--navy);
        }}
        .wstep-hr {{
            border: 0;
            border-top: 1px solid var(--line);
            margin: 20px 0;
        }}
        .wstep-h4 {{
            color: var(--navy2);
        }}
        .header {{
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 26px;
            color: var(--text-main);
        }}
        .header p {{
            margin: 0;
            color: var(--muted);
            font-size: 15px;
        }}
        .header a {{
            color: var(--navy2);
            text-decoration: none;
        }}
        .grid-top {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .left-col {{
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}
        .score-cards {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        .score-card {{
            background-color: var(--card-soft);
            border: 1px solid var(--card-soft-border);
            border-radius: 12px;
            padding: 20px 25px;
            position: relative;
            box-shadow: 0 2px 10px rgba(0,0,0,0.02);
        }}
        .score-title {{
            color: var(--muted);
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 15px;
            display: block;
        }}
        .score-value {{
            font-size: 48px;
            font-weight: 800;
        }}
        .score-max {{
            font-size: 20px;
            color: var(--muted);
            font-weight: 500;
        }}
        .summary-card {{
            background-color: var(--card-bg);
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.03);
            border: 1px solid var(--line);
        }}
        .summary-text {{
            font-size: 16px;
            line-height: 1.6;
            margin-bottom: 25px;
        }}
        .summary-text strong {{
            color: var(--bad);
            font-weight: 600;
        }}
        .quick-wins-title {{
            font-size: 13px;
            font-weight: 700;
            color: var(--muted);
            text-transform: uppercase;
            margin-bottom: 15px;
            letter-spacing: 0.5px;
        }}
        .quick-win-card {{
            display: flex;
            align-items: center;
            padding: 14px 18px;
            border: 1px solid var(--line);
            border-radius: 8px;
            margin-bottom: 10px;
            background-color: var(--card-soft);
            transition: background-color 0.2s;
        }}
        .badge {{
            font-size: 11px;
            padding: 5px 10px;
            border-radius: 6px;
            margin-right: 15px;
            font-weight: 600;
        }}
        .badge-green {{
            background-color: rgba(45, 171, 102, 0.12);
            color: var(--good);
            border: 1px solid rgba(45, 171, 102, 0.3);
        }}
        .qw-text {{
            font-size: 14px;
            color: var(--text-main);
            font-weight: 500;
        }}
        .qw-impact {{
            color: var(--muted);
            font-size: 12px;
        }}
        .chart-card {{
            background-color: var(--card-bg);
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 8px 30px rgba(0,0,0,0.04);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--line);
        }}
        .chart-title {{
            width: 100%;
            font-size: 18px;
            font-weight: 800;
            margin-bottom: 25px;
            color: var(--text-main);
        }}
        .canvas-container {{
            width: 100%;
            max-width: 450px;
            aspect-ratio: 1;
        }}
        .details-section {{
            margin-top: 30px;
            background-color: var(--card-bg);
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.03);
            border: 1px solid var(--line);
        }}
        .details-section h2 {{
            font-size: 20px;
            margin-top: 0;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--line);
            padding-bottom: 15px;
        }}
        .before-after-block {{
            background: var(--card-soft);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 14px;
            border-left: 4px solid var(--accent);
        }}
        .before-text {{
            margin-top: 10px;
            color: var(--muted);
            font-style: italic;
        }}
        .after-text {{
            color: var(--good);
            margin-top: 15px;
            font-weight: 600;
            padding-top: 15px;
            border-top: 1px dashed var(--line);
        }}
        .structure-block {{
            margin-bottom: 15px;
            padding: 15px;
            background: var(--card-soft);
            border-left: 4px solid var(--navy2);
            border-radius: 4px;
        }}
        .structure-block .bluf {{
            color: var(--muted);
            font-size: 14px;
            display: inline-block;
            margin-top: 5px;
        }}
        table.eav-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            font-size: 14px;
        }}
        table.eav-table th {{
            padding: 10px;
            text-align: left;
            background-color: {theme['table_header_bg']};
            color: {theme['table_header_text']};
            font-size: 12px;
            text-transform: uppercase;
        }}
        table.eav-table td {{
            padding: 10px;
            border-bottom: 1px solid var(--line);
        }}
        .two-col-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        .two-col-grid h4 {{
            margin-top: 0;
            color: var(--text-main);
        }}
        .two-col-grid ul, .two-col-grid p {{
            padding-left: 20px;
            color: var(--muted);
            font-size: 14px;
        }}
        .two-col-grid p {{
            padding-left: 0;
            line-height: 1.6;
        }}
        @media (max-width: 900px) {{
            .grid-top, .two-col-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    """


def _radar_chart_js(theme: dict, canvas_id: str, labels_json: str, data_json: str, label_font_size: int = 12) -> str:
    return f"""
        const ctx_{canvas_id} = document.getElementById('{canvas_id}').getContext('2d');
        new Chart(ctx_{canvas_id}, {{
            type: 'radar',
            data: {{
                labels: {labels_json},
                datasets: [{{
                    label: 'Wynik Wymiaru',
                    data: {data_json},
                    backgroundColor: '{theme['chart_fill']}',
                    borderColor: '{theme['chart_border']}',
                    pointBackgroundColor: '{theme['chart_point']}',
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: '{theme['chart_border']}',
                    borderWidth: 2,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    r: {{
                        beginAtZero: true,
                        min: 0,
                        max: 10,
                        angleLines: {{ color: 'rgba(0, 0, 0, 0.05)' }},
                        grid: {{ color: 'rgba(0, 0, 0, 0.05)' }},
                        pointLabels: {{
                            font: {{ size: {label_font_size}, family: {json.dumps(theme['font_heading'])}, weight: '600' }},
                            color: '{theme['muted']}'
                        }},
                        ticks: {{ stepSize: 2, display: false }}
                    }}
                }},
                plugins: {{ legend: {{ display: false }} }}
            }}
        }});
    """


def generate_single_html_report(url: str, title: str, keyword: str, gap_analysis: GapAnalysisResult, scores: ContentScores, report: AuditReport, theme_key: str = "PG") -> bytes:
    theme = get_theme(theme_key)

    labels = [dim.dimension_name for dim in scores.dimensions]
    data_points = [dim.score for dim in scores.dimensions]
    chart_labels_json = json.dumps(labels, ensure_ascii=False)
    chart_data_json = json.dumps(data_points)

    quick_wins = [r for r in report.recommendations if r.priority.upper() in ["KRYTYCZNE", "WYSOKIE"]]

    quick_wins_html = ""
    for qw in quick_wins:
        quick_wins_html += f"""
        <div class="quick-win-card">
            <span class="badge badge-green">Akcja</span>
            <span class="qw-text">{esc(qw.title)} <span class="qw-impact">(+{esc(qw.impact_cqs)} pkt)</span></span>
        </div>
        """

    cqs_color = theme["warn"] if report.cqs_score < 80 else theme["good"]
    if report.cqs_score < 50:
        cqs_color = theme["bad"]

    ai_citability = report.ai_citability_score
    ai_color = theme["warn"] if ai_citability < 8 else theme["good"]
    if ai_citability < 5:
        ai_color = theme["bad"]

    crit_high_count = len(quick_wins)

    recommendations_html = ""
    for r in report.recommendations:
        recommendations_html += f"""
        <div class="before-after-block">
            <strong>[{esc(r.priority)}] {esc(r.title)}</strong> (Wpływ: +{esc(r.impact_cqs)} pkt)<br>
            <div class="before-text">Przed zmianą: "{esc(r.before_quote)}"</div>
            <div class="after-text">Przykładowa (nowa) treść: "{esc(r.after_generated)}"</div>
        </div>
        """

    eav_rows_html = ""
    for e in gap_analysis.eav_matrix:
        eav_rows_html += f"""
        <tr>
            <td>{esc(e.attribute)}</td>
            <td>{esc(e.urr_type)}</td>
            <td>{esc(e.coverage)}</td>
            <td>{esc(e.priority)}</td>
            <td>{esc(e.status)}</td>
        </tr>
        """

    structure_html = ""
    if getattr(report, "target_structure", None):
        for entry in report.target_structure:
            structure_html += f"""
            <div class="structure-block">
                <strong style="font-size: 16px;">{esc(entry.heading)}</strong><br>
                <span class="bluf"><strong>Przykładowy (nowy) BLUF:</strong> {esc(entry.bluf)}</span>
            </div>
            """
    else:
        structure_html = "<p style='color: var(--muted);'>Brak specyficznych rekomendacji dla nagłówków.</p>"

    eeat_miss = []
    for e in scores.eeat_signals.as_list():
        if e.missing_signals and e.missing_signals.strip() != "":
            eeat_miss.append(f"[{esc(e.dimension)}]: {esc(e.missing_signals)}")

    tf_idf = ", ".join(esc(t) for t in scores.missing_tf_idf_terms) if scores.missing_tf_idf_terms else "Brak"
    eeat_list_html = ''.join(f'<li>{e}</li>' for e in eeat_miss) if eeat_miss else '<li>Brak istotnych braków w sygnałach E-E-A-T.</li>'

    dots_div = '<div class="dots"></div>' if theme["dots_overlay"] else ""

    html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{esc(title)}</title>
    {_chartjs_inline()}
    <style>{_base_css(theme)}</style>
</head>
<body>
    {dots_div}
    {_brand_header(theme)}
    <div class="container">
        <div class="header">
            <h1>{esc(title)}</h1>
            <p><strong>URL:</strong> <a href="{esc(url)}" target="_blank">{esc(url)}</a> | <strong>Fraza:</strong> {esc(keyword)}</p>
        </div>

        {_wstep_html(theme)}

        <div class="grid-top">
            <div class="left-col">
                <div class="score-cards">
                    <div class="score-card">
                        <span class="score-title">Content Quality Score</span>
                        <div>
                            <span class="score-value" style="color: {cqs_color};">{esc(report.cqs_score)}</span><span class="score-max"> / 100</span>
                        </div>
                    </div>
                    <div class="score-card">
                        <span class="score-title">AI Citability Score</span>
                        <div>
                            <span class="score-value" style="color: {ai_color};">{esc(report.ai_citability_score)}</span><span class="score-max"> / 10</span>
                        </div>
                    </div>
                </div>

                <div class="summary-card">
                    <div class="summary-text">
                        Zidentyfikowano <strong>{crit_high_count} problemów krytycznych/ważnych.</strong><br><br>
                        <strong>Podsumowanie:</strong> {esc(report.executive_summary)}
                    </div>
                </div>
            </div>

            <div class="chart-card">
                <div class="chart-title">Profil wymiarów</div>
                <div class="canvas-container">
                    <canvas id="radarChart"></canvas>
                </div>
            </div>
        </div>

        <div class="summary-card" style="margin-bottom: 20px;">
            <div class="quick-wins-title">QUICK WINS ({crit_high_count})</div>
            {quick_wins_html}
        </div>

        <div class="details-section">
            <h2>Wszystkie Rekomendacje</h2>
            {recommendations_html}
        </div>

        <div class="details-section">
            <h2>Matrix EAV (Entity-Attribute-Value)</h2>
            <div style="overflow-x: auto;">
            <table class="eav-table">
                <thead>
                    <tr>
                        <th>Atrybut</th>
                        <th>Typ</th>
                        <th>Pokrycie</th>
                        <th>Priorytet</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {eav_rows_html}
                </tbody>
            </table>
            </div>
        </div>

        <div class="details-section">
            <h2>Docelowa Struktura Nagłówków (H1-H3) i BLUF</h2>
            {structure_html}
        </div>

        <div class="details-section">
            <h2>Sygnały E-E-A-T i Brakujące Frazy (TF-IDF)</h2>
            <div class="two-col-grid">
                <div>
                    <h4>Braki E-E-A-T</h4>
                    <!--EEAT_BLOCK:START-->
                    <ul>
                        {eeat_list_html}
                    </ul>
                    <!--EEAT_BLOCK:END-->
                </div>
                <div>
                    <h4>Brakujące powiązane frazy (TF-IDF)</h4>
                    <p>{tf_idf}</p>
                </div>
            </div>
        </div>

        {_brand_footer(theme)}
    </div>

    <script>
        {_radar_chart_js(theme, "radarChart", chart_labels_json, chart_data_json)}
    </script>
</body>
</html>
"""
    return html_content.encode("utf-8")


def generate_master_html_report(all_results: list, theme_key: str = "PG") -> bytes:
    theme = get_theme(theme_key)

    # Sort results by CQS score ascending
    sorted_results = sorted(all_results, key=lambda x: x.get("report").cqs_score if x.get("report") else 100)

    total_cqs = 0
    total_ai_cit = 0
    excellent_count = 0
    needs_improvement_count = 0
    total_articles = 0

    rows_html = ""
    chart_scripts = ""

    for item in sorted_results:
        url = item.get("url", "")
        keyword = item.get("keyword", "")
        r = item.get("report")
        s = item.get("scores")

        if not r:
            continue

        total_articles += 1
        total_cqs += r.cqs_score
        total_ai_cit += r.ai_citability_score

        if r.cqs_score >= 80:
            excellent_count += 1
        else:
            needs_improvement_count += 1

        ai_badge_color = theme["good"] if r.ai_citability_score >= 8 else theme["warn"]

        def rec_li(rec):
            return (
                f"<li><strong>[{esc(rec.title)}]</strong><br>"
                f"<span style='color:var(--muted);font-size:13px;'>Obecna treść: {esc(rec.before_quote)}<br>"
                f"Przykładowa (nowa) treść: {esc(rec.after_generated)}</span></li>"
            )

        crit = [rec_li(rec) for rec in r.recommendations if rec.priority.upper() == "KRYTYCZNE"]
        high = [rec_li(rec) for rec in r.recommendations if rec.priority.upper() == "WYSOKIE"]
        med = [rec_li(rec) for rec in r.recommendations if rec.priority.upper() == "ŚREDNIE"]

        structure = []
        if getattr(r, "target_structure", None):
            for entry in r.target_structure:
                structure.append(f"<li><strong>{esc(entry.heading)}</strong> (Przykładowy (nowy) BLUF: {esc(entry.bluf)})</li>")

        eeat_miss = []
        if s and hasattr(s, "eeat_signals"):
            for e in s.eeat_signals.as_list():
                if e.missing_signals and e.missing_signals.strip() != "":
                    eeat_miss.append(f"<li>[{esc(e.dimension)}]: {esc(e.missing_signals)}</li>")

        tf_idf = ", ".join(esc(t) for t in s.missing_tf_idf_terms) if s and getattr(s, "missing_tf_idf_terms", None) else "Brak"

        chart_labels = [d.dimension_name for d in s.dimensions] if s and getattr(s, "dimensions", None) else []
        chart_data = [d.score for d in s.dimensions] if s and getattr(s, "dimensions", None) else []
        chart_labels_json = json.dumps(chart_labels, ensure_ascii=False)
        chart_data_json = json.dumps(chart_data)

        canvas_id = f"radarChart_{total_articles}"
        chart_scripts += _radar_chart_js(theme, canvas_id, chart_labels_json, chart_data_json, label_font_size=10)

        crit_high_count = len([rec for rec in r.recommendations if rec.priority.upper() in ["KRYTYCZNE", "WYSOKIE"]])

        g = item.get("gap_analysis")
        eav_rows = ""
        if g and hasattr(g, "eav_matrix"):
            for e in g.eav_matrix:
                eav_rows += f"""
                <tr>
                    <td>{esc(e.attribute)}</td>
                    <td>{esc(e.urr_type)}</td>
                    <td>{esc(e.coverage)}</td>
                    <td>{esc(e.priority)}</td>
                    <td>{esc(e.status)}</td>
                </tr>
                """

        eav_table_html = f"""
        <div class="data-card" style="grid-column: 1 / -1; margin-top: 20px;">
            <h4>Matrix EAV:</h4>
            <div style="overflow-x: auto;">
                <table class="eav-table" style="font-size: 13px;">
                    <thead>
                        <tr>
                            <th>Atrybut</th>
                            <th>Typ</th>
                            <th>Pokrycie</th>
                            <th>Priorytet</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {eav_rows}
                    </tbody>
                </table>
            </div>
        </div>
        """

        rows_html += f"""
        <details class="url-details">
            <summary class="url-summary">
                <div class="sum-row">
                    <span class="s-url">{esc(url)}</span>
                    <span class="s-score">CQS: {esc(r.cqs_score)}/100 | AI Cit: <span style="color:{ai_badge_color}">{esc(r.ai_citability_score)}/10</span></span>
                </div>
            </summary>
            <div class="details-content">
                <p><strong>Fraza:</strong> {esc(keyword)}</p>

                <div class="grid-top" style="margin-bottom: 20px;">
                    <div class="left-col">
                        <div class="score-cards">
                            <div class="score-card">
                                <span class="score-title">CQS</span>
                                <div>
                                    <span class="score-value">{esc(r.cqs_score)}</span><span class="score-max"> / 100</span>
                                </div>
                            </div>
                            <div class="score-card">
                                <span class="score-title">AI Citability</span>
                                <div>
                                    <span class="score-value" style="color: {ai_badge_color};">{esc(r.ai_citability_score)}</span><span class="score-max"> / 10</span>
                                </div>
                            </div>
                        </div>

                        <div class="summary-card">
                            <div class="summary-text">
                                Zidentyfikowano <strong>{crit_high_count} problemów krytycznych/ważnych.</strong><br><br>
                                <strong>Podsumowanie:</strong> {esc(r.executive_summary)}
                            </div>
                        </div>
                    </div>

                    <div class="chart-card">
                        <div class="chart-title">Profil wymiarów</div>
                        <div class="canvas-container" style="height: 250px;">
                            <canvas id="{canvas_id}"></canvas>
                        </div>
                    </div>
                </div>

                <div class="card-grid">
                    <div class="data-card">
                        <h4>Rekomendacje:</h4>
                        <ul class="data-list">
                            {''.join(crit)}
                            {''.join(high)}
                            {''.join(med)}
                        </ul>
                    </div>
                    <div class="data-card">
                        <h4>Docelowa Struktura Nagłówków:</h4>
                        <ul class="data-list">
                            {''.join(structure) if structure else '<li>Brak</li>'}
                        </ul>
                    </div>
                    <div class="data-card">
                        <h4>Braki E-E-A-T:</h4>
                        <!--EEAT_BLOCK:START:{esc(url)}-->
                        <ul class="data-list">
                            {''.join(eeat_miss) if eeat_miss else '<li>Brak</li>'}
                        </ul>
                        <!--EEAT_BLOCK:END:{esc(url)}-->
                    </div>
                    <div class="data-card">
                        <h4>Brakujące Słowa (TF-IDF):</h4>
                        <p style="font-size: 14px; color: var(--muted); margin: 0;">{tf_idf}</p>
                    </div>
                    {eav_table_html}
                </div>
            </div>
        </details>
        """

    avg_cqs = round(total_cqs / total_articles, 2) if total_articles > 0 else 0
    avg_ai = round(total_ai_cit / total_articles, 2) if total_articles > 0 else 0

    dots_div = '<div class="dots"></div>' if theme["dots_overlay"] else ""

    master_css = f"""
        .summary-box {{
            background: var(--card-bg);
            padding: 30px;
            border-radius: 16px;
            box-shadow: 0 8px 30px rgba(0,0,0,0.04);
            margin-bottom: 30px;
            border: 1px solid var(--line);
        }}
        .summary-box h1 {{ margin-top: 0; font-size: 24px; font-weight: 800; color: var(--navy2); }}
        .stats {{
            display: flex;
            gap: 20px;
            margin-top: 20px;
        }}
        .stat-card {{
            background: var(--card-soft);
            border: 1px solid var(--card-soft-border);
            padding: 20px;
            border-radius: 8px;
            flex: 1;
            text-align: center;
        }}
        .stat-val {{ font-size: 32px; font-weight: bold; display: block; }}
        .url-details {{
            background: var(--card-bg);
            margin-bottom: 15px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.03);
            overflow: hidden;
            border: 1px solid var(--line);
        }}
        .url-summary {{
            padding: 20px;
            padding-left: 45px;
            cursor: pointer;
            font-weight: 500;
            list-style: none;
            position: relative;
        }}
        .url-summary::-webkit-details-marker {{ display: none; }}
        .url-summary::before {{
            content: '▶';
            position: absolute;
            left: 20px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--navy2);
            transition: transform 0.2s ease;
            font-size: 14px;
        }}
        .url-details[open] .url-summary::before {{
            transform: translateY(-50%) rotate(90deg);
        }}
        .sum-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .s-url {{
            flex-grow: 1;
            font-weight: 600;
            color: var(--text-main);
            word-break: break-all;
            padding-right: 15px;
            font-size: 13px;
        }}
        .s-score {{
            white-space: nowrap;
            color: var(--muted);
            font-size: 13px;
        }}
        .details-content {{
            padding: 0 20px 20px 20px;
            border-top: 1px solid var(--line);
            margin-top: 10px;
            padding-top: 20px;
        }}
        .card-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 20px;
        }}
        .data-card {{
            background: var(--card-soft);
            border: 1px solid var(--card-soft-border);
            border-radius: 8px;
            padding: 20px;
        }}
        .data-card h4 {{
            margin-top: 0;
            margin-bottom: 15px;
            color: var(--text-main);
            border-bottom: 1px solid var(--line);
            padding-bottom: 10px;
            font-size: 15px;
        }}
        .data-list {{
            font-size: 14px;
            margin: 0;
            padding-left: 20px;
        }}
        li {{ margin-bottom: 8px; }}
        @media (max-width: 900px) {{
            .card-grid {{ grid-template-columns: 1fr; }}
            .stats {{ flex-direction: column; }}
        }}
    """

    html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Zbiorczy Raport Audytu Masowego</title>
    {_chartjs_inline()}
    <style>
        {_base_css(theme)}
        {master_css}
    </style>
</head>
<body>
    {dots_div}
    {_brand_header(theme)}
    <div class="container" style="max-width: 1000px;">
        <div class="summary-box">
            <h1>Zbiorczy Raport Audytu (Master HTML)</h1>
            <p>Sprawdzono <strong>{total_articles}</strong> artykułów. <strong>{excellent_count}</strong> z nich ma ocenę bardzo dobrą, <strong>{needs_improvement_count}</strong> jest do poprawy.</p>
            <div class="stats">
                <div class="stat-card">
                    <span class="stat-val" style="color: var(--accent);">{total_articles}</span>
                    <span>Przeanalizowane URL</span>
                </div>
                <div class="stat-card">
                    <span class="stat-val" style="color: var(--navy2);">{avg_cqs}</span>
                    <span>Średni Wynik CQS</span>
                </div>
                <div class="stat-card">
                    <span class="stat-val" style="color: var(--good);">{avg_ai}</span>
                    <span>Średnie AI Citability</span>
                </div>
            </div>
        </div>

        {_wstep_html(theme)}

        <h2>Lista Artykułów</h2>
        {rows_html}

        {_brand_footer(theme)}
    </div>
    <script>
        {chart_scripts}
    </script>
</body>
</html>
"""
    return html_content.encode("utf-8")
