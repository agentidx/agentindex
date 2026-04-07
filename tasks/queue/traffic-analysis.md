# Traffic Analysis — 2026-03-07

**Data source:** `logs/analytics.db` (166,293 requests, Feb 23 – Mar 7)
**Supplementary:** `agentindex/crypto/zarq_api_log.db` (444 rows, observability middleware, today only)

---

## Summary

| Metric | Value |
|--------|-------|
| Total requests (all time) | 166,293 |
| Last 24 hours | 47,848 |
| Last 1 hour | 18,754 |
| Unique IPs (24h) | 755 |
| Bot traffic | 92.1% |
| Human traffic | 7.9% |

---

## Daily Traffic Trend

| Date | Total | Bots | Humans | Human % |
|------|-------|------|--------|---------|
| Feb 23 | 914 | 9 | 905 | 99% |
| Feb 24 | 4,260 | 1,411 | 2,849 | 67% |
| Feb 25 | 2,894 | 333 | 2,561 | 89% |
| Feb 26 | 1,466 | 216 | 1,250 | 85% |
| Feb 27 | 136 | 12 | 124 | 91% |
| Feb 28 | 204 | 75 | 129 | 63% |
| Mar 1 | 1,853 | 1,410 | 443 | 24% |
| Mar 2 | 7,874 | 6,981 | 893 | 11% |
| Mar 3 | 30,503 | 28,749 | 1,754 | 6% |
| **Mar 4** | **35,873** | **35,291** | **582** | **2%** |
| Mar 5 | 32,468 | 31,729 | 739 | 2% |
| Mar 6 | 29,094 | 28,595 | 499 | 2% |
| Mar 7 (partial) | 18,758 | 18,346 | 412 | 2% |

**Key insight:** Traffic exploded 20x from Mar 1–4 driven almost entirely by bot crawlers. Human traffic stayed flat at ~500–900/day. The site went from ~1K/day to ~30K+/day in one week.

---

## Bot Breakdown

| Bot | Requests | Unique Pages | Avg Latency |
|-----|----------|--------------|-------------|
| Meta (Facebook) | 125,296 | ~128K | 163s (!) |
| Claude (Anthropic) | 10,235 | 10,054 | 12.9s |
| curl (internal/monitoring) | 9,268 | — | — |
| Google | 3,666 | 2,676 | 56.9s |
| python-httpx | 1,977 | — | — |
| ChatGPT (OpenAI) | 1,145 | 988 | 38.7s |
| MJ12bot | 885 | — | — |
| Bing | 410 | 259 | 2.8s |
| Amazon | 59 | 58 | 3.2s |
| Yandex | 47 | 22 | 1.7s |
| Perplexity | 33 | 29 | 5.0s |
| Apple | 12 | 11 | 0.01s |

**Dominant crawler: Meta/Facebook** — 75% of all traffic (125K requests). This is `meta-externalagent/1.1` crawling agent pages. Average latency 163 seconds is extreme — these are likely timing out or hitting very slow DB queries on agent detail pages.

**AI bots (Claude + ChatGPT + Perplexity):** 11,413 requests (6.9%), actively indexing content.

---

## Traffic by Category

| Category | Requests | % of Total |
|----------|----------|------------|
| Agent detail pages (`/agent/*`) | 124,734 | **75.0%** |
| Other (homepage, static, misc) | 19,694 | 11.8% |
| Crypto token pages (`/crypto/token/*`) | 7,864 | 4.7% |
| Crypto API (`/v1/crypto/*`) | 5,140 | 3.1% |
| Crypto pages (`/crypto/*`) | 4,651 | 2.8% |
| Other v1 API | 1,423 | 0.9% |
| Yield API (`/v1/yield/*`) | 1,304 | 0.8% |
| WordPress probes (attack traffic) | 1,274 | 0.8% |
| Agent risk API (`/v1/agents/*`) | 221 | 0.1% |

**75% of all traffic is agent detail pages** — almost entirely Meta bot crawling all 4.66M agent pages. This is the primary load driver.

---

## Top Endpoints (All Time)

| Endpoint | Hits | Avg ms | Errors |
|----------|------|--------|--------|
| `/` (homepage) | 8,851 | 34 | 116 |
| `/admin/dashboard` | 3,659 | 1,819 | 1 |
| `/v1/health` | 1,106 | 1,501 | 0 |
| `/v1/yield/insights` | 636 | 233 | 0 |
| `/v1/yield/overview` | 559 | 40 | 2 |
| `/wp-admin/setup-config.php` | 480 | 2 | 240 |
| `/v1/discover` | 185 | **20,401** | 18 |
| `/crypto` | 156 | 13,681 | 0 |
| `/v1/agents/structural-collapse` | 108 | 6,564 | 1 |
| `/v1/yield/traps` | 102 | 155 | 1 |
| `/v1/agents/chain-concentration-risk` | 101 | 7,023 | 0 |
| `/v1/stats` | 70 | **8,945** | 0 |
| `/v1/crypto/stresstest` | 36 | **71,511** | 0 |
| `/v1/crypto/contagion/network` | 16 | **159,079** | 0 |

