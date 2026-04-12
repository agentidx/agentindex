# Phase 0 Day 1 — Complete

**Date:** 2026-04-12 (Sunday — execution moved from original 2026-04-13 plan)
**Status:** Day 1 complete, ready for Day 2
**Related:** `docs/session-handoff-2026-04-13-phase-0-day-1.md`, `docs/status/phase-0-day-0-decisions.md`

---

## What was accomplished

### Hetzner Nürnberg node provisioned

- **Server name:** nerq-nbg-1
- **Public IPv4:** 178.104.160.85
- **Public IPv6:** 2a01:4f8:1c19:6ea0::1
- **Tailscale IPv4:** 100.119.193.70
- **Server type:** CPX42 (8 shared vCPU x86, 16 GB RAM, 320 GB NVMe)
- **Location:** nbg1 (Nürnberg DC)
- **OS:** Ubuntu 24.04 LTS, kernel 6.8.0-100
- **Provisioned:** 2026-04-12 08:49 CEST

**Note: Original plan specified CPX41, but that series was deprecated by Hetzner in 2025-10 (unavailable after 2026-01-01). CPX42 is the direct successor (new generation, same specs, 8 cores / 16 GB RAM, 320 GB disk instead of 240 GB). Pricing: €31.86/month vs €40.61 for old CPX41 — actually cheaper.**

### Hardening completed

- System: `apt update && upgrade` ran clean
- User: `nerq` created with sudo NOPASSWD, SSH key copied from root
- Firewall: UFW active, allows 22, 80, 443, tailscale0
- Security: fail2ban enabled for SSH brute-force protection
- Updates: unattended-upgrades configured for security patches only
- Timezone: Europe/Stockholm

### Software installed

- Docker 29.4.0 + Docker Compose plugin
- PostgreSQL 16 client + server (apt.postgresql.org repo)
- Tailscale (ansluten till existing tailnet)
- Standard tools: ufw, fail2ban, htop, iotop, ncdu, tmux, vim, git, rsync, jq

**Not yet done (Day 2+):**
- SSH root login disabled (safety-net retained until Tailscale verified works across sessions)
- PostgreSQL configured (replication configured Day 3)
- No data loaded

### Tailscale integration

- Node joined tailnet successfully
- All 5 nodes visible: anderss-mac-studio, andersminis-mac-mini, iphone-14-plus, macbook-pro, nerq-nbg-1
- Direct mesh connections established where NAT permits
- SSH aliases configured on Mac Studio: `ssh nerq-nbg` (as nerq), `ssh nerq-nbg-root` (as root)

### ZARQ migration scope identified

Baseline capture of `crypto_trust.db` (1.2 GB, 67 tables) analyzed:
- 8 active tables (daily writes)
- 10 semi-active (monthly writes)
- 8 inactive (>30 days dormant)
- 41 tables with no timestamp column, 5 of which show recent Python code activity (UPSERT pattern)

**Final migration scope for Option A-light:** 12-22 tables, ~3M rows, ~150-310 MB. Documented in `docs/status/zarq-active-tables.md`.

---

## What stayed unchanged

- Mac Studio production: 9 uvicorn workers serving Nerq + ZARQ normally
- AI citations and traffic flowing as usual
- M5.1 experiment: ran kl 07:03 today, submitted 300K random-sampled URLs. Next: 2026-04-18 measurement.
- Analytics dashboard: aggregation LaunchAgent running every 15 min, cache fresh
- Sacred bytes verified intact: pplx-verdict=2, ai-summary=2, SpeakableSpecification=1
- Buzz: operating per updated OPERATIONSPLAN.md (commit b3b44b8)

---

## Time spent

- Pre-flight checks + research (hcloud CLI, server type selection): ~1 hour
- Server provisioning + hardening script: ~30 min (actual provisioning 5 min, script ran 10-15 min on server)
- Tailscale setup + verification: ~15 min
- ZARQ table analysis: ~20 min
- Documentation: ~15 min

**Total Day 1: ~2.5 hours execution time.**

Started ~08:30 CEST, completed ~11:00 CEST. Ran ahead of the 3-5h estimate because provisioning + hardening went smoothly.

---

## Deviations from plan

1. **CPX41 → CPX42.** Original plan referenced deprecated server type. Upgraded to new generation equivalent, actually slightly cheaper.
2. **Execution date moved forward.** Day 1 was scheduled for Monday 2026-04-13. Anders wanted to push through on Sunday 2026-04-12 morning.
3. **Cost baseline update.** ADR-003 estimated 2× CPX41 = €50/month. Actual: 2× CPX42 = €64/month. Budget adjustment reflected in `docs/status/phase-0-day-0-decisions.md`. Still within €100 total cap target.

---

## Open items for Day 2

1. **Provision Hetzner Helsinki node** (nerq-hel-1, CPX42)
2. **Provision CPX21 replacement** (likely CPX22 since CPX21 was also deprecated) — worker node
3. **Join both new nodes to Tailscale**
4. **Configure PostgreSQL replication:** Mac Studio primary → Nbg sync replica
5. **Optional start:** Begin generating Postgres DDL from SQLite schema for Tier A ZARQ tables

**Day 2 estimate:** 3-5 hours.

---

## Known gotchas for Day 2

- **Hetzner cloud-init quirk:** First boot may take 60-90s before SSH responds. Wait before testing.
- **Tailscale interactive vs heredoc:** `tailscale up --authkey=...` inside bash heredoc fails silently (inappropriate ioctl). Must run directly in shell. Heredoc works after initial auth.
- **Postgres deprecated types check:** `hcloud server-type list | grep -v Deprecation` may still show deprecated types in other regions. Verify each choice.

---

## Checklist

- [x] Hetzner CPX42 Nürnberg provisioned (was CPX41 in original plan — deprecated)
- [x] SSH works as `nerq` user via public IP and Tailscale IP
- [x] Firewall configured (ufw: 22, 80, 443, tailscale0)
- [x] Tailscale joined tailnet, visible from all other devices
- [x] Docker 29.4.0 + Compose installed
- [x] PostgreSQL 16 installed (not configured for replication yet)
- [x] Timezone = Europe/Stockholm
- [x] Active ZARQ table list written to `docs/status/zarq-active-tables.md`
- [x] Day 1 completion doc written (this file)
- [x] Production unchanged throughout, sacred bytes intact

---

*End of Phase 0 Day 1 completion report.*
