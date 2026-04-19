#!/usr/bin/env python3
"""
refresh_ai_bot_unserved_paths.py — weekly refresh of the AI-bot 404 view.

Refreshes `smedjan.ai_bot_unserved_paths` (materialised view) using a
CONCURRENT refresh so downstream readers never block. The view aggregates
the last 7 days of `analytics_mirror.requests` rows where status=404 and
is_ai_bot=1, bucketed by (bot_name, path_shape, slug).

Source audit:  AUDIT-QUERY-20260418 finding #6 (13,245 AI-bot 404s / 7d).
Consumers:     FU-QUERY-20260418-{01,02,04,05} — coverage-backfill jobs
               read this view to prioritise slugs AI crawlers actually cite.

Schedule:      weekly, driven by com.nerq.smedjan.ai_bot_unserved_refresh
               (LaunchAgent plist under smedjan/).

Exit codes:    0 on success, 1 on mirror unreachable, 2 on refresh error.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smedjan import sources  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smedjan.ai_bot_unserved_refresh")

MV = "smedjan.ai_bot_unserved_paths"


def _summarise(cur) -> dict:
    cur.execute(
        f"SELECT count(*) AS rows, "
        f"       count(DISTINCT bot_name) AS bots, "
        f"       count(DISTINCT path_shape) AS shapes, "
        f"       COALESCE(sum(hits), 0) AS total_404s, "
        f"       max(refreshed_at) AS refreshed_at "
        f"FROM {MV}"
    )
    rows, bots, shapes, total, refreshed_at = cur.fetchone()
    return {
        "rows": int(rows),
        "bots": int(bots),
        "shapes": int(shapes),
        "total_404s": int(total),
        "refreshed_at": refreshed_at.isoformat() if refreshed_at else None,
    }


def main() -> int:
    try:
        hrs = sources.mirror_freshness_hours()
    except sources.SourceUnavailable as e:
        log.error("analytics_mirror unavailable: %s", e)
        return 1
    if hrs is not None and hrs > 48:
        log.warning("analytics_mirror is %.1fh old (> 48h threshold)", hrs)

    try:
        with sources.smedjan_db_cursor() as (conn, cur):
            # CONCURRENTLY requires autocommit — open a fresh, non-tx
            # connection via SET to avoid "cannot run inside a transaction".
            conn.set_isolation_level(0)  # ISOLATION_LEVEL_AUTOCOMMIT
            log.info("refreshing %s CONCURRENTLY", MV)
            cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {MV}")
            summary = _summarise(cur)
    except Exception as e:  # noqa: BLE001
        # Fall back to non-concurrent refresh if CONCURRENTLY fails
        # (e.g. first-ever refresh needs a populated MV + unique index,
        # both provided by schema.sql, but defence in depth).
        log.warning("CONCURRENT refresh failed (%s); retrying non-concurrent", e)
        try:
            with sources.smedjan_db_cursor() as (_, cur):
                cur.execute(f"REFRESH MATERIALIZED VIEW {MV}")
                summary = _summarise(cur)
        except Exception as inner:  # noqa: BLE001
            log.error("non-concurrent refresh also failed: %s", inner)
            return 2

    log.info(
        "refreshed %s: rows=%d bots=%d shapes=%d total_404s=%d",
        MV, summary["rows"], summary["bots"], summary["shapes"], summary["total_404s"],
    )
    if summary["rows"] == 0:
        log.warning(
            "MV is empty — either analytics_mirror is stale or AI crawlers "
            "finally stopped hitting unknown paths. Investigate before "
            "declaring victory."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
