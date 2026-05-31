# Session summary — 2026-05-31

**Window:** ~04:00 → ~11:00 CEST (incident + fix-cycle + arch-doc; ~7 h
agent time, longer including overnight cron).
**Operator:** Anders Nilsson.
**Assistant:** Claude Opus 4.7.

## A. Top-line

One P0 incident at 03:00, fully resolved by 08:36. Pipeline-fix cycle
delivered partial recovery (R-PIPE-1 fixed, R-PIPE-2 partial,
R-PIPE-3 confirmed real). Architecture call for SQLite-multi-writer
deferred to a future Anders-led session. R1 (Cloudflare CNAMEs)
remains blocked.

## B. Commits (8 non-Smedjan)

```
40c5802  docs+feat  03→08  morning incident diagnosis, boot-path inventory, Smedjan smoke canary
33663c5  perf       08:24  disable pool_pre_ping → 60s pool_recycle (R-SW2 amplifier fix)
13ba17c  docs       08:41  incident report — Smedjan OFFSET query + pool_pre_ping amplifier
71bf305  docs       09:30  pipeline diagnosis 20260531 — R-PIPE-1/2/3 + canary gap
717f944  fix        10:06  SQLite busy_timeout=30s on crypto_trust.db (R-PIPE-2 partial)
13f30cd  fix        10:06  explicit subprocess env + master self-import (R-PIPE-1)
e13f709  docs       10:07  pipeline fix attempt — partial recovery, NO-GO for R1
31e5854  docs       10:48  SQLite multi-writer problem — architecture alternatives
```

Plus 9 automatic Smedjan FB-F2 freshness-CSV commits (routine).

All 17 commits pushed to `origin/main` (12 fast-forwarded at 10:25,
last 1 at 10:48 — verified end-of-session).

## C. Incident recoveries (1 P0)

**03:00 → 08:36 CEST — ZARQ public-facing 502, 5h36m duration.**

Sequence:
- 04:00 com.nerq.smedjan.daily-merge kickstart-API + smoke = 0/23 →
  silent rollback (Smedjan canary blindness, separate workstream).
- 04:00 Smedjan factory worker opens 4 h-long `OFFSET 1865000` query
  on `agents` (1.8 M rows skipped per batch) → Nbg load 43.52, swap
  saturated.
- 03:00 → 07:30 API restart-loop on Mac Studio. Cause: per-request
  `pool_pre_ping=True` amplifying PG-saturation into worker-killing
  `anyio.WouldBlock` cascade.
- 08:15 Smedjan workers paused via `launchctl bootout`.
- 08:17 `pg_terminate_backend(3152538)` on Nbg.
- 08:24 `pool_pre_ping=False`, `pool_recycle=60s` committed (`33663c5`).
- 08:25 smoke 23/23. 5 min soak clean.
- 08:30 → 08:35 Smedjan workers a-d resumed one at a time.
- 08:36 resolved. Nbg load back to 1.87.

Full report: `docs/incidents/20260531/incident_report.md`.

## D. Permanent fixes landed

- **`33663c5`** — `pool_pre_ping=True → False`, `pool_recycle=300 → 60` on
  read + write engines. Removes per-request PgBouncer ping that
  amplified saturation into worker death.
- **`40c5802`** — `scripts/smedjan_smoke_canary.py` + LaunchAgent
  `com.zarq.smedjan-canary` at 03:30 daily. Closes the silent-rollback
  observability gap that hid this morning's incident for hours.
- **`717f944`** — `PRAGMA busy_timeout=30000` on 5 sqlite-open sites
  (`dual_write.py:_ensure_pragmas` helper + 4 direct
  `sqlite3.connect` sites). Fixes short writer-races (steps 4 + 4b
  newly pass).
- **`13f30cd`** — `subprocess.run(env={**os.environ, "PYTHONPATH":
  REPO_ROOT})` + `sys.path.insert(0, REPO_ROOT)` at master top. Makes
  the pipeline runnable from any shell, not just LaunchAgent.

