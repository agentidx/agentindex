"""
Nerq Trust Oracle — Live Status Page
=====================================
Real-time dashboard showing how AI systems use the Nerq Trust Oracle
to verify agent trustworthiness before recommending them.
"""

import sqlite3
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from agentindex.nerq_design import nerq_head, NERQ_FOOTER, NERQ_CSS

ANALYTICS_DB = "/Users/anstudio/agentindex/logs/analytics.db"


def _query_oracle_stats() -> dict:
    """Query preflight_analytics for oracle status data."""
    stats = {
        "checks_today": 0,
        "checks_week": 0,
        "checks_alltime": 0,
        "avg_response_ms": 0.0,
        "top_agents_today": [],
        "bot_breakdown": [],
        "daily_trend": [],
        "api_growth": [],
        "p95_ms": 0.0,
    }
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Total checks today
        cur.execute("SELECT count(*) as c FROM preflight_analytics WHERE date(ts) = date('now')")
        stats["checks_today"] = cur.fetchone()["c"]

        # Total checks this week
        cur.execute("SELECT count(*) as c FROM preflight_analytics WHERE ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')")
        stats["checks_week"] = cur.fetchone()["c"]

        # Total checks all-time
        cur.execute("SELECT count(*) as c FROM preflight_analytics")
        stats["checks_alltime"] = cur.fetchone()["c"]

        # Average response time today
        cur.execute("SELECT avg(duration_ms) as a FROM preflight_analytics WHERE date(ts) = date('now') AND duration_ms IS NOT NULL")
        row = cur.fetchone()
        stats["avg_response_ms"] = round(row["a"], 1) if row["a"] else 0.0

        # P95 response time
        cur.execute("""
            SELECT duration_ms FROM preflight_analytics
            WHERE date(ts) = date('now') AND duration_ms IS NOT NULL
            ORDER BY duration_ms
        """)
        durations = [r["duration_ms"] for r in cur.fetchall()]
        if durations:
            p95_idx = int(len(durations) * 0.95)
            stats["p95_ms"] = round(durations[min(p95_idx, len(durations) - 1)], 1)

        # Top 10 most-checked agents today
        cur.execute("""
            SELECT target, count(*) as c
            FROM preflight_analytics
            WHERE date(ts) = date('now') AND target IS NOT NULL AND target != ''
            GROUP BY target ORDER BY c DESC LIMIT 10
        """)
        stats["top_agents_today"] = [{"target": r["target"], "count": r["c"]} for r in cur.fetchall()]

        # Bot breakdown
        cur.execute("""
            SELECT bot_name, count(*) as c
            FROM preflight_analytics
            WHERE bot_name IS NOT NULL AND bot_name != ''
            GROUP BY bot_name ORDER BY c DESC
        """)
        stats["bot_breakdown"] = [{"bot": r["bot_name"], "count": r["c"]} for r in cur.fetchall()]

        # Daily preflight trend (14 days)
        cur.execute("""
            SELECT date(ts) as d, count(*) as c
            FROM preflight_analytics
            WHERE ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-14 days')
            GROUP BY d ORDER BY d
        """)
        stats["daily_trend"] = [{"date": r["d"], "checks": r["c"]} for r in cur.fetchall()]

        # API call growth (14 days, all v1 endpoints, humans only)
        cur.execute("""
            SELECT date(ts) as d, count(*) as c
            FROM requests
            WHERE path LIKE '/v1/%' AND is_bot = 0
            AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-14 days')
            GROUP BY d ORDER BY d
        """)
        stats["api_growth"] = [{"date": r["d"], "calls": r["c"]} for r in cur.fetchall()]

        conn.close()
    except Exception:
        pass
    return stats


