# Pipeline fix attempt — 2026-05-31

**Status:** NO-GO for R1. Partial recovery only.
**Commits:** `717f944` (R-PIPE-2), `13f30cd` (R-PIPE-1).

## A. Pre-fix state (recap from pipeline_diagnosis_20260531.md)

- Last successful `zarq.crypto_pipeline_runs` row: id=374, 2026-05-29.
- Pipeline failing daily for 2+ runs.
- Three root causes identified: R-PIPE-1 (subprocess env),
  R-PIPE-2 (SQLite lock), R-PIPE-3 (step 3 timeout).

## B. What was changed

### R-PIPE-1 (commit `13f30cd`, `crypto_daily_master.py`)

- Added `sys.path.insert(0, REPO_ROOT)` at module load so the master is
  self-sufficient for `from agentindex.crypto.dual_write import ...`
  in `save_run_status`. Previously this only worked when LaunchAgent
  had set PYTHONPATH.
- Added `env={**os.environ, "PYTHONPATH": REPO_ROOT}` to the
  `subprocess.run(...)` call in `run_step()` so children inherit the
  correct PYTHONPATH regardless of caller env.
- Verified: a manual run from `cd ~/agentindex && env -u PYTHONPATH
  venv/bin/python ...` no longer produces `ModuleNotFoundError: No
  module named 'agentindex'`.

### R-PIPE-2 (commit `717f944`)

WAL was already enabled on `crypto_trust.db`. The actual issue was
`busy_timeout=0` (SQLite default — fail immediately on lock). Added
`PRAGMA busy_timeout=30000` in five places:

- `dual_write.py`: `_ensure_pragmas(sqlite_conn)` helper, cached on the
  connection, called at the start of dual_execute / dual_executemany /
  dual_executemany_named / dual_delete.
- `crypto_price_pipeline.py:connect_crypto_db` and `connect_data_db`.
- `crypto_ndd_daily_v3.py:connect_data_db` and `connect_crypto_db`.
- `nerq_risk_signals.py:main`.
- `crypto_daily_master.py:save_run_status`.

Documentation migration `migrations/zarq/20260531-01-crypto-trust-wal-mode.sql`
recording the intent and the per-connection caveat.

## C. Pipeline rerun result (2026-05-31 09:38 → 10:03, 25.5 min)

| Step | Pre-fix (04:00 cron) | Post-fix (09:38 manual) | Change |
|---|---|---|---|
| 1_crawl_tokens | ✅ | ✅ (153s) | — |
| 2_fetch_prices | ❌ sqlite locked | ❌ sqlite locked at 31s | no fix; busy_timeout exhausted |
| 3_credit_rating | ✅ | ❌ timed out 15 min | **regression-looking** |
| 4_ndd_distress | ❌ sqlite locked | ✅ (2s) | **fixed** |
| 4b_defillama_fallback | ❌ timed out | ✅ (295s) | **fixed** |
| 5_risk_signals | ❌ sqlite locked | ❌ sqlite locked at 31s | no fix |
| Master writeback | ❌ "database is locked" | ❌ "No module named 'agentindex'" → won't write OK row | (manual-run-only issue) |

Net: 2 steps newly passing (4, 4b). 2 steps still failing on lock
(2, 5). 1 step regressed-looking (3 — but see R-PIPE-3 note below).

### Lock-holder identified (not MCP)

`lsof` during the rerun showed `crypto_trust.db` held WRITE-mode by:

- `zarq_mcp_server.py` (pid 1017) — read-only, fd `3u` (open for r/w
  but the server has no `INSERT/UPDATE/DELETE`)
- `agentindex.crawlers.npm_downloads_crawler` (pid 97545, started
  04:00 today, 6+ hours running) — fd `3u`, `8u` (WAL), `9u` (SHM)
  → actively writing during long batches

The 31s failure pattern (busy_timeout 30s + ~1s overhead) confirms
npm-crawler holds the exclusive writer lock for >30 s during its batch
transactions. WAL mode lets readers continue freely but only one
writer at a time. The pipeline's writers and npm-crawler's writers
race on the same `crypto_trust.db`.

### R-PIPE-3 status

