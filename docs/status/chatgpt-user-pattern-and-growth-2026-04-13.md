# ChatGPT-User Pattern & Growth Analysis — 2026-04-13

**Period:** 30 days (2026-03-14 → 2026-04-13)
**Total ChatGPT-User requests:** 32,269
**Unique IPs (proxy for unique user queries):** ~600/day stable

---

## DEL A — Pattern Analysis

### 1. URL Pattern Distribution

| Pattern | Count | % | Interpretation |
|---|---:|---:|---|
| `/dataset/*` | 6,132 | **19.0%** | "Is this dataset safe/good?" |
| homepage `/` | 4,775 | **14.8%** | ChatGPT checking what Nerq is |
| `/model/*` | 4,086 | **12.7%** | "Is this model safe?" |
| `/profile/*` | 3,784 | **11.7%** | "Tell me about this project" |
| `/safe/*` | 3,381 | **10.5%** | "Is X safe?" (core trust query) |
| `/agent/*` | 2,635 | **8.2%** | "Is this AI agent trustworthy?" |
| `/compare/*` | 2,191 | **6.8%** | "X vs Y — which is safer?" |
| `/crypto/*` | 1,360 | **4.2%** | "Is this DeFi/token safe?" |
| `/package/*` | 945 | **2.9%** | Package trust check |
| `/token/*` | 715 | **2.2%** | Crypto token lookup |
| `/is-*-safe` | 588 | **1.8%** | Direct safety question URL |
| localized | 473 | **1.5%** | Non-English queries |
| `/org/*` | 206 | **0.6%** | Organization lookup |
| `/npm/*` | 75 | **0.2%** | npm package check |
| `/kya/*` | 28 | **0.1%** | Know Your Agent report |
| `/best/*` | 2 | **0.0%** | Rankings (almost never) |

**Key insight:** Datasets (19%) and models (13%) dominate — ChatGPT users ask about HuggingFace assets more than traditional software. The `/safe/*` pattern is only 10.5%, meaning most ChatGPT-User traffic uses Nerq-specific URL patterns that map to HuggingFace entities, not the traditional "is X safe" pattern.

### 2. Top 20 Winning URLs

| URL | Count | Category |
|---|---:|---|
| `/` | 4,773 | Homepage (ChatGPT validating the source) |
| `/agent/083f89ad...` | 99 | Specific agent by UUID |
| `/model/deepseek-v3-2-reap...` | 79 | DeepSeek model safety |
| `/dataset/wildchat-1m` | 68 | WildChat dataset |
| `/npm/express` | 66 | Express.js trust score |
| `/profile/eleutherai-lm-evaluation-harness` | 54 | EleutherAI project |
| `/safe/trulens` | 51 | TruLens observability tool |
| `/token/goplus-security` | 50 | GoPlus Security token |
| `/dataset/wildchat-4-8m` | 49 | WildChat dataset variant |
| `/model/h3-proxy` | 49 | H3 Proxy model |
| `/safe/davideaststitch-mcp` | 47 | MCP server trust check |
| `/compare/obsidian-smart-connections-vs-posthog` | 46 | Plugin comparison |
| `/profile/waybarrios-vllm-mlx` | 44 | vLLM MLX project |
| `/dataset/convomem` | 41 | ConvoMem dataset |
| `/crypto/defi/atrium` | 32 | DeFi protocol safety |
| `/safe/replit` | 29 | Replit trust score |
| `/safe/make` | 34 | Make.com trust score |
| `/safe/weaviate` | 30 | Weaviate vector DB |
| `/safe/tiktok` | 20 | TikTok safety |
| `/safe/expensify` | 27 | Expensify trust |

**Pattern:** Users ask ChatGPT about AI/ML tools, datasets, models, and MCP servers. These are developer-oriented queries. The traditional consumer queries ("is TikTok safe?") are present but secondary.

### 3. Top 20 Losing URLs (heavily trained, zero user queries)

| URL | Training crawls (7d) | User queries | Gap |
|---|---:|---:|---|
| `/safe/puppeteer-table-parser` | 7 | 0 | Obscure npm package |
| `/safe/pure-orm` | 6 | 0 | Niche ORM library |
| `/safe/com-google-android-apps-maps` | 5 | 0 | Google Maps Android |
| `/safe/storybook-react` | 5 | 0 | Storybook React |
| `/safe/oracle-oracledevtools` | 5 | 0 | Oracle DevTools |

**Pattern for losers:** Obscure packages that nobody asks about by name. Training crawlers crawl everything systematically; user queries are highly selective for trending/relevant tools.

### 4. Hourly Distribution (UTC)

```
00-05:  1,134-1,312/h  — US evening / Asia morning
06-09:  1,413-1,588/h  — US morning / Europe afternoon (PEAK)
10-14:  1,276-1,503/h  — US workday
15-20:  1,381-1,434/h  — US afternoon / Europe evening
21-23:  1,017-1,267/h  — overnight minimum
```

**Flat distribution** — no strong geographic concentration. Peaks during US morning (06-09 UTC = 8-11 AM EST). The flatness suggests global user base, not US-only.

### 5. Day-of-Week Distribution

| Day | Avg/week |
|---|---:|
| Mon | 1,262 |
| Sun | 1,241 |
| Sat | 1,154 |
| Fri | 1,118 |
| Tue | 1,107 |
| Wed | 1,105 |
| Thu | 1,082 |

