#!/usr/bin/env python3
"""
NERQ CRYPTO — Task 1.5 v2: Adaptive BTC Allocation via Regime Detection
=========================================================================
v2: exchange filter, rating-weighted basket, return cap ±80%, BTC min 35%
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
BTC_MIN = 0.35
BTC_MAX = 0.90
EMERGENCY_DD_THRESHOLD = -0.30
EMERGENCY_BTC_ALLOC = 0.50
EMERGENCY_STABLE_ALLOC = 0.50
REBALANCE_COST = 0.0015
TOKEN_RETURN_CAP = 0.80

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
DEFAULT_WEIGHTS = [0.25, 0.20, 0.20, 0.20, 0.15]

def connect():
    if not os.path.exists(DB_PATH): print(f"ERROR: {DB_PATH}"); sys.exit(1)
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn

def load_all_prices(conn, start, end):
    rows = conn.execute("SELECT token_id,date,close,volume FROM crypto_price_history WHERE date>=? AND date<=? ORDER BY token_id,date",(start,end)).fetchall()
    prices = defaultdict(dict); volumes = defaultdict(dict)
    for r in rows: prices[r["token_id"]][r["date"]]=r["close"]; volumes[r["token_id"]][r["date"]]=r["volume"]
    return dict(prices), dict(volumes)

def load_ratings(conn, start, end):
    rows = conn.execute("SELECT token_id,year_month,rating FROM crypto_rating_history WHERE year_month>=? AND year_month<=?",(start[:7],end[:7])).fetchall()
    return {(r["token_id"],r["year_month"]):r["rating"] for r in rows}

def get_eligible_alts(prices, volumes, start, end):
    eligible = []
    for tid in MAJOR_EXCHANGE_TOKENS:
        if tid not in prices or tid in STABLECOINS or tid in WRAPPED: continue
        pdata = prices[tid]
        dates_in_range = [d for d in pdata if start <= d <= end]
        if len(dates_in_range) < 60: continue
        vol_vals = [volumes.get(tid,{}).get(d,0) for d in dates_in_range]
        if np.mean(vol_vals) < 10000: continue
        eligible.append(tid)
    return eligible

def compute_return(prices_dict, lookback_days, ref_date, dates_sorted):
    idx = None
    for i, d in enumerate(dates_sorted):
        if d <= ref_date: idx = i
        else: break
    if idx is None: return None
    si = max(0, idx - lookback_days)
    pe = prices_dict.get(dates_sorted[idx]); ps = prices_dict.get(dates_sorted[si])
    if pe and ps and ps > 0: return (pe/ps)-1
    return None

def signal_btc_dominance_trend(bp, abp, rd, bd):
    br = compute_return(bp,60,rd,bd)
    if br is None: return 0.5
    ar = [compute_return(ap,60,rd,sorted(ap.keys())) for ap in abp.values()]
    ar = [r for r in ar if r is not None]
    if len(ar)<5: return 0.5
    return max(0.0,min(1.0, 0.5+(br-np.median(ar))/0.6))

def signal_alt_breadth(bp, abp, rd, bd):
    br = compute_return(bp,30,rd,bd)
    if br is None: return 0.5
    op=0;tot=0
    for ap in abp.values():
        r = compute_return(ap,30,rd,sorted(ap.keys()))
        if r is not None: tot+=1; op+=(1 if r>br else 0)
    if tot<5: return 0.5
    return max(0.0,min(1.0, 1.0-op/tot))

def signal_btc_momentum(bp, rd, bd):
    r30 = compute_return(bp,30,rd,bd); r90 = compute_return(bp,90,rd,bd)
    if r30 is None or r90 is None: return 0.5
    return max(0.0,min(1.0, 0.5+-(r30*0.6+r90*0.4)/0.8))

def signal_alt_dispersion(abp, rd):
    rets = [compute_return(ap,30,rd,sorted(ap.keys())) for ap in abp.values()]
    rets = [r for r in rets if r is not None]
    if len(rets)<5: return 0.5
    return max(0.0,min(1.0, np.std(np.clip(rets,-1,3))/0.5))

def signal_drawdown_regime(bp, rd, bd):
    idx = None
    for i,d in enumerate(bd):
        if d<=rd: idx=i
        else: break
    if idx is None: return 0.5
    si = max(0,idx-365)
    pw = [bp.get(bd[i]) for i in range(si,idx+1) if bp.get(bd[i])]
    if not pw: return 0.5
    dd = (bp.get(bd[idx],max(pw))/max(pw))-1
    return max(0.0,min(1.0, -dd/0.7))

def compute_regime_score(bp, abp, rd, bd, w):
    sigs = [signal_btc_dominance_trend(bp,abp,rd,bd), signal_alt_breadth(bp,abp,rd,bd),
            signal_btc_momentum(bp,rd,bd), signal_alt_dispersion(abp,rd),
            signal_drawdown_regime(bp,rd,bd)]
    return sum(s*ww for s,ww in zip(sigs,w)), sigs

def compute_btc_dd_at_date(bp, rd, bd):
    idx = None
    for i,d in enumerate(bd):
        if d<=rd: idx=i
        else: break
    if idx is None: return None
    si = max(0,idx-365)
    pw = [bp.get(bd[i],0) for i in range(si,idx+1)]; pw=[p for p in pw if p>0]
    if not pw: return None
    return (bp.get(bd[idx],max(pw))/max(pw))-1

def regime_to_btc_alloc(composite, btc_dd):
    if btc_dd is not None and btc_dd < EMERGENCY_DD_THRESHOLD:
        return EMERGENCY_BTC_ALLOC, 0.0, EMERGENCY_STABLE_ALLOC, True
    ba = BTC_MIN + composite*(BTC_MAX-BTC_MIN)
    return ba, 1.0-ba, 0.0, False

def compute_alt_basket_return_weighted(abp, ratings, entry, exit_d, ym):
    trets = []
    for tid, ap in abp.items():
        pe = ap.get(entry); px = ap.get(exit_d)
        if pe and px and pe>0:
            ret = max(-TOKEN_RETURN_CAP, min(TOKEN_RETURN_CAP, (px/pe)-1))
            rating = ratings.get((tid,ym),"B2")
            trets.append((ret, RATING_SCORE.get(rating,3.0)))
    if not trets: return 0.0
    tw = sum(w for _,w in trets)
    return sum(r*w for r,w in trets)/tw if tw>0 else 0.0

def run_adaptive_backtest(bp, abp, bd, weights, ratings, start, end):
    records=[]; cur=datetime.strptime(start,"%Y-%m-%d"); end_dt=datetime.strptime(end,"%Y-%m-%d")
    nav=1.0; bnav=1.0
    while cur<=end_dt:
        ym=cur.strftime("%Y-%m"); rd=cur.strftime("%Y-%m-%d")
        nm = cur.replace(year=cur.year+1,month=1,day=1) if cur.month==12 else cur.replace(month=cur.month+1,day=1)
        ed = (nm-timedelta(days=1)).strftime("%Y-%m-%d")
        ea=ex=None
        for d in bd:
            if d>=rd and ea is None: ea=d
            if d>=ed and ex is None: ex=d
            if d>ed: break
        if not ex: ex=bd[-1] if bd else ed
        if ea is None or ea>=ex: cur=nm; continue
        comp,sigs = compute_regime_score(bp,abp,ea,bd,weights)
        bdd = compute_btc_dd_at_date(bp,ea,bd)
        ba,aa,sa,emer = regime_to_btc_alloc(comp,bdd)
        bp1=bp.get(ea,0); bp2=bp.get(ex,0)
        bret = (bp2/bp1-1) if bp1>0 else 0
        aret = compute_alt_basket_return_weighted(abp,ratings,ea,ex,ym)
        pret = ba*bret + aa*aret + sa*0.0 - 0.25*REBALANCE_COST
        nav*=(1+pret); bnav*=(1+bret)
        rl = "EMERGENCY" if emer else ("RISK-OFF" if comp>0.65 else "NEUTRAL" if comp>0.35 else "RISK-ON")
        records.append({"month":ym,"entry":ea,"exit":ex,"composite":round(comp,3),
            "signals":[round(s,3) for s in sigs],"regime":rl,
            "btc_alloc":round(ba,3),"alt_alloc":round(aa,3),"stable_alloc":round(sa,3),
            "is_emergency":emer,"btc_ret":round(bret,4),"alt_ret":round(aret,4),
            "port_ret":round(pret,4),"nav":round(nav,4),"btc_nav":round(bnav,4),
            "alpha_cum":round((nav/bnav-1)*100,2),"btc_dd_from_ath":round(bdd*100,1) if bdd else None})
        cur=nm
    return records

def evaluate_weights(bp, abp, bd, w, ratings, start, end):
    recs = run_adaptive_backtest(bp,abp,bd,w,ratings,start,end)
    if not recs: return -999
    navs=[r["nav"] for r in recs]; bnavs=[r["btc_nav"] for r in recs]
    pr=[r["port_ret"] for r in recs]; br=[r["btc_ret"] for r in recs]
    yrs=len(recs)/12
    if yrs<0.5: return -999
    ann=(navs[-1])**(1/yrs)-1
    pk=navs[0];mdd=0
    for n in navs:
        if n>pk: pk=n
        dd=(n/pk)-1
        if dd<mdd: mdd=dd
    if mdd==0: mdd=-0.001
    cal = ann/abs(mdd)
    alpha = (navs[-1]-1)-(bnavs[-1]-1)
    if alpha<0: cal*=0.3
    wr = sum(1 for p,b in zip(pr,br) if p>b)/len(recs)
    vol = np.std(pr)*math.sqrt(12)
    if wr>0.50: cal*=(1+(wr-0.50))
    if vol<0.80: cal*=1.1
    return cal

def grid_search_weights(bp, abp, bd, ratings, start, end):
    print("\n  Grid search (v2: finer grid, win-rate bonus)...")
    best_s=-999; best_w=DEFAULT_WEIGHTS[:]
    steps=[round(i*0.05,2) for i in range(1,9)]
    combos=[]
    for w1 in steps:
        for w2 in steps:
            for w3 in steps:
                for w4 in steps:
                    w5=round(1.0-w1-w2-w3-w4,2)
                    if 0.05<=w5<=0.45: combos.append([w1,w2,w3,w4,w5])
    print(f"  Testing {len(combos)} combinations...")
    for i,w in enumerate(combos):
        s = evaluate_weights(bp,abp,bd,w,ratings,start,end)
        if s>best_s: best_s=s; best_w=w[:]
        if (i+1)%200==0: print(f"    [{i+1}/{len(combos)}] Best: {best_s:.3f} w={[f'{x:.2f}' for x in best_w]}")
    print(f"\n  Best: score={best_s:.3f} w={[f'{x:.2f}' for x in best_w]}")
    return best_w, best_s

def compute_metrics(records):
    if not records: return {}
    navs=[r["nav"] for r in records]; bnavs=[r["btc_nav"] for r in records]
    pr=[r["port_ret"] for r in records]; br=[r["btc_ret"] for r in records]
    yrs=len(records)/12
    pt=navs[-1]-1; bt=bnavs[-1]-1
    ap=(navs[-1])**(1/yrs)-1 if yrs>0 else 0; ab=(bnavs[-1])**(1/yrs)-1 if yrs>0 else 0
    pv=np.std(pr)*math.sqrt(12); bv=np.std(br)*math.sqrt(12)
    rf=0.045
    ps=(ap-rf)/pv if pv>0 else 0; bs=(ab-rf)/bv if bv>0 else 0
    def mdd(ns):
        pk=ns[0];m=0
        for n in ns:
            if n>pk:pk=n
            d=(n/pk)-1
            if d<m:m=d
        return m
    pm=mdd(navs);bm=mdd(bnavs)
    pc=ap/abs(pm) if pm!=0 else 0; bc=ab/abs(bm) if bm!=0 else 0
    wins=sum(1 for r in records if r["port_ret"]>r["btc_ret"])
    wr=wins/len(records)*100
    regimes=defaultdict(list)
    for r in records: regimes[r["regime"]].append(r)
    rs={}
    for reg,rcs in regimes.items():
        avgp=np.mean([r["port_ret"] for r in rcs])*100; avgb=np.mean([r["btc_ret"] for r in rcs])*100
        rs[reg]={"count":len(rcs),"avg_port_ret":round(avgp,2),"avg_btc_ret":round(avgb,2),"avg_alpha":round(avgp-avgb,2)}
    return {"months":len(records),"years":round(yrs,1),"port_total_pct":round(pt*100,1),"btc_total_pct":round(bt*100,1),
        "alpha_total_pct":round((pt-bt)*100,1),"ann_port_pct":round(ap*100,1),"ann_btc_pct":round(ab*100,1),
        "port_vol_pct":round(pv*100,1),"btc_vol_pct":round(bv*100,1),"port_sharpe":round(ps,2),"btc_sharpe":round(bs,2),
        "port_max_dd_pct":round(pm*100,1),"btc_max_dd_pct":round(bm*100,1),"port_calmar":round(pc,2),"btc_calmar":round(bc,2),
        "win_rate_pct":round(wr,1),"profit_months":sum(1 for r in records if r["port_ret"]>0),"regime_stats":rs}

def print_results(records, metrics, label):
    m=metrics
    print(f"\n{'='*72}\n  {label}\n{'='*72}")
    print(f"\n  Period:          {records[0]['month']} -> {records[-1]['month']} ({m['months']} months, {m['years']}y)")
    print(f"  Portfolio:       {m['port_total_pct']:+.1f}% total ({m['ann_port_pct']:+.1f}% ann.)")
    print(f"  BTC Buy-Hold:    {m['btc_total_pct']:+.1f}% total ({m['ann_btc_pct']:+.1f}% ann.)")
    print(f"  Alpha:           {m['alpha_total_pct']:+.1f}% total")
    print(f"  Volatility:      Portfolio {m['port_vol_pct']:.1f}% | BTC {m['btc_vol_pct']:.1f}%")
    print(f"  Sharpe:          Portfolio {m['port_sharpe']:.2f} | BTC {m['btc_sharpe']:.2f}")
    print(f"  Max Drawdown:    Portfolio {m['port_max_dd_pct']:.1f}% | BTC {m['btc_max_dd_pct']:.1f}%")
    print(f"  Calmar:          Portfolio {m['port_calmar']:.2f} | BTC {m['btc_calmar']:.2f}")
    print(f"  Win Rate vs BTC: {m['win_rate_pct']:.1f}% ({int(m['win_rate_pct']*m['months']/100)}/{m['months']} months)")
    print(f"  Profitable mos:  {m['profit_months']}/{m['months']}")
    print(f"\n  Regime Breakdown:")
    for reg,rs in sorted(m["regime_stats"].items()):
        print(f"    {reg:12s}: {rs['count']:2d} months | Port {rs['avg_port_ret']:+.1f}%/mo | BTC {rs['avg_btc_ret']:+.1f}%/mo | Alpha {rs['avg_alpha']:+.1f}%/mo")
    print(f"\n  Monthly Track Record:")
    print(f"  {'Month':8s} {'Regime':11s} {'BTC%':>6s} {'Alt%':>5s} {'Stbl':>5s} {'Port':>7s} {'BTC':>7s} {'Alpha':>7s} {'NAV':>8s} {'BTC_NAV':>8s}")
    print(f"  {'-'*80}")
    for r in records:
        em=" !" if r["is_emergency"] else "  "
        print(f"  {r['month']:8s} {r['regime']:11s} {r['btc_alloc']*100:5.0f}% {r['alt_alloc']*100:4.0f}% {r['stable_alloc']*100:4.0f}%"
              f"  {r['port_ret']*100:+6.1f}% {r['btc_ret']*100:+6.1f}% {(r['port_ret']-r['btc_ret'])*100:+6.1f}%"
              f"  {r['nav']:7.4f} {r['btc_nav']:7.4f}{em}")

def save_results(conn, records, metrics, weights, label):
    conn.execute("CREATE TABLE IF NOT EXISTS crypto_regime_backtest_v2 (id INTEGER PRIMARY KEY AUTOINCREMENT,run_date TEXT,label TEXT,month TEXT,composite REAL,regime TEXT,btc_alloc REAL,alt_alloc REAL,stable_alloc REAL,is_emergency INTEGER,btc_ret REAL,alt_ret REAL,port_ret REAL,nav REAL,btc_nav REAL,signals TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS crypto_regime_summary_v2 (id INTEGER PRIMARY KEY AUTOINCREMENT,run_date TEXT,label TEXT,weights TEXT,months INTEGER,port_total_pct REAL,btc_total_pct REAL,alpha_total_pct REAL,port_sharpe REAL,btc_sharpe REAL,port_max_dd_pct REAL,btc_max_dd_pct REAL,port_calmar REAL,btc_calmar REAL,win_rate_pct REAL)")
    rd=datetime.now().strftime("%Y-%m-%d %H:%M")
    for r in records:
        conn.execute("INSERT INTO crypto_regime_backtest_v2 (run_date,label,month,composite,regime,btc_alloc,alt_alloc,stable_alloc,is_emergency,btc_ret,alt_ret,port_ret,nav,btc_nav,signals) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rd,label,r["month"],r["composite"],r["regime"],r["btc_alloc"],r["alt_alloc"],r["stable_alloc"],1 if r["is_emergency"] else 0,r["btc_ret"],r["alt_ret"],r["port_ret"],r["nav"],r["btc_nav"],json.dumps(r["signals"])))
    conn.execute("INSERT INTO crypto_regime_summary_v2 (run_date,label,weights,months,port_total_pct,btc_total_pct,alpha_total_pct,port_sharpe,btc_sharpe,port_max_dd_pct,btc_max_dd_pct,port_calmar,btc_calmar,win_rate_pct) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rd,label,json.dumps(weights),metrics["months"],metrics["port_total_pct"],metrics["btc_total_pct"],metrics["alpha_total_pct"],metrics["port_sharpe"],metrics["btc_sharpe"],metrics["port_max_dd_pct"],metrics["btc_max_dd_pct"],metrics["port_calmar"],metrics["btc_calmar"],metrics["win_rate_pct"]))
    conn.commit(); print(f"\n  Saved {len(records)} records (label: {label})")

def main():
    print("="*72)
    print("  NERQ CRYPTO — Task 1.5 v2: Adaptive BTC Allocation")
    print("  Fixes: exchange filter, rating-weighted, return cap +/-80%")
    print("="*72)
    print(f"  DB: {DB_PATH}")
    print(f"  BTC range: {BTC_MIN*100:.0f}%-{BTC_MAX*100:.0f}%")
    print(f"  Emergency DD: {EMERGENCY_DD_THRESHOLD*100:.0f}%")
    print(f"  Token return cap: +/-{TOKEN_RETURN_CAP*100:.0f}%")
    conn = connect()
    print("\n  Loading data...")
    prices,volumes = load_all_prices(conn,"2020-10-01",FULL_END)
    bp = prices.get("bitcoin",{}); bd = sorted(bp.keys())
    print(f"    BTC: {len(bp)} days ({bd[0]} -> {bd[-1]})")
    ratings = load_ratings(conn,FULL_START,FULL_END)
    print(f"    Ratings: {len(ratings)} token-months")
    eligible = get_eligible_alts(prices,volumes,FULL_START,FULL_END)
    abp = {tid:prices[tid] for tid in eligible}
    print(f"    Eligible alts: {len(eligible)} (exchange-filtered, was 183 in v1)")

    print("\n"+"~"*72+"\n  PHASE 1: IN-SAMPLE (2021-2023)\n"+"~"*72)
    print("\n  Baseline (default weights):")
    isd = run_adaptive_backtest(bp,abp,bd,DEFAULT_WEIGHTS,ratings,IN_SAMPLE_START,IN_SAMPLE_END)
    ism = compute_metrics(isd)
    print(f"    Return: {ism['port_total_pct']:+.1f}% vs BTC {ism['btc_total_pct']:+.1f}%")
    print(f"    Sharpe: {ism['port_sharpe']:.2f} | DD: {ism['port_max_dd_pct']:.1f}% | Win: {ism['win_rate_pct']:.1f}%")
    bw,bs = grid_search_weights(bp,abp,bd,ratings,IN_SAMPLE_START,IN_SAMPLE_END)
    isr = run_adaptive_backtest(bp,abp,bd,bw,ratings,IN_SAMPLE_START,IN_SAMPLE_END)
    isme = compute_metrics(isr)
    print_results(isr,isme,"IN-SAMPLE (2021-2023) -- Optimized v2")

    print("\n"+"~"*72+f"\n  PHASE 2: OOS (2024-2025) -- FROZEN: {[f'{w:.2f}' for w in bw]}\n"+"~"*72)
    oosr = run_adaptive_backtest(bp,abp,bd,bw,ratings,OUT_SAMPLE_START,OUT_SAMPLE_END)
    oosm = compute_metrics(oosr)
    print_results(oosr,oosm,"OUT-OF-SAMPLE (2024-2025) -- Frozen v2")

    fr = run_adaptive_backtest(bp,abp,bd,bw,ratings,FULL_START,FULL_END)
    fm = compute_metrics(fr)
    print_results(fr,fm,"FULL PERIOD (2021-2025) v2")

    save_results(conn,isr,isme,bw,"v2_in_sample")
    save_results(conn,oosr,oosm,bw,"v2_oos")
    save_results(conn,fr,fm,bw,"v2_full")

    print("\n"+"="*72+"\n  VALIDATION (OOS) -- v2\n"+"="*72)
    checks=[
        ("Alpha > 0%",oosm["alpha_total_pct"]>0,f"{oosm['alpha_total_pct']:+.1f}%"),
        ("Sharpe > BTC",oosm["port_sharpe"]>oosm["btc_sharpe"],f"{oosm['port_sharpe']:.2f} vs {oosm['btc_sharpe']:.2f}"),
        ("Max DD < BTC DD",oosm["port_max_dd_pct"]>oosm["btc_max_dd_pct"],f"{oosm['port_max_dd_pct']:.1f}% vs {oosm['btc_max_dd_pct']:.1f}%"),
        ("Win rate > 50%",oosm["win_rate_pct"]>50,f"{oosm['win_rate_pct']:.1f}%"),
        ("Calmar > BTC",oosm["port_calmar"]>oosm["btc_calmar"],f"{oosm['port_calmar']:.2f} vs {oosm['btc_calmar']:.2f}"),
    ]
    p=0
    for name,ok,detail in checks:
        st="PASS" if ok else "FAIL"; print(f"  {'v' if ok else 'x'} {st}  {name:25s}  {detail}")
        if ok: p+=1
    print(f"\n  Result: {p}/5")
    if p>=5: print("  -> MODEL VALIDATED")
    elif p>=3: print("  -> PARTIAL -- publish with caveats")
    else: print("  -> NEEDS WORK")
    print(f"\n  FROZEN: weights={[f'{w:.2f}' for w in bw]} BTC={BTC_MIN*100:.0f}-{BTC_MAX*100:.0f}% alts={len(eligible)} cap=+/-{TOKEN_RETURN_CAP*100:.0f}%")
    conn.close(); print("  Done.")

if __name__ == "__main__":
    main()
