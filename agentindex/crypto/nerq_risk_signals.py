#!/usr/bin/env python3
"""
NERQ Risk Intelligence — Daily Signal Generator
================================================
Step 5 in the daily pipeline. Computes for each token:
  1. BTC Beta (rolling 90-day)
  2. Structural Weakness score (0-4)
  3. Structural Strength score (0-4)
  4. Risk classification (SAFE / WATCH / WARNING / CRITICAL)
  5. Stores signals in crypto_trust.db

Tables created/updated:
  - nerq_risk_signals: Daily risk scores per token
  - nerq_risk_alerts: New alerts when status changes

Usage:
  python3 nerq_risk_signals.py           # Full run
  python3 nerq_risk_signals.py --show    # Show current signals

Author: NERQ
Version: 1.0
Date: 2026-02-28
"""

import sqlite3
import math
import os
import sys
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(SCRIPT_DIR, "crypto_trust.db")


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{ts} | {level:<5} | {msg}")


def gidx(pl, date):
    lo, hi = 0, len(pl) - 1
    r = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if pl[mid][0] <= date:
            r = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return r


def compute_vol(pl, idx, w=30):
    if idx < w:
        return None
    rets = []
    for i in range(idx - w + 1, idx + 1):
        if i > 0 and pl[i - 1][1] > 0:
            rets.append((pl[i][1] - pl[i - 1][1]) / pl[i - 1][1])
    if len(rets) < 20:
        return None
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / len(rets)
    return math.sqrt(var) * math.sqrt(365)


def compute_beta(tp, btc, date, lookback=90):
    ti = gidx(tp, date)
    bi = gidx(btc, date)
    if ti is None or bi is None or ti < lookback or bi < lookback:
        return None
    tok_r = []
    btc_r = []
    for i in range(ti - lookback + 1, ti + 1):
        if i <= 0:
            continue
        bj = gidx(btc, tp[i][0])
        if bj is None or bj <= 0:
            continue
        tr = (tp[i][1] - tp[i - 1][1]) / tp[i - 1][1] if tp[i - 1][1] > 0 else 0
        br = (btc[bj][1] - btc[bj - 1][1]) / btc[bj - 1][1] if btc[bj - 1][1] > 0 else 0
        tok_r.append(tr)
        btc_r.append(br)
    if len(tok_r) < 30:
        return None
    bx = np.array(btc_r)
    by = np.array(tok_r)
    vb = np.var(bx)
    if vb < 1e-10:
        return 1.0
    return max(-5, min(10, np.cov(bx, by)[0, 1] / vb))


