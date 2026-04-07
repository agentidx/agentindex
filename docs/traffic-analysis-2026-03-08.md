# ZARQ Traffic Analysis — 2026-03-08

**Period:** 2026-03-07 14:26 UTC to 2026-03-08 09:57 UTC (~19.5 hours)
**Total requests:** 28,812
**Unique IPs:** 390

---

## Executive Summary

**The hard truth:** 90.4% of all traffic is a single bot (Meta/Facebook external agent) systematically crawling Nerq agent pages. Stripping that out, real traffic is ~2,747 requests/day from ~110 unique IPs, mostly internal (curl/testclient). Genuine external organic traffic is approximately 1,067 requests (~3.7%).

**Product-market fit signal:** Weak but present. Three real tokens are being checked (bitcoin, ethereum, solana) by 4 external IPs. No agent framework integrations detected yet. Google is indexing us (228 requests). Claude, ChatGPT, and Perplexity are visiting (39 combined).

---

## 1. Who Is Using Us

### Traffic Breakdown

| Category | Requests | % | Assessment |
|----------|----------|---|-----------|
| Meta bot (agent page crawling) | 26,065 | 90.4% | Facebook indexing Nerq agent pages — good for social sharing |
| Internal (curl/testclient) | 1,700 | 5.9% | Our own testing and monitoring |
| Organic external | 1,067 | 3.7% | Real users and bots |

### User Agent Classification (All Traffic)

| Type | Requests | % |
|------|----------|---|
| Other Bot (Meta) | 26,065 | 90.4% |
| API Client (curl) | 1,008 | 3.5% |
| Unknown (testclient) | 705 | 2.4% |
| Human Browser (Chrome) | 403 | 1.4% |
| Search Bot (Google) | 228 | 0.8% |
| Human Browser (Chrome Mobile) | 166 | 0.6% |
| API Client (Python) | 99 | 0.3% |
| Human Browser (Safari) | 86 | 0.3% |
| AI Bot (Claude) | 20 | 0.1% |
| AI Bot (ChatGPT) | 11 | 0.0% |
| AI Bot (Perplexity) | 8 | 0.0% |
| SEO Bot | 6 | 0.0% |
| Social Bot | 5 | 0.0% |
| Search Bot (DuckDuckGo) | 5 | 0.0% |
| Search Bot (Bing) | 3 | 0.0% |

### Key User Profiles

**IP 12ca17b49af22894 (965 requests)** — Internal monitoring/development
- Uses curl, hits /v1/health (487x), homepage (157x), yield endpoints (261x)
- Checks 6 tokens including bitcoin, ethereum, solana
- Pattern: Developer actively testing endpoints

**IP 846488f1dc5c07b4 (692 requests)** — Test suite runner
- Uses testclient (pytest/Starlette), systematically hits all endpoints
- 56x /v1/check/bitcoin, 38x every major endpoint
- Pattern: Automated test suite

**IPs 8f6395282d6985f1 through b2368daf49144473 (370-427 each)** — Meta bot cluster
- 65+ Meta IPs each crawling ~370 unique /agent/{uuid} pages
- Never visits the same page twice (breadth-first crawl)
- Pattern: Facebook indexing our entire Nerq agent catalog

---

## 2. What They Want

### Endpoint Demand (Organic, Excluding Meta)

| Category | Requests | % |
|----------|----------|---|
| Nerq Agent API | 20,140 | 69.9% |
| Pages/Static | 6,337 | 22.0% |
| ZARQ Crypto API | 2,151 | 7.5% |
| Admin/Internal | 204 | 0.7% |

### ZARQ Crypto Endpoints Used

| Endpoint | Calls | Unique IPs |
|----------|-------|-----------|
| /v1/check/bitcoin | 72 | 4 |
| /v1/yield/insights | 153 | 24 |
| /v1/yield/overview | 133 | 1 |
| /v1/crypto/ndd/bitcoin | 38 | 1 |
| /v1/crypto/rating/bitcoin | 38 | 1 |
| /v1/crypto/ratings | 38 | 1 |
| /v1/check/ethereum | 10 | 3 |
| /v1/check/solana | 4 | 1 |
| /v1/demo/save-simulator | 29 | 2 |

### Token Check Activity

- **Total real /v1/check calls:** 86 (excluding test tokens)
- **Unique real tokens checked:** 3 (bitcoin, ethereum, solana)
- **Repeat callers:** 3 IPs made ≥3 calls to /v1/check
- **Multi-token checkers:** 3 IPs checked ≥2 different tokens

### Cross-Product Usage
- 76 IPs hit both ZARQ crypto and Nerq agent endpoints
- But most of these are Meta bot or internal traffic

---

## 3. Temporal Patterns

### Hourly Distribution (UTC)

Traffic is **NOT constant 24/7**. Clear pattern:
- **Low period:** 00:00-09:00 UTC (~1,100-1,280 req/hr) — mostly Meta bot
- **High period:** 14:00-22:00 UTC (~1,300-2,280 req/hr) — Meta + organic peaks
- **Peak hour:** 19:00 UTC (2,280 requests) = 20:00 CET (European evening)

