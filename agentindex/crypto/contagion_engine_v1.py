#!/usr/bin/env python3
"""
NERQ CONTAGION ENGINE v1.0
============================
"Your token is at risk because of what's happening elsewhere."

Three integrated modules:
  1. CASCADE CLOCK — Where on the risk curve is stress right now?
     Splits market into quintiles by market cap, measures stress per layer.
     Detects when micro-cap stress is spreading inward.

  2. CONTAGION NETWORK — Which tokens infect which?
     30-day rolling correlation matrix for top tokens.
     Identifies clusters of co-moving tokens.
     When tokens in your cluster fall, you're next.

  3. PROPAGATED RISK SCORE — Everything combined per token.
     Internal health (vol, drawdown, momentum) ×
     External stress (BTC vol, cascade position) ×
     Network exposure (how many neighbors are falling) =
     Single 0-100 risk score with explanation.

Data: crypto_price_history (5,916 tokens, 2017-2026)
Method: IS (2021-2023) calibration, OOS (2024-2026) validation
Output: Risk scores + NDD v4 + validation metrics

PERFORMANCE NOTE: This script processes thousands of tokens.
To keep runtime manageable (<15 min), we:
  - Use top 500 tokens by market cap for correlation network
  - Compute cascade across all tokens but sample weekly
  - Use efficient numpy operations where possible
"""

import sqlite3
import os
import sys
import json
import numpy as np
from datetime import datetime, timedelta
from math import sqrt, log, exp
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")
IS_CUTOFF = "2023-12-31"
OOS_START = "2024-01-01"
CRASH_THRESHOLD = -0.30
CRASH_WINDOW_DAYS = 90

# How many top tokens to include in correlation network
NETWORK_TOP_N = 500
# Rolling correlation window (days)
CORR_WINDOW = 30
# Minimum correlation to count as "connected"
CORR_THRESHOLD = 0.50
# Sample interval for weekly snapshots
SAMPLE_INTERVAL_DAYS = 7


def wilson_ci(s, n, z=1.96):
    if n == 0: return 0, 0, 0
    p = s / n
    d = 1 + z**2/n
    c = (p + z**2/(2*n)) / d
    sp = z * sqrt((p*(1-p) + z**2/(4*n)) / n) / d
    return p, max(0, c-sp), min(1, c+sp)


def compute_auc(scores, labels):
    pos = [s for s, l in zip(scores, labels) if l == 1]
    neg = [s for s, l in zip(scores, labels) if l == 0]
    if not pos or not neg: return 0.5
    pos.sort(); neg.sort()
    j = 0; conc = 0
    for ps in pos:
        while j < len(neg) and neg[j] < ps:
            j += 1
        conc += j
    return conc / (len(pos) * len(neg)) if (len(pos) * len(neg)) > 0 else 0.5


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_price_data(conn):
    """Load price history into numpy-friendly format."""
    print("  Loading price history...")
    rows = conn.execute("""
        SELECT token_id, date, close, volume, market_cap
        FROM crypto_price_history
        WHERE close IS NOT NULL AND close > 0
        ORDER BY token_id, date
    """).fetchall()

    prices = defaultdict(list)
    for tid, d, c, v, m in rows:
        prices[tid].append((d, c, v or 0, m or 0))

    print(f"    {len(prices)} tokens, {len(rows)} rows")
    return dict(prices)


def get_common_dates(prices, min_tokens=50):
    """Find dates where enough tokens have data."""
    date_counts = defaultdict(int)
    for tid, series in prices.items():
        for d, c, v, m in series:
            date_counts[d] += 1

    common = sorted(d for d, cnt in date_counts.items() if cnt >= min_tokens)
    return common


def get_top_tokens_at_date(prices, target_date, top_n=NETWORK_TOP_N):
    """Get top N tokens by market cap at a given date."""
    token_mcaps = []
    for tid, series in prices.items():
        # Binary search for date
        idx = None
        lo, hi = 0, len(series) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if series[mid][0] <= target_date:
                idx = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if idx is not None and series[idx][3] > 0:
            token_mcaps.append((tid, series[idx][3]))

    token_mcaps.sort(key=lambda x: x[1], reverse=True)
    return [t[0] for t in token_mcaps[:top_n]]


def get_price_at_date(series, target_date):
    """Binary search for price at date."""
    lo, hi = 0, len(series) - 1
    result = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if series[mid][0] <= target_date:
            result = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return result


