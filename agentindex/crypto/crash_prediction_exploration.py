#!/usr/bin/env python3
"""
NERQ — CRASH PREDICTION FEATURE EXPLORATION v1.0
=================================================
Systematic analysis of what actually predicts crypto crashes.

Four feature categories:
  1. INTERNAL HEALTH — 7 NDD signals individually + Trust Score pillars
  2. EXTERNAL STRESS — BTC momentum, market volatility, market breadth
  3. VULNERABILITY — interaction: weak token × stressed market
  4. LIQUIDITY CASCADE — micro-cap stress spreading inward along risk curve

Data sources:
  - crypto_price_history (1.1M rows, 2017-2028)
  - crypto_ndd_history (32.5K rows, 2021-2026, weekly)
  - crypto_rating_history (7.8K rows, monthly)

Methodology:
  - Each row = one token-week observation
  - Target = 30%+ price drop within 90 days (binary)
  - Univariate AUC per feature
  - Correlation matrix between top features
  - IS: 2021-03-08 to 2023-12-31 (calibration)
  - OOS: 2024-01-01 to latest (validation)

Output: Feature ranking, top combinations, recommended model architecture.
"""

import sqlite3
import os
import sys
import json
from datetime import datetime, timedelta
from math import sqrt, log, exp
from collections import defaultdict

# ── Config ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")
IS_CUTOFF = "2023-12-31"
OOS_START = "2024-01-01"
CRASH_THRESHOLD = -0.30      # 30% drop
CRASH_WINDOW_DAYS = 90       # look-ahead window
MIN_OBS_FOR_AUC = 50         # minimum observations for reliable AUC


def wilson_ci(successes, total, z=1.96):
    if total == 0:
        return 0.0, 0.0, 0.0
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return p, max(0, center - spread), min(1, center + spread)


def compute_auc(scores, labels):
    """
    Compute AUC using the Wilcoxon-Mann-Whitney statistic.
    scores: list of float (higher = more likely crash)
    labels: list of 0/1 (1 = crash)
    Returns AUC (0.5 = random, 1.0 = perfect, 0.0 = perfectly wrong)
    """
    pairs = sorted(zip(scores, labels), key=lambda x: x[0])
    
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    
    if n_pos == 0 or n_neg == 0:
        return 0.5
    
    # Count concordant pairs
    sum_ranks = 0
    cum_neg = 0
    
    for score, label in pairs:
        if label == 0:
            cum_neg += 1
        else:
            sum_ranks += cum_neg
    
    auc = sum_ranks / (n_pos * n_neg)
    return auc


def compute_auc_inverted(scores, labels):
    """
    Compute AUC for features where LOWER value = higher crash risk.
    Returns the max of AUC and 1-AUC (so we always get the 'best direction').
    Also returns direction: 'low_is_risky' or 'high_is_risky'
    """
    auc_raw = compute_auc(scores, labels)
    if auc_raw >= 0.5:
        return auc_raw, "high_is_risky"
    else:
        return 1.0 - auc_raw, "low_is_risky"


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_all_data(conn):
    """Load and index all data sources."""
    data = {}
    
    # ── Price history ───────────────────────────────────────────────────────
    print("  Loading price history...")
    rows = conn.execute("""
        SELECT token_id, date, close, volume, market_cap
        FROM crypto_price_history
        WHERE close IS NOT NULL AND close > 0
        ORDER BY token_id, date
    """).fetchall()
    
    prices = defaultdict(list)
    for token_id, date, close, volume, mcap in rows:
        prices[token_id].append({
            'date': date, 'close': close,
            'volume': volume or 0, 'mcap': mcap or 0
        })
    
    data['prices'] = dict(prices)
    print(f"    {len(data['prices'])} tokens, {len(rows)} price points")
    
    # ── NDD history (weekly) ────────────────────────────────────────────────
    print("  Loading NDD history...")
    rows = conn.execute("""
        SELECT token_id, week_date, ndd,
               signal_1, signal_2, signal_3, signal_4,
               signal_5, signal_6, signal_7, alert_level
        FROM crypto_ndd_history
        WHERE ndd IS NOT NULL
        ORDER BY token_id, week_date
    """).fetchall()
    
    ndd = defaultdict(list)
    for token_id, week_date, ndd_val, s1, s2, s3, s4, s5, s6, s7, alert in rows:
        ndd[token_id].append({
            'date': week_date, 'ndd': ndd_val,
            'sig1_liq': s1, 'sig2_hold': s2, 'sig3_res': s3,
            'sig4_fund': s4, 'sig5_cont': s5, 'sig6_str': s6,
            'sig7_rel': s7, 'alert_level': alert
        })
    
    data['ndd'] = dict(ndd)
    print(f"    {len(data['ndd'])} tokens, {len(rows)} weekly observations")
    
    # ── Rating history (monthly) ────────────────────────────────────────────
    print("  Loading rating history...")
    rows = conn.execute("""
        SELECT token_id, year_month, rating, score,
               pillar_1, pillar_2, pillar_3, pillar_4, pillar_5
        FROM crypto_rating_history
        WHERE score IS NOT NULL
        ORDER BY token_id, year_month
    """).fetchall()
    
    ratings = defaultdict(list)
    for token_id, ym, rating, score, p1, p2, p3, p4, p5 in rows:
        ratings[token_id].append({
            'year_month': ym, 'rating': rating, 'score': score,
            'p1_security': p1, 'p2_compliance': p2, 'p3_maintenance': p3,
            'p4_popularity': p4, 'p5_ecosystem': p5
        })
    
    data['ratings'] = dict(ratings)
    print(f"    {len(data['ratings'])} tokens, {len(rows)} monthly observations")
    
    return data


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE ENGINEERING
# ══════════════════════════════════════════════════════════════════════════════

