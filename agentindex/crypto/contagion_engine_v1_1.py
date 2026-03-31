#!/usr/bin/env python3
"""
NERQ CONTAGION ENGINE v1.1 (fixed)
====================================
Fix: market_cap is NULL in crypto_price_history.
Uses VOLUME as dynamic size proxy + static mcap_rank from data DB.

Three modules:
  1. CASCADE CLOCK — stress propagation across market cap tiers
  2. CONTAGION NETWORK — rolling correlations, cluster detection
  3. PROPAGATED RISK SCORE — internal + external + network = 0-100
"""

import sqlite3
import os
import json
import numpy as np
from datetime import datetime, timedelta
from math import sqrt, log, exp
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")
DATA_DB_PATH = os.path.join(SCRIPT_DIR, "..", "data", "crypto_trust.db")

IS_CUTOFF = "2023-12-31"
OOS_START = "2024-01-01"
CRASH_THRESHOLD = -0.30
CRASH_WINDOW_DAYS = 90
NETWORK_TOP_N = 500
CORR_WINDOW = 30
CORR_THRESHOLD = 0.50
SAMPLE_INTERVAL_DAYS = 7


def wilson_ci(s, n, z=1.96):
    if n == 0: return 0, 0, 0
    p = s/n; d = 1+z**2/n; c = (p+z**2/(2*n))/d
    sp = z*sqrt((p*(1-p)+z**2/(4*n))/n)/d
    return p, max(0,c-sp), min(1,c+sp)


def compute_auc(scores, labels):
    pos = sorted(s for s, l in zip(scores, labels) if l == 1)
    neg = sorted(s for s, l in zip(scores, labels) if l == 0)
    if not pos or not neg: return 0.5
    j = 0; conc = 0
    for ps in pos:
        while j < len(neg) and neg[j] < ps: j += 1
        conc += j
    return conc / (len(pos)*len(neg))


# ══════════════════════════════════════════════════════════════════════════════
# DATA
# ══════════════════════════════════════════════════════════════════════════════

def load_data():
    """Load price data and static mcap ranks."""
    conn = sqlite3.connect(DB_PATH)

    print("  Loading price history...")
    rows = conn.execute("""
        SELECT token_id, date, close, volume
        FROM crypto_price_history
        WHERE close IS NOT NULL AND close > 0
        ORDER BY token_id, date
    """).fetchall()
    conn.close()

    # prices[tid] = [(date, close, volume), ...]
    prices = defaultdict(list)
    for tid, d, c, v in rows:
        prices[tid].append((d, c, v or 0.0))
    prices = dict(prices)
    print(f"    {len(prices)} tokens, {len(rows)} rows")

    # Load static mcap rank from data DB
    mcap_rank = {}
    if os.path.exists(DATA_DB_PATH):
        print("  Loading static mcap ranks from data DB...")
        conn2 = sqlite3.connect(DATA_DB_PATH)
        try:
            mrows = conn2.execute("""
                SELECT id, market_cap_usd, market_cap_rank
                FROM crypto_tokens
                WHERE market_cap_usd IS NOT NULL AND market_cap_usd > 0
            """).fetchall()
            for tid, mcap, rank in mrows:
                mcap_rank[tid] = {'mcap': mcap, 'rank': rank or 99999}
            print(f"    {len(mcap_rank)} tokens with mcap data")
        except:
            print("    Could not load mcap data")
        conn2.close()
    else:
        print(f"  Data DB not found at {DATA_DB_PATH}")

    return prices, mcap_rank


def get_idx(series, date):
    lo, hi = 0, len(series)-1
    result = None
    while lo <= hi:
        mid = (lo+hi)//2
        if series[mid][0] <= date: result = mid; lo = mid+1
        else: hi = mid-1
    return result


def get_return(series, idx, days):
    if idx < days: return None
    now = series[idx][1]; past = series[idx-days][1]
    return (now-past)/past if past > 0 else None


