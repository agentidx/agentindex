#!/usr/bin/env python3
"""
Quick AUC recalculation — fixes the inverted AUC bug from v1 and v2.
Loads crash_model_v2.json and recomputes correct AUC on both IS and OOS.
"""
import sqlite3, os, json
from datetime import datetime, timedelta
from math import sqrt, exp
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")
IS_CUTOFF = "2023-12-31"
OOS_START = "2024-01-01"
CRASH_THRESHOLD = -0.30
CRASH_WINDOW_DAYS = 90


def auc_correct(scores, labels):
    """
    AUC = P(score_positive > score_negative).
    Higher score should mean higher crash probability.
    """
    pos_scores = [s for s, l in zip(scores, labels) if l == 1]
    neg_scores = [s for s, l in zip(scores, labels) if l == 0]
    
    if not pos_scores or not neg_scores:
        return 0.5
    
    # Sort approach: count how many (pos, neg) pairs where pos > neg
    pos_scores.sort()
    neg_scores.sort()
    
    concordant = 0
    tied = 0
    j = 0
    
    for ps in pos_scores:
        while j < len(neg_scores) and neg_scores[j] < ps:
            j += 1
        concordant += j
        # Count ties
        k = j
        while k < len(neg_scores) and neg_scores[k] == ps:
            tied += 1
            k += 1
    
    total_pairs = len(pos_scores) * len(neg_scores)
    auc = (concordant + 0.5 * tied) / total_pairs
    return auc


def auc_simple(scores, labels):
    """Even simpler: brute force for verification on a sample."""
    pos = [s for s, l in zip(scores, labels) if l == 1]
    neg = [s for s, l in zip(scores, labels) if l == 0]
    
    if not pos or not neg:
        return 0.5
    
    # Sample if too large
    import random
    random.seed(42)
    if len(pos) > 2000:
        pos = random.sample(pos, 2000)
    if len(neg) > 2000:
        neg = random.sample(neg, 2000)
    
    concordant = sum(1 for p in pos for n in neg if p > n)
    tied = sum(1 for p in pos for n in neg if p == n)
    total = len(pos) * len(neg)
    
    return (concordant + 0.5 * tied) / total


# Load model
model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash_model_v2.json")
with open(model_path) as f:
    model_data = json.load(f)

weights = model_data['weights']
bias = model_data['bias']
means = model_data['feature_means']
stds = model_data['feature_stds']
features = model_data['features']
n_feat = len(features)

def sigmoid(z):
    z = max(-500, min(500, z))
    return 1.0 / (1.0 + exp(-z))

def predict(feat_vec):
    z = bias + sum(weights[j] * (feat_vec[j] - means[j]) / stds[j] for j in range(n_feat))
    return sigmoid(z)

# We need to rebuild predictions — load the v2 script's logic
# But simpler: just load the raw data and recompute

print("=" * 70)
print("  AUC RECALCULATION (bug fix)")
print("=" * 70)

# Load data
conn = sqlite3.connect(DB_PATH)

print("\n  Loading NDD history...")
ndd_rows = conn.execute("""
    SELECT token_id, week_date, ndd, signal_3, signal_5, signal_6
    FROM crypto_ndd_history WHERE ndd IS NOT NULL
    ORDER BY token_id, week_date
""").fetchall()

ndd = defaultdict(list)
for tid, wd, n, s3, s5, s6 in ndd_rows:
    ndd[tid].append({'date': wd, 'ndd': n, 'sig3_res': s3, 'sig5_cont': s5, 'sig6_str': s6})

print("  Loading price history...")
price_rows = conn.execute("""
    SELECT token_id, date, close, market_cap
    FROM crypto_price_history WHERE close IS NOT NULL AND close > 0
    ORDER BY token_id, date
""").fetchall()

prices = defaultdict(list)
for tid, d, c, m in price_rows:
    prices[tid].append({'date': d, 'close': c, 'mcap': m or 0})
prices = dict(prices)

print("  Loading ratings...")
rat_rows = conn.execute("""
    SELECT token_id, year_month, pillar_3
    FROM crypto_rating_history WHERE pillar_3 IS NOT NULL
    ORDER BY token_id, year_month
""").fetchall()

ratings = defaultdict(list)
for tid, ym, p3 in rat_rows:
    ratings[tid].append({'year_month': ym, 'p3': p3})

conn.close()

# Helper
def get_idx(lst, date, key='date'):
    result = None
    lo, hi = 0, len(lst) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if lst[mid][key] <= date:
            result = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return result

def compute_vol(pl, idx, w=30):
    if idx < w: return None
    rets = []
    for i in range(idx-w+1, idx+1):
        if i > 0 and pl[i-1]['close'] > 0:
            rets.append((pl[i]['close'] - pl[i-1]['close']) / pl[i-1]['close'])
    if len(rets) < 20: return None
    m = sum(rets)/len(rets)
    v = sum((r-m)**2 for r in rets)/len(rets)
    return sqrt(v) * sqrt(365)

# Compute IS vol 90th for threshold
print("  Computing vol threshold...")
is_vols = []
for tid in ndd:
    if tid not in prices: continue
    tp = prices[tid]
    for obs in ndd[tid]:
        if obs['date'] > IS_CUTOFF: continue
        idx = get_idx(tp, obs['date'])
        if idx and idx >= 30:
            v = compute_vol(tp, idx)
            if v: is_vols.append(v)
is_vols.sort()
vol_90th = is_vols[int(len(is_vols)*0.9)] if is_vols else 2.0
print(f"  Vol 90th: {vol_90th:.3f}")

# Build predictions
print("  Building predictions...")

