#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 1 Enrichment Crawler
Enriches existing data + adds new entity types using FREE APIs only.

Includes:
1. Bridge volume enrichment (DeFiLlama free)
2. DEX volumes (DeFiLlama free)
3. Fees & Revenue (DeFiLlama free)
4. Perps & Options volumes (DeFiLlama free)
5. CMC Tags & metadata (CMC free tier)
6. Protocol oracle mapping (from DeFiLlama protocol data)

Usage: python3 crypto_sprint1_enrichment.py
"""

import json
import sqlite3
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ============================================================
# CONFIG
# ============================================================

CRYPTO_DB_PATH = None  # Auto-detect

def get_db_path():
    global CRYPTO_DB_PATH
    if CRYPTO_DB_PATH:
        return CRYPTO_DB_PATH
    import os
    paths = [
        os.path.expanduser("~/agentindex/agentindex/data/crypto_trust.db"),
        os.path.join(os.path.dirname(__file__), "..", "data", "crypto_trust.db"),
    ]
    for p in paths:
        if os.path.exists(p):
            CRYPTO_DB_PATH = p
            return p
    # Create default
    CRYPTO_DB_PATH = paths[0]
    os.makedirs(os.path.dirname(CRYPTO_DB_PATH), exist_ok=True)
    return CRYPTO_DB_PATH

def get_db():
    return sqlite3.connect(get_db_path(), timeout=30)

DEFILLAMA_BASE = "https://api.llama.fi"
DEFILLAMA_BRIDGE = "https://bridges.llama.fi"
CMC_BASE = "https://pro-api.coinmarketcap.com"
CMC_API_KEY = ""  # Set if you have one

HEADERS = {"User-Agent": "NerqCrawler/1.0", "Accept": "application/json"}

def api_get(url, headers=None):
    """Simple GET request with error handling."""
    h = dict(HEADERS)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"   ⚠️  HTTP {e.code} for {url}")
        return None
    except Exception as e:
        print(f"   ⚠️  Error: {e} for {url}")
        return None


# ============================================================
# INIT TABLES
# ============================================================

def init_tables():
    conn = get_db()
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_dex_volumes (
            id TEXT PRIMARY KEY,
            name TEXT,
            chains TEXT,
            volume_24h REAL,
            volume_7d REAL,
            volume_30d REAL,
            change_1d REAL,
            change_7d REAL,
            change_1m REAL,
            category TEXT,
            crawled_at TEXT
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_fees_revenue (
            protocol_id TEXT PRIMARY KEY,
            name TEXT,
            daily_fees REAL,
            daily_revenue REAL,
            daily_holders_revenue REAL,
            fees_30d REAL,
            revenue_30d REAL,
            change_1d REAL,
            change_7d REAL,
            change_1m REAL,
            category TEXT,
            chains TEXT,
            crawled_at TEXT
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_oracles (
            id TEXT PRIMARY KEY,
            name TEXT,
            tvs_usd REAL,
            num_protocols INTEGER,
            num_chains INTEGER,
            chains TEXT,
            protocols TEXT,
            crawled_at TEXT,
            total_score REAL,
            grade TEXT,
            scored_at TEXT
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_protocol_oracle (
            protocol_id TEXT,
            oracle_id TEXT,
            oracle_role TEXT DEFAULT 'primary',
            PRIMARY KEY (protocol_id, oracle_id)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_hack_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            protocol_name TEXT,
            date TEXT,
            amount_usd REAL,
            root_cause TEXT,
            technique TEXT,
            chain TEXT,
            recovered_usd REAL,
            audit_before_hack TEXT,
            source TEXT,
            crawled_at TEXT
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_token_tags (
            token_id TEXT PRIMARY KEY,
            cmc_id INTEGER,
            tags TEXT,
            platform TEXT,
            description TEXT,
            website TEXT,
            technical_doc TEXT,
            is_audited BOOLEAN,
            crawled_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Sprint 1 tables initialized")


# ============================================================
# 1. BRIDGE ENRICHMENT — Volume per bridge
# ============================================================

def crawl_bridge_volumes():
    print("\n🌉 ENRICHING BRIDGE VOLUMES")
    
    # Get bridge list with IDs
    data = api_get(f"{DEFILLAMA_BRIDGE}/bridges?includeChains=true")
    if not data or "bridges" not in data:
        print("   ⚠️  Failed to fetch bridges")
        return 0
    
    bridges = data["bridges"]
    print(f"   Found {len(bridges)} bridges with IDs")
    
    conn = get_db()
    updated = 0
    
    for b in bridges:
        bridge_id = b.get("id")
        name = b.get("displayName") or b.get("name", "")
        volume_prev_day = b.get("lastDailyVolume")
        volume_prev_month = b.get("monthlyVolume")
        dest_chains = b.get("destinationChain")
        chains = b.get("chains", [])
        
        # Try to match with existing bridge in our DB
        slug = name.lower().replace(" ", "-").replace(".", "-")
        
        # Update existing bridge or insert volume data
        try:
            conn.execute("""
                UPDATE crypto_bridges SET 
                    volume_24h = COALESCE(?, volume_24h),
                    num_chains = COALESCE(?, num_chains),
                    destination_chains = COALESCE(?, destination_chains),
                    source_chains = COALESCE(?, source_chains)
                WHERE LOWER(name) LIKE ?
            """, (
                volume_prev_day,
                len(chains) if chains else None,
                json.dumps(chains) if chains else None,
                json.dumps(chains) if chains else None,
                f"%{name.lower().split(' ')[0]}%"
            ))
            if conn.total_changes > updated:
                updated += 1
        except Exception:
            pass
    
    conn.commit()
    conn.close()
    print(f"✅ Bridges enriched: {updated} with volume data")
    
    # Show top bridges by volume
    if bridges:
        sorted_b = sorted(bridges, key=lambda x: x.get("lastDailyVolume") or 0, reverse=True)
        print("   Top 10 by daily volume:")
        for b in sorted_b[:10]:
            vol = b.get("lastDailyVolume") or 0
            name = b.get("displayName") or b.get("name", "")
            print(f"      {name:30s}  ${vol/1e6:,.1f}M/day")
    
    return updated


# ============================================================
# 2. DEX VOLUMES
# ============================================================

def crawl_dex_volumes():
    print("\n📊 CRAWLING DEX VOLUMES")
    
    data = api_get(f"{DEFILLAMA_BASE}/overview/dexs")
    if not data or "protocols" not in data:
        print("   ⚠️  Failed to fetch DEX data")
        return 0
    
    dexes = data["protocols"]
    now = datetime.now(timezone.utc).isoformat()
    print(f"   Received {len(dexes)} DEXes")
    
    conn = get_db()
    count = 0
    
    for d in dexes:
        dex_id = d.get("defillamaId") or d.get("module") or d.get("name", "").lower().replace(" ", "-")
        name = d.get("name", "")
        chains = d.get("chains", [])
        vol_24h = d.get("total24h")
        vol_7d = d.get("total7d")
        vol_30d = d.get("total30d")
        change_1d = d.get("change_1d")
        change_7d = d.get("change_7d")
        change_1m = d.get("change_1m")
        
        conn.execute("""
            INSERT OR REPLACE INTO crypto_dex_volumes 
            (id, name, chains, volume_24h, volume_7d, volume_30d,
             change_1d, change_7d, change_1m, category, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(dex_id), name, json.dumps(chains),
            vol_24h, vol_7d, vol_30d,
            change_1d, change_7d, change_1m,
            "DEX", now
        ))
        count += 1
    
    conn.commit()
    conn.close()
    
    print(f"✅ DEX volumes crawled: {count}")
    
    # Top 10
    sorted_d = sorted(dexes, key=lambda x: x.get("total24h") or 0, reverse=True)
    print("   Top 10 by 24h volume:")
    for d in sorted_d[:10]:
        vol = d.get("total24h") or 0
        print(f"      {d['name']:30s}  ${vol/1e6:,.1f}M/day")
    
    return count


