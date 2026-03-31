#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 2.1: Daily Credit Rating Engine
======================================================
Runs daily at 06:00 UTC via LaunchAgent.
Fetches latest price data, computes credit rating for top 200 tokens,
saves to DB with full breakdown.

Usage:
  python3 crypto_rating_daily.py              # Run for today
  python3 crypto_rating_daily.py --backfill 7 # Backfill last 7 days

LaunchAgent: crypto_rating_daily.plist (see bottom of file for template)

Author: NERQ
Version: 1.0
Date: 2026-02-26
"""

import sqlite3
import os
import sys
import json
import math
import argparse
import time
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

DB_NAME = "crypto_trust.db"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)

# ─────────────────────────────────────────────────────────────
# FROZEN PARAMETERS (from Sprint 1 optimization)
# ─────────────────────────────────────────────────────────────
PILLAR_WEIGHTS = [0.15, 0.25, 0.25, 0.20, 0.15]
# Pillars: Security(Rug Pull), Compliance(Contagion), Maintenance(Resilience),
#          Popularity(Fundamental), Ecosystem

RATING_THRESHOLDS = [
    (95, "Aaa"), (90, "Aa1"), (85, "Aa2"), (80, "Aa3"),
    (75, "A1"),  (70, "A2"),  (65, "A3"),
    (60, "Baa1"), (55, "Baa2"), (50, "Baa3"),
    (45, "Ba1"), (40, "Ba2"), (35, "Ba3"),
    (30, "B1"),  (25, "B2"),  (20, "B3"),
    (15, "Caa1"), (10, "Caa2"), (5, "Caa3"),
    (2, "Ca"),   (0, "C"),
]

STABLECOINS = {
    'tether', 'usd-coin', 'binance-usd', 'dai', 'true-usd', 'paxos-standard',
    'gusd', 'frax', 'usdd', 'tusd', 'busd', 'lusd', 'susd', 'eurs', 'usdp',
    'first-digital-usd', 'ethena-usde', 'usde', 'paypal-usd', 'fdusd',
    'stasis-eur', 'gemini-dollar', 'husd', 'nusd', 'musd', 'cusd',
    'terrausd', 'ust', 'magic-internet-money', 'euro-coin', 'ondo-us-dollar-yield',
}

# CoinGecko API config
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
COINGECKO_PRO_BASE = "https://pro-api.coingecko.com/api/v3"
API_KEY = os.environ.get("COINGECKO_API_KEY", "")  # Set via environment
USE_PRO = bool(API_KEY)
RATE_LIMIT_SECONDS = 1.5 if not USE_PRO else 0.5


# ─────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────
def connect():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables(conn):
    """Create daily rating table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_rating_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            token_id TEXT NOT NULL,
            symbol TEXT,
            name TEXT,
            market_cap_rank INTEGER,
            rating TEXT NOT NULL,
            score REAL NOT NULL,
            pillar_1 REAL,
            pillar_2 REAL,
            pillar_3 REAL,
            pillar_4 REAL,
            pillar_5 REAL,
            breakdown TEXT,
            price_usd REAL,
            market_cap REAL,
            volume_24h REAL,
            price_change_24h REAL,
            price_change_7d REAL,
            price_change_30d REAL,
            calculated_at TEXT NOT NULL,
            UNIQUE(run_date, token_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rating_daily_date
        ON crypto_rating_daily(run_date)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rating_daily_token
        ON crypto_rating_daily(token_id, run_date)
    """)
    conn.commit()


# ─────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────
def fetch_top_tokens(n=200):
    """
    Fetch top N tokens by market cap from CoinGecko.
    Returns list of dicts with token data.
    """
    try:
        import requests
    except ImportError:
        print("  ERROR: requests not installed. Run: pip install requests")
        sys.exit(1)

    base = COINGECKO_PRO_BASE if USE_PRO else COINGECKO_BASE
    headers = {"x-cg-pro-api-key": API_KEY} if USE_PRO else {}

    all_tokens = []
    per_page = 250
    pages = math.ceil(n / per_page)

    for page in range(1, pages + 1):
        url = f"{base}/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "24h,7d,30d",
        }

        print(f"    Fetching page {page}/{pages}...")
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            all_tokens.extend(data)
            time.sleep(RATE_LIMIT_SECONDS)
        except Exception as e:
            print(f"    ERROR fetching page {page}: {e}")
            break

    return all_tokens[:n]


def fetch_token_history(token_id, days=90):
    """Fetch price history for a single token."""
    try:
        import requests
    except ImportError:
        return None

    base = COINGECKO_PRO_BASE if USE_PRO else COINGECKO_BASE
    headers = {"x-cg-pro-api-key": API_KEY} if USE_PRO else {}

    url = f"{base}/coins/{token_id}/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval": "daily"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"    ERROR fetching history for {token_id}: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# PILLAR CALCULATIONS
# ─────────────────────────────────────────────────────────────

def calc_pillar_1_rug_pull(token, history):
    """
    Pillar 1: Rug Pull / Security Risk (15%)
    Signals: anomalous volume, extreme moves, dump patterns, rank stability
    """
    scores = {}

    # Volume anomaly — is recent volume wildly different from average?
    if history and "total_volumes" in history:
        vols = [v[1] for v in history["total_volumes"] if v[1] and v[1] > 0]
        if len(vols) >= 14:
            recent = np.mean(vols[-7:])
            older = np.mean(vols[:-7])
            if older > 0:
                ratio = recent / older
                # Ratio close to 1 = stable = good
                if 0.5 <= ratio <= 2.0:
                    scores["anomaly"] = 100
                elif 0.3 <= ratio <= 3.0:
                    scores["anomaly"] = 70
                elif 0.1 <= ratio <= 5.0:
                    scores["anomaly"] = 40
                else:
                    scores["anomaly"] = 10
            else:
                scores["anomaly"] = 50
        else:
            scores["anomaly"] = 50
    else:
        scores["anomaly"] = 50

    # Extreme price moves (flash crash risk)
    if history and "prices" in history:
        prices = [p[1] for p in history["prices"] if p[1] and p[1] > 0]
        if len(prices) >= 7:
            daily_rets = [(prices[i] - prices[i-1]) / prices[i-1]
                          for i in range(1, len(prices)) if prices[i-1] > 0]
            if daily_rets:
                max_drop = min(daily_rets)
                if max_drop > -0.05:
                    scores["extreme"] = 100
                elif max_drop > -0.15:
                    scores["extreme"] = 80
                elif max_drop > -0.30:
                    scores["extreme"] = 50
                elif max_drop > -0.50:
                    scores["extreme"] = 25
                else:
                    scores["extreme"] = 5
            else:
                scores["extreme"] = 50
        else:
            scores["extreme"] = 50
    else:
        scores["extreme"] = 50

    # Dump pattern: sustained decline
    change_30d = token.get("price_change_percentage_30d_in_currency")
    if change_30d is not None:
        if change_30d > -10:
            scores["dump"] = 90
        elif change_30d > -25:
            scores["dump"] = 70
        elif change_30d > -50:
            scores["dump"] = 40
        elif change_30d > -75:
            scores["dump"] = 15
        else:
            scores["dump"] = 5
    else:
        scores["dump"] = 50

    # Market cap rank stability (proxy for legitimacy)
    rank = token.get("market_cap_rank", 999)
    if rank <= 10:
        scores["rank_safety"] = 100
    elif rank <= 30:
        scores["rank_safety"] = 95
    elif rank <= 50:
        scores["rank_safety"] = 90
    elif rank <= 100:
        scores["rank_safety"] = 80
    elif rank <= 200:
        scores["rank_safety"] = 65
    else:
        scores["rank_safety"] = 40

    pillar = np.mean(list(scores.values())) if scores else 50
    return round(pillar, 2), scores


def calc_pillar_2_contagion(token, history, btc_prices=None):
    """
    Pillar 2: Contagion / Compliance Risk (25%)
    Signals: BTC correlation, beta, idiosyncratic risk
    """
    scores = {}

    if history and "prices" in history and btc_prices:
        prices = [p[1] for p in history["prices"] if p[1] and p[1] > 0]
        btc_p = [p[1] for p in btc_prices if p[1] and p[1] > 0]

        min_len = min(len(prices), len(btc_p))
        if min_len >= 30:
            prices = prices[-min_len:]
            btc_p = btc_p[-min_len:]

            tok_rets = np.diff(prices) / prices[:-1]
            btc_rets = np.diff(btc_p) / btc_p[:-1]

            if len(tok_rets) == len(btc_rets) and len(tok_rets) > 10:
                corr = np.corrcoef(tok_rets, btc_rets)[0, 1]
                # Lower correlation = more independent = safer in contagion sense
                # But also: very low correlation could mean manipulation
                if 0.3 <= corr <= 0.7:
                    scores["corr"] = 80  # healthy independence
                elif 0.7 <= corr <= 0.9:
                    scores["corr"] = 50  # high correlation = contagion risk
                elif corr > 0.9:
                    scores["corr"] = 30  # extreme correlation
                elif 0.0 <= corr < 0.3:
                    scores["corr"] = 60  # very independent (could be good or bad)
                else:
                    scores["corr"] = 40  # negative correlation (unusual)

                # Beta
                cov = np.cov(tok_rets, btc_rets)[0, 1]
                var_btc = np.var(btc_rets)
                beta = cov / var_btc if var_btc > 0 else 1.0
                if 0.5 <= beta <= 1.5:
                    scores["beta"] = 80
                elif 1.5 < beta <= 2.0:
                    scores["beta"] = 50
                elif beta > 2.0:
                    scores["beta"] = 20
                else:
                    scores["beta"] = 60  # low beta

                # Idiosyncratic risk
                residuals = tok_rets - beta * btc_rets
                idio_vol = np.std(residuals) * np.sqrt(365)
                if idio_vol < 0.5:
                    scores["idio"] = 80
                elif idio_vol < 1.0:
                    scores["idio"] = 60
                elif idio_vol < 2.0:
                    scores["idio"] = 35
                else:
                    scores["idio"] = 15

    if not scores:
        scores = {"corr": 50, "beta": 50, "idio": 50}

    pillar = np.mean(list(scores.values()))
    return round(pillar, 2), scores


def calc_pillar_3_resilience(token, history):
    """
    Pillar 3: Historical Resilience / Maintenance (25%)
    Signals: max drawdown, recovery ratio, volatility, tail risk
    """
    scores = {}

    if history and "prices" in history:
        prices = [p[1] for p in history["prices"] if p[1] and p[1] > 0]

        if len(prices) >= 30:
            # Max drawdown
            peak = prices[0]
            max_dd = 0
            for p in prices:
                if p > peak:
                    peak = p
                dd = (p - peak) / peak
                if dd < max_dd:
                    max_dd = dd

            if max_dd > -0.10:
                scores["mdd"] = 95
            elif max_dd > -0.20:
                scores["mdd"] = 80
            elif max_dd > -0.30:
                scores["mdd"] = 65
            elif max_dd > -0.50:
                scores["mdd"] = 45
            elif max_dd > -0.70:
                scores["mdd"] = 25
            else:
                scores["mdd"] = 10

            # Recovery: current price vs peak
            recovery = prices[-1] / peak if peak > 0 else 0
            if recovery > 0.95:
                scores["recovery"] = 95
            elif recovery > 0.80:
                scores["recovery"] = 75
            elif recovery > 0.60:
                scores["recovery"] = 55
            elif recovery > 0.40:
                scores["recovery"] = 35
            else:
                scores["recovery"] = 15

            # Annualized volatility
            daily_rets = np.diff(prices) / prices[:-1]
            ann_vol = np.std(daily_rets) * np.sqrt(365)
            if ann_vol < 0.30:
                scores["vol"] = 90
            elif ann_vol < 0.60:
                scores["vol"] = 70
            elif ann_vol < 1.00:
                scores["vol"] = 50
            elif ann_vol < 1.50:
                scores["vol"] = 30
            else:
                scores["vol"] = 10

            # Tail risk: worst 5% of daily returns
            if len(daily_rets) >= 20:
                sorted_rets = sorted(daily_rets)
                n5 = max(1, len(sorted_rets) // 20)
                tail_avg = np.mean(sorted_rets[:n5])
                if tail_avg > -0.05:
                    scores["tail"] = 90
                elif tail_avg > -0.10:
                    scores["tail"] = 70
                elif tail_avg > -0.15:
                    scores["tail"] = 50
                elif tail_avg > -0.25:
                    scores["tail"] = 30
                else:
                    scores["tail"] = 10

    if not scores:
        scores = {"mdd": 50, "recovery": 50, "vol": 50, "tail": 50}

    pillar = np.mean(list(scores.values()))
    return round(pillar, 2), scores


def calc_pillar_4_fundamental(token):
    """
    Pillar 4: Fundamental Quality / Popularity (20%)
    Signals: age, consistency, price trend, market cap stability
    """
    scores = {}

    # Market cap (proxy for maturity)
    mcap = token.get("market_cap", 0) or 0
    if mcap >= 50e9:
        scores["mcap"] = 95
    elif mcap >= 10e9:
        scores["mcap"] = 85
    elif mcap >= 1e9:
        scores["mcap"] = 70
    elif mcap >= 100e6:
        scores["mcap"] = 55
    elif mcap >= 10e6:
        scores["mcap"] = 35
    else:
        scores["mcap"] = 15

    # Volume / market cap ratio (liquidity health)
    vol = token.get("total_volume", 0) or 0
    if mcap > 0:
        vol_ratio = vol / mcap
        if 0.01 <= vol_ratio <= 0.20:
            scores["liquidity"] = 85  # healthy
        elif vol_ratio < 0.01:
            scores["liquidity"] = 40  # illiquid
        elif vol_ratio <= 0.50:
            scores["liquidity"] = 65  # somewhat high
        else:
            scores["liquidity"] = 30  # suspicious volume
    else:
        scores["liquidity"] = 30

    # Price trend (7d and 30d)
    change_7d = token.get("price_change_percentage_7d_in_currency")
    if change_7d is not None:
        if change_7d > 10:
            scores["trend_7d"] = 75
        elif change_7d > 0:
            scores["trend_7d"] = 80
        elif change_7d > -10:
            scores["trend_7d"] = 65
        elif change_7d > -25:
            scores["trend_7d"] = 40
        else:
            scores["trend_7d"] = 20
    else:
        scores["trend_7d"] = 50

    change_30d = token.get("price_change_percentage_30d_in_currency")
    if change_30d is not None:
        if change_30d > 20:
            scores["trend_30d"] = 70
        elif change_30d > 0:
            scores["trend_30d"] = 75
        elif change_30d > -15:
            scores["trend_30d"] = 60
        elif change_30d > -40:
            scores["trend_30d"] = 35
        else:
            scores["trend_30d"] = 15
    else:
        scores["trend_30d"] = 50

    pillar = np.mean(list(scores.values()))
    return round(pillar, 2), scores


def calc_pillar_5_ecosystem(token):
    """
    Pillar 5: Ecosystem Strength (15%)
    Signals: volume stability, market cap rank, trading activity
    """
    scores = {}

    # Rank stability
    rank = token.get("market_cap_rank", 999)
    if rank <= 10:
        scores["rank"] = 100
    elif rank <= 25:
        scores["rank"] = 90
    elif rank <= 50:
        scores["rank"] = 80
    elif rank <= 100:
        scores["rank"] = 65
    elif rank <= 200:
        scores["rank"] = 50
    else:
        scores["rank"] = 25

    # Volume size
    vol = token.get("total_volume", 0) or 0
    if vol >= 1e9:
        scores["vol_size"] = 100
    elif vol >= 100e6:
        scores["vol_size"] = 85
    elif vol >= 10e6:
        scores["vol_size"] = 65
    elif vol >= 1e6:
        scores["vol_size"] = 45
    else:
        scores["vol_size"] = 20

    # ATH ratio (how far from all-time high — proxy for ecosystem health)
    ath = token.get("ath", 0) or 0
    current = token.get("current_price", 0) or 0
    if ath > 0 and current > 0:
        ath_ratio = current / ath
        if ath_ratio > 0.80:
            scores["ath_health"] = 90
        elif ath_ratio > 0.50:
            scores["ath_health"] = 70
        elif ath_ratio > 0.25:
            scores["ath_health"] = 45
        elif ath_ratio > 0.10:
            scores["ath_health"] = 25
        else:
            scores["ath_health"] = 10
    else:
        scores["ath_health"] = 50

    pillar = np.mean(list(scores.values()))
    return round(pillar, 2), scores


# ─────────────────────────────────────────────────────────────
# COMPOSITE RATING
# ─────────────────────────────────────────────────────────────
def score_to_rating(score):
    for threshold, rating in RATING_THRESHOLDS:
        if score >= threshold:
            return rating
    return "C"


def compute_rating(token, history, btc_prices=None):
    """Compute full credit rating for a single token."""
    p1, p1d = calc_pillar_1_rug_pull(token, history)
    p2, p2d = calc_pillar_2_contagion(token, history, btc_prices)
    p3, p3d = calc_pillar_3_resilience(token, history)
    p4, p4d = calc_pillar_4_fundamental(token)
    p5, p5d = calc_pillar_5_ecosystem(token)

    pillars = [p1, p2, p3, p4, p5]
    composite = sum(p * w for p, w in zip(pillars, PILLAR_WEIGHTS))
    rating = score_to_rating(composite)

    return {
        "rating": rating,
        "score": round(composite, 2),
        "pillars": [round(p, 2) for p in pillars],
        "breakdown": {
            "rug_pull_risk": p1d,
            "contagion_risk": p2d,
            "historical_resilience": p3d,
            "fundamental_quality": p4d,
            "ecosystem_strength": p5d,
        },
    }


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────
def run_daily(conn, run_date=None, use_cached=False):
    """
    Run the daily rating pipeline.
    If use_cached=True, uses existing DB data instead of fetching from API.
    """
    if run_date is None:
        run_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n  Run date: {run_date}")

    if use_cached:
        print("  Mode: CACHED (using existing DB data)")
        return run_from_db(conn, run_date)
    else:
        print("  Mode: LIVE (fetching from CoinGecko)")
        return run_from_api(conn, run_date)


def run_from_db(conn, run_date):
    """
    Compute ratings using existing price data in DB.
    Used when API is not available or for backfilling.
    """
    # Get unique tokens with recent data
    ym = run_date[:7]
    rows = conn.execute("""
        SELECT DISTINCT token_id FROM crypto_price_history
        WHERE date >= date(?, '-90 days') AND date <= ?
        ORDER BY token_id
    """, (run_date, run_date)).fetchall()

    token_ids = [r["token_id"] for r in rows if r["token_id"] not in STABLECOINS]
    print(f"  Tokens with data: {len(token_ids)}")

    # Get existing ratings for this month (from crypto_rating_history)
    existing = conn.execute("""
        SELECT token_id, rating, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5, breakdown
        FROM crypto_rating_history WHERE year_month = ?
    """, (ym,)).fetchall()

    if existing:
        print(f"  Found {len(existing)} existing ratings for {ym}")
        # Copy to daily table
        saved = 0
        for r in existing:
            if r["token_id"] in STABLECOINS:
                continue
            try:
                breakdown = r["breakdown"] if r["breakdown"] else "{}"
                conn.execute("""
                    INSERT OR REPLACE INTO crypto_rating_daily
                    (run_date, token_id, rating, score, pillar_1, pillar_2, pillar_3,
                     pillar_4, pillar_5, breakdown, calculated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    run_date, r["token_id"], r["rating"], r["score"],
                    r["pillar_1"], r["pillar_2"], r["pillar_3"],
                    r["pillar_4"], r["pillar_5"], breakdown,
                    datetime.now().isoformat(),
                ))
                saved += 1
            except Exception as e:
                print(f"    Error saving {r['token_id']}: {e}")
        conn.commit()
        print(f"  Saved {saved} ratings to crypto_rating_daily")
        return saved
    else:
        print(f"  No existing ratings for {ym} — need to run from API or run rating engine")
        return 0


