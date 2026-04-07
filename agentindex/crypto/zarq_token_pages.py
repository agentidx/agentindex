"""
ZARQ Token SEO Pages
====================
Individual token pages at /token/{slug} and hub page at /tokens.
Designed to capture "is [token] safe" / "[token] risk rating" search traffic.

Usage in discovery.py:
    from agentindex.crypto.zarq_token_pages import mount_token_pages
    mount_token_pages(app)
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import date
from fastapi.responses import HTMLResponse, Response

logger = logging.getLogger("zarq.token_pages")

try:
    from agentindex.crypto.mica_mapping import get_mica_category, get_mica_badge_html
except ImportError:
    def get_mica_category(token_id, category=None):
        return "Utility Token / Crypto-Asset"
    def get_mica_badge_html(token_id, category=None):
        return ""

try:
    from agentindex.crypto.token_risk_tiers import score_to_grade, grade_color
except ImportError:
    def score_to_grade(s):
        return "NR" if s is None else ("A" if s >= 70 else "B" if s >= 40 else "C")
    def grade_color(g):
        return "#16a34a" if g.startswith("A") else "#ca8a04" if g.startswith("B") else "#dc2626"

try:
    from agentindex.crypto.vitality_score import get_vitality_for_token, vitality_grade, vitality_color
except ImportError:
    def get_vitality_for_token(token_id):
        return None
    def vitality_grade(s):
        return "N/A"
    def vitality_color(g):
        return "#a8a29e"

DB_PATH = str(Path(__file__).parent / "crypto_trust.db")
TEMPLATE_DIR = Path(__file__).parent / "templates"
SLUGS_PATH = Path(__file__).parent / "token_slugs.json"

# Staged rollout: which tiers are enabled for individual pages
ENABLED_TIERS = {"T1", "T2", "T4"}  # T3, T5 added later

_SECURITY_CHECK_JS = """<script>
async function runSecurityCheck(){var btn=document.querySelector('.security-check-btn');var cta=document.querySelector('.security-check-cta');btn.textContent='Checking...';btn.disabled=true;if(localStorage.getItem('ck_ok')){navigator.sendBeacon('/v1/event',JSON.stringify({event:'security_check_click',path:location.pathname}));}try{var r=await fetch('/my/check');var h=await r.text();cta.innerHTML=h;if(localStorage.getItem('ck_ok')){var m=h.match(/(\\d+)\\/100/);navigator.sendBeacon('/v1/event',JSON.stringify({event:'security_check_complete',path:location.pathname,score:m?parseInt(m[1]):null}));}}catch(e){btn.textContent='Get my score \\u2192';btn.disabled=false;}}
if(localStorage.getItem('ck_ok')&&document.querySelector('.security-check-cta')){navigator.sendBeacon('/v1/event',JSON.stringify({event:'cta_impression',path:location.pathname}));}
</script>"""

# Load slug mapping once
_slug_map = {}    # token_id -> {symbol, name, tier, risk_grade}
_slug_ids = set() # all known token_ids

def _load_slugs():
    global _slug_map, _slug_ids
    if _slug_map:
        return
    try:
        with open(SLUGS_PATH) as f:
            data = json.load(f)
        # New format: {token_id: {symbol, name, tier, risk_grade}}
        if isinstance(data, dict) and not any("slug" in v for v in list(data.values())[:3] if isinstance(v, dict)):
            _slug_map = data
            _slug_ids = set(data.keys())
        else:
            # Legacy format: [{slug, token_id, symbol, name}]
            for t in data:
                tid = t.get("token_id", t.get("slug"))
                _slug_map[tid] = {
                    "symbol": t.get("symbol"),
                    "name": t.get("name"),
                    "tier": "T1",
                    "risk_grade": "NR",
                }
            _slug_ids = set(_slug_map.keys())
    except Exception as e:
        logger.error(f"Failed to load token slugs: {e}")


def _esc(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _rating_color(rating):
    if not rating:
        return "#78716c"
    r = rating.lower()
    if r.startswith("aa"):
        return "#16a34a"
    if r.startswith("a"):
        return "#16a34a"
    if r.startswith("baa"):
        return "#ca8a04"
    if r.startswith("ba"):
        return "#ea580c"
    if r.startswith("b"):
        return "#ea580c"
    if r.startswith("ca") or r.startswith("c"):
        return "#dc2626"
    return "#78716c"


def _alert_color(level):
    m = {"SAFE": "#16a34a", "WATCH": "#ca8a04", "WARNING": "#ea580c", "CRITICAL": "#dc2626"}
    return m.get(level, "#78716c")


def _status_class(level):
    m = {"SAFE": "status-safe", "WATCH": "status-watch", "WARNING": "status-warning", "CRITICAL": "status-critical"}
    return m.get(level, "")


def _fmt_price(val):
    if val is None:
        return "N/A"
    if val >= 1:
        return f"${val:,.2f}"
    if val >= 0.01:
        return f"${val:.4f}"
    return f"${val:.6f}"


def _fmt_score(val):
    if val is None:
        return "N/A"
    return f"{val:.1f}"


def _ndd_description(ndd):
    if ndd is None:
        return "No NDD data available"
    if ndd >= 4.0:
        return "Very strong — far from distress threshold"
    if ndd >= 3.0:
        return "Healthy — comfortable distance from default"
    if ndd >= 2.0:
        return "Moderate — some structural pressure"
    if ndd >= 1.0:
        return "Elevated risk — approaching distress"
    return "Critical — near or below default threshold"


def _risk_summary(rating, crash_pct, alert_level, structural_weakness):
    """Generate human-readable risk summary for FAQ answers."""
    if not rating:
        return "insufficient data", "unknown", "insufficient data"

    score_desc = ""
    if rating.startswith("Aa"):
        score_desc = "one of the highest-rated tokens, indicating very low risk"
    elif rating.startswith("A"):
        score_desc = "a high-quality rating, indicating low to moderate risk"
    elif rating.startswith("Baa"):
        score_desc = "an investment-grade rating at the lower end, indicating moderate risk"
    elif rating.startswith("Ba"):
        score_desc = "a speculative-grade rating, indicating elevated risk"
    else:
        score_desc = "a lower rating, indicating significant risk"

    crash_desc = ""
    cp = float(crash_pct) if crash_pct else 0
    if cp < 5:
        crash_desc = f"very low crash probability at {crash_pct}%"
    elif cp < 15:
        crash_desc = f"moderate crash probability at {crash_pct}%"
    elif cp < 30:
        crash_desc = f"elevated crash probability at {crash_pct}%"
    else:
        crash_desc = f"high crash probability at {crash_pct}%"

    struct_desc = ""
    sw = structural_weakness or 0
    if sw >= 3:
        struct_desc = "Multiple structural weaknesses have been detected, indicating potential for significant decline."
    elif sw >= 2:
        struct_desc = "Some structural stress signals are present."
    elif sw >= 1:
        struct_desc = "Minor structural concerns are noted."
    else:
        struct_desc = "No structural weaknesses detected."

    return score_desc, crash_desc, struct_desc


def _best_pillar(rating_row):
    """Return name of highest-scoring pillar."""
    pillars = [
        (rating_row["pillar_1"], "ecosystem strength"),
        (rating_row["pillar_2"], "contagion risk"),
        (rating_row["pillar_3"], "historical resilience"),
        (rating_row["pillar_4"], "fundamental quality"),
        (rating_row["pillar_5"], "rug pull risk"),
    ]
    valid = [(v or 0, n) for v, n in pillars]
    return max(valid, key=lambda x: x[0])[1]


def _weakest_pillar(rating_row):
    """Return name of lowest-scoring pillar."""
    pillars = [
        (rating_row["pillar_1"], "ecosystem strength"),
        (rating_row["pillar_2"], "contagion risk"),
        (rating_row["pillar_3"], "historical resilience"),
        (rating_row["pillar_4"], "fundamental quality"),
        (rating_row["pillar_5"], "rug pull risk"),
    ]
    valid = [(v or 0, n) for v, n in pillars]
    return min(valid, key=lambda x: x[0])[1]


def _get_token_data(token_id):
    """Fetch all data for a token in one connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rating = conn.execute("""
        SELECT r.token_id, r.symbol, r.name, r.rating, r.score,
               r.pillar_1, r.pillar_2, r.pillar_3, r.pillar_4, r.pillar_5,
               r.price_usd, r.price_change_24h, r.price_change_7d, r.run_date
        FROM crypto_rating_daily r
        WHERE r.token_id = ?
        ORDER BY r.run_date DESC LIMIT 1
    """, (token_id,)).fetchone()

    ndd = conn.execute("""
        SELECT n.ndd, n.crash_probability, n.alert_level, n.price_usd, n.symbol, n.name
        FROM crypto_ndd_daily n
        WHERE n.token_id = ?
        ORDER BY n.run_date DESC LIMIT 1
    """, (token_id,)).fetchone()

    risk = conn.execute("""
        SELECT s.risk_level, s.structural_weakness, s.trust_score, s.ndd_current,
               s.sig6_structure, s.trust_p3, s.drawdown_90d
        FROM nerq_risk_signals s
        WHERE s.token_id = ?
        ORDER BY s.signal_date DESC LIMIT 1
    """, (token_id,)).fetchone()

    # Get defi protocol category for MiCA classification
    defi_cat = conn.execute("""
        SELECT category FROM defi_protocol_tokens
        WHERE token_id = ? LIMIT 1
    """, (token_id,)).fetchone()
    defi_category = defi_cat["category"] if defi_cat else None

    # Get similar tokens (same rating category) for compare section
    similar = []
    if rating:
        similar = conn.execute("""
            SELECT r.token_id, r.rating, r.score, n.symbol, n.name
            FROM crypto_rating_daily r
            LEFT JOIN crypto_ndd_daily n ON r.token_id = n.token_id
                AND n.run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)
            WHERE r.run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
              AND r.rating = ?
              AND r.token_id != ?
            ORDER BY ABS(r.score - ?) ASC
            LIMIT 5
        """, (rating["rating"], token_id, rating["score"])).fetchall()

    conn.close()
    return rating, ndd, risk, similar, defi_category


def _risk_level_color(level):
    """Color for risk level badges."""
    m = {"SAFE": "#00d4aa", "WATCH": "#f59e0b", "WARNING": "#f97316", "CRITICAL": "#ef4444"}
    return m.get(level, "#78716c")


def _risk_level_description(level):
    """Human-readable description for risk level."""
    m = {
        "SAFE": "No significant risk signals detected. The token shows healthy structural integrity.",
        "WATCH": "Minor risk signals present. The token is being monitored for emerging stress.",
        "WARNING": "Elevated risk signals detected. Structural stress is building and warrants caution.",
        "CRITICAL": "Severe risk signals active. The token shows critical structural weakness and elevated collapse risk.",
    }
    return m.get(level, "Risk level could not be determined.")


# ── Shared helpers for FIX 2 + FIX 3 (all tiers) ────────────────────────

def _build_pros_cons(ri):
    """Build data-driven pros and cons lists from risk_info dict."""
    pros, cons = [], []
    crash_f = ri.get("crash_prob")
    ndd_v = ri.get("ndd")
    sw = ri.get("structural_weakness", 0)
    alert = ri.get("alert_level", "")
    trust = ri.get("trust_score")
    has_rating = ri.get("has_rating", False)
    crash_pct = ri.get("crash_pct", "N/A")

    # Crash probability
    if crash_f is not None:
        if crash_f < 0.10:
            pros.append(f"Low crash probability ({crash_pct}%)")
        elif crash_f < 0.20:
            pros.append(f"Moderate crash probability ({crash_pct}%)")
        elif crash_f < 0.35:
            cons.append(f"Elevated crash probability ({crash_pct}%)")
        else:
            cons.append(f"High crash probability ({crash_pct}%)")

    # NDD
    if ndd_v is not None:
        if ndd_v >= 3.5:
            pros.append(f"Strong distance from default (NDD: {ndd_v:.1f})")
        elif ndd_v >= 2.0:
            pros.append(f"Healthy distance from default (NDD: {ndd_v:.1f})")
        elif ndd_v >= 1.0:
            cons.append(f"Approaching distress threshold (NDD: {ndd_v:.1f})")
        else:
            cons.append(f"Near or below default threshold (NDD: {ndd_v:.1f})")

    # Structural weakness
    if sw == 0:
        pros.append("No structural collapse signals detected")
    elif sw >= 3:
        cons.append(f"{sw} structural weakness signals active — elevated collapse risk")
    elif sw >= 1:
        cons.append(f"{sw} structural weakness signal{'s' if sw > 1 else ''} active")

    # Alert level
    if alert in ("SAFE",):
        pros.append("No active risk alerts")
    elif alert in ("WARNING", "CRITICAL"):
        cons.append(f"Active risk alert: {alert}")

    # Trust score
    if trust is not None:
        if trust >= 70:
            pros.append(f"High trust score ({trust:.0f}/100)")
        elif trust < 35:
            cons.append(f"Below-average trust score ({trust:.0f}/100)")

    # Rating
    if not has_rating:
        cons.append("Full Moody's-style credit rating pending")

    # Ensure at least 2 of each
    if len(pros) < 2:
        pros.append("Daily automated risk monitoring by ZARQ")
    if len(cons) < 2:
        cons.append("Crypto assets carry inherent volatility risk")

    return pros[:3], cons[:3]


