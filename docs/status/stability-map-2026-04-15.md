# Stability Map — 2026-04-15

**Purpose:** Complete system audit post-primary-switch (Day 6c). READ-ONLY — no changes made.
**Author:** Claude (stability sprint Day 1)
**Goal:** Provide enough data for a stabilization plan without further exploration needed.

---

## 0. Executive Summary — The Root Cause

**The API is writing to a read-only replica.** After Day 6c primary switch (Mac → Nbg), the API LaunchAgent retained `DATABASE_URL=postgresql://localhost/agentindex`. Localhost is now a read-only replica. Every write attempt fails with `ReadOnlySqlTransaction`. 128 occurrences logged in `api_error.log`.

Additionally: 22 LaunchAgents have NO `DATABASE_URL` set and fall back to localhost/socket defaults — which also hit the read-only replica. `compute_trust_score.py` is hardcoded to `dbname=agentindex` (socket).

---

## 1. LaunchAgents Inventory (40 agents)

### DATABASE_URL Audit — The Critical Finding

| Category | Count | Points to |
|----------|-------|-----------|
| Correctly set to Nbg (100.119.193.70) | **17** | Primary (correct) |
| Set to localhost | **1** (api) | **Read-only replica (BROKEN)** |
| NOT SET (defaults to localhost) | **22** | **Read-only replica (BROKEN for writes)** |

### Agents correctly pointing to Nbg (17)

badge-discovery, badge-outreach, chrome-users, community-signals, compat-matrix, contributor-metrics, crypto-daily, dashboard-data, dex-volumes, firefox-users, go-github-stars, npm-bulk-enricher, npm-dependency-collector, nuget-downloads, openssf-crawler, osv-crawler, signal-warehouse

### Agents WITHOUT DATABASE_URL (22) — all default to localhost (replica)

analytics-aggregation, analytics-cache, analytics-weekly-cache, auto-indexnow, badge-responder, cache-warmer, capacity-check, cve-alerts, daily-backup, daily-scores, freshness-daily, king-refresh, kpi-csv, master-watchdog, npm-crawler, paper-trading-daily, performance-guardian, reach-dashboard, scout, stale-scores, yield-orchestrator, zarq-cache

### API plist — the most critical one

```
DATABASE_URL=postgresql://localhost/agentindex  ← POINTS TO REPLICA
```

The API runs 16 uvicorn workers, each with a connection pool (pool_size=5, max_overflow=5). All writes via `get_session()` hit the local replica and fail.

### Failing Agents (non-zero exit)

| Agent | Exit Code | Root Cause |
|-------|-----------|------------|
| api | 1 (but running via KeepAlive) | PG connection drops, read-only errors |
| zarq-cache | 2 | Script timing out every 4 min (300s limit) |
| stale-scores | 1 | Queries `entity_lookup.trust_calculated_at` — column doesn't exist |
| crypto-daily | 1 | Unknown — runs daily |
| dashboard-data | 1 | Unknown — runs daily |
| nuget-downloads | 1 | `UPDATE in read-only transaction` (before plist was fixed) |

### ZARQ_PG_DSN (dual-write) — All correctly set to Nbg (7 agents)

community-signals, compat-matrix, crypto-daily, dashboard-data, dex-volumes, openssf-crawler, osv-crawler

### Python Interpreter Inconsistency

| Interpreter | Agents |
|-------------|--------|
| `/Users/anstudio/agentindex/venv/bin/python` | Most (35+) |
| `/opt/homebrew/bin/python3` | npm-dependency-collector, dex-volumes |
| `/usr/bin/python3` | npm-crawler |
| `/usr/bin/env python3` | badge-outreach |

---

## 2. Database Connections Map

### Postgres Connection Patterns

| # | Pattern | Env Var | Default DSN | When unset → |
|---|---------|---------|-------------|-------------|
| 1 | `get_session()` (SQLAlchemy) | `DATABASE_URL` | `postgresql://localhost/agentindex` | **Replica (broken for writes)** |
| 2 | `dual_write.py` | `ZARQ_PG_DSN` | `host=100.90.152.88` | **Old primary IP (pre-switch)** |
| 3 | `dual_read.py` | `DATABASE_URL` | `host=100.90.152.88` | **Old primary IP (pre-switch)** |
| 4 | Direct `psycopg2.connect()` | varies | varies | varies |

### Hardcoded DSNs — Danger Zone

