"""
Nerq Reach Dashboard — Internal route showing AI reach per entity.
Mount: from agentindex.reach_dashboard import mount_reach_dashboard
"""

import json
import os
import logging
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.requests import Request

logger = logging.getLogger("nerq.reach")

DASHBOARD_JSON = os.path.expanduser("~/agentindex/data/reach_dashboard.json")
DASHBOARD_KEY = os.environ.get("NERQ_DASHBOARD_KEY", "nerq-reach-2026")

router = APIRouter()


def _load_data():
    """Load latest dashboard data from JSON."""
    try:
        with open(DASHBOARD_JSON) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _render_html(data):
    """Render reach dashboard as dark-themed HTML."""
    s = data["summary"]
    entities = data.get("top_100_entities", [])
    generated = data.get("generated_at", "unknown")[:19]
    hours = data.get("period_hours", 24)

    # AI system breakdown rows
    sys_rows = ""
    for system, count in s.get("by_ai_system", {}).items():
        pct = round(100 * count / max(s["total_citations"], 1), 1)
        bar_w = min(pct * 3, 100)
        sys_rows += (
            f'<tr><td>{system}</td><td style="text-align:right">{count:,}</td>'
            f'<td><div style="background:#1e293b;border-radius:4px;overflow:hidden;height:18px">'
            f'<div style="background:#4fc3f7;height:100%;width:{bar_w}%"></div></div></td>'
            f'<td style="text-align:right">{pct}%</td></tr>'
        )

    # Registry breakdown rows
    reg_rows = ""
    for reg, count in list(s.get("by_registry", {}).items())[:15]:
        reg_rows += f'<tr><td>{reg}</td><td style="text-align:right">{count:,}</td></tr>'

    # Route type rows
    route_rows = ""
    for rt, count in list(s.get("by_route_type", {}).items())[:10]:
        route_rows += f'<tr><td>{rt}</td><td style="text-align:right">{count:,}</td></tr>'

    # Entity table rows
    entity_rows = ""
    for i, e in enumerate(entities[:50], 1):
        sys_str = ", ".join(f'{k}: {v}' for k, v in list(e.get("by_ai_system", {}).items())[:3])
        score = e.get("trust_score", "N/A")
        king = " ♛" if e.get("is_king") else ""
        reg = e.get("registry", "?")
        entity_rows += (
            f'<tr>'
            f'<td>{i}</td>'
            f'<td><a href="/safe/{e["slug"]}" style="color:#4fc3f7;text-decoration:none">'
            f'<strong>{e["name"]}</strong></a>{king}</td>'
            f'<td>{reg}</td>'
            f'<td>{score}</td>'
            f'<td style="text-align:right;font-weight:600">{e["citations_24h"]:,}</td>'
            f'<td style="text-align:right">{e["preflight_calls_24h"]:,}</td>'
            f'<td style="text-align:right;color:#4fc3f7">{e["estimated_human_reach"]:,}</td>'
            f'<td style="font-size:12px;color:#94a3b8">{sys_str}</td>'
            f'</tr>'
        )

    monthly_citations = s["total_citations"] * 30
    monthly_reach = s["total_estimated_reach"] * 30

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Nerq Reach Dashboard</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0f;color:#e2e8f0;line-height:1.6;padding:24px}}
.wrap{{max-width:1400px;margin:0 auto}}
h1{{font-size:28px;color:#4fc3f7;margin-bottom:4px}}
h2{{font-size:18px;color:#81d4fa;margin:32px 0 12px;border-bottom:1px solid #1e293b;padding-bottom:8px}}
.meta{{color:#64748b;font-size:13px;margin-bottom:20px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:20px 0}}
.kpi{{background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:20px;text-align:center}}
.kpi-val{{font-size:2.2em;font-weight:700;color:#4fc3f7;font-family:ui-monospace,monospace}}
.kpi-label{{font-size:12px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
.grid-3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:24px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th{{background:#0f172a;color:#4fc3f7;padding:10px 8px;text-align:left;border-bottom:2px solid #1e293b;position:sticky;top:0;font-size:12px;text-transform:uppercase;letter-spacing:0.5px}}
td{{padding:8px;border-bottom:1px solid #1e293b}}
tr:hover{{background:#0f172a}}
.card{{background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:20px}}
.pitch{{background:linear-gradient(135deg,#0f172a,#1a1a2e);border:1px solid #334155;border-radius:12px;padding:24px;margin:32px 0}}
.pitch p{{color:#94a3b8;font-size:15px;line-height:1.7}}
.pitch strong{{color:#e2e8f0}}
@media(max-width:768px){{.kpi-grid{{grid-template-columns:repeat(2,1fr)}}.grid-2,.grid-3{{grid-template-columns:1fr}}}}
</style></head>
<body>
<div class="wrap">

<h1>Nerq Reach Dashboard</h1>
<p class="meta">Generated: {generated} UTC · Period: {hours}h · Internal only</p>

<div class="kpi-grid">
<div class="kpi"><div class="kpi-val">{s['total_citations']:,}</div><div class="kpi-label">AI Citations (24h)</div></div>
<div class="kpi"><div class="kpi-val">{s['total_preflight']:,}</div><div class="kpi-label">Preflight API Calls</div></div>
<div class="kpi"><div class="kpi-val">{s['total_entities_cited']:,}</div><div class="kpi-label">Unique Entities Cited</div></div>
<div class="kpi"><div class="kpi-val">{s['total_estimated_reach']:,}</div><div class="kpi-label">Est. Human Reach</div></div>
</div>

<div class="kpi-grid">
<div class="kpi"><div class="kpi-val">{monthly_citations:,}</div><div class="kpi-label">Projected Monthly Citations</div></div>
<div class="kpi"><div class="kpi-val">{monthly_reach:,}</div><div class="kpi-label">Projected Monthly Reach</div></div>
<div class="kpi"><div class="kpi-val">{round(s['total_citations'] / max(s['total_entities_cited'], 1), 1)}</div><div class="kpi-label">Avg Citations / Entity</div></div>
<div class="kpi"><div class="kpi-val">{len([e for e in entities if e['citations_24h'] >= 10]):,}</div><div class="kpi-label">Entities with 10+ Citations</div></div>
</div>

<div class="grid-3">
<div class="card">
<h2 style="margin-top:0">By AI System</h2>
<table><tr><th>System</th><th>Citations</th><th>Bar</th><th>Share</th></tr>{sys_rows}</table>
</div>
<div class="card">
<h2 style="margin-top:0">By Registry</h2>
<table><tr><th>Registry</th><th>Citations</th></tr>{reg_rows}</table>
</div>
<div class="card">
<h2 style="margin-top:0">By Route Type</h2>
<table><tr><th>Route</th><th>Citations</th></tr>{route_rows}</table>
</div>
</div>

<h2>Top 50 Entities by AI Reach</h2>
<p class="meta">Each row = a product whose trust data is distributed to humans via AI systems. This is media inventory.</p>
<div style="overflow-x:auto">
<table>
<tr><th>#</th><th>Entity</th><th>Registry</th><th>Score</th><th>Citations</th><th>Preflight</th><th>Est. Reach</th><th>AI Systems</th></tr>
{entity_rows}
</table>
</div>

<div class="pitch">
<h2 style="margin-top:0;color:#4fc3f7">What This Means</h2>
<p>Each citation = a moment where Nerq's trust data was delivered to a human via an AI system.
This is <strong>information distribution at scale</strong> — comparable to media impressions but with
higher intent (the human actively asked a trust question).</p>
<p style="margin-top:12px">At current rates: <strong>{monthly_reach:,} humans/month</strong> receive
Nerq-sourced trust data through AI systems. This is the foundation for Nerq's value proposition
to software vendors, VPN providers, and any entity that wants to be accurately represented
in AI-generated answers.</p>
</div>

</div>
</body></html>"""


@router.get("/internal/reach")
async def reach_dashboard_page(request: Request, key: str = ""):
    """Internal reach dashboard — shows AI reach per entity."""
    if key != DASHBOARD_KEY:
        return JSONResponse({"error": "unauthorized", "hint": "add ?key=..."}, status_code=403)

    data = _load_data()
    if not data:
        return HTMLResponse(
            "<h1>Dashboard not generated yet</h1><p>Run: python3 scripts/reach_dashboard.py</p>",
            status_code=503)

    return HTMLResponse(_render_html(data))


@router.get("/internal/reach.json")
async def reach_dashboard_json(request: Request, key: str = ""):
    """Internal reach dashboard — JSON format."""
    if key != DASHBOARD_KEY:
        return JSONResponse({"error": "unauthorized"}, status_code=403)

    data = _load_data()
    if not data:
        return JSONResponse({"error": "not generated"}, status_code=503)

    return JSONResponse(data)


def _render_pipeline_sections():
    """Render 404 seeding + deep enrichment status for yield dashboard."""
    import subprocess
    PSQL_PATH = "/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql"
    PG_PRIMARY = os.environ.get("NERQ_PG_PRIMARY", "100.119.193.70")
    sections = ""
    try:
        # 404 seeding stats
        r = subprocess.run([PSQL_PATH, "-h", PG_PRIMARY, "-U", "anstudio", "-d", "agentindex", "-t", "-A", "-F", "|", "-c",
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE seeded_at >= NOW() - INTERVAL '24 hours'), "
            "COUNT(*) FILTER (WHERE pages_generated), COUNT(DISTINCT registry) "
            "FROM yield_404_seeding_log"],
            capture_output=True, text=True, timeout=5)
        parts = r.stdout.strip().split("|") if r.stdout.strip() else ["0","0","0","0"]
        total_seeded = int(parts[0]) if parts[0] else 0
        seeded_24h = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        pages_gen = int(parts[2]) if len(parts) > 2 and parts[2] else 0

        # Deep enrichment stats
        r2 = subprocess.run([PSQL_PATH, "-h", PG_PRIMARY, "-U", "anstudio", "-d", "agentindex", "-t", "-A", "-F", "|", "-c",
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE triggered_at >= NOW() - INTERVAL '24 hours') "
            "FROM yield_deep_enrichments"],
            capture_output=True, text=True, timeout=5)
        dp = r2.stdout.strip().split("|") if r2.stdout.strip() else ["0","0"]
        deep_total = int(dp[0]) if dp[0] else 0
        deep_24h = int(dp[1]) if len(dp) > 1 and dp[1] else 0

        sections = f"""
<div class="g2">
<div class="c">
<h2 style="margin-top:0">404→Live Page Pipeline</h2>
<table>
<tr><td>Total entities seeded</td><td style="text-align:right;font-weight:600">{total_seeded:,}</td></tr>
<tr><td>Seeded (24h)</td><td style="text-align:right">{seeded_24h:,}</td></tr>
<tr><td>Pages generated</td><td style="text-align:right">{pages_gen:,}</td></tr>
<tr><td>Daily cap</td><td style="text-align:right">{seeded_24h}/300</td></tr>
</table>
</div>
<div class="c">
<h2 style="margin-top:0">Deep Enrichment</h2>
<table>
<tr><td>Total deep enrichments</td><td style="text-align:right;font-weight:600">{deep_total:,}</td></tr>
<tr><td>Triggered (24h)</td><td style="text-align:right">{deep_24h:,}</td></tr>
<tr><td>Citation threshold</td><td style="text-align:right">≥10/day</td></tr>
<tr><td>Recency gate</td><td style="text-align:right">7 days</td></tr>
</table>
</div>
</div>"""
    except Exception:
        sections = ""
    return sections


@router.get("/internal/yield")
async def yield_dashboard_page(request: Request, key: str = ""):
    """Internal yield dashboard — shows yield per tier, registry, pattern, bot."""
    if key != DASHBOARD_KEY:
        return JSONResponse({"error": "unauthorized"}, status_code=403)

    import sqlite3
    HISTORY_DB = os.path.expanduser("~/agentindex/data/reach_history.db")
    try:
        conn = sqlite3.connect(HISTORY_DB)
        # Get latest snapshots per granularity
        latest_ts = conn.execute("SELECT MAX(snapshot_ts) FROM yield_snapshots").fetchone()[0]
        if not latest_ts:
            return HTMLResponse("<h1>No yield data yet. Run: python3 scripts/yield_tracker.py</h1>", status_code=503)

        tiers = conn.execute("SELECT key, citations_count, miss_count, entity_count, yield_per_entity FROM yield_snapshots WHERE snapshot_ts=? AND granularity='tier' ORDER BY citations_count DESC", (latest_ts,)).fetchall()
        registries = conn.execute("SELECT key, citations_count, miss_count, entity_count, yield_per_entity, metadata FROM yield_snapshots WHERE snapshot_ts=? AND granularity='registry' ORDER BY citations_count DESC LIMIT 15", (latest_ts,)).fetchall()
        patterns = conn.execute("SELECT key, citations_count, miss_count, entity_count, yield_per_entity FROM yield_snapshots WHERE snapshot_ts=? AND granularity='pattern' ORDER BY citations_count DESC LIMIT 15", (latest_ts,)).fetchall()
        bots = conn.execute("SELECT key, citations_count, miss_count FROM yield_snapshots WHERE snapshot_ts=? AND granularity='bot' ORDER BY citations_count DESC", (latest_ts,)).fetchall()
        top_entities = conn.execute("SELECT key, citations_count, miss_count, metadata FROM yield_snapshots WHERE snapshot_ts=? AND granularity='entity' ORDER BY citations_count DESC LIMIT 30", (latest_ts,)).fetchall()
        conn.close()
    except Exception as e:
        return HTMLResponse(f"<h1>Error: {e}</h1>", status_code=500)

    total_cit = sum(r[1] for r in tiers)
    total_404 = sum(r[2] for r in tiers)
    total_ent = sum(r[3] for r in tiers)

    # Build tier rows
    tier_rows = ""
    for key, cit, miss, ent, yld in tiers:
        tier_rows += f"<tr><td>{key}</td><td style='text-align:right'>{ent:,}</td><td style='text-align:right;font-weight:600'>{cit:,}</td><td style='text-align:right;color:#ef4444'>{miss:,}</td><td style='text-align:right;color:#4fc3f7'>{yld:.1f}</td></tr>"

    # Registry rows
    reg_rows = ""
    for key, cit, miss, ent, yld, meta in registries:
        kings = ""
        try:
            m = json.loads(meta or "{}")
            kings = f" ({m.get('kings', 0)} kings)" if m.get("kings") else ""
        except: pass
        reg_rows += f"<tr><td>{key}{kings}</td><td style='text-align:right'>{ent:,}</td><td style='text-align:right;font-weight:600'>{cit:,}</td><td style='text-align:right'>{yld:.1f}</td></tr>"

    # Pattern rows
    pat_rows = ""
    for key, cit, miss, ent, yld in patterns:
        pat_rows += f"<tr><td>{key}</td><td style='text-align:right;font-weight:600'>{cit:,}</td><td style='text-align:right;color:#ef4444'>{miss:,}</td><td style='text-align:right'>{ent:,}</td><td style='text-align:right;color:#4fc3f7'>{yld:.1f}</td></tr>"

    # Bot rows
    bot_rows = ""
    for key, cit, miss in bots:
        eff = cit / max(cit + miss, 1) * 100
        bot_rows += f"<tr><td>{key}</td><td style='text-align:right;font-weight:600'>{cit:,}</td><td style='text-align:right;color:#ef4444'>{miss:,}</td><td style='text-align:right'>{eff:.0f}%</td></tr>"

    # Entity rows
    ent_rows = ""
    for i, (key, cit, miss, meta) in enumerate(top_entities, 1):
        reg = ""
        try:
            m = json.loads(meta or "{}")
            reg = m.get("registry", "")
            king = " ♛" if m.get("is_king") else ""
        except:
            king = ""
        ent_rows += f"<tr><td>{i}</td><td><a href='/safe/{key}' style='color:#4fc3f7'>{key}</a>{king}</td><td>{reg}</td><td style='text-align:right;font-weight:600'>{cit:,}</td><td style='text-align:right;color:#ef4444'>{miss:,}</td></tr>"

    return HTMLResponse(f"""<!DOCTYPE html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Nerq Yield Dashboard</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:#0a0a0f;color:#e2e8f0;padding:24px}}
.w{{max-width:1400px;margin:0 auto}}
h1{{color:#4fc3f7;font-size:24px;margin-bottom:4px}}
h2{{color:#81d4fa;font-size:16px;margin:28px 0 10px;border-bottom:1px solid #1e293b;padding-bottom:6px}}
.meta{{color:#64748b;font-size:13px;margin-bottom:16px}}
.kpi{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}}
.k{{background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:16px;text-align:center}}
.k .v{{font-size:2em;font-weight:700;color:#4fc3f7;font-family:monospace}}
.k .l{{font-size:11px;color:#64748b;margin-top:4px;text-transform:uppercase}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}}
th{{background:#0f172a;color:#4fc3f7;padding:8px;text-align:left;border-bottom:2px solid #1e293b;font-size:11px;text-transform:uppercase}}
td{{padding:6px 8px;border-bottom:1px solid #1e293b}}
tr:hover{{background:#0f172a}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.g3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px}}
.c{{background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:16px}}
a{{color:#4fc3f7;text-decoration:none}}
@media(max-width:768px){{.kpi,.g2,.g3{{grid-template-columns:1fr}}}}
</style></head><body><div class="w">
<h1>Nerq Yield Dashboard</h1>
<p class="meta">Snapshot: {latest_ts} UTC · <a href="/internal/reach?key={DASHBOARD_KEY}">Reach Dashboard</a></p>

<div class="kpi">
<div class="k"><div class="v">{total_cit:,}</div><div class="l">Citations (24h)</div></div>
<div class="k"><div class="v">{total_404:,}</div><div class="l">AI 404s (demand)</div></div>
<div class="k"><div class="v">{total_ent:,}</div><div class="l">Entities Cited</div></div>
<div class="k"><div class="v">{total_cit / max(total_ent, 1):.1f}</div><div class="l">Yield per Entity</div></div>
</div>

<h2>Yield per Tier</h2>
<table><tr><th>Tier</th><th style="text-align:right">Entities</th><th style="text-align:right">Citations</th><th style="text-align:right">404s</th><th style="text-align:right">Yield/Entity</th></tr>{tier_rows}</table>

<div class="g2">
<div class="c">
<h2 style="margin-top:0">Yield per Registry</h2>
<table><tr><th>Registry</th><th style="text-align:right">Entities</th><th style="text-align:right">Citations</th><th style="text-align:right">Yield</th></tr>{reg_rows}</table>
</div>
<div class="c">
<h2 style="margin-top:0">Yield per AI Bot</h2>
<table><tr><th>Bot</th><th style="text-align:right">Citations</th><th style="text-align:right">404s</th><th style="text-align:right">Efficiency</th></tr>{bot_rows}</table>
</div>
</div>

<h2>Yield per URL Pattern</h2>
<table><tr><th>Pattern</th><th style="text-align:right">Citations</th><th style="text-align:right">404s</th><th style="text-align:right">Entities</th><th style="text-align:right">Yield/Entity</th></tr>{pat_rows}</table>

<h2>Top 30 Entities by Citations</h2>
<table><tr><th>#</th><th>Entity</th><th>Registry</th><th style="text-align:right">Citations</th><th style="text-align:right">404s</th></tr>{ent_rows}</table>

{_render_pipeline_sections()}

</div></body></html>""")


def mount_reach_dashboard(app):
    """Mount reach dashboard routes."""
    app.include_router(router)
    logger.info("Reach dashboard mounted at /internal/reach + /internal/yield")
