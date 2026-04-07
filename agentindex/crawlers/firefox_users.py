"""
Firefox Add-on Daily Active Users Enricher
============================================
Fetches average_daily_users from AMO API (addons.mozilla.org/api/v5/).

Usage:
    python -m agentindex.crawlers.firefox_users [--batch 3000] [--dry-run]
"""
import argparse
import json
import logging
import os
import time

import psycopg2
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [firefox-users] %(message)s")
logger = logging.getLogger("firefox-users")

DB_DSN = os.environ.get("DATABASE_URL", "dbname=agentindex")
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "firefox_users_state.json")
AMO_API = "https://addons.mozilla.org/api/v5/addons/addon"


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


def fetch_firefox_users(slug: str) -> int:
    """Fetch average_daily_users from AMO API."""
    try:
        resp = requests.get(f"{AMO_API}/{slug}/", timeout=8,
                           headers={"User-Agent": "NerqBot/1.0 (trust indexer)"})
        if resp.status_code == 200:
            return resp.json().get("average_daily_users", 0)
    except Exception:
        pass
    return 0


def rescore(cur, pkg_id, daily_users, sec, maint, comm, qual):
    """Recalculate trust_score using daily-user-based popularity."""
    if daily_users > 1_000_000: pop = 95
    elif daily_users > 100_000: pop = 80
    elif daily_users > 10_000: pop = 65
    elif daily_users > 1_000: pop = 50
    elif daily_users > 100: pop = 35
    else: pop = 20

    total = round((sec or 90) * 0.25 + (maint or 50) * 0.25 + pop * 0.15 + (comm or 35) * 0.15 + (qual or 30) * 0.20, 1)
    grade = ("A+" if total >= 90 else "A" if total >= 85 else "A-" if total >= 80 else
             "B+" if total >= 75 else "B" if total >= 70 else "B-" if total >= 65 else
             "C+" if total >= 60 else "C" if total >= 55 else "C-" if total >= 50 else
             "D" if total >= 40 else "F")

    cur.execute(
        "UPDATE software_registry SET downloads=%s, trust_score=%s, trust_grade=%s, popularity_score=%s WHERE id=%s",
        (daily_users, total, grade, round(pop, 1), pkg_id)
    )


def run(batch_size=3000, dry_run=False):
    state = _load_state()
    conn = psycopg2.connect(DB_DSN, options="-c statement_timeout=30000")
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM software_registry WHERE registry='firefox' AND (downloads IS NULL OR downloads=0)")
    remaining = cur.fetchone()[0]
    logger.info(f"Firefox add-ons without users: {remaining:,}")

    if dry_run:
        logger.info("DRY RUN"); cur.close(); conn.close(); return

    cur.execute(
        "SELECT id, slug, security_score, maintenance_score, community_score, quality_score "
        "FROM software_registry WHERE registry='firefox' AND (downloads IS NULL OR downloads=0) LIMIT %s",
        (batch_size,)
    )
    rows = cur.fetchall()
    logger.info(f"Fetched {len(rows)} Firefox add-ons")

    updated = 0
    for i, (pkg_id, slug, sec, maint, comm, qual) in enumerate(rows):
        users = fetch_firefox_users(slug)
        if users > 0:
            rescore(cur, pkg_id, users, sec, maint, comm, qual)
            updated += 1
        else:
            cur.execute("UPDATE software_registry SET downloads=-1 WHERE id=%s AND downloads IS NULL", (pkg_id,))

        if (i + 1) % 500 == 0:
            logger.info(f"  Progress: {i+1}/{len(rows)}, updated: {updated}")
        time.sleep(1.0)

    state["total_processed"] = state.get("total_processed", 0) + len(rows)
    state["total_updated"] = state.get("total_updated", 0) + updated
    _save_state(state)

    cur.execute("SELECT ROUND(AVG(trust_score)::numeric,1), ROUND(STDDEV(trust_score)::numeric,1) FROM software_registry WHERE registry='firefox' AND trust_score IS NOT NULL")
    r = cur.fetchone()
    logger.info(f"Firefox scores: avg={r[0]}, stddev={r[1]}. Updated {updated}/{len(rows)}")
    cur.close(); conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=3000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(batch_size=args.batch, dry_run=args.dry_run)
