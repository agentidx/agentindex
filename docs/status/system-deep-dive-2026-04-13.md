# System Deep Dive — 2026-04-13

## Executive Summary (800 words)

Nerq is a trust score engine serving 2.47M scored entities across 30 registries plus 5M HuggingFace agents/models/datasets, rendered across 23 languages and ~35 URL patterns. The system handles ~1M requests/day, dominated by AI crawlers (96%) with ~1,200 real user-triggered AI citations per day (95.8% from ChatGPT).

**What we actually built vs what we think we built:** The trust score system uses 5 dimensions (Security, Maintenance, Popularity, Community, Quality), not the 8 referenced in strategy documents. Website scoring is heavily skewed toward Popularity (70% weight via Tranco rank). Non-website scoring is evenly distributed (20-25% per dimension). This works well for developer packages but poorly for entities without GitHub presence (charities, travel, cosmetics).

**The real URL pattern count is ~35, not 12.** Beyond the 12 in `pattern_routes.py`, there are 22 in `demand_pages.py`, 14 in `seo_programmatic.py`, 14 in `seo_dynamic.py`, plus entity-specific routes in `agent_safety_pages.py`. Most share the same template infrastructure (`_resolve` → data lookup → f-string HTML) but only 2 have full AI citation optimization (Article schema + pplx-verdict): `/safe/*` and `/was-X-hacked`.

**Localization is deep but narrow.** Entity pages (`/safe/*`) are fully localized via `_render_agent_page(slug, info, lang=lang)` — the base English HTML is generated with the `lang` parameter, then phrase-replacement translations are applied (12,621 lines of translation mappings). But pattern_routes pages (12 patterns) have NO localization — they render English-only even when accessed via `/{lang}/was-X-hacked`. The localized_routes catch-all handles them but without translating the content.

**Automation has 37 LaunchAgents but 4 are failing:** npm-crawler (exit 1), npm-bulk-enricher (exit 1), signal-warehouse (exit 1), stale-scores (exit 1). These silent failures mean npm packages aren't being refreshed and stale score detection isn't running. The API itself (exit 1 in launchctl list) is actually running correctly — the exit code is from the most recent restart, not current state.

**The Buzz 2.0 specification is ambitious and complete** (27K words, 24 responsibility areas). It envisions Buzz handling everything from health monitoring to customer service to revenue operations. But the current Buzz runs on qwen3:8b (Ollama, 8B parameter local model) with a stale Feb 2026 operations plan — the gap between spec and reality is large.

**Cloud migration is 60% complete.** Mac Studio remains the sole traffic receiver. Hetzner Nbg+Hel nodes have the API deployed, Postgres streaming replication active, dual-write live, pgBackRest verified. What remains: Cloudflare Load Balancer configuration, DNS cutover, Patroni failover, Buzz relocation.

**The three biggest constraints for 24/7 automation are:**
1. **Code deployment requires API restart** — there's no hot-reload, no blue-green deployment. Every code change requires `kill -9` + LaunchAgent restart, causing 5-10 seconds of downtime.
2. **No quality gate between code and production** — there are no automated tests that run before serving new content. A bad template change goes live immediately.
3. **Single Redis instance** (512 MB, maxmemory reached) — Redis is at capacity. Adding more cached pages requires either eviction policy changes or a larger Redis instance.

---

## DEL 1: What We Actually Built

### 1A: Pattern Routes — Complete Inventory

12 routes in `pattern_routes.py`, all using the shared template infrastructure:

| # | URL Pattern | Handler | Content uniqueness vs /safe/ |
|---|---|---|---|
| 1 | `/was-{slug}-hacked` | `_hacked_page()` | **High** — CVE data, incident history, Article schema |
| 2 | `/{slug}-data-breach` | `_pattern_page("data-breach")` | Low — same trust score, different headline |
| 3 | `/is-{slug}-down` | `_pattern_page("down")` | Low — same trust score, "Operational" verdict |
| 4 | `/is-{slug}-worth-it` | `_pattern_page("worth-it")` | Low — reformulated trust assessment |
| 5 | `/should-i-use-{slug}` | `_pattern_page("should-")` | Low — reformulated verdict |
| 6 | `/who-owns/{slug}` | `_pattern_page("who-owns")` | Low — shows author/publisher |
| 7 | `/where-is-{slug}-based` | `_pattern_page("where")` | Low — shows jurisdiction |
| 8 | `/how-does-{slug}-make-money` | `_pattern_page("how-money")` | Low — generic revenue model |
| 9 | `/how-to-delete-{slug}-account` | `_pattern_page("delete")` | Low — generic instructions |
| 10 | `/{slug}-security-settings` | `_pattern_page("security")` | Low — generic security tips |
| 11 | `/free-alternative-to-{slug}` | Custom | Medium — links to /alternatives/ |
| 12 | `/private-alternative-to-{slug}` | Custom | Medium — privacy-focused alts |

