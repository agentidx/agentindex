# ZARQ Surface Inventory — 2026-05-30

> **Phase 1 of the systematic ZARQ surface audit.** Read-only inventory of
> every place ZARQ exposes itself to a user, an AI consumer, or another
> system. No fixes, no recommendations beyond "this exists / this is missing
> a counterpart." Symptoms (paper trading dead, dashboards rendering wrong,
> some 404s) are explicitly NOT investigated here — that is Phase 3.

**Status:** Living artifact. Update on each phase iteration.
**Generated from:** code state at commit `e1a310f` on `main` (2026-05-30).
**Related:** `docs/adr/ADR-003a-current-db-topology.md` (DB topology context).

## Pre-flight snapshot

- `com.nerq.api`: `pid=16269 runs=2141 last_exit=1` — process up, but had
  2 restarts since the 08:53 PgBouncer repoint (4:32 ago at inventory start).
  Not the >30 min stable target, but inventory is code-level, not runtime-level.
- PgBouncer `query_wait_timeout` events since 09:00: 14 (down from ~10+/min
  during the morning outage, not yet zero).
- Endpoints serving 200 at inventory start: `localhost:8000/health` (4 ms),
  `zarq.ai/` (2.8 s — cold cache normal), `nerq.ai/health` (66 ms).
  `mcp.zarq.ai/` returns 404 (route handler missing on the SSE app — see
  section D, item 3).
- Working tree clean of modified files; commits A + B from earlier session
  already on `origin/main`.

## Topology refresher (from ADR-003a)

```
                           ┌──────────────────────────┐
                           │  Cloudflare edge tunnel  │  UUID a17d…1ad
                           │  (config.yml-defined)    │
                           └────────────┬─────────────┘
                                        │ ingress map
            ┌───────────────────┬───────┴──────────┬──────────────────┐
            ▼                   ▼                  ▼                  ▼
        :8000                :8001              :8203              :8300
   com.nerq.api          com.zarq.mcp-sse     com.agentindex.    com.agentindex.
   uvicorn / FastAPI     Starlette            dashboard          mcp-sse
   (agentindex.api.      (agentindex.crypto.  (port confirmed,   (port confirmed,
    discovery:app)        zarq_mcp_server)     plist not inspected)plist not inspected)
                                        │
                                        ▼
                               ┌──────────────────────────┐
                               │  PgBouncer 127.0.0.1:6432│
                               │  agentindex_write → Nbg  │
                               │  agentindex_read  → local│
                               │  agentindex       → local│
                               └────────────┬─────────────┘
                                            ▼
                       ┌──────────────────────┬───────────────────────┐
                Hetzner Nbg primary       Mac Studio local       (Hel: PG off)
                100.119.193.70:5432       127.0.0.1:5432
                schema: zarq + public     standby; LSN gap
```

## A) Surface overview

Numbers from systematic grep at inventory time. ZARQ-relevant means the
path or handler contains: zarq, paper, trade, crypto, signal, risk, vitality,
dashboard, track, ndd, structural, breakout, audit, yield, defi, token,
vital, rating, distress, alert.

### A.1 HTTP endpoints (FastAPI)

**505 total routes in `agentindex/`**. **93 ZARQ-relevant** (18.4%).

Top files by route count:

| File | Routes | ZARQ-touching |
|---|---|---|
| `agentindex/api/discovery.py` | 56 | mixed (nerq + zarq + agentcrawl) |
| `agentindex/demand_pages.py` | 29 | mostly nerq |
| `agentindex/crypto/crypto_seo_pages.py` | 26 | **yes — landing pages** |
| `agentindex/experiments/experiments_api.py` | 24 | partial |
| `agentindex/seo_pages.py` | 24 | partial |
| `agentindex/crypto/crypto_api_v3.py` | 22 | **yes — crypto API v3** |
| `agentindex/seo_asset_pages.py` | 16 | no |
| `agentindex/seo_dynamic.py` | 14 | no |
| `agentindex/seo_programmatic.py` | 14 | no |
| `agentindex/crypto/zarq_seo_builds.py` | 12 | **yes** |
| `agentindex/pattern_routes.py` | 12 | mixed |
| `agentindex/entity_pages.py` | 11 | mixed |
| `agentindex/crypto/crypto_api.py` | 8 | **yes — crypto API v1** |
| `agentindex/crypto/zarq_token_pages.py` | 6 | **yes — token detail pages** |
| `agentindex/crypto/zarq_compare_pages.py` | 6 | **yes — comparison pages** |
| `agentindex/crypto/zarq_machine_discovery.py` | 7 | **yes — agent-discovery API** |

