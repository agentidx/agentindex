# Tracking: healthcheck-based PgBouncer failover

**Opened:** 2026-05-30
**Severity:** medium (no current outage; addresses missing resilience)
**Owner:** unassigned
**Status:** tracking — do not implement yet, gather requirements first

## Context

2026-05-30 outage: `com.nerq.api` crash-looped because PgBouncer's
`agentindex_write` pool routed to Hel (100.79.171.54), whose PG had been off
for 25 days. PgBouncer kept queueing writes for 30s each then returning
`query_wait_timeout`. Recovery required manual diff of pgbouncer.ini, manual
repoint to Nbg, manual SIGHUP. No automated failover, no automated alarm.

Manual repoint was the right call in the moment, but it isn't permanent —
the next time a primary dies the same manual scramble repeats. The infra
healthcheck cron (`scripts/infra_healthcheck.py` + `com.nerq.infra-healthcheck`)
solves the *silent* part of the failure (we now get a row in
`zarq.infrastructure_alerts` within 5 min), but not the *failover* part.

## What this issue tracks

Evaluate options for *active* PgBouncer failover so a dead primary is routed
around automatically, not just alarmed about.

## Candidates

1. **HAProxy in front of PgBouncer** — TCP healthchecks on Patroni's REST API
   (`/master`, `/replica`) pick the current primary. Patroni already exposes
   the right endpoints. HAProxy is the canonical pattern in the Patroni docs.

2. **Patroni-aware PgBouncer pool reconfig** — script that polls Patroni's
   REST endpoint and rewrites `pgbouncer.ini` + SIGHUP when leader changes.
   Less moving parts than HAProxy; more bespoke code.

3. **Cloudflare Load Balancer at the application layer** — failover the
   *whole* API host pair, not just the DB. ADR-003 already specifies this
   for the FastAPI tier. Doesn't help local Mac Studio's connections to
   the cloud primary; complementary rather than substitute.

## Prerequisites that must be solved first

- **Patroni must actually be running.** As of 2026-05-30 both Patroni
  instances are dead (Hel since 2026-05-23, Nbg since 2026-05-26 OOM-kill).
  Any failover scheme relies on a working DCS.
- **etcd cluster must tolerate a node loss.** Current 2-node cluster is
  single-failure intolerant by Raft math. Need 3 nodes (or external DCS).
- **Memory pressure on Nbg** killed Patroni once already (OOM). Investigate
  whether `vm.swappiness`, `huge_pages`, or PG `shared_buffers` need tuning
  before re-enabling Patroni.

## Decision needed

Not now. After:

1. Patroni is brought back up and verified leading.
2. Replication is re-established Nbg → Hel.
3. We've had at least a week of stable HA operation.

Then revisit and pick option 1, 2, or both.

## Related

- `scripts/infra_healthcheck.py` — periodic alarm; doesn't failover.
- `zarq.infrastructure_alerts` — surface for any future failover code to
  consume / annotate.
- `docs/adr/ADR-003-cloud-native-expansion-first.md` — original HA design
  (currently divergent from reality).
