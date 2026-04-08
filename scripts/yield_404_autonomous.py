#!/usr/bin/env python3
"""
Nerq Autonomous 404→Live Page Pipeline
Converts AI bot 404s into live pages: demand→seed→enrich→verify.

Safety caps: min 3 hits, max 150/run, max 500/day, garbage filter.
Run: python3 scripts/yield_404_autonomous.py [--dry-run] [--limit N] [hours]
"""

import json
import logging
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
HISTORY_DB = os.path.expanduser("~/agentindex/data/reach_history.db")
LOG_DIR = os.path.expanduser("~/agentindex/logs")

# Safety caps
MIN_DEMAND_HITS = 3
MAX_PER_RUN = 150
MAX_PER_DAY = 500

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler(os.path.join(LOG_DIR, "yield_404_autonomous.log")),
                              logging.StreamHandler()])
log = logging.getLogger("404auto")

# Garbage slug patterns
_GARBAGE = re.compile(
    r"^[a-f0-9]{32,}$|"       # UUID/hash
    r"^\d+$|"                  # pure numbers
    r"^[a-f0-9-]{36}$|"       # UUID with dashes
    r".{101,}|"                # too long
    r"^.{0,2}$"               # too short
)


def _psql(query, timeout=10):
    try:
        r = subprocess.run([PSQL, "-d", "agentindex", "-t", "-A", "-F", "|", "-c", query],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        log.warning(f"psql error: {e}")
        return ""


def _psql_exec(query, timeout=10):
    try:
        subprocess.run([PSQL, "-d", "agentindex", "-c", query],
                       capture_output=True, text=True, timeout=timeout)
        return True
    except Exception as e:
        log.warning(f"psql exec error: {e}")
        return False


def _is_garbage(slug):
    return bool(_GARBAGE.match(slug))


def _humanize(slug):
    """Convert slug to human-readable name."""
    name = slug.replace("-", " ").replace("_", " ").replace("/", " / ")
    # Title case but preserve known acronyms
    parts = name.split()
    result = []
    for p in parts:
        if p.upper() in ("AI", "API", "CLI", "SDK", "MCP", "LLM", "UI", "ML", "NLP", "IBM", "AWS", "GCP"):
            result.append(p.upper())
        else:
            result.append(p.capitalize())
    return " ".join(result)


def _guess_registry(slug, paths):
    """Guess registry from slug format and request paths."""
    if "/" in slug or slug.startswith("@"):
        return "npm"
    # Check paths for clues
    path_str = " ".join(paths)
    if "/token/" in path_str:
        return "crypto"
    if any(slug.endswith(s) for s in ("-js", "-ts", "-cli", "-api", "-sdk", "-node")):
        return "npm"
    if any(slug.endswith(s) for s in ("-py", "-python")):
        return "pypi"
    if any(slug.endswith(s) for s in ("-rs", "-rust")):
        return "crates"
    # Most demanded entities are GitHub repos / AI tools
    if any(kw in slug for kw in ("agent", "mcp", "llm", "gpt", "ai-", "ml-", "model", "diffusion", "transformer")):
        return "ai_tool"
    # GitHub owner-repo pattern (contains author name): fallback to generic
    # These are typically AI tools/projects that get searched
    if re.match(r"^[a-z0-9]+-[a-z]", slug) and len(slug) > 5:
        return "ai_tool"  # Safe default for demanded entities
    return None  # Can't determine — skip


def _get_daily_count():
    """Get number of entities seeded today."""
    out = _psql("""
        SELECT COUNT(*) FROM yield_404_seeding_log
        WHERE seeded_at >= NOW() - INTERVAL '24 hours'
    """)
    try:
        return int(out.strip())
    except (ValueError, AttributeError):
        return 0


def run(hours=24, dry_run=False, limit=None):
    limit = limit or MAX_PER_RUN
    log.info(f"Autonomous 404 Pipeline — {hours}h, dry_run={dry_run}, limit={limit}")

    # Ensure seeding log table exists
    _psql_exec("""
        CREATE TABLE IF NOT EXISTS yield_404_seeding_log (
            id SERIAL PRIMARY KEY,
            entity_slug TEXT NOT NULL,
            demand_hits INT,
            source_bots TEXT,
            registry TEXT,
            seeded_at TIMESTAMPTZ DEFAULT NOW(),
            enriched_at TIMESTAMPTZ,
            pages_generated BOOLEAN DEFAULT FALSE,
            first_citation_at TIMESTAMPTZ
        )
    """)

    # Check daily cap
    daily_count = _get_daily_count()
    remaining_cap = MAX_PER_DAY - daily_count
    if remaining_cap <= 0:
        log.info(f"Daily cap reached ({daily_count}/{MAX_PER_DAY}). Skipping.")
        return {"seeded": 0, "reason": "daily_cap"}

    limit = min(limit, remaining_cap)
    log.info(f"Daily cap: {daily_count}/{MAX_PER_DAY}, remaining: {remaining_cap}, limit: {limit}")

    # Step 1: Get AI bot 404s
    conn = sqlite3.connect(ANALYTICS_DB)
    rows = conn.execute(f"""
        SELECT path, bot_name, query_string, COUNT(*) as hits
        FROM requests
        WHERE status = 404 AND is_ai_bot = 1
          AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-{int(hours)} hours')
        GROUP BY path, bot_name, query_string
        ORDER BY hits DESC
    """).fetchall()
    conn.close()

    # Step 2: Extract and aggregate demand
    demand = defaultdict(lambda: {"hits": 0, "bots": defaultdict(int), "paths": set()})
    for path, bot, qs, hits in rows:
        slugs = extract_slugs(path, qs)
        for slug in (slugs or []):
            if not slug or len(slug) < 2:
                continue
            slug = slug.strip().lower()
            d = demand[slug]
            d["hits"] += hits
            d["bots"][classify_bot(bot)] += hits
            d["paths"].add(path)

    # Step 3: Filter
    filtered = {}
    skipped_reasons = defaultdict(int)
    for slug, data in demand.items():
        if data["hits"] < MIN_DEMAND_HITS:
            skipped_reasons["low_demand"] += 1
            continue
        if _is_garbage(slug):
            skipped_reasons["garbage_slug"] += 1
            continue
        filtered[slug] = data

    log.info(f"Demand: {len(demand)} entities, filtered: {len(filtered)}, skipped: {dict(skipped_reasons)}")

    # Step 4: Check which exist in DB
    existing = set()
    all_slugs = list(filtered.keys())
    for i in range(0, len(all_slugs), 500):
        batch = all_slugs[i:i+500]
        slug_list = ",".join(f"'{s.replace(chr(39), '')}'" for s in batch)
        out = _psql(f"SELECT slug FROM software_registry WHERE slug IN ({slug_list})")
        for line in out.split("\n"):
            if line.strip():
                existing.add(line.strip())

    missing = {s: d for s, d in filtered.items() if s not in existing}
    log.info(f"Already in DB: {len(existing)}, missing: {len(missing)}")

    # Step 5: Classify and seed
    to_seed = sorted(missing.items(), key=lambda x: -x[1]["hits"])[:limit]
    seeded = 0
    skipped_no_registry = 0

    for slug, data in to_seed:
        registry = _guess_registry(slug, data["paths"])
        if not registry:
            skipped_no_registry += 1
            continue

        name = _humanize(slug)
        bots_str = ", ".join(f"{b}:{c}" for b, c in sorted(data["bots"].items(), key=lambda x: -x[1]))

        if dry_run:
            log.info(f"  [DRY] Would seed: {slug} ({registry}) — {data['hits']} hits [{bots_str}]")
            seeded += 1
            continue

        # Seed in software_registry
        success = _psql_exec(f"""
            INSERT INTO software_registry (id, name, slug, registry, created_at)
            VALUES ('{uuid.uuid4()}', '{name.replace(chr(39), chr(39)+chr(39))}',
                    '{slug.replace(chr(39), chr(39)+chr(39))}', '{registry}', NOW())
            ON CONFLICT (registry, slug) DO NOTHING;
        """)
        if success:
            # Log in seeding table
            _psql_exec(f"""
                INSERT INTO yield_404_seeding_log (entity_slug, demand_hits, source_bots, registry)
                VALUES ('{slug.replace(chr(39), chr(39)+chr(39))}', {data['hits']},
                        '{bots_str.replace(chr(39), chr(39)+chr(39))}', '{registry}');
            """)
            seeded += 1

    # Step 6: Report
    log.info(f"")
    log.info(f"{'='*60}")
    log.info(f"AUTONOMOUS 404 PIPELINE REPORT")
    log.info(f"{'='*60}")
    log.info(f"AI 404 entities (24h):     {len(demand):,}")
    log.info(f"Passed filter (≥{MIN_DEMAND_HITS} hits):  {len(filtered):,}")
    log.info(f"Already in DB:             {len(existing):,}")
    log.info(f"Missing from DB:           {len(missing):,}")
    log.info(f"Skipped (no registry):     {skipped_no_registry}")
    log.info(f"{'Would seed' if dry_run else 'Seeded'}:  {seeded}")
    log.info(f"Daily cap: {daily_count + (seeded if not dry_run else 0)}/{MAX_PER_DAY}")

    if to_seed:
        log.info(f"\nTop 15 seeded/would-seed:")
        for slug, data in to_seed[:15]:
            reg = _guess_registry(slug, data["paths"]) or "?"
            bots = ", ".join(f"{b}:{c}" for b, c in sorted(data["bots"].items(), key=lambda x: -x[1])[:2])
            log.info(f"  {slug:<50} {data['hits']:>4} hits  [{reg}] [{bots}]")

    return {"demand": len(demand), "filtered": len(filtered), "missing": len(missing), "seeded": seeded}


if __name__ == "__main__":
    hours = 24
    dry_run = "--dry-run" in sys.argv
    limit_arg = None
    for arg in sys.argv[1:]:
        if arg.startswith("--limit"):
            try:
                limit_arg = int(sys.argv[sys.argv.index(arg) + 1])
            except (IndexError, ValueError):
                pass
        elif arg.isdigit():
            hours = int(arg)
    run(hours, dry_run=dry_run, limit=limit_arg)
