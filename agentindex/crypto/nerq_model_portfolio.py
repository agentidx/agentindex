#!/usr/bin/env python3
"""
NERQ MODEL PORTFOLIO — "Does Your Portfolio Beat Bitcoin?"
============================================================
Combines regime detection with rating-based token selection.

Three regimes:
  ALT SEASON  -> 30% BTC + 70% in top rated/undervalued alts
  BTC SEASON  -> 100% BTC
  BEAR MARKET -> 100% cash (stablecoins)

Two variants:
  CONSERVATIVE: Rating >= A, NDD >= 2.0, top 10 tokens
  GROWTH:       Rating >= Baa, NDD >= 1.5, top 15 tokens

Token selection: Combined score = Rating(35%) + RCS(40%) + NDD(25%)
RCS = token's 90d return vs same-rating-class peers (undervalued quality)

Run:  python3 nerq_model_portfolio.py
"""
import sqlite3, os, sys, json, math
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

DB_NAME = "crypto_trust.db"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
IN_SAMPLE_START  = "2021-01-01"
IN_SAMPLE_END    = "2023-12-31"
OUT_SAMPLE_START = "2024-01-01"
OUT_SAMPLE_END   = "2025-12-31"
FULL_START       = "2021-01-01"
FULL_END         = "2025-12-31"

REBALANCE_COST = 0.0015
TOKEN_RETURN_CAP = 0.80  # cap per token per month
MAX_TOKEN_WEIGHT = 0.15  # max 15% per token

STABLECOINS = {
    "tether","usd-coin","binance-usd","dai","true-usd","paxos-standard",
    "gusd","frax","usdd","tusd","busd","lusd","susd","eurs","usdp",
    "first-digital-usd","ethena-usde","usde","paypal-usd","fdusd",
    "stasis-eur","gemini-dollar","husd","nusd","musd","cusd",
    "terrausd","ust","magic-internet-money","euro-coin","ondo-us-dollar-yield",
}
WRAPPED = {
    "wrapped-bitcoin","weth","wrapped-steth","wrapped-eeth",
    "coinbase-wrapped-staked-eth","rocket-pool-eth","staked-ether",
}
MAJOR_EXCHANGE_TOKENS = {
    "ethereum","ripple","solana","cardano",
    "dogecoin","tron","polkadot","avalanche-2","chainlink",
    "shiba-inu","stellar","cosmos","monero","hedera-hashgraph",
    "vechain","internet-computer","litecoin","near",
    "uniswap","pepe","kaspa","sui","sei-network",
    "celestia","arbitrum","optimism","immutable-x",
    "the-graph","render-token","fetch-ai","injective-protocol",
    "bittensor","helium","livepeer","aave","curve-dao-token",
    "maker","lido-dao","the-open-network",
    "axie-infinity","decentraland","the-sandbox","gala",
    "enjincoin","flow","decred","zilliqa","iota",
    "eos","neo","dash","zcash","algorand",
    "fantom","kava","celo","ankr",
    "worldcoin-wld","pyth-network","layerzero",
    "ondo-finance","ethena","jasmycoin",
    "blockstack","elrond-erd-2",
    "crypto-com-chain","filecoin",
    "aptos","mantle","bonk","dogwifcoin",
    "floki","theta-token","quant-network",
    "arweave","stacks","pendle",
    "bitcoin-cash","ethereum-classic",
    "jupiter-exchange-solana","raydium","pi-network",
}

