# ZARQ Incident Report — 2026-05-31

**Status:** Resolved.
**Duration:** 03:00–08:36 CEST (5h 36m end-to-end).
**Customer impact:** 502 from Cloudflare on `zarq.ai` / `nerq.ai` for the
duration. `mcp.zarq.ai` unaffected (separate service on :8001).
**Severity:** P0 — public-facing ZARQ + Nerq dark.

## TL;DR

A Smedjan worker started a 4-hour `SELECT ... FROM agents` paginated batch
on Nbg at 04:00. The query held 6.5 GB RAM and pushed Nbg into swap
thrashing. SQLAlchemy's `pool_pre_ping=True` then amplified every API
request into a worker-killing cascade via `anyio.WouldBlock`. Daily-merge's
03:00 smoke test caught it (0/23 from morning) but Smedjan's silent
rollback meant nothing alerted. Operators discovered the outage at 07:30.

Resolution (this session): paused Smedjan workers, `pg_terminate_backend`
on the runaway pid, fixed the `pool_pre_ping` amplifier, restarted API.
Smoke 23/23, 5-min soak clean, workers resumed.

## Timeline (all times CEST)

| Time | Event |
|---|---|
| 2026-04-28 | Daily-merge cron starts running daily. First rollback tag. |
| 2026-04-28 → 2026-05-30 | Smoke test passes some days, fails others. Silent rollbacks accumulate. No alarm. |
| **2026-05-27 00:32** | First post-Patroni-OOM `statement_timeout` cancel on Nbg targeting software_registry (R-SW root, fixed 2026-05-30). |
| 2026-05-30 ~22:00 | R-SW fixes deployed (`f41eb34`, `04ee95e`, `ef7efe1`). API healthy. |
| 2026-05-31 03:00 | `com.nerq.smedjan.daily-merge` cron fires. Cherry-picks 1 commit, kickstarts API, smoke = **0/23**, rollback. **Silent.** |
| 2026-05-31 04:00 | Smedjan worker on `100.90.152.88` opens a connection to Nbg (`pid 3152538`). Starts paginated `SELECT id, risk_class, agent_type, domains, name, description FROM agents WHERE risk_class IS NOT NULL ORDER BY id LIMIT 5000 OFFSET 1865000`. |
| 2026-05-31 04:00 → 08:00 | Worker holds the connection across many OFFSET batches. By 08:00 it has stepped through 372 OFFSET windows (~1.86 M rows). The current batch alone takes ≥19 minutes due to OFFSET-pagination's O(n) prefix-skip on a 4.98 M-row table. RAM held: 6.5 GB. |
| 2026-05-31 03:00 → 07:30 | Mac Studio `com.nerq.api` keeps restart-looping. Workers can't survive a single request because `pool_pre_ping=True` SELECT 1 piles up in the saturated PgBouncer queue. **+8 LaunchAgent restarts in 35 min** at peak. Cloudflare returns 502. |
| 2026-05-31 07:30 | Operators notice. Manual diagnosis begins. |
| 2026-05-31 07:35 | API booted out via `launchctl bootout` + orphan kill. Restart-loop stopped. |
| 2026-05-31 07:35 → 08:15 | Investigation: rollback tag is a recurring benign Smedjan pattern, not damage; morning tables intact; the actual amplifier is per-request `pool_pre_ping`. See `docs/status/boot-path-pg-deps-20260531.md`. |
| 2026-05-31 08:15 | Smedjan workers a/b/c/d paused (`launchctl bootout`). |
| 2026-05-31 08:17 | `pg_terminate_backend(3152538)` on Nbg. RAM 15 → 13 Gi. Active queries 9 → 3. |
| 2026-05-31 08:23 | Nbg load 43.52 → 5.66. Reachable from Mac Studio again. |
| 2026-05-31 08:24 | `pool_pre_ping=False, pool_recycle=60` committed (`33663c5`). API bootstrapped. |
| 2026-05-31 08:25 | Smoke = base=8/8 + localized=5/5 + sacred=10/10 = **23/23**. (First run was 22/23: `/v1/agent/stats` cold-cache hit 10s timeout; warm runs <50ms; not a boot issue.) |
| 2026-05-31 08:25 → 08:30 | 5-min soak: 0 new restarts, 0 new `anyio.WouldBlock`, 0 new `psycopg2.OperationalError`. All endpoints 200. |
| 2026-05-31 08:30 → 08:35 | Smedjan workers a–d resumed one at a time with 60 s observation. Nbg active queries held at 1–2. No regression. |
| 2026-05-31 **08:36** | **Resolved.** Nbg load 1.87. Endpoints serving normally. |