def _pros_cons_html(ri):
    """Generate Pros & Cons section HTML."""
    pros, cons = _build_pros_cons(ri)
    name = _esc(ri["name"])
    pros_html = "".join(
        f'<div style="display:flex;gap:10px;align-items:start;margin-bottom:10px">'
        f'<span style="color:var(--green);font-size:18px;line-height:1">&#10003;</span>'
        f'<span style="font-family:var(--sans);font-size:14px;color:var(--gray-700)">{_esc(p)}</span></div>'
        for p in pros
    )
    cons_html = "".join(
        f'<div style="display:flex;gap:10px;align-items:start;margin-bottom:10px">'
        f'<span style="color:var(--red);font-size:18px;line-height:1">&#10007;</span>'
        f'<span style="font-family:var(--sans);font-size:14px;color:var(--gray-700)">{_esc(c)}</span></div>'
        for c in cons
    )
    return (
        f'<h2 class="section-title">Pros &amp; Cons of {name}</h2>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:48px">'
        f'<div style="background:rgba(22,163,74,0.03);border:1px solid rgba(22,163,74,0.12);padding:20px">'
        f'<div style="font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--green);margin-bottom:16px">Strengths</div>'
        f'{pros_html}</div>'
        f'<div style="background:rgba(220,38,38,0.03);border:1px solid rgba(220,38,38,0.12);padding:20px">'
        f'<div style="font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--red);margin-bottom:16px">Risks</div>'
        f'{cons_html}</div></div>'
    )


def _investment_summary_html(ri):
    """Generate Investment Risk Summary section."""
    name = _esc(ri["name"])
    symbol = _esc(ri["symbol"])
    crash_pct = ri.get("crash_pct", "N/A")
    ndd_str = _fmt_score(ri.get("ndd")) if ri.get("ndd") else "N/A"
    alert = _esc(ri.get("alert_level", "N/A"))
    rating_str = _esc(ri.get("rating", "")) if ri.get("has_rating") else "Pending"

    # Build plain-language summary
    if ri.get("crash_prob") is not None and ri["crash_prob"] < 0.10:
        outlook = f"{name} shows relatively low crash risk with a {crash_pct}% probability of a major drawdown."
    elif ri.get("crash_prob") is not None and ri["crash_prob"] < 0.25:
        outlook = f"{name} carries moderate crash risk at {crash_pct}%, typical for mid-cap crypto assets."
    elif ri.get("crash_prob") is not None:
        outlook = f"{name} has an elevated crash probability of {crash_pct}%, warranting extra caution."
    else:
        outlook = f"Crash probability data for {name} is not yet available."

    sw = ri.get("structural_weakness", 0)
    if sw >= 3:
        struct_note = f" Multiple structural weakness signals ({sw}) are active, indicating potential for significant decline."
    elif sw >= 1:
        struct_note = f" Minor structural stress has been detected ({sw} signal{'s' if sw > 1 else ''})."
    else:
        struct_note = " No structural weaknesses have been detected."

    # Vitality crash resistance note
    tid = ri.get("token_id", "")
    vd_inv = _get_vitality_data(tid) if tid else {"score": "N/A"}
    vitality_note_inv = ""
    if vd_inv["score"] != "N/A":
        vs = float(vd_inv["score"])
        if vs >= 52.5:  # top quintile threshold from backtest
            vitality_note_inv = (
                f' This token scored in the top quintile for crash resistance based on backtested Vitality Score '
                f'({vd_inv["score"]}, Grade {vd_inv["grade"]}). '
                f'<a href="/vitality/backtest" style="color:var(--warm)">Backtest results</a>'
            )
        else:
            vitality_note_inv = (
                f' Vitality Score: {vd_inv["score"]}/100 (Grade {vd_inv["grade"]}). '
                f'<a href="/vitality/backtest" style="color:var(--warm)">Backtest results</a>'
            )

    return (
        f'<h2 class="section-title">Investment Risk Summary</h2>'
        f'<div style="background:var(--gray-100);border:1px solid var(--gray-200);padding:24px 28px;margin-bottom:48px">'
        f'<div style="font-family:var(--sans);font-size:15px;color:var(--gray-700);line-height:1.7;margin-bottom:16px">'
        f'{outlook}{struct_note}'
        f' The Distance-to-Default stands at {ndd_str}, with an alert level of {alert}.'
        f' Rating: {rating_str}.{vitality_note_inv}</div>'
        f'<div style="font-family:var(--mono);font-size:12px;color:var(--gray-500);border-top:1px solid var(--gray-200);padding-top:12px">'
        f'<strong>Disclaimer:</strong> This is quantitative risk analysis, not investment advice. '
        f'Crypto assets are volatile and can lose value rapidly. Never invest more than you can afford to lose. '
        f'ZARQ provides independent risk data — always do your own research before making investment decisions.'
        f'</div></div>'
    )


def _internal_links_html(token_id, name):
    """Generate internal links section at bottom of token page."""
    _load_slugs()
    # Find 5 related tokens (next in alphabetical order for simplicity)
    all_ids = sorted(_slug_ids)
    try:
        idx = all_ids.index(token_id)
    except ValueError:
        idx = 0
    # Pick 5 nearby tokens, wrapping around
    related = []
    for offset in [1, 2, 3, -1, -2]:
        i = (idx + offset) % len(all_ids)
        rid = all_ids[i]
        if rid != token_id:
            rinfo = _slug_map.get(rid, {})
            rname = rinfo.get("name") or rid.replace("-", " ").title()
            tier = rinfo.get("tier", "T1")
            if tier in ENABLED_TIERS:
                related.append((rid, rname))
        if len(related) >= 5:
            break

    links = "".join(
        f'<a href="/token/{_esc(rid)}" style="font-family:var(--mono);font-size:13px;color:var(--warm);'
        f'text-decoration:none;border:1px solid var(--gray-200);padding:10px 16px;display:inline-block">'
        f'{_esc(rn)}</a>'
        for rid, rn in related
    )

    return (
        f'<div style="margin-top:48px">'
        f'<h2 class="section-title">Explore More</h2>'
        f'<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:24px">{links}</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:12px">'
        f'<a href="/vitality" style="font-family:var(--mono);font-size:13px;color:var(--gray-600);text-decoration:none;border:1px solid var(--gray-200);padding:10px 16px">Vitality Rankings</a>'
        f'<a href="/crash-watch" style="font-family:var(--mono);font-size:13px;color:var(--gray-600);text-decoration:none;border:1px solid var(--gray-200);padding:10px 16px">Crash Watch</a>'
        f'<a href="/yield-risk" style="font-family:var(--mono);font-size:13px;color:var(--gray-600);text-decoration:none;border:1px solid var(--gray-200);padding:10px 16px">Yield Risk</a>'
        f'<a href="/scan" style="font-family:var(--mono);font-size:13px;color:var(--gray-600);text-decoration:none;border:1px solid var(--gray-200);padding:10px 16px">Token Scanner</a>'
        f'<a href="/vitality/methodology" style="font-family:var(--mono);font-size:13px;color:var(--gray-600);text-decoration:none;border:1px solid var(--gray-200);padding:10px 16px">Methodology</a>'
        f'<a href="/tokens" style="font-family:var(--mono);font-size:13px;color:var(--gray-600);text-decoration:none;border:1px solid var(--gray-200);padding:10px 16px">All Token Ratings</a>'
        f'</div></div>'
    )


def _extra_faq_answers(ri):
    """Generate FAQ answers for FIX 2 + FIX 3 (questions 4-7)."""
    name = _esc(ri["name"])
    symbol = _esc(ri["symbol"])
    crash_pct = ri.get("crash_pct", "N/A")
    ndd_str = _fmt_score(ri.get("ndd")) if ri.get("ndd") else "N/A"
    alert = _esc(ri.get("alert_level", "N/A"))
    sw = ri.get("structural_weakness", 0)
    trust = ri.get("trust_score")
    trust_str = _fmt_score(trust) if trust else "N/A"
    rating = _esc(ri.get("rating", "")) if ri.get("has_rating") else None
    pros, cons = _build_pros_cons(ri)

    # FAQ 4: Should I invest?
    if ri.get("has_rating") and rating:
        invest_context = f"{name} holds a {rating} rating from ZARQ."
    else:
        invest_context = f"{name} is currently monitored by ZARQ with risk grade {_esc(ri.get('risk_grade', 'NR'))}."

    faq4 = (
        f"{invest_context} "
        f"The crash probability is {crash_pct}% and the Distance-to-Default is {ndd_str}. "
        f"These metrics suggest {'relatively contained' if ri.get('crash_prob') is not None and ri['crash_prob'] < 0.15 else 'notable'} downside risk. "
        f"However, ZARQ provides risk data, not investment advice. All crypto investments carry significant risk, "
        f"including total loss of capital. Consider your risk tolerance, portfolio diversification, and investment horizon. "
        f"Never invest more than you can afford to lose."
    )

    # FAQ 5: Price prediction
    faq5 = (
        f"ZARQ does not make price predictions for {name}. Instead, we provide quantitative risk metrics: "
        f"the crash probability is {crash_pct}% (probability of a &gt;50% drawdown), "
        f"the Distance-to-Default is {ndd_str}, and the alert level is {alert}. "
        f"{'There are ' + str(sw) + ' structural weakness signals active.' if sw > 0 else 'No structural weakness signals are active.'} "
        f"These risk signals are updated daily and can help inform — but not replace — your own analysis."
    )

    # FAQ 6: Is it a scam?
    if sw >= 3:
        scam_data = f"Warning: {sw} structural collapse signals are currently active, indicating elevated risk."
    elif sw >= 1:
        scam_data = f"Minor structural stress detected ({sw} signal{'s' if sw > 1 else ''})."
    else:
        scam_data = "No structural collapse signals detected."

    faq6 = (
        f"ZARQ's analysis of {name} shows "
        f"{'a ' + rating + ' rating' if rating else 'a risk level of ' + alert}. "
        f"{scam_data} "
        f"ZARQ monitors {name} daily across 7 quantitative risk signals including Distance-to-Default, "
        f"crash probability, and structural integrity. While these signals can flag elevated risk, "
        f"they cannot definitively determine if an asset is fraudulent. Always verify the project's team, "
        f"code, and community independently."
    )

    # FAQ 7: Pros and cons
    pros_text = "; ".join(pros)
    cons_text = "; ".join(cons)
    faq7 = (
        f"Based on ZARQ's quantitative analysis, {name} ({symbol}) has the following strengths: {pros_text}. "
        f"Key risks include: {cons_text}. "
        f"These assessments are based on daily-updated risk models and should be considered alongside "
        f"your own research and risk tolerance."
    )

    return faq4, faq5, faq6, faq7


def _extra_faq_html(ri):
    """Generate HTML for FAQ items 4-7."""
    name = _esc(ri["name"])
    faq4, faq5, faq6, faq7 = _extra_faq_answers(ri)
    return (
        f'<div class="faq-item">'
        f'<div class="faq-q">Should I invest in {name}?</div>'
        f'<div class="faq-a">{faq4}</div></div>'
        f'<div class="faq-item">'
        f'<div class="faq-q">{name} price prediction — what does the risk data say?</div>'
        f'<div class="faq-a">{faq5}</div></div>'
        f'<div class="faq-item">'
        f'<div class="faq-q">Is {name} a scam?</div>'
        f'<div class="faq-a">{faq6}</div></div>'
        f'<div class="faq-item">'
        f'<div class="faq-q">What are the pros and cons of {name}?</div>'
        f'<div class="faq-a">{faq7}</div></div>'
    )


def _extra_faq_jsonld(ri):
    """Return list of 4 extra FAQ JSON-LD entries for questions 4-7."""
    name = ri["name"]
    faq4, faq5, faq6, faq7 = _extra_faq_answers(ri)
    return [
        {"@type": "Question", "name": f"Should I invest in {name}?",
         "acceptedAnswer": {"@type": "Answer", "text": faq4}},
        {"@type": "Question", "name": f"{name} price prediction — what does the risk data say?",
         "acceptedAnswer": {"@type": "Answer", "text": faq5.replace("&gt;", ">")}},
        {"@type": "Question", "name": f"Is {name} a scam?",
         "acceptedAnswer": {"@type": "Answer", "text": faq6}},
        {"@type": "Question", "name": f"What are the pros and cons of {name}?",
         "acceptedAnswer": {"@type": "Answer", "text": faq7}},
    ]


