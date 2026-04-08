#!/usr/bin/env python3
"""
Nerq 404→Enrichment Pipeline — Convert AI bot 404s into enriched pages.
Finds entities that AI bots are requesting but we don't have,
creates stub entries, and queues them for enrichment.

Run: python3 scripts/yield_404_pipeline.py [hours]
"""

import os
import re
import sqlite3
import subprocess
import sys
import uuid
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agentindex"))
from scripts.reach_dashboard import extract_slugs, classify_bot

ANALYTICS_DB = os.path.expanduser("~/agentindex/logs/analytics.db")
PSQL = "/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql"


def _psql(query, timeout=10):
    """Run a psql query and return stdout."""
    try:
        r = subprocess.run(
            [PSQL, "-d", "agentindex", "-t", "-A", "-F", "|", "-c", query],
            capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip()
    except Exception as e:
        print(f"  psql error: {e}")
        return ""


def _psql_exec(query, timeout=10):
    """Execute a psql command (INSERT/UPDATE)."""
    try:
        subprocess.run(
            [PSQL, "-d", "agentindex", "-c", query],
            capture_output=True, text=True, timeout=timeout
        )
    except Exception as e:
        print(f"  psql exec error: {e}")


def _guess_registry(slug):
    """Guess likely registry from slug format."""
    if "/" in slug:
        return "npm"  # scoped packages
    if slug.startswith("@"):
        return "npm"
    # Common patterns
    if any(slug.endswith(s) for s in ["-js", "-ts", "-cli", "-api", "-sdk"]):
        return "npm"
    if any(slug.endswith(s) for s in ["-py", "-python"]):
        return "pypi"
    if any(slug.endswith(s) for s in ["-rs", "-rust"]):
        return "crates"
    return None


def run_404_pipeline(hours=24, dry_run=False, limit=200):
    """Main 404→enrichment pipeline."""
    print(f"=== 404→Enrichment Pipeline — {hours}h ===")

    conn = sqlite3.connect(ANALYTICS_DB)

    # Get all AI bot 404s
    rows = conn.execute(f"""
        SELECT path, bot_name, query_string, COUNT(*) as hits
        FROM requests
        WHERE status = 404 AND is_ai_bot = 1
          AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-{int(hours)} hours')
        GROUP BY path, bot_name, query_string
        ORDER BY hits DESC
    """).fetchall()
    conn.close()

    # Extract slugs and aggregate
    demand = defaultdict(lambda: {"hits": 0, "bots": defaultdict(int), "paths": set()})
    for path, bot, qs, hits in rows:
        slugs = extract_slugs(path, qs)
        for slug in (slugs or []):
            if not slug or len(slug) < 2 or len(slug) > 100:
                continue
            slug = slug.strip().lower()
            d = demand[slug]
            d["hits"] += hits
            d["bots"][classify_bot(bot)] += hits
            d["paths"].add(path)

    print(f"  Found {len(demand):,} unique entities in AI 404s")

    # Check which exist in DB already
    if demand:
        all_slugs = list(demand.keys())
        existing = set()
        for i in range(0, len(all_slugs), 500):
            batch = all_slugs[i:i+500]
            slug_list = ",".join(f"'{s.replace(chr(39), '')}'" for s in batch)
            out = _psql(f"SELECT slug FROM software_registry WHERE slug IN ({slug_list})")
            for line in out.split("\n"):
                if line.strip():
                    existing.add(line.strip())

        missing = {s: d for s, d in demand.items() if s not in existing}
        in_db_not_enriched = {s: d for s, d in demand.items() if s in existing}

        print(f"  Already in DB: {len(in_db_not_enriched):,}")
        print(f"  Missing from DB: {len(missing):,}")
    else:
        missing = {}
        in_db_not_enriched = {}

    # Sort by demand (hits)
    top_missing = sorted(missing.items(), key=lambda x: -x[1]["hits"])[:limit]
    top_existing = sorted(in_db_not_enriched.items(), key=lambda x: -x[1]["hits"])[:50]

    # Create stub entries for top missing entities
    created = 0
    if not dry_run and top_missing:
        for slug, data in top_missing:
            reg = _guess_registry(slug)
            if not reg:
                continue
            name = slug.replace("-", " ").replace("/", " / ").title()
            _psql_exec(f"""
                INSERT INTO software_registry (id, name, slug, registry, trust_score, created_at)
                VALUES ('{uuid.uuid4()}', '{name.replace(chr(39), '')}', '{slug.replace(chr(39), '')}', '{reg}', NULL, NOW())
                ON CONFLICT (registry, slug) DO NOTHING;
            """)
            created += 1

    # Print report
    print(f"\n{'='*60}")
    print(f"404→ENRICHMENT REPORT — {hours}h")
    print(f"{'='*60}")
    print(f"Total AI 404 entities:  {len(demand):,}")
    print(f"Already in DB:          {len(in_db_not_enriched):,}")
    print(f"Missing from DB:        {len(missing):,}")
    if not dry_run:
        print(f"Stubs created:          {created}")
    else:
        print(f"Would create:           {min(len(top_missing), limit)} stubs (dry-run)")

    print(f"\nTop 20 demanded missing entities:")
    for slug, data in top_missing[:20]:
        bots = ", ".join(f"{b}:{c}" for b, c in sorted(data["bots"].items(), key=lambda x: -x[1])[:2])
        print(f"  {slug:<45} {data['hits']:>4} hits  [{bots}]")

    print(f"\nTop 10 in-DB entities with 404s (routing/pattern issues):")
    for slug, data in top_existing[:10]:
        paths = list(data["paths"])[:2]
        print(f"  {slug:<45} {data['hits']:>4} hits  paths: {paths}")

    return {"demand": len(demand), "missing": len(missing), "created": created}


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    dry_run = "--dry-run" in sys.argv
    run_404_pipeline(hours, dry_run=dry_run)
