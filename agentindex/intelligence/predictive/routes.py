"""
Nerq Predictive Intelligence — Routes & API
=============================================
- GET /v1/intelligence/predict/{tool} — Full prediction JSON
- GET /v1/intelligence/predictions — Top predictions overview JSON
- GET /v1/intelligence/ai-interest — AI Interest Index JSON
- GET /v1/intelligence/fragile — Most fragile popular tools JSON
- GET /v1/intelligence/accuracy — Calibration report JSON
- GET /predict/{tool} — Individual prediction page (HTML)
- GET /predictions — Hub page (HTML)

Usage:
    from agentindex.intelligence.predictive.routes import mount_predictive_routes
    mount_predictive_routes(app)
"""

import html as html_mod
import json
import logging
import re
import time
from datetime import date

from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.predictive.routes")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
MONTH_YEAR = date.today().strftime("%B %Y")
YEAR = date.today().year
DISCLAIMER = "Nerq Predictive Intelligence v0.1 — Early signals. Accuracy improves with data. Not investment advice."

_cache = {}
CACHE_TTL = 1800


def _cached(key):
    e = _cache.get(key)
    if e and (time.time() - e[0]) < CACHE_TTL:
        return e[1]
    return None


def _set_cache(key, val):
    _cache[key] = (time.time(), val)
    return val


def _esc(t):
    return html_mod.escape(str(t)) if t else ""


def _to_slug(name):
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _phase_color(phase):
    return {"emerging": "#8b5cf6", "growing": "#16a34a", "mature": "#0d9488",
            "declining": "#f59e0b", "abandoned": "#dc2626"}.get(phase, "#6b7280")


def _phase_emoji(phase):
    return {"emerging": "&#x1F331;", "growing": "&#x1F680;", "mature": "&#x2705;",
            "declining": "&#x26A0;", "abandoned": "&#x274C;"}.get(phase, "")


