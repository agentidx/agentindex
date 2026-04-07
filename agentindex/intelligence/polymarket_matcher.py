#!/usr/bin/env python3
"""
Polymarket Signal Matcher
===========================
Fetches active Polymarket markets, matches with ZARQ crypto signals,
identifies edge opportunities, logs paper trades.
"""

import json, logging, re, sqlite3, sys, time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests as http
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/polymarket.log")])
logger = logging.getLogger("polymarket")

CRYPTO_DB = str(Path(__file__).parent.parent / "crypto" / "crypto_trust.db")
TODAY = date.today()

CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
    "crypto", "defi", "token", "exchange", "binance", "coinbase",
    "hack", "sec", "regulation", "etf", "stablecoin", "tether",
    "price", "crash", "bull", "bear", "halving",
    "cardano", "ripple", "xrp", "dogecoin", "doge",
    "nft", "web3", "blockchain", "bitcoin price", "crypto market",
    "usdc", "usdt", "bnb", "avax", "matic", "polygon",
]

TOKEN_MAP = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "solana": "solana", "sol": "solana",
    "cardano": "cardano", "ada": "cardano",
    "ripple": "ripple", "xrp": "ripple",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "polkadot": "polkadot", "dot": "polkadot",
    "avalanche": "avalanche-2", "avax": "avalanche-2",
    "polygon": "matic-network", "matic": "matic-network",
    "chainlink": "chainlink", "link": "chainlink",
    "uniswap": "uniswap", "uni": "uniswap",
    "tether": "tether", "usdt": "tether",
    "bnb": "binancecoin", "binance": "binancecoin",
}


def fetch_markets():
    """Fetch all active Polymarket markets."""
    logger.info("Fetching Polymarket markets...")
    markets = []
    offset = 0
    while True:
        try:
            r = http.get("https://gamma-api.polymarket.com/markets",
                        params={"active": "true", "closed": "false", "limit": 100, "offset": offset},
                        timeout=30)
            if r.status_code != 200:
                break
            data = r.json()
            if not data:
                break
            markets.extend(data)
            offset += 100
            if len(data) < 100:
                break
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Fetch error: {e}")
            break
    logger.info(f"  Total markets: {len(markets)}")
    return markets


def filter_crypto(markets):
    """Filter for crypto-related markets."""
    crypto = []
    for m in markets:
        text_field = (m.get("question", "") + " " + (m.get("description") or "")).lower()
        if any(kw in text_field for kw in CRYPTO_KEYWORDS):
            crypto.append(m)
    logger.info(f"  Crypto markets: {len(crypto)}")
    return crypto


def get_zarq_signals(token_id):
    """Fetch ZARQ signals for a token from crypto DB."""
    signals = {}
    try:
        conn = sqlite3.connect(CRYPTO_DB, timeout=5)
        conn.row_factory = sqlite3.Row

        ndd = conn.execute("SELECT ndd, crash_probability, alert_level FROM crypto_ndd_daily WHERE token_id = ? ORDER BY run_date DESC LIMIT 1", (token_id,)).fetchone()
        if ndd:
            signals["crash_probability"] = ndd["crash_probability"]
            signals["ndd"] = ndd["ndd"]
            signals["alert_level"] = ndd["alert_level"]

        rating = conn.execute("SELECT rating, score FROM crypto_rating_daily WHERE token_id = ? ORDER BY run_date DESC LIMIT 1", (token_id,)).fetchone()
        if rating:
            signals["rating"] = rating["rating"]
            signals["trust_score"] = rating["score"]

        vitality = conn.execute("SELECT vitality_score, vitality_grade FROM vitality_scores WHERE token_id = ? ORDER BY rowid DESC LIMIT 1", (token_id,)).fetchone()
        if vitality:
            signals["vitality_score"] = vitality["vitality_score"]
            signals["vitality_grade"] = vitality["vitality_grade"]

        conn.close()
    except Exception as e:
        logger.debug(f"ZARQ signal fetch for {token_id}: {e}")
    return signals


def categorize_market(question):
    """Categorize a market question."""
    q = question.lower()
    if any(w in q for w in ["price", "reach", "above", "below", "high", "low", "ath", "$"]):
        return "crypto_price"
    if any(w in q for w in ["hack", "exploit", "breach", "attack", "vulnerability"]):
        return "crypto_hack"
    if any(w in q for w in ["sec", "regulation", "ban", "approve", "etf", "legal"]):
        return "crypto_regulatory"
    if any(w in q for w in ["adopt", "top 10", "mainstream", "million users"]):
        return "crypto_adoption"
    if any(w in q for w in ["defi", "tvl", "yield", "protocol", "liquidity"]):
        return "defi"
    return "crypto_other"


def extract_tokens(question):
    """Extract token references from a market question."""
    q = question.lower()
    tokens = []
    for keyword, token_id in TOKEN_MAP.items():
        if keyword in q and token_id not in tokens:
            tokens.append(token_id)
    return tokens


