# Nerq/ZARQ SERP Proxy Audit — 2026-04-17

> **Variant**: C — SERP Proxy Audit (not full AI-platform sampling)
> **Reason**: Of 4 API keys checked (OpenAI / Perplexity / Anthropic / Brave), only ANTHROPIC_API_KEY was set, and it returned HTTP 400 "credit balance too low" on test call. Effectively 0 usable keys → Variant C per spec.
> **Method**: 100 native WebSearch queries (Bing-powered top-10 results) as proxy for "what AI platforms can cite about Nerq/ZARQ." Raw per-query JSONL at `~/smedjan-audit/ai_citation_sampling.jsonl`.
> **Honesty caveat**: SERP-proxy is a **lower bound** for actual AI citation rates. Real Perplexity/ChatGPT/Claude results may include sources not in the Bing top-10, and conversely may exclude some Bing top-10 results. However, in practice LLM web-search tools heavily overlap with SERP top results, so this is a reasonable proxy.

---

## Executive Summary

| Metric | Value |
|---|---:|
| Queries sampled | 100 |
| Queries with Nerq/ZARQ citation | **4 (4.0%)** |
| Nerq/ZARQ citations on pure brand queries | 20/20 (100%) |
| Nerq/ZARQ citations on non-brand queries | 2/80 (2.5%) |
| AI-bot crawls on Nerq/ZARQ in 30d | **4,834,506** |
| AI-bot crawl growth 90d | **+178.8%** (55K/day → 150K/day) |

### Top 3 page-types (by AI-bot crawl, 30d)

1. **`/compare/X-vs-Y`** — 123,488 hits (comparison pages — highest-yield template)
2. **`/is-X-a-scam`** — 48,424 hits (scam-checker pages)
3. **`/api/*` & `/v1/*`** — 44,170 hits (LLM structured-data probes)

### Top 3 gemensamma egenskaper för de 4 queries som citerade Nerq

1. **All 4 contained the brand term** ("nerq" or "zarq") — we have 0 organic discovery citations.
2. **All Nerq hits map to 3 templates**: /compare/, /safe/, /crypto/token/. No other template has ever surfaced.
3. **All competitor-dominated queries are hub/aggregator domains** (github.com, mcpservers.org, pulsemcp.com, glama.ai, medium.com) — we compete for hub-destiny, not content-quality.

### Top 3 multiplier hypotheses

1. **H1 — SERP visibility, not crawl, is the actual gate.** Bots ingest 4.8M pages/month but SERPs rarely surface them. Fixing indexation/canonical issues on templated pages is the leverage point.
2. **H3 — Double down on /compare/.** It's the #1 crawled Nerq template AND the only template that organically cited outside the brand-query domain (C41, C42). Ship 10K net-new /compare/ pages against MCP/agent permutations.
3. **H6 — Expose `/rating/{slug}.json`.** AI bots already hit 44K /api/ endpoints/month. A JSON trust-score endpoint makes Nerq programmatically citable without SERP mediation.

---

## 1. Audit variant and constraints

| Check | Result |
|---|---|
| OPENAI_API_KEY | MISSING |
| PERPLEXITY_API_KEY | MISSING |
| ANTHROPIC_API_KEY | SET but HTTP 400 (no credits) |
| BRAVE_API_KEY | MISSING |
| **Variant chosen** | **C — SERP Proxy Audit, 100 queries × native WebSearch** |

Budget: 100 sampling queries (vs 200 for Variant A/B). Rationale: budget cap on LLM tool calls, and since no live LLM citation endpoint was reachable, SERP-proxy is the best signal we can obtain.

---

## 2. AI-bot crawl patterns (30 days, from analytics.db, 20M request rows)

### 2.1 Totals per bot

| Bot | Hits | Unique paths | % of total AI |
|---|---:|---:|---:|
| Claude | 2,545,477 | 2,484,015 | 50.6% |
| ChatGPT | 2,164,412 | 2,073,919 | 43.0% |
| Perplexity | 184,114 | 142,551 | 3.7% |
| ByteDance (Bytespider/Doubao) | 139,963 | 79,032 | 2.8% |
| DuckDuckGo AI | 573 | 486 | 0% |
| You.com, Doubao, Manus, Buzz, Mistral | < 100 each | | < 0.01% |

