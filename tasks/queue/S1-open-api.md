# S1 Task 1 — Open API + Zero-Friction Check Endpoint

**Date:** 2026-03-07
**Status:** Complete — 60/60 tests passing

---

## What Was Built

### 1. `/v1/check/{token}` — Zero-Friction Token Risk Check

New endpoint at `GET /v1/check/{token}` that returns a complete risk verdict with no auth, no API key, no signup.

**Example:** `curl https://zarq.ai/v1/check/bitcoin`

```json
{
    "token": "bitcoin",
    "name": "Bitcoin",
    "symbol": "BTC",
    "verdict": "WARNING",
    "trust_score": 74.52,
    "rating": "A2",
    "distance_to_default": 3.03,
    "structural_weakness": true,
    "risk_level": "WARNING",
    "crash_probability": 0.3177,
    "price_usd": 70825.0,
    "market_cap": null,
    "signal_date": "2026-02-28",
    "checked_at": "2026-03-07T15:26:47.301426+00:00"
}
```

**Verdict mapping:**
- `SAFE` — risk_level is SAFE or WATCH
- `WARNING` — risk_level is WARNING
- `CRITICAL` — risk_level is CRITICAL

**Data sources (single query with 3 joins):**
- `nerq_risk_signals` — risk_level, trust_score, ndd_current, structural_weakness
- `crypto_rating_daily` — rating grade, score, market_cap
- `crypto_ndd_daily` — symbol, price_usd
- `crash_model_v3_predictions` — crash_probability

**Error handling:**
- Unknown token → 404 with `{"error": "Token not found", "available_tokens": 205, "docs": "https://zarq.ai/docs"}`
- Pipeline down → 503 with explanation

### 2. Response Headers on ALL `/v1/` Endpoints

Every `/v1/` response now includes:

```
X-Calls-Today: 107
X-Daily-Limit: 500
X-Tier: open
X-Powered-By: ZARQ (zarq.ai)
```

`X-Calls-Today` counts from the observability DB (`api_log` table) for the requesting IP hash. Added to the existing `ObservabilityMiddleware` so it runs on every request with zero additional middleware overhead.

---

## Files Created/Modified

| File | Change |
|------|--------|
| `agentindex/crypto/zarq_check_api.py` | **New** — /v1/check/{token} endpoint |
| `agentindex/observability.py` | **Modified** — Added `_count_calls_today()` + X-headers on /v1/ |
| `agentindex/api/discovery.py` | **Modified** — Mount `router_check` |
| `tests/test_api_basic.py` | **Modified** — 11 new tests (7 check + 4 headers) |

## Test Results

```
60 passed, 80 warnings in 74.81s
```

- 29 existing API tests (no regressions)
- 7 new /v1/check tests (200, fields, verdict, trust_score, 404, ethereum, name+symbol)
- 4 new response header tests (X-Powered-By, X-Daily-Limit, X-Tier, X-Calls-Today)
- 10 circuit breaker tests
- 10 ZARQ healthcheck tests

## Live Verification

```
$ curl -D - https://zarq.ai/v1/check/bitcoin

HTTP/1.1 200 OK
cache-control: public, max-age=300
x-calls-today: 102
x-daily-limit: 500
x-tier: free
x-powered-by: ZARQ (zarq.ai)

{"token":"bitcoin","name":"Bitcoin","symbol":"BTC","verdict":"WARNING",...}
```

```
$ curl https://zarq.ai/v1/check/zzz-fake-token

{"error":"Token not found","detail":"'zzz-fake-token' is not tracked...","available_tokens":205,"docs":"https://zarq.ai/docs"}
```
