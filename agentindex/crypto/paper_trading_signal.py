#!/usr/bin/env python3
"""
NERQ CRYPTO — PAPER TRADING SIGNAL GENERATOR
==============================================
Exact replication of nav_tracker.py for live paper trading.

Run monthly on 1st:  python3 paper_trading_signal.py [YYYY-MM]
Default: current month.
"""

import sqlite3
import os
import sys
import json
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import numpy as np

# ═══════════════════════════════════════════
# CONFIG — exact nav_tracker.py parameters
# ═══════════════════════════════════════════
WEIGHTS = [0.10, 0.30, 0.30, 0.15, 0.15]
MAX_CAP = 1.0
MIN_VOL = 50000
MIN_COV = 0.70
MIN_NDD_SHORT = 1.5
HOLD_DAYS = 90
BEAR_THRESHOLD_MONTHLY = -0.15
SW = 0.4
NW = 0.6
TOP_N = 5
MAX_TOK = 2
START_CAPITAL = 10000.0

STABLECOINS = {
    'tether','usd-coin','binance-usd','dai','true-usd','paxos-standard','gusd',
    'frax','usdd','tusd','busd','lusd','susd','eurs','usdp','first-digital-usd',
    'ethena-usde','usde','paypal-usd','fdusd','stasis-eur','gemini-dollar','husd',
    'nusd','musd','cusd','terrausd','ust','magic-internet-money','euro-coin',
    'ondo-us-dollar-yield'
}

MAJOR = {
    'bitcoin','ethereum','ripple','solana','cardano','dogecoin','tron','polkadot',
    'avalanche-2','chainlink','shiba-inu','stellar','cosmos','monero',
    'hedera-hashgraph','vechain','internet-computer','litecoin','near','uniswap',
    'pepe','kaspa','sui','sei-network','celestia','arbitrum','optimism',
    'immutable-x','the-graph','render-token','fetch-ai','injective-protocol',
    'bittensor','helium','livepeer','aave','curve-dao-token','maker','lido-dao',
    'the-open-network','axie-infinity','decentraland','the-sandbox','gala',
    'enjincoin','flow','decred','zilliqa','iota','eos','neo','dash','zcash',
    'algorand','fantom','kava','celo','ankr','worldcoin-wld','pyth-network',
    'layerzero','ondo-finance','ethena','jasmycoin','blockstack','elrond-erd-2',
    'crypto-com-chain','filecoin','aptos','mantle','bonk','dogwifcoin','floki',
    'theta-token','quant-network','arweave','stacks','pendle','bitcoin-cash',
    'ethereum-classic','jupiter-exchange-solana','raydium','pi-network'
}

R2C = {r: 'IG_MID' for r in ['A1', 'A2', 'A3']}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")
PT_DB_PATH = os.path.join(SCRIPT_DIR, "paper_trading.db")

# Portfolio allocations
ALLOCATIONS = {
    "ALPHA": {
        "BULL": {"ls_pct": 1.00, "btc_pct": 0.00, "cash_pct": 0.00},
        "BEAR": {"ls_pct": 0.00, "btc_pct": 0.00, "cash_pct": 1.00},
    },
    "DYNAMIC": {
        "BULL": {"ls_pct": 0.20, "btc_pct": 0.40, "cash_pct": 0.40},
        "BEAR": {"ls_pct": 0.30, "btc_pct": 0.10, "cash_pct": 0.60},
    },
    "CONSERVATIVE": {
        "BULL": {"ls_pct": 0.15, "btc_pct": 0.35, "cash_pct": 0.50},
        "BEAR": {"ls_pct": 0.20, "btc_pct": 0.05, "cash_pct": 0.75},
    },
}


# ═══════════════════════════════════════════
# SHA-256 HASH CHAIN
# ═══════════════════════════════════════════
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


