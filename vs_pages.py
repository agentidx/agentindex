#!/usr/bin/env python3
"""
Nerq VS Pages Module
======================
Dynamic "Agent A vs Agent B" comparison pages.

Routes:
  GET /vs/{id_a}/{id_b}          — Full VS comparison page
  GET /vs                        — Popular VS comparisons index
  GET /sitemap-vs.xml            — Sitemap for pre-generated popular VS pairs

AI-optimized: citable first paragraph, JSON-LD, structured comparison data.

Usage in discovery.py:
    from agentindex.vs_pages import mount_vs_pages
    mount_vs_pages(app)
"""

import logging
import json
import re
from datetime import datetime
from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text
from agentindex.db.models import get_session

logger = logging.getLogger("nerq.vs")

SITE_URL = "https://nerq.ai"


def mount_vs_pages(app):
    """Mount VS page routes onto the FastAPI app."""

    # Cache for popular pairs (rebuilt hourly)
    _vs_cache = {"pairs": None, "ts": 0}

    def _get_popular_pairs(session, limit=200):
        """Generate popular VS pairs from top agents in same categories."""
        import time
        now = time.time()
        if _vs_cache["pairs"] and (now - _vs_cache["ts"]) < 3600:
            return _vs_cache["pairs"]

        # Get top MCP servers grouped by domain
        rows = session.execute(text("""
            SELECT id, name, stars, domains, compliance_score, risk_class
            FROM agents
            WHERE is_active = true AND agent_type = 'mcp_server'
            AND stars > 50
            ORDER BY stars DESC NULLS LAST
            LIMIT 500
        """)).fetchall()

        agents = [dict(zip(['id','name','stars','domains','score','risk'], r)) for r in rows]

        # Group by domain
        by_domain = {}
        for a in agents:
            for d in (a['domains'] or ['general']):
                by_domain.setdefault(d, []).append(a)

        # Generate pairs: top agents within same domain
        pairs = []
        seen = set()
        for domain, domain_agents in by_domain.items():
            top = domain_agents[:20]  # Top 20 per domain
            for i in range(len(top)):
                for j in range(i+1, min(i+5, len(top))):  # Each pairs with next 4
                    a, b = top[i], top[j]
                    key = tuple(sorted([a['id'], b['id']]))
                    if key not in seen:
                        seen.add(key)
                        pairs.append((a, b))
                    if len(pairs) >= limit:
                        break
                if len(pairs) >= limit:
                    break
            if len(pairs) >= limit:
                break

        _vs_cache["pairs"] = pairs
        _vs_cache["ts"] = now
        return pairs

    # ================================================================
    # VS INDEX PAGE
    # ================================================================
    @app.get("/vs", response_class=HTMLResponse)
    def vs_index():
        session = get_session()
        try:
            pairs = _get_popular_pairs(session, limit=100)
            html = _render_vs_index(pairs)
            return HTMLResponse(content=html)
        finally:
            session.close()

    # ================================================================
    # VS COMPARISON PAGE
    # ================================================================
    @app.get("/vs/{id_a}/{id_b}", response_class=HTMLResponse)
    def vs_page(id_a: str, id_b: str):
        session = get_session()
        try:
            # Fetch both agents
            agent_a = _fetch_agent(session, id_a)
            agent_b = _fetch_agent(session, id_b)

            if not agent_a or not agent_b:
                return HTMLResponse(status_code=404,
                    content="<h1>Agent not found</h1><p><a href='/vs'>Browse comparisons</a></p>")

            # Fetch jurisdiction data for both
            j_a = _fetch_jurisdictions(session, id_a)
            j_b = _fetch_jurisdictions(session, id_b)

            html = _render_vs_page(agent_a, agent_b, j_a, j_b)
            return HTMLResponse(content=html)
        finally:
            session.close()

    # ================================================================
    # VS SITEMAP
    # ================================================================
    @app.get("/sitemap-vs.xml", response_class=Response)
    def sitemap_vs():
        session = get_session()
        try:
            pairs = _get_popular_pairs(session, limit=200)
            now = datetime.utcnow().strftime("%Y-%m-%d")

            xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
            xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            xml += f'  <url><loc>{SITE_URL}/vs</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>\n'

            for a, b in pairs:
                xml += f'  <url><loc>{SITE_URL}/vs/{a["id"]}/{b["id"]}</loc><lastmod>{now}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>\n'

            xml += '</urlset>'
            return Response(content=xml, media_type="application/xml")
        finally:
            session.close()

    logger.info("VS pages mounted: /vs, /vs/{id_a}/{id_b}, /sitemap-vs.xml")


