# M4b Audit — Apple Intelligence Extended Coverage

**Audited:** 2026-04-10 by Claude Code (Leverage Sprint Day 2 M4b)
**Status:** Read-only audit, deployment-ready design
**Blocks production:** no — design only
**Reviewer:** Anders + Claude chat session

---

## Step 1 — localized_routes.py

**File:** `agentindex/localized_routes.py`
**Size:** 1,034,363 bytes, 12,610 lines
**Mount point:** `discovery.py:1676-1677` — `mount_localized_routes(app)`

### Rendering architecture

Entity pages flow through `_render_localized_page()` (line 413), which calls `_render_agent_page(entity_slug, ..., lang=lang)` from `agent_safety_pages.py` (line 424-425). This means **localized entity pages use the same template** (`agent_safety_page.html`) as English pages — Apple meta tags added in M4a already flow through automatically.

Post-processing applies:
- Phrase-based string replacement for UI translations (lines 436-445)
- Internal link localization via `i18n/html_rewrite.py` (line 450-451)
- In-memory dict cache with 3600s TTL (lines 36-47, key format `l10n:{lang}:{pattern}:{slug}`)

The localized routes also do regex rewriting of `og:url` (lines 7085-7090) and `og:title`/`og:description` (lines 7098-8755) for ~20 languages. Apple meta tags (`apple-mobile-web-app-*`, `apple-touch-icon`, `format-detection`) are static/non-translatable and survive all post-processing unchanged.

### Languages

`SUPPORTED_LANGS` is derived from `URL_PATTERNS.keys()` in `translations.py:2013` minus "en" (line 33-34). 23 languages total (22 non-English):

`en, es, pt, fr, de, ja, ru, ko, it, tr, nl, pl, id, th, vi, hi, ar, sv, cs, ro, zh, da, no`

### Localized homepage path

Localized homepages (e.g. `/sv/`, `/de/`) are rendered by `render_localized_homepage()` from `homepage_i18n.py` (line 12265, 12296-12301). This file already has Apple meta tags from M4a:
- `homepage_i18n.py:3208-3212`: apple-mobile-web-app-capable, apple-mobile-web-app-status-bar-style, apple-mobile-web-app-title, apple-touch-icon, format-detection

### Route patterns

The mount function at line 12261 registers:
- `/{lang}/about`, `/{lang}/privacy`, `/{lang}/terms`, `/{lang}/discover` (lines 12289-12292)
- `/{lang}/` and `/{lang}` — homepage (lines 12301-12302)
- `/{lang}/{pattern_slug}` — catch-all for entity pages (line 12311)

Catch-all handles English patterns (lines 12318-12341: `is-{slug}-safe`, `is-{slug}-legit`, etc.), localized URL patterns (lines 12350-12360), best pages (lines 12396-12448), and categories (lines 12362-12382).

### M4b assessment for localized routes

**Entity pages: NO ACTION NEEDED.** Apple meta tags from M4a (`agent_safety_page.html:17-21`) already flow through `_render_agent_page()` to all 22 localized variants.

**Localized homepages: NO ACTION NEEDED.** Apple meta tags from M4a (`homepage_i18n.py:3208-3212`) already present.

**Gap: apple-touch-icon uses single generic icon** (`/static/nerq-logo-512.png`) rather than sized variants. When M4b generates sized icons, the `<link>` tags in both `agent_safety_page.html` and `homepage_i18n.py` need updating to reference the 4 sized variants. These changes will automatically propagate to all localized pages.

**Gap: No og:image on entity pages.** `agent_safety_page.html` has NO `og:image` tag (confirmed by grep — zero matches). Adding og:image to the template will also propagate to all 22 localized variants automatically.

**Gap: `_render_localized_page_minimal` fallback (line 12137) has its own `<head>` section.** This fallback renders when `_render_agent_page()` fails or returns empty HTML (line 426-430). Its `<head>` is at lines 12197-12214 — a standalone f-string with NO Apple meta tags, NO apple-touch-icon, NO format-detection, NO og:image. Only has: charset, viewport, title, description, canonical, hreflang, og:title, og:description, og:locale, nerq:* meta, robots. This path needs a separate patch to add Apple meta tags. Insert after line 12210 (robots meta) and before line 12211 (faq_ld):

```python
# Insert after line 12210, before line 12211:
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="{_esc(nm)} Trust">
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon-180.png">
<link rel="apple-touch-icon" sizes="167x167" href="/static/apple-touch-icon-167.png">
<link rel="apple-touch-icon" sizes="152x152" href="/static/apple-touch-icon-152.png">
<link rel="apple-touch-icon" sizes="120x120" href="/static/apple-touch-icon-120.png">
<meta name="format-detection" content="telephone=no">
<meta property="og:image" content="https://nerq.ai/static/nerq-logo-512.png">
```

