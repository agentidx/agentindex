#!/usr/bin/env python3
"""
Backfill gap rows from SQLite → PostgreSQL zarq.* for Tier A tables.

Between ZARQ migration (2026-04-12 ~19:00) and dual-write activation
(2026-04-13 ~07:55), SQLite received writes that PostgreSQL didn't.
This script copies those missing rows using ON CONFLICT DO NOTHING
(idempotent — safe to re-run).

Usage:
    python3 scripts/backfill_tier_a_gap.py --dry-run   # analyze only
    python3 scripts/backfill_tier_a_gap.py              # execute backfill
"""

import argparse
import sqlite3
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SQLITE_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "agentindex", "crypto", "crypto_trust.db"
)

PG_DSN = "host=/tmp port=5432 dbname=agentindex user=anstudio"

# Table configs: (table_name, pk_columns, all_columns)
TABLES = [
    ("crypto_ndd_alerts", ("id",), [
        "id", "alert_date", "token_id", "symbol", "alert_level", "ndd",
        "market_cap_rank", "trust_grade", "trigger_signals", "message", "created_at"
    ]),
    ("crypto_price_history", ("token_id", "date"), [
        "token_id", "date", "open", "high", "low", "close", "volume",
        "market_cap", "fetched_at", "source"
    ]),
    ("crypto_ndd_daily", ("id",), [
        "id", "run_date", "token_id", "symbol", "name", "market_cap_rank",
        "trust_grade", "ndd", "signal_1", "signal_2", "signal_3", "signal_4",
        "signal_5", "signal_6", "signal_7", "alert_level", "override_triggered",
        "confirmed_distress", "has_ohlcv", "price_usd", "market_cap", "volume_24h",
        "breakdown", "calculated_at", "ndd_trend", "ndd_change_4w",
        "crash_probability", "hc_alert", "hc_streak", "bottlefish_signal", "bounce_90d"
    ]),
    ("vitality_scores", ("token_id",), [
        "token_id", "symbol", "name", "vitality_score", "vitality_grade",
        "ecosystem_gravity", "capital_commitment", "coordination_efficiency",
        "stress_resilience", "organic_momentum", "trust_score", "trust_rating",
        "confidence", "data_coverage", "computed_at"
    ]),
    ("nerq_risk_signals", ("token_id", "signal_date"), [
        "token_id", "signal_date", "btc_beta", "vol_30d", "trust_p3",
        "trust_score", "sig6_structure", "ndd_current", "ndd_min_4w",
        "p3_decay_3m", "score_decay_3m", "structural_weakness",
        "structural_strength", "risk_level", "drawdown_90d", "weeks_since_ath",
        "excess_vol", "p3_rank", "details", "created_at", "first_collapse_date",
        "price_at_collapse", "weeks_in_collapse"
    ]),
    ("crypto_pipeline_runs", ("id",), [
        "id", "run_date", "started_at", "completed_at", "steps_json",
        "status", "total_seconds"
    ]),
]


def run(dry_run=True):
    import psycopg2
    import psycopg2.extras

    sc = sqlite3.connect(SQLITE_DB)
    sc.row_factory = sqlite3.Row
    pg = psycopg2.connect(PG_DSN)

    report = []
    total_inserted = 0

    for table, pk_cols, columns in TABLES:
        cols_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        conflict_cols = ", ".join(pk_cols)

        # Count before
        pg_cur = pg.cursor()
        pg_cur.execute(f"SELECT COUNT(*) FROM zarq.{table}")
        pg_before = pg_cur.fetchone()[0]
        sq_count = sc.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        delta = sq_count - pg_before

        print(f"\n{'='*60}")
        print(f"Table: {table}")
        print(f"  SQLite: {sq_count:>10}")
        print(f"  Postgres: {pg_before:>10}")
        print(f"  Delta: {delta:>+10}")

        if delta <= 0:
            print(f"  → No gap. Skipping.")
            report.append((table, sq_count, pg_before, 0, 0))
            continue

        # Read ALL rows from SQLite
        rows = sc.execute(f"SELECT {cols_str} FROM {table}").fetchall()
        data = [tuple(row) for row in rows]
        print(f"  SQLite rows read: {len(data)}")

        if dry_run:
            print(f"  → DRY RUN: would INSERT {len(data)} rows with ON CONFLICT DO NOTHING")
            report.append((table, sq_count, pg_before, delta, 0))
            continue

        # INSERT with ON CONFLICT DO NOTHING
        sql = f"INSERT INTO zarq.{table} ({cols_str}) VALUES ({placeholders}) ON CONFLICT ({conflict_cols}) DO NOTHING"
        psycopg2.extras.execute_batch(pg_cur, sql, data, page_size=500)
        pg.commit()

        # Count after
        pg_cur.execute(f"SELECT COUNT(*) FROM zarq.{table}")
        pg_after = pg_cur.fetchone()[0]
        inserted = pg_after - pg_before

        print(f"  Postgres after: {pg_after:>10}")
        print(f"  Inserted: {inserted:>10}")
        print(f"  Skipped (dupes): {len(data) - inserted:>10}")
        total_inserted += inserted
        report.append((table, sq_count, pg_after, delta, inserted))
        pg_cur.close()

    sc.close()
    pg.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}")
    print(f"{'Table':<25} {'SQLite':>10} {'Postgres':>10} {'Gap':>8} {'Inserted':>10}")
    print("-" * 65)
    for table, sq, pg_c, gap, ins in report:
        print(f"{table:<25} {sq:>10} {pg_c:>10} {gap:>+8} {ins:>10}")
    if not dry_run:
        print(f"\nTotal rows inserted: {total_inserted}")
    print(f"\nTimestamp: {datetime.now().isoformat()}")

    return report, dry_run


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill Tier A gap rows")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, no writes")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
