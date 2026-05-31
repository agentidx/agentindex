# Crypto pipeline failure diagnosis — 2026-05-31

**Status:** diagnostics only. No fixes applied. No retry.
**Pipeline:** `com.nerq.crypto-daily` LaunchAgent, runs 04:00 CET daily.

## A. TL;DR

The crypto pipeline has been **failing silently for ≥48 hours**. Last
successful pipeline_runs entry: `id=374, run_date=2026-05-29, status=OK,
total=495s`. Today's auto-cron at 04:00 CET ran for 27 min and produced
no usable data; the manual rerun this morning (FAS B1) reproduced the
same failure surface but with a different error pattern.

Data-freshness consequence:
- `zarq.nerq_risk_signals`: last row **2026-05-29 22:40** (~36 h stale)
- `zarq.crypto_pipeline_runs`: last OK row **2026-05-29 21:14**
- The Smedjan canary did **not** alert (it watches Smedjan smoke, not
  crypto pipeline). See `docs/tracking/pipeline-success-canary.md`.

Three root causes are described below. None are intermittent — the
auto-cron run logs and the manual run both show predictable failures
each at the same call sites. They are also **independent**: fixing
R-PIPE-2 will unblock the pipeline; R-PIPE-1 is a robustness gap; R-PIPE-3
is a latent slowness that hides behind the others.

## B. Root causes

### R-PIPE-1: subprocess `from agentindex.*` only resolves under LaunchAgent env

**Trigger:** Running `crypto_daily_master.py` manually from a shell
without `PYTHONPATH=/Users/anstudio/agentindex` set.

**Evidence:**
- Plist `/Users/anstudio/Library/LaunchAgents/com.nerq.crypto-daily.plist`
  sets `PYTHONPATH=/Users/anstudio/agentindex` and
  `WorkingDirectory=/Users/anstudio/agentindex`. Plist last modified
  2026-04-15 09:27 — **unchanged for 6+ weeks**, not the recent regression.
- `crypto_daily_master.py:70` spawns each step via
  `subprocess.run(cmd, cwd=SCRIPT_DIR, capture_output=True, text=True,
  timeout=timeout_min*60)` — **no `env=` parameter passed**. Children
  inherit master's env.
- In MY manual run today (`cd ~/agentindex && venv/bin/python
  agentindex/crypto/crypto_daily_master.py`), no `PYTHONPATH` was set
  in the shell. Children's sys.path = `[crypto/, site-packages, ...]`.
  `agentindex.crypto.dual_write` is at
  `~/agentindex/agentindex/crypto/dual_write.py`. To import `agentindex.*`
  Python needs `~/agentindex` on sys.path. It is not.
- Reproduced directly:
  - From `~/agentindex`: `python -c "from agentindex.crypto.dual_write
    import dual_execute"` → **OK**
  - From `~/agentindex/agentindex/crypto/`: same command → **fails with
    `ModuleNotFoundError: No module named 'agentindex'`**
  - From `~/agentindex/agentindex/crypto/` with
    `PYTHONPATH=/Users/anstudio/agentindex`: → **OK**
- Auto-cron 04:00 today did NOT fail with this error (it failed with
  R-PIPE-2 instead) — confirming LaunchAgent's PYTHONPATH is what
  prevents this failure mode in production.

**Hypothesis:** the manual rerun reproduces R-PIPE-1, but R-PIPE-1 has
**never been a production failure**. It is a robustness gap: the master
script should set `env=os.environ` (or explicitly add PYTHONPATH) so the
pipeline can be run by humans from a fresh shell. Today's manual rerun
exposed this gap; auto-cron survives by inheriting plist env.

**One-line fix (NOT applied):** add `env={**os.environ, "PYTHONPATH":
str(REPO_ROOT)}` to `subprocess.run(...)` in `crypto_daily_master.py:70`.

### R-PIPE-2: SQLite `database is locked` — the actual production blocker

**Trigger:** `crypto_trust.db` is held open by `zarq_mcp_server.py`
(pid 1017, started 2026-05-27 19:30 — 4 days ago, running since before
the last successful pipeline run on 2026-05-29).

**Evidence (auto-cron 04:00 today, `crypto_daily_stdout.log`):**
- Step 4 (NDD distress): `sqlite3.OperationalError: database is locked`
  at `dual_write.py:245` → `sqlite_conn.execute(sql, params or ())`.
- Step 5 (risk_signals): same error at `dual_write.py:281` →
  `sqlite_conn.executemany(sql, rows)`.
- Step 2 (fetch_prices): same error at
  `crypto_price_pipeline.py:807` (sqlite write in different code path).
