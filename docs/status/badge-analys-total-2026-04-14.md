# Badge System — Total Analysis

**Date:** 2026-04-14
**Source:** analytics.db, badge_outreach_log.json, badge_outreach_targets.json, badge_api.py

---

## DEL A — Grundläggande inventering

### A1. Badge-endpoints

| Endpoint | Returns | Lookup |
|---|---|---|
| `/badge/{name}` | SVG badge | By agent name |
| `/badge/npm/{package}` | SVG badge | By npm package |
| `/badge/pypi/{package}` | SVG badge | By PyPI package |
| `/badge/{name}?format=html` | HTML embed page | Badge + embed code |
| `/badges` | HTML catalog page | Browse all badges |
| `/compliance/badge/trust-grade/{grade}` | SVG badge | Static grade badge |

**Format:** shields.io-style SVG. Green (#22c55e) for A/B grades, yellow (#eab308) for C/D, red (#ef4444) for E/F. Gray (#9ca3af) for unknown entities.

**Caching:** Cloudflare CDN caches badges (entity pages path matches `s-maxage=86400`). Redis PageCacheMiddleware also caches. Badge updates when entity score changes + cache expires (up to 24h stale).

**Query parameters:** `?format=html` for embed page. No style/color/theme parameters.

### A2. Origin

File `badge_api.py` (403 lines). Badge outreach system: `badge_outreach_auto.py`, `badge_outreach_discovery.py`, `badge_outreach_ab.py`, `badge_pr_bot.py`. Created during Sprint 0-era (pre-April 2026). No design doc found — code comments reference "badges for README embedding."

### A3. Technical generation

`_svg_badge(label, value, color)` in `badge_api.py:31` generates SVG inline per request. Entity data fetched via SQLAlchemy `get_session()` from Postgres (now Nbg primary). Badge dimensions calculated from text length. No image files — pure SVG text response.

---

## DEL B — Outreach-mekanismen

### B1. Outreach historik

| Metric | Värde |
|---|---:|
| Target list | 230 repos |
| Runs | 23 |
| Period | 2026-03-11 → 2026-04-10 |
| Frequency | Daily at 10:00 CEST |
| Batch size | 10 per run |
| Criteria | AI agent/MCP repos, trust_score ≥85, stars ≥1000 |

**Status:** Outreach **har stannat** sedan 2026-04-10. Alla 230 targets är kontaktade. `badge_outreach_discovery.py` (weekly discovery of new targets) har ett LaunchAgent men ingen schemalagd discovery har körts.

### B2. Outreach-resultat

| Run date | Attempted | Succeeded | Failed |
|---|---:|---:|---:|
| 2026-03-11 | 10 | 9 | 1 |
| 2026-03-12 | 10 | 10 | 0 |
| 2026-03-13 | 10 | 9 | 1 |
| ... (20 more runs) | 10 each | 6-10 | 0-7 |
| 2026-04-10 (last) | 8 | 8 | 0 |
| **Total** | **228** | **206** | **22** |

**Success rate:** 90.4% (206/228). Failures are 403 Forbidden (repo has issues disabled) or rate limits.

**Blocklisted repos:** 4 (manually excluded after rejection/spam-flagging).

### B3. Maintainer response

**Data gap:** Vi har INTE spårat om GitHub issues stängdes, kommenterades, eller ignorerades. Vi skapade issues men har ingen uppföljnings-mekanism. badge_outreach_log.json sparar bara "issue_url" vid skapandet — ingen uppföljning.

**Observation:** Av de 206 issues som skapades, har vi inget data om:
- Hur många stängdes som "won't fix" eller spam
- Hur många ledde till faktisk badge-installation
- Hur många kommenterades positivt/negativt

---

## DEL C — Badge-adoption

### C1. Adoptions-distribution (30 dagar)

| Requests per badge | Antal badges | Total requests | % av badges |
|---|---:|---:|---:|
| 1 request | 25,733 | 25,733 | 61.8% |
| 2-9 | 13,296 | 49,317 | 31.9% |
| 10-99 | 2,630 | 45,670 | 6.3% |
| 100-999 | 5 | 1,891 | 0.01% |
| 1000+ | 2 | 2,523 | 0.005% |
| **Total** | **41,666** | **125,134** | |

**62% av alla badges har bara 1 request** (sannolikt en engångs-check, inte en installation). Bara 2,637 badges (6.3%) har ≥10 requests, vilket indikerar faktisk embedding i en README eller sida.

### C2. Outreach → adoption konvertering

**Data-begränsning:** LIKE-matchning mot 230 target-slugs i 125K badge requests är långsam. Baserat på partiell analys:

De specifika referrer-matcharna visar att outreach-repos syns i datan:
- `olasunkanmi-SE/codebuddy`: 1,443 requests (outreach target → VS Code Marketplace)
- `call518/MCP-PostgreSQL-Ops`: 452 requests (outreach target → mcpservers.org)

**Observation:** De mest framgångsrika badge-adoptionerna korrelerar med att repos listas på tredjepartssajter (VS Code Marketplace, MCP-kataloger), inte direkt med README-embedding.

### C3. Icke-outreach badges (41,436 stycken)

**Fördelning per typ:** Ej direkt spårbart från path — badge-slug matchar inte direkt mot registry. Men baserat på top badges:
- MCP-servrar dominerar (strudel-mcp-server, tavily-mcp, MCP-PostgreSQL-Ops)
- AI-agenter (NagaAgent, codebuddy, autocoder-nano)
- Spel (HELLDIVERS 2)
- Generic entities (express, harbor)

**Tidsserie:** Badges ökade kraftigt 31 mars (1,000→9,418/dag, sammanfaller med ClaudeBot/GPTBot training crawl-explosion som indexerade badge-URLs).

---

## DEL D — Spridningsmekanismen

### D1. Referrer-analys (30 dagar, alla med >2 requests)

| Referrer | Requests | Typ |
|---|---:|---|
| zarq.ai | 5,112 | Intern (ZARQ dashboard) |
| google.com | 304 | Sökmotor bildsök |
| bing.com | 191 | Sökmotor bildsök |
| gitee.com | 162 | Kinesisk GitHub |
| marketplace.visualstudio.com | 103 | VS Code Marketplace |
| mcpservers.org | 71 | MCP-katalog |
| open-vsx.org | 45 | VS Code alt-marketplace |
| localhost:63342 | 43 | JetBrains IDE preview |
| 127.0.0.1:10000 | 28 | Lokal dev-server |
| mcpworld.com | 26 | MCP-katalog |
| doubao.com | 22 | ByteDance Doubao AI |
| code.mgdaas-int.com | 14 | Enterprise internt |
| baidu.ai | 14 | Baidu AI-plattform |
| yahoo.ai | 9 | Yahoo AI |
| yandex.ai | 7 | Yandex AI |
| skillsllm.com | 7 | LLM skills-katalog |
| google.ai | 7 | Google AI |
| github.com | 7 | GitHub direkt |
| mcpmarket.cn | 5 | Kinesisk MCP-marknad |
| mcp-servers.info | 4 | MCP-katalog |
| bing.ai | 4 | Bing AI |

**Exkluderat zarq.ai (intern):** 1,093 externa badge-referrals/30 dagar.

### D2. Daglig adoptionskurva

| Period | Requests/dag | Unika badges/dag | Event |
|---|---:|---:|---|
| Mar 15-18 | 800-1,800 | 267-502 | Baseline |
| Mar 19-22 | 1,100-2,400 | 700-1,900 | Outreach-rundor |
| Mar 23-30 | 2,600-5,800 | 2,000-4,300 | Organisk tillväxt |
| **Mar 31-Apr 1** | **9,400-9,700** | **6,200-6,700** | **ClaudeBot-spike** |
| Apr 2-14 | 2,900-8,700 | 2,500-5,700 | Stabil med variation |

**Observationer:**
- Mar 31-Apr 1 spike (9.7K/dag) sammanfaller exakt med ClaudeBot training crawl-explosionen (361K/dag). AI-crawlers indexerade badge-URLs som del av sin systematiska crawl.
- Unika badges ökade 10x (267→6,700) under mars, sedan stabiliserade vid ~3,000-5,000/dag.

### D3. User-agent-fördelning (badge requests, 30d)

| User-agent typ | Requests | % |
|---|---:|---:|
| Other bot (SEO, scrapers) | 58,372 | 46.7% |
| ClaudeBot | 18,535 | 14.8% |
| Chrome browser | 17,800 | 14.2% |
| Safari | 9,102 | 7.3% |
| Applebot | 8,549 | 6.8% |
| OpenAI (GPTBot/ChatGPT) | 7,712 | 6.2% |
| GitHub image proxy | 2,752 | 2.2% |
| Firefox | 1,486 | 1.2% |
| Googlebot | 378 | 0.3% |
| Bingbot | 297 | 0.2% |

**GitHub image proxy (2,752 requests) = 154 unika IPs.** Detta representerar repos vars README:er visar Nerq badges via GitHubs bild-cache (camo.githubusercontent.com). Dessa 154 repos har faktiskt embedding.

**Chrome+Safari+Firefox = 28,388 (22.7%)** — mänskliga besökare som ser badges i README:er, VS Code Marketplace, eller MCP-kataloger.

### D4. Specifika källor

| Referrer | Badge | Requests | Context |
|---|---|---:|---|
| gitee.com | MGdaasLab/WHartTest | 162 | Kinesiskt enterprise-repo med Nerq badge |
| marketplace.visualstudio.com | olasunkanmi-SE/codebuddy | 103 | VS Code extension med badge |
| mcpservers.org | call518/MCP-PostgreSQL-Ops | 71 | MCP-katalog med badge |

---

## DEL E — Klick-konvertering

### E1. Leder badges till trafik?

**0 besök till /safe/* sidor med badge-referrer** under 30 dagar.

**Förklaring:** Badges har inte `<a href>` wrapping i alla embedding-kontexter. GitHub README-badges har länk, men image-camo-proxyn tar bort referrer. VS Code Marketplace visar bilden utan klickbar länk.

**Badge-systemet driver INTE mätbar trafik till Nerq.** Dess värde ligger i brand-exposure, inte klick-konvertering.

---

## DEL F — Kontext

Shields.io serverar ~2.5 miljarder badge-requests/månad. Nerq serverar ~125K/månad (0.005% av shields.io). Codecov har ~100M badges/månad. Nerq's badge-system är i tidig adoptionsfas jämfört med etablerade badge-ekosystem.

---

## DEL G — Oförklarade mönster

### G1. Anomalier

1. **25,733 single-request badges (62%).** Dessa är troligen AI-crawlers som hämtar `/badge/{slug}` en gång under sin systematiska crawl av nerq.ai. Inte faktiska installationer.

2. **RTGS2017/NagaAgent: 1,080 requests.** Hög volym utan uppenbar referrer. Möjlig bot-loop eller badge-hot-linking från en populär sida.

3. **Mar 31 spike:** 9,418 badge-requests på en dag (3x normal). Sammanfaller med ClaudeBot 361K training-spike. ClaudeBot crawlade badge-URLs som del av sin `/{pattern}/*` systematiska indexering.

### G2. Potentiella problem

- **Ingen rate limiting på badge-endpoints.** En enskild bot kan requestra tusentals badges utan throttling.
- **Badge-score kan vara stale.** Om entity-score ändras men Redis-cache inte invalideras, visar badgen gammal data upp till 24h.
- **Ingen spam-detektion.** Vi vet inte om outreach-issues markerades som spam av GitHub.

---

## DEL H — Rå-data

Exporterat till `~/Desktop/April/badge-data/`:

| Fil | Innehåll |
|---|---|
| top-1000-badges.csv | Top 1000 badges: slug, requests, first/last request, unique referrers |
| daily-badge-adoption.csv | Daglig kurva: requests + unique badges |
| referrer-timeseries.csv | Referrer per dag per domain |
| badge_outreach_log.json | Full outreach-logg (230 targets, 23 runs) |

---

## Sammanfattning av fakta

| Metric | Värde |
|---|---:|
| Outreach targets | 230 |
| Issues skapade | 206 |
| Badge-requests/30d | ~125,000 |
| Unika badges requestade | 41,664 |
| Badges med ≥10 requests | 2,637 (6.3%) |
| GitHub image proxy requests | 2,752 (154 unika repos) |
| Externa referrers | 1,093 |
| Klick-konvertering → /safe/ | 0 |
| Outreach-status | **Stannat** — alla targets kontaktade |
| Discovery-pipeline | Existerar i kod men ej schemalagd |
