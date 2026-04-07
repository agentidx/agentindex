# NERQ / AGENTINDEX — SYSTEM ARCHITECTURE
## ⚠️ READ THIS FILE AT THE START OF EVERY NEW CHAT SESSION ⚠️
### Last updated: 2026-03-01

---

## CRITICAL RULES

1. **NEVER run ALTER TABLE on the `agents` table** without first setting a statement timeout. This table has 4.9M rows and 15GB+ of data. An ALTER TABLE takes an exclusive lock that blocks ALL queries. The system deadlocked for 8+ hours on 2026-03-01 because of this.
2. **NEVER kill the API process without checking** that it will auto-restart (LaunchAgent has KeepAlive=true).
3. **PostgreSQL is the bottleneck.** The `agents` table is 15GB, `agent_jurisdiction_status` is 57GB. Any full table scan or DDL change can lock the system.
4. **Two separate database systems exist**: PostgreSQL (agents, 4.9M rows) and SQLite (crypto, `crypto_trust.db`, 336MB). They are independent.
5. **Always use heredoc format** for terminal commands: `bash << 'EOF' ... EOF`
6. **psql is not in PATH.** Use: `/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql`
7. **The system runs on a Mac Studio** at Anders' home in Italy, exposed via Cloudflare Tunnel. It is NOT a cloud server.

---

## ARCHITECTURE OVERVIEW

```
Internet
    │
    ▼
Cloudflare Tunnel (cloudflared, PID persistent)
    │
    ├── nerq.ai / api.nerq.ai / agentcrawl.dev → localhost:8000 (Discovery API)
    ├── dash.nerq.ai / dash.agentcrawl.dev     → localhost:8203 (Dashboard)
    └── mcp.nerq.ai / mcp.agentcrawl.dev       → localhost:8300 (MCP SSE Server)

localhost:8000 — Discovery API (FastAPI, uvicorn)
    ├── /v1/health, /v1/discover, /v1/register, /v1/agent/{id}, /v1/stats
    ├── /v1/mcp/discover
    ├── /.well-known/agent-card.json, /a2a
    ├── /v1/crypto/* (12 endpoints, Sprint 2.5)
    ├── /api/v1/crypto/trust-score/{type}/{id}
    ├── /crypto/* (SEO pages)
    ├── /agent/{id}, /best/*, /vs/* (SEO pages)
    ├── /comply/* (compliance)
    ├── /admin/dashboard (analytics)
    ├── /robots.txt, /llms.txt, /sitemap-*.xml
    └── / (landing page)

localhost:8203 — Dashboard (FastAPI, standalone)
    └── Action queue: approve/reject/dismiss agents

localhost:8300 — MCP SSE Server (Starlette)
    └── Tools: discover_agents, check_compliance, get_trust_score, etc.
```

---

## PROCESSES (LaunchAgents)

All managed via macOS LaunchAgents in `~/Library/LaunchAgents/`.
All use KeepAlive=true (auto-restart on crash) except crypto-daily.

| LaunchAgent | Process | Port | What it does |
|-------------|---------|------|-------------|
| `com.nerq.api` | `uvicorn agentindex.api.discovery:app` | 8000 | Main API serving everything |
| `com.agentindex.dashboard` | `python -m agentindex.dashboard` | 8203 | Admin dashboard with action queue |
| `com.agentindex.mcp-sse` | `python -m agentindex.mcp_sse_server` | 8300 | MCP protocol server (SSE transport) |
| `com.agentindex.orchestrator` | `python -m agentindex.run` | — | Runs all spiders on schedule (GitHub, npm, PyPI, HuggingFace, MCP) |
| `com.agentindex.parser` | `python run_parser_loop.py` | — | Parses raw crawled data into structured agents + MCP compliance |
| `com.nerq.crypto-daily` | `crypto_daily_master.py` | — | Daily crypto pipeline at 06:00 CET (NOT KeepAlive, calendar-triggered) |

### Cron Jobs (crontab)
| Schedule | Script | What |
|----------|--------|------|
| Sun 02:00 | `compute_trust_score.py` | Re-score all 4.9M agents (trust score) |
| Sun 03:00 | `trust_snapshot_export.py` | Snapshot + JSONL bulk export |
| Daily 09:00 | `check_prs.py` | Monitor GitHub PRs |

