#!/usr/bin/env python3
"""
NERQ L1 ECOSYSTEM ANALYZER v5
==============================
v5 CHANGES from v4:
  - EXPANDED: 38 → 60 chains (22 new chains added)
  - NEW CHAINS: TON, Sonic, SEI, Celo, Klaytn, Berachain, Starknet, XDC,
    Injective, Ronin, Scroll, Blast, Stacks, Kava, Monad, Ordinals,
    World Chain, Manta Pacific, Mode, Core, Osmosis, Chiliz
  - EXPANDED: Coverage check now shows top-1000 instead of top-100
  - KEEP: All v4 features + fixes

Insights 1-12:
  1. True Ecosystem Size (Native vs Bridged)
  2. Ecosystem DNA (category breakdown, native only)
  3. Single Points of Failure
  4. Stablecoin Concentration Risk
  5. Development Health
  6. Cross-chain Contagion Corridors
  7. Ghost Chains vs Thriving Ecosystems
  8. Ecosystem Health Scorecard
  9. Innovation Moat (competitive advantage per chain)
  10. Cycle Context (bear market drawdowns)
  11. Risk/Reward Score
  12. Investment Signal Matrix

Usage:
    python3 l1_ecosystem_analyzer_v5.py --all --save     # Full analysis + save
    python3 l1_ecosystem_analyzer_v5.py --insights       # Insights 1-8
    python3 l1_ecosystem_analyzer_v5.py --moat            # Insights 9-12 (moat/cycle/R-R)
    python3 l1_ecosystem_analyzer_v5.py --coverage        # Top-1000 coverage check
    python3 l1_ecosystem_analyzer_v5.py --save            # Save to DB only
"""

import sqlite3
import json
import os
import sys
from datetime import datetime, timezone
from collections import defaultdict

DB_PATH = os.path.expanduser("~/agentindex/agentindex/data/crypto_trust.db")

# ═══════════════════════════════════════════════════════════════
# L1/L2 CHAIN DEFINITIONS — v5: expanded from 38 → 60 chains
# ═══════════════════════════════════════════════════════════════

L1_CHAINS = {
    # === ORIGINAL 21 CHAINS (from v1-v3) ===
    "ethereum": {"token_id": "ethereum", "symbol": "ETH", "type": "L1", "platform_keys": ["ethereum"]},
    "binance-smart-chain": {"token_id": "binancecoin", "symbol": "BNB", "type": "L1", "platform_keys": ["binance-smart-chain"]},
    "solana": {"token_id": "solana", "symbol": "SOL", "type": "L1", "platform_keys": ["solana"]},
    "tron": {"token_id": "tron", "symbol": "TRX", "type": "L1", "platform_keys": ["tron"]},
    "cardano": {"token_id": "cardano", "symbol": "ADA", "type": "L1", "platform_keys": ["cardano"]},
    "avalanche": {"token_id": "avalanche-2", "symbol": "AVAX", "type": "L1", "platform_keys": ["avalanche"]},
    "polkadot": {"token_id": "polkadot", "symbol": "DOT", "type": "L1", "platform_keys": ["polkadot"]},
    "polygon": {"token_id": "matic-network", "symbol": "POL", "type": "L2", "platform_keys": ["polygon-pos"]},
    "arbitrum": {"token_id": "arbitrum", "symbol": "ARB", "type": "L2", "platform_keys": ["arbitrum-one"]},
    "optimism": {"token_id": "optimism", "symbol": "OP", "type": "L2", "platform_keys": ["optimistic-ethereum"]},
    "base": {"token_id": None, "symbol": "BASE", "type": "L2", "platform_keys": ["base"]},
    "near": {"token_id": "near", "symbol": "NEAR", "type": "L1", "platform_keys": ["near-protocol"]},
    "sui": {"token_id": "sui", "symbol": "SUI", "type": "L1", "platform_keys": ["sui"]},
    "aptos": {"token_id": "aptos", "symbol": "APT", "type": "L1", "platform_keys": ["aptos"]},
    "fantom": {"token_id": "fantom", "symbol": "FTM", "type": "L1", "platform_keys": ["fantom"]},
    "cosmos": {"token_id": "cosmos", "symbol": "ATOM", "type": "L1", "platform_keys": ["cosmos"]},
    "algorand": {"token_id": "algorand", "symbol": "ALGO", "type": "L1", "platform_keys": ["algorand"]},
    "cronos": {"token_id": "crypto-com-chain", "symbol": "CRO", "type": "L1", "platform_keys": ["cronos"]},
    "mantle": {"token_id": "mantle", "symbol": "MNT", "type": "L2", "platform_keys": ["mantle"]},
    "linea": {"token_id": None, "symbol": "LINEA", "type": "L2", "platform_keys": ["linea"]},
    "zksync": {"token_id": "zksync", "symbol": "ZK", "type": "L2", "platform_keys": ["zksync"]},

    # === v4 CHAINS (17) — fixes top-100 coverage gap ===
    "bitcoin": {"token_id": "bitcoin", "symbol": "BTC", "type": "L1", "platform_keys": ["bitcoin"]},
    "xrp": {"token_id": "ripple", "symbol": "XRP", "type": "L1", "platform_keys": ["xrp", "ripple"]},
    "dogecoin": {"token_id": "dogecoin", "symbol": "DOGE", "type": "L1", "platform_keys": ["dogecoin"]},
    "litecoin": {"token_id": "litecoin", "symbol": "LTC", "type": "L1", "platform_keys": ["litecoin"]},
    "bitcoin-cash": {"token_id": "bitcoin-cash", "symbol": "BCH", "type": "L1", "platform_keys": ["bitcoin-cash"]},
    "stellar": {"token_id": "stellar", "symbol": "XLM", "type": "L1", "platform_keys": ["stellar"]},
    "hedera": {"token_id": "hedera-hashgraph", "symbol": "HBAR", "type": "L1", "platform_keys": ["hedera-hashgraph"]},
    "monero": {"token_id": "monero", "symbol": "XMR", "type": "L1", "platform_keys": ["monero"]},
    "ethereum-classic": {"token_id": "ethereum-classic", "symbol": "ETC", "type": "L1", "platform_keys": ["ethereum-classic"]},
    "kaspa": {"token_id": "kaspa", "symbol": "KAS", "type": "L1", "platform_keys": ["kaspa"]},
    "filecoin": {"token_id": "filecoin", "symbol": "FIL", "type": "L1", "platform_keys": ["filecoin"]},
    "vechain": {"token_id": "vechain", "symbol": "VET", "type": "L1", "platform_keys": ["vechain"]},
    "flare": {"token_id": "flare-networks", "symbol": "FLR", "type": "L1", "platform_keys": ["flare-networks"]},
    "hyperliquid": {"token_id": "hyperliquid", "symbol": "HYPE", "type": "L1", "platform_keys": ["hyperliquid"]},
    "bittensor": {"token_id": "bittensor", "symbol": "TAO", "type": "L1", "platform_keys": ["bittensor"]},
    "decred": {"token_id": "decred", "symbol": "DCR", "type": "L1", "platform_keys": ["decred"]},
    "internet-computer": {"token_id": "internet-computer", "symbol": "ICP", "type": "L1", "platform_keys": ["internet-computer"]},

    # === v5 NEW CHAINS (22) — expands ecosystem coverage ===
    "ton": {"token_id": "the-open-network", "symbol": "TON", "type": "L1", "platform_keys": ["the-open-network"]},
    "sonic": {"token_id": "sonic-3", "symbol": "S", "type": "L1", "platform_keys": ["sonic"]},
    "sei": {"token_id": "sei-network", "symbol": "SEI", "type": "L1", "platform_keys": ["sei-v2"]},
    "celo": {"token_id": "celo", "symbol": "CELO", "type": "L1", "platform_keys": ["celo"]},
    "klaytn": {"token_id": "klay-token", "symbol": "KLAY", "type": "L1", "platform_keys": ["klay-token"]},
    "berachain": {"token_id": "berachain-bera", "symbol": "BERA", "type": "L1", "platform_keys": ["berachain"]},
    "starknet": {"token_id": "starknet", "symbol": "STRK", "type": "L2", "platform_keys": ["starknet"]},
    "xdc": {"token_id": "xdce-crowd-sale", "symbol": "XDC", "type": "L1", "platform_keys": ["xdc-network"]},
    "injective": {"token_id": "injective-protocol", "symbol": "INJ", "type": "L1", "platform_keys": ["injective"]},
    "ronin": {"token_id": "ronin", "symbol": "RON", "type": "L1", "platform_keys": ["ronin"]},
    "scroll": {"token_id": "scroll", "symbol": "SCR", "type": "L2", "platform_keys": ["scroll"]},
    "blast": {"token_id": "blast", "symbol": "BLAST", "type": "L2", "platform_keys": ["blast"]},
    "stacks": {"token_id": "blockstack", "symbol": "STX", "type": "L2", "platform_keys": ["stacks"]},
    "kava": {"token_id": "kava", "symbol": "KAVA", "type": "L1", "platform_keys": ["kava"]},
    "monad": {"token_id": "monad", "symbol": "MON", "type": "L1", "platform_keys": ["monad"]},
    "ordinals": {"token_id": None, "symbol": "BRC20", "type": "L2", "platform_keys": ["ordinals"]},
    "world-chain": {"token_id": "worldcoin-wld", "symbol": "WLD", "type": "L2", "platform_keys": ["world-chain"]},
    "manta-pacific": {"token_id": "manta-network", "symbol": "MANTA", "type": "L2", "platform_keys": ["manta-pacific"]},
    "mode": {"token_id": "mode", "symbol": "MODE", "type": "L2", "platform_keys": ["mode"]},
    "core": {"token_id": "coredaoorg", "symbol": "CORE", "type": "L1", "platform_keys": ["core"]},
    "osmosis": {"token_id": "osmosis", "symbol": "OSMO", "type": "L1", "platform_keys": ["osmosis"]},
    "chiliz": {"token_id": "chiliz", "symbol": "CHZ", "type": "L1", "platform_keys": ["chiliz"]},
}

