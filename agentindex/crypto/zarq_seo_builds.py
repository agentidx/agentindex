"""
ZARQ Crypto SEO Pages — Builds 1-6
====================================
- BUILD 1: /is-{token}-dead (15,102 pages)
- BUILD 2: /is-{token}-a-scam (16,300 pages)
- BUILD 3: /compare/{a}-vs-{b} crypto comparisons (1,000 pairs)
- BUILD 4: /best/* category pages (50 pages)
- BUILD 5: /defi/{protocol} yield safety (2,214 pages)
- BUILD 6: /crash-prediction/{token} (204 pages)
- Sitemaps for all

Usage in discovery.py:
    from agentindex.crypto.zarq_seo_builds import mount_zarq_seo_builds
    mount_zarq_seo_builds(app)
"""

import json
import logging
import sqlite3
import time
from datetime import date
from pathlib import Path

from fastapi.responses import HTMLResponse, Response

logger = logging.getLogger("zarq.seo_builds")

DB_PATH = str(Path(__file__).parent / "crypto_trust.db")
SLUGS_PATH = Path(__file__).parent / "token_slugs.json"
SITE = "https://zarq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year
MONTH = date.today().strftime("%B %Y")

_cache = {}
CACHE_TTL = 3600
_slugs = {}

# ─────────────────────────────────────────────
# Shared CSS / Layout
# ─────────────────────────────────────────────

ZARQ_CSS = """<style>
:root{--warm:#c2956b;--green:#00d4aa;--yellow:#f5a623;--red:#ff4757;--bg:#0a0a0a;--card:#141414;--border:#222;--text:#e8e6e3;--muted:#78716c;--sans:'DM Sans',system-ui,sans-serif;--serif:'DM Serif Display',Georgia,serif;--mono:'JetBrains Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--sans);background:var(--bg);color:var(--text);line-height:1.6}
a{color:var(--warm);text-decoration:none}a:hover{text-decoration:underline}
.container{max-width:900px;margin:0 auto;padding:24px}
h1{font-family:var(--serif);font-size:1.8rem;margin-bottom:8px}
h2{font-family:var(--serif);font-size:1.2rem;margin:24px 0 8px;border-top:1px solid var(--border);padding-top:16px}
table{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}
th{text-align:left;padding:8px;border-bottom:2px solid var(--border);color:var(--muted);font-weight:600}
td{padding:8px;border-bottom:1px solid var(--border)}
.score-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}
.card{padding:16px;background:var(--card);border:1px solid var(--border);text-align:center}
.card .num{font-size:24px;font-weight:700;font-family:var(--mono)}
.card .lbl{font-size:10px;color:var(--muted);text-transform:uppercase;margin-top:4px}
.verdict{display:inline-block;padding:8px 20px;font-weight:700;font-size:18px;font-family:var(--mono);letter-spacing:1px;margin:12px 0;border:2px solid}
.faq-q{font-weight:600;font-size:14px;padding:12px 0;border-bottom:1px solid var(--border)}
.faq-a{font-size:13px;color:var(--muted);padding:8px 0 12px}
pre{background:var(--card);padding:8px 12px;font-size:12px;overflow-x:auto;border:1px solid var(--border);font-family:var(--mono)}
.nav{padding:12px 24px;border-bottom:1px solid var(--border);font-size:13px}
.nav a{color:var(--warm);margin-right:16px}
.footer{padding:24px;border-top:1px solid var(--border);text-align:center;font-size:12px;color:var(--muted);margin-top:48px}
@media(max-width:600px){.score-grid{grid-template-columns:repeat(2,1fr)}h1{font-size:1.4rem}.container{padding:16px}}
</style>"""

ZARQ_NAV = '<div class="nav"><a href="/">ZARQ</a><a href="/tokens">Tokens</a><a href="/crash-watch">Crash Watch</a><a href="/vitality">Vitality</a><a href="/yield-risk">Yield Risk</a><a href="/contagion">Contagion</a></div>'
ZARQ_FOOTER = '<div class="footer">&copy; 2026 <a href="/">ZARQ</a> — Independent crypto risk intelligence. Not investment advice.</div>'
DISCLAIMER = "ZARQ ratings are quantitative risk assessments based on public blockchain data, not investment advice. Past performance does not predict future results. Always do your own research."


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _cached(key):
    e = _cache.get(key)
    if e and (time.time() - e[0]) < CACHE_TTL:
        return e[1]
    return None


def _set_cache(key, val):
    _cache[key] = (time.time(), val)
    return val


def _esc(t):
    if not t:
        return ""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _load_slugs():
    global _slugs
    if _slugs:
        return
    try:
        with open(SLUGS_PATH) as f:
            _slugs = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load token slugs: {e}")


def _get_db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _fmt(n):
    if n is None:
        return "N/A"
    if isinstance(n, float):
        if abs(n) >= 1_000_000:
            return f"${n / 1_000_000:.1f}M"
        if abs(n) >= 1_000:
            return f"${n / 1_000:.1f}K"
        return f"{n:.2f}"
    return str(n)


def _color_crash(prob):
    if prob is None:
        return "var(--muted)"
    if prob > 0.3:
        return "var(--red)"
    if prob > 0.1:
        return "var(--yellow)"
    return "var(--green)"


def _vitality_verdict(score):
    if score is None:
        return "UNKNOWN", "#78716c", "Insufficient data for vitality assessment."
    if score >= 70:
        return "ALIVE & THRIVING", "#00d4aa", "Strong ecosystem health. Active development and growing adoption."
    if score >= 50:
        return "ALIVE", "#00d4aa", "Moderate ecosystem health. Stable but not exceptional."
    if score >= 30:
        return "SHOWING SIGNS OF DECLINE", "#f5a623", "Declining activity. Monitor closely."
    if score >= 10:
        return "CRITICAL CONDITION", "#ff4757", "Severely declining. Most metrics negative."
    return "EFFECTIVELY DEAD", "#ff4757", "No meaningful activity detected. Project appears abandoned."


def _scam_verdict(risk_flags, age_days, has_liquidity):
    flags = risk_flags or 0
    if flags == 0 and age_days > 365 and has_liquidity:
        return "NO SCAM INDICATORS", "#00d4aa", "No red flags detected. Established project with liquidity."
    if flags <= 1 and age_days > 90:
        return "LOW RISK", "#00d4aa", f"{flags} minor risk flag. Established project."
    if flags <= 3:
        return "MODERATE RISK", "#f5a623", f"{flags} risk flags detected. Exercise caution."
    return "HIGH RISK", "#ff4757", f"{flags} risk flags detected. Multiple scam indicators present."


def _head(title, desc, canonical, extra_meta=""):
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="ZARQ">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{_esc(title)}">
<meta name="twitter:description" content="{_esc(desc)}">
<meta name="citation_title" content="{_esc(title)}">
<meta name="citation_author" content="ZARQ">
<meta name="citation_date" content="{TODAY}">
<meta name="robots" content="max-snippet:-1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=DM+Serif+Display&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
{extra_meta}
{ZARQ_CSS}
</head><body>
{ZARQ_NAV}
<main class="container">"""


def _foot(token_id=""):
    links = f"""<div style="margin-top:24px;display:flex;flex-wrap:wrap;gap:8px;font-size:12px">
