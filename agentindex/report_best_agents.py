"""
"Best AI Agents" article pages — 5 categories, all from live DB.
Routes: /report/best-{slug}-agents-2026
Cached 1 hour.
"""

import logging
import time as _time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.report.best")

router_best_agents = APIRouter(tags=["report"])

_SOURCE_NAMES = {
    "github": "GitHub", "npm_full": "npm", "pypi_full": "PyPI",
    "huggingface_full": "HuggingFace", "mcp": "MCP registries",
}

ARTICLES = [
    {
        "slug": "coding",
        "title": "Best AI Coding Agents 2026",
        "meta_desc": "Top 15 AI coding agents ranked by trust score. From code assistants to autonomous debugging — data-driven rankings from 10,000+ coding agents.",
        "intro": "The AI coding agent space has exploded. From code completion to autonomous debugging, "
                 "developers now have thousands of AI-powered tools to choose from. But which ones can you actually trust? "
                 "We ranked all {total} coding agents in the Nerq index by Trust Score — a composite metric covering "
                 "security, maintenance, popularity, documentation, and ecosystem signals.",
        "category_filter": "category = 'coding'",
        "benchmark_cat": "coding",
    },
    {
        "slug": "communication",
        "title": "Best AI Customer Service & Communication Agents 2026",
        "meta_desc": "Top 15 AI communication agents ranked by trust score. Voice agents, chatbots, email automation — data-driven rankings.",
        "intro": "AI agents are transforming how businesses communicate — from WhatsApp bots to voice assistants "
                 "to automated email workflows. We ranked all {total} communication agents in the Nerq index by Trust Score "
                 "to find the most reliable, well-maintained, and secure options.",
        "category_filter": "category = 'communication'",
        "benchmark_cat": "communication",
    },
    {
        "slug": "devops",
        "title": "Best AI DevOps Agents 2026",
        "meta_desc": "Top 15 AI DevOps and infrastructure agents ranked by trust score. From Kubernetes deployment to monitoring — data-driven rankings.",
        "intro": "DevOps is where AI agents deliver the most immediate value — automating deployments, managing infrastructure, "
                 "and resolving incidents autonomously. We ranked all {total} DevOps and infrastructure agents in the Nerq index "
                 "by Trust Score to identify the most production-ready tools.",
        "category_filter": "category IN ('devops', 'infrastructure')",
        "benchmark_cat": "devops",
    },
    {
        "slug": "content",
        "title": "Best AI Content Creation Agents 2026",
        "meta_desc": "Top 15 AI content creation and marketing agents ranked by trust score. Writing, SEO, social media — data-driven rankings.",
        "intro": "Content creation is one of the fastest-growing use cases for AI agents — from blog writing to video production "
                 "to social media automation. We ranked all {total} content and marketing agents in the Nerq index "
                 "by Trust Score to find the tools that are actually reliable and well-maintained.",
        "category_filter": "category IN ('content', 'marketing')",
        "benchmark_cat": "content",
    },
    {
        "slug": "security",
        "title": "Best AI Security Agents 2026",
        "meta_desc": "Top 15 AI security agents ranked by trust score. Pentesting, SOC automation, vulnerability scanning — data-driven rankings.",
        "intro": "Security is a natural fit for AI agents — from automated penetration testing to real-time threat detection. "
                 "We ranked all {total} security agents in the Nerq index by Trust Score. In security especially, "
                 "trust and maintenance quality matter — a poorly maintained security tool is worse than none at all.",
        "category_filter": "category = 'security'",
        "benchmark_cat": "security",
    },
]

# Per-article cache
_cache: dict[str, dict] = {}
_CACHE_TTL = 3600


def _query_article(art: dict) -> dict:
    session = get_session()
    try:
        cat_filter = art["category_filter"]
        rows = session.execute(text(f"""
            SELECT name, agent_type, trust_score_v2, trust_grade, source, stars,
                   LEFT(description, 200) as desc_short
            FROM entity_lookup
            WHERE is_active = true
            AND agent_type IN ('agent', 'tool', 'mcp_server')
            AND {cat_filter}
            AND trust_score_v2 IS NOT NULL
            ORDER BY trust_score_v2 DESC, stars DESC NULLS LAST
            LIMIT 15
        """)).fetchall()

        total = session.execute(text(f"""
            SELECT COUNT(*) FROM entity_lookup
            WHERE is_active = true
            AND agent_type IN ('agent', 'tool', 'mcp_server')
            AND {cat_filter}
        """)).scalar() or 0

        return {
            "agents": [dict(zip(
                ["name", "agent_type", "trust_score", "trust_grade", "source", "stars", "description"], r
            )) for r in rows],
            "total": total,
        }
    finally:
        session.close()


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if s else ""


