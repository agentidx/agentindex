#!/usr/bin/env python3
"""
Nerq Deep Enrichment — Auto-trigger deeper enrichment for high-velocity entities.
Entities with >=10 citations/day but shallow data get re-enriched.

Run: python3 scripts/yield_deep_enrichment.py [--dry-run] [--limit N]
"""

import json
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime

HISTORY_DB = os.path.expanduser("~/agentindex/data/reach_history.db")
PSQL = "/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql"
PG_PRIMARY = os.environ.get("NERQ_PG_PRIMARY", "100.119.193.70")
LOG_DIR = os.path.expanduser("~/agentindex/logs")

CITATION_THRESHOLD = 10  # min citations/24h to trigger
MAX_PER_DAY = 200
RECENCY_DAYS = 7  # don't re-enrich within 7 days

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler(os.path.join(LOG_DIR, "yield_deep_enrichment.log")),
                              logging.StreamHandler()])
log = logging.getLogger("deep_enrich")


def _psql(query, timeout=10):
    try:
        r = subprocess.run([PSQL, "-h", PG_PRIMARY, "-U", "anstudio", "-d", "agentindex", "-t", "-A", "-F", "|", "-c", query],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        log.warning(f"psql error: {e}")
        return ""


def _psql_exec(query, timeout=10):
    try:
        subprocess.run([PSQL, "-h", PG_PRIMARY, "-U", "anstudio", "-d", "agentindex", "-c", query],
                       capture_output=True, text=True, timeout=timeout)
        return True
    except Exception:
        return False


def run(dry_run=False, limit=None):
    limit = limit or MAX_PER_DAY
    log.info(f"Deep Enrichment — dry_run={dry_run}, limit={limit}")

    # Ensure table
    _psql_exec("""
        CREATE TABLE IF NOT EXISTS yield_deep_enrichments (
            id SERIAL PRIMARY KEY,
            entity_slug TEXT NOT NULL,
            registry TEXT,
            citations_before INT,
            depth_before INT,
            depth_after INT,
            triggered_at TIMESTAMPTZ DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)

    # Get high-velocity entities from yield_snapshots
    hist = sqlite3.connect(HISTORY_DB)
    latest = hist.execute("SELECT MAX(snapshot_ts) FROM yield_snapshots WHERE granularity='entity'").fetchone()[0]
    if not latest:
        log.info("No yield snapshots found. Run yield_tracker.py first.")
        hist.close()
        return

    candidates = hist.execute("""
        SELECT key, citations_count, metadata FROM yield_snapshots
        WHERE granularity='entity' AND snapshot_ts=? AND citations_count >= ?
        ORDER BY citations_count DESC
    """, (latest, CITATION_THRESHOLD)).fetchall()
    hist.close()

    log.info(f"Candidates with >={CITATION_THRESHOLD} citations: {len(candidates)}")

    # Get depth info from PostgreSQL
    slugs_str = ",".join(f"'{s[0].replace(chr(39), '')}'" for s in candidates[:500])
    if not slugs_str:
        log.info("No candidates.")
        return

    # Calculate depth: count non-null important fields
    depth_query = f"""
        SELECT slug, registry,
            (CASE WHEN description IS NOT NULL AND description != '' THEN 1 ELSE 0 END
             + CASE WHEN trust_score IS NOT NULL THEN 1 ELSE 0 END
             + CASE WHEN security_score IS NOT NULL THEN 1 ELSE 0 END
             + CASE WHEN popularity_score IS NOT NULL THEN 1 ELSE 0 END
             + CASE WHEN author IS NOT NULL AND author != '' AND author != 'Unknown' THEN 1 ELSE 0 END
             + CASE WHEN homepage_url IS NOT NULL AND homepage_url != '' THEN 1 ELSE 0 END
             + CASE WHEN latest_version IS NOT NULL AND latest_version != '' THEN 1 ELSE 0 END
             + CASE WHEN enriched_at IS NOT NULL THEN 1 ELSE 0 END
            ) as depth,
            enriched_at
        FROM software_registry
        WHERE slug IN ({slugs_str})
        ORDER BY slug
    """
    depth_out = _psql(depth_query)
    depth_map = {}
    for line in depth_out.split("\n"):
        if "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) >= 4:
            slug = parts[0].strip()
            depth_map[slug] = {
                "registry": parts[1].strip(),
                "depth": int(parts[2].strip()) if parts[2].strip().isdigit() else 0,
                "enriched_at": parts[3].strip(),
            }

    # Filter: need enrichment (depth < 6 out of 8) and not recently enriched
    to_enrich = []
    for slug, citations, meta_str in candidates:
        info = depth_map.get(slug)
        if not info:
            continue
        if info["depth"] >= 6:
            continue  # Already deep enough

        # Skip if deep-enriched recently
        recent = _psql(f"SELECT COUNT(*) FROM yield_deep_enrichments WHERE entity_slug='{slug.replace(chr(39),'')}' AND triggered_at >= NOW() - INTERVAL '{RECENCY_DAYS} days'")
        if recent.strip() not in ("", "0"):
            continue

        to_enrich.append({
            "slug": slug,
            "citations": citations,
            "registry": info["registry"],
            "depth": info["depth"],
        })

    to_enrich = to_enrich[:limit]
    log.info(f"Entities to deep enrich: {len(to_enrich)}")

    enriched = 0
    for ent in to_enrich:
        if dry_run:
            log.info(f"  [DRY] {ent['slug']} ({ent['registry']}) — {ent['citations']} cit, depth {ent['depth']}/8")
            enriched += 1
            continue

        # Trigger enrichment: set enriched_at to NULL so watchdog picks it up
        _psql_exec(f"""
            UPDATE software_registry SET enriched_at = NULL
            WHERE slug = '{ent['slug'].replace(chr(39), chr(39)+chr(39))}'
            AND registry = '{ent['registry']}'
        """)

        # Log
        _psql_exec(f"""
            INSERT INTO yield_deep_enrichments (entity_slug, registry, citations_before, depth_before, triggered_at)
            VALUES ('{ent['slug'].replace(chr(39), chr(39)+chr(39))}', '{ent['registry']}', {ent['citations']}, {ent['depth']}, NOW())
        """)
        enriched += 1

    log.info(f"\n{'='*60}")
    log.info(f"DEEP ENRICHMENT REPORT")
    log.info(f"{'='*60}")
    log.info(f"High-velocity candidates:  {len(candidates)}")
    log.info(f"Need deeper data:          {len(to_enrich)}")
    log.info(f"{'Would enrich' if dry_run else 'Triggered'}:  {enriched}")
    if to_enrich:
        log.info(f"\nTop 10:")
        for ent in to_enrich[:10]:
            log.info(f"  {ent['slug']:<45} {ent['citations']:>5} cit  depth {ent['depth']}/8  [{ent['registry']}]")

    return {"candidates": len(candidates), "to_enrich": len(to_enrich), "enriched": enriched}


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    limit = None
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    run(dry_run=dry_run, limit=limit)
