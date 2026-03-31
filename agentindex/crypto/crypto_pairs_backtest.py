#!/usr/bin/env python3
"""
NERQ CRYPTO — Task 1.4 v2: Pairs Portfolio Backtest
====================================================
Fixes from v1:
  1. Winsorize pair returns at ±200% (eliminate outlier explosions)
  2. Filter out stablecoins from pair universe
  3. Minimum liquidity filter (avg daily volume)
  4. NDD filter: skip shorting tokens with NDD < 1.5 (distress recovery risk)
  5. Require minimum price data coverage (>70% of trading days)

Run:  python3 crypto_pairs_backtest.py
"""

import sqlite3
import os
import sys
import json
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
DB_NAME = "crypto_trust.db"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)

IN_SAMPLE_START  = "2021-01-01"
IN_SAMPLE_END    = "2023-12-31"
OUT_SAMPLE_START = "2024-01-01"
OUT_SAMPLE_END   = "2025-12-31"

HOLD_DAYS = 90

# ── FILTERS (NEW in v2) ──
MAX_RETURN_CAP = 2.0        # Winsorize: cap any single leg at ±200%
MIN_AVG_VOLUME = 50_000     # Minimum avg daily volume (USD) to include token
MIN_PRICE_COVERAGE = 0.70   # Token must have prices for 70%+ of trading days
MIN_NDD_FOR_SHORT = 1.5     # Don't short tokens with NDD below this (recovery risk)

# Stablecoins to exclude (they don't move → bad long candidates)
STABLECOINS = {
    "tether", "usd-coin", "binance-usd", "dai", "true-usd", "paxos-standard",
    "gusd", "frax", "usdd", "tusd", "busd", "lusd", "susd", "eurs", "usdp",
    "first-digital-usd", "ethena-usde", "usde", "paypal-usd", "fdusd",
    "stasis-eur", "gemini-dollar", "husd", "nusd", "musd", "cusd",
    "terrausd", "ust", "magic-internet-money",
}

RATING_CLASSES = {
    "IG_HIGH":  ["Aaa", "Aa1", "Aa2", "Aa3"],
    "IG_MID":   ["A1", "A2", "A3"],
    "IG_LOW":   ["Baa1", "Baa2", "Baa3"],
    "HY_HIGH":  ["Ba1", "Ba2", "Ba3"],
    "HY_LOW":   ["B1", "B2", "B3"],
    "DISTRESS": ["Caa1", "Caa2", "Caa3", "Ca", "C", "D"],
}

RATING_TO_CLASS = {}
for cls, ratings in RATING_CLASSES.items():
    for r in ratings:
        RATING_TO_CLASS[r] = cls

DEFAULT_WEIGHTS = [0.25, 0.25, 0.20, 0.15, 0.15]

# Expanded weight grid (more granular around v1 winner [0.15, 0.25, 0.25, 0.20, 0.15])
WEIGHT_VARIATIONS = [
    [0.15, 0.25, 0.25, 0.20, 0.15],  # v1 winner
    [0.10, 0.25, 0.30, 0.20, 0.15],  # more resilience
    [0.15, 0.30, 0.25, 0.15, 0.15],  # more contagion
    [0.15, 0.25, 0.25, 0.25, 0.10],  # more fundamental
    [0.15, 0.25, 0.30, 0.15, 0.15],  # resilience++
    [0.10, 0.30, 0.25, 0.20, 0.15],  # contagion++ eco--
    [0.15, 0.20, 0.30, 0.20, 0.15],  # resilience + fundamental
    [0.10, 0.25, 0.25, 0.25, 0.15],  # fundamental++ eco--
    [0.15, 0.25, 0.20, 0.25, 0.15],  # fundamental over resilience
    [0.25, 0.25, 0.20, 0.15, 0.15],  # default
    [0.20, 0.20, 0.30, 0.15, 0.15],  # resilience heavy
    [0.25, 0.30, 0.20, 0.15, 0.10],  # contagion heavy
    [0.20, 0.20, 0.20, 0.20, 0.20],  # equal
    [0.10, 0.30, 0.30, 0.15, 0.15],  # contagion + resilience
    [0.10, 0.20, 0.30, 0.25, 0.15],  # resilience + fundamental heavy
    [0.15, 0.30, 0.20, 0.20, 0.15],  # contagion + fundamental
]

