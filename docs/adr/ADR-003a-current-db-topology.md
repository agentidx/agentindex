# ADR-003a: Current Postgres Topology — Partial Implementation of ADR-003

**Status:** Active: Partial implementation. Document what is, not what we want.
**Date:** 2026-05-30
**Supersedes:** ADR-003 status ("Accepted") for purposes of describing reality.
  ADR-003 remains the canonical end-state target; this document tracks the
  delta until the open issues are closed.
**Authors:** Anders Nilsson + Claude (during the 2026-05-30 outage triage)

## Why this document exists

ADR-003 was filed 2026-04-09 with status "Accepted". The implementation plan
ran 2026-04-09 → ~2026-05-28 (`docs/strategy/phase-0-cloud-migration-plan.md`).
On 2026-05-30 a triage of the `com.nerq.api` crash-loop and `zarq.ai`/`nerq.ai`
5xx outage revealed that the live state does not match the ADR-003 design.
Marking that ADR "Accepted" against current reality would be documenting
something false; future sessions consulting the ADR would build mental models
on it and act on them. This ADR-003a captures what is actually true today and
the work that remains to reach ADR-003.

## 1. Actual current state (2026-05-30)

| Node | Tailscale IP | Host | PG | Patroni | Role in etcd |
|---|---|---|---|---|---|
| **Nbg** (`nerq-nbg-1`) | `100.119.193.70` | up 48d, **RAM 13/15G + swap 7.5/8G**, load 3.69 | `postgresql@16-main` active since 2026-05-30 06:05, `pg_is_in_recovery()=f` → **de-facto primary** | **OOM-killed 2026-05-26 23:17**, never restarted | etcd up, `/service/agentindex/*` keys are **empty** |
| **Hel** (`nerq-hel-1`) | `100.79.171.54` | up 47d, idle (1.4 G / 15 G mem, 0 swap) | **stopped since 2026-04-12 09:32** (clean exit 0) | **exit 1 since 2026-05-23 06:16** (`etcd.EtcdConnectionFailed: No more machines in the cluster`) | etcd up, members keys empty |
| **Mac Studio local** | `127.0.0.1` | n/a | `pg_is_in_recovery()=t` → **standby**, `pg_last_wal_replay_lsn=38E/FC0000A0` vs Nbg `3A5/B27276D8` — large gap | n/a | n/a |

**Replication on Nbg:**

- Slot `node2` (Hel) — physical, `active=false`
- Slot `mac_studio_slot` — physical, `active=false`, no `restart_lsn`
- `pg_stat_replication` — empty (no senders right now)
- No streaming is happening from Nbg to anywhere

**etcd cluster:** healthy at the cluster level (both nodes reachable on :2379)
but unused by application — no Patroni instance is writing to it.

**PgBouncer (`/opt/homebrew/etc/pgbouncer.ini`):** `agentindex_write` pool now
routes to Nbg (`100.119.193.70:5432`); read pool stays on local Mac socket.
This was a manual repoint 2026-05-30 08:53 after the outage triage. Backup of
the previous Hel-pointing config: `pgbouncer.ini.bak-pre-nbg-repoint-20260530-0852`.

## 2. Diff vs. ADR-003 intent

| Aspect | ADR-003 intent | Reality 2026-05-30 |
|---|---|---|
| Primary | Hetzner Nbg | Nbg ✓ (but unmanaged — no Patroni) |
| Failover target | Hetzner Hel | Hel's PG off + Patroni dead |
| Failover mechanism | Automatic via Patroni, ~30–60s | Manual config edit + SIGHUP (what we did 05-30) |
| DCS | etcd, multi-node | 2-node etcd; not single-failure-tolerant by Raft math |
| Replication Nbg → Hel | Continuous streaming on `node2` slot | Slot exists, inactive, no upstream |
| Replication Nbg → Mac Studio | Optional accelerator | Slot exists, inactive; standby has large LSN gap |
| Cloudflare LB in front of both Hetzner nodes | Specified | Not configured. Cloudflared tunnel still terminates at Mac Studio (see `CLAUDE.md`) |
| pgBackRest WAL archive → Backblaze B2 | Specified | Not verified in this session — out of scope |

## 3. Open architectural issues

Severity scale: P0 = active outage risk, P1 = next-failure-causes-outage, P2 = expansion blocker, P3 = nice-to-have.

