"""
OpenRouter Crawler — fetches AI models from openrouter.ai
Source: https://openrouter.ai/api/v1/models
Stores into agent_crypto_profile table (source='openrouter').
"""
import requests, sqlite3, json
from datetime import datetime, timezone

DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
API_URL = "https://openrouter.ai/api/v1/models"


def fetch_models():
    r = requests.get(API_URL, timeout=30)
    r.raise_for_status()
    data = r.json()
    models = data.get("data", [])
    print(f"Fetched {len(models)} models from OpenRouter")
    return models


def save_models(models):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for m in models:
        model_id = m.get("id", "")
        if not model_id:
            continue
        agent_id = f"openrouter-{model_id.replace('/', '-')}"
        name = m.get("name", model_id)
        desc = m.get("description", "")
        arch = m.get("architecture", {})
        pricing = m.get("pricing", {})
        ctx = m.get("context_length", 0)

        try:
            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, description, chain,
                 creator_address, agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'openrouter', ?, ?, 'openrouter', ?, 'model', ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    description=excluded.description,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                agent_id,
                name,
                desc[:2000],
                model_id.split("/")[0] if "/" in model_id else "",
                json.dumps({
                    "model_id": model_id,
                    "context_length": ctx,
                    "architecture": arch,
                    "pricing": pricing,
                    "supported_parameters": m.get("supported_parameters", []),
                    "top_provider": m.get("top_provider", {}),
                    "created": m.get("created"),
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
    print("=== OpenRouter Crawler ===")
    models = fetch_models()
    saved = save_models(models)
    print(f"Saved: {saved} models")

    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='openrouter'").fetchone()[0]
    conn.close()
    print(f"OpenRouter total in DB: {total}")


if __name__ == "__main__":
    run()
