# Phase 0 Day 4 — Hetzner App Deployment Complete

Date: 2026-04-13
Status: Both nodes running, entity pages serving, crypto endpoints pending

## Nodes

| Node | IP (Tailscale) | OS | Python | Postgres | Status |
|---|---|---|---|---|---|
| nerq-nbg-1 | 100.119.193.70 | Ubuntu 24.04 x86_64 | 3.12.3 | 16 replica (streaming) | **active (running)** |
| nerq-hel-1 | 100.79.171.54 | Ubuntu 24.04 x86_64 | 3.12.3 | 16 replica (streaming) | **active (running)** |

## Rsync

- Transfer size: 104 MB compressed (490 MB on disk)
- Excluded: venv/, .git/, logs/, *.db, node_modules/, integrations/, backups/
- Destination: /opt/agentindex/
- Symlink: /home/nerq/agentindex → /opt/agentindex

## pip install

Clean install on both nodes. System deps required: `python3.12-venv python3-dev libpq-dev build-essential`.
Additional: `Pillow` (for OG image endpoint).
No build failures. All 52 packages installed.

## Systemd service

```
/etc/systemd/system/nerq-api.service
ExecStart: uvicorn agentindex.api.discovery:app --host 0.0.0.0 --port 8000 --workers 4
User: nerq
Restart: always
EnvironmentFile: /opt/agentindex/.env
```

Enabled on both nodes (`systemctl enable nerq-api`).

## Health checks from Mac Studio via Tailscale

| Test | Nbg | Hel |
|---|---|---|
| `GET /` | 200 (148ms) | 200 (70ms) |
| `GET /safe/nordvpn` | 200 (1,071ms) | 200 (1,051ms) |
| `GET /robots.txt` | 200 | 200 |
| `GET /v1/crypto/rating/bitcoin` | 500 | 500 |

Entity pages work (read from local Postgres replica). Crypto API endpoints
return 500 because they read from empty SQLite crypto_trust.db (not yet
migrated to read from Postgres).

## Postgres access

Both nodes read from local replica via trust auth (pg_hba.conf modified):
```sql
SELECT pg_is_in_recovery() → true
SELECT count(*) FROM zarq.crypto_price_history → 1,125,586
```

`anstudio` role used for app access. No read-only role created yet (not
needed while pg_hba uses trust for localhost).

## SQLite stub databases

Created empty SQLite databases so the app doesn't crash on startup:

| Path | Purpose |
|---|---|
| agentindex/crypto/zarq_api_log.db | observability.py startup |
| agentindex/crypto/zarq_webhooks.db | zarq_websocket_webhooks.py |
| agentindex/crypto/crypto_trust.db | ZARQ crypto read path |
| agentindex/crypto/healthcheck.db | healthcheck module |
| data/crypto_trust.db | NDD data pipeline |
| logs/analytics.db | analytics middleware (writes to stub) |
| logs/ab_events.db | A/B test logging (created by app) |

## Code paths that tried to write (and how handled)

| Module | Write target | Resolution |
|---|---|---|
| observability.py:112 | zarq_api_log.db | Stub created, CREATE TABLE succeeds |
| analytics.py:307 | analytics.db | Stub created, writes to local stub (empty) |
| ab_test.py:88-107 | ab_events.db | App creates it on startup with _init_db() |
| zarq_websocket_webhooks.py:69 | zarq_webhooks.db | Stub created |
| flywheel_dashboard.py | analytics.db | Reads from stub (returns empty) |

**Note:** Analytics writes from Hetzner nodes go to local stub databases, NOT
to Mac Studio's production analytics.db. This is correct — Hetzner nodes
should not log analytics until they receive production traffic.

## Environment variables

```bash
NERQ_NODE=nbg|hel
NERQ_ROLE=replica
DATABASE_URL=postgresql://anstudio@127.0.0.1:5432/agentindex
ZARQ_DUAL_WRITE=0  # read-only replicas
NERQ_ANALYTICS_DISABLED=1
```

## Firewall

UFW active on both nodes. Only SSH (22/tcp) allowed from internet.
Port 8000 accessible via Tailscale only.

## Memory usage

- Nbg: 660 MB (4 workers)
- Hel: 656 MB (4 workers)
- CPX42: 16 GB RAM → ~4% usage

## Issues encountered

1. **python3.12-venv** not installed on Ubuntu 24.04 by default
2. **ProtectSystem=strict** in systemd blocked SQLite writes — removed
3. **ab_events.db** stub had wrong schema → deleted, let app create correctly
4. **Service bound to 127.0.0.1** → changed to 0.0.0.0 for Tailscale access (UFW blocks public)
5. **Postgres role "postgres" doesn't exist** on replicas (replicated from Mac Studio where superuser is anstudio) → changed pg_hba.conf to trust auth for localhost
6. **`~/agentindex` path** used by some modules → symlink from /home/nerq/agentindex → /opt/agentindex

## What works (Day 4 scope)

- [x] Codebase synced to both nodes
- [x] venv + deps installed
- [x] systemd service enabled and running
- [x] Entity pages served from Postgres replica (/safe/*, /best/*, /, etc.)
- [x] robots.txt, llms.txt serving
- [x] Static files serving (icons, CSS)
- [x] Health check from Mac Studio via Tailscale

## What doesn't work yet (Day 5+ scope)

- [ ] Crypto API endpoints (read from empty SQLite, not Postgres yet)
- [ ] DNS/Cloudflare tunnel not pointing to Hetzner nodes
- [ ] No load balancer configured
- [ ] No Redis on Hetzner nodes (cache disabled)
- [ ] Analytics writes go to local stub (not production)
- [ ] Dedicated read-only Postgres user not created

## Rollback

```bash
# On affected node:
ssh nerq-nbg  # or nerq-hel
sudo systemctl stop nerq-api
# Nothing else needed — DNS/tunnel not touched
```
