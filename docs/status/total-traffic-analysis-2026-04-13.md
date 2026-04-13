# Total Traffic Analysis — Raw Data Audit

**Date:** 2026-04-13
**Source:** analytics.db requests table (sole raw data source)
**Period:** 2026-03-14 → 2026-04-13 (30 days)
**Rows:** 17,287,913
**Method:** Direct SQL against requests table. No dashboard code used.

---

## Fas 0 — Classification Verification

### 0.1 — Bot-classified with empty bot_name

Zero rows in last 7 days where `is_bot=1 AND bot_name=''`. The analytics pipeline always assigns a bot_name when it sets is_bot=1. The 558K empty bot_names in the full dataset are all from is_bot=0 (human) rows — expected behavior.

### 0.2 — "Human"-classified IPs with >10 requests/day

Of the top 20 highest-volume "human" IPs:

| IP | Req/day | Paths | Assessment |
|---|---:|---:|---|
| 194.132.208.188 | 596-1,459 | 3-23 | **Anders** (confirmed: Nerq-Audit/1.0 UA seen) |
| 89.116.88.10 | 200-1,039 | 191-691 | **Bot** — 691 unique paths in one day |
| 64.227.178.32 | 242 | 242 | **Bot** — DigitalOcean IP, 100% unique paths |
| 43.255.191.169 | 200 | 191 | **Bot** — datacenter, 96% unique paths |
| 172.190.142.176 | 122 | 122 | **Bot** — empty UA, Azure IP |
| 157.245.36.108 | 66 | 32 | **Bot** — "l9scan" in UA |
| 93.203.52.53 | 63 | 60 | **Bot** — "image_gobbler" UA |

**6 of top 20 "human" IPs are clearly bots** that evaded detection. The 50 req/day threshold is too high, and several UA patterns ("l9scan", "gobbler") should trigger bot classification.

### 0.3 — Session-shape analysis (all "human" IPs, 7 days)

```sql
-- Categorized 133,329 unique "human" IPs by behavior
```

| Behavior | IPs | Requests | % of IPs | % of requests |
|---|---:|---:|---:|---:|
| single_shot (1 request ever) | 123,002 | 123,002 | **92.3%** | 75.6% |
| brief (2-3 requests) | 8,464 | 18,572 | 6.3% | 11.4% |
| scraper_like (>80% unique paths) | 1,656 | 10,376 | 1.2% | 6.4% |
| session_like (real navigation) | 207 | 10,703 | **0.2%** | 6.6% |

**92.3% of "human" IPs make exactly ONE request and never return.** Of these single-shot visits:

- **98.4% have NO referrer** (Direct/None) — 121,087 requests
- 1.1% from Google SERP — 1,371 requests
- 0.0% from ChatGPT — 11 requests
- 0.0% from Perplexity — 5 requests

Single-shot, no-referrer, diverse paths = classic signature of **distributed crawlers using residential IPs and browser-like UAs**.

### 0.4 — Classification reliability verdict

| Category | analytics.py label | Estimated accuracy |
|---|---|---|
| Known AI bots (ClaudeBot, GPTBot, etc.) | is_ai_bot=1 | **~99%** — UA-based, hard to spoof |
| Known SEO/search bots (Googlebot, etc.) | is_bot=1, is_ai_bot=0 | **~95%** — some edge UAs missed |
| Datacenter scrapers | bot_name='Datacenter Scraper' | **~90%** — only Alibaba IPs, many others missed |
| "Human" visitors | is_bot=0 | **~20-30% actual humans** — massive overcounting |

**The "human" classification is the weakest link.** The 50 req/day IP threshold, combined with no TLS fingerprinting or JS execution checks, means any bot with rotating IPs and a Chrome UA evades detection.

---

## Fas 1 — Volume and Breakdown (30 days)

### Daily traffic summary