Selected ZARQ endpoints (representative, not exhaustive):

| Method | Path | File:line | Purpose |
|---|---|---|---|
| GET | `/rating/{token_id}` | `crypto/crypto_api.py:62` | Token credit rating lookup |
| GET | `/ndd/{token_id}` | `crypto/crypto_api.py:114` | NDD (distance-to-default) score |
| GET | `/distress-watch` | `crypto/crypto_api.py:348` | Currently distressed tokens |
| GET | `/contagion/{token_id}` | `crypto/crypto_api_v3.py:119` | Contagion-graph risk |
| GET | `/crash-thresholds/{token_id}` | `crypto/crypto_api_v3.py:232` | Crash threshold model |
| GET | `/v1/crypto/rating/test` | `crypto/crypto_api_v3.py` | Self-test endpoint |
| GET | `/v1/crypto/ndd/test` | `crypto/crypto_api_v3.py` | Self-test endpoint |
| GET | `/v1/crypto/safety/test` | `crypto/crypto_api_v3.py` | Self-test endpoint |
| GET | `/crypto` | `crypto/crypto_seo_pages.py:1173` | Crypto landing page |
| GET | `/crypto/token/{token_id}` | `crypto/crypto_seo_pages.py:1092` | Per-token detail page |
| GET | `/tokens` | `crypto/zarq_token_pages.py:2044` | Token directory index |
| GET | `/compare/{token_a}-vs-{token_b}` | `crypto/zarq_seo_builds.py:529` | A/B token comparison |
| GET | `/cascade-risk` | `crypto/zarq_cascade_page.py:8` | Risk cascade visualization |
| GET | `/vitality` | `crypto/zarq_vitality_page.py:32` | Vitality dashboard |
| GET | `/yield` | `crypto/zarq_yield_page.py:40` | Yield risk dashboard |
| GET | `/zarq/doc` | `agentindex/api/discovery.py` | ZARQ API documentation |
| GET | `/zarq/kya` | `agentindex/api/discovery.py` | Know-Your-Asset entry |

Decorator distribution: 443 on `app`, 62 on `router`. (The high `app` count
is because `discovery.py` defines `app = FastAPI()` and many sibling
modules attach to it directly via `from agentindex.api.discovery import app`.)

### A.2 Router include-chain (`agentindex/api/discovery.py`)

**43 `include_router(...)` calls** in `discovery.py`. Grouped roughly by
domain (ZARQ-relevant marked):

