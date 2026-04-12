# Phase 0 Day 2 — Basebackup Running

Date: 2026-04-12 (Sunday afternoon)
Status: pg_basebackup streaming from Mac Studio to nerq-nbg-1, ~5h remaining
Related: docs/status/phase-0-day-2-paused.md

## Breakthrough

The pg_hba.conf blocker was not actually an authentication rule problem.
Root cause: psql CLI does not pass replication=database parameter correctly
in connection strings. When Postgres did not receive replication mode,
it tried to match pg_hba rules for a regular database connection to a
database literally named "replication" - which does not exist.

pg_basebackup uses libpq internal replication mode and does NOT have this
issue. Our rules were always correct, just our test tool (psql) was wrong.

## Current state

- pg_basebackup running on nerq-nbg-1 as bg process (PID 17824)
- Rate: ~7 MB/s (--max-rate=5M was conservative, actual network permits more)
- Started: 11:21 CEST
- Progress: 2.8 GB / 94 GB (~3%)
- ETA: ~15:00 CEST (3.6 hours remaining)
- Target: /var/lib/postgresql/16/main on nerq-nbg-1
- Flags: --wal-method=stream (continues replication after initial backup)
         --slot=nerq_nbg_replica
         --write-recovery-conf (auto-configures standby mode)
- Log: /var/log/pg_basebackup.log on nerq-nbg-1

## Configuration done (pg_hba.conf, Mac Studio)
host    replication     nbg_repl        100.119.193.70/32       scram-sha-256
host    replication     nbg_repl        100.79.171.54/32        scram-sha-256

Line 132 (Mac Mini original replicator rule) temporarily disabled with
#DISABLED prefix to stop log spam. To be restored when Mac Mini replica
is re-authed physically.

## Mac Mini replica status

Mac Mini replica is broken due to password rotation. Anders physically
updated .pgpass on Mac Mini but new password was not picked up (likely
copy-paste issue or walreceiver caching). Currently generating
no pg_hba.conf entry errors every 5s in log (harmless noise).

Fix deferred: Log into Mac Mini, regenerate .pgpass with exact 32-char
password from Mac Studio ~/.config/phase-0/replicator.password,
full postgres restart, verify on Mac Studio via pg_stat_replication.

## Credentials (on Mac Studio, 600 perms)

- ~/.config/phase-0/replicator.password (for existing replicator user)
- ~/.config/phase-0/nbg_repl.password (for new nbg_repl user, 32 chars)

## Production impact during basebackup

Moderate. ZARQ P95 ~5s intermittently (same as baseline when crawlers burst).
Nerq stable at ~35ms. Memory pressure 62 MB free remains the underlying
issue - Phase 0 migration is the fix for this, not a side effect.

Rate-limit at 5 MB/s keeps basebackup from aggravating memory pressure.

## Next steps (when basebackup completes around 15:00 CEST)

1. Verify completion: tail /var/log/pg_basebackup.log should show
   pg_basebackup: base backup completed
2. Verify standby.signal exists on Nbg: /var/lib/postgresql/16/main/standby.signal
3. Verify postgresql.auto.conf has primary_conninfo set
4. Start Postgres on Nbg: systemctl start postgresql@16-main
5. Verify replication on Mac Studio:
   SELECT client_addr, state, sync_state, replay_lsn FROM pg_stat_replication
6. Should show 100.119.193.70 with state=streaming, async
7. Verify lag is close to zero

## Parallel work while waiting

- ZARQ Tier A PostgreSQL DDL generation (separate commit/doc)
- Mac Studio memory profiling to understand baseline ZARQ latency

## Lesson learned

When debug doesn't progress in 30 min, the bug is often in our tool
or test methodology, not the system under test. Today's lost 60 min was
testing replication via psql CLI (wrong tool for replication mode) when
we should have tested with pg_basebackup directly (correct tool, works).