# ================================================================
# DATA FETCHING
# ================================================================

def _fetch_agent(session, agent_id):
    row = session.execute(text("""
        SELECT id, name, description, source, author, agent_type, risk_class,
               domains, tags, stars, downloads, license, source_url,
               compliance_score
        FROM agents WHERE id = :id AND is_active = true
    """), {"id": agent_id}).fetchone()
    if not row:
        return None
    return dict(zip(['id','name','description','source','author','agent_type','risk_class',
                    'domains','tags','stars','downloads','license','source_url',
                    'compliance_score'], row))


def _fetch_jurisdictions(session, agent_id):
    rows = session.execute(text("""
        SELECT ajs.jurisdiction_id, ajs.risk_level, jr.name as j_name
        FROM agent_jurisdiction_status ajs
        JOIN jurisdiction_registry jr ON jr.id = ajs.jurisdiction_id
        WHERE ajs.agent_id = :id
        ORDER BY jr.name
    """), {"id": agent_id}).fetchall()
    return [dict(zip(['j_id','risk','j_name'], r)) for r in rows]


# ================================================================
# HTML RENDERING
# ================================================================

def _esc(t):
    if not t: return ''
    return str(t).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def _risk_color(risk):
    return {'unacceptable':'#dc2626','high':'#ea580c','limited':'#ca8a04','minimal':'#16a34a'}.get(risk,'#6b7280')

def _risk_label(risk):
    return {'unacceptable':'PROHIBITED','high':'HIGH RISK','limited':'LIMITED','minimal':'MINIMAL'}.get(risk,(risk or 'N/A').upper())

def _score_display(score):
    if score is None:
        return '<span style="color:#6b7280">Pending</span>'
    color = '#16a34a' if score >= 80 else '#ca8a04' if score >= 50 else '#dc2626'
    return f'<strong style="color:{color}">{score}/100</strong>'

def _winner_text(val_a, val_b, name_a, name_b, higher_is_better=True):
    """Return who wins on a metric."""
    if val_a is None or val_b is None:
        return ""
    if val_a == val_b:
        return "Tie"
    if higher_is_better:
        return f"<strong style='color:#16a34a'>{_esc(name_a if val_a > val_b else name_b)}</strong>"
    else:
        return f"<strong style='color:#16a34a'>{_esc(name_a if val_a < val_b else name_b)}</strong>"


def _short_name(name):
    """Shorten org/repo to just repo for display."""
    if '/' in (name or ''):
        return name.split('/')[-1]
    return name or 'Unknown'


def _render_vs_index(pairs):
    now = datetime.utcnow().strftime("%B %d, %Y")
    n = len(pairs)

    rows = ""
    for a, b in pairs[:100]:
        rows += f"""<tr>
<td><a href="/vs/{a['id']}/{b['id']}" style="color:#2563eb;text-decoration:none;font-weight:500">{_esc(_short_name(a['name']))} vs {_esc(_short_name(b['name']))}</a></td>
<td>{a['stars'] or 0:,} vs {b['stars'] or 0:,}</td>
<td>{a.get('score') or '?'} vs {b.get('score') or '?'}</td>
</tr>"""

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "MCP Server Comparisons — VS Pages",
        "description": f"{n} head-to-head MCP server comparisons with compliance data.",
        "url": f"{SITE_URL}/vs",
        "provider": {"@type": "Organization", "name": "Nerq", "url": SITE_URL},
    })

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MCP Server Comparisons — {n} Head-to-Head VS Pages | Nerq</title>
<meta name="description" content="Compare {n} MCP server pairs head-to-head. Stars, compliance scores, risk levels across 52 jurisdictions. Data-driven, no opinions.">
<link rel="canonical" href="{SITE_URL}/vs">
<script type="application/ld+json">{schema}</script>
{_common_styles()}
</head><body>
{_header()}
<div class="container">