# ═══════════════════════════════════════════
# DB SETUP
# ═══════════════════════════════════════════
def init_paper_trading_db(conn):
    """Create paper trading tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date TEXT NOT NULL,
            signal_month TEXT NOT NULL,
            portfolio TEXT NOT NULL,
            regime TEXT NOT NULL,
            btc_monthly_return REAL,
            btc_dd_from_ath REAL,
            n_pairs INTEGER,
            pairs_json TEXT NOT NULL,
            allocation_json TEXT NOT NULL,
            data_hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS portfolio_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date TEXT NOT NULL,
            signal_month TEXT NOT NULL,
            portfolio TEXT NOT NULL,
            position_type TEXT NOT NULL,
            token_id TEXT NOT NULL,
            side TEXT NOT NULL,
            weight REAL NOT NULL,
            entry_price REAL,
            price_date TEXT,
            pair_index INTEGER,
            conviction REAL,
            composite_score REAL,
            ndd_score REAL,
            data_hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS portfolio_nav (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nav_date TEXT NOT NULL,
            portfolio TEXT NOT NULL,
            nav_value REAL NOT NULL,
            daily_return REAL,
            cumulative_return REAL,
            drawdown REAL,
            max_drawdown REAL,
            regime TEXT,
            btc_price REAL,
            btc_nav REAL,
            data_hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS portfolio_regime (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_date TEXT NOT NULL,
            btc_price REAL,
            btc_ath_365d REAL,
            btc_dd_from_ath REAL,
            btc_monthly_return REAL,
            alpha_regime TEXT NOT NULL,
            dynamic_regime TEXT NOT NULL,
            data_hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT NOT NULL,
            data_hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL
        );
    """)
    conn.commit()


# ═══════════════════════════════════════════
# COMPOSITE SCORE (exact nav_tracker.py)
# ═══════════════════════════════════════════
def composite(pillars):
    if not pillars or any(p is None for p in pillars):
        return None
    return sum(p * w for p, w in zip(pillars, WEIGHTS))


# ═══════════════════════════════════════════
# BEAR DETECTION
# ═══════════════════════════════════════════
def detect_regime(trust_conn, target_ym):
    """
    Alpha bear: BTC monthly return < -15% (exact nav_tracker.py logic)
    Dynamic/Conservative bear: BTC DD from 365d ATH > -20%
    """
    # BTC monthly return (nav_tracker.py method)
    entry_str = f"{target_ym}-01"
    entry_dt = datetime.strptime(entry_str, '%Y-%m-%d')
    prev_dt = entry_dt - timedelta(days=30)

    btc_prices = {}
    for r in trust_conn.execute(
        "SELECT date, close FROM crypto_price_history WHERE token_id='bitcoin' ORDER BY date"
    ).fetchall():
        btc_prices[r[0]] = r[1]

    # Find entry price (closest to 1st of month)
    entry_price = None
    for offset in range(8):
        c = (entry_dt + timedelta(days=offset)).strftime('%Y-%m-%d')
        if c in btc_prices:
            entry_price = btc_prices[c]
            break
    # If no future price yet, use latest available
    if entry_price is None:
        latest = max(d for d in btc_prices.keys() if d <= entry_str or True)
        entry_price = btc_prices.get(latest)

    # Find prev price (~30 days before)
    prev_price = None
    for offset in range(8):
        c = (prev_dt + timedelta(days=offset)).strftime('%Y-%m-%d')
        if c in btc_prices:
            prev_price = btc_prices[c]
            break

    btc_monthly_ret = None
    if entry_price and prev_price and prev_price > 0:
        btc_monthly_ret = (entry_price - prev_price) / prev_price

    # BTC DD from 365d ATH
    latest_date = max(btc_prices.keys())
    latest_price = btc_prices[latest_date]
    ath_start = (datetime.strptime(latest_date, '%Y-%m-%d') - timedelta(days=365)).strftime('%Y-%m-%d')
    ath_365d = max(v for d, v in btc_prices.items() if d >= ath_start)
    btc_dd = (latest_price - ath_365d) / ath_365d if ath_365d > 0 else 0

    # Regimes
    alpha_bear = btc_monthly_ret is not None and btc_monthly_ret < BEAR_THRESHOLD_MONTHLY
    dynamic_bear = btc_dd < -0.20

    return {
        'btc_price': latest_price,
        'btc_price_date': latest_date,
        'btc_ath_365d': ath_365d,
        'btc_dd_from_ath': btc_dd,
        'btc_monthly_return': btc_monthly_ret,
        'alpha_regime': 'BEAR' if alpha_bear else 'BULL',
        'dynamic_regime': 'BEAR' if dynamic_bear else 'BULL',
    }


