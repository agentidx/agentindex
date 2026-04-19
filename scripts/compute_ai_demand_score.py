#!/usr/bin/env python3
"""
compute_ai_demand_score.py — Smedjan L3 AI Demand Signal.

Aggregates analytics_mirror.preflight_analytics for the last 30 days,
log-normalises query counts to a 0-100 demand score, and upserts into
`smedjan.ai_demand_scores`.

Data-path under the hybrid architecture:
    READS  — analytics_mirror.preflight_analytics (mirror of Mac Studio
             analytics.db, refreshed nightly 03:30 Europe/Stockholm)
    READS  — public.software_registry (Nerq RO) for the join-coverage report
    WRITES — smedjan.ai_demand_scores (smedjan DB)

All DSNs come from ~/smedjan/config/config.toml via smedjan.sources; no
hardcoded DSNs in this file.
"""
from __future__ import annotations

import logging
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from psycopg2.extras import execute_values  # noqa: E402

from smedjan import sources  # noqa: E402

WINDOW_DAYS = int(os.environ.get("SMEDJAN_WINDOW_DAYS", "30"))
MIN_QUERIES = int(os.environ.get("SMEDJAN_MIN_QUERIES", "1"))

UPSERT_SQL = """
INSERT INTO smedjan.ai_demand_scores (slug, score, last_30d_queries, computed_at)
VALUES %s
ON CONFLICT (slug) DO UPDATE SET
    score            = EXCLUDED.score,
    last_30d_queries = EXCLUDED.last_30d_queries,
    computed_at      = EXCLUDED.computed_at;
"""

HISTORY_INSERT_SQL = """
INSERT INTO smedjan.ai_demand_history (slug, computed_at, score)
VALUES %s
ON CONFLICT (slug, computed_at) DO NOTHING;
"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smedjan.ai_demand")


def normalise(raw: str | None) -> str | None:
    if raw is None:
        return None
    slug = unquote(raw).strip().lower()
    return slug or None


def load_preflight_counts() -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    with sources.analytics_mirror_cursor() as (_, cur):
        cur.execute(
            "SELECT target, COUNT(*) AS queries "
            "FROM preflight_analytics "
            "WHERE ts > %s AND target IS NOT NULL AND target != '' "
            "GROUP BY target",
            (cutoff,),
        )
        rows = cur.fetchall()

    counts: dict[str, int] = {}
    for raw_target, n in rows:
        slug = normalise(raw_target)
        if slug is None:
            continue
        counts[slug] = counts.get(slug, 0) + int(n)
    log.info(
        "aggregated %d distinct normalised slugs from %d raw mirror rows",
        len(counts), len(rows),
    )
    return counts


def score_rows(counts: dict[str, int]) -> list[tuple[str, float, int, datetime]]:
    if not counts:
        return []
    max_n = max(counts.values())
    denom = math.log1p(max_n) or 1.0
    now = datetime.now(timezone.utc)
    rows: list[tuple[str, float, int, datetime]] = []
    for slug, n in counts.items():
        if n < MIN_QUERIES:
            continue
        rows.append((slug, round(100.0 * math.log1p(n) / denom, 2), n, now))
    log.info("scored %d slugs (max queries=%d)", len(rows), max_n)
    return rows


def upsert(rows: list[tuple[str, float, int, datetime]]) -> int:
    if not rows:
        return 0
    with sources.smedjan_db_cursor() as (_, cur):
        execute_values(cur, UPSERT_SQL, rows, page_size=1000)
    return len(rows)


def append_history(rows: list[tuple[str, float, int, datetime]]) -> int:
    """Snapshot every scored slug into smedjan.ai_demand_history.

    Feeds the 3σ velocity detector (smedjan.ai_demand_velocity). Append-only;
    conflict-free via (slug, computed_at) PK.
    """
    if not rows:
        return 0
    history_rows = [(slug, ts, score) for slug, score, _queries, ts in rows]
    with sources.smedjan_db_cursor() as (_, cur):
        execute_values(cur, HISTORY_INSERT_SQL, history_rows, page_size=1000)
    return len(history_rows)


def report_join_coverage() -> None:
    # Total + per-slug set from smedjan DB
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute("SELECT count(*) FROM smedjan.ai_demand_scores")
        (total,) = cur.fetchone()
        cur.execute("SELECT slug FROM smedjan.ai_demand_scores")
        demand_slugs = {r[0] for r in cur.fetchall()}
    if not demand_slugs:
        log.info("join coverage: 0 demand slugs to report")
        return

    # Registry breakdown from Nerq RO
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute("SET statement_timeout = '120s'")
        cur.execute(
            "SELECT registry, slug FROM public.software_registry "
            "WHERE slug = ANY(%s)",
            (list(demand_slugs),),
        )
        by_reg: dict[str, set[str]] = {}
        for registry, slug in cur.fetchall():
            by_reg.setdefault(registry, set()).add(slug)

    matched = sum(len(s) for s in by_reg.values())
    log.info(
        "join coverage: %d/%d demand slugs match software_registry (%.1f%%)",
        matched, total, 100.0 * matched / total if total else 0.0,
    )
    for reg, slugs in sorted(by_reg.items(), key=lambda kv: -len(kv[1])):
        log.info("  %-20s %d", reg, len(slugs))


def main() -> int:
    try:
        hrs = sources.mirror_freshness_hours()
        if hrs is not None and hrs > 48:
            log.warning("analytics_mirror is %.1fh old (> 48h threshold)", hrs)
    except sources.SourceUnavailable as e:
        log.error("cannot read mirror freshness: %s", e)
        return 1

    counts = load_preflight_counts()
    rows = score_rows(counts)
    written = upsert(rows)
    log.info("upserted %d rows into smedjan.ai_demand_scores", written)
    snapshotted = append_history(rows)
    log.info("appended %d rows into smedjan.ai_demand_history", snapshotted)
    report_join_coverage()
    # Run the 3σ surge detector AFTER the score refresh (T131). Any failure
    # here must not mask a successful score-refresh run, so we catch and log.
    try:
        from smedjan import ai_demand_velocity
        ai_demand_velocity.run()
    except Exception:  # noqa: BLE001 — velocity is advisory, never fatal
        log.exception("ai_demand_velocity run failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