---

## Performance Hotspots

| Endpoint | Avg Latency | Max Latency | Issue |
|----------|-------------|-------------|-------|
| `/agent/*` (detail pages) | **180s** | **7,119s** | PostgreSQL full-table scans under Meta bot load |
| `/v1/crypto/contagion/network` | 159s | — | Heavy computation |
| `/v1/crypto/stresstest` | 71.5s | 2,551s | Heavy computation |
| `/v1/crypto/paper-trading/nav/*` | 45.6s | — | Complex queries |
| `/v1/discover` | 20.4s | 2,303s | Full-text search + semantic |
| `/crypto` (landing) | 13.7s | — | Multiple DB queries |
| `/v1/stats` | 8.9s | — | COUNT(*) on 4.66M rows |

**Critical:** Agent detail pages averaging 3 minutes response time under Meta bot crawl pressure. This is the #1 performance issue.

---

## HTTP Status Codes

| Status | Count | % |
|--------|-------|---|
| 200 OK | 156,990 | 94.4% |
| 404 Not Found | 6,673 | 4.0% |
| 301 Redirect | 2,108 | 1.3% |
| 405 Method Not Allowed | 506 | 0.3% |

---

## Top 404s (Attack Surface)

| Path | Hits |
|------|------|
| `/wp-admin/setup-config.php` | 240 |
| `/wordpress/wp-admin/setup-config.php` | 233 |
| `/api` | 65 |
| `/index.php` | 40 |
| `/admin` | 38 |
| `/xmlrpc.php` | 17 |

Standard WordPress/PHP vulnerability scanning. No action needed (returns 404 fast).

---

## Referral Traffic

| Source | Hits |
|--------|------|
| nerq.ai (internal) | 4,853 |
| zarq.ai (internal) | 1,497 |
| agentcrawl.dev | 300 |
| google.com | 84 |
| claude.ai | 34 |
| bing.com | 11 |

**Google organic:** 84 referrals. Still early — SEO is barely producing clicks.

---

## Top Search Queries (from referrers)

| Query | Hits |
|-------|------|
| popular AI agents | 131 |
| mcp server database | 15 |
| slack integration | 12 |
| code review | 12 |
| code assistant | 12 |
| browser automation | 12 |
| mcp server | 11 |
| langchain | 10 |

---

## Top Crypto Token Pages

| Token | Hits |
|-------|------|
| bitcoin | 39 |
| token-metrics-ai | 17 |
| infraxa | 16 |
| sovrun | 16 |
| handshake | 15 |
| gloria-ai | 13 |
| polkadot | 13 |

---

## Hourly Distribution (Last 24h)

```
00-04: ~2,400/hr  (bot-heavy, steady crawl)
05-10: ~2,300/hr  (bot-heavy, steady crawl)
11-14: ~2,700/hr  (peak — slight human bump)
15-20: ~1,170/hr  (significant drop)
21-22: ~1,350/hr  (recovering)
```

Traffic is relatively flat — no strong diurnal pattern, consistent with bot-dominated traffic.

---

## Recommendations

### Urgent
1. **Rate-limit Meta bot** — 125K requests at 163s avg = massive server load. Add `Crawl-delay: 10` to robots.txt or block `meta-externalagent` if agent pages aren't needed on Facebook.
2. **Cache agent detail pages** — 75% of traffic hits `/agent/*` with 180s avg response. Add Redis caching (TTL 1h) or serve static HTML.
3. **Add `COUNT(*) OVER()` or materialized stats** — `/v1/stats` taking 9s for a simple count.

### Important
4. **Fix `/v1/discover` latency** — 20s average is too slow for an API endpoint.
5. **Gate heavy computation endpoints** — `/v1/crypto/stresstest` (71s) and `/v1/crypto/contagion/network` (159s) should be async with job queues.
6. **Block WordPress probes** — 1,274 requests to non-existent PHP paths. Add nginx/Cloudflare rule.

### Monitor
7. Human traffic is flat (~500-900/day) despite 20x bot growth — SEO not yet converting.
8. Google has crawled 2,676 unique pages — good coverage, but avg latency 57s may hurt rankings.
9. Claude AI is the most active AI bot (10K requests) — verify agent-card.json is being picked up.