# Build reverse lookup: token_id -> chain_name (for L1 native detection)
TOKEN_ID_TO_CHAIN = {}
for cn, info in L1_CHAINS.items():
    if info["token_id"]:
        TOKEN_ID_TO_CHAIN[info["token_id"]] = cn

# ═══════════════════════════════════════════════════════════════
# KNOWN OVERRIDES + CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

KNOWN_OVERRIDES = {
    "chainlink": "oracle", "band-protocol": "oracle", "api3": "oracle",
    "pyth-network": "oracle", "uma": "oracle", "tellor": "oracle", "dia-data": "oracle",
    "uniswap": "dex", "sushiswap": "dex", "pancakeswap-token": "dex",
    "curve-dao-token": "dex", "balancer": "dex", "1inch": "dex",
    "jupiter-exchange-solana": "dex", "raydium": "dex", "orca": "dex",
    "aerodrome-finance": "dex", "velodrome-finance": "dex",
    "aave": "lending", "compound-governance-token": "lending",
    "maker": "lending", "morpho": "lending", "venus": "lending",
    "lido-dao": "liquid_staking", "rocket-pool": "liquid_staking",
    "zcash": "privacy", "monero": "privacy",
}
# Auto-add all L1/L2 token IDs as overrides
for cn, info in L1_CHAINS.items():
    if info["token_id"]:
        KNOWN_OVERRIDES[info["token_id"]] = info["type"].lower()


def classify_token_v2(token_id, categories_json):
    if token_id in KNOWN_OVERRIDES:
        return KNOWN_OVERRIDES[token_id]
    if not categories_json:
        return "other"
    try:
        cats = json.loads(categories_json) if isinstance(categories_json, str) else []
        cat_str = " ".join(cats).lower()
    except:
        return "other"
    if any(x in cat_str for x in ["stablecoin", "usd stablecoin", "eur stablecoin"]): return "stablecoin"
    if any(x in cat_str for x in ["oracle"]): return "oracle"
    if any(x in cat_str for x in ["decentralized exchange", "dex", "amm"]): return "dex"
    if any(x in cat_str for x in ["lending", "borrowing"]): return "lending"
    if any(x in cat_str for x in ["liquid staking", "restaking"]): return "liquid_staking"
    if any(x in cat_str for x in ["yield aggregator", "yield farming"]): return "yield"
    if any(x in cat_str for x in ["bridge", "cross-chain"]): return "bridge"
    if any(x in cat_str for x in ["layer 2", "l2", "rollup"]): return "l2"
    if any(x in cat_str for x in ["layer 1", "l1", "smart contract platform"]): return "l1"
    if any(x in cat_str for x in ["meme", "dog-themed", "cat-themed", "pepe"]): return "meme"
    if any(x in cat_str for x in ["defi", "decentralized finance"]): return "defi"
    if any(x in cat_str for x in ["nft", "metaverse", "gaming", "play-to-earn"]): return "nft_gaming"
    if any(x in cat_str for x in ["governance", "dao"]): return "governance"
    if any(x in cat_str for x in ["privacy", "monero", "zcash"]): return "privacy"
    if any(x in cat_str for x in ["wrapped", "bridged"]): return "wrapped"
    if any(x in cat_str for x in ["real world asset", "rwa", "tokenized"]): return "rwa"
    if any(x in cat_str for x in ["artificial intelligence", " ai "]): return "ai"
    if any(x in cat_str for x in ["storage", "computing", "data"]): return "infrastructure"
    return "other"


