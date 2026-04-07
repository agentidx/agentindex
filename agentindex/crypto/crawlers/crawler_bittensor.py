import os, requests, sqlite3, json, time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/Users/anstudio/agentindex/.env")
DB_PATH = "/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
KEY = os.getenv("TAOSTATS_API_KEY")
HEADERS = {"Authorization": KEY, "Accept": "application/json"}
BASE = "https://api.taostats.io/api"

def fetch_subnets():
    all_subnets = []
    page = 1
    while True:
        r = requests.get(f"{BASE}/subnet/latest/v1?limit=100&page={page}", headers=HEADERS, timeout=15)
        d = r.json()
        items = d.get("data", [])
        if not items:
            break
        all_subnets.extend(items)
        total_pages = d.get("pagination", {}).get("total_pages", 1)
        print(f"  Subnets sida {page}/{total_pages}: {len(items)}")
        page += 1
        if page > total_pages:
            break
        time.sleep(0.3)
    return all_subnets

def fetch_neurons(netuid, limit=100):
    """Hämtar neurons (miners+validators) för ett subnet"""
    all_neurons = []
    page = 1
    while True:
        r = requests.get(f"{BASE}/neuron/latest/v1?netuid={netuid}&limit={limit}&page={page}", 
                        headers=HEADERS, timeout=15)
        if r.status_code != 200:
            break
        d = r.json()
        items = d.get("data", [])
        if not items:
            break
        all_neurons.extend(items)
        total_pages = d.get("pagination", {}).get("total_pages", 1)
        page += 1
        if page > total_pages or page > 5:  # max 500 neurons per subnet
            break
        time.sleep(0.2)
    return all_neurons

def save_subnets(subnets):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for s in subnets:
        try:
            netuid = s.get("netuid")
            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, description, chain,
                 token_symbol, staked_value_usd, creator_address,
                 agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'bittensor', ?, ?, 'bittensor', 'TAO', ?, ?, 'subnet', ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    agent_name=excluded.agent_name,
                    staked_value_usd=excluded.staked_value_usd,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                f"bittensor-subnet-{netuid}",
                s.get("subnet_name") or f"Subnet {netuid}",
                s.get("description") or s.get("github") or "",
                s.get("emission", 0),
                s.get("owner", {}).get("ss58") if isinstance(s.get("owner"), dict) else str(s.get("owner","")),
                json.dumps({
                    "netuid": netuid,
                    "emission": s.get("emission"),
                    "tempo": s.get("tempo"),
                    "max_n": s.get("max_n"),
                    "active_keys": s.get("active_keys"),
                    "github": s.get("github"),
                }),
                now, now
            ))
            saved += 1
        except Exception as e:
            print(f"  DB-fel subnet: {e}")
    conn.commit()
    conn.close()
    return saved

def save_neurons(neurons, netuid):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for n in neurons:
        try:
            hotkey = n.get("hotkey", {})
            hotkey_ss58 = hotkey.get("ss58") if isinstance(hotkey, dict) else str(hotkey)
            conn.execute("""
                INSERT INTO agent_crypto_profile
                (agent_id, source, agent_name, chain,
                 token_symbol, staked_value_usd, creator_address,
                 agent_type, metadata_json, first_seen_at, last_updated_at)
                VALUES (?, 'bittensor', ?, 'bittensor', 'TAO', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id, source) DO UPDATE SET
                    staked_value_usd=excluded.staked_value_usd,
                    metadata_json=excluded.metadata_json,
                    last_updated_at=excluded.last_updated_at
            """, (
                f"bittensor-neuron-{netuid}-{hotkey_ss58}",
                f"Neuron {n.get('uid')} (subnet {netuid})",
                n.get("stake", 0),
                hotkey_ss58,
                "validator" if n.get("validator_trust", 0) > 0 else "miner",
                json.dumps({
                    "netuid": netuid,
                    "uid": n.get("uid"),
                    "stake": n.get("stake"),
                    "trust": n.get("trust"),
                    "validator_trust": n.get("validator_trust"),
                    "emission": n.get("emission"),
                    "active": n.get("active"),
                }),
                now, now
            ))
            saved += 1
        except Exception as e:
            print(f"  DB-fel neuron: {e}")
    conn.commit()
    conn.close()
    return saved

def run():
    print("=== Bittensor Crawler ===")
    
    # 1. Hämta alla subnets
    print("Hämtar subnets...")
    subnets = fetch_subnets()
    print(f"Totalt subnets: {len(subnets)}")
    saved_s = save_subnets(subnets)
    print(f"Sparade subnets: {saved_s}")
    
    # 2. Hämta neurons för top-20 subnets (mest emission)
    top_subnets = sorted(subnets, key=lambda x: x.get("emission", 0), reverse=True)[:20]
    print(f"\nHämtar neurons för top-20 subnets...")
    total_neurons = 0
    for s in top_subnets:
        netuid = s.get("netuid")
        name = s.get("subnet_name") or f"Subnet {netuid}"
        neurons = fetch_neurons(netuid)
        if neurons:
            saved_n = save_neurons(neurons, netuid)
            total_neurons += saved_n
            print(f"  {name} (netuid={netuid}): {saved_n} neurons")
    
    print(f"\nTotalt neurons sparade: {total_neurons}")
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM agent_crypto_profile WHERE source='bittensor'").fetchone()[0]
    conn.close()
    print(f"Bittensor totalt i DB: {total}")

if __name__ == "__main__":
    run()
