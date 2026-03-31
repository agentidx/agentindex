"""
The ZARQ Signal — Daily Crypto Risk Intelligence Feed
Route: /v1/signal/feed, /v1/signal/feed/history, /v1/signal/subscribe
HTML: /signal, /zarq-signal
Zero auth, zero rate limit.
"""

import os
import sqlite3
import time as _time_mod
from datetime import datetime, timezone

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

CRYPTO_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto", "crypto_trust.db")
API_LOG_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto", "zarq_api_log.db")

router_signal = APIRouter(tags=["signal"])

_signal_cache: dict = {"data": None, "ts": 0}
_SIGNAL_TTL = 3600  # 1 hour — signal data changes daily, no need for frequent refreshes


def _get_db():
    conn = sqlite3.connect(CRYPTO_DB)
    conn.row_factory = sqlite3.Row
    return conn


@router_signal.get("/v1/signal/feed")
def signal_feed(response: Response):
    """
    The ZARQ Signal — Live crypto risk intelligence feed.
    Returns all current signals sorted by severity.
    """
    if _signal_cache["data"] and (_time_mod.time() - _signal_cache["ts"]) < _SIGNAL_TTL:
        response.headers["Cache-Control"] = "public, max-age=300"
        return _signal_cache["data"]

    conn = _get_db()

    # Latest signal date
    sd = conn.execute("SELECT MAX(signal_date) as d FROM nerq_risk_signals").fetchone()["d"]
    if not sd:
        conn.close()
        return JSONResponse(status_code=503, content={"error": "Signal pipeline unavailable"})

    # Previous signal date for comparison
    prev_sd = conn.execute(
        "SELECT MAX(signal_date) as d FROM nerq_risk_signals WHERE signal_date < ?", (sd,)
    ).fetchone()["d"]

    # All current signals with rating data
    rows = conn.execute("""
        SELECT s.token_id, s.risk_level, s.trust_score, s.ndd_current,
               s.structural_weakness, s.structural_strength, s.drawdown_90d,
               s.weeks_since_ath, s.first_collapse_date, s.weeks_in_collapse,
               r.rating, r.symbol, r.name, r.price_usd, r.market_cap,
               r.price_change_24h, r.price_change_7d,
               c.crash_prob_v3
        FROM nerq_risk_signals s
        LEFT JOIN crypto_rating_daily r ON s.token_id = r.token_id
            AND r.run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
        LEFT JOIN (
            SELECT token_id, crash_prob_v3
            FROM crash_model_v3_predictions
            WHERE (token_id, date) IN (
                SELECT token_id, MAX(date) FROM crash_model_v3_predictions GROUP BY token_id
            )
        ) c ON s.token_id = c.token_id
        WHERE s.signal_date = ?
        ORDER BY
            CASE s.risk_level
                WHEN 'CRITICAL' THEN 0
                WHEN 'WARNING' THEN 1
                WHEN 'WATCH' THEN 2
                ELSE 3
            END,
            s.ndd_current ASC
    """, (sd,)).fetchall()

    # New signals (not in previous day or changed severity)
    new_signals = []
    resolved = []
    if prev_sd:
        prev_rows = conn.execute("""
            SELECT token_id, risk_level FROM nerq_risk_signals WHERE signal_date = ?
        """, (prev_sd,)).fetchall()
        prev_map = {r["token_id"]: r["risk_level"] for r in prev_rows}
        current_map = {r["token_id"]: r["risk_level"] for r in rows}

        for r in rows:
            tid = r["token_id"]
            if tid not in prev_map:
                new_signals.append(tid)
            elif prev_map[tid] != r["risk_level"] and r["risk_level"] in ("WARNING", "CRITICAL"):
                new_signals.append(tid)

        for tid, prev_level in prev_map.items():
            if prev_level in ("WARNING", "CRITICAL"):
                cur_level = current_map.get(tid, "SAFE")
                if cur_level in ("SAFE", "WATCH"):
                    resolved.append({"token_id": tid, "was": prev_level, "now": cur_level})

    conn.close()

    # Build signal list
    signals = []
    counts = {"CRITICAL": 0, "WARNING": 0, "WATCH": 0, "SAFE": 0}
    for r in rows:
        rl = r["risk_level"] or "SAFE"
        counts[rl] = counts.get(rl, 0) + 1
        signals.append({
            "token_id": r["token_id"],
            "name": r["name"] or r["token_id"].replace("-", " ").title(),
            "symbol": (r["symbol"] or "").upper(),
            "verdict": "CRITICAL" if rl == "CRITICAL" else ("WARNING" if rl == "WARNING" else "SAFE"),
            "risk_level": rl,
            "trust_score": round(float(r["trust_score"]), 2) if r["trust_score"] else None,
            "rating": r["rating"],
            "crash_probability": round(float(r["crash_prob_v3"]), 4) if r["crash_prob_v3"] else None,
            "distance_to_default": round(float(r["ndd_current"]), 2) if r["ndd_current"] else None,
            "structural_weakness": (r["structural_weakness"] or 0) >= 2,
            "drawdown_90d": round(float(r["drawdown_90d"]) * 100, 1) if r["drawdown_90d"] else None,
            "price_usd": r["price_usd"],
            "price_change_24h": round(float(r["price_change_24h"]), 2) if r["price_change_24h"] else None,
            "price_change_7d": round(float(r["price_change_7d"]), 2) if r["price_change_7d"] else None,
            "in_collapse": bool(r["first_collapse_date"]),
            "weeks_in_collapse": r["weeks_in_collapse"],
            "is_new": r["token_id"] in new_signals,
        })

    summary = (
        f"{counts.get('CRITICAL', 0)} tokens in structural collapse, "
        f"{counts.get('WARNING', 0)} in stress, "
        f"{counts.get('SAFE', 0) + counts.get('WATCH', 0)} stable"
    )

    result = {
        "signal_date": sd,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_tokens_monitored": len(signals),
            "active_warnings": counts.get("WARNING", 0),
            "active_criticals": counts.get("CRITICAL", 0),
            "safe_tokens": counts.get("SAFE", 0) + counts.get("WATCH", 0),
            "new_signals_24h": len(new_signals),
            "resolved_24h": len(resolved),
            "market_risk_summary": summary,
        },
        "signals": signals,
        "new_signals_24h": new_signals,
        "resolved_24h": resolved,
    }

    _signal_cache["data"] = result
    _signal_cache["ts"] = _time_mod.time()
    response.headers["Cache-Control"] = "public, max-age=300"
    return result


