# Phase 0 Day 3 — ZARQ Dual-Write Implementation

Date: 2026-04-13
Status: COMPLETE — dual-write code deployed, ready to enable

## What was done

Created `agentindex/crypto/dual_write.py` — central helper that mirrors every
SQLite write to Tier A tables into PostgreSQL `zarq.*` schema. Refactored all
16 write-site files (25 individual write operations) to use the helper.

## Architecture

```
Python module → dual_execute(sqlite_conn, sql, params)
                  ├─ 1. sqlite_conn.execute(sql, params)  ← always runs
                  └─ 2. pg_conn.execute(translated_sql)   ← if ZARQ_DUAL_WRITE=1
                       ├─ success → commit
                       └─ failure → log to dual_write_errors.log, rollback
```

Feature flag: `export ZARQ_DUAL_WRITE=1` to enable, unset to disable.

## SQL translation

| SQLite pattern | PostgreSQL output |
|---|---|
| `INSERT OR REPLACE INTO table (cols) VALUES (?,?)` | `INSERT INTO zarq.table (cols) VALUES (%s,%s) ON CONFLICT (pk) DO UPDATE SET ...` |
| `INSERT INTO table (cols) VALUES (?,?)` | `INSERT INTO zarq.table (cols) VALUES (%s,%s) ON CONFLICT (pk) DO NOTHING` |
| `DELETE FROM table` | `DELETE FROM zarq.table` |
| `:named` params | `%(named)s` params |
| SQL with existing `ON CONFLICT` | Passthrough with `zarq.` prefix |

## Files modified

### New file
- `agentindex/crypto/dual_write.py` (293 lines)

### Refactored files (16)

| File | Table(s) | Operations |
|---|---|---|
| `crypto/crypto_daily_master.py` | crypto_pipeline_runs | 1x INSERT |
| `crypto/nerq_risk_signals.py` | nerq_risk_signals | 1x executemany |
| `crypto/vitality_score.py` | vitality_scores | 1x DELETE + loop INSERT |
| `crypto/crypto_rating_daily.py` | crypto_rating_daily | 2x INSERT OR REPLACE |
| `crypto/crypto_ndd_daily_v3.py` | crypto_ndd_daily, crypto_ndd_alerts | 2x INSERT/REPLACE |
| `crypto/crypto_ndd_daily_v2.py` | crypto_ndd_daily, crypto_ndd_alerts | 2x INSERT/REPLACE |
| `crypto/crypto_ndd_daily.py` | crypto_ndd_daily, crypto_ndd_alerts | 2x INSERT/REPLACE |
| `crypto/crypto_price_pipeline.py` | crypto_price_history | 1x INSERT OR REPLACE |
| `crypto/quick_price_fetch.py` | crypto_price_history | 1x INSERT OR REPLACE |
| `crypto/crypto_price_fetcher.py` | crypto_price_history | 1x executemany (named) |
| `crypto/defillama_price_fallback.py` | crypto_price_history | 1x INSERT ON CONFLICT |
| `crypto/data_pipeline_defillama.py` | defi_yields | 1x executemany |
| `crypto/crawlers/defi_dex_volumes.py` | chain_dex_volumes | 1x executemany |
| `crawlers/compatibility_matrix.py` | compatibility_matrix | 1x DELETE + 3x INSERT |
| `crawlers/openssf_scorecard.py` | external_trust_signals | 2x INSERT OR REPLACE |
| `crawlers/snyk_crossref.py` | external_trust_signals | 3x INSERT OR REPLACE |
| `crawlers/community_signals.py` | external_trust_signals | 4x INSERT OR REPLACE |
| `intelligence/dashboard_data.py` | agent_dashboard | 1x INSERT OR REPLACE |

### Skipped (not Tier A)
- `nerq_risk_signals.py:399` — writes to `nerq_risk_alerts` (not a Tier A table)
- `bootstrap_march_ratings.py` — one-time migration script

## Test results

1. SQL translation: all 5 patterns tested, correct output
2. Postgres connection pool: connects, queries, returns to pool
3. End-to-end: test row written to SQLite AND Postgres, verified both, cleaned up
4. Feature flag: disabled by default, enables correctly when set

## Commits

1. `ce35c53` — dual_write.py module
2. `f294c66` — pipeline_runs, risk_signals, vitality, ratings
3. `9963bae` — NDD daily (v1/v2/v3), price history, defi yields
4. `d87b45d` — compatibility matrix, trust signals, volumes, dashboard

## How to enable

```bash
# In the LaunchAgent plist for each writing process, add:
export ZARQ_DUAL_WRITE=1

# Or set in ~/.zshrc for all processes:
echo 'export ZARQ_DUAL_WRITE=1' >> ~/.zshrc
```

## How to disable (emergency)

```bash
unset ZARQ_DUAL_WRITE
# Processes will stop mirroring on next write
```

## Open questions

1. **Backfill gap**: 6 tables have deltas (rows written between migration Apr 12
   and now). Need a one-time catch-up migration before considering Postgres as
   source of truth. Largest gap: crypto_ndd_daily (+5,409 rows).

2. **LaunchAgent env vars**: Each cron-triggered module runs via LaunchAgent. The
   `ZARQ_DUAL_WRITE` env var must be set in the LaunchAgent plist `EnvironmentVariables`
   dict for each relevant plist, or globally via launchd.

3. **Commit timing**: Dual-write commits Postgres independently per execute call.
   If a module does multiple executes then one commit, Postgres will have committed
   some rows even if the final SQLite commit doesn't happen. This is acceptable
   because Postgres is the mirror, not the source of truth.

4. **Autoincrement IDs**: Tables with INTEGER PRIMARY KEY AUTOINCREMENT
   (crypto_ndd_alerts, crypto_ndd_daily, crypto_rating_daily, crypto_pipeline_runs,
   external_trust_signals) may have different IDs between SQLite and Postgres after
   the gap period. This only matters if anything joins on those IDs across databases.
