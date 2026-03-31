"""
Nerq Crypto Module — Etherscan Smart Contract Crawler
Punkt 27: Crawla top smart contracts med audit-data, verifiering, interaktioner.

Etherscan free tier: 5 calls/sec, 100K calls/day.
BSCScan uses same API format with different base URL.

Usage:
    python3 crypto_etherscan_crawler.py                        # Crawl Ethereum
    python3 crypto_etherscan_crawler.py --chain bsc            # Crawl BSC
    python3 crypto_etherscan_crawler.py --enrich               # Enrich tokens with contract data
    python3 crypto_etherscan_crawler.py --stats                # Print stats
"""

import argparse
import json
import time
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ requests not installed")
    sys.exit(1)

from crypto_models import get_db, init_db

# ── Config ────────────────────────────────────────────────────────

import os
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")

CHAIN_CONFIG = {
    "ethereum": {
        "base_url": "https://api.etherscan.io/v2/api",
        "chainid": "1",
        "api_key_env": "ETHERSCAN_API_KEY",
        "name": "Ethereum",
        "symbol": "ETH",
    },
    "bsc": {
        "base_url": "https://api.etherscan.io/v2/api",
        "chainid": "56",
        "api_key_env": "ETHERSCAN_API_KEY",  # V2 uses same key for all chains
        "name": "BNB Smart Chain",
        "symbol": "BNB",
    },
}

DELAY = 0.22  # 5 calls/sec max → 0.2s + margin


def _n(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError, OverflowError):
        return None


# ── DB Schema Extension ──────────────────────────────────────────

def init_contracts_table():
    """Create smart_contracts table if not exists."""
    conn = get_db()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS crypto_smart_contracts (
        address TEXT NOT NULL,
        chain TEXT NOT NULL DEFAULT 'ethereum',
        
        -- Contract info
        name TEXT,
        compiler TEXT,
        optimization INTEGER,
        runs INTEGER,
        
        -- Verification
        is_verified INTEGER DEFAULT 0,
        source_code_available INTEGER DEFAULT 0,
        license_type TEXT,
        
        -- Risk signals
        is_proxy INTEGER DEFAULT 0,
        implementation_address TEXT,
        has_self_destruct INTEGER DEFAULT 0,
        has_delegatecall INTEGER DEFAULT 0,
        
        -- Activity
        creation_date TEXT,
        creation_tx TEXT,
        transaction_count INTEGER,
        
        -- Token association
        token_name TEXT,
        token_symbol TEXT,
        token_decimals INTEGER,
        token_total_supply TEXT,
        
        -- Trust Score
        trust_score REAL,
        trust_grade TEXT,
        security_score REAL,
        compliance_score REAL,
        maintenance_score REAL,
        popularity_score REAL,
        ecosystem_score REAL,
        
        -- Metadata
        crawled_at TEXT NOT NULL,
        scored_at TEXT,
        
        PRIMARY KEY (address, chain)
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_chain ON crypto_smart_contracts(chain)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_verified ON crypto_smart_contracts(is_verified)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_trust ON crypto_smart_contracts(trust_score)")
    conn.commit()
    conn.close()


# ── Etherscan API ─────────────────────────────────────────────────

def etherscan_get(chain, params, retries=3):
    """Make Etherscan API call with rate limiting."""
    config = CHAIN_CONFIG.get(chain, CHAIN_CONFIG["ethereum"])
    api_key = os.getenv(config["api_key_env"]) or ETHERSCAN_API_KEY
    
    if not api_key:
        print(f"❌ No API key for {chain}")
        return None
    
    params["apikey"] = api_key
    params["chainid"] = config.get("chainid", "1")
    url = config["base_url"]
    
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=30)
            data = resp.json()
            
            if data.get("status") == "1" or data.get("result"):
                return data.get("result")
            elif "Max rate limit reached" in str(data.get("result", "")):
                print(f"  ⏳ Rate limited, waiting 5s...")
                time.sleep(5)
                continue
            else:
                msg = data.get("message", "") or data.get("result", "")
                if "No transactions found" in str(msg) or "No records found" in str(msg):
                    return []
                print(f"  ⚠️ API error: {msg} (attempt {attempt+1})")
                time.sleep(2)
        except Exception as e:
            print(f"  ⚠️ Request error: {e} (attempt {attempt+1})")
            time.sleep(2)
    
    return None