---

## Step 2 — ab_test.py render_homepage

**File:** `agentindex/ab_test.py`
**Size:** 94,961 bytes, 1,824 lines
**Mount point:** `discovery.py:1429-1430` — `mount_ab_test(app)`

### Architecture

The root homepage `/` is served by `hub_page()` in `discovery.py:1721-1737`, which calls:
1. `get_variant(ip)` (ab_test.py:40) — deterministic IP-based variant assignment
2. `render_homepage(variant)` (ab_test.py:744) — assembles HTML

`render_homepage()` (line 744) returns: `_HEAD + _NERQ_NAV + hero_fn() + footer_sections + _STATIC_SECTIONS + cookie_banner + _TRACKING_SCRIPT`

### Shared `<head>` — all 4 variants share ONE `<head>`

`_HEAD` is a module-level string constant defined at line 202, spanning to line 316 (`</head>`). It contains:
- Google/Bing verification meta (lines 205-206)
- charset, viewport, title, description (lines 207-210)
- canonical, atom feed, hreflang tags for all 22 languages (lines 211-234)
- robots with max-snippet:-1 (line 235)
- og:title, og:description, og:url (lines 236-238) — **NO og:image, NO og:type, NO og:site_name**
- JSON-LD WebSite schema (lines 239-241)
- Full CSS inline (lines 242-312)
- External stylesheet link (line 314)

### 4 A/B variants differ ONLY in hero section

| Variant | Hero function | Line |
|---------|--------------|------|
| A | `_hero_a()` | 575 |
| B | `_hero_b()` | 621 |
| C | `_hero_c()` | 661 |
| D | `_hero_d()` | 691 |

Mapping at line 741: `HERO_VARIANTS = {"A": _hero_a, "B": _hero_b, "C": _hero_c, "D": _hero_d}`

### Current Apple meta tags: NONE

Grep for `apple-mobile-web-app|apple-touch-icon|format-detection|og:image` in ab_test.py: zero matches for Apple tags, zero for og:image.

### A/B tracking

Tracking happens via:
1. `log_ab_event()` called in `discovery.py:1735-1736` — logs IP, variant, is_bot, bot_name, event type
2. `_TRACKING_SCRIPT` (line 545) — client-side tracking at end of `<body>`

**Apple meta tag addition is safe for A/B tracking.** Meta tags are in `<head>`, tracking is in `<body>` and server-side. No interference.

### Proposed insertion point

Insert Apple meta tags and og:image into `_HEAD` after line 238 (`og:url`), before line 239 (`<script type="application/ld+json">`):

```python
# After line 238 (<meta property="og:url" ...>), add:
<meta property="og:image" content="https://nerq.ai/static/nerq-logo-512.png">
<meta property="og:image:width" content="512">
<meta property="og:image:height" content="512">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Nerq">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Nerq — Trust Scores">
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon-180.png">
<link rel="apple-touch-icon" sizes="167x167" href="/static/apple-touch-icon-167.png">
<link rel="apple-touch-icon" sizes="152x152" href="/static/apple-touch-icon-152.png">
<link rel="apple-touch-icon" sizes="120x120" href="/static/apple-touch-icon-120.png">
<meta name="format-detection" content="telephone=no">
```

**Single patch to `_HEAD` covers all 4 A/B variants.** No variant-specific changes needed.

---

## Step 3 — Apple touch-icon generation

### Pillow availability

**Available.** Pillow 12.1.1 installed in venv at `/Users/anstudio/agentindex/venv/bin/python`.

### Source image

**File:** `/Users/anstudio/agentindex/static/nerq-logo-512.png`
**Size:** 6,530 bytes
**Dimensions:** 512×512 px
**Mode:** RGBA (transparency)
**Format:** PNG

**Assessment:** 512×512 is sufficient for all 4 target sizes (180, 167, 152, 120). Square aspect ratio is correct for touch icons. RGBA mode should be converted to RGB with white background for touch icons (iOS ignores transparency on touch icons and renders black background).

### No sized icons exist yet

```
ls static/apple-touch-icon* → no matches
```

### Pre-generation script sketch

```python
#!/usr/bin/env python3
"""Generate Apple touch icons at 4 required sizes from nerq-logo-512.png."""
from PIL import Image
import os

SOURCE = "static/nerq-logo-512.png"
SIZES = [120, 152, 167, 180]

img = Image.open(SOURCE).convert("RGBA")

# Composite onto white background (iOS renders transparency as black)
bg = Image.new("RGB", img.size, (255, 255, 255))
bg.paste(img, mask=img.split()[3])  # Use alpha channel as mask

for size in SIZES:
    resized = bg.resize((size, size), Image.LANCZOS)
    out = f"static/apple-touch-icon-{size}.png"
    resized.save(out, "PNG", optimize=True)
    print(f"Generated {out} ({os.path.getsize(out)} bytes)")
```

