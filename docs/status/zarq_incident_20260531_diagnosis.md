# ZARQ Incident 2026-05-31 — Diagnosis (no fix yet)

> Read-only investigation per Anders' "we've burned 3 sessions today on
> things that get undone by automation we don't understand" framing.
> No git/DB/LaunchAgent changes beyond stopping the restart-loop.

## STEG 1 — restart-loop stopped

`launchctl bootout` removed the LaunchAgent registration; an orphaned
uvicorn parent stayed alive holding `:8000` and was killed with `SIGTERM`.
End state: nothing on `:8000`, no uvicorn processes, `com.nerq.api`
unregistered. PgBouncer pressure relieved.

## STEG 2 — daily-merge "rollback" is not an emergency

`daily-merge-rollback-20260531` is one of **eleven** daily rollback tags
from `2026-04-28` onwards. Pattern: every 24 h Smedjan's automation
tags HEAD, attempts a cherry-pick batch, runs a smoke test, and rolls
back to the tag when the smoke fails. **The smoke has been failing
every day for at least the last 5 days.**

```
Pre-run rollback tag: daily-merge-rollback-20260527 → base=0/8 loc=4/5 sb=8/10  ❌
                                  20260528 → base=0/8 loc=3/5 sb=10/10  ❌
                                  20260529 → base=1/8 loc=5/5 sb=9/10  ❌
                                  20260530 → base=0/8 loc=3/5 sb=6/10  ❌
                                  20260531 → base=0/8 loc=0/5 sb=0/10  ❌  ← worst
```

Today's smoke is uniquely catastrophic: **0/23 checks pass** (vs the
prior days that at least had partial passes).

3 local commits ahead of `origin/main`:

```
1fe7428  smedjan FB-F2-20260531-003 (HEAD, tag rollback)
e1d5156  smedjan FB-F2-20260531-009
6471881  smedjan FB-F2-20260531-010
```

All three add files **only** under `smedjan/audits/FB-F2-20260531-*.{csv,py}`
— read-only audit artifacts (200 oldest top-5-registry rows). **No code,
no migrations, no deletions.** Our morning work is intact in git.

## STEG 3 — daily-merge pipeline reverse-engineered

Location: `/Users/anstudio/agentindex-factory/smedjan/daily_merge/cli.py`
(separate worktree `agentindex-factory`, branch `smedjan-factory-v0`).
LaunchAgent: `com.nerq.smedjan.daily-merge.plist`, fires `Hour=3 Minute=0`,
runs `python -m smedjan.daily_merge.cli run`, logs to
`/Users/anstudio/smedjan/worker-logs/daily-merge.log`.

Sequence:

```
1. cherry_pick.working_tree_clean()      # abort if dirty
2. rollback.tag_pre_run()                # tag HEAD as daily-merge-rollback-<date>
3. classifier.fetch_commits()            # collect A/B-class commits from factory
4. cherry_pick.cherry_pick_sequence(...) # apply them on the main worktree
5. file_copy.sync_files(...)             # mirror smedjan/ files
6. smoke_test.restart_api_kickstart()    # ← THIS kicks com.nerq.api
7. smoke_test.wait_for_api_ready(60)
8. smoke_test.run_smoke_test(seed=42)
9. canary.run_canary(min)                # if smoke passed
10. rollback.rollback_to_tag(tag)        # if smoke OR canary failed
```

**Step 6 is the user-visible interaction with our manual ZARQ fixes.**
Daily-merge's kickstart is the same `launchctl kickstart` we ran during
phase 4. After today's 03:00 kickstart the smoke saw 0/23 → rollback
fires → tag stays at HEAD → API continues to live in whatever state it
booted into.

The cherry-pick today: `picked: 1, skipped: 7, halted: 682b5d6`. The
halt-commit `682b5d6` matches the memory note about Smedjan's unbehandlad
halt-commit (per `project_overvintring_2026-05-05.md`). So cherry-pick
runs into the same wall it's been hitting since 2026-04-28; that's not
new.

## STEG 4 — DB consistency check

