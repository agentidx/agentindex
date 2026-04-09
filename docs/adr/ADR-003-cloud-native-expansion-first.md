# ADR-003: Cloud-Native Expansion-First Architecture with Freshness SLA

**Status:** Accepted
**Date:** 2026-04-09
**Supersedes:** ADR-002 (expansion-first strategy with three-tier DR) — superseded in its DR tier ordering and infrastructure placement. The expansion-first principle from ADR-002 is preserved and strengthened.
**Related:** ADR-001 (v2 platform migration — remains deferred)
**Authors:** Anders Nilsson + Claude

## Context

ADR-002, adopted the day before this one, established an expansion-first strategy with Mac Studio as primary, Mac Mini as local replica, and Hetzner as a manual-failover warm standby. The assumption was that Mac Studio + Mac Mini co-location in Stockholm was acceptable because Hetzner provided geographic DR.

On 2026-04-09, during planning for the Cloudflare R2 cache-fallback Worker (ADR-002 Phase 0 Step 2), three things became clear:

1. **The R2 cache-fallback approach does not scale.** At current traffic it costs ~$40/month. After successful expansion to 50 languages and 100 verticals, the same naive approach would cost $220-250/month due to R2 write operations. This exceeds the $100/month cap and provides static fallback only — ZARQ's dynamic risk data cannot be served from stale cache.

2. **The robustness target was too weak.** ADR-002 assumed Mac Studio or Mac Mini would fail independently. Anders raised the target: the system must survive permanent loss of both machines simultaneously (fire, flood, theft, power event affecting Stockholm location). With both machines co-located, the old DR tier ordering provided only geographic redundancy via Hetzner as a secondary — not a production-grade primary.

3. **Expansion demands continuous compute.** The expansion plan targets 100 verticals and 50 languages. Beyond the initial build, the product's core value proposition — trust scores as a reliable real-time source — requires continuous re-scoring, signal ingestion, and page freshness management. This is not a one-time compute spike; it is a permanent workload that must be designed into the architecture.

The existing ADR-002 plan addressed none of these in a way that would survive contact with reality. A replacement was needed before any infrastructure was built, not after.

## Decision

**Adopt a cloud-native architecture with Mac Studio and Mac Mini demoted to optional accelerators. Self-host Postgres and FastAPI on two Hetzner nodes in different datacenters. Render pages on-demand with tier-based cache TTLs tied to a published freshness SLA.**

### Core architectural shifts from ADR-002

| Dimension | ADR-002 | ADR-003 |
|---|---|---|
| Primary serving | Mac Studio | Hetzner Nürnberg |
| Secondary serving | Hetzner (manual promote) | Hetzner Helsinki (automatic failover) |
| Mac Studio role | Primary, SPOF | Optional accelerator |
| Mac Mini role | Local replica | Optional accelerator |
| Survival target | Mac Studio OR Mac Mini failure | Permanent loss of both |
| Failover time | 5-30 min manual | 30-60 seconds automatic |
| DR Tier 1 | R2 cache fallback | Warm standby Hetzner node |
| DR Tier 2 | Hetzner async replica | Backblaze B2 pgBackRest |
| DR Tier 3 | Backblaze B2 | (removed — collapsed to two tiers) |
| Freshness model | Not specified | Four-tier SLA |
| Cost at current scale | ~$22-25/month | ~$75-85/month |
| Cost at 10x scale | ~$220-250/month | ~$80-95/month (flat) |

### Infrastructure

**Serving layer (HA):**
- 2× Hetzner CPX41 (8 vCPU, 16 GB RAM, 240 GB NVMe) — one in Nürnberg (nbg1), one in Helsinki (hel1)
- Each runs the full FastAPI stack, Redis, and a Postgres instance
- Public IPs on each, reached directly by Cloudflare
- Cloudflare Load Balancer with 30-second health checks performs automatic failover