### Template updates required

1. **`agent_safety_page.html:20`** — replace single `<link rel="apple-touch-icon" href="/static/nerq-logo-512.png">` with 4 sized variants
2. **`homepage_i18n.py:3211`** — same replacement
3. **`ab_test.py:_HEAD`** — add 4 sized variants (currently has none)

The sized `<link>` tags:
```html
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon-180.png">
<link rel="apple-touch-icon" sizes="167x167" href="/static/apple-touch-icon-167.png">
<link rel="apple-touch-icon" sizes="152x152" href="/static/apple-touch-icon-152.png">
<link rel="apple-touch-icon" sizes="120x120" href="/static/apple-touch-icon-120.png">
```

**Localized pages do NOT need separate patches** — they inherit from agent_safety_page.html template and homepage_i18n.py respectively.

---

## Step 4 — OG image generator

### Pillow availability

**Available.** Pillow 12.1.1.

### Memory analysis

```
Mac Studio current state (2026-04-10 11:28):
  PhysMem: 49G used, 14G unused (of 64G total)
  Compressor: 739M
  Swap: 5.1M out (low)
  CPU: 88.5% idle, load avg 4.33
```

Per-request memory for 1200×630 RGB image: **~2.2 MB raw**. With Pillow overhead (font cache, drawing context): ~3-5 MB peak per request. Acceptable given 14G unused.

### Font availability

- **System fonts:** Helvetica available at `/System/Library/Fonts/Helvetica.ttc`
- **Design fonts (DM Serif Display, JetBrains Mono, DM Sans):** NOT installed locally, NOT in static/
- **Fallback:** LiberationSans in `integrations/elizaos/node_modules/pdfjs-dist/standard_fonts/` (not ideal for production)

**Recommendation:** Download DM Sans (body) and DM Serif Display (headings) as .ttf files into `static/fonts/` for consistent branding with the Nerq design system.

### Route design

```python
@app.get("/og/{slug}.png")
async def og_image(slug: str):
    """Generate 1200x630 OG card for entity."""
    from PIL import Image, ImageDraw, ImageFont
    import io, hashlib

    # 1. Look up entity
    from agentindex.agent_safety_pages import _resolve_entity
    entity = _resolve_entity(slug)
    if not entity:
        return Response(status_code=404)

    # 2. Build card
    img = Image.new("RGB", (1200, 630), "#fafaf9")
    draw = ImageDraw.Draw(img)
    # ... entity name (large), trust score + grade, category, Nerq branding

    # 3. Serialize
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    buf.seek(0)

    # 4. ETag from content hash
    etag = hashlib.md5(buf.getvalue()).hexdigest()

    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=604800, s-maxage=604800, immutable",
            "CDN-Cache-Control": "public, max-age=604800, immutable",
            "ETag": f'"{etag}"',
        },
    )
```

### Card layout sketch

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                                                         │ │
│  │   [Nerq logo]  nerq.ai                                 │ │
│  │                                                         │ │
│  │   NordVPN                              ┌─────────┐     │ │
│  │   VPN Service                          │  A  85  │     │ │
│  │                                        │ /100    │     │ │
│  │   Independent Trust Score              └─────────┘     │ │
│  │   by Nerq — Is It Safe?                                │ │
│  │                                                         │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Data source

`_resolve_entity(slug)` from `agent_safety_pages.py` (same as used by `_render_localized_page` at `localized_routes.py:56`). Returns dict with `name`, `trust_score`, `trust_grade`, `category`, `description`, `author`.

### Cache strategy

`Cache-Control: public, max-age=604800, s-maxage=604800, immutable` — Cloudflare caches after first hit for 7 days. Each unique slug generates one image. For 37,688 Kings × ~15KB average PNG = ~550 MB in Cloudflare edge cache. Acceptable.

### Module-level font caching

```python
# Module-level — loaded once, reused across requests
_FONT_TITLE = None
_FONT_BODY = None

def _get_fonts():
    global _FONT_TITLE, _FONT_BODY
    if _FONT_TITLE is None:
        _FONT_TITLE = ImageFont.truetype("static/fonts/DMSerifDisplay-Regular.ttf", 56)
        _FONT_BODY = ImageFont.truetype("static/fonts/DMSans-Regular.ttf", 28)
    return _FONT_TITLE, _FONT_BODY
```

### Fallback plan (if Pillow is too heavy)

