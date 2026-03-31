"""
Nerq Trust Badge API — SVG badges for README embedding.
Routes: /badge/{name}, /badge/npm/{pkg}, /badge/pypi/{pkg}, /badges
"""

import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.badge")

router_badge = APIRouter(tags=["badge"])

# Trust grade colors
_GRADE_COLORS = {
    "A+": "#22c55e", "A": "#22c55e",
    "B": "#22c55e",
    "C": "#eab308",
    "D": "#eab308",
    "E": "#ef4444",
    "F": "#ef4444",
}
_UNKNOWN_COLOR = "#9ca3af"


def _svg_badge(label: str, value: str, color: str) -> str:
    """Generate a shields.io-style SVG badge."""
    lw = max(len(label) * 6.5 + 14, 40)
    vw = max(len(value) * 6.5 + 14, 40)
    tw = lw + vw
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{tw:.0f}" height="20" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
  <clipPath id="r"><rect width="{tw:.0f}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{lw:.0f}" height="20" fill="#555"/>
    <rect x="{lw:.0f}" width="{vw:.0f}" height="20" fill="{color}"/>
    <rect width="{tw:.0f}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="11">
    <text x="{lw / 2:.0f}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{lw / 2:.0f}" y="14">{label}</text>
    <text x="{lw + vw / 2:.0f}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{lw + vw / 2:.0f}" y="14">{value}</text>
  </g>