def get_returns(series, idx, days):
    """Get return over N days ending at idx."""
    if idx < days: return None
    p_now = series[idx][1]
    p_past = series[idx - days][1]
    if p_past <= 0: return None
    return (p_now - p_past) / p_past


def get_volatility(series, idx, window=30):
    """Annualized realized volatility."""
    if idx < window: return None
    rets = []
    for i in range(idx - window + 1, idx + 1):
        if i > 0 and series[i-1][1] > 0:
            rets.append((series[i][1] - series[i-1][1]) / series[i-1][1])
    if len(rets) < 20: return None
    m = np.mean(rets)
    v = np.mean([(r-m)**2 for r in rets])
    return sqrt(v) * sqrt(365)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 1: CASCADE CLOCK
# ══════════════════════════════════════════════════════════════════════════════

def compute_cascade_snapshot(prices, target_date, lookback=7):
    """
    Compute cascade indicators at a given date.
    Splits all tokens into quintiles by market cap.
    Returns cascade features.
    """
    # Get all tokens with data at this date
    token_data = []
    for tid, series in prices.items():
        idx = get_price_at_date(series, target_date)
        if idx is None or idx < lookback:
            continue
        mcap = series[idx][3]
        if mcap <= 0:
            continue

        ret = get_returns(series, idx, lookback)
        if ret is None:
            continue

        token_data.append((tid, mcap, ret))

    if len(token_data) < 50:
        return None

    # Sort by market cap, split into quintiles
    token_data.sort(key=lambda x: x[1])
    n = len(token_data)
    q_size = n // 5

    quintiles = {}
    for q in range(5):
        start = q * q_size
        end = start + q_size if q < 4 else n
        q_tokens = token_data[start:end]
        q_rets = [t[2] for t in q_tokens]
        q_mcaps = [t[1] for t in q_tokens]

        avg_ret = np.mean(q_rets)
        pct_falling_10 = sum(1 for r in q_rets if r < -0.10) / len(q_rets)
        pct_falling_20 = sum(1 for r in q_rets if r < -0.20) / len(q_rets)

        quintiles[q+1] = {
            'avg_ret': avg_ret,
            'pct_falling_10': pct_falling_10,
            'pct_falling_20': pct_falling_20,
            'n_tokens': len(q_tokens),
            'median_mcap': np.median(q_mcaps),
        }

    # CASCADE INDICATORS
    features = {}

    # Q1=micro-cap, Q5=large-cap
    features['cascade_q1_ret'] = quintiles[1]['avg_ret']
    features['cascade_q2_ret'] = quintiles[2]['avg_ret']
    features['cascade_q3_ret'] = quintiles[3]['avg_ret']
    features['cascade_q5_ret'] = quintiles[5]['avg_ret']

    # Spread: micro vs large (negative = micro-caps falling harder)
    features['cascade_spread'] = quintiles[1]['avg_ret'] - quintiles[5]['avg_ret']

    # Cascade depth: how many quintiles are falling?
    falling_quintiles = sum(1 for q in range(1, 6) if quintiles[q]['avg_ret'] < -0.05)
    features['cascade_depth'] = falling_quintiles

    # Cascade progression: stress moving inward?
    # True if Q1 < -10% AND Q2 < -5% AND Q5 > -5%
    if quintiles[1]['avg_ret'] < -0.10 and quintiles[5]['avg_ret'] > -0.05:
        features['cascade_active'] = 1.0
        # How far has it spread? Count from outside in
        spread_depth = 1
        if quintiles[2]['avg_ret'] < -0.07: spread_depth = 2
        if quintiles[3]['avg_ret'] < -0.05: spread_depth = 3
        if quintiles[4]['avg_ret'] < -0.03: spread_depth = 4
        features['cascade_spread_depth'] = spread_depth
    else:
        features['cascade_active'] = 0.0
        features['cascade_spread_depth'] = 0

    # Market breadth
    all_rets = [t[2] for t in token_data]
    features['market_breadth_10'] = sum(1 for r in all_rets if r < -0.10) / len(all_rets)
    features['market_breadth_20'] = sum(1 for r in all_rets if r < -0.20) / len(all_rets)
    features['market_avg_ret'] = np.mean(all_rets)

    # Micro-cap distress intensity
    features['q1_pct_falling_20'] = quintiles[1]['pct_falling_20']

    return features, quintiles


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 2: CONTAGION NETWORK
# ══════════════════════════════════════════════════════════════════════════════

