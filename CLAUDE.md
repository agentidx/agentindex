# CLAUDE.md -- Orientation for Claude sessions working on Nerq/ZARQ

**Read this file first.** It is the map to everything else.

---

## The critical fact you must know before touching anything

Nerq is operated 24/7 by an autonomous AI agent named **Buzz**, running inside openclaw (`~/.openclaw/`). Buzz was configured by a previous Claude instance. The system has three participants:

1. **Anders Nilsson** -- strategic decisions
2. **Buzz** -- 24/7 operations, health monitoring, self-healing
3. **Claude** (you) -- advisory, building, fixing

When things happen in the system that neither you nor Anders did, it is probably Buzz. Do not assume you know what Buzz is doing without reading its config.

**Required reading before operational work:** `docs/buzz-context.md`

---

## What is this system?

- **ZARQ** (zarq.ai) is a crypto risk intelligence platform -- "Moody's for crypto". Trust Score, Distance-to-Default, crash probability.
- **Nerq** (nerq.ai) is an AI asset search engine indexing 5M+ AI assets (204K agents & tools, 4.7M models & datasets) with Trust Scores.
- Both run on the same FastAPI backend on one Mac Studio M1 Ultra (64 GB RAM).

---

## Critical paths

- Main app: `~/agentindex/agentindex/api/discovery.py` (mounts as `agentindex.api.discovery:app` on port 8000)
- SQLite DB (analytics): `~/agentindex/logs/analytics.db` (8.77 GB as of 2026-04-09, growing)
- SQLite DB (ratings/pipeline): `~/agentindex/agentindex/crypto/crypto_trust.db` (379 MB)
- SQLite DB (SEO): `~/agentindex/data/crypto_trust.db` (20 MB)
- Templates: `~/agentindex/agentindex/crypto/templates/`
- LaunchAgent: `~/Library/LaunchAgents/com.nerq.api.plist`
- Healthcheck: `~/agentindex/system_healthcheck.py`
- Autoheal: `~/agentindex/system_autoheal.py` (invocation path unclear -- may be called by Buzz, not cron)
- Redis: `/opt/homebrew/bin/redis-cli` **(full path required)**
- Postgres: `/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql -U anstudio -d agentindex`
- Cloudflare Tunnel ID: `a17d8bfb-9596-4700-848a-df481dc171a4` **(ghost -- scheduled for deletion)**

---

## Key conventions -- READ THESE

1. **All shell commands MUST be wrapped in heredoc:** `bash << 'EOF' ... EOF`. Prefer Python for anything involving markdown, multi-line text, or special characters -- heredocs are fragile with those. Use base64 for anything with embedded markdown or quotes sent through a layer of bash from a zsh shell.
2. **LaunchAgents:** Use `launchctl stop/start com.nerq.api` -- NEVER `pkill` (auto-restarts). For a full restart use `kill -9` + `launchctl kickstart` (avoids race conditions in stop+start).
3. **PostgreSQL pool:** max pool_size=5, max_overflow=5
4. **ZARQ design:** light theme, DM Serif Display, JetBrains Mono, DM Sans, `--warm: #c2956b`
5. **Welcome all traffic.** Do not propose blocking or rate-limiting crawlers without explicit user reconsideration. The default answer is always "let them in."
6. **Expansion-first.** Robustness is the foundation, but the goal is 50 languages and 100 verticals before monetization. See `docs/adr/ADR-002-expansion-first-strategy.md`.
7. **Monetization trigger:** 150K human visits/day sustained for 7 consecutive days. Do not propose monetization changes before then.


---

## Database tables (important -- schema guide)

Column drift between code and schema has caused multiple production incidents. Known safe patterns:

- `nerq_risk_signals` (205 tokens). Columns: `token_id, risk_level, structural_weakness, trust_score, ndd_current, sig6_structure, trust_p3`. **Does NOT have** `token_symbol`, `crash_probability`, or `chain` -- requires joins to get those.
- `entity_lookup` (Postgres, ~5M rows, 3 GB). **Does NOT have** `language`, `trust_calculated_at`, or `tags`. Use `LEFT JOIN agents a ON a.id = el.id` for those columns.
- `agents` (Postgres, ~4.98M rows, 17 GB). Has `language`, `tags`, primary key `id`.
- `crash_model_v3_predictions`
- `crypto_rating_daily`
- `defi_protocol_tokens`

Known broken schema references (as of 2026-04-09, not yet fixed):

