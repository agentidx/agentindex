# Brave Search Audit — 2026-04-13

## Indexing Status

| Site | Pages visible in Brave SERP | Brave crawler requests (30d) |
|---|---|---|
| nerq.ai | ~19 | **0** |
| zarq.ai | ~15 | **0** |

Brave has indexed a small number of pages (likely via Bing's index or external links, not direct crawling). No BraveSearch crawler requests observed in 30 days of logs.

### nerq.ai pages in Brave

Indexed pages are a mix of old URL patterns and a few entity pages:
- Homepage `/`
- Agent pages: `/agent/{uuid}` (3 pages — old format, not `/safe/`)
- Entity pages: `/safe/tailscale`, `/safe/temu`, `/safe/anvil-agent`, etc.
- Category pages: `/extensions`, `/games`
- Model/dataset pages: `/model/...`, `/dataset/...`, `/package/...`
- Static: `/stats`, `/index`, `/static/nerq-logo-512.png`

**Missing:** All 23 language variants, `/best/` ranking pages, `/is-*-safe` patterns, compare pages. Brave is seeing <0.001% of the 7.5M entity corpus.

### zarq.ai pages in Brave

~15 pages indexed, mostly token pages and compare pages:
- `/crypto/token/render-token`, `/crypto/token/sundog`, etc.
- `/compare/clore-ai-vs-bitcoin`, etc.
- `/methodology`, `/crypto/defi/powerflow`

## Crawler Activity

### BraveSearch bot

| Metric | Value |
|---|---|
| Requests (30d) | **0** |
| robots.txt directive | `User-agent: BraveSearch` → `Allow: /` ✅ |

BraveSearch crawler has never visited nerq.ai or zarq.ai as far as our logs show.

### Brave browser users

| UA | Requests | Period |
|---|---:|---|
| Brave/1 Mobile (iPhone iOS 26.3-26.4) | 5 | Mar 19 – Apr 12 |
| Brave/1 Mobile (iPhone iOS 18.7) | 3 | Mar 27 – Apr 12 |

Only 8 visits from Brave browser users in 30 days (all mobile iOS).

## robots.txt

```
# Brave Search AI
User-agent: BraveSearch
Allow: /
```

Correctly configured. No Disallow, no Crawl-delay.

## Why indexing is minimal

1. **No direct crawler visits** — BraveSearch hasn't crawled us. Our pages in Brave likely come from Bing's index (Brave uses Bing as a fallback data source).
2. **No Brave Webmaster Tools submission** — Brave doesn't have a public webmaster tools or sitemap submission interface.
3. **Brave indexes primarily via their own crawler + Bing** — without crawler visits, coverage depends on Bing's index and external backlinks.

## Recommendations

### 1. No action needed (low priority)

Brave Search has ~1% global search market share. The 19 indexed pages are from organic discovery. Forcing indexing isn't worth engineering effort.

### 2. If wanting to improve coverage (optional)

- Ensure nerq.ai appears on well-indexed directories/aggregators that Brave crawls
- Brave's crawler will eventually discover the site via sitemap links from other indexed sites
- Monitor: once BraveSearch starts crawling, our `Allow: /` directive and comprehensive sitemaps will give it full access

### 3. Already correctly configured

- robots.txt: ✅ BraveSearch explicitly allowed
- Sitemaps: ✅ Standard XML format, compatible with all crawlers
- No Brave-specific meta tags needed (Brave respects standard robots directives)