def _build_risk_info(name, symbol, slug, token_id, tier, **kwargs):
    """Build standardized risk_info dict for shared helpers."""
    return {
        "name": name,
        "symbol": symbol,
        "slug": slug,
        "token_id": token_id,
        "tier": tier,
        "rating": kwargs.get("rating"),
        "risk_grade": kwargs.get("risk_grade", "NR"),
        "risk_level": kwargs.get("risk_level"),
        "alert_level": kwargs.get("alert_level"),
        "trust_score": kwargs.get("trust_score"),
        "risk_score": kwargs.get("risk_score"),
        "ndd": kwargs.get("ndd"),
        "crash_pct": kwargs.get("crash_pct", "N/A"),
        "crash_prob": kwargs.get("crash_prob"),
        "structural_weakness": kwargs.get("structural_weakness", 0),
        "has_rating": kwargs.get("has_rating", False),
    }


def _get_vitality_data(token_id):
    """Load vitality score data for a token. Returns dict or None."""
    v = get_vitality_for_token(token_id)
    if v is None:
        return {"score": "N/A", "grade": "N/A", "color": "#a8a29e",
                "eg": None, "cc": None, "ce": None, "sr": None, "om": None,
                "confidence": 0}
    return {
        "score": f"{v['vitality_score']:.0f}" if v.get("vitality_score") is not None else "N/A",
        "grade": v.get("vitality_grade", "N/A"),
        "color": vitality_color(v.get("vitality_grade", "F")),
        "eg": v.get("ecosystem_gravity"),
        "cc": v.get("capital_commitment"),
        "ce": v.get("coordination_efficiency"),
        "sr": v.get("stress_resilience"),
        "om": v.get("organic_momentum"),
        "confidence": v.get("confidence", 0),
    }


def _vitality_section_html(token_id, name):
    """Generate Vitality Score breakdown section HTML."""
    vd = _get_vitality_data(token_id)
    if vd["score"] == "N/A":
        return "", vd

    dims = [
        ("Ecosystem Gravity", vd["eg"], "Multi-chain presence, protocol count, DeFi depth"),
        ("Capital Commitment", vd["cc"], "TVL stability, locked capital, market cap rank"),
        ("Coordination Efficiency", vd["ce"], "Audit coverage, category diversity, yield density"),
        ("Stress Resilience", vd["sr"], "Drawdown recovery, NDD stability, crash probability"),
        ("Organic Momentum", vd["om"], "Rating trend, NDD trend, volume momentum"),
    ]

    bars = ""
    for label, val, desc in dims:
        if val is None:
            bars += (
                f'<div style="margin-bottom:16px">'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
                f'<span style="font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:0.05em;color:var(--gray-500)">{label}</span>'
                f'<span style="font-family:var(--mono);font-size:12px;color:var(--gray-400)">—</span>'
                f'</div>'
                f'<div style="background:var(--gray-200);height:6px"><div style="background:var(--gray-400);height:6px;width:0%"></div></div>'
                f'<div style="font-size:12px;color:var(--gray-500);margin-top:2px">{desc}</div>'
                f'</div>'
            )
        else:
            v = min(val, 100)
            color = "#16a34a" if v >= 60 else "#ca8a04" if v >= 35 else "#dc2626"
            bars += (
                f'<div style="margin-bottom:16px">'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
                f'<span style="font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:0.05em;color:var(--gray-500)">{label}</span>'
                f'<span style="font-family:var(--mono);font-size:12px;font-weight:600;color:{color}">{v:.0f}</span>'
                f'</div>'
                f'<div style="background:var(--gray-200);height:6px"><div style="background:{color};height:6px;width:{v:.0f}%"></div></div>'
                f'<div style="font-size:12px;color:var(--gray-500);margin-top:2px">{desc}</div>'
                f'</div>'
            )

    html = (
        f'<div style="margin-top:48px;margin-bottom:48px">'
        f'<h2 class="section-title">Vitality Score Breakdown</h2>'
        f'<p style="font-size:14px;color:var(--gray-600);margin-bottom:24px">'
        f'The ZARQ Vitality Score measures ecosystem health and crash resistance across 5 dimensions. '
        f'{_esc(name)} scores <strong>{vd["score"]}</strong>/100 (Grade {vd["grade"]}), '
        f'indicating crash resistance &mdash; backtested high-Vitality tokens lost 44% less during the 2025&ndash;2026 market crash (p&nbsp;&lt;&nbsp;0.001). '
        f'<a href="/vitality/backtest" style="color:var(--warm);font-family:var(--mono);font-size:12px">Backtested&nbsp;&#10003;</a> '
        f'<a href="/vitality/methodology" style="color:var(--warm)">Methodology</a></p>'
        f'{bars}'
        f'<div style="font-family:var(--mono);font-size:11px;color:var(--gray-400);margin-top:8px">'
        f'Data confidence: {vd["confidence"]}%</div>'
        f'</div>'
    )
    return html, vd


def _render_risk_signal_page(slug, token_id, token_info, risk_row, ndd_row):
    """Render a tier (b) token page — risk-signal-only, no full Moody's rating."""
    name = token_info.get("name") or (ndd_row["name"] if ndd_row and ndd_row["name"] else token_id.replace("-", " ").title())
    symbol = token_info.get("symbol") or (ndd_row["symbol"] if ndd_row and ndd_row["symbol"] else token_id.split("-")[0].upper())

    risk_level = risk_row["risk_level"] or "N/A"
    trust_score = risk_row["trust_score"]
    ndd_val = risk_row["ndd_current"]
    sig6 = risk_row["sig6_structure"]
    structural_weakness = risk_row["structural_weakness"] or 0
    trust_p3 = risk_row["trust_p3"]
    drawdown_90d = risk_row["drawdown_90d"]
    signal_date = ""

    # Try to get signal_date from DB
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT signal_date FROM nerq_risk_signals WHERE token_id = ? ORDER BY signal_date DESC LIMIT 1", (token_id,)).fetchone()
        if row:
            signal_date = row[0]
        conn.close()
    except:
        pass

    today = signal_date or date.today().isoformat()
    risk_color = _risk_level_color(risk_level)
    risk_desc = _risk_level_description(risk_level)
    ndd_str = _fmt_score(ndd_val) if ndd_val else "N/A"
    trust_str = _fmt_score(trust_score) if trust_score else "N/A"
    rating_str = "Pending"  # Risk-signal-only tokens don't have a full Moody's rating yet
    dd_sentence = f" Over the past 90 days, {_esc(name)} has experienced a {abs(drawdown_90d)*100:.1f}% maximum drawdown." if drawdown_90d and drawdown_90d < -0.01 else ""

    struct_status = "No structural weaknesses detected." if structural_weakness == 0 else f"{structural_weakness} structural weakness signal{'s' if structural_weakness != 1 else ''} active."

    # Build risk_info for shared helpers
    ri = _build_risk_info(name, symbol, slug, token_id, "T2",
        risk_level=risk_level, alert_level=risk_level, trust_score=trust_score,
        ndd=ndd_val, crash_pct="N/A", crash_prob=None,
        structural_weakness=structural_weakness, has_rating=False, risk_grade=token_info.get("risk_grade", "NR"))

    # Vitality Score
    vitality_html_t2, vd_t2 = _vitality_section_html(token_id, name)

    # AI summary
    vd_ai_t2 = _get_vitality_data(token_id)
    vitality_note_t2 = ""
    if vd_ai_t2["score"] != "N/A":
        vitality_note_t2 = (
            f" Vitality Score: {vd_ai_t2['score']}/100 (Grade {vd_ai_t2['grade']}), indicating crash resistance — "
            f"backtested high-Vitality tokens lost 44% less during the 2025-2026 market crash (p < 0.001)."
        )
    ai_summary = (
        f"Is {_esc(name)} safe? ZARQ monitors {_esc(name)} ({_esc(symbol)}) with a risk score of {trust_str}/100 "
        f"and a risk level of {_esc(risk_level)}. Distance-to-Default: {ndd_str}. "
        f"{struct_status}{vitality_note_t2} Investors searching for {_esc(name)} safety information should note this token "
        f"is monitored daily across 7 quantitative risk signals. Full credit rating pending."
    )

    # FAQ answers for risk-signal-only tokens
    faq_answer_1 = (
        f"{_esc(name)} ({_esc(symbol)}) is currently monitored by ZARQ with a risk status of {_esc(risk_level)}. "
        f"{risk_desc} "
        f"The trust score is {trust_str}/100 and the Distance-to-Default stands at {ndd_str}. "
        f"{struct_status}{dd_sentence} "
        f"A full Moody's-style credit rating is pending. As with all crypto assets, conduct your own research."
    )
    faq_answer_2 = (
        f"{_esc(name)} does not yet have a full Moody's-style credit rating from ZARQ. "
        f"It is currently classified as {_esc(risk_level)} based on quantitative risk signals including "
        f"structural integrity (Sig6: {_fmt_score(sig6)}), Distance-to-Default ({ndd_str}), "
        f"and trust score ({trust_str}/100). "
        f"A full rating across five pillars will be assigned once sufficient data is available."
    )
    faq_answer_3 = (
        f"ZARQ's risk monitoring classifies {_esc(name)} as {_esc(risk_level)}. "
        f"The Distance-to-Default (NDD) is {ndd_str}, which indicates "
        f"{_ndd_description(ndd_val).lower()}. "
        f"There {'are' if structural_weakness != 1 else 'is'} {structural_weakness} structural weakness "
        f"signal{'s' if structural_weakness != 1 else ''} active. "
        f"{struct_status}{dd_sentence} "
        f"These are model-based risk signals updated daily, not guarantees of future performance."
    )

    # JSON-LD
    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Token Ratings", "item": "https://zarq.ai/tokens"},
            {"@type": "ListItem", "position": 3, "name": f"{name} ({symbol})"},
        ]
    })

    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"Is {name} Safe? {risk_level} Risk — ZARQ",
        "description": f"Is {name} safe? ZARQ monitors {name} with a risk score of {trust_str}/100. Risk level: {risk_level}.",
        "url": f"https://zarq.ai/token/{slug}",
        "publisher": {"@type": "Organization", "name": "ZARQ", "url": "https://zarq.ai"},
        "dateModified": today,
    })

    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f"Is {name} safe to invest in?",
                "acceptedAnswer": {"@type": "Answer", "text": faq_answer_1.replace("&gt;", ">")}
            },
            {
                "@type": "Question",
                "name": f"What is {name}'s risk rating?",
                "acceptedAnswer": {"@type": "Answer", "text": faq_answer_2}
            },
            {
                "@type": "Question",
                "name": f"Will {name} crash?",
                "acceptedAnswer": {"@type": "Answer", "text": faq_answer_3.replace("&gt;", ">")}
            },
        ] + _extra_faq_jsonld(ri)
    })

    # Structural warning box
    structural_warning = ""
    if structural_weakness >= 3:
        structural_warning = (
            '<div class="warning-box">'
            '<div class="warn-title">Structural Collapse Warning</div>'
            f'<div class="warn-text">{_esc(name)} has {structural_weakness} structural weakness signals active. '
            'Tokens with 3+ structural weaknesses have historically experienced severe drawdowns.</div>'
            '</div>'
        )
    elif structural_weakness >= 2:
        structural_warning = (
            '<div class="warning-box">'
            '<div class="warn-title">Structural Stress Detected</div>'
            f'<div class="warn-text">{_esc(name)} has {structural_weakness} structural stress signals. '
            'This indicates emerging weakness that may worsen. Monitor closely.</div>'
            '</div>'
        )
    elif structural_weakness == 0 and risk_level == "SAFE":
        structural_warning = (
            '<div class="safe-box">'
            '<div class="safe-title">No Structural Warnings</div>'
            f'<div class="safe-text">{_esc(name)} shows no structural weaknesses. '
            'The Distance-to-Default model indicates healthy structural integrity.</div>'
            '</div>'
        )

    # Pending rating notice
    pending_notice = (
        '<div style="background:rgba(194,149,107,0.08);border:1px solid rgba(194,149,107,0.25);'
        'padding:24px 28px;margin-bottom:48px">'
        '<div style="font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:0.1em;'
        f'color:var(--warm);margin-bottom:8px">Risk Monitoring</div>'
        '<div style="font-family:var(--sans);font-size:14px;color:var(--gray-700)">'
        f'Full credit rating pending for {_esc(name)} — currently monitored for risk signals. '
        'A Moody\'s-style rating (Aaa-D) will be assigned once sufficient historical data and '
        'pillar scores are computed.</div>'
        '</div>'
    )

    # Build the page HTML using the same design system
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Is {_esc(name)} Safe? {_esc(risk_level)} Risk — ZARQ</title>
<meta name="description" content="Is {_esc(name)} safe? ZARQ monitors {_esc(name)} with a risk score of {trust_str}/100 and a risk level of {_esc(risk_level)}. Distance-to-Default: {ndd_str}. Independent risk monitoring.">
<link rel="canonical" href="https://zarq.ai/token/{_esc(slug)}">
<meta property="og:title" content="Is {_esc(name)} Safe? {_esc(risk_level)} Risk — ZARQ">
<meta property="og:description" content="Is {_esc(name)} safe? Risk score {trust_str}/100. {_esc(risk_level)} risk level. Independent risk monitoring by ZARQ.">
<meta property="og:url" content="https://zarq.ai/token/{_esc(slug)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="ZARQ">
<meta name="twitter:card" content="summary">
<meta name="robots" content="index, follow">
<meta name="zarq:trust_score" content="{trust_str}">
<meta name="zarq:risk_level" content="{_esc(risk_level)}">
<meta name="zarq:rating" content="{_esc(rating_str)}">
<meta name="zarq:api" content="https://zarq.ai/v1/crypto/rating/{_esc(slug)}">

