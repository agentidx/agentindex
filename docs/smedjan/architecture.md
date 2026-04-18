# Smedjan hybrid architecture (2026-04-18)

## One-line summary

Smedjan's factory lives on **smedjan.nbg1.hetzner**; the worker and
canary_monitor stay on **Mac Studio** because Claude Code 2.1.114 has no
viable headless Linux auth (see `runbooks/claude-code-linux-auth.md`).
Everything cross-host rides Tailscale.

## Host topology

```
┌───────────────────────────────────────────────────────┐
│                      anderss-mac-studio               │
│                   (100.90.152.88, CEST)               │
│                                                       │
│   nerq-api (uvicorn:8000) ── production               │
│   nerq-postgres (replica of 100.119.193.70) :5432     │
│       smedjan_readonly ── SELECT public/zarq          │
│   analytics.db (sqlite, 158K preflight + requests)    │
│                                                       │
│   Mac-resident Smedjan LaunchAgents:                  │
│     com.nerq.smedjan.worker.plist.disabled            │
│         (worker — awaits Phase B, stub until then)    │
│     com.nerq.smedjan.canary_monitor                   │
│         (every 2 min, reads local analytics.db +      │
│          Nerq-RO via Tailscale to smedjan-DB)         │
│     com.nerq.smedjan.analytics_export                 │
│         (03:00 Europe/Stockholm, sqlite → CSV → rsync)│
└──────────────────────────┬────────────────────────────┘
                           │   Tailscale
                           │ 100.64.0.0/10
                           ▼
┌───────────────────────────────────────────────────────┐
│                  smedjan.nbg1.hetzner                 │
│                (100.109.11.35, UTC, cx33)             │
│                                                       │
│   Postgres 16, listen localhost + Tailscale IP        │
│     DB `smedjan`:                                     │
│       schema smedjan            — tasks /             │
│                                    evidence_signals / │
│                                    heartbeats /       │
│                                    ai_demand_scores   │
│       schema analytics_mirror   — requests / preflight│
│                                    / requests_daily   │
│                                                       │
│   systemd timers (all Europe/Stockholm where TZ-set): │
│     smedjan-analytics-import 03:30                    │
│     smedjan-ai-demand        04:00                    │
│     smedjan-l1-observation   every 12h                │
│     smedjan-backup           02:00 (pg_dump+config)   │
│                                                       │
│   ~/smedjan/smedjan/ — configs, runbooks,             │
│                       observations, audits, backups   │
│   ~/agentindex/      — smedjan package + scripts only │
│                       (NOT the full Nerq tree)        │
└───────────────────────────────────────────────────────┘
```

## Connection profiles (who owns each DSN)

| DSN | Host | Reader/Writer | Purpose |
|---|---|---|---|
| `smedjan_app@smedjan:5432/smedjan` | Mac Studio Nerq-worker + smedjan CLI | RW | Factory writes: tasks, ai_demand_scores, analytics_mirror |
| `smedjan_app@localhost:5432/smedjan` | smedjan schedulers | RW | Same target, local path |
| `smedjan_readonly@localhost:5432/agentindex` | Mac Studio scripts | R | Nerq data via local replica |
| `smedjan_readonly@anderss-mac-studio:5432/agentindex` | smedjan schedulers | R | Nerq data via Tailscale |

One line in `config.toml` changes when Nerq moves: `nerq_readonly_source.dsn`. See `runbooks/nerq-migration.md`.

## Nightly sync at a glance

```
  Mac Studio 03:00 CEST                       smedjan 03:30 CEST
  ────────────────────────                    ──────────────────
  smedjan-analytics-export.sh                smedjan-analytics-import.sh
      sqlite3 → CSVs                              psql \copy TRUNCATE+COPY
      rsync → smedjan:/tmp/...                    updates
                                                  analytics_mirror._sync_state

  04:00 CEST                                  smedjan-ai-demand:
                                                reads analytics_mirror.preflight_analytics,
                                                writes smedjan.ai_demand_scores
```

Filter applied to `requests` mirror:
```
is_ai_bot = 1
OR path LIKE '/safe/%'
OR path LIKE '/compare/%'
OR path LIKE '/best/%'
OR path LIKE '/alternatives/%'
OR status >= 400
```
First sync: 151K preflight + 7.2M requests + 29K daily aggregates.

## Backups

smedjan `/home/smedjan/backups/` (mode 700):

```
  postgres/    — nightly pg_dump of smedjan DB (compressed, ~250 MB)
  config/     — nightly tar of config + migration-backups + runbooks
```

Retention: 7 days, rotation handled in-script. See
`runbooks/M15-rollback.md` for the data-dump taken the day the Nerq
primary was cleared of Smedjan objects.

## Paid-API stance

No component here calls a paid API. The worker uses the Max-subscription
`claude` CLI only (on Mac Studio); every other API call goes to free /
subscription-included services (ntfy.sh, GSC, Bing WMT, IndexNow, OSV,
OpenSSF Scorecard). Memory note: `feedback_no_paid_apis.md`.

## When each host is decommissioned

- **Mac Studio goes away** — worker, canary_monitor, and
  analytics-export exporter all need to move. Worker is blocked on
  Claude Code Linux auth. canary_monitor + analytics-export co-locate
  with whichever host runs Nerq-prod. See `runbooks/nerq-migration.md`.
- **smedjan goes away** — Postgres dump restorable from
  `/home/smedjan/backups/postgres/`. Rebuild a new host from
  `smedjan/schema.sql` + `smedjan/schema_analytics_mirror.sql`, restore
  latest dump, update Mac Studio config.toml to the new host's Tailscale
  name.