# ═══════════════════════════════════════════
# SIGNAL GENERATION (exact nav_tracker.py)
# ═══════════════════════════════════════════
def generate_signals(trust_conn, target_ym):
    """Generate L/S pair signals using exact nav_tracker.py logic."""

    # Load ratings for this month
    ratings = {}
    for r in trust_conn.execute(
        "SELECT token_id, rating, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5 "
        "FROM crypto_rating_history WHERE year_month = ?", (target_ym,)
    ).fetchall():
        ratings[r[0]] = {
            'rating': r[1],
            'pillars': [r[2], r[3], r[4], r[5], r[6]]
        }

    # Load NDD (use nerq_risk_signals for latest, fallback to ndd_history monthly avg)
    ndd = {}
    # Try risk signals first (most recent)
    for r in trust_conn.execute(
        "SELECT token_id, ndd_current FROM nerq_risk_signals "
        "WHERE signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)"
    ).fetchall():
        ndd[r[0]] = r[1]

    # Fallback: ndd_history monthly average
    for r in trust_conn.execute(
        "SELECT token_id, AVG(ndd) as n FROM crypto_ndd_history "
        "WHERE substr(week_date,1,7) = ? GROUP BY token_id", (target_ym,)
    ).fetchall():
        if r[0] not in ndd:
            ndd[r[0]] = r[1]

    # Load volumes for eligibility
    vols = trust_conn.execute(
        "SELECT token_id, AVG(volume) as v, COUNT(*) as d FROM crypto_price_history GROUP BY token_id"
    ).fetchall()
    total_days = (datetime(2026, 3, 1) - datetime(2021, 1, 1)).days
    eligible = {
        r[0] for r in vols
        if r[0] not in STABLECOINS
        and r[0] in MAJOR
        and (r[1] or 0) >= MIN_VOL
        and r[2] / total_days >= MIN_COV
    }

    # Build IG_MID tokens with composite scores
    ct = defaultdict(list)
    for tid, data in ratings.items():
        if tid not in eligible:
            continue
        cls = R2C.get(data['rating'])
        if not cls:
            continue
        c = composite(data['pillars'])
        if c is None:
            continue
        ct[cls].append({
            'tid': tid,
            'comp': c,
            'ndd': ndd.get(tid, 2.5),
            'rating': data['rating'],
            'pillars': data['pillars'],
        })

    # Generate pairs (exact nav_tracker.py logic)
    all_pairs = []
    for cls, toks in ct.items():
        if len(toks) < 4:
            continue
        toks.sort(key=lambda x: x['comp'], reverse=True)
        n = len(toks)
        q = max(1, n // 4)
        longs = toks[:q]
        shorts = [s for s in toks[-q:] if ndd.get(s['tid'], 3.0) >= MIN_NDD_SHORT]

        for lt in longs:
            for st in shorts:
                if lt['tid'] == st['tid']:
                    continue
                all_pairs.append({
                    'l': lt['tid'], 's': st['tid'],
                    'l_comp': lt['comp'], 's_comp': st['comp'],
                    'l_ndd': lt['ndd'], 's_ndd': st['ndd'],
                    'l_rating': lt['rating'], 's_rating': st['rating'],
                    'spread': lt['comp'] - st['comp'],
                    'ndd_diff': lt['ndd'] - st['ndd'],
                })

    if not all_pairs:
        return [], ct

    # Conviction scoring (exact nav_tracker.py)
    sps = [p['spread'] for p in all_pairs]
    nds = [p['ndd_diff'] for p in all_pairs]
    sr = max(sps) - min(sps) or 1
    nr = max(nds) - min(nds) or 1
    smn, nmn = min(sps), min(nds)

    for p in all_pairs:
        p['conv'] = SW * ((p['spread'] - smn) / sr) + NW * ((p['ndd_diff'] - nmn) / nr)

    all_pairs.sort(key=lambda p: p['conv'], reverse=True)

    # Select top-N with max-token constraint
    sel = []
    tc = Counter()
    for p in all_pairs:
        if tc[p['l']] >= MAX_TOK or tc[p['s']] >= MAX_TOK:
            continue
        sel.append(p)
        tc[p['l']] += 1
        tc[p['s']] += 1

    top = sel[:TOP_N]
    return top, ct


# ═══════════════════════════════════════════
# LOAD ENTRY PRICES
# ═══════════════════════════════════════════
def load_entry_prices(trust_conn, token_ids):
    """Get latest available prices for entry."""
    prices = {}
    for tid in token_ids:
        row = trust_conn.execute(
            "SELECT close, date FROM crypto_price_history "
            "WHERE token_id = ? ORDER BY date DESC LIMIT 1", (tid,)
        ).fetchone()
        if row:
            prices[tid] = {'price': row[0], 'date': row[1]}
    return prices


# ═══════════════════════════════════════════
# MAIN — GENERATE & LOG
# ═══════════════════════════════════════════
def main():
    # Determine target month
    if len(sys.argv) > 1:
        target_ym = sys.argv[1]  # e.g. "2026-03"
    else:
        target_ym = datetime.now().strftime('%Y-%m')

    # Use previous month's ratings (ratings for Feb → signals for Mar)
    dt = datetime.strptime(f"{target_ym}-01", '%Y-%m-%d')
    prev_dt = dt - timedelta(days=1)
    rating_ym = prev_dt.strftime('%Y-%m')

    print("=" * 70)
    print(f"  NERQ PAPER TRADING — SIGNAL GENERATION")
    print(f"  Signal month: {target_ym}")
    print(f"  Rating data:  {rating_ym}")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Connect
    trust_conn = sqlite3.connect(DB_PATH)
    trust_conn.row_factory = sqlite3.Row

    pt_conn = sqlite3.connect(PT_DB_PATH)
    init_paper_trading_db(pt_conn)

    # Check if signals already exist for this month
    existing = pt_conn.execute(
        "SELECT COUNT(*) FROM portfolio_signals WHERE signal_month = ?", (target_ym,)
    ).fetchone()[0]
    if existing > 0:
        print(f"\n  ⚠️  Signals already exist for {target_ym} ({existing} rows).")
        print(f"  Paper trading DB is append-only. Exiting.")
        return 0

    # 1. REGIME DETECTION
    regime = detect_regime(trust_conn, target_ym)
    print(f"\n  BTC Price:          ${regime['btc_price']:,.0f} ({regime['btc_price_date']})")
    print(f"  BTC 365d ATH:       ${regime['btc_ath_365d']:,.0f}")
    print(f"  BTC DD from ATH:    {regime['btc_dd_from_ath']*100:.1f}%")
    print(f"  BTC Monthly Return: {regime['btc_monthly_return']*100:.1f}%" if regime['btc_monthly_return'] else "  BTC Monthly Return: N/A")
    print(f"  Alpha Regime:       {regime['alpha_regime']}")
    print(f"  Dynamic Regime:     {regime['dynamic_regime']}")

    # Log regime
    regime_data = json.dumps(regime, default=str)
    prev_hash = get_last_hash(pt_conn, "portfolio_regime")
    data_hash = sha256_hash(regime_data, prev_hash)
    pt_conn.execute(
        "INSERT INTO portfolio_regime (check_date, btc_price, btc_ath_365d, "
        "btc_dd_from_ath, btc_monthly_return, alpha_regime, dynamic_regime, "
        "data_hash, prev_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (target_ym, regime['btc_price'], regime['btc_ath_365d'],
         regime['btc_dd_from_ath'], regime['btc_monthly_return'],
         regime['alpha_regime'], regime['dynamic_regime'],
         data_hash, prev_hash, datetime.now().isoformat())
    )

    # 2. GENERATE SIGNALS (always, even in bear — for transparency)
    print(f"\n  Generating signals from {rating_ym} ratings...")
    pairs, ct = generate_signals(trust_conn, rating_ym)

    if not pairs:
        print("  ⚠️  NO PAIRS generated. Check data.")
        # Still log the empty signal
        for portfolio in ALLOCATIONS:
            _log_signal(pt_conn, target_ym, portfolio, regime, [], {})
        pt_conn.commit()
        return 1

    # Show IG_MID universe
    ig_mid = ct.get('IG_MID', [])
    print(f"  IG_MID eligible: {len(ig_mid)} tokens")
    q = max(1, len(ig_mid) // 4)
    print(f"  Quartile size: {q}")

    # 3. LOAD ENTRY PRICES
    all_tokens = set()
    for p in pairs:
        all_tokens.add(p['l'])
        all_tokens.add(p['s'])
    all_tokens.add('bitcoin')
    entry_prices = load_entry_prices(trust_conn, all_tokens)

    # 4. DISPLAY PAIRS
    print(f"\n  {'─' * 66}")
    print(f"  TOP {len(pairs)} PAIRS (conviction-ranked):")
    print(f"  {'─' * 66}")
    print(f"  {'#':<3} {'LONG':<22} {'SHORT':<22} {'Conv':>6} {'Spread':>7} {'NDD∆':>6}")
    for i, p in enumerate(pairs):
        print(f"  {i+1:<3} {p['l']:<22} {p['s']:<22} {p['conv']:>6.3f} {p['spread']:>7.1f} {p['ndd_diff']:>6.2f}")

    print(f"\n  Entry prices (latest available):")
    for tid in sorted(all_tokens):
        if tid in entry_prices:
            ep = entry_prices[tid]
            print(f"    {tid:<25} ${ep['price']:>12,.4f}  ({ep['date']})")

    # 5. LOG SIGNALS + POSITIONS FOR EACH PORTFOLIO
    exit_date = (dt + timedelta(days=HOLD_DAYS)).strftime('%Y-%m-%d')

    for portfolio, allocs in ALLOCATIONS.items():
        port_regime = regime['alpha_regime'] if portfolio == 'ALPHA' else regime['dynamic_regime']
        alloc = allocs[port_regime]

        # Alpha in BEAR = skip (no positions)
        if portfolio == 'ALPHA' and port_regime == 'BEAR':
            _log_signal(pt_conn, target_ym, portfolio, regime, pairs, alloc, bear_skip=True)
            print(f"\n  {portfolio}: BEAR SKIP — signals logged but no positions taken")
            continue

        _log_signal(pt_conn, target_ym, portfolio, regime, pairs, alloc)

        # Log positions
        prev_hash = get_last_hash(pt_conn, "portfolio_positions")
        ls_weight_per_pair = alloc['ls_pct'] / len(pairs) if pairs else 0

        print(f"\n  {portfolio} ({port_regime}): L/S={alloc['ls_pct']:.0%}, BTC={alloc['btc_pct']:.0%}, Cash={alloc['cash_pct']:.0%}")

        for i, p in enumerate(pairs):
            for side_key, side_label in [('l', 'LONG'), ('s', 'SHORT')]:
                tid = p[side_key]
                ep = entry_prices.get(tid, {})
                pos_data = json.dumps({
                    'month': target_ym, 'portfolio': portfolio,
                    'token': tid, 'side': side_label, 'pair': i,
                    'price': ep.get('price'), 'date': ep.get('date'),
                })
                data_hash = sha256_hash(pos_data, prev_hash)
                pt_conn.execute(
                    "INSERT INTO portfolio_positions (signal_date, signal_month, portfolio, "
                    "position_type, token_id, side, weight, entry_price, price_date, "
                    "pair_index, conviction, composite_score, ndd_score, "
                    "data_hash, prev_hash, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (datetime.now().strftime('%Y-%m-%d'), target_ym, portfolio,
                     'L/S_PAIR', tid, side_label, ls_weight_per_pair,
                     ep.get('price'), ep.get('date'), i,
                     p['conv'], p[f'{side_key}_comp'], p[f'{side_key}_ndd'],
                     data_hash, prev_hash, datetime.now().isoformat())
                )
                prev_hash = data_hash

        # BTC position
        if alloc['btc_pct'] > 0:
            btc_ep = entry_prices.get('bitcoin', {})
            pos_data = json.dumps({'month': target_ym, 'portfolio': portfolio,
                                   'token': 'bitcoin', 'side': 'LONG', 'type': 'BTC_CORE'})
            data_hash = sha256_hash(pos_data, prev_hash)
            pt_conn.execute(
                "INSERT INTO portfolio_positions (signal_date, signal_month, portfolio, "
                "position_type, token_id, side, weight, entry_price, price_date, "
                "pair_index, conviction, composite_score, ndd_score, "
                "data_hash, prev_hash, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (datetime.now().strftime('%Y-%m-%d'), target_ym, portfolio,
                 'BTC_CORE', 'bitcoin', 'LONG', alloc['btc_pct'],
                 btc_ep.get('price'), btc_ep.get('date'), None,
                 None, None, None,
                 data_hash, prev_hash, datetime.now().isoformat())
            )
            prev_hash = data_hash

        # Cash position
        if alloc['cash_pct'] > 0:
            pos_data = json.dumps({'month': target_ym, 'portfolio': portfolio, 'type': 'CASH'})
            data_hash = sha256_hash(pos_data, prev_hash)
            pt_conn.execute(
                "INSERT INTO portfolio_positions (signal_date, signal_month, portfolio, "
                "position_type, token_id, side, weight, entry_price, price_date, "
                "pair_index, conviction, composite_score, ndd_score, "
                "data_hash, prev_hash, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (datetime.now().strftime('%Y-%m-%d'), target_ym, portfolio,
                 'CASH', 'USD', 'HOLD', alloc['cash_pct'],
                 1.0, datetime.now().strftime('%Y-%m-%d'), None,
                 None, None, None,
                 data_hash, prev_hash, datetime.now().isoformat())
            )
            prev_hash = data_hash

    # 6. LOG INITIAL NAV (Day 0)
    prev_hash = get_last_hash(pt_conn, "portfolio_nav")
    for portfolio in ALLOCATIONS:
        nav_data = json.dumps({'date': target_ym, 'portfolio': portfolio, 'nav': START_CAPITAL})
        data_hash = sha256_hash(nav_data, prev_hash)
        pt_conn.execute(
            "INSERT INTO portfolio_nav (nav_date, portfolio, nav_value, daily_return, "
            "cumulative_return, drawdown, max_drawdown, regime, btc_price, btc_nav, "
            "data_hash, prev_hash, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().strftime('%Y-%m-%d'), portfolio, START_CAPITAL,
             0.0, 0.0, 0.0, 0.0,
             regime['alpha_regime'] if portfolio == 'ALPHA' else regime['dynamic_regime'],
             regime['btc_price'], START_CAPITAL,
             data_hash, prev_hash, datetime.now().isoformat())
        )
        prev_hash = data_hash

    # 7. AUDIT LOG
    audit_data = json.dumps({
        'event': 'SIGNAL_GENERATION',
        'month': target_ym,
        'regime': regime,
        'n_pairs': len(pairs),
        'pairs': [{'l': p['l'], 's': p['s'], 'conv': round(p['conv'], 4)} for p in pairs],
    }, default=str)
    prev_hash = get_last_hash(pt_conn, "audit_log")
    data_hash = sha256_hash(audit_data, prev_hash)
    pt_conn.execute(
        "INSERT INTO audit_log (timestamp, event_type, event_data, data_hash, prev_hash) "
        "VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(), 'SIGNAL_GENERATION', audit_data, data_hash, prev_hash)
    )

    pt_conn.commit()
    pt_conn.close()
    trust_conn.close()

    print(f"\n  {'═' * 66}")
    print(f"  ✅ Paper trading signals logged for {target_ym}")
    print(f"  📁 DB: {PT_DB_PATH}")
    print(f"  📅 Exit date: {exit_date}")
    print(f"  🔗 All entries SHA-256 hash-chained")
    print(f"  {'═' * 66}")
    return 0