RATING_SCORE = {
    "Aaa":10,"Aa1":9.5,"Aa2":9,"Aa3":8.5,
    "A1":8,"A2":7.5,"A3":7,"Baa1":6.5,"Baa2":6,"Baa3":5.5,
    "Ba1":5,"Ba2":4.5,"Ba3":4,"B1":3.5,"B2":3,"B3":2.5,
    "Caa1":2,"Caa2":1.5,"Caa3":1,"Ca":0.5,"C":0.3,"D":0.1,
}
RATING_CLASS = {}
for r in ["Aaa"]: RATING_CLASS[r] = "IG_TOP"
for r in ["Aa1","Aa2","Aa3"]: RATING_CLASS[r] = "IG_HIGH"
for r in ["A1","A2","A3"]: RATING_CLASS[r] = "IG_MID"
for r in ["Baa1","Baa2","Baa3"]: RATING_CLASS[r] = "IG_LOW"
for r in ["Ba1","Ba2","Ba3"]: RATING_CLASS[r] = "HY_HIGH"
for r in ["B1","B2","B3"]: RATING_CLASS[r] = "HY_LOW"
for r in ["Caa1","Caa2","Caa3","Ca","C","D"]: RATING_CLASS[r] = "DISTRESS"

# Conservative: >= A (i.e. Aaa, Aa, A)
CONSERVATIVE_MIN = 7.0   # A3 = 7.0
CONSERVATIVE_NDD = 2.0
CONSERVATIVE_N   = 10

# Growth: >= Baa
GROWTH_MIN = 5.5          # Baa3 = 5.5
GROWTH_NDD = 1.5
GROWTH_N   = 15

# Regime thresholds (to be optimized)
DEFAULT_THRESHOLDS = {
    "bear_dd": -0.25,         # BTC >25% from ATH = bear
    "alt_breadth": 0.55,      # >55% of alts beating BTC = alt season
    "btc_mom_floor": -0.10,   # BTC momentum must be > -10% for alt season
}

# ─── DATABASE ────────────────────────────────────────────────────────
def connect():
    if not os.path.exists(DB_PATH): print(f"ERROR: {DB_PATH}"); sys.exit(1)
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn

def load_all_prices(conn, start, end):
    rows = conn.execute("SELECT token_id,date,close,volume FROM crypto_price_history WHERE date>=? AND date<=? ORDER BY token_id,date",(start,end)).fetchall()
    prices = defaultdict(dict); volumes = defaultdict(dict)
    for r in rows: prices[r["token_id"]][r["date"]]=r["close"]; volumes[r["token_id"]][r["date"]]=r["volume"]
    return dict(prices), dict(volumes)

def load_ratings(conn, start, end):
    rows = conn.execute("SELECT token_id,year_month,rating,score,pillar_1,pillar_2,pillar_3,pillar_4,pillar_5 FROM crypto_rating_history WHERE year_month>=? AND year_month<=?",(start[:7],end[:7])).fetchall()
    d = {}
    for r in rows:
        d[(r["token_id"],r["year_month"])] = {
            "rating": r["rating"], "score": r["score"],
            "pillars": [r["pillar_1"],r["pillar_2"],r["pillar_3"],r["pillar_4"],r["pillar_5"]]
        }
    return d

def load_ndd(conn, start, end):
    rows = conn.execute("SELECT token_id,substr(week_date,1,7) as ym,AVG(ndd) as n FROM crypto_ndd_history WHERE week_date>=? AND week_date<=? GROUP BY token_id,substr(week_date,1,7)",(start,end)).fetchall()
    return {(r["token_id"],r["ym"]):r["n"] for r in rows}

def get_eligible(prices, volumes, start, end):
    eligible = []
    for tid in MAJOR_EXCHANGE_TOKENS:
        if tid not in prices or tid in STABLECOINS or tid in WRAPPED: continue
        if tid == "bitcoin": continue  # BTC handled separately
        dates_in_range = [d for d in prices[tid] if start <= d <= end]
        if len(dates_in_range) < 60: continue
        vol_vals = [volumes.get(tid,{}).get(d,0) for d in dates_in_range]
        if np.mean(vol_vals) < 10000: continue
        eligible.append(tid)
    return eligible

def compute_return(pd, lb, rd, ds):
    idx = None
    for i,d in enumerate(ds):
        if d<=rd: idx=i
        else: break
    if idx is None: return None
    si = max(0, idx-lb)
    pe=pd.get(ds[idx]); ps=pd.get(ds[si])
    if pe and ps and ps>0: return (pe/ps)-1
    return None


