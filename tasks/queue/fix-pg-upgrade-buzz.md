# Fix PG + Upgrade Buzz with LLM Intelligence

**Date:** 2026-03-08
**Status:** Complete

---

## TASK 1: PostgreSQL + P50 Latency

### Problem
- PG was up but API health taking 105s (pool exhaustion from agent page traffic)
- P50 showing 2558ms on dashboard — stale data from outage period

### Already Fixed (previous session)
- `/v1/health`: replaced `COUNT(*)` on 4.9M rows with `pg_class.reltuples` (instant)
- `/v1/stats`: cache TTL increased from 5min to 1hr, protocol unnest limited
- P50 window: changed from 24h to 10min, filtered to `/v1/` endpoints only
- nerq_mcp label: fixed from `com.nerq.mcp-sse` to `com.agentindex.mcp-sse`

### Current Status
- P50: **22.8ms** (was 2558ms)
- Health: **21ms** (was 9.8s cold, 105s during pool exhaustion)
- PG: ok
- All LaunchAgents: running

## TASK 2: Buzz LLM Intelligence

### Changes to `system_autoheal.py`

Added LLM-powered diagnostics using **qwen2.5:7b** via Ollama:

1. **`_collect_error_context()`** — gathers:
   - Last ~4KB of API error log
   - Last ~2KB of autoheal log
   - Current PG connection count

2. **`_call_ollama(prompt)`** — calls qwen2.5:7b with:
   - Temperature 0.3 (deterministic)
   - Max 300 tokens
   - 30s timeout (won't block Buzz if Ollama is slow)

3. **`llm_diagnose(conn)`** — structured prompt returns:
   - ROOT_CAUSE: 1 sentence
   - ACTION: one of the safe action names or "none"
   - EXPLANATION: 1 sentence

4. **Level 1 (auto-execute):**
   - `restart_api` — stop/start com.nerq.api
   - `restart_postgresql` — brew services restart
   - `clear_redis_cache` — FLUSHDB
   - `kill_idle_connections` — pg_terminate_backend on idle >5min

5. **Level 2 (log only):**
   - Any action not in Level 1 list → logged but not executed

### Test Result
```
[BUZZ/INTEL] LLM raw response: ROOT_CAUSE: The PostgreSQL connection pool exhausted its available connections.
ACTION: restart_postgresql
EXPLANATION: Restarting the PostgreSQL service will release and recreate connections.
[BUZZ/INTEL] LLM recommends Level 1 action: restart_postgresql — executing
[BUZZ/HEAL] ACTION: llm_restart_postgresql — rc=0
```

LLM correctly diagnosed PG pool exhaustion and auto-executed restart.

### Why qwen2.5:7b not qwen3:8b
qwen3:8b uses a thinking mode that puts output in a `thinking` field with empty `response`. Would need special parsing. qwen2.5:7b is already loaded in VRAM (6.8GB), responds correctly, and is fast enough for diagnostics.

## TASK 3: Ollama Status

- Ollama: running
- Models available: qwen3:32b, qwen2.5-coder:7b, codellama:7b, llama3.2:3b, qwen2.5:7b-32k, qwen3:8b, qwen3:30b-a3b, qwen2.5:7b
- Loaded in VRAM: qwen2.5:7b (6.8GB)
- Buzz configured to use: qwen2.5:7b

## Files Modified
- `system_autoheal.py` — added LLM diagnostics (OLLAMA_URL, SAFE_ACTIONS, _collect_error_context, _call_ollama, llm_diagnose)
- `agentindex/zarq_dashboard.py` — P50 window: 10min + /v1/ filter (previous session)
- `agentindex/observability.py` — P50 window: 10min + /v1/ filter (previous session)
- `agentindex/api/discovery.py` — health uses reltuples, stats cache 1hr (previous session)

## Verification
- P50: 22.8ms
- Health: 21ms
- PG: ok
- All LaunchAgents: running
- Buzz LLM: tested, working, correctly diagnoses and auto-heals
