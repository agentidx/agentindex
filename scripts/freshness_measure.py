#!/usr/bin/env python3
"""
Weekly Freshness Measurement — compares AI bot hits on recently-refreshed
entities vs stale entities to measure the freshness lift.

Usage:
    python3 scripts/freshness_measure.py
"""

import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ANALYTICS_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "analytics.db")
REGEN_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "freshness-regenerated.jsonl")


def load_regenerated_slugs(days=7):
    """Load slugs regenerated in the last N days from the JSONL log."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    slugs = set()
    if not os.path.exists(REGEN_LOG):
        return slugs
    with open(REGEN_LOG) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("date", "") >= cutoff:
                    slugs.add(entry["slug"])
            except Exception:
                pass
    return slugs


def measure():
    regen_slugs = load_regenerated_slugs(7)
    if not regen_slugs:
        print("No regenerated entities in last 7 days. Pipeline may not have run yet.")
        return

    conn = sqlite3.connect(ANALYTICS_DB)

    # Get AI bot hits on /safe/* paths in last 7 days
    rows = conn.execute("""
        SELECT REPLACE(path, '/safe/', '') as slug, bot_purpose, COUNT(*) as cnt
        FROM requests
        WHERE ts >= date('now', '-7 days')
          AND path LIKE '/safe/%' AND path NOT LIKE '/safe/%/%'
          AND bot_purpose IN ('user_triggered', 'search_index', 'training')
        GROUP BY slug, bot_purpose
    """).fetchall()

    # Split into regenerated vs stale
    regen = defaultdict(lambda: defaultdict(int))
    stale = defaultdict(lambda: defaultdict(int))

    for slug, purpose, cnt in rows:
        if slug in regen_slugs:
            regen[purpose]["hits"] += cnt
            regen[purpose]["entities"] += 1
        else:
            stale[purpose]["hits"] += cnt
            stale[purpose]["entities"] += 1

    conn.close()

    print(f"\nFreshness Lift Measurement — {date.today()}")
    print(f"Regenerated entities (7d): {len(regen_slugs)}")
    print(f"{'='*70}")
    print(f"{'Purpose':<20} {'Regen hits':>10} {'Regen N':>8} {'Regen avg':>10} {'Stale avg':>10} {'Lift':>8}")
    print(f"{'-'*70}")

    for purpose in ['user_triggered', 'search_index', 'training']:
        r_hits = regen[purpose]["hits"]
        r_n = regen[purpose]["entities"] or 1
        s_hits = stale[purpose]["hits"]
        s_n = stale[purpose]["entities"] or 1
        r_avg = r_hits / r_n
        s_avg = s_hits / s_n
        lift = r_avg / s_avg if s_avg > 0 else float('inf')
        print(f"{purpose:<20} {r_hits:>10} {r_n:>8} {r_avg:>10.1f} {s_avg:>10.1f} {lift:>7.1f}x")


if __name__ == "__main__":
    measure()
