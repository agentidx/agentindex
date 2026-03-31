#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 1, Uppgift 1.2
crypto_rating_engine.py

Beräknar retroaktiv Credit Rating per token per månad (jan 2021 → nu).
5-pelare system med Moody's-stil rating (Aaa → D).

Pelare (vikter):
  1. Ecosystem Strength    (25%) — volymstabilitet, handelsaktivitet, mcap-proxy
  2. Contagion Risk         (25%) — BTC-korrelation, beta, idiosynkratisk risk
  3. Historical Resilience  (20%) — max drawdown, recovery speed, volatilitet
  4. Fundamental Quality    (15%) — token-ålder, volymkonsistens, prisstruktur
  5. Rug Pull Risk          (15%) — volym-anomalier, pris-spikes, likviditetsrisker

Input:  crypto_trust.db (från uppgift 1.1 — 240K+ prisrader)
Output: crypto_rating_history tabell med ~14,400 datapunkter

Användning:
    python3 crypto_rating_engine.py
    python3 crypto_rating_engine.py --status
    python3 crypto_rating_engine.py --token bitcoin
"""

import sqlite3
import numpy as np
import logging
import argparse
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ─────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────

DB_PATH = "crypto_trust.db"

# Rating-skala (Moody's-stil)
RATING_SCALE = [
    ("Aaa", 95), ("Aa1", 90), ("Aa2", 85), ("Aa3", 80),
    ("A1",  75), ("A2",  70), ("A3",  65),
    ("Baa1", 60), ("Baa2", 55), ("Baa3", 50),
    ("Ba1", 45), ("Ba2", 40), ("Ba3", 35),
    ("B1",  30), ("B2",  25), ("B3",  20),
    ("Caa1", 15), ("Caa2", 10), ("Caa3", 5),
    ("D",   0),
]

# Pelare-vikter
WEIGHTS = {
    "ecosystem_strength":   0.25,
    "contagion_risk":       0.25,
    "historical_resilience": 0.20,
    "fundamental_quality":  0.15,
    "rug_pull_risk":        0.15,
}

# Lookback-period i dagar för beräkningar
LOOKBACK_DAYS = 90

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("crypto_rating_engine.log", encoding="utf-8")
    ]
)
log = logging.getLogger("nerq_rating")


# ─────────────────────────────────────────────
# DATABAS
# ─────────────────────────────────────────────

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_rating_history (
            token_id    TEXT NOT NULL,
            year_month  TEXT NOT NULL,
            rating      TEXT NOT NULL,
            score       REAL NOT NULL,
            pillar_1    REAL,
            pillar_2    REAL,
            pillar_3    REAL,
            pillar_4    REAL,
            pillar_5    REAL,
            breakdown   TEXT,
            calculated_at TEXT NOT NULL,
            PRIMARY KEY (token_id, year_month)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rating_token
        ON crypto_rating_history(token_id, year_month)
    """)
    conn.commit()
    return conn


def load_price_data(conn, token_id):
    """Ladda all prisdata för en token som sorterad lista."""
    rows = conn.execute("""
        SELECT date, open, high, low, close, volume, market_cap
        FROM crypto_price_history
        WHERE token_id = ?
        ORDER BY date ASC
    """, (token_id,)).fetchall()
    return rows


def load_btc_prices(conn):
    """Ladda BTC close-priser som dict {date: close}."""
    rows = conn.execute("""
        SELECT date, close FROM crypto_price_history
        WHERE token_id = 'bitcoin' ORDER BY date ASC
    """).fetchall()
    return {r[0]: r[1] for r in rows if r[1]}


def get_tokens(conn):
    """Hämta alla tokens med tillräckligt data."""
    rows = conn.execute("""
        SELECT token_id, name, symbol, market_cap_rank, rows_fetched
        FROM crypto_fetch_status
        WHERE status = 'completed' AND rows_fetched > 30
        ORDER BY market_cap_rank ASC
    """).fetchall()
    return rows


# ─────────────────────────────────────────────
# HJÄLPFUNKTIONER
# ─────────────────────────────────────────────