**Database layer (self-hosted, async replication):**
- Postgres 16 primary on Nürnberg node
- Postgres 16 async streaming replica on Helsinki node (via Tailscale or WireGuard)
- Under failover, Helsinki is promoted to primary automatically via Patroni or equivalent, accepting <1 second of write loss (acceptable for this workload — Nerq rarely writes synchronously from user requests, ZARQ accepts a brief read-only window)
- pgBackRest ships continuous WAL archive + nightly full backups to Backblaze B2

**Scoring and signal-ingestion worker (always-on):**
- 1× Hetzner CPX21 (3 vCPU, 4 GB RAM, 80 GB disk) dedicated to continuous signal ingestion, scoring, cache invalidation, and IndexNow pings
- Reads from primary Postgres, writes signals and score updates back
- Handles Tiers 1-3 of the freshness SLA (see below)

**Burst compute (on-demand):**
- Hetzner CPX51 (16 vCPU, 32 GB RAM) provisioned on-demand for large expansion sprints or Tier 4 weekly full-rescores
- Average cost: $5-10/month across typical usage
- Runs only during active sprints, stopped otherwise

**Mac Studio + Mac Mini (optional accelerators):**
- If healthy, run signal-fetchers and scoring workers as gratis compute, offloading the CPX21 worker
- If dead, CPX21 takes full load (slower but functional)
- No production traffic depends on them
- Retained for 3-6 months post-migration; re-evaluated after monetization trigger

**Cloudflare Tunnel:**
- Decommissioned after migration. Both Hetzner nodes are reached directly via Cloudflare's DDoS-protected edge. One fewer single point of failure, simpler debugging, simpler DNS.

### Freshness SLA (product commitment)

The four-tier SLA is both an internal compute budget and a public product commitment. It replaces vague "real-time" language with specific, measurable targets.

| Tier | Content | Update kadens | Render TTL | Volume (est.) |
|---|---|---|---|---|
| **1: Real-time** | ZARQ crypto tokens, active security CVEs, DeFi TVL/yield | Seconds to minutes (event-driven) | 60 seconds | ~30K localized pages |
| **2: Hot** | Top 1000 most-trafficked entities, trending packages | Every 15 minutes | 900 seconds | ~150K localized pages |
| **3: Warm** | Entities with new signals in the last 24 hours | Daily | 86400 seconds | ~500K localized pages |
| **4: Cold** | Full corpus of 5M entities | Weekly | 604800 seconds | ~700M theoretical, ~1-5M actually requested per week |

Critically, pages are **rendered on-demand, not pre-rendered**. A request arrives, Cloudflare checks edge cache, and on miss the origin renders from templates plus current Postgres data with the Cache-TTL set by tier. Score updates trigger explicit cache purges for affected URLs plus IndexNow pings. This means we never need to pre-render 700M pages, and Cloudflare's free edge cache absorbs almost all steady-state traffic.

### Freshness observability

A new dashboard tracks, per tier, the percentage of entities whose score is older than the tier SLA. The existing `stale_score_detector` (currently broken due to schema drift against `entity_lookup.trust_calculated_at`) will be fixed and become the data source. Alerts fire when any tier falls below 95% SLA compliance for more than one hour. Without this, "trust source" is a claim; with it, it is verifiable.

### Buzz migration

Buzz (openclaw autonomous operator) migrates from Mac Studio to the Nürnberg node. Mac Studio optionally runs a secondary Buzz instance for when Hetzner Nürnberg fails, with a simple watchdog promoting whichever is healthy. This means Buzz survives permanent Mac Studio loss — a requirement that ADR-002 did not address.

### Acceleration sequencing

The expansion plan targets 50 languages and 100 verticals. Anders made clear on 2026-04-09 that the target is aggressive acceleration once the infrastructure is in place. ADR-003 commits to a specific sequence that respects the hard prerequisites:

1. **Cloud migration first (2 weeks)** — ADR-003 infrastructure built. New vertical expansion paused during this window. Language expansion and hidden registry fixes continue in parallel on Mac Studio.
2. **Parameterize the Norwegian language-addition model (3-5 days)** — the existing process requires ~700 lines of manual Claude Code edits per language. This must be converted to a declarative `language_config.yaml` + `add_language.py` before 27 new languages are attempted. Without this, the 50-language sprint is impossible in the target timeframe.
3. **50-language sprint (5-10 days)** — parallel execution of 4-8 languages per batch, using the new parameterized pipeline, running on burst CPX51 or Mac Mini.
4. **Vertical pipeline build (3-5 days)** — declarative vertical config schema + build orchestrator + refactoring of hardcoded templates to config-driven. Without this, the 100-vertical sprint is impossible.
5. **100-vertical sprint (2-3 weeks)** — Rings 4-5 from the expansion plan via the new pipeline, parallel execution on burst compute.

Total timeline from 2026-04-09 to "100 verticals × 50 languages live with freshness SLA operational": 5-8 weeks.

### Cost

| Item | Monthly |
|---|---|
| 2× Hetzner CPX41 (serving + DB, Nbg + Hel) | ~€50 / ~$55 |
| 1× Hetzner CPX21 (always-on signal + scoring worker) | ~€5 / ~$6 |
| Cloudflare Load Balancer | $5 |
| Backblaze B2 (pgBackRest + WAL archive + SQLite rsync) | $5-8 |
| Burst compute (expansion sprints + Tier 4 rescores) | $5-10 |
| **Total** | **$75-85/month steady-state** |

Hard cap retained at $100/month. Cost is flat with respect to traffic volume — expansion to 50 languages and 100 verticals does not increase the bill unless we choose to upgrade to larger instances. ADR-002's R2 cache approach would have cost $220-250/month at the same scale.

## Consequences

### Positive

- **Survives permanent loss of both Stockholm machines.** The failure mode Anders explicitly required is now covered.
- **Automatic failover in 30-60 seconds.** ADR-002's 5-30 minute manual failover is replaced by Cloudflare Load Balancer health checks plus Patroni (or equivalent) promotion.
- **Cost is flat with expansion.** Growth does not create cost pressure. Monetization trigger (150K human visits/day × 7 days) arrives without architectural debt.
- **Freshness is a product feature, not a claim.** The four-tier SLA is measurable and marketable. "Updated within 60 seconds" is a stronger statement than "real-time."
- **Render-on-demand avoids the pre-render trap.** We never build 700M pages. Cloudflare edge cache handles almost everything.
- **Mac Studio becomes free capacity, not critical infrastructure.** Its death is inconvenient, not catastrophic.
- **Buzz survives Mac Studio failure.** The autonomous operator is no longer co-located with the production system it operates.
- **Cloudflare Tunnel removed.** One fewer SPOF, simpler network topology.
- **Expansion acceleration is architecturally supported.** Burst compute + parameterized language pipeline + declarative vertical pipeline make "100 verticals in a few weeks" actually possible.

### Negative

- **Initial migration is high-risk.** Moving 80 GB of Postgres, the full FastAPI app, Redis state, and Buzz's workspace to a new environment is 2 weeks of careful work. The plan must be executed in order with checkpoints.
- **Operational surface grows.** From one machine (Mac Studio) to three (Nbg CPX41, Hel CPX41, CPX21 worker) plus optional Mac Studio/Mac Mini plus occasional burst CPX51. More to monitor, more to secure.
- **Async replication loses <1 second of writes on failover.** Acceptable for this workload but not zero. If sync replication is ever required later, the design supports it.
- **Self-hosted Postgres means Anders/Buzz carries the ops burden.** No managed provider will fix issues. The trade-off is $30-50/month saved and no vendor lock-in.
- **Cloudflare Load Balancer adds $5/month and a new failure mode.** If CF routing itself fails, both origin nodes are unreachable. Mitigated by Cloudflare's own SLA being higher than anything else in the stack.
- **Weekly Tier 4 full rescore is compute-heavy.** Either runs on a serving node during off-peak (4-8 hours on CPX41) or on a burst CPX51 for ~$1-2/week. Must be scheduled and monitored.

