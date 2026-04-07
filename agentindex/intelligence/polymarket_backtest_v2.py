#!/usr/bin/env python3
"""
Polymarket Backtest v2 — TRUE point-in-time
=============================================
Uses ZARQ's historical crash predictions (31K data points, 2021-2026)
matched against resolved Polymarket markets at the CORRECT timestamp.
No look-ahead bias.
"""

import json, logging, re, sqlite3, sys, time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests as http
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("backtest_v2")

CRYPTO_DB = str(Path(__file__).parent.parent / "crypto" / "crypto_trust.db")

TOKEN_MAP = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "solana": "solana", "sol": "solana",
    "cardano": "cardano", "ada": "cardano",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "polkadot": "polkadot", "dot": "polkadot",
    "avalanche": "avalanche-2", "avax": "avalanche-2",
    "chainlink": "chainlink", "link": "chainlink",
    "uniswap": "uniswap", "bnb": "binancecoin",
    "ripple": "ripple", "xrp": "ripple",
    "polygon": "matic-network", "matic": "matic-network",
}

STRICT_KW = ["bitcoin", "btc", "ethereum", "eth ", "solana", "sol ",
             "cardano", "xrp", "dogecoin", "doge", "bnb", "avalanche",
             "chainlink", "polkadot", "uniswap", "crypto price",
             "polygon", "matic"]


def get_crash_prob_at_date(conn, token_id, target_date):
    """Get ZARQ crash probability for token AT or BEFORE target_date (no look-ahead)."""
    row = conn.execute(
        "SELECT crash_prob_v3, crash_label, max_drawdown, date FROM crash_model_v3_predictions "
        "WHERE token_id = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        (token_id, target_date)
    ).fetchone()
    if row:
        return {"crash_prob": row[0], "crash_label": row[1],
                "max_drawdown": row[2], "signal_date": row[3]}
    return None


def get_price_at_date(conn, token_id, target_date):
    """Get token price at or before target_date."""
    row = conn.execute(
        "SELECT close, date FROM crypto_price_history "
        "WHERE token_id = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        (token_id, target_date)
    ).fetchone()
    return row[0] if row else None


def extract_price_target(question):
    """Extract price target from market question."""
    # Match patterns like "$70,000", "$70K", "$100k"
    m = re.search(r'\$([0-9,]+(?:\.\d+)?)\s*([kK])?', question)
    if m:
        price = float(m.group(1).replace(",", ""))
        if m.group(2): price *= 1000
        return price
    return None


def extract_tokens(question):
    q = question.lower()
    found = []
    for kw, tid in TOKEN_MAP.items():
        if kw in q and tid not in found:
            found.append(tid)
    return found


def is_above_market(question):
    """Determine if market asks 'above' or 'below' a price."""
    q = question.lower()
    if any(w in q for w in ["above", "reach", "hit", "surpass", "over", "higher"]):
        return True
    if any(w in q for w in ["below", "under", "drop", "fall", "crash"]):
        return False
    return True  # default: assume "above"


def fetch_resolved_crypto():
    """Fetch resolved crypto markets from Polymarket."""
    logger.info("Fetching resolved Polymarket markets...")
    markets = []
    for offset in range(0, 10000, 100):
        try:
            r = http.get("https://gamma-api.polymarket.com/markets",
                        params={"active": "false", "closed": "true", "limit": 100, "offset": offset},
                        timeout=30)
            if r.status_code != 200: break
            data = r.json()
            if not data: break
            markets.extend(data)
            if len(data) < 100: break
        except Exception:
            break
        time.sleep(0.3)

    crypto = []
    for m in markets:
        q = m.get("question", "").lower()
        if any(kw in q for kw in STRICT_KW):
            prices = m.get("outcomePrices", "")
            if prices and prices != '["0","0"]':
                crypto.append(m)

    logger.info(f"  Total resolved: {len(markets)}, Crypto: {len(crypto)}")
    return crypto


