#!/usr/bin/env python3
"""
NERQ — HC ALERT IS/OOS VALIDATION v2
=====================================
Reads from crypto_ndd_history (weekly NDD since 2021) + crypto_price_history (prices since 2017).
Retroactively computes HC Alert triggers and validates against actual price crashes.

HC Alert criteria (from METHODOLOGY_CANONICAL.md):
  - NDD falling streak >= 3 consecutive weeks
  - NDD change over 4 weeks <= -1.0

Crash definition: token drops >= 30% within 90 days of alert.

IS: 2021-03-08 to 2023-12-31 (calibration period)
OOS: 2024-01-01 to 2026-02-23 (validation period)
"""

import sqlite3
import sys
import os
from datetime import datetime, timedelta
from math import sqrt

# ── Config ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")
IS_CUTOFF = "2023-12-31"
OOS_START = "2024-01-01"
HC_STREAK_MIN = 3          # consecutive weeks NDD falling
HC_NDD_CHANGE_MIN = -1.0   # 4-week NDD change threshold
CRASH_THRESHOLD = -0.30    # 30% drop
CRASH_WINDOW_DAYS = 90     # days to look ahead for crash
NDD_DISTRESS_THRESHOLD = 2.0  # for crash detection recall analysis


def wilson_ci(successes, total, z=1.96):
    """Wilson score confidence interval for binomial proportion."""
    if total == 0:
        return 0.0, 0.0, 0.0
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return p, max(0, center - spread), min(1, center + spread)


def load_ndd_history(conn):
    """Load weekly NDD history, sorted by token and date."""
    rows = conn.execute("""
        SELECT token_id, week_date, ndd
        FROM crypto_ndd_history
        WHERE ndd IS NOT NULL
        ORDER BY token_id, week_date
    """).fetchall()
    
    # Group by token
    tokens = {}
    for token_id, week_date, ndd in rows:
        if token_id not in tokens:
            tokens[token_id] = []
        tokens[token_id].append((week_date, ndd))
    
    return tokens


def compute_hc_alerts(tokens):
    """
    For each token's weekly NDD series, compute:
    - falling streak (consecutive weeks where NDD decreased)
    - 4-week NDD change
    - HC Alert trigger when both criteria met
    
    Returns list of (token_id, week_date, ndd, streak, ndd_change_4w, triggered)
    """
    alerts = []
    
    for token_id, series in tokens.items():
        if len(series) < 5:  # need at least 5 weeks for 4w change + streak
            continue
        
        for i in range(1, len(series)):
            week_date, ndd = series[i]
            prev_ndd = series[i-1][1]
            
            # Calculate falling streak
            streak = 0
            for j in range(i, 0, -1):
                if series[j][1] < series[j-1][1]:
                    streak += 1
                else:
                    break
            
            # Calculate 4-week NDD change
            ndd_change_4w = None
            if i >= 4:
                ndd_change_4w = ndd - series[i-4][1]
            
            # HC Alert trigger
            triggered = (streak >= HC_STREAK_MIN and 
                        ndd_change_4w is not None and 
                        ndd_change_4w <= HC_NDD_CHANGE_MIN)
            
            alerts.append((token_id, week_date, ndd, streak, ndd_change_4w, triggered))
    
    return alerts


def load_price_data(conn):
    """Load price history indexed by (token_id, date) for crash checking."""
    rows = conn.execute("""
        SELECT token_id, date, close
        FROM crypto_price_history
        WHERE close IS NOT NULL AND close > 0
        ORDER BY token_id, date
    """).fetchall()
    
    # Group by token: {token_id: [(date, close), ...]}
    prices = {}
    for token_id, date, close in rows:
        if token_id not in prices:
            prices[token_id] = []
        prices[token_id].append((date, close))
    
    return prices


def check_crash_after(prices, token_id, alert_date, window_days=CRASH_WINDOW_DAYS, threshold=CRASH_THRESHOLD):
    """
    Check if token dropped >= threshold within window_days after alert_date.
    Returns (crashed: bool, max_drop: float, has_data: bool)
    """
    if token_id not in prices:
        return False, 0.0, False
    
    token_prices = prices[token_id]
    
    # Find alert date price (closest date on or after alert)
    alert_price = None
    alert_idx = None
    for idx, (d, p) in enumerate(token_prices):
        if d >= alert_date:
            alert_price = p
            alert_idx = idx
            break
    
    if alert_price is None or alert_price <= 0:
        return False, 0.0, False
    
    # Find max drop within window
    end_date = (datetime.strptime(alert_date, "%Y-%m-%d") + timedelta(days=window_days)).strftime("%Y-%m-%d")
    max_drop = 0.0
    
    for idx in range(alert_idx, len(token_prices)):
        d, p = token_prices[idx]
        if d > end_date:
            break
        drop = (p - alert_price) / alert_price
        if drop < max_drop:
            max_drop = drop
    
    crashed = max_drop <= threshold
    return crashed, max_drop, True