### Organic Traffic Pattern (Excluding Meta)

Organic traffic spikes at:
- 09:00 UTC (299 organic) — European morning
- 15:00-16:00 UTC (329-345 organic) — US East Coast morning / EU afternoon

This suggests primarily European and US East Coast users.

### Daily Volume
| Date | Requests | IPs |
|------|----------|-----|
| 2026-03-07 (partial) | 16,995 | 283 |
| 2026-03-08 (partial) | 11,837 | 281 |

---

## 4. AI Bot Intelligence

| AI Bot | Requests | What They're Doing |
|--------|----------|-------------------|
| Claude (Anthropic) | 20 | Crawling content for training/RAG |
| ChatGPT (OpenAI) | 11 | Browsing/answering user queries about us |
| Perplexity | 8 | Indexing for search results |

Combined AI bot traffic: 39 requests. This is a leading indicator — when users ask AI assistants about crypto risk tools, they may find ZARQ. Having our llms.txt and API docs well-structured matters.

---

## 5. Error Analysis

| Error | Count | Cause |
|-------|-------|-------|
| /internal/metrics 401 | 36 | Auth working correctly |
| /favicon.ico 404 | 28 | No favicon (cosmetic) |
| /v1/crypto/rating/zzz-* 404 | 18 | Test probes |
| /v1/discover 422 | 18 | Missing required fields |
| WordPress probes 404/405 | 60+ | Scanner noise |

No real bugs. All errors are expected behavior.

---

## 6. Key Findings

### Signals of Product-Market Fit

**Positive:**
1. **Facebook is systematically indexing our agent catalog** — 26K+ requests across 65+ IPs, crawling individual agent pages. This means shared agent links render properly on Facebook/Instagram/WhatsApp.
2. **Google is indexing us** — 228 Googlebot requests. SEO pages are working.
3. **Three AI assistants visit us** — Claude, ChatGPT, Perplexity. Users are asking AI about crypto risk tools.
4. **24 unique IPs hit /v1/yield/insights** — highest organic endpoint after homepage.
5. **Human browser traffic exists** — ~655 requests from Chrome/Safari/Firefox users actively browsing.

**Concerning:**
1. **Zero agent framework traffic detected** — No LangChain, CrewAI, ElizaOS, or Solana Agent Kit user agents. Our framework integrations haven't driven adoption yet.
2. **Only 3 real tokens checked** — bitcoin, ethereum, solana. No one is checking altcoins where ZARQ's crash detection is most valuable.
3. **Only 4 external IPs used /v1/check** — The zero-friction endpoint hasn't gone viral yet.
4. **90% traffic is one bot** — Strip Meta out and real traffic is modest.
5. **No webhook subscribers** — POST /v1/crash-shield/subscribe has zero external calls.

### What Our Users Actually Want

Based on traffic patterns:
1. **Yield data** (/v1/yield/) — 286 calls from 24 IPs. Highest organic ZARQ demand.
2. **Risk check for major tokens** — bitcoin/ethereum/solana only.
3. **Agent discovery** — Nerq agent pages get the most organic page views.
4. **Dashboard/analytics** — /admin/dashboard gets 90 internal hits.

---

## 7. Recommendations

### Immediate (This Week)

1. **Add favicon.ico** — 28 unnecessary 404s. Trivial fix for professionalism.
2. **Publish llms.txt to root** — Ensure AI bots (Claude/ChatGPT/Perplexity) can discover our API. Already exists at /exports/llms.txt, needs to be at /.well-known/llms.txt and /llms.txt.
3. **Submit to Smithery + Glama** — MCP registry listings will drive agent framework adoption.
4. **Share save-cards on Twitter/crypto communities** — The save-cards are built but no one knows about them.

### Short-Term (This Month)

5. **Expand token coverage in marketing** — No one checks altcoins because no one knows we rate 205 tokens. Feature specific crash saves (Story -86%, Virtuals -84%) in marketing.
6. **Build demo integrations** — Since zero LangChain/CrewAI traffic exists, we need to publish working demo repos that people can clone.
7. **Rate-limit Meta bot** — 26K requests is fine, but if it grows 10x it will strain resources. Consider robots.txt Crawl-delay.
8. **API usage examples** — The /v1/check endpoint is powerful but only 4 IPs have found it. Need prominent docs/tutorials.

### Strategic

9. **Yield data is the surprise hit** — 286 calls to yield endpoints from 24 IPs. Consider building this out as a distinct product surface.
10. **Cross-pollination opportunity** — 76 IPs already hit both ZARQ and Nerq. Build explicit bridges (agent pages linking to token risk, token pages linking to related agents).

---

## Raw Data Sources

- Database: `agentindex/crypto/zarq_api_log.db`
- Table: `api_log` (28,812 rows)
- Columns: timestamp, endpoint, method, status_code, latency_ms, ip_hash, tier, user_agent, response_size
- Period: 2026-03-07T14:26 to 2026-03-08T09:57 UTC
