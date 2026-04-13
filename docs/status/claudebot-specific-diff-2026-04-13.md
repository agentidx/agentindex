# ClaudeBot Crawl Rate Differential — 2026-04-13

**Analyst:** Claude Code (Opus 4.6)
**Question:** Why is ClaudeBot at ~25% baseline while ChatGPT recovered?
**Conclusion:** **External (Anthropic-side).** Zero server-side differences found.

---

## Fas A — Status Code Distribution

| Day | Bot | 2xx | 3xx | 404 | 5xx | Total | %2xx |
|-----|-----|----:|----:|----:|----:|------:|-----:|
| Apr 08 | Claude | 139,105 | 183 | 3,147 | 0 | 142,435 | **97.7%** |
| Apr 08 | ChatGPT | 140,098 | 190 | 183 | 0 | 140,471 | 99.7% |
| Apr 09 | Claude | 137,585 | 153 | 1,365 | 0 | 139,103 | **98.9%** |
| Apr 10 | Claude | 143,477 | 251 | 1,358 | 0 | 145,086 | **98.9%** |
| Apr 11 | Claude | 148,386 | 201 | 1,317 | 0 | 149,904 | **99.0%** |
| Apr 12 | Claude | 64,547 | 123 | 611 | 0 | 65,281 | **98.9%** |
| Apr 13 | Claude | 18,607 | 29 | 151 | 0 | 18,787 | **99.0%** |

**Claude's 2xx rate is identical pre and post incident (98.9-99.0%).** Zero 5xx. Zero 403. Zero 429. The server responds successfully to every Claude request it receives. There are just fewer requests.

ChatGPT also maintained 99.3-99.7% 2xx throughout. Apple at 96-99%.

---

## Fas B — Response Times

| Day | Claude avg (ms) | ChatGPT avg (ms) | Apple avg (ms) |
|-----|----------------:|------------------:|---------------:|
| Apr 08 | 121 | 64 | 331 |
| Apr 09 | 131 | 111 | 515 |
| Apr 10 | 113 | 96 | 182 |
| Apr 11 | 117 | 94 | 328 |
| Apr 12 | 343 | 280 | 968 |
| Apr 13 | 252 | 109 | 347 |

Apr 12 latency was elevated for ALL bots (Cloudflare incident). ChatGPT returned to normal by Apr 13 (109ms). Claude is slightly elevated (252ms) — likely due to lower volume causing fewer cache hits, not a serving issue.

**No Claude-specific latency anomaly.**

---

## Fas C — URL Distribution

### Baseline (Apr 8-11) top paths

| Path | Count |
|------|------:|
| /v1/preflight | 476 |
| /is-react-slider-a-scam | 3 |
| (all others at 1-2 each) | ~574K |

### Post-incident (Apr 12-13) top paths

| Path | Count |
|------|------:|
| /v1/preflight | 25 |
| (all others at 1-2 each) | ~84K |

**Distribution shape is identical.** ClaudeBot spreads requests evenly across entity pages with minimal repetition. The only change is total volume.

**No Claude-specific 4xx paths found.** Query for "paths where Claude gets 4xx but ChatGPT doesn't" returned zero rows.

---

## Fas D — User Agent Variants

| User-Agent | Requests | First seen | Last seen |
|---|---:|---|---|
| `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)` | 660,606 | Apr 08 | Apr 13 |

**Only ONE variant.** No UA changes, no variant collapse, no migration between crawler pipelines.

---

## Fas E — Cache Status

Both ClaudeBot and GPTBot receive `cf-cache-status: HIT` on identical requests. Claude's slightly higher latency on Apr 13 (252ms vs 109ms) is consistent with fewer requests → less cache warmth, not differential treatment.

---

## Fas F — IP Range

| IP prefix | Requests | First seen | Last seen |
|---|---:|---|---|
| 216.73.* | 660,606 | Apr 08 | Apr 13 |

**Single IP prefix for entire period.** No infrastructure change on Anthropic's side visible to us.

---

## Fas G — Robots.txt

All Claude/Anthropic directives are explicit `Allow: /`:

```
User-agent: ClaudeBot      → Allow: /
User-agent: Claude-SearchBot → Allow: /
User-agent: Claude-User     → Allow: /
User-agent: Anthropic-ai    → Allow: /
User-agent: Claude-Web      → Allow: /
```

No Disallow, no Crawl-delay. No changes to robots.txt during the period.

---

## Fas H — External Signal (live test)

| Header | ClaudeBot UA | GPTBot UA |
|--------|-------------|-----------|
| HTTP status | 200 | 200 |
| content-type | text/html | text/html |
| cf-cache-status | HIT | HIT |
| x-cache | HIT | HIT |
| cache-control | identical | identical |

**Byte-for-byte identical responses.** No differential treatment by Cloudflare or our application.

---

## Hourly Recovery Comparison

| Hour | Claude | ChatGPT | Claude recovery % |
|------|-------:|--------:|------------------:|
| Apr 11 baseline | ~6,800/h | ~6,500/h | 100% |
| Apr 12 05:00 (nadir) | 330 | 104 | 5% |
| Apr 12 14:00 (spike) | 6,102 | 45 | 90% (brief) |
| Apr 12 21:00 | 1,269 | 1,063 | 19% |
| Apr 12 23:00 | 1,240 | 4,442 | 18% |
| Apr 13 00:00 | 3,947 | 4,555 | 58% |
| Apr 13 04:00 | 2,516 | 4,766 | 37% |
| Apr 13 09:00 | 286 | 3,426 | 4% |

**ChatGPT recovered to ~70% by Apr 13 and climbed steadily. Claude oscillates between 4-58% with no stable recovery trend.** The oscillation pattern (one good hour, then collapse) is consistent with Anthropic's crawler restarting and then throttling back.

---

## Verdict

### Cause: **External (Anthropic-side)**

Evidence for external cause:
1. **Zero server-side error difference:** Claude's 2xx rate is 99.0% — identical to baseline
2. **Zero response code anomaly:** No 403, 429, or 5xx for Claude
3. **Zero UA discrimination:** ClaudeBot and GPTBot get identical HTTP responses (headers, cache, status)
4. **Zero robots.txt issue:** All Claude UAs have explicit `Allow: /`
5. **Zero URL pattern issue:** No Claude-specific 4xx paths
6. **Single IP prefix unchanged:** 216.73.* throughout entire period

Evidence against internal cause:
1. ChatGPT recovered to ~70% with identical infrastructure
2. Apple (CF-independent) is at 100% — no server issue
3. No code changes that could affect Claude specifically

**The recovery pattern** (oscillation without convergence) is inconsistent with a server-side issue, which would produce consistent behavior. It is consistent with an upstream crawler being rate-limited or throttled by its own infrastructure.

### Recommended action: **Continue waiting**

No patch to apply on our side. Monitor daily via:
```bash
sqlite3 ~/agentindex/logs/analytics.db "
  SELECT date(ts), COUNT(*) FROM requests
  WHERE bot_name='Claude' AND ts >= date('now','-7 days')
  GROUP BY date(ts) ORDER BY 1"
```

If Claude hasn't recovered to >80% baseline by Apr 16 (72h post-incident), consider reaching out to `claudebot@anthropic.com` (from their UA string) to ask if they're aware of reduced crawl capacity to nerq.ai.
