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
    master_data = []
    
    for item in all_results:
        url = item.get("url", "")
        keyword = item.get("keyword", "")
        r = item.get("report")
        s = item.get("scores")
        g = item.get("gap_analysis")
        
        if not r or not s or not g:
            continue
            
        row = {
            "URL": url,
            "Fraza": keyword,
            "CQS Score": r.cqs_score,
            "AI Citability": r.ai_citability_score,
            "Executive Summary": r.executive_summary,
            "Missing TF-IDF": ", ".join(s.missing_tf_idf_terms)
        }
        
        # Dimensions
        for dim in s.dimensions:
            row[f"{dim.dimension_name} Score"] = dim.score
            row[f"{dim.dimension_name} Problem"] = dim.top_problem
            
        # EEAT
        for eeat in s.eeat_signals:
            row[f"EEAT {eeat.dimension} Score"] = eeat.score
            row[f"EEAT {eeat.dimension} Missing"] = eeat.missing_signals
            
        # Recommendations
        for i, rec in enumerate(r.recommendations):
            row[f"Rec {i+1} Priority"] = rec.priority
            row[f"Rec {i+1} Title"] = rec.title
            row[f"Rec {i+1} Impact"] = f"+{rec.impact_cqs}"
            row[f"Rec {i+1} BEFORE"] = rec.before_quote
            row[f"Rec {i+1} AFTER"] = rec.after_generated
            
        master_data.append(row)
        
    df_master = pd.DataFrame(master_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_master.to_excel(writer, sheet_name="Master Report", index=False)
    
    output.seek(0)
    return output.getvalue()

def create_zip_archive(files_dict: dict) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename, filebytes in files_dict.items():
            zf.writestr(filename, filebytes)
    output.seek(0)
    return output.getvalue()
