#!/usr/bin/env python3
"""
NERQ — DEEP PERFORMANCE ANALYSIS
===================================
Answers:
  1. When we predict a crash, how much more does it fall?
  2. How much has already dropped when we trigger?
  3. When we're WRONG (false positive), what actually happens?
  4. Compare our metrics to published benchmarks

Uses crash_model_v2 (our best: AUC 0.71) on the full dataset.
"""

import sqlite3
import os
import json
import numpy as np
from datetime import datetime, timedelta
from math import sqrt, exp
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")
IS_CUTOFF = "2023-12-31"
OOS_START = "2024-01-01"

# Load model
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash_model_v2.json")


def load_model():
    with open(MODEL_PATH) as f:
        m = json.load(f)
    return m

def sigmoid(z):
    z = max(-500, min(500, z))
    return 1.0 / (1.0 + exp(-z))

def predict(feat_vec, model):
    w = model['weights']
    b = model['bias']
    means = model['feature_means']
    stds = model['feature_stds']
    n = len(w)
    z = b + sum(w[j] * (feat_vec[j] - means[j]) / stds[j] for j in range(n))
    return sigmoid(z)


def get_idx(series, date, key='date'):
    lo, hi = 0, len(series)-1; r = None
    while lo <= hi:
        mid = (lo+hi)//2
        if series[mid][key] <= date: r = mid; lo = mid+1
        else: hi = mid-1
    return r