def _fmt(n) -> str:
    if n is None:
        return "&mdash;"
    return f"{n:,}" if isinstance(n, int) else str(n)


def _type_label(t: str) -> str:
    if t == "mcp_server":
        return "MCP server"
    return t


def _build_itemlist_json(art: dict, agents: list) -> str:
    import json
    items = []
    for i, a in enumerate(agents, 1):
        items.append({
            "@type": "ListItem",
            "position": i,
            "item": {
                "@type": "SoftwareApplication",
                "name": a["name"],
                "applicationCategory": "AI Agent",
                "aggregateRating": {
                    "@type": "AggregateRating",
                    "ratingValue": round(a["trust_score"], 1),
                    "bestRating": 100,
                    "worstRating": 0,
                    "ratingCount": 1
                }
            }
        })
    schema = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": art["title"],
        "numberOfItems": len(agents),
        "itemListElement": items
    }
    # Escape braces for f-string by returning raw JSON
    return json.dumps(schema, ensure_ascii=False)


def _build_article(art: dict, data: dict) -> str:
    agents = data["agents"]
    total = data["total"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Table rows
    table_rows = ""
    for i, a in enumerate(agents, 1):
        src = _SOURCE_NAMES.get(a["source"], a["source"])
        stars = _fmt(a["stars"]) if a["stars"] else "&mdash;"
        desc = _esc(a["description"] or "")
        if len(desc) > 180:
            desc = desc[:177] + "..."
        atype = _type_label(a["agent_type"])
        table_rows += f"""<tr>
<td>{i}</td>
<td><strong><a href="/kya?agent={_esc(a['name'])}">{_esc(a['name'])}</a></strong></td>
<td><code>{atype}</code></td>
<td class="num-cell">{a['trust_score']:.1f}</td>
<td>{a['trust_grade'] or ''}</td>
<td>{src}</td>
<td class="num-cell">{stars}</td>
</tr>
<tr><td colspan="7" style="font-size:13px;color:#6b7280;padding:4px 10px 12px;border-bottom:1px solid #e5e7eb">{desc}</td></tr>
"""

    # Detail cards
    detail_cards = ""
    for i, a in enumerate(agents[:5], 1):
        src = _SOURCE_NAMES.get(a["source"], a["source"])
        stars_str = f" &middot; {_fmt(a['stars'])} stars" if a["stars"] else ""
        desc = _esc(a["description"] or "")
        atype = _type_label(a["agent_type"])
        detail_cards += f"""<div class="card">
<h3>{i}. {_esc(a['name'])} <span style="font-size:13px;font-weight:400;color:#6b7280">&mdash; {atype}</span></h3>
<p style="font-size:14px;margin:6px 0">{desc}</p>
<p style="font-size:13px;color:#6b7280">Trust: <strong>{a['trust_score']:.1f}/100</strong> ({a['trust_grade']}) &middot; {src}{stars_str} &middot; <a href="/kya?agent={_esc(a['name'])}">full report</a></p>
</div>
"""

    intro = art["intro"].format(total=_fmt(total))
    benchmark_cat = art["benchmark_cat"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(art['title'])} | Nerq</title>
<meta name="description" content="{_esc(art['meta_desc'])}">
<link rel="canonical" href="https://nerq.ai/report/best-{art['slug']}-agents-2026">
<meta name="robots" content="index, follow">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Nerq">
<meta property="og:title" content="{_esc(art['title'])}">
<meta property="og:description" content="{_esc(art['meta_desc'])}">
<meta property="og:url" content="https://nerq.ai/report/best-{art['slug']}-agents-2026">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Article","headline":"{_esc(art['title'])}","description":"{_esc(art['meta_desc'])}","url":"https://nerq.ai/report/best-{art['slug']}-agents-2026","datePublished":"2026-03-09","dateModified":"{generated}","author":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}},"publisher":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}},"mainEntityOfPage":"https://nerq.ai/report/best-{art['slug']}-agents-2026"}}
</script>
<script type="application/ld+json">
{_build_itemlist_json(art, agents)}
</script>
<style>{NERQ_CSS}
table{{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0}}
th{{text-align:left;padding:8px 10px;border-bottom:2px solid #e5e7eb;color:#6b7280;font-weight:600;font-size:12px}}
td{{padding:6px 10px;border-bottom:1px solid #e5e7eb}}
.num-cell{{font-family:ui-monospace,'SF Mono',monospace;text-align:right}}
.card{{border:1px solid #e5e7eb;padding:16px;margin-bottom:12px}}
.card h3{{font-size:15px;margin-bottom:4px}}
.cta{{display:inline-block;padding:8px 20px;background:#0d9488;color:#fff;font-size:14px;font-weight:600;text-decoration:none;margin:8px 4px 8px 0}}
.cta:hover{{background:#0f766e;text-decoration:none;color:#fff}}
.cta-outline{{display:inline-block;padding:8px 20px;border:1px solid #e5e7eb;font-size:14px;text-decoration:none;color:#6b7280;margin:8px 4px 8px 0}}
.cta-outline:hover{{border-color:#0d9488;color:#0d9488;text-decoration:none}}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px;max-width:800px">

<div class="breadcrumb"><a href="/">nerq</a> / <a href="/report/q1-2026">reports</a> / best {art['slug']} agents</div>

<h1>{_esc(art['title'])}</h1>
<p style="font-size:13px;color:#6b7280;margin:4px 0 16px">Published {generated} &middot; Data from <a href="https://nerq.ai">nerq.ai</a> &middot; Updated hourly</p>

<p style="font-size:15px;line-height:1.7;margin-bottom:20px">{intro}</p>

<h2 style="border-top:none;padding-top:0">Top 5 — in detail</h2>
{detail_cards}

<h2>Full ranking — top 15</h2>
<table>
<tr><th>#</th><th>Name</th><th>Type</th><th style="text-align:right">Score</th><th>Grade</th><th>Source</th><th style="text-align:right">Stars</th></tr>
{table_rows}
</table>

<h2>How we rank</h2>
<p style="font-size:14px;line-height:1.7">Rankings are based on the <strong>Nerq Trust Score</strong> (0-100), a composite metric covering:</p>
<ul style="font-size:14px;line-height:1.8">
<li><strong>Security</strong> (30%) &mdash; vulnerability audit, dependency safety</li>
<li><strong>Maintenance</strong> (25%) &mdash; commit recency, release cadence</li>
<li><strong>Popularity</strong> (20%) &mdash; stars, downloads, community</li>
<li><strong>Documentation</strong> (15%) &mdash; README, API docs, examples</li>
<li><strong>Ecosystem</strong> (10%) &mdash; protocol support, integrations</li>
</ul>
<p style="font-size:14px;margin-top:12px">Scores update continuously as new data is crawled. These rankings reflect live data from the Nerq index of {_fmt(total)} {art['slug']} agents.</p>

<div style="margin:24px 0">
<a href="/v1/agent/benchmark/{benchmark_cat}" class="cta">live API ranking</a>
<a href="/kya" class="cta-outline">check any agent</a>
<a href="/nerq/docs" class="cta-outline">API docs</a>
<a href="/report/q1-2026" class="cta-outline">full Q1 report</a>
</div>

<h2>Related reports</h2>
<ul style="font-size:14px;line-height:2">
<li><a href="/report/q1-2026">State of AI Assets &mdash; Q1 2026</a></li>
{"".join(f'<li><a href="/report/best-{a["slug"]}-agents-2026">{a["title"]}</a></li>' for a in ARTICLES if a["slug"] != art["slug"])}
</ul>

<div style="font-size:12px;color:#6b7280;margin-top:32px;padding-top:16px;border-top:1px solid #e5e7eb">
Data from nerq.ai on {generated}. Live ranking: <a href="/v1/agent/benchmark/{benchmark_cat}">nerq.ai/v1/agent/benchmark/{benchmark_cat}</a>
</div>

</main>
{NERQ_FOOTER}
</body>
</html>"""


def _get_or_build(art: dict) -> str:
    slug = art["slug"]
    now = _time.time()
    cached = _cache.get(slug)
    if cached and (now - cached["ts"]) < _CACHE_TTL:
        return cached["html"]

    data = _query_article(art)
    html = _build_article(art, data)
    _cache[slug] = {"html": html, "ts": now}
    return html


# Register routes for all 5 articles
for _art in ARTICLES:
    _slug = _art["slug"]

    def _make_handler(article=_art):
        def handler():
            return HTMLResponse(_get_or_build(article))
        return handler

    router_best_agents.add_api_route(
        f"/report/best-{_slug}-agents-2026",
        _make_handler(),
        methods=["GET"],
        response_class=HTMLResponse,
    )
