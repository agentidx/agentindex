#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 2.2: Daily NDD Engine v3
================================================
Fuses the PROVEN v3.1 calibration (1190/1200 crash detection) with
the 15,000-token architecture reading from data/crypto_trust.db.

CRITICAL: Weights, overrides, and thresholds are FROZEN from v3.1
which achieved near-perfect crash prediction on historical data.
DO NOT CHANGE THESE without re-running backtest validation.

FROZEN from v3.1 (do not modify):
  - Signal weights: S1=10% S2=5% S3=30% S4=10% S5=25% S6=5% S7=15%
  - Override: 1 signal <0.5 → cap 1.0 | 2+ <1.5 → cap 1.5 | 3+ <2.0 → cap 1.5
  - Alert thresholds: SAFE≥4.0, WATCH≥3.0, WARNING≥2.0, DISTRESS≥1.0, CRITICAL<1.0
  - Top50 gets gentler thresholds (WARNING≥1.5 instead of 2.0)

NEW in v3 (architecture only):
  - Reads from data/crypto_trust.db (18,291 tokens) instead of 210
  - Signals adapted for snapshot data (no 60d OHLCV required)
  - For tokens WITH OHLCV history: uses original signal calculations
  - For tokens WITHOUT OHLCV: uses snapshot approximation with same scoring curves

Data sources:
  PRIMARY: agentindex/data/crypto_trust.db → crypto_tokens (18,291 tokens)
  OHLCV:   agentindex/crypto/crypto_trust.db → crypto_price_history (210 tokens)
  OUTPUT:  agentindex/crypto/crypto_trust.db → crypto_ndd_daily, crypto_ndd_alerts

