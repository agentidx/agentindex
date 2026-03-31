"""
ZARQ Save Simulator — Sprint 2
Shows the most dramatic crashes ZARQ predicted, as "saves" an agent could have made.
"""

import os
import sqlite3
from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse, JSONResponse

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")

router_save_sim = APIRouter(tags=["demo"])

SAVE_QUERY = """
    WITH first_warnings AS (
        SELECT token_id, MIN(date) as warning_date, crash_prob_v3
        FROM crash_model_v3_predictions
        WHERE crash_prob_v3 > 0.5 AND max_drawdown < -0.5 AND period = 'OOS'
        GROUP BY token_id
    ),
    worst_drawdowns AS (
        SELECT token_id, MIN(max_drawdown) as worst_drawdown
        FROM crash_model_v3_predictions
        WHERE crash_prob_v3 > 0.5 AND max_drawdown < -0.5 AND period = 'OOS'
        GROUP BY token_id
    )
    SELECT fw.token_id, fw.warning_date, fw.crash_prob_v3, wd.worst_drawdown,
           pw.close as price_at_warning,
           n.symbol, n.name
    FROM first_warnings fw
    JOIN worst_drawdowns wd ON fw.token_id = wd.token_id
    LEFT JOIN crypto_price_history pw ON fw.token_id = pw.token_id AND pw.date = fw.warning_date
    LEFT JOIN crypto_ndd_daily n ON fw.token_id = n.token_id AND n.run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)
    WHERE wd.worst_drawdown < -0.5 AND pw.close IS NOT NULL AND pw.close > 0
    ORDER BY wd.worst_drawdown ASC
    LIMIT 5
"""


def _get_saves():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(SAVE_QUERY).fetchall()
    conn.close()

    saves = []
    for r in rows:
        drop = abs(r["worst_drawdown"])
        price_warning = r["price_at_warning"]
        price_crash = price_warning * (1 - drop)
        name = r["name"] or r["token_id"]
        symbol = (r["symbol"] or r["token_id"]).upper()

        # Estimate crash date (~4 weeks after warning for max drawdown)
        saves.append({
            "token": name,
            "symbol": symbol,
            "token_id": r["token_id"],
            "warning_date": r["warning_date"],
            "crash_probability": round(r["crash_prob_v3"], 2),
            "price_at_warning": round(price_warning, 4),
            "price_at_bottom": round(price_crash, 4),
            "drop_percent": round(drop * 100, 1),
            "message": (
                f"If your agent had ZARQ on {r['warning_date']}, it would have avoided "
                f"{symbol} — which fell {round(drop * 100, 1)}% from "
                f"${price_warning:.4g} to ${price_crash:.4g}."
            ),
        })
    return saves


@router_save_sim.get("/v1/demo/save-simulator")
def save_simulator_api(response: Response):
    """Top 5 most dramatic crashes ZARQ predicted — the saves an agent could have made."""
    saves = _get_saves()
    response.headers["Cache-Control"] = "public, max-age=3600"
    return {"saves": saves, "total": len(saves), "source": "ZARQ crash_model_v3 (OOS predictions)"}


