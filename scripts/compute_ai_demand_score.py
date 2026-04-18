#!/usr/bin/env python3
"""
compute_ai_demand_score.py — Smedjan L3 AI Demand Signal

Aggregates preflight_analytics (SQLite ~/agentindex/logs/analytics.db) for the
last 30 days, log-normalises query counts to a 0-100 demand score, and upserts
into Postgres table public.ai_demand_scores keyed by normalised slug.

The score lets Smedjan prioritise enrichment/rollout work against entities that
AI bots actually query for today, instead of download-weighted popularity.
"""

from __future__ import annotations

import logging
import math
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import unquote

import psycopg2
from psycopg2.extras import execute_values

ANALYTICS_DB = os.environ.get(
    "SMEDJAN_ANALYTICS_DB",
    os.path.expanduser("~/agentindex/logs/analytics.db"),
)
PG_DSN = os.environ.get(
    "SMEDJAN_PG_DSN",
    "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio",
)
WINDOW_DAYS = int(os.environ.get("SMEDJAN_WINDOW_DAYS", "30"))
MIN_QUERIES = int(os.environ.get("SMEDJAN_MIN_QUERIES", "1"))

DDL = """
CREATE TABLE IF NOT EXISTS public.ai_demand_scores (
    slug             text PRIMARY KEY,
    score            real NOT NULL,
    last_30d_queries integer NOT NULL,
    computed_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ai_demand_scores_score
    ON public.ai_demand_scores (score DESC);
CREATE INDEX IF NOT EXISTS idx_ai_demand_scores_computed_at
    ON public.ai_demand_scores (computed_at);
"""

UPSERT = """
INSERT INTO public.ai_demand_scores (slug, score, last_30d_queries, computed_at)
VALUES %s
ON CONFLICT (slug) DO UPDATE SET
    score            = EXCLUDED.score,
    last_30d_queries = EXCLUDED.last_30d_queries,
    computed_at      = EXCLUDED.computed_at;
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("smedjan.ai_demand")


def normalise(raw: str | None) -> str | None:
    if raw is None:
        return None
    slug = unquote(raw).strip().lower()
    if not slug:
        return None
    return slug


def load_preflight_counts() -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    sql = (
        "SELECT target, COUNT(*) AS queries "
        "FROM preflight_analytics "
        "WHERE ts > ? AND target IS NOT NULL AND target != '' "
        "GROUP BY target"
    )
    conn = sqlite3.connect(f"file:{ANALYTICS_DB}?mode=ro", uri=True)
    try:
        rows = conn.execute(sql, (cutoff,)).fetchall()
    finally:
        conn.close()

    counts: dict[str, int] = {}
    for raw_target, n in rows:
        slug = normalise(raw_target)
        if slug is None:
            continue
        counts[slug] = counts.get(slug, 0) + int(n)
    log.info(
        "aggregated %d distinct normalised slugs from %d raw targets",
        len(counts),
        len(rows),
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
        score = round(100.0 * math.log1p(n) / denom, 2)
        rows.append((slug, score, n, now))
    log.info("scored %d slugs (max queries=%d)", len(rows), max_n)
    return rows


def upsert(rows: Iterable[tuple[str, float, int, datetime]]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    conn = psycopg2.connect(PG_DSN)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(DDL)
            execute_values(cur, UPSERT, rows, page_size=1000)
        return len(rows)
    finally:
        conn.close()


def report_join_coverage() -> None:
    conn = psycopg2.connect(PG_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '120s';")
            cur.execute("SELECT COUNT(*) FROM public.ai_demand_scores;")
            (total,) = cur.fetchone()
            # software_registry.slug is indexed; ~0.004% non-lowercase rows are
            # ignored here — direct equality uses the index.
            cur.execute(
                """
                SELECT s.registry, COUNT(DISTINCT d.slug)
                FROM public.ai_demand_scores d
                JOIN public.software_registry s ON s.slug = d.slug
                GROUP BY s.registry
                ORDER BY 2 DESC
                """
            )
            by_reg = cur.fetchall()
            matched = sum(n for _, n in by_reg)
    finally:
        conn.close()
    log.info(
        "join coverage: %d/%d demand slugs match software_registry (%.1f%%)",
        matched,
        total,
        100.0 * matched / total if total else 0.0,
    )
    for registry, n in by_reg:
        log.info("  %-20s %d", registry, n)


def main() -> int:
    counts = load_preflight_counts()
    rows = score_rows(counts)
    written = upsert(rows)
    log.info("upserted %d rows into public.ai_demand_scores", written)
    report_join_coverage()
    return 0


if __name__ == "__main__":
    sys.exit(main())