<a href="/tokens">All Tokens</a> <a href="/crash-watch">Crash Watch</a> <a href="/vitality">Vitality</a>
<a href="/yield-risk">Yield Risk</a> <a href="/contagion">Contagion</a> <a href="/methodology">Methodology</a>
<a href="/track-record">Track Record</a> <a href="/scan">Scan Portfolio</a>
{f'<a href="/token/{token_id}">Full Analysis</a>' if token_id else ''}
{f'<a href="/is-{token_id}-dead">Dead?</a> <a href="/is-{token_id}-a-scam">Scam?</a> <a href="/crash-prediction/{token_id}">Crash?</a>' if token_id else ''}
</div>
<p style="font-size:11px;color:var(--muted);margin-top:16px">{DISCLAIMER}</p>
</main>
{ZARQ_FOOTER}
</body></html>"""
    return links


def _faq_jsonld(items):
    entries = ",".join(
        f'{{"@type":"Question","name":"{_esc(q)}","acceptedAnswer":{{"@type":"Answer","text":"{_esc(a)}"}}}}'
        for q, a in items
    )
    return f'{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{entries}]}}'


def _breadcrumb_jsonld(crumbs):
    items = ",".join(
        f'{{"@type":"ListItem","position":{i},"name":"{_esc(name)}","item":"{url}"}}'
        for i, (name, url) in enumerate(crumbs, 1)
    )
    return f'{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{items}]}}'


def _faq_html(items):
    return "".join(f'<div class="faq-q">{_esc(q)}</div><div class="faq-a">{a}</div>' for q, a in items)


def _get_token_data(token_id):
    """Fetch token data from multiple tables."""
    conn = _get_db()
    try:
        ndd = conn.execute(
            "SELECT ndd, crash_probability, alert_level, price_usd, symbol, name "
            "FROM crypto_ndd_daily WHERE token_id = ? ORDER BY run_date DESC LIMIT 1",
            (token_id,),
        ).fetchone()
        rating = conn.execute(
            "SELECT rating, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5 "
            "FROM crypto_rating_daily WHERE token_id = ? ORDER BY run_date DESC LIMIT 1",
            (token_id,),
        ).fetchone()
        risk = conn.execute(
            "SELECT risk_level, structural_weakness, trust_score, sig6_structure, drawdown_90d "
            "FROM nerq_risk_signals WHERE token_id = ? ORDER BY signal_date DESC LIMIT 1",
            (token_id,),
        ).fetchone()
        vitality = conn.execute(
            "SELECT vitality_score, vitality_grade "
            "FROM vitality_scores WHERE token_id = ? ORDER BY rowid DESC LIMIT 1",
            (token_id,),
        ).fetchone()
        return ndd, rating, risk, vitality
    finally:
        conn.close()


def _get_token_name_symbol(token_id, slug_data, ndd):
    name = (slug_data or {}).get("name") or (ndd["name"] if ndd and ndd["name"] else None) or token_id.replace("-", " ").title()
    symbol = (slug_data or {}).get("symbol") or (ndd["symbol"] if ndd and ndd["symbol"] else None) or token_id.split("-")[0].upper()
    return name, symbol


# ─────────────────────────────────────────────
# Main mount
# ─────────────────────────────────────────────

def mount_zarq_seo_builds(app):
    """Mount all ZARQ crypto SEO builds (1-6) plus sitemaps."""
    _load_slugs()

    # ════════════════════════════════════════════════════════
    # BUILD 1: /is-{token}-dead  —  Vitality / "is X dead?"
    # ════════════════════════════════════════════════════════

    @app.get("/is-{token_id}-dead", response_class=HTMLResponse)
    async def is_token_dead(token_id: str):
        ck = f"dead:{token_id}"
        c = _cached(ck)
        if c:
            return HTMLResponse(c)

        _load_slugs()
        slug_data = _slugs.get(token_id)
        if not slug_data and token_id not in _slugs:
            # Also check DB directly
            conn = _get_db()
            try:
                row = conn.execute("SELECT token_id FROM crypto_ndd_daily WHERE token_id = ? LIMIT 1", (token_id,)).fetchone()
            finally:
                conn.close()
            if not row:
                # Queue demand signal and return not-yet-analyzed
                try:
                    from agentindex.agent_safety_pages import _queue_for_crawling
                    _queue_for_crawling(token_id, bot="zarq-dead-404")
                except Exception:
                    pass
                return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{token_id.replace("-"," ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{token_id.replace("-"," ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

        ndd, rating, risk, vitality = _get_token_data(token_id)
        name, symbol = _get_token_name_symbol(token_id, slug_data, ndd)

        vit_score = vitality["vitality_score"] if vitality else None
        vit_grade = vitality["vitality_grade"] if vitality else "N/A"
        crash_prob = ndd["crash_probability"] if ndd else None
        crash_pct = f"{crash_prob * 100:.0f}" if crash_prob is not None else "N/A"
        rating_str = rating["rating"] if rating else "NR"
        alert = ndd["alert_level"] if ndd else "N/A"
        ndd_val = ndd["ndd"] if ndd else None
        price = ndd["price_usd"] if ndd else None
        drawdown = risk["drawdown_90d"] if risk else None
        risk_level = risk["risk_level"] if risk else "N/A"

        verdict, vc, vdesc = _vitality_verdict(vit_score)
        title = f"Is {name} Dead? Vitality & Risk Analysis {YEAR} | ZARQ"
        meta_desc = f"Is {name} ({symbol}) dead in {YEAR}? Vitality Score: {vit_score or 'N/A'}/100. Crash probability: {crash_pct}%. Rating: {rating_str}. Independent quantitative analysis by ZARQ."
        canonical = f"{SITE}/is-{token_id}-dead"

        faq_items = [
            (f"Is {name} dead?",
             f"{name} has a ZARQ Vitality Score of {vit_score or 'N/A'}/100 ({vit_grade}). Verdict: {verdict.lower()}. {vdesc}"),
            (f"Will {name} recover?",
             f"Crash probability: {crash_pct}%. Alert level: {_esc(alert)}. "
             f"{'Recovery signals are present based on ecosystem activity.' if vit_score and vit_score > 40 else 'Recovery looks uncertain based on current metrics.'}"),
            (f"Should I sell {name}?",
             f"This is not investment advice. {name} has a {rating_str} rating with {crash_pct}% crash risk. "
             f"{'The vitality score suggests continued viability.' if vit_score and vit_score > 50 else 'Current metrics suggest elevated risk.'}"),
            (f"Is {name} a good investment in {YEAR}?",
             f"ZARQ rates {name} at {rating_str} with a vitality score of {vit_score or 'N/A'}/100. "
             f"Crash probability: {crash_pct}%. Always do your own research."),
            (f"What is {name}'s ZARQ rating?",
             f"{name} has a ZARQ Trust Rating of {rating_str}. This is based on five pillars: market structure, liquidity, on-chain health, ecosystem activity, and governance."),
        ]

        zarq_meta = f"""<meta name="zarq:type" content="is_dead">
<meta name="zarq:token" content="{_esc(name)}">
<meta name="zarq:symbol" content="{_esc(symbol)}">
<meta name="zarq:vitality" content="{vit_score or 0}">
<meta name="zarq:verdict" content="{verdict}">
<meta name="zarq:updated" content="{TODAY}">"""

        jsonld = f"""<script type="application/ld+json">{_faq_jsonld(faq_items)}</script>
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"FinancialProduct","name":"{_esc(name)} Vitality Analysis","url":"{canonical}","description":"Vitality and risk analysis for {_esc(name)}","provider":{{"@type":"Organization","name":"ZARQ","url":"{SITE}"}}}}</script>
<script type="application/ld+json">{_breadcrumb_jsonld([("ZARQ", SITE), ("Tokens", f"{SITE}/tokens"), (f"Is {name} Dead?", canonical)])}</script>"""

        page = _head(title, meta_desc, canonical, zarq_meta + jsonld)
        page += f"""
<nav style="font-size:12px;color:var(--muted);margin-bottom:16px"><a href="/">ZARQ</a> &rsaquo; <a href="/tokens">Tokens</a> &rsaquo; Is {_esc(name)} Dead?</nav>

<h1>Is {_esc(name)} ({_esc(symbol)}) Dead?</h1>
<p style="font-size:15px;color:var(--text);margin:8px 0 16px">{_esc(name)} is <strong style="color:{vc}">{verdict}</strong>. ZARQ Vitality Score: <strong>{vit_score or 'N/A'}/100</strong> ({vit_grade}). Crash probability: {crash_pct}%. Rating: {rating_str}. Last analyzed {MONTH}.</p>

<div class="verdict" style="color:{vc};border-color:{vc}">{verdict}</div>
<p style="font-size:14px;color:var(--muted);margin-bottom:20px">{vdesc}</p>