Serve one static PNG per trust grade: A+, A, A-, B+, B, B-, C+, C, D, F — 10 static files. Template sets og:image to `/static/og-grade-{grade}.png`. Pre-generate once. No per-request rendering. ~150 KB total disk.

### Route insertion point

Best location: `discovery.py:1697` area (after widget.js, before End Compliance Layer). Or create a separate module `agentindex/og_image.py` with `mount_og_image(app)` and add mount at `discovery.py:~1677` alongside other mounts. **Critical:** must be added BEFORE the catch-all static mount at `discovery.py:2238` (`app.mount("/", StaticFiles(...))`), which swallows all unmatched routes.

### Template update

Add to `agent_safety_page.html` (after line 16 or wherever og:url is):
```html
<meta property="og:image" content="https://nerq.ai/og/{{ slug }}.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
```

---

## Step 5 — ETag support

### Current cache middleware

**File:** `agentindex/api/discovery.py`
**Lines:** 187-304 (PageCacheMiddleware class)
**Class:** `PageCacheMiddleware(BaseHTTPMiddleware)` (line 189)

### Current flow

1. Request arrives at `dispatch()` (line 227)
2. Non-GET/HEAD skipped (line 228-229)
3. Non-cacheable paths skipped (line 234-235, excludes `/v1/`, `/flywheel`, `/dashboard`, etc.)
4. Redis connection obtained (line 245-247)
5. Cache key: `f"pc:{path}"` (line 249) — simple path-based key
6. Path-aware CDN TTLs computed (lines 251-264):
   - Entity pages: `s-maxage=86400`
   - Ranking pages: `s-maxage=86400`
   - Homepage: `s-maxage=3600`
   - Everything else: `s-maxage=43200`
   - Browser: always `max-age=300`
7. Cache hit → return cached body with `X-Cache: HIT` (lines 267-277)
8. Cache miss → call next, read body, store in Redis with `_TTL=14400`, return with `X-Cache: MISS` (lines 281-301)

### No existing ETag support

Grep for `ETag|etag|If-None-Match|304` in discovery.py: **zero matches**. No conditional request handling exists anywhere.

### ETag generation design

Generate ETag from content hash of cached body:

```python
import hashlib

# In cache HIT path (after line 267):
cached = r.get(cache_key)
if cached:
    etag = f'"{hashlib.md5(cached).hexdigest()}"'

    # Handle If-None-Match
    client_etag = request.headers.get("if-none-match", "")
    if client_etag == etag:
        return StarletteResponse(
            content=b"",
            status_code=304,
            headers={
                "ETag": etag,
                "Cache-Control": _cc,
                "CDN-Cache-Control": _cdn_cc,
            }
        )

    return StarletteResponse(
        content=cached,
        media_type="text/html; charset=utf-8",
        headers={
            "X-Cache": "HIT",
            "ETag": etag,
            "Cache-Control": _cc,
            "CDN-Cache-Control": _cdn_cc,
        }
    )

# In cache MISS path (after line 289):
# Also compute and return ETag
etag = f'"{hashlib.md5(body).hexdigest()}"'
# ... include in response headers
```

### Insertion points

1. **Cache HIT path:** Lines 267-277 — add ETag computation and If-None-Match check before returning
2. **Cache MISS path:** Lines 292-301 — add ETag to response headers
3. **md5 import:** Add at top of file or use `hashlib` (already available in Python stdlib)

### Risk assessment

**Medium risk.** ETag changes affect ALL cached responses, not just entity pages. Considerations:

1. **Positive:** Applebot and all crawlers benefit from efficient re-crawling (304 saves bandwidth)
2. **Positive:** Reduces server bandwidth for repeat visitors
3. **Risk:** md5 computation on every cache hit adds ~0.1ms per request. For cached content up to 200KB (line 288), this is negligible
4. **Risk:** If Cloudflare's CDN cache layer also sends If-None-Match, we may see unexpected 304s. However, Cloudflare handles origin ETags correctly
5. **Risk:** The fallback cache middleware (lines 564-591) does NOT set ETags — only PageCacheMiddleware would. Pages that bypass Redis (cache down, non-cacheable) won't have ETags. This is acceptable — ETags are an optimization, not a requirement

**Mitigation:** Deploy and test with a single entity page first (`/safe/nordvpn`), verify via `curl -I` with `If-None-Match` header before enabling site-wide.

---

## Step 6 — Applebot analytics panel

### Current flywheel_dashboard.py structure

**File:** `agentindex/flywheel_dashboard.py`
**Size:** 75,190 bytes, 1,327 lines
**Mount:** `discovery.py:1348-1349` — `mount_flywheel(app)`

### Current Apple treatment

