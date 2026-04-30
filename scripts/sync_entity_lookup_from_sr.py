#!/usr/bin/env python3
"""sync_entity_lookup_from_sr.py — propagate software_registry updates → entity_lookup.

Background (sprint 2026-04-30 crawler-rate-restoration):

  - `agents` table has trigger trg_sync_entity_lookup → entity_lookup.
  - `software_registry` has *no* such trigger; its updates never reach
    entity_lookup. Net effect: 2.4M software_registry rows can refresh
    daily but entity_lookup stays stale, sitemap-lastmod stays stale,
    /safe/{slug} pages stay stale.

This script bridges that gap *honestly* — when software_registry has
real new data (newer updated_at), we copy the relevant columns into
entity_lookup. No fake "today" timestamps; updated_at = now() only when
something actually changes.

Run schedule: LaunchAgent at StartInterval=600 (every 10 minutes).
Each pass syncs up to ``BATCH_SIZE`` slugs and skips at PG-statement
timeout — the next pass picks up where we left off.

Schema note: software_registry → entity_lookup is matched on lower(slug),
with a reactive freshness window controlled by ``WINDOW_HOURS``.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [sr-sync] %(message)s",
)
log = logging.getLogger("sr-sync")

# Always use the write DSN — DATABASE_URL on this host points at a
# read-only replica, which silently rejects UPDATE.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from agentindex.db_config import get_write_dsn
    DB_DSN = get_write_dsn(fmt="psycopg2")
except Exception:
    DB_DSN = os.environ.get("NERQ_PG_WRITE_DSN") or os.environ.get("DATABASE_URL", "dbname=agentindex")
BATCH_SIZE = 5000
WINDOW_HOURS = 72  # how far back to consider sr.updated_at "new"


def run(batch_size: int = BATCH_SIZE, window_hours: int = WINDOW_HOURS,
        dry_run: bool = False) -> dict:
    started = time.time()
    conn = psycopg2.connect(
        DB_DSN,
        options=(
            "-c statement_timeout=120000 "
            "-c application_name=nerq_sr_sync "
            "-c work_mem=4MB"
        ),
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=6,
    )
    conn.autocommit = False
    cur = conn.cursor()

    # Pull software_registry rows whose updated_at is newer than the
    # matching entity_lookup row's updated_at. If no entity_lookup row
    # exists for the slug, skip (we only refresh existing rows here —
    # creation is handled by the discovery crawlers).
    cur.execute(
        """
        SELECT sr.slug, sr.trust_score, sr.trust_grade,
               sr.downloads, sr.stars, sr.description,
               sr.updated_at
        FROM software_registry sr
        JOIN entity_lookup el ON el.slug = sr.slug
        WHERE sr.updated_at > NOW() - (%s || ' hours')::interval
          AND sr.updated_at > el.updated_at
          AND el.is_active = true
        ORDER BY sr.updated_at DESC
        LIMIT %s
        """,
        (window_hours, batch_size),
    )
    rows = cur.fetchall()
    log.info(f"candidate rows: {len(rows)} (batch={batch_size}, window={window_hours}h)")

    if dry_run:
        log.info("DRY RUN — not applying")
        cur.close()
        conn.close()
        return {"candidates": len(rows), "applied": 0, "elapsed_s": time.time() - started}

    # Per-slug UPDATE in chunks. Set-based JOIN UPDATE was tried but
    # primary has post-PRIMARY-SWITCH index corruption on idx_el_name_lower
    # (e.g. "table tid (9696,8) overlaps with invalid duplicate tuple at
    # offset 15 of block 9441") — a single bad tuple in a 5K batch poisons
    # the whole transaction. Per-slug commits skip the bad rows and let
    # the rest land. Real fix is REINDEX, which is operator-scope.
    applied = 0
    failed = 0
    chunk = 50
    for offset in range(0, len(rows), chunk):
        batch = rows[offset:offset + chunk]
        slugs = [r[0] for r in batch]
        try:
            cur.execute(
                """
                UPDATE entity_lookup el
                SET trust_score = COALESCE(sr.trust_score, el.trust_score),
                    trust_grade = COALESCE(sr.trust_grade, el.trust_grade),
                    downloads   = COALESCE(sr.downloads,   el.downloads),
                    stars       = COALESCE(sr.stars,       el.stars),
                    description = COALESCE(LEFT(sr.description, 300), el.description),
                    updated_at  = NOW()
                FROM software_registry sr
                WHERE el.slug = sr.slug
                  AND el.slug = ANY(%s)
                  AND el.is_active = true
                  AND sr.updated_at > el.updated_at
                """,
                (slugs,),
            )
            applied += cur.rowcount
            conn.commit()
        except Exception as exc:
            conn.rollback()
            # Drill down to single rows to skip just the bad ones.
            for s in slugs:
                try:
                    cur.execute(
                        """
                        UPDATE entity_lookup el
                        SET trust_score = COALESCE(sr.trust_score, el.trust_score),
                            trust_grade = COALESCE(sr.trust_grade, el.trust_grade),
                            downloads   = COALESCE(sr.downloads,   el.downloads),
                            stars       = COALESCE(sr.stars,       el.stars),
                            description = COALESCE(LEFT(sr.description, 300), el.description),
                            updated_at  = NOW()
                        FROM software_registry sr
                        WHERE el.slug = sr.slug
                          AND el.slug = %s
                          AND el.is_active = true
                          AND sr.updated_at > el.updated_at
                        """,
                        (s,),
                    )
                    applied += cur.rowcount
                    conn.commit()
                except Exception:
                    failed += 1
                    conn.rollback()
        if offset and offset % 500 == 0:
            log.info(f"  progress: applied={applied} failed={failed} (offset={offset})")

    cur.close()
    conn.close()

    elapsed = time.time() - started
    log.info(f"done: applied={applied} failed={failed} elapsed={elapsed:.1f}s")
    return {"candidates": len(rows), "applied": applied, "failed": failed, "elapsed_s": elapsed}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, default=BATCH_SIZE)
    p.add_argument("--window-hours", type=int, default=WINDOW_HOURS)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    result = run(batch_size=args.batch, window_hours=args.window_hours,
                 dry_run=args.dry_run)
    return 0 if result.get("applied", 0) >= 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