# ─── REGIME DETECTION ────────────────────────────────────────────────

def detect_regime(bp, abp, rd, bd, thresh):
    """
    ALT_SEASON: >X% of alts beat BTC 30d AND BTC not in deep DD AND BTC momentum ok
    BEAR:       BTC >Y% drawdown from 365d ATH
    BTC_SEASON: everything else
    """
    # BTC drawdown from 365d ATH
    idx = None
    for i,d in enumerate(bd):
        if d<=rd: idx=i
        else: break
    if idx is None: return "BTC_SEASON", {}

    si = max(0, idx-365)
    pw = [bp.get(bd[i]) for i in range(si,idx+1) if bp.get(bd[i])]
    if not pw: return "BTC_SEASON", {}
    btc_dd = (bp.get(bd[idx], max(pw))/max(pw)) - 1

    if btc_dd < thresh["bear_dd"]:
        return "BEAR", {"dd": btc_dd}

    # Alt breadth
    btc_30 = compute_return(bp, 30, rd, bd)
    btc_90 = compute_return(bp, 90, rd, bd)
    if btc_30 is None: return "BTC_SEASON", {"dd": btc_dd}

    op = 0; tot = 0
    for tid, ap in abp.items():
        ad = sorted(ap.keys())
        r = compute_return(ap, 30, rd, ad)
        if r is not None:
            tot += 1
            if r > btc_30: op += 1
    breadth = op / tot if tot > 5 else 0.5

    btc_mom = btc_30 * 0.5 + (btc_90 or 0) * 0.5

    if breadth > thresh["alt_breadth"] and btc_mom > thresh["btc_mom_floor"]:
        return "ALT_SEASON", {"dd": btc_dd, "breadth": breadth, "mom": btc_mom}

    return "BTC_SEASON", {"dd": btc_dd, "breadth": breadth, "mom": btc_mom}


# ─── RCS: RISK COMPENSATION SCORE ───────────────────────────────────

def compute_rcs(token_id, ym, prices, ratings, all_eligible, bd):
    """
    RCS = token's 90d return minus median 90d return of same rating class.
    Positive RCS = outperforming peers = undervalued quality.
    """
    # Get this token's rating class
    rdata = ratings.get((token_id, ym))
    if not rdata: return 0.0
    my_class = RATING_CLASS.get(rdata["rating"], "UNKNOWN")
    my_score = RATING_SCORE.get(rdata["rating"], 5.0)

    # Find reference date (first of month)
    ref_date = f"{ym}-01"

    # This token's 90d return
    tp = prices.get(token_id, {})
    td = sorted(tp.keys())
    my_ret = compute_return(tp, 90, ref_date, td)
    if my_ret is None: return 0.0

    # Peer returns (same rating class)
    peer_rets = []
    for tid in all_eligible:
        if tid == token_id: continue
        pr = ratings.get((tid, ym))
        if not pr: continue
        peer_class = RATING_CLASS.get(pr["rating"], "UNKNOWN")
        if peer_class != my_class: continue
        pp = prices.get(tid, {})
        pd = sorted(pp.keys())
        r = compute_return(pp, 90, ref_date, pd)
        if r is not None: peer_rets.append(r)

    if len(peer_rets) < 2:
        # Not enough peers in same class — use adjacent classes
        for tid in all_eligible:
            if tid == token_id: continue
            pr = ratings.get((tid, ym))
            if not pr: continue
            peer_score = RATING_SCORE.get(pr["rating"], 5.0)
            if abs(peer_score - my_score) <= 2.0:  # Within 2 rating notches
                pp = prices.get(tid, {})
                pd = sorted(pp.keys())
                r = compute_return(pp, 90, ref_date, pd)
                if r is not None: peer_rets.append(r)

    if not peer_rets: return 0.0

    # RCS = my return - median peer return (normalized to -10..+10 scale)
    rcs = (my_ret - np.median(peer_rets))
    # Scale: ±50% difference maps to ±10
    rcs_scaled = max(-10, min(10, rcs * 20))
    return rcs_scaled


