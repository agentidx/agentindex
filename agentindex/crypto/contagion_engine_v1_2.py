#!/usr/bin/env python3
"""
NERQ CONTAGION ENGINE v1.2
============================
Fixes from v1.1 diagnosis:
  1. EXTERNAL is now PER-TOKEN: which quintile are YOU in, how is YOUR tier doing?
  2. CASCADE is RELATIVE: difference between your tier and the tier above
  3. Correlation threshold lowered 0.50 → 0.30
  4. Removed global BTC vol from external (same for all = zero discrimination)
  5. Network score weighted stronger based on actual neighbor distress
  6. Added: token-specific beta to BTC (high beta = more exposed to market moves)
"""

import sqlite3
import os
import json
import numpy as np
from datetime import datetime, timedelta
from math import sqrt, log
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
CORR_THRESHOLD = 0.30  # lowered from 0.50
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
    conn = sqlite3.connect(DB_PATH)
    print("  Loading price history...")
    rows = conn.execute("""
        SELECT token_id, date, close, volume
        FROM crypto_price_history WHERE close > 0
        ORDER BY token_id, date
    """).fetchall()
    conn.close()

    prices = defaultdict(list)
    for tid, d, c, v in rows:
        prices[tid].append((d, c, v or 0.0))
    prices = dict(prices)
    print(f"    {len(prices)} tokens, {len(rows)} rows")

    mcap_rank = {}
    if os.path.exists(DATA_DB_PATH):
        print("  Loading mcap ranks...")
        conn2 = sqlite3.connect(DATA_DB_PATH)
        try:
            for tid, mcap, rank in conn2.execute(
                "SELECT id, market_cap_usd, market_cap_rank FROM crypto_tokens WHERE market_cap_usd > 0"):
                mcap_rank[tid] = {'mcap': mcap, 'rank': rank or 99999}
        except: pass
        conn2.close()
        print(f"    {len(mcap_rank)} tokens")

    return prices, mcap_rank

def get_idx(series, date):
    lo, hi = 0, len(series)-1; r = None
    while lo <= hi:
        mid = (lo+hi)//2
        if series[mid][0] <= date: r = mid; lo = mid+1
        else: hi = mid-1
    return r

def get_return(series, idx, days):
    if idx < days: return None
    now, past = series[idx][1], series[idx-days][1]
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

def get_beta(series, btc_series, idx, btc_idx, w=30):
    """Token's beta to BTC over window. High beta = amplifies BTC moves."""
    if idx is None or idx < w or btc_idx is None or btc_idx < w:
        return None
    t_rets = []
    b_rets = []
    for i in range(w):
        ti = idx - w + 1 + i
        bi = btc_idx - w + 1 + i
        if ti > 0 and bi > 0 and series[ti-1][1] > 0 and btc_series[bi-1][1] > 0:
            t_rets.append((series[ti][1]-series[ti-1][1])/series[ti-1][1])
            b_rets.append((btc_series[bi][1]-btc_series[bi-1][1])/btc_series[bi-1][1])
    if len(t_rets) < 20:
        return None
    t_rets = np.array(t_rets)
    b_rets = np.array(b_rets)
    b_var = np.var(b_rets)
    if b_var < 1e-10:
        return None
    cov = np.mean((t_rets - t_rets.mean()) * (b_rets - b_rets.mean()))
    return cov / b_var

def get_top_tokens(prices, mcap_rank, date, top_n=NETWORK_TOP_N):
    tokens = []
    for tid, series in prices.items():
        idx = get_idx(series, date)
        if idx is None or idx < 30: continue
        vol_sum = sum(series[i][2] for i in range(max(0,idx-6), idx+1) if series[i][2] > 0)
        static = mcap_rank.get(tid, {}).get('mcap', 0)
        score = vol_sum + static * 0.001
        if score > 0: tokens.append((tid, score))
    tokens.sort(key=lambda x: x[1], reverse=True)
    return [t[0] for t in tokens[:top_n]]


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 1: CASCADE — PER-TOKEN TIER ASSIGNMENT
# ══════════════════════════════════════════════════════════════════════════════

