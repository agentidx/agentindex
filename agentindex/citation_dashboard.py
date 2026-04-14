"""
Citation Dashboard — Verified AI Citation Metrics
===================================================
Shows ONLY data we trust. No misleading aggregations.
URL: /citation-dashboard

Principles:
- user_triggered = someone asked an AI a question → real citation
- search_index = AI building its index → leading indicator
- training = LLM training data → unknown value
- These are NEVER mixed into a single "AI citations" number
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, date, timedelta
from fastapi.responses import HTMLResponse

logger = logging.getLogger("nerq.citation_dashboard")

ANALYTICS_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "analytics.db")
FRESHNESS_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "freshness-regenerated.jsonl")

_cache = {}
CACHE_TTL = 300  # 5 minutes


def _esc(s):
    import html
    return html.escape(str(s)) if s else ""


def _get_data():
    """Fetch all dashboard data from analytics.db."""
    conn = sqlite3.connect(ANALYTICS_DB, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    d = {}

    # ── Section 1: User-triggered daily (30d) ──
    d["ut_daily"] = conn.execute("""
        SELECT date(ts) as day,
          SUM(CASE WHEN bot_name='ChatGPT' THEN 1 ELSE 0 END) as chatgpt,
          SUM(CASE WHEN bot_name='Perplexity' THEN 1 ELSE 0 END) as perplexity,
          SUM(CASE WHEN bot_name='DuckDuckGo AI' THEN 1 ELSE 0 END) as duckassist,
          SUM(CASE WHEN bot_name='You.com' THEN 1 ELSE 0 END) as youbot,
          SUM(CASE WHEN bot_name='Claude' THEN 1 ELSE 0 END) as claude,
          SUM(CASE WHEN bot_name='Doubao' THEN 1 ELSE 0 END) as doubao,
          SUM(CASE WHEN bot_name='Mistral' THEN 1 ELSE 0 END) as mistral,
          SUM(CASE WHEN bot_name='Manus' THEN 1 ELSE 0 END) as manus,
          COUNT(*) as total
        FROM requests
        WHERE bot_purpose='user_triggered' AND ts >= date('now', '-30 days')
        GROUP BY day ORDER BY day
    """).fetchall()

    # ── Section 1: Top URLs per bot (7d) ──
    d["ut_top_urls"] = conn.execute("""
        SELECT bot_name, path, COUNT(*) as cnt
        FROM requests
        WHERE bot_purpose='user_triggered' AND ts >= date('now', '-7 days')
        GROUP BY bot_name, path
        ORDER BY bot_name, cnt DESC
    """).fetchall()

    # ── Section 1: Concentration ──
    d["ut_concentration"] = conn.execute("""
        SELECT bot_name, COUNT(*) as cnt
        FROM requests
        WHERE bot_purpose='user_triggered' AND ts >= date('now', '-7 days')
        GROUP BY bot_name ORDER BY cnt DESC
    """).fetchall()

    # ── Section 2: Search-index daily (30d) ──
    d["si_daily"] = conn.execute("""
        SELECT date(ts) as day,
          SUM(CASE WHEN user_agent LIKE '%OAI-SearchBot%' THEN 1 ELSE 0 END) as oai_search,
          SUM(CASE WHEN bot_name='Apple' THEN 1 ELSE 0 END) as apple,
          SUM(CASE WHEN bot_name='Perplexity' AND bot_purpose='search_index' THEN 1 ELSE 0 END) as pplx_index,
          SUM(CASE WHEN bot_name='Bing' THEN 1 ELSE 0 END) as bing,
          SUM(CASE WHEN bot_name='Google' THEN 1 ELSE 0 END) as google
        FROM requests
        WHERE ts >= date('now', '-30 days')
          AND (bot_purpose='search_index' OR user_agent LIKE '%OAI-SearchBot%')
        GROUP BY day ORDER BY day
    """).fetchall()

    # ── Section 3: Pilot 1 — /was-X-hacked ──
    d["pilot1_daily"] = conn.execute("""
        SELECT date(ts) as day,
          SUM(CASE WHEN bot_purpose='user_triggered' THEN 1 ELSE 0 END) as user_triggered,
          SUM(CASE WHEN user_agent LIKE '%OAI-SearchBot%' THEN 1 ELSE 0 END) as oai_search,
          SUM(CASE WHEN bot_name='Apple' THEN 1 ELSE 0 END) as apple
        FROM requests
        WHERE path LIKE '/was-%-hacked' AND ts >= '2026-04-13'
        GROUP BY day ORDER BY day
    """).fetchall()

    d["pilot1_total_ut"] = conn.execute("""
        SELECT COUNT(*) FROM requests
        WHERE bot_purpose='user_triggered' AND path LIKE '/was-%-hacked' AND ts >= '2026-04-13'
    """).fetchone()[0]

    d["pilot1_oai_first"] = conn.execute("""
        SELECT MIN(ts) FROM requests
        WHERE user_agent LIKE '%OAI-SearchBot%' AND path LIKE '/was-%-hacked' AND ts >= '2026-04-13'
    """).fetchone()[0]

    # ── Section 4: ChatGPT-User growth (full history) ──
    d["chatgpt_growth"] = conn.execute("""
        SELECT date(ts) as day, COUNT(*) as cnt
        FROM requests
        WHERE bot_name='ChatGPT' AND bot_purpose='user_triggered'
        GROUP BY day ORDER BY day
    """).fetchall()

    # ── Section 5: Applebot language dist (7d) ──
    d["apple_langs"] = conn.execute("""
        SELECT
          CASE
            WHEN path LIKE '/de/%' THEN 'de' WHEN path LIKE '/es/%' THEN 'es'
            WHEN path LIKE '/fr/%' THEN 'fr' WHEN path LIKE '/ja/%' THEN 'ja'
            WHEN path LIKE '/it/%' THEN 'it' WHEN path LIKE '/pt/%' THEN 'pt'
            WHEN path LIKE '/ko/%' THEN 'ko' WHEN path LIKE '/sv/%' THEN 'sv'
            WHEN path LIKE '/zh/%' THEN 'zh' WHEN path LIKE '/ar/%' THEN 'ar'
            ELSE 'en+other'
          END as lang, COUNT(*) as cnt
        FROM requests
        WHERE bot_name='Apple' AND ts >= date('now', '-7 days')
        GROUP BY lang ORDER BY cnt DESC LIMIT 12
    """).fetchall()

    # ── Section 6: Referral traffic (30d) ──
    d["referrals"] = conn.execute("""
        SELECT date(ts) as day,
          SUM(CASE WHEN referrer_domain LIKE '%google%' THEN 1 ELSE 0 END) as google,
          SUM(CASE WHEN referrer_domain LIKE '%bing%' THEN 1 ELSE 0 END) as bing,
          SUM(CASE WHEN referrer_domain LIKE '%chatgpt%' OR referrer_domain LIKE '%openai%' THEN 1 ELSE 0 END) as chatgpt,
          SUM(CASE WHEN referrer_domain LIKE '%claude%' OR referrer_domain LIKE '%anthropic%' THEN 1 ELSE 0 END) as claude,
          SUM(CASE WHEN referrer_domain LIKE '%perplexity%' THEN 1 ELSE 0 END) as perplexity,
          SUM(CASE WHEN referrer_domain LIKE '%github%' THEN 1 ELSE 0 END) as github
        FROM requests
        WHERE is_bot=0 AND ts >= date('now', '-30 days')
          AND referrer_domain IS NOT NULL AND referrer_domain != ''
        GROUP BY day ORDER BY day
    """).fetchall()

    conn.close()
    return d


def _svg_line_chart(series_data, width=800, height=200, colors=None):
    """Generate a simple SVG line chart. series_data: list of (label, [values])."""
    if not series_data or not series_data[0][1]:
        return '<p style="color:#94a3b8;font-size:13px">No data yet</p>'

    n = len(series_data[0][1])
    all_vals = [v for _, vals in series_data for v in vals if v is not None]
    if not all_vals:
        return '<p style="color:#94a3b8;font-size:13px">No data yet</p>'
    max_val = max(all_vals) or 1
    margin_x, margin_y = 50, 20
    chart_w = width - margin_x - 10
    chart_h = height - margin_y * 2

    default_colors = ["#0d9488", "#f59e0b", "#8b5cf6", "#ef4444", "#3b82f6", "#ec4899", "#10b981", "#6366f1"]
    if not colors:
        colors = default_colors

    svg = f'<svg viewBox="0 0 {width} {height}" style="width:100%;max-width:{width}px;height:auto">'
    # Y-axis labels
    for i in range(5):
        y = margin_y + chart_h - (i / 4) * chart_h
        val = int(max_val * i / 4)
        svg += f'<text x="{margin_x-5}" y="{y+4}" text-anchor="end" font-size="10" fill="#94a3b8">{val:,}</text>'
        svg += f'<line x1="{margin_x}" y1="{y}" x2="{width-10}" y2="{y}" stroke="#e2e8f0" stroke-width="0.5"/>'

    # Lines
    for idx, (label, vals) in enumerate(series_data):
        color = colors[idx % len(colors)]
        points = []
        for i, v in enumerate(vals):
            if v is None:
                continue
            x = margin_x + (i / max(n - 1, 1)) * chart_w
            y = margin_y + chart_h - (v / max_val) * chart_h
            points.append(f"{x:.1f},{y:.1f}")
        if points:
            svg += f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="1.5" opacity="0.85"/>'

    svg += '</svg>'

    # Legend
    legend = '<div style="display:flex;flex-wrap:wrap;gap:12px;font-size:11px;margin-top:4px">'
    for idx, (label, vals) in enumerate(series_data):
        color = colors[idx % len(colors)]
        total = sum(v for v in vals if v)
        legend += f'<span style="color:{color}">■ {label} ({total:,})</span>'
    legend += '</div>'

    return svg + legend


def _render(data):
    """Render the full citation dashboard HTML."""
    now = datetime.now()
    today = date.today()

    html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Citation Dashboard — Nerq</title>
<meta name="robots" content="noindex">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui,-apple-system,sans-serif;color:#1e293b;background:#0f172a;line-height:1.5;font-size:14px}}
.wrap{{max-width:960px;margin:0 auto;padding:16px}}
h1{{font-size:1.3em;color:#e2e8f0;margin:0 0 4px;font-weight:600}}
.sub{{font-size:12px;color:#64748b;margin-bottom:20px}}
.card{{background:#1e293b;border-radius:10px;padding:16px;margin-bottom:16px;border:1px solid #334155}}
.card h2{{font-size:1em;color:#e2e8f0;margin:0 0 12px;font-weight:600}}
.card h3{{font-size:0.85em;color:#94a3b8;margin:12px 0 6px;font-weight:500}}
.kpi{{display:inline-block;text-align:center;padding:8px 16px;margin:0 8px 8px 0;background:#0f172a;border-radius:8px;min-width:90px}}
.kpi .num{{font-size:1.4em;font-weight:700;color:#22d3ee}}
.kpi .lbl{{font-size:10px;color:#94a3b8;margin-top:2px}}
.warn{{color:#f59e0b}} .ok{{color:#22d3ee}} .bad{{color:#ef4444}} .good{{color:#10b981}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin:8px 0}}
th{{text-align:left;padding:6px 8px;color:#94a3b8;border-bottom:1px solid #334155;font-weight:500}}
td{{padding:6px 8px;border-bottom:1px solid #1e293b;color:#cbd5e1}}
.pill{{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600}}
.progress{{background:#334155;border-radius:4px;height:8px;margin:4px 0}}
.progress-bar{{height:8px;border-radius:4px}}
.note{{font-size:11px;color:#64748b;font-style:italic;margin-top:6px}}
@media(max-width:600px){{.kpi{{min-width:70px;padding:6px 10px}}.kpi .num{{font-size:1.1em}}}}
</style></head><body>
<div class="wrap">
<h1>Citation Dashboard</h1>
<p class="sub">Verified AI citation metrics only. Updated {now.strftime('%H:%M')}. Cached 5 min.</p>
"""

    # ═══════ SECTION 1: USER-TRIGGERED CITATIONS ═══════
    ut = data["ut_daily"]
    ut_conc = data["ut_concentration"]

    # KPIs — rolling 7 days (NOT calendar week)
    last7 = [r for r in ut if r["day"] >= (today - timedelta(days=7)).isoformat()]
    prev7 = [r for r in ut if (today - timedelta(days=14)).isoformat() <= r["day"] < (today - timedelta(days=7)).isoformat()]
    this_week = sum(r["total"] for r in last7)
    prev_week = sum(r["total"] for r in prev7)
    last7_start = (today - timedelta(days=7)).strftime("%b %d")
    last7_end = (today - timedelta(days=1)).strftime("%b %d")
    wow = ((this_week / max(prev_week, 1)) - 1) * 100

    total_ut = sum(r["cnt"] for r in ut_conc)
    chatgpt_pct = (sum(r["cnt"] for r in ut_conc if r["bot_name"] == "ChatGPT") / max(total_ut, 1)) * 100

    html += f"""
<div class="card">
<h2>User-Triggered Citations <span style="font-size:11px;color:#64748b">(someone asked an AI a question about us)</span></h2>
<div>
<div class="kpi"><div class="num">{this_week:,}</div><div class="lbl">Last 7d ({last7_start}–{last7_end})</div></div>
<div class="kpi"><div class="num {'good' if wow > 0 else 'bad'}">{wow:+.0f}%</div><div class="lbl">vs prev 7d</div></div>
<div class="kpi"><div class="num">{this_week // max(len(last7),1):,}</div><div class="lbl">Per day avg (7d)</div></div>
<div class="kpi"><div class="num {'bad' if chatgpt_pct > 90 else 'warn' if chatgpt_pct > 70 else 'good'}">{chatgpt_pct:.0f}%</div><div class="lbl">ChatGPT share</div></div>
</div>"""

    # Chart
    days = [r["day"][-5:] for r in ut]
    bots = [
        ("ChatGPT-User", [r["chatgpt"] for r in ut]),
        ("Perplexity-User", [r["perplexity"] for r in ut]),
        ("DuckAssist", [r["duckassist"] for r in ut]),
        ("You.com", [r["youbot"] for r in ut]),
        ("Claude-User", [r["claude"] for r in ut]),
    ]
    html += _svg_line_chart(bots)

    # Concentration warning
    if chatgpt_pct > 90:
        html += f'<p class="note" style="color:#f59e0b">⚠ Concentration risk: {chatgpt_pct:.0f}% from ChatGPT alone. If ChatGPT stops citing, {this_week // max(len(last7),1) * (1 - chatgpt_pct/100):.0f}/day remains.</p>'

    # Top URLs table (just ChatGPT, top 10)
    chatgpt_urls = [(r["path"], r["cnt"]) for r in data["ut_top_urls"] if r["bot_name"] == "ChatGPT"][:10]
    if chatgpt_urls:
        html += '<h3>Top ChatGPT-User URLs (7d)</h3><table><tr><th>URL</th><th style="text-align:right">Hits</th></tr>'
        for path, cnt in chatgpt_urls:
            html += f'<tr><td style="font-family:monospace;font-size:11px">{_esc(path[:60])}</td><td style="text-align:right">{cnt}</td></tr>'
        html += '</table>'
    html += '</div>'

    # ═══════ SECTION 2: SEARCH-INDEX ═══════
    si = data["si_daily"]
    html += """
<div class="card">
<h2>Search-Index Crowd <span style="font-size:11px;color:#64748b">(leading indicator — they index, then users cite)</span></h2>"""

    si_bots = [
        ("Applebot", [r["apple"] for r in si]),
        ("OAI-SearchBot", [r["oai_search"] for r in si]),
        ("PerplexityBot", [r["pplx_index"] for r in si]),
        ("BingBot", [r["bing"] for r in si]),
        ("Googlebot", [r["google"] for r in si]),
    ]
    html += _svg_line_chart(si_bots, colors=["#f59e0b", "#3b82f6", "#8b5cf6", "#22d3ee", "#ef4444"])

    # Ratio table
    html += '<h3>Index → Citation Conversion</h3><table><tr><th>Platform</th><th style="text-align:right">Index/day</th><th style="text-align:right">User/day</th><th style="text-align:right">Ratio</th></tr>'
    last7_si = [r for r in si if r["day"] >= (today - timedelta(days=7)).isoformat()]
    n7 = max(len(last7_si), 1)
    oai_avg = sum(r["oai_search"] for r in last7_si) // n7
    chatgpt_user_avg = sum(r["chatgpt"] for r in last7) // max(len(last7), 1) if last7 else 0
    pplx_idx_avg = sum(r["pplx_index"] for r in last7_si) // n7
    pplx_user_avg = sum(r["perplexity"] for r in last7) // max(len(last7), 1) if last7 else 0
    apple_avg = sum(r["apple"] for r in last7_si) // n7

    html += f'<tr><td>ChatGPT</td><td style="text-align:right">{oai_avg:,}</td><td style="text-align:right">{chatgpt_user_avg:,}</td><td style="text-align:right">{oai_avg // max(chatgpt_user_avg,1):,}:1</td></tr>'
    html += f'<tr><td>Perplexity</td><td style="text-align:right">{pplx_idx_avg:,}</td><td style="text-align:right">{pplx_user_avg}</td><td style="text-align:right">{pplx_idx_avg // max(pplx_user_avg,1):,}:1</td></tr>'
    html += f'<tr><td>Apple</td><td style="text-align:right">{apple_avg:,}</td><td style="text-align:right">—</td><td style="text-align:right;color:#64748b">waiting</td></tr>'
    html += '</table></div>'

    # ═══════ SECTION 3: ACTIVE PILOTS ═══════
    p1 = data["pilot1_daily"]
    p1_total = data["pilot1_total_ut"]
    p1_oai_first = data["pilot1_oai_first"]

    html += '<div class="card"><h2>Active Pilots</h2>'

    # Pilot 1
    html += '<h3>Pilot 1: /was-X-hacked (deploy 2026-04-13)</h3>'
    if p1_oai_first:
        oai_first_date = p1_oai_first[:10]
        days_since = (today - date.fromisoformat(oai_first_date)).days
        html += f'<p style="font-size:12px;color:#cbd5e1">OAI-SearchBot first pickup: {oai_first_date} ({days_since}d ago). Measuring 7d from that date.</p>'
    else:
        html += '<p style="font-size:12px;color:#94a3b8">OAI-SearchBot: not yet picked up pilot URLs. Waiting...</p>'

    # Progress bar toward 50 hits
    bar_pct = min(p1_total / 50 * 100, 100)
    bar_color = "#10b981" if p1_total >= 50 else "#f59e0b" if p1_total >= 20 else "#334155"
    html += f"""
<div style="margin:8px 0">
<span style="font-size:12px;color:#cbd5e1">ChatGPT-User on pilot URLs: <strong>{p1_total}</strong> / 50 target</span>
<div class="progress"><div class="progress-bar" style="width:{bar_pct:.0f}%;background:{bar_color}"></div></div>
<span style="font-size:11px;color:#64748b">{"✅ Scale to 5-7 forms" if p1_total >= 50 else "🔍 Investigate" if p1_total >= 20 else "⏳ Accumulating..."}</span>
</div>"""

    if p1:
        p1_chart = [
            ("ChatGPT-User", [r["user_triggered"] for r in p1]),
            ("OAI-SearchBot", [r["oai_search"] for r in p1]),
        ]
        html += _svg_line_chart(p1_chart, height=120, colors=["#10b981", "#3b82f6"])

    # Pilot 2: Freshness
    html += '<h3>Pilot 2: Freshness Pipeline (deploy 2026-04-13)</h3>'
    regen_count = 0
    regen_days = set()
    if os.path.exists(FRESHNESS_LOG):
        try:
            with open(FRESHNESS_LOG) as f:
                for line in f:
                    entry = json.loads(line)
                    regen_count += 1
                    regen_days.add(entry.get("date", ""))
        except Exception:
            pass
    html += f'<p style="font-size:12px;color:#cbd5e1">Entities regenerated: <strong>{regen_count}</strong> across {len(regen_days)} days</p>'
    html += '<p class="note">Measurement: after 4 weeks, compare Perplexity-User lift on regenerated vs stale entities. Target: >1.5x.</p>'

    # M5.1 Kings
    html += '<h3>M5.1: Kings Hypothesis (started 2026-04-11)</h3>'
    m51_end = date(2026, 4, 18)
    m51_days_left = (m51_end - today).days
    if m51_days_left > 0:
        html += f'<p style="font-size:12px;color:#cbd5e1">{m51_days_left} days remaining. Do NOT touch auto_indexnow.py.</p>'
    else:
        html += '<p style="font-size:12px;color:#f59e0b">Measurement window closed. Run analysis.</p>'
    html += '</div>'

    # ═══════ SECTION 4: GROWTH TRAJECTORY ═══════
    cg = data["chatgpt_growth"]
    html += '<div class="card"><h2>ChatGPT-User Growth</h2>'
    if cg:
        # 7d rolling average
        vals = [r["cnt"] for r in cg]
        rolling = []
        for i in range(len(vals)):
            window = vals[max(0, i-6):i+1]
            rolling.append(sum(window) // len(window))
        growth_chart = [
            ("Daily", vals),
            ("7d avg", rolling),
        ]
        html += _svg_line_chart(growth_chart, height=160, colors=["#334155", "#22d3ee"])

        # Annotate key dates
        html += '<p class="note">Key dates: Mar 21 — URL-form spike (9 patterns discovered). Apr 12 — Cloudflare incident.</p>'
    html += '</div>'

    # ═══════ SECTION 5: KNOWN UNKNOWNS ═══════
    html += """
<div class="card">
<h2>Known Unknowns <span style="font-size:11px;color:#64748b">(what we don't know)</span></h2>
<table>
<tr><td style="color:#f59e0b">●</td><td><strong>ClaudeBot value</strong></td><td style="color:#94a3b8">140K/day training crawl. Does it drive any citations? Unknown.</td></tr>
<tr><td style="color:#f59e0b">●</td><td><strong>Manual citation check</strong></td><td style="color:#94a3b8">Does Nerq actually appear in AI answers? Not manually verified.</td></tr>
<tr><td style="color:#f59e0b">●</td><td><strong>Data depth vs competitors</strong></td><td style="color:#94a3b8">Are our trust scores competitive? Comparison not done.</td></tr>
<tr><td style="color:#64748b">●</td><td><strong>Apple Intelligence</strong></td><td style="color:#94a3b8">293K/day indexing. No user-triggered bot yet. Watching.</td></tr>
</table>
</div>"""

    # ═══════ SECTION 6: REFERRAL TRAFFIC ═══════
    refs = data["referrals"]
    html += '<div class="card"><h2>AI Referral Traffic <span style="font-size:11px;color:#64748b">(verified human visits from AI platforms)</span></h2>'

    last7_refs = [r for r in refs if r["day"] >= (today - timedelta(days=7)).isoformat()]
    g_total = sum(r["google"] for r in last7_refs)
    ai_total = sum(r["chatgpt"] + r["claude"] + r["perplexity"] for r in last7_refs)
    html += f"""
<div>
<div class="kpi"><div class="num">{g_total}</div><div class="lbl">Google (7d)</div></div>
<div class="kpi"><div class="num">{ai_total}</div><div class="lbl">AI referrals (7d)</div></div>
</div>
<p class="note">AI referral volume is very low ({ai_total // max(len(last7_refs),1)}/day). High variance expected. This counts humans who clicked a link from an AI chatbot to nerq.ai — NOT the AI bot fetching our data.</p>"""

    ref_chart = [
        ("Google", [r["google"] for r in refs]),
        ("ChatGPT ref", [r["chatgpt"] for r in refs]),
        ("Perplexity ref", [r["perplexity"] for r in refs]),
    ]
    html += _svg_line_chart(ref_chart, height=120, colors=["#ef4444", "#3b82f6", "#8b5cf6"])
    html += '</div>'

    html += f"""
<p style="text-align:center;font-size:11px;color:#475569;margin:16px 0">
Citation Dashboard v1 — {now.strftime('%Y-%m-%d %H:%M')} — <a href="/flywheel" style="color:#64748b">Flywheel</a> · <a href="/admin/analytics-dashboard" style="color:#64748b">Analytics</a>
</p>
</div></body></html>"""

    return html


def mount_citation_dashboard(app):
    @app.get("/citation-dashboard", response_class=HTMLResponse)
    async def citation_dashboard():
        ck = "citation_dash"
        cached = _cache.get(ck)
        if cached:
            html, ts = cached
            if time.time() - ts < CACHE_TTL:
                return HTMLResponse(html, headers={"Cache-Control": "no-cache, private"})

        try:
            data = _get_data()
            html = _render(data)
            _cache[ck] = (html, time.time())
            return HTMLResponse(html, headers={"Cache-Control": "no-cache, private"})
        except Exception as e:
            logger.error(f"Citation dashboard error: {e}", exc_info=True)
            return HTMLResponse(f"<h1>Error</h1><pre>{_esc(str(e))}</pre>", status_code=500)