<script type="application/ld+json">
{webpage_jsonld}
</script>
<script type="application/ld+json">
{faq_jsonld}
</script>
<script type="application/ld+json">
{breadcrumb_jsonld}
</script>

<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --white: #fafaf9; --black: #0a0a0a;
  --gray-100: #f5f5f4; --gray-200: #e7e5e4; --gray-400: #a8a29e;
  --gray-500: #78716c; --gray-600: #57534e; --gray-700: #44403c;
  --gray-800: #292524; --gray-900: #1c1917;
  --warm: #c2956b; --warm-light: rgba(194, 149, 107, 0.08);
  --green: #16a34a; --red: #dc2626; --yellow: #ca8a04;
  --serif: 'DM Serif Display', Georgia, serif;
  --mono: 'JetBrains Mono', monospace;
  --sans: 'DM Sans', sans-serif;
  --measure: 680px; --wide: 1120px;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
::selection {{ background: var(--warm); color: var(--black); }}
html {{ font-size: 17px; -webkit-font-smoothing: antialiased; }}
body {{ background: var(--white); color: var(--gray-800); font-family: var(--sans); line-height: 1.6; }}
nav {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  padding: 20px 40px; display: flex; justify-content: space-between; align-items: center;
  backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  background: rgba(250, 250, 249, 0.85); border-bottom: 1px solid rgba(0,0,0,0.04);
}}
.nav-mark {{ font-family: var(--mono); font-weight: 500; font-size: 15px; letter-spacing: 0.15em; text-transform: uppercase; color: var(--black); text-decoration: none; }}
.nav-links {{ display: flex; gap: 32px; align-items: center; }}
.nav-links a {{ font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-600); text-decoration: none; transition: color 0.2s; }}
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
.container {{ max-width: var(--wide); margin: 0 auto; padding: 120px 40px 80px; }}
.breadcrumb {{ font-family: var(--mono); font-size: 11px; color: var(--gray-500); margin-bottom: 24px; }}
.breadcrumb a {{ color: var(--warm); text-decoration: none; }}
.breadcrumb a:hover {{ text-decoration: underline; }}
h1 {{ font-family: var(--serif); font-size: 2.4rem; color: var(--black); line-height: 1.2; margin-bottom: 16px; }}
.subtitle {{ font-family: var(--sans); font-size: 1rem; color: var(--gray-600); margin-bottom: 40px; }}
.badge-row {{ display: flex; gap: 16px; align-items: center; margin-bottom: 40px; flex-wrap: wrap; }}
.badge {{ display: inline-flex; align-items: center; gap: 8px; padding: 8px 20px; border: 1px solid var(--gray-200); font-family: var(--mono); font-size: 13px; }}
.badge-rating {{ font-size: 18px; font-weight: 500; }}
.badge-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--gray-500); }}
.score-card {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 48px; }}
.score-item {{ background: var(--gray-100); border: 1px solid var(--gray-200); padding: 24px; }}
.score-item .value {{ font-family: var(--serif); font-size: 32px; color: var(--black); }}
.score-item .label {{ font-family: var(--mono); font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--gray-500); margin-top: 4px; }}
.score-item .detail {{ font-family: var(--sans); font-size: 13px; color: var(--gray-600); margin-top: 8px; }}
.ai-summary {{ background: var(--gray-100); border-left: 3px solid var(--warm); padding: 20px 24px; margin-bottom: 40px; font-family: var(--sans); font-size: 15px; line-height: 1.7; color: var(--gray-700); }}
.section-title {{ font-family: var(--serif); font-size: 1.6rem; color: var(--black); margin-bottom: 24px; margin-top: 48px; }}
.signals-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 48px; }}
.signal-card {{ background: var(--gray-100); border: 1px solid var(--gray-200); padding: 20px; }}
.signal-card .sig-name {{ font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--gray-500); margin-bottom: 6px; }}
.signal-card .sig-value {{ font-family: var(--serif); font-size: 28px; color: var(--black); }}
.signal-card .sig-desc {{ font-family: var(--sans); font-size: 13px; color: var(--gray-600); margin-top: 8px; }}
.warning-box {{ background: rgba(220, 38, 38, 0.04); border: 1px solid rgba(220, 38, 38, 0.15); padding: 24px 28px; margin-bottom: 48px; }}
.warning-box .warn-title {{ font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--red); margin-bottom: 8px; }}
.warning-box .warn-text {{ font-family: var(--sans); font-size: 14px; color: var(--gray-700); }}
.safe-box {{ background: rgba(22, 163, 74, 0.04); border: 1px solid rgba(22, 163, 74, 0.15); padding: 24px 28px; margin-bottom: 48px; }}
.safe-box .safe-title {{ font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--green); margin-bottom: 8px; }}
.safe-box .safe-text {{ font-family: var(--sans); font-size: 14px; color: var(--gray-700); }}
.faq-section {{ margin-top: 48px; margin-bottom: 48px; }}
.faq-item {{ border-bottom: 1px solid var(--gray-200); padding: 24px 0; }}
.faq-item:first-child {{ border-top: 1px solid var(--gray-200); }}
.faq-q {{ font-family: var(--serif); font-size: 1.2rem; color: var(--black); margin-bottom: 12px; }}
.faq-a {{ font-family: var(--sans); font-size: 15px; color: var(--gray-700); line-height: 1.7; }}
footer {{ border-top: 1px solid var(--gray-200); padding: 40px; text-align: center; }}
footer p {{ font-family: var(--mono); font-size: 11px; color: var(--gray-500); }}
footer a {{ color: var(--warm); text-decoration: none; }}
@media (max-width: 768px) {{
  nav {{ padding: 16px 20px; }}
  .nav-hamburger {{ display: flex; }}
  .nav-links {{ display: none; position: absolute; top: 100%; left: 0; right: 0; background: var(--white); border-bottom: 1px solid var(--gray-200); padding: 16px 20px; flex-direction: column; gap: 16px; }}
  .nav-toggle-input:checked ~ .nav-links {{ display: flex; }}
  .nav-dropdown-menu {{ display: block; position: static; box-shadow: none; border: none; padding: 0 0 0 12px; }}
  .nav-dropdown-trigger {{ display: none; }}
  .container {{ padding: 100px 20px 60px; }}
  h1 {{ font-size: 1.8rem; }}
  .signals-grid {{ grid-template-columns: 1fr; }}
  .score-card {{ grid-template-columns: 1fr 1fr; }}
}}
</style>
</head>
<body>
<!-- AI_SUMMARY: {ai_summary} -->
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
  <div class="breadcrumb">
    <a href="/">ZARQ</a> / <a href="/tokens">Token Ratings</a> / {_esc(name)}
  </div>

  <h1>Is {_esc(name)} Safe? — Risk Score: {trust_str}/100</h1>
  <p class="subtitle">Risk monitoring for {_esc(name)} ({_esc(symbol)}). Last updated {_esc(today)}.</p>

  <div class="ai-summary">{ai_summary}</div>

  <div class="badge-row">
    <div class="badge">
      <span class="badge-label">Risk Level</span>
      <span class="badge-rating" style="color: {risk_color}">{_esc(risk_level)}</span>
    </div>
    <div class="badge">
      <span class="badge-label">Trust Score</span>
      <span class="badge-rating">{trust_str}/100</span>
    </div>
    <div class="badge">
      <span class="badge-label">NDD</span>
      <span class="badge-rating">{ndd_str}</span>
    </div>
    <div class="badge">
      <span class="badge-label">Rating</span>
      <span class="badge-rating" style="color: var(--gray-400)">Pending</span>
    </div>
  </div>

  {pending_notice}

  <div class="score-card">
    <div class="score-item">
      <div class="value">{trust_str}</div>
      <div class="label">Trust Score</div>
      <div class="detail">Composite risk score 0-100</div>
    </div>
    <div class="score-item">
      <div class="value">{ndd_str}</div>
      <div class="label">Distance-to-Default</div>
      <div class="detail">{_ndd_description(ndd_val)}</div>
    </div>
    <div class="score-item">
      <div class="value" style="color:{risk_color}">{_esc(risk_level)}</div>
      <div class="label">Risk Level</div>
      <div class="detail">{risk_desc}</div>
    </div>
    <div class="score-item">
      <div class="value">{_fmt_score(trust_p3) if trust_p3 else 'N/A'}</div>
      <div class="label">Trust P3</div>
      <div class="detail">Third pillar trust metric (historical resilience)</div>
    </div>
    <div class="score-item" style="border-left:3px solid {vd_t2['color']}">
      <div class="value">{vd_t2['score']}</div>
      <div class="label">Vitality Score</div>
      <div class="detail">Grade {vd_t2['grade']} — ecosystem health</div>
    </div>
  </div>

  <div class="security-check-cta" style="margin:24px 0;padding:20px 24px;border:1px solid var(--gray-200);border-radius:12px;background:var(--gray-100);text-align:center">
    <p style="font-size:1.1em;font-weight:600;margin:0 0 6px;font-family:var(--sans)">This token scores <strong>{trust_score:.0f}</strong>/100. What&#39;s yours?</p>
    <p style="font-size:0.9em;color:var(--gray-500);margin:0 0 14px;font-family:var(--sans)">Free security check, 2 seconds, nothing stored.</p>
    <button onclick="runSecurityCheck()" class="security-check-btn" style="background:var(--warm);color:white;border:none;padding:10px 24px;border-radius:8px;font-size:0.95em;font-weight:500;cursor:pointer;font-family:var(--sans)">Get my score &rarr;</button>
  </div>

  {vitality_html_t2}

  {structural_warning}

  <h2 class="section-title">Risk Signal Breakdown</h2>
  <div class="signals-grid">
    <div class="signal-card">
      <div class="sig-name">Distance-to-Default (NDD)</div>
      <div class="sig-value">{ndd_str}</div>
      <div class="sig-desc">Structural distance from default threshold. Below 2.0 = elevated distress.</div>
    </div>
    <div class="signal-card">
      <div class="sig-name">Structural Signal (Sig6)</div>
      <div class="sig-value">{_fmt_score(sig6)}</div>
      <div class="sig-desc">Structural integrity score. Lower values indicate structural weakness.</div>
    </div>
    <div class="signal-card">
      <div class="sig-name">Trust Score</div>
      <div class="sig-value">{trust_str}</div>
      <div class="sig-desc">Composite trust metric based on available risk signals.</div>
    </div>
    <div class="signal-card">
      <div class="sig-name">Structural Weaknesses</div>
      <div class="sig-value">{structural_weakness}</div>
      <div class="sig-desc">Number of active structural weakness signals. 3+ indicates high collapse risk.</div>
    </div>
  </div>

  {_pros_cons_html(ri)}

  {_investment_summary_html(ri)}

  <div class="faq-section">
    <h2 class="section-title">Frequently Asked Questions</h2>
    <div class="faq-item">
      <div class="faq-q">Is {_esc(name)} safe to invest in?</div>
      <div class="faq-a">{faq_answer_1}</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">What is {_esc(name)}'s risk rating?</div>
      <div class="faq-a">{faq_answer_2}</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">Will {_esc(name)} crash?</div>
      <div class="faq-a">{faq_answer_3}</div>
    </div>
    {_extra_faq_html(ri)}
  </div>

  {_internal_links_html(token_id, name)}

  <div style="margin-top:48px;padding:24px;background:var(--gray-100);border:1px solid var(--gray-200);font-family:var(--mono);font-size:12px;color:var(--gray-600)">
    <strong>Disclaimer:</strong> ZARQ ratings are quantitative risk assessments, not investment advice. Past performance does not predict future results. Always do your own research.
  </div>
</div>

<footer>
  <p>&copy; 2026 <a href="https://zarq.ai">ZARQ</a> — Independent crypto risk intelligence</p>
