"""
Popular AI Agents Page — nerq.ai/popular
========================================
Top 50 agents by trust score, targeting "popular AI agents" search query.
Includes FAQ schema for rich snippets.
"""

import json
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from agentindex.db.models import get_session
from agentindex.nerq_design import nerq_head, NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.popular")

_cache = {"html": None, "ts": 0}
_CACHE_TTL = 1800  # 30 min


def _esc(s):
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _fetch_top_agents(limit=50):
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT name, source, trust_score_v2, trust_grade, category, stars, downloads,
                   description, source_url
            FROM entity_lookup
            WHERE is_active = true
              AND agent_type IN ('agent', 'tool', 'mcp_server')
              AND trust_score_v2 IS NOT NULL
              AND trust_score_v2 > 0
            ORDER BY trust_score_v2 DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()
        return [
            {
                "name": r[0], "source": r[1], "score": round(r[2], 1),
                "grade": r[3], "category": r[4], "stars": r[5],
                "downloads": r[6], "desc": (r[7] or "")[:200],
                "url": r[8],
            }
            for r in rows
        ]
    finally:
        session.close()


def _grade_color(grade):
    if not grade:
        return "#9ca3af"
    g = grade[0]
    if g == "A":
        return "#22c55e"
    if g == "B":
        return "#3b82f6"
    if g == "C":
        return "#eab308"
    return "#ef4444"


def _build_page(agents):
    rows = ""
    for i, a in enumerate(agents, 1):
        name_esc = _esc(a["name"])
        stars = f'{a["stars"]:,}' if a["stars"] else "—"
        dl = f'{a["downloads"]:,}' if a["downloads"] else "—"
        cat = _esc(a["category"] or "—")
        src = _esc(a["source"] or "")
        color = _grade_color(a["grade"])
        badge = f'<span style="background:{color};color:#fff;padding:2px 8px;font-size:12px;font-weight:600;white-space:nowrap">{a["grade"] or "?"}</span>'
        link = f'/kya/{a["name"]}' if a["name"] else "#"
        rows += f"""<tr>
<td style="text-align:center;color:#6b7280">{i}</td>
<td><a href="{link}" style="font-weight:600;color:#111">{name_esc}</a><br><span style="font-size:12px;color:#6b7280">{_esc(a['desc'][:100])}</span></td>
<td style="text-align:center">{badge}</td>
<td style="text-align:right;font-family:ui-monospace,monospace">{a['score']}</td>
<td>{cat}</td>
<td style="text-align:right">{stars}</td>
<td style="text-align:right">{dl}</td>
<td style="font-size:12px;color:#6b7280">{src}</td>
</tr>"""

    faq_items = [
        ("What are the most popular AI agents?", "The most popular AI agents by trust score include frameworks like LangChain, CrewAI, AutoGen, and tools like SWE-agent. Nerq indexes 204K+ agents from GitHub, npm, PyPI, HuggingFace, and MCP registries with independent Trust Scores."),
        ("How are AI agent trust scores calculated?", "Nerq Trust Scores (0-100) are calculated across 5 dimensions: Code Quality (25%), Community Adoption (25%), Compliance (20%), Operational Health (15%), and Security (15%). Security scoring includes CVE data from the GitHub Advisory Database."),
        ("What is an AI agent?", "An AI agent is an autonomous software system that can perceive its environment, make decisions, and take actions to achieve goals. Unlike simple chatbots, agents can use tools, chain reasoning steps, and interact with external systems."),
        ("How many AI agents exist?", "Nerq indexes over 204,000 AI agents and MCP servers from 6 ecosystems: GitHub, npm, PyPI, HuggingFace, MCP registries, and Docker Hub. The number is growing rapidly as the agentic economy accelerates."),
    ]

    faq_html = ""
    faq_ld = []
    for q, a_text in faq_items:
        faq_html += f"""<details style="margin-bottom:12px;border:1px solid #e5e7eb;padding:12px">
<summary style="font-weight:600;cursor:pointer;font-size:14px">{_esc(q)}</summary>
<p style="margin-top:8px;font-size:14px;color:#374151;line-height:1.7">{_esc(a_text)}</p>
</details>"""
        faq_ld.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a_text}})

    jsonld = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": faq_ld})

    body = f"""
<h1>Popular AI Agents — Trust Ranked</h1>
<p class="desc">Top 50 AI agents by Nerq Trust Score. Updated continuously from 204K+ indexed agents across GitHub, npm, PyPI, HuggingFace, and MCP registries.</p>

<div style="overflow-x:auto;margin:20px 0">
<table style="width:100%;font-size:13px;border-collapse:collapse">
<thead><tr style="background:#f9fafb;text-align:left">
<th style="padding:8px;width:40px">#</th>
<th style="padding:8px">Agent</th>
<th style="padding:8px;text-align:center">Grade</th>
<th style="padding:8px;text-align:right">Score</th>
<th style="padding:8px">Category</th>
<th style="padding:8px;text-align:right">Stars</th>
<th style="padding:8px;text-align:right">Downloads</th>
<th style="padding:8px">Source</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
</div>

<p style="font-size:13px;color:#6b7280;margin:16px 0">
Scores recalculated daily. <a href="/protocol">Trust Score methodology</a> &middot;
<a href="/v1/preflight?target=langchain">Try the API</a> &middot;
<a href="/badges">Add a trust badge</a>
</p>

<h2 style="margin-top:32px">Frequently Asked Questions</h2>
{faq_html}

<script type="application/ld+json">{jsonld}</script>
"""

    return nerq_head(
        title="Popular AI Agents — Top 50 by Trust Score | Nerq",
        description="Top 50 most popular AI agents ranked by Nerq Trust Score. Independent trust ratings for 204K+ agents from GitHub, npm, PyPI, HuggingFace, and MCP registries.",
        canonical="https://nerq.ai/popular",
    ) + f'{NERQ_NAV}<main class="container" style="padding-top:20px;padding-bottom:40px">{body}</main>{NERQ_FOOTER}</body></html>'


def mount_popular_page(app: FastAPI):
    @app.get("/popular", response_class=HTMLResponse, include_in_schema=False)
    async def popular_page(request: Request):
        import time
        now = time.time()
        if _cache["html"] and now - _cache["ts"] < _CACHE_TTL:
            return HTMLResponse(_cache["html"])
        agents = _fetch_top_agents(50)
        html = _build_page(agents)
        _cache["html"] = html
        _cache["ts"] = now
        return HTMLResponse(html)