| Date | Total | AI bots | Other bots | "Human" | 2xx | 4xx | 5xx |
|------|------:|--------:|-----------:|--------:|----:|----:|----:|
| Apr 08 | 896K | 293K | 595K | 8K | 858K | 27K | 7 |
| Apr 09 | 1,073K | 280K | 779K | 15K | 1,033K | 18K | 6 |
| Apr 10 | 1,130K | 303K | 781K | 46K | 1,090K | 14K | 10 |
| Apr 11 | 1,255K | 308K | 921K | 26K | 1,211K | 18K | 3 |
| Apr 12 | 880K | 89K | 761K | 30K | 851K | 16K | 8 |
| Apr 13 | 537K | 77K | 456K | 4K | 521K | 7K | 2 |

**AI bots:** ~280-308K/day baseline → 77-89K/day post-incident (Cloudflare)
**"Human":** highly variable 4K-46K/day — includes Alibaba scraper pre-fix, Anders testing, and genuine humans

### 30-day totals

| Category | Requests | % of total |
|---|---:|---:|
| Other bots (search, SEO, scrapers) | 12,175,891 | 70.4% |
| AI bots (Claude, ChatGPT, etc.) | 4,454,660 | 25.8% |
| "Human" (classified) | 657,362 | 3.8% |
| **Total** | **17,287,913** | **100%** |

---

## Fas 2 — Origin Classification (7 days)

### Top 50 UA strings analysis

The top 50 UAs account for ~7.1M of 7.6M requests (93%). Breakdown:

| Category | UAs | Requests | Classification |
|---|---:|---:|---|
| Verified AI crawlers | 8 | 4.91M | ✅ Correctly classified |
| Verified search/SEO bots | 14 | 1.14M | ✅ Correctly classified |
| Datacenter scrapers (Alibaba) | 11 | 134K | ✅ Classified since Apr 12 |
| Chrome-UA (is_bot=0) | 17 | 245K | ⚠️ **Likely mix of bots + humans** |

The 17 Chrome-UA entries classified as human show a suspicious pattern: each UA has 7K-23K requests in 7 days with identical version strings. Real browser traffic would show more version diversity. These are likely a mix of:
- Headless Chrome scrapers (~70%)
- Real Chrome users (~30%)

**Cannot separate without TLS fingerprinting or JS execution signals.**

### Country distribution ("human" traffic, 7 days)

| Country | Requests | IPs | Req/IP |
|---|---:|---:|---:|
| VN | 55,672 | 54,373 | 1.0 |
| US | 16,050 | 12,478 | 1.3 |
| CN | 5,284 | 2,199 | 2.4 |
| HK | 5,025 | 2,007 | 2.5 |
| SE | 3,623 | 266 | **13.6** |
| SG | 3,383 | 2,136 | 1.6 |
| BR | 3,106 | 2,983 | 1.0 |

**Vietnam is 34% of "human" traffic** (55K requests) but with 1.0 requests per IP — single-shot, no referrer. This is almost certainly bot farm traffic with residential/mobile IPs.

**Sweden's 13.6 req/IP** (from 266 IPs) is the clearest signal of actual human usage — consistent with Anders, the dev team, and Swedish early adopters.

---

## Fas 3 — Behavior by Category

### Top URLs by category (7 days)

**AI bots** crawl entity pages broadly — top hit is `/v1/preflight` (5.3K), then homepage (1.8K), then diverse entity pages (~20 each).

**"Human" traffic** is dominated by:
1. `/zarq/dashboard/data` (6.5K) — JavaScript API call from ZARQ dashboard
2. `/` (1.4K) — homepage
3. `/v1/preflight` (1.2K) — API calls, NOT human browsing
4. `/flywheel` (288) — internal dashboard

**Many "human" URLs are API endpoints** (`/v1/*`) — these are programmatic calls from developer tools classified as human because the UA is a browser.

---

## Fas 4 — Human Visits Deep Dive

### Referrer analysis (all "human", 7 days)

