# Nerq migration — cutover checklist (from Smedjan's point of view)

**Purpose:** when Nerq-prod moves off Mac Studio (planned cutover window
22–25 April 2026, or any later migration), the Smedjan factory must
follow along with minimal downtime. Hybrid architecture makes this
mostly a config-file edit — *mostly*.

Smedjan components today:

| Component | Host | Reason |
|---|---|---|
| smedjan factory DB + schedulers (ai_demand_score, l1_observation, analytics-mirror-import) | **smedjan.nbg1.hetzner** | Durable factory home |
| Worker (factory_core loop) | **Mac Studio** | Claude Code Max-auth only works here; `~/smedjan/runbooks/claude-code-linux-auth.md` |
| canary_monitor | **Mac Studio** | Belongs with Nerq-prod (needs live analytics.db) |
| analytics-mirror exporter | **Mac Studio** | Co-located with the source analytics.db |
| Nerq replica Postgres (the `smedjan_readonly` source) | **Mac Studio** | Follows Nerq-prod |

## What changes when Nerq moves

Updates required per component:

| Host | Change | File(s) |
|---|---|---|
| Mac Studio | nothing if Mac Studio is decommissioned (see below), otherwise keep running | — |
| smedjan | point `nerq_readonly_source.dsn` at the new Nerq host | `~/smedjan/smedjan/config/config.toml` on smedjan |
| new Nerq host | install Claude Code + auth; move worker here | see `claude-code-linux-auth.md` (blocked unless Anthropic adds headless flow) |
| new Nerq host | move `canary_monitor` LaunchAgent/timer here | `scripts/canary_monitor_l1.py` + plist / systemd unit |
| new Nerq host | move `analytics-mirror-export` LaunchAgent here | `scripts/smedjan-analytics-export.sh` + `com.nerq.smedjan.analytics_export.plist` |
| smedjan-readonly role | replicate to the new Nerq primary (it is cluster-level so it replicates automatically if streaming replication is in use) | verify `SELECT rolname FROM pg_roles` on new host |
| new Nerq host | add pg_hba entry: `host agentindex smedjan_readonly 100.64.0.0/10 scram-sha-256` | `pg_hba.conf` |
| new Nerq host | `listen_addresses` must include the Tailscale IP | `postgresql.conf` |

## Cutover-day checklist

1. **Freeze Smedjan writes.**
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.nerq.smedjan.ai_demand.plist
   launchctl unload ~/Library/LaunchAgents/com.nerq.smedjan.l1_observation.plist   # only while on Mac Studio
   ssh smedjan 'sudo systemctl stop smedjan-analytics-import.timer'
   # worker: if already on new host, stop there; if still on Mac Studio, unload LaunchAgent
   ```
2. **Let the export finish** (if a cycle is in flight).
3. **Move Nerq-prod** per Anders' separate runbook.
4. **On the new Nerq host**, verify:
   - `psql -U smedjan_readonly -h localhost -d agentindex` connects
   - `pg_hba.conf` allows `100.64.0.0/10`
   - `listen_addresses` includes the new host's Tailscale IP
5. **On smedjan**, edit `~/smedjan/smedjan/config/config.toml`:
   - set `nerq_readonly_source.dsn` host to the new Nerq host (Tailscale hostname)
   - verify: `python3 -c "from smedjan import sources; import smedjan.config as c; print(c.NERQ_RO_DSN)"`
6. **Smoke-test** the change from smedjan:
   ```bash
   cd ~/smedjan && python3 -c "
   from smedjan import sources
   with sources.nerq_readonly_cursor() as (_, cur):
       cur.execute('SELECT count(*) FROM public.software_registry')
       print(cur.fetchone())
   "
   ```
7. **Move canary_monitor** to the new Nerq host (install
   `scripts/canary_monitor_l1.py` + a systemd timer or LaunchAgent there).
8. **Move analytics-mirror exporter** to the new Nerq host (install
   `scripts/smedjan-analytics-export.sh` + scheduler; update
   `SMEDJAN_RSYNC_TARGET` if the hostname of smedjan changed).
9. **Move worker** — blocked on Claude Code headless Linux auth. If that
   fix has landed, follow `claude-code-linux-auth.md`. If not, worker
   stays on Mac Studio until Mac Studio is decommissioned, and factory
   operates with a half-step (scheduler on smedjan, worker on Mac Studio,
   Nerq elsewhere). This is acceptable; worker writes are limited to
   the smedjan DB which is reachable from anywhere on Tailscale.
10. **Restart schedulers:**
    ```bash
    ssh smedjan 'sudo systemctl start smedjan-analytics-import.timer'
    launchctl load -w ~/Library/LaunchAgents/com.nerq.smedjan.ai_demand.plist
    launchctl load -w ~/Library/LaunchAgents/com.nerq.smedjan.l1_observation.plist
    ```
11. **Verify the first scheduled runs** complete without blocked tasks
    in smedjan.worker_heartbeats or errors in ntfy.

## What does NOT change

- smedjan factory DB (DSN, schema, seeds, task-queue)
- `~/smedjan/config/.env` on smedjan (passwords)
- analytics-mirror schema on smedjan DB
- Tailscale hostnames of smedjan and whichever hosts remain

## Emergency rollback

If the new Nerq host has problems and you need to send Smedjan back to
the old Nerq replica (while it still exists), it is a single-line DSN
edit on smedjan `config.toml` + restart schedulers. The smedjan_readonly
role on the old host continues to work as long as the replica is alive.

## Future cleanups (post-hybrid)

- When Claude Code adds headless Linux auth, move worker to smedjan and
  strike this runbook's "blocked" note.
- When analytics.db itself moves to Postgres-on-Hetzner (beyond the
  scope of this migration), the analytics-mirror export/rsync pipeline
  collapses into a cross-DB view inside the same Postgres cluster.
