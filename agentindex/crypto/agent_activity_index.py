"""
Sprint 7: Agent Activity Index
Beräknar "X% av TVL kontrolleras av Y identifierade AI-agenter"
per token, protokoll och chain.
"""
import os
import sqlite3, json, logging
from datetime import datetime, timezone
from collections import Counter

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)).replace("/agentindex-factory/", "/agentindex/"),
    "crypto_trust.db",
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def compute_index_for_entity(conn, entity_type: str, entity_id: str) -> dict:
    """
    Beräkna Agent Activity Index för en entity.
    Kopplar agent_crypto_relations → agent_crypto_profile → wallet_behavior.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Hämta alla agenter kopplade till denna entity
    if entity_type in ("token", "protocol", "chain", "subnet"):
        agents = conn.execute("""
            SELECT r.agent_id, r.agent_source, r.confidence as relation_confidence,
                   a.agent_name, a.agent_type, a.market_cap_usd, a.staked_value_usd,
                   a.creator_address, a.chain as agent_chain,
                   a.token_symbol, a.token_address
            FROM agent_crypto_relations r
            JOIN agent_crypto_profile a ON r.agent_id = a.agent_id AND r.agent_source = a.source
            WHERE r.relation_type = ? AND LOWER(r.entity_id) = LOWER(?)
        """, (entity_type, entity_id)).fetchall()
    else:
        # Fallback: sök i agent_crypto_profile direkt
        agents = conn.execute("""
            SELECT agent_id, source as agent_source, 1.0 as relation_confidence,
                   agent_name, agent_type, market_cap_usd, staked_value_usd,
                   creator_address, chain as agent_chain,
                   token_symbol, token_address
            FROM agent_crypto_profile
            WHERE LOWER(chain) = LOWER(?)
        """, (entity_id,)).fetchall()

    if not agents:
        return None

    agent_ids = [a["agent_id"] for a in agents]
    total_agents = len(agent_ids)

    # Hämta wallet behavior för dessa agenters creator_addresses
    creator_addresses = [
        a["creator_address"].lower()
        for a in agents
        if a["creator_address"] and len(a["creator_address"]) >= 10
    ]

    ai_wallets = 0
    total_wallets_analyzed = 0
    confidence_sum = 0.0
    agent_types = Counter()

    if creator_addresses:
        placeholders = ",".join("?" * len(creator_addresses))
        behaviors = conn.execute(f"""
            SELECT wallet_address, confidence, is_ai_agent, agent_type
            FROM wallet_behavior
            WHERE wallet_address IN ({placeholders})
        """, creator_addresses).fetchall()

        total_wallets_analyzed = len(behaviors)
        for b in behaviors:
            if b["is_ai_agent"]:
                ai_wallets += 1
                if b["agent_type"]:
                    agent_types[b["agent_type"]] += 1
            confidence_sum += b["confidence"]

    # Beräkna AI-agent ratio
    # Primärt: baserat på wallet behavior-analys
    # Fallback: baserat på source (olas/fetchai = troliga AI-agenter)
    AI_SOURCES = {"olas", "fetchai", "bittensor", "virtuals"}
    source_based_ai = sum(1 for a in agents if a["agent_source"] in AI_SOURCES)

    if total_wallets_analyzed > 0:
        ai_agent_ratio = ai_wallets / total_wallets_analyzed
        avg_confidence = confidence_sum / total_wallets_analyzed
    else:
        # Fallback till source-baserad uppskattning
        ai_agent_ratio = source_based_ai / total_agents if total_agents > 0 else 0
        avg_confidence = 0.70 if source_based_ai > 0 else 0.0

    # TVL/market cap kontrollerad av AI-agenter
    total_mcap = sum(
        (a["market_cap_usd"] or 0) + (a["staked_value_usd"] or 0)
        for a in agents
    )
    ai_mcap = sum(
        (a["market_cap_usd"] or 0) + (a["staked_value_usd"] or 0)
        for a in agents
        if a["agent_source"] in AI_SOURCES
    )
    ai_tvl_ratio = ai_mcap / total_mcap if total_mcap > 0 else 0

    # Entity-namn och symbol
    entity_name = entity_id
    entity_symbol = None
    if agents:
        first = agents[0]
        if entity_type == "token":
            entity_symbol = first["token_symbol"]
        elif entity_type == "chain":
            entity_name = entity_id.title()

    return {
        "entity_type": entity_type,
        "entity_id": entity_id.lower(),
        "entity_name": entity_name,
        "entity_symbol": entity_symbol,
        "total_agents": total_agents,
        "identified_ai_agents": ai_wallets if total_wallets_analyzed > 0 else source_based_ai,
        "ai_agent_ratio": round(ai_agent_ratio, 4),
        "ai_controlled_tvl_usd": round(ai_mcap, 2) if ai_mcap > 0 else None,
        "total_tvl_usd": round(total_mcap, 2) if total_mcap > 0 else None,
        "ai_tvl_ratio": round(ai_tvl_ratio, 4) if total_mcap > 0 else None,
        "avg_agent_confidence": round(avg_confidence, 3),
        "top_agent_types": json.dumps(dict(agent_types.most_common(5))),
        "agent_ids_json": json.dumps(agent_ids[:100]),  # max 100 i index
        "computed_at": now,
    }

def upsert_index(conn, data: dict):
    conn.execute("""
        INSERT INTO agent_activity_index
        (entity_type, entity_id, entity_name, entity_symbol,
         total_agents, identified_ai_agents, ai_agent_ratio,
         ai_controlled_tvl_usd, total_tvl_usd, ai_tvl_ratio,
         avg_agent_confidence, top_agent_types, agent_ids_json, computed_at)
        VALUES (:entity_type, :entity_id, :entity_name, :entity_symbol,
                :total_agents, :identified_ai_agents, :ai_agent_ratio,
                :ai_controlled_tvl_usd, :total_tvl_usd, :ai_tvl_ratio,
                :avg_agent_confidence, :top_agent_types, :agent_ids_json, :computed_at)
        ON CONFLICT(entity_type, entity_id) DO UPDATE SET
            entity_name=excluded.entity_name,
            entity_symbol=excluded.entity_symbol,
            total_agents=excluded.total_agents,
            identified_ai_agents=excluded.identified_ai_agents,
            ai_agent_ratio=excluded.ai_agent_ratio,
            ai_controlled_tvl_usd=excluded.ai_controlled_tvl_usd,
            total_tvl_usd=excluded.total_tvl_usd,
            ai_tvl_ratio=excluded.ai_tvl_ratio,
            avg_agent_confidence=excluded.avg_agent_confidence,
            top_agent_types=excluded.top_agent_types,
            agent_ids_json=excluded.agent_ids_json,
            computed_at=excluded.computed_at
    """, data)

def compute_all_indexes():
    """
    Beräknar Agent Activity Index för alla unika entities i agent_crypto_relations.
    Kör också chain-level index från agent_crypto_profile.
    """
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()

    # Hämta alla unika (relation_type, entity_id) från relations-tabellen
    entities = conn.execute("""
        SELECT DISTINCT relation_type as entity_type, entity_id, entity_name, entity_symbol
        FROM agent_crypto_relations
        WHERE entity_id IS NOT NULL AND entity_id != ''
        ORDER BY relation_type, entity_id
    """).fetchall()

    log.info(f"Beräknar index för {len(entities)} entities...")
    saved = 0

    for e in entities:
        try:
            data = compute_index_for_entity(conn, e["entity_type"], e["entity_id"])
            if data:
                if e["entity_name"]:
                    data["entity_name"] = e["entity_name"]
                if e["entity_symbol"]:
                    data["entity_symbol"] = e["entity_symbol"]
                upsert_index(conn, data)
                saved += 1
        except Exception as ex:
            log.warning(f"Fel för {e['entity_type']}/{e['entity_id']}: {ex}")

    # Chain-level index från agent_crypto_profile
    chains = conn.execute("""
        SELECT LOWER(chain) as chain, COUNT(*) as n
        FROM agent_crypto_profile
        WHERE chain IS NOT NULL AND chain != ''
        GROUP BY LOWER(chain)
        HAVING n >= 5
    """).fetchall()

    for c in chains:
        try:
            data = compute_index_for_entity(conn, "chain", c["chain"])
            if data:
                upsert_index(conn, data)
                saved += 1
        except Exception as ex:
            log.warning(f"Fel för chain/{c['chain']}: {ex}")

    conn.commit()
    conn.close()
    log.info(f"Agent Activity Index klar: {saved} entities indexerade")
    return saved

def get_summary_stats() -> dict:
    """Sammanfattning för rapport och API."""
    conn = get_conn()

    total_agents = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile").fetchone()[0]
    ai_agents = conn.execute("SELECT COUNT(*) FROM wallet_behavior WHERE is_ai_agent=1").fetchone()[0]
    analyzed_wallets = conn.execute("SELECT COUNT(*) FROM wallet_behavior").fetchone()[0]

    top_entities = conn.execute("""
        SELECT entity_type, entity_id, entity_name, total_agents,
               identified_ai_agents, ai_agent_ratio, ai_tvl_ratio
        FROM agent_activity_index
        ORDER BY identified_ai_agents DESC
        LIMIT 20
    """).fetchall()

    chain_breakdown = conn.execute("""
        SELECT chain, COUNT(*) as n
        FROM agent_crypto_profile
        GROUP BY chain ORDER BY n DESC LIMIT 10
    """).fetchall()

    type_breakdown = conn.execute("""
        SELECT agent_type, COUNT(*) as n
        FROM wallet_behavior
        WHERE is_ai_agent=1
        GROUP BY agent_type ORDER BY n DESC
    """).fetchall()

    conn.close()

    return {
        "total_agents_indexed": total_agents,
        "wallets_analyzed": analyzed_wallets,
        "identified_ai_agents": ai_agents,
        "ai_detection_rate": round(ai_agents / analyzed_wallets, 3) if analyzed_wallets > 0 else 0,
        "top_entities_by_ai_agents": [dict(r) for r in top_entities],
        "chain_breakdown": {r["chain"]: r["n"] for r in chain_breakdown},
        "ai_agent_type_breakdown": {r["agent_type"]: r["n"] for r in type_breakdown},
    }

if __name__ == "__main__":
    count = compute_all_indexes()
    stats = get_summary_stats()
    print(f"\n=== Agent Activity Index ===")
    print(f"Indexerade entities: {count}")
    print(f"Totala agenter: {stats['total_agents_indexed']}")
    print(f"Identifierade AI-agenter: {stats['identified_ai_agents']}")
    print(f"\nTop entities:")
    for e in stats["top_entities_by_ai_agents"][:10]:
        print(f"  {e['entity_type']}/{e['entity_id']}: {e['identified_ai_agents']} AI-agenter ({e['ai_agent_ratio']*100:.1f}%)")