| Line | Router name | Notes |
|---|---|---|
| 553 | `router_nerq` | core nerq |
| 557 | `router_weekly` | weekly |
| 559 | `router_verified` | verified-badge |
| 565 | `github_app_router` | github app |
| 1295 | `badge_router` | conditional include (inside `if`) |
| 1298 | `multi_jurisdiction_router` | conditional |
| 1352 | `router_agents` | conditional |
| 1359 | `router_check` | safety check |
| 1360 | `router_vitality` | **ZARQ** vitality |
| 1364 | `router_scan` | scan |
| 1377 | `router_save_sim` | **ZARQ** paper-trading save |
| 1381 | `router_crash_shield` | **ZARQ** crash shield |
| 1385 | `router_dashboard` | **ZARQ** dashboard |
| 1389 | `router_docs` | API docs |
| 1435 | `router_rss` | rss |
| 1439 | `router_rss_feeds` | rss feeds |
| 1456 | `router_start` | onboarding |
| 1460 | `router_kya` | **ZARQ** know-your-asset |
| 1464 | `router_nerq_docs` | docs |
| 1474 | `router_signal` | **ZARQ** signal feed |
| 1540 | `crypto_v1_router` | **ZARQ** crypto API v1 |
| 1545 | `crypto_v3_router` | **ZARQ** crypto API v3 (conditional) |
| 1653 | `router_combined_dashboard` | dashboard |
| 1657 | `router_report` | report |
| 1661 | `router_best_agents` | best agents |
| 1665 | `router_badge` | badge |
| 1669 | `router_frameworks` | frameworks |
| 1680 | `router_blog` | blog |
| 1707 | `router_preflight` | universal preflight |
| 1711 | `router_commerce` | commerce |
| 1715 | `router_dependencies` | deps |
| 1719 | `router_signals` | **ZARQ** signals (plural) |
| 1723 | `router_prediction` | **ZARQ** prediction |
| 1727 | `router_dimensions` | dims |
| 1731 | `router_rating` | **ZARQ** rating |
| 1742 | `router_dim_redirects` | redirects |
| 1750 | `router_hacked` | hacked-watch |
| 1764 | `router_docs_langchain` | langchain docs |
| 1768 | `router_benchmark` | benchmark |
| 1772 | `router_scout` | scout |
| 1776 | `router_claim` | claim |
| 1780 | `router_trust_pages` | trust |
| 1801 | `channel_router` | channel |
| 1805 | `security_check_router` | security |
| 2399 | `router_resolve` | conditional |

Two `app.mount(...)` calls at the bottom (lines 2429, 2434) attach
`/static` and `/` to a static-files directory. The `/`-mount means any
route NOT defined above falls through to static — relevant for 404 vs
serve-from-disk behavior.

### A.3 MCP tools (`agentindex/crypto/zarq_mcp_server.py`)

Standalone server on `:8001`, served by `com.zarq.mcp-sse` (Starlette). The
tool list is declared at module scope (around line 80–422). 19 ZARQ-relevant
tools total:

| Tool name | One-line purpose |
|---|---|
| `crypto_rating` | Full Trust Score for a token (overall + 5-pillar breakdown) |
| `crypto_dtd` | Distance-to-Default (0–5) + 7 signal scores + trend + crash prob |
| `crypto_signals` | All active risk signals (collapse / stress) + scoreboard |
| `crypto_compare` | A/B token comparison |
| `crypto_distress_watch` | Tokens with DtD < 2.0, sorted asc |
| `crypto_alerts` | Active ZARQ structural warnings, filter by level |
| `crypto_ratings_bulk` | All rated tokens (bulk download) |
| `check_token_risk` | Zero-friction verdict (SAFE/WARNING/CRITICAL) + score |
| `get_risk_signals` | Full 205-token monitoring list |
| `get_trust_score` | Lightweight score-only lookup |
| `kya_check_agent` | Know-Your-Agent risk for an AI agent |
| `get_signal_feed` | Live signal feed sorted by severity |
| `vitality_check` | 5-dimension Vitality Score for a token |
| `vitality_compare` | A/B vitality comparison |
| `find_best_agent` | Top agents in a category meeting min trust score |
| `agent_benchmark` | Top-20 leaderboard for an agent category |
| `get_agent_stats` | Nerq ecosystem stats |
| `preflight_check` | Universal preflight for any software entity |
| `best_in_category` | Top-rated entities in any registry/category |

Tool handlers in `handle_tool(...)` (line 426) dispatch by name. Internally
each tool calls `zarq_api(path, params)` (line 49) which proxies to
`http://localhost:8000/<path>` — i.e. the MCP server **depends on the main
:8000 API** being up. If `com.nerq.api` is down, every MCP tool returns
error. Worth flagging in Phase 2 testing.

Starlette routes on the MCP app (around line 632–668):
- `/mcp` (`handle_mcp`)
- `/sse` (`handle_sse`)
- `/messages` (`handle_messages`)
- `/server-card` (`handle_server_card`)
- `/health` (`handle_health`)
- **No `/` root handler** → bare `mcp.zarq.ai/` returns 404. (Section D.3.)

### A.4 HTML templates

37 `.html` files under `agentindex/`. **18 ZARQ-relevant**, all in
`agentindex/crypto/templates/` plus one in `agentindex/templates/`:

| Template | Renderer module | Notes |
|---|---|---|
| `zarq_landing.html` | `crypto_seo_pages.py` | main `/crypto` page |
| `zarq_methodology.html` | `crypto_seo_pages.py` | also has `.bak.20260304` |
| `zarq_whitepaper.html` | `crypto_seo_pages.py` | |
| `zarq_api_docs.html` | `crypto_seo_pages.py` | |
| `zarq_cascade_risk.html` | `zarq_cascade_page.py` | |
| `zarq_early_warning.html` | `crypto_seo_pages.py` | |
| `zarq_track_record.html` | `crypto_seo_pages.py` | |
| `zarq_vitality_backtest.html` | `crypto_seo_pages.py` | |
| `zarq_vitality_methodology.html` | `crypto_seo_pages.py` | |
| `zarq_agent_intelligence.html` | `crypto_seo_pages.py` | |
| `zarq_recovery.html` | `crypto_seo_pages.py` | |
| `paper_trading.html` | `crypto_seo_pages.py` | also has `.bak` — section D.4 |
| `token_page.html` | `zarq_token_pages.py` | per-token page |
| `tokens_index.html` | `zarq_token_pages.py` | `/tokens` directory |
| `crash_watch.html` | `zarq_content_pages.py` | |
| `yield_risk.html` | `zarq_yield_page.py` | |
| `learn_article.html` / `learn_hub.html` | `zarq_content_pages.py` | learn section |
| `zarq_yield_template.html` | (in `templates/`) | yield variant |

### A.5 Static assets

`agentindex/static/` exists (mounted at `/`). Contains ~32 files including
a stand-alone `zarq_home.html`. No further classification — too many small
asset files to enumerate; the mount catches anything not routed.

### A.6 Cloudflared ingress (`~/.cloudflared/config.yml`)

| Hostname | Target | Service |
|---|---|---|
| `nerq.ai` | `http://localhost:8000` | com.nerq.api |
| `api.nerq.ai` | `http://localhost:8000` | com.nerq.api |
| `dash.nerq.ai` | `http://localhost:8203` | com.agentindex.dashboard |
| `mcp.nerq.ai` | `http://localhost:8300` | com.agentindex.mcp-sse |
| `mcp.zarq.ai` | `http://localhost:8001` | com.zarq.mcp-sse |
| `zarq.ai` | `http://localhost:8000` | com.nerq.api |
| `api.zarq.ai` | `http://localhost:8000` | com.nerq.api |
| `agentcrawl.dev` | `http://localhost:8000` | com.nerq.api |
| `api.agentcrawl.dev` | `http://localhost:8000` | com.nerq.api |
| `dash.agentcrawl.dev` | `http://localhost:8203` | com.agentindex.dashboard |
| `mcp.agentcrawl.dev` | `http://localhost:8300` | com.agentindex.mcp-sse |
| catch-all | `http_status:404` | tunnel default |

Tunnel UUID in config.yml: `a17d8bfb-9596-4700-848a-df481dc171ad`. (CLAUDE.md
lists `a17d8bfb-9596-4700-848a-df481dc171a4` — last character mismatch.
Section D.1.)

### A.7 LaunchAgents relevant to ZARQ surface