- Master writeback: "Could not save run status: database is locked" —
  the master's own write to `pipeline_runs` failed for the same reason.
- Step 4b (defillama_fallback): timed out at 10 min, likely waiting
  for the same lock.
- Step 3 (credit_rating): ✅ OK in auto-cron — it doesn't write to the
  same SQLite hot rows.

**lsof evidence:**
- Pid 1017 (`zarq_mcp_server.py --transport sse --port 8001`) holds
  `crypto_trust.db` with fd `3u` (read+write).
- API process (pid 31332) does **not** hold the SQLite file.
- Etime on MCP server: 4d 13h 43m → started 2026-05-27 ~19:30. MCP was
  up during the 2026-05-29 successful run too, so the lock isn't
  always-on; it's intermittent based on whether MCP holds an open
  write transaction when the pipeline tries to write.

**Hypothesis:** `zarq_mcp_server.py` keeps a long-lived SQLite
connection with implicit transaction state. Under load, SQLite's
default journal mode (`rollback` or `delete`) makes any open writer
block all other writers. The pipeline's `dual_write.execute` waits up
to SQLite's default busy timeout (~5 s) and then raises `database is
locked`.

**Why 2026-05-29 worked:** race condition. MCP wasn't in an open
transaction at the moment the pipeline tried to write. Or MCP was
doing only reads. Or the busy-timeout window happened to be quiet.
Not reproducible to "always works" without removing the contention.

**Possible fixes (NOT applied — listed for prioritization):**
- Switch `crypto_trust.db` to WAL mode (`PRAGMA journal_mode=WAL`):
  allows concurrent reader + writer. Highest leverage.
- Increase SQLite busy timeout in dual_write (`PRAGMA busy_timeout=30000`).
- Stop MCP server before pipeline runs (recover bypass — has 8001
  downtime). Not ideal.
- Move zarq.nerq_risk_signals etc to Postgres-only and stop dual-writing
  to SQLite (long-term direction).

**Why I have NOT applied a fix:** Anders' instruction was diagnostics
only, and the MCP server's open file handles are evidence for diagnosis.
Restarting MCP would destroy the evidence and possibly mask a deeper
issue (e.g. a corrupted journal file).

### R-PIPE-3: step 3 (credit_rating) slowness — masked by other failures

**Trigger:** unclear. Step 3 timed out at 15 min in my manual run, but
ran to completion ✅ in the auto-cron run (with 27 min total pipeline
time, vs the 8 min reference baseline from 2026-05-29).

**Evidence:**
- 2026-05-29 id=374: total=495 s (8 min) for the WHOLE pipeline.
- 2026-05-31 04:00 auto-cron: total=1630 s (27 min), step 3 OK.
- 2026-05-31 09:00 manual: step 3 timed out at 15 min (master's per-step
  budget for step 3, set in `crypto_daily_master.py`).
- `COINGECKO_TIER` is unset → defaults to `demo` in
  `crypto_rating_daily.py:_TIER`. Demo tier is 30 calls/min → 0.5
  calls/sec. With ~200 tokens needing API calls, expected lower bound
  is ~400 s, comfortably under 15 min.

**Hypothesis:** Step 3 contention with Nbg. After step 2 fails with
SQLite-locked, the pipeline tries step 3 against Nbg over PgBouncer
under (a) PG saturation from the morning's earlier 4-hour OFFSET query
incident (not fully cleared until ~08:23), or (b) other pipeline
subprocess fighting for the same Nbg connections. The 15-min timeout
is a symptom, not the root cause.

**Why this needs follow-up but not now:** once R-PIPE-2 is fixed, the
pipeline will complete and we can measure step 3's actual time without
the cascade. If step 3 is consistently >10 min, the timeout needs
raising (currently `timeout_min=15`); if it's only slow during PG
contention, then it's a non-issue.

## C. Smedjan canary cross-reference

The 2026-05-31 morning incident response built `com.zarq.smedjan-canary`
(`scripts/smedjan_smoke_canary.py`, commit `40c5802`) to alert when the
Smedjan daily-merge smoke score falls below floor.

**This canary did NOT alert today.** Reason: it only watches the
Smedjan smoke log, which tests boot-path health (can the API boot from
cold cache and pass 23 sacred endpoints?). It does **not** watch the
crypto pipeline output.

`zarq.crypto_pipeline_runs` is a structurally identical signal — last
OK row indicates pipeline freshness. The same "silent automation
without read-back" pattern that caused the morning incident applies to
the crypto pipeline: no entry today, no entry yesterday, no alert.

**Follow-up:** tracking issue at
`docs/tracking/pipeline-success-canary.md` — same pattern as Smedjan
canary, ~1 hour implementation, watches `MAX(run_date) WHERE
status='OK'` from `crypto_pipeline_runs`. NOT implemented yet.

## D. Priority for next session

| Item | Why prio | Effort | Blocks |
|---|---|---|---|
| **R-PIPE-2** SQLite lock | Production-blocking; fresh data depends on it | 30 min (WAL mode + busy_timeout) to 2 h (Postgres-only redesign) | data freshness for ZARQ/Nerq frontend; eventually R1 since it touches data the frontend serves |
| **R-PIPE-1** subprocess env | Robustness; affects only manual reruns (which we may need during incident recovery) | 5 min one-line edit | manual recovery flows; not production |
| **R-PIPE-3** step-3 slowness | Latent, may resolve after R-PIPE-2 fix | observe-first; defer to after R-PIPE-2 measurement | nothing immediate |
| **Pipeline canary** | Observability gap (same class as 2026-05-31 morning) | 1 h | nothing — purely additive observability |

R1 (Cloudflare tunnel CNAMEs) was blocked behind a green baseline.
Baseline is not green — pipeline is failing. R1 should remain blocked
until **at least R-PIPE-2** is resolved and a fresh `pipeline_runs OK`
row appears.

## E. Data-freshness status

```
zarq.nerq_risk_signals       MAX(created_at)    2026-05-29 22:40:24 CEST   (~36 h stale)
zarq.crypto_pipeline_runs    MAX(completed_at)  2026-05-29 21:14:55 CEST   (~38 h stale)
zarq.dual_write_failures     MAX(occurred_at)   2026-05-31 06:35:41 CEST   (live — failures still happening)
```

`dual_write_failures` rolling fresh = the failure-counter table is doing
its job (loud), but nothing reads it for alerting (silent in practice).

The ZARQ frontend (zarq.ai) serves data from these tables. **Trust
scores, risk signals, and Distance-to-Default scores are 36 h stale.**
The site does not surface a staleness banner. Users see the values as
current.

## F. Nbg impact of this morning

The manual pipeline rerun amplified the morning incident's recovery
state. Sequence:

```
08:36   incident resolution baseline:   load=1.87, swap=8.0Gi, 0 open alerts
08:52   pipeline rerun start
09:08   pgbouncer agentindex_read crash (1)
09:09   pgbouncer agentindex_write crash (1)
09:10   pipeline exit (failed)
09:11   pgbouncer agentindex_write crash (2 more) + Nbg infra alert: 
        TCP_DOWN, "TimeoutError: timed out (after 4.01s)"
