# Urgent Fixes — Dashboard Review Follow-up

**Date:** 2026-03-08
**Status:** Complete — 85/85 tests passing

---

## Fix 1: LATENCY CRISIS — RESOLVED

### Root Causes Identified

| Endpoint | Before | After | Root Cause |
|----------|--------|-------|-----------|
| `/v1/health` | 4,846ms avg | **3ms** | Cache defined but never checked |
| `/v1/check/bitcoin` | 824ms avg | **14-32ms** | Correlated subquery on crash_model_v3_predictions |
| `/v1/stats` | 10,631ms avg | **25ms** (cached) | Full-table Python-side protocol counting |

### Changes Made

**`agentindex/api/discovery.py` — Health endpoint cache fix:**
- Added cache check at function start: `if _health_cache["data"] and (_time.time() - _health_cache["ts"]) < _HEALTH_TTL`
- Was computing 2 PostgreSQL COUNT queries (4.9M rows) on every single request
- Now serves from 60-second cache → **1600x improvement**

**`agentindex/crypto/zarq_check_api.py` — CTE replaces correlated subquery:**
- Replaced `AND c.date = (SELECT MAX(date) FROM crash_model_v3_predictions WHERE token_id = s.token_id)` (per-row scan)
- With CTE: `WITH max_crash AS (SELECT token_id, MAX(date) as max_date FROM crash_model_v3_predictions GROUP BY token_id)` (single scan)
- Bitcoin had 256 rows in crash_model, causing O(n²) behavior → **58x improvement**

**`agentindex/api/discovery.py` — SQL-side protocol aggregation:**
- Replaced Python-side protocol counting (loading all agent protocol arrays into memory) with `SELECT unnest(protocols), COUNT(*) GROUP BY proto`
- Cold: 9.4s (expected for 4.9M rows), cached at 25ms for 5 minutes → **425x improvement on cache hits**

**SQLite indexes added:**
- `idx_cmv3_token_date ON crash_model_v3_predictions(token_id, date DESC)`
- `idx_nrs_token_date ON nerq_risk_signals(token_id, signal_date)`

---

## Fix 2: POSTGRESQL — NOT DOWN

PostgreSQL@16 is running and accepting connections. The dashboard was using `pg_isready` which wasn't in PATH.
- Actual binary: `/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/pg_isready`
- Status: `/tmp:5432 - accepting connections`
- No restart needed.

---

## Fix 3: DATA STALENESS — FIXED

### Root Cause: Bug in `crypto_daily_master.py` line 259

```python
# BUG: undefined variables 'run_all' and 'only'
if run_all or only == "risk":  # NameError crashes entire pipeline
```

**Fix applied:** Replaced with properly scoped variables:
```python
run_risk = args.only in (None, "risk")
if run_risk:
```
Also moved Step 5 (risk signals) to execute BEFORE the summary section where it was misplaced.

### Manual Data Refresh
- Ran `nerq_risk_signals.py` — signals updated to 2026-03-08 (was 2026-02-28)
- `crypto_ndd_daily` already current (2026-03-08)
- `crypto_rating_daily` remains at 2026-02-28 — requires CoinGecko API crawl (will run on next daily pipeline at 06:00 CET)
- `/v1/check/bitcoin` now returns `signal_date: "2026-03-08"`

---

## Fix 4: ERROR RATE 3.4% — ANALYZED (No Fix Needed)

Errors are almost entirely scanner noise and expected behavior:

| Endpoint | Status | Count | Cause |
|----------|--------|-------|-------|
| `/internal/metrics` | 401 | 36 | Unauthorized access attempts (working correctly) |
| `/favicon.ico` | 404 | 28 | No favicon file (cosmetic) |
| `/v1/crypto/rating/zzz-*` | 404 | 18 | Test probes for nonexistent tokens |
| `/v1/discover` | 422 | 18 | Validation errors (missing required fields) |
| WordPress probes | 404/405 | 60+ | Bot scanning for WordPress vulnerabilities |

No real bugs. The 401s on `/internal/metrics` confirm auth is working. WordPress probe 404s are expected.

---

## Fix 5: TASK CLEANUP — DONE

Moved 12 completed task files from `tasks/queue/` to `tasks/done/`:
- S0-diagnostics-report, S0-track-a-fixes, S0-track-b-buzz, S0-track-c-separation
- S0-track-d-tests, S0-track-e-observability
- S1-fix-signals, S1-mcp-server
- S2-conversion-and-simulator, S3-agent-distribution, S4-crash-shield
- zarq-dashboard

Remaining in queue (not yet implemented): S1-nerq-cross-pollination, S1-open-api, S1-paper-trading, traffic-analysis

---

## Fix 6: DAILY TRACK RECORD CRON — ACTIVATED

Added to crontab:
```
0 1 * * * /bin/bash /Users/anstudio/agentindex/scripts/run_daily_track_record.sh
```

Verified in `crontab -l` output. Will run daily at 01:00 local time.

---

## Files Modified

| File | Change |
|------|--------|
| `agentindex/api/discovery.py` | Health cache check + SQL protocol aggregation |
| `agentindex/crypto/zarq_check_api.py` | CTE for crash_model join |
| `agentindex/crypto/crypto_daily_master.py` | Fix NameError on line 259 (run_all → run_risk) |
| `agentindex/crypto/crypto_trust.db` | 2 new indexes added |
| `tasks/queue/` → `tasks/done/` | 12 files moved |
| crontab | Daily track record at 01:00 |

## Test Results

```
85 passed, 137 warnings in 47.89s
```
