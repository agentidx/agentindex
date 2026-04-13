#!/usr/bin/env python3
"""Quick price fetch for paper trading tokens only. Runs in <60 seconds."""
import sqlite3, requests, time, os, sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")
PT_DB_PATH = os.path.join(SCRIPT_DIR, "paper_trading.db")

def fetch_price_coingecko(token_id):
    """Fetch current price from CoinGecko free API with retry."""
    env_path = os.path.join(SCRIPT_DIR, ".env")
    headers = {}
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("COINGECKO_API_KEY="):
                headers["x-cg-demo-api-key"] = line.strip().split("=", 1)[1]
    for attempt in range(3):
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={token_id}&vs_currencies=usd"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            data = r.json()
            if token_id in data:
                return data[token_id].get("usd", 0)
        except Exception as e:
            print(f"  CoinGecko attempt {attempt+1} failed for {token_id}: {e}")
    return None

def fetch_price_binance(symbol):
    """Fetch from Binance as fallback."""
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        r = requests.get(url, timeout=10)
        data = r.json()
        return float(data.get("price", 0))
    except:
        return None

BINANCE_MAP = {
    "bitcoin": "BTC", "ethereum": "ETH", "the-open-network": "TON",
    "zcash": "ZEC", "cosmos": "ATOM", "pepe": "PEPE",
    "crypto-com-chain": "CRO", "cronos": "CRO", "algorand": "ALGO",
}

def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"  Quick Price Fetch — {today}")

    pt_conn = sqlite3.connect(PT_DB_PATH)
    tokens = set()
    for r in pt_conn.execute("SELECT DISTINCT token_id FROM portfolio_positions WHERE token_id != 'USD'").fetchall():
        tokens.add(r[0])
    tokens.add("bitcoin")  # Always need BTC
    # CoinGecko ID aliases
    ALIASES = {"crypto-com-chain": "crypto-com-chain"}
    pt_conn.close()

    print(f"  Tokens to fetch: {sorted(tokens)}")

    trust_conn = sqlite3.connect(DB_PATH)
    fetched = 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    for token_id in sorted(tokens):
        price = fetch_price_coingecko(token_id)
        if not price and token_id in BINANCE_MAP:
            price = fetch_price_binance(BINANCE_MAP[token_id])

        if price and price > 0:
            from agentindex.crypto.dual_write import dual_execute
            dual_execute(trust_conn, """
                INSERT OR REPLACE INTO crypto_price_history
                (token_id, date, open, high, low, close, volume, market_cap, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)
            """, (token_id, today, price, price, price, price, now))
            print(f"  {token_id:25s} = ${price}")
            fetched += 1
        else:
            print(f"  {token_id:25s} = FAILED")
        time.sleep(2.5)

    trust_conn.commit()
    trust_conn.close()
    print(f"  Done: {fetched}/{len(tokens)} prices updated")

if __name__ == "__main__":
    main()
