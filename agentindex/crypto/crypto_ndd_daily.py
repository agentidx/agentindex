#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 2.2: Daily NDD (Nearness to Distress/Default) Engine
===========================================================================
Runs daily alongside crypto_rating_daily.py.
Computes NDD for all rated tokens, generates alerts for distressed tokens.

NDD Scale:
  5.0 = Very safe (blue chip)
  4.0 = Safe
  3.0 = Watch
  2.0 = Elevated risk — WATCH alert
  1.5 = High risk — WARNING alert
  1.0 = Critical — DISTRESS alert
  <1.0 = Imminent distress — EMERGENCY alert

Alert Levels:
  SAFE:      NDD >= 3.0
  WATCH:     2.0 <= NDD < 3.0
  WARNING:   1.5 <= NDD < 2.0
  DISTRESS:  1.0 <= NDD < 1.5
  EMERGENCY: NDD < 1.0

Usage:
  python3 crypto_ndd_daily.py              # Run for today
  python3 crypto_ndd_daily.py --cached     # Use existing DB data
  python3 crypto_ndd_daily.py --alerts     # Only show alerts

LaunchAgent: runs after crypto_rating_daily.py (06:15 UTC)

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
# NDD SIGNAL WEIGHTS (7 signals)
# ─────────────────────────────────────────────────────────────
# From existing crypto_ndd_calculator.py
SIGNAL_WEIGHTS = [0.15, 0.10, 0.20, 0.10, 0.15, 0.15, 0.15]
# s1: Liquidity, s2: Holder concentration, s3: Resilience,
# s4: Fundamental, s5: Contagion, s6: Structural, s7: Relative

ALERT_THRESHOLDS = {
    "SAFE": 3.0,
    "WATCH": 2.0,
    "WARNING": 1.5,
    "DISTRESS": 1.0,
    "EMERGENCY": 0.0,
}

