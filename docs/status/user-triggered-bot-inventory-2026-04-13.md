# User-Triggered AI Bot Inventory — 2026-04-13

**Source:** analytics.db, raw user_agent column, last 30 days (17.3M total requests)

---

## Tier 1 — Active User-Triggered Bots (citation = someone asked a question)

| Bot | UA pattern | 30d requests | Daily avg | IPs | Type |
|---|---|---:|---:|---:|---|
| **ChatGPT-User** | `ChatGPT-User/1.0; +openai.com/bot` | 32,231 | **1,074** | 1,428 | User query fetch |
| **Perplexity-User** | `Perplexity-User/1.0; +perplexity.ai` | 218 | **7** | 8 | User query fetch |
| **Claude-User** (browser) | `Claude-User/1.0; +anthropic.com` | 20 | <1 | 1 | AI-mediated browse |
| **Claude-User** (code) | `Claude-User (claude-code/2.1.x)` | 28 | <1 | ~20 | Dev tool fetch |
| **MistralAI-User** | `MistralAI-User/1.0; +docs.mistral.ai` | 1 | <1 | 1 | User query fetch |
| **Manus-User** | `Manus-User/1.0` | 10 | <1 | 10 | Agentic browser |

### ChatGPT-User daily trend (primary signal)

```
Mar 14-17:  61 → 297/day   (ramp-up phase)
Mar 18-20:  374 → 647/day  (growing)
Mar 21-27:  1,198 → 1,647  (plateau at ~1,300-1,600/day)
Mar 28-Apr 11: 1,023-1,470 (stable baseline ~1,200/day)
Apr 12-13:  1,023 → 615    (dropped — Cloudflare incident impact)
```

**ChatGPT-User grew 20x in 2 weeks** (Mar 14 → Mar 27) then stabilized at ~1,200/day. Currently depressed to ~600-1,000/day from the Cloudflare incident.

### ChatGPT-User top URLs

| URL | Count | Interpretation |
|---|---:|---|
| `/` (homepage) | 4,770 | ChatGPT checking what Nerq is |
| `/agent/083f89ad...` | 99 | Specific agent lookup |
| `/model/deepseek-v3-2-reap...` | 79 | AI model safety check |
| `/dataset/wildchat-1m` | 68 | Dataset safety check |
| `/npm/express` | 66 | Package safety check |
| `/safe/trulens` | 51 | Direct entity trust query |

**Pattern:** Users ask ChatGPT "is X safe?" or "what is the trust score for X?" and ChatGPT fetches the answer from nerq.ai. The homepage dominance (4,770) suggests ChatGPT first validates the site, then fetches entity pages.

### ChatGPT-User country distribution

| Country | Count | % |
|---|---:|---:|
| US | 13,157 | 41% |
| PL | 3,741 | 12% |
| JP | 2,121 | 7% |
| AU | 1,801 | 6% |
| ES | 1,506 | 5% |
| NZ | 1,318 | 4% |
| BR | 1,291 | 4% |
| IN | 1,201 | 4% |
| KR | 1,148 | 4% |

This distribution reflects ChatGPT's user base, not bot infrastructure. US dominates as expected.

---

## Tier 2 — Search/Index Bots (proxy citation signal)

| Bot | UA pattern | 30d requests | Daily avg | Type |
|---|---|---:|---:|---|
| **PerplexityBot** | `PerplexityBot/1.0` | 177,932 | **5,931** | Index crawler |
| **OAI-SearchBot** | `OAI-SearchBot/1.3` | 67,450 | **2,248** | ChatGPT Search index |
| **DuckAssistBot** | `DuckAssistBot/1.2` | 491 | **16** | DuckDuckGo AI Assist |
| **DuckDuckBot** | `DuckDuckBot/1.1` | 243 | **8** | DDG index crawler |
| **YouBot** | `YouBot/1.0; +docs.you.com` | 162 | **5** | You.com search index |

### OAI-SearchBot daily trend

```
Mar 14-17:   109-512/day    (early)
Mar 21-22:   2,120-5,637    (massive spike — indexing phase)
Mar 23-27:   3,221-4,555    (steady high)
Apr 1-11:    1,468-3,235    (stabilized ~2,000/day)
Apr 12-13:   856-1,584      (dropped — Cloudflare)
```

**OAI-SearchBot** is OpenAI's dedicated search indexer for ChatGPT Search. It runs independently of ChatGPT-User — it indexes pages proactively so ChatGPT Search can serve results instantly.

---

## Tier 3 — Discovered New Bots (not currently classified)

