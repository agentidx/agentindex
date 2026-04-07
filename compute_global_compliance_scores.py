#!/usr/bin/env python3
"""
Compute Weighted Global Compliance Scores for All Agents
========================================================
Calculates a weighted compliance_score (0-100) for each agent based on
their risk_level across all assessed jurisdictions, weighted by:
  - Penalty severity (higher fines = more weight)
  - Market size (EU/US/UK/CN = more weight)
  - Enforcement status (enacted > proposed > voluntary)

Jurisdiction tiers:
  Tier 1 (weight 8-10): EU AI Act + EU implementations, US CA SB53, US CO,
                         Canada AIDA, UK, South Korea, Brazil
  Tier 2 (weight 4-6):  Other US states, China, Japan, Australia, CoE,
                         real penalties
  Tier 3 (weight 2-3):  Voluntary frameworks, TBD penalties, small markets

Risk level scores:
  minimal      = 100
  limited      =  60
  high         =  20
  unacceptable =   0

compliance_score = weighted_sum(risk_score x jurisdiction_weight) / sum(weights)

Global risk class determined by worst risk in Tier 1 jurisdictions.

Run: cd ~/agentindex && source venv/bin/activate && python compute_global_compliance_scores.py
"""

import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, '/Users/anstudio/agentindex')
from agentindex.db.models import get_session
from sqlalchemy import text

# --- Jurisdiction weights based on penalty severity + market size ---
JURISDICTION_WEIGHTS = {
    # TIER 1 (weight 8-10) — Major penalties + huge markets
    'eu_ai_act':        10,   # E35M or 7% global turnover
    'eu_de_aiact':      10,   # Germany — largest EU economy
    'eu_fr_aiact':      10,   # France
    'eu_it_aiact':      10,   # Italy
    'eu_es_aiact':      10,   # Spain
    'eu_nl_aiact':      10,   # Netherlands
    'eu_ie_aiact':      10,   # Ireland (tech hub)
    'eu_pl_aiact':      10,   # Poland
    'eu_se_aiact':      10,   # Sweden
    'us_ca_sb53':        9,   # $10M-$50M per violation
    'us_co_sb205':       8,   # $500K per violation
    'ca_aida':           8,   # CAD $25M or 5% revenue
    'uk_ai_regulation':  8,   # UK — large market
    'kr_ai_basic_act':   8,   # W300M or 3% revenue
    'br_ai_bill':        8,   # R$50M or 2% revenue

    # TIER 2 (weight 4-6) — Real penalties or large markets
    'us_ny_raise':       6,   # $25M per violation
    'us_fed_takedown':   6,   # 3 years imprisonment
    'cn_ai_labeling':    6,   # CAC enforcement, huge market
    'cn_cybersecurity':  6,   # Y1M-Y10M, huge market
    'us_ca_ab2013':      5,   # $5K/day per violation
    'us_ca_sb942':       5,   # $5K per violation
    'us_ca_sb243':       5,   # AG enforcement, California
    'us_ct_sb1295':      5,   # AG enforcement
    'us_ny_ll144':       5,   # $1.5K per violation, NYC
    'us_il_aivi':        5,   # $5K per violation
    'us_il_hb3773':      5,   # Human rights penalties
    'us_md_aieha':       5,   # Civil rights enforcement
    'jp_ai_bill':        5,   # Administrative guidance, big market
    'au_ai_guardrails':  5,   # TBD but mandatory
    'za_popia_ai':       5,   # ZAR 10M or imprisonment
    'intl_coe_convention': 5, # Treaty obligations
    'in_it_rules':       4,   # Loss of safe harbor
    'us_tx_traiga':      4,   # Administrative remedies
    'us_ut_aipa':        4,   # UDCP enforcement
    'us_ut_sb226':       4,   # Professional licensing
    'ng_ndpr':           4,   # NGN 10M or 2%
    'ke_data_protection': 4,  # KES 5M or 1%
    'vn_ai_law':         4,   # VND 2B

    # TIER 3 (weight 2-3) — Voluntary, TBD, or small penalties
    'sg_ai_governance':  3,   # Voluntary but influential
    'in_ai_governance':  3,   # Voluntary, binding expected
    'ae_ai_strategy':    3,   # Licensing revocation
    'sa_ai_ethics':      3,   # SDAIA enforcement
    'tw_ai_basic_act':   3,   # Administrative guidance
    'ph_ai_development': 2,   # TBD
    'mx_ai_regulation':  2,   # TBD
    'cl_ai_bill':        2,   # TBD
    'pe_ai_law':         2,   # Administrative guidance
    'th_ai_governance':  2,   # Voluntary
    'nz_ai_charter':     2,   # Voluntary
    'co_ai_guidelines':  2,   # Voluntary
    'intl_oecd_ai':      2,   # Voluntary principles
    'intl_iso42001':     2,   # Certification standard
}

DEFAULT_WEIGHT = 3

RISK_SCORES = {
    'minimal':      100,
    'limited':       60,
    'high':          20,
    'unacceptable':   0,
}

RISK_SEVERITY = {
    'unacceptable': 4,
    'high': 3,
    'limited': 2,
    'minimal': 1,
}
SEVERITY_TO_CLASS = {4: 'unacceptable', 3: 'high', 2: 'limited', 1: 'minimal', 0: 'minimal'}