def get_vol(series, idx, w=30):
    if idx is None or idx < w: return None
    rets = []
    for i in range(idx-w+1, idx+1):
        if i > 0 and series[i-1][1] > 0:
            rets.append((series[i][1]-series[i-1][1])/series[i-1][1])
    if len(rets) < 20: return None
    m = sum(rets)/len(rets)
    v = sum((r-m)**2 for r in rets)/len(rets)
    return sqrt(v)*sqrt(365)


def get_top_tokens(prices, mcap_rank, date, top_n=NETWORK_TOP_N):
    """
    Get top N tokens at date.
    Strategy: use volume as dynamic proxy, boosted by static mcap rank.
    """
    token_scores = []
    for tid, series in prices.items():
        idx = get_idx(series, date)
        if idx is None or idx < 30:
            continue

        # Average volume over last 7 days
        vol_sum = 0; vol_cnt = 0
        for i in range(max(0, idx-6), idx+1):
            if series[i][2] > 0:
                vol_sum += series[i][2]
                vol_cnt += 1
        avg_vol = vol_sum / vol_cnt if vol_cnt > 0 else 0

        # Static mcap boost
        static_mcap = mcap_rank.get(tid, {}).get('mcap', 0)

        # Combined score: volume + static mcap (both are $ denominated)
        score = avg_vol + static_mcap * 0.001  # weight mcap lightly
        if score > 0:
            token_scores.append((tid, score))

    token_scores.sort(key=lambda x: x[1], reverse=True)
    return [t[0] for t in token_scores[:top_n]]


def get_all_tokens_with_returns(prices, date, lookback=7):
    """Get all tokens with their recent return, sorted by volume."""
    results = []
    for tid, series in prices.items():
        idx = get_idx(series, date)
        if idx is None or idx < lookback:
            continue
        ret = get_return(series, idx, lookback)
        if ret is None:
            continue
        vol = series[idx][2]
        results.append((tid, vol, ret))
    results.sort(key=lambda x: x[1], reverse=True)  # sort by volume
    return results


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 1: CASCADE CLOCK
# ══════════════════════════════════════════════════════════════════════════════

def compute_cascade(prices, date, lookback=7):
    """Cascade indicators: quintile stress analysis."""
    tokens = get_all_tokens_with_returns(prices, date, lookback)
    if len(tokens) < 100:
        return None

    # Quintiles by volume (proxy for size)
    n = len(tokens)
    q_size = n // 5

    quintiles = {}
    for q in range(5):
        s = q * q_size
        e = s + q_size if q < 4 else n
        q_rets = [t[2] for t in tokens[s:e]]

        quintiles[q+1] = {
            'avg_ret': float(np.mean(q_rets)),
            'pct_falling_10': sum(1 for r in q_rets if r < -0.10) / len(q_rets),
            'pct_falling_20': sum(1 for r in q_rets if r < -0.20) / len(q_rets),
            'n': len(q_rets),
        }

    # NOTE: Q1=LARGEST (highest volume), Q5=SMALLEST
    # For cascade: stress starts at Q5 (smallest) and spreads to Q1 (largest)
    features = {}
    features['q1_large_ret'] = quintiles[1]['avg_ret']
    features['q5_small_ret'] = quintiles[5]['avg_ret']
    features['cascade_spread'] = quintiles[5]['avg_ret'] - quintiles[1]['avg_ret']

    # Cascade depth: how many quintiles falling?
    falling = sum(1 for q in range(1,6) if quintiles[q]['avg_ret'] < -0.05)
    features['cascade_depth'] = falling

    # Cascade active: small caps falling hard, large caps still OK
    if quintiles[5]['avg_ret'] < -0.10 and quintiles[1]['avg_ret'] > -0.05:
        features['cascade_active'] = 1.0
        depth = 1
        if quintiles[4]['avg_ret'] < -0.07: depth = 2
        if quintiles[3]['avg_ret'] < -0.05: depth = 3
        if quintiles[2]['avg_ret'] < -0.03: depth = 4
        features['cascade_spread_depth'] = depth
    else:
        features['cascade_active'] = 0.0
        features['cascade_spread_depth'] = 0

    # Market breadth
    all_rets = [t[2] for t in tokens]
    features['breadth_10'] = sum(1 for r in all_rets if r < -0.10) / len(all_rets)
    features['breadth_20'] = sum(1 for r in all_rets if r < -0.20) / len(all_rets)
    features['market_avg_ret'] = float(np.mean(all_rets))

    return features


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 2: CONTAGION NETWORK
# ══════════════════════════════════════════════════════════════════════════════