**Critical finding:** Only #1 (`/was-X-hacked`) has genuinely unique content (CVE data, Article schema, pplx-verdict). Patterns #2-10 use `_pattern_page()` which generates the SAME trust-score table with different headings. This is a thin-content risk if all are indexed.

All 12 share: `_head()` (meta, hreflang, og:), `_foot()` (cross-links to all patterns), `_faq()` (3 FAQ items → FAQPage schema), `_resolve()` (entity lookup from software_registry → agents).

### 1B: Trust Score — Real Implementation

**5 dimensions, computed in `rescore_registries.py`:**

```
Standard weighting (all registries except website):
  Security:    25% — score_security(cve_count, enriched, license, openssf)
  Maintenance: 20% — score_maintenance(release_count)  
  Popularity:  20% — score_popularity(registry, downloads, stars, forks)
  Community:   15% — score_community(stars, forks, contributors)
  Quality:     20% — score_quality(license, description)

Website weighting:
  Popularity:  70% — Tranco rank is only differentiator
  Quality:     15%
  Security:     5%
  Maintenance:  5%
  Community:    5%
```

**Data sources per dimension:**
- Security: `cve_count` (from cve_scanner.py/OSV.dev), `openssf_score` (from openssf_scorecard.py), license string
- Maintenance: `release_count` (from registry crawlers)
- Popularity: `downloads`/`weekly_downloads` (registry-specific), `stars`, `forks`
- Community: `stars`, `forks`, `contributors`
- Quality: `license` (validated), `description` (length/presence)

**Missing data handling:** Functions return 50 (neutral) when input is NULL/0. This means entities without CVEs get Security=50, entities without releases get Maintenance=50. The effect: many entities cluster around 48-55 with minimal differentiation.

**The "8 dimensions" discrepancy:** Strategy documents reference 8 dimensions (Security, Privacy, Reliability, Transparency, Maintenance, plus 3 others). The code implements 5. The additional columns `privacy_score`, `transparency_score`, `reliability_score` exist in `software_registry` but are populated only for Kings (275 entities = 0.01% of corpus). They are NOT used in `compute_total()`.

**`trust_score_v3.py`** exists with a `calculate_v3_score()` function that computes additional dimensions (transparency, privacy) but it's invoked only during Kings enrichment, not during batch rescoring.

### 1C: Entity Pipeline (crawl → serve)

```
CRAWL (npm example: npm_crawler.py)
  └→ Fetches package metadata from registry.npmjs.org
  └→ Inserts/updates software_registry row
  └→ ~200ms per entity (network-bound)

ENRICH (registry_enrichment.py, cve_scanner.py, openssf_scorecard.py)
  └→ Adds CVE data, OpenSSF scores, GitHub stats
  └→ ~500ms per entity (external API calls)
  └→ Kings enriched first (is_king=true filter)

SCORE (rescore_registries.py)
  └→ Reads 5 dimension inputs from software_registry
  └→ Computes weighted total
  └→ UPDATE trust_score, trust_grade + 5 dimension scores
  └→ ~0.1ms per entity (in-DB computation)

RENDER (agent_safety_pages.py _render_agent_page)
  └→ Reads entity from software_registry (or agents table)
  └→ Generates full HTML (7,000-15,000 chars, Kings get extra sections)
  └→ 100-1,000ms cold render (f-string assembly + DB queries)

CACHE (3 layers)
  └→ L1: In-memory dict (1h TTL, per-worker, ~100MB)
  └→ L2: Redis PageCacheMiddleware (4h TTL, 512MB, shared)
  └→ L3: Cloudflare CDN (max-age=14400 browser, s-maxage=86400 CDN)

SERVE (FastAPI/uvicorn, 8 workers)
  └→ Cache hit: <1ms (Redis) or <5ms (Cloudflare edge)
  └→ Cache miss: 100-1,000ms (full render)
```

### 1D: All URL Patterns (Complete Count)

