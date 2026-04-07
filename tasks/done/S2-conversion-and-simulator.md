# S2 — Conversion Logic + First Save Simulator

**Date:** 2026-03-07
**Status:** Complete — 52/52 tests passing

---

## Task A: Tier/Rate-Limit Logic

### Implementation

Replaced SQLite-based call counting with Redis-backed tier system in `agentindex/observability.py`.

**Tier thresholds (per IP hash, daily):**

| Tier | Calls/Day | Behavior |
|------|-----------|----------|
| `open` | 0–499 | Full response |
| `signal` | 500–1999 | Full response + tier headers |
| `degraded` | 2000–4999 | Stripped response: removes `crash_probability` and `distance_to_default`, adds `_degraded: true` |
| `blocked` | 5000+ | HTTP 402 with payment instructions JSON |

**Redis implementation:**
- Key format: `zarq:calls:{ip_hash}:{YYYY-MM-DD}`
- Uses `INCR` + `EXPIRE 86400` for atomic daily counting
- Graceful degradation: if Redis is down, falls through to "open" tier (all calls succeed)
- Uses `/opt/homebrew/bin/redis-cli` subprocess calls (no redis-py dependency needed)

**402 response body:**
```json
{
  "error": "daily_limit_exceeded",
  "tier": "blocked",
  "calls_today": 5001,
  "daily_limit": 5000,
  "upgrade": {
    "message": "You've exceeded 5,000 calls today. Upgrade for unlimited access.",
    "contact": "hello@zarq.ai",
    "plans": {"pro": {"price": "$49/mo"}, "enterprise": {"price": "Custom"}}
  }
}
```

**Degraded tier stripping:**
- Recursively removes `crash_probability` and `distance_to_default` from response JSON (including nested in arrays)
- Adds `_degraded: true` and `_upgrade` hint to response
- Only applies to HTTP 200 responses on non-health endpoints

**Headers on all /v1/ responses:**
- `X-Calls-Today`: current count from Redis
- `X-Daily-Limit`: 5000
- `X-Tier`: open/signal/degraded/blocked
- `X-Powered-By`: ZARQ (zarq.ai)

### Verified
```
$ curl -sI localhost:8000/v1/check/bitcoin | grep x-
x-calls-today: 5
x-daily-limit: 5000
x-tier: open
x-powered-by: ZARQ (zarq.ai)

$ redis-cli KEYS "zarq:calls:*:2026-03-07"
zarq:calls:12ca17b49af22894:2026-03-07
```

---

## Task B: Save Simulator

### API Endpoint: GET /v1/demo/save-simulator

Queries `crash_model_v3_predictions` for tokens where ZARQ flagged crash probability > 50% AND the token subsequently dropped > 50%. Uses only out-of-sample (OOS) predictions.

**Response:**
```json
{
  "saves": [
    {
      "token": "Flying Tulip", "symbol": "FT", "warning_date": "2024-04-15",
      "price_at_warning": 1.808, "price_at_bottom": 0.0382, "drop_percent": 97.9,
      "crash_probability": 0.57,
      "message": "If your agent had ZARQ on 2024-04-15, it would have avoided FT — which fell 97.9% from $1.808 to $0.03816."
    }
  ],
  "total": 5,
  "source": "ZARQ crash_model_v3 (OOS predictions)"
}
```

**Top 5 saves found:**

| Token | Warning Date | Drop | Price At Warning | Bottom |
|-------|-------------|------|-----------------|--------|
| Flying Tulip (FT) | 2024-04-15 | 97.9% | $1.808 | $0.038 |
| Hyperliquid (HYPE) | 2024-03-11 | 96.1% | $0.0001 | $0.000 |
| River (RIVER) | 2026-01-19 | 90.6% | $29.94 | $2.81 |
| Virtuals Protocol (VIRTUAL) | 2024-12-30 | 87.9% | $3.50 | $0.42 |
| Story (IP) | 2025-10-06 | 86.2% | $10.33 | $1.43 |

### HTML Page: GET /demo/save-simulator

Visual page with ZARQ design (light theme, DM Serif Display, warm gold accent):
- Animated save cards showing each crash prediction
- Price-at-warning → price-at-bottom visual comparison
- Crash probability badge
- CTA: "Add ZARQ to your agent in 1 line" with `GET https://zarq.ai/v1/check/bitcoin`
- Link to API docs
- Attribution to OOS crash_model_v3 predictions

---

## Files Modified

| File | Change |
|------|--------|
| `agentindex/observability.py` | Redis tier system: _redis_incr_daily, _get_tier, _strip_degraded_fields, 402 blocked response, degraded body stripping |
| `agentindex/crypto/zarq_save_simulator.py` | New: save simulator API + HTML page |
| `agentindex/api/discovery.py` | Mount router_save_sim |
| `tests/test_api_basic.py` | +12 tests: TestTierLogic (6), TestSaveSimulator (6); updated daily limit header 500→5000 |

## Test Results

```
52 passed, 102 warnings in 40.03s
```

New tests:
- `TestTierLogic::test_open_tier_returns_full_response`
- `TestTierLogic::test_tier_header_present`
- `TestTierLogic::test_daily_limit_is_5000`
- `TestTierLogic::test_tier_function_boundaries`
- `TestTierLogic::test_strip_degraded_fields`
- `TestTierLogic::test_strip_preserves_nested`
- `TestSaveSimulator::test_save_simulator_api_returns_200`
- `TestSaveSimulator::test_save_simulator_has_saves`
- `TestSaveSimulator::test_save_has_required_fields`
- `TestSaveSimulator::test_save_drop_over_50`
- `TestSaveSimulator::test_save_simulator_page_returns_html`
- `TestSaveSimulator::test_save_simulator_page_has_cta`