</footer>
</body>
</html>'''
    html = html.replace('</body>', _SECURITY_CHECK_JS + '</body>')
    return html


def _render_ndd_only_page(slug, token_id, token_info, ndd_row):
    """Render a T4 token page — NDD data only, no rating or risk signals."""
    name = token_info.get("name") or (ndd_row["name"] if ndd_row["name"] else token_id.replace("-", " ").title())
    symbol = token_info.get("symbol") or (ndd_row["symbol"] if ndd_row["symbol"] else token_id.split("-")[0].upper())
    tier_info = _slug_map.get(token_id, {})
    risk_grade = tier_info.get("risk_grade", "NR")

    ndd_val = ndd_row["ndd"]
    crash_prob = ndd_row["crash_probability"]
    alert_level = ndd_row["alert_level"] or "N/A"
    price = ndd_row["price_usd"]
    today = date.today().isoformat()

    ndd_str = _fmt_score(ndd_val) if ndd_val else "N/A"
    crash_pct = f"{crash_prob * 100:.0f}" if crash_prob is not None else "N/A"
    price_str = _fmt_price(price)
    risk_color = _alert_color(alert_level)
    grade_col = grade_color(risk_grade)

    # Build risk_info for shared helpers
    ri = _build_risk_info(name, symbol, slug, token_id, "T4",
        alert_level=alert_level, ndd=ndd_val,
        crash_pct=crash_pct, crash_prob=crash_prob,
        structural_weakness=0, has_rating=False, risk_grade=risk_grade)

    # Vitality Score
    vitality_html_t4, vd_t4 = _vitality_section_html(token_id, name)

    vd_ai_t4 = _get_vitality_data(token_id)
    vitality_note_t4 = ""
    if vd_ai_t4["score"] != "N/A":
        vitality_note_t4 = (
            f" Vitality Score: {vd_ai_t4['score']}/100 (Grade {vd_ai_t4['grade']}), indicating crash resistance — "
            f"backtested high-Vitality tokens lost 44% less during the 2025-2026 market crash (p < 0.001)."
        )
    ai_summary = (
        f"Is {_esc(name)} safe? ZARQ monitors {_esc(name)} ({_esc(symbol)}) with a risk score based on "
        f"Distance-to-Default of {ndd_str} and crash probability of {crash_pct}%. "
        f"Alert level: {_esc(alert_level)}. Risk grade: {_esc(risk_grade)}.{vitality_note_t4} "
        f"Investors searching for {_esc(name)} safety information should note this token is monitored "
        f"daily via ZARQ's quantitative risk engine. Full credit rating pending."
    )

    faq_answer_1 = (
        f"{_esc(name)} ({_esc(symbol)}) is monitored by ZARQ's risk engine. "
        f"The current crash probability is {crash_pct}% and the Distance-to-Default stands at {ndd_str}. "
        f"The alert level is {_esc(alert_level)}, meaning {_ndd_description(ndd_val).lower()}. "
        f"A full Moody's-style rating is pending. Always do your own research."
    )
    faq_answer_2 = (
        f"{_esc(name)} does not yet have a full credit rating. Its risk grade is {_esc(risk_grade)}, "
        f"calculated from Distance-to-Default ({ndd_str}), crash probability ({crash_pct}%), "
        f"and alert level ({_esc(alert_level)}). Higher NDD values indicate greater distance from distress."
    )
    faq_answer_3 = (
        f"ZARQ's model estimates a {crash_pct}% crash probability for {_esc(name)}. "
        f"The NDD of {ndd_str} indicates {_ndd_description(ndd_val).lower()}. "
        f"These are quantitative estimates updated daily, not investment advice."
    )

    breadcrumb_jsonld = json.dumps({"@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Token Ratings", "item": "https://zarq.ai/tokens"},
            {"@type": "ListItem", "position": 3, "name": f"{name} ({symbol})"},
        ]})
    webpage_jsonld = json.dumps({"@context": "https://schema.org", "@type": "WebPage",
        "name": f"Is {name} Safe? {alert_level} Risk — ZARQ",
        "description": f"Is {name} safe? ZARQ monitors {name} with a crash probability of {crash_pct}% and NDD of {ndd_str}.",
        "url": f"https://zarq.ai/token/{slug}"})
    faq_jsonld = json.dumps({"@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": f"Is {name} safe?", "acceptedAnswer": {"@type": "Answer", "text": faq_answer_1}},
            {"@type": "Question", "name": f"What is {name}'s risk rating?", "acceptedAnswer": {"@type": "Answer", "text": faq_answer_2}},
            {"@type": "Question", "name": f"Will {name} crash?", "acceptedAnswer": {"@type": "Answer", "text": faq_answer_3}},
        ] + _extra_faq_jsonld(ri)})

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Is {_esc(name)} Safe? {_esc(alert_level)} Risk — ZARQ</title>
<meta name="description" content="Is {_esc(name)} safe? ZARQ monitors {_esc(name)} with a crash probability of {crash_pct}% and Distance-to-Default of {ndd_str}. Alert level: {_esc(alert_level)}. Independent risk monitoring.">
<link rel="canonical" href="https://zarq.ai/token/{_esc(slug)}">
<meta property="og:title" content="Is {_esc(name)} Safe? {_esc(alert_level)} Risk — ZARQ">
<meta property="og:description" content="Is {_esc(name)} safe? Crash probability: {crash_pct}%. NDD: {ndd_str}. Independent risk monitoring by ZARQ.">
<meta property="og:url" content="https://zarq.ai/token/{_esc(slug)}">
<meta property="og:type" content="article">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{webpage_jsonld}</script>
<script type="application/ld+json">{faq_jsonld}</script>
<script type="application/ld+json">{breadcrumb_jsonld}</script>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --white: #fafaf9; --black: #0a0a0a;
  --gray-100: #f5f5f4; --gray-200: #e7e5e4; --gray-400: #a8a29e;
  --gray-500: #78716c; --gray-600: #57534e; --gray-700: #44403c;
  --gray-800: #292524; --gray-900: #1c1917;
  --warm: #c2956b; --warm-light: rgba(194, 149, 107, 0.08);
  --green: #16a34a; --red: #dc2626; --yellow: #ca8a04;
  --serif: 'DM Serif Display', Georgia, serif;
  --mono: 'JetBrains Mono', monospace;
  --sans: 'DM Sans', sans-serif;
  --measure: 680px; --wide: 1120px;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
::selection {{ background: var(--warm); color: var(--black); }}
html {{ font-size: 17px; -webkit-font-smoothing: antialiased; }}
body {{ background: var(--white); color: var(--gray-800); font-family: var(--sans); line-height: 1.6; }}
nav {{ position: fixed; top: 0; left: 0; right: 0; z-index: 100; padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; backdrop-filter: blur(20px); background: rgba(250,250,249,0.85); border-bottom: 1px solid rgba(0,0,0,0.04); }}
.nav-mark {{ font-family: var(--mono); font-weight: 500; font-size: 15px; letter-spacing: 0.15em; text-transform: uppercase; color: var(--black); text-decoration: none; }}
.nav-links {{ display: flex; gap: 32px; align-items: center; }}
.nav-links a {{ font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-600); text-decoration: none; }}
.nav-links a:hover {{ color: var(--black); }}
.nav-api {{ font-family: var(--mono); font-size: 11px; letter-spacing: 0.05em; color: var(--warm); border: 1px solid var(--warm); padding: 6px 16px; text-decoration: none; }}
.nav-api:hover {{ background: var(--warm); color: var(--white); }}
.container {{ max-width: var(--wide); margin: 0 auto; padding: 120px 40px 80px; }}
.breadcrumb {{ font-family: var(--mono); font-size: 11px; color: var(--gray-500); margin-bottom: 24px; }}
.breadcrumb a {{ color: var(--warm); text-decoration: none; }}
h1 {{ font-family: var(--serif); font-size: 2.4rem; color: var(--black); line-height: 1.2; margin-bottom: 16px; }}
.subtitle {{ font-family: var(--sans); font-size: 1rem; color: var(--gray-600); margin-bottom: 40px; }}
.badge-row {{ display: flex; gap: 16px; align-items: center; margin-bottom: 40px; flex-wrap: wrap; }}
.badge {{ display: inline-flex; align-items: center; gap: 8px; padding: 8px 20px; border: 1px solid var(--gray-200); font-family: var(--mono); font-size: 13px; }}
.badge-rating {{ font-size: 18px; font-weight: 500; }}
.badge-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--gray-500); }}
.score-card {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 48px; }}
.score-item {{ background: var(--gray-100); border: 1px solid var(--gray-200); padding: 24px; }}
.score-item .value {{ font-family: var(--serif); font-size: 32px; color: var(--black); }}
.score-item .label {{ font-family: var(--mono); font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--gray-500); margin-top: 4px; }}
.score-item .detail {{ font-family: var(--sans); font-size: 13px; color: var(--gray-600); margin-top: 8px; }}
.ai-summary {{ background: var(--gray-100); border-left: 3px solid var(--warm); padding: 20px 24px; margin-bottom: 40px; font-family: var(--sans); font-size: 15px; line-height: 1.7; color: var(--gray-700); }}
.section-title {{ font-family: var(--serif); font-size: 1.6rem; color: var(--black); margin-bottom: 24px; margin-top: 48px; }}
.faq-section {{ margin-top: 48px; margin-bottom: 48px; }}
.faq-item {{ border-bottom: 1px solid var(--gray-200); padding: 24px 0; }}
.faq-item:first-child {{ border-top: 1px solid var(--gray-200); }}
.faq-q {{ font-family: var(--serif); font-size: 1.2rem; color: var(--black); margin-bottom: 12px; }}
.faq-a {{ font-family: var(--sans); font-size: 15px; color: var(--gray-700); line-height: 1.7; }}
footer {{ border-top: 1px solid var(--gray-200); padding: 40px; text-align: center; }}
footer p {{ font-family: var(--mono); font-size: 11px; color: var(--gray-500); }}
footer a {{ color: var(--warm); text-decoration: none; }}
@media (max-width: 768px) {{
  nav {{ padding: 16px 20px; }}
  .container {{ padding: 100px 20px 60px; }}
  h1 {{ font-size: 1.8rem; }}
  .score-card {{ grid-template-columns: 1fr 1fr; }}
}}
</style>
</head>
<body>
<!-- AI_SUMMARY: {ai_summary} -->
<nav>
  <a href="/" class="nav-mark">zarq</a>
  <div class="nav-links">
    <a href="/scan">Scan</a>
    <a href="/crypto">Ratings</a>
    <a href="/tokens">Token Ratings</a>
    <a href="/crash-watch">Crash Watch</a>
    <a href="/docs" class="nav-api">API</a>
  </div>
</nav>
<div class="container">
  <div class="breadcrumb">
    <a href="/">ZARQ</a> / <a href="/tokens">Token Ratings</a> / {_esc(name)}
  </div>
  <h1>Is {_esc(name)} Safe? — Risk Grade: {_esc(risk_grade)}</h1>
  <p class="subtitle">Quantitative risk monitoring for {_esc(name)} ({_esc(symbol)}). Last updated {_esc(today)}.</p>
  <div class="ai-summary">{ai_summary}</div>
  <div class="badge-row">
    <div class="badge">
      <span class="badge-label">Risk Grade</span>
      <span class="badge-rating" style="color: {grade_col}">{_esc(risk_grade)}</span>
    </div>
    <div class="badge">
      <span class="badge-label">Alert</span>
      <span class="badge-rating" style="color: {risk_color}">{_esc(alert_level)}</span>
    </div>
    <div class="badge">
      <span class="badge-label">NDD</span>
      <span class="badge-rating">{ndd_str}</span>
    </div>
    <div class="badge">
      <span class="badge-label">Crash Prob.</span>
      <span class="badge-rating">{crash_pct}%</span>
    </div>
  </div>
  <div style="background:rgba(194,149,107,0.08);border:1px solid rgba(194,149,107,0.25);padding:24px 28px;margin-bottom:48px">
    <div style="font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--warm);margin-bottom:8px">Risk Monitoring</div>
    <div style="font-family:var(--sans);font-size:14px;color:var(--gray-700)">
      Full credit rating pending for {_esc(name)} — currently monitored via Distance-to-Default model.
      A Moody's-style rating (Aaa-D) will be assigned once sufficient historical data is computed.</div>
  </div>
  <div class="score-card">
    <div class="score-item">
      <div class="value">{ndd_str}</div>
      <div class="label">Distance-to-Default</div>
      <div class="detail">{_ndd_description(ndd_val)}</div>
    </div>
    <div class="score-item">
      <div class="value">{crash_pct}%</div>
      <div class="label">Crash Probability</div>
      <div class="detail">Probability of &gt;50% drawdown</div>
    </div>
    <div class="score-item">
      <div class="value" style="color:{risk_color}">{_esc(alert_level)}</div>
      <div class="label">Alert Level</div>
      <div class="detail">Current risk monitoring status</div>
    </div>
    <div class="score-item">
      <div class="value">{price_str}</div>
      <div class="label">Price</div>
      <div class="detail">Last recorded price</div>
    </div>
    <div class="score-item" style="border-left:3px solid {vd_t4['color']}">
      <div class="value">{vd_t4['score']}</div>
      <div class="label">Vitality Score</div>
      <div class="detail">Grade {vd_t4['grade']} — ecosystem health</div>
    </div>
  </div>
  {vitality_html_t4}
  {_pros_cons_html(ri)}

  {_investment_summary_html(ri)}

  <div class="faq-section">
    <h2 class="section-title">Frequently Asked Questions</h2>
    <div class="faq-item">
      <div class="faq-q">Is {_esc(name)} safe to invest in?</div>
      <div class="faq-a">{faq_answer_1}</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">What is {_esc(name)}'s risk rating?</div>
      <div class="faq-a">{faq_answer_2}</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">Will {_esc(name)} crash?</div>
      <div class="faq-a">{faq_answer_3}</div>
    </div>
    {_extra_faq_html(ri)}
  </div>

  {_internal_links_html(token_id, name)}

  <div style="margin-top:48px;padding:24px;background:var(--gray-100);border:1px solid var(--gray-200);font-family:var(--mono);font-size:12px;color:var(--gray-600)">
    <strong>Disclaimer:</strong> ZARQ ratings are quantitative risk assessments, not investment advice. Past performance does not predict future results. Always do your own research.
  </div>
</div>
<footer>
  <p>&copy; 2026 <a href="https://zarq.ai">ZARQ</a> — Independent crypto risk intelligence</p>
</footer>
</body>
</html>'''
    return html


