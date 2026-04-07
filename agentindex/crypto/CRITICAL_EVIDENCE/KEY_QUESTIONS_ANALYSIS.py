#!/usr/bin/env python3
"""
ZARQ CRITICAL EVIDENCE — KEY QUESTIONS ANALYSIS
=================================================
This script answers the three key questions:
Q1: How many tokens that "die" do we warn about? → 113/113 (100%)
Q2: When do we warn and what's the value? → Median -31% DD, 58% avoided
Q3: How many idiosyncratic deaths do we catch? → 98/98 (100%)

OOS Period: Jan 2024 — Feb 2026
Universe: 207 tokens with NDD + Rating history

Run: cd ~/agentindex/agentindex/crypto && python3 CRITICAL_EVIDENCE/KEY_QUESTIONS_ANALYSIS.py
Output saved to: CRITICAL_EVIDENCE/KEY_QUESTIONS_OUTPUT.txt

VERIFIED RESULTS (2026-02-28):
- 113/113 deaths (>80% DD) detected
- 172/174 tokens >50% DD warned (99%)
- 143/143 tokens >70% DD warned (100%)
- 8 tokens warned at 0% drawdown (before any drop)
- Median 58% additional loss avoided after warning
- 87% of deaths idiosyncratic, 100% of those warned
"""

import sqlite3,math,os,numpy as np
from datetime import datetime,timedelta
from collections import defaultdict
import xgboost as xgb
from sklearn.metrics import roc_auc_score
import warnings;warnings.filterwarnings('ignore')

DB=os.path.expanduser("~/agentindex/agentindex/crypto/crypto_trust.db")
DB_REF=os.path.expanduser("~/agentindex/agentindex/data/crypto_trust.db")
CAT_RISK={'Algo-Stables':1.0,'Yield Aggregator':0.85,'Derivatives':0.8,'Yield':0.8,
    'Leveraged Farming':0.9,'Options':0.75,'Synthetics':0.8,'Bridge':0.7,'Cross Chain':0.7,
    'DEX':0.5,'Lending':0.45,'Liquid Staking':0.4,'CDP':0.5,'NFT Lending':0.7,'RWA':0.35,
    'CEX':0.2,'Chain':0.3,'Payments':0.3,'Privacy':0.6,'Launchpad':0.65,'Gaming':0.7,
    'Prediction Market':0.65,'Insurance':0.35,'Indexes':0.4,'Staking Pool':0.35}
def cvol(pl,idx,w=30):
    if idx<w:return None
    rets=[(pl[i][1]-pl[i-1][1])/pl[i-1][1] for i in range(idx-w+1,idx+1) if i>0 and pl[i-1][1]>0]
    if len(rets)<20:return None
    mu=sum(rets)/len(rets);return math.sqrt(sum((r-mu)**2 for r in rets)/len(rets))*math.sqrt(365)
def gidx(pl,date):
    lo,hi=0,len(pl)-1;r=None
    while lo<=hi:
        mid=(lo+hi)//2
        if pl[mid][0]<=date:r=mid;lo=mid+1
        else:hi=mid-1
    return r
def wilson(s,t):
    if t==0:return 0,0,0
    z=1.96;p=s/t;d=1+z*z/t;c=(p+z*z/(2*t))/d;m=z*math.sqrt((p*(1-p)+z*z/(4*t))/t)/d
    return p,max(0,c-m),min(1,c+m)
def compute_beta(tp,btc,date,lookback=90):
    ti=gidx(tp,date);bi=gidx(btc,date)
    if ti is None or bi is None or ti<lookback or bi<lookback:return None
    tok_r=[];btc_r=[]
    for i in range(ti-lookback+1,ti+1):
        if i<=0:continue
        bj=gidx(btc,tp[i][0])
        if bj is None or bj<=0:continue
        tr=(tp[i][1]-tp[i-1][1])/tp[i-1][1] if tp[i-1][1]>0 else 0
        br=(btc[bj][1]-btc[bj-1][1])/btc[bj-1][1] if btc[bj-1][1]>0 else 0
        tok_r.append(tr);btc_r.append(br)
    if len(tok_r)<30:return None
    bx=np.array(btc_r);by=np.array(tok_r)
    vb=np.var(bx)
    if vb<1e-10:return 1.0
    return max(-5,min(10,np.cov(bx,by)[0,1]/vb))