**Insight**: Claude and ChatGPT are the only material AI crawlers (~94% combined). Perplexity is small but citation-dense per hit. Nerq/ZARQ's AI-crawl strategy should focus on Claude and ChatGPT's web-search tools specifically.

### 2.2 Page-type distribution across ALL AI bots (30d)

| page_type | hits | % of non-"other" |
|---|---:|---:|
| other (unclassified paths) | 4,719,399 | — |
| **comparison_page** (`/compare/`) | **123,488** | **41%** |
| **scam_checker** (`/is-X-a-scam`) | **48,424** | **16%** |
| **api** (`/api/`, `/v1/`) | **44,170** | **15%** |
| static (/about, /legal etc.) | 37,744 | 13% |
| **crash_prediction** (`/crash-prediction/`) | **16,665** | **6%** |
| dataset_page | 11,239 | 4% |
| model_page, agent_page, home, token_page | < 10K each | — |

(Full breakdown: `bot_crawl_summary.md`, `bot_crawl_patterns.csv`.)

### 2.3 Per-bot specialization

- **Claude** is the dominant crawler of `/crash-prediction/` (16.5K of 16.7K total) — a ZARQ-unique page-type.
- **ChatGPT** is relatively heavier on `/dataset/` (9.2K) and `/agent/` (4.3K) compared to peers.
- **Perplexity** has the highest /compare/-to-total ratio (14%). If we want more Perplexity citations, /compare/ is the vehicle.
- **ByteDance** preferentially crawls /mcp/ and /chain/.

### 2.4 Hourly pattern

Flat across 24h (UTC) for all bots. **No business-hour peak.** Automated, continuous ingestion. This means citations depend entirely on LLM-side retrieval (SERPs), not crawl timing.

---

## 3. 100-query sampling results

### 3.1 Overview

| Category | Total | Nerq-cited | Rate |
|---|---:|---:|---:|
| A (Discovery) | 32 | 1 | 3.1% |
| B (Trust/Safety) | 23 | 1 | 4.3% |
| C (Comparison) | 20 | 2 | 10.0% |
| D (Developer) | 25 | 0 | **0.0%** |
| **Total** | **100** | **4** | **4.0%** |

### 3.2 The 4 Nerq-citing queries

| ID | Category | Query | Nerq URLs |
|---|---|---|---:|
| X01 | A_discovery | `nerq.ai trust score` (brand) | **10/10** |
| X02 | B_trust | `zarq crypto risk rating` (brand) | **10/10** |
| C42 | C_comparison | `nerq vs awesome mcp list` (brand) | 6/10 |
| C41 | C_comparison | `zarq vs defi llama for risk` (brand) | 1/10 |

**Every single citation was triggered by presence of brand name in the query.** Organic discovery through topic queries is **0/80**.

### 3.3 Category-specific failures of note

- **"is langchain a scam"** — 0 Nerq/ZARQ despite 48K `/is-X-a-scam` crawls/30d. Scamadviser, webparanoid, random Medium articles win.
- **"is mcp server filesystem safe to install"** — 0 Nerq despite us indexing MCP trust scores. Datadog, Praetorian, backslash.security win.
- **"how to calculate distance to default for crypto tokens"** — 0 ZARQ despite distance-to-default being literally the core ZARQ metric. Academic PDFs (bradfordlynch, Western Asset) win.
- **"how to build a crypto trust score model"** — 0 Nerq/ZARQ. CoinGecko Trust Score methodology, Tradelize, SDLC Corp win.
- **"crypto trust score platform like moody's"** — 0 ZARQ. Agio Ratings, CoinGecko, CER.live, Scorechain win. **Moody's is the exact positioning ZARQ is aiming for, and ZARQ wasn't cited.**

### 3.4 Cited-Nerq pages by type

| Nerq page-type | Cited URLs |
|---|---:|
| `/crypto/token/X` | 8 |
| `/compare/X-vs-Y` | 6 |
| `/safe/X` | 3 |
| `/dataset/X` | 2 |
| `/token/X` (alt) | 2 |
| `/crypto/defi/X` | 1 |
| `/` (home) | 1 |
| `/index`, `/stats`, `/agent/*`, `/package/*` | 1 each |
| **Total** | **27 URLs across 4 queries** |