# ── Contract Verification Checker ─────────────────────────────────

def check_contract_verified(chain, address):
    """Check if a contract's source code is verified on Etherscan."""
    result = etherscan_get(chain, {
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
    })
    time.sleep(DELAY)
    
    if not result or not isinstance(result, list) or len(result) == 0:
        return {}
    
    contract = result[0]
    source = contract.get("SourceCode", "")
    
    return {
        "is_verified": 1 if source and source != "" else 0,
        "source_code_available": 1 if source and len(source) > 10 else 0,
        "name": contract.get("ContractName", ""),
        "compiler": contract.get("CompilerVersion", ""),
        "optimization": 1 if contract.get("OptimizationUsed") == "1" else 0,
        "runs": int(contract.get("Runs", 0) or 0),
        "is_proxy": 1 if contract.get("Proxy") == "1" or contract.get("Implementation", "") else 0,
        "implementation_address": contract.get("Implementation", "") or None,
        "license_type": contract.get("LicenseType", ""),
        "has_self_destruct": 1 if "selfdestruct" in source.lower() or "suicide" in source.lower() else 0,
        "has_delegatecall": 1 if "delegatecall" in source.lower() else 0,
    }


# ── Crawl Token Contracts ────────────────────────────────────────

def crawl_token_contracts(chain="ethereum", limit=500):
    """
    Get contract addresses from our token DB and verify them on Etherscan.
    This enriches our existing token data with smart contract security info.
    """
    print(f"\n📜 CRAWLING TOKEN CONTRACTS ({CHAIN_CONFIG[chain]['name']})")
    print(f"   Limit: {limit} contracts")
    
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    # Get tokens that have contract addresses on this chain
    chain_key = "ethereum" if chain == "ethereum" else "binance-smart-chain"
    
    rows = conn.execute("""
        SELECT id, name, symbol, platforms, contract_address 
        FROM crypto_tokens 
        WHERE platforms IS NOT NULL 
        AND platforms != '{}'
        AND platforms != ''
        ORDER BY market_cap_rank ASC NULLS LAST
        LIMIT ?
    """, (limit * 3,)).fetchall()  # fetch more since not all will match chain
    
    print(f"   Found {len(rows)} tokens with platform data\n")
    
    crawled = 0
    for row in rows:
        if crawled >= limit:
            break
            
        token = dict(row)
        
        # Extract contract address for this chain
        address = None
        try:
            platforms = json.loads(token["platforms"]) if isinstance(token["platforms"], str) else token["platforms"]
            address = platforms.get(chain_key) or platforms.get("ethereum")
        except (json.JSONDecodeError, TypeError):
            pass
        
        if not address or len(address) < 10:
            continue
        
        # Check if already crawled
        existing = conn.execute(
            "SELECT address FROM crypto_smart_contracts WHERE address = ? AND chain = ?",
            (address.lower(), chain)
        ).fetchone()
        
        if existing:
            crawled += 1
            continue
        
        # Verify contract
        info = check_contract_verified(chain, address)
        
        if info:
            conn.execute("""
                INSERT INTO crypto_smart_contracts (
                    address, chain, name, compiler, optimization, runs,
                    is_verified, source_code_available, license_type,
                    is_proxy, implementation_address,
                    has_self_destruct, has_delegatecall,
                    token_name, token_symbol,
                    crawled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(address, chain) DO UPDATE SET
                    is_verified = excluded.is_verified,
                    source_code_available = excluded.source_code_available,
                    is_proxy = excluded.is_proxy,
                    has_self_destruct = excluded.has_self_destruct,
                    has_delegatecall = excluded.has_delegatecall,
                    crawled_at = excluded.crawled_at
            """, (
                address.lower(), chain,
                info.get("name", ""), info.get("compiler", ""),
                info.get("optimization", 0), info.get("runs", 0),
                info.get("is_verified", 0), info.get("source_code_available", 0),
                info.get("license_type", ""),
                info.get("is_proxy", 0), info.get("implementation_address"),
                info.get("has_self_destruct", 0), info.get("has_delegatecall", 0),
                token.get("name", ""), token.get("symbol", ""),
                now
            ))
            
            status = "✅" if info.get("is_verified") else "❌"
            proxy = " 🔄PROXY" if info.get("is_proxy") else ""
            risk = " ⚠️SELFDESTRUCT" if info.get("has_self_destruct") else ""
            
            crawled += 1
            print(f"   [{crawled}/{limit}] {status}{proxy}{risk} {token.get('symbol', '').upper():>8s} — {address[:10]}...{address[-6:]}")
            
            if crawled % 50 == 0:
                conn.commit()
                print(f"   💾 Committed {crawled} contracts")
        
        time.sleep(DELAY)
    
    # Also update tokens table with audit/verification info
    print(f"\n   Enriching tokens with contract verification data...")
    verified_contracts = conn.execute("""
        SELECT address, is_verified, is_proxy, has_self_destruct, has_delegatecall
        FROM crypto_smart_contracts 
        WHERE chain = ? AND is_verified = 1
    """, (chain,)).fetchall()
    
    enriched = 0
    for vc in verified_contracts:
        # Find token with this contract
        result = conn.execute("""
            UPDATE crypto_tokens SET has_audit = 1
            WHERE (LOWER(contract_address) = ? OR platforms LIKE ?)
            AND has_audit = 0
        """, (vc["address"], f"%{vc['address']}%"))
        enriched += result.rowcount
    
    conn.commit()
    conn.close()
    print(f"   ✅ {enriched} tokens enriched with verification data")
    print(f"\n✅ Contract crawl complete: {crawled} contracts checked")
    return crawled


