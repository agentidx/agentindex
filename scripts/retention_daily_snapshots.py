#!/usr/bin/env python3
"""
Daily Snapshots Retention Policy — Hierarchical compression.

Keeps:
- Last 90 days: daily resolution (full data)
- 91-365 days: weekly resolution (keep Sunday, delete rest)
- >365 days: monthly resolution (keep 1st, delete rest)

Run monthly via LaunchAgent. Safe to re-run (idempotent).

Usage:
    python3 scripts/retention_daily_snapshots.py              # run retention
    python3 scripts/retention_daily_snapshots.py --dry-run     # preview only
    python3 scripts/retention_daily_snapshots.py --status      # show size info
"""

import argparse
import logging
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
PG_DSN = os.environ.get("DATABASE_URL", "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "retention.log")),
    ]
)
log = logging.getLogger("retention")


def show_status(conn):
    cur = conn.cursor()
    cur.execute("SELECT pg_size_pretty(pg_total_relation_size('daily_snapshots'))")
    size = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM daily_snapshots")
    total = cur.fetchone()[0]
    cur.execute("SELECT MIN(date), MAX(date), COUNT(DISTINCT date) FROM daily_snapshots")
    min_d, max_d, days = cur.fetchone()
    cur.close()

    print(f"\ndaily_snapshots status:")
    print(f"  Total rows: {total:,}")
    print(f"  Table size: {size}")
    print(f"  Date range: {min_d} to {max_d} ({days} distinct days)")
    print(f"  Avg rows/day: {total // max(days, 1):,}")
    print(f"  Projected annual: {total // max(days, 1) * 365:,} rows (~{total // max(days, 1) * 365 * 350 / 1e9:.0f} GB)")
    print(f"\n  Retention policy:")
    print(f"    0-90 days: daily (full)")
    print(f"    91-365 days: weekly (Sundays)")
    print(f"    >365 days: monthly (1st of month)")


def run_retention(conn, dry_run=False):
    today = date.today()
    cutoff_weekly = (today - timedelta(days=90)).isoformat()
    cutoff_monthly = (today - timedelta(days=365)).isoformat()

    cur = conn.cursor()

    # Phase 1: Compress 91-365 day data to weekly (keep Sundays only)
    cur.execute("""
        SELECT COUNT(*) FROM daily_snapshots
        WHERE date < %s AND date >= %s
        AND EXTRACT(DOW FROM date::timestamp) != 0
    """, (cutoff_weekly, cutoff_monthly))
    weekly_count = cur.fetchone()[0]
    log.info(f"Phase 1 (weekly compression): {weekly_count:,} rows to delete (91-365 days, non-Sundays)")

    if not dry_run and weekly_count > 0:
        cur.execute("""
            DELETE FROM daily_snapshots
            WHERE date < %s AND date >= %s
            AND EXTRACT(DOW FROM date::timestamp) != 0
        """, (cutoff_weekly, cutoff_monthly))
        conn.commit()
        log.info(f"  Deleted {cur.rowcount:,} rows")

    # Phase 2: Compress >365 day data to monthly (keep 1st of month only)
    cur.execute("""
        SELECT COUNT(*) FROM daily_snapshots
        WHERE date < %s
        AND EXTRACT(DAY FROM date::timestamp) != 1
    """, (cutoff_monthly,))
    monthly_count = cur.fetchone()[0]
    log.info(f"Phase 2 (monthly compression): {monthly_count:,} rows to delete (>365 days, non-1st)")

    if not dry_run and monthly_count > 0:
        cur.execute("""
            DELETE FROM daily_snapshots
            WHERE date < %s
            AND EXTRACT(DAY FROM date::timestamp) != 1
        """, (cutoff_monthly,))
        conn.commit()
        log.info(f"  Deleted {cur.rowcount:,} rows")

    # Phase 3: VACUUM if significant deletions
    if not dry_run and (weekly_count + monthly_count) > 100000:
        log.info("Running VACUUM ANALYZE...")
        old_autocommit = conn.autocommit
        conn.autocommit = True
        cur.execute("VACUUM ANALYZE daily_snapshots")
        conn.autocommit = old_autocommit
        log.info("  VACUUM complete")

    total_deleted = weekly_count + monthly_count
    log.info(f"\nRetention complete: {total_deleted:,} rows {'would be' if dry_run else ''} deleted")

    cur.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Snapshots Retention Policy")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't delete")
    parser.add_argument("--status", action="store_true", help="Show size info")
    args = parser.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)

    import psycopg2
    conn = psycopg2.connect(PG_DSN)
    cur = conn.cursor()
    cur.execute("SET statement_timeout = '300s'")
    cur.close()

    if args.status:
        show_status(conn)
    else:
        run_retention(conn, dry_run=args.dry_run)
        show_status(conn)

    conn.close()
