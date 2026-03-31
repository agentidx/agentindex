#!/usr/bin/env python3
"""
NERQ — SEVERE CRASH DETECTION ANALYSIS
=========================================
Key question: How many of the WORST crashes do we catch?
Specifically tokens that drop 90-95%+ and never recover.

Breaks down by crash severity:
  - Mild: -30% to -50%
  - Severe: -50% to -70%
  - Catastrophic: -70% to -90%
  - Terminal: -90%+ (the ones that matter most)

For each: what % did we flag? At what threshold?
And: do terminal crashes recover or are they dead?
"""

import sqlite3
import os
import json
import numpy as np
from datetime import datetime, timedelta
from math import sqrt, exp
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash_model_v2.json")
OOS_START = "2024-01-01"
IS_CUTOFF = "2023-12-31"

def sigmoid(z):
    z = max(-500, min(500, z))
    return 1.0 / (1.0 + exp(-z))

def predict(feat_vec, model):
    w = model['weights']
    b = model['bias']
    means = model['feature_means']
    stds = model['feature_stds']
    z = b + sum(w[j] * (feat_vec[j] - means[j]) / stds[j] for j in range(len(w)))
    return sigmoid(z)

def get_idx(series, date):
    lo, hi = 0, len(series)-1; r = None
    while lo <= hi:
        mid = (lo+hi)//2
        if series[mid][0] <= date: r = mid; lo = mid+1
        else: hi = mid-1
    return r


