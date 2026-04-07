"""
Nerq Weekly Signal — AI Agent Ecosystem Update
Routes: /v1/agent/weekly (JSON), /weekly (HTML page)
Live DB queries, cached 1 hour.
"""

import logging
import time as _time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.weekly")

router_weekly = APIRouter(tags=["weekly"])

_weekly_cache: dict = {"data": None, "html": None, "ts": 0}
_WEEKLY_TTL = 3600


def _query_weekly() -> dict:
    """Query all weekly signal data from PostgreSQL."""
    session = get_session()
    try:
        # New assets indexed this week (all types, including unclassified)
        total_new = session.execute(text("""
            SELECT COUNT(*) FROM entity_lookup
            WHERE is_active = true
            AND first_indexed >= NOW() - INTERVAL '7 days'
        """)).scalar() or 0

        # Breakdown by type (may be 0 if new entries are unclassified)
        type_breakdown = session.execute(text("""
            SELECT COALESCE(agent_type, 'unclassified') as atype, COUNT(*)
            FROM entity_lookup
            WHERE is_active = true
            AND first_indexed >= NOW() - INTERVAL '7 days'
            GROUP BY atype ORDER BY COUNT(*) DESC
        """)).fetchall()
        type_map = {r[0]: r[1] for r in type_breakdown}

        new_agents = type_map.get("agent", 0)
        new_tools = type_map.get("tool", 0)
        new_mcp = type_map.get("mcp_server", 0)

        # Active this week — recently crawled/updated agents (last_crawled not in entity_lookup)
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        active_this_week = session.execute(text("""
            SELECT COUNT(*) FROM agents
            WHERE is_active = true AND last_crawled >= NOW() - INTERVAL '7 days'
            AND agent_type IN ('agent', 'mcp_server', 'tool')
        """)).scalar() or 0

        # Agent of the week — highest trust among classified agents
        # Prefer recently indexed, but fall back to highest trust overall
        aotw_row = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, agent_type, stars, source_url, category
            FROM entity_lookup
            WHERE is_active = true AND trust_score_v2 IS NOT NULL
            AND agent_type IN ('agent', 'mcp_server', 'tool')
            ORDER BY trust_score_v2 DESC
            LIMIT 1
        """)).fetchone()

        agent_of_week = None
        if aotw_row:
            agent_of_week = {
                "name": aotw_row[0], "trust_score": float(aotw_row[1]),
                "grade": aotw_row[2], "type": aotw_row[3], "stars": aotw_row[4],
                "source_url": aotw_row[5], "category": aotw_row[6],
            }

        # Top 10 agents — highest trust scores in the index
        top_agents = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, agent_type, stars, source_url, category
            FROM entity_lookup
            WHERE is_active = true AND trust_score_v2 IS NOT NULL
            AND agent_type IN ('agent', 'mcp_server', 'tool')
            ORDER BY trust_score_v2 DESC
            LIMIT 10
        """)).fetchall()

        top_list = [
            {"name": r[0], "trust_score": float(r[1]), "grade": r[2],
             "type": r[3], "stars": r[4], "source_url": r[5], "category": r[6]}
            for r in top_agents
        ]

        # Trust changes — agents whose v2 score differs from v1 by >5 points
        trust_changes = session.execute(text("""
            SELECT name, trust_score_v2, trust_score, trust_grade, agent_type,
                   (trust_score_v2 - trust_score) as delta
            FROM entity_lookup
            WHERE is_active = true
            AND trust_score_v2 IS NOT NULL AND trust_score IS NOT NULL
            AND ABS(trust_score_v2 - trust_score) > 5
            AND agent_type IN ('agent', 'mcp_server', 'tool')
            ORDER BY ABS(trust_score_v2 - trust_score) DESC
            LIMIT 10
        """)).fetchall()

        changes_list = [
            {"name": r[0], "current_score": float(r[1]), "previous_score": float(r[2]),
             "grade": r[3], "type": r[4], "delta": round(float(r[5]), 1)}
            for r in trust_changes
        ]

        # Trending frameworks — by total adoption
        fw_all = session.execute(text("""
            SELECT unnest(frameworks) as fw, COUNT(*) as cnt
            FROM entity_lookup
            WHERE is_active = true AND frameworks IS NOT NULL
            AND agent_type IN ('agent', 'mcp_server', 'tool')
            GROUP BY fw
            ORDER BY cnt DESC
            LIMIT 10
        """)).fetchall()

        frameworks_list = [
            {"framework": r[0], "total": r[1]}
            for r in fw_all
        ]

        # Top categories by agent count
        cat_top = session.execute(text("""
            SELECT category, COUNT(*) as cnt
            FROM entity_lookup
            WHERE is_active = true
            AND category IS NOT NULL AND category != ''
            AND agent_type IN ('agent', 'mcp_server', 'tool')
            GROUP BY category
            ORDER BY cnt DESC
            LIMIT 10
        """)).fetchall()

        categories_list = [
            {"category": r[0], "count": r[1]}
            for r in cat_top
        ]

        # Ecosystem totals
        totals = session.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE agent_type = 'agent') as agents,
                COUNT(*) FILTER (WHERE agent_type = 'tool') as tools,
                COUNT(*) FILTER (WHERE agent_type = 'mcp_server') as mcp,
                COUNT(*) as total,
                ROUND(AVG(trust_score_v2)::numeric, 1) as avg_trust
            FROM entity_lookup WHERE is_active = true
            AND agent_type IN ('agent', 'mcp_server', 'tool')
        """)).fetchone()

        return {
            "week_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "new_indexed_count": total_new,
            "new_agents_count": new_agents,
            "new_tools_count": new_tools,
            "new_mcp_count": new_mcp,
            "active_this_week": active_this_week,
            "ecosystem": {
                "total_agents": totals[0] if totals else 0,
                "total_tools": totals[1] if totals else 0,
                "total_mcp": totals[2] if totals else 0,
                "total_classified": totals[3] if totals else 0,
                "avg_trust_score": float(totals[4]) if totals and totals[4] else 0,
            },
            "top_agents": top_list,
            "agent_of_the_week": agent_of_week,
            "trust_changes": changes_list,
            "trending_frameworks": frameworks_list,
            "top_categories": categories_list,
        }
    finally:
        session.close()


@router_weekly.get("/v1/agent/weekly")
def weekly_signal_api():
    """Weekly AI agent ecosystem signal — JSON."""
    now = _time.time()
    if _weekly_cache["data"] and (now - _weekly_cache["ts"]) < _WEEKLY_TTL:
        return _weekly_cache["data"]
    data = _query_weekly()
    _weekly_cache["data"] = data
    _weekly_cache["ts"] = now
    return data


@router_weekly.get("/weekly", response_class=HTMLResponse)
def weekly_signal_page():
    """Weekly signal HTML page."""
    now = _time.time()
    if _weekly_cache["html"] and (now - _weekly_cache["ts"]) < _WEEKLY_TTL:
        return HTMLResponse(_weekly_cache["html"])
    data = _query_weekly()
    html = _build_weekly_html(data)
    _weekly_cache["data"] = data
    _weekly_cache["html"] = html
    _weekly_cache["ts"] = now
    return HTMLResponse(html)


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if s else ""


def _build_weekly_html(d: dict) -> str:
    week = d["week_of"]
    eco = d.get("ecosystem", {})
    new_indexed = d["new_indexed_count"]

    # Top agents table
    top_rows = ""
    for i, a in enumerate(d.get("top_agents", []), 1):
        name = _esc(a["name"])
        grade_class = "pill-green" if (a.get("grade") or "").startswith("A") else "pill-yellow" if (a.get("grade") or "").startswith(("B", "C")) else "pill-gray"
        top_rows += f"""<tr>
