"""
AI Agent Frameworks Compared — 2026
Route: /report/framework-comparison-2026
Live DB queries, cached 1 hour.
"""

import logging
import time as _time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.report.frameworks")

router_frameworks = APIRouter(tags=["report"])

_fw_cache: dict = {"html": None, "md": None, "ts": 0}
_FW_TTL = 3600

# Frameworks to compare
FRAMEWORKS = [
    "langchain", "openai", "anthropic", "mcp", "ollama",
    "huggingface", "autogen", "crewai", "llamaindex", "a2a",
    "semantic-kernel",
]

# Display names
_FW_DISPLAY = {
    "langchain": "LangChain",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "mcp": "MCP",
    "ollama": "Ollama",
    "huggingface": "HuggingFace",
    "autogen": "AutoGen",
    "crewai": "CrewAI",
    "llamaindex": "LlamaIndex",
    "a2a": "A2A",
    "semantic-kernel": "Semantic Kernel",
}


def _query_frameworks() -> list[dict]:
    """Query framework comparison data from PostgreSQL — 2 queries instead of 44."""
    session = get_session()
    try:
        # Query 1: counts, avg trust, new-this-month, top language per framework
        fw_params = {f"fw{i}": fw for i, fw in enumerate(FRAMEWORKS)}
        fw_array = ", ".join(f":{k}" for k in fw_params)
        main_rows = session.execute(text(f"""
            WITH fw_list AS (
                SELECT unnest(ARRAY[{fw_array}]::varchar[]) AS fw
            ),
            fw_agents AS (
                SELECT fl.fw, a.name, a.trust_score_v2, a.language, a.first_indexed
                FROM fw_list fl
                JOIN agents a ON a.frameworks @> ARRAY[fl.fw]::varchar[]
                    AND a.is_active = true
                    AND a.agent_type IN ('agent', 'mcp_server', 'tool')
            ),
            stats AS (
                SELECT fw,
                       COUNT(*) AS cnt,
                       AVG(trust_score_v2) AS avg_trust,
                       COUNT(*) FILTER (WHERE first_indexed >= NOW() - INTERVAL '30 days') AS new_month
                FROM fw_agents GROUP BY fw
            ),
            top_lang AS (
                SELECT DISTINCT ON (fw) fw, language
                FROM (
                    SELECT fw, language, COUNT(*) AS lc
                    FROM fw_agents
                    WHERE language IS NOT NULL AND language != ''
                    GROUP BY fw, language
                ) sub ORDER BY fw, lc DESC
            )
            SELECT s.fw, s.cnt, ROUND(s.avg_trust::numeric, 1) AS avg_trust, s.new_month,
                   COALESCE(tl.language, '—') AS primary_language
            FROM stats s
            LEFT JOIN top_lang tl ON s.fw = tl.fw
        """), fw_params).fetchall()

        stats_map = {}
        for row in main_rows:
            stats_map[row[0]] = {
                "count": row[1] or 0,
                "avg_trust": float(row[2]) if row[2] else 0,
                "new_month": row[3] or 0,
                "primary_language": row[4] or "—",
            }

        # Query 2: top agent per framework
        top_rows = session.execute(text(f"""
            WITH fw_list AS (
                SELECT unnest(ARRAY[{fw_array}]::varchar[]) AS fw
            )
            SELECT DISTINCT ON (fl.fw) fl.fw, a.name, ROUND(a.trust_score_v2::numeric, 1)
            FROM fw_list fl
            JOIN agents a ON a.frameworks @> ARRAY[fl.fw]::varchar[]
                AND a.is_active = true
                AND a.agent_type IN ('agent', 'mcp_server', 'tool')
                AND a.trust_score_v2 IS NOT NULL
            ORDER BY fl.fw, a.trust_score_v2 DESC
        """), fw_params).fetchall()

        top_map = {row[0]: (row[1], float(row[2]) if row[2] else 0) for row in top_rows}

        results = []
        for fw in FRAMEWORKS:
            s = stats_map.get(fw, {"count": 0, "avg_trust": 0, "new_month": 0, "primary_language": "—"})
            top = top_map.get(fw, ("—", 0))
            results.append({
                "framework": fw,
                "display_name": _FW_DISPLAY.get(fw, fw),
                "agent_count": s["count"],
                "avg_trust_score": s["avg_trust"],
                "top_agent": top[0],
                "top_agent_score": top[1],
                "primary_language": s["primary_language"],
                "new_this_month": s["new_month"],
            })

        results.sort(key=lambda x: x["agent_count"], reverse=True)
        return results
    finally:
        session.close()


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if s else ""


