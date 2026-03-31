#!/usr/bin/env python3
"""
NERQ Crash Model v3 — Extends v2 with DeFiLlama features
Uses SAME data sources as v2: crypto_ndd_history (weekly), crypto_rating_history (monthly)
Only 198-207 tokens that have ALL three: prices + ndd_history + rating_history
"""
import sqlite3, json, math, os
from datetime import datetime, timedelta
from collections import defaultdict

DB = os.path.expanduser("~/agentindex/agentindex/crypto/crypto_trust.db")
DB_REF = os.path.expanduser("~/agentindex/agentindex/data/crypto_trust.db")
IS_CUTOFF = "2023-12-31"
OOS_START = "2024-01-01"
CRASH_THRESH = -0.30
CRASH_DAYS = 90

V2_FEAT = ['vol_30d','trust_p3_maintenance','sig6_str','ndd_min_4w','sig5_cont','sig3_res',
    'drawdown_90d','btc_vol_30d','ix_vol_x_ndd_weak','ix_drawdown_x_cont',
    'ix_btcvol_x_ndd_weak','ix_vol_x_maint_low','nl_ndd_below_2','nl_drawdown_severe',
    'nl_vol_extreme','nl_trust_p3_low']

V3_NEW = ['tvl_momentum_7d','tvl_momentum_30d','tvl_drawdown','tvl_vs_price_divergence',
    'has_tvl_data','has_audit','is_fork','category_risk','protocol_age_days',
    'chain_stablecoin_change_30d','yield_anomaly',
    'ix_tvl_div_x_trust','ix_no_audit_x_drawdown']

ALL_FEAT = V2_FEAT + V3_NEW

CAT_RISK = {"Algo-Stables":1.0,"Yield Aggregator":0.85,"Derivatives":0.8,"Yield":0.8,
    "Leveraged Farming":0.9,"Options":0.75,"Synthetics":0.8,"Bridge":0.7,"Cross Chain":0.7,
    "DEX":0.5,"Lending":0.45,"Liquid Staking":0.4,"CDP":0.5,"NFT Lending":0.7,"RWA":0.35,
    "CEX":0.2,"Chain":0.3,"Payments":0.3,"Privacy":0.6,"Launchpad":0.65,"Gaming":0.7,
    "Prediction Market":0.65,"Insurance":0.35,"Indexes":0.4,"Staking Pool":0.35}
SEV = {"mild":(-0.50,-0.30),"severe":(-0.70,-0.50),"catastrophic":(-0.90,-0.70),"terminal":(-1.00,-0.90)}

def wilson(s,t,z=1.96):
    if t==0: return 0,0,0
    p=s/t; d=1+z*z/t; c=(p+z*z/(2*t))/d; m=z*math.sqrt((p*(1-p)+z*z/(4*t))/t)/d
    return p,max(0,c-m),min(1,c+m)

def sig(x):
    x=max(-500,min(500,x))
    return 1/(1+math.exp(-x))

def auc_calc(lab,sc):
    pairs=sorted(zip(sc,lab),key=lambda x:x[0])
    cn=0; conc=0
    for s,l in pairs:
        if l==0: cn+=1
        else: conc+=cn
    np_=sum(lab); nn=len(lab)-np_
    if np_==0 or nn==0: return 0.5
    return 1.0-(conc/(np_*nn))  # Same as v2: 1-concordant/total

def compute_vol(pl,idx,w=30):
    if idx<w: return None
    rets=[]
    for i in range(idx-w+1,idx+1):
        if i>0 and pl[i-1][1]>0:
            rets.append((pl[i][1]-pl[i-1][1])/pl[i-1][1])
    if len(rets)<20: return None
    mu=sum(rets)/len(rets)
    var=sum((r-mu)**2 for r in rets)/len(rets)
    return math.sqrt(var)*math.sqrt(365)  # Annualized

def get_idx(pl,date):
    lo,hi=0,len(pl)-1; r=None
    while lo<=hi:
        mid=(lo+hi)//2
        if pl[mid][0]<=date: r=mid; lo=mid+1
        else: hi=mid-1
    return r

