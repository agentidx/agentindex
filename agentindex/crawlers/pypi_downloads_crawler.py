#!/usr/bin/env python3
"""
PyPI Download Stats Crawler
============================
Fetches download stats for agents with PyPI packages.
Uses pypistats.org API (30 req/min rate limit).

Usage: python3 -m agentindex.crawlers.pypi_downloads_crawler
LaunchAgent: com.nerq.pypi-crawler — Sundays 04:30
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
    format="%(asctime)s %(levelname)s [pypi-crawler] %(message)s",
)
logger = logging.getLogger("pypi-crawler")

from agentindex.db_config import get_write_dsn
DB_URL = os.environ.get("DATABASE_URL") or get_write_dsn()
SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", "crypto", "crypto_trust.db")
RATE_LIMIT_INTERVAL = 2.1  # 30 req/min = 1 req per 2 seconds, with margin
MAX_AGENTS = 10000


def ensure_table():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS package_downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT,
            package_name TEXT NOT NULL,
            registry TEXT DEFAULT 'npm',
            weekly_downloads INTEGER,
            monthly_downloads INTEGER,
            total_downloads INTEGER,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(package_name, registry)
        )
    """)
    conn.commit()
    conn.close()


def get_pypi_agents():
    """Get agents with PyPI packages from PostgreSQL."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (source_id)
            id::text, source_id, name, trust_score
        FROM entity_lookup
        WHERE source IN ('pip', 'pypi', 'pypi_full', 'pypi_ai')
        AND source_id IS NOT NULL AND source_id != ''
        ORDER BY source_id, trust_score DESC NULLS LAST
        LIMIT %s
    """, (MAX_AGENTS,))
    rows = cur.fetchall()
    conn.close()
    logger.info(f"Found {len(rows)} PyPI agents in PostgreSQL")
    return rows


def fetch_pypi_downloads(client, package_name):
    """Fetch download stats from pypistats.org API."""
    url = f"https://pypistats.org/api/packages/{package_name}/recent"
    try:
        resp = client.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            return {
                "last_day": data.get("last_day", 0),
                "last_week": data.get("last_week", 0),
                "last_month": data.get("last_month", 0),
            }
        elif resp.status_code == 404:
            return None
        else:
            return None
    except Exception as e:
        logger.debug(f"pypistats error for {package_name}: {e}")
        return None


def run():
    ensure_table()
    agents = get_pypi_agents()
    if not agents:
        logger.info("No PyPI agents found")
        return

    # Build package -> agent_id mapping
    pkg_to_agent = {}
    packages = []
    for agent_id, source_id, name, trust_score in agents:
        pkg_name = source_id.strip().lower()
        if pkg_name and pkg_name not in pkg_to_agent:
            pkg_to_agent[pkg_name] = agent_id
            packages.append(pkg_name)

    logger.info(f"Processing {len(packages)} unique PyPI packages")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    not_found = 0
    total_weekly = 0

    with httpx.Client() as client:
        for i, pkg_name in enumerate(packages):
            stats = fetch_pypi_downloads(client, pkg_name)
            time.sleep(RATE_LIMIT_INTERVAL)

            if stats is None:
                not_found += 1
                continue

            w = stats["last_week"]
            m = stats["last_month"]
            agent_id = pkg_to_agent.get(pkg_name)

            try:
                sqlite_conn.execute("""
                    INSERT INTO package_downloads
                        (agent_id, package_name, registry, weekly_downloads, monthly_downloads, fetched_at)
                    VALUES (?, ?, 'pypi', ?, ?, ?)
                    ON CONFLICT(package_name, registry) DO UPDATE SET
                        weekly_downloads = excluded.weekly_downloads,
                        monthly_downloads = excluded.monthly_downloads,
                        fetched_at = excluded.fetched_at
                """, (agent_id, pkg_name, w, m, now))
                saved += 1
                total_weekly += w
            except Exception as e:
                logger.warning(f"DB error for {pkg_name}: {e}")

            if (i + 1) % 50 == 0:
                sqlite_conn.commit()
                logger.info(f"  Progress: {i + 1}/{len(packages)} ({saved} saved, {not_found} not found)")

    sqlite_conn.commit()

    # Report top 10
    top10 = sqlite_conn.execute("""
        SELECT package_name, weekly_downloads, monthly_downloads
        FROM package_downloads WHERE registry = 'pypi'
        ORDER BY weekly_downloads DESC LIMIT 10
    """).fetchall()

    sqlite_conn.close()

    logger.info(f"\n{'='*60}")
    logger.info(f"PyPI Downloads Crawler Complete")
    logger.info(f"  Packages processed: {len(packages)}")
    logger.info(f"  Downloads fetched: {saved}")
    logger.info(f"  Not found: {not_found}")
    logger.info(f"  Total weekly downloads: {total_weekly:,}")
    logger.info(f"\nTop 10 by weekly downloads:")
    for pkg, w, m in top10:
        logger.info(f"  {pkg}: {w:,}/week ({m:,}/month)")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    run()
