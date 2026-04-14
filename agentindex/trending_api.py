"""
Emergent Patterns — "What AI Agents Ask About Right Now"
=========================================================
Unique data: what entities AI agents (ChatGPT, Claude, Perplexity, MCP clients)
query about in real-time. No competitor has this signal.

Routes:
  GET /v1/trending           — top trending entities
  GET /v1/trending/{category} — per domain
  GET /trending               — public HTML dashboard
  MCP tool: nerq_trending

Data sources:
  - preflight_analytics (MCP trust checks): 128K+ queries, 45K entities
  - requests (user_triggered): ChatGPT-User, Perplexity-User entity queries
"""

import html as html_mod
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, date, timedelta
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("nerq.trending")

ANALYTICS_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "analytics.db")

router_trending = APIRouter(tags=["trending"])

_cache = {}
CACHE_TTL = 300  # 5 min


def _esc(s):
    return html_mod.escape(str(s)) if s else ""


def _get_trending_data(period="24h", limit=50):
    """Compute trending entities from query data."""
    conn = sqlite3.connect(ANALYTICS_DB, timeout=15)

    if period == "24h":
        recent = "date('now', '-1 day')"
        baseline = "date('now', '-7 days')"
        baseline_days = 7
    elif period == "7d":
        recent = "date('now', '-7 days')"
        baseline = "date('now', '-30 days')"
        baseline_days = 30
    else:
        recent = "date('now', '-1 day')"
        baseline = "date('now', '-7 days')"
        baseline_days = 7

    # Combine preflight queries + user-triggered entity visits
    rows = conn.execute(f"""
        WITH combined AS (
            SELECT target as entity, ts, 'preflight' as source
            FROM preflight_analytics
            WHERE target IS NOT NULL AND target != '' AND target != 'test'
              AND ts >= {baseline}
            UNION ALL
            SELECT REPLACE(path, '/safe/', '') as entity, ts, 'citation' as source
            FROM requests
            WHERE bot_purpose='user_triggered' AND path LIKE '/safe/%' AND path NOT LIKE '/safe/%/%'
              AND ts >= {baseline}
        )
        SELECT entity,
          SUM(CASE WHEN ts >= {recent} THEN 1 ELSE 0 END) as recent_count,
          COUNT(*) * 1.0 / {baseline_days} as daily_baseline,
          SUM(CASE WHEN source='preflight' THEN 1 ELSE 0 END) as preflight_queries,
          SUM(CASE WHEN source='citation' THEN 1 ELSE 0 END) as citation_queries,
          COUNT(*) as total
        FROM combined
        GROUP BY entity
        HAVING SUM(CASE WHEN ts >= {recent} THEN 1 ELSE 0 END) >= 2
        ORDER BY SUM(CASE WHEN ts >= {recent} THEN 1 ELSE 0 END) * 1.0 /
                 MAX(COUNT(*) * 1.0 / {baseline_days}, 0.5) DESC
        LIMIT {limit}
    """).fetchall()

    conn.close()

    results = []
    for entity, recent_count, daily_baseline, pf, cit, total in rows:
        trend_ratio = recent_count / max(daily_baseline, 0.5)
        results.append({
            "entity": entity,
            "queries_recent": recent_count,
            "queries_daily_avg": round(daily_baseline, 1),
            "trend_ratio": round(trend_ratio, 2),
            "preflight_queries": pf,
            "citation_queries": cit,
            "total_queries_period": total,
            "signal": "spike" if trend_ratio > 3 else "rising" if trend_ratio > 1.5 else "stable",
        })

    return results


def _get_anomalies():
    """Detect entities with sudden query spikes (>5x baseline)."""
    conn = sqlite3.connect(ANALYTICS_DB, timeout=15)
    rows = conn.execute("""
        WITH daily AS (
            SELECT target as entity,
              SUM(CASE WHEN ts >= date('now', '-1 day') THEN 1 ELSE 0 END) as today,
              SUM(CASE WHEN ts >= date('now', '-7 days') THEN 1 ELSE 0 END) / 7.0 as avg_7d
            FROM preflight_analytics
            WHERE target IS NOT NULL AND target != '' AND target != 'test'
              AND ts >= date('now', '-7 days')
            GROUP BY target
            HAVING today >= 3 AND avg_7d > 0
        )
        SELECT entity, today, ROUND(avg_7d, 1), ROUND(today / avg_7d, 1) as spike
        FROM daily WHERE today / avg_7d > 5.0
        ORDER BY spike DESC LIMIT 20
    """).fetchall()
    conn.close()

    return [{"entity": e, "today": t, "daily_avg": a, "spike_ratio": s}
            for e, t, a, s in rows]


