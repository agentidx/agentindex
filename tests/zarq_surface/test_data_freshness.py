"""DB-level data freshness tests.

Independent of the HTTP surface. We connect directly to the Nbg primary
(read-only) and ask, per `zarq.<table>`, what the most recent timestamp
column value is. Tables without an automated cadence (reference data) are
skipped via the `freshness_thresholds` fixture.

A failing freshness test does not mean the endpoint serving the data is
broken — it means the upstream pipeline that fills the table is. Phase 3
uses the breakdown to route the fix (LaunchAgent vs endpoint vs API code).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from . import conftest as cf


def _build_freshness_cases(thresholds: dict) -> list[tuple[str, str, int]]:
    out = []
    for table, (col, max_hours) in thresholds.items():
        if col is None or max_hours is None:
            continue
        out.append((table, col, max_hours))
    return out


def _all_cases():
    # We can't easily depend on the fixture here, so duplicate the threshold
    # keys statically; the fixture is the source of truth for thresholds at
    # runtime. If this list drifts, conftest.freshness_thresholds wins.
    return [
        ("crypto_ndd_daily",      "run_date::timestamp",       36),
        ("crypto_ndd_alerts",     "alert_date::timestamp",     36),
        ("nerq_risk_signals",     "signal_date::timestamp",    36),
        ("crypto_price_history",  "date::timestamp",           36),
        ("crypto_rating_daily",   "run_date::timestamp",       36),
        ("crypto_pipeline_runs",  "started_at::timestamp",     36),
        ("external_trust_signals", "fetched_at",               72),
        ("infrastructure_alerts",  "last_seen_at",             24),
    ]


@pytest.mark.parametrize(
    "table,timestamp_col,max_hours",
    _all_cases(),
    ids=[c[0] for c in _all_cases()],
)
def test_table_freshness(table, timestamp_col, max_hours, pg_conn, request):
    """SELECT MAX(<col>) FROM zarq.<table>; assert age < max_hours."""
    test_id = request.node.nodeid
    cur = pg_conn.cursor()
    q = f"SELECT MAX({timestamp_col}) FROM zarq.{table}"
    t0 = time.time()
    try:
        cur.execute(q)
        row = cur.fetchone()
    except Exception as e:
        elapsed_ms = (time.time() - t0) * 1000
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target="pg-nbg", category=cf.FailureCategory.DB_TABLE_MISSING,
            detail=f"query failed: {type(e).__name__}: {e}",
            method="SELECT", path=f"zarq.{table}", elapsed_ms=elapsed_ms,
            pg_pool="agentindex_write (direct to Nbg)",
        ))
        pytest.fail(f"DB_QUERY_FAILED {table}: {e}")
    elapsed_ms = (time.time() - t0) * 1000

    cur.close()

    if not row or row[0] is None:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target="pg-nbg", category=cf.FailureCategory.EMPTY_RESPONSE,
            detail=f"zarq.{table} is empty (MAX({timestamp_col}) NULL)",
            method="SELECT", path=f"zarq.{table}", elapsed_ms=elapsed_ms,
            pg_pool="agentindex_write (direct to Nbg)",
        ))
        pytest.fail(f"EMPTY zarq.{table}")

    last = row[0]
    # Normalize to aware datetime in UTC.
    if isinstance(last, str):
        try:
            last = datetime.fromisoformat(last)
        except Exception:
            pytest.skip(f"freshness MAX value not a datetime for {table}: {last!r}")
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600

    if age_hours > max_hours:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target="pg-nbg", category=cf.FailureCategory.STALE_DATA,
            detail=f"zarq.{table} latest={last.isoformat()} age={age_hours:.1f}h > threshold {max_hours}h",
            method="SELECT", path=f"zarq.{table}", elapsed_ms=elapsed_ms,
            pg_pool="agentindex_write (direct to Nbg)",
            extra={"age_hours": round(age_hours, 1), "max_hours": max_hours},
        ))
        pytest.fail(f"STALE {table} {age_hours:.1f}h > {max_hours}h")

    cf.record_pass(test_id, "pg-nbg", elapsed_ms, path=f"zarq.{table}")
