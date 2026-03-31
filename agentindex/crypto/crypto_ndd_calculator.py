#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 1, Uppgift 1.3
crypto_ndd_calculator.py v3.1

Förbättringar v3.1 (baserat på signalkorrelationsanalys):
- Omfördelade vikter baserat på prediktiv kraft
- S1 Liquidity 20%→10% (kontraproduktiv — högt vid krascher)
- S2 Holders 15%→5% (kontraproduktiv)
- S3 Resilience 30%→30% (behålls — näst bäst prediktor)
- S4 Fundamental 15%→10% (nästan slumpmässig)
- S5 Contagion 10%→25% (starkaste prediktorn: -1.14 diff crash vs stable)
- S6 Structural 10%→5% (svag signal)
- NY S7 Relative Weakness 15% (token vs BTC underprestation)

Plus v3-förbättringar: stablecoin-filter, confirmed distress, tightare override, mcap-trösklar.

NDD 0-5 skala: 5 = helt säker, 0 = omedelbar kollapsrisk.
"""

import sqlite3
import numpy as np
import logging
import argparse
import os
import sys
import json
from datetime import datetime, timezone, timedelta, date

DB_PATH = "crypto_trust.db"

# v3.1: Omfördelade vikter baserat på signalkorrelationsanalys
NDD_WEIGHTS = {
    "liquidity_depth":       0.10,   # v3: 0.20 → minskat (kontraproduktiv)
    "holder_concentration":  0.05,   # v3: 0.15 → minskat (kontraproduktiv)
    "ecosystem_resilience":  0.30,   # behålls (stark prediktor)
    "fundamental_activity":  0.10,   # v3: 0.15 → minskat (slumpmässig)
    "contagion_exposure":    0.25,   # v3: 0.10 → ÖKAD (starkaste prediktorn)
    "structural_risk":       0.05,   # v3: 0.10 → minskat (svag)
    "relative_weakness":     0.15,   # NY — token vs marknads-underprestation
}

# v3 override-parametrar behålls
SEVERE_SIGNAL_THRESHOLD = 0.5
MULTI_SIGNAL_THRESHOLD = 1.5
MULTI_SIGNAL_COUNT = 2

# v3.1: Sänkt multi-signal cap (var 2.0 → nu 1.5)
MULTI_SIGNAL_CAP = 1.5
# NY: 3+ signaler under 2.0 → cap 1.5
BROAD_WEAKNESS_THRESHOLD = 2.0
BROAD_WEAKNESS_COUNT = 3
BROAD_WEAKNESS_CAP = 1.5

TOP50_WARNING_THRESHOLD = 1.5

STABLECOIN_IDS = {
    "tether", "usd-coin", "binance-usd", "dai", "true-usd", "paxos-standard",
    "frax", "gemini-dollar", "husd", "alchemix-usd", "liquity-usd",
    "paypal-usd", "first-digital-usd", "ripple-usd", "usdd",
    "crvusd", "euro-coin", "stasis-eurs", "tether-gold",
    "ondo-us-dollar-yield", "usd1-wlfi", "astherus-usdf", "falcon-finance",
}

NDD_LOOKBACK = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("crypto_ndd_calculator.log", encoding="utf-8")
    ]
)
log = logging.getLogger("nerq_ndd")


# ─────────────────────────────────────────────
# DATABAS
# ─────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_ndd_history (
            token_id    TEXT NOT NULL,
            week_date   TEXT NOT NULL,
            ndd         REAL NOT NULL,
            signal_1    REAL, signal_2 REAL, signal_3 REAL,
            signal_4    REAL, signal_5 REAL, signal_6 REAL,
            signal_7    REAL,
            alert_level TEXT,
            override_triggered INTEGER DEFAULT 0,
            confirmed_distress INTEGER DEFAULT 0,
            breakdown   TEXT,
            calculated_at TEXT NOT NULL,
            PRIMARY KEY (token_id, week_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ndd_tw ON crypto_ndd_history(token_id, week_date)")
    conn.commit()
    return conn


def load_price_data(conn, token_id):
    return conn.execute("""
        SELECT date, open, high, low, close, volume
        FROM crypto_price_history WHERE token_id = ? ORDER BY date ASC
    """, (token_id,)).fetchall()


def load_btc_data(conn):
    """v3.1: Laddar både returns och closes för S7"""
    rows = conn.execute("""
        SELECT date, close FROM crypto_price_history
        WHERE token_id = 'bitcoin' ORDER BY date ASC
    """).fetchall()
    rets = {}
    closes = {}
    for i, (d, c) in enumerate(rows):
        closes[d] = c
        if i > 0 and rows[i][1] and rows[i-1][1] and rows[i-1][1] > 0:
            rets[d] = (rows[i][1] / rows[i-1][1]) - 1
    return rets, closes


def get_tokens(conn):
    return conn.execute("""
        SELECT token_id, name, symbol, market_cap_rank, rows_fetched
        FROM crypto_fetch_status
        WHERE status = 'completed' AND rows_fetched > 60
        ORDER BY market_cap_rank ASC
    """).fetchall()


def clamp(val, lo=0.0, hi=5.0):
    return max(lo, min(hi, float(val)))


def get_weekly_dates(first_date_str, last_date_str):
    first = date.fromisoformat(first_date_str)
    last = date.fromisoformat(last_date_str)
    d = first + timedelta(days=NDD_LOOKBACK)
    d = d + timedelta(days=(7 - d.weekday()) % 7)
    weeks = []
    while d <= last:
        weeks.append(d.isoformat())
        d += timedelta(days=7)
    return weeks


def slice_data(price_data, end_date, days=60):
    start = (date.fromisoformat(end_date) - timedelta(days=days)).isoformat()
    return [r for r in price_data if start <= r[0] <= end_date]


def get_alert_level(ndd, is_top50=False):
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


# ─────────────────────────────────────────────
# SIGNAL 1: LIQUIDITY DEPTH (10%)
# ─────────────────────────────────────────────

def calc_signal_1(window):
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
    return clamp(total), {"turnover": round(turnover_score, 2), "trend": round(trend, 2), "stability": round(stability, 2)}


# ─────────────────────────────────────────────
# SIGNAL 2: HOLDER CONCENTRATION (5%)
# ─────────────────────────────────────────────

def calc_signal_2(window):
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


# ─────────────────────────────────────────────
# SIGNAL 3: ECOSYSTEM RESILIENCE (30%)
# ─────────────────────────────────────────────

def calc_signal_3(window):
    closes = [r[4] for r in window if r[4] and r[4] > 0]
    if len(closes) < 15:
        return 2.5, {}

    c = np.array(closes)
    rets = np.diff(c) / c[:-1]
    rets = rets[np.isfinite(rets)]

    peak = np.max(c)
    current = c[-1]
    dd = (current - peak) / peak if peak > 0 else 0
    if dd >= 0:
        dd_score = 5.0
    elif dd > -0.3:
        dd_score = 5.0 + dd * 8.33
    elif dd > -0.6:
        dd_score = 2.5 + (dd + 0.3) * 6.67
    elif dd > -0.9:
        dd_score = 0.5 + (dd + 0.6) * 1.67
    else:
        dd_score = 0.0

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
    return clamp(total), {
        "dd": round(float(dd), 4), "dd_score": round(dd_score, 2),
        "vol_score": round(vol_score, 2), "mom_score": round(mom_score, 2),
        "accel_score": round(accel_score, 2), "streak_score": round(streak_score, 2),
    }


# ─────────────────────────────────────────────
# SIGNAL 4: FUNDAMENTAL ACTIVITY (10%)
# ─────────────────────────────────────────────

def calc_signal_4(window):
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

        if price_chg < -0.20 and vol_spike > 3:
            panic_score = 0.5
        elif price_chg < -0.10 and vol_spike > 2:
            panic_score = 1.5
        elif price_chg < -0.10:
            panic_score = 2.0
        elif price_chg < 0 and vol_spike > 3:
            panic_score = 2.5
        elif price_chg > 0.1:
            panic_score = 4.5
        else:
            panic_score = 3.5
    else:
        panic_score = 3.0

    if len(closes) >= 14 and len(vol_arr) >= 14:
        pc = (closes[-1] / closes[-14]) - 1 if closes[-14] > 0 else 0
        vc = (np.mean(vol_arr[-7:]) / np.mean(vol_arr[-14:-7])) - 1 if np.mean(vol_arr[-14:-7]) > 0 else 0
        if pc < -0.1 and vc < -0.2:
            div_score = 1.0
        elif pc < -0.2 and vc > 0.5:
            div_score = 0.5
        elif pc > 0 and vc > 0:
            div_score = 4.0
        else:
            div_score = 2.5
    else:
        div_score = 2.5

    total = trend_score * 0.20 + activity_score * 0.15 + panic_score * 0.35 + div_score * 0.30
    return clamp(total), {
        "trend": round(trend_score, 2), "panic": round(panic_score, 2), "div": round(div_score, 2),
    }


# ─────────────────────────────────────────────
# SIGNAL 5: CONTAGION EXPOSURE (25%)
# ─────────────────────────────────────────────

def calc_signal_5(window, btc_rets, week_date):
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


# ─────────────────────────────────────────────
# SIGNAL 6: STRUCTURAL RISK (5%)
# ─────────────────────────────────────────────

def calc_signal_6(window, all_data, week_date):
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

    total_days = len(all_data)
    if total_days > 1000: age_score = 4.5
    elif total_days > 365: age_score = 3.5
    elif total_days > 90: age_score = 2.5
    else: age_score = 1.5

    total = flash_score * 0.40 + spread_score * 0.30 + age_score * 0.30
    return clamp(total), {"flash": round(flash_score, 2), "spread": round(spread_score, 2), "age": round(age_score, 2)}


# ─────────────────────────────────────────────
# SIGNAL 7: RELATIVE WEAKNESS (15%) — v3.1 NY
# ─────────────────────────────────────────────

def calc_signal_7(window, btc_closes, week_date):
    """
    Mäter token-prestation relativt BTC.
    Om BTC går +5% men token går -10% = stark varningssignal.
    Beräknar relativ return över 7d, 14d, 30d.
    """
    closes = [r[4] for r in window if r[4] and r[4] > 0]
    dates = [r[0] for r in window if r[4] and r[4] > 0]
    if len(closes) < 15:
        return 3.0, {}

    # Token returns
    tok_7d = (closes[-1] / closes[-7]) - 1 if len(closes) >= 7 and closes[-7] > 0 else 0
    tok_14d = (closes[-1] / closes[-14]) - 1 if len(closes) >= 14 and closes[-14] > 0 else 0
    tok_30d = (closes[-1] / closes[-30]) - 1 if len(closes) >= 30 and closes[-30] > 0 else 0

    # BTC returns för samma perioder
    btc_price_now = btc_closes.get(dates[-1], 0) if dates else 0
    btc_price_7d = btc_closes.get(dates[-7], 0) if len(dates) >= 7 else 0
    btc_price_14d = btc_closes.get(dates[-14], 0) if len(dates) >= 14 else 0
    btc_price_30d = btc_closes.get(dates[-30], 0) if len(dates) >= 30 else 0

    btc_7d = (btc_price_now / btc_price_7d) - 1 if btc_price_7d > 0 else 0
    btc_14d = (btc_price_now / btc_price_14d) - 1 if btc_price_14d > 0 else 0
    btc_30d = (btc_price_now / btc_price_30d) - 1 if btc_price_30d > 0 else 0

    # Relativ prestation (token minus BTC)
    rel_7d = tok_7d - btc_7d
    rel_14d = tok_14d - btc_14d
    rel_30d = tok_30d - btc_30d

    # Scoring: 0% relative → 3.5, -10% → 2.5, -30% → 1.0, -50%+ → 0.0
    def rel_score(rel):
        if rel >= 0.05:   return 5.0
        elif rel >= 0:    return 4.0
        elif rel > -0.10: return 3.0 + rel * 10   # -10% → 2.0
        elif rel > -0.30: return 2.0 + (rel + 0.10) * 5   # -30% → 1.0
        elif rel > -0.50: return 1.0 + (rel + 0.30) * 2.5  # -50% → 0.5
        else:             return 0.0

    s7d = rel_score(rel_7d)
    s14d = rel_score(rel_14d)
    s30d = rel_score(rel_30d)

    # Vikta: 7d viktigast (fångar snabba fall), 30d ger kontext
    total = s7d * 0.40 + s14d * 0.30 + s30d * 0.30
    return clamp(total), {
        "rel_7d": round(rel_7d, 4), "rel_14d": round(rel_14d, 4), "rel_30d": round(rel_30d, 4),
        "s7d": round(s7d, 2), "s14d": round(s14d, 2), "s30d": round(s30d, 2),
    }


# ─────────────────────────────────────────────
# NDD BERÄKNING v3.1
# ─────────────────────────────────────────────

def calculate_ndd(conn, token_id, name, symbol, rank, btc_rets, btc_closes, idx, total_tokens):
    price_data = load_price_data(conn, token_id)
    if len(price_data) < 60:
        return 0

    first_date = price_data[0][0]
    last_date = price_data[-1][0]
    weeks = get_weekly_dates(first_date, last_date)
    if not weeks:
        return 0

    is_stablecoin = token_id in STABLECOIN_IDS
    is_top50 = rank is not None and rank <= 50

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    results = []
    prev_ndd = None

    for week_date in weeks:
        window = slice_data(price_data, week_date, NDD_LOOKBACK)
        if len(window) < 15:
            continue

        s1, d1 = calc_signal_1(window)
        s2, d2 = calc_signal_2(window)
        s3, d3 = calc_signal_3(window)
        s4, d4 = calc_signal_4(window)
        s5, d5 = calc_signal_5(window, btc_rets, week_date)
        s6, d6 = calc_signal_6(window, price_data, week_date)
        s7, d7 = calc_signal_7(window, btc_closes, week_date)

        signals = [s1, s2, s3, s4, s5, s6, s7]
        min_signal = min(signals)
        signals_below_multi = sum(1 for s in signals if s < MULTI_SIGNAL_THRESHOLD)
        signals_below_broad = sum(1 for s in signals if s < BROAD_WEAKNESS_THRESHOLD)

        # Viktad NDD
        ndd = (
            s1 * NDD_WEIGHTS["liquidity_depth"] +
            s2 * NDD_WEIGHTS["holder_concentration"] +
            s3 * NDD_WEIGHTS["ecosystem_resilience"] +
            s4 * NDD_WEIGHTS["fundamental_activity"] +
            s5 * NDD_WEIGHTS["contagion_exposure"] +
            s6 * NDD_WEIGHTS["structural_risk"] +
            s7 * NDD_WEIGHTS["relative_weakness"]
        )

        # v3.1: TRESTEGS-OVERRIDE
        override = 0
        if min_signal < SEVERE_SIGNAL_THRESHOLD:
            # 1 signal under 0.5 = absolut kris
            ndd = min(ndd, 1.0)
            override = 3
        elif signals_below_multi >= MULTI_SIGNAL_COUNT:
            # 2+ signaler under 1.5 = allvarlig svaghet
            ndd = min(ndd, MULTI_SIGNAL_CAP)  # v3.1: cap 1.5 (var 2.0)
            override = 2
        elif signals_below_broad >= BROAD_WEAKNESS_COUNT:
            # 3+ signaler under 2.0 = bred svaghet
            ndd = min(ndd, BROAD_WEAKNESS_CAP)
            override = 1

        # Stablecoin-filter
        if is_stablecoin and ndd < 2.0:
            ndd = max(ndd, 2.0)
            override = 0

        ndd = round(clamp(ndd), 2)
        alert = get_alert_level(ndd, is_top50=is_top50)

        # Confirmed DISTRESS
        confirmed = 0
        if ndd <= 1.5 and prev_ndd is not None and prev_ndd <= 1.5:
            confirmed = 1
        elif ndd <= 1.0:
            confirmed = 1

        breakdown = json.dumps({
            "s1_liquidity": {"v": round(s1,2), **d1},
            "s2_holders": {"v": round(s2,2), **d2},
            "s3_resilience": {"v": round(s3,2), **d3},
            "s4_fundamental": {"v": round(s4,2), **d4},
            "s5_contagion": {"v": round(s5,2), **d5},
            "s6_structural": {"v": round(s6,2), **d6},
            "s7_relative": {"v": round(s7,2), **d7},
            "min_signal": round(min_signal, 2),
            "signals_below_1.5": signals_below_multi,
            "signals_below_2.0": signals_below_broad,
            "override": override,
            "is_stablecoin": is_stablecoin,
            "is_top50": is_top50,
            "confirmed_distress": confirmed,
        })

        results.append({
            "token_id": token_id, "week_date": week_date, "ndd": ndd,
            "signal_1": round(s1,2), "signal_2": round(s2,2), "signal_3": round(s3,2),
            "signal_4": round(s4,2), "signal_5": round(s5,2), "signal_6": round(s6,2),
            "signal_7": round(s7,2),
            "alert_level": alert, "override_triggered": override,
            "confirmed_distress": confirmed,
            "breakdown": breakdown, "calculated_at": now,
        })

        prev_ndd = ndd

    if results:
        conn.executemany("""
            INSERT OR REPLACE INTO crypto_ndd_history
            (token_id, week_date, ndd, signal_1, signal_2, signal_3, signal_4,
             signal_5, signal_6, signal_7, alert_level, override_triggered, confirmed_distress,
             breakdown, calculated_at)
            VALUES (:token_id, :week_date, :ndd, :signal_1, :signal_2, :signal_3,
                    :signal_4, :signal_5, :signal_6, :signal_7, :alert_level, :override_triggered,
                    :confirmed_distress, :breakdown, :calculated_at)
        """, results)
        conn.commit()

        latest = results[-1]
        markers = {"SAFE":"🟢","WATCH":"🟡","WARNING":"🟠","DISTRESS":"🔴","CRITICAL":"⛔"}
        m = markers.get(latest["alert_level"], "")
        ovr = " [OVR]" if latest["override_triggered"] else ""
        conf = " [CONF]" if latest["confirmed_distress"] else ""
        stbl = " [STABLE]" if is_stablecoin else ""
        log.info(f"[{idx}/{total_tokens}] {name} ({symbol}): NDD={latest['ndd']:.2f} {m} {latest['alert_level']}{ovr}{conf}{stbl} | {len(results)} veckor")

    return len(results)


def validate_collapses(conn):
    log.info("\n" + "=" * 60)
    log.info("RETROAKTIV VALIDERING v3.1 — Kända kollapser")
    log.info("=" * 60)

    targets = []
    for pattern in ['%luna%', '%lunc%', '%terra%']:
        ids = conn.execute("SELECT DISTINCT token_id FROM crypto_ndd_history WHERE token_id LIKE ?", (pattern,)).fetchall()
        for (tid,) in ids:
            targets.append((tid, "LUNA/LUNC", "2022-05-09", "2022-01-01", "2022-06-01"))

    for pattern in ['%ftx%', '%ftt%']:
        ids = conn.execute("SELECT DISTINCT token_id FROM crypto_ndd_history WHERE token_id LIKE ?", (pattern,)).fetchall()
        for (tid,) in ids:
            targets.append((tid, "FTT", "2022-11-08", "2022-08-01", "2022-12-01"))

    # v3.1: Lägg till OHM, AVAX, NEAR
    extra = [
        ("olympus", "OHM", "2022-03-07", "2021-10-01", "2022-06-01"),
        ("avalanche-2", "AVAX", "2022-05-16", "2022-01-01", "2022-06-01"),
        ("near", "NEAR", "2022-05-16", "2022-01-01", "2022-06-01"),
    ]
    for tid, name, collapse, start, end in extra:
        exists = conn.execute("SELECT COUNT(*) FROM crypto_ndd_history WHERE token_id = ?", (tid,)).fetchone()[0]
        if exists:
            targets.append((tid, name, collapse, start, end))

    if not targets:
        log.info("Inga tokens i databasen.")
        return

    seen = set()
    for tid, name, collapse, start, end in targets:
        if tid in seen:
            continue
        seen.add(tid)

        log.info(f"\n--- {name} ({tid}) — Kollaps: {collapse} ---")
        rows = conn.execute("""
            SELECT week_date, ndd, alert_level, signal_1, signal_2, signal_3, signal_4, 
                   signal_5, signal_6, signal_7, override_triggered, confirmed_distress
            FROM crypto_ndd_history WHERE token_id = ? AND week_date BETWEEN ? AND ?
            ORDER BY week_date
        """, (tid, start, end)).fetchall()

        if not rows:
            log.info(f"  Ingen NDD-data {start} → {end}")
            continue

        for wd, ndd, alert, s1, s2, s3, s4, s5, s6, s7, ovr, conf in rows:
            flag = "⚠️" if ndd < 2.0 else "🔴" if ndd < 2.5 else "  "
            ovr_str = " [OVR]" if ovr else ""
            conf_str = " [CONF]" if conf else ""
            log.info(f"  {wd}: NDD={ndd:.2f} [{alert:>8}] {flag}{ovr_str}{conf_str} "
                     f"Liq={s1:.1f} Hold={s2:.1f} Res={s3:.1f} Fund={s4:.1f} Cont={s5:.1f} Str={s6:.1f} Rel={s7:.1f}")

        min_ndd = min(r[1] for r in rows)
        min_date = [r[0] for r in rows if r[1] == min_ndd][0]
        distress_weeks = sum(1 for r in rows if r[1] < 2.0)
        confirmed_weeks = sum(1 for r in rows if r[11] == 1)

        log.info(f"  → Lägsta NDD: {min_ndd:.2f} ({min_date})")
        log.info(f"  → Veckor i DISTRESS (<2.0): {distress_weeks}")
        log.info(f"  → Confirmed DISTRESS: {confirmed_weeks}")

        if min_ndd < 1.5:
            log.info(f"  ✅ FRAMGÅNG: NDD flaggade DISTRESS (< 1.5)")
        elif min_ndd < 2.0:
            log.info(f"  ✅ FRAMGÅNG: NDD flaggade WARNING/DISTRESS (< 2.0)")
        elif min_ndd < 2.5:
            log.info(f"  ⚠️ DELVIS: NDD visade WARNING (< 2.5)")
        else:
            log.info(f"  ❌ MISSLYCKADES: Min NDD = {min_ndd:.2f}")


def run(token_filter=None, do_validate=False):
    log.info("=" * 60)
    log.info("NERQ CRYPTO — NDD v3.1 (Network Distress Detector)")
    log.info("v3.1: Ny S7 Relative Weakness, omfördelade vikter, trestegs-override")
    log.info(f"Databas: {DB_PATH}")
    log.info("=" * 60)

    conn = init_db()

    log.info("Laddar BTC-referensdata...")
    btc_rets, btc_closes = load_btc_data(conn)
    log.info(f"BTC: {len(btc_rets)} dagliga returns, {len(btc_closes)} closes")

    tokens = get_tokens(conn)
    if token_filter:
        tokens = [t for t in tokens if t[0] == token_filter]

    if not tokens:
        log.error("Inga tokens!")
        return

    log.info(f"Beräknar NDD för {len(tokens)} tokens...")
    log.info(f"Stablecoins i filter: {len(STABLECOIN_IDS)}")
    log.info(f"Vikter: {json.dumps({k: f'{v:.0%}' for k,v in NDD_WEIGHTS.items()})}")
    log.info("-" * 60)

    import time
    t0 = time.time()
    total_ndds = 0

    for i, (tid, name, sym, rank, rows) in enumerate(tokens, 1):
        try:
            total_ndds += calculate_ndd(conn, tid, name or tid, sym or "?", rank, btc_rets, btc_closes, i, len(tokens))
        except Exception as e:
            log.error(f"[{i}] {name}: {e}")

    elapsed = time.time() - t0
    log.info("=" * 60)
    log.info(f"KLART! {total_ndds:,} NDD-beräkningar ({elapsed:.1f}s)")

    # Alert-distribution
    dist = conn.execute("""
        SELECT alert_level, COUNT(*) FROM crypto_ndd_history GROUP BY alert_level
        ORDER BY CASE alert_level WHEN 'CRITICAL' THEN 1 WHEN 'DISTRESS' THEN 2
        WHEN 'WARNING' THEN 3 WHEN 'WATCH' THEN 4 WHEN 'SAFE' THEN 5 END
    """).fetchall()
    markers = {"SAFE":"🟢","WATCH":"🟡","WARNING":"🟠","DISTRESS":"🔴","CRITICAL":"⛔"}
    log.info("\nAlert-distribution:")
    for alert, count in dist:
        log.info(f"  {markers.get(alert,'')} {alert:>8}: {count:>6}")

    overrides = conn.execute("SELECT COUNT(*) FROM crypto_ndd_history WHERE override_triggered > 0").fetchone()[0]
    confirmed = conn.execute("SELECT COUNT(*) FROM crypto_ndd_history WHERE confirmed_distress = 1").fetchone()[0]
    log.info(f"\nOverrides: {overrides:,}")
    log.info(f"Confirmed DISTRESS: {confirmed:,}")

    # Lägst NDD nu
    latest = conn.execute("SELECT MAX(week_date) FROM crypto_ndd_history").fetchone()[0]
    if latest:
        bottom = conn.execute("""
            SELECT n.token_id, f.name, f.symbol, n.ndd, n.alert_level, n.override_triggered, n.confirmed_distress, n.signal_7
            FROM crypto_ndd_history n JOIN crypto_fetch_status f ON n.token_id = f.token_id
            WHERE n.week_date = ? ORDER BY n.ndd ASC LIMIT 15
        """, (latest,)).fetchall()
        log.info(f"\nLägst NDD ({latest}):")
        for tid, name, sym, ndd, alert, ovr, conf, s7 in bottom:
            m = markers.get(alert, "")
            o = " [OVR]" if ovr else ""
            c = " [CONF]" if conf else ""
            s = " [STABLE]" if tid in STABLECOIN_IDS else ""
            log.info(f"  {name:>25} ({sym:>6}): NDD={ndd:.2f} {m} {alert}{o}{c}{s} S7={s7:.1f}")

    if do_validate:
        validate_collapses(conn)

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="NERQ Crypto — NDD v3.1")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--token", type=str)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.status:
        conn = init_db()
        t = conn.execute("SELECT COUNT(*) FROM crypto_ndd_history").fetchone()[0]
        log.info(f"NDD-rader: {t:,}")
        conn.close()
        return

    run(token_filter=args.token, do_validate=args.validate)


if __name__ == "__main__":
    main()