def build_corr_network(prices, tokens, date):
    """Build correlation network for tokens at date."""
    n = len(tokens)
    mat = np.zeros((CORR_WINDOW, n))
    valid = [False] * n

    for j, tid in enumerate(tokens):
        if tid not in prices: continue
        series = prices[tid]
        idx = get_idx(series, date)
        if idx is None or idx < CORR_WINDOW: continue

        has_data = True
        for i in range(CORR_WINDOW):
            di = idx - CORR_WINDOW + 1 + i
            if di > 0 and series[di-1][1] > 0:
                mat[i, j] = (series[di][1] - series[di-1][1]) / series[di-1][1]
            else:
                has_data = False
                break
        valid[j] = has_data

    # Filter to valid tokens only
    valid_idx = [j for j in range(n) if valid[j]]
    if len(valid_idx) < 20:
        return {}, np.array([])

    valid_tokens = [tokens[j] for j in valid_idx]
    valid_mat = mat[:, valid_idx]

    # Standardize
    means = valid_mat.mean(axis=0, keepdims=True)
    stds = valid_mat.std(axis=0, keepdims=True)
    stds[stds < 1e-10] = 1.0
    std_mat = (valid_mat - means) / stds

    corr = (std_mat.T @ std_mat) / CORR_WINDOW
    np.fill_diagonal(corr, 0)

    # Get 7-day returns for neighbor stress
    returns = {}
    for tid in valid_tokens:
        series = prices[tid]
        idx = get_idx(series, date)
        if idx is not None:
            r = get_return(series, idx, 7)
            if r is not None:
                returns[tid] = r

    # Build network info
    network = {}
    nv = len(valid_tokens)

    for i, tid in enumerate(valid_tokens):
        strong = [j for j in range(nv) if j != i and corr[i,j] > CORR_THRESHOLD]

        neighbor_rets = []
        neighbor_wts = []
        for j in strong:
            other = valid_tokens[j]
            if other in returns:
                neighbor_rets.append(returns[other])
                neighbor_wts.append(corr[i,j])

        if neighbor_rets:
            wts = np.array(neighbor_wts)
            rets = np.array(neighbor_rets)
            w_ret = float(np.average(rets, weights=wts))
            pct_fall = sum(1 for r in neighbor_rets if r < -0.10) / len(neighbor_rets)
        else:
            w_ret = 0.0
            pct_fall = 0.0

        network[tid] = {
            'n_connections': len(strong),
            'neighbor_avg_ret': w_ret,
            'neighbor_pct_falling': pct_fall,
            'n_neighbors_falling': sum(1 for r in neighbor_rets if r < -0.10),
        }

    return network, corr


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 3: PROPAGATED RISK SCORE
# ══════════════════════════════════════════════════════════════════════════════

