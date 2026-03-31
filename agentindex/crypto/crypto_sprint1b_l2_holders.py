#!/usr/bin/env python3
"""
NERQ CRYPTO — Sprint 1b: L2Beat Risk + Etherscan Holders

1. L2Beat L2 Risk Scraper — scrapes project pages for risk dimensions
2. Etherscan Top Holders — top token holders per token (ERC-20)

Usage: python3 crypto_sprint1b_l2_holders.py
"""

import json
import sqlite3
import time
import re
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ============================================================
# CONFIG
# ============================================================

CRYPTO_DB_PATH = None

def get_db_path():
    global CRYPTO_DB_PATH
    if CRYPTO_DB_PATH:
        return CRYPTO_DB_PATH
    paths = [
        os.path.expanduser("~/agentindex/agentindex/data/crypto_trust.db"),
        os.path.join(os.path.dirname(__file__), "..", "data", "crypto_trust.db"),
    ]
    for p in paths:
        if os.path.exists(p):
            CRYPTO_DB_PATH = p
            return p
    CRYPTO_DB_PATH = paths[0]
    os.makedirs(os.path.dirname(CRYPTO_DB_PATH), exist_ok=True)
    return CRYPTO_DB_PATH

def get_db():
    return sqlite3.connect(get_db_path(), timeout=30)

ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")

HEADERS = {"User-Agent": "Mozilla/5.0 (NerqCrawler/1.0)", "Accept": "application/json"}

def api_get(url, headers=None, timeout=30):
    h = dict(HEADERS)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        print(f"   ⚠️  HTTP {e.code} for {url[:80]}")
        return None
    except Exception as e:
        print(f"   ⚠️  Error: {e}")
        return None


# ============================================================
# INIT TABLES
# ============================================================

