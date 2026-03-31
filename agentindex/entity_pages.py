"""
Nerq Entity Rating Pages & API
================================
- /software/{slug}, /company/{slug}, /government/{slug}, /university/{slug}
- /index/sp500, /index/saas, /index/ftse100, /index/government, /index/universities
- /industry/{name}
- /company/{a}-vs-{b}, /software/{a}-vs-{b}
- /v1/entity/{type}/{slug}
- /v1/index/{index_name}
- Sitemaps

Usage:
    from agentindex.entity_pages import mount_entity_pages
    mount_entity_pages(app)
"""

import html as html_mod
import json
import logging
import re
import time
from datetime import date

from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.intelligence.rating_engine import rating_color, score_to_rating
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.entity_pages")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year
MONTH_YEAR = date.today().strftime("%B %Y")
METHODOLOGY = "Based on analysis of public GitHub repositories, published dependencies, and public documentation. Ratings reflect publicly observable AI stack health and may not represent the complete internal technology stack."

_cache = {}
CACHE_TTL = 3600


def _cached(key):
    e = _cache.get(key)
    if e and (time.time() - e[0]) < CACHE_TTL:
        return e[1]
    return None

def _set_cache(key, val):
    _cache[key] = (time.time(), val)
    return val

def _esc(t):
    return html_mod.escape(str(t)) if t else ""

def _to_slug(name):
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

def _fmt_num(n):
    if n is None: return "0"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return str(int(n))

def _get_entity(entity_type, slug):
    session = get_session()
    try:
        row = session.execute(text("""
            SELECT entity_name, entity_slug, display_name, github_org, website,
                   industry, country, ticker, stock_index,
                   rating, score, tools_found, dependencies_total,
                   critical_issues, health_warnings,
                   tool_breakdown, risk_factors, predictions, compliance_signals,
                   scanned_at, updated_at
            FROM entity_ratings
            WHERE entity_type = :etype AND entity_slug = :slug
        """), {"etype": entity_type, "slug": slug}).fetchone()
        if row:
            return dict(zip(["name","slug","display_name","github_org","website",
                           "industry","country","ticker","index",
                           "rating","score","tools_found","deps_total",
                           "critical","warnings",
                           "tool_breakdown","risk_factors","predictions","compliance",
                           "scanned_at","updated_at"], row))
    finally:
        session.close()
    return None

def _get_entities_by_type(entity_type, limit=200):
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT entity_name, entity_slug, display_name, industry, country,
                   ticker, stock_index, rating, score, tools_found, critical_issues
            FROM entity_ratings
            WHERE entity_type = :etype
            ORDER BY score DESC NULLS LAST
            LIMIT :lim
        """), {"etype": entity_type, "lim": limit}).fetchall()
        return [dict(zip(["name","slug","display_name","industry","country",
                         "ticker","index","rating","score","tools","critical"], r)) for r in rows]
    finally:
        session.close()

def _get_entities_by_index(index_name, limit=200):
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT entity_name, entity_slug, display_name, entity_type, industry, country,
                   ticker, rating, score, tools_found, critical_issues
            FROM entity_ratings
            WHERE stock_index = :idx
            ORDER BY score DESC NULLS LAST
            LIMIT :lim
        """), {"idx": index_name, "lim": limit}).fetchall()
        return [dict(zip(["name","slug","display_name","type","industry","country",
                         "ticker","rating","score","tools","critical"], r)) for r in rows]
    finally:
        session.close()

def _get_entities_by_industry(industry, limit=200):
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT entity_name, entity_slug, display_name, entity_type, country,
                   ticker, stock_index, rating, score, tools_found, critical_issues
            FROM entity_ratings
            WHERE LOWER(industry) = :ind
            ORDER BY score DESC NULLS LAST
            LIMIT :lim
        """), {"ind": industry.lower(), "lim": limit}).fetchall()
        return [dict(zip(["name","slug","display_name","type","country",
                         "ticker","index","rating","score","tools","critical"], r)) for r in rows]
    finally:
        session.close()


def _render_entity_page(entity_type, slug, route_prefix):
    ck = f"entity:{entity_type}:{slug}"
    c = _cached(ck)
    if c: return c

    e = _get_entity(entity_type, slug)
    if not e: return None

    name = e["display_name"] or e["name"]
    rating = e["rating"] or "NR"
    score = e["score"] or 0
    rc = rating_color(rating)
    tools = e["tools_found"] or 0
    deps = e["deps_total"] or 0
    critical = e["critical"] or 0
    warnings = e["warnings"] or 0
    industry = e["industry"] or ""
    country = e["country"] or ""
    ticker = e["ticker"] or ""
    website = e["website"] or ""

    _tb = e["tool_breakdown"]
    tool_breakdown = json.loads(_tb) if isinstance(_tb, str) else (_tb if _tb else [])
    _rf = e["risk_factors"]
    risk_factors = json.loads(_rf) if isinstance(_rf, str) else (_rf if _rf else [])
    _pr = e["predictions"]
    predictions = json.loads(_pr) if isinstance(_pr, str) else (_pr if _pr else {})

    # Type-specific titles
    titles = {
        "saas": f"Is {_esc(name)} AI Safe? Stack Rating {YEAR} | Nerq",
        "company": f"{_esc(name)} AI Risk Rating — Stack Analysis {YEAR} | Nerq",
        "government": f"{_esc(name)} AI Transparency Rating {YEAR} | Nerq",
        "university": f"{_esc(name)} AI Research Rating {YEAR} | Nerq",
    }
    title = titles.get(entity_type, f"{_esc(name)} AI Rating {YEAR} | Nerq")

    meta_desc = f"{_esc(name)} has a Nerq AI Rating of {rating} ({score:.0f}/100). {tools} AI tools analyzed, {critical} critical issues. Independent rating."
    canonical = f"{SITE}/{route_prefix}/{slug}"

    # First paragraph (citable)
    first_p = f"{_esc(name)} has a Nerq AI Rating of <strong style='color:{rc}'>{rating}</strong> ({score:.0f}/100), based on analysis of {tools} identified AI tools{f' across {deps} dependencies' if deps else ''}. {f'{critical} critical issues detected.' if critical else 'No critical issues detected.'}{f' Industry: {_esc(industry)}.' if industry else ''}{f' Ticker: {_esc(ticker)}.' if ticker else ''} Last analyzed {MONTH_YEAR}."

    # Tool breakdown table
    tools_html = ""
    for t in tool_breakdown[:20]:
        ts = t.get("trust_score") or 0
        tc = "#16a34a" if ts >= 70 else "#ca8a04" if ts >= 50 else "#dc2626"
        tools_html += f'<tr><td><a href="/safe/{_to_slug(t.get("name",""))}" style="color:#0d9488">{_esc(t.get("name",""))}</a></td><td style="color:{tc};font-weight:600">{ts:.0f}</td><td>{_esc(t.get("grade","D"))}</td><td>{_esc(t.get("category",""))}</td></tr>'

    # Risk factors
    risks_html = ""
    for r in risk_factors:
        sev = r.get("severity", "LOW")
        sc = {"HIGH": "#dc2626", "MEDIUM": "#f59e0b", "LOW": "#6b7280"}.get(sev, "#6b7280")
        risks_html += f'<tr><td style="color:{sc};font-weight:600">{sev}</td><td>{_esc(r.get("description",""))}</td></tr>'

    # Predictions
    pred_html = ""
    if predictions:
        pred_html = f"""
