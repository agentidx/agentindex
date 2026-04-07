#!/usr/bin/env python3
"""
Trust Score v2 — Enriched with CVE, download, and license data
================================================================
Reads new data from SQLite (package_downloads, agent_vulnerabilities,
agent_licenses) and recalculates trust scores for matching agents
in PostgreSQL.

Trust Score v2 (0-100):
├── Code Quality (25%) — desc length, name quality, has capabilities
│   + CVE count (more CVEs = lower), security advisory count
├── Community Adoption (25%) — stars, downloads, forks
│   + npm/PyPI weekly downloads percentile boost
├── Compliance (20%) — license, EU risk class
│   + license_category bonus/penalty
├── Operational Health (15%) — recency, activity
│   + release frequency from GitHub
└── Security (15%) — CVE-based dimension
    = f(cve_count, max_severity, has_active_advisory)

Usage: python3 -m agentindex.crawlers.trust_score_v2
"""

import json
import logging
import math
import os
import sqlite3
from datetime import datetime, timezone

import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [trust-v2] %(message)s",
)
logger = logging.getLogger("trust-v2")

DB_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/agentindex")
SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", "crypto", "crypto_trust.db")

# Weights
WEIGHTS = {
    "code_quality": 0.25,
    "community": 0.25,
    "compliance": 0.20,
    "operational": 0.15,
    "security": 0.15,
}

LICENSE_BONUS = {
    "PERMISSIVE": 10,
    "COPYLEFT": 5,
    "VIRAL": 0,
    "UNKNOWN": -5,
    "PROPRIETARY": -3,
}


def load_enrichment_data():
    """Load CVE, download, and license data from SQLite."""
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    # Downloads
    downloads = {}
    try:
        for row in conn.execute("SELECT agent_id, registry, weekly_downloads, monthly_downloads FROM package_downloads WHERE agent_id IS NOT NULL"):
            aid = row["agent_id"]
            if aid not in downloads:
                downloads[aid] = {"npm_weekly": 0, "pypi_weekly": 0}
            if row["registry"] == "npm":
                downloads[aid]["npm_weekly"] = row["weekly_downloads"] or 0
            elif row["registry"] == "pypi":
                downloads[aid]["pypi_weekly"] = row["weekly_downloads"] or 0
    except Exception as e:
        logger.warning(f"No package_downloads table: {e}")

    # CVEs
    cves = {}
    try:
        for row in conn.execute("""
            SELECT agent_id, COUNT(*) as cve_count,
                   MAX(CASE WHEN severity = 'CRITICAL' THEN 1 ELSE 0 END) as has_critical,
                   MAX(CASE WHEN severity = 'HIGH' THEN 1 ELSE 0 END) as has_high,
                   MAX(cvss_score) as max_cvss
            FROM agent_vulnerabilities
            GROUP BY agent_id
        """):
            cves[row["agent_id"]] = {
                "count": row["cve_count"],
                "has_critical": bool(row["has_critical"]),
                "has_high": bool(row["has_high"]),
                "max_cvss": row["max_cvss"],
            }
    except Exception as e:
        logger.warning(f"No agent_vulnerabilities table: {e}")

    # Licenses
    licenses = {}
    try:
        for row in conn.execute("SELECT agent_id, license_spdx, license_category FROM agent_licenses"):
            licenses[row["agent_id"]] = {
                "spdx": row["license_spdx"],
                "category": row["license_category"],
            }
    except Exception as e:
        logger.warning(f"No agent_licenses table: {e}")

    conn.close()

    logger.info(f"Enrichment data loaded: {len(downloads)} downloads, {len(cves)} CVEs, {len(licenses)} licenses")
    return downloads, cves, licenses


def compute_percentile(value, all_values):
    """Compute percentile rank of value in sorted all_values."""
    if not all_values or value is None:
        return 0
    count_below = sum(1 for v in all_values if v < value)
    return (count_below / len(all_values)) * 100


