"""
Agent Intelligence Scheduler
=============================
Kör alla Sprint 7 analyser autonomt på schema.
Startas via LaunchAgent com.zarq.agent-intelligence.

Schema:
- Dagligen 04:00 UTC: WOW-analys (risk/crash/collapse) + protocol snapshot
- Måndagar 02:00 UTC: Wallet behavior-analys (Etherscan, tar ~15 min)
- Måndagar 03:00 UTC: Agent Activity Index
"""
import sys, logging, sqlite3
from datetime import datetime, timezone

sys.path.insert(0, '/Users/anstudio/agentindex')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/Users/anstudio/agentindex/logs/agent_intelligence.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"

def run_daily():
    """Körs dagligen 04:00 UTC."""
    log.info("=== Agent Intelligence: Daglig körning ===")
    now = datetime.now(timezone.utc)

    # WOW-analys
    try:
        from agentindex.crypto.agent_wow_analysis import run as run_wow
        stats = run_wow()
        collapse_count = len(stats.get("structural_collapse_agents", []))
        crash_mcap = stats.get("crash_exposure", {}).get("mcap_at_risk", 0)
        log.info(f"WOW-analys klar: {collapse_count} collapse-agenter, ${crash_mcap/1e6:.1f}M kraschexponering")
    except Exception as e:
        log.error(f"WOW-analys fel: {e}")

    # Protocol snapshot (Tier 2 exodus-data)
    try:
        from agentindex.crypto.agent_wow_analysis import get_conn, take_protocol_snapshot
        conn = get_conn()
        n = take_protocol_snapshot(conn)
        conn.close()
        log.info(f"Protocol snapshot: {n} protokoll")
    except Exception as e:
        log.error(f"Protocol snapshot fel: {e}")

    log.info("=== Daglig körning klar ===")

def run_weekly():
    """Körs måndagar. Tyngre analyser."""
    log.info("=== Agent Intelligence: Veckovis körning ===")

    # Wallet behavior (Etherscan, långsam)
    try:
        from agentindex.crypto.wallet_behavior import run_batch_analysis
        analyzed, ai_found = run_batch_analysis(limit=500)
        log.info(f"Wallet behavior: {analyzed} analyserade, {ai_found} AI-agenter")
    except Exception as e:
        log.error(f"Wallet behavior fel: {e}")

    # Agent Activity Index
    try:
        from agentindex.crypto.agent_activity_index import get_conn, compute_index_for_entity, upsert_index
        conn = get_conn()
        entities = conn.execute("""
            SELECT relation_type as entity_type, entity_id, entity_name, entity_symbol,
                   COUNT(*) as n
            FROM agent_crypto_relations
            GROUP BY relation_type, entity_id
            ORDER BY n DESC LIMIT 500
        """).fetchall()
        saved = 0
        for e in entities:
            data = compute_index_for_entity(conn, e[0], e[1])
            if data:
                if e[2]: data['entity_name'] = e[2]
                if e[3]: data['entity_symbol'] = e[3]
                upsert_index(conn, data)
                saved += 1
        conn.commit()
        conn.close()
        log.info(f"Activity Index: {saved} entities uppdaterade")
    except Exception as e:
        log.error(f"Activity Index fel: {e}")

    # WOW-analys efter wallet-uppdatering
    run_daily()

    log.info("=== Veckovis körning klar ===")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    args = parser.parse_args()

    if args.mode == "weekly":
        run_weekly()
    else:
        run_daily()