def get_monthly_periods(first_date, last_date):
    """Generera lista av (year_month, period_start, period_end)."""
    from datetime import date
    periods = []
    d = date.fromisoformat(first_date).replace(day=1)
    end = date.fromisoformat(last_date)

    while d <= end:
        ym = d.strftime("%Y-%m")
        # Period: 90 dagar bakåt från sista dagen i månaden
        if d.month == 12:
            next_month = d.replace(year=d.year+1, month=1, day=1)
        else:
            next_month = d.replace(month=d.month+1, day=1)
        month_end = next_month - timedelta(days=1)
        if month_end > end:
            month_end = end
        period_start = month_end - timedelta(days=LOOKBACK_DAYS)
        periods.append((ym, period_start.isoformat(), month_end.isoformat()))
        d = next_month

    return periods


def closes_in_range(price_data, start_date, end_date):
    """Extrahera close-priser inom datumintervall."""
    return [r[4] for r in price_data if start_date <= r[0] <= end_date and r[4] and r[4] > 0]


def volumes_in_range(price_data, start_date, end_date):
    """Extrahera volymer inom datumintervall."""
    return [r[5] for r in price_data if start_date <= r[0] <= end_date and r[5] and r[5] > 0]


def highs_lows_in_range(price_data, start_date, end_date):
    """Extrahera high/low inom datumintervall."""
    highs = [r[2] for r in price_data if start_date <= r[0] <= end_date and r[2] and r[2] > 0]
    lows = [r[3] for r in price_data if start_date <= r[0] <= end_date and r[3] and r[3] > 0]
    return highs, lows


def daily_returns(closes):
    """Beräkna dagliga avkastningar."""
    if len(closes) < 2:
        return []
    c = np.array(closes)
    return list((c[1:] / c[:-1]) - 1)


def max_drawdown(closes):
    """Beräkna maximum drawdown."""
    if len(closes) < 2:
        return 0
    c = np.array(closes)
    peak = np.maximum.accumulate(c)
    dd = (c - peak) / peak
    return float(np.min(dd))


def recovery_speed(closes):
    """
    Mät hur snabbt priset återhämtar sig efter drawdown.
    Returnerar ratio: dagar i drawdown > -20% / totala dagar.
    Lägre = bättre (snabbare recovery).
    """
    if len(closes) < 10:
        return 0.5
    c = np.array(closes)
    peak = np.maximum.accumulate(c)
    dd = (c - peak) / peak
    deep_dd_days = np.sum(dd < -0.20)
    return float(deep_dd_days / len(closes))


def score_to_rating(score):
    """Konvertera numerisk score (0-100) till Moody's-stil rating."""
    for rating, threshold in RATING_SCALE:
        if score >= threshold:
            return rating
    return "D"


def clamp(val, lo=0, hi=100):
    return max(lo, min(hi, val))


# ─────────────────────────────────────────────
# PELARE 1: ECOSYSTEM STRENGTH (25%)
# ─────────────────────────────────────────────

def calc_pillar_1(closes, volumes, rank):
    """
    Ecosystem Strength — mäter marknadsstyrka och stabilitet.

    Faktorer:
    - Volymstabilitet (volym CoV — lägre = stabilare ekosystem)
    - Genomsnittlig daglig volym (USD) — proxy för exchange listings
    - Market cap rank — proxy för ekosystembredd
    - Handelsaktivitet (dagar med volym / totala dagar)
    """
    if len(closes) < 10 or len(volumes) < 10:
        return 20.0, {"reason": "insufficient_data"}

    scores = []

    # 1a. Volymstabilitet (CoV) — lägre variation = bättre
    vol_arr = np.array(volumes)
    vol_mean = np.mean(vol_arr)
    vol_std = np.std(vol_arr)
    vol_cov = vol_std / vol_mean if vol_mean > 0 else 5
    # CoV < 0.5 = excellent (100), CoV > 3 = terrible (0)
    vol_stability_score = clamp(100 - (vol_cov - 0.5) * 40)
    scores.append(vol_stability_score * 0.25)

    # 1b. Genomsnittlig daglig volym (USD)
    # > $1B/dag = 100, < $10K/dag = 0
    if vol_mean > 0:
        vol_log = np.log10(vol_mean)
        vol_size_score = clamp((vol_log - 4) * 20)  # log10(10K)=4, log10(1B)=9
    else:
        vol_size_score = 0
    scores.append(vol_size_score * 0.30)

    # 1c. Market cap rank — topp 10 = 100, rank 300 = 20
    if rank and rank > 0:
        rank_score = clamp(100 - (rank - 1) * 0.35)
    else:
        rank_score = 30
    scores.append(rank_score * 0.25)

    # 1d. Handelsaktivitet — dagar med volym > 0
    active_days = sum(1 for v in volumes if v > 0)
    activity_ratio = active_days / len(volumes) if volumes else 0
    activity_score = clamp(activity_ratio * 100)
    scores.append(activity_score * 0.20)

    total = sum(scores)
    breakdown = {
        "vol_stability": round(vol_stability_score, 1),
        "vol_size": round(vol_size_score, 1),
        "rank": round(rank_score, 1),
        "activity": round(activity_score, 1),
    }
    return round(clamp(total), 2), breakdown


