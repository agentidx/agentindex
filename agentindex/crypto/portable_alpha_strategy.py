#!/usr/bin/env python3
"""
NERQ CRYPTO — portable_alpha_strategy.py
==========================================
Sprint 2.0 Blockerare 1: Reconcilierar nav_tracker.py och crypto_pairs_backtest.py

Implementerar nav_tracker.py:s EXAKTA strategi med:
  1. Korrekt IS/OOS-separation
  2. Execution costs (0.5% per trade)
  3. Tre varianter (Conservative/Growth/Aggressive)
  4. Konfidensintervall via Wilson score
  5. Jämförelse med BTC buy-and-hold

Strategi (replikerar nav_tracker.py):
  - Universum: MAJOR tokens, exkl stablecoins
  - Rating-klass: IG_MID only (A1, A2, A3)
  - Par-selektion: Top-5 per conviction score (40% spread + 60% NDD diff)
  - Max 2 par per token
  - Bear detection: BTC monthly return < -15% → skip
  - Holding: 90 dagar
  - Return cap: ±100% per leg

GO/NO-GO beslut baseras på OOS-resultaten.

Kör:  python3 portable_alpha_strategy.py
"""

import sqlite3
import os
import sys
import json
import math
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import numpy as np

# ─────────────────────────────────────────────────────────────
# CONFIG — Exakt replikation av nav_tracker.py
# ─────────────────────────────────────────────────────────────
DB_NAME = "crypto_trust.db"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)

# Periods
IN_SAMPLE_START = "2021-01-01"
IN_SAMPLE_END = "2023-12-31"
OUT_SAMPLE_START = "2024-01-01"
OUT_SAMPLE_END = "2025-12-31"

# Strategy params (from nav_tracker.py)
WEIGHTS = [0.10, 0.30, 0.30, 0.15, 0.15]  # P1-P5 pillar weights
MAX_CAP = 1.0          # ±100% return cap per leg
MIN_VOL = 50000        # Min avg daily volume
MIN_COV = 0.70         # Min price coverage
MIN_NDD_SHORT = 1.5    # Don't short tokens with NDD below this
HOLD_DAYS = 90         # Holding period
BEAR_THRESHOLD = -0.15 # BTC monthly return threshold for skip
SW = 0.4               # Spread weight in conviction score
NW = 0.6               # NDD diff weight in conviction score
TOP_N = 5              # Top pairs per month
MAX_TOK = 2            # Max appearances per token

# Execution costs
EXEC_COST_PER_TRADE = 0.005  # 0.5% per trade (entry or exit)
ROUND_TRIP_COST = EXEC_COST_PER_TRADE * 4  # 2 legs × entry + exit = 4 trades

# Portfolio variants
VARIANTS = {
    "Conservative": {"pairs_pct": 0.20, "cash_pct": 0.80, "risk_score": "5/5"},
    "Growth":       {"pairs_pct": 0.40, "cash_pct": 0.60, "risk_score": "3/5"},
    "Aggressive":   {"pairs_pct": 0.60, "cash_pct": 0.40, "risk_score": "1/5"},
}

START_CAPITAL = 10000

# Rating class — ONLY IG_MID (from nav_tracker.py)
RATING_TO_CLASS = {}
for r in ['A1', 'A2', 'A3']:
    RATING_TO_CLASS[r] = 'IG_MID'

# Stablecoins (from nav_tracker.py)
STABLECOINS = {
    'tether','usd-coin','binance-usd','dai','true-usd','paxos-standard','gusd',
    'frax','usdd','tusd','busd','lusd','susd','eurs','usdp','first-digital-usd',
    'ethena-usde','usde','paypal-usd','fdusd','stasis-eur','gemini-dollar','husd',
    'nusd','musd','cusd','terrausd','ust','magic-internet-money','euro-coin',
    'ondo-us-dollar-yield'
}

# MAJOR tokens (from nav_tracker.py)
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