Apple is currently classified as a **search bot** (not AI bot), grouped with Google/Bing/Yandex/DuckDuck:
- `flywheel_dashboard.py:190`: `bot_name IN ('Google','Bing','Yandex','Apple','DuckDuck')`
- `flywheel_dashboard.py:193`: excluded from `other_bots`
- `flywheel_dashboard.py:570`: same grouping

**No dedicated Applebot panel exists.**

### Dashboard layout (relevant sections)

```
{cards}            — top-level KPIs
{chart_html}       — traffic trend chart
{funnel_section}   — conversion funnel
{pipeline_table}   — pipeline metrics
{citation_table}   — citation tracking
{efficiency_table} — efficiency metrics
{demand_table}     — demand metrics
{enrichment_section} — enrichment stats
{kings_section}    — Kings analytics (lines 955-991)
{growth_section}   — growth metrics
{crawl_trend_section} — crawl trends
{lang_section}     — language breakdown
{infra_section}    — infrastructure
{ai_share_section} — AI share
```

### Proposed insertion point

Two insertion options:

**Option A (inline, line 839):** Add Applebot to the bot summary bar (lines 830-838) alongside Claude, ChatGPT, ByteDance, Perplexity. Quick win — just adds Apple volume to existing bot summary.

**Option B (section, line 1249):** Add `{applebot_section}` after `{kings_section}` and before `{growth_section}` in the `_render()` output. This adds a full dedicated Applebot panel with all 5 sub-panels. Requires matching data queries in `_get_data()` (line 144+).

**Recommended:** Both. Option A for at-a-glance volume, Option B for deep analysis.

### Chart rendering

The dashboard uses **Chart.js 4** (CDN at line 812) for 3 chart instances (trendChart, growthChart, crawlChart) via `<canvas>` elements, plus inline HTML tables for static data. SQL queries are inline f-string text within `_get_data()` (line 144). Bot summaries for Claude, ChatGPT, ByteDance, Perplexity appear at lines 830-838 as inline HTML spans — no Apple in this section.

### 5 panel designs with SQL

**Panel a: Daily Applebot request volume 7-day trend**

```sql
SELECT date(ts) as day, COUNT(*) as reqs
FROM requests
WHERE bot_name = 'Apple'
  AND ts >= date('now', '-7 days')
GROUP BY date(ts)
ORDER BY day
```

Render as: HTML table with sparkline-style bar chart (CSS `width: {pct}%` bars).

**Panel b: Top 20 paths requested by Applebot**

```sql
SELECT path, COUNT(*) as hits
FROM requests
WHERE bot_name = 'Apple'
  AND ts >= date('now', '-7 days')
GROUP BY path
ORDER BY hits DESC
LIMIT 20
```

Render as: HTML table with path, hit count, percentage bar.

**Panel c: Applebot vs Claude vs ChatGPT vs Perplexity daily comparison**

```sql
SELECT date(ts) as day,
  SUM(CASE WHEN bot_name = 'Apple' THEN 1 ELSE 0 END) as apple,
  SUM(CASE WHEN bot_name = 'Claude' THEN 1 ELSE 0 END) as claude,
  SUM(CASE WHEN bot_name = 'ChatGPT' THEN 1 ELSE 0 END) as chatgpt,
  SUM(CASE WHEN bot_name = 'Perplexity' THEN 1 ELSE 0 END) as perplexity
FROM requests
WHERE is_bot = 1
  AND bot_name IN ('Apple', 'Claude', 'ChatGPT', 'Perplexity')
  AND ts >= date('now', '-7 days')
GROUP BY date(ts)
ORDER BY day
```

Render as: Multi-row HTML table with color-coded percentage bars per bot.

**Panel d: Safari/Apple referrer patterns**

```sql
SELECT referrer_domain, COUNT(*) as hits
FROM requests
WHERE is_bot = 0
  AND referrer_domain IS NOT NULL
  AND (referrer_domain LIKE '%apple%'
    OR referrer_domain LIKE '%safari%'
    OR referrer_domain LIKE '%siri%'
    OR referrer_domain LIKE '%spotlight%')
  AND ts >= date('now', '-7 days')
GROUP BY referrer_domain
ORDER BY hits DESC
LIMIT 20
```

Render as: HTML table. Note: this panel may return zero rows if Apple AI citations don't set referrer headers — that's a valid finding.

**Panel e: Applebot response code breakdown**

```sql
SELECT
  CASE WHEN status >= 200 AND status < 300 THEN '2xx'
       WHEN status >= 300 AND status < 400 THEN '3xx'
       WHEN status >= 400 AND status < 500 THEN '4xx'
       WHEN status >= 500 THEN '5xx'
       ELSE 'other' END as code_class,
  COUNT(*) as hits
FROM requests
WHERE bot_name = 'Apple'
  AND ts >= date('now', '-7 days')
GROUP BY code_class
ORDER BY hits DESC
```