<h2>Predictions</h2>
<table style="width:100%;border-collapse:collapse;font-size:13px">
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb">Components at risk (6 months)</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:600">{predictions.get('components_at_risk_6m',0)}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb">Predicted incidents (12 months)</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:600">{predictions.get('predicted_incidents_12m',0)}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb">Weakest link</td><td style="padding:8px;border-bottom:1px solid #e5e7eb">{_esc(predictions.get('weakest_link','—'))} (trust: {predictions.get('weakest_link_trust',0):.0f})</td></tr>
</table>"""

    # FAQ
    faq_items = [
        (f"What AI tools does {_esc(name)} use?", f"Based on public repository analysis, {_esc(name)} uses {tools} AI tools including {', '.join(t.get('name','') for t in tool_breakdown[:3])}."),
        (f"Is {_esc(name)}'s AI safe?", f"{_esc(name)} has a Nerq AI Rating of {rating} ({score:.0f}/100). {f'{critical} critical issues detected.' if critical else 'No critical issues detected.'}"),
        (f"What is {_esc(name)}'s AI risk level?", f"AI risk rating: {rating}. {'Low risk.' if score >= 75 else 'Moderate risk.' if score >= 55 else 'Elevated risk.'}"),
        (f"How does {_esc(name)} compare to competitors?", f"View industry comparison at nerq.ai/industry/{_to_slug(industry) if industry else 'tech'}."),
        (f"Does {_esc(name)} have AI vulnerabilities?", f"{critical} critical issues and {warnings} health warnings detected across {tools} AI tools."),
    ]
    faq_html = "".join(f'<div style="border-bottom:1px solid #e5e7eb;padding:12px 0"><div style="font-weight:600;font-size:14px">{q}</div><div style="font-size:13px;color:#374151;margin-top:6px">{a}</div></div>' for q, a in faq_items)
    faq_jsonld = ",".join(f'{{"@type":"Question","name":"{q}","acceptedAnswer":{{"@type":"Answer","text":"{a}"}}}}' for q, a in faq_items)

    # Industry peers
    peers = _get_entities_by_industry(industry, limit=10) if industry else []
    peers_html = ""
    for p in peers:
        if p["slug"] == slug: continue
        prc = rating_color(p.get("rating","C"))
        peers_html += f'<tr><td><a href="/{route_prefix}/{p["slug"]}" style="color:#0d9488">{_esc(p.get("display_name") or p["name"])}</a></td><td style="color:{prc};font-weight:600">{p.get("rating","NR")}</td><td>{(p.get("score") or 0):.0f}</td><td>{p.get("tools",0)}</td></tr>'

    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(meta_desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(name)} AI Rating: {rating} ({score:.0f}/100)">
<meta property="og:description" content="{tools} AI tools analyzed. {critical} critical issues.">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary">
<meta name="nerq:type" content="{entity_type}_rating">
<meta name="nerq:entity" content="{_esc(name)}">
{f'<meta name="nerq:ticker" content="{_esc(ticker)}">' if ticker else ''}
<meta name="nerq:rating" content="{rating}">
<meta name="nerq:score" content="{score:.0f}">
<meta name="nerq:tools_count" content="{tools}">
<meta name="nerq:critical_issues" content="{critical}">
<meta name="nerq:updated" content="{TODAY}">
<meta name="citation_title" content="{_esc(title)}">
<meta name="citation_author" content="Nerq">
<meta name="citation_date" content="{TODAY}">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Organization","name":"{_esc(name)}","url":"{canonical}","aggregateRating":{{"@type":"AggregateRating","ratingValue":"{score/20:.1f}","bestRating":"5","worstRating":"1","ratingCount":"{max(1, tools)}"}}}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{faq_jsonld}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"Nerq","item":"{SITE}"}},{{"@type":"ListItem","position":2,"name":"{entity_type.title()}","item":"{SITE}/{route_prefix}"}},{{"@type":"ListItem","position":3,"name":"{_esc(name)}","item":"{canonical}"}}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Dataset","name":"{_esc(name)} AI Stack Rating","description":"Independent AI risk rating","dateModified":"{TODAY}","creator":{{"@type":"Organization","name":"Nerq"}},"variableMeasured":[{{"@type":"PropertyValue","name":"AI Rating","value":"{rating}"}},{{"@type":"PropertyValue","name":"AI Score","value":"{score:.0f}"}},{{"@type":"PropertyValue","name":"AI Tools Found","value":"{tools}"}},{{"@type":"PropertyValue","name":"Critical Issues","value":"{critical}"}}]}}
</script>
{NERQ_CSS}
<style>
.rating-badge{{display:inline-block;padding:12px 24px;font-size:32px;font-weight:700;font-family:ui-monospace,monospace;border:3px solid;margin:12px 0}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}
th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280;font-weight:600}}
td{{padding:8px;border-bottom:1px solid #e5e7eb}}
.score-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:16px 0}}
.score-card{{padding:14px;border:1px solid #e5e7eb;text-align:center}}
.score-card .num{{font-size:22px;font-weight:700;font-family:ui-monospace,monospace}}
.score-card .lbl{{font-size:10px;color:#6b7280;text-transform:uppercase;margin-top:4px}}
</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:960px;margin:0 auto;padding:24px">

<nav style="font-size:12px;color:#6b7280;margin-bottom:16px"><a href="/" style="color:#0d9488">Nerq</a> &rsaquo; <a href="/{route_prefix}" style="color:#0d9488">{entity_type.title()}</a> &rsaquo; {_esc(name)}</nav>

<h1>{_esc(name)} — AI {'Stack' if entity_type == 'saas' else 'Risk' if entity_type == 'company' else 'Transparency' if entity_type == 'government' else 'Research'} Rating {YEAR}</h1>

<div class="rating-badge" style="color:{rc};border-color:{rc}">{rating}</div>

<p class="short-answer" style="font-size:15px;color:#374151;margin:12px 0 20px">{first_p}</p>

<div class="score-grid">
<div class="score-card"><div class="num" style="color:{rc}">{score:.0f}</div><div class="lbl">AI Score</div></div>
<div class="score-card"><div class="num">{tools}</div><div class="lbl">AI Tools</div></div>
<div class="score-card"><div class="num" style="color:{'#dc2626' if critical else '#16a34a'}">{critical}</div><div class="lbl">Critical</div></div>
<div class="score-card"><div class="num">{warnings}</div><div class="lbl">Warnings</div></div>
<div class="score-card"><div class="num">{deps}</div><div class="lbl">Dependencies</div></div>
</div>

<h2>AI Stack Overview</h2>
<table>
<tr><th>Tool</th><th>Trust Score</th><th>Grade</th><th>Category</th></tr>
{tools_html if tools_html else '<tr><td colspan="4" style="color:#6b7280">No AI tools discovered in public repositories</td></tr>'}
</table>

{"<h2>Risk Factors</h2><table><tr><th>Severity</th><th>Description</th></tr>" + risks_html + "</table>" if risks_html else ""}

{pred_html}

{"<h2>Industry Comparison</h2><table><tr><th>Entity</th><th>Rating</th><th>Score</th><th>Tools</th></tr>" + peers_html + "</table>" if peers_html else ""}

<h2>Methodology</h2>
<p style="font-size:13px;color:#6b7280">{METHODOLOGY}</p>

<h2>Frequently Asked Questions</h2>
{faq_html}

<div style="margin-top:24px;padding:16px;background:#f9fafb;border:1px solid #e5e7eb">
<pre style="background:#f5f5f5;padding:8px;font-size:12px;overflow-x:auto">curl nerq.ai/v1/entity/{entity_type}/{slug}</pre>
<div style="font-size:12px;margin-top:8px">
<a href="/predictions" style="color:#0d9488">Predictions</a> &middot;
<a href="/stats/ai-ecosystem" style="color:#0d9488">Ecosystem Stats</a> &middot;
<a href="/index/{_to_slug(e.get('index','saas') or 'saas')}" style="color:#0d9488">Index</a> &middot;
<a href="/industry/{_to_slug(industry) if industry else 'tech'}" style="color:#0d9488">{_esc(industry or 'Tech')} Industry</a>
</div>
</div>

</main>
{NERQ_FOOTER}
</body></html>"""

    return _set_cache(ck, page)