<div class="section" style="border-left:4px solid #2563eb;margin-top:16px">
<h1 style="font-size:22px;margin-bottom:12px">MCP Server Comparisons</h1>
<p style="font-size:16px;line-height:1.7">Compare <strong>{n} MCP server pairs</strong> head-to-head with data from Nerq's index of 17,000+ MCP servers. Every comparison includes GitHub stars, Nerq Weighted Compliance Scores across 52 jurisdictions, risk classification, and per-jurisdiction breakdown.</p>
<small style="color:#6b7280">Last updated: {now} | Data from Nerq</small>
</div>

<div class="section">
<h2>Popular Comparisons</h2>
<table class="compliance-table">
<thead><tr><th>Comparison</th><th>Stars</th><th>Compliance</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</div>

</div>
{_footer()}
</body></html>"""


def _render_vs_page(a, b, j_a, j_b):
    now = datetime.utcnow().strftime("%B %d, %Y")
    name_a = _short_name(a['name'])
    name_b = _short_name(b['name'])
    full_a = a['name']
    full_b = b['name']

    # Determine winners
    stars_winner = _winner_text(a['stars'], b['stars'], name_a, name_b)
    score_winner = _winner_text(a['compliance_score'], b['compliance_score'], name_a, name_b)

    # Build jurisdiction comparison
    j_map_a = {j['j_id']: j for j in j_a}
    j_map_b = {j['j_id']: j for j in j_b}
    all_j_ids = sorted(set(list(j_map_a.keys()) + list(j_map_b.keys())))

    j_rows = ""
    a_wins = 0
    b_wins = 0
    for j_id in all_j_ids:
        ja = j_map_a.get(j_id)
        jb = j_map_b.get(j_id)
        j_name = (ja or jb or {}).get('j_name', j_id)
        risk_a = (ja or {}).get('risk', 'N/A')
        risk_b = (jb or {}).get('risk', 'N/A')

        # Determine who's better in this jurisdiction
        severity = {'minimal': 1, 'limited': 2, 'high': 3, 'unacceptable': 4}
        sa = severity.get(risk_a, 5)
        sb = severity.get(risk_b, 5)
        if sa < sb:
            a_wins += 1
            highlight = f' style="background:#f0fdf4"'
        elif sb < sa:
            b_wins += 1
            highlight = f' style="background:#fef2f2"'
        else:
            highlight = ''

        j_rows += f"""<tr{highlight}>