def compute_risk_score(prices, tid, date, cascade, network, btc_vol):
    """Compute 0-100 risk score for a token."""
    if tid not in prices: return None
    series = prices[tid]
    idx = get_idx(series, date)
    if idx is None or idx < 90: return None

    close = series[idx][1]
    if close <= 0: return None

    exp_dict = {}

    # ── INTERNAL (0-40) ─────────────────────────────────────────────────────
    internal = 0.0

    # Volatility (0-15)
    vol = get_vol(series, idx, 30)
    if vol is not None:
        internal += min(15, vol * 8)
        exp_dict['vol_30d'] = round(vol, 3)

    # Drawdown 90d (0-12)
    high_90 = max(series[i][1] for i in range(max(0, idx-89), idx+1))
    dd = (close - high_90) / high_90 if high_90 > 0 else 0
    internal += min(12, abs(dd) * 20)
    exp_dict['drawdown_90d'] = round(dd, 3)

    # Momentum (0-8)
    r7 = get_return(series, idx, 7)
    r30 = get_return(series, idx, 30)
    mom = 0
    if r7 is not None and r7 < -0.05: mom += min(4, abs(r7)*20)
    if r30 is not None and r30 < -0.10: mom += min(4, abs(r30)*10)
    internal += mom
    exp_dict['ret_7d'] = round(r7, 4) if r7 else 0

    # Volume decline (0-5) — dropping volume = less support
    if idx >= 30:
        vol_recent = np.mean([series[i][2] for i in range(max(0,idx-6), idx+1)])
        vol_past = np.mean([series[i][2] for i in range(max(0,idx-29), max(1,idx-22))])
        if vol_past > 0:
            vol_change = (vol_recent - vol_past) / vol_past
            if vol_change < -0.3:
                internal += min(5, abs(vol_change) * 5)

    # ── EXTERNAL (0-30) ─────────────────────────────────────────────────────
    external = 0.0

    # BTC vol (0-10)
    if btc_vol is not None:
        external += min(10, btc_vol * 12)
        exp_dict['btc_vol'] = round(btc_vol, 3)

    # Cascade (0-12)
    if cascade:
        if cascade.get('cascade_active', 0) > 0:
            external += 6 + cascade.get('cascade_spread_depth', 0) * 1.5
            exp_dict['cascade'] = True
        else:
            external += min(8, cascade.get('breadth_20', 0) * 40)
            exp_dict['cascade'] = False

    # Market regime (0-8)
    if cascade:
        mret = cascade.get('market_avg_ret', 0)
        if mret < -0.05:
            external += min(8, abs(mret) * 40)

    # ── NETWORK (0-30) ──────────────────────────────────────────────────────
    net_score = 0.0

    if network and tid in network:
        info = network[tid]

        # Neighbors falling (0-15)
        npf = info.get('neighbor_pct_falling', 0)
        net_score += min(15, npf * 30)
        exp_dict['neighbor_pct_falling'] = round(npf, 3)

        # Neighbor avg return (0-10)
        nret = info.get('neighbor_avg_ret', 0)
        if nret < -0.05:
            net_score += min(10, abs(nret) * 50)
        exp_dict['neighbor_avg_ret'] = round(nret, 4)

        # Connections breadth (0-5)
        nc = info.get('n_connections', 0)
        net_score += min(5, nc / 20 * 5)
        exp_dict['n_connections'] = nc
    else:
        net_score = 8  # unknown = moderate-low

    # ── TOTAL ───────────────────────────────────────────────────────────────
    total = min(100, internal + external + net_score)

    if total >= 70: level = "CRITICAL"
    elif total >= 55: level = "HIGH"
    elif total >= 40: level = "ELEVATED"
    elif total >= 25: level = "MODERATE"
    else: level = "LOW"

    ndd_v4 = max(1.0, min(5.0, 5.0 - (total/100)*4.0))

    return {
        'score': round(total, 1),
        'level': level,
        'ndd_v4': round(ndd_v4, 2),
        'internal': round(internal, 1),
        'external': round(external, 1),
        'network': round(net_score, 1),
        'explain': exp_dict,
    }


def check_crash(prices, tid, date):
    if tid not in prices: return None
    series = prices[tid]
    idx = get_idx(series, date)
    if idx is None: return None
    start = series[idx][1]
    if start <= 0: return None
    end_d = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=CRASH_WINDOW_DAYS)).strftime("%Y-%m-%d")
    max_drop = 0.0
    for i in range(idx+1, len(series)):
        if series[i][0] > end_d: break
        d = (series[i][1] - start) / start
        if d < max_drop: max_drop = d
    return 1 if max_drop <= CRASH_THRESHOLD else 0


