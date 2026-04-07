"""
Stale Score Detector — Daily 07:00
====================================
Finds agents whose trust scores are stale (>14 days old) and triggers re-scoring.
Also detects agents with new enrichment data (downloads, CVEs, licenses) that
haven't been incorporated into their scores yet.

Usage:
    python -m agentindex.stale_score_detector
"""

import logging
import time
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.sql import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [stale-scores] %(message)s",
)
logger = logging.getLogger("stale-scores")

SQLITE_DB = Path(__file__).parent / "crypto" / "crypto_trust.db"
MAX_RESCORE_PER_RUN = 1000

# Trust score weights (same as trust_score_v2.py)
WEIGHTS = {
    "code_quality": 0.25,
    "community": 0.25,
    "compliance": 0.20,
    "operational": 0.15,
    "security": 0.15,
}


def _get_pg_session():
    from agentindex.db.models import get_session
    return get_session()


def _get_enrichment_data(agent_names):
    """Fetch enrichment data from SQLite for a batch of agents."""
    if not SQLITE_DB.exists():
        return {}
    enrichment = {}
    conn = sqlite3.connect(str(SQLITE_DB))
    try:
        for name in agent_names:
            row = conn.execute(
                "SELECT npm_weekly, pypi_weekly FROM package_downloads WHERE agent_name = ? LIMIT 1",
                (name,),
            ).fetchone()
            downloads = (row[0] or 0) + (row[1] or 0) if row else 0

            cve_row = conn.execute(
                "SELECT COUNT(*) FROM agent_vulnerabilities WHERE agent_name = ?",
                (name,),
            ).fetchone()
            cve_count = cve_row[0] if cve_row else 0

            lic_row = conn.execute(
                "SELECT license_category FROM agent_licenses WHERE agent_name = ? LIMIT 1",
                (name,),
            ).fetchone()
            license_cat = lic_row[0] if lic_row else None

            enrichment[name] = {
                "downloads": downloads,
                "cve_count": cve_count,
                "license_category": license_cat,
            }
    finally:
        conn.close()
    return enrichment


def _compute_score(agent, enrichment):
    """Compute a quick trust score from agent data + enrichment."""
    # Code quality (25%)
    desc = agent.get("description") or ""
    desc_score = min(len(desc) / 200.0, 1.0) * 60 + 20
    name = agent.get("name") or ""
    name_penalty = -10 if "/" in name and len(name) > 40 else 0
    code_quality = min(max(desc_score + name_penalty, 0), 100)

    # Community (25%)
    stars = agent.get("stars") or 0
    downloads = enrichment.get("downloads", 0) if enrichment else 0
    star_score = min(stars / 1000.0, 1.0) * 50 + (30 if stars > 0 else 0)
    dl_score = min(downloads / 10000.0, 1.0) * 40 if downloads > 0 else 0
    community = min(max(star_score + dl_score, 0), 100)

    # Compliance (20%)
    compliance = agent.get("compliance_score") or 50
    lic_cat = enrichment.get("license_category") if enrichment else None
    if lic_cat == "PERMISSIVE":
        compliance = min(compliance + 10, 100)
    elif lic_cat == "UNKNOWN" or lic_cat is None:
        compliance = max(compliance - 10, 0)

    # Operational (15%)
    is_active = agent.get("is_active", True)
    is_verified = agent.get("is_verified", False)
    operational = 60
    if is_verified:
        operational += 20
    if is_active:
        operational += 10
    operational = min(operational, 100)

    # Security (15%)
    cve_count = enrichment.get("cve_count", 0) if enrichment else 0
    security = 80
    if cve_count > 0:
        security = max(80 - cve_count * 15, 10)

    score = (
        code_quality * WEIGHTS["code_quality"]
        + community * WEIGHTS["community"]
        + compliance * WEIGHTS["compliance"]
        + operational * WEIGHTS["operational"]
        + security * WEIGHTS["security"]
    )
    return round(score, 1)


def _assign_grade(score):
    if score >= 90: return "A+"
    if score >= 85: return "A"
    if score >= 80: return "A-"
    if score >= 75: return "B+"
    if score >= 70: return "B"
    if score >= 65: return "B-"
    if score >= 60: return "C+"
    if score >= 55: return "C"
    if score >= 50: return "C-"
    if score >= 45: return "D+"
    if score >= 40: return "D"
    if score >= 35: return "D-"
    return "F"


def find_stale_agents(session, limit=MAX_RESCORE_PER_RUN):
    """Find agents whose trust_calculated_at is >14 days old or NULL."""
    cutoff = (datetime.now() - timedelta(days=14)).isoformat()
    rows = session.execute(text("""
        SELECT id, name, description, stars, compliance_score,
               is_active, is_verified,
               COALESCE(trust_score_v2, trust_score) as current_score,
               trust_calculated_at
        FROM entity_lookup
        WHERE is_active = true
          AND (trust_calculated_at IS NULL OR trust_calculated_at < :cutoff)
        ORDER BY stars DESC NULLS LAST
        LIMIT :lim
    """), {"cutoff": cutoff, "lim": limit}).fetchall()
    return [dict(r._mapping) for r in rows]