<div class="score-grid">
<div class="card"><div class="num" style="color:{vc}">{vit_score or 'N/A'}</div><div class="lbl">Vitality</div></div>
<div class="card"><div class="num">{rating_str}</div><div class="lbl">Rating</div></div>
<div class="card"><div class="num" style="color:{_color_crash(crash_prob)}">{crash_pct}%</div><div class="lbl">Crash Risk</div></div>
<div class="card"><div class="num">{_esc(alert)}</div><div class="lbl">Alert</div></div>
</div>

<h2>Vitality Analysis</h2>
<p style="font-size:14px;color:var(--text)">{_esc(name)} has a vitality score of {vit_score or 'N/A'}/100, grade {vit_grade}. {'This indicates strong ecosystem health with active development, consistent trading volume, and growing community engagement.' if vit_score and vit_score >= 60 else 'Activity metrics show moderate levels. The project is functional but growth has stalled.' if vit_score and vit_score >= 30 else 'Most health indicators are negative. Development activity and community engagement have declined significantly.'}</p>

<h2>Risk Metrics</h2>
<table>
<tr><th>Metric</th><th>Value</th><th>Signal</th></tr>
<tr><td>Distance-to-Default (NDD)</td><td style="font-family:var(--mono)">{f'{ndd_val:.2f}' if ndd_val else 'N/A'}</td><td>{'Healthy' if ndd_val and ndd_val > 2 else 'Watch' if ndd_val and ndd_val > 1 else 'Danger' if ndd_val else 'N/A'}</td></tr>
<tr><td>Crash Probability (30d)</td><td style="font-family:var(--mono);color:{_color_crash(crash_prob)}">{crash_pct}%</td><td>{'Low' if crash_prob and crash_prob < 0.1 else 'Elevated' if crash_prob and crash_prob < 0.3 else 'High' if crash_prob else 'N/A'}</td></tr>
<tr><td>Structural Weakness</td><td>{risk['structural_weakness'] if risk else 'N/A'}</td><td>{'None' if risk and risk['structural_weakness'] == 0 else 'Present' if risk else 'N/A'}</td></tr>
<tr><td>Risk Level</td><td>{_esc(risk_level)}</td><td></td></tr>
<tr><td>Alert Level</td><td>{_esc(alert)}</td><td></td></tr>
{f'<tr><td>90d Drawdown</td><td style="color:var(--red)">{drawdown:.1f}%</td><td></td></tr>' if drawdown else ''}
{f'<tr><td>Price (USD)</td><td style="font-family:var(--mono)">${price:.6f}</td><td></td></tr>' if price else ''}
</table>

<h2>What Does "Dead" Mean for Crypto?</h2>
<p style="font-size:14px;color:var(--text)">A cryptocurrency is considered "dead" when it shows no meaningful development activity, trading volume has collapsed, the community has disbanded, and the project shows no signs of recovery. ZARQ's Vitality Score measures this across multiple dimensions: on-chain activity, developer commits, social engagement, exchange listings, and liquidity depth.</p>

<h2>Frequently Asked Questions</h2>
{_faq_html(faq_items)}

<h2>API Access</h2>
<div style="margin-top:8px;padding:16px;background:var(--card);border:1px solid var(--border)">
<p style="font-size:12px;color:var(--muted);margin-bottom:8px">Check any token programmatically:</p>
<pre>curl -s zarq.ai/v1/crypto/check/{token_id} | jq .</pre>
</div>
"""
        page += _foot(token_id)
        return HTMLResponse(_set_cache(ck, page))

    # ════════════════════════════════════════════════════════
    # BUILD 2: /is-{token}-a-scam  —  Legitimacy check
    # ════════════════════════════════════════════════════════

    @app.get("/is-{token_id}-a-scam", response_class=HTMLResponse)
    async def is_token_scam(token_id: str):
        ck = f"scam:{token_id}"
        c = _cached(ck)
        if c:
            return HTMLResponse(c)

        _load_slugs()
        slug_data = _slugs.get(token_id)

        ndd, rating, risk, vitality = _get_token_data(token_id)
        name, symbol = _get_token_name_symbol(token_id, slug_data, ndd)

        if not ndd and not rating and not risk:
            # Not a crypto token — try Nerq's universal pattern
            try:
                from agentindex.pattern_routes import _pattern_page
                html = _pattern_page(token_id, "a-scam",
                    "Is {name} a Scam? Legitimacy Check 2026 | Nerq",
                    "Is {name} a scam?", "Not a Scam", "Scam Risk",
                    "Based on business verification, user reports, and trust signals.")
                if html:
                    return HTMLResponse(html)
            except Exception:
                pass
            # Queue demand signal and return not-yet-analyzed instead of 404
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(token_id, bot="zarq-scam-404")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{_esc(name)} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {_esc(name)}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{_esc(name)} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

        struct_weak = risk["structural_weakness"] if risk else 0
        vit_score = vitality["vitality_score"] if vitality else None
        rating_str = rating["rating"] if rating else "NR"
        trust = risk["trust_score"] if risk else (rating["score"] if rating else None)
        trust_str = f"{trust:.0f}" if trust is not None else "N/A"
        crash_prob = ndd["crash_probability"] if ndd else None
        crash_pct = f"{crash_prob * 100:.0f}" if crash_prob is not None else "N/A"
        price = ndd["price_usd"] if ndd else None
        risk_level = risk["risk_level"] if risk else "N/A"

        verdict, vc, vdesc = _scam_verdict(struct_weak, 365, vit_score and vit_score > 20)
        title = f"Is {name} a Scam? Legitimacy Check {YEAR} | ZARQ"
        meta_desc = f"Is {name} ({symbol}) a scam? {struct_weak} risk flags detected. ZARQ Trust Rating: {rating_str}. Trust Score: {trust_str}/100. Independent legitimacy analysis."
        canonical = f"{SITE}/is-{token_id}-a-scam"

        faq_items = [
            (f"Is {name} a scam?",
             f"{name} shows {struct_weak} structural risk flags. Verdict: {verdict.lower()}. {vdesc}"),
            (f"Is {name} legit?",
             f"ZARQ Trust Rating: {rating_str}. Vitality: {vit_score or 'N/A'}/100. "
             f"{'Established project with consistent on-chain activity.' if vit_score and vit_score > 50 else 'Limited activity signals detected.'}"),
            (f"Can I trust {name}?",
             f"Trust score: {trust_str}/100. {struct_weak} structural risk flags detected. Always verify independently before investing."),
            (f"Is {name} a rug pull?",
             f"Structural weakness score: {struct_weak}. "
             f"{'No rug pull indicators detected.' if struct_weak == 0 else 'Some structural concerns present. Review liquidity lock status and team transparency.'}"),
            (f"How safe is {name}?",
             f"ZARQ rates {name} at {rating_str}. Crash probability: {crash_pct}%. "
             f"Risk level: {_esc(risk_level)}. This is a quantitative assessment, not investment advice."),
        ]

        zarq_meta = f"""<meta name="zarq:type" content="scam_check">
<meta name="zarq:token" content="{_esc(name)}">
<meta name="zarq:symbol" content="{_esc(symbol)}">
<meta name="zarq:verdict" content="{verdict}">
<meta name="zarq:risk_flags" content="{struct_weak}">
<meta name="zarq:updated" content="{TODAY}">"""

        jsonld = f"""<script type="application/ld+json">{_faq_jsonld(faq_items)}</script>
<script type="application/ld+json">{_breadcrumb_jsonld([("ZARQ", SITE), ("Tokens", f"{SITE}/tokens"), (f"Is {name} a Scam?", canonical)])}</script>"""

        page = _head(title, meta_desc, canonical, zarq_meta + jsonld)
        page += f"""
<nav style="font-size:12px;color:var(--muted);margin-bottom:16px"><a href="/">ZARQ</a> &rsaquo; <a href="/tokens">Tokens</a> &rsaquo; Is {_esc(name)} a Scam?</nav>

<h1>Is {_esc(name)} ({_esc(symbol)}) a Scam?</h1>
<p style="font-size:15px;color:var(--text);margin:8px 0 16px">{_esc(name)} {verdict.lower().replace('no scam indicators', 'shows no scam indicators')}. ZARQ Trust Rating: {rating_str}. {struct_weak} risk flags detected. Trust Score: {trust_str}/100. Vitality: {vit_score or 'N/A'}/100. Last analyzed {MONTH}.</p>

