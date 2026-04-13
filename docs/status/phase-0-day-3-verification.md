# Phase 0 Day 3 — Dual-Write Verification

Date: 2026-04-13 ~07:00 CEST
Status: Pre-enable verification complete

## Row count comparison: SQLite vs PostgreSQL

| Table | SQLite | Postgres | Delta | Status |
|---|---:|---:|---:|---|
| crypto_ndd_alerts | 1,532,199 | 1,530,189 | +2,010 | Expected gap |
| crypto_price_history | 1,125,978 | 1,125,586 | +392 | Expected gap |
| crypto_ndd_daily | 235,821 | 230,412 | +5,409 | Expected gap |
| external_trust_signals | 22,502 | 22,502 | 0 | Match |
| defi_yields | 18,784 | 18,784 | 0 | Match |
| compatibility_matrix | 18,741 | 18,741 | 0 | Match |
| agent_dashboard | 15,986 | 15,986 | 0 | Match |
| vitality_scores | 15,149 | 15,144 | +5 | Expected gap |
| nerq_risk_signals | 6,560 | 6,355 | +205 | Expected gap |
| crypto_rating_daily | 3,743 | 3,743 | 0 | Match |
| crypto_pipeline_runs | 372 | 371 | +1 | Expected gap |
| chain_dex_volumes | 316 | 316 | 0 | Match |

**6 tables match exactly (0 delta).** These tables have not been written to since
the April 12 migration.

**6 tables have positive deltas.** These are rows written to SQLite between the
migration (Apr 12 evening) and now (Apr 13 morning) before dual-write was enabled.
All deltas are in the expected range for 12-18 hours of cron activity.

## End-to-end test result

```
Test: INSERT OR REPLACE INTO chain_dex_volumes with test row
SQLite: ('__test_chain__', 0.0, 0.0, 0.0, 0.0, '2026-04-13T00:00:00') ✅
Postgres: ('__test_chain__', 0.0, 0.0, 0.0, 0.0, '2026-04-13T00:00:00') ✅
Cleanup: both rows deleted ✅
```

## Next steps

1. Enable ZARQ_DUAL_WRITE=1 in relevant LaunchAgent plists
2. Wait for next cron cycle (crypto_daily_master runs at 06:00 UTC)
3. Re-run verification to confirm deltas are no longer growing
4. Backfill the gap rows (one-time CSV export → COPY)
5. After 24-48h of parity: switch ZARQ reads to PostgreSQL
