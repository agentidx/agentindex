"""
Intelligence API & Dashboard Pages — Sprint 4
===============================================
Endpoints:
  GET /v1/intelligence/trending            — Ecosystem trends
  GET /v1/intelligence/agent/{name}/dashboard — Agent dashboard data
  GET /v1/intelligence/report/latest       — Latest weekly report
  GET /dashboard                           — Dashboard hub page
  GET /dashboard/{agent}                   — Individual agent dashboard
  GET /trends                              — Trending agents page
  GET /security                            — Security overview page
  GET /reports                             — Report archive page

Usage in discovery.py:
    from agentindex.intelligence_api import mount_intelligence
    mount_intelligence(app)
"""

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER, nerq_page

logger = logging.getLogger("nerq.intelligence")

SQLITE_DB = Path(__file__).parent / "crypto" / "crypto_trust.db"
REPORTS_DIR = Path(__file__).parent.parent / "docs" / "auto-reports"


def _get_trending_data():
    """Pull trending data from agent_trends table."""
    if not SQLITE_DB.exists():
        return {"trending": [], "alerts": [], "frameworks": []}

    conn = sqlite3.connect(str(SQLITE_DB), timeout=5)
    try:
        # Rising agents
        trending = conn.execute("""
            SELECT agent_name, trend_type, direction, magnitude, details
            FROM agent_trends
            WHERE direction = 'rising' AND detected_at > datetime('now', '-7 days')
            ORDER BY magnitude DESC
            LIMIT 20
        """).fetchall()

        # Security alerts
        alerts = conn.execute("""
            SELECT agent_name, details
            FROM agent_trends
            WHERE trend_type = 'security_alert' AND detected_at > datetime('now', '-7 days')
            ORDER BY magnitude DESC
            LIMIT 10
        """).fetchall()

        # Framework momentum
        frameworks = conn.execute("""
            SELECT agent_name, magnitude, details
            FROM agent_trends
            WHERE trend_type = 'framework_shift' AND detected_at > datetime('now', '-7 days')
            ORDER BY magnitude DESC
            LIMIT 15
        """).fetchall()

        # New entrants
        new_entrants = conn.execute("""
            SELECT agent_name, magnitude, details
            FROM agent_trends
            WHERE trend_type = 'new_entrant' AND detected_at > datetime('now', '-7 days')
            ORDER BY magnitude DESC
            LIMIT 10
        """).fetchall()

        return {
            "trending": [{"name": r[0], "type": r[1], "direction": r[2],
                          "magnitude": r[3], "details": json.loads(r[4]) if r[4] else {}}
                         for r in trending],
            "alerts": [{"name": r[0], "details": json.loads(r[1]) if r[1] else {}}
                       for r in alerts],
            "frameworks": [{"framework": r[0], "agent_count": int(r[1]),
                           "details": json.loads(r[2]) if r[2] else {}}
                          for r in frameworks],
            "new_entrants": [{"name": r[0], "trust_score": r[1],
                             "details": json.loads(r[2]) if r[2] else {}}
                            for r in new_entrants],
        }
    except Exception as e:
        logger.warning(f"Trending data error: {e}")
        return {"trending": [], "alerts": [], "frameworks": [], "new_entrants": []}
    finally:
        conn.close()


def _get_dashboard_data(agent_name):
    """Get dashboard data from SQLite."""
    if not SQLITE_DB.exists():
        return None
    conn = sqlite3.connect(str(SQLITE_DB), timeout=5)
    try:
        row = conn.execute("""
            SELECT trust_score_history, preflight_checks_7d, preflight_checks_30d,
                   page_views_7d, badge_displays_7d, category_rank, category_total,
                   category_avg_trust, updated_at
            FROM agent_dashboard
            WHERE agent_name = ? OR agent_name LIKE ?
            LIMIT 1
        """, (agent_name, f"%{agent_name}%")).fetchone()
        if not row:
            return None
        return {
            "trust_history": json.loads(row[0]) if row[0] else [],
            "preflight_7d": row[1] or 0,
            "preflight_30d": row[2] or 0,
            "page_views_7d": row[3] or 0,
            "badge_displays_7d": row[4] or 0,
            "category_rank": row[5],
            "category_total": row[6],
            "category_avg_trust": row[7],
        }
    except Exception:
        return None
    finally:
        conn.close()


