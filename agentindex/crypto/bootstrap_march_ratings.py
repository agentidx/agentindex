#!/usr/bin/env python3
"""
One-time bootstrap: compute March 2026 ratings from existing DB price data.
No CoinGecko API calls needed.

Usage: python3 bootstrap_march_ratings.py
"""
import json
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crypto_rating_daily import compute_rating, connect, ensure_tables, print_summary, STABLECOINS

RUN_DATE = "2026-03-12"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")


def build_token_dict(conn, token_id, run_date):
    """Build CoinGecko-compatible token dict from DB data."""
    row = conn.execute("""
        SELECT close AS current_price, volume AS total_volume, market_cap,
               token_id AS id
        FROM crypto_price_history
        WHERE token_id = ? AND date <= ?
        ORDER BY date DESC LIMIT 1
    """, (token_id, run_date)).fetchone()
    if not row or not row["current_price"]:
        return None

    # Get symbol/name/rank from last rating or pipeline status
    meta = conn.execute("""
        SELECT symbol, name, market_cap_rank
        FROM crypto_rating_daily
        WHERE token_id = ?
        ORDER BY run_date DESC LIMIT 1
    """, (token_id,)).fetchone()

    # Price changes from history
    prices_7d = conn.execute("""
        SELECT close FROM crypto_price_history
        WHERE token_id = ? AND date <= ? ORDER BY date DESC LIMIT 8
    """, (token_id, run_date)).fetchall()

    prices_30d = conn.execute("""
        SELECT close FROM crypto_price_history
        WHERE token_id = ? AND date <= ? ORDER BY date DESC LIMIT 31
    """, (token_id, run_date)).fetchall()

    pct_7d = None
    if len(prices_7d) >= 2 and prices_7d[-1]["close"]:
        pct_7d = ((prices_7d[0]["close"] - prices_7d[-1]["close"]) / prices_7d[-1]["close"]) * 100

    pct_30d = None
    if len(prices_30d) >= 2 and prices_30d[-1]["close"]:
        pct_30d = ((prices_30d[0]["close"] - prices_30d[-1]["close"]) / prices_30d[-1]["close"]) * 100

    return {
        "id": token_id,
        "symbol": meta["symbol"] if meta else "",
        "name": meta["name"] if meta else token_id,
        "market_cap_rank": (meta["market_cap_rank"] if meta and meta["market_cap_rank"] else 999),
        "current_price": row["current_price"],
        "total_volume": row["total_volume"],
        "market_cap": row["market_cap"],
        "price_change_percentage_24h": None,
        "price_change_percentage_7d_in_currency": pct_7d,
        "price_change_percentage_30d_in_currency": pct_30d,
    }


def build_history(conn, token_id, run_date, days=90):
    """Build CoinGecko market_chart-compatible history from DB data."""
    rows = conn.execute("""
        SELECT date, close, volume, market_cap
        FROM crypto_price_history
        WHERE token_id = ? AND date >= date(?, ?) AND date <= ?
        ORDER BY date ASC
    """, (token_id, run_date, f"-{days} days", run_date)).fetchall()

    if not rows:
        return None

    prices = []
    volumes = []
    market_caps = []
    for r in rows:
        # Convert date to timestamp ms (approximate)
        try:
            ts = int(datetime.strptime(r["date"], "%Y-%m-%d").timestamp() * 1000)
        except:
            continue
        if r["close"]:
            prices.append([ts, r["close"]])
        if r["volume"]:
            volumes.append([ts, r["volume"]])
        if r["market_cap"]:
            market_caps.append([ts, r["market_cap"]])

    return {
        "prices": prices,
        "total_volumes": volumes,
        "market_caps": market_caps,
    }


def main():
    conn = connect()
    ensure_tables(conn)

    # Get tokens that had ratings in Feb (our known universe)
    rated_tokens = conn.execute("""
        SELECT DISTINCT token_id FROM crypto_rating_daily
        WHERE run_date = '2026-02-28'
    """).fetchall()

    token_ids = [r["token_id"] for r in rated_tokens if r["token_id"] not in STABLECOINS]
    print(f"Bootstrapping {len(token_ids)} tokens for {RUN_DATE}")

    # BTC history for contagion pillar
    btc_history = build_history(conn, "bitcoin", RUN_DATE, days=90)
    btc_prices = btc_history["prices"] if btc_history else []

    saved = 0
    errors = 0

    for i, tid in enumerate(token_ids):
        if (i + 1) % 50 == 0:
            print(f"  Processing {i+1}/{len(token_ids)}...")

        token = build_token_dict(conn, tid, RUN_DATE)
        if not token:
            errors += 1
            continue

        history = build_history(conn, tid, RUN_DATE, days=90)

        try:
            result = compute_rating(token, history, btc_prices)

            conn.execute("""
                INSERT OR REPLACE INTO crypto_rating_daily
                (run_date, token_id, symbol, name, market_cap_rank,
                 rating, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5,
                 breakdown, price_usd, market_cap, volume_24h,
                 price_change_24h, price_change_7d, price_change_30d,
                 calculated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                RUN_DATE, tid,
                token.get("symbol", ""),
                token.get("name", ""),
                token.get("market_cap_rank"),
                result["rating"], result["score"],
                result["pillars"][0], result["pillars"][1],
                result["pillars"][2], result["pillars"][3], result["pillars"][4],
                json.dumps(result["breakdown"]),
                token.get("current_price"),
                token.get("market_cap"),
                token.get("total_volume"),
                token.get("price_change_percentage_24h"),
                token.get("price_change_percentage_7d_in_currency"),
                token.get("price_change_percentage_30d_in_currency"),
                datetime.now().isoformat(),
            ))
            saved += 1

        except Exception as e:
            print(f"  ERROR rating {tid}: {e}")
            errors += 1

    conn.commit()
    print(f"\nSaved {saved} ratings, {errors} errors/skipped")

    # Also save to crypto_rating_history for this month
    ym = RUN_DATE[:7]
    for tid in token_ids:
        row = conn.execute("""
            SELECT token_id, rating, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5, breakdown
            FROM crypto_rating_daily WHERE run_date = ? AND token_id = ?
        """, (RUN_DATE, tid)).fetchone()
        if row:
            conn.execute("""
                INSERT OR REPLACE INTO crypto_rating_history
                (year_month, token_id, rating, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5, breakdown, calculated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (ym, row["token_id"], row["rating"], row["score"],
                  row["pillar_1"], row["pillar_2"], row["pillar_3"],
                  row["pillar_4"], row["pillar_5"], row["breakdown"],
                  datetime.now().isoformat()))
    conn.commit()
    print(f"Saved {ym} to crypto_rating_history (for future --cached runs)")

    print_summary(conn, RUN_DATE)
    conn.close()


if __name__ == "__main__":
    main()