# ─── TOKEN SELECTION & WEIGHTING ─────────────────────────────────────

def select_tokens(prices, ratings, ndd_data, eligible, ym, bd,
                   min_rating_score, min_ndd, top_n, w_rating=0.35, w_rcs=0.40, w_ndd=0.25):
    """
    Select and weight tokens for the portfolio.
    Combined score = Rating(35%) + RCS(40%) + NDD(25%)
    """
    candidates = []

    for tid in eligible:
        rdata = ratings.get((tid, ym))
        if not rdata: continue

        rscore = RATING_SCORE.get(rdata["rating"], 0)
        if rscore < min_rating_score: continue

        ndd_val = ndd_data.get((tid, ym))
        if ndd_val is None or ndd_val < min_ndd: continue

        rcs = compute_rcs(tid, ym, prices, ratings, eligible, bd)

        # Normalize to 0-10
        rating_norm = rscore  # Already 0-10
        rcs_norm = (rcs + 10) / 2.0  # -10..+10 → 0..10
        ndd_norm = ndd_val * 2.0      # 0-5 → 0-10

        combined = w_rating * rating_norm + w_rcs * rcs_norm + w_ndd * ndd_norm

        candidates.append({
            "token": tid, "rating": rdata["rating"], "rating_score": rscore,
            "rcs": round(rcs, 2), "ndd": round(ndd_val, 2),
            "combined": round(combined, 3),
        })

    # Sort by combined score descending
    candidates.sort(key=lambda x: x["combined"], reverse=True)
    selected = candidates[:top_n]

    if not selected: return []

    # Weight by combined score with max cap
    total_score = sum(s["combined"] for s in selected)
    for s in selected:
        raw_weight = s["combined"] / total_score if total_score > 0 else 1.0 / len(selected)
        s["weight"] = min(MAX_TOKEN_WEIGHT, max(0.02, raw_weight))

    # Renormalize weights to sum to 1.0
    total_w = sum(s["weight"] for s in selected)
    for s in selected:
        s["weight"] = round(s["weight"] / total_w, 4)

    return selected


# ─── PORTFOLIO RETURN ────────────────────────────────────────────────

def compute_portfolio_return(selected_tokens, prices, entry_date, exit_date):
    """Weighted return of selected tokens."""
    if not selected_tokens: return 0.0

    total_ret = 0.0
    total_weight = 0.0
    for t in selected_tokens:
        tp = prices.get(t["token"], {})
        pe = tp.get(entry_date)
        px = tp.get(exit_date)
        if pe and px and pe > 0:
            ret = (px / pe) - 1
            ret = max(-TOKEN_RETURN_CAP, min(TOKEN_RETURN_CAP, ret))
            total_ret += t["weight"] * ret
            total_weight += t["weight"]

    if total_weight > 0 and total_weight < 0.99:
        # Some tokens didn't have data — redistribute
        total_ret = total_ret / total_weight

    return total_ret


# ─── BACKTEST ENGINE ─────────────────────────────────────────────────

