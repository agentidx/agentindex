#!/usr/bin/env python3
"""
NERQ Crash Prediction Model v3
================================
Extends v2 (16 features, AUC 0.708 OOS) with DeFiLlama-derived features.
Target: improve "never-recover" detection from 63% → 80%+.

DB Schema (verified 2026-02-28):
  crypto_ndd_daily: run_date, token_id, ndd, signal_1..signal_7
  crypto_rating_daily: run_date, token_id, score, pillar_1..pillar_5
  crypto_price_history: token_id, date, close, volume
  defi_tvl_history: protocol_id, date, tvl_usd
  defi_protocol_tokens: token_id, protocol_id, audit_count, category, forked_from, listed_at, chains
  defi_stablecoin_flows: chain, date, total_circulating
  defi_yields: pool_id, chain, project, symbol, apy, tvl_usd
"""

import sqlite3
import json
import math
import os
from datetime import datetime, timedelta
from collections import defaultdict

# ─── CONFIG ──────────────────────────────────────────────────────────────────

DB_MAIN = os.path.expanduser("~/agentindex/agentindex/crypto/crypto_trust.db")
DB_REF = os.path.expanduser("~/agentindex/agentindex/data/crypto_trust.db")

IS_START = "2021-01-01"
IS_END = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END = "2026-02-28"

CRASH_THRESHOLD = 0.30
CRASH_WINDOW_DAYS = 90
PREDICTION_FREQUENCY = 7

CATEGORY_RISK = {
    "Algo-Stables": 1.0, "Yield Aggregator": 0.85, "Derivatives": 0.8,
    "Yield": 0.8, "Leveraged Farming": 0.9, "Options": 0.75,
    "Synthetics": 0.8, "Bridge": 0.7, "Cross Chain": 0.7,
    "DEX": 0.5, "Lending": 0.45, "Liquid Staking": 0.4,
    "CDP": 0.5, "NFT Lending": 0.7, "RWA": 0.35,
    "CEX": 0.2, "Chain": 0.3, "Payments": 0.3,
    "Privacy": 0.6, "Launchpad": 0.65, "Gaming": 0.7,
    "Prediction Market": 0.65, "Insurance": 0.35, "Indexes": 0.4,
    "Staking Pool": 0.35,
}
DEFAULT_CATEGORY_RISK = 0.5

SEVERITY_LEVELS = {
    "mild":          (-0.50, -0.30),
    "severe":        (-0.70, -0.50),
    "catastrophic":  (-0.90, -0.70),
    "terminal":      (-1.00, -0.90),
}


# ─── UTILITIES ───────────────────────────────────────────────────────────────

def wilson_ci(successes, total, z=1.96):
    if total == 0:
        return 0.0, 0.0, 0.0
    p = successes / total
    denom = 1 + z*z/total
    centre = (p + z*z/(2*total)) / denom
    margin = z * math.sqrt((p*(1-p) + z*z/(4*total)) / total) / denom
    return p, max(0, centre - margin), min(1, centre + margin)


def sigmoid(x):
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    else:
        ex = math.exp(x)
        return ex / (1 + ex)


def auc_manual(labels, scores):
    pos = [s for s, l in zip(scores, labels) if l == 1]
    neg = [s for s, l in zip(scores, labels) if l == 0]
    if not pos or not neg:
        return 0.5
    concordant = 0
    tied = 0
    for ps in pos:
        for ns in neg:
            if ps > ns:
                concordant += 1
            elif ps == ns:
                tied += 0.5
    return (concordant + tied) / (len(pos) * len(neg))


def find_closest(lookup_dict, target_date, max_days=7):
    for offset in range(max_days + 1):
        check = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=offset)).strftime("%Y-%m-%d")
        if check in lookup_dict:
            return lookup_dict[check]
    return None


# ─── STEP 0: LOAD V2 MODEL ──────────────────────────────────────────────────