def calculate_v2_score(agent, downloads_data, cve_data, license_data, dl_percentiles):
    """Calculate Trust Score v2 for a single agent."""
    agent_id = str(agent["id"])

    # ── Code Quality (25%) ──────────────────────────
    cq = 0
    desc = agent.get("description") or ""
    if len(desc) >= 200: cq += 35
    elif len(desc) >= 100: cq += 25
    elif len(desc) >= 50: cq += 15
    elif len(desc) >= 20: cq += 8

    name = agent.get("name") or ""
    if 5 <= len(name) <= 50: cq += 15
    elif len(name) >= 2: cq += 5

    caps = agent.get("capabilities")
    if caps:
        cq += min(15, len(caps) * 4)

    if agent.get("category"): cq += 10
    if agent.get("license"): cq += 10

    # CVE penalty on code quality
    cve = cve_data.get(agent_id)
    if cve:
        cq -= min(25, cve["count"] * 5)  # -5 per CVE, max -25
        if cve["has_critical"]: cq -= 10

    cq = max(0, min(100, cq))

    # ── Community Adoption (25%) ──────────────────────
    ca = 0
    stars = agent.get("stars") or 0
    if stars >= 1000: ca += 35
    elif stars >= 100: ca += 25
    elif stars >= 10: ca += 15
    elif stars >= 1: ca += 8

    dl = agent.get("downloads") or 0
    if dl >= 100000: ca += 25
    elif dl >= 10000: ca += 20
    elif dl >= 1000: ca += 15
    elif dl >= 100: ca += 10
    elif dl >= 10: ca += 5

    forks = agent.get("forks") or 0
    if forks >= 100: ca += 15
    elif forks >= 20: ca += 10
    elif forks >= 5: ca += 7
    elif forks >= 1: ca += 3

    # NEW: npm/PyPI download percentile boost
    dl_data = downloads_data.get(agent_id)
    if dl_data:
        total_weekly = dl_data.get("npm_weekly", 0) + dl_data.get("pypi_weekly", 0)
        if total_weekly > 0:
            pct = compute_percentile(total_weekly, dl_percentiles)
            if pct >= 95: ca += 20
            elif pct >= 80: ca += 15
            elif pct >= 50: ca += 10
            elif pct >= 20: ca += 5

    source_bonus = {"github": 8, "npm": 7, "pypi": 7, "npm_full": 7, "pypi_full": 7,
                    "huggingface": 5, "mcp": 5, "mcp_registry": 5}.get(agent.get("source", ""), 2)
    ca += source_bonus
    ca = min(100, ca)

    # ── Compliance (20%) ──────────────────────────────
    comp = 50  # base
    if agent.get("license"): comp += 10
    eu_risk = agent.get("eu_risk_class", "")
    if eu_risk == "minimal": comp += 15
    elif eu_risk == "limited": comp += 10
    elif eu_risk == "high": comp -= 10
    elif eu_risk == "unacceptable": comp -= 30

    # NEW: license category bonus
    lic = license_data.get(agent_id)
    if lic:
        comp += LICENSE_BONUS.get(lic["category"], 0)

    comp = max(0, min(100, comp))

    # ── Operational Health (15%) ──────────────────────
    op = 50  # base
    last_update = agent.get("last_source_update")
    if last_update:
        try:
            if isinstance(last_update, str):
                lu = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
            else:
                lu = last_update
            days = (datetime.now(timezone.utc) - lu.replace(tzinfo=timezone.utc if lu.tzinfo is None else lu.tzinfo)).days
            if days <= 7: op += 40
            elif days <= 30: op += 30
            elif days <= 90: op += 20
            elif days <= 180: op += 10
            elif days > 365: op -= 15
        except Exception:
            pass

    if agent.get("is_verified"): op += 10
    if agent.get("is_active") is False: op -= 30
    op = max(0, min(100, op))

    # ── Security (15%) — NEW DIMENSION ────────────────
    sec = 85  # start high, penalize for issues
    cve = cve_data.get(agent_id)
    if cve:
        sec -= min(40, cve["count"] * 8)  # -8 per CVE
        if cve["has_critical"]: sec -= 25
        elif cve["has_high"]: sec -= 15
        if cve.get("max_cvss") and cve["max_cvss"] >= 9.0: sec -= 10
    else:
        # No CVE data = not scanned, neutral
        sec = 70

    # License affects security perception
    if lic:
        if lic["category"] == "UNKNOWN": sec -= 5
    sec = max(0, min(100, sec))

    # ── Weighted total ────────────────────────────────
    total = (
        cq * WEIGHTS["code_quality"]
        + ca * WEIGHTS["community"]
        + comp * WEIGHTS["compliance"]
        + op * WEIGHTS["operational"]
        + sec * WEIGHTS["security"]
    )

    # ── Popularity floor ──────────────────────────────
    # Tools with massive proven adoption should not score below a credible
    # minimum. A tool with 50K+ GitHub stars is demonstrably safe-to-use
    # regardless of metadata completeness. This prevents short descriptions
    # or missing license fields from making popular tools look dangerous.
    if stars >= 50000:
        total = max(total, 75)  # B+ floor
    elif stars >= 20000:
        total = max(total, 70)  # B floor
    elif stars >= 10000:
        total = max(total, 65)  # B- floor
    elif stars >= 5000:
        total = max(total, 60)  # C+ floor

    return round(total, 1), {
        "code_quality": round(cq, 1),
        "community": round(ca, 1),
        "compliance": round(comp, 1),
        "operational": round(op, 1),
        "security": round(sec, 1),
    }


