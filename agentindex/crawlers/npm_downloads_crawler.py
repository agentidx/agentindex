#!/usr/bin/env python3
"""
NPM Download Stats Crawler
===========================
Fetches weekly/monthly download stats for agents with npm packages.
Queries PostgreSQL for agents with source in ('npm', 'npm_full'),
then batch-fetches download stats from npm API.

Usage: python3 -m agentindex.crawlers.npm_downloads_crawler
LaunchAgent: com.nerq.npm-crawler — Sundays 04:00
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
    format="%(asctime)s %(levelname)s [npm-crawler] %(message)s",
)
logger = logging.getLogger("npm-crawler")

from agentindex.db_config import get_write_dsn
DB_URL = os.environ.get("DATABASE_URL") or get_write_dsn()
SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", "crypto", "crypto_trust.db")
BATCH_SIZE = 40   # smaller batches to avoid 429s
RATE_DELAY = 1.5  # seconds between requests
MAX_AGENTS = 10000
MAX_RETRIES = 3


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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pkg_dl_agent ON package_downloads(agent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pkg_dl_weekly ON package_downloads(weekly_downloads DESC)")
    conn.commit()
    conn.close()


def get_npm_agents():
    """Get agents with npm packages from PostgreSQL."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    # Get agents with npm source — source_id IS the package name
    cur.execute("""
        SELECT DISTINCT ON (source_id)
            id::text, source_id, name, trust_score
        FROM entity_lookup
        WHERE source IN ('npm', 'npm_full')
        AND source_id IS NOT NULL AND source_id != ''
        ORDER BY source_id, trust_score DESC NULLS LAST
        LIMIT %s
    """, (MAX_AGENTS,))
    rows = cur.fetchall()
    conn.close()
    logger.info(f"Found {len(rows)} npm agents in PostgreSQL")
    return rows


