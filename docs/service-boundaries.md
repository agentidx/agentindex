# ZARQ / Nerq Service Boundaries

Sprint 0, Track C — Separation preparation document.
Generated 2026-03-07. This is the authoritative map for splitting the monolith.

---

## 1. Route Classification

Every route registered in discovery.py, classified by product.

### ZARQ (crypto risk intelligence — zarq.ai)

#### API endpoints (prefix: `/v1/crypto/`)

Source: `crypto_api_v2.py` (router_v1, prefix `/v1/crypto/`)

| Route | Method | Description |
|-------|--------|-------------|
| `/v1/crypto/rating/{token_id}` | GET | Trust Score for a token |
| `/v1/crypto/ndd/{token_id}` | GET | Distance-to-Default distress score |
| `/v1/crypto/ratings` | GET | All ratings (paginated) |
| `/v1/crypto/signals` | GET | Active risk signals |
| `/v1/crypto/signals/history` | GET | Historical risk signals |
| `/v1/crypto/compare/{token1}/{token2}` | GET | Head-to-head token comparison |
| `/v1/crypto/distress-watch` | GET | Tokens near distress threshold |
| `/v1/crypto/safety/{token_address}` | GET | Pre-trade safety check |
| `/v1/crypto/risk-level/{token_id}` | GET | Risk classification |
| `/v1/crypto/risk-levels` | GET | All risk levels |
| `/v1/crypto/portfolio/pairs` | GET | Pairs backtest data |
| `/v1/crypto/portfolio/adaptive` | GET | Adaptive portfolio |
| `/v1/crypto/paper-trading/nav/{portfolio}` | GET | Paper trading NAV |
| `/v1/crypto/paper-trading/positions/{portfolio}` | GET | Paper trading positions |
| `/v1/crypto/paper-trading/signals` | GET | Paper trading signals |
| `/v1/crypto/paper-trading/regime` | GET | Regime detector state |
| `/v1/crypto/paper-trading/audit` | GET | Paper trading audit log |

Source: `crypto_api_v3.py` (router_v3, prefix `/v1/crypto/`)

| Route | Method | Description |
|-------|--------|-------------|
| `/v1/crypto/contagion/scores/all` | GET | All contagion scores |
| `/v1/crypto/contagion/scenarios` | GET | Available contagion scenarios |
| `/v1/crypto/contagion/network` | GET | Contagion network graph |
| `/v1/crypto/contagion/case-studies` | GET | Historical case studies |
| `/v1/crypto/contagion/scenario/{scenario_id}` | GET | Specific scenario |
| `/v1/crypto/contagion/{token_id}` | GET | Token contagion data |
| `/v1/crypto/stresstest` | POST | Run portfolio stresstest |
| `/v1/crypto/stresstest/scenarios` | GET | Stresstest scenarios |
| `/v1/crypto/stresstest/portfolios` | GET | Predefined portfolios |
| `/v1/crypto/transition-matrix/{period}` | GET | Rating transitions |
| `/v1/crypto/transition/{token_id}` | GET | Token transition history |
| `/v1/crypto/exit-score/{token_id}` | GET | Exit timing score |
| `/v1/crypto/crash-thresholds/{token_id}` | GET | Crash threshold levels |
| `/v1/crypto/cascade/simulate` | GET | Cascade simulation |
| `/v1/crypto/cascade/graph` | GET | Cascade graph data |
| `/v1/crypto/cascade/hotspots` | GET | Cascade hotspot tokens |
| `/v1/crypto/cascade/stats` | GET | Cascade statistics |
| `/v1/crypto/portfolio/crash-shield` | POST | Crash shield config |
| `/v1/crypto/portfolio/crash-shield/webhooks` | GET | Crash shield webhooks |
| `/v1/crypto/portfolio/crash-shield/prevented` | GET | Prevented losses |
| `/v1/crypto/portfolio/analyze` | POST | Portfolio analysis |

Source: `zarq_batch_api.py` (router_batch, prefix `/v1/crypto/`)