def _render_index_page(index_name):
    ck = f"index:{index_name}"
    c = _cached(ck)
    if c: return c

    # Map index names to display names and query params
    index_map = {
        "sp500": ("S&P 500 AI Risk Ratings", "sp500", "company"),
        "saas": ("SaaS AI Stack Ratings", None, "saas"),
        "ftse100": ("FTSE 100 AI Risk Ratings", "ftse100", "company"),
        "government": ("Government AI Transparency Ratings", None, "government"),
        "universities": ("University AI Research Ratings", None, "university"),
        "dax": ("DAX AI Risk Ratings", "dax", "company"),
        "omx30": ("OMX 30 AI Risk Ratings", "omx30", "company"),
        "global": ("Global AI Risk Ratings", None, None),
    }

    config = index_map.get(index_name)

    # Global index: get ALL entities
    if index_name == "global":
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT entity_name, entity_slug, display_name, entity_type, industry, country,
                       rating, score, tools_found, critical_issues
                FROM entity_ratings ORDER BY score DESC NULLS LAST
            """)).fetchall()
        finally:
            session.close()
        entities = [{"name": r[0], "slug": r[1], "display_name": r[2] or r[0], "type": r[3],
                    "industry": r[4], "country": r[5], "rating": r[6], "score": r[7],
                    "tools": r[8], "critical": r[9]} for r in rows]
        display_name = "Global AI Risk Ratings"
        entity_type = "all"
    elif not config:
        return None
    else:
        display_name, stock_index, entity_type = config
        if stock_index:
            entities = _get_entities_by_index(stock_index)
        else:
            entities = _get_entities_by_type(entity_type)

    if not entities:
        # Return page with "scanning in progress" message
        pass

    avg_score = sum(e.get("score") or 0 for e in entities) / max(1, len(entities))
    avg_rating = score_to_rating(avg_score)

    route_prefix = {"company": "company", "saas": "software", "government": "government", "university": "university"}.get(entity_type, "company")

    rows_html = ""
    for i, e in enumerate(entities, 1):
        rc = rating_color(e.get("rating", "C"))
        ticker_html = f' <span style="color:#6b7280;font-size:11px">({_esc(e.get("ticker",""))})</span>' if e.get("ticker") else ""
        rows_html += f'<tr><td>{i}</td><td><a href="/{route_prefix}/{e["slug"]}" style="color:#0d9488">{_esc(e.get("display_name") or e["name"])}</a>{ticker_html}</td><td>{_esc(e.get("industry",""))}</td><td>{_esc(e.get("country",""))}</td><td style="color:{rc};font-weight:700;font-size:15px">{e.get("rating","NR")}</td><td>{(e.get("score") or 0):.0f}</td><td>{e.get("tools",0)}</td><td style="color:{"#dc2626" if e.get("critical",0) else "#16a34a"}">{e.get("critical",0)}</td></tr>'

    title = f"{display_name} {YEAR} — Every {'Company' if entity_type == 'company' else 'Product' if entity_type == 'saas' else 'Agency' if entity_type == 'government' else 'University'} Rated | Nerq"
    canonical = f"{SITE}/index/{index_name}"

    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{display_name}. {len(entities)} entities rated. Average AI score: {avg_score:.0f}/100 ({avg_rating}). Updated {MONTH_YEAR}.">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}">
<meta name="nerq:type" content="index">
<meta name="nerq:updated" content="{TODAY}">
<meta name="citation_title" content="{_esc(title)}">
<meta name="citation_author" content="Nerq">
<meta name="citation_date" content="{TODAY}">
{NERQ_CSS}
<style>
table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}
th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280;font-weight:600;cursor:pointer}}
td{{padding:8px;border-bottom:1px solid #e5e7eb}}
</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:1100px;margin:0 auto;padding:24px">

<h1>{_esc(display_name)} {YEAR}</h1>
<p class="short-answer" style="font-size:15px;color:#374151;margin:8px 0 20px">{len(entities)} entities rated with an average AI score of <strong>{avg_score:.0f}/100</strong> ({avg_rating}). Based on public repository analysis of AI tools, dependencies, and security signals. Updated {MONTH_YEAR}.</p>

<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0">
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:24px;font-weight:700">{len(entities)}</div><div style="font-size:10px;color:#6b7280;text-transform:uppercase">Entities Rated</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:24px;font-weight:700;color:{rating_color(avg_rating)}">{avg_rating}</div><div style="font-size:10px;color:#6b7280;text-transform:uppercase">Avg Rating</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:24px;font-weight:700">{avg_score:.0f}</div><div style="font-size:10px;color:#6b7280;text-transform:uppercase">Avg Score</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:24px;font-weight:700;color:#dc2626">{sum(1 for e in entities if (e.get("critical") or 0) > 0)}</div><div style="font-size:10px;color:#6b7280;text-transform:uppercase">With Critical Issues</div></div>
</div>

<table>
<tr><th>#</th><th>Entity</th><th>Industry</th><th>Country</th><th>Rating</th><th>Score</th><th>AI Tools</th><th>Critical</th></tr>
{rows_html if rows_html else '<tr><td colspan="8" style="color:#6b7280">Scanning in progress — entities will appear after first scan completes.</td></tr>'}
</table>

<p style="font-size:12px;color:#6b7280;margin-top:24px"><strong>Methodology:</strong> {METHODOLOGY}</p>
</main>
{NERQ_FOOTER}
</body></html>"""

    return _set_cache(ck, page)


