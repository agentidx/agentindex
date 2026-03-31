#!/usr/bin/env python3
"""
NERQ — CRASH PREDICTION MODEL v1.0 (NDD v4 candidate)
=======================================================
Combines the top stable features from exploration into a logistic regression model.

Features (from exploration, all AUC > 0.62, stability > 0.95):
  1. vol_30d          — Token 30-day realized volatility (AUC 0.720)
  2. trust_p3_maint   — Trust Score pillar 3: Maintenance (AUC 0.715)
  3. sig6_str          — NDD Signal 6: Structural (AUC 0.689)
  4. ndd_min_4w        — Minimum NDD over last 4 weeks (AUC 0.670)
  5. sig5_cont         — NDD Signal 5: Contagion (AUC 0.654)
  6. sig3_res          — NDD Signal 3: Reserves (AUC 0.653)
  7. drawdown_90d      — Current drawdown from 90-day high (AUC 0.622)
  8. btc_vol_30d       — BTC 30-day volatility / market stress (AUC 0.600)

Methodology:
  - Train logistic regression on IS (2021-2023)
  - Freeze coefficients
  - Validate on OOS (2024-2026)
  - Report precision, recall, AUC, calibration
  - Compare to old NDD

Target: 30%+ drop within 90 days.
"""

import sqlite3
import os
import sys
import json
from datetime import datetime, timedelta
from math import sqrt, log, exp, pi
from collections import defaultdict

# ── Config ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")
IS_CUTOFF = "2023-12-31"
OOS_START = "2024-01-01"
CRASH_THRESHOLD = -0.30
CRASH_WINDOW_DAYS = 90

# Features to use (ordered by importance)
FEATURE_NAMES = [
    'vol_30d',
    'trust_p3_maintenance',
    'sig6_str',
    'ndd_min_4w',
    'sig5_cont',
    'sig3_res',
    'drawdown_90d',
    'btc_vol_30d',
]


def wilson_ci(successes, total, z=1.96):
    if total == 0:
        return 0.0, 0.0, 0.0
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return p, max(0, center - spread), min(1, center + spread)


def compute_auc(scores, labels):
    """AUC via Wilcoxon-Mann-Whitney."""
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    
    pairs = sorted(zip(scores, labels), key=lambda x: x[0])
    cum_neg = 0
    sum_ranks = 0
    for score, label in pairs:
        if label == 0:
            cum_neg += 1
        else:
            sum_ranks += cum_neg
    
    return 1.0 - (sum_ranks / (n_pos * n_neg))  # higher score = higher crash prob


# ══════════════════════════════════════════════════════════════════════════════
# LOGISTIC REGRESSION (from scratch — no sklearn dependency)
# ══════════════════════════════════════════════════════════════════════════════