| File | Hardcoded DSN | Problem |
|------|--------------|---------|
| `dual_write.py` | `host=100.90.152.88` (default) | **Old Mac primary IP** |
| `dual_read.py` | `host=100.90.152.88` (default) | **Old Mac primary IP** |
| `compute_trust_score.py` | `dbname=agentindex` (socket) | **Connects to local replica** |
| `compute_trust_score_v21.py` | `dbname=agentindex` (socket) | Same |
| `compute_trust_score_v22.py` | `dbname=agentindex` (socket) | Same |
| `trust_snapshot_export.py` | `dbname=agentindex` (socket) | Same |
| `overnight_crawl.py` | `dbname=agentindex` (socket) | Same |
| `crawler_manager.py` | `dbname=agentindex` (socket) | Same |
| `scripts/backfill_tier_a_gap.py` | `host=/tmp` (socket) | Same |

### SQLite Databases

| Path | Size | Growth Rate |
|------|------|-------------|
| `agentindex/crypto/zarq_api_log.db` | **18 GB** | Not in CLAUDE.md — unchecked |
| `logs/analytics.db` | **11 GB** | ~370 MB/day (was 8.77 GB on Apr 9) |
| `agentindex/crypto/crypto_trust.db` | **1.2 GB** | Was 379 MB (CLAUDE.md) — 3x growth |
| `logs/ab_events.db` | 370 MB | Unknown |
| `data/indexnow_submit_tracking.db` | 353 MB | Unknown |
| Total SQLite on disk | **~31 GB** | |

---

## 3. Postgres State

### Node Overview

| | Mac (local) | Nbg (primary) | Hel (replica) |
|-|-------------|---------------|---------------|
| Version | 16.11 | 16.13 | 16.13 |
| Role | **REPLICA** | **PRIMARY** | REPLICA |
| Start time | Apr 14 12:37 | Apr 14 12:07 | Apr 15 07:23 |
| Uptime | ~21h | ~21.5h | ~2.5h |
| Extensions | plpgsql, pg_trgm, amcheck | Same | Same |
| pg_stat_statements | **NOT installed** | **NOT installed** | **NOT installed** |

### Version Skew

Mac is PG 16.11, Nbg/Hel are PG 16.13 (two minor versions behind).

### Top 10 Tables by Size

| Table | Size | Live Tuples (Nbg stats) | Actual Count | Notes |
|-------|------|------------------------|--------------|-------|
| agent_jurisdiction_status | **57 GB** | 0 (stats broken) | **255,576,828** | Never vacuumed/analyzed |
| agents | 17 GB | 0 (stats broken) | ~5M (estimated) | Never analyzed |
| daily_snapshots | 9.8 GB | 33,436,602 | — | Analyzed recently |
| software_registry | 4.1 GB | 0 (stats broken) | ~2.5M | Never analyzed |
| entity_lookup | 3.2 GB | 5,037,019 | — | Analyzed recently |
| trust_score_history_deprecated | 2.2 GB | 0 | 4,808,972 | **DEPRECATED — safe to DROP** |
| crawl_queue | 1.0 GB | 2,106,754 | — | |
| crypto_ndd_alerts | 328 MB | 0 (stats broken) | — | zarq schema |
| crypto_price_history | 301 MB | 0 (stats broken) | — | zarq schema |
| crypto_ndd_daily | 132 MB | 0 (stats broken) | — | zarq schema |

**Total database size: 94 GB**

### Critical: `agent_jurisdiction_status` = 57 GB (60% of DB)

- 255M rows, 57 GB
- `n_live_tup = 0`, `n_dead_tup = 0` — autovacuum stats completely stale
- Never vacuumed, never analyzed
- This single table is larger than the rest of the database combined

### Critical: Stats Collection Broken

The largest tables (`agent_jurisdiction_status`, `agents`, `software_registry`) show `n_live_tup = 0` on the primary. `last_vacuum = NULL`, `last_autovacuum = NULL`, `last_analyze = NULL`. Autovacuum is either not running or unable to complete on these tables. This means the query planner has no statistics and is making suboptimal plans.

### Replication Slots

| Slot | Node | Active | Status |
|------|------|--------|--------|
| node2 | Nbg | **yes** | Feeding Hel |
| mac_studio_slot | Nbg | **yes** | Feeding Mac |
| node1 | Hel | **no** | Dormant — retaining WAL unnecessarily |

### Connections