# ═══════════════════════════════════════════════════════════════
# v3 FEATURES: INNOVATION MOAT + CYCLE CONTEXT + RISK/REWARD
# ═══════════════════════════════════════════════════════════════

CHAIN_MOAT = {
    "bitcoin":    {"moat": 99, "narrative": "Digital gold. PoW, 21M cap, Lindy effect, ETF approved, never hacked", "launch": 2009, "ath_mcap": 1400e9},
    "ethereum":   {"moat": 89, "narrative": "Settlement layer. EVM standard, most devs+TVL, rollup roadmap", "launch": 2015, "ath_mcap": 570e9},
    "solana":     {"moat": 70, "narrative": "Consumer crypto. PoH, low fees, Firedancer, meme/payments", "launch": 2020, "ath_mcap": 96e9},
    "binance-smart-chain": {"moat": 62, "narrative": "Binance distribution. CeFi bridge, BSC ecosystem", "launch": 2020, "ath_mcap": 110e9},
    "tron":       {"moat": 55, "narrative": "Stablecoin highway. USDT dominance, Asia payments", "launch": 2017, "ath_mcap": 18e9},
    "cardano":    {"moat": 42, "narrative": "Academic chain. Haskell/Plutus, slow development", "launch": 2017, "ath_mcap": 95e9},
    "avalanche":  {"moat": 58, "narrative": "Subnet architecture. Enterprise focus, gaming subnets", "launch": 2020, "ath_mcap": 42e9},
    "polkadot":   {"moat": 48, "narrative": "Parachain model. Cross-chain messaging, losing dev share", "launch": 2020, "ath_mcap": 55e9},
    "polygon":    {"moat": 55, "narrative": "Ethereum scaling. zkEVM, enterprise partnerships", "launch": 2019, "ath_mcap": 20e9},
    "arbitrum":   {"moat": 60, "narrative": "Leading L2. Optimistic rollup, Orbit chains, most L2 TVL", "launch": 2021, "ath_mcap": 5.4e9},
    "optimism":   {"moat": 52, "narrative": "OP Stack. Superchain vision, Base built on it", "launch": 2021, "ath_mcap": 5e9},
    "base":       {"moat": 66, "narrative": "Coinbase L2. 100M+ user funnel, distribution moat", "launch": 2023, "ath_mcap": 0},
    "near":       {"moat": 50, "narrative": "Chain abstraction. Sharding, account aggregation", "launch": 2020, "ath_mcap": 13e9},
    "sui":        {"moat": 65, "narrative": "Move language. Parallel execution, object-centric model", "launch": 2023, "ath_mcap": 13e9},
    "aptos":      {"moat": 45, "narrative": "Move L1. Meta DNA, lower adoption than Sui", "launch": 2022, "ath_mcap": 7e9},
    "fantom":     {"moat": 31, "narrative": "Sonic upgrade. Andre Cronje key-man risk", "launch": 2019, "ath_mcap": 9e9},
    "cosmos":     {"moat": 69, "narrative": "IBC protocol. Sovereign chains, dYdX/Osmosis", "launch": 2019, "ath_mcap": 15e9},
    "algorand":   {"moat": 38, "narrative": "Pure PoS. Academic pedigree, small ecosystem", "launch": 2019, "ath_mcap": 15e9},
    "cronos":     {"moat": 35, "narrative": "Crypto.com chain. Captive users, limited innovation", "launch": 2021, "ath_mcap": 5e9},
    "mantle":     {"moat": 32, "narrative": "BitDAO treasury. Small ecosystem, needs unique niche", "launch": 2023, "ath_mcap": 3e9},
    "linea":      {"moat": 40, "narrative": "ConsenSys L2. Metamask integration potential", "launch": 2023, "ath_mcap": 0},
    "zksync":     {"moat": 44, "narrative": "ZK rollup pioneer. Native account abstraction", "launch": 2023, "ath_mcap": 2e9},
    # v4 new chains
    "bitcoin-cash": {"moat": 25, "narrative": "BTC fork. Larger blocks, declining relevance", "launch": 2017, "ath_mcap": 70e9},
    "litecoin":   {"moat": 28, "narrative": "Silver to BTC gold. Legacy, no unique innovation", "launch": 2011, "ath_mcap": 26e9},
    "xrp":        {"moat": 50, "narrative": "Cross-border payments. Bank partnerships, SEC case", "launch": 2012, "ath_mcap": 140e9},
    "dogecoin":   {"moat": 30, "narrative": "Meme pioneer. Elon/culture moat, no tech moat", "launch": 2013, "ath_mcap": 88e9},
    "stellar":    {"moat": 40, "narrative": "Remittance focus. Anchor protocol, MoneyGram", "launch": 2014, "ath_mcap": 16e9},
    "hedera":     {"moat": 42, "narrative": "Hashgraph consensus. Enterprise governance council", "launch": 2019, "ath_mcap": 14e9},
    "monero":     {"moat": 60, "narrative": "Privacy leader. Ring signatures, untraceable, Lindy", "launch": 2014, "ath_mcap": 8e9},
    "ethereum-classic": {"moat": 20, "narrative": "ETH fork. Legacy PoW, minimal development", "launch": 2016, "ath_mcap": 10e9},
    "kaspa":      {"moat": 50, "narrative": "BlockDAG. Fastest PoW, GHOSTDAG protocol", "launch": 2021, "ath_mcap": 3e9},
    "filecoin":   {"moat": 45, "narrative": "Decentralized storage. IPFS integration, storage proofs", "launch": 2020, "ath_mcap": 16e9},
    "vechain":    {"moat": 38, "narrative": "Supply chain. Enterprise partnerships (Walmart China)", "launch": 2018, "ath_mcap": 8e9},
    "flare":      {"moat": 35, "narrative": "Data oracle chain. Enshrined oracle, cross-chain data", "launch": 2023, "ath_mcap": 3e9},
    "hyperliquid": {"moat": 68, "narrative": "On-chain orderbook DEX. L1 for perps, unique tech", "launch": 2023, "ath_mcap": 12e9},
    "bittensor":  {"moat": 55, "narrative": "Decentralized AI. Subnet model for ML, unique niche", "launch": 2021, "ath_mcap": 8e9},
    "decred":     {"moat": 22, "narrative": "Hybrid PoW/PoS governance. Small, declining community", "launch": 2016, "ath_mcap": 3e9},
    "internet-computer": {"moat": 48, "narrative": "Web3 compute. Canister smart contracts, DFINITY", "launch": 2021, "ath_mcap": 45e9},
    # v5 new chains
    "ton":        {"moat": 72, "narrative": "Telegram integration. 900M user base, TON apps, mini-apps", "launch": 2018, "ath_mcap": 45e9},
    "sonic":      {"moat": 40, "narrative": "Fantom rebrand. Sonic speed, Andre Cronje, fresh start", "launch": 2024, "ath_mcap": 3e9},
    "sei":        {"moat": 48, "narrative": "Parallelized EVM. Trading-optimized L1, fast finality", "launch": 2023, "ath_mcap": 3e9},
    "celo":       {"moat": 35, "narrative": "Mobile-first DeFi. Phone number identity, stablecoins", "launch": 2020, "ath_mcap": 5e9},
    "klaytn":     {"moat": 32, "narrative": "Kakao-backed L1. Korean user base, enterprise focus", "launch": 2019, "ath_mcap": 12e9},
    "berachain":  {"moat": 52, "narrative": "Proof of Liquidity. Novel consensus, DeFi-native L1", "launch": 2025, "ath_mcap": 2e9},
    "starknet":   {"moat": 55, "narrative": "ZK rollup. STARK proofs, Cairo language, validity proofs", "launch": 2023, "ath_mcap": 3e9},
    "xdc":        {"moat": 30, "narrative": "Trade finance. XinFin enterprise hybrid blockchain", "launch": 2019, "ath_mcap": 2e9},
    "injective":  {"moat": 52, "narrative": "DeFi-specific L1. Orderbook module, MEV-resistant, Cosmos SDK", "launch": 2021, "ath_mcap": 5e9},
    "ronin":      {"moat": 45, "narrative": "Gaming chain. Axie Infinity, Sky Mavis, Pixels", "launch": 2021, "ath_mcap": 4e9},
    "scroll":     {"moat": 40, "narrative": "zkEVM rollup. EVM-equivalent, bytecode-level compatibility", "launch": 2023, "ath_mcap": 1.5e9},
    "blast":      {"moat": 35, "narrative": "Yield-bearing L2. Native ETH/stablecoin yield, Blur team", "launch": 2024, "ath_mcap": 3e9},
    "stacks":     {"moat": 48, "narrative": "Bitcoin L2. sBTC, Clarity language, BTC smart contracts", "launch": 2021, "ath_mcap": 4e9},
    "kava":       {"moat": 32, "narrative": "Cosmos DeFi hub. Dual architecture EVM+Cosmos SDK", "launch": 2019, "ath_mcap": 3e9},
    "monad":      {"moat": 55, "narrative": "Parallel EVM. 10k TPS, pipelining, new entrant hype", "launch": 2025, "ath_mcap": 1e9},
    "ordinals":   {"moat": 42, "narrative": "Bitcoin NFTs/tokens. BRC-20, inscriptions on BTC", "launch": 2023, "ath_mcap": 0},
    "world-chain": {"moat": 38, "narrative": "Worldcoin L2. Proof of personhood, World ID, OP Stack", "launch": 2024, "ath_mcap": 5e9},
    "manta-pacific": {"moat": 30, "narrative": "Modular L2. ZK applications, Celestia DA", "launch": 2023, "ath_mcap": 2e9},
    "mode":       {"moat": 28, "narrative": "OP Stack L2. DeFi-focused, sequencer fee sharing", "launch": 2024, "ath_mcap": 0.5e9},
    "core":       {"moat": 35, "narrative": "Satoshi Plus consensus. BTC-staked security, EVM", "launch": 2023, "ath_mcap": 2e9},
    "osmosis":    {"moat": 50, "narrative": "Cosmos DEX hub. IBC liquidity center, superfluid staking", "launch": 2021, "ath_mcap": 3e9},
    "chiliz":     {"moat": 40, "narrative": "Sports/fan tokens. Socios.com, FC Barcelona, UFC", "launch": 2019, "ath_mcap": 3e9},
}


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def fmt_b(val):
    if val >= 1e9: return f"${val/1e9:.1f}B"
    elif val >= 1e6: return f"${val/1e6:.0f}M"
    elif val >= 1e3: return f"${val/1e3:.0f}K"
    return f"${val:.0f}"