def _render_entity_comparison(entity_type, slug_a, slug_b, route_prefix):
    """Render side-by-side entity comparison."""
    ck = f"cmp:{entity_type}:{slug_a}:{slug_b}"
    c = _cached(ck)
    if c: return HTMLResponse(c)

    a = _get_entity(entity_type, slug_a)
    b = _get_entity(entity_type, slug_b)
    if not a or not b:
        return HTMLResponse(status_code=404, content="<h1>Entity not found</h1><p>One or both entities haven't been scanned yet.</p>")

    name_a = a["display_name"] or a["name"]
    name_b = b["display_name"] or b["name"]
    score_a = a["score"] or 0
    score_b = b["score"] or 0
    rating_a = a["rating"] or "NR"
    rating_b = b["rating"] or "NR"
    winner = name_a if score_a >= score_b else name_b

    title = f"{_esc(name_a)} vs {_esc(name_b)} — AI Stack Comparison {YEAR} | Nerq"
    meta_desc = f"{_esc(name_a)} ({rating_a}, {score_a:.0f}) vs {_esc(name_b)} ({rating_b}, {score_b:.0f}). Side-by-side AI stack comparison."
    canonical = f"{SITE}/{route_prefix}/{slug_a}-vs-{slug_b}"

    rows = [
        ("AI Rating", f'<strong style="color:{rating_color(rating_a)}">{rating_a}</strong>', f'<strong style="color:{rating_color(rating_b)}">{rating_b}</strong>'),
        ("AI Score", f"{score_a:.0f}/100", f"{score_b:.0f}/100"),
        ("AI Tools Found", str(a["tools_found"] or 0), str(b["tools_found"] or 0)),
        ("Critical Issues", str(a["critical"] or 0), str(b["critical"] or 0)),
        ("Warnings", str(a["warnings"] or 0), str(b["warnings"] or 0)),
        ("Industry", _esc(a["industry"] or "—"), _esc(b["industry"] or "—")),
        ("Country", _esc(a["country"] or "—"), _esc(b["country"] or "—")),
    ]
    rows_html = "".join(f'<tr><td style="font-weight:600;color:#6b7280">{label}</td><td style="text-align:center">{va}</td><td style="text-align:center">{vb}</td></tr>' for label, va, vb in rows)

    faq_items = [
        (f"Which is safer: {_esc(name_a)} or {_esc(name_b)} AI?", f"{_esc(winner)} has a higher Nerq AI Rating ({rating_a if score_a >= score_b else rating_b}, {max(score_a,score_b):.0f}/100) compared to {_esc(name_b if score_a >= score_b else name_a)} ({rating_b if score_a >= score_b else rating_a}, {min(score_a,score_b):.0f}/100)."),
        (f"How many AI tools does {_esc(name_a)} use?", f"{_esc(name_a)} has {a['tools_found'] or 0} identified AI tools with {a['critical'] or 0} critical issues."),
        (f"How many AI tools does {_esc(name_b)} use?", f"{_esc(name_b)} has {b['tools_found'] or 0} identified AI tools with {b['critical'] or 0} critical issues."),
    ]
    faq_html = "".join(f'<div style="border-bottom:1px solid #e5e7eb;padding:12px 0"><div style="font-weight:600;font-size:14px">{q}</div><div style="font-size:13px;color:#374151;margin-top:6px">{ans}</div></div>' for q, ans in faq_items)
    faq_jsonld = ",".join(f'{{"@type":"Question","name":"{q}","acceptedAnswer":{{"@type":"Answer","text":"{ans}"}}}}' for q, ans in faq_items)

    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(meta_desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(name_a)} vs {_esc(name_b)} AI Rating">