# ============================================================
# 3. FEES & REVENUE
# ============================================================

def crawl_fees_revenue():
    print("\n💰 CRAWLING FEES & REVENUE")
    
    data = api_get(f"{DEFILLAMA_BASE}/overview/fees")
    if not data or "protocols" not in data:
        print("   ⚠️  Failed to fetch fees data")
        return 0
    
    protocols = data["protocols"]
    now = datetime.now(timezone.utc).isoformat()
    print(f"   Received {len(protocols)} protocols with fee data")
    
    conn = get_db()
    count = 0
    
    for p in protocols:
        pid = p.get("defillamaId") or p.get("module") or p.get("name", "").lower().replace(" ", "-")
        name = p.get("name", "")
        daily_fees = p.get("total24h")
        daily_revenue = p.get("revenue24h") or p.get("totalRevenue24h")
        daily_holders_rev = p.get("dailyHoldersRevenue")
        fees_30d = p.get("total30d")
        revenue_30d = p.get("totalRevenue30d")
        change_1d = p.get("change_1d")
        change_7d = p.get("change_7d")
        change_1m = p.get("change_1m")
        category = p.get("category", "")
        chains = p.get("chains", [])
        
        conn.execute("""
            INSERT OR REPLACE INTO crypto_fees_revenue 
            (protocol_id, name, daily_fees, daily_revenue, daily_holders_revenue,
             fees_30d, revenue_30d, change_1d, change_7d, change_1m,
             category, chains, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(pid), name, daily_fees, daily_revenue, daily_holders_rev,
            fees_30d, revenue_30d, change_1d, change_7d, change_1m,
            category, json.dumps(chains), now
        ))
        count += 1
    
    conn.commit()
    conn.close()
    
    print(f"✅ Fees & revenue crawled: {count}")
    
    sorted_p = sorted(protocols, key=lambda x: x.get("total24h") or 0, reverse=True)
    print("   Top 10 by daily fees:")
    for p in sorted_p[:10]:
        fees = p.get("total24h") or 0
        rev = p.get("revenue24h") or p.get("totalRevenue24h") or 0
        print(f"      {p['name']:30s}  fees: ${fees/1e6:,.1f}M  rev: ${rev/1e6:,.1f}M")
    
    return count


# ============================================================
# 4. PERPS & OPTIONS
# ============================================================

def crawl_perps_options():
    print("\n📈 CRAWLING PERPS & OPTIONS VOLUMES")
    
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    total = 0
    
    for category, endpoint in [("Perps", "overview/dexs?type=perps"), ("Options", "overview/options")]:
        # Try the correct endpoint format
        if category == "Perps":
            # DeFiLlama uses /overview/dexs for perps too, but separate endpoint
            url = f"{DEFILLAMA_BASE}/overview/dexs"
        else:
            url = f"{DEFILLAMA_BASE}/overview/options"
        
        data = api_get(url)
        if not data or "protocols" not in data:
            print(f"   ⚠️  Failed to fetch {category}")
            continue
        
        protocols = data["protocols"]
        # Filter by category if mixed
        if category == "Perps":
            protocols = [p for p in protocols if "perpetual" in (p.get("category", "") or "").lower() 
                        or "derivative" in (p.get("category", "") or "").lower()]
        
        count = 0
        for d in protocols:
            dex_id = d.get("defillamaId") or d.get("module") or d.get("name", "").lower().replace(" ", "-")
            name = d.get("name", "")
            
            conn.execute("""
                INSERT OR REPLACE INTO crypto_dex_volumes 
                (id, name, chains, volume_24h, volume_7d, volume_30d,
                 change_1d, change_7d, change_1m, category, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"{category.lower()}_{dex_id}", name, json.dumps(d.get("chains", [])),
                d.get("total24h"), d.get("total7d"), d.get("total30d"),
                d.get("change_1d"), d.get("change_7d"), d.get("change_1m"),
                category, now
            ))
            count += 1
        
        print(f"   {category}: {count} protocols")
        total += count
    
    conn.commit()
    conn.close()
    print(f"✅ Perps & Options crawled: {total}")
    return total