| Source file | Entity patterns | Meta/feed patterns | Sitemap patterns | Total |
|---|---:|---:|---:|---:|
| agent_safety_pages.py | 5 | 3 | 0 | 8 |
| pattern_routes.py | 12 | 0 | 0 | 12 |
| demand_pages.py | 13 | 4 (feeds) | 5 | 22 |
| seo_programmatic.py | 4 | 1 | 5 | 10 |
| seo_dynamic.py | 8 | 0 | 4 | 12 |
| comparison_pages.py | 3 | 0 | 0 | 3 |
| guide_pages.py | 4 | 0 | 0 | 4 |
| vs_pages.py | 4 | 0 | 0 | 4 |
| review_pages.py | 1 | 0 | 0 | 1 |
| **Total** | **54** | **8** | **14** | **76** |

**54 entity-specific URL patterns.** Each can theoretically render for any of the 2.47M entities. But most return 404 or generic "Not Yet Analyzed" for entities they don't have specific data for.

### 1E: Localization Depth

| Template type | Localization method | Quality |
|---|---|---|
| Entity pages (/safe/*) | `_render_agent_page(lang=lang)` → phrase replacement | Machine-translated, 12,621 lines of mappings |
| Homepage | `render_localized_homepage()` | Dedicated per-language templates |
| About/Privacy/Terms | `pages_i18n.py` renders | Dedicated per-language |
| /best/* pages | `_BEST_UI_STRINGS` + `_BEST_FAQ_I18N` dicts | UI labels translated, entity names unchanged |
| pattern_routes (12 patterns) | **NOT localized** | English content with lang attribute only |
| demand_pages (13 patterns) | **NOT localized** | English only |

### 1F: MCP Server

15 tools, 67K SSE requests in 30 days. Top preflight targets: `test` (6,803), `langchain-ai/langchain` (124), `express` (111), `react` (78), `tiktok` (62).

Not registered in any marketplace. Tools cover: agent discovery (4), crypto risk (5), trust checks (3), ecosystem stats (3).

### 1G: Analytics Pipeline

`analytics.py:344 log_request()` → SQLite INSERT on every non-static request. Bot detection: UA pattern matching (34 AI_BOTS patterns) → generic bot keywords → datacenter IP detection → volume-based (>50/day). `bot_purpose` taxonomy added 2026-04-13 with 30-day backfill.

**692K requests/7d have bot_purpose=NULL** (mostly is_bot=1 from generic bot detection where the specific bot isn't in AI_BOTS). **169K human requests/7d** also have NULL purpose.

Return visitors: **8,031 IPs visited on multiple days** out of 138,722 total IPs (5.8%) in 7 days.

---

## DEL 2: Infrastructure

### 2A: Architecture

| Node | Specs | Role today | Planned role |
|---|---|---|---|
| Mac Studio | M1 Ultra, 20 cores, 64 GB | **Primary**: API, Postgres, Redis, all crawlers, Buzz | Optional accelerator |
| Mac Mini | (not accessible) | Idle/Claude Code | Read-only queries, crawl offload |
| Hetzner Nbg | 8 vCPU, 16 GB, 301 GB disk | API deployed (no traffic), PG replica | **Primary**: API, Postgres primary, Buzz |
| Hetzner Hel | 8 vCPU, 16 GB, 301 GB disk | API deployed (no traffic), PG replica | Replica, failover standby |
| Hetzner CPX21 | (provisioned) | Idle | Worker node (crawlers, enrichment) |

### 2D: Data Storage

| Store | Size | Content |
|---|---|---|
| Postgres (total) | ~91 GB | agents (17 GB), software_registry (4 GB), entity_lookup (3 GB), zarq.* (1 GB), others |
| SQLite analytics.db | 11 GB | 17.3M request rows (30d retention) |
| SQLite crypto_trust.db | 1.1 GB | ZARQ crypto data (dual-write to PG) |
| Redis | 512 MB (at maxmemory) | Page cache (pc:* keys), 4h TTL |

### 2C: Network

| Path | Latency |
|---|---|
| Mac Studio → Nbg (Tailscale) | 36 ms |
| Mac Studio → Hel (Tailscale) | 13 ms |
| Cloudflare → Mac Studio (tunnel) | ~30 ms |
| User → Cloudflare edge | 10-100 ms (geographic) |

### 2E: Architectural Constraints

**With 5x compute:** Could run 40 uvicorn workers (vs 8), parallel crawlers across 5 nodes, 50K entities/hour enrichment (vs 10K).

**Cannot do regardless of compute:** Real-time trust score updates (scoring depends on batch data like weekly downloads), TLS fingerprint bot detection (requires Cloudflare Enterprise), client-side JS analytics (no CDN for JS delivery).

**Architectural debt:** Single Redis instance at maxmemory, no connection pooling for SQLite (WAL mode contention), no automated deployment pipeline (manual kill+restart), no test suite for templates.

---

## DEL 3: Automation Analysis

### 3A: Current Automation (37 LaunchAgents)

| Category | Count | Status |
|---|---:|---|
| Running processes (PID) | 5 | api, watchdog, chrome-users, nuget-downloads, zarq-cache |
| Healthy cron (exit 0) | 28 | All scheduled jobs between runs |
| Failing (exit 1) | 4 | npm-crawler, npm-bulk-enricher, signal-warehouse, stale-scores |

### 3B: Manual Steps Required Today

| Operation | Steps | Can automate? |
|---|---|---|
| New URL pattern | 1. Write code 2. Restart API 3. Flush cache 4. IndexNow 5. Sitemap | Yes, with hot-reload + deployment pipeline |
| Bulk entity generation | Run crawler → enrich → rescore | Already automated (LaunchAgents) |
| IndexNow push | auto_indexnow.py runs daily | Already automated |
| Localization | Done at render time via lang parameter | Automated for /safe/*, NOT for pattern_routes |
| Cache purge | Manual Redis DEL or wait 4h | Could auto-flush on git push |
| Quality control | Manual curl + visual check | No automated smoke tests exist |

### 3C: Full Automation Scenarios

**Scenario: New pattern_route (e.g. /is-X-deprecated)**
1. Claude Code writes handler in pattern_routes.py (5 min)
2. Git commit + push
3. **GAP:** No automated deploy pipeline. Today: manual kill+restart.
4. **GAP:** No automated smoke test. Today: manual curl.
5. IndexNow via auto_indexnow.py (next morning run)
6. Sitemap auto-generates if route follows existing patterns

**Required for automation:** Git-push-triggered deployment hook, automated smoke test suite, health check after restart.

**Scenario: 100K new entities**
1. Crawler fetches from registry API: ~14 hours at 2 entities/sec
2. Enrichment (CVE, GitHub, OpenSSF): ~28 hours at 1 entity/sec
3. Scoring: ~17 minutes at 100K/hour
4. Pages render on-demand (no pre-generation needed)
5. IndexNow: 100K URLs × 8 patterns = 800K URLs → 4 days at 200K/day

**Total: ~3 days for full pipeline.** Bottleneck is enrichment (external API rate limits).

**Scenario: Daily content regeneration at scale (100K × 12 × 23 = 27.6M pages)**
Not feasible to regenerate 27.6M pages daily. The freshness pipeline approach (detect delta, regenerate only changed, push selectively) is the correct architecture. Expected: 500-2,000 entities change daily → 500-2K × 8 URLs = 4K-16K IndexNow pushes/day.

**Scenario: A/B template testing**
Not currently possible. Would require:
1. Template variant system (serve different HTML to different user segments)
2. Measurement integration (track AI bot response per variant)
3. Decision engine (after N days, pick winner)
4. This is a significant engineering project, not a quick automation.

### 3D: Buzz 2.0

**Current Buzz:** 8 cron jobs on openclaw, qwen3:8b local model, stale Feb 2026 operations plan. Discord integration broken. Effectively a degraded health-check bot.

**Buzz 2.0 spec:** 24 responsibility areas across 4 categories (daily ops, content ops, content generation, strategic decisions). Requires: upgraded LLM (70B+ parameter), reliable node (Hetzner), full API access to Nerq systems, escalation chain to Anders.

**Gap to close:** The spec is complete but implementation requires Phase 0 completion (Buzz needs to run on Hetzner Nbg, not Mac Studio). Estimated implementation: 2-3 weeks after Phase 0 cutover.

### 3E: Claude Code Capacity

| Node | Claude Code instances | Best suited for |
|---|---:|---|
| Mac Studio | 1-2 (memory-constrained) | Code changes, analysis, DB queries |
| Hetzner Nbg | 2-3 (16 GB RAM) | Bulk data processing, crawling |
| Hetzner Hel | 2-3 (16 GB RAM) | Parallel analysis, testing |

**Orchestration:** No mechanism exists for Buzz to spawn Claude Code jobs. Would require: task queue (Redis or Postgres), job runner on each node, result collection.

### 3F: Quality Gates for 24/7

**Required but not built:**
1. Smoke test suite: curl 10 sample URLs after deploy, verify 200 + key content
2. Schema validation: verify FAQPage/Article JSON-LD parses correctly
3. Anomaly detection: alert if ChatGPT-User drops >30% day-over-day
4. Rollback trigger: if 5xx rate exceeds 1% for 5 minutes, auto-revert last deploy
5. Notification: ntfy.sh or Discord alert on anomalies (currently broken)

---

## DEL 4: Strategic Findings

### 5 Most Important Findings for Automation

1. **33 of 35 URL patterns lack AI citation optimization.** Only `/safe/*` and `/was-X-hacked` have the full stack (Article schema, pplx-verdict, ai-summary, nerq:answer). The other 33 patterns are template-generated with minimal schema — low cost to upgrade if the pilot succeeds.

2. **No deployment pipeline exists.** Every code change requires manual API restart. This is the single biggest blocker for 24/7 automated operations. A git-push → restart → smoke-test pipeline would unlock Buzz-driven deployments.

3. **Redis at 512 MB maxmemory.** The page cache is full. New pages evict old pages. Scaling to more patterns/entities requires either increasing Redis memory or switching to a tiered cache strategy.

4. **The freshness pipeline covers only scoring, not content.** `freshness_pipeline.py` detects score changes and pushes to IndexNow, but it doesn't regenerate the actual HTML. The cached HTML still shows the old score until the Redis cache expires (4h) or is manually flushed.

5. **4 LaunchAgents failing silently** means npm data freshness is degraded. npm is our largest registry (528K entities). Stale npm scores affect ChatGPT-User citation quality for developer-tool queries.

### 5 Things We Think Exist But Don't (Gaps)

1. **8 trust dimensions** — only 5 are computed in production; 3 more exist in code but only for Kings
2. **Localized pattern pages** — `/{lang}/was-X-hacked` serves English content with a lang tag
3. **Automated quality testing** — no smoke tests, no schema validation, no regression detection
4. **Hot-reload deployment** — every change requires full API restart
5. **Return visitor tracking** — no cookies, no sessions, no way to distinguish repeat humans from new ones

### 5 Hidden Assets We Didn't Expect

1. **67K MCP requests/month** — the MCP server is actively used (mostly preflight checks)
2. **`trust_score_v3.py`** — a more sophisticated scoring engine exists but is only used for Kings enrichment
3. **4 JSON/JSONL data feeds** (`/feed/daily-changes.jsonl`, `/feed/entity-ratings.jsonl`, `/feed/predictions.jsonl`, `/feed/ai-interest.jsonl`) — machine-readable feeds that AI systems could consume
4. **`_queue_for_crawling()`** — entities that get 404 are automatically queued for crawling
5. **8,031 multi-day return visitors** (5.8% of human IPs) — there IS a returning audience, even if small

### 3 Quick Wins (< 48 hours)

1. **Fix the 4 failing LaunchAgents** (npm-crawler, npm-bulk-enricher, signal-warehouse, stale-scores). These are likely simple configuration errors. Fixing them restores npm data freshness for 528K entities.

2. **Add HuggingFace to llms.txt** — HuggingFace datasets+models are 32% of ChatGPT-User traffic but llms.txt doesn't mention them. A 5-line edit could improve AI discoverability.

3. **Extend AI citation optimization to 5 more pattern_routes** — copy the `/was-X-hacked` treatment (Article schema, pplx-verdict, direct answer) to `/who-owns/`, `/should-i-use/`, `/is-X-worth-it/`, `/free-alternative-to/`, `/private-alternative-to/`. Uses existing code, ~2 hours of work.

### 3 Structural Changes for 24/7 at Scale

1. **Deployment pipeline:** git push → automated restart → smoke test → rollback on failure. Without this, every code change requires human intervention.

2. **Cache invalidation pipeline:** When a trust score changes, automatically flush the Redis cache for that entity's URLs (all patterns + languages). Currently, cache expires after 4 hours — meaning users see stale scores after an update.

3. **Buzz 2.0 implementation:** Move from 8 cron jobs on a degraded local LLM to the 24-responsibility Buzz 2.0 spec running on Hetzner with a capable LLM. This is the foundational change that enables everything else.
