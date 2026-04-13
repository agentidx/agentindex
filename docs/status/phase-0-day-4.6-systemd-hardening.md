# Phase 0 Day 4.6 — systemd Hardening for nerq-api

Date: 2026-04-13
Status: COMPLETE — 14 of 15 hardening directives active on both nodes

## Before

```ini
# Hardening
NoNewPrivileges=true
PrivateTmp=true
```

2 directives.

## After

```ini
# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native
SystemCallFilter=@system-service
SystemCallFilter=~@privileged @resources
```

15 directives (14 new + 1 `SystemCallFilter` exclusion line).

## Directives kept (14)

| Directive | Purpose |
|---|---|
| NoNewPrivileges | Prevent privilege escalation via setuid |
| PrivateTmp | Isolated /tmp |
| ProtectSystem=full | /usr, /boot read-only |
| ProtectKernelTunables | Block /proc/sys writes |
| ProtectKernelModules | Block module loading |
| ProtectKernelLogs | Block /dev/kmsg |
| ProtectControlGroups | Block cgroup writes |
| RestrictNamespaces | Block namespace creation |
| RestrictRealtime | Block RT scheduling |
| RestrictSUIDSGID | Block setuid/setgid bits |
| LockPersonality | Lock execution domain |
| MemoryDenyWriteExecute | Block W+X memory (JIT) |
| SystemCallArchitectures=native | Only native arch syscalls |
| SystemCallFilter=@system-service / ~@privileged @resources | Allow service syscalls, deny privileged |

## Directives excluded (1)

| Directive | Reason |
|---|---|
| ProtectHome=true | Blocks `/home/nerq/agentindex` symlink which `zarq_websocket_webhooks.py` uses via `os.path.expanduser("~/agentindex/...")`. Would require refactoring all `~/` paths to `/opt/agentindex/` first. |

## Test results

| Endpoint | Nbg | Hel |
|---|---|---|
| `/` | 200 | 200 |
| `/safe/nordvpn` | 200 | 200 |
| `/v1/crypto/rating/bitcoin` | 200 | 200 |

## Rollback

```bash
sudo cp /etc/systemd/system/nerq-api.service.bak-hardening /etc/systemd/system/nerq-api.service
sudo systemctl daemon-reload && sudo systemctl restart nerq-api
```
