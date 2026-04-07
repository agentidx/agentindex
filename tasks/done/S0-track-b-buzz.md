# S0 Track B — Robust Buzz (Local LLM Health System)

**Date:** 2026-03-07
**Status:** Complete — 49/49 tests passing

---

## Assessment: What Buzz Already Monitors

The existing healthcheck (`system_healthcheck.py`) + autoheal (`system_autoheal.py`) run every 5 min via cron and cover:

| Check | Component | Auto-heal? |
|-------|-----------|------------|
| PostgreSQL connections/queries/locks/idle-tx | Nerq | Yes (kills stuck queries, idle-tx, lock storms) |
| API port 8000 | Shared | Yes (restarts via LaunchAgent) |
| MCP port 8300 | Shared | No |
| Process counts (6 services) | Shared | Yes (kickstart/reload LaunchAgents) |
| Disk space | Shared | No |
| Redis | Shared | Yes (brew services restart) |
| Ollama | Nerq | No |
| Cloudflare tunnel | Shared | No |
| Parser state (suspended) | Nerq | Yes (kill -9 + restart) |
| Agent count trend | Nerq | No |
| Yield API/crawler | ZARQ | No (warn only) |
| Hung cron jobs | Shared | Yes (kill -9 after 60 min) |

### What Was MISSING for ZARQ

1. NDD pipeline staleness — no check if risk signals stop updating
2. Trust Score age — no check if ratings go stale
3. API response time — only checks port, not latency
4. Observability DB writes — no check if logging is working
5. Circuit breakers — no protection against external API failures (CoinGecko, DeFiLlama)

---

## What Was Built

### 1. ZARQ Healthcheck (`zarq_healthcheck.py`)

Five new checks:

| Check | Thresholds | Metric |
|-------|-----------|--------|
| NDD pipeline staleness | >1d = WARN, >3d = ERROR | `zarq.ndd_signal_age_days` |
| Trust Score age | >1d = WARN, >3d = ERROR | `zarq.trust_score_age_days` |
| API responsiveness | >2s = WARN, timeout = ERROR | `zarq.api_health_latency_ms` |
| Observability DB activity | >10 min since write = WARN | `zarq.obs_db_age_minutes` |
| Circuit breaker status | Any open circuit = WARN | (per-circuit state) |

Results saved to `zarq_healthcheck` table in `logs/healthcheck.db`. Metrics saved with `zarq.` prefix to `healthcheck_metrics`.

### 2. Integration with Main Healthcheck

`system_healthcheck.py` now calls `run_zarq_checks()` at the end of every run. ZARQ warnings/errors are merged into the main result and affect the overall status. Runs automatically via existing cron (every 5 min).

### 3. Circuit Breaker (`agentindex/circuit_breaker.py`)

Thread-safe circuit breaker for external APIs:

- **Threshold:** 3 consecutive failures opens circuit
- **Backoff:** Exponential (30s -> 60s -> 120s -> ... -> 10 min max)
- **Recovery:** Single success resets to closed
- **API:** `is_available(name)`, `record_success(name)`, `record_failure(name)`, `get_circuit_status()`
- **Integration:** Healthcheck queries circuit status and warns on open circuits

Ready to be wired into CoinGecko/DeFiLlama callers (wrap existing HTTP calls with `is_available()` check + `record_success()`/`record_failure()`).

---

## Files Created/Modified

| File | Change |
|------|--------|
| `zarq_healthcheck.py` | **New** — 5 ZARQ-specific healthchecks |
| `agentindex/circuit_breaker.py` | **New** — Circuit breaker with exponential backoff |
| `system_healthcheck.py` | **Modified** — Calls ZARQ checks, merges results |
| `tests/test_circuit_breaker.py` | **New** — 10 tests |
| `tests/test_zarq_healthcheck.py` | **New** — 10 tests |

## Test Results

```
49 passed, 62 warnings in 45.31s
```

- 29 API tests (unchanged, no regressions)
- 10 circuit breaker tests (state transitions, backoff, caps, recovery)
- 10 ZARQ healthcheck tests (structure, required fields, types)

## Live Run Output

```
2026-03-07 [ZARQ/ERROR] NDD pipeline stale: last signal 2026-02-28 (7d ago)
2026-03-07 [ZARQ/ERROR] Trust Scores stale: last run 2026-02-28 (7d ago)
2026-03-07 [ZARQ/INFO]  obs_db_active: true, circuit_breakers: {}
```

The staleness alerts are real — the crypto daily pipeline hasn't run since 2026-02-28. This is exactly the kind of issue Track B was designed to catch.