# ── LOAD DATA ──
def load_data():
    conn=sqlite3.connect(DB)
    print("[LOAD] prices...")
    rows=conn.execute("SELECT token_id,date,close,volume FROM crypto_price_history WHERE close>0 ORDER BY token_id,date").fetchall()
    prices=defaultdict(list)
    for tid,d,c,v in rows: prices[tid].append((d,c,v or 0))
    prices=dict(prices)
    print(f"  {len(prices)} tokens, {len(rows)} rows")

    print("[LOAD] ndd_history (weekly)...")
    rows=conn.execute("SELECT token_id,week_date,ndd,signal_3,signal_5,signal_6 FROM crypto_ndd_history WHERE ndd IS NOT NULL ORDER BY token_id,week_date").fetchall()
    ndd=defaultdict(list)
    for tid,wd,n,s3,s5,s6 in rows: ndd[tid].append((wd,n,s3 or 0,s5 or 0,s6 or 0))
    ndd=dict(ndd)
    print(f"  {len(ndd)} tokens, {len(rows)} rows")

    print("[LOAD] rating_history (monthly)...")
    rows=conn.execute("SELECT token_id,year_month,score,pillar_3 FROM crypto_rating_history WHERE score IS NOT NULL ORDER BY token_id,year_month").fetchall()
    ratings=defaultdict(list)
    for tid,ym,sc,p3 in rows: ratings[tid].append((ym,p3 or 0))
    ratings=dict(ratings)
    print(f"  {len(ratings)} tokens, {len(rows)} rows")

    # DeFiLlama data
    print("[LOAD] TVL...")
    tp_map=defaultdict(list)
    rows=conn.execute("SELECT DISTINCT token_id,protocol_id FROM defi_protocol_tokens WHERE token_id IS NOT NULL AND token_id!=''").fetchall()
    for tid,pid in rows: tp_map[tid].append(pid)
    tvl_proto=defaultdict(dict)
    rows=conn.execute("SELECT protocol_id,date,tvl_usd FROM defi_tvl_history ORDER BY protocol_id,date").fetchall()
    for pid,d,tv in rows: tvl_proto[pid][d]=tv
    # Aggregate TVL per token
    tvl_tok={}
    for tid,pids in tp_map.items():
        agg={}
        for pid in pids:
            for d,tv in tvl_proto.get(pid,{}).items(): agg[d]=agg.get(d,0)+tv
        if agg: tvl_tok[tid]=agg
    print(f"  {len(tvl_tok)} tokens with TVL")

    print("[LOAD] structural...")
    struct={}
    rows=conn.execute("SELECT token_id,audit_count,forked_from,category,listed_at FROM defi_protocol_tokens WHERE token_id IS NOT NULL AND token_id!=''").fetchall()
    for tid,au,fk,cat,la in rows:
        f={"audit":1.0 if (au or 0)>0 else 0.0,"fork":1.0 if (fk or"").strip() else 0.0,
           "cat_risk":CAT_RISK.get(cat or"",0.5),"listed_at":la}
        if tid not in struct or f["audit"]>struct[tid]["audit"]: struct[tid]=f
    print(f"  {len(struct)} tokens")

    print("[LOAD] stablecoin flows...")
    sbc=defaultdict(dict)
    rows=conn.execute("SELECT chain,date,total_circulating FROM defi_stablecoin_flows ORDER BY chain,date").fetchall()
    for ch,d,c in rows: sbc[ch.lower()][d]=c
    print(f"  {len(sbc)} chains")

    # Token→chain
    tok_chain={}
    try:
        conn_r=sqlite3.connect(DB_REF)
        rows=conn_r.execute("SELECT token_id,chain FROM crypto_token_ecosystem_v2 WHERE chain IS NOT NULL").fetchall()
        for tid,ch in rows: tok_chain[tid]=ch.lower()
        conn_r.close()
        print(f"  {len(tok_chain)} token→chain mappings")
    except: print("  [WARN] no chain mapping")

    print("[LOAD] yields...")
    yld={}
    try:
        rows=conn.execute("""SELECT dpt.token_id,MAX(dy.apy) FROM defi_yields dy
            JOIN defi_protocol_tokens dpt ON LOWER(dy.project)=LOWER(dpt.protocol_id)
            WHERE dy.apy>0 GROUP BY dpt.token_id""").fetchall()
        for tid,a in rows:
            if tid: yld[tid]=min(a,10000)
    except: pass
    if len(yld)<10:
        try:
            rows=conn.execute("SELECT project,MAX(apy) FROM defi_yields WHERE apy>0 GROUP BY project").fetchall()
            pa={r[0].lower():r[1] for r in rows}
            rows=conn.execute("SELECT token_id,protocol_id FROM defi_protocol_tokens WHERE token_id IS NOT NULL").fetchall()
            for tid,pid in rows:
                if pid and pid.lower() in pa and tid not in yld: yld[tid]=min(pa[pid.lower()],10000)
        except: pass
    print(f"  {len(yld)} tokens with yield")

    conn.close()
    return prices,ndd,ratings,tvl_tok,struct,sbc,tok_chain,yld