Step 3 (credit_rating) timed out at exactly 15 min today.
04:00 auto-cron earlier today: step 3 ran to completion (in 27-min
total). 2026-05-29 baseline: full pipeline in 495 s, step 3
implicitly fast.

So step 3 is sometimes-fast / sometimes-slow. Possible drivers:
- Contention with Nbg under PgBouncer (we just had a
  Smedjan-OFFSET-query saturation incident this morning)
- CoinGecko Demo-tier rate-limit hitting more tokens than yesterday
- Long-running rating computation per token, summing to >15 min
  occasionally

Cannot conclude R-PIPE-3 is a real timeout-budget issue from one data
point. Defer.

## D. GO/NO-GO

Anders' GO criteria were:
1. Ny `pipeline_runs` rad med status=OK alla 5 steg → **NO** (latest
   still id=374)
2. Färska data i alla `crypto_*` tabeller (CURRENT_DATE matches) → **NO**
   (`crypto_price_history` now 56h stale; `nerq_risk_signals` 36h)
3. Freshness-tests PASS → **NO** (4 failed, 5 passed)
4. MCP unaffected (pid 1017 unchanged) → ✅
5. Nbg-load stabil under hela körningen (<5) → mostly ✅ (load 1.9–3.4
   median; one brief spike to 11.75 in min 21 then back down)

**Verdict: NO-GO. R1 stays blocked.**

## E. Why busy_timeout=30s wasn't enough

Two writers cannot coexist in SQLite, even with WAL. When npm-crawler
opens a write transaction, the pipeline's writes wait. After 30 s,
the pipeline gives up with `database is locked`. Possible permanent
fixes, in increasing scope:

1. **Increase busy_timeout to e.g. 120 s.** Trivial change but the
   pipeline will block instead of fail, slowing its overall run by up
   to 2 min per collision.
2. **Shorten npm-crawler transactions** — wrap each batch in
   short `BEGIN ... COMMIT` instead of one long one. Hour of work to
   review the crawler code.
3. **Sequence pipeline and crawler** — make crawler check a lock file
   or paused state during the 04:00 pipeline run. Less elegant.
4. **Move conflicting tables to Postgres-only** — stop dual-writing
   them to SQLite at all. Multi-hour refactor.

These are all candidates. None applied in this session. Recommendation
for next session: option 1 (raise to 120 s, observe) + option 2 if
that's insufficient.

## F. Status of related work

| Item | Status |
|---|---|
| R-PIPE-1 (subprocess env) | ✅ fixed (commit `13f30cd`) |
| R-PIPE-2 (SQLite lock) | 🟡 partial — 30 s busy_timeout fixes short races (steps 4, 4b), not >30 s holds (steps 2, 5) |
| R-PIPE-3 (step 3 timeout) | 🔴 confirmed real after R-PIPE-2 partial fix |
| Pipeline-success canary | 🔴 still NOT implemented (`docs/tracking/pipeline-success-canary.md`) |
| Data-freshness tests | 4 fail / 5 pass — still red |
| Latest `pipeline_runs OK` | id=374, 2026-05-29 (~62 h stale) |

## G. Recommendation for next session

In priority order:

1. **Bump `_BUSY_TIMEOUT_MS` in dual_write.py from 30000 to 120000.**
   Cheap test: does step 2 and step 5 now pass when npm-crawler is
   batched up? If yes, this is enough.
2. **Investigate npm-crawler transaction length.** Read
   `agentindex/crawlers/npm_downloads_crawler.py`; if it has a single
   long `BEGIN ... COMMIT` over many batches, split into per-batch
   transactions.
3. **Defer R-PIPE-3 until R-PIPE-2 is fully clean.** Then time
   step 3 in 3 consecutive successful runs and decide if the 15-min
   budget needs raising.
4. **R1 (Cloudflare tunnel CNAMEs)** stays blocked until a fresh
   `pipeline_runs OK` row appears.

## H. What was NOT done

- Did not increase busy_timeout beyond 30 s in this session — Anders'
  plan specified 30 s.
- Did not touch npm-crawler.
- Did not restart MCP server or API.
- Did not re-trigger the pipeline a second time (we have enough data
  from one rerun to characterise R-PIPE-2's residual gap).
- Did not implement the pipeline-success canary (separate workstream).