### Restart Commands
```bash
# Restart API
kill -9 $(ps aux | grep "discovery:app" | grep -v grep | awk '{print $2}')
# LaunchAgent auto-restarts within ~5 seconds

# Restart all services
launchctl kickstart -k gui/$(id -u)/com.nerq.api
launchctl kickstart -k gui/$(id -u)/com.agentindex.orchestrator
launchctl kickstart -k gui/$(id -u)/com.agentindex.parser
launchctl kickstart -k gui/$(id -u)/com.agentindex.dashboard
launchctl kickstart -k gui/$(id -u)/com.agentindex.mcp-sse
```

---

## DATABASES

### 1. PostgreSQL (`agentindex`)
**Connection:** `postgresql://localhost/agentindex`
**Size:** ~75GB total
**psql path:** `/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql`

| Table | Size | Rows | Description |
|-------|------|------|-------------|
| `agent_jurisdiction_status` | 57 GB | ~250M | Compliance status per agent per jurisdiction (52 jurisdictions × 4.9M) |
| `agents` | 15 GB | 4,916,895 | All indexed AI agents |
| `trust_score_history` | 1.8 GB | — | Weekly trust score snapshots |
| `crawl_jobs` | 416 KB | — | Crawl queue |
| `discovery_log` | 112 KB | — | API discovery request log |
| `jurisdiction_registry` | 88 KB | 52 | Jurisdictions with rules |
| `compliance_assessments` | 56 KB | — | Compliance results |
| `system_status` | 16 KB | — | System health |

**Key columns in `agents`:**
- `id` (UUID), `name`, `description`, `source` (github/npm/pypi/huggingface/mcp)
- `source_url`, `capabilities` (JSONB), `tags` (JSONB), `protocols` (JSONB array)
- `trust_score` (0-100), `trust_grade` (A-F), `is_active`, `crawl_status`
- `last_crawled`, `raw_data` (JSONB), `parsed_data` (JSONB)

**⚠️ DANGER ZONE:**
- `ALTER TABLE agents` → Takes exclusive lock, blocks everything. ALWAYS set `statement_timeout` first.
- `SELECT count(*) FROM agents` → Takes ~2-6 seconds (full table scan on 15GB).
- `UPDATE agents SET ... WHERE <no index>` → Can lock for hours. Always use indexed columns.

### 2. SQLite (`crypto_trust.db`)
**Path:** `~/agentindex/agentindex/crypto/crypto_trust.db`
**Size:** 336 MB
**Used by:** Crypto API endpoints, crypto daily pipeline

Key tables: `crypto_rating_daily`, `crypto_ndd_daily`, `nerq_risk_signals`, `crypto_price_history`, `crypto_portable_alpha_backtest`, `defi_tvl_history`

**Note:** The `nerq_risk_signals` table uses `signal_date` as its date column, NOT `run_date`. Other crypto tables use `run_date`.

### 3. Other SQLite DBs (minor)
- `logs/analytics.db` (3MB) — API analytics
- `discovery_analytics.db` (32KB) — Legacy
- `system_monitor.db` (888KB) — System metrics

---

## FILE STRUCTURE