# ── BUILD DATASET ──
def build_dataset(prices,ndd,ratings,tvl_tok,struct,sbc,tok_chain,yld):
    # Pre-compute IS vol 90th percentile (same as v2)
    print("\n[BUILD] Computing IS vol threshold...")
    is_vols=[]
    for tid in ndd:
        tp=prices.get(tid)
        if not tp: continue
        for wd,_,_,_,_ in ndd[tid]:
            if wd>IS_CUTOFF: continue
            idx=get_idx(tp,wd)
            if idx and idx>=30:
                v=compute_vol(tp,idx,30)
                if v is not None: is_vols.append(v)
    is_vols.sort()
    vol_90=is_vols[int(len(is_vols)*0.90)] if is_vols else 2.0
    print(f"  vol_90th={vol_90:.3f}")

    # Precompute stablecoin 30d changes
    stable_chg={}
    for ch,dv in sbc.items():
        sd=sorted(dv.keys())
        for ds in sd:
            vn=dv[ds]
            for off in range(7):
                ck=(datetime.strptime(ds,"%Y-%m-%d")-timedelta(days=30-off)).strftime("%Y-%m-%d")
                if ck in dv:
                    v30=dv[ck]
                    if v30>0: stable_chg[(ch,ds)]=(vn-v30)/v30
                    break

    btc=prices.get('bitcoin')
    if not btc: print("[FATAL] No bitcoin prices!"); return [],[]

    print("[BUILD] Feature matrix...")
    rows_is=[]; rows_oos=[]; skip=0
    token_list=sorted(set(ndd.keys())&set(ratings.keys()))
    print(f"  {len(token_list)} tokens with both NDD+Rating")

    for ti,tid in enumerate(token_list):
        tp=prices.get(tid)
        if not tp: skip+=1; continue
        ndd_series=ndd[tid]
        rat_series=ratings[tid]

        for obs_i,(wd,ndd_val,s3,s5,s6) in enumerate(ndd_series):
            # V2 features
            idx=get_idx(tp,wd)
            if idx is None or idx<90: skip+=1; continue
            close=tp[idx][1]
            if close<=0: skip+=1; continue

            vol=compute_vol(tp,idx,30)
            if vol is None: skip+=1; continue

            high90=max(tp[i][1] for i in range(idx-89,idx+1))
            dd90=(close-high90)/high90 if high90>0 else 0

            btc_idx=get_idx(btc,wd)
            btc_vol=compute_vol(btc,btc_idx,30) if btc_idx else None
            if btc_vol is None: skip+=1; continue

            # ndd_min_4w
            if obs_i>=4:
                ndd_min4=min(ndd_series[j][1] for j in range(obs_i-3,obs_i+1))
            else:
                ndd_min4=ndd_val

            # trust p3
            tgt_ym=wd[:7]; r_idx=None
            for ri,(ym,p3) in enumerate(rat_series):
                if ym<=tgt_ym: r_idx=ri
                else: break
            if r_idx is None: skip+=1; continue
            p3=rat_series[r_idx][1]

            # V2 interactions
            ndd_weak=max(0,3.5-ndd_min4)
            maint_weak=max(0,50-p3)/50

            ft={}
            ft['vol_30d']=vol
            ft['trust_p3_maintenance']=p3
            ft['sig6_str']=s6
            ft['ndd_min_4w']=ndd_min4
            ft['sig5_cont']=s5
            ft['sig3_res']=s3
            ft['drawdown_90d']=dd90
            ft['btc_vol_30d']=btc_vol
            ft['ix_vol_x_ndd_weak']=vol*ndd_weak
            ft['ix_drawdown_x_cont']=abs(dd90)*max(0,3.0-s5)
            ft['ix_btcvol_x_ndd_weak']=btc_vol*ndd_weak
            ft['ix_vol_x_maint_low']=vol*maint_weak
            ft['nl_ndd_below_2']=1.0 if ndd_min4<2.0 else 0.0
            ft['nl_drawdown_severe']=1.0 if dd90<-0.40 else 0.0
            ft['nl_vol_extreme']=1.0 if vol>vol_90 else 0.0
            ft['nl_trust_p3_low']=1.0 if p3<40 else 0.0

            # ── V3 NEW: TVL features ──
            tvl_d=tvl_tok.get(tid)
            if tvl_d:
                ft['has_tvl_data']=1.0
                tn=None
                for o in range(4):
                    ck=(datetime.strptime(wd,"%Y-%m-%d")-timedelta(days=o)).strftime("%Y-%m-%d")
                    if ck in tvl_d: tn=tvl_d[ck]; break
                if tn and tn>0:
                    t7=None
                    for o in range(4):
                        ck=(datetime.strptime(wd,"%Y-%m-%d")-timedelta(days=7+o)).strftime("%Y-%m-%d")
                        if ck in tvl_d: t7=tvl_d[ck]; break
                    t30=None
                    for o in range(4):
                        ck=(datetime.strptime(wd,"%Y-%m-%d")-timedelta(days=30+o)).strftime("%Y-%m-%d")
                        if ck in tvl_d: t30=tvl_d[ck]; break
                    t90h=0
                    for i in range(91):
                        ck=(datetime.strptime(wd,"%Y-%m-%d")-timedelta(days=i)).strftime("%Y-%m-%d")
                        if ck in tvl_d and tvl_d[ck]>t90h: t90h=tvl_d[ck]

                    ft['tvl_momentum_7d']=(tn-t7)/t7 if t7 and t7>0 else 0.0
                    ft['tvl_momentum_30d']=(tn-t30)/t30 if t30 and t30>0 else 0.0
                    ft['tvl_drawdown']=(tn-t90h)/t90h if t90h>0 else 0.0
                    # Price divergence
                    pn_price=tp[idx][1]
                    p30_idx=get_idx(tp,(datetime.strptime(wd,"%Y-%m-%d")-timedelta(days=30)).strftime("%Y-%m-%d"))
                    if p30_idx and tp[p30_idx][1]>0:
                        pchg=(pn_price-tp[p30_idx][1])/tp[p30_idx][1]
                        ft['tvl_vs_price_divergence']=ft['tvl_momentum_30d']-pchg
                    else:
                        ft['tvl_vs_price_divergence']=0.0
                else:
                    ft['tvl_momentum_7d']=ft['tvl_momentum_30d']=ft['tvl_drawdown']=ft['tvl_vs_price_divergence']=0.0
            else:
                ft['has_tvl_data']=0.0
                ft['tvl_momentum_7d']=ft['tvl_momentum_30d']=ft['tvl_drawdown']=ft['tvl_vs_price_divergence']=0.0

            # Structural
            sf=struct.get(tid)
            if sf:
                ft['has_audit']=sf['audit']
                ft['is_fork']=sf['fork']
                ft['category_risk']=sf['cat_risk']
                la=sf.get('listed_at')
                if la:
                    try:
                        ld=datetime.fromtimestamp(la) if isinstance(la,(int,float)) else datetime.strptime(str(la)[:10],"%Y-%m-%d")
                        ft['protocol_age_days']=max(0,(datetime.strptime(wd,"%Y-%m-%d")-ld).days)/365.0
                    except: ft['protocol_age_days']=0.0
                else: ft['protocol_age_days']=0.0
            else:
                ft['has_audit']=0.0; ft['is_fork']=0.0; ft['category_risk']=0.5; ft['protocol_age_days']=0.0

            # Stablecoin
            ch=tok_chain.get(tid,"")
            sv=0.0
            if ch:
                for o in range(7):
                    ck=(datetime.strptime(wd,"%Y-%m-%d")-timedelta(days=o)).strftime("%Y-%m-%d")
                    if (ch,ck) in stable_chg: sv=stable_chg[(ch,ck)]; break
            ft['chain_stablecoin_change_30d']=sv

            # Yield
            apy=yld.get(tid,0)
            ft['yield_anomaly']=1.0 if apy>100 else (apy/100.0 if apy>0 else 0.0)

            # V3 interactions
            ft['ix_tvl_div_x_trust']=ft['tvl_vs_price_divergence']*maint_weak
            ft['ix_no_audit_x_drawdown']=(1-ft['has_audit'])*abs(dd90)

            # Crash label
            start_p=close
            end_d=(datetime.strptime(wd,"%Y-%m-%d")+timedelta(days=CRASH_DAYS)).strftime("%Y-%m-%d")
            max_drop=0.0
            for pi in range(idx+1,len(tp)):
                if tp[pi][0]>end_d: break
                d=(tp[pi][1]-start_p)/start_p
                if d<max_drop: max_drop=d
            crashed=1 if max_drop<=CRASH_THRESH else 0

            row={'tid':tid,'date':wd,'ft':ft,'crashed':crashed,'max_drop':max_drop}
            if wd<=IS_CUTOFF: rows_is.append(row)
            elif wd>=OOS_START: rows_oos.append(row)

    print(f"  IS:  {len(rows_is)} ({sum(r['crashed'] for r in rows_is)} crashes = {100*sum(r['crashed'] for r in rows_is)/max(1,len(rows_is)):.1f}%)")
    print(f"  OOS: {len(rows_oos)} ({sum(r['crashed'] for r in rows_oos)} crashes = {100*sum(r['crashed'] for r in rows_oos)/max(1,len(rows_oos)):.1f}%)")
    print(f"  Skip: {skip}")
    return rows_is,rows_oos

