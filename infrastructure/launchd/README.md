# launchd LaunchAgents

These are macOS LaunchAgent property list files that run Nerq + ZARQ
infrastructure on the Mac Studio host. They are checked into the repo
for reproducibility, audit, and disaster recovery — but the live copies
on the Mac Studio are in `~/Library/LaunchAgents/`, not here.

Treat the files in this directory as **the canonical version**. If you
edit a live plist on the Mac Studio, copy it back here and commit.

> **Ops discipline (post-ADR-003a):** any LaunchAgent, PgBouncer config
> change, or other infra edit that lives outside git is a future incident
> waiting to happen. The 5 maj 2026 PgBouncer Hel-promote was a direct
> ops edit; it caused 25 days of silent write-pool failure. New infra
> artifacts go into git first, get applied second.

## Files

### com.nerq.api.plist

Runs the main Nerq + ZARQ FastAPI application via uvicorn on port 8000.
This is the primary user-facing service.

Current configuration:
- 8 worker processes (Mac Studio M1 Ultra has 20 cores)
- `--limit-concurrency 50` per worker (returns 503 above this instead
  of queuing forever)
- `--backlog 256` (TCP listen backlog)
- `--timeout-keep-alive 30` (close idle connections after 30s to prevent
  Cloudflared connection accumulation)

History:
- 2026-04-08: Increased workers from 4 to 8 and added concurrency limits
  after a worker backpressure incident took the API down for ~2 hours.
  See findings #21.

### com.nerq.analytics-cache.plist

Runs `scripts/refresh_analytics_cache.py` every 30 minutes (1800s) to
pre-compute the data backing `/admin/analytics-dashboard`. Without this,
the dashboard would run a 70-second SQLite query under each HTTP request
and exhaust workers.

Configuration:
- `StartInterval`: 1800 seconds (30 minutes)
- `RunAtLoad`: true (refresh immediately on macOS boot or `launchctl load`)
- `Nice`: 10 (lower priority so it does not compete with web traffic)
- Logs to `~/agentindex/logs/analytics_cache_refresh.log`

History:
- 2026-04-08: Created after the 70-second analytics_dashboard query
  caused worker exhaustion. See findings #18.

### com.nerq.infra-healthcheck.plist

Runs `scripts/infra_healthcheck.py` every 5 minutes (300s). The script
parses the active `pgbouncer.ini`, TCP-probes each `[databases]` host:port,
and opens / bumps / resolves rows in `zarq.infrastructure_alerts` so a
dead Postgres host surfaces in minutes instead of weeks.

Configuration:
- `StartInterval`: 300 seconds (5 minutes)
- `RunAtLoad`: true
- `PGBOUNCER_INI`: `/opt/homebrew/etc/pgbouncer.ini`
- `INFRA_ALERT_DSN`: writes alerts to `zarq.infrastructure_alerts` on Nbg
- Logs to `~/agentindex/logs/infra_healthcheck.log`

History:
- 2026-05-30: Created after the 25-day silent failure where PgBouncer's
  `agentindex_write` pool routed to Hel's :5432 (closed) without any alarm.
  Root cause documented in `docs/adr/ADR-003a-current-db-topology.md`.

## Installation

To install or reinstall any of these LaunchAgents on the Mac Studio:
```bash
# Copy plist into the live LaunchAgents directory
cp infrastructure/launchd/com.nerq.api.plist ~/Library/LaunchAgents/

# Validate
plutil -lint ~/Library/LaunchAgents/com.nerq.api.plist

# Unload existing if running
launchctl unload ~/Library/LaunchAgents/com.nerq.api.plist 2>/dev/null

# Load fresh
launchctl load ~/Library/LaunchAgents/com.nerq.api.plist

# Verify it is running
launchctl list | grep nerq
```

To check status of a running LaunchAgent:
```bash
launchctl list | grep nerq
```

The first column is the PID (`-` if not running), the second is the
last exit code, the third is the label.

## Adding a new LaunchAgent

1. Create the plist file in this directory
2. Validate with `plutil -lint your-file.plist`
3. Update this README with what it does
4. Copy to `~/Library/LaunchAgents/`
5. `launchctl load ~/Library/LaunchAgents/your-file.plist`
6. Commit the new file in this directory

## Future LaunchAgents to add

These services currently run via cron or manually and should eventually
be migrated to launchd for better lifecycle management:

- `daily_backup.sh` (currently in cron, runs at 01:30)
- ZARQ dashboard cache refresh (script exists, LaunchAgent not yet
  installed: `scripts/refresh_zarq_dashboard_cache.py`)
- IndexNow batch submission
- Sitemap regeneration
- Trust score recalculation

This list maps to the OpenClaw steady-state plan in
`~/nerq-todos/openclaw-steady-state-guide.md`.