# ── Top Contracts by Transaction Count ────────────────────────────

def crawl_top_contracts(chain="ethereum", addresses=None):
    """
    Crawl transaction count for known high-value contracts.
    Uses a curated list of important DeFi/DEX/Bridge contracts.
    """
    if addresses is None:
        # Top Ethereum contracts (DeFi routers, bridges, major protocols)
        addresses = [
            ("0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D", "Uniswap V2 Router"),
            ("0xE592427A0AEce92De3Edee1F18E0157C05861564", "Uniswap V3 Router"),
            ("0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F", "SushiSwap Router"),
            ("0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD", "Uniswap Universal Router"),
            ("0x881D40237659C251811CEC9c364ef91dC08D300C", "MetaMask Swap Router"),
            ("0xDef1C0ded9bec7F1a1670819833240f027b25EfF", "0x Exchange Proxy"),
            ("0x1111111254EEB25477B68fb85Ed929f73A960582", "1inch V5 Router"),
            ("0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45", "Uniswap V3 Router 2"),
            ("0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2", "Aave V3 Pool"),
            ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "USDC"),
            ("0xdAC17F958D2ee523a2206206994597C13D831ec7", "USDT"),
            ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "WETH"),
            ("0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "WBTC"),
            ("0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0", "MATIC"),
            ("0x514910771AF9Ca656af840dff83E8264EcF986CA", "LINK"),
            ("0x6B175474E89094C44Da98b954EedeAC495271d0F", "DAI"),
            ("0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84", "stETH (Lido)"),
            ("0xBe9895146f7AF43049ca1c1AE358B0541Ea49704", "cbETH (Coinbase)"),
            ("0xae78736Cd615f374D3085123A210448E74Fc6393", "rETH (Rocket Pool)"),
            ("0x4Fabb145d64652a948d72533023f6E7A623C7C53", "BUSD"),
        ]
    
    print(f"\n📊 CRAWLING TOP CONTRACTS ({CHAIN_CONFIG[chain]['name']})")
    print(f"   {len(addresses)} contracts to check\n")
    
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    checked = 0
    
    for addr, label in addresses:
        # Get verification info
        info = check_contract_verified(chain, addr)
        
        # Get transaction count
        tx_count_result = etherscan_get(chain, {
            "module": "proxy",
            "action": "eth_getTransactionCount",
            "address": addr,
            "tag": "latest",
        })
        time.sleep(DELAY)
        
        tx_count = None
        if tx_count_result:
            try:
                tx_count = int(tx_count_result, 16)
            except (ValueError, TypeError):
                pass
        
        if info:
            conn.execute("""
                INSERT INTO crypto_smart_contracts (
                    address, chain, name, compiler, optimization, runs,
                    is_verified, source_code_available, license_type,
                    is_proxy, implementation_address,
                    has_self_destruct, has_delegatecall,
                    transaction_count, token_name,
                    crawled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(address, chain) DO UPDATE SET
                    is_verified = excluded.is_verified,
                    source_code_available = excluded.source_code_available,
                    is_proxy = excluded.is_proxy,
                    transaction_count = excluded.transaction_count,
                    crawled_at = excluded.crawled_at
            """, (
                addr.lower(), chain,
                info.get("name") or label, info.get("compiler", ""),
                info.get("optimization", 0), info.get("runs", 0),
                info.get("is_verified", 0), info.get("source_code_available", 0),
                info.get("license_type", ""),
                info.get("is_proxy", 0), info.get("implementation_address"),
                info.get("has_self_destruct", 0), info.get("has_delegatecall", 0),
                tx_count, label,
                now
            ))
        
        status = "✅" if info and info.get("is_verified") else "❌"
        proxy = " 🔄" if info and info.get("is_proxy") else ""
        tx_str = f" txs:{tx_count:,}" if tx_count else ""
        
        checked += 1
        print(f"   [{checked}/{len(addresses)}] {status}{proxy} {label:30s}{tx_str}")
    
    conn.commit()
    conn.close()
    print(f"\n✅ Top contracts crawled: {checked}")
    return checked