| Source | Requests | IPs |
|---|---:|---:|
| Direct/None | 150,287 | 130,834 |
| Self (nerq/zarq) | 9,704 | 1,291 |
| Google | 1,834 | 1,668 |
| Other | 460 | 285 |
| Bing | 244 | 125 |
| GitHub | 108 | 96 |
| ChatGPT | 16 | 16 |
| Perplexity | 5 | 3 |
| Claude | 3 | 2 |

**92.4% of "human" traffic has no referrer.** Only 2,106 visits (1.3%) come from any search engine. Only 24 from AI chatbot referrers.

### Valuable visitor estimate

```sql
-- Multi-request "human" IPs with quality signals
```

| Quality tier | IPs | Requests | Interpretation |
|---|---:|---:|---|
| high_value (search ref + 3+ pages) | 191 | 1,027 | Likely real humans from search |
| search_referral (search ref, brief) | 201 | 441 | Real humans, single search visit |
| explorer (5+ pages, no ref) | 900 | 16,389 | Mix: power users + sophisticated bots |
| engaged (3+ req, 2+ pages) | 2,351 | 8,286 | Plausible humans |
| low_signal (multi-req, low engagement) | 6,684 | 13,514 | Ambiguous |
| single_shot (1 request) | 123,002 | 123,002 | **Mostly bots (98% no referrer)** |

### Estimated real human traffic

| Confidence level | IPs/week | Requests/week | Per day |
|---|---:|---:|---:|
| High confidence (search ref OR engaged) | ~2,700 | ~10,000 | **~1,400** |
| Plausible (includes explorers) | ~4,200 | ~26,000 | **~3,700** |
| Maximum generous (includes low_signal) | ~10,300 | ~40,000 | **~5,700** |

**Our dashboard's "15-45K human visits/day" is overstated by 3-30x.** Realistic estimate: **1,400-5,700 actual human visits per day** depending on how generous the classification.

---

## Fas 5 — Purpose and Value

### What traffic generates measurable value?

| Traffic type | Daily volume | Creates value? | Why |
|---|---:|---|---|
| AI bot citations (Claude, GPTBot, etc.) | ~280K | **Yes** — each citation = potential AI-mediated human visit | Drives AI search citations |
| Search engine crawls (Google, Bing, Apple) | ~600K | **Yes** — indexing enables SERP ranking | Drives organic discovery |
| SEO tool crawls (Semrush, Moz, etc.) | ~30K | **Indirect** — competitors monitoring us = market validation | No direct value |
| Google SERP → human visit | ~260/day | **Yes** — genuine search discovery | Highest quality |
| ChatGPT/Perplexity → human visit | ~3/day | **Yes** — AI-mediated conversion | Very small volume |
| Direct human (no referrer) | ~1K-5K/day | **Unknown** — could be returning users or bots | Can't determine |
| Single-shot no-referrer | ~17K/day | **Unlikely** — signature of distributed bots | Minimal value |

### Verticals with quality visitors (search-referred humans, 7 days)

Cannot determine per-vertical quality without path-level referrer analysis across registries. The search-referred 1,834 visits are spread across entity pages — no single vertical dominates.

---

## Fas 6 — Critique of Our Classification

### What analytics.py assumes (and where it's wrong)

| Assumption | Reality | Impact |
|---|---|---|
| "If UA doesn't contain bot keywords → human" | Many bots use Chrome UAs | **Major** — inflates human count 3-30x |
| "50 req/day IP threshold for volume-based bot detection" | Most bot farms use rotating IPs (<50 req each) | **Major** — doesn't catch distributed bots |
| "Alibaba Cloud IPs = bot" | Probably correct, but other datacenter IPs are missed | **Moderate** — only catches one operator |
| "No referrer = could be human" | 98.4% of single-shot humans have no referrer | **Major** — this is a bot signal, not neutral |
| "IP + UA is enough for classification" | Modern bots spoof everything except TLS/JS | **Fundamental** — we lack the right signals |