09:11   Nbg load peak: 41.49 (1-min)
09:13   Nbg load: 41.49 / 32.99 / 19.65 (1/5/15 min averages)
09:23   Nbg load: 2.40, swap unchanged, TCP_DOWN alert AUTO-RESOLVED
        by next infra_healthcheck cron
```

Verdict: Nbg fully recovered without intervention. **No long-running
queries are left.** Swap did not grow (308 Ki delta = noise). The
saturation was a brief spike caused by the pipeline subprocesses
hammering Nbg over a saturated SQLite-locked path and then exiting.

Memory is still pressured (14 Gi used, 8 Gi swap, 344 MiB free) but
that's the steady state on Nbg since 2026-05-26's Patroni OOM. ADR-003a
tracks this.

## G. What I did NOT do (per Anders' constraints)

- Did **not** apply any fix for R-PIPE-1/2/3.
- Did **not** re-run the pipeline.
- Did **not** change cron schedule. Tomorrow's 04:00 auto-cron will
  fail the same way; that's consistent failure data for diagnostics,
  worth keeping.
- Did **not** restart MCP server or API. MCP holds evidence for R-PIPE-2.

## Open follow-ups (added to tracking)

- `docs/tracking/pipeline-success-canary.md` — observability gap

## Source artifacts

- `/Users/anstudio/agentindex/logs/crypto_daily_stdout.log` —
  auto-cron 04:00 log (3.97 MB; trim with `tail -200` for the failure
  trace)
- `/tmp/pipeline-rerun-20260531.log` — manual rerun log this morning
- `/Users/anstudio/Library/LaunchAgents/com.nerq.crypto-daily.plist` —
  LaunchAgent config (mtime 2026-04-15)
- `~/agentindex/agentindex/crypto/crypto_daily_master.py:70` —
  `subprocess.run(...)` call without `env=`
- `~/agentindex/agentindex/crypto/dual_write.py:245,281` — SQLite
  failure sites