def init_tables():
    conn = get_db()
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_l2_risk (
            id TEXT PRIMARY KEY,
            name TEXT,
            stage TEXT,
            category TEXT,
            tvs_usd REAL,
            sequencer_failure TEXT,
            proposer_failure TEXT,
            exit_window TEXT,
            data_availability TEXT,
            state_validation TEXT,
            upgrade_delay TEXT,
            upgrade_multisig TEXT,
            num_permissions INTEGER,
            can_freeze_funds BOOLEAN,
            can_upgrade_instantly BOOLEAN,
            total_score REAL,
            grade TEXT,
            crawled_at TEXT,
            scored_at TEXT
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_token_holders (
            token_id TEXT,
            chain TEXT,
            contract_address TEXT,
            rank INTEGER,
            holder_address TEXT,
            balance REAL,
            share_pct REAL,
            is_contract BOOLEAN,
            label TEXT,
            crawled_at TEXT,
            PRIMARY KEY (token_id, chain, rank)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_holder_summary (
            token_id TEXT PRIMARY KEY,
            chain TEXT,
            total_holders INTEGER,
            top10_share_pct REAL,
            top20_share_pct REAL,
            top50_share_pct REAL,
            top100_share_pct REAL,
            gini_coefficient REAL,
            whale_count INTEGER,
            concentration_risk TEXT,
            crawled_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Sprint 1b tables initialized")


# ============================================================
# 1. L2BEAT RISK SCRAPER
# ============================================================

# Known L2 projects with their L2Beat slugs
L2_PROJECTS = [
    # Major optimistic rollups
    "arbitrum", "op-mainnet", "base", "blast", "mantle", "manta-pacific",
    "mode", "zora", "fraxtal", "kroma", "lyra", "metal", "mint",
    "cyber", "lisk", "orderly", "redstone", "swan", "world-chain",
    # Major ZK rollups  
    "zksync-era", "linea", "scroll", "starknet", "polygon-zkevm",
    "taiko", "zircuit", "paradex", "myria", "immutable-x",
    "dydx", "loopring", "zkspace", "rhinofi",
    # Validiums / Optimiums
    "metis", "boba", "aevo", "apex", "sorare",
    "ancient8", "hypr", "lumio", "rari", "proof-of-play",
    "xai", "polynomial", "parallel", "apechain", "gravity",
    "soneium", "ink", "unichain", "abstract",
    # Others
    "arbitrum-nova", "termstructure", "lighter", "degate-v1",
    "publicgoodsnetwork", "astar-zkevm", "morph", "kinto",
]

def scrape_l2beat_project(slug):
    """Scrape L2Beat project page for risk data."""
    url = f"https://l2beat.com/scaling/projects/{slug}"
    html = api_get(url, timeout=15)
    
    if not html:
        return None
    
    result = {
        "id": slug,
        "name": slug.replace("-", " ").title(),
    }
    
    # Try to extract structured data from the HTML
    # L2Beat uses Next.js so data is in __NEXT_DATA__ script
    next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if next_data_match:
        try:
            next_data = json.loads(next_data_match.group(1))
            # Navigate to project data
            props = next_data.get("props", {}).get("pageProps", {})
            project = props.get("project", {})
            
            if project:
                result["name"] = project.get("name", result["name"])
                result["category"] = project.get("display", {}).get("category", "")
                
                # Stage
                stage = project.get("stage", {})
                if isinstance(stage, dict):
                    result["stage"] = stage.get("stage", "")
                elif isinstance(stage, str):
                    result["stage"] = stage
        except (json.JSONDecodeError, KeyError):
            pass
    
    # Fallback: parse HTML for key indicators
    # Look for risk summary items
    if "sequencer" in html.lower():
        if "force via l1" in html.lower() or "force transactions" in html.lower():
            result["sequencer_failure"] = "force via L1"
        elif "self-sequence" in html.lower() or "submit transactions to an l1 queue" in html.lower():
            result["sequencer_failure"] = "self-sequence"
        elif "no mechanism" in html.lower():
            result["sequencer_failure"] = "no mechanism"
        else:
            result["sequencer_failure"] = "enqueue via L1"
    
    # State validation
    if "validity proof" in html.lower() or "zk proof" in html.lower() or "snarks" in html.lower() or "starks" in html.lower():
        result["state_validation"] = "validity proofs"
    elif "fraud proof" in html.lower():
        result["state_validation"] = "fraud proofs"
    
    # Data availability
    if "published onchain" in html.lower() or "posted to ethereum" in html.lower():
        result["data_availability"] = "onchain"
    elif "data availability committee" in html.lower() or "dac" in html.lower():
        result["data_availability"] = "DAC"
    elif "celestia" in html.lower() or "avail" in html.lower() or "eigenda" in html.lower():
        result["data_availability"] = "external"
    
    # Exit window
    if "instantly upgradable" in html.lower() or "no window" in html.lower():
        result["exit_window"] = "none"
        result["can_upgrade_instantly"] = True
    elif "7d" in html.lower() or "7 days" in html.lower():
        result["exit_window"] = "7d"
    elif "14d" in html.lower() or "14 days" in html.lower():
        result["exit_window"] = "14d"
    elif "30d" in html.lower() or "30 days" in html.lower():
        result["exit_window"] = "30d"
    
    # Upgrade risk
    if "funds can be stolen if a contract receives a malicious code upgrade" in html.lower():
        result["can_freeze_funds"] = True
    
    # Category from URL patterns
    if "zk" in slug or "scroll" in slug or "starknet" in slug or "linea" in slug:
        result.setdefault("category", "ZK Rollup")
    elif any(x in slug for x in ["op-", "base", "blast", "arbitrum", "mode"]):
        result.setdefault("category", "Optimistic Rollup")
    
    return result


def crawl_l2beat():
    print("\n🏗️  SCRAPING L2BEAT RISK DATA")
    print(f"   {len(L2_PROJECTS)} projects to check")
    
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    failed = 0
    
    for i, slug in enumerate(L2_PROJECTS):
        if (i + 1) % 10 == 0:
            print(f"   Progress: {i+1}/{len(L2_PROJECTS)}")
        
        result = scrape_l2beat_project(slug)
        
        if not result:
            failed += 1
            time.sleep(0.5)
            continue
        
        conn.execute("""
            INSERT OR REPLACE INTO crypto_l2_risk 
            (id, name, stage, category, sequencer_failure, proposer_failure,
             exit_window, data_availability, state_validation,
             can_freeze_funds, can_upgrade_instantly, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.get("id"),
            result.get("name"),
            result.get("stage"),
            result.get("category"),
            result.get("sequencer_failure"),
            result.get("proposer_failure"),
            result.get("exit_window"),
            result.get("data_availability"),
            result.get("state_validation"),
            result.get("can_freeze_funds"),
            result.get("can_upgrade_instantly"),
            now
        ))
        count += 1
        time.sleep(0.3)  # Be polite
    
    conn.commit()
    conn.close()
    
    print(f"✅ L2Beat risk data: {count} projects scraped ({failed} failed)")
    return count


# ============================================================
# 2. ETHERSCAN TOP HOLDERS
# ============================================================

CHAIN_EXPLORERS = {
    "ethereum": "https://api.etherscan.io/v2/api",
    # Etherscan V2 — single key works for all chains via chainid param
}

# Chain IDs for Etherscan V2
CHAIN_IDS = {
    "ethereum": 1,
    "binance-smart-chain": 56,
    "polygon-pos": 137,
    "arbitrum-one": 42161,
    "optimistic-ethereum": 10,
    "avalanche": 43114,
    "base": 8453,
}


def get_top_holders_etherscan(contract_address, chain="ethereum", chain_id=1):
    """Get top token holders from Etherscan V2."""
    if not ETHERSCAN_API_KEY:
        return None
    
    url = (
        f"https://api.etherscan.io/v2/api"
        f"?chainid={chain_id}"
        f"&module=token"
        f"&action=tokenholderlist"
        f"&contractaddress={contract_address}"
        f"&page=1&offset=100"
        f"&apikey={ETHERSCAN_API_KEY}"
    )
    
    resp = api_get(url)
    if not resp:
        return None
    
    try:
        data = json.loads(resp)
        if data.get("status") == "1" and data.get("result"):
            return data["result"]
    except:
        pass
    
    return None


def crawl_token_holders():
    global ETHERSCAN_API_KEY
    print("\n🐋 CRAWLING TOKEN HOLDER DISTRIBUTION")
    
    if not ETHERSCAN_API_KEY:
        # Try to load from .env
        env_path = os.path.expanduser("~/agentindex/agentindex/crypto/.env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("ETHERSCAN_API_KEY="):
                        ETHERSCAN_API_KEY = line.strip().split("=", 1)[1].strip('"').strip("'")
        
        if not ETHERSCAN_API_KEY:
            print("   ⚠️  No ETHERSCAN_API_KEY — skipping holder crawl")
            print("   Set ETHERSCAN_API_KEY in environment or crypto/.env")
            return 0
    
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    # Get top tokens with Ethereum contract addresses
    cursor = conn.execute("""
        SELECT id, name, contract_address, platforms 
        FROM crypto_tokens 
        WHERE contract_address IS NOT NULL 
        AND contract_address != ''
        ORDER BY market_cap_rank ASC 
        LIMIT 200
    """)
    tokens = cursor.fetchall()
    print(f"   Found {len(tokens)} tokens with contract addresses")
    
    count = 0
    
    for token_id, name, contract, platforms_json in tokens:
        # Determine chain
        chain = "ethereum"
        chain_id = 1
        
        if platforms_json:
            try:
                platforms = json.loads(platforms_json) if isinstance(platforms_json, str) else platforms_json
                if isinstance(platforms, dict):
                    if "ethereum" in platforms:
                        contract = platforms["ethereum"]
                    elif "binance-smart-chain" in platforms:
                        contract = platforms["binance-smart-chain"]
                        chain = "binance-smart-chain"
                        chain_id = 56
                    elif "polygon-pos" in platforms:
                        contract = platforms["polygon-pos"]
                        chain = "polygon-pos"
                        chain_id = 137
                    elif "arbitrum-one" in platforms:
                        contract = platforms["arbitrum-one"]
                        chain = "arbitrum-one"
                        chain_id = 42161
            except:
                pass
        
        if not contract or len(contract) < 10:
            continue
        
        # Rate limit: 5 calls/sec for Etherscan
        time.sleep(0.22)
        
        holders = get_top_holders_etherscan(contract, chain, chain_id)
        
        if not holders:
            continue
        
        # Calculate total supply from holders (approximate)
        total_balance = sum(float(h.get("TokenHolderQuantity", 0)) for h in holders)
        
        # Save individual holders
        for rank, h in enumerate(holders, 1):
            address = h.get("TokenHolderAddress", "")
            balance = float(h.get("TokenHolderQuantity", 0))
            share = (balance / total_balance * 100) if total_balance > 0 else 0
            
            conn.execute("""
                INSERT OR REPLACE INTO crypto_token_holders 
                (token_id, chain, contract_address, rank, holder_address, 
                 balance, share_pct, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (token_id, chain, contract, rank, address, balance, share, now))
        
        # Calculate summary
        top10_share = sum(float(h.get("TokenHolderQuantity", 0)) for h in holders[:10]) / total_balance * 100 if total_balance > 0 else 0
        top20_share = sum(float(h.get("TokenHolderQuantity", 0)) for h in holders[:20]) / total_balance * 100 if total_balance > 0 else 0
        top50_share = sum(float(h.get("TokenHolderQuantity", 0)) for h in holders[:50]) / total_balance * 100 if total_balance > 0 else 0
        top100_share = sum(float(h.get("TokenHolderQuantity", 0)) for h in holders[:100]) / total_balance * 100 if total_balance > 0 else 0
        
        # Concentration risk
        if top10_share > 80:
            concentration = "extreme"
        elif top10_share > 60:
            concentration = "high"
        elif top10_share > 40:
            concentration = "moderate"
        else:
            concentration = "low"
        
        conn.execute("""
            INSERT OR REPLACE INTO crypto_holder_summary 
            (token_id, chain, total_holders, top10_share_pct, top20_share_pct, 
             top50_share_pct, top100_share_pct, concentration_risk, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            token_id, chain, len(holders),
            round(top10_share, 2), round(top20_share, 2),
            round(top50_share, 2), round(top100_share, 2),
            concentration, now
        ))
        
        count += 1
        
        if count % 20 == 0:
            print(f"   Progress: {count} tokens processed")
            conn.commit()
    
    conn.commit()
    conn.close()
    
    print(f"✅ Token holders crawled: {count} tokens")
    return count


# ============================================================
# MAIN
# ============================================================

def main():
    start = time.time()
    
    print("=" * 60)
    print("  NERQ CRYPTO — SPRINT 1b: L2 RISK + HOLDERS")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)
    
    init_tables()
    
    results = {}
    
    # 1. L2Beat risk data
    results["l2_risk"] = crawl_l2beat()
    
    # 2. Token holders
    results["token_holders"] = crawl_token_holders()
    
    elapsed = time.time() - start
    
    print("\n" + "=" * 60)
    print("  SPRINT 1b COMPLETE")
    print("=" * 60)
    for key, val in results.items():
        print(f"   {key:25s}  {val:,}")
    print(f"\n   ⏱️  Total time: {elapsed:.1f} seconds")


if __name__ == "__main__":
    main()
