#!/usr/bin/env python3
"""
NERQ CRYPTO — ON-CHAIN DIRECT DATA CRAWLER v2
===============================================
Reads data DIRECTLY from blockchains via free public RPCs.
No middlemen. No paid APIs. We own the entire data chain.

v2 FIXES:
- "Python int too large to convert to SQLite INTEGER" — all large ints
  now converted to float or str before INSERT
- Chainlink round_id stored as TEXT (uint80 overflows SQLite int64)
- Aave total_supplied/total_borrowed converted to float
- Compound V3 uses getUtilization() instead of manual calc
- Better error handling with per-field conversion

What this crawler does:
1. Stablecoin: totalSupply per chain for major stablecoins
2. Chainlink: Oracle price feed data (latest answer, decimals, description)
3. Aave V3: Lending/borrowing rates for all reserves (on-chain APY)
4. Compound V3: Lending rates

All data comes directly from smart contract reads (eth_call).
Zero dependency on CoinGecko, DeFiLlama, or any aggregator.

Usage: python3 crypto_onchain_crawler_v2.py
Requirements: pip3 install web3 --break-system-packages
"""

import json
import sqlite3
import time
import os
from datetime import datetime, timezone

try:
    from web3 import Web3
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False
    print("⚠️  web3 not installed. Run: pip3 install web3 --break-system-packages")


# ============================================================
# HELPER: Safe conversion for SQLite
# ============================================================

def safe_int(val):
    """Convert large ints to float for SQLite compatibility.
    SQLite INTEGER max is 2^63-1 (~9.2e18). Anything bigger → float."""
    if val is None:
        return None
    if isinstance(val, int) and (val > 9_000_000_000_000_000_000 or val < -9_000_000_000_000_000_000):
        return float(val)
    return val

def safe_text(val):
    """Convert any value to text for SQLite TEXT columns."""
    if val is None:
        return None
    return str(val)


# ============================================================
# FREE PUBLIC RPC ENDPOINTS — No API key, no signup
# ============================================================

PUBLIC_RPCS = {
    "ethereum": [
        "https://ethereum-rpc.publicnode.com",
        "https://rpc.ankr.com/eth",
        "https://eth.drpc.org",
        "https://1rpc.io/eth",
    ],
    "base": [
        "https://base-rpc.publicnode.com",
        "https://rpc.ankr.com/base",
        "https://base.drpc.org",
    ],
    "arbitrum": [
        "https://arbitrum-one-rpc.publicnode.com",
        "https://rpc.ankr.com/arbitrum",
        "https://arb1.arbitrum.io/rpc",
    ],
    "polygon": [
        "https://polygon-bor-rpc.publicnode.com",
        "https://rpc.ankr.com/polygon",
        "https://polygon.drpc.org",
    ],
    "bsc": [
        "https://bsc-rpc.publicnode.com",
        "https://rpc.ankr.com/bsc",
        "https://bsc.drpc.org",
    ],
    "optimism": [
        "https://optimism-rpc.publicnode.com",
        "https://rpc.ankr.com/optimism",
        "https://mainnet.optimism.io",
    ],
    "avalanche": [
        "https://avalanche-c-chain-rpc.publicnode.com",
        "https://rpc.ankr.com/avalanche",
        "https://api.avax.network/ext/bc/C/rpc",
    ],
}

def get_web3(chain="ethereum"):
    """Get a Web3 connection using free public RPC, with fallback."""
    rpcs = PUBLIC_RPCS.get(chain, PUBLIC_RPCS["ethereum"])
    for rpc_url in rpcs:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
            if w3.is_connected():
                return w3
        except Exception:
            continue
    raise ConnectionError(f"Could not connect to any RPC for {chain}")


# ============================================================
# DB
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


# ============================================================
# MINIMAL ABIs — Only what we need, no external dependencies
# ============================================================