print("="*70)
print("NERQ — ANSWERING THE KEY QUESTIONS")
print("="*70)

# LOAD
conn=sqlite3.connect(DB)
prices=defaultdict(list)
for tid,d,c in conn.execute("SELECT token_id,date,close FROM crypto_price_history WHERE close>0 ORDER BY token_id,date").fetchall():
    prices[tid].append((d,c))
prices=dict(prices)
ndd=defaultdict(list)
for tid,wd,n,s3,s5,s6 in conn.execute("SELECT token_id,week_date,ndd,signal_3,signal_5,signal_6 FROM crypto_ndd_history WHERE ndd IS NOT NULL ORDER BY token_id,week_date").fetchall():
    ndd[tid].append((wd,n,s3 or 0,s5 or 0,s6 or 0))
ndd=dict(ndd)
rat=defaultdict(list)
for tid,ym,sc,p1,p2,p3,p4,p5 in conn.execute("SELECT token_id,year_month,score,pillar_1,pillar_2,pillar_3,pillar_4,pillar_5 FROM crypto_rating_history WHERE score IS NOT NULL ORDER BY token_id,year_month").fetchall():
    rat[tid].append((ym,sc or 0,p1 or 0,p2 or 0,p3 or 0,p4 or 0,p5 or 0))
rat=dict(rat)
stru={}
for tid,au,fk,cat,la in conn.execute("SELECT token_id,audit_count,forked_from,category,listed_at FROM defi_protocol_tokens WHERE token_id IS NOT NULL").fetchall():
    cr=CAT_RISK.get(cat or '',0.5)
    f={'au':1.0 if(au or 0)>0 else 0.0,'fk':1.0 if(fk or'').strip()else 0.0,'cr':float(cr)}
    if tid not in stru or f['au']>stru[tid]['au']:stru[tid]=f
sbc=defaultdict(dict)
for ch,d,c in conn.execute("SELECT chain,date,total_circulating FROM defi_stablecoin_flows ORDER BY chain,date").fetchall():sbc[ch.lower()][d]=c
stable_chg={}
for ch,dv in sbc.items():
    for ds in sorted(dv.keys()):
        vn=dv[ds]
        for off in range(7):
            ck=(datetime.strptime(ds,"%Y-%m-%d")-timedelta(days=30-off)).strftime("%Y-%m-%d")
            if ck in dv and dv[ck]>0:stable_chg[(ch,ds)]=(vn-dv[ck])/dv[ck];break
tc={}
try:
    cr2=sqlite3.connect(DB_REF)
    for tid,ch in cr2.execute("SELECT token_id,chain FROM crypto_token_ecosystem_v2 WHERE chain IS NOT NULL").fetchall():tc[tid]=ch.lower()
    cr2.close()
except:pass
conn.close()

btc=prices.get('bitcoin')
all_vols=defaultdict(dict)
for tid in ndd:
    tp=prices.get(tid)
    if not tp:continue
    for wd,_,_,_,_ in ndd[tid]:
        idx=gidx(tp,wd)
        if idx and idx>=30:
            v=cvol(tp,idx,30)
            if v is not None:all_vols[wd][tid]=v
tl=sorted(set(ndd.keys())&set(rat.keys()))
p3_by_month=defaultdict(dict)
for tid in rat:
    for ym,sc,p1,p2,p3,p4,p5 in rat[tid]:p3_by_month[ym][tid]=p3

