"""
Combined ZARQ + Nerq Dashboard
Route: /dashboard
Public overview dashboard showing both platforms.
"""

import json
import logging
import os
import sqlite3
import time as _time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.dashboard")

CRYPTO_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto", "crypto_trust.db")
API_LOG_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto", "zarq_api_log.db")

router_combined_dashboard = APIRouter(tags=["dashboard"])

# Category normalization map — merge duplicates
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

# Cache
_dash_cache: dict = {"data": None, "ts": 0}
_DASH_TTL = 300  # 5 min


def _get_nerq_data() -> dict:
    """Get Nerq agent index stats."""
    session = get_session()
    try:
        combined = session.execute(text("""
            SELECT
                SUM(CASE WHEN agent_type = 'agent' THEN 1 ELSE 0 END) as agents,
                SUM(CASE WHEN agent_type = 'tool' THEN 1 ELSE 0 END) as tools,
                SUM(CASE WHEN agent_type = 'mcp_server' THEN 1 ELSE 0 END) as mcp_servers,
                SUM(CASE WHEN agent_type = 'model' THEN 1 ELSE 0 END) as models,
                SUM(CASE WHEN agent_type = 'dataset' THEN 1 ELSE 0 END) as datasets,
                SUM(CASE WHEN agent_type = 'space' THEN 1 ELSE 0 END) as spaces,
                SUM(CASE WHEN agent_type IN ('agent','mcp_server','tool')
                          AND trust_score_v2 >= 60 THEN 1 ELSE 0 END) as trusted,
                SUM(CASE WHEN agent_type IN ('agent','mcp_server','tool')
                          AND trust_score_v2 >= 35 AND trust_score_v2 < 60 THEN 1 ELSE 0 END) as caution,
                SUM(CASE WHEN agent_type IN ('agent','mcp_server','tool')
                          AND trust_score_v2 < 35 AND trust_score_v2 IS NOT NULL THEN 1 ELSE 0 END) as untrusted,
                ROUND(AVG(CASE WHEN agent_type IN ('agent','mcp_server','tool')
                               AND trust_score_v2 IS NOT NULL
                          THEN trust_score_v2 END)::numeric, 1) as avg_trust
            FROM entity_lookup WHERE is_active = true
        """)).fetchone()

        total_assets = session.execute(
            text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'agents'")
        ).scalar() or 0

        # Top categories — exclude uncategorized, normalize duplicates
        cat_rows = session.execute(text("""
            SELECT COALESCE(category, 'uncategorized') as cat, COUNT(*)
            FROM entity_lookup WHERE is_active = true AND agent_type IN ('agent', 'mcp_server', 'tool')
            GROUP BY cat ORDER BY COUNT(*) DESC LIMIT 30
        """)).fetchall()

        # Normalize and merge categories
        merged: dict[str, int] = {}
        for cat, cnt in cat_rows:
            if cat == "uncategorized":
                continue
            normalized = _CAT_NORMALIZE.get(cat, cat)
            merged[normalized] = merged.get(normalized, 0) + cnt
        # Sort by count desc, take top 10
        top_categories = dict(sorted(merged.items(), key=lambda x: -x[1])[:10])

        return {
            "total_assets": max(total_assets, 0),
            "agents": combined[0] or 0,
            "tools": combined[1] or 0,
            "mcp_servers": combined[2] or 0,
            "models": combined[3] or 0,
            "datasets": combined[4] or 0,
            "spaces": combined[5] or 0,
            "trusted": combined[6] or 0,
            "caution": combined[7] or 0,
            "untrusted": combined[8] or 0,
            "avg_trust": float(combined[9]) if combined[9] else None,
            "top_categories": top_categories,
        }
    except Exception as e:
        logger.error(f"nerq data error: {e}")
        return {"error": str(e)[:200]}
    finally:
        session.close()


def _classify_ua(ua: str) -> str:
    if not ua:
        return None
    ul = ua.lower()
    if any(x in ul for x in ['claude', 'anthropic']):
        return "Claude"
    if any(x in ul for x in ['chatgpt', 'gptbot', 'openai']):
        return "ChatGPT"
    if 'perplexity' in ul:
        return "Perplexity"
    if any(x in ul for x in ['googlebot', 'google-extended', 'apis-google']):
        return "Google"
    if any(x in ul for x in ['bingbot']):
        return "Bing"
    return None


