#!/usr/bin/env python3
"""
Polymarket Backtester
======================
Tests ZARQ signals against resolved Polymarket crypto markets.
"""

import json, logging, re, sqlite3, sys, time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests as http
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("polymarket_backtest")

CRYPTO_DB = str(Path(__file__).parent.parent / "crypto" / "crypto_trust.db")

# Strict crypto keywords (avoid false positives)
STRICT_CRYPTO_KW = ["bitcoin", "btc ", "ethereum", "eth ", "solana", "sol ",
                     "crypto", "defi", "token price", "binance", "coinbase",
                     "cardano", "xrp", "dogecoin", "bnb", "avax", "chainlink"]

TOKEN_MAP = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "solana": "solana", "sol": "solana",
    "cardano": "cardano", "xrp": "ripple",
    "dogecoin": "dogecoin", "bnb": "binancecoin",
    "avalanche": "avalanche-2", "polkadot": "polkadot",
    "chainlink": "chainlink", "uniswap": "uniswap",
}


def fetch_resolved_crypto():
    """Fetch resolved markets that are strictly crypto-related."""
    logger.info("Fetching resolved Polymarket markets...")
    all_markets = []
    for offset in range(0, 10000, 100):
        try:
            r = http.get("https://gamma-api.polymarket.com/markets",
                        params={"active": "false", "closed": "true", "limit": 100, "offset": offset},
                        timeout=30)
            if r.status_code != 200: break
            data = r.json()
            if not data: break
            all_markets.extend(data)
            if len(data) < 100: break
        except Exception:
            break
        time.sleep(0.3)

    # Strict filter
    crypto = []
    for m in all_markets:
        q = m.get("question", "").lower()
        if any(kw in q for kw in STRICT_CRYPTO_KW):
            # Must have outcome prices (resolved)
            prices = m.get("outcomePrices", "")
            if prices and prices != '["0","0"]':
                crypto.append(m)

    logger.info(f"  Total resolved: {len(all_markets)}, Strict crypto: {len(crypto)}")
    return crypto


def get_zarq_historical(token_id):
    """Get ZARQ historical data for a token."""
    try:
        conn = sqlite3.connect(CRYPTO_DB, timeout=5)
        conn.row_factory = sqlite3.Row

        # Latest data (we don't have time-series yet, just latest snapshot)
        ndd = conn.execute("SELECT ndd, crash_probability, alert_level FROM crypto_ndd_daily WHERE token_id = ? ORDER BY run_date DESC LIMIT 1",
                          (token_id,)).fetchone()
        rating = conn.execute("SELECT rating, score FROM crypto_rating_daily WHERE token_id = ? ORDER BY run_date DESC LIMIT 1",
                             (token_id,)).fetchone()
        vitality = conn.execute("SELECT vitality_score FROM vitality_scores WHERE token_id = ? ORDER BY rowid DESC LIMIT 1",
                               (token_id,)).fetchone()
        conn.close()

        if not ndd and not rating:
            return None

        return {
            "crash_prob": ndd["crash_probability"] if ndd else None,
            "ndd": ndd["ndd"] if ndd else None,
            "alert": ndd["alert_level"] if ndd else None,
            "rating": rating["rating"] if rating else None,
            "trust_score": rating["score"] if rating else None,
            "vitality": vitality["vitality_score"] if vitality else None,
        }
    except Exception:
        return None


def extract_tokens(question):
    q = question.lower()
    found = []
    for kw, tid in TOKEN_MAP.items():
        if kw in q and tid not in found:
            found.append(tid)
    return found


def estimate_outcome(signals, question):
    """Estimate probability of YES outcome based on ZARQ signals."""
    if not signals:
        return None, "none"

    q = question.lower()
    crash_prob = signals.get("crash_prob")
    vitality = signals.get("vitality")
    trust = signals.get("trust_score")

    # Price target markets
    if any(w in q for w in ["price", "above", "reach", "hit", "$"]):
        if crash_prob is not None:
            # High crash probability → less likely to hit targets
            our_yes = max(0.05, min(0.95, (1 - crash_prob) * (vitality or 50) / 100 * 0.8))
            confidence = "high" if signals.get("alert") in ("WARNING", "CRITICAL") else "medium"
            return our_yes, confidence

    # Crash/bear markets
    if any(w in q for w in ["crash", "drop", "bear", "below", "fall"]):
        if crash_prob is not None:
            our_yes = max(0.05, min(0.95, crash_prob))
            return our_yes, "high"

    # Hack markets
    if any(w in q for w in ["hack", "exploit", "breach"]):
        if trust is not None:
            our_yes = max(0.05, min(0.4, (100 - trust) / 300))
            return our_yes, "low"

    return None, "none"


