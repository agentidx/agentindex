#!/usr/bin/env python3
"""
NERQ CRYPTO — Multi-Source Price Pipeline
============================================
Fetches OHLCV data directly from exchanges and DeFi sources.
NO single vendor dependency. NO wrappers.

Sources (all free, no API key required for market data):
  1. Binance      — ~600 USDT pairs, 1d OHLCV candles
  2. Coinbase     — ~500 USD pairs, 1d OHLCV candles
  3. Kraken       — ~300 USD pairs, 1d OHLCV candles
  4. OKX          — ~400 USDT pairs, 1d OHLCV candles
  5. DeFiLlama   — ~5,000 tokens, daily price + TVL (no OHLCV)

Strategy:
  - For each token, try sources in order until we get data
  - Store source alongside data for transparency
  - Map exchange symbols back to our token_id (CoinGecko format)
  - Daily cron: fetch last 90 days for new tokens, last 1 day for existing

Output: crypto_price_history table in crypto_trust.db (same format as existing)

Usage:
  python3 crypto_price_pipeline.py                    # Daily update (last 2 days)
  python3 crypto_price_pipeline.py --backfill 90      # Backfill 90 days
  python3 crypto_price_pipeline.py --exchange binance  # Only Binance
  python3 crypto_price_pipeline.py --list-coverage     # Show coverage stats

Author: NERQ
Version: 1.0
Date: 2026-02-27
"""

import sqlite3
import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict

try:
    import requests
except ImportError:
    print("pip install requests --break-system-packages")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CRYPTO_DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")
DATA_DB_PATH = os.path.join(SCRIPT_DIR, "..", "data", "crypto_trust.db")