STABLECOINS = {
    'tether', 'usd-coin', 'binance-usd', 'dai', 'true-usd', 'paxos-standard',
    'gusd', 'frax', 'usdd', 'tusd', 'busd', 'lusd', 'susd', 'eurs', 'usdp',
    'first-digital-usd', 'ethena-usde', 'usde', 'paypal-usd', 'fdusd',
    'stasis-eur', 'gemini-dollar', 'husd', 'nusd', 'musd', 'cusd',
    'terrausd', 'ust', 'magic-internet-money', 'euro-coin', 'ondo-us-dollar-yield',
}


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
    """Create daily NDD and alert tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_ndd_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            token_id TEXT NOT NULL,
            symbol TEXT,
            ndd REAL NOT NULL,
            signal_1 REAL, signal_2 REAL, signal_3 REAL,
            signal_4 REAL, signal_5 REAL, signal_6 REAL, signal_7 REAL,
            alert_level TEXT,
            ndd_7d_ago REAL,
            ndd_30d_ago REAL,
            ndd_trend_7d REAL,
            ndd_trend_30d REAL,
            override_triggered INTEGER DEFAULT 0,
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
            trigger_signals TEXT,
            message TEXT,
            acknowledged INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ndd_daily_date ON crypto_ndd_daily(run_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ndd_daily_token ON crypto_ndd_daily(token_id, run_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ndd_alerts_date ON crypto_ndd_alerts(alert_date)")
    conn.commit()


# ─────────────────────────────────────────────────────────────
# NDD SIGNAL CALCULATIONS
# ─────────────────────────────────────────────────────────────

def calc_signal_1_liquidity(prices, volumes):
    """
    Signal 1: Liquidity health
    Based on volume trends, turnover, and stability.
    """
    if not volumes or len(volumes) < 14:
        return 2.5, {"status": "insufficient_data"}

    recent = volumes[-7:]
    older = volumes[-14:-7]

    # Volume trend
    avg_recent = np.mean(recent) if recent else 0
    avg_older = np.mean(older) if older else 1
    trend = avg_recent / avg_older if avg_older > 0 else 1.0

    if trend > 1.2:
        trend_score = 4.5  # increasing volume
    elif trend > 0.8:
        trend_score = 4.0  # stable volume
    elif trend > 0.5:
        trend_score = 3.0  # declining
    elif trend > 0.2:
        trend_score = 2.0  # severe decline
    else:
        trend_score = 1.0  # volume collapse

    # Volume stability (low CV = stable)
    cv = np.std(recent) / np.mean(recent) if np.mean(recent) > 0 else 2.0
    if cv < 0.3:
        stability = 4.5
    elif cv < 0.5:
        stability = 3.5
    elif cv < 1.0:
        stability = 2.5
    else:
        stability = 1.5

    # Turnover (volume / price proxy)
    avg_vol = np.mean(volumes[-7:])
    if avg_vol >= 1e8:
        turnover = 4.5
    elif avg_vol >= 1e7:
        turnover = 3.5
    elif avg_vol >= 1e6:
        turnover = 2.5
    else:
        turnover = 1.5

    signal = (trend_score + stability + turnover) / 3
    return round(signal, 2), {"trend": round(trend, 2), "stability": round(cv, 2), "turnover": round(avg_vol, 0)}


def calc_signal_2_holders(token_data):
    """
    Signal 2: Holder concentration proxy.
    Without on-chain data, we use market cap rank and volume/mcap ratio.
    """
    rank = token_data.get("market_cap_rank") or 999
    mcap = token_data.get("market_cap", 0) or 0
    vol = token_data.get("total_volume", 0) or 0

    # Higher rank = likely more distributed holders
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
    else:
        rank_score = 2.0

    # Vol/mcap as proxy for active holders
    ratio = vol / mcap if mcap > 0 else 0
    if 0.02 <= ratio <= 0.15:
        holder_activity = 4.0  # healthy activity
    elif ratio < 0.02:
        holder_activity = 2.5  # low activity = concentrated
    elif ratio <= 0.30:
        holder_activity = 3.5
    else:
        holder_activity = 2.0  # suspicious activity

    signal = (rank_score + holder_activity) / 2
    return round(signal, 2), {"rank": rank, "vol_mcap_ratio": round(ratio, 4)}


def calc_signal_3_resilience(prices):
    """
    Signal 3: Price resilience (most important signal, weight 0.20).
    Based on drawdown, momentum, acceleration.
    """
    if not prices or len(prices) < 30:
        return 2.5, {"status": "insufficient_data"}

    # Max drawdown (last 90 days)
    peak = prices[0]
    max_dd = 0
    for p in prices:
        if p > peak:
            peak = p
        dd = (p - peak) / peak if peak > 0 else 0
        if dd < max_dd:
            max_dd = dd

    if max_dd > -0.05:
        dd_score = 5.0
    elif max_dd > -0.10:
        dd_score = 4.5
    elif max_dd > -0.20:
        dd_score = 4.0
    elif max_dd > -0.30:
        dd_score = 3.0
    elif max_dd > -0.50:
        dd_score = 2.0
    elif max_dd > -0.70:
        dd_score = 1.0
    else:
        dd_score = 0.5

    # Momentum (7-day price change)
    if len(prices) >= 7:
        mom_7d = (prices[-1] - prices[-7]) / prices[-7] if prices[-7] > 0 else 0
        if mom_7d > 0.10:
            mom_score = 4.5
        elif mom_7d > 0:
            mom_score = 4.0
        elif mom_7d > -0.05:
            mom_score = 3.5
        elif mom_7d > -0.15:
            mom_score = 2.5
        elif mom_7d > -0.30:
            mom_score = 1.5
        else:
            mom_score = 0.5
    else:
        mom_score = 2.5

    # Acceleration (is decline speeding up?)
    if len(prices) >= 14:
        mom_recent = (prices[-1] - prices[-7]) / prices[-7] if prices[-7] > 0 else 0
        mom_older = (prices[-7] - prices[-14]) / prices[-14] if prices[-14] > 0 else 0
        accel = mom_recent - mom_older
        if accel > 0.05:
            accel_score = 4.5  # improving
        elif accel > -0.02:
            accel_score = 3.5  # stable
        elif accel > -0.10:
            accel_score = 2.0  # deteriorating
        else:
            accel_score = 1.0  # accelerating decline
    else:
        accel_score = 2.5

    # Volatility
    daily_rets = np.diff(prices) / prices[:-1]
    vol = np.std(daily_rets) * np.sqrt(365) if len(daily_rets) > 5 else 1.0
    if vol < 0.30:
        vol_score = 4.5
    elif vol < 0.60:
        vol_score = 3.5
    elif vol < 1.00:
        vol_score = 2.5
    elif vol < 1.50:
        vol_score = 1.5
    else:
        vol_score = 0.5

    signal = (dd_score * 0.35 + mom_score * 0.25 + accel_score * 0.20 + vol_score * 0.20)
    return round(signal, 2), {
        "dd": round(max_dd, 4), "dd_score": round(dd_score, 1),
        "mom_7d": round(mom_7d if len(prices) >= 7 else 0, 4),
        "mom_score": round(mom_score, 1),
        "accel_score": round(accel_score, 1),
        "vol": round(vol, 4), "vol_score": round(vol_score, 1),
    }


def calc_signal_4_fundamental(token_data):
    """Signal 4: Fundamental health."""
    change_24h = token_data.get("price_change_percentage_24h") or 0
    change_7d = token_data.get("price_change_percentage_7d_in_currency") or 0
    change_30d = token_data.get("price_change_percentage_30d_in_currency") or 0

    # Trend health
    if change_30d > 10:
        trend = 4.0
    elif change_30d > 0:
        trend = 3.5
    elif change_30d > -15:
        trend = 3.0
    elif change_30d > -30:
        trend = 2.0
    else:
        trend = 1.0

    # Panic selling indicator
    if change_24h < -15:
        panic = 1.0  # severe single-day drop
    elif change_24h < -8:
        panic = 2.0
    elif change_24h < -3:
        panic = 3.0
    else:
        panic = 4.0

    signal = (trend * 0.6 + panic * 0.4)
    return round(signal, 2), {"trend_30d": round(change_30d, 1), "panic_24h": round(change_24h, 1)}


def calc_signal_5_contagion(prices, btc_prices):
    """Signal 5: Contagion risk (correlation with BTC)."""
    if not prices or not btc_prices or len(prices) < 30 or len(btc_prices) < 30:
        return 2.5, {"status": "insufficient_data"}

    min_len = min(len(prices), len(btc_prices))
    tok_rets = np.diff(prices[-min_len:]) / prices[-min_len:-1]
    btc_rets = np.diff(btc_prices[-min_len:]) / btc_prices[-min_len:-1]

    if len(tok_rets) != len(btc_rets) or len(tok_rets) < 10:
        return 2.5, {"status": "alignment_error"}

    corr = np.corrcoef(tok_rets, btc_rets)[0, 1]

    # High correlation = more exposed to BTC-driven contagion
    # Very high correlation is actually a risk factor
    if corr > 0.9:
        signal = 1.5  # extreme contagion exposure
    elif corr > 0.7:
        signal = 2.5
    elif corr > 0.5:
        signal = 3.5
    elif corr > 0.3:
        signal = 4.0
    else:
        signal = 3.0  # low corr could be good or manipulation

    # Beta amplification
    cov = np.cov(tok_rets, btc_rets)[0, 1]
    var_btc = np.var(btc_rets)
    beta = cov / var_btc if var_btc > 0 else 1.0

    if beta > 2.0:
        signal = min(signal, 1.5)
    elif beta > 1.5:
        signal = min(signal, 2.5)

    return round(signal, 2), {"corr": round(corr, 3), "beta": round(beta, 3)}


def calc_signal_6_structural(token_data, prices):
    """Signal 6: Structural integrity (flash crash risk, spread, age)."""
    rank = token_data.get("market_cap_rank") or 999

    # Age proxy (rank = likely more established)
    if rank <= 20:
        age_score = 4.5
    elif rank <= 50:
        age_score = 4.0
    elif rank <= 100:
        age_score = 3.5
    elif rank <= 200:
        age_score = 3.0
    else:
        age_score = 2.0

    # Flash crash risk (extreme single-day moves in recent history)
    if prices and len(prices) >= 14:
        daily_rets = np.diff(prices[-14:]) / prices[-14:-1]
        min_ret = min(daily_rets) if len(daily_rets) > 0 else 0
        if min_ret > -0.05:
            flash_score = 5.0
        elif min_ret > -0.10:
            flash_score = 4.0
        elif min_ret > -0.20:
            flash_score = 3.0
        elif min_ret > -0.30:
            flash_score = 2.0
        else:
            flash_score = 1.0
    else:
        flash_score = 3.0

    signal = (age_score * 0.4 + flash_score * 0.6)
    return round(signal, 2), {"age_score": age_score, "flash_score": flash_score}


def calc_signal_7_relative(prices, btc_prices):
    """Signal 7: Relative performance vs BTC."""
    if not prices or not btc_prices:
        return 3.0, {"status": "insufficient_data"}

    scores = []

    for window, label in [(7, "7d"), (14, "14d"), (30, "30d")]:
        if len(prices) >= window and len(btc_prices) >= window:
            tok_ret = (prices[-1] - prices[-window]) / prices[-window] if prices[-window] > 0 else 0
            btc_ret = (btc_prices[-1] - btc_prices[-window]) / btc_prices[-window] if btc_prices[-window] > 0 else 0
            relative = tok_ret - btc_ret

            if relative > 0.10:
                s = 4.5  # outperforming
            elif relative > 0:
                s = 4.0
            elif relative > -0.05:
                s = 3.5
            elif relative > -0.15:
                s = 2.5
            elif relative > -0.30:
                s = 1.5
            else:
                s = 0.5
            scores.append(s)

    signal = np.mean(scores) if scores else 3.0
    return round(signal, 2), {"n_windows": len(scores)}


# ─────────────────────────────────────────────────────────────
# COMPOSITE NDD
# ─────────────────────────────────────────────────────────────
def compute_ndd(token_data, prices, volumes, btc_prices):
    """Compute NDD from 7 signals."""
    s1, s1d = calc_signal_1_liquidity(prices, volumes)
    s2, s2d = calc_signal_2_holders(token_data)
    s3, s3d = calc_signal_3_resilience(prices)
    s4, s4d = calc_signal_4_fundamental(token_data)
    s5, s5d = calc_signal_5_contagion(prices, btc_prices)
    s6, s6d = calc_signal_6_structural(token_data, prices)
    s7, s7d = calc_signal_7_relative(prices, btc_prices)

    signals = [s1, s2, s3, s4, s5, s6, s7]
    ndd = sum(s * w for s, w in zip(signals, SIGNAL_WEIGHTS))

    # Override: if ANY signal is critically low, cap NDD
    min_signal = min(signals)
    n_below_1_5 = sum(1 for s in signals if s < 1.5)
    n_below_2_0 = sum(1 for s in signals if s < 2.0)

    override = False
    if min_signal < 1.0:
        ndd = min(ndd, 1.5)
        override = True
    elif n_below_1_5 >= 2:
        ndd = min(ndd, 2.0)
        override = True
    elif n_below_2_0 >= 3:
        ndd = min(ndd, 2.5)
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
        "min_signal": round(min_signal, 2),
        "breakdown": {
            "s1_liquidity": s1d,
            "s2_holders": s2d,
            "s3_resilience": s3d,
            "s4_fundamental": s4d,
            "s5_contagion": s5d,
            "s6_structural": s6d,
            "s7_relative": s7d,
        },
    }


# ─────────────────────────────────────────────────────────────
# NDD TRENDS
# ─────────────────────────────────────────────────────────────
def get_ndd_history(conn, token_id, run_date, days_back):
    """Get NDD from N days ago."""
    target = (datetime.strptime(run_date, "%Y-%m-%d") - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Check daily table first
    row = conn.execute(
        "SELECT ndd FROM crypto_ndd_daily WHERE token_id=? AND run_date<=? ORDER BY run_date DESC LIMIT 1",
        (token_id, target)
    ).fetchone()

    if row:
        return row["ndd"]

    # Fallback to weekly history table
    row = conn.execute(
        "SELECT ndd FROM crypto_ndd_history WHERE token_id=? AND week_date<=? ORDER BY week_date DESC LIMIT 1",
        (token_id, target)
    ).fetchone()

    return row["ndd"] if row else None


# ─────────────────────────────────────────────────────────────
# ALERT GENERATION
# ─────────────────────────────────────────────────────────────
def generate_alert(conn, token_id, symbol, ndd_result, ndd_previous, run_date):
    """Generate alert if NDD crosses threshold or changes significantly."""
    alert_level = ndd_result["alert_level"]
    ndd = ndd_result["ndd"]

    # Only alert for WATCH or worse
    if alert_level == "SAFE":
        return None

    # Check if this is a new alert or deterioration
    ndd_change = ndd - ndd_previous if ndd_previous is not None else 0
    is_deterioration = ndd_previous is not None and ndd < ndd_previous - 0.3

    # Identify trigger signals (below 2.0)
    signal_names = ["Liquidity", "Holders", "Resilience", "Fundamental",
                    "Contagion", "Structural", "Relative"]
    triggers = [
        f"{signal_names[i]}={ndd_result['signals'][i]:.1f}"
        for i in range(7) if ndd_result['signals'][i] < 2.0
    ]

    # Build message
    if alert_level == "EMERGENCY":
        msg = f"🚨 EMERGENCY: {symbol} NDD={ndd:.2f} — imminent distress risk"
    elif alert_level == "DISTRESS":
        msg = f"⚠️ DISTRESS: {symbol} NDD={ndd:.2f} — high distress probability"
    elif alert_level == "WARNING":
        msg = f"⚠️ WARNING: {symbol} NDD={ndd:.2f} — elevated risk"
    else:
        msg = f"👁 WATCH: {symbol} NDD={ndd:.2f} — monitor closely"

    if is_deterioration:
        msg += f" (deteriorated {ndd_change:+.2f})"
    if triggers:
        msg += f" [triggers: {', '.join(triggers)}]"

    # Save alert
    from agentindex.crypto.dual_write import dual_execute
    dual_execute(conn, """
        INSERT INTO crypto_ndd_alerts
        (alert_date, token_id, symbol, alert_level, ndd, ndd_previous,
         ndd_change, trigger_signals, message, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        run_date, token_id, symbol, alert_level, ndd,
        ndd_previous, round(ndd_change, 2),
        json.dumps(triggers), msg, datetime.now().isoformat(),
    ))

    return msg


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────
def run_daily_ndd(conn, run_date=None, use_cached=False):
    """Run daily NDD computation."""
    if run_date is None:
        run_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n  Run date: {run_date}")

    if use_cached:
        return run_ndd_from_db(conn, run_date)
    else:
        return run_ndd_from_db(conn, run_date)  # NDD always uses DB price data


