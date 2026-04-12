# Fix: Alibaba Cloud Singapore Scraper Classified as Bot

Date: 2026-04-12 (Sunday evening 19:25 CEST)
Status: Applied and verified — scraper now classified as bot in analytics

## Discovery

While investigating discrepancies between Summary human visits, 
Top 10 by Country, and By Language in the analytics dashboard,
Singapore showed exponential growth in 'human visits':

| Date | SG human visits |
|---|---|
| 2026-04-03 | 2,006 |
| 2026-04-05 | 4,457 |
| 2026-04-07 | 13,284 |
| 2026-04-09 | 21,368 |
| 2026-04-11 | 50,219 |
| 2026-04-12 | ~41K (ongoing) |

250x growth in 9 days is not organic human traffic.

## Root cause

Alibaba Cloud Singapore IPs running a scraper targeting /v1/preflight
endpoint for MCP servers. Characteristics:

- IP ranges: 43.172.x.x, 43.173.x.x, 47.79.x.x, 47.82.x.x (Alibaba Cloud)
- All identical user-agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
- ~70 requests per IP per day, rotating across many IPs
- Primary target: /v1/preflight?target=<mcp-server-name>
- 3 requests per unique MCP server target
- 24/7 activity pattern (not business hours)
- Average 1.25s response time — they wait for and consume responses
- 79K requests in 24h from these IPs combined

Likely purpose: building a competing MCP server catalog using ZARQ trust
scores as data source. Possibly a Chinese/Asian MCP aggregator.

## What they access

79,134 requests in 24h:
- 1,156 requests to /v1/preflight (MCP server trust queries)
- Small volumes to /kya, /what-is/, /safe/, /alternatives/, /predict/

MCP targets scraped include: zed-mcp-server-threadbridge, seo-mcp-server,
gsuite-mcp, github-mcp, fluidmcp, demo-recorder-mcp, xmtp-docs-mcp,
chatbot-gaming-assistant, RedmineMCP, and many more.

## Decision: classify as bot, do not block

Options considered:
- Block entirely (too aggressive; we lose potential AI citation value)
- Rate limit (requires Cloudflare WAF config; not urgent)
- Classify as bot in analytics (keeps analytics clean)
- Brand attribution in responses (clever but requires code change)

Chosen: classify as bot. Keeps analytics correct without blocking
data propagation that may indirectly benefit Nerq through AI citations.

## Code change

Added `DATACENTER_SCRAPER_PREFIXES` constant in analytics.py listing
Alibaba Cloud IP ranges. `_detect_bot()` now checks this list before
the existing BOT_IP_PREFIXES list and returns ('Datacenter Scraper',
True, False) for matching IPs.

## Verification

After FastAPI restart at 19:25 CEST:
- 93 Alibaba requests, 100% classified as 'Datacenter Scraper' bot
- 0 SG human visits from Alibaba IPs in analytics
- All other SG bots (ByteDance, Other Bot) still correctly classified

## Impact on analytics dashboard

Singapore's 'Human Visits by Country' will drop significantly as the
41K scraper visits/day migrate to bot category. Top 10 countries will
rebalance — US, VN, SE likely move up. Total Summary human visits
decreases to reflect actual human traffic.

Historical data (before 19:25 CEST 2026-04-12) is not retroactively
fixed. Scraper requests remain classified as human in historical rows.

## Next steps

Monitor Singapore human visits trend over next 24h to confirm the
drop. If other datacenter scraper patterns emerge from different
regions (AWS Tokyo, GCP Taiwan, etc), add those prefixes to the same
DATACENTER_SCRAPER_PREFIXES tuple.