def mount_predictive_routes(app):
    """Mount all predictive intelligence routes."""

    # ════════════════════════════════════════════
    # API ENDPOINTS (JSON)
    # ════════════════════════════════════════════

    @app.get("/v1/intelligence/predict/{tool}")
    async def api_predict_tool(tool: str):
        session = get_session()
        try:
            t = tool.lower().strip()
            p = "%" + t.replace("-", "%") + "%"
            row = session.execute(text("""
                SELECT p.agent_name, p.adoption_phase, p.adoption_confidence,
                       p.fragility_index, p.fragility_reasoning,
                       p.ai_recommendation_prob, p.survival_30d_prob,
                       p.nerq_predictive_index, p.reasoning, p.predicted_at
                FROM predictions p
                JOIN agents a ON p.agent_id = a.id
                WHERE (LOWER(a.name) = :q OR LOWER(a.name) LIKE :p)
                ORDER BY p.predicted_at DESC
                LIMIT 1
            """), {"q": t, "p": p}).fetchone()

            if not row:
                return JSONResponse({"error": "No predictions found for this tool", "tool": tool}, status_code=404)

            return {
                "tool": row[0],
                "predicted_at": str(row[9]),
                "adoption": {"phase": row[1], "confidence": row[2]},
                "fragility": {"index": row[3], "reasoning": row[4]},
                "ai_recommendation_probability": row[5],
                "survival_30d_probability": row[6],
                "nerq_predictive_index": row[7],
                "reasoning": json.loads(row[8]) if row[8] else {},
                "disclaimer": DISCLAIMER,
            }
        finally:
            session.close()

    @app.get("/v1/intelligence/predictions")
    async def api_predictions():
        session = get_session()
        try:
            today = date.today().isoformat()
            # Top breakouts (high NPI + emerging/growing)
            breakouts = session.execute(text("""
                SELECT agent_name, nerq_predictive_index, adoption_phase,
                       fragility_index, ai_recommendation_prob, survival_30d_prob
                FROM predictions
                WHERE predicted_at = (SELECT MAX(predicted_at) FROM predictions)
                AND adoption_phase IN ('emerging', 'growing')
                ORDER BY nerq_predictive_index DESC NULLS LAST
                LIMIT 20
            """)).fetchall()

            # Health warnings (declining + fragile)
            warnings = session.execute(text("""
                SELECT agent_name, nerq_predictive_index, adoption_phase,
                       fragility_index, fragility_reasoning
                FROM predictions
                WHERE predicted_at = (SELECT MAX(predicted_at) FROM predictions)
                AND (fragility_index > 50 OR adoption_phase IN ('declining', 'abandoned'))
                ORDER BY fragility_index DESC NULLS LAST
                LIMIT 20
            """)).fetchall()

            return {
                "date": today,
                "breakouts": [{"name": r[0], "npi": r[1], "phase": r[2],
                              "fragility": r[3], "ai_prob": r[4], "survival": r[5]} for r in breakouts],
                "health_warnings": [{"name": r[0], "npi": r[1], "phase": r[2],
                                    "fragility": r[3], "reason": r[4]} for r in warnings],
                "disclaimer": DISCLAIMER,
            }
        finally:
            session.close()

    @app.get("/v1/intelligence/ai-interest")
    async def api_ai_interest():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT s.agent_name, s.ai_attention_score, s.ai_attention_delta_7d,
                       s.signals_json
                FROM prediction_signals s
                WHERE s.calculated_at = (SELECT MAX(calculated_at) FROM prediction_signals)
                AND s.ai_attention_score > 0
                ORDER BY s.ai_attention_score DESC
                LIMIT 50
            """)).fetchall()

            return {
                "title": "AI Interest Index — What AI Systems Are Watching",
                "count": len(rows),
                "tools": [{"name": r[0], "ai_attention_score": r[1],
                          "ai_attention_delta_7d": r[2],
                          "trending": (r[2] or 0) > 0} for r in rows],
                "disclaimer": DISCLAIMER,
            }
        finally:
            session.close()

    @app.get("/v1/intelligence/fragile")
    async def api_fragile():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT agent_name, fragility_index, fragility_reasoning,
                       nerq_predictive_index, adoption_phase
                FROM predictions
                WHERE predicted_at = (SELECT MAX(predicted_at) FROM predictions)
                AND fragility_index > 30
                ORDER BY fragility_index DESC
                LIMIT 50
            """)).fetchall()

            return {
                "title": "Most Fragile Popular Tools",
                "count": len(rows),
                "tools": [{"name": r[0], "fragility": r[1], "reasoning": r[2],
                          "npi": r[3], "phase": r[4]} for r in rows],
                "disclaimer": DISCLAIMER,
            }
        finally:
            session.close()

    @app.get("/v1/intelligence/accuracy")
    async def api_accuracy():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT prediction_type, accuracy_pct, predictions_evaluated, details, calibrated_at
                FROM prediction_calibration
                ORDER BY calibrated_at DESC
                LIMIT 20
            """)).fetchall()

            return {
                "title": "Prediction Accuracy Report",
                "calibrations": [{"type": r[0], "accuracy_pct": r[1],
                                 "evaluated": r[2], "details": json.loads(r[3]) if r[3] else {},
                                 "date": str(r[4])} for r in rows],
                "note": "Calibration requires 7+ days of observations. Accuracy improves over time.",
            }
        finally:
            session.close()

    # ════════════════════════════════════════════
    # HTML PAGES
    # ════════════════════════════════════════════

    @app.get("/predict/{tool}", response_class=HTMLResponse)
    async def predict_page(tool: str):
        ck = f"predict:{tool}"
        c = _cached(ck)
        if c:
            return HTMLResponse(c)

        session = get_session()
        try:
            t = tool.lower().strip()
            p = "%" + t.replace("-", "%") + "%"
            row = session.execute(text("""
                SELECT p.agent_name, p.adoption_phase, p.adoption_confidence,
                       p.fragility_index, p.fragility_reasoning,
                       p.ai_recommendation_prob, p.survival_30d_prob,
                       p.nerq_predictive_index, p.reasoning, p.predicted_at,
                       a.stars, a.trust_score_v2, a.trust_grade, a.description, a.category
                FROM predictions p
                JOIN agents a ON p.agent_id = a.id
                WHERE (LOWER(a.name) = :q OR LOWER(a.name) LIKE :p) AND a.is_active = true
                ORDER BY p.predicted_at DESC
                LIMIT 1
            """), {"q": t, "p": p}).fetchone()

            if not row:
                try:
                    from agentindex.agent_safety_pages import _queue_for_crawling
                    _queue_for_crawling(tool, bot="404-route")
                except Exception:
                    pass
                return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

            name = row[0]
            short = name.split("/")[-1] if "/" in name else name
            phase = row[1]
            phase_conf = row[2] or 0
            frag = row[3] or 0
            frag_reason = row[4] or "None detected"
            ai_prob = row[5] or 0
            surv = row[6] or 0
            npi = row[7] or 0
            stars = row[10] or 0
            trust = row[11] or 0
            grade = row[12] or "D"
            desc = row[13] or ""
            category = row[14] or ""
            reasoning = row[8] if isinstance(row[8], dict) else (json.loads(row[8]) if row[8] else {})

            pc = _phase_color(phase)
            pe = _phase_emoji(phase)
            canonical = f"{SITE}/predict/{_to_slug(name)}"

            title = f"{_esc(short)} Prediction — AI Tool Forecast {YEAR} | Nerq"
            meta_desc = f"{_esc(short)}: NPI {npi:.0f}/100. Phase: {phase}. Fragility: {frag:.0f}. AI recommendation: {ai_prob*100:.0f}%. 30-day survival: {surv*100:.0f}%."

            faq_items = [
                (f"Is {_esc(short)} growing or dying?", f"{_esc(short)} is in the '{phase}' phase with {phase_conf*100:.0f}% confidence. Star velocity: {reasoning.get('signals_summary',{}).get('star_velocity','N/A')}/week."),
                (f"Will {_esc(short)} survive the next 30 days?", f"Our model estimates a {surv*100:.0f}% probability of continued active maintenance in 30 days."),
                (f"Should I adopt {_esc(short)}?", f"Nerq Predictive Index: {npi:.0f}/100. Fragility: {frag:.0f}/100. {'Low fragility, safe to adopt.' if frag < 30 else 'Moderate fragility — evaluate alternatives.' if frag < 60 else 'High fragility — significant risk.'}"),
                (f"Do AI systems recommend {_esc(short)}?", f"AI recommendation probability: {ai_prob*100:.0f}%. {'AI systems actively cite this tool.' if ai_prob > 0.3 else 'Limited AI visibility.'}"),
            ]
            faq_html = "".join(f'<div style="border-bottom:1px solid #e5e7eb;padding:12px 0"><div style="font-weight:600;font-size:14px">{q}</div><div style="font-size:13px;color:#374151;margin-top:6px">{a}</div></div>' for q, a in faq_items)
            faq_jsonld = ",".join(f'{{"@type":"Question","name":"{q}","acceptedAnswer":{{"@type":"Answer","text":"{a}"}}}}' for q, a in faq_items)

            html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(meta_desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(meta_desc)}">
<meta name="nerq:type" content="prediction">
<meta name="nerq:tools" content="{_esc(name)}">
<meta name="nerq:verdict" content="NPI {npi:.0f}/100 — {phase}">
<meta name="nerq:updated" content="{TODAY}">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{faq_jsonld}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Dataset","name":"{_esc(short)} Predictive Analysis","description":"Adoption, fragility, and AI recommendation predictions for {_esc(short)}","variableMeasured":[{{"@type":"PropertyValue","name":"NPI","value":"{npi:.0f}","unitText":"out of 100"}},{{"@type":"PropertyValue","name":"Fragility","value":"{frag:.0f}"}},{{"@type":"PropertyValue","name":"Survival 30d","value":"{surv*100:.0f}%"}}]}}
</script>
{NERQ_CSS}
<style>
.pred-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}}
.pred-card{{padding:16px;border:1px solid #e5e7eb;text-align:center}}
.pred-card .num{{font-size:24px;font-weight:700;font-family:ui-monospace,monospace}}
.pred-card .lbl{{font-size:11px;color:#6b7280;text-transform:uppercase;margin-top:4px}}
</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:900px;margin:0 auto;padding:24px">
<nav style="font-size:12px;color:#6b7280;margin-bottom:16px"><a href="/" style="color:#0d9488">Nerq</a> &rsaquo; <a href="/predictions" style="color:#0d9488">Predictions</a> &rsaquo; {_esc(short)}</nav>

<h1>{_esc(short)} — Predictive Intelligence {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 16px">{_esc(short)} has a Nerq Predictive Index of <strong>{npi:.0f}/100</strong>. Phase: <strong style="color:{pc}">{pe} {phase.title()}</strong>. Fragility: {frag:.0f}/100. AI recommendation probability: {ai_prob*100:.0f}%. 30-day survival: {surv*100:.0f}%. Last analyzed {MONTH_YEAR}.</p>

<div class="pred-grid">
<div class="pred-card"><div class="num" style="color:{'#16a34a' if npi >= 70 else '#ca8a04' if npi >= 40 else '#dc2626'}">{npi:.0f}</div><div class="lbl">Predictive Index</div></div>
<div class="pred-card"><div class="num" style="color:{pc}">{phase.title()}</div><div class="lbl">Adoption Phase</div></div>
<div class="pred-card"><div class="num" style="color:{'#16a34a' if frag < 30 else '#ca8a04' if frag < 60 else '#dc2626'}">{frag:.0f}</div><div class="lbl">Fragility</div></div>
<div class="pred-card"><div class="num">{surv*100:.0f}%</div><div class="lbl">30-Day Survival</div></div>
</div>

<h2>Adoption Trajectory</h2>
<p style="font-size:14px;color:#374151">{_esc(short)} is in the <strong style="color:{pc}">{phase}</strong> phase ({phase_conf*100:.0f}% confidence). {"This tool is gaining momentum and attracting new users." if phase in ("emerging","growing") else "Growth is stable." if phase == "mature" else "This tool shows signs of declining interest." if phase == "declining" else "This tool appears to be no longer maintained."}</p>

<h2>Fragility Analysis</h2>
<p style="font-size:14px;color:#374151">Fragility Index: <strong>{frag:.0f}/100</strong>. {"Low fragility — this tool has robust foundations." if frag < 30 else "Moderate fragility — some risk factors present." if frag < 60 else "High fragility — significant risk of disruption."}</p>
<p style="font-size:13px;color:#6b7280">Risk factors: {_esc(frag_reason)}</p>

<h2>AI Recommendation Probability</h2>
<p style="font-size:14px;color:#374151">There is a <strong>{ai_prob*100:.0f}%</strong> probability that AI systems (ChatGPT, Perplexity, Claude) will cite {_esc(short)} in the next 7 days. {"AI systems actively recommend this tool." if ai_prob > 0.3 else "Limited AI visibility — this tool is not frequently cited by AI systems."}</p>

<h2>30-Day Survival</h2>
<p style="font-size:14px;color:#374151">Estimated <strong>{surv*100:.0f}%</strong> probability of continued active maintenance over the next 30 days.</p>

<h2>Frequently Asked Questions</h2>
{faq_html}

<div style="margin-top:24px;padding:16px;background:#f9fafb;border:1px solid #e5e7eb">
<pre style="background:#f5f5f5;padding:8px;font-size:12px;overflow-x:auto">curl nerq.ai/v1/intelligence/predict/{_to_slug(name)}</pre>
<div style="font-size:12px;margin-top:8px"><a href="/safe/{_to_slug(name)}" style="color:#0d9488">Safety Report</a> &middot; <a href="/predictions" style="color:#0d9488">All Predictions</a> &middot; <a href="/trending" style="color:#0d9488">Trending</a> &middot; <a href="/leaderboard" style="color:#0d9488">Leaderboard</a></div>
</div>

<p style="font-size:12px;color:#6b7280;margin-top:24px"><strong>{DISCLAIMER}</strong></p>
</main>
{NERQ_FOOTER}
</body></html>"""

            _set_cache(ck, html)
            return HTMLResponse(html)
        finally:
            session.close()

    @app.get("/predictions", response_class=HTMLResponse)
    async def predictions_hub():
        c = _cached("predictions_hub")
        if c:
            return HTMLResponse(c)

        session = get_session()
        try:
            # Top NPI tools
            top = session.execute(text("""
                SELECT agent_name, nerq_predictive_index, adoption_phase,
                       fragility_index, ai_recommendation_prob, survival_30d_prob
                FROM predictions
                WHERE predicted_at = (SELECT MAX(predicted_at) FROM predictions)
                ORDER BY nerq_predictive_index DESC NULLS LAST
                LIMIT 50
            """)).fetchall()

            # Health warnings
            warnings = session.execute(text("""
                SELECT agent_name, fragility_index, adoption_phase, fragility_reasoning
                FROM predictions
                WHERE predicted_at = (SELECT MAX(predicted_at) FROM predictions)
                AND fragility_index > 50
                ORDER BY fragility_index DESC
                LIMIT 20
            """)).fetchall()

            # Accuracy
            acc = session.execute(text("""
                SELECT prediction_type, accuracy_pct, calibrated_at
                FROM prediction_calibration
                ORDER BY calibrated_at DESC
                LIMIT 4
            """)).fetchall()

            total_preds = session.execute(text("SELECT COUNT(*) FROM predictions WHERE predicted_at = (SELECT MAX(predicted_at) FROM predictions)")).scalar() or 0

            top_html = ""
            for r in top:
                short = r[0].split("/")[-1] if "/" in r[0] else r[0]
                pc = _phase_color(r[2])
                top_html += f'<tr><td><a href="/predict/{_to_slug(r[0])}" style="color:#0d9488">{_esc(short)}</a></td><td style="font-weight:700">{(r[1] or 0):.0f}</td><td style="color:{pc}">{(r[2] or "?").title()}</td><td>{(r[3] or 0):.0f}</td><td>{(r[4] or 0)*100:.0f}%</td><td>{(r[5] or 0)*100:.0f}%</td></tr>'

            warn_html = ""
            for r in warnings:
                short = r[0].split("/")[-1] if "/" in r[0] else r[0]
                warn_html += f'<tr><td><a href="/predict/{_to_slug(r[0])}" style="color:#dc2626">{_esc(short)}</a></td><td style="color:#dc2626;font-weight:700">{(r[1] or 0):.0f}</td><td>{(r[2] or "?").title()}</td><td style="font-size:12px">{_esc(r[3] or "")[:80]}</td></tr>'

            acc_html = ""
            for r in acc:
                acc_html += f'<tr><td>{_esc(r[0])}</td><td>{r[1]:.1f}%</td><td>{r[2]}</td></tr>' if r[1] is not None else f'<tr><td>{_esc(r[0])}</td><td>Pending</td><td>{r[2]}</td></tr>'

            html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Tool Predictions — Adoption, Risk & Forecasts {YEAR} | Nerq</title>
