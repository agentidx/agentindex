# Fix /zarq/docs Route

**Date:** 2026-03-08
**Status:** Complete

---

## Investigation

1. Route exists in code: `discovery.py:636` imports `router_docs` from `zarq_docs`
2. Server had stopped (curl returned exit code 7 / HTTP 000)
3. Restarted via `launchctl stop/start com.nerq.api`

## Verification

- `http://localhost:8000/zarq/docs` → **200**
- `https://zarq.ai/zarq/docs` → **200**

Both local and tunnel confirmed working.