def backtest():
    logger.info("=== POLYMARKET BACKTEST v2 (point-in-time) ===")

    crypto_markets = fetch_resolved_crypto()
    conn = sqlite3.connect(CRYPTO_DB, timeout=10)

    trades = []
    no_signal = 0
    no_price_target = 0

    for market in crypto_markets:
        question = market.get("question", "")
        tokens = extract_tokens(question)
        if not tokens:
            continue

        token_id = tokens[0]
        price_target = extract_price_target(question)
        asks_above = is_above_market(question)

        # Get market outcome
        try:
            outcome_prices = json.loads(market.get("outcomePrices", "[]"))
            if not outcome_prices or len(outcome_prices) < 2:
                continue
            yes_final = float(outcome_prices[0])
            actual_yes = yes_final > 0.5
        except (json.JSONDecodeError, ValueError, IndexError):
            continue

        # Get market creation date (approximate from slug/data)
        # Polymarket doesn't always give clean dates, use end_date - 30 days as entry
        end_date_str = market.get("endDate") or market.get("resolutionDate")
        if not end_date_str:
            continue
        try:
            end_date = end_date_str[:10]
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            entry_dt = end_dt - timedelta(days=14)  # Our entry: 14 days before resolution
            entry_date = entry_dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue

        # POINT-IN-TIME: Get ZARQ signal at entry_date (NOT current signal!)
        signal = get_crash_prob_at_date(conn, token_id, entry_date)
        if not signal:
            no_signal += 1
            continue

        crash_prob = signal["crash_prob"]

        # Our probability estimate (point-in-time)
        if price_target:
            current_price = get_price_at_date(conn, token_id, entry_date)
            if not current_price:
                no_signal += 1
                continue

            # Distance to target as factor
            if asks_above:
                pct_to_target = (price_target - current_price) / current_price
                # High crash prob + far from target = low chance of reaching
                # Low crash prob + close to target = high chance
                if pct_to_target > 0:
                    our_yes = max(0.05, min(0.95,
                        (1 - crash_prob) * max(0.1, 1 - pct_to_target * 2)))
                else:
                    # Already above target
                    our_yes = max(0.3, min(0.95, 1 - crash_prob))
            else:
                # "Below" market
                our_yes = max(0.05, min(0.95, crash_prob * 1.2))
        else:
            # Non-price markets — use crash prob as general risk indicator
            if any(w in question.lower() for w in ["crash", "drop", "bear", "fall"]):
                our_yes = max(0.05, min(0.95, crash_prob))
            else:
                our_yes = max(0.05, min(0.95, 1 - crash_prob * 0.5))
            no_price_target += 1

        # Did we predict correctly?
        our_predicted_yes = our_yes > 0.5
        correct = our_predicted_yes == actual_yes

        # P&L calculation
        # We bet our confidence as position size fraction
        if our_predicted_yes:
            entry_cost = our_yes  # Buy YES at our fair value
            payout = 1.0 if actual_yes else 0.0
        else:
            entry_cost = 1 - our_yes  # Buy NO at our fair value
            payout = 1.0 if not actual_yes else 0.0

        pnl = (payout - entry_cost) * 100  # $100 position

        trades.append({
            "question": question[:100],
            "token": token_id,
            "entry_date": entry_date,
            "end_date": end_date,
            "signal_date": signal["signal_date"],
            "crash_prob_at_entry": round(crash_prob, 4),
            "price_target": price_target,
            "our_yes_prob": round(our_yes, 4),
            "actual_yes": actual_yes,
            "correct": correct,
            "pnl": round(pnl, 2),
        })

    conn.close()

    # Results
    total = len(trades)
    correct = sum(1 for t in trades if t["correct"])
    hit_rate = correct / total if total > 0 else 0
    total_pnl = sum(t["pnl"] for t in trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0

    # Running P&L for max drawdown
    running = 0
    peak = 0
    max_dd = 0
    for t in trades:
        running += t["pnl"]
        peak = max(peak, running)
        dd = peak - running
        max_dd = max(max_dd, dd)

    logger.info(f"\n{'='*60}")
    logger.info(f"POLYMARKET BACKTEST v2 — POINT-IN-TIME RESULTS")
    logger.info(f"{'='*60}")
    logger.info(f"Markets analyzed: {len(crypto_markets)}")
    logger.info(f"No ZARQ signal available: {no_signal}")
    logger.info(f"No price target extracted: {no_price_target}")
    logger.info(f"Trades executed: {total}")
    logger.info(f"")
    logger.info(f"Hit rate: {correct}/{total} ({hit_rate:.1%})")
    logger.info(f"Total P&L: ${total_pnl:,.2f}")
    logger.info(f"Avg P&L per trade: ${total_pnl / max(1, total):.2f}")
    logger.info(f"Win/Loss: {len(wins)}/{len(losses)}")
    logger.info(f"Avg win: ${avg_win:.2f}")
    logger.info(f"Avg loss: ${avg_loss:.2f}")
    logger.info(f"Win/Loss ratio: {abs(avg_win / avg_loss) if avg_loss else 0:.2f}")
    logger.info(f"Max drawdown: ${max_dd:.2f}")
    logger.info(f"")

    if trades:
        best = max(trades, key=lambda t: t["pnl"])
        worst = min(trades, key=lambda t: t["pnl"])
        logger.info(f"Best: ${best['pnl']:.2f} — {best['question'][:60]}")
        logger.info(f"  Signal: crash_prob={best['crash_prob_at_entry']}, our_yes={best['our_yes_prob']}, actual={best['actual_yes']}")
        logger.info(f"Worst: ${worst['pnl']:.2f} — {worst['question'][:60]}")
        logger.info(f"  Signal: crash_prob={worst['crash_prob_at_entry']}, our_yes={worst['our_yes_prob']}, actual={worst['actual_yes']}")

    # Save to DB
    session = get_session()
    try:
        # Mark v1 as invalid
        session.execute(text("""
            UPDATE signal_events SET data = jsonb_set(COALESCE(data,'{}'), '{version}', '"v1_invalid"')
            WHERE signal_type = 'polymarket_backtest' AND (data->>'version') IS NULL
        """))

        session.execute(text("""
            INSERT INTO signal_events (date, signal_type, severity, description, data)
            VALUES (:d, 'polymarket_backtest', 'info', :desc, CAST(:data AS jsonb))
        """), {"d": date.today().isoformat(),
              "desc": f"v2 point-in-time: {total} trades, {hit_rate:.1%} hit rate, ${total_pnl:,.0f} P&L",
              "data": json.dumps({"version": "v2_point_in_time", "total": total,
                                 "correct": correct, "hit_rate": round(hit_rate, 4),
                                 "pnl": round(total_pnl, 2), "max_drawdown": round(max_dd, 2),
                                 "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
                                 "win_loss_ratio": round(abs(avg_win / avg_loss) if avg_loss else 0, 2),
                                 "trades_sample": trades[:30]})})
        session.commit()
    finally:
        session.close()

    return trades


if __name__ == "__main__":
    backtest()
