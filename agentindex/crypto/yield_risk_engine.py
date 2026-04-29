"""Sprint 9: Yield Risk Engine v1.1 — batch SQL, no N+1"""
import os
import sqlite3
from typing import Optional

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)).replace("/agentindex-factory/", "/agentindex/"),
    "crypto_trust.db",
)

def _apy_risk_score(apy):
    if apy<=0: return 5
    if apy<=5: return 0
    if apy<=20: return 5
    if apy<=50: return 10
    if apy<=100: return 18
    if apy<=200: return 25
    if apy<=500: return 33
    return 40

def _reward_dependency_score(apy, apy_reward):
    if apy<=0: return 0
    r=apy_reward/apy
    if r<0.3: return 0
    if r<0.5: return 5
    if r<0.7: return 10
    if r<0.9: return 15
    return 20

def _tvl_risk_score(tvl):
    if tvl is None or tvl<=0: return 15
    if tvl>=100_000_000: return 0
    if tvl>=10_000_000: return 3
    if tvl>=1_000_000: return 7
    if tvl>=100_000: return 11
    return 15

def _il_risk_score(il, apy):
    if il=="yes":
        if apy<10: return 10
        if apy<30: return 6
        return 3
    return 0

def _protocol_risk_score(rl, cp):
    s=0
    if rl=="CRITICAL": s+=12
    elif rl=="WARNING": s+=8
    elif rl=="WATCH": s+=4
    if cp: s+=min(cp*10,5)
    return min(s,15)

def compute_yield_risk_score(apy,apy_base,apy_reward,tvl_usd,il_risk,stablecoin,risk_level=None,crash_prob=None):
    a=_apy_risk_score(apy)
    rw=_reward_dependency_score(apy,apy_reward)
    tv=_tvl_risk_score(tvl_usd)
    il=_il_risk_score(il_risk,apy)
    pr=_protocol_risk_score(risk_level,crash_prob)
    raw=a+rw+tv+il+pr
    if stablecoin: raw*=0.8
    score=min(round(raw),100)
    rr=(apy_reward/apy) if apy>0 else 0
    is_trap=((apy>500 and rr>0.8) or (risk_level in("CRITICAL","WARNING") and apy>100)
             or (il_risk=="yes" and apy<10) or (tvl_usd is not None and tvl_usd<100_000 and apy>50)
             or (rr>0.9 and apy>50))
    if score>=75: tier="EXTREME"
    elif score>=55: tier="HIGH"
    elif score>=35: tier="MEDIUM"
    elif score>=15: tier="LOW"
    else: tier="SAFE"
    return {"yield_risk_score":score,"yield_risk_tier":tier,"is_yield_trap":is_trap,
            "components":{"apy_risk":round(a,1),"reward_dependency":round(rw,1),
                          "tvl_risk":round(tv,1),"il_risk":round(il,1),"protocol_risk":round(pr,1)}}

def _get_db():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c

def _get_protocol_risk(conn,project):
    try:
        r=conn.execute("SELECT r.risk_level,c.crash_prob_v3 FROM nerq_risk_signals r LEFT JOIN crash_model_v3_predictions c ON c.token_id=r.token_id WHERE LOWER(r.token_id) LIKE LOWER(?) ORDER BY r.signal_date DESC LIMIT 1",(f"%{project}%",)).fetchone()
        if r: return r["risk_level"],r["crash_prob_v3"]
    except: pass
    return None,None

def _batch_protocol_risk(conn,projects):
    if not projects: return {}
    try:
        rows=conn.execute("SELECT r.token_id,r.risk_level,c.crash_prob_v3 FROM nerq_risk_signals r LEFT JOIN crash_model_v3_predictions c ON c.token_id=r.token_id WHERE r.signal_date=(SELECT MAX(r2.signal_date) FROM nerq_risk_signals r2 WHERE r2.token_id=r.token_id)").fetchall()
    except: return {p.lower():(None,None) for p in projects}
    tm={r["token_id"].lower():(r["risk_level"],r["crash_prob_v3"]) for r in rows}
    result={}
    for p in projects:
        pl=p.lower()
        if pl in tm: result[pl]=tm[pl]; continue
        result[pl]=next((v for tid,v in tm.items() if pl in tid or tid in pl),(None,None))
    return result