# ─────────────────────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────────────────────
def get_db():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_data(conn, start, end):
    """Load all required data for a period."""
    # Prices
    prices = defaultdict(dict)
    for r in conn.execute(
        "SELECT token_id, date, close FROM crypto_price_history WHERE date >= ? AND date <= ? ORDER BY token_id, date",
        (start, end)
    ).fetchall():
        prices[r['token_id']][r['date']] = r['close']

    # Volumes & coverage
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    total_days = (end_dt - start_dt).days

    vols = conn.execute(
        "SELECT token_id, AVG(volume) as v, COUNT(*) as d FROM crypto_price_history WHERE date >= ? AND date <= ? GROUP BY token_id",
        (start, end)
    ).fetchall()

    eligible = set()
    for r in vols:
        tid = r['token_id']
        if tid.lower() in STABLECOINS:
            continue
        if tid not in MAJOR:
            continue
        if (r['v'] or 0) < MIN_VOL:
            continue
        if r['d'] / max(total_days, 1) < MIN_COV:
            continue
        eligible.add(tid)

    # Ratings
    start_ym = start[:7]
    end_ym = end[:7]
    ratings = {}
    for r in conn.execute(
        "SELECT token_id, year_month, rating, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5 FROM crypto_rating_history WHERE year_month >= ? AND year_month <= ?",
        (start_ym, end_ym)
    ).fetchall():
        ratings[(r['token_id'], r['year_month'])] = {
            'rating': r['rating'],
            'pillars': [r['pillar_1'], r['pillar_2'], r['pillar_3'], r['pillar_4'], r['pillar_5']]
        }

    # NDD monthly
    ndd = {}
    for r in conn.execute(
        "SELECT token_id, substr(week_date,1,7) as ym, AVG(ndd) as n FROM crypto_ndd_history WHERE week_date >= ? AND week_date <= ? GROUP BY token_id, substr(week_date,1,7)",
        (start, end)
    ).fetchall():
        ndd[(r['token_id'], r['ym'])] = r['n']

    # BTC prices (for bear detection)
    btc = {}
    for r in conn.execute(
        "SELECT date, close FROM crypto_price_history WHERE token_id='bitcoin' AND date >= ? AND date <= ? ORDER BY date",
        (start, end)
    ).fetchall():
        btc[r['date']] = r['close']

    return dict(prices), eligible, ratings, ndd, btc


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def composite(pillars):
    if not pillars or any(p is None for p in pillars):
        return None
    return sum(p * w for p, w in zip(pillars, WEIGHTS))


def closest_date(dates_set, target_str, max_offset=7):
    target = datetime.strptime(target_str, '%Y-%m-%d')
    for offset in range(max_offset + 1):
        for delta in [offset, -offset]:
            candidate = (target + timedelta(days=delta)).strftime('%Y-%m-%d')
            if candidate in dates_set:
                return candidate
    return None


def btc_monthly_return(btc, ym):
    """Calculate BTC monthly return for a given YYYY-MM."""
    entry_str = f"{ym}-01"
    entry_dt = datetime.strptime(entry_str, '%Y-%m-%d')
    prev_dt = entry_dt - timedelta(days=30)
    prev_str = prev_dt.strftime('%Y-%m-%d')

    entry_price = None
    for offset in range(8):
        c = (entry_dt + timedelta(days=offset)).strftime('%Y-%m-%d')
        if c in btc:
            entry_price = btc[c]
            break

    prev_price = None
    for offset in range(8):
        c = (prev_dt + timedelta(days=offset)).strftime('%Y-%m-%d')
        if c in btc:
            prev_price = btc[c]
            break

    if entry_price and prev_price and prev_price > 0:
        return (entry_price - prev_price) / prev_price
    return None


def wilson_ci(successes, total, z=1.96):
    """Wilson score confidence interval for a proportion."""
    if total == 0:
        return 0, 0, 0
    p_hat = successes / total
    denom = 1 + z**2 / total
    center = (p_hat + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total) / denom
    lo = max(0, center - spread)
    hi = min(1, center + spread)
    return p_hat, lo, hi