def run_model_portfolio(bp, prices, bd, ratings, ndd_data, eligible, abp,
                         thresh, min_rating, min_ndd, top_n, variant_name):
    records = []
    cur = datetime.strptime(FULL_START, "%Y-%m-%d")
    end_dt = datetime.strptime(FULL_END, "%Y-%m-%d")
    nav = 1.0; bnav = 1.0

    while cur <= end_dt:
        ym = cur.strftime("%Y-%m")
        rd = cur.strftime("%Y-%m-%d")
        nm = cur.replace(year=cur.year+1,month=1,day=1) if cur.month==12 else cur.replace(month=cur.month+1,day=1)
        ed = (nm - timedelta(days=1)).strftime("%Y-%m-%d")

        ea = ex = None
        for d in bd:
            if d >= rd and ea is None: ea = d
            if d >= ed and ex is None: ex = d
            if d > ed: break
        if not ex: ex = bd[-1]
        if ea is None or ea >= ex: cur = nm; continue

        # Detect regime
        regime, sigs = detect_regime(bp, abp, ea, bd, thresh)

        # Select tokens (only needed for ALT_SEASON)
        selected = []
        if regime == "ALT_SEASON":
            selected = select_tokens(prices, ratings, ndd_data, eligible, ym, bd,
                                      min_rating, min_ndd, top_n)

        # Compute returns
        bp1 = bp.get(ea, 0); bp2 = bp.get(ex, 0)
        btc_ret = (bp2/bp1 - 1) if bp1 > 0 else 0

        if regime == "ALT_SEASON" and selected:
            alt_ret = compute_portfolio_return(selected, prices, ea, ex)
            port_ret = 0.30 * btc_ret + 0.70 * alt_ret
            alloc_str = f"BTC 30% + {len(selected)} alts 70%"
        elif regime == "BTC_SEASON":
            alt_ret = 0.0
            port_ret = btc_ret
            alloc_str = "BTC 100%"
        else:  # BEAR
            alt_ret = 0.0
            port_ret = 0.0
            alloc_str = "CASH 100%"

        # Transaction costs
        port_ret -= 0.20 * REBALANCE_COST

        nav *= (1 + port_ret)
        bnav *= (1 + btc_ret)

        # Top 3 holdings for display
        top3 = ", ".join(f"{t['token'][:8]}({t['weight']*100:.0f}%)" for t in selected[:3]) if selected else "-"

        records.append({
            "month": ym, "regime": regime,
            "alloc": alloc_str, "top_holdings": top3,
            "n_tokens": len(selected),
            "btc_ret": round(btc_ret, 4),
            "alt_ret": round(alt_ret, 4),
            "port_ret": round(port_ret, 4),
            "nav": round(nav, 4),
            "btc_nav": round(bnav, 4),
            "alpha_m": round((port_ret - btc_ret) * 100, 2),
            "sigs": {k: round(v, 3) for k, v in sigs.items()} if sigs else {},
        })
        cur = nm

    return records


# ─── METRICS ─────────────────────────────────────────────────────────

def compute_metrics(records, label=""):
    if not records: return {}
    navs = [r["nav"] for r in records]
    bnavs = [r["btc_nav"] for r in records]
    pr = [r["port_ret"] for r in records]
    br = [r["btc_ret"] for r in records]
    yrs = len(records) / 12

    pt = navs[-1] - 1; bt = bnavs[-1] - 1
    ap = (navs[-1])**(1/yrs) - 1 if yrs > 0 else 0
    ab = (bnavs[-1])**(1/yrs) - 1 if yrs > 0 else 0
    pv = np.std(pr) * math.sqrt(12); bv = np.std(br) * math.sqrt(12)
    rf = 0.045
    ps = (ap-rf)/pv if pv > 0 else 0; bs = (ab-rf)/bv if bv > 0 else 0

    def mdd(ns):
        pk=ns[0]; m=0
        for n in ns:
            if n>pk: pk=n
            dd=(n/pk)-1
            if dd<m: m=dd
        return m

    pm = mdd(navs); bm = mdd(bnavs)
    pc = ap/abs(pm) if pm != 0 else 0; bc = ab/abs(bm) if bm != 0 else 0
    wins = sum(1 for p, b in zip(pr, br) if p >= b)

    regimes = defaultdict(int)
    for r in records: regimes[r["regime"]] += 1

    return {
        "label": label, "months": len(records), "years": round(yrs, 1),
        "port_total": round(pt*100, 1), "btc_total": round(bt*100, 1),
        "alpha": round((pt-bt)*100, 1),
        "ann_port": round(ap*100, 1), "ann_btc": round(ab*100, 1),
        "vol_port": round(pv*100, 1), "vol_btc": round(bv*100, 1),
        "sharpe_port": round(ps, 2), "sharpe_btc": round(bs, 2),
        "dd_port": round(pm*100, 1), "dd_btc": round(bm*100, 1),
        "calmar_port": round(pc, 2), "calmar_btc": round(bc, 2),
        "win_rate": round(wins/len(records)*100, 1),
        "profit_months": sum(1 for r in records if r["port_ret"] > 0),
        "regimes": dict(regimes),
    }