| Bot | UA | 30d count | Assessment |
|---|---|---:|---|
| **SamanthaDoubao** | `SamanthaDoubao/1.27-2.6.8` + `doubao` app | 20 | ByteDance's Doubao AI assistant (China) |
| **Manus-User** | `Manus-User/1.0` | 10 | Manus AI — agentic browser platform |
| **Google-Read-Aloud** | `Google-Read-Aloud` | 79 | Google's accessibility reader |
| **research-bot** | `research-bot/1.0` | 83 | Generic research crawler |
| **OpenClawDeepResearch** | `OpenClawDeepResearch/0.1` | 4 | **Buzz!** (openclaw.ai = our own agent) |
| **naga-agent** | `naga-agent/5.0.0 Electron` | 1 | Desktop AI agent |
| **AnthropicSearchEval** | `AnthropicSearchEval/1.0` | 1 | Anthropic evaluation probe |
| **AINewsAgent** | `AINewsAgent/1.0` | 1 | News aggregation bot |

**SamanthaDoubao** is particularly interesting — it's ByteDance's Doubao AI assistant making user-triggered fetches (20 requests from ~15 unique IPs). The `doubao` mobile app UA variant confirms these are real user queries in China.

---

## Ratio Analysis: User-Triggered vs Training Crawlers

| AI company | Training crawler | User-triggered | Ratio (user:crawler) |
|---|---|---|---|
| OpenAI | GPTBot: 2,575,000 | ChatGPT-User: 32,231 | **1:80** |
| OpenAI | — | OAI-SearchBot: 67,450 | (search index) |
| Anthropic | ClaudeBot: 2,289,000 | Claude-User: 48 | **1:47,688** |
| Perplexity | PerplexityBot: 177,932 | Perplexity-User: 218 | **1:816** |
| ByteDance | Bytespider: 175,000 | Doubao: 20 | **1:8,750** |
| DuckDuckGo | DuckDuckBot: 243 | DuckAssistBot: 491 | **2:1** (!) |
| You.com | — | YouBot: 162 | (no separate crawler) |
| Mistral | — | MistralAI-User: 1 | (just started) |

**Key insight:** DuckDuckGo is the ONLY provider where user-triggered fetches exceed index crawls (2:1). This means DuckAssist is actively fetching Nerq content to answer user queries, without building a large index first.

**OpenAI's ratio is 1:80** — for every 80 GPTBot crawl requests, 1 actual user query hits nerq.ai via ChatGPT-User. This means ~1,074 real people per day ask ChatGPT a question that results in nerq.ai being fetched.

**Anthropic's ratio is 1:47,688** — Claude-User is essentially absent. Either Anthropic's search feature doesn't cite nerq.ai, or they use a different mechanism (no User-Agent header, or fetching via a proxy).

---

## Classification Gaps (what analytics.py misses)

| UA | Current classification | Should be |
|---|---|---|
| `ChatGPT-User/1.0` | is_ai_bot=1, bot_name='ChatGPT' | ✅ Correct |
| `OAI-SearchBot/1.3` | is_ai_bot=1, bot_name='ChatGPT' | ✅ Correct |
| `Perplexity-User/1.0` | Not in AI_BOTS dict | ❌ Should be bot_name='Perplexity' |
| `PerplexityBot/1.0` | is_ai_bot=1, bot_name='Perplexity' | ✅ Correct |
| `DuckAssistBot/1.2` | Not in AI_BOTS dict | ❌ Should be bot_name='DuckDuckGo AI' |
| `YouBot/1.0` | Not in AI_BOTS dict | ❌ Should be bot_name='You.com' |
| `Claude-User (claude-code/...)` | Not caught | ❌ Should be bot_name='Claude' |
| `MistralAI-User/1.0` | Not in AI_BOTS dict | ❌ Should be bot_name='Mistral' |
| `Manus-User/1.0` | Not caught | ❌ Should be bot_name='Manus' |
| `SamanthaDoubao/*` | Not caught | ❌ Should be bot_name='Doubao' |
| `Google-Read-Aloud` | Not caught | ❌ Should be bot_name='Google' |

**8 user-triggered bot UAs are not properly classified.** Combined volume: ~1,000 requests/30d (small but growing).

## Recommended AI_BOTS additions

```python
# User-triggered AI bots (citation signals)
'Perplexity-User': 'Perplexity',
'DuckAssistBot': 'DuckDuckGo AI',
'YouBot': 'You.com',
'Claude-User': 'Claude',
'MistralAI-User': 'Mistral',
'Manus-User': 'Manus',
'SamanthaDoubao': 'Doubao',
'doubao': 'Doubao',
'Google-Read-Aloud': 'Google',
'AnthropicSearchEval': 'Claude',
```