def check_crash_detection(ndd_data, prices, period_label, start_date=None, end_date=None):
    """
    Recall analysis: of all actual crashes, how many had NDD < threshold nearby?
    This validates the '1190/1200' claim.
    """
    # Find all crash events from price data
    crash_events = []
    
    for token_id, token_prices in prices.items():
        for i in range(len(token_prices)):
            d, p = token_prices[i]
            
            # Apply date filter
            if start_date and d < start_date:
                continue
            if end_date and d > end_date:
                continue
            
            # Look 90 days ahead for 30%+ drop
            end_window = (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=90)).strftime("%Y-%m-%d")
            min_price = p
            for j in range(i+1, len(token_prices)):
                dj, pj = token_prices[j]
                if dj > end_window:
                    break
                if pj < min_price:
                    min_price = pj
            
            drop = (min_price - p) / p if p > 0 else 0
            if drop <= CRASH_THRESHOLD:
                crash_events.append((token_id, d, drop))
    
    # Deduplicate: keep first crash per token per 90-day window
    seen = set()
    unique_crashes = []
    for token_id, d, drop in crash_events:
        key = (token_id, d[:7])  # one per token per month
        if key not in seen:
            seen.add(key)
            unique_crashes.append((token_id, d, drop))
    
    # Build NDD lookup: {token_id: [(week_date, ndd), ...]}
    ndd_lookup = {}
    for token_id, week_date, ndd, streak, change, triggered in ndd_data:
        if token_id not in ndd_lookup:
            ndd_lookup[token_id] = []
        ndd_lookup[token_id].append((week_date, ndd))
    
    # Check each crash: was NDD < threshold within 4 weeks before crash?
    detected = 0
    undetected = 0
    no_ndd = 0
    
    for token_id, crash_date, drop in unique_crashes:
        if token_id not in ndd_lookup:
            no_ndd += 1
            continue
        
        lookback_start = (datetime.strptime(crash_date, "%Y-%m-%d") - timedelta(days=28)).strftime("%Y-%m-%d")
        
        found_distress = False
        for wd, ndd in ndd_lookup[token_id]:
            if lookback_start <= wd <= crash_date:
                if ndd < NDD_DISTRESS_THRESHOLD:
                    found_distress = True
                    break
        
        if found_distress:
            detected += 1
        else:
            undetected += 1
    
    total_with_ndd = detected + undetected
    
    return unique_crashes, detected, undetected, no_ndd, total_with_ndd


