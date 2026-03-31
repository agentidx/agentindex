#!/usr/bin/env python3
"""
NERQ MODEL PORTFOLIO v4 — "The Inverted Model"
=================================================
Key insight: Top 20 alts outperform BTC 72% of months.
The only edge needed: avoid bear markets.

DEFAULT: 100% quality alts (rated, NDD-filtered, RCS-ranked)
BEAR:    100% cash (BTC DD < threshold from 365d ATH)

Two variants:
  CONSERVATIVE: Rating >= A,    NDD >= 2.0, top 10
  GROWTH:       Rating >= Baa3, NDD >= 1.5, top 15

Token selection: Combined score = Rating(35%) + RCS(40%) + NDD(25%)

Bear detection: BTC drawdown from 365-day ATH < threshold
  Optimized in-sample, frozen out-of-sample
"""
import sqlite3, os, sys, json, math
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

DB_NAME = "crypto_trust.db"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)

REBALANCE_COST = 0.002
TOKEN_RETURN_CAP = 1.50
MAX_TOKEN_WEIGHT = 0.15

STABLECOINS = {
    "tether","usd-coin","binance-usd","dai","true-usd","paxos-standard",
    "gusd","frax","usdd","tusd","busd","lusd","susd","eurs","usdp",
    "first-digital-usd","ethena-usde","usde","paypal-usd","fdusd",
    "stasis-eur","gemini-dollar","husd","nusd","musd","cusd",
    "terrausd","ust","magic-internet-money","euro-coin",
}
WRAPPED = {"wrapped-bitcoin","weth","wrapped-steth","wrapped-eeth","staked-ether"}