<meta name="description" content="Nerq Predictive Intelligence: adoption forecasts, fragility analysis, and AI recommendation probabilities for {total_preds:,} AI tools.">
<link rel="canonical" href="{SITE}/predictions">
<meta name="nerq:type" content="predictions_hub">
<meta name="nerq:updated" content="{TODAY}">
{NERQ_CSS}
<style>
table{{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}}
th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280;font-weight:600}}
td{{padding:8px;border-bottom:1px solid #e5e7eb}}
</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:1000px;margin:0 auto;padding:24px">
<h1>AI Tool Predictions — Nerq Predictive Intelligence {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 16px">Adoption forecasts, fragility analysis, and AI recommendation probabilities for {total_preds:,} AI tools. Updated daily. Predictions based on star velocity, AI crawler activity, maintenance signals, and ecosystem health.</p>

<h2>Tools to Watch (Highest NPI)</h2>
<table>
<tr><th>Tool</th><th>NPI</th><th>Phase</th><th>Fragility</th><th>AI Prob</th><th>Survival</th></tr>
{top_html if top_html else '<tr><td colspan="6" style="color:#6b7280">Collecting data — predictions available after 2 days of observations.</td></tr>'}
</table>

<h2 style="color:#dc2626">Health Warnings (Fragility &gt; 50)</h2>
<table>
<tr><th>Tool</th><th>Fragility</th><th>Phase</th><th>Risk Factors</th></tr>
{warn_html if warn_html else '<tr><td colspan="4" style="color:#6b7280">No high-fragility tools detected yet.</td></tr>'}
</table>

{"<h2>Prediction Accuracy</h2><table><tr><th>Type</th><th>Accuracy</th><th>Date</th></tr>" + acc_html + "</table>" if acc_html else ""}

<div style="margin-top:24px;padding:16px;background:#f9fafb;border:1px solid #e5e7eb;font-size:13px">
<div style="font-weight:600;margin-bottom:8px">API Endpoints</div>
<code>GET /v1/intelligence/predictions</code> — Top predictions<br>
<code>GET /v1/intelligence/predict/{{tool}}</code> — Individual tool<br>
<code>GET /v1/intelligence/ai-interest</code> — AI Interest Index<br>
<code>GET /v1/intelligence/fragile</code> — Most fragile tools<br>
<code>GET /v1/intelligence/accuracy</code> — Calibration report
</div>

<p style="font-size:12px;color:#6b7280;margin-top:24px"><strong>{DISCLAIMER}</strong></p>
</main>
{NERQ_FOOTER}
</body></html>"""

            _set_cache("predictions_hub", html)
            return HTMLResponse(html)
        finally:
            session.close()

    logger.info("Mounted predictive intelligence routes: /predict/{tool}, /predictions, /v1/intelligence/*")
