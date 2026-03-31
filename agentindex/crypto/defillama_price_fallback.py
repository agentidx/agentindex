#!/usr/bin/env python3
"""
ZARQ — DeFiLlama Price Fallback
==================================
Standalone script to fetch current prices from DeFiLlama when CoinGecko
or exchange sources are unavailable (quota exhausted, rate limited, etc.).

DeFiLlama API:
  - Free, no API key required
  - Generous rate limits (~500 req/min)
  - Accepts CoinGecko IDs via "coingecko:" prefix
  - Batch endpoint: up to 100 tokens per request

Usage:
  python3 defillama_price_fallback.py              # Update all tracked tokens
  python3 defillama_price_fallback.py --days 7      # Backfill last 7 days
  python3 defillama_price_fallback.py --token bitcoin  # Single token
  python3 defillama_price_fallback.py --dry-run     # Show what would be fetched

Author: NERQ
Date: 2026-03-12
"""

import sqlite3
import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    # Fallback to urllib
    import urllib.request
    import urllib.error
    requests = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CRYPTO_DB = os.path.join(SCRIPT_DIR, "crypto_trust.db")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("defillama_fallback")

# DeFiLlama endpoints
CURRENT_PRICES_URL = "https://coins.llama.fi/prices/current/{coins}"
CHART_URL = "https://coins.llama.fi/chart/{coin_key}"
BATCH_SIZE = 50  # tokens per batch request
DELAY = 0.2  # seconds between requests


def fetch_json(url, params=None, timeout=20):
    """Fetch JSON with requests or urllib fallback."""
    if requests:
        try:
            resp = requests.get(url, params=params, timeout=timeout,
                                headers={"User-Agent": "ZARQ-Pipeline/1.0"})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.debug(f"Request failed: {e}")
            return None
    else:
        try:
            if params:
                from urllib.parse import urlencode
                url = f"{url}?{urlencode(params)}"
            req = urllib.request.Request(url, headers={"User-Agent": "ZARQ-Pipeline/1.0"})
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read())
        except Exception as e:
            log.debug(f"Request failed: {e}")
            return None


def get_tracked_tokens():
    """Get all token IDs we track from nerq_risk_signals."""
    conn = sqlite3.connect(CRYPTO_DB)
    rows = conn.execute("SELECT DISTINCT token_id FROM nerq_risk_signals ORDER BY token_id").fetchall()
    conn.close()
    return [r[0] for r in rows]


def fetch_current_prices_batch(token_ids):
    """Fetch current prices for a batch of tokens.

    Uses DeFiLlama's batch price endpoint:
    GET https://coins.llama.fi/prices/current/coingecko:bitcoin,coingecko:ethereum,...

    Returns: {token_id: {"price": float, "timestamp": int, "confidence": float}}
    """
    coins = ",".join(f"coingecko:{tid}" for tid in token_ids)
    url = CURRENT_PRICES_URL.format(coins=coins)
    data = fetch_json(url)
    if not data:
        return {}

    results = {}
    coins_data = data.get("coins", {})
    for tid in token_ids:
        key = f"coingecko:{tid}"
        if key in coins_data:
            info = coins_data[key]
            results[tid] = {
                "price": info.get("price", 0),
                "timestamp": info.get("timestamp", 0),
                "confidence": info.get("confidence", 0),
                "symbol": info.get("symbol", ""),
            }
    return results


