"""
ZARQ Crypto Intelligence Pages
================================
Crypto entity pages with ZARQ design language.
Mount this in discovery.py AFTER mount_seo_pages(app).

What it adds:
  GET /crypto/token/{id}          - Token rating page
  GET /crypto/exchange/{id}       - Exchange rating page
  GET /crypto/defi/{id}           - DeFi protocol rating page
  GET /best/crypto-tokens         - Top 50 tokens by trust score
  GET /best/crypto-exchanges      - Top 50 exchanges by trust score
  GET /best/crypto-defi           - Top 50 DeFi protocols by trust score
  GET /crypto                     - Crypto intelligence landing page
  GET /api/v1/crypto/trust-score/{entity_type}/{id} - API endpoint
  GET /sitemap-crypto.xml         - Crypto sitemap

Usage in discovery.py:
    from agentindex.crypto.crypto_seo_pages import mount_crypto_pages
    mount_crypto_pages(app)
"""

import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from fastapi import Request
from fastapi.responses import HTMLResponse, Response, JSONResponse

logger = logging.getLogger("zarq.crypto.seo")

SITE_URL = "https://zarq.ai"
CRYPTO_DB_PATH = str(Path(__file__).parent.parent / "data" / "crypto_trust.db")
CRYPTO_RISK_DB_PATH = str(Path(__file__).parent / "crypto_trust.db")


def _get_risk_data(token_id):
    """Fetch DtD, risk level, crash probability from main crypto DB."""
    try:
        conn = sqlite3.connect(CRYPTO_RISK_DB_PATH)
        conn.row_factory = sqlite3.Row
        ndd = conn.execute("""
            SELECT ndd, alert_level, crash_probability, hc_alert, hc_streak,
                   bottlefish_signal, ndd_trend, ndd_change_4w
            FROM crypto_ndd_daily WHERE token_id = ? ORDER BY run_date DESC LIMIT 1
        """, (token_id,)).fetchone()
        risk = conn.execute("""
            SELECT risk_level, structural_weakness, structural_strength, drawdown_90d
            FROM nerq_risk_signals WHERE token_id = ? ORDER BY signal_date DESC LIMIT 1
        """, (token_id,)).fetchone()
        rating = conn.execute("""
            SELECT rating, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5
            FROM crypto_rating_daily WHERE token_id = ? ORDER BY run_date DESC LIMIT 1
        """, (token_id,)).fetchone()
        conn.close()
        return {
            "ndd": dict(ndd) if ndd else None,
            "risk": dict(risk) if risk else None,
            "rating": dict(rating) if rating else None,
        }
    except:
        return {"ndd": None, "risk": None, "rating": None}


def _get_db():
    conn = sqlite3.connect(CRYPTO_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _esc(text):
    """Escape HTML entities."""
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _grade_color(grade):
    """Map letter grade to warm-palette colors."""
    colors = {
        "A+": "#16a34a", "A": "#16a34a", "B+": "#65a30d", "B": "#a8a29e",
        "C+": "#c2956b", "C": "#dc2626", "D+": "#b91c1c", "D": "#991b1b", "F": "#7f1d1d"
    }
    return colors.get(grade, "#78716c")


def _format_usd(val):
    if not val:
        return "N/A"
    if val >= 1_000_000_000:
        return f"${val/1e9:.1f}B"
    if val >= 1_000_000:
        return f"${val/1e6:.1f}M"
    if val >= 1_000:
        return f"${val/1e3:.1f}K"
    if val >= 1:
        return f"${val:.2f}"
    return f"${val:.6f}"


def _format_num(val):
    if not val:
        return "N/A"
    if val >= 1_000_000_000:
        return f"{val/1e9:.1f}B"
    if val >= 1_000_000:
        return f"{val/1e6:.1f}M"
    if val >= 1_000:
        return f"{val/1e3:.1f}K"
    return f"{val:,.0f}"


def _pct(val):
    if val is None:
        return "N/A"
    color = "#16a34a" if val >= 0 else "#dc2626"
    return f'<span style="color:{color}">{val:+.1f}%</span>'


# ── ZARQ Design System ───────────────────────────────────────────

def _page_head(title, description, url, schema_json=None):
    schema_tag = ""
    if schema_json:
        schema_tag = f'<script type="application/ld+json">{json.dumps(schema_json)}</script>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{SITE_URL}{url}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:url" content="{SITE_URL}{url}">
<meta property="og:type" content="website">
<meta name="robots" content="index, follow">
{schema_tag}
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --white: #fafaf9;
  --black: #0a0a0a;
  --gray-100: #f5f5f4;
  --gray-200: #e7e5e4;
  --gray-400: #a8a29e;
  --gray-500: #78716c;
  --gray-600: #57534e;
  --gray-700: #44403c;
  --gray-800: #292524;
  --gray-900: #1c1917;
  --warm: #c2956b;
  --warm-light: rgba(194, 149, 107, 0.08);
  --green: #16a34a;
  --red: #dc2626;
  --serif: 'DM Serif Display', Georgia, serif;
  --mono: 'JetBrains Mono', monospace;
  --sans: 'DM Sans', sans-serif;
  --wide: 1120px;
  --measure: 680px;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
::selection {{ background: var(--warm); color: var(--black); }}
.site-disclaimer {{
  max-width: var(--wide); margin: 0 auto; padding: 24px 40px 40px;
  font-family: var(--mono); font-size: 10px; line-height: 1.7;
  color: var(--gray-500); letter-spacing: 0.02em;
}}
.site-disclaimer p {{ margin: 0 0 8px; }}
html {{ font-size: 17px; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }}
body {{ background: var(--white); color: var(--gray-800); font-family: var(--sans); line-height: 1.6; }}

/* ─── Navigation ─── */
nav {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  padding: 20px 40px; display: flex; justify-content: space-between; align-items: center;
  backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  background: rgba(250, 250, 249, 0.85); border-bottom: 1px solid rgba(0,0,0,0.04);
}}
.nav-mark {{
  font-family: var(--mono); font-weight: 500; font-size: 15px;
  letter-spacing: 0.15em; text-transform: uppercase; color: var(--black); text-decoration: none;
}}
.nav-links {{ display: flex; gap: 32px; align-items: center; }}
.nav-links a {{
  font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em;
  color: var(--gray-600); text-decoration: none; transition: color 0.2s;
}}
.nav-links a:hover {{ color: var(--black); }}
.nav-api {{ font-family: var(--mono); font-size: 11px; letter-spacing: 0.05em; color: var(--warm); border: 1px solid var(--warm); padding: 6px 16px; text-decoration: none; transition: all 0.2s; }}
.nav-api:hover {{ background: var(--warm); color: var(--white); }}
.nav-dropdown {{ position: relative; }}
.nav-dropdown-trigger {{ cursor: pointer; }}
.nav-dropdown-menu {{ display: none; position: absolute; top: 100%; right: 0; background: var(--white); border: 1px solid var(--gray-200); box-shadow: 0 8px 24px rgba(0,0,0,0.08); padding: 8px 0; min-width: 180px; z-index: 200; }}
.nav-dropdown:hover .nav-dropdown-menu {{ display: block; }}
.nav-dropdown-menu a {{ display: block; padding: 8px 20px; font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-600); text-decoration: none; white-space: nowrap; }}
.nav-dropdown-menu a:hover {{ background: var(--warm-light); color: var(--black); }}
.nav-toggle-input {{ display: none; }}
.nav-hamburger {{ display: none; cursor: pointer; flex-direction: column; gap: 5px; }}
.nav-hamburger span {{ display: block; width: 22px; height: 2px; background: var(--black); transition: all 0.3s; }}

/* ─── Content ─── */
.container {{ max-width: var(--wide); margin: 0 auto; padding: 140px 40px 60px; }}
a {{ color: var(--warm); text-decoration: none; }} a:hover {{ text-decoration: underline; }}
h1 {{
  font-family: var(--serif); font-weight: 400;
  font-size: clamp(32px, 4vw, 48px); line-height: 1.1;
  color: var(--black); letter-spacing: -0.02em; margin-bottom: 8px;
}}
h2 {{
  font-family: var(--serif); font-weight: 400; font-size: 22px;
  color: var(--black); margin-bottom: 16px;
}}
.meta {{
  font-family: var(--mono); font-size: 11px; letter-spacing: 0.05em;
  color: var(--gray-500); margin-bottom: 32px;
}}

/* ─── Cards ─── */
.card {{
  background: var(--white); border: 1px solid var(--gray-200);
  padding: 32px; margin-bottom: 24px;
}}
.card-dark {{
  background: var(--white); border: 1px solid var(--gray-200);
  padding: 32px; margin-bottom: 24px; color: var(--gray-200); position: relative; overflow: hidden;
}}
.card-dark::before {{
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, var(--warm), transparent);
}}

/* ─── Grade Badge ─── */
.grade-badge {{
  display: inline-flex; align-items: center; justify-content: center;
  width: 56px; height: 56px; font-family: var(--serif);
  font-size: 22px; font-weight: 400; color: white;
}}

/* ─── Score System ─── */
.score-bar {{ height: 4px; background: var(--gray-200); overflow: hidden; margin-top: 8px; }}
.score-fill {{ height: 100%; }}
.dim-grid {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1px; background: var(--gray-200); border: 1px solid var(--gray-200); margin-top: 24px;
}}
.dim-item {{ background: var(--white); padding: 20px; }}
.dim-label {{
  font-family: var(--mono); font-size: 10px; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--gray-500);
}}
.dim-score {{ font-family: var(--mono); font-size: 22px; font-weight: 400; margin: 6px 0 2px; }}

/* ─── Tables ─── */
table {{ width: 100%; border-collapse: collapse; }}
th {{
  text-align: left; padding: 12px 16px; font-family: var(--mono);
  font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--gray-500); border-bottom: 1px solid var(--gray-200); font-weight: 400;
}}
td {{ padding: 10px 16px; border-bottom: 1px solid var(--gray-100); font-size: 14px; color: var(--gray-700); }}
tr:hover td {{ background: var(--warm-light); }}

/* ─── FAQ ─── */
.faq {{ margin-top: 40px; }}
.faq h3 {{
  font-family: var(--serif); font-size: 18px; font-weight: 400;
  color: var(--black); margin: 24px 0 8px;
}}
.faq p {{ color: var(--gray-600); font-size: 15px; line-height: 1.7; }}

/* ─── Footer ─── */
footer {{
  max-width: var(--wide); margin: 0 auto; padding: 40px 40px 60px;
  border-top: 1px solid var(--gray-200); display: flex;
  justify-content: space-between; align-items: baseline;
}}
.foot-left {{ font-family: var(--mono); font-size: 11px; color: var(--gray-500); }}
.foot-right {{ display: flex; gap: 24px; }}
.foot-right a {{ font-family: var(--mono); font-size: 11px; color: var(--gray-500); text-decoration: none; }}
.foot-right a:hover {{ color: var(--black); }}

@media (max-width: 768px) {{
  nav {{ padding: 16px 20px; }}
  .nav-hamburger {{ display: flex; }}
  .nav-links {{ display: none; position: absolute; top: 100%; left: 0; right: 0; background: var(--white); border-bottom: 1px solid var(--gray-200); padding: 16px 20px; flex-direction: column; gap: 16px; }}
  .nav-toggle-input:checked ~ .nav-links {{ display: flex; }}
  .nav-dropdown-menu {{ display: block; position: static; box-shadow: none; border: none; padding: 0 0 0 12px; }}
  .nav-dropdown-trigger {{ display: none; }}
  .container {{ padding: 120px 20px 40px; }}
  .dim-grid {{ grid-template-columns: repeat(2, 1fr); }}
  footer {{ flex-direction: column; gap: 16px; padding: 40px 20px; }}
}}
</style>
</head>
<body>
<nav>
  <a href="/" class="nav-mark">zarq</a>
  <input type="checkbox" id="nav-toggle" class="nav-toggle-input">
  <label for="nav-toggle" class="nav-hamburger"><span></span><span></span><span></span></label>
  <div class="nav-links">
    <a href="/scan">Scan</a>
    <a href="/crypto">Ratings</a>
    <a href="/tokens">Token Ratings</a>
    <a href="/crash-watch">Crash Watch</a>
    <div class="nav-dropdown">
      <a href="#" class="nav-dropdown-trigger">More &#9662;</a>
      <div class="nav-dropdown-menu">
        <a href="/yield-risk">Yield Risk</a>
        <a href="/compare">Compare</a>
        <a href="/learn">Learn</a>
        <a href="/track-record">Track Record</a>
        <a href="/paper-trading">Paper Trading</a>
        <a href="/press">Press</a>
        <a href="/methodology">Methodology</a>
      </div>
    </div>
    <a href="/docs" class="nav-api">API</a>
  </div>
</nav>
<div class="container">"""


def _page_foot():
    return """
</div>

<div class="site-disclaimer">
<p><strong>Disclaimer</strong> &mdash; ZARQ provides data-driven crypto intelligence for informational and educational purposes only. Nothing on this website constitutes financial advice, investment advice, trading advice, or any other form of professional advice. ZARQ does not recommend buying, selling, or holding any cryptocurrency or financial instrument.</p>
<p>Trust ratings, Distance-to-Default (DtD) scores, crash probabilities, trading signals, and all other data are derived from quantitative models and may contain errors, lag behind real-time conditions, or fail to predict future outcomes. Past performance, whether backtested or live, is not indicative of future results. All backtested results are hypothetical and do not represent actual trading.</p>
<p>Crypto assets are highly volatile, speculative, and may result in total loss of invested capital. You should conduct your own research (DYOR) and consult a qualified, licensed financial advisor before making any investment decisions. ZARQ is not registered as a broker-dealer, investment advisor, or financial institution in any jurisdiction.</p>
<p>By using this website, you acknowledge that you bear sole responsibility for your own investment decisions and that ZARQ, its founders, contributors, and affiliates accept no liability for any losses, damages, or consequences arising from the use of information provided herein.</p>
</div>
<footer>
  <div class="foot-left">&copy; 2026 ZARQ &middot; Crypto Intelligence</div>
  <div class="foot-right">
    <a href="/crypto">Ratings</a>
    <a href="/tokens">Token Ratings</a>
    <a href="/crypto/alerts">Alerts</a>
    <a href="/risk-scanner">Risk Scanner</a>
    <a href="/contagion">Contagion</a>
    <a href="/track-record">Track Record</a>
        <a href="/paper-trading">Paper Trading</a>
    <a href="/paper-trading">Paper Trading</a>
    <a href="/methodology">Methodology</a>
    <a href="/docs">API</a>
    <a href="https://nerq.ai">NERQ (AI Agents)</a>
    <a href="mailto:hello@zarq.ai" style="margin-left:12px">hello@zarq.ai</a>
  </div>
</footer>
</body></html>"""


# ── Risk Intelligence Block (DtD) ────────────────────────────────

def _risk_intelligence_block(t):
    """Render DtD, risk level, crash probability block for token pages."""
    rd = t.get("_risk")
    if not rd:
        return ""
    ndd = rd.get("ndd")
    risk = rd.get("risk")
    rating = rd.get("rating")
    if not ndd and not risk:
        return ""

    dtd_val = ndd.get("ndd", 0) if ndd else 0
    alert = ndd.get("alert_level", "N/A") if ndd else "N/A"
    cp = ndd.get("crash_probability") if ndd else 0
    cp = cp if cp is not None else 0
    hc = ndd.get("hc_alert", 0) if ndd else 0
    trend = ndd.get("ndd_trend", "N/A") if ndd else "N/A"
    bf = ndd.get("bottlefish_signal", "N/A") if ndd else "N/A"

    rl = risk.get("risk_level", "N/A") if risk else "N/A"
    weakness = risk.get("structural_weakness", 0) if risk else 0
    dd90 = (risk.get("drawdown_90d", 0) or 0) * 100 if risk else 0

    moody_rating = rating.get("rating", "N/A") if rating else "N/A"
    moody_score = rating.get("score", 0) if rating else 0

    rl_colors = {"SAFE": "#16a34a", "WATCH": "#a8a29e", "WARNING": "#c2956b", "CRITICAL": "#dc2626"}
    rl_color = rl_colors.get(rl, "#78716c")
    alert_colors = {"HEALTHY": "#16a34a", "WATCH": "#a8a29e", "WARNING": "#c2956b", "DISTRESS": "#dc2626", "EMERGENCY": "#991b1b"}
    alert_color = alert_colors.get(alert, "#78716c")

    hc_html = '<span style="color:#dc2626;font-weight:500"> · HC ALERT ACTIVE</span>' if hc else ""

    return f"""
<div class="card-dark" style="margin-top:24px">
<div style="font-family:var(--mono);font-size:10px;letter-spacing:0.15em;text-transform:uppercase;color:var(--gray-400);margin-bottom:20px">Risk Intelligence</div>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:24px">
  <div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500)">Risk Level</div>
    <div style="font-family:var(--serif);font-size:22px;color:{rl_color};margin-top:4px">{rl}</div>
  </div>
  <div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500)">DtD Score</div>
    <div style="font-family:var(--mono);font-size:22px;color:{alert_color};margin-top:4px">{dtd_val:.2f}<span style="font-size:13px;color:var(--gray-500)">/5.0</span></div>
  </div>
  <div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500)">Crash Prob (90d)</div>
    <div style="font-family:var(--mono);font-size:22px;color:{"#dc2626" if cp > 30 else "#c2956b" if cp > 10 else "#16a34a"};margin-top:4px">{cp:.0f}%</div>
  </div>
  <div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500)">Credit Rating</div>
    <div style="font-family:var(--serif);font-size:22px;color:var(--gray-800);margin-top:4px">{moody_rating} <span style="font-family:var(--mono);font-size:13px;color:var(--gray-500)">{moody_score:.0f}/100</span></div>
  </div>
  <div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500)">Weakness</div>
    <div style="font-family:var(--mono);font-size:22px;color:var(--gray-800);margin-top:4px">{weakness}/4</div>
  </div>
  <div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500)">Trend</div>
    <div style="font-family:var(--mono);font-size:22px;color:var(--gray-800);margin-top:4px">{trend}</div>
  </div>