# ============================================================
# 5. ORACLE MAPPING (from DeFiLlama protocol data)
# ============================================================

def crawl_oracle_mapping():
    print("\n🔮 MAPPING ORACLE DEPENDENCIES")
    
    # Get all protocols — many have 'oracles' field
    data = api_get(f"{DEFILLAMA_BASE}/protocols")
    if not data:
        print("   ⚠️  Failed to fetch protocols")
        return 0
    
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    
    oracle_stats = {}  # oracle_name -> {protocols: [], chains: set(), tvl: 0}
    mapping_count = 0
    
    for p in data:
        oracles = p.get("oracles", [])
        if not oracles:
            continue
        
        protocol_name = p.get("name", "")
        protocol_slug = p.get("slug", protocol_name.lower().replace(" ", "-"))
        protocol_tvl = p.get("tvl") or 0
        protocol_chains = p.get("chains", [])
        
        for oracle_name in oracles:
            oracle_id = oracle_name.lower().replace(" ", "-")
            
            if oracle_id not in oracle_stats:
                oracle_stats[oracle_id] = {
                    "name": oracle_name,
                    "protocols": [],
                    "chains": set(),
                    "tvl": 0
                }
            
            oracle_stats[oracle_id]["protocols"].append(protocol_name)
            oracle_stats[oracle_id]["chains"].update(protocol_chains)
            oracle_stats[oracle_id]["tvl"] += protocol_tvl
            
            # Save mapping
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO crypto_protocol_oracle 
                    (protocol_id, oracle_id, oracle_role)
                    VALUES (?, ?, ?)
                """, (protocol_slug, oracle_id, "primary"))
                mapping_count += 1
            except Exception:
                pass
    
    # Save oracle summary
    for oracle_id, stats in oracle_stats.items():
        conn.execute("""
            INSERT OR REPLACE INTO crypto_oracles 
            (id, name, tvs_usd, num_protocols, num_chains, chains, protocols, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            oracle_id,
            stats["name"],
            stats["tvl"],
            len(stats["protocols"]),
            len(stats["chains"]),
            json.dumps(sorted(stats["chains"])),
            json.dumps(stats["protocols"][:100]),  # Top 100 protocols
            now
        ))
    
    conn.commit()
    conn.close()
    
    print(f"✅ Oracles mapped: {len(oracle_stats)}")
    print(f"   Protocol→Oracle mappings: {mapping_count}")
    
    # Top oracles by TVS
    sorted_o = sorted(oracle_stats.items(), key=lambda x: x[1]["tvl"], reverse=True)
    print("   Top 10 oracles by TVS:")
    for oid, stats in sorted_o[:10]:
        tvs = stats["tvl"]
        print(f"      {stats['name']:25s}  TVS: ${tvs/1e9:,.1f}B  protocols: {len(stats['protocols']):,}  chains: {len(stats['chains'])}")
    
    return len(oracle_stats)