# ─────────────────────────────────────────────
# PELARE 2: CONTAGION RISK (25%)
# ─────────────────────────────────────────────

def calc_pillar_2(closes, btc_closes_aligned):
    """
    Contagion Risk — mäter exponering mot systemisk risk.
    INVERTERAD: hög score = LÅG risk (bra).

    Faktorer:
    - BTC-korrelation — hög korrelation = mer exponerad
    - Beta mot BTC — hög beta = mer volatil vid BTC-rörelser
    - Idiosynkratisk risk — andel av varians som INTE förklaras av BTC
    """
    if len(closes) < 20 or len(btc_closes_aligned) < 20:
        return 40.0, {"reason": "insufficient_data"}

    token_rets = np.array(daily_returns(closes))
    btc_rets = np.array(daily_returns(btc_closes_aligned))

    # Matcha längder
    min_len = min(len(token_rets), len(btc_rets))
    if min_len < 15:
        return 40.0, {"reason": "insufficient_overlap"}
    token_rets = token_rets[-min_len:]
    btc_rets = btc_rets[-min_len:]

    # 2a. BTC-korrelation
    corr = np.corrcoef(token_rets, btc_rets)[0, 1]
    if np.isnan(corr):
        corr = 0.5
    # Korrelation 0.3 = bra (diversifierad), 0.95 = dåligt (helt exponerad)
    corr_score = clamp(100 - abs(corr) * 100)
    # Negativ korrelation är ok men ovanligt, ge lite bonus
    if corr < 0:
        corr_score = min(100, corr_score + 10)

    # 2b. Beta mot BTC
    btc_var = np.var(btc_rets)
    if btc_var > 0:
        beta = np.cov(token_rets, btc_rets)[0, 1] / btc_var
    else:
        beta = 1.0
    # Beta 0.5 = bra, Beta > 2 = mycket känslig
    beta_score = clamp(100 - (abs(beta) - 0.5) * 40)

    # 2c. Idiosynkratisk risk (R² med BTC)
    if btc_var > 0 and np.var(token_rets) > 0:
        r_squared = corr ** 2
        # Hög R² = mest av variansen förklaras av BTC = systemisk risk
        # Låg R² = mest idiosynkratisk (kan vara bra eller dåligt)
        # Mellanting ~0.3-0.5 R² = bäst (delvis diversifierad)
        if r_squared < 0.3:
            idio_score = 60  # Okänd risk, inte nödvändigtvis bra
        elif r_squared < 0.6:
            idio_score = 80  # Bra diversifiering
        else:
            idio_score = max(20, 100 - r_squared * 100)
    else:
        idio_score = 40

    total = corr_score * 0.40 + beta_score * 0.35 + idio_score * 0.25
    breakdown = {
        "btc_correlation": round(float(corr), 3),
        "beta": round(float(beta), 3),
        "r_squared": round(float(corr**2), 3),
        "corr_score": round(corr_score, 1),
        "beta_score": round(beta_score, 1),
        "idio_score": round(idio_score, 1),
    }
    return round(clamp(total), 2), breakdown