print("[BETA]...")
token_betas={}
for tid in tl:
    tp=prices.get(tid)
    if not tp:continue
    betas={}
    for wd,_,_,_,_ in ndd[tid]:
        b=compute_beta(tp,btc,wd)
        if b is not None:betas[wd]=b
    if betas:token_betas[tid]=betas

OOS_S="2024-01-01"
token_max_dd={}
token_death={}
for tid in tl:
    tp=prices.get(tid)
    if not tp:continue
    oos_prices=[(d,p) for d,p in tp if d>=OOS_S]
    if len(oos_prices)<30:continue
    peak=0;peak_d=None;max_dd=0;trough_d=None;trough_p=None
    for d,p in oos_prices:
        if p>peak:peak=p;peak_d=d
        dd=(p-peak)/peak if peak>0 else 0
        if dd<max_dd:max_dd=dd;trough_d=d;trough_p=p
    token_max_dd[tid]=max_dd
    if max_dd<=-0.80:
        token_death[tid]={'peak_d':peak_d,'peak':peak,'trough_d':trough_d,'trough':trough_p,'dd':max_dd}

print(f"\n  Tokens in OOS with enough data: {len(token_max_dd)}")
print(f"  Tokens that 'died' (>80% from peak): {len(token_death)}")
print(f"  Tokens >70% from peak: {sum(1 for v in token_max_dd.values() if v<=-0.70)}")
print(f"  Tokens >60% from peak: {sum(1 for v in token_max_dd.values() if v<=-0.60)}")
print(f"  Tokens >50% from peak: {sum(1 for v in token_max_dd.values() if v<=-0.50)}")

print(f"\n  DEAD TOKENS (>80% drawdown):")
print(f"  {'Token':>25} {'Peak':>12} {'Trough':>12} {'MaxDD':>7} {'Struct':>6} {'P3min':>6} {'Warned?':>8}")

warned_tokens=set()
not_warned=set()
for tid in sorted(token_death.keys()):
    info=token_death[tid]
    ns=ndd.get(tid,[])
    rs=rat.get(tid,[])
    was_warned=False
    first_warn_date=None
    first_warn_dd=None
    min_p3=100
    for oi,(wd,nv,s3,s5,s6) in enumerate(ns):
        if wd<OOS_S or wd>info['trough_d']:continue
        tym=wd[:7];ri2=None
        for j,(ym,sc,p1,p2,p3,p4,p5) in enumerate(rs):
            if ym<=tym:ri2=j
            else:break
        if ri2 is None:continue
        p3_now=rs[ri2][4]
        if p3_now<min_p3:min_p3=p3_now
        nm4=min(ns[j2][1] for j2 in range(max(0,oi-3),oi+1))
        p3_3m=p3_now
        ym_3m=(datetime.strptime(tym+"-01","%Y-%m-%d")-timedelta(days=95)).strftime("%Y-%m")
        for ym2,_,_,_,p32,_,_ in rs:
            if ym2<=ym_3m:p3_3m=p32
        decay=p3_now-p3_3m
        sw=sum([1.0 if p3_now<40 else 0,1.0 if s6<2.5 else 0,
                1.0 if nm4<3.0 else 0,1.0 if decay<-15 else 0])
        if sw>=2 and not was_warned:
            was_warned=True
            first_warn_date=wd
            tp2=prices.get(tid)
            if tp2:
                idx=gidx(tp2,wd)
                if idx:
                    peak_so_far=max(p for d,p in tp2 if d>=OOS_S and d<=wd)
                    first_warn_dd=(tp2[idx][1]-peak_so_far)/peak_so_far if peak_so_far>0 else 0
    status="YES" if was_warned else "NO"
    if was_warned:warned_tokens.add(tid)
    else:not_warned.add(tid)
    warn_info=""
    if first_warn_date:
        warn_info=f" @{first_warn_date} ({first_warn_dd*100:+.0f}%)"
    print(f"  {tid:>25} {info['peak_d']:>12} {info['trough_d']:>12} {info['dd']*100:>+6.1f}% {status:>6} {min_p3:>5.1f} {warn_info}")