def main():
    print("=" * 80)
    print("  NERQ — HC ALERT IS/OOS VALIDATION v2")
    print("  Source: crypto_ndd_history (weekly) + crypto_price_history")
    print(f"  IS: 2021-03-08 → {IS_CUTOFF}  |  OOS: {OOS_START} → latest")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    conn = sqlite3.connect(DB_PATH)
    
    # ── Load data ───────────────────────────────────────────────────────────
    print("\n  Loading NDD history...")
    tokens = load_ndd_history(conn)
    total_tokens = len(tokens)
    total_weeks = sum(len(v) for v in tokens.values())
    print(f"  {total_tokens} tokens, {total_weeks} weekly observations")
    
    print("  Computing HC Alert triggers retroactively...")
    all_alerts = compute_hc_alerts(tokens)
    triggered = [a for a in all_alerts if a[5]]
    print(f"  Total observations: {len(all_alerts)}")
    print(f"  HC Alert triggers: {len(triggered)}")
    
    print("\n  Loading price history...")
    prices = load_price_data(conn)
    total_price_tokens = len(prices)
    total_price_rows = sum(len(v) for v in prices.values())
    print(f"  {total_price_tokens} tokens, {total_price_rows} price points")
    
    # ── Split IS/OOS ────────────────────────────────────────────────────────
    is_triggers = [a for a in triggered if a[1] <= IS_CUTOFF]
    oos_triggers = [a for a in triggered if a[1] >= OOS_START]
    
    print(f"\n  IS triggers: {len(is_triggers)}")
    print(f"  OOS triggers: {len(oos_triggers)}")
    
    # ── Evaluate HC Alert precision ─────────────────────────────────────────
    for label, triggers in [("IN-SAMPLE", is_triggers), ("OUT-OF-SAMPLE", oos_triggers)]:
        print(f"\n  {'─' * 60}")
        print(f"  {label} HC ALERT RESULTS")
        print(f"  {'─' * 60}")
        
        if not triggers:
            print(f"  No triggers — skipping")
            continue
        
        correct = 0
        false_pos = 0
        no_price = 0
        drops = []
        
        for token_id, week_date, ndd, streak, change, _ in triggers:
            crashed, max_drop, has_data = check_crash_after(prices, token_id, week_date)
            if not has_data:
                no_price += 1
                continue
            drops.append(max_drop)
            if crashed:
                correct += 1
            else:
                false_pos += 1
        
        evaluated = correct + false_pos
        precision, ci_low, ci_high = wilson_ci(correct, evaluated)
        
        print(f"  Total triggers:     {len(triggers)}")
        print(f"  Evaluated:          {evaluated} (no price data: {no_price})")
        print(f"  Correct (≥30% drop): {correct}")
        print(f"  False positive:      {false_pos}")
        print(f"  Precision:           {precision*100:.1f}%")
        print(f"  95% CI (Wilson):     [{ci_low*100:.1f}%, {ci_high*100:.1f}%]")
        if drops:
            avg_drop = sum(drops) / len(drops)
            print(f"  Avg max drop:        {avg_drop*100:.1f}%")
            print(f"  Worst drop:          {min(drops)*100:.1f}%")
        
        # Show some example triggers
        print(f"\n  Sample triggers:")
        for token_id, week_date, ndd, streak, change, _ in triggers[:10]:
            crashed, max_drop, has_data = check_crash_after(prices, token_id, week_date)
            status = f"DROP {max_drop*100:.0f}%" if has_data else "NO DATA"
            print(f"    {week_date} | {token_id[:30]:30s} | NDD={ndd:.2f} streak={streak} Δ4w={change:.2f} | {status}")
    
    # ── Crash Detection Recall ──────────────────────────────────────────────
    print(f"\n  {'═' * 60}")
    print(f"  CRASH DETECTION RECALL (validates '1190/1200' claim)")
    print(f"  {'═' * 60}")
    
    # Overall
    crashes, detected, undetected, no_ndd, total_with = check_crash_detection(
        all_alerts, prices, "ALL")
    
    if total_with > 0:
        recall, r_low, r_high = wilson_ci(detected, total_with)
        print(f"\n  OVERALL:")
        print(f"  Total crash events (≥30% in 90d): {len(crashes)}")
        print(f"  With NDD data: {total_with}, without: {no_ndd}")
        print(f"  Detected (NDD < {NDD_DISTRESS_THRESHOLD} within 4w before): {detected}")
        print(f"  Undetected: {undetected}")
        print(f"  Recall: {recall*100:.1f}% [{r_low*100:.1f}%, {r_high*100:.1f}%]")
    
    # IS
    is_crashes, is_det, is_undet, is_no, is_total = check_crash_detection(
        [a for a in all_alerts if a[1] <= IS_CUTOFF], prices, "IS",
        start_date="2021-01-01", end_date=IS_CUTOFF)
    
    if is_total > 0:
        is_recall, is_low, is_high = wilson_ci(is_det, is_total)
        print(f"\n  IN-SAMPLE (2021-2023):")
        print(f"  Crashes: {len(is_crashes)}, with NDD: {is_total}")
        print(f"  Detected: {is_det}, Undetected: {is_undet}")
        print(f"  Recall: {is_recall*100:.1f}% [{is_low*100:.1f}%, {is_high*100:.1f}%]")
    
    # OOS
    oos_crashes, oos_det, oos_undet, oos_no, oos_total = check_crash_detection(
        [a for a in all_alerts if a[1] >= OOS_START], prices, "OOS",
        start_date=OOS_START, end_date="2026-12-31")
    
    if oos_total > 0:
        oos_recall, oos_low, oos_high = wilson_ci(oos_det, oos_total)
        print(f"\n  OUT-OF-SAMPLE (2024-2026):")
        print(f"  Crashes: {len(oos_crashes)}, with NDD: {oos_total}")
        print(f"  Detected: {oos_det}, Undetected: {oos_undet}")
        print(f"  Recall: {oos_recall*100:.1f}% [{oos_low*100:.1f}%, {oos_high*100:.1f}%]")
    
    # ── Crash Probability Table ─────────────────────────────────────────────
    print(f"\n  {'═' * 60}")
    print(f"  CRASH PROBABILITY TABLE — BY NDD LEVEL & TREND")
    print(f"  {'═' * 60}")
    
    # Compute NDD trend categories per observation
    # Trend: based on 4-week change direction
    # Level: based on NDD value
    def ndd_level(ndd):
        if ndd >= 4.0: return "SAFE"
        elif ndd >= 3.0: return "WATCH"
        elif ndd >= 2.0: return "WARNING"
        else: return "DISTRESS"
    
    def ndd_trend(change_4w):
        if change_4w is None: return None
        if change_4w <= -1.5: return "FREEFALL"
        elif change_4w <= -0.5: return "FALLING"
        elif change_4w <= -0.1: return "SLIDING"
        elif change_4w <= 0.5: return "STABLE"
        else: return "IMPROVING"
    
    # Build crash probability table
    table = {}  # (trend, level) -> (total, crashed)
    
    for token_id, week_date, ndd, streak, change_4w, _ in all_alerts:
        if change_4w is None:
            continue
        
        trend = ndd_trend(change_4w)
        level = ndd_level(ndd)
        
        if trend is None:
            continue
        
        key = (trend, level)
        if key not in table:
            table[key] = [0, 0]
        
        table[key][0] += 1
        
        # Check if crash followed
        crashed, _, has_data = check_crash_after(prices, token_id, week_date)
        if has_data and crashed:
            table[key][1] += 1
    
    # Print table
    trends = ["FREEFALL", "FALLING", "SLIDING", "STABLE", "IMPROVING"]
    levels = ["SAFE", "WATCH", "WARNING", "DISTRESS"]
    
    print(f"\n  {'Trend':<12} {'Level':<10} {'Obs':>6} {'Crashed':>8} {'Rate':>8} {'95% CI':>20}")
    print(f"  {'─' * 70}")
    
    for trend in trends:
        for level in levels:
            key = (trend, level)
            if key in table:
                obs, crashed = table[key]
                if obs > 0:
                    rate, ci_low, ci_high = wilson_ci(crashed, obs)
                    print(f"  {trend:<12} {level:<10} {obs:>6} {crashed:>8} {rate*100:>7.1f}% [{ci_low*100:.1f}%-{ci_high*100:.1f}%]")
    
    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\n  {'═' * 60}")
    print(f"  SUMMARY & GO/NO-GO")
    print(f"  {'═' * 60}")
    
    hc_total = len(is_triggers) + len(oos_triggers)
    print(f"\n  HC Alert triggers total: {hc_total} (IS: {len(is_triggers)}, OOS: {len(oos_triggers)})")
    
    if oos_total > 0 and len(oos_triggers) > 0:
        oos_eval = sum(1 for t in oos_triggers 
                       if check_crash_after(prices, t[0], t[1])[2])
        oos_correct = sum(1 for t in oos_triggers 
                         if check_crash_after(prices, t[0], t[1])[0])
        if oos_eval > 0:
            oos_prec = oos_correct / oos_eval
            print(f"  OOS HC Alert precision: {oos_prec*100:.1f}% ({oos_correct}/{oos_eval})")
        
        print(f"  OOS Crash recall: {oos_recall*100:.1f}%")
        
        if oos_prec >= 0.60 and oos_recall >= 0.50:
            print(f"\n  🎯 HC ALERT: CONDITIONAL GO — Precision OK but needs honest reporting")
        elif oos_prec >= 0.50:
            print(f"\n  ⚠️  HC ALERT: MARGINAL — Precision {oos_prec*100:.0f}%, needs improvement")
        else:
            print(f"\n  ❌ HC ALERT: NO-GO — Precision too low for external communication")
        
        if oos_recall >= 0.80:
            print(f"  ✅ CRASH DETECTION: Recall {oos_recall*100:.0f}% supports '1190/1200' narrative")
        elif oos_recall >= 0.60:
            print(f"  ⚠️  CRASH DETECTION: Recall {oos_recall*100:.0f}% — cannot claim '1190/1200'")
            print(f"     → Reframe as 'detected {oos_recall*100:.0f}% of major crashes'")
        else:
            print(f"  ❌ CRASH DETECTION: Recall {oos_recall*100:.0f}% — '1190/1200' claim invalid")
            print(f"     → Must retract or heavily qualify this claim")
    
    print(f"\n  Done.")
    conn.close()


if __name__ == "__main__":
    main()