### Risks accepted

- **Cloudflare account compromise or policy action.** We are deeply dependent on Cloudflare for DNS, CDN, LB, and DDoS. If Cloudflare cuts us off, recovery requires migrating DNS elsewhere, which takes hours. Mitigated by not violating policies and by keeping DNS TTLs reasonable.
- **Hetzner regional outage.** If both nbg1 and hel1 go down simultaneously (extremely rare but possible), we are offline until one recovers. B2 backups allow restoration to any other provider but this is a multi-hour recovery. Accepted because the alternative (three providers) is operationally complex for a pre-revenue product.
- **Tailscale or WireGuard dependency for replication.** If the overlay network fails between nodes, replication stops. Mitigated by monitoring lag and by Tailscale's own reliability track record.
- **Buzz's operational plan is still stale (dated February 2026).** This must be rewritten as part of Phase 0 or Buzz will continue operating on obsolete assumptions on the new infrastructure. Flagged as a dependency.

## Implementation notes

### SQLite analytics database handling

`analytics.db` (8.8 GB and growing) does not replicate via Postgres WAL. Three options were considered:

1. Migrate the `requests` table to Postgres — cleanest but weeks of work
2. Rsync every 10 minutes from primary to Helsinki and Backblaze B2 — accepts <10 min of analytics loss on failover
3. Accept that analytics stops during failover, resume when primary recovers

**Decision: option 2 for now, option 1 during a future quiet period.** Analytics is not customer-facing, so <10 min loss is tolerable. Migration to Postgres is tracked as a follow-up task, not a blocker.

### Cloudflare Tunnel decommissioning

Current tunnel ID is `a17d8bfb-9596-4700-848a-df481dc171a4` (noted as "ghost" in CLAUDE.md, already scheduled for deletion). Migration to direct-origin mode requires:

1. Opening ports 443 on both Hetzner nodes (standard, firewalled except from Cloudflare IPs)
2. Configuring Cloudflare origin rules to use the node public IPs
3. Testing that all existing DNS records resolve correctly
4. Removing the tunnel daemon from Mac Studio after validation

### Patroni vs pg_auto_failover vs manual promotion

Three options for automatic Postgres failover were considered. Patroni is the industry standard and integrates with etcd or Consul for consensus. pg_auto_failover is Postgres-native but less mature. Manual promotion is simple but defeats the 30-60 second failover target.

**Decision: Patroni with a simple 2-node + 1-witness topology.** The witness can be a tiny free-tier instance anywhere (Oracle Cloud free tier, Hetzner CX11, or even the CPX21 worker node). This is the only component where we accept moderate operational complexity because automatic failover is the core requirement.

### Freshness SLA as code

The four tiers must be expressed as code, not documentation. A `freshness_policy.py` module defines which entity belongs to which tier based on deterministic rules (Tier 1 = crypto token table membership; Tier 2 = analytics-derived top-1000 list refreshed hourly; Tier 3 = default for entities with signals newer than 24h; Tier 4 = everything else). The render path consults this module to set cache headers. The observability dashboard consults it to compute SLA compliance.

## References

- ADR-001: Nerq v2 architecture migration (deferred)
- ADR-002: Expansion-first strategy with three-tier DR (superseded in DR tier ordering and infrastructure placement)
- `docs/strategy/nerq-vertical-expansion-master-plan-v3.md` — vertical expansion plan
- `docs/buzz-context.md` — three-entity system documentation
- `docs/session-handoff-2026-04-09.md` — previous session context
- `docs/strategy/phase-0-cloud-migration-plan.md` — implementation plan for this ADR