def _get_scout_data() -> dict:
    """Get Scout status from nerq_scout_log table."""
    try:
        session = get_session()
        evaluated_total = session.execute(text(
            "SELECT COUNT(*) FROM nerq_scout_log WHERE event_type = 'scout_evaluate'"
        )).scalar() or 0
        featured_total = session.execute(text(
            "SELECT COUNT(DISTINCT agent_name) FROM nerq_scout_log WHERE event_type = 'scout_evaluate'"
        )).scalar() or 0
        claimed = session.execute(text(
            "SELECT COUNT(*) FROM nerq_scout_log WHERE event_type = 'claim_submit'"
        )).scalar() or 0
        reviews_total = session.execute(text(
            "SELECT COUNT(*) FROM agent_reviews"
        )).scalar() or 0

        # Last run time
        last_run_row = session.execute(text(
            "SELECT MAX(created_at) FROM nerq_scout_log WHERE event_type = 'scout_evaluate'"
        )).scalar()
        last_run = last_run_row.isoformat() if last_run_row else None

        # Next run: cron runs at 04, 10, 16, 22 UTC
        next_run = None
        if last_run_row:
            now = datetime.now(timezone.utc)
            cron_hours = [4, 10, 16, 22]
            for offset in range(2):  # today and tomorrow
                for h in cron_hours:
                    candidate = now.replace(hour=h, minute=0, second=0, microsecond=0) + timedelta(days=offset)
                    if candidate > now:
                        next_run = candidate.isoformat()
                        break
                if next_run:
                    break

        # Blog posts count
        import glob as _glob
        blog_count = len(_glob.glob(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "auto-reports", "*.md")
        ))

        # Dev.to articles (count scout_evaluate entries that have devto in details — approximate)
        devto_count = blog_count  # 1:1 with blog posts since auto-publisher publishes each

        # Bluesky posts (approximate from scout runs that have bluesky posting enabled)
        bluesky_count = 0
        try:
            from pathlib import Path
            bsky_creds = Path.home() / ".config" / "nerq" / "bluesky_handle"
            if bsky_creds.exists():
                # Count distinct scout run days as proxy for bluesky posts
                bsky_days = session.execute(text(
                    "SELECT COUNT(DISTINCT DATE(created_at)) FROM nerq_scout_log WHERE event_type = 'scout_evaluate'"
                )).scalar() or 0
                bluesky_count = bsky_days
        except Exception:
            pass

        # Last 5 evaluated agents
        last_5_rows = session.execute(text("""
            SELECT agent_name, details, created_at
            FROM nerq_scout_log
            WHERE event_type = 'scout_evaluate' AND agent_name IS NOT NULL
            ORDER BY created_at DESC LIMIT 5
        """)).fetchall()
        last_5 = []
        for r in last_5_rows:
            details = r[1] if isinstance(r[1], dict) else (json.loads(r[1]) if r[1] else {})
            last_5.append({
                "name": r[0],
                "trust_score": details.get("trust_score"),
                "grade": details.get("grade"),
                "evaluated_at": r[2].isoformat() if r[2] else None,
            })

        session.close()
        return {
            "evaluated_total": evaluated_total,
            "featured_total": featured_total,
            "claimed": claimed,
            "reviews_total": reviews_total,
            "last_run": last_run,
            "next_run": next_run,
            "blog_posts": blog_count,
            "devto_articles": devto_count,
            "bluesky_posts": bluesky_count,
            "last_5_evaluated": last_5,
        }
    except Exception:
        return {"evaluated_total": 0, "featured_total": 0, "claimed": 0, "reviews_total": 0}