@router_signal.get("/v1/signal/feed/history")
def signal_feed_history(days: int = 30, response: Response = None):
    """Daily snapshots of signal counts over the last N days."""
    conn = _get_db()

    rows = conn.execute("""
        SELECT signal_date,
               COUNT(*) as total,
               SUM(CASE WHEN risk_level = 'CRITICAL' THEN 1 ELSE 0 END) as criticals,
               SUM(CASE WHEN risk_level = 'WARNING' THEN 1 ELSE 0 END) as warnings,
               SUM(CASE WHEN risk_level IN ('SAFE', 'WATCH') THEN 1 ELSE 0 END) as safe,
               AVG(trust_score) as avg_trust,
               AVG(ndd_current) as avg_ndd
        FROM nerq_risk_signals
        WHERE signal_date >= date((SELECT MAX(signal_date) FROM nerq_risk_signals), ?)
        GROUP BY signal_date
        ORDER BY signal_date DESC
    """, (f"-{days} days",)).fetchall()

    conn.close()

    snapshots = [{
        "date": r["signal_date"],
        "total_tokens": r["total"],
        "criticals": r["criticals"],
        "warnings": r["warnings"],
        "safe": r["safe"],
        "avg_trust_score": round(float(r["avg_trust"]), 1) if r["avg_trust"] else None,
        "avg_distance_to_default": round(float(r["avg_ndd"]), 2) if r["avg_ndd"] else None,
    } for r in rows]

    if response:
        response.headers["Cache-Control"] = "public, max-age=3600"
    return {"days": days, "snapshots": snapshots}


class SubscribeRequest(BaseModel):
    email: Optional[str] = None
    webhook_url: Optional[str] = None
    severity: Optional[str] = "WARNING"  # WARNING or CRITICAL


@router_signal.get("/v1/signal/subscribe")
def signal_subscribe_info():
    """Info about subscribing to ZARQ signals."""
    return {
        "info": "POST to this endpoint to register for signal notifications (coming soon).",
        "method": "POST",
        "body": {"email": "your@email.com", "webhook_url": "https://...", "severity": "WARNING|CRITICAL"},
        "status": "Registrations are stored but notifications are not sent yet.",
    }