@router_save_sim.get("/demo/save-simulator", response_class=HTMLResponse)
def save_simulator_page():
    """Visual save simulator page."""
    saves = _get_saves()

    save_cards = ""
    for i, s in enumerate(saves):
        save_cards += f"""
        <div class="save-card" style="animation-delay: {i * 0.15}s">
            <div class="save-header">
                <span class="save-symbol">{s['symbol']}</span>
                <span class="save-name">{s['token']}</span>
                <span class="save-drop">-{s['drop_percent']}%</span>
            </div>
            <div class="save-prices">
                <div class="price-box">
                    <div class="price-label">Price at Warning</div>
                    <div class="price-value">${s['price_at_warning']:.4g}</div>
                    <div class="price-date">{s['warning_date']}</div>
                </div>
                <div class="price-arrow">&rarr;</div>
                <div class="price-box crash">
                    <div class="price-label">Bottom Price</div>
                    <div class="price-value">${s['price_at_bottom']:.4g}</div>
                </div>
            </div>
            <div class="save-message">{s['message']}</div>
            <div class="save-prob">Crash probability at warning: <strong>{int(s['crash_probability'] * 100)}%</strong></div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Save Simulator — ZARQ Crypto Risk Intelligence</title>
<meta name="description" content="See the crashes ZARQ predicted before they happened. Real out-of-sample predictions on real tokens.">
<link rel="canonical" href="https://zarq.ai/demo/save-simulator">
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
    --green: #16a34a;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
}}
.container {{ max-width: 800px; margin: 0 auto; padding: 40px 20px; }}
h1 {{
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 2.2rem;
    font-weight: 400;
    margin-bottom: 8px;
}}
.subtitle {{
    color: var(--gray-600);
    font-size: 1.1rem;
    margin-bottom: 40px;
}}
.subtitle strong {{ color: var(--warm); }}
.save-card {{
    background: #fff;
    border: 1px solid #e5e5e5;
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 20px;
    opacity: 0;
    animation: fadeIn 0.5s ease-out forwards;
}}
@keyframes fadeIn {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}
.save-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
}}
.save-symbol {{
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 1.1rem;
    background: var(--warm-light);
    color: var(--warm);
    padding: 4px 10px;
    border-radius: 6px;
}}
.save-name {{ color: var(--gray-600); flex: 1; }}
.save-drop {{
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 1.3rem;
    color: var(--red);
}}
.save-prices {{
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 16px;
}}
.price-box {{
    flex: 1;
    background: var(--bg);
    border-radius: 8px;
    padding: 12px 16px;
    text-align: center;
}}
.price-box.crash {{
    background: var(--red-light);
}}
.price-label {{
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--gray-400);
    margin-bottom: 4px;
}}
.price-value {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.2rem;
    font-weight: 600;
}}
.price-date {{
    font-size: 0.8rem;
    color: var(--gray-400);
    margin-top: 2px;
}}
.price-arrow {{
    font-size: 1.5rem;
    color: var(--red);
}}
.save-message {{
    font-size: 0.95rem;
    color: var(--gray-600);
    margin-bottom: 8px;
    line-height: 1.5;
}}
.save-prob {{
    font-size: 0.85rem;
    color: var(--gray-400);
}}
.cta-box {{
    background: linear-gradient(135deg, var(--warm-light), #fff);
    border: 2px solid var(--warm);
    border-radius: 12px;
    padding: 32px;
    text-align: center;
    margin-top: 40px;
}}
.cta-box h2 {{
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 1.5rem;
    font-weight: 400;
    margin-bottom: 12px;
}}
.cta-code {{
    background: #1a1a1a;
    color: #e5e5e5;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.9rem;
    padding: 16px 24px;
    border-radius: 8px;
    display: inline-block;
    margin: 16px 0;
    text-align: left;
}}
.cta-code .comment {{ color: #6b7280; }}
.cta-code .url {{ color: var(--warm); }}
.cta-btn {{
    display: inline-block;
    background: var(--warm);
    color: #fff;
    text-decoration: none;
    padding: 12px 32px;
    border-radius: 8px;
    font-weight: 600;
    font-size: 1rem;
    margin-top: 12px;
    transition: opacity 0.2s;
}}
.cta-btn:hover {{ opacity: 0.85; }}
.badge {{
    display: inline-block;
    background: var(--warm-light);
    color: var(--warm);
    font-size: 0.8rem;
    font-weight: 600;
    padding: 4px 12px;
    border-radius: 20px;
    margin-bottom: 16px;
}}
.footer {{
    text-align: center;
    margin-top: 40px;
    color: var(--gray-400);
    font-size: 0.85rem;
}}
.footer a {{ color: var(--warm); text-decoration: none; }}
</style>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
</head>
<body>
<div class="container">
    <div class="badge">Out-of-Sample Predictions</div>
    <h1>The Saves ZARQ Would Have Made</h1>
    <p class="subtitle">Real predictions on real tokens. All out-of-sample — <strong>ZARQ flagged these before they crashed.</strong></p>

    {save_cards}

    <div class="cta-box">
        <h2>Add ZARQ to your agent in 1 line</h2>
        <div class="cta-code">
            <span class="comment"># Before any crypto trade, check risk:</span><br>
            GET <span class="url">https://zarq.ai/v1/check/bitcoin</span>
        </div>
        <br>
        <a href="/docs" class="cta-btn">Read the API Docs &rarr;</a>
    </div>

    <div class="footer">
        <p>Data from ZARQ crash_model_v3 out-of-sample predictions (Jan 2024 &ndash; present).</p>
        <p>100% recall on structural collapses. 98% precision. <a href="/track-record">See full track record &rarr;</a></p>
        <p style="margin-top:8px"><a href="/v1/demo/save-simulator">API endpoint</a> &middot; <a href="/kya">Know Your Agent</a> &middot; <a href="/signal">ZARQ Signal</a> &middot; <a href="/zarq/docs">API Docs</a> &middot; <a href="https://zarq.ai">zarq.ai</a></p>
    </div>
</div>
</body>
</html>"""
