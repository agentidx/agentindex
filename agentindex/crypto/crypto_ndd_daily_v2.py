#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 2.2: Daily NDD Engine v2
================================================
Computes NDD (Nearness to Distress/Default) for ALL 15,000+ tokens
using data from the main crawl database (data/crypto_trust.db).

This is NOT a CoinGecko wrapper — it reads from our already-crawled
token database which contains 18,291 tokens with price, volume,
market cap, trust scores, and change data.

Data sources:
  PRIMARY: agentindex/data/crypto_trust.db → crypto_tokens (18,291 tokens)
  SECONDARY: agentindex/crypto/crypto_trust.db → crypto_price_history (210 tokens, OHLCV)
  OUTPUT: agentindex/crypto/crypto_trust.db → crypto_ndd_daily, crypto_ndd_alerts

NDD Signals (7):
  S1: Liquidity health (volume, volume/mcap ratio, volume trend proxy)
  S2: Holder concentration (market cap rank, volume/mcap as proxy)
  S3: Price resilience (7d/30d drawdown, momentum, ATH ratio)
  S4: Fundamental health (trend, panic selling, mcap stability)
  S5: Contagion exposure (trust score correlation, ecosystem dependency)
  S6: Structural integrity (age proxy, trust grade, audit status)
  S7: Relative performance (vs BTC, vs peers)

Alert Levels:
  SAFE:      NDD >= 3.0
  WATCH:     2.0 <= NDD < 3.0
  WARNING:   1.5 <= NDD < 2.0
  DISTRESS:  1.0 <= NDD < 1.5
  EMERGENCY: NDD < 1.0

Usage:
  python3 crypto_ndd_daily.py           # Run for all tokens
  python3 crypto_ndd_daily.py --top 500 # Only top 500 by market cap
  python3 crypto_ndd_daily.py --alerts  # Only show alerts

