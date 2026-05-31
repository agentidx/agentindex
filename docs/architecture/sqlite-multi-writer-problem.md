# Architecture decision pending: SQLite multi-writer contention on crypto_trust.db

**Status:** Open. Decision deferred to an Anders-led session (architecture
call, not an agent call).
**Surfaced by:** 2026-05-31 crypto-pipeline failure (R-PIPE-2). See
`docs/status/pipeline_diagnosis_20260531.md` and
`docs/status/pipeline_fix_20260531.md`.
**Blocks:** R1 (Cloudflare tunnel CNAMEs) and any future feature that
depends on fresh `zarq.crypto_*` data.

## A. Problem framing

The ZARQ architecture has been described internally as "100 % SQLite,
Postgres scrapped" (project memory + ADR discussions). Reality:
`crypto_trust.db` is written to by **multiple concurrent processes**:

- `crypto_daily_master.py` and its subprocesses (steps 2, 4, 5,
  writeback) — pipeline, 04:00 CET daily, ~10-30 min duration.
- `agentindex.crawlers.npm_downloads_crawler` — runs for 6 + hours
  per invocation; holds the writer lock during long batches.
- Other potential writers (not exhaustively audited):
  `agentindex/zarq_dashboard.py`, `data_exports.py`, `crash_shield.py`,
  `seo_pages.py`, and ~15 other modules `grep`-ref crypto_trust.db.
  Whether they take write transactions long enough to collide is
  unknown without an audit.
- `zarq_mcp_server.py` (pid 1017, MCP read interface) holds the file
  open for read but does not write per code inspection — does add
  reader contention for SHM/WAL pages.

SQLite + WAL: many concurrent **readers** + at most **one writer**. The
moment two processes both want a write transaction, the loser waits
`busy_timeout` ms and then raises `sqlite3.OperationalError: database
is locked`. WAL does not help writer-vs-writer.

Result on 2026-05-31: pipeline failed on steps 2 + 5 (sqlite locked)
even after WAL was already on and `busy_timeout` was set to 30 s per
connection. The failure pattern: exactly 31 s wait → fail. The
npm-crawler held the writer lock for the full 30 s window.

This is the second consecutive day the pipeline has been broken by
this contention. Data in `zarq.nerq_risk_signals` is now 36 + h stale;
`crypto_price_history` is 56 + h stale.

## B. Current state (post commits 717f944 + 13f30cd)

| Setting | Value |
|---|---|
| `crypto_trust.db` journal_mode | WAL ✓ |
| `crypto_trust.db` synchronous | NORMAL (1) ✓ |
| Per-connection `busy_timeout` | 30 000 ms (set in 5 code sites) |
| Identified write competitor | `npm-downloads-crawler` (transactions > 30 s) |
| WAL file size at peak | 37.5 MB |
| Latest `pipeline_runs` row with status=OK | id 374, 2026-05-29 |

## C. Alternatives (analysis, no decision)

### Alt 1 — Raise `busy_timeout` to 120 s (or 300 s)

**Pros**
- One-line change in `dual_write.py:_BUSY_TIMEOUT_MS` plus matching
  bumps in `crypto_price_pipeline.py`, etc.
- Reversible; trivial to roll back.

**Cons**
- Lap over the symptom. Breaks again the first time a transaction
  exceeds the new ceiling, or when a third concurrent writer appears.
- Pipeline already has a 15 min budget for step 3 (credit_rating).
  Adding multi-minute waits for SQLite reduces actual work-time
  available.
- Encourages "make the timeout bigger" as the default fix for future
  contention. Wrong incentive.

### Alt 2 — Refactor `npm-crawler` (and any other long-writer) to per-batch BEGIN/COMMIT

**Pros**
- Keeps the SQLite-first architecture intact.
- Permanent fix for the *known* offending pattern.

**Cons**
- Requires reading `agentindex/crawlers/npm_downloads_crawler.py` and
  potentially several other modules; effort is medium (2-4 h) and
  carries regression risk if batching semantics matter elsewhere
  (e.g. transactional consistency of a multi-step crawl insert).
- Discipline-dependent. Every new pipeline / crawler / utility that
  writes to `crypto_trust.db` must follow the same rule. No
  enforcement mechanism — drift over time is likely.
- Does not solve the case of *legitimate* long transactions (large
  one-shot UPSERT batches in the pipeline itself).

### Alt 3 — Migrate `crypto_trust.db` writes to Postgres `zarq` schema

**Pros**
- Postgres uses MVCC: concurrent writers don't lock each other on row-
  level updates. Solves the root cause.
- Postgres infrastructure already runs on Nbg (primary, after
  2026-05-30 repoint) and Mac Studio (replica, stale per ADR-003a).
