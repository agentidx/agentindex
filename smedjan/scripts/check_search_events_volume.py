"""check_search_events_volume.py — daily floor check for analytics_mirror.search_events.

Context: FU-CITATION-20260422-09 / AUDIT-CITATION-20260422 finding #9.
`analytics_mirror.search_events` is the intended successor to
`requests.search_query` for "top user-search queries" intent signal. The
writer lives on branch `smedjan-factory-v0` but is not yet merged to
`main` as of 2026-04-22 — only 6 bot-probe rows have landed in the mirror.

This script queries the mirror for rows in the last 24h and warns if the
count is below a configured floor (default 50). A grace period keeps the
check dormant until 2026-04-26 so the weekly auditor has time to land
the writer merge.

Design notes
------------
* Advisory-only: exits 0 when healthy, dormant, or mirror unreachable;
  exits 1 only when the floor is breached **past** the grace date.
* Prints a single status line (no ntfy), suitable for factory worker
  logs and hand-invocation. If someone later decides to page Anders on
  breach, wire the exit-1 branch into ``ntfy_action_required.alert``
  from the caller — do not add a side-effecting ntfy call here.

Invocation
----------
    python3 -m smedjan.scripts.check_search_events_volume
    python3 -m smedjan.scripts.check_search_events_volume --floor 50
    python3 -m smedjan.scripts.check_search_events_volume --grace-until 2026-04-26
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone

from smedjan import sources


DEFAULT_FLOOR = 50
DEFAULT_GRACE_UNTIL = date(2026, 4, 26)


def _fetch_24h_count() -> int | None:
    try:
        with sources.analytics_mirror_cursor() as (_, cur):
            cur.execute(
                "SELECT count(*) FROM analytics_mirror.search_events "
                "WHERE ts >= now() - interval '24 hours'"
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0
    except sources.SourceUnavailable:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--floor", type=int, default=DEFAULT_FLOOR,
        help=f"Minimum acceptable events/24h (default: {DEFAULT_FLOOR}).",
    )
    parser.add_argument(
        "--grace-until", type=date.fromisoformat, default=DEFAULT_GRACE_UNTIL,
        help=(
            "ISO date; before this date the check is dormant (always exits 0) "
            f"to give writer rollout time (default: {DEFAULT_GRACE_UNTIL.isoformat()})."
        ),
    )
    args = parser.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    count = _fetch_24h_count()

    if count is None:
        print(
            f"[check_search_events_volume] mirror unavailable — exit 0 (advisory, not a page)",
            file=sys.stderr,
        )
        return 0

    if today < args.grace_until:
        print(
            f"[check_search_events_volume] dormant "
            f"(today={today.isoformat()} < grace_until={args.grace_until.isoformat()}) "
            f"count_24h={count} floor={args.floor}"
        )
        return 0

    if count < args.floor:
        print(
            f"[check_search_events_volume] WARN count_24h={count} < floor={args.floor} "
            f"today={today.isoformat()} — search_events writer appears dark; "
            f"see smedjan/docs/FU-CITATION-20260422-09-search-events-successor.md"
        )
        return 1

    print(
        f"[check_search_events_volume] OK count_24h={count} >= floor={args.floor} "
        f"today={today.isoformat()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
