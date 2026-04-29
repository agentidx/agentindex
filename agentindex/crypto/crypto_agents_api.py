"""
Sprint 6: On-chain Agent Crawling API
GET /v1/agents/crypto/{agent_id}
GET /v1/agents/in/{entity_type}/{entity_id}
GET /v1/agents/new
"""
import os
import sqlite3, json
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)).replace("/agentindex-factory/", "/agentindex/"),
    "crypto_trust.db",
)

router_agents = APIRouter(prefix="/v1/agents", tags=["agents"])

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def row_to_dict(row):
    d = dict(row)
    if d.get("metadata_json"):
        try:
            d["metadata"] = json.loads(d.pop("metadata_json"))
        except:
            d.pop("metadata_json", None)
    return d

@router_agents.get("/crypto/{agent_id}")
def get_agent_profile(agent_id: str):
    """Hämta profil för en specifik agent"""
    conn = get_db()
    row = conn.execute("""
        SELECT agent_id, source, agent_name, description, chain,
               token_address, token_symbol, market_cap_usd,
               staked_value_usd, creator_address, agent_type,
               metadata_json, first_seen_at, last_updated_at
        FROM agent_crypto_profile
        WHERE agent_id = ?
    """, (agent_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return row_to_dict(row)

@router_agents.get("/in/{entity_type}/{entity_id}")
def get_agents_in_entity(
    entity_type: str,
    entity_id: str,
    source: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0
):
    """
    Agenter inom en entity.
    entity_type: chain | source | type
    entity_id: ex 'base', 'olas', 'trading'
    """
    conn = get_db()

    if entity_type == "chain":
        where = "LOWER(chain) = LOWER(?)"
        param = entity_id
    elif entity_type == "source":
        where = "source = ?"
        param = entity_id
    elif entity_type == "type":
        where = "agent_type = ?"
        param = entity_id
    else:
        raise HTTPException(status_code=400, detail=f"entity_type must be: chain, source, type")

    extra = " AND source = ?" if source else ""
    params = [param, limit, offset] if not source else [param, source, limit, offset]

    rows = conn.execute(f"""
        SELECT agent_id, source, agent_name, agent_type, chain,
               token_symbol, market_cap_usd, last_updated_at
        FROM agent_crypto_profile
        WHERE {where}{extra}
        ORDER BY market_cap_usd DESC NULLS LAST
        LIMIT ? OFFSET ?
    """, params).fetchall()

    total = conn.execute(f"""
        SELECT COUNT(*) FROM agent_crypto_profile WHERE {where}{extra}
    """, [param] if not source else [param, source]).fetchone()[0]

    conn.close()
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "agents": [dict(r) for r in rows]
    }

@router_agents.get("/new")
def get_new_agents(
    source: Optional[str] = None,
    limit: int = Query(50, le=200)
):
    """Senast crawlade agenter"""
    conn = get_db()
    where = "WHERE source = ?" if source else ""
    params = [source, limit] if source else [limit]
    rows = conn.execute(f"""
        SELECT agent_id, source, agent_name, agent_type, chain,
               token_symbol, market_cap_usd, first_seen_at, last_updated_at
        FROM agent_crypto_profile
        {where}
        ORDER BY last_updated_at DESC
        LIMIT ?
    """, params).fetchall()

    stats = conn.execute("""
        SELECT source, COUNT(*) as n
        FROM agent_crypto_profile
        GROUP BY source ORDER BY n DESC
    """).fetchall()
    conn.close()

    return {
        "total_agents": sum(r[1] for r in stats),
        "by_source": {r[0]: r[1] for r in stats},
        "agents": [dict(r) for r in rows]
    }

@router_agents.get("/relations/{agent_id}")
def get_agent_relations(agent_id: str):
    """Hämta alla relationer för en agent"""
    conn = get_db()
    rows = conn.execute("""
        SELECT relation_type, entity_id, entity_name, entity_symbol, confidence
        FROM agent_crypto_relations
        WHERE agent_id = ?
        ORDER BY relation_type
    """, (agent_id,)).fetchall()
    conn.close()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Inga relationer för '{agent_id}'")
    return {
        "agent_id": agent_id,
        "relations": [dict(r) for r in rows]
    }

@router_agents.get("/graph/{entity_type}/{entity_id}")
def get_entity_graph(
    entity_type: str,
    entity_id: str,
    limit: int = Query(50, le=200)
):
    """Hämta alla agenter kopplade till en entity (chain/protocol/token/subnet)"""
    conn = get_db()
    rows = conn.execute("""
        SELECT r.agent_id, r.agent_source, r.confidence,
               a.agent_name, a.agent_type, a.market_cap_usd
        FROM agent_crypto_relations r
        JOIN agent_crypto_profile a ON r.agent_id = a.agent_id AND r.agent_source = a.source
        WHERE r.relation_type = ? AND LOWER(r.entity_id) = LOWER(?)
        ORDER BY a.market_cap_usd DESC NULLS LAST
        LIMIT ?
    """, (entity_type, entity_id, limit)).fetchall()
    total = conn.execute("""
        SELECT COUNT(*) FROM agent_crypto_relations
        WHERE relation_type = ? AND LOWER(entity_id) = LOWER(?)
    """, (entity_type, entity_id)).fetchone()[0]
    conn.close()
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "total": total,
        "agents": [dict(r) for r in rows]
    }