def get_yield_risk(protocol,pool):
    conn=_get_db()
    try:
        row=conn.execute("SELECT * FROM defi_yields WHERE pool_id=? OR (LOWER(project)=LOWER(?) AND LOWER(symbol) LIKE LOWER(?)) LIMIT 1",(pool,protocol,f"%{pool}%")).fetchone()
        if not row: row=conn.execute("SELECT * FROM defi_yields WHERE LOWER(project)=LOWER(?) ORDER BY tvl_usd DESC LIMIT 1",(protocol,)).fetchone()
        if not row: return {"error":f"Not found: {protocol}/{pool}","found":False}
        rl,cp=_get_protocol_risk(conn,protocol)
        sc=compute_yield_risk_score(apy=row["apy"] or 0,apy_base=row["apy_base"] or 0,apy_reward=row["apy_reward"] or 0,tvl_usd=row["tvl_usd"],il_risk=row["il_risk"] or "no",stablecoin=row["stablecoin"] or 0,risk_level=rl,crash_prob=cp)
        rr=(row["apy_reward"]/row["apy"]) if (row["apy"] or 0)>0 else 0
        return {"found":True,"pool_id":row["pool_id"],"protocol":row["project"],"chain":row["chain"],"symbol":row["symbol"],"tvl_usd":row["tvl_usd"],"apy":row["apy"],"apy_base":row["apy_base"],"apy_reward":row["apy_reward"],"reward_ratio":round(rr,3),"il_risk":row["il_risk"],"stablecoin":bool(row["stablecoin"]),"protocol_risk_level":rl,"protocol_crash_prob":round(cp,3) if cp else None,**sc,"zarq_url":"https://zarq.ai/yield-risk","data_freshness":row["crawled_at"]}
    finally: conn.close()

def get_yield_traps(min_apy=5,chain=None,limit=50,include_stablecoins=False):
    conn=_get_db()
    try:
        wc=["apy >= ?"]; params=[min_apy]; wc[0]="apy >= ?"
        if chain: wc.append("LOWER(chain)=LOWER(?)"); params.append(chain)
        if not include_stablecoins: wc.append("stablecoin=0")
        rows=conn.execute(f"SELECT * FROM defi_yields WHERE {' AND '.join(wc)} AND apy IS NOT NULL ORDER BY apy DESC LIMIT 10000",params).fetchall()
        if not rows:
            return {"summary":{"total_pools_analyzed":0,"yield_traps_detected":0,"high_risk_pools":0,"tier_distribution":{"EXTREME":0,"HIGH":0,"MEDIUM":0,"LOW":0,"SAFE":0},"top_trap_chains":[],"filter":{"min_apy":min_apy,"chain":chain,"include_stablecoins":include_stablecoins}},"yield_traps":[],"high_risk_pools":[],"data_freshness":None,"zarq_url":"https://zarq.ai/yield-risk"}
        projects=list({r["project"] for r in rows})
        rm=_batch_protocol_risk(conn,projects)
        traps,high_risk,all_scored=[],[],[]
        tc={"EXTREME":0,"HIGH":0,"MEDIUM":0,"LOW":0,"SAFE":0}
        ct={}
        for row in rows:
            p=(row["project"] or "").lower()
            rl,cp=rm.get(p,(None,None))
            sc=compute_yield_risk_score(apy=row["apy"] or 0,apy_base=row["apy_base"] or 0,apy_reward=row["apy_reward"] or 0,tvl_usd=row["tvl_usd"],il_risk=row["il_risk"] or "no",stablecoin=row["stablecoin"] or 0,risk_level=rl,crash_prob=cp)
            tc[sc["yield_risk_tier"]]=tc.get(sc["yield_risk_tier"],0)+1
            e={"pool_id":row["pool_id"],"protocol":row["project"],"chain":row["chain"],"symbol":row["symbol"],"tvl_usd":row["tvl_usd"],"apy":row["apy"],"apy_base":row["apy_base"] or 0,"apy_reward":row["apy_reward"] or 0,"il_risk":row["il_risk"],"stablecoin":bool(row["stablecoin"]),"protocol_risk_level":rl,**sc}
            all_scored.append(e)
            if sc["is_yield_trap"]: traps.append(e); ct[row["chain"]]=ct.get(row["chain"],0)+1
            if sc["yield_risk_tier"] in("EXTREME","HIGH"): high_risk.append(e)
        traps.sort(key=lambda x:x["yield_risk_score"],reverse=True)
        high_risk.sort(key=lambda x:x["yield_risk_score"],reverse=True)
        return {"summary":{"total_pools_analyzed":len(all_scored),"yield_traps_detected":len(traps),"high_risk_pools":len(high_risk),"tier_distribution":tc,"top_trap_chains":[{"chain":c,"traps":n} for c,n in sorted(ct.items(),key=lambda x:x[1],reverse=True)[:8]],"filter":{"min_apy":min_apy,"chain":chain,"include_stablecoins":include_stablecoins}},"yield_traps":traps[:limit],"high_risk_pools":high_risk[:limit],"data_freshness":rows[0]["crawled_at"] if rows else None,"zarq_url":"https://zarq.ai/yield-risk"}
    finally: conn.close()