def estimate_probability(signals, category, question):
    """Estimate our probability based on ZARQ signals."""
    if not signals:
        return None, "low"

    q = question.lower()

    if category == "crypto_price":
        # Price target questions
        crash_prob = signals.get("crash_probability", 0.5)
        vitality = signals.get("vitality_score", 50)
        trust = signals.get("trust_score", 50)

        # "Will X reach [high price]?" — lower crash prob = higher chance
        if any(w in q for w in ["above", "reach", "hit", "surpass", "over"]):
            our_prob = max(0.05, min(0.95, (1 - crash_prob) * (vitality / 100) * 0.8))
            return our_prob, "medium" if vitality > 50 else "low"

        # "Will X crash/fall below?" — use crash prob directly
        if any(w in q for w in ["crash", "below", "drop", "fall"]):
            our_prob = max(0.05, min(0.95, crash_prob * 1.2))
            return our_prob, "high" if signals.get("alert_level") in ("WARNING", "CRITICAL") else "medium"

    elif category == "crypto_hack":
        trust = signals.get("trust_score", 50)
        our_prob = max(0.05, min(0.5, (100 - trust) / 200))
        return our_prob, "low"

    elif category == "defi":
        vitality = signals.get("vitality_score", 50)
        crash_prob = signals.get("crash_probability", 0.3)
        our_prob = max(0.1, min(0.9, crash_prob))
        return our_prob, "medium"

    return None, "low"


def match_market(market):
    """Match a single market with ZARQ signals."""
    question = market.get("question", "")
    category = categorize_market(question)
    tokens = extract_tokens(question)

    # Get market probability from outcomes
    outcomes = market.get("outcomePrices") or market.get("outcomes")
    market_prob = None
    if isinstance(outcomes, str):
        try:
            prices = json.loads(outcomes)
            if prices and len(prices) >= 1:
                market_prob = float(prices[0])
        except (json.JSONDecodeError, ValueError, IndexError):
            pass

    # Get ZARQ signals for matched tokens
    all_signals = {}
    for token_id in tokens:
        sigs = get_zarq_signals(token_id)
        if sigs:
            all_signals[token_id] = sigs

    # Estimate our probability
    our_prob = None
    confidence = "low"
    if all_signals:
        primary = list(all_signals.values())[0]
        our_prob, confidence = estimate_probability(primary, category, question)

    edge = None
    if our_prob is not None and market_prob is not None:
        edge = our_prob - market_prob

    return {
        "market_id": market.get("id") or market.get("condition_id", ""),
        "question": question,
        "category": category,
        "tokens_matched": tokens,
        "market_probability": market_prob,
        "our_probability": our_prob,
        "edge": edge,
        "confidence": confidence,
        "signals": all_signals,
        "volume": market.get("volume", 0),
    }


def save_matches(session, matches):
    """Save matches to tracking table."""
    saved = 0
    for m in matches:
        if m["market_probability"] is None and m["our_probability"] is None:
            continue
        try:
            session.execute(text("""
                INSERT INTO prediction_market_tracking
                (date, market_id, question, category, market_probability, our_probability, edge, our_signals, confidence)
                VALUES (:d, :mid, :q, :cat, :mp, :op, :edge, CAST(:sigs AS jsonb), :conf)
                ON CONFLICT DO NOTHING
            """), {"d": TODAY.isoformat(), "mid": m["market_id"][:100], "q": m["question"][:500],
                  "cat": m["category"], "mp": m["market_probability"], "op": m["our_probability"],
                  "edge": m["edge"], "sigs": json.dumps(m["signals"]),
                  "conf": m["confidence"]})
            saved += 1
        except Exception:
            session.rollback()

    # Open paper trades for high-edge opportunities
    trades = 0
    for m in matches:
        if m["edge"] is not None and abs(m["edge"]) > 0.15 and m["confidence"] in ("medium", "high"):
            direction = "YES" if m["edge"] > 0 else "NO"
            entry = m["market_probability"] if direction == "YES" else (1 - (m["market_probability"] or 0.5))
            try:
                session.execute(text("""
                    INSERT INTO prediction_market_paper_trades
                    (date, market_id, direction, entry_price, current_price, position_size, status)
                    VALUES (:d, :mid, :dir, :ep, :ep, 100, 'open')
                """), {"d": TODAY.isoformat(), "mid": m["market_id"][:100],
                      "dir": direction, "ep": entry})
                trades += 1
            except Exception:
                session.rollback()

    session.commit()
    return saved, trades


def main():
    logger.info(f"=== POLYMARKET SCAN {TODAY} ===")

    # Fetch and filter
    markets = fetch_markets()
    crypto = filter_crypto(markets)

    # Match all
    matches = []
    for m in crypto:
        match = match_market(m)
        matches.append(match)

    # Sort by edge
    with_edge = [m for m in matches if m["edge"] is not None]
    with_edge.sort(key=lambda x: abs(x["edge"]), reverse=True)

    # Report
    logger.info(f"\n=== RESULTS ===")
    logger.info(f"Total markets: {len(markets)}")
    logger.info(f"Crypto markets: {len(crypto)}")
    logger.info(f"With ZARQ signals: {len(with_edge)}")

    if with_edge:
        logger.info(f"\nTop edge opportunities:")
        for m in with_edge[:10]:
            logger.info(f"  Edge: {m['edge']:+.2f} | Market: {m['market_probability']:.2f} | Ours: {m['our_probability']:.2f} | {m['confidence']}")
            logger.info(f"    Q: {m['question'][:80]}")
            logger.info(f"    Tokens: {m['tokens_matched']} | Category: {m['category']}")

    # Save to DB
    session = get_session()
    try:
        saved, trades = save_matches(session, matches)
        logger.info(f"\nSaved: {saved} matches, {trades} paper trades")
    finally:
        session.close()

    logger.info(f"=== SCAN COMPLETE ===")


if __name__ == "__main__":
    main()
