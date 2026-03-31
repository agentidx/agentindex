#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 2.0.3: HC Alert IS/OOS Separation
========================================================
Splits HC Alert data (n=275) into In-Sample and Out-of-Sample periods.
Calculates Wilson score confidence intervals for precision.
Analyzes "1190/1200 crashes" claim with precision/recall/lead time.

Run: python3 hc_alert_is_oos_split.py
"""

import sqlite3
import os
import sys
import json
import math
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")

# IS/OOS boundary
IS_END = "2023-12-31"
OOS_START = "2024-01-01"

# HC Alert criteria (from METHODOLOGY_CANONICAL)
HC_MIN_STREAK = 3
HC_FREEFALL_THRESHOLD = -1.0

# Crash definition
CRASH_THRESHOLD_30PCT = 0.30  # >30% drop within 90 days
CRASH_WINDOW_DAYS = 90


def wilson_ci(successes, total, z=1.96):
    """Wilson score 95% confidence interval."""
    if total == 0:
        return 0, 0, 0
    p_hat = successes / total
    denom = 1 + z**2 / total
    center = (p_hat + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total) / denom
    lo = max(0, center - spread)
    hi = min(1, center + spread)
    return p_hat, lo, hi


def get_db():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def analyze_hc_alerts(conn):
    """Find all HC Alert triggers and analyze outcomes."""
    print("=" * 80)
    print("  NERQ — HC ALERT IS/OOS SEPARATION ANALYSIS")
    print(f"  IS: ≤ {IS_END}  |  OOS: ≥ {OOS_START}")
    print("=" * 80)

    # Check if hc_alert column exists in crypto_ndd_daily
    try:
        test = conn.execute("SELECT hc_alert FROM crypto_ndd_daily LIMIT 1").fetchone()
        has_daily = True
        print("  Using crypto_ndd_daily table (has hc_alert column)")
    except:
        has_daily = False
        print("  crypto_ndd_daily does not have hc_alert — using crypto_ndd_history")

    # Strategy: Find all weeks where HC Alert conditions were met
    # HC Alert = streak >= 3 weeks in WARNING/DISTRESS + NDD change <= -1.0

    if has_daily:
        # Use crypto_ndd_daily which has hc_alert pre-computed
        hc_rows = conn.execute("""
            SELECT token_id, run_date as week_date, symbol, ndd, alert_level,
                   ndd_trend, ndd_change_4w, hc_alert, hc_streak, crash_probability
            FROM crypto_ndd_daily
            WHERE hc_alert = 1
            ORDER BY run_date ASC
        """).fetchall()
    else:
        # Fall back to computing from crypto_ndd_history
        hc_rows = []
        # Get all tokens
        tokens = conn.execute("""
            SELECT DISTINCT token_id FROM crypto_ndd_history
        """).fetchall()

        for (tid,) in [(r['token_id'],) for r in tokens]:
            weeks = conn.execute("""
                SELECT week_date, ndd, alert_level
                FROM crypto_ndd_history
                WHERE token_id = ?
                ORDER BY week_date ASC
            """, (tid,)).fetchall()

            streak = 0
            for i, w in enumerate(weeks):
                if w['alert_level'] in ('WARNING', 'DISTRESS', 'CRITICAL'):
                    streak += 1
                else:
                    streak = 0

                if streak >= HC_MIN_STREAK and i >= 4:
                    # Check NDD change over 4 weeks
                    prev_ndd = weeks[i - 4]['ndd'] if i >= 4 else None
                    if prev_ndd is not None:
                        ndd_change = w['ndd'] - prev_ndd
                        if ndd_change <= HC_FREEFALL_THRESHOLD:
                            hc_rows.append({
                                'token_id': tid,
                                'week_date': w['week_date'],
                                'ndd': w['ndd'],
                                'alert_level': w['alert_level'],
                                'ndd_change_4w': ndd_change,
                                'streak': streak,
                            })

    if not hc_rows:
        print("\n  ⚠️  No HC Alert data found. Cannot perform IS/OOS split.")
        print("  Possible reasons:")
        print("    - HC Alert was computed ad-hoc, not stored in DB")
        print("    - The n=275 figure comes from a different analysis")
        print("  → ANDERS: Where does the '78% precision (n=275)' figure come from?")
        print("  → Need the original analysis script or data export.")
        return

    print(f"\n  Total HC Alert triggers found: {len(hc_rows)}")

    # Split IS/OOS
    is_alerts = []
    oos_alerts = []

    for r in hc_rows:
        week = r['week_date'] if isinstance(r, dict) else r[1]
        if week <= IS_END:
            is_alerts.append(r)
        else:
            oos_alerts.append(r)

    print(f"  In-Sample (≤{IS_END}):  {len(is_alerts)} alerts")
    print(f"  Out-of-Sample (≥{OOS_START}): {len(oos_alerts)} alerts")

    # Analyze outcomes: did a >30% crash occur within 90 days?
    for label, alerts in [("IN-SAMPLE", is_alerts), ("OUT-OF-SAMPLE", oos_alerts)]:
        if not alerts:
            print(f"\n  {label}: No alerts — skipping")
            continue

        correct = 0
        false_positive = 0
        no_data = 0
        lead_times = []

        for a in alerts:
            tid = a['token_id'] if isinstance(a, dict) else a[0]
            week = a['week_date'] if isinstance(a, dict) else a[1]

            # Get price at alert date and within next 90 days
            prices = conn.execute("""
                SELECT date, close FROM crypto_price_history
                WHERE token_id = ? AND date >= ? AND date <= date(?, '+90 days')
                ORDER BY date ASC
            """, (tid, week, week)).fetchall()

            if not prices or len(prices) < 5:
                no_data += 1
                continue

            alert_price = prices[0]['close']
            if not alert_price or alert_price <= 0:
                no_data += 1
                continue

            # Find max drop within 90 days
            min_price = min(p['close'] for p in prices if p['close'] and p['close'] > 0)
            max_drop = (alert_price - min_price) / alert_price

            if max_drop >= CRASH_THRESHOLD_30PCT:
                correct += 1
                # Calculate lead time (days to reach 30% drop)
                for p in prices:
                    if p['close'] and p['close'] > 0:
                        drop = (alert_price - p['close']) / alert_price
                        if drop >= CRASH_THRESHOLD_30PCT:
                            lead_days = (datetime.strptime(p['date'], '%Y-%m-%d') -
                                        datetime.strptime(week, '%Y-%m-%d')).days
                            lead_times.append(lead_days)
                            break
            else:
                false_positive += 1

        total_evaluated = correct + false_positive
        precision, ci_lo, ci_hi = wilson_ci(correct, total_evaluated)

        print(f"\n  {'─' * 60}")
        print(f"  {label} RESULTS")
        print(f"  {'─' * 60}")
        print(f"  Total alerts:        {len(alerts)}")
        print(f"  Evaluated:           {total_evaluated} (no price data: {no_data})")
        print(f"  Correct (>30% drop): {correct}")
        print(f"  False positive:      {false_positive}")
        print(f"  Precision:           {precision:.1%}")
        print(f"  95% CI (Wilson):     [{ci_lo:.1%}, {ci_hi:.1%}]")
        if lead_times:
            print(f"  Avg lead time:       {np.mean(lead_times):.0f} days")
            print(f"  Median lead time:    {np.median(lead_times):.0f} days")
            print(f"  Min/Max lead time:   {min(lead_times)}/{max(lead_times)} days")

    # Analyze the "1190/1200 crashes" claim
    print(f"\n  {'═' * 60}")
    print(f"  CRASH DETECTION ANALYSIS (1190/1200 claim)")
    print(f"  {'═' * 60}")

    # Find all crash events (>30% drop in 90 days) for tokens with NDD data
    crash_events = analyze_crash_detection(conn)


def analyze_crash_detection(conn):
    """Analyze the '1190/1200 crashes detected' claim."""

    # Get all tokens with NDD history
    tokens = conn.execute("""
        SELECT DISTINCT token_id FROM crypto_ndd_history
    """).fetchall()
    token_ids = [r['token_id'] for r in tokens]

    print(f"  Tokens with NDD history: {len(token_ids)}")

    total_crashes = 0
    detected_crashes = 0
    undetected_crashes = 0

    is_crashes = {'total': 0, 'detected': 0}
    oos_crashes = {'total': 0, 'detected': 0}

    for tid in token_ids:
        # Get price history
        prices = conn.execute("""
            SELECT date, close FROM crypto_price_history
            WHERE token_id = ? AND close > 0 ORDER BY date ASC
        """, (tid,)).fetchall()

        if len(prices) < 30:
            continue

        # Find crash events (peaks followed by >30% drops within 90 days)
        closes = [(p['date'], p['close']) for p in prices]
        i = 0
        while i < len(closes) - 10:
            peak_date, peak_price = closes[i]
            # Look forward 90 days for >30% drop
            min_price = peak_price
            min_date = peak_date
            for j in range(i + 1, min(i + 91, len(closes))):
                if closes[j][1] < min_price:
                    min_price = closes[j][1]
                    min_date = closes[j][0]

            drop = (peak_price - min_price) / peak_price
            if drop >= CRASH_THRESHOLD_30PCT:
                total_crashes += 1

                # Was this in IS or OOS?
                period = is_crashes if peak_date <= IS_END else oos_crashes
                period['total'] += 1

                # Did NDD detect it? (was NDD < 2.0 at or before crash start?)
                ndd_before = conn.execute("""
                    SELECT MIN(ndd) as min_ndd FROM crypto_ndd_history
                    WHERE token_id = ? AND week_date >= date(?, '-28 days') AND week_date <= ?
                """, (tid, peak_date, min_date)).fetchone()

                if ndd_before and ndd_before['min_ndd'] is not None and ndd_before['min_ndd'] < 2.0:
                    detected_crashes += 1
                    period['detected'] += 1
                else:
                    undetected_crashes += 1

                # Skip ahead past this crash
                i = min(i + 91, len(closes) - 1)
            else:
                i += 7  # Check weekly

    print(f"\n  Total crash events (>30% in 90d): {total_crashes}")
    print(f"  Detected (NDD < 2.0 near crash):  {detected_crashes}")
    print(f"  Undetected:                        {undetected_crashes}")

    if total_crashes > 0:
        recall = detected_crashes / total_crashes
        r_hat, r_lo, r_hi = wilson_ci(detected_crashes, total_crashes)
        print(f"  Recall: {recall:.1%} [{r_lo:.1%}, {r_hi:.1%}]")

    print(f"\n  IS crashes: {is_crashes['total']} total, {is_crashes['detected']} detected")
    if is_crashes['total'] > 0:
        r, lo, hi = wilson_ci(is_crashes['detected'], is_crashes['total'])
        print(f"    IS Recall: {r:.1%} [{lo:.1%}, {hi:.1%}]")

    print(f"  OOS crashes: {oos_crashes['total']} total, {oos_crashes['detected']} detected")
    if oos_crashes['total'] > 0:
        r, lo, hi = wilson_ci(oos_crashes['detected'], oos_crashes['total'])
        print(f"    OOS Recall: {r:.1%} [{lo:.1%}, {hi:.1%}]")


def analyze_crash_probability_table(conn):
    """Validate the crash probability lookup table with observation counts per cell."""
    print(f"\n  {'═' * 60}")
    print(f"  CRASH PROBABILITY TABLE — OBSERVATION COUNTS")
    print(f"  {'═' * 60}")

    # For each (trend, alert_level) combination, count observations
    # This requires matching NDD observations with subsequent price outcomes

    trends = ['FREEFALL', 'FALLING', 'SLIDING', 'STABLE', 'IMPROVING']
    levels = ['SAFE', 'WATCH', 'WARNING', 'DISTRESS', 'CRITICAL']

    # Check if ndd_trend exists in crypto_ndd_daily
    try:
        conn.execute("SELECT ndd_trend FROM crypto_ndd_daily LIMIT 1")
        has_trend = True
    except:
        has_trend = False
        print("  ⚠️ crypto_ndd_daily lacks ndd_trend column — cannot validate table")
        return

    print(f"\n  {'Trend':<12} {'Level':<10} {'Obs':>6} {'Crashed':>8} {'Rate':>8} {'Claimed':>8} {'Match':>6}")
    print(f"  {'─' * 64}")

    from crypto_ndd_daily_v3 import CRASH_PROB_TABLE

    for trend in trends:
        for level in levels:
            key = (trend, level)
            claimed = CRASH_PROB_TABLE.get(key, (None,))[0]

            obs = conn.execute("""
                SELECT COUNT(*) as c FROM crypto_ndd_daily
                WHERE ndd_trend = ? AND alert_level = ?
            """, (trend, level)).fetchone()['c']

            if obs == 0:
                continue

            # Count how many actually crashed >30% in 90 days
            # This requires joining with price data — complex query
            # For now, just report observation counts
            status = "✅" if obs >= 30 else "⚠️" if obs >= 10 else "❌"
            claimed_str = f"{claimed:.0%}" if claimed is not None else "—"
            print(f"  {trend:<12} {level:<10} {obs:>6} {'—':>8} {'—':>8} {claimed_str:>8} {status:>6}")


def main():
    conn = get_db()
    analyze_hc_alerts(conn)

    try:
        analyze_crash_probability_table(conn)
    except Exception as e:
        print(f"\n  Crash prob table analysis skipped: {e}")

    conn.close()
    print(f"\n  Done.")


if __name__ == "__main__":
    main()
