import json
import io
from utils.openai_llm import GapAnalysisResult, ContentScores, AuditReport

def generate_single_html_report(url: str, title: str, keyword: str, gap_analysis: GapAnalysisResult, scores: ContentScores, report: AuditReport) -> bytes:
    WSTEP_HTML = """
    <details class="wstep-details" style="background: white; padding: 20px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); border-left: 4px solid #003366;">
        <summary style="font-size: 18px; font-weight: 600; cursor: pointer; color: #003366;">Wstęp i definicje (Rozwiń)</summary>
        <div style="margin-top: 20px; font-size: 15px; color: #4a4a4a; line-height: 1.6;">
            <h3 style="margin-top: 0;">Wstęp do Audytu Semantycznego: Jak Google i AI "czytają" Twoje treści?</h3>
            <p>Celem tego audytu nie jest tylko sprawdzenie, czy tekst "dobrze się czyta" ludziom. Naszym głównym zadaniem jest dostosowanie treści do sposobu, w jaki analizują ją <strong>algorytmy Google oraz nowoczesne modele AI</strong> (takie jak ChatGPT czy Google AI Overviews).</p>
            <p>Audyt składa się z <strong>3 głównych filarów</strong>, które sprawdzają treść pod kątem co najmniej 12 kluczowych kryteriów:</p>
            <ol>
            <li><strong>Zgodność z Central Search Intent (CSI)</strong> – czy algorytm rozumie, o czym dokładnie piszesz i dla kogo?</li>
            <li><strong>Jakość treści</strong> – jak kosztowna i trudna w interpretacji jest Twoja strona dla robota?</li>
            <li><strong>Ocena E-E-A-T</strong> – czy Google uważa Cię za wiarygodnego eksperta?</li>
            </ol>
            
            <hr style="border: 0; border-top: 1px solid #ebeef5; margin: 20px 0;">
            
            <h4 style="color: #006699;">1. Zgodność z Central Search Intent (CSI)</h4>
            <p><em>(Analiza: EAV GAP + BLUF + Chunk + URR)</em><br>
            Tutaj sprawdzamy, czy Twój artykuł odpowiada na intencję użytkownika i czy jest zbudowany tak, aby maszyna mogła bezbłędnie zidentyfikować temat przewodni.</p>
            <ul>
            <li><strong>Central Search Intent (CSI):</strong> To matematyczne połączenie tematu (Encji) z kontekstem źródła. Algorytm musi wiedzieć, z jakiej perspektywy opisujesz temat.</li>
            <li><strong>Entity-Attribute-Value (EAV):</strong> Google dąży do wyekstrahowania z tekstu "suchych faktów" i zapisania ich w tabeli (Grafie Wiedzy). Sprawdzimy, czy Twój tekst to "lita ściana tekstu", czy ustrukturyzowana baza wiedzy.</li>
            <li><strong>BLUF (Bottom Line Up Front):</strong> Najważniejsza informacja musi znaleźć się na początku. Google i AI często skanują tylko początek sekcji.</li>
            <li><strong>CHUNK (Fragmentacja pod RAG):</strong> Każda sekcja pod nagłówkiem H2 powinna być samodzielną, wyczerpującą odpowiedzią na dany problem.</li>
            <li><strong>URR (Unique, Root, Rare):</strong> Aby content był uznany za wybitny, musisz ułożyć atrybuty encji w odpowiedniej hierarchii (definiujące, wyróżniające, niszowe).</li>
            </ul>

            <hr style="border: 0; border-top: 1px solid #ebeef5; margin: 20px 0;">

            <h4 style="color: #006699;">2. Jakość treści</h4>
            <p><em>(Analiza: CoR + Information Density + SRL + TF-IDF)</em><br>
            W tej sekcji mierzymy efektywność Twojego tekstu. Czy dostarczasz wiedzę szybko i konkretnie, czy zmuszasz Google do "marnowania prądu"?</p>
            <ul>
            <li><strong>CoR (Cost of Retrieval):</strong> Wydatek obliczeniowy, jaki wyszukiwarka ponosi na przeczytanie Twojej strony. Google wybierze konkurencję, która dostarczy tę samą wiedzę "taniej".</li>
            <li><strong>Information Density (Gęstość Informacji):</strong> Stosunek konkretnych faktów do "puchu" (fluff). Im więcej faktów i konkretów, tym wyższa ocena.</li>
            <li><strong>SRL (Semantic Role Labeling):</strong> To gramatyka dla robotów. Wskazanie: Kto? Co robi? Komu? Należy usuwać stronę bierną, aby Twoja Encja była "Bohaterem" zdania.</li>
            <li><strong>TF-IDF (Trafność terminologiczna):</strong> Ocena używania specjalistycznego i rzadkiego słownictwa (IDF), które daje silny sygnał bycia ekspertem.</li>
            </ul>

            <hr style="border: 0; border-top: 1px solid #ebeef5; margin: 20px 0;">

            <h4 style="color: #006699;">3. Ocena E-E-A-T</h4>
            <p><em>(Experience, Expertise, Authoritativeness, Trustworthiness)</em><br>
            System, którym Google ocenia wiarygodność Twoją i Twojej strony (krytyczne dla branż YMYL).</p>
            <ul>
            <li><strong>Experience:</strong> Czy widać dowody używania produktu/przeżycia doświadczenia (własne zdjęcia, opis odczuć)?</li>
            <li><strong>Expertise:</strong> Czy autor ma wiedzę formalną?</li>
            <li><strong>Authoritativeness:</strong> Czy inni eksperci cytują tę stronę?</li>
            <li><strong>Trust:</strong> Czy strona jest bezpieczna i prawdziwa?</li>
            </ul>
        </div>
    </details>
    """
    labels = []
    data_points = []
    
    for dim in scores.dimensions:
        labels.append(dim.dimension_name)
        data_points.append(dim.score)
        
    chart_data_json = json.dumps(data_points)
    chart_labels_json = json.dumps(labels)
    
    quick_wins = [r for r in report.recommendations if r.priority.upper() in ["KRYTYCZNE", "WYSOKIE"]]
    
    quick_wins_html = ""
    for qw in quick_wins:
        quick_wins_html += f"""
        <div class="quick-win-card">
            <span class="badge badge-green">Akcja</span>
            <span class="qw-text">{qw.title} <span style="color:#7f8c8d; font-size: 12px;">(+{qw.impact_cqs} pkt)</span></span>
        </div>
        """
        
    cqs_badge = "UWAGA" if report.cqs_score < 80 else "ŚWIETNIE"
    cqs_color = "#e6a23c" if report.cqs_score < 80 else "#67c23a"
    if report.cqs_score < 50:
        cqs_color = "#f56c6c"
    
    ai_citability = report.ai_citability_score
    ai_badge = "UWAGA" if ai_citability < 8 else "ŚWIETNIE"
    ai_color = "#e6a23c" if ai_citability < 8 else "#67c23a"
    if ai_citability < 5:
        ai_color = "#f56c6c"
    
    crit_high_count = len(quick_wins)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');
            
            :root {{
                --bg-color: #f4f6f9;
                --card-bg: #ffffff;
                --text-main: #0A2540;
                --text-muted: #5B6B80;
                --accent-orange: #F2994A;
                --accent-green: #27AE60;
                --card-beige: #F8F9FA;
                --border-color: #E2E8F0;
                --primary-blue: #006699;
            }}
            body {{
                font-family: 'Manrope', sans-serif;
                background-color: var(--bg-color);
                color: var(--text-main);
                margin: 0;
                padding: 40px 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
            }}
            .header {{
                margin-bottom: 30px;
            }}
            .header h1 {{
                margin: 0 0 10px 0;
                font-size: 26px;
                color: #1a1a1a;
            }}
            .header p {{
                margin: 0;
                color: var(--text-muted);
                font-size: 15px;
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
                background-color: var(--card-beige);
                border: 1px solid #f2eed8;
                border-radius: 12px;
                padding: 20px 25px;
                position: relative;
                box-shadow: 0 2px 10px rgba(0,0,0,0.02);
            }}
            .score-title {{
                color: var(--text-muted);
                font-size: 14px;
                font-weight: 500;
                margin-bottom: 15px;
                display: block;
            }}
            .score-value {{
                font-size: 48px;
                font-weight: 700;
                color: {cqs_color};
            }}
            .score-max {{
                font-size: 20px;
                color: var(--text-muted);
                font-weight: 500;
            }}
            .badge-top-right {{
                position: absolute;
                top: 20px;
                right: 20px;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.5px;
                text-transform: uppercase;
            }}
            .summary-card {{
                background-color: var(--card-bg);
                border-radius: 12px;
                padding: 30px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.03);
            }}
            .summary-text {{
                font-size: 16px;
                line-height: 1.6;
                margin-bottom: 25px;
            }}
            .summary-text strong {{
                color: #f56c6c;
                font-weight: 600;
            }}
            .quick-wins-title {{
                font-size: 13px;
                font-weight: 700;
                color: var(--text-muted);
                text-transform: uppercase;
                margin-bottom: 15px;
                letter-spacing: 0.5px;
            }}
            .quick-win-card {{
                display: flex;
                align-items: center;
                padding: 14px 18px;
                border: 1px solid var(--border-color);
                border-radius: 8px;
                margin-bottom: 10px;
                background-color: #fafbfc;
                transition: background-color 0.2s;
            }}
            .quick-win-card:hover {{
                background-color: #f0f4f8;
            }}
            .badge {{
                font-size: 11px;
                padding: 5px 10px;
                border-radius: 6px;
                margin-right: 15px;
                font-weight: 600;
            }}
            .badge-green {{
                background-color: #eaf5e9;
                color: #2e7d32;
                border: 1px solid #c8e6c9;
            }}
            .qw-text {{
                font-size: 14px;
                color: var(--text-main);
                font-weight: 500;
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
                border: 1px solid var(--border-color);
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
            }}
            .details-section h2 {{
                font-size: 20px;
                margin-top: 0;
                margin-bottom: 20px;
                border-bottom: 1px solid var(--border-color);
                padding-bottom: 15px;
            }}
            .before-after-block {{
                background: #fafbfc;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                font-size: 14px;
                border-left: 4px solid var(--accent-orange);
            }}
            .after-text {{
                color: #2e7d32;
                margin-top: 15px;
                font-weight: 600;
                padding-top: 15px;
                border-top: 1px dashed #e0e0e0;
            }}
            @media (max-width: 900px) {{
                .grid-top {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{title}</h1>
                <p><strong>URL:</strong> <a href="{url}" target="_blank" style="color: #409eff; text-decoration: none;">{url}</a> | <strong>Fraza:</strong> {keyword}</p>
            </div>
            
            {WSTEP_HTML}
            
            <div class="grid-top">
                <div class="left-col">
                    <div class="score-cards">
                        <div class="score-card">
                            <span class="score-title">Content Quality Score</span>
                            <div>
                                <span class="score-value">{report.cqs_score}</span><span class="score-max"> / 100</span>
                            </div>
                        </div>
                        <div class="score-card">
                            <span class="score-title">AI Citability Score</span>
                            <div>
                                <span class="score-value" style="color: {ai_color};">{report.ai_citability_score}</span><span class="score-max"> / 10</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="summary-card">
                        <div class="summary-text">
                            Zidentyfikowano <strong>{crit_high_count} problemów krytycznych/ważnych.</strong><br><br>
                            <em>Profil audytu: Audyt Semantyczny - wagi i kryteria dostosowane do typu treści.</em><br><br>
                            <strong>Podsumowanie Executive:</strong> {report.executive_summary}
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
    """
    
    for r in report.recommendations:
        html_content += f"""
        <div class="before-after-block">
            <strong>[{r.priority}] {r.title}</strong> (Wpływ: +{r.impact_cqs} pkt)<br>
            <div style="margin-top: 10px; color: #666; font-style: italic;">Przed zmianą: "{r.before_quote}"</div>
            <div class="after-text">Rekomendowana treść: "{r.after_generated}"</div>
        </div>
        """
        
    html_content += "</div>"
    
    # EAV Matrix HTML
    html_content += """
    <div class="details-section">
        <h2>Matrix EAV (Entity-Attribute-Value)</h2>
        <div style="overflow-x: auto;">
        <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px;">
            <thead>
                <tr style="background-color: #f8f9fa; border-bottom: 2px solid #ebeef5;">
                    <th style="padding: 10px; text-align: left;">Atrybut</th>
                    <th style="padding: 10px; text-align: left;">Typ</th>
                    <th style="padding: 10px; text-align: left;">Pokrycie</th>
                    <th style="padding: 10px; text-align: left;">Priorytet</th>
                    <th style="padding: 10px; text-align: left;">Status</th>
                </tr>
            </thead>
            <tbody>
    """
    for e in gap_analysis.eav_matrix:
        html_content += f"""
        <tr style="border-bottom: 1px solid #ebeef5;">
            <td style="padding: 10px;">{e.attribute}</td>
            <td style="padding: 10px;">{e.urr_type}</td>
            <td style="padding: 10px;">{e.coverage}</td>
            <td style="padding: 10px;">{e.priority}</td>
            <td style="padding: 10px;">{e.status}</td>
        </tr>
        """
    html_content += """
            </tbody>
        </table>
        </div>
    </div>
    """

    # Target H2 Structure HTML
    html_content += """
    <div class="details-section">
        <h2>Rekomendowana Struktura Nagłówków (H2) i BLUF</h2>
    """
    if report.target_structure_h2:
        h2s = report.target_structure_h2
        blufs = report.bluf_per_h2 if report.bluf_per_h2 else []
        for i in range(max(len(h2s), len(blufs))):
            h2 = h2s[i] if i < len(h2s) else ""
            bluf = blufs[i] if i < len(blufs) else ""
            html_content += f"""
            <div style="margin-bottom: 15px; padding: 15px; background: #fafbfc; border-left: 4px solid #409eff; border-radius: 4px;">
                <strong style="font-size: 16px;">{h2}</strong><br>
                <span style="color: #666; font-size: 14px; display: inline-block; margin-top: 5px;"><strong>BLUF:</strong> {bluf}</span>
            </div>
            """
    else:
        html_content += "<p style='color: #666;'>Brak specyficznych rekomendacji H2.</p>"
    html_content += "</div>"

    # EEAT and TF-IDF HTML
    eeat_miss = []
    for e in scores.eeat_signals:
        if e.missing_signals and e.missing_signals.strip() != "":
            eeat_miss.append(f"[{e.dimension}]: {e.missing_signals}")
            
    tf_idf = ", ".join(scores.missing_tf_idf_terms) if hasattr(scores, 'missing_tf_idf_terms') and scores.missing_tf_idf_terms else "Brak"
    
    html_content += f"""
    <div class="details-section">
        <h2>Sygnały E-E-A-T i Brakujące Frazy (TF-IDF)</h2>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div>
                <h4 style="margin-top: 0; color: #2c3e50;">Braki E-E-A-T</h4>
                <ul style="padding-left: 20px; color: #666; font-size: 14px;">
                    {''.join([f'<li>{e}</li>' for e in eeat_miss]) if eeat_miss else '<li>Brak istotnych braków w sygnałach E-E-A-T.</li>'}
                </ul>
            </div>
            <div>
                <h4 style="margin-top: 0; color: #2c3e50;">Brakujące powiązane frazy (TF-IDF)</h4>
                <p style="color: #666; font-size: 14px; line-height: 1.6;">{tf_idf}</p>
            </div>
        </div>
    </div>
    """

    html_content += f"""
        </div>

        <script>
            const ctx = document.getElementById('radarChart').getContext('2d');
            new Chart(ctx, {{
                type: 'radar',
                data: {{
                    labels: {chart_labels_json},
                    datasets: [{{
                        label: 'Wynik Wymiaru',
                        data: {chart_data_json},
                        backgroundColor: 'rgba(26, 147, 140, 0.2)',
                        borderColor: 'rgba(26, 147, 140, 0.8)',
                        pointBackgroundColor: 'rgba(26, 147, 140, 1)',
                        pointBorderColor: '#fff',
                        pointHoverBackgroundColor: '#fff',
                        pointHoverBorderColor: 'rgba(26, 147, 140, 1)',
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
                                font: {{ size: 12, family: "'Manrope', sans-serif", weight: '600' }},
                                color: '#5B6B80'
                            }},
                            ticks: {{
                                stepSize: 2,
                                display: false
                            }}
                        }}
                    }},
                    plugins: {{
                        legend: {{ display: false }}
                    }}
                }}
            }});
        </script>
    </body>
    </html>
    """
    return html_content.encode("utf-8")


def generate_master_html_report(all_results: list) -> bytes:
    WSTEP_HTML = """
    <details class="wstep-details" style="background: white; padding: 20px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); border-left: 4px solid #003366;">
        <summary style="font-size: 18px; font-weight: 600; cursor: pointer; color: #003366;">Wstęp i definicje (Rozwiń)</summary>
        <div style="margin-top: 20px; font-size: 15px; color: #4a4a4a; line-height: 1.6;">
            <h3 style="margin-top: 0;">Wstęp do Audytu Semantycznego: Jak Google i AI "czytają" Twoje treści?</h3>
            <p>Celem tego audytu nie jest tylko sprawdzenie, czy tekst "dobrze się czyta" ludziom. Naszym głównym zadaniem jest dostosowanie treści do sposobu, w jaki analizują ją <strong>algorytmy Google oraz nowoczesne modele AI</strong> (takie jak ChatGPT czy Google AI Overviews).</p>
            <p>Audyt składa się z <strong>3 głównych filarów</strong>, które sprawdzają treść pod kątem co najmniej 12 kluczowych kryteriów:</p>
            <ol>
            <li><strong>Zgodność z Central Search Intent (CSI)</strong> – czy algorytm rozumie, o czym dokładnie piszesz i dla kogo?</li>
            <li><strong>Jakość treści</strong> – jak kosztowna i trudna w interpretacji jest Twoja strona dla robota?</li>
            <li><strong>Ocena E-E-A-T</strong> – czy Google uważa Cię za wiarygodnego eksperta?</li>
            </ol>
            
            <hr style="border: 0; border-top: 1px solid #ebeef5; margin: 20px 0;">
            
            <h4 style="color: #006699;">1. Zgodność z Central Search Intent (CSI)</h4>
            <p><em>(Analiza: EAV GAP + BLUF + Chunk + URR)</em><br>
            Tutaj sprawdzamy, czy Twój artykuł odpowiada na intencję użytkownika i czy jest zbudowany tak, aby maszyna mogła bezbłędnie zidentyfikować temat przewodni.</p>
            <ul>
            <li><strong>Central Search Intent (CSI):</strong> To matematyczne połączenie tematu (Encji) z kontekstem źródła. Algorytm musi wiedzieć, z jakiej perspektywy opisujesz temat.</li>
            <li><strong>Entity-Attribute-Value (EAV):</strong> Google dąży do wyekstrahowania z tekstu "suchych faktów" i zapisania ich w tabeli (Grafie Wiedzy). Sprawdzimy, czy Twój tekst to "lita ściana tekstu", czy ustrukturyzowana baza wiedzy.</li>
            <li><strong>BLUF (Bottom Line Up Front):</strong> Najważniejsza informacja musi znaleźć się na początku. Google i AI często skanują tylko początek sekcji.</li>
            <li><strong>CHUNK (Fragmentacja pod RAG):</strong> Każda sekcja pod nagłówkiem H2 powinna być samodzielną, wyczerpującą odpowiedzią na dany problem.</li>
            <li><strong>URR (Unique, Root, Rare):</strong> Aby content był uznany za wybitny, musisz ułożyć atrybuty encji w odpowiedniej hierarchii (definiujące, wyróżniające, niszowe).</li>
            </ul>

            <hr style="border: 0; border-top: 1px solid #ebeef5; margin: 20px 0;">

            <h4 style="color: #006699;">2. Jakość treści</h4>
            <p><em>(Analiza: CoR + Information Density + SRL + TF-IDF)</em><br>
            W tej sekcji mierzymy efektywność Twojego tekstu. Czy dostarczasz wiedzę szybko i konkretnie, czy zmuszasz Google do "marnowania prądu"?</p>
            <ul>
            <li><strong>CoR (Cost of Retrieval):</strong> Wydatek obliczeniowy, jaki wyszukiwarka ponosi na przeczytanie Twojej strony. Google wybierze konkurencję, która dostarczy tę samą wiedzę "taniej".</li>
            <li><strong>Information Density (Gęstość Informacji):</strong> Stosunek konkretnych faktów do "puchu" (fluff). Im więcej faktów i konkretów, tym wyższa ocena.</li>
            <li><strong>SRL (Semantic Role Labeling):</strong> To gramatyka dla robotów. Wskazanie: Kto? Co robi? Komu? Należy usuwać stronę bierną, aby Twoja Encja była "Bohaterem" zdania.</li>
            <li><strong>TF-IDF (Trafność terminologiczna):</strong> Ocena używania specjalistycznego i rzadkiego słownictwa (IDF), które daje silny sygnał bycia ekspertem.</li>
            </ul>

            <hr style="border: 0; border-top: 1px solid #ebeef5; margin: 20px 0;">

            <h4 style="color: #006699;">3. Ocena E-E-A-T</h4>
            <p><em>(Experience, Expertise, Authoritativeness, Trustworthiness)</em><br>
            System, którym Google ocenia wiarygodność Twoją i Twojej strony (krytyczne dla branż YMYL).</p>
            <ul>
            <li><strong>Experience:</strong> Czy widać dowody używania produktu/przeżycia doświadczenia (własne zdjęcia, opis odczuć)?</li>
            <li><strong>Expertise:</strong> Czy autor ma wiedzę formalną?</li>
            <li><strong>Authoritativeness:</strong> Czy inni eksperci cytują tę stronę?</li>
            <li><strong>Trust:</strong> Czy strona jest bezpieczna i prawdziwa?</li>
            </ul>
        </div>
    </details>
    """

    total_cqs = 0
    total_ai_cit = 0
    excellent_count = 0
    needs_improvement_count = 0
    total_articles = 0
    
    rows_html = ""
    
    for item in all_results:
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
            
        ai_badge_color = "#67c23a" if r.ai_citability_score >= 8 else "#e6a23c"
        
        crit = [f"<li><strong>[{rec.title}]</strong><br><span style='color:#666;font-size:13px;'>Przed: {rec.before_quote}<br>Po: {rec.after_generated}</span></li>" for rec in r.recommendations if rec.priority.upper() == "KRYTYCZNE"]
        high = [f"<li><strong>[{rec.title}]</strong><br><span style='color:#666;font-size:13px;'>Przed: {rec.before_quote}<br>Po: {rec.after_generated}</span></li>" for rec in r.recommendations if rec.priority.upper() == "WYSOKIE"]
        med  = [f"<li><strong>[{rec.title}]</strong><br><span style='color:#666;font-size:13px;'>Przed: {rec.before_quote}<br>Po: {rec.after_generated}</span></li>" for rec in r.recommendations if rec.priority.upper() == "ŚREDNIE"]
        
        h2s = r.target_structure_h2 if r.target_structure_h2 else []
        blufs = r.bluf_per_h2 if r.bluf_per_h2 else []
        structure = []
        for i in range(max(len(h2s), len(blufs))):
            h2 = h2s[i] if i < len(h2s) else ""
            bluf = blufs[i] if i < len(blufs) else ""
            structure.append(f"<li><strong>{h2}</strong> (BLUF: {bluf})</li>")
            
        eeat_miss = []
        if s and hasattr(s, "eeat_signals"):
            for e in s.eeat_signals:
                if e.missing_signals and e.missing_signals.strip() != "":
                    eeat_miss.append(f"<li>[{e.dimension}]: {e.missing_signals}</li>")
                    
        tf_idf = ", ".join(s.missing_tf_idf_terms) if s and hasattr(s, 'missing_tf_idf_terms') and s.missing_tf_idf_terms else "Brak"
        
        rows_html += f"""
        <details class="url-details">
            <summary class="url-summary">
                <div class="sum-row">
                    <span class="s-url">{url}</span>
                    <span class="s-score">CQS: {r.cqs_score}/100 | AI Cit: <span style="color:{ai_badge_color}">{r.ai_citability_score}/10</span></span>
                </div>
            </summary>
            <div class="details-content">
                <p><strong>Fraza:</strong> {keyword}</p>
                <p><strong>Executive Summary:</strong> {r.executive_summary}</p>
                
                <div class="card-grid">
                    <div class="data-card">
                        <h4>Rekomendacje:</h4>
                        <ul class="data-list">
                            {''.join(crit) if crit else ''}
                            {''.join(high) if high else ''}
                            {''.join(med) if med else ''}
                            {'' if not (crit or high or med) else ''}
                        </ul>
                    </div>
                    <div class="data-card">
                        <h4>Docelowa Struktura H2:</h4>
                        <ul class="data-list">
                            {''.join(structure) if structure else '<li>Brak</li>'}
                        </ul>
                    </div>
                    <div class="data-card">
                        <h4>Braki E-E-A-T:</h4>
                        <ul class="data-list">
                            {''.join(eeat_miss) if eeat_miss else '<li>Brak</li>'}
                        </ul>
                    </div>
                    <div class="data-card">
                        <h4>Brakujące Słowa (TF-IDF):</h4>
                        <p style="font-size: 14px; color: #666; margin: 0;">{tf_idf}</p>
                    </div>
                </div>
            </div>
        </details>
        """
        
    avg_cqs = round(total_cqs / total_articles, 2) if total_articles > 0 else 0
    avg_ai = round(total_ai_cit / total_articles, 2) if total_articles > 0 else 0
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pl">
    <head>
        <meta charset="UTF-8">
        <title>Zbiorczy Raport Audytu Masowego</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');
            body {{
                font-family: 'Manrope', sans-serif;
                background-color: #f4f6f9;
                color: #0A2540;
                padding: 40px 20px;
                margin: 0;
            }}
            .container {{
                max-width: 1000px;
                margin: 0 auto;
            }}
            .summary-box {{
                background: white;
                padding: 30px;
                border-radius: 16px;
                box-shadow: 0 8px 30px rgba(0,0,0,0.04);
                margin-bottom: 30px;
                border: 1px solid #E2E8F0;
            }}
            .summary-box h1 {{ margin-top: 0; font-size: 24px; font-weight: 800; color: #006699; }}
            .stats {{
                display: flex;
                gap: 20px;
                margin-top: 20px;
            }}
            .stat-card {{
                background: #fdfaf3;
                border: 1px solid #f2eed8;
                padding: 20px;
                border-radius: 8px;
                flex: 1;
                text-align: center;
            }}
            .stat-val {{ font-size: 32px; font-weight: bold; color: #e6a23c; display: block; }}
            .url-details {{
                background: white;
                margin-bottom: 15px;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.03);
                overflow: hidden;
                border: 1px solid #E2E8F0;
            }}
            .url-summary {{
                padding: 20px;
                cursor: pointer;
                font-weight: 500;
                list-style: none;
                position: relative;
                padding-right: 40px;
            }}
            .url-summary::-webkit-details-marker {{ display: none; }}
            .url-summary::after {{
                content: '▼';
                position: absolute;
                right: 20px;
                top: 50%;
                transform: translateY(-50%);
                color: #409eff;
                transition: transform 0.2s ease;
                font-size: 12px;
            }}
            .url-details[open] .url-summary::after {{
                transform: translateY(-50%) rotate(180deg);
            }}
            .sum-row {{
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .s-url {{ color: #409eff; word-break: break-all; margin-right: 20px; }}
            .details-content {{
                padding: 0 20px 20px 20px;
                border-top: 1px solid #eee;
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
                background: #fdfaf3;
                border: 1px solid #f2eed8;
                border-radius: 8px;
                padding: 20px;
            }}
            .data-card h4 {{
                margin-top: 0;
                margin-bottom: 15px;
                color: #2c3e50;
                border-bottom: 1px solid #e5eaef;
                padding-bottom: 10px;
                font-size: 15px;
            }}
            .data-list {{
                font-size: 14px;
                margin: 0;
                padding-left: 20px;
            }}
            li {{ margin-bottom: 8px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="summary-box">
                <h1>Zbiorczy Raport Audytu (Master HTML)</h1>
                <p>Sprawdzono <strong>{total_articles}</strong> artykułów. <strong>{excellent_count}</strong> z nich ma ocenę bardzo dobrą, <strong>{needs_improvement_count}</strong> jest do poprawy.</p>
                <div class="stats">
                    <div class="stat-card">
                        <span class="stat-val">{total_articles}</span>
                        <span>Przeanalizowane URL</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-val" style="color: #409eff;">{avg_cqs}</span>
                        <span>Średni Wynik CQS</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-val" style="color: #67c23a;">{avg_ai}</span>
                        <span>Średnie AI Citability</span>
                    </div>
                </div>
            </div>
            
            {WSTEP_HTML}
            
            <h2>Lista Artykułów</h2>
            {rows_html}
        </div>
    </body>
    </html>
    """
    return html_content.encode("utf-8")
