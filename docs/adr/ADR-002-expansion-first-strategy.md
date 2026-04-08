# ADR-002: Expansion-First Strategy with Three-Tier Disaster Recovery

**Status:** Accepted
**Date:** 2026-04-08
**Supersedes:** ADR-001 (v2 platform migration — deferred)
**Author:** Anders Nilsson + Claude (technical co-founder)

## Context

Following the production incident on the morning of 2026-04-08 (SQLite lock cascade, resolved with 6 commits including the critical text-sort bug fix), we re-evaluated the proposed ADR-001 17-week v2 platform migration.

ADR-001 prioritized technical excellence: a full rewrite to a v2 platform with improved architecture, better testing, and cleaner abstractions. Estimated 17 weeks of focused work before any new features.

Anders pushed back on this trade-off with a clear re-prioritization:

> "Optimal technical solution now is not an end in itself. What matters is that it works during expansion."

Priorities clarified:
1. **Robustness** — system must survive Mac Studio single-point-of-failure
2. **AI-to-human conversion** — leverage the Claude citation spike (1.26M/week, 22x growth)
3. **Language expansion** — 22 → 50 languages
4. **Vertical expansion** — 14 → 100 verticals
5. **Monetization** — triggered at 150K human visits/day sustained for 7 days

A 17-week migration before any feature work was incompatible with these priorities.

## Decision

**Defer ADR-001. Adopt expansion-first strategy with minimal robustness foundation.**

### Three-Tier Disaster Recovery (new)

**Tier 1: Cloudflare R2 cache fallback (fastest failover)**
- Cloudflare Worker proxies to Mac Studio normally
- Async-writes successful responses to R2 bucket
- On 5xx or timeout from origin, serves cached R2 version
- Adds `X-Served-From: r2-fallback` header when active
- Cost: $5/month Workers Paid + negligible R2 storage
- Failover time: <100ms (Worker-level)

**Tier 2: Hetzner CPX32 Nürnberg async replica (manual promotion)**
- Different physical location from Mac Studio/Mac Mini (co-located in Stockholm)
- PostgreSQL async replica via Tailscale
- Cost: ~$15/month
- Failover time: 5-30 minutes (manual DNS change + promotion)
- Role: catastrophic failure recovery when primary hardware is lost

**Tier 3: Backblaze B2 backups via pgBackRest (archive)**
- Nightly full + continuous WAL archive
- Separate provider from R2 (avoid vendor lock-in risk)
- Cost: ~$2-5/month for current 80 GB DB
- Recovery time: hours (restore + replay)
- Role: ransomware / data corruption recovery

### Mac Mini as Primary Build Worker + Local Replica

- Mac Mini M4 (16 GB RAM, co-located with Mac Studio) repurposed from lightf1ow
- Lightf1ow paused (files preserved, backup complete)
- Mac Mini runs:
  - PostgreSQL 16 streaming replica of Mac Studio (async, via Tailscale)
  - Python build worker for vertical/language enrichment jobs
  - Can serve as failover primary in emergency
- Replication tested: ~10ms lag via Tailscale LAN
- LaunchAgent: `com.nerq.postgres-replica` (custom, bypasses brew services due to Tailscale socket issue)

### Phases

**Phase 0: Robustness Foundation (2-3 days)**
- Mac Mini Postgres replica ✅ (completed 2026-04-08)
- Cloudflare R2 fallback Worker
- pgBackRest to Backblaze B2
- Hetzner CPX32 provisioning
- Failover runbook documentation

**Phase 1: AI-to-human Conversion (background, ongoing)**
- Target 25% of pages with conversion-optimized content
- Monitor Claude citation → human visit funnel

**Phase 2: Language Expansion 22 → 50 (~15 days)**
- 2 languages/day on Mac Mini build worker
- Use local Postgres replica (read path)

**Phase 3: Vertical Pipeline Architecture (3-5 days)**
- Universal BaseEnricher plugin framework
- Yield-first prioritization

**Phase 4: Vertical Expansion 5 → 25 → 100**
- Scale vertical count using Phase 3 framework
- Use local replica for read-heavy enrichment

**Phase 5: Monetization Trigger OR v2 Evaluation**
- At 150K human visits/day × 7 days sustained → activate monetization
- At that point, re-evaluate ADR-001 with revenue context

### Cost

- R2 Workers Paid: $5/month
- Hetzner CPX32: $15/month
- B2 storage: $2-5/month
- **Total: ~$22-25/month new spend**
- **Hard cap: $100/month** before we re-evaluate

## Consequences

### Positive

- **Survives Mac Studio failure** via three independent recovery layers
- **Build capacity doubled** (Mac Mini as dedicated worker)
- **Expansion continues** — no 17-week pause
- **Revenue path preserved** — monetization trigger unchanged
- **ADR-001 remains an option** — deferred, not rejected

### Negative

- **Operational complexity increases** — more systems to monitor
- **Tailscale dependency** — replication and cross-machine comms rely on it
- **Manual Tier 2 failover** — not automatic, requires human action
- **Mac Mini co-located with Mac Studio** — LAN-level DR only, Hetzner is geographic DR

### Risks accepted

- **Power outage / fire** in Stockholm location → both Mac Studio and Mac Mini down simultaneously → Tier 2 (Hetzner) as fallback, 5-30 min recovery
- **Tailscale service outage** → falls back to direct LAN (10.39.1.x) if configured
- **Mac Mini M4 hardware failure** → reprovision from R2/B2, ~1 day recovery

## Implementation Notes

### Postgres Replication Gotcha (2026-04-08)

When Postgres is started via brew services on Mac Mini with Tailscale installed, the walreceiver child process fails to create outbound TCP sockets to LAN IPs (10.39.1.12) with "No route to host", even though ping, nc, psql (in replication mode), and pg_receivewal all work fine from the same machine.

Root cause appears to be Tailscale's socket interceptor interfering with launchd-spawned Postgres subprocess network context. `pg_receivewal` works because it's spawned from an interactive shell, not from launchd.

**Workaround:** Use Tailscale IP (100.90.152.88) instead of LAN IP in primary_conninfo. Custom LaunchAgent `com.nerq.postgres-replica` bypasses brew services.

### Replication Configuration

- Primary: Mac Studio, 10.39.1.12 / 100.90.152.88
- Replica: Mac Mini, 10.39.1.34 / 100.115.230.106
- Replication slot: `macmini_replica`
- User: `replicator` (24-char password, stored in `~/.pg_replicator_password` on primary)
- pg_hba.conf rules for both LAN and Tailscale IPs (Mac Mini only connects via Tailscale due to above bug)
- Mac Mini listen_addresses: `localhost,10.39.1.34` (does NOT listen on Tailscale — build worker connects via LAN or localhost)
- Mac Studio listen_addresses: `localhost,10.39.1.12,100.90.152.88`

### Resource Tuning on Mac Mini (16 GB RAM)

Adjusted from Mac Studio defaults (64 GB RAM):
- `shared_buffers`: 8GB → 2GB
- `effective_cache_size`: 48GB → 8GB
- `maintenance_work_mem`: 2GB → 256MB
- `wal_buffers`: 64MB → 16MB
- `max_wal_size`: 2GB → 1GB
- `max_connections`: kept at 100 (required to match or exceed primary)
- `work_mem`: 4MB (unchanged)

## References

- ADR-001: v2 platform migration (deferred)
- Day 33 transcript: /mnt/transcripts/2026-04-08-14-31-25-dag33-incident-adr002-replica.txt
- Mac Mini backup: /Users/anstudio/macmini-backups/20260408-141500/ (25 GB)