def compute_tier_stress(prices, date, lookback=7):
    """
    Assign each token to a quintile (by volume) and compute per-tier stress.
    Returns: tier_info dict with per-quintile metrics + token→tier mapping.
    """
    tokens = []
    for tid, series in prices.items():
        idx = get_idx(series, date)
        if idx is None or idx < lookback: continue
        ret = get_return(series, idx, lookback)
        if ret is None: continue
        vol = series[idx][2]
        tokens.append((tid, vol, ret))

    if len(tokens) < 100:
        return None, {}

    tokens.sort(key=lambda x: x[1], reverse=True)
    n = len(tokens)
    q_size = n // 5

    token_tier = {}
    tier_stats = {}

    for q in range(5):
        s = q * q_size
        e = s + q_size if q < 4 else n
        tier_tokens = tokens[s:e]
        rets = [t[2] for t in tier_tokens]

        tier = q + 1  # 1=largest, 5=smallest
        tier_stats[tier] = {
            'avg_ret': float(np.mean(rets)),
            'median_ret': float(np.median(rets)),
            'pct_falling_10': sum(1 for r in rets if r < -0.10) / len(rets),
            'pct_falling_20': sum(1 for r in rets if r < -0.20) / len(rets),
            'std_ret': float(np.std(rets)),
            'n': len(rets),
        }

        for tid, vol, ret in tier_tokens:
            token_tier[tid] = tier

    # Cascade metrics
    # How much worse is each tier doing vs the tier above (closer to large-cap)?
    for tier in range(2, 6):
        tier_stats[tier]['excess_drop'] = tier_stats[tier]['avg_ret'] - tier_stats[tier-1]['avg_ret']

    tier_stats[1]['excess_drop'] = 0.0

    # Market-wide
    all_rets = [t[2] for t in tokens]
    tier_stats['market'] = {
        'avg_ret': float(np.mean(all_rets)),
        'breadth_10': sum(1 for r in all_rets if r < -0.10) / len(all_rets),
        'breadth_20': sum(1 for r in all_rets if r < -0.20) / len(all_rets),
    }

    return tier_stats, token_tier


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 2: CONTAGION NETWORK
# ══════════════════════════════════════════════════════════════════════════════

def build_network(prices, tokens, date):
    n = len(tokens)
    mat = np.zeros((CORR_WINDOW, n))
    valid = [False]*n

    for j, tid in enumerate(tokens):
        if tid not in prices: continue
        series = prices[tid]
        idx = get_idx(series, date)
        if idx is None or idx < CORR_WINDOW: continue
        ok = True
        for i in range(CORR_WINDOW):
            di = idx - CORR_WINDOW + 1 + i
            if di > 0 and series[di-1][1] > 0:
                mat[i,j] = (series[di][1]-series[di-1][1])/series[di-1][1]
            else: ok = False; break
        valid[j] = ok

    vi = [j for j in range(n) if valid[j]]
    if len(vi) < 20: return {}
    vt = [tokens[j] for j in vi]
    vm = mat[:, vi]

    means = vm.mean(axis=0, keepdims=True)
    stds = vm.std(axis=0, keepdims=True); stds[stds<1e-10]=1.0
    sm = (vm-means)/stds
    corr = (sm.T @ sm) / CORR_WINDOW
    np.fill_diagonal(corr, 0)

    # Returns for neighbor stress
    returns = {}
    for tid in vt:
        s = prices[tid]; idx = get_idx(s, date)
        if idx: r = get_return(s, idx, 7)
        else: r = None
        if r is not None: returns[tid] = r

    network = {}
    nv = len(vt)
    for i, tid in enumerate(vt):
        # All tokens above threshold
        strong_idx = [j for j in range(nv) if j!=i and corr[i,j] > CORR_THRESHOLD]

        n_rets = []; n_wts = []
        for j in strong_idx:
            ot = vt[j]
            if ot in returns:
                n_rets.append(returns[ot])
                n_wts.append(corr[i,j])

        if n_rets:
            wts = np.array(n_wts); rets = np.array(n_rets)
            w_ret = float(np.average(rets, weights=wts))
            pct_fall = sum(1 for r in n_rets if r < -0.10) / len(n_rets)
            worst_neighbor = min(n_rets)
        else:
            w_ret = 0.0; pct_fall = 0.0; worst_neighbor = 0.0

        network[tid] = {
            'n_connections': len(strong_idx),
            'neighbor_avg_ret': w_ret,
            'neighbor_pct_falling': pct_fall,
            'worst_neighbor_ret': worst_neighbor,
            'n_neighbors_falling': sum(1 for r in n_rets if r < -0.10),
        }

    return network


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 3: PROPAGATED RISK SCORE — PER-TOKEN
# ══════════════════════════════════════════════════════════════════════════════

