import os
import streamlit as st
from openai import OpenAI
from pydantic import BaseModel
from typing import List, Optional

def get_openai_client():
    try:
        api_key = st.secrets.get("OPENAI_API_KEY")
    except Exception:
        api_key = os.environ.get("OPENAI_API_KEY")
    return OpenAI(api_key=api_key)

# Pydantic Models for Structured Outputs

class EAVEntry(BaseModel):
    attribute: str
    urr_type: str # UNIQUE, ROOT, RARE
    coverage: str # e.g. "8/10"
    priority: str # P1, P2, P3, P4
    status: str # COVERED, GAP, UNIQUE

class GapAnalysisResult(BaseModel):
    eav_matrix: List[EAVEntry]
    top_3_gaps_p1: List[str]
    root_attributes: List[str]
    unique_opportunities: List[str]

class ScoreDimension(BaseModel):
    dimension_name: str
    score: int
    top_problem: str
    before_quote: str

class ProblematicFragment(BaseModel):
    section: str
    dimension: str
    problem: str
    before_quote: str

class SRLInstance(BaseModel):
    sentence: str
    ce_role: str # Patient
    section: str

class EEATSignal(BaseModel):
    dimension: str # Experience, Expertise, Authority, Trust
    score: int
    present_signals: str
    missing_signals: str

class ContentScores(BaseModel):
    dimensions: List[ScoreDimension]
    problematic_fragments: List[ProblematicFragment]
    srl_patient_instances: List[SRLInstance]
    eeat_signals: List[EEATSignal]
    missing_tf_idf_terms: List[str]

class Recommendation(BaseModel):
    priority: str # KRYTYCZNE, WYSOKIE, ŚREDNIE
    title: str
    context: str
    before_quote: str
    after_generated: str
    impact_cqs: int

class AuditReport(BaseModel):
    cqs_score: int
    ai_citability_score: int
    executive_summary: str
    recommendations: List[Recommendation]
    target_structure_h2: List[str]
    bluf_per_h2: List[str] # Bottom Line Up Front suggested first sentences
    eeat_ready_blocks: str # Bio, disclaimer, etc

def analyze_competitor_gaps(topic, consolidated_competitors, model_name, system_prompt) -> GapAnalysisResult:
    client = get_openai_client()
    prompt = f"""
    Analyze the top 10 competitors for the topic: "{topic}".
    Extract Entity-Attribute-Value (EAV) triplets.
    Classify each attribute as UNIQUE (1-2/10), ROOT (5+/10), or RARE (3-4/10).
    Identify content gaps assuming we are planning an article about this topic.
    
    Competitor Content:
    {consolidated_competitors}
    """
    
    response = client.beta.chat.completions.parse(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt + "\n\nWażne: Wszystkie odpowiedzi i wygenerowane treści muszą być w języku polskim. Odpowiadaj wyłącznie po polsku."},
            {"role": "user", "content": prompt}
        ],
        response_format=GapAnalysisResult
    )
    return response.choices[0].message.parsed

def score_content(source_article, gap_analysis_result: GapAnalysisResult, model_name, system_prompt) -> ContentScores:
    client = get_openai_client()
    prompt = f"""
    Analyze the following source article against the competitor gap analysis.
    Evaluate 9 dimensions (0-10): CSI Alignment, BLUF, Chunk Quality, URR Placement, Cost of Retrieval, Information Density, SRL Salience, TF-IDF Quality.
    Provide scores, top problems, and extract problematic quotes (BEFORE).
    
    Gap Analysis:
    {gap_analysis_result.model_dump_json()}
    
    Source Article:
    {source_article}
    """
    
    response = client.beta.chat.completions.parse(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt + "\n\nWażne: Wszystkie odpowiedzi i wygenerowane treści muszą być w języku polskim. Odpowiadaj wyłącznie po polsku."},
            {"role": "user", "content": prompt}
        ],
        response_format=ContentScores
    )
    return response.choices[0].message.parsed

def generate_audit_report(source_article, gap_analysis: GapAnalysisResult, scores: ContentScores, model_name, system_prompt) -> AuditReport:
    client = get_openai_client()
    prompt = f"""
    Generate a final actionable audit report.
    Calculate CQS (0-100) and AI Citability (0-10).
    Provide prioritized recommendations (KRYTYCZNE, WYSOKIE, ŚREDNIE) with BEFORE/AFTER examples.
    Generate a target H2 structure and BLUF (Bottom Line Up Front) sentences.
    
    Scores Data:
    {scores.model_dump_json()}
    
    Gap Analysis Data:
    {gap_analysis.model_dump_json()}
    
    Source Article (for context):
    {source_article}
    """
    
    response = client.beta.chat.completions.parse(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt + "\n\nWażne: Wszystkie odpowiedzi i wygenerowane treści muszą być w języku polskim. Odpowiadaj wyłącznie po polsku."},
            {"role": "user", "content": prompt}
        ],
        response_format=AuditReport
    )
    return response.choices[0].message.parsed
