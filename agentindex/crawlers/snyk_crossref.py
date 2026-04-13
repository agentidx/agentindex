"""
OSV.dev Vulnerability Cross-Reference — Wednesdays 05:30
=========================================================
Cross-references our existing vulnerability data with OSV.dev for second-source validation.
API: POST https://api.osv.dev/v1/query

Usage:
    python -m agentindex.crawlers.snyk_crossref
"""

import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy.sql import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [osv-crossref] %(message)s")
logger = logging.getLogger("osv-crossref")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"
OSV_API = "https://api.osv.dev/v1/query"

# Rate: generous, but be polite — 0.5s delay
RATE_DELAY = 0.5


def _init_db():
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS external_trust_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            source TEXT NOT NULL,
            signal_name TEXT NOT NULL,
            signal_value REAL,
            signal_max REAL,
            raw_data TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ets_agent ON external_trust_signals(agent_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ets_source ON external_trust_signals(source)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ets_unique ON external_trust_signals(agent_name, source, signal_name)")
    conn.commit()
    conn.close()


def _detect_ecosystem(agent_name, source):
    """Detect package ecosystem based on agent source and name."""
    if source in ("npm", "npm_full"):
        return "npm", agent_name
    if source in ("pypi", "pypi_full"):
        return "PyPI", agent_name
    return None, None


def _query_osv(package_name, ecosystem):
    """Query OSV.dev for vulnerabilities affecting a package."""
    try:
        resp = requests.post(OSV_API, json={
            "package": {"name": package_name, "ecosystem": ecosystem}
        }, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        logger.warning(f"OSV error for {package_name}: {e}")
        return None


def _severity_rank(severity):
    """Rank severity for max_severity calculation."""
    return {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "MEDIUM": 2, "LOW": 1}.get(severity.upper(), 0)


def _extract_severity(vuln):
    """Extract severity from an OSV vulnerability entry."""
    for sev in vuln.get("severity", []):
        if sev.get("type") == "CVSS_V3":
            score_str = sev.get("score", "")
            # Parse CVSS vector for score
            try:
                # Some have numeric score directly
                return float(score_str) if score_str.replace(".", "").isdigit() else None
            except Exception:
                pass
    # Fall back to database_specific severity
    db_spec = vuln.get("database_specific", {})
    severity = db_spec.get("severity", "")
    return severity if severity else None


def _store_osv_signals(conn, agent_name, osv_data):
    """Store OSV vulnerability signals."""
    now = datetime.now().isoformat()
    vulns = osv_data.get("vulns", [])
    vuln_count = len(vulns)

    # Determine max severity
    max_sev = "NONE"
    has_exploit = False
    cve_ids = []
    for v in vulns:
        # Check aliases for CVE IDs
        for alias in v.get("aliases", []):
            if alias.startswith("CVE-"):
                cve_ids.append(alias)
        # Check severity
        db_spec = v.get("database_specific", {})
        sev = db_spec.get("severity", "").upper()
        if _severity_rank(sev) > _severity_rank(max_sev):
            max_sev = sev
        # Check for exploit mentions
        details = v.get("details", "")
        if "exploit" in details.lower():
            has_exploit = True

    from agentindex.crypto.dual_write import dual_execute
    dual_execute(conn, """
        INSERT OR REPLACE INTO external_trust_signals
        (agent_name, source, signal_name, signal_value, signal_max, raw_data, fetched_at)
        VALUES (?, 'osv_dev', 'vulnerability_count', ?, NULL, ?, ?)
    """, (agent_name, vuln_count, json.dumps({"cve_ids": cve_ids[:20]}), now))

    dual_execute(conn, """
        INSERT OR REPLACE INTO external_trust_signals
        (agent_name, source, signal_name, signal_value, signal_max, raw_data, fetched_at)
        VALUES (?, 'osv_dev', 'max_severity', ?, 4, ?, ?)
    """, (agent_name, _severity_rank(max_sev), json.dumps({"severity": max_sev}), now))

    dual_execute(conn, """
        INSERT OR REPLACE INTO external_trust_signals
        (agent_name, source, signal_name, signal_value, signal_max, raw_data, fetched_at)
        VALUES (?, 'osv_dev', 'has_known_exploit', ?, 1, NULL, ?)
    """, (agent_name, 1.0 if has_exploit else 0.0, now))

    return vuln_count, max_sev, cve_ids


def crawl(limit=5000):
    """Cross-reference our agents with OSV.dev."""
    _init_db()

    from agentindex.db.models import get_session
    session = get_session()

    try:
        rows = session.execute(text("""
            SELECT name, source
            FROM entity_lookup
            WHERE is_active = true
              AND source IN ('npm', 'npm_full', 'pypi', 'pypi_full')
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()
    finally:
        session.close()

    logger.info(f"Found {len(rows)} npm/PyPI agents to cross-reference")

    conn = sqlite3.connect(str(SQLITE_DB))
    processed = 0
    with_vulns = 0
    total_vulns = 0
    new_cves_found = 0
    severity_dist = {"CRITICAL": 0, "HIGH": 0, "MODERATE": 0, "LOW": 0, "NONE": 0}

    # Load existing CVE IDs for cross-reference
    existing_cves = set()
    try:
        for r in conn.execute("SELECT cve_id FROM agent_vulnerabilities"):
            existing_cves.add(r[0])
    except Exception:
        pass
    logger.info(f"Existing CVE database has {len(existing_cves)} entries")

    for i, r in enumerate(rows):
        d = dict(r._mapping)
        agent_name = d["name"]
        ecosystem, pkg_name = _detect_ecosystem(agent_name, d["source"])

        if not ecosystem:
            continue

        # Check if already fetched recently
        existing = conn.execute(
            "SELECT fetched_at FROM external_trust_signals WHERE agent_name = ? AND source = 'osv_dev' AND signal_name = 'vulnerability_count' AND fetched_at > datetime('now', '-7 days')",
            (agent_name,)
        ).fetchone()
        if existing:
            continue

        osv_data = _query_osv(pkg_name, ecosystem)
        if osv_data is not None:
            vuln_count, max_sev, cve_ids = _store_osv_signals(conn, agent_name, osv_data)
            processed += 1
            if vuln_count > 0:
                with_vulns += 1
                total_vulns += vuln_count
                severity_dist[max_sev if max_sev in severity_dist else "NONE"] += 1
                # Check for new CVEs not in our existing database
                for cid in cve_ids:
                    if cid not in existing_cves:
                        new_cves_found += 1
            else:
                severity_dist["NONE"] += 1

            if processed % 100 == 0:
                conn.commit()
                logger.info(f"  Progress: {processed} checked, {with_vulns} with vulns ({i+1}/{len(rows)})")
        else:
            processed += 1

        time.sleep(RATE_DELAY)

    conn.commit()
    conn.close()

    return {
        "processed": processed,
        "with_vulnerabilities": with_vulns,
        "total_vulns": total_vulns,
        "new_cves_beyond_existing": new_cves_found,
        "severity_distribution": severity_dist,
    }


def main():
    logger.info("=" * 60)
    logger.info("OSV.dev Vulnerability Cross-Reference — starting")
    logger.info("=" * 60)

    result = crawl()

    logger.info("")
    logger.info("=" * 60)
    logger.info("OSV Cross-Reference — COMPLETE")
    logger.info(f"  Agents processed: {result['processed']}")
    logger.info(f"  With vulnerabilities: {result['with_vulnerabilities']}")
    logger.info(f"  Total vulns found: {result['total_vulns']}")
    logger.info(f"  NEW CVEs (beyond existing data): {result['new_cves_beyond_existing']}")
    logger.info(f"  Severity distribution: {result['severity_distribution']}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
