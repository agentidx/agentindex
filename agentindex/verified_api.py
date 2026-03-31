"""
Nerq Verified — Agents that meet the trust threshold.
Routes: /v1/agent/verified (JSON), /verified (HTML page)
Threshold: trust_score_v2 >= 70
"""

import logging
import time as _time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.verified")

router_verified = APIRouter(tags=["verified"])

_verified_cache: dict = {"data": None, "html": None, "ts": 0}
_VERIFIED_TTL = 3600

VERIFIED_THRESHOLD = 70


def _query_verified() -> list[dict]:
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, agent_type, category, stars, source_url, first_indexed
            FROM agents
            WHERE is_active = true
            AND trust_score_v2 >= :threshold
            AND agent_type IN ('agent', 'mcp_server', 'tool')
            ORDER BY trust_score_v2 DESC
            LIMIT 500
        """), {"threshold": VERIFIED_THRESHOLD}).fetchall()

        return [
            {
                "name": r[0],
                "trust_score": round(float(r[1]), 1),
                "grade": r[2],
                "type": r[3],
                "category": r[4],
                "stars": r[5],
                "source_url": r[6],
                "verified_date": str(r[7])[:10] if r[7] else None,
                "badge_url": f"https://nerq.ai/badge/{r[0]}",
            }
            for r in rows
        ]
    finally:
        session.close()


def _count_verified() -> int:
    session = get_session()
    try:
        return session.execute(text("""
            SELECT COUNT(*) FROM agents
            WHERE is_active = true
            AND trust_score_v2 >= :threshold
            AND agent_type IN ('agent', 'mcp_server', 'tool')
        """), {"threshold": VERIFIED_THRESHOLD}).scalar() or 0
    finally:
        session.close()


@router_verified.get("/v1/agent/verified")
def verified_agents_api():
    """List all Nerq Verified agents (trust >= 70)."""
    now = _time.time()
    if _verified_cache["data"] and (now - _verified_cache["ts"]) < _VERIFIED_TTL:
        return _verified_cache["data"]
    agents = _query_verified()
    count = _count_verified()
    data = {
        "verified_count": count,
        "threshold": VERIFIED_THRESHOLD,
        "agents": agents,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _verified_cache["data"] = data
    _verified_cache["ts"] = now
    return data


@router_verified.get("/verified", response_class=HTMLResponse)
def verified_page():
    """Nerq Verified HTML page."""
    now = _time.time()
    if _verified_cache["html"] and (now - _verified_cache["ts"]) < _VERIFIED_TTL:
        return HTMLResponse(_verified_cache["html"])
    agents = _query_verified()
    count = _count_verified()
    html = _build_verified_html(agents, count)
    _verified_cache["html"] = html
    _verified_cache["ts"] = now
    return HTMLResponse(html)


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if s else ""


def _build_verified_html(agents: list[dict], total_count: int) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Count by type
    type_counts = {}
    for a in agents:
        t = a["type"].replace("_", " ")
        type_counts[t] = type_counts.get(t, 0) + 1

    # Build table rows (top 500)
    rows = ""
    for i, a in enumerate(agents, 1):
        grade_class = "pill-green" if (a["grade"] or "").startswith("A") else "pill-yellow"
        rows += f"""<tr>
<td>{i}</td>
<td><a href="/kya/{_esc(a['name'])}">{_esc(a['name'][:40])}</a></td>
<td>{a['type'].replace('_', ' ')}</td>
<td>{a['trust_score']}</td>
<td><span class="pill {grade_class}">{a['grade'] or '—'}</span></td>
<td>{a.get('stars') or 0:,}</td>
<td>{_esc(a.get('category') or '—')}</td>
</tr>"""

    type_pills = " ".join(
        f'<span class="pill pill-green" style="margin:2px">{t}: {c}</span>'
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1])
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nerq Verified — {total_count:,} Trusted AI Agents | Nerq</title>
<meta name="description" content="{total_count:,} AI agents meet the Nerq Verified threshold (trust score 70+). Browse the most trusted agents, tools, and MCP servers.">
<link rel="canonical" href="https://nerq.ai/verified">
<meta name="robots" content="index, follow">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"CollectionPage","name":"Nerq Verified Agents","description":"{total_count:,} AI agents with trust score >= 70","url":"https://nerq.ai/verified","numberOfItems":{total_count},"publisher":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}}}}
</script>
<style>{NERQ_CSS}
.verified-badge{{display:inline-flex;align-items:center;gap:4px;background:#ecfdf5;color:#065f46;padding:4px 10px;font-size:13px;font-weight:600;border:1px solid #a7f3d0}}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px;max-width:960px">

<h1>nerq verified</h1>
<p class="desc">{total_count:,} agents meet the Nerq trust threshold (score &ge; {VERIFIED_THRESHOLD})</p>

<div style="display:flex;gap:24px;flex-wrap:wrap;margin:20px 0">
<div class="card" style="flex:1;min-width:160px;text-align:center">
<div style="font-family:ui-monospace,'SF Mono',monospace;font-size:1.6rem;font-weight:700;color:#065f46">{total_count:,}</div>
<div style="font-size:12px;color:#6b7280">verified agents</div>
</div>
<div class="card" style="flex:1;min-width:160px;text-align:center">
<div style="font-family:ui-monospace,'SF Mono',monospace;font-size:1.6rem;font-weight:700">{VERIFIED_THRESHOLD}+</div>
<div style="font-size:12px;color:#6b7280">trust score threshold</div>
</div>
</div>

<div style="margin:12px 0">{type_pills}</div>

<h2>what is nerq verified?</h2>
<p style="font-size:14px;color:#6b7280;line-height:1.7;margin-bottom:16px">
Nerq Verified means an AI agent has scored {VERIFIED_THRESHOLD} or above on the Nerq Trust Score &mdash;
a composite metric covering security practices, multi-jurisdiction compliance, maintenance activity,
community trust, and ecosystem compatibility. Verified status updates automatically as scores change.
</p>

<h2>verified agents</h2>
<p class="desc">Top 500 by trust score. JSON: <a href="/v1/agent/verified">/v1/agent/verified</a></p>
<table>
<thead><tr><th>#</th><th>name</th><th>type</th><th>score</th><th>grade</th><th>stars</th><th>category</th></tr></thead>
<tbody>{rows}</tbody>
</table>

<h2>get the badge</h2>
<p style="font-size:14px;color:#6b7280;line-height:1.7">
If your agent is Nerq Verified, add the trust badge to your README:
</p>
<pre>[![Nerq Trust](https://nerq.ai/badge/YOUR_AGENT)](https://nerq.ai/kya/YOUR_AGENT)</pre>
<p style="font-size:13px;color:#6b7280;margin-top:8px"><a href="/badges">Badge showcase &amp; embed formats</a></p>

<p style="font-size:13px;color:#6b7280;margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb">
Updated hourly from the Nerq index. <a href="/nerq/docs">API docs</a> &middot;
<a href="/weekly">weekly signal</a> &middot; <a href="/reports">reports</a>
</p>

</main>
{NERQ_FOOTER}
</body>
</html>"""
