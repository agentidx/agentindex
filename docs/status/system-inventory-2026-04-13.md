# System Inventory — 2026-04-13

## Executive Summary (5 key findings)

1. **2.47M entities across 30 registries, 293K sitemap URLs.** The entity corpus is massive but only a fraction is surfaced through sitemaps. The 5M agents table contains HuggingFace models/datasets that have separate page generators but limited structured safety analysis.

2. **23 URL-pattern forms × millions of entities = theoretically infinite pages.** But only ~12 patterns have unique content. The rest are template-reuse with different headings — a thin-content risk if all are indexed aggressively.

3. **Trust scores use 5 dimensions, not 8.** Security (25%), Maintenance (20%), Popularity (20%), Community (15%), Quality (20%). Websites use a different weighting (Popularity 70%). The "8 dimensions" referenced in strategy docs doesn't match the code.

4. **15 MCP tools, 26 verticals in llms.txt, but MCP and llms.txt describe different scopes.** MCP covers crypto+agents, llms.txt covers all registries. Neither covers HuggingFace models/datasets explicitly despite them being 32% of ChatGPT-User traffic.

5. **37 LaunchAgents, 3 with nonzero exit codes.** The system is heavily automated but several jobs are failing silently (npm-crawler, signal-warehouse, stale-scores, npm-bulk-enricher all exit 1).

---

## 1. Production Pages — What's Live

### Sitemap URL counts

| Sitemap | URLs |
|---|---:|
| sitemap-agents (3 files) | 150,000 |
| sitemap-safe (2 files) | 61,078 |
| sitemap-models | 50,000 |
| sitemap-compare-pages | 20,985 |
| sitemap-what-is | 5,000 |
| sitemap-localized | 3,784 |
| sitemap-reviews | 1,000 |
| sitemap-issues | 1,000 |
| sitemap-alternatives | 500 |
| sitemap-best | 303 |
| sitemap-guides | 200 |
| sitemap-stacks | 25 |
| sitemap-migrate | 20 |
| sitemap-trending | 5 |
| sitemap-blog | 5 |
| **Total indexed** | **~293,000** |

### URL patterns in code (complete list)

**From agent_safety_pages.py (primary entity pages):**
- `/safe/{slug}` — main trust score page
- `/is-{slug}-safe`, `/is-{slug}-legit`, `/is-{slug}-a-scam`
- `/is-{slug}-spyware`, `/is-{slug}-safe-for-kids`

**From pattern_routes.py (12 question patterns):**
- `/was-{slug}-hacked` (enhanced 2026-04-13 with CVE data)
- `/{slug}-data-breach`, `/is-{slug}-down`
- `/is-{slug}-worth-it`, `/should-i-use-{slug}`
- `/who-owns/{slug}`, `/where-is-{slug}-based`
- `/how-does-{slug}-make-money`, `/how-to-delete-{slug}-account`
- `/{slug}-security-settings`
- `/free-alternative-to-{slug}`, `/private-alternative-to-{slug}`

**From demand_pages.py (6 entity patterns + meta pages):**
- `/what-is/{slug}`, `/review/{slug}`, `/a-scam/{slug}`
- `/stack/{slug}`, `/issues/{slug}`, `/ai-interest/{slug}`
- `/profile/{slug}`, `/migrate/{a}-to-{b}`
- `/this-week`

**From seo_programmatic.py (3 collection patterns):**
- `/compare/{a}-vs-{b}`, `/best/{category}`, `/alternatives/{slug}`
- `/guide/{slug}`

**From seo_dynamic.py (aggregation pages):**
- `/trending`, `/new`, `/leaderboard`, `/leaderboard/{category}`
- `/insights`, `/insights/{slug}`
- `/model/{name}`, `/models`

**From localized_routes.py (23 language variants of all above):**
- `/{lang}/safe/{slug}`, `/{lang}/is-{slug}-safe`, etc.
- 22 non-English languages: es, pt, fr, de, ja, ru, ko, it, tr, nl, pl, id, th, vi, hi, ar, sv, cs, ro, zh, da, no

### Entity counts per vertical