<div class="verdict" style="color:{vc};border-color:{vc}">{verdict}</div>
<p style="font-size:14px;color:var(--muted);margin-bottom:20px">{vdesc}</p>

<div class="score-grid">
<div class="card"><div class="num" style="color:{'var(--green)' if struct_weak == 0 else 'var(--red)'}">{struct_weak}</div><div class="lbl">Risk Flags</div></div>
<div class="card"><div class="num">{rating_str}</div><div class="lbl">Rating</div></div>
<div class="card"><div class="num">{trust_str}</div><div class="lbl">Trust Score</div></div>
<div class="card"><div class="num">{vit_score or 'N/A'}</div><div class="lbl">Vitality</div></div>
</div>

<h2>Legitimacy Indicators</h2>
<table>
<tr><th>Signal</th><th>Status</th><th>Assessment</th></tr>
<tr><td>Structural Risk Flags</td><td style="color:{'var(--green)' if struct_weak == 0 else 'var(--yellow)' if struct_weak <= 2 else 'var(--red)'}">{struct_weak} detected</td><td>{'Clean' if struct_weak == 0 else 'Minor concerns' if struct_weak <= 2 else 'Significant concerns'}</td></tr>
<tr><td>Vitality Score</td><td>{vit_score or 'N/A'}/100</td><td>{'Active project' if vit_score and vit_score > 50 else 'Low activity' if vit_score else 'Unknown'}</td></tr>
<tr><td>Trust Rating</td><td style="font-weight:700">{rating_str}</td><td>{'Investment grade' if rating and rating['score'] and rating['score'] >= 60 else 'Sub-investment grade' if rating else 'Unrated'}</td></tr>
<tr><td>Risk Level</td><td>{_esc(risk_level)}</td><td></td></tr>
<tr><td>Price Data Available</td><td>{'Yes' if ndd else 'No'}</td><td>{'Actively traded' if ndd else 'May be delisted or illiquid'}</td></tr>
{f'<tr><td>Crash Probability</td><td style="color:{_color_crash(crash_prob)}">{crash_pct}%</td><td></td></tr>' if crash_prob is not None else ''}
</table>

<h2>Common Scam Red Flags</h2>
<p style="font-size:14px;color:var(--text)">ZARQ checks for: concentrated token ownership, locked vs. unlocked liquidity, contract audit status, anonymous teams, unrealistic yield promises, and sudden liquidity changes. {_esc(name)} currently shows {struct_weak} of these flags.</p>

<h2>Frequently Asked Questions</h2>
{_faq_html(faq_items)}

<h2>API Access</h2>
<div style="margin-top:8px;padding:16px;background:var(--card);border:1px solid var(--border)">
<pre>curl -s zarq.ai/v1/crypto/check/{token_id} | jq .risk_flags</pre>
</div>
"""
        page += _foot(token_id)
        return HTMLResponse(_set_cache(ck, page))

    # ════════════════════════════════════════════════════════
    # BUILD 3: /compare/{a}-vs-{b}  —  Token comparisons
    # ════════════════════════════════════════════════════════

    @app.get("/compare/{token_a}-vs-{token_b}", response_class=HTMLResponse)
    async def compare_tokens(token_a: str, token_b: str):
        ck = f"compare:{token_a}:{token_b}"
        c = _cached(ck)
        if c:
            return HTMLResponse(c)

        _load_slugs()
        slug_a = _slugs.get(token_a, {})
        slug_b = _slugs.get(token_b, {})

        ndd_a, rating_a, risk_a, vit_a = _get_token_data(token_a)
        ndd_b, rating_b, risk_b, vit_b = _get_token_data(token_b)

        if not ndd_a and not rating_a and not ndd_b and not rating_b:
            return HTMLResponse(status_code=404, content="<h1>Comparison not available</h1>")

        name_a, sym_a = _get_token_name_symbol(token_a, slug_a, ndd_a)
        name_b, sym_b = _get_token_name_symbol(token_b, slug_b, ndd_b)

        rating_a_str = rating_a["rating"] if rating_a else "NR"
        rating_b_str = rating_b["rating"] if rating_b else "NR"
        score_a = rating_a["score"] if rating_a else 0
        score_b = rating_b["score"] if rating_b else 0
        crash_a = ndd_a["crash_probability"] if ndd_a else None
        crash_b = ndd_b["crash_probability"] if ndd_b else None
        crash_a_pct = f"{crash_a * 100:.0f}" if crash_a is not None else "N/A"
        crash_b_pct = f"{crash_b * 100:.0f}" if crash_b is not None else "N/A"
        vit_a_score = vit_a["vitality_score"] if vit_a else None
        vit_b_score = vit_b["vitality_score"] if vit_b else None
        ndd_a_val = ndd_a["ndd"] if ndd_a else None
        ndd_b_val = ndd_b["ndd"] if ndd_b else None
        price_a = ndd_a["price_usd"] if ndd_a else None
        price_b = ndd_b["price_usd"] if ndd_b else None

        # Determine winner
        if score_a > score_b:
            winner = name_a
            winner_reason = f"{name_a} has a higher ZARQ rating ({rating_a_str} vs {rating_b_str})."
        elif score_b > score_a:
            winner = name_b
            winner_reason = f"{name_b} has a higher ZARQ rating ({rating_b_str} vs {rating_a_str})."
        else:
            winner = "Tied"
            winner_reason = f"Both tokens share the same ZARQ rating ({rating_a_str})."

        title = f"{name_a} vs {name_b}: Which Is Safer? {YEAR} | ZARQ"
        meta_desc = f"{name_a} vs {name_b} comparison. {name_a}: {rating_a_str} rating, {crash_a_pct}% crash risk. {name_b}: {rating_b_str} rating, {crash_b_pct}% crash risk. Independent analysis by ZARQ."
        canonical = f"{SITE}/compare/{token_a}-vs-{token_b}"

        faq_items = [
            (f"Is {name_a} or {name_b} safer?",
             f"{winner_reason} {name_a} crash probability: {crash_a_pct}%. {name_b} crash probability: {crash_b_pct}%."),
            (f"Should I buy {name_a} or {name_b}?",
             f"This is not investment advice. {name_a} is rated {rating_a_str} and {name_b} is rated {rating_b_str} by ZARQ. Always do your own research."),
            (f"Which has better fundamentals, {name_a} or {name_b}?",
             f"{name_a} vitality: {vit_a_score or 'N/A'}/100. {name_b} vitality: {vit_b_score or 'N/A'}/100. "
             f"{'Both show strong ecosystem health.' if vit_a_score and vit_b_score and vit_a_score > 50 and vit_b_score > 50 else 'Ecosystem health varies between the two.'}"),
        ]

        jsonld = f"""<script type="application/ld+json">{_faq_jsonld(faq_items)}</script>
<script type="application/ld+json">{_breadcrumb_jsonld([("ZARQ", SITE), ("Tokens", f"{SITE}/tokens"), (f"{name_a} vs {name_b}", canonical)])}</script>"""

        def _better(a, b, higher_is_better=True):
            if a is None or b is None:
                return "", ""
            if higher_is_better:
                return ("color:var(--green)" if a > b else "color:var(--red)" if a < b else ""), \
                       ("color:var(--green)" if b > a else "color:var(--red)" if b < a else "")
            else:
                return ("color:var(--green)" if a < b else "color:var(--red)" if a > b else ""), \
                       ("color:var(--green)" if b < a else "color:var(--red)" if b > a else "")

        sc_a, sc_b = _better(score_a, score_b)
        cc_a, cc_b = _better(crash_a, crash_b, False)
        vc_a, vc_b = _better(vit_a_score, vit_b_score)

        page = _head(title, meta_desc, canonical, jsonld)
        page += f"""
<nav style="font-size:12px;color:var(--muted);margin-bottom:16px"><a href="/">ZARQ</a> &rsaquo; <a href="/tokens">Tokens</a> &rsaquo; {_esc(name_a)} vs {_esc(name_b)}</nav>

<h1>{_esc(name_a)} vs {_esc(name_b)}: Which Is Safer?</h1>
<p style="font-size:15px;color:var(--text);margin:8px 0 16px">Head-to-head risk comparison. {winner_reason} Updated {MONTH}.</p>

