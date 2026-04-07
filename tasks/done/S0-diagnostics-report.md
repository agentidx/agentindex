# S0 — Sprint 0 Diagnostics Report: Crash-Looping LaunchAgents

**Date:** 2026-03-07
**Track:** A — Infrastructure Hardening
**Status:** Diagnostics complete, fixes pending

---

## Executive Summary

Five LaunchAgent services show exit codes indicating abnormal termination. The root causes are:
1. **PostgreSQL is down** — services using psycopg2 fail on every DB query
2. **Port contention** — `KeepAlive` + port conflicts cause rapid restart loops (9,359 bind failures for MCP SSE alone)
3. **Unhandled NoneType in crypto SEO pages** — causes 500 errors on token pages
4. **SQLAlchemy model bug in parser** — `Boolean` column mapped as `False` literal

All 5 services are currently running but have historically crash-looped extensively. The API error log alone is **23.6M lines**.

---

## Service-by-Service Analysis

### 1. com.nerq.api (PID 54006, exit -9 = SIGKILL)

**Plist:** `~/Library/LaunchAgents/com.nerq.api.plist`
**Command:** `venv/bin/python -m uvicorn agentindex.api.discovery:app --host 0.0.0.0 --port 8000`
**Logs:** `logs/api.log`, `logs/api_error.log`

**Root Cause: OOM kills (SIGKILL = -9) + PostgreSQL connection exhaustion**

Evidence:
- Exit code -9 = SIGKILL, which on macOS means the kernel OOM killer terminated the process
- Memory: currently 1.2% (~795MB RSS) — the largest Python process
- `api_error.log` is **23.6M lines** with **14,174 restarts** recorded
- Errors include:
  - `psycopg2.OperationalError: server closed the connection unexpectedly` — PostgreSQL crashed or restarted
  - `TypeError: '>' not supported between instances of 'NoneType' and 'int'` in `crypto_seo_pages.py:374` — crash_probability (`cp`) is None for some tokens, no null guard
- PostgreSQL is currently **not running** (`pg_isready` fails), yet the API stays up because it also uses SQLite

**Recommended Fix:**
1. Start PostgreSQL and keep it monitored
2. Add null guard in `crypto_seo_pages.py:374`: `cp = cp or 0` before the comparison
3. Add `pool_pre_ping=True` to SQLAlchemy engine to handle stale PG connections
4. Consider adding `ProcessMemoryLimit` to plist or uvicorn `--limit-max-requests` to prevent unbounded memory growth

---

### 2. com.agentindex.parser (PID 72389, exit -15 = SIGTERM)

**Plist:** `~/Library/LaunchAgents/com.agentindex.parser.plist`
**Command:** `venv/bin/python run_parser_loop.py`
**Logs:** `parser.log`

**Root Cause: SQLAlchemy model definition bug (non-fatal) + graceful SIGTERM restarts**

Evidence:
- Exit code -15 = SIGTERM — this is a graceful shutdown signal, not a crash
- Every parse batch ends with: `Parser error: Object False associated with '.type' attribute is not a TypeEngine class or object`
- This means a SQLAlchemy column is defined with `False` instead of `Boolean` (e.g., `Column(False)` instead of `Column(Boolean, default=False)`)
- Despite this error, the parser continues running and processing batches successfully (3-7 agents parsed per batch)
- The SIGTERM likely came from a previous `launchctl stop` or system restart

**Recommended Fix:**
1. Find and fix the column definition in `agentindex/db/models.py` — search for a column where `False` is passed as the type argument
2. This is low-urgency since the parser is functioning despite the error

---

### 3. com.agentindex.mcp-sse (PID 72399, exit -15 = SIGTERM)

**Plist:** `~/Library/LaunchAgents/com.agentindex.mcp-sse.plist`
**Command:** `venv/bin/python -m agentindex.mcp_sse_server` (port 8300)
**Logs:** `mcp_sse.log`

**Root Cause: Port 8300 bind failure causing rapid restart loop**

Evidence:
- **9,359 "address already in use" errors** on port 8300
- **9,368 restarts** total — nearly 1:1 with bind failures
- The pattern: process starts -> port 8300 still held by previous instance -> bind fails -> process exits -> `KeepAlive` restarts immediately -> repeat
- This is a classic `KeepAlive` + `SO_REUSEADDR` issue on macOS
- Log file is 68K lines, mostly healthcheck 404s from something polling `GET /` on 127.0.0.1

