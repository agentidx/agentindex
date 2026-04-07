# ZARQ/Nerq Operations Log

## 2026-03-07 (Evening)

- S0 Track A: Fixed 5 crash-looping LaunchAgents (ThrottleInterval, OOM fix, port delay)
- S0 Track B: ZARQ healthchecks + circuit breakers (CoinGecko, DeFiLlama)
- S0 Track C: Service boundary documentation (78 ZARQ routes, 53 Nerq routes)
- S0 Track D: Pytest suite created (25 tests, 10 endpoints)
- S0 Track E: Observability middleware + /internal/metrics
- S1: /v1/check/{token} endpoint live (zero auth, zero friction)
- S1: Paper trading track record started (genesis hash, 75 warnings, cron-ready)
- S1: Nerq→ZARQ cross-pollination (Trust Score on 5M+ AI asset pages, llms.txt updated)
- S1: MCP server updated (11 tools, mcp.zarq.ai verified live)
- S1: /v1/crypto/signals bug fixed (3 endpoints repaired — wrong column + wrong table)
- S2: Tier/rate-limit logic (Redis-backed, 4 tiers: open→signal→degraded→blocked/402)
- S2: First Save Simulator (HTML page + API endpoint, top 5 OOS crashes)
- S3: LangChain wrapper, ElizaOS plugin, Solana Agent Kit integration
- S4: Crash Shield (50 verified saves, webhook subscriptions)
- S4: Viral save-cards (shareable HTML, OpenGraph meta)
- S4: Forta API integration (GraphQL client + circuit breaker)
- Strategic: CLAUDE.md updated, llms.txt repositioned, strategic-options.md created

## 2026-03-08 (Morning)

- ZARQ Operations Dashboard built (6 sections, live at /zarq/dashboard)
- Urgent fixes: Latency crisis resolved
  - /v1/health: 4,846ms → 3ms (added missing cache check)
  - /v1/check/bitcoin: 824ms → 14ms (CTE replaces correlated subquery + new index)
  - /v1/stats: 10,631ms → 25ms (SQL-side protocol aggregation)
- Data pipeline bug fixed (crypto_daily_master.py line 259 NameError since Feb 28)
- Risk signals refreshed to 2026-03-08 (was stuck at 2026-02-28)
- SQLite indexes added: idx_cmv3_token_date, idx_nrs_token_date
- Cron activated: daily track record at 01:00
- Task files cleaned up (12 moved queue→done)
- Traffic analysis completed (docs/traffic-analysis-2026-03-08.md)
- User Intelligence section added to dashboard (user types, AI bots, token checks, recurring integrations)
- Finding: 90.4% traffic is Meta bot. Organic ~1,067 req/day. Zero agent framework traffic yet. Yield endpoints = surprise demand signal.

## 2026-03-08 (Afternoon)

- Operations log created (this file)
- LangChain package prepared for PyPI (zarq-langchain v0.1.0, pyproject.toml, __init__.py)
- ElizaOS plugin prepared for npm (@zarq/elizaos-plugin v0.1.0, package.json, tsconfig.json)
- Manual registration guide created (Smithery, Glama, ERC-8004, Discord templates)
- /zarq/docs page created (public API documentation, ZARQ design, integration examples)
- zarq-langchain v0.1.0 published to PyPI: https://pypi.org/project/zarq-langchain/0.1.0/
- @zarq/elizaos-plugin v0.1.0 published to npm: https://www.npmjs.com/package/@zarq/elizaos-plugin
- Glama MCP registration submitted for review
- Smithery registration attempted — blocked by false OAuth requirement. Needs Streamable HTTP transport. PARKED.
- /zarq/docs verified live (server restart was needed)
- MCP SSE endpoint verified working at mcp.zarq.ai/sse
- LangChain Forum post published (Talking Shop category)
- X/Twitter post published announcing zarq-langchain + API
- ElizaOS Discord joined but posting blocked (insufficient role/permissions). PARKED.
- r/algotrading post blocked (insufficient karma). PARKED.
- Streamable HTTP transport verified working at mcp.zarq.ai/mcp (was already implemented, just needed testing)
- Full external endpoint verification — all 9 endpoints returning 200 via Cloudflare tunnel
- ZARQ MCP server registered and PUBLIC on Smithery: https://smithery.ai/server/agentidx/zarq-risk (11 tools, listed)
- Streamable HTTP transport added at /mcp alongside SSE at /sse
- .well-known/mcp/server-card.json served with full tool schemas
- @zarq/elizaos-plugin v0.1.0 published to npm
- All 9 key endpoints verified 200 via Cloudflare Tunnel

## 2026-03-08 (Evening)

