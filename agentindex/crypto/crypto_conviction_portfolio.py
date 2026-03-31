#!/usr/bin/env python3
"""
NERQ CRYPTO — Conviction Pairs Portfolio v3
=============================================
v3: Added major exchange tradability filter.
Only tokens available on Coinbase/Binance/Kraken are eligible.

Run:  python3 crypto_conviction_portfolio.py
"""

import sqlite3
import os
import sys
import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter

import numpy as np

DB_NAME = "crypto_trust.db"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)

IN_SAMPLE_START  = "2021-01-01"
IN_SAMPLE_END    = "2023-12-31"
OUT_SAMPLE_START = "2024-01-01"
OUT_SAMPLE_END   = "2025-12-31"

HOLD_DAYS = 90
MAX_RETURN_CAP = 1.0
MIN_AVG_VOLUME = 50_000
MIN_PRICE_COVERAGE = 0.70
MIN_NDD_FOR_SHORT = 1.5
BEST_WEIGHTS = [0.10, 0.30, 0.30, 0.15, 0.15]

STABLECOINS = {
    "tether","usd-coin","binance-usd","dai","true-usd","paxos-standard",
    "gusd","frax","usdd","tusd","busd","lusd","susd","eurs","usdp",
    "first-digital-usd","ethena-usde","usde","paypal-usd","fdusd",
    "stasis-eur","gemini-dollar","husd","nusd","musd","cusd",
    "terrausd","ust","magic-internet-money","euro-coin","ondo-us-dollar-yield",
}

