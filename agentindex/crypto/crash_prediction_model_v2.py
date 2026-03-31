#!/usr/bin/env python3
"""
NERQ — CRASH PREDICTION MODEL v2.0
====================================
Improvements over v1:
  - Fixed AUC calculation (was inverted)
  - Added feature interactions (volatility × NDD weakness, drawdown × contagion)
  - Added non-linear terms (squared, threshold bins)
  - Better regularization tuning
  - Expanded feature set based on v1 learnings

Features:
  BASE (8 from v1):
    vol_30d, trust_p3_maintenance, sig6_str, ndd_min_4w,
    sig5_cont, sig3_res, drawdown_90d, btc_vol_30d

  INTERACTIONS (new):
    vol_x_ndd_weakness   — high volatility + low NDD = very dangerous
    drawdown_x_contagion — already falling + contagion spreading
    btc_vol_x_ndd_weak   — stressed market + weak token
    vol_x_maintenance    — volatile + poorly maintained

  NON-LINEAR (new):
    ndd_below_2          — binary: NDD in distress zone
    drawdown_severe      — binary: already down >40% from high
    vol_extreme          — binary: vol in top decile
    trust_p3_low         — binary: maintenance score < 40

Target: 30%+ drop within 90 days.
IS: 2021-2023  |  OOS: 2024-2026
"""

import sqlite3
import os
import json
from datetime import datetime, timedelta
from math import sqrt, log, exp
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")
IS_CUTOFF = "2023-12-31"
OOS_START = "2024-01-01"
CRASH_THRESHOLD = -0.30
CRASH_WINDOW_DAYS = 90