## Root cause

**Three contributing factors, ranked by leverage:**

### 1. `pool_pre_ping=True` per-request amplifier (PRIMARY)

`agentindex/db/models.py:get_engine()` and `get_write_engine()` had
`pool_pre_ping=True`. Every SQLAlchemy connection checkout ran `SELECT
1` against PgBouncer to validate the connection. Under any PG slowness,
those `SELECT 1`s piled up in PgBouncer's `query_wait_timeout=30s`
queue. After 5 s `pool_timeout` exhausted, requests failed with
`QueuePool exhausted`, BaseHTTPMiddleware's anyio memory stream raised
`WouldBlock` during the in-flight body cleanup, and uvicorn killed the
worker. LaunchAgent `KeepAlive=true` restarted it instantly; next request
hit the same cascade.

Without this amplifier, slow PG queries cause slow responses, not worker
death. With it, the system pivots from "degraded" to "completely down"
on the first wave of saturation.

**Fix:** commit `33663c5`. `pool_pre_ping=False` + `pool_recycle=60`
(was 300). Stale connections will surface as `OperationalError` at first
use rather than as proactive `SELECT 1` validation; the 60s recycle keeps
the stale window short.

### 2. Smedjan worker OFFSET-pagination on `agents` (TRIGGER)

The worker on `100.90.152.88` (Smedjan factory) ran a paginated
`SELECT FROM agents WHERE risk_class IS NOT NULL ORDER BY id LIMIT 5000
OFFSET 1865000`. PG must scan + discard the first 1.86 M rows on every
OFFSET batch. Disk-bound (wait_event = `DataFileRead`), and the
cumulative result-set kept ~6.5 GB resident.

**Fix:** the runaway query was terminated this session. The Smedjan-side
pattern (which Smedjan automation it is, and whether it'll restart on the
next overvintring re-enable) needs a separate fix: switch to keyset
pagination (`WHERE id > :last_id ORDER BY id LIMIT 5000`) or batched
COPY-style exports. Tracked in
`docs/incidents/20260531/followup-smedjan-offset-pagination.md` (to be
written by a future session).

### 3. Smedjan daily-merge canary blindness (META-BUG)

Smedjan's daily-merge at 03:00 has run a smoke test every day since
2026-04-28 and silently rolled back when it failed. The smoke has been
failing daily for ≥5 days (the last 4 saw `base=0/8`, `1/8`, `0/8`,
`0/8`). Nothing read the log. We've been operating blind to the daily
"can the API reboot from scratch?" signal.

**Fix:** `scripts/smedjan_smoke_canary.py` + LaunchAgent
`com.zarq.smedjan-canary` at 03:30 (commit `40c5802`). Parses the
daily-merge log, opens / resolves a `zarq.infrastructure_alerts` row
when the smoke score falls below the floor (default 18/23).

## Fix commits

```
40c5802  docs(status) + feat(infra): incident diagnosis + boot-path inventory + Smedjan canary
33663c5  perf(db): disable pool_pre_ping; pool_recycle=60 (per-request amplifier fix)
```