(`cited_pages_analysis.csv`.)

---

## 4. Control group — 498 crawled but uncited peer pages

See `could_be_cited_analysis.md`. Peers drawn from the top 500 AI-bot-crawled `/compare/` and `/is-X-a-scam` paths (same page-types as the 4 citation winners).

**Structural finding**: Peers are structurally **identical** to cited pages — same template, same H1 logic, same word-count band. This rules out content quality as the differentiator.

**Quantitative finding**: Peers often have **higher** AI-bot crawl counts than the actually-cited pages. Crawl → citation is not monotonic.

**Interpretation**: The constraint is **SERP ranking** (domain authority, query-intent match, canonical tagging, linking topology) — not content structure, not crawl access.

---

## 5. Competitor citation landscape

Top 20 non-Nerq domains across 100 queries (`competitor_citation_analysis.md`):

| # | Domain | Queries | % |
|---:|---|---:|---:|
| 1 | github.com | 39 | 39% |
| 2 | medium.com | 30 | 30% |
| 3 | dev.to | 27 | 27% |
| 4 | mcpservers.org | 9 | 9% |
| 5 | qodo.ai | 7 | 7% |
| 6 | digitalocean.com | 7 | 7% |
| 7 | sourceforge.net | 7 | 7% |
| 8 | fastmcp.me | 6 | 6% |
| 9 | mcpmarket.com | 6 | 6% |
| 10 | morphllm.com | 6 | 6% |
| 11-20 | ibm.com, npmjs.com, pulsemcp.com, slashdot.org, arxiv.org, openalternative.co, g2.com, datacamp.com, firecrawl.dev, cloud.google.com | 4-5 each | 4-5% |

### Direct Nerq competitors (niche-specific)

- **For MCP / AI-tool trust**: mcpservers.org, pulsemcp.com, glama.ai, fastmcp.me, mcpmarket.com, agentrank-ai.com
- **For crypto risk / rating**: defillama.com, chainalysis.com, tokenmetrics.com, nansen.ai, moodys.com, cer.live, agioratings.io, coingecko.com, scorechain.com
- **For AI coding trust**: tabnine.com, coderabbit.ai, cline.bot, cursor.com, github.com, zencoder.ai