# ═══════════════════════════════════════════════════════════
# SPRINT 7: Wallet Behavior + Agent Activity Index
# ═══════════════════════════════════════════════════════════
REPORT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)).replace("/agentindex-factory/", "/agentindex/"),
    "reports",
)

@router_agents.get("/activity/{entity_type}/{entity_id}")
def get_agent_activity_index(entity_type: str, entity_id: str):
    """Agent Activity Index — AI-koncentration per entity."""
    conn = get_db()
    row = conn.execute("""
        SELECT entity_type, entity_id, entity_name, entity_symbol,
               total_agents, identified_ai_agents, ai_agent_ratio,
               ai_controlled_tvl_usd, total_tvl_usd, ai_tvl_ratio,
               avg_agent_confidence, top_agent_types, computed_at
        FROM agent_activity_index
        WHERE entity_type = ? AND LOWER(entity_id) = LOWER(?)
    """, (entity_type, entity_id)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Ingen activity index för {entity_type}/{entity_id}")
    d = dict(row)
    if d.get("top_agent_types"):
        try: d["top_agent_types"] = json.loads(d["top_agent_types"])
        except: pass
    ai_ratio_pct = round(d["ai_agent_ratio"] * 100, 1)
    tvl_str = f", kontrollerar {d['ai_tvl_ratio']*100:.1f}% av TVL" if d.get("ai_tvl_ratio") else ""
    d["summary"] = f"{d['identified_ai_agents']} av {d['total_agents']} ({ai_ratio_pct}%) är AI-agenter{tvl_str}"
    return d

@router_agents.get("/activity-overview")
def get_activity_overview(
    entity_type: Optional[str] = None,
    min_ai_agents: int = Query(1, ge=0),
    limit: int = Query(50, le=200),
    offset: int = 0
):
    """Översikt av alla entities sorterade på AI-agent koncentration."""
    conn = get_db()
    where = "identified_ai_agents >= ?"
    params = [min_ai_agents]
    if entity_type:
        where += " AND entity_type = ?"
        params.append(entity_type)
    rows = conn.execute(f"""
        SELECT entity_type, entity_id, entity_name, entity_symbol,
               total_agents, identified_ai_agents, ai_agent_ratio,
               ai_tvl_ratio, avg_agent_confidence, computed_at
        FROM agent_activity_index WHERE {where}
        ORDER BY identified_ai_agents DESC LIMIT ? OFFSET ?
    """, params + [limit, offset]).fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM agent_activity_index WHERE {where}", params).fetchone()[0]
    stats = conn.execute("SELECT SUM(total_agents), SUM(identified_ai_agents), COUNT(DISTINCT entity_id) FROM agent_activity_index").fetchone()
    conn.close()
    return {
        "global_stats": {"total_agents": stats[0], "total_ai_agents": stats[1], "entities_indexed": stats[2]},
        "total_results": total, "limit": limit, "offset": offset,
        "entities": [dict(r) for r in rows]
    }

@router_agents.get("/wallet/{address}")
def get_wallet_behavior(address: str):
    """Wallet behavior-analys — P(AI-agent) confidence och beteendesignaler."""
    conn = get_db()
    row = conn.execute("""
        SELECT wallet_address, chain, tx_count_90d, avg_tx_per_day,
               night_tx_ratio, weekend_tx_ratio, interval_regularity,
               failed_tx_ratio, unique_protocols, defi_tx_ratio,
               agent_type, confidence, confidence_signals, is_ai_agent,
               first_tx_date, last_tx_date, analyzed_at
        FROM wallet_behavior WHERE wallet_address = LOWER(?)
    """, (address,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Ingen analys för {address}")
    d = dict(row)
    if d.get("confidence_signals"):
        try: d["confidence_signals"] = json.loads(d["confidence_signals"])
        except: pass
    d["is_ai_agent"] = bool(d["is_ai_agent"])
    d["confidence_label"] = "HIGH" if d["confidence"] >= 0.75 else "MEDIUM" if d["confidence"] >= 0.50 else "LOW"
    return d

@router_agents.get("/ai-identified")
def get_ai_identified_agents(
    agent_type: Optional[str] = None,
    min_confidence: float = Query(0.35, ge=0.0, le=1.0),
    limit: int = Query(50, le=200),
    offset: int = 0
):
    """Lista alla wallets identifierade som AI-agenter."""
    conn = get_db()
    where = "wb.is_ai_agent=1 AND wb.confidence >= ?"
    params = [min_confidence]
    if agent_type:
        where += " AND wb.agent_type = ?"
        params.append(agent_type)
    rows = conn.execute(f"""
        SELECT wb.wallet_address, wb.agent_type, wb.confidence,
               wb.avg_tx_per_day, wb.night_tx_ratio, wb.interval_regularity,
               wb.unique_protocols, wb.analyzed_at,
               acp.agent_id, acp.agent_name, acp.source, acp.chain,
               acp.token_symbol, acp.market_cap_usd
        FROM wallet_behavior wb
        LEFT JOIN agent_crypto_profile acp ON LOWER(acp.creator_address) = wb.wallet_address
        WHERE {where} ORDER BY wb.confidence DESC LIMIT ? OFFSET ?
    """, params + [limit, offset]).fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM wallet_behavior wb WHERE {where}", params).fetchone()[0]
    type_breakdown = conn.execute("""
        SELECT agent_type, COUNT(*) as n FROM wallet_behavior
        WHERE is_ai_agent=1 GROUP BY agent_type ORDER BY n DESC
    """).fetchall()
    conn.close()
    return {
        "total": total, "limit": limit, "offset": offset,
        "type_breakdown": {r["agent_type"]: r["n"] for r in type_breakdown},
        "agents": [dict(r) for r in rows]
    }

@router_agents.get("/report/latest")
def get_latest_discovery_report():
    """Senaste veckovisa Agent Discovery Report (JSON)."""
    json_path = f"{REPORT_DIR}/agent_discovery_latest.json"
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="Ingen rapport ännu. Kör weekly_discovery_report.py")
    with open(json_path, "r") as f:
        return json.load(f)

# ═══════════════════════════════════════════════════════════
# SPRINT 7 WOW: Agent Risk Intelligence
# ═══════════════════════════════════════════════════════════

@router_agents.get("/risk-exposure")
def get_agent_risk_exposure(
    risk_level: Optional[str] = None,
    structural_collapse: bool = False,
    high_crash_risk: bool = False,
    source: Optional[str] = None,
    chain: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """WOW 1/2/3: AI-agenter rankade efter riskexponering."""
    conn = get_db()
    where = ["1=1"]
    params = []
    if risk_level:
        where.append("risk_level = ?")
        params.append(risk_level.upper())
    if structural_collapse:
        where.append("is_structural_collapse = 1")
    if high_crash_risk:
        where.append("is_high_crash_risk = 1")
    if source:
        where.append("agent_source = ?")
        params.append(source)
    if chain:
        where.append("LOWER(chain) = LOWER(?)")
        params.append(chain)
    where_str = " AND ".join(where)
    rows = conn.execute(f"""
        SELECT agent_id, agent_source, agent_name, chain, token_symbol,
               market_cap_usd, risk_level, structural_weakness,
               trust_p3, crash_prob_v3, is_structural_collapse,
               is_high_crash_risk, is_warning_or_critical, computed_at
        FROM agent_risk_exposure WHERE {where_str}
        ORDER BY CASE risk_level WHEN 'CRITICAL' THEN 1 WHEN 'WARNING' THEN 2
                 WHEN 'WATCH' THEN 3 WHEN 'SAFE' THEN 4 ELSE 5 END,
                 COALESCE(crash_prob_v3,0) DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset]).fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM agent_risk_exposure WHERE {where_str}", params).fetchone()[0]
    agg = conn.execute(f"""
        SELECT SUM(CASE WHEN risk_level='CRITICAL' THEN 1 ELSE 0 END) as critical,
               SUM(CASE WHEN risk_level='WARNING' THEN 1 ELSE 0 END) as warning,
               SUM(is_structural_collapse) as structural_collapse,
               SUM(is_high_crash_risk) as high_crash_risk,
               SUM(COALESCE(market_cap_usd,0)) as total_mcap,
               SUM(CASE WHEN risk_level IN ('WARNING','CRITICAL')
                   THEN COALESCE(market_cap_usd,0) ELSE 0 END) as mcap_at_risk
        FROM agent_risk_exposure WHERE {where_str}
    """, params).fetchone()
    conn.close()
    return {
        "total": total, "limit": limit, "offset": offset,
        "summary": {
            "critical": agg["critical"] or 0,
            "warning": agg["warning"] or 0,
            "structural_collapse": agg["structural_collapse"] or 0,
            "high_crash_risk": agg["high_crash_risk"] or 0,
            "total_mcap_usd": round(agg["total_mcap"] or 0, 2),
            "mcap_at_risk_usd": round(agg["mcap_at_risk"] or 0, 2),
        },
        "agents": [dict(r) for r in rows]
    }

@router_agents.get("/structural-collapse")
def get_structural_collapse_agents(limit: int = Query(50, le=200), offset: int = 0):
    """WOW 3: AI-agenter exponerade mot Structural Collapse-tokens."""
    conn = get_db()
    rows = conn.execute("""
        SELECT agent_id, agent_source, agent_name, chain, token_symbol,
               market_cap_usd, structural_weakness, trust_p3,
               sig6_structure, ndd_current, crash_prob_v3, computed_at
        FROM agent_risk_exposure WHERE is_structural_collapse = 1
        ORDER BY COALESCE(market_cap_usd, 0) DESC
        LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM agent_risk_exposure WHERE is_structural_collapse=1").fetchone()[0]
    total_mcap = conn.execute("SELECT SUM(COALESCE(market_cap_usd,0)) FROM agent_risk_exposure WHERE is_structural_collapse=1").fetchone()[0] or 0
    conn.close()
    return {
        "total_agents_in_structural_collapse": total,
        "total_mcap_exposed_usd": round(total_mcap, 2),
        "warning": "These tokens have triggered ZARQ Structural Collapse signal (100% recall).",
        "agents": [dict(r) for r in rows]
    }

@router_agents.get("/chain-concentration-risk")
def get_chain_concentration_risk(limit: int = Query(20, le=50)):
    """WOW 5: Chain-ranking efter AI-agent koncentrationsrisk."""
    conn = get_db()
    rows = conn.execute("""
        SELECT chain, total_agents, total_market_cap_usd,
               agents_in_critical, agents_in_warning,
               agents_structural_collapse, agents_high_crash_risk,
               mcap_in_critical_usd, mcap_in_warning_usd,
               mcap_high_crash_risk_usd, mcap_structural_collapse_usd,
               concentration_risk_score, risk_summary, computed_at
        FROM chain_concentration_risk
        ORDER BY concentration_risk_score DESC LIMIT ?
    """, (limit,)).fetchall()
    totals = conn.execute("""
        SELECT SUM(total_agents) as agents, SUM(total_market_cap_usd) as mcap,
               SUM(agents_in_critical + agents_in_warning) as at_risk
        FROM chain_concentration_risk
    """).fetchone()
    conn.close()
    chains = [dict(r) for r in rows]
    for i, c in enumerate(chains):
        c["rank"] = i + 1
        c["risk_label"] = ("EXTREME" if c["concentration_risk_score"] >= 8 else
                           "HIGH" if c["concentration_risk_score"] >= 6 else
                           "MEDIUM" if c["concentration_risk_score"] >= 4 else "LOW")
    return {
        "global": {"total_agents": totals["agents"] or 0,
                   "total_mcap_usd": round(totals["mcap"] or 0, 2),
                   "agents_at_risk": totals["at_risk"] or 0},
        "chains": chains
    }

@router_agents.get("/exodus-snapshot")
def get_exodus_snapshot(protocol_id: Optional[str] = None, days: int = Query(30, le=365)):
    """Tier 2: Agent Protocol Snapshot — tidsserie för exodus-analys. Backtest Q3 2026."""
    from datetime import datetime, timezone, timedelta
    conn = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    if protocol_id:
        rows = conn.execute("""
            SELECT snapshot_date, protocol_id, agent_count, total_market_cap_usd
            FROM agent_protocol_snapshot
            WHERE protocol_id = ? AND snapshot_date >= ?
            ORDER BY snapshot_date DESC
        """, (protocol_id, cutoff)).fetchall()
    else:
        rows = conn.execute("""
            SELECT snapshot_date, protocol_id, agent_count, total_market_cap_usd
            FROM agent_protocol_snapshot
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM agent_protocol_snapshot)
            ORDER BY agent_count DESC LIMIT 50
        """).fetchall()
    total_days = conn.execute("SELECT COUNT(DISTINCT snapshot_date) FROM agent_protocol_snapshot").fetchone()[0]
    conn.close()
    return {
        "days_of_history": total_days,
        "exodus_signal_eta": "Q3 2026 (requires 90 days of data)",
        "snapshots": [dict(r) for r in rows]
    }
