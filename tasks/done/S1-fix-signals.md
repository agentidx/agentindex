# S1 — Fix /v1/crypto/signals 500 Error

**Date:** 2026-03-07
**Status:** Complete — 40/40 tests passing

---

## Root Cause

Two bugs in `agentindex/crypto/crypto_api_v2.py`:

### Bug 1: Wrong column name in `latest_run_date()`
The `latest_run_date()` helper always queried `MAX(run_date)`, but `nerq_risk_signals` uses `signal_date` instead of `run_date`. This caused an `sqlite3.OperationalError: no such column: run_date` on any endpoint that called `latest_run_date(conn, "nerq_risk_signals")`.

**Affected endpoints:** `/v1/crypto/signals`, `/v1/crypto/risk-levels`

**Fix:** Added column-name dispatch:
```python
def latest_run_date(conn, table="crypto_rating_daily"):
    col = "signal_date" if table == "nerq_risk_signals" else "run_date"
    row = conn.execute(f"SELECT MAX({col}) as d FROM {table}").fetchone()
    return row["d"] if row else None
```

### Bug 2: symbol/name pulled from wrong table
Queries used `r.symbol, r.name` from `crypto_rating_daily`, but that table has NULL symbol/name for all 198 rows. `crypto_ndd_daily` has symbol/name populated for all rows.

**Fix:** Changed all three affected queries to pull `n.symbol, n.name, n.market_cap_rank` from the `crypto_ndd_daily` join instead of `crypto_rating_daily`.

---

## Files Modified

| File | Change |
|------|--------|
| `agentindex/crypto/crypto_api_v2.py` | Fixed `latest_run_date()` for signal_date column; moved symbol/name/market_cap_rank to ndd join in 3 queries |

## Endpoints Fixed

| Endpoint | Before | After |
|----------|--------|-------|
| `GET /v1/crypto/signals` | HTTP 500 | 50 signals, symbols populated |
| `GET /v1/crypto/signals/history` | symbol/name NULL | symbol/name from ndd |
| `GET /v1/crypto/risk-levels` | HTTP 500 | 205 tokens, distribution: CRITICAL=25, WARNING=47, WATCH=82, SAFE=51 |

## MCP Tool Fixed

`get_risk_signals` on the ZARQ MCP server (port 8001) now returns data successfully:
```
MCP get_risk_signals: 50 signals
  First: bera (Berachain) - CRITICAL - crash=0.2
```

## Verification

```
curl https://zarq.ai/v1/crypto/signals → 50 signals, symbols populated
curl localhost:8000/v1/crypto/risk-levels → 205 tokens with distribution
curl localhost:8000/v1/crypto/signals/history → Historical data with symbols
MCP tools/call get_risk_signals → Working via mcp.zarq.ai
Tests: 40 passed, 87 warnings
```