def compute_price_features(prices, token_id, target_date, lookback_days=90):
    """
    Compute price-based features for a token at a given date.
    Returns dict of features or None if insufficient data.
    """
    if token_id not in prices:
        return None
    
    token_prices = prices[token_id]
    
    # Find index for target_date
    idx = None
    for i, p in enumerate(token_prices):
        if p['date'] >= target_date:
            idx = i
            break
    
    if idx is None or idx < lookback_days:
        return None
    
    current = token_prices[idx]
    features = {}
    
    # ── Returns ─────────────────────────────────────────────────────────────
    for days, label in [(7, '7d'), (14, '14d'), (30, '30d'), (60, '60d'), (90, '90d')]:
        if idx >= days:
            past = token_prices[idx - days]['close']
            if past > 0:
                features[f'ret_{label}'] = (current['close'] - past) / past
    
    # ── Volatility (realized, 30d) ──────────────────────────────────────────
    if idx >= 30:
        returns = []
        for i in range(idx - 29, idx + 1):
            if i > 0:
                prev_close = token_prices[i-1]['close']
                if prev_close > 0:
                    r = (token_prices[i]['close'] - prev_close) / prev_close
                    returns.append(r)
        if len(returns) >= 20:
            mean_r = sum(returns) / len(returns)
            var = sum((r - mean_r)**2 for r in returns) / len(returns)
            features['vol_30d'] = sqrt(var) * sqrt(365)  # annualized
    
    # ── Volume change ───────────────────────────────────────────────────────
    if idx >= 30:
        recent_vol = sum(token_prices[i]['volume'] for i in range(idx-6, idx+1)) / 7
        past_vol = sum(token_prices[i]['volume'] for i in range(idx-29, idx-6)) / 23
        if past_vol > 0:
            features['vol_change_30d'] = (recent_vol - past_vol) / past_vol
    
    # ── Market cap ──────────────────────────────────────────────────────────
    features['mcap'] = current['mcap']
    features['mcap_log'] = log(max(current['mcap'], 1))
    
    # ── Drawdown from recent high ───────────────────────────────────────────
    if idx >= 90:
        high_90d = max(token_prices[i]['close'] for i in range(idx-89, idx+1))
        if high_90d > 0:
            features['drawdown_90d'] = (current['close'] - high_90d) / high_90d
    
    return features


def compute_btc_features(prices, target_date):
    """
    Compute BTC/market-level features (external stress indicators).
    """
    btc_id = 'bitcoin'
    if btc_id not in prices:
        return None
    
    features = compute_price_features(prices, btc_id, target_date)
    if features is None:
        return None
    
    # Rename with btc_ prefix
    btc_features = {}
    for k, v in features.items():
        btc_features[f'btc_{k}'] = v
    
    return btc_features


