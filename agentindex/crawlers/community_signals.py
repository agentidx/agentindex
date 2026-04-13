"""
Community Signal Aggregator — Sundays 08:00
=============================================
Collects community signals from GitHub Issues, Stack Overflow, and Reddit.

Usage:
    python -m agentindex.crawlers.community_signals
"""

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from sqlalchemy.sql import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [community] %(message)s")
logger = logging.getLogger("community")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Rate limits
GITHUB_DELAY = 0.8    # 5K/hr with token
SO_DELAY = 1.2        # 300/day
REDDIT_DELAY = 1.1    # 60/min


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
    if source_url:
        m = re.search(r"github\.com/([^/]+)/([^/\s?#]+)", source_url)
        if m:
            return m.group(1), m.group(2).rstrip(".git")
    if "/" in agent_name:
        parts = agent_name.split("/")
        if len(parts) == 2 and len(parts[0]) > 0 and len(parts[1]) > 0:
            return parts[0], parts[1]
    return None, None


def _github_headers():
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


def _fetch_github_issues(owner, repo):
    """Fetch GitHub issue stats for a repo."""
    try:
        # Get open issues count
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=_github_headers(), timeout=15
        )
        if resp.status_code != 200:
            return None

        repo_data = resp.json()
        open_issues = repo_data.get("open_issues_count", 0)

        # Get closed issues in last 30 days
        since = (datetime.now() - timedelta(days=30)).isoformat()
        resp2 = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/issues",
            params={"state": "closed", "since": since, "per_page": 100},
            headers=_github_headers(), timeout=15
        )
        closed_recent = len(resp2.json()) if resp2.status_code == 200 else 0

        # Get bug-labeled issues
        resp3 = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/issues",
            params={"labels": "bug", "state": "all", "per_page": 1},
            headers=_github_headers(), timeout=15
        )
        # GitHub returns total_count in link headers, approximate from response
        bug_count = 0
        if resp3.status_code == 200:
            # Check link header for total pages
            link = resp3.headers.get("Link", "")
            if "last" in link:
                m = re.search(r'page=(\d+)>; rel="last"', link)
                bug_count = int(m.group(1)) if m else len(resp3.json())
            else:
                bug_count = len(resp3.json())

        total_issues = open_issues + closed_recent
        close_rate = closed_recent / max(total_issues, 1)
        bug_ratio = bug_count / max(total_issues, 1) if total_issues > 0 else 0

        return {
            "open_issues": open_issues,
            "closed_30d": closed_recent,
            "bug_count": bug_count,
            "close_rate": round(close_rate, 3),
            "bug_ratio": round(bug_ratio, 3),
        }
    except Exception as e:
        logger.warning(f"GitHub issues error for {owner}/{repo}: {e}")
        return None