Author: NERQ
Version: 2.0
Date: 2026-02-27
"""

import sqlite3
import os
import sys
import json
import math
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

# ─────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Main crawl DB with 18,291 tokens
DATA_DB_PATH = os.path.join(SCRIPT_DIR, "..", "data", "crypto_trust.db")
# Backtest/output DB with OHLCV history + pairs + PA
CRYPTO_DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")

# ─────────────────────────────────────────────────────────────
# NDD SIGNAL WEIGHTS
# ─────────────────────────────────────────────────────────────
SIGNAL_WEIGHTS = [0.12, 0.10, 0.22, 0.12, 0.14, 0.15, 0.15]
# s1: Liquidity      0.12
# s2: Holders         0.10
# s3: Resilience      0.22 (most important — price-based distress)
# s4: Fundamental     0.12
# s5: Contagion       0.14
# s6: Structural      0.15
# s7: Relative        0.15

STABLECOINS = {
    'tether', 'usd-coin', 'binance-usd', 'dai', 'true-usd', 'paxos-standard',
    'gusd', 'frax', 'usdd', 'tusd', 'busd', 'lusd', 'susd', 'eurs', 'usdp',
    'first-digital-usd', 'ethena-usde', 'usde', 'paypal-usd', 'fdusd',
    'stasis-eur', 'gemini-dollar', 'husd', 'nusd', 'musd', 'cusd',
    'terrausd', 'ust', 'magic-internet-money', 'euro-coin',
}


# ─────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────
def connect_data_db():
    """Connect to the main crawl database (18,291 tokens)."""
    if not os.path.exists(DATA_DB_PATH):
        print(f"  ERROR: Data DB not found at {DATA_DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(DATA_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def connect_crypto_db():
    """Connect to the backtest/output database."""
    if not os.path.exists(CRYPTO_DB_PATH):
        print(f"  ERROR: Crypto DB not found at {CRYPTO_DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(CRYPTO_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables(conn):
    """Create NDD tables in crypto DB."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_ndd_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            token_id TEXT NOT NULL,
            symbol TEXT,
            name TEXT,
            market_cap_rank INTEGER,
            trust_grade TEXT,
            ndd REAL NOT NULL,
            signal_1 REAL, signal_2 REAL, signal_3 REAL,
            signal_4 REAL, signal_5 REAL, signal_6 REAL, signal_7 REAL,
            alert_level TEXT,
            ndd_7d_ago REAL,
            ndd_trend_7d REAL,
            override_triggered INTEGER DEFAULT 0,
            price_usd REAL,
            market_cap REAL,
            volume_24h REAL,
            breakdown TEXT,
            calculated_at TEXT NOT NULL,
            UNIQUE(run_date, token_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_ndd_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_date TEXT NOT NULL,
            token_id TEXT NOT NULL,
            symbol TEXT,
            alert_level TEXT NOT NULL,
            ndd REAL NOT NULL,
            ndd_previous REAL,
            ndd_change REAL,
            market_cap_rank INTEGER,
            trust_grade TEXT,
            trigger_signals TEXT,
            message TEXT,
            acknowledged INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ndd_daily_v2_date ON crypto_ndd_daily(run_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ndd_daily_v2_token ON crypto_ndd_daily(token_id, run_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ndd_daily_v2_alert ON crypto_ndd_daily(run_date, alert_level)")
    conn.commit()


# ─────────────────────────────────────────────────────────────
# LOAD ALL TOKENS FROM DATA DB
# ─────────────────────────────────────────────────────────────
def load_tokens(data_conn, top_n=None):
    """Load all tokens with price data from the main crawl DB."""
    query = """
        SELECT id as token_id, symbol, name,
               current_price_usd, market_cap_usd, market_cap_rank,
               total_volume_24h_usd,
               price_change_24h_pct, price_change_7d_pct, price_change_30d_pct,
               circulating_supply, total_supply, max_supply,
               ath_usd, ath_date, atl_usd, atl_date,
               fully_diluted_valuation, categories, platforms,
               has_audit, is_verified,
               twitter_followers, reddit_subscribers,
               github_stars, github_forks, github_contributors, github_last_commit,
               trust_score, trust_grade,
               security_score, compliance_score, maintenance_score,
               popularity_score, ecosystem_score,
               crawled_at
        FROM crypto_tokens
        WHERE current_price_usd > 0
          AND total_volume_24h_usd > 0
    """
    if top_n:
        query += f" AND market_cap_rank IS NOT NULL AND market_cap_rank <= {top_n}"
    query += " ORDER BY market_cap_rank ASC NULLS LAST"

    rows = data_conn.execute(query).fetchall()
    return [dict(r) for r in rows]


def load_btc_data(data_conn):
    """Load BTC data for relative performance calculations."""
    row = data_conn.execute("""
        SELECT current_price_usd, price_change_24h_pct,
               price_change_7d_pct, price_change_30d_pct
        FROM crypto_tokens WHERE id = 'bitcoin'
    """).fetchone()
    return dict(row) if row else None


# ─────────────────────────────────────────────────────────────
# SIGNAL 1: LIQUIDITY (12%)
# ─────────────────────────────────────────────────────────────
def calc_signal_1(t):
    """Liquidity health: volume size, volume/mcap ratio, volume sustainability."""
    vol = t.get("total_volume_24h_usd") or 0
    mcap = t.get("market_cap_usd") or 0

    # Absolute volume (0-5)
    if vol >= 1e9:
        vol_score = 5.0
    elif vol >= 100e6:
        vol_score = 4.5
    elif vol >= 10e6:
        vol_score = 4.0
    elif vol >= 1e6:
        vol_score = 3.5
    elif vol >= 100e3:
        vol_score = 2.5
    elif vol >= 10e3:
        vol_score = 1.5
    elif vol >= 1e3:
        vol_score = 1.0
    else:
        vol_score = 0.5

    # Volume/market cap ratio (0-5) — healthy is 1-20%
    if mcap > 0:
        ratio = vol / mcap
        if 0.01 <= ratio <= 0.05:
            ratio_score = 5.0  # very healthy
        elif 0.05 < ratio <= 0.20:
            ratio_score = 4.0  # healthy
        elif 0.005 <= ratio < 0.01:
            ratio_score = 3.0  # low but ok
        elif 0.20 < ratio <= 0.50:
            ratio_score = 3.0  # somewhat high
        elif ratio < 0.005:
            ratio_score = 1.5  # illiquid
        elif ratio <= 1.0:
            ratio_score = 2.0  # suspicious
        else:
            ratio_score = 1.0  # wash trading likely
    else:
        ratio_score = 1.0

    signal = vol_score * 0.5 + ratio_score * 0.5
    return round(signal, 2), {"vol": vol, "ratio": round(vol/mcap, 4) if mcap > 0 else 0}


# ─────────────────────────────────────────────────────────────
# SIGNAL 2: HOLDER CONCENTRATION PROXY (10%)
# ─────────────────────────────────────────────────────────────
def calc_signal_2(t):
    """Holder concentration: rank, FDV/mcap ratio, supply distribution."""
    rank = t.get("market_cap_rank") or 99999
    mcap = t.get("market_cap_usd") or 0
    fdv = t.get("fully_diluted_valuation") or 0
    circ = t.get("circulating_supply") or 0
    total = t.get("total_supply") or 0

    # Rank proxy (higher rank = more distributed typically)
    if rank <= 10:
        rank_score = 5.0
    elif rank <= 30:
        rank_score = 4.5
    elif rank <= 50:
        rank_score = 4.0
    elif rank <= 100:
        rank_score = 3.5
    elif rank <= 200:
        rank_score = 3.0
    elif rank <= 500:
        rank_score = 2.5
    elif rank <= 1000:
        rank_score = 2.0
    elif rank <= 3000:
        rank_score = 1.5
    else:
        rank_score = 1.0

    # Circulating/total supply ratio (low = concentrated/locked)
    if total > 0 and circ > 0:
        supply_ratio = circ / total
        if supply_ratio > 0.80:
            supply_score = 4.5
        elif supply_ratio > 0.50:
            supply_score = 3.5
        elif supply_ratio > 0.25:
            supply_score = 2.5
        elif supply_ratio > 0.10:
            supply_score = 1.5
        else:
            supply_score = 1.0
    else:
        supply_score = 2.5  # unknown

    # FDV/mcap ratio (high = lots of unlocked tokens coming)
    if fdv > 0 and mcap > 0:
        fdv_ratio = fdv / mcap
        if fdv_ratio <= 1.2:
            fdv_score = 4.5  # almost fully diluted
        elif fdv_ratio <= 2.0:
            fdv_score = 3.5
        elif fdv_ratio <= 5.0:
            fdv_score = 2.5
        elif fdv_ratio <= 10.0:
            fdv_score = 1.5
        else:
            fdv_score = 1.0  # massive dilution ahead
    else:
        fdv_score = 2.5

    signal = rank_score * 0.4 + supply_score * 0.3 + fdv_score * 0.3
    return round(signal, 2), {"rank": rank, "supply_ratio": round(circ/total, 2) if total > 0 else 0}


# ─────────────────────────────────────────────────────────────
# SIGNAL 3: PRICE RESILIENCE (22%) — most important
# ─────────────────────────────────────────────────────────────
def calc_signal_3(t):
    """
    Price resilience: momentum, drawdown from ATH, trend acceleration.
    This is the primary crash detection signal.
    """
    change_24h = t.get("price_change_24h_pct") or 0
    change_7d = t.get("price_change_7d_pct") or 0
    change_30d = t.get("price_change_30d_pct") or 0
    price = t.get("current_price_usd") or 0
    ath = t.get("ath_usd") or 0

    # 7-day momentum (0-5)
    if change_7d > 15:
        mom_7d = 4.5
    elif change_7d > 5:
        mom_7d = 4.0
    elif change_7d > 0:
        mom_7d = 3.5
    elif change_7d > -5:
        mom_7d = 3.0
    elif change_7d > -15:
        mom_7d = 2.0
    elif change_7d > -30:
        mom_7d = 1.0
    else:
        mom_7d = 0.5

    # 30-day momentum (0-5)
    if change_30d > 25:
        mom_30d = 4.5
    elif change_30d > 10:
        mom_30d = 4.0
    elif change_30d > 0:
        mom_30d = 3.5
    elif change_30d > -10:
        mom_30d = 3.0
    elif change_30d > -25:
        mom_30d = 2.0
    elif change_30d > -50:
        mom_30d = 1.0
    elif change_30d > -75:
        mom_30d = 0.5
    else:
        mom_30d = 0.2

    # ATH drawdown (0-5)
    if ath > 0 and price > 0:
        ath_ratio = price / ath
        if ath_ratio > 0.90:
            ath_score = 5.0
        elif ath_ratio > 0.70:
            ath_score = 4.0
        elif ath_ratio > 0.50:
            ath_score = 3.5
        elif ath_ratio > 0.30:
            ath_score = 2.5
        elif ath_ratio > 0.10:
            ath_score = 1.5
        elif ath_ratio > 0.01:
            ath_score = 0.8
        else:
            ath_score = 0.3  # >99% from ATH — essentially dead
    else:
        ath_score = 2.5

    # Acceleration: is the decline speeding up?
    # If 7d is worse than 30d/4 → accelerating decline
    weekly_avg_from_30d = change_30d / 4.0 if change_30d else 0
    if change_7d < weekly_avg_from_30d - 5:
        accel_score = 1.0  # accelerating decline
    elif change_7d < weekly_avg_from_30d:
        accel_score = 2.0  # continuing decline
    elif change_7d > weekly_avg_from_30d + 5:
        accel_score = 4.5  # recovering
    else:
        accel_score = 3.0  # stable

    # Flash crash detection (24h)
    if change_24h < -25:
        flash = 0.3
    elif change_24h < -15:
        flash = 1.0
    elif change_24h < -8:
        flash = 2.0
    elif change_24h < -3:
        flash = 3.0
    else:
        flash = 4.0

    signal = (mom_7d * 0.20 + mom_30d * 0.25 + ath_score * 0.25 +
              accel_score * 0.15 + flash * 0.15)
    return round(signal, 2), {
        "change_7d": round(change_7d, 1),
        "change_30d": round(change_30d, 1),
        "change_24h": round(change_24h, 1),
        "ath_ratio": round(price/ath, 4) if ath > 0 else 0,
    }


# ─────────────────────────────────────────────────────────────
# SIGNAL 4: FUNDAMENTAL HEALTH (12%)
# ─────────────────────────────────────────────────────────────
def calc_signal_4(t):
    """Fundamental health: market cap size, community, development activity."""
    mcap = t.get("market_cap_usd") or 0
    twitter = t.get("twitter_followers") or 0
    reddit = t.get("reddit_subscribers") or 0
    github_stars = t.get("github_stars") or 0
    github_contribs = t.get("github_contributors") or 0
    github_commit = t.get("github_last_commit") or ""

    # Market cap (stability proxy)
    if mcap >= 50e9:
        mcap_score = 5.0
    elif mcap >= 10e9:
        mcap_score = 4.5
    elif mcap >= 1e9:
        mcap_score = 4.0
    elif mcap >= 100e6:
        mcap_score = 3.5
    elif mcap >= 10e6:
        mcap_score = 3.0
    elif mcap >= 1e6:
        mcap_score = 2.0
    elif mcap >= 100e3:
        mcap_score = 1.5
    else:
        mcap_score = 1.0

    # Community (social proof)
    community = twitter + reddit
    if community >= 1e6:
        comm_score = 5.0
    elif community >= 100e3:
        comm_score = 4.0
    elif community >= 10e3:
        comm_score = 3.0
    elif community >= 1e3:
        comm_score = 2.0
    else:
        comm_score = 1.0

    # Development activity
    if github_contribs >= 50 and github_stars >= 500:
        dev_score = 5.0
    elif github_contribs >= 20:
        dev_score = 4.0
    elif github_contribs >= 5:
        dev_score = 3.0
    elif github_stars >= 10:
        dev_score = 2.0
    else:
        dev_score = 1.5  # no github = slightly concerning

    signal = mcap_score * 0.5 + comm_score * 0.25 + dev_score * 0.25
    return round(signal, 2), {"mcap": mcap, "community": community, "devs": github_contribs}


# ─────────────────────────────────────────────────────────────
# SIGNAL 5: CONTAGION EXPOSURE (14%)
# ─────────────────────────────────────────────────────────────
def calc_signal_5(t):
    """
    Contagion exposure: how vulnerable is this token to ecosystem-wide shocks.
    Uses trust scores and ecosystem dependency.
    """
    trust = t.get("trust_score") or 0
    security = t.get("security_score") or 0
    compliance = t.get("compliance_score") or 0
    ecosystem = t.get("ecosystem_score") or 0
    categories = t.get("categories") or ""

    # Trust score as contagion proxy (0-100 → 0-5)
    # Low trust = more likely to be affected by contagion
    if trust >= 80:
        trust_signal = 4.5
    elif trust >= 60:
        trust_signal = 3.5
    elif trust >= 40:
        trust_signal = 2.5
    elif trust >= 20:
        trust_signal = 1.5
    else:
        trust_signal = 0.5

    # Security score (vulnerability to exploit)
    if security >= 80:
        sec_signal = 4.5
    elif security >= 60:
        sec_signal = 3.5
    elif security >= 40:
        sec_signal = 2.5
    elif security >= 20:
        sec_signal = 1.5
    else:
        sec_signal = 0.5

    # Category risk — meme coins, leveraged, algorithmic = higher contagion
    high_risk_cats = ["meme", "leveraged", "algorithmic", "rebase", "ponzi"]
    cat_lower = categories.lower() if categories else ""
    cat_penalty = 0
    for hrc in high_risk_cats:
        if hrc in cat_lower:
            cat_penalty += 0.5
    cat_signal = max(1.0, 4.0 - cat_penalty)

    signal = trust_signal * 0.4 + sec_signal * 0.3 + cat_signal * 0.3
    return round(signal, 2), {"trust": trust, "security": security}


# ─────────────────────────────────────────────────────────────
# SIGNAL 6: STRUCTURAL INTEGRITY (15%)
# ─────────────────────────────────────────────────────────────
def calc_signal_6(t):
    """
    Structural integrity: audit status, verification, age, code quality.
    """
    has_audit = t.get("has_audit") or 0
    is_verified = t.get("is_verified") or 0
    trust_grade = t.get("trust_grade") or "F"
    github_issues_total = t.get("github_total_issues") or 0
    github_issues_closed = t.get("github_closed_issues") or 0
    homepage = t.get("homepage") or ""
    rank = t.get("market_cap_rank") or 99999

    # Trust grade (already computed by trust engine)
    grade_map = {
        "A": 5.0, "A+": 5.0, "A-": 4.7,
        "B+": 4.2, "B": 3.8, "B-": 3.5,
        "C+": 3.0, "C": 2.5, "C-": 2.0,
        "D+": 1.5, "D": 1.0, "D-": 0.7,
        "F": 0.5,
    }
    grade_score = grade_map.get(trust_grade, 0.5)

    # Audit status
    audit_score = 4.5 if has_audit else 1.5

    # Verification
    verify_score = 4.0 if is_verified else 2.0

    # Issue resolution rate (code maintenance)
    if github_issues_total > 10:
        resolution = github_issues_closed / github_issues_total
        if resolution > 0.80:
            maint_score = 4.5
        elif resolution > 0.50:
            maint_score = 3.0
        else:
            maint_score = 1.5
    else:
        maint_score = 2.5  # not enough data

    # Has website
    web_score = 3.5 if homepage else 1.5

    signal = (grade_score * 0.35 + audit_score * 0.20 + verify_score * 0.15 +
              maint_score * 0.15 + web_score * 0.15)
    return round(signal, 2), {"grade": trust_grade, "audited": has_audit, "verified": is_verified}


# ─────────────────────────────────────────────────────────────
# SIGNAL 7: RELATIVE PERFORMANCE (15%)
# ─────────────────────────────────────────────────────────────
def calc_signal_7(t, btc_data):
    """Relative performance vs BTC across timeframes."""
    if not btc_data:
        return 3.0, {"status": "no_btc_data"}

    btc_7d = btc_data.get("price_change_7d_pct") or 0
    btc_30d = btc_data.get("price_change_30d_pct") or 0

    tok_7d = t.get("price_change_7d_pct") or 0
    tok_30d = t.get("price_change_30d_pct") or 0

    # 7d relative
    rel_7d = tok_7d - btc_7d
    if rel_7d > 10:
        score_7d = 4.5
    elif rel_7d > 0:
        score_7d = 4.0
    elif rel_7d > -5:
        score_7d = 3.5
    elif rel_7d > -15:
        score_7d = 2.5
    elif rel_7d > -30:
        score_7d = 1.5
    else:
        score_7d = 0.5

    # 30d relative
    rel_30d = tok_30d - btc_30d
    if rel_30d > 20:
        score_30d = 4.5
    elif rel_30d > 0:
        score_30d = 4.0
    elif rel_30d > -10:
        score_30d = 3.0
    elif rel_30d > -25:
        score_30d = 2.0
    elif rel_30d > -50:
        score_30d = 1.0
    else:
        score_30d = 0.5

    signal = score_7d * 0.5 + score_30d * 0.5
    return round(signal, 2), {"rel_7d": round(rel_7d, 1), "rel_30d": round(rel_30d, 1)}


# ─────────────────────────────────────────────────────────────
# COMPOSITE NDD
# ─────────────────────────────────────────────────────────────
def compute_ndd(t, btc_data):
    """Compute NDD from 7 signals using token snapshot data."""
    s1, s1d = calc_signal_1(t)
    s2, s2d = calc_signal_2(t)
    s3, s3d = calc_signal_3(t)
    s4, s4d = calc_signal_4(t)
    s5, s5d = calc_signal_5(t)
    s6, s6d = calc_signal_6(t)
    s7, s7d = calc_signal_7(t, btc_data)

    signals = [s1, s2, s3, s4, s5, s6, s7]
    ndd = sum(s * w for s, w in zip(signals, SIGNAL_WEIGHTS))

    # Override rules
    min_signal = min(signals)
    n_below_1_0 = sum(1 for s in signals if s < 1.0)
    n_below_1_5 = sum(1 for s in signals if s < 1.5)
    n_below_2_0 = sum(1 for s in signals if s < 2.0)

    override = False
    if n_below_1_0 >= 2:
        ndd = min(ndd, 1.0)
        override = True
    elif min_signal < 0.5:
        ndd = min(ndd, 1.0)
        override = True
    elif min_signal < 1.0:
        ndd = min(ndd, 1.5)
        override = True
    elif n_below_1_5 >= 3:
        ndd = min(ndd, 1.5)
        override = True
    elif n_below_2_0 >= 4:
        ndd = min(ndd, 2.0)
        override = True

    # Alert level
    if ndd >= 3.0:
        alert = "SAFE"
    elif ndd >= 2.0:
        alert = "WATCH"
    elif ndd >= 1.5:
        alert = "WARNING"
    elif ndd >= 1.0:
        alert = "DISTRESS"
    else:
        alert = "EMERGENCY"

    return {
        "ndd": round(ndd, 2),
        "signals": [round(s, 2) for s in signals],
        "alert_level": alert,
        "override": override,
        "breakdown": {
            "s1_liquidity": s1d, "s2_holders": s2d, "s3_resilience": s3d,
            "s4_fundamental": s4d, "s5_contagion": s5d,
            "s6_structural": s6d, "s7_relative": s7d,
        },
    }


# ─────────────────────────────────────────────────────────────
# NDD HISTORY LOOKUP
# ─────────────────────────────────────────────────────────────
def get_previous_ndd(crypto_conn, token_id, run_date):
    """Get most recent NDD before this run date."""
    row = crypto_conn.execute("""
        SELECT ndd FROM crypto_ndd_daily
        WHERE token_id = ? AND run_date < ?
        ORDER BY run_date DESC LIMIT 1
    """, (token_id, run_date)).fetchone()
    return row["ndd"] if row else None


# ─────────────────────────────────────────────────────────────
# ALERT GENERATION
# ─────────────────────────────────────────────────────────────
def generate_alert(crypto_conn, t, ndd_result, ndd_prev, run_date):
    """Generate alert for non-SAFE tokens."""
    alert_level = ndd_result["alert_level"]
    ndd = ndd_result["ndd"]
    if alert_level == "SAFE":
        return None

    ndd_change = ndd - ndd_prev if ndd_prev is not None else 0
    signal_names = ["Liquidity", "Holders", "Resilience", "Fundamental",
                    "Contagion", "Structural", "Relative"]
    triggers = [f"{signal_names[i]}={ndd_result['signals'][i]:.1f}"
                for i in range(7) if ndd_result['signals'][i] < 2.0]

    symbol = t.get("symbol", "?").upper()
    rank = t.get("market_cap_rank") or "?"
    grade = t.get("trust_grade") or "?"

    emoji = {"EMERGENCY": "🚨", "DISTRESS": "⛔", "WARNING": "⚠️", "WATCH": "👁"}.get(alert_level, "")
    msg = f"{emoji} {alert_level}: {symbol} (#{rank}, {grade}) NDD={ndd:.2f}"

    if ndd_prev is not None and ndd_change < -0.3:
        msg += f" (deteriorated {ndd_change:+.2f})"
    if triggers:
        msg += f" [{', '.join(triggers[:3])}]"

    crypto_conn.execute("""
        INSERT INTO crypto_ndd_alerts
        (alert_date, token_id, symbol, alert_level, ndd, ndd_previous,
         ndd_change, market_cap_rank, trust_grade, trigger_signals, message, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        run_date, t["token_id"], symbol, alert_level, ndd,
        ndd_prev, round(ndd_change, 2),
        t.get("market_cap_rank"), grade,
        json.dumps(triggers), msg, datetime.now().isoformat(),
    ))
    return msg


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────
def run_ndd(top_n=None):
    """Run NDD computation for all tokens."""
    run_date = datetime.now().strftime("%Y-%m-%d")

    data_conn = connect_data_db()
    crypto_conn = connect_crypto_db()
    ensure_tables(crypto_conn)

    # Load tokens
    print(f"\n  Loading tokens from {DATA_DB_PATH}...")
    tokens = load_tokens(data_conn, top_n=top_n)
    print(f"  Loaded {len(tokens)} tokens with price+volume data")

    # Filter stablecoins
    tokens = [t for t in tokens if t["token_id"] not in STABLECOINS]
    print(f"  After stablecoin filter: {len(tokens)}")

    # Load BTC data
    btc_data = load_btc_data(data_conn)
    if btc_data:
        print(f"  BTC: ${btc_data['current_price_usd']:,.0f}, "
              f"7d: {btc_data['price_change_7d_pct'] or 0:+.1f}%, "
              f"30d: {btc_data['price_change_30d_pct'] or 0:+.1f}%")

    # Compute NDD for all tokens
    saved = 0
    alerts = []
    dist = defaultdict(int)

    for t in tokens:
        result = compute_ndd(t, btc_data)

        # Get previous NDD
        ndd_prev = get_previous_ndd(crypto_conn, t["token_id"], run_date)
        trend = result["ndd"] - ndd_prev if ndd_prev is not None else None

        # Save to DB
        crypto_conn.execute("""
            INSERT OR REPLACE INTO crypto_ndd_daily
            (run_date, token_id, symbol, name, market_cap_rank, trust_grade,
             ndd, signal_1, signal_2, signal_3, signal_4, signal_5, signal_6, signal_7,
             alert_level, ndd_7d_ago, ndd_trend_7d, override_triggered,
             price_usd, market_cap, volume_24h, breakdown, calculated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            run_date, t["token_id"], t["symbol"], t["name"],
            t.get("market_cap_rank"), t.get("trust_grade"),
            result["ndd"], *result["signals"],
            result["alert_level"], ndd_prev, trend,
            1 if result["override"] else 0,
            t.get("current_price_usd"), t.get("market_cap_usd"),
            t.get("total_volume_24h_usd"),
            json.dumps(result["breakdown"]),
            datetime.now().isoformat(),
        ))
        saved += 1
        dist[result["alert_level"]] += 1

        # Generate alert
        alert_msg = generate_alert(crypto_conn, t, result, ndd_prev, run_date)
        if alert_msg:
            alerts.append((result["ndd"], alert_msg))

    crypto_conn.commit()
    data_conn.close()

    # Sort alerts by NDD (worst first)
    alerts.sort(key=lambda x: x[0])

    # ── DISPLAY ─────────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  NDD RESULTS — {run_date}")
    print(f"{'='*100}")
    print(f"  Scored: {saved} tokens")

    print(f"\n  Distribution:")
    for level in ["SAFE", "WATCH", "WARNING", "DISTRESS", "EMERGENCY"]:
        count = dist.get(level, 0)
        pct = count / saved * 100 if saved > 0 else 0
        bar = "█" * min(80, count // 10)
        emoji = {"SAFE": "✅", "WATCH": "👁", "WARNING": "⚠️",
                 "DISTRESS": "⛔", "EMERGENCY": "🚨"}.get(level, "")
        print(f"    {emoji} {level:<12} {count:>6} ({pct:>5.1f}%) {bar}")

    # Show worst alerts
    if alerts:
        n_show = min(50, len(alerts))
        print(f"\n  TOP {n_show} ALERTS (of {len(alerts)} total):")
        for _, msg in alerts[:n_show]:
            print(f"    {msg}")

    # Summary for API
    print(f"\n  Summary:")
    print(f"    EMERGENCY: {dist.get('EMERGENCY', 0)} tokens")
    print(f"    DISTRESS:  {dist.get('DISTRESS', 0)} tokens")
    print(f"    WARNING:   {dist.get('WARNING', 0)} tokens")
    print(f"    WATCH:     {dist.get('WATCH', 0)} tokens")
    print(f"    SAFE:      {dist.get('SAFE', 0)} tokens")

    crypto_conn.close()
    return saved, len(alerts)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NERQ Daily NDD Engine v2")
    parser.add_argument("--top", type=int, default=None,
                        help="Only score top N tokens by market cap")
    parser.add_argument("--alerts", action="store_true",
                        help="Only show existing alerts")
    args = parser.parse_args()

    print("=" * 80)
    print("  NERQ CRYPTO — Daily NDD Engine v2.0")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print(f"  Data DB:   {DATA_DB_PATH}")
    print(f"  Output DB: {CRYPTO_DB_PATH}")

    if args.alerts:
        crypto_conn = connect_crypto_db()
        run_date = datetime.now().strftime("%Y-%m-%d")
        rows = crypto_conn.execute("""
            SELECT message FROM crypto_ndd_alerts
            WHERE alert_date = ? ORDER BY ndd ASC
        """, (run_date,)).fetchall()
        if rows:
            for r in rows:
                print(f"  {r['message']}")
        else:
            print(f"  No alerts for {run_date}")
        crypto_conn.close()
        return

    run_ndd(top_n=args.top)
    print(f"\n  Done.")


if __name__ == "__main__":
    main()