def compute_market_breadth(prices, target_date, lookback_days=7):
    """
    Compute market breadth features:
    - % of tokens declining > 10% in last week
    - Micro-cap vs large-cap return spread (liquidity cascade)
    - Returns by market cap quintile
    """
    features = {}
    
    # Collect weekly returns for all tokens with data on target_date
    token_returns = []
    
    for token_id, token_prices in prices.items():
        # Find target date index
        idx = None
        for i, p in enumerate(token_prices):
            if p['date'] >= target_date:
                idx = i
                break
        
        if idx is None or idx < lookback_days:
            continue
        
        current = token_prices[idx]['close']
        past = token_prices[idx - lookback_days]['close']
        mcap = token_prices[idx]['mcap']
        
        if past > 0 and current > 0 and mcap > 0:
            ret = (current - past) / past
            token_returns.append((token_id, ret, mcap))
    
    if len(token_returns) < 20:
        return None
    
    # ── Breadth: % declining > 10% ──────────────────────────────────────────
    declining_10 = sum(1 for _, r, _ in token_returns if r < -0.10)
    declining_20 = sum(1 for _, r, _ in token_returns if r < -0.20)
    features['breadth_decline_10pct'] = declining_10 / len(token_returns)
    features['breadth_decline_20pct'] = declining_20 / len(token_returns)
    
    # ── Market cap quintiles ────────────────────────────────────────────────
    sorted_by_mcap = sorted(token_returns, key=lambda x: x[2])
    n = len(sorted_by_mcap)
    q_size = n // 5
    
    if q_size >= 3:
        quintile_returns = {}
        for q in range(5):
            start = q * q_size
            end = start + q_size if q < 4 else n
            q_rets = [r for _, r, _ in sorted_by_mcap[start:end]]
            quintile_returns[q+1] = sum(q_rets) / len(q_rets) if q_rets else 0
        
        # Q1 = smallest, Q5 = largest
        features['quintile_1_ret'] = quintile_returns.get(1, 0)  # micro-caps
        features['quintile_2_ret'] = quintile_returns.get(2, 0)
        features['quintile_3_ret'] = quintile_returns.get(3, 0)
        features['quintile_5_ret'] = quintile_returns.get(5, 0)  # large-caps
        
        # ── Liquidity cascade indicator ─────────────────────────────────────
        # Micro-cap stress vs large-cap: negative = micro-caps falling harder
        features['cascade_spread'] = quintile_returns.get(1, 0) - quintile_returns.get(5, 0)
        
        # Cascade intensity: how much worse are small caps doing?
        features['cascade_q1_vs_q3'] = quintile_returns.get(1, 0) - quintile_returns.get(3, 0)
        
        # Are micro-caps falling while large-caps stable?
        if quintile_returns.get(5, 0) > -0.02 and quintile_returns.get(1, 0) < -0.10:
            features['cascade_divergence'] = 1.0
        else:
            features['cascade_divergence'] = 0.0
    
    # ── Average market return ───────────────────────────────────────────────
    all_rets = [r for _, r, _ in token_returns]
    features['market_avg_ret'] = sum(all_rets) / len(all_rets)
    
    return features


