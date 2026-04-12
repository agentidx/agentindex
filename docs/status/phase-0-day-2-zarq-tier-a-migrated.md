# Phase 0 Day 2 Evening — ZARQ Tier A Migration Complete

Date: 2026-04-12 (Sunday evening)
Status: All 12 ZARQ Tier A tables migrated from SQLite to PostgreSQL
Related: docs/status/phase-0-day-2-replication-active.md, docs/status/zarq-active-tables.md

## Migrated tables and row counts (all match SQLite exactly)

| Table | Rows |
|---|---|
| crypto_ndd_alerts | 1,530,189 |
| crypto_price_history | 1,125,586 |
| crypto_ndd_daily | 230,412 |
| external_trust_signals | 22,502 |
| defi_yields | 18,784 |
| compatibility_matrix | 18,741 |
| agent_dashboard | 15,986 |
| vitality_scores | 15,144 |
| nerq_risk_signals | 6,355 |
| crypto_rating_daily | 3,743 |
| crypto_pipeline_runs | 371 |
| chain_dex_volumes | 316 |

Total: 3,088,129 rows

## Schema

All tables created in `zarq` PostgreSQL schema (isolated from nerq tables).
12 CREATE TABLE + 13 CREATE INDEX executed from
`docs/migrations/zarq-tier-a-postgres.sql`.

## Migration method

1. SQLite table exported to CSV via `sqlite3 -csv -header`
2. PostgreSQL COPY FROM loaded CSV
3. Row count verified against SQLite source

Time: ~2 minutes for 11 tables + 15s for crypto_price_history (which
needed `SET statement_timeout = 0` due to the default 5s timeout killing
the 1.1M row bulk load).

## Replication status

- nerq-nbg-1 (streaming, 0 bytes lag): receiving zarq data live
- nerq-hel-1 (basebackup running): will include all zarq data since it's
  being copied after DDL was applied

Once Hel completes (~22:00 CEST), both replicas will have identical data.

## Database sizes

- Before migration: 90 GB
- After migration: 91 GB (+1 GB for zarq tables)

Minimal overhead vs. 1.2 GB SQLite due to PostgreSQL's better compression
for integer and float columns.

## What remains (Day 3+)

1. Helsinki replica finishes and starts streaming
2. Update ZARQ Python modules to write PostgreSQL instead of SQLite
   (target files: agentindex/crypto/crypto_pipeline.py and others that
   write to crypto_trust.db)
3. Dual-write period (both SQLite and PostgreSQL accept writes, verify
   parity for 24-48h)
4. Cutover ZARQ reads to PostgreSQL
5. Deprecate SQLite write path for Tier A tables
6. Tier B migration (10 more semi-active tables, ~37K rows)

## Production during migration

Throughout ZARQ data migration (~5 minutes), production served 200 OK.
No user impact. Sacred bytes 2/2/1 preserved.

## Lesson

PostgreSQL default `statement_timeout` of 5s (from our production config)
must be overridden for bulk operations. `SET statement_timeout = 0` in
migration scripts is safe.
