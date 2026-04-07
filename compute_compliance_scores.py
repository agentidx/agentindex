#!/usr/bin/env python3
"""
Compliance Score Aggregator

Computes a weighted compliance_score (0-100) for every agent based on their
assessment across all 52 jurisdictions in agent_jurisdiction_status.

DESIGN PRINCIPLES:
1. Every jurisdiction is assessed with equal analytical rigor
2. The aggregate score weights jurisdictions by real-world impact:
   - Penalty severity (€35M EU vs $500K Colorado)
   - Enforcement likelihood (enacted > proposed > voluntary)
   - Market breadth (EU-wide vs single state)
3. Higher score = MORE compliant (100 = clean across all jurisdictions)
4. Replaces the old EU-centric compliance_score with a global one

OUTPUT: Updates agents.compliance_score for ALL agents that have jurisdiction assessments.
Also computes a jurisdiction-neutral risk summary stored in agents.eu_risk_class
(renamed conceptually to "global_risk_class" but keeping column name for compatibility).
"""

import psycopg2, psycopg2.extras, json, logging, os, time
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [score-agg] %(message)s")
logger = logging.getLogger("score-agg")
DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')

# ============================================================
# JURISDICTION WEIGHT SYSTEM
# ============================================================
# Weights reflect: enforcement power × market size × maturity
# Scale: 1.0 = baseline, higher = more impactful
# 
# Tier 1 (weight 3.0): Major enacted laws with severe penalties
# Tier 2 (weight 2.0): Enacted laws with moderate penalties or large market
# Tier 3 (weight 1.5): Enacted but narrow scope, or major proposed
# Tier 4 (weight 1.0): Voluntary, proposed, or limited scope
# Tier 5 (weight 0.5): Guidelines, principles, or very early stage

JURISDICTION_WEIGHTS = {
    # TIER 1 — Major enacted, severe penalties
    'eu_ai_act': 3.0,           # €35M / 7% global turnover, EU-wide
    'cn_cybersecurity': 2.5,    # Strict enforcement, huge market
    'cn_ai_labeling': 2.5,     # Mandatory, enforced
    
    # TIER 2 — Enacted, significant penalties
    'us_co_sb205': 2.0,        # $500K + $20K/consumer, first US state AI act
    'us_ca_sb53': 2.0,         # California, major tech market
    'us_ca_ab2013': 2.0,       # California transparency
    'us_nyc_ll144': 2.0,       # NYC bias audit, actively enforced
    'ca_aida': 2.0,            # Canada, enacted
    'br_ai_bill': 2.0,         # Brazil, large market
    'kr_ai_act': 2.0,          # South Korea, tech market
    'uk_ai_regulation': 2.0,   # UK, major market
    'sg_ai_governance': 2.0,   # Singapore, financial hub
    'in_digital_india': 2.0,   # India, massive market
    
    # TIER 2.5 — EU national implementations (add to EU AI Act)
    'eu_de_aiact': 1.5,        # Germany
    'eu_fr_aiact': 1.5,        # France
    'eu_it_aiact': 1.5,        # Italy
    'eu_es_aiact': 1.5,        # Spain
    'eu_nl_aiact': 1.5,        # Netherlands
    'eu_se_aiact': 1.5,        # Sweden
    'eu_ie_aiact': 1.5,        # Ireland
    'eu_pl_aiact': 1.5,        # Poland
    
    # TIER 3 — Enacted narrow, or major proposed
    'us_ct_sb1295': 1.5,       # Connecticut
    'us_ut_aipa': 1.5,         # Utah
    'us_ut_sb149': 1.5,        # Utah gen AI
    'us_ny_raise': 1.5,        # New York state
    'us_il_hb3773': 1.5,       # Illinois
    'us_md_sb818': 1.5,        # Maryland
    'us_take_it_down': 1.5,    # Federal NCII
    'jp_ai_governance': 1.5,   # Japan
    'au_ai_guardrails': 1.5,   # Australia proposed
    'tw_ai_basic': 1.5,        # Taiwan
    'in_dpdp': 1.5,            # India data protection
    'vn_ai_law': 1.5,          # Vietnam
    'sa_ai_authority': 1.5,    # Saudi Arabia
    'ae_ai_strategy': 1.5,     # UAE
    
    # TIER 4 — Proposed, voluntary, limited scope
    'mx_ai_regulation': 1.0,
    'cl_ai_bill': 1.0,
    'co_ai_guidelines': 1.0,   # Colombia
    'pe_ai_strategy': 1.0,
    'ke_ai_regulation': 1.0,
    'ng_ai_strategy': 1.0,
    'za_ai_regulation': 1.0,
    'ph_ai_development': 1.0,
    'th_ai_governance': 1.0,
    'nz_ai_charter': 1.0,
    
    # TIER 5 — International frameworks (soft law)
    'intl_oecd_ai': 0.75,
    'intl_coe_convention': 0.75,
    'intl_iso42001': 0.5,
}