- Hacker News Show HN posted: "Show HN: ZARQ – Free crypto risk API for AI agents (205 tokens)"
- Dev.to blog post published: "How to add pre-trade risk scoring to your LangChain crypto agent in 2 lines"
- awesome-mcp-servers PR #2922 submitted (pending review)
- awesome-langchain PR submitted (pending review)
- Adoption Triggers dashboard card added — gold border, targets table, auto-verdicts
- Adoption Triggers card fixed: strict bot/scanner filtering (Raw 180 → Filtered 26, Excluded IPs 2 → 18)
- Verdict boxes updated: show grey "Collecting data" until evaluation dates (Week 1: 2026-03-14, Week 2: 2026-03-21)
- Distribution channels doc created (docs/distribution-channels.md) — 8 channels with ready-to-submit content
- GitHub track-record repo set up (kbanilsson-pixel/track-record) with push script + README
- Server crash investigated: PostgreSQL pool exhaustion in seo_pages.py (QueuePool 5+5 reached). Autoheal recovered.
- PostgreSQL pool increased: pool_size 5→10, max_overflow 5→10 (20 max connections per worker)
- /zarq/doc → /zarq/docs 301 redirect added (HN link fix)
- P50 latency fixed: 2558ms → 22.8ms (10min window, /v1/ only, reltuples for health)
- PostgreSQL crash: pool exhaustion → PG restarted, pool increased
- Buzz upgraded with LLM intelligence (qwen2.5:7b via Ollama) — auto-diagnoses and heals
- **KYA — Know Your Agent** built: /v1/agent/kya/{name}, /kya page, MCP tool (204K agents & tools)
- **The ZARQ Signal** built: /v1/signal/feed, /v1/signal/feed/history, /signal page (205 tokens, auto-refresh)
- Signal subscribe endpoint: POST /v1/signal/subscribe (stores registrations)
- MCP server updated: 13 tools (was 11) — added kya_check_agent + get_signal_feed
- /zarq/docs updated with KYA + Signal sections
- llms.txt updated with KYA + Signal endpoints
- Tests: 115 passed (was 111)
- Cross-navigation added between all product pages (hub, KYA, Signal, Save Simulator, Docs)
- Landing page alerts fixed: query rewired from empty nerq_risk_signals columns to crash_model_v3_predictions
  - 1st Target Hit: 0% → **88%** (61/69 mature alerts declined ≥30%)
  - 2nd Target Hit: 0% → **80%** (55/69 mature alerts declined ≥50%)
  - Dates and symbols now populated (was blank)
- Landing page navigation added: Signal, KYA in nav bar + 4-card Product Suite grid + footer links
- P95 latency: 7215ms → **300ms**
  - Root cause 1: `/agent/` pages doing seq scan on 5M+ rows (no index on `domains`)
  - Root cause 2: SQLite timestamp comparison bug (`datetime()` vs ISO format with `T` and `+00:00`)
  - Fix: GIN index on `domains`, `@>` operator, 10min HTML cache, 10s statement timeout, ISO cutoff in Python
  - Agent pages: 217s → 1.8s cold / **10ms cached**
  - Signal feed: 3.8s → 34ms cold / 19ms cached
- Buzz upgraded with qwen2.5:7b LLM diagnostics (auto-diagnoses PG pool exhaustion, restarts services)
- Dev.to article #2 published (KYA + Signal)
- HN comment updated with KYA + Signal
- X/Twitter: Signal feed announced
- Agent Insurance Protocol analysis document created

### Distribution Summary (all channels 2026-03-08)

PyPI (zarq-langchain), npm (@zarq/elizaos-plugin), Smithery (PUBLIC), Glama (pending review), awesome-mcp-servers PR #2922, awesome-langchain PR, Hacker News Show HN, Dev.to ×2, LangChain Forum, X/Twitter ×3, GitHub track-record

### Next Check

**2026-03-15** — Week 1 evaluation on Adoption Triggers dashboard

## TODO (Manual — Anders)

- [x] Publish zarq-langchain on PyPI
- [x] Publish @zarq/elizaos-plugin on npm
- [x] Glama MCP registration (submitted, awaiting review)
- [x] LangChain community post
- [x] X/Twitter announcement
- [x] Add Streamable HTTP transport to MCP server (was already implemented)
- [x] Verify zarq.ai/demo/save-simulator works externally (200, 86ms)
- [x] Smithery MCP registration (PUBLIC, 11 tools)
- [ ] ElizaOS Discord post (need role/permissions)
- [ ] ERC-8004 registration (requires wallet + gas)
- [ ] Follow up Glama review (3-5 days)
- [ ] r/algotrading (need karma)
- [ ] Add favicon.ico (28 unnecessary 404s/day)
- [ ] Publish llms.txt to /.well-known/llms.txt
- [x] Hacker News Show HN posted
- [x] Dev.to blog post published
- [x] awesome-mcp-servers PR submitted (#2922)
- [x] awesome-langchain PR submitted
- [x] Adoption Triggers dashboard card (with strict filtering)
- [x] Track-record GitHub repo set up
- [x] PostgreSQL pool fix (5→10)
- [x] /zarq/doc redirect fix

## Metrics Snapshot (2026-03-08)

| Metric | Value |
|--------|-------|
| Tokens rated | 205 |
| AI assets indexed | 5M+ (204K agents & tools, 4.7M models & datasets) |
| Crash Shield saves | 50 verified |
| API requests (24h) | ~28K (90% Meta bot) |
| Organic requests (24h) | ~1,067 |
| Unique IPs (24h) | ~390 |
| Real /v1/check tokens | 3 (bitcoin, ethereum, solana) |
| AI bots visiting | Claude (20), ChatGPT (12), Perplexity (8) |
| Agent framework integrations | 0 detected |
| Tests passing | 115/115 |
| MCP tools | 13 |
| P50 latency | ~255ms (10min /v1/) |
| P95 latency | ~300ms |
| Products live | Ratings, Alerts, Signal, KYA, Save Simulator, Paper Trading, Risk Scanner, Contagion |