def main():
    print("="*80)
    print("  NERQ — DEEP PERFORMANCE ANALYSIS")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    model = load_model()
    features = model['features']
    print(f"  Model: {model.get('version','?')}, {len(features)} features")

    conn = sqlite3.connect(DB_PATH)

    # Load all data
    print("  Loading data...")
    price_rows = conn.execute("""
        SELECT token_id, date, close FROM crypto_price_history
        WHERE close > 0 ORDER BY token_id, date
    """).fetchall()

    prices = defaultdict(list)
    for tid, d, c in price_rows:
        prices[tid].append({'date': d, 'close': c})
    prices = dict(prices)

    ndd_rows = conn.execute("""
        SELECT token_id, week_date, ndd, signal_3, signal_5, signal_6
        FROM crypto_ndd_history WHERE ndd IS NOT NULL
        ORDER BY token_id, week_date
    """).fetchall()

    ndd = defaultdict(list)
    for tid, wd, n, s3, s5, s6 in ndd_rows:
        ndd[tid].append({'date': wd, 'ndd': n, 'sig3': s3, 'sig5': s5, 'sig6': s6})

    rat_rows = conn.execute("""
        SELECT token_id, year_month, pillar_3
        FROM crypto_rating_history WHERE pillar_3 IS NOT NULL
        ORDER BY token_id, year_month
    """).fetchall()

    ratings = defaultdict(list)
    for tid, ym, p3 in rat_rows:
        ratings[tid].append({'ym': ym, 'p3': p3})

    conn.close()

    # Compute vol 90th from IS
    print("  Computing vol threshold...")
    is_vols = []
    for tid in ndd:
        if tid not in prices: continue
        tp = prices[tid]
        for obs in ndd[tid]:
            if obs['date'] > IS_CUTOFF: continue
            idx = get_idx(tp, obs['date'])
            if idx and idx >= 30:
                rets = []
                for i in range(idx-29, idx+1):
                    if i > 0 and tp[i-1]['close'] > 0:
                        rets.append((tp[i]['close']-tp[i-1]['close'])/tp[i-1]['close'])
                if len(rets) >= 20:
                    m = sum(rets)/len(rets)
                    v = sum((r-m)**2 for r in rets)/len(rets)
                    is_vols.append(sqrt(v)*sqrt(365))
    is_vols.sort()
    vol_90th = is_vols[int(len(is_vols)*0.9)] if is_vols else 2.0

    # Build predictions with detailed forward price paths
    print("  Building predictions with forward paths...")

    results = []
    btc = prices.get('bitcoin', [])

    for tid in sorted(ndd.keys()):
        if tid not in prices: continue
        tp = prices[tid]

        for obs in ndd[tid]:
            date = obs['date']
            idx = get_idx(tp, date)
            if not idx or idx < 90: continue

            close = tp[idx]['close']
            if close <= 0: continue

            # ── Compute features (same as crash_model_v2) ──────────────
            # vol_30d
            if idx < 30: continue
            rets = []
            for i in range(idx-29, idx+1):
                if i > 0 and tp[i-1]['close'] > 0:
                    rets.append((tp[i]['close']-tp[i-1]['close'])/tp[i-1]['close'])
            if len(rets) < 20: continue
            m = sum(rets)/len(rets); v = sum((r-m)**2 for r in rets)/len(rets)
            vol = sqrt(v)*sqrt(365)

            # drawdown_90d
            high90 = max(tp[i]['close'] for i in range(max(0,idx-89), idx+1))
            dd = (close-high90)/high90 if high90 > 0 else 0

            # btc_vol
            btc_idx = get_idx(btc, date) if btc else None
            if not btc_idx or btc_idx < 30: continue
            b_rets = []
            for i in range(btc_idx-29, btc_idx+1):
                if i > 0 and btc[i-1]['close'] > 0:
                    b_rets.append((btc[i]['close']-btc[i-1]['close'])/btc[i-1]['close'])
            if len(b_rets) < 20: continue
            bm = sum(b_rets)/len(b_rets); bv = sum((r-bm)**2 for r in b_rets)/len(b_rets)
            btc_vol = sqrt(bv)*sqrt(365)

            # NDD signals
            ndd_idx = None
            for i, o in enumerate(ndd[tid]):
                if o['date'] <= date: ndd_idx = i
                else: break
            if ndd_idx is None: continue
            cur = ndd[tid][ndd_idx]
            sig6 = cur.get('sig6') or 0
            sig5 = cur.get('sig5') or 0
            sig3 = cur.get('sig3') or 0
            ndd_min = cur['ndd']
            if ndd_idx >= 4:
                ndd_min = min(ndd[tid][i]['ndd'] for i in range(ndd_idx-3, ndd_idx+1))

            # Trust p3
            if tid not in ratings: continue
            r_idx = get_idx(ratings[tid], date[:7], key='ym')
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

            prob = predict(feat_vec, model)

            # ── Forward price path analysis ──────────────────────────────
            # Track what actually happens 7d, 14d, 30d, 60d, 90d after prediction
            forward = {}
            for horizon in [7, 14, 30, 60, 90]:
                target_d = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=horizon)).strftime("%Y-%m-%d")
                # Find max drop and end price within horizon
                max_drop = 0.0
                end_price = None
                for i in range(idx+1, len(tp)):
                    if tp[i]['date'] > target_d: break
                    d = (tp[i]['close'] - close) / close
                    if d < max_drop: max_drop = d
                    end_price = tp[i]['close']

                if end_price is not None:
                    end_ret = (end_price - close) / close
                    forward[f'max_drop_{horizon}d'] = max_drop
                    forward[f'end_ret_{horizon}d'] = end_ret

            if 'max_drop_90d' not in forward: continue
            crashed = 1 if forward['max_drop_90d'] <= -0.30 else 0

            # How much had already dropped BEFORE this prediction?
            # Look back 7d and 30d
            pre_drop_7d = get_return_simple(tp, idx, 7)
            pre_drop_30d = get_return_simple(tp, idx, 30)

            results.append({
                'token_id': tid,
                'date': date,
                'prob': prob,
                'crashed': crashed,
                'drawdown_90d': dd,
                'vol_30d': vol,
                'pre_drop_7d': pre_drop_7d,
                'pre_drop_30d': pre_drop_30d,
                **forward,
            })

    print(f"  Total predictions: {len(results)}")

    is_res = [r for r in results if r['date'] <= IS_CUTOFF]
    oos_res = [r for r in results if r['date'] >= OOS_START]
    print(f"  IS: {len(is_res)} | OOS: {len(oos_res)}")

    # ══════════════════════════════════════════════════════════════════════════
    # ANALYSIS — OOS ONLY (the real test)
    # ══════════════════════════════════════════════════════════════════════════

    for label, res in [("OUT-OF-SAMPLE (2024-2026)", oos_res)]:
        if len(res) < 100: continue

        print(f"\n  {'═'*75}")
        print(f"  {label} (n={len(res)})")
        print(f"  {'═'*75}")

        # ── Q1: When we predict crash, how much MORE does it fall? ──────
        print(f"\n  Q1: REMAINING DOWNSIDE AFTER PREDICTION")
        print(f"  (How much drop is LEFT after we flag it?)\n")

        for threshold_name, lo, hi in [
            ("LOW RISK (prob <25%)", 0, 0.25),
            ("MODERATE (25-45%)", 0.25, 0.45),
            ("ELEVATED (45-60%)", 0.45, 0.60),
            ("HIGH RISK (60-75%)", 0.60, 0.75),
            ("CRITICAL (>75%)", 0.75, 1.01),
        ]:
            bucket = [r for r in res if lo <= r['prob'] < hi]
            if len(bucket) < 20: continue

            # Future max drops at different horizons
            drops_7 = [r['max_drop_7d'] for r in bucket if 'max_drop_7d' in r]
            drops_30 = [r['max_drop_30d'] for r in bucket if 'max_drop_30d' in r]
            drops_90 = [r['max_drop_90d'] for r in bucket if 'max_drop_90d' in r]
            ends_30 = [r['end_ret_30d'] for r in bucket if 'end_ret_30d' in r]
            ends_90 = [r['end_ret_90d'] for r in bucket if 'end_ret_90d' in r]

            print(f"  {threshold_name} (n={len(bucket)}):")
            if drops_7:  print(f"    Next 7d:  avg max drop {np.mean(drops_7)*100:+.1f}%  median {np.median(drops_7)*100:+.1f}%")
            if drops_30: print(f"    Next 30d: avg max drop {np.mean(drops_30)*100:+.1f}%  median {np.median(drops_30)*100:+.1f}%")
            if drops_90: print(f"    Next 90d: avg max drop {np.mean(drops_90)*100:+.1f}%  median {np.median(drops_90)*100:+.1f}%")
            if ends_30:  print(f"    30d end:  avg return   {np.mean(ends_30)*100:+.1f}%  median {np.median(ends_30)*100:+.1f}%")
            if ends_90:  print(f"    90d end:  avg return   {np.mean(ends_90)*100:+.1f}%  median {np.median(ends_90)*100:+.1f}%")
            print()

        # ── Q2: How much has already dropped when we predict? ───────────
        print(f"\n  Q2: HOW MUCH HAS ALREADY DROPPED AT PREDICTION TIME")
        print(f"  (Are we catching it early or late?)\n")

        for threshold_name, lo, hi in [
            ("LOW RISK", 0, 0.25),
            ("MODERATE", 0.25, 0.45),
            ("ELEVATED", 0.45, 0.60),
            ("HIGH+CRITICAL", 0.60, 1.01),
        ]:
            bucket = [r for r in res if lo <= r['prob'] < hi]
            if len(bucket) < 20: continue

            pre7 = [r['pre_drop_7d'] for r in bucket if r['pre_drop_7d'] is not None]
            pre30 = [r['pre_drop_30d'] for r in bucket if r['pre_drop_30d'] is not None]
            dd90 = [r['drawdown_90d'] for r in bucket]

            print(f"  {threshold_name} (n={len(bucket)}):")
            if pre7:  print(f"    Already dropped (7d):  avg {np.mean(pre7)*100:+.1f}%  median {np.median(pre7)*100:+.1f}%")
            if pre30: print(f"    Already dropped (30d): avg {np.mean(pre30)*100:+.1f}%  median {np.median(pre30)*100:+.1f}%")
            print(f"    Current drawdown (90d): avg {np.mean(dd90)*100:+.1f}%  median {np.median(dd90)*100:+.1f}%")
            print()

        # ── Q3: When we're WRONG, what happens? ────────────────────────
        print(f"\n  Q3: FALSE POSITIVES — WHAT HAPPENS WHEN WE'RE WRONG?")
        print(f"  (We say 'crash coming' but it doesn't crash ≥30%)\n")

        # High probability but no crash
        for threshold_name, lo, hi in [
            ("All flagged (>50%)", 0.50, 1.01),
            ("High confidence (>60%)", 0.60, 1.01),
            ("Very high (>70%)", 0.70, 1.01),
        ]:
            fp = [r for r in res if lo <= r['prob'] < hi and r['crashed'] == 0]
            tp = [r for r in res if lo <= r['prob'] < hi and r['crashed'] == 1]

            if len(fp) < 10: continue

            print(f"  {threshold_name}:")
            print(f"    True Positives: {len(tp)} | False Positives: {len(fp)}")
            print(f"    Precision: {len(tp)/(len(tp)+len(fp))*100:.1f}%")

            # What actually happens to false positives?
            fp_drops_90 = [r['max_drop_90d'] for r in fp]
            fp_ends_90 = [r['end_ret_90d'] for r in fp if 'end_ret_90d' in r]

            print(f"    FP avg max drop 90d: {np.mean(fp_drops_90)*100:+.1f}%")
            print(f"    FP median max drop:  {np.median(fp_drops_90)*100:+.1f}%")
            if fp_ends_90:
                print(f"    FP avg end return:   {np.mean(fp_ends_90)*100:+.1f}%")
                pct_still_down = sum(1 for r in fp_ends_90 if r < -0.10) / len(fp_ends_90)
                pct_recovered = sum(1 for r in fp_ends_90 if r > 0.0) / len(fp_ends_90)
                print(f"    FP still down >10%:  {pct_still_down*100:.0f}%")
                print(f"    FP recovered (>0%):  {pct_recovered*100:.0f}%")

            # Compare: what happens to TRUE positives?
            tp_drops_90 = [r['max_drop_90d'] for r in tp]
            if tp_drops_90:
                print(f"    TP avg max drop 90d: {np.mean(tp_drops_90)*100:+.1f}%")
            print()

        # ── Q3b: What happens to MISSED crashes? ───────────────────────
        print(f"\n  Q3b: MISSED CRASHES — What did we miss?")
        missed = [r for r in res if r['prob'] < 0.40 and r['crashed'] == 1]
        caught = [r for r in res if r['prob'] >= 0.40 and r['crashed'] == 1]

        if missed and caught:
            print(f"  Caught (prob≥40%): {len(caught)} crashes")
            print(f"  Missed (prob<40%): {len(missed)} crashes")
            print(f"  Recall at 40%:    {len(caught)/(len(caught)+len(missed))*100:.1f}%")
            print(f"\n  Missed crashes characteristics:")
            print(f"    Avg vol:     {np.mean([r['vol_30d'] for r in missed]):.2f} (caught: {np.mean([r['vol_30d'] for r in caught]):.2f})")
            print(f"    Avg drawdown:{np.mean([r['drawdown_90d'] for r in missed])*100:+.1f}% (caught: {np.mean([r['drawdown_90d'] for r in caught])*100:+.1f}%)")
            print(f"    Avg max drop:{np.mean([r['max_drop_90d'] for r in missed])*100:.1f}% (caught: {np.mean([r['max_drop_90d'] for r in caught])*100:.1f}%)")

        # ── ECONOMIC VALUE: If you listened to us... ────────────────────
        print(f"\n  {'═'*75}")
        print(f"  ECONOMIC VALUE: What if you acted on our predictions?")
        print(f"  {'═'*75}")

        # Strategy: sell/avoid tokens with prob > threshold
        for thresh in [0.40, 0.50, 0.60]:
            flagged = [r for r in res if r['prob'] >= thresh]
            unflagged = [r for r in res if r['prob'] < thresh]

            if not flagged or not unflagged: continue

            # Average 30d and 90d return for flagged vs unflagged
            flag_30 = [r['end_ret_30d'] for r in flagged if 'end_ret_30d' in r]
            unflag_30 = [r['end_ret_30d'] for r in unflagged if 'end_ret_30d' in r]
            flag_90 = [r['end_ret_90d'] for r in flagged if 'end_ret_90d' in r]
            unflag_90 = [r['end_ret_90d'] for r in unflagged if 'end_ret_90d' in r]

            print(f"\n  Threshold >{thresh*100:.0f}% (flag {len(flagged)}, keep {len(unflagged)}):")
            if flag_30 and unflag_30:
                print(f"    30d: flagged avg {np.mean(flag_30)*100:+.1f}% | kept avg {np.mean(unflag_30)*100:+.1f}% | avoided loss: {(np.mean(unflag_30)-np.mean(flag_30))*100:+.1f}pp")
            if flag_90 and unflag_90:
                print(f"    90d: flagged avg {np.mean(flag_90)*100:+.1f}% | kept avg {np.mean(unflag_90)*100:+.1f}% | avoided loss: {(np.mean(unflag_90)-np.mean(flag_90))*100:+.1f}pp")

    print(f"\n  Done.")


def get_return_simple(series, idx, days):
    if idx < days: return None
    now = series[idx]['close']
    past = series[idx-days]['close']
    return (now-past)/past if past > 0 else None


if __name__ == "__main__":
    main()
