"""
Citation Tracker — Daily 09:30
===============================
Monitors external citations and references to Nerq trust scores.
Tracks: GitHub README mentions, badge displays, external referrers.

Usage:
    python -m agentindex.intelligence.citation_tracker
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [citation-tracker] %(message)s")
logger = logging.getLogger("citation-tracker")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def _init_db():
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nerq_citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_url TEXT,
            context TEXT,
            agent_referenced TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nc_type ON nerq_citations(source_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nc_url ON nerq_citations(source_url)")
    conn.commit()
    conn.close()


def _github_headers():
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


def _search_github_readmes(conn):
    """Search GitHub for READMEs that mention nerq.ai."""
    count = 0
    queries = [
        "nerq.ai in:file extension:md",
        '"Nerq Trust" in:file extension:md',
        "nerq.ai/badge in:file",
        "nerq.ai/safe in:file extension:md",
    ]

    for query in queries:
        try:
            resp = requests.get(
                "https://api.github.com/search/code",
                params={"q": query, "per_page": 30},
                headers=_github_headers(),
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", []):
                    repo_name = item.get("repository", {}).get("full_name", "")
                    file_path = item.get("path", "")
                    html_url = item.get("html_url", "")

                    # Check if already tracked
                    existing = conn.execute(
                        "SELECT id FROM nerq_citations WHERE source_url = ?",
                        (html_url,)
                    ).fetchone()
                    if not existing:
                        # Try to identify which agent is referenced
                        agent_ref = repo_name  # Best guess
                        conn.execute(
                            "INSERT INTO nerq_citations (source_type, source_url, context, agent_referenced) VALUES (?, ?, ?, ?)",
                            ("github_readme", html_url, f"{repo_name}/{file_path}"[:200], agent_ref)
                        )
                        count += 1
            elif resp.status_code == 403:
                logger.warning("GitHub API rate limited for code search")
                break

            time.sleep(2)  # Code search has lower rate limit
        except Exception as e:
            logger.warning(f"GitHub search error: {e}")

    conn.commit()
    return count


def _check_badge_referrers(conn):
    """Check for badge display referrers from our analytics/logs."""
    count = 0
    # Check if we have any nginx/access logs to parse
    log_paths = [
        Path("/var/log/nginx/access.log"),
        Path.home() / "agentindex" / "logs" / "api_access.log",
    ]
    for log_path in log_paths:
        if log_path.exists():
            try:
                with open(log_path) as f:
                    for line in f:
                        if "/badge/" in line and ".svg" in line:
                            # Extract referrer if present
                            parts = line.split('"')
                            if len(parts) >= 6:
                                referrer = parts[5] if len(parts) > 5 else "-"
                                if referrer and referrer != "-" and "nerq.ai" not in referrer:
                                    existing = conn.execute(
                                        "SELECT id FROM nerq_citations WHERE source_url = ? AND source_type = 'badge_display'",
                                        (referrer,)
                                    ).fetchone()
                                    if not existing:
                                        conn.execute(
                                            "INSERT INTO nerq_citations (source_type, source_url, context, agent_referenced) VALUES (?, ?, ?, ?)",
                                            ("badge_display", referrer, "Badge embed detected", None)
                                        )
                                        count += 1
            except Exception as e:
                logger.warning(f"Log parsing error: {e}")
    conn.commit()
    return count


def track_citations():
    """Run all citation tracking methods."""
    _init_db()
    conn = sqlite3.connect(str(SQLITE_DB))

    # GitHub README mentions
    github_new = _search_github_readmes(conn)
    logger.info(f"  New GitHub README citations: {github_new}")

    # Badge referrers
    badge_new = _check_badge_referrers(conn)
    logger.info(f"  New badge display citations: {badge_new}")

    # Totals
    total = conn.execute("SELECT COUNT(*) FROM nerq_citations").fetchone()[0]
    by_type = conn.execute(
        "SELECT source_type, COUNT(*) FROM nerq_citations GROUP BY source_type"
    ).fetchall()

    # Recent citations (last 7 days)
    recent = conn.execute(
        "SELECT COUNT(*) FROM nerq_citations WHERE first_seen > datetime('now', '-7 days')"
    ).fetchone()[0]

    conn.close()

    return {
        "new_github": github_new,
        "new_badge": badge_new,
        "total_citations": total,
        "by_type": {r[0]: r[1] for r in by_type},
        "recent_7d": recent,
    }


def main():
    logger.info("=" * 60)
    logger.info("Citation Tracker — starting")
    logger.info("=" * 60)

    result = track_citations()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Citation Tracker — COMPLETE")
    logger.info(f"  New citations: {result['new_github'] + result['new_badge']}")
    logger.info(f"  Total citations: {result['total_citations']}")
    logger.info(f"  By type: {result['by_type']}")
    logger.info(f"  Recent (7d): {result['recent_7d']}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