def print_results(records, metrics):
    m = metrics
    print(f"\n{'='*78}")
    print(f"  {m['label']}")
    print(f"{'='*78}")
    print(f"  Period:       {records[0]['month']} -> {records[-1]['month']} ({m['months']} months)")
    print(f"  Portfolio:    {m['port_total']:+.1f}% ({m['ann_port']:+.1f}% ann.)")
    print(f"  BTC:          {m['btc_total']:+.1f}% ({m['ann_btc']:+.1f}% ann.)")
    print(f"  Alpha:        {m['alpha']:+.1f}%")
    print(f"  Vol:          {m['vol_port']:.1f}% port | {m['vol_btc']:.1f}% BTC")
    print(f"  Sharpe:       {m['sharpe_port']:.2f} port | {m['sharpe_btc']:.2f} BTC")
    print(f"  Max DD:       {m['dd_port']:.1f}% port | {m['dd_btc']:.1f}% BTC")
    print(f"  Calmar:       {m['calmar_port']:.2f} port | {m['calmar_btc']:.2f} BTC")
    print(f"  Win rate:     {m['win_rate']:.1f}% ({int(m['win_rate']*m['months']/100)}/{m['months']})")
    print(f"  Regimes:      {m['regimes']}")

    print(f"\n  {'Month':7s} {'Regime':11s} {'Allocation':28s} {'Port':>7s} {'BTC':>7s} {'Alpha':>6s} {'NAV':>8s} {'BTC_N':>8s} {'Top Holdings'}")
    print(f"  {'-'*110}")
    for r in records:
        print(f"  {r['month']:7s} {r['regime']:11s} {r['alloc']:28s}"
              f" {r['port_ret']*100:+6.1f}% {r['btc_ret']*100:+6.1f}% {r['alpha_m']:+5.1f}%"
              f" {r['nav']:7.4f} {r['btc_nav']:7.4f}  {r['top_holdings']}")


# ─── OPTIMIZATION ────────────────────────────────────────────────────

def optimize_thresholds(bp, prices, bd, ratings, ndd_data, eligible, abp,
                         min_rating, min_ndd, top_n, start, end, variant):
    """Grid search over regime thresholds."""
    print(f"\n  Optimizing {variant}...")
    best_score = -999
    best_thresh = DEFAULT_THRESHOLDS.copy()

    dd_range = [-0.15, -0.20, -0.25, -0.30, -0.35]
    breadth_range = [0.45, 0.50, 0.55, 0.60, 0.65]
    mom_range = [-0.15, -0.10, -0.05, 0.0, 0.05]

    total = len(dd_range) * len(breadth_range) * len(mom_range)
    print(f"  Testing {total} threshold combos...")
    tested = 0

    for dd in dd_range:
        for br in breadth_range:
            for mom in mom_range:
                thresh = {"bear_dd": dd, "alt_breadth": br, "btc_mom_floor": mom}
                recs = run_model_portfolio(bp, prices, bd, ratings, ndd_data, eligible, abp,
                                           thresh, min_rating, min_ndd, top_n, variant)
                # Only evaluate on in-sample period
                is_recs = [r for r in recs if r["month"] >= start[:7] and r["month"] <= end[:7]]
                if not is_recs: continue

                navs = [r["nav"] for r in is_recs]
                bnavs = [r["btc_nav"] for r in is_recs]
                pr = [r["port_ret"] for r in is_recs]
                br_list = [r["btc_ret"] for r in is_recs]
                yrs = len(is_recs) / 12
                if yrs < 0.5: continue

                ann = (navs[-1] / (is_recs[0]["nav"] / (1+is_recs[0]["port_ret"])))**(1/yrs) - 1

                # Recalculate NAV relative to start of IS period
                is_nav = 1.0
                is_navs = []
                for r in is_recs:
                    is_nav *= (1 + r["port_ret"])
                    is_navs.append(is_nav)

                pk = 1.0; mdd = 0
                for n in is_navs:
                    if n > pk: pk = n
                    d = (n/pk) - 1
                    if d < mdd: mdd = d
                if mdd == 0: mdd = -0.001

                cal = ann / abs(mdd)

                # Alpha check
                is_bnav = 1.0
                for r in is_recs: is_bnav *= (1 + r["btc_ret"])
                alpha = (is_nav - 1) - (is_bnav - 1)
                if alpha < 0: cal *= 0.3

                wr = sum(1 for p, b in zip(pr, br_list) if p >= b) / len(is_recs)
                if wr > 0.45: cal *= (1 + (wr - 0.45))

                tested += 1
                if cal > best_score:
                    best_score = cal
                    best_thresh = thresh.copy()

    print(f"  Best: score={best_score:.3f}")
    print(f"  Thresholds: bear_dd={best_thresh['bear_dd']}, breadth={best_thresh['alt_breadth']}, mom={best_thresh['btc_mom_floor']}")
    return best_thresh