# ─────────────────────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────────────────────
def get_db():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_prices(conn, start, end):
    rows = conn.execute("""
        SELECT token_id, date, close
        FROM crypto_price_history
        WHERE date >= ? AND date <= ?
        ORDER BY token_id, date
    """, (start, end)).fetchall()
    prices = defaultdict(dict)
    for r in rows:
        prices[r["token_id"]][r["date"]] = r["close"]
    return dict(prices)


def load_volumes(conn, start, end):
    rows = conn.execute("""
        SELECT token_id, AVG(volume) as avg_vol, COUNT(*) as days
        FROM crypto_price_history
        WHERE date >= ? AND date <= ?
        GROUP BY token_id
    """, (start, end)).fetchall()
    return {r["token_id"]: {"avg_vol": r["avg_vol"] or 0, "days": r["days"]} for r in rows}


def load_ratings(conn, start_ym, end_ym):
    rows = conn.execute("""
        SELECT token_id, year_month, rating, score,
               pillar_1, pillar_2, pillar_3, pillar_4, pillar_5
        FROM crypto_rating_history
        WHERE year_month >= ? AND year_month <= ?
    """, (start_ym, end_ym)).fetchall()
    ratings = {}
    for r in rows:
        ratings[(r["token_id"], r["year_month"])] = {
            "rating": r["rating"],
            "score": r["score"],
            "pillars": [r["pillar_1"], r["pillar_2"], r["pillar_3"],
                        r["pillar_4"], r["pillar_5"]],
        }
    return ratings


def load_ndd_monthly(conn, start, end):
    rows = conn.execute("""
        SELECT token_id,
               substr(week_date, 1, 7) as ym,
               AVG(ndd) as avg_ndd
        FROM crypto_ndd_history
        WHERE week_date >= ? AND week_date <= ?
        GROUP BY token_id, substr(week_date, 1, 7)
    """, (start, end)).fetchall()
    ndd = {}
    for r in rows:
        ndd[(r["token_id"], r["ym"])] = r["avg_ndd"]
    return ndd


def load_btc_prices(conn, start, end):
    for tid in ["bitcoin", "btc", "BTC", "Bitcoin"]:
        rows = conn.execute("""
            SELECT date, close FROM crypto_price_history
            WHERE token_id = ? AND date >= ? AND date <= ?
            ORDER BY date
        """, (tid, start, end)).fetchall()
        if rows:
            return {r["date"]: r["close"] for r in rows}
    print("WARNING: Could not find BTC price data")
    return {}


# ─────────────────────────────────────────────────────────────
# FILTERING (v2)
# ─────────────────────────────────────────────────────────────
def build_eligible_tokens(volumes, prices, start, end):
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    total_days = (end_dt - start_dt).days

    eligible = set()
    filtered_reasons = defaultdict(int)

    for tid, vol_data in volumes.items():
        if tid.lower() in STABLECOINS:
            filtered_reasons["stablecoin"] += 1
            continue
        if vol_data["avg_vol"] < MIN_AVG_VOLUME:
            filtered_reasons["low_volume"] += 1
            continue
        coverage = vol_data["days"] / max(total_days, 1)
        if coverage < MIN_PRICE_COVERAGE:
            filtered_reasons["low_coverage"] += 1
            continue
        eligible.add(tid)

    return eligible, dict(filtered_reasons)


# ─────────────────────────────────────────────────────────────
# SCORING & PAIR GENERATION
# ─────────────────────────────────────────────────────────────
def composite_score(pillars, weights):
    if not pillars or any(p is None for p in pillars):
        return None
    return sum(p * w for p, w in zip(pillars, weights))