# ── LOGISTIC REGRESSION ──
class LogReg:
    def __init__(self,d):
        self.w=[0.0]*d; self.b=0.0; self.means=[0.0]*d; self.stds=[1.0]*d
    def fit(self,X,y,lr=0.01,iters=10000,reg=0.01):
        n,d=len(X),len(X[0])
        for j in range(d):
            vals=[X[i][j] for i in range(n)]
            self.means[j]=sum(vals)/n
            var=sum((v-self.means[j])**2 for v in vals)/n
            self.stds[j]=math.sqrt(var) if var>1e-10 else 1.0
        Xs=[[(X[i][j]-self.means[j])/self.stds[j] for j in range(d)] for i in range(n)]
        best_loss=1e9; pat=0
        for ep in range(iters):
            pr=[sig(sum(self.w[j]*Xs[i][j] for j in range(d))+self.b) for i in range(n)]
            loss=-sum(y[i]*math.log(max(pr[i],1e-15))+(1-y[i])*math.log(max(1-pr[i],1e-15)) for i in range(n))/n
            loss+=reg*sum(w*w for w in self.w)/(2*n)
            if loss<best_loss-1e-6: best_loss=loss; pat=0
            else: pat+=1
            if pat>200: break
            gw=[0.0]*d; gb=0.0
            for i in range(n):
                e=pr[i]-y[i]
                for j in range(d): gw[j]+=e*Xs[i][j]/n+reg*self.w[j]/n
                gb+=e/n
            for j in range(d): self.w[j]-=lr*gw[j]
            self.b-=lr*gb
            if ep==3000: lr*=0.5
            if ep==6000: lr*=0.5
        pr=[sig(sum(self.w[j]*Xs[i][j] for j in range(d))+self.b) for i in range(n)]
        print(f"  Converged ep={ep} loss={best_loss:.4f}")
    def predict(self,X):
        return [sig(sum(self.w[j]*(X[i][j]-self.means[j])/self.stds[j] for j in range(len(self.w)))+self.b) for i in range(len(X))]