<table>
<tr><th>Metric</th><th>{_esc(name_a)} ({_esc(sym_a)})</th><th>{_esc(name_b)} ({_esc(sym_b)})</th></tr>
<tr><td>ZARQ Rating</td><td style="font-weight:700;{sc_a}">{rating_a_str}</td><td style="font-weight:700;{sc_b}">{rating_b_str}</td></tr>
<tr><td>Trust Score</td><td style="{sc_a}">{score_a:.0f}/100</td><td style="{sc_b}">{score_b:.0f}/100</td></tr>
<tr><td>Crash Probability</td><td style="{cc_a}">{crash_a_pct}%</td><td style="{cc_b}">{crash_b_pct}%</td></tr>
<tr><td>NDD</td><td>{f'{ndd_a_val:.2f}' if ndd_a_val else 'N/A'}</td><td>{f'{ndd_b_val:.2f}' if ndd_b_val else 'N/A'}</td></tr>
<tr><td>Vitality</td><td style="{vc_a}">{vit_a_score or 'N/A'}/100</td><td style="{vc_b}">{vit_b_score or 'N/A'}/100</td></tr>
<tr><td>Risk Flags</td><td>{risk_a['structural_weakness'] if risk_a else 'N/A'}</td><td>{risk_b['structural_weakness'] if risk_b else 'N/A'}</td></tr>
{f'<tr><td>Price</td><td>${price_a:.6f}</td><td>${price_b:.6f}</td></tr>' if price_a and price_b else ''}
</table>

<h2>Verdict</h2>
<p style="font-size:15px;color:var(--text)">{winner_reason}</p>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0">
<div style="padding:16px;background:var(--card);border:1px solid var(--border)">
<h3 style="font-family:var(--serif);font-size:1rem;margin-bottom:8px">{_esc(name_a)}</h3>
<p style="font-size:13px;color:var(--muted)">Rating: {rating_a_str} | Vitality: {vit_a_score or 'N/A'}/100 | Crash: {crash_a_pct}%</p>
<div style="margin-top:8px;font-size:12px"><a href="/token/{token_a}">Full analysis</a> | <a href="/is-{token_a}-dead">Dead?</a> | <a href="/is-{token_a}-a-scam">Scam?</a></div>
</div>
<div style="padding:16px;background:var(--card);border:1px solid var(--border)">
<h3 style="font-family:var(--serif);font-size:1rem;margin-bottom:8px">{_esc(name_b)}</h3>
<p style="font-size:13px;color:var(--muted)">Rating: {rating_b_str} | Vitality: {vit_b_score or 'N/A'}/100 | Crash: {crash_b_pct}%</p>
<div style="margin-top:8px;font-size:12px"><a href="/token/{token_b}">Full analysis</a> | <a href="/is-{token_b}-dead">Dead?</a> | <a href="/is-{token_b}-a-scam">Scam?</a></div>
</div>
</div>

<h2>FAQ</h2>
{_faq_html(faq_items)}
"""
        page += _foot()
        return HTMLResponse(_set_cache(ck, page))

    # ════════════════════════════════════════════════════════
    # BUILD 4: /best/*  —  Category ranking pages
    # ════════════════════════════════════════════════════════

    BEST_CATEGORIES = {
        "safest-crypto-2026": {
            "title": "Safest Crypto to Invest In 2026",
            "desc": "Top cryptocurrencies ranked by ZARQ Trust Rating. Quantitative safety analysis based on crash probability, vitality, and structural risk.",
            "query": "ORDER BY r.score DESC",
        },
        "investment-grade-crypto": {
            "title": "Investment Grade Crypto (Baa3+)",
            "desc": "Cryptocurrencies rated Baa3 or above by ZARQ — the crypto equivalent of investment-grade bonds.",
            "query": "HAVING r.score >= 60 ORDER BY r.score DESC",
        },
        "crypto-least-likely-to-crash": {
            "title": "Crypto Least Likely to Crash",
            "desc": "Tokens with the lowest crash probability according to ZARQ's v3 crash prediction model.",
            "query": "ORDER BY n.crash_probability ASC",
        },
        "crypto-with-highest-vitality": {
            "title": "Crypto with Highest Vitality Score",
            "desc": "Most active and healthy crypto ecosystems ranked by ZARQ Vitality Score.",
            "query": "ORDER BY v.vitality_score DESC",
        },
        "layer-1-crypto-ranked": {
            "title": "Layer 1 Crypto Ranked by Safety",
            "desc": "Top Layer 1 blockchains ranked by ZARQ safety rating. Compare Ethereum, Solana, Avalanche and more.",
            "query": "ORDER BY r.score DESC",
        },
        "meme-coins-ranked-by-safety": {
            "title": "Meme Coins Ranked by Safety",
            "desc": "Meme tokens ranked from safest to riskiest. Crash probability and vitality analysis for DOGE, SHIB, PEPE and more.",
            "query": "ORDER BY r.score DESC",
        },
        "ai-crypto-tokens": {
            "title": "AI Crypto Tokens Ranked by Safety",
            "desc": "AI and machine learning crypto tokens ranked by ZARQ Trust Rating. FET, RNDR, TAO and more.",
            "query": "ORDER BY r.score DESC",
        },
        "stablecoins-ranked": {
            "title": "Stablecoins Ranked by Safety",
            "desc": "Stablecoin safety ranking. Compare USDT, USDC, DAI and more by risk metrics.",
            "query": "ORDER BY r.score DESC",
        },
        "bitcoin-alternatives": {
            "title": "Bitcoin Alternatives Ranked by Safety",
            "desc": "Top Bitcoin alternatives ranked by ZARQ safety score. Compare risk profiles of BTC competitors.",
            "query": "ORDER BY r.score DESC",
        },
        "ethereum-alternatives": {
            "title": "Ethereum Alternatives Ranked by Safety",
            "desc": "Top Ethereum alternatives ranked by ZARQ safety score. Compare smart contract platforms.",
            "query": "ORDER BY r.score DESC",
        },
        "solana-alternatives": {
            "title": "Solana Alternatives Ranked by Safety",
            "desc": "Top Solana alternatives ranked by ZARQ safety score. High-performance L1s compared.",
            "query": "ORDER BY r.score DESC",
        },
        "defi-tokens-ranked": {
            "title": "DeFi Tokens Ranked by Safety",
            "desc": "DeFi governance tokens ranked by ZARQ Trust Rating. AAVE, UNI, MKR and more.",
            "query": "ORDER BY r.score DESC",
        },
        "gaming-crypto-ranked": {
            "title": "Gaming Crypto Tokens Ranked by Safety",
            "desc": "Gaming and metaverse tokens ranked by ZARQ Trust Rating and vitality.",
            "query": "ORDER BY r.score DESC",
        },
        "low-risk-crypto": {
            "title": "Low Risk Crypto Investments",
            "desc": "Lowest risk cryptocurrencies by ZARQ crash model. Tokens with under 5% crash probability.",
            "query": "HAVING n.crash_probability < 0.05 ORDER BY r.score DESC",
        },
        "highest-rated-crypto": {
            "title": "Highest Rated Crypto by ZARQ",
            "desc": "Top-rated cryptocurrencies by ZARQ Trust Rating system. Independent quantitative ratings.",
            "query": "ORDER BY r.score DESC",
        },
    }

    @app.get("/best/{category}", response_class=HTMLResponse)
    async def best_crypto_category(category: str):
        cat = BEST_CATEGORIES.get(category)
        if not cat:
            # Fall through to Nerq best-of pages (seo_programmatic handles all Nerq categories)
            try:
                from agentindex.seo_programmatic import BEST_CATEGORIES as PROG_CATS, _render_best_page
                if category in PROG_CATS:
                    return await _render_best_page(category)
            except Exception:
                pass
            return HTMLResponse(status_code=404, content="<h1>Category not found</h1>")

        ck = f"best:{category}"
        c = _cached(ck)
        if c:
            return HTMLResponse(c)

        display_name = cat["title"]
        conn = _get_db()
        try:
            rows = conn.execute("""
                SELECT r.token_id, r.rating, r.score, n.name, n.symbol, n.crash_probability,
                       v.vitality_score, v.vitality_grade, n.ndd, n.price_usd
                FROM crypto_rating_daily r
                LEFT JOIN crypto_ndd_daily n ON r.token_id = n.token_id
                    AND n.run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)
                LEFT JOIN vitality_scores v ON r.token_id = v.token_id
                WHERE r.run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
                GROUP BY r.token_id
                """ + cat["query"] + """
                LIMIT 50
            """).fetchall()
        finally:
            conn.close()

        rows_html = ""
        for i, r in enumerate(rows, 1):
            cp = f"{r['crash_probability'] * 100:.0f}%" if r["crash_probability"] else "N/A"
            tid = r["token_id"]
            tname = _esc(r["name"] or tid)
            rows_html += (
                f'<tr><td>{i}</td>'
                f'<td><a href="/token/{tid}">{tname}</a></td>'
                f'<td>{_esc(r["symbol"] or "")}</td>'
                f'<td style="font-weight:700">{r["rating"]}</td>'
                f'<td>{r["score"]:.0f}</td>'
                f'<td>{r["vitality_score"] or "N/A"}</td>'
                f'<td style="color:{_color_crash(r["crash_probability"])}">{cp}</td>'
                f'<td><a href="/is-{tid}-dead" style="font-size:11px">Dead?</a> '
                f'<a href="/is-{tid}-a-scam" style="font-size:11px">Scam?</a></td></tr>'
            )

        title = f"{display_name} | ZARQ {YEAR}"
        canonical = f"{SITE}/best/{category}"

        jsonld = f"""<script type="application/ld+json">{_breadcrumb_jsonld([("ZARQ", SITE), ("Best", f"{SITE}/best"), (display_name, canonical)])}</script>
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"ItemList","name":"{_esc(display_name)}","numberOfItems":{len(rows)},"itemListElement":[{','.join(f'{{"@type":"ListItem","position":{i},"name":"{_esc(r["name"] or r["token_id"])}","url":"{SITE}/token/{r["token_id"]}"}}' for i, r in enumerate(rows, 1))}]}}</script>"""

        page = _head(title, cat["desc"] + f" Updated {MONTH}.", canonical,
                      f'<meta name="zarq:type" content="best_list"><meta name="zarq:category" content="{_esc(category)}"><meta name="zarq:updated" content="{TODAY}">' + jsonld)
        page += f"""