**Nearly flat across all days.** No weekend drop — consistent with ChatGPT being used 24/7 by individuals, not primarily by businesses.

### 6. Unique Queries Proxy

| Metric | Value |
|---|---:|
| Average unique IPs/day | ~600 |
| Average requests/IP/day | 2.0-2.1 |
| Max unique IPs/day | 717 (Mar 23) |
| Min unique IPs/day | 400 (Apr 13, partial) |

**~600 unique user queries per day**, each triggering ~2 page fetches (homepage + entity page). This is NOT 200 queries repeated — it's 600 distinct users asking distinct questions.

### 7. Correlation with Training/Search

For top 25 ChatGPT-User URLs:

| URL | User-triggered | GPTBot training | OAI-SearchBot |
|---|---:|---:|---:|
| `/` | 4,776 | 45 | 17 |
| `/agent/083f89ad...` | 99 | 0 | 0 |
| `/model/deepseek-v3-2...` | 79 | 0 | 0 |
| `/dataset/wildchat-1m` | 68 | 1 | 1 |
| `/npm/express` | 66 | 0 | 1 |

**Zero correlation between training crawl volume and user-triggered volume.** The pages that ChatGPT-User fetches are NOT the same pages that GPTBot crawls heavily. ChatGPT-User responds to real-time user questions — it goes wherever the user's question points.

**OAI-SearchBot also shows zero correlation** — it indexes broadly but user queries target specific entities.

---

## DEL B — Growth Curve

### Daily Volume

```
Mar 14:    61  ← first appearance
Mar 15:   109
Mar 17:   297  ← 4.9x in 3 days
Mar 20:   647
Mar 21: 1,198  ← INFLECTION: 2x overnight
Mar 23: 1,647  ← peak
Mar 24: 1,496  ← plateau begins
Mar 28: 1,169  ← slight dip
Apr 01: 1,360  ← stable ~1,200-1,400
Apr 04: 1,026  ← weekend dip
Apr 10: 1,310  ← stable
Apr 12: 1,023  ← CF incident impact
Apr 13:   647  ← partial day
```

### Inflection Points

| Date | Event | Volume change | Likely cause |
|---|---|---|---|
| **Mar 14** | First appearance | 0 → 61 | OpenAI started including nerq.ai in ChatGPT Search results |
| **Mar 17-20** | Rapid growth | 61 → 647 (10.6x) | Index expansion — more pages discoverable |
| **Mar 21** | Step change | 647 → 1,198 (1.85x overnight) | OAI-SearchBot spike same day (2,120). OpenAI re-indexed and promoted Nerq significantly |
| **Mar 23** | Peak | 1,647 | PerplexityBot also spiked (25,545). Multiple AI search engines indexed aggressively |
| **Mar 24** | Plateau | 1,647 → 1,496 | Natural equilibrium — demand-driven, not supply-driven |
| **Apr 12** | Drop | 1,310 → 1,023 | Cloudflare Workers AI incident |

### Correlation with Our Changes

| Date | Our change | ChatGPT-User impact |
|---|---|---|
| Mar 18 | Entity pages launched at scale (18K+ registry entities) | Possible cause of Mar 17-20 ramp |
| Mar 21 | Sitemap update + IndexNow submission | **Likely cause of Mar 21 step change** — OAI-SearchBot indexed 2,120 pages that day |
| Mar 23 | No specific deploy | Organic peak from Mar 21 index expansion |
| Apr 10 | M4a Apple meta tags + Schema.org enhancements | No visible ChatGPT-User impact |
| Apr 11 | M5.1 Kings experiment (IndexNow randomized) | No immediate impact (Apr 11: 1,160, normal) |

**The Mar 21 step change correlates with OAI-SearchBot activity**, not a specific git commit. OpenAI's search indexer discovered a large batch of pages and promoted them in ChatGPT Search results. This drove user queries.

---

## Combined Analysis

### What winning pages have in common

1. **They answer a specific question** — "Is X safe?", "What is the trust score for X?", "X vs Y"
2. **They cover trending AI/ML entities** — DeepSeek, WildChat, TruLens, MCP servers
3. **They have structured data** — FAQPage JSON-LD, trust score, grade
4. **They exist at a predictable URL** — `/safe/{slug}`, `/dataset/{slug}`, `/model/{slug}`
5. **They are NOT localized** — only 1.5% of ChatGPT-User traffic goes to non-English pages

### What losing pages have in common

1. **Obscure entities** nobody asks about by name
2. **No question-shaped URL** — `/safe/pure-orm` doesn't match any user question pattern
3. **No trending context** — not mentioned in recent discussions, papers, or news

### Top 3 acceleration levers to test

1. **Expand HuggingFace coverage** — datasets (19%) and models (13%) are the biggest ChatGPT-User categories. We currently index ~200K HuggingFace assets. Adding structured safety analysis to more models/datasets would directly serve more user queries.

2. **Create "is it safe" pages for trending AI tools** — MCP servers, AI coding assistants, and agentic platforms dominate the top URLs. Proactively creating `/safe/` pages for trending tools (from HN, GitHub trending, ProductHunt) within 24h of launch would capture query demand while it peaks.

3. **Optimize for ChatGPT Search specifically** — Our `/best/` pages get essentially zero ChatGPT-User traffic (2 requests in 30 days). ChatGPT users ask entity-specific questions, not "best X" questions. Invest in entity depth (better descriptions, more dimensions) rather than ranking pages.