# ─────────────────────────────────────────────────────────────
# STRATEGY ENGINE (replicates nav_tracker.py exactly)
# ─────────────────────────────────────────────────────────────
def run_strategy(prices, eligible, ratings, ndd, btc, start, end, label=""):
    """Run the exact nav_tracker.py strategy and return monthly returns."""
    results = {
        'monthly_returns': {},       # ym → decimal return (or 'SKIP'/'NO_PAIRS')
        'monthly_pairs': {},         # ym → list of pair dicts
        'all_pair_returns': [],      # flat list of all pair returns
        'months_skipped': 0,
        'months_no_pairs': 0,
        'months_traded': 0,
    }

    cur = datetime.strptime(start, '%Y-%m-%d')
    end_dt = datetime.strptime(end, '%Y-%m-%d')

    while cur <= end_dt:
        ym = cur.strftime('%Y-%m')
        entry = cur.strftime('%Y-%m-%d')

        # Bear detection
        br = btc_monthly_return(btc, ym)
        if br is not None and br < BEAR_THRESHOLD:
            results['monthly_returns'][ym] = 'SKIP'
            results['months_skipped'] += 1
            cur = _next_month(cur)
            continue

        # Find eligible tokens with IG_MID rating this month
        ct = defaultdict(list)
        for (tid, m), data in ratings.items():
            if m != ym or tid not in eligible:
                continue
            cls = RATING_TO_CLASS.get(data['rating'])
            if not cls:
                continue
            c = composite(data['pillars'])
            if c is None:
                continue
            ct[cls].append({
                'tid': tid,
                'comp': c,
                'ndd': ndd.get((tid, ym), 2.5)
            })

        # Generate pairs
        all_pairs = []
        for cls, toks in ct.items():
            if len(toks) < 4:
                continue
            toks.sort(key=lambda x: x['comp'], reverse=True)
            n = len(toks)
            q = max(1, n // 4)
            longs = toks[:q]
            shorts = [s for s in toks[-q:] if ndd.get((s['tid'], ym), 3.0) >= MIN_NDD_SHORT]

            for lt in longs:
                for st in shorts:
                    if lt['tid'] == st['tid']:
                        continue
                    all_pairs.append({
                        'l': lt['tid'], 's': st['tid'],
                        'spread': lt['comp'] - st['comp'],
                        'ndd_diff': lt['ndd'] - st['ndd']
                    })

        if not all_pairs:
            results['monthly_returns'][ym] = 'NO_PAIRS'
            results['months_no_pairs'] += 1
            cur = _next_month(cur)
            continue

        # Conviction scoring & selection (exact nav_tracker.py logic)
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

        # Calculate returns for selected pairs
        alphas = []
        pair_details = []
        for p in top:
            exit_str = (datetime.strptime(entry, '%Y-%m-%d') + timedelta(days=HOLD_DAYS)).strftime('%Y-%m-%d')

            lp = prices.get(p['l'], {})
            sp = prices.get(p['s'], {})
            if not lp or not sp:
                continue

            el = closest_date(set(lp.keys()), entry)
            es = closest_date(set(sp.keys()), entry)
            xl = closest_date(set(lp.keys()), exit_str)
            xs = closest_date(set(sp.keys()), exit_str)

            if not all([el, es, xl, xs]) or lp[el] <= 0 or sp[es] <= 0:
                continue

            lr = max(-MAX_CAP, min(MAX_CAP, (lp[xl] - lp[el]) / lp[el]))
            sr_ = max(-MAX_CAP, min(MAX_CAP, (sp[xs] - sp[es]) / sp[es]))
            gross_alpha = lr - sr_
            net_alpha = gross_alpha - ROUND_TRIP_COST

            alphas.append(net_alpha)
            pair_details.append({
                'long': p['l'], 'short': p['s'],
                'long_ret': lr, 'short_ret': sr_,
                'gross_alpha': gross_alpha, 'net_alpha': net_alpha,
                'entry': entry, 'exit': exit_str,
                'spread': p['spread'], 'conviction': p['conv'],
                'hit': 1 if net_alpha > 0 else 0,
            })

        if alphas:
            mo_ret = np.mean(alphas)
            results['monthly_returns'][ym] = mo_ret
            results['monthly_pairs'][ym] = pair_details
            results['all_pair_returns'].extend(pair_details)
            results['months_traded'] += 1
        else:
            results['monthly_returns'][ym] = 'NO_PAIRS'
            results['months_no_pairs'] += 1

        cur = _next_month(cur)

    return results


def _next_month(dt):
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1, day=1)
    return dt.replace(month=dt.month + 1, day=1)


