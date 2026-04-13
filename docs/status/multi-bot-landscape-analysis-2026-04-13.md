# Multi-Bot Landscape Analysis — 2026-04-13

**Period:** 30 days. **Source:** analytics.db requests table.

---

## TIER A — Deep Analysis

### A1. Applebot (search_index)

**Volume:** ~293K/day baseline (8.8M/30d). Largest single bot.

**URL pattern distribution:**

| Pattern | Count | % |
|---|---:|---:|
| localized (/{lang}/*) | 2,195,475 | **86.8%** |
| `/safe/*` | 58,283 | 2.3% |
| `/is-*` | 40,839 | 1.6% |
| `/compare/*` | 25,763 | 1.0% |
| `/alternatives/*` | 9,973 | 0.4% |
| `/what-is/*` | 9,041 | 0.4% |
| `/review/*`, `/pros-cons/*`, `/who-owns/*`, etc. | ~58,000 | 2.3% |
| other | 13,826 | 0.5% |

**Critical finding: 86.8% of Applebot traffic goes to localized pages.** This is radically different from ChatGPT-User (1.5% localized). Apple is indexing the entire 23-language corpus systematically.

**Language distribution (remarkably even):**

| Language | Count | % | Language | Count | % |
|---|---:|---:|---|---:|---:|
| en | 239,340 | 9.5% | vi | 118,559 | 4.7% |
| fr | 131,129 | 5.2% | th | 115,456 | 4.6% |
| it | 128,954 | 5.1% | zh | 111,732 | 4.4% |
| da | 128,220 | 5.1% | ar | 109,253 | 4.3% |
| nl | 127,317 | 5.0% | de | 108,276 | 4.3% |
| es | 122,827 | 4.9% | sv | 104,222 | 4.1% |
| pt | 119,680 | 4.7% | tr | 103,690 | 4.1% |
| ko | 119,140 | 4.7% | ja | 99,459 | 3.9% |

**All 23 languages indexed.** English is only 9.5% — Apple treats the localized corpus as equally important. This is the strongest signal that our 23-language investment is paying off with at least one major platform.

**Hourly distribution:** Flat (68K-118K/h). No geographic concentration — Apple's crawler infrastructure is global.

**Unique Apple characteristics:**
- Only bot that indexes ALL 23 languages at significant volume
- Focuses on entity pages (`/safe/*`, `/is-*`) and question patterns
- Does NOT crawl `/model/*`, `/dataset/*`, `/profile/*` (HuggingFace entities) — only 225 model hits vs ChatGPT-User's 4,086
- Stable volume — unaffected by Cloudflare incident

### A2. OAI-SearchBot (search_index)

**Volume:** ~2,248/day (67K/30d).

**URL pattern distribution:**

| Pattern | Count | % |
|---|---:|---:|
| localized | 25,788 | **38.2%** |
| `/is-*` | 6,939 | 10.3% |
| `/safe/*` | 5,019 | 7.4% |
| other (question patterns) | 5,420 | 8.0% |
| `/alternatives/*` | 3,034 | 4.5% |
| `/compare/*` | 2,182 | 3.2% |
| `/dataset/*` | 1,934 | 2.9% |
| `/token/*` | 1,583 | 2.3% |
| `/model/*` | 1,114 | 1.7% |
| `/profile/*` | 1,000 | 1.5% |
| `/predict/*` | 765 | 1.1% |
| `/crypto/*` | 702 | 1.0% |
| `/guide/*` | 602 | 0.9% |

**OAI-SearchBot indexes broadly** — all URL patterns, all categories. It's the most diverse indexer. Unlike Applebot, it indexes HuggingFace entities (datasets, models, profiles) significantly.

**Correlation with ChatGPT-User:** OAI-SearchBot is the PIPELINE for ChatGPT-User. When OAI-SearchBot indexes a page, ChatGPT-User may cite it within hours. But the per-URL correlation is near zero — OAI-SearchBot indexes systematically, ChatGPT-User responds to specific user questions.

---

## TIER B — Medium Analysis

### B1. DuckAssistBot (user_triggered)

**Volume:** 16/day (491/30d). N=491 — **low but stable.**

**Top URLs:** `/compare/*` dominates (7 of top 15). DuckAssist users compare tools.

**Unique pattern:** Compare pages are the #1 content type. DuckAssist is the only bot where compare pages dominate over entity pages. OpenAI users ask "is X safe?"; DuckDuckGo users ask "X vs Y?".

**Trend:** Stable. 135 (prev 7d) → 180 (last 7d) = slight growth.

### B2. Perplexity-User (user_triggered)

**Volume:** 7/day (218/30d). N=218 — **low, caution on patterns.**

**Top URLs:** Crypto-heavy. DeFi and token pages dominate top 15. Perplexity users ask about crypto more than software safety.

**Trend:** Stable. 64 → 75 (last 7d).

### B3. YouBot (user_triggered)

**Volume:** 5/day (162/30d). N=162 — **low.**

**Top URLs:** Dataset-heavy. `salesforce-lotsa-data` (10), `2wikimultihopqa` (8). You.com users research ML datasets.

**Trend:** **Growing.** 32 (prev 7d) → 104 (last 7d) = **3.25x growth**. YouBot is the fastest-growing user-triggered bot.

---

## TIER C — Observation & Tracking

| Bot | 30d total | Last 7d | Prev 7d | Trend | Status |
|---|---:|---:|---:|---|---|
| Claude (user_triggered) | 48 | 12 | 13 | Stable | Worth monitoring — Anthropic may expand |
| Doubao (user_triggered) | 22 | 5 | 4 | Stable | Chinese market signal |
| Manus (user_triggered) | 10 | 2 | 3 | Stable | Agentic browser — future potential |
| Mistral (user_triggered) | 1 | 1 | 0 | First appearance | Too early |
| Buzz (internal) | 4 | 0 | 0 | One-time | Exclude from metrics |
| Bing (search_index) | 1,590,373 | 513K | 428K | **Growing 20%** | Drives ChatGPT Search |
| Google (search_index) | 454,048 | 111K | 76K | **Growing 46%** | Standard SEO |
| Perplexity (search_index) | 178,029 | 55K | 54K | Stable | Feeds Perplexity-User |

**Bing is growing 20% week-over-week** — significant because Bing powers ChatGPT Search. More Bing indexing = more pages available to ChatGPT-User.

**Google is growing 46% week-over-week** — accelerating. Likely responding to our 410-fix (Apr 7) and content quality improvements.

---

## SYNTHESIS

### 1. Comparison Matrix

| Bot | Vol/day | Unique queries/day | Top category | Growing? | Concentration risk |
|---|---:|---:|---|---|---|
| Applebot | 293K | N/A (index) | Localized entity pages | Stable | LOW (Apple-independent) |
| ChatGPT-User | 1,074 | ~600 | Datasets, models | Stable | **HIGH (52% of user queries)** |
| OAI-SearchBot | 2,248 | N/A (index) | Diverse | Stable | Tied to ChatGPT |
| Bing | 53K | N/A (index) | Diverse | **+20%/wk** | Supports ChatGPT |
| Google | 15K | N/A (index) | Diverse | **+46%/wk** | Supports organic |
| Perplexity-User | 7 | ~5 | Crypto/DeFi | Stable | Low |
| DuckAssistBot | 16 | ~15 | Compare pages | Stable | Low |
| YouBot | 5 | ~5 | Datasets | **+225%/wk** | Low |
| Claude-User | 2 | ~2 | Mixed | Stable | Low |

### 2. Platform-Unique Preferences

**ChatGPT-User picks up what others don't:**
- HuggingFace entities (datasets 19%, models 13%) — no other user-triggered bot indexes these at scale
- The homepage (15%) — ChatGPT validates source authority before citing

**Applebot picks up what others don't:**
- All 23 localized languages equally (86.8% of traffic)
- English is only 9.5% of Apple's crawl — every other bot is 80%+ English
- Question-pattern URLs (`/who-owns/*`, `/was-*-hacked`) at significant volume

**Content invisible to ALL platforms:**
- `/best/*` ranking pages: 155 Apple, 41 OAI-SearchBot, 2 ChatGPT-User, 0 others. Rankings are essentially ignored by all AI platforms.
- `/npm/*`, `/pypi/*`, `/crates/*` registry hub pages: near-zero across all bots

### 3. Portfolio Analysis

**User-triggered query distribution (30d):**

| Platform | Queries/day | % of total |
|---|---:|---:|
| ChatGPT-User | 1,074 | **95.8%** |
| DuckAssistBot | 16 | 1.4% |
| Perplexity-User | 7 | 0.6% |
| YouBot | 5 | 0.4% |
| Claude-User | 2 | 0.2% |
| All others | <5 | <0.5% |

**Concentration risk: EXTREME.** 95.8% of user-triggered queries come from ChatGPT. If ChatGPT stops citing Nerq tomorrow, we lose ~1,020 daily user queries. Remaining: ~47/day.

**If ChatGPT drops to zero, what we have:**
- 47 user-triggered queries/day from other platforms
- 293K/day Applebot indexing (potential future Apple Intelligence citations)
- 178K/day PerplexityBot indexing (but only 7 user-triggered queries/day)
- 54K/day Bing indexing (future Copilot potential)
- Google organic search traffic (~260 visits/day from SERP)

### 4. Recommendations

**Top 3 platforms to invest in (beyond ChatGPT):**

1. **Apple Intelligence / Siri** — 293K/day indexing, 86.8% localized. Apple is our largest bot by volume and the only one systematically indexing all 23 languages. When Apple Intelligence launches search-citation features (Siri answers, Safari Suggestions), Nerq is positioned to be cited in 23 languages. **Investment:** Maintain Apple meta tags, ensure all localized pages have Schema.org, monitor for Apple Intelligence user-triggered bot appearance.

2. **Perplexity** — 178K/day indexing but only 7 user-triggered queries. The gap between indexing and citation is the largest of any platform. **Investment:** Study Perplexity's citation criteria (they favor pages with clear, concise answers near the top). Add Perplexity-specific `<meta name="pplx-verdict">` blocks. Our existing `pplx-verdict` CSS class is a start but may not be sufficient.

3. **You.com** — Only 5/day but **growing 225% week-over-week**. They focus on datasets and ML tools — overlap with our HuggingFace corpus. **Investment:** Ensure YouBot is explicitly allowed in robots.txt (currently covered by wildcard). Monitor growth trajectory — if 225%/wk sustains, reaches ChatGPT-User levels in ~2 months.

**Top 3 underutilized content types:**

1. **Localized compare pages** — Apple indexes localized entity pages massively but `/compare/*` only has 25K Apple hits vs 2.2M localized entity pages. Adding localized compare pages would give Apple more question-shaped content to index in all 23 languages.

2. **Crypto/DeFi for Perplexity** — Perplexity-User's top URLs are crypto-heavy. We have ZARQ crypto data but it's not well-connected to the Perplexity citation pipeline. Create `pplx-verdict`-style answer blocks on ZARQ token pages.

3. **Dataset safety pages** — ChatGPT-User's #1 category (19%), but datasets lack the rich safety analysis that `/safe/` entity pages have. Adding trust score analysis to dataset pages would serve existing demand.

**Blind spots:**

- **Gemini-User:** Zero traffic. Either Google doesn't use a separate user-triggered bot (it may use Googlebot for both), or Gemini doesn't cite Nerq. No action needed — Google's organic indexing is growing +46%/wk regardless.
- **Claude-User at 2/day:** Anthropic's search citation feature is either not live, not citing Nerq, or using a different mechanism. The 48 total requests in 30 days are mostly Claude Code CLI users, not Claude Search.
- **Brave:** Zero BraveSearch crawler visits. Brave indexes via Bing. No direct action needed.