def build_return_matrix(prices, tokens, target_date, window=CORR_WINDOW):
    """
    Build a (window × n_tokens) return matrix for correlation computation.
    """
    n = len(tokens)
    mat = np.full((window, n), np.nan)

    for j, tid in enumerate(tokens):
        if tid not in prices:
            continue
        series = prices[tid]
        idx = get_price_at_date(series, target_date)
        if idx is None or idx < window:
            continue

        for i in range(window):
            day_idx = idx - window + 1 + i
            if day_idx > 0 and series[day_idx-1][1] > 0:
                mat[i, j] = (series[day_idx][1] - series[day_idx-1][1]) / series[day_idx-1][1]

    return mat


def compute_correlation_network(return_matrix, tokens, threshold=CORR_THRESHOLD):
    """
    Compute correlation matrix and extract network features.
    Returns: adjacency info, cluster assignments, per-token network metrics.
    """
    n = len(tokens)

    # Handle NaN: fill with 0 for tokens with missing data
    mat = np.nan_to_num(return_matrix, nan=0.0)

    # Compute correlation matrix using numpy
    # Standardize columns
    means = mat.mean(axis=0, keepdims=True)
    stds = mat.std(axis=0, keepdims=True)
    stds[stds < 1e-10] = 1.0
    standardized = (mat - means) / stds

    corr = (standardized.T @ standardized) / mat.shape[0]
    np.fill_diagonal(corr, 0)  # no self-correlation

    # Network metrics per token
    network = {}
    for i, tid in enumerate(tokens):
        # Number of strong connections
        connections = np.sum(np.abs(corr[i, :]) > threshold)

        # Average correlation with connected tokens
        strong = np.where(np.abs(corr[i, :]) > threshold)[0]
        avg_corr = np.mean(corr[i, strong]) if len(strong) > 0 else 0

        # "Neighbor stress": average recent return of strongly correlated tokens
        # (computed later when we have returns)

        network[tid] = {
            'n_connections': int(connections),
            'avg_correlation': float(avg_corr),
            'max_correlation': float(np.max(corr[i, :])) if n > 1 else 0,
            'corr_row': corr[i, :],
        }

    # Simple clustering: tokens with mutual correlation > threshold
    # Use greedy approach for speed
    clusters = {}
    assigned = set()
    cluster_id = 0

    for i in range(n):
        if tokens[i] in assigned:
            continue
        # Find all tokens correlated with i
        members = [i]
        for j in range(i+1, n):
            if tokens[j] in assigned:
                continue
            if corr[i, j] > threshold:
                members.append(j)

        if len(members) >= 2:
            for m in members:
                clusters[tokens[m]] = cluster_id
                assigned.add(tokens[m])
            cluster_id += 1
        else:
            clusters[tokens[i]] = -1  # no cluster
            assigned.add(tokens[i])

    return network, clusters, corr


def compute_neighbor_stress(prices, tokens, network, corr_matrix, target_date, lookback=7):
    """
    For each token, compute how much its correlated neighbors are falling.
    This is the "contagion pressure" on the token.
    """
    n = len(tokens)

    # Get returns for all tokens
    returns = {}
    for tid in tokens:
        if tid not in prices:
            continue
        series = prices[tid]
        idx = get_price_at_date(series, target_date)
        if idx is not None:
            ret = get_returns(series, idx, lookback)
            if ret is not None:
                returns[tid] = ret

    # For each token: weighted average return of correlated neighbors
    for i, tid in enumerate(tokens):
        if tid not in network:
            continue

        neighbor_rets = []
        neighbor_weights = []

        for j, other_tid in enumerate(tokens):
            if i == j or other_tid not in returns:
                continue
            corr_val = corr_matrix[i, j]
            if corr_val > CORR_THRESHOLD:
                neighbor_rets.append(returns[other_tid])
                neighbor_weights.append(corr_val)

        if neighbor_rets:
            weights = np.array(neighbor_weights)
            rets = np.array(neighbor_rets)
            weighted_ret = np.average(rets, weights=weights)
            pct_falling = sum(1 for r in neighbor_rets if r < -0.10) / len(neighbor_rets)

            network[tid]['neighbor_avg_ret'] = float(weighted_ret)
            network[tid]['neighbor_pct_falling'] = float(pct_falling)
            network[tid]['n_neighbors_falling'] = sum(1 for r in neighbor_rets if r < -0.10)
        else:
            network[tid]['neighbor_avg_ret'] = 0.0
            network[tid]['neighbor_pct_falling'] = 0.0
            network[tid]['n_neighbors_falling'] = 0

    return network


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 3: PROPAGATED RISK SCORE
# ══════════════════════════════════════════════════════════════════════════════

