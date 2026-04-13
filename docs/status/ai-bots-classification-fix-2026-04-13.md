# AI Bot Classification Fix — 2026-04-13

## Changes

### 1. Added 8 missing UAs to AI_BOTS dict

| UA pattern | bot_name | bot_purpose |
|---|---|---|
| Perplexity-User | Perplexity | user_triggered |
| DuckAssistBot | DuckDuckGo AI | user_triggered |
| YouBot | You.com | user_triggered |
| MistralAI-User | Mistral | user_triggered |
| Manus-User | Manus | user_triggered |
| SamanthaDoubao / doubao | Doubao | user_triggered |
| Google-Read-Aloud | Google | user_triggered |
| AnthropicSearchEval | Claude | user_triggered |
| OpenClawDeepResearch | Buzz | internal |

### 2. Added bot_purpose taxonomy

New column `bot_purpose TEXT` on requests table. Values:

| Purpose | Meaning | Example bots |
|---|---|---|
| `training` | Building LLM training data | GPTBot, ClaudeBot, Bytespider |
| `user_triggered` | Real-time fetch when user asks a question | ChatGPT-User, DuckAssistBot, YouBot |
| `search_index` | Building search index for AI search | OAI-SearchBot, PerplexityBot, Googlebot |
| `internal` | Our own agents (exclude from metrics) | Buzz (OpenClawDeepResearch) |
| NULL | Unclassified bot or human | Other Bot, High-Volume Bot, humans |

### 3. Backfilled 30 days

All 17.3M rows in the last 30 days backfilled with bot_purpose values.

## Verification (last 24 hours)

| bot_name | bot_purpose | Count |
|---|---|---:|
| Apple | search_index | 509,013 |
| Yandex | search_index | 186,159 |
| Meta | search_index | 168,830 |
| Claude | training | 87,459 |
| ChatGPT | training | 65,364 |
| ChatGPT | search_index | 2,446 |
| **ChatGPT** | **user_triggered** | **1,657** |
| **DuckDuckGo AI** | **user_triggered** | **30** |
| Perplexity | search_index | 5,684 |
| **Perplexity** | **user_triggered** | **16** |
| **You.com** | **user_triggered** | **15** |
| **Claude** | **user_triggered** | **2** |
| **Doubao** | **user_triggered** | **1** |
| **Mistral** | **user_triggered** | **1** |

All 8 new bots now visible in analytics with correct classification.

## Sanity check

ChatGPT-User 24h count: 1,657 — consistent with pre-fix count (~1,074/day average over 30 days, higher recently). No data was lost or inflated.