print(f"\n  SUMMARY:")
print(f"    Dead tokens (>80% DD): {len(token_death)}")
print(f"    Warned by structural filter: {len(warned_tokens)} ({100*len(warned_tokens)/len(token_death):.0f}%)")
print(f"    NOT warned: {len(not_warned)} ({100*len(not_warned)/len(token_death):.0f}%)")
if not_warned:
    print(f"    Unwarned tokens: {', '.join(sorted(not_warned))}")

print(f"\n  COVERAGE BY SEVERITY:")
for threshold in [0.50,0.60,0.70,0.80,0.90]:
    dead_at={tid for tid,dd in token_max_dd.items() if dd<=-threshold}
    sw_any=set()
    for tid in dead_at:
        ns2=ndd.get(tid,[]);rs2=rat.get(tid,[])
        for oi,(wd,nv,s3,s5,s6) in enumerate(ns2):
            if wd<OOS_S:continue
            tym=wd[:7];ri2=None
            for j,(ym,sc,p1,p2,p3,p4,p5) in enumerate(rs2):
                if ym<=tym:ri2=j
                else:break
            if ri2 is None:continue
            p3_now=rs2[ri2][4]
            nm4=min(ns2[j2][1] for j2 in range(max(0,oi-3),oi+1))
            p3_3m=p3_now
            ym_3m=(datetime.strptime(tym+"-01","%Y-%m-%d")-timedelta(days=95)).strftime("%Y-%m")
            for ym2,_,_,_,p32,_,_ in rs2:
                if ym2<=ym_3m:p3_3m=p32
            decay=p3_now-p3_3m
            sw=sum([1.0 if p3_now<40 else 0,1.0 if s6<2.5 else 0,
                    1.0 if nm4<3.0 else 0,1.0 if decay<-15 else 0])
            if sw>=2:sw_any.add(tid);break
    print(f"    DD >{threshold:.0%}: {len(dead_at)} tokens, warned={len(sw_any)} ({100*len(sw_any)/max(len(dead_at),1):.0f}%)")

# Q2: TIMING
print("\n\n" + "="*70)
print("Q2: TIMING — When do we warn and what's the value?")
print("="*70)
timing_data=[]
for tid in warned_tokens:
    info=token_death[tid]
    ns=ndd.get(tid,[]);rs=rat.get(tid,[])
    tp2=prices.get(tid)
    if not tp2:continue
    for oi,(wd,nv,s3,s5,s6) in enumerate(ns):
        if wd<OOS_S or wd>info['trough_d']:continue
        tym=wd[:7];ri2=None
        for j,(ym,sc,p1,p2,p3,p4,p5) in enumerate(rs):
            if ym<=tym:ri2=j
            else:break
        if ri2 is None:continue
        p3_now=rs[ri2][4]
        nm4=min(ns[j2][1] for j2 in range(max(0,oi-3),oi+1))
        p3_3m=p3_now
        ym_3m=(datetime.strptime(tym+"-01","%Y-%m-%d")-timedelta(days=95)).strftime("%Y-%m")
        for ym2,_,_,_,p32,_,_ in rs:
            if ym2<=ym_3m:p3_3m=p32
        decay=p3_now-p3_3m
        sw=sum([1.0 if p3_now<40 else 0,1.0 if s6<2.5 else 0,
                1.0 if nm4<3.0 else 0,1.0 if decay<-15 else 0])
        if sw>=2:
            idx=gidx(tp2,wd)
            if idx:
                peak_so_far=max(p for d,p in tp2 if d>=OOS_S and d<=wd)
                dd_at_warn=(tp2[idx][1]-peak_so_far)/peak_so_far if peak_so_far>0 else 0
                total_dd=info['dd']
                loss_avoided=total_dd-dd_at_warn
                timing_data.append({'tid':tid,'warn_date':wd,'dd_at_warn':dd_at_warn,
                    'total_dd':total_dd,'loss_avoided':loss_avoided,'p3':p3_now,'ndd':nv})
                break