class LogisticRegression:
    """
    Simple logistic regression trained via gradient descent.
    No external dependencies needed.
    """
    
    def __init__(self, n_features, learning_rate=0.01, max_iter=5000, reg_lambda=0.01):
        self.weights = [0.0] * n_features
        self.bias = 0.0
        self.lr = learning_rate
        self.max_iter = max_iter
        self.reg_lambda = reg_lambda  # L2 regularization
        self.feature_means = [0.0] * n_features
        self.feature_stds = [1.0] * n_features
    
    def _sigmoid(self, z):
        # Clamp to prevent overflow
        z = max(-500, min(500, z))
        return 1.0 / (1.0 + exp(-z))
    
    def _standardize_fit(self, X):
        """Compute means and stds from training data."""
        n = len(X)
        n_feat = len(X[0])
        
        for j in range(n_feat):
            vals = [X[i][j] for i in range(n)]
            mean = sum(vals) / n
            var = sum((v - mean)**2 for v in vals) / n
            std = sqrt(var) if var > 0 else 1.0
            self.feature_means[j] = mean
            self.feature_stds[j] = std
        
        # Return standardized X
        X_std = []
        for i in range(n):
            row = [(X[i][j] - self.feature_means[j]) / self.feature_stds[j] 
                   for j in range(n_feat)]
            X_std.append(row)
        return X_std
    
    def _standardize_transform(self, X):
        """Apply learned standardization."""
        X_std = []
        for i in range(len(X)):
            row = [(X[i][j] - self.feature_means[j]) / self.feature_stds[j] 
                   for j in range(len(X[0]))]
            X_std.append(row)
        return X_std
    
    def fit(self, X, y):
        """Train on data. X = list of feature vectors, y = list of 0/1."""
        n = len(X)
        n_feat = len(X[0])
        
        # Standardize features
        X_std = self._standardize_fit(X)
        
        # Gradient descent
        best_loss = float('inf')
        patience = 0
        
        for iteration in range(self.max_iter):
            # Forward pass
            total_loss = 0
            grad_w = [0.0] * n_feat
            grad_b = 0.0
            
            for i in range(n):
                z = self.bias + sum(self.weights[j] * X_std[i][j] for j in range(n_feat))
                pred = self._sigmoid(z)
                
                # Binary cross-entropy loss
                pred_clipped = max(1e-10, min(1 - 1e-10, pred))
                loss = -(y[i] * log(pred_clipped) + (1 - y[i]) * log(1 - pred_clipped))
                total_loss += loss
                
                # Gradients
                error = pred - y[i]
                for j in range(n_feat):
                    grad_w[j] += error * X_std[i][j]
                grad_b += error
            
            total_loss /= n
            
            # L2 regularization
            for j in range(n_feat):
                grad_w[j] = grad_w[j] / n + self.reg_lambda * self.weights[j]
            grad_b /= n
            
            # Update
            for j in range(n_feat):
                self.weights[j] -= self.lr * grad_w[j]
            self.bias -= self.lr * grad_b
            
            # Early stopping
            if total_loss < best_loss - 1e-6:
                best_loss = total_loss
                patience = 0
            else:
                patience += 1
                if patience > 200:
                    break
            
            if iteration % 1000 == 0:
                print(f"    Iter {iteration}: loss={total_loss:.4f}")
        
        print(f"    Final: loss={best_loss:.4f} after {iteration+1} iterations")
    
    def predict_proba(self, X):
        """Predict crash probability for each row."""
        X_std = self._standardize_transform(X)
        n_feat = len(X[0])
        
        probs = []
        for i in range(len(X_std)):
            z = self.bias + sum(self.weights[j] * X_std[i][j] for j in range(n_feat))
            probs.append(self._sigmoid(z))
        
        return probs
    
    def get_feature_importance(self, feature_names):
        """Return feature importance (absolute standardized weight)."""
        importance = []
        for j, name in enumerate(feature_names):
            importance.append({
                'feature': name,
                'weight': self.weights[j],
                'abs_weight': abs(self.weights[j]),
                'direction': 'higher→crash' if self.weights[j] > 0 else 'lower→crash',
            })
        importance.sort(key=lambda x: x['abs_weight'], reverse=True)
        return importance


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING & FEATURE ENGINEERING (reused from exploration)
# ══════════════════════════════════════════════════════════════════════════════

