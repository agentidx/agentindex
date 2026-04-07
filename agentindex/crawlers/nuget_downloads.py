"""
NuGet Download Count Enricher
==============================
Fetches totalDownloads from NuGet Search API for all NuGet packages.
Resumes from last position. Rate-limited to 1 req/s.

Usage:
    python -m agentindex.crawlers.nuget_downloads [--batch 5000] [--dry-run]
"""
import argparse
import json
import logging
import os
import time

import psycopg2
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [nuget-dl] %(message)s")
logger = logging.getLogger("nuget-dl")

DB_DSN = os.environ.get("DATABASE_URL", "dbname=agentindex")
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "nuget_downloads_state.json")
NUGET_SEARCH = "https://azuresearch-usnc.nuget.org/query"
RATE_LIMIT = 1.0  # seconds between requests


def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_offset": 0, "total_updated": 0, "total_processed": 0}


def _save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def fetch_download_count(name: str) -> int:
    """Fetch totalDownloads from NuGet Search API."""
    try:
        resp = requests.get(NUGET_SEARCH, params={"q": f"packageid:{name}", "take": 1}, timeout=8)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            if data:
                return int(data[0].get("totalDownloads", 0))
    except Exception:
        pass
    return 0


def rescore(cur, pkg_id, downloads, sec, maint, comm, qual):
    """Recalculate trust_score using download-based popularity."""
    if downloads > 10_000_000: pop = 100
    elif downloads > 1_000_000: pop = 90
    elif downloads > 100_000: pop = 75
    elif downloads > 10_000: pop = 60
    elif downloads > 1_000: pop = 45
    elif downloads > 100: pop = 30
    elif downloads > 0: pop = 15
    else: pop = 0

    total = round((sec or 90) * 0.25 + (maint or 50) * 0.25 + pop * 0.15 + (comm or 35) * 0.15 + (qual or 30) * 0.20, 1)
    grade = ("A+" if total >= 90 else "A" if total >= 85 else "A-" if total >= 80 else
             "B+" if total >= 75 else "B" if total >= 70 else "B-" if total >= 65 else
             "C+" if total >= 60 else "C" if total >= 55 else "C-" if total >= 50 else
             "D" if total >= 40 else "F")

    cur.execute(
        "UPDATE software_registry SET downloads=%s, trust_score=%s, trust_grade=%s, popularity_score=%s WHERE id=%s",
        (downloads, total, grade, round(pop, 1), pkg_id)
    )


def run(batch_size=5000, dry_run=False):
    state = _load_state()
    offset = state["last_offset"]

    conn = psycopg2.connect(DB_DSN, options="-c statement_timeout=30000")
    conn.autocommit = True
    cur = conn.cursor()

    # Count remaining
    cur.execute("SELECT COUNT(*) FROM software_registry WHERE registry='nuget' AND (downloads IS NULL OR downloads=0)")
    remaining = cur.fetchone()[0]
    logger.info(f"NuGet packages without downloads: {remaining:,}. Starting from offset {offset}.")

    if dry_run:
        logger.info("DRY RUN — not updating anything")
        cur.close()
        conn.close()
        return

    # Fetch batch
    cur.execute(
        "SELECT id, name, security_score, maintenance_score, community_score, quality_score "
        "FROM software_registry WHERE registry='nuget' AND (downloads IS NULL OR downloads=0) "
        "ORDER BY name OFFSET %s LIMIT %s",
        (0, batch_size)  # Always offset 0 since we update downloads (removes from pool)
    )
    rows = cur.fetchall()
    logger.info(f"Fetched {len(rows)} packages for this batch")

    updated = 0
    errors = 0
    for i, (pkg_id, name, sec, maint, comm, qual) in enumerate(rows):
        dl = fetch_download_count(name)
        if dl > 0:
            rescore(cur, pkg_id, dl, sec, maint, comm, qual)
            updated += 1
        else:
            # Mark as checked (set downloads=0 explicitly so we skip next time)
            # Actually downloads IS already 0/NULL so this won't help. Use -1 as sentinel.
            cur.execute("UPDATE software_registry SET downloads=-1 WHERE id=%s AND downloads IS NULL", (pkg_id,))

        errors += 0  # requests lib handles errors silently

        if (i + 1) % 1000 == 0:
            state["total_processed"] = state.get("total_processed", 0) + 1000
            state["total_updated"] = state.get("total_updated", 0) + updated
            _save_state(state)
            logger.info(f"  Progress: {i+1}/{len(rows)}, updated: {updated}, batch total: {i+1}")
            updated = 0  # Reset per-1000 counter for logging

        time.sleep(RATE_LIMIT)

    state["total_processed"] = state.get("total_processed", 0) + (len(rows) % 1000)
    state["total_updated"] = state.get("total_updated", 0) + updated
    state["last_offset"] = offset + len(rows)
    _save_state(state)

    # Report score distribution
    cur.execute("""
        SELECT ROUND(AVG(trust_score)::numeric,1), ROUND(STDDEV(trust_score)::numeric,1),
               COUNT(*) FILTER (WHERE downloads > 0), COUNT(*)
        FROM software_registry WHERE registry='nuget' AND trust_score IS NOT NULL
    """)
    r = cur.fetchone()
    logger.info(f"NuGet scores: avg={r[0]}, stddev={r[1]}, with_downloads={r[2]}/{r[3]}")

    cur.close()
    conn.close()
    logger.info(f"Batch complete. Total processed all-time: {state['total_processed']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NuGet download count enricher")
    parser.add_argument("--batch", type=int, default=5000, help="Packages per run (default 5000)")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without updating")
    args = parser.parse_args()
    run(batch_size=args.batch, dry_run=args.dry_run)