def run_from_api(conn, run_date):
    """
    Fetch latest data from CoinGecko and compute fresh ratings.
    """
    print("  Fetching top 200 tokens from CoinGecko...")
    tokens = fetch_top_tokens(200)
    if not tokens:
        print("  ERROR: No tokens fetched. Check API key / rate limits.")
        return 0

    print(f"  Fetched {len(tokens)} tokens")

    # Fetch BTC price history for contagion pillar
    print("  Fetching BTC history...")
    btc_history = fetch_token_history("bitcoin", days=90)
    btc_prices = btc_history.get("prices", []) if btc_history else []

    saved = 0
    errors = 0

    for i, token in enumerate(tokens):
        tid = token.get("id", "")
        if tid in STABLECOINS:
            continue

        # Fetch individual history (for resilience + rug pull pillars)
        if (i + 1) % 20 == 0:
            print(f"    Processing {i+1}/{len(tokens)}...")

        history = fetch_token_history(tid, days=90)
        time.sleep(RATE_LIMIT_SECONDS)

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
                run_date, tid,
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
            print(f"    ERROR rating {tid}: {e}")
            errors += 1

    conn.commit()
    print(f"\n  Saved {saved} ratings, {errors} errors")
    return saved


# ─────────────────────────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────────────────────────
def print_summary(conn, run_date):
    """Print summary of today's ratings."""
    rows = conn.execute("""
        SELECT token_id, symbol, name, market_cap_rank, rating, score,
               pillar_1, pillar_2, pillar_3, pillar_4, pillar_5,
               price_usd, price_change_24h
        FROM crypto_rating_daily
        WHERE run_date = ?
        ORDER BY score DESC
    """, (run_date,)).fetchall()

    if not rows:
        print(f"\n  No ratings found for {run_date}")
        return

    print(f"\n{'='*100}")
    print(f"  DAILY CREDIT RATINGS — {run_date}")
    print(f"{'='*100}")
    print(f"  {'#':>3} {'Symbol':<8} {'Name':<20} {'Rating':>7} {'Score':>6} "
          f"{'Rug':>5} {'Cont':>5} {'Resl':>5} {'Fund':>5} {'Eco':>5} {'Price':>12} {'24h':>8}")
    print(f"  {'-'*98}")

    for i, r in enumerate(rows[:50]):  # Top 50
        price_str = f"${r['price_usd']:,.2f}" if r['price_usd'] else "—"
        change_str = f"{r['price_change_24h']:+.1f}%" if r['price_change_24h'] else "—"
        print(f"  {i+1:>3} {(r['symbol'] or '')::<8} {(r['name'] or '')[:20]:<20} "
              f"{r['rating']:>7} {r['score']:>5.1f} "
              f"{r['pillar_1'] or 0:>5.1f} {r['pillar_2'] or 0:>5.1f} "
              f"{r['pillar_3'] or 0:>5.1f} {r['pillar_4'] or 0:>5.1f} "
              f"{r['pillar_5'] or 0:>5.1f} {price_str:>12} {change_str:>8}")

    # Rating distribution
    dist = defaultdict(int)
    for r in rows:
        # Group: Aaa-Aa = IG_HIGH, A = IG_MID, Baa = IG_LOW, Ba-B = HY, Caa-C = DISTRESS
        rating = r["rating"]
        if rating.startswith("Aa") or rating == "Aaa":
            dist["IG_HIGH"] += 1
        elif rating.startswith("A"):
            dist["IG_MID"] += 1
        elif rating.startswith("Baa"):
            dist["IG_LOW"] += 1
        elif rating.startswith("Ba") or rating.startswith("B"):
            dist["HY"] += 1
        else:
            dist["DISTRESS"] += 1

    print(f"\n  Rating Distribution:")
    for grade in ["IG_HIGH", "IG_MID", "IG_LOW", "HY", "DISTRESS"]:
        count = dist.get(grade, 0)
        bar = "█" * count
        print(f"    {grade:<10} {count:>3} {bar}")

    print(f"\n  Total rated: {len(rows)}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NERQ Daily Credit Rating Engine")
    parser.add_argument("--backfill", type=int, default=0,
                        help="Backfill N days from DB data")
    parser.add_argument("--cached", action="store_true",
                        help="Use cached DB data instead of API")
    parser.add_argument("--date", type=str, default=None,
                        help="Run for specific date (YYYY-MM-DD)")
    args = parser.parse_args()

    print("=" * 80)
    print("  NERQ CRYPTO — Daily Credit Rating Engine v1.0")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print(f"  Database: {DB_PATH}")
    print(f"  API: {'CoinGecko Pro' if USE_PRO else 'CoinGecko Free (rate limited)'}")

    conn = connect()
    ensure_tables(conn)

    if args.backfill > 0:
        print(f"\n  Backfilling {args.backfill} days from DB...")
        for i in range(args.backfill, 0, -1):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            run_daily(conn, run_date=d, use_cached=True)
    else:
        run_date = args.date or datetime.now().strftime("%Y-%m-%d")
        run_daily(conn, run_date=run_date, use_cached=args.cached)

    # Print summary
    run_date = args.date or datetime.now().strftime("%Y-%m-%d")
    print_summary(conn, run_date)

    conn.close()
    print(f"\n  Done.")