| Registry | Entities | Scored | Kings | Category |
|---|---:|---:|---:|---|
| nuget | 641,641 | 641,641 | 200 | .NET packages |
| npm | 528,326 | 528,306 | 501 | Node packages |
| website | 500,963 | 500,963 | 10,879 | Websites (Tranco) |
| crates | 204,080 | 204,080 | 100 | Rust packages |
| packagist | 113,818 | 113,818 | 100 | PHP packages |
| pypi | 93,768 | 93,761 | 300 | Python packages |
| android | 57,552 | 57,552 | 13,050 | Android apps |
| wordpress | 57,089 | 57,089 | 500 | WP plugins |
| vscode | 48,948 | 48,948 | 200 | VS Code extensions |
| ios | 48,071 | 48,071 | 5,427 | iOS apps |
| steam | 45,361 | 45,361 | 500 | Steam games |
| chrome | 44,229 | 44,229 | 472 | Chrome extensions |
| firefox | 29,120 | 29,120 | 200 | Firefox add-ons |
| go | 22,095 | 22,095 | 100 | Go modules |
| gems | 10,104 | 10,104 | 100 | Ruby gems |
| homebrew | 8,286 | 8,286 | 80 | Homebrew |
| saas | 4,963 | 4,963 | 2,806 | SaaS platforms |
| city | 2,981 | 2,981 | 185 | Travel (cities) |
| ai_tool | 2,350 | 2,344 | 787 | AI tools |
| ingredient | 669 | 669 | 65 | Food ingredients |
| supplement | 584 | 584 | 137 | Supplements |
| cosmetic_ingredient | 584 | 584 | 73 | Cosmetics |
| charity | 504 | 504 | 493 | Charities |
| crypto | 226 | 224 | 196 | Crypto tokens |
| country | 158 | 158 | 158 | Travel (countries) |
| vpn | 79 | 79 | 79 | VPN services |
| password_manager | 55 | 55 | 0 | Password managers |
| website_builder | 51 | 51 | 0 | Website builders |
| hosting | 51 | 51 | 0 | Hosting providers |
| antivirus | 51 | 51 | 0 | Antivirus |
| **Total** | **2,466,757** | **2,466,532** | **37,688** | |

**Additionally:** `agents` table: 5,033,771 rows (HuggingFace models, datasets, MCP servers, etc.)

---

## 2. Data Sources

### Active crawlers/enrichers

| Crawler | Registry/scope | Entities | Update freq |
|---|---|---:|---|
| npm_crawler + npm_enrichment | npm | 528K | Daily (bulk enricher) |
| pypi_crawler + pypi_enrichment | pypi | 94K | Periodic |
| cve_scanner + cve_enrichment | All registries | 228 with CVEs | Daily |
| openssf_scorecard | GitHub repos | ~2K | Weekly |
| snyk_crossref (OSV.dev) | All registries | ~2K | Weekly |
| community_signals | GitHub/SO/Reddit | ~2K | Weekly |
| crypto_daily_master | crypto | 226 | Daily 06:00 UTC |
| chrome_crawler + chrome_users | chrome | 44K | Periodic |
| go_github_stars | go | 22K | Periodic |
| rescore_registries | All | 2.47M | On-demand |
| freshness_pipeline | Top 10K | 10K | Daily 08:30 CEST |

### API keys (available, not exposed)

| Service | Key status |
|---|---|
| CoinGecko | Active (crypto data) |
| GitHub API | Active (stars, issues, OpenSSF) |
| Backblaze B2 | Active (backups) |
| IndexNow (Bing) | Active |
| ip-api.com | Free tier (deprecated for CF-IPCountry) |
| NVD | **None** — using OSV.dev instead (free, no key) |
| HuggingFace API | **None** — no dedicated enrichment |

---

## 3. Trust Score System

### Dimensions (5, not 8)

| Dimension | Weight (standard) | Weight (website) | What it measures |
|---|---:|---:|---|
| Security | 25% | 5% | CVE count, OpenSSF, license, enrichment |
| Maintenance | 20% | 5% | Release count |
| Popularity | 20% | 70% | Downloads, stars, forks (registry-specific) |
| Community | 15% | 5% | Stars, forks, contributors |
| Quality | 20% | 15% | License, description quality |

### Grade scale

A+ ≥90, A ≥85, A- ≥80, B+ ≥75, B ≥70, B- ≥65, C+ ≥60, C ≥55, <55 = D/F

### Update mechanism

Scores updated via `rescore_registries.py` (batch UPDATE in Postgres). Triggered by:
- `com.nerq.daily-scores` LaunchAgent
- `freshness_pipeline.py` daily (detects delta ≥0.1, pushes to IndexNow)
- Manual: `python3 crawlers/rescore_registries.py --registry=all`

### Public documentation

Methodology page at `/methodology` (live). Trust score breakdown visible on every entity page for Kings. Non-Kings show overall score only.

---

## 4. Template System

### Shared components

All templates use: `NERQ_CSS`, `NERQ_NAV`, `NERQ_FOOTER` (from `nerq_design.py`), `render_hreflang()` for all 23 languages, `citation_title`/`citation_author` meta tags.

### AI citation optimization status