is_scores, is_labels = [], []
oos_scores, oos_labels = [], []
old_is_scores, old_is_labels = [], []
old_oos_scores, old_oos_labels = [], []

for tid in sorted(ndd.keys()):
    if tid not in prices: continue
    tp = prices[tid]
    btc = prices.get('bitcoin', [])
    
    for obs in ndd[tid]:
        date = obs['date']
        idx = get_idx(tp, date)
        if not idx or idx < 90: continue
        
        close = tp[idx]['close']
        if close <= 0: continue
        
        # Target
        end_d = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=90)).strftime("%Y-%m-%d")
        max_drop = 0.0
        for i in range(idx+1, len(tp)):
            if tp[i]['date'] > end_d: break
            d = (tp[i]['close'] - close) / close
            if d < max_drop: max_drop = d
        crashed = 1 if max_drop <= CRASH_THRESHOLD else 0
        
        # Old NDD score (inverted: 5-ndd, higher = riskier)
        old_score = 5.0 - obs['ndd']
        
        # New model features
        vol = compute_vol(tp, idx)
        if vol is None: continue
        
        high_90 = max(tp[i]['close'] for i in range(idx-89, idx+1))
        dd = (close - high_90) / high_90 if high_90 > 0 else 0
        
        btc_idx = get_idx(btc, date)
        btc_vol = compute_vol(btc, btc_idx) if btc_idx else None
        if btc_vol is None: continue
        
        # NDD signals
        ndd_idx = None
        series = ndd[tid]
        for i, o in enumerate(series):
            if o['date'] <= date: ndd_idx = i
            else: break
        if ndd_idx is None: continue
        
        cur = series[ndd_idx]
        sig6 = cur.get('sig6_str') or 0
        sig5 = cur.get('sig5_cont') or 0
        sig3 = cur.get('sig3_res') or 0
        
        ndd_min = cur['ndd']
        if ndd_idx >= 4:
            ndd_min = min(series[i]['ndd'] for i in range(ndd_idx-3, ndd_idx+1))
        
        # Trust p3
        if tid not in ratings: continue
        r_idx = get_idx(ratings[tid], date[:7], key='year_month')
        if r_idx is None: continue
        p3 = ratings[tid][r_idx].get('p3') or 0
        
        # Interactions
        ndd_weak = max(0, 3.5 - ndd_min)
        maint_weak = max(0, 50 - p3) / 50
        
        ix_vol_ndd = vol * ndd_weak
        ix_dd_cont = abs(dd) * max(0, 3.0 - sig5)
        ix_btc_ndd = btc_vol * ndd_weak
        ix_vol_maint = vol * maint_weak
        
        nl_ndd2 = 1.0 if ndd_min < 2.0 else 0.0
        nl_dd_sev = 1.0 if dd < -0.40 else 0.0
        nl_vol_ext = 1.0 if vol > vol_90th else 0.0
        nl_p3_low = 1.0 if p3 < 40 else 0.0
        
        feat_vec = [vol, p3, sig6, ndd_min, sig5, sig3, dd, btc_vol,
                    ix_vol_ndd, ix_dd_cont, ix_btc_ndd, ix_vol_maint,
                    nl_ndd2, nl_dd_sev, nl_vol_ext, nl_p3_low]
        
        prob = predict(feat_vec)
        
        if date <= IS_CUTOFF:
            is_scores.append(prob)
            is_labels.append(crashed)
            old_is_scores.append(old_score)
            old_is_labels.append(crashed)
        elif date >= OOS_START:
            oos_scores.append(prob)
            oos_labels.append(crashed)
            old_oos_scores.append(old_score)
            old_oos_labels.append(crashed)

print(f"\n  IS: {len(is_scores)} predictions")
print(f"  OOS: {len(oos_scores)} predictions")

# Compute correct AUC
print(f"\n  {'═' * 60}")
print(f"  CORRECTED AUC RESULTS")
print(f"  {'═' * 60}")

new_is_auc = auc_correct(is_scores, is_labels)
new_oos_auc = auc_correct(oos_scores, oos_labels)
old_is_auc = auc_correct(old_is_scores, old_is_labels)
old_oos_auc = auc_correct(old_oos_scores, old_oos_labels)

# Verify with brute force
new_oos_auc_bf = auc_simple(oos_scores, oos_labels)
old_oos_auc_bf = auc_simple(old_oos_scores, old_oos_labels)

print(f"\n  {'Metric':<30} {'Old NDD v3.1':>14} {'New Model v2':>14} {'Delta':>10}")
print(f"  {'─' * 70}")
print(f"  {'IS AUC':<30} {old_is_auc:>14.3f} {new_is_auc:>14.3f} {new_is_auc - old_is_auc:>+10.3f}")
print(f"  {'OOS AUC':<30} {old_oos_auc:>14.3f} {new_oos_auc:>14.3f} {new_oos_auc - old_oos_auc:>+10.3f}")
print(f"  {'OOS AUC (brute force verify)':<30} {old_oos_auc_bf:>14.3f} {new_oos_auc_bf:>14.3f}")

improvement = (new_oos_auc - old_oos_auc) / old_oos_auc * 100

print(f"\n  Improvement: {improvement:+.1f}%")

if new_oos_auc >= 0.78:
    print(f"\n  🎯 STRONG — Production ready (AUC {new_oos_auc:.3f})")
elif new_oos_auc >= 0.72:
    print(f"\n  ✅ GOOD — Deployable (AUC {new_oos_auc:.3f})")
elif new_oos_auc >= 0.65:
    print(f"\n  ⚠️  DECENT — Significant improvement, room for more (AUC {new_oos_auc:.3f})")
else:
    print(f"\n  ❌ NEEDS WORK (AUC {new_oos_auc:.3f})")

print(f"\n  Done.")
