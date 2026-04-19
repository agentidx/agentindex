"""
Refresh the high-trust entity snapshot that backs
``smedjan.trust_score_crawl_coverage_30d``.

Populates ``smedjan.trust_score_snapshot`` from ``public.entity_lookup`` on
the Nerq RO replica. Reads the full set of active entities with
``trust_score_v2 >= TRUST_SCORE_MIN`` (default 80 — A-/A/A+) and upserts
them into the smedjan DB via a TRUNCATE+COPY-semantics style full refresh
(we use a staging temp table + swap-in to keep the snapshot atomic).

Invocation
----------
Run as ``python3 -m smedjan.measurement.trust_crawl_coverage_refresh``.
Designed to be invoked by a nightly timer alongside the analytics-mirror
import so the snapshot freshness tracks the crawl-volume freshness.

The view itself is live — it re-aggregates ``analytics_mirror.requests``
on every SELECT — so this script only refreshes the Nerq-side input.

Source: FU-CITATION-20260418-03.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from smedjan.sources import nerq_readonly_cursor, smedjan_db_cursor

log = logging.getLogger("smedjan.measurement.trust_crawl_coverage_refresh")

TRUST_SCORE_MIN = 80.0  # Must match the WHERE clause in the view.


def _fetch_snapshot_from_nerq() -> list[tuple[str, float, str | None, str | None]]:
    """Return (slug, trust_score_v2, trust_grade, category) for every
    active Nerq entity with trust_score_v2 >= TRUST_SCORE_MIN.
    """
    with nerq_readonly_cursor() as (_, cur):
        cur.execute(
            """
            SELECT DISTINCT ON (slug) slug, trust_score_v2, trust_grade, category
              FROM public.entity_lookup
             WHERE is_active = true
               AND slug IS NOT NULL
               AND trust_score_v2 IS NOT NULL
               AND trust_score_v2 >= %s
             ORDER BY slug, trust_score_v2 DESC
            """,
            (TRUST_SCORE_MIN,),
        )
        return cur.fetchall()


def _swap_snapshot(rows: list[tuple[str, float, str | None, str | None]]) -> int:
    """Atomically replace smedjan.trust_score_snapshot with ``rows``.

    Uses a temp staging table + TRUNCATE + INSERT inside a single
    transaction so readers never observe a half-populated snapshot.
    """
    now = datetime.now(timezone.utc)
    with smedjan_db_cursor() as (conn, cur):
        cur.execute(
            """
            CREATE TEMP TABLE _tss_staging (LIKE smedjan.trust_score_snapshot)
            ON COMMIT DROP
            """
        )
        cur.executemany(
            """
            INSERT INTO _tss_staging
                (slug, trust_score_v2, trust_grade, category, snapshot_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [(slug, score, grade, category, now) for slug, score, grade, category in rows],
        )
        cur.execute("TRUNCATE smedjan.trust_score_snapshot")
        cur.execute(
            """
            INSERT INTO smedjan.trust_score_snapshot
                (slug, trust_score_v2, trust_grade, category, snapshot_at)
            SELECT slug, trust_score_v2, trust_grade, category, snapshot_at
              FROM _tss_staging
            """
        )
        cur.execute("SELECT count(*) FROM smedjan.trust_score_snapshot")
        (written,) = cur.fetchone()
        return int(written)


def refresh() -> dict:
    rows = _fetch_snapshot_from_nerq()
    written = _swap_snapshot(rows)
    return {
        "trust_score_min": TRUST_SCORE_MIN,
        "pulled_from_nerq": len(rows),
        "written_to_smedjan": written,
    }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        summary = refresh()
    except Exception as e:  # noqa: BLE001 — top-level guard for systemd
        log.exception("trust_crawl_coverage_refresh failed: %s", e)
        return 1
    print(
        f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
        f"trust_crawl_coverage_refresh: {summary}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