</div>
{f'<div style="margin-top:16px;font-family:var(--mono);font-size:12px;color:#dc2626">{hc_html}</div>' if hc else ""}
<div style="margin-top:16px;font-family:var(--mono);font-size:10px;color:var(--gray-500)">Bottlefish: {bf} · 90d Drawdown: {dd90:.1f}% · <a href="/v1/crypto/ndd/{t.get("id","")}" style="color:var(--warm)">API</a> · <a href="/crypto/signals" style="color:var(--warm)">Signals Feed</a></div>
</div>"""


# ── Trust Score Block ─────────────────────────────────────────────

def _trust_score_block(entity, entity_type):
    """Render the trust score card with 5 dimensions — ZARQ design."""
    score = entity.get("trust_score") or 0
    grade = entity.get("trust_grade") or "F"
    gc = _grade_color(grade)

    dims = [
        ("Security", entity.get("security_score") or 0, "30%"),
        ("Compliance", entity.get("compliance_score") or 0, "25%"),
        ("Maintenance", entity.get("maintenance_score") or 0, "20%"),
        ("Popularity", entity.get("popularity_score") or 0, "15%"),
        ("Ecosystem", entity.get("ecosystem_score") or 0, "10%"),
    ]

    dim_html = ""
    for label, val, weight in dims:
        dim_html += f"""<div class="dim-item">
  <div class="dim-label">{label} ({weight})</div>
  <div class="dim-score">{val:.0f}</div>
  <div class="score-bar"><div class="score-fill" style="width:{val}%;background:var(--warm)"></div></div>
</div>"""

    return f"""<div class="card">
  <div style="display:flex;align-items:center;gap:20px;margin-bottom:20px">
    <div class="grade-badge" style="background:{gc}">{grade}</div>
    <div>
      <div style="font-family:var(--serif);font-size:36px;letter-spacing:-0.02em">{score:.1f}<span style="font-family:var(--mono);font-size:14px;color:var(--gray-500)">/100</span></div>
      <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500)">ZARQ Trust Score</div>
    </div>
  </div>
  <div class="score-bar" style="height:6px"><div class="score-fill" style="width:{score}%;background:{gc}"></div></div>
  <div class="dim-grid">{dim_html}</div>
</div>"""


# ── Token Page ────────────────────────────────────────────────────

def _render_token_page(t):
    name = _esc(t.get("name") or t["id"])
    symbol = _esc((t.get("symbol") or "").upper())
    token_id = t["id"]
    trust_score = t.get("trust_score", 0) or 0
    trust_grade = t.get("trust_grade", "F")
    risk_data = t.get("_risk", {})
    risk_level = "UNKNOWN"
    if risk_data and risk_data.get("risk"):
        risk_level = risk_data["risk"].get("risk_level", "UNKNOWN") or "UNKNOWN"
    crash_prob = None
    if risk_data and risk_data.get("ndd"):
        crash_prob = risk_data["ndd"].get("crash_probability")

    # SEO-optimized title: "Is X Safe? Risk Rating & Analysis 2026 | ZARQ"
    title = f"Is {name} ({symbol}) Safe? Risk Rating & Analysis 2026 | ZARQ"
    # SEO-optimized description with grade, risk level, crash prob, CTA
    desc = f"{name} has a ZARQ safety rating of {trust_grade} ({trust_score:.0f}/100)."
    if risk_level != "UNKNOWN":
        desc += f" Risk level: {risk_level.upper()}."
    desc += f" Live crash probability, yield risk, and Vitality Score analysis."
    url = f"/crypto/token/{token_id}"

    schema = {
        "@context": "https://schema.org",
        "@type": "FinancialProduct",
        "name": f"{name} ({symbol})",
        "description": desc,
        "url": f"{SITE_URL}{url}",
        "provider": {"@type": "Organization", "name": "ZARQ", "url": SITE_URL},
        "review": {
            "@type": "Review",
            "author": {"@type": "Organization", "name": "ZARQ"},
            "reviewRating": {
                "@type": "Rating",
                "ratingValue": str(round(trust_score / 20, 1)),
                "bestRating": "5",
                "worstRating": "0"
            },
            "reviewBody": desc
        }
    }

    # BreadcrumbList schema
    breadcrumb_schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Crypto Safety", "item": "https://zarq.ai/vitality"},
            {"@type": "ListItem", "position": 3, "name": f"{name} ({symbol})"},
        ]
    }

    # Market data section
    market_html = ""
    if t.get("current_price_usd") is not None:
        market_html = f"""<div class="card">
  <h2>Market Data</h2>
  <table>
    <tr><td>Price</td><td><strong>{_format_usd(t.get('current_price_usd'))}</strong></td></tr>
    <tr><td>Market Cap</td><td>{_format_usd(t.get('market_cap_usd'))}</td></tr>
    <tr><td>Market Cap Rank</td><td>#{t.get('market_cap_rank') or 'N/A'}</td></tr>
    <tr><td>24h Volume</td><td>{_format_usd(t.get('total_volume_24h_usd'))}</td></tr>
    <tr><td>24h Change</td><td>{_pct(t.get('price_change_24h_pct'))}</td></tr>
    <tr><td>7d Change</td><td>{_pct(t.get('price_change_7d_pct'))}</td></tr>
    <tr><td>30d Change</td><td>{_pct(t.get('price_change_30d_pct'))}</td></tr>
    <tr><td>Circulating Supply</td><td>{_format_num(t.get('circulating_supply'))}</td></tr>
    <tr><td>Total Supply</td><td>{_format_num(t.get('total_supply'))}</td></tr>
    <tr><td>Max Supply</td><td>{_format_num(t.get('max_supply'))}</td></tr>
    <tr><td>All-Time High</td><td>{_format_usd(t.get('ath_usd'))}</td></tr>
    <tr><td>All-Time Low</td><td>{_format_usd(t.get('atl_usd'))}</td></tr>
  </table>
</div>"""

    # Community/dev section
    community_html = ""
    if t.get("twitter_followers") or t.get("github_stars"):
        community_html = f"""<div class="card">
  <h2>Community &amp; Development</h2>
  <table>
    {"<tr><td>Twitter Followers</td><td>" + _format_num(t.get('twitter_followers')) + "</td></tr>" if t.get('twitter_followers') else ""}
    {"<tr><td>Reddit Subscribers</td><td>" + _format_num(t.get('reddit_subscribers')) + "</td></tr>" if t.get('reddit_subscribers') else ""}
    {"<tr><td>GitHub Stars</td><td>" + _format_num(t.get('github_stars')) + "</td></tr>" if t.get('github_stars') else ""}
    {"<tr><td>GitHub Forks</td><td>" + _format_num(t.get('github_forks')) + "</td></tr>" if t.get('github_forks') else ""}
    {"<tr><td>Contributors</td><td>" + _format_num(t.get('github_contributors')) + "</td></tr>" if t.get('github_contributors') else ""}
  </table>
</div>"""

    # Security check CTA
    security_cta = f'''<div class="security-check-cta" style="
        margin:24px 0;padding:20px 24px;border:1px solid #e2e8f0;
        border-radius:12px;background:#f8fafc;text-align:center">
        <p style="font-size:1.1em;font-weight:600;margin:0 0 6px">
            This token scores <strong>{trust_score:.0f}</strong>/100.
            What&#39;s yours?
        </p>
        <p style="font-size:0.9em;color:#64748b;margin:0 0 14px">
            Free security check, 2 seconds, nothing stored.
        </p>
        <button onclick="runSecurityCheck()" class="security-check-btn" style="
            background:#0d9488;color:white;border:none;padding:10px 24px;
            border-radius:8px;font-size:0.95em;font-weight:500;cursor:pointer">
            Get my score &rarr;
        </button>
    </div>'''

    # FAQ — expanded for long-tail SEO
    crash_prob_text = f"{crash_prob*100:.1f}%" if crash_prob is not None else "not currently available"
    faq_items = [
        (f"What is the {name} Trust Score?",
         f"{name} ({symbol}) has a ZARQ Trust Score of {trust_score:.1f} out of 100, graded {trust_grade}. This score is calculated across five dimensions: Security (30%), Compliance (25%), Maintenance (20%), Popularity (15%), and Ecosystem (10%)."),
        (f"Is {name} safe to invest in?",
         f"The ZARQ Trust Score provides a data-driven risk assessment but is not investment advice. {name} scored {t.get('security_score', 0):.0f}/100 on Security and {t.get('compliance_score', 0):.0f}/100 on Compliance. Current risk level: {risk_level}. Always do your own research and consult a financial advisor."),
        (f"What is the crash probability for {name}?",
         f"The current crash probability for {name} ({symbol}) is {crash_prob_text}. This is calculated using ZARQ's Distance-to-Default model, which measures 7 risk signals including liquidity depth, holder concentration, ecosystem resilience, and structural risk."),
        (f"How does {name} compare to {'Ethereum' if token_id == 'bitcoin' else 'Bitcoin'}?",
         f"With a Trust Score of {trust_score:.1f} (Grade {trust_grade}), {name} "
         f"{'scores comparably to Bitcoin.' if trust_score >= 70 else 'scores below Bitcoin, which typically rates above 70/100.'} "
         f"Compare detailed metrics at zarq.ai/v1/crypto/compare/{token_id}/{'ethereum' if token_id == 'bitcoin' else 'bitcoin'}."),
        (f"What is {name}'s Vitality Score?",
         f"{name}'s Vitality Score measures ecosystem health across 5 dimensions: Ecosystem Gravity, Capital Commitment, Coordination Efficiency, Stress Resilience, and Organic Momentum. Check the live Vitality Score at zarq.ai/v1/vitality/{token_id}."),
        (f"Is {name} a good investment in 2026?",
         f"ZARQ provides risk intelligence, not investment advice. {name} ({symbol}) currently has a Trust Score of {trust_score:.1f}/100 (Grade {trust_grade}) and risk level {risk_level}. "
         f"{'The token shows strong fundamentals.' if trust_score >= 70 else 'Review the risk signals carefully before investing.'} "
         f"See our methodology at zarq.ai/methodology for how scores are calculated."),
        (f"Should I invest in {name} in 2026?",
         f"{name} ({symbol}) carries a {trust_grade} safety grade from ZARQ. "
         f"{'Investment-grade tokens (A/B) have historically shown lower default rates.' if trust_grade and trust_grade[0] in 'AB' else 'Speculative-grade tokens require careful due diligence and position sizing.'} "
         f"Review the full risk profile at zarq.ai/crypto/token/{token_id} before making any decisions."),
        (f"How does {name} compare to Bitcoin in safety?",
         f"{name} has a ZARQ Trust Score of {trust_score:.1f}/100, "
         f"{'which is competitive with Bitcoin (typically 75+/100).' if trust_score >= 70 else 'compared to Bitcoin which typically scores above 75/100.'} "
         f"Key differences may include security infrastructure, regulatory compliance, and ecosystem depth. "
         f"See the full side-by-side at zarq.ai/compare/{token_id}-vs-bitcoin."),
        (f"What is the {name} risk level today?",
         f"As of today, {name} ({symbol}) has a risk level of {risk_level}. "
         f"This is derived from ZARQ's structural risk model which monitors on-chain concentration, liquidity depth, developer activity, and market microstructure. "
         f"{'Crash probability: ' + f'{crash_prob*100:.1f}%.' if crash_prob is not None else 'Crash probability data is being computed.'} "
         f"Updated daily at zarq.ai/crypto/token/{token_id}."),
        (f"What chains does {name} support?",
         f"{name} ({symbol}) is available on "
         + (f"{', '.join(list(json.loads(t['platforms']).keys())[:5])}" if t.get('platforms') else "its native blockchain")
         + ". Multi-chain availability can improve liquidity and ecosystem reach. "
         f"Check the full {name} safety report at zarq.ai/crypto/token/{token_id}."),
    ]

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq_items
        ]
    }

    faq_html = '<div class="faq"><h2>Frequently Asked Questions</h2>'
    for q, a in faq_items:
        faq_html += f"<h3>{_esc(q)}</h3><p>{_esc(a)}</p>"
    faq_html += "</div>"

    # AI-Citable Summary
    ai_summary = f"""<!-- AI-Citable Summary: {name} ({symbol}) has a ZARQ Trust Score of {t.get('trust_score', 0):.1f}/100 (Grade {t.get('trust_grade', 'F')}). Security: {t.get('security_score', 0):.0f}, Compliance: {t.get('compliance_score', 0):.0f}, Maintenance: {t.get('maintenance_score', 0):.0f}, Popularity: {t.get('popularity_score', 0):.0f}, Ecosystem: {t.get('ecosystem_score', 0):.0f}. Source: ZARQ (zarq.ai) — independent crypto intelligence. -->"""

    # Related tokens — same chain for internal link clusters
    related_html = ""
    try:
        conn = _get_db()
        related_rows = []
        # Try chain-based: find tokens on the same platform/chain
        platforms_raw = t.get("platforms")
        if platforms_raw:
            try:
                plats = json.loads(platforms_raw) if isinstance(platforms_raw, str) else platforms_raw
                if plats and isinstance(plats, dict):
                    chain = list(plats.keys())[0]  # primary chain
                    # Find other tokens on the same chain
                    all_tokens = conn.execute("""
                        SELECT id, name, symbol, trust_score, trust_grade, market_cap_rank, platforms
                        FROM crypto_tokens
                        WHERE id != ? AND trust_score IS NOT NULL AND platforms IS NOT NULL
                        ORDER BY market_cap_rank ASC NULLS LAST
                        LIMIT 500
                    """, (token_id,)).fetchall()
                    for r in all_tokens:
                        try:
                            rp = json.loads(r["platforms"]) if r["platforms"] else {}
                            if chain in rp:
                                related_rows.append(r)
                                if len(related_rows) >= 5:
                                    break
                        except (json.JSONDecodeError, TypeError):
                            continue
            except (json.JSONDecodeError, TypeError):
                pass
        # Fallback: score-adjacent if chain matching found <3
        if len(related_rows) < 3:
            fallback = conn.execute("""
                SELECT id, name, symbol, trust_score, trust_grade, market_cap_rank
                FROM crypto_tokens
                WHERE id != ? AND trust_score IS NOT NULL
                AND ABS(trust_score - ?) < 15
                ORDER BY market_cap_rank ASC NULLS LAST
                LIMIT ?
            """, (token_id, trust_score, 5 - len(related_rows))).fetchall()
            seen = {r["id"] for r in related_rows}
            for r in fallback:
                if r["id"] not in seen:
                    related_rows.append(r)
        conn.close()
        if related_rows:
            related_html = '<div class="card"><h2>Related Tokens</h2><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px">'
            for r in related_rows[:5]:
                rname = _esc(r["name"])
                rsym = _esc((r["symbol"] or "").upper())
                rscore = r["trust_score"] or 0
                rgrade = r["trust_grade"] or "?"
                related_html += f'<a href="/crypto/token/{r["id"]}" style="display:block;padding:10px 12px;border:1px solid var(--gray-200);text-decoration:none;color:inherit"><strong>{rname}</strong> <span style="color:var(--gray-500);font-size:12px">{rsym}</span><br><span style="font-family:var(--mono);font-size:13px;color:var(--warm)">{rscore:.0f}/100 ({rgrade})</span></a>'
            related_html += '</div></div>'
    except Exception:
        pass

    # BTC comparison mini-section
    btc_compare_html = ""
    try:
        conn = _get_db()
        btc = conn.execute("SELECT trust_score, trust_grade FROM crypto_tokens WHERE id = 'bitcoin'").fetchone()
        eth = conn.execute("SELECT trust_score, trust_grade FROM crypto_tokens WHERE id = 'ethereum'").fetchone()
        conn.close()
        if btc and token_id not in ('bitcoin', 'ethereum'):
            btc_score = btc["trust_score"] or 0
            eth_score = (eth["trust_score"] or 0) if eth else 0
            diff_btc = trust_score - btc_score
            btc_compare_html = f"""<div class="card">