# ─────────────────────────────────────────────
# PELARE 3: HISTORICAL RESILIENCE (20%)
# ─────────────────────────────────────────────

def calc_pillar_3(closes):
    """
    Historical Resilience — mäter hur väl token tål nedgångar.

    Faktorer:
    - Max drawdown — djupare = sämre
    - Recovery speed — längre tid i djup drawdown = sämre
    - Volatilitet — lägre = bättre
    - Tail risk — andel dagar med >10% förlust
    """
    if len(closes) < 20:
        return 30.0, {"reason": "insufficient_data"}

    rets = np.array(daily_returns(closes))

    # 3a. Max drawdown
    mdd = max_drawdown(closes)  # Negativ siffra
    # MDD > -10% = excellent (100), MDD < -90% = terrible (0)
    mdd_score = clamp(100 + mdd * 111)  # -90% → 0, 0% → 100

    # 3b. Recovery speed
    rec = recovery_speed(closes)
    # 0% av tid i djup DD = 100, 80%+ = 0
    rec_score = clamp(100 - rec * 125)

    # 3c. Volatilitet (annualiserad)
    vol = float(np.std(rets) * np.sqrt(365)) if len(rets) > 1 else 2.0
    # Vol < 30% = excellent, Vol > 200% = terrible
    vol_score = clamp(100 - (vol - 0.3) * 58)

    # 3d. Tail risk — dagar med > 10% förlust
    tail_days = np.sum(rets < -0.10)
    tail_ratio = tail_days / len(rets) if len(rets) > 0 else 0.1
    # 0% tail days = 100, > 5% = 0
    tail_score = clamp(100 - tail_ratio * 2000)

    total = mdd_score * 0.30 + rec_score * 0.25 + vol_score * 0.25 + tail_score * 0.20
    breakdown = {
        "max_drawdown": round(float(mdd), 4),
        "recovery_ratio": round(float(rec), 4),
        "annualized_vol": round(float(vol), 4),
        "tail_risk_ratio": round(float(tail_ratio), 4),
        "mdd_score": round(mdd_score, 1),
        "rec_score": round(rec_score, 1),
        "vol_score": round(vol_score, 1),
        "tail_score": round(tail_score, 1),
    }
    return round(clamp(total), 2), breakdown


# ─────────────────────────────────────────────
# PELARE 4: FUNDAMENTAL QUALITY (15%)
# ─────────────────────────────────────────────