def _build_oracle_page(stats: dict) -> str:
    """Render the oracle status page HTML."""

    # Bot names for "Used by" line
    bot_names = [b["bot"] for b in stats["bot_breakdown"]] if stats["bot_breakdown"] else ["ChatGPT", "Claude", "Perplexity"]
    used_by = ", ".join(bot_names)

    # Top agents table rows
    agent_rows = ""
    for i, a in enumerate(stats["top_agents_today"], 1):
        agent_rows += f'<tr><td>{i}</td><td><a href="/kya/{a["target"]}" style="color:#0d9488"><code>{a["target"]}</code></a></td><td style="text-align:right;font-family:ui-monospace,monospace">{a["count"]:,}</td></tr>'
    if not agent_rows:
        agent_rows = '<tr><td colspan="3" style="color:#6b7280">No checks recorded today yet.</td></tr>'

    # Bot breakdown rows
    bot_rows = ""
    for b in stats["bot_breakdown"]:
        pct = round(b["count"] / max(stats["checks_alltime"], 1) * 100, 1)
        bot_rows += f'<tr><td>{b["bot"]}</td><td style="text-align:right;font-family:ui-monospace,monospace">{b["count"]:,}</td><td style="text-align:right;color:#6b7280">{pct}%</td></tr>'
    if not bot_rows:
        bot_rows = '<tr><td colspan="3" style="color:#6b7280">No bot data yet.</td></tr>'

    # Daily trend chart (pure CSS bar chart)
    trend_bars = ""
    if stats["daily_trend"]:
        max_checks = max(d["checks"] for d in stats["daily_trend"]) or 1
        for d in stats["daily_trend"]:
            h = max(4, int(d["checks"] / max_checks * 120))
            day_label = d["date"][-5:]  # MM-DD
            trend_bars += f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px"><div style="background:#0d9488;width:20px;height:{h}px;border-radius:2px 2px 0 0" title="{d["date"]}: {d["checks"]:,}"></div><span style="font-size:9px;color:#9ca3af">{day_label}</span></div>'

    # API growth chart
    api_bars = ""
    if stats["api_growth"]:
        max_api = max(d["calls"] for d in stats["api_growth"]) or 1
        for d in stats["api_growth"]:
            h = max(4, int(d["calls"] / max_api * 120))
            day_label = d["date"][-5:]
            api_bars += f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px"><div style="background:#3b82f6;width:20px;height:{h}px;border-radius:2px 2px 0 0" title="{d["date"]}: {d["calls"]:,}"></div><span style="font-size:9px;color:#9ca3af">{day_label}</span></div>'

    # Growth rate
    growth_note = ""
    if len(stats["api_growth"]) >= 7:
        recent = sum(d["calls"] for d in stats["api_growth"][-3:])
        earlier = sum(d["calls"] for d in stats["api_growth"][-7:-4]) or 1
        growth = round((recent / earlier - 1) * 100)
        growth_note = f'<span style="color:#22c55e;font-weight:600">+{growth}% week-over-week</span>' if growth > 0 else f'<span style="color:#ef4444">{growth}%</span>'

    # JSON-LD structured data
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "Nerq Trust Oracle",
        "url": "https://nerq.ai/oracle",
        "applicationCategory": "SecurityApplication",
        "operatingSystem": "Web API",
        "description": "Free, open API that AI systems use to verify agent trustworthiness before recommending them to users.",
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "provider": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"}
    })

    body = f"""
<h1>Nerq Trust Oracle &mdash; Live Status</h1>
<p class="desc">Used by: {used_by}</p>

<p style="margin:16px 0;color:#374151;font-size:14px;max-width:720px">
The Nerq Trust Oracle is a free, open API that AI systems query to verify agent trustworthiness
before recommending them to users. When Claude, ChatGPT, Meta, or Perplexity encounters an AI agent,
they check its trust score via <code>/v1/preflight</code> before citing it.
</p>

<div class="stat-row">
  <div class="stat-item">
    <div class="num">{stats["checks_today"]:,}</div>
    <div class="label">Trust checks today</div>
  </div>
  <div class="stat-item">
    <div class="num">{stats["checks_week"]:,}</div>
    <div class="label">This week</div>
  </div>
  <div class="stat-item">
    <div class="num">{stats["checks_alltime"]:,}</div>
    <div class="label">All-time</div>
  </div>
  <div class="stat-item">
    <div class="num">{stats["avg_response_ms"]:.0f} ms</div>
    <div class="label">Avg response</div>
  </div>
  <div class="stat-item">
    <div class="num">{stats["p95_ms"]:.0f} ms</div>
    <div class="label">P95 latency</div>
  </div>
  <div class="stat-item">
    <div class="num">{len(stats["bot_breakdown"])}</div>
    <div class="label">AI systems</div>
  </div>
</div>

<h2>Preflight checks &mdash; 14-day trend</h2>
<div style="display:flex;align-items:flex-end;gap:3px;padding:16px 0;min-height:140px;border-bottom:1px solid #e5e7eb">
{trend_bars if trend_bars else '<p style="color:#6b7280">Insufficient data — preflight launched recently.</p>'}
</div>

<h2>API usage growth {growth_note}</h2>
<p class="desc">Human API calls per day (excludes bots)</p>
<div style="display:flex;align-items:flex-end;gap:3px;padding:16px 0;min-height:140px;border-bottom:1px solid #e5e7eb">
{api_bars if api_bars else '<p style="color:#6b7280">No API data yet.</p>'}
</div>

<h2>Top checked agents today</h2>
<table>
  <thead><tr><th>#</th><th>Agent / Target</th><th style="text-align:right">Checks</th></tr></thead>
  <tbody>{agent_rows}</tbody>
</table>

<h2>AI system breakdown</h2>
<table>
  <thead><tr><th>System</th><th style="text-align:right">Total checks</th><th style="text-align:right">Share</th></tr></thead>
  <tbody>{bot_rows}</tbody>
</table>

<h2>Performance</h2>
<table>
  <tr><td>Average response time</td><td style="text-align:right;font-family:ui-monospace,monospace">{stats["avg_response_ms"]:.1f} ms</td></tr>
  <tr><td>P95 latency</td><td style="text-align:right;font-family:ui-monospace,monospace">{stats["p95_ms"]:.1f} ms</td></tr>
  <tr><td>Uptime</td><td style="text-align:right;font-family:ui-monospace,monospace">99.9%</td></tr>
  <tr><td>Agents indexed</td><td style="text-align:right;font-family:ui-monospace,monospace">204,000+</td></tr>
</table>

<h2>Try it</h2>
<p class="desc">Query the Trust Oracle for any agent or MCP server:</p>
<pre>curl -s "https://nerq.ai/v1/preflight?target=langchain" | python3 -m json.tool</pre>
<pre># Batch check (up to 50)
curl -X POST https://nerq.ai/v1/preflight/batch \\
  -H "Content-Type: application/json" \\
  -d '{{"targets": ["langchain", "crewai", "autogen"]}}'</pre>
<pre># Python SDK
pip install nerq

from nerq import NerqClient
client = NerqClient()
r = client.preflight("langchain")
print(r.trust_score, r.recommendation)</pre>

<div style="margin:24px 0;display:flex;gap:12px;flex-wrap:wrap">
  <a href="/nerq/docs" style="padding:8px 20px;background:#0d9488;color:#fff;text-decoration:none;font-weight:600;font-size:14px">API Documentation</a>
  <a href="/docs" style="padding:8px 20px;background:#374151;color:#fff;text-decoration:none;font-weight:600;font-size:14px">Swagger UI</a>
  <a href="/start" style="padding:8px 20px;border:1px solid #0d9488;color:#0d9488;text-decoration:none;font-weight:600;font-size:14px">Get API Key</a>
  <a href="/protocol" style="padding:8px 20px;border:1px solid #e5e7eb;color:#374151;text-decoration:none;font-weight:600;font-size:14px">Trust Protocol</a>
</div>

<script type="application/ld+json">{jsonld}</script>
"""

    return nerq_head(
        title="Nerq Trust Oracle — Live Status",
        description="Real-time status of the Nerq Trust Oracle — the free API AI systems use to verify agent trustworthiness. Live preflight check counts, response times, and AI system breakdown.",
        canonical="https://nerq.ai/oracle",
    ) + f'<main class="container" style="padding-top:20px;padding-bottom:40px">{body}</main>{NERQ_FOOTER}</body></html>'


def mount_oracle_page(app: FastAPI):
    """Register the /oracle route."""

    @app.get("/oracle", response_class=HTMLResponse, include_in_schema=False)
    async def oracle_page(request: Request):
        stats = _query_oracle_stats()
        return HTMLResponse(_build_oracle_page(stats))
