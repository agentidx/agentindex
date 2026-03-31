#!/usr/bin/env python3
"""
NERQ CRYPTO — SPRINT 2: UNISWAP POOLS + TOKEN HOLDERS + DEFI ENRICHMENT
=========================================================================
Three data sources, zero cost:

1. UNISWAP V3 POOLS — Read directly from on-chain via The Graph (free)
   Top pools by TVL with token pairs, fee tier, volume, liquidity
   
2. TOKEN HOLDER DISTRIBUTION — Via Etherscan V2 API (free, have key)
   Top holders for top 200 tokens by market cap
   Concentration metrics: top 10 holders %, Gini coefficient
   
3. DEFI PROTOCOL ENRICHMENT — DeFiLlama free endpoints
   TVL breakdown per chain, audit info, category detail

Usage:
    python3 crypto_sprint2_pools_holders.py              # Run all
    python3 crypto_sprint2_pools_holders.py --pools       # Only Uniswap pools
    python3 crypto_sprint2_pools_holders.py --holders     # Only token holders
    python3 crypto_sprint2_pools_holders.py --defi        # Only DeFi enrichment
    python3 crypto_sprint2_pools_holders.py --stats       # Show DB stats

Requirements: pip3 install web3 requests --break-system-packages
"""

import argparse
import json
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ requests not installed: pip3 install requests --break-system-packages")
    sys.exit(1)

try:
    from web3 import Web3
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False

# ============================================================
# ENV + DB
# ============================================================

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"

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


# ============================================================
# INIT TABLES
# ============================================================