```
~/agentindex/
├── agentindex/                    # Main Python package
│   ├── api/
│   │   ├── discovery.py           # ★ MAIN APP — FastAPI, all routes
│   │   ├── keys.py                # API key management
│   │   ├── a2a.py                 # Agent-to-Agent protocol
│   │   ├── api_protection.py      # Rate limiting, security
│   │   ├── multi_jurisdiction.py  # Multi-jurisdiction compliance API
│   │   └── semantic.py            # FAISS semantic search (optional)
│   ├── agents/
│   │   ├── parser.py              # Raw data → structured agent
│   │   ├── mcp_compliance.py      # MCP compliance classification
│   │   └── action_queue.py        # Approve/reject agent actions
│   ├── compliance/
│   │   ├── integration.py         # Compliance routes mount
│   │   └── badge_api.py           # Compliance badge API
│   ├── crypto/
│   │   ├── crypto_api_v2.py       # ★ Sprint 2.5 — v1/ crypto endpoints
│   │   ├── crypto_seo_pages.py    # /crypto/* HTML pages + /api/v1/crypto/trust-score/*
│   │   ├── crypto_daily_master.py # Daily pipeline orchestrator
│   │   ├── crypto_rating_daily.py # Trust Score computation
│   │   ├── crypto_ndd_daily_v3.py # NDD computation
│   │   ├── nerq_risk_signals.py   # Risk level computation (Step 5)
│   │   ├── portable_alpha_strategy.py # Backtest system
│   │   └── crypto_trust.db        # ★ SQLite crypto database (336MB)
│   ├── db/
│   │   └── models.py              # SQLAlchemy models (Agent, CrawlJob, etc.)
│   ├── spiders/                   # Crawlers (GitHub, npm, PyPI, HuggingFace, MCP)
│   ├── seo_pages.py               # /agent/{id}, /best/*, sitemaps, llms.txt
│   ├── vs_pages.py                # /vs/{a}/{b} comparison pages
│   ├── comparison_pages.py        # /compare/* pages
│   ├── analytics.py               # Analytics middleware + /admin/dashboard
│   ├── dashboard.py               # Standalone dashboard app (:8203)
│   ├── mcp_sse_server.py          # MCP SSE transport (:8300)
│   └── run.py                     # ★ Orchestrator — runs all spiders
├── run_parser_loop.py             # Parser loop (standalone)
├── compute_trust_score.py         # Weekly trust re-score (4.9M agents)
├── trust_snapshot_export.py       # Weekly snapshot + JSONL export
├── .env                           # Environment variables
├── logs/                          # All log files
└── venv/                          # Python 3.12 virtualenv
```

---

## CLOUDFLARE TUNNEL

**Tunnel ID:** `a17d8bfb-9596-4700-848a-df481dc171ad`
**Config:** `~/.cloudflared/config.yml`
**Log:** `~/.cloudflared/cloudflared_nerq.log`

| Hostname | Backend | Purpose |
|----------|---------|---------|
| `nerq.ai` | `localhost:8000` | Main site + API |
| `api.nerq.ai` | `localhost:8000` | API (same backend) |
| `dash.nerq.ai` | `localhost:8203` | Dashboard |
| `mcp.nerq.ai` | `localhost:8300` | MCP server |
| `agentcrawl.dev` | `localhost:8000` | Legacy domain |
| `api.agentcrawl.dev` | `localhost:8000` | Legacy API |

---

## CRYPTO DAILY PIPELINE

Runs daily at 06:00 CET via `com.nerq.crypto-daily` LaunchAgent.
Script: `agentindex/crypto/crypto_daily_master.py`

```
Step 1: Price fetch        → crypto_price_history (SQLite)
Step 2: Rating compute     → crypto_rating_daily
Step 3: NDD compute        → crypto_ndd_daily
Step 4: Crash model        → updates hc_alert, crash_probability, bottlefish in NDD
Step 5: Risk signals       → nerq_risk_signals
```

Covers ~200 tokens. Logs in `logs/crypto_daily_*.log`.

---

## API ENDPOINTS SUMMARY

### Agent Discovery (PostgreSQL)
- `POST /v1/discover` — Find agents by need
- `POST /v1/register` — Register an agent
- `GET /v1/agent/{agent_id}` — Agent details
- `GET /v1/stats` — System statistics
- `GET /v1/health` — Health check
- `POST /v1/mcp/discover` — MCP protocol discovery

### Crypto Intelligence (SQLite)
- `GET /v1/crypto/rating/{token_id}` — Trust Score
- `GET /v1/crypto/ndd/{token_id}` — NDD distress score
- `GET /v1/crypto/ratings` — All ratings (sortable, filterable)
- `GET /v1/crypto/signals` — Active risk warnings
- `GET /v1/crypto/signals/history` — Historical signals + outcomes
- `GET /v1/crypto/compare/{t1}/{t2}` — Compare tokens
- `GET /v1/crypto/distress-watch` — NDD < 2.0 tokens
- `GET /v1/crypto/safety/{address}` — Quick safety check
- `GET /v1/crypto/risk-level/{token_id}` — Risk classification
- `GET /v1/crypto/risk-levels` — All risk levels
- `GET /v1/crypto/portfolio/pairs` — L/S track record
- `GET /v1/crypto/portfolio/adaptive` — Portable Alpha variants
- `GET /api/v1/crypto/trust-score/{type}/{id}` — Legacy trust-score endpoint