def _get_traffic_data() -> dict:
    """Get API traffic stats from zarq_api_log.db."""
    if not os.path.exists(API_LOG_DB):
        return {}
    try:
        conn = sqlite3.connect(API_LOG_DB)
        now_dt = datetime.now(timezone.utc)
        cutoff_24h = (now_dt - timedelta(hours=24)).isoformat()
        cutoff_10m = (now_dt - timedelta(minutes=10)).isoformat()

        r24 = conn.execute("SELECT COUNT(*) FROM api_log WHERE timestamp >= ?", [cutoff_24h]).fetchone()[0]
        uips = conn.execute("SELECT COUNT(DISTINCT ip_hash) FROM api_log WHERE timestamp >= ?", [cutoff_24h]).fetchone()[0]

        # Latency (last 10 min, /v1/ endpoints)
        latencies = [r[0] for r in conn.execute(
            "SELECT latency_ms FROM api_log WHERE timestamp >= ? AND endpoint LIKE '/v1/%' ORDER BY latency_ms",
            [cutoff_10m]).fetchall()]
        p50 = latencies[len(latencies) // 2] if latencies else 0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0

        # Top nerq endpoints
        nerq_eps = conn.execute("""
            SELECT endpoint, COUNT(*) as cnt FROM api_log
            WHERE timestamp >= ? AND endpoint LIKE '/v1/agent/%'
            GROUP BY endpoint ORDER BY cnt DESC LIMIT 8
        """, [cutoff_24h]).fetchall()

        # AI bot crawls (last 24h)
        all_uas = conn.execute("""
            SELECT user_agent, COUNT(*) as cnt FROM api_log
            WHERE timestamp >= ? GROUP BY user_agent
        """, [cutoff_24h]).fetchall()
        ai_bots: dict[str, int] = {}
        for ua_row in all_uas:
            bot = _classify_ua(ua_row[0] or "")
            if bot:
                ai_bots[bot] = ai_bots.get(bot, 0) + ua_row[1]

        conn.close()
        return {
            "requests_24h": r24,
            "unique_ips_24h": uips,
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "top_nerq_endpoints": [{"endpoint": r[0], "count": r[1]} for r in nerq_eps],
            "ai_bot_crawls": dict(sorted(ai_bots.items(), key=lambda x: -x[1])),
        }
    except Exception as e:
        logger.error(f"traffic data error: {e}")
        return {}


def _get_zarq_data() -> dict:
    """Get ZARQ crypto intelligence stats."""
    if not os.path.exists(CRYPTO_DB):
        return {"available": False}
    try:
        conn = sqlite3.connect(CRYPTO_DB)
        conn.row_factory = sqlite3.Row

        # Total tokens rated
        total_tokens = conn.execute(
            "SELECT COUNT(DISTINCT token_id) FROM nerq_risk_signals WHERE signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)"
        ).fetchone()[0] or 0

        # Latest run date
        latest_date = conn.execute("SELECT MAX(signal_date) FROM nerq_risk_signals").fetchone()[0] or "N/A"

        # Risk distribution
        risk_rows = conn.execute("""
            SELECT risk_level, COUNT(*) FROM nerq_risk_signals
            WHERE signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)
            GROUP BY risk_level
        """).fetchall()
        risk_dist = {r[0]: r[1] for r in risk_rows}

        # Warnings count
        warnings = conn.execute("""
            SELECT COUNT(*) FROM nerq_risk_signals
            WHERE signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)
            AND risk_level IN ('WARNING', 'CRITICAL')
        """).fetchone()[0] or 0

        # Rating distribution
        rating_rows = conn.execute("""
            SELECT rating, COUNT(*) FROM crypto_rating_daily
            WHERE run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
            GROUP BY rating ORDER BY COUNT(*) DESC
        """).fetchall()
        ratings = {r[0]: r[1] for r in rating_rows}

        # Crash shield saves
        saves = 0
        try:
            saves = conn.execute("SELECT COUNT(*) FROM crash_shield_saves").fetchone()[0] or 0
        except Exception:
            pass

        conn.close()
        return {
            "available": True,
            "total_tokens": total_tokens,
            "latest_date": latest_date,
            "risk_distribution": risk_dist,
            "active_warnings": warnings,
            "ratings": ratings,
            "crash_shield_saves": saves,
        }
    except Exception as e:
        logger.error(f"zarq data error: {e}")
        return {"available": False, "error": str(e)[:200]}


@router_combined_dashboard.get("/dashboard/data")
def dashboard_data_endpoint(response: Response):
    """JSON data for the combined dashboard."""
    now = _time.time()
    if _dash_cache["data"] and (now - _dash_cache["ts"]) < _DASH_TTL:
        response.headers["X-Cache"] = "HIT"
        return _dash_cache["data"]

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "nerq": _get_nerq_data(),
        "zarq": _get_zarq_data(),
        "traffic": _get_traffic_data(),
        "scout": _get_scout_data(),
    }
    _dash_cache["data"] = data
    _dash_cache["ts"] = now
    response.headers["X-Cache"] = "MISS"
    response.headers["Cache-Control"] = "public, max-age=300"
    return data