<h2>How {_esc(name)} Compares</h2>
<table>
<tr><td>{_esc(name)} ({symbol})</td><td style="font-family:var(--mono);color:var(--warm)">{trust_score:.0f}/100 ({trust_grade})</td></tr>
<tr><td>Bitcoin (BTC)</td><td style="font-family:var(--mono)">{btc_score:.0f}/100 ({btc["trust_grade"]})</td></tr>
<tr><td>Ethereum (ETH)</td><td style="font-family:var(--mono)">{eth_score:.0f}/100 ({eth["trust_grade"] if eth else "?"})</td></tr>
</table>
<p style="font-size:13px;color:var(--gray-500);margin-top:8px">{_esc(name)} scores {abs(diff_btc):.0f} points {"above" if diff_btc > 0 else "below"} Bitcoin. <a href="/v1/crypto/compare/{token_id}/bitcoin">Full comparison &rarr;</a></p>
</div>"""
    except Exception:
        pass

    html = _page_head(title, desc, url, schema)
    html += f"""
{ai_summary}
<script type="application/ld+json">{json.dumps(faq_schema)}</script>
<script type="application/ld+json">{json.dumps(breadcrumb_schema)}</script>
<nav style="font-size:12px;color:var(--gray-500);margin-bottom:12px"><a href="/" style="color:var(--gray-500)">Home</a> &rsaquo; <a href="/tokens" style="color:var(--gray-500)">Crypto Safety</a> &rsaquo; {_esc(name)}</nav>
<h1>{_esc(name)} <span style="font-family:var(--mono);font-size:clamp(16px,2vw,22px);color:var(--gray-500)">{symbol}</span></h1>
<p class="meta">Crypto Token · {"Rank #" + str(t.get('market_cap_rank')) if t.get('market_cap_rank') else 'Unranked'} by Market Cap · Updated {t.get('crawled_at', 'N/A')[:10]}</p>
{_trust_score_block(t, 'token')}
{security_cta}
{_risk_intelligence_block(t)}
{market_html}
{btc_compare_html}
{community_html}
{faq_html}
{related_html}
<script>
async function runSecurityCheck(){{
  var btn=document.querySelector('.security-check-btn');
  var cta=document.querySelector('.security-check-cta');
  btn.textContent='Checking...';btn.disabled=true;
  if(localStorage.getItem('ck_ok')){{
    navigator.sendBeacon('/v1/event',JSON.stringify({{event:'security_check_click',path:location.pathname}}));
  }}
  try{{
    var r=await fetch('/my/check');
    var h=await r.text();
    cta.innerHTML=h;
    if(localStorage.getItem('ck_ok')){{
      var m=h.match(/(\\d+)\\/100/);
      navigator.sendBeacon('/v1/event',JSON.stringify({{event:'security_check_complete',path:location.pathname,score:m?parseInt(m[1]):null}}));
    }}
  }}catch(e){{btn.textContent='Get my score \\u2192';btn.disabled=false;}}
}}
if(localStorage.getItem('ck_ok')&&document.querySelector('.security-check-cta')){{
  navigator.sendBeacon('/v1/event',JSON.stringify({{event:'cta_impression',path:location.pathname}}));
}}
</script>
"""
    html += _page_foot()
    return html


# ── Exchange Page ─────────────────────────────────────────────────

def _render_exchange_page(ex):
    name = _esc(ex.get("name") or ex["id"])
    title = f"{name} Rating — ZARQ Crypto Exchange Intelligence"
    desc = f"{name} has a ZARQ Trust Score of {ex.get('trust_score', 0):.1f}/100 (Grade {ex.get('trust_grade', 'F')}). Independent security and compliance assessment."
    url = f"/crypto/exchange/{ex['id']}"

    schema = {
        "@context": "https://schema.org",
        "@type": "FinancialService",
        "name": name,
        "description": desc,
        "url": f"{SITE_URL}{url}",
        "provider": {"@type": "Organization", "name": "ZARQ", "url": SITE_URL},
        "review": {
            "@type": "Review",
            "author": {"@type": "Organization", "name": "ZARQ"},
            "reviewRating": {
                "@type": "Rating",
                "ratingValue": str(round(ex.get("trust_score", 0) / 20, 1)),
                "bestRating": "5",
                "worstRating": "0"
            }
        }
    }

    info_html = f"""<div class="card">
  <h2>Exchange Info</h2>
  <table>
    <tr><td>Country</td><td>{_esc(ex.get('country') or 'Unknown')}</td></tr>
    <tr><td>Year Established</td><td>{ex.get('year_established') or 'Unknown'}</td></tr>
    <tr><td>CoinGecko Trust Score</td><td>{ex.get('trust_score_cg') or 'N/A'}/10</td></tr>
    <tr><td>CoinGecko Trust Rank</td><td>#{ex.get('trust_score_rank') or 'N/A'}</td></tr>
    <tr><td>24h Volume (BTC)</td><td>{_format_num(ex.get('trade_volume_24h_btc'))}</td></tr>
    <tr><td>Website</td><td>{"<a href='" + _esc(ex.get('url')) + "' rel='nofollow'>" + _esc(ex.get('url')) + "</a>" if ex.get('url') else 'N/A'}</td></tr>
  </table>
</div>"""

    faq_items = [
        (f"Is {name} a safe exchange?",
         f"{name} has a ZARQ Trust Score of {ex.get('trust_score', 0):.1f}/100, graded {ex.get('trust_grade', 'F')}. Security score: {ex.get('security_score', 0):.0f}/100, Compliance: {ex.get('compliance_score', 0):.0f}/100. This is an automated assessment — always verify with official sources."),
        (f"How does {name} compare to other exchanges?",
         f"Among exchanges rated by ZARQ, {name} is graded {ex.get('trust_grade', 'F')}. See our Top Exchanges page for the highest-rated alternatives."),
    ]

    faq_schema = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq_items]
    }

    faq_html = '<div class="faq"><h2>Frequently Asked Questions</h2>'
    for q, a in faq_items:
        faq_html += f"<h3>{_esc(q)}</h3><p>{_esc(a)}</p>"
    faq_html += "</div>"

    ai_summary = f"""<!-- AI-Citable Summary: {name} exchange has a ZARQ Trust Score of {ex.get('trust_score', 0):.1f}/100 (Grade {ex.get('trust_grade', 'F')}). Security: {ex.get('security_score', 0):.0f}, Compliance: {ex.get('compliance_score', 0):.0f}. Country: {ex.get('country') or 'Unknown'}. Source: ZARQ (zarq.ai) -->"""

    html = _page_head(title, desc, url, schema)
    html += f"""
{ai_summary}
<script type="application/ld+json">{json.dumps(faq_schema)}</script>
<h1>{name}</h1>
<p class="meta">Crypto Exchange · {_esc(ex.get('country') or 'Unknown')} · Est. {ex.get('year_established') or 'Unknown'}</p>
{_trust_score_block(ex, 'exchange')}
{info_html}
{faq_html}
"""
    html += _page_foot()
    return html


# ── DeFi Protocol Page ───────────────────────────────────────────

def _render_defi_page(p):
    name = _esc(p.get("name") or p["id"])
    title = f"{name} Rating — ZARQ DeFi Protocol Intelligence"
    desc = f"{name} has a ZARQ Trust Score of {p.get('trust_score', 0):.1f}/100 (Grade {p.get('trust_grade', 'F')}). TVL: {_format_usd(p.get('tvl_usd'))}."
    url = f"/crypto/defi/{p['id']}"

    chains = []
    if p.get("chains"):
        try:
            chains = json.loads(p["chains"]) if isinstance(p["chains"], str) else p["chains"]
        except (json.JSONDecodeError, TypeError):
            pass

    hacks = []
    total_stolen = 0
    if p.get("hack_history"):
        try:
            hd = json.loads(p["hack_history"]) if isinstance(p["hack_history"], str) else p["hack_history"]
            hacks = hd.get("incidents", []) if isinstance(hd, dict) else hd
            total_stolen = hd.get("total_stolen_usd", 0) if isinstance(hd, dict) else 0
        except (json.JSONDecodeError, TypeError):
            pass

    schema = {
        "@context": "https://schema.org",
        "@type": "FinancialProduct",
        "name": name,
        "description": desc,
        "url": f"{SITE_URL}{url}",
        "provider": {"@type": "Organization", "name": "ZARQ", "url": SITE_URL},
    }

    info_html = f"""<div class="card">
  <h2>Protocol Info</h2>
  <table>
    <tr><td>Category</td><td>{_esc(p.get('category') or 'Unknown')}</td></tr>
    <tr><td>Total Value Locked</td><td><strong>{_format_usd(p.get('tvl_usd'))}</strong></td></tr>
    <tr><td>TVL Change (24h)</td><td>{_pct(p.get('tvl_change_1d'))}</td></tr>
    <tr><td>TVL Change (7d)</td><td>{_pct(p.get('tvl_change_7d'))}</td></tr>
    <tr><td>TVL Change (30d)</td><td>{_pct(p.get('tvl_change_30d'))}</td></tr>
    <tr><td>Chains</td><td>{', '.join(chains[:10]) or 'Unknown'}{' +' + str(len(chains)-10) + ' more' if len(chains) > 10 else ''}</td></tr>
    <tr><td>Website</td><td>{"<a href='" + _esc(p.get('url')) + "' rel='nofollow'>" + _esc(p.get('url')) + "</a>" if p.get('url') else 'N/A'}</td></tr>
  </table>
</div>"""

    # Hack history section
    hack_html = ""
    if hacks:
        hack_html = f"""<div class="card">
  <h2>Security Incidents ({len(hacks)})</h2>
  <p style="font-family:var(--mono);font-size:12px;color:var(--gray-500);margin-bottom:16px">Total stolen: {_format_usd(total_stolen)}</p>
  <table>
    <tr><th>Date</th><th>Amount</th><th>Type</th><th>Chain</th></tr>"""
        for h in sorted(hacks, key=lambda x: str(x.get("date", "")), reverse=True)[:10]:
            hack_html += f"""<tr>
  <td>{_esc(str(h.get('date', 'Unknown'))[:10])}</td>
  <td>{_format_usd(h.get('amount_usd'))}</td>
  <td>{_esc(h.get('classification') or h.get('technique') or 'Unknown')}</td>
  <td>{_esc(h.get('chain') or 'Unknown')}</td>
</tr>"""
        hack_html += "</table></div>"

    faq_items = [
        (f"Is {name} safe to use?",
         f"{name} has a ZARQ Trust Score of {p.get('trust_score', 0):.1f}/100, graded {p.get('trust_grade', 'F')}. "
         f"{'It has ' + str(len(hacks)) + ' known security incidents totaling ' + _format_usd(total_stolen) + ' stolen. ' if hacks else 'No known security incidents. '}"
         f"TVL: {_format_usd(p.get('tvl_usd'))}. Always verify smart contract audits before depositing funds."),
        (f"What chains does {name} support?",
         f"{name} is deployed on {len(chains)} chain{'s' if len(chains) != 1 else ''}: {', '.join(chains[:5]) or 'Unknown'}{' and more' if len(chains) > 5 else ''}."),
    ]

    faq_schema = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq_items]
    }

    faq_html = '<div class="faq"><h2>Frequently Asked Questions</h2>'
    for q, a in faq_items:
        faq_html += f"<h3>{_esc(q)}</h3><p>{_esc(a)}</p>"
    faq_html += "</div>"

    ai_summary = f"""<!-- AI-Citable Summary: {name} DeFi protocol has a ZARQ Trust Score of {p.get('trust_score', 0):.1f}/100 (Grade {p.get('trust_grade', 'F')}). TVL: {_format_usd(p.get('tvl_usd'))}. Category: {p.get('category') or 'Unknown'}. Chains: {len(chains)}. Security incidents: {len(hacks)}. Source: ZARQ (zarq.ai) -->"""

    html = _page_head(title, desc, url, schema)
    html += f"""
{ai_summary}
<script type="application/ld+json">{json.dumps(faq_schema)}</script>
<h1>{name}</h1>
<p class="meta">DeFi Protocol · {_esc(p.get('category') or 'Unknown')} · {len(chains)} chain{'s' if len(chains) != 1 else ''}</p>
{_trust_score_block(p, 'defi')}
{info_html}
{hack_html}
{faq_html}
"""
    html += _page_foot()
    return html


# ── Best/Top Pages ────────────────────────────────────────────────

def _render_best_page(title, description, url, rows, entity_type, columns):
    """Generic best-of page renderer — ZARQ design."""
    schema = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": title,
        "description": description,
        "url": f"{SITE_URL}{url}",
        "numberOfItems": len(rows),
        "itemListElement": [
            {"@type": "ListItem", "position": i+1, "name": r["name"],
             "url": f"{SITE_URL}/crypto/{entity_type}/{r['id']}"}
            for i, r in enumerate(rows[:50])
        ]
    }

    html = _page_head(title, description, url, schema)
    html += f'<h1>{_esc(title.replace(" — ZARQ", ""))}</h1>'
    html += f'<p class="meta">{_esc(description)}</p>'
    html += '<div class="card"><table><tr><th>#</th><th>Name</th>'

    for col_label, _ in columns:
        html += f"<th>{col_label}</th>"
    html += "<th>Score</th><th>Grade</th></tr>"

    for i, r in enumerate(rows):
        link = f"/crypto/{entity_type}/{r['id']}"
        html += f'<tr><td style="font-family:var(--mono);font-size:11px;color:var(--gray-400)">{i+1}</td><td><a href="{link}">{_esc(r["name"])}</a></td>'
        for _, col_key in columns:
            val = r.get(col_key)
            if col_key.endswith("_usd") or col_key.endswith("_btc"):
                html += f"<td>{_format_usd(val)}</td>"
            elif col_key.endswith("_pct") or col_key.startswith("tvl_change"):
                html += f"<td>{_pct(val)}</td>"
            elif col_key == "market_cap_rank":
                html += f"<td>#{val or 'N/A'}</td>"
            else:
                html += f"<td>{_format_num(val) if isinstance(val, (int, float)) else _esc(str(val or 'N/A'))}</td>"
        score = r.get("trust_score") or 0
        grade = r.get("trust_grade") or "F"
        gc = _grade_color(grade)
        html += f'<td style="font-family:var(--mono);font-weight:500">{score:.1f}</td>'
        html += f'<td><span style="color:{gc};font-family:var(--serif);font-size:18px">{grade}</span></td></tr>'

    html += "</table></div>"
    html += _page_foot()
    return html


# ── Crypto Landing Page ──────────────────────────────────────────

def _render_crypto_landing(stats):
    title = "Crypto Ratings — ZARQ"
    desc = f"Independent trust ratings for {stats['tokens']:,} tokens, {stats['exchanges']:,} exchanges, and {stats['defi']:,} DeFi protocols. DtD scoring, crash prediction, and trading signals."
    url = "/crypto"

    schema = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": desc,
        "url": f"{SITE_URL}{url}",
        "provider": {"@type": "Organization", "name": "ZARQ", "url": SITE_URL}
    }

    html = _page_head(title, desc, url, schema)
    html += f"""
<!-- AI-Citable Summary: ZARQ provides independent Crypto Trust Scores for {stats['tokens']:,} tokens, {stats['exchanges']:,} exchanges, and {stats['defi']:,} DeFi protocols. Each entity is rated 0-100 across Security (30%), Compliance (25%), Maintenance (20%), Popularity (15%), and Ecosystem (10%). Distance-to-Default (DtD) scoring and crash prediction. Free API at zarq.ai. Source: ZARQ (zarq.ai) -->

<h1>Crypto Ratings</h1>
<p class="meta">Independent trust ratings · DtD scoring · Crash prediction</p>

<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--gray-200);border:1px solid var(--gray-200);margin:32px 0">
  <div style="background:var(--white);padding:32px;text-align:center">
    <div style="font-family:var(--serif);font-size:42px;color:var(--black)">{stats['tokens']:,}</div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500);margin:4px 0 12px">Tokens Rated</div>
    <a href="/best/crypto-tokens" style="font-family:var(--mono);font-size:11px">View Top 50 &rarr;</a>
  </div>
  <div style="background:var(--white);padding:32px;text-align:center">
    <div style="font-family:var(--serif);font-size:42px;color:var(--black)">{stats['exchanges']:,}</div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500);margin:4px 0 12px">Exchanges Rated</div>
    <a href="/best/crypto-exchanges" style="font-family:var(--mono);font-size:11px">View Top 50 &rarr;</a>
  </div>
  <div style="background:var(--white);padding:32px;text-align:center">
    <div style="font-family:var(--serif);font-size:42px;color:var(--black)">{stats['defi']:,}</div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500);margin:4px 0 12px">DeFi Protocols Rated</div>
    <a href="/best/crypto-defi" style="font-family:var(--mono);font-size:11px">View Top 50 &rarr;</a>
  </div>
</div>