def _get_category_trending(category):
    """Trending for a specific registry/category."""
    conn = sqlite3.connect(ANALYTICS_DB, timeout=15)
    # Map category to path patterns
    patterns = {
        "npm": "/npm/%", "pypi": "/pypi/%", "crypto": "/crypto/%",
        "vpn": "/safe/%vpn%", "ai": "/safe/%agent%",
    }
    pattern = patterns.get(category, f"/safe/%{category}%")

    rows = conn.execute("""
        SELECT REPLACE(path, '/safe/', '') as entity,
          SUM(CASE WHEN ts >= date('now', '-1 day') THEN 1 ELSE 0 END) as today,
          COUNT(*) / 7.0 as avg_7d,
          COUNT(*) as total
        FROM requests
        WHERE ts >= date('now', '-7 days')
          AND (path LIKE ? OR bot_purpose='user_triggered')
          AND path LIKE '/safe/%' AND path NOT LIKE '/safe/%/%'
        GROUP BY entity HAVING today >= 1
        ORDER BY today DESC LIMIT 30
    """, (pattern,)).fetchall()
    conn.close()

    return [{"entity": e, "queries_today": t, "daily_avg": round(a, 1), "total_7d": tot}
            for e, t, a, tot in rows]


# ── API Endpoints ──

@router_trending.get("/v1/trending")
async def api_trending(period: str = "24h", limit: int = 30):
    """Top trending entities across all AI agent queries."""
    ck = f"trending:{period}:{limit}"
    cached = _cache.get(ck)
    if cached and time.time() - cached[1] < CACHE_TTL:
        return JSONResponse(cached[0])

    data = _get_trending_data(period, min(limit, 100))
    result = {
        "data": data,
        "meta": {
            "period": period,
            "source": "AI agent queries (MCP preflight + ChatGPT/Claude/Perplexity citations)",
            "updated": datetime.utcnow().isoformat() + "Z",
            "count": len(data),
        }
    }
    _cache[ck] = (result, time.time())
    return JSONResponse(result)


@router_trending.get("/v1/trending/{category}")
async def api_trending_category(category: str):
    """Trending entities for a specific category."""
    data = _get_category_trending(category)
    return JSONResponse({
        "data": data,
        "meta": {"category": category, "updated": datetime.utcnow().isoformat() + "Z"}
    })


@router_trending.get("/v1/anomalies")
async def api_anomalies():
    """Entities with sudden query spikes (>5x baseline)."""
    data = _get_anomalies()
    return JSONResponse({
        "data": data,
        "meta": {"threshold": "5x daily average", "updated": datetime.utcnow().isoformat() + "Z"}
    })


# ── Public Dashboard ──

@router_trending.get("/trending", response_class=HTMLResponse)
async def trending_dashboard():
    ck = "trending_html"
    cached = _cache.get(ck)
    if cached and time.time() - cached[1] < CACHE_TTL:
        return HTMLResponse(cached[0])

    trending = _get_trending_data("24h", 30)
    anomalies = _get_anomalies()
    now = datetime.now()

    html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Agent Trending — What AI Is Asking About Right Now | Nerq</title>