- Consistent with the existing public/zarq schema pattern already used
  by `agents`, `entity_lookup`, etc.
- Dual-write code already exists (`dual_write.py`) — it mirrors
  SQLite → Postgres today. Inverting the master (Postgres becomes
  primary, SQLite becomes the mirror or is retired) is a finite, well-
  bounded change.

**Cons**
- Medium-to-large migration. Estimated 2-4 h of focused Code-time per
  conflicting table, plus consumer-side audit (`zarq_mcp_server`,
  `crypto_api`, dashboard pages, ~15 modules that read from
  `crypto_trust.db`).
- Conflicts with the "ZARQ is 100 % SQLite" narrative. Needs an ADR
  documenting the reality and the decision.
- MCP server (`zarq_mcp_server.py`, port 8001) must be re-pointed to
  Postgres. Connection pool + DSN config. Not free.
- Increases coupling between ZARQ and the Nbg/Hel/Mac-Studio Postgres
  fleet, which itself has unresolved HA issues (ADR-003a).

### Alt 4 — Hybrid: Postgres as primary writer, SQLite as MCP-read replica

**Pros**
- Preserves SQLite's read-side simplicity / latency for MCP.
- Decouples write contention from read latency.

**Cons**
- Introduces a replication-lag surface — SQLite copy can drift behind
  Postgres if the sync job stalls.
- More moving parts: writes go to PG, a job pulls deltas to SQLite,
  the MCP reads from SQLite. Three things to monitor instead of one.
- Not obvious this gives anything Alt 3 doesn't, unless MCP read
  latency is empirically shown to require SQLite.

## D. Blocking questions before deciding

These are facts we don't have today. Each is a 10-30 min spike:

1. **Full inventory of writers to `crypto_trust.db`.** Today's evidence
   identifies `npm_downloads_crawler` as the long-writer, but ~15
   modules `grep` for the file. How many actually open a write
   transaction, and for how long?
2. **What is `npm-crawler` doing for 6 + hours?** Why are transactions
   > 30 s? Is it a single long batch or many short batches under one
   lock? Determines whether Alt 2 is hours or days of work.
3. **Is MCP server's SQLite read-path a hard requirement?** Profile
   MCP query latency. If it's > 10 ms on common paths, Postgres-over-
   local-socket would match. If it's < 1 ms, switching costs measurable
   latency.
4. **Is R-PIPE-3 (step 3 timeout) actually SQLite-driven or rate-limit-
   driven?** If step 3 freezes because of `COINGECKO_TIER=demo`'s
   30 req/min cap on 200 + tokens, it's independent of Alt 1/2/3/4.
   Profile: count CoinGecko calls vs SQLite writes during a step 3 run.

## E. Preliminary recommendation (for the future architecture call)

Ranked, not decided:

  **Alt 3 (Postgres migration) > Alt 2 (npm-crawler refactor) > Alt 4 > Alt 1**

Rationale:

- Alt 3 fixes the root cause. Postgres infrastructure exists. Inverting
  the dual_write direction is bounded scope.
- Alt 2 is acceptable as a stop-gap while Alt 3 is planned, but is
  not a long-term answer.
- Alt 1 is a footgun; recommend against unless explicitly used as a
  buffer for one pipeline run while Alt 2/3 are in flight.

However, this is an architecture decision, not an agent decision.
"ZARQ is 100 % SQLite" is a stance Anders has held; an inversion is
his call. This document exists to make the trade-off explicit, not
to drive it.

## F. R1 status

R1 (Cloudflare tunnel CNAMEs for `api.zarq.ai` / `api.nerq.ai`) is
blocked until:

1. The architecture decision is taken (Alt 1/2/3/4 or another).
2. The decision is implemented to the point that the pipeline runs OK
   for 3 consecutive daily cycles (gives confidence the fix holds).
3. The Cloudflare API token is provisioned (Anders side).

R1 itself is not technically dependent on the pipeline being green —
it is a tunnel-routing change. But operating discipline says don't add
new public surfaces while existing surfaces are serving stale data.

## G. References

- `docs/status/pipeline_diagnosis_20260531.md` — initial R-PIPE-1/2/3
  diagnosis
- `docs/status/pipeline_fix_20260531.md` — partial-fix attempt result
- `agentindex/crypto/dual_write.py` — current dual-write helper
  (SQLite → Postgres mirror)
- `agentindex/crawlers/npm_downloads_crawler.py` — known long-writer
- `docs/adr/ADR-003a-current-db-topology.md` — Postgres fleet state
  (Nbg primary, Hel cold, Mac Studio stale)