### Issue 1 — Patroni dead on both nodes (P0)

- **What:** `systemctl status patroni` is `failed` on both Nbg (OOM 2026-05-26)
  and Hel (etcd-quorum exit 2026-05-23). Neither has been restarted.
- **Blast radius if triggered again:** any orchestration that relies on
  Patroni (leader election, automatic failover, replica bootstrap) is
  unavailable. Manual ops are the only recovery path.
- **Prerequisite to fix:** understand the Nbg OOM root cause (Issue 2)
  before restarting Patroni — otherwise it OOMs again.

### Issue 2 — Memory pressure on Nbg (P0)

- **What:** 13 GB of 15 GB resident + 7.5 GB of 8 GB swap in use. Load
  averages elevated. Patroni's OOM 2026-05-26 is consistent with this profile.
- **Blast radius if triggered:** OOM-killer takes whichever process is
  biggest; in 2026-05-26 it took Patroni. Could take PG itself next time.
- **Prerequisite to fix:** read-only diagnostic pass — top memory consumers,
  PG `shared_buffers` vs working set, any leaked Patroni/python processes,
  swap tuning (`vm.swappiness`).

### Issue 3 — 2-node etcd cluster is single-failure-intolerant (P1)

- **What:** Raft quorum requires `floor(N/2) + 1`. For N=2, quorum = 2. Lose
  one node → cluster cannot make progress → Patroni can't lease → Patroni dies.
  This is exactly what happened 2026-05-23 when Nbg dropped from etcd's view.
- **Blast radius:** any single-node outage in the etcd cluster takes HA
  offline. Today that means Nbg failure also kills Hel's ability to be
  promoted, because Hel-side Patroni can't lease either.
- **Prerequisite to fix:** add a third etcd node. Candidates: Mac Studio
  local etcd, a CPX11 Hetzner micro, or external DCS (e.g. Consul). Spec
  decision needed.

### Issue 4 — No Cloudflare LB in front of Hetzner nodes (P2)

- **What:** ADR-003 specifies Cloudflare Load Balancer with 30s health checks
  for application-layer failover between Hetzner Nbg and Hel. Not configured.
  Cloudflared tunnel still terminates at Mac Studio (per `CLAUDE.md` tunnel
  ID `a17d8bfb-9596-4700-848a-df481dc171a4`, marked "scheduled for deletion").