@router_frameworks.get("/report/framework-comparison-2026", response_class=HTMLResponse)
def framework_comparison():
    """AI Agent Frameworks Compared — 2026."""
    now = _time.time()
    if _fw_cache["html"] and (now - _fw_cache["ts"]) < _FW_TTL:
        return HTMLResponse(_fw_cache["html"])

    data = _query_frameworks()
    html = _build_html(data)
    _fw_cache["html"] = html
    _fw_cache["ts"] = now
    return HTMLResponse(html)


def _build_html(data: list[dict]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_agents = sum(d["agent_count"] for d in data)

    # Main comparison table
    rows = ""
    for i, d in enumerate(data, 1):
        trust_color = "#22c55e" if d["avg_trust_score"] >= 65 else "#eab308" if d["avg_trust_score"] >= 50 else "#ef4444"
        rows += f"""<tr>
<td style="font-weight:600">{d['display_name']}</td>
<td class="num-cell">{d['agent_count']:,}</td>
<td style="color:{trust_color};font-weight:600">{d['avg_trust_score']}</td>
<td><a href="/kya/{_esc(d['top_agent'])}">{_esc(d['top_agent'][:30])}</a> <span style="font-size:12px;color:#6b7280">({d['top_agent_score']})</span></td>
<td>{_esc(d['primary_language'])}</td>
<td class="num-cell">{d['new_this_month']:,}</td>
</tr>"""

    # Bar chart — agent count
    max_count = max(d["agent_count"] for d in data) if data else 1
    bar_rows = ""
    for d in data:
        pct = (d["agent_count"] / max_count * 100) if max_count else 0
        bar_rows += f"""<div style="display:flex;align-items:center;gap:8px;margin:6px 0">
<span style="width:120px;font-size:13px;font-weight:500">{d['display_name']}</span>
<div style="flex:1;height:20px;background:#f5f5f5;overflow:hidden">
<div style="width:{pct:.0f}%;height:100%;background:#0d9488"></div>
</div>
<span style="width:60px;font-size:13px;text-align:right;font-family:ui-monospace,'SF Mono',monospace">{d['agent_count']:,}</span>
</div>"""

    # Bar chart — avg trust
    trust_bars = ""
    for d in sorted(data, key=lambda x: x["avg_trust_score"], reverse=True):
        color = "#22c55e" if d["avg_trust_score"] >= 65 else "#eab308" if d["avg_trust_score"] >= 50 else "#ef4444"
        trust_bars += f"""<div style="display:flex;align-items:center;gap:8px;margin:6px 0">
<span style="width:120px;font-size:13px;font-weight:500">{d['display_name']}</span>
<div style="flex:1;height:20px;background:#f5f5f5;overflow:hidden">
<div style="width:{d['avg_trust_score']:.0f}%;height:100%;background:{color}"></div>
</div>
<span style="width:40px;font-size:13px;text-align:right;font-family:ui-monospace,'SF Mono',monospace">{d['avg_trust_score']:.0f}</span>
</div>"""

    # ItemList JSON-LD
    items_json = ",".join(
        f'{{"@type":"ListItem","position":{i},"item":{{"@type":"SoftwareApplication","name":"{d["display_name"]}","applicationCategory":"AI Framework"}}}}'
        for i, d in enumerate(data, 1)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Agent Frameworks Compared — 2026 | Nerq</title>
<meta name="description" content="Data-driven comparison of {len(data)} AI agent frameworks: LangChain, OpenAI, Anthropic, MCP, CrewAI, and more. Agent counts, trust scores, growth rates.">
<link rel="canonical" href="https://nerq.ai/report/framework-comparison-2026">
<meta name="robots" content="index, follow">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Article","headline":"AI Agent Frameworks Compared — 2026","datePublished":"{today}","dateModified":"{today}","author":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}},"publisher":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}}}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"ItemList","name":"AI Agent Frameworks 2026","numberOfItems":{len(data)},"itemListElement":[{items_json}]}}
</script>
<style>{NERQ_CSS}
.num-cell{{font-family:ui-monospace,'SF Mono',monospace;text-align:right}}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px;max-width:900px">

<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/reports">reports</a> &rsaquo; framework comparison</div>

<h1>AI agent frameworks compared — 2026</h1>
<p class="desc">Data-driven comparison of {len(data)} major AI agent frameworks from the Nerq index of 5M+ assets. Published {today}.</p>

<div style="display:flex;gap:24px;flex-wrap:wrap;margin:20px 0">
<div class="card" style="flex:1;min-width:140px;text-align:center">
<div style="font-family:ui-monospace,'SF Mono',monospace;font-size:1.4rem;font-weight:700">{len(data)}</div>
<div style="font-size:12px;color:#6b7280">frameworks compared</div>
</div>
<div class="card" style="flex:1;min-width:140px;text-align:center">
<div style="font-family:ui-monospace,'SF Mono',monospace;font-size:1.4rem;font-weight:700">{total_agents:,}</div>
<div style="font-size:12px;color:#6b7280">total agents using these</div>
</div>
<div class="card" style="flex:1;min-width:140px;text-align:center">
<div style="font-family:ui-monospace,'SF Mono',monospace;font-size:1.4rem;font-weight:700">{data[0]['display_name'] if data else '—'}</div>
<div style="font-size:12px;color:#6b7280">most adopted</div>
</div>
</div>

<h2>comparison table</h2>
<table>
<thead><tr><th>framework</th><th style="text-align:right">agents</th><th>avg trust</th><th>top agent</th><th>language</th><th style="text-align:right">new (30d)</th></tr></thead>
<tbody>{rows}</tbody>
</table>

<h2>adoption — agent count</h2>
<p class="desc">Number of agents in the Nerq index using each framework</p>
{bar_rows}

<h2>average trust score</h2>
<p class="desc">Mean trust score of agents using each framework (0-100)</p>
{trust_bars}

<h2>methodology</h2>
<p style="font-size:14px;color:#6b7280;line-height:1.7">
Framework association is determined from the <code>frameworks</code> array in the Nerq agent database.
An agent is counted under a framework if that framework appears in its declared dependencies, metadata, or detected integrations.
Trust scores are the Nerq Trust Score v2 — a composite of security practices, compliance, maintenance activity, community trust, and ecosystem compatibility.
Data updates hourly from the live index.
</p>

<h2>related</h2>
<p style="font-size:14px">
<a href="/report/q1-2026">State of AI Assets Q1 2026</a> &middot;
<a href="/report/best-coding-agents-2026">Best Coding Agents</a> &middot;
<a href="/v1/agent/benchmark/categories">Benchmark API</a> &middot;
<a href="/weekly">Weekly Signal</a>
</p>

<p style="font-size:13px;color:#6b7280;margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb">
Data from the Nerq index. JSON: <a href="/v1/agent/stats">/v1/agent/stats</a> &middot;
<a href="/nerq/docs">API docs</a> &middot; <a href="/reports">all reports</a>
</p>

</main>
{NERQ_FOOTER}
</body>
</html>"""