## E. Diagnosis-only items (no fix yet, documented for future)

- **R-PIPE-2 residual** — npm-crawler holds writer lock > 30 s,
  busy_timeout doesn't help. Steps 2 + 5 still fail. Documented in
  `docs/architecture/sqlite-multi-writer-problem.md`. Blocks
  pipeline-OK.
- **R-PIPE-3** — step 3 (credit_rating) intermittent timeout. Today's
  04:00 cron: step 3 OK. 09:00 manual: timed out 15 min. Defer until
  R-PIPE-2 is clean and we can measure step 3 in isolation.
- **OOM correlation** — Patroni OOM 2026-05-26 may have been the
  *effect* of growing software_registry pressure, not the cause.
  Documented in `docs/status/oom-correlation-observation-20260530.md`.
  7-day watch criteria defined.

## F. Architecture questions surfaced

1. **SQLite multi-writer** — the question of the day. Four
   alternatives documented, decision deferred.
   `docs/architecture/sqlite-multi-writer-problem.md`.
2. **HA recovery** — Patroni dead on Hel + Nbg, etcd quorum
   unrestored, Mac Studio replica stale. `docs/adr/
   ADR-003a-current-db-topology.md` already documents this; not
   driven today.
3. **Cloudflare ingress** — R1a/R1b (api.zarq.ai / api.nerq.ai CNAMEs)
   still need CF API token. R1 also semantically blocked behind
   pipeline-OK per the discipline of "don't add public surfaces while
   existing surfaces serve stale data."

## G. Smedjan interaction

- Workers paused for ~25 min during incident response.
- All 4 (a/b/c/d) resumed cleanly post-fix.
- Daily-merge cycle (03:00 → 04:00) preserved.
- New canary (`com.zarq.smedjan-canary`) will fire at 03:30 tomorrow
  if smoke is below floor — self-test.

## H. Open follow-ups (prioritised for next sessions)

| Item | Prio | Blocks | Notes |
|---|---|---|---|
| SQLite-multi-writer architecture decision | **P0** | R1, pipeline OK, fresh ZARQ data | Anders call; see arch doc |
| Pipeline-success canary (`docs/tracking/pipeline-success-canary.md`) | P1 | observability for arch-decision rollout | ~1 h impl |
| R-PIPE-3 measurement (after R-PIPE-2 clean) | P2 | step 3 budget decision | Defer |
| 7-day Nbg OOM-watch checkpoint | P2 | demote Mac-Studio replica decision | Hit 2026-06-06 |
| Day-14 audit-review (`/crypto/*`, `/experiments/*`, `/action/*`) | P2 | deprecation-logger followup | Hit 2026-06-13 |
| HA recovery workstream (Patroni, etcd 3-node, CF LB) | P2 | DR posture | Larger workstream |
| R1 (Cloudflare CNAMEs) | blocked | — | Needs arch + CF token + 3-day-clean pipeline |

## I. Lessons captured today

- **`pool_pre_ping=True` is footgun-shaped under PG-saturation** —
  every checkout becomes a PG round-trip. Documented in incident report.
- **Silent automation without read-back grows P0s slowly** — Smedjan
  smoke had failed for ≥5 days; crypto pipeline for ≥2. The Smedjan
  canary closes one loop; the pipeline canary will close the other.
- **WAL is not enough for multi-writer SQLite** — busy_timeout helps
  short races, but the *real* fix to writer-vs-writer contention is
  architectural, not parameter-tuning.
- **Pause → terminate → fix → resume is the right runbook for
  saturation incidents** — verified twice today (morning incident +
  pipeline diagnostics). Worth codifying as a runbook in a future
  session.

## J. End-of-session state

API + endpoints serving normally. No open critical alerts. Git in
sync with origin. Smedjan workers running. Pipeline broken (known);
arch decision pending.

Verified in STEG 4 of this session.