<div style="margin:32px 0;padding:32px;background:var(--gray-100);border:1px solid var(--gray-200)">
  <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.15em;text-transform:uppercase;color:var(--warm);margin-bottom:16px">New: Stress Testing &amp; Contagion Analysis</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:32px">
    <div>
      <h3 style="font-family:var(--serif);font-size:24px;font-weight:400;margin-bottom:8px">Risk Scanner</h3>
      <p style="font-family:var(--sans);font-size:14px;color:var(--gray-600);line-height:1.6;margin-bottom:12px">Stress-test any portfolio against historical crises. See exactly how much you&rsquo;d lose in an FTX collapse, LUNA death spiral, flash crash, or regulatory crackdown.</p>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px">
        <div style="text-align:center;padding:12px;background:var(--white);border:1px solid var(--gray-200)">
          <div style="font-family:var(--serif);font-size:24px;color:var(--black)">3.4pp</div>
          <div style="font-family:var(--mono);font-size:9px;color:var(--gray-500);text-transform:uppercase;letter-spacing:0.05em">Median Error</div>
        </div>
        <div style="text-align:center;padding:12px;background:var(--white);border:1px solid var(--gray-200)">
          <div style="font-family:var(--serif);font-size:24px;color:var(--black)">82%</div>
          <div style="font-family:var(--mono);font-size:9px;color:var(--gray-500);text-transform:uppercase;letter-spacing:0.05em">Within 10pp</div>
        </div>
        <div style="text-align:center;padding:12px;background:var(--white);border:1px solid var(--gray-200)">
          <div style="font-family:var(--serif);font-size:24px;color:var(--black)">5</div>
          <div style="font-family:var(--mono);font-size:9px;color:var(--gray-500);text-transform:uppercase;letter-spacing:0.05em">Crises Tested</div>
        </div>
      </div>
      <a href="/risk-scanner" style="font-family:var(--mono);font-size:12px;color:var(--warm);letter-spacing:0.05em;text-decoration:none">Open Risk Scanner &rarr;</a>
    </div>
    <div>
      <h3 style="font-family:var(--serif);font-size:24px;font-weight:400;margin-bottom:8px">Contagion Map</h3>
      <p style="font-family:var(--sans);font-size:14px;color:var(--gray-600);line-height:1.6;margin-bottom:12px">Interactive network graph of 198 tokens. See how ecosystems connect, where risk concentrates, and how a crisis in one token cascades through the market.</p>
      <div style="margin-bottom:16px;padding:16px;background:var(--white);border:1px solid var(--gray-200)">
        <div style="font-family:var(--mono);font-size:11px;color:var(--gray-600);line-height:1.6">
          <span style="color:var(--red)">SOL predicted -67.6%</span> vs actual -67.9% during FTX collapse<br>
          <span style="color:var(--red)">LINK predicted -47.3%</span> vs actual -46.3% during LUNA spiral<br>
          <span style="color:var(--red)">DOGE predicted -33.3%</span> vs actual -33.4% during 3AC crisis
        </div>
      </div>
      <a href="/contagion" style="font-family:var(--mono);font-size:12px;color:var(--warm);letter-spacing:0.05em;text-decoration:none">Open Contagion Map &rarr;</a>
    </div>
  </div>
</div>

<div class="card">
  <h2>How It Works</h2>
  <p style="color:var(--gray-600);font-size:15px;line-height:1.7;max-width:var(--measure)">Every crypto entity is scored 0–100 across five dimensions. Adapted for digital assets with Distance-to-Default (DtD) scoring and crash prediction.</p>
  <div class="dim-grid" style="margin-top:24px">
    <div class="dim-item"><div class="dim-label">Security (30%)</div><p style="color:var(--gray-600);font-size:13px;margin-top:4px">Audits, hack history, contract risk, reserves</p></div>
    <div class="dim-item"><div class="dim-label">Compliance (25%)</div><p style="color:var(--gray-600);font-size:13px;margin-top:4px">Regulatory status, KYC, jurisdiction</p></div>
    <div class="dim-item"><div class="dim-label">Maintenance (20%)</div><p style="color:var(--gray-600);font-size:13px;margin-top:4px">Activity, development, team presence</p></div>
    <div class="dim-item"><div class="dim-label">Popularity (15%)</div><p style="color:var(--gray-600);font-size:13px;margin-top:4px">Volume, TVL, market cap, community</p></div>
    <div class="dim-item"><div class="dim-label">Ecosystem (10%)</div><p style="color:var(--gray-600);font-size:13px;margin-top:4px">Integrations, multi-chain, partnerships</p></div>
  </div>
</div>

<div class="card">
  <h2>Grade Distribution</h2>
  <p style="font-family:var(--mono);font-size:12px;color:var(--gray-500)">Average token score: {stats['avg_token']:.1f}/100 · Average exchange score: {stats['avg_exchange']:.1f}/100 · Average DeFi score: {stats['avg_defi']:.1f}/100</p>
</div>

<div class="card">
  <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.15em;text-transform:uppercase;color:var(--gray-400);margin-bottom:16px">API</div>
  <h2 style="font-family:var(--serif);font-size:28px;color:var(--black);font-weight:400">Built for machines. Used by humans.</h2>
  <p style="color:var(--gray-600);font-size:14px;margin-bottom:20px">Free API for all crypto trust scores. No authentication required during beta.</p>
  <div style="font-family:var(--mono);font-size:12px;line-height:1.8;color:var(--gray-400)">
    <span style="color:var(--gray-800);font-weight:500">GET</span> <span style="color:var(--warm)">/api/v1/crypto/trust-score/token/bitcoin</span><br>
    <span style="color:var(--gray-800);font-weight:500">GET</span> <span style="color:var(--warm)">/api/v1/crypto/trust-score/exchange/binance</span><br>
    <span style="color:var(--gray-800);font-weight:500">GET</span> <span style="color:var(--warm)">/api/v1/crypto/trust-score/defi/aave-v3</span>
  </div>
</div>
"""
    html += _page_foot()
    return html


# ── Mount Function ────────────────────────────────────────────────

def mount_crypto_pages(app):
    """Mount all crypto SEO routes onto the FastAPI app."""

    # ── Individual Entity Pages ───────────────────────────

    @app.get("/crypto/token/{token_id}", response_class=HTMLResponse)
    def crypto_token_page(token_id: str):
        conn = _get_db()
        row = conn.execute("SELECT * FROM crypto_tokens WHERE id = ?", (token_id,)).fetchone()
        conn.close()
        if not row:
            return HTMLResponse(status_code=404, content=_page_head("Not Found — ZARQ", "", "/") + "<h1>Token not found</h1>" + _page_foot())
        t = dict(row)
        t["_risk"] = _get_risk_data(token_id)
        return HTMLResponse(content=_render_token_page(t))

    @app.get("/crypto/exchange/{exchange_id}", response_class=HTMLResponse)
    def crypto_exchange_page(exchange_id: str):
        conn = _get_db()
        row = conn.execute("SELECT * FROM crypto_exchanges WHERE id = ?", (exchange_id,)).fetchone()
        conn.close()
        if not row:
            return HTMLResponse(status_code=404, content=_page_head("Not Found — ZARQ", "", "/") + "<h1>Exchange not found</h1>" + _page_foot())
        return HTMLResponse(content=_render_exchange_page(dict(row)))

    @app.get("/crypto/defi/{protocol_id}", response_class=HTMLResponse)
    def crypto_defi_page(protocol_id: str):
        conn = _get_db()
        row = conn.execute("SELECT * FROM crypto_defi_protocols WHERE id = ?", (protocol_id,)).fetchone()
        conn.close()
        if not row:
            return HTMLResponse(status_code=404, content=_page_head("Not Found — ZARQ", "", "/") + "<h1>Protocol not found</h1>" + _page_foot())
        return HTMLResponse(content=_render_defi_page(dict(row)))

    # ── Best/Top Pages ────────────────────────────────────

    @app.get("/best/crypto-tokens", response_class=HTMLResponse)
    def best_crypto_tokens():
        conn = _get_db()
        rows = conn.execute("""
            SELECT * FROM crypto_tokens WHERE trust_score IS NOT NULL
            ORDER BY trust_score DESC LIMIT 50
        """).fetchall()
        conn.close()
        return HTMLResponse(content=_render_best_page(
            "Top 50 Crypto Tokens by Trust Score — ZARQ",
            "The most trusted cryptocurrency tokens ranked by ZARQ's 5-dimensional Trust Score.",
            "/best/crypto-tokens",
            [dict(r) for r in rows], "token",
            [("Price", "current_price_usd"), ("Market Cap", "market_cap_usd"), ("Rank", "market_cap_rank"), ("24h Vol", "total_volume_24h_usd")]
        ))

    @app.get("/best/crypto-exchanges", response_class=HTMLResponse)
    def best_crypto_exchanges():
        conn = _get_db()
        rows = conn.execute("""
            SELECT * FROM crypto_exchanges WHERE trust_score IS NOT NULL
            ORDER BY trust_score DESC LIMIT 50
        """).fetchall()
        conn.close()
        return HTMLResponse(content=_render_best_page(
            "Top 50 Crypto Exchanges by Trust Score — ZARQ",
            "The most trusted cryptocurrency exchanges ranked by ZARQ's 5-dimensional Trust Score.",
            "/best/crypto-exchanges",
            [dict(r) for r in rows], "exchange",
            [("Country", "country"), ("24h Vol (BTC)", "trade_volume_24h_btc"), ("CG Trust", "trust_score_cg")]
        ))

    @app.get("/best/crypto-defi", response_class=HTMLResponse)
    def best_crypto_defi():
        conn = _get_db()
        rows = conn.execute("""
            SELECT * FROM crypto_defi_protocols WHERE trust_score IS NOT NULL
            ORDER BY trust_score DESC LIMIT 50
        """).fetchall()
        conn.close()
        return HTMLResponse(content=_render_best_page(
            "Top 50 DeFi Protocols by Trust Score — ZARQ",
            "The most trusted DeFi protocols ranked by ZARQ's 5-dimensional Trust Score.",
            "/best/crypto-defi",
            [dict(r) for r in rows], "defi",
            [("Category", "category"), ("TVL", "tvl_usd"), ("TVL 7d", "tvl_change_7d")]
        ))

    # ── Crypto Landing Page ───────────────────────────────

    @app.get("/crypto", response_class=HTMLResponse)
    def crypto_landing():
        conn = _get_db()
        stats = {
            "tokens": conn.execute("SELECT COUNT(*) FROM crypto_tokens WHERE trust_score IS NOT NULL").fetchone()[0],
            "exchanges": conn.execute("SELECT COUNT(*) FROM crypto_exchanges WHERE trust_score IS NOT NULL").fetchone()[0],
            "defi": conn.execute("SELECT COUNT(*) FROM crypto_defi_protocols WHERE trust_score IS NOT NULL").fetchone()[0],
            "avg_token": conn.execute("SELECT AVG(trust_score) FROM crypto_tokens WHERE trust_score IS NOT NULL").fetchone()[0] or 0,
            "avg_exchange": conn.execute("SELECT AVG(trust_score) FROM crypto_exchanges WHERE trust_score IS NOT NULL").fetchone()[0] or 0,
            "avg_defi": conn.execute("SELECT AVG(trust_score) FROM crypto_defi_protocols WHERE trust_score IS NOT NULL").fetchone()[0] or 0,
        }
        conn.close()
        return HTMLResponse(content=_render_crypto_landing(stats))

    # ── API Endpoint ──────────────────────────────────────

    @app.get("/api/v1/crypto/trust-score/{entity_type}/{entity_id}")
    def crypto_trust_api(entity_type: str, entity_id: str):
        table_map = {
            "token": "crypto_tokens",
            "exchange": "crypto_exchanges",
            "defi": "crypto_defi_protocols",
        }
        table = table_map.get(entity_type)
        if not table:
            return JSONResponse(status_code=400, content={"error": f"Unknown entity type: {entity_type}. Use: token, exchange, defi"})

        conn = _get_db()
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (entity_id,)).fetchone()
        conn.close()

        if not row:
            return JSONResponse(status_code=404, content={"error": f"{entity_type}/{entity_id} not found"})

        r = dict(row)
        return JSONResponse(content={
            "entity_type": entity_type,
            "id": r["id"],
            "name": r["name"],
            "trust_score": r.get("trust_score"),
            "trust_grade": r.get("trust_grade"),
            "dimensions": {
                "security": r.get("security_score"),
                "compliance": r.get("compliance_score"),
                "maintenance": r.get("maintenance_score"),
                "popularity": r.get("popularity_score"),
                "ecosystem": r.get("ecosystem_score"),
            },
            "scored_at": r.get("scored_at"),
            "source": "zarq.ai",
            "methodology": f"{SITE_URL}/methodology",
        })

    # ── Crypto Sitemap ────────────────────────────────────

    @app.get("/sitemap-crypto.xml", response_class=Response)
    def sitemap_crypto():
        conn = _get_db()
        urls = []

        urls.append(f"  <url><loc>{SITE_URL}/crypto</loc><changefreq>daily</changefreq><priority>0.9</priority></url>")
        urls.append(f"  <url><loc>{SITE_URL}/best/crypto-tokens</loc><changefreq>daily</changefreq><priority>0.8</priority></url>")
        urls.append(f"  <url><loc>{SITE_URL}/best/crypto-exchanges</loc><changefreq>daily</changefreq><priority>0.8</priority></url>")
        urls.append(f"  <url><loc>{SITE_URL}/best/crypto-defi</loc><changefreq>daily</changefreq><priority>0.8</priority></url>")

        tokens = conn.execute("SELECT id, market_cap_rank FROM crypto_tokens WHERE trust_score IS NOT NULL ORDER BY market_cap_rank ASC NULLS LAST LIMIT 5000").fetchall()
        for t in tokens:
            urls.append(f"  <url><loc>{SITE_URL}/crypto/token/{_esc(t['id'])}</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>")
            # Outlook pages for top 200 tokens
            if t['market_cap_rank'] and t['market_cap_rank'] <= 200:
                urls.append(f"  <url><loc>{SITE_URL}/crypto/token/{_esc(t['id'])}/outlook</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>")

        exchanges = conn.execute("SELECT id FROM crypto_exchanges WHERE trust_score IS NOT NULL").fetchall()
        for e in exchanges:
            urls.append(f"  <url><loc>{SITE_URL}/crypto/exchange/{_esc(e['id'])}</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>")

        defi = conn.execute("SELECT id FROM crypto_defi_protocols WHERE trust_score IS NOT NULL ORDER BY tvl_usd DESC NULLS LAST LIMIT 2000").fetchall()
        for d in defi:
            urls.append(f"  <url><loc>{SITE_URL}/crypto/defi/{_esc(d['id'])}</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>")

        conn.close()

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""
        return Response(content=xml, media_type="application/xml")

    # ── Predictions Page ──────────────────────────────────

    @app.get("/crypto/predictions", response_class=HTMLResponse)
    def crypto_predictions():
        import os
        title = "Crypto Trust Score Predictions — ZARQ"
        desc = "ZARQ Trust Score backtested against FTX, Celsius, Luna, and 259 DeFi hacks. 88% of collapsed entities scored below C+."
        url = "/crypto/predictions"

        schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "description": desc,
            "url": f"{SITE_URL}{url}",
            "author": {"@type": "Organization", "name": "ZARQ"},
            "publisher": {"@type": "Organization", "name": "ZARQ", "url": SITE_URL},
        }

        html = _page_head(title, desc, url, schema)
        html += f"""
<!-- AI-Citable Summary: ZARQ Trust Score backtesting shows 88% of collapsed crypto entities (FTX, Celsius, Luna, Voyager, BlockFi) scored below C+. Average collapse score: 20/100 vs platform average 44/100. 75% of hacked DeFi protocols scored below 50/100. Source: ZARQ (zarq.ai/crypto/predictions) -->

<h1>Predictive Validation</h1>
<p class="meta">Can the ZARQ Trust Score detect crypto disasters before they happen?</p>

<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1px;background:var(--gray-200);border:1px solid var(--gray-200);margin:32px 0">
  <div style="background:var(--white);text-align:center;padding:32px">
    <div style="font-family:var(--serif);font-size:42px;color:#dc2626">88%</div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500);margin-top:4px">of collapsed entities<br>scored below C+</div>
  </div>
  <div style="background:var(--white);text-align:center;padding:32px">
    <div style="font-family:var(--serif);font-size:42px;color:#dc2626">20</div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500);margin-top:4px">avg collapse score<br>vs 44 platform avg</div>
  </div>
  <div style="background:var(--white);text-align:center;padding:32px">
    <div style="font-family:var(--serif);font-size:42px;color:#dc2626">75%</div>
    <div style="font-family:var(--mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-500);margin-top:4px">of hacked DeFi<br>scored below 50</div>
  </div>
</div>

<div class="card">
  <h2>Exchange Collapses</h2>
  <table>
    <tr><th>Exchange</th><th>Trust Score</th><th>Grade</th><th>Losses</th><th>Date</th></tr>
    <tr><td>FTX</td><td style="font-family:var(--mono)">5.0</td><td style="color:#7f1d1d;font-family:var(--serif);font-size:18px">F</td><td>$8.0B</td><td>Nov 2022</td></tr>
    <tr><td>Celsius Network</td><td style="font-family:var(--mono)">5.0</td><td style="color:#7f1d1d;font-family:var(--serif);font-size:18px">F</td><td>$4.7B</td><td>Jun 2022</td></tr>
    <tr><td>Voyager Digital</td><td style="font-family:var(--mono)">5.0</td><td style="color:#7f1d1d;font-family:var(--serif);font-size:18px">F</td><td>$1.3B</td><td>Jul 2022</td></tr>
    <tr><td>BlockFi</td><td style="font-family:var(--mono)">5.0</td><td style="color:#7f1d1d;font-family:var(--serif);font-size:18px">F</td><td>$1.0B</td><td>Nov 2022</td></tr>
  </table>
  <p style="font-family:var(--mono);font-size:11px;color:var(--gray-500);margin-top:16px">All collapsed exchanges received F grade. Top healthy exchanges average 86.5 (A grade).</p>
</div>