def get_yield_overview():
    conn=_get_db()
    try:
        s=conn.execute("SELECT COUNT(*) as total_pools,COUNT(DISTINCT project) as total_protocols,COUNT(DISTINCT chain) as total_chains,SUM(tvl_usd) as total_tvl,AVG(apy) as avg_apy,MAX(apy) as max_apy,SUM(CASE WHEN apy>500 THEN 1 ELSE 0 END) as extreme_apy_count,SUM(CASE WHEN apy>100 THEN 1 ELSE 0 END) as high_apy_count,SUM(CASE WHEN stablecoin=1 THEN 1 ELSE 0 END) as stablecoin_pools,SUM(CASE WHEN il_risk='yes' THEN 1 ELSE 0 END) as il_risk_pools FROM defi_yields").fetchone()
        top=conn.execute("SELECT project,chain,symbol,tvl_usd,apy FROM defi_yields ORDER BY tvl_usd DESC LIMIT 10").fetchall()
        chains=conn.execute("SELECT chain,COUNT(*) as pools,SUM(tvl_usd) as tvl FROM defi_yields GROUP BY chain ORDER BY tvl DESC LIMIT 10").fetchall()
        return {"total_pools":s["total_pools"],"total_protocols":s["total_protocols"],"total_chains":s["total_chains"],"total_tvl_usd":s["total_tvl"],"avg_apy":round(s["avg_apy"] or 0,2),"max_apy":s["max_apy"],"extreme_apy_pools":s["extreme_apy_count"],"high_apy_pools":s["high_apy_count"],"stablecoin_pools":s["stablecoin_pools"],"il_risk_pools":s["il_risk_pools"],"top_tvl_pools":[dict(r) for r in top],"chains":[dict(r) for r in chains]}
    finally: conn.close()

def check_yield_crash_shield_triggers(conn=None):
    close=False
    if conn is None: conn=_get_db(); close=True
    try:
        rows=conn.execute("SELECT dy.*,r.risk_level,c.crash_prob_v3 FROM defi_yields dy LEFT JOIN nerq_risk_signals r ON LOWER(r.token_id) LIKE LOWER('%'||dy.project||'%') LEFT JOIN crash_model_v3_predictions c ON c.token_id=r.token_id WHERE dy.apy>100 AND (r.risk_level IN ('CRITICAL','WARNING') OR dy.apy>500) ORDER BY dy.apy DESC LIMIT 200").fetchall()
        triggers=[]
        for row in rows:
            sc=compute_yield_risk_score(apy=row["apy"] or 0,apy_base=row["apy_base"] or 0,apy_reward=row["apy_reward"] or 0,tvl_usd=row["tvl_usd"],il_risk=row["il_risk"] or "no",stablecoin=row["stablecoin"] or 0,risk_level=row["risk_level"],crash_prob=row["crash_prob_v3"])
            if sc["is_yield_trap"] and sc["yield_risk_score"]>=65:
                triggers.append({"event_type":"YIELD_TRAP_DETECTED","pool_id":row["pool_id"],"protocol":row["project"],"chain":row["chain"],"symbol":row["symbol"],"apy":row["apy"],"tvl_usd":row["tvl_usd"],"yield_risk_score":sc["yield_risk_score"],"yield_risk_tier":sc["yield_risk_tier"],"protocol_risk_level":row["risk_level"]})
        return triggers
    finally:
        if close: conn.close()