| Route | Method | Description |
|-------|--------|-------------|
| `/v1/crypto/ratings/batch` | POST | Batch Trust Score lookup |
| `/v1/crypto/ndd/batch` | POST | Batch NDD lookup |
| `/v1/crypto/safety/batch` | POST | Batch safety check |

Source: `zarq_websocket_webhooks.py` (router_ws)

| Route | Method | Description |
|-------|--------|-------------|
| `/v1/stream/signals` | WebSocket | Live risk signal stream |
| `/v1/stream/yield-traps` | WebSocket | Live yield trap alerts |
| `/v1/stream/agents` | WebSocket | Live agent activity |
| `/v1/stream/status` | GET | WebSocket stream status |
| `/v1/webhooks/register` | POST | Register webhook |
| `/v1/webhooks` | GET | List webhooks |
| `/v1/webhooks/{webhook_id}` | DELETE | Delete webhook |
| `/v1/webhooks/{webhook_id}/test` | POST | Test webhook |
| `/v1/webhooks/dlq` | GET | Dead letter queue |

#### SEO / HTML pages (ZARQ)

| Route | Source | Description |
|-------|--------|-------------|
| `/crypto` | crypto_seo_pages.py | Crypto landing page |
| `/crypto/token/{token_id}` | crypto_seo_pages.py | Token detail page |
| `/crypto/exchange/{exchange_id}` | crypto_seo_pages.py | Exchange detail |
| `/crypto/defi/{protocol_id}` | crypto_seo_pages.py | DeFi protocol detail |
| `/crypto/predictions` | crypto_seo_pages.py | Crash predictions |
| `/crypto/alerts` | crypto_seo_pages.py | Active alerts page |
| `/crypto/signals` | crypto_early_warning.py | Early warning page |
| `/crypto/signals/rss` | crypto_early_warning.py | RSS feed |
| `/crypto/signals/atom` | crypto_early_warning.py | Atom feed |
| `/best/crypto-tokens` | crypto_seo_pages.py | Best tokens ranking |
| `/best/crypto-exchanges` | crypto_seo_pages.py | Best exchanges |
| `/best/crypto-defi` | crypto_seo_pages.py | Best DeFi protocols |
| `/paper-trading` | crypto_seo_pages.py | Paper trading dashboard |
| `/track-record` | crypto_seo_pages.py | Track record page |
| `/methodology` | crypto_seo_pages.py | ZARQ methodology |
| `/whitepaper` | crypto_seo_pages.py | ZARQ whitepaper |
| `/recovery` | crypto_seo_pages.py | Recovery analysis |
| `/risk-scanner` | zarq_risk_pages.py | Risk scanner tool |
| `/contagion` | zarq_risk_pages.py | Contagion map |
| `/cascade-risk` | zarq_cascade_page.py | Cascade risk page |
| `/cascade` | zarq_cascade_page.py | Redirect |
| `/yield-risk` | zarq_yield_page.py | Yield risk page |
| `/yield` | zarq_yield_page.py | Redirect |
| `/yield-traps` | zarq_yield_page.py | Redirect |
| `/agent-intelligence` | crypto_seo_pages.py | Agent intelligence page |
| `/compare/{slug}` | crypto_seo_pages.py | Token comparison |
| `/docs` | crypto_seo_pages.py | API documentation |
| `/api/v1/crypto/trust-score/{entity_type}/{entity_id}` | crypto_seo_pages.py | Inline trust score API |
| `/data/crypto-trust-scores.jsonl.gz` | crypto_seo_pages.py | Bulk data export |
| `/data/crypto-trust-summary.json` | crypto_seo_pages.py | Summary export |
| `/sitemap-crypto.xml` | crypto_seo_pages.py | Crypto sitemap |
| `/sitemap-compare.xml` | crypto_seo_pages.py | Comparison sitemap |
| `/sitemap-pages.xml` | crypto_seo_pages.py | Pages sitemap |

#### MCP endpoints (ZARQ)

| Route | Method | Description |
|-------|--------|-------------|
| `/mcp/sse` | GET | MCP SSE transport |
| `/mcp/messages` | POST | MCP message handler |

#### Machine discovery (ZARQ domain, but serves both)