| Label | Function | Current state |
|---|---|---|
| `com.nerq.api` | FastAPI on :8000 (the whole surface) | `pid=16269 runs=2141 last_exit=1` |
| `com.zarq.mcp-sse` | MCP server on :8001 | `pid=1017 exit=0` ✓ |
| `com.agentindex.dashboard` | dashboard server on :8203 | `pid=1027 exit=0` ✓ |
| `com.agentindex.mcp-sse` | MCP server on :8300 | `pid=1025 exit=0` ✓ |
| `com.zarq.vitality-recalc` | nightly vitality recalc | idle, `exit=0` |
| `com.zarq.vitality-report` | vitality report | idle, `exit=0` |
| `com.nerq.zarq-cache` | builds `/tmp/zarq_dashboard_cache.json` every 4 min | **`exit=2`** (broken) |
| `com.nerq.dashboard-cache-warmer` | warms dashboard cache every 4 min | `pid=23210 exit=0` ✓ |
| `com.nerq.dashboard-data` | dashboard data refresh | **`exit=1`** |
| `com.nerq.crypto-daily` | the rating/NDD/signals pipeline | `exit=1` (last partial run; fixed by commits 2bce993 + 0eac6d7) |
| `com.nerq.paper-trading-daily` | paper trading nightly | idle, `exit=0` |
| `com.nerq.alert-monitor` | alert monitor | idle, `exit=0` |
| `com.nerq.compat-matrix` | compatibility matrix builder | `exit=0` but pre-existing CLAUDE.md note flags it broken weekly |
| `com.nerq.dex-volumes` | dex volume refresh | **`exit=1`** |
| `com.nerq.daily-scores` | daily score recompute | `pid=79831 exit=0` (running) |
| `com.nerq.yield-orchestrator` | yield orchestrator | idle, `exit=0` |
| `com.nerq.signal-warehouse` | signal warehouse | idle, `exit=0` |
| `com.nerq.cache-warmer` | hourly general cache warmer | idle, `exit=0` |
| `com.nerq.stale-scores` | stale-score detector | **`exit=1`** |
| `com.nerq.trust-score-v3` | trust score recomputer | **`exit=1`** |
| `com.nerq.king-refresh` | king-of-category refresh | idle, `exit=0` |
| `com.nerq.infra-healthcheck` | this session's deploy | idle, `exit=0` ✓ |

**Five ZARQ-touching LaunchAgents with non-zero last exit**:
`com.nerq.zarq-cache` (2), `com.nerq.dashboard-data` (1), `com.nerq.dex-volumes`
(1), `com.nerq.stale-scores` (1), `com.nerq.trust-score-v3` (1).

## B) Cloudflared ↔ App routing

```
nerq.ai               ──┐
api.nerq.ai           ──┤
zarq.ai               ──┤
api.zarq.ai           ──┼──→ :8000 (com.nerq.api)
agentcrawl.dev        ──┤    │
api.agentcrawl.dev    ──┘    │
                              ├──> 56 routes in discovery.py
                              ├──> 26 in crypto_seo_pages
                              ├──> 22 in crypto_api_v3
                              ├──> 12 in zarq_seo_builds
                              ├──> 11 in entity_pages
                              ├──> 8 in crypto_api.py
                              ├──> 6 in zarq_token_pages
                              ├──> 6 in zarq_compare_pages
                              ├──> 7 in zarq_machine_discovery
                              └──> ~50 more routes across other modules

dash.nerq.ai          ──┐
dash.agentcrawl.dev   ──┴──→ :8203 (com.agentindex.dashboard)
                              └──> contents not inventoried this phase

mcp.nerq.ai           ──┐
mcp.agentcrawl.dev    ──┴──→ :8300 (com.agentindex.mcp-sse)
                              └──> contents not inventoried this phase

mcp.zarq.ai           ─────→ :8001 (com.zarq.mcp-sse)
                              ├──> 19 MCP tools (section A.3)
                              └──> 5 Starlette routes (no root → 404 on /)
```

**Gaps:** none of the cloudflared hostnames point at a port that isn't
listening, and every listening port has at least one hostname. The
gap-of-coverage is internal: see D.3 (`mcp.zarq.ai/` has no root handler).

## C) Dependency graph (ZARQ-relevant)