# ── SEVERITY ──
def severity(rows,probs,label):
    print(f"\n{'='*70}\nSEVERITY — {label} (n={len(rows)})\n{'='*70}")
    for th in [0.3,0.4,0.5]:
        print(f"\n--- >{th:.0%} ---")
        for sn,(lo,hi) in SEV.items():
            obs=[(r,p) for r,p in zip(rows,probs) if lo<r['max_drop']<=hi]
            if not obs: continue
            c=sum(1 for r,p in obs if p>th)
            rate,cl,ch2=wilson(c,len(obs))
            print(f"  {sn:15s}: {c:>4}/{len(obs):<4} = {rate:>6.1%} [{cl:.1%}, {ch2:.1%}]")
        nr=[(r,p) for r,p in zip(rows,probs) if r['max_drop']<=-0.80]
        if nr:
            c=sum(1 for r,p in nr if p>th)
            rate,cl,ch2=wilson(c,len(nr))
            print(f"  {'never-recover':15s}: {c:>4}/{len(nr):<4} = {rate:>6.1%} [{cl:.1%}, {ch2:.1%}]")
    # TVL subgroup
    print(f"\n--- TVL Impact (>40%, crashes) ---")
    for ht,lb in [(1,"WITH TVL"),(0,"NO TVL")]:
        sub=[(r,p) for r,p in zip(rows,probs) if r['ft'].get('has_tvl_data',0)==ht and r['crashed']==1]
        if sub:
            c=sum(1 for r,p in sub if p>0.4)
            rate,_,_=wilson(c,len(sub))
            print(f"  {lb:12s}: {c}/{len(sub)} = {rate:.1%}")