# ─────────────────────────────────────────────────────────────
# NAV TRACKING & METRICS
# ─────────────────────────────────────────────────────────────
def compute_nav(results, variant_name, btc, start, end):
    """Compute NAV for a given variant."""
    v = VARIANTS[variant_name]
    pairs_pct = v['pairs_pct']
    cash_pct = v['cash_pct']

    nav = START_CAPITAL
    nav_peak = START_CAPITAL
    nav_maxdd = 0.0
    monthly_navs = {}

    btc_start_price = None
    for d in sorted(btc.keys()):
        if d >= start:
            btc_start_price = btc[d]
            break

    for ym in sorted(results['monthly_returns'].keys()):
        ret = results['monthly_returns'][ym]

        if ret == 'SKIP' or ret == 'NO_PAIRS':
            pass  # NAV unchanged
        else:
            # Pairs portion gets the return, cash portion stays flat
            pairs_return = ret * pairs_pct
            nav = nav * (1 + pairs_return)

        nav_peak = max(nav_peak, nav)
        dd = (nav - nav_peak) / nav_peak
        nav_maxdd = min(nav_maxdd, dd)

        monthly_navs[ym] = {
            'nav': nav,
            'total_return': (nav / START_CAPITAL - 1),
            'dd': dd,
            'max_dd': nav_maxdd,
        }

    # BTC comparison
    btc_end_price = None
    for d in sorted(btc.keys(), reverse=True):
        if d <= end:
            btc_end_price = btc[d]
            break

    btc_return = 0
    if btc_start_price and btc_end_price:
        btc_return = (btc_end_price - btc_start_price) / btc_start_price

    return monthly_navs, nav, nav_maxdd, btc_return


def compute_metrics(results):
    """Compute aggregate metrics from strategy results."""
    pairs = results['all_pair_returns']
    if not pairs:
        return {}

    alphas = [p['net_alpha'] for p in pairs]
    hits = sum(p['hit'] for p in pairs)
    n = len(pairs)

    avg_alpha = np.mean(alphas)
    median_alpha = np.median(alphas)
    std_alpha = np.std(alphas) if n > 1 else 1.0

    # Sharpe (annualized from quarterly)
    sharpe = (avg_alpha / std_alpha) * np.sqrt(4) if std_alpha > 0 else 0

    # Wilson confidence interval for hit rate
    hit_rate, hit_lo, hit_hi = wilson_ci(hits, n)

    # Monthly returns for Sharpe calculation
    monthly_rets = [v for v in results['monthly_returns'].values()
                    if isinstance(v, (int, float))]
    monthly_sharpe = 0
    if monthly_rets and len(monthly_rets) > 1:
        ms = np.std(monthly_rets)
        if ms > 0:
            monthly_sharpe = (np.mean(monthly_rets) / ms) * np.sqrt(12)

    return {
        'total_pairs': n,
        'hit_rate': hit_rate,
        'hit_rate_ci': (hit_lo, hit_hi),
        'avg_alpha': avg_alpha,
        'median_alpha': median_alpha,
        'std_alpha': std_alpha,
        'sharpe_quarterly': sharpe,
        'sharpe_monthly': monthly_sharpe,
        'months_traded': results['months_traded'],
        'months_skipped': results['months_skipped'],
        'months_no_pairs': results['months_no_pairs'],
        'gross_avg': np.mean([p['gross_alpha'] for p in pairs]),
        'exec_cost_total': ROUND_TRIP_COST * n,
    }