Render as: Single-row summary with color-coded status badges (green for 2xx, yellow for 3xx, red for 4xx/5xx).

### Data source code sketch

Add to `_get_data()` function:

```python
# Applebot section
apple_trend = session.execute(text("""...""")).fetchall()
apple_paths = session.execute(text("""...""")).fetchall()
apple_compare = session.execute(text("""...""")).fetchall()
apple_referrers = session.execute(text("""...""")).fetchall()
apple_status = session.execute(text("""...""")).fetchall()
data["applebot"] = {
    "trend": apple_trend,
    "paths": apple_paths,
    "compare": apple_compare,
    "referrers": apple_referrers,
    "status": apple_status,
}
```

Note: These queries hit analytics.db (SQLite), not Postgres. The `session` used for other dashboard queries is the SQLite session via `get_analytics_session()` or equivalent. Verify which session object is used at the top of `_get_data()`.

---

## Step 7 — max-age discrepancy

### Investigation

**Code-set value:** `max-age=300` at `discovery.py:263`
```python
_cc = f"public, max-age=300, s-maxage={_smaxage}, stale-while-revalidate=86400"
```

**Live response:** `max-age=14400`
```
cache-control: public, max-age=14400, s-maxage=86400, stale-while-revalidate=86400
```

**CDN-Cache-Control is unchanged:** `public, max-age=86400, stale-while-revalidate=86400` — matches code at `discovery.py:264`.

### Grep for "14400" in codebase

Only two locations:
1. `discovery.py:192` — `_TTL = 14400  # 4 hours — pages rarely change, enrichment flushes cache` (Redis cache TTL)
2. `crawlers/rate_limit_mapper.py:59-60` — unrelated rate limit config

### Cloudflare config

`~/.cloudflared/config.yml` contains only tunnel/ingress config — no cache rules, no transform rules. The rewrite is NOT in cloudflared.

### Root cause

**Cloudflare "Browser Cache TTL" setting** (configured in Cloudflare dashboard, not visible from server). When Cloudflare sees a `Cache-Control` header with `max-age=300` and the dashboard-configured "Browser Cache TTL" is 14400 (4 hours), Cloudflare rewrites `max-age` to the higher value.

Evidence:
- Only `max-age` is rewritten (300 → 14400), not `s-maxage` or `stale-while-revalidate`
- `CDN-Cache-Control` is untouched (Cloudflare only rewrites `Cache-Control`)
- 14400 seconds = 4 hours, a common Cloudflare Browser Cache TTL preset
- The coincidence with `_TTL = 14400` (Redis) suggests intentional alignment

### Recommendation

**Accept and document.** The 4-hour browser cache TTL is reasonable for a site where trust scores change daily. If Anders wants to reduce browser cache time (e.g. for faster score updates to human visitors), change the Cloudflare Browser Cache TTL setting in the dashboard, not the code. The code's `max-age=300` is being overridden and is effectively dead code.

**Optional:** Change code to `max-age=14400` to match reality and prevent confusion in future audits.

---

## Step 8 — Duplicate index cleanup

### Current indices on `requests` table

```sql
SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='requests';
```

| Index | Definition | Size |
|-------|-----------|------|
| `idx_ts` | `CREATE INDEX idx_ts ON requests(ts)` | 601 MB |
| `idx_requests_ts` | `CREATE INDEX idx_requests_ts ON requests(ts)` | 582 MB |
| `idx_path` | `CREATE INDEX idx_path ON requests(path)` | — |
| `idx_bot` | `CREATE INDEX idx_bot ON requests(is_bot)` | — |
| `idx_ai_bot` | `CREATE INDEX idx_ai_bot ON requests(is_ai_bot)` | — |
| `idx_requests_duration` | `CREATE INDEX idx_requests_duration ON requests(ts, duration_ms)` | — |
| `idx_requests_bot` | `CREATE INDEX idx_requests_bot ON requests(ts, is_ai_bot, bot_name)` | — |

### Duplicate confirmed

`idx_ts` and `idx_requests_ts` are **exact duplicates** — both index only `(ts)` on the `requests` table. Combined size: **1.18 GB** of wasted disk on an 8.77 GB database.

### Table stats

- **Row count:** 14,747,748 rows
- **Page size:** 4,096 bytes
- **Total pages:** 2,278,101 (= 9.33 GB total database)

### Drop recommendation

**Drop `idx_ts`** (the less descriptive name). Keep `idx_requests_ts` as the canonical ts index.

```sql
DROP INDEX idx_ts;
VACUUM;  -- reclaim space (WARNING: may take minutes and temporarily doubles DB size)
```