def get_tokens_by_class_month(ratings, year_month, weights, eligible_tokens):
    class_tokens = defaultdict(list)
    for (tid, ym), data in ratings.items():
        if ym != year_month:
            continue
        if tid not in eligible_tokens:
            continue
        cls = RATING_TO_CLASS.get(data["rating"])
        if not cls:
            continue
        score = composite_score(data["pillars"], weights)
        if score is None:
            continue
        class_tokens[cls].append({
            "token_id": tid,
            "rating": data["rating"],
            "score": data["score"],
            "composite": score,
        })
    for cls in class_tokens:
        class_tokens[cls].sort(key=lambda x: x["composite"], reverse=True)
    return dict(class_tokens)


def generate_pairs(class_tokens, ndd_monthly, year_month, min_tokens=4):
    pairs = []
    ndd_filtered = 0

    for cls, tokens in class_tokens.items():
        if len(tokens) < min_tokens:
            continue

        n = len(tokens)
        q1 = max(1, n // 4)

        longs = tokens[:q1]
        short_candidates = tokens[-q1:]

        shorts = []
        for s in short_candidates:
            ndd_val = ndd_monthly.get((s["token_id"], year_month))
            if ndd_val is not None and ndd_val < MIN_NDD_FOR_SHORT:
                ndd_filtered += 1
                continue
            shorts.append(s)

        for l_tok in longs:
            for s_tok in shorts:
                if l_tok["token_id"] != s_tok["token_id"]:
                    pairs.append({
                        "long": l_tok["token_id"],
                        "short": s_tok["token_id"],
                        "class": cls,
                        "long_composite": l_tok["composite"],
                        "short_composite": s_tok["composite"],
                        "spread": l_tok["composite"] - s_tok["composite"],
                    })

    return pairs, ndd_filtered


def get_closest_date(dates_set, target_date_str, max_offset=7):
    target = datetime.strptime(target_date_str, "%Y-%m-%d")
    for offset in range(max_offset + 1):
        for delta in [offset, -offset]:
            candidate = (target + timedelta(days=delta)).strftime("%Y-%m-%d")
            if candidate in dates_set:
                return candidate
    return None


# ─────────────────────────────────────────────────────────────
# BACKTEST ENGINE
# ─────────────────────────────────────────────────────────────
def compute_pair_return(prices, long_id, short_id, entry_date, hold_days=HOLD_DAYS):
    exit_date_dt = datetime.strptime(entry_date, "%Y-%m-%d") + timedelta(days=hold_days)
    exit_date = exit_date_dt.strftime("%Y-%m-%d")

    long_prices = prices.get(long_id, {})
    short_prices = prices.get(short_id, {})
    if not long_prices or not short_prices:
        return None

    long_dates = set(long_prices.keys())
    short_dates = set(short_prices.keys())

    entry_long_date = get_closest_date(long_dates, entry_date)
    entry_short_date = get_closest_date(short_dates, entry_date)
    exit_long_date = get_closest_date(long_dates, exit_date)
    exit_short_date = get_closest_date(short_dates, exit_date)

    if not all([entry_long_date, entry_short_date, exit_long_date, exit_short_date]):
        return None

    entry_long = long_prices[entry_long_date]
    exit_long = long_prices[exit_long_date]
    entry_short = short_prices[entry_short_date]
    exit_short = short_prices[exit_short_date]

    if entry_long <= 0 or entry_short <= 0:
        return None

    long_ret = (exit_long - entry_long) / entry_long
    short_ret = (exit_short - entry_short) / entry_short

    # WINSORIZE
    long_ret = max(-MAX_RETURN_CAP, min(MAX_RETURN_CAP, long_ret))
    short_ret = max(-MAX_RETURN_CAP, min(MAX_RETURN_CAP, short_ret))

    pair_alpha = long_ret - short_ret

    return {
        "long_return": long_ret,
        "short_return": short_ret,
        "pair_alpha": pair_alpha,
        "hit": 1 if pair_alpha > 0 else 0,
        "entry_date": entry_date,
        "exit_date": exit_date,
    }


def run_backtest(prices, ratings, ndd_monthly, weights, eligible, start_date, end_date):
    results = []
    total_ndd_filtered = 0
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    while current <= end:
        year_month = current.strftime("%Y-%m")
        entry_date = current.strftime("%Y-%m-%d")

        exit_dt = current + timedelta(days=HOLD_DAYS)
        if exit_dt > datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=HOLD_DAYS):
            break

        class_tokens = get_tokens_by_class_month(ratings, year_month, weights, eligible)
        pairs, ndd_filt = generate_pairs(class_tokens, ndd_monthly, year_month)
        total_ndd_filtered += ndd_filt

        for pair in pairs:
            ret = compute_pair_return(prices, pair["long"], pair["short"], entry_date)
            if ret:
                ret["long_id"] = pair["long"]
                ret["short_id"] = pair["short"]
                ret["class"] = pair["class"]
                ret["spread"] = pair["spread"]
                results.append(ret)

        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)

    return results, total_ndd_filtered


