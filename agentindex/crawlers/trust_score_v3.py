"""
Trust Score v3 — Federated with External Validation
=====================================================
Extends v2 with a new "External Validation" dimension that incorporates
OpenSSF Scorecard, OSV.dev, community signals, and citation data.

Trust Score v3 (0-100):
├── Code Quality (20%)        — description, name, capabilities, CVE count
├── Community Adoption (20%)  — stars, downloads, SO questions, Reddit mentions
├── Compliance (15%)          — license, EU risk class
├── Operational Health (15%)  — recency, issue close rate
├── Security (15%)            — CVEs, OpenSSF Scorecard, OSV cross-ref
└── External Validation (15%) — openssf_score, osv_crossref, community, citations

If external data is unavailable, dimension defaults to 50 and weight
redistributes proportionally.

Usage: python3 -m agentindex.crawlers.trust_score_v3
"""

import json
import logging
import math
import os
import sqlite3
from datetime import datetime, timezone

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [trust-v3] %(message)s")
logger = logging.getLogger("trust-v3")

from agentindex.db_config import get_write_dsn
DB_URL = os.environ.get("DATABASE_URL") or get_write_dsn()
SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", "crypto", "crypto_trust.db")

BASE_WEIGHTS = {
    "code_quality": 0.20,
    "community": 0.20,
    "compliance": 0.15,
    "operational": 0.15,
    "security": 0.15,
    "external_validation": 0.15,
}

LICENSE_BONUS = {
    "PERMISSIVE": 10,
    "COPYLEFT": 5,
    "VIRAL": 0,
    "UNKNOWN": -5,
    "PROPRIETARY": -3,
}


def load_all_enrichment():
    """Load all enrichment data including external trust signals."""
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    # Downloads
    downloads = {}
    try:
        for row in conn.execute("SELECT agent_id, registry, weekly_downloads FROM package_downloads WHERE agent_id IS NOT NULL"):
            aid = row["agent_id"]
            if aid not in downloads:
                downloads[aid] = {"npm_weekly": 0, "pypi_weekly": 0}
            if row["registry"] == "npm":
                downloads[aid]["npm_weekly"] = row["weekly_downloads"] or 0
            elif row["registry"] == "pypi":
                downloads[aid]["pypi_weekly"] = row["weekly_downloads"] or 0
    except Exception:
        pass

    # CVEs
    cves = {}
    try:
        for row in conn.execute("""
            SELECT agent_id, COUNT(*) as cve_count,
                   MAX(CASE WHEN severity = 'CRITICAL' THEN 1 ELSE 0 END) as has_critical,
                   MAX(CASE WHEN severity = 'HIGH' THEN 1 ELSE 0 END) as has_high,
                   MAX(cvss_score) as max_cvss
            FROM agent_vulnerabilities GROUP BY agent_id
        """):
            cves[row["agent_id"]] = {
                "count": row["cve_count"],
                "has_critical": bool(row["has_critical"]),
                "has_high": bool(row["has_high"]),
                "max_cvss": row["max_cvss"],
            }
    except Exception:
        pass

    # Licenses
    licenses = {}
    try:
        for row in conn.execute("SELECT agent_id, license_spdx, license_category FROM agent_licenses"):
            licenses[row["agent_id"]] = {"spdx": row["license_spdx"], "category": row["license_category"]}
    except Exception:
        pass

    # External trust signals (by agent_name, not agent_id)
    external = {}
    try:
        for row in conn.execute("SELECT agent_name, source, signal_name, signal_value, signal_max FROM external_trust_signals"):
            name = row["agent_name"]
            if name not in external:
                external[name] = {}
            key = f"{row['source']}_{row['signal_name']}"
            external[name][key] = {
                "value": row["signal_value"],
                "max": row["signal_max"],
            }
    except Exception:
        pass

    # Citations
    citations = {}
    try:
        for row in conn.execute("SELECT agent_referenced, COUNT(*) as cnt FROM nerq_citations WHERE agent_referenced IS NOT NULL GROUP BY agent_referenced"):
            citations[row["agent_referenced"]] = row["cnt"]
    except Exception:
        pass

    # Federation contributions
    federation = {}
    try:
        for row in conn.execute("""
            SELECT agent_name, AVG(score) as avg_score, COUNT(*) as cnt
            FROM federation_contributions
            WHERE contributor_trust IN ('VERIFIED', 'TRUSTED')
            GROUP BY agent_name
        """):
            federation[row["agent_name"]] = {"avg_score": row["avg_score"], "count": row["cnt"]}
    except Exception:
        pass

    conn.close()
    logger.info(f"Enrichment: {len(downloads)} downloads, {len(cves)} CVEs, {len(licenses)} licenses, "
                f"{len(external)} external signals, {len(citations)} citations, {len(federation)} federation")
    return downloads, cves, licenses, external, citations, federation