def compute_propagated_risk(prices, tid, target_date, cascade_features, network_info, btc_vol):
    """
    Compute the final Propagated Risk Score (0-100) for a token.
    Combines internal health, external stress, and network exposure.

    Returns: (score, explanation_dict) or None
    """
    if tid not in prices:
        return None

    series = prices[tid]
    idx = get_price_at_date(series, target_date)
    if idx is None or idx < 90:
        return None

    close = series[idx][1]
    mcap = series[idx][3]

    # ── INTERNAL HEALTH (0-40 points) ───────────────────────────────────────
    internal = 0
    explanation = {}

    # Volatility (0-15)
    vol = get_volatility(series, idx, 30)
    if vol is not None:
        vol_score = min(15, vol * 8)  # vol=1.0 → 8pts, vol=2.0 → 15pts cap
        internal += vol_score
        explanation['volatility_30d'] = round(vol, 3)
    else:
        vol_score = 7.5  # neutral
        internal += vol_score

    # Drawdown from 90d high (0-12)
    high_90d = max(series[i][1] for i in range(max(0, idx-89), idx+1))
    dd = (close - high_90d) / high_90d if high_90d > 0 else 0
    dd_score = min(12, abs(dd) * 20)  # dd=-30% → 6pts, dd=-60% → 12pts cap
    internal += dd_score
    explanation['drawdown_90d'] = round(dd, 3)

    # Momentum — falling fast (0-8)
    ret_7d = get_returns(series, idx, 7)
    ret_30d = get_returns(series, idx, 30)
    mom_score = 0
    if ret_7d is not None and ret_7d < -0.05:
        mom_score += min(4, abs(ret_7d) * 20)
    if ret_30d is not None and ret_30d < -0.10:
        mom_score += min(4, abs(ret_30d) * 10)
    internal += mom_score
    explanation['ret_7d'] = round(ret_7d, 4) if ret_7d else 0
    explanation['ret_30d'] = round(ret_30d, 4) if ret_30d else 0

    # Market cap size penalty (0-5) — smaller = riskier
    if mcap > 0:
        mcap_score = max(0, 5 - log(max(mcap, 1)) / log(10) * 0.5)
        internal += min(5, mcap_score)
        explanation['mcap'] = mcap

    # ── EXTERNAL STRESS (0-30 points) ───────────────────────────────────────
    external = 0

    # BTC volatility (0-10)
    if btc_vol is not None:
        btc_score = min(10, btc_vol * 12)  # vol=0.5 → 6, vol=0.8 → 10 cap
        external += btc_score
        explanation['btc_vol_30d'] = round(btc_vol, 3)

    # Cascade indicators (0-12)
    if cascade_features:
        # Cascade active? Big signal.
        if cascade_features.get('cascade_active', 0) > 0:
            cascade_score = 6 + cascade_features.get('cascade_spread_depth', 0) * 1.5
            external += min(12, cascade_score)
            explanation['cascade_active'] = True
            explanation['cascade_depth'] = cascade_features.get('cascade_spread_depth', 0)
        else:
            # Market breadth stress
            breadth = cascade_features.get('market_breadth_20', 0)
            external += min(8, breadth * 40)  # 20% falling >20% → 8pts
            explanation['cascade_active'] = False

        explanation['market_breadth_20'] = round(cascade_features.get('market_breadth_20', 0), 3)
        explanation['cascade_spread'] = round(cascade_features.get('cascade_spread', 0), 3)

    # Market regime (0-8)
    if cascade_features:
        mkt_ret = cascade_features.get('market_avg_ret', 0)
        if mkt_ret < -0.05:
            regime_score = min(8, abs(mkt_ret) * 40)
            external += regime_score
        explanation['market_avg_ret'] = round(mkt_ret, 4)

    # ── NETWORK EXPOSURE (0-30 points) ──────────────────────────────────────
    network = 0

    if network_info and tid in network_info:
        info = network_info[tid]

        # Neighbors falling (0-15)
        neighbor_pct = info.get('neighbor_pct_falling', 0)
        network += min(15, neighbor_pct * 30)  # 50% of neighbors falling → 15pts
        explanation['neighbor_pct_falling'] = round(neighbor_pct, 3)

        # Neighbor average return (0-10)
        neighbor_ret = info.get('neighbor_avg_ret', 0)
        if neighbor_ret < -0.05:
            network += min(10, abs(neighbor_ret) * 50)
        explanation['neighbor_avg_ret'] = round(neighbor_ret, 4)

        # Number of connections (exposure breadth) (0-5)
        n_conn = info.get('n_connections', 0)
        conn_score = min(5, n_conn / 20 * 5)  # 20+ connections → 5pts
        network += conn_score
        explanation['n_connections'] = n_conn
    else:
        # Token not in network — assign moderate network risk
        network = 10  # unknown = moderate
        explanation['in_network'] = False

    # ── TOTAL ───────────────────────────────────────────────────────────────
    total = min(100, internal + external + network)

    # Risk level
    if total >= 70: level = "CRITICAL"
    elif total >= 55: level = "HIGH"
    elif total >= 40: level = "ELEVATED"
    elif total >= 25: level = "MODERATE"
    else: level = "LOW"

    # NDD v4 equivalent (invert: 100→1.0, 0→5.0)
    ndd_v4 = max(1.0, min(5.0, 5.0 - (total / 100) * 4.0))

    explanation['internal_score'] = round(internal, 1)
    explanation['external_score'] = round(external, 1)
    explanation['network_score'] = round(network, 1)
    explanation['total_score'] = round(total, 1)
    explanation['risk_level'] = level
    explanation['ndd_v4'] = round(ndd_v4, 2)

    return total, explanation