# ── MAIN ──
def main():
    print("="*70+"\nNERQ CRASH MODEL v3 (correct v2 base)\n"+"="*70)
    prices,ndd,ratings,tvl_tok,struct,sbc,tok_chain,yld=load_data()
    rows_is,rows_oos=build_dataset(prices,ndd,ratings,tvl_tok,struct,sbc,tok_chain,yld)
    if not rows_is: print("[FATAL] No IS data!"); return

    for feat_set,label in [(V2_FEAT,"V2 (16)"),(ALL_FEAT,"V3 (29)")]:
        print(f"\n{'='*70}\nTRAINING: {label}\n{'='*70}")
        d=len(feat_set)
        X_is=[[r['ft'][f] for f in feat_set] for r in rows_is]
        y_is=[r['crashed'] for r in rows_is]
        model=LogReg(d)
        model.fit(X_is,y_is)
        p_is=model.predict(X_is)
        auc_is=auc_calc(y_is,p_is)
        print(f"  IS AUC: {auc_is:.4f}")

        if rows_oos:
            X_oos=[[r['ft'][f] for f in feat_set] for r in rows_oos]
            y_oos=[r['crashed'] for r in rows_oos]
            p_oos=model.predict(X_oos)
            auc_oos=auc_calc(y_oos,p_oos)
            print(f"  OOS AUC: {auc_oos:.4f}")
            severity(rows_oos,p_oos,f"{label} OOS")
        else:
            auc_oos=None

        if feat_set==ALL_FEAT:
            # Feature importance
            imp=sorted([(abs(model.w[i]),model.w[i],feat_set[i]) for i in range(d)],reverse=True)
            tot=sum(a for a,_,_ in imp)
            print(f"\nFEATURE IMPORTANCE:")
            print(f"{'#':>3} {'Feature':35s} {'Wt':>10} {'%':>6}")
            print("-"*60)
            new_f=set(V3_NEW)
            for i,(a,w,n) in enumerate(imp[:20]):
                print(f"{i+1:>3} {n:35s} {'+'if w>0 else'-'}{a:.5f} {100*a/tot:>5.1f}%{' ★'if n in new_f else''}")
            print("★ = new v3")

            # Save model
            m={'version':'crash_model_v3','weights':model.w,'bias':model.b,
               'feature_means':model.means,'feature_stds':model.stds,
               'feature_names':feat_set,'is_auc':auc_is,'oos_auc':auc_oos,
               'run_date':datetime.now().isoformat()}
            mp=os.path.join(os.path.dirname(DB),"crash_model_v3.json")
            with open(mp,"w") as f: json.dump(m,f,indent=2)
            print(f"\n[SAVED] {mp}")

            # Save to DB
            try:
                conn=sqlite3.connect(DB)
                cur=conn.cursor()
                cur.execute("""CREATE TABLE IF NOT EXISTS crash_model_v3_predictions(
                    token_id TEXT,date TEXT,crash_prob_v3 REAL,crash_label INTEGER,
                    max_drawdown REAL,has_tvl_data INTEGER,period TEXT,
                    PRIMARY KEY(token_id,date))""")
                cur.execute("DELETE FROM crash_model_v3_predictions")
                for rows,per,probs in [(rows_is,"IS",model.predict([[r['ft'][f] for f in feat_set] for r in rows_is])),
                                        (rows_oos,"OOS",model.predict([[r['ft'][f] for f in feat_set] for r in rows_oos]) if rows_oos else [])]:
                    for r,p in zip(rows,probs):
                        cur.execute("INSERT OR REPLACE INTO crash_model_v3_predictions VALUES(?,?,?,?,?,?,?)",
                            (r['tid'],r['date'],p,r['crashed'],r['max_drop'],int(r['ft'].get('has_tvl_data',0)),per))
                conn.commit(); conn.close()
                print(f"[DB] Saved predictions")
            except Exception as e:
                print(f"[DB] Error: {e}")

    print(f"\n{'='*70}\nDONE\n{'='*70}")

if __name__=="__main__": main()