# ── Stats ─────────────────────────────────────────────────────────

def print_stats():
    conn = get_db()
    
    total = conn.execute("SELECT COUNT(*) as c FROM crypto_smart_contracts").fetchone()["c"]
    verified = conn.execute("SELECT COUNT(*) as c FROM crypto_smart_contracts WHERE is_verified = 1").fetchone()["c"]
    proxy = conn.execute("SELECT COUNT(*) as c FROM crypto_smart_contracts WHERE is_proxy = 1").fetchone()["c"]
    selfdestruct = conn.execute("SELECT COUNT(*) as c FROM crypto_smart_contracts WHERE has_self_destruct = 1").fetchone()["c"]
    delegatecall = conn.execute("SELECT COUNT(*) as c FROM crypto_smart_contracts WHERE has_delegatecall = 1").fetchone()["c"]
    
    print(f"\n📊 SMART CONTRACT STATS")
    print(f"   Total contracts:    {total:,}")
    print(f"   Verified:           {verified:,} ({verified/total*100:.0f}%)" if total else "")
    print(f"   Proxy contracts:    {proxy:,} ({proxy/total*100:.0f}%)" if total else "")
    print(f"   Has selfdestruct:   {selfdestruct:,}" if total else "")
    print(f"   Has delegatecall:   {delegatecall:,}" if total else "")
    
    # By chain
    chains = conn.execute("SELECT chain, COUNT(*) as c FROM crypto_smart_contracts GROUP BY chain").fetchall()
    if chains:
        print(f"\n   By chain:")
        for c in chains:
            print(f"     {c['chain']}: {c['c']:,}")
    
    conn.close()


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Nerq Crypto — Etherscan Contract Crawler")
    parser.add_argument("--chain", default="ethereum", choices=["ethereum", "bsc"])
    parser.add_argument("--limit", type=int, default=500, help="Max token contracts to check")
    parser.add_argument("--top-contracts", action="store_true", help="Crawl curated top contracts")
    parser.add_argument("--enrich", action="store_true", help="Enrich token contracts from DB")
    parser.add_argument("--stats", action="store_true", help="Print stats")
    parser.add_argument("--all", action="store_true", help="Run everything")
    args = parser.parse_args()
    
    if not ETHERSCAN_API_KEY:
        print("❌ ETHERSCAN_API_KEY not set!")
        print("   Add to .env: ETHERSCAN_API_KEY=your-key-here")
        sys.exit(1)
    
    init_db()
    init_contracts_table()
    
    if args.stats:
        print_stats()
        return
    
    print("=" * 60)
    print(f"  NERQ CRYPTO — Etherscan Contract Crawler ({args.chain})")
    print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
    print(f"  API Key: {ETHERSCAN_API_KEY[:6]}...{ETHERSCAN_API_KEY[-4:]}")
    print("=" * 60)
    
    start = time.time()
    
    if args.all or args.top_contracts:
        crawl_top_contracts(args.chain)
    
    if args.all or args.enrich or (not args.top_contracts):
        crawl_token_contracts(args.chain, limit=args.limit)
    
    elapsed = time.time() - start
    print(f"\n⏱️  Total time: {elapsed/60:.1f} minutes")
    
    print_stats()


if __name__ == "__main__":
    main()
