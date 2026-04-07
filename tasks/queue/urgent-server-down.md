# URGENT: zarq.ai Down — Investigation

**Date:** 2026-03-08 16:35
**Status:** Resolved (auto-healed)

---

## Root Cause

**PostgreSQL connection pool exhaustion** — NOT caused by recent dashboard code changes.

```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 5 reached,
connection timed out, timeout 30.00
```

The crash originated in `agentindex/seo_pages.py:377` — agent page queries were exhausting the connection pool (max 5 + 5 overflow = 10 connections).

## Timeline

- **16:20:18** — Autoheal detected API down (port status 000), restarted. Healthy after restart.
- **16:30:19** — Crashed again (same pool exhaustion). Autoheal restarted again at 16:30:32.
- **16:31+** — Stable since second restart.

## Current Status

All endpoints returning 200:
- `http://localhost:8000/v1/health` — 200
- `https://zarq.ai/v1/health` — 200
- `https://zarq.ai/v1/check/bitcoin` — 200
- `/zarq/dashboard` — 200

## Analysis

- **Not our fault**: The crash was in `seo_pages.py` agent page queries hitting PostgreSQL, not in the dashboard/triggers code we modified today.
- **Autoheal worked**: The `system_autoheal.py` correctly detected the outage and restarted the service both times.
- **Recurring issue**: Pool exhaustion suggests either connection leaks or burst traffic hitting agent pages. Current pool config: `pool_size=5, max_overflow=5`.

## Potential Fixes (for later)

1. Increase pool size: `pool_size=10, max_overflow=10`
2. Add `pool_pre_ping=True` to recycle stale connections
3. Ensure all sessions are properly closed with `try/finally` in seo_pages.py
4. Add `pool_recycle=3600` to prevent stale connections

## Files Involved

- `agentindex/seo_pages.py:377` — source of pool exhaustion
- `agentindex/db/models.py` — pool configuration
- `system_autoheal.py` — correctly auto-healed

## Result

Server is stable. No action needed now — autoheal is working. Pool size increase recommended for Sprint 0 infrastructure hardening.