<td><small>{_esc(j_name)}</small></td>
<td><span style="background:{_risk_color(risk_a)};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">{_risk_label(risk_a)}</span></td>
<td><span style="background:{_risk_color(risk_b)};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">{_risk_label(risk_b)}</span></td>
</tr>"""

    # Summary sentence
    if a['compliance_score'] and b['compliance_score']:
        if a['compliance_score'] > b['compliance_score']:
            summary = f"{name_a} has a higher compliance score ({a['compliance_score']}/100 vs {b['compliance_score']}/100)."
        elif b['compliance_score'] > a['compliance_score']:
            summary = f"{name_b} has a higher compliance score ({b['compliance_score']}/100 vs {a['compliance_score']}/100)."
        else:
            summary = f"Both have the same compliance score ({a['compliance_score']}/100)."
    else:
        summary = "Compliance scores are still being calculated."

    stars_summary = ""
    if a['stars'] and b['stars']:
        if a['stars'] > b['stars']:
            stars_summary = f"{name_a} is more popular with {a['stars']:,} stars vs {b['stars']:,}."
        elif b['stars'] > a['stars']:
            stars_summary = f"{name_b} is more popular with {b['stars']:,} stars vs {a['stars']:,}."
        else:
            stars_summary = f"Both have {a['stars']:,} stars."

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"{name_a} vs {name_b} — MCP Server Comparison",
        "description": f"Data-driven comparison of {name_a} and {name_b}. {summary}",
        "url": f"{SITE_URL}/vs/{a['id']}/{b['id']}",
        "author": {"@type": "Organization", "name": "Nerq", "url": SITE_URL},
        "datePublished": datetime.utcnow().strftime("%Y-%m-%d"),
        "publisher": {"@type": "Organization", "name": "Nerq", "url": SITE_URL},
    })

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name_a} vs {name_b} — MCP Server Comparison ({datetime.utcnow().strftime("%B %Y")}) | Nerq</title>
<meta name="description" content="{name_a} vs {name_b}: {summary} {stars_summary} Compared across 52 AI jurisdictions.">
<link rel="canonical" href="{SITE_URL}/vs/{a['id']}/{b['id']}">
<meta property="og:title" content="{name_a} vs {name_b} — MCP Server Comparison">
<meta property="og:description" content="{summary} {stars_summary}">
<script type="application/ld+json">{schema}</script>
{_common_styles()}
</head><body>
{_header()}
<div class="container">

<div class="breadcrumb">
<a href="/">Nerq</a> &rsaquo; <a href="/vs">Comparisons</a> &rsaquo; <strong>{_esc(name_a)} vs {_esc(name_b)}</strong>
</div>

<!-- AI-Citable Summary -->
<div class="section" style="border-left:4px solid #2563eb;margin-top:16px">
<h1 style="font-size:22px;margin-bottom:12px">{_esc(name_a)} vs {_esc(name_b)}</h1>
<p style="font-size:16px;line-height:1.7">{summary} {stars_summary}
Across {len(all_j_ids)} jurisdictions, {_esc(name_a)} has lower risk in <strong>{a_wins}</strong> and
{_esc(name_b)} in <strong>{b_wins}</strong>.
Both are assessed using Nerq's Weighted Global Compliance Score, weighted by jurisdiction penalty severity.</p>
<small style="color:#6b7280">Last updated: {now} | Data from Nerq</small>
</div>

<!-- Side-by-Side Summary -->
<div class="section">
<h2>Head-to-Head Summary</h2>
<table class="compliance-table">
<thead><tr><th>Metric</th><th>{_esc(name_a)}</th><th>{_esc(name_b)}</th><th>Winner</th></tr></thead>
<tbody>
<tr>
<td><strong>Stars</strong></td>
<td>{a['stars'] or 0:,}</td>
<td>{b['stars'] or 0:,}</td>
<td>{stars_winner}</td>
</tr>
<tr>
<td><strong>Compliance Score</strong></td>
<td>{_score_display(a['compliance_score'])}</td>
<td>{_score_display(b['compliance_score'])}</td>
<td>{score_winner}</td>
</tr>
<tr>
<td><strong>Risk Class</strong></td>
<td><span style="background:{_risk_color(a['risk_class'])};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{_risk_label(a['risk_class'])}</span></td>
<td><span style="background:{_risk_color(b['risk_class'])};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{_risk_label(b['risk_class'])}</span></td>
<td></td>
</tr>
<tr>
<td><strong>Type</strong></td>
<td>{_esc(a['agent_type'])}</td>
<td>{_esc(b['agent_type'])}</td>
<td></td>
</tr>
<tr>
<td><strong>Source</strong></td>
<td>{_esc(a['source'])}</td>
<td>{_esc(b['source'])}</td>
<td></td>
</tr>
<tr>
<td><strong>License</strong></td>
<td>{_esc(a['license'] or 'N/A')}</td>
<td>{_esc(b['license'] or 'N/A')}</td>
<td></td>
</tr>
<tr>
<td><strong>Author</strong></td>
<td>{_esc(a['author'] or 'Unknown')}</td>
<td>{_esc(b['author'] or 'Unknown')}</td>
<td></td>
</tr>
<tr>
<td><strong>Jurisdictions won</strong></td>
<td><strong style="color:#16a34a">{a_wins}</strong></td>
<td><strong style="color:#16a34a">{b_wins}</strong></td>
<td>{_winner_text(a_wins, b_wins, name_a, name_b)}</td>
</tr>
</tbody>
</table>
</div>

<!-- Per-Jurisdiction Comparison -->
<div class="section">
<h2>Compliance Comparison Across {len(all_j_ids)} Jurisdictions</h2>
<p style="color:#6b7280;font-size:13px;margin-bottom:12px">Green rows = {_esc(name_a)} has lower risk. Red rows = {_esc(name_b)} has lower risk.</p>
<div style="overflow-x:auto">
<table class="compliance-table">
<thead><tr><th>Jurisdiction</th><th>{_esc(name_a)}</th><th>{_esc(name_b)}</th></tr></thead>
<tbody>{j_rows}</tbody>
</table>
</div>
</div>

<!-- Individual Pages -->
<div class="section">
<h2>Full Agent Profiles</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
<a href="/agent/{a['id']}" style="display:block;padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;text-decoration:none;color:#111">
<strong>{_esc(full_a)}</strong><br>
<small style="color:#6b7280">{_score_display(a['compliance_score'])} · {a['stars'] or 0:,} stars · Full compliance details →</small>
</a>
<a href="/agent/{b['id']}" style="display:block;padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;text-decoration:none;color:#111">
<strong>{_esc(full_b)}</strong><br>
<small style="color:#6b7280">{_score_display(b['compliance_score'])} · {b['stars'] or 0:,} stars · Full compliance details →</small>
</a>
</div>
</div>

</div>
{_footer()}
</body></html>"""