Mac has **66 connections** from the application (SQLAlchemy pool). Nbg has 8, Hel has 4. The 66 connections on a replica are from the API's 16 workers × pool_size=5 — they work for reads but all writes fail.

### Sequences — Split-Brain Evidence

Several sequences on Mac are **ahead** of Nbg (Mac was previously primary):

| Sequence | Mac | Nbg | Delta |
|----------|-----|-----|-------|
| daily_snapshots_id_seq | 50,626,392 | 50,626,360 | Mac +32 |
| ai_behavior_daily_id_seq | 25,030 | 24,999 | Mac +31 |
| trust_changes_id_seq | 1,222,154 | 1,222,127 | Mac +27 |
| signal_events_id_seq | 24,595 | 24,570 | Mac +25 |

This is expected after pg_rewind — sequences on Mac retained pre-switch values. Not a data integrity issue but confirms the timeline.

---

## 4. Endpoints & API

### Route Count

**51 routes** registered in `discovery.py` (GET + POST + routers).

### Endpoint Latency (3 tests each)

| Endpoint | localhost avg | nerq.ai avg |
|----------|-------------|-------------|
| `/` | 5ms | 95ms |
| `/safe/nordvpn` | 4ms | 64ms |
| `/categories` | 5ms | 71ms |
| `/best/vpn` | 8ms | 70ms |
| `/v1/crypto/rating/bitcoin` | 22ms | 123ms |
| `/v1/preflight?target=openai` | 53ms | 55ms |

All returning 200. Latency is healthy — Cloudflare overhead is 30-130ms (ARN PoPs).

### Replication Status

| Replica | State | Lag |
|---------|-------|-----|
| node2 (Hel) | streaming | **0 bytes** |
| mac_studio | streaming | **0 bytes** |

Replication is fully caught up.

---

## 5. Cloudflare & Networking

### Tunnel Config

- **Tunnel ID:** `a17d8bfb-9596-4700-848a-df481dc171ad`
- **Connections:** 4 active (2× arn02 + 2× arn07, Stockholm)
- **Second tunnel:** `lightf1ow` (inactive, 0 connections)

### Ingress Rules (11 hostnames)

| Hostname | Backend |
|----------|---------|
| nerq.ai | localhost:8000 |
| api.nerq.ai | localhost:8000 |
| zarq.ai | localhost:8000 |
| api.zarq.ai | localhost:8000 |
| agentcrawl.dev | localhost:8000 |
| api.agentcrawl.dev | localhost:8000 |
| dash.nerq.ai | localhost:8203 |
| mcp.nerq.ai | localhost:8300 |
| mcp.zarq.ai | localhost:8001 |
| dash.agentcrawl.dev | localhost:8203 |
| mcp.agentcrawl.dev | localhost:8300 |

**All traffic goes through Mac Studio's Cloudflare tunnel.** Hetzner nodes are not serving any external traffic directly.

### DNS

All three domains (nerq.ai, zarq.ai, agentcrawl.dev) resolve to Cloudflare proxy IPs.

---

## 6. Observability Gaps

### Alerting

- **ntfy.sh:** Configured in `scripts/external_alert.py` but no LaunchAgent runs it. Not actively alerting.
- **Discord:** Broken. WebSocket closes with code 1005/1006. Anders receives NO Buzz reports.
- **Healthcheck endpoint:** `/v1/health` exists but no external monitoring consumes it.

### Missing Monitoring

- No LaunchAgent for `external_alert.py`
- No uptime monitoring (Pingdom, UptimeRobot, etc.)
- No pg_stat_statements for query performance
- No alerting on LaunchAgent failures
- No disk growth alerts

### Buzz Status

- Running (session file 1 MB, last modified 09:29 today)
- Discord delivery **fully broken** for 18+ hours
- 6 cron delivery failures across 3 job IDs
- Running openclaw `v2026.2.22-2` (nearly 2 months behind latest `v2026.4.14`)
- OPERATIONSPLAN.md still stale (February 2026)

---

## 7. Anomalies

### RAM: 60 GB / 64 GB Used

**Top 11 processes are ALL idle PostgreSQL backends**, each 1.2-2.0 GB RSS:

| PID | %MEM | RSS | Notes |
|-----|------|-----|-------|
| 16310 | 3.0% | 2.0 GB | Idle PG backend |
| 43161 | 2.8% | 1.9 GB | Idle PG backend |
| 43150 | 2.6% | 1.75 GB | Idle PG backend |
| 56596 | 2.5% | 1.7 GB | ... |
| 24972 | 2.5% | 1.66 GB | ... |
| 56620 | 2.5% | 1.65 GB | ... |
| 52854 | 2.5% | 1.65 GB | ... |
| 58819 | 2.4% | 1.63 GB | ... |
| 94516 | 2.0% | 1.33 GB | ... |
| 52848 | 1.9% | 1.26 GB | ... |
| 95882 | 1.8% | 1.21 GB | ... |

**11 idle PG backends consume ~18 GB.** These are the API's SQLAlchemy pool connections to the local replica. With 16 workers × pool_size=5 = 80 potential connections, but only ~66 are active.

### Redis

| Metric | Value |
|--------|-------|
| Used memory | 2.43 GB |
| Max memory | 4.00 GB |
| Evicted keys | **9,714,810** |
| Keyspace hits | 93,051 |
| Keyspace misses | 11,425,504 |
| **Hit rate** | **0.8%** |

Redis is functionally useless. 99.2% cache miss rate. 9.7M keys evicted. The page cache middleware (Redis db1, 69K keys, 2 GB) is competing with other Redis usage and being constantly evicted.

**Note:** CLAUDE.md says Redis maxmemory was increased to 2 GB. The actual current value is 4 GB. This was likely changed without documentation.

### Disk

| Path | Size |
|------|------|
| `/Users/anstudio/agentindex/logs/` | **34 GB** |
| `logs/analytics.db` | 11 GB (growing 370 MB/day) |
| `agentindex/crypto/zarq_api_log.db` | 18 GB |
| Total disk used | 11 GB / 1.8 TB (1%) |

Disk is not an immediate concern but analytics.db will be 30 GB within 2 months at current growth.

### Read-Only Transaction Errors

**128 occurrences** in `api_error.log`:
```
Failed to create user_reviews table: (psycopg2.errors.ReadOnlySqlTransaction) 
cannot execute CREATE TABLE in a read-only transaction
```

Source: `agentindex/review_pages.py:47` — tries `CREATE TABLE IF NOT EXISTS user_reviews` on every request. Since local PG is a replica, this fails every time.

Also in `nuget_enrichment.log`:
```
cannot execute UPDATE in a read-only transaction
```

### Log Growth

No log files exceed 100 MB currently. Largest: `api.log` at 82 MB.

---

## 8. Known Pre-Existing Bugs