<meta name="description" content="Real-time trending entities from AI agent queries. See what ChatGPT, Claude, Perplexity, and MCP agents are checking right now.">
<link rel="canonical" href="https://nerq.ai/trending">
<meta property="og:title" content="AI Agent Trending — Nerq">
<meta property="og:description" content="What AI agents are asking about right now. Live data from {len(trending)} trending entities.">
<meta name="robots" content="index, follow, max-snippet:-1">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Article","headline":"AI Agent Trending — What AI Is Asking About Right Now","author":{{"@type":"Organization","name":"Nerq"}},"publisher":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}},"datePublished":"{date.today().isoformat()}","dateModified":"{date.today().isoformat()}","description":"Real-time trending data from AI agent trust queries across {len(trending)} entities."}}
</script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui,-apple-system,sans-serif;color:#1e293b;background:#fafaf9;line-height:1.6;font-size:15px}}
.container{{max-width:900px;margin:0 auto;padding:24px}}
h1{{font-size:1.5em;margin-bottom:4px}}
.sub{{color:#64748b;font-size:13px;margin-bottom:24px}}
.card{{background:#fff;border:1px solid #e5e5e3;border-radius:10px;padding:16px;margin-bottom:16px}}
.card h2{{font-size:1em;margin:0 0 12px;color:#0d9488}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280;font-weight:500}}
td{{padding:8px;border-bottom:1px solid #f1f5f9}}
.spike{{color:#ef4444;font-weight:600}}
.rising{{color:#f59e0b;font-weight:600}}
.stable{{color:#6b7280}}
a{{color:#0d9488;text-decoration:none}}
a:hover{{text-decoration:underline}}
.badge{{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600}}
.badge-spike{{background:#fef2f2;color:#ef4444}}
.badge-rising{{background:#fffbeb;color:#f59e0b}}
.badge-stable{{background:#f0fdf4;color:#16a34a}}
</style></head><body>
<div class="container">
<h1>AI Agent Trending</h1>
<p class="sub">What AI agents (ChatGPT, Claude, Perplexity, MCP clients) are checking right now. Updated {now.strftime('%H:%M')} UTC. Data from {now.strftime('%B %d, %Y')}.</p>
"""

    # Trending table
    html += '<div class="card"><h2>Trending Entities (24h)</h2>'
    html += '<p style="font-size:12px;color:#94a3b8;margin-bottom:8px">Ranked by query acceleration vs 7-day baseline. Only entities with ≥2 queries today shown.</p>'
    html += '<table><tr><th>#</th><th>Entity</th><th>Today</th><th>Avg/day</th><th>Trend</th><th>Signal</th></tr>'
    for i, t in enumerate(trending[:20]):
        signal_class = t["signal"]
        badge = f'<span class="badge badge-{signal_class}">{t["signal"]}</span>'
        entity_link = f'<a href="/safe/{_esc(t["entity"])}">{_esc(t["entity"])}</a>'
        html += f'<tr><td>{i+1}</td><td>{entity_link}</td><td>{t["queries_recent"]}</td><td>{t["queries_daily_avg"]}</td><td>{t["trend_ratio"]}x</td><td>{badge}</td></tr>'
    html += '</table></div>'

    # Anomalies
    if anomalies:
        html += '<div class="card"><h2>Anomaly Detection</h2>'
        html += '<p style="font-size:12px;color:#94a3b8;margin-bottom:8px">Entities with sudden query spikes (&gt;5x their normal daily volume). May indicate emerging security events or trending topics.</p>'
        html += '<table><tr><th>Entity</th><th>Today</th><th>Normal</th><th>Spike</th></tr>'
        for a in anomalies[:10]:
            html += f'<tr><td><a href="/safe/{_esc(a["entity"])}">{_esc(a["entity"])}</a></td><td class="spike">{a["today"]}</td><td>{a["daily_avg"]}</td><td class="spike">{a["spike_ratio"]}x</td></tr>'
        html += '</table></div>'

    # API docs
    html += f"""<div class="card"><h2>API Access</h2>
<p style="font-size:13px;color:#374151">This data is available via API for integration into your workflows:</p>
<pre style="background:#f8fafc;padding:12px;border-radius:6px;font-size:12px;overflow-x:auto">
GET /v1/trending              — Top trending entities
GET /v1/trending/npm          — npm package trending
GET /v1/trending/crypto       — Crypto token trending
GET /v1/anomalies             — Spike detection
</pre>
<p style="font-size:12px;color:#94a3b8;margin-top:8px">Data source: {127000}+ AI agent trust queries across 45,000+ entities. Updated every 5 minutes.</p>
</div>

<p style="font-size:12px;color:#94a3b8;text-align:center;margin-top:16px">
<a href="/" style="color:#94a3b8">Nerq</a> · <a href="/citation-dashboard" style="color:#94a3b8">Citation Dashboard</a> · <a href="/flywheel" style="color:#94a3b8">Flywheel</a>
</p>
</div></body></html>"""

    _cache[ck] = (html, time.time())
    return HTMLResponse(html)


def mount_trending(app):
    """Mount trending routes."""
    app.include_router(router_trending)
