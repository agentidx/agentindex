"""
State of AI Assets — Q1 2026
Route: /report/q1-2026
Generated from live PostgreSQL data, cached for 1 hour.
"""

import logging
import time as _time
from datetime import datetime, timezone

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.report")

router_report = APIRouter(tags=["report"])

_report_cache: dict = {"html": None, "ts": 0}
_REPORT_TTL = 3600  # 1 hour

# Category normalization
_CAT_NORMALIZE = {
    "ai_tool": "AI tool", "AI_tool": "AI tool",
    "ai_assistant": "AI assistant", "AI_assistant": "AI assistant",
    "AI assistants": "AI assistant", "personal_ai_assistant": "AI assistant",
    "personal_assistant": "AI assistant",
    "ai": "AI tool", "AI": "AI tool",
    "agent_platform": "agent platform",
    "autonomous agents": "autonomous agents", "autonomous": "autonomous agents",
    "autonomy": "autonomous agents",
    "AI agent": "AI tool", "agent": "AI tool",
    "AI assistance": "AI assistant",
    "AI|automation": "automation",
    "communication|productivity": "communication",
    "customer_service": "communication",
    "human-resources": "recruitment",
}

# Source display names
_SOURCE_NAMES = {
    "github": "GitHub",
    "npm_full": "npm",
    "pypi_full": "PyPI",
    "huggingface_full": "HuggingFace",
    "huggingface_author2": "HuggingFace",
    "huggingface_w2": "HuggingFace",
    "mcp": "MCP registries",
    "dockerhub": "Docker Hub",
}


def _fmt(n: int) -> str:
    """Format number with comma separators."""
    return f"{n:,}"