| Schema check | Mac Studio local (127.0.0.1) | Nbg (100.119.193.70) |
|---|---|---|
| `zarq.infrastructure_alerts` | **MISSING** | **present** |
| `zarq.dual_write_failures` | **MISSING** | **present** |
| `zarq.endpoint_usage_audit` | **MISSING** | **present** |
| `pg_is_in_recovery()` | `t` (standby) | `f` (primary) |
| Replay LSN | `38E/FC0000A0` | (current) `3B6/9E000000` |

**The Mac Studio local PG is a STANDBY that has been disconnected from
streaming replication since at least 2026-05-30 morning.** Replay LSN
gap is huge (`38E/FC…` → `3B6/9E…` ≈ 200+ GB of unstreamed WAL). Tables
we created on Nbg yesterday have never reached Mac Studio because
streaming was already broken.

This is **not new damage** — it's the same standby breakage documented
in `docs/adr/ADR-003a-current-db-topology.md`. The user's premise
("infrastructure_alerts finns INTE i Mac Studio lokal pg nu") is
technically correct but expected for a table that's <24 h old when
replication has been dead for weeks.

Migration files in git — all intact:

```
migrations/zarq/20260530-01-identity-defaults-and-failure-tables.sql
migrations/zarq/20260530-02-endpoint-usage-audit.sql
migrations/public/20260530-01-user-reviews-table.sql
migrations/public/20260530-02-software-registry-lower-name-pattern-index.sql
migrations/{public,zarq}/README.md
```

No `git log` entries modifying `migrations/` after our morning commits.
No DROP TABLE statement anywhere in the Smedjan codebase (`grep -rn
"DROP TABLE" agentindex/ smedjan/` returns only test/dev fixtures).

`user_reviews` exists in BOTH Mac local and Nbg (probably from a much
older `_ensure_reviews_table` boot-time run when replication still
worked, or from a manual sync — irrelevant for the current crash).

## STEG 5 — Diagnosis

### What happened

```
2026-05-30 18:00  R-SW STEP 1+2+3 deployed. 30-min soak: 0 restarts,
                  0 PgBouncer crashes, all endpoints 200. API healthy.

2026-05-30 ~20:00 → 2026-05-31 03:00  Anders ends the session. The API
                  runs untouched. No code/DB changes from us.

2026-05-31 03:00  Smedjan daily-merge cron fires
                  - Tags HEAD as daily-merge-rollback-20260531
                  - Cherry-picks 1 commit from factory (read-only audit)
                  - launchctl kickstart com.nerq.api  ← worker restart
                  - Smoke test: 0/23 — TOTAL FAILURE
                  - rollback.rollback_to_tag(...)

2026-05-31 03:00+ Workers can't boot cleanly. KeepAlive restarts them.
                  Each restart hits boot-time PG calls. PgBouncer queue
                  backs up. PG drops connections mid-flight.
                  → anyio.WouldBlock during request body streaming
                  → SQLAlchemy fairy._reset tries to roll back
                  → psycopg2.OperationalError: server closed connection
                  → Worker dies, asyncio cancels 80+ tasks mid-shutdown
                  → Loop, for ~4.5 hours until Anders checks at 07:30.
```

### Root cause (hypothesis with supporting evidence)

**Same class of failure as R-SW yesterday, narrower in scope.** Our STEP
1+2+3 fixes resolved the *amplifiers* (boot DDL, missing index) and the
*meta-bug* (TCP-only probes). They did NOT eliminate:

1. **Worker-boot's other PG dependencies** beyond `user_reviews`. SQLAlchemy
   engine creation, ZarqRouter middleware init, possibly other modules,
   touch PG at import-time. When PG has any 30-second-class slowness,
   workers fail to boot.
2. **PgBouncer `query_wait_timeout = 30s`** still in place. Bursts of
   slow queries from any source still saturate. Today's daily-merge cron
   at 03:00 was the burst trigger.

Specifically what made 03:00 fragile vs the rest of the night: I can't
pin from this read-only investigation alone. Hypotheses worth checking
in a fix-phase:

- **`com.nerq.crypto-daily` runs 04:00** but daily-merge is 03:00 — so
  it's NOT crypto-daily.
- **`com.nerq.zarq-cache`** (exit=2 from yesterday's inventory) restarts
  every 240s. Each restart may pile work onto Nbg.
- **`com.nerq.dashboard-data`** (exit=1) — same.
- **Other 02:00–03:00 crons** — `daily-merge`, `daily-backup` (cron at
  01:30 per CLAUDE.md), maybe more.

The 0/23 smoke result is significantly worse than recent days, which
points to *several concurrent failures at boot time*, not one.

### What is NOT the cause

- **Not the daily-merge rollback itself** — it's a benign daily cycle.
- **Not the 3 local audit-CSV commits** — pure data files, no API
  surface impact.
- **Not lost tables on Mac Studio local** — that's pre-existing standby
  breakage from ADR-003a, not a new regression.
- **Not Nbg being unreachable** — direct `psql host=100.119.193.70`
  responds in <100 ms right now.
- **Not PgBouncer being down** — both pools respond in <100 ms right now.
- **Not a code regression vs yesterday** — `git diff origin/main..HEAD`
  is 4 audit files only; working tree is clean.

### Smedjan ↔ manual-fixes interaction model

Per the user's framing: yes, there's a real interaction. Smedjan
**doesn't fight our fixes** — it doesn't delete tables, doesn't revert
commits we cared about, doesn't modify migrations. What it **does** do
that creates the appearance of conflict:

1. **Restarts the API every 24 h** (the kickstart in `smoke_test.restart_api_kickstart`).
2. Tags HEAD daily. If a future automation reads the tag as "this is
   what production should be," it could create confusion.
3. Cherry-picks a small set of A/B-class commits, then rolls back. The
   working-tree state after rollback IS the pre-pick state, but the
   3-commit history visible from `git log` is just whatever Smedjan
   committed during the day via other automation (worker.py?
   audit_scheduler.py?) — not daily-merge's doing.

The cycle is essentially: every night daily-merge takes a snapshot of
"what the system was doing" and tests whether the API survives a clean
restart from that snapshot. **For 5+ days it has failed.** Smedjan has
been silently telling us "the API can't reboot cleanly" daily, and we
haven't been reading the daily-merge log.

That's the real lesson: this isn't a fight between our manual fixes and
Smedjan. It's that Smedjan is the *only* thing exercising "can the API
reboot from scratch?" and the answer has been **no** for at least 5 days,
including immediately after we deployed yesterday's "fix."

## What I propose for the next session (NOT executed in this one)

1. **Mount the surface inventory of boot-path PG dependencies.** Track
   every module-load-time `session.execute(...)` against agentindex DB
   beyond `user_reviews`. Move them all to migrations the same way we
   moved the user_reviews DDL.
2. **Check why 03:00 specifically.** Look at logs around the daily-merge
   kickstart for other 02:00–03:00 cron activity contention.
3. **Read the smoke-test code.** If the smoke uses the same boot path
   the API does, fixing the boot path fixes the smoke. If it doesn't,
   the 0/23 may be a smoke-config issue, not an app failure — we should
   know which.
4. **Don't bring the API back yet.** It's bootout'd; no traffic is being
   served, but no harm is being done either. Once we have the boot path
   audited, the next restart can be controlled.

Until then: `com.nerq.api` is stopped. Cloudflare-edge returns 502 for
`zarq.ai` and `nerq.ai`. `mcp.zarq.ai` is unaffected (separate process,
`com.zarq.mcp-sse` on :8001).

## Files referenced

- `/Users/anstudio/agentindex-factory/smedjan/daily_merge/cli.py`
- `/Users/anstudio/smedjan/worker-logs/daily-merge.log`
- `/Users/anstudio/Library/LaunchAgents/com.nerq.smedjan.daily-merge.plist`
- `/Users/anstudio/agentindex/logs/api_error.log`
- `docs/adr/ADR-003a-current-db-topology.md`
- `docs/status/r7_state_check_20260530_1735.md`