if __name__ == "__main__":
    main()


# ─────────────────────────────────────────────────────────────
# LAUNCHAGENT TEMPLATE
# ─────────────────────────────────────────────────────────────
# Save as: ~/Library/LaunchAgents/com.nerq.crypto-rating-daily.plist
#
# <?xml version="1.0" encoding="UTF-8"?>
# <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
# <plist version="1.0">
# <dict>
#     <key>Label</key>
#     <string>com.nerq.crypto-rating-daily</string>
#     <key>ProgramArguments</key>
#     <array>
#         <string>/Users/anstudio/agentindex/venv/bin/python3</string>
#         <string>/Users/anstudio/agentindex/agentindex/crypto/crypto_rating_daily.py</string>
#     </array>
#     <key>StartCalendarInterval</key>
#     <dict>
#         <key>Hour</key>
#         <integer>7</integer>
#         <key>Minute</key>
#         <integer>0</integer>
#     </dict>
#     <key>StandardOutPath</key>
#     <string>/Users/anstudio/agentindex/logs/crypto_rating_daily.log</string>
#     <key>StandardErrorPath</key>
#     <string>/Users/anstudio/agentindex/logs/crypto_rating_daily_err.log</string>
#     <key>EnvironmentVariables</key>
#     <dict>
#         <key>COINGECKO_API_KEY</key>
#         <string>YOUR_KEY_HERE</string>
#     </dict>
# </dict>
# </plist>
#
# Install:
#   mkdir -p ~/agentindex/logs
#   cp com.nerq.crypto-rating-daily.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.nerq.crypto-rating-daily.plist
#
# Test:
#   launchctl start com.nerq.crypto-rating-daily