</svg>'''


def _badge_response(svg: str) -> Response:
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=300",
            "Access-Control-Allow-Origin": "*",
        },
    )


def _lookup_agent(name: str) -> tuple:
    """Lookup agent by name. Returns (score, grade) or (None, None).
    Runs all match strategies and picks the highest-scored result.
    Priority: exact full name > suffix after '/' > partial ILIKE.
    """
    session = get_session()
    try:
        row = session.execute(text("""
            SELECT trust_score_v2, trust_grade, match_rank FROM (
                SELECT trust_score_v2, trust_grade, 1 AS match_rank FROM agents
                WHERE is_active = true AND LOWER(name) = LOWER(:name)
                AND agent_type IN ('agent', 'tool', 'mcp_server')
              UNION ALL
                SELECT trust_score_v2, trust_grade, 2 AS match_rank FROM agents
                WHERE is_active = true AND lower(name::text) LIKE lower(:suffix)
                AND agent_type IN ('agent', 'tool', 'mcp_server')
              UNION ALL
                SELECT trust_score_v2, trust_grade, 3 AS match_rank FROM agents
                WHERE is_active = true AND lower(name::text) LIKE lower(:pattern)
                AND agent_type IN ('agent', 'tool', 'mcp_server')
            ) sub
            WHERE trust_score_v2 IS NOT NULL
            ORDER BY trust_score_v2 DESC
            LIMIT 1
        """), {"name": name, "suffix": f"%/{name}", "pattern": f"%{name}%"}).fetchone()
        if row and row[0] is not None:
            return (row[0], row[1])
        return (None, None)
    finally:
        session.close()


def _lookup_by_source(pkg: str, source_prefix: str) -> tuple:
    """Lookup by package name in a specific source."""
    session = get_session()
    try:
        row = session.execute(text("""
            SELECT trust_score_v2, trust_grade FROM agents
            WHERE is_active = true AND source LIKE :src
            AND (name = :name OR lower(name::text) LIKE lower(:iname))
            ORDER BY trust_score_v2 DESC NULLS LAST LIMIT 1
        """), {"src": f"{source_prefix}%", "name": pkg, "iname": f"%{pkg}%"}).fetchone()
        if row and row[0] is not None:
            return (row[0], row[1])
        return (None, None)
    finally:
        session.close()


def _make_badge(score, grade) -> Response:
    if score is None:
        return _badge_response(_svg_badge("nerq trust", "unknown", _UNKNOWN_COLOR))
    score_val = round(score, 1)
    grade_str = grade or "?"
    if score >= 70:
        color = "#22c55e"
    elif score >= 40:
        color = "#eab308"
    else:
        color = "#ef4444"
    value = f"{score_val} {grade_str}"
    return _badge_response(_svg_badge("nerq trust", value, color))


_REGISTRY_BEST = {
    "npm": "npm-packages", "pypi": "python-packages", "crates": "best-rust-crates",
    "wordpress": "best-wordpress-plugins", "chrome": "chrome-extensions",
    "firefox": "firefox-addons", "vscode": "best-vscode-extensions",
    "ios": "ios-apps", "android": "android-apps", "steam": "steam-games",
    "vpn": "safest-vpns", "homebrew": "homebrew-cli-tools",
    "website": "safest-websites", "saas": "saas-tools",
}


def _badge_html_page(name: str, score, grade, registry: str = "") -> HTMLResponse:
    """HTML landing page for a badge — SEO + cross-pollination."""
    import html as h
    import json
    from datetime import date
    dn = name.split("/")[-1].replace("-", " ").replace("_", " ").title()
    slug = name.lower().replace("/", "-").replace(" ", "-")
    score_str = f"{round(score, 1)}" if score is not None else "N/A"
    grade_str = h.escape(grade or "N/A")
    today = date.today().isoformat()

    if score and score >= 70:
        color = "#22c55e"
    elif score and score >= 40:
        color = "#eab308"
    else:
        color = "#ef4444"

    svg = _svg_badge("nerq trust", f"{score_str} {grade_str}", color if score else _UNKNOWN_COLOR)
    md_code = f"[![Nerq Trust Score](https://nerq.ai/badge/{h.escape(name)})](https://nerq.ai/safe/{h.escape(slug)})"
    html_code = f'&lt;a href="https://nerq.ai/safe/{h.escape(slug)}"&gt;&lt;img src="https://nerq.ai/badge/{h.escape(name)}" alt="Nerq Trust Score"&gt;&lt;/a&gt;'

    # Cross-links
    best_slug = _REGISTRY_BEST.get(registry, "")
    best_link = f'<a href="/best/{best_slug}" style="color:#2563eb">See all safest {h.escape(registry)} &rarr;</a>' if best_slug else ""

    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "WebPage",
        "name": f"{dn} — Nerq Trust Badge",
        "description": f"Trust badge for {dn}. Nerq Trust Score: {score_str}/100 ({grade_str}).",
        "url": f"https://nerq.ai/badge/{name}?format=html",
        "dateModified": today,
        "publisher": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
    })

    from agentindex.nerq_design import nerq_head, render_hreflang
    _head = nerq_head(
        f"{dn} Trust Badge — {score_str}/100 ({grade_str}) | Nerq",
        f"Nerq Trust Badge for {dn}. Trust Score: {score_str}/100, Grade: {grade_str}. Embed in your README.",
        f"https://nerq.ai/badge/{name}?format=html",
    )

    return HTMLResponse(f"""{_head}
<script type="application/ld+json">{jsonld}</script>
<main class="container" style="padding-top:20px;padding-bottom:40px">
  <nav class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/badges">badges</a> &rsaquo; {h.escape(dn)}</nav>

  <h1 style="font-size:1.5rem;font-weight:700;margin-bottom:12px">{h.escape(dn)} — Trust Badge</h1>

  <div style="display:flex;align-items:center;gap:20px;margin:16px 0;padding:20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px">
    <div>{svg}</div>
    <div>
      <div style="font-size:24px;font-weight:700">{score_str}<span style="color:#94a3b8">/100</span></div>
      <div style="font-size:14px;color:#64748b">Grade: <strong>{grade_str}</strong></div>
      <div style="font-size:12px;color:#94a3b8">Last updated: {today}</div>
    </div>
  </div>

  <h2 style="font-size:1.1rem;margin:24px 0 8px">Embed this badge</h2>
  <p style="font-size:14px;color:#64748b;margin-bottom:12px">Add this badge to your README to show your trust score:</p>

  <div style="margin-bottom:16px">
    <div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:4px">Markdown</div>
    <pre style="background:#0f172a;color:#e2e8f0;padding:12px;border-radius:6px;font-size:13px;overflow-x:auto">{h.escape(md_code)}</pre>
  </div>
  <div style="margin-bottom:24px">
    <div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:4px">HTML</div>
    <pre style="background:#0f172a;color:#e2e8f0;padding:12px;border-radius:6px;font-size:13px;overflow-x:auto">{html_code}</pre>
  </div>

  <h2 style="font-size:1.1rem;margin:24px 0 8px">About {h.escape(dn)}</h2>
  <div style="display:flex;flex-wrap:wrap;gap:10px;margin:12px 0">
    <a href="/safe/{h.escape(slug)}" style="padding:8px 16px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;text-decoration:none;color:#1e40af;font-size:14px;font-weight:500">Safety Report &rarr;</a>
    <a href="/alternatives/{h.escape(slug)}" style="padding:8px 16px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;text-decoration:none;color:#166534;font-size:14px;font-weight:500">Alternatives &rarr;</a>
    <a href="/review/{h.escape(slug)}" style="padding:8px 16px;background:#fefce8;border:1px solid #fde68a;border-radius:6px;text-decoration:none;color:#854d0e;font-size:14px;font-weight:500">Reviews &rarr;</a>
  </div>
  {f'<div style="margin-top:12px">{best_link}</div>' if best_link else ''}

  <p style="margin-top:24px;font-size:12px;color:#94a3b8">Nerq Trust Scores are independent assessments based on security, maintenance, community, and compliance signals. <a href="/protocol">Learn more</a>.</p>
</main>
{NERQ_FOOTER}
</body>
</html>""")


@router_badge.get("/badge/{agent_name:path}")
async def trust_badge(agent_name: str, format: str = "svg"):
    """SVG trust badge or HTML landing page. Embed in README files."""
    # Handle /badge/npm/X and /badge/pypi/X
    if agent_name.startswith("npm/"):
        pkg = agent_name[4:]
        score, grade = _lookup_by_source(pkg, "npm")
        if format == "html":
            return _badge_html_page(pkg, score, grade, "npm")
        return _make_badge(score, grade)
    if agent_name.startswith("pypi/"):
        pkg = agent_name[5:]
        score, grade = _lookup_by_source(pkg, "pypi")
        if format == "html":
            return _badge_html_page(pkg, score, grade, "pypi")
        return _make_badge(score, grade)

    score, grade = _lookup_agent(agent_name)
    if format == "html":
        return _badge_html_page(agent_name, score, grade)
    return _make_badge(score, grade)


@router_badge.get("/badge-json/{agent_name:path}")
async def trust_badge_json(agent_name: str):
    """Shields.io JSON endpoint. Use with: https://img.shields.io/endpoint?url=https://nerq.ai/badge-json/AGENT"""
    if agent_name.startswith("npm/"):
        score, grade = _lookup_by_source(agent_name[4:], "npm")
    elif agent_name.startswith("pypi/"):
        score, grade = _lookup_by_source(agent_name[5:], "pypi")
    else:
        score, grade = _lookup_agent(agent_name)

    if score is None:
        return {"schemaVersion": 1, "label": "nerq trust", "message": "unknown", "color": "lightgrey"}

    if score >= 70:
        color = "brightgreen"
    elif score >= 40:
        color = "yellow"
    else:
        color = "red"

    return {"schemaVersion": 1, "label": "nerq trust", "message": f"{round(score, 1)} {grade or '?'}", "color": color}


# ── Badge showcase page ──────────────────────────────────

@router_badge.get("/badges", response_class=HTMLResponse)
async def badges_page():
    return HTMLResponse(_render_badges_page())


def _render_badges_page() -> str:
    examples = [
        ("SWE-agent/SWE-agent", "SWE-agent"),
        ("RooCodeInc/Roo-Code", "Roo-Code"),
        ("harbor", "harbor"),
        ("tavily-ai/tavily-mcp", "tavily-mcp"),
    ]

    example_rows = ""
    for name, short in examples:
        md = f"[![Nerq Trust](https://nerq.ai/badge/{name})](https://nerq.ai/kya/{name})"
        html_snip = f'<a href="https://nerq.ai/kya/{name}"><img src="https://nerq.ai/badge/{name}" alt="Nerq Trust"></a>'
        example_rows += f"""<div class="card">
<h3>{short}</h3>
<p><img src="/badge/{name}" alt="Nerq Trust badge for {short}" style="vertical-align:middle"></p>
<p style="font-size:12px;color:#6b7280;margin-top:8px">Markdown:</p>
<pre style="font-size:12px;user-select:all">{_esc(md)}</pre>
</div>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trust Badges | Nerq</title>
<meta name="description" content="Add a Nerq Trust badge to your README. Show your agent's trust score with an embeddable SVG badge.">
<link rel="canonical" href="https://nerq.ai/badges">
<meta name="robots" content="index, follow">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"WebPage","name":"Nerq Trust Badges","url":"https://nerq.ai/badges","description":"Embeddable SVG trust badges for AI agent READMEs."}}
</script>
<style>{NERQ_CSS}
.card{{border:1px solid #e5e7eb;padding:16px;margin-bottom:12px}}
.card h3{{font-size:15px;margin-bottom:8px}}
pre{{user-select:all;cursor:text}}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px;max-width:800px">

<h1>trust badges</h1>
<p class="desc">Add a Nerq Trust badge to your AI agent's README</p>

<div style="margin:20px 0;padding:20px;background:#f9fafb;border:1px solid #e5e7eb">
<p style="font-size:15px;margin-bottom:12px"><strong>Your agent's badge:</strong></p>
<p style="font-size:14px;color:#6b7280;margin-bottom:8px">Replace <code>AGENT_NAME</code> with your agent's name as it appears in the Nerq index.</p>
<pre style="font-size:13px">[![Nerq Trust](https://nerq.ai/badge/AGENT_NAME)](https://nerq.ai/kya/AGENT_NAME)</pre>
</div>

<h2>examples</h2>
{example_rows}

<h2>badge variants</h2>
<table>
<tr><th>Endpoint</th><th>Description</th></tr>
<tr><td><code>/badge/{{name}}</code></td><td>Lookup by agent name</td></tr>
<tr><td><code>/badge/npm/{{package}}</code></td><td>Lookup by npm package name</td></tr>
<tr><td><code>/badge/pypi/{{package}}</code></td><td>Lookup by PyPI package name</td></tr>
</table>

<h2>embed formats</h2>

<h3>Markdown</h3>
<pre>[![Nerq Trust](https://nerq.ai/badge/YOUR_AGENT)](https://nerq.ai/kya/YOUR_AGENT)</pre>

<h3>HTML</h3>
<pre>{_esc('<a href="https://nerq.ai/kya/YOUR_AGENT"><img src="https://nerq.ai/badge/YOUR_AGENT" alt="Nerq Trust"></a>')}</pre>

<h3>reStructuredText</h3>
<pre>.. image:: https://nerq.ai/badge/YOUR_AGENT
   :target: https://nerq.ai/kya/YOUR_AGENT
   :alt: Nerq Trust</pre>

<h2>how it works</h2>
<ul style="font-size:14px;line-height:1.8">
<li>The badge shows the agent's <strong>Nerq Trust Score</strong> (0-100) and grade (A+ through F)</li>
<li>Green (70+) = high trust, yellow (40-69) = medium trust, red (&lt;40) = low trust</li>
<li>Badges are cached for 5 minutes and update automatically as scores change</li>
<li>Returns <code>image/svg+xml</code> — works everywhere images are supported</li>
<li>If the agent is not found, shows "unknown" in gray</li>
</ul>

<p style="font-size:13px;color:#6b7280;margin-top:24px">
<a href="/nerq/docs#badges">API docs</a> &middot;
<a href="/kya">check any agent</a> &middot;
<a href="/reports">reports</a>
</p>

</main>
{NERQ_FOOTER}
</body>
</html>"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if s else ""


@router_badge.get("/sitemap-badges.xml")
async def sitemap_badges():
    """Sitemap for badge HTML landing pages — top 200 entities."""
    from datetime import date as _d
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT name FROM agents
            WHERE is_active = true AND trust_score_v2 IS NOT NULL AND trust_score_v2 > 0
            ORDER BY COALESCE(stars, 0) DESC LIMIT 200
        """)).fetchall()
    finally:
        session.close()
    now = _d.today().isoformat()
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for r in rows:
        name = _esc(r[0])
        xml += f'<url><loc>https://nerq.ai/badge/{name}?format=html</loc><lastmod>{now}</lastmod><priority>0.5</priority></url>\n'
    xml += '</urlset>'
    return Response(xml, media_type="application/xml")