| Route | Source | Notes |
|-------|--------|-------|
| `/robots.txt` | zarq_machine_discovery.py | Overridden by seo_pages.py for nerq |
| `/llms.txt` | zarq_machine_discovery.py | ZARQ-specific |
| `/llms-full.txt` | zarq_machine_discovery.py | ZARQ-specific |
| `/apis.json` | zarq_machine_discovery.py | API catalog |
| `/.well-known/ai-plugin.json` | zarq_machine_discovery.py | ChatGPT plugin manifest |
| `/sitemap.xml` | zarq_machine_discovery.py | Master sitemap |

---

### Nerq (AI agent search engine — nerq.ai)

#### API endpoints

| Route | Method | Source | Description |
|-------|--------|--------|-------------|
| `/v1/discover` | POST | discovery.py | Core agent discovery |
| `/v1/agent/{agent_id}` | GET | discovery.py | Agent detail |
| `/v1/stats` | GET | discovery.py | Index statistics |
| `/v1/register` | POST | discovery.py | API key registration |
| `/v1/mcp/discover` | POST | discovery.py | MCP-format discovery |
| `/v1/semantic/status` | GET | discovery.py | Semantic index status |
| `/.well-known/agent-card.json` | GET | discovery.py | A2A agent card |
| `/.well-known/agent.json` | GET | discovery.py | A2A agent card (alt) |
| `/a2a` | POST | discovery.py | A2A JSON-RPC endpoint |

#### Agent Intelligence endpoints (prefix: `/v1/agents/`)

Source: `crypto_agents_api.py` (router_agents, prefix `/v1/agents/`)
Note: Despite living in `crypto/`, these are ZARQ+Nerq crossover — crypto agents.

| Route | Method | Description |
|-------|--------|-------------|
| `/v1/agents/crypto/{agent_id}` | GET | Crypto agent profile |
| `/v1/agents/in/{entity_type}/{entity_id}` | GET | Agents in entity |
| `/v1/agents/new` | GET | Newly discovered agents |
| `/v1/agents/relations/{agent_id}` | GET | Agent relationships |
| `/v1/agents/graph/{entity_type}/{entity_id}` | GET | Agent graph |
| `/v1/agents/activity/{entity_type}/{entity_id}` | GET | Agent activity |
| `/v1/agents/activity-overview` | GET | Activity overview |
| `/v1/agents/wallet/{address}` | GET | Wallet agent analysis |
| `/v1/agents/ai-identified` | GET | AI-identified agents |
| `/v1/agents/report/latest` | GET | Weekly report |
| `/v1/agents/risk-exposure` | GET | Agent risk exposure |
| `/v1/agents/structural-collapse` | GET | Structural collapse |
| `/v1/agents/chain-concentration-risk` | GET | Chain concentration |
| `/v1/agents/exodus-snapshot` | GET | Exodus snapshot |

#### Compliance endpoints (prefix: `/compliance/`)

Source: `compliance/compliance_api.py`, `compliance/badge_api.py`, `api/multi_jurisdiction.py`

| Route | Method | Description |
|-------|--------|-------------|
| `/compliance/check` | POST | Run compliance check |
| `/compliance/check/{assessment_id}` | GET | Assessment result |
| `/compliance/agent/{agent_id}` | GET | Agent compliance |
| `/compliance/deadlines` | GET | Regulatory deadlines |
| `/compliance/stats` | GET | Compliance statistics |
| `/compliance/badge/{risk_class}` | GET | SVG badge |
| `/compliance/badge/agent/{agent_id}` | GET | Agent badge |
| `/compliance/badge/multi/{risk_class}/{count}` | GET | Multi badge |
| `/compliance/badge/trust/{agent_id}` | GET | Trust badge |
| `/compliance/badge/trust-grade/{grade}` | GET | Grade badge |
| `/compliance/multi-check` | POST | Multi-jurisdiction check |
| `/compliance/jurisdictions` | GET | All jurisdictions |
| `/compliance/jurisdictions/{jurisdiction_id}` | GET | Jurisdiction detail |
| `/compliance/changelog` | GET | Regulatory changelog |

#### SEO / HTML pages (Nerq)