# Rate limits (requests per second)
RATE_LIMITS = {
    "binance": 0.15,     # ~6/sec allowed, we use ~7/sec
    "coinbase": 0.35,    # ~3/sec
    "kraken": 1.1,       # ~1/sec
    "okx": 0.25,         # ~4/sec
    "defillama": 0.5,    # ~2/sec
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


# ─────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────
def connect_crypto_db():
    conn = sqlite3.connect(CRYPTO_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def connect_data_db():
    if not os.path.exists(DATA_DB_PATH):
        return None
    conn = sqlite3.connect(DATA_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables(conn):
    """Add source column if not exists."""
    # Check if source column exists
    cols = [r[1] for r in conn.execute("PRAGMA table_info(crypto_price_history)").fetchall()]
    if "source" not in cols:
        conn.execute("ALTER TABLE crypto_price_history ADD COLUMN source TEXT DEFAULT 'coingecko'")
        conn.commit()
        log.info("Added 'source' column to crypto_price_history")

    # Pipeline status table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_pipeline_status (
            token_id TEXT PRIMARY KEY,
            symbol TEXT,
            name TEXT,
            source TEXT,
            exchange_symbol TEXT,
            last_fetched TEXT,
            rows_total INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()


# ─────────────────────────────────────────────────────────────
# SYMBOL MAPPING: exchange symbols → our token_id
# ─────────────────────────────────────────────────────────────
def build_symbol_map(data_conn):
    """
    Build mapping from exchange trading symbols to our token_id.
    Uses the data DB (18,291 tokens) as the canonical source.
    Returns: {"BTC": "bitcoin", "ETH": "ethereum", ...}
    """
    if not data_conn:
        # Fallback: use crypto_fetch_status
        return {}

    rows = data_conn.execute("""
        SELECT id, symbol, name FROM crypto_tokens
        WHERE current_price_usd > 0
        ORDER BY market_cap_rank ASC NULLS LAST
    """).fetchall()

    # symbol (uppercase) → token_id, first match wins (highest mcap)
    sym_map = {}
    for r in rows:
        sym = r["symbol"].upper()
        if sym not in sym_map:
            sym_map[sym] = r["id"]

    log.info(f"Symbol map: {len(sym_map)} tokens")
    return sym_map


# ─────────────────────────────────────────────────────────────
# EXCHANGE: BINANCE
# ─────────────────────────────────────────────────────────────
class BinanceSource:
    """Binance public API — no key required for market data."""
    BASE = "https://api.binance.com/api/v3"
    NAME = "binance"

    @staticmethod
    def get_all_pairs():
        """Get all USDT trading pairs."""
        try:
            resp = requests.get(f"{BinanceSource.BASE}/exchangeInfo", timeout=15)
            resp.raise_for_status()
            data = resp.json()
            pairs = []
            for s in data["symbols"]:
                if s["quoteAsset"] == "USDT" and s["status"] == "TRADING":
                    pairs.append({
                        "symbol": s["baseAsset"].upper(),
                        "exchange_pair": s["symbol"],  # e.g. "BTCUSDT"
                    })
            return pairs
        except Exception as e:
            log.error(f"Binance pairs error: {e}")
            return []

    @staticmethod
    def fetch_ohlcv(exchange_pair, days=90):
        """Fetch daily OHLCV candles."""
        try:
            end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

            resp = requests.get(f"{BinanceSource.BASE}/klines", params={
                "symbol": exchange_pair,
                "interval": "1d",
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": min(days + 1, 1000),
            }, timeout=15)
            resp.raise_for_status()

            candles = []
            for c in resp.json():
                candles.append({
                    "date": datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": float(c[5]) * float(c[4]),  # base_vol * close = USD volume
                })
            return candles
        except Exception as e:
            log.debug(f"Binance {exchange_pair}: {e}")
            return []


# ─────────────────────────────────────────────────────────────
# EXCHANGE: COINBASE
# ─────────────────────────────────────────────────────────────
class CoinbaseSource:
    """Coinbase public API — no key required."""
    BASE = "https://api.exchange.coinbase.com"
    NAME = "coinbase"

    @staticmethod
    def get_all_pairs():
        try:
            resp = requests.get(f"{CoinbaseSource.BASE}/products", timeout=15)
            resp.raise_for_status()
            pairs = []
            for p in resp.json():
                if p.get("quote_currency") == "USD" and p.get("status") == "online":
                    pairs.append({
                        "symbol": p["base_currency"].upper(),
                        "exchange_pair": p["id"],  # e.g. "BTC-USD"
                    })
            return pairs
        except Exception as e:
            log.error(f"Coinbase pairs error: {e}")
            return []

    @staticmethod
    def fetch_ohlcv(exchange_pair, days=90):
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=days)

            # Coinbase max 300 candles per request
            candles = []
            chunk_start = start

            while chunk_start < end:
                chunk_end = min(chunk_start + timedelta(days=299), end)
                resp = requests.get(
                    f"{CoinbaseSource.BASE}/products/{exchange_pair}/candles",
                    params={
                        "start": chunk_start.isoformat(),
                        "end": chunk_end.isoformat(),
                        "granularity": 86400,  # daily
                    }, timeout=15
                )
                resp.raise_for_status()
                data = resp.json()

                for c in data:
                    # Coinbase: [time, low, high, open, close, volume]
                    candles.append({
                        "date": datetime.fromtimestamp(c[0], tz=timezone.utc).strftime("%Y-%m-%d"),
                        "open": float(c[3]),
                        "high": float(c[2]),
                        "low": float(c[1]),
                        "close": float(c[4]),
                        "volume": float(c[5]) * float(c[4]),
                    })
                chunk_start = chunk_end + timedelta(days=1)
                time.sleep(RATE_LIMITS["coinbase"])

            return sorted(candles, key=lambda x: x["date"])
        except Exception as e:
            log.debug(f"Coinbase {exchange_pair}: {e}")
            return []


# ─────────────────────────────────────────────────────────────
# EXCHANGE: KRAKEN
# ─────────────────────────────────────────────────────────────
class KrakenSource:
    """Kraken public API — no key required."""
    BASE = "https://api.kraken.com/0/public"
    NAME = "kraken"

    # Kraken uses non-standard symbols
    SYMBOL_MAP = {
        "XBT": "BTC", "XXBT": "BTC", "XETH": "ETH", "XXRP": "XRP",
        "XLTC": "LTC", "XXLM": "XLM", "XDOGE": "DOGE",
    }

    @staticmethod
    def get_all_pairs():
        try:
            resp = requests.get(f"{KrakenSource.BASE}/AssetPairs", timeout=15)
            resp.raise_for_status()
            data = resp.json()
            pairs = []
            for name, info in data.get("result", {}).items():
                quote = info.get("quote", "")
                if quote in ("ZUSD", "USD"):
                    base = info.get("base", "")
                    # Normalize symbol
                    sym = KrakenSource.SYMBOL_MAP.get(base, base.lstrip("XZ"))
                    pairs.append({
                        "symbol": sym.upper(),
                        "exchange_pair": name,
                    })
            return pairs
        except Exception as e:
            log.error(f"Kraken pairs error: {e}")
            return []

    @staticmethod
    def fetch_ohlcv(exchange_pair, days=90):
        try:
            since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
            resp = requests.get(f"{KrakenSource.BASE}/OHLC", params={
                "pair": exchange_pair,
                "interval": 1440,  # daily
                "since": since,
            }, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            candles = []
            for key, rows in data.get("result", {}).items():
                if key == "last":
                    continue
                for c in rows:
                    candles.append({
                        "date": datetime.fromtimestamp(c[0], tz=timezone.utc).strftime("%Y-%m-%d"),
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[6]),  # already in quote currency
                    })
            return sorted(candles, key=lambda x: x["date"])
        except Exception as e:
            log.debug(f"Kraken {exchange_pair}: {e}")
            return []


# ─────────────────────────────────────────────────────────────
# EXCHANGE: OKX
# ─────────────────────────────────────────────────────────────
class OKXSource:
    """OKX public API — no key required for market data."""
    BASE = "https://www.okx.com/api/v5"
    NAME = "okx"

    @staticmethod
    def get_all_pairs():
        try:
            resp = requests.get(f"{OKXSource.BASE}/public/instruments",
                                params={"instType": "SPOT"}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            pairs = []
            for inst in data.get("data", []):
                if inst["quoteCcy"] == "USDT" and inst["state"] == "live":
                    pairs.append({
                        "symbol": inst["baseCcy"].upper(),
                        "exchange_pair": inst["instId"],  # e.g. "BTC-USDT"
                    })
            return pairs
        except Exception as e:
            log.error(f"OKX pairs error: {e}")
            return []

    @staticmethod
    def fetch_ohlcv(exchange_pair, days=90):
        try:
            # OKX returns max 100 candles, need to paginate
            candles = []
            after = ""

            for _ in range(max(1, days // 100 + 1)):
                params = {"instId": exchange_pair, "bar": "1D", "limit": "100"}
                if after:
                    params["after"] = after

                resp = requests.get(f"{OKXSource.BASE}/market/candles",
                                    params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json().get("data", [])
                if not data:
                    break

                for c in data:
                    ts = int(c[0]) / 1000
                    d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
                    if d < cutoff:
                        continue
                    candles.append({
                        "date": d,
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]) * float(c[4]),  # base * close
                    })
                after = data[-1][0]
                time.sleep(RATE_LIMITS["okx"])

            return sorted(candles, key=lambda x: x["date"])
        except Exception as e:
            log.debug(f"OKX {exchange_pair}: {e}")
            return []


# ─────────────────────────────────────────────────────────────
# SOURCE: DEFILLAMA (price history, no OHLCV)
# ─────────────────────────────────────────────────────────────
class DefiLlamaSource:
    """DeFiLlama — free, open, no key. Daily close + volume only."""
    BASE = "https://coins.llama.fi"
    NAME = "defillama"

    @staticmethod
    def fetch_price_history(coingecko_id, days=90):
        """Fetch daily prices using CoinGecko ID mapping."""
        try:
            # DeFiLlama accepts coingecko: prefix
            coin_key = f"coingecko:{coingecko_id}"
            end = int(datetime.now(timezone.utc).timestamp())
            start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
            period = "1d"

            resp = requests.get(
                f"{DefiLlamaSource.BASE}/chart/{coin_key}",
                params={"start": start, "span": days, "period": period},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()

            candles = []
            coins = data.get("coins", {})
            if coin_key in coins:
                for pt in coins[coin_key].get("prices", []):
                    d = datetime.fromtimestamp(pt["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d")
                    price = pt["price"]
                    candles.append({
                        "date": d,
                        "open": price,
                        "high": price,  # no OHLC, just close
                        "low": price,
                        "close": price,
                        "volume": 0,  # DeFiLlama chart doesn't give volume
                    })
            return candles
        except Exception as e:
            log.debug(f"DeFiLlama {coingecko_id}: {e}")
            return []


# ─────────────────────────────────────────────────────────────
# PIPELINE ORCHESTRATOR
# ─────────────────────────────────────────────────────────────
SOURCES = [BinanceSource, CoinbaseSource, KrakenSource, OKXSource]


def discover_exchange_coverage(sym_map):
    """Discover which tokens are available on which exchanges."""
    coverage = defaultdict(dict)  # symbol → {exchange: exchange_pair}

    for source_cls in SOURCES:
        log.info(f"  Discovering {source_cls.NAME} pairs...")
        pairs = source_cls.get_all_pairs()
        matched = 0
        for p in pairs:
            sym = p["symbol"]
            if sym in sym_map:
                token_id = sym_map[sym]
                coverage[token_id][source_cls.NAME] = p["exchange_pair"]
                matched += 1
        log.info(f"    {source_cls.NAME}: {len(pairs)} pairs, {matched} matched to our tokens")
        time.sleep(1)

    return coverage


def fetch_token_data(token_id, coverage_entry, days=90):
    """Try each exchange in order until we get data."""
    source_order = ["binance", "coinbase", "okx", "kraken"]
    source_map = {
        "binance": BinanceSource,
        "coinbase": CoinbaseSource,
        "kraken": KrakenSource,
        "okx": OKXSource,
    }

    for src_name in source_order:
        if src_name not in coverage_entry:
            continue
        exchange_pair = coverage_entry[src_name]
        source_cls = source_map[src_name]

        candles = source_cls.fetch_ohlcv(exchange_pair, days=days)
        if candles and len(candles) >= 5:
            return candles, src_name, exchange_pair

        time.sleep(RATE_LIMITS.get(src_name, 0.5))

    # Fallback: DeFiLlama
    candles = DefiLlamaSource.fetch_price_history(token_id, days=days)
    if candles and len(candles) >= 5:
        return candles, "defillama", token_id

    return [], None, None


def save_candles(conn, token_id, candles, source):
    """Save candles to crypto_price_history."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    saved = 0

    for c in candles:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO crypto_price_history
                (token_id, date, open, high, low, close, volume, market_cap, fetched_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """, (
                token_id, c["date"], c["open"], c["high"], c["low"],
                c["close"], c["volume"], now, source,
            ))
            saved += 1
        except Exception as e:
            log.debug(f"Save error {token_id} {c['date']}: {e}")

    conn.commit()
    return saved


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────
def run_pipeline(days=2, exchange_filter=None, max_tokens=None):
    t0 = time.time()

    crypto_conn = connect_crypto_db()
    data_conn = connect_data_db()
    ensure_tables(crypto_conn)

    # Build symbol map from data DB
    sym_map = build_symbol_map(data_conn)
    if not sym_map:
        # Fallback: build from fetch_status
        rows = crypto_conn.execute(
            "SELECT token_id, symbol FROM crypto_fetch_status WHERE status='completed'"
        ).fetchall()
        sym_map = {r["symbol"].upper(): r["token_id"] for r in rows if r["symbol"]}
        log.info(f"Fallback symbol map: {len(sym_map)} tokens")

    # Discover exchange coverage
    log.info(f"\nDiscovering exchange coverage...")
    coverage = discover_exchange_coverage(sym_map)
    log.info(f"Total tokens with exchange coverage: {len(coverage)}")

    # Add DeFiLlama fallback for tokens in data DB but not on exchanges
    if data_conn:
        all_tokens = data_conn.execute("""
            SELECT id FROM crypto_tokens
            WHERE current_price_usd > 0 AND total_volume_24h_usd > 1000
            ORDER BY market_cap_rank ASC NULLS LAST
        """).fetchall()
        defillama_only = 0
        for r in all_tokens:
            tid = r["id"]
            if tid not in coverage:
                coverage[tid] = {"defillama": tid}
                defillama_only += 1
        log.info(f"DeFiLlama fallback: {defillama_only} additional tokens")

    # Get existing tokens (to skip if recent data exists)
    existing = {}
    rows = crypto_conn.execute("""
        SELECT token_id, MAX(date) as last_date, COUNT(*) as n
        FROM crypto_price_history GROUP BY token_id
    """).fetchall()
    for r in rows:
        existing[r["token_id"]] = {"last_date": r["last_date"], "n": r["n"]}

    # Determine which tokens need updating
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    tokens_to_fetch = []
    for token_id, sources in coverage.items():
        if exchange_filter and exchange_filter not in sources:
            continue
        ex = existing.get(token_id)
        if ex and ex["last_date"] >= yesterday and days <= 2:
            continue  # already up to date
        # New token: fetch full history; existing: just update
        fetch_days = days if (ex and ex["n"] >= 60) else max(days, 90)
        tokens_to_fetch.append((token_id, sources, fetch_days))

    if max_tokens:
        tokens_to_fetch = tokens_to_fetch[:max_tokens]

    log.info(f"\nTokens to fetch: {len(tokens_to_fetch)} (of {len(coverage)} covered)")

    # Fetch data
    stats = defaultdict(int)
    errors = 0

    for i, (token_id, sources, fetch_days) in enumerate(tokens_to_fetch):
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            log.info(f"  Progress: {i+1}/{len(tokens_to_fetch)} ({elapsed:.0f}s)")

        candles, source, ex_pair = fetch_token_data(token_id, sources, days=fetch_days)

        if candles:
            saved = save_candles(crypto_conn, token_id, candles, source)
            stats[source] += 1

            # Update pipeline status
            crypto_conn.execute("""
                INSERT OR REPLACE INTO crypto_pipeline_status
                (token_id, source, exchange_symbol, last_fetched, rows_total, status)
                VALUES (?, ?, ?, ?, ?, 'active')
            """, (token_id, source, ex_pair, today, saved))
        else:
            errors += 1
            stats["failed"] += 1

        # Rate limiting
        rate = RATE_LIMITS.get(source, 0.5) if source else 0.2
        time.sleep(rate)

    crypto_conn.commit()
    elapsed = time.time() - t0

    # ── RESULTS ──────────────────────────────────────────────
    log.info(f"\n{'='*70}")
    log.info(f"  PIPELINE COMPLETE ({elapsed:.1f}s)")
    log.info(f"{'='*70}")
    for src, count in sorted(stats.items()):
        log.info(f"  {src:<15} {count:>6} tokens")
    log.info(f"  {'errors':<15} {errors:>6}")

    # Total coverage
    total = crypto_conn.execute("SELECT COUNT(DISTINCT token_id) FROM crypto_price_history").fetchone()[0]
    recent = crypto_conn.execute("""
        SELECT COUNT(DISTINCT token_id) FROM crypto_price_history
        WHERE date >= date('now', '-7 days')
    """).fetchone()[0]
    log.info(f"\n  Total tokens with OHLCV: {total}")
    log.info(f"  Updated in last 7 days:  {recent}")

    # Source distribution
    src_dist = crypto_conn.execute("""
        SELECT source, COUNT(DISTINCT token_id) FROM crypto_price_history
        WHERE source IS NOT NULL GROUP BY source ORDER BY COUNT(*) DESC
    """).fetchall()
    if src_dist:
        log.info(f"\n  Source distribution:")
        for src, count in src_dist:
            log.info(f"    {src or 'legacy':<15} {count:>6} tokens")

    crypto_conn.close()
    if data_conn:
        data_conn.close()

    return stats


def list_coverage():
    """Show coverage statistics."""
    data_conn = connect_data_db()
    sym_map = build_symbol_map(data_conn)
    coverage = discover_exchange_coverage(sym_map)

    # Count per exchange
    ex_counts = defaultdict(int)
    for tid, sources in coverage.items():
        for ex in sources:
            ex_counts[ex] += 1

    print(f"\n  Exchange Coverage:")
    for ex, count in sorted(ex_counts.items(), key=lambda x: -x[1]):
        print(f"    {ex:<15} {count:>6} tokens")

    # Tokens on multiple exchanges
    multi = sum(1 for s in coverage.values() if len(s) >= 2)
    single = sum(1 for s in coverage.values() if len(s) == 1)
    print(f"\n  Multi-exchange:  {multi}")
    print(f"  Single-exchange: {single}")
    print(f"  Total covered:   {len(coverage)}")

    if data_conn:
        total_tokens = data_conn.execute(
            "SELECT COUNT(*) FROM crypto_tokens WHERE current_price_usd > 0"
        ).fetchone()[0]
        print(f"  Total in data DB: {total_tokens}")
        print(f"  Coverage:         {len(coverage)/total_tokens*100:.1f}%")
        data_conn.close()


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NERQ Multi-Source Price Pipeline")
    parser.add_argument("--backfill", type=int, default=2,
                        help="Days to fetch (default 2 = daily update)")
    parser.add_argument("--exchange", type=str, default=None,
                        help="Only fetch from specific exchange")
    parser.add_argument("--max", type=int, default=None,
                        help="Max tokens to fetch")
    parser.add_argument("--list-coverage", action="store_true",
                        help="Show coverage statistics")
    args = parser.parse_args()

    print("=" * 70)
    print("  NERQ CRYPTO — Multi-Source Price Pipeline v1.0")
    print("  Sources: Binance + Coinbase + Kraken + OKX + DeFiLlama")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    if args.list_coverage:
        list_coverage()
        return

    run_pipeline(
        days=args.backfill,
        exchange_filter=args.exchange,
        max_tokens=args.max,
    )
    print("\n  Done.")


if __name__ == "__main__":
    main()


# ─────────────────────────────────────────────────────────────
# LAUNCHAGENT
# ─────────────────────────────────────────────────────────────
# Save as: ~/Library/LaunchAgents/com.nerq.crypto-pipeline.plist
# Kör 06:00 UTC (07:00 CET), innan rating + NDD
# <key>StartCalendarInterval</key>
# <dict>
#     <key>Hour</key><integer>6</integer>
#     <key>Minute</key><integer>0</integer>
# </dict>
