#!/usr/bin/env python3
"""
License Compliance Checker
===========================
Checks LICENSE files for agents with GitHub repos.
Classifies into PERMISSIVE, COPYLEFT, VIRAL, UNKNOWN, PROPRIETARY.

Usage: python3 -m agentindex.crawlers.license_checker
LaunchAgent: com.nerq.license-checker — Saturdays 04:00
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone

import httpx
import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [license-checker] %(message)s",
)
logger = logging.getLogger("license-checker")

DB_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/agentindex")
SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", "crypto", "crypto_trust.db")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
MAX_AGENTS = 5000
GH_RATE_LIMIT = 0.75  # seconds between requests

LICENSE_CATEGORIES = {
    # PERMISSIVE
    "MIT": "PERMISSIVE",
    "Apache-2.0": "PERMISSIVE",
    "BSD-2-Clause": "PERMISSIVE",
    "BSD-3-Clause": "PERMISSIVE",
    "ISC": "PERMISSIVE",
    "Unlicense": "PERMISSIVE",
    "0BSD": "PERMISSIVE",
    "CC0-1.0": "PERMISSIVE",
    "Zlib": "PERMISSIVE",
    "BSL-1.0": "PERMISSIVE",
    "CC-BY-4.0": "PERMISSIVE",
    "WTFPL": "PERMISSIVE",
    # COPYLEFT
    "GPL-2.0": "COPYLEFT",
    "GPL-2.0-only": "COPYLEFT",
    "GPL-2.0-or-later": "COPYLEFT",
    "GPL-3.0": "COPYLEFT",
    "GPL-3.0-only": "COPYLEFT",
    "GPL-3.0-or-later": "COPYLEFT",
    "LGPL-2.1": "COPYLEFT",
    "LGPL-2.1-only": "COPYLEFT",
    "LGPL-2.1-or-later": "COPYLEFT",
    "LGPL-3.0": "COPYLEFT",
    "LGPL-3.0-only": "COPYLEFT",
    "LGPL-3.0-or-later": "COPYLEFT",
    "MPL-2.0": "COPYLEFT",
    "EPL-2.0": "COPYLEFT",
    # VIRAL
    "AGPL-3.0": "VIRAL",
    "AGPL-3.0-only": "VIRAL",
    "AGPL-3.0-or-later": "VIRAL",
    # PROPRIETARY indicators
    "NOASSERTION": "UNKNOWN",
}

# Compliance score adjustments
COMPLIANCE_BONUS = {
    "PERMISSIVE": 10,
    "COPYLEFT": 5,
    "VIRAL": 0,
    "UNKNOWN": -5,
    "PROPRIETARY": -3,
}


def ensure_table():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT,
            agent_name TEXT,
            license_spdx TEXT,
            license_category TEXT,
            license_url TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(agent_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_license_cat ON agent_licenses(license_category)")
    conn.commit()
    conn.close()


def get_github_agents():
    """Get agents with GitHub repos."""
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
    logger.info(f"Found {len(rows)} GitHub agents to check licenses")
    return rows


def classify_license(spdx_id):
    """Classify SPDX license into category."""
    if not spdx_id:
        return "UNKNOWN"
    cat = LICENSE_CATEGORIES.get(spdx_id)
    if cat:
        return cat
    # Fuzzy match
    spdx_upper = spdx_id.upper()
    if "MIT" in spdx_upper:
        return "PERMISSIVE"
    if "APACHE" in spdx_upper:
        return "PERMISSIVE"
    if "BSD" in spdx_upper:
        return "PERMISSIVE"
    if "AGPL" in spdx_upper:
        return "VIRAL"
    if "GPL" in spdx_upper:
        return "COPYLEFT"
    if "LGPL" in spdx_upper:
        return "COPYLEFT"
    if "MPL" in spdx_upper:
        return "COPYLEFT"
    if "PROPRIETARY" in spdx_upper or "COMMERCIAL" in spdx_upper:
        return "PROPRIETARY"
    return "UNKNOWN"


def fetch_license(client, owner, repo):
    """Fetch license info from GitHub API."""
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    url = f"https://api.github.com/repos/{owner}/{repo}/license"
    try:
        resp = client.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            license_info = data.get("license", {})
            return {
                "spdx_id": license_info.get("spdx_id"),
                "name": license_info.get("name"),
                "url": data.get("html_url"),
            }
        elif resp.status_code == 404:
            return {"spdx_id": None, "name": None, "url": None}
        else:
            return None
    except Exception as e:
        logger.debug(f"License fetch error for {owner}/{repo}: {e}")
        return None


def run():
    ensure_table()
    agents = get_github_agents()
    if not agents:
        logger.info("No GitHub agents found")
        return

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    now = datetime.now(timezone.utc).isoformat()
    checked = 0
    category_counts = {"PERMISSIVE": 0, "COPYLEFT": 0, "VIRAL": 0, "UNKNOWN": 0, "PROPRIETARY": 0}

    with httpx.Client() as client:
        for agent_id, name, source_id, source_url, trust_score in agents:
            parts = source_id.strip().split("/")
            if len(parts) < 2:
                continue

            owner, repo = parts[0], parts[1]
            license_data = fetch_license(client, owner, repo)
            time.sleep(GH_RATE_LIMIT)

            if license_data is None:
                continue

            checked += 1
            spdx = license_data["spdx_id"]
            category = classify_license(spdx)
            category_counts[category] += 1

            try:
                sqlite_conn.execute("""
                    INSERT INTO agent_licenses
                        (agent_id, agent_name, license_spdx, license_category, license_url, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(agent_id) DO UPDATE SET
                        license_spdx = excluded.license_spdx,
                        license_category = excluded.license_category,
                        license_url = excluded.license_url,
                        fetched_at = excluded.fetched_at
                """, (agent_id, name, spdx, category, license_data.get("url"), now))
            except Exception as e:
                logger.warning(f"DB error for {name}: {e}")

            if checked % 100 == 0:
                sqlite_conn.commit()
                logger.info(f"  Progress: {checked}/{len(agents)} checked")

    sqlite_conn.commit()
    sqlite_conn.close()

    logger.info(f"\n{'='*60}")
    logger.info(f"License Checker Complete")
    logger.info(f"  Agents checked: {checked}")
    logger.info(f"  License distribution:")
    for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            logger.info(f"    {cat}: {count} ({count*100//max(checked,1)}%)")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    run()