MAJOR_EXCHANGE_TOKENS = {
    "ethereum","ripple","solana","cardano","dogecoin","tron","polkadot",
    "avalanche-2","chainlink","shiba-inu","stellar","cosmos","monero",
    "hedera-hashgraph","vechain","internet-computer","litecoin","near",
    "uniswap","pepe","kaspa","sui","sei-network","celestia","arbitrum",
    "optimism","immutable-x","the-graph","render-token","fetch-ai",
    "injective-protocol","bittensor","helium","livepeer","aave",
    "curve-dao-token","maker","lido-dao","the-open-network",
    "axie-infinity","decentraland","the-sandbox","gala","enjincoin",
    "flow","decred","zilliqa","iota","eos","neo","dash","zcash",
    "algorand","fantom","kava","celo","ankr","worldcoin-wld",
    "pyth-network","layerzero","ondo-finance","ethena","jasmycoin",
    "blockstack","elrond-erd-2","crypto-com-chain","filecoin","aptos",
    "mantle","bonk","dogwifcoin","floki","theta-token","quant-network",
    "arweave","stacks","pendle","bitcoin-cash","ethereum-classic",
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

VARIANTS = {
    "CONSERVATIVE": {"min_rating": 7.0, "min_ndd": 2.0, "top_n": 10},
    "GROWTH":       {"min_rating": 5.5, "min_ndd": 1.5, "top_n": 15},
}

def connect():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found"); sys.exit(1)
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn

def load_prices(conn):
    rows = conn.execute("SELECT token_id,date,close,volume,market_cap FROM crypto_price_history ORDER BY token_id,date").fetchall()
    prices=defaultdict(dict); volumes=defaultdict(dict); mcaps=defaultdict(dict)
    for r in rows:
        prices[r["token_id"]][r["date"]]=r["close"]
        volumes[r["token_id"]][r["date"]]=r["volume"]
        mcaps[r["token_id"]][r["date"]]=r["market_cap"]
    return dict(prices),dict(volumes),dict(mcaps)

def load_ratings(conn):
    rows = conn.execute("SELECT token_id,year_month,rating,score,pillar_1,pillar_2,pillar_3,pillar_4,pillar_5 FROM crypto_rating_history").fetchall()
    return {(r["token_id"],r["year_month"]):{"rating":r["rating"],"score":r["score"]} for r in rows}

def load_ndd(conn):
    rows = conn.execute("SELECT token_id,substr(week_date,1,7) as ym,AVG(ndd) as n FROM crypto_ndd_history GROUP BY token_id,substr(week_date,1,7)").fetchall()
    return {(r["token_id"],r["ym"]):r["n"] for r in rows}

def compute_btc_dd(btc_prices, btc_dates, date):
    idx = None
    for i,d in enumerate(btc_dates):
        if d<=date: idx=i
        else: break
    if idx is None: return 0
    start=max(0,idx-365)
    window=[btc_prices[btc_dates[i]] for i in range(start,idx+1)]
    if not window: return 0
    return (btc_prices[btc_dates[idx]]/max(window))-1

def compute_rcs(token_id, ym, prices, ratings, eligible):
    rdata=ratings.get((token_id,ym))
    if not rdata: return 0.0
    my_class=RATING_CLASS.get(rdata["rating"],"UNK")
    my_score=RATING_SCORE.get(rdata["rating"],5.0)
    ref=f"{ym}-01"
    tp=prices.get(token_id,{}); td=sorted(tp.keys())
    def r90(pp,pd,ref):
        idx=None
        for i,d in enumerate(pd):
            if d<=ref: idx=i
            else: break
        if idx is None or idx<90: return None
        si=max(0,idx-90)
        pe=pp.get(pd[idx]); ps=pp.get(pd[si])
        if pe and ps and ps>0: return (pe/ps)-1
        return None
    my_ret=r90(tp,td,ref)
    if my_ret is None: return 0.0
    peers=[]
    for tid in eligible:
        if tid==token_id: continue
        pr=ratings.get((tid,ym))
        if not pr: continue
        pc=RATING_CLASS.get(pr["rating"],"UNK")
        ps=RATING_SCORE.get(pr["rating"],5.0)
        if pc!=my_class and abs(ps-my_score)>2.0: continue
        pp=prices.get(tid,{}); pd=sorted(pp.keys())
        r=r90(pp,pd,ref)
        if r is not None: peers.append(r)
    if not peers: return 0.0
    return max(-10,min(10,(my_ret-np.median(peers))*20))

def select_tokens(prices, ratings, ndd_data, eligible, ym, min_rs, min_ndd, top_n):
    cands=[]
    for tid in eligible:
        rd=ratings.get((tid,ym))
        if not rd: continue
        rs=RATING_SCORE.get(rd["rating"],0)
        if rs<min_rs: continue
        nv=ndd_data.get((tid,ym))
        if nv is None or nv<min_ndd: continue
        rcs=compute_rcs(tid,ym,prices,ratings,eligible)
        combined=0.35*(rs)+0.40*((rcs+10)/2.0)+0.25*(nv*2.0)
        cands.append({"token":tid,"rating":rd["rating"],"rating_score":rs,
                       "rcs":round(rcs,2),"ndd":round(nv,2),"combined":round(combined,3)})
    cands.sort(key=lambda x:x["combined"],reverse=True)
    sel=cands[:top_n]
    if not sel: return []
    total=sum(s["combined"] for s in sel)
    for s in sel:
        raw=s["combined"]/total if total>0 else 1.0/len(sel)
        s["weight"]=min(MAX_TOKEN_WEIGHT,max(0.02,raw))
    tw=sum(s["weight"] for s in sel)
    for s in sel: s["weight"]=round(s["weight"]/tw,4)
    return sel

def select_top20_mcap(prices, mcaps, eligible, ym):
    cands=[]
    for tid in eligible:
        mc=mcaps.get(tid,{})
        mv=None
        for d in sorted(mc.keys()):
            if d.startswith(ym): mv=mc[d]; break
        if mv and mv>0: cands.append({"token":tid,"mcap":mv})
    cands.sort(key=lambda x:x["mcap"],reverse=True)
    sel=cands[:20]
    if not sel: return []
    w=1.0/len(sel)
    for s in sel: s["weight"]=round(w,4); s["rating"]="N/A"; s["rcs"]=0; s["ndd"]=0; s["combined"]=0; s["rating_score"]=0
    return sel

def run_backtest(prices, mcaps, btc_p, btc_d, ratings, ndd, elig, bear_th, vcfg, vname, start="2021-01", end="2025-12", use_ratings=True):
    records=[]; nav=1.0; bnav=1.0
    cur=datetime.strptime(f"{start}-01","%Y-%m-%d")
    end_dt=datetime.strptime(f"{end}-28","%Y-%m-%d")
    while cur<=end_dt:
        ym=cur.strftime("%Y-%m")
        nm=cur.replace(year=cur.year+1,month=1,day=1) if cur.month==12 else cur.replace(month=cur.month+1,day=1)
        ed=(nm-timedelta(days=1)).strftime("%Y-%m-%d")
        fd=cur.strftime("%Y-%m-%d")
        ea=ex=None
        for d in btc_d:
            if d>=fd and ea is None: ea=d
            if d>=ed and ex is None: ex=d
            if d>ed: break
        if not ex: ex=btc_d[-1]
        if ea is None or ea>=ex: cur=nm; continue
        bp1=btc_p.get(ea,0); bp2=btc_p.get(ex,0)
        btc_ret=(bp2/bp1-1) if bp1>0 else 0
        dd=compute_btc_dd(btc_p,btc_d,ea)
        bear=dd<bear_th
        if bear:
            port_ret=0.0; regime="BEAR"; selected=[]; alloc="CASH 100%"
        else:
            if use_ratings:
                selected=select_tokens(prices,ratings,ndd,elig,ym,vcfg["min_rating"],vcfg["min_ndd"],vcfg["top_n"])
            else:
                selected=[]
            if not selected:
                selected=select_top20_mcap(prices,mcaps,elig,ym)
            if selected:
                tr=0.0; tw=0.0
                for t in selected:
                    tp=prices.get(t["token"],{})
                    pe=tp.get(ea); px=tp.get(ex)
                    if pe and px and pe>0:
                        ret=max(-TOKEN_RETURN_CAP,min(TOKEN_RETURN_CAP,(px/pe)-1))
                        tr+=t["weight"]*ret; tw+=t["weight"]
                if tw>0 and tw<0.95: tr/=tw
                port_ret=tr
            else:
                port_ret=btc_ret
            regime="ALTS"; alloc=f"Top {len(selected)} alts"
        port_ret-=REBALANCE_COST
        nav*=(1+port_ret); bnav*=(1+btc_ret)
        top3=", ".join(f"{t['token'][:10]}({t['weight']*100:.0f}%)" for t in selected[:3]) if selected else "-"
        records.append({"month":ym,"regime":regime,"alloc":alloc,"top_holdings":top3,
            "n_tokens":len(selected),"btc_dd":round(dd*100,1),"btc_ret":round(btc_ret,4),
            "alt_ret":round(port_ret+REBALANCE_COST,4),"port_ret":round(port_ret,4),
            "nav":round(nav,4),"btc_nav":round(bnav,4),"alpha_m":round((port_ret-btc_ret)*100,2)})
        cur=nm
    return records

def compute_metrics(records, label=""):
    if not records: return {}
    pr=[r["port_ret"] for r in records]; br=[r["btc_ret"] for r in records]
    nav=1.0; bnav=1.0; navs=[]; bnavs=[]
    for p,b in zip(pr,br):
        nav*=(1+p); bnav*=(1+b); navs.append(nav); bnavs.append(bnav)
    yrs=len(records)/12
    pt=nav-1; bt=bnav-1
    ap=nav**(1/yrs)-1 if yrs>0 else 0; ab=bnav**(1/yrs)-1 if yrs>0 else 0
    pv=np.std(pr)*math.sqrt(12); bv=np.std(br)*math.sqrt(12)
    rf=0.045
    ps=(ap-rf)/pv if pv>0 else 0; bs=(ab-rf)/bv if bv>0 else 0
    def mdd(ns):
        pk=ns[0];m=0
        for n in ns:
            if n>pk:pk=n
            dd=(n/pk)-1
            if dd<m:m=dd
        return m
    pm=mdd(navs);bm=mdd(bnavs)
    pc=ap/abs(pm) if pm!=0 else 0; bc=ab/abs(bm) if bm!=0 else 0
    wins=sum(1 for p,b in zip(pr,br) if p>=b)
    regimes=defaultdict(int)
    for r in records: regimes[r["regime"]]+=1
    return {"label":label,"months":len(records),
        "port_total":round(pt*100,1),"btc_total":round(bt*100,1),"alpha":round((pt-bt)*100,1),
        "ann_port":round(ap*100,1),"ann_btc":round(ab*100,1),
        "vol_port":round(pv*100,1),"vol_btc":round(bv*100,1),
        "sharpe_port":round(ps,2),"sharpe_btc":round(bs,2),
        "dd_port":round(pm*100,1),"dd_btc":round(bm*100,1),
        "calmar_port":round(pc,2),"calmar_btc":round(bc,2),
        "win_rate":round(wins/len(records)*100,1),
        "regimes":dict(regimes),"final_nav":round(nav,2),"final_btc":round(bnav,2)}

def print_results(records, metrics):
    m=metrics
    print(f"\n{'='*80}")
    print(f"  {m['label']}")
    print(f"{'='*80}")
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
    print(f"  $10K ->       ${m['final_nav']*10000:,.0f} (port) | ${m['final_btc']*10000:,.0f} (BTC)")
    print(f"\n  {'Month':8s} {'Rgm':5s} {'DD%':>5s} {'Port':>7s} {'BTC':>7s} {'a':>6s} {'NAV':>8s} {'BTC_N':>8s}  {'Top Holdings'}")
    print(f"  {'-'*100}")
    for r in records:
        print(f"  {r['month']:8s} {r['regime']:5s} {r['btc_dd']:+4.0f}%"
              f" {r['port_ret']*100:+6.1f}% {r['btc_ret']*100:+6.1f}% {r['alpha_m']:+5.1f}%"
              f" {r['nav']:7.4f} {r['btc_nav']:7.4f}  {r['top_holdings']}")

def main():
    print("="*80)
    print("  NERQ MODEL PORTFOLIO v4 — 'The Inverted Model'")
    print("  Default: ALTS | Only switch: BEAR -> CASH")
    print("  Insight: Top20 alts beat BTC 72% of months")
    print("="*80)
    conn=connect()
    print(f"\n  DB: {DB_PATH}")
    print("  Loading data...")
    prices,volumes,mcaps=load_prices(conn)
    btc_p=prices.get("bitcoin",{}); btc_d=sorted(btc_p.keys())
    ratings=load_ratings(conn); ndd=load_ndd(conn)
    elig=[]
    for tid in MAJOR_EXCHANGE_TOKENS:
        if tid in STABLECOINS or tid in WRAPPED or tid=="bitcoin": continue
        if tid not in prices: continue
        if len([d for d in prices[tid] if "2021-01"<=d<="2025-12-31"])<60: continue
        elig.append(tid)
    print(f"    BTC: {len(btc_p)} days | Ratings: {len(ratings)} | NDD: {len(ndd)} | Eligible: {len(elig)}")

    # === BASELINE: Top20 by mcap ===
    print(f"\n{'#'*80}")
    print("  BASELINE: Top 20 by market cap (no ratings)")
    print(f"{'#'*80}")
    best_dd_b=-0.25; best_cal_b=-999
    print("\n  Optimizing bear threshold (baseline)...")
    for dd in np.arange(-0.10,-0.51,-0.05):
        recs=run_backtest(prices,mcaps,btc_p,btc_d,ratings,ndd,elig,dd,VARIANTS["GROWTH"],"BASE","2021-01","2023-12",False)
        m=compute_metrics(recs,"t")
        cal=m["ann_port"]/abs(m["dd_port"]/100) if m["dd_port"]<0 else 0
        bn=sum(1 for r in recs if r["regime"]=="BEAR")
        if bn>24: cal*=0.5
        print(f"    DD={dd:.2f}: ret={m['port_total']:+.1f}% maxDD={m['dd_port']:.1f}% cal={cal:.2f} bear={bn}")
        if cal>best_cal_b: best_cal_b=cal; best_dd_b=dd
    print(f"  -> Best: {best_dd_b:.2f}")
    for label,s,e in [("IS 2021-2023","2021-01","2023-12"),("OOS 2024-2025 (FROZEN)","2024-01","2025-12")]:
        recs=run_backtest(prices,mcaps,btc_p,btc_d,ratings,ndd,elig,best_dd_b,VARIANTS["GROWTH"],"BASE",s,e,False)
        m=compute_metrics(recs,f"BASELINE {label}")
        print_results(recs,m)

    # === RATED VARIANTS ===
    for vname,vcfg in VARIANTS.items():
        print(f"\n{'#'*80}")
        print(f"  {vname}: Rating>={vcfg['min_rating']} NDD>={vcfg['min_ndd']} Top{vcfg['top_n']}")
        print(f"{'#'*80}")
        best_dd=-0.25; best_cal=-999
        print(f"\n  Optimizing bear threshold ({vname})...")
        for dd in np.arange(-0.10,-0.51,-0.05):
            recs=run_backtest(prices,mcaps,btc_p,btc_d,ratings,ndd,elig,dd,vcfg,vname,"2021-01","2023-12",True)
            m=compute_metrics(recs,"t")
            cal=m["ann_port"]/abs(m["dd_port"]/100) if m["dd_port"]<0 else 0
            bn=sum(1 for r in recs if r["regime"]=="BEAR")
            if bn>24: cal*=0.5
            print(f"    DD={dd:.2f}: ret={m['port_total']:+.1f}% maxDD={m['dd_port']:.1f}% cal={cal:.2f} bear={bn}")
            if cal>best_cal: best_cal=cal; best_dd=dd
        print(f"  -> Best: {best_dd:.2f}")
        for label,s,e in [("IS 2021-2023","2021-01","2023-12"),("OOS 2024-2025 (FROZEN)","2024-01","2025-12")]:
            recs=run_backtest(prices,mcaps,btc_p,btc_d,ratings,ndd,elig,best_dd,vcfg,vname,s,e,True)
            m=compute_metrics(recs,f"{vname} {label}")
            print_results(recs,m)
            if "OOS" in label:
                save_results(conn,recs,m,best_dd,vname)
                print(f"\n  VALIDATION ({vname} OOS):")
                checks=[
                    ("Alpha > 0%",m["alpha"]>0,f"{m['alpha']:+.1f}%"),
                    ("Sharpe > BTC",m["sharpe_port"]>m["sharpe_btc"],f"{m['sharpe_port']:.2f} vs {m['sharpe_btc']:.2f}"),
                    ("Max DD < BTC",m["dd_port"]>m["dd_btc"],f"{m['dd_port']:.1f}% vs {m['dd_btc']:.1f}%"),
                    ("Win rate > 50%",m["win_rate"]>50,f"{m['win_rate']:.1f}%"),
                    ("Calmar > BTC",m["calmar_port"]>m["calmar_btc"],f"{m['calmar_port']:.2f} vs {m['calmar_btc']:.2f}"),
                ]
                passed=0
                for name,ok,detail in checks:
                    st="v PASS" if ok else "x FAIL"
                    print(f"    {st}  {name:25s}  {detail}")
                    if ok: passed+=1
                print(f"    Result: {passed}/5")
    conn.close()
    print(f"\n  Done.")

def save_results(conn,records,metrics,bear_th,variant):
    conn.execute("""CREATE TABLE IF NOT EXISTS nerq_portfolio_v4 (id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT,variant TEXT,month TEXT,regime TEXT,alloc TEXT,n_tokens INTEGER,top_holdings TEXT,
        btc_dd REAL,btc_ret REAL,alt_ret REAL,port_ret REAL,nav REAL,btc_nav REAL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS nerq_portfolio_v4_summary (id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT,variant TEXT,bear_threshold REAL,period TEXT,months INTEGER,
        port_total REAL,btc_total REAL,alpha REAL,sharpe_port REAL,sharpe_btc REAL,
        dd_port REAL,dd_btc REAL,calmar_port REAL,calmar_btc REAL,win_rate REAL)""")
    rd=datetime.now().strftime("%Y-%m-%d %H:%M")
    for r in records:
        conn.execute("INSERT INTO nerq_portfolio_v4 (run_date,variant,month,regime,alloc,n_tokens,top_holdings,btc_dd,btc_ret,alt_ret,port_ret,nav,btc_nav) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rd,variant,r["month"],r["regime"],r["alloc"],r["n_tokens"],r["top_holdings"],r["btc_dd"],r["btc_ret"],r["alt_ret"],r["port_ret"],r["nav"],r["btc_nav"]))
    m=metrics
    conn.execute("INSERT INTO nerq_portfolio_v4_summary (run_date,variant,bear_threshold,period,months,port_total,btc_total,alpha,sharpe_port,sharpe_btc,dd_port,dd_btc,calmar_port,calmar_btc,win_rate) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rd,variant,bear_th,m["label"],m["months"],m["port_total"],m["btc_total"],m["alpha"],m["sharpe_port"],m["sharpe_btc"],m["dd_port"],m["dd_btc"],m["calmar_port"],m["calmar_btc"],m["win_rate"]))
    conn.commit()

if __name__=="__main__":
    main()