def main():
    log("=" * 60)
    log("NERQ Risk Intelligence — Daily Signal Generator")
    log("=" * 60)

    if not os.path.exists(DB):
        log(f"Database not found: {DB}", "ERROR")
        return False

    conn = sqlite3.connect(DB)

    # Create tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS nerq_risk_signals (
            token_id TEXT,
            signal_date TEXT,
            btc_beta REAL,
            vol_30d REAL,
            trust_p3 REAL,
            trust_score REAL,
            sig6_structure REAL,
            ndd_current REAL,
            ndd_min_4w REAL,
            p3_decay_3m REAL,
            score_decay_3m REAL,
            structural_weakness INTEGER,
            structural_strength INTEGER,
            risk_level TEXT,
            drawdown_90d REAL,
            weeks_since_ath REAL,
            excess_vol REAL,
            p3_rank REAL,
            details TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (token_id, signal_date)
        );
        CREATE TABLE IF NOT EXISTS nerq_risk_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_date TEXT,
            token_id TEXT,
            symbol TEXT,
            prev_level TEXT,
            new_level TEXT,
            btc_beta REAL,
            structural_weakness INTEGER,
            trust_p3 REAL,
            p3_decay_3m REAL,
            ndd_current REAL,
            message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # Load data
    log("Loading price data...")
    prices = defaultdict(list)
    for tid, d, c in conn.execute(
        "SELECT token_id, date, close FROM crypto_price_history WHERE close > 0 ORDER BY token_id, date"
    ).fetchall():
        prices[tid].append((d, c))
    prices = dict(prices)

    log("Loading NDD history...")
    ndd = defaultdict(list)
    for tid, wd, n, s3, s5, s6 in conn.execute(
        "SELECT token_id, week_date, ndd, signal_3, signal_5, signal_6 "
        "FROM crypto_ndd_history WHERE ndd IS NOT NULL ORDER BY token_id, week_date"
    ).fetchall():
        ndd[tid].append((wd, n, s3 or 0, s5 or 0, s6 or 0))
    ndd = dict(ndd)

    log("Loading rating history...")
    rat = defaultdict(list)
    for tid, ym, sc, p1, p2, p3, p4, p5 in conn.execute(
        "SELECT token_id, year_month, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5 "
        "FROM crypto_rating_history WHERE score IS NOT NULL ORDER BY token_id, year_month"
    ).fetchall():
        rat[tid].append((ym, sc or 0, p1 or 0, p2 or 0, p3 or 0, p4 or 0, p5 or 0))
    rat = dict(rat)

    # Get latest NDD daily for most current data
    ndd_daily = {}
    for tid, rd, n in conn.execute(
        "SELECT token_id, run_date, ndd FROM crypto_ndd_daily WHERE run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)"
    ).fetchall():
        ndd_daily[tid] = (rd, n)

    btc = prices.get('bitcoin')
    if not btc:
        log("No Bitcoin price data!", "ERROR")
        return False

    tl = sorted(set(ndd.keys()) & set(rat.keys()))
    today = datetime.now().strftime("%Y-%m-%d")
    log(f"Tokens to process: {len(tl)}")

    # P3 cross-sectional ranking
    p3_by_month = defaultdict(dict)
    for tid in rat:
        for ym, sc, p1, p2, p3, p4, p5 in rat[tid]:
            p3_by_month[ym][tid] = p3

    # Get previous signals for alert detection
    prev_signals = {}
    for tid, level in conn.execute(
        "SELECT token_id, risk_level FROM nerq_risk_signals "
        "WHERE signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)"
    ).fetchall():
        prev_signals[tid] = level

    # Symbols lookup
    symbols = {}
    for tid, sym in conn.execute("SELECT token_id, symbol FROM crypto_fetch_status").fetchall():
        symbols[tid] = sym

    signals = []
    alerts = []

    for tid in tl:
        tp = prices.get(tid)
        if not tp or len(tp) < 90:
            continue

        ns = ndd[tid]
        rs = rat[tid]
        if not ns or not rs:
            continue

        # Latest data point
        latest_date = tp[-1][0]
        idx = len(tp) - 1
        cl = tp[idx][1]
        if cl <= 0:
            continue

        # Volatility
        vol = compute_vol(tp, idx, 30)
        if vol is None:
            continue

        # Beta
        beta = compute_beta(tp, btc, latest_date)
        if beta is None:
            beta = 1.0

        # Latest NDD
        latest_ndd = ns[-1]
        nv = latest_ndd[1]
        s6 = latest_ndd[4]

        # Use daily NDD if available and more recent
        if tid in ndd_daily:
            nv = ndd_daily[tid][1] or nv

        # NDD min 4 weeks
        nm4 = min(n[1] for n in ns[-4:]) if len(ns) >= 4 else nv

        # Latest rating
        tym = latest_date[:7]
        ri = None
        for j, (ym, sc, p1, p2, p3, p4, p5) in enumerate(rs):
            if ym <= tym:
                ri = j
            else:
                break
        if ri is None:
            continue

        _, sc_now, p1_now, p2_now, p3_now, p4_now, p5_now = rs[ri]

        # P3 decay (3 month)
        ym_3m = (datetime.strptime(tym + "-01", "%Y-%m-%d") - timedelta(days=95)).strftime("%Y-%m")
        p3_3m = p3_now
        sc_3m = sc_now
        for ym2, sc2, _, _, p32, _, _ in rs:
            if ym2 <= ym_3m:
                p3_3m = p32
                sc_3m = sc2
        p3_decay = p3_now - p3_3m
        sc_decay = sc_now - sc_3m

        # Drawdown 90d
        h90 = max(tp[i][1] for i in range(max(0, idx - 89), idx + 1))
        dd90 = (cl - h90) / h90 if h90 > 0 else 0

        # Weeks since ATH
        ath = max(p for _, p in tp)
        if ath == cl:
            weeks_ath = 0.0
        else:
            for back in range(idx, -1, -1):
                if tp[back][1] >= ath * 0.99:
                    weeks_ath = (datetime.strptime(latest_date, "%Y-%m-%d") -
                                 datetime.strptime(tp[back][0], "%Y-%m-%d")).days / 7.0
                    break
            else:
                weeks_ath = 52.0

        # Excess vol
        bv = compute_vol(btc, gidx(btc, latest_date), 30)
        excess_vol = max(0, vol - abs(beta) * bv) if bv and bv > 0 else 0

        # P3 rank
        month_p3s = p3_by_month.get(tym, {})
        p3_rank = (sum(1 for v in month_p3s.values() if v < p3_now) /
                   max(len(month_p3s), 1)) if len(month_p3s) > 1 else 0.5

        # STRUCTURAL WEAKNESS (0-4)
        sw = int(sum([
            1 if p3_now < 40 else 0,
            1 if s6 < 2.5 else 0,
            1 if nm4 < 3.0 else 0,
            1 if p3_decay < -15 else 0
        ]))

        # STRUCTURAL STRENGTH (0-4)
        ss = int(sum([
            1 if p3_now >= 60 else 0,
            1 if s6 >= 4.0 else 0,
            1 if nm4 >= 3.5 else 0,
            1 if p3_decay >= 10 else 0
        ]))

        # RISK LEVEL
        if sw >= 3:
            risk_level = "CRITICAL"
        elif sw >= 2:
            risk_level = "WARNING"
        elif sw >= 1 or p3_now < 50:
            risk_level = "WATCH"
        else:
            risk_level = "SAFE"

        # Build details JSON
        import json
        details = json.dumps({
            "p3": round(p3_now, 1),
            "p3_3m_ago": round(p3_3m, 1),
            "sig6": round(s6, 2),
            "ndd": round(nv, 2),
            "ndd_min_4w": round(nm4, 2),
            "beta": round(beta, 2),
            "vol_30d": round(vol, 3),
            "dd_90d": round(dd90 * 100, 1),
            "weeks_ath": round(weeks_ath, 1),
            "weakness_signals": {
                "p3_below_40": p3_now < 40,
                "sig6_below_2.5": s6 < 2.5,
                "ndd_below_3": nm4 < 3.0,
                "p3_decay_15": p3_decay < -15
            },
            "strength_signals": {
                "p3_above_60": p3_now >= 60,
                "sig6_above_4": s6 >= 4.0,
                "ndd_above_3.5": nm4 >= 3.5,
                "p3_improving_10": p3_decay >= 10
            }
        })

        signals.append((
            tid, today, beta, vol, p3_now, sc_now, s6, nv, nm4,
            p3_decay, sc_decay, sw, ss, risk_level, dd90,
            weeks_ath, excess_vol, p3_rank, details
        ))

        # Check for level changes → alerts
        prev = prev_signals.get(tid)
        if prev and prev != risk_level:
            severity_order = {"SAFE": 0, "WATCH": 1, "WARNING": 2, "CRITICAL": 3}
            if severity_order.get(risk_level, 0) > severity_order.get(prev, 0):
                # Escalation
                sym = symbols.get(tid, tid)
                if risk_level == "CRITICAL":
                    msg = (f"⚠️ CRITICAL: {sym} — structural weakness {sw}/4. "
                           f"P3={p3_now:.0f} (decay {p3_decay:+.0f}), NDD={nv:.2f}, "
                           f"sig6={s6:.1f}, beta={beta:.2f}")
                elif risk_level == "WARNING":
                    msg = (f"⚡ WARNING: {sym} — structural weakness {sw}/4. "
                           f"P3={p3_now:.0f}, NDD={nv:.2f}")
                else:
                    msg = f"📋 WATCH: {sym} elevated to watch. P3={p3_now:.0f}"

                alerts.append((
                    today, tid, sym, prev, risk_level, beta, sw,
                    p3_now, p3_decay, nv, msg
                ))

    # Write signals
    log(f"Writing {len(signals)} signals...")
    conn.executemany(
        "INSERT OR REPLACE INTO nerq_risk_signals "
        "(token_id, signal_date, btc_beta, vol_30d, trust_p3, trust_score, "
        "sig6_structure, ndd_current, ndd_min_4w, p3_decay_3m, score_decay_3m, "
        "structural_weakness, structural_strength, risk_level, drawdown_90d, "
        "weeks_since_ath, excess_vol, p3_rank, details) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        signals
    )

    # Write alerts
    if alerts:
        log(f"Writing {len(alerts)} alerts...")
        conn.executemany(
            "INSERT INTO nerq_risk_alerts "
            "(alert_date, token_id, symbol, prev_level, new_level, btc_beta, "
            "structural_weakness, trust_p3, p3_decay_3m, ndd_current, message) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            alerts
        )

    conn.commit()

    # Summary
    levels = defaultdict(int)
    for s in signals:
        levels[s[13]] += 1

    log("")
    log("=" * 40)
    log(f"  SAFE:     {levels.get('SAFE', 0):>4} tokens")
    log(f"  WATCH:    {levels.get('WATCH', 0):>4} tokens")
    log(f"  WARNING:  {levels.get('WARNING', 0):>4} tokens")
    log(f"  CRITICAL: {levels.get('CRITICAL', 0):>4} tokens")
    log(f"  Alerts:   {len(alerts):>4} level changes")
    log("=" * 40)

    if alerts:
        log("\nNew Alerts:")
        for a in alerts:
            log(f"  {a[10]}")

    conn.close()
    return True