def _pct(part: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{part / total * 100:.1f}%"


def _query_report_data() -> dict:
    """Run all report queries against PostgreSQL."""
    session = get_session()
    try:
        # 1. Total counts by type
        type_rows = session.execute(text("""
            SELECT agent_type, COUNT(*) FROM entity_lookup
            WHERE is_active = true GROUP BY agent_type ORDER BY COUNT(*) DESC
        """)).fetchall()
        type_counts = {(r[0] or "unclassified"): r[1] for r in type_rows}

        # 2. Growth — 7d and 30d
        growth_7d = session.execute(text("""
            SELECT COALESCE(agent_type, 'other'), COUNT(*) FROM entity_lookup
            WHERE is_active = true AND first_indexed > NOW() - INTERVAL '7 days'
            GROUP BY agent_type ORDER BY COUNT(*) DESC
        """)).fetchall()
        growth_30d = session.execute(text("""
            SELECT COALESCE(agent_type, 'other'), COUNT(*) FROM entity_lookup
            WHERE is_active = true AND first_indexed > NOW() - INTERVAL '30 days'
            GROUP BY agent_type ORDER BY COUNT(*) DESC
        """)).fetchall()

        AT_FILTER = "agent_type IN ('agent', 'tool', 'mcp_server')"

        # 3. Top categories
        cat_rows = session.execute(text(f"""
            SELECT COALESCE(category, 'uncategorized') as cat, COUNT(*)
            FROM entity_lookup WHERE is_active = true AND {AT_FILTER}
            GROUP BY cat ORDER BY COUNT(*) DESC LIMIT 30
        """)).fetchall()

        # 4. Framework distribution
        fw_rows = session.execute(text(f"""
            SELECT fw, COUNT(*) FROM entity_lookup,
            LATERAL unnest(frameworks) AS fw
            WHERE is_active = true AND {AT_FILTER}
            GROUP BY fw ORDER BY COUNT(*) DESC LIMIT 15
        """)).fetchall()

        # 5. Language distribution (language not in entity_lookup)
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        lang_rows = session.execute(text(f"""
            SELECT language, COUNT(*) FROM agents
            WHERE is_active = true AND {AT_FILTER}
            AND language IS NOT NULL AND language != 'unknown'
            GROUP BY language ORDER BY COUNT(*) DESC LIMIT 10
        """)).fetchall()

        # 6. Source distribution
        src_rows = session.execute(text(f"""
            SELECT source, COUNT(*) FROM entity_lookup
            WHERE is_active = true AND {AT_FILTER}
            GROUP BY source ORDER BY COUNT(*) DESC
        """)).fetchall()

        # 7. Trust distribution
        trust = session.execute(text(f"""
            SELECT
                COUNT(*) FILTER (WHERE trust_score_v2 >= 70) as high,
                COUNT(*) FILTER (WHERE trust_score_v2 >= 40 AND trust_score_v2 < 70) as medium,
                COUNT(*) FILTER (WHERE trust_score_v2 < 40 AND trust_score_v2 IS NOT NULL) as low,
                COUNT(*) FILTER (WHERE trust_score_v2 IS NULL) as unscored,
                ROUND(AVG(trust_score_v2)::numeric, 1) as avg
            FROM entity_lookup WHERE is_active = true AND {AT_FILTER}
        """)).fetchone()

        # 8. Top 20 agents
        top_agents = session.execute(text(f"""
            SELECT name, agent_type, trust_score_v2, trust_grade, source, category, stars
            FROM entity_lookup WHERE is_active = true AND agent_type IN ('agent', 'mcp_server')
            AND trust_score_v2 IS NOT NULL
            ORDER BY trust_score_v2 DESC, stars DESC NULLS LAST LIMIT 20
        """)).fetchall()

        # 9. Top 20 MCP servers
        top_mcp = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, source, stars
            FROM entity_lookup WHERE is_active = true AND agent_type = 'mcp_server'
            AND trust_score_v2 IS NOT NULL
            ORDER BY trust_score_v2 DESC, stars DESC NULLS LAST LIMIT 20
        """)).fetchall()

        # 10. Total assets
        total_assets = session.execute(
            text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'agents'")
        ).scalar() or 0

        return {
            "type_counts": type_counts,
            "growth_7d": {(r[0] or "other"): r[1] for r in growth_7d},
            "growth_30d": {(r[0] or "other"): r[1] for r in growth_30d},
            "categories": [(r[0], r[1]) for r in cat_rows],
            "frameworks": [(r[0], r[1]) for r in fw_rows],
            "languages": [(r[0], r[1]) for r in lang_rows],
            "sources": [(r[0], r[1]) for r in src_rows],
            "trust_high": trust[0] or 0,
            "trust_medium": trust[1] or 0,
            "trust_low": trust[2] or 0,
            "trust_unscored": trust[3] or 0,
            "trust_avg": float(trust[4]) if trust[4] else 0,
            "top_agents": [dict(zip(
                ["name", "agent_type", "trust_score", "trust_grade", "source", "category", "stars"], r
            )) for r in top_agents],
            "top_mcp": [dict(zip(
                ["name", "trust_score", "trust_grade", "source", "stars"], r
            )) for r in top_mcp],
            "total_assets": max(total_assets, 0),
        }
    except Exception as e:
        logger.error(f"report query error: {e}")
        raise
    finally:
        session.close()


def _normalize_categories(raw_cats: list[tuple]) -> list[tuple[str, int]]:
    merged: dict[str, int] = {}
    for cat, cnt in raw_cats:
        if cat == "uncategorized":
            continue
        normalized = _CAT_NORMALIZE.get(cat, cat)
        merged[normalized] = merged.get(normalized, 0) + cnt
    return sorted(merged.items(), key=lambda x: -x[1])[:20]


def _normalize_sources(raw_sources: list[tuple]) -> list[tuple[str, int]]:
    merged: dict[str, int] = {}
    for src, cnt in raw_sources:
        name = _SOURCE_NAMES.get(src, src)
        merged[name] = merged.get(name, 0) + cnt
    return sorted(merged.items(), key=lambda x: -x[1])


def _build_report_html(d: dict) -> str:
    tc = d["type_counts"]
    agents = tc.get("agent", 0)
    tools = tc.get("tool", 0)
    mcp = tc.get("mcp_server", 0)
    models = tc.get("model", 0)
    datasets = tc.get("dataset", 0)
    spaces = tc.get("space", 0)
    total_at = agents + tools + mcp

    categories = _normalize_categories(d["categories"])
    sources = _normalize_sources(d["sources"])
    total_scored = d["trust_high"] + d["trust_medium"] + d["trust_low"]

    # Growth
    g7_total = sum(d["growth_7d"].values())
    g30_total = sum(d["growth_30d"].values())

    # --- Build HTML sections ---

    # Type breakdown bar
    type_bar = ""
    if total_at > 0:
        a_pct = agents / total_at * 100
        t_pct = tools / total_at * 100
        m_pct = mcp / total_at * 100
        type_bar = f"""<div class="bar-row">
<div style="display:flex;height:16px;margin:8px 0">
<div style="width:{a_pct:.1f}%;background:#0d9488" title="Agents: {_fmt(agents)}"></div>
<div style="width:{t_pct:.1f}%;background:#6366f1" title="Tools: {_fmt(tools)}"></div>
<div style="width:{m_pct:.1f}%;background:#8b5cf6" title="MCP Servers: {_fmt(mcp)}"></div>
</div>
<div style="display:flex;gap:16px;font-size:12px;color:#6b7280">
<span><span style="display:inline-block;width:10px;height:10px;background:#0d9488;margin-right:4px"></span>agents {_fmt(agents)} ({_pct(agents, total_at)})</span>
<span><span style="display:inline-block;width:10px;height:10px;background:#6366f1;margin-right:4px"></span>tools {_fmt(tools)} ({_pct(tools, total_at)})</span>
<span><span style="display:inline-block;width:10px;height:10px;background:#8b5cf6;margin-right:4px"></span>MCP servers {_fmt(mcp)} ({_pct(mcp, total_at)})</span>
</div>
</div>"""

    # Category table
    cat_rows = ""
    for cat, cnt in categories:
        bar_w = min(cnt / categories[0][1] * 200, 200)
        cat_rows += f'<tr><td>{_esc(cat)}</td><td class="num-cell">{_fmt(cnt)}</td><td><div style="background:#0d9488;height:8px;width:{bar_w:.0f}px"></div></td></tr>\n'

    # Framework table
    fw_rows = ""
    for fw, cnt in d["frameworks"]:
        bar_w = min(cnt / d["frameworks"][0][1] * 200, 200)
        fw_rows += f'<tr><td>{_esc(fw)}</td><td class="num-cell">{_fmt(cnt)}</td><td><div style="background:#6366f1;height:8px;width:{bar_w:.0f}px"></div></td></tr>\n'

    # Language table
    lang_rows = ""
    for lang, cnt in d["languages"]:
        bar_w = min(cnt / d["languages"][0][1] * 200, 200)
        lang_rows += f'<tr><td>{_esc(lang)}</td><td class="num-cell">{_fmt(cnt)}</td><td><div style="background:#8b5cf6;height:8px;width:{bar_w:.0f}px"></div></td></tr>\n'

    # Source table
    src_rows = ""
    for src, cnt in sources:
        src_rows += f'<tr><td>{_esc(src)}</td><td class="num-cell">{_fmt(cnt)}</td><td class="num-cell">{_pct(cnt, total_at)}</td></tr>\n'

    # Trust distribution bar
    trust_bar = ""
    if total_scored > 0:
        h_pct = d["trust_high"] / total_scored * 100
        m_pct_t = d["trust_medium"] / total_scored * 100
        l_pct = d["trust_low"] / total_scored * 100
        trust_bar = f"""<div style="display:flex;height:16px;margin:8px 0">
<div style="width:{h_pct:.1f}%;background:#059669" title="High: {_fmt(d['trust_high'])}"></div>
<div style="width:{m_pct_t:.1f}%;background:#d97706" title="Medium: {_fmt(d['trust_medium'])}"></div>
<div style="width:{l_pct:.1f}%;background:#dc2626" title="Low: {_fmt(d['trust_low'])}"></div>
</div>
<div style="display:flex;gap:16px;font-size:12px;color:#6b7280;margin-top:4px">
<span><span class="pill pill-green">HIGH</span> {_fmt(d['trust_high'])} ({_pct(d['trust_high'], total_scored)})</span>
<span><span class="pill pill-yellow">MEDIUM</span> {_fmt(d['trust_medium'])} ({_pct(d['trust_medium'], total_scored)})</span>
<span><span class="pill pill-red">LOW</span> {_fmt(d['trust_low'])} ({_pct(d['trust_low'], total_scored)})</span>
</div>"""

    # Top agents table
    agent_rows = ""
    for i, a in enumerate(d["top_agents"], 1):
        src_display = _SOURCE_NAMES.get(a["source"], a["source"])
        stars = _fmt(a["stars"]) if a["stars"] else "&mdash;"
        cat = _esc(a["category"] or "")
        atype = "MCP" if a["agent_type"] == "mcp_server" else "agent"
        agent_rows += f'<tr><td>{i}</td><td>{_esc(a["name"])}</td><td><code>{atype}</code></td><td class="num-cell">{a["trust_score"]:.1f}</td><td>{a["trust_grade"] or ""}</td><td>{src_display}</td><td class="num-cell">{stars}</td></tr>\n'

    # Top MCP table
    mcp_rows = ""
    for i, m in enumerate(d["top_mcp"], 1):
        src_display = _SOURCE_NAMES.get(m["source"], m["source"])
        stars = _fmt(m["stars"]) if m["stars"] else "&mdash;"
        mcp_rows += f'<tr><td>{i}</td><td>{_esc(m["name"])}</td><td class="num-cell">{m["trust_score"]:.1f}</td><td>{m["trust_grade"] or ""}</td><td>{src_display}</td><td class="num-cell">{stars}</td></tr>\n'

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>State of AI Assets — Q1 2026 | Nerq</title>
<meta name="description" content="The first comprehensive census of the AI agent ecosystem. {_fmt(d['total_assets'])} assets indexed. {_fmt(total_at)} agents &amp; tools. All trust scored.">
<link rel="canonical" href="https://nerq.ai/report/q1-2026">
<meta name="robots" content="index, follow">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Nerq">
<meta property="og:title" content="State of AI Assets — Q1 2026">
<meta property="og:description" content="The first comprehensive census of the AI agent ecosystem. {_fmt(total_at)} agents &amp; tools trust scored.">
<meta property="og:url" content="https://nerq.ai/report/q1-2026">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Article","headline":"State of AI Assets — Q1 2026","description":"The first comprehensive census of the AI agent ecosystem. {_fmt(d['total_assets'])} assets indexed.","url":"https://nerq.ai/report/q1-2026","datePublished":"2026-03-09","dateModified":"{generated}","author":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}},"publisher":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}},"mainEntityOfPage":"https://nerq.ai/report/q1-2026"}}
</script>
<style>{NERQ_CSS}
.report-stat{{display:inline-block;margin-right:32px;margin-bottom:12px}}
.report-stat .num{{font-family:ui-monospace,'SF Mono',monospace;font-size:1.6rem;font-weight:700;line-height:1.2}}
.report-stat .label{{font-size:12px;color:#6b7280}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0}}
th{{text-align:left;padding:8px 10px;border-bottom:2px solid #e5e7eb;color:#6b7280;font-weight:600;font-size:12px}}
td{{padding:6px 10px;border-bottom:1px solid #e5e7eb}}
.num-cell{{font-family:ui-monospace,'SF Mono',monospace;text-align:right}}
.pill{{display:inline-block;padding:1px 8px;font-size:12px;font-weight:600;border:1px solid #e5e7eb}}
.pill-green{{background:#ecfdf5;color:#065f46;border-color:#a7f3d0}}
.pill-yellow{{background:#fffbeb;color:#92400e;border-color:#fde68a}}
.pill-red{{background:#fef2f2;color:#991b1b;border-color:#fecaca}}
h2{{font-size:1.15rem;font-weight:700;margin:28px 0 10px;padding-top:20px;border-top:1px solid #e5e7eb}}
h2:first-of-type{{border-top:none;padding-top:0}}
.summary-box{{background:#f9fafb;border:1px solid #e5e7eb;padding:20px;margin:16px 0}}
code{{font-family:ui-monospace,'SF Mono',monospace;background:#f5f5f5;padding:1px 5px;font-size:0.9em}}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px;max-width:800px">

<h1>State of AI Assets — Q1 2026</h1>
<p class="desc">The first comprehensive census of the AI agent ecosystem</p>
<p style="font-size:13px;color:#6b7280">Published {generated} &middot; Data from <a href="https://nerq.ai">nerq.ai</a> &middot; <a href="/v1/agent/stats">Live API</a></p>

<h2>1. Executive summary</h2>

<div class="summary-box">
<div class="report-stat"><div class="num">{_fmt(d['total_assets'])}</div><div class="label">total AI assets indexed</div></div>
<div class="report-stat"><div class="num">{_fmt(total_at)}</div><div class="label">agents, tools &amp; MCP servers</div></div>
<div class="report-stat"><div class="num">{_fmt(mcp)}</div><div class="label">MCP servers</div></div>
<div class="report-stat"><div class="num">{d['trust_avg']}/100</div><div class="label">average trust score</div></div>
<div class="report-stat"><div class="num">{_pct(d['trust_high'], total_scored)}</div><div class="label">high trust (70+)</div></div>
<div class="report-stat"><div class="num">{len(d['frameworks'])}</div><div class="label">frameworks tracked</div></div>
</div>

<p>Nerq has indexed <strong>{_fmt(d['total_assets'])} AI assets</strong> from {len(sources)} registries, making it the largest open census of the AI agent ecosystem. Of these, <strong>{_fmt(total_at)}</strong> are agents, tools, and MCP servers — the executable components that power the emerging agentic economy.</p>
<p>Every asset receives a <strong>Trust Score</strong> (0-100) based on security, maintenance, popularity, documentation, and ecosystem signals. The average trust score across all agents and tools is <strong>{d['trust_avg']}/100</strong>.</p>

<h2>2. The AI asset landscape</h2>

<p>The {_fmt(d['total_assets'])} indexed assets break down into:</p>
<table>
<tr><th>Type</th><th style="text-align:right">Count</th><th style="text-align:right">Share</th></tr>
<tr><td>Models</td><td class="num-cell">{_fmt(models)}</td><td class="num-cell">{_pct(models, d['total_assets'])}</td></tr>
<tr><td>Spaces / Apps</td><td class="num-cell">{_fmt(spaces)}</td><td class="num-cell">{_pct(spaces, d['total_assets'])}</td></tr>
<tr><td>Datasets</td><td class="num-cell">{_fmt(datasets)}</td><td class="num-cell">{_pct(datasets, d['total_assets'])}</td></tr>
<tr><td>Agents</td><td class="num-cell">{_fmt(agents)}</td><td class="num-cell">{_pct(agents, d['total_assets'])}</td></tr>
<tr><td>Tools</td><td class="num-cell">{_fmt(tools)}</td><td class="num-cell">{_pct(tools, d['total_assets'])}</td></tr>
<tr><td>MCP Servers</td><td class="num-cell">{_fmt(mcp)}</td><td class="num-cell">{_pct(mcp, d['total_assets'])}</td></tr>
<tr style="font-weight:700"><td>Total</td><td class="num-cell">{_fmt(d['total_assets'])}</td><td class="num-cell">100%</td></tr>
</table>

<p style="font-size:14px">Agents, tools, and MCP servers — the <em>actionable</em> components — represent {_pct(total_at, d['total_assets'])} of all assets:</p>
{type_bar}

<h2>3. What agents do — category distribution</h2>

<p>Top 20 categories among {_fmt(total_at)} agents and tools (excluding uncategorized):</p>
<table>
<tr><th>Category</th><th style="text-align:right">Count</th><th>Distribution</th></tr>
{cat_rows}
</table>

<p style="font-size:13px;color:#6b7280"><strong>Coding</strong> dominates with {_fmt(categories[0][1])} agents — reflecting the developer-tool origin of the agent ecosystem. <strong>Infrastructure</strong> and <strong>DevOps</strong> follow, showing agents are increasingly used for operational automation.</p>

<h2>4. How they're built — frameworks &amp; languages</h2>

<p><strong>Framework distribution</strong> (agents declaring a framework):</p>
<table>
<tr><th>Framework</th><th style="text-align:right">Count</th><th>Distribution</th></tr>
{fw_rows}
</table>

<p style="font-size:13px;color:#6b7280"><strong>Anthropic</strong> and <strong>OpenAI</strong> SDKs lead, followed by <strong>LangChain</strong> as the dominant orchestration framework. <strong>MCP</strong> (Model Context Protocol) already ranks 4th with {_fmt(d['frameworks'][3][1] if len(d['frameworks']) > 3 else 0)} agents — a strong signal of protocol adoption.</p>

<p style="margin-top:20px"><strong>Language distribution</strong> (known languages only):</p>
<table>
<tr><th>Language</th><th style="text-align:right">Count</th><th>Distribution</th></tr>
{lang_rows}
</table>

<p style="font-size:13px;color:#6b7280"><strong>Python</strong> accounts for {_pct(d['languages'][0][1], sum(c for _, c in d['languages']))} of agents with known languages. <strong>TypeScript</strong> is the clear second at {_pct(d['languages'][1][1], sum(c for _, c in d['languages']))} — driven by MCP server development and npm packages.</p>

<h2>5. Where they come from — source registries</h2>

<table>
<tr><th>Source</th><th style="text-align:right">Count</th><th style="text-align:right">Share</th></tr>
{src_rows}
</table>

<h2>6. Trust &amp; quality</h2>

<p>Every agent and tool receives a <strong>Nerq Trust Score</strong> (0-100) computed from five pillars:</p>
<ul style="font-size:14px;line-height:1.8">
<li><strong>Security</strong> (30%) — known vulnerabilities, dependency audit, code patterns</li>
<li><strong>Maintenance</strong> (25%) — commit recency, release frequency, issue response time</li>
<li><strong>Popularity</strong> (20%) — stars, downloads, forks, community size</li>
<li><strong>Documentation</strong> (15%) — README quality, API docs, examples</li>
<li><strong>Ecosystem</strong> (10%) — protocol support, integrations, interoperability</li>
</ul>

<p><strong>Trust distribution</strong> across {_fmt(total_scored)} scored agents and tools:</p>
{trust_bar}
<table style="margin-top:12px">
<tr><th>Level</th><th>Score</th><th style="text-align:right">Count</th><th style="text-align:right">Share</th></tr>
<tr><td><span class="pill pill-green">HIGH</span></td><td>70-100</td><td class="num-cell">{_fmt(d['trust_high'])}</td><td class="num-cell">{_pct(d['trust_high'], total_scored)}</td></tr>
<tr><td><span class="pill pill-yellow">MEDIUM</span></td><td>40-69</td><td class="num-cell">{_fmt(d['trust_medium'])}</td><td class="num-cell">{_pct(d['trust_medium'], total_scored)}</td></tr>
<tr><td><span class="pill pill-red">LOW</span></td><td>0-39</td><td class="num-cell">{_fmt(d['trust_low'])}</td><td class="num-cell">{_pct(d['trust_low'], total_scored)}</td></tr>
<tr style="font-weight:700"><td>Average</td><td colspan="3" class="num-cell">{d['trust_avg']}/100</td></tr>
</table>

<h2>7. Top 20 most trusted agents</h2>

<table>
<tr><th>#</th><th>Name</th><th>Type</th><th style="text-align:right">Score</th><th>Grade</th><th>Source</th><th style="text-align:right">Stars</th></tr>
{agent_rows}
</table>

<h2>8. Top 20 MCP servers</h2>

<table>
<tr><th>#</th><th>Name</th><th style="text-align:right">Score</th><th>Grade</th><th>Source</th><th style="text-align:right">Stars</th></tr>
{mcp_rows}
</table>

<h2>9. Growth trends</h2>

<table>
<tr><th>Timeframe</th><th style="text-align:right">New assets</th></tr>
<tr><td>Last 7 days</td><td class="num-cell">{_fmt(g7_total)}</td></tr>
<tr><td>Last 30 days</td><td class="num-cell">{_fmt(g30_total)}</td></tr>
</table>

<p style="font-size:13px;color:#6b7280">Note: Nerq's initial bulk index was completed in February 2026. Growth figures reflect <em>newly discovered</em> assets since the initial crawl. The index is continuously updated as new agents are published to npm, PyPI, GitHub, HuggingFace, Docker Hub, and MCP registries.</p>

<h2>10. Methodology</h2>

<p style="font-size:14px">Nerq indexes AI assets from six registries: <strong>GitHub</strong>, <strong>npm</strong>, <strong>PyPI</strong>, <strong>HuggingFace</strong>, <strong>Docker Hub</strong>, and <strong>MCP registries</strong>. Assets are classified by type (agent, tool, MCP server, model, dataset, space) using keyword analysis and metadata inspection.</p>
<p style="font-size:14px">Trust Scores are computed using a weighted composite of security, maintenance, popularity, documentation, and ecosystem signals. Scores are updated on a rolling basis as new data becomes available.</p>
<p style="font-size:14px">All data is available via the <a href="/nerq/docs">Nerq API</a> and can be queried programmatically.</p>

<h2>Related reports</h2>
<ul style="font-size:14px;line-height:2">
<li><a href="/report/best-coding-agents-2026">Best AI Coding Agents 2026</a></li>
<li><a href="/report/best-communication-agents-2026">Best AI Customer Service &amp; Communication Agents 2026</a></li>
<li><a href="/report/best-devops-agents-2026">Best AI DevOps Agents 2026</a></li>
<li><a href="/report/best-content-agents-2026">Best AI Content Creation Agents 2026</a></li>
<li><a href="/report/best-security-agents-2026">Best AI Security Agents 2026</a></li>
</ul>

<h2>12. About Nerq</h2>

<p style="font-size:14px"><strong>Nerq</strong> is the AI asset search engine — the largest open index of AI agents, tools, and MCP servers. Built for the agentic economy, Nerq provides trust scoring, compliance classification, and discovery APIs that help developers and organizations find, evaluate, and integrate AI assets safely.</p>
<ul style="font-size:14px;line-height:1.8">
<li><a href="/">nerq.ai</a> — search the index</li>
<li><a href="/nerq/docs">API documentation</a></li>
<li><a href="/kya">KYA — Know Your Agent</a> — due diligence reports</li>
<li><a href="/stats">Live statistics</a></li>
<li><a href="/mcp-servers">MCP server directory</a></li>
</ul>

<div style="font-size:12px;color:#6b7280;margin-top:32px;padding-top:16px;border-top:1px solid #e5e7eb">
Data sourced from nerq.ai on {generated}. Live data: <a href="/v1/agent/stats">nerq.ai/v1/agent/stats</a>
</div>

</main>
{NERQ_FOOTER}
</body>
</html>"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if s else ""


@router_report.get("/report/q1-2026", response_class=HTMLResponse)
def report_q1_2026():
    now = _time.time()
    if _report_cache["html"] and (now - _report_cache["ts"]) < _REPORT_TTL:
        return HTMLResponse(_report_cache["html"])

    d = _query_report_data()
    html = _build_report_html(d)
    _report_cache["html"] = html
    _report_cache["ts"] = now
    return HTMLResponse(html)


@router_report.get("/reports", response_class=HTMLResponse)
def reports_index():
    """Index page listing all published reports."""
    from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

    reports = [
        ("/report/q1-2026", "State of AI Assets — Q1 2026",
         "The first comprehensive census of the AI agent ecosystem. 5M+ assets, 204K agents & tools, all trust scored."),
        ("/report/best-coding-agents-2026", "Best AI Coding Agents 2026",
         "Top 15 coding agents ranked by trust score — from code assistants to autonomous debugging."),
        ("/report/best-devops-agents-2026", "Best AI DevOps Agents 2026",
         "Top 15 DevOps and infrastructure agents ranked by trust score."),
        ("/report/best-security-agents-2026", "Best AI Security Agents 2026",
         "Top 15 security agents ranked by trust score — pentesting, SOC automation, vulnerability scanning."),
        ("/report/best-communication-agents-2026", "Best AI Customer Service & Communication Agents 2026",
         "Top 15 communication agents ranked by trust score — voice agents, chatbots, email automation."),
        ("/report/best-content-agents-2026", "Best AI Content Creation Agents 2026",
         "Top 15 content and marketing agents ranked by trust score."),
        ("/report/framework-comparison-2026", "AI Agent Frameworks Compared — 2026",
         "Data-driven comparison of 11 major AI agent frameworks: agent counts, trust scores, growth rates."),
        ("/report/benchmark", "With Nerq vs Without Nerq — Benchmark",
         "Quantified: how preflight trust checks reduce failure rates and improve agent tool selection quality."),
    ]

    rows = ""
    for url, title, desc in reports:
        rows += f"""<div style="border-bottom:1px solid #e5e7eb;padding:16px 0">
<a href="{url}" style="font-size:15px;font-weight:600">{title}</a>
<p style="font-size:14px;color:#6b7280;margin-top:4px">{desc}</p>
</div>\n"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reports | Nerq</title>
<meta name="description" content="Research and analysis from the world's largest AI agent index. Trust rankings, ecosystem census, and category deep-dives.">
<link rel="canonical" href="https://nerq.ai/reports">
<meta name="robots" content="index, follow">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"CollectionPage","name":"Nerq Reports","description":"Research and analysis from the world's largest AI agent index.","url":"https://nerq.ai/reports","publisher":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}},"numberOfItems":{len(reports)}}}
</script>
<style>{NERQ_CSS}</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px;max-width:800px">
<h1>reports</h1>
<p class="desc">Research and analysis from the Nerq AI agent index</p>
{rows}
<p style="font-size:13px;color:#6b7280;margin-top:24px">All reports use live data from the Nerq index and update hourly. <a href="/nerq/docs">API docs</a> &middot; <a href="/v1/agent/stats">live stats</a></p>
</main>
{NERQ_FOOTER}
</body>
</html>"""
    return HTMLResponse(html)
