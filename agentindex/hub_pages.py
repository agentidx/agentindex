"""
Registry Hub Pages + Tiered Sitemaps
======================================
Hub pages: /apps, /npm, /pypi, /extensions, /vpns, /games, /wordpress-plugins, /websites, /desktop
Tiered sitemaps: Tier 1 (top 1K, priority 1.0), Tier 2 (top 10K, 0.8), Tier 3 (all, 0.6)

Usage:
    from agentindex.hub_pages import mount_hub_pages
    mount_hub_pages(app)
"""

import html as html_mod
import logging
import re
import time
from datetime import date

from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER, render_breadcrumb, render_footer

logger = logging.getLogger("nerq.hubs")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year
MY = date.today().strftime("%B %Y")

_cache = {}
CACHE_TTL = 3600

def _c(k):
    e = _cache.get(k)
    return e[1] if e and (time.time() - e[0]) < CACHE_TTL else None

def _sc(k, v):
    _cache[k] = (time.time(), v)
    return v

def _esc(t):
    return html_mod.escape(str(t)) if t else ""

def _slug(n):
    return re.sub(r"[^a-z0-9]+", "-", n.lower().strip()).strip("-")

def _fmt(n):
    if n is None: return "0"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return str(int(n))

def _gc(g):
    if not g: return "#6b7280"
    return {"A": "#16a34a", "B": "#0d9488", "C": "#ca8a04", "D": "#f97316"}.get(g[0].upper(), "#dc2626")


HUBS = {
    "apps": {"title": "Mobile App Trust Ratings", "registries": ["ios", "android"],
             "desc": "Trust scores for iOS and Android apps. Ratings, permissions, privacy analysis.",
             "route_prefix": "app"},
    "npm": {"title": "npm Package Trust Ratings", "registries": ["npm"],
            "desc": "Trust scores for npm packages. Security, maintenance, and community analysis.",
            "route_prefix": "npm"},
    "pypi": {"title": "PyPI Package Trust Ratings", "registries": ["pypi"],
             "desc": "Trust scores for Python packages. Security, licensing, and maintenance analysis.",
             "route_prefix": "pypi"},
    "extensions": {"title": "Browser Extension Trust Ratings", "registries": ["extension", "firefox"],
                   "desc": "Trust scores for Chrome and Firefox extensions. Permission analysis.",
                   "route_prefix": "extension"},
    "vpns": {"title": "VPN Trust Ratings — Independent, No Affiliate Links", "registries": ["vpn"],
             "desc": "Independent VPN trust scores. Jurisdiction, audit status, protocols. Zero affiliate links.",
             "route_prefix": "vpn"},
    "games": {"title": "Game Trust & Safety Ratings", "registries": ["steam"],
              "desc": "Trust scores for Steam games. Reviews, age ratings, developer track record.",
              "route_prefix": "steam"},
    "wordpress-plugins": {"title": "WordPress Plugin Trust Ratings", "registries": ["wordpress"],
                          "desc": "Trust scores for WordPress plugins. Active installs, compatibility, support.",
                          "route_prefix": "wordpress"},
    "websites": {"title": "Website Trust Checker", "registries": ["website"],
                 "desc": "Trust scores for websites. SSL, security headers, Tranco rank.",
                 "route_prefix": "website"},
    "desktop": {"title": "Desktop Software Trust Ratings", "registries": ["homebrew", "chocolatey"],
                "desc": "Trust scores for Homebrew formulae and Chocolatey packages.",
                "route_prefix": "homebrew"},
    "crates": {"title": "Rust Crate Trust Ratings", "registries": ["crates"],
               "desc": "Trust scores for Rust crates. Downloads, maintenance, licensing.",
               "route_prefix": "crates"},
    "go-packages": {"title": "Go Module Trust Ratings", "registries": ["go"],
                    "desc": "Trust scores for Go modules.",
                    "route_prefix": "go"},
    "nuget": {"title": "NuGet Package Trust Ratings", "registries": ["nuget"],
              "desc": "Trust scores for .NET NuGet packages.",
              "route_prefix": "nuget"},
    "packagist": {"title": "PHP Package Trust Ratings", "registries": ["packagist"],
                  "desc": "Trust scores for PHP Composer packages.",
                  "route_prefix": "packagist"},
    "gems": {"title": "Ruby Gem Trust Ratings", "registries": ["gems"],
             "desc": "Trust scores for Ruby gems.",
             "route_prefix": "gems"},
}