# ─── SAVE TO DB ──────────────────────────────────────────────────────

def save_results(conn, records, metrics, thresh, variant):
    conn.execute("""CREATE TABLE IF NOT EXISTS nerq_model_portfolio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT, variant TEXT, month TEXT, regime TEXT,
        alloc TEXT, n_tokens INTEGER, top_holdings TEXT,
        btc_ret REAL, alt_ret REAL, port_ret REAL,
        nav REAL, btc_nav REAL, signals TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS nerq_model_portfolio_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT, variant TEXT, thresholds TEXT,
        months INTEGER, port_total REAL, btc_total REAL, alpha REAL,
        sharpe_port REAL, sharpe_btc REAL,
        dd_port REAL, dd_btc REAL,
        calmar_port REAL, calmar_btc REAL, win_rate REAL)""")

    rd = datetime.now().strftime("%Y-%m-%d %H:%M")
    for r in records:
        conn.execute("INSERT INTO nerq_model_portfolio (run_date,variant,month,regime,alloc,n_tokens,top_holdings,btc_ret,alt_ret,port_ret,nav,btc_nav,signals) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rd, variant, r["month"], r["regime"], r["alloc"], r["n_tokens"], r["top_holdings"],
             r["btc_ret"], r["alt_ret"], r["port_ret"], r["nav"], r["btc_nav"], json.dumps(r["sigs"])))
    m = metrics
    conn.execute("INSERT INTO nerq_model_portfolio_summary (run_date,variant,thresholds,months,port_total,btc_total,alpha,sharpe_port,sharpe_btc,dd_port,dd_btc,calmar_port,calmar_btc,win_rate) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rd, variant, json.dumps(thresh), m["months"], m["port_total"], m["btc_total"], m["alpha"],
         m["sharpe_port"], m["sharpe_btc"], m["dd_port"], m["dd_btc"],
         m["calmar_port"], m["calmar_btc"], m["win_rate"]))
    conn.commit()


# ─── MAIN ────────────────────────────────────────────────────────────

