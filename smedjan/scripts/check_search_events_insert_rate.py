"""check_search_events_insert_rate.py — hourly insert-rate floor for
`logs/analytics.db` `search_events`.

Context: FU-QUERY-20260427-09 / AUDIT-QUERY-20260427 finding #9. The
sister script `check_search_events_volume.py` checks the *mirror*
(daily floor) and is the right tool for "did the nightly export
produce data?" This script is the *source* counterpart — it watches
the SQLite analytics.db that the live `/search` handler writes to,
and pages when the writer goes dark for >24h.

Why two scripts:
* mirror check tells you "the pipeline produced rows" but lags by up
  to 24h (nightly export);
* source check tells you "the writer is alive *right now*" with no
  pipeline lag — so we catch a regression within the hour rather than
  after the next 03:00 export run.

Behaviour:
* Counts rows in the last 24h window in `logs/analytics.db`.
* If the count is 0 AND the wall clock is past `--active-from`, exits 1
  (advisory page; caller wires it to ntfy if desired).
* `--ntfy` flag pages directly via
  `smedjan.scripts.ntfy_action_required.alert(Trigger.INFRA_CRITICAL)`
  — opt-in so cron callers can choose whether breach is human-page
  worthy or just a log line.
* Default active-from is the date FU-QUERY-20260427-09 was filed
  (2026-04-27). Override per task or per environment.

Invocation:
    python3 -m smedjan.scripts.check_search_events_insert_rate
    python3 -m smedjan.scripts.check_search_events_insert_rate --ntfy
    python3 -m smedjan.scripts.check_search_events_insert_rate \\
        --active-from 2026-04-29 --ntfy
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone

DEFAULT_DB = os.environ.get(
    "SMEDJAN_ANALYTICS_DB",
    "/Users/anstudio/agentindex/logs/analytics.db",
)
DEFAULT_ACTIVE_FROM = date(2026, 4, 27)
WINDOW_HOURS = 24


def _count_last_24h(db_path: str) -> int | None:
    if not os.path.exists(db_path):
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        try:
            row = conn.execute(
                "SELECT count(*) FROM search_events WHERE ts >= ?",
                (cutoff,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return None
    return int(row[0]) if row else 0


def _page_ntfy(count: int, db_path: str, window_hours: int) -> None:
    try:
        from smedjan.scripts.ntfy_action_required import Trigger, alert
    except Exception as exc:
        print(
            f"[check_search_events_insert_rate] ntfy import failed: {exc}",
            file=sys.stderr,
        )
        return
    alert(
        Trigger.INFRA_CRITICAL,
        title="search_events writer dark",
        reason=(
            f"0 inserts into {os.path.basename(db_path)} `search_events` "
            f"in the last {window_hours}h — /search instrumentation likely "
            f"un-deployed (see smedjan/docs/FU-QUERY-20260427-09-*)."
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"Path to SQLite analytics.db (default: {DEFAULT_DB}).",
    )
    parser.add_argument(
        "--active-from",
        type=date.fromisoformat,
        default=DEFAULT_ACTIVE_FROM,
        help=(
            "ISO date; before this date the check is dormant (always exits 0). "
            f"Default: {DEFAULT_ACTIVE_FROM.isoformat()}."
        ),
    )
    parser.add_argument(
        "--ntfy",
        action="store_true",
        help="On breach, page via ntfy_action_required INFRA_CRITICAL.",
    )
    args = parser.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    count = _count_last_24h(args.db)

    if count is None:
        print(
            "[check_search_events_insert_rate] db unreadable or table missing — "
            "exit 0 (advisory)",
            file=sys.stderr,
        )
        return 0

    rate_per_hour = count / WINDOW_HOURS

    if today < args.active_from:
        print(
            f"[check_search_events_insert_rate] dormant "
            f"(today={today.isoformat()} < active_from={args.active_from.isoformat()}) "
            f"count_24h={count} rate_per_hr={rate_per_hour:.2f}"
        )
        return 0

    if count == 0:
        print(
            f"[check_search_events_insert_rate] WARN count_24h=0 "
            f"rate_per_hr=0.00 db={args.db} today={today.isoformat()} — "
            "writer dark; see smedjan/docs/FU-QUERY-20260427-09-*"
        )
        if args.ntfy:
            _page_ntfy(count, args.db, WINDOW_HOURS)
        return 1

    print(
        f"[check_search_events_insert_rate] OK count_24h={count} "
        f"rate_per_hr={rate_per_hour:.2f} db={args.db} today={today.isoformat()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
