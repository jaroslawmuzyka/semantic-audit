import pandas as pd
import io
import zipfile
from utils.openai_llm import GapAnalysisResult, ContentScores, AuditReport

def generate_excel_report(gap_analysis: GapAnalysisResult, scores: ContentScores, report: AuditReport, source_content: str, consolidated_competitors: str) -> bytes:
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Sheet 1: Executive Summary
        summary_data = {
            "Metric": ["CQS Score", "AI Citability Score", "Executive Summary"],
            "Value": [report.cqs_score, report.ai_citability_score, report.executive_summary]
        }
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name="Summary & CQS", index=False)
        
        # Sheet 2: Recommendations
        recs_data = []
        for r in report.recommendations:
            recs_data.append({
                "Priority": r.priority,
                "Title": r.title,
                "Context": r.context,
                "BEFORE": r.before_quote,
                "AFTER": r.after_generated,
                "Impact on CQS": f"+{r.impact_cqs}"
            })
        df_recs = pd.DataFrame(recs_data)
        df_recs.to_excel(writer, sheet_name="Recommendations", index=False)
        
        # Sheet 3: Competitor EAV Matrix
        eav_data = []
        for e in gap_analysis.eav_matrix:
            row = {
                "Attribute": e.attribute,
                "URR Type": e.urr_type,
                "Coverage": e.coverage,
                "Priority": e.priority,
                "Status": e.status
            }
            # Add K1-K10 columns
            for i in range(10):
                col_name = f"K{i+1}"
                if i < len(e.competitors_presence):
                    row[col_name] = "+" if e.competitors_presence[i] else "-"
                else:
                    row[col_name] = "Brak danych"
            eav_data.append(row)
            
        df_eav = pd.DataFrame(eav_data)
        df_eav.to_excel(writer, sheet_name="Competitor EAV Matrix", index=False)
        
        # Sheet 4: Scores
        scores_data = []
        for s in scores.dimensions:
            scores_data.append({
                "Dimension": s.dimension_name,
                "Score (0-10)": s.score,
                "Top Problem": s.top_problem,
                "Problematic Quote": s.before_quote
            })
        df_scores = pd.DataFrame(scores_data)
        df_scores.to_excel(writer, sheet_name="Dimension Scores", index=False)
        
        # Sheet 5: EEAT Signals
        eeat_data = []
        for e in scores.eeat_signals:
            eeat_data.append({
                "Dimension": e.dimension,
                "Score": e.score,
                "Present Signals": e.present_signals,
                "Missing Signals": e.missing_signals
            })
        df_eeat = pd.DataFrame(eeat_data)
        df_eeat.to_excel(writer, sheet_name="EEAT Analysis", index=False)
        
        # Sheet 6: Action Plan
        action_plan_data = {
            "Target H2 Structure": report.target_structure_h2,
            "Suggested BLUF (First Sentence)": report.bluf_per_h2 + [""] * (len(report.target_structure_h2) - len(report.bluf_per_h2)) 
        }
        # Pad with empty strings if lengths don't match
        max_len = max(len(report.target_structure_h2), len(report.bluf_per_h2))
        action_plan_data["Target H2 Structure"].extend([""] * (max_len - len(action_plan_data["Target H2 Structure"])))
        action_plan_data["Suggested BLUF (First Sentence)"].extend([""] * (max_len - len(action_plan_data["Suggested BLUF (First Sentence)"])))
        
        df_action = pd.DataFrame(action_plan_data)
        df_action.to_excel(writer, sheet_name="Action Plan", index=False)
        
        # Sheet 7: Missing TF-IDF
        tfidf_data = {"Missing Terms": scores.missing_tf_idf_terms}
        df_tfidf = pd.DataFrame(tfidf_data)
        df_tfidf.to_excel(writer, sheet_name="Missing TF-IDF", index=False)
        
        # Sheet 8: Raw Source Content
        df_source = pd.DataFrame({"Source Article Content": [source_content]})
        df_source.to_excel(writer, sheet_name="Raw Source Content", index=False)
        
        # Sheet 9: Raw Competitors Content
        df_comps = pd.DataFrame({"Consolidated Competitors Content": [consolidated_competitors]})
        df_comps.to_excel(writer, sheet_name="Raw Competitors Content", index=False)
        
    output.seek(0)
    return output.getvalue()