# ─────────────────────────────────────────────────────────────
# REPORTING
# ─────────────────────────────────────────────────────────────
def print_results(is_metrics, oos_metrics, is_navs, oos_navs, btc_ret_is, btc_ret_oos):
    """Print comprehensive results and GO/NO-GO decision."""

    print("\n" + "=" * 90)
    print("  NERQ PORTABLE ALPHA — RECONCILIATION RESULTS")
    print("  Strategy: nav_tracker.py replication (IG_MID, top-5 conviction, bear skip)")
    print(f"  Execution cost: {ROUND_TRIP_COST*100:.1f}% round-trip per pair")
    print("=" * 90)

    # Metrics comparison
    print(f"\n  {'Metric':<30} {'In-Sample':>15} {'Out-of-Sample':>15}")
    print(f"  {'─' * 62}")

    for label, is_v, oos_v, fmt in [
        ("Total Pairs", is_metrics.get('total_pairs', 0), oos_metrics.get('total_pairs', 0), "d"),
        ("Hit Rate", is_metrics.get('hit_rate', 0), oos_metrics.get('hit_rate', 0), ".1%"),
        ("  95% CI Low", is_metrics.get('hit_rate_ci', (0, 0))[0], oos_metrics.get('hit_rate_ci', (0, 0))[0], ".1%"),
        ("  95% CI High", is_metrics.get('hit_rate_ci', (0, 0))[1], oos_metrics.get('hit_rate_ci', (0, 0))[1], ".1%"),
        ("Avg Alpha (net)", is_metrics.get('avg_alpha', 0), oos_metrics.get('avg_alpha', 0), ".2%"),
        ("Avg Alpha (gross)", is_metrics.get('gross_avg', 0), oos_metrics.get('gross_avg', 0), ".2%"),
        ("Median Alpha (net)", is_metrics.get('median_alpha', 0), oos_metrics.get('median_alpha', 0), ".2%"),
        ("Sharpe (quarterly)", is_metrics.get('sharpe_quarterly', 0), oos_metrics.get('sharpe_quarterly', 0), ".2f"),
        ("Sharpe (monthly NAV)", is_metrics.get('sharpe_monthly', 0), oos_metrics.get('sharpe_monthly', 0), ".2f"),
        ("Months Traded", is_metrics.get('months_traded', 0), oos_metrics.get('months_traded', 0), "d"),
        ("Months Skipped (bear)", is_metrics.get('months_skipped', 0), oos_metrics.get('months_skipped', 0), "d"),
    ]:
        if fmt == "d":
            print(f"  {label:<30} {is_v:>15} {oos_v:>15}")
        elif fmt.endswith("%"):
            print(f"  {label:<30} {is_v:>14{fmt}} {oos_v:>14{fmt}}")
        else:
            print(f"  {label:<30} {is_v:>15{fmt}} {oos_v:>15{fmt}}")

    # NAV per variant
    print(f"\n  {'─' * 62}")
    print(f"  NAV RESULTS (start: ${START_CAPITAL:,})")
    print(f"  {'─' * 62}")

    for variant in VARIANTS:
        is_nav_data = is_navs[variant]
        oos_nav_data = oos_navs[variant]
        v = VARIANTS[variant]

        is_final = is_nav_data['final_nav']
        oos_final = oos_nav_data['final_nav']
        is_dd = is_nav_data['max_dd']
        oos_dd = oos_nav_data['max_dd']

        print(f"\n  {variant} ({v['pairs_pct']:.0%} pairs / {v['cash_pct']:.0%} cash) — Risk: {v['risk_score']}")
        print(f"    IS NAV:  ${is_final:>12,.0f} ({(is_final/START_CAPITAL-1)*100:>+7.1f}%)  MaxDD: {is_dd*100:>6.1f}%")
        print(f"    OOS NAV: ${oos_final:>12,.0f} ({(oos_final/START_CAPITAL-1)*100:>+7.1f}%)  MaxDD: {oos_dd*100:>6.1f}%")

    print(f"\n  BTC Buy & Hold:")
    print(f"    IS:  {btc_ret_is*100:>+7.1f}%")
    print(f"    OOS: {btc_ret_oos*100:>+7.1f}%")

    # GO/NO-GO
    print(f"\n  {'═' * 62}")
    print("  GO/NO-GO DECISION")
    print(f"  {'═' * 62}")

    oos_hr = oos_metrics.get('hit_rate', 0)
    oos_alpha = oos_metrics.get('avg_alpha', 0)
    oos_median = oos_metrics.get('median_alpha', 0)
    oos_sharpe = oos_metrics.get('sharpe_quarterly', 0)

    checks = [
        ("OOS Hit Rate > 55%", oos_hr > 0.55, f"{oos_hr:.1%}"),
        ("OOS Avg Alpha > 0% (net)", oos_alpha > 0, f"{oos_alpha:.2%}"),
        ("OOS Median Alpha > 0% (net)", oos_median > 0, f"{oos_median:.2%}"),
        ("OOS Sharpe > 0.3", oos_sharpe > 0.3, f"{oos_sharpe:.2f}"),
        ("Conservative OOS return > 0%", oos_navs['Conservative']['final_nav'] > START_CAPITAL,
         f"{(oos_navs['Conservative']['final_nav']/START_CAPITAL-1)*100:+.1f}%"),
    ]

    all_pass = True
    for name, passed, val in checks:
        icon = "✅" if passed else "❌"
        print(f"  {icon} {name}: {val}")
        if not passed:
            all_pass = False

    critical_pass = oos_alpha > 0 and oos_hr > 0.55
    partial = oos_alpha > 0 or oos_median > 0

    print(f"\n  {'═' * 62}")
    if all_pass:
        print("  🎯 GO — Pairs alpha reconcilierad. Fortsätt med full berättelse.")
        print("  → Använd Conservative-varianten som primär i kommunikation.")
        print("  → Inkludera execution costs i alla siffror.")
        decision = "GO"
    elif partial:
        print("  ⚠️  DELVIS GO — Positiv alpha men ej alla kriterier.")
        print("  → Använd lägre, OOS-baserade siffror i kommunikation.")
        print("  → Framhäv Sharpe och drawdown-reduktion, ej absolut avkastning.")
        print("  → Conservative-varianten som sekundärt bevis, ej primär berättelse.")
        decision = "PARTIAL"
    else:
        print("  ❌ NO-GO — Pairs alpha ej verifierbar OOS.")
        print("  → Stryk ALL pairs/alpha/fond-kommunikation.")
        print("  → Fokus 100%: NDD + HC Alert + Contagion + Stresstest.")
        decision = "NO_GO"
    print(f"  {'═' * 62}")

    return decision