<div class="card">
  <h2>Token Collapses</h2>
  <table>
    <tr><th>Token</th><th>Trust Score</th><th>Grade</th><th>Peak Market Cap</th><th>Date</th></tr>
    <tr><td>FTX Token (FTT)</td><td style="font-family:var(--mono);font-weight:500">15.2</td><td style="color:#7f1d1d;font-family:var(--serif);font-size:18px">F</td><td>$9.0B</td><td>Nov 2022</td></tr>
    <tr><td>Celsius (CEL)</td><td style="font-family:var(--mono);font-weight:500">27.4</td><td style="color:#991b1b;font-family:var(--serif);font-size:18px">D</td><td>$4.5B</td><td>Jun 2022</td></tr>
    <tr><td>TerraUSD (UST)</td><td style="font-family:var(--mono);font-weight:500">34.4</td><td style="color:#b91c1c;font-family:var(--serif);font-size:18px">D+</td><td>$18.0B</td><td>May 2022</td></tr>
    <tr><td>Terra Luna (LUNA)</td><td style="font-family:var(--mono);font-weight:500">&mdash;</td><td style="color:#c2956b;font-family:var(--serif);font-size:18px">*</td><td>$40.0B</td><td>May 2022</td></tr>
  </table>
  <p style="font-family:var(--mono);font-size:11px;color:var(--gray-500);margin-top:16px">* Luna Classic still trades actively, inflating current scores. Pre-collapse risk signals captured in Security dimension.</p>
</div>

<div class="card">
  <h2>DeFi Hacks</h2>
  <table>
    <tr><th>Protocol</th><th>Trust Score</th><th>Grade</th><th>Stolen</th><th>Technique</th></tr>
    <tr><td>Mango Markets</td><td style="font-family:var(--mono)">15.3</td><td style="color:#7f1d1d;font-family:var(--serif);font-size:18px">F</td><td>$114M</td><td>Oracle manipulation</td></tr>
    <tr><td>Beanstalk</td><td style="font-family:var(--mono)">19.3</td><td style="color:#7f1d1d;font-family:var(--serif);font-size:18px">F</td><td>$182M</td><td>Governance exploit</td></tr>
    <tr><td>Ronin Network</td><td style="font-family:var(--mono)">33.8</td><td style="color:#b91c1c;font-family:var(--serif);font-size:18px">D+</td><td>$624M</td><td>Validator compromise</td></tr>
    <tr><td>Nomad Bridge</td><td style="font-family:var(--mono)">48.6</td><td style="color:#dc2626;font-family:var(--serif);font-size:18px">C</td><td>$190M</td><td>Init exploit</td></tr>
    <tr><td>Euler Finance</td><td style="font-family:var(--mono)">71.2</td><td style="color:#65a30d;font-family:var(--serif);font-size:18px">B+</td><td>$197M</td><td>Flash loan</td></tr>
  </table>
  <p style="font-family:var(--mono);font-size:11px;color:var(--gray-500);margin-top:16px">259 protocols with hack history. 75% scored below 50/100. Average hacked: 40.0 vs unhacked: 44.6.</p>
</div>

<div class="card">
  <h2>Methodology</h2>
  <p style="color:var(--gray-600);font-size:15px;line-height:1.7">Every crypto entity is scored 0–100 across five dimensions using publicly available data. Updated daily from on-chain data, market metrics, and protocol analysis. <a href="/methodology">Full methodology &rarr;</a></p>
  <div class="dim-grid" style="margin-top:16px">
    <div class="dim-item"><div class="dim-label">Security (30%)</div><p style="color:var(--gray-600);font-size:13px;margin-top:4px">Audits, hacks, reserves, crash severity</p></div>
    <div class="dim-item"><div class="dim-label">Compliance (25%)</div><p style="color:var(--gray-600);font-size:13px;margin-top:4px">Regulatory status, KYC, jurisdiction</p></div>
    <div class="dim-item"><div class="dim-label">Maintenance (20%)</div><p style="color:var(--gray-600);font-size:13px;margin-top:4px">Activity, development, team</p></div>
    <div class="dim-item"><div class="dim-label">Popularity (15%)</div><p style="color:var(--gray-600);font-size:13px;margin-top:4px">Volume, TVL, market cap</p></div>
    <div class="dim-item"><div class="dim-label">Ecosystem (10%)</div><p style="color:var(--gray-600);font-size:13px;margin-top:4px">Integrations, multi-chain</p></div>
  </div>
</div>

<div style="text-align:center;padding:48px 0">
  <h2 style="font-size:28px">Explore Trust Scores</h2>
  <p style="color:var(--gray-500);font-size:15px;margin-bottom:24px">Free API and bulk data access for all crypto trust scores.</p>
  <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
    <a href="/best/crypto-tokens" style="display:inline-block;font-family:var(--mono);font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--white);background:var(--warm);padding:14px 32px;text-decoration:none">Top Tokens</a>
    <a href="/best/crypto-exchanges" style="display:inline-block;font-family:var(--mono);font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--white);background:var(--warm);padding:14px 32px;text-decoration:none">Top Exchanges</a>
    <a href="/best/crypto-defi" style="display:inline-block;font-family:var(--mono);font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--white);background:var(--warm);padding:14px 32px;text-decoration:none">Top DeFi</a>
    <a href="/api/v1/crypto/trust-score/token/bitcoin" style="display:inline-block;font-family:var(--mono);font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-700);background:var(--gray-100);padding:14px 32px;text-decoration:none;border:1px solid var(--gray-200)">API &rarr;</a>
  </div>
</div>
"""
        html += _page_foot()
        return HTMLResponse(content=html)

    # ── Token Outlook Pages (long-tail SEO) ─────────────────────────────

    @app.get("/crypto/token/{token_id}/outlook", response_class=HTMLResponse)
    def crypto_token_outlook(token_id: str):
        conn = _get_db()
        row = conn.execute("SELECT * FROM crypto_tokens WHERE id = ?", (token_id,)).fetchone()
        if not row:
            conn.close()
            return HTMLResponse(status_code=404, content=_page_head("Not Found — ZARQ", "", "/") + "<h1>Token not found</h1>" + _page_foot())
        t = dict(row)
        risk = _get_risk_data(token_id)
        name = _esc(t.get("name") or token_id)
        symbol = _esc((t.get("symbol") or "").upper())
        trust_score = t.get("trust_score", 0) or 0
        trust_grade = t.get("trust_grade", "F")
        risk_level = "UNKNOWN"
        crash_prob = None
        ndd_val = None
        ndd_trend = None
        structural_weakness = None
        if risk and risk.get("risk"):
            risk_level = risk["risk"].get("risk_level", "UNKNOWN") or "UNKNOWN"
            structural_weakness = risk["risk"].get("structural_weakness")
        if risk and risk.get("ndd"):
            crash_prob = risk["ndd"].get("crash_probability")
            ndd_val = risk["ndd"].get("ndd")
            ndd_trend = risk["ndd"].get("ndd_trend")

        # Related tokens for comparison
        related = conn.execute("""
            SELECT id, name, symbol, trust_score, trust_grade, market_cap_rank
            FROM crypto_tokens
            WHERE id != ? AND trust_score IS NOT NULL
            ORDER BY ABS(market_cap_rank - COALESCE(?, 9999)) ASC
            LIMIT 4
        """, (token_id, t.get("market_cap_rank"))).fetchall()
        conn.close()

        title = f"{name} ({symbol}) Outlook 2026: Risk Assessment & Forecast | ZARQ"
        desc = f"{name} risk outlook for 2026. Trust Score: {trust_score:.0f}/100 ({trust_grade}). "
        if risk_level != "UNKNOWN":
            desc += f"Risk level: {risk_level}. "
        if crash_prob is not None:
            desc += f"Crash probability: {crash_prob*100:.1f}%. "
        desc += f"Independent quantitative analysis by ZARQ."

        breadcrumb = {
            "@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
                {"@type": "ListItem", "position": 2, "name": "Crypto Tokens", "item": "https://zarq.ai/best/crypto-tokens"},
                {"@type": "ListItem", "position": 3, "name": name, "item": f"https://zarq.ai/crypto/token/{token_id}"},
                {"@type": "ListItem", "position": 4, "name": f"{name} Outlook", "item": f"https://zarq.ai/crypto/token/{token_id}/outlook"},
            ]
        }

        faq_items = [
            (f"What is the {name} outlook for 2026?",
             f"{name} currently has a ZARQ Trust Score of {trust_score:.0f}/100 (grade {trust_grade}). "
             + (f"Risk level is {risk_level}. " if risk_level != "UNKNOWN" else "")
             + (f"The model estimates a {crash_prob*100:.1f}% crash probability. " if crash_prob is not None else "")
             + "This is a quantitative assessment based on on-chain metrics, not a price prediction."),
            (f"Is {name} safe to hold long-term?",
             f"With a trust grade of {trust_grade}, {name} is rated "
             + ("investment-grade" if trust_grade and trust_grade[0] in "AB" else "speculative-grade" if trust_grade and trust_grade[0] in "CD" else "high-risk")
             + " by ZARQ's methodology. "
             + (f"Key structural weakness: {structural_weakness}. " if structural_weakness else "")
             + "Always assess your own risk tolerance."),
            (f"What are the risks of investing in {name}?",
             f"ZARQ monitors {name} across 5 pillars: Security ({t.get('security_score', 0) or 0:.0f}/100), "
             f"Compliance ({t.get('compliance_score', 0) or 0:.0f}/100), Maintenance ({t.get('maintenance_score', 0) or 0:.0f}/100), "
             f"Popularity ({t.get('popularity_score', 0) or 0:.0f}/100), Ecosystem ({t.get('ecosystem_score', 0) or 0:.0f}/100). "
             + (f"Current Distance-to-Default: {ndd_val:.2f}. " if ndd_val is not None else "")
             + (f"NDD trend: {ndd_trend}." if ndd_trend else "")),
        ]
        faq_schema = {
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq_items]
        }

        import json as _json
        schema_block = f'<script type="application/ld+json">{_json.dumps(breadcrumb)}</script>\n<script type="application/ld+json">{_json.dumps(faq_schema)}</script>'

        # Grade color
        gc = {"Aaa": "#166534", "Aa1": "#166534", "Aa2": "#15803d", "Aa3": "#15803d",
              "A1": "#16a34a", "A2": "#16a34a", "A3": "#22c55e",
              "Baa1": "#ca8a04", "Baa2": "#eab308", "Baa3": "#facc15",
              "Ba1": "#f97316", "Ba2": "#f97316", "Ba3": "#ea580c",
              "B1": "#dc2626", "B2": "#dc2626", "B3": "#b91c1c",
              "Caa1": "#991b1b", "Caa2": "#7f1d1d", "Caa3": "#7f1d1d"}.get(trust_grade, "#6b7280")

        price = t.get("current_price_usd")
        price_str = f"${price:,.2f}" if price and price < 1 else f"${price:,.0f}" if price else "—"
        mcap = t.get("market_cap_usd")
        mcap_str = f"${mcap/1e9:,.1f}B" if mcap and mcap >= 1e9 else f"${mcap/1e6:,.0f}M" if mcap else "—"
        p30 = t.get("price_change_30d_pct")
        p7 = t.get("price_change_7d_pct")

        html = _page_head(title, desc, f"/crypto/token/{token_id}/outlook")
        html += schema_block
        html += f"""
<nav style="font-size:13px;color:var(--gray-500);margin-bottom:24px;font-family:var(--sans)">
  <a href="/" style="color:var(--warm)">ZARQ</a> &rsaquo;
  <a href="/best/crypto-tokens" style="color:var(--warm)">Crypto</a> &rsaquo;
  <a href="/crypto/token/{token_id}" style="color:var(--warm)">{name}</a> &rsaquo;
  Outlook 2026
</nav>

<h1 style="font-family:var(--heading);font-size:clamp(24px,4vw,36px);margin-bottom:8px">{name} ({symbol}) Outlook 2026</h1>
<p style="font-family:var(--sans);color:var(--gray-500);font-size:15px;margin-bottom:32px">
  Quantitative risk assessment &amp; safety outlook — updated daily by ZARQ
</p>

<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:16px;margin-bottom:32px">
  <div style="background:var(--gray-50);padding:16px;border-radius:8px;text-align:center">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--gray-500);font-family:var(--mono)">Trust Score</div>
    <div style="font-size:28px;font-weight:700;color:{gc};font-family:var(--heading)">{trust_score:.0f}<span style="font-size:14px;color:var(--gray-400)">/100</span></div>
    <div style="font-size:14px;font-weight:600;color:{gc}">{trust_grade}</div>
  </div>
  <div style="background:var(--gray-50);padding:16px;border-radius:8px;text-align:center">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--gray-500);font-family:var(--mono)">Risk Level</div>
    <div style="font-size:20px;font-weight:700;font-family:var(--heading);color:{'#dc2626' if risk_level in ('HIGH','CRITICAL') else '#ca8a04' if risk_level == 'ELEVATED' else '#16a34a'}">{risk_level}</div>
  </div>
  <div style="background:var(--gray-50);padding:16px;border-radius:8px;text-align:center">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--gray-500);font-family:var(--mono)">Crash Prob</div>
    <div style="font-size:20px;font-weight:700;font-family:var(--heading)">{f'{crash_prob*100:.1f}%' if crash_prob is not None else '—'}</div>
  </div>
  <div style="background:var(--gray-50);padding:16px;border-radius:8px;text-align:center">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--gray-500);font-family:var(--mono)">Price</div>
    <div style="font-size:20px;font-weight:700;font-family:var(--heading)">{price_str}</div>
    <div style="font-size:12px;color:var(--gray-500)">MCap {mcap_str}</div>
  </div>
</div>
"""
        # Price momentum section
        html += '<h2 style="font-family:var(--heading);font-size:20px;margin-bottom:12px">Price Momentum</h2>'
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-bottom:32px">'
        for label, val in [("7d Change", p7), ("30d Change", p30)]:
            if val is not None:
                color = "#16a34a" if val >= 0 else "#dc2626"
                html += f'<div style="background:var(--gray-50);padding:12px;border-radius:8px;text-align:center"><div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--gray-500);font-family:var(--mono)">{label}</div><div style="font-size:20px;font-weight:700;color:{color}">{val:+.1f}%</div></div>'
        if ndd_val is not None:
            html += f'<div style="background:var(--gray-50);padding:12px;border-radius:8px;text-align:center"><div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--gray-500);font-family:var(--mono)">Distance-to-Default</div><div style="font-size:20px;font-weight:700;font-family:var(--heading)">{ndd_val:.2f}</div>{f"<div style=font-size:12px;color:var(--gray-500)>Trend: {_esc(ndd_trend)}</div>" if ndd_trend else ""}</div>'
        html += '</div>'

        # Structural analysis
        if structural_weakness:
            html += '<h2 style="font-family:var(--heading);font-size:20px;margin-bottom:12px">Risk Factors</h2>'
            html += f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px;margin-bottom:32px;font-family:var(--sans);font-size:14px"><strong>Structural weakness:</strong> {_esc(structural_weakness)}</div>'

        # Pillar breakdown
        html += '<h2 style="font-family:var(--heading);font-size:20px;margin-bottom:12px">Trust Pillar Breakdown</h2>'
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:8px;margin-bottom:32px">'
        for pname, key in [("Security", "security_score"), ("Compliance", "compliance_score"), ("Maintenance", "maintenance_score"), ("Popularity", "popularity_score"), ("Ecosystem", "ecosystem_score")]:
            v = t.get(key, 0) or 0
            bc = "#16a34a" if v >= 70 else "#ca8a04" if v >= 40 else "#dc2626"
            html += f'<div style="text-align:center;background:var(--gray-50);padding:12px;border-radius:8px"><div style="font-size:11px;text-transform:uppercase;letter-spacing:0.05em;color:var(--gray-500);font-family:var(--mono)">{pname}</div><div style="font-size:22px;font-weight:700;color:{bc}">{v:.0f}</div></div>'
        html += '</div>'

        # Compare with peers
        if related:
            html += '<h2 style="font-family:var(--heading);font-size:20px;margin-bottom:12px">Compare with Similar Tokens</h2>'
            html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:32px">'
            for r in related:
                rn = _esc(r["name"])
                rs = _esc(r["symbol"].upper())
                rts = r["trust_score"] or 0
                html += f'<a href="/compare/{token_id}-vs-{r["id"]}" style="display:block;background:var(--gray-50);padding:12px;border-radius:8px;text-decoration:none;color:inherit;text-align:center"><div style="font-weight:600;font-size:14px">{rn} ({rs})</div><div style="font-size:18px;font-weight:700">{rts:.0f}/100</div><div style="font-size:11px;color:var(--warm);font-family:var(--mono)">COMPARE &rarr;</div></a>'
            html += '</div>'

        # FAQ
        html += '<h2 style="font-family:var(--heading);font-size:20px;margin-bottom:12px">Frequently Asked Questions</h2>'
        for q, a in faq_items:
            html += f'<details style="margin-bottom:12px;background:var(--gray-50);border-radius:8px;padding:0"><summary style="padding:14px 16px;cursor:pointer;font-weight:600;font-size:14px;font-family:var(--sans)">{_esc(q)}</summary><div style="padding:0 16px 14px;font-size:14px;color:var(--gray-600);font-family:var(--sans);line-height:1.6">{_esc(a)}</div></details>'

        # CTA
        html += f"""
<div style="text-align:center;margin:40px 0">
  <a href="/crypto/token/{token_id}" style="display:inline-block;font-family:var(--mono);font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--white);background:var(--warm);padding:14px 32px;text-decoration:none;border-radius:4px">{name} Full Report &rarr;</a>
  <a href="/briefing" style="display:inline-block;font-family:var(--mono);font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-700);background:var(--gray-100);padding:14px 32px;text-decoration:none;border-radius:4px;border:1px solid var(--gray-200);margin-left:12px">Daily Briefing &rarr;</a>