def _score_cls(score):
    """CSS class for trust score coloring."""
    if score is None:
        return "sc-mid"
    s = float(score)
    if s >= 80: return "sc-high"
    if s >= 60: return "sc-good"
    if s >= 40: return "sc-mid"
    if s >= 20: return "sc-low"
    return "sc-crit"


def _render_hub(hub_key):
    ck = f"hub:{hub_key}"
    c = _c(ck)
    if c: return c

    hub = HUBS.get(hub_key)
    if not hub: return None

    session = get_session()
    try:
        regs = hub["registries"]
        placeholders = ",".join(f"'{r}'" for r in regs)

        if "website" in regs:
            rows = session.execute(text(f"""
                SELECT domain as name, domain as slug, 'website' as registry,
                       trust_score, trust_grade, tranco_rank as downloads
                FROM website_cache ORDER BY tranco_rank ASC LIMIT 50
            """)).fetchall()
            total = session.execute(text("SELECT COUNT(*) FROM website_cache")).scalar() or 0
        else:
            # Try filtered query first (exclude garbage entries)
            rows = session.execute(text(f"""
                SELECT name, slug, registry, trust_score, trust_grade, downloads
                FROM software_registry WHERE registry IN ({placeholders})
                AND (downloads > 0 OR trust_score > 30 OR stars > 0)
                ORDER BY COALESCE(downloads, 0) DESC, COALESCE(trust_score, 0) DESC, name ASC LIMIT 20
            """)).fetchall()
            # Fall back to unfiltered if too few results
            if len(rows) < 5:
                rows = session.execute(text(f"""
                    SELECT name, slug, registry, trust_score, trust_grade, downloads
                    FROM software_registry WHERE registry IN ({placeholders})
                    ORDER BY COALESCE(downloads, 0) DESC, COALESCE(trust_score, 0) DESC, name ASC LIMIT 20
                """)).fetchall()
            total = session.execute(text(f"""
                SELECT COUNT(*) FROM software_registry WHERE registry IN ({placeholders})
            """)).scalar() or 0

        # Average score
        if "website" in regs:
            avg_score = session.execute(text("SELECT AVG(trust_score) FROM website_cache WHERE trust_score IS NOT NULL")).scalar()
        else:
            avg_score = session.execute(text(f"""
                SELECT AVG(trust_score) FROM software_registry WHERE registry IN ({placeholders}) AND trust_score IS NOT NULL
            """)).scalar()
        avg_score = avg_score or 0
    finally:
        session.close()

    prefix = hub["route_prefix"]
    title = f"{hub['title']} {YEAR} | Nerq"
    canonical = f"{SITE}/{hub_key}"
    hub_label = hub_key.replace("-", " ").title()
    dl_label = "Rank" if "website" in regs else "Downloads"

    # Breadcrumb
    breadcrumb = render_breadcrumb([
        (f"{SITE}/", "Nerq"),
        (None, hub_label),
    ])

    # Entity cards (top 20)
    cards_html = ""
    top_rows = rows[:20]
    for i, r in enumerate(top_rows, 1):
        nm = r[0].split("/")[-1] if "/" in str(r[0]) else r[0]
        sl = r[1]
        gr = r[4] or "D"
        sc = r[3] or 0
        dl = r[5] or 0
        sc_cls = _score_cls(sc)
        cards_html += f"""<div class="entity-card">
<span class="entity-rank">{i}</span>
<a href="/{prefix}/{sl}" style="flex:1">
<span class="entity-name">{_esc(nm)}</span>
<span class="entity-desc" style="display:block">{_esc(gr)} &middot; {_fmt(dl)} {dl_label.lower()}</span>
</a>
<span class="entity-score {sc_cls}">{sc:.0f}</span>
</div>
"""

    if not cards_html:
        cards_html = '<p style="color:#64748b;padding:20px 0">Crawling in progress&hellip;</p>'

    # JSON-LD ItemList
    ld_items = []
    for i, r in enumerate(top_rows, 1):
        nm = r[0].split("/")[-1] if "/" in str(r[0]) else r[0]
        sl = r[1]
        ld_items.append(f'{{"@type":"ListItem","position":{i},"url":"{SITE}/{prefix}/{sl}","name":"{_esc(nm)}"}}')
    jsonld = f"""<script type="application/ld+json">{{"@context":"https://schema.org","@type":"ItemList","name":"{_esc(hub['title'])}","numberOfItems":{len(top_rows)},"itemListElement":[{",".join(ld_items)}]}}</script>"""

    # Cross-links to other hubs
    cross_links = ""
    for k, h in HUBS.items():
        if k == hub_key:
            continue
        label = k.replace("-", " ").title()
        cross_links += f'<a href="/{k}" class="cross-link">{_esc(label)}</a>\n'
    cross_links += '<a href="/discover" class="cross-link">Discover</a>\n'
    cross_links += '<a href="/trending" class="cross-link">Trending</a>\n'

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(hub['desc'])} {total:,} entries indexed. Updated {MY}.">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(hub['desc'])}">
<meta name="nerq:type" content="hub">
<meta name="nerq:updated" content="{TODAY}">
<meta name="citation_title" content="{_esc(title)}">
<meta name="citation_author" content="Nerq">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
{jsonld}
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;line-height:1.6;background:#fff;font-size:15px}}
a{{color:#2563eb;text-decoration:none}}
.nav{{border-bottom:1px solid #e2e8f0;padding:10px 0;position:sticky;top:0;background:#fff;z-index:100}}
.nav-inner{{max-width:1100px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:16px}}
.nav-logo{{font-size:20px;font-weight:700;color:#0f172a;text-decoration:none}}
.nav-logo span{{font-weight:400;color:#64748b;font-size:13px;margin-left:6px}}
.nav-links{{display:flex;gap:16px;font-size:13px;margin-left:auto}}
.nav-links a{{color:#64748b;text-decoration:none}}
.container{{max-width:780px;margin:0 auto;padding:0 20px}}
.sc-high{{color:#16a34a}}.sc-good{{color:#22c55e}}.sc-mid{{color:#f59e0b}}.sc-low{{color:#ef4444}}.sc-crit{{color:#991b1b}}
</style>
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head>
<body>
{NERQ_NAV}
<main class="container" style="max-width:1000px;margin:0 auto;padding:24px 20px">
{breadcrumb}

<p style="font-size:15px;color:#374151;margin:12px 0 20px;line-height:1.7">
Nerq indexes <strong>{total:,}</strong> {hub_label.lower()} entries with independent trust scores.
{_esc(hub['desc'])} Each entity is scored 0&ndash;100 using automated analysis of security, maintenance,
community signals, and licensing. Average score: <strong>{avg_score:.0f}/100</strong>. Updated {MY}.</p>

<div style="margin:20px 0">
<h1 style="font-size:1.5rem;margin-bottom:12px">{_esc(hub['title'])} {YEAR}</h1>
<p class="desc">{_esc(hub['desc'])}</p>
</div>

<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:20px 0">
<div style="padding:16px;border:1px solid #e2e8f0;border-radius:8px;text-align:center">
<div style="font-size:26px;font-weight:700">{total:,}</div>
<div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.5px">Total Indexed</div>
</div>
<div style="padding:16px;border:1px solid #e2e8f0;border-radius:8px;text-align:center">
<div style="font-size:26px;font-weight:700">{avg_score:.0f}</div>
<div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.5px">Avg Score</div>
</div>
<div style="padding:16px;border:1px solid #e2e8f0;border-radius:8px;text-align:center">
<div style="font-size:26px;font-weight:700">{MY}</div>
<div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.5px">Last Updated</div>
</div>
</div>

<h2 style="font-size:1.15rem;margin:28px 0 12px">Top {len(top_rows)} by Popularity</h2>
<div class="entity-list">
{cards_html}
</div>

<div style="margin-top:28px;padding:18px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px">
<p style="font-size:14px;color:#374151;margin-bottom:8px"><strong>Check any {hub_key.replace("-"," ")}:</strong></p>
<pre style="background:#f1f5f9;padding:10px;font-size:12px;border-radius:6px;overflow-x:auto">curl nerq.ai/v1/preflight?target={{name}}</pre>
</div>

<div class="cross-links" style="margin-top:24px">
{cross_links}
</div>
</main>
{NERQ_FOOTER}
</body>
</html>"""

    return _sc(ck, page)


def mount_hub_pages(app):
    """Mount all registry hub pages + tiered sitemaps."""

    # Hub pages
    for hub_key in HUBS:
        def _mk(k=hub_key):
            async def handler():
                html = _render_hub(k)
                return HTMLResponse(html) if html else HTMLResponse(status_code=404, content="<h1>Hub not found</h1>")
            return handler
        app.get(f"/{hub_key}", response_class=HTMLResponse)(_mk())

    # Registry name → hub key aliases (e.g. /hub/steam → games, /hub/ios → apps)
    _HUB_ALIASES = {
        "steam": "games", "ios": "apps", "android": "apps",
        "firefox": "extensions", "chrome": "extensions", "vscode": "extensions",
        "homebrew": "desktop", "chocolatey": "desktop",
        "wordpress": "wordpress-plugins", "ai-tools": "apps",
        "crypto": "apps", "vpn": "vpns",
    }

    # Also mount at /hub/{key}
    @app.get("/hub/{hub_key}", response_class=HTMLResponse)
    async def hub_by_registry(hub_key: str):
        resolved = _HUB_ALIASES.get(hub_key, hub_key)
        html = _render_hub(resolved)
        return HTMLResponse(html) if html else HTMLResponse(status_code=404, content="<h1>Hub not found</h1>")

    # Tiered sitemaps
    @app.get("/sitemap-tier1.xml", response_class=Response)
    async def sitemap_tier1():
        """Top 1000 entities by downloads — highest priority."""
        ck = "sitemap:tier1"
        c = _c(ck)
        if c: return Response(c, media_type="application/xml")

        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT slug, registry, COALESCE(updated_at, created_at) AS lm
                FROM software_registry
                WHERE trust_score IS NOT NULL
                ORDER BY COALESCE(downloads, 0) DESC LIMIT 1000
            """)).fetchall()
        finally:
            session.close()

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for r in rows:
            slug, reg, lm = r[0], r[1], r[2]
            lm_str = lm.strftime("%Y-%m-%d") if lm else None
            lm_xml = f"<lastmod>{lm_str}</lastmod>" if lm_str else ""
            for pattern in [f"/{reg}/{slug}", f"/is-{slug}-safe", f"/what-is/{slug}",
                          f"/review/{slug}", f"/is-{slug}-legit"]:
                xml += f'<url><loc>{SITE}{pattern}</loc>{lm_xml}<priority>1.0</priority></url>\n'
        xml += '</urlset>'
        return Response(_sc(ck, xml), media_type="application/xml")

    @app.get("/sitemap-tier2.xml", response_class=Response)
    async def sitemap_tier2():
        """Top 10K entities — high priority."""
        ck = "sitemap:tier2"
        c = _c(ck)
        if c: return Response(c, media_type="application/xml")

        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT slug, registry, COALESCE(updated_at, created_at) AS lm
                FROM software_registry
                WHERE trust_score IS NOT NULL
                ORDER BY COALESCE(downloads, 0) DESC
                OFFSET 1000 LIMIT 9000
            """)).fetchall()
        finally:
            session.close()

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for r in rows:
            slug, reg, lm = r[0], r[1], r[2]
            lm_str = lm.strftime("%Y-%m-%d") if lm else None
            lm_xml = f"<lastmod>{lm_str}</lastmod>" if lm_str else ""
            xml += f'<url><loc>{SITE}/{reg}/{slug}</loc>{lm_xml}<priority>0.8</priority></url>\n'
            xml += f'<url><loc>{SITE}/is-{slug}-safe</loc>{lm_xml}<priority>0.8</priority></url>\n'
        xml += '</urlset>'
        return Response(_sc(ck, xml), media_type="application/xml")

    @app.get("/sitemap-tier3-{chunk}.xml", response_class=Response)
    async def sitemap_tier3(chunk: int):
        """All remaining entities — chunked at 50K."""
        ck = f"sitemap:tier3:{chunk}"
        c = _c(ck)
        if c: return Response(c, media_type="application/xml")

        offset = 10000 + chunk * 50000
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT slug, registry, COALESCE(updated_at, created_at) AS lm
                FROM software_registry
                WHERE trust_score IS NOT NULL
                ORDER BY COALESCE(downloads, 0) DESC
                OFFSET :off LIMIT 50000
            """), {"off": offset}).fetchall()
        finally:
            session.close()

        if not rows:
            return Response('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>',
                          media_type="application/xml")

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for r in rows:
            lm = r[2]
            lm_str = lm.strftime("%Y-%m-%d") if lm else None
            lm_xml = f"<lastmod>{lm_str}</lastmod>" if lm_str else ""
            xml += f'<url><loc>{SITE}/{r[1]}/{r[0]}</loc>{lm_xml}<priority>0.6</priority></url>\n'
        xml += '</urlset>'
        return Response(_sc(ck, xml), media_type="application/xml")

    # Hub sitemap — hubs are static derived pages, no DB-backed URL freshness.
    # Omit lastmod (Google: omitted = "must check", honest).
    @app.get("/sitemap-hubs.xml", response_class=Response)
    async def sitemap_hubs():
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for hub_key in HUBS:
            xml += f'<url><loc>{SITE}/{hub_key}</loc><priority>0.9</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    logger.info(f"Mounted {len(HUBS)} hub pages + tiered sitemaps")