# ══════════════════════════════════════════════════════════════════════════════
# EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def check_crash(prices, tid, target_date):
    if tid not in prices: return None
    series = prices[tid]
    idx = get_price_at_date(series, target_date)
    if idx is None: return None
    start = series[idx][1]
    if start <= 0: return None
    end_d = (datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=CRASH_WINDOW_DAYS)).strftime("%Y-%m-%d")
    max_drop = 0.0
    for i in range(idx+1, len(series)):
        if series[i][0] > end_d: break
        d = (series[i][1] - start) / start
        if d < max_drop: max_drop = d
    return 1 if max_drop <= CRASH_THRESHOLD else 0


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("  NERQ CONTAGION ENGINE v1.0")
    print("  Cascade Clock + Contagion Network + Propagated Risk Score")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    prices = load_price_data(conn)
    conn.close()

    # Get dates where we have enough tokens
    all_dates = get_common_dates(prices, min_tokens=100)
    print(f"  {len(all_dates)} dates with 100+ tokens")

    # Sample weekly for performance
    weekly_dates = []
    last_date = None
    for d in all_dates:
        if last_date is None or (datetime.strptime(d, "%Y-%m-%d") - datetime.strptime(last_date, "%Y-%m-%d")).days >= SAMPLE_INTERVAL_DAYS:
            weekly_dates.append(d)
            last_date = d

    # Filter to NDD-comparable range (2021+) for consistency
    weekly_dates = [d for d in weekly_dates if d >= "2021-01-01"]
    print(f"  {len(weekly_dates)} weekly dates (2021+) to process")

    is_dates = [d for d in weekly_dates if d <= IS_CUTOFF]
    oos_dates = [d for d in weekly_dates if d >= OOS_START]
    print(f"  IS: {len(is_dates)} weeks | OOS: {len(oos_dates)} weeks")

    # ── Process each weekly snapshot ────────────────────────────────────────
    all_scores = []  # (token_id, date, risk_score, crashed, explanation)
    cascade_history = []

    total_weeks = len(weekly_dates)
    progress_interval = max(1, total_weeks // 20)

    for week_idx, date in enumerate(weekly_dates):
        if week_idx % progress_interval == 0:
            print(f"\n  Week {week_idx}/{total_weeks}: {date}")

        # Get top tokens at this date
        top_tokens = get_top_tokens_at_date(prices, date, NETWORK_TOP_N)
        if len(top_tokens) < 50:
            continue

        # MODULE 1: Cascade Clock
        cascade_result = compute_cascade_snapshot(prices, date)
        if cascade_result is None:
            continue
        cascade_features, quintiles = cascade_result
        cascade_history.append((date, cascade_features))

        # MODULE 2: Contagion Network
        return_matrix = build_return_matrix(prices, top_tokens, date, CORR_WINDOW)
        network_info, clusters, corr_matrix = compute_correlation_network(
            return_matrix, top_tokens)
        network_info = compute_neighbor_stress(
            prices, top_tokens, network_info, corr_matrix, date)

        # BTC volatility
        btc_vol = get_volatility(prices.get('bitcoin', []),
                                 get_price_at_date(prices.get('bitcoin', []), date) or 0, 30)

        # MODULE 3: Propagated Risk Score for each top token
        for tid in top_tokens:
            result = compute_propagated_risk(
                prices, tid, date, cascade_features, network_info, btc_vol)
            if result is None:
                continue

            score, explanation = result
            crashed = check_crash(prices, tid, date)
            if crashed is None:
                continue

            all_scores.append({
                'token_id': tid,
                'date': date,
                'risk_score': score,
                'crashed': crashed,
                'ndd_v4': explanation.get('ndd_v4', 3.0),
                'risk_level': explanation.get('risk_level', 'UNKNOWN'),
                'internal': explanation.get('internal_score', 0),
                'external': explanation.get('external_score', 0),
                'network': explanation.get('network_score', 0),
                'cascade_active': explanation.get('cascade_active', False),
                'neighbor_pct_falling': explanation.get('neighbor_pct_falling', 0),
            })

    print(f"\n\n  Total scored observations: {len(all_scores)}")

    # ── Split IS/OOS ────────────────────────────────────────────────────────
    is_scores = [s for s in all_scores if s['date'] <= IS_CUTOFF]
    oos_scores = [s for s in all_scores if s['date'] >= OOS_START]

    print(f"  IS: {len(is_scores)} | OOS: {len(oos_scores)}")

    # ── Evaluate ────────────────────────────────────────────────────────────
    for label, scores in [("IN-SAMPLE (2021-2023)", is_scores),
                          ("OUT-OF-SAMPLE (2024-2026)", oos_scores)]:
        if len(scores) < 100:
            print(f"\n  {label}: Too few observations ({len(scores)})")
            continue

        risk_vals = [s['risk_score'] for s in scores]
        crash_vals = [s['crashed'] for s in scores]
        n_crash = sum(crash_vals)
        n_total = len(scores)

        auc = compute_auc(risk_vals, crash_vals)

        print(f"\n  {'═' * 70}")
        print(f"  {label}")
        print(f"  {'═' * 70}")
        print(f"  N={n_total} | Crashes={n_crash} ({n_crash/n_total*100:.1f}%) | AUC={auc:.3f}")

        # Risk buckets
        print(f"\n  RISK BUCKETS:")
        print(f"  {'Level':<12} {'Range':>12} {'N':>7} {'Crashes':>8} {'Rate':>7} {'CI':>15}")
        print(f"  {'─' * 65}")

        for name, lo, hi in [("LOW", 0, 25), ("MODERATE", 25, 40),
                              ("ELEVATED", 40, 55), ("HIGH", 55, 70),
                              ("CRITICAL", 70, 101)]:
            bucket = [s for s in scores if lo <= s['risk_score'] < hi]
            if bucket:
                nc = sum(s['crashed'] for s in bucket)
                rate, ci_lo, ci_hi = wilson_ci(nc, len(bucket))
                print(f"  {name:<12} [{lo:>3}-{hi:>3}) {len(bucket):>7} {nc:>8} {rate:>6.1%} [{ci_lo*100:.0f}-{ci_hi*100:.0f}%]")

        # Precision/recall at thresholds
        print(f"\n  PRECISION/RECALL:")
        print(f"  {'Threshold':>10} {'Flagged':>8} {'TP':>6} {'Prec':>7} {'Recall':>7} {'F1':>6}")
        print(f"  {'─' * 50}")

        best_f1 = 0
        for thresh in [30, 40, 50, 55, 60, 65, 70, 75, 80]:
            tp = sum(1 for s in scores if s['risk_score'] >= thresh and s['crashed'] == 1)
            fp = sum(1 for s in scores if s['risk_score'] >= thresh and s['crashed'] == 0)
            flagged = tp + fp
            prec = tp / flagged if flagged else 0
            rec = tp / n_crash if n_crash else 0
            f1 = 2*prec*rec/(prec+rec) if (prec+rec) else 0
            mk = " ←" if f1 > best_f1 else ""
            if f1 > best_f1: best_f1 = f1
            print(f"  {thresh:>10} {flagged:>8} {tp:>6} {prec:>6.1%} {rec:>6.1%} {f1:>5.3f}{mk}")

        # Component contribution analysis
        print(f"\n  COMPONENT CONTRIBUTION:")
        crashed_obs = [s for s in scores if s['crashed'] == 1]
        safe_obs = [s for s in scores if s['crashed'] == 0]
        for comp in ['internal', 'external', 'network']:
            crash_avg = np.mean([s[comp] for s in crashed_obs]) if crashed_obs else 0
            safe_avg = np.mean([s[comp] for s in safe_obs]) if safe_obs else 0
            print(f"  {comp:<12} crash={crash_avg:.1f}  safe={safe_avg:.1f}  separation={crash_avg-safe_avg:+.1f}")

        # Cascade analysis
        cascade_active_obs = [s for s in scores if s.get('cascade_active')]
        cascade_inactive_obs = [s for s in scores if not s.get('cascade_active')]
        if cascade_active_obs and cascade_inactive_obs:
            ca_crash = sum(s['crashed'] for s in cascade_active_obs) / len(cascade_active_obs)
            ci_crash = sum(s['crashed'] for s in cascade_inactive_obs) / len(cascade_inactive_obs)
            print(f"\n  CASCADE EFFECT:")
            print(f"    Cascade active:   {ca_crash:.1%} crash rate (n={len(cascade_active_obs)})")
            print(f"    Cascade inactive: {ci_crash:.1%} crash rate (n={len(cascade_inactive_obs)})")
            print(f"    Lift: {ca_crash/ci_crash:.2f}x" if ci_crash > 0 else "    Lift: N/A")

        # Network effect
        high_neighbor_stress = [s for s in scores if s.get('neighbor_pct_falling', 0) > 0.3]
        low_neighbor_stress = [s for s in scores if s.get('neighbor_pct_falling', 0) <= 0.1]
        if high_neighbor_stress and low_neighbor_stress:
            hn_crash = sum(s['crashed'] for s in high_neighbor_stress) / len(high_neighbor_stress)
            ln_crash = sum(s['crashed'] for s in low_neighbor_stress) / len(low_neighbor_stress)
            print(f"\n  CONTAGION EFFECT:")
            print(f"    >30% neighbors falling: {hn_crash:.1%} crash rate (n={len(high_neighbor_stress)})")
            print(f"    ≤10% neighbors falling: {ln_crash:.1%} crash rate (n={len(low_neighbor_stress)})")
            print(f"    Lift: {hn_crash/ln_crash:.2f}x" if ln_crash > 0 else "    Lift: N/A")

    # ── Compare to old NDD ──────────────────────────────────────────────────
    print(f"\n  {'═' * 70}")
    print(f"  COMPARISON: CONTAGION ENGINE vs OLD NDD v3.1 vs CRASH MODEL v2")
    print(f"  {'═' * 70}")

    # Old NDD comparison (only for tokens that have NDD)
    conn = sqlite3.connect(DB_PATH)
    ndd_rows = conn.execute("SELECT token_id, week_date, ndd FROM crypto_ndd_history").fetchall()
    conn.close()

    ndd_lookup = {}
    for tid, wd, ndd_val in ndd_rows:
        ndd_lookup[(tid, wd)] = ndd_val

    # Match: find observations where we have both contagion score and old NDD
    matched_is = []
    matched_oos = []
    for s in all_scores:
        key = (s['token_id'], s['date'])
        if key in ndd_lookup:
            entry = {
                'contagion_score': s['risk_score'],
                'old_ndd_inverted': 5.0 - ndd_lookup[key],
                'crashed': s['crashed'],
            }
            if s['date'] <= IS_CUTOFF:
                matched_is.append(entry)
            else:
                matched_oos.append(entry)

    for label, matched in [("IS (matched)", matched_is), ("OOS (matched)", matched_oos)]:
        if len(matched) < 50:
            continue
        contagion_auc = compute_auc([m['contagion_score'] for m in matched],
                                     [m['crashed'] for m in matched])
        old_auc = compute_auc([m['old_ndd_inverted'] for m in matched],
                               [m['crashed'] for m in matched])
        print(f"\n  {label} (n={len(matched)}):")
        print(f"    Contagion Engine AUC: {contagion_auc:.3f}")
        print(f"    Old NDD v3.1 AUC:    {old_auc:.3f}")
        print(f"    Delta:               {contagion_auc - old_auc:+.3f}")

    # ── Example outputs ─────────────────────────────────────────────────────
    print(f"\n  {'═' * 70}")
    print(f"  EXAMPLE: HIGH-RISK TOKENS (latest date)")
    print(f"  {'═' * 70}")

    latest = max(s['date'] for s in all_scores)
    latest_scores = [s for s in all_scores if s['date'] == latest]
    latest_scores.sort(key=lambda x: x['risk_score'], reverse=True)

    print(f"\n  Date: {latest}")
    print(f"  {'Token':<30} {'Score':>6} {'Level':<10} {'Int':>5} {'Ext':>5} {'Net':>5} {'Crashed':>8}")
    print(f"  {'─' * 75}")
    for s in latest_scores[:15]:
        crash_str = "YES" if s['crashed'] else "no"
        print(f"  {s['token_id'][:30]:<30} {s['risk_score']:>5.1f} {s['risk_level']:<10} "
              f"{s['internal']:>5.1f} {s['external']:>5.1f} {s['network']:>5.1f} {crash_str:>8}")

    print(f"\n  Low risk tokens:")
    for s in latest_scores[-10:]:
        crash_str = "YES" if s['crashed'] else "no"
        print(f"  {s['token_id'][:30]:<30} {s['risk_score']:>5.1f} {s['risk_level']:<10} "
              f"{s['internal']:>5.1f} {s['external']:>5.1f} {s['network']:>5.1f} {crash_str:>8}")

    # ── Cascade Clock history ───────────────────────────────────────────────
    print(f"\n  {'═' * 70}")
    print(f"  CASCADE CLOCK HISTORY")
    print(f"  {'═' * 70}")

    active_cascades = [(d, f) for d, f in cascade_history if f.get('cascade_active', 0) > 0]
    print(f"\n  Total cascade events detected: {len(active_cascades)} out of {len(cascade_history)} weeks")

    if active_cascades:
        print(f"\n  {'Date':<12} {'Depth':>6} {'Q1 ret':>8} {'Q5 ret':>8} {'Spread':>8} {'Breadth':>8}")
        print(f"  {'─' * 55}")
        for d, f in active_cascades[:20]:
            print(f"  {d:<12} {f.get('cascade_spread_depth',0):>6} "
                  f"{f.get('cascade_q1_ret',0):>7.1%} {f.get('cascade_q5_ret',0):>7.1%} "
                  f"{f.get('cascade_spread',0):>7.1%} {f.get('market_breadth_20',0):>7.1%}")

    # ── Save results ────────────────────────────────────────────────────────
    summary = {
        'version': 'contagion_engine_v1',
        'run_date': datetime.now().isoformat(),
        'total_observations': len(all_scores),
        'cascade_events': len(active_cascades),
        'cascade_total_weeks': len(cascade_history),
    }

    # Add AUC if computed
    if oos_scores:
        summary['oos_auc'] = compute_auc(
            [s['risk_score'] for s in oos_scores],
            [s['crashed'] for s in oos_scores])
        summary['oos_n'] = len(oos_scores)

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "contagion_engine_results.json")
    with open(path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Saved to {path}")

    print(f"\n  {'═' * 70}")
    print(f"  FINAL VERDICT")
    print(f"  {'═' * 70}")

    if oos_scores:
        oos_auc = summary.get('oos_auc', 0)
        if oos_auc >= 0.78:
            print(f"\n  🎯 OOS AUC {oos_auc:.3f} — STRONG. Production ready.")
        elif oos_auc >= 0.72:
            print(f"\n  ✅ OOS AUC {oos_auc:.3f} — GOOD. Deployable with honest communication.")
        elif oos_auc >= 0.65:
            print(f"\n  ⚠️  OOS AUC {oos_auc:.3f} — DECENT. Better than old NDD.")
        else:
            print(f"\n  ❌ OOS AUC {oos_auc:.3f} — Needs more work.")

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