def compute_risk(prices, tid, date, tier_stats, token_tier, network, btc_series):
    if tid not in prices: return None
    series = prices[tid]
    idx = get_idx(series, date)
    if idx is None or idx < 90: return None
    close = series[idx][1]
    if close <= 0: return None

    ex = {}

    # ── INTERNAL (0-40) ─────────────────────────────────────────────────────
    internal = 0.0

    # Volatility (0-15)
    vol = get_vol(series, idx, 30)
    if vol is not None:
        internal += min(15, vol * 8)
        ex['vol'] = round(vol, 3)

    # Drawdown 90d (0-12)
    high90 = max(series[i][1] for i in range(max(0,idx-89), idx+1))
    dd = (close-high90)/high90 if high90 > 0 else 0
    internal += min(12, abs(dd)*20)
    ex['dd90'] = round(dd, 3)

    # Momentum (0-8)
    r7 = get_return(series, idx, 7)
    r30 = get_return(series, idx, 30)
    mom = 0
    if r7 is not None and r7 < -0.05: mom += min(4, abs(r7)*20)
    if r30 is not None and r30 < -0.10: mom += min(4, abs(r30)*10)
    internal += mom

    # Volume decline (0-5)
    if idx >= 30:
        vr = np.mean([series[i][2] for i in range(max(0,idx-6), idx+1)])
        vp = np.mean([series[i][2] for i in range(max(0,idx-29), max(1,idx-22))])
        if vp > 0:
            vc = (vr-vp)/vp
            if vc < -0.3: internal += min(5, abs(vc)*5)

    # ── EXTERNAL — PER TOKEN (0-30) ────────────────────────────────────────
    external = 0.0

    my_tier = token_tier.get(tid, 3)
    tier_info = tier_stats.get(my_tier, {})

    # YOUR tier's performance (0-10)
    tier_ret = tier_info.get('avg_ret', 0)
    if tier_ret < 0:
        external += min(10, abs(tier_ret) * 50)  # -10%→5, -20%→10
    ex['tier'] = my_tier
    ex['tier_ret'] = round(tier_ret, 4)

    # YOUR tier vs tier above — cascade pressure on YOU (0-8)
    excess = tier_info.get('excess_drop', 0)
    if excess < -0.02:  # your tier falling faster than tier above
        external += min(8, abs(excess) * 80)  # -5%→4, -10%→8
    ex['excess_drop'] = round(excess, 4)

    # Tier stress breadth — what % of YOUR tier is crashing (0-7)
    tier_breadth = tier_info.get('pct_falling_20', 0)
    external += min(7, tier_breadth * 35)  # 20%→7
    ex['tier_breadth_20'] = round(tier_breadth, 3)

    # Beta to BTC — amplifies market stress for high-beta tokens (0-5)
    btc_idx = get_idx(btc_series, date) if btc_series else None
    beta = get_beta(series, btc_series, idx, btc_idx) if btc_idx else None
    btc_ret = get_return(btc_series, btc_idx, 7) if btc_idx else None

    if beta is not None and btc_ret is not None and btc_ret < -0.03:
        # High beta + BTC falling = extra risk
        beta_stress = max(0, beta - 1.0) * abs(btc_ret) * 100
        external += min(5, beta_stress)
        ex['beta'] = round(beta, 2)
        ex['btc_7d'] = round(btc_ret, 4)

    # ── NETWORK (0-30) ──────────────────────────────────────────────────────
    net_score = 0.0

    if network and tid in network:
        info = network[tid]

        # Neighbors falling hard (0-12)
        npf = info.get('neighbor_pct_falling', 0)
        net_score += min(12, npf * 24)
        ex['n_pct_fall'] = round(npf, 3)

        # Weighted neighbor return — how bad is the contagion (0-10)
        nret = info.get('neighbor_avg_ret', 0)
        if nret < 0:
            net_score += min(10, abs(nret) * 60)
        ex['n_avg_ret'] = round(nret, 4)

        # Connection count — more connected = more exposed (0-5)
        nc = info.get('n_connections', 0)
        net_score += min(5, nc / 30 * 5)
        ex['n_conn'] = nc

        # Worst neighbor — extreme contagion signal (0-3)
        worst = info.get('worst_neighbor_ret', 0)
        if worst < -0.20:
            net_score += min(3, abs(worst) * 10)
    else:
        net_score = 5  # unknown = low-moderate

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
        'explain': ex,
    }