def _fetch_with_retry(client, url, label=""):
    """Fetch URL with exponential backoff on 429."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = (2 ** attempt) * 5  # 5s, 10s, 20s
                logger.warning(f"429 rate limited ({label}), waiting {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue
            elif resp.status_code == 404:
                return {}
            else:
                logger.warning(f"npm API returned {resp.status_code} for {label}")
                return {}
        except Exception as e:
            logger.warning(f"npm API error ({label}): {e}")
            return {}
    logger.warning(f"Max retries exceeded for {label}")
    return {}


def fetch_weekly_downloads(client, packages):
    """Fetch weekly downloads for a batch of packages."""
    pkg_str = ",".join(packages)
    url = f"https://api.npmjs.org/downloads/point/last-week/{pkg_str}"
    return _fetch_with_retry(client, url, f"weekly batch of {len(packages)}")


def fetch_monthly_downloads(client, packages):
    """Fetch monthly downloads for a batch of packages."""
    pkg_str = ",".join(packages)
    url = f"https://api.npmjs.org/downloads/point/last-month/{pkg_str}"
    return _fetch_with_retry(client, url, f"monthly batch of {len(packages)}")


def run():
    ensure_table()
    agents = get_npm_agents()
    if not agents:
        logger.info("No npm agents found")
        return

    # Build package -> agent_id mapping
    pkg_to_agent = {}
    packages = []
    for agent_id, source_id, name, trust_score in agents:
        pkg_name = source_id.strip()
        if pkg_name and pkg_name not in pkg_to_agent:
            pkg_to_agent[pkg_name] = agent_id
            packages.append(pkg_name)

    logger.info(f"Processing {len(packages)} unique npm packages")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    total_downloads = 0

    # Split scoped (@org/pkg) vs unscoped — scoped can't be batched
    scoped = [p for p in packages if p.startswith("@")]
    unscoped = [p for p in packages if not p.startswith("@")]
    logger.info(f"  Unscoped: {len(unscoped)}, Scoped: {len(scoped)} (fetched individually)")

    with httpx.Client() as client:
        # Process unscoped in batches
        for i in range(0, len(unscoped), BATCH_SIZE):
            batch = unscoped[i:i + BATCH_SIZE]
            weekly = fetch_weekly_downloads(client, batch)
            time.sleep(RATE_DELAY)
            monthly = fetch_monthly_downloads(client, batch)
            time.sleep(RATE_DELAY)

            for pkg_name in batch:
                w = 0
                m = 0
                # npm API returns different structure for single vs batch
                if len(batch) == 1:
                    w = weekly.get("downloads", 0) if weekly else 0
                    m = monthly.get("downloads", 0) if monthly else 0
                else:
                    pkg_data = weekly.get(pkg_name)
                    if pkg_data and isinstance(pkg_data, dict):
                        w = pkg_data.get("downloads", 0)
                    pkg_data_m = monthly.get(pkg_name)
                    if pkg_data_m and isinstance(pkg_data_m, dict):
                        m = pkg_data_m.get("downloads", 0)

                agent_id = pkg_to_agent.get(pkg_name)
                try:
                    sqlite_conn.execute("""
                        INSERT INTO package_downloads
                            (agent_id, package_name, registry, weekly_downloads, monthly_downloads, fetched_at)
                        VALUES (?, ?, 'npm', ?, ?, ?)
                        ON CONFLICT(package_name, registry) DO UPDATE SET
                            weekly_downloads = excluded.weekly_downloads,
                            monthly_downloads = excluded.monthly_downloads,
                            fetched_at = excluded.fetched_at
                    """, (agent_id, pkg_name, w, m, now))
                    saved += 1
                    total_downloads += w
                except Exception as e:
                    logger.warning(f"DB error for {pkg_name}: {e}")

            if (i // BATCH_SIZE) % 10 == 0:
                sqlite_conn.commit()
                logger.info(f"  Unscoped progress: {i + len(batch)}/{len(unscoped)}")

        # Process scoped packages one-by-one
        for idx, pkg_name in enumerate(scoped):
            weekly = fetch_weekly_downloads(client, [pkg_name])
            time.sleep(RATE_DELAY)
            monthly = fetch_monthly_downloads(client, [pkg_name])
            time.sleep(RATE_DELAY)

            w = weekly.get("downloads", 0) if weekly else 0
            m = monthly.get("downloads", 0) if monthly else 0

            agent_id = pkg_to_agent.get(pkg_name)
            try:
                sqlite_conn.execute("""
                    INSERT INTO package_downloads
                        (agent_id, package_name, registry, weekly_downloads, monthly_downloads, fetched_at)
                    VALUES (?, ?, 'npm', ?, ?, ?)
                    ON CONFLICT(package_name, registry) DO UPDATE SET
                        weekly_downloads = excluded.weekly_downloads,
                        monthly_downloads = excluded.monthly_downloads,
                        fetched_at = excluded.fetched_at
                """, (agent_id, pkg_name, w, m, now))
                saved += 1
                total_downloads += w
            except Exception as e:
                logger.warning(f"DB error for {pkg_name}: {e}")

            if idx % 100 == 0:
                sqlite_conn.commit()
                logger.info(f"  Scoped progress: {idx}/{len(scoped)}")

    sqlite_conn.commit()

    # Report top 10
    top10 = sqlite_conn.execute("""
        SELECT package_name, weekly_downloads, monthly_downloads
        FROM package_downloads WHERE registry = 'npm'
        ORDER BY weekly_downloads DESC LIMIT 10
    """).fetchall()

    sqlite_conn.close()

    logger.info(f"\n{'='*60}")
    logger.info(f"NPM Downloads Crawler Complete")
    logger.info(f"  Packages found: {len(packages)}")
    logger.info(f"  Downloads fetched: {saved}")
    logger.info(f"  Total weekly downloads: {total_downloads:,}")
    logger.info(f"\nTop 10 by weekly downloads:")
    for pkg, w, m in top10:
        logger.info(f"  {pkg}: {w:,}/week ({m:,}/month)")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    run()