def show_signals():
    """Display current risk signals."""
    conn = sqlite3.connect(DB)
    latest = conn.execute("SELECT MAX(signal_date) FROM nerq_risk_signals").fetchone()[0]
    if not latest:
        print("No signals found. Run nerq_risk_signals.py first.")
        return

    print(f"\nNERQ Risk Signals — {latest}")
    print("=" * 90)

    for level in ["CRITICAL", "WARNING", "WATCH", "SAFE"]:
        rows = conn.execute(
            "SELECT s.token_id, f.symbol, s.btc_beta, s.trust_p3, s.p3_decay_3m, "
            "s.ndd_current, s.sig6_structure, s.structural_weakness, s.drawdown_90d "
            "FROM nerq_risk_signals s "
            "LEFT JOIN crypto_fetch_status f ON s.token_id = f.token_id "
            "WHERE s.signal_date = ? AND s.risk_level = ? "
            "ORDER BY s.structural_weakness DESC, s.trust_p3 ASC",
            (latest, level)
        ).fetchall()

        if not rows:
            continue

        emoji = {"CRITICAL": "🔴", "WARNING": "🟡", "WATCH": "🟠", "SAFE": "🟢"}[level]
        print(f"\n{emoji} {level} ({len(rows)} tokens):")
        print(f"  {'Token':>25} {'Symbol':>8} {'Beta':>6} {'P3':>5} {'dP3':>6} {'NDD':>5} {'sig6':>5} {'SW':>3} {'DD90':>7}")
        for r in rows[:20]:
            print(f"  {r[0]:>25} {(r[1] or ''):>8} {r[2]:>5.2f} {r[3]:>5.1f} {r[4]:>+5.0f} {r[5]:>5.2f} {r[6]:>5.2f} {r[7]:>3} {r[8]*100:>+6.1f}%")
        if len(rows) > 20:
            print(f"  ... and {len(rows) - 20} more")

    conn.close()


if __name__ == "__main__":
    if "--show" in sys.argv:
        show_signals()
    else:
        success = main()
        sys.exit(0 if success else 1)