# ══════════════════════════════════════════════════════════════════════════════
# EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def evaluate(all_obs, label):
    if len(all_obs) < 100:
        print(f"\n  {label}: Too few ({len(all_obs)})")
        return 0.5

    scores = [o['score'] for o in all_obs]
    labels = [o['crashed'] for o in all_obs]
    n_crash = sum(labels)
    auc = compute_auc(scores, labels)

    print(f"\n  {'═'*70}")
    print(f"  {label}")
    print(f"  {'═'*70}")
    print(f"  N={len(all_obs)} | Crashes={n_crash} ({n_crash/len(all_obs)*100:.1f}%) | AUC={auc:.3f}")

    # Risk buckets
    print(f"\n  {'Level':<12} {'Range':>10} {'N':>7} {'Crash':>7} {'Rate':>7} {'CI':>15}")
    print(f"  {'─'*60}")
    for name, lo, hi in [("LOW",0,25),("MODERATE",25,40),("ELEVATED",40,55),("HIGH",55,70),("CRITICAL",70,101)]:
        b = [o for o in all_obs if lo <= o['score'] < hi]
        if b:
            nc = sum(o['crashed'] for o in b)
            r, ci_l, ci_h = wilson_ci(nc, len(b))
            print(f"  {name:<12} [{lo:>3}-{hi:>3}) {len(b):>7} {nc:>7} {r:>6.1%} [{ci_l*100:.0f}-{ci_h*100:.0f}%]")

    # Precision/recall
    print(f"\n  {'Thresh':>7} {'Flag':>7} {'TP':>6} {'Prec':>7} {'Rec':>7} {'F1':>6}")
    print(f"  {'─'*45}")
    best_f1 = 0
    for t in [30,40,50,55,60,65,70,75]:
        tp = sum(1 for o in all_obs if o['score'] >= t and o['crashed']==1)
        fp = sum(1 for o in all_obs if o['score'] >= t and o['crashed']==0)
        fl = tp+fp; pr = tp/fl if fl else 0; rc = tp/n_crash if n_crash else 0
        f1 = 2*pr*rc/(pr+rc) if (pr+rc) else 0
        mk = " ←" if f1 > best_f1 else ""
        if f1 > best_f1: best_f1 = f1
        print(f"  {t:>7} {fl:>7} {tp:>6} {pr:>6.1%} {rc:>6.1%} {f1:>5.3f}{mk}")

    # Component separation
    print(f"\n  Component separation (crash vs safe avg):")
    crashed = [o for o in all_obs if o['crashed']==1]
    safe = [o for o in all_obs if o['crashed']==0]
    for comp in ['internal','external','network']:
        ca = np.mean([o[comp] for o in crashed]) if crashed else 0
        sa = np.mean([o[comp] for o in safe]) if safe else 0
        print(f"    {comp:<12} crash={ca:.1f}  safe={sa:.1f}  Δ={ca-sa:+.1f}")

    # Cascade effect
    ca_obs = [o for o in all_obs if o.get('cascade_active')]
    ci_obs = [o for o in all_obs if not o.get('cascade_active')]
    if ca_obs and ci_obs:
        ca_cr = sum(o['crashed'] for o in ca_obs)/len(ca_obs)
        ci_cr = sum(o['crashed'] for o in ci_obs)/len(ci_obs)
        print(f"\n  Cascade effect:")
        print(f"    Active:   {ca_cr:.1%} crash (n={len(ca_obs)})")
        print(f"    Inactive: {ci_cr:.1%} crash (n={len(ci_obs)})")
        if ci_cr > 0: print(f"    Lift: {ca_cr/ci_cr:.2f}x")

    # Contagion effect
    hi_n = [o for o in all_obs if o.get('neighbor_pct_falling',0) > 0.3]
    lo_n = [o for o in all_obs if o.get('neighbor_pct_falling',0) <= 0.1]
    if hi_n and lo_n:
        hi_cr = sum(o['crashed'] for o in hi_n)/len(hi_n)
        lo_cr = sum(o['crashed'] for o in lo_n)/len(lo_n)
        print(f"\n  Contagion effect:")
        print(f"    >30% neighbors falling: {hi_cr:.1%} crash (n={len(hi_n)})")
        print(f"    ≤10% neighbors falling: {lo_cr:.1%} crash (n={len(lo_n)})")
        if lo_cr > 0: print(f"    Lift: {hi_cr/lo_cr:.2f}x")

    return auc


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("="*80)
    print("  NERQ CONTAGION ENGINE v1.1")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    prices, mcap_rank = load_data()

    # Weekly dates 2021+
    all_dates = sorted(set(d for series in prices.values() for d, c, v in series))
    weekly = []
    last = None
    for d in all_dates:
        if d < "2021-01-01": continue
        if last is None or (datetime.strptime(d,"%Y-%m-%d") - datetime.strptime(last,"%Y-%m-%d")).days >= 7:
            weekly.append(d)
            last = d

    is_wk = [d for d in weekly if d <= IS_CUTOFF]
    oos_wk = [d for d in weekly if d >= OOS_START]
    print(f"  {len(weekly)} weeks: IS={len(is_wk)} OOS={len(oos_wk)}")

    all_obs = []
    cascade_log = []
    total = len(weekly)
    prog = max(1, total//20)

    for wi, date in enumerate(weekly):
        if wi % prog == 0:
            pct = wi/total*100
            print(f"\n  [{pct:.0f}%] Week {wi}/{total}: {date} (obs so far: {len(all_obs)})")

        # Top tokens
        top = get_top_tokens(prices, mcap_rank, date, NETWORK_TOP_N)
        if len(top) < 50:
            print(f"    Only {len(top)} tokens, skipping")
            continue

        # M1: Cascade
        cascade = compute_cascade(prices, date)
        if cascade:
            cascade_log.append((date, cascade))

        # M2: Network
        net_result = build_corr_network(prices, top, date)
        if isinstance(net_result, tuple) and len(net_result) == 2:
            network, _ = net_result
        else:
            network = {}

        # BTC vol
        btc_series = prices.get('bitcoin', [])
        btc_idx = get_idx(btc_series, date) if btc_series else None
        btc_vol = get_vol(btc_series, btc_idx) if btc_idx else None

        # M3: Score each top token
        scored = 0
        for tid in top:
            result = compute_risk_score(prices, tid, date, cascade, network, btc_vol)
            if result is None:
                continue

            crashed = check_crash(prices, tid, date)
            if crashed is None:
                continue

            obs = {
                'token_id': tid,
                'date': date,
                'score': result['score'],
                'level': result['level'],
                'ndd_v4': result['ndd_v4'],
                'crashed': crashed,
                'internal': result['internal'],
                'external': result['external'],
                'network': result['network'],
                'cascade_active': result['explain'].get('cascade', False),
                'neighbor_pct_falling': result['explain'].get('neighbor_pct_falling', 0),
            }
            all_obs.append(obs)
            scored += 1

        if wi % prog == 0:
            print(f"    Scored {scored} tokens this week")

    print(f"\n\n  Total observations: {len(all_obs)}")

    # ── Evaluate ────────────────────────────────────────────────────────────
    is_obs = [o for o in all_obs if o['date'] <= IS_CUTOFF]
    oos_obs = [o for o in all_obs if o['date'] >= OOS_START]
    print(f"  IS: {len(is_obs)} | OOS: {len(oos_obs)}")

    is_auc = evaluate(is_obs, "IN-SAMPLE (2021-2023)")
    oos_auc = evaluate(oos_obs, "OUT-OF-SAMPLE (2024-2026)")

    # ── Compare old NDD ─────────────────────────────────────────────────────
    print(f"\n  {'═'*70}")
    print(f"  COMPARISON vs OLD NDD v3.1")
    print(f"  {'═'*70}")

    conn = sqlite3.connect(DB_PATH)
    ndd_rows = conn.execute("SELECT token_id, week_date, ndd FROM crypto_ndd_history").fetchall()
    conn.close()

    ndd_map = {}
    for tid, wd, ndd in ndd_rows:
        ndd_map[(tid, wd)] = ndd

    for label, obs in [("IS", is_obs), ("OOS", oos_obs)]:
        matched = [(o['score'], 5.0 - ndd_map[(o['token_id'], o['date'])], o['crashed'])
                   for o in obs if (o['token_id'], o['date']) in ndd_map]
        if len(matched) < 50:
            # Try fuzzy date matching (±3 days)
            fuzzy_matched = []
            for o in obs:
                tid = o['token_id']
                od = datetime.strptime(o['date'], "%Y-%m-%d")
                for delta in range(4):
                    for sign in [0, -1, 1]:
                        check = (od + timedelta(days=sign*delta)).strftime("%Y-%m-%d")
                        if (tid, check) in ndd_map:
                            fuzzy_matched.append((o['score'], 5.0 - ndd_map[(tid, check)], o['crashed']))
                            break
                    else:
                        continue
                    break
            matched = fuzzy_matched

        if len(matched) >= 50:
            ce_auc = compute_auc([m[0] for m in matched], [m[2] for m in matched])
            old_auc = compute_auc([m[1] for m in matched], [m[2] for m in matched])
            print(f"\n  {label} (n={len(matched)}):")
            print(f"    Contagion Engine: AUC {ce_auc:.3f}")
            print(f"    Old NDD v3.1:    AUC {old_auc:.3f}")
            print(f"    Delta:           {ce_auc-old_auc:+.3f}")
        else:
            print(f"\n  {label}: Not enough matched obs ({len(matched)})")

    # ── Example high-risk tokens (latest) ───────────────────────────────────
    if all_obs:
        latest = max(o['date'] for o in all_obs)
        latest_obs = sorted([o for o in all_obs if o['date']==latest],
                           key=lambda x: x['score'], reverse=True)

        print(f"\n  {'═'*70}")
        print(f"  LATEST SNAPSHOT: {latest}")
        print(f"  {'═'*70}")
        print(f"\n  TOP RISK:")
        print(f"  {'Token':<25} {'Score':>6} {'Level':<10} {'Int':>5} {'Ext':>5} {'Net':>5}")
        print(f"  {'─'*60}")
        for o in latest_obs[:15]:
            print(f"  {o['token_id'][:25]:<25} {o['score']:>5.1f} {o['level']:<10} "
                  f"{o['internal']:>5.1f} {o['external']:>5.1f} {o['network']:>5.1f}")

        print(f"\n  LOWEST RISK:")
        for o in latest_obs[-10:]:
            print(f"  {o['token_id'][:25]:<25} {o['score']:>5.1f} {o['level']:<10} "
                  f"{o['internal']:>5.1f} {o['external']:>5.1f} {o['network']:>5.1f}")

    # ── Cascade history ─────────────────────────────────────────────────────
    active = [(d,f) for d,f in cascade_log if f.get('cascade_active',0) > 0]
    print(f"\n  CASCADE EVENTS: {len(active)} / {len(cascade_log)} weeks")
    if active:
        print(f"  {'Date':<12} {'Depth':>6} {'SmallRet':>9} {'LargeRet':>9} {'Spread':>8}")
        print(f"  {'─'*48}")
        for d, f in active[:25]:
            print(f"  {d:<12} {f.get('cascade_spread_depth',0):>6} "
                  f"{f.get('q5_small_ret',0):>8.1%} {f.get('q1_large_ret',0):>8.1%} "
                  f"{f.get('cascade_spread',0):>7.1%}")

    # ── Final verdict ───────────────────────────────────────────────────────
    print(f"\n  {'═'*70}")
    print(f"  FINAL VERDICT")
    print(f"  {'═'*70}")
    print(f"  OOS AUC: {oos_auc:.3f}")

    if oos_auc >= 0.78:
        print(f"  🎯 STRONG — Production ready")
    elif oos_auc >= 0.72:
        print(f"  ✅ GOOD — Deployable")
    elif oos_auc >= 0.65:
        print(f"  ⚠️  DECENT — Better than old NDD")
    else:
        print(f"  ❌ NEEDS WORK")

    # Save
    summary = {
        'version': 'contagion_engine_v1.1',
        'run_date': datetime.now().isoformat(),
        'total_obs': len(all_obs),
        'is_auc': is_auc,
        'oos_auc': oos_auc,
        'cascade_events': len(active),
    }
    path = os.path.join(SCRIPT_DIR, "contagion_engine_results.json")
    with open(path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Saved to {path}")
    print(f"  Done.")


if __name__ == "__main__":
    main()