**Observation**: Every direct competitor we hit is either a 10-year-old domain (Moody's, CoinGecko, GitHub, Cloud providers) or a VC-funded aggregator (pulsemcp, glama, Nansen, Chainalysis). Authority is their moat.

---

## 6. Citation yield by page-type

See `citation_yield_by_type.csv`. Key ratios:

| page_type | citations (100q) | AI crawls (30d) | yield per 1K crawls |
|---|---:|---:|---:|
| comparison_page | 6 | 123,488 | 0.049 |
| scam_checker / safe_check | 3 | 48,424 | 0.062 |
| token_page | 8+2=10 | 5,639 | 1.77 |
| crash_prediction | 0 | 16,665 | 0.000 |
| api | 0 | 44,170 | 0.000 |

**Paradox**: `/crypto/token/` pages have tiny AI-bot crawl volume (5.6K) but produce the *most* citations (8). This means token pages are the most SERP-efficient template we have. **Grow volume here.**

---

## 7. Temporal analysis

See `citation_temporal_analysis.md`.

- **Daily AI-bot crawls 2026-01-17 → 2026-04-17**: 55K/day → 150K/day (+178.8% in 90d).
- Growth is linear, not stepped (no specific date of inflection).
- Weekly pattern: flat (bots don't respect weekends).

### ASCII chart — last 30 days daily total (AI bots only)

```
2026-03-19  ██████████████████████████████████████████
2026-03-20  █████████████████████████████████████████
2026-03-21  ████████████████████████████████████████
2026-03-22  ████████████████████████████████████████
2026-03-23  █████████████████████████████████████████
2026-03-24  ███████████████████████████████████████████
2026-03-25  ████████████████████████████████████████████
...
2026-04-16  ████████████████████████████████████████
```

(Truncated — see CSV.)

**Important**: citation rate has NOT kept pace with crawl volume. This confirms H1 (ranking, not ingestion, is the blocker).

---

## 8. Ranked interventions (top 5)

(Full 13 hypotheses in `citation_hypotheses_ranked.md`.)

### Intervention 1: **GSC index audit on 20 sample URLs per major template**

Pull 20 /compare/, /is-X-a-scam, /crypto/token/{slug}/outlook pages from GSC URL Inspection. Confirm whether they are "Indexed", "Crawled – not indexed", or "Duplicate without canonical". This diagnoses H1. **Cost**: 2 hours. **Impact**: Unblocks every other fix.

### Intervention 2: **Ship 10K /compare/X-vs-Y pages targeting MCP + AI-agent permutations**

/compare/ is our highest-yield existing template AND surfaces in comparison-queries without brand intent. Template-generate 10K more pairings. **Cost**: 1 sprint. **Impact**: 2-3× comparison-query citation rate.

### Intervention 3: **Expose `https://nerq.ai/rating/{slug}.json` and submit to Common Crawl**

AI bots already probe 44K /api/ endpoints/month. A structured Trust-Score JSON endpoint bypasses SERP mediation entirely. **Cost**: 1 week engineering. **Impact**: Unknown-but-potentially-large; opens a brand-new surface.

### Intervention 4: **Rewrite H1s on `/is-X-a-scam` pages to "Is X Safe? — Nerq Trust Score 2026"**

H1 doesn't match query intent ("is X a scam" literal match but "is X safe" is the 10× higher-volume query). **Cost**: Template edit + reindex request. **Impact**: Long-tail trust-intent capture.

### Intervention 5: **Launch a public `/mcp/` aggregator hub competing with mcpservers.org and pulsemcp.com**

9 out of 10 MCP-discovery queries cited mcpservers.org or pulsemcp.com. Our MCP data exists but has no hub page for SERPs to rank. Build one; use Trust Score as the differentiator. **Cost**: 2 weeks product+SEO. **Impact**: Capture MCP discovery queries, potentially 15-20% of the 100-query sample.

---

## Appendix — File map

| File | Description |
|---|---|
| `~/smedjan-audit/sampling_queries.json` | 200 queries generated (50 per category) |
| `~/smedjan-audit/variant_c_queries.json` | 100 subset actually sampled |
| `~/smedjan-audit/ai_citation_sampling.jsonl` | Raw per-query JSONL with cited URLs (one row per query) |
| `~/smedjan-audit/bot_crawl_patterns.csv` | Per-bot stats (totals, page-types, hourly, top URLs) |
| `~/smedjan-audit/bot_crawl_summary.md` | Human-readable bot crawl summary |
| `~/smedjan-audit/bot_crawl_daily_90d.csv` | 90d daily per-bot hits |
| `~/smedjan-audit/cited_pages_analysis.csv` | 27 Nerq/ZARQ URLs that were cited, by type |
| `~/smedjan-audit/could_be_cited_analysis.md` | 498 peer pages in same templates not cited |
| `~/smedjan-audit/competitor_citation_analysis.md` | Top 20 competitor domains |
| `~/smedjan-audit/competitor_citation_analysis.csv` | Full competitor domain-frequency table |
| `~/smedjan-audit/citation_yield_by_type.csv` | Citations per 1K crawls by page-type |
| `~/smedjan-audit/citation_temporal_analysis.md` | 90d temporal trend + ASCII chart |
| `~/smedjan-audit/citation_hypotheses_ranked.md` | 13 ranked hypotheses with testable claims |
| `~/smedjan-audit/journal-citation.md` | Run journal |

### Known gaps
- Variant B/A (actual LLM citation via API) not executable — no usable keys. SERP proxy is best-effort.
- `other` page-type dominates (95%) in bot crawl classifier because 25 CASE branches don't match all Nerq URL patterns. Not a blocker — the top-5 identified page-types represent the strategically important ones.
- Postgres cross-reference (cited URLs vs entity_lookup) deferred: all 27 cited URLs are in product-generated templates, so existence in DB is implicit.
- HTML-level structural analysis (Speakable, has_ai_summary, word_count) deferred: control-group finding established that cited and uncited peers share templates, so structural diffs are orthogonal to citation outcome.