def compute_metrics(results, btc_prices=None, start_date=None, end_date=None):
    if not results:
        return {
            "total_pairs": 0, "hit_rate": 0, "avg_alpha": 0,
            "median_alpha": 0, "sharpe": 0, "max_drawdown": 0, "btc_sharpe": 0,
        }

    hits = sum(1 for r in results if r["hit"])
    alphas = [r["pair_alpha"] for r in results]

    hit_rate = hits / len(results) * 100
    avg_alpha = np.mean(alphas) * 100
    median_alpha = np.median(alphas) * 100
    std_alpha = np.std(alphas) if len(alphas) > 1 else 1.0

    sharpe = (np.mean(alphas) / std_alpha) * np.sqrt(4) if std_alpha > 0 else 0

    cum_alpha = np.cumsum(alphas)
    running_max = np.maximum.accumulate(cum_alpha)
    drawdowns = cum_alpha - running_max
    max_dd = abs(np.min(drawdowns)) * 100 if len(drawdowns) > 0 else 0

    btc_sharpe = 0
    if btc_prices and len(btc_prices) > 90:
        btc_sorted = sorted(btc_prices.items())
        btc_rets = []
        for i in range(0, len(btc_sorted) - 90, 30):
            p0 = btc_sorted[i][1]
            p1 = btc_sorted[min(i + 90, len(btc_sorted) - 1)][1]
            if p0 > 0:
                btc_rets.append((p1 - p0) / p0)
        if btc_rets and np.std(btc_rets) > 0:
            btc_sharpe = (np.mean(btc_rets) / np.std(btc_rets)) * np.sqrt(4)

    class_hits = defaultdict(lambda: {"hits": 0, "total": 0, "alphas": []})
    for r in results:
        cls = r.get("class", "?")
        class_hits[cls]["total"] += 1
        class_hits[cls]["hits"] += r["hit"]
        class_hits[cls]["alphas"].append(r["pair_alpha"])

    class_breakdown = {}
    for cls, d in class_hits.items():
        class_breakdown[cls] = {
            "pairs": d["total"],
            "hit_rate": d["hits"] / d["total"] * 100 if d["total"] > 0 else 0,
            "avg_alpha": np.mean(d["alphas"]) * 100 if d["alphas"] else 0,
            "median_alpha": np.median(d["alphas"]) * 100 if d["alphas"] else 0,
        }

    return {
        "total_pairs": len(results),
        "hit_rate": round(hit_rate, 2),
        "avg_alpha": round(avg_alpha, 4),
        "median_alpha": round(median_alpha, 4),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "btc_sharpe": round(btc_sharpe, 4),
        "class_breakdown": class_breakdown,
    }