def load_all_data(conn):
    data = {}
    
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
    
    print("  Loading NDD history...")
    rows = conn.execute("""
        SELECT token_id, week_date, ndd,
               signal_1, signal_2, signal_3, signal_4,
               signal_5, signal_6, signal_7
        FROM crypto_ndd_history
        WHERE ndd IS NOT NULL
        ORDER BY token_id, week_date
    """).fetchall()
    
    ndd = defaultdict(list)
    for token_id, week_date, ndd_val, s1, s2, s3, s4, s5, s6, s7 in rows:
        ndd[token_id].append({
            'date': week_date, 'ndd': ndd_val,
            'sig1_liq': s1, 'sig2_hold': s2, 'sig3_res': s3,
            'sig4_fund': s4, 'sig5_cont': s5, 'sig6_str': s6,
            'sig7_rel': s7,
        })
    data['ndd'] = dict(ndd)
    print(f"    {len(data['ndd'])} tokens, {len(rows)} weekly observations")
    
    print("  Loading rating history...")
    rows = conn.execute("""
        SELECT token_id, year_month, score, pillar_3
        FROM crypto_rating_history
        WHERE score IS NOT NULL
        ORDER BY token_id, year_month
    """).fetchall()
    
    ratings = defaultdict(list)
    for token_id, ym, score, p3 in rows:
        ratings[token_id].append({
            'year_month': ym, 'score': score, 'p3_maintenance': p3,
        })
    data['ratings'] = dict(ratings)
    print(f"    {len(data['ratings'])} tokens, {len(rows)} monthly observations")
    
    return data


def get_price_idx(token_prices, target_date):
    """Binary search for date index."""
    lo, hi = 0, len(token_prices) - 1
    result = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if token_prices[mid]['date'] <= target_date:
            result = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return result


def compute_features(data, token_id, date):
    """
    Compute all 8 features for a token at a given date.
    Returns list of feature values (in FEATURE_NAMES order) or None.
    """
    prices = data['prices']
    ndd_data = data['ndd']
    ratings_data = data['ratings']
    
    features = {}
    
    # ── Token price features ────────────────────────────────────────────────
    if token_id not in prices:
        return None
    
    token_prices = prices[token_id]
    idx = get_price_idx(token_prices, date)
    
    if idx is None or idx < 90:
        return None
    
    current_close = token_prices[idx]['close']
    if current_close <= 0:
        return None
    
    # vol_30d
    if idx >= 30:
        returns = []
        for i in range(idx - 29, idx + 1):
            if i > 0:
                prev = token_prices[i-1]['close']
                if prev > 0:
                    returns.append((token_prices[i]['close'] - prev) / prev)
        if len(returns) >= 20:
            mean_r = sum(returns) / len(returns)
            var = sum((r - mean_r)**2 for r in returns) / len(returns)
            features['vol_30d'] = sqrt(var) * sqrt(365)
    
    # drawdown_90d
    if idx >= 90:
        high_90d = max(token_prices[i]['close'] for i in range(idx-89, idx+1))
        if high_90d > 0:
            features['drawdown_90d'] = (current_close - high_90d) / high_90d
    
    # ── BTC volatility ──────────────────────────────────────────────────────
    btc_prices = prices.get('bitcoin')
    if btc_prices:
        btc_idx = get_price_idx(btc_prices, date)
        if btc_idx and btc_idx >= 30:
            returns = []
            for i in range(btc_idx - 29, btc_idx + 1):
                if i > 0:
                    prev = btc_prices[i-1]['close']
                    if prev > 0:
                        returns.append((btc_prices[i]['close'] - prev) / prev)
            if len(returns) >= 20:
                mean_r = sum(returns) / len(returns)
                var = sum((r - mean_r)**2 for r in returns) / len(returns)
                features['btc_vol_30d'] = sqrt(var) * sqrt(365)
    
    # ── NDD features ────────────────────────────────────────────────────────
    if token_id in ndd_data:
        series = ndd_data[token_id]
        ndd_idx = None
        for i, obs in enumerate(series):
            if obs['date'] <= date:
                ndd_idx = i
            else:
                break
        
        if ndd_idx is not None:
            current_ndd = series[ndd_idx]
            features['sig6_str'] = current_ndd.get('sig6_str') or 0
            features['sig5_cont'] = current_ndd.get('sig5_cont') or 0
            features['sig3_res'] = current_ndd.get('sig3_res') or 0
            
            # ndd_min_4w
            if ndd_idx >= 4:
                recent_ndds = [series[i]['ndd'] for i in range(ndd_idx-3, ndd_idx+1)]
                features['ndd_min_4w'] = min(recent_ndds)
    
    # ── Trust Score p3 ──────────────────────────────────────────────────────
    if token_id in ratings_data:
        target_ym = date[:7]
        r_idx = None
        for i, obs in enumerate(ratings_data[token_id]):
            if obs['year_month'] <= target_ym:
                r_idx = i
            else:
                break
        
        if r_idx is not None:
            features['trust_p3_maintenance'] = ratings_data[token_id][r_idx].get('p3_maintenance') or 0
    
    # ── Check all features present ──────────────────────────────────────────
    for f in FEATURE_NAMES:
        if f not in features:
            return None
    
    return [features[f] for f in FEATURE_NAMES]