def _get_latest_report():
    """Get the most recent weekly report JSON."""
    if not REPORTS_DIR.exists():
        return None
    json_files = sorted(REPORTS_DIR.glob("report-week-*.json"), reverse=True)
    if not json_files:
        return None
    try:
        return json.loads(json_files[0].read_text())
    except Exception:
        return None


def mount_intelligence(app):

    # ═══════════════════════════════════════════════════════════
    # GET /v1/intelligence/trending
    # ═══════════════════════════════════════════════════════════

    @app.get("/v1/intelligence/trending")
    def trending_endpoint(period: str = Query("7d")):
        t0 = time.time()

        data = _get_trending_data()

        # Ecosystem stats
        session = get_session()
        try:
            total = session.execute(text("SELECT COUNT(*) FROM agents WHERE is_active = true")).scalar() or 0
            avg_trust = session.execute(text(
                "SELECT AVG(COALESCE(trust_score_v2, trust_score)) FROM agents WHERE is_active = true"
            )).scalar() or 0
        finally:
            session.close()

        conn = sqlite3.connect(str(SQLITE_DB), timeout=3)
        try:
            cve_total = conn.execute("SELECT COUNT(*) FROM agent_vulnerabilities").fetchone()[0]
            licensed = conn.execute("SELECT COUNT(DISTINCT agent_name) FROM agent_licenses").fetchone()[0]
            fw_total = conn.execute("SELECT COUNT(DISTINCT framework) FROM agent_frameworks").fetchone()[0]
        except Exception:
            cve_total = licensed = fw_total = 0
        finally:
            conn.close()

        pct_cves = round(cve_total / max(total, 1) * 100, 1)
        pct_licensed = round(licensed / max(total, 1) * 100, 1)

        result = {
            "period": period,
            "trending_agents": data["trending"][:10],
            "security_alerts": data["alerts"][:5],
            "framework_momentum": data["frameworks"][:10],
            "new_entrants": data.get("new_entrants", [])[:5],
            "ecosystem_stats": {
                "total_agents": total,
                "avg_trust_score": round(float(avg_trust), 1),
                "pct_with_cves": pct_cves,
                "pct_with_license": pct_licensed,
                "total_frameworks_tracked": fw_total,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "response_time_ms": round((time.time() - t0) * 1000, 1),
        }

        return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=300"})

    # ═══════════════════════════════════════════════════════════
    # GET /v1/intelligence/agent/{name}/dashboard
    # ═══════════════════════════════════════════════════════════

    @app.get("/v1/intelligence/agent/{agent_name}/dashboard")
    def agent_dashboard_api(agent_name: str):
        t0 = time.time()
        session = get_session()
        try:
            row = session.execute(text("""
                SELECT name, COALESCE(trust_score_v2, trust_score) as ts,
                       trust_grade, category, stars, is_verified
                FROM (
                    SELECT *, 1 AS _r FROM agents WHERE LOWER(name) = LOWER(:name) AND is_active = true
                  UNION ALL
                    SELECT *, 2 AS _r FROM agents WHERE lower(name) LIKE lower(:pattern) AND is_active = true
                ) sub
                ORDER BY _r ASC, COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
                LIMIT 1
            """), {"name": agent_name, "pattern": f"%{agent_name}%"}).fetchone()

            if not row:
                return JSONResponse(status_code=404, content={"error": f"Agent '{agent_name}' not found"})

            d = dict(row._mapping)
            name = d["name"]
            trust = float(d.get("ts") or 0)
        finally:
            session.close()

        dash = _get_dashboard_data(name)
        if not dash:
            dash = {"trust_history": [], "preflight_7d": 0, "preflight_30d": 0,
                    "page_views_7d": 0, "badge_displays_7d": 0,
                    "category_rank": None, "category_total": None, "category_avg_trust": None}

        above_avg = round(trust - (dash.get("category_avg_trust") or trust), 1)

        from agentindex.agent_safety_pages import _make_slug
        slug = _make_slug(name)

        result = {
            "agent": name,
            "trust_score": round(trust, 1),
            "grade": d.get("trust_grade"),
            "category": d.get("category"),
            "category_rank": dash.get("category_rank"),
            "category_total": dash.get("category_total"),
            "category_avg_trust": dash.get("category_avg_trust"),
            "above_average_by": above_avg,
            "trust_history_30d": dash.get("trust_history", [])[-30:],
            "preflight_checks": {
                "last_7d": dash.get("preflight_7d", 0),
                "last_30d": dash.get("preflight_30d", 0),
            },
            "page_views_7d": dash.get("page_views_7d", 0),
            "badge_displays_7d": dash.get("badge_displays_7d", 0),
            "embed_badge": f"[![Nerq Trust](https://nerq.ai/badge/{slug}.svg)](https://nerq.ai/safe/{slug})",
            "details_url": f"https://nerq.ai/safe/{slug}",
            "dashboard_url": f"https://nerq.ai/dashboard/{slug}",
            "response_time_ms": round((time.time() - t0) * 1000, 1),
        }

        return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=300"})

    # ═══════════════════════════════════════════════════════════
    # GET /v1/intelligence/report/latest
    # ═══════════════════════════════════════════════════════════

    @app.get("/v1/intelligence/report/latest")
    def latest_report_api():
        report = _get_latest_report()
        if not report:
            return JSONResponse(status_code=404, content={"error": "No reports available yet"})
        return JSONResponse(content=report, headers={"Cache-Control": "public, max-age=3600"})

    # ═══════════════════════════════════════════════════════════
    # /dashboard — Hub page
    # ═══════════════════════════════════════════════════════════

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard_hub(request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        session = get_session()
        try:
            top_agents = session.execute(text("""
                SELECT name, COALESCE(trust_score_v2, trust_score) as ts, trust_grade, category, stars
                FROM agents WHERE is_active = true AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
                ORDER BY stars DESC NULLS LAST
                LIMIT 20
            """)).fetchall()
        finally:
            session.close()

        from agentindex.agent_safety_pages import _make_slug
        rows = ""
        for r in top_agents:
            d = dict(r._mapping)
            slug = _make_slug(d["name"])
            rows += f'<tr><td><a href="/dashboard/{slug}">{d["name"]}</a></td><td>{float(d.get("ts") or 0):.0f}</td><td>{d.get("trust_grade", "N/A")}</td><td>{d.get("category", "—")}</td><td>{(d.get("stars") or 0):,}</td></tr>'

        body = f"""<h1>AI Agent Developer Dashboards</h1>
<p class="desc">Track your agent's trust score, analytics, and improvement recommendations. Public dashboards for all indexed agents.</p>

<div class="search-box" style="max-width:500px">
<input type="text" id="agent-input" placeholder="Find your agent's dashboard..." autofocus>
<button onclick="window.location.href='/dashboard/'+document.getElementById('agent-input').value.toLowerCase().replace(/[\\s\\/]+/g,'-')">View Dashboard</button>
</div>

<h2>Most Popular Agents</h2>
<table><thead><tr><th>Agent</th><th>Trust</th><th>Grade</th><th>Category</th><th>Stars</th></tr></thead>
<tbody>{rows}</tbody></table>

<script>
document.getElementById('agent-input').addEventListener('keydown', e => {{
    if (e.key === 'Enter') {{
        const v = document.getElementById('agent-input').value.trim().toLowerCase().replace(/[\\s\\/]+/g, '-');
        if (v) window.location.href = '/dashboard/' + v;
    }}
}});
</script>"""

        return HTMLResponse(nerq_page(
            "AI Agent Developer Dashboards — Track Your Trust Score | Nerq",
            body,
            "Track your AI agent's trust score, preflight checks, and improvement recommendations. Free public dashboards for 200K+ agents.",
            "https://nerq.ai/dashboard"
        ))

    # ═══════════════════════════════════════════════════════════
    # /dashboard/{agent} — Individual agent dashboard
    # ═══════════════════════════════════════════════════════════

    @app.get("/dashboard/{agent_slug}", response_class=HTMLResponse)
    def agent_dashboard_page(agent_slug: str, request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        from agentindex.agent_safety_pages import _SLUG_OVERRIDES, _make_slug
        override = _SLUG_OVERRIDES.get(agent_slug.lower())
        lookup_name = override or agent_slug

        session = get_session()
        try:
            row = session.execute(text("""
                SELECT name, COALESCE(trust_score_v2, trust_score) as ts,
                       trust_grade, category, stars, description, source_url
                FROM (
                    SELECT *, 1 AS _r FROM agents WHERE LOWER(name) = LOWER(:name) AND is_active = true
                  UNION ALL
                    SELECT *, 2 AS _r FROM agents WHERE lower(name) LIKE lower(:pattern) AND is_active = true
                ) sub
                ORDER BY _r ASC, COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
                LIMIT 1
            """), {"name": lookup_name, "pattern": f"%{lookup_name}%"}).fetchone()

            if not row:
                return HTMLResponse(status_code=404, content=nerq_page(
                    "Agent Not Found | Nerq",
                    f'<h1>Agent Not Found</h1><p>No agent matching "{agent_slug}". <a href="/dashboard">Search dashboards</a>.</p>'
                ))

            d = dict(row._mapping)
        finally:
            session.close()

        name = d["name"]
        trust = float(d.get("ts") or 0)
        grade = d.get("trust_grade") or "N/A"
        slug = _make_slug(name)

        dash = _get_dashboard_data(name)
        if not dash:
            dash = {"trust_history": [], "category_rank": None, "category_total": None,
                    "category_avg_trust": None, "preflight_7d": 0, "badge_displays_7d": 0}

        rank_text = f"#{dash['category_rank']} of {dash['category_total']}" if dash.get("category_rank") else "N/A"
        above_avg = round(trust - (dash.get("category_avg_trust") or trust), 1)
        above_text = f"+{above_avg}" if above_avg > 0 else f"{above_avg}" if above_avg < 0 else "±0"

        verified = '<span class="pill pill-green">Nerq Verified</span>' if trust >= 70 else ""

        # Sparkline from trust history
        history = dash.get("trust_history", [])
        spark_data = json.dumps([h.get("score", 0) for h in history[-30:]])

        body = f"""<div class="breadcrumb"><a href="/dashboard">Dashboards</a> / {name}</div>
<h1>{name} Developer Dashboard {verified}</h1>
<p class="desc">{(d.get('description') or '')[:200]}</p>

<div class="stat-row">
<div class="stat-item"><div class="num" style="color:#0d9488">{trust:.0f}</div><div class="label">Trust Score ({grade})</div></div>
<div class="stat-item"><div class="num">{rank_text}</div><div class="label">Category Rank ({d.get('category', 'N/A')})</div></div>
<div class="stat-item"><div class="num">{above_text}</div><div class="label">vs Category Avg</div></div>
<div class="stat-item"><div class="num">{(d.get('stars') or 0):,}</div><div class="label">GitHub Stars</div></div>
</div>

<h2>Trust Score History</h2>
<div id="sparkline" style="height:60px;background:#f9fafb;border:1px solid #e5e7eb;padding:8px;margin-bottom:16px;display:flex;align-items:flex-end;gap:2px"></div>

<h2>Embed Trust Badge</h2>
<p class="desc">Add this badge to your README to show your trust score:</p>
<pre style="user-select:all">[![Nerq Trust Score](https://nerq.ai/badge/{slug}.svg)](https://nerq.ai/safe/{slug})</pre>

<h2>Links</h2>
<ul style="font-size:14px;line-height:2">
<li><a href="/safe/{slug}">Full Safety Report</a></li>
<li><a href="/v1/preflight?target={name}">Preflight Check (API)</a></li>
<li><a href="/v1/economics/{name}">Economics Data (API)</a></li>
<li><a href="/v1/improve/{name}">Improvement Plan (API)</a></li>
<li><a href="/v1/intelligence/agent/{name}/dashboard">Dashboard Data (API)</a></li>
</ul>

<script>
const data = {spark_data};
const el = document.getElementById('sparkline');
if (data.length > 1) {{
    const max = Math.max(...data);
    const min = Math.min(...data);
    const range = max - min || 1;
    data.forEach(v => {{
        const bar = document.createElement('div');
        const h = Math.max(4, ((v - min) / range) * 48);
        bar.style.cssText = `flex:1;background:#0d9488;min-width:3px;height:${{h}}px;opacity:0.7`;
        bar.title = v.toFixed(1);
        el.appendChild(bar);
    }});
}} else {{
    el.innerHTML = '<span style="color:#6b7280;font-size:13px;padding:16px">History will appear after multiple data points are collected.</span>';
}}
</script>"""

        return HTMLResponse(nerq_page(
            f"{name} Developer Dashboard — Trust Score, Analytics & Improvements | Nerq",
            body,
            f"{name} developer dashboard: trust score {trust:.0f}/100 ({grade}), category rank {rank_text}, improvement recommendations.",
            f"https://nerq.ai/dashboard/{slug}"
        ))

    # ═══════════════════════════════════════════════════════════
    # /trends — Trending agents page
    # ═══════════════════════════════════════════════════════════

    @app.get("/trends", response_class=HTMLResponse)
    def trends_page(request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        data = _get_trending_data()
        from agentindex.agent_safety_pages import _make_slug

        def _trend_rows(items, show_field="magnitude"):
            if not items:
                return "<p style='color:#6b7280;font-size:13px'>No data for this period yet.</p>"
            rows = ""
            for item in items[:15]:
                name = item.get("name", "")
                slug = _make_slug(name)
                details = item.get("details", {})
                score = details.get("trust_score", item.get("trust_score", ""))
                stars = details.get("stars", "")
                rows += f'<tr><td><a href="/dashboard/{slug}">{name}</a></td><td>{score}</td><td>{stars}</td></tr>'
            return f"<table><thead><tr><th>Agent</th><th>Trust Score</th><th>Stars</th></tr></thead><tbody>{rows}</tbody></table>"

        faq = json.dumps({
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": "What AI agents are trending?",
                 "acceptedAnswer": {"@type": "Answer", "text": "Nerq tracks trending AI agents based on trust score changes, GitHub star growth, and npm download increases. Visit nerq.ai/trends for the latest data."}},
                {"@type": "Question", "name": "Which AI agents are growing fastest?",
                 "acceptedAnswer": {"@type": "Answer", "text": "The fastest-growing AI agents are tracked by Nerq's trend detector, which monitors trust scores, popularity metrics, and framework adoption across 200K+ agents."}},
            ]
        })

        body = f"""<h1>Trending AI Agents 2026</h1>
<p class="desc">Live data from Nerq's trend detector. Updated daily from 200K+ indexed agents.</p>

<h2>Rising This Week</h2>
{_trend_rows(data.get('trending', []))}

<h2>New Entrants</h2>
{_trend_rows(data.get('new_entrants', []))}

<h2>Security Alerts</h2>
{_trend_rows(data.get('alerts', []))}

<h2>Framework Momentum</h2>
"""
        fw_rows = ""
        for fw in data.get("frameworks", [])[:10]:
            fw_rows += f'<tr><td><a href="/framework/{fw["framework"]}">{fw["framework"]}</a></td><td>{fw.get("agent_count", 0)}</td></tr>'
        if fw_rows:
            body += f"<table><thead><tr><th>Framework</th><th>Agents</th></tr></thead><tbody>{fw_rows}</tbody></table>"
        else:
            body += "<p style='color:#6b7280;font-size:13px'>No framework data yet.</p>"

        body += f'<script type="application/ld+json">{faq}</script>'

        return HTMLResponse(nerq_page(
            "Trending AI Agents 2026 — Rising, Declining & New Agents | Nerq",
            body,
            "Discover trending AI agents: rising trust scores, new entrants, security alerts, and framework adoption. Updated daily.",
            "https://nerq.ai/trends"
        ))

    # ═══════════════════════════════════════════════════════════
    # /security — Security overview page
    # ═══════════════════════════════════════════════════════════

    @app.get("/security", response_class=HTMLResponse)
    def security_page(request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        conn = sqlite3.connect(str(SQLITE_DB), timeout=5)
        try:
            total_cves = conn.execute("SELECT COUNT(*) FROM agent_vulnerabilities").fetchone()[0]
            by_severity = conn.execute(
                "SELECT severity, COUNT(*) FROM agent_vulnerabilities GROUP BY severity ORDER BY COUNT(*) DESC"
            ).fetchall()
            recent = conn.execute("""
                SELECT agent_name, cve_id, severity, description
                FROM agent_vulnerabilities
                ORDER BY cve_id DESC LIMIT 10
            """).fetchall()
            affected = conn.execute(
                "SELECT COUNT(DISTINCT agent_name) FROM agent_vulnerabilities"
            ).fetchone()[0]
        except Exception:
            total_cves = affected = 0
            by_severity = []
            recent = []
        finally:
            conn.close()

        sev_rows = ""
        for s, c in by_severity:
            color = {"CRITICAL": "pill-red", "HIGH": "pill-red", "MEDIUM": "pill-yellow", "LOW": "pill-green"}.get(s, "pill-gray")
            sev_rows += f'<tr><td><span class="pill {color}">{s}</span></td><td>{c}</td></tr>'

        from agentindex.agent_safety_pages import _make_slug
        recent_rows = ""
        for r in recent:
            slug = _make_slug(r[0])
            recent_rows += f'<tr><td><a href="/safe/{slug}">{r[0]}</a></td><td>{r[1]}</td><td>{r[2]}</td><td>{(r[3] or "")[:100]}</td></tr>'

        body = f"""<h1>AI Agent Security Report 2026</h1>
<p class="desc">Continuous security monitoring across 200K+ AI agents. CVE tracking, vulnerability analysis, and trust impact assessment.</p>

<div class="stat-row">
<div class="stat-item"><div class="num">{total_cves}</div><div class="label">Known CVEs</div></div>
<div class="stat-item"><div class="num">{affected}</div><div class="label">Affected Agents</div></div>
</div>

<h2>Severity Distribution</h2>
<table><thead><tr><th>Severity</th><th>Count</th></tr></thead><tbody>{sev_rows}</tbody></table>

<h2>Recent CVEs</h2>
<table><thead><tr><th>Agent</th><th>CVE</th><th>Severity</th><th>Description</th></tr></thead>
<tbody>{recent_rows}</tbody></table>

<div class="search-box" style="max-width:500px;margin-top:24px">
<input type="text" id="agent-input" placeholder="Check any agent for vulnerabilities...">
<button onclick="window.location.href='/safe/'+document.getElementById('agent-input').value.toLowerCase().replace(/[\\s\\/]+/g,'-')">Check</button>
</div>

<script>
document.getElementById('agent-input').addEventListener('keydown', e => {{
    if (e.key === 'Enter') {{
        const v = document.getElementById('agent-input').value.trim().toLowerCase().replace(/[\\s\\/]+/g, '-');
        if (v) window.location.href = '/safe/' + v;
    }}
}});
</script>"""

        return HTMLResponse(nerq_page(
            "AI Agent Security Report 2026 — CVEs, Vulnerabilities & Trust | Nerq",
            body,
            "Comprehensive security monitoring for AI agents: CVE tracking, vulnerability analysis, and trust impact across 200K+ agents.",
            "https://nerq.ai/security"
        ))

    # ═══════════════════════════════════════════════════════════
    # /reports — Report archive page
    # ═══════════════════════════════════════════════════════════

    @app.get("/reports", response_class=HTMLResponse)
    def reports_page(request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        # List all report files
        reports = []
        if REPORTS_DIR.exists():
            for f in sorted(REPORTS_DIR.glob("*-weekly.md"), reverse=True):
                name = f.stem
                # Parse date from filename
                date_str = name[:10] if len(name) >= 10 else name
                reports.append({"filename": name, "date": date_str, "path": str(f)})

        latest = _get_latest_report()

        latest_section = ""
        if latest:
            latest_section = f"""<div class="card" style="margin-bottom:20px">
<h2 style="border:none;padding:0;margin:0 0 8px">Latest: Week {latest.get('week', '?')}, {latest.get('year', '?')}</h2>
<div class="stat-row">
<div class="stat-item"><div class="num">{latest.get('ecosystem', {}).get('total_agents', 0):,}</div><div class="label">Agents</div></div>
<div class="stat-item"><div class="num">{latest.get('ecosystem', {}).get('avg_trust_score', 0)}</div><div class="label">Avg Trust</div></div>
<div class="stat-item"><div class="num">{latest.get('security', {}).get('total_cves', 0)}</div><div class="label">CVEs</div></div>
<div class="stat-item"><div class="num">{latest.get('ecosystem', {}).get('new_agents_7d', 0)}</div><div class="label">New This Week</div></div>
</div>
<p style="margin-top:8px;font-size:13px"><a href="{latest.get('report_url', '#')}">Read full report &rarr;</a> &middot; <a href="/v1/intelligence/report/latest">API (JSON)</a></p>
</div>"""

        report_list = ""
        for r in reports[:20]:
            report_list += f'<li style="padding:4px 0"><a href="/blog/{r["filename"]}">{r["date"]}</a></li>'

        body = f"""<h1>State of the Agent Economy — Weekly Reports</h1>
<p class="desc">Weekly analysis of the AI agent ecosystem. Trust scores, CVEs, framework adoption, and pricing trends.</p>

{latest_section}

<h2>Report Archive</h2>
<ul style="font-size:14px">{report_list or '<li>No reports yet. First report generates on Monday.</li>'}</ul>

<p style="margin-top:20px;font-size:13px;color:#6b7280">
Reports are auto-generated every Monday by Nerq Intelligence and published to blog, Dev.to, and Bluesky.
<a href="/feed.xml">RSS feed</a>
</p>"""

        return HTMLResponse(nerq_page(
            "State of the Agent Economy — Weekly Reports | Nerq",
            body,
            "Weekly analysis of the AI agent ecosystem: trust scores, CVEs, framework adoption, pricing trends across 200K+ agents.",
            "https://nerq.ai/reports"
        ))

    logger.info("Mounted intelligence: /v1/intelligence/trending, /dashboard, /trends, /security, /reports")