def compute_percentile(value, all_values):
    if not all_values or value is None:
        return 0
    count_below = sum(1 for v in all_values if v < value)
    return (count_below / len(all_values)) * 100


def calculate_v3_score(agent, downloads_data, cve_data, license_data,
                        external_data, citations_data, federation_data, dl_percentiles):
    """Calculate Trust Score v3 with external validation dimension."""
    agent_id = str(agent["id"])
    agent_name = agent["name"]

    # ── Code Quality (20%) ──────────────────────────────
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

    cve = cve_data.get(agent_id)
    if cve:
        cq -= min(25, cve["count"] * 5)
        if cve["has_critical"]: cq -= 10
    cq = max(0, min(100, cq))

    # ── Community Adoption (20%) ─────────────────────────
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

    dl_data = downloads_data.get(agent_id)
    if dl_data:
        total_weekly = dl_data.get("npm_weekly", 0) + dl_data.get("pypi_weekly", 0)
        if total_weekly > 0:
            pct = compute_percentile(total_weekly, dl_percentiles)
            if pct >= 95: ca += 20
            elif pct >= 80: ca += 15
            elif pct >= 50: ca += 10
            elif pct >= 20: ca += 5

    # NEW: Stack Overflow & Reddit boost
    ext = external_data.get(agent_name, {})
    so_questions = ext.get("stackoverflow_stackoverflow_questions", {}).get("value", 0) or 0
    reddit_mentions = ext.get("reddit_reddit_mentions_30d", {}).get("value", 0) or 0
    if so_questions >= 1000: ca += 10
    elif so_questions >= 100: ca += 7
    elif so_questions >= 10: ca += 3
    if reddit_mentions >= 10: ca += 5
    elif reddit_mentions >= 3: ca += 2

    source_bonus = {"github": 8, "npm": 7, "pypi": 7, "npm_full": 7, "pypi_full": 7,
                    "huggingface": 5, "mcp": 5, "mcp_registry": 5}.get(agent.get("source", ""), 2)
    ca += source_bonus
    ca = min(100, ca)

    # ── Compliance (15%) ─────────────────────────────────
    comp = 50
    if agent.get("license"): comp += 10
    eu_risk = agent.get("eu_risk_class", "")
    if eu_risk == "minimal": comp += 15
    elif eu_risk == "limited": comp += 10
    elif eu_risk == "high": comp -= 10
    elif eu_risk == "unacceptable": comp -= 30
    lic = license_data.get(agent_id)
    if lic:
        comp += LICENSE_BONUS.get(lic["category"], 0)
    comp = max(0, min(100, comp))

    # ── Operational Health (15%) ─────────────────────────
    op = 50
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

    # NEW: GitHub issue close rate bonus
    close_rate = ext.get("github_community_issue_close_rate", {}).get("value")
    if close_rate is not None:
        if close_rate >= 0.7: op += 10
        elif close_rate >= 0.4: op += 5
    op = max(0, min(100, op))

    # ── Security (15%) ───────────────────────────────────
    sec = 85
    cve = cve_data.get(agent_id)
    if cve:
        sec -= min(40, cve["count"] * 8)
        if cve["has_critical"]: sec -= 25
        elif cve["has_high"]: sec -= 15
        if cve.get("max_cvss") and cve["max_cvss"] >= 9.0: sec -= 10
    else:
        sec = 70
    if lic and lic["category"] == "UNKNOWN": sec -= 5

    # NEW: OpenSSF Scorecard boost
    openssf = ext.get("openssf_scorecard_overall_score", {}).get("value")
    if openssf is not None:
        if openssf >= 7: sec += 10
        elif openssf >= 5: sec += 5
        elif openssf < 3: sec -= 5

    # NEW: OSV cross-reference
    osv_count = ext.get("osv_dev_vulnerability_count", {}).get("value", 0) or 0
    if osv_count > 0:
        sec -= min(15, int(osv_count) * 3)
    sec = max(0, min(100, sec))

    # ── External Validation (15%) — NEW DIMENSION ────────
    has_external = False
    ev = 50  # neutral default

    if openssf is not None:
        has_external = True
        ev = max(0, min(100, openssf * 10))  # 0-10 → 0-100

    # OSV cross-validation: same findings from multiple sources = more confidence
    osv_vulns = ext.get("osv_dev_vulnerability_count", {}).get("value", 0) or 0
    our_cve_count = cve["count"] if cve else 0
    if osv_vulns >= 0 and our_cve_count >= 0:
        # If both sources agree (similar counts), boost confidence
        if abs(osv_vulns - our_cve_count) <= 2:
            ev += 10
            has_external = True

    # Community engagement
    if so_questions > 0 or reddit_mentions > 0:
        has_external = True
        community_score = min(30, (min(so_questions, 1000) / 1000 * 20) + (min(reddit_mentions, 25) / 25 * 10))
        ev += community_score

    # Citations (network effect)
    cite_count = citations_data.get(agent_name, 0)
    if cite_count > 0:
        has_external = True
        ev += min(10, cite_count * 2)

    # Federation signals
    fed = federation_data.get(agent_name)
    if fed and fed["count"] > 0:
        has_external = True
        ev += min(10, (fed["avg_score"] or 0) / 10)

    ev = max(0, min(100, ev))

    # ── Weighted total ───────────────────────────────────
    if has_external:
        weights = BASE_WEIGHTS.copy()
    else:
        # Redistribute external_validation weight proportionally
        ev_weight = BASE_WEIGHTS["external_validation"]
        other_total = 1.0 - ev_weight
        weights = {}
        for k, v in BASE_WEIGHTS.items():
            if k == "external_validation":
                weights[k] = 0.0
            else:
                weights[k] = v / other_total
        ev = 50  # neutral, but weight is 0

    total = (
        cq * weights["code_quality"]
        + ca * weights["community"]
        + comp * weights["compliance"]
        + op * weights["operational"]
        + sec * weights["security"]
        + ev * weights["external_validation"]
    )

    return round(total, 1), {
        "code_quality": round(cq, 1),
        "community": round(ca, 1),
        "compliance": round(comp, 1),
        "operational": round(op, 1),
        "security": round(sec, 1),
        "external_validation": round(ev, 1),
        "has_external_data": has_external,
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


def run(limit=50000):
    downloads, cves, licenses, external, citations, federation = load_all_enrichment()

    # Build download percentile reference
    all_weekly = []
    for d in downloads.values():
        total = d.get("npm_weekly", 0) + d.get("pypi_weekly", 0)
        if total > 0:
            all_weekly.append(total)
    all_weekly.sort()

    # Get agents that have ANY enrichment data (including external)
    enriched_ids = set(downloads.keys()) | set(cves.keys()) | set(licenses.keys())

    # Also include agents with external signals (by name → need to resolve to ID)
    external_names = set(external.keys()) | set(citations.keys()) | set(federation.keys())

    if not enriched_ids and not external_names:
        logger.info("No enrichment data available. Run crawlers first.")
        return

    logger.info(f"Recalculating v3 scores: {len(enriched_ids)} by ID, {len(external_names)} by name")

    pg_conn = psycopg2.connect(DB_URL)
    pg_cur = pg_conn.cursor()

    updated = 0
    score_changes = []
    grade_changes = 0

    # Process by ID batches
    enriched_list = list(enriched_ids)
    for i in range(0, len(enriched_list), 500):
        batch_ids = enriched_list[i:i + 500]
        pg_cur.execute("""
            SELECT id::text, name, description, source, stars, forks, downloads,
                   last_source_update, language, license, category, capabilities,
                   is_verified, is_active, trust_score, trust_score_v2, trust_grade,
                   eu_risk_class
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
                "eu_risk_class": row[17],
            }

            old_score = row[15] or row[14] or 0  # trust_score_v2 or trust_score
            old_grade = row[16] or ""
            new_score, components = calculate_v3_score(
                agent, downloads, cves, licenses, external, citations, federation, all_weekly
            )

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
                if grade != old_grade:
                    grade_changes += 1

        pg_conn.commit()
        if (i + 500) % 5000 == 0:
            logger.info(f"  Progress: {min(i + 500, len(enriched_list))}/{len(enriched_list)}")

    # Also process agents with external data by name (that may not be in enriched_ids)
    if external_names:
        name_list = list(external_names)
        for i in range(0, len(name_list), 200):
            batch_names = name_list[i:i + 200]
            pg_cur.execute("""
                SELECT id::text, name, description, source, stars, forks, downloads,
                       last_source_update, language, license, category, capabilities,
                       is_verified, is_active, trust_score, trust_score_v2, trust_grade,
                       eu_risk_class
                FROM entity_lookup
                WHERE name = ANY(%s) AND is_active = true
            """, (batch_names,))

            for row in pg_cur.fetchall():
                agent = {
                    "id": row[0], "name": row[1], "description": row[2],
                    "source": row[3], "stars": row[4], "forks": row[5],
                    "downloads": row[6], "last_source_update": row[7],
                    "language": row[8], "license": row[9], "category": row[10],
                    "capabilities": row[11], "is_verified": row[12],
                    "is_active": row[13], "trust_score": row[14],
                    "eu_risk_class": row[17],
                }

                if agent["id"] in enriched_ids:
                    continue  # Already processed

                old_score = row[15] or row[14] or 0
                old_grade = row[16] or ""
                new_score, components = calculate_v3_score(
                    agent, downloads, cves, licenses, external, citations, federation, all_weekly
                )

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
                    if grade != old_grade:
                        grade_changes += 1

            pg_conn.commit()

    pg_conn.close()

    # Stats
    if score_changes:
        avg_change = sum(score_changes) / len(score_changes)
        increases = sum(1 for c in score_changes if c > 0)
        decreases = sum(1 for c in score_changes if c < 0)
    else:
        avg_change, increases, decreases = 0, 0, 0

    return {
        "enriched_by_id": len(enriched_ids),
        "enriched_by_name": len(external_names),
        "updated": updated,
        "avg_change": round(avg_change, 1),
        "increases": increases,
        "decreases": decreases,
        "grade_changes": grade_changes,
    }


def main():
    logger.info("=" * 60)
    logger.info("Trust Score v3 — Federated Recalculation")
    logger.info("=" * 60)

    result = run()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Trust Score v3 — COMPLETE")
    logger.info(f"  Agents with enrichment (by ID): {result['enriched_by_id']}")
    logger.info(f"  Agents with external signals (by name): {result['enriched_by_name']}")
    logger.info(f"  Scores updated: {result['updated']}")
    logger.info(f"  Average change: {result['avg_change']:+.1f}")
    logger.info(f"  Increases: {result['increases']}, Decreases: {result['decreases']}")
    logger.info(f"  Grade changes: {result['grade_changes']}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    main()