def check_crash(prices, token_id, target_date):
    if token_id not in prices:
        return None, None
    
    token_prices = prices[token_id]
    idx = get_price_idx(token_prices, target_date)
    
    if idx is None:
        return None, None
    
    start_price = token_prices[idx]['close']
    if start_price <= 0:
        return None, None
    
    end_date = (datetime.strptime(target_date, "%Y-%m-%d") + 
                timedelta(days=CRASH_WINDOW_DAYS)).strftime("%Y-%m-%d")
    
    max_drop = 0.0
    for i in range(idx + 1, len(token_prices)):
        if token_prices[i]['date'] > end_date:
            break
        drop = (token_prices[i]['close'] - start_price) / start_price
        if drop < max_drop:
            max_drop = drop
    
    crashed = 1 if max_drop <= CRASH_THRESHOLD else 0
    return crashed, max_drop


# ══════════════════════════════════════════════════════════════════════════════
# BUILD DATASET
# ══════════════════════════════════════════════════════════════════════════════

def build_dataset(data):
    """Build feature matrix with target variable."""
    ndd_data = data['ndd']
    prices = data['prices']
    
    print("\n  Building dataset...")
    
    all_dates = set()
    for token_id, series in ndd_data.items():
        for obs in series:
            all_dates.add(obs['date'])
    
    rows_is = []
    rows_oos = []
    skipped = 0
    
    token_list = sorted(ndd_data.keys())
    progress = max(1, len(token_list) // 10)
    
    for t_idx, token_id in enumerate(token_list):
        if t_idx % progress == 0:
            print(f"    Token {t_idx}/{len(token_list)}...")
        
        for obs in ndd_data[token_id]:
            date = obs['date']
            
            # Compute features
            feat_vec = compute_features(data, token_id, date)
            if feat_vec is None:
                skipped += 1
                continue
            
            # Compute target
            crashed, max_drop = check_crash(prices, token_id, date)
            if crashed is None:
                skipped += 1
                continue
            
            row = {
                'token_id': token_id,
                'date': date,
                'features': feat_vec,
                'crashed': crashed,
                'max_drop': max_drop,
            }
            
            if date <= IS_CUTOFF:
                rows_is.append(row)
            elif date >= OOS_START:
                rows_oos.append(row)
    
    print(f"    IS: {len(rows_is)} rows ({sum(r['crashed'] for r in rows_is)} crashes)")
    print(f"    OOS: {len(rows_oos)} rows ({sum(r['crashed'] for r in rows_oos)} crashes)")
    print(f"    Skipped: {skipped}")
    
    return rows_is, rows_oos


# ══════════════════════════════════════════════════════════════════════════════
# EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_model(model, rows, label, feature_names):
    """Comprehensive evaluation of model on a dataset."""
    X = [r['features'] for r in rows]
    y = [r['crashed'] for r in rows]
    
    probs = model.predict_proba(X)
    
    # AUC
    auc = compute_auc(probs, y)
    
    n_crash = sum(y)
    n_safe = len(y) - n_crash
    crash_rate = n_crash / len(y)
    
    print(f"\n  {'═' * 70}")
    print(f"  {label}")
    print(f"  {'═' * 70}")
    print(f"  Observations: {len(rows)} | Crashes: {n_crash} ({crash_rate*100:.1f}%)")
    print(f"  Model AUC: {auc:.3f}")
    
    # ── Precision/Recall at various thresholds ──────────────────────────────
    print(f"\n  {'Threshold':>10} {'Flagged':>8} {'TP':>6} {'FP':>6} {'FN':>6} {'Precision':>10} {'Recall':>8} {'F1':>6}")
    print(f"  {'─' * 70}")
    
    best_f1 = 0
    best_threshold = 0.5
    
    for threshold in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        tp = sum(1 for p, l in zip(probs, y) if p >= threshold and l == 1)
        fp = sum(1 for p, l in zip(probs, y) if p >= threshold and l == 0)
        fn = sum(1 for p, l in zip(probs, y) if p < threshold and l == 1)
        
        flagged = tp + fp
        precision = tp / flagged if flagged > 0 else 0
        recall = tp / n_crash if n_crash > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        marker = " ←" if f1 > best_f1 else ""
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = threshold
        
        prec_ci = wilson_ci(tp, flagged)
        
        print(f"  {threshold:>10.2f} {flagged:>8} {tp:>6} {fp:>6} {fn:>6} {precision:>9.1%} {recall:>7.1%} {f1:>5.2f}{marker}")
    
    print(f"\n  Best F1: {best_f1:.3f} at threshold {best_threshold:.2f}")
    
    # ── Calibration: predicted probability vs actual crash rate ──────────────
    print(f"\n  CALIBRATION (predicted prob vs actual crash rate):")
    print(f"  {'Prob bin':>12} {'Count':>7} {'Actual crashes':>15} {'Actual rate':>12} {'Pred rate':>10}")
    print(f"  {'─' * 60}")
    
    bins = [(0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5),
            (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    
    for lo, hi in bins:
        in_bin = [(p, l) for p, l in zip(probs, y) if lo <= p < hi]
        if len(in_bin) >= 5:
            actual_rate = sum(l for _, l in in_bin) / len(in_bin)
            pred_rate = sum(p for p, _ in in_bin) / len(in_bin)
            actual_count = sum(l for _, l in in_bin)
            print(f"  [{lo:.1f}-{hi:.1f})  {len(in_bin):>7} {actual_count:>15} {actual_rate:>11.1%} {pred_rate:>9.1%}")
    
    # ── Risk buckets (for communication) ────────────────────────────────────
    print(f"\n  RISK BUCKETS:")
    
    buckets = [
        ("LOW RISK", 0, 0.25),
        ("MODERATE", 0.25, 0.45),
        ("ELEVATED", 0.45, 0.60),
        ("HIGH RISK", 0.60, 0.75),
        ("CRITICAL", 0.75, 1.01),
    ]
    
    print(f"  {'Bucket':<12} {'Range':>12} {'Count':>7} {'Crashes':>8} {'Crash rate':>11}")
    print(f"  {'─' * 55}")
    
    for bucket_name, lo, hi in buckets:
        in_bucket = [(p, l) for p, l in zip(probs, y) if lo <= p < hi]
        if in_bucket:
            n_in = len(in_bucket)
            n_crashed = sum(l for _, l in in_bucket)
            rate = n_crashed / n_in
            rate_p, rate_lo, rate_hi = wilson_ci(n_crashed, n_in)
            print(f"  {bucket_name:<12} [{lo:.2f}-{hi:.2f}) {n_in:>7} {n_crashed:>8} {rate:>10.1%} [{rate_lo*100:.0f}-{rate_hi*100:.0f}%]")
    
    return auc, best_f1, best_threshold, probs


def compare_old_ndd(data, rows, label):
    """
    Compare new model to old NDD as crash predictor.
    Old NDD: lower NDD = higher crash risk.
    """
    ndd_data = data['ndd']
    
    # Get NDD value for each row
    old_scores = []
    labels = []
    
    for row in rows:
        token_id = row['token_id']
        date = row['date']
        
        if token_id not in ndd_data:
            continue
        
        series = ndd_data[token_id]
        ndd_idx = None
        for i, obs in enumerate(series):
            if obs['date'] <= date:
                ndd_idx = i
            else:
                break
        
        if ndd_idx is None:
            continue
        
        ndd_val = series[ndd_idx]['ndd']
        old_scores.append(5.0 - ndd_val)  # invert: higher = more risky
        labels.append(row['crashed'])
    
    if len(old_scores) < 50:
        return 0.5
    
    auc = compute_auc(old_scores, labels)
    print(f"\n  OLD NDD (v3.1) as crash predictor ({label}):")
    print(f"  AUC: {auc:.3f} (using inverted NDD score, n={len(old_scores)})")
    
    return auc


# ══════════════════════════════════════════════════════════════════════════════
# COMPUTE NEW NDD v4 SCORE
# ══════════════════════════════════════════════════════════════════════════════

def derive_ndd_v4_weights(model, feature_names):
    """
    Convert model weights back into NDD-style weights.
    Shows how to construct a new NDD v4 composite score.
    """
    importance = model.get_feature_importance(feature_names)
    
    print(f"\n  {'═' * 70}")
    print(f"  NEW NDD v4 — DERIVED WEIGHTS")
    print(f"  {'═' * 70}")
    
    print(f"\n  Model coefficients (standardized):")
    print(f"  {'Feature':<25} {'Weight':>8} {'|Weight|':>8} {'Direction':<20}")
    print(f"  {'─' * 65}")
    
    total_abs = sum(f['abs_weight'] for f in importance)
    
    for f in importance:
        pct = f['abs_weight'] / total_abs * 100 if total_abs > 0 else 0
        print(f"  {f['feature']:<25} {f['weight']:>8.3f} {f['abs_weight']:>8.3f} {f['direction']:<20} ({pct:.1f}%)")
    
    print(f"\n  Bias: {model.bias:.3f}")
    
    # Map to NDD-style 1-5 composite
    print(f"\n  PROPOSED NDD v4 COMPOSITE:")
    print(f"  NDD v4 = weighted combination of 8 features, mapped to 1.0-5.0 scale")
    print(f"  Higher = safer, Lower = more distressed (same convention as v3)")
    print(f"\n  Feature weights for NDD v4:")
    
    # Only include NDD-native signals for the "core NDD" reweighting
    ndd_signals = {f['feature']: f for f in importance 
                   if f['feature'].startswith('sig') or f['feature'] == 'ndd_min_4w'}
    
    ndd_total = sum(f['abs_weight'] for f in ndd_signals.values())
    
    if ndd_total > 0:
        print(f"\n  NDD-internal signal reweighting:")
        for name, f in sorted(ndd_signals.items(), key=lambda x: x[1]['abs_weight'], reverse=True):
            new_wt = f['abs_weight'] / ndd_total * 100
            print(f"    {name:<20} → {new_wt:.1f}%")
    
    return importance


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("  NERQ — CRASH PREDICTION MODEL v1.0")
    print("  Logistic regression on top-8 stable features")
    print(f"  Features: {', '.join(FEATURE_NAMES)}")
    print(f"  IS: 2021 → 2023  |  OOS: 2024 → 2026")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    data = load_all_data(conn)
    
    # Build dataset
    rows_is, rows_oos = build_dataset(data)
    
    if not rows_is or not rows_oos:
        print("  ERROR: Insufficient data")
        conn.close()
        return
    
    # ── Train model on IS ───────────────────────────────────────────────────
    print(f"\n  {'═' * 70}")
    print(f"  TRAINING on In-Sample (2021-2023)")
    print(f"  {'═' * 70}")
    
    X_is = [r['features'] for r in rows_is]
    y_is = [r['crashed'] for r in rows_is]
    
    model = LogisticRegression(
        n_features=len(FEATURE_NAMES),
        learning_rate=0.05,
        max_iter=10000,
        reg_lambda=0.001,
    )
    
    print(f"  Training logistic regression ({len(X_is)} samples, {len(FEATURE_NAMES)} features)...")
    model.fit(X_is, y_is)
    
    # ── Evaluate IS ─────────────────────────────────────────────────────────
    is_auc, is_f1, is_thresh, is_probs = evaluate_model(
        model, rows_is, "IN-SAMPLE RESULTS (training data — expect optimistic)", FEATURE_NAMES)
    
    # ── Evaluate OOS (THE REAL TEST) ────────────────────────────────────────
    oos_auc, oos_f1, oos_thresh, oos_probs = evaluate_model(
        model, rows_oos, "OUT-OF-SAMPLE RESULTS (2024-2026 — model never saw this data)", FEATURE_NAMES)
    
    # ── Compare to old NDD ──────────────────────────────────────────────────
    print(f"\n  {'═' * 70}")
    print(f"  COMPARISON: NEW MODEL vs OLD NDD v3.1")
    print(f"  {'═' * 70}")
    
    old_is_auc = compare_old_ndd(data, rows_is, "IS")
    old_oos_auc = compare_old_ndd(data, rows_oos, "OOS")
    
    print(f"\n  Summary:")
    print(f"  {'Metric':<30} {'Old NDD v3.1':>15} {'New Model v4':>15} {'Improvement':>15}")
    print(f"  {'─' * 75}")
    print(f"  {'IS AUC':<30} {old_is_auc:>15.3f} {is_auc:>15.3f} {(is_auc-old_is_auc)*100:>+14.1f}pp")
    print(f"  {'OOS AUC':<30} {old_oos_auc:>15.3f} {oos_auc:>15.3f} {(oos_auc-old_oos_auc)*100:>+14.1f}pp")
    print(f"  {'OOS Best F1':<30} {'—':>15} {oos_f1:>15.3f}")
    
    # ── Feature importance ──────────────────────────────────────────────────
    importance = derive_ndd_v4_weights(model, FEATURE_NAMES)
    
    # ── Final verdict ───────────────────────────────────────────────────────
    print(f"\n  {'═' * 70}")
    print(f"  FINAL VERDICT")
    print(f"  {'═' * 70}")
    
    if oos_auc >= 0.75:
        verdict = "🎯 STRONG — Ready for production"
    elif oos_auc >= 0.70:
        verdict = "✅ GOOD — Usable with honest communication"
    elif oos_auc >= 0.65:
        verdict = "⚠️  MODERATE — Better than old NDD but room for improvement"
    else:
        verdict = "❌ WEAK — Needs more work"
    
    print(f"\n  OOS AUC: {oos_auc:.3f}")
    print(f"  OOS F1:  {oos_f1:.3f}")
    print(f"  Verdict: {verdict}")
    
    if oos_auc > old_oos_auc:
        improvement = (oos_auc - old_oos_auc) / old_oos_auc * 100
        print(f"  Improvement over old NDD: +{improvement:.1f}%")
    
    # ── Save model ──────────────────────────────────────────────────────────
    model_data = {
        'version': 'ndd_v4_candidate_1',
        'run_date': datetime.now().isoformat(),
        'features': FEATURE_NAMES,
        'weights': model.weights,
        'bias': model.bias,
        'feature_means': model.feature_means,
        'feature_stds': model.feature_stds,
        'is_auc': is_auc,
        'oos_auc': oos_auc,
        'oos_f1': oos_f1,
        'best_threshold': oos_thresh,
        'feature_importance': [
            {'feature': f['feature'], 'weight': f['weight'], 'direction': f['direction']}
            for f in importance
        ],
    }
    
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "crash_model_v1.json")
    with open(model_path, 'w') as f:
        json.dump(model_data, f, indent=2)
    print(f"\n  Model saved to {model_path}")
    
    print(f"\n  Done.")
    conn.close()


if __name__ == "__main__":
    main()