(Plus commits in the chain that landed yesterday — `f41eb34`, `04ee95e`,
`ef7efe1` — were necessary preconditions; this session would not have
resolved cleanly without yesterday's R-SW STEP 1 + STEP 2 already in.)

## Verification (final, end of session)

| Check | Value | Threshold | Status |
|---|---|---|---|
| Smoke test (Smedjan, warm cache) | 23/23 passed | 23/23 | ✓ |
| API restart count in 5-min soak | 0 | 0 | ✓ |
| `anyio.WouldBlock` in 5-min soak | +0 | 0 | ✓ |
| `psycopg2.OperationalError` in 5-min soak | +0 | 0 | ✓ |
| Nbg load average | 1.87 | <8 | ✓ |
| Nbg active queries | 1 | <10 | ✓ |
| Smedjan workers resumed (a, b, c, d) | 4/4 | 4/4 | ✓ |
| zarq.ai / nerq.ai endpoints | 200 / 200 | 200 | ✓ |

## Lessons

### Smedjan smoke is the canary; read it daily

Five days of `base=0/8 loc=4/5 sb=8/10`-class failures with nothing
reading the log is the kind of slow drift that builds into a P0 outage.
The new canary closes this loop. If `zarq.infrastructure_alerts` is
healthy tomorrow morning, the alert wasn't needed. If it has an open row
for `smedjan-canary`, we'll know within 5 minutes and act.

### `pool_pre_ping=True` is footgun-shaped under PG-saturation conditions

The SQLAlchemy docs frame `pool_pre_ping=True` as a "safety check." It
is — for stale-connection detection. It is NOT safe under PG-saturation
because every checkout becomes a PG round-trip. The right defaults are
short `pool_recycle` (we use 60 s) + applications that handle
`OperationalError` on first use.

### OFFSET-pagination on 5 M-row tables is a saturation generator

The Smedjan worker's pattern (OFFSET 1.86 M) was a slow query type that
would have eventually run anyway, but the per-batch cost grows linearly
with OFFSET. Replacing with keyset pagination removes the entire amplifier
class. This is tracked as a follow-up.

### Pause-resume discipline works

The four-stage approach used here — pause Smedjan, terminate runaway,
verify Nbg, then bring everything back one at a time — kept the system
recoverable at every step. Worth codifying as a runbook for future PG
saturation incidents. Tracked: `docs/runbooks/pg-saturation-recovery.md`
(to be written by a future session).

## Open follow-ups

| Item | Why | Owner | Tracking |
|---|---|---|---|
| Convert Smedjan paginated agents-export to keyset pagination | Removes 4 h-query class permanently | (to assign) | `docs/incidents/20260531/followup-smedjan-offset-pagination.md` (TBD) |
| Verify overvintring status — should workers be running 2026-05-31? | Memory says paused; reality says running | Anders | this incident report |
| Write `docs/runbooks/pg-saturation-recovery.md` | Codify pause→terminate→fix→resume | Next session | this incident report |
| Confirm Smedjan canary fires correctly when smoke fails again | Self-test of the alarm | Tomorrow 03:30 (auto) | LaunchAgent `com.zarq.smedjan-canary` |
| `/v1/agent/stats` cold-cache 4.7s slowness | Made smoke 22/23 on first run | (to assign) | This report |
| Push backlog (was 4 commits ahead before pause; now 6 ahead — confirm Anders is fine with the auto-pushed Smedjan audit commits) | Visibility | Anders | this report |

## Files added / modified

- `docs/incidents/20260531/incident_report.md` (this file)
- `docs/incidents/20260531/smedjan_state_pre_pause.txt`
- `docs/incidents/20260531/smedjan_state_post_pause.txt`
- `docs/incidents/20260531/runaway_query_pid_3152538.txt`
- `docs/status/zarq_incident_20260531_diagnosis.md`
- `docs/status/boot-path-pg-deps-20260531.md`
- `scripts/smedjan_smoke_canary.py`
- `infrastructure/launchd/com.zarq.smedjan-canary.plist`
- `infrastructure/launchd/README.md` (added section for canary)
- `agentindex/db/models.py` (`pool_pre_ping`, `pool_recycle` change)