| Bug | File | Symptom | Status |
|-----|------|---------|--------|
| `trust_calculated_at` missing | `stale_score_detector.py:153` | Queries `entity_lookup.trust_calculated_at` — column doesn't exist. Needs LEFT JOIN agents. | **Active — stale-scores exits 1 daily** |
| `npm_weekly` column missing | `compatibility_matrix.py:196` | Queries SQLite `npm_weekly` column from `package_downloads` — doesn't exist. | **Active — compat-matrix fails weekly** |
| `yield_crawler_status` missing | `system_healthcheck.py:680` | Queries missing table in healthcheck.db. | **Active — autoheal warns every 3 min** |
| Newsletter model hardcoded | Buzz newsletter job | `anthropic/claude-sonnet-4-20250514` not allowed. | **Active — failing 2+ weeks** |
| OPERATIONSPLAN.md stale | `~/.openclaw/workspace/` | Dated February 2026. Buzz monitors port 8100 (doesn't exist). | **Active** |
| Discord broken | openclaw gateway | WebSocket 1005/1006 closures. | **Active 18+ hours** |
| `user_reviews` CREATE TABLE | `review_pages.py:51` | Tries CREATE TABLE on replica — fails on every request. | **NEW — caused by Day 6c switch** |

---

## 9. Changes from Yesterday-Today

### Day 6c Primary Switch (Apr 14 12:03-12:38)

- Nbg promoted to primary via Patroni
- Mac demoted to streaming replica
- Hel reconfigured as Patroni replica of Nbg
- 15 LaunchAgent plists updated: `100.90.152.88` → `100.119.193.70`
- Patroni config fix: `etcd:` → `etcd3:` (etcd v2 API disabled)
- pg_rewind: 37 GB over Tailscale (25 min)
- Mac replication slot `mac_studio_slot` created

### Post-Switch Fixes (Apr 14-15)

- signal-warehouse: added DATABASE_URL to plist
- signal-warehouse: batched agent snapshots, 300s timeout, resilient collectors
- daily_snapshots: unique index `idx_ds_unique`, removed 482K duplicates
- trust_score_history: deprecated (renamed to `_deprecated`)
- paper-trading: fixed JS percentage display (×100), made page fully dynamic
- paper-trading: excluded from Redis page cache, set s-maxage=300
- Contributor metrics: new table + collector + trust score integration
- Dependency graph: new table + collector (19K/528K packages processed)
- History API: `GET /api/v1/trust-score/{id}/history` — new endpoint

---

## 10. Ranked Root Cause Hypotheses

### #1: API DATABASE_URL points to read-only replica (HIGH CONFIDENCE)

**Evidence:**
- API plist: `DATABASE_URL=postgresql://localhost/agentindex`
- Mac is `pg_is_in_recovery() = true` (replica since Day 6c)
- 128 `ReadOnlySqlTransaction` errors in api_error.log
- `review_pages.py` tries CREATE TABLE on every request, fails every time
- nuget_enrichment.log shows UPDATE failures

**Contradicting:** API still serves reads fine (all endpoints return 200). The bug only manifests on writes.

**Impact:** Any API-initiated write (user reviews, dynamic table creation) fails silently. Most reads work because the replica has the data.

### #2: 22 LaunchAgents without DATABASE_URL default to localhost (HIGH CONFIDENCE)

**Evidence:**
- 22 agents have no DATABASE_URL in their plist
- `get_session()` defaults to `postgresql://localhost/agentindex`
- Scripts using `dbname=agentindex` (socket) connect to local replica
- `compute_trust_score.py` hardcoded to `dbname=agentindex`

**Impact:** Any agent that writes and lacks DATABASE_URL will fail. Agents that only read (analytics, cache warmers) work fine.

### #3: PostgreSQL stats collection broken — planner flying blind (MEDIUM CONFIDENCE)

**Evidence:**
- `agent_jurisdiction_status` (57 GB, 255M rows) shows `n_live_tup = 0`
- `agents` (17 GB, ~5M rows) shows `n_live_tup = 0`
- `software_registry` (4.1 GB) shows `n_live_tup = 0`
- `last_analyze = NULL`, `last_autovacuum = NULL` for all large tables
- Only recently-created tables have analyze data

**Contradicting:** Query performance is actually fine (22ms for crypto rating). Autovacuum may be working but stats haven't been reported to `pg_stat_user_tables` yet (possible with a fresh primary after pg_rewind).

**Impact:** Query planner makes suboptimal plans. Could explain sporadic timeouts on large queries (signal-warehouse batch inserts).

### #4: Redis cache functionally dead — 0.8% hit rate (MEDIUM CONFIDENCE)

**Evidence:**
- 9.7M keys evicted
- 93K hits vs 11.4M misses
- Page cache (db1) has 69K keys using 2 GB
- Constant eviction cycle: new pages cached → immediately evicted by next batch

**Contradicting:** Redis is at 2.43 GB / 4 GB — not full. The low hit rate may be structural (too many unique pages, not enough repeated access).

**Impact:** Every page request is a cold render from Postgres. No caching benefit. All 16 workers hit PG for every request.

### #5: Memory pressure from idle PG backends (MEDIUM CONFIDENCE)

**Evidence:**
- 11 idle PG backends consume ~18 GB RSS
- System at 60/64 GB (3 GB free)
- These are connections to the LOCAL REPLICA — they serve reads for the API
- 16 workers × pool_size=5 = 80 potential connections

**Contradicting:** The system hasn't OOM'd. macOS manages memory pressure with compression (4.2 GB compressor). Idle PG backends should release memory under pressure.

**Impact:** Leaves minimal headroom for other processes. Any memory spike (trust score recalc, large query) could cause swapping.

---

## Appendix A: Critical Actions Needed (for stabilization plan)

1. **Fix API DATABASE_URL** — point to Nbg primary for writes, keep replica for reads (or just point everything to Nbg)
2. **Add DATABASE_URL to 22 agents** — any that write need Nbg, read-only agents can stay on localhost
3. **Run ANALYZE on large tables** — `agent_jurisdiction_status`, `agents`, `software_registry` need fresh stats
4. **Investigate `agent_jurisdiction_status`** — 57 GB / 255M rows. Is this intentional? Can it be truncated or archived?
5. **Fix Redis hit rate** — either increase maxmemory or reduce what gets cached
6. **Fix `review_pages.py`** — stop trying CREATE TABLE on a replica

---

*End of stability map. No changes were made during this audit.*