**Alternative without VACUUM:**
```sql
DROP INDEX idx_ts;
-- Space is reclaimed lazily as SQLite reuses freed pages
```

### Timing estimate

- `DROP INDEX`: near-instant (< 1 second) — just removes the index metadata
- `VACUUM`: likely 3-10 minutes for a 9.33 GB database, temporarily needs ~9 GB additional disk space during operation. **Run during low-traffic window.**

### Risk

**Low risk.** SQLite query planner will use `idx_requests_ts` instead of `idx_ts` — they're identical. Also, `idx_requests_bot` and `idx_requests_duration` both have `ts` as their leading column, providing additional coverage.

**Pre-deployment check:** Verify no code references `idx_ts` by name (e.g., `INDEXED BY idx_ts`):

```bash
grep -rn "idx_ts" agentindex/ scripts/ --include="*.py"
```

---

## Overall risk assessment for M4b deployment

1. **LOW — Touch icon generation (Step 3):** Pre-generated static files, zero runtime risk. Only risk: RGBA-to-RGB conversion producing poor visual quality (test with a quick render).

2. **LOW — ab_test.py Apple meta tags (Step 2):** Single insertion into `_HEAD` constant. All 4 variants share it. No A/B tracking interference.

3. **LOW — localized_routes meta tags (Step 1):** No direct patch needed — tags inherit from template. Only sized touch-icon updates to template propagate automatically.

4. **LOW — Duplicate index drop (Step 8):** Straightforward index removal. VACUUM timing risk during peak traffic.

5. **MEDIUM — ETag support (Step 5):** Touches the hot path of every cached response. md5 per-request is cheap but any bug in 304 handling could serve empty pages. Needs careful testing.

6. **MEDIUM — Applebot dashboard panels (Step 6):** 5 new SQL queries against analytics.db (8.77 GB, 14.7M rows). Query performance on `bot_name = 'Apple'` depends on whether `idx_requests_bot` covers it (it does — leading column is `ts`, with `is_ai_bot, bot_name`). But Apple is classified as `is_ai_bot=0`, so the index may not efficiently filter. Consider adding `WHERE ts >= date('now', '-7 days')` to use the ts index first.

7. **MEDIUM — OG image generator (Step 4):** Per-request Pillow rendering at ~3-5 MB peak per request. With Cloudflare caching, most requests are cache hits. But initial crawl of 37K+ entities could spike memory. Fallback plan (static grade images) is safer.

8. **LOW-MEDIUM — max-age discrepancy (Step 7):** No action needed (documentation only), but should be communicated to Anders for awareness.

---

## Proposed deployment order

1. **Step 3 — Touch icon generation** (5 minutes). Pre-generate 4 PNGs, verify visual quality. No code changes, just file creation.

2. **Step 2 — ab_test.py Apple meta tags** (10 minutes). Single `_HEAD` patch. Add og:image, apple meta tags. Test with `curl / | grep apple`.

3. **Step 1 — Template updates for sized touch icons** (10 minutes). Update `agent_safety_page.html:20` and `homepage_i18n.py:3211` to reference 4 sized icons. Test localized page renders.

4. **Step 8 — Duplicate index cleanup** (5 minutes + VACUUM time). Drop idx_ts, optionally VACUUM during low-traffic window.

5. **Step 5 — ETag support** (30 minutes). Deploy, test with curl If-None-Match against `/safe/nordvpn`. Verify 304 returns empty body with correct headers.

6. **Step 6 — Applebot dashboard panels** (45 minutes). Add 5 SQL queries + HTML rendering. Test query performance individually before integrating.

7. **Step 4 — OG image generator** (60 minutes). Start with fallback plan (10 static grade images) for immediate og:image coverage. Dynamic per-entity generation is Phase 2.

8. **Step 7 — max-age documentation** (5 minutes). Update comments in discovery.py:263 to note Cloudflare Browser Cache TTL override.

**Rationale:** Deploy low-risk, high-impact changes first (touch icons, meta tags). Database cleanup next (easy win). Then progressively riskier items (ETag, dashboard, OG images).

---

## Open questions

1. **Cloudflare Browser Cache TTL:** Is the 14400-second (4-hour) Browser Cache TTL intentionally set? Should we change it to match the code's intended 300 seconds, or accept the current behavior?

2. **OG image fonts:** DM Serif Display and DM Sans are not installed on Mac Studio. Should we download them to `static/fonts/` for branded OG cards, or use system Helvetica?

3. **OG image strategy:** Start with the fallback plan (10 static grade images) or go directly to per-entity dynamic generation? Fallback is safer for memory pressure but less differentiated for social sharing.