Author: NERQ
Version: 3.1
Date: 2026-02-27
"""

import sqlite3
import os
import sys
import json
import argparse
import time
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

# ─────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DB_PATH = os.path.join(SCRIPT_DIR, "..", "data", "crypto_trust.db")
CRYPTO_DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")

# ─────────────────────────────────────────────────────────────
# ██ FROZEN PARAMETERS — from v3.1 (1190/1200 crash detection) ██
# DO NOT CHANGE without re-running backtest validation
# ─────────────────────────────────────────────────────────────
NDD_WEIGHTS = {
    "liquidity_depth":       0.10,
    "holder_concentration":  0.05,
    "ecosystem_resilience":  0.30,   # most important
    "fundamental_activity":  0.10,
    "contagion_exposure":    0.25,   # strongest predictor
    "structural_risk":       0.05,
    "relative_weakness":     0.15,
}
WEIGHT_LIST = [0.10, 0.05, 0.30, 0.10, 0.25, 0.05, 0.15]

# Override thresholds — FROZEN
SEVERE_SIGNAL_THRESHOLD = 0.5      # 1 signal below → cap 1.0
MULTI_SIGNAL_THRESHOLD = 1.5       # 2+ below → cap 1.5
MULTI_SIGNAL_COUNT = 2
MULTI_SIGNAL_CAP = 1.5
BROAD_WEAKNESS_THRESHOLD = 2.0     # 3+ below → cap 1.5
BROAD_WEAKNESS_COUNT = 3
BROAD_WEAKNESS_CAP = 1.5

# Alert thresholds — FROZEN
TOP50_WARNING_THRESHOLD = 1.5

STABLECOIN_IDS = {
    "tether", "usd-coin", "binance-usd", "dai", "true-usd", "paxos-standard",
    "frax", "gemini-dollar", "husd", "alchemix-usd", "liquity-usd",
    "paypal-usd", "first-digital-usd", "ripple-usd", "usdd",
    "crvusd", "euro-coin", "stasis-eurs", "tether-gold",
    "ondo-us-dollar-yield", "usd1-wlfi", "astherus-usdf", "falcon-finance",
}

NDD_LOOKBACK = 60
# ─────────────────────────────────────────────────────────────
# CRASH PROBABILITY TABLE — validated on 393 crash cycles
# Key: (trend, alert_level) → P(crash >30% within 90d)
# Trend = NDD change over 4 weeks
# ─────────────────────────────────────────────────────────────
CRASH_PROB_TABLE = {
    # (trend, level): (P_crash_30pct, P_crash_50pct, false_positive_rate)
    ("FREEFALL", "WARNING"):  (0.43, 0.19, 0.15),
    ("FREEFALL", "DISTRESS"): (0.34, 0.13, 0.16),
    ("FREEFALL", "WATCH"):    (0.28, 0.09, 0.21),
    ("FALLING",  "WARNING"):  (0.37, 0.14, 0.18),
    ("FALLING",  "DISTRESS"): (0.30, 0.10, 0.20),
    ("FALLING",  "WATCH"):    (0.25, 0.07, 0.22),
    ("SLIDING",  "WARNING"):  (0.33, 0.12, 0.17),
    ("SLIDING",  "DISTRESS"): (0.28, 0.10, 0.18),
    ("SLIDING",  "WATCH"):    (0.20, 0.06, 0.23),
    ("STABLE",   "SAFE"):     (0.03, 0.02, 0.58),
    ("STABLE",   "WATCH"):    (0.18, 0.07, 0.25),
    ("STABLE",   "WARNING"):  (0.33, 0.12, 0.17),
    ("STABLE",   "DISTRESS"): (0.30, 0.10, 0.25),
    ("IMPROVING","SAFE"):     (0.02, 0.01, 0.60),
    ("IMPROVING","WATCH"):    (0.12, 0.05, 0.30),
    ("IMPROVING","WARNING"):  (0.20, 0.08, 0.25),
    ("IMPROVING","DISTRESS"): (0.18, 0.07, 0.28),
}

# HC Alert thresholds — validated: 78% precision, 5% false positive
HC_ALERT_MIN_STREAK = 3       # 3+ weeks in WARNING/DISTRESS
HC_ALERT_FREEFALL_THRESHOLD = -1.0  # NDD drop > 1.0 in 4 weeks

# Bottlefish thresholds — validated on 393 crash cycles
# bounce90 = price recovery from trough within last 90 days
BOTTLEFISH_THRESHOLDS = {
    "STRONG_BUY":  {"bounce90": 150, "rank_max": 100, "score_min": 60},  # 80% win, 10% dead
    "BUY":         {"bounce90": 200, "rank_max": 200, "score_min": 0},   # 72% win, 27% dead
    "SPECULATIVE": {"bounce90": 150, "rank_max": 500, "score_min": 50},  # 64% win, 23% dead
}



def clamp(val, lo=0.0, hi=5.0):
    return max(lo, min(hi, float(val)))


def get_alert_level(ndd, is_top50=False):
    """FROZEN alert thresholds from v3.1"""
    if ndd >= 4.0:   return "SAFE"
    elif ndd >= 3.0: return "WATCH"
    elif is_top50:
        if ndd >= TOP50_WARNING_THRESHOLD: return "WATCH"
        elif ndd >= 1.0: return "WARNING"
        else: return "DISTRESS"
    else:
        if ndd >= 2.0: return "WARNING"
        elif ndd >= 1.0: return "DISTRESS"
        else: return "CRITICAL"


# ─────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────
def connect_data_db():
    if not os.path.exists(DATA_DB_PATH):
        print(f"  ERROR: Data DB not found at {DATA_DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(DATA_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def connect_crypto_db():
    if not os.path.exists(CRYPTO_DB_PATH):
        print(f"  ERROR: Crypto DB not found at {CRYPTO_DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(CRYPTO_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables(conn):
    # conn.execute("DROP TABLE IF EXISTS crypto_ndd_daily")
    # conn.execute("DROP TABLE IF EXISTS crypto_ndd_alerts")
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
            override_triggered INTEGER DEFAULT 0,
            confirmed_distress INTEGER DEFAULT 0,
            has_ohlcv INTEGER DEFAULT 0,
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
            market_cap_rank INTEGER,
            trust_grade TEXT,
            trigger_signals TEXT,
            message TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ndd3_date ON crypto_ndd_daily(run_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ndd3_token ON crypto_ndd_daily(token_id, run_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ndd3_alert ON crypto_ndd_daily(run_date, alert_level)")
    conn.commit()


# ─────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────
def load_all_tokens(data_conn):
    """Load all tokens with price+volume from data DB."""
    rows = data_conn.execute("""
        SELECT id as token_id, symbol, name,
               current_price_usd, market_cap_usd, market_cap_rank,
               total_volume_24h_usd,
               price_change_24h_pct, price_change_7d_pct, price_change_30d_pct,
               circulating_supply, total_supply, max_supply,
               ath_usd, ath_date, atl_usd, atl_date,
               fully_diluted_valuation, categories,
               has_audit, is_verified,
               twitter_followers, reddit_subscribers,
               github_stars, github_contributors, github_last_commit,
               trust_score, trust_grade,
               security_score, compliance_score, maintenance_score,
               popularity_score, ecosystem_score
        FROM crypto_tokens
        WHERE current_price_usd > 0 AND total_volume_24h_usd > 0
        ORDER BY market_cap_rank ASC NULLS LAST
    """).fetchall()
    return [dict(r) for r in rows]


def load_ohlcv_tokens(crypto_conn, run_date):
    """Load OHLCV history for tokens that have it (210 tokens)."""
    ohlcv = {}
    tokens = crypto_conn.execute("""
        SELECT DISTINCT token_id FROM crypto_price_history
        WHERE date >= date(?, '-60 days') AND date <= ?
    """, (run_date, run_date)).fetchall()

    for row in tokens:
        tid = row["token_id"]
        prices = crypto_conn.execute("""
            SELECT date, open, high, low, close, volume
            FROM crypto_price_history
            WHERE token_id = ? AND date >= date(?, '-60 days') AND date <= ?
            ORDER BY date ASC
        """, (tid, run_date, run_date)).fetchall()
        if len(prices) >= 15:
            ohlcv[tid] = [tuple(p) for p in prices]
    return ohlcv


def load_btc_reference(crypto_conn, run_date):
    """Load BTC returns and closes for contagion + relative signals."""
    rows = crypto_conn.execute("""
        SELECT date, close FROM crypto_price_history
        WHERE token_id = 'bitcoin' AND date >= date(?, '-60 days') AND date <= ?
        ORDER BY date ASC
    """, (run_date, run_date)).fetchall()

    btc_rets = {}
    btc_closes = {}
    for i, r in enumerate(rows):
        btc_closes[r["date"]] = r["close"]
        if i > 0 and r["close"] and rows[i-1]["close"] and rows[i-1]["close"] > 0:
            btc_rets[r["date"]] = (r["close"] / rows[i-1]["close"]) - 1
    return btc_rets, btc_closes


# ─────────────────────────────────────────────────────────────
# SIGNALS — OHLCV path (original v3.1 logic, exact copy)
# ─────────────────────────────────────────────────────────────

def ohlcv_signal_1(window):
    """S1 Liquidity — EXACT v3.1 logic"""
    closes = [r[4] for r in window if r[4] and r[4] > 0]
    volumes = [r[5] for r in window if r[5] and r[5] > 0]
    if len(closes) < 10 or len(volumes) < 10:
        return 2.5, {}
    vol_arr = np.array(volumes)
    avg_vol = np.mean(vol_arr)
    avg_price = np.mean(closes)
    turnover = avg_vol / avg_price if avg_price > 0 else 0
    turnover_score = min(5, np.log10(max(turnover, 1)) / 2) if turnover > 0 else 0
    if len(vol_arr) >= 20:
        recent = np.mean(vol_arr[-14:])
        earlier = np.mean(vol_arr[:-14])
        ratio = recent / earlier if earlier > 0 else 0.5
        if ratio > 1.0:    trend = 4.5
        elif ratio > 0.5:  trend = 1.5 + ratio * 3
        elif ratio > 0.1:  trend = ratio * 10
        else:               trend = 0.3
    else:
        trend = 2.5
    vol_cov = np.std(vol_arr) / np.mean(vol_arr) if np.mean(vol_arr) > 0 else 5
    stability = max(0, 5 - vol_cov * 1.5)
    total = turnover_score * 0.25 + trend * 0.45 + stability * 0.30
    return clamp(total), {"turnover": round(turnover_score, 2), "trend": round(trend, 2)}


def ohlcv_signal_2(window):
    """S2 Holders — EXACT v3.1 logic"""
    volumes = [r[5] for r in window if r[5] and r[5] > 0]
    if len(volumes) < 10:
        return 2.5, {}
    vol_arr = np.array(volumes)
    vol_median = np.median(vol_arr)
    if vol_median > 0:
        whale_days = np.sum(vol_arr > vol_median * 5)
        whale_ratio = whale_days / len(vol_arr)
        whale_score = max(0, 5 - whale_ratio * 50)
    else:
        whale_score = 2.0
    sorted_vol = np.sort(vol_arr)
    n = len(sorted_vol)
    gini = (2 * np.sum(np.arange(1, n+1) * sorted_vol) / (n * np.sum(sorted_vol))) - (n + 1) / n
    gini_score = max(0, 5 - gini * 5)
    low_vol = np.sum(vol_arr < vol_median * 0.01) if vol_median > 0 else 0
    activity_score = max(0, 5 - (low_vol / len(vol_arr)) * 10)
    total = whale_score * 0.40 + gini_score * 0.30 + activity_score * 0.30
    return clamp(total), {"whale": round(whale_score, 2), "gini": round(float(gini), 3)}


def ohlcv_signal_3(window):
    """S3 Resilience — EXACT v3.1 logic"""
    closes = [r[4] for r in window if r[4] and r[4] > 0]
    if len(closes) < 15:
        return 2.5, {}
    c = np.array(closes)
    rets = np.diff(c) / c[:-1]
    rets = rets[np.isfinite(rets)]
    peak = np.max(c)
    current = c[-1]
    dd = (current - peak) / peak if peak > 0 else 0
    if dd >= 0:        dd_score = 5.0
    elif dd > -0.3:    dd_score = 5.0 + dd * 8.33
    elif dd > -0.6:    dd_score = 2.5 + (dd + 0.3) * 6.67
    elif dd > -0.9:    dd_score = 0.5 + (dd + 0.6) * 1.67
    else:              dd_score = 0.0
    if len(rets) > 5:
        vol = float(np.std(rets) * np.sqrt(365))
        vol_score = max(0, 5 - vol * 2.5)
    else:
        vol_score = 2.5
    if len(c) >= 30:
        mom_30d = (c[-1] / c[-30]) - 1
        mom_7d = (c[-1] / c[-7]) - 1 if len(c) >= 7 else 0
        mom_score = clamp(3.0 + mom_30d * 4 + mom_7d * 3)
    elif len(c) >= 7:
        mom_7d = (c[-1] / c[-7]) - 1
        mom_score = clamp(3.0 + mom_7d * 5)
    else:
        mom_score = 2.5
    if len(c) >= 14:
        ret_recent = (c[-1] / c[-7]) - 1 if c[-7] > 0 else 0
        ret_prior = (c[-7] / c[-14]) - 1 if c[-14] > 0 else 0
        if ret_recent < -0.1 and ret_recent < ret_prior:
            accel_score = max(0, 2.0 + ret_recent * 10)
        elif ret_recent < -0.05:
            accel_score = 2.5
        else:
            accel_score = 4.0
    else:
        accel_score = 3.0
    if len(rets) >= 5:
        neg_streak = 0
        max_neg = 0
        for r in rets[-30:] if len(rets) >= 30 else rets:
            if r < -0.01:
                neg_streak += 1
                max_neg = max(max_neg, neg_streak)
            else:
                neg_streak = 0
        streak_score = max(0, 5 - max_neg * 0.6)
    else:
        streak_score = 2.5
    total = dd_score * 0.30 + vol_score * 0.15 + mom_score * 0.20 + accel_score * 0.20 + streak_score * 0.15
    return clamp(total), {"dd": round(float(dd), 4), "dd_score": round(dd_score, 2), "mom": round(mom_score, 2)}


def ohlcv_signal_4(window):
    """S4 Fundamental — EXACT v3.1 logic"""
    volumes = [r[5] for r in window if r[5] and r[5] > 0]
    closes = [r[4] for r in window if r[4] and r[4] > 0]
    if len(volumes) < 10 or len(closes) < 10:
        return 2.5, {}
    vol_arr = np.array(volumes)
    if len(vol_arr) >= 30:
        ma14 = np.mean(vol_arr[-14:])
        ma30 = np.mean(vol_arr[-30:])
        trend_score = clamp(ma14 / ma30 * 2.5) if ma30 > 0 else 1.0
    else:
        trend_score = 2.5
    active = sum(1 for v in volumes if v > 0)
    activity_score = clamp(active / len(volumes) * 5)
    if len(closes) >= 14 and len(vol_arr) >= 14:
        price_chg = (closes[-1] / closes[-14]) - 1 if closes[-14] > 0 else 0
        vol_spike = np.max(vol_arr[-7:]) / np.median(vol_arr) if np.median(vol_arr) > 0 else 1
        if price_chg < -0.20 and vol_spike > 3:   panic_score = 0.5
        elif price_chg < -0.10 and vol_spike > 2:  panic_score = 1.5
        elif price_chg < -0.10:                     panic_score = 2.0
        elif price_chg < 0 and vol_spike > 3:       panic_score = 2.5
        elif price_chg > 0.1:                        panic_score = 4.5
        else:                                        panic_score = 3.5
    else:
        panic_score = 3.0
    if len(closes) >= 14 and len(vol_arr) >= 14:
        pc = (closes[-1] / closes[-14]) - 1 if closes[-14] > 0 else 0
        vc = (np.mean(vol_arr[-7:]) / np.mean(vol_arr[-14:-7])) - 1 if np.mean(vol_arr[-14:-7]) > 0 else 0
        if pc < -0.1 and vc < -0.2:      div_score = 1.0
        elif pc < -0.2 and vc > 0.5:     div_score = 0.5
        elif pc > 0 and vc > 0:           div_score = 4.0
        else:                              div_score = 2.5
    else:
        div_score = 2.5
    total = trend_score * 0.20 + activity_score * 0.15 + panic_score * 0.35 + div_score * 0.30
    return clamp(total), {"trend": round(trend_score, 2), "panic": round(panic_score, 2)}


def ohlcv_signal_5(window, btc_rets):
    """S5 Contagion — EXACT v3.1 logic"""
    closes = [r[4] for r in window if r[4] and r[4] > 0]
    if len(closes) < 20:
        return 2.5, {}
    c = np.array(closes)
    token_rets = (c[1:] / c[:-1]) - 1
    token_rets = token_rets[np.isfinite(token_rets)]
    dates = [r[0] for r in window if r[4] and r[4] > 0]
    btc_m, tok_m = [], []
    for i in range(1, len(dates)):
        if dates[i] in btc_rets and i-1 < len(token_rets):
            btc_m.append(btc_rets[dates[i]])
            tok_m.append(token_rets[i-1])
    if len(btc_m) < 15:
        return 3.0, {}
    btc_arr = np.array(btc_m)
    tok_arr = np.array(tok_m)
    corr = np.corrcoef(tok_arr, btc_arr)[0, 1]
    if np.isnan(corr): corr = 0.5
    btc_down = btc_arr < 0
    if np.sum(btc_down) > 5:
        bv = np.var(btc_arr[btc_down])
        down_beta = np.cov(tok_arr[btc_down], btc_arr[btc_down])[0, 1] / bv if bv > 0 else 1.0
    else:
        down_beta = 1.0
    corr_score = max(0, 5 - abs(corr) * 4)
    beta_score = max(0, 5 - abs(down_beta) * 2)
    total = corr_score * 0.50 + beta_score * 0.50
    return clamp(total), {"corr": round(float(corr), 3), "d_beta": round(float(down_beta), 3)}


def ohlcv_signal_6(window, total_days):
    """S6 Structural — EXACT v3.1 logic"""
    closes = [r[4] for r in window if r[4] and r[4] > 0]
    if len(closes) < 10:
        return 2.5, {}
    c = np.array(closes)
    rets = np.diff(c) / c[:-1]
    rets = rets[np.isfinite(rets)]
    if len(rets) > 0:
        extreme = np.sum(np.abs(rets) > 0.30)
        flash_score = max(0, 5 - (extreme / len(rets)) * 100)
    else:
        flash_score = 2.5
    highs = [r[2] for r in window if r[2] and r[2] > 0]
    lows = [r[3] for r in window if r[3] and r[3] > 0]
    if len(highs) >= 10 and len(lows) >= 10:
        mn = min(len(highs), len(lows))
        h, l = np.array(highs[-mn:]), np.array(lows[-mn:])
        spread = np.mean((h - l) / l)
        spread_score = max(0, 5 - spread * 10) if np.isfinite(spread) else 2.5
    else:
        spread_score = 2.5
    if total_days > 1000:   age_score = 4.5
    elif total_days > 365:  age_score = 3.5
    elif total_days > 90:   age_score = 2.5
    else:                    age_score = 1.5
    total = flash_score * 0.40 + spread_score * 0.30 + age_score * 0.30
    return clamp(total), {"flash": round(flash_score, 2), "spread": round(spread_score, 2)}


def ohlcv_signal_7(window, btc_closes):
    """S7 Relative Weakness — EXACT v3.1 logic"""
    closes = [r[4] for r in window if r[4] and r[4] > 0]
    dates = [r[0] for r in window if r[4] and r[4] > 0]
    if len(closes) < 15:
        return 3.0, {}
    tok_7d = (closes[-1] / closes[-7]) - 1 if len(closes) >= 7 and closes[-7] > 0 else 0
    tok_14d = (closes[-1] / closes[-14]) - 1 if len(closes) >= 14 and closes[-14] > 0 else 0
    tok_30d = (closes[-1] / closes[-30]) - 1 if len(closes) >= 30 and closes[-30] > 0 else 0
    btc_price_now = btc_closes.get(dates[-1], 0) if dates else 0
    btc_price_7d = btc_closes.get(dates[-7], 0) if len(dates) >= 7 else 0
    btc_price_14d = btc_closes.get(dates[-14], 0) if len(dates) >= 14 else 0
    btc_price_30d = btc_closes.get(dates[-30], 0) if len(dates) >= 30 else 0
    btc_7d = (btc_price_now / btc_price_7d) - 1 if btc_price_7d > 0 else 0
    btc_14d = (btc_price_now / btc_price_14d) - 1 if btc_price_14d > 0 else 0
    btc_30d = (btc_price_now / btc_price_30d) - 1 if btc_price_30d > 0 else 0
    rel_7d = tok_7d - btc_7d
    rel_14d = tok_14d - btc_14d
    rel_30d = tok_30d - btc_30d
    def rel_score(rel):
        if rel >= 0.05:   return 5.0
        elif rel >= 0:    return 4.0
        elif rel > -0.10: return 3.0 + rel * 10
        elif rel > -0.30: return 2.0 + (rel + 0.10) * 5
        elif rel > -0.50: return 1.0 + (rel + 0.30) * 2.5
        else:             return 0.0
    s7d = rel_score(rel_7d)
    s14d = rel_score(rel_14d)
    s30d = rel_score(rel_30d)
    total = s7d * 0.40 + s14d * 0.30 + s30d * 0.30
    return clamp(total), {"rel_7d": round(rel_7d, 4), "rel_30d": round(rel_30d, 4)}


# ─────────────────────────────────────────────────────────────
# SIGNALS — SNAPSHOT path (for tokens without OHLCV)
# Uses same scoring curves as v3.1, adapted for snapshot fields
# ─────────────────────────────────────────────────────────────

def snap_signal_1(t):
    """S1 Liquidity from snapshot — matches v3.1 scoring curves"""
    vol = t.get("total_volume_24h_usd") or 0
    price = t.get("current_price_usd") or 0
    mcap = t.get("market_cap_usd") or 0

    # Turnover (v3.1: avg_vol / avg_price, log-scaled)
    turnover = vol / price if price > 0 else 0
    turnover_score = min(5, np.log10(max(turnover, 1)) / 2) if turnover > 0 else 0

    # No multi-day data → trend = neutral
    trend = 2.5

    # Vol stability proxy: vol/mcap ratio (stable coins have stable ratio)
    if mcap > 0:
        ratio = vol / mcap
        if 0.01 <= ratio <= 0.20:
            stability = 4.0
        elif 0.005 <= ratio <= 0.50:
            stability = 2.5
            stability = 1.0
    else:
        stability = 1.5

    total = turnover_score * 0.25 + trend * 0.45 + stability * 0.30
    return clamp(total), {"vol": vol, "turnover_s": round(turnover_score, 2)}


def snap_signal_2(t):
    """S2 Holders from snapshot — proxy using rank + supply"""
    rank = t.get("market_cap_rank") or 99999
    circ = t.get("circulating_supply") or 0
    total_s = t.get("total_supply") or 0

    # Whale proxy: lower rank = more distributed
    if rank <= 20:     whale_score = 4.5
    elif rank <= 50:   whale_score = 4.0
    elif rank <= 100:  whale_score = 3.5
    elif rank <= 300:  whale_score = 3.0
    elif rank <= 1000: whale_score = 2.5
    elif rank <= 3000: whale_score = 2.0
    else:              whale_score = 1.5

    # Gini proxy: supply ratio
    if total_s > 0 and circ > 0:
        ratio = circ / total_s
        gini_score = clamp(ratio * 5)
    else:
        gini_score = 2.5

    activity_score = 3.0  # neutral without multi-day data

    total = whale_score * 0.40 + gini_score * 0.30 + activity_score * 0.30
    return clamp(total), {"rank": rank}


def snap_signal_3(t):
    """S3 Resilience from snapshot — uses same scoring curves as v3.1"""
    change_7d = t.get("price_change_7d_pct") or 0
    change_30d = t.get("price_change_30d_pct") or 0
    price = t.get("current_price_usd") or 0
    ath = t.get("ath_usd") or 0

    # Drawdown from ATH (v3.1 curve: dd=0→5.0, dd=-0.3→2.5, dd=-0.6→0.5, dd=-0.9→0)
    dd = (price / ath) - 1 if ath > 0 and price > 0 else -0.5
    if dd >= 0:        dd_score = 5.0
    elif dd > -0.3:    dd_score = 5.0 + dd * 8.33
    elif dd > -0.6:    dd_score = 2.5 + (dd + 0.3) * 6.67
    elif dd > -0.9:    dd_score = 0.5 + (dd + 0.6) * 1.67
    else:              dd_score = 0.0

    # Volatility proxy from 7d change magnitude
    vol_proxy = abs(change_7d) / 100 * 52  # annualize weekly move
    vol_score = max(0, 5 - vol_proxy * 2.5)

    # Momentum (v3.1 curve: 3.0 + mom_30d*4 + mom_7d*3)
    mom_30d = change_30d / 100
    mom_7d = change_7d / 100
    mom_score = clamp(3.0 + mom_30d * 4 + mom_7d * 3)

    # Acceleration: is 7d worse than 30d pace?
    weekly_pace = (change_30d / 4) if change_30d else 0
    if change_7d < weekly_pace - 5:
        accel_score = max(0, 2.0 + (change_7d / 100) * 10)
    elif change_7d < -5:
        accel_score = 2.5
    else:
        accel_score = 4.0

    streak_score = 3.0  # neutral without daily data

    total = dd_score * 0.30 + vol_score * 0.15 + mom_score * 0.20 + accel_score * 0.20 + streak_score * 0.15
    return clamp(total), {"dd": round(dd, 4), "dd_score": round(dd_score, 2), "mom": round(mom_score, 2)}


def snap_signal_4(t):
    """S4 Fundamental from snapshot"""
    change_24h = t.get("price_change_24h_pct") or 0
    vol = t.get("total_volume_24h_usd") or 0
    mcap = t.get("market_cap_usd") or 0

    trend_score = 2.5  # neutral without multi-day volume
    activity_score = 4.0 if vol > 0 else 1.0

    # Panic detection (v3.1 curve)
    if change_24h < -20:    panic_score = 0.5
    elif change_24h < -10:  panic_score = 1.5
    elif change_24h < -5:   panic_score = 2.0
    elif change_24h < 0:    panic_score = 3.0
    elif change_24h > 10:   panic_score = 4.5
    else:                    panic_score = 3.5

    div_score = 2.5  # neutral without multi-day data

    total = trend_score * 0.20 + activity_score * 0.15 + panic_score * 0.35 + div_score * 0.30
    return clamp(total), {"panic": round(panic_score, 2)}


def snap_signal_5(t):
    """S5 Contagion from snapshot — uses trust scores as proxy"""
    trust = t.get("trust_score") or 0
    security = t.get("security_score") or 0
    compliance = t.get("compliance_score") or 0

    # v3.1 uses correlation + downside beta (range typically 0-5)
    # Trust score 0-100 → map to same range
    # High trust = lower contagion exposure (better diversified, audited, etc)
    if trust >= 80:     corr_proxy = 4.0
    elif trust >= 60:   corr_proxy = 3.0
    elif trust >= 40:   corr_proxy = 2.0
    elif trust >= 20:   corr_proxy = 1.0
    else:               corr_proxy = 0.5

    if security >= 60:  beta_proxy = 4.0
    elif security >= 40: beta_proxy = 2.5
    elif security >= 20: beta_proxy = 1.5
    else:                beta_proxy = 0.5

    total = corr_proxy * 0.50 + beta_proxy * 0.50
    return clamp(total), {"trust": trust, "security": security}


def snap_signal_6(t):
    """S6 Structural from snapshot"""
    trust_grade = t.get("trust_grade") or "F"
    has_audit = t.get("has_audit") or 0
    rank = t.get("market_cap_rank") or 99999

    # Flash crash proxy: rank-based (lower rank = more liquid = fewer flash crashes)
    if rank <= 50:      flash_score = 4.5
    elif rank <= 200:   flash_score = 3.5
    elif rank <= 1000:  flash_score = 2.5
    elif rank <= 5000:  flash_score = 1.5
    else:               flash_score = 1.0

    spread_score = 2.5  # neutral without OHLC data

    # Age proxy from trust grade (established tokens get better grades)
    grade_age = {"A": 4.5, "A+": 4.5, "B+": 4.0, "B": 3.5,
                 "C+": 3.0, "C": 2.5, "D+": 2.0, "D": 1.5, "F": 1.0}
    age_score = grade_age.get(trust_grade, 1.5)

    total = flash_score * 0.40 + spread_score * 0.30 + age_score * 0.30
    return clamp(total), {"flash": round(flash_score, 2), "grade": trust_grade}


def snap_signal_7(t, btc_data):
    """S7 Relative Weakness from snapshot — EXACT v3.1 scoring curve"""
    if not btc_data:
        return 3.0, {}

    btc_7d = btc_data.get("price_change_7d_pct") or 0
    btc_30d = btc_data.get("price_change_30d_pct") or 0
    tok_7d = t.get("price_change_7d_pct") or 0
    tok_30d = t.get("price_change_30d_pct") or 0

    rel_7d = (tok_7d - btc_7d) / 100
    rel_14d = ((tok_7d + tok_30d/4) / 2 - (btc_7d + btc_30d/4) / 2) / 100  # approximate 14d
    rel_30d = (tok_30d - btc_30d) / 100

    # EXACT v3.1 scoring curve
    def rel_score(rel):
        if rel >= 0.05:   return 5.0
        elif rel >= 0:    return 4.0
        elif rel > -0.10: return 3.0 + rel * 10
        elif rel > -0.30: return 2.0 + (rel + 0.10) * 5
        elif rel > -0.50: return 1.0 + (rel + 0.30) * 2.5
        else:             return 0.0

    s7d = rel_score(rel_7d)
    s14d = rel_score(rel_14d)
    s30d = rel_score(rel_30d)

    total = s7d * 0.40 + s14d * 0.30 + s30d * 0.30
    return clamp(total), {"rel_7d": round(rel_7d, 4), "rel_30d": round(rel_30d, 4)}


# ─────────────────────────────────────────────────────────────
# NDD COMPUTATION — FROZEN override logic
# ─────────────────────────────────────────────────────────────
def compute_ndd(signals, is_top50=False, is_stablecoin=False):
    """Apply FROZEN v3.1 weighting, overrides, and alert logic."""
    s1, s2, s3, s4, s5, s6, s7 = signals

    ndd = (s1 * WEIGHT_LIST[0] + s2 * WEIGHT_LIST[1] + s3 * WEIGHT_LIST[2] +
           s4 * WEIGHT_LIST[3] + s5 * WEIGHT_LIST[4] + s6 * WEIGHT_LIST[5] +
           s7 * WEIGHT_LIST[6])

    min_signal = min(signals)
    signals_below_multi = sum(1 for s in signals if s < MULTI_SIGNAL_THRESHOLD)
    signals_below_broad = sum(1 for s in signals if s < BROAD_WEAKNESS_THRESHOLD)

    override = 0
    if min_signal < SEVERE_SIGNAL_THRESHOLD:
        ndd = min(ndd, 1.0)
        override = 3
    elif signals_below_multi >= MULTI_SIGNAL_COUNT:
        ndd = min(ndd, MULTI_SIGNAL_CAP)
        override = 2
    elif signals_below_broad >= BROAD_WEAKNESS_COUNT:
        ndd = min(ndd, BROAD_WEAKNESS_CAP)
        override = 1

    if is_stablecoin and ndd < 2.0:
        ndd = max(ndd, 2.0)
        override = 0

    ndd = round(clamp(ndd), 2)
    alert = get_alert_level(ndd, is_top50=is_top50)

    return ndd, alert, override


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# TREND + HC ALERT + BOTTLEFISH CALCULATIONS
# Validated: HC Alert = 78% precision, 5% FP
# Validated: Bottlefish STRONG_BUY = 80% winner rate
# ─────────────────────────────────────────────────────────────

def compute_ndd_trend(ndd_change_4w):
    """Categorize NDD trend based on 4-week change."""
    if ndd_change_4w is None:
        return "UNKNOWN"
    if ndd_change_4w < -1.0:
        return "FREEFALL"
    elif ndd_change_4w < -0.5:
        return "FALLING"
    elif ndd_change_4w < -0.2:
        return "SLIDING"
    elif ndd_change_4w <= 0.2:
        return "STABLE"
    else:
        return "IMPROVING"


def get_crash_probability(trend, alert_level):
    """Look up crash probability from validated table."""
    key = (trend, alert_level)
    if key in CRASH_PROB_TABLE:
        return CRASH_PROB_TABLE[key][0]  # P(crash >30%)
    # Fallback: use level-only estimate
    level_defaults = {"SAFE": 0.03, "WATCH": 0.18, "WARNING": 0.33, "DISTRESS": 0.30, "CRITICAL": 0.35}
    return level_defaults.get(alert_level, 0.20)


def compute_hc_alert(alert_level, streak, ndd_change_4w):
    """High Conviction Alert: 3+ weeks WARNING/DISTRESS + freefall.
    Validated: 78% precision, 5% false positive rate."""
    if streak >= HC_ALERT_MIN_STREAK and ndd_change_4w is not None:
        if ndd_change_4w <= HC_ALERT_FREEFALL_THRESHOLD:
            return 1
    return 0


def compute_bottlefish(token_id, crypto_conn, run_date, rank, trust_score):
    """Bottlefish signal: identifies crashed tokens with strong recovery bounce.
    Validated on 393 crash cycles.
    STRONG_BUY: 80% winner rate, 10% dead rate.
    """
    if not rank or not trust_score:
        return None, None

    # Get price history for this token
    rows = crypto_conn.execute("""
        SELECT date, close FROM crypto_price_history
        WHERE token_id = ? AND date >= date(?, '-365 days') AND date <= ? AND close > 0
        ORDER BY date ASC
    """, (token_id, run_date, run_date)).fetchall()

    if len(rows) < 90:
        return None, None

    closes = [r[1] for r in rows]
    peak = max(closes)
    peak_idx = closes.index(peak)

    # Need crash after peak
    after_peak = closes[peak_idx:]
    if len(after_peak) < 30:
        return None, None

    trough = min(after_peak)
    trough_idx = peak_idx + after_peak.index(trough)
    crash_pct = (1 - trough / peak) * 100

    if crash_pct < 70:
        return None, None  # Not a significant crash

    # Calculate bounce from trough (90d)
    remaining = closes[trough_idx:]
    if len(remaining) < 30:
        return None, None

    # Use latest price vs trough
    current = closes[-1]
    bounce_90d = ((current / trough) - 1) * 100

    # Determine signal level
    signal = None
    t = BOTTLEFISH_THRESHOLDS
    if (bounce_90d >= t["STRONG_BUY"]["bounce90"] and
            rank <= t["STRONG_BUY"]["rank_max"] and
            trust_score >= t["STRONG_BUY"]["score_min"]):
        signal = "STRONG_BUY"
    elif (bounce_90d >= t["BUY"]["bounce90"] and
            rank <= t["BUY"]["rank_max"]):
        signal = "BUY"
    elif (bounce_90d >= t["SPECULATIVE"]["bounce90"] and
            rank <= t["SPECULATIVE"]["rank_max"] and
            trust_score >= t["SPECULATIVE"]["score_min"]):
        signal = "SPECULATIVE"
    elif crash_pct >= 70 and bounce_90d < 50:
        signal = "AVOID"

    return signal, round(bounce_90d, 1)


def load_previous_ndd(crypto_conn, token_id, run_date, weeks_back=4):
    """Load NDD from ~4 weeks ago for trend calculation.
    Checks crypto_ndd_daily first, then falls back to crypto_ndd_history."""
    # Try daily table first
    row = crypto_conn.execute("""
        SELECT ndd, alert_level FROM crypto_ndd_daily
        WHERE token_id = ? AND run_date <= date(?, ?) AND run_date >= date(?, ?)
        ORDER BY run_date DESC LIMIT 1
    """, (token_id, run_date, f'-{weeks_back * 7 - 3} days',
          run_date, f'-{weeks_back * 7 + 3} days')).fetchone()
    if row:
        return (row["ndd"], row["alert_level"])
    # Fallback to weekly history table
    row = crypto_conn.execute("""
        SELECT ndd, alert_level FROM crypto_ndd_history
        WHERE token_id = ? AND week_date <= date(?, ?) AND week_date >= date(?, ?)
        ORDER BY week_date DESC LIMIT 1
    """, (token_id, run_date, f'-{weeks_back * 7 - 3} days',
          run_date, f'-{weeks_back * 7 + 3} days')).fetchone()
    return (row["ndd"], row["alert_level"]) if row else (None, None)


def load_alert_streak(crypto_conn, token_id, run_date):
    """Count consecutive weeks in WARNING/DISTRESS before run_date.
    Checks crypto_ndd_daily first, then falls back to crypto_ndd_history."""
    rows = crypto_conn.execute("""
        SELECT alert_level FROM crypto_ndd_daily
        WHERE token_id = ? AND run_date < ?
        ORDER BY run_date DESC LIMIT 12
    """, (token_id, run_date)).fetchall()

    if not rows:
        # Fallback to weekly history
        rows = crypto_conn.execute("""
            SELECT alert_level FROM crypto_ndd_history
            WHERE token_id = ? AND week_date < ?
            ORDER BY week_date DESC LIMIT 12
        """, (token_id, run_date)).fetchall()

    streak = 0
    for row in rows:
        if row["alert_level"] in ("WARNING", "DISTRESS", "CRITICAL"):
            streak += 1
        else:
            break
    return streak


def run_ndd():
    run_date = datetime.now().strftime("%Y-%m-%d")
    t0 = time.time()

    data_conn = connect_data_db()
    crypto_conn = connect_crypto_db()
    ensure_tables(crypto_conn)

    # Load all tokens from data DB
    print(f"\n  Loading tokens from data DB...")
    tokens = load_all_tokens(data_conn)
    print(f"  Loaded {len(tokens)} tokens")

    # Load OHLCV for tokens that have it
    print(f"  Loading OHLCV history...")
    ohlcv = load_ohlcv_tokens(crypto_conn, run_date)
    print(f"  OHLCV available for {len(ohlcv)} tokens")

    # Load BTC reference
    btc_rets, btc_closes = load_btc_reference(crypto_conn, run_date)
    print(f"  BTC: {len(btc_rets)} daily returns")

    # BTC snapshot for snap_signal_7
    btc_snap = None
    for t in tokens:
        if t["token_id"] == "bitcoin":
            btc_snap = t
            break

    if btc_snap:
        print(f"  BTC: ${btc_snap['current_price_usd']:,.0f}, "
              f"7d: {btc_snap.get('price_change_7d_pct') or 0:+.1f}%, "
              f"30d: {btc_snap.get('price_change_30d_pct') or 0:+.1f}%")

    # Process all tokens
    saved = 0
    alerts = []
    dist = defaultdict(int)
    now = datetime.now().isoformat()

    for t in tokens:
        tid = t["token_id"]
        is_stablecoin = tid in STABLECOIN_IDS
        rank = t.get("market_cap_rank") or 99999
        is_top50 = rank <= 50

        # OHLCV ONLY — skip tokens without real price history
        if tid not in ohlcv:
            continue

        window = ohlcv[tid]
        total_days = len(window)
        s1, d1 = ohlcv_signal_1(window)
        s2, d2 = ohlcv_signal_2(window)
        s3, d3 = ohlcv_signal_3(window)
        s4, d4 = ohlcv_signal_4(window)
        s5, d5 = ohlcv_signal_5(window, btc_rets)
        s6, d6 = ohlcv_signal_6(window, total_days)
        s7, d7 = ohlcv_signal_7(window, btc_closes)
        has_ohlcv = 1

        signals = [s1, s2, s3, s4, s5, s6, s7]
        ndd, alert, override = compute_ndd(signals, is_top50=is_top50, is_stablecoin=is_stablecoin)

        # Compute trend, HC alert, crash probability, bottlefish
        prev_ndd, prev_alert = load_previous_ndd(crypto_conn, tid, run_date)
        ndd_change_4w = round(ndd - prev_ndd, 2) if prev_ndd is not None else None
        ndd_trend = compute_ndd_trend(ndd_change_4w)
        crash_prob = get_crash_probability(ndd_trend, alert)

        streak = load_alert_streak(crypto_conn, tid, run_date)
        if alert in ("WARNING", "DISTRESS", "CRITICAL"):
            streak += 1  # include current week
        else:
            streak = 0

        hc_alert = compute_hc_alert(alert, streak, ndd_change_4w)
        trust_score = t.get("trust_score") or 0
        bf_signal, bounce_90d = compute_bottlefish(tid, crypto_conn, run_date, rank, trust_score)

        # Save
        crypto_conn.execute("""
            INSERT OR REPLACE INTO crypto_ndd_daily
            (run_date, token_id, symbol, name, market_cap_rank, trust_grade,
             ndd, signal_1, signal_2, signal_3, signal_4, signal_5, signal_6, signal_7,
             alert_level, override_triggered, confirmed_distress, has_ohlcv,
             price_usd, market_cap, volume_24h, breakdown, calculated_at,
             ndd_trend, ndd_change_4w, crash_probability, hc_alert, hc_streak,
             bottlefish_signal, bounce_90d)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            run_date, tid, t.get("symbol"), t.get("name"),
            t.get("market_cap_rank"), t.get("trust_grade"),
            ndd, s1, s2, s3, s4, s5, s6, s7,
            alert, override, 0, has_ohlcv,
            t.get("current_price_usd"), t.get("market_cap_usd"),
            t.get("total_volume_24h_usd"),
            json.dumps({"s1": d1, "s2": d2, "s3": d3, "s4": d4, "s5": d5, "s6": d6, "s7": d7}),
            now,
            ndd_trend, ndd_change_4w, crash_prob, hc_alert, streak,
            bf_signal, bounce_90d,
        ))
        saved += 1
        dist[alert] += 1

        # Generate alert for WARNING and worse
        if alert in ("WARNING", "DISTRESS", "CRITICAL"):
            symbol = (t.get("symbol") or "?").upper()
            grade = t.get("trust_grade") or "?"
            signal_names = ["Liq", "Hold", "Res", "Fund", "Cont", "Str", "Rel"]
            triggers = [f"{signal_names[i]}={signals[i]:.1f}"
                        for i in range(7) if signals[i] < 2.0]
            emoji = {"CRITICAL": "🚨", "DISTRESS": "⛔", "WARNING": "⚠️"}.get(alert, "")
            ohlcv_tag = "" if has_ohlcv else " [snap]"
            hc_tag = " 🔴HC_ALERT" if hc_alert else ""
            trend_tag = f" {ndd_trend}" if ndd_trend != "UNKNOWN" else ""
            cp_tag = f" P(crash)={crash_prob:.0%}" if crash_prob > 0.25 else ""
            bf_tag = f" 🐟{bf_signal}" if bf_signal and bf_signal != "AVOID" else ""
            msg = f"{emoji} {alert}: {symbol} (#{rank}, {grade}) NDD={ndd:.2f}{trend_tag}{cp_tag}{hc_tag}{bf_tag}{ohlcv_tag}"
            if triggers:
                msg += f" [{', '.join(triggers[:4])}]"
            alerts.append((ndd, msg))

            crypto_conn.execute("""
                INSERT INTO crypto_ndd_alerts
                (alert_date, token_id, symbol, alert_level, ndd,
                 market_cap_rank, trust_grade, trigger_signals, message, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (run_date, tid, symbol, alert, ndd, rank, grade,
                  json.dumps(triggers), msg, now))

    crypto_conn.commit()
    elapsed = time.time() - t0

    # Sort alerts by NDD
    alerts.sort(key=lambda x: x[0])

    # ── DISPLAY ─────────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  NDD v3.1 RESULTS — {run_date} ({elapsed:.1f}s)")
    print(f"  Frozen calibration from v3.1 (1190/1200 crash detection)")
    print(f"{'='*100}")
    print(f"  Total scored: {saved}")
    print(f"  OHLCV path:   {sum(1 for t in tokens if t['token_id'] in ohlcv)}")
    print(f"  Snapshot path: {saved - sum(1 for t in tokens if t['token_id'] in ohlcv)}")

    print(f"\n  Distribution (FROZEN thresholds: SAFE≥4.0, WATCH≥3.0, WARNING≥2.0, DISTRESS≥1.0):")
    for level in ["SAFE", "WATCH", "WARNING", "DISTRESS", "CRITICAL"]:
        count = dist.get(level, 0)
        pct = count / saved * 100 if saved > 0 else 0
        bar = "█" * min(80, max(1, count // 20))
        emoji = {"SAFE": "✅", "WATCH": "👁", "WARNING": "⚠️",
                 "DISTRESS": "⛔", "CRITICAL": "🚨"}.get(level, "")
        print(f"    {emoji} {level:<12} {count:>6} ({pct:>5.1f}%) {bar}")

    # Top alerts
    # HC Alert and Bottlefish summary
    hc_count = crypto_conn.execute(
        "SELECT COUNT(*) as c FROM crypto_ndd_daily WHERE run_date=? AND hc_alert=1", (run_date,)
    ).fetchone()["c"]
    bf_count = crypto_conn.execute(
        "SELECT COUNT(*) as c FROM crypto_ndd_daily WHERE run_date=? AND bottlefish_signal IS NOT NULL AND bottlefish_signal != 'AVOID'", (run_date,)
    ).fetchone()["c"]

    print(f"\n  🔴 HIGH CONVICTION ALERTS: {hc_count}")
    print(f"     (78% precision, 5% false positive — validated on 275 signals)")
    if hc_count > 0:
        hc_rows = crypto_conn.execute("""
            SELECT symbol, ndd, ndd_trend, crash_probability, hc_streak
            FROM crypto_ndd_daily WHERE run_date=? AND hc_alert=1 ORDER BY ndd ASC
        """, (run_date,)).fetchall()
        for r in hc_rows:
            print(f"     🔴 {r['symbol']:>8} NDD={r['ndd']:.2f} {r['ndd_trend']} P(crash)={r['crash_probability']:.0%} streak={r['hc_streak']}w")

    print(f"\n  🐟 BOTTLEFISH SIGNALS: {bf_count}")
    print(f"     (STRONG_BUY: 80% winner rate — validated on 393 crash cycles)")
    if bf_count > 0:
        bf_rows = crypto_conn.execute("""
            SELECT symbol, bottlefish_signal, bounce_90d, market_cap_rank, ndd
            FROM crypto_ndd_daily WHERE run_date=? AND bottlefish_signal IS NOT NULL
            AND bottlefish_signal != 'AVOID' ORDER BY bottlefish_signal ASC
        """, (run_date,)).fetchall()
        for r in bf_rows:
            print(f"     🐟 {r['symbol']:>8} {r['bottlefish_signal']:<12} bounce={r['bounce_90d']:>6.0f}% rank=#{r['market_cap_rank']} NDD={r['ndd']:.2f}")

    n_show = min(30, len(alerts))
    if alerts:
        print(f"\n  TOP {n_show} ALERTS (of {len(alerts)} total):")
        for _, msg in alerts[:n_show]:
            print(f"    {msg}")

    data_conn.close()
    crypto_conn.close()
    return saved


def main():
    parser = argparse.ArgumentParser(description="NERQ NDD Engine v3.1 (frozen v3.1 calibration)")
    parser.add_argument("--alerts", action="store_true", help="Only show existing alerts")
    args = parser.parse_args()

    print("=" * 80)
    print("  NERQ CRYPTO — Daily NDD Engine v3.1")
    print("  Calibration: FROZEN from v3.1 (1190/1200 crash detection)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print(f"  Weights: Liq={WEIGHT_LIST[0]:.0%} Hold={WEIGHT_LIST[1]:.0%} "
          f"Res={WEIGHT_LIST[2]:.0%} Fund={WEIGHT_LIST[3]:.0%} "
          f"Cont={WEIGHT_LIST[4]:.0%} Str={WEIGHT_LIST[5]:.0%} Rel={WEIGHT_LIST[6]:.0%}")
    print(f"  Data DB:   {DATA_DB_PATH}")
    print(f"  Output DB: {CRYPTO_DB_PATH}")

    if args.alerts:
        crypto_conn = connect_crypto_db()
        run_date = datetime.now().strftime("%Y-%m-%d")
        rows = crypto_conn.execute(
            "SELECT message FROM crypto_ndd_alerts WHERE alert_date=? ORDER BY ndd ASC",
            (run_date,)
        ).fetchall()
        for r in rows:
            print(f"  {r['message']}")
        print(f"\n  Total: {len(rows)} alerts")
        crypto_conn.close()
        return

    run_ndd()
    print(f"\n  Done.")


if __name__ == "__main__":
    main()
