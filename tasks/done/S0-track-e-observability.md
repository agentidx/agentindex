# S0 Track E — Observability Foundation

**Date:** 2026-03-07
**Status:** Complete — 29/29 tests passing

---

## What was built

### 1. Request logging middleware (`agentindex/observability.py`)

Every HTTP request is logged to `agentindex/crypto/zarq_api_log.db` with:

| Column | Type | Description |
|--------|------|-------------|
| timestamp | TEXT | ISO 8601 UTC |
| endpoint | TEXT | Request path |
| method | TEXT | GET/POST/etc |
| status_code | INTEGER | HTTP response code |
| latency_ms | REAL | Response time in ms |
| ip_hash | TEXT | SHA-256 of client IP (first 16 chars) |
| tier | TEXT | open/free/basic/pro/internal (from X-Nerq-Tier header) |
| user_agent | TEXT | First 200 chars |
| response_size | INTEGER | Content-Length bytes |

**Design:**
- Buffered writes: rows accumulate in memory, flushed to SQLite every 20 requests
- Thread-safe via `threading.Lock`
- Indexes on `timestamp` and `endpoint` for fast metric queries
- Reads tier from `X-Nerq-Tier` response header (set by existing ApiProtectionMiddleware)
- Uses `datetime.now(timezone.utc)` (not deprecated `utcnow()`)

### 2. Metrics endpoint (`GET /internal/metrics`)

Protected by bearer token (`ZARQ_METRICS_TOKEN` env var, default `zarq-internal-2026`).

Returns JSON:
```json
{
  "requests_last_24h": 142,
  "requests_last_1h": 23,
  "unique_ips_last_24h": 8,
  "p50_latency_ms": 12.3,
  "p95_latency_ms": 245.1,
  "top_10_endpoints": [{"endpoint": "/v1/health", "count": 45}, ...],
  "tier_distribution": {"open": 100, "free": 30, "internal": 12}
}
```

### 3. Integration

Added to `discovery.py` line 156 via `mount_observability(app)`, which:
- Initializes the SQLite DB + table
- Adds `ObservabilityMiddleware` to the middleware stack
- Registers the `/internal/metrics` route

---

## Files changed

| File | Change |
|------|--------|
| `agentindex/observability.py` | **New** — middleware + metrics endpoint |
| `agentindex/api/discovery.py` | Added 2 lines to mount observability |
| `tests/test_api_basic.py` | Added 4 tests for /internal/metrics |

---

## Test results

```
29 passed, 62 warnings in 26.53s
```

New tests:
- `test_metrics_unauthorized_without_token` — 401 without token
- `test_metrics_unauthorized_wrong_token` — 401 with bad token
- `test_metrics_returns_200_with_valid_token` — 200 with correct bearer
- `test_metrics_has_required_fields` — all 7 fields present, correct types

All 25 pre-existing tests still pass (no regressions).

---

## Verification

```
sqlite3 zarq_api_log.db ".schema api_log"
→ 9 columns, 2 indexes
→ 26 rows logged from test run alone
```