<td>{i}</td>
<td><a href="/kya/{_esc(name)}">{name}</a></td>
<td>{(a.get('type') or '').replace('_', ' ')}</td>
<td>{a['trust_score']:.1f}</td>
<td><span class="pill {grade_class}">{a.get('grade') or '—'}</span></td>
<td>{a.get('stars') or 0:,}</td>
<td>{_esc(a.get('category') or '—')}</td>
</tr>"""

    # Agent of the week
    aotw_html = ""
    aotw = d.get("agent_of_the_week")
    if aotw:
        aotw_html = f"""<div class="card" style="border-left:4px solid #0d9488">
<h3 style="margin-bottom:8px">agent of the week</h3>
<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
<div>
<a href="/kya/{_esc(aotw['name'])}" style="font-size:18px;font-weight:700">{_esc(aotw['name'])}</a>
<span class="pill pill-green" style="margin-left:8px">{aotw.get('grade') or '?'}</span>
</div>
<div style="font-size:14px;color:#6b7280">
Trust Score: <strong>{aotw['trust_score']:.1f}/100</strong> &middot;
{(aotw.get('type') or '').replace('_', ' ')} &middot;
{aotw.get('stars') or 0:,} stars
</div>
</div>
<p style="font-size:13px;color:#6b7280;margin-top:8px">Highest trust score in the Nerq index.</p>
</div>"""

    # Trust changes
    changes_rows = ""
    for c in d.get("trust_changes", []):
        delta = c["delta"]
        arrow = "&#x25b2;" if delta > 0 else "&#x25bc;"
        color = "#22c55e" if delta > 0 else "#ef4444"
        changes_rows += f"""<tr>
<td><a href="/kya/{_esc(c['name'])}">{_esc(c['name'])}</a></td>
<td>{(c.get('type') or '').replace('_', ' ')}</td>
<td>{c['current_score']:.1f}</td>
<td>{c['previous_score']:.1f}</td>
<td style="color:{color};font-weight:600">{arrow} {delta:+.1f}</td>
</tr>"""

    # Frameworks
    fw_rows = ""
    for f in d.get("trending_frameworks", []):
        fw_rows += f"""<tr>