def compute_ndd_features(ndd_data, token_id, target_date):
    """
    Compute NDD-based features for a token at a given date.
    Treats all 7 signals individually.
    """
    if token_id not in ndd_data:
        return None
    
    series = ndd_data[token_id]
    
    # Find closest observation on or before target_date
    idx = None
    for i, obs in enumerate(series):
        if obs['date'] <= target_date:
            idx = i
        else:
            break
    
    if idx is None:
        return None
    
    current = series[idx]
    features = {}
    
    # ── Current values ──────────────────────────────────────────────────────
    features['ndd'] = current['ndd']
    for sig_name in ['sig1_liq', 'sig2_hold', 'sig3_res', 'sig4_fund',
                     'sig5_cont', 'sig6_str', 'sig7_rel']:
        val = current.get(sig_name)
        if val is not None:
            features[sig_name] = val
    
    # ── Changes over time ───────────────────────────────────────────────────
    for weeks_back, label in [(1, '1w'), (2, '2w'), (4, '4w'), (8, '8w')]:
        if idx >= weeks_back:
            past = series[idx - weeks_back]
            
            # NDD change
            features[f'ndd_chg_{label}'] = current['ndd'] - past['ndd']
            
            # Individual signal changes
            for sig_name in ['sig1_liq', 'sig2_hold', 'sig3_res', 'sig4_fund',
                             'sig5_cont', 'sig6_str', 'sig7_rel']:
                curr_val = current.get(sig_name)
                past_val = past.get(sig_name)
                if curr_val is not None and past_val is not None:
                    features[f'{sig_name}_chg_{label}'] = curr_val - past_val
    
    # ── Falling streak ──────────────────────────────────────────────────────
    streak = 0
    for i in range(idx, 0, -1):
        if series[i]['ndd'] < series[i-1]['ndd']:
            streak += 1
        else:
            break
    features['ndd_falling_streak'] = streak
    
    # ── NDD level category ──────────────────────────────────────────────────
    features['ndd_below_2'] = 1.0 if current['ndd'] < 2.0 else 0.0
    features['ndd_below_3'] = 1.0 if current['ndd'] < 3.0 else 0.0
    
    # ── Min NDD over last 4 weeks ───────────────────────────────────────────
    if idx >= 4:
        recent_ndds = [series[i]['ndd'] for i in range(idx-3, idx+1)]
        features['ndd_min_4w'] = min(recent_ndds)
    
    return features


def compute_rating_features(ratings_data, token_id, target_date):
    """
    Compute Trust Score features for a token at a given date.
    """
    if token_id not in ratings_data:
        return None
    
    series = ratings_data[token_id]
    target_ym = target_date[:7]  # '2023-06' from '2023-06-15'
    
    # Find closest month on or before target
    idx = None
    for i, obs in enumerate(series):
        if obs['year_month'] <= target_ym:
            idx = i
        else:
            break
    
    if idx is None:
        return None
    
    current = series[idx]
    features = {}
    
    features['trust_score'] = current['score'] or 0
    for pname in ['p1_security', 'p2_compliance', 'p3_maintenance',
                  'p4_popularity', 'p5_ecosystem']:
        val = current.get(pname)
        if val is not None:
            features[f'trust_{pname}'] = val
    
    # Rating as numeric (A1=6, A2=5, A3=4, B1=3, B2=2, B3=1, C=0)
    rating_map = {'A1': 6, 'A2': 5, 'A3': 4, 'B1': 3, 'B2': 2, 'B3': 1, 'C': 0}
    features['trust_rating_num'] = rating_map.get(current.get('rating'), 0)
    
    # Change from previous month
    if idx >= 1:
        prev = series[idx - 1]
        if prev.get('score') and current.get('score'):
            features['trust_score_chg'] = current['score'] - prev['score']
    
    return features


def check_crash(prices, token_id, target_date):
    """
    Check if token drops >= 30% within 90 days after target_date.
    Returns (crashed: bool, max_drop: float, has_data: bool)
    """
    if token_id not in prices:
        return False, 0.0, False
    
    token_prices = prices[token_id]
    
    # Find target date index
    idx = None
    for i, p in enumerate(token_prices):
        if p['date'] >= target_date:
            idx = i
            break
    
    if idx is None:
        return False, 0.0, False
    
    start_price = token_prices[idx]['close']
    if start_price <= 0:
        return False, 0.0, False
    
    end_date = (datetime.strptime(target_date, "%Y-%m-%d") + 
                timedelta(days=CRASH_WINDOW_DAYS)).strftime("%Y-%m-%d")
    
    max_drop = 0.0
    for i in range(idx + 1, len(token_prices)):
        if token_prices[i]['date'] > end_date:
            break
        drop = (token_prices[i]['close'] - start_price) / start_price
        if drop < max_drop:
            max_drop = drop
    
    return max_drop <= CRASH_THRESHOLD, max_drop, True


# ══════════════════════════════════════════════════════════════════════════════
# BUILD FEATURE MATRIX
# ══════════════════════════════════════════════════════════════════════════════