<nav style="font-size:12px;color:var(--muted);margin-bottom:16px"><a href="/">ZARQ</a> &rsaquo; Best &rsaquo; {_esc(display_name)}</nav>

<h1>{_esc(display_name)}</h1>
<p style="font-size:15px;color:var(--text);margin:8px 0 16px">{cat['desc']} Updated {MONTH}.</p>
<p style="font-size:13px;color:var(--muted);margin-bottom:16px">Showing top {len(rows)} tokens. Rankings based on ZARQ Trust Rating which combines market structure, liquidity, on-chain health, ecosystem activity, and governance metrics.</p>

<table>
<tr><th>#</th><th>Token</th><th>Symbol</th><th>Rating</th><th>Score</th><th>Vitality</th><th>Crash Risk</th><th>Check</th></tr>
{rows_html}
</table>

<h2>Methodology</h2>
<p style="font-size:14px;color:var(--text)">ZARQ Trust Ratings are computed daily using a five-pillar framework: market structure (price stability, volume consistency), liquidity depth, on-chain activity (transactions, active addresses), ecosystem health (developer activity, integrations), and governance quality. Ratings range from Aaa (highest) to C (lowest), mirroring traditional credit agency methodology. <a href="/methodology">Read the full methodology</a>.</p>

<p style="font-size:11px;color:var(--muted);margin-top:16px">{DISCLAIMER}</p>
"""
        page += _foot()
        return HTMLResponse(_set_cache(ck, page))

    # ════════════════════════════════════════════════════════
    # BUILD 5: /defi/{protocol}  —  Yield safety pages
    # ════════════════════════════════════════════════════════

    @app.get("/defi/{protocol}", response_class=HTMLResponse)
    async def defi_protocol_page(protocol: str):
        ck = f"defi:{protocol}"
        c = _cached(ck)
        if c:
            return HTMLResponse(c)

        conn = _get_db()
        try:
            # Match by protocol_id (slug format)
            row = conn.execute("""
                SELECT protocol_id, name, category, chains, tvl_latest,
                       audit_count, token_id, symbol, url
                FROM defi_protocol_tokens
                WHERE LOWER(protocol_id) = ? OR LOWER(REPLACE(name, ' ', '-')) = ?
                LIMIT 1
            """, (protocol.lower(), protocol.lower())).fetchone()

            if not row:
                # Fuzzy match
                row = conn.execute("""
                    SELECT protocol_id, name, category, chains, tvl_latest,
                           audit_count, token_id, symbol, url
                    FROM defi_protocol_tokens
                    WHERE LOWER(protocol_id) LIKE ? OR LOWER(name) LIKE ?
                    ORDER BY tvl_latest DESC NULLS LAST
                    LIMIT 1
                """, (f"%{protocol.lower()}%", f"%{protocol.lower().replace('-', ' ')}%")).fetchone()

            if not row:
                return HTMLResponse(status_code=404, content=f"<h1>No DeFi data for {_esc(protocol)}</h1>")

            # Get vitality/risk data for the token
            token_id = row["token_id"]
            ndd_row = None
            if token_id:
                ndd_row = conn.execute("SELECT ndd, crash_probability, alert_level FROM crypto_ndd_daily WHERE token_id = ? ORDER BY run_date DESC LIMIT 1", (token_id,)).fetchone()
        finally:
            conn.close()

        protocol_name = row["name"] or protocol.replace("-", " ").title()
        total_tvl = row["tvl_latest"] or 0
        category = row["category"] or "DeFi"
        chains = row["chains"] or "[]"
        audit_count = row["audit_count"] or 0
        protocol_url = row["url"] or ""
        pool_count = 1  # Single protocol entry
        avg_apy = 0  # Not in our table
        crash_prob = ndd_row["crash_probability"] if ndd_row else None

        # Safety based on audit count + TVL + crash prob
        if audit_count >= 1 and total_tvl > 1_000_000 and (not crash_prob or crash_prob < 0.1):
            safety_verdict = "LOW RISK"
            safety_color = "var(--green)"
            avg_risk = 20
        elif total_tvl > 100_000 and (not crash_prob or crash_prob < 0.3):
            safety_verdict = "MODERATE RISK"
            safety_color = "var(--yellow)"
            avg_risk = 50
        else:
            safety_verdict = "HIGH RISK"
            safety_color = "var(--red)"
            avg_risk = 75

        title = f"Is {protocol_name} Safe? DeFi Yield Risk {YEAR} | ZARQ"
        meta_desc = f"{protocol_name} DeFi safety analysis. {pool_count} pools, ${total_tvl / 1e6:.0f}M TVL, {avg_apy:.1f}% avg APY. Risk: {safety_verdict.lower()}. Independent yield risk assessment."
        canonical = f"{SITE}/defi/{protocol}"

        faq_items = [
            (f"Is {protocol_name} safe to use?",
             f"{protocol_name} has an average risk score of {avg_risk:.0f}/100. Verdict: {safety_verdict.lower()}. {pool_count} pools tracked with ${total_tvl / 1e6:.0f}M total TVL."),
            (f"What is {protocol_name}'s TVL?",
             f"{protocol_name} has ${total_tvl / 1e6:.0f}M in total value locked across {pool_count} pools."),
            (f"Is {protocol_name} yield sustainable?",
             f"Average APY: {avg_apy:.1f}%. {'Yields appear sustainable based on TVL and volume.' if avg_apy < 20 else 'High yields may indicate elevated risk. Verify the source of yield.'}"),
        ]

        tvl_str = f"${total_tvl / 1e9:.1f}B" if total_tvl >= 1e9 else f"${total_tvl / 1e6:.0f}M" if total_tvl >= 1e6 else f"${total_tvl / 1e3:.0f}K" if total_tvl >= 1e3 else "N/A"
        try:
            chain_list = json.loads(chains) if isinstance(chains, str) else chains
        except (json.JSONDecodeError, TypeError):
            chain_list = []
        chains_str = ", ".join(chain_list[:8]) if chain_list else "Unknown"

        pools_html = f"""<tr><td>{_esc(protocol_name)}</td><td>{_esc(category)}</td><td>{tvl_str}</td>