# ============================================================
# 6. HACK ROOT CAUSE ANALYSIS (from DeFiLlama protocol hacks field)
# ============================================================

def crawl_hack_analysis():
    print("\n🔓 ANALYZING HACK ROOT CAUSES")
    
    # Get DeFi protocols with hack history
    conn = get_db()
    cursor = conn.execute("SELECT id, name, hack_history FROM crypto_defi_protocols WHERE hack_history IS NOT NULL AND hack_history != '[]'")
    rows = cursor.fetchall()
    
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    root_causes = {}
    
    for row in rows:
        protocol_id, name, hack_json = row
        try:
            hacks = json.loads(hack_json) if hack_json else []
        except:
            continue
        
        for hack in hacks:
            if isinstance(hack, str):
                continue
            date = hack.get("date", "")
            amount = hack.get("amount") or hack.get("amountUsd") or 0
            technique = hack.get("technique") or hack.get("classification") or "unknown"
            chain = hack.get("chain") or hack.get("chains") or ""
            if isinstance(chain, list):
                chain = ", ".join(chain)
            
            # Classify root cause
            technique_lower = str(technique).lower()
            if "rug" in technique_lower or "exit scam" in technique_lower:
                root_cause = "rug_pull"
            elif "flash" in technique_lower:
                root_cause = "flash_loan"
            elif "oracle" in technique_lower or "price manipulation" in technique_lower:
                root_cause = "oracle_manipulation"
            elif "bridge" in technique_lower:
                root_cause = "bridge_exploit"
            elif "key" in technique_lower or "phish" in technique_lower or "social" in technique_lower:
                root_cause = "private_key_compromise"
            elif "governance" in technique_lower or "vote" in technique_lower:
                root_cause = "governance_attack"
            elif "bug" in technique_lower or "exploit" in technique_lower or "reentrancy" in technique_lower:
                root_cause = "smart_contract_bug"
            else:
                root_cause = "other"
            
            root_causes[root_cause] = root_causes.get(root_cause, 0) + 1
            
            conn.execute("""
                INSERT INTO crypto_hack_analysis 
                (protocol_name, date, amount_usd, root_cause, technique, chain, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, date, amount, root_cause, technique, chain, now))
            count += 1
    
    conn.commit()
    conn.close()
    
    print(f"✅ Hack analysis: {count} incidents classified")
    print("   Root cause distribution:")
    for cause, cnt in sorted(root_causes.items(), key=lambda x: -x[1]):
        print(f"      {cause:30s}  {cnt:,}")
    
    return count


# ============================================================
# MAIN
# ============================================================

def main():
    start = time.time()
    
    print("=" * 60)
    print("  NERQ CRYPTO — SPRINT 1 ENRICHMENT")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print("  All free APIs — no paid keys required")
    print("=" * 60)
    
    init_tables()
    
    results = {}
    
    # 1. Bridge volumes
    results["bridge_volumes"] = crawl_bridge_volumes()
    time.sleep(0.5)
    
    # 2. DEX volumes
    results["dex_volumes"] = crawl_dex_volumes()
    time.sleep(0.5)
    
    # 3. Fees & Revenue
    results["fees_revenue"] = crawl_fees_revenue()
    time.sleep(0.5)
    
    # 4. Perps & Options
    results["perps_options"] = crawl_perps_options()
    time.sleep(0.5)
    
    # 5. Oracle mapping
    results["oracles"] = crawl_oracle_mapping()
    time.sleep(0.5)
    
    # 6. Hack analysis
    results["hack_analysis"] = crawl_hack_analysis()
    
    elapsed = time.time() - start
    
    # Summary
    print("\n" + "=" * 60)
    print("  SPRINT 1 ENRICHMENT COMPLETE")
    print("=" * 60)
    for key, val in results.items():
        print(f"   {key:25s}  {val:,}")
    print(f"\n   ⏱️  Total time: {elapsed:.1f} seconds")
    
    # Grand total
    conn = get_db()
    totals = {}
    for table in ["crypto_tokens", "crypto_exchanges", "crypto_defi_protocols", 
                   "crypto_smart_contracts", "crypto_bridges", "crypto_stablecoins",
                   "crypto_chains", "crypto_dex_volumes", "crypto_fees_revenue",
                   "crypto_oracles", "crypto_protocol_oracle", "crypto_hack_analysis"]:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            totals[table] = row[0]
        except:
            totals[table] = 0
    conn.close()
    
    print(f"\n   📊 GRAND TOTAL DATABASE:")
    total_entities = 0
    for table, cnt in sorted(totals.items()):
        emoji = "📦"
        if "token" in table and "tag" not in table: emoji = "🪙"
        elif "exchange" in table: emoji = "🏦"
        elif "defi" in table: emoji = "🔄"
        elif "contract" in table: emoji = "📜"
        elif "bridge" in table: emoji = "🌉"
        elif "stable" in table: emoji = "💵"
        elif "chain" in table: emoji = "⛓️"
        elif "dex" in table: emoji = "📊"
        elif "fee" in table: emoji = "💰"
        elif "oracle" in table and "protocol" not in table: emoji = "🔮"
        elif "protocol_oracle" in table: emoji = "🔗"
        elif "hack" in table: emoji = "🔓"
        
        print(f"      {emoji} {table:35s}  {cnt:>7,}")
        if "protocol_oracle" not in table:
            total_entities += cnt
    
    print(f"\n      🏆 TOTAL ENTITIES: {total_entities:,}")


if __name__ == "__main__":
    main()