def main():
    print("="*80)
    print("  NERQ — SEVERE CRASH DETECTION ANALYSIS")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    model = json.load(open(MODEL_PATH))

    conn = sqlite3.connect(DB_PATH)

    # Load prices as (date, close)
    print("  Loading prices...")
    rows = conn.execute("""
        SELECT token_id, date, close FROM crypto_price_history
        WHERE close > 0 ORDER BY token_id, date
    """).fetchall()
    prices = defaultdict(list)
    for tid, d, c in rows:
        prices[tid].append((d, c))
    prices = dict(prices)

    # Load NDD
    ndd_rows = conn.execute("""
        SELECT token_id, week_date, ndd, signal_3, signal_5, signal_6
        FROM crypto_ndd_history WHERE ndd IS NOT NULL
        ORDER BY token_id, week_date
    """).fetchall()
    ndd = defaultdict(list)
    for tid, wd, n, s3, s5, s6 in ndd_rows:
        ndd[tid].append((wd, n, s3, s5, s6))

    # Load ratings
    rat_rows = conn.execute("""
        SELECT token_id, year_month, pillar_3
        FROM crypto_rating_history WHERE pillar_3 IS NOT NULL
        ORDER BY token_id, year_month
    """).fetchall()
    ratings = defaultdict(list)
    for tid, ym, p3 in rat_rows:
        ratings[tid].append((ym, p3))

    conn.close()

    # Compute vol_90th from IS
    print("  Computing IS vol threshold...")
    btc = prices.get('bitcoin', [])
    is_vols = []
    for tid in ndd:
        if tid not in prices: continue
        tp = prices[tid]
        for wd, n, s3, s5, s6 in ndd[tid]:
            if wd > IS_CUTOFF: continue
            idx = get_idx(tp, wd)
            if idx and idx >= 30:
                rets = []
                for i in range(idx-29, idx+1):
                    if i > 0 and tp[i-1][1] > 0:
                        rets.append((tp[i][1]-tp[i-1][1])/tp[i-1][1])
                if len(rets) >= 20:
                    m = sum(rets)/len(rets)
                    v = sum((r-m)**2 for r in rets)/len(rets)
                    is_vols.append(sqrt(v)*sqrt(365))
    is_vols.sort()
    vol_90th = is_vols[int(len(is_vols)*0.9)] if is_vols else 2.0

    # Build predictions with DETAILED forward paths
    print("  Building predictions with extended forward paths...")

    results = []

    for tid in sorted(ndd.keys()):
        if tid not in prices: continue
        tp = prices[tid]

        for wd, ndd_val, s3, s5, s6 in ndd[tid]:
            date = wd
            idx = get_idx(tp, date)
            if not idx or idx < 90: continue
            close = tp[idx][1]
            if close <= 0: continue

            # Vol
            if idx < 30: continue
            rets = []
            for i in range(idx-29, idx+1):
                if i > 0 and tp[i-1][1] > 0:
                    rets.append((tp[i][1]-tp[i-1][1])/tp[i-1][1])
            if len(rets) < 20: continue
            m = sum(rets)/len(rets); v = sum((r-m)**2 for r in rets)/len(rets)
            vol = sqrt(v)*sqrt(365)

            # Drawdown 90d
            high90 = max(tp[i][1] for i in range(max(0,idx-89), idx+1))
            dd = (close-high90)/high90 if high90 > 0 else 0

            # BTC vol
            btc_idx = get_idx(btc, date) if btc else None
            if not btc_idx or btc_idx < 30: continue
            b_rets = []
            for i in range(btc_idx-29, btc_idx+1):
                if i > 0 and btc[i-1][1] > 0:
                    b_rets.append((btc[i][1]-btc[i-1][1])/btc[i-1][1])
            if len(b_rets) < 20: continue
            bm = sum(b_rets)/len(b_rets); bv = sum((r-bm)**2 for r in b_rets)/len(b_rets)
            btc_vol = sqrt(bv)*sqrt(365)

            # NDD min 4w
            ni = None
            for i, (w, n, _s3, _s5, _s6) in enumerate(ndd[tid]):
                if w <= date: ni = i
                else: break
            if ni is None: continue
            cur_ndd = ndd[tid][ni][1]
            ndd_min = cur_ndd
            if ni >= 3:
                ndd_min = min(ndd[tid][i][1] for i in range(ni-3, ni+1))

            # Trust p3
            if tid not in ratings: continue
            ri = None
            for i, (ym, p3) in enumerate(ratings[tid]):
                if ym <= date[:7]: ri = i
                else: break
            if ri is None: continue
            p3 = ratings[tid][ri][1]

            # Features
            ndd_weak = max(0, 3.5 - ndd_min)
            maint_weak = max(0, 50 - p3) / 50
            feat_vec = [vol, p3, s6 or 0, ndd_min, s5 or 0, s3 or 0, dd, btc_vol,
                        vol * ndd_weak, abs(dd) * max(0, 3.0 - (s5 or 0)),
                        btc_vol * ndd_weak, vol * maint_weak,
                        1.0 if ndd_min < 2.0 else 0.0,
                        1.0 if dd < -0.40 else 0.0,
                        1.0 if vol > vol_90th else 0.0,
                        1.0 if p3 < 40 else 0.0]

            prob = predict(feat_vec, model)

            # Forward paths: track max drop at multiple horizons AND check recovery
            # Extended: 30d, 90d, 180d, 365d
            forward = {}
            for horizon in [30, 90, 180, 365]:
                target_d = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=horizon)).strftime("%Y-%m-%d")
                max_drop = 0.0
                end_price = None
                for i in range(idx+1, len(tp)):
                    if tp[i][0] > target_d: break
                    d = (tp[i][1] - close) / close
                    if d < max_drop: max_drop = d
                    end_price = tp[i][1]

                if end_price is not None:
                    forward[f'max_drop_{horizon}d'] = max_drop
                    forward[f'end_ret_{horizon}d'] = (end_price - close) / close

            if 'max_drop_90d' not in forward: continue

            # Check if token is essentially dead (price < 10% of prediction price after 365d)
            dead = False
            if 'end_ret_365d' in forward and forward['end_ret_365d'] < -0.90:
                dead = True
            elif 'end_ret_180d' in forward and forward['end_ret_180d'] < -0.90:
                dead = True

            results.append({
                'token_id': tid,
                'date': date,
                'prob': prob,
                'max_drop_90d': forward['max_drop_90d'],
                'max_drop_180d': forward.get('max_drop_180d'),
                'max_drop_365d': forward.get('max_drop_365d'),
                'end_ret_90d': forward.get('end_ret_90d'),
                'end_ret_180d': forward.get('end_ret_180d'),
                'end_ret_365d': forward.get('end_ret_365d'),
                'dead': dead,
                'vol': vol,
                'dd90': dd,
                'p3': p3,
            })

    print(f"  Total predictions: {len(results)}")
    oos = [r for r in results if r['date'] >= OOS_START]
    is_res = [r for r in results if r['date'] <= IS_CUTOFF]
    print(f"  IS: {len(is_res)} | OOS: {len(oos)}")

    # ══════════════════════════════════════════════════════════════════════════
    # ANALYSIS BY CRASH SEVERITY
    # ══════════════════════════════════════════════════════════════════════════

    for label, res in [("IN-SAMPLE (2021-2023)", is_res), ("OUT-OF-SAMPLE (2024-2026)", oos)]:
        print(f"\n  {'═'*75}")
        print(f"  {label} (n={len(res)})")
        print(f"  {'═'*75}")

        # Categorize by max drop severity
        categories = [
            ("NO CRASH (>-30%)", lambda r: r['max_drop_90d'] > -0.30),
            ("MILD (-30% to -50%)", lambda r: -0.50 < r['max_drop_90d'] <= -0.30),
            ("SEVERE (-50% to -70%)", lambda r: -0.70 < r['max_drop_90d'] <= -0.50),
            ("CATASTROPHIC (-70% to -90%)", lambda r: -0.90 < r['max_drop_90d'] <= -0.70),
            ("TERMINAL (-90%+)", lambda r: r['max_drop_90d'] <= -0.90),
        ]

        print(f"\n  CRASH SEVERITY DISTRIBUTION:")
        print(f"  {'Category':<30} {'N':>7} {'Pct':>7} {'Avg prob':>9} {'Med prob':>9} {'Flagged>50%':>12} {'Flagged>40%':>12}")
        print(f"  {'─'*90}")

        for name, filt in categories:
            bucket = [r for r in res if filt(r)]
            if not bucket: continue
            n = len(bucket)
            pct = n / len(res) * 100
            avg_p = np.mean([r['prob'] for r in bucket])
            med_p = np.median([r['prob'] for r in bucket])
            flagged_50 = sum(1 for r in bucket if r['prob'] >= 0.50)
            flagged_40 = sum(1 for r in bucket if r['prob'] >= 0.40)
            print(f"  {name:<30} {n:>7} {pct:>6.1f}% {avg_p:>8.1%} {med_p:>8.1%} "
                  f"{flagged_50:>5} ({flagged_50/n*100:>4.0f}%) {flagged_40:>5} ({flagged_40/n*100:>4.0f}%)")

        # ── Focus: Terminal crashes (-90%+) ─────────────────────────────
        terminal = [r for r in res if r['max_drop_90d'] <= -0.90]
        catastrophic = [r for r in res if -0.90 < r['max_drop_90d'] <= -0.70]
        severe = [r for r in res if -0.70 < r['max_drop_90d'] <= -0.50]

        if terminal:
            print(f"\n  TERMINAL CRASHES (-90%+ in 90 days): {len(terminal)} observations")
            print(f"  ──────────────────────────────────────")

            # Detection rates at various thresholds
            print(f"  Detection rates:")
            for thresh in [0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70]:
                caught = sum(1 for r in terminal if r['prob'] >= thresh)
                print(f"    Threshold >{thresh*100:.0f}%: caught {caught}/{len(terminal)} ({caught/len(terminal)*100:.1f}%)")

            # Do they recover?
            print(f"\n  Recovery analysis:")
            for horizon, key in [(90,'end_ret_90d'), (180,'end_ret_180d'), (365,'end_ret_365d')]:
                has_data = [r for r in terminal if r.get(key) is not None]
                if not has_data: continue
                avg_end = np.mean([r[key] for r in has_data])
                med_end = np.median([r[key] for r in has_data])
                pct_still_down_50 = sum(1 for r in has_data if r[key] < -0.50) / len(has_data)
                pct_still_down_90 = sum(1 for r in has_data if r[key] < -0.90) / len(has_data)
                pct_recovered = sum(1 for r in has_data if r[key] > 0) / len(has_data)
                print(f"    After {horizon}d (n={len(has_data)}):")
                print(f"      Median end return: {med_end*100:+.1f}%")
                print(f"      Still down >50%:   {pct_still_down_50*100:.0f}%")
                print(f"      Still down >90%:   {pct_still_down_90*100:.0f}%")
                print(f"      Recovered (>0%):   {pct_recovered*100:.0f}%")

            # Token examples
            terminal.sort(key=lambda x: x['max_drop_90d'])
            print(f"\n  Worst terminal crashes:")
            print(f"  {'Token':<25} {'Date':<12} {'Max Drop':>9} {'Prob':>6} {'P3':>5} {'End 90d':>9} {'Dead?':>6}")
            print(f"  {'─'*75}")
            seen = set()
            for r in terminal[:30]:
                if r['token_id'] in seen: continue
                seen.add(r['token_id'])
                end = f"{r.get('end_ret_90d',0)*100:+.0f}%" if r.get('end_ret_90d') is not None else "?"
                dead = "YES" if r['dead'] else "no"
                print(f"  {r['token_id'][:25]:<25} {r['date']:<12} {r['max_drop_90d']*100:>8.1f}% {r['prob']:>5.0%} {r['p3']:>5.0f} {end:>9} {dead:>6}")
                if len(seen) >= 20: break

        # ── Comparison: detection by severity ───────────────────────────
        print(f"\n  DETECTION COMPARISON BY SEVERITY (threshold >40%):")
        print(f"  {'Severity':<30} {'Total':>7} {'Caught':>8} {'Rate':>7} {'Avg prob':>9}")
        print(f"  {'─'*65}")

        for name, bucket in [
            ("Mild (-30% to -50%)", [r for r in res if -0.50 < r['max_drop_90d'] <= -0.30]),
            ("Severe (-50% to -70%)", [r for r in res if -0.70 < r['max_drop_90d'] <= -0.50]),
            ("Catastrophic (-70% to -90%)", [r for r in res if -0.90 < r['max_drop_90d'] <= -0.70]),
            ("Terminal (-90%+)", [r for r in res if r['max_drop_90d'] <= -0.90]),
        ]:
            if not bucket: continue
            caught = sum(1 for r in bucket if r['prob'] >= 0.40)
            avg_p = np.mean([r['prob'] for r in bucket])
            print(f"  {name:<30} {len(bucket):>7} {caught:>8} {caught/len(bucket)*100:>5.1f}% {avg_p:>8.1%}")

        # ── "Never recover" analysis ────────────────────────────────────
        print(f"\n  'NEVER RECOVER' TOKENS (still down >80% after max available horizon):")

        never_recover = []
        for r in res:
            # Check longest available horizon
            for key in ['end_ret_365d', 'end_ret_180d', 'end_ret_90d']:
                if r.get(key) is not None:
                    if r[key] < -0.80:
                        never_recover.append(r)
                    break

        if never_recover:
            print(f"  Total: {len(never_recover)} observations")
            caught_50 = sum(1 for r in never_recover if r['prob'] >= 0.50)
            caught_40 = sum(1 for r in never_recover if r['prob'] >= 0.40)
            caught_30 = sum(1 for r in never_recover if r['prob'] >= 0.30)
            print(f"  Detection rates:")
            print(f"    >50% threshold: {caught_50}/{len(never_recover)} ({caught_50/len(never_recover)*100:.1f}%)")
            print(f"    >40% threshold: {caught_40}/{len(never_recover)} ({caught_40/len(never_recover)*100:.1f}%)")
            print(f"    >30% threshold: {caught_30}/{len(never_recover)} ({caught_30/len(never_recover)*100:.1f}%)")

            avg_prob = np.mean([r['prob'] for r in never_recover])
            med_prob = np.median([r['prob'] for r in never_recover])
            print(f"  Avg probability assigned: {avg_prob:.1%}")
            print(f"  Med probability assigned: {med_prob:.1%}")

            # What did the missed ones look like?
            missed = [r for r in never_recover if r['prob'] < 0.40]
            caught = [r for r in never_recover if r['prob'] >= 0.40]
            if missed and caught:
                print(f"\n  Missed vs Caught 'never recover' tokens:")
                print(f"    {'Metric':<25} {'Caught (≥40%)':>15} {'Missed (<40%)':>15}")
                print(f"    {'─'*55}")
                print(f"    {'Avg volatility':<25} {np.mean([r['vol'] for r in caught]):>14.2f} {np.mean([r['vol'] for r in missed]):>14.2f}")
                print(f"    {'Avg drawdown at pred':<25} {np.mean([r['dd90'] for r in caught])*100:>13.1f}% {np.mean([r['dd90'] for r in missed])*100:>13.1f}%")
                print(f"    {'Avg Trust P3':<25} {np.mean([r['p3'] for r in caught]):>14.1f} {np.mean([r['p3'] for r in missed]):>14.1f}")
                print(f"    {'Max drop 90d':<25} {np.mean([r['max_drop_90d'] for r in caught])*100:>13.1f}% {np.mean([r['max_drop_90d'] for r in missed])*100:>13.1f}%")

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
