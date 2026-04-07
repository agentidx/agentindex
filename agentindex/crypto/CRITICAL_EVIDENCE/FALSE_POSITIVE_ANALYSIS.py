#!/usr/bin/env python3
"""
ZARQ CRITICAL EVIDENCE — FALSE POSITIVE ANALYSIS
==================================================
Measures precision at all severity thresholds.

VERIFIED RESULTS (2026-02-28):
- 176/207 tokens triggered warning (85%)
- Precision at >30% crash: 99.4% (175/176)
- Precision at >50% crash: 97.7% (172/176)  
- 1 genuine false positive: stasis-eurs (-21.8% DD)
- 29/31 unwarned tokens stayed healthy (<30% DD)

Run: cd ~/agentindex/agentindex/crypto && python3 CRITICAL_EVIDENCE/FALSE_POSITIVE_ANALYSIS.py
"""

import sqlite3,math,os,numpy as np
from datetime import datetime,timedelta
from collections import defaultdict
import warnings;warnings.filterwarnings('ignore')

DB=os.path.expanduser("~/agentindex/agentindex/crypto/crypto_trust.db")

def gidx(pl,date):
    lo,hi=0,len(pl)-1;r=None
    while lo<=hi:
        mid=(lo+hi)//2
        if pl[mid][0]<=date:r=mid;lo=mid+1
        else:hi=mid-1
    return r

print("="*70)
print("FALSE POSITIVE ANALYSIS")
print("How many tokens did we warn about that DIDN'T crash?")
print("="*70)

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
conn.close()

OOS_S="2024-01-01"
tl=sorted(set(ndd.keys())&set(rat.keys()))

token_max_dd={}
token_warned={}
token_outcome={}

for tid in tl:
    tp=prices.get(tid)
    if not tp:continue
    ns=ndd.get(tid,[]);rs=rat.get(tid,[])
    oos_p=[(d,p) for d,p in tp if d>=OOS_S]
    if len(oos_p)<30:continue
    peak=0;max_dd=0
    for d,p in oos_p:
        if p>peak:peak=p
        dd=(p-peak)/peak if peak>0 else 0
        if dd<max_dd:max_dd=dd
    token_max_dd[tid]=max_dd
    start_p=oos_p[0][1]
    end_p=oos_p[-1][1]
    total_ret=(end_p-start_p)/start_p if start_p>0 else 0
    first_warn=None
    for oi,(wd,nv,s3,s5,s6) in enumerate(ns):
        if wd<OOS_S:continue
        tym=wd[:7];ri=None
        for j,(ym,sc,p1,p2,p3,p4,p5) in enumerate(rs):
            if ym<=tym:ri=j
            else:break
        if ri is None:continue
        p3_now=rs[ri][4]
        nm4=min(ns[j2][1] for j2 in range(max(0,oi-3),oi+1))
        p3_3m=p3_now
        ym_3m=(datetime.strptime(tym+"-01","%Y-%m-%d")-timedelta(days=95)).strftime("%Y-%m")
        for ym2,_,_,_,p32,_,_ in rs:
            if ym2<=ym_3m:p3_3m=p32
        decay=p3_now-p3_3m
        sw=sum([1.0 if p3_now<40 else 0,1.0 if s6<2.5 else 0,
                1.0 if nm4<3.0 else 0,1.0 if decay<-15 else 0])
        if sw>=2 and first_warn is None:
            first_warn=wd
            break
    was_warned=first_warn is not None
    token_warned[tid]=first_warn
    token_outcome[tid]={'max_dd':max_dd,'total_ret':total_ret,'warned':was_warned,
                        'first_warn':first_warn,'start':start_p,'end':end_p,
                        'start_date':oos_p[0][0],'end_date':oos_p[-1][0]}

print(f"\n  Total tokens with OOS data: {len(token_outcome)}")
warned=[tid for tid,o in token_outcome.items() if o['warned']]
not_warned=[tid for tid,o in token_outcome.items() if not o['warned']]
print(f"  Warned (structural filter triggered): {len(warned)}")
print(f"  Not warned: {len(not_warned)}")

print(f"\n{'='*70}")
print(f"  CONFUSION MATRIX BY SEVERITY THRESHOLD")
print(f"{'='*70}")
print(f"  {'Threshold':>15} {'TP':>5} {'FP':>5} {'FN':>5} {'TN':>5} {'Prec':>7} {'Recall':>7} {'FP Rate':>8}")
print(f"  {'-'*60}")

for threshold in [0.30,0.40,0.50,0.60,0.70,0.80,0.90]:
    tp=sum(1 for tid in warned if token_outcome[tid]['max_dd']<=-threshold)
    fp=sum(1 for tid in warned if token_outcome[tid]['max_dd']>-threshold)
    fn=sum(1 for tid in not_warned if token_outcome[tid]['max_dd']<=-threshold)
    tn=sum(1 for tid in not_warned if token_outcome[tid]['max_dd']>-threshold)
    prec=tp/(tp+fp) if tp+fp>0 else 0
    recall=tp/(tp+fn) if tp+fn>0 else 0
    fpr=fp/(fp+tn) if fp+tn>0 else 0
    print(f"  DD>{threshold:.0%}:  {tp:>5} {fp:>5} {fn:>5} {tn:>5} {prec:>6.1%} {recall:>6.1%} {fpr:>7.1%}")

print(f"\n{'='*70}")
print(f"HONEST SUMMARY")
print(f"{'='*70}")
total=len(token_outcome)
w=len(warned);nw=len(not_warned)
warned_dds=[token_outcome[tid]['max_dd'] for tid in warned]
nw_dds=[token_outcome[tid]['max_dd'] for tid in not_warned]
print(f"\n  Of {total} tokens tracked in OOS (2024-2026):")
print(f"  Warned: {w} ({100*w/total:.0f}%)")
print(f"  Not warned: {nw} ({100*nw/total:.0f}%)")
tp80=sum(1 for d in warned_dds if d<=-0.80)
fp80=sum(1 for d in warned_dds if d>-0.80)
print(f"\n  PRECISION AT DIFFERENT THRESHOLDS:")
print(f"    'Warning means >80% crash':  {100*tp80/w:.0f}% precision")
print(f"    'Warning means >50% crash':  {100*sum(1 for d in warned_dds if d<=-0.50)/w:.0f}% precision")
print(f"    'Warning means >30% crash':  {100*sum(1 for d in warned_dds if d<=-0.30)/w:.0f}% precision")
fa_mild=sum(1 for d in warned_dds if d>-0.30)
print(f"    Genuine false positives (<30% DD): {fa_mild}/{w}")

print("\n" + "="*70 + "\nDONE\n" + "="*70)