def _render_token_page(slug, token_id, token_info):
    """Render a token page with full SEO markup. Falls back to risk-signal page if no rating."""
    _load_slugs()
    tier_data = _slug_map.get(token_id, {})
    tier = tier_data.get("tier", "T1")

    # Check staged rollout
    if tier not in ENABLED_TIERS:
        return None

    rating_row, ndd_row, risk_row, similar_tokens, defi_category = _get_token_data(token_id)

    # T1: Full Moody's rating — use template
    if rating_row:
        pass  # falls through to template rendering below

    # T2/T4: Has NDD data — use risk signal page if available, else NDD-only page
    elif ndd_row:
        if risk_row:
            return _render_risk_signal_page(slug, token_id, token_info, risk_row, ndd_row)
        return _render_ndd_only_page(slug, token_id, token_info, ndd_row)

    # No data at all
    else:
        return None

    # === T1 rendering below (rating_row exists) ===

    name = token_info.get("name") or (ndd_row["name"] if ndd_row and ndd_row["name"] else token_id.replace("-", " ").title())
    symbol = token_info.get("symbol") or (ndd_row["symbol"] if ndd_row and ndd_row["symbol"] else token_id.split("-")[0].upper())
    rating = rating_row["rating"] or "NR"
    score = rating_row["score"] or 0
    run_date = rating_row["run_date"] or ""

    # NDD data
    ndd_val = ndd_row["ndd"] if ndd_row else None
    crash_prob = ndd_row["crash_probability"] if ndd_row else None
    crash_pct = f"{crash_prob * 100:.0f}" if crash_prob is not None else "N/A"
    alert_level = ndd_row["alert_level"] if ndd_row else "N/A"
    price = ndd_row["price_usd"] if ndd_row else (rating_row["price_usd"] if rating_row["price_usd"] else None)

    # Risk signals
    structural_weakness = risk_row["structural_weakness"] if risk_row else 0
    sig6 = risk_row["sig6_structure"] if risk_row else None

    # Pillars
    p1 = _fmt_score(rating_row["pillar_1"])
    p2 = _fmt_score(rating_row["pillar_2"])
    p3 = _fmt_score(rating_row["pillar_3"])
    p4 = _fmt_score(rating_row["pillar_4"])
    p5 = _fmt_score(rating_row["pillar_5"])

    # FAQ answers
    score_desc, crash_desc, struct_desc = _risk_summary(rating, crash_pct, alert_level, structural_weakness)
    ndd_str = _fmt_score(ndd_val) if ndd_val else "N/A"
    drawdown_90d = risk_row["drawdown_90d"] if risk_row and risk_row["drawdown_90d"] else None
    dd_sentence = f" Over the past 90 days, {_esc(name)} has experienced a {abs(drawdown_90d)*100:.1f}% maximum drawdown." if drawdown_90d and drawdown_90d < -0.01 else ""

    faq_answer_1 = (
        f"{_esc(name)} ({_esc(symbol)}) currently holds a {_esc(rating)} rating from ZARQ with a trust score of "
        f"{_fmt_score(score)}/100. This is {score_desc}. The current crash probability is {crash_pct}%, "
        f"and its Distance-to-Default stands at {ndd_str}. "
        f"{struct_desc}{dd_sentence} "
        f"The alert level is {_esc(alert_level)}. As with all crypto investments, you should conduct your own research and consider your risk tolerance."
    )
    faq_answer_2 = (
        f"ZARQ rates {_esc(name)} at {_esc(rating)} on a Moody's-style scale (Aaa to C), where Baa3 and above is investment grade. "
        f"The trust score is {_fmt_score(score)} out of 100, based on five quantitative pillars: "
        f"ecosystem strength ({p1}/100), contagion risk ({p2}/100), historical resilience ({p3}/100), "
        f"fundamental quality ({p4}/100), and rug pull risk ({p5}/100). "
        f"The strongest pillar is {_best_pillar(rating_row)}, while {_weakest_pillar(rating_row)} scores lowest. "
        f"The alert level is currently {_esc(alert_level)}."
    )
    faq_answer_3 = (
        f"ZARQ's crash model estimates a {crash_pct}% probability of a &gt;50% drawdown for {_esc(name)}. "
        f"The Distance-to-Default (NDD) is {ndd_str}, which indicates "
        f"{_ndd_description(ndd_val).lower()}. "
        f"The structural integrity signal (Sig6) is {_fmt_score(sig6)}, and there "
        f"{'are' if (structural_weakness or 0) != 1 else 'is'} {structural_weakness or 0} structural weakness "
        f"signal{'s' if (structural_weakness or 0) != 1 else ''} active. "
        f"{struct_desc} "
        f"These are model-based estimates updated daily, not guarantees of future performance."
    )

    # Build risk_info for shared helpers
    ri = _build_risk_info(name, symbol, slug, token_id, "T1",
        rating=rating, risk_level=alert_level, alert_level=alert_level,
        trust_score=score, ndd=ndd_val,
        crash_pct=crash_pct, crash_prob=crash_prob,
        structural_weakness=structural_weakness or 0, has_rating=True,
        risk_grade=rating)

    # AI summary — citation-optimized: key facts in first 3 sentences
    struct_status = "No structural weaknesses detected." if (structural_weakness or 0) == 0 else f"{structural_weakness} structural weakness signal{'s' if structural_weakness != 1 else ''} active — elevated collapse risk."
    vd_ai = _get_vitality_data(token_id)
    vitality_sentence = ""
    if vd_ai["score"] != "N/A":
        vitality_sentence = f" and a Vitality Score of {vd_ai['grade']} ({vd_ai['score']}/100)"
    risk_detail = ""
    if alert_level in ("WARNING", "CRITICAL"):
        risk_detail = f" ZARQ's structural analysis detected {structural_weakness or 0} weakness signal{'s' if (structural_weakness or 0) != 1 else ''}."
    ai_summary = (
        f"{_esc(name)} ({_esc(symbol)}) has a ZARQ Safety Rating of {_esc(rating)} ({_fmt_score(score)}/100){vitality_sentence}. "
        f"Risk level: {_esc(alert_level)}. Crash probability: {crash_pct}%. Distance-to-Default: {ndd_str}.{risk_detail} "
        f"Last updated: {_esc(run_date)}. Based on 7 quantitative pillars including NDD, crash probability, TVL, and DeFi yield analysis. "
        f"{struct_status}"
    )

    # JSON-LD: BreadcrumbList
    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Token Ratings", "item": "https://zarq.ai/tokens"},
            {"@type": "ListItem", "position": 3, "name": f"{name} ({symbol})"},
        ]
    })

    # JSON-LD: WebPage
    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"Is {name} Safe? {rating} Risk Rating",
        "description": f"{name} ({symbol}) has a {rating} risk rating with a {crash_pct}% crash probability.",
        "url": f"https://zarq.ai/token/{slug}",
        "publisher": {
            "@type": "Organization",
            "name": "ZARQ",
            "url": "https://zarq.ai"
        },
        "dateModified": run_date,
    })

    # JSON-LD: FAQPage (7 questions)
    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f"Is {name} safe to invest in?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq_answer_1.replace("&gt;", ">")
                }
            },
            {
                "@type": "Question",
                "name": f"What is {name}'s risk rating?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq_answer_2
                }
            },
            {
                "@type": "Question",
                "name": f"Will {name} crash?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq_answer_3.replace("&gt;", ">")
                }
            },
        ] + _extra_faq_jsonld(ri) + ([{
            "@type": "Question",
            "name": f"How crash-resistant is {name}?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": (
                    f"{name} has a ZARQ Vitality Score of {vd_ai['score']}/100 (Grade {vd_ai['grade']}). "
                    f"In backtesting across 3 time windows (355-412 tokens each), high-Vitality tokens "
                    f"lost 44% less during the July 2025 to February 2026 crypto crash, with statistical "
                    f"significance (p < 0.001). Stress Resilience is the strongest predictive dimension. "
                    f"See full backtest results at zarq.ai/vitality/backtest."
                )
            }
        }] if vd_ai["score"] != "N/A" else [])
    })

    # Structural warning box
    structural_warning = ""
    sw = structural_weakness or 0
    if sw >= 3:
        structural_warning = (
            '<div class="warning-box">'
            '<div class="warn-title">Structural Collapse Warning</div>'
            f'<div class="warn-text">{_esc(name)} has {sw} structural weakness signals active. '
            'The Distance-to-Default model has flagged this token for elevated collapse risk. '
            'Tokens with 3+ structural weaknesses have historically experienced severe drawdowns.</div>'
            '</div>'
        )
    elif sw >= 2:
        structural_warning = (
            '<div class="warning-box">'
            '<div class="warn-title">Structural Stress Detected</div>'
            f'<div class="warn-text">{_esc(name)} has {sw} structural stress signals. '
            'This indicates emerging weakness that may worsen. Monitor closely.</div>'
            '</div>'
        )
    elif sw == 0 and alert_level == "SAFE":
        structural_warning = (
            '<div class="safe-box">'
            '<div class="safe-title">No Structural Warnings</div>'
            f'<div class="safe-text">{_esc(name)} shows no structural weaknesses. '
            'The Distance-to-Default model indicates healthy structural integrity.</div>'
            '</div>'
        )

    # Compare section
    compare_section = ""
    if similar_tokens:
        _load_slugs()
        cards = ""
        for st in similar_tokens:
            st_id = st["token_id"]
            st_slug = st_id  # slug == token_id in our mapping
            st_name = st["name"] or st_id.replace("-", " ").title()
            st_symbol = (st["symbol"] or st_id.split("-")[0][:5]).upper()
            st_rating = st["rating"]
            st_score = st["score"]
            st_vd = _get_vitality_data(st_id)
            vit_line = f' · Vitality: {st_vd["score"]} ({st_vd["grade"]})' if st_vd["score"] != "N/A" else ""
            cards += (
                f'<a href="/token/{_esc(st_slug)}" class="compare-card">'
                f'<div class="cc-name">{_esc(st_name)}</div>'
                f'<div class="cc-rating" style="color:{_rating_color(st_rating)}">{_esc(st_rating)}</div>'
                f'<div class="cc-score">{_esc(st_symbol)} — Score: {_fmt_score(st_score)}{vit_line}</div>'
                '</a>'
            )
        compare_section = (
            '<div class="compare-section">'
            f'<h2 class="section-title">Compare Similar Tokens ({_esc(rating)} Rated)</h2>'
            f'<div class="compare-grid">{cards}</div>'
            '</div>'
        )

    # Price display
    price_str = _fmt_price(price)
    price_change = ""
    if rating_row["price_change_24h"] is not None:
        pc24 = rating_row["price_change_24h"]
        color = "var(--green)" if pc24 >= 0 else "var(--red)"
        price_change = f'<span style="color:{color}">{pc24:+.1f}% (24h)</span>'

    # Vitality Score
    vitality_html, vd = _vitality_section_html(token_id, name)

    # Read template
    template_path = TEMPLATE_DIR / "token_page.html"
    html = template_path.read_text()

    # Replace placeholders
    replacements = {
        "{{ name }}": _esc(name),
        "{{ symbol }}": _esc(symbol),
        "{{ slug }}": _esc(slug),
        "{{ rating }}": _esc(rating),
        "{{ score }}": _fmt_score(score),
        "{{ run_date }}": _esc(run_date),
        "{{ rating_color }}": _rating_color(rating),
        "{{ crash_pct }}": _esc(crash_pct),
        "{{ crash_color }}": _alert_color(alert_level) if crash_prob and crash_prob > 0.15 else "#ca8a04" if crash_prob and crash_prob > 0.05 else "#16a34a",
        "{{ alert_level }}": _esc(alert_level),
        "{{ alert_color }}": _alert_color(alert_level),
        "{{ ndd }}": _fmt_score(ndd_val),
        "{{ ndd_desc }}": _ndd_description(ndd_val),
        "{{ price_usd }}": price_str,
        "{{ price_change }}": price_change,
        "{{ pillar_1 }}": p1,
        "{{ pillar_2 }}": p2,
        "{{ pillar_3 }}": p3,
        "{{ pillar_4 }}": p4,
        "{{ pillar_5 }}": p5,
        "{{ sig6 }}": _fmt_score(sig6),
        "{{ structural_warning }}": structural_warning,
        "{{ mica_badge }}": get_mica_badge_html(token_id, defi_category),
        "{{ compare_section }}": compare_section,
        "{{ pros_cons_section }}": _pros_cons_html(ri),
        "{{ investment_summary_section }}": _investment_summary_html(ri),
        "{{ extra_faq_html }}": _extra_faq_html(ri),
        "{{ internal_links_section }}": _internal_links_html(token_id, name),
        "{{ vitality_score }}": vd["score"],
        "{{ vitality_grade }}": vd["grade"],
        "{{ vitality_color }}": vd["color"],
        "{{ vitality_section }}": vitality_html,
        "{{ faq_answer_1 }}": faq_answer_1,
        "{{ faq_answer_2 }}": faq_answer_2,
        "{{ faq_answer_3 }}": faq_answer_3,
        "{{ webpage_jsonld }}": webpage_jsonld,
        "{{ faq_jsonld }}": faq_jsonld,
        "{{ breadcrumb_jsonld }}": breadcrumb_jsonld,
        "{{ product_jsonld }}": json.dumps({
            "@context": "https://schema.org",
            "@type": "Product",
            "name": f"{name} ({symbol})",
            "description": f"{name} crypto token — ZARQ Safety Rating: {rating} ({_fmt_score(score)}/100). Crash probability: {crash_pct}%.",
            "url": f"https://zarq.ai/token/{slug}",
            "brand": {"@type": "Brand", "name": name},
            "review": {
                "@type": "Review",
                "author": {"@type": "Organization", "name": "ZARQ", "url": "https://zarq.ai"},
                "reviewRating": {
                    "@type": "Rating",
                    "ratingValue": str(_fmt_score(score)),
                    "bestRating": "100",
                    "worstRating": "0",
                },
                "reviewBody": f"ZARQ rates {name} ({symbol}) at {rating} with a trust score of {_fmt_score(score)}/100 and {crash_pct}% crash probability.",
            },
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": str(_fmt_score(score)),
                "bestRating": "100",
                "worstRating": "0",
                "ratingCount": "1",
            },
        }),
        "{{ ai_summary }}": ai_summary,
        "{{ security_check_cta }}": f'''<div class="security-check-cta" style="
            margin:24px 0;padding:20px 24px;border:1px solid var(--gray-200);
            border-radius:12px;background:var(--gray-100);text-align:center">
            <p style="font-size:1.1em;font-weight:600;margin:0 0 6px;font-family:var(--sans)">
                This token scores <strong>{_fmt_score(score)}</strong>/100.
                What&#39;s yours?
            </p>
            <p style="font-size:0.9em;color:var(--gray-500);margin:0 0 14px;font-family:var(--sans)">
                Free security check, 2 seconds, nothing stored.
            </p>
            <button onclick="runSecurityCheck()" class="security-check-btn" style="
                background:var(--warm);color:white;border:none;padding:10px 24px;
                border-radius:8px;font-size:0.95em;font-weight:500;cursor:pointer;font-family:var(--sans)">
                Get my score &rarr;
            </button>
        </div>''',
    }

    for key, val in replacements.items():
        html = html.replace(key, str(val))

    return html