# ─────────────────────────────────────────────────────────────
# SAVE
# ─────────────────────────────────────────────────────────────
def save_results(conn, is_metrics, oos_metrics, is_navs, oos_navs, decision):
    """Save results to DB — uses EXISTING crypto_portable_alpha_backtest table schema."""

    # The table already exists with a different schema (variant/period/month/regime).
    # We create a NEW results table to avoid conflicts.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_portable_alpha_reconciliation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT, version TEXT,
            is_pairs INTEGER, oos_pairs INTEGER,
            is_hit_rate REAL, oos_hit_rate REAL,
            oos_hit_rate_ci_lo REAL, oos_hit_rate_ci_hi REAL,
            is_avg_alpha REAL, oos_avg_alpha REAL,
            is_median_alpha REAL, oos_median_alpha REAL,
            is_sharpe REAL, oos_sharpe REAL,
            conservative_is_nav REAL, conservative_oos_nav REAL,
            growth_is_nav REAL, growth_oos_nav REAL,
            aggressive_is_nav REAL, aggressive_oos_nav REAL,
            conservative_oos_maxdd REAL, growth_oos_maxdd REAL, aggressive_oos_maxdd REAL,
            exec_cost_per_trade REAL,
            decision TEXT,
            params TEXT
        )
    """)

    conn.execute("""
        INSERT INTO crypto_portable_alpha_reconciliation
        (run_date, version, is_pairs, oos_pairs,
         is_hit_rate, oos_hit_rate, oos_hit_rate_ci_lo, oos_hit_rate_ci_hi,
         is_avg_alpha, oos_avg_alpha, is_median_alpha, oos_median_alpha,
         is_sharpe, oos_sharpe,
         conservative_is_nav, conservative_oos_nav,
         growth_is_nav, growth_oos_nav,
         aggressive_is_nav, aggressive_oos_nav,
         conservative_oos_maxdd, growth_oos_maxdd, aggressive_oos_maxdd,
         exec_cost_per_trade, decision, params)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        datetime.now().isoformat(), "v1",
        is_metrics.get('total_pairs', 0), oos_metrics.get('total_pairs', 0),
        is_metrics.get('hit_rate', 0), oos_metrics.get('hit_rate', 0),
        oos_metrics.get('hit_rate_ci', (0, 0))[0], oos_metrics.get('hit_rate_ci', (0, 0))[1],
        is_metrics.get('avg_alpha', 0), oos_metrics.get('avg_alpha', 0),
        is_metrics.get('median_alpha', 0), oos_metrics.get('median_alpha', 0),
        is_metrics.get('sharpe_quarterly', 0), oos_metrics.get('sharpe_quarterly', 0),
        is_navs['Conservative']['final_nav'], oos_navs['Conservative']['final_nav'],
        is_navs['Growth']['final_nav'], oos_navs['Growth']['final_nav'],
        is_navs['Aggressive']['final_nav'], oos_navs['Aggressive']['final_nav'],
        oos_navs['Conservative']['max_dd'], oos_navs['Growth']['max_dd'], oos_navs['Aggressive']['max_dd'],
        EXEC_COST_PER_TRADE, decision,
        json.dumps({
            "weights": WEIGHTS, "hold_days": HOLD_DAYS,
            "bear_threshold": BEAR_THRESHOLD, "top_n": TOP_N,
            "max_tok": MAX_TOK, "max_cap": MAX_CAP,
            "exec_cost": EXEC_COST_PER_TRADE,
            "rating_class": "IG_MID", "major_count": len(MAJOR),
        })
    ))
    conn.commit()
    print(f"\n  Saved to DB: crypto_portable_alpha_reconciliation")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    print("=" * 90)
    print("  NERQ CRYPTO — PORTABLE ALPHA STRATEGY BACKTEST")
    print(f"  Replicates nav_tracker.py with IS/OOS separation + execution costs")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)
    print(f"  Rating class: IG_MID only (A1, A2, A3)")
    print(f"  Universe: {len(MAJOR)} MAJOR tokens, {len(STABLECOINS)} stablecoins excluded")
    print(f"  Conviction: top-{TOP_N}, max {MAX_TOK}/token, {SW:.0%} spread + {NW:.0%} NDD")
    print(f"  Bear skip: BTC monthly < {BEAR_THRESHOLD:.0%}")
    print(f"  Hold: {HOLD_DAYS}d, cap ±{MAX_CAP:.0%}, cost {EXEC_COST_PER_TRADE:.1%}/trade")
    print(f"  IS: {IN_SAMPLE_START} → {IN_SAMPLE_END}")
    print(f"  OOS: {OUT_SAMPLE_START} → {OUT_SAMPLE_END}")

    conn = get_db()

    # Quick DB stats
    for tbl in ["crypto_price_history", "crypto_rating_history", "crypto_ndd_history"]:
        row = conn.execute(f"SELECT COUNT(*) as c FROM {tbl}").fetchone()
        print(f"  {tbl}: {row['c']:,} rows")

    # Load data
    print("\n  Loading IS data...")
    is_prices, is_eligible, is_ratings, is_ndd, is_btc = load_data(conn, IN_SAMPLE_START, IN_SAMPLE_END)
    print(f"  IS eligible: {len(is_eligible)} tokens")

    print("  Loading OOS data...")
    oos_prices, oos_eligible, oos_ratings, oos_ndd, oos_btc = load_data(conn, OUT_SAMPLE_START, OUT_SAMPLE_END)
    print(f"  OOS eligible: {len(oos_eligible)} tokens")

    # Run strategy
    print("\n  Running IS strategy...")
    is_results = run_strategy(is_prices, is_eligible, is_ratings, is_ndd, is_btc,
                              IN_SAMPLE_START, IN_SAMPLE_END, "IS")
    is_metrics = compute_metrics(is_results)

    print("  Running OOS strategy...")
    oos_results = run_strategy(oos_prices, oos_eligible, oos_ratings, oos_ndd, oos_btc,
                               OUT_SAMPLE_START, OUT_SAMPLE_END, "OOS")
    oos_metrics = compute_metrics(oos_results)

    # Compute NAVs for all variants
    is_navs = {}
    oos_navs = {}
    for variant in VARIANTS:
        is_mn, is_final, is_dd, btc_ret_is = compute_nav(is_results, variant, is_btc,
                                                           IN_SAMPLE_START, IN_SAMPLE_END)
        oos_mn, oos_final, oos_dd, btc_ret_oos = compute_nav(oos_results, variant, oos_btc,
                                                               OUT_SAMPLE_START, OUT_SAMPLE_END)
        is_navs[variant] = {'monthly': is_mn, 'final_nav': is_final, 'max_dd': is_dd}
        oos_navs[variant] = {'monthly': oos_mn, 'final_nav': oos_final, 'max_dd': oos_dd}

    # Print & decide
    decision = print_results(is_metrics, oos_metrics, is_navs, oos_navs, btc_ret_is, btc_ret_oos)

    # Save
    save_results(conn, is_metrics, oos_metrics, is_navs, oos_navs, decision)

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