| Route | Source | Description |
|-------|--------|-------------|
| `/` | discovery.py | Hub landing (nerq.ai) |
| `/discover` | discovery.py | Agent search page |
| `/comply` | discovery.py | EU compliance page |
| `/stats` | discovery.py | Stats dashboard |
| `/blog` | discovery.py | Blog index |
| `/agent/{agent_id}` | seo_pages.py | Agent detail page |
| `/best` | seo_pages.py | Best agents overview |
| `/best/{category}` | seo_pages.py | Best agents by category |
| `/mcp-servers` | comparison_pages.py | MCP server directory |
| `/best-mcp-servers-for-{category}` | comparison_pages.py | MCP by category |
| `/vs` | vs_pages.py | Agent comparison hub |
| `/vs/{id_a}/{id_b}` | vs_pages.py | Head-to-head comparison |
| `/robots.txt` | seo_pages.py | Robots (nerq domain) |
| `/llms.txt` | seo_pages.py | LLM discovery |
| `/llms-full.txt` | seo_pages.py | Full LLM data |
| `/data/trust-scores.jsonl.gz` | seo_pages.py | Agent trust data |
| `/data/trust-summary.json` | seo_pages.py | Summary data |
| `/api/v1/trust-score/{agent_id}` | seo_pages.py | Agent trust API |
| `/sitemap-index.xml` | seo_pages.py | Sitemap index |
| `/sitemap-static.xml` | seo_pages.py | Static sitemap |
| `/sitemap-agents-{chunk}.xml` | seo_pages.py | Agent sitemaps |
| `/sitemap-comparisons.xml` | comparison_pages.py | Comparison sitemap |
| `/sitemap-vs.xml` | vs_pages.py | VS sitemap |

---

### Shared

| Route | Method | Source | Description |
|-------|--------|--------|-------------|
| `/v1/health` | GET/HEAD | discovery.py | Healthcheck (both products) |
| `/admin/dashboard` | GET | discovery.py | Analytics dashboard |
| `/internal/metrics` | GET | observability.py | Observability metrics |

---

## 2. Database Tables

### PostgreSQL (database: `agentindex`, public schema)

Used by: **Nerq** (agent discovery) + **Shared compliance**

| Table | Product | Description |
|-------|---------|-------------|
| `agents` | Nerq | 4.9M agent records (core table) |
| `discovery_log` | Nerq | Discovery query log |
| `system_status` | Shared | System health status |
| `crawl_jobs` | Nerq | Spider crawl tracking |
| `trust_score_history` | Nerq | Agent trust score history |
| `outreach_issues` | Nerq | GitHub outreach tracking |
| `compliance_assessments` | Nerq | EU AI Act assessments |
| `compliance_monitors` | Nerq | Compliance monitors |
| `compliance_subscribers` | Nerq | Compliance subscribers |
| `jurisdiction_registry` | Nerq | Regulatory jurisdictions |
| `regulatory_rules` | Nerq | Regulatory rules |
| `agent_jurisdiction_status` | Nerq | Agent compliance per jurisdiction |
| `checker_usage` | Nerq | Compliance checker usage |

No `zarq.*` schema exists. All tables are in `public`.

### SQLite: `agentindex/crypto/crypto_trust.db` (379MB)

Used by: **ZARQ** (crypto risk intelligence)