def generate_master_excel_report(all_results: list) -> bytes:
    full_data = []
    short_data = []
    action_data = []
    eav_data = []
    
    total_cqs = 0
    excellent_count = 0
    needs_improvement_count = 0
    total_articles = 0
    total_cost = 0.0
    total_tokens_in = 0
    total_tokens_out = 0
    
    for item in all_results:
        url = item.get("url", "")
        keyword = item.get("keyword", "")
        r = item.get("report")
        s = item.get("scores")
        g = item.get("gap_analysis")
        
        t_in = item.get("tokens_in", 0)
        t_out = item.get("tokens_out", 0)
        cost = item.get("cost", 0.0)
        
        if not r or not s or not g:
            continue
            
        total_articles += 1
        total_cqs += r.cqs_score
        total_cost += cost
        total_tokens_in += t_in
        total_tokens_out += t_out
        
        if r.cqs_score >= 80:
            excellent_count += 1
        else:
            needs_improvement_count += 1
            
        # --- 1. FULL ROW ---
        row_full = {
            "URL": url,
            "Fraza": keyword,
            "CQS Score": r.cqs_score,
            "AI Citability": r.ai_citability_score,
            "Koszt ($)": cost,
            "Tokens IN": t_in,
            "Tokens OUT": t_out,
            "Executive Summary": r.executive_summary,
            "Missing TF-IDF": ", ".join(s.missing_tf_idf_terms) if s.missing_tf_idf_terms else ""
        }
        
        # Dimensions
        for dim in s.dimensions:
            row_full[f"{dim.dimension_name} Score"] = dim.score
            row_full[f"{dim.dimension_name} Problem"] = dim.top_problem
            
        # EEAT
        for eeat in s.eeat_signals:
            row_full[f"EEAT {eeat.dimension} Score"] = eeat.score
            row_full[f"EEAT {eeat.dimension} Missing"] = eeat.missing_signals
            
        # Recommendations
        for i, rec in enumerate(r.recommendations):
            row_full[f"Rec {i+1} Priority"] = rec.priority
            row_full[f"Rec {i+1} Title"] = rec.title
            row_full[f"Rec {i+1} Impact"] = f"+{rec.impact_cqs}"
            row_full[f"Rec {i+1} BEFORE"] = rec.before_quote
            row_full[f"Rec {i+1} AFTER"] = rec.after_generated
            
        full_data.append(row_full)
        
        # --- 2. SHORT ROW (Bez Ocen) ---
        row_short = {
            "URL": url,
            "Fraza": keyword,
            "CQS Score": r.cqs_score,
            "AI Citability": r.ai_citability_score,
            "Koszt ($)": cost,
            "Tokens IN": t_in,
            "Tokens OUT": t_out,
            "Executive Summary": r.executive_summary,
            "Missing TF-IDF": row_full["Missing TF-IDF"]
        }
        for i, rec in enumerate(r.recommendations):
            row_short[f"Rec {i+1} Priority"] = rec.priority
            row_short[f"Rec {i+1} Title"] = rec.title
            row_short[f"Rec {i+1} Impact"] = f"+{rec.impact_cqs}"
            row_short[f"Rec {i+1} BEFORE"] = rec.before_quote
            row_short[f"Rec {i+1} AFTER"] = rec.after_generated
            
        short_data.append(row_short)
        
        # --- 3. ACTIONABLE ROW ---
        crit = [f"[- {rec.title} -]\nZmień z:\n{rec.before_quote}\nNa:\n{rec.after_generated}" for rec in r.recommendations if rec.priority.upper() == "KRYTYCZNE"]
        high = [f"[- {rec.title} -]\nZmień z:\n{rec.before_quote}\nNa:\n{rec.after_generated}" for rec in r.recommendations if rec.priority.upper() == "WYSOKIE"]
        med  = [f"[- {rec.title} -]\nZmień z:\n{rec.before_quote}\nNa:\n{rec.after_generated}" for rec in r.recommendations if rec.priority.upper() == "ŚREDNIE"]
        
        h2s = r.target_structure_h2 if r.target_structure_h2 else []
        blufs = r.bluf_per_h2 if r.bluf_per_h2 else []
        structure = []
        for i in range(max(len(h2s), len(blufs))):
            h2 = h2s[i] if i < len(h2s) else ""
            bluf = blufs[i] if i < len(blufs) else ""
            structure.append(f"{h2}\nBLUF: {bluf}")
            
        eeat_miss = []
        for e in s.eeat_signals:
            if e.missing_signals and e.missing_signals.strip() != "":
                eeat_miss.append(f"[{e.dimension}]: {e.missing_signals}")
                
        row_action = {
            "URL": url,
            "Fraza": keyword,
            "CQS Score": r.cqs_score,
            "Koszt ($)": cost,
            "KRYTYCZNE Rekomendacje": "\n\n".join(crit) if crit else "Brak",
            "WYSOKIE Rekomendacje": "\n\n".join(high) if high else "Brak",
            "ŚREDNIE Rekomendacje": "\n\n".join(med) if med else "Brak",
            "Docelowa Struktura H2": "\n\n".join(structure) if structure else "Brak",
            "Braki E-E-A-T": "\n".join(eeat_miss) if eeat_miss else "Brak",
            "Brakujące Słowa (TF-IDF)": row_full["Missing TF-IDF"]
        }
        
        action_data.append(row_action)
        
        # --- 4. ZBIORCZY EAV MATRIX ---
        for e in g.eav_matrix:
            row_eav = {
                "URL": url,
                "Fraza": keyword,
                "Attribute": e.attribute,
                "URR Type": e.urr_type,
                "Coverage": e.coverage,
                "Priority": e.priority,
                "Status": e.status
            }
            for i in range(10):
                col_name = f"K{i+1}"
                if i < len(e.competitors_presence):
                    row_eav[col_name] = "+" if e.competitors_presence[i] else "-"
                else:
                    row_eav[col_name] = "Brak danych"
            eav_data.append(row_eav)
            
    # --- 5. PODSUMOWANIE ---
    avg_cqs = round(total_cqs / total_articles, 2) if total_articles > 0 else 0
    summary_text = f"Sprawdzono {total_articles} artykułów. {excellent_count} z nich ma ocenę bardzo dobrą (CQS >= 80), {needs_improvement_count} jest do poprawy (CQS < 80). Średnia ilość punktów CQS to {avg_cqs}."
    
    summary_data = [
        {"Metryka": "Podsumowanie", "Wartość": summary_text},
        {"Metryka": "Zbadane adresy URL", "Wartość": total_articles},
        {"Metryka": "Średni wynik CQS", "Wartość": avg_cqs},
        {"Metryka": "Artykuły bardzo dobre (>=80)", "Wartość": excellent_count},
        {"Metryka": "Artykuły do poprawy (<80)", "Wartość": needs_improvement_count},
        {"Metryka": "Łączny koszt audytu masowego ($)", "Wartość": round(total_cost, 4)},
        {"Metryka": "Łączne zużycie tokenów (IN)", "Wartość": total_tokens_in},
        {"Metryka": "Łączne zużycie tokenów (OUT)", "Wartość": total_tokens_out}
    ]
        
    df_full = pd.DataFrame(full_data)
    df_short = pd.DataFrame(short_data)
    df_action = pd.DataFrame(action_data)
    df_eav = pd.DataFrame(eav_data)
    df_summary = pd.DataFrame(summary_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name="Podsumowanie", index=False)
        df_action.to_excel(writer, sheet_name="Rekomendacje (Actionable)", index=False)
        df_short.to_excel(writer, sheet_name="Skrócony (Bez Ocen)", index=False)
        df_eav.to_excel(writer, sheet_name="Zbiorczy Matrix EAV", index=False)
        df_full.to_excel(writer, sheet_name="Pełny Raport", index=False)
    
    output.seek(0)
    return output.getvalue()

def create_zip_archive(files_dict: dict) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename, filebytes in files_dict.items():
            zf.writestr(filename, filebytes)
    output.seek(0)
    return output.getvalue()