# ─────────────────────────────────────────────────────────────
# WEIGHT OPTIMIZATION
# ─────────────────────────────────────────────────────────────
def optimize_weights(prices, ratings, ndd_monthly, eligible, btc_prices):
    print("\n" + "=" * 70)
    print("PHASE 1: IN-SAMPLE WEIGHT OPTIMIZATION (2021-2023)")
    print(f"  Filters: winsorize ±{MAX_RETURN_CAP*100:.0f}%, min_vol ${MIN_AVG_VOLUME:,}, "
          f"NDD short ≥{MIN_NDD_FOR_SHORT}, {len(STABLECOINS)} stablecoins excluded")
    print("=" * 70)

    best_weights = None
    best_score = -999
    best_metrics = None

    for i, weights in enumerate(WEIGHT_VARIATIONS):
        w_str = " | ".join(f"{w:.2f}" for w in weights)
        results, ndd_filt = run_backtest(prices, ratings, ndd_monthly, weights,
                                          eligible, IN_SAMPLE_START, IN_SAMPLE_END)
        metrics = compute_metrics(results, btc_prices, IN_SAMPLE_START, IN_SAMPLE_END)

        if metrics["total_pairs"] == 0:
            print(f"  [{i+1:2d}/{len(WEIGHT_VARIATIONS)}] [{w_str}] → No pairs")
            continue

        hr_bonus = max(0, metrics["hit_rate"] - 50) * 2
        alpha_bonus = metrics["avg_alpha"] * 5
        median_bonus = metrics["median_alpha"] * 5
        sharpe_bonus = max(0, metrics["sharpe"]) * 10

        score = hr_bonus + alpha_bonus + median_bonus + sharpe_bonus

        print(f"  [{i+1:2d}/{len(WEIGHT_VARIATIONS)}] [{w_str}] → "
              f"P:{metrics['total_pairs']:>5}, HR:{metrics['hit_rate']:>5.1f}%, "
              f"α:{metrics['avg_alpha']:>7.2f}%, med:{metrics['median_alpha']:>7.2f}%, "
              f"S:{metrics['sharpe']:>5.2f}, NDD_filt:{ndd_filt:>3} → score:{score:>7.1f}")

        if score > best_score:
            best_score = score
            best_weights = weights
            best_metrics = metrics

    if not best_weights:
        print("\n  ERROR: No valid weights found! Using default.")
        best_weights = DEFAULT_WEIGHTS
        best_metrics = {"total_pairs": 0, "hit_rate": 0, "avg_alpha": 0,
                        "median_alpha": 0, "sharpe": 0, "max_drawdown": 0}

    print(f"\n  {'─' * 60}")
    print(f"  BEST WEIGHTS: [{' | '.join(f'{w:.2f}' for w in best_weights)}]")
    print(f"  Hit Rate: {best_metrics['hit_rate']:.1f}% | "
          f"Alpha: {best_metrics['avg_alpha']:.2f}% | "
          f"Median: {best_metrics.get('median_alpha', 0):.2f}% | "
          f"Sharpe: {best_metrics['sharpe']:.2f} | "
          f"MaxDD: {best_metrics.get('max_drawdown', 0):.2f}%")
    print(f"  {'─' * 60}")

    return best_weights, best_metrics


def validate_oos(prices, ratings, ndd_monthly, weights, eligible, btc_prices):
    print("\n" + "=" * 70)
    print("PHASE 2: OUT-OF-SAMPLE VALIDATION (2024-2025) — FROZEN WEIGHTS")
    print(f"  Weights: [{' | '.join(f'{w:.2f}' for w in weights)}]")
    print("=" * 70)

    results, ndd_filt = run_backtest(prices, ratings, ndd_monthly, weights,
                                      eligible, OUT_SAMPLE_START, OUT_SAMPLE_END)
    metrics = compute_metrics(results, btc_prices, OUT_SAMPLE_START, OUT_SAMPLE_END)
    print(f"  NDD-filtered shorts: {ndd_filt}")
    return results, metrics