def _render_tokens_index():
    """Render the hub page listing all tokens (rated + risk-signal-only)."""
    _load_slugs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Tier (a): fully rated tokens
    rated_rows = conn.execute("""
        SELECT r.token_id, r.rating, r.score, r.price_usd as r_price,
               n.symbol, n.name, n.crash_probability, n.alert_level, n.price_usd
        FROM crypto_rating_daily r
        LEFT JOIN crypto_ndd_daily n ON r.token_id = n.token_id
            AND n.run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)
        WHERE r.run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
        ORDER BY r.score DESC
    """).fetchall()

    rated_ids = {r["token_id"] for r in rated_rows}

    # Tier (b): risk-signal-only tokens (not in rated)
    risk_only_rows = conn.execute("""
        SELECT s.token_id, s.risk_level, s.trust_score, s.ndd_current,
               s.structural_weakness
        FROM nerq_risk_signals s
        WHERE s.signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals WHERE token_id = s.token_id)
          AND s.token_id NOT IN (SELECT DISTINCT token_id FROM crypto_rating_daily)
        ORDER BY s.trust_score DESC
    """).fetchall()

    # Tier T2/T4: NDD-only tokens (not in rated and not in risk_signals)
    risk_only_ids = {r["token_id"] for r in risk_only_rows}
    ndd_only_rows = conn.execute("""
        SELECT n.token_id, n.symbol, n.name, n.ndd, n.crash_probability,
               n.alert_level, n.price_usd, n.market_cap_rank
        FROM crypto_ndd_daily n
        WHERE n.run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)
          AND n.token_id NOT IN (SELECT DISTINCT token_id FROM crypto_rating_daily)
          AND n.token_id NOT IN (SELECT DISTINCT token_id FROM nerq_risk_signals)
        ORDER BY n.market_cap_rank ASC NULLS LAST
    """).fetchall()

    conn.close()

    total = len(rated_rows) + len(risk_only_rows) + len(ndd_only_rows)

    # Build table rows
    table_rows = ""
    itemlist_items = []
    idx = 0

    # Rated tokens first
    for row in rated_rows:
        tid = row["token_id"]
        slug = tid
        name = row["name"] or tid.replace("-", " ").title()
        symbol = (row["symbol"] or tid.split("-")[0][:5]).upper()
        rating = row["rating"] or "NR"
        score = row["score"] or 0
        crash_prob = row["crash_probability"]
        crash_pct = f"{crash_prob * 100:.0f}%" if crash_prob is not None else "N/A"
        crash_sort = f"{crash_prob * 100:.1f}" if crash_prob is not None else "999"
        alert_level = row["alert_level"] or "N/A"
        price = row["price_usd"] or row["r_price"]
        price_str = _fmt_price(price)
        price_sort = f"{price:.8f}" if price else "0"

        sc = _status_class(alert_level)

        table_rows += (
            f'<tr>'
            f'<td><a href="/token/{_esc(slug)}">{_esc(name)}</a></td>'
            f'<td class="mono">{_esc(symbol)}</td>'
            f'<td><span class="rating-badge" style="color:{_rating_color(rating)}">{_esc(rating)}</span></td>'
            f'<td class="mono" data-sort="{score:.1f}">{score:.1f}</td>'
            f'<td class="mono" data-sort="{crash_sort}">{_esc(crash_pct)}</td>'
            f'<td class="mono {sc}">{_esc(alert_level)}</td>'
            f'<td class="mono" data-sort="{price_sort}">{price_str}</td>'
            f'</tr>\n'
        )

        itemlist_items.append({
            "@type": "ListItem",
            "position": idx + 1,
            "url": f"https://zarq.ai/token/{slug}",
            "name": f"{name} ({symbol}) — {rating}"
        })
        idx += 1

    # Risk-signal-only tokens
    for row in risk_only_rows:
        tid = row["token_id"]
        slug = tid
        # Look up name/symbol from slug map
        tinfo = _slug_map.get(tid, {})
        name = tinfo.get("name") or tid.replace("-", " ").title()
        symbol = tinfo.get("symbol") or tid.split("-")[0].upper()[:5]
        risk_level = row["risk_level"] or "N/A"
        trust_score = row["trust_score"] or 0
        score_sort = f"{trust_score:.1f}" if trust_score else "0"
        rl_color = _risk_level_color(risk_level)
        sc = _status_class(risk_level)

        table_rows += (
            f'<tr>'
            f'<td><a href="/token/{_esc(slug)}">{_esc(name)}</a></td>'
            f'<td class="mono">{_esc(symbol)}</td>'
            f'<td><span class="rating-badge" style="color:{rl_color}">{_esc(risk_level)}</span></td>'
            f'<td class="mono" data-sort="{score_sort}">{_fmt_score(trust_score)}</td>'
            f'<td class="mono" data-sort="999">N/A</td>'
            f'<td class="mono {sc}">{_esc(risk_level)}</td>'
            f'<td class="mono" data-sort="0">N/A</td>'
            f'</tr>\n'
        )

        itemlist_items.append({
            "@type": "ListItem",
            "position": idx + 1,
            "url": f"https://zarq.ai/token/{slug}",
            "name": f"{name} ({symbol}) — {risk_level}"
        })
        idx += 1

    # NDD-only tokens (T2/T4 without risk signals)
    for row in ndd_only_rows:
        tid = row["token_id"]
        slug = tid
        tinfo = _slug_map.get(tid, {})
        name = tinfo.get("name") or row["name"] or tid.replace("-", " ").title()
        symbol = (tinfo.get("symbol") or row["symbol"] or tid.split("-")[0][:5]).upper()
        ndd_val = row["ndd"]
        crash_prob = row["crash_probability"]
        crash_pct = f"{crash_prob * 100:.0f}%" if crash_prob is not None else "N/A"
        crash_sort = f"{crash_prob * 100:.1f}" if crash_prob is not None else "999"
        alert_level = row["alert_level"] or "N/A"
        price = row["price_usd"]
        price_str = _fmt_price(price)
        price_sort = f"{price:.8f}" if price else "0"
        risk_grade = tinfo.get("risk_grade", "NR")
        sc = _status_class(alert_level)

        table_rows += (
            f'<tr>'
            f'<td><a href="/token/{_esc(slug)}">{_esc(name)}</a></td>'
            f'<td class="mono">{_esc(symbol)}</td>'
            f'<td><span class="rating-badge" style="color:{grade_color(risk_grade)}">{_esc(risk_grade)}</span></td>'
            f'<td class="mono" data-sort="{_fmt_score(ndd_val)}">{_fmt_score(ndd_val)}</td>'
            f'<td class="mono" data-sort="{crash_sort}">{_esc(crash_pct)}</td>'
            f'<td class="mono {sc}">{_esc(alert_level)}</td>'
            f'<td class="mono" data-sort="{price_sort}">{price_str}</td>'
            f'</tr>\n'
        )

        itemlist_items.append({
            "@type": "ListItem",
            "position": idx + 1,
            "url": f"https://zarq.ai/token/{slug}",
            "name": f"{name} ({symbol}) — {risk_grade}"
        })
        idx += 1

    # JSON-LD ItemList
    itemlist_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Crypto Risk Ratings — {total} Tokens Monitored",
        "description": f"Independent crypto risk ratings and monitoring for {total} tokens by ZARQ.",
        "numberOfItems": total,
        "itemListElement": itemlist_items
    })

    # Read template
    template_path = TEMPLATE_DIR / "tokens_index.html"
    html = template_path.read_text()

    html = html.replace("{{ total }}", str(total))
    html = html.replace("{{ table_rows }}", table_rows)
    html = html.replace("{{ itemlist_jsonld }}", itemlist_jsonld)

    return html


