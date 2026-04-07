# S0 Track A — Infrastructure Fixes Applied

**Date:** 2026-03-07
**Status:** Complete

---

## Fix 1: PostgreSQL (P0)

**Action:** `brew services start postgresql@16`
**Result:** PostgreSQL was already running. Verified with `pg_isready` — accepting connections on `/tmp:5432`.

---

## Fix 2: ThrottleInterval on crash-looping plists (P2)

Added `<key>ThrottleInterval</key><integer>10</integer>` to all 4 crash-looping services:

| Plist | ThrottleInterval | Reloaded |
|-------|-----------------|----------|
| com.agentindex.parser.plist | 10s | Yes |
| com.agentindex.mcp-sse.plist | 10s | Yes |
| com.agentindex.dashboard.plist | 10s | Yes |
| com.zarq.mcp-sse.plist | 10s | Yes |

Each plist was unloaded and reloaded via `launchctl unload/load`.

---

## Fix 3: com.agentindex.mcp-sse startup delay (P2)

**Problem:** Port 8300 bind failures (9,359 occurrences) — old process holds port when launchd restarts immediately.

**Action:** Changed ProgramArguments from direct Python invocation to a bash wrapper with 5-second sleep:
```
/bin/bash -c "sleep 5 && exec /Users/anstudio/agentindex/venv/bin/python -m agentindex.mcp_sse_server"
```

Combined with the 10s ThrottleInterval, this gives 15 seconds total before a restart attempt binds the port.

**Result:** Service running (PID 56550), stable after 8-second verification check.

---

## Fix 4: com.nerq.api OOM mitigation (P1)

**Problem:** Exit code -9 (SIGKILL/OOM), 14,174 restarts, 795MB RSS.

**Action:** Added to ProgramArguments in plist:
- `--workers 1` — single worker to cap memory
- `--limit-max-requests 1000` — force worker recycling after 1000 requests to prevent unbounded memory growth

**Result:** Service running (PID 56563), exit code 0.

---

## Verification

All 5 services running with stable PIDs after reload:

```
56560  0  com.zarq.mcp-sse
56547  0  com.agentindex.parser
56550  0  com.agentindex.mcp-sse
56555  0  com.agentindex.dashboard
56563  0  com.nerq.api
```

PostgreSQL: `/tmp:5432 - accepting connections`

---

## Remaining items (not in scope for this task)

- Fix null guard in `crypto_seo_pages.py:374` (cp = cp or 0)
- Add `pool_pre_ping=True` to SQLAlchemy engines
- Fix SQLAlchemy column definition bug in `agentindex/db/models.py`
- Set up log rotation for `api_error.log` (23.6M lines)