MAJOR_EXCHANGE_TOKENS = {
    "bitcoin","ethereum","ripple","solana","cardano",
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

RATING_CLASSES = {
    "IG_HIGH":["Aaa","Aa1","Aa2","Aa3"],"IG_MID":["A1","A2","A3"],
    "IG_LOW":["Baa1","Baa2","Baa3"],"HY_HIGH":["Ba1","Ba2","Ba3"],
    "HY_LOW":["B1","B2","B3"],"DISTRESS":["Caa1","Caa2","Caa3","Ca","C","D"],
}
RATING_TO_CLASS = {}
for cls,rats in RATING_CLASSES.items():
    for r in rats: RATING_TO_CLASS[r]=cls

CONFIGS = [
    (0.6,0.4,5,["IG_MID"],2,0.15,"MID_t5_cap2_rg15"),
    (0.6,0.4,5,["IG_MID"],1,0.15,"MID_t5_cap1_rg15"),
    (0.6,0.4,7,["IG_MID"],2,0.15,"MID_t7_cap2_rg15"),
    (0.6,0.4,3,["IG_MID"],2,0.15,"MID_t3_cap2_rg15"),
    (0.6,0.4,5,["IG_MID","IG_LOW"],2,0.15,"MID+LOW_t5_cap2_rg15"),
    (0.6,0.4,7,["IG_MID","IG_LOW"],2,0.15,"MID+LOW_t7_cap2_rg15"),
    (0.5,0.5,5,["IG_MID"],2,0.15,"eq_MID_t5_cap2_rg15"),
    (0.7,0.3,5,["IG_MID"],2,0.15,"spr_MID_t5_cap2_rg15"),
    (0.4,0.6,5,["IG_MID"],2,0.15,"ndd_MID_t5_cap2_rg15"),
    (0.6,0.4,5,["IG_MID"],2,0.10,"MID_t5_cap2_rg10"),
    (0.6,0.4,5,["IG_MID"],2,0.20,"MID_t5_cap2_rg20"),
    (0.6,0.4,5,["IG_MID"],2,None,"MID_t5_cap2_noRG"),
    (0.6,0.4,5,["IG_MID","IG_LOW","IG_HIGH"],2,0.15,"ALL_IG_t5_cap2_rg15"),
    (0.6,0.4,7,["IG_MID","IG_LOW","IG_HIGH"],2,0.15,"ALL_IG_t7_cap2_rg15"),
]

def get_db():
    if not os.path.exists(DB_PATH): print(f"ERROR: {DB_PATH}"); sys.exit(1)
    conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row; return conn

def load_prices(conn,s,e):
    rows=conn.execute("SELECT token_id,date,close FROM crypto_price_history WHERE date>=? AND date<=? ORDER BY token_id,date",(s,e)).fetchall()
    p=defaultdict(dict)
    for r in rows: p[r["token_id"]][r["date"]]=r["close"]
    return dict(p)

def load_volumes(conn,s,e):
    rows=conn.execute("SELECT token_id,AVG(volume) as v,COUNT(*) as d FROM crypto_price_history WHERE date>=? AND date<=? GROUP BY token_id",(s,e)).fetchall()
    return {r["token_id"]:{"avg_vol":r["v"] or 0,"days":r["d"]} for r in rows}

def load_ratings(conn,s,e):
    rows=conn.execute("SELECT token_id,year_month,rating,score,pillar_1,pillar_2,pillar_3,pillar_4,pillar_5 FROM crypto_rating_history WHERE year_month>=? AND year_month<=?",(s,e)).fetchall()
    return {(r["token_id"],r["year_month"]):{"rating":r["rating"],"score":r["score"],"pillars":[r["pillar_1"],r["pillar_2"],r["pillar_3"],r["pillar_4"],r["pillar_5"]]} for r in rows}

def load_ndd_monthly(conn,s,e):
    rows=conn.execute("SELECT token_id,substr(week_date,1,7) as ym,AVG(ndd) as n FROM crypto_ndd_history WHERE week_date>=? AND week_date<=? GROUP BY token_id,substr(week_date,1,7)",(s,e)).fetchall()
    return {(r["token_id"],r["ym"]):r["n"] for r in rows}

def load_btc_prices(conn,s,e):
    for tid in ["bitcoin","btc","BTC"]:
        rows=conn.execute("SELECT date,close FROM crypto_price_history WHERE token_id=? AND date>=? AND date<=? ORDER BY date",(tid,s,e)).fetchall()
        if rows: return {r["date"]:r["close"] for r in rows}
    return {}

def build_eligible(volumes,s,e):
    td=(datetime.strptime(e,"%Y-%m-%d")-datetime.strptime(s,"%Y-%m-%d")).days
    eligible=set(); filtered=Counter()
    for tid,v in volumes.items():
        if tid.lower() in STABLECOINS: filtered["stablecoin"]+=1; continue
        if tid not in MAJOR_EXCHANGE_TOKENS: filtered["not_on_major_exchange"]+=1; continue
        if v["avg_vol"]<MIN_AVG_VOLUME: filtered["low_volume"]+=1; continue
        if v["days"]/max(td,1)<MIN_PRICE_COVERAGE: filtered["low_coverage"]+=1; continue
        eligible.add(tid)
    return eligible,dict(filtered)

def build_btc_monthly_returns(btc):
    ret={}
    for d in sorted(btc.keys()):
        if d[8:10]!="01": continue
        t30=(datetime.strptime(d,"%Y-%m-%d")-timedelta(days=30)).strftime("%Y-%m-%d")
        pn=btc[d]; p30=None
        for off in range(8):
            c=(datetime.strptime(t30,"%Y-%m-%d")+timedelta(days=off)).strftime("%Y-%m-%d")
            if c in btc: p30=btc[c]; break
        if pn and p30 and p30>0: ret[d[:7]]=(pn-p30)/p30
    return ret

def comp_score(pillars,w):
    if not pillars or any(p is None for p in pillars): return None
    return sum(p*ww for p,ww in zip(pillars,w))

def closest_date(ds,target,mx=7):
    t=datetime.strptime(target,"%Y-%m-%d")
    for o in range(mx+1):
        for d in [o,-o]:
            c=(t+timedelta(days=d)).strftime("%Y-%m-%d")
            if c in ds: return c
    return None

def pair_return(prices,lid,sid,entry):
    ex=(datetime.strptime(entry,"%Y-%m-%d")+timedelta(days=HOLD_DAYS)).strftime("%Y-%m-%d")
    lp,sp=prices.get(lid,{}),prices.get(sid,{})
    if not lp or not sp: return None
    el=closest_date(set(lp.keys()),entry); es=closest_date(set(sp.keys()),entry)
    xl=closest_date(set(lp.keys()),ex); xs=closest_date(set(sp.keys()),ex)
    if not all([el,es,xl,xs]) or lp[el]<=0 or sp[es]<=0: return None
    lr=max(-MAX_RETURN_CAP,min(MAX_RETURN_CAP,(lp[xl]-lp[el])/lp[el]))
    sr=max(-MAX_RETURN_CAP,min(MAX_RETURN_CAP,(sp[xs]-sp[es])/sp[es]))
    a=lr-sr
    return {"long_return":lr,"short_return":sr,"pair_alpha":a,"hit":1 if a>0 else 0,"entry_date":entry,"exit_date":ex}

def gen_scored_pairs(ratings,ndd,ym,eligible,w,classes,sw,nw):
    ct=defaultdict(list)
    for (tid,m),data in ratings.items():
        if m!=ym or tid not in eligible: continue
        cls=RATING_TO_CLASS.get(data["rating"])
        if not cls or cls not in classes: continue
        c=comp_score(data["pillars"],w)
        if c is None: continue
        ct[cls].append({"tid":tid,"comp":c,"ndd":ndd.get((tid,ym),2.5)})
    pairs=[]
    for cls,toks in ct.items():
        if len(toks)<4: continue
        toks.sort(key=lambda x:x["comp"],reverse=True)
        n=len(toks); q=max(1,n//4)
        longs=toks[:q]
        shorts=[s for s in toks[-q:] if ndd.get((s["tid"],ym),3.0)>=MIN_NDD_FOR_SHORT]
        for lt in longs:
            for st in shorts:
                if lt["tid"]==st["tid"]: continue
                pairs.append({"long":lt["tid"],"short":st["tid"],"class":cls,
                    "spread":lt["comp"]-st["comp"],"ndd_diff":lt["ndd"]-st["ndd"]})
    if not pairs: return []
    sps=[p["spread"] for p in pairs]; nds=[p["ndd_diff"] for p in pairs]
    sr=max(sps)-min(sps) or 1; nr=max(nds)-min(nds) or 1
    smn,nmn=min(sps),min(nds)
    for p in pairs: p["conviction"]=sw*((p["spread"]-smn)/sr)+nw*((p["ndd_diff"]-nmn)/nr)
    pairs.sort(key=lambda p:p["conviction"],reverse=True)
    return pairs

def apply_cap(pairs,mt):
    sel=[]; tc=Counter()
    for p in pairs:
        if tc[p["long"]]>=mt or tc[p["short"]]>=mt: continue
        sel.append(p); tc[p["long"]]+=1; tc[p["short"]]+=1
    return sel

def run_bt(prices,ratings,ndd,eligible,w,cls,sw,nw,tn,mt,rg,btc_mr,sd,ed):
    results=[]; picks={}; skipped=0
    cur=datetime.strptime(sd,"%Y-%m-%d"); end=datetime.strptime(ed,"%Y-%m-%d")
    while cur<=end:
        ym=cur.strftime("%Y-%m"); entry=cur.strftime("%Y-%m-%d")
        if cur+timedelta(days=HOLD_DAYS)>end+timedelta(days=HOLD_DAYS): break
        if rg is not None:
            br=btc_mr.get(ym)
            if br is not None and br<-rg:
                skipped+=1
                cur=cur.replace(year=cur.year+1,month=1,day=1) if cur.month==12 else cur.replace(month=cur.month+1,day=1)
                continue
        scored=gen_scored_pairs(ratings,ndd,ym,eligible,w,cls,sw,nw)
        capped=apply_cap(scored,mt)
        top=capped[:tn]; mr=[]
        for p in top:
            ret=pair_return(prices,p["long"],p["short"],entry)
            if ret:
                ret.update({"long_id":p["long"],"short_id":p["short"],"class":p["class"],
                    "conviction":p["conviction"],"spread":p["spread"],"ndd_diff":p["ndd_diff"]})
                mr.append(ret)
        results.extend(mr)
        if mr: picks[ym]=[{"long":r["long_id"],"short":r["short_id"],"conviction":round(r["conviction"],3)} for r in mr]
        cur=cur.replace(year=cur.year+1,month=1,day=1) if cur.month==12 else cur.replace(month=cur.month+1,day=1)
    return results,picks,skipped

def metrics(results,btc=None):
    if not results:
        return {"total_pairs":0,"hit_rate":0,"avg_alpha":0,"median_alpha":0,"sharpe":0,
                "max_dd":0,"btc_sharpe":0,"months":0,"avg_per_month":0,"win_avg":0,
                "lose_avg":0,"best":0,"worst":0,"pct_profitable_months":0}
    alphas=[r["pair_alpha"] for r in results]
    hits=sum(1 for a in alphas if a>0)
    winners=[a for a in alphas if a>0]; losers=[a for a in alphas if a<=0]
    ms=sorted(set(r["entry_date"][:7] for r in results))
    std=np.std(alphas) if len(alphas)>1 else 1.0
    sharpe=(np.mean(alphas)/std)*np.sqrt(4) if std>0 else 0
    cum=np.cumsum(alphas); rmx=np.maximum.accumulate(cum)
    mdd=abs(np.min(cum-rmx))*100 if len(cum)>0 else 0
    ma={}
    for r in results:
        ym=r["entry_date"][:7]; ma.setdefault(ym,[]).append(r["pair_alpha"])
    pm=sum(1 for als in ma.values() if np.mean(als)>0)
    bs=0
    if btc and len(btc)>90:
        bsr=sorted(btc.items()); br=[]
        for i in range(0,len(bsr)-90,30):
            p0=bsr[i][1]; p1=bsr[min(i+90,len(bsr)-1)][1]
            if p0>0: br.append((p1-p0)/p0)
        if br and np.std(br)>0: bs=(np.mean(br)/np.std(br))*np.sqrt(4)
    return {"total_pairs":len(results),"months":len(ms),
        "avg_per_month":round(len(results)/max(len(ms),1),1),
        "hit_rate":round(hits/len(results)*100,1),
        "avg_alpha":round(np.mean(alphas)*100,2),
        "median_alpha":round(np.median(alphas)*100,2),
        "sharpe":round(sharpe,3),"max_dd":round(mdd,2),"btc_sharpe":round(bs,3),
        "win_avg":round(np.mean(winners)*100,2) if winners else 0,
        "lose_avg":round(np.mean(losers)*100,2) if losers else 0,
        "best":round(max(alphas)*100,2),"worst":round(min(alphas)*100,2),
        "profitable_months":pm,"pct_profitable_months":round(pm/max(len(ms),1)*100,1)}

def main():
    print("="*72)
    print("NERQ CRYPTO — PAIR SIGNALS v3 (Major Exchange Filter)")
    print(f"DB: {DB_PATH}")
    print(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Weights: [{' | '.join(f'{w:.2f}' for w in BEST_WEIGHTS)}]")
    print(f"Winsorize: +/-{MAX_RETURN_CAP*100:.0f}%")
    print(f"Exchange whitelist: {len(MAJOR_EXCHANGE_TOKENS)} tokens")
    print("="*72)

    conn=get_db()
    print("\n  Loading data...")
    is_p=load_prices(conn,IN_SAMPLE_START,IN_SAMPLE_END)
    oos_p=load_prices(conn,OUT_SAMPLE_START,OUT_SAMPLE_END)
    is_r=load_ratings(conn,"2021-01","2023-12")
    oos_r=load_ratings(conn,"2024-01","2025-12")
    is_n=load_ndd_monthly(conn,IN_SAMPLE_START,IN_SAMPLE_END)
    oos_n=load_ndd_monthly(conn,OUT_SAMPLE_START,OUT_SAMPLE_END)
    all_btc=load_btc_prices(conn,"2020-12-01",OUT_SAMPLE_END)
    btc_oos=load_btc_prices(conn,OUT_SAMPLE_START,OUT_SAMPLE_END)
    btc_mr=build_btc_monthly_returns(all_btc)
    is_vols=load_volumes(conn,IN_SAMPLE_START,IN_SAMPLE_END)
    oos_vols=load_volumes(conn,OUT_SAMPLE_START,OUT_SAMPLE_END)
    is_el,is_filt=build_eligible(is_vols,IN_SAMPLE_START,IN_SAMPLE_END)
    oos_el,oos_filt=build_eligible(oos_vols,OUT_SAMPLE_START,OUT_SAMPLE_END)
    print(f"    IS eligible: {len(is_el)} tokens")
    for r,c in sorted(is_filt.items()): print(f"      Filtered ({r}): {c}")
    print(f"    OOS eligible: {len(oos_el)} tokens")
    for r,c in sorted(oos_filt.items()): print(f"      Filtered ({r}): {c}")

    # Phase 1
    print("\n"+"="*72)
    print("PHASE 1: IN-SAMPLE (2021-2023)")
    print("="*72)
    hdr=f"  {'Label':<30} {'P':>4} {'/mo':>4} {'HR':>6} {'a':>8} {'med':>8} {'S':>7} {'DD':>8} {'P%':>5} {'sk':>3} {'score':>7}"
    print(hdr); print(f"  {'-'*96}")
    all_is=[]
    for cfg in CONFIGS:
        sw,nw,tn,cls,mt,rg,label=cfg
        res,_,sk=run_bt(is_p,is_r,is_n,is_el,BEST_WEIGHTS,cls,sw,nw,tn,mt,rg,btc_mr,IN_SAMPLE_START,IN_SAMPLE_END)
        m=metrics(res)
        sp=max(0,30-m["total_pairs"])*1.5
        cb=m["pct_profitable_months"]*0.3
        score=(m["hit_rate"]-50)*2+m["avg_alpha"]*2+m["median_alpha"]*3+max(0,m["sharpe"])*15+cb-sp
        all_is.append({"cfg":cfg,"label":label,"m":m,"score":score,"skip":sk})
        print(f"  {label:<30} {m['total_pairs']:>4} {m['avg_per_month']:>4.0f} {m['hit_rate']:>5.1f}% {m['avg_alpha']:>7.2f}% {m['median_alpha']:>7.2f}% {m['sharpe']:>7.3f} {m['max_dd']:>7.1f}% {m['pct_profitable_months']:>4.0f}% {sk:>3} {score:>7.1f}")

    all_is.sort(key=lambda x:x["score"],reverse=True)
    best=all_is[0]; bc=best["cfg"]
    bsw,bnw,btn,bcls,bmt,brg,blabel=bc; bm=best["m"]
    print(f"\n  {'-'*60}")
    print(f"  BEST: {blabel}")
    print(f"    Classes:{bcls} top_n={btn} cap={bmt} regime={'BTC<-'+f'{brg*100:.0f}%' if brg else 'None'}")
    print(f"    HR:{bm['hit_rate']:.1f}% a:{bm['avg_alpha']:.2f}% med:{bm['median_alpha']:.2f}% S:{bm['sharpe']:.3f} P%:{bm['pct_profitable_months']:.0f}%")
    print(f"\n  TOP 5:")
    for i,r in enumerate(all_is[:5]):
        m=r["m"]
        print(f"    {i+1}. {r['label']:<30} HR:{m['hit_rate']:.1f}% a:{m['avg_alpha']:.2f}% med:{m['median_alpha']:.2f}% S:{m['sharpe']:.3f} P%:{m['pct_profitable_months']:.0f}%")

    # Phase 2
    print("\n"+"="*72)
    print("PHASE 2: OUT-OF-SAMPLE (2024-2025) — FROZEN")
    print(f"  Config: {blabel}")
    print("="*72)
    oos_res,oos_picks,oos_sk=run_bt(oos_p,oos_r,oos_n,oos_el,BEST_WEIGHTS,bcls,bsw,bnw,btn,bmt,brg,btc_mr,OUT_SAMPLE_START,OUT_SAMPLE_END)
    om=metrics(oos_res,btc_oos)
    print(f"  Months skipped: {oos_sk}")

    # Results
    print("\n"+"="*72)
    print("RESULTS — PAIR SIGNALS v3 (Tradeable Only)")
    print("="*72)
    print(f"\n  {'Metric':<28} {'In-Sample':>15} {'Out-of-Sample':>15}")
    print(f"  {'-'*60}")
    for lbl,iv,ov in [("Total Pairs",bm['total_pairs'],om['total_pairs']),("Active Months",bm['months'],om['months']),("Avg Pairs/Month",bm['avg_per_month'],om['avg_per_month'])]:
        print(f"  {lbl:<28} {iv:>15} {ov:>15}")
    for lbl,iv,ov in [("Hit Rate",bm['hit_rate'],om['hit_rate']),("Avg Alpha (90d)",bm['avg_alpha'],om['avg_alpha']),("Median Alpha (90d)",bm['median_alpha'],om['median_alpha']),("Max Drawdown",bm['max_dd'],om['max_dd']),("Avg Winner",bm['win_avg'],om['win_avg']),("Avg Loser",bm['lose_avg'],om['lose_avg']),("Best Pair",bm['best'],om['best']),("Worst Pair",bm['worst'],om['worst'])]:
        print(f"  {lbl:<28} {iv:>14.2f}% {ov:>14.2f}%")
    for lbl,iv,ov in [("Sharpe",bm['sharpe'],om['sharpe']),("BTC Sharpe","--",om['btc_sharpe'])]:
        if isinstance(iv,str): print(f"  {lbl:<28} {iv:>15} {ov:>15.3f}")
        else: print(f"  {lbl:<28} {iv:>15.3f} {ov:>15.3f}")
    print(f"  {'Profitable Months':<28} {bm['pct_profitable_months']:>14.0f}% {om['pct_profitable_months']:>14.0f}%")

    print(f"\n  {'-'*60}")
    for name,ok,val in [
        ("Hit Rate > 58%",om["hit_rate"]>58,f"{om['hit_rate']:.1f}%"),
        ("Avg Alpha > 0%",om["avg_alpha"]>0,f"{om['avg_alpha']:.2f}%"),
        ("Median Alpha > 0%",om["median_alpha"]>0,f"{om['median_alpha']:.2f}%"),
        ("Sharpe > BTC",om["sharpe"]>om["btc_sharpe"],f"{om['sharpe']:.3f} vs {om['btc_sharpe']:.3f}"),
        ("Profitable Months >= 70%",om["pct_profitable_months"]>=70,f"{om['pct_profitable_months']:.0f}%"),
    ]: print(f"  {'PASS' if ok else 'FAIL'}  {name}: {val}")

    # Monthly
    if oos_res:
        print(f"\n  MONTHLY TRACK RECORD (OOS):")
        print(f"  {'Month':<10} {'Pairs':>6} {'Hits':>5} {'HR':>7} {'Avg a':>10} {'St':>4}")
        print(f"  {'-'*44}")
        c=datetime.strptime(OUT_SAMPLE_START,"%Y-%m-%d"); e=datetime.strptime(OUT_SAMPLE_END,"%Y-%m-%d")
        while c<=e:
            ym=c.strftime("%Y-%m")
            mr=[r for r in oos_res if r["entry_date"][:7]==ym]
            if not mr:
                br=btc_mr.get(ym)
                if brg and br is not None and br<-brg: print(f"  {ym:<10} {'--':>6} {'--':>5} {'--':>7} {'--':>10} {'SKIP':>4}")
                c=c.replace(year=c.year+1,month=1,day=1) if c.month==12 else c.replace(month=c.month+1,day=1); continue
            mh=sum(1 for r in mr if r["hit"]); ma=np.mean([r["pair_alpha"] for r in mr])*100
            print(f"  {ym:<10} {len(mr):>6} {mh:>5} {mh/len(mr)*100:>6.0f}% {ma:>9.2f}% {'OK' if ma>0 else 'NEG':>4}")
            c=c.replace(year=c.year+1,month=1,day=1) if c.month==12 else c.replace(month=c.month+1,day=1)

    # Tokens
    if oos_res:
        tf=Counter()
        for r in oos_res: tf[r["long_id"]]+=1; tf[r["short_id"]]+=1
        print(f"\n  TOKEN FREQUENCY (top 15):")
        print(f"  {'Token':<25} {'Count':>7} {'Long':>6} {'Short':>6}")
        print(f"  {'-'*46}")
        for tok,cnt in tf.most_common(15):
            al=sum(1 for r in oos_res if r["long_id"]==tok)
            ash=sum(1 for r in oos_res if r["short_id"]==tok)
            print(f"  {tok:<25} {cnt:>7} {al:>6} {ash:>6}")

    # Top/bottom
    if oos_res:
        sr=sorted(oos_res,key=lambda r:r["pair_alpha"],reverse=True)
        print(f"\n  TOP 10 PAIRS:")
        print(f"  {'Long':<20} {'Short':<20} {'Conv':>6} {'Alpha':>10} {'Entry':>10}")
        print(f"  {'-'*68}")
        for r in sr[:10]: print(f"  {r['long_id']:<20} {r['short_id']:<20} {r.get('conviction',0):>5.2f} {r['pair_alpha']*100:>9.1f}% {r['entry_date']:>10}")
        print(f"\n  BOTTOM 5:")
        for r in sr[-5:]: print(f"  {r['long_id']:<20} {r['short_id']:<20} {r.get('conviction',0):>5.2f} {r['pair_alpha']*100:>9.1f}% {r['entry_date']:>10}")

    # Save
    sd_path=os.path.dirname(os.path.abspath(__file__))
    conn.execute("DROP TABLE IF EXISTS crypto_conviction_results")
    conn.execute("""CREATE TABLE crypto_conviction_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,run_date TEXT,version TEXT,config_label TEXT,
        classes TEXT,spread_w REAL,ndd_w REAL,top_n INTEGER,
        max_per_token INTEGER,regime_threshold REAL,
        is_hit_rate REAL,is_avg_alpha REAL,is_median_alpha REAL,is_sharpe REAL,
        oos_hit_rate REAL,oos_avg_alpha REAL,oos_median_alpha REAL,
        oos_sharpe REAL,oos_btc_sharpe REAL,oos_max_dd REAL,
        oos_total_pairs INTEGER,oos_profitable_months REAL,
        monthly_picks TEXT,all_pairs_json TEXT)""")
    conn.execute("""INSERT INTO crypto_conviction_results
        (run_date,version,config_label,classes,spread_w,ndd_w,top_n,max_per_token,regime_threshold,
         is_hit_rate,is_avg_alpha,is_median_alpha,is_sharpe,
         oos_hit_rate,oos_avg_alpha,oos_median_alpha,oos_sharpe,oos_btc_sharpe,oos_max_dd,
         oos_total_pairs,oos_profitable_months,monthly_picks,all_pairs_json)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (datetime.now().isoformat(),"v3",blabel,json.dumps(bcls),bsw,bnw,btn,bmt,brg or 0,
         bm["hit_rate"],bm["avg_alpha"],bm["median_alpha"],bm["sharpe"],
         om["hit_rate"],om["avg_alpha"],om["median_alpha"],om["sharpe"],om["btc_sharpe"],om["max_dd"],
         om["total_pairs"],om["pct_profitable_months"],json.dumps(oos_picks),
         json.dumps([{"long":r["long_id"],"short":r["short_id"],"class":r.get("class",""),
             "conviction":round(r.get("conviction",0),3),"alpha":round(r["pair_alpha"],6),
             "entry":r["entry_date"],"exit":r["exit_date"]} for r in oos_res])))
    conn.commit()

    md=f"""# NERQ Pair Signals — Track Record v3 (Tradeable Only)
## Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}
### All tokens tradeable on Coinbase, Binance, or Kraken
### Config: {blabel}
- Classes: {', '.join(bcls)}, top_n={btn}, cap={bmt}/token/month
- Regime guard: {'BTC 30d < -'+f'{brg*100:.0f}%' if brg else 'None'}
- Winsorize: +/-{MAX_RETURN_CAP*100:.0f}%

| Metric | In-Sample | Out-of-Sample |
|--------|-----------|---------------|
| Pairs | {bm['total_pairs']} | {om['total_pairs']} |
| Hit Rate | {bm['hit_rate']:.1f}% | {om['hit_rate']:.1f}% |
| Avg Alpha | {bm['avg_alpha']:.2f}% | {om['avg_alpha']:.2f}% |
| Median Alpha | {bm['median_alpha']:.2f}% | {om['median_alpha']:.2f}% |
| Sharpe | {bm['sharpe']:.3f} | {om['sharpe']:.3f} |
| Max Drawdown | {bm['max_dd']:.1f}% | {om['max_dd']:.1f}% |
| Profitable Months | {bm['pct_profitable_months']:.0f}% | {om['pct_profitable_months']:.0f}% |
"""
    with open(os.path.join(sd_path,"CONVICTION_PORTFOLIO_RESULTS.md"),"w") as f: f.write(md)
    print(f"\n  Report: {os.path.join(sd_path,'CONVICTION_PORTFOLIO_RESULTS.md')}")
    print(f"  DB: crypto_conviction_results (v3)")
    conn.close()
    return 0

if __name__=="__main__": sys.exit(main())