def load_v2_model(db_dir):
    path = os.path.join(db_dir, "crash_model_v2.json")
    if not os.path.exists(path):
        print("[INFO] crash_model_v2.json not found — training v2 from scratch")
        return None
    with open(path) as f:
        m = json.load(f)
    print(f"[OK] V2 reference: {len(m.get('feature_names',[]))} features, OOS AUC={m.get('oos_auc','N/A')}")
    return m


# ─── STEP 1: TVL FEATURES ───────────────────────────────────────────────────

def build_tvl_features(conn):
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT token_id, protocol_id FROM defi_protocol_tokens WHERE token_id IS NOT NULL AND token_id != ''")
    token_protocol = defaultdict(list)
    for tid, pid in cur.fetchall():
        token_protocol[tid].append(pid)
    print(f"[Step 1] {len(token_protocol)} tokens mapped to protocols")

    cur.execute("SELECT protocol_id, date, tvl_usd FROM defi_tvl_history ORDER BY protocol_id, date")
    tvl_by_proto = defaultdict(dict)
    for pid, d, tvl in cur.fetchall():
        tvl_by_proto[pid][d] = tvl

    cur.execute("SELECT token_id, date, close FROM crypto_price_history WHERE close > 0 ORDER BY token_id, date")
    price_by_tok = defaultdict(dict)
    for tid, d, c in cur.fetchall():
        price_by_tok[tid][d] = c

    features = {}
    for token_id, pids in token_protocol.items():
        tvl_dates = {}
        for pid in pids:
            for d, tvl in tvl_by_proto.get(pid, {}).items():
                tvl_dates[d] = tvl_dates.get(d, 0) + tvl
        if not tvl_dates:
            continue

        sorted_d = sorted(tvl_dates.keys())
        prices = price_by_tok.get(token_id, {})
        first = datetime.strptime(sorted_d[0], "%Y-%m-%d")
        last = datetime.strptime(sorted_d[-1], "%Y-%m-%d")
        cur_dt = first + timedelta(days=90)

        while cur_dt <= last:
            ds = cur_dt.strftime("%Y-%m-%d")
            tvl_now = None
            for off in range(4):
                ck = (cur_dt - timedelta(days=off)).strftime("%Y-%m-%d")
                if ck in tvl_dates:
                    tvl_now = tvl_dates[ck]; break
            if not tvl_now or tvl_now <= 0:
                cur_dt += timedelta(days=PREDICTION_FREQUENCY); continue

            tvl_7d = None
            for off in range(4):
                ck = (cur_dt - timedelta(days=7+off)).strftime("%Y-%m-%d")
                if ck in tvl_dates: tvl_7d = tvl_dates[ck]; break

            tvl_30d = None
            for off in range(4):
                ck = (cur_dt - timedelta(days=30+off)).strftime("%Y-%m-%d")
                if ck in tvl_dates: tvl_30d = tvl_dates[ck]; break

            tvl_90h = max((tvl_dates.get((cur_dt - timedelta(days=i)).strftime("%Y-%m-%d"), 0) for i in range(91)), default=0)

            f = {}
            f["tvl_momentum_7d"] = (tvl_now - tvl_7d) / tvl_7d if tvl_7d and tvl_7d > 0 else 0.0
            f["tvl_momentum_30d"] = (tvl_now - tvl_30d) / tvl_30d if tvl_30d and tvl_30d > 0 else 0.0
            f["tvl_drawdown"] = (tvl_now - tvl_90h) / tvl_90h if tvl_90h > 0 else 0.0

            pn = None
            for off in range(4):
                ck = (cur_dt - timedelta(days=off)).strftime("%Y-%m-%d")
                if ck in prices: pn = prices[ck]; break
            p30 = None
            for off in range(4):
                ck = (cur_dt - timedelta(days=30+off)).strftime("%Y-%m-%d")
                if ck in prices: p30 = prices[ck]; break

            if pn and p30 and p30 > 0:
                f["tvl_vs_price_divergence"] = f["tvl_momentum_30d"] - (pn - p30) / p30
            else:
                f["tvl_vs_price_divergence"] = 0.0

            features[(token_id, ds)] = f
            cur_dt += timedelta(days=PREDICTION_FREQUENCY)

    print(f"[Step 1] {len(features)} (token,date) TVL feature rows")
    return features, set(token_protocol.keys())


