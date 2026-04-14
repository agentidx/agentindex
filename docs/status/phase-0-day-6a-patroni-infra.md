# Phase 0 Day 6a — Patroni Infrastructure Installed

Date: 2026-04-14
Status: COMPLETE — etcd cluster active, Patroni installed but NOT running

## What IS active

| Component | Nbg | Hel | Status |
|---|---|---|---|
| etcd 3.5.21 | systemd enabled+running | systemd enabled+running | **Cluster healthy** |
| Patroni 4.1.1 | Installed, config at /etc/patroni/ | Installed, config at /etc/patroni/ | **NOT running** |
| PostgreSQL | streaming replica, 0 lag | streaming replica, 0 lag | **Unchanged** |
| nerq-api | 200 OK | 200 OK | **Unchanged** |

## What is NOT active

- Patroni systemd service: created but **NOT enabled, NOT started**
- Automatic failover: **NOT configured**
- Primary takeover: **NOT initiated**
- Mac Studio Postgres: **NOT touched**
- Cloudflare/DNS: **NOT touched**
- Dual-write: **NOT touched**

## etcd Cluster

```
Members:
  node1 (Nbg): cb760b2e0e78c1e9, http://100.119.193.70:2379
  node2 (Hel): f5d65b69fcc6941e, http://100.79.171.54:2379

Health:
  Nbg: healthy (27ms commit)
  Hel: healthy (124ms commit)
```

**2-node limitation:** A 2-node etcd cluster does NOT tolerate the loss of either member (quorum requires both). If one node dies, etcd becomes read-only. Options for Day 6b+:
- Add Mac Studio as 3rd etcd member (tolerates 1 failure)
- Accept 2-node limitation (manual recovery if one dies)

## Patroni Config (secrets redacted)

```yaml
scope: agentindex-cluster
namespace: /nerq/
name: node1  # or node2

etcd:
  hosts: 100.119.193.70:2379,100.79.171.54:2379

restapi:
  listen: 0.0.0.0:8008
  connect_address: <tailscale_ip>:8008

postgresql:
  data_dir: /var/lib/postgresql/16/main
  bin_dir: /usr/lib/postgresql/16/bin
  config_dir: /etc/postgresql/16/main
  authentication:
    superuser: anstudio
    replication: anstudio

bootstrap.dcs:
  ttl: 30, loop_wait: 10, retry_timeout: 10
  maximum_lag_on_failover: 1048576 (1 MB)
  use_pg_rewind: true, use_slots: true
```

Config validation: **passes** (port 5432 warning expected — Postgres already running under systemd, not Patroni).

## Verification results

| Check | Result |
|---|---|
| Nbg API /safe/nordvpn | 200 ✅ |
| Hel API /safe/nordvpn | 200 ✅ |
| Nbg PG streaming, 0 lag | ✅ |
| Hel PG streaming, 0 lag | ✅ |
| etcd cluster health | Both healthy ✅ |
| Patroni NOT running | inactive ✅ |
| dual_write_errors.log | Empty ✅ |

## Rollback

```bash
# Remove etcd
ssh nerq-nbg "sudo systemctl stop etcd && sudo systemctl disable etcd"
ssh nerq-hel "sudo systemctl stop etcd && sudo systemctl disable etcd"

# Remove Patroni
ssh nerq-nbg "sudo pip3 uninstall patroni -y && sudo rm -rf /etc/patroni"
ssh nerq-hel "sudo pip3 uninstall patroni -y && sudo rm -rf /etc/patroni"
```

Postgres streaming replication completely unaffected.

## Plan for Day 6b (NOT YET — wait for M5.1 results Apr 18)

1. Stop postgresql@16-main on Nbg
2. Start Patroni on Nbg (takes over Postgres)
3. Patroni initializes as replica from Mac Studio
4. Start Patroni on Hel (joins as second replica)
5. Verify Patroni cluster: `patronictl list`
6. Reconfigure dual_write.py to connect via Patroni leader endpoint

## Plan for Day 6c (primary switch)

1. Patroni promotes Nbg to primary
2. Mac Studio becomes replica (or disconnected)
3. Cloudflare tunnel/LB points to Nbg
4. DNS cutover