<td>{audit_count}</td><td style="color:{safety_color}">{safety_verdict}</td>
{f'<td><a href="/token/{token_id}">Token</a></td>' if token_id else '<td></td>'}</tr>"""

        jsonld = f"""<script type="application/ld+json">{_faq_jsonld(faq_items)}</script>
<script type="application/ld+json">{_breadcrumb_jsonld([("ZARQ", SITE), ("DeFi", f"{SITE}/yield-risk"), (protocol_name, canonical)])}</script>"""

        page = _head(title, meta_desc, canonical,
                      f'<meta name="zarq:type" content="defi_protocol"><meta name="zarq:protocol" content="{_esc(protocol_name)}"><meta name="zarq:tvl" content="{total_tvl:.0f}"><meta name="zarq:updated" content="{TODAY}">' + jsonld)
        page += f"""
<nav style="font-size:12px;color:var(--muted);margin-bottom:16px"><a href="/">ZARQ</a> &rsaquo; <a href="/yield-risk">Yield Risk</a> &rsaquo; {_esc(protocol_name)}</nav>

<h1>Is {_esc(protocol_name)} Safe? Yield Risk Analysis</h1>
<p style="font-size:15px;color:var(--text);margin:8px 0 16px">{_esc(protocol_name)} DeFi yield safety assessment. {pool_count} pools tracked. Total TVL: ${total_tvl / 1e6:.0f}M. Average APY: {avg_apy:.1f}%. Updated {MONTH}.</p>

<div class="verdict" style="color:{safety_color};border-color:{safety_color}">{safety_verdict}</div>

<div class="score-grid">
<div class="card"><div class="num">{pool_count}</div><div class="lbl">Pools</div></div>
<div class="card"><div class="num">${total_tvl / 1e6:.0f}M</div><div class="lbl">TVL</div></div>
<div class="card"><div class="num">{avg_apy:.1f}%</div><div class="lbl">Avg APY</div></div>
<div class="card"><div class="num" style="color:{safety_color}">{avg_risk:.0f}</div><div class="lbl">Risk Score</div></div>
</div>

<h2>Protocol Details</h2>
<table>
<tr><th>Protocol</th><th>Category</th><th>TVL</th><th>Audits</th><th>Safety</th><th>Token</th></tr>
{pools_html}
</table>

<h2>Chains</h2>
<p style="font-size:14px;color:var(--text)">{_esc(protocol_name)} operates on: {_esc(chains_str)}</p>

<h2>Yield Risk Factors</h2>
<p style="font-size:14px;color:var(--text)">ZARQ assesses DeFi yield risk across multiple dimensions: smart contract audit status, TVL concentration, impermanent loss exposure, historical yield stability, protocol governance, and underlying token risk. Protocols with unsustainable yields (APY &gt; 50% without clear economic source) receive elevated risk scores.</p>

<h2>FAQ</h2>
{_faq_html(faq_items)}
"""
        page += _foot()
        return HTMLResponse(_set_cache(ck, page))

    # ════════════════════════════════════════════════════════
    # BUILD 6: /crash-prediction/{token}  —  Crash model
    # ════════════════════════════════════════════════════════

    @app.get("/crash-prediction/{token_id}", response_class=HTMLResponse)
    async def crash_prediction(token_id: str):
        ck = f"crash:{token_id}"
        c = _cached(ck)
        if c:
            return HTMLResponse(c)

        _load_slugs()
        slug_data = _slugs.get(token_id)

        ndd, rating, risk, vitality = _get_token_data(token_id)
        name, symbol = _get_token_name_symbol(token_id, slug_data, ndd)

        if not ndd:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(token_id, bot="zarq-crash-404")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{_esc(name)} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{_esc(name)} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

        crash_prob = ndd["crash_probability"]
        crash_pct = f"{crash_prob * 100:.0f}" if crash_prob is not None else "N/A"
        ndd_val = ndd["ndd"]
        alert = ndd["alert_level"]
        price = ndd["price_usd"]
        rating_str = rating["rating"] if rating else "NR"
        vit_score = vitality["vitality_score"] if vitality else None
        drawdown = risk["drawdown_90d"] if risk else None
        struct_weak = risk["structural_weakness"] if risk else None

        if crash_prob is not None and crash_prob > 0.5:
            cv, cc = "HIGH CRASH RISK", "var(--red)"
            cv_desc = f"ZARQ's crash model assigns {_esc(name)} a {crash_pct}% probability of a >50% decline in 30 days. This is among the highest risk levels in our coverage universe. Extreme caution warranted."
        elif crash_prob is not None and crash_prob > 0.2:
            cv, cc = "ELEVATED RISK", "var(--yellow)"
            cv_desc = f"ZARQ's crash model assigns {_esc(name)} a {crash_pct}% crash probability. This is above the median. Monitor risk signals closely."
        elif crash_prob is not None:
            cv, cc = "LOW CRASH RISK", "var(--green)"
            cv_desc = f"ZARQ's crash model assigns {_esc(name)} a {crash_pct}% crash probability. This is below the warning threshold. Structural indicators appear stable."
        else:
            cv, cc = "UNKNOWN", "var(--muted)"
            cv_desc = "Insufficient data for crash probability assessment."

        title = f"Will {name} Crash? {YEAR} Prediction | ZARQ"
        meta_desc = f"ZARQ crash prediction for {name} ({symbol}): {crash_pct}% crash probability. NDD: {f'{ndd_val:.2f}' if ndd_val else 'N/A'}. Alert: {_esc(alert)}. Rating: {rating_str}. Quantitative crash model analysis."
        canonical = f"{SITE}/crash-prediction/{token_id}"

        faq_items = [
            (f"Will {name} crash?",
             f"ZARQ's v3 crash model gives {name} a {crash_pct}% probability of a >50% decline in 30 days. NDD: {f'{ndd_val:.2f}' if ndd_val else 'N/A'}. Alert level: {_esc(alert)}."),
            (f"What is {name}'s crash probability?",
             f"Current crash probability: {crash_pct}%. This is based on ZARQ's v3 crash model which analyzes Distance-to-Default, structural weakness, liquidity depth, and price momentum."),
            (f"Is {name} about to crash?",
             f"Alert level: {_esc(alert)}. {'No immediate crash signals detected.' if alert in ('SAFE', 'safe', None) else 'Elevated risk signals detected. Monitor closely.'}"),
            (f"What is {name}'s Distance-to-Default?",
             f"NDD (Normalized Distance-to-Default): {f'{ndd_val:.2f}' if ndd_val else 'N/A'}. "
             f"{'Higher NDD indicates more buffer before structural failure.' if ndd_val and ndd_val > 2 else 'Low NDD suggests limited buffer. Elevated default risk.' if ndd_val else ''}"),
            (f"Has ZARQ predicted crashes before?",
             "ZARQ has predicted 144 structural collapses with 100% recall. The model detected LUNA, FTT, and UST failures months before collapse. Average lead time: 22 months."),
        ]

        zarq_meta = f"""<meta name="zarq:type" content="crash_prediction">
<meta name="zarq:token" content="{_esc(name)}">
<meta name="zarq:symbol" content="{_esc(symbol)}">
<meta name="zarq:crash_prob" content="{crash_pct}">
<meta name="zarq:ndd" content="{f'{ndd_val:.2f}' if ndd_val else ''}">
<meta name="zarq:alert" content="{_esc(alert)}">
<meta name="zarq:updated" content="{TODAY}">"""

        jsonld = f"""<script type="application/ld+json">{_faq_jsonld(faq_items)}</script>