def init_sprint2_tables():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_dex_pools (
            pool_address TEXT,
            chain TEXT,
            dex TEXT,
            token0_symbol TEXT,
            token0_address TEXT,
            token1_symbol TEXT,
            token1_address TEXT,
            fee_tier INTEGER,
            tvl_usd REAL,
            volume_24h_usd REAL,
            volume_7d_usd REAL,
            fees_24h_usd REAL,
            tick_current INTEGER,
            liquidity_raw TEXT,
            tx_count_24h INTEGER,
            created_at TEXT,
            crawled_at TEXT,
            PRIMARY KEY (pool_address, chain)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_token_holders (
            token_id TEXT,
            chain TEXT,
            contract_address TEXT,
            rank INTEGER,
            holder_address TEXT,
            balance_raw TEXT,
            balance_formatted REAL,
            percentage REAL,
            label TEXT,
            crawled_at TEXT,
            PRIMARY KEY (token_id, chain, rank)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_token_concentration (
            token_id TEXT,
            chain TEXT,
            contract_address TEXT,
            total_holders INTEGER,
            top10_pct REAL,
            top20_pct REAL,
            top50_pct REAL,
            top100_pct REAL,
            gini_coefficient REAL,
            hhi_index REAL,
            largest_holder_pct REAL,
            is_concentrated INTEGER,
            crawled_at TEXT,
            PRIMARY KEY (token_id, chain)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_defi_detail (
            protocol_id TEXT PRIMARY KEY,
            name TEXT,
            category TEXT,
            chains TEXT,
            tvl_usd REAL,
            tvl_change_1d REAL,
            tvl_change_7d REAL,
            tvl_change_1m REAL,
            mcap_tvl_ratio REAL,
            audits TEXT,
            audit_note TEXT,
            oracles TEXT,
            forked_from TEXT,
            listed_at TEXT,
            slug TEXT,
            url TEXT,
            twitter TEXT,
            github TEXT,
            tvl_per_chain TEXT,
            crawled_at TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Sprint 2 tables initialized")


# ============================================================
# 1. UNISWAP V3 POOLS — via DeFiLlama yields (free, no key)
# ============================================================

def crawl_uniswap_pools():
    """
    Fetch top DEX pools from DeFiLlama's /pools endpoint (free).
    This gives us Uniswap V3 + other DEX pools with TVL, APY, volume.
    No Graph API key needed.
    """
    print("\n🦄 CRAWLING DEX POOL DATA (DeFiLlama Pools — Free)")

    # DeFiLlama /pools endpoint is actually free and gives pool-level data
    # for major DEXes
    url = "https://yields.llama.fi/pools"
    
    try:
        resp = requests.get(url, timeout=60, headers={"User-Agent": "Nerq/1.0"})
        if resp.status_code == 402:
            print("   ⚠️  DeFiLlama /pools requires Pro ($300/mo)")
            print("   Falling back to on-chain Uniswap V3 factory reads...")
            return crawl_uniswap_onchain()
        if resp.status_code != 200:
            print(f"   ⚠️  HTTP {resp.status_code} from DeFiLlama pools")
            print("   Falling back to on-chain reads...")
            return crawl_uniswap_onchain()
        
        data = resp.json()
        pools = data.get("data", [])
        print(f"   Received {len(pools):,} yield pools")
        
    except Exception as e:
        print(f"   ⚠️  Failed: {e}")
        print("   Falling back to on-chain reads...")
        return crawl_uniswap_onchain()

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    # Filter for DEX pools (Uniswap, Curve, SushiSwap, PancakeSwap, etc)
    dex_projects = {
        "uniswap-v3", "uniswap-v2", "uniswap-v4",
        "curve-dex", "curve-finance",
        "sushiswap", "pancakeswap-amm-v3", "pancakeswap-amm-v2",
        "aerodrome-v2", "aerodrome-slipstream",
        "balancer-v2", "balancer-v3",
        "trader-joe-v2.1", "camelot-v3",
        "orca", "raydium",
        "velodrome-v2",
    }

    for pool in pools:
        project = pool.get("project", "").lower()
        
        # Include all DEX pools + large TVL pools from any project
        if project not in dex_projects and pool.get("tvlUsd", 0) < 1_000_000:
            continue

        pool_id = pool.get("pool", "")
        chain = pool.get("chain", "unknown")
        symbol = pool.get("symbol", "")
        tvl = pool.get("tvlUsd", 0) or 0
        apy = pool.get("apy", 0) or 0
        apy_base = pool.get("apyBase", 0) or 0
        apy_reward = pool.get("apyReward", 0) or 0
        volume_1d = pool.get("volumeUsd1d", 0) or 0
        volume_7d = pool.get("volumeUsd7d", 0) or 0
        il_7d = pool.get("il7d", 0) or 0

        # Parse token symbols from the pool symbol (e.g. "WETH-USDC")
        tokens = symbol.split("-") if "-" in symbol else [symbol, ""]
        token0 = tokens[0] if len(tokens) > 0 else ""
        token1 = tokens[1] if len(tokens) > 1 else ""

        # Extract fee tier from pool metadata if available
        fee_tier = 0
        pool_meta = pool.get("poolMeta", "")
        if pool_meta and "%" in str(pool_meta):
            try:
                fee_pct = float(str(pool_meta).replace("%", "").strip())
                fee_tier = int(fee_pct * 10000)  # 0.3% → 3000
            except (ValueError, TypeError):
                pass

        try:
            conn.execute("""
                INSERT OR REPLACE INTO crypto_dex_pools
                (pool_address, chain, dex, token0_symbol, token0_address,
                 token1_symbol, token1_address, fee_tier, tvl_usd,
                 volume_24h_usd, volume_7d_usd, fees_24h_usd,
                 tick_current, liquidity_raw, tx_count_24h, created_at, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pool_id, chain, project, token0, "",
                token1, "", fee_tier, tvl,
                volume_1d, volume_7d, volume_1d * 0.003 if fee_tier == 0 else volume_1d * fee_tier / 1_000_000,
                None, None, None, None, now
            ))
            count += 1
        except Exception as e:
            if count == 0:
                print(f"   ⚠️  Insert error: {e}")

    conn.commit()
    conn.close()

    print(f"✅ DEX pools crawled: {count:,}")
    
    # Show top 15
    conn = get_db()
    top = conn.execute("""
        SELECT dex, token0_symbol, token1_symbol, chain, tvl_usd, volume_24h_usd
        FROM crypto_dex_pools
        ORDER BY tvl_usd DESC
        LIMIT 15
    """).fetchall()
    conn.close()

    if top:
        print("   Top 15 pools by TVL:")
        for dex, t0, t1, chain, tvl, vol in top:
            pair = f"{t0}/{t1}" if t1 else t0
            vol_str = f"${vol/1e6:.1f}M" if vol and vol > 0 else "N/A"
            print(f"      {pair:20s} {dex:25s} {chain:12s} TVL: ${tvl/1e6:>8.1f}M  vol: {vol_str}")

    return count


def crawl_uniswap_onchain():
    """
    Fallback: read Uniswap V3 factory directly from chain.
    Gets top pools by querying known high-volume pairs.
    """
    if not HAS_WEB3:
        print("   ⚠️  web3 not installed — skipping on-chain pool reads")
        return 0

    print("   📡 Reading Uniswap V3 pools directly from Ethereum...")

    # Uniswap V3 Factory
    FACTORY_ADDRESS = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
    FACTORY_ABI = json.loads('[{"inputs":[{"name":"tokenA","type":"address"},{"name":"tokenB","type":"address"},{"name":"fee","type":"uint24"}],"name":"getPool","outputs":[{"name":"pool","type":"address"}],"type":"function"}]')

    # Pool ABI for reading state
    POOL_ABI = json.loads("""[
        {"inputs":[],"name":"token0","outputs":[{"name":"","type":"address"}],"type":"function"},
        {"inputs":[],"name":"token1","outputs":[{"name":"","type":"address"}],"type":"function"},
        {"inputs":[],"name":"fee","outputs":[{"name":"","type":"uint24"}],"type":"function"},
        {"inputs":[],"name":"liquidity","outputs":[{"name":"","type":"uint128"}],"type":"function"},
        {"inputs":[],"name":"slot0","outputs":[{"name":"sqrtPriceX96","type":"uint160"},{"name":"tick","type":"int24"},{"name":"observationIndex","type":"uint16"},{"name":"observationCardinality","type":"uint16"},{"name":"observationCardinalityNext","type":"uint16"},{"name":"feeProtocol","type":"uint8"},{"name":"unlocked","type":"bool"}],"type":"function"}
    ]""")

    ERC20_ABI_MINI = json.loads('[{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}]')

    # Known high-volume Uniswap V3 pairs on Ethereum
    KNOWN_PAIRS = [
        # (token0, token1, fee_bps) — major pairs
        ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 500),    # WETH/USDC 0.05%
        ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 3000),   # WETH/USDC 0.3%
        ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 500),    # WETH/USDT 0.05%
        ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 3000),   # WETH/USDT 0.3%
        ("0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", 500),    # WBTC/WETH 0.05%
        ("0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", 3000),   # WBTC/WETH 0.3%
        ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 100),    # USDC/USDT 0.01%
        ("0x6B175474E89094C44Da98b954EedeAC495271d0F", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 100),    # DAI/USDC 0.01%
        ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0x514910771AF9Ca656af840dff83E8264EcF986CA", 3000),   # WETH/LINK 0.3%
        ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", 3000),   # WETH/UNI 0.3%
        ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9", 3000),   # WETH/AAVE 0.3%
        ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2", 3000),   # WETH/MKR 0.3%
    ]

    from web3 import Web3 as W3

    try:
        w3 = W3(W3.HTTPProvider("https://ethereum-rpc.publicnode.com", request_kwargs={"timeout": 15}))
        if not w3.is_connected():
            print("   ❌ Cannot connect to Ethereum RPC")
            return 0
    except Exception as e:
        print(f"   ❌ RPC error: {e}")
        return 0

    factory = w3.eth.contract(address=W3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for token_a, token_b, fee in KNOWN_PAIRS:
        try:
            pool_addr = factory.functions.getPool(
                W3.to_checksum_address(token_a),
                W3.to_checksum_address(token_b),
                fee
            ).call()

            if pool_addr == "0x0000000000000000000000000000000000000000":
                continue

            pool = w3.eth.contract(address=W3.to_checksum_address(pool_addr), abi=POOL_ABI)
            
            liquidity = float(pool.functions.liquidity().call())
            slot0 = pool.functions.slot0().call()
            tick = slot0[1]

            # Get token symbols
            try:
                t0_contract = w3.eth.contract(address=W3.to_checksum_address(token_a), abi=ERC20_ABI_MINI)
                t1_contract = w3.eth.contract(address=W3.to_checksum_address(token_b), abi=ERC20_ABI_MINI)
                sym0 = t0_contract.functions.symbol().call()
                sym1 = t1_contract.functions.symbol().call()
            except Exception:
                sym0, sym1 = "?", "?"

            conn.execute("""
                INSERT OR REPLACE INTO crypto_dex_pools
                (pool_address, chain, dex, token0_symbol, token0_address,
                 token1_symbol, token1_address, fee_tier, tvl_usd,
                 volume_24h_usd, volume_7d_usd, fees_24h_usd,
                 tick_current, liquidity_raw, tx_count_24h, created_at, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pool_addr.lower(), "ethereum", "uniswap-v3", sym0, token_a.lower(),
                sym1, token_b.lower(), fee, None,
                None, None, None,
                tick, str(int(liquidity)), None, None, now
            ))
            count += 1
            fee_pct = fee / 10000
            print(f"      {sym0}/{sym1:6s} fee:{fee_pct}%  liq:{liquidity:.0f}  tick:{tick}")

        except Exception as e:
            print(f"      ⚠️  pair error: {str(e)[:50]}")

        time.sleep(0.2)

    conn.commit()
    conn.close()
    print(f"✅ Uniswap V3 on-chain pools: {count}")
    return count


# ============================================================
# 2. TOKEN HOLDER DISTRIBUTION — Etherscan V2 API
# ============================================================

# Known labels for common addresses
KNOWN_LABELS = {
    "0x0000000000000000000000000000000000000000": "burn_address",
    "0x000000000000000000000000000000000000dead": "burn_address",
    "0x28c6c06298d514db089934071355e5743bf21d60": "binance_hot",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "binance_cold",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "binance",
    "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": "coinbase",
    "0x503828976d22510aad0201ac7ec88293211d23da": "coinbase",
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "coinbase",
    "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503": "binance",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "binance",
    "0x5a52e96bacdabb82fd05763e25335261b270efcb": "binance",
}

def label_address(addr):
    """Try to label known addresses (exchanges, bridges, etc)."""
    addr_lower = addr.lower() if addr else ""
    return KNOWN_LABELS.get(addr_lower, "")


def crawl_token_holders():
    """
    Fetch top holder distribution for top tokens using Etherscan V2.
    One API key works for 20+ EVM chains.
    """
    print("\n🐋 CRAWLING TOKEN HOLDER DISTRIBUTION (Etherscan V2)")

    if not ETHERSCAN_API_KEY:
        print("   ⚠️  No ETHERSCAN_API_KEY found")
        print("   Set in environment or ~/agentindex/agentindex/crypto/.env")
        print("   Get free key at: https://etherscan.io/apis")
        return 0

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Get top tokens by market cap that have contract addresses
    # platforms is a JSON dict like {"ethereum": "0x...", "bsc": "0x..."}
    tokens = conn.execute("""
        SELECT id, name, symbol, contract_address, platforms, market_cap_usd
        FROM crypto_tokens
        WHERE contract_address IS NOT NULL
          AND contract_address != ''
          AND market_cap_usd IS NOT NULL
        ORDER BY market_cap_usd DESC
        LIMIT 200
    """).fetchall()
    conn.close()

    if not tokens:
        print("   ⚠️  No tokens with contract addresses found in DB")
        print("   Run crypto_mass_enrich.py first to populate contract addresses")
        return 0

    print(f"   Found {len(tokens)} tokens with contracts to check")

    # Map platform names to Etherscan V2 chain IDs
    CHAIN_IDS = {
        "ethereum": 1,
        "binance-smart-chain": 56,
        "polygon-pos": 137,
        "arbitrum-one": 42161,
        "optimistic-ethereum": 10,
        "base": 8453,
        "avalanche": 43114,
    }

    conn = get_db()
    total_holders = 0
    tokens_processed = 0

    for token_id, name, symbol, contract, platforms_json, mcap in tokens:
        # Parse platforms JSON to find which chain + contract to use
        platform = "ethereum"  # default
        token_contract = contract
        
        if platforms_json:
            try:
                platforms_dict = json.loads(platforms_json) if isinstance(platforms_json, str) else {}
                # Prefer ethereum, then other supported chains
                for chain_name in ["ethereum", "binance-smart-chain", "polygon-pos", 
                                   "arbitrum-one", "optimistic-ethereum", "base", "avalanche"]:
                    if chain_name in platforms_dict and platforms_dict[chain_name]:
                        platform = chain_name
                        token_contract = platforms_dict[chain_name]
                        break
            except (json.JSONDecodeError, TypeError):
                pass

        chain_id = CHAIN_IDS.get(platform)
        if not chain_id or not token_contract:
            continue

        try:
            # Etherscan V2: get top token holders
            resp = requests.get(ETHERSCAN_V2_URL, params={
                "chainid": chain_id,
                "module": "token",
                "action": "tokenholderlist",
                "contractaddress": token_contract,
                "page": "1",
                "offset": "100",  # top 100 holders
                "apikey": ETHERSCAN_API_KEY,
            }, timeout=15)

            data = resp.json()

            if data.get("status") != "1" or not data.get("result"):
                # Try alternative: tokenholdercount at least
                if "Max rate limit reached" in str(data.get("result", "")):
                    print(f"   ⚠️  Rate limited — sleeping 5s")
                    time.sleep(5)
                    continue
                continue

            holders = data["result"]
            if not holders or not isinstance(holders, list):
                continue

            # Get token decimals
            decimals = 18  # default
            try:
                dec_resp = requests.get(ETHERSCAN_V2_URL, params={
                    "chainid": chain_id,
                    "module": "token",
                    "action": "tokeninfo",
                    "contractaddress": token_contract,
                    "apikey": ETHERSCAN_API_KEY,
                }, timeout=10)
                dec_data = dec_resp.json()
                if dec_data.get("status") == "1" and dec_data.get("result"):
                    result = dec_data["result"]
                    if isinstance(result, list) and len(result) > 0:
                        decimals = int(result[0].get("divisor", "18") or "18")
                    elif isinstance(result, dict):
                        decimals = int(result.get("divisor", "18") or "18")
                time.sleep(0.22)
            except Exception:
                pass

            # Calculate total from holders for percentage calc
            total_balance = sum(float(h.get("TokenHolderQuantity", 0)) for h in holders)

            # Store individual holders
            for rank, holder in enumerate(holders, 1):
                addr = holder.get("TokenHolderAddress", "")
                balance_raw = holder.get("TokenHolderQuantity", "0")
                balance = float(balance_raw)
                balance_formatted = balance / (10 ** decimals)
                pct = (balance / total_balance * 100) if total_balance > 0 else 0

                conn.execute("""
                    INSERT OR REPLACE INTO crypto_token_holders
                    (token_id, chain, contract_address, rank, holder_address,
                     balance_raw, balance_formatted, percentage, label, crawled_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    token_id, platform, token_contract, rank, addr,
                    balance_raw, balance_formatted, round(pct, 4),
                    label_address(addr), now
                ))
                total_holders += 1

            # Calculate concentration metrics
            percentages = []
            for h in holders:
                bal = float(h.get("TokenHolderQuantity", 0))
                pct = (bal / total_balance * 100) if total_balance > 0 else 0
                percentages.append(pct)

            top10_pct = sum(percentages[:10])
            top20_pct = sum(percentages[:20])
            top50_pct = sum(percentages[:50])
            top100_pct = sum(percentages[:100])
            largest = percentages[0] if percentages else 0

            # Gini coefficient
            n = len(percentages)
            if n > 1:
                sorted_p = sorted(percentages)
                gini = sum((2 * (i + 1) - n - 1) * sorted_p[i] for i in range(n)) / (n * sum(sorted_p)) if sum(sorted_p) > 0 else 0
            else:
                gini = 1.0

            # HHI (Herfindahl-Hirschman Index)
            hhi = sum(p ** 2 for p in percentages) / 10000 if percentages else 0

            # Concentrated if top 10 > 80% (rug pull risk signal)
            is_concentrated = 1 if top10_pct > 80 else 0

            conn.execute("""
                INSERT OR REPLACE INTO crypto_token_concentration
                (token_id, chain, contract_address, total_holders,
                 top10_pct, top20_pct, top50_pct, top100_pct,
                 gini_coefficient, hhi_index, largest_holder_pct,
                 is_concentrated, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                token_id, platform, token_contract, len(holders),
                round(top10_pct, 2), round(top20_pct, 2),
                round(top50_pct, 2), round(top100_pct, 2),
                round(gini, 4), round(hhi, 4), round(largest, 2),
                is_concentrated, now
            ))

            tokens_processed += 1

            if tokens_processed % 10 == 0:
                conn.commit()
                print(f"   Progress: {tokens_processed}/{len(tokens)} tokens")

            # Show interesting ones
            if top10_pct > 90:
                print(f"      🔴 {symbol:8s} top10: {top10_pct:.1f}% — HIGH CONCENTRATION")
            elif tokens_processed <= 20:
                print(f"      {symbol:8s} top10: {top10_pct:.1f}%  top100: {top100_pct:.1f}%  gini: {gini:.2f}")

        except Exception as e:
            err = str(e)
            if "rate limit" in err.lower() or "429" in err:
                print(f"   ⚠️  Rate limited — sleeping 5s")
                time.sleep(5)
            elif tokens_processed < 5:
                print(f"   ⚠️  {symbol}: {err[:60]}")

        time.sleep(0.22)  # Etherscan rate limit: ~5 calls/sec

    conn.commit()
    conn.close()

    print(f"\n✅ Token holders crawled: {tokens_processed} tokens, {total_holders:,} holder records")

    # Show concentration summary
    conn = get_db()
    concentrated = conn.execute("SELECT COUNT(*) FROM crypto_token_concentration WHERE is_concentrated = 1").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM crypto_token_concentration").fetchone()[0]
    conn.close()

    if total > 0:
        print(f"   🔴 Concentrated tokens (top10 > 80%): {concentrated}/{total} ({concentrated/total*100:.1f}%)")

    return tokens_processed


# ============================================================
# 3. DEFI PROTOCOL ENRICHMENT — DeFiLlama detail
# ============================================================

def crawl_defi_detail():
    """
    Enrich DeFi protocols with detailed data from DeFiLlama.
    Gets per-chain TVL breakdown, audit info, oracle deps, links.
    """
    print("\n🏦 ENRICHING DEFI PROTOCOL DETAILS (DeFiLlama)")

    conn = get_db()

    # Get protocols we already have (schema: id, name, tvl_usd, ...)
    existing = conn.execute("""
        SELECT id, name FROM crypto_defi_protocols
        ORDER BY tvl_usd DESC NULLS LAST
        LIMIT 500
    """).fetchall()
    conn.close()

    if not existing:
        print("   ⚠️  No DeFi protocols in DB. Run crypto_infra_crawler.py first.")
        return 0

    print(f"   Found {len(existing)} protocols to enrich")

    # Fetch all protocols in one call
    try:
        resp = requests.get("https://api.llama.fi/protocols", timeout=60,
                          headers={"User-Agent": "Nerq/1.0"})
        if resp.status_code != 200:
            print(f"   ⚠️  HTTP {resp.status_code}")
            return 0
        all_protocols = resp.json()
        print(f"   Received {len(all_protocols):,} protocols from DeFiLlama")
    except Exception as e:
        print(f"   ⚠️  Failed: {e}")
        return 0

    # Index by slug and name for matching
    by_slug = {}
    by_name = {}
    for p in all_protocols:
        slug = p.get("slug", "").lower()
        name = p.get("name", "").lower()
        if slug:
            by_slug[slug] = p
        if name:
            by_name[name] = p

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for row in existing:
        proto_id = row[0]
        proto_name = row[1]

        # Match by name (lowercase)
        match = None
        name_lower = proto_name.lower() if proto_name else ""
        slug_guess = name_lower.replace(" ", "-")
        match = by_name.get(name_lower) or by_slug.get(name_lower) or by_slug.get(slug_guess)

        if not match:
            continue

        # Extract detail
        category = match.get("category", "")
        chains = json.dumps(match.get("chains", []))
        tvl = match.get("tvl", 0)
        tvl_1d = match.get("change_1d", 0) or 0
        tvl_7d = match.get("change_7d", 0) or 0
        tvl_1m = match.get("change_1m", 0) or 0
        mcap = match.get("mcap", 0) or 0
        mcap_tvl = (mcap / tvl) if tvl and tvl > 0 and mcap else None
        
        audits = json.dumps(match.get("audits", ""))
        audit_note = match.get("audit_note") or match.get("auditNote", "")
        oracles = json.dumps(match.get("oracles", []))
        forked_from = match.get("forkedFrom") or ""
        listed_at = match.get("listedAt", "")
        slug = match.get("slug", "")
        url = match.get("url", "")
        twitter = match.get("twitter", "")
        github_list = match.get("github", [])
        github = json.dumps(github_list) if github_list else ""

        # TVL per chain
        chain_tvls = {}
        for key, val in match.items():
            if key.endswith("-tvl") or (isinstance(val, (int, float)) and key in (match.get("chains", []))):
                chain_tvls[key] = val
        # Also check chainTvls
        chain_tvls_raw = match.get("chainTvls", {})
        if chain_tvls_raw:
            for cname, cdata in chain_tvls_raw.items():
                if isinstance(cdata, dict):
                    latest = cdata.get("tvl", [])
                    if latest and isinstance(latest, list) and len(latest) > 0:
                        chain_tvls[cname] = latest[-1].get("totalLiquidityUSD", 0)
                elif isinstance(cdata, (int, float)):
                    chain_tvls[cname] = cdata

        try:
            conn.execute("""
                INSERT OR REPLACE INTO crypto_defi_detail
                (protocol_id, name, category, chains, tvl_usd,
                 tvl_change_1d, tvl_change_7d, tvl_change_1m, mcap_tvl_ratio,
                 audits, audit_note, oracles, forked_from, listed_at,
                 slug, url, twitter, github, tvl_per_chain, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                proto_id, proto_name, category, chains, tvl,
                tvl_1d, tvl_7d, tvl_1m, mcap_tvl,
                audits, audit_note, oracles, forked_from, listed_at,
                slug, url, twitter, github, json.dumps(chain_tvls), now
            ))
            count += 1
        except Exception as e:
            if count == 0:
                print(f"   ⚠️  Insert error: {e}")

    conn.commit()
    conn.close()

    print(f"✅ DeFi protocols enriched: {count}")

    # Show interesting stats
    conn = get_db()
    audited = conn.execute("SELECT COUNT(*) FROM crypto_defi_detail WHERE audits != '\"\"' AND audits != '[]' AND audits != ''").fetchone()[0]
    has_oracle = conn.execute("SELECT COUNT(*) FROM crypto_defi_detail WHERE oracles != '[]' AND oracles != ''").fetchone()[0]
    forked = conn.execute("SELECT COUNT(*) FROM crypto_defi_detail WHERE forked_from != ''").fetchone()[0]
    conn.close()

    print(f"   📊 Audited: {audited}  With oracle: {has_oracle}  Forks: {forked}")

    return count


# ============================================================
# DB STATS
# ============================================================

def show_stats():
    print("\n" + "=" * 60)
    print("  NERQ CRYPTO — DATABASE STATISTICS")
    print("=" * 60)

    conn = get_db()

    tables = [
        ("crypto_tokens", "🪙"),
        ("crypto_exchanges", "🏦"),
        ("crypto_defi_protocols", "🔄"),
        ("crypto_smart_contracts", "📜"),
        ("crypto_bridges", "🌉"),
        ("crypto_stablecoins", "💵"),
        ("crypto_chains", "⛓️"),
        ("crypto_dex_volumes", "📊"),
        ("crypto_fees_revenue", "💰"),
        ("crypto_oracles", "🔮"),
        ("crypto_protocol_oracle", "🔗"),
        ("crypto_hack_analysis", "🔓"),
        ("crypto_l2_risk", "🏗️"),
        ("crypto_dex_pools", "🦄"),
        ("crypto_token_holders", "🐋"),
        ("crypto_token_concentration", "📈"),
        ("crypto_defi_detail", "📋"),
        ("onchain_stablecoin_supply", "💵"),
        ("onchain_oracle_feeds", "🔮"),
        ("onchain_lending_rates", "🏦"),
    ]

    grand_total = 0
    for table, emoji in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count > 0:
                print(f"   {emoji} {table:35s} {count:>8,}")
                grand_total += count
        except Exception:
            pass

    print(f"\n   🏆 GRAND TOTAL: {grand_total:,} data points")

    # Concentration stats
    try:
        conc = conn.execute("""
            SELECT COUNT(*), 
                   SUM(CASE WHEN is_concentrated = 1 THEN 1 ELSE 0 END),
                   AVG(top10_pct),
                   AVG(gini_coefficient)
            FROM crypto_token_concentration
        """).fetchone()
        if conc[0] and conc[0] > 0:
            print(f"\n   📈 HOLDER CONCENTRATION:")
            print(f"      Tokens analyzed: {conc[0]}")
            print(f"      Concentrated (top10 > 80%): {conc[1]} ({conc[1]/conc[0]*100:.1f}%)")
            print(f"      Avg top10 holder %: {conc[2]:.1f}%")
            print(f"      Avg Gini coefficient: {conc[3]:.3f}")
    except Exception:
        pass

    # Pool stats
    try:
        pools = conn.execute("""
            SELECT COUNT(*), SUM(tvl_usd), SUM(volume_24h_usd)
            FROM crypto_dex_pools
        """).fetchone()
        if pools[0] and pools[0] > 0:
            tvl = pools[1] or 0
            vol = pools[2] or 0
            print(f"\n   🦄 DEX POOLS:")
            print(f"      Pools tracked: {pools[0]:,}")
            print(f"      Total TVL: ${tvl/1e9:.2f}B")
            print(f"      Total 24h volume: ${vol/1e9:.2f}B")
    except Exception:
        pass

    conn.close()


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Nerq Crypto Sprint 2: Pools + Holders + DeFi")
    parser.add_argument("--pools", action="store_true", help="Only crawl DEX pools")
    parser.add_argument("--holders", action="store_true", help="Only crawl token holders")
    parser.add_argument("--defi", action="store_true", help="Only enrich DeFi protocols")
    parser.add_argument("--stats", action="store_true", help="Show DB statistics")
    parser.add_argument("--etherscan-key", type=str, help="Etherscan API key (or set ETHERSCAN_API_KEY env)")
    args = parser.parse_args()

    # Set Etherscan key if provided via argument
    global ETHERSCAN_API_KEY
    if args.etherscan_key:
        ETHERSCAN_API_KEY = args.etherscan_key
    elif not ETHERSCAN_API_KEY:
        # Try to find it from existing .env files
        for env_path in [
            os.path.expanduser("~/agentindex/.env"),
            os.path.expanduser("~/agentindex/agentindex/.env"),
            os.path.expanduser("~/agentindex/agentindex/crypto/.env"),
            os.path.expanduser("~/.env"),
        ]:
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.strip().startswith("ETHERSCAN_API_KEY="):
                            ETHERSCAN_API_KEY = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                            print(f"   Found Etherscan key in {env_path}")
                            break
            if ETHERSCAN_API_KEY:
                break

    start = time.time()

    print("=" * 60)
    print("  NERQ CRYPTO — SPRINT 2: POOLS + HOLDERS + DEFI")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print("  All free APIs — zero cost")
    print("=" * 60)

    if args.stats:
        show_stats()
        return

    init_sprint2_tables()

    run_all = not (args.pools or args.holders or args.defi)
    results = {}

    if run_all or args.pools:
        results["dex_pools"] = crawl_uniswap_pools()

    if run_all or args.holders:
        results["token_holders"] = crawl_token_holders()

    if run_all or args.defi:
        results["defi_detail"] = crawl_defi_detail()

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print("  SPRINT 2 COMPLETE")
    print("=" * 60)
    for key, val in results.items():
        print(f"   {key:25s} {val:>8,}")
    print(f"\n   ⏱️  Total time: {elapsed:.1f} seconds")

    show_stats()


if __name__ == "__main__":
    main()