# Risk level to penalty score (higher = worse compliance)
RISK_PENALTY = {
    'high': 1.0,        # Full penalty
    'limited': 0.4,     # Moderate concern
    'minimal': 0.0,     # No concern
}

# Status to compliance deduction
STATUS_DEDUCTION = {
    # Severe — active non-compliance
    'non_compliant': 1.0,
    'unacceptable_risk': 1.0,
    'restricted': 0.9,
    
    # High concern — requires action
    'high_risk': 0.7,
    'high_impact': 0.7,
    'requires_assessment': 0.6,
    'requires_compliance': 0.6,
    'requires_bias_audit': 0.6,
    'requires_safety_protocols': 0.6,
    'requires_licensing': 0.6,
    'requires_conformity': 0.5,
    'requires_labeling': 0.5,
    'requires_watermark': 0.5,
    'requires_disclosure': 0.5,
    'covered_frontier': 0.5,
    'covered_model': 0.5,
    'critical_sector': 0.5,
    'regulated': 0.5,
    'rights_impacting': 0.5,
    'government_compliance': 0.5,
    'charter_applies': 0.4,
    'sector_regulated': 0.4,
    
    # Moderate concern
    'moderate_impact': 0.3,
    'review_recommended': 0.2,
    'transparency_required': 0.2,
    'limited_risk': 0.15,
    
    # Low/no concern
    'certification_available': 0.05,
    'aligned': 0.0,
    'compliant': 0.0,
    'general': 0.0,
    'general_compliance': 0.0,
    'general_processing': 0.0,
    'not_applicable': 0.0,
    'not_covered': 0.0,
    'not_high_risk': 0.0,
    'not_high_impact': 0.0,
    'minimal_risk': 0.0,
    'minimal_regulation': 0.0,
    'low_risk': 0.0,
    'low_impact': 0.0,
    'exempt': 0.0,
    'no_specific_rules': 0.0,
}


def compute_agent_score(jurisdiction_rows):
    """
    Compute compliance score for a single agent from their jurisdiction assessments.
    
    Returns (compliance_score 0-100, global_risk_class, high_risk_count, confidence)
    
    Score = 100 - weighted_penalty_sum / max_possible_penalty * 100
    """
    if not jurisdiction_rows:
        return None, None, 0, 0.0
    
    total_weighted_penalty = 0.0
    total_weight = 0.0
    high_risk_count = 0
    severe_count = 0
    
    for j_id, status, risk_level in jurisdiction_rows:
        weight = JURISDICTION_WEIGHTS.get(j_id, 1.0)
        
        # Get deduction from status
        status_deduction = STATUS_DEDUCTION.get(status, 0.1)  # Unknown = small penalty
        
        # Get risk penalty
        risk_penalty = RISK_PENALTY.get(risk_level, 0.0)
        
        # Combined penalty: max of status-based and risk-based (don't double-count)
        penalty = max(status_deduction, risk_penalty * 0.7)
        
        total_weighted_penalty += penalty * weight
        total_weight += weight
        
        if risk_level == 'high':
            high_risk_count += 1
        if status in ('non_compliant', 'unacceptable_risk', 'restricted'):
            severe_count += 1
    
    if total_weight == 0:
        return 50, 'unknown', 0, 0.0
    
    # Normalize: max possible penalty = total_weight (if penalty=1.0 everywhere)
    raw_score = 100 * (1 - total_weighted_penalty / total_weight)
    
    # Clamp to 0-100
    score = max(0, min(100, round(raw_score)))
    
    # Determine global risk class based on score AND high-risk count
    if severe_count > 0 or score < 20:
        risk_class = 'unacceptable'
    elif high_risk_count >= 10 or score < 40:
        risk_class = 'high'
    elif high_risk_count >= 3 or score < 65:
        risk_class = 'limited'
    else:
        risk_class = 'minimal'
    
    # Confidence based on how many jurisdictions were assessed
    confidence = min(1.0, len(jurisdiction_rows) / 52)
    
    return score, risk_class, high_risk_count, confidence