### SEO / HTML Pages
- `/` — Landing page
- `/crypto` — Crypto hub
- `/crypto/token/{id}` — Token pages
- `/agent/{id}` — Agent pages
- `/best/*` — Category rankings
- `/vs/{a}/{b}` — Comparisons
- `/methodology` — Methodology page
- `/sitemap-*.xml` — Sitemaps
- `/robots.txt`, `/llms.txt`, `/llms-full.txt`

### Admin
- `/admin/dashboard?hours=24` — Analytics dashboard
- `/swagger` — OpenAPI docs

---

## ENVIRONMENT

| Variable | Value | Used by |
|----------|-------|---------|
| `DATABASE_URL` | `postgresql://localhost/agentindex` | All PostgreSQL code |
| `REDIS_URL` | `redis://localhost:6379` | API caching |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local LLM (Qwen 2.5) |
| `OLLAMA_MODEL_SMALL` | `qwen2.5:7b` | Parser, compliance |
| `API_RATE_LIMIT_PER_HOUR` | `100` | Discovery API |
| `CRAWL_INTERVAL_HOURS` | `6` | Spider schedule |

---

## COMMON ISSUES & FIXES

### API not responding (curl returns 000)
1. Check if process exists: `ps aux | grep "discovery:app"`
2. If exists but not responding: `kill -9 <PID>` — LaunchAgent auto-restarts
3. Check error log: `tail -20 ~/agentindex/logs/api_error.log`
4. Most common cause: PostgreSQL deadlock (see below)

### PostgreSQL deadlock / hung queries
1. Diagnose: 
```bash
PSQL=/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql
$PSQL -d agentindex -c "SELECT pid, state, wait_event, now()-query_start as dur, left(query,60) FROM pg_stat_activity WHERE datname='agentindex' AND state != 'idle' ORDER BY query_start LIMIT 10;"
```
2. Kill offenders:
```bash
$PSQL -d agentindex -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='agentindex' AND state != 'idle' AND query_start < now() - interval '1 hour' AND pid != pg_backend_pid();"
```

### Before any DDL on agents table
```bash
# ALWAYS set timeout first
$PSQL -d agentindex -c "SET statement_timeout = '60s'; ALTER TABLE agents ADD COLUMN xyz ...;"
```

### Parser stuck
- Parser process shows state `T` (suspended) → restart:
```bash
launchctl kickstart -k gui/$(id -u)/com.agentindex.parser
```

### Dashboard slow
- `/admin/dashboard` takes 5-6 seconds — this is normal (full scan on analytics.db)
- If it times out: PostgreSQL is likely locked, fix that first

---

## DEVELOPMENT WORKFLOW

### Night/Day Split Model
- **Night pass:** Claude works autonomously producing code/docs that don't need server access
- **Day pass:** Anders active, validates against live data, deploys

### Adding new routes to the API
1. Create the file in the appropriate directory
2. In `discovery.py`, add import + `app.include_router()` or `mount_*()` after existing mounts (~line 556-581)
3. Restart API: `kill -9 <PID>` (auto-restarts via LaunchAgent)
4. Test: `curl -s http://localhost:8000/your/new/route`

### Testing locally vs production
- Local: `curl http://localhost:8000/...`
- Production: `curl https://nerq.ai/...` (via Cloudflare tunnel)
- Same backend — if localhost works, production works

---

*This file lives at: `~/agentindex/SYSTEM_ARCHITECTURE.md`*
*Update this file whenever system architecture changes.*
*Every new Claude chat session must read this file first.*

---

## PostgreSQL Safety Settings (added 2026-03-01)

These database-level settings prevent deadlocks and connection leaks:
```
idle_in_transaction_session_timeout = 300s  (kills forgotten transactions after 5 min)
statement_timeout = 120s                     (no query runs longer than 2 min)
```

If you need to run a long DDL (e.g. ALTER TABLE, CREATE INDEX CONCURRENTLY):
```bash
PSQL=/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql
$PSQL -d agentindex -c "SET statement_timeout = '30min'; CREATE INDEX CONCURRENTLY ..."
```
This overrides only for that session, not globally.
