#!/usr/bin/env python3
"""Smedjan daily-merge smoke canary → zarq.infrastructure_alerts.

Smedjan's daily-merge cron has been running smoke tests against the API
every 03:00 since 2026-04-28 and silently rolling back when they fail.
We discovered on 2026-05-31 morning that the smoke had been failing for
at least 5 days, ramping from base=1/8 to base=0/8 with nothing reading
the daily-merge log. This canary fixes that silence.

It reads the latest daily-merge run from
/Users/anstudio/smedjan/worker-logs/daily-merge.log, extracts the
smoke-test summary line in the form

    base=X/8 localized=Y/5 sacred-bytes=Z/N, passed=True|False

and opens / resolves a row in zarq.infrastructure_alerts depending on
the total score X+Y+Z against the configured threshold (default 18/23).
Severity grades: <THRESHOLD → critical (0/23 still maps here),
== full → resolved.

The script is idempotent: bumping probe_count + last_seen_at on
re-runs against the same still-failing daily-merge. Resolving fires
when the smoke passes again.

Run via LaunchAgent `com.zarq.smedjan-canary` at 03:30 daily (after the
daily-merge job that fires at 03:00).
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg2
except ImportError:
    sys.stderr.write("psycopg2 not installed in this venv\n")
    sys.exit(2)


DAILY_MERGE_LOG = Path(os.environ.get(
    "SMEDJAN_DAILY_MERGE_LOG",
    "/Users/anstudio/smedjan/worker-logs/daily-merge.log",
))
ALERT_DSN = os.environ.get(
    "INFRA_ALERT_DSN",
    "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio",
)
# 78% threshold = 18/23. Below this opens an alert; full pass resolves.
SMOKE_FLOOR = int(os.environ.get("SMEDJAN_SMOKE_FLOOR", "18"))

# The service-tag we use in zarq.infrastructure_alerts. Distinct from the
# other infra_healthcheck.py tags so they don't shadow each other.
SERVICE = "smedjan-daily-merge|SMOKE_BELOW_FLOOR"

SUMMARY_RE = re.compile(
    r"base=(?P<base>\d+)/(?P<base_total>\d+)\s+"
    r"localized=(?P<loc>\d+)/(?P<loc_total>\d+)\s+"
    r"sacred-bytes=(?P<sb>\d+)/(?P<sb_total>\d+),\s*passed=(?P<passed>True|False)"
)
ROLLBACK_TAG_RE = re.compile(r"Pre-run rollback tag:\s*(?P<tag>\S+)")


def parse_latest_smoke(log_path: Path) -> dict | None:
    """Return the most-recent smoke result, or None if the log is empty
    or unreadable.

    The log is append-only. We walk it from the end and stop at the
    first complete (rollback-tag, summary) pair we find — that pair is
    the latest daily-merge run.
    """
    if not log_path.exists():
        return None
    text = log_path.read_text(errors="ignore")
    # Find every summary line. The last one is the most recent.
    summaries = list(SUMMARY_RE.finditer(text))
    if not summaries:
        return None
    last_sum = summaries[-1]
    # Find the rollback tag that preceded this summary
    pre = text[: last_sum.start()]
    tag_matches = list(ROLLBACK_TAG_RE.finditer(pre))
    rollback_tag = tag_matches[-1].group("tag") if tag_matches else "(none)"
    base = int(last_sum.group("base"))
    base_total = int(last_sum.group("base_total"))
    loc = int(last_sum.group("loc"))
    loc_total = int(last_sum.group("loc_total"))
    sb = int(last_sum.group("sb"))
    sb_total = int(last_sum.group("sb_total"))
    passed = last_sum.group("passed") == "True"
    return {
        "rollback_tag": rollback_tag,
        "base": base, "base_total": base_total,
        "localized": loc, "localized_total": loc_total,
        "sacred_bytes": sb, "sacred_bytes_total": sb_total,
        "passed": passed,
        "total_ok": base + loc + sb,
        "total_max": base_total + loc_total + sb_total,
    }


def open_or_bump_alert(cur, host: str, port: int, error_msg: str,
                       severity: str) -> tuple[int, int]:
    cur.execute(
        """
        INSERT INTO zarq.infrastructure_alerts
            (host, port, service, severity, error_msg, last_seen_at, probe_count)
        VALUES (%s, %s, %s, %s, %s, now(), 1)
        ON CONFLICT (host, port, service) WHERE resolved_at IS NULL DO UPDATE
        SET last_seen_at = now(),
            probe_count  = zarq.infrastructure_alerts.probe_count + 1,
            error_msg    = EXCLUDED.error_msg,
            severity     = EXCLUDED.severity
        RETURNING id, probe_count
        """,
        (host, port, SERVICE, severity, error_msg),
    )
    return cur.fetchone()


def resolve_alert(cur, host: str, port: int) -> list[tuple]:
    cur.execute(
        """
        UPDATE zarq.infrastructure_alerts
        SET resolved_at = now()
        WHERE host=%s AND port=%s AND service=%s AND resolved_at IS NULL
        RETURNING id, probe_count, (now() - occurred_at)::text
        """,
        (host, port, SERVICE),
    )
    return cur.fetchall()


def main() -> int:
    snap = parse_latest_smoke(DAILY_MERGE_LOG)
    if snap is None:
        print(f"[{datetime.now(timezone.utc).isoformat()}] no smoke summary in {DAILY_MERGE_LOG}",
              flush=True)
        return 0

    # Sentinel host:port — daily-merge isn't a network endpoint, so we use
    # placeholders that don't collide with infra_healthcheck's TCP probes.
    host = "smedjan-canary"
    port = 0
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if snap["passed"] and snap["total_ok"] == snap["total_max"]:
        # Full pass — resolve any open alert
        closed = resolve_alert_with_conn(host, port)
        for _id, probes, dur in closed:
            print(f"[{ts}] RESOLVED smedjan smoke (was {probes} probes / {dur})", flush=True)
        print(f"[{ts}] ok       smedjan-canary  smoke={snap['total_ok']}/{snap['total_max']}",
              flush=True)
        return 0

    # Below floor — open or bump
    score = snap["total_ok"]
    max_ = snap["total_max"]
    if score == 0:
        severity = "critical"
    elif score < SMOKE_FLOOR:
        severity = "critical"
    else:
        # Between floor and max but not perfect — warning
        severity = "warning"
    if severity == "warning" and score >= SMOKE_FLOOR:
        # Above floor but not full pass — leave any prior alert as-is,
        # don't open a new one
        print(f"[{ts}] ok-degraded smedjan-canary  smoke={score}/{max_}", flush=True)
        return 0

    error_msg = (
        f"smedjan daily-merge smoke {score}/{max_} below floor {SMOKE_FLOOR}; "
        f"base={snap['base']}/{snap['base_total']} "
        f"localized={snap['localized']}/{snap['localized_total']} "
        f"sacred-bytes={snap['sacred_bytes']}/{snap['sacred_bytes_total']}; "
        f"rollback_tag={snap['rollback_tag']}"
    )
    id_, probe_count = open_or_bump_alert_with_conn(host, port, error_msg, severity)
    tag = "OPENED" if probe_count == 1 else f"ONGOING #{probe_count}"
    print(f"[{ts}] {tag:9s} smedjan-canary (severity={severity}) — {error_msg}",
          flush=True)
    return 0


def open_or_bump_alert_with_conn(host, port, error_msg, severity):
    with psycopg2.connect(ALERT_DSN, connect_timeout=4) as conn:
        with conn.cursor() as cur:
            return open_or_bump_alert(cur, host, port, error_msg, severity)


def resolve_alert_with_conn(host, port):
    with psycopg2.connect(ALERT_DSN, connect_timeout=4) as conn:
        with conn.cursor() as cur:
            return resolve_alert(cur, host, port)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        sys.stderr.write(f"smedjan_smoke_canary FAILED: {type(e).__name__}: {e}\n")
        sys.exit(1)