def evaluate_success(is_m, oos_m):
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    print(f"\n  {'Metric':<25} {'In-Sample':>15} {'Out-of-Sample':>15} {'Target':>15}")
    print(f"  {'─' * 70}")
    print(f"  {'Total Pairs':<25} {is_m['total_pairs']:>15} {oos_m['total_pairs']:>15} {'—':>15}")
    print(f"  {'Hit Rate':<25} {is_m['hit_rate']:>14.1f}% {oos_m['hit_rate']:>14.1f}% {'>58%':>15}")
    print(f"  {'Avg Alpha (90d)':<25} {is_m['avg_alpha']:>14.2f}% {oos_m['avg_alpha']:>14.2f}% {'>0%':>15}")
    print(f"  {'Median Alpha (90d)':<25} {is_m.get('median_alpha',0):>14.2f}% {oos_m.get('median_alpha',0):>14.2f}% {'—':>15}")
    print(f"  {'Sharpe':<25} {is_m['sharpe']:>15.2f} {oos_m['sharpe']:>15.2f} {'>BTC':>15}")
    print(f"  {'BTC Sharpe':<25} {'—':>15} {oos_m['btc_sharpe']:>15.2f} {'—':>15}")
    print(f"  {'Max Drawdown':<25} {is_m.get('max_drawdown',0):>14.2f}% {oos_m.get('max_drawdown',0):>14.2f}% {'—':>15}")

    if oos_m.get("class_breakdown"):
        print(f"\n  OOS BY RATING CLASS:")
        print(f"  {'Class':<12} {'Pairs':>8} {'Hit Rate':>10} {'Avg α':>10} {'Med α':>10}")
        print(f"  {'─' * 52}")
        for cls in sorted(oos_m["class_breakdown"].keys()):
            bd = oos_m["class_breakdown"][cls]
            print(f"  {cls:<12} {bd['pairs']:>8} {bd['hit_rate']:>9.1f}% "
                  f"{bd['avg_alpha']:>9.2f}% {bd.get('median_alpha',0):>9.2f}%")

    print(f"\n  {'─' * 70}")
    hit_ok = oos_m["hit_rate"] > 58
    alpha_ok = oos_m["avg_alpha"] > 0
    sharpe_ok = oos_m["sharpe"] > oos_m["btc_sharpe"]

    for name, ok, val in [
        ("Hit Rate > 58%", hit_ok, f"{oos_m['hit_rate']:.1f}%"),
        ("Alpha > 0%", alpha_ok, f"{oos_m['avg_alpha']:.2f}%"),
        ("Sharpe > BTC", sharpe_ok, f"{oos_m['sharpe']:.2f} vs {oos_m['btc_sharpe']:.2f}"),
    ]:
        print(f"  {'✅ PASS' if ok else '❌ FAIL'}  {name}: {val}")

    med_ok = oos_m.get("median_alpha", 0) > 0
    print(f"  {'✅ INFO' if med_ok else '⚠️ INFO'}  Median Alpha > 0%: "
          f"{oos_m.get('median_alpha', 0):.2f}% (robust measure)")

    all_pass = hit_ok and alpha_ok and sharpe_ok
    print(f"\n  {'═' * 70}")
    if all_pass:
        print("  🎯 SUCCESS — All criteria passed!")
    else:
        print("  ⚠️  NOT ALL CRITERIA MET — Analyze and iterate per GO/NO-GO")
        if med_ok and hit_ok:
            print("  💡 NOTE: Median alpha positive + hit rate passes → "
                  "signal works, outliers drag mean down")
    print(f"  {'═' * 70}")
    return all_pass


def report_top_pairs(results, n=15):
    if not results:
        return
    s = sorted(results, key=lambda r: r["pair_alpha"], reverse=True)
    print(f"\n  TOP {n} PAIRS:")
    print(f"  {'Long':<20} {'Short':<20} {'Class':<10} {'Alpha':>10} {'Entry':>12}")
    print(f"  {'─' * 74}")
    for r in s[:n]:
        print(f"  {r['long_id']:<20} {r['short_id']:<20} {r.get('class',''):<10} "
              f"{r['pair_alpha']*100:>9.1f}% {r['entry_date']:>12}")
    print(f"\n  BOTTOM 5:")
    print(f"  {'─' * 74}")
    for r in s[-5:]:
        print(f"  {r['long_id']:<20} {r['short_id']:<20} {r.get('class',''):<10} "
              f"{r['pair_alpha']*100:>9.1f}% {r['entry_date']:>12}")