# ─── STEP 2: STRUCTURAL FEATURES ────────────────────────────────────────────

def build_structural_features(conn):
    cur = conn.cursor()
    cur.execute("SELECT token_id, audit_count, forked_from, category, listed_at, chains FROM defi_protocol_tokens WHERE token_id IS NOT NULL AND token_id != ''")
    struct = {}
    for tid, audit, forked, cat, listed, chains in cur.fetchall():
        f = {
            "has_audit": 1.0 if (audit or 0) > 0 else 0.0,
            "is_fork": 1.0 if (forked or "").strip() else 0.0,
            "category_risk": CATEGORY_RISK.get(cat or "", DEFAULT_CATEGORY_RISK),
            "listed_at": listed,
            "primary_chain": (chains or "").split(",")[0].strip(),
        }
        if tid not in struct or f["has_audit"] > struct[tid]["has_audit"]:
            struct[tid] = f
    print(f"[Step 2] {len(struct)} tokens, {sum(1 for v in struct.values() if v['has_audit'])} audited")
    return struct


def protocol_age_years(sf, ds):
    la = sf.get("listed_at")
    if not la: return 0.0
    try:
        if isinstance(la, (int, float)):
            ld = datetime.fromtimestamp(la)
        else:
            ld = datetime.strptime(str(la)[:10], "%Y-%m-%d")
        return max(0, (datetime.strptime(ds, "%Y-%m-%d") - ld).days) / 365.0
    except:
        return 0.0


# ─── STEP 3: STABLECOIN FLOW ────────────────────────────────────────────────