<meta property="og:description" content="{_esc(meta_desc)}">
<meta name="nerq:type" content="entity_comparison">
<meta name="nerq:updated" content="{TODAY}">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{faq_jsonld}]}}</script>
{NERQ_CSS}
<style>table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}th{{text-align:left;padding:10px;border-bottom:2px solid #e5e7eb;color:#6b7280}}td{{padding:10px;border-bottom:1px solid #e5e7eb}}</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:900px;margin:0 auto;padding:24px">
<h1>{_esc(name_a)} vs {_esc(name_b)} — AI Stack Comparison {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(name_a)} ({rating_a}, {score_a:.0f}/100) vs {_esc(name_b)} ({rating_b}, {score_b:.0f}/100). <strong>{_esc(winner)}</strong> has the stronger AI stack. Based on public repository analysis of AI tools, dependencies, and security signals. Updated {MONTH_YEAR}.</p>

<table>
<tr><th style="width:30%">Metric</th><th style="text-align:center;width:35%">{_esc(name_a)}</th><th style="text-align:center;width:35%">{_esc(name_b)}</th></tr>
{rows_html}
</table>

<h2>Frequently Asked Questions</h2>
{faq_html}

<div style="margin-top:24px;font-size:12px;color:#6b7280">
<a href="/{route_prefix}/{slug_a}" style="color:#0d9488">{_esc(name_a)} full report</a> &middot;
<a href="/{route_prefix}/{slug_b}" style="color:#0d9488">{_esc(name_b)} full report</a> &middot;
<a href="/index/{'sp500' if entity_type == 'company' else 'saas'}" style="color:#0d9488">All ratings</a>
</div>
<p style="font-size:12px;color:#6b7280;margin-top:16px"><strong>Methodology:</strong> {METHODOLOGY}</p>
</main>
{NERQ_FOOTER}
</body></html>"""

    _set_cache(ck, page)
    return HTMLResponse(page)


def mount_entity_pages(app):

    # Entity comparison pages
    @app.get("/company/{slug_a}-vs-{slug_b}", response_class=HTMLResponse)
    async def company_comparison(slug_a: str, slug_b: str):
        return _render_entity_comparison("company", slug_a, slug_b, "company")

    @app.get("/software/{slug_a}-vs-{slug_b}", response_class=HTMLResponse)
    async def software_comparison(slug_a: str, slug_b: str):
        return _render_entity_comparison("saas", slug_a, slug_b, "software")

    # Entity pages
    for etype, prefix in [("saas","software"), ("company","company"), ("government","government"), ("university","university")]:
        def make_handler(et, pf):
            async def handler(slug: str):
                html = _render_entity_page(et, slug, pf)
                return HTMLResponse(html) if html else HTMLResponse(status_code=404, content=f"<h1>{et.title()} not found</h1><p>This entity hasn't been scanned yet.</p>")
            return handler
        app.get(f"/{prefix}/{{slug}}", response_class=HTMLResponse)(make_handler(etype, prefix))

    # Index pages
    @app.get("/index/{index_name}", response_class=HTMLResponse)
    async def index_page(index_name: str):
        html = _render_index_page(index_name)
        return HTMLResponse(html) if html else HTMLResponse(status_code=404, content="<h1>Index not found</h1>")

    # Industry pages
    @app.get("/industry/{industry_name}", response_class=HTMLResponse)
    async def industry_page(industry_name: str):
        entities = _get_entities_by_industry(industry_name)
        if not entities:
            return HTMLResponse(status_code=404, content=f"<h1>No entities in {industry_name}</h1>")
        avg_score = sum(e.get("score") or 0 for e in entities) / max(1, len(entities))
        rows_html = ""
        for e in entities:
            rc = rating_color(e.get("rating","C"))
            prefix = {"company":"company","saas":"software","government":"government","university":"university"}.get(e.get("type","company"),"company")
            rows_html += f'<tr><td><a href="/{prefix}/{e["slug"]}" style="color:#0d9488">{_esc(e.get("display_name") or e["name"])}</a></td><td style="color:{rc};font-weight:700">{e.get("rating","NR")}</td><td>{(e.get("score") or 0):.0f}</td><td>{e.get("tools",0)}</td></tr>'
        html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_esc(industry_name.replace('_',' ').title())} AI Risk Ratings {YEAR} | Nerq</title><link rel="canonical" href="{SITE}/industry/{_to_slug(industry_name)}"><meta name="nerq:type" content="industry"><meta name="nerq:updated" content="{TODAY}">{NERQ_CSS}<style>table{{width:100%;border-collapse:collapse;font-size:13px}}th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280}}td{{padding:8px;border-bottom:1px solid #e5e7eb}}</style></head><body>{NERQ_NAV}<main class="container" style="max-width:960px;margin:0 auto;padding:24px"><h1>{_esc(industry_name.replace('_',' ').title())} — AI Risk Ratings {YEAR}</h1><p style="font-size:15px;color:#374151;margin:8px 0 16px">{len(entities)} entities in {_esc(industry_name.replace('_',' '))}. Average AI score: {avg_score:.0f}/100. Updated {MONTH_YEAR}.</p><table><tr><th>Entity</th><th>Rating</th><th>Score</th><th>AI Tools</th></tr>{rows_html}</table><p style="font-size:12px;color:#6b7280;margin-top:24px"><strong>Methodology:</strong> {METHODOLOGY}</p></main>{NERQ_FOOTER}</body></html>"""
        return HTMLResponse(html)

    # Country pages
    @app.get("/country/{country_code}", response_class=HTMLResponse)
    async def country_page(country_code: str):
        code = country_code.upper()
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT entity_name, entity_slug, display_name, entity_type, industry,
                       rating, score, tools_found, critical_issues
                FROM entity_ratings
                WHERE UPPER(country) = :code
                ORDER BY score DESC NULLS LAST
            """), {"code": code}).fetchall()
        finally:
            session.close()

        if not rows:
            return HTMLResponse(status_code=404, content=f"<h1>No entities rated for {code}</h1>")

        entities = [dict(zip(["name","slug","display","type","industry","rating","score","tools","critical"], r)) for r in rows]
        avg_score = sum(e["score"] or 0 for e in entities) / max(1, len(entities))

        country_names = {"US": "United States", "UK": "United Kingdom", "DE": "Germany", "SE": "Sweden",
                        "FR": "France", "NL": "Netherlands", "CH": "Switzerland", "JP": "Japan",
                        "KR": "South Korea", "CN": "China", "CA": "Canada", "IN": "India",
                        "SG": "Singapore", "AU": "Australia", "FI": "Finland", "EE": "Estonia",
                        "EU": "European Union", "IL": "Israel"}
        display_country = country_names.get(code, code)

        prefix_map = {"saas": "software", "company": "company", "government": "government", "university": "university"}
        rows_html = ""
        for e in entities:
            rc = rating_color(e["rating"] or "C")
            prefix = prefix_map.get(e["type"], "company")
            rows_html += f'<tr><td><a href="/{prefix}/{e["slug"]}" style="color:#0d9488">{_esc(e["display"] or e["name"])}</a></td><td>{_esc(e["type"])}</td><td>{_esc(e["industry"] or "—")}</td><td style="color:{rc};font-weight:700">{e["rating"] or "NR"}</td><td>{(e["score"] or 0):.0f}</td><td>{e["tools"] or 0}</td></tr>'

        html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Risk Ratings: {_esc(display_country)} {YEAR} | Nerq</title>
<meta name="description" content="{len(entities)} entities in {_esc(display_country)} rated for AI risk. Average score: {avg_score:.0f}/100. Updated {MONTH_YEAR}.">
<link rel="canonical" href="{SITE}/country/{code.lower()}">
<meta name="nerq:type" content="country"><meta name="nerq:updated" content="{TODAY}">
{NERQ_CSS}
<style>table{{width:100%;border-collapse:collapse;font-size:13px}}th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280}}td{{padding:8px;border-bottom:1px solid #e5e7eb}}</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:1000px;margin:0 auto;padding:24px">
<h1>AI Risk Ratings: {_esc(display_country)} — {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{len(entities)} entities in {_esc(display_country)} rated for AI stack health. Average score: <strong>{avg_score:.0f}/100</strong>. Updated {MONTH_YEAR}.</p>
<table><tr><th>Entity</th><th>Type</th><th>Industry</th><th>Rating</th><th>Score</th><th>AI Tools</th></tr>{rows_html}</table>
<p style="font-size:12px;color:#6b7280;margin-top:24px"><strong>Methodology:</strong> {METHODOLOGY}</p>
</main>{NERQ_FOOTER}</body></html>"""
        return HTMLResponse(html)

    # Global index
    @app.get("/index/global", response_class=HTMLResponse)
    async def global_index():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT entity_name, entity_slug, display_name, entity_type, industry,
                       country, rating, score, tools_found, critical_issues
                FROM entity_ratings
                ORDER BY score DESC NULLS LAST
            """)).fetchall()
        finally:
            session.close()

        entities = [dict(zip(["name","slug","display","type","industry","country","rating","score","tools","critical"], r)) for r in rows]
        avg_score = sum(e["score"] or 0 for e in entities) / max(1, len(entities))

        prefix_map = {"saas": "software", "company": "company", "government": "government", "university": "university"}
        rows_html = ""
        for i, e in enumerate(entities, 1):
            rc = rating_color(e["rating"] or "C")
            prefix = prefix_map.get(e["type"], "company")
            rows_html += f'<tr><td>{i}</td><td><a href="/{prefix}/{e["slug"]}" style="color:#0d9488">{_esc(e["display"] or e["name"])}</a></td><td>{_esc(e["type"])}</td><td>{_esc(e["country"] or "—")}</td><td style="color:{rc};font-weight:700">{e["rating"] or "NR"}</td><td>{(e["score"] or 0):.0f}</td><td>{e["tools"] or 0}</td></tr>'

        html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Global AI Risk Ratings {YEAR} — {len(entities)} Entities Ranked | Nerq</title>
<meta name="description" content="Global AI risk ratings for {len(entities)} companies, SaaS products, and organizations. Average score: {avg_score:.0f}/100. Updated {MONTH_YEAR}.">
<link rel="canonical" href="{SITE}/index/global">
{NERQ_CSS}
<style>table{{width:100%;border-collapse:collapse;font-size:13px}}th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280}}td{{padding:8px;border-bottom:1px solid #e5e7eb}}</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:1100px;margin:0 auto;padding:24px">
<h1>Global AI Risk Ratings {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{len(entities)} entities ranked by AI stack health. Average score: <strong>{avg_score:.0f}/100</strong>. Covering companies, SaaS products, governments, and universities worldwide. Updated {MONTH_YEAR}.</p>
<table><tr><th>#</th><th>Entity</th><th>Type</th><th>Country</th><th>Rating</th><th>Score</th><th>AI Tools</th></tr>{rows_html}</table>
<p style="font-size:12px;color:#6b7280;margin-top:24px"><strong>Methodology:</strong> {METHODOLOGY}</p>
</main>{NERQ_FOOTER}</body></html>"""
        return HTMLResponse(html)

    # API endpoints
    @app.get("/v1/entity/{entity_type}/{slug}")
    async def api_entity(entity_type: str, slug: str):
        e = _get_entity(entity_type, slug)
        if not e:
            return JSONResponse({"error": "Entity not found"}, status_code=404)
        return {
            "name": e["name"], "type": entity_type, "rating": e["rating"],
            "score": e["score"], "tools_found": e["tools_found"],
            "critical_issues": e["critical"], "warnings": e["warnings"],
            "tool_breakdown": (json.loads(e["tool_breakdown"]) if isinstance(e["tool_breakdown"], str) else e["tool_breakdown"]) or [],
            "risk_factors": (json.loads(e["risk_factors"]) if isinstance(e["risk_factors"], str) else e["risk_factors"]) or [],
            "predictions": (json.loads(e["predictions"]) if isinstance(e["predictions"], str) else e["predictions"]) or {},
            "methodology": METHODOLOGY,
        }

    @app.get("/v1/index/{index_name}")
    async def api_index(index_name: str):
        entities = _get_entities_by_index(index_name) if index_name not in ("saas","government","universities") else _get_entities_by_type({"saas":"saas","government":"government","universities":"university"}.get(index_name, index_name))
        return {"index": index_name, "count": len(entities), "entities": entities}

    # Insights/blog pages
    @app.get("/research/sp500-ai-ratings-march-2026", response_class=HTMLResponse)
    async def insight_sp500():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT entity_name, display_name, industry, country, rating, score, tools_found, critical_issues
                FROM entity_ratings WHERE entity_type = 'company'
                ORDER BY score DESC NULLS LAST
            """)).fetchall()
        finally:
            session.close()

        entities = [dict(zip(["name","display","industry","country","rating","score","tools","critical"], r)) for r in rows]
        avg = sum(e["score"] or 0 for e in entities) / max(1, len(entities))
        top5 = entities[:5]
        bottom5 = entities[-5:] if len(entities) >= 5 else entities

        top_html = "".join(f'<li><strong>{_esc(e["display"] or e["name"])}</strong> — {e["rating"]} ({(e["score"] or 0):.0f}/100), {e["tools"] or 0} AI tools</li>' for e in top5)
        bottom_html = "".join(f'<li><strong>{_esc(e["display"] or e["name"])}</strong> — {e["rating"]} ({(e["score"] or 0):.0f}/100), {e["tools"] or 0} AI tools</li>' for e in bottom5)

        # Industry averages
        ind_scores = {}
        for e in entities:
            ind = e["industry"] or "other"
            ind_scores.setdefault(ind, []).append(e["score"] or 0)
        ind_avg = sorted([(k, sum(v)/len(v), len(v)) for k, v in ind_scores.items()], key=lambda x: -x[1])
        ind_html = "".join(f'<tr><td>{_esc(i[0])}</td><td>{i[1]:.0f}</td><td>{i[2]}</td></tr>' for i in ind_avg)

        html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>First AI Risk Ratings for Companies — March 2026 | Nerq</title>
<meta name="description" content="Nerq rates {len(entities)} companies on AI stack health. Average score: {avg:.0f}/100. Top: {_esc(top5[0]['display'] or top5[0]['name'])} ({top5[0]['rating']}). Full analysis inside.">
<link rel="canonical" href="{SITE}/research/sp500-ai-ratings-march-2026">
<meta name="nerq:type" content="insight"><meta name="nerq:updated" content="{TODAY}">
{NERQ_CSS}
<style>table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280}}td{{padding:8px;border-bottom:1px solid #e5e7eb}}</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:800px;margin:0 auto;padding:24px">
<p style="font-size:12px;color:#6b7280">Published {MONTH_YEAR} &middot; Nerq Research</p>
<h1>First AI Risk Ratings for Companies — March 2026</h1>
<p style="font-size:15px;color:#374151;margin:12px 0 20px">Nerq has rated {len(entities)} companies for AI stack health based on public repository analysis. The average AI score is <strong>{avg:.0f}/100</strong>. Here are the key findings.</p>

<h2>Key Findings</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>{len(entities)} companies rated from {len(ind_scores)} industries</li>
<li>Average AI score: {avg:.0f}/100</li>
<li>{sum(1 for e in entities if (e['score'] or 0) >= 75)} companies rated A or above (strong AI stack)</li>
<li>{sum(1 for e in entities if (e['critical'] or 0) > 0)} companies have critical AI issues</li>
<li>Total AI tools identified: {sum(e['tools'] or 0 for e in entities)}</li>
</ul>

<h2>Top 5 Companies by AI Score</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">{top_html}</ol>

<h2>Bottom 5 Companies by AI Score</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">{bottom_html}</ol>

<h2>Industry Averages</h2>
<table><tr><th>Industry</th><th>Avg Score</th><th>Companies</th></tr>{ind_html}</table>

<h2>Methodology</h2>
<p style="font-size:13px;color:#6b7280">{METHODOLOGY}</p>

<div style="margin-top:24px;font-size:12px;color:#6b7280">
<a href="/index/sp500" style="color:#0d9488">Full S&P 500 ratings</a> &middot;
<a href="/index/global" style="color:#0d9488">Global ratings</a> &middot;
<a href="/index/saas" style="color:#0d9488">SaaS ratings</a>
</div>
</main>{NERQ_FOOTER}</body></html>"""
        return HTMLResponse(html)

    @app.get("/research/saas-ai-safety-march-2026", response_class=HTMLResponse)
    async def insight_saas():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT entity_name, display_name, industry, rating, score, tools_found, critical_issues
                FROM entity_ratings WHERE entity_type = 'saas'
                ORDER BY score DESC NULLS LAST
            """)).fetchall()
        finally:
            session.close()

        entities = [dict(zip(["name","display","industry","rating","score","tools","critical"], r)) for r in rows]
        avg = sum(e["score"] or 0 for e in entities) / max(1, len(entities))

        rank_html = ""
        for i, e in enumerate(entities, 1):
            rc = rating_color(e["rating"] or "C")
            rank_html += f'<tr><td>{i}</td><td>{_esc(e["display"] or e["name"])}</td><td>{_esc(e["industry"] or "—")}</td><td style="color:{rc};font-weight:700">{e["rating"]}</td><td>{(e["score"] or 0):.0f}</td><td>{e["tools"] or 0}</td></tr>'

        html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Which SaaS Products Have the Safest AI? — March 2026 | Nerq</title>
<meta name="description" content="{len(entities)} SaaS products rated for AI safety. Average: {avg:.0f}/100. See which tools are safest.">
<link rel="canonical" href="{SITE}/research/saas-ai-safety-march-2026">
{NERQ_CSS}
<style>table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280}}td{{padding:8px;border-bottom:1px solid #e5e7eb}}</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:800px;margin:0 auto;padding:24px">
<p style="font-size:12px;color:#6b7280">Published {MONTH_YEAR} &middot; Nerq Research</p>
<h1>Which SaaS Products Have the Safest AI? — March 2026</h1>
<p style="font-size:15px;color:#374151;margin:12px 0 20px">{len(entities)} SaaS products rated for AI stack safety. Average score: <strong>{avg:.0f}/100</strong>.</p>

<h2>Full Rankings</h2>
<table><tr><th>#</th><th>Product</th><th>Industry</th><th>Rating</th><th>Score</th><th>AI Tools</th></tr>{rank_html}</table>

<h2>Methodology</h2>
<p style="font-size:13px;color:#6b7280">{METHODOLOGY}</p>
<div style="margin-top:24px;font-size:12px;color:#6b7280">
<a href="/index/saas" style="color:#0d9488">Live SaaS ratings</a> &middot; <a href="/index/global" style="color:#0d9488">Global ratings</a>
</div>
</main>{NERQ_FOOTER}</body></html>"""
        return HTMLResponse(html)

    # Sitemaps
    @app.get("/sitemap-entities.xml", response_class=Response)
    async def sitemap_entities():
        session = get_session()
        try:
            rows = session.execute(text("SELECT entity_type, entity_slug, score FROM entity_ratings ORDER BY score DESC")).fetchall()
        finally:
            session.close()

        prefix_map = {"saas": "software", "company": "company", "government": "government", "university": "university"}
        urls = []
        for r in rows:
            prefix = prefix_map.get(r[0], r[0])
            urls.append((f"{SITE}/{prefix}/{r[1]}", "0.9"))

        # Add index pages
        for idx in ["sp500", "saas", "ftse100", "government", "universities", "dax", "omx30"]:
            urls.append((f"{SITE}/index/{idx}", "1.0"))

        # Add insight pages
        urls.append((f"{SITE}/research/sp500-ai-ratings-march-2026", "0.8"))
        urls.append((f"{SITE}/research/saas-ai-safety-march-2026", "0.8"))
        urls.append((f"{SITE}/index/global", "1.0"))

        # Add industry pages
        industries = set()
        for r in rows:
            pass  # Would need industry data

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for url, prio in urls:
            xml += f'<url><loc>{html_mod.escape(url)}</loc><lastmod>{TODAY}</lastmod><priority>{prio}</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    logger.info("Mounted entity pages: /software/, /company/, /government/, /university/, /index/, /industry/, /v1/entity/")
