import json
import io
from utils.openai_llm import GapAnalysisResult, ContentScores, AuditReport

def generate_single_html_report(url: str, keyword: str, gap_analysis: GapAnalysisResult, scores: ContentScores, report: AuditReport) -> bytes:
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
        <title>Audyt SEO AI - {url}</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            
            :root {{
                --bg-color: #f7f9fc;
                --card-bg: #ffffff;
                --text-main: #2c3e50;
                --text-muted: #7f8c8d;
                --accent-orange: #e6a23c;
                --accent-green: #67c23a;
                --card-beige: #fdfaf3;
                --border-color: #ebeef5;
            }}
            body {{
                font-family: 'Inter', sans-serif;
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
                border-radius: 12px;
                padding: 30px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.03);
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
            }}
            .chart-title {{
                width: 100%;
                font-size: 16px;
                font-weight: 700;
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
                <h1>Raport Audytu AI</h1>
                <p><strong>URL:</strong> <a href="{url}" target="_blank" style="color: #409eff; text-decoration: none;">{url}</a> | <strong>Fraza:</strong> {keyword}</p>
            </div>
            
            <div class="grid-top">
                <div class="left-col">
                    <div class="score-cards">
                        <div class="score-card">
                            <span class="badge-top-right" style="color: {cqs_color}; border-color: {cqs_color}; background: #fff;">{cqs_badge}</span>
                            <span class="score-title">Content Quality Score ℹ️</span>
                            <div>
                                <span class="score-value">{report.cqs_score}</span><span class="score-max"> / 100</span>
                            </div>
                        </div>
                        <div class="score-card">
                            <span class="badge-top-right" style="color: {ai_color}; border-color: {ai_color}; background: #fff;">{ai_badge}</span>
                            <span class="score-title">AI Citability Score ℹ️</span>
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
                        
                        <div class="quick-wins-title">QUICK WINS ({crit_high_count})</div>
                        {quick_wins_html}
                    </div>
                </div>
                
                <div class="chart-card">
                    <div class="chart-title">Profil wymiarów ℹ️</div>
                    <div class="canvas-container">
                        <canvas id="radarChart"></canvas>
                    </div>
                </div>
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
        
    html_content += f"""
            </div>
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
                            angleLines: {{ color: 'rgba(0, 0, 0, 0.05)' }},
                            grid: {{ color: 'rgba(0, 0, 0, 0.05)' }},
                            pointLabels: {{
                                font: {{ size: 12, family: "'Inter', sans-serif" }},
                                color: '#7f8c8d'
                            }},
                            ticks: {{
                                min: 0,
                                max: 10,
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
    total_cqs = 0
    excellent_count = 0
    needs_improvement_count = 0
    total_articles = 0
    
    rows_html = ""
    
    for item in all_results:
        url = item.get("url", "")
        keyword = item.get("keyword", "")
        r = item.get("report")
        
        if not r:
            continue
            
        total_articles += 1
        total_cqs += r.cqs_score
        
        if r.cqs_score >= 80:
            excellent_count += 1
            badge = "<span style='color: #67c23a; font-weight: bold;'>Świetnie</span>"
        else:
            needs_improvement_count += 1
            badge = "<span style='color: #e6a23c; font-weight: bold;'>Uwaga</span>"
            
        rows_html += f"""
        <details class="url-details">
            <summary class="url-summary">
                <div class="sum-row">
                    <span class="s-url">{url}</span>
                    <span class="s-score">CQS: {r.cqs_score}/100 ({badge})</span>
                </div>
            </summary>
            <div class="details-content">
                <p><strong>Fraza:</strong> {keyword}</p>
                <p><strong>Executive Summary:</strong> {r.executive_summary}</p>
                <h4>Rekomendacje (Quick Wins):</h4>
                <ul>
        """
        for rec in r.recommendations:
            if rec.priority.upper() in ["KRYTYCZNE", "WYSOKIE"]:
                rows_html += f"<li><strong>{rec.priority}:</strong> {rec.title} (+{rec.impact_cqs})</li>"
        
        rows_html += """
                </ul>
            </div>
        </details>
        """
        
    avg_cqs = round(total_cqs / total_articles, 2) if total_articles > 0 else 0
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pl">
    <head>
        <meta charset="UTF-8">
        <title>Zbiorczy Raport Audytu Masowego</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            body {{
                font-family: 'Inter', sans-serif;
                background-color: #f7f9fc;
                color: #2c3e50;
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
                border-radius: 12px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.03);
                margin-bottom: 30px;
            }}
            .summary-box h1 {{ margin-top: 0; font-size: 24px; }}
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
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.02);
                overflow: hidden;
            }}
            .url-summary {{
                padding: 20px;
                cursor: pointer;
                font-weight: 500;
                list-style: none;
            }}
            .url-summary::-webkit-details-marker {{ display: none; }}
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
                </div>
            </div>
            
            <h2>Lista Artykułów</h2>
            {rows_html}
        </div>
    </body>
    </html>
    """
    return html_content.encode("utf-8")