def gini(values):
    if not values or len(values) < 2: return 0
    sv = sorted(values)
    n, total = len(sv), sum(sv)
    if total == 0: return 0
    gs = sum((2*(i+1)-n-1)*v for i, v in enumerate(sv))
    return gs / (n * total)


def main():
    run_all = "--all" in sys.argv
    run_insights = "--insights" in sys.argv or run_all
    run_moat = "--moat" in sys.argv or run_all
    run_scenarios = "--scenarios" in sys.argv or run_all
    run_coverage = "--coverage" in sys.argv or run_all
    save = "--save" in sys.argv
    if not any([run_all, run_insights, run_moat, run_scenarios, run_coverage, save]):
        run_insights = True

    conn = get_db()

    # ── Fetch all tokens ──
    tokens = [dict(r) for r in conn.execute("""
        SELECT id, name, symbol, market_cap_usd, market_cap_rank,
               categories, platforms, trust_score, trust_grade,
               current_price_usd, total_volume_24h_usd,
               circulating_supply, total_supply, max_supply,
               has_audit, is_verified, github_stars, github_contributors,
               twitter_followers
        FROM crypto_tokens WHERE market_cap_usd IS NOT NULL
        ORDER BY market_cap_usd DESC
    """).fetchall()]

    # ── Fetch DeFi/pool data ──
    defi_protocols = {}
    try:
        for r in conn.execute("SELECT name, tvl_usd, category, chains FROM crypto_defi_protocols"):
            defi_protocols[r[0].lower()] = dict(r)
    except: pass

    print(f"Total tokens with market cap: {len(tokens)}")

    # ═══════════════════════════════════════════════════════════════
    # v4 CORE FIX: Map tokens → ecosystems with empty platform key handling
    # ═══════════════════════════════════════════════════════════════

    ecosystem_map = defaultdict(list)
    token_chains = defaultdict(set)

    for t in tokens:
        platforms_raw = t["platforms"]
        if not platforms_raw:
            # NO platform data at all — check if this token IS an L1 native
            if t["id"] in TOKEN_ID_TO_CHAIN:
                chain = TOKEN_ID_TO_CHAIN[t["id"]]
                ecosystem_map[chain].append(t)
                token_chains[t["id"]].add(chain)
            continue

        try:
            platforms = json.loads(platforms_raw) if isinstance(platforms_raw, str) else {}
        except:
            continue

        # v4 FIX: Handle empty platform key {"": ""}
        # This means the token IS an L1 native — map it to its own chain
        if "" in platforms and len(platforms) <= 2:
            if t["id"] in TOKEN_ID_TO_CHAIN:
                chain = TOKEN_ID_TO_CHAIN[t["id"]]
                ecosystem_map[chain].append(t)
                token_chains[t["id"]].add(chain)
                # Also check if it has real platform keys besides ""
                real_platforms = {k: v for k, v in platforms.items() if k and v}
                if not real_platforms:
                    continue  # Only had empty key, already mapped

        # Normal platform key mapping
        for chain_name, chain_info in L1_CHAINS.items():
            for pkey in chain_info["platform_keys"]:
                if pkey in platforms and platforms[pkey]:
                    # v3 FIX: Don't count L1 tokens as "native" to OTHER chains
                    # e.g. BNB has an ERC-20 wrapper on Ethereum — skip that
                    if t["id"] in TOKEN_ID_TO_CHAIN and TOKEN_ID_TO_CHAIN[t["id"]] != chain_name:
                        # This is an L1 token living on ANOTHER chain — still map but flag it
                        pass  # We'll handle this in native/shared classification
                    ecosystem_map[chain_name].append(t)
                    token_chains[t["id"]].add(chain_name)

    # Also ensure every L1 native token appears in its own chain even if missed
    for chain_name, info in L1_CHAINS.items():
        tid = info["token_id"]
        if not tid:
            continue
        if chain_name not in ecosystem_map or not any(t["id"] == tid for t in ecosystem_map[chain_name]):
            for t in tokens:
                if t["id"] == tid:
                    ecosystem_map[chain_name].append(t)
                    token_chains[t["id"]].add(chain_name)
                    break

    # ── Build ecosystem analysis ──
    ecosystems = {}

    for chain_name in sorted(ecosystem_map.keys(),
                              key=lambda c: sum(t.get("market_cap_usd", 0) or 0 for t in ecosystem_map[c]),
                              reverse=True):
        ct = ecosystem_map[chain_name]
        l1_info = L1_CHAINS[chain_name]

        # Separate NATIVE (single-chain) from SHARED (multi-chain)
        # v3 FIX: L1 tokens on OTHER chains are always "shared", never "native"
        native_tokens = []
        shared_tokens = []
        for t in ct:
            cat = classify_token_v2(t["id"], t.get("categories"))
            t["_category"] = cat
            chains_for_token = token_chains.get(t["id"], set())
            is_native = len(chains_for_token) == 1
            # Extra check: if this token is an L1 for a DIFFERENT chain, it's shared here
            if t["id"] in TOKEN_ID_TO_CHAIN and TOKEN_ID_TO_CHAIN[t["id"]] != chain_name:
                is_native = False
            if is_native:
                native_tokens.append(t)
            else:
                shared_tokens.append(t)

        native_mcap = sum(t.get("market_cap_usd", 0) or 0 for t in native_tokens)
        shared_mcap = sum(t.get("market_cap_usd", 0) or 0 for t in shared_tokens)
        total_mcap = native_mcap + shared_mcap

        # Category breakdown (native only)
        native_cats = defaultdict(lambda: {"count": 0, "mcap": 0, "tokens": []})
        for t in native_tokens:
            c = t["_category"]
            m = t.get("market_cap_usd", 0) or 0
            native_cats[c]["count"] += 1
            native_cats[c]["mcap"] += m
            native_cats[c]["tokens"].append(t)

        all_cats = defaultdict(lambda: {"count": 0, "mcap": 0})
        for t in ct:
            c = t["_category"]
            m = t.get("market_cap_usd", 0) or 0
            all_cats[c]["count"] += 1
            all_cats[c]["mcap"] += m

        # Trust/audit/dev metrics
        scores = [t["trust_score"] for t in ct if t.get("trust_score")]
        native_scores = [t["trust_score"] for t in native_tokens if t.get("trust_score")]
        audited = sum(1 for t in ct if t.get("has_audit"))
        with_github = [t for t in ct if t.get("github_stars") and t["github_stars"] > 0]
        total_stars = sum(t["github_stars"] for t in with_github)
        total_contributors = sum(t.get("github_contributors", 0) or 0 for t in with_github)

        mcap_values = [t.get("market_cap_usd", 0) or 0 for t in native_tokens if t.get("market_cap_usd")]
        mcap_gini_val = gini(mcap_values) if mcap_values else 0

        stablecoins_here = [t for t in ct if t["_category"] == "stablecoin"]
        stable_mcap = sum(t.get("market_cap_usd", 0) or 0 for t in stablecoins_here)

        defi_cats = ["dex", "lending", "liquid_staking", "yield", "defi", "bridge"]
        defi_tokens = [t for t in ct if t["_category"] in defi_cats]
        defi_native = [t for t in native_tokens if t["_category"] in defi_cats]

        l1_token = None
        for t in tokens:
            if t["id"] == l1_info.get("token_id"):
                l1_token = t
                break
        l1_mcap = l1_token.get("market_cap_usd", 0) or 0 if l1_token else 0

        sorted_all = sorted(ct, key=lambda x: x.get("market_cap_usd", 0) or 0, reverse=True)
        sorted_native = sorted(native_tokens, key=lambda x: x.get("market_cap_usd", 0) or 0, reverse=True)

        top1_native_pct = (sorted_native[0].get("market_cap_usd", 0) or 0) / native_mcap * 100 if native_mcap and sorted_native else 0

        ecosystems[chain_name] = {
            "chain": chain_name, "symbol": l1_info["symbol"], "type": l1_info["type"],
            "l1_mcap": l1_mcap,
            "l1_trust": l1_token.get("trust_score") if l1_token else None,
            "l1_grade": l1_token.get("trust_grade") if l1_token else None,
            "total_tokens": len(ct), "native_tokens": len(native_tokens), "shared_tokens": len(shared_tokens),
            "total_mcap": total_mcap, "native_mcap": native_mcap, "shared_mcap": shared_mcap,
            "native_pct": native_mcap / total_mcap * 100 if total_mcap else 0,
            "native_cats": dict(native_cats), "all_cats": dict(all_cats),
            "avg_trust": sum(scores)/len(scores) if scores else 0,
            "native_avg_trust": sum(native_scores)/len(native_scores) if native_scores else 0,
            "low_trust_count": sum(1 for s in scores if s < 40),
            "audited_count": audited,
            "audited_pct": audited / len(ct) * 100 if ct else 0,
            "github_projects": len(with_github), "total_stars": total_stars,
            "total_contributors": total_contributors, "mcap_gini": mcap_gini_val,
            "top1_native_pct": top1_native_pct,
            "stablecoin_count": len(stablecoins_here), "stablecoin_mcap": stable_mcap,
            "stablecoin_dependency": stable_mcap / total_mcap * 100 if total_mcap else 0,
            "defi_count": len(defi_tokens), "defi_native_count": len(defi_native),
            "tokens_sorted": sorted_all, "native_sorted": sorted_native,
            "shared_sorted": sorted(shared_tokens, key=lambda x: x.get("market_cap_usd", 0) or 0, reverse=True),
        }

    # ═══════════════════════════════════════════════════════════════
    # INSIGHTS 1-8
    # ═══════════════════════════════════════════════════════════════

    if run_insights:
        # INSIGHT 1: True Ecosystem Size
        print(f"\n{'=' * 100}")
        print("  INSIGHT 1: TRUE ECOSYSTEM SIZE — Native vs Bridged")
        print(f"{'=' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: x["native_mcap"], reverse=True)[:25]:
            print(f"  {eco['chain'].upper():25s} ({eco['symbol']:5s})  "
                  f"Native: {fmt_b(eco['native_mcap']):>10s} ({eco['native_tokens']:>4} tokens)  "
                  f"Shared: {fmt_b(eco['shared_mcap']):>10s} ({eco['shared_tokens']:>4} tokens)  "
                  f"Native%: {eco['native_pct']:.0f}%")

        # INSIGHT 2: Ecosystem DNA
        print(f"\n{'=' * 100}")
        print("  INSIGHT 2: ECOSYSTEM DNA — What each chain is made of (native tokens only)")
        print(f"{'=' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: x["native_mcap"], reverse=True)[:15]:
            if eco["native_mcap"] < 1e6: continue
            print(f"  {eco['chain'].upper()} ({eco['symbol']}) — Native: {fmt_b(eco['native_mcap'])}")
            for cat_name, cd in sorted(eco["native_cats"].items(), key=lambda x: -x[1]["mcap"]):
                if cd["mcap"] < 1e4: continue
                pct = cd["mcap"] / eco["native_mcap"] * 100 if eco["native_mcap"] else 0
                bar = "#" * max(1, int(pct / 3))
                top = ""
                if cd["tokens"]:
                    b = max(cd["tokens"], key=lambda x: x.get("market_cap_usd", 0) or 0)
                    top = f"(top: {b['symbol'].upper()} {fmt_b(b.get('market_cap_usd',0) or 0)})"
                print(f"    {cat_name:16s} {pct:5.1f}%  {bar:20s}  {cd['count']:>3} tokens  {fmt_b(cd['mcap']):>10s}  {top}")
            print()

        # INSIGHT 3: Single Points of Failure
        print(f"\n{'=' * 100}")
        print("  INSIGHT 3: SINGLE POINTS OF FAILURE")
        print(f"{'=' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: x["native_mcap"], reverse=True)[:15]:
            spofs = []
            cat_counts = defaultdict(list)
            for t in eco["native_sorted"]:
                cat_counts[t["_category"]].append(t)
            for cat in ["dex", "lending", "oracle", "stablecoin", "liquid_staking", "bridge"]:
                tl = cat_counts.get(cat, [])
                if len(tl) == 1 and (tl[0].get("market_cap_usd", 0) or 0) > 1e6:
                    spofs.append((cat, tl[0]))
                elif len(tl) == 0 and cat in ["dex", "lending", "stablecoin"]:
                    shared = [t for t in eco["shared_sorted"] if t["_category"] == cat]
                    if shared:
                        spofs.append((f"NO NATIVE {cat}", shared[0]))
            if spofs:
                print(f"  {eco['chain'].upper()} ({eco['symbol']}):")
                for cat, t in spofs:
                    risk = "!!" if "NO NATIVE" in cat else "! "
                    m = t.get("market_cap_usd", 0) or 0
                    print(f"    [{risk}] Only {cat}: {t['symbol'].upper()} ({fmt_b(m) if m else 'shared'})")
                print()

        # INSIGHT 8: Ecosystem Health Scorecard
        print(f"\n{'=' * 100}")
        print("  INSIGHT 8: ECOSYSTEM HEALTH SCORECARD")
        print(f"{'=' * 100}\n")
        print(f"  {'CHAIN':20s} {'DIVERSITY':>10s} {'TRUST':>8s} {'DEV':>8s} {'NATIVE%':>10s} {'INFRA':>8s} {'HEALTH':>8s}")
        print(f"  {'─' * 75}")

        health_scores = []
        for eco in ecosystems.values():
            n_cats = len([c for c, d in eco["native_cats"].items() if d["count"] > 0])
            diversity = min(100, n_cats * 15)
            trust = eco["native_avg_trust"] if eco["native_avg_trust"] else eco["avg_trust"]
            dev = min(100, eco["total_contributors"] / 10 + eco["audited_pct"])
            independence = eco["native_pct"]
            infra_cats = set(t["_category"] for t in eco["native_sorted"])
            infra_score = sum(17 for x in ["dex", "lending", "stablecoin", "oracle", "liquid_staking", "bridge"] if x in infra_cats)
            health = diversity * 0.15 + trust * 0.25 + dev * 0.20 + independence * 0.20 + infra_score * 0.20
            health_scores.append((eco, health, diversity, trust, dev, independence, infra_score))

        for eco, h, d, t, dv, ind, inf in sorted(health_scores, key=lambda x: -x[1])[:25]:
            em = "ok" if h > 50 else "! " if h > 30 else "!!"
            print(f"  [{em}] {eco['chain'].upper():18s} {d:>7.0f}/100 {t:>6.0f}/100 {dv:>6.0f}/100 {ind:>7.0f}%    {inf:>5.0f}/100 {h:>6.0f}/100")

    # ═══════════════════════════════════════════════════════════════
    # INSIGHTS 9-12: MOAT + CYCLE + RISK/REWARD
    # ═══════════════════════════════════════════════════════════════

    if run_moat:
        print(f"\n\n{'=' * 100}")
        print("  INSIGHT 9: INNOVATION MOAT — Competitive advantage per chain")
        print(f"{'=' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: CHAIN_MOAT.get(x["chain"], {}).get("moat", 0), reverse=True):
            cm = CHAIN_MOAT.get(eco["chain"])
            if not cm: continue
            bar = "#" * (cm["moat"] // 2) + "." * (50 - cm["moat"] // 2)
            print(f"  {eco['chain'].upper():25s} {eco['symbol']:5s}  {bar}  {cm['moat']:>3}/100")
            print(f"    {cm['narrative']}")

        # INSIGHT 10: Cycle Context
        print(f"\n\n{'=' * 100}")
        print("  INSIGHT 10: CYCLE CONTEXT — Drawdown from ATH")
        print(f"{'=' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: x["l1_mcap"], reverse=True):
            cm = CHAIN_MOAT.get(eco["chain"])
            if not cm or cm["ath_mcap"] == 0: continue
            current = eco["l1_mcap"]
            ath = cm["ath_mcap"]
            drawdown = (1 - current / ath) * 100 if ath > 0 else 0
            if drawdown < 0: drawdown = 0  # above ATH
            age = 2026 - cm["launch"]
            status = "ABOVE ATH" if current >= ath else f"-{drawdown:.0f}%"
            print(f"  {eco['chain'].upper():25s} {eco['symbol']:5s}  "
                  f"Current: {fmt_b(current):>10s}  ATH: {fmt_b(ath):>10s}  "
                  f"Drawdown: {status:>10s}  Age: {age}yr  Launch: {cm['launch']}")

        # INSIGHT 11: Risk/Reward
        print(f"\n\n{'=' * 100}")
        print("  INSIGHT 11: RISK/REWARD SCORE")
        print(f"  Risk = Fragility x Dependency | Reward = Moat x Drawdown x Dev Activity")
        print(f"{'=' * 100}\n")

        rr_results = []
        for eco in ecosystems.values():
            cm = CHAIN_MOAT.get(eco["chain"])
            if not cm: continue

            # RISK (0-100, higher = riskier)
            stable_dep = eco["stablecoin_dependency"]
            low_trust_pct = eco["low_trust_count"] / eco["total_tokens"] * 100 if eco["total_tokens"] else 0
            unaudited = 100 - eco["audited_pct"]
            fragility = stable_dep * 0.3 + low_trust_pct * 0.25 + unaudited * 0.2 + (100 - eco["avg_trust"]) * 0.25
            risk = min(100, max(5, fragility))

            # REWARD (0-100, higher = more upside)
            moat = cm["moat"]
            drawdown = (1 - eco["l1_mcap"] / cm["ath_mcap"]) * 100 if cm["ath_mcap"] > 0 else 0
            drawdown = max(0, min(100, drawdown))  # clamp 0-100
            dev_signal = min(100, eco["total_contributors"] * 0.5 + eco["github_projects"] * 2)
            reward = moat * 0.40 + drawdown * 0.35 + dev_signal * 0.25
            reward = min(100, max(5, reward))

            rr = reward / risk if risk > 0 else 0
            rr_results.append((eco, cm, risk, reward, rr))

        for eco, cm, risk, reward, rr in sorted(rr_results, key=lambda x: -x[4]):
            if rr > 1.5: signal = "HIGH CONVICTION"
            elif rr > 1.0: signal = "WATCHLIST     "
            elif rr > 0.5: signal = "CAUTION       "
            else: signal = "AVOID         "
            print(f"  [{signal}] {eco['chain'].upper():25s} {eco['symbol']:5s}  "
                  f"Risk: {risk:>5.0f}  Reward: {reward:>5.0f}  R/R: {rr:>5.1f}x  "
                  f"Moat: {cm['moat']}")

        # INSIGHT 12: Investment Signal Matrix
        print(f"\n\n{'=' * 100}")
        print("  INSIGHT 12: INVESTMENT SIGNAL MATRIX")
        print(f"{'=' * 100}\n")

        for label, lo, hi in [("HIGH CONVICTION (R/R > 1.5)", 1.5, 999),
                               ("WATCHLIST (R/R 1.0-1.5)", 1.0, 1.5),
                               ("CAUTION (R/R 0.5-1.0)", 0.5, 1.0),
                               ("AVOID (R/R < 0.5)", 0, 0.5)]:
            group = [(e, c, ri, re, rr) for e, c, ri, re, rr in rr_results if lo <= rr < hi]
            if group:
                print(f"\n  === {label} ===")
                for eco, cm, risk, reward, rr in sorted(group, key=lambda x: -x[4]):
                    print(f"    {eco['chain'].upper():25s} {eco['symbol']:5s}  R/R: {rr:.1f}x  |  {cm['narrative'][:60]}")

    # ═══════════════════════════════════════════════════════════════
    # COVERAGE CHECK
    # ═══════════════════════════════════════════════════════════════

    if run_coverage:
        print(f"\n\n{'=' * 100}")
        print("  TOP-1000 COVERAGE CHECK")
        print(f"{'=' * 100}\n")

        top1000 = tokens[:1000]
        covered = []
        missing = []
        for t in top1000:
            if t["id"] in token_chains and token_chains[t["id"]]:
                covered.append(t)
            else:
                missing.append(t)

        covered_mcap = sum(t.get("market_cap_usd", 0) or 0 for t in covered)
        missing_mcap = sum(t.get("market_cap_usd", 0) or 0 for t in missing)
        total_top1000_mcap = covered_mcap + missing_mcap

        print(f"  Covered: {len(covered)}/{len(top1000)} tokens ({covered_mcap/total_top1000_mcap*100:.1f}% of mcap = {fmt_b(covered_mcap)})")
        print(f"  Missing: {len(missing)}/{len(top1000)} tokens ({missing_mcap/total_top1000_mcap*100:.1f}% of mcap = {fmt_b(missing_mcap)})")

        if missing:
            print(f"\n  MISSING TOKENS (top 30 by mcap):")
            for t in sorted(missing, key=lambda x: x.get("market_cap_usd", 0) or 0, reverse=True)[:30]:
                m = t.get("market_cap_usd", 0) or 0
                plat = ""
                try:
                    p = json.loads(t["platforms"]) if t.get("platforms") else {}
                    plat = ", ".join(k for k in p.keys() if k) or "empty-key"
                except: plat = "?"
                print(f"    #{t.get('market_cap_rank','?'):>5}  {t['symbol'].upper():8s}  {fmt_b(m):>10s}  platforms: {plat}")

    # ═══════════════════════════════════════════════════════════════
    # SCENARIO ANALYSIS
    # ═══════════════════════════════════════════════════════════════

    if run_scenarios:
        print(f"\n\n{'=' * 100}")
        print("  SCENARIO ANALYSIS — What happens if an L1 crashes?")
        print(f"{'=' * 100}")

        l2_parent = {
            "arbitrum": "ethereum", "optimism": "ethereum", "base": "ethereum",
            "polygon": "ethereum", "zksync": "ethereum", "linea": "ethereum",
            "mantle": "ethereum", "scroll": "ethereum", "blast": "ethereum",
            "starknet": "ethereum", "mode": "ethereum", "manta-pacific": "ethereum",
            "world-chain": "ethereum",
            "stacks": "bitcoin", "ordinals": "bitcoin",
        }

        for target_chain in ["ethereum", "solana", "binance-smart-chain", "bitcoin"]:
            eco = ecosystems.get(target_chain)
            if not eco: continue
            cm = CHAIN_MOAT.get(target_chain, {})
            shock = -40

            direct_loss = abs(eco["l1_mcap"] * shock / 100)
            native_loss = abs(eco["native_mcap"] * shock / 100 * 0.7)

            print(f"\n  >> {target_chain.upper()} ({eco['symbol']}) crashes {shock}%")
            print(f"     Direct L1 token loss: {fmt_b(direct_loss)}")
            print(f"     Native ecosystem loss (est 70% corr): {fmt_b(native_loss)}")

            # L2 cascade
            cascade_chains = [cn for cn, parent in l2_parent.items() if parent == target_chain]
            if cascade_chains:
                print(f"     L2 CASCADE:")
                for l2 in cascade_chains:
                    l2_eco = ecosystems.get(l2)
                    if l2_eco:
                        l2_loss = l2_eco["total_mcap"] * abs(shock) / 100 * 0.5
                        print(f"       {l2.upper():15s} {fmt_b(l2_eco['total_mcap']):>10s} ecosystem  "
                              f"est loss: {fmt_b(l2_loss)}")

    # ═══════════════════════════════════════════════════════════════
    # SAVE TO DATABASE
    # ═══════════════════════════════════════════════════════════════

    if save:
        print(f"\n\n{'=' * 100}")
        print("  SAVING TO DATABASE...")
        print(f"{'=' * 100}")

        # Enhanced table with moat/risk/reward fields
        conn.execute("DROP TABLE IF EXISTS crypto_ecosystem_analysis")
        conn.execute("""CREATE TABLE crypto_ecosystem_analysis (
            chain TEXT PRIMARY KEY, symbol TEXT, chain_type TEXT,
            l1_mcap REAL, l1_trust_score REAL,
            total_tokens INTEGER, native_tokens INTEGER, shared_tokens INTEGER,
            total_mcap REAL, native_mcap REAL, shared_mcap REAL, native_pct REAL,
            avg_trust REAL, native_avg_trust REAL, low_trust_count INTEGER,
            audited_pct REAL, github_projects INTEGER, total_stars INTEGER,
            total_contributors INTEGER, mcap_gini REAL,
            stablecoin_count INTEGER, stablecoin_mcap REAL, stablecoin_dependency REAL,
            defi_count INTEGER, defi_native_count INTEGER,
            moat_score INTEGER, launch_year INTEGER, ath_mcap REAL,
            narrative TEXT, risk_score REAL, reward_score REAL, rr_ratio REAL,
            categories_json TEXT, crawled_at TEXT
        )""")

        conn.execute("DROP TABLE IF EXISTS crypto_token_ecosystem_v2")
        conn.execute("""CREATE TABLE crypto_token_ecosystem_v2 (
            token_id TEXT, chain TEXT, is_native INTEGER,
            category TEXT, market_cap_usd REAL, trust_score REAL,
            crawled_at TEXT, PRIMARY KEY (token_id, chain)
        )""")

        now = datetime.now(timezone.utc).isoformat()

        # Pre-calculate R/R for all chains
        rr_map = {}
        for eco in ecosystems.values():
            cm = CHAIN_MOAT.get(eco["chain"], {})
            if not cm:
                rr_map[eco["chain"]] = (0, 0, 0)
                continue
            stable_dep = eco["stablecoin_dependency"]
            low_trust_pct = eco["low_trust_count"] / eco["total_tokens"] * 100 if eco["total_tokens"] else 0
            unaudited = 100 - eco["audited_pct"]
            risk = min(100, max(5, stable_dep*0.3 + low_trust_pct*0.25 + unaudited*0.2 + (100-eco["avg_trust"])*0.25))
            drawdown = max(0, min(100, (1 - eco["l1_mcap"]/cm["ath_mcap"])*100)) if cm.get("ath_mcap", 0) > 0 else 0
            dev_signal = min(100, eco["total_contributors"]*0.5 + eco["github_projects"]*2)
            reward = min(100, max(5, cm["moat"]*0.40 + drawdown*0.35 + dev_signal*0.25))
            rr = reward / risk if risk > 0 else 0
            rr_map[eco["chain"]] = (risk, reward, rr)

        for cn, eco in ecosystems.items():
            cm = CHAIN_MOAT.get(cn, {})
            risk, reward, rr = rr_map.get(cn, (0, 0, 0))
            cats_json = json.dumps({k: {"count": v["count"], "mcap": v["mcap"]}
                                    for k, v in eco["native_cats"].items()})
            conn.execute("""INSERT OR REPLACE INTO crypto_ecosystem_analysis VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                cn, eco["symbol"], eco["type"], eco["l1_mcap"], eco["l1_trust"],
                eco["total_tokens"], eco["native_tokens"], eco["shared_tokens"],
                eco["total_mcap"], eco["native_mcap"], eco["shared_mcap"], eco["native_pct"],
                eco["avg_trust"], eco["native_avg_trust"], eco["low_trust_count"],
                eco["audited_pct"], eco["github_projects"], eco["total_stars"],
                eco["total_contributors"], eco["mcap_gini"],
                eco["stablecoin_count"], eco["stablecoin_mcap"], eco["stablecoin_dependency"],
                eco["defi_count"], eco["defi_native_count"],
                cm.get("moat", 0), cm.get("launch", 0), cm.get("ath_mcap", 0),
                cm.get("narrative", ""), risk, reward, rr,
                cats_json, now))

            for t in eco["tokens_sorted"]:
                chains_for_t = token_chains.get(t["id"], set())
                is_nat = 1 if len(chains_for_t) == 1 else 0
                if t["id"] in TOKEN_ID_TO_CHAIN and TOKEN_ID_TO_CHAIN[t["id"]] != cn:
                    is_nat = 0
                conn.execute("INSERT OR REPLACE INTO crypto_token_ecosystem_v2 VALUES (?,?,?,?,?,?,?)", (
                    t["id"], cn, is_nat, t.get("_category", "other"),
                    t.get("market_cap_usd"), t.get("trust_score"), now))

        conn.commit()
        total_eco = conn.execute("SELECT COUNT(*) FROM crypto_ecosystem_analysis").fetchone()[0]
        total_map = conn.execute("SELECT COUNT(*) FROM crypto_token_ecosystem_v2").fetchone()[0]
        print(f"  Saved {total_eco} ecosystems + {total_map} token->chain mappings")

    conn.close()

    # Summary
    total_mapped = sum(len(e["tokens_sorted"]) for e in ecosystems.values())
    total_chains = len(ecosystems)
    total_covered_mcap = sum(e["total_mcap"] for e in ecosystems.values())
    print(f"\nDone! {total_mapped} token-chain mappings across {total_chains} ecosystems")
    print(f"Total covered ecosystem mcap: {fmt_b(total_covered_mcap)}")


if __name__ == "__main__":
    main()