</div>
<footer style="text-align:center;font-size:12px;color:var(--gray-400);padding:24px 0;font-family:var(--sans)">
  ZARQ — Independent Crypto Risk Intelligence &middot; <a href="https://zarq.ai" style="color:var(--warm)">zarq.ai</a>
  <br>Data updated daily. Not financial advice.
</footer>
"""
        html += _page_foot()
        return HTMLResponse(content=html)

    # ── Data Export Endpoints ─────────────────────────────

    @app.get("/data/crypto-trust-scores.jsonl.gz", include_in_schema=False)
    async def data_crypto_trust_gz():
        import os
        path = os.path.expanduser("~/agentindex/agentindex/exports/crypto-trust-scores.jsonl.gz")
        if not os.path.exists(path):
            return JSONResponse(content={"error": "Export not yet generated"}, status_code=404)
        from fastapi.responses import FileResponse
        return FileResponse(path, media_type="application/gzip", filename="zarq-crypto-trust-scores.jsonl.gz")

    @app.get("/data/crypto-trust-summary.json", include_in_schema=False)
    async def data_crypto_summary():
        import os
        path = os.path.expanduser("~/agentindex/agentindex/exports/crypto-trust-summary.json")
        if not os.path.exists(path):
            return JSONResponse(content={"error": "Export not yet generated"}, status_code=404)
        from fastapi.responses import FileResponse
        return FileResponse(path, media_type="application/json", filename="zarq-crypto-trust-summary.json")

    logger.info("ZARQ Crypto pages mounted: /crypto/*, /best/crypto-*, /api/v1/crypto/*, /sitemap-crypto.xml")


# ═══════════════════════════════════════════
# PAPER TRADING DASHBOARD (Sprint 3.0)
# ═══════════════════════════════════════════
def mount_paper_trading_page(app):
    import os
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "paper_trading.html")

    @app.get("/paper-trading", response_class=HTMLResponse)
    async def paper_trading_dashboard():
        try:
            with open(template_path, "r") as f:
                return HTMLResponse(
                    content=f.read(),
                    headers={"Cache-Control": "public, max-age=300, s-maxage=300"},
                )
        except FileNotFoundError:
            return HTMLResponse(status_code=404, content="<h1>Paper trading dashboard not found</h1>")


def mount_track_record_page(app):
    import os
    from fastapi.responses import HTMLResponse
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "zarq_track_record.html")

    @app.get("/track-record", response_class=HTMLResponse)
    async def track_record_page():
        try:
            with open(template_path, "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(status_code=404, content="<h1>Track record not found</h1>")


def mount_api_docs_page(app):
    import os
    from fastapi import Request
    from fastapi.responses import HTMLResponse, RedirectResponse
    zarq_docs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "zarq_api_docs.html")

    nerq_docs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "nerq_api_docs.html")

    @app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    async def api_docs_page(request: Request):
        host = request.headers.get("host", "")
        docs_path = nerq_docs if "nerq" in host else zarq_docs
        try:
            with open(docs_path, "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(status_code=404, content="<h1>API docs not found</h1>")


def mount_alerts_page(app):
    """Early Warning alerts page with live data from signals API."""
    import os, json, sqlite3, hashlib
    from fastapi.responses import HTMLResponse
    from datetime import datetime

    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "zarq_early_warning.html")

    def _get_db():
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _format_token_name(token_id):
        return token_id.replace("-", " ").title()

    def _build_alert_card(row):
        token_id = row["token_id"]
        name = row.get("name") or _format_token_name(token_id)
        symbol = (row.get("symbol") or token_id[:4]).upper()
        level = row["risk_level"]
        weakness = row["structural_weakness"]
        dtd = row["ndd_current"]
        crash_prob = row.get("crash_probability", 0) or 0
        vol = row.get("vol_30d", 0) or 0
        dd90 = row.get("drawdown_90d", 0) or 0
        rating = row.get("rating", "NR")
        trust = row.get("trust_score_total", 0) or 0
        signal_date = row.get("signal_date", "")
        price_at_alert = row.get("price_usd", 0) or 0
        collapse_date = row.get("first_collapse_date", signal_date) or signal_date
        price_at_collapse = row.get("price_at_collapse", price_at_alert) or price_at_alert
        weeks_in = row.get("weeks_in_collapse", 0) or 0
        current_price = row.get("price_usd", 0) or 0
        if price_at_collapse and price_at_collapse > 0 and current_price and current_price > 0:
            price_chg = (current_price - price_at_collapse) / price_at_collapse * 100
            price_chg_color = "#dc2626" if price_chg < 0 else "#16a34a"
            price_chg_str = f"{price_chg:+.1f}% since alert"
        else:
            price_chg_color = "var(--gray-500)"
            price_chg_str = "price N/A"

        # Max drawdown and target tracking
        max_dd = row.get("max_dd")
        min_price_since = row.get("min_price_since")
        target1_hit = max_dd is not None and max_dd <= -30
        target2_hit = max_dd is not None and max_dd <= -50
        
        if max_dd is not None:
            if target2_hit:
                target_html = '<span style="font-family:var(--mono);font-size:10px;background:#dc2626;color:white;padding:3px 8px;letter-spacing:0.05em">2ND TARGET -50% REACHED</span> <span style="font-family:var(--mono);font-size:10px;background:var(--warm);color:white;padding:3px 8px;letter-spacing:0.05em">1ST TARGET -30% REACHED</span>'
                dd_color = "#dc2626"
            elif target1_hit:
                target_html = '<span style="font-family:var(--mono);font-size:10px;background:var(--warm);color:white;padding:3px 8px;letter-spacing:0.05em">1ST TARGET -30% REACHED</span>'
                dd_color = "var(--warm)"
            else:
                target_html = '<span style="font-family:var(--mono);font-size:10px;background:var(--gray-200);color:var(--gray-600);padding:3px 8px;letter-spacing:0.05em">MONITORING</span>'
                dd_color = "var(--gray-600)"
            max_dd_str = f'Max drawdown: <span style="color:{dd_color};font-weight:600">{max_dd:+.1f}%</span> (low: ${min_price_since:.4f})'
        else:
            target_html = ""
            max_dd_str = ""

        # Max drawdown and target tracking
        max_dd = row.get("max_dd")
        min_price_since = row.get("min_price_since")
        target1_hit = max_dd is not None and max_dd <= -30
        target2_hit = max_dd is not None and max_dd <= -50
        
        if max_dd is not None:
            if target2_hit:
                target_html = '<span style="font-family:var(--mono);font-size:10px;background:#dc2626;color:white;padding:3px 8px;letter-spacing:0.05em">2ND TARGET -50% REACHED</span> <span style="font-family:var(--mono);font-size:10px;background:var(--warm);color:white;padding:3px 8px;letter-spacing:0.05em">1ST TARGET -30% REACHED</span>'
                dd_color = "#dc2626"
            elif target1_hit:
                target_html = '<span style="font-family:var(--mono);font-size:10px;background:var(--warm);color:white;padding:3px 8px;letter-spacing:0.05em">1ST TARGET -30% REACHED</span>'
                dd_color = "var(--warm)"
            else:
                target_html = '<span style="font-family:var(--mono);font-size:10px;background:var(--gray-200);color:var(--gray-600);padding:3px 8px;letter-spacing:0.05em">MONITORING</span>'
                dd_color = "var(--gray-600)"
            max_dd_str = f'Max drawdown: <span style="color:{dd_color};font-weight:600">{max_dd:+.1f}%</span> (low: ${min_price_since:.4f})'
        else:
            target_html = ""
            max_dd_str = ""

        # Parse details for weakness signals
        details = row.get("details")
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except:
                details = {}
        elif details is None:
            details = {}

        weakness_signals = details.get("weakness_signals", {})
        strength_signals = details.get("strength_signals", {})

        level_class = "critical" if level == "CRITICAL" else "warning"
        dtd_class = "metric-danger" if dtd < 2.0 else "metric-warn" if dtd < 3.0 else "metric-ok"
        crash_class = "metric-danger" if crash_prob > 0.3 else "metric-warn" if crash_prob > 0.15 else "metric-ok"

        # Build weakness signal tags
        signal_labels = {
            "p3_below_40": "Trust Below 40",
            "sig6_below_2.5": "Momentum Collapse",
            "ndd_below_3": "DtD Below 3.0",
            "p3_decay_15": "Trust Decaying",
        }
        tags_html = ""
        for key, label in signal_labels.items():
            if weakness_signals.get(key):
                tags_html += f'<span class="signal-tag">{label}</span>\n'

        strength_labels = {
            "p3_above_60": "Trust Above 60",
            "sig6_above_4": "Strong Momentum",
            "ndd_above_3.5": "DtD Healthy",
            "p3_improving_10": "Trust Improving",
        }
        for key, label in strength_labels.items():
            if strength_signals.get(key):
                tags_html += f'<span class="signal-strength">{label}</span>\n'

        display_level = "STRUCTURAL COLLAPSE" if level == "CRITICAL" else "STRUCTURAL STRESS"
        return f"""<div class="alert-card alert-{level_class}">
  <div class="alert-header">
    <div>
      <div class="alert-token">{name}</div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--gray-500);margin-top:2px">{symbol} &middot; Rating: {rating} &middot; Score: {trust:.0f}/100</div>
    </div>
    <div class="alert-level level-{level_class}">{display_level}</div>
  </div>
  <div class="alert-metrics">
    <div class="alert-metric">
      <div class="metric-label">Distance-to-Default</div>
      <div class="metric-value {dtd_class}">{dtd:.2f}</div>
    </div>
    <div class="alert-metric">
      <div class="metric-label">Crash Prob (90d)</div>
      <div class="metric-value {crash_class}">{crash_prob:.0%}</div>
    </div>
    <div class="alert-metric">
      <div class="metric-label">Weakness Score</div>
      <div class="metric-value metric-danger">{weakness}/4</div>
    </div>
    <div class="alert-metric">
      <div class="metric-label">30d Volatility</div>
      <div class="metric-value metric-warn">{vol:.1f}%</div>
    </div>
    <div class="alert-metric">
      <div class="metric-label">90d Drawdown</div>
      <div class="metric-value {"metric-danger" if dd90 < -0.3 else "metric-warn"}">{dd90:.1%}</div>
    </div>
    <div class="alert-metric">
      <div class="metric-label">Rating</div>
      <div class="metric-value metric-ok">{rating}</div>
    </div>
  </div>
  <div class="alert-signals">{tags_html}</div>
  <div style="display:flex;gap:6px;align-items:center;margin:8px 16px 0;flex-wrap:wrap">{target_html}</div>
  <div class="alert-footer">
    <div class="alert-date">Alert issued {collapse_date} &middot; Price then: ${price_at_collapse:.4f} &middot; {weeks_in} weeks ago &middot; <span style="color:{price_chg_color}">{price_chg_str}</span>{"" if not max_dd_str else " &middot; " + max_dd_str}</div>
    <a href="/crypto/token/{token_id}" class="alert-link">View full profile &rarr;</a>
  </div>
</div>"""

    @app.get("/crypto/alerts", response_class=HTMLResponse, include_in_schema=False)
    async def alerts_page():
        try:
            with open(template_path, "r") as f:
                html = f.read()
        except FileNotFoundError:
            return HTMLResponse(status_code=404, content="<h1>Alerts page not found</h1>")

        try:
            conn = _get_db()
            # Get latest run date
            row = conn.execute("SELECT MAX(signal_date) as d FROM nerq_risk_signals").fetchone()
            run_date = row["d"] if row else "Unknown"

            # Get active signals
            rows = conn.execute("""
                SELECT s.token_id, s.signal_date, s.risk_level, s.structural_weakness, s.first_collapse_date, s.price_at_collapse, s.weeks_in_collapse,
                       s.structural_strength, s.btc_beta, s.vol_30d, s.ndd_current,
                       s.ndd_min_4w, s.trust_p3, s.trust_score, s.drawdown_90d, s.details,
                       n.crash_probability,
                       r.rating, r.score as trust_score_total, r.symbol, r.name, r.market_cap_rank,
                       n.price_usd
                FROM nerq_risk_signals s
                LEFT JOIN crypto_ndd_daily n ON s.token_id = n.token_id AND n.run_date = s.signal_date
                LEFT JOIN crypto_rating_daily r ON s.token_id = r.token_id AND r.run_date = s.signal_date
                WHERE s.signal_date = ? AND s.risk_level IN ('WARNING', 'CRITICAL')
                ORDER BY s.first_collapse_date DESC, s.structural_weakness DESC, s.ndd_current ASC
            """, [run_date]).fetchall()
            conn.close()

            critical = sum(1 for r in rows if r["risk_level"] == "CRITICAL")
            warning = sum(1 for r in rows if r["risk_level"] == "WARNING")
            total = len(rows)

            # Compute max drawdown since alert for each token
            conn2 = _get_db()
            enriched_rows = []
            for r in rows:
                rd = dict(r)
                tid = rd.get("token_id")
                first_date = rd.get("first_collapse_date") or rd.get("signal_date")
                price_at = rd.get("price_at_collapse") or 0
                max_dd = None
                min_price = None
                if tid and first_date and price_at and price_at > 0:
                    mp = conn2.execute(
                        "SELECT MIN(close) FROM crypto_price_history WHERE token_id=? AND date>=?",
                        (tid, first_date)
                    ).fetchone()
                    if mp and mp[0] is not None and mp[0] > 0:
                        min_price = mp[0]
                        max_dd = (mp[0] - price_at) / price_at * 100
                rd["max_dd"] = max_dd
                rd["min_price_since"] = min_price
                enriched_rows.append(rd)
            conn2.close()

            cards_html = "\n".join(_build_alert_card(r) for r in enriched_rows)

            html = html.replace("{{RUN_DATE}}", run_date or "Unknown")
            html = html.replace("{{CRITICAL_COUNT}}", str(critical))
            html = html.replace("{{WARNING_COUNT}}", str(warning))
            html = html.replace("{{TOTAL_COUNT}}", str(total))

            # Target tracking stats
            mature_cutoff = "2026-01-15"
            mature = [r for r in enriched_rows if (r.get("first_collapse_date") or "") < mature_cutoff]
            t1_hit = sum(1 for r in mature if r.get("max_dd") is not None and r["max_dd"] <= -30)
            t2_hit = sum(1 for r in mature if r.get("max_dd") is not None and r["max_dd"] <= -50)
            fresh = len(enriched_rows) - len(mature)
            html = html.replace("{{MATURE_COUNT}}", str(len(mature)))
            html = html.replace("{{T1_HIT}}", str(t1_hit))
            html = html.replace("{{T1_RATE}}", f"{t1_hit/len(mature)*100:.0f}" if mature else "0")
            html = html.replace("{{T2_HIT}}", str(t2_hit))
            html = html.replace("{{T2_RATE}}", f"{t2_hit/len(mature)*100:.0f}" if mature else "0")
            html = html.replace("{{FRESH_COUNT}}", str(fresh))

            # Target tracking stats
            mature_cutoff = "2026-01-15"
            mature = [r for r in enriched_rows if (r.get("first_collapse_date") or "") < mature_cutoff]
            t1_hit = sum(1 for r in mature if r.get("max_dd") is not None and r["max_dd"] <= -30)
            t2_hit = sum(1 for r in mature if r.get("max_dd") is not None and r["max_dd"] <= -50)
            fresh = len(enriched_rows) - len(mature)
            html = html.replace("{{MATURE_COUNT}}", str(len(mature)))
            html = html.replace("{{T1_HIT}}", str(t1_hit))
            html = html.replace("{{T1_RATE}}", f"{t1_hit/len(mature)*100:.0f}" if mature else "0")
            html = html.replace("{{T2_HIT}}", str(t2_hit))
            html = html.replace("{{T2_RATE}}", f"{t2_hit/len(mature)*100:.0f}" if mature else "0")
            html = html.replace("{{FRESH_COUNT}}", str(fresh))
            html = html.replace("{{ALERT_CARDS}}", cards_html)

        except Exception as e:
            html = html.replace("{{RUN_DATE}}", "Error")
            html = html.replace("{{CRITICAL_COUNT}}", "0")
            html = html.replace("{{WARNING_COUNT}}", "0")
            html = html.replace("{{TOTAL_COUNT}}", "0")
            html = html.replace("{{ALERT_CARDS}}", f'<div class="alert-card"><p>Error loading signals: {e}</p></div>')

        return HTMLResponse(content=html)


def mount_methodology_page(app):
    import os
    from fastapi.responses import HTMLResponse
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "zarq_methodology.html")

    @app.get("/methodology", response_class=HTMLResponse)
    async def methodology_page():
        try:
            with open(template_path, "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(status_code=404, content="<h1>Methodology not found</h1>")


def mount_recovery_page(app):
    """Recovery Signal page with live data from crypto_ndd_daily."""
    import os, json, sqlite3
    from fastapi.responses import HTMLResponse

    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "zarq_recovery.html")

    def _get_db():
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _build_recovery_card(row):
        token_id = row["token_id"]
        symbol = (row["symbol"] or token_id[:4]).upper()
        name = token_id.replace("-", " ").title()
        signal = row["bottlefish_signal"]
        bounce = row["bounce_90d"] or 0
        ndd = row["ndd"] or 0
        rank = row["market_cap_rank"] or 999
        price = row["price_usd"] or 0
        rating = row["rating"] or "NR"
        trust = row["trust_score"] or 0

        level_map = {
            "STRONG_BUY": ("strong", "STRONG BUY"),
            "BUY": ("buy", "BUY"),
            "SPECULATIVE": ("spec", "SPECULATIVE"),
        }
        css_class, display = level_map.get(signal, ("spec", signal))

        return f"""<div class="signal-card card-{css_class}">
  <div class="sc-header">
    <div>
      <div class="sc-token">{name}</div>
      <div class="sc-sub">{symbol} &middot; Rating: {rating} &middot; Rank #{rank}</div>
    </div>
    <div class="sc-level level-{css_class}">{display}</div>
  </div>
  <div class="sc-metrics">
    <div class="sc-metric">
      <div class="sc-m-label">Bounce from Trough</div>
      <div class="sc-m-val m-green">+{bounce:.1f}%</div>
    </div>
    <div class="sc-metric">
      <div class="sc-m-label">Distance-to-Default</div>
      <div class="sc-m-val {"m-warn" if ndd < 3.0 else "m-ok"}">{ndd:.2f}</div>
    </div>
    <div class="sc-metric">
      <div class="sc-m-label">Trust Score</div>
      <div class="sc-m-val m-ok">{trust:.0f}/100</div>
    </div>
    <div class="sc-metric">
      <div class="sc-m-label">Current Price</div>
      <div class="sc-m-val m-ok">${price:.4f}</div>
    </div>
  </div>
  <div class="sc-footer">
    <div style="font-family:var(--mono);font-size:11px;color:var(--gray-400)">Crashed 70%+ from peak · Recovery bounce active</div>
    <a href="/crypto/token/{token_id}" class="sc-link">View full profile &rarr;</a>
  </div>
