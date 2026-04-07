"""
ERC-8004 Crawler — fetches on-chain agents from 8004scan.io
Source: https://www.8004scan.io/api/v1/agents
Stores into agent_crypto_profile table (source='erc8004').
88K+ agents across BSC, Ethereum, Base chains.
"""
import requests, sqlite3, json, time
from datetime import datetime, timezone

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
API_URL = "https://www.8004scan.io/api/v1/agents"
PAGE_SIZE = 100


def fetch_agents():
    all_agents = []
    offset = 0
    total = None

    while True:
        try:
            r = requests.get(API_URL, params={"limit": PAGE_SIZE, "offset": offset}, timeout=30)
            r.raise_for_status()
        except Exception as e:
            print(f"  Request error at offset {offset}: {e}")
            break

        d = r.json()
        batch = d.get("items", [])
        if total is None:
            total = d.get("total", 0)
            print(f"  Total agents in registry: {total}")

        if not batch:
            break

        all_agents.extend(batch)
        offset += PAGE_SIZE
        if offset >= total:
            break
        if len(all_agents) % 5000 == 0:
            print(f"  Fetched {len(all_agents)}/{total}...")
        time.sleep(0.2)

    print(f"Fetched {len(all_agents)} agents from ERC-8004")
    return all_agents


def save_agents(agents):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for a in agents:
        agent_id_raw = a.get("agent_id", "")
        if not agent_id_raw:
            continue
        agent_id = f"erc8004-{agent_id_raw}"
        name = a.get("name", "")
        desc = a.get("description", "")
        owner = a.get("owner_address", "")
        chain_id = a.get("chain_id", 0)
        chain_map = {1: "ethereum", 56: "bsc", 8453: "base"}
        chain = chain_map.get(chain_id, f"evm-{chain_id}")

        try:
            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, description, chain,
                 creator_address, agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'erc8004', ?, ?, ?, ?, 'agent', ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    description=excluded.description,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                agent_id,
                name,
                desc[:2000],
                chain,
                owner,
                json.dumps({
                    "agent_id": agent_id_raw,
                    "token_id": a.get("token_id"),
                    "chain_id": chain_id,
                    "contract_address": a.get("contract_address"),
                    "agent_wallet": a.get("agent_wallet"),
                    "is_verified": a.get("is_verified"),
                    "x402_supported": a.get("x402_supported"),
                    "mcp_server": a.get("mcp_server"),
                    "a2a_endpoint": a.get("a2a_endpoint"),
                    "total_score": a.get("total_score"),
                    "quality_score": a.get("quality_score"),
                    "health_score": a.get("health_score"),
                    "star_count": a.get("star_count"),
                    "supported_trust_models": a.get("supported_trust_models"),
                    "created_tx_hash": a.get("created_tx_hash"),
                    "image_url": a.get("image_url"),
                }),
                now, now
            ))
            saved += 1
        except Exception as e:
            pass
    conn.commit()
    conn.close()
    return saved


def run():
    print("=== ERC-8004 Crawler ===")
    agents = fetch_agents()
    saved = save_agents(agents)
    print(f"Saved: {saved} agents")

    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='erc8004'").fetchone()[0]
    conn.close()
    print(f"ERC-8004 total in DB: {total}")


if __name__ == "__main__":
    run()