**Recommended Fix:**
1. Add `ThrottleInterval` (e.g., 10 seconds) to the plist to prevent rapid restart loops
2. Add `SO_REUSEADDR` / `SO_REUSEPORT` via uvicorn or add a startup delay script
3. Fix the healthcheck poller to use `/health` instead of `/` (which returns 404)

---

### 4. com.agentindex.dashboard (PID 72400, exit -15 = SIGTERM)

**Plist:** `~/Library/LaunchAgents/com.agentindex.dashboard.plist`
**Command:** `venv/bin/python -m agentindex.dashboard` (port 8200)
**Logs:** `dashboard.log`

**Root Cause: PostgreSQL connection exhaustion + PG being down**

Evidence:
- `psycopg2.OperationalError: FATAL: sorry, too many clients already` — PG connection pool exhausted
- `psycopg2.OperationalError: server closed the connection unexpectedly` — PG crashed
- 1 port-bind failure on 8200 (minor, not the primary issue)
- The dashboard queries `SELECT count(agents.id) FROM agents` which requires PostgreSQL
- Also uses deprecated `datetime.utcnow()`
- Exit -15 = SIGTERM, graceful shutdown

**Recommended Fix:**
1. Start PostgreSQL (shared root cause with #1)
2. Reduce connection pool size — CLAUDE.md says max `pool_size=5, max_overflow=5`, verify this is enforced in dashboard code
3. Add `pool_pre_ping=True` to handle stale connections
4. Add fallback/error handling when PG is unavailable (return cached or degraded response instead of crashing)

---

### 5. com.zarq.mcp-sse (PID 72398, exit -15 = SIGTERM)

**Plist:** `~/Library/LaunchAgents/com.zarq.mcp-sse.plist`
**Command:** `venv/bin/python agentindex/crypto/zarq_mcp_server.py --transport sse --port 8001`
**Logs:** `zarq_mcp_sse.log`

**Root Cause: Route returning None + MCP protocol validation errors**

Evidence:
- `TypeError: 'NoneType' object is not callable` — a route handler returns `None` instead of a Response object, triggered when clients hit `/mcp` with GET
- Pydantic validation errors from clients sending non-standard MCP method names (e.g., `ai.smithery/events/topics/list`)
- Only 2 restarts total — this is the healthiest service
- Exit -15 = SIGTERM, graceful shutdown

**Recommended Fix:**
1. Add a proper GET handler for `/mcp` that returns a 405 or redirect to the SSE endpoint
2. Add catch-all error handling for unknown MCP methods
3. Low priority — only 2 restarts and currently stable

---

## Priority Order for Fixes

| Priority | Service | Severity | Effort | Why |
|----------|---------|----------|--------|-----|
| **P0** | PostgreSQL (affects #1, #4) | Critical | Low | Start PG, add monitoring. Root cause of connection errors across multiple services |
| **P1** | com.nerq.api (#1) | High | Medium | Production-facing, 500 errors on token pages, memory leaks causing OOM kills |
| **P2** | com.agentindex.mcp-sse (#3) | High | Low | 9,359 restart loops, add `ThrottleInterval` to plist |
| **P3** | com.agentindex.dashboard (#4) | Medium | Low | Add pool_pre_ping, enforce pool limits |
| **P4** | com.agentindex.parser (#2) | Low | Low | Fix SQLAlchemy column def, parser works despite error |
| **P5** | com.zarq.mcp-sse (#5) | Low | Low | Only 2 restarts, add null-safe route handler |

---

## Shared Root Causes

1. **PostgreSQL is down** — Affects api (#1) and dashboard (#4). Must be started and monitored.
2. **No `ThrottleInterval` in plists** — All 5 plists use `KeepAlive: true` without throttling. When a service crashes, launchd restarts it immediately, causing rapid restart loops (especially with port contention).
3. **No `pool_pre_ping`** — SQLAlchemy connections go stale when PG restarts, causing cascading failures.
4. **Log rotation missing** — `api_error.log` is 23.6M lines. No rotation configured.

## Recommended Immediate Actions

1. `brew services start postgresql@16` (or whichever version is installed)
2. Add `<key>ThrottleInterval</key><integer>10</integer>` to all 5 plists
3. Fix null guard in `crypto_seo_pages.py:374`
4. Set up log rotation for all service logs
