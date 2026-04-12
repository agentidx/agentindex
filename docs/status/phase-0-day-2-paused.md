# Phase 0 Day 2 — Paused at Postgres Replication Step

Date: 2026-04-12 (Sunday afternoon)
Status: Partial progress, paused to return with fresh eyes
Related: docs/status/phase-0-day-1-complete.md, docs/strategy/phase-0-cloud-migration-plan.md

## What was accomplished (Day 2 partial)

### Infrastructure provisioned

Three new Hetzner servers up and running, fully hardened:

| Name | Type | Location | Public IPv4 | Tailscale IPv4 | Status |
|---|---|---|---|---|---|
| nerq-nbg-1 | CPX42 | Nbg | 178.104.160.85 | 100.119.193.70 | Ready |
| nerq-hel-1 | CPX42 | Hel | 204.168.251.143 | 100.79.171.54 | Ready |
| nerq-worker-1 | CPX22 | Nbg | 46.224.147.240 | 100.101.184.47 | Ready |

Per node: Ubuntu 24.04, nerq user with sudo, UFW firewall, Docker 29.4.0, PostgreSQL 16.13 (installed not configured), Tailscale 1.96.4, fail2ban, unattended-upgrades.

SSH aliases on Mac Studio: ssh nerq-nbg, ssh nerq-hel, ssh nerq-worker (plus root variants).

### Cost
- 2x CPX42 Nbg+Hel: 64 EUR/month
- 1x CPX22 worker: 8 EUR/month
- Total running: ~72 EUR/month

These are billable but idle waiting for Phase 0 continuation.

## What blocked us

### PostgreSQL replication setup (BLOCKER)

Attempted to configure Postgres streaming replication from Mac Studio primary to nerq-nbg-1 replica.

Steps completed:
1. Verified existing replicator user has replication privilege
2. Backed up pg_hba.conf
3. Added host replication rules for 100.119.193.70 and 100.79.171.54, using scram-sha-256 auth with identical format to working Mac Mini rule
4. Set wal_keep_size = 1GB via ALTER SYSTEM + reload
5. Created nerq_nbg_replica replication slot
6. Rotated replicator password (old one visible in chat momentarily, deemed compromised)
7. Transferred new password to Nbg via SSH into /var/lib/postgresql/.pgpass

The blocker: Every connection attempt from Nbg to Mac Studio fails with:
  FATAL: no pg_hba.conf entry for host "100.119.193.70", user "replicator",
         database "replication", no encryption

Everything appears correct:
- pg_hba_file_rules view shows the new rules loaded, no errors
- Rules follow identical format to existing Mac Mini rule (line 132, works)
- Network connectivity verified (ping 36ms RTT, no loss)
- Nbg uses 100.119.193.70 as source IP (verified via ip route get)
- Tried sslmode=disable and sslmode=prefer, same error
- Tried full Postgres restart, same error
- Byte-level comparison shows equivalent format to working rule

Hypotheses tested and refuted:
- Reload didn't pick up rules (pg_hba_file_rules shows them loaded)
- Wrong file being loaded (hba_file path confirmed)
- Invisible characters (od -c shows clean bytes)
- Format differences (clean rewrite matching Mac Mini format)
- Firewall blocking (ping works, pg_isready works)

Unresolved. Some Postgres edge case we haven't identified yet. Deserves fresh eyes next session, possibly community help, might be Homebrew Postgres build quirk.

### Side effect: Mac Mini replica broken

When we rotated the replicator password, Mac Mini's stored password in its .pgpass became stale. Mac Mini keeps failing authentication every 5 seconds (log noise only, no production impact).

Fix: Log into Mac Mini physically, update ~/.pgpass with new password stored on Mac Studio at ~/.config/phase-0/replicator.password. Not blocking Phase 0 resumption.

## Current state (at pause)

- Production: Mac Studio serving Nerq + ZARQ normally, 9 uvicorn workers, 200 OK
- Sacred bytes: 2/2/1 intact
- Mac Studio Postgres: pg_hba.conf restored from backup, wal_keep_size reset, replication slot dropped. Clean original state.
- Hetzner nodes: 3 provisioned and ready, nothing deployed yet
- Tailscale: all 7 nodes in mesh
- M5.1 experiment: ran at 07:03 today, on track for 2026-04-18 measurement
- Analytics dashboard: aggregation running every 15 min, fresh

## Open items for next Day 2 resumption

Priority 1 - Unblock replication:
1. Research Postgres no pg_hba.conf entry edge case with matching rule
2. Try ALTER ROLE ... WITH ENCRYPTED PASSWORD to force re-encryption
3. Create fresh replication user (nbg_replicator) to rule out stale state
4. Try sslmode=require even though server has ssl=off
5. Fallback: use pg_dump + transfer + pg_restore instead of streaming

Priority 2 - Fix Mac Mini replica:
1. Physical access, update .pgpass, restore connectivity

Priority 3 - Proceed with Day 2:
1. PostgreSQL base config on Nbg + Hel
2. Begin ZARQ Tier A table DDL generation

## Time spent Day 2

- Provisioning + hardening 2 nodes: 30 min
- Tailscale setup: 15 min
- Replication debugging: 60 min (unproductive)
- Cleanup + rollback: 10 min
- Documentation: 15 min
Total: ~2h 10min

## Lesson learned

When a config issue doesn't yield to rational debugging in 30 min, stop and come back fresh. 30-min rule for next time.
