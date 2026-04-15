# Phase 0 Stability Sprint — Dag 3 Report

**Date:** 2026-04-15
**Goal:** Regression-driven verification of all Dag 1 + Dag 2 fixes

---

## Regression Test Results

**Script:** `scripts/regression_test.sh` — 12 automated checks

| Test | Description | Result |
|------|-------------|--------|
| T1 | No hardcoded DATABASE_URL localhost fallbacks | **PASS** (0 matches) |
| T2 | No hardcoded old IP (100.90.152.88) DSNs | **PASS** (0 matches) |
| T3 | db_config adopted by 27+ files | **PASS** (27 files) |
| T4 | stale-scores LEFT JOIN agents | **PASS** |
| T5 | vitality busy_timeout | **PASS** |
| T6 | pg_stat_statements on 3 nodes | **PASS** (Mac:1 Nbg:1 Hel:1) |
| T7 | PgBouncer running | **PASS** (port 6432, query OK) |
| T8 | Alert monitor active | **PASS** |
| T9 | 0 read-only errors (last 2 min) | **PASS** (0 errors since 14:31) |
| T10 | Replication 0 lag, 2 replicas | **PASS** (node2:0, mac_studio:0) |
| T11 | API latency <500ms (10 samples) | **PASS** (avg 5ms) |
| T12 | API functional (3 endpoints) | **PASS** (all 200) |

## Issue Found and Fixed

**`run_parser_loop.py`** (PID 3578) had been running continuously since April 2 — 13 days with cached old code (pre-db_config). It imported `Parser()` once at startup and never re-imported, so it kept using the old `get_session()` (read replica) for UPDATE operations.

**Fix:** Killed the stale process + master_watchdog. Watchdog restarted both with fresh code. Parser now correctly uses `get_write_session()` → Nbg primary. 0 read-only errors since restart at 14:31.

**Root cause classification:** This was the **same bug** as iter3-4 (parser/classifier write-on-replica) but it persisted because a **long-running daemon** cached the old module. All LaunchAgent-based agents reload code on each run, but `run_parser_loop.py` is a while-True loop that never exits.

## Baseline Metrics (14:33)

| Metric | Value |
|--------|-------|
| RAM | 60/64 GB used (3.3 GB free) |
| CPU | 51% idle |
| Load avg | 8.21 / 7.99 / 7.99 |
| PG connections | 24 |
| Replication lag | node2: 0, mac_studio: 0 |
| API latency p50 | 3.6ms |
| API latency p95 | 10.9ms |
| PgBouncer | 10 xacts/s, 20 queries/s, wait 80us |
| Redis keys (db1) | 138,316 |
| Redis hit rate | 0.81% (pre-existing, unchanged) |

## Known Remaining Issues

| Issue | Status | Impact |
|-------|--------|--------|
| zarq-cache timeout | Timeout raised 300→600s (iter8). Exit 2 from pre-fix run still cached in launchctl. | Low — next run should succeed |
| stale-scores | Fixed (iter8 schema + iter9 SQLite). Exit 1 from 07:00 run still cached. | None — next run at 07:00 will succeed |
| vitality-recalc | Fixed (iter9 busy_timeout). Exit 1 from 06:00 run still cached. | None — next run at 06:00 will succeed |
| Redis hit rate 0.81% | Not addressed in stability sprint. Pre-existing. | Performance — cold renders |
| RAM 3.3 GB free | Improved from 1.5 GB (PgBouncer), but not at 10 GB target. | Monitor — Ollama + Chrome consume ~4 GB |
| `run_parser_loop.py` design | while-True loop doesn't reload code. Should exit periodically. | Fragile — any future code change requires manual kill |

## Files Changed in Dag 3

- `scripts/regression_test.sh` — new, 12 automated checks
- Killed stale `run_parser_loop.py` (no code change, process restart)

## Total Sprint Summary (Dag 1-3)

| Day | Iterations | Files changed | Key fixes |
|-----|-----------|---------------|-----------|
| Dag 1 | 7 | 42 files | db_config.py, write/read separation, 128 ReadOnly errors → 0 |
| Dag 2 | 3 (dag2-1 to iter9) | 12 files | PgBouncer (RAM 4.7→11 GB), schema-drift (3 bugs), cache timeouts, vitality retry |
| Dag 3 | 1 | 1 file + process kill | Regression test suite, stale parser daemon |