def run(batch_size=50000):
    """Compute compliance_score for all agents from jurisdiction assessments."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    # Count agents with jurisdiction data
    cur.execute("SELECT COUNT(DISTINCT agent_id) FROM agent_jurisdiction_status")
    total = cur.fetchone()[0]
    logger.info(f"Agents with jurisdiction assessments: {total:,}")
    
    # Process in batches using distinct agent_ids
    offset = 0
    updated = 0
    start_time = time.time()
    
    while offset < total:
        # Get a batch of agent_ids
        cur.execute("""
            SELECT DISTINCT agent_id FROM agent_jurisdiction_status
            ORDER BY agent_id
            LIMIT %s OFFSET %s
        """, (batch_size, offset))
        agent_ids = [r[0] for r in cur.fetchall()]
        
        if not agent_ids:
            break
        
        # Fetch all jurisdiction data for this batch
        cur.execute("""
            SELECT agent_id, jurisdiction_id, status, risk_level
            FROM agent_jurisdiction_status
            WHERE agent_id = ANY(%s)
            ORDER BY agent_id
        """, (agent_ids,))
        
        rows = cur.fetchall()
        
        # Group by agent_id
        from collections import defaultdict
        agent_data = defaultdict(list)
        for agent_id, j_id, status, risk_level in rows:
            agent_data[agent_id].append((j_id, status, risk_level))
        
        # Compute scores and batch update
        update_vals = []
        for agent_id, j_rows in agent_data.items():
            score, risk_class, high_count, confidence = compute_agent_score(j_rows)
            if score is not None:
                update_vals.append((score, risk_class, confidence, datetime.now(), agent_id))
        
        if update_vals:
            psycopg2.extras.execute_batch(cur, """
                UPDATE agents SET 
                    compliance_score = %s,
                    eu_risk_class = %s,
                    eu_risk_confidence = %s,
                    last_compliance_check = %s
                WHERE id = %s
            """, update_vals, page_size=5000)
            conn.commit()
        
        updated += len(update_vals)
        offset += batch_size
        elapsed = time.time() - start_time
        rate = updated / elapsed if elapsed > 0 else 0
        eta = (total - updated) / rate if rate > 0 else 0
        
        logger.info(f"Progress: {updated:,}/{total:,} agents scored ({rate:.0f}/sec, ETA: {eta/60:.1f}min)")
    
    elapsed = time.time() - start_time
    logger.info(f"\n{'='*60}")
    logger.info(f"COMPLIANCE SCORE AGGREGATION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Agents scored: {updated:,}")
    logger.info(f"Time: {elapsed/60:.1f} minutes")
    
    # Summary statistics
    cur.execute("""
        SELECT eu_risk_class, COUNT(*), ROUND(AVG(compliance_score),1) as avg_score
        FROM agents 
        WHERE compliance_score IS NOT NULL
        GROUP BY eu_risk_class 
        ORDER BY COUNT(*) DESC
    """)
    logger.info(f"\nScore distribution:")
    logger.info(f"{'Risk Class':20s} {'Count':>12s} {'Avg Score':>10s}")
    for row in cur.fetchall():
        logger.info(f"  {str(row[0]):18s} {row[1]:>12,} {row[2]:>10}")
    
    cur.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE compliance_score >= 80) as excellent,
            COUNT(*) FILTER (WHERE compliance_score >= 60 AND compliance_score < 80) as good,
            COUNT(*) FILTER (WHERE compliance_score >= 40 AND compliance_score < 60) as moderate,
            COUNT(*) FILTER (WHERE compliance_score >= 20 AND compliance_score < 40) as poor,
            COUNT(*) FILTER (WHERE compliance_score < 20) as critical
        FROM agents WHERE compliance_score IS NOT NULL
    """)
    row = cur.fetchone()
    logger.info(f"\nCompliance bands:")
    logger.info(f"  Excellent (80-100): {row[0]:>12,}")
    logger.info(f"  Good     (60-79):   {row[1]:>12,}")
    logger.info(f"  Moderate (40-59):   {row[2]:>12,}")
    logger.info(f"  Poor     (20-39):   {row[3]:>12,}")
    logger.info(f"  Critical (0-19):    {row[4]:>12,}")
    
    conn.close()


if __name__ == "__main__":
    run()
