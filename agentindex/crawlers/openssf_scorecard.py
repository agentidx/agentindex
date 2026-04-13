"""
OpenSSF Scorecard Crawler — Saturdays 04:00
=============================================
Fetches OpenSSF Scorecard security scores for GitHub-based agents.
API: https://api.securityscorecards.dev/projects/github.com/{owner}/{repo}

Usage:
    python -m agentindex.crawlers.openssf_scorecard
"""

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy.sql import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [openssf] %(message)s")
logger = logging.getLogger("openssf")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"
API_BASE = "https://api.securityscorecards.dev/projects/github.com"

# Rate: 100 req/min → ~1.7/s, use 0.7s delay
RATE_DELAY = 0.7


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


def _extract_owner_repo(agent_name, source_url=None):
    """Extract GitHub owner/repo from agent name or source_url."""
    # Try source_url first
    if source_url:
        m = re.search(r"github\.com/([^/]+)/([^/\s?#]+)", source_url)
        if m:
            return m.group(1), m.group(2).rstrip(".git")

    # Try agent name (many are in owner/repo format)
    if "/" in agent_name:
        parts = agent_name.split("/")
        if len(parts) == 2 and len(parts[0]) > 0 and len(parts[1]) > 0:
            return parts[0], parts[1]

    return None, None


def _fetch_scorecard(owner, repo):
    """Fetch OpenSSF scorecard for a GitHub repo."""
    url = f"{API_BASE}/{owner}/{repo}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            return None  # Not scored yet
        elif resp.status_code == 429:
            logger.warning("Rate limited, sleeping 30s...")
            time.sleep(30)
            return None
        else:
            return None
    except Exception as e:
        logger.warning(f"Error fetching {owner}/{repo}: {e}")
        return None


def _store_signals(conn, agent_name, scorecard_data):
    """Store scorecard signals in external_trust_signals."""
    now = datetime.now().isoformat()
    overall = scorecard_data.get("score", 0)
    stored = 0

    # Store overall score
    from agentindex.crypto.dual_write import dual_execute
    dual_execute(conn, """
        INSERT OR REPLACE INTO external_trust_signals
        (agent_name, source, signal_name, signal_value, signal_max, raw_data, fetched_at)
        VALUES (?, 'openssf_scorecard', 'overall_score', ?, 10, ?, ?)
    """, (agent_name, overall, json.dumps({"repo": scorecard_data.get("repo", {}).get("name", "")}), now))
    stored += 1

    # Store individual check scores
    for check in scorecard_data.get("checks", []):
        check_name = check.get("name", "").lower().replace("-", "_")
        check_score = check.get("score", -1)
        if check_score < 0:
            continue
        dual_execute(conn, """
            INSERT OR REPLACE INTO external_trust_signals
            (agent_name, source, signal_name, signal_value, signal_max, raw_data, fetched_at)
            VALUES (?, 'openssf_scorecard', ?, ?, 10, ?, ?)
        """, (agent_name, check_name, check_score, json.dumps({"reason": check.get("reason", "")[:200]}), now))
        stored += 1

    return stored


def crawl(limit=5000):
    """Crawl OpenSSF Scorecard for top agents."""
    _init_db()

    from agentindex.db.models import get_session
    session = get_session()

    try:
        rows = session.execute(text("""
            SELECT name, source_url
            FROM entity_lookup
            WHERE is_active = true
              AND (source = 'github' OR source_url LIKE '%github.com%')
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()
    finally:
        session.close()

    logger.info(f"Found {len(rows)} GitHub agents to check")

    conn = sqlite3.connect(str(SQLITE_DB))
    scored = 0
    skipped = 0
    errors = 0
    scores = []

    for i, r in enumerate(rows):
        d = dict(r._mapping)
        agent_name = d["name"]
        owner, repo = _extract_owner_repo(agent_name, d.get("source_url"))

        if not owner or not repo:
            skipped += 1
            continue

        # Check if already fetched recently (within 7 days)
        existing = conn.execute(
            "SELECT fetched_at FROM external_trust_signals WHERE agent_name = ? AND source = 'openssf_scorecard' AND signal_name = 'overall_score' AND fetched_at > datetime('now', '-7 days')",
            (agent_name,)
        ).fetchone()
        if existing:
            skipped += 1
            continue

        data = _fetch_scorecard(owner, repo)
        if data and "score" in data:
            _store_signals(conn, agent_name, data)
            scores.append(data["score"])
            scored += 1
            if scored % 50 == 0:
                conn.commit()
                logger.info(f"  Progress: {scored} scored, {skipped} skipped, {errors} errors ({i+1}/{len(rows)})")
        else:
            errors += 1

        time.sleep(RATE_DELAY)

    conn.commit()

    # Distribution
    dist = {"0-2": 0, "2-4": 0, "4-6": 0, "6-8": 0, "8-10": 0}
    for s in scores:
        if s < 2: dist["0-2"] += 1
        elif s < 4: dist["2-4"] += 1
        elif s < 6: dist["4-6"] += 1
        elif s < 8: dist["6-8"] += 1
        else: dist["8-10"] += 1

    perfect = sum(1 for s in scores if s >= 9.5)

    conn.close()

    return {
        "scored": scored,
        "skipped": skipped,
        "errors": errors,
        "avg_score": round(sum(scores) / max(len(scores), 1), 2),
        "distribution": dist,
        "perfect_10": perfect,
    }


def main():
    logger.info("=" * 60)
    logger.info("OpenSSF Scorecard Crawler — starting")
    logger.info("=" * 60)

    result = crawl()

    logger.info("")
    logger.info("=" * 60)
    logger.info("OpenSSF Scorecard Crawler — COMPLETE")
    logger.info(f"  Agents scored: {result['scored']}")
    logger.info(f"  Skipped: {result['skipped']}")
    logger.info(f"  Errors: {result['errors']}")
    logger.info(f"  Average OpenSSF score: {result['avg_score']}/10")
    logger.info(f"  Distribution: {result['distribution']}")
    logger.info(f"  Perfect 10s: {result['perfect_10']}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