def _log_signal(pt_conn, target_ym, portfolio, regime, pairs, alloc, bear_skip=False):
    """Log signal entry with hash chain."""
    port_regime = regime['alpha_regime'] if portfolio == 'ALPHA' else regime['dynamic_regime']
    signal_data = json.dumps({
        'month': target_ym, 'portfolio': portfolio,
        'regime': port_regime, 'bear_skip': bear_skip,
        'pairs': [{'l': p['l'], 's': p['s']} for p in pairs],
        'allocation': alloc,
    })
    prev_hash = get_last_hash(pt_conn, "portfolio_signals")
    data_hash = sha256_hash(signal_data, prev_hash)
    pt_conn.execute(
        "INSERT INTO portfolio_signals (signal_date, signal_month, portfolio, regime, "
        "btc_monthly_return, btc_dd_from_ath, n_pairs, pairs_json, allocation_json, "
        "data_hash, prev_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (datetime.now().strftime('%Y-%m-%d'), target_ym, portfolio,
         f"{port_regime}{'_SKIP' if bear_skip else ''}",
         regime['btc_monthly_return'], regime['btc_dd_from_ath'],
         len(pairs) if not bear_skip else 0,
         json.dumps([{'l': p['l'], 's': p['s'], 'conv': round(p['conv'], 4)} for p in pairs]),
         json.dumps(alloc),
         data_hash, prev_hash, datetime.now().isoformat())
    )


if __name__ == "__main__":
    sys.exit(main())