| Template | FAQPage | Article | pplx-verdict | ai-summary | nerq:answer |
|---|---|---|---|---|---|
| agent_safety_pages (/safe/*) | ✅ | ❌ | ✅ | ✅ | ✅ |
| pattern_routes (/was-*-hacked) | ✅ | ✅ | ✅ | ✅ | ❌ |
| pattern_routes (other 11 patterns) | ✅ | ❌ | ❌ | ❌ | ❌ |
| demand_pages (/what-is, /review) | ✅ | ❌ | ❌ | ❌ | ❌ |
| seo_programmatic (/compare, /best) | Partial | ❌ | ❌ | ❌ | ❌ |
| seo_dynamic (/trending, /model) | ❌ | ❌ | ❌ | ❌ | ❌ |

**11 of 12 pattern_routes patterns lack Article schema and AI-specific markup.** The /was-X-hacked enhancement was a pilot — the same treatment should extend to the other patterns if successful.

---

## 5. AI Distribution & Discovery

### llms.txt

175 lines. Covers all 26 registries grouped by category: Security & Privacy, Apps & Games, Developer Packages, Browser & IDE Extensions, SaaS & Website Builders, Crypto, AI & Machine Learning, Health & Supplements, Travel & Safety.

**Gap:** Does not mention HuggingFace models/datasets explicitly (32% of ChatGPT-User traffic).

### robots.txt

All major AI bots explicitly allowed: ClaudeBot, Claude-SearchBot, Claude-User, GPTBot, OAI-SearchBot, ChatGPT-User, PerplexityBot, Applebot, Applebot-Extended, Google-Extended, BraveSearch, Anthropic-ai, Claude-Web.

### IndexNow

- Daily submission: ~200K URLs
- Batch size: 100 URLs/request
- Key: `nerq2026indexnow`
- Rate limit handling: stops at HTTP 429

### MCP server

15 tools at `/.well-known/mcp.json` and `/mcp/sse`:
discover_agents, get_agent_details, agent_index_stats, nerq_crypto_rating, nerq_crypto_ndd, nerq_crypto_safety, nerq_crypto_signals, nerq_crypto_compare, find_best_agent, agent_benchmark, get_agent_stats, preflight_trust_check, kya_report, nerq_scout_status, nerq_scout_findings

### RSS feeds

- `/feed.xml`, `/rss.xml` — blog/auto-reports
- `/feed/recent` — Atom feed of recent trust score updates

### Schema.org types used

- `WebPage` + `SpeakableSpecification` (all entity pages)
- `FAQPage` (entity pages + pattern pages)
- `SoftwareApplication` / `MobileApplication` (entity pages)
- `BreadcrumbList` (entity pages)
- `Article` (/was-X-hacked only — pilot)
- `ItemList` (Kings only — trust dimension breakdown)
- `WebSite` + `SearchAction` (homepage)

---

## 6. Analytics & Measurement

### Analytics tables (SQLite analytics.db)

| Table | Rows | Purpose |
|---|---:|---|
| requests | 17.3M | All HTTP requests (30d retention) |
| preflight_analytics | ~500K | /v1/preflight API calls |
| conversion_events | ~1K | CTA clicks |
| requests_daily | ~900 | Pre-aggregated daily summaries |
| requests_daily_new_ai | ~180 | AI-specific daily aggregates |
| requests_daily_social | ~90 | Social referral aggregates |

### bot_purpose taxonomy

| Purpose | Meaning | Example bots |
|---|---|---|
| training | LLM training data | GPTBot, ClaudeBot, Bytespider |
| user_triggered | Real-time citation | ChatGPT-User, DuckAssistBot, YouBot |
| search_index | Building search index | OAI-SearchBot, PerplexityBot, Googlebot |
| internal | Our own agents | Buzz (OpenClawDeepResearch) |
| NULL | Unclassified | Other Bot, human traffic |

### Dashboards

| Dashboard | URL | Purpose |
|---|---|---|
| Citation Dashboard | /citation-dashboard | Verified AI citation metrics only |
| Flywheel Dashboard | /flywheel | Overall traffic + operations |
| Analytics Dashboard | /admin/analytics-dashboard | Raw analytics + country/language |
| Analytics Weekly | /admin/analytics-weekly | Weekly summaries |

---

## 7. Active Pilots & Experiments

| Pilot | Started | Deadline | Decision rule |
|---|---|---|---|
| M5.1 Kings hypothesis | Apr 11 | Apr 18 (7d) or Apr 25 (14d) | <1.5x = bias, 1.5-3x = partial, >3x = real |
| /was-X-hacked query-form | Apr 13 | 7d after OAI-SearchBot pickup | >50 ChatGPT-User = scale, <20 = fail |
| Freshness pipeline | Apr 13 | 4 weeks (May 11) | Perplexity-User >1.5x lift = scale to 50K |

---

## 8. Strategic Documents

### Strategy (docs/strategy/)

| File | Summary |
|---|---|
| phase-0-cloud-migration-plan.md | Active Phase 0 plan — Mac Studio → Hetzner |
| leverage-sprint-plan.md | Active sprint: Apple+AI tracking+Kings |
| nerq-vertical-expansion-master-plan-v3.md | 14→100 verticals plan |
| nerq-traffic-sprint-v2-complete.md | Traffic acquisition playbook |
| nerq-revenue-sprint-safe.md | Monetization (gated on 150K humans/day) |
| nerq-ai-citation-optimization-sprint.md | AI citation optimization |
| buzz-2.0-spec.md | Buzz autonomous agent redesign |

### ADRs (docs/adr/)

| ADR | Status |
|---|---|
| ADR-002 Expansion-first strategy | Partially superseded by ADR-003 |
| ADR-003 Cloud-native expansion-first | **Active** — authoritative architecture |
| ADR-003 Addendum #3 Sequence revision | Active — Leverage Sprint before Phase 0 |
| ADR-003 Addendum #4 Kings pivot | Active — measurement-first Kings |

---

## 9. Infrastructure

### LaunchAgents (37 total)

| Status | Count | Examples |
|---|---:|---|
| Running (PID > 0) | 5 | api, master-watchdog, chrome-users, nuget-downloads, zarq-cache |
| Idle (exit 0) | 28 | All cron-scheduled jobs between runs |
| Error (exit 1) | 4 | npm-crawler, npm-bulk-enricher, signal-warehouse, stale-scores |

### Cloud migration status

| Component | Location | Status |
|---|---|---|
| API (production traffic) | Mac Studio | Live |
| API (replica, no traffic) | Hetzner Nbg + Hel | Deployed, tested, not receiving traffic |
| PostgreSQL primary | Mac Studio | Live |
| PostgreSQL replicas | Nbg + Hel (streaming) | Active, 0 lag |
| pgBackRest backup | Nbg → Backblaze B2 | Active, PITR verified |
| DNS/Cloudflare tunnel | Mac Studio only | Not yet migrated |
| Buzz | Mac Studio (openclaw) | Not migrated |
| SQLite analytics.db | Mac Studio only | Not replicated |

---

## 10. ZARQ Status

### Data

| Table | Rows | Content |
|---|---:|---|
| zarq.crypto_ndd_alerts | 1,532,199 | NDD distress alerts |
| zarq.crypto_price_history | 1,125,978 | OHLCV price data |
| zarq.crypto_ndd_daily | 235,821 | Daily NDD scores |
| zarq.vitality_scores | 15,149 | Ecosystem vitality |
| zarq.nerq_risk_signals | 6,560 | Risk signals |
| zarq.crypto_rating_daily | 3,743 | Credit ratings |

### ZARQ traffic

ZARQ (zarq.ai) serves crypto-specific pages. Traffic mostly from Googlebot and Applebot indexing crypto token/compare pages. Dual-write active for all 12 Tier A tables.

---

## 11. Capacity Limits

### Current throughput

| Dimension | Current capacity | Bottleneck |
|---|---|---|
| Entity rendering | ~50K pages/hour (cache-served) | CPU on Mac Studio for cold renders |
| IndexNow submission | ~200K URLs/day | IndexNow rate limits (429 at ~10K/batch) |
| Language generation | 23 languages × entity count | Template rendering time (~100ms/page cold) |
| Score recalculation | ~100K entities/hour | Postgres UPDATE throughput |
| Sitemap URLs | ~293K currently | 50K/file limit (need more chunked sitemaps) |

### Top 3 constraints for 10x scale

1. **Cold render time.** Each entity page takes ~100-1,000ms to render on first access. At 2.47M entities × 23 languages × 12 patterns = 682M theoretical pages. Pre-rendering is impossible; caching is essential. Redis + Cloudflare cover this today but new patterns/languages increase the cold-render surface.

2. **IndexNow daily budget.** At 200K URLs/day and ~2.47M entities, a full resubmission takes 12 days. Adding patterns and languages multiplies the URL count. Selective push (only changed entities) is critical — the freshness pipeline addresses this.

3. **Data freshness per entity.** Only the top 10K entities get daily freshness checks. The remaining 2.46M entities have stale scores from their initial crawl. Scaling freshness to 50K+ requires faster enrichment pipelines and more API capacity (GitHub, registry APIs).