@router_signal.post("/v1/signal/subscribe")
def signal_subscribe(req: SubscribeRequest):
    """Register for signal notifications (stores only, doesn't send yet)."""
    if not req.email and not req.webhook_url:
        return JSONResponse(status_code=400, content={"error": "Provide email or webhook_url"})

    try:
        db_path = API_LOG_DB
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                webhook_url TEXT,
                severity TEXT DEFAULT 'WARNING',
                created_at TEXT DEFAULT (datetime('now')),
                is_active INTEGER DEFAULT 1
            )
        """)
        conn.execute(
            "INSERT INTO signal_subscribers (email, webhook_url, severity) VALUES (?, ?, ?)",
            (req.email, req.webhook_url, req.severity or "WARNING")
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Best effort — don't break the endpoint

    return {
        "status": "registered",
        "message": "You'll be notified when signal notifications go live.",
        "severity": req.severity,
    }


# ── HTML Page ──

@router_signal.get("/signal", response_class=HTMLResponse)
@router_signal.get("/zarq-signal", response_class=HTMLResponse)
def signal_page():
    return HTMLResponse(_render_signal_page())


def _render_signal_page() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The ZARQ Signal — Daily Crypto Risk Intelligence</title>
<meta name="description" content="Live crypto risk feed: structural collapse warnings, trust scores, and crash probability for 205 tokens. Updated daily, free, no signup.">
<meta property="og:title" content="The ZARQ Signal — Daily Crypto Risk Intelligence">
<meta property="og:description" content="Live structural collapse warnings, trust scores, and crash probability for 205 crypto tokens.">
<meta property="og:url" content="https://zarq.ai/signal">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="https://zarq.ai/signal">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
    --warm: #c2956b; --warm-light: #f5ebe0; --bg: #fafaf8; --card-bg: #fff;
    --text: #1a1a1a; --text-secondary: #6b7280; --border: #e5e7eb;
    --green: #059669; --red: #dc2626; --yellow: #d97706; --blue: #2563eb;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'DM Sans', -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }
.container { max-width: 900px; margin: 0 auto; padding: 0 24px; }
header { background: #fff; border-bottom: 1px solid var(--border); padding: 32px 0; text-align: center; }
header h1 { font-family: 'DM Serif Display', Georgia, serif; font-size: 2rem; font-weight: 400; }
header h1 span { color: var(--warm); }
header p { color: var(--text-secondary); margin-top: 8px; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 24px 0; }
.stat-card {
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px; text-align: center;
}
.stat-card .num { font-size: 1.8rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
.stat-card .lbl { font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px; }
.filters { margin: 16px 0; display: flex; gap: 8px; flex-wrap: wrap; }
.filters button {
    padding: 6px 16px; border: 1px solid var(--border); border-radius: 20px;
    background: #fff; cursor: pointer; font-size: 0.85rem; font-family: 'DM Sans', sans-serif;
}
.filters button.active { background: var(--warm); color: #fff; border-color: var(--warm); }
table { width: 100%; border-collapse: collapse; margin: 16px 0; background: var(--card-bg); border-radius: 10px; overflow: hidden; border: 1px solid var(--border); }
th { background: #f9fafb; font-weight: 600; font-size: 0.8rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #f3f4f6; }
td { font-size: 0.9rem; }
tr:last-child td { border: none; }
tr.new-signal { background: #fffbeb; }
.pill { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
.pill-critical { background: #fee2e2; color: #991b1b; }
.pill-warning { background: #fef3c7; color: #92400e; }
.pill-safe { background: #d1fae5; color: #065f46; }
.pill-watch { background: #e0e7ff; color: #3730a3; }
.risk-summary { padding: 16px; background: var(--warm-light); border-radius: 10px; margin: 16px 0; font-size: 0.95rem; }
.mono { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; }
.refresh { color: var(--text-secondary); font-size: 0.8rem; text-align: center; margin: 8px 0; }
footer { text-align: center; padding: 32px 0; color: var(--text-secondary); font-size: 0.85rem; }
footer a { color: var(--warm); text-decoration: none; }
@media (max-width: 600px) { td, th { padding: 6px 8px; font-size: 0.8rem; } }
</style>
</head>
<body>
<header>
    <div class="container">
        <h1>The <span>ZARQ</span> Signal</h1>
        <p>Daily Crypto Risk Intelligence — 205 tokens monitored</p>
    </div>
</header>
<main class="container">
    <div id="feed"><div style="text-align:center;padding:40px;color:var(--text-secondary)">Loading signals...</div></div>
</main>
<footer>
    <div class="container">
        <p>Powered by <a href="https://zarq.ai">ZARQ</a> | <a href="/kya">Know Your Agent</a> | <a href="/zarq/docs">API Docs</a> | <a href="/demo/save-simulator">Save Simulator</a> | <a href="/v1/signal/feed">API: GET /v1/signal/feed</a></p>
    </div>
</footer>
<script>
let allSignals = [];
let currentFilter = 'ALL';

async function loadFeed() {
    try {
        const r = await fetch('/v1/signal/feed');
        if (!r.ok) { document.getElementById('feed').innerHTML = '<p style="color:var(--red);text-align:center">Failed to load</p>'; return; }
        const d = await r.json();
        allSignals = d.signals;
        renderFeed(d);
    } catch(e) {
        document.getElementById('feed').innerHTML = '<p style="color:var(--red);text-align:center">Error loading feed</p>';
    }
}

function renderFeed(d) {
    const s = d.summary;
    let html = `
    <div class="summary-grid">
        <div class="stat-card"><div class="num">${s.total_tokens_monitored}</div><div class="lbl">Tokens Monitored</div></div>
        <div class="stat-card"><div class="num" style="color:var(--red)">${s.active_criticals}</div><div class="lbl">Critical</div></div>
        <div class="stat-card"><div class="num" style="color:var(--yellow)">${s.active_warnings}</div><div class="lbl">Warning</div></div>
        <div class="stat-card"><div class="num" style="color:var(--green)">${s.safe_tokens}</div><div class="lbl">Stable</div></div>
        <div class="stat-card"><div class="num">${s.new_signals_24h}</div><div class="lbl">New (24h)</div></div>
        <div class="stat-card"><div class="num">${s.resolved_24h}</div><div class="lbl">Resolved (24h)</div></div>
    </div>
    <div class="risk-summary">${s.market_risk_summary}</div>
    <div class="filters">
        <button class="${currentFilter==='ALL'?'active':''}" onclick="filterSignals('ALL')">All</button>
        <button class="${currentFilter==='CRITICAL'?'active':''}" onclick="filterSignals('CRITICAL')">Critical</button>
        <button class="${currentFilter==='WARNING'?'active':''}" onclick="filterSignals('WARNING')">Warning</button>
        <button class="${currentFilter==='SAFE'?'active':''}" onclick="filterSignals('SAFE')">Safe</button>
    </div>`;

    const filtered = currentFilter === 'ALL' ? allSignals : allSignals.filter(s => s.verdict === currentFilter || (currentFilter === 'SAFE' && s.verdict === 'SAFE'));

    html += `<table>
    <thead><tr>
        <th>Token</th><th>Verdict</th><th>Trust</th><th>Rating</th><th>DtD</th><th>Crash %</th><th>24h</th>
    </tr></thead><tbody>`;

    for (const sig of filtered) {
        const pillClass = sig.verdict === 'CRITICAL' ? 'pill-critical' : sig.verdict === 'WARNING' ? 'pill-warning' : 'pill-safe';
        const rowClass = sig.is_new ? 'new-signal' : '';
        const change = sig.price_change_24h != null ? (sig.price_change_24h >= 0 ? '+' : '') + sig.price_change_24h.toFixed(1) + '%' : '—';
        const changeColor = sig.price_change_24h >= 0 ? 'var(--green)' : 'var(--red)';
        html += `<tr class="${rowClass}">
            <td><strong>${sig.name}</strong><br><span class="mono" style="color:var(--text-secondary);font-size:0.75rem">${sig.symbol}</span></td>
            <td><span class="pill ${pillClass}">${sig.verdict}</span>${sig.is_new ? ' <span style="color:var(--yellow);font-size:0.7rem">NEW</span>' : ''}${sig.in_collapse ? ' <span style="color:var(--red);font-size:0.7rem">COLLAPSE</span>' : ''}</td>
            <td class="mono">${sig.trust_score ?? '—'}</td>
            <td class="mono">${sig.rating ?? '—'}</td>
            <td class="mono">${sig.distance_to_default ?? '—'}</td>
            <td class="mono">${sig.crash_probability != null ? (sig.crash_probability * 100).toFixed(1) + '%' : '—'}</td>
            <td class="mono" style="color:${changeColor}">${change}</td>
        </tr>`;
    }
    html += '</tbody></table>';
    html += `<div class="refresh">Signal date: ${d.signal_date} | Auto-refreshes every 60s | <span class="mono">${d.generated_at.substring(11,19)} UTC</span></div>`;

    document.getElementById('feed').innerHTML = html;
}

function filterSignals(level) {
    currentFilter = level;
    // Re-render with current data
    loadFeed();
}

loadFeed();
setInterval(loadFeed, 60000);
</script>
</body>
</html>"""