</div>"""

    @app.get("/recovery", response_class=HTMLResponse, include_in_schema=False)
    async def recovery_page():
        try:
            with open(template_path, "r") as f:
                html = f.read()
        except FileNotFoundError:
            return HTMLResponse(status_code=404, content="<h1>Recovery page not found</h1>")

        try:
            conn = _get_db()
            run_date_row = conn.execute("SELECT MAX(run_date) as d FROM crypto_ndd_daily").fetchone()
            run_date = run_date_row["d"] if run_date_row else "Unknown"

            rows = conn.execute("""
                SELECT d.symbol, d.token_id, d.bottlefish_signal, d.bounce_90d, d.ndd,
                       d.market_cap_rank, d.alert_level, d.price_usd,
                       r.rating, r.score as trust_score
                FROM crypto_ndd_daily d
                LEFT JOIN crypto_rating_daily r ON d.token_id = r.token_id AND r.run_date = d.run_date
                WHERE d.run_date = ?
                AND d.bottlefish_signal IS NOT NULL
                AND d.bottlefish_signal NOT IN ('AVOID', '')
                ORDER BY
                  CASE d.bottlefish_signal
                    WHEN 'STRONG_BUY' THEN 1
                    WHEN 'BUY' THEN 2
                    WHEN 'SPECULATIVE' THEN 3
                    ELSE 4
                  END,
                  d.bounce_90d DESC
            """, [run_date]).fetchall()

            # Also get AVOID count
            avoid_row = conn.execute("""
                SELECT COUNT(*) as cnt FROM crypto_ndd_daily
                WHERE run_date = ? AND bottlefish_signal = 'AVOID'
            """, [run_date]).fetchone()
            avoid_count = avoid_row["cnt"] if avoid_row else 0

            conn.close()

            if rows:
                cards_html = "\n".join(_build_recovery_card(dict(r)) for r in rows)
                cards_html += f'\n<div style="font-family:var(--mono);font-size:12px;color:var(--gray-500);margin-top:16px">{avoid_count} additional tokens classified AVOID (crashed but insufficient recovery)</div>'
            else:
                cards_html = f"""<div class="empty-state">
  <div class="es-icon">📉</div>
  <h3>No Active Recovery Signals</h3>
  <p>No tokens currently meet the recovery criteria. This is common during sustained bear markets when crashed tokens have not yet shown sufficient bounce. {avoid_count} tokens are classified AVOID (crashed but insufficient recovery).</p>
</div>"""

            html = html.replace("{{RUN_DATE}}", run_date or "Unknown")
            html = html.replace("{{RECOVERY_CARDS}}", cards_html)

        except Exception as e:
            html = html.replace("{{RUN_DATE}}", "Error")
            html = html.replace("{{RECOVERY_CARDS}}", f'<div class="signal-card"><p>Error loading data: {e}</p></div>')

        return HTMLResponse(content=html)


def mount_sitemap_pages(app):
    """Sitemap for static ZARQ pages."""
    from starlette.responses import Response
    from datetime import date

    @app.get("/sitemap-pages.xml", response_class=Response)
    def sitemap_pages():
        today = date.today().isoformat()
        pages = [
            ("/", "daily", "1.0"),
            ("/crypto", "daily", "0.9"),
            ("/crypto/alerts", "daily", "0.9"),
            ("/track-record", "weekly", "0.8"),
            ("/paper-trading", "daily", "0.8"),
            ("/methodology", "monthly", "0.7"),
            ("/docs", "monthly", "0.6"),
            ("/best/crypto-tokens", "weekly", "0.7"),
            ("/best/crypto-exchanges", "weekly", "0.7"),
            ("/best/crypto-defi", "weekly", "0.7"),
            ("/tokens", "weekly", "1.0"),
            ("/vitality/methodology", "monthly", "0.7"),
            ("/scan", "daily", "0.9"),
        ]
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
"""
        for path, freq, priority in pages:
            xml += f"""  <url>
    <loc>https://zarq.ai{path}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{priority}</priority>
  </url>
"""
        xml += "</urlset>"
        return Response(content=xml, media_type="application/xml")


def mount_vitality_methodology_page(app):
    import os
    from fastapi.responses import HTMLResponse
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "zarq_vitality_methodology.html")
    backtest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "zarq_vitality_backtest.html")

    @app.get("/vitality/methodology", response_class=HTMLResponse, include_in_schema=False)
    async def vitality_methodology_page():
        try:
            with open(template_path, "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(status_code=404, content="<h1>Vitality methodology not found</h1>")

    @app.get("/vitality/backtest", response_class=HTMLResponse, include_in_schema=False)
    async def vitality_backtest_page():
        try:
            with open(backtest_path, "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(status_code=404, content="<h1>Backtest results not found</h1>")


def mount_whitepaper_page(app):
    import os
    from fastapi.responses import HTMLResponse
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "zarq_whitepaper.html")

    @app.get("/whitepaper", response_class=HTMLResponse)
    async def whitepaper_page():
        try:
            with open(template_path, "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(status_code=404, content="<h1>White paper not found</h1>")

def mount_compare_pages(app):
    """Mount token comparison pages: /compare/{token-a}-vs-{token-b}"""
    import sqlite3
    import json
    from pathlib import Path
    from fastapi.responses import HTMLResponse, Response
    from datetime import date

    DB_PATH = str(Path(__file__).parent.parent / "data" / "crypto_trust.db")

    def get_db():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def esc(text):
        if not text:
            return ""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    def grade_color(grade):
        if not grade:
            return "#78716c"
        g = grade[0].upper()
        return {"A": "#16a34a", "B": "#65a30d", "C": "#d97706", "D": "#ea580c", "F": "#dc2626"}.get(g, "#78716c")

    def fmt_usd(val):
        if val is None:
            return "N/A"
        if val >= 1e12:
            return f"${val/1e12:.2f}T"
        if val >= 1e9:
            return f"${val/1e9:.2f}B"
        if val >= 1e6:
            return f"${val/1e6:.2f}M"
        return f"${val:,.0f}"

    def fmt_pct(val):
        if val is None:
            return "N/A"
        sign = "+" if val > 0 else ""
        return f"{sign}{val:.1f}%"

    def pct_color(val):
        if val is None:
            return "#78716c"
        return "#16a34a" if val >= 0 else "#dc2626"

    def bar(score, color):
        if score is None:
            score = 0
        w = max(0, min(100, score))
        return f'<div style="background:#e7e5e4;border-radius:4px;height:8px;width:100%;margin-top:4px"><div style="background:{color};border-radius:4px;height:8px;width:{w}%"></div></div>'

    RISK_DB = str(Path(__file__).parent / "crypto_trust.db")

    def vitality_grade_color(grade):
        if not grade:
            return "#78716c"
        return {"S": "#c2956b", "A": "#16a34a", "B": "#65a30d", "C": "#d97706", "D": "#ea580c", "F": "#dc2626"}.get(grade, "#78716c")

    def render_compare_page(a, b):
        a = dict(a)
        b = dict(b)

        # Load Vitality Scores
        try:
            rconn = sqlite3.connect(RISK_DB)
            rconn.row_factory = sqlite3.Row
            va = rconn.execute("SELECT * FROM vitality_scores WHERE token_id=?", (a["id"],)).fetchone()
            vb = rconn.execute("SELECT * FROM vitality_scores WHERE token_id=?", (b["id"],)).fetchone()
            rconn.close()
            a_vitality = dict(va) if va else None
            b_vitality = dict(vb) if vb else None
        except Exception:
            a_vitality = None
            b_vitality = None

        a_color = grade_color(a.get("trust_grade"))
        b_color = grade_color(b.get("trust_grade"))

        title = f"{esc(a['name'])} vs {esc(b['name'])}: Safety & Risk Comparison 2026 | ZARQ"
        desc = (
            f"{esc(a['name'])} ({esc(a['symbol'].upper())}) vs {esc(b['name'])} ({esc(b['symbol'].upper())}): "
            f"which is safer? {esc(a['name'])} scores {a.get('trust_score', 0):.1f}/100 ({a.get('trust_grade','?')}), "
            f"{esc(b['name'])} scores {b.get('trust_score', 0):.1f}/100 ({b.get('trust_grade','?')}). "
            f"Independent risk comparison by ZARQ."
        )
        url = f"https://zarq.ai/compare/{a['id']}-vs-{b['id']}"

        schema = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": title,
            "description": desc,
            "url": url,
            "provider": {"@type": "Organization", "name": "ZARQ", "url": "https://zarq.ai"}
        }

        pillars = [
            ("Security", "security_score", "30%"),
            ("Compliance", "compliance_score", "25%"),
            ("Maintenance", "maintenance_score", "20%"),
            ("Popularity", "popularity_score", "15%"),
            ("Ecosystem", "ecosystem_score", "10%"),
        ]

        # Winner logic
        a_score = a.get("trust_score") or 0
        b_score = b.get("trust_score") or 0
        if a_score > b_score:
            winner = a["name"]
            winner_by = a_score - b_score
        elif b_score > a_score:
            winner = b["name"]
            winner_by = b_score - a_score
        else:
            winner = None
            winner_by = 0

        ai_summary = (
            f"<!-- AI-Citable Summary: {a['name']} ({a['symbol'].upper()}) has a ZARQ Trust Score of "
            f"{a_score:.1f}/100 (Grade {a.get('trust_grade','?')}). "
            f"{b['name']} ({b['symbol'].upper()}) has a ZARQ Trust Score of "
            f"{b_score:.1f}/100 (Grade {b.get('trust_grade','?')}). "
            f"{'Winner: ' + winner + ' by ' + f'{winner_by:.1f} points.' if winner else 'Tied.'} "
            f"Source: ZARQ (zarq.ai) — independent crypto risk intelligence. -->"
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="website">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{json.dumps(schema)}</script>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --white: #fafaf9; --black: #0a0a0a;
  --gray-100: #f5f5f4; --gray-200: #e7e5e4; --gray-400: #a8a29e;
  --gray-500: #78716c; --gray-600: #57534e; --gray-700: #44403c;
  --gray-800: #292524; --gray-900: #1c1917;
  --warm: #c2956b; --warm-light: rgba(194,149,107,0.08);
  --green: #16a34a; --red: #dc2626;
  --serif: 'DM Serif Display', serif;
  --sans: 'DM Sans', sans-serif;
  --mono: 'JetBrains Mono', monospace;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--black); color: var(--white); font-family: var(--sans); min-height: 100vh; }}
