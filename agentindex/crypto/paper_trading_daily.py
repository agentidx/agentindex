#!/usr/bin/env python3
"""
NERQ CRYPTO — PAPER TRADING DAILY NAV
=======================================
Runs daily to calculate NAV for all portfolios.
Fetches current prices, computes P&L, updates NAV.

Run daily at 00:05 UTC via LaunchAgent:
  python3 paper_trading_daily.py
"""

import sqlite3
import os
import sys
import json
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")
PT_DB_PATH = os.path.join(SCRIPT_DIR, "paper_trading.db")
HOLD_DAYS = 90
MAX_CAP = 1.0


def sha256_hash(data_str, prev_hash="GENESIS"):
    payload = f"{prev_hash}|{data_str}"
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()

def get_last_hash(conn, table_name):
    try:
        row = conn.execute(
            f"SELECT data_hash FROM {table_name} ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else "GENESIS"
    except:
        return "GENESIS"


def main():
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"  NERQ Paper Trading — Daily NAV: {today}")

    trust_conn = sqlite3.connect(DB_PATH)
    pt_conn = sqlite3.connect(PT_DB_PATH)

    # Check if already computed today
    existing = pt_conn.execute(
        "SELECT COUNT(*) FROM portfolio_nav WHERE nav_date = ?", (today,)
    ).fetchone()[0]
    if existing > 0:
        print(f"  NAV already computed for {today}. Skipping.")
        return 0

    # Get latest available prices from crypto_trust.db
    # Uses JOIN approach instead of correlated subquery for reliability
    # At midnight, today's prices aren't in yet — this gets the most recent available
    prices = {}
    for r in trust_conn.execute(
        "SELECT p.token_id, p.close, p.date FROM crypto_price_history p "
        "INNER JOIN (SELECT token_id, MAX(date) as max_date FROM crypto_price_history GROUP BY token_id) m "
        "ON p.token_id = m.token_id AND p.date = m.max_date"
    ).fetchall():
        prices[r[0]] = {'price': r[1], 'date': r[2]}
    print(f"  Prices loaded: {len(prices)} tokens")

    # BTC price + regime
    btc_data = prices.get('bitcoin', {})
    btc_price = btc_data.get('price', 0)

    # BTC NAV (buy & hold from $10K)
    btc_start_row = pt_conn.execute(
        "SELECT btc_price FROM portfolio_nav WHERE portfolio = 'ALPHA' ORDER BY id ASC LIMIT 1"
    ).fetchone()
    btc_start = btc_start_row[0] if btc_start_row else btc_price
    btc_nav = 10000.0 * btc_price / btc_start if btc_start > 0 else 10000.0

    # For each portfolio, calculate current NAV
    for portfolio in ['ALPHA', 'DYNAMIC', 'CONSERVATIVE']:
        # Get previous NAV
        prev_nav_row = pt_conn.execute(
            "SELECT nav_value, max_drawdown FROM portfolio_nav "
            "WHERE portfolio = ? ORDER BY id DESC LIMIT 1", (portfolio,)
        ).fetchone()
        if not prev_nav_row:
            print(f"  No previous NAV for {portfolio}. Skipping.")
            continue

        prev_nav = prev_nav_row[0]
        prev_max_dd = prev_nav_row[1]

        # Get active positions for this portfolio
        # Active = signal_month where entry + 90d > today
        positions = pt_conn.execute(
            "SELECT token_id, side, weight, entry_price, position_type, signal_month "
            "FROM portfolio_positions WHERE portfolio = ? "
            "ORDER BY id DESC", (portfolio,)
        ).fetchall()

        # Group by signal_month, only keep active months
        month_positions = defaultdict(list)
        for pos in positions:
            signal_month = pos[5]
            entry_dt = datetime.strptime(f"{signal_month}-01", '%Y-%m-%d')
            exit_dt = entry_dt + timedelta(days=HOLD_DAYS)
            if datetime.strptime(today, '%Y-%m-%d') <= exit_dt:
                month_positions[signal_month].append({
                    'token_id': pos[0], 'side': pos[1], 'weight': pos[2],
                    'entry_price': pos[3], 'position_type': pos[4],
                })

        if not month_positions:
            # No active positions — NAV unchanged
            nav = prev_nav
        else:
            # Calculate weighted return across all active position months
            total_return = 0.0
            total_weight = 0.0

            for signal_month, pos_list in month_positions.items():
                for pos in pos_list:
                    if pos['position_type'] == 'CASH' or pos['entry_price'] is None:
                        continue  # Cash doesn't change

                    current_price = prices.get(pos['token_id'], {}).get('price')
                    if current_price is None or pos['entry_price'] <= 0:
                        continue

                    raw_ret = (current_price - pos['entry_price']) / pos['entry_price']
                    capped_ret = max(-MAX_CAP, min(MAX_CAP, raw_ret))

                    if pos['side'] == 'SHORT':
                        capped_ret = -capped_ret  # Short profits when price goes down

                    total_return += capped_ret * pos['weight']
                    total_weight += pos['weight']

            # NAV = prev_start_nav * (1 + weighted return)
            # For daily tracking, we recalculate from entry prices
            nav = 10000.0 * (1 + total_return)

        # Metrics
        daily_ret = (nav - prev_nav) / prev_nav if prev_nav > 0 else 0
        cum_ret = (nav / 10000.0) - 1
        nav_peak = max(nav, pt_conn.execute(
            "SELECT MAX(nav_value) FROM portfolio_nav WHERE portfolio = ?", (portfolio,)
        ).fetchone()[0] or nav)
        drawdown = (nav - nav_peak) / nav_peak if nav_peak > 0 else 0
        max_dd = min(drawdown, prev_max_dd)

        # Regime
        regime_row = pt_conn.execute(
            "SELECT alpha_regime, dynamic_regime FROM portfolio_regime ORDER BY id DESC LIMIT 1"
        ).fetchone()
        regime = 'UNKNOWN'
        if regime_row:
            regime = regime_row[0] if portfolio == 'ALPHA' else regime_row[1]

        # Log NAV
        nav_data = json.dumps({
            'date': today, 'portfolio': portfolio,
            'nav': round(nav, 2), 'daily_ret': round(daily_ret, 6),
        })
        prev_hash = get_last_hash(pt_conn, "portfolio_nav")
        data_hash = sha256_hash(nav_data, prev_hash)

        pt_conn.execute(
            "INSERT INTO portfolio_nav (nav_date, portfolio, nav_value, daily_return, "
            "cumulative_return, drawdown, max_drawdown, regime, btc_price, btc_nav, "
            "data_hash, prev_hash, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (today, portfolio, round(nav, 2), round(daily_ret, 6),
             round(cum_ret, 6), round(drawdown, 6), round(max_dd, 6),
             regime, btc_price, round(btc_nav, 2),
             data_hash, prev_hash, datetime.now().isoformat())
        )

        print(f"  {portfolio}: NAV=${nav:,.2f} (daily:{daily_ret*100:+.2f}%, cum:{cum_ret*100:+.2f}%, dd:{drawdown*100:.2f}%)")

    # Audit log
    audit_data = json.dumps({'event': 'DAILY_NAV', 'date': today})
    prev_hash = get_last_hash(pt_conn, "audit_log")
    data_hash = sha256_hash(audit_data, prev_hash)
    pt_conn.execute(
        "INSERT INTO audit_log (timestamp, event_type, event_data, data_hash, prev_hash) "
        "VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(), 'DAILY_NAV', audit_data, data_hash, prev_hash)
    )

    pt_conn.commit()
    pt_conn.close()
    trust_conn.close()
    print(f"  ✅ NAV updated for {today}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