```
                                  ┌─────────────────────────────────────┐
                                  │ Nbg primary (zarq.* + public)       │
                                  │ via PgBouncer write pool            │
                                  └──────┬──────────────────────────────┘
                                         │ reads + writes
                                         │
                  ┌──────────────────────┴─────────────┐
                  │                                    │
            ZARQ HTTP endpoints                   ZARQ pipelines
            (zarq.ai, api.zarq.ai,                (com.nerq.crypto-daily,
             /crypto/*, /tokens/*,                 com.zarq.vitality-recalc,
             /vitality, /yield, …)                 com.nerq.daily-scores, …)
                  │                                    │
                  │ also read from local PG            │ produce zarq.* rows
                  ▼ (replica, stale per ADR-003a)      ▼
            Mac Studio local PG                  zarq.crypto_price_history
            via PgBouncer read pool              zarq.crypto_ndd_alerts (now
                                                  writable post-2bce993)
                                                 zarq.crypto_ndd_daily
                                                 zarq.nerq_risk_signals
                                                 zarq.crypto_rating_daily
                                                 zarq.vitality_scores
                                                 zarq.defi_yields
                                                 zarq.crypto_pipeline_runs
                                                 zarq.dual_write_failures
                                                 zarq.infrastructure_alerts
                                                 zarq.agent_dashboard
                                                 zarq.compatibility_matrix
                                                 zarq.chain_dex_volumes
                                                 zarq.external_trust_signals

            ZARQ dashboard pages                 Cache builders
            (/dashboard, etc.)                   ┌──────────────────────────┐
                  │                              │ com.nerq.zarq-cache      │
                  │ HTTP                         │   writes /tmp/zarq_      │
                  └──→ /tmp/zarq_dashboard_      │   dashboard_cache.json   │
                       cache.json ◀──────────────┤   every 240s. exit=2     │
                                                 │   = broken               │
                                                 │ com.nerq.dashboard-      │
                                                 │   cache-warmer (running) │
                                                 │ com.nerq.dashboard-data  │
                                                 │   (exit=1)               │
                                                 └──────────────────────────┘

            MCP tools (mcp.zarq.ai)              MCP server (:8001)
                  │ JSON-RPC over HTTP/SSE       internally calls
                  └──→ http://localhost:8001 ──→ http://localhost:8000/<path>
                                                 (i.e. depends on :8000 being up)
```

**Hard dependency chain:** every `mcp.zarq.ai` tool call → MCP server →
`localhost:8000`. If com.nerq.api dies, MCP tools fail. If PgBouncer write
pool saturates again (cf. morning incident), some MCP tools that hit
write paths queue and time out.

**Cache file is in `/tmp`:** `/tmp/zarq_dashboard_cache.json` is volatile
across reboots. If macOS reboots while `com.nerq.zarq-cache` is still
`exit=2`-broken, the dashboard has no cache fallback.

## D) Initial observations (facts, not analysis)

D.1 — **Cloudflared tunnel UUID mismatch.** `~/.cloudflared/config.yml`
declares `a17d8bfb-9596-4700-848a-df481dc171ad`. `CLAUDE.md` (Critical
paths) declares `a17d8bfb-9596-4700-848a-df481dc171a4` and tags it as
"scheduled for deletion." Last character differs (`d` vs `4`). One of the
two documents is wrong about the current tunnel.

D.2 — **Code references `crash_model_v3_predictions` in 12 places across
8 files** (`kya_api.py`, `crash_shield.py`, `signal_feed.py`,
`vitality_score.py`, `crash_shield_api.py`, `agent_wow_analysis.py`,
`zarq_seo_builds.py`, `propagated_risk_engine.py`) but the table is not in
the live `zarq.*` schema on Nbg. Per the templates-and-schema audit it's a
*local* SQLite table created by `crash_prediction_model_v3.py`. Whether
the eight files querying it actually find the SQLite table is not
investigated here — fact-of-existence-in-code is the data point.

D.3 — **`mcp.zarq.ai/` returns 404.** The Starlette app on :8001 has routes
`/mcp`, `/sse`, `/messages`, `/server-card`, `/health` (file
`agentindex/crypto/zarq_mcp_server.py` lines 632–672) but no `/` handler.
Bare-domain hits get the tunnel-default 404. (Mentioned by Anders in the
opening of the 2026-05-30 outage triage.)

D.4 — **`paper_trading.html.bak` lives next to `paper_trading.html`** in
`agentindex/crypto/templates/`. Same with `zarq_methodology.html.bak.20260304`.
Two-version template artifacts present.

D.5 — **Five ZARQ-touching LaunchAgents have non-zero `last_exit`.** Listed
in A.7: `com.nerq.zarq-cache` (2), `com.nerq.dashboard-data` (1),
`com.nerq.dex-volumes` (1), `com.nerq.stale-scores` (1),
`com.nerq.trust-score-v3` (1). CLAUDE.md (`Known broken things` section)
explicitly calls out `stale_score_detector` and `compatibility_matrix` as
broken; the rest are new data points.