- **Blast radius:** if Mac Studio dies, all of `zarq.ai` / `nerq.ai` go dark.
  No cloud serving. (Today the Hetzner nodes aren't even serving the API —
  the application layer hasn't migrated yet.)
- **Prerequisite to fix:** finish moving the FastAPI workload to Hetzner
  (separate, larger work item). Not blocking DB issues.

### Issue 5 — Mac Studio standby has large LSN gap (P2)

- **What:** Mac Studio reports `pg_is_in_recovery()=t` with replay LSN
  `38E/FC0000A0` while Nbg primary is at `3A5/B27276D8`. The replication slot
  on Nbg (`mac_studio_slot`) is inactive — Mac Studio is not currently
  streaming. The gap is too large to catch up by streaming alone.
- **Blast radius:** if "Mac Studio is a usable replica" is assumed in any
  failover plan, it isn't. Stale read responses if anything routes there
  for reads (note: the API's read pool DOES route to local Mac socket per
  PgBouncer config — read freshness is unverified).
- **Prerequisite to fix:** either re-bootstrap via `pg_basebackup` from Nbg
  + re-establish streaming, or decommission the Mac Studio replica role
  entirely and route reads elsewhere.

## 4. Decision log

| Date | Decision / event | Logged where | Versioned? |
|---|---|---|---|
| 2026-04-09 | ADR-003 written, status "Accepted" | `docs/adr/ADR-003-cloud-native-expansion-first.md` | yes |
| 2026-04-12 09:32 | PG stopped on Hel (clean exit; HA reconfiguration) | systemd journal on Hel | no |
| 2026-05-03 | Nbg dies (OOM per memory note) | session memory only | no |
| 2026-05-05 09:06 | PgBouncer `agentindex_write` repointed to Hel ("hel-promote") | `pgbouncer.ini.bak-pre-hel-promote-20260505-0906` | no — direct ops edit, no commit |
| 2026-05-05 → 2026-05-30 | **25 days of silent write-pool failure** — Hel:5432 closed, every write returned `query_wait_timeout`. API kept serving reads from local replica so external endpoints mostly looked OK; the writes that did happen accumulated into worker-boot retry storms | `api_error.log`, PgBouncer log | no monitoring |
| 2026-05-23 06:16 | Patroni dies on Hel (etcd-quorum exit) | journalctl on Hel | no |
| 2026-05-26 23:17 | Patroni OOM-killed on Nbg | journalctl on Nbg | no |
| 2026-05-27 18:17 | PG shut down on Nbg | journalctl on Nbg | no |
| 2026-05-30 06:05 | PG restarted on Nbg (autoheal? manual? source unknown) | journalctl on Nbg | no |
| 2026-05-30 08:43 | `com.nerq.api` enters fatal restart-loop (KeepAlive bounce 2135 → 2139 runs) | `logs/api_error.log` | no |
| 2026-05-30 08:53 | PgBouncer repointed back to Nbg + SIGHUP; API up | `pgbouncer.ini.bak-pre-nbg-repoint-20260530-0852` + this ADR | partial — backup file only |
| 2026-05-30 ~09:10 | `com.nerq.infra-healthcheck` LaunchAgent + `zarq.infrastructure_alerts` deployed so the next silent-failure window is bounded to 5 minutes, not 25 days | `scripts/infra_healthcheck.py`, `~/Library/LaunchAgents/com.nerq.infra-healthcheck.plist`, PG schema | yes (the code; LaunchAgent itself is outside git) |

## 5. Path forward (work-items, not committed plan)

These are required to converge ADR-003a (current) toward ADR-003 (intent).
**Documenting only.** Not a plan we have agreed to execute — decisions about
ordering, owners, and whether some of these stay deferred are still open.

1. **Read-only diagnostic of Nbg memory pressure.** Top consumers,
   PG configuration vs hardware, anything leaking. Output: a root cause
   for the 2026-05-26 OOM. Blocks Patroni restart.
2. **Patroni bootstrap on Nbg.** Once memory is understood. Verify cluster
   initialize in etcd, leader key set, replica slot states.
3. **Hel re-bootstrap.** `pg_basebackup` from Nbg, start PG as standby,
   verify replication streaming on `node2` slot.
4. **Decide: third etcd node.** Mac Studio local, a CPX11, or external DCS.
   This is a design decision, not just an install task.
5. **Mac Studio replica: keep or decommission.** If keep, re-bootstrap.
   If decommission, remove `mac_studio_slot` on Nbg and route reads
   elsewhere (PgBouncer config + application reconfig).
6. **Cloudflare LB + Hetzner serving migration.** ADR-003 specifies but
   never implemented. Separate work item; out of scope for "DB topology".
7. **Versioning ops changes.** Today PgBouncer config edits and Patroni
   bootstrap commands aren't versioned. Move `pgbouncer.ini` to a git-tracked
   location or a config-management mechanism so the 5 maj-style undocumented
   change can't happen again silently.

## 6. Risks if current state persists

Listed so we know what we're carrying.

- **Silent failure resurgence:** the healthcheck cron deployed 2026-05-30
  catches new connection-level failures within 5 min. It does NOT catch:
  - PG accepting connections but returning wrong/stale data
  - PgBouncer pool-saturation that doesn't manifest as connect failure
  - Replication lag silently growing
  Augment alarms with logical-state probes when there's appetite.
- **OOM-loop re-occurs:** without finding the root cause of Nbg memory
  pressure, the next OOM is a question of when, not if. Probability rises
  with traffic and with any new write-heavy job (rating engine doubles in
  size, etc.).
- **No real HA:** "Patroni-managed automatic failover" is a slide in
  ADR-003, not a deployed reality. Any Nbg failure today causes a manual
  scramble identical to 2026-05-30. ETA-to-recovery is human-attention-bound.
- **Documentation drift will recur** unless ops changes are versioned and
  ADR re-visits become part of recovery procedures (this document is itself
  an attempt at that).

## Re-visit trigger

Convert ADR-003a back into ADR-003 (status "Accepted, implemented") only
when:

- Patroni is running on both Nbg and Hel
- Replication is streaming on both slots, lag < 60s sustained for 7 days
- etcd cluster has 3+ nodes
- A simulated Nbg failure has been tested end-to-end and Hel auto-promoted
  within ADR-003's 30–60s target

Until then this ADR remains the source of truth for current DB topology.
