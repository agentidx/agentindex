#!/usr/bin/env python3
"""
canary_monitor_l1.py — Smedjan L1 canary alert monitor.

Runs every ~2 minutes via LaunchAgent. Reads analytics.db (SQLite) and
checks three conditions, pushing to ntfy.sh/nerq-alerts when any fires.
Dedupes via a state file so Anders is not paged every tick.

Conditions
  1. gems+homebrew /safe/* 5xx count in the last 30 min ≥ 3
     (baseline 24h: 0/2,318 requests across the two registries). A floor
     of 3 avoids paging on single transient errors while any sustained
     issue trips within ~2 ticks.
  2. Whole Nerq 5xx rate in the last 30 min > 0.2 %.
     Baseline: 3 / 1,194,849 = 0.00025 %. 0.2 % is ~800× baseline and
     matches the "20 % above baseline" spirit once baseline is non-zero.
  3. analytics.db write rate in the last 5 min < 476 req/min.
     Baseline p50: 953 req/min. 476 = 50 %. Triggers on a genuine hang
     (LaunchAgent frozen, SQLite lock) without firing on normal valleys.

Environment overrides (useful for tests)
  SMEDJAN_NTFY_TOPIC   default: nerq-alerts
  SMEDJAN_ANALYTICS_DB default: ~/agentindex/logs/analytics.db
  SMEDJAN_CANARY_REGS  default: gems,homebrew   (comma-separated list)
  SMEDJAN_STATE_FILE   default: ~/agentindex/logs/smedjan-canary-state.json
  SMEDJAN_FORCE_TEST   "1" → fire a test alert and exit (ntfy plumbing check)
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

NTFY_TOPIC    = os.environ.get("SMEDJAN_NTFY_TOPIC", "nerq-alerts")
ANALYTICS_DB  = os.path.expanduser(os.environ.get("SMEDJAN_ANALYTICS_DB",
                                                  "~/agentindex/logs/analytics.db"))
STATE_FILE    = os.path.expanduser(os.environ.get("SMEDJAN_STATE_FILE",
                                                  "~/agentindex/logs/smedjan-canary-state.json"))
CANARY_REGS   = [s.strip() for s in os.environ.get("SMEDJAN_CANARY_REGS", "gems,homebrew").split(",") if s.strip()]
PG_DSN        = os.environ.get("SMEDJAN_PG_DSN",
                               "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio")

DEDUP_WINDOW_SECONDS = 30 * 60  # don't re-page for the same alert within 30 min

# Thresholds (doc above)
CANARY_5XX_FLOOR_30M      = 3
WHOLE_5XX_PCT_30M         = 0.2     # %
WRITE_RATE_MIN_PER_MIN_5M = 476

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smedjan.canary_monitor")


def _iso(delta_seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=delta_seconds)).strftime("%Y-%m-%dT%H:%M:%S")


def _ntfy(title: str, message: str, priority: str = "high", tags: str = "rotating_light") -> None:
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode(),
            headers={"Title": title, "Priority": priority, "Tags": tags},
        )
        urllib.request.urlopen(req, timeout=10)
        log.info("ntfy delivered: %s", title)
    except Exception as e:
        log.error("ntfy failed: %s", e)


def _load_state() -> dict:
    try:
        return json.loads(Path(STATE_FILE).read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(STATE_FILE).write_text(json.dumps(state, indent=2))
    except Exception as e:
        log.error("state save failed: %s", e)


def _path_slug(path: str) -> str | None:
    m = re.match(r"/safe/([^/?#]+)", path)
    if not m:
        return None
    from urllib.parse import unquote
    return unquote(m.group(1)).lower()


def _canary_slugs_set() -> set[str]:
    """Fetch gems+homebrew non-King slugs once per invocation — ~18K set, ~2 MB RAM."""
    import psycopg2
    slugs: set[str] = set()
    with psycopg2.connect(PG_DSN) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT slug FROM public.software_registry "
                "WHERE registry = ANY(%s) AND is_king = false AND enriched_at IS NOT NULL",
                (CANARY_REGS,),
            )
            slugs = {r[0].lower() for r in cur.fetchall()}
    return slugs


def check_canary_5xx(cur: sqlite3.Cursor, canary: set[str]) -> tuple[int, int]:
    """Return (5xx_count, total) for canary cohort in last 30 min."""
    cur.execute(
        "SELECT path, status FROM requests "
        "WHERE path LIKE '/safe/%' AND ts > ?",
        (_iso(30 * 60),),
    )
    c5, total = 0, 0
    for path, status in cur:
        slug = _path_slug(path)
        if slug is None or slug not in canary:
            continue
        total += 1
        if status is not None and status >= 500:
            c5 += 1
    return c5, total


def check_whole_5xx(cur: sqlite3.Cursor) -> tuple[int, int]:
    cur.execute(
        "SELECT COUNT(*), SUM(CASE WHEN status>=500 THEN 1 ELSE 0 END) "
        "FROM requests WHERE ts > ?",
        (_iso(30 * 60),),
    )
    total, c5 = cur.fetchone()
    return int(c5 or 0), int(total or 0)


def check_write_rate(cur: sqlite3.Cursor) -> int:
    """Requests recorded in the last 5 min, converted to req/min average."""
    cur.execute(
        "SELECT COUNT(*) FROM requests WHERE ts > ?",
        (_iso(5 * 60),),
    )
    n = cur.fetchone()[0]
    return n // 5


def should_page(state: dict, key: str) -> bool:
    last = state.get(key, 0)
    return (time.time() - last) >= DEDUP_WINDOW_SECONDS


def mark_paged(state: dict, key: str) -> None:
    state[key] = time.time()


def main() -> int:
    if os.environ.get("SMEDJAN_FORCE_TEST"):
        _ntfy("[SMEDJAN TEST] canary monitor alive",
              f"Probe at {datetime.now().isoformat(timespec='seconds')}. "
              "If you see this, the ntfy plumbing is live.",
              priority="default", tags="white_check_mark")
        return 0

    state = _load_state()
    log.info("monitor tick; state keys=%s", list(state.keys()))

    try:
        canary = _canary_slugs_set()
    except Exception as e:
        _ntfy("[SMEDJAN monitor] can't load canary slugs",
              f"postgres query failed: {e}", tags="warning")
        return 1
    log.info("canary slug set size=%d", len(canary))

    conn = sqlite3.connect(f"file:{ANALYTICS_DB}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        can5, can_total = check_canary_5xx(cur, canary)
        whole5, whole_total = check_whole_5xx(cur)
        wrate = check_write_rate(cur)
    finally:
        conn.close()

    whole_pct = (100.0 * whole5 / whole_total) if whole_total else 0.0
    log.info("30m: canary_5xx=%d/%d, whole_5xx=%d/%d (%.3f%%), 5m write_rate=%d/min",
             can5, can_total, whole5, whole_total, whole_pct, wrate)

    # Condition 1
    if can5 >= CANARY_5XX_FLOOR_30M:
        if should_page(state, "canary_5xx"):
            _ntfy(
                "[SMEDJAN L1] canary 5xx spike",
                f"{CANARY_REGS} /safe/* saw {can5} 5xx / {can_total} reqs in 30 min "
                f"(threshold ≥ {CANARY_5XX_FLOOR_30M}). Consider rollback: "
                "~/smedjan/runbooks/L1-rollback.md",
                priority="urgent", tags="rotating_light",
            )
            mark_paged(state, "canary_5xx")
        else:
            log.info("canary_5xx alert active but recently paged; deduped")

    # Condition 2
    if whole_pct > WHOLE_5XX_PCT_30M:
        if should_page(state, "whole_5xx"):
            _ntfy(
                "[SMEDJAN L1] whole-Nerq 5xx elevated",
                f"Whole-site 5xx at {whole_pct:.3f}% over 30 min "
                f"({whole5}/{whole_total}, threshold > {WHOLE_5XX_PCT_30M}%). "
                "Investigate ~/agentindex/logs/api_error.log",
                priority="urgent", tags="rotating_light",
            )
            mark_paged(state, "whole_5xx")
        else:
            log.info("whole_5xx alert active but recently paged; deduped")

    # Condition 3
    if wrate < WRITE_RATE_MIN_PER_MIN_5M:
        if should_page(state, "write_rate"):
            _ntfy(
                "[SMEDJAN L1] analytics write rate low",
                f"5m avg write rate {wrate} req/min < {WRITE_RATE_MIN_PER_MIN_5M}. "
                "Possible ingestion hang — check api / discovery_log writers.",
                priority="high", tags="warning",
            )
            mark_paged(state, "write_rate")
        else:
            log.info("write_rate alert active but recently paged; deduped")

    _save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
