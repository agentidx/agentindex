#!/usr/bin/env python3
"""
CVE/Vulnerability Scanner
==========================
Scans top agents for known security vulnerabilities using GitHub Advisory Database.

Usage: python3 -m agentindex.crawlers.cve_scanner
LaunchAgent: com.nerq.cve-scanner — Wednesdays 05:00
"""

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

import httpx
import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [cve-scanner] %(message)s",
)
logger = logging.getLogger("cve-scanner")

DB_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/agentindex")
SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", "crypto", "crypto_trust.db")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
MAX_AGENTS = 2000
GH_RATE_LIMIT = 1.0  # seconds between requests


def ensure_table():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_vulnerabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT,
            agent_name TEXT,
            cve_id TEXT,
            severity TEXT,
            cvss_score REAL,
            description TEXT,
            status TEXT DEFAULT 'open',
            source TEXT DEFAULT 'github',
            package_name TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(agent_id, cve_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vuln_agent ON agent_vulnerabilities(agent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vuln_severity ON agent_vulnerabilities(severity)")
    conn.commit()
    conn.close()


def get_github_agents():
    """Get agents with GitHub repos, ordered by trust score."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT id::text, name, source_id, source_url, trust_score
        FROM entity_lookup
        WHERE source = 'github'
        AND source_id IS NOT NULL AND source_id LIKE '%%/%%'
        ORDER BY trust_score DESC NULLS LAST
        LIMIT %s
    """, (MAX_AGENTS,))
    rows = cur.fetchall()
    conn.close()
    logger.info(f"Found {len(rows)} GitHub agents to scan")
    return rows


def extract_owner_repo(source_id):
    """Extract owner/repo from source_id like 'owner/repo'."""
    if not source_id:
        return None, None
    parts = source_id.strip().split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None


def search_advisories(client, package_name):
    """Search GitHub Advisory Database for package vulnerabilities."""
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    url = "https://api.github.com/advisories"
    params = {"affects": package_name, "per_page": 20}
    try:
        resp = client.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 422:
            return []
        else:
            logger.debug(f"Advisory search returned {resp.status_code} for {package_name}")
            return []
    except Exception as e:
        logger.debug(f"Advisory search error for {package_name}: {e}")
        return []


def check_repo_advisories(client, owner, repo):
    """Check for security advisories on a specific repo."""
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    url = f"https://api.github.com/repos/{owner}/{repo}/security-advisories"
    try:
        resp = client.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def search_nvd(client, keyword):
    """Search NVD for CVEs (fallback, 5 req/30s without key)."""
    url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    params = {"keywordSearch": keyword, "resultsPerPage": 10}
    try:
        resp = client.get(url, params=params, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            vulns = data.get("vulnerabilities", [])
            results = []
            for v in vulns:
                cve = v.get("cve", {})
                cve_id = cve.get("id", "")
                descriptions = cve.get("descriptions", [])
                desc = ""
                for d in descriptions:
                    if d.get("lang") == "en":
                        desc = d.get("value", "")
                        break
                metrics = cve.get("metrics", {})
                cvss_score = None
                severity = "UNKNOWN"
                for metric_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                    if metric_key in metrics:
                        for m in metrics[metric_key]:
                            cvss_data = m.get("cvssData", {})
                            cvss_score = cvss_data.get("baseScore")
                            severity = cvss_data.get("baseSeverity", "UNKNOWN")
                            break
                        break
                results.append({
                    "cve_id": cve_id,
                    "severity": severity,
                    "cvss_score": cvss_score,
                    "description": desc[:500],
                    "source": "nvd",
                })
            return results
        return []
    except Exception as e:
        logger.debug(f"NVD search error for {keyword}: {e}")
        return []


def run():
    ensure_table()
    agents = get_github_agents()
    if not agents:
        logger.info("No GitHub agents found")
        return

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    now = datetime.now(timezone.utc).isoformat()
    scanned = 0
    total_cves = 0
    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}

    with httpx.Client() as client:
        for agent_id, name, source_id, source_url, trust_score in agents:
            owner, repo = extract_owner_repo(source_id)
            if not owner or not repo:
                continue

            scanned += 1
            found_cves = []

            # 1. Check repo security advisories
            advisories = check_repo_advisories(client, owner, repo)
            time.sleep(GH_RATE_LIMIT)

            for adv in advisories:
                cve_id = adv.get("cve_id") or adv.get("ghsa_id", "")
                severity = (adv.get("severity") or "UNKNOWN").upper()
                cvss = None
                if adv.get("cvss", {}).get("score"):
                    cvss = adv["cvss"]["score"]
                desc = (adv.get("summary") or adv.get("description", ""))[:500]
                status = adv.get("state", "open")
                found_cves.append({
                    "cve_id": cve_id,
                    "severity": severity,
                    "cvss_score": cvss,
                    "description": desc,
                    "status": status,
                    "source": "github",
                })

            # 2. Search advisory database by package name
            pkg_advisories = search_advisories(client, repo)
            time.sleep(GH_RATE_LIMIT)

            for adv in pkg_advisories:
                cve_id = adv.get("cve_id") or adv.get("ghsa_id", "")
                if any(c["cve_id"] == cve_id for c in found_cves):
                    continue
                severity = (adv.get("severity") or "UNKNOWN").upper()
                cvss = None
                if adv.get("cvss", {}).get("score"):
                    cvss = adv["cvss"]["score"]
                desc = (adv.get("summary") or "")[:500]
                found_cves.append({
                    "cve_id": cve_id,
                    "severity": severity,
                    "cvss_score": cvss,
                    "description": desc,
                    "status": "published",
                    "source": "github_advisory",
                })

            # Store results
            for cve in found_cves:
                sev = cve["severity"]
                if sev in severity_counts:
                    severity_counts[sev] += 1
                else:
                    severity_counts["UNKNOWN"] += 1
                total_cves += 1

                try:
                    sqlite_conn.execute("""
                        INSERT INTO agent_vulnerabilities
                            (agent_id, agent_name, cve_id, severity, cvss_score,
                             description, status, source, package_name, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(agent_id, cve_id) DO UPDATE SET
                            severity = excluded.severity,
                            cvss_score = excluded.cvss_score,
                            description = excluded.description,
                            status = excluded.status,
                            fetched_at = excluded.fetched_at
                    """, (agent_id, name, cve["cve_id"], cve["severity"],
                          cve["cvss_score"], cve["description"], cve["status"],
                          cve["source"], repo, now))
                except Exception as e:
                    logger.warning(f"DB error for {name}/{cve['cve_id']}: {e}")

            if scanned % 100 == 0:
                sqlite_conn.commit()
                logger.info(f"  Progress: {scanned}/{len(agents)} agents, {total_cves} CVEs found")

    sqlite_conn.commit()
    sqlite_conn.close()

    logger.info(f"\n{'='*60}")
    logger.info(f"CVE Scanner Complete")
    logger.info(f"  Agents scanned: {scanned}")
    logger.info(f"  Total CVEs found: {total_cves}")
    logger.info(f"  Severity distribution:")
    for sev, count in sorted(severity_counts.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            logger.info(f"    {sev}: {count}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    run()