ERC20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},{"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]')

# Chainlink Aggregator V3
CHAINLINK_ABI = json.loads('[{"inputs":[],"name":"latestRoundData","outputs":[{"name":"roundId","type":"uint80"},{"name":"answer","type":"int256"},{"name":"startedAt","type":"uint256"},{"name":"updatedAt","type":"uint256"},{"name":"answeredInRound","type":"uint80"}],"type":"function"},{"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},{"inputs":[],"name":"description","outputs":[{"name":"","type":"string"}],"type":"function"}]')

# Aave V3 Pool Data Provider (simplified)
AAVE_DATA_PROVIDER_ABI = json.loads("""[
    {"inputs":[],"name":"getAllReservesTokens","outputs":[{"components":[{"name":"symbol","type":"string"},{"name":"tokenAddress","type":"address"}],"name":"","type":"tuple[]"}],"type":"function"},
    {"inputs":[{"name":"asset","type":"address"}],"name":"getReserveData","outputs":[{"name":"unbacked","type":"uint256"},{"name":"accruedToTreasuryScaled","type":"uint256"},{"name":"totalAToken","type":"uint256"},{"name":"totalStableDebt","type":"uint256"},{"name":"totalVariableDebt","type":"uint256"},{"name":"liquidityRate","type":"uint256"},{"name":"variableBorrowRate","type":"uint256"},{"name":"stableBorrowRate","type":"uint256"},{"name":"averageStableBorrowRate","type":"uint256"},{"name":"liquidityIndex","type":"uint256"},{"name":"variableBorrowIndex","type":"uint256"},{"name":"lastUpdateTimestamp","type":"uint40"}],"type":"function"},
    {"inputs":[{"name":"asset","type":"address"}],"name":"getReserveConfigurationData","outputs":[{"name":"decimals","type":"uint256"},{"name":"ltv","type":"uint256"},{"name":"liquidationThreshold","type":"uint256"},{"name":"liquidationBonus","type":"uint256"},{"name":"reserveFactor","type":"uint256"},{"name":"usageAsCollateralEnabled","type":"bool"},{"name":"borrowingEnabled","type":"bool"},{"name":"stableBorrowRateEnabled","type":"bool"},{"name":"isActive","type":"bool"},{"name":"isFrozen","type":"bool"}],"type":"function"}
]""")

# Compound V3 Comet — updated ABI with getUtilization
COMPOUND_V3_ABI = json.loads('[{"inputs":[],"name":"getSupplyRate","outputs":[{"name":"","type":"uint64"}],"type":"function"},{"inputs":[],"name":"getBorrowRate","outputs":[{"name":"","type":"uint64"}],"type":"function"},{"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"type":"function"},{"inputs":[],"name":"totalBorrow","outputs":[{"name":"","type":"uint256"}],"type":"function"},{"inputs":[],"name":"baseToken","outputs":[{"name":"","type":"address"}],"type":"function"},{"inputs":[{"name":"utilization","type":"uint256"}],"name":"getSupplyRate","outputs":[{"name":"","type":"uint64"}],"type":"function"},{"inputs":[{"name":"utilization","type":"uint256"}],"name":"getBorrowRate","outputs":[{"name":"","type":"uint64"}],"type":"function"},{"inputs":[],"name":"getUtilization","outputs":[{"name":"","type":"uint256"}],"type":"function"}]')


# ============================================================
# KNOWN CONTRACT ADDRESSES
# ============================================================

# Major stablecoins — contract addresses per chain
STABLECOINS = {
    "USDT": {
        "ethereum": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "bsc": "0x55d398326f99059fF775485246999027B3197955",
        "polygon": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "arbitrum": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "optimism": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",
        "avalanche": "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7",
    },
    "USDC": {
        "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "bsc": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        "polygon": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "optimism": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
        "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "avalanche": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
    },
    "DAI": {
        "ethereum": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        "polygon": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
        "arbitrum": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
        "optimism": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
    },
}

# Chainlink price feed addresses on Ethereum mainnet
CHAINLINK_FEEDS = {
    "ETH/USD": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
    "BTC/USD": "0xF4030086522a5bEEa4988F8cA5B36dbC97BeE88c",
    "LINK/USD": "0x2c1d072e956AFFC0D435Cb7AC38EF18d24d9127c",
    "AAVE/USD": "0x547a514d5e3769680Ce22B2361c10Ea13619e8a9",
    "UNI/USD": "0x553303d460EE0afB37EdFf9bE42922D8FF63220e",
    "USDT/USD": "0x3E7d1eAB13ad0104d2750B8863b489D65364e32D",
    "USDC/USD": "0x8fFfFfd4AfB6115b954Bd326cbe7B4BA576818f6",
    "DAI/USD": "0xAed0c38402a5d19df6E4c03F4E2DceD6e29c1ee9",
    "SOL/USD": "0x4ffC43a60e009B551865A93d232E33Fce9f01507",
    "DOGE/USD": "0x2465CefD3b488BE410b941b1d4b2767088e2A028",
    "AVAX/USD": "0xFF3EEb22B5E3dE6e705b44749C2559d704923FD7",
    "MATIC/USD": "0x7bAC85A8a13A4BcD8abb3eB7d6b4d632c5a57676",
    "DOT/USD": "0x1C07AFb8E2B827c5A4739C6d59Ae3A5035f28734",
    "SHIB/USD": "0x8dD1CD88F43aF196ae478e91b9F5E4Ac69A97C61",
    "CRV/USD": "0xCd627aA160A6fA45Eb793D19Ef54f5062F20f33f",
    "MKR/USD": "0xec1D1B3b0443256cc3860e24a46F108e699484Aa",
    "COMP/USD": "0xdbd020CAeF83eFd542f4De03e3cF0C28A4428bd5",
    "SNX/USD": "0xDC3EA94CD0AC27d9A86C180091e7f78C683d3699",
    "SUSHI/USD": "0xCc70F09A6CC17553b2E31954cD36E4A2d89501f7",
    "YFI/USD": "0xA027702dbb89fbd58938e4324ac03B58d812b0E1",
}

# Aave V3 PoolDataProvider addresses
AAVE_V3_DATA_PROVIDERS = {
    "ethereum": "0x497a1994c46d4f6C864904A9f1fac6328Cb7C8a6",
    "polygon": "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654",
    "arbitrum": "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654",
    "optimism": "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654",
    "avalanche": "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654",
    "base": "0x2d8A3C5677189723C4cB8873CfC9C8976FDF38Ac",
}

# Compound V3 Comet addresses (USDC markets)
COMPOUND_V3_MARKETS = {
    "ethereum_usdc": "0xc3d688B66703497DAA19211EEdff47f25384cdc3",
    "ethereum_weth": "0xA17581A9E3356d9A858b789D68B4d866e593aE94",
    "base_usdc": "0xb125E6687d4313864e53df431d5425969c15Eb2F",
    "arbitrum_usdc": "0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf",
    "polygon_usdc": "0xF25212E676D1F7F89Cd72fFEe66158f541246445",
}


# ============================================================
# INIT TABLES — round_id is now TEXT to handle uint80
# ============================================================

def init_tables():
    conn = get_db()
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS onchain_token_supply (
            contract_address TEXT,
            chain TEXT,
            symbol TEXT,
            name TEXT,
            decimals INTEGER,
            total_supply_raw TEXT,
            total_supply_formatted REAL,
            block_number INTEGER,
            crawled_at TEXT,
            PRIMARY KEY (contract_address, chain)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS onchain_lending_rates (
            protocol TEXT,
            chain TEXT,
            asset_symbol TEXT,
            asset_address TEXT,
            supply_apy REAL,
            borrow_apy REAL,
            total_supplied_raw TEXT,
            total_borrowed_raw TEXT,
            utilization_rate REAL,
            block_number INTEGER,
            crawled_at TEXT,
            PRIMARY KEY (protocol, chain, asset_address)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS onchain_oracle_feeds (
            feed_name TEXT,
            chain TEXT,
            feed_address TEXT,
            latest_price REAL,
            decimals INTEGER,
            last_updated INTEGER,
            round_id TEXT,
            block_number INTEGER,
            crawled_at TEXT,
            PRIMARY KEY (feed_name, chain)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS onchain_stablecoin_supply (
            stablecoin TEXT,
            chain TEXT,
            contract_address TEXT,
            total_supply REAL,
            decimals INTEGER,
            block_number INTEGER,
            crawled_at TEXT,
            PRIMARY KEY (stablecoin, chain)
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ On-chain tables initialized")


# ============================================================
# 1. STABLECOIN SUPPLY — Direct from chain (unchanged, works)
# ============================================================

def crawl_stablecoin_supply():
    print("\n💵 READING STABLECOIN SUPPLY DIRECTLY FROM CHAINS")
    
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    total_supply_all = 0
    
    for stable_name, chains in STABLECOINS.items():
        stable_total = 0
        for chain, address in chains.items():
            try:
                w3 = get_web3(chain)
                contract = w3.eth.contract(
                    address=Web3.to_checksum_address(address),
                    abi=ERC20_ABI
                )
                
                raw_supply = contract.functions.totalSupply().call()
                decimals = contract.functions.decimals().call()
                formatted = raw_supply / (10 ** decimals)
                block = w3.eth.block_number
                
                conn.execute("""
                    INSERT OR REPLACE INTO onchain_stablecoin_supply
                    (stablecoin, chain, contract_address, total_supply, decimals, block_number, crawled_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (stable_name, chain, address, formatted, decimals, block, now))
                
                stable_total += formatted
                count += 1
                
                print(f"   {stable_name:6s} on {chain:12s}: ${formatted:>15,.0f}")
                
            except Exception as e:
                print(f"   ⚠️  {stable_name} on {chain}: {str(e)[:60]}")
            
            time.sleep(0.2)
        
        if stable_total > 0:
            print(f"   {'':6s} {'TOTAL':12s}: ${stable_total:>15,.0f}")
            total_supply_all += stable_total
        print()
    
    conn.commit()
    conn.close()
    
    print(f"✅ Stablecoin supply: {count} chain readings")
    print(f"   Combined supply: ${total_supply_all:,.0f}")
    return count


# ============================================================
# 2. CHAINLINK ORACLE FEEDS — FIX: round_id as TEXT
# ============================================================

def crawl_chainlink_feeds():
    print("\n🔮 READING CHAINLINK ORACLE FEEDS FROM CHAIN")
    
    w3 = get_web3("ethereum")
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    block = w3.eth.block_number
    count = 0
    
    for feed_name, address in CHAINLINK_FEEDS.items():
        try:
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(address),
                abi=CHAINLINK_ABI
            )
            
            round_data = contract.functions.latestRoundData().call()
            decimals = contract.functions.decimals().call()
            
            # round_data: (roundId, answer, startedAt, updatedAt, answeredInRound)
            round_id = round_data[0]     # uint80 — can be huge
            answer = round_data[1]       # int256 — the price in raw
            updated_at = round_data[3]   # uint256 — unix timestamp
            
            # Convert answer to human-readable price
            price = float(answer) / (10 ** decimals)
            
            # Store round_id as TEXT (uint80 overflows SQLite int64)
            # Store updated_at safely
            conn.execute("""
                INSERT OR REPLACE INTO onchain_oracle_feeds
                (feed_name, chain, feed_address, latest_price, decimals, 
                 last_updated, round_id, block_number, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                feed_name, "ethereum", address, price, decimals,
                safe_int(updated_at),   # timestamp fits in int64
                safe_text(round_id),    # round_id as TEXT
                block, now
            ))
            
            count += 1
            
            # Staleness check
            age_seconds = int(time.time()) - int(updated_at)
            stale = " ⚠️ STALE!" if age_seconds > 3600 else ""
            print(f"   {feed_name:12s}  ${price:>12,.4f}  (updated {age_seconds}s ago){stale}")
            
        except Exception as e:
            err = str(e)
            if "execution reverted" in err:
                print(f"   ⚠️  {feed_name}: Feed inactive or deprecated")
            else:
                print(f"   ⚠️  {feed_name}: {err[:60]}")
        
        time.sleep(0.15)
    
    conn.commit()
    conn.close()
    
    print(f"✅ Chainlink feeds: {count} prices read from chain")
    return count


# ============================================================
# 3. AAVE V3 LENDING RATES — FIX: convert all big ints to float
# ============================================================

RAY = 10 ** 27  # Aave uses RAY precision (27 decimals)
SECONDS_PER_YEAR = 31536000

def ray_to_apy(rate_ray):
    """Convert Aave ray rate to APY percentage.
    rate_ray is a uint256 in ray units (1e27 = 100%).
    We convert to float first to avoid SQLite overflow."""
    rate = float(rate_ray) / float(RAY)
    apy = rate * SECONDS_PER_YEAR * 100
    return apy


def crawl_aave_rates():
    print("\n🏦 READING AAVE V3 LENDING RATES FROM CHAIN")
    
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    total_count = 0
    
    for chain, data_provider_addr in AAVE_V3_DATA_PROVIDERS.items():
        try:
            w3 = get_web3(chain)
            block = w3.eth.block_number
            
            provider = w3.eth.contract(
                address=Web3.to_checksum_address(data_provider_addr),
                abi=AAVE_DATA_PROVIDER_ABI
            )
            
            # Get all reserves
            reserves = provider.functions.getAllReservesTokens().call()
            print(f"\n   {chain.upper()}: {len(reserves)} reserves")
            
            for symbol, token_address in reserves:
                try:
                    data = provider.functions.getReserveData(token_address).call()
                    
                    # data indices:
                    # 0: unbacked, 1: accruedToTreasuryScaled, 2: totalAToken,
                    # 3: totalStableDebt, 4: totalVariableDebt, 5: liquidityRate,
                    # 6: variableBorrowRate, 7: stableBorrowRate,
                    # 8: averageStableBorrowRate, 9: liquidityIndex,
                    # 10: variableBorrowIndex, 11: lastUpdateTimestamp
                    
                    liquidity_rate = data[5]       # Supply APY (ray) — uint256
                    variable_borrow_rate = data[6]  # Borrow APY (ray) — uint256
                    total_atoken = data[2]          # Total supplied — uint256
                    total_stable_debt = data[3]     # Stable debt — uint256
                    total_variable_debt = data[4]   # Variable debt — uint256
                    
                    # Convert ray to APY (float)
                    supply_apy = ray_to_apy(liquidity_rate)
                    borrow_apy = ray_to_apy(variable_borrow_rate)
                    
                    # Convert big ints to float for utilization calc
                    total_supplied = float(total_atoken)
                    total_borrowed = float(total_variable_debt) + float(total_stable_debt)
                    utilization = (total_borrowed / total_supplied * 100) if total_supplied > 0 else 0
                    
                    # Get decimals from ERC20 contract directly (cheaper than config call)
                    try:
                        token_contract = w3.eth.contract(
                            address=Web3.to_checksum_address(token_address),
                            abi=ERC20_ABI
                        )
                        token_decimals = token_contract.functions.decimals().call()
                    except Exception:
                        token_decimals = 18  # fallback
                    
                    supplied_human = total_supplied / (10 ** token_decimals)
                    borrowed_human = total_borrowed / (10 ** token_decimals)
                    
                    # Store with raw values as TEXT (they're huge uint256)
                    conn.execute("""
                        INSERT OR REPLACE INTO onchain_lending_rates
                        (protocol, chain, asset_symbol, asset_address,
                         supply_apy, borrow_apy, total_supplied_raw, total_borrowed_raw,
                         utilization_rate, block_number, crawled_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        "aave_v3", chain, symbol, token_address,
                        round(supply_apy, 4), round(borrow_apy, 4),
                        f"{supplied_human:.2f}",   # human-readable as text
                        f"{borrowed_human:.2f}",   # human-readable as text
                        round(utilization, 2), block, now
                    ))
                    
                    total_count += 1
                    
                    if supply_apy > 0.01:  # Only show non-zero
                        print(f"      {symbol:16s}  supply: {supply_apy:8.2f}%  borrow: {borrow_apy:8.2f}%  util: {utilization:5.1f}%")
                    
                except Exception as e:
                    err = str(e)
                    if "too large" in err:
                        # This shouldn't happen anymore, but just in case
                        print(f"      ⚠️  {symbol}: overflow (skipped)")
                    else:
                        print(f"      ⚠️  {symbol}: {err[:50]}")
                
                time.sleep(0.1)
            
        except Exception as e:
            print(f"   ⚠️  {chain}: {str(e)[:60]}")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Aave V3 rates: {total_count} reserves across {len(AAVE_V3_DATA_PROVIDERS)} chains")
    return total_count


# ============================================================
# 4. COMPOUND V3 RATES — FIX: use getUtilization, safe conversions
# ============================================================

def crawl_compound_rates():
    print("\n🏛️  READING COMPOUND V3 RATES FROM CHAIN")
    
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    
    for market_name, comet_address in COMPOUND_V3_MARKETS.items():
        chain = market_name.split("_")[0]
        asset = market_name.split("_")[1].upper()
        
        try:
            w3 = get_web3(chain)
            block = w3.eth.block_number
            
            comet = w3.eth.contract(
                address=Web3.to_checksum_address(comet_address),
                abi=COMPOUND_V3_ABI
            )
            
            # Try getUtilization first (newer Compound V3)
            try:
                utilization_raw = comet.functions.getUtilization().call()
                # Compound V3 utilization is scaled by 1e18
                utilization = float(utilization_raw) / 1e18 * 100
            except Exception:
                utilization = 0.0
            
            # Get rates using utilization as input if available
            try:
                supply_rate = comet.functions.getSupplyRate(utilization_raw).call()
            except Exception:
                try:
                    supply_rate = comet.functions.getSupplyRate().call()
                except Exception:
                    supply_rate = 0
            
            try:
                borrow_rate = comet.functions.getBorrowRate(utilization_raw).call()
            except Exception:
                try:
                    borrow_rate = comet.functions.getBorrowRate().call()
                except Exception:
                    borrow_rate = 0
            
            # Get total supply/borrow
            try:
                total_supply = float(comet.functions.totalSupply().call())
                total_borrow = float(comet.functions.totalBorrow().call())
            except Exception:
                total_supply = 0.0
                total_borrow = 0.0
            
            # Convert per-second rate to APY
            # Compound V3 rates are per-second, scaled by 1e18
            supply_apy = float(supply_rate) / 1e18 * SECONDS_PER_YEAR * 100
            borrow_apy = float(borrow_rate) / 1e18 * SECONDS_PER_YEAR * 100
            
            if utilization == 0 and total_supply > 0:
                utilization = (total_borrow / total_supply * 100)
            
            conn.execute("""
                INSERT OR REPLACE INTO onchain_lending_rates
                (protocol, chain, asset_symbol, asset_address,
                 supply_apy, borrow_apy, total_supplied_raw, total_borrowed_raw,
                 utilization_rate, block_number, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "compound_v3", chain, asset, comet_address,
                round(supply_apy, 4), round(borrow_apy, 4),
                str(total_supply), str(total_borrow),
                round(utilization, 2), block, now
            ))
            
            count += 1
            print(f"   {market_name:20s}  supply: {supply_apy:6.2f}%  borrow: {borrow_apy:6.2f}%  util: {utilization:5.1f}%")
            
        except Exception as e:
            err = str(e)
            if "execution reverted" in err:
                print(f"   ⚠️  {market_name}: Contract call reverted (may need updated ABI)")
            else:
                print(f"   ⚠️  {market_name}: {err[:60]}")
        
        time.sleep(0.2)
    
    conn.commit()
    conn.close()
    
    print(f"✅ Compound V3 rates: {count} markets")
    return count


# ============================================================
# MAIN
# ============================================================

def main():
    if not HAS_WEB3:
        print("\n❌ Please install web3: pip3 install web3 --break-system-packages")
        print("   Then run this script again.")
        return
    
    start = time.time()
    
    print("=" * 60)
    print("  NERQ CRYPTO — ON-CHAIN DIRECT DATA CRAWLER v2")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print("  Reading directly from blockchains")
    print("  No middlemen. No paid APIs. We own the data.")
    print("=" * 60)
    
    # Test connectivity
    print("\n🔌 TESTING RPC CONNECTIONS")
    connected = []
    for chain in PUBLIC_RPCS:
        try:
            w3 = get_web3(chain)
            block = w3.eth.block_number
            print(f"   ✅ {chain:12s}  block #{block:,}")
            connected.append(chain)
        except Exception as e:
            print(f"   ❌ {chain:12s}  {str(e)[:50]}")
    
    print(f"   Connected to {len(connected)}/{len(PUBLIC_RPCS)} chains")
    
    init_tables()
    
    results = {}
    
    # 1. Stablecoin supply (already works fine)
    results["stablecoin_supply"] = crawl_stablecoin_supply()
    
    # 2. Chainlink oracle feeds (FIXED: round_id as TEXT)
    results["chainlink_feeds"] = crawl_chainlink_feeds()
    
    # 3. Aave V3 lending rates (FIXED: all big ints → float)
    results["aave_v3_rates"] = crawl_aave_rates()
    
    # 4. Compound V3 rates (FIXED: safe conversions)
    results["compound_v3_rates"] = crawl_compound_rates()
    
    elapsed = time.time() - start
    
    # Summary
    print("\n" + "=" * 60)
    print("  ON-CHAIN CRAWL COMPLETE")
    print("=" * 60)
    for key, val in results.items():
        print(f"   {key:25s}  {val:,}")
    
    total = sum(results.values())
    print(f"\n   📊 Total on-chain data points: {total:,}")
    print(f"   ⏱️  Total time: {elapsed:.1f} seconds")
    print(f"\n   🔑 KEY: Zero paid APIs used. All data read directly from blockchains.")
    
    print(f"\n   💡 WHAT WE NOW OWN:")
    print(f"      • Real-time stablecoin supply across {len(STABLECOINS)} stablecoins × {len(connected)} chains")
    print(f"      • {len(CHAINLINK_FEEDS)} Chainlink price feeds — oracle health monitoring")
    print(f"      • Aave V3 lending/borrowing rates across {len(AAVE_V3_DATA_PROVIDERS)} chains")
    print(f"      • Compound V3 rates across {len(COMPOUND_V3_MARKETS)} markets")
    print(f"\n   🚀 NEXT: Add Uniswap pool data, more DeFi protocols, token holders")


if __name__ == "__main__":
    main()