def backtest():
    logger.info("=== POLYMARKET BACKTEST ===")

    crypto_markets = fetch_resolved_crypto()

    results = {
        "total_analyzed": 0,
        "with_signals": 0,
        "correct_predictions": 0,
        "total_edge": 0,
        "total_pnl": 0,
        "trades": [],
        "by_category": {},
    }

    for market in crypto_markets:
        question = market.get("question", "")
        tokens = extract_tokens(question)
        if not tokens:
            continue

        # Get ZARQ signals for primary token
        signals = get_zarq_historical(tokens[0])
        if not signals:
            continue

        # Get market final price (outcome)
        outcome_prices = market.get("outcomePrices", "")
        try:
            prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
            if not prices or len(prices) < 2:
                continue
            yes_price = float(prices[0])
            # Resolved: yes_price near 1.0 = YES won, near 0.0 = NO won
            actual_outcome = yes_price > 0.5  # TRUE if YES won
        except (json.JSONDecodeError, ValueError, IndexError):
            continue

        # Our estimate
        our_prob, confidence = estimate_outcome(signals, question)
        if our_prob is None:
            continue

        results["total_analyzed"] += 1
        results["with_signals"] += 1

        # Did we predict correctly?
        our_predicted_yes = our_prob > 0.5
        correct = our_predicted_yes == actual_outcome
        if correct:
            results["correct_predictions"] += 1

        # Simulated P&L: bet $100 on our signal
        # If we said YES (prob > 0.5), we bought YES at some price
        # Assume we could have bought at market_midpoint
        # P&L = $100 * (outcome_price - entry_price) / entry_price
        entry_price = our_prob  # simplified: we buy at our estimated fair value
        exit_price = 1.0 if actual_outcome else 0.0
        pnl = 100 * (exit_price - entry_price) if our_predicted_yes else 100 * (entry_price - exit_price)
        results["total_pnl"] += pnl

        trade = {
            "question": question[:80],
            "tokens": tokens,
            "our_prob": round(our_prob, 3),
            "actual_yes": actual_outcome,
            "correct": correct,
            "pnl": round(pnl, 2),
            "confidence": confidence,
        }
        results["trades"].append(trade)

    # Summary
    total = results["with_signals"]
    correct = results["correct_predictions"]
    hit_rate = correct / total if total > 0 else 0

    logger.info(f"\n=== BACKTEST RESULTS ===")
    logger.info(f"Resolved crypto markets analyzed: {results['total_analyzed']}")
    logger.info(f"Markets with ZARQ signals: {total}")
    logger.info(f"Correct predictions: {correct}/{total} ({hit_rate:.1%})")
    logger.info(f"Total simulated P&L: ${results['total_pnl']:.2f}")
    logger.info(f"Avg P&L per trade: ${results['total_pnl'] / max(1, total):.2f}")

    # Best and worst
    if results["trades"]:
        best = max(results["trades"], key=lambda t: t["pnl"])
        worst = min(results["trades"], key=lambda t: t["pnl"])
        logger.info(f"\nBest trade: ${best['pnl']:.2f} — {best['question']}")
        logger.info(f"Worst trade: ${worst['pnl']:.2f} — {worst['question']}")

        # By confidence
        for conf in ["high", "medium", "low"]:
            trades = [t for t in results["trades"] if t["confidence"] == conf]
            if trades:
                hit = sum(1 for t in trades if t["correct"]) / len(trades)
                avg_pnl = sum(t["pnl"] for t in trades) / len(trades)
                logger.info(f"  {conf}: {len(trades)} trades, {hit:.1%} hit rate, avg P&L ${avg_pnl:.2f}")

    # Save results
    session = get_session()
    try:
        session.execute(text("""
            INSERT INTO signal_events (date, signal_type, severity, description, data)
            VALUES (:d, 'polymarket_backtest', 'info', :desc, CAST(:data AS jsonb))
        """), {"d": date.today().isoformat(),
              "desc": f"Backtest: {total} markets, {hit_rate:.1%} hit rate, ${results['total_pnl']:.0f} P&L",
              "data": json.dumps({"total": total, "correct": correct, "hit_rate": round(hit_rate, 3),
                                 "pnl": round(results["total_pnl"], 2),
                                 "top_trades": results["trades"][:20]})})
        session.commit()
    finally:
        session.close()

    return results


if __name__ == "__main__":
    backtest()