<td>{_esc(f['framework'])}</td>
<td>{f['total']:,}</td>
</tr>"""

    # Categories
    cat_rows = ""
    for c in d.get("top_categories", []):
        cat_rows += f"""<tr>
<td>{_esc(c['category'])}</td>
<td>{c['count']:,}</td>
</tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Nerq Weekly — AI Agent Ecosystem Update | {week}</title>
<meta name="description" content="Weekly AI agent ecosystem update: {eco.get('total_classified',0):,} agents indexed, top trust scores, framework adoption, category breakdown.">
<link rel="canonical" href="https://nerq.ai/weekly">
<meta name="robots" content="index, follow">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Article","headline":"The Nerq Weekly — AI Agent Ecosystem Update","datePublished":"{week}","dateModified":"{week}","author":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}},"publisher":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}},"description":"AI agent ecosystem snapshot: {eco.get('total_classified',0):,} agents indexed with average trust score of {eco.get('avg_trust_score',0)}."}}
</script>
<style>{NERQ_CSS}</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px;max-width:860px">

<h1>the nerq weekly</h1>
<p class="desc">AI agent ecosystem snapshot &mdash; {week}</p>

<div style="display:flex;gap:16px;flex-wrap:wrap;margin:20px 0">
<div class="card" style="flex:1;min-width:130px;text-align:center">
<div style="font-family:ui-monospace,'SF Mono',monospace;font-size:1.4rem;font-weight:700;color:#0d9488">{eco.get('total_classified',0):,}</div>
<div style="font-size:12px;color:#6b7280">agents &amp; tools indexed</div>
</div>
<div class="card" style="flex:1;min-width:130px;text-align:center">
<div style="font-family:ui-monospace,'SF Mono',monospace;font-size:1.4rem;font-weight:700">{eco.get('total_agents',0):,}</div>
<div style="font-size:12px;color:#6b7280">agents</div>
</div>
<div class="card" style="flex:1;min-width:130px;text-align:center">
<div style="font-family:ui-monospace,'SF Mono',monospace;font-size:1.4rem;font-weight:700">{eco.get('total_tools',0):,}</div>
<div style="font-size:12px;color:#6b7280">tools</div>
</div>
<div class="card" style="flex:1;min-width:130px;text-align:center">
<div style="font-family:ui-monospace,'SF Mono',monospace;font-size:1.4rem;font-weight:700">{eco.get('total_mcp',0):,}</div>
<div style="font-size:12px;color:#6b7280">MCP servers</div>
</div>
<div class="card" style="flex:1;min-width:130px;text-align:center">
<div style="font-family:ui-monospace,'SF Mono',monospace;font-size:1.4rem;font-weight:700">{eco.get('avg_trust_score',0)}</div>
<div style="font-size:12px;color:#6b7280">avg trust score</div>
</div>
</div>

<div style="display:flex;gap:16px;flex-wrap:wrap;margin:0 0 20px">
<div style="font-size:14px;color:#6b7280">
<strong>{new_indexed:,}</strong> new assets indexed this week &middot;
<strong>{d.get('active_this_week', 0):,}</strong> agents active (crawled in 7d)
</div>
</div>

{aotw_html}

<h2>top agents by trust score</h2>
<p class="desc">Highest trust scores in the Nerq index</p>
<table>
<thead><tr><th>#</th><th>name</th><th>type</th><th>score</th><th>grade</th><th>stars</th><th>category</th></tr></thead>
<tbody>{top_rows if top_rows else '<tr><td colspan="7" style="color:#6b7280;text-align:center">No data</td></tr>'}</tbody>
</table>

<h2>trust score changes</h2>
<p class="desc">Agents with the largest gap between Trust Score v1 and v2</p>
<table>
<thead><tr><th>name</th><th>type</th><th>v2 score</th><th>v1 score</th><th>delta</th></tr></thead>
<tbody>{changes_rows if changes_rows else '<tr><td colspan="5" style="color:#6b7280;text-align:center">No significant changes</td></tr>'}</tbody>
</table>

<h2>framework adoption</h2>
<p class="desc">Most popular frameworks by agent count</p>
<table>
<thead><tr><th>framework</th><th>agents</th></tr></thead>
<tbody>{fw_rows if fw_rows else '<tr><td colspan="2" style="color:#6b7280;text-align:center">No framework data</td></tr>'}</tbody>
</table>

<h2>top categories</h2>
<p class="desc">Largest agent categories in the index</p>
<table>
<thead><tr><th>category</th><th>agents</th></tr></thead>
<tbody>{cat_rows if cat_rows else '<tr><td colspan="2" style="color:#6b7280;text-align:center">No category data</td></tr>'}</tbody>
</table>

<p style="font-size:13px;color:#6b7280;margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb">
Data from the <a href="/v1/agent/stats">Nerq index</a>. Updated hourly. JSON: <a href="/v1/agent/weekly">/v1/agent/weekly</a> &middot;
<a href="/reports">reports</a> &middot; <a href="/badges">badges</a> &middot; <a href="/nerq/docs">api</a>
</p>

</main>
{NERQ_FOOTER}
</body>
</html>"""
