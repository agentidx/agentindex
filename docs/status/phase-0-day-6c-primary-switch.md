# Phase 0 Day 6c — Primary Switch Complete

**Started:** 2026-04-14 12:03 CEST
**Completed:** 2026-04-14 12:38 CEST
**Duration:** 35 minutes (including 25 min pg_rewind)
**Status:** SUCCESS — Nbg is primary, Mac is replica

## Timeline

| Time | Phase | Action | Result |
|---|---|---|---|
| 12:03 | Pre-flight | All checks pass | Replication 0 lag, LSN 2E9/F40AE340 |
| 12:03 | Phase 1 | Pause 24 writing LaunchAgents | All unloaded |
| 12:03 | Phase 2 | Wait for replication catch-up | 22KB lag (negligible) |
| 12:04 | Phase 3 | Activate Patroni on Nbg | **FAILED** — etcd v2 API disabled |
| 12:04 | Rollback | Restore Nbg postgresql@16-main | Recovered in 30s |
| 12:04 | Fix | Change Patroni config `etcd:` → `etcd3:` | Both nodes |
| 12:07 | Phase 3 retry | Activate Patroni on Nbg | **Nbg = Leader (TL 2)** |
| 12:07 | Phase 3b | Activate Patroni on Hel | **Hel = Replica** |
| 12:08 | Phase 4 | Stop Mac Postgres | Stopped |
| 12:08 | Phase 4 | pg_rewind (37 GB via Tailscale) | 25 min, successful |
| 12:37 | Phase 4 | Configure Mac as standby | standby.signal + primary_conninfo |
| 12:37 | Phase 4 | Create replication slot mac_studio_slot | Created |
| 12:37 | Phase 4 | Start Mac as replica | **Streaming, 0 lag** |
| 12:38 | Phase 5 | Update 15 plists: 100.90.152.88 → 100.119.193.70 | Done |
| 12:38 | Phase 5 | Reload 24 LaunchAgents | All loaded |
| 12:38 | Phase 6 | End-to-end verification | **All pass** |

## New Topology

```
Nbg (100.119.193.70) ← PRIMARY (Patroni Leader, TL 2)
  ├── Hel (100.79.171.54) ← Replica (Patroni node2)
  └── Mac Studio (100.90.152.88) ← Replica (external streaming)
```

## Verification Results

| Check | Result |
|---|---|
| Patroni cluster | Nbg=Leader, Hel=Replica ✅ |
| Mac pg_is_in_recovery() | true ✅ |
| Mac streaming from Nbg | 0 lag ✅ |
| Production API (localhost) | 200 ✅ |
| Production API (nerq.ai) | 200 ✅ |
| dual_write_errors.log | 0 lines ✅ |

## Issue Encountered + Resolution

**etcd v2 API:** Patroni 4.1.1 with `etcd:` config tries v2 API (`/v2/`), but etcd 3.5.21 has v2 disabled by default. Fixed by changing `etcd:` → `etcd3:` in both Patroni configs. Nbg Postgres was restored from systemd within 30 seconds during the first failed attempt.

## Rollback Procedure (if needed later)

```bash
# 1. Stop Patroni on Hetzner
ssh nerq-nbg "sudo systemctl stop patroni && sudo systemctl disable patroni"
ssh nerq-hel "sudo systemctl stop patroni && sudo systemctl disable patroni"

# 2. Re-enable systemd Postgres
ssh nerq-nbg "sudo systemctl enable postgresql@16-main && sudo systemctl start postgresql@16-main"
ssh nerq-hel "sudo systemctl enable postgresql@16-main && sudo systemctl start postgresql@16-main"

# 3. Remove standby.signal on Mac
rm /opt/homebrew/var/postgresql@16/standby.signal
# Remove primary_conninfo from postgresql.auto.conf
brew services restart postgresql@16

# 4. Restore LaunchAgent plists
cp ~/Library/LaunchAgents/.bak-day6c/* ~/Library/LaunchAgents/
# Reload all plists
```

## What changed

- **Mac Studio:** Was primary → now replica of Nbg
- **Nbg:** Was replica → now Patroni-managed primary
- **Hel:** Was replica of Mac → now Patroni-managed replica of Nbg
- **LaunchAgents:** 15 plists updated from 100.90.152.88 → 100.119.193.70
- **Patroni configs:** `etcd:` → `etcd3:` on both nodes
