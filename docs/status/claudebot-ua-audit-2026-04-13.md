# ClaudeBot UA Audit — 2026-04-13

**Scenario: C** — Claude-User + Claude-SearchBot traffic is genuinely tiny. The crawl rate issue is 100% about ClaudeBot/1.0 volume (Anthropic-side).

---

## Fas 1 — Raw UA Strings (last 14 days)

| User-Agent | Requests | bot_name | is_bot | is_ai_bot | Type |
|---|---:|---|---|---|---|
| `ClaudeBot/1.0; +claudebot@anthropic.com` | 2,289,036 | Claude | 1 | 1 | Crawler |
| `Claude-User (claude-code/2.1.92; ...)` | 8 | *(empty)* | 0 | 0 | Human via Claude Code |
| `Claude-User (claude-code/2.1.87; ...)` | 5 | *(empty)* | 0 | 0 | Human via Claude Code |
| `Claude-User/1.0; +Claude-User@anthropic.com` | 3 | *(empty)* | 0 | 0 | AI-mediated browser |
| `Claude-User (claude-code/2.1.85-97; ...)` | 8 | *(empty)* | 0 | 0 | Human via Claude Code |
| `AnthropicSearchEval/1.0` | 1 | *(empty)* | 0 | 0 | Search eval probe |
| **Claude-SearchBot** | **0** | — | — | — | **Not seen** |

**Total Claude/Anthropic: 2,289,062.** Of which 99.999% is ClaudeBot/1.0.

---

## Fas 2 — Analytics Pipeline Classification

**`analytics.py:49-55` AI_BOTS dict:**
```python
'ClaudeBot': 'Claude',      # ← matches ClaudeBot/1.0 UA
'anthropic-ai': 'Claude',   # ← matches anthropic-ai UA (not seen)
```

**Classification behavior:**

| UA pattern | Matches AI_BOTS? | bot_name | is_bot | is_ai_bot |
|---|---|---|---|---|
| ClaudeBot/1.0 | Yes (`ClaudeBot`) | Claude | 1 | 1 |
| Claude-User (claude-code/...) | No | *(empty)* | 0 | 0 |
| Claude-User/1.0 | No | *(empty)* | 0 | 0 |
| AnthropicSearchEval/1.0 | No | *(empty)* | 0 | 0 |

**Issue found:** `Claude-User` and `AnthropicSearchEval` UAs are NOT in the AI_BOTS dict. They fall through all bot detection and are classified as `is_bot=0` (human visitors).

**Impact:** 25 requests in 14 days misclassified. Negligible for analytics but worth fixing for correctness.

**Fix needed in `analytics.py` AI_BOTS dict:**
```python
'Claude-User': 'Claude',           # AI-mediated human visits
'AnthropicSearchEval': 'Claude',   # Search evaluation bot
```

Note: `Claude-User (claude-code/...)` requests are genuinely AI-mediated human visits (a person using Claude Code CLI to fetch a URL). Classifying them as `bot_name='Claude', is_bot=1, is_ai_bot=0` is correct — they're bot traffic from an AI tool, but not AI crawlers.

---

## Fas 3 — Robots.txt Coverage

| User-Agent directive | Present? |
|---|---|
| `User-agent: ClaudeBot` + `Allow: /` | ✅ |
| `User-agent: Claude-SearchBot` + `Allow: /` | ✅ |
| `User-agent: Claude-User` + `Allow: /` | ✅ |
| `User-agent: Anthropic-ai` + `Allow: /` | ✅ |
| `User-agent: Claude-Web` + `Allow: /` | ✅ |
| `User-agent: AnthropicSearchEval` | ❌ (covered by `User-agent: *`) |

Robots.txt is correct. All known Anthropic UAs have explicit `Allow: /`.

---

## Fas 4 — Scenario Assessment

**Scenario C: Claude-User + Claude-SearchBot traffic is genuinely tiny.**

- Claude-SearchBot: **0 requests ever seen.** Either not deployed against nerq.ai or using a different UA.
- Claude-User: **25 requests in 14 days.** All from Claude Code CLI users, not Anthropic's search infrastructure.
- AnthropicSearchEval: **1 request ever.** One-time evaluation probe.

The crawl rate differential (ClaudeBot at ~25% baseline) is entirely about Anthropic's primary crawler pipeline (ClaudeBot/1.0), not about missing bot variants.

---

## Recommended fixes

### 1. Add Claude-User to AI_BOTS (correctness, low priority)

In `analytics.py`, add to the AI_BOTS dict:
```python
'Claude-User': 'Claude',
'AnthropicSearchEval': 'Claude',
```

This would classify the 25 Claude-User requests as `bot_name='Claude'` instead of leaving bot_name empty. Volume is negligible but keeps the data clean.

### 2. No action needed on crawl rate

The ClaudeBot/1.0 differential is confirmed external (Anthropic-side) by the previous analysis (`claudebot-specific-diff-2026-04-13.md`). Our server responds 99.0% 2xx to every request received.

### 3. Add AnthropicSearchEval to robots.txt (optional)

```
User-agent: AnthropicSearchEval
Allow: /
```

Purely for completeness — 1 request ever and already covered by wildcard.