| Table | Description |
|-------|-------------|
| `crypto_rating_daily` | Daily trust scores per token |
| `crypto_rating_history` | Historical rating snapshots |
| `crypto_ndd_daily` | Daily NDD distress scores |
| `crypto_ndd_history` | Historical NDD data |
| `crypto_ndd_alerts` | NDD alert events |
| `nerq_risk_signals` | Collapse/stress signals (205 tokens) |
| `nerq_risk_alerts` | Alert notifications |
| `crash_model_v3_predictions` | Crash probability model output |
| `crypto_price_history` | OHLCV price data |
| `crypto_pipeline_runs` | Pipeline execution log |
| `crypto_pipeline_status` | Pipeline status |
| `crypto_fetch_status` | Price fetch status |
| `defi_protocol_tokens` | DeFi protocol mapping |
| `defi_tvl_history` | TVL history (DeFiLlama) |
| `defi_yields` | Current yield data |
| `defi_yield_history` | Historical yield data |
| `defi_stablecoin_flows` | Stablecoin flow data |
| `crypto_regime_backtest` | Regime detection backtest |
| `crypto_regime_backtest_v2` | Regime detection v2 |
| `crypto_regime_summary` | Regime summaries |
| `crypto_regime_summary_v2` | Regime summaries v2 |
| `nerq_model_portfolio` | Model portfolio holdings |
| `nerq_model_portfolio_summary` | Portfolio summary |
| `nerq_portfolio_v4` | Portfolio v4 |
| `nerq_portfolio_v4_summary` | Portfolio v4 summary |
| `crypto_pairs_backtest_results` | Pairs strategy results |
| `crypto_conviction_results` | Conviction portfolio |
| `crypto_portable_alpha_backtest` | Portable alpha |
| `crypto_portable_alpha_summary` | Alpha summary |
| `crash_shield_events` | Crash shield triggers |
| `crash_shield_prevented` | Prevented losses |
| `crash_shield_webhooks` | Crash shield webhooks |
| `agent_activity_index` | Crypto agent activity |
| `agent_crypto_profile` | Crypto agent profiles |
| `agent_crypto_relations` | Agent relationships |
| `agent_protocol_snapshot` | Protocol snapshots |
| `agent_risk_exposure` | Agent risk exposure |
| `chain_concentration_risk` | Chain concentration |
| `wallet_behavior` | Wallet behavior data |

### SQLite: `agentindex/data/crypto_trust.db` (20MB)

Used by: **ZARQ** SEO pages (read-only copy for page rendering)

### SQLite: `agentindex/crypto/zarq_api_log.db`

Used by: **Shared** (observability, Sprint 0 Track E)

### SQLite: `logs/analytics.db`

Used by: **Shared** (analytics middleware)

---

## 3. Templates

### ZARQ templates (`agentindex/crypto/templates/`)

| File | Route | Description |
|------|-------|-------------|
| `zarq_landing.html` | `/` (zarq.ai) | ZARQ landing page |
| `zarq_methodology.html` | `/methodology` | Trust Score methodology |
| `zarq_whitepaper.html` | `/whitepaper` | ZARQ whitepaper |
| `zarq_track_record.html` | `/track-record` | Performance track record |
| `zarq_api_docs.html` | `/docs` | ZARQ API documentation |
| `zarq_early_warning.html` | `/crypto/signals` | Early warning page |
| `zarq_cascade_risk.html` | `/cascade-risk` | Cascade risk page |
| `zarq_recovery.html` | `/recovery` | Recovery analysis |
| `zarq_agent_intelligence.html` | `/agent-intelligence` | Agent intelligence |
| `paper_trading.html` | `/paper-trading` | Paper trading dashboard |

### Nerq templates (`static/`)

| File | Route | Description |
|------|-------|-------------|
| `hub.html` | `/` (nerq.ai) | Nerq hub landing |
| `index.html` | `/discover` | Agent search UI |
| `eu-compliance.html` | `/comply` | EU compliance checker |
| `stats.html` | `/stats` | Stats dashboard |

### Shared

| File | Route | Description |
|------|-------|-------------|
| `nerq_api_docs.html` | (unused?) | Nerq API docs template |

---

## 4. External API Dependencies

### ZARQ

| Service | Usage | API Key? |
|---------|-------|----------|
| CoinGecko | Token metadata, prices, trust scores, categories | Free tier (no key) |
| DeFiLlama | TVL, yields, stablecoin flows, protocol data | Free (no key) |
| DexScreener | DEX token discovery, price data | Free (no key) |
| Etherscan | Wallet behavior analysis, on-chain data | Yes (env var) |

### Nerq

| Service | Usage | API Key? |
|---------|-------|----------|
| GitHub API | Agent discovery, repo crawling | Yes (GITHUB_TOKEN) |
| npm Registry | Package discovery | No |
| PyPI | Package discovery | No |
| HuggingFace | Model/space discovery | No |
| Docker Hub | Container discovery | No |

### Shared