4. **Applebot classification:** Apple is currently classified as a search bot (`is_ai_bot=0`). Should this be reclassified as AI bot for analytics purposes? Apple Intelligence (Siri, Spotlight AI) is an AI-mediated search experience. This affects how Applebot appears in the AI share dashboard section.

5. **VACUUM timing:** The `VACUUM` after dropping `idx_ts` temporarily needs ~9 GB free disk. Is there enough free disk on Mac Studio? Should it run during a maintenance window?

6. **Redis cache flush after meta tag deployment:** Adding Apple meta tags changes page content. Should we flush the Redis page cache (`FLUSHDB` on db 1) to ensure crawlers see updated pages immediately, or let the 4-hour TTL expire naturally?

---

## Appendix A: raw grep output

### Apple meta tags in codebase (post-M4a)
```
agentindex/homepage_i18n.py:3208:<meta name="apple-mobile-web-app-capable" content="yes">
agentindex/homepage_i18n.py:3209:<meta name="apple-mobile-web-app-status-bar-style" content="default">
agentindex/homepage_i18n.py:3210:<meta name="apple-mobile-web-app-title" content="Nerq Trust Scores">
agentindex/homepage_i18n.py:3211:<link rel="apple-touch-icon" href="/static/nerq-logo-512.png">
agentindex/homepage_i18n.py:3212:<meta name="format-detection" content="telephone=no">
agentindex/templates/agent_safety_page.html:17:<meta name="apple-mobile-web-app-capable" content="yes">
agentindex/templates/agent_safety_page.html:18:<meta name="apple-mobile-web-app-status-bar-style" content="default">
agentindex/templates/agent_safety_page.html:19:<meta name="apple-mobile-web-app-title" content="{{ display_name }} Trust">
agentindex/templates/agent_safety_page.html:20:<link rel="apple-touch-icon" href="/static/nerq-logo-512.png">
agentindex/templates/agent_safety_page.html:21:<meta name="format-detection" content="telephone=no">
```

### og:image in codebase
```
agentindex/homepage_i18n.py:3205:<meta property="og:image" content="https://nerq.ai/static/nerq-logo-512.png">
agentindex/homepage_i18n.py:3206:<meta property="og:image:width" content="512">
agentindex/homepage_i18n.py:3207:<meta property="og:image:height" content="512">
(NO og:image in agent_safety_page.html or ab_test.py)
```

### 14400 in codebase
```
agentindex/api/discovery.py:192:    _TTL = 14400  # Redis TTL
agentindex/crawlers/rate_limit_mapper.py:59-60:  (unrelated — rate limit rpd)
```

### Cache-Control in discovery.py
```
Line 263: max-age=300 (browser), s-maxage varies (CDN)
Line 264: CDN-Cache-Control max-age matches s-maxage
Line 274: Cache HIT response
Line 298: Cache MISS response
Lines 566-591: Fallback middleware (only if cache-control not already set)
```

## Appendix B: raw sqlite3 output

### Indices on requests table
```
idx_ts|requests|CREATE INDEX idx_ts ON requests(ts)
idx_path|requests|CREATE INDEX idx_path ON requests(path)
idx_bot|requests|CREATE INDEX idx_bot ON requests(is_bot)
idx_ai_bot|requests|CREATE INDEX idx_ai_bot ON requests(is_ai_bot)
idx_requests_ts|requests|CREATE INDEX idx_requests_ts ON requests(ts)
idx_requests_duration|requests|CREATE INDEX idx_requests_duration ON requests(ts, duration_ms)
idx_requests_bot|requests|CREATE INDEX idx_requests_bot ON requests(ts, is_ai_bot, bot_name)
```

### Index sizes (duplicate pair)
```
idx_ts:          601,354,240 bytes (601 MB)
idx_requests_ts: 581,898,240 bytes (582 MB)
Combined waste:  1,183,252,480 bytes (1.18 GB)
```

### Table stats
```
Row count:  14,747,748
Page size:  4,096 bytes
Page count: 2,278,101
Total DB:   ~9.33 GB
```

### requests table schema
```sql
CREATE TABLE requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    method TEXT,
    path TEXT,
    status INTEGER,
    duration_ms REAL,
    ip TEXT,
    user_agent TEXT,
    bot_name TEXT,
    is_bot INTEGER DEFAULT 0,
    is_ai_bot INTEGER DEFAULT 0,
    referrer TEXT,
    referrer_domain TEXT,
    query_string TEXT,
    search_query TEXT,
    country TEXT,
    ai_source TEXT,
    visitor_type TEXT
)
```

### Memory status (2026-04-10 11:28)
```
PhysMem: 49G used, 14G unused (64G total)
Compressor: 739M
CPU: 88.5% idle, load avg 4.33
Swap: 5.1M swapouts total (lifetime, not current)
```