def calc_pillar_4(closes, volumes, token_first_date, period_end):
    """
    Fundamental Quality — proxy baserad på tillgänglig data.

    Faktorer (proxy — berikas med GitHub/on-chain data senare):
    - Token-ålder — äldre = mer beprövad
    - Volymkonsistens — stabil volym = riktig användning
    - Prisstruktur — extremt låga priser kan indikera dålig tokenomics
    - Volym/pris-förhållande — hälsosam handelsaktivitet
    """
    if len(closes) < 10:
        return 25.0, {"reason": "insufficient_data"}

    from datetime import date

    # 4a. Token-ålder (dagar sedan första data)
    try:
        first = date.fromisoformat(token_first_date)
        end = date.fromisoformat(period_end)
        age_days = (end - first).days
    except:
        age_days = 0
    # > 1500 dagar (4+ år) = 100, < 30 dagar = 10
    age_score = clamp(10 + (age_days / 1500) * 90)

    # 4b. Volymkonsistens — % av dagar med signifikant volym
    if volumes:
        median_vol = np.median(volumes) if volumes else 0
        consistent_days = sum(1 for v in volumes if v > median_vol * 0.1)
        consistency = consistent_days / len(volumes)
        consistency_score = clamp(consistency * 100)
    else:
        consistency_score = 20

    # 4c. Prisstruktur — extremt låga priser ofta = meme/scam
    avg_price = np.mean(closes) if closes else 0
    if avg_price > 1.0:
        price_score = 70  # Normal prisstruktur
    elif avg_price > 0.01:
        price_score = 50  # Lågt men kan vara legit (DOGE, SHIB)
    elif avg_price > 0.000001:
        price_score = 30  # Mycket lågt, troligen meme
    else:
        price_score = 10  # Extremt lågt

    # 4d. Volym/pris-förhållande — volymtrend
    if len(volumes) >= 30:
        first_half = np.mean(volumes[:len(volumes)//2])
        second_half = np.mean(volumes[len(volumes)//2:])
        if first_half > 0:
            vol_trend = second_half / first_half
            # Stabil/växande volym = bra
            if vol_trend > 0.8:
                trend_score = 70
            elif vol_trend > 0.4:
                trend_score = 50
            else:
                trend_score = 25  # Sjunkande volym = dåligt
        else:
            trend_score = 30
    else:
        trend_score = 40

    total = age_score * 0.30 + consistency_score * 0.25 + price_score * 0.25 + trend_score * 0.20
    breakdown = {
        "age_days": age_days,
        "age_score": round(age_score, 1),
        "consistency_score": round(consistency_score, 1),
        "price_score": round(price_score, 1),
        "trend_score": round(trend_score, 1),
    }
    return round(clamp(total), 2), breakdown


# ─────────────────────────────────────────────
# PELARE 5: RUG PULL RISK (15%)
# ─────────────────────────────────────────────

def calc_pillar_5(closes, volumes, rank):
    """
    Rug Pull Risk — INVERTERAD (hög score = låg rug risk = bra).

    Faktorer (proxy — berikas med on-chain data senare):
    - Volym-anomalier — plötsliga volymspikes kan vara manipulation
    - Prisstabilitet — extrema dagliga moves > 50% = varning
    - Likviditetsrisk — förhållande volym/pris-storlek
    - Market cap rank — topp-tokens har låg rug risk
    """
    if len(closes) < 10:
        return 30.0, {"reason": "insufficient_data"}

    rets = np.array(daily_returns(closes))

    # 5a. Volym-anomalier — dagar med volym > 10x median
    if volumes and len(volumes) > 5:
        vol_arr = np.array(volumes)
        vol_median = np.median(vol_arr)
        if vol_median > 0:
            anomaly_days = np.sum(vol_arr > vol_median * 10)
            anomaly_ratio = anomaly_days / len(vol_arr)
            # 0% anomalier = 100, > 10% = 0
            anomaly_score = clamp(100 - anomaly_ratio * 1000)
        else:
            anomaly_score = 30
    else:
        anomaly_score = 40

    # 5b. Extrema prisrörelser (>50% på en dag = rug risk signal)
    extreme_moves = np.sum(np.abs(rets) > 0.50) if len(rets) > 0 else 0
    extreme_ratio = extreme_moves / len(rets) if len(rets) > 0 else 0.1
    extreme_score = clamp(100 - extreme_ratio * 5000)

    # 5c. Nedåt-bias — fler extrema ned-dagar än upp-dagar = potentiell dump
    if len(rets) > 10:
        big_down = np.sum(rets < -0.20)
        big_up = np.sum(rets > 0.20)
        if big_down > 0 and big_up > 0:
            dump_ratio = big_down / (big_down + big_up)
            dump_score = clamp(100 - dump_ratio * 100)
        elif big_down > 0:
            dump_score = 20
        else:
            dump_score = 80
    else:
        dump_score = 50

    # 5d. Market cap rank som safety proxy
    if rank and rank > 0:
        if rank <= 20:
            rank_safety = 95
        elif rank <= 50:
            rank_safety = 80
        elif rank <= 100:
            rank_safety = 65
        elif rank <= 200:
            rank_safety = 45
        else:
            rank_safety = 30
    else:
        rank_safety = 25

    total = anomaly_score * 0.25 + extreme_score * 0.30 + dump_score * 0.20 + rank_safety * 0.25
    breakdown = {
        "anomaly_score": round(anomaly_score, 1),
        "extreme_score": round(extreme_score, 1),
        "dump_score": round(dump_score, 1),
        "rank_safety": round(rank_safety, 1),
    }
    return round(clamp(total), 2), breakdown


# ─────────────────────────────────────────────
# HUVUDLOGIK
# ─────────────────────────────────────────────

def rate_token(conn, token_id, name, symbol, rank, btc_prices, idx, total):
    """Beräkna rating per månad för en token."""

    price_data = load_price_data(conn, token_id)
    if not price_data or len(price_data) < 30:
        log.info(f"[{idx}/{total}] {name}: för lite data ({len(price_data)} rader), hoppar över")
        return 0

    first_date = price_data[0][0]
    last_date = price_data[-1][0]
    periods = get_monthly_periods(first_date, last_date)

    # Filtrera: börja först när vi har minst 30 dagars data
    from datetime import date
    min_start = (date.fromisoformat(first_date) + timedelta(days=30)).isoformat()
    periods = [(ym, s, e) for ym, s, e in periods if e >= min_start]

    if not periods:
        return 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ratings = []

    for ym, period_start, period_end in periods:
        # Extrahera data för perioden
        closes = closes_in_range(price_data, period_start, period_end)
        volumes = volumes_in_range(price_data, period_start, period_end)

        if len(closes) < 15:
            continue

        # BTC close-priser för samma period (för korrelation)
        btc_closes = [btc_prices.get(r[0]) for r in price_data
                      if period_start <= r[0] <= period_end and btc_prices.get(r[0])]

        # Beräkna varje pelare
        p1_score, p1_detail = calc_pillar_1(closes, volumes, rank)
        p2_score, p2_detail = calc_pillar_2(closes, btc_closes)
        p3_score, p3_detail = calc_pillar_3(closes)
        p4_score, p4_detail = calc_pillar_4(closes, volumes, first_date, period_end)
        p5_score, p5_detail = calc_pillar_5(closes, volumes, rank)

        # Viktad total
        total_score = (
            p1_score * WEIGHTS["ecosystem_strength"] +
            p2_score * WEIGHTS["contagion_risk"] +
            p3_score * WEIGHTS["historical_resilience"] +
            p4_score * WEIGHTS["fundamental_quality"] +
            p5_score * WEIGHTS["rug_pull_risk"]
        )
        total_score = round(clamp(total_score), 2)

        rating = score_to_rating(total_score)

        breakdown = {
            "ecosystem_strength": {"score": p1_score, "weight": 0.25, **p1_detail},
            "contagion_risk": {"score": p2_score, "weight": 0.25, **p2_detail},
            "historical_resilience": {"score": p3_score, "weight": 0.20, **p3_detail},
            "fundamental_quality": {"score": p4_score, "weight": 0.15, **p4_detail},
            "rug_pull_risk": {"score": p5_score, "weight": 0.15, **p5_detail},
        }

        ratings.append({
            "token_id": token_id,
            "year_month": ym,
            "rating": rating,
            "score": total_score,
            "pillar_1": p1_score,
            "pillar_2": p2_score,
            "pillar_3": p3_score,
            "pillar_4": p4_score,
            "pillar_5": p5_score,
            "breakdown": json.dumps(breakdown),
            "calculated_at": now,
        })

    if ratings:
        conn.executemany("""
            INSERT OR REPLACE INTO crypto_rating_history
            (token_id, year_month, rating, score, pillar_1, pillar_2, pillar_3,
             pillar_4, pillar_5, breakdown, calculated_at)
            VALUES (:token_id, :year_month, :rating, :score, :pillar_1, :pillar_2,
                    :pillar_3, :pillar_4, :pillar_5, :breakdown, :calculated_at)
        """, ratings)
        conn.commit()

        # Visa senaste rating
        latest = ratings[-1]
        log.info(f"[{idx}/{total}] {name} ({symbol}): {latest['rating']} ({latest['score']:.1f}) "
                 f"| P1={latest['pillar_1']:.0f} P2={latest['pillar_2']:.0f} "
                 f"P3={latest['pillar_3']:.0f} P4={latest['pillar_4']:.0f} P5={latest['pillar_5']:.0f} "
                 f"| {len(ratings)} månader")

    return len(ratings)


def run(token_filter=None):
    log.info("=" * 60)
    log.info("NERQ CRYPTO — Credit Rating Engine")
    log.info(f"Databas: {DB_PATH}")
    log.info(f"5-pelare system, Moody's-skala (Aaa → D)")
    log.info(f"Lookback: {LOOKBACK_DAYS} dagar per beräkning")
    log.info("=" * 60)

    conn = init_db(DB_PATH)

    # Ladda BTC-priser (referens för korrelation)
    log.info("Laddar BTC-referenspriser...")
    btc_prices = load_btc_prices(conn)
    log.info(f"BTC: {len(btc_prices)} dagar")

    # Hämta tokens
    tokens = get_tokens(conn)
    if token_filter:
        tokens = [t for t in tokens if t[0] == token_filter]

    if not tokens:
        log.error("Inga tokens att beräkna!")
        return

    log.info(f"Beräknar ratings för {len(tokens)} tokens...")
    log.info("-" * 60)

    total_ratings = 0
    import time
    t0 = time.time()

    for i, (tid, name, symbol, rank, rows) in enumerate(tokens, 1):
        try:
            count = rate_token(conn, tid, name or tid, symbol or "?", rank or 999, btc_prices, i, len(tokens))
            total_ratings += count
        except Exception as e:
            log.error(f"[{i}/{len(tokens)}] {name}: FEL — {e}")

    elapsed = time.time() - t0

    # Sammanfattning
    log.info("=" * 60)
    log.info(f"KLART! {total_ratings:,} ratings genererade för {len(tokens)} tokens ({elapsed:.1f}s)")

    # Rating-distribution
    dist = conn.execute("""
        SELECT rating, COUNT(*) FROM crypto_rating_history
        GROUP BY rating ORDER BY
        CASE rating
            WHEN 'Aaa' THEN 1 WHEN 'Aa1' THEN 2 WHEN 'Aa2' THEN 3 WHEN 'Aa3' THEN 4
            WHEN 'A1' THEN 5 WHEN 'A2' THEN 6 WHEN 'A3' THEN 7
            WHEN 'Baa1' THEN 8 WHEN 'Baa2' THEN 9 WHEN 'Baa3' THEN 10
            WHEN 'Ba1' THEN 11 WHEN 'Ba2' THEN 12 WHEN 'Ba3' THEN 13
            WHEN 'B1' THEN 14 WHEN 'B2' THEN 15 WHEN 'B3' THEN 16
            WHEN 'Caa1' THEN 17 WHEN 'Caa2' THEN 18 WHEN 'Caa3' THEN 19
            WHEN 'D' THEN 20
        END
    """).fetchall()

    log.info("Rating-distribution:")
    for rating, count in dist:
        bar = "█" * min(50, count // 20)
        log.info(f"  {rating:>4}: {count:>5} {bar}")

    # Topp-tokens senaste rating
    log.info("\nTopp 20 tokens — senaste rating:")
    top = conn.execute("""
        SELECT r.token_id, f.name, f.symbol, r.rating, r.score, r.year_month
        FROM crypto_rating_history r
        JOIN crypto_fetch_status f ON r.token_id = f.token_id
        WHERE r.year_month = (SELECT MAX(year_month) FROM crypto_rating_history WHERE token_id = r.token_id)
        AND f.market_cap_rank <= 20
        ORDER BY f.market_cap_rank ASC
    """).fetchall()
    for tid, name, sym, rating, score, ym in top:
        log.info(f"  {name:>25} ({sym:>6}): {rating:>4} ({score:.1f})")

    conn.close()


def show_status():
    if not os.path.exists(DB_PATH):
        print(f"Databas {DB_PATH} finns inte.")
        return
    conn = init_db(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM crypto_rating_history").fetchone()[0]
    tokens = conn.execute("SELECT COUNT(DISTINCT token_id) FROM crypto_rating_history").fetchone()[0]
    months = conn.execute("SELECT COUNT(DISTINCT year_month) FROM crypto_rating_history").fetchone()[0]
    ym_range = conn.execute("SELECT MIN(year_month), MAX(year_month) FROM crypto_rating_history").fetchone()

    log.info(f"Ratings: {total:,} | Tokens: {tokens} | Månader: {months} | "
             f"Spann: {ym_range[0] or '?'} → {ym_range[1] or '?'}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="NERQ Crypto — Credit Rating Engine")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--token", type=str, help="Beräkna bara specifik token")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    run(token_filter=args.token)


if __name__ == "__main__":
    main()