@router_combined_dashboard.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return HTMLResponse(_render_dashboard())


def _render_dashboard() -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>dashboard | nerq + zarq</title>
<meta name="description" content="Combined operations dashboard for Nerq (AI agent index) and ZARQ (crypto risk intelligence).">
<meta name="robots" content="noindex, nofollow">
{NERQ_CSS}
<style>
.dash-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0}}
.dash-card{{border:1px solid #e5e7eb;padding:16px;text-align:center}}
.dash-card .num{{font-family:ui-monospace,'SF Mono',monospace;font-size:1.8rem;font-weight:700;line-height:1.2}}
.dash-card .label{{font-size:12px;color:#6b7280;margin-top:4px}}
.dash-section{{margin:24px 0}}
.dash-section h2{{font-size:1.1rem;font-weight:700;margin-bottom:12px;padding-top:16px;border-top:1px solid #e5e7eb}}
.dash-section:first-child h2{{border-top:none;padding-top:0}}
.mini-table{{width:100%;font-size:13px;border-collapse:collapse}}
.mini-table td{{padding:6px 10px;border-bottom:1px solid #e5e7eb}}
.mini-table td:last-child{{text-align:right;font-family:ui-monospace,'SF Mono',monospace;font-weight:600}}
.trust-bar{{display:flex;height:12px;overflow:hidden;margin:8px 0}}
.trust-bar div{{height:100%}}
.pill{{display:inline-block;padding:1px 8px;font-size:12px;font-weight:600;border:1px solid #e5e7eb}}
.pill-green{{background:#ecfdf5;color:#065f46;border-color:#a7f3d0}}
.pill-yellow{{background:#fffbeb;color:#92400e;border-color:#fde68a}}
.pill-red{{background:#fef2f2;color:#991b1b;border-color:#fecaca}}
.pill-gray{{background:#f9fafb;color:#6b7280;border-color:#e5e7eb}}
.status{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}}
.status-ok{{background:#059669}}
.status-warn{{background:#d97706}}
.status-err{{background:#dc2626}}
@media(max-width:640px){{.dash-grid{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">
<h1>dashboard</h1>
<p class="desc">Combined overview &mdash; nerq (AI assets) + zarq (crypto risk)</p>

<div id="dash-content">
<div style="text-align:center;padding:40px;color:#6b7280">loading...</div>
</div>

</main>
{NERQ_FOOTER}

<script>
async function loadDashboard() {{
  try {{
    const r = await fetch('/dashboard/data');
    const d = await r.json();
    render(d);
  }} catch(e) {{
    document.getElementById('dash-content').innerHTML = '<div style="color:#dc2626;padding:20px">Failed to load dashboard data</div>';
  }}
}}

function fmt(n) {{ return n != null ? Number(n).toLocaleString() : '&mdash;'; }}

function render(d) {{
  const n = d.nerq || {{}};
  const z = d.zarq || {{}};
  const t = d.traffic || {{}};
  const totalAgentsTools = (n.agents||0) + (n.tools||0) + (n.mcp_servers||0);

  let html = '';

  // ── NERQ Section ──
  html += '<div class="dash-section"><h2>nerq &mdash; AI asset intelligence</h2>';
  html += '<div class="dash-grid">';
  html += card(fmt(n.total_assets), 'total assets');
  html += card(fmt(totalAgentsTools), 'agents &amp; tools');
  html += card(fmt(n.models), 'models');
  html += card(fmt(n.datasets), 'datasets');
  html += card(fmt(n.spaces), 'spaces');
  html += card(n.avg_trust ? n.avg_trust + '/100' : '&mdash;', 'avg trust score');
  html += '</div>';
  html += '<div style="font-size:12px;color:#6b7280;margin-top:4px">';
  html += fmt(n.agents) + ' agents &middot; ' + fmt(n.tools) + ' tools &middot; ' + fmt(n.mcp_servers) + ' MCP servers';
  html += '</div>';

  // Trust distribution bar
  const trusted = n.trusted || 0;
  const caution = n.caution || 0;
  const untrusted = n.untrusted || 0;
  const total = trusted + caution + untrusted;
  if (total > 0) {{
    const tPct = (trusted/total*100).toFixed(1);
    const cPct = (caution/total*100).toFixed(1);
    const uPct = (untrusted/total*100).toFixed(1);
    html += '<div style="margin:12px 0">';
    html += '<div style="font-size:13px;color:#6b7280;margin-bottom:4px">trust distribution (agents &amp; tools)</div>';
    html += '<div class="trust-bar">';
    html += '<div style="width:' + tPct + '%;background:#059669" title="Trusted: ' + fmt(trusted) + '"></div>';
    html += '<div style="width:' + cPct + '%;background:#d97706" title="Caution: ' + fmt(caution) + '"></div>';
    html += '<div style="width:' + uPct + '%;background:#dc2626" title="Untrusted: ' + fmt(untrusted) + '"></div>';
    html += '</div>';
    html += '<div style="display:flex;gap:16px;font-size:12px;color:#6b7280;margin-top:4px">';
    html += '<span><span class="pill pill-green">TRUSTED</span> ' + fmt(trusted) + ' (' + tPct + '%)</span>';
    html += '<span><span class="pill pill-yellow">CAUTION</span> ' + fmt(caution) + ' (' + cPct + '%)</span>';
    html += '<span><span class="pill pill-red">UNTRUSTED</span> ' + fmt(untrusted) + ' (' + uPct + '%)</span>';
    html += '</div></div>';
  }}

  // Top categories
  if (n.top_categories) {{
    html += '<div style="margin-top:16px"><div style="font-size:13px;color:#6b7280;margin-bottom:4px">top categories</div>';
    html += '<table class="mini-table">';
    Object.entries(n.top_categories).forEach(([cat, cnt]) => {{
      html += '<tr><td>' + esc(cat) + '</td><td>' + fmt(cnt) + '</td></tr>';
    }});
    html += '</table></div>';
  }}
  html += '</div>';

  // ── Traffic Section ──
  if (t.requests_24h) {{
    html += '<div class="dash-section"><h2>traffic &mdash; all endpoints (24h)</h2>';
    html += '<div class="dash-grid">';
    html += card(fmt(t.requests_24h), 'requests (24h)');
    html += card(fmt(t.unique_ips_24h), 'unique IPs');
    html += card(t.p50_ms + 'ms', 'p50 latency');
    html += card(t.p95_ms + 'ms', 'p95 latency');
    html += '</div>';

    if (t.top_nerq_endpoints && t.top_nerq_endpoints.length) {{
      html += '<div style="margin-top:12px"><div style="font-size:13px;color:#6b7280;margin-bottom:4px">top nerq endpoints</div>';
      html += '<table class="mini-table">';
      t.top_nerq_endpoints.forEach(ep => {{
        html += '<tr><td><code>' + esc(ep.endpoint) + '</code></td><td>' + fmt(ep.count) + '</td></tr>';
      }});
      html += '</table></div>';
    }}

    if (t.ai_bot_crawls && Object.keys(t.ai_bot_crawls).length) {{
      html += '<div style="margin-top:12px"><div style="font-size:13px;color:#6b7280;margin-bottom:4px">AI &amp; search bot crawls</div>';
      html += '<table class="mini-table">';
      Object.entries(t.ai_bot_crawls).forEach(([bot, cnt]) => {{
        html += '<tr><td>' + esc(bot) + '</td><td>' + fmt(cnt) + '</td></tr>';
      }});
      html += '</table></div>';
    }}
    html += '</div>';
  }}

  // ── Scout Section ──
  const s = d.scout || {{}};
  html += '<div class="dash-section"><h2>scout &mdash; autonomous agent discovery</h2>';

  // Status row
  const lastRun = s.last_run ? new Date(s.last_run).toLocaleString() : '&mdash;';
  const nextRun = s.next_run ? new Date(s.next_run).toLocaleString() : '&mdash;';
  html += '<div style="font-size:13px;color:#6b7280;margin-bottom:12px">';
  html += '<span class="status status-ok"></span> Last run: ' + lastRun;
  html += ' &middot; Next: ' + nextRun;
  html += '</div>';

  html += '<div class="dash-grid">';
  html += card(fmt(s.evaluated_total || 0), 'agents evaluated');
  html += card(fmt(s.featured_total || 0), 'agents featured');
  html += card(fmt(s.blog_posts || 0), 'blog posts');
  html += card(fmt(s.bluesky_posts || 0), 'bluesky posts');
  html += card(fmt(s.devto_articles || 0), 'dev.to articles');
  html += card(fmt(s.claimed || 0), 'claimed');
  html += card(fmt(s.reviews_total || 0), 'reviews');
  html += '</div>';

  // Last 5 evaluated
  if (s.last_5_evaluated && s.last_5_evaluated.length) {{
    html += '<div style="margin-top:12px"><div style="font-size:13px;color:#6b7280;margin-bottom:4px">last evaluated</div>';
    html += '<table class="mini-table"><thead style="font-size:12px;color:#6b7280"><tr><td>agent</td><td>score</td><td>grade</td></tr></thead>';
    s.last_5_evaluated.forEach(a => {{
      const sc = a.trust_score ? a.trust_score.toFixed(1) : '&mdash;';
      const gr = a.grade || '&mdash;';
      const pillCls = a.trust_score >= 70 ? 'pill-green' : a.trust_score >= 40 ? 'pill-yellow' : 'pill-red';
      html += '<tr><td><a href="/trust/' + esc(a.name) + '">' + esc(a.name) + '</a></td>';
      html += '<td>' + sc + '</td>';
      html += '<td><span class="pill ' + pillCls + '">' + esc(gr) + '</span></td></tr>';
    }});
    html += '</table></div>';
  }}
  html += '</div>';

  // ── ZARQ Section ──
  html += '<div class="dash-section"><h2>zarq &mdash; crypto risk intelligence</h2>';
  if (!z.available) {{
    html += '<p style="color:#6b7280;font-size:14px">ZARQ data not available. <a href="https://zarq.ai">zarq.ai</a></p>';
  }} else {{
    html += '<div class="dash-grid">';
    html += card(fmt(z.total_tokens), 'tokens rated');
    html += card(fmt(z.active_warnings), 'active warnings');
    html += card(fmt(z.crash_shield_saves), 'crash shield saves');
    html += card(z.latest_date || '&mdash;', 'latest data');
    html += '</div>';

    // Risk distribution
    if (z.risk_distribution) {{
      html += '<div style="margin-top:12px"><div style="font-size:13px;color:#6b7280;margin-bottom:4px">risk distribution</div>';
      html += '<table class="mini-table">';
      Object.entries(z.risk_distribution).forEach(([level, cnt]) => {{
        const pillClass = level === 'SAFE' ? 'pill-green' : level === 'WARNING' ? 'pill-yellow' : level === 'CRITICAL' ? 'pill-red' : 'pill-gray';
        html += '<tr><td><span class="pill ' + pillClass + '">' + esc(level) + '</span></td><td>' + fmt(cnt) + '</td></tr>';
      }});
      html += '</table></div>';
    }}

    // Rating distribution
    if (z.ratings) {{
      html += '<div style="margin-top:12px"><div style="font-size:13px;color:#6b7280;margin-bottom:4px">ratings</div>';
      html += '<table class="mini-table">';
      Object.entries(z.ratings).forEach(([rating, cnt]) => {{
        html += '<tr><td>' + esc(rating) + '</td><td>' + fmt(cnt) + '</td></tr>';
      }});
      html += '</table></div>';
    }}
  }}
  html += '</div>';

  // ── Meta ──
  html += '<div style="font-size:12px;color:#6b7280;margin-top:24px;padding-top:12px;border-top:1px solid #e5e7eb">';
  html += 'generated: ' + (d.generated_at || 'unknown') + ' &middot; refreshes every 60s &middot; ';
  html += '<a href="/dashboard/data">json</a> &middot; ';
  html += '<a href="/report/q1-2026">state of AI assets report</a> &middot; ';
  html += '<a href="/zarq/dashboard">zarq ops dashboard</a>';
  html += '</div>';

  document.getElementById('dash-content').innerHTML = html;
}}

function card(num, label) {{
  return '<div class="dash-card"><div class="num">' + num + '</div><div class="label">' + label + '</div></div>';
}}

function esc(s) {{ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') : ''; }}

loadDashboard();
setInterval(loadDashboard, 60000);
</script>
</body>
</html>"""