### Signals we DON'T capture (but should)

| Signal | What it would tell us | Difficulty to implement |
|---|---|---|
| TLS fingerprint (JA3/JA4) | Distinguish real Chrome from headless Chrome | **Hard** — requires TLS termination change |
| JavaScript execution | Real browsers execute JS; bots often don't | **Medium** — add JS challenge to first visit |
| Cookie persistence | Real browsers accept cookies; most bots don't | **Easy** — check cookie roundtrip |
| Mouse/scroll events | Only real humans produce these | **Medium** — client-side JS |
| CF-Connecting-IP → ASN lookup | Distinguish residential from datacenter IPs | **Easy** — Cloudflare adds ASN header |

### How many requests are genuinely unclassifiable?

With current data: **~150K requests/week** (the single-shot, no-referrer, Chrome-UA pool) cannot be reliably classified as human or bot. This is ~92% of all "human" traffic.

---

## Fas 7 — Missing Data and Next Steps

### Questions we COULD NOT answer

1. **Are the 55K Vietnam "human" visits real?** We have no ASN data, no TLS fingerprint, no JS execution signal. The behavioral pattern (single-shot, no referrer, 1 req/IP) is consistent with bots but not conclusive.

2. **What fraction of Chrome-UA traffic is headless?** Without TLS fingerprinting (JA3 hash), we can't distinguish real Chrome from headless Chrome.

3. **Where do our Google SERP visitors come from?** We have referrer_domain but not the search query. No Google Search Console integration.

4. **Do AI-mediated visits convert?** We have 24 visits from ChatGPT/Perplexity/Claude referrers in 7 days. The `ai_source` and `visitor_type` columns exist but are 99.8% empty.

5. **Session depth for genuine humans.** We have per-IP request counts but no session ID, no cookie tracking, no client-side analytics.

### Recommended additions (minimal disk impact)

| Addition | Benefit | Disk impact |
|---|---|---|
| Log `CF-IPCountry` (already done) | Country attribution | 0 (column exists) |
| Log Cloudflare `cf-ipcity`, `cf-ipcontinent` | City-level geo | ~2 bytes/row |
| Log `cf-ray` header | Dedup, Cloudflare diagnostics | ~16 bytes/row |
| Add ASN column from CF header `cf-connecting-ip-asn` | Distinguish residential vs datacenter | ~6 bytes/row |
| Set + check a 1st-party cookie on first visit | Distinguish real browsers from bots | 0 (no new column needed, use existing cookie header) |
| Populate `ai_source` for all AI-referred visits | Track AI-to-human conversion | 0 (column exists, just underpopulated) |

**Estimated disk impact:** <30 bytes/row × 800K rows/day = ~24 MB/day = ~720 MB/month. Negligible compared to the 10 GB database.

---

## Summary Table

| Metric | Dashboard says | Raw data says | Discrepancy |
|---|---|---|---|
| Human visits/day | 15-45K | **1,400-5,700** | **3-30x overcount** |
| AI citations/day | ~300K | ~280-308K (pre-incident) | Close — AI bot classification is accurate |
| Total daily requests | ~900K-1.2M | Same | Dashboard matches raw data for totals |
| Google SERP referrals/day | (not shown) | **~260** | Not tracked by dashboard |
| AI chatbot referrals/day | (not shown) | **~3** | Not tracked separately |
| Single-shot visitors | (not shown) | **92% of "humans"** | Not visible in dashboard |

## Open Questions

1. Is the Vietnam traffic (34% of "human") real or bot farm?
2. What fraction of Chrome-UA traffic is headless/automated?
3. Should we invest in client-side analytics (JS execution check) given the scale of misclassification?
4. Does it matter if "human" traffic is overcounted? (Only matters for monetization trigger at 150K/day — we're at 1.4-5.7K actual)
5. Should the 50 req/day bot threshold be lowered? (Would catch more bots but also flag power users)