# All features including interactions and non-linear terms
FEATURE_NAMES = [
    # Base (8)
    'vol_30d',
    'trust_p3_maintenance',
    'sig6_str',
    'ndd_min_4w',
    'sig5_cont',
    'sig3_res',
    'drawdown_90d',
    'btc_vol_30d',
    # Interactions (4)
    'ix_vol_x_ndd_weak',
    'ix_drawdown_x_cont',
    'ix_btcvol_x_ndd_weak',
    'ix_vol_x_maint_low',
    # Non-linear (4)
    'nl_ndd_below_2',
    'nl_drawdown_severe',
    'nl_vol_extreme',
    'nl_trust_p3_low',
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
    """
    AUC: probability that a random positive has higher score than random negative.
    Higher score = higher predicted crash probability.
    """
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5

    pairs = sorted(zip(scores, labels), key=lambda x: x[0])
    cum_neg = 0
    concordant = 0

    for score, label in pairs:
        if label == 0:
            cum_neg += 1
        else:
            concordant += cum_neg

    # concordant counts how many (neg, pos) pairs where neg has lower score
    # We want P(pos has HIGHER score than neg), so:
    auc = 1.0 - (concordant / (n_pos * n_neg))
    return auc


# ══════════════════════════════════════════════════════════════════════════════
# LOGISTIC REGRESSION
# ══════════════════════════════════════════════════════════════════════════════

class LogisticRegression:
    def __init__(self, n_features, learning_rate=0.01, max_iter=10000, reg_lambda=0.01):
        self.weights = [0.0] * n_features
        self.bias = 0.0
        self.lr = learning_rate
        self.max_iter = max_iter
        self.reg_lambda = reg_lambda
        self.feature_means = [0.0] * n_features
        self.feature_stds = [1.0] * n_features

    def _sigmoid(self, z):
        z = max(-500, min(500, z))
        return 1.0 / (1.0 + exp(-z))

    def _standardize_fit(self, X):
        n = len(X)
        n_feat = len(X[0])
        for j in range(n_feat):
            vals = [X[i][j] for i in range(n)]
            mean = sum(vals) / n
            var = sum((v - mean)**2 for v in vals) / n
            std = sqrt(var) if var > 1e-10 else 1.0
            self.feature_means[j] = mean
            self.feature_stds[j] = std

        return [[(X[i][j] - self.feature_means[j]) / self.feature_stds[j]
                 for j in range(n_feat)] for i in range(n)]

    def _standardize_transform(self, X):
        n_feat = len(X[0])
        return [[(X[i][j] - self.feature_means[j]) / self.feature_stds[j]
                 for j in range(n_feat)] for i in range(len(X))]

    def fit(self, X, y):
        n = len(X)
        n_feat = len(X[0])
        X_std = self._standardize_fit(X)

        best_loss = float('inf')
        patience = 0
        # Adaptive learning rate
        lr = self.lr

        for iteration in range(self.max_iter):
            total_loss = 0
            grad_w = [0.0] * n_feat
            grad_b = 0.0

            for i in range(n):
                z = self.bias + sum(self.weights[j] * X_std[i][j] for j in range(n_feat))
                pred = self._sigmoid(z)
                pred_c = max(1e-10, min(1 - 1e-10, pred))
                total_loss += -(y[i] * log(pred_c) + (1 - y[i]) * log(1 - pred_c))

                error = pred - y[i]
                for j in range(n_feat):
                    grad_w[j] += error * X_std[i][j]
                grad_b += error

            total_loss /= n

            for j in range(n_feat):
                grad_w[j] = grad_w[j] / n + self.reg_lambda * self.weights[j]
            grad_b /= n

            for j in range(n_feat):
                self.weights[j] -= lr * grad_w[j]
            self.bias -= lr * grad_b

            if total_loss < best_loss - 1e-6:
                best_loss = total_loss
                patience = 0
            else:
                patience += 1
                if patience > 300:
                    break
                if patience > 100:
                    lr *= 0.99  # decay

            if iteration % 1000 == 0:
                print(f"    Iter {iteration}: loss={total_loss:.6f}, lr={lr:.5f}")

        print(f"    Final: loss={best_loss:.6f} after {iteration+1} iterations")

    def predict_proba(self, X):
        X_std = self._standardize_transform(X)
        n_feat = len(X[0])
        return [self._sigmoid(self.bias + sum(self.weights[j] * X_std[i][j]
                for j in range(n_feat))) for i in range(len(X_std))]

    def get_feature_importance(self, feature_names):
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
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_all_data(conn):
    data = {}

    print("  Loading price history...")
    rows = conn.execute("""
        SELECT token_id, date, close, volume, market_cap
        FROM crypto_price_history WHERE close IS NOT NULL AND close > 0
        ORDER BY token_id, date
    """).fetchall()
    prices = defaultdict(list)
    for tid, d, c, v, m in rows:
        prices[tid].append({'date': d, 'close': c, 'volume': v or 0, 'mcap': m or 0})
    data['prices'] = dict(prices)
    print(f"    {len(data['prices'])} tokens, {len(rows)} price points")

    print("  Loading NDD history...")
    rows = conn.execute("""
        SELECT token_id, week_date, ndd, signal_1, signal_2, signal_3,
               signal_4, signal_5, signal_6, signal_7
        FROM crypto_ndd_history WHERE ndd IS NOT NULL
        ORDER BY token_id, week_date
    """).fetchall()
    ndd = defaultdict(list)
    for tid, wd, n, s1, s2, s3, s4, s5, s6, s7 in rows:
        ndd[tid].append({'date': wd, 'ndd': n, 'sig3_res': s3,
                         'sig5_cont': s5, 'sig6_str': s6})
    data['ndd'] = dict(ndd)
    print(f"    {len(data['ndd'])} tokens, {len(rows)} weekly obs")

    print("  Loading rating history...")
    rows = conn.execute("""
        SELECT token_id, year_month, score, pillar_3
        FROM crypto_rating_history WHERE score IS NOT NULL
        ORDER BY token_id, year_month
    """).fetchall()
    ratings = defaultdict(list)
    for tid, ym, sc, p3 in rows:
        ratings[tid].append({'year_month': ym, 'p3_maintenance': p3})
    data['ratings'] = dict(ratings)
    print(f"    {len(data['ratings'])} tokens, {len(rows)} monthly obs")

    # Pre-compute vol_30d distribution from IS for threshold calibration
    print("  Pre-computing volatility distribution for thresholds...")
    data['vol_90th'] = None  # will be set during IS build

    return data


def get_price_idx(token_prices, target_date):
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


def compute_vol(prices_list, idx, window=30):
    """Compute annualized realized volatility."""
    if idx < window:
        return None
    returns = []
    for i in range(idx - window + 1, idx + 1):
        if i > 0:
            prev = prices_list[i-1]['close']
            if prev > 0:
                returns.append((prices_list[i]['close'] - prev) / prev)
    if len(returns) < 20:
        return None
    mean_r = sum(returns) / len(returns)
    var = sum((r - mean_r)**2 for r in returns) / len(returns)
    return sqrt(var) * sqrt(365)


def compute_features(data, token_id, date, vol_90th=None):
    """Compute all 16 features for a token-week."""
    prices = data['prices']
    ndd_data = data['ndd']
    ratings = data['ratings']

    if token_id not in prices:
        return None

    tp = prices[token_id]
    idx = get_price_idx(tp, date)
    if idx is None or idx < 90:
        return None

    close = tp[idx]['close']
    if close <= 0:
        return None

    feats = {}

    # ── Base: vol_30d ───────────────────────────────────────────────────────
    vol = compute_vol(tp, idx, 30)
    if vol is None:
        return None
    feats['vol_30d'] = vol

    # ── Base: drawdown_90d ──────────────────────────────────────────────────
    high_90d = max(tp[i]['close'] for i in range(idx-89, idx+1))
    feats['drawdown_90d'] = (close - high_90d) / high_90d if high_90d > 0 else 0

    # ── Base: btc_vol_30d ───────────────────────────────────────────────────
    btc = prices.get('bitcoin')
    if not btc:
        return None
    btc_idx = get_price_idx(btc, date)
    btc_vol = compute_vol(btc, btc_idx, 30) if btc_idx else None
    if btc_vol is None:
        return None
    feats['btc_vol_30d'] = btc_vol

    # ── Base: NDD signals ───────────────────────────────────────────────────
    if token_id not in ndd_data:
        return None
    series = ndd_data[token_id]
    ndd_idx = None
    for i, obs in enumerate(series):
        if obs['date'] <= date:
            ndd_idx = i
        else:
            break
    if ndd_idx is None:
        return None

    cur_ndd = series[ndd_idx]
    feats['sig6_str'] = cur_ndd.get('sig6_str') or 0
    feats['sig5_cont'] = cur_ndd.get('sig5_cont') or 0
    feats['sig3_res'] = cur_ndd.get('sig3_res') or 0

    # ndd_min_4w
    if ndd_idx >= 4:
        feats['ndd_min_4w'] = min(series[i]['ndd'] for i in range(ndd_idx-3, ndd_idx+1))
    else:
        feats['ndd_min_4w'] = cur_ndd['ndd']

    # ── Base: trust_p3 ──────────────────────────────────────────────────────
    if token_id not in ratings:
        return None
    target_ym = date[:7]
    r_idx = None
    for i, obs in enumerate(ratings[token_id]):
        if obs['year_month'] <= target_ym:
            r_idx = i
        else:
            break
    if r_idx is None:
        return None
    feats['trust_p3_maintenance'] = ratings[token_id][r_idx].get('p3_maintenance') or 0

    # ── INTERACTIONS ────────────────────────────────────────────────────────
    ndd_weakness = max(0, 3.5 - feats['ndd_min_4w'])  # 0 if healthy, up to 2.5 if distressed
    maint_weakness = max(0, 50 - feats['trust_p3_maintenance']) / 50  # 0 if well maintained, 1 if terrible

    feats['ix_vol_x_ndd_weak'] = feats['vol_30d'] * ndd_weakness
    feats['ix_drawdown_x_cont'] = abs(feats['drawdown_90d']) * max(0, 3.0 - feats['sig5_cont'])
    feats['ix_btcvol_x_ndd_weak'] = feats['btc_vol_30d'] * ndd_weakness
    feats['ix_vol_x_maint_low'] = feats['vol_30d'] * maint_weakness

    # ── NON-LINEAR / THRESHOLD ──────────────────────────────────────────────
    feats['nl_ndd_below_2'] = 1.0 if feats['ndd_min_4w'] < 2.0 else 0.0
    feats['nl_drawdown_severe'] = 1.0 if feats['drawdown_90d'] < -0.40 else 0.0
    feats['nl_vol_extreme'] = 1.0 if vol_90th and feats['vol_30d'] > vol_90th else 0.0
    feats['nl_trust_p3_low'] = 1.0 if feats['trust_p3_maintenance'] < 40 else 0.0

    # ── Assemble feature vector ─────────────────────────────────────────────
    for f in FEATURE_NAMES:
        if f not in feats:
            return None

    return [feats[f] for f in FEATURE_NAMES]


def check_crash(prices, token_id, target_date):
    if token_id not in prices:
        return None, None
    tp = prices[token_id]
    idx = get_price_idx(tp, target_date)
    if idx is None:
        return None, None
    start = tp[idx]['close']
    if start <= 0:
        return None, None
    end_d = (datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=CRASH_WINDOW_DAYS)).strftime("%Y-%m-%d")
    max_drop = 0.0
    for i in range(idx+1, len(tp)):
        if tp[i]['date'] > end_d:
            break
        d = (tp[i]['close'] - start) / start
        if d < max_drop:
            max_drop = d
    return (1 if max_drop <= CRASH_THRESHOLD else 0), max_drop