- `stale_score_detector` queries `entity_lookup.trust_calculated_at` -- fails daily, needs LEFT JOIN agents
- `compatibility_matrix` queries SQLite `npm_weekly` column -- doesn't exist, fails weekly
- `yield_crawler_status` table missing from healthcheck.db -- warns in autoheal every 3 min

---

## Repository orientation

Key files, indented to show structure:

    ~/agentindex/
        CLAUDE.md                                  (you are here)
        docs/
            buzz-context.md                        (READ FIRST if touching operations)
            health-audit-2026-04-09.md             (Day 34 incident audit, messy but useful)
            adr/
                ADR-002-expansion-first-strategy.md    (current architecture strategy)
            strategy/
                phase-0-1-implementation-plan.md                (what we are doing now)
                nerq-vertical-expansion-master-plan-v3.md       (14 to 100 verticals)
                nerq-traffic-sprint-v2-complete.md              (traffic acquisition)
                nerq-revenue-sprint-safe.md                     (monetization trigger)
                nerq-ai-citation-optimization-sprint.md         (AI citation optimization)
                nerq-ai-onboarding-sprint.md                    (AI-to-human funnel)
                nerq-personalization-sprint.md                  (personalized trust scores)
                nerq-dimension-expansion-sprint.md              (10 dimensions framework)
                nerq-future-dimensions-and-click-psychology.md  (CTR optimization)
        agentindex/                                (main Python package)
        system_autoheal.py                         (may or may not be called by Buzz)
        scripts/

## Strategic context

The agentic economy is accelerating faster than expected. Key signals:

- **Stripe Tempo:** Stripe launched agent-to-agent payments. Agents need trust scores before transacting.
- **$110T stablecoin settlement:** Stablecoin settlement volume hit $110T annualized. Autonomous agents will drive the next order of magnitude.
- **Sui a402 monitoring:** Sui's HTTP 402 payment protocol creates machine-native payment rails. ZARQ's tier system (open->signal->degraded->402) mirrors this pattern.
- **On-chain oracle (long-term):** Publishing ZARQ Trust Scores on-chain as a Chainlink-style oracle is a viable exit path. Protocols could gate DeFi actions on ZARQ ratings.
- **Positioning:** ZARQ is the trust layer for the machine economy. Every autonomous financial decision -- swaps, lending, portfolio rebalancing -- needs a trust anchor. ZARQ provides that anchor: independent, quantitative, hash-chained, machine-readable risk intelligence.

---

## Known broken things (as of 2026-04-09)

1. **OPERATIONSPLAN.md is stale** (dated Feb 2026) -- Buzz operates on a 6-8 weeks outdated plan. Needs rewrite.
2. **Discord integration broken** -- Anders not receiving Buzz reports for 24+ hours.
3. **Schema drift:** see "Database tables" section above.
4. **Newsletter job** hardcoded to `claude-sonnet-4-20250514` (model not allowed, failing 2+ weeks).
5. **Memory pressure:** Mac Studio runs at 95% RAM constantly, 75% swap used.
6. **Pending sudo fixes:** `scripts/apply_system_limits.sh`, auto-login anstudio, UPS purchase. Sudo password unknown -- needs recovery.

---

## Task system

- New tasks: `~/agentindex/tasks/queue/`
- Read task file, implement, test, commit
- Move task to `done/` when complete, `failed/` if it fails
- Write results in task file "## Result" section before moving

---

## What you must NOT do

- Change database schema without explicit instruction
- Restart LaunchAgents with `pkill`
- Change Cloudflare configuration without explicit instruction
- Delete or modify backup files
- Modify nerq_risk_signals table directly
- Associate Nerq or ZARQ with any legal entity name without explicit user confirmation
- Propose 17-week migrations (ADR-001 is deferred, ADR-002 is the active strategy)
- Unload LaunchAgents assuming they stay unloaded -- Buzz may re-load them
- Make claims about Buzz's behavior without reading `~/.openclaw/cron/jobs.json` and `~/.openclaw/workspace/OPERATIONSPLAN.md` first

---

## What you can expect from Anders

- Strategic direction and final approval on architectural changes
- Fast decisions when given clear options and tradeoffs
- Pushback when you over-engineer or lose sight of expansion goals
- Swedish casually, English technically -- both are fine
- He is not a coder. Do not expect him to debug code for you. Do it yourself or explain clearly what you need verified.

---

## If you are Claude Code in the terminal

You also have access to `claude-code` directly on this server. Anders can invoke you that way too. When working in that mode, you have full shell access and can operate directly on files. The same rules above apply.

---

*This file should be updated whenever the operational context changes significantly. Last updated: 2026-04-09.*