def _fetch_stackoverflow(tag_name):
    """Fetch Stack Overflow tag info."""
    try:
        # Clean tag name: lowercase, replace spaces with hyphens
        clean_tag = tag_name.lower().replace(" ", "-").replace("/", "-")
        resp = requests.get(
            f"https://api.stackexchange.com/2.3/tags/{clean_tag}/info",
            params={"site": "stackoverflow"},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            if items:
                return {
                    "questions": items[0].get("count", 0),
                    "tag_exists": True,
                }
        return {"questions": 0, "tag_exists": False}
    except Exception as e:
        logger.warning(f"Stack Overflow error for {tag_name}: {e}")
        return {"questions": 0, "tag_exists": False}


def _fetch_reddit_mentions(agent_name):
    """Fetch Reddit mentions of an agent."""
    try:
        # Clean search query
        query = agent_name.split("/")[-1] if "/" in agent_name else agent_name
        if len(query) < 3:
            return {"mentions": 0}

        resp = requests.get(
            "https://www.reddit.com/search.json",
            params={"q": query, "sort": "new", "limit": 25, "t": "month"},
            headers={"User-Agent": "NerqBot/1.0 (AI Agent Trust Index)"},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            return {"mentions": len(posts)}
        return {"mentions": 0}
    except Exception as e:
        logger.warning(f"Reddit error for {agent_name}: {e}")
        return {"mentions": 0}


def _store_community_signals(conn, agent_name, github_data, so_data, reddit_data):
    """Store all community signals."""
    now = datetime.now().isoformat()

    from agentindex.crypto.dual_write import dual_execute

    if github_data:
        dual_execute(conn, """
            INSERT OR REPLACE INTO external_trust_signals
            (agent_name, source, signal_name, signal_value, signal_max, raw_data, fetched_at)
            VALUES (?, 'github_community', 'issue_close_rate', ?, 1.0, ?, ?)
        """, (agent_name, github_data["close_rate"],
              json.dumps({"open": github_data["open_issues"], "closed_30d": github_data["closed_30d"]}), now))

        dual_execute(conn, """
            INSERT OR REPLACE INTO external_trust_signals
            (agent_name, source, signal_name, signal_value, signal_max, raw_data, fetched_at)
            VALUES (?, 'github_community', 'bug_ratio', ?, 1.0, ?, ?)
        """, (agent_name, github_data["bug_ratio"],
              json.dumps({"bug_count": github_data["bug_count"]}), now))

    if so_data:
        dual_execute(conn, """
            INSERT OR REPLACE INTO external_trust_signals
            (agent_name, source, signal_name, signal_value, signal_max, raw_data, fetched_at)
            VALUES (?, 'stackoverflow', 'stackoverflow_questions', ?, NULL, ?, ?)
        """, (agent_name, so_data["questions"],
              json.dumps({"tag_exists": so_data["tag_exists"]}), now))

    if reddit_data:
        dual_execute(conn, """
            INSERT OR REPLACE INTO external_trust_signals
            (agent_name, source, signal_name, signal_value, signal_max, raw_data, fetched_at)
            VALUES (?, 'reddit', 'reddit_mentions_30d', ?, NULL, NULL, ?)
        """, (agent_name, reddit_data["mentions"], now))


def crawl(limit=2000):
    """Collect community signals for top agents."""
    _init_db()

    from agentindex.db.models import get_session
    session = get_session()

    try:
        rows = session.execute(text("""
            SELECT name, source_url, source
            FROM entity_lookup
            WHERE is_active = true
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()
    finally:
        session.close()

    logger.info(f"Processing {len(rows)} agents for community signals")

    conn = sqlite3.connect(str(SQLITE_DB))
    processed = 0
    with_community = 0
    most_discussed = []

    for i, r in enumerate(rows):
        d = dict(r._mapping)
        agent_name = d["name"]

        # Check if already fetched recently
        existing = conn.execute(
            "SELECT fetched_at FROM external_trust_signals WHERE agent_name = ? AND source = 'github_community' AND fetched_at > datetime('now', '-7 days')",
            (agent_name,)
        ).fetchone()
        if existing:
            continue

        # GitHub Issues (only for GitHub agents)
        github_data = None
        owner, repo = _extract_owner_repo(agent_name, d.get("source_url"))
        if owner and repo and GITHUB_TOKEN:
            github_data = _fetch_github_issues(owner, repo)
            time.sleep(GITHUB_DELAY)

        # Stack Overflow
        short_name = agent_name.split("/")[-1] if "/" in agent_name else agent_name
        so_data = _fetch_stackoverflow(short_name)
        time.sleep(SO_DELAY)

        # Reddit
        reddit_data = _fetch_reddit_mentions(agent_name)
        time.sleep(REDDIT_DELAY)

        _store_community_signals(conn, agent_name, github_data, so_data, reddit_data)
        processed += 1

        total_signal = (so_data.get("questions", 0) or 0) + (reddit_data.get("mentions", 0) or 0)
        if total_signal > 0:
            with_community += 1
            most_discussed.append((agent_name, total_signal))

        if processed % 50 == 0:
            conn.commit()
            logger.info(f"  Progress: {processed}/{len(rows)}")

    conn.commit()
    conn.close()

    most_discussed.sort(key=lambda x: x[1], reverse=True)

    return {
        "processed": processed,
        "with_community_presence": with_community,
        "most_discussed": most_discussed[:10],
    }


def main():
    logger.info("=" * 60)
    logger.info("Community Signal Aggregator — starting")
    logger.info("=" * 60)

    result = crawl()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Community Signal Aggregator — COMPLETE")
    logger.info(f"  Agents processed: {result['processed']}")
    logger.info(f"  With community presence: {result['with_community_presence']}")
    if result["most_discussed"]:
        logger.info(f"  Most discussed:")
        for name, count in result["most_discussed"][:5]:
            logger.info(f"    {name}: {count} mentions")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