def mount_token_pages(app):
    """Mount /token/{slug} and /tokens routes."""
    _load_slugs()

    @app.get("/tokens", response_class=HTMLResponse)
    async def tokens_index_page():
        try:
            html = _render_tokens_index()
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering tokens index: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error loading token ratings</h1><p>{_esc(str(e))}</p>")

    @app.get("/token/{slug}", response_class=HTMLResponse)
    async def token_page(slug: str):
        _load_slugs()
        # In new format, slug == token_id
        token_id = slug
        if token_id not in _slug_ids:
            return HTMLResponse(status_code=404, content="<h1>Token not found</h1><p>No rating data available for this token.</p>")

        # Build token_info from slug map
        slug_data = _slug_map.get(token_id, {})
        token_info = {
            "name": slug_data.get("name"),
            "symbol": slug_data.get("symbol"),
            "tier": slug_data.get("tier"),
            "risk_grade": slug_data.get("risk_grade"),
        }

        try:
            html = _render_token_page(slug, token_id, token_info)
            if html is None:
                return HTMLResponse(status_code=404, content="<h1>Token not found</h1><p>No rating data available for this token.</p>")
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering token page {slug}: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    # ================================================================
    # SAFE TOKEN PAGES — "Is {token} safe to buy?"
    # ================================================================
    def _render_safe_token_page(slug, token_id, token_info):
        """Render a safety-focused token page targeting 'is X safe to buy?' queries."""
        rating_row, ndd_row, risk_row, similar_tokens, defi_category = _get_token_data(token_id)
        if not rating_row and not ndd_row:
            return None

        name = token_info.get("name") or (ndd_row["name"] if ndd_row and ndd_row["name"] else token_id.replace("-", " ").title())
        symbol = token_info.get("symbol") or token_id.split("-")[0].upper()

        score = rating_row["score"] if rating_row else 0
        rating = rating_row["rating"] if rating_row else "NR"
        crash_prob = ndd_row["crash_probability"] if ndd_row else None
        crash_pct = f"{crash_prob * 100:.0f}" if crash_prob is not None else "N/A"
        alert_level = ndd_row["alert_level"] if ndd_row else "N/A"
        ndd_val = ndd_row["ndd"] if ndd_row else None
        structural_weakness = risk_row["structural_weakness"] if risk_row else 0

        # Safety verdict
        if score >= 70:
            verdict = "RELATIVELY SAFE"
            verdict_color = "#16a34a"
            verdict_desc = f"{_esc(name)} has a strong trust rating of {_esc(rating)}. While no crypto is risk-free, this token shows solid fundamentals."
        elif score >= 40:
            verdict = "EXERCISE CAUTION"
            verdict_color = "#ca8a04"
            verdict_desc = f"{_esc(name)} has a moderate risk profile with a {_esc(rating)} rating. Research thoroughly before investing."
        else:
            verdict = "HIGH RISK"
            verdict_color = "#dc2626"
            verdict_desc = f"{_esc(name)} shows elevated risk signals. Consider this a speculative asset with significant downside potential."

        # Similar tokens for alternatives
        alts_html = ""
        if similar_tokens:
            for t in similar_tokens[:5]:
                t_name = _esc(t["name"] or t["token_id"] if t["name"] else t["token_id"])
                t_score = _fmt_score(t["score"] or 0)
                t_id = t["token_id"]
                alts_html += f'<a href="/safe/token/{t_id}" style="display:inline-block;padding:6px 12px;border:1px solid #e5e7eb;font-size:13px;color:#1a1a1a;text-decoration:none;margin:3px">{t_name} ({t_score}/100)</a>'

        # FAQ schema
        faq_items = [
            (f"Is {_esc(name)} safe to buy?",
             f"{_esc(name)} ({_esc(symbol)}) has a ZARQ Trust Score of {_fmt_score(score)}/100 and a {_esc(rating)} rating. "
             f"The crash probability is {crash_pct}%. Verdict: {verdict.lower()}."),
            (f"Is {_esc(name)} a scam?",
             f"Based on quantitative analysis, {_esc(name)} shows {structural_weakness} structural weakness signal{'s' if structural_weakness != 1 else ''}. "
             f"The alert level is {_esc(alert_level)}. A trust score of {_fmt_score(score)}/100 suggests {'legitimate fundamentals' if score >= 50 else 'elevated risk — conduct thorough research'}."),
            (f"What is the crash risk for {_esc(name)}?",
             f"ZARQ estimates a {crash_pct}% probability of a >50% drawdown. The Distance-to-Default is {_fmt_score(ndd_val) if ndd_val else 'N/A'}."),
            (f"Should I invest in {_esc(name)}?",
             f"This is not financial advice. {_esc(name)} has a {_esc(rating)} rating ({_fmt_score(score)}/100). "
             f"{'It meets investment-grade criteria.' if score >= 60 else 'It falls below investment-grade criteria.'} Always do your own research."),
        ]
        faq_html = ""
        faq_jsonld = ""
        for q, a in faq_items:
            faq_html += f'<div style="border-bottom:1px solid #e5e7eb;padding:12px 0"><div style="font-weight:600;font-size:14px">{q}</div><div style="font-size:13px;color:#374151;margin-top:6px">{a}</div></div>'
            faq_jsonld += f'{{"@type":"Question","name":"{q}","acceptedAnswer":{{"@type":"Answer","text":"{a}"}}}},'

        return f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Is {_esc(name)} Safe to Buy? DeFi Risk Analysis 2026 | ZARQ</title>
<meta name="description" content="Is {_esc(name)} ({_esc(symbol)}) safe? Trust Score: {_fmt_score(score)}/100. Rating: {_esc(rating)}. Crash probability: {crash_pct}%. Independent risk analysis by ZARQ.">
<link rel="canonical" href="https://zarq.ai/safe/token/{slug}">
<meta property="og:title" content="Is {_esc(name)} Safe to Buy? | ZARQ Risk Analysis">
<meta property="og:description" content="Trust Score {_fmt_score(score)}/100 · Rating {_esc(rating)} · Crash probability {crash_pct}%">
<meta property="og:url" content="https://zarq.ai/safe/token/{slug}">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{faq_jsonld.rstrip(",")}]}}
</script>
<style>
:root{{--warm:#c2956b;--green:#16a34a;--yellow:#ca8a04;--red:#dc2626;--gray-700:#374151;--sans:DM Sans,system-ui,sans-serif;--serif:DM Serif Display,Georgia,serif;--mono:JetBrains Mono,monospace}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:var(--sans);color:#1a1a1a;background:#fff;line-height:1.6}}
.container{{max-width:800px;margin:0 auto;padding:24px}}
h1{{font-family:var(--serif);font-size:1.6rem;margin-bottom:8px}}
.verdict{{display:inline-block;padding:8px 20px;font-weight:700;font-size:18px;letter-spacing:1px;margin:16px 0}}
.score-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}}
.score-card{{padding:16px;border:1px solid #e5e7eb;text-align:center}}
.score-card .num{{font-size:24px;font-weight:700;font-family:var(--mono)}}
.score-card .lbl{{font-size:11px;color:#6b7280;text-transform:uppercase;margin-top:4px}}
</style>
</head><body>
<div class="container">
<nav style="font-size:12px;color:#6b7280;margin-bottom:16px"><a href="/" style="color:var(--warm)">ZARQ</a> &rsaquo; <a href="/tokens" style="color:var(--warm)">Tokens</a> &rsaquo; Is {_esc(name)} Safe?</nav>

<h1>Is {_esc(name)} ({_esc(symbol)}) Safe to Buy?</h1>
<p style="font-size:15px;color:#374151;margin-bottom:16px">Independent quantitative risk analysis of {_esc(name)}. Updated {date.today().strftime("%B %Y")}.</p>

<div class="verdict" style="color:{verdict_color};border:2px solid {verdict_color};background:{verdict_color}11">{verdict}</div>
<p style="font-size:14px;color:#374151;margin-bottom:20px">{verdict_desc}</p>

<div class="score-grid">
<div class="score-card"><div class="num" style="color:{verdict_color}">{_fmt_score(score)}</div><div class="lbl">Trust Score</div></div>
<div class="score-card"><div class="num">{_esc(rating)}</div><div class="lbl">Rating</div></div>
<div class="score-card"><div class="num" style="color:{'#dc2626' if crash_prob and crash_prob > 0.3 else '#ca8a04' if crash_prob and crash_prob > 0.1 else '#16a34a'}">{crash_pct}%</div><div class="lbl">Crash Risk</div></div>
<div class="score-card"><div class="num">{_esc(alert_level)}</div><div class="lbl">Alert Level</div></div>
</div>

<h2 style="font-size:1.1rem;margin:24px 0 8px">Is {_esc(name)} a Scam?</h2>
<p style="font-size:14px;color:#374151">Based on ZARQ's quantitative analysis, {_esc(name)} shows <strong>{structural_weakness}</strong> structural weakness signal{'s' if structural_weakness != 1 else ''}. {'No critical structural weaknesses detected — this is a positive sign.' if structural_weakness == 0 else 'Active structural weaknesses require careful monitoring.'} The Distance-to-Default stands at {_fmt_score(ndd_val) if ndd_val else 'N/A'}, indicating {_ndd_description(ndd_val).lower() if ndd_val else 'insufficient data for assessment'}.</p>

<h2 style="font-size:1.1rem;margin:24px 0 8px">Frequently Asked Questions</h2>
{faq_html}

{"<h2 style='font-size:1.1rem;margin:24px 0 8px'>Safer Alternatives</h2><p style='font-size:13px;color:#6b7280;margin-bottom:8px'>Higher-rated tokens in the same category:</p><div>" + alts_html + "</div>" if alts_html else ""}

<div style="margin-top:32px;padding:16px;border:1px solid #e5e7eb;background:#f9fafb">
<div style="font-weight:600;margin-bottom:8px">Check Any Token</div>
<p style="font-size:13px;color:#6b7280">Use ZARQ's API to check any token before investing:</p>
<pre style="background:#f5f5f5;padding:8px;font-size:12px;margin:8px 0;overflow-x:auto">curl zarq.ai/v1/preflight?target={slug}</pre>
<div style="font-size:12px;margin-top:8px"><a href="/tokens" style="color:var(--warm)">Browse all tokens</a> · <a href="/token/{slug}" style="color:var(--warm)">Full analysis</a> · <a href="/zarq/docs" style="color:var(--warm)">API docs</a></div>
</div>

<p style="margin-top:24px;font-size:12px;color:#6b7280"><strong>Disclaimer:</strong> ZARQ ratings are quantitative risk assessments, not investment advice. Always conduct your own research. Past performance does not predict future results.</p>
</div>
</body></html>'''

    @app.get("/safe/token/{slug}", response_class=HTMLResponse)
    async def safe_token_page(slug: str):
        """Safety-focused token page: 'Is X safe to buy?'"""
        _load_slugs()
        token_id = slug
        if token_id not in _slug_ids:
            return HTMLResponse(status_code=404, content="<h1>Token not found</h1>")
        slug_data = _slug_map.get(token_id, {})
        token_info = {"name": slug_data.get("name"), "symbol": slug_data.get("symbol"),
                      "tier": slug_data.get("tier"), "risk_grade": slug_data.get("risk_grade")}
        try:
            html = _render_safe_token_page(slug, token_id, token_info)
            if html is None:
                return HTMLResponse(status_code=404, content="<h1>Token not found</h1>")
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering safe token page {slug}: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    @app.get("/is-{slug}-safe-to-buy", response_class=HTMLResponse)
    async def is_token_safe_to_buy(slug: str):
        """SEO alias: /is-bitcoin-safe-to-buy → /safe/token/bitcoin"""
        _load_slugs()
        if slug in _slug_ids:
            return await safe_token_page(slug)
        return HTMLResponse(status_code=404, content="<h1>Token not found</h1>")

    # Sitemap for safe token pages
    @app.get("/sitemap-safe-tokens.xml", response_class=Response)
    async def sitemap_safe_tokens():
        _load_slugs()
        today = date.today().isoformat()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        count = 0
        for token_id, info in _slug_map.items():
            tier = info.get("tier", "T1")
            if tier not in ENABLED_TIERS:
                continue
            prio = "0.9" if tier == "T1" else "0.7"
            xml += f'  <url>\n    <loc>https://zarq.ai/safe/token/{token_id}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>{prio}</priority>\n  </url>\n'
            count += 1
            if count >= 500:
                break
        xml += '</urlset>'
        return Response(content=xml, media_type="application/xml")

    # Sitemap for token pages
    @app.get("/sitemap-tokens.xml", response_class=Response)
    async def sitemap_tokens():
        _load_slugs()
        today = date.today().isoformat()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

        # Hub page
        xml += f'  <url>\n    <loc>https://zarq.ai/tokens</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>1.0</priority>\n  </url>\n'
        # Vitality pages
        xml += f'  <url>\n    <loc>https://zarq.ai/vitality</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.9</priority>\n  </url>\n'
        xml += f'  <url>\n    <loc>https://zarq.ai/vitality/methodology</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>0.8</priority>\n  </url>\n'
        xml += f'  <url>\n    <loc>https://zarq.ai/vitality/backtest</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>0.8</priority>\n  </url>\n'

        # Individual token pages (only enabled tiers)
        for token_id, info in _slug_map.items():
            tier = info.get("tier", "T1")
            if tier not in ENABLED_TIERS:
                continue
            prio = "0.9" if tier == "T1" else "0.7" if tier == "T2" else "0.5"
            xml += f'  <url>\n    <loc>https://zarq.ai/token/{token_id}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>{prio}</priority>\n  </url>\n'

        xml += '</urlset>'
        return Response(content=xml, media_type="application/xml")

    enabled_count = sum(1 for v in _slug_map.values() if v.get("tier") in ENABLED_TIERS)
    logger.info(f"Mounted token pages: {enabled_count}/{len(_slug_map)} tokens (tiers {ENABLED_TIERS}), /tokens hub, /sitemap-tokens.xml")