def fetch_price_history(token_id, days=7):
    """Fetch daily price history for a single token.

    Returns: [{"date": "YYYY-MM-DD", "close": float}, ...]
    """
    coin_key = f"coingecko:{token_id}"
    end = int(datetime.now(timezone.utc).timestamp())
    start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    data = fetch_json(
        CHART_URL.format(coin_key=coin_key),
        params={"start": start, "span": days, "period": "1d"},
    )
    if not data:
        return []

    candles = []
    coins = data.get("coins", {})
    if coin_key in coins:
        for pt in coins[coin_key].get("prices", []):
            d = datetime.fromtimestamp(pt["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d")
            price = pt["price"]
            candles.append({
                "date": d,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0,
            })
    return candles


def save_prices(conn, token_id, candles, source="defillama"):
    """Upsert price data into crypto_price_history."""
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for c in candles:
        try:
            conn.execute("""
                INSERT INTO crypto_price_history
                    (token_id, date, open, high, low, close, volume, market_cap, fetched_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(token_id, date) DO UPDATE SET
                    close = excluded.close,
                    fetched_at = excluded.fetched_at,
                    source = excluded.source
                WHERE close IS NULL OR close = 0
            """, (
                token_id, c["date"], c["open"], c["high"], c["low"],
                c["close"], c["volume"], now, source,
            ))
            inserted += 1
        except Exception as e:
            log.debug(f"  Insert error {token_id} {c['date']}: {e}")
    return inserted


def find_stale_tokens(conn, max_age_days=2):
    """Find tokens whose price data is stale (older than max_age_days)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    tracked = get_tracked_tokens()

    stale = []
    for tid in tracked:
        row = conn.execute(
            "SELECT MAX(date) as latest FROM crypto_price_history WHERE token_id = ?",
            (tid,)
        ).fetchone()
        if not row or not row[0] or row[0] < cutoff:
            stale.append(tid)

    return stale


def main():
    parser = argparse.ArgumentParser(description="DeFiLlama Price Fallback")
    parser.add_argument("--days", type=int, default=2, help="Days of history to fetch (default: 2)")
    parser.add_argument("--token", type=str, help="Fetch single token")
    parser.add_argument("--stale-only", action="store_true", help="Only fetch tokens with stale data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched")
    args = parser.parse_args()

    conn = sqlite3.connect(CRYPTO_DB)
    conn.execute("PRAGMA journal_mode=WAL")

    # Determine which tokens to fetch
    if args.token:
        tokens = [args.token]
    elif args.stale_only:
        tokens = find_stale_tokens(conn, max_age_days=2)
        log.info(f"Found {len(tokens)} stale tokens")
    else:
        tokens = get_tracked_tokens()

    log.info(f"DeFiLlama fallback: {len(tokens)} tokens, {args.days} days")

    if args.dry_run:
        for t in tokens:
            print(f"  Would fetch: {t}")
        conn.close()
        return

    # Step 1: Batch fetch current prices
    total_updated = 0
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for i in range(0, len(tokens), BATCH_SIZE):
        batch = tokens[i:i + BATCH_SIZE]
        log.info(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} tokens...")

        prices = fetch_current_prices_batch(batch)
        for tid, pdata in prices.items():
            if pdata["price"] and pdata["price"] > 0:
                candle = [{
                    "date": now_str,
                    "open": pdata["price"],
                    "high": pdata["price"],
                    "low": pdata["price"],
                    "close": pdata["price"],
                    "volume": 0,
                }]
                n = save_prices(conn, tid, candle)
                total_updated += n

        conn.commit()
        time.sleep(DELAY)

    # Step 2: If backfill requested (days > 1), fetch history for each token
    if args.days > 1:
        log.info(f"  Backfilling {args.days} days of history...")
        for tid in tokens:
            candles = fetch_price_history(tid, days=args.days)
            if candles:
                n = save_prices(conn, tid, candles)
                total_updated += n
                log.debug(f"    {tid}: {n} candles")
            time.sleep(DELAY)
            if tokens.index(tid) % 50 == 0 and tokens.index(tid) > 0:
                conn.commit()
                log.info(f"    Progress: {tokens.index(tid)}/{len(tokens)}")

    conn.commit()
    conn.close()

    log.info(f"DeFiLlama fallback complete: {total_updated} price updates for {len(tokens)} tokens")


if __name__ == "__main__":
    main()