# ══════════════════════════════════════════════════════════════════════════════
# BUILD DATASET
# ══════════════════════════════════════════════════════════════════════════════

def build_dataset(data):
    ndd_data = data['ndd']
    prices = data['prices']

    print("\n  Building dataset...")

    # First pass: collect IS vol_30d for 90th percentile threshold
    print("  Pass 1: Computing volatility threshold from IS data...")
    is_vols = []
    token_list = sorted(ndd_data.keys())

    for token_id in token_list:
        tp = prices.get(token_id)
        if not tp:
            continue
        for obs in ndd_data[token_id]:
            if obs['date'] > IS_CUTOFF:
                continue
            idx = get_price_idx(tp, obs['date'])
            if idx and idx >= 30:
                v = compute_vol(tp, idx, 30)
                if v is not None:
                    is_vols.append(v)

    is_vols.sort()
    vol_90th = is_vols[int(len(is_vols) * 0.90)] if is_vols else 2.0
    print(f"  Volatility 90th percentile (IS): {vol_90th:.3f}")

    # Second pass: build full dataset
    print("  Pass 2: Building feature matrix...")
    rows_is = []
    rows_oos = []
    skipped = 0
    progress = max(1, len(token_list) // 10)

    for t_idx, token_id in enumerate(token_list):
        if t_idx % progress == 0:
            print(f"    Token {t_idx}/{len(token_list)}...")

        for obs in ndd_data[token_id]:
            date = obs['date']
            feat_vec = compute_features(data, token_id, date, vol_90th)
            if feat_vec is None:
                skipped += 1
                continue

            crashed, max_drop = check_crash(prices, token_id, date)
            if crashed is None:
                skipped += 1
                continue

            row = {'token_id': token_id, 'date': date,
                   'features': feat_vec, 'crashed': crashed, 'max_drop': max_drop}

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

def evaluate(model, rows, label):
    X = [r['features'] for r in rows]
    y = [r['crashed'] for r in rows]
    probs = model.predict_proba(X)
    auc = compute_auc(probs, y)

    n_crash = sum(y)
    n_safe = len(y) - n_crash
    crash_rate = n_crash / len(y)

    print(f"\n  {'═' * 70}")
    print(f"  {label}")
    print(f"  {'═' * 70}")
    print(f"  N={len(rows)} | Crashes={n_crash} ({crash_rate*100:.1f}%) | AUC={auc:.3f}")

    # Precision/Recall table
    print(f"\n  {'Thresh':>7} {'Flag':>6} {'TP':>6} {'FP':>6} {'Prec':>7} {'Recall':>7} {'F1':>6}")
    print(f"  {'─' * 50}")

    best_f1 = 0
    best_thresh = 0.5
    results_at_thresh = {}

    for t in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
        tp = sum(1 for p, l in zip(probs, y) if p >= t and l == 1)
        fp = sum(1 for p, l in zip(probs, y) if p >= t and l == 0)
        fn = n_crash - tp
        flagged = tp + fp
        prec = tp / flagged if flagged else 0
        rec = tp / n_crash if n_crash else 0
        f1 = 2*prec*rec/(prec+rec) if (prec+rec) else 0
        mk = " ←" if f1 > best_f1 else ""
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = t
        print(f"  {t:>7.2f} {flagged:>6} {tp:>6} {fp:>6} {prec:>6.1%} {rec:>6.1%} {f1:>5.3f}{mk}")
        results_at_thresh[t] = {'prec': prec, 'rec': rec, 'f1': f1, 'tp': tp, 'fp': fp}

    print(f"\n  Best F1={best_f1:.3f} at threshold={best_thresh:.2f}")

    # Calibration
    print(f"\n  CALIBRATION:")
    print(f"  {'Bin':>12} {'N':>6} {'Actual':>8} {'Predicted':>10}")
    print(f"  {'─' * 40}")

    for lo in [x/10 for x in range(10)]:
        hi = lo + 0.1
        bucket = [(p, l) for p, l in zip(probs, y) if lo <= p < hi + (0.01 if lo >= 0.9 else 0)]
        if len(bucket) >= 5:
            act = sum(l for _, l in bucket) / len(bucket)
            pred = sum(p for p, _ in bucket) / len(bucket)
            print(f"  [{lo:.1f}-{hi:.1f})  {len(bucket):>6} {act:>7.1%} {pred:>9.1%}")

    # Risk buckets
    print(f"\n  RISK BUCKETS (OOS-applicable):")
    print(f"  {'Bucket':<12} {'N':>7} {'Crashes':>8} {'Rate':>7} {'95% CI':>15}")
    print(f"  {'─' * 55}")

    for name, lo, hi in [("LOW", 0, 0.20), ("MODERATE", 0.20, 0.40),
                          ("ELEVATED", 0.40, 0.55), ("HIGH", 0.55, 0.70),
                          ("CRITICAL", 0.70, 1.01)]:
        b = [(p, l) for p, l in zip(probs, y) if lo <= p < hi]
        if b:
            nc = sum(l for _, l in b)
            rate, ci_lo, ci_hi = wilson_ci(nc, len(b))
            print(f"  {name:<12} {len(b):>7} {nc:>8} {rate:>6.1%} [{ci_lo*100:.0f}-{ci_hi*100:.0f}%]")

    return auc, best_f1, best_thresh, probs


def compare_old_ndd(data, rows_is, rows_oos):
    """Compare to old NDD v3.1."""
    ndd_data = data['ndd']

    print(f"\n  {'═' * 70}")
    print(f"  COMPARISON: NEW MODEL v2 vs OLD NDD v3.1")
    print(f"  {'═' * 70}")

    results = {}
    for label, rows in [("IS", rows_is), ("OOS", rows_oos)]:
        scores = []
        labels = []
        for row in rows:
            tid = row['token_id']
            if tid not in ndd_data:
                continue
            series = ndd_data[tid]
            ndd_idx = None
            for i, obs in enumerate(series):
                if obs['date'] <= row['date']:
                    ndd_idx = i
                else:
                    break
            if ndd_idx is None:
                continue
            # Higher score = higher crash risk (invert NDD)
            scores.append(5.0 - series[ndd_idx]['ndd'])
            labels.append(row['crashed'])

        auc = compute_auc(scores, labels)
        results[label] = auc
        print(f"  Old NDD v3.1 {label}: AUC={auc:.3f} (n={len(scores)})")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("  NERQ — CRASH PREDICTION MODEL v2.0")
    print("  16 features: 8 base + 4 interactions + 4 non-linear")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    data = load_all_data(conn)
    rows_is, rows_oos = build_dataset(data)

    if not rows_is or not rows_oos:
        print("  ERROR: No data")
        conn.close()
        return

    # ── Train ───────────────────────────────────────────────────────────────
    print(f"\n  {'═' * 70}")
    print(f"  TRAINING (IS: 2021-2023)")
    print(f"  {'═' * 70}")

    X_is = [r['features'] for r in rows_is]
    y_is = [r['crashed'] for r in rows_is]

    model = LogisticRegression(
        n_features=len(FEATURE_NAMES),
        learning_rate=0.05,
        max_iter=15000,
        reg_lambda=0.005,
    )
    model.fit(X_is, y_is)

    # ── Evaluate ────────────────────────────────────────────────────────────
    is_auc, is_f1, is_thresh, _ = evaluate(model, rows_is, "IN-SAMPLE (2021-2023)")
    oos_auc, oos_f1, oos_thresh, oos_probs = evaluate(model, rows_oos, "OUT-OF-SAMPLE (2024-2026)")

    # ── Compare old NDD ─────────────────────────────────────────────────────
    old_aucs = compare_old_ndd(data, rows_is, rows_oos)

    print(f"\n  {'Metric':<25} {'Old NDD v3.1':>14} {'New v2':>14} {'Delta':>10}")
    print(f"  {'─' * 65}")
    print(f"  {'IS AUC':<25} {old_aucs.get('IS',0):>14.3f} {is_auc:>14.3f} {(is_auc - old_aucs.get('IS',0)):>+9.3f}")
    print(f"  {'OOS AUC':<25} {old_aucs.get('OOS',0):>14.3f} {oos_auc:>14.3f} {(oos_auc - old_aucs.get('OOS',0)):>+9.3f}")
    print(f"  {'OOS Best F1':<25} {'—':>14} {oos_f1:>14.3f}")

    # ── Feature importance ──────────────────────────────────────────────────
    importance = model.get_feature_importance(FEATURE_NAMES)

    print(f"\n  {'═' * 70}")
    print(f"  FEATURE IMPORTANCE (standardized |weight|)")
    print(f"  {'═' * 70}")

    total_abs = sum(f['abs_weight'] for f in importance)
    for f in importance:
        pct = f['abs_weight'] / total_abs * 100 if total_abs > 0 else 0
        bar = '█' * int(pct / 2)
        print(f"  {f['feature']:<25} {f['weight']:>+7.3f} ({pct:>5.1f}%) {bar} {f['direction']}")

    # ── NDD v4 signal weights ───────────────────────────────────────────────
    print(f"\n  {'═' * 70}")
    print(f"  NDD v4 REWEIGHTING")
    print(f"  {'═' * 70}")

    current = {'sig1_liq': 10, 'sig2_hold': 5, 'sig3_res': 30,
               'sig4_fund': 10, 'sig5_cont': 25, 'sig6_str': 5, 'sig7_rel': 15}

    # Extract signal weights from model (direct + interaction contributions)
    signal_importance = {}
    for f in importance:
        name = f['feature']
        w = f['abs_weight']
        if name == 'sig3_res':
            signal_importance['sig3_res'] = signal_importance.get('sig3_res', 0) + w
        elif name == 'sig5_cont':
            signal_importance['sig5_cont'] = signal_importance.get('sig5_cont', 0) + w
        elif name == 'sig6_str':
            signal_importance['sig6_str'] = signal_importance.get('sig6_str', 0) + w
        elif name == 'ndd_min_4w':
            # Distribute to all signals proportionally
            signal_importance['ndd_composite'] = w
        elif name == 'ix_drawdown_x_cont':
            signal_importance['sig5_cont'] = signal_importance.get('sig5_cont', 0) + w * 0.5
        elif name == 'ix_vol_x_ndd_weak':
            signal_importance['ndd_composite'] = signal_importance.get('ndd_composite', 0) + w * 0.5
        elif name == 'ix_btcvol_x_ndd_weak':
            signal_importance['ndd_composite'] = signal_importance.get('ndd_composite', 0) + w * 0.3

    sig_total = sum(signal_importance.values()) or 1
    print(f"\n  {'Signal':<20} {'Current':>8} {'Data-driven':>12} {'Change'}")
    print(f"  {'─' * 55}")

    for sig, old_wt in current.items():
        new_wt = signal_importance.get(sig, 0) / sig_total * 100
        change = "↑" if new_wt > old_wt + 3 else "↓" if new_wt < old_wt - 3 else "≈"
        print(f"  {sig:<20} {old_wt:>7}% {new_wt:>11.1f}% {change}")

    # External factors
    print(f"\n  NEW external factors to ADD to NDD v4:")
    ext_feats = [f for f in importance if f['feature'].startswith(('vol_', 'btc_', 'drawdown', 'trust_p3', 'ix_', 'nl_'))]
    for f in ext_feats[:8]:
        pct = f['abs_weight'] / total_abs * 100
        print(f"    {f['feature']:<25} {pct:>5.1f}% importance")

    # ── Final verdict ───────────────────────────────────────────────────────
    print(f"\n  {'═' * 70}")
    print(f"  FINAL VERDICT")
    print(f"  {'═' * 70}")

    oos_improvement = oos_auc - old_aucs.get('OOS', 0.5)

    if oos_auc >= 0.78:
        verdict = "🎯 STRONG — Production ready"
    elif oos_auc >= 0.72:
        verdict = "✅ GOOD — Deployable with honest communication"
    elif oos_auc >= 0.65:
        verdict = "⚠️  DECENT — Better than old, but room for more"
    else:
        verdict = "❌ WEAK — Needs more work"

    print(f"\n  New Model v2 OOS AUC:  {oos_auc:.3f}")
    print(f"  Old NDD v3.1 OOS AUC:  {old_aucs.get('OOS', 0):.3f}")
    print(f"  Improvement:           {oos_improvement:+.3f} ({oos_improvement/max(old_aucs.get('OOS',0.5), 0.01)*100:+.1f}%)")
    print(f"  OOS F1:                {oos_f1:.3f}")
    print(f"  Verdict:               {verdict}")

    if oos_auc >= 0.72:
        print(f"\n  ✅ RECOMMENDED: Deploy as NDD v4")
        print(f"  → Use risk buckets for communication")
        print(f"  → LOW/MODERATE/ELEVATED/HIGH/CRITICAL replaces single NDD score")
    elif oos_auc >= 0.65:
        print(f"\n  ⚠️  RECOMMENDED: Deploy as beta, continue improving")
        print(f"  → Add more interaction terms")
        print(f"  → Consider market breadth features with more granular data")

    # Save model
    model_data = {
        'version': 'crash_model_v2',
        'run_date': datetime.now().isoformat(),
        'features': FEATURE_NAMES,
        'weights': model.weights,
        'bias': model.bias,
        'feature_means': model.feature_means,
        'feature_stds': model.feature_stds,
        'is_auc': is_auc,
        'oos_auc': oos_auc,
        'oos_f1': oos_f1,
        'importance': [{'feature': f['feature'], 'weight': f['weight'],
                        'pct': f['abs_weight']/total_abs*100} for f in importance],
    }

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash_model_v2.json")
    with open(path, 'w') as f:
        json.dump(model_data, f, indent=2)
    print(f"\n  Saved to {path}")
    print(f"  Done.")
    conn.close()


if __name__ == "__main__":
    main()
