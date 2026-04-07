# Fix Save Simulator 502

**Date:** 2026-03-08
**Status:** Complete — was transient

---

## Investigation

1. **Route exists:** `discovery.py:624` imports `router_save_sim` from `agentindex.crypto.zarq_save_simulator`
2. **Local test:** `http://localhost:8000/demo/save-simulator` → 200 (36ms, 11KB)
3. **Alternate path:** `http://localhost:8000/v1/demo/save-simulator` → 200
4. **Tunnel test:** `https://zarq.ai/demo/save-simulator` → 200 (126ms)

## Root Cause

Transient 502 — the server was likely mid-restart when the 502 occurred (server was restarted earlier for `/zarq/docs` route). No code fix needed.

## Verification

| Endpoint | Status | Latency |
|----------|--------|---------|
| `localhost:8000/demo/save-simulator` | 200 | 36ms |
| `zarq.ai/demo/save-simulator` | 200 | 126ms |
| `zarq.ai/v1/check/bitcoin` | 200 | — |