D.6 — **ZARQ dashboard cache is written to `/tmp`.** `_DASHBOARD_CACHE_FILE
= "/tmp/zarq_dashboard_cache.json"` (`agentindex/zarq_dashboard.py:768`).
Volatile across reboots. `com.nerq.zarq-cache` is the (currently-broken)
producer.

D.7 — **MCP server is layered on top of `:8000`.** `zarq_mcp_server.py:49`
`async def zarq_api(path, params)` is the universal proxy that every MCP
tool calls. There is no fallback if `:8000` is down — the morning incident's
crash-loop would have made every MCP tool fail too. No counterpart to
`zarq.infrastructure_alerts` for `:8000` from the MCP side.

D.8 — **Two MCP services exist (com.zarq.mcp-sse on :8001 and
com.agentindex.mcp-sse on :8300).** Both are up. Whether they expose the
same tool surface or different ones is not inventoried here — only the
`:8001` server's tool list was read this phase.

D.9 — **`/static`-mount catches the unrouted long tail.** Two `app.mount`
calls at the bottom of `discovery.py` (lines 2429 and 2434) attach
`/static` and `/`. The `/`-mount means any path that doesn't match a
defined route falls through to serve a file from `agentindex/static/`. A
file named `<something>.html` in that directory becomes implicitly
accessible at `/<something>.html`. The directory contains a standalone
`zarq_home.html` whose route status (404 vs served) was not verified.

D.10 — **`com.nerq.api` is unstable post-fix.** `runs=2141` at inventory
start, was 2139 immediately after the morning's PgBouncer repoint. Two
restarts in roughly an hour. PgBouncer log shows 14 `query_wait_timeout`
events since 09:00. The morning fix unblocked the silent-failure mode but
did not eliminate transient saturation under load.

D.11 — **Conditional `include_router` calls.** Lines 1295
(`badge_router`), 1298 (`multi_jurisdiction_router`), 1352 (`router_agents`),
1545 (`crypto_v3_router`), 2399 (`router_resolve`) are indented inside `if`
blocks. Whether their guards evaluate true at runtime was not verified.

## E) Phase 2 test-scope recommendation

Phase 2 should smoke-test the ZARQ surface — these counts are inputs.

- **HTTP endpoints to test:** 93 ZARQ-relevant routes (the 18.4% subset).
- **MCP tools to test:** 19 (every entry in A.3). Each requires the
  `:8000` API up because of the proxy chain.
- **HTML pages to render:** 18 templates (A.4). Each tied to one or more
  routes already in the 93-count.
- **Read-only vs write:** the visible majority is read-only (rating, NDD,
  vitality, signals all GET). Paper trading is the obvious write target
  (`router_save_sim` line 1377). To be confirmed.
- **Test data:** paper trading has a per-user simulation table the Phase 2
  test should locate before issuing writes. Other surfaces accept
  arbitrary token IDs and degrade gracefully.
- **Synthetic input needed for:** any path with a `{token_id}` placeholder
  — supply a fixed test set (`bitcoin`, `ethereum`, `solana`, plus one
  known-distressed and one known-missing).
- **Estimated runtime:** assuming ~1s per request (cold cache average from
  the morning probes), ~110 requests = roughly 2 minutes serial, 30s with
  modest parallelism. The MCP tools add ~19 calls; same magnitude.
- **Tests that will likely fail before the test suite even runs:** the
  five-LaunchAgent-`exit≠0` set (D.5) means whatever data those agents
  produce is stale. Endpoints reading from those tables will return old
  or no data. Phase 2 should record this as expected, not as a test
  failure.

## Out-of-scope for Phase 1

- Actually hitting any endpoint with HTTP (Phase 2).
- Reasoning about *why* anything is broken (Phase 3).
- Cleaning up `.bak` files, redundant routes, orphaned cache files
  (Phase ≥4 if at all).
- Inventorying the `:8203` and `:8300` services beyond ports and labels.
- Verifying whether the conditional `include_router` guards evaluate true
  at runtime.
