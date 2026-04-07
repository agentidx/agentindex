# S1 — Paper Trading Track Record (Hash-Chained Daily Signals)

**Date:** 2026-03-07
**Status:** Complete — Genesis entry generated, 60/60 tests passing

---

## What Was Built

### Daily Track Record System

A tamper-evident daily snapshot of all 205 token risk signals, hash-chained like a blockchain.

**Script:** `scripts/daily_track_record.py`

Each day it:
1. Queries all 205 tokens from `nerq_risk_signals` (latest signal date)
2. Marks tokens with `structural_weakness >= 2` OR `trust_p3 < 40` as ZARQ WARNING
3. Gets current price for each token from `crypto_price_history`
4. Computes SHA-256 hash of `{date, signals[], previous_hash}` (hash chain)
5. Appends one line to `track-record/daily-signals.jsonl`
6. Idempotent — skips if today's entry already exists

### Hash Chain

Each entry contains:
```json
{
  "date": "2026-03-07",
  "signal_date": "2026-02-28",
  "total_tokens": 205,
  "zarq_warnings": 75,
  "signals": [...],
  "hash": "fd8574ac0258c070...",
  "previous_hash": "genesis",
  "generated_at": "2026-03-07T15:42:37Z"
}
```

The hash is `SHA-256(JSON.stringify({date, signals, previous_hash}, sorted_keys))`. Any modification to historical entries breaks the chain — verifiable by anyone with the JSONL file.

### Signal Structure

Each of the 205 signals contains:
```json
{
  "token_id": "1inch",
  "risk_level": "CRITICAL",
  "trust_score": 59.07,
  "trust_p3": 39.47,
  "ndd": 2.88,
  "structural_weakness": 3,
  "zarq_warning": true,
  "price_usd": 0.0941,
  "price_date": "2026-02-27",
  "first_collapse_date": "2025-12-01",
  "price_at_collapse": 0.1882
}
```

Warning tokens also include `first_collapse_date` and `price_at_collapse` for later performance verification.

---

## Genesis Entry

```
Signal date: 2026-02-28
Total tokens: 205
ZARQ warnings: 75 (37% of tracked tokens)
Hash: fd8574ac0258c070317e6c1ec1d76b57e9d76d6693826fdae46a7f0e64327831
Previous: genesis
```

Hash integrity verified — recomputation matches stored hash.

---

## Files Created

| File | Description |
|------|-------------|
| `scripts/daily_track_record.py` | Main script — queries DB, builds signals, hash-chains |
| `scripts/run_daily_track_record.sh` | Cron wrapper (logs to `logs/daily_track_record.log`) |
| `track-record/daily-signals.jsonl` | Output file — genesis entry generated |

## Cron Setup

```
0 1 * * * /Users/anstudio/agentindex/scripts/run_daily_track_record.sh
```

## Existing Paper Trading Infrastructure

The project already has a paper trading system:
- `paper_trading_daily.py` — Daily NAV calculation for ALPHA/DYNAMIC/CONSERVATIVE portfolios
- `paper_trading_signal.py` — Monthly signal generation with hash chains
- `paper_trading.db` — SQLite with portfolio_nav, positions, signals tables
- 5 API endpoints at `/v1/crypto/paper-trading/*`
- HTML dashboard at `/paper-trading`

The new track record system is complementary — it creates a public, verifiable daily log of ALL risk signals (not just portfolio actions) that can be independently audited.

## Test Results

```
60 passed, 81 warnings in 57.86s
```

No regressions.