def run_ndd_from_db(conn, run_date):
    """Compute NDD using existing DB price data."""

    # Get all tokens with recent price data
    tokens_raw = conn.execute("""
        SELECT DISTINCT ph.token_id,
               (SELECT close FROM crypto_price_history
                WHERE token_id = ph.token_id ORDER BY date DESC LIMIT 1) as last_price
        FROM crypto_price_history ph
        WHERE ph.date >= date(?, '-7 days')
        GROUP BY ph.token_id
    """, (run_date,)).fetchall()

    token_ids = [r["token_id"] for r in tokens_raw if r["token_id"] not in STABLECOINS]
    print(f"  Tokens with recent data: {len(token_ids)}")

    # Load BTC prices
    btc_rows = conn.execute("""
        SELECT close FROM crypto_price_history
        WHERE token_id = 'bitcoin' AND date >= date(?, '-90 days') AND date <= ?
        ORDER BY date
    """, (run_date, run_date)).fetchall()
    btc_prices = [r["close"] for r in btc_rows if r["close"] and r["close"] > 0]

    # Check for ratings (to get market cap rank etc)
    ratings = {}
    for r in conn.execute("""
        SELECT token_id, market_cap_rank, price_usd, market_cap, volume_24h,
               price_change_24h, price_change_7d, price_change_30d
        FROM crypto_rating_daily WHERE run_date = ?
    """, (run_date,)).fetchall():
        ratings[r["token_id"]] = dict(r)

    saved = 0
    alerts = []

    for tid in token_ids:
        # Get price history
        price_rows = conn.execute("""
            SELECT close, volume FROM crypto_price_history
            WHERE token_id = ? AND date >= date(?, '-90 days') AND date <= ?
            ORDER BY date
        """, (tid, run_date, run_date)).fetchall()

        prices = [r["close"] for r in price_rows if r["close"] and r["close"] > 0]
        volumes = [r["volume"] for r in price_rows if r["volume"]]

        if len(prices) < 14:
            continue

        # Build token_data dict (from rating or minimal)
        token_data = ratings.get(tid, {})
        if not token_data:
            token_data = {
                "market_cap_rank": 999,
                "market_cap": 0,
                "total_volume": volumes[-1] if volumes else 0,
                "price_change_percentage_24h": 0,
                "price_change_percentage_7d_in_currency": 0,
                "price_change_percentage_30d_in_currency": 0,
            }

        # Compute NDD
        result = compute_ndd(token_data, prices, volumes, btc_prices)

        # Get historical NDD for trends
        ndd_7d = get_ndd_history(conn, tid, run_date, 7)
        ndd_30d = get_ndd_history(conn, tid, run_date, 30)
        trend_7d = result["ndd"] - ndd_7d if ndd_7d is not None else None
        trend_30d = result["ndd"] - ndd_30d if ndd_30d is not None else None

        # Get symbol
        sym_row = conn.execute(
            "SELECT symbol FROM crypto_fetch_status WHERE token_id = ?", (tid,)
        ).fetchone()
        symbol = sym_row["symbol"] if sym_row else tid[:6].upper()

        # Save to DB
        from agentindex.crypto.dual_write import dual_execute
        dual_execute(conn, """
            INSERT OR REPLACE INTO crypto_ndd_daily
            (run_date, token_id, symbol, ndd,
             signal_1, signal_2, signal_3, signal_4, signal_5, signal_6, signal_7,
             alert_level, ndd_7d_ago, ndd_30d_ago, ndd_trend_7d, ndd_trend_30d,
             override_triggered, breakdown, calculated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            run_date, tid, symbol, result["ndd"],
            *result["signals"],
            result["alert_level"], ndd_7d, ndd_30d, trend_7d, trend_30d,
            1 if result["override"] else 0,
            json.dumps(result["breakdown"]),
            datetime.now().isoformat(),
        ))
        saved += 1

        # Generate alerts
        ndd_prev = ndd_7d  # compare to week ago
        alert_msg = generate_alert(conn, tid, symbol, result, ndd_prev, run_date)
        if alert_msg:
            alerts.append(alert_msg)

    conn.commit()
    print(f"  Saved {saved} NDD scores")
    print(f"  Generated {len(alerts)} alerts")

    return saved, alerts


# ─────────────────────────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────────────────────────
def print_summary(conn, run_date):
    """Print NDD summary and alerts."""
    rows = conn.execute("""
        SELECT token_id, symbol, ndd, signal_1, signal_2, signal_3,
               signal_4, signal_5, signal_6, signal_7,
               alert_level, ndd_trend_7d, override_triggered
        FROM crypto_ndd_daily
        WHERE run_date = ?
        ORDER BY ndd ASC
    """, (run_date,)).fetchall()

    if not rows:
        print(f"\n  No NDD data for {run_date}")
        return

    print(f"\n{'='*110}")
    print(f"  DAILY NDD SCORES — {run_date}")
    print(f"{'='*110}")

    # Distress watch (NDD < 3.0)
    watch_list = [r for r in rows if r["ndd"] < 3.0]
    if watch_list:
        print(f"\n  ⚠️  DISTRESS WATCH ({len(watch_list)} tokens below 3.0)")
        print(f"  {'Token':<12} {'NDD':>5} {'Alert':>10} {'S1':>4} {'S2':>4} {'S3':>4} "
              f"{'S4':>4} {'S5':>4} {'S6':>4} {'S7':>4} {'7d Δ':>6} {'OVR':>4}")
        print(f"  {'-'*85}")
        for r in watch_list:
            trend = f"{r['ndd_trend_7d']:+.2f}" if r['ndd_trend_7d'] is not None else "—"
            ovr = "YES" if r['override_triggered'] else ""
            alert_mark = {"EMERGENCY": "🚨", "DISTRESS": "⛔", "WARNING": "⚠️", "WATCH": "👁"}.get(r['alert_level'], "")
            print(f"  {r['symbol'] or r['token_id'][:10]:<12} {r['ndd']:>5.2f} "
                  f"{alert_mark} {r['alert_level']:<8} "
                  f"{r['signal_1']:>4.1f} {r['signal_2']:>4.1f} {r['signal_3']:>4.1f} "
                  f"{r['signal_4']:>4.1f} {r['signal_5']:>4.1f} {r['signal_6']:>4.1f} "
                  f"{r['signal_7']:>4.1f} {trend:>6} {ovr:>4}")

    # Distribution
    dist = defaultdict(int)
    for r in rows:
        dist[r["alert_level"]] += 1

    print(f"\n  NDD Distribution:")
    for level in ["SAFE", "WATCH", "WARNING", "DISTRESS", "EMERGENCY"]:
        count = dist.get(level, 0)
        bar = "█" * count
        emoji = {"SAFE": "✅", "WATCH": "👁", "WARNING": "⚠️", "DISTRESS": "⛔", "EMERGENCY": "🚨"}.get(level, "")
        print(f"    {emoji} {level:<12} {count:>3} {bar}")

    # Today's alerts
    alert_rows = conn.execute("""
        SELECT message FROM crypto_ndd_alerts
        WHERE alert_date = ? ORDER BY ndd ASC
    """, (run_date,)).fetchall()

    if alert_rows:
        print(f"\n  TODAY'S ALERTS ({len(alert_rows)}):")
        for r in alert_rows:
            print(f"    {r['message']}")

    print(f"\n  Total scored: {len(rows)}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NERQ Daily NDD Engine")
    parser.add_argument("--cached", action="store_true", help="Use cached DB data")
    parser.add_argument("--date", type=str, default=None, help="Run for specific date")
    parser.add_argument("--alerts", action="store_true", help="Only show alerts")
    args = parser.parse_args()

    print("=" * 80)
    print("  NERQ CRYPTO — Daily NDD Engine v1.0")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print(f"  Database: {DB_PATH}")

    conn = connect()
    ensure_tables(conn)

    run_date = args.date or datetime.now().strftime("%Y-%m-%d")

    if not args.alerts:
        run_daily_ndd(conn, run_date=run_date, use_cached=args.cached)

    print_summary(conn, run_date)
    conn.close()
    print(f"\n  Done.")


if __name__ == "__main__":
    main()


# ─────────────────────────────────────────────────────────────
# LAUNCHAGENT TEMPLATE
# ─────────────────────────────────────────────────────────────
# Save as: ~/Library/LaunchAgents/com.nerq.crypto-ndd-daily.plist
# Same as rating daily but runs at 07:15 (15 min after rating)
# <key>StartCalendarInterval</key>
# <dict>
#     <key>Hour</key><integer>7</integer>
#     <key>Minute</key><integer>15</integer>
# </dict>