def build_feature_matrix(data):
    """
    Build the complete feature matrix: one row per token-week where NDD exists.
    """
    prices = data['prices']
    ndd_data = data['ndd']
    ratings_data = data['ratings']
    
    print("\n  Building feature matrix...")
    print("  (This will take a few minutes — computing features for each token-week)")
    
    # Cache BTC features and market breadth by date
    # First, collect all unique NDD dates
    all_dates = set()
    for token_id, series in ndd_data.items():
        for obs in series:
            all_dates.add(obs['date'])
    
    all_dates = sorted(all_dates)
    print(f"  {len(all_dates)} unique week dates to process")
    
    # Pre-compute market-level features per date
    print("  Pre-computing BTC features per date...")
    btc_cache = {}
    for date in all_dates:
        btc_cache[date] = compute_btc_features(prices, date)
    
    print("  Pre-computing market breadth per date...")
    breadth_cache = {}
    progress_interval = max(1, len(all_dates) // 10)
    for i, date in enumerate(all_dates):
        if i % progress_interval == 0:
            print(f"    {i}/{len(all_dates)} dates...")
        breadth_cache[date] = compute_market_breadth(prices, date)
    
    # Build rows
    print("  Building token-week rows...")
    rows = []
    skipped_no_price = 0
    skipped_no_crash = 0
    total_processed = 0
    
    token_list = sorted(ndd_data.keys())
    progress_interval = max(1, len(token_list) // 20)
    
    for t_idx, token_id in enumerate(token_list):
        if t_idx % progress_interval == 0:
            print(f"    Token {t_idx}/{len(token_list)}: {token_id[:30]}...")
        
        series = ndd_data[token_id]
        
        for obs in series:
            date = obs['date']
            total_processed += 1
            
            # Target: did this token crash within 90 days?
            crashed, max_drop, has_data = check_crash(prices, token_id, date)
            if not has_data:
                skipped_no_crash += 1
                continue
            
            row = {
                'token_id': token_id,
                'date': date,
                'crashed': 1 if crashed else 0,
                'max_drop_90d': max_drop,
            }
            
            # Category 1: Internal health (NDD signals)
            ndd_feats = compute_ndd_features(ndd_data, token_id, date)
            if ndd_feats:
                row.update(ndd_feats)
            
            # Category 1b: Trust Score
            trust_feats = compute_rating_features(ratings_data, token_id, date)
            if trust_feats:
                row.update(trust_feats)
            
            # Category 2: External stress (BTC)
            btc_feats = btc_cache.get(date)
            if btc_feats:
                row.update(btc_feats)
            
            # Category 3: Price-based features for this token
            price_feats = compute_price_features(prices, token_id, date)
            if price_feats:
                row.update(price_feats)
            
            # Category 4: Market breadth + liquidity cascade
            breadth_feats = breadth_cache.get(date)
            if breadth_feats:
                row.update(breadth_feats)
            
            # Category 3b: Vulnerability interactions
            # (weak token × stressed market)
            if ndd_feats and btc_feats and price_feats:
                ndd_val = ndd_feats.get('ndd', 3.0)
                btc_ret = btc_feats.get('btc_ret_30d', 0)
                token_vol = price_feats.get('vol_30d', 0)
                
                # Weak token in falling market
                features_vuln = {}
                features_vuln['vuln_ndd_x_btc'] = (5.0 - ndd_val) * max(0, -btc_ret)
                features_vuln['vuln_vol_x_btc'] = token_vol * max(0, -btc_ret)
                
                # Cascade: is this token a micro-cap in a diverging market?
                if breadth_feats:
                    cascade = breadth_feats.get('cascade_spread', 0)
                    features_vuln['vuln_ndd_x_cascade'] = (5.0 - ndd_val) * max(0, -cascade)
                
                row.update(features_vuln)
            
            rows.append(row)
    
    print(f"\n  Feature matrix built:")
    print(f"    Total rows: {len(rows)}")
    print(f"    Crashed: {sum(r['crashed'] for r in rows)} ({sum(r['crashed'] for r in rows)/len(rows)*100:.1f}%)")
    print(f"    Skipped (no price data): {skipped_no_crash}")
    
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def analyze_features(rows, period_label):
    """
    Univariate analysis: AUC per feature, sorted by predictive power.
    """
    if len(rows) < MIN_OBS_FOR_AUC:
        print(f"  {period_label}: Too few rows ({len(rows)})")
        return []
    
    n_crash = sum(r['crashed'] for r in rows)
    n_no_crash = len(rows) - n_crash
    crash_rate = n_crash / len(rows)
    
    print(f"\n  {'═' * 70}")
    print(f"  {period_label} — FEATURE RANKING BY AUC")
    print(f"  {'═' * 70}")
    print(f"  Observations: {len(rows)} | Crashes: {n_crash} ({crash_rate*100:.1f}%) | No crash: {n_no_crash}")
    
    # Collect all feature names (excluding metadata)
    meta_keys = {'token_id', 'date', 'crashed', 'max_drop_90d'}
    all_features = set()
    for row in rows:
        all_features.update(k for k in row.keys() if k not in meta_keys)
    
    # Compute AUC per feature
    results = []
    
    for feat in sorted(all_features):
        # Get valid (score, label) pairs
        pairs = [(r[feat], r['crashed']) for r in rows if feat in r and r[feat] is not None]
        
        if len(pairs) < MIN_OBS_FOR_AUC:
            continue
        
        scores = [p[0] for p in pairs]
        labels = [p[1] for p in pairs]
        
        n_crash_feat = sum(labels)
        if n_crash_feat < 10 or (len(labels) - n_crash_feat) < 10:
            continue
        
        auc, direction = compute_auc_inverted(scores, labels)
        
        # Compute mean values for crash vs no-crash
        crash_vals = [s for s, l in pairs if l == 1]
        safe_vals = [s for s, l in pairs if l == 0]
        mean_crash = sum(crash_vals) / len(crash_vals) if crash_vals else 0
        mean_safe = sum(safe_vals) / len(safe_vals) if safe_vals else 0
        
        results.append({
            'feature': feat,
            'auc': auc,
            'direction': direction,
            'n_obs': len(pairs),
            'mean_crash': mean_crash,
            'mean_safe': mean_safe,
            'separation': abs(mean_crash - mean_safe),
        })
    
    # Sort by AUC descending
    results.sort(key=lambda x: x['auc'], reverse=True)
    
    # Print top features
    print(f"\n  {'Rank':<5} {'Feature':<30} {'AUC':>6} {'Direction':<15} {'N':>6} {'Mean(crash)':>12} {'Mean(safe)':>12}")
    print(f"  {'─' * 95}")
    
    for i, r in enumerate(results[:40]):
        print(f"  {i+1:<5} {r['feature']:<30} {r['auc']:.3f}  {r['direction']:<15} {r['n_obs']:>6} {r['mean_crash']:>12.4f} {r['mean_safe']:>12.4f}")
    
    # ── Category breakdown ──────────────────────────────────────────────────
    print(f"\n  {'═' * 70}")
    print(f"  TOP FEATURES BY CATEGORY")
    print(f"  {'═' * 70}")
    
    categories = {
        'Internal NDD signals': [r for r in results if r['feature'].startswith('sig') or r['feature'].startswith('ndd')],
        'Trust Score': [r for r in results if r['feature'].startswith('trust')],
        'BTC / External': [r for r in results if r['feature'].startswith('btc_')],
        'Token price': [r for r in results if r['feature'].startswith(('ret_', 'vol_', 'drawdown', 'mcap'))],
        'Market breadth': [r for r in results if r['feature'].startswith(('breadth', 'quintile', 'market_avg'))],
        'Liquidity cascade': [r for r in results if r['feature'].startswith('cascade')],
        'Vulnerability': [r for r in results if r['feature'].startswith('vuln')],
    }
    
    for cat_name, cat_results in categories.items():
        if not cat_results:
            print(f"\n  {cat_name}: No features with enough data")
            continue
        
        cat_results.sort(key=lambda x: x['auc'], reverse=True)
        top = cat_results[:5]
        
        best_auc = top[0]['auc'] if top else 0
        grade = "★★★" if best_auc >= 0.65 else "★★" if best_auc >= 0.58 else "★" if best_auc >= 0.52 else "○"
        
        print(f"\n  {cat_name} {grade} (best AUC: {best_auc:.3f})")
        for r in top:
            print(f"    {r['feature']:<30} AUC={r['auc']:.3f} ({r['direction']})")
    
    return results


def compute_correlations(rows, top_features):
    """
    Compute correlation matrix between top features.
    """
    if len(top_features) < 2:
        return
    
    feature_names = [f['feature'] for f in top_features[:15]]
    
    print(f"\n  {'═' * 70}")
    print(f"  CORRELATION MATRIX — TOP 15 FEATURES")
    print(f"  {'═' * 70}")
    
    # Compute pairwise correlations
    def pearson(xs, ys):
        n = len(xs)
        if n < 10:
            return 0
        mx = sum(xs) / n
        my = sum(ys) / n
        sx = sqrt(sum((x - mx)**2 for x in xs) / n)
        sy = sqrt(sum((y - my)**2 for y in ys) / n)
        if sx == 0 or sy == 0:
            return 0
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
        return cov / (sx * sy)
    
    # Print header
    short_names = [f[:8] for f in feature_names]
    header = f"  {'':>20}" + "".join(f"{s:>9}" for s in short_names)
    print(header)
    
    for i, f1 in enumerate(feature_names):
        vals1 = [r.get(f1) for r in rows]
        row_str = f"  {f1[:20]:>20}"
        
        for j, f2 in enumerate(feature_names):
            vals2 = [r.get(f2) for r in rows]
            
            # Get paired valid values
            pairs = [(v1, v2) for v1, v2 in zip(vals1, vals2) 
                     if v1 is not None and v2 is not None]
            
            if len(pairs) >= 10:
                xs = [p[0] for p in pairs]
                ys = [p[1] for p in pairs]
                corr = pearson(xs, ys)
                row_str += f"{corr:>9.2f}"
            else:
                row_str += f"{'—':>9}"
        
        print(row_str)


def print_recommendations(is_results, oos_results):
    """
    Print final recommendations based on IS and OOS analysis.
    """
    print(f"\n  {'═' * 70}")
    print(f"  RECOMMENDATIONS FOR NEW CRASH MODEL")
    print(f"  {'═' * 70}")
    
    # Find features that are strong in BOTH IS and OOS
    is_dict = {r['feature']: r['auc'] for r in is_results}
    oos_dict = {r['feature']: r['auc'] for r in oos_results}
    
    # Features present in both with AUC > 0.55 in both
    stable_features = []
    for feat, is_auc in is_dict.items():
        oos_auc = oos_dict.get(feat, 0.5)
        if is_auc >= 0.55 and oos_auc >= 0.55:
            stability = 1.0 - abs(is_auc - oos_auc)  # closer = more stable
            avg_auc = (is_auc + oos_auc) / 2
            stable_features.append({
                'feature': feat,
                'is_auc': is_auc,
                'oos_auc': oos_auc,
                'avg_auc': avg_auc,
                'stability': stability,
                'score': avg_auc * 0.7 + stability * 0.3  # weighted score
            })
    
    stable_features.sort(key=lambda x: x['score'], reverse=True)
    
    print(f"\n  STABLE FEATURES (AUC ≥ 0.55 in both IS and OOS):")
    print(f"  {'Feature':<30} {'IS AUC':>8} {'OOS AUC':>8} {'Avg':>6} {'Stability':>10}")
    print(f"  {'─' * 70}")
    
    for f in stable_features[:20]:
        print(f"  {f['feature']:<30} {f['is_auc']:>8.3f} {f['oos_auc']:>8.3f} {f['avg_auc']:>6.3f} {f['stability']:>10.3f}")
    
    # NDD signal analysis
    print(f"\n  {'─' * 70}")
    print(f"  NDD SIGNAL REWEIGHTING RECOMMENDATION")
    print(f"  {'─' * 70}")
    
    current_weights = {
        'sig1_liq': 0.10, 'sig2_hold': 0.05, 'sig3_res': 0.30,
        'sig4_fund': 0.10, 'sig5_cont': 0.25, 'sig6_str': 0.05, 'sig7_rel': 0.15
    }
    
    signal_aucs = {}
    for feat in stable_features:
        for sig in current_weights:
            if feat['feature'] == sig:
                signal_aucs[sig] = feat['avg_auc']
    
    # Also check changes
    for feat in stable_features:
        for sig in current_weights:
            if feat['feature'].startswith(sig) and feat['feature'] not in signal_aucs:
                key = feat['feature']
                signal_aucs[key] = feat['avg_auc']
    
    print(f"\n  {'Signal':<25} {'Current Wt':>10} {'Avg AUC':>8} {'Suggested action'}")
    print(f"  {'─' * 65}")
    
    for sig, current_wt in current_weights.items():
        auc = signal_aucs.get(sig, 0.5)
        # Check if any change variant is better
        change_aucs = [(f['feature'], f['avg_auc']) for f in stable_features 
                       if f['feature'].startswith(sig + '_chg')]
        best_change = max(change_aucs, key=lambda x: x[1]) if change_aucs else (None, 0.5)
        
        if auc >= 0.60:
            action = "INCREASE weight"
        elif auc >= 0.55:
            action = "KEEP or slight increase"
        elif best_change[1] >= 0.58:
            action = f"Use CHANGE ({best_change[0]}) instead"
        else:
            action = "DECREASE or REMOVE"
        
        print(f"  {sig:<25} {current_wt*100:>9.0f}% {auc:>8.3f} {action}")
    
    # Recommended model architecture
    print(f"\n  {'─' * 70}")
    print(f"  RECOMMENDED MODEL ARCHITECTURE")
    print(f"  {'─' * 70}")
    
    top_stable = [f['feature'] for f in stable_features[:10]]
    
    print(f"\n  Top 10 most stable predictive features:")
    for i, feat in enumerate(top_stable):
        f = stable_features[i]
        print(f"    {i+1}. {feat} (AUC: {f['avg_auc']:.3f}, IS↔OOS stability: {f['stability']:.3f})")
    
    print(f"\n  Suggested approach:")
    print(f"  1. Use top 5-8 stable features as inputs")
    print(f"  2. Logistic regression or simple scoring model")
    print(f"  3. Calibrate on IS (2021-2023)")
    print(f"  4. Freeze and validate on OOS (2024-2026)")
    print(f"  5. If OOS precision ≥ 60% and recall ≥ 40% → GO")
    print(f"  6. New NDD = reweighted based on feature importance")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("  NERQ — CRASH PREDICTION FEATURE EXPLORATION v1.0")
    print("  Systematic analysis: what actually predicts crypto crashes?")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    
    # Load all data
    data = load_all_data(conn)
    
    # Build feature matrix
    rows = build_feature_matrix(data)
    
    if not rows:
        print("  ERROR: No rows built. Check data.")
        conn.close()
        return
    
    # Split IS/OOS
    is_rows = [r for r in rows if r['date'] <= IS_CUTOFF]
    oos_rows = [r for r in rows if r['date'] >= OOS_START]
    
    print(f"\n  IS rows: {len(is_rows)} (crashes: {sum(r['crashed'] for r in is_rows)})")
    print(f"  OOS rows: {len(oos_rows)} (crashes: {sum(r['crashed'] for r in oos_rows)})")
    
    # Analyze IS
    is_results = analyze_features(is_rows, "IN-SAMPLE (2021-2023)")
    
    # Analyze OOS
    oos_results = analyze_features(oos_rows, "OUT-OF-SAMPLE (2024-2026)")
    
    # Correlation matrix (on full dataset for stability)
    if is_results:
        compute_correlations(rows, is_results)
    
    # Recommendations
    if is_results and oos_results:
        print_recommendations(is_results, oos_results)
    
    # Save feature matrix for further analysis
    print(f"\n  Saving feature matrix to crash_exploration_matrix.json...")
    
    # Save summary stats (not full matrix — too large)
    summary = {
        'run_date': datetime.now().isoformat(),
        'total_rows': len(rows),
        'is_rows': len(is_rows),
        'oos_rows': len(oos_rows),
        'crash_rate_is': sum(r['crashed'] for r in is_rows) / len(is_rows) if is_rows else 0,
        'crash_rate_oos': sum(r['crashed'] for r in oos_rows) / len(oos_rows) if oos_rows else 0,
        'is_results': [{'feature': r['feature'], 'auc': r['auc'], 'direction': r['direction']} 
                       for r in is_results[:30]],
        'oos_results': [{'feature': r['feature'], 'auc': r['auc'], 'direction': r['direction']} 
                        for r in oos_results[:30]],
    }
    
    summary_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                "crash_exploration_results.json")
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  Saved to {summary_path}")
    
    print(f"\n  Done.")
    conn.close()


if __name__ == "__main__":
    main()
