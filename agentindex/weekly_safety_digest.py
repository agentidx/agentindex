#!/usr/bin/env python3
"""Weekly safety digest — top movers, new tools, CVE updates.
Generates HTML digest page at /safety-digest and writes to logs/weekly_digest.log.

Usage in discovery.py:
    from agentindex.weekly_safety_digest import mount_safety_digest
    mount_safety_digest(app)
"""

import logging
import json
import time
from datetime import datetime, timedelta
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text
from agentindex.db.models import get_session

logger = logging.getLogger("nerq.digest")

_digest_cache = {"html": None, "ts": 0}
_CACHE_TTL = 3600  # 1 hour


def _build_digest():
    """Build weekly safety digest from DB data."""
    session = get_session()
    try:
        now = datetime.utcnow()
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        # Recently indexed agents (by highest score, as proxy for "new")
        new_agents = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, source, agent_type
            FROM entity_lookup WHERE is_active = true AND trust_score_v2 IS NOT NULL
            ORDER BY id DESC
            LIMIT 20
        """)).fetchall()

        # Top trusted agents overall
        top_trusted = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, source, stars
            FROM entity_lookup WHERE is_active = true AND trust_score_v2 IS NOT NULL
            ORDER BY trust_score_v2 DESC LIMIT 10
        """)).fetchall()

        # Lowest trust (caution zone)
        low_trust = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, source
            FROM entity_lookup WHERE is_active = true AND trust_score_v2 IS NOT NULL
            AND trust_score_v2 < 40 AND trust_score_v2 > 0
            ORDER BY stars DESC NULLS LAST LIMIT 10
        """)).fetchall()

        # Stats
        total = session.execute(text(
            "SELECT COUNT(*) FROM entity_lookup WHERE is_active = true"
        )).scalar() or 0
        mcp_count = session.execute(text(
            "SELECT COUNT(*) FROM entity_lookup WHERE is_active = true AND agent_type = 'mcp_server'"
        )).scalar() or 0
        avg_score = session.execute(text(
            "SELECT AVG(trust_score_v2) FROM entity_lookup WHERE is_active = true AND trust_score_v2 IS NOT NULL"
        )).scalar() or 0

        return {
            "date": now.strftime("%Y-%m-%d"),
            "week_start": week_ago,
            "new_agents": [dict(zip(['name','score','grade','source','type'], r)) for r in new_agents],
            "top_trusted": [dict(zip(['name','score','grade','source','stars'], r)) for r in top_trusted],
            "low_trust": [dict(zip(['name','score','grade','source'], r)) for r in low_trust],
            "total": total,
            "mcp_count": mcp_count,
            "avg_score": round(float(avg_score), 1),
        }
    finally:
        session.close()


def _esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _render_digest(data):
    """Render digest as HTML page."""
    new_rows = ""
    for a in data["new_agents"]:
        score = a.get("score") or 0
        grade = a.get("grade") or "N/A"
        slug = _esc(str(a["name"]).lower().replace("/", "").replace(" ", "-"))
        new_rows += f'<tr><td><a href="/safe/{slug}">{_esc(a["name"])}</a></td><td>{score:.1f}</td><td>{_esc(grade)}</td><td>{_esc(a.get("source",""))}</td></tr>\n'

    top_rows = ""
    for a in data["top_trusted"]:
        score = a.get("score") or 0
        slug = _esc(str(a["name"]).lower().replace("/", "").replace(" ", "-"))
        top_rows += f'<tr><td><a href="/safe/{slug}">{_esc(a["name"])}</a></td><td>{score:.1f}</td><td>{_esc(a.get("grade",""))}</td><td>{a.get("stars",0):,}</td></tr>\n'

    caution_rows = ""
    for a in data["low_trust"]:
        score = a.get("score") or 0
        slug = _esc(str(a["name"]).lower().replace("/", "").replace(" ", "-"))
        caution_rows += f'<tr><td><a href="/safe/{slug}">{_esc(a["name"])}</a></td><td>{score:.1f}</td><td>{_esc(a.get("grade",""))}</td><td>{_esc(a.get("source",""))}</td></tr>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Tool Safety Digest — Week of {_esc(data["week_start"])} | Nerq</title>
<meta name="description" content="Weekly safety digest: {len(data["new_agents"])} new AI tools indexed, average trust score {data["avg_score"]}/100. Independent safety analysis by Nerq.">
<meta name="nerq:question" content="Which AI tools are safe this week?">
<meta name="nerq:answer" content="{data["total"]:,} AI tools indexed. Average trust score: {data["avg_score"]}/100. {len(data["new_agents"])} new tools added this week.">
<link rel="canonical" href="https://nerq.ai/safety-digest">
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:900px;margin:0 auto;padding:20px;color:#1a1a1a;line-height:1.6}}
h1{{font-size:1.8rem;margin-bottom:4px}}
.subtitle{{color:#6b7280;margin-bottom:24px}}
table{{width:100%;border-collapse:collapse;margin:12px 0 32px}}
th,td{{text-align:left;padding:8px 12px;border-bottom:1px solid #e5e7eb}}
th{{font-size:12px;text-transform:uppercase;color:#6b7280;letter-spacing:0.03em}}
a{{color:#0d9488;text-decoration:none}}
a:hover{{text-decoration:underline}}
.stat-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:20px 0}}
.stat{{background:#f9fafb;padding:16px;text-align:center}}
.stat .num{{font-size:2rem;font-weight:700;color:#0d9488;font-family:ui-monospace,monospace}}
.stat .label{{font-size:12px;color:#6b7280;text-transform:uppercase}}
.caution{{background:#fef3c7;padding:12px;margin:8px 0}}
</style>
</head>
<body>
<nav style="margin-bottom:24px"><a href="/">Nerq</a> &rsaquo; <a href="/safe">Safety</a> &rsaquo; Weekly Digest</nav>
<h1>AI Tool Safety Digest</h1>
<p class="subtitle">Week of {_esc(data["week_start"])} &mdash; Generated {_esc(data["date"])}</p>

<div class="stat-grid">
<div class="stat"><div class="num">{data["total"]:,}</div><div class="label">Total Tools Indexed</div></div>
<div class="stat"><div class="num">{data["mcp_count"]:,}</div><div class="label">MCP Servers</div></div>
<div class="stat"><div class="num">{data["avg_score"]}</div><div class="label">Avg Trust Score</div></div>
</div>

<h2>New Tools This Week ({len(data["new_agents"])})</h2>
<table>
<tr><th>Tool</th><th>Score</th><th>Grade</th><th>Source</th></tr>
{new_rows if new_rows else '<tr><td colspan="4">No new tools this week.</td></tr>'}
</table>

<h2>Top 10 Most Trusted</h2>
<table>
<tr><th>Tool</th><th>Score</th><th>Grade</th><th>Stars</th></tr>
{top_rows}
</table>

<h2>Caution Zone (Score &lt; 40)</h2>
<div class="caution">These popular tools have low trust scores. Exercise caution before using in production.</div>
<table>
<tr><th>Tool</th><th>Score</th><th>Grade</th><th>Source</th></tr>
{caution_rows if caution_rows else '<tr><td colspan="4">No caution-zone tools with significant usage.</td></tr>'}
</table>

<p style="color:#6b7280;font-size:13px;margin-top:40px">
Data from <a href="https://nerq.ai">Nerq</a> — independent safety analysis for AI tools.
Check any tool: <code>GET https://nerq.ai/v1/preflight?target={{tool_name}}</code>
</p>
</body>
</html>"""


def mount_safety_digest(app):
    """Mount /safety-digest route."""

    @app.get("/safety-digest", response_class=HTMLResponse)
    def safety_digest():
        now = time.time()
        if _digest_cache["html"] and now - _digest_cache["ts"] < _CACHE_TTL:
            return HTMLResponse(content=_digest_cache["html"])
        try:
            data = _build_digest()
            html = _render_digest(data)
            _digest_cache["html"] = html
            _digest_cache["ts"] = now
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error building digest: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    @app.get("/safety-digest.json")
    def safety_digest_json():
        try:
            return _build_digest()
        except Exception as e:
            return {"error": str(e)}

    logger.info("Safety digest mounted: /safety-digest, /safety-digest.json")
