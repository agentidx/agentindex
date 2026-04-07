"""
Go Package GitHub Stars Enricher
=================================
Resolves GitHub repo URLs for Go packages and fetches stars/forks.
Rate-limited to respect GitHub API limits (5000/hr authenticated, 60/hr unauth).

Usage:
    python -m agentindex.crawlers.go_github_stars [--batch 2000] [--dry-run]
"""
import argparse
import json
import logging
import os
import re
import time

import psycopg2
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [go-stars] %(message)s")
logger = logging.getLogger("go-stars")

DB_DSN = os.environ.get("DATABASE_URL", "dbname=agentindex")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "go_stars_state.json")


def _headers():
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"total_updated": 0, "total_processed": 0}


def _save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def extract_github_repo(name: str) -> tuple:
    """Extract owner/repo from Go package name (e.g., github.com/gin-gonic/gin)."""
    m = re.match(r"github\.com/([^/]+)/([^/]+)", name)
    if m:
        return m.group(1), m.group(2)
    return None, None


def fetch_github_stats(owner: str, repo: str) -> dict:
    """Fetch stars, forks from GitHub API."""
    try:
        resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=_headers(), timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "license": (data.get("license") or {}).get("spdx_id", ""),
            }
    except Exception:
        pass
    return {}


def rescore(cur, pkg_id, stars, forks, sec, maint, comm, qual):
    """Recalculate trust_score using star-based popularity."""
    if stars >= 10000: pop = 98
    elif stars >= 1000: pop = 90
    elif stars >= 500: pop = 82
    elif stars >= 100: pop = 72
    elif stars >= 50: pop = 62
    elif stars >= 10: pop = 50
    elif stars >= 1: pop = 35
    else: pop = 0

    fb = 15 if forks >= 100 else 10 if forks >= 10 else 5 if forks >= 3 else 0
    pop = min(100, pop + fb)

    total = round((sec or 90) * 0.25 + (maint or 50) * 0.25 + pop * 0.15 + (comm or 35) * 0.15 + (qual or 30) * 0.20, 1)
    grade = ("A+" if total >= 90 else "A" if total >= 85 else "A-" if total >= 80 else
             "B+" if total >= 75 else "B" if total >= 70 else "B-" if total >= 65 else
             "C+" if total >= 60 else "C" if total >= 55 else "C-" if total >= 50 else
             "D" if total >= 40 else "F")

    cur.execute(
        "UPDATE software_registry SET stars=%s, forks=%s, trust_score=%s, trust_grade=%s, popularity_score=%s WHERE id=%s",
        (stars, forks, total, grade, round(pop, 1), pkg_id)
    )


def run(batch_size=2000, dry_run=False):
    state = _load_state()
    rate = 0.8 if GITHUB_TOKEN else 60.0  # 1.25/s with token, 1/min without

    conn = psycopg2.connect(DB_DSN, options="-c statement_timeout=30000")
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM software_registry WHERE registry='go' AND (stars IS NULL OR stars=0)")
    remaining = cur.fetchone()[0]
    logger.info(f"Go packages without stars: {remaining:,}. Token: {'yes' if GITHUB_TOKEN else 'NO'}")

    if dry_run:
        logger.info("DRY RUN"); cur.close(); conn.close(); return

    cur.execute(
        "SELECT id, name, security_score, maintenance_score, community_score, quality_score "
        "FROM software_registry WHERE registry='go' AND (stars IS NULL OR stars=0) "
        "AND name LIKE 'github.com/%%' LIMIT %s", (batch_size,)
    )
    rows = cur.fetchall()
    logger.info(f"Fetched {len(rows)} Go packages with GitHub URLs")

    updated = 0
    for i, (pkg_id, name, sec, maint, comm, qual) in enumerate(rows):
        owner, repo = extract_github_repo(name)
        if not owner:
            continue
        stats = fetch_github_stats(owner, repo)
        if stats.get("stars", 0) > 0:
            rescore(cur, pkg_id, stats["stars"], stats.get("forks", 0), sec, maint, comm, qual)
            updated += 1
        else:
            cur.execute("UPDATE software_registry SET stars=-1 WHERE id=%s AND stars IS NULL", (pkg_id,))

        if (i + 1) % 500 == 0:
            logger.info(f"  Progress: {i+1}/{len(rows)}, updated: {updated}")
        time.sleep(rate)

    state["total_processed"] = state.get("total_processed", 0) + len(rows)
    state["total_updated"] = state.get("total_updated", 0) + updated
    _save_state(state)

    cur.execute("SELECT ROUND(AVG(trust_score)::numeric,1), ROUND(STDDEV(trust_score)::numeric,1) FROM software_registry WHERE registry='go' AND trust_score IS NOT NULL")
    r = cur.fetchone()
    logger.info(f"Go scores: avg={r[0]}, stddev={r[1]}. Updated {updated}/{len(rows)}")
    cur.close(); conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=2000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(batch_size=args.batch, dry_run=args.dry_run)