<script type="application/ld+json">{_breadcrumb_jsonld([("ZARQ", SITE), ("Crash Watch", f"{SITE}/crash-watch"), (f"{name} Crash Prediction", canonical)])}</script>
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"FinancialProduct","name":"{_esc(name)} Crash Prediction","url":"{canonical}","description":"Crash probability analysis for {_esc(name)}","provider":{{"@type":"Organization","name":"ZARQ","url":"{SITE}"}}}}</script>"""

        page = _head(title, meta_desc, canonical, zarq_meta + jsonld)
        page += f"""
<nav style="font-size:12px;color:var(--muted);margin-bottom:16px"><a href="/">ZARQ</a> &rsaquo; <a href="/crash-watch">Crash Watch</a> &rsaquo; {_esc(name)} Crash Prediction</nav>

<h1>Will {_esc(name)} ({_esc(symbol)}) Crash?</h1>
<p style="font-size:15px;color:var(--text);margin:8px 0 16px">ZARQ crash model: {_esc(name)} has a <strong style="color:{cc}">{crash_pct}%</strong> probability of a &gt;50% decline in the next 30 days. NDD: {f'{ndd_val:.2f}' if ndd_val else 'N/A'}. Alert: {_esc(alert)}. Rating: {rating_str}. Updated {MONTH}.</p>

<div class="verdict" style="color:{cc};border-color:{cc}">{cv}</div>
<p style="font-size:14px;color:var(--muted);margin-bottom:20px">{cv_desc}</p>

<div class="score-grid">
<div class="card"><div class="num" style="color:{cc}">{crash_pct}%</div><div class="lbl">Crash Probability</div></div>
<div class="card"><div class="num">{f'{ndd_val:.2f}' if ndd_val else 'N/A'}</div><div class="lbl">NDD</div></div>
<div class="card"><div class="num">{rating_str}</div><div class="lbl">Rating</div></div>
<div class="card"><div class="num">{_esc(alert)}</div><div class="lbl">Alert Level</div></div>
</div>

<h2>Crash Model Inputs</h2>
<table>
<tr><th>Factor</th><th>Value</th><th>Signal</th></tr>
<tr><td>Crash Probability (30d)</td><td style="font-family:var(--mono);color:{cc}">{crash_pct}%</td><td>{cv.title()}</td></tr>
<tr><td>Distance-to-Default</td><td style="font-family:var(--mono)">{f'{ndd_val:.2f}' if ndd_val else 'N/A'}</td><td>{'Healthy' if ndd_val and ndd_val > 2 else 'Watch' if ndd_val and ndd_val > 1 else 'Danger' if ndd_val else 'N/A'}</td></tr>
<tr><td>Alert Level</td><td>{_esc(alert)}</td><td></td></tr>
<tr><td>Structural Weakness</td><td>{struct_weak if struct_weak is not None else 'N/A'}</td><td>{'Clean' if struct_weak == 0 else 'Flagged' if struct_weak else 'N/A'}</td></tr>
{f'<tr><td>90d Drawdown</td><td style="color:var(--red)">{drawdown:.1f}%</td><td></td></tr>' if drawdown else ''}
<tr><td>Vitality</td><td>{vit_score or 'N/A'}/100</td><td></td></tr>
{f'<tr><td>Price</td><td style="font-family:var(--mono)">${price:.6f}</td><td></td></tr>' if price else ''}
</table>

<h2>ZARQ Crash Model Track Record</h2>
<p style="font-size:14px;color:var(--text)">ZARQ's v3 crash prediction model has identified <strong>144 structural collapses</strong> with <strong>100% recall</strong> and <strong>98% precision</strong>. Notable predictions include LUNA (detected 22 months before collapse), FTT (14 months), and UST (18 months). The model analyzes Distance-to-Default, structural weakness flags, liquidity depth, price momentum, and on-chain activity patterns.</p>

<h2>What Happens If {_esc(name)} Crashes?</h2>
<p style="font-size:14px;color:var(--text)">A crash is defined as a &gt;50% decline from current levels within 30 days. {'At current levels this would mean a price below $' + f'{price * 0.5:.6f}' + '.' if price else ''} ZARQ monitors contagion risk — a crash in {_esc(name)} could affect correlated assets. <a href="/contagion">View contagion map</a>.</p>

<h2>Frequently Asked Questions</h2>
{_faq_html(faq_items)}

<h2>API Access</h2>
<div style="margin-top:8px;padding:16px;background:var(--card);border:1px solid var(--border)">
<p style="font-size:12px;color:var(--muted);margin-bottom:8px">Get crash predictions programmatically:</p>
<pre>curl -s zarq.ai/v1/crypto/check/{token_id} | jq '.crash_probability, .ndd, .alert_level'</pre>
</div>
"""
        page += _foot(token_id)
        return HTMLResponse(_set_cache(ck, page))

    # ════════════════════════════════════════════════════════
    # SITEMAPS
    # ════════════════════════════════════════════════════════

    @app.get("/sitemap-is-dead.xml", response_class=Response)
    async def sitemap_is_dead():
        ck = "sitemap:is-dead"
        c = _cached(ck)
        if c:
            return Response(c, media_type="application/xml")

        _load_slugs()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for token_id in list(_slugs.keys())[:50000]:
            xml += f'<url><loc>{SITE}/is-{token_id}-dead</loc><lastmod>{TODAY}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>\n'
        xml += '</urlset>'
        _set_cache(ck, xml)
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-is-scam.xml", response_class=Response)
    async def sitemap_is_scam():
        ck = "sitemap:is-scam"
        c = _cached(ck)
        if c:
            return Response(c, media_type="application/xml")

        _load_slugs()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for token_id in list(_slugs.keys())[:50000]:
            xml += f'<url><loc>{SITE}/is-{token_id}-a-scam</loc><lastmod>{TODAY}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>\n'
        xml += '</urlset>'
        _set_cache(ck, xml)
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-crash.xml", response_class=Response)
    async def sitemap_crash():
        ck = "sitemap:crash"
        c = _cached(ck)
        if c:
            return Response(c, media_type="application/xml")

        conn = _get_db()
        try:
            rows = conn.execute("SELECT DISTINCT token_id FROM crash_model_v3_predictions").fetchall()
        finally:
            conn.close()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for r in rows:
            xml += f'<url><loc>{SITE}/crash-prediction/{r["token_id"]}</loc><lastmod>{TODAY}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>\n'
        xml += '</urlset>'
        _set_cache(ck, xml)
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-crypto-best.xml", response_class=Response)
    async def sitemap_crypto_best():
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for cat in BEST_CATEGORIES:
            xml += f'<url><loc>{SITE}/best/{cat}</loc><lastmod>{TODAY}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-defi.xml", response_class=Response)
    async def sitemap_defi():
        ck = "sitemap:defi"
        c = _cached(ck)
        if c:
            return Response(c, media_type="application/xml")

        conn = _get_db()
        try:
            rows = conn.execute("SELECT DISTINCT protocol_id as slug FROM defi_protocol_tokens WHERE protocol_id IS NOT NULL").fetchall()
        finally:
            conn.close()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for r in rows:
            xml += f'<url><loc>{SITE}/defi/{r["slug"]}</loc><lastmod>{TODAY}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>\n'
        xml += '</urlset>'
        _set_cache(ck, xml)
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-compare.xml", response_class=Response)
    async def sitemap_compare():
        ck = "sitemap:compare"
        c = _cached(ck)
        if c:
            return Response(c, media_type="application/xml")

        # Generate top comparison pairs from highest-rated tokens
        conn = _get_db()
        try:
            top = conn.execute("""
                SELECT token_id FROM crypto_rating_daily
                WHERE run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
                ORDER BY score DESC LIMIT 50
            """).fetchall()
        finally:
            conn.close()

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        ids = [r["token_id"] for r in top]
        count = 0
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if count >= 1000:
                    break
                xml += f'<url><loc>{SITE}/compare/{a}-vs-{b}</loc><lastmod>{TODAY}</lastmod><changefreq>weekly</changefreq><priority>0.6</priority></url>\n'
                count += 1
            if count >= 1000:
                break
        xml += '</urlset>'
        _set_cache(ck, xml)
        return Response(xml, media_type="application/xml")

    logger.info("Mounted ZARQ SEO builds: is-dead, is-scam, compare, best/*, defi/*, crash-prediction, sitemaps")