def grade_from_score(score):
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


def run():
    downloads, cves, licenses = load_enrichment_data()

    # Build download percentile reference
    all_weekly = []
    for d in downloads.values():
        total = d.get("npm_weekly", 0) + d.get("pypi_weekly", 0)
        if total > 0:
            all_weekly.append(total)
    all_weekly.sort()

    # Get agents that have enrichment data
    enriched_ids = set(downloads.keys()) | set(cves.keys()) | set(licenses.keys())
    if not enriched_ids:
        logger.info("No enrichment data available. Run crawlers first.")
        return

    logger.info(f"Recalculating trust scores for {len(enriched_ids)} enriched agents")

    pg_conn = psycopg2.connect(DB_URL)
    pg_cur = pg_conn.cursor()

    # Fetch agent data for enriched agents in batches
    updated = 0
    score_changes = []
    enriched_list = list(enriched_ids)

    for i in range(0, len(enriched_list), 500):
        batch_ids = enriched_list[i:i + 500]
        # Use ANY with array for batch lookup
        pg_cur.execute("""
            SELECT id::text, name, description, source, stars, forks, downloads,
                   last_source_update, language, license, category, capabilities,
                   is_verified, is_active, trust_score, eu_risk_class,
                   frameworks, protocols
            FROM entity_lookup
            WHERE id::text = ANY(%s)
        """, (batch_ids,))

        for row in pg_cur.fetchall():
            agent = {
                "id": row[0], "name": row[1], "description": row[2],
                "source": row[3], "stars": row[4], "forks": row[5],
                "downloads": row[6], "last_source_update": row[7],
                "language": row[8], "license": row[9], "category": row[10],
                "capabilities": row[11], "is_verified": row[12],
                "is_active": row[13], "trust_score": row[14],
                "eu_risk_class": row[15], "frameworks": row[16],
                "protocols": row[17],
            }

            old_score = agent["trust_score"] or 0
            new_score, components = calculate_v2_score(
                agent, downloads, cves, licenses, all_weekly
            )

            # Only update if we have new data and score changed
            if abs(new_score - old_score) > 0.1:
                grade = grade_from_score(new_score)
                pg_cur.execute("""
                    UPDATE agents SET
                        trust_score_v2 = %s,
                        trust_grade = %s,
                        trust_components = %s,
                        trust_calculated_at = NOW()
                    WHERE id = %s::uuid
                """, (new_score, grade, json.dumps(components), agent["id"]))
                updated += 1
                score_changes.append(new_score - old_score)

        pg_conn.commit()
        logger.info(f"  Progress: {min(i + 500, len(enriched_list))}/{len(enriched_list)}")

    pg_conn.commit()
    pg_conn.close()

    # Statistics
    if score_changes:
        avg_change = sum(score_changes) / len(score_changes)
        increases = sum(1 for c in score_changes if c > 0)
        decreases = sum(1 for c in score_changes if c < 0)
    else:
        avg_change = 0
        increases = 0
        decreases = 0

    logger.info(f"\n{'='*60}")
    logger.info(f"Trust Score v2 Recalculation Complete")
    logger.info(f"  Agents with enrichment data: {len(enriched_ids)}")
    logger.info(f"  Scores updated: {updated}")
    logger.info(f"  Average change: {avg_change:+.1f}")
    logger.info(f"  Increases: {increases}, Decreases: {decreases}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    run()
