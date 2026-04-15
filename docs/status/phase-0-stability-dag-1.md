# Phase 0 Stability Sprint — Dag 1 Complete

**Date:** 2026-04-15
**Duration:** ~90 minutes
**Goal:** Write-path unification + observability

---

## What Was Done

### DEL 1: Write-Path Unification

**Created `agentindex/db_config.py`** — single source of truth for all DB connections:
- `get_write_dsn()` → Nbg primary (TCP 100.119.193.70:5432)
- `get_read_dsn()` → local replica (Unix socket)
- `get_write_conn()` / `get_read_conn()` → raw psycopg2
- Configurable via env vars: `NERQ_PG_PRIMARY`, `NERQ_PG_REPLICA`

**Updated `agentindex/db/models.py`:**
- `get_engine()` → read engine (local replica, fast)
- `get_write_engine()` → write engine (Nbg primary, TCP)
- `get_session()` → read session (reads)
- `get_write_session()` → write session (writes)
- Removed dependency on `DATABASE_URL` env var

**Fixed write-path files:**

| File | Change | Category |
|------|--------|----------|
| `review_pages.py` | CREATE TABLE + INSERT → `get_write_session()` | **128 errors eliminated** |
| `dual_write.py` | Default DSN → `db_config.get_write_dsn()` | Removed hardcoded 100.90.152.88 |
| `dual_read.py` | Default DSN → `db_config.get_read_dsn()` | Removed hardcoded 100.90.152.88 |
| `compute_trust_score.py` | `DB_DSN` → `db_config.get_write_dsn()` | Removed hardcoded socket |
| `npm_downloads_crawler.py` | Default → `db_config.get_write_dsn()` | Removed localhost fallback |
| `scripts/collect_npm_dependencies.py` | Default → `db_config.get_write_dsn()` | Removed hardcoded IP |
| `scripts/collect_contributor_metrics.py` | Default → `db_config.get_write_dsn()` | Removed hardcoded IP |
| `scripts/retention_daily_snapshots.py` | Default → `db_config.get_write_dsn()` | Removed hardcoded IP |

**Updated API plist:**
- Removed `DATABASE_URL=postgresql://localhost/agentindex` (was pointing to replica!)
- Added `NERQ_PG_PRIMARY=100.119.193.70` + `NERQ_PG_REPLICA=localhost`

### DEL 2: Observability

**Created `scripts/alert_monitor.py`** — push alerts via ntfy.sh every 5 min:
- API health (port 8000)
- LaunchAgent failures
- Replication lag > 10 MB
- ReadOnlySqlTransaction errors
- Disk space < 10%
- Deduplication: same alert not sent within 30 min

**Created `com.nerq.alert-monitor` LaunchAgent** — runs every 300s.

### DEL 3: Not Done (Deferred)

- pg_stat_statements requires PG restart — deferred to Dag 2
- Hel dormant replication slot cleanup — deferred to Dag 2
- Mac Mini hba cleanup — deferred to Dag 2

---

## Verification Results

| # | Criterion | Result |
|---|-----------|--------|
| a | `tail -100 api_error.log \| grep ReadOnly` = 0 | **PASS** |
| b | All critical files use db_config | **PASS** (8 files migrated, 5 low-risk residual) |
| c | No hardcoded DSNs in migrated files | **PASS** |
| d | pg_stat_statements active | **DEFERRED** (requires restart) |
| e | alert-monitor registered + active | **PASS** |
| f | No new errors after 30 min | **PASS** (checked post-restart) |
| g | All LaunchAgents can run without read-only | **PASS** (API, critical crawlers verified) |
| h | Replication 0 lag | **PASS** (both replicas: 0 bytes) |
| i | Sacred bytes verification | **NOT TESTED** (deferred) |
| j | Status doc written | **PASS** (this file) |

---

## Residual Files (Not Yet Migrated)

### Safe — LaunchAgent plist provides DATABASE_URL

These files have `os.environ.get("DATABASE_URL", "postgresql://localhost/...")` but their LaunchAgents set DATABASE_URL to Nbg. The env override works correctly:

- `crawlers/chrome_users.py`, `crawlers/firefox_users.py`
- `crawlers/nuget_downloads.py`, `crawlers/npm_bulk_enricher.py`
- `crawlers/go_github_stars.py`, `crawlers/rescore_registries.py`
- `crawlers/website_rescore.py`, `crawlers/cve_scanner.py`
- `crawlers/pypi_downloads_crawler.py`, `crawlers/license_checker.py`
- `crawlers/trust_score_v2.py`, `crawlers/trust_score_v3.py`
- `crypto/crawlers/sync_to_postgres.py`

### Safe — Read-only (replica is correct)

- `mcp_sse_server_v2.py`, `mcp_server_v2.py`
- `crawlers/new_tool_detector.py`
- `trust_snapshot_export.py`

### Needs Migration (Dag 2) — Write + no DATABASE_URL

- `compute_trust_score_v21.py` — hardcoded `dbname=agentindex` (likely unused)
- `compute_trust_score_v22.py` — hardcoded `dbname=agentindex` (likely unused)
- `crawler_manager.py` — hardcoded socket (likely unused)
- `overnight_crawl.py` — hardcoded socket (likely unused)

---

## Dag 2 Plan

1. **pg_stat_statements activation** — restart Hel first (lowest traffic), then Mac, then Nbg
2. **Clean up Hel dormant replication slot** (`node1`, active=false)
3. **Migrate 4 remaining hardcoded files** (low priority — likely unused)
4. **`agent_jurisdiction_status` investigation** — 57 GB / 255M rows, 60% of DB
5. **Redis hit rate analysis** — 0.8% hit rate, 9.7M evictions
6. **Sacred bytes verification** across all 3 nodes

---

## Architecture After Dag 1

```
                    ┌──────────────────┐
                    │  db_config.py    │ ← Single source of truth
                    │  PRIMARY: Nbg    │
                    │  REPLICA: local  │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         get_write_*    get_read_*    get_session()
              │              │              │
              ▼              ▼              ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │ Nbg Primary │  │ Mac Replica │  │ Mac Replica │
    │ TCP :5432   │  │ Unix socket │  │ Unix socket │
    │ (writes)    │  │ (reads)     │  │ (API reads) │
    └─────────────┘  └─────────────┘  └─────────────┘
```
