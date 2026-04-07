"""
LobeHub Crawler — fetches chat agents from chat-agents.lobehub.com
Source: https://chat-agents.lobehub.com/index.json
Stores into agent_crypto_profile table (source='lobehub').
"""
import requests, sqlite3, json
from datetime import datetime, timezone

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
API_URL = "https://chat-agents.lobehub.com/index.json"


def fetch_agents():
    r = requests.get(API_URL, timeout=60)
    r.raise_for_status()
    data = r.json()
    agents = data.get("agents", [])
    print(f"Fetched {len(agents)} agents from LobeHub")
    return agents


def save_agents(agents):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for a in agents:
        identifier = a.get("identifier", "")
        if not identifier:
            continue
        agent_id = f"lobehub-{identifier}"
        meta = a.get("meta", {})
        name = meta.get("title", identifier)
        desc = meta.get("description", "")
        category = meta.get("category", "")
        tags = meta.get("tags", [])
        author = a.get("author", "")
        homepage = a.get("homepage", "")
        created = a.get("createdAt", "")

        try:
            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, description, chain,
                 creator_address, agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'lobehub', ?, ?, 'lobehub', ?, 'agent', ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    description=excluded.description,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                agent_id,
                name,
                desc[:2000],
                author,
                json.dumps({
                    "identifier": identifier,
                    "author": author,
                    "homepage": homepage,
                    "category": category,
                    "tags": tags,
                    "avatar": meta.get("avatar", ""),
                    "created_at": created,
                    "token_usage": a.get("tokenUsage", 0),
                    "plugin_count": a.get("pluginCount", 0),
                    "knowledge_count": a.get("knowledgeCount", 0),
                    "schema_version": a.get("schemaVersion"),
                }),
                now, now
            ))
            saved += 1
        except Exception as e:
            print(f"  Error saving {name}: {e}")
    conn.commit()
    conn.close()
    return saved


def run():
    print("=== LobeHub Crawler ===")
    agents = fetch_agents()
    saved = save_agents(agents)
    print(f"Saved: {saved} agents")

    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='lobehub'").fetchone()[0]
    conn.close()
    print(f"LobeHub total in DB: {total}")


if __name__ == "__main__":
    run()