| Service | Usage | Notes |
|---------|-------|-------|
| Cloudflare Tunnel | Reverse proxy (both domains) | Tunnel ID in CLAUDE.md |
| Redis | Discovery result caching | localhost:6379 |

---

## 5. Shared Infrastructure

| Component | Used by | Location |
|-----------|---------|----------|
| Redis | Nerq (discovery cache) | localhost:6379 |
| PostgreSQL | Nerq (agents, compliance) | localhost:5432, db=agentindex |
| FastAPI app | Both | Single process, port 8000 |
| Cloudflare Tunnel | Both | Tunnel a17d8bfb... |
| LaunchAgent (com.nerq.api) | Both | Single uvicorn process |
| API key system | Both | api_keys.json + env var |
| Rate limiting | Both | api_protection.py middleware |
| Observability | Both | observability.py middleware |
| Analytics | Both | analytics.py middleware |

---

## 6. Current Separation Status

### What ZarqRouter already does

`zarq_router.py` is a middleware (not a FastAPI Router) that intercepts requests based on `Host: zarq.ai`:

1. Serves `zarq_landing.html` for `zarq.ai/`
2. Passes `/v1/*` API calls through (shared namespace)
3. Passes `/crypto/*`, `/paper-trading/*`, `/admin/*` through
4. Everything else falls through to the shared app

**This is host-based routing, not code separation.** Both products share the same FastAPI app, same process, same database connections.

### What is NOT separated

- No separate router/app for ZARQ API endpoints
- No separate database connections (ZARQ SQLite reads happen inline)
- No separate middleware stacks
- No separate health checks per product
- The `/v1/crypto/*` and `/v1/agents/*` routes live in the same URL namespace
- MCP endpoints (`/mcp/sse`, `/mcp/messages`) are ZARQ but registered on the shared app

---

## 7. Migration Plan (DO NOT EXECUTE)

### Phase 1: Schema separation (PostgreSQL)

Currently no `zarq` schema exists. All 13 PostgreSQL tables are Nerq-owned.
ZARQ uses SQLite exclusively. No PostgreSQL migration needed.

### Phase 2: Router separation

1. Create `agentindex/api/zarq_api.py` as a proper FastAPI `APIRouter(prefix="/v1/crypto")`
2. Move all ZARQ router imports from discovery.py into zarq_api.py:
   - `crypto_api_v2.router_v1`
   - `crypto_api_v3.router_v3`
   - `zarq_batch_api.router_batch`
   - `zarq_websocket_webhooks.router_ws`
3. Create `agentindex/api/nerq_api.py` as a proper APIRouter
4. Move all Nerq routes from discovery.py into nerq_api.py:
   - `/v1/discover`, `/v1/agent/*`, `/v1/stats`, `/v1/register`
   - `/v1/mcp/discover`, `/v1/semantic/status`
   - A2A endpoints

### Phase 3: Page separation

1. Move all ZARQ SEO page mounts into zarq_api.py
2. Move all Nerq SEO page mounts into nerq_api.py
3. discovery.py becomes a thin shell that mounts both routers + shared middleware

### Phase 4: Process separation (future)

1. Split into two FastAPI apps with separate uvicorn processes
2. ZARQ on port 8000, Nerq on port 8001 (or reverse)
3. Cloudflare Tunnel routes by domain
4. Separate LaunchAgents per product
5. Independent health checks and scaling

### Tables to move if PostgreSQL is needed for ZARQ

Currently ZARQ is 100% SQLite. If ZARQ needs PostgreSQL:
- Create schema `zarq` in the `agentindex` database
- Migrate `crypto_trust.db` tables that need ACID/concurrent writes
- Priority candidates: `crypto_rating_daily`, `crypto_ndd_daily`, `nerq_risk_signals`
- Keep SQLite as read cache for SEO pages (fast, no connection pool needed)

### Risk assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Route conflicts during migration | Medium | Use feature flag to switch between old/new routing |
| Shared middleware breaks | Low | Middleware is product-agnostic |
| Database connection changes | Low | ZARQ uses SQLite, Nerq uses PostgreSQL — already separated |
| Static file serving | Low | Move static/ to per-product dirs |
| Rate limiting state | Low | Currently in-memory, stateless restart OK |