def check_crash(prices, tid, date):
    if tid not in prices: return None
    s = prices[tid]; idx = get_idx(s, date)
    if idx is None: return None
    start = s[idx][1]
    if start <= 0: return None
    end_d = (datetime.strptime(date,"%Y-%m-%d")+timedelta(days=CRASH_WINDOW_DAYS)).strftime("%Y-%m-%d")
    mx = 0.0
    for i in range(idx+1, len(s)):
        if s[i][0] > end_d: break
        d = (s[i][1]-start)/start
        if d < mx: mx = d
    return 1 if mx <= CRASH_THRESHOLD else 0


# ══════════════════════════════════════════════════════════════════════════════
# EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def evaluate(obs, label):
    if len(obs) < 100:
        print(f"\n  {label}: Too few ({len(obs)})"); return 0.5
    scores = [o['score'] for o in obs]
    labels = [o['crashed'] for o in obs]
    nc = sum(labels); auc = compute_auc(scores, labels)

    print(f"\n  {'═'*70}")
    print(f"  {label}")
    print(f"  {'═'*70}")
    print(f"  N={len(obs)} | Crashes={nc} ({nc/len(obs)*100:.1f}%) | AUC={auc:.3f}")

    print(f"\n  {'Level':<12} {'Range':>10} {'N':>7} {'Crash':>7} {'Rate':>7} {'CI':>15}")
    print(f"  {'─'*60}")
    for name, lo, hi in [("LOW",0,25),("MODERATE",25,40),("ELEVATED",40,55),("HIGH",55,70),("CRITICAL",70,101)]:
        b = [o for o in obs if lo <= o['score'] < hi]
        if b:
            nc2 = sum(o['crashed'] for o in b)
            r, cl, ch = wilson_ci(nc2, len(b))
            print(f"  {name:<12} [{lo:>3}-{hi:>3}) {len(b):>7} {nc2:>7} {r:>6.1%} [{cl*100:.0f}-{ch*100:.0f}%]")

    print(f"\n  {'Thresh':>7} {'Flag':>7} {'TP':>6} {'Prec':>7} {'Rec':>7} {'F1':>6}")
    print(f"  {'─'*45}")
    bf = 0
    for t in [25,30,35,40,45,50,55,60,65,70]:
        tp = sum(1 for o in obs if o['score']>=t and o['crashed']==1)
        fp = sum(1 for o in obs if o['score']>=t and o['crashed']==0)
        fl=tp+fp; pr=tp/fl if fl else 0; rc=tp/nc if nc else 0
        f1=2*pr*rc/(pr+rc) if (pr+rc) else 0
        mk=" ←" if f1>bf else ""
        if f1>bf: bf=f1
        print(f"  {t:>7} {fl:>7} {tp:>6} {pr:>6.1%} {rc:>6.1%} {f1:>5.3f}{mk}")

    print(f"\n  Component separation (crash vs safe avg):")
    cr = [o for o in obs if o['crashed']==1]
    sf = [o for o in obs if o['crashed']==0]
    for comp in ['internal','external','network']:
        ca = np.mean([o[comp] for o in cr]) if cr else 0
        sa = np.mean([o[comp] for o in sf]) if sf else 0
        print(f"    {comp:<12} crash={ca:.1f}  safe={sa:.1f}  Δ={ca-sa:+.1f}")

    # Contagion effect
    hi_n = [o for o in obs if o.get('n_pct_fall',0) > 0.3]
    lo_n = [o for o in obs if o.get('n_pct_fall',0) <= 0.1]
    if hi_n and lo_n:
        hc = sum(o['crashed'] for o in hi_n)/len(hi_n)
        lc = sum(o['crashed'] for o in lo_n)/len(lo_n)
        print(f"\n  Contagion: >30% falling={hc:.1%} (n={len(hi_n)}) | ≤10%={lc:.1%} (n={len(lo_n)}) | lift={hc/lc:.2f}x" if lc>0 else "")

    # Tier effect
    for tier in [1,3,5]:
        t_obs = [o for o in obs if o.get('tier')==tier]
        if t_obs:
            tc = sum(o['crashed'] for o in t_obs)/len(t_obs)
            ta = np.mean([o['score'] for o in t_obs])
            print(f"  Tier {tier}: crash={tc:.1%} avg_score={ta:.1f} (n={len(t_obs)})")

    return auc


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("="*80)
    print("  NERQ CONTAGION ENGINE v1.2")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    prices, mcap_rank = load_data()
    btc_series = prices.get('bitcoin', [])
    print(f"  BTC series: {len(btc_series)} days")

    # Weekly dates
    all_dates = sorted(set(d for s in prices.values() for d,c,v in s))
    weekly = []; last = None
    for d in all_dates:
        if d < "2021-01-01": continue
        if last is None or (datetime.strptime(d,"%Y-%m-%d")-datetime.strptime(last,"%Y-%m-%d")).days >= 7:
            weekly.append(d); last = d

    print(f"  {len(weekly)} weeks")

    all_obs = []
    total = len(weekly); prog = max(1, total//20)

    for wi, date in enumerate(weekly):
        if wi % prog == 0:
            print(f"\n  [{wi/total*100:.0f}%] Week {wi}: {date} | obs={len(all_obs)}")

        top = get_top_tokens(prices, mcap_rank, date, NETWORK_TOP_N)
        if len(top) < 50: continue

        # M1: Tier stress
        tier_stats, token_tier = compute_tier_stress(prices, date)
        if tier_stats is None: continue

        # M2: Network
        network = build_network(prices, top, date)

        # M3: Score
        scored = 0
        for tid in top:
            result = compute_risk(prices, tid, date, tier_stats, token_tier, network, btc_series)
            if result is None: continue
            crashed = check_crash(prices, tid, date)
            if crashed is None: continue

            obs = {
                'token_id': tid, 'date': date,
                'score': result['score'], 'level': result['level'],
                'ndd_v4': result['ndd_v4'], 'crashed': crashed,
                'internal': result['internal'], 'external': result['external'],
                'network': result['network'],
                'n_pct_fall': result['explain'].get('n_pct_fall', 0),
                'tier': result['explain'].get('tier', 0),
            }
            all_obs.append(obs)
            scored += 1

        if wi % prog == 0:
            print(f"    scored={scored}")

    print(f"\n\n  Total: {len(all_obs)}")
    is_obs = [o for o in all_obs if o['date'] <= IS_CUTOFF]
    oos_obs = [o for o in all_obs if o['date'] >= OOS_START]
    print(f"  IS={len(is_obs)} OOS={len(oos_obs)}")

    is_auc = evaluate(is_obs, "IN-SAMPLE (2021-2023)")
    oos_auc = evaluate(oos_obs, "OUT-OF-SAMPLE (2024-2026)")

    # Compare old NDD
    print(f"\n  {'═'*70}")
    print(f"  COMPARISON vs OLD NDD v3.1")
    print(f"  {'═'*70}")

    conn = sqlite3.connect(DB_PATH)
    ndd_rows = conn.execute("SELECT token_id, week_date, ndd FROM crypto_ndd_history").fetchall()
    conn.close()
    ndd_map = {(t,w): n for t,w,n in ndd_rows}

    for label, obs in [("IS", is_obs), ("OOS", oos_obs)]:
        matched = []
        for o in obs:
            tid, od = o['token_id'], datetime.strptime(o['date'],"%Y-%m-%d")
            for delta in range(4):
                for sign in [0,-1,1]:
                    ck = (od+timedelta(days=sign*delta)).strftime("%Y-%m-%d")
                    if (tid,ck) in ndd_map:
                        matched.append((o['score'], 5.0-ndd_map[(tid,ck)], o['crashed']))
                        break
                else: continue
                break

        if len(matched) >= 50:
            ce = compute_auc([m[0] for m in matched], [m[2] for m in matched])
            old = compute_auc([m[1] for m in matched], [m[2] for m in matched])
            print(f"  {label} (n={len(matched)}): CE={ce:.3f} vs NDD={old:.3f} Δ={ce-old:+.3f}")

    # Latest snapshot
    if all_obs:
        latest = max(o['date'] for o in all_obs)
        lo = sorted([o for o in all_obs if o['date']==latest], key=lambda x: x['score'], reverse=True)
        print(f"\n  LATEST: {latest}")
        print(f"  {'Token':<25} {'Score':>6} {'Lv':<10} {'Int':>5} {'Ext':>5} {'Net':>5} {'Tier':>4}")
        print(f"  {'─'*62}")
        for o in lo[:10]:
            print(f"  {o['token_id'][:25]:<25} {o['score']:>5.1f} {o['level']:<10} "
                  f"{o['internal']:>5.1f} {o['external']:>5.1f} {o['network']:>5.1f} {o.get('tier','?'):>4}")
        print(f"  ...")
        for o in lo[-5:]:
            print(f"  {o['token_id'][:25]:<25} {o['score']:>5.1f} {o['level']:<10} "
                  f"{o['internal']:>5.1f} {o['external']:>5.1f} {o['network']:>5.1f} {o.get('tier','?'):>4}")

    # Verdict
    print(f"\n  {'═'*70}")
    print(f"  VERDICT: OOS AUC={oos_auc:.3f}")
    if oos_auc >= 0.78: print(f"  🎯 STRONG")
    elif oos_auc >= 0.72: print(f"  ✅ GOOD")
    elif oos_auc >= 0.65: print(f"  ⚠️  DECENT")
    else: print(f"  ❌ NEEDS WORK")

    # Save
    json.dump({'v':'1.2','is_auc':is_auc,'oos_auc':oos_auc,'n':len(all_obs)},
              open(os.path.join(SCRIPT_DIR,"contagion_engine_results.json"),'w'), indent=2)
    print(f"  Done.")

if __name__ == "__main__":
    main()