nav {{ padding: 16px 24px; border-bottom: 1px solid #1c1917; display: flex; align-items: center; gap: 16px; position: relative; }}
.nav-mark {{ font-family: var(--mono); font-weight: 500; font-size: 15px; letter-spacing: 0.15em; text-transform: uppercase; color: var(--white); text-decoration: none; }}
.nav-links {{ display: flex; gap: 24px; align-items: center; margin-left: auto; }}
.nav-links a {{ font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-500); text-decoration: none; }}
.nav-links a:hover {{ color: var(--white); }}
.nav-api {{ font-size: 11px; color: var(--warm); border: 1px solid var(--warm); padding: 4px 12px; }}
.nav-api:hover {{ background: var(--warm); color: var(--black); }}
.nav-dropdown {{ position: relative; }}
.nav-dropdown-trigger {{ cursor: pointer; }}
.nav-dropdown-menu {{ display: none; position: absolute; top: 100%; right: 0; background: var(--gray-900); border: 1px solid #292524; padding: 8px 0; min-width: 180px; z-index: 200; }}
.nav-dropdown:hover .nav-dropdown-menu {{ display: block; }}
.nav-dropdown-menu a {{ display: block; padding: 8px 20px; font-family: var(--mono); font-size: 12px; color: var(--gray-500); white-space: nowrap; }}
.nav-dropdown-menu a:hover {{ background: var(--warm-light); color: var(--white); }}
.nav-toggle-input {{ display: none; }}
.nav-hamburger {{ display: none; cursor: pointer; flex-direction: column; gap: 5px; }}
.nav-hamburger span {{ display: block; width: 22px; height: 2px; background: var(--white); }}
.container {{ max-width: 900px; margin: 0 auto; padding: 40px 24px; }}
h1 {{ font-family: var(--serif); font-size: clamp(24px, 4vw, 36px); color: var(--white); margin-bottom: 8px; }}
.subtitle {{ color: var(--gray-500); font-size: 14px; margin-bottom: 40px; font-family: var(--mono); }}
.vs-grid {{ display: grid; grid-template-columns: 1fr auto 1fr; gap: 16px; align-items: start; margin-bottom: 40px; }}
.token-card {{ background: var(--gray-900); border: 1px solid #292524; border-radius: 12px; padding: 24px; }}
.token-card.winner {{ border-color: var(--warm); }}
.token-symbol {{ font-family: var(--mono); font-size: 12px; color: var(--gray-500); text-transform: uppercase; letter-spacing: 0.1em; }}
.token-name {{ font-family: var(--serif); font-size: 24px; color: var(--white); margin: 4px 0 16px; }}
.score-big {{ font-family: var(--mono); font-size: 48px; font-weight: 700; line-height: 1; }}
.grade-badge {{ display: inline-block; font-family: var(--mono); font-size: 13px; font-weight: 700; padding: 2px 8px; border-radius: 4px; margin-left: 8px; color: var(--white); }}
.vs-divider {{ display: flex; align-items: center; justify-content: center; font-family: var(--serif); font-size: 28px; color: var(--gray-600); padding-top: 60px; }}
.pillar-row {{ margin: 10px 0; }}
.pillar-label {{ display: flex; justify-content: space-between; font-size: 12px; color: var(--gray-500); font-family: var(--mono); margin-bottom: 2px; }}
.pillar-val {{ font-weight: 600; color: var(--white); }}
.winner-banner {{ background: var(--warm-light); border: 1px solid var(--warm); border-radius: 8px; padding: 16px 20px; margin-bottom: 32px; text-align: center; }}
.winner-banner strong {{ color: var(--warm); font-family: var(--serif); font-size: 18px; }}
.market-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 40px; }}
.market-card {{ background: var(--gray-900); border: 1px solid #292524; border-radius: 12px; padding: 20px; }}
.market-card h3 {{ font-family: var(--mono); font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--gray-500); margin-bottom: 12px; }}
.market-row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #1c1917; font-size: 13px; }}
.market-row:last-child {{ border-bottom: none; }}
.market-row .label {{ color: var(--gray-500); }}
.section-title {{ font-family: var(--serif); font-size: 20px; color: var(--white); margin-bottom: 16px; }}
.faq {{ margin-bottom: 40px; }}
.faq-item {{ border-bottom: 1px solid #1c1917; padding: 16px 0; }}
.faq-item h3 {{ font-size: 15px; font-weight: 600; color: var(--white); margin-bottom: 6px; }}
.faq-item p {{ font-size: 13px; color: var(--gray-500); line-height: 1.6; }}
footer {{ border-top: 1px solid #1c1917; padding: 24px; text-align: center; font-size: 12px; color: var(--gray-600); font-family: var(--mono); }}
@media (max-width: 640px) {{
  .vs-grid {{ grid-template-columns: 1fr; }}
  .vs-divider {{ padding-top: 0; }}
  .market-grid {{ grid-template-columns: 1fr; }}
}}
@media (max-width: 768px) {{
  .nav-hamburger {{ display: flex; }}
  .nav-links {{ display: none; position: absolute; top: 100%; left: 0; right: 0; background: var(--gray-900); border-bottom: 1px solid #292524; padding: 16px 20px; flex-direction: column; gap: 16px; }}
  .nav-toggle-input:checked ~ .nav-links {{ display: flex; }}
  .nav-dropdown-menu {{ display: block; position: static; border: none; padding: 0 0 0 12px; }}
  .nav-dropdown-trigger {{ display: none; }}
}}
</style>
</head>
<body>
{ai_summary}
<nav>
  <a href="/" class="nav-mark">zarq</a>
  <input type="checkbox" id="nav-toggle" class="nav-toggle-input">
  <label for="nav-toggle" class="nav-hamburger"><span></span><span></span><span></span></label>
  <div class="nav-links">
    <a href="/scan">Scan</a>
    <a href="/crypto">Ratings</a>
    <a href="/tokens">Token Ratings</a>
    <a href="/crash-watch">Crash Watch</a>
    <div class="nav-dropdown">
      <a href="#" class="nav-dropdown-trigger">More &#9662;</a>
      <div class="nav-dropdown-menu">
        <a href="/yield-risk">Yield Risk</a>
        <a href="/compare">Compare</a>
        <a href="/learn">Learn</a>
        <a href="/track-record">Track Record</a>
        <a href="/paper-trading">Paper Trading</a>
        <a href="/press">Press</a>
        <a href="/methodology">Methodology</a>
      </div>
    </div>
    <a href="/docs" class="nav-api">API</a>
  </div>
</nav>
<div class="container">
  <h1>{esc(a['name'])} vs {esc(b['name'])}</h1>
  <p class="subtitle">ZARQ Trust Score comparison — independent crypto risk intelligence</p>
"""

        if winner:
            html += f"""  <div class="winner-banner">
    <strong>{esc(winner)}</strong> scores higher by <strong style="color:var(--warm)">{winner_by:.1f} points</strong>
  </div>
"""

        # VS grid
        def pillar_rows(t, color):
            rows = ""
            for label, key, weight in pillars:
                val = t.get(key)
                val_str = f"{val:.0f}" if val is not None else "N/A"
                rows += f"""<div class="pillar-row">
  <div class="pillar-label"><span>{label} <span style="color:var(--gray-600)">({weight})</span></span><span class="pillar-val">{val_str}</span></div>
  {bar(val, color)}
</div>"""
            return rows

        a_winner_class = "winner" if a_score > b_score else ""
        b_winner_class = "winner" if b_score > a_score else ""

        html += f"""  <div class="vs-grid">
    <div class="token-card {a_winner_class}">
      <div class="token-symbol">{esc(a['symbol'].upper())}</div>
      <div class="token-name">{esc(a['name'])}</div>
      <div>
        <span class="score-big" style="color:{a_color}">{a_score:.1f}</span>
        <span class="grade-badge" style="background:{a_color}">{esc(a.get('trust_grade','?'))}</span>
      </div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--gray-500);margin:8px 0 16px">Trust Score / 100</div>
      {pillar_rows(a, a_color)}
    </div>
    <div class="vs-divider">vs</div>
    <div class="token-card {b_winner_class}">
      <div class="token-symbol">{esc(b['symbol'].upper())}</div>
      <div class="token-name">{esc(b['name'])}</div>
      <div>
        <span class="score-big" style="color:{b_color}">{b_score:.1f}</span>
        <span class="grade-badge" style="background:{b_color}">{esc(b.get('trust_grade','?'))}</span>
      </div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--gray-500);margin:8px 0 16px">Trust Score / 100</div>
      {pillar_rows(b, b_color)}
    </div>
  </div>
"""

        # Vitality Score & Crash Protection section
        if a_vitality or b_vitality:
            av = a_vitality or {}
            bv = b_vitality or {}
            a_vs = av.get("vitality_score")
            b_vs = bv.get("vitality_score")
            a_vg = av.get("vitality_grade", "?")
            b_vg = bv.get("vitality_grade", "?")
            a_sr = av.get("stress_resilience")
            b_sr = bv.get("stress_resilience")
            a_vc = vitality_grade_color(a_vg)
            b_vc = vitality_grade_color(b_vg)

            # Vitality winner
            if a_vs and b_vs:
                if a_vs > b_vs:
                    v_winner = a["name"]
                    v_diff = a_vs - b_vs
                elif b_vs > a_vs:
                    v_winner = b["name"]
                    v_diff = b_vs - a_vs
                else:
                    v_winner = None
                    v_diff = 0
            else:
                v_winner = None
                v_diff = 0

            vitality_dims = [
                ("Stress Resilience", "stress_resilience", "25%"),
                ("Ecosystem Gravity", "ecosystem_gravity", "20%"),
                ("Capital Commitment", "capital_commitment", "20%"),
                ("Coordination Efficiency", "coordination_efficiency", "15%"),
                ("Organic Momentum", "organic_momentum", "20%"),
            ]

            def vitality_bars(v, color):
                rows_html = ""
                for label, key, weight in vitality_dims:
                    val = v.get(key)
                    val_str = f"{val:.0f}" if val is not None else "N/A"
                    rows_html += f"""<div class="pillar-row">
  <div class="pillar-label"><span>{label} <span style="color:var(--gray-600)">({weight})</span></span><span class="pillar-val">{val_str}</span></div>
  {bar(val, color)}
</div>"""
                return rows_html

            html += f"""
  <h2 class="section-title" style="margin-top:24px">Crash Protection — Vitality Score</h2>
  <p style="font-size:13px;color:var(--gray-500);margin-bottom:16px;line-height:1.6">
    The Vitality Score measures ecosystem health and crash resistance (0–100).
    <strong style="color:var(--warm)">Backtested:</strong> top-quintile tokens lost 44% less in the 2025–2026 crash (p&lt;0.001).
    <a href="/vitality/backtest" style="color:var(--warm)">Full results &rarr;</a>
  </p>
"""
            if v_winner:
                html += f"""  <div class="winner-banner">
    <strong>{esc(v_winner)}</strong> is more crash-resistant by <strong style="color:var(--warm)">{v_diff:.1f} points</strong> (Vitality Score)
  </div>
"""

            a_vw = "winner" if a_vs and b_vs and a_vs > b_vs else ""
            b_vw = "winner" if a_vs and b_vs and b_vs > a_vs else ""

            html += f"""  <div class="vs-grid">
    <div class="token-card {a_vw}">
      <div class="token-symbol">{esc(a['symbol'].upper())} VITALITY</div>
      <div class="token-name">{esc(a['name'])}</div>
      <div>
        <span class="score-big" style="color:{a_vc}">{f'{a_vs:.1f}' if a_vs else 'N/A'}</span>
        <span class="grade-badge" style="background:{a_vc}">{a_vg}</span>
      </div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--gray-500);margin:8px 0 16px">Vitality Score / 100</div>
      {vitality_bars(av, a_vc)}
    </div>
    <div class="vs-divider">vs</div>
    <div class="token-card {b_vw}">
      <div class="token-symbol">{esc(b['symbol'].upper())} VITALITY</div>
      <div class="token-name">{esc(b['name'])}</div>
      <div>
        <span class="score-big" style="color:{b_vc}">{f'{b_vs:.1f}' if b_vs else 'N/A'}</span>
        <span class="grade-badge" style="background:{b_vc}">{b_vg}</span>
      </div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--gray-500);margin:8px 0 16px">Vitality Score / 100</div>
      {vitality_bars(bv, b_vc)}
    </div>
  </div>
"""

        # Market data
        html += f"""  <div class="market-grid">
    <div class="market-card">
      <h3>{esc(a['name'])} market data</h3>
      <div class="market-row"><span class="label">Price</span><span>{fmt_usd(a.get('current_price_usd'))}</span></div>
      <div class="market-row"><span class="label">Market Cap</span><span>{fmt_usd(a.get('market_cap_usd'))}</span></div>
      <div class="market-row"><span class="label">Rank</span><span>#{a.get('market_cap_rank','?')}</span></div>
      <div class="market-row"><span class="label">24h</span><span style="color:{pct_color(a.get('price_change_24h_pct'))}">{fmt_pct(a.get('price_change_24h_pct'))}</span></div>
      <div class="market-row"><span class="label">7d</span><span style="color:{pct_color(a.get('price_change_7d_pct'))}">{fmt_pct(a.get('price_change_7d_pct'))}</span></div>
      <div class="market-row"><span class="label">Audit</span><span>{'✓ Yes' if a.get('has_audit') else '✗ No'}</span></div>
    </div>
    <div class="market-card">
      <h3>{esc(b['name'])} market data</h3>
      <div class="market-row"><span class="label">Price</span><span>{fmt_usd(b.get('current_price_usd'))}</span></div>
      <div class="market-row"><span class="label">Market Cap</span><span>{fmt_usd(b.get('market_cap_usd'))}</span></div>
      <div class="market-row"><span class="label">Rank</span><span>#{b.get('market_cap_rank','?')}</span></div>
      <div class="market-row"><span class="label">24h</span><span style="color:{pct_color(b.get('price_change_24h_pct'))}">{fmt_pct(b.get('price_change_24h_pct'))}</span></div>
      <div class="market-row"><span class="label">7d</span><span style="color:{pct_color(b.get('price_change_7d_pct'))}">{fmt_pct(b.get('price_change_7d_pct'))}</span></div>
      <div class="market-row"><span class="label">Audit</span><span>{'✓ Yes' if b.get('has_audit') else '✗ No'}</span></div>
    </div>
  </div>
"""

        # FAQ
        faq_items = [
            (
                f"Which is safer, {a['name']} or {b['name']}?",
                f"Based on ZARQ's independent Trust Score, {winner if winner else 'neither token'} "
                f"{'scores higher' if winner else 'scores the same'} "
                f"({'by ' + f'{winner_by:.1f} points' if winner else 'tied at ' + f'{a_score:.1f}'})."
                f" {a['name']} scores {a_score:.1f}/100 (Grade {a.get('trust_grade','?')}) and "
                f"{b['name']} scores {b_score:.1f}/100 (Grade {b.get('trust_grade','?')})."
                f" This is not investment advice."
            ),
            (
                f"What is the Trust Score for {a['name']}?",
                f"{a['name']} ({a['symbol'].upper()}) has a ZARQ Trust Score of {a_score:.1f}/100, "
                f"Grade {a.get('trust_grade','?')}. Scored across Security, Compliance, Maintenance, "
                f"Popularity, and Ecosystem dimensions."
            ),
            (
                f"What is the Trust Score for {b['name']}?",
                f"{b['name']} ({b['symbol'].upper()}) has a ZARQ Trust Score of {b_score:.1f}/100, "
                f"Grade {b.get('trust_grade','?')}. Scored across Security, Compliance, Maintenance, "
                f"Popularity, and Ecosystem dimensions."
            ),
        ]

        # Add Vitality FAQ if data available
        if a_vitality and b_vitality:
            a_vs = a_vitality.get("vitality_score", 0)
            b_vs = b_vitality.get("vitality_score", 0)
            a_vg = a_vitality.get("vitality_grade", "?")
            b_vg = b_vitality.get("vitality_grade", "?")
            cr_winner = a["name"] if a_vs > b_vs else b["name"] if b_vs > a_vs else "Neither"
            faq_items.append((
                f"Which is more crash-resistant, {a['name']} or {b['name']}?",
                f"Based on ZARQ's Vitality Score (backtested, p<0.001), {cr_winner} has higher crash resistance. "
                f"{a['name']} Vitality: {a_vs:.1f}/100 (Grade {a_vg}), "
                f"{b['name']} Vitality: {b_vs:.1f}/100 (Grade {b_vg}). "
                f"In the 2025-2026 crash, top-quintile Vitality tokens lost 44% less than bottom-quintile. "
                f"Not investment advice."
            ))

        faq_schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": q,
                    "acceptedAnswer": {"@type": "Answer", "text": ans}
                }
                for q, ans in faq_items
            ]
        }

        html += f'<script type="application/ld+json">{json.dumps(faq_schema)}</script>\n'
        html += '<div class="faq"><h2 class="section-title">Frequently Asked Questions</h2>\n'
        for q, ans in faq_items:
            html += f'<div class="faq-item"><h3>{esc(q)}</h3><p>{esc(ans)}</p></div>\n'
        html += '</div>\n'

        html += f"""  <p style="font-size:12px;color:var(--gray-600);font-family:var(--mono);margin-bottom:40px">
    Data updated daily. Not investment advice. <a href="https://zarq.ai/methodology" style="color:var(--warm)">Methodology &rarr;</a>
    &nbsp;|&nbsp; <a href="https://zarq.ai/crypto/token/{a['id']}" style="color:var(--warm)">{esc(a['name'])} full report &rarr;</a>
    &nbsp;|&nbsp; <a href="https://zarq.ai/crypto/token/{b['id']}" style="color:var(--warm)">{esc(b['name'])} full report &rarr;</a>
  </p>
<footer>ZARQ — Independent Crypto Risk Intelligence &nbsp;·&nbsp; zarq.ai</footer>
</div>
</body>
</html>"""

        return html

    @app.get("/compare/{slug}", response_class=HTMLResponse)
    def compare_page(slug: str, request: Request):
        # Nerq agent comparisons are handled by agent_compare_pages module
        host = request.headers.get("host", "")
        if "zarq.ai" not in host:
            from agentindex.agent_compare_pages import _load_pairs, _pair_map, _render_compare_page, _esc, _page_cache, _CACHE_TTL, _CACHE_MAX
            import time as _t
            _load_pairs()
            pair_info = _pair_map.get(slug)
            if pair_info:
                now = _t.time()
                if slug in _page_cache:
                    html, ts = _page_cache[slug]
                    if now - ts < _CACHE_TTL:
                        return HTMLResponse(content=html)
                try:
                    html = _render_compare_page(slug, pair_info)
                    if html is not None:
                        if len(_page_cache) < _CACHE_MAX:
                            _page_cache[slug] = (html, _t.time())
                        return HTMLResponse(content=html)
                except Exception:
                    pass
            # Fallback for slugs not in pair_map: dynamically create pair_info and render
            if "-vs-" in slug:
                parts = slug.split("-vs-", 1)
                dynamic_pair = {"slug": slug, "agent_a": parts[0], "agent_b": parts[1], "category": ""}
                try:
                    html = _render_compare_page(slug, dynamic_pair)
                    if html is not None:
                        if len(_page_cache) < _CACHE_MAX:
                            _page_cache[slug] = (html, _t.time())
                        return HTMLResponse(content=html)
                except Exception:
                    pass
                # Last resort: crypto token comparison
                try:
                    conn = get_db()
                    a = conn.execute("SELECT * FROM crypto_tokens WHERE id = ?", (parts[0],)).fetchone()
                    b = conn.execute("SELECT * FROM crypto_tokens WHERE id = ?", (parts[1],)).fetchone()
                    conn.close()
                    if a and b:
                        return HTMLResponse(content=render_compare_page(a, b))
                except Exception:
                    pass
            # Return "not yet analyzed" instead of 404 to preserve crawl budget
            if "-vs-" in slug:
                parts_nya = slug.split("-vs-", 1)
                _dn_a = parts_nya[0].replace("-", " ").title()
                _dn_b = parts_nya[1].replace("-", " ").title()
                try:
                    from agentindex.agent_safety_pages import _queue_for_crawling
                    _queue_for_crawling(parts_nya[0], bot="compare-404")
                    _queue_for_crawling(parts_nya[1], bot="compare-404")
                except Exception:
                    pass
                return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{_dn_a} vs {_dn_b} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{_dn_a} vs {_dn_b} — Comparison Not Yet Available</h1>
<p>This comparison has been queued for analysis.</p>
<p><a href="/compare">Browse comparisons</a> · <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
            return HTMLResponse(status_code=404, content="<h1>Not found</h1>")

        if "-vs-" not in slug:
            return HTMLResponse(status_code=404, content="<h1>Not found</h1>")
        parts = slug.split("-vs-", 1)
        token_a_id, token_b_id = parts[0], parts[1]
        conn = get_db()
        a = conn.execute("SELECT * FROM crypto_tokens WHERE id = ?", (token_a_id,)).fetchone()
        b = conn.execute("SELECT * FROM crypto_tokens WHERE id = ?", (token_b_id,)).fetchone()
        conn.close()
        if not a or not b:
            return HTMLResponse(status_code=404, content="<h1>Token not found</h1>")
        return HTMLResponse(content=render_compare_page(a, b))

    @app.get("/sitemap-compare.xml", response_class=Response)
    def sitemap_compare(request: Request):
        # Nerq agent comparison sitemap
        host = request.headers.get("host", "")
        if "zarq.ai" not in host:
            from agentindex.agent_compare_pages import _load_pairs, _pairs
            _load_pairs()
            today = date.today().isoformat()
            xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
            xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            xml += f'  <url>\n    <loc>https://nerq.ai/compare</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.9</priority>\n  </url>\n'
            for p in _pairs:
                xml += f'  <url>\n    <loc>https://nerq.ai/compare/{p["slug"]}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.9</priority>\n  </url>\n'
            xml += '</urlset>'
            return Response(content=xml, media_type="application/xml")

        conn = get_db()
        top = conn.execute(
            "SELECT id FROM crypto_tokens WHERE trust_score IS NOT NULL ORDER BY trust_score DESC LIMIT 50"
        ).fetchall()
        conn.close()
        ids = [r["id"] for r in top]
        today = date.today().isoformat()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for i, a in enumerate(ids):
            for b in ids[i+1:]:
                xml += f'  <url><loc>https://zarq.ai/compare/{a}-vs-{b}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.6</priority></url>\n'
        xml += '</urlset>'
        return Response(content=xml, media_type="application/xml")


def mount_agent_intelligence_page(app):
    import os
    from fastapi.responses import HTMLResponse
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "zarq_agent_intelligence.html")

    @app.get("/agent-intelligence", response_class=HTMLResponse)
    def agent_intelligence_page():
        if os.path.exists(template_path):
            with open(template_path) as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(status_code=404, content="<h1>Agent Intelligence page not found</h1>")
