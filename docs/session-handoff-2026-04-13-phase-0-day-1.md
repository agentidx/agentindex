# Session Handoff — Phase 0 Day 1 (2026-04-13)

**Date:** 2026-04-13 (Monday — first Phase 0 execution day)
**Status:** Ready to execute. All prereqs complete.
**Related:** `docs/strategy/phase-0-cloud-migration-plan.md`, `docs/status/phase-0-day-0-decisions.md`

---

## Pre-flight checklist (complete at session start)

Run these first to verify nothing has shifted since Day 0:

1. Git clean: `cd ~/agentindex && git status` should show no uncommitted changes
2. Latest: `git pull && git log --oneline -5` — should show `phase-0-day-0-decisions` as recent
3. Production healthy: `curl -sI https://nerq.ai | head -2` → 200
4. Sacred bytes: pplx-verdict=2, ai-summary=2, SpeakableSpecification=1 on `/safe/nordvpn`
5. Analytics dashboard fresh: `/tmp/nerq_analytics_dashboard.json` generated within last 30 min
6. Analytics aggregation running: `launchctl list | grep analytics-aggregation` → `- 0`
7. M5.1 experiment status: check `grep "M5.1 EXPERIMENT" /tmp/auto-indexnow.log | tail -3` — should show yesterday's run
8. No Buzz self-heal during migration: `head -30 ~/.openclaw/workspace/OPERATIONSPLAN.md` should show migration section

---

## Day 1 goals

**Primary:** Provision Hetzner Nürnberg CPX41 (nerq-nbg-1), harden, join Tailscale, prep for Postgres.

**Secondary:** Identify exact list of active ZARQ tables for Option A-light migration.

**Time estimate:** 3-5 hours.

---

## Execution plan

### Step 1: Provision Hetzner Nürnberg node (15-30 min)

Anders goes to Hetzner Cloud console. Creates server:
- Type: CPX41 (16 dedicated vCPU, 16 GB RAM, 240 GB NVMe)
- Location: nbg1 (Nürnberg)
- OS: Ubuntu 24.04 LTS
- SSH key: `mac-studio-anders` (already uploaded)
- Name: `nerq-nbg-1`
- Network: Default, note public IPv4

Alternatively use hcloud CLI (installed 2026-04-12):
```bash
hcloud server create \
  --name nerq-nbg-1 \
  --type cpx41 \
  --image ubuntu-24.04 \
  --ssh-key mac-studio-anders \
  --location nbg1
```

Once provisioned, Anders pastes IP to Claude in chat. Claude verifies SSH works.

### Step 2: Initial server hardening (1 hour)

Claude provides a setup script. Anders runs via SSH. Script does:
1. `apt update && apt upgrade -y && reboot`
2. Create user `nerq` with sudo
3. Disable root SSH login, password auth
4. Configure ufw firewall: allow 22, 80, 443. Tailscale will open 41641.
5. Install Docker, Docker Compose
6. Install PostgreSQL 16 client tools
7. Install pgbackrest client
8. Set timezone to Europe/Stockholm
9. Configure unattended-upgrades for security patches

### Step 3: Join Tailscale (15 min)

Install Tailscale, join the existing tailnet, verify connectivity to Mac Studio.

### Step 4: Prepare for Postgres installation (30 min)

- Install PostgreSQL 16 server (not configured yet)
- Allocate 150 GB of the 240 GB NVMe for Postgres data directory
- Don't start yet — we configure replication before first start

### Step 5: Identify active ZARQ tables (30 min, parallel)

While hardening runs, start a parallel task on Mac Studio:
```sql
-- Run for each table in crypto_trust.db
SELECT 
  'table_name' as table_name,
  COUNT(*) as rows,
  MAX(<timestamp_col>) as last_write
FROM <table_name>;
```

Identify tables with `last_write` within 30 days → these are the migration targets for Option A-light.

### Step 6: Document Day 1 completion (15 min)

Write end-of-day status:
- Nürnberg node IP
- Tailscale IP assigned
- Active ZARQ table list
- Any deviations from plan
- Any issues to address Day 2

Save as `docs/status/phase-0-day-1-complete-YYYY-MM-DD.md`.

---

## Day 1 checklist

- [ ] Hetzner CPX41 Nürnberg provisioned
- [ ] SSH works as `nerq` user (root disabled)
- [ ] Firewall configured (ufw allow 22, 80, 443)
- [ ] Tailscale joined, verified connectivity to Mac Studio
- [ ] Docker + Compose installed
- [ ] PostgreSQL 16 installed (not yet configured for replication)
- [ ] Timezone = Europe/Stockholm
- [ ] Active ZARQ table list written to `docs/status/zarq-active-tables.md`
- [ ] Day 1 completion doc written
- [ ] Production remains healthy throughout (verify at end of day)

---

## Safety protocols during Phase 0

- **Sacred bytes verified after every production-affecting change.** pplx-verdict=2, ai-summary=2, SpeakableSpecification=1.
- **Buzz is NOT self-healing during migration.** Per OPERATIONSPLAN.md, migration-related events are expected and Buzz escalates to Anders rather than acting.
- **Cutover window (Day 11-12) requires Anders's explicit GO.** No unilateral cutover execution.
- **Rollback always available.** Cloudflare Load Balancer flip back to Mac Studio is a <60s operation until Tunnel is decommissioned.

---

## What's NOT in Day 1

- Helsinki node (that's Day 2)
- CPX21 worker node (that's Day 2)
- Postgres replication configuration (Day 3 after restore)
- 57 GB data transfer (Day 3-4 overnight)
- App deployment (Week 2)
- Cutover (Day 11-12)

Day 1 is pure foundation. Don't over-reach.

---

*End of Phase 0 Day 1 Handoff.*
