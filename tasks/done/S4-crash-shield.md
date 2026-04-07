# S4 — Crash Shield, Viral Save-Cards, Forta Integration

**Date:** 2026-03-07
**Status:** Complete — 75/75 tests passing

---

## Task A: Crash Shield Alert System

### Core Logic: `agentindex/crash_shield.py`

**`check_for_new_saves(min_prob=0.5, min_drop=0.30)`:**
- Queries `crash_model_v3_predictions` for OOS predictions with crash_prob > 0.5
- Cross-references with `crypto_price_history` to find lowest price within 90 days
- Calculates actual drop percentage from warning price to bottom price
- Only counts drops > 30% as verified "saves"
- SHA-256 hash of save data for integrity
- Stores in new `crash_shield_saves` SQLite table
- Idempotent — skips existing saves via `INSERT OR IGNORE`

**Initial seed:** 50 verified saves detected (limited by GROUP BY deduplication per token).

**Top 5 saves:**

| Token | Drop | Warning Date | Lead Time | Saved per $1,000 |
|-------|------|-------------|-----------|-------------------|
| Story (IP) | 86.2% | 2025-10-06 | 80 days | $861.96 |
| Virtuals Protocol | 84.0% | 2024-12-30 | 70 days | $840.20 |
| Unibase (UB) | 83.9% | 2024-12-02 | 25 days | $838.54 |
| Undeads Games | 81.7% | 2024-10-07 | 22 days | $817.07 |
| Berachain (BERA) | 80.8% | 2025-10-06 | 73 days | $808.44 |

### API Endpoints

**`GET /v1/crash-shield/saves`** — All verified saves with value calculations:
- `saved_per_1000_usd`: how much $1,000 would have been saved
- `days_lead_time`: days between warning and crash

**`POST /v1/crash-shield/subscribe`** — Webhook registration:
- Input: `{"url": "https://...", "alert_levels": "WARNING,CRITICAL"}`
- Returns: `webhook_id`, status, confirmation message
- Stores in existing `crash_shield_webhooks` table
- Validates URL format

---

## Task B: Viral Save-Cards

**`GET /v1/crash-shield/save/{save_id}/card`** — Shareable HTML card:
- ZARQ design: light theme, DM Serif Display, warm gold accent
- Shows: token name, drop %, warning date, crash date, prices, crash probability, SHA-256
- "ZARQ detected this X days before crash" headline
- OpenGraph meta tags: og:title, og:description, og:url, og:type
- Twitter Card meta tags: twitter:card, twitter:title, twitter:description
- Footer: "Trust Checked by ZARQ — Risk Intelligence for the Agent Economy"
- CTA: link to check token now

**`GET /save/{save_id}`** — Pretty URL (same content)

---

## Task C: Forta API Integration

### `agentindex/forta_integration.py`

**`fetch_forta_alerts(severities, limit)`:**
- Queries Forta GraphQL API (`https://api.forta.network/graphql`)
- Fetches CRITICAL and HIGH severity alerts
- Cross-references with 20 ZARQ-tracked protocols (Uniswap, Aave, Compound, etc.)
- Stores all alerts in `forta_alerts` SQLite table
- Uses circuit breaker (`agentindex/circuit_breaker.py`) for graceful degradation
- If Forta is down: 3 failures → backoff 30s→60s→120s→max 10min

**Protocol matching:** fuzzy match against protocol name, alert name, and description for 20 DeFi protocols mapped to CoinGecko token IDs.

**`get_stored_forta_alerts(token_id, limit)`:** Query stored alerts by ZARQ token.

---

## Files Created/Modified

| File | Change |
|------|--------|
| `agentindex/crash_shield.py` | New: saves detection, API endpoints, save cards, webhook subscriptions |
| `agentindex/forta_integration.py` | New: Forta GraphQL client, protocol matching, SQLite storage, circuit breaker |
| `agentindex/api/discovery.py` | Mount router_crash_shield |
| `tests/test_api_basic.py` | +14 tests for crash shield and Forta |

## Test Results

```
75 passed, 130 warnings in 37.47s
```

New tests (+14):
- `TestCrashShield::test_saves_returns_200`
- `TestCrashShield::test_saves_has_data`
- `TestCrashShield::test_save_has_required_fields`
- `TestCrashShield::test_save_has_value_calculations`
- `TestCrashShield::test_save_card_returns_html`
- `TestCrashShield::test_save_card_has_meta_tags`
- `TestCrashShield::test_save_card_pretty_url`
- `TestCrashShield::test_save_card_404_for_unknown`
- `TestCrashShield::test_subscribe_returns_webhook_id`
- `TestCrashShield::test_subscribe_rejects_invalid_url`
- `TestCrashShield::test_subscribe_rejects_missing_url`
- `TestFortaIntegration::test_protocol_matching`
- `TestFortaIntegration::test_forta_table_exists`
- `TestFortaIntegration::test_get_stored_alerts_empty`