def build_stablecoin_features(conn_main, conn_ref):
    cur = conn_main.cursor()
    cur.execute("SELECT chain, date, total_circulating FROM defi_stablecoin_flows ORDER BY chain, date")
    sbc = defaultdict(dict)
    for ch, d, circ in cur.fetchall():
        sbc[ch.lower()][d] = circ
    print(f"[Step 3] {len(sbc)} chains with stablecoin data")

    stable_lookup = {}
    for chain, dv in sbc.items():
        for ds in sorted(dv.keys()):
            vn = dv[ds]
            tgt = (datetime.strptime(ds, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
            v30 = None
            for off in range(7):
                ck = (datetime.strptime(tgt, "%Y-%m-%d") + timedelta(days=off)).strftime("%Y-%m-%d")
                if ck in dv: v30 = dv[ck]; break
            if v30 and v30 > 0 and vn:
                stable_lookup[(chain, ds)] = (vn - v30) / v30

    token_chain = {}
    try:
        cr = conn_ref.cursor()
        cr.execute("SELECT token_id, chain FROM crypto_token_ecosystem_v2 WHERE chain IS NOT NULL")
        for tid, ch in cr.fetchall():
            token_chain[tid] = ch.lower()
        print(f"[Step 3] {len(token_chain)} tokens → chains")
    except Exception as e:
        print(f"[Step 3] Chain mapping failed: {e}")

    return stable_lookup, token_chain


# ─── STEP 4: YIELD ANOMALY ──────────────────────────────────────────────────

def build_yield_features(conn):
    cur = conn.cursor()
    yf = {}
    try:
        cur.execute("""SELECT dpt.token_id, MAX(dy.apy) FROM defi_yields dy
            JOIN defi_protocol_tokens dpt ON LOWER(dy.project) = LOWER(dpt.protocol_id)
            WHERE dy.apy > 0 GROUP BY dpt.token_id""")
        for tid, apy in cur.fetchall():
            if tid: yf[tid] = min(apy, 10000)
    except: pass

    if len(yf) < 10:
        print(f"[Step 4] Direct join: {len(yf)}, trying fuzzy...")
        try:
            cur.execute("SELECT project, MAX(apy) FROM defi_yields WHERE apy > 0 GROUP BY project")
            pa = {r[0].lower(): r[1] for r in cur.fetchall()}
            cur.execute("SELECT token_id, protocol_id FROM defi_protocol_tokens WHERE token_id IS NOT NULL")
            for tid, pid in cur.fetchall():
                if pid and pid.lower() in pa and tid not in yf:
                    yf[tid] = min(pa[pid.lower()], 10000)
        except: pass

    print(f"[Step 4] {len(yf)} tokens with yield data ({sum(1 for v in yf.values() if v > 100)} APY>100%)")
    return yf


# ─── STEP 5a: V2 BASE FEATURES ──────────────────────────────────────────────

def build_v2_features(conn):
    cur = conn.cursor()

    print("[Step 5a] Loading NDD (run_date, ndd, signal_1..7)...")
    cur.execute("""SELECT token_id, run_date, ndd,
        signal_1, signal_2, signal_3, signal_4, signal_5, signal_6, signal_7
        FROM crypto_ndd_daily ORDER BY token_id, run_date""")
    ndd = defaultdict(dict)
    for row in cur.fetchall():
        ndd[row[0]][row[1]] = {
            "ndd": row[2] or 0,
            "sig_liq": row[3] or 0, "sig_hold": row[4] or 0, "sig_res": row[5] or 0,
            "sig_fund": row[6] or 0, "sig_cont": row[7] or 0, "sig_str": row[8] or 0, "sig_rel": row[9] or 0,
        }
    print(f"         NDD: {len(ndd)} tokens")

    print("[Step 5a] Loading ratings (run_date, pillar_1..5)...")
    cur.execute("""SELECT token_id, run_date, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5
        FROM crypto_rating_daily ORDER BY token_id, run_date""")
    trust = defaultdict(dict)
    for row in cur.fetchall():
        trust[row[0]][row[1]] = {
            "score": row[2] or 50,
            "p1_eco": row[3] or 50, "p2_cont": row[4] or 50, "p3_res": row[5] or 50,
            "p4_fund": row[6] or 50, "p5_rug": row[7] or 50,
        }
    print(f"         Trust: {len(trust)} tokens")

    print("[Step 5a] Loading prices...")
    cur.execute("SELECT token_id, date, close, volume FROM crypto_price_history WHERE close > 0 ORDER BY token_id, date")
    prices = defaultdict(list)
    for tid, d, c, v in cur.fetchall():
        prices[tid].append((d, c, v or 0))
    print(f"         Price: {len(prices)} tokens")

    tokens = set(ndd.keys()) & set(prices.keys())
    print(f"[Step 5a] Building for {len(tokens)} tokens...")

    dataset = {}
    for tid in tokens:
        pl = prices[tid]
        if len(pl) < 90: continue
        ndd_l = ndd[tid]
        trust_l = trust.get(tid, {})

        for idx in range(90, len(pl), PREDICTION_FREQUENCY):
            ds = pl[idx][0]
            pn = pl[idx][1]

            # Crash label
            end = min(idx + CRASH_WINDOW_DAYS, len(pl))
            if end - idx < 14: continue
            future = [p for _, p, _ in pl[idx:end]]
            mdd = min((p - pn) / pn for p in future[1:]) if len(future) > 1 else 0
            crash = 1 if mdd <= -CRASH_THRESHOLD else 0

            ft = {}

            # Price features
            p90 = [p for _, p, _ in pl[max(0,idx-90):idx+1]]
            pk = max(p90) if p90 else pn
            ft["drawdown_90d"] = (pn - pk) / pk if pk > 0 else 0

            p30 = [p for _, p, _ in pl[max(0,idx-30):idx+1]]
            if len(p30) > 5:
                rets = [(p30[j]-p30[j-1])/p30[j-1] for j in range(1,len(p30)) if p30[j-1]>0]
                if rets:
                    mu = sum(rets)/len(rets)
                    ft["volatility_30d"] = math.sqrt(sum((r-mu)**2 for r in rets)/len(rets))
                else: ft["volatility_30d"] = 0
            else: ft["volatility_30d"] = 0

            ft["momentum_30d"] = (pn - pl[idx-30][1]) / pl[idx-30][1] if idx >= 30 and pl[idx-30][1] > 0 else 0

            vn = pl[idx][2]
            v30 = pl[max(0,idx-30)][2]
            ft["volume_change_30d"] = (vn - v30) / v30 if v30 > 0 else 0

            # NDD
            n = find_closest(ndd_l, ds, 7)
            if n:
                ft["ndd_score"] = n["ndd"]
                ft["sig_cont"] = n["sig_cont"]
                ft["sig_res"] = n["sig_res"]
                ft["sig_liq"] = n["sig_liq"]
            else:
                ft["ndd_score"] = ft["sig_cont"] = ft["sig_res"] = ft["sig_liq"] = 0

            # Trust
            t = find_closest(trust_l, ds, 14)
            if t:
                ft["trust_p1_security"] = t["p5_rug"]
                ft["trust_p3_maintenance"] = t["p3_res"]
                ft["trust_p5_ecosystem"] = t["p1_eco"]
            else:
                ft["trust_p1_security"] = ft["trust_p3_maintenance"] = ft["trust_p5_ecosystem"] = 50

            # Interactions
            ft["ix_drawdown_x_cont"] = ft["drawdown_90d"] * ft["sig_cont"]
            ft["ix_vol_x_ndd"] = ft["volatility_30d"] * ft["ndd_score"]
            ft["ix_momentum_x_liq"] = ft["momentum_30d"] * ft["sig_liq"]
            ft["ix_trust_x_drawdown"] = ft["trust_p3_maintenance"] * ft["drawdown_90d"]

            # Thresholds
            ft["drawdown_severe"] = 1.0 if ft["drawdown_90d"] < -0.5 else 0.0
            ft["ndd_high_distress"] = 1.0 if ft["ndd_score"] > 70 else 0.0
            ft["vol_extreme"] = 1.0 if ft["volatility_30d"] > 0.1 else 0.0
            ft["trust_low"] = 1.0 if ft["trust_p3_maintenance"] < 30 else 0.0

            ft["_crash_label"] = crash
            ft["_max_dd"] = mdd
            dataset[(tid, ds)] = ft

    crashes = sum(1 for v in dataset.values() if v["_crash_label"] == 1)
    print(f"[Step 5a] {len(dataset)} obs, {crashes} crashes ({100*crashes/max(1,len(dataset)):.1f}%)")
    return dataset


# ─── STEP 5b: MERGE ─────────────────────────────────────────────────────────

def merge_all(v2ds, tvl_f, tvl_tok, struct_f, stable_l, tok_chain, yield_f):
    ds = {}
    tvl_m = 0
    for (tid, d), ft in v2ds.items():
        f = dict(ft)
        tvl = tvl_f.get((tid, d))
        if tvl:
            f.update(tvl); f["has_tvl_data"] = 1.0; tvl_m += 1
        else:
            f["tvl_momentum_7d"] = f["tvl_momentum_30d"] = f["tvl_drawdown"] = f["tvl_vs_price_divergence"] = 0.0
            f["has_tvl_data"] = 0.0

        sf = struct_f.get(tid)
        if sf:
            f["has_audit"] = sf["has_audit"]; f["is_fork"] = sf["is_fork"]
            f["category_risk"] = sf["category_risk"]; f["protocol_age_days"] = protocol_age_years(sf, d)
        else:
            f["has_audit"] = f["is_fork"] = 0.0; f["category_risk"] = DEFAULT_CATEGORY_RISK; f["protocol_age_days"] = 0.0

        ch = tok_chain.get(tid, "")
        sv = 0.0
        if ch:
            for off in range(7):
                ck = (datetime.strptime(d, "%Y-%m-%d") - timedelta(days=off)).strftime("%Y-%m-%d")
                if (ch, ck) in stable_l: sv = stable_l[(ch, ck)]; break
        f["chain_stablecoin_change_30d"] = sv

        apy = yield_f.get(tid, 0)
        f["yield_anomaly"] = 1.0 if apy > 100 else (apy / 100.0 if apy > 0 else 0.0)

        f["ix_tvl_div_x_trust"] = f["tvl_vs_price_divergence"] * (100 - f["trust_p3_maintenance"]) / 100
        f["ix_no_audit_x_drawdown"] = (1 - f["has_audit"]) * abs(f["drawdown_90d"])

        ds[(tid, d)] = f
    print(f"[Step 5b] {len(ds)} obs, TVL matched: {tvl_m} ({100*tvl_m/max(1,len(ds)):.1f}%)")
    return ds


# ─── LOGISTIC REGRESSION ────────────────────────────────────────────────────

V3_FEATURES = [
    "drawdown_90d", "volatility_30d", "momentum_30d", "volume_change_30d",
    "ndd_score", "sig_cont", "sig_res", "sig_liq",
    "trust_p1_security", "trust_p3_maintenance", "trust_p5_ecosystem",
    "ix_drawdown_x_cont", "ix_vol_x_ndd", "ix_momentum_x_liq", "ix_trust_x_drawdown",
    "drawdown_severe", "ndd_high_distress", "vol_extreme", "trust_low",
    "tvl_momentum_7d", "tvl_momentum_30d", "tvl_drawdown", "tvl_vs_price_divergence", "has_tvl_data",
    "has_audit", "is_fork", "category_risk", "protocol_age_days",
    "chain_stablecoin_change_30d", "yield_anomaly",
    "ix_tvl_div_x_trust", "ix_no_audit_x_drawdown",
]
V2_FEATURES = V3_FEATURES[:19]


def train(dataset, fnames, period="IS"):
    if period == "IS":
        data = {k: v for k, v in dataset.items() if IS_START <= k[1] <= IS_END}
    else:
        data = {k: v for k, v in dataset.items() if OOS_START <= k[1] <= OOS_END}
    if not data:
        print(f"[TRAIN] No data for {period}!"); return None

    X = [[ft.get(fn, 0.0) or 0.0 for fn in fnames] for ft in data.values()]
    y = [ft["_crash_label"] for ft in data.values()]
    n, d = len(X), len(fnames)
    print(f"[TRAIN {period}] n={n}, d={d}, crash={sum(y)/n:.3f}")

    means = [sum(X[i][j] for i in range(n))/n for j in range(d)]
    stds = [max(1e-8, math.sqrt(sum((X[i][j]-means[j])**2 for i in range(n))/n)) for j in range(d)]
    Xs = [[(X[i][j]-means[j])/stds[j] for j in range(d)] for i in range(n)]

    w = [0.0]*d; b = 0.0; lr = 0.01; reg = 0.001
    for ep in range(500):
        pr = [sigmoid(sum(w[j]*Xs[i][j] for j in range(d))+b) for i in range(n)]
        gw = [0.0]*d; gb = 0.0
        for i in range(n):
            e = pr[i]-y[i]
            for j in range(d): gw[j] += e*Xs[i][j]/n + reg*w[j]
            gb += e/n
        for j in range(d): w[j] -= lr*gw[j]
        b -= lr*gb
        if ep == 200: lr = 0.005
        if ep == 350: lr = 0.002

    pr = [sigmoid(sum(w[j]*Xs[i][j] for j in range(d))+b) for i in range(n)]
    a = auc_manual(y, pr)
    print(f"[TRAIN {period}] AUC: {a:.4f}")
    return {"weights":w, "bias":b, "feature_means":means, "feature_stds":stds,
            "feature_names":fnames, "auc":a, "n":n, "crash_rate":sum(y)/n}


def pred(model, ft):
    w, b, m, s, fn = model["weights"], model["bias"], model["feature_means"], model["feature_stds"], model["feature_names"]
    x = [(ft.get(n,0.0)-m[i])/s[i] for i,n in enumerate(fn)]
    return sigmoid(sum(w[i]*x[i] for i in range(len(w)))+b)


# ─── STEP 6: SEVERITY ───────────────────────────────────────────────────────

def severity(dataset, model, period="OOS", label=""):
    if period == "IS":
        data = {k:v for k,v in dataset.items() if IS_START <= k[1] <= IS_END}
    else:
        data = {k:v for k,v in dataset.items() if OOS_START <= k[1] <= OOS_END}
    if not data: print(f"[SEV {period}] No data!"); return

    res = [{"tid":k[0],"d":k[1],"prob":pred(model,v),"mdd":v["_max_dd"],"crash":v["_crash_label"],"tvl":v.get("has_tvl_data",0)} for k,v in data.items()]

    print(f"\n{'='*70}\nSEVERITY — {label or period} (n={len(res)})\n{'='*70}")
    for th in [0.3, 0.4, 0.5]:
        print(f"\n--- Threshold >{th:.0%} ---")
        for sn, (lo, hi) in SEVERITY_LEVELS.items():
            obs = [r for r in res if lo < r["mdd"] <= hi]
            if not obs: continue
            c = sum(1 for r in obs if r["prob"] > th)
            rate, cl, ch2 = wilson_ci(c, len(obs))
            print(f"  {sn:15s}: {c:>4}/{len(obs):<4} = {rate:>6.1%} [{cl:.1%}, {ch2:.1%}]")
        nr = [r for r in res if r["mdd"] <= -0.80]
        if nr:
            c = sum(1 for r in nr if r["prob"] > th)
            rate, cl, ch2 = wilson_ci(c, len(nr))
            print(f"  {'never-recover':15s}: {c:>4}/{len(nr):<4} = {rate:>6.1%} [{cl:.1%}, {ch2:.1%}]")

    print(f"\n--- TVL Impact (>40%, crashes only) ---")
    for ht, lb in [(1,"WITH TVL"),(0,"NO TVL")]:
        sub = [r for r in res if r["tvl"]==ht and r["crash"]==1]
        if sub:
            c = sum(1 for r in sub if r["prob"] > 0.4)
            rate, _, _ = wilson_ci(c, len(sub))
            print(f"  {lb:12s}: {c}/{len(sub)} = {rate:.1%}")


def feat_importance(model):
    new = {"tvl_momentum_7d","tvl_momentum_30d","tvl_drawdown","tvl_vs_price_divergence",
           "has_tvl_data","has_audit","is_fork","category_risk","protocol_age_days",
           "chain_stablecoin_change_30d","yield_anomaly","ix_tvl_div_x_trust","ix_no_audit_x_drawdown"}
    imp = sorted([(abs(w),w,n) for w,n in zip(model["weights"],model["feature_names"])], reverse=True)
    tot = sum(i for i,_,_ in imp)
    print(f"\nFEATURE IMPORTANCE (top 15):")
    print(f"{'#':>3} {'Feature':35s} {'Wt':>8} {'%':>6}")
    print("-"*58)
    for i,(a,w,n) in enumerate(imp[:15]):
        s = "+" if w > 0 else "-"
        st = " ★" if n in new else ""
        print(f"{i+1:>3} {n:35s} {s}{a:.4f} {100*a/tot:>5.1f}%{st}")
    print("★ = new v3 feature")


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    print("="*70)
    print("NERQ CRASH PREDICTION MODEL v3")
    print("="*70)
    print(f"IS: {IS_START} → {IS_END}  |  OOS: {OOS_START} → {OOS_END}\n")

    conn = sqlite3.connect(DB_MAIN)
    try: conn_ref = sqlite3.connect(DB_REF)
    except: print("[WARN] No ref DB"); conn_ref = conn

    load_v2_model(os.path.dirname(DB_MAIN))

    print("\n" + "─"*50 + "\nSTEP 1: TVL\n" + "─"*50)
    tvl_f, tvl_t = build_tvl_features(conn)

    print("\n" + "─"*50 + "\nSTEP 2: STRUCTURAL\n" + "─"*50)
    struct_f = build_structural_features(conn)

    print("\n" + "─"*50 + "\nSTEP 3: STABLECOIN\n" + "─"*50)
    stable_l, tok_ch = build_stablecoin_features(conn, conn_ref)

    print("\n" + "─"*50 + "\nSTEP 4: YIELD\n" + "─"*50)
    yield_f = build_yield_features(conn)

    print("\n" + "─"*50 + "\nSTEP 5: BUILD + TRAIN\n" + "─"*50)
    v2ds = build_v2_features(conn)
    v3ds = merge_all(v2ds, tvl_f, tvl_t, struct_f, stable_l, tok_ch, yield_f)

    print("\n" + "="*70 + "\nMODEL COMPARISON\n" + "="*70)
    print("\n--- V2 (19 features) ---")
    v2m = train(v3ds, V2_FEATURES, "IS")
    print("\n--- V3 (32 features) ---")
    v3m = train(v3ds, V3_FEATURES, "IS")

    if not v2m or not v3m:
        print("[FATAL] Training failed!"); conn.close(); return

    oos = {k:v for k,v in v3ds.items() if OOS_START <= k[1] <= OOS_END}
    v2p = [pred(v2m,f) for f in oos.values()]
    v3p = [pred(v3m,f) for f in oos.values()]
    lab = [f["_crash_label"] for f in oos.values()]

    v2a = auc_manual(lab, v2p)
    v3a = auc_manual(lab, v3p)

    print(f"\n{'='*50}")
    print(f"  V2  IS: {v2m['auc']:.4f}  |  OOS: {v2a:.4f}")
    print(f"  V3  IS: {v3m['auc']:.4f}  |  OOS: {v3a:.4f}")
    print(f"  Δ OOS: {v3a - v2a:+.4f}")
    print(f"  {'✅ V3 BEATS V2' if v3a > v2a else '⚠️  V3 does NOT beat V2'}")
    print(f"{'='*50}")

    feat_importance(v3m)

    print("\n" + "─"*50 + "\nSTEP 6: SEVERITY\n" + "─"*50)
    severity(v3ds, v3m, "IS", "V3 IN-SAMPLE")
    severity(v3ds, v3m, "OOS", "V3 OOS")
    severity(v3ds, v2m, "OOS", "V2 OOS (baseline)")

    v3m["oos_auc"] = v3a; v3m["is_auc"] = v3m["auc"]
    mp = os.path.join(os.path.dirname(DB_MAIN), "crash_model_v3.json")
    with open(mp, "w") as f: json.dump(v3m, f, indent=2)
    print(f"\n[SAVED] {mp}")

    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS crash_model_v3_predictions (
        token_id TEXT, date TEXT, crash_prob_v3 REAL, crash_prob_v2 REAL,
        crash_label INTEGER, max_drawdown REAL, has_tvl_data INTEGER, period TEXT,
        PRIMARY KEY (token_id, date))""")
    cur.execute("DELETE FROM crash_model_v3_predictions")
    rows = [(k[0],k[1],pred(v3m,v),pred(v2m,v),v["_crash_label"],v["_max_dd"],
             int(v.get("has_tvl_data",0)),"IS" if IS_START<=k[1]<=IS_END else "OOS")
            for k,v in v3ds.items()]
    cur.executemany("INSERT OR REPLACE INTO crash_model_v3_predictions VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"[DB] {len(rows)} predictions saved")

    print(f"\n{'='*70}\nDONE\n{'='*70}")
    conn.close()
    if conn_ref != conn: conn_ref.close()

if __name__ == "__main__":
    main()
