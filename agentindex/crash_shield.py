"""
ZARQ Crash Shield — Sprint 4
Detects verified "saves" where ZARQ warned before a crash, exposes via API,
and provides webhook subscriptions for real-time alerts.
"""

import hashlib
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("zarq.crash_shield")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto", "crypto_trust.db")

router_crash_shield = APIRouter(tags=["crash-shield"])


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_saves_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS crash_shield_saves (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        save_id TEXT UNIQUE NOT NULL,
        token_id TEXT NOT NULL,
        symbol TEXT,
        name TEXT,
        warning_date TEXT NOT NULL,
        warning_price REAL,
        crash_date TEXT NOT NULL,
        crash_price REAL,
        drop_percent REAL NOT NULL,
        crash_prob_at_warning REAL,
        sha256_hash TEXT NOT NULL,
        detected_at TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_css_token ON crash_shield_saves(token_id)")
    conn.commit()
    conn.close()


_init_saves_table()


# ─── Core Logic ───

def check_for_new_saves(min_prob: float = 0.5, min_drop: float = 0.30) -> list[dict]:
    """
    Find tokens where ZARQ warned (crash_prob > min_prob) and that subsequently
    dropped > min_drop (30%). Cross-references crash_model_v3_predictions with
    crypto_price_history. Only considers OOS predictions.
    Returns list of newly detected saves.
    """
    conn = _get_db()

    # Find warnings: high crash probability predictions (OOS only)
    warnings = conn.execute("""
        SELECT p.token_id, p.date as warning_date, p.crash_prob_v3, p.max_drawdown,
               pw.close as warning_price,
               n.symbol, n.name
        FROM crash_model_v3_predictions p
        LEFT JOIN crypto_price_history pw ON p.token_id = pw.token_id AND pw.date = p.date
        LEFT JOIN crypto_ndd_daily n ON p.token_id = n.token_id
            AND n.run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)
        WHERE p.crash_prob_v3 > ? AND p.period = 'OOS'
            AND p.max_drawdown < ?
            AND pw.close IS NOT NULL AND pw.close > 0
        GROUP BY p.token_id
        ORDER BY p.max_drawdown ASC
    """, (min_prob, -min_drop)).fetchall()

    # Check which saves we already have
    existing = set()
    for row in conn.execute("SELECT token_id, warning_date FROM crash_shield_saves").fetchall():
        existing.add((row["token_id"], row["warning_date"]))

    new_saves = []
    for w in warnings:
        token_id = w["token_id"]
        warning_date = w["warning_date"]

        if (token_id, warning_date) in existing:
            continue

        # Find the lowest price within 90 days after warning
        bottom = conn.execute("""
            SELECT date, close FROM crypto_price_history
            WHERE token_id = ? AND date > ? AND date <= date(?, '+90 days')
                AND close IS NOT NULL AND close > 0
            ORDER BY close ASC
            LIMIT 1
        """, (token_id, warning_date, warning_date)).fetchone()

        if not bottom:
            continue

        warning_price = w["warning_price"]
        crash_price = bottom["close"]
        drop = (warning_price - crash_price) / warning_price

        if drop < min_drop:
            continue

        # This is a verified save
        save_data = {
            "token_id": token_id,
            "warning_date": warning_date,
            "crash_date": bottom["date"],
            "warning_price": warning_price,
            "crash_price": crash_price,
            "drop_percent": round(drop * 100, 1),
            "crash_prob": w["crash_prob_v3"],
        }
        sha = hashlib.sha256(json.dumps(save_data, sort_keys=True).encode()).hexdigest()[:16]
        save_id = f"save-{token_id[:12]}-{sha[:8]}"

        conn.execute("""
            INSERT OR IGNORE INTO crash_shield_saves
            (save_id, token_id, symbol, name, warning_date, warning_price,
             crash_date, crash_price, drop_percent, crash_prob_at_warning,
             sha256_hash, detected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            save_id, token_id, w["symbol"], w["name"],
            warning_date, warning_price,
            bottom["date"], crash_price, round(drop * 100, 1),
            w["crash_prob_v3"], sha,
            datetime.now(timezone.utc).isoformat(),
        ))

        new_saves.append({
            "save_id": save_id,
            "token_id": token_id,
            "symbol": w["symbol"],
            "name": w["name"],
            **save_data,
        })

    conn.commit()
    conn.close()
    logger.info("Crash shield: %d new saves detected", len(new_saves))
    return new_saves


def get_saves(limit: int = 50) -> list[dict]:
    """Return all verified saves, most dramatic first."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT * FROM crash_shield_saves
        ORDER BY drop_percent DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── API Endpoints ───

@router_crash_shield.get("/v1/crash-shield/saves")
def api_saves(response: Response, limit: int = 50):
    """All verified saves — cases where ZARQ warned before a crash."""
    saves = get_saves(limit)
    for s in saves:
        if s.get("warning_price") and s.get("crash_price"):
            s["saved_per_1000_usd"] = round(1000 * (1 - s["crash_price"] / s["warning_price"]), 2)
            days = 0
            try:
                from datetime import date as _d
                w = _d.fromisoformat(s["warning_date"])
                c = _d.fromisoformat(s["crash_date"])
                days = (c - w).days
            except Exception:
                pass
            s["days_lead_time"] = days
    response.headers["Cache-Control"] = "public, max-age=3600"
    return {"saves": saves, "total": len(saves)}


@router_crash_shield.post("/v1/crash-shield/subscribe")
async def api_subscribe(request: Request):
    """Register a webhook URL to receive crash shield alerts."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    url = body.get("url")
    if not url or not url.startswith("http"):
        return JSONResponse({"error": "Missing or invalid 'url' field"}, status_code=400)

    alert_levels = body.get("alert_levels", "WARNING,CRITICAL")
    portfolio = body.get("portfolio")

    webhook_id = str(uuid.uuid4())
    conn = _get_db()
    conn.execute("""
        INSERT INTO crash_shield_webhooks
        (webhook_id, url, portfolio_json, alert_levels, registered_at, trigger_count, is_active)
        VALUES (?, ?, ?, ?, ?, 0, 1)
    """, (
        webhook_id, url,
        json.dumps(portfolio) if portfolio else "[]",
        alert_levels,
        datetime.now(timezone.utc).isoformat(),
    ))
    conn.commit()
    conn.close()

    return {
        "webhook_id": webhook_id,
        "url": url,
        "alert_levels": alert_levels,
        "status": "active",
        "message": "You will receive POST requests when ZARQ detects a new crash shield save.",
    }


@router_crash_shield.get("/v1/crash-shield/save/{save_id}/card", response_class=HTMLResponse)
def save_card(save_id: str):
    """Shareable HTML card for a verified save."""
    conn = _get_db()
    row = conn.execute("SELECT * FROM crash_shield_saves WHERE save_id = ?", (save_id,)).fetchone()
    conn.close()

    if not row:
        return HTMLResponse("<h1>Save not found</h1>", status_code=404)

    s = dict(row)
    name = s.get("name") or s["token_id"]
    symbol = (s.get("symbol") or s["token_id"]).upper()
    drop = s["drop_percent"]
    days_lead = 0
    try:
        from datetime import date as _d
        w = _d.fromisoformat(s["warning_date"])
        c = _d.fromisoformat(s["crash_date"])
        days_lead = (c - w).days
    except Exception:
        pass

    title = f"ZARQ detected {symbol} crash {days_lead} days early"
    description = (
        f"ZARQ flagged {name} ({symbol}) on {s['warning_date']} with "
        f"{int((s.get('crash_prob_at_warning') or 0) * 100)}% crash probability. "
        f"It dropped {drop}% from ${s.get('warning_price', 0):.4g} to ${s.get('crash_price', 0):.4g}."
    )
    card_url = f"https://zarq.ai/save/{save_id}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | ZARQ Crash Shield</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{card_url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="ZARQ">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<link rel="canonical" href="{card_url}">
<style>
:root {{
    --warm: #c2956b;
    --warm-light: #f5ebe0;
    --bg: #fafaf8;
    --text: #1a1a1a;
    --gray-400: #9ca3af;
    --gray-600: #4b5563;
    --red: #dc2626;
    --red-light: #fef2f2;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family: 'DM Sans', -apple-system, sans-serif;
    background: var(--bg); color: var(--text);
    display:flex; align-items:center; justify-content:center;
    min-height:100vh; padding:20px;
}}
.card {{
    max-width:520px; width:100%; background:#fff;
    border:1px solid #e5e5e5; border-radius:16px;
    overflow:hidden;
}}
.card-top {{
    background: linear-gradient(135deg, var(--red-light), #fff);
    padding:32px; text-align:center;
}}
.shield {{ font-size:48px; margin-bottom:12px; }}
.token-name {{
    font-family: 'DM Serif Display', Georgia, serif;
    font-size:1.8rem; font-weight:400;
}}
.drop {{
    font-family: 'JetBrains Mono', monospace;
    font-size:2.5rem; font-weight:700; color:var(--red);
    margin:8px 0;
}}
.lead-time {{
    font-size:1.1rem; color:var(--gray-600);
}}
.lead-time strong {{ color:var(--warm); }}
.card-body {{ padding:24px 32px; }}
.row {{ display:flex; justify-content:space-between; padding:10px 0; border-bottom:1px solid #f0f0f0; }}
.row:last-child {{ border:none; }}
.label {{ color:var(--gray-400); font-size:0.85rem; }}
.value {{ font-family:'JetBrains Mono',monospace; font-weight:600; }}
.card-footer {{
    background:var(--warm-light); padding:20px 32px;
    text-align:center; font-size:0.9rem;
}}
.card-footer a {{ color:var(--warm); text-decoration:none; font-weight:600; }}
.badge {{
    display:inline-block; background:var(--warm); color:#fff;
    font-size:0.75rem; font-weight:600; padding:3px 10px;
    border-radius:20px; margin-bottom:12px;
}}
</style>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
</head>
<body>
<div class="card">
    <div class="card-top">
        <div class="badge">Verified Save</div>
        <div class="token-name">{name} ({symbol})</div>
        <div class="drop">-{drop}%</div>
        <div class="lead-time">ZARQ detected this <strong>{days_lead} days</strong> before crash</div>
    </div>
    <div class="card-body">
        <div class="row"><span class="label">Warning Date</span><span class="value">{s['warning_date']}</span></div>
        <div class="row"><span class="label">Crash Date</span><span class="value">{s['crash_date']}</span></div>
        <div class="row"><span class="label">Price at Warning</span><span class="value">${s.get('warning_price', 0):.4g}</span></div>
        <div class="row"><span class="label">Price at Bottom</span><span class="value">${s.get('crash_price', 0):.4g}</span></div>
        <div class="row"><span class="label">Crash Probability</span><span class="value">{int((s.get('crash_prob_at_warning') or 0) * 100)}%</span></div>
        <div class="row"><span class="label">SHA-256</span><span class="value" style="font-size:0.75rem">{s.get('sha256_hash', '')}</span></div>
    </div>
    <div class="card-footer">
        Trust Checked by <a href="https://zarq.ai">ZARQ</a> &mdash; Risk Intelligence for the Agent Economy
        <br><a href="https://zarq.ai/v1/check/{s['token_id']}" style="font-size:0.8rem">Check this token now &rarr;</a>
    </div>
</div>
</body>
</html>"""


# Also mount a prettier route at /save/{save_id}
@router_crash_shield.get("/save/{save_id}", response_class=HTMLResponse)
def save_card_pretty(save_id: str):
    """Pretty URL redirect to card."""
    return save_card(save_id)