BATCH_SIZE = 5000


def compute_scores():
    session = get_session()

    total = session.execute(text(
        "SELECT COUNT(DISTINCT agent_id) FROM agent_jurisdiction_status"
    )).scalar()
    logger.info(f"Agents with jurisdiction assessments: {total:,}")

    offset = 0
    updated = 0
    start = time.time()

    while True:
        # Get batch of agent_ids
        batch_ids = session.execute(text("""
            SELECT DISTINCT agent_id
            FROM agent_jurisdiction_status
            ORDER BY agent_id
            LIMIT :limit OFFSET :offset
        """), {"limit": BATCH_SIZE, "offset": offset}).fetchall()

        if not batch_ids:
            break

        ids = [row[0] for row in batch_ids]

        # Get all jurisdiction statuses for this batch
        rows = session.execute(text("""
            SELECT agent_id, jurisdiction_id, risk_level
            FROM agent_jurisdiction_status
            WHERE agent_id = ANY(:ids)
        """), {"ids": ids}).fetchall()

        # Group by agent
        agent_data = {}
        for agent_id, jurisdiction_id, risk_level in rows:
            if agent_id not in agent_data:
                agent_data[agent_id] = []
            agent_data[agent_id].append((jurisdiction_id, risk_level))

        # Compute weighted scores
        updates = []
        for agent_id, jurisdictions in agent_data.items():
            weighted_sum = 0.0
            weight_total = 0.0

            for j_id, risk_level in jurisdictions:
                weight = JURISDICTION_WEIGHTS.get(j_id, DEFAULT_WEIGHT)
                score = RISK_SCORES.get(risk_level, 50)
                weighted_sum += score * weight
                weight_total += weight

            compliance_score = round(weighted_sum / weight_total) if weight_total > 0 else None

            # Global risk class: worst risk in TIER 1 jurisdictions
            # (weight >= 8), falling back to worst overall
            worst_tier1 = 0
            worst_overall = 0
            for j_id, risk_level in jurisdictions:
                sev = RISK_SEVERITY.get(risk_level, 0)
                w = JURISDICTION_WEIGHTS.get(j_id, DEFAULT_WEIGHT)
                if w >= 8:  # Tier 1
                    worst_tier1 = max(worst_tier1, sev)
                worst_overall = max(worst_overall, sev)

            # Use tier 1 worst if available, else overall worst
            worst = worst_tier1 if worst_tier1 > 0 else worst_overall
            global_risk_class = SEVERITY_TO_CLASS.get(worst, 'minimal')

            updates.append({
                'id': agent_id,
                'score': compliance_score,
                'risk': global_risk_class,
            })

        # Bulk update
        if updates:
            for u in updates:
                session.execute(text("""
                    UPDATE agents
                    SET compliance_score = :score,
                        risk_class = :risk
                    WHERE id = :id
                """), u)
            session.commit()
            updated += len(updates)

        offset += BATCH_SIZE
        elapsed = time.time() - start
        rate = updated / elapsed if elapsed > 0 else 0
        eta = ((total - updated) / rate / 60) if rate > 0 else 0
        logger.info(f"  {updated:,}/{total:,} ({rate:.0f}/sec, ETA {eta:.1f}min)")

    elapsed = time.time() - start
    logger.info(f"DONE: {updated:,} agents in {elapsed:.1f}s ({elapsed/60:.1f}min)")

    # --- Show results ---
    logger.info("\n--- Compliance Score Distribution ---")
    dist = session.execute(text("""
        SELECT
            CASE
                WHEN compliance_score >= 90 THEN '90-100 (excellent)'
                WHEN compliance_score >= 70 THEN '70-89 (good)'
                WHEN compliance_score >= 50 THEN '50-69 (moderate)'
                WHEN compliance_score >= 30 THEN '30-49 (poor)'
                WHEN compliance_score IS NOT NULL THEN '0-29 (critical)'
                ELSE 'NULL (no data)'
            END as range,
            COUNT(*) as count
        FROM agents WHERE is_active = true
        GROUP BY range ORDER BY range DESC
    """)).fetchall()
    for row in dist:
        logger.info(f"  {row[0]}: {row[1]:,}")

    logger.info("\n--- Risk Class Distribution ---")
    risk_dist = session.execute(text("""
        SELECT risk_class, COUNT(*)
        FROM agents WHERE is_active = true
        GROUP BY risk_class ORDER BY COUNT(*) DESC
    """)).fetchall()
    for row in risk_dist:
        logger.info(f"  {row[0] or 'NULL'}: {row[1]:,}")

    logger.info("\n--- Sample Agents (random) ---")
    samples = session.execute(text("""
        SELECT name, compliance_score, risk_class
        FROM agents WHERE compliance_score IS NOT NULL AND is_active = true
        ORDER BY RANDOM() LIMIT 10
    """)).fetchall()
    for s in samples:
        logger.info(f"  {s[0][:50]:50s} score={s[1]:3d}  risk={s[2]}")

    session.close()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("COMPUTING WEIGHTED GLOBAL COMPLIANCE SCORES")
    logger.info("Weighting: penalty severity x market size x enforcement")
    logger.info("=" * 60)
    compute_scores()