if timing_data:
    dd_warns=[t['dd_at_warn'] for t in timing_data]
    losses=[t['loss_avoided'] for t in timing_data]
    print(f"\n  Warned dead tokens with timing: {len(timing_data)}")
    print(f"\n  DRAWDOWN AT FIRST WARNING:")
    print(f"    Median: {np.median(dd_warns)*100:+.1f}%")
    print(f"    Mean:   {np.mean(dd_warns)*100:+.1f}%")
    print(f"    Warned at 0% (before ANY drop): {sum(1 for d in dd_warns if d>=0)}/{len(dd_warns)}")
    print(f"    Warned at <10% down:            {sum(1 for d in dd_warns if d>-0.10)}/{len(dd_warns)}")
    print(f"    Warned at <20% down:            {sum(1 for d in dd_warns if d>-0.20)}/{len(dd_warns)}")
    print(f"    Warned at <30% down:            {sum(1 for d in dd_warns if d>-0.30)}/{len(dd_warns)}")
    print(f"    Warned at <50% down:            {sum(1 for d in dd_warns if d>-0.50)}/{len(dd_warns)}")
    print(f"\n  ADDITIONAL LOSS AFTER WARNING (what you avoid by selling):")
    print(f"    Median: {np.median(losses)*100:+.1f}%")
    print(f"    Mean:   {np.mean(losses)*100:+.1f}%")

# Q3: IDIOSYNCRATIC
print("\n\n" + "="*70)
print("Q3: IDIOSYNCRATIC DEATHS")
print("="*70)
idio_deaths=0;beta_deaths=0
for tid in sorted(token_death.keys()):
    info=token_death[tid]
    beta=token_betas.get(tid,{})
    peak_d=info['peak_d']
    closest_beta=1.0
    for wd,b in beta.items():
        if wd<=peak_d:closest_beta=b
    bi_peak=gidx(btc,info['peak_d'])
    bi_trough=gidx(btc,info['trough_d'])
    if bi_peak and bi_trough and btc[bi_peak][1]>0:
        btc_ret=(btc[bi_trough][1]-btc[bi_peak][1])/btc[bi_peak][1]
    else:btc_ret=0
    expected=closest_beta*min(0,btc_ret)
    actual=info['dd']
    idio=actual-expected
    if abs(idio)>abs(expected):idio_deaths+=1
    else:beta_deaths+=1

print(f"\n  Idiosyncratic deaths: {idio_deaths}/{len(token_death)} ({100*idio_deaths/len(token_death):.0f}%)")
print(f"  Beta-driven deaths:   {beta_deaths}/{len(token_death)} ({100*beta_deaths/len(token_death):.0f}%)")

idio_warned=0
for tid in sorted(token_death.keys()):
    info=token_death[tid]
    beta_vals=token_betas.get(tid,{})
    peak_d=info['peak_d']
    closest_beta=1.0
    for wd,b in beta_vals.items():
        if wd<=peak_d:closest_beta=b
    bi_peak=gidx(btc,info['peak_d'])
    bi_trough=gidx(btc,info['trough_d'])
    btc_ret=(btc[bi_trough][1]-btc[bi_peak][1])/btc[bi_peak][1] if bi_peak and bi_trough and btc[bi_peak][1]>0 else 0
    expected=closest_beta*min(0,btc_ret)
    idio=info['dd']-expected
    if abs(idio)>abs(expected) and tid in warned_tokens:
        idio_warned+=1

print(f"  Of idiosyncratic deaths, warned: {idio_warned}/{idio_deaths} ({100*idio_warned/max(idio_deaths,1):.0f}%)")
print("\n" + "="*70 + "\nDONE\n" + "="*70)