def save_results(conn, weights, is_m, oos_m, oos_results, passed):
    script_dir = os.path.dirname(os.path.abspath(__file__))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_pairs_backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT, version TEXT, weights TEXT,
            in_sample_hit_rate REAL, in_sample_alpha REAL, in_sample_sharpe REAL,
            oos_hit_rate REAL, oos_alpha REAL, oos_median_alpha REAL,
            oos_sharpe REAL, oos_btc_sharpe REAL, oos_max_drawdown REAL,
            oos_total_pairs INTEGER, passed INTEGER,
            filters TEXT, class_breakdown TEXT, all_pairs_json TEXT
        )
    """)

    filters_json = json.dumps({
        "winsorize_cap": MAX_RETURN_CAP,
        "min_avg_volume": MIN_AVG_VOLUME,
        "min_price_coverage": MIN_PRICE_COVERAGE,
        "min_ndd_for_short": MIN_NDD_FOR_SHORT,
        "stablecoins_excluded": len(STABLECOINS),
    })

    conn.execute("""
        INSERT INTO crypto_pairs_backtest_results
        (run_date, version, weights, in_sample_hit_rate, in_sample_alpha,
         in_sample_sharpe, oos_hit_rate, oos_alpha, oos_median_alpha,
         oos_sharpe, oos_btc_sharpe, oos_max_drawdown, oos_total_pairs,
         passed, filters, class_breakdown, all_pairs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(), "v2",
        json.dumps(weights),
        is_m["hit_rate"], is_m["avg_alpha"], is_m["sharpe"],
        oos_m["hit_rate"], oos_m["avg_alpha"], oos_m.get("median_alpha", 0),
        oos_m["sharpe"], oos_m["btc_sharpe"], oos_m.get("max_drawdown", 0),
        oos_m["total_pairs"], 1 if passed else 0,
        filters_json,
        json.dumps(oos_m.get("class_breakdown", {})),
        json.dumps([{
            "long": r["long_id"], "short": r["short_id"],
            "class": r.get("class", ""), "alpha": round(r["pair_alpha"], 6),
            "entry": r["entry_date"], "exit": r["exit_date"],
        } for r in oos_results]) if oos_results else "[]"
    ))
    conn.commit()

    status = "PASSED" if passed else "DID NOT PASS ALL CRITERIA"
    md = f"""# NERQ Pairs Portfolio Backtest Results (v2)
## Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}

### Status: {status}

### v2 Filters Applied
- Winsorized returns at +/-{MAX_RETURN_CAP*100:.0f}% per leg
- {len(STABLECOINS)} stablecoins excluded
- Min avg daily volume >= ${MIN_AVG_VOLUME:,}
- NDD filter: no shorting tokens with NDD < {MIN_NDD_FOR_SHORT}
- Price coverage >= {MIN_PRICE_COVERAGE*100:.0f}%

### Optimized Pillar Weights
| Pillar | Weight |
|--------|--------|
| Ecosystem Strength | {weights[0]:.0%} |
| Contagion Risk | {weights[1]:.0%} |
| Historical Resilience | {weights[2]:.0%} |
| Fundamental Quality | {weights[3]:.0%} |
| Rug Pull Risk | {weights[4]:.0%} |

### Results
| Metric | In-Sample | Out-of-Sample | Target |
|--------|-----------|---------------|--------|
| Pairs | {is_m['total_pairs']} | {oos_m['total_pairs']} | - |
| Hit Rate | {is_m['hit_rate']:.1f}% | {oos_m['hit_rate']:.1f}% | >58% |
| Avg Alpha | {is_m['avg_alpha']:.2f}% | {oos_m['avg_alpha']:.2f}% | >0% |
| Median Alpha | {is_m.get('median_alpha',0):.2f}% | {oos_m.get('median_alpha',0):.2f}% | - |
| Sharpe | {is_m['sharpe']:.2f} | {oos_m['sharpe']:.2f} | >{oos_m['btc_sharpe']:.2f} (BTC) |
| Max Drawdown | {is_m.get('max_drawdown',0):.2f}% | {oos_m.get('max_drawdown',0):.2f}% | - |

### OOS Class Breakdown
| Class | Pairs | Hit Rate | Avg Alpha | Median Alpha |
|-------|-------|----------|-----------|--------------|
"""
    if oos_m.get("class_breakdown"):
        for cls in sorted(oos_m["class_breakdown"].keys()):
            bd = oos_m["class_breakdown"][cls]
            md += (f"| {cls} | {bd['pairs']} | {bd['hit_rate']:.1f}% | "
                   f"{bd['avg_alpha']:.2f}% | {bd.get('median_alpha',0):.2f}% |\n")

    md += f"""
### Methodology
- Long/short pairs within same rating class (quartile selection)
- Hold: {HOLD_DAYS}d, monthly rebalance
- IS: {IN_SAMPLE_START} to {IN_SAMPLE_END}, OOS: {OUT_SAMPLE_START} to {OUT_SAMPLE_END}
"""
    path = os.path.join(script_dir, "PAIRS_BACKTEST_RESULTS.md")
    with open(path, "w") as f:
        f.write(md)
    print(f"\n  Report: {path}")
    print(f"  DB: crypto_pairs_backtest_results (version=v2)")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("NERQ CRYPTO — PAIRS PORTFOLIO BACKTEST v2")
    print(f"Database: {DB_PATH}")
    print(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    conn = get_db()

    for tbl, label in [("crypto_price_history", "Price"),
                        ("crypto_rating_history", "Rating"),
                        ("crypto_ndd_history", "NDD")]:
        row = conn.execute(f"SELECT COUNT(*) as c FROM {tbl}").fetchone()
        print(f"  {label} rows: {row['c']:,}")

    print("\n  Building eligible token sets...")
    is_volumes = load_volumes(conn, IN_SAMPLE_START, IN_SAMPLE_END)
    is_prices = load_prices(conn, IN_SAMPLE_START, IN_SAMPLE_END)
    is_eligible, is_filtered = build_eligible_tokens(
        is_volumes, is_prices, IN_SAMPLE_START, IN_SAMPLE_END)
    print(f"    In-sample: {len(is_eligible)} eligible")
    for r, c in sorted(is_filtered.items()):
        print(f"      Filtered ({r}): {c}")

    oos_volumes = load_volumes(conn, OUT_SAMPLE_START, OUT_SAMPLE_END)
    oos_prices = load_prices(conn, OUT_SAMPLE_START, OUT_SAMPLE_END)
    oos_eligible, oos_filtered = build_eligible_tokens(
        oos_volumes, oos_prices, OUT_SAMPLE_START, OUT_SAMPLE_END)
    print(f"    Out-of-sample: {len(oos_eligible)} eligible")
    for r, c in sorted(oos_filtered.items()):
        print(f"      Filtered ({r}): {c}")

    print("\n  Loading data...")
    is_ratings = load_ratings(conn, "2021-01", "2023-12")
    oos_ratings = load_ratings(conn, "2024-01", "2025-12")
    is_ndd = load_ndd_monthly(conn, IN_SAMPLE_START, IN_SAMPLE_END)
    oos_ndd = load_ndd_monthly(conn, OUT_SAMPLE_START, OUT_SAMPLE_END)
    btc_is = load_btc_prices(conn, IN_SAMPLE_START, IN_SAMPLE_END)
    btc_oos = load_btc_prices(conn, OUT_SAMPLE_START, OUT_SAMPLE_END)
    print(f"    IS ratings: {len(is_ratings):,}, OOS: {len(oos_ratings):,}")
    print(f"    IS NDD: {len(is_ndd):,}, OOS: {len(oos_ndd):,}")
    print(f"    BTC: IS={len(btc_is)}, OOS={len(btc_oos)} days")

    best_weights, is_metrics = optimize_weights(
        is_prices, is_ratings, is_ndd, is_eligible, btc_is)

    oos_results, oos_metrics = validate_oos(
        oos_prices, oos_ratings, oos_ndd, best_weights, oos_eligible, btc_oos)

    passed = evaluate_success(is_metrics, oos_metrics)
    report_top_pairs(oos_results)
    save_results(conn, best_weights, is_metrics, oos_metrics, oos_results, passed)

    conn.close()
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
