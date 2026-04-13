# Phase 0 Day 4.7 — Tier A Gap Backfill Complete

Date: 2026-04-13 08:50 CEST
Status: COMPLETE — all 6 tables at parity

## Result

| Table | SQLite | Postgres | Inserted | Skipped |
|---|---:|---:|---:|---:|
| crypto_ndd_alerts | 1,532,199 | 1,532,199 | 2,010 | 1,530,189 |
| crypto_price_history | 1,125,978 | 1,125,978 | 392 | 1,125,586 |
| crypto_ndd_daily | 235,821 | 235,821 | 5,409 | 230,412 |
| vitality_scores | 15,149 | 15,149 | 5 | 15,144 |
| nerq_risk_signals | 6,560 | 6,560 | 205 | 6,355 |
| crypto_pipeline_runs | 372 | 372 | 1 | 371 |
| **Total** | | | **8,022** | **2,907,057** |

All 6 tables now have identical row counts between SQLite and PostgreSQL.

## Method

Script `scripts/backfill_tier_a_gap.py` reads all rows from SQLite and
inserts into `zarq.*` with `ON CONFLICT (pk) DO NOTHING`. Duplicates
(2.9M rows already present) are skipped automatically.

Runtime: ~3 minutes. No errors.

## ID handling

All 3 autoincrement tables (crypto_ndd_alerts, crypto_ndd_daily,
crypto_pipeline_runs) had SQLite max(id) > Postgres max(id), so SQLite
IDs were preserved as-is. No Postgres sequences exist (tables use plain
INTEGER PK, not SERIAL).