def main():
    print("=" * 78)
    print("  NERQ MODEL PORTFOLIO")
    print("  'Does Your Portfolio Beat Bitcoin?' — Answered with data.")
    print("=" * 78)
    print(f"  DB: {DB_PATH}")

    conn = connect()
    print("\n  Loading data...")
    prices, volumes = load_all_prices(conn, "2020-10-01", FULL_END)
    bp = prices.get("bitcoin", {}); bd = sorted(bp.keys())
    ratings = load_ratings(conn, FULL_START, FULL_END)
    ndd_data = load_ndd(conn, FULL_START, FULL_END)
    eligible = get_eligible(prices, volumes, FULL_START, FULL_END)
    abp = {tid: prices[tid] for tid in eligible}

    print(f"    BTC: {len(bp)} days")
    print(f"    Ratings: {len(ratings)} token-months")
    print(f"    NDD: {len(ndd_data)} token-months")
    print(f"    Eligible alts: {len(eligible)}")

    for variant, min_rat, min_ndd, top_n in [
        ("CONSERVATIVE", CONSERVATIVE_MIN, CONSERVATIVE_NDD, CONSERVATIVE_N),
        ("GROWTH", GROWTH_MIN, GROWTH_NDD, GROWTH_N),
    ]:
        print(f"\n{'#'*78}")
        print(f"  {variant} PORTFOLIO")
        print(f"  Min rating: {min_rat} | Min NDD: {min_ndd} | Top N: {top_n}")
        print(f"{'#'*78}")

        # Optimize thresholds in-sample
        best_thresh = optimize_thresholds(
            bp, prices, bd, ratings, ndd_data, eligible, abp,
            min_rat, min_ndd, top_n, IN_SAMPLE_START, IN_SAMPLE_END, variant
        )

        # Run full period with frozen thresholds
        full_recs = run_model_portfolio(
            bp, prices, bd, ratings, ndd_data, eligible, abp,
            best_thresh, min_rat, min_ndd, top_n, variant
        )

        # Split into IS and OOS
        is_recs = [r for r in full_recs if r["month"] <= "2023-12"]
        oos_recs = [r for r in full_recs if r["month"] >= "2024-01"]

        # Need to recalculate NAV for IS and OOS separately
        # IS: use as-is (starts from 1.0)
        is_nav = 1.0; is_bnav = 1.0
        for r in is_recs:
            is_nav *= (1 + r["port_ret"]); is_bnav *= (1 + r["btc_ret"])
            r["nav"] = round(is_nav, 4); r["btc_nav"] = round(is_bnav, 4)

        oos_nav = 1.0; oos_bnav = 1.0
        for r in oos_recs:
            oos_nav *= (1 + r["port_ret"]); oos_bnav *= (1 + r["btc_ret"])
            r["nav"] = round(oos_nav, 4); r["btc_nav"] = round(oos_bnav, 4)

        is_m = compute_metrics(is_recs, f"{variant} IN-SAMPLE (2021-2023)")
        oos_m = compute_metrics(oos_recs, f"{variant} OUT-OF-SAMPLE (2024-2025) — FROZEN")

        print_results(is_recs, is_m)
        print_results(oos_recs, oos_m)

        # Full period (keep original NAVs)
        full_m = compute_metrics(full_recs, f"{variant} FULL (2021-2025)")
        print_results(full_recs, full_m)

        # Save
        save_results(conn, full_recs, full_m, best_thresh, variant)

        # Validation
        print(f"\n  VALIDATION ({variant} OOS):")
        checks = [
            ("Alpha > 0%", oos_m["alpha"] > 0, f"{oos_m['alpha']:+.1f}%"),
            ("Sharpe > BTC", oos_m["sharpe_port"] > oos_m["sharpe_btc"],
             f"{oos_m['sharpe_port']:.2f} vs {oos_m['sharpe_btc']:.2f}"),
            ("Max DD < BTC", oos_m["dd_port"] > oos_m["dd_btc"],
             f"{oos_m['dd_port']:.1f}% vs {oos_m['dd_btc']:.1f}%"),
            ("Win rate > 50%", oos_m["win_rate"] > 50, f"{oos_m['win_rate']:.1f}%"),
            ("Calmar > BTC", oos_m["calmar_port"] > oos_m["calmar_btc"],
             f"{oos_m['calmar_port']:.2f} vs {oos_m['calmar_btc']:.2f}"),
        ]
        passed = 0
        for name, ok, detail in checks:
            st = "v PASS" if ok else "x FAIL"
            print(f"    {st}  {name:25s}  {detail}")
            if ok: passed += 1
        print(f"    Result: {passed}/5")

    conn.close()
    print(f"\n  Done.")

if __name__ == "__main__":
    main()