def _common_styles():
    return """<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#111;background:#fafafa;line-height:1.6}
.container{max-width:1100px;margin:0 auto;padding:20px}
header{background:#0f172a;color:#fff;padding:16px 0}
header .container{display:flex;justify-content:space-between;align-items:center}
header a{color:#fff;text-decoration:none;font-weight:700;font-size:20px}
header nav a{color:#94a3b8;margin-left:20px;font-size:14px;font-weight:400}
header nav a:hover{color:#fff}
.breadcrumb{padding:12px 0;font-size:13px;color:#6b7280}
.breadcrumb a{color:#2563eb;text-decoration:none}
.section{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;margin:16px 0}
.section h2{font-size:18px;margin-bottom:16px;color:#0f172a}
.compliance-table{width:100%;border-collapse:collapse;font-size:14px}
.compliance-table th{background:#f8fafc;padding:10px 12px;text-align:left;border-bottom:2px solid #e2e8f0;font-size:13px;color:#475569}
.compliance-table td{padding:10px 12px;border-bottom:1px solid #f1f5f9;vertical-align:top}
.compliance-table tr:hover{background:#f8fafc}
footer{background:#0f172a;color:#94a3b8;padding:24px 0;margin-top:40px;font-size:13px;text-align:center}
footer a{color:#60a5fa;text-decoration:none}
</style>"""


def _header():
    return """<header>
<div class="container">
<a href="/">Nerq</a>
<nav>
<a href="/discover">Discover</a>
<a href="/mcp-servers">MCP Servers</a>
<a href="/vs">Compare</a>
<a href="/comply">Comply</a>
<a href="/docs">API Docs</a>
</nav>
</div>
</header>"""


def _footer():
    return f"""<footer>
<div class="container">
<p>&copy; {datetime.utcnow().year} Nerq (AgentIndex AB). World's largest AI agent compliance database.</p>
<p style="margin-top:8px">
<a href="/">Home</a> &middot; <a href="/mcp-servers">MCP Servers</a> &middot;
<a href="/vs">Comparisons</a> &middot; <a href="/discover">Discover</a> &middot; <a href="/docs">API</a>
</p>
</div>
</footer>"""