def find_agents_with_new_enrichment(session, limit=500):
    """Find agents that have enrichment data but stale scores."""
    if not SQLITE_DB.exists():
        return []

    # Get agents that have download/CVE data in SQLite
    conn = sqlite3.connect(str(SQLITE_DB))
    try:
        enriched_names = set()
        for row in conn.execute(
            "SELECT DISTINCT agent_name FROM package_downloads WHERE npm_weekly > 0 OR pypi_weekly > 0 LIMIT 2000"
        ).fetchall():
            enriched_names.add(row[0])
        for row in conn.execute(
            "SELECT DISTINCT agent_name FROM agent_vulnerabilities LIMIT 500"
        ).fetchall():
            enriched_names.add(row[0])
    finally:
        conn.close()

    if not enriched_names:
        return []

    # Check which of these haven't been re-scored recently
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    names_list = list(enriched_names)[:limit]

    # Query in batches to avoid parameter limits
    results = []
    batch_size = 100
    for i in range(0, len(names_list), batch_size):
        batch = names_list[i:i + batch_size]
        placeholders = ",".join(f":n{j}" for j in range(len(batch)))
        params = {f"n{j}": n for j, n in enumerate(batch)}
        params["cutoff"] = cutoff
        rows = session.execute(text(f"""
            SELECT id, name, description, stars, compliance_score,
                   is_active, is_verified,
                   COALESCE(trust_score_v2, trust_score) as current_score,
                   trust_calculated_at
            FROM entity_lookup
            WHERE name IN ({placeholders})
              AND is_active = true
              AND (trust_calculated_at IS NULL OR trust_calculated_at < :cutoff)
            LIMIT 200
        """), params).fetchall()
        results.extend([dict(r._mapping) for r in rows])

    return results


def rescore_agents(session, agents):
    """Re-score a batch of agents and update the DB."""
    if not agents:
        return 0

    names = [a["name"] for a in agents]
    enrichment = _get_enrichment_data(names)

    updated = 0
    for agent in agents:
        name = agent["name"]
        enr = enrichment.get(name, {})
        new_score = _compute_score(agent, enr)
        old_score = agent.get("current_score") or 0

        # Only update if score changed meaningfully
        if abs(new_score - (old_score or 0)) < 0.1:
            continue

        new_grade = _assign_grade(new_score)
        try:
            session.execute(text("""
                UPDATE agents
                SET trust_score_v2 = :score,
                    trust_grade = :grade,
                    trust_calculated_at = :now
                WHERE id = :id
            """), {
                "score": new_score,
                "grade": new_grade,
                "now": datetime.now().isoformat(),
                "id": agent["id"],
            })
            updated += 1
        except Exception as e:
            logger.error(f"Failed to update {name}: {e}")

    if updated > 0:
        session.commit()
    return updated


def main():
    logger.info("=" * 60)
    logger.info("Stale Score Detector — starting")
    logger.info("=" * 60)

    session = _get_pg_session()
    try:
        # Phase 1: Find stale agents
        logger.info("Phase 1: Finding stale agents (>14 days)...")
        stale = find_stale_agents(session)
        logger.info(f"  Found {len(stale)} stale agents")

        # Phase 2: Find agents with new enrichment data
        logger.info("Phase 2: Finding agents with new enrichment data...")
        enriched = find_agents_with_new_enrichment(session)
        logger.info(f"  Found {len(enriched)} agents with un-incorporated enrichment")

        # Merge and deduplicate
        seen_ids = set()
        all_agents = []
        for a in stale + enriched:
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"])
                all_agents.append(a)

        # Cap at MAX_RESCORE_PER_RUN
        all_agents = all_agents[:MAX_RESCORE_PER_RUN]
        logger.info(f"Total to re-score: {len(all_agents)}")

        # Phase 3: Re-score
        if all_agents:
            logger.info("Phase 3: Re-scoring...")
            batch_size = 200
            total_updated = 0
            for i in range(0, len(all_agents), batch_size):
                batch = all_agents[i:i + batch_size]
                updated = rescore_agents(session, batch)
                total_updated += updated
                logger.info(f"  Batch {i // batch_size + 1}: {updated} updated")
        else:
            total_updated = 0

        logger.info("")
        logger.info("=" * 60)
        logger.info("Stale Score Detector — COMPLETE")
        logger.info(f"  Stale agents found: {len(stale)}")
        logger.info(f"  New enrichment agents: {len(enriched)}")
        logger.info(f"  Re-scored: {total_updated}")
        logger.info(f"  Timestamp: {datetime.now().isoformat()}")
        logger.info("=" * 60)

    finally:
        session.close()


if __name__ == "__main__":
    main()
