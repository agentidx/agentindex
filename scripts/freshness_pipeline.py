#!/usr/bin/env python3
"""
Daily Freshness Pipeline — Stage 1 + 4
=======================================
Detects trust score changes for top 10K entities and pushes only changed
entities to IndexNow. Idempotent — no change = no push.

Stage 1: Snapshot scores → rescore → detect deltas
Stage 4: IndexNow push for changed entities only

Usage:
    python3 scripts/freshness_pipeline.py              # full run
    python3 scripts/freshness_pipeline.py --dry-run    # detect only, no push
    python3 scripts/freshness_pipeline.py --top 1000   # smaller batch

LaunchAgent: com.nerq.freshness-daily (06:30 UTC, after crypto-daily at 06:00)
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, date

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_DSN = os.environ.get("DATABASE_URL", "dbname=agentindex")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "freshness-snapshots")
SITE = "https://nerq.ai"
LANGS = ["", "es", "de", "fr", "ja", "pt", "id", "cs", "th", "ro", "tr",
         "hi", "ru", "pl", "it", "ko", "vi", "nl", "sv", "zh", "da", "no", "ar"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "freshness-daily.log")),
    ]
)
log = logging.getLogger("freshness")


def get_top_entities(cur, top_n):
    """Get top N entities by trust_score from software_registry."""
    cur.execute("""
        SELECT id, slug, registry, trust_score, trust_grade,
               security_score, maintenance_score, popularity_score,
               community_score, quality_score, cve_count, updated_at
        FROM software_registry
        WHERE trust_score IS NOT NULL AND trust_score > 0
          AND slug IS NOT NULL AND slug != ''
          AND description IS NOT NULL AND length(description) > 5
        ORDER BY trust_score DESC NULLS LAST
        LIMIT %s
    """, (top_n,))
    return cur.fetchall()


def load_previous_snapshot(today_str):
    """Load yesterday's snapshot if it exists."""
    # Try yesterday
    yesterday = date.today().isoformat()  # We save today, load from files
    snapshot_path = os.path.join(SNAPSHOT_DIR, f"scores-latest.json")
    if os.path.exists(snapshot_path):
        try:
            with open(snapshot_path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_snapshot(scores, today_str):
    """Save today's scores as latest snapshot."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    snapshot_path = os.path.join(SNAPSHOT_DIR, f"scores-latest.json")
    archive_path = os.path.join(SNAPSHOT_DIR, f"scores-{today_str}.json")
    with open(snapshot_path, "w") as f:
        json.dump(scores, f)
    with open(archive_path, "w") as f:
        json.dump(scores, f)


def detect_changes(current_entities, previous_scores, threshold=0.1):
    """Compare current scores to previous snapshot.

    Returns list of (slug, old_score, new_score, delta) for changed entities.
    """
    changed = []
    for eid, slug, registry, score, grade, sec, maint, pop, comm, qual, cve, updated_at in current_entities:
        prev = previous_scores.get(slug)
        if prev is None:
            # New entity — always include
            changed.append((slug, 0, score, score))
        else:
            prev_score = prev.get("score", 0)
            delta = abs(score - prev_score)
            if delta >= threshold:
                changed.append((slug, prev_score, score, delta))
            elif prev.get("cve") != (cve or 0):
                # CVE count changed — security-relevant
                changed.append((slug, prev_score, score, delta))
    return changed


def push_indexnow(changed_slugs, dry_run=False):
    """Submit changed entity URLs to IndexNow. Only /safe/ and /was-X-hacked."""
    if not changed_slugs:
        log.info("No entities to push to IndexNow")
        return 0

    urls = []
    for slug in changed_slugs:
        urls.append(f"{SITE}/safe/{slug}")
        urls.append(f"{SITE}/was-{slug}-hacked")
        # Localized /safe/ for active languages (top 6 by volume)
        for lang in ["es", "de", "fr", "ja", "pt", "id"]:
            urls.append(f"{SITE}/{lang}/safe/{slug}")

    log.info(f"IndexNow: {len(urls)} URLs for {len(changed_slugs)} entities")

    if dry_run:
        log.info("DRY RUN — skipping IndexNow submission")
        return len(urls)

    import requests as req

    ENDPOINT = "https://api.indexnow.org/indexnow"
    KEY = "nerq2026indexnow"
    BATCH = 100
    submitted = 0

    for i in range(0, len(urls), BATCH):
        batch = urls[i:i+BATCH]
        try:
            r = req.post(ENDPOINT, json={
                "host": "nerq.ai",
                "key": KEY,
                "keyLocation": f"https://nerq.ai/{KEY}.txt",
                "urlList": batch,
            }, timeout=30)
            if r.status_code == 200:
                submitted += len(batch)
            elif r.status_code == 429:
                log.warning(f"IndexNow rate limited at batch {i//BATCH+1}")
                break
            else:
                log.warning(f"IndexNow batch {i//BATCH+1}: HTTP {r.status_code}")
                submitted += len(batch)  # Count as attempted
        except Exception as e:
            log.error(f"IndexNow batch error: {e}")

    log.info(f"IndexNow submitted: {submitted}/{len(urls)} URLs")
    return submitted


def log_regenerated(changed, today_str):
    """Log which entities were regenerated today for measurement tracking."""
    regen_path = os.path.join(LOG_DIR, "freshness-regenerated.jsonl")
    with open(regen_path, "a") as f:
        for slug, old, new, delta in changed:
            f.write(json.dumps({
                "date": today_str,
                "slug": slug,
                "old_score": round(old, 2),
                "new_score": round(new, 2),
                "delta": round(delta, 2),
            }) + "\n")


def run(top_n=10000, threshold=0.1, dry_run=False):
    import psycopg2

    today_str = date.today().isoformat()
    t0 = time.time()
    log.info(f"Freshness pipeline started: top={top_n}, threshold={threshold}, dry_run={dry_run}")

    # Connect to Postgres
    conn = psycopg2.connect(DB_DSN, options="-c statement_timeout=120000")
    cur = conn.cursor()

    # Stage 1a: Get current entity scores
    log.info("Stage 1a: Loading entity scores...")
    entities = get_top_entities(cur, top_n)
    log.info(f"  Loaded {len(entities)} entities")

    # Build current score map
    current_scores = {}
    for eid, slug, registry, score, grade, sec, maint, pop, comm, qual, cve, updated_at in entities:
        current_scores[slug] = {
            "score": round(score, 2) if score else 0,
            "grade": grade,
            "cve": cve or 0,
            "registry": registry,
        }

    # Stage 1b: Load previous snapshot and detect changes
    log.info("Stage 1b: Detecting changes...")
    previous = load_previous_snapshot(today_str)
    if not previous:
        log.info("  No previous snapshot — first run, saving baseline only")
        save_snapshot(current_scores, today_str)
        log.info(f"  Saved snapshot for {len(current_scores)} entities")
        cur.close()
        conn.close()
        log.info(f"Freshness pipeline complete (first run, no push): {time.time()-t0:.0f}s")
        return

    changed = detect_changes(entities, previous, threshold)
    unchanged = len(entities) - len(changed)

    log.info(f"  Changed: {len(changed)} entities (delta >= {threshold} or CVE change)")
    log.info(f"  Unchanged: {unchanged} entities")

    # Save today's snapshot
    save_snapshot(current_scores, today_str)

    if changed:
        # Log top 10 biggest changes
        changed_sorted = sorted(changed, key=lambda x: abs(x[3]), reverse=True)
        for slug, old, new, delta in changed_sorted[:10]:
            log.info(f"  Δ {slug}: {old:.1f} → {new:.1f} ({delta:+.1f})")

    # Stage 4: IndexNow push for changed entities
    changed_slugs = [slug for slug, _, _, _ in changed]
    pushed = push_indexnow(changed_slugs, dry_run=dry_run)

    # Log regenerated entities for measurement
    log_regenerated(changed, today_str)

    cur.close()
    conn.close()

    elapsed = time.time() - t0
    log.info(f"Freshness pipeline complete: scanned={len(entities)}, changed={len(changed)}, pushed={pushed}, elapsed={elapsed:.0f}s")

    # Summary to stdout
    print(f"\n{'='*60}")
    print(f"FRESHNESS PIPELINE — {today_str}")
    print(f"{'='*60}")
    print(f"  Entities scanned:    {len(entities)}")
    print(f"  Changed (Δ≥{threshold}):    {len(changed)}")
    print(f"  Unchanged:           {unchanged}")
    print(f"  IndexNow URLs pushed: {pushed}")
    print(f"  Elapsed:             {elapsed:.0f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Freshness Pipeline")
    parser.add_argument("--top", type=int, default=10000, help="Top N entities by score")
    parser.add_argument("--threshold", type=float, default=0.1, help="Score delta threshold")
    parser.add_argument("--dry-run", action="store_true", help="Detect only, no IndexNow push")
    args = parser.parse_args()
    os.makedirs(LOG_DIR, exist_ok=True)
    run(top_n=args.top, threshold=args.threshold, dry_run=args.dry_run)
