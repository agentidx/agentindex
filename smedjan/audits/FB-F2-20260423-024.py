"""FB-F2-20260423-024: freshness-refresh prep.

Determine top-5 software_registry registries by ai_demand_scores coverage,
then emit 200 oldest enriched rows in those registries.

Cross-DB: ai_demand_scores lives in the smedjan DB (Hetzner over
Tailscale); software_registry lives in the Nerq replica.  The assembly
is done in Python.

NOTE 2026-04-23: the Mac Studio local Nerq replica is rebuilding via
pg_basebackup and has been smart-shut-down; reads have been force-
redirected to the Hel replica (100.79.171.54) at the prod level via
agentindex/db_config.py.  The smedjan config.toml still points
NERQ_RO_DSN at localhost, so sources.nerq_readonly_cursor() is
currently unreachable.  To avoid blocking freshness-prep work during
the rejoin window, this audit uses an explicit psycopg2 connection to
the Hel replica with the same smedjan_readonly credentials.  Revert
to sources.nerq_readonly_cursor() once the local replica is caught up
and the smedjan config is repointed.
"""
from __future__ import annotations

import csv
import json
import os
import sys

import psycopg2

from smedjan import sources

OUT_PATH = os.path.expanduser("~/smedjan/audits/FB-F2-20260423-024.csv")

NERQ_RO_HOST = os.environ.get("NERQ_RO_HOST_OVERRIDE", "100.79.171.54")
NERQ_RO_PORT = int(os.environ.get("NERQ_RO_PORT_OVERRIDE", "5432"))
NERQ_RO_USER = "smedjan_readonly"
NERQ_RO_DB = "agentindex"


def _nerq_ro_connect():
    pw = os.environ.get("NERQ_RO_PW")
    if not pw:
        raise RuntimeError("NERQ_RO_PW not in environment")
    conn = psycopg2.connect(
        host=NERQ_RO_HOST,
        port=NERQ_RO_PORT,
        user=NERQ_RO_USER,
        dbname=NERQ_RO_DB,
        password=pw,
        connect_timeout=10,
    )
    with conn.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
    return conn


def main() -> int:
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute("SELECT slug, score FROM smedjan.ai_demand_scores")
        ads_rows = cur.fetchall()
    ads_by_slug = {slug: score for slug, score in ads_rows}
    slugs = list(ads_by_slug.keys())

    conn = _nerq_ro_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT registry, COUNT(*) AS n
                FROM software_registry
                WHERE slug = ANY(%s)
                GROUP BY registry
                ORDER BY n DESC
                LIMIT 5
                """,
                (slugs,),
            )
            top_rows = cur.fetchall()
            top5 = [r[0] for r in top_rows]
            coverage = {r[0]: int(r[1]) for r in top_rows}

            cur.execute(
                """
                SELECT slug, registry, enriched_at
                FROM software_registry
                WHERE registry = ANY(%s)
                ORDER BY registry ASC, enriched_at ASC
                LIMIT 200
                """,
                (top5,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    with open(OUT_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["slug", "registry", "enriched_at", "ai_demand_score"])
        for slug, registry, enriched_at in rows:
            score = ads_by_slug.get(slug)
            w.writerow([
                slug,
                registry,
                enriched_at.isoformat() if enriched_at else "",
                "" if score is None else score,
            ])

    evidence = {
        "row_count": len(rows),
        "top5_registries": top5,
        "top5_coverage": coverage,
        "ai_demand_scores_slug_count": len(slugs),
        "output_path": OUT_PATH,
        "nerq_ro_host_used": NERQ_RO_HOST,
    }
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
