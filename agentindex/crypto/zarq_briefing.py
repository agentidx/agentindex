"""
ZARQ Daily Risk Briefing — zarq.ai/briefing
Consolidates everything the power user checks into one Bloomberg-terminal-style page.
Pulls all data live from existing APIs.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
import httpx
import asyncio
import json
from datetime import datetime

router_briefing = APIRouter()

async def _fetch(client, path):
    """Fetch from local API."""
    try:
        r = await client.get(f"http://127.0.0.1:8000{path}", timeout=5.0)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


@router_briefing.get("/briefing", response_class=HTMLResponse)
async def daily_briefing(request: Request):
    host = request.headers.get("host", "")
    if "zarq" not in host and "localhost" not in host and "127.0" not in host:
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="https://zarq.ai/briefing", status_code=301)

    async with httpx.AsyncClient() as client:
        regime, collapse, yield_traps, chain_conc, nav_alpha, nav_dynamic, nav_conservative, yield_insights = await asyncio.gather(
            _fetch(client, "/v1/crypto/paper-trading/regime"),
            _fetch(client, "/v1/agents/structural-collapse"),
            _fetch(client, "/v1/yield/traps"),
            _fetch(client, "/v1/agents/chain-concentration-risk"),
            _fetch(client, "/v1/crypto/paper-trading/nav/ALPHA"),
            _fetch(client, "/v1/crypto/paper-trading/nav/DYNAMIC"),
            _fetch(client, "/v1/crypto/paper-trading/nav/CONSERVATIVE"),
            _fetch(client, "/v1/yield/insights"),
        )

    # Extract regime data
    rd = regime.get("data", {})
    current_regime = rd.get("alpha_regime", "UNKNOWN")
    btc_price = rd.get("btc_price", 0)
    btc_dd = rd.get("btc_dd_from_ath", 0)

    # Collapse agents
    collapse_agents = collapse.get("agents", [])[:5]
    total_collapse = collapse.get("total_agents_in_structural_collapse", 0)
    collapse_mcap = collapse.get("total_mcap_exposed_usd", 0)

    # NAV data - get latest entry
    def _nav_latest(nav_data):
        history = nav_data.get("data", {}).get("history", [])
        if history:
            latest = history[-1]
            return {
                "nav": latest.get("nav_value", 10000),
                "cum_return": latest.get("cumulative_return", 0),
                "drawdown": latest.get("drawdown", 0),
                "max_dd": latest.get("max_drawdown", 0),
                "date": latest.get("nav_date", ""),
                "btc_nav": latest.get("btc_nav", 10000),
            }
        return {"nav": 10000, "cum_return": 0, "drawdown": 0, "max_dd": 0, "date": "", "btc_nav": 10000}

    alpha = _nav_latest(nav_alpha)
    dynamic = _nav_latest(nav_dynamic)
    conservative = _nav_latest(nav_conservative)

    # Yield data
    yield_summary = yield_traps.get("summary", {})
    extreme_traps = yield_summary.get("tier_distribution", {}).get("EXTREME", 0)
    high_traps = yield_summary.get("tier_distribution", {}).get("HIGH", 0)
    total_traps = yield_summary.get("yield_traps_detected", 0)

    # Yield insights top 5
    top_insights = (yield_insights.get("insights", []))[:5]

    # Chain concentration
    chain_global = chain_conc.get("global", {})
    agents_at_risk = chain_global.get("agents_at_risk", 0)
    chains = chain_conc.get("chains", [])
    # Find chains with actual risk
    risky_chains = [c for c in chains if c.get("agents_structural_collapse", 0) > 0 or c.get("agents_in_critical", 0) > 0][:5]

    # Regime colors
    regime_color = {"BULL": "#065f46", "BEAR": "#991b1b", "NEUTRAL": "#92400e"}.get(current_regime, "#6b7280")
    regime_bg = {"BULL": "#ecfdf5", "BEAR": "#fef2f2", "NEUTRAL": "#fffbeb"}.get(current_regime, "#f5f5f5")

    def _fmt_pct(v):
        if v is None:
            return "—"
        return f"{v*100:+.2f}%" if abs(v) < 1 else f"{v:+.2f}%"

    def _fmt_usd(v):
        if v >= 1e9:
            return f"${v/1e9:.1f}B"
        if v >= 1e6:
            return f"${v/1e6:.1f}M"
        if v >= 1e3:
            return f"${v/1e3:.0f}K"
        return f"${v:.0f}"

    def _nav_color(cum_ret):
        if cum_ret > 0:
            return "#065f46"
        if cum_ret < -0.05:
            return "#991b1b"
        return "#92400e"

    # Build collapse rows
    collapse_html = ""
    for a in collapse_agents:
        name = a.get("agent_name", a.get("agent_id", "?"))
        symbol = a.get("token_symbol", "")
        mcap = a.get("market_cap_usd", 0)
        ndd = a.get("ndd_current", 0)
        tp3 = a.get("trust_p3", 0)
        collapse_html += f'''<tr>
            <td><a href="/token/{name}" style="color:#991b1b;font-weight:600">{_esc(symbol or name)}</a></td>
            <td style="text-align:right">{_fmt_usd(mcap)}</td>
            <td style="text-align:right;color:#991b1b;font-weight:600">{ndd:.2f}</td>
            <td style="text-align:right">{tp3:.1f}%</td>
        </tr>'''

    # Build yield insight rows
    yield_html = ""
    for ins in top_insights:
        protocol = ins.get("protocol", "")
        chain = ins.get("chain", "")
        symbol = ins.get("symbol", "")
        apy = ins.get("apy", 0)
        wow = ins.get("wow_text", "")
        signal = ins.get("top_signal", "")
        yield_html += f'''<tr>
            <td><span style="font-weight:600">{_esc(symbol)}</span> <span style="color:#6b7280;font-size:12px">{_esc(protocol)}</span></td>
            <td style="text-align:right">{_esc(chain)}</td>
            <td style="text-align:right;color:{'#991b1b' if apy > 50 else '#92400e' if apy > 20 else '#065f46'}">{apy:.1f}%</td>
            <td style="font-size:12px;color:#6b7280">{_esc(signal)}</td>
        </tr>'''

    # Chain risk rows
    chain_html = ""
    for c in risky_chains:
        ch = c.get("chain", "?")
        agents_c = c.get("total_agents", 0)
        crit = c.get("agents_in_critical", 0)
        sc = c.get("agents_structural_collapse", 0)
        mcap_risk = c.get("mcap_structural_collapse_usd", 0) + c.get("mcap_in_critical_usd", 0)
        chain_html += f'''<tr>
            <td style="font-weight:600">{_esc(ch)}</td>
            <td style="text-align:right">{agents_c:,}</td>
            <td style="text-align:right;color:#991b1b">{sc}</td>
            <td style="text-align:right;color:#92400e">{crit}</td>
            <td style="text-align:right">{_fmt_usd(mcap_risk)}</td>
        </tr>'''

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Risk Briefing — ZARQ</title>
<meta name="description" content="ZARQ Daily Risk Briefing: market regime, structural collapse alerts, paper trading NAV, yield risk, chain concentration. Updated live.">
<link rel="canonical" href="https://zarq.ai/briefing">
<link rel="alternate" type="application/rss+xml" title="ZARQ Risk Feed" href="https://zarq.ai/zarq/feed.xml">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;600&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'DM Sans',system-ui,sans-serif;color:#1a1a1a;background:#0a0a0a;line-height:1.5;font-size:14px}}
a{{color:#c2956b;text-decoration:none}}
a:hover{{color:#d4a77d;text-decoration:underline}}
.mono{{font-family:'JetBrains Mono',ui-monospace,monospace}}
nav{{border-bottom:1px solid #222;padding:10px 0;background:#111}}
nav .inner{{max-width:1100px;margin:0 auto;padding:0 16px;display:flex;align-items:center;justify-content:space-between}}
nav .logo{{font-family:'DM Serif Display',serif;font-weight:700;font-size:1.1rem;color:#c2956b;text-decoration:none}}
nav .links{{display:flex;gap:16px;font-size:13px}}
nav .links a{{color:#888}}
nav .links a:hover{{color:#c2956b;text-decoration:none}}
.dash{{max-width:1100px;margin:0 auto;padding:16px}}
.header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #222}}
.header h1{{font-family:'DM Serif Display',serif;font-size:1.4rem;color:#e5e5e5;font-weight:400}}
.header .ts{{font-size:12px;color:#666}}
.regime-bar{{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}}
.regime-card{{background:#111;border:1px solid #222;padding:12px 16px;flex:1;min-width:140px}}
.regime-card .label{{font-size:11px;color:#666;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px}}
.regime-card .value{{font-family:'JetBrains Mono',monospace;font-size:1.3rem;font-weight:600}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}}
.grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px}}
.panel{{background:#111;border:1px solid #222;padding:14px 16px}}
.panel h2{{font-family:'DM Serif Display',serif;font-size:1rem;color:#e5e5e5;font-weight:400;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center}}
.panel h2 .count{{font-family:'JetBrains Mono',monospace;font-size:12px;color:#c2956b}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:4px 8px;border-bottom:1px solid #333;color:#666;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.05em}}
td{{padding:4px 8px;border-bottom:1px solid #1a1a1a;color:#ccc}}
.nav-card{{background:#111;border:1px solid #222;padding:14px 16px;text-align:center}}
.nav-card .port{{font-size:11px;color:#666;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px}}
.nav-card .nav-val{{font-family:'JetBrains Mono',monospace;font-size:1.5rem;font-weight:600;margin-bottom:2px}}
.nav-card .nav-ret{{font-family:'JetBrains Mono',monospace;font-size:13px;margin-bottom:2px}}
.nav-card .nav-dd{{font-size:11px;color:#666}}
.pill{{display:inline-block;padding:2px 8px;font-size:12px;font-weight:600;font-family:'JetBrains Mono',monospace}}
footer{{border-top:1px solid #222;padding:14px 0;margin-top:20px;font-size:12px;color:#555;text-align:center}}
.refresh-btn{{background:none;border:1px solid #333;color:#888;font-size:12px;padding:3px 10px;cursor:pointer;font-family:'DM Sans',sans-serif}}
.refresh-btn:hover{{border-color:#c2956b;color:#c2956b}}
@media(max-width:768px){{.grid2,.grid3{{grid-template-columns:1fr}}.regime-bar{{flex-direction:column}}}}
</style>
</head>
<body>

<nav><div class="inner">
<a href="/" class="logo">zarq</a>
<div class="links">
<a href="/crypto">dashboard</a>
<a href="/paper-trading">paper trading</a>
<a href="/crash-watch">crash watch</a>
<a href="/yield-risk">yield risk</a>
<a href="/signal">signal</a>
<a href="/zarq/feed.xml">rss</a>
</div>
</div></nav>

<div class="dash">

<div class="header">
<h1>Daily Risk Briefing</h1>
<div>
<span class="ts">{now}</span>
<button class="refresh-btn" onclick="location.reload()" style="margin-left:8px">refresh</button>
</div>
</div>

<div class="regime-bar">
<div class="regime-card">
<div class="label">Market Regime</div>
<div class="value" style="color:{regime_color};background:{regime_bg};display:inline-block;padding:2px 12px">{current_regime}</div>
</div>
<div class="regime-card">
<div class="label">BTC Price</div>
<div class="value mono" style="color:#e5e5e5">${btc_price:,.0f}</div>
</div>
<div class="regime-card">
<div class="label">BTC Drawdown from ATH</div>
<div class="value mono" style="color:#991b1b">{btc_dd*100:.1f}%</div>
</div>
<div class="regime-card">
<div class="label">Structural Collapses</div>
<div class="value mono" style="color:{'#991b1b' if total_collapse > 0 else '#065f46'}">{total_collapse} <span style="font-size:12px;color:#666">({_fmt_usd(collapse_mcap)} exposed)</span></div>
</div>
</div>

<div class="grid3">
<div class="nav-card">
<div class="port">Alpha</div>
<div class="nav-val mono" style="color:{_nav_color(alpha['cum_return'])}">${alpha['nav']:,.0f}</div>
<div class="nav-ret mono" style="color:{_nav_color(alpha['cum_return'])}">{_fmt_pct(alpha['cum_return'])}</div>
<div class="nav-dd">Max DD: {_fmt_pct(alpha['max_dd'])} &middot; BTC: ${alpha['btc_nav']:,.0f}</div>
</div>
<div class="nav-card">
<div class="port">Dynamic</div>
<div class="nav-val mono" style="color:{_nav_color(dynamic['cum_return'])}">${dynamic['nav']:,.0f}</div>
<div class="nav-ret mono" style="color:{_nav_color(dynamic['cum_return'])}">{_fmt_pct(dynamic['cum_return'])}</div>
<div class="nav-dd">Max DD: {_fmt_pct(dynamic['max_dd'])} &middot; BTC: ${dynamic['btc_nav']:,.0f}</div>
</div>
<div class="nav-card">
<div class="port">Conservative</div>
<div class="nav-val mono" style="color:{_nav_color(conservative['cum_return'])}">${conservative['nav']:,.0f}</div>
<div class="nav-ret mono" style="color:{_nav_color(conservative['cum_return'])}">{_fmt_pct(conservative['cum_return'])}</div>
<div class="nav-dd">Max DD: {_fmt_pct(conservative['max_dd'])} &middot; BTC: ${conservative['btc_nav']:,.0f}</div>
</div>
</div>

<div class="grid2">
<div class="panel">
<h2>Structural Collapse Alerts <span class="count">{total_collapse} active</span></h2>
{'<table><thead><tr><th>Token</th><th style="text-align:right">MCap</th><th style="text-align:right">NDD</th><th style="text-align:right">Crash P</th></tr></thead><tbody>' + collapse_html + '</tbody></table>' if collapse_html else '<p style="color:#065f46;font-size:13px">No structural collapse alerts active.</p>'}
</div>

<div class="panel">
<h2>Yield Risk Flags <span class="count">{extreme_traps} extreme &middot; {high_traps} high</span></h2>
{'<table><thead><tr><th>Pool</th><th style="text-align:right">Chain</th><th style="text-align:right">APY</th><th>Signal</th></tr></thead><tbody>' + yield_html + '</tbody></table>' if yield_html else '<p style="color:#6b7280;font-size:13px">No yield insights available.</p>'}
<p style="font-size:11px;color:#555;margin-top:6px">{total_traps:,} yield traps detected across {yield_summary.get('total_pools_analyzed', 0):,} pools</p>
</div>
</div>

<div class="panel" style="margin-bottom:16px">
<h2>Chain Concentration Risk <span class="count">{agents_at_risk} agents at risk</span></h2>
{'<table><thead><tr><th>Chain</th><th style="text-align:right">Agents</th><th style="text-align:right">Collapse</th><th style="text-align:right">Critical</th><th style="text-align:right">MCap at Risk</th></tr></thead><tbody>' + chain_html + '</tbody></table>' if chain_html else '<p style="color:#6b7280;font-size:13px">No chain concentration risk flags.</p>'}
</div>

<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
<a href="/track-record" style="background:#111;border:1px solid #222;padding:8px 16px;color:#c2956b;font-size:13px;text-decoration:none">Track Record &rarr;</a>
<a href="/crypto/alerts" style="background:#111;border:1px solid #222;padding:8px 16px;color:#c2956b;font-size:13px;text-decoration:none">All Alerts &rarr;</a>
<a href="/crash-watch" style="background:#111;border:1px solid #222;padding:8px 16px;color:#c2956b;font-size:13px;text-decoration:none">Crash Watch &rarr;</a>
<a href="/paper-trading" style="background:#111;border:1px solid #222;padding:8px 16px;color:#c2956b;font-size:13px;text-decoration:none">Paper Trading &rarr;</a>
<a href="/yield-risk" style="background:#111;border:1px solid #222;padding:8px 16px;color:#c2956b;font-size:13px;text-decoration:none">Yield Risk &rarr;</a>
<a href="/zarq/feed.xml" style="background:#111;border:1px solid #222;padding:8px 16px;color:#c2956b;font-size:13px;text-decoration:none">RSS Feed &rarr;</a>
</div>

</div>

<footer>
zarq &mdash; the trust layer for the machine economy &middot; <a href="/zarq/docs">api</a> &middot; <a href="/start">get started</a> &middot; <a href="/zarq/feed.xml">rss</a>
</footer>

</body>
</html>"""
    return HTMLResponse(content=html)


def _esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def mount_briefing(app):
    app.include_router(router_briefing)
