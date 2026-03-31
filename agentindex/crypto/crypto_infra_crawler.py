"""
Nerq Crypto — Bridges, Stablecoins & Chains Crawler
Priority data entities from DeFiLlama (all free, no API key).

Usage:
    python3 crypto_infra_crawler.py              # Crawl all three
    python3 crypto_infra_crawler.py --bridges     # Only bridges
    python3 crypto_infra_crawler.py --stablecoins # Only stablecoins
    python3 crypto_infra_crawler.py --chains      # Only chains
    python3 crypto_infra_crawler.py --stats       # Show stats
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ requests not installed")
    sys.exit(1)

from crypto_models import get_db, init_db


def _n(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError, OverflowError):
        return None


def api_get(url, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "Nerq/1.0 (https://nerq.ai)"
            })
            if resp.status_code == 200:
                return resp.json()
            print(f"  ⚠️ HTTP {resp.status_code} for {url}")
            time.sleep(2)
        except Exception as e:
            print(f"  ⚠️ Error: {e}")
            time.sleep(2)
    return None


# ══════════════════════════════════════════════════════════════════
# DB SCHEMA
# ══════════════════════════════════════════════════════════════════

def init_infra_tables():
    conn = get_db()

    # ── Bridges ───────────────────────────────────────────
    conn.execute("""
    CREATE TABLE IF NOT EXISTS crypto_bridges (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        display_name TEXT,
        
        -- Volume & activity
        volume_24h_usd REAL,
        volume_prev_day_usd REAL,
        volume_change_pct REAL,
        
        -- Chains connected
        destination_chains TEXT,         -- JSON array
        source_chains TEXT,              -- JSON array  
        num_chains INTEGER DEFAULT 0,
        
        -- Metadata
        url TEXT,
        
        -- Trust signals
        hack_history TEXT,               -- JSON from DeFiLlama hacks
        total_stolen_usd REAL DEFAULT 0,
        
        -- Trust Score
        trust_score REAL,
        trust_grade TEXT,
        security_score REAL,
        compliance_score REAL,
        maintenance_score REAL,
        popularity_score REAL,
        ecosystem_score REAL,
        
        crawled_at TEXT NOT NULL,
        scored_at TEXT
    )
    """)

    # ── Stablecoins ───────────────────────────────────────
    conn.execute("""
    CREATE TABLE IF NOT EXISTS crypto_stablecoins (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        symbol TEXT,
        
        -- Peg data
        peg_type TEXT,                   -- 'USD', 'EUR', 'BTC', 'algorithmic'
        peg_mechanism TEXT,              -- 'fiat-backed', 'crypto-backed', 'algorithmic', 'hybrid'
        price_usd REAL,
        
        -- Market cap per chain
        circulating_usd REAL,
        circulating_by_chain TEXT,       -- JSON dict {chain: amount}
        
        -- Stability signals
        depeg_events TEXT,               -- JSON array of known depegs
        max_depeg_pct REAL,              -- worst depeg ever
        
        -- Backing/reserves
        backing_type TEXT,               -- 'full-reserve', 'partial', 'algorithmic', 'crypto-over-collateralized'
        auditor TEXT,
        attestation_frequency TEXT,      -- 'monthly', 'quarterly', 'none'
        
        -- Chains
        chains TEXT,                     -- JSON array
        num_chains INTEGER DEFAULT 0,
        
        -- Trust Score
        trust_score REAL,
        trust_grade TEXT,
        security_score REAL,
        compliance_score REAL,
        maintenance_score REAL,
        popularity_score REAL,
        ecosystem_score REAL,
        
        crawled_at TEXT NOT NULL,
        scored_at TEXT
    )
    """)

    # ── Chains (L1 + L2) ─────────────────────────────────
    conn.execute("""
    CREATE TABLE IF NOT EXISTS crypto_chains (
        id TEXT PRIMARY KEY,             -- e.g. 'ethereum', 'arbitrum'
        name TEXT NOT NULL,
        
        -- Type
        chain_type TEXT,                 -- 'L1', 'L2-optimistic', 'L2-zk', 'sidechain'
        consensus TEXT,                  -- 'PoS', 'PoW', 'DPoS', 'optimistic-rollup', 'zk-rollup'
        parent_chain TEXT,               -- for L2s: 'ethereum'
        
        -- TVL & activity
        tvl_usd REAL,
        tvl_change_1d REAL,
        tvl_change_7d REAL,
        
        -- Ecosystem
        num_protocols INTEGER DEFAULT 0,
        num_tokens INTEGER DEFAULT 0,
        
        -- Security signals
        validator_count INTEGER,
        is_evm INTEGER DEFAULT 0,
        has_escape_hatch INTEGER DEFAULT 0,  -- L2: can users force-exit?
        sequencer_centralized INTEGER DEFAULT 0,  -- L2 risk
        
        -- Bridge connections
        bridges TEXT,                    -- JSON array of bridge names
        num_bridges INTEGER DEFAULT 0,
        
        -- Trust Score
        trust_score REAL,
        trust_grade TEXT,
        security_score REAL,
        compliance_score REAL,
        maintenance_score REAL,
        popularity_score REAL,
        ecosystem_score REAL,
        
        crawled_at TEXT NOT NULL,
        scored_at TEXT
    )
    """)

    # Indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bridges_trust ON crypto_bridges(trust_score)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stables_trust ON crypto_stablecoins(trust_score)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stables_circ ON crypto_stablecoins(circulating_usd)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chains_tvl ON crypto_chains(tvl_usd)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chains_trust ON crypto_chains(trust_score)")

    conn.commit()
    conn.close()
    print("✅ Infrastructure tables initialized")


# ══════════════════════════════════════════════════════════════════
# BRIDGES
# ══════════════════════════════════════════════════════════════════

def crawl_bridges():
    print("\n🌉 CRAWLING BRIDGES")

    data = api_get("https://bridges.llama.fi/bridges?includeChains=true")
    if not data:
        print("❌ Failed to fetch bridges")
        return 0

    bridges = data.get("bridges", data) if isinstance(data, dict) else data
    print(f"   Received {len(bridges)} bridges\n")

    # Also get hack data for bridges
    hacks_data = api_get("https://api.llama.fi/hacks")
    bridge_hacks = {}
    if hacks_data:
        for h in hacks_data:
            target = (h.get("target_type") or "").lower()
            name = (h.get("name") or "").lower()
            if target == "bridge" or "bridge" in name:
                key = name.replace(" bridge", "").replace(" ", "-")
                if key not in bridge_hacks:
                    bridge_hacks[key] = []
                bridge_hacks[key].append({
                    "date": h.get("date", ""),
                    "amount_usd": _n(h.get("amount")),
                    "classification": h.get("classification", ""),
                    "technique": h.get("technique", ""),
                })

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for b in bridges:
        bridge_id = b.get("id")
        if not bridge_id:
            continue

        name = b.get("displayName") or b.get("name", "")
        dest_chains = b.get("destinationChain") or b.get("chains", [])
        if isinstance(dest_chains, str):
            dest_chains = [dest_chains]

        # Match hack data
        name_key = name.lower().replace(" ", "-")
        hacks = bridge_hacks.get(name_key, [])
        total_stolen = sum(h.get("amount_usd") or 0 for h in hacks)

        conn.execute("""
            INSERT OR REPLACE INTO crypto_bridges (
                id, name, display_name,
                volume_24h_usd, volume_prev_day_usd,
                destination_chains, num_chains,
                url, hack_history, total_stolen_usd,
                crawled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            bridge_id, name, name,
            _n(b.get("currentDayVolume")),
            _n(b.get("prevDayVolume")),
            json.dumps(dest_chains),
            len(dest_chains) if isinstance(dest_chains, list) else 0,
            b.get("url", ""),
            json.dumps(hacks) if hacks else None,
            total_stolen,
            now
        ))
        count += 1

    conn.commit()
    conn.close()

    hacked_count = sum(1 for h in bridge_hacks.values() if h)
    print(f"✅ Bridges crawled: {count}")
    print(f"   With hack history: {hacked_count}")
    return count


# ══════════════════════════════════════════════════════════════════
# STABLECOINS
# ══════════════════════════════════════════════════════════════════

# Curated backing data for major stablecoins
STABLECOIN_BACKING = {
    "tether": {"peg_mechanism": "fiat-backed", "backing_type": "full-reserve", "auditor": "BDO Italia", "attestation_frequency": "quarterly"},
    "usd-coin": {"peg_mechanism": "fiat-backed", "backing_type": "full-reserve", "auditor": "Deloitte", "attestation_frequency": "monthly"},
    "dai": {"peg_mechanism": "crypto-backed", "backing_type": "crypto-over-collateralized", "auditor": "Multiple", "attestation_frequency": "real-time"},
    "binance-usd": {"peg_mechanism": "fiat-backed", "backing_type": "full-reserve", "auditor": "Withum", "attestation_frequency": "monthly"},
    "frax": {"peg_mechanism": "hybrid", "backing_type": "partial", "auditor": "None", "attestation_frequency": "none"},
    "true-usd": {"peg_mechanism": "fiat-backed", "backing_type": "full-reserve", "auditor": "Armanino (dropped)", "attestation_frequency": "none"},
    "pax-dollar": {"peg_mechanism": "fiat-backed", "backing_type": "full-reserve", "auditor": "Withum", "attestation_frequency": "monthly"},
    "usdd": {"peg_mechanism": "algorithmic", "backing_type": "partial", "auditor": "None", "attestation_frequency": "none"},
    "gemini-dollar": {"peg_mechanism": "fiat-backed", "backing_type": "full-reserve", "auditor": "BPM", "attestation_frequency": "monthly"},
    "ethena-usde": {"peg_mechanism": "hybrid", "backing_type": "delta-neutral", "auditor": "Multiple", "attestation_frequency": "real-time"},
    "first-digital-usd": {"peg_mechanism": "fiat-backed", "backing_type": "full-reserve", "auditor": "Prescient Assurance", "attestation_frequency": "monthly"},
    "paypal-usd": {"peg_mechanism": "fiat-backed", "backing_type": "full-reserve", "auditor": "EY", "attestation_frequency": "monthly"},
    "ondo-us-dollar-yield": {"peg_mechanism": "fiat-backed", "backing_type": "treasury-backed", "auditor": "NAV Consulting", "attestation_frequency": "daily"},
}

# Known depeg events
DEPEG_EVENTS = {
    "tether": [{"date": "2022-05-12", "low_price": 0.9485, "duration_hours": 48, "trigger": "UST contagion"}],
    "usd-coin": [{"date": "2023-03-11", "low_price": 0.878, "duration_hours": 72, "trigger": "SVB exposure ($3.3B)"}],
    "dai": [{"date": "2020-03-12", "low_price": 0.945, "duration_hours": 24, "trigger": "Black Thursday liquidations"}],
    "terrausd": [{"date": "2022-05-09", "low_price": 0.0, "duration_hours": 9999, "trigger": "Algorithmic death spiral"}],
    "usdd": [{"date": "2022-06-13", "low_price": 0.928, "duration_hours": 168, "trigger": "Market fear + thin reserves"}],
    "iron-titanium-token": [{"date": "2021-06-16", "low_price": 0.0, "duration_hours": 9999, "trigger": "Algorithmic death spiral (Iron Finance)"}],
}


def crawl_stablecoins():
    print("\n💵 CRAWLING STABLECOINS")

    data = api_get("https://stablecoins.llama.fi/stablecoins?includePrices=true")
    if not data:
        print("❌ Failed to fetch stablecoins")
        return 0

    stables = data.get("peggedAssets", [])
    print(f"   Received {len(stables)} stablecoins\n")

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for s in stables:
        stable_id = s.get("gecko_id") or s.get("name", "").lower().replace(" ", "-")
        name = s.get("name", "")
        symbol = s.get("symbol", "")

        # Circulating supply
        circ = _n(s.get("circulating", {}).get("peggedUSD")) if isinstance(s.get("circulating"), dict) else _n(s.get("circulating"))

        # Chain distribution
        chain_circ = s.get("chainCirculating", {})
        chains = list(chain_circ.keys()) if chain_circ else []
        circ_by_chain = {}
        for chain, data_val in (chain_circ or {}).items():
            if isinstance(data_val, dict):
                amt = data_val.get("current", {}).get("peggedUSD")
            else:
                amt = data_val
            if amt:
                circ_by_chain[chain] = _n(amt)

        # Peg type
        peg_type = "USD"
        if s.get("pegType"):
            peg_type = s["pegType"].replace("peggedUSD", "USD").replace("peggedEUR", "EUR").replace("peggedBTC", "BTC")

        # Backing data from curated list
        backing = STABLECOIN_BACKING.get(stable_id, {})
        depegs = DEPEG_EVENTS.get(stable_id, [])
        max_depeg = 0
        if depegs:
            max_depeg = max((1 - (d.get("low_price") or 1)) * 100 for d in depegs)

        # Price
        price = _n(s.get("price"))

        conn.execute("""
            INSERT OR REPLACE INTO crypto_stablecoins (
                id, name, symbol, peg_type, peg_mechanism, price_usd,
                circulating_usd, circulating_by_chain,
                depeg_events, max_depeg_pct,
                backing_type, auditor, attestation_frequency,
                chains, num_chains,
                crawled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stable_id, name, symbol, peg_type,
            backing.get("peg_mechanism", "unknown"),
            price,
            circ,
            json.dumps(circ_by_chain),
            json.dumps(depegs) if depegs else None,
            max_depeg,
            backing.get("backing_type", "unknown"),
            backing.get("auditor", "unknown"),
            backing.get("attestation_frequency", "unknown"),
            json.dumps(chains),
            len(chains),
            now
        ))
        count += 1

    conn.commit()
    conn.close()
    print(f"✅ Stablecoins crawled: {count}")
    return count


# ══════════════════════════════════════════════════════════════════
# CHAINS
# ══════════════════════════════════════════════════════════════════

# Curated chain metadata
CHAIN_METADATA = {
    "Ethereum": {"chain_type": "L1", "consensus": "PoS", "is_evm": 1, "validator_count": 900000},
    "BSC": {"chain_type": "L1", "consensus": "DPoS", "is_evm": 1, "validator_count": 29, "parent_chain": None},
    "Solana": {"chain_type": "L1", "consensus": "PoS+PoH", "is_evm": 0, "validator_count": 1800},
    "Avalanche": {"chain_type": "L1", "consensus": "Snowball", "is_evm": 1, "validator_count": 1700},
    "Polygon": {"chain_type": "sidechain", "consensus": "PoS", "is_evm": 1, "validator_count": 100, "parent_chain": "Ethereum"},
    "Arbitrum": {"chain_type": "L2-optimistic", "consensus": "optimistic-rollup", "is_evm": 1, "parent_chain": "Ethereum", "sequencer_centralized": 1, "has_escape_hatch": 1},
    "Optimism": {"chain_type": "L2-optimistic", "consensus": "optimistic-rollup", "is_evm": 1, "parent_chain": "Ethereum", "sequencer_centralized": 1, "has_escape_hatch": 1},
    "Base": {"chain_type": "L2-optimistic", "consensus": "optimistic-rollup", "is_evm": 1, "parent_chain": "Ethereum", "sequencer_centralized": 1, "has_escape_hatch": 0},
    "zkSync Era": {"chain_type": "L2-zk", "consensus": "zk-rollup", "is_evm": 1, "parent_chain": "Ethereum", "sequencer_centralized": 1},
    "Linea": {"chain_type": "L2-zk", "consensus": "zk-rollup", "is_evm": 1, "parent_chain": "Ethereum", "sequencer_centralized": 1},
    "Scroll": {"chain_type": "L2-zk", "consensus": "zk-rollup", "is_evm": 1, "parent_chain": "Ethereum", "sequencer_centralized": 1},
    "Blast": {"chain_type": "L2-optimistic", "consensus": "optimistic-rollup", "is_evm": 1, "parent_chain": "Ethereum", "sequencer_centralized": 1},
    "Mantle": {"chain_type": "L2-optimistic", "consensus": "optimistic-rollup", "is_evm": 1, "parent_chain": "Ethereum", "sequencer_centralized": 1},
    "Tron": {"chain_type": "L1", "consensus": "DPoS", "is_evm": 0, "validator_count": 27},
    "Fantom": {"chain_type": "L1", "consensus": "Lachesis (DAG)", "is_evm": 1, "validator_count": 60},
    "Cronos": {"chain_type": "L1", "consensus": "PoA", "is_evm": 1, "validator_count": 30},
    "Gnosis": {"chain_type": "sidechain", "consensus": "PoS", "is_evm": 1, "validator_count": 170000, "parent_chain": "Ethereum"},
    "Sui": {"chain_type": "L1", "consensus": "Mysticeti", "is_evm": 0, "validator_count": 107},
    "Aptos": {"chain_type": "L1", "consensus": "AptosBFT", "is_evm": 0, "validator_count": 120},
    "Near": {"chain_type": "L1", "consensus": "Nightshade (PoS)", "is_evm": 0, "validator_count": 250},
    "Cosmos": {"chain_type": "L1", "consensus": "Tendermint BFT", "is_evm": 0, "validator_count": 180},
    "Cardano": {"chain_type": "L1", "consensus": "Ouroboros (PoS)", "is_evm": 0, "validator_count": 3200},
    "Polkadot": {"chain_type": "L1", "consensus": "NPoS", "is_evm": 0, "validator_count": 300},
    "TON": {"chain_type": "L1", "consensus": "PoS", "is_evm": 0, "validator_count": 350},
    "Sonic": {"chain_type": "L1", "consensus": "Lachesis", "is_evm": 1},
    "Berachain": {"chain_type": "L1", "consensus": "PoL (Proof of Liquidity)", "is_evm": 1},
    "Sei": {"chain_type": "L1", "consensus": "Twin-Turbo", "is_evm": 1},
    "Monad": {"chain_type": "L1", "consensus": "MonadBFT", "is_evm": 1},
    "Celo": {"chain_type": "L2-optimistic", "consensus": "optimistic-rollup", "is_evm": 1, "parent_chain": "Ethereum"},
    "Mode": {"chain_type": "L2-optimistic", "consensus": "optimistic-rollup", "is_evm": 1, "parent_chain": "Ethereum", "sequencer_centralized": 1},
}


def crawl_chains():
    print("\n⛓️  CRAWLING CHAINS")

    # Get chain TVL data
    data = api_get("https://api.llama.fi/v2/chains")
    if not data:
        print("❌ Failed to fetch chains")
        return 0

    print(f"   Received {len(data)} chains\n")

    # Get protocol count per chain
    protocols = api_get("https://api.llama.fi/protocols")
    chain_protocol_count = {}
    if protocols:
        for p in protocols:
            for chain in (p.get("chains") or []):
                chain_protocol_count[chain] = chain_protocol_count.get(chain, 0) + 1

    # Get token count per chain from our DB
    conn = get_db()
    token_chain_counts = {}
    rows = conn.execute("SELECT platforms FROM crypto_tokens WHERE platforms IS NOT NULL AND platforms != '{}'").fetchall()
    for r in rows:
        try:
            platforms = json.loads(r[0])
            for chain in platforms:
                # Normalize chain name
                token_chain_counts[chain] = token_chain_counts.get(chain, 0) + 1
        except:
            pass

    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for c in data:
        name = c.get("name", "")
        chain_id = c.get("gecko_id") or name.lower().replace(" ", "-")

        meta = CHAIN_METADATA.get(name, {})

        # Map DeFiLlama chain name to our platform names for token count
        platform_mappings = {
            "Ethereum": "ethereum", "BSC": "binance-smart-chain",
            "Solana": "solana", "Base": "base", "Polygon": "polygon-pos",
            "Arbitrum": "arbitrum-one", "Avalanche": "avalanche",
            "Optimism": "optimistic-ethereum", "Fantom": "fantom",
            "TON": "the-open-network", "Cronos": "cronos",
            "Gnosis": "xdai", "Tron": "tron",
        }
        platform_key = platform_mappings.get(name, name.lower())
        num_tokens = token_chain_counts.get(platform_key, 0)

        conn.execute("""
            INSERT OR REPLACE INTO crypto_chains (
                id, name, chain_type, consensus, parent_chain,
                tvl_usd, num_protocols, num_tokens,
                validator_count, is_evm,
                has_escape_hatch, sequencer_centralized,
                crawled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chain_id, name,
            meta.get("chain_type", "L1"),
            meta.get("consensus", "unknown"),
            meta.get("parent_chain"),
            _n(c.get("tvl")),
            chain_protocol_count.get(name, 0),
            num_tokens,
            meta.get("validator_count"),
            meta.get("is_evm", 0),
            meta.get("has_escape_hatch", 0),
            meta.get("sequencer_centralized", 0),
            now
        ))
        count += 1

    conn.commit()
    conn.close()
    print(f"✅ Chains crawled: {count}")
    return count


# ══════════════════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════════════════

def print_stats():
    conn = get_db()

    print(f"\n{'='*60}")
    print(f"  INFRASTRUCTURE DATA STATS")
    print(f"{'='*60}")

    # Bridges
    try:
        bridges = conn.execute("SELECT COUNT(*) FROM crypto_bridges").fetchone()[0]
        hacked_bridges = conn.execute("SELECT COUNT(*) FROM crypto_bridges WHERE hack_history IS NOT NULL").fetchone()[0]
        top_bridges = conn.execute("SELECT name, volume_24h_usd, total_stolen_usd FROM crypto_bridges ORDER BY volume_24h_usd DESC NULLS LAST LIMIT 5").fetchall()
        print(f"\n   🌉 BRIDGES: {bridges}")
        print(f"      With hack history: {hacked_bridges}")
        if top_bridges:
            print(f"      Top 5 by volume:")
            for b in top_bridges:
                vol = f"${_n(b['volume_24h_usd'] or 0)/1e6:.0f}M" if b['volume_24h_usd'] else "N/A"
                stolen = f" ⚠️${_n(b['total_stolen_usd'] or 0)/1e6:.0f}M stolen" if b['total_stolen_usd'] else ""
                print(f"        {b['name']:30s} vol: {vol}{stolen}")
    except:
        print("\n   🌉 BRIDGES: table not created yet")

    # Stablecoins
    try:
        stables = conn.execute("SELECT COUNT(*) FROM crypto_stablecoins").fetchone()[0]
        total_circ = conn.execute("SELECT SUM(circulating_usd) FROM crypto_stablecoins").fetchone()[0] or 0
        top_stables = conn.execute("SELECT name, symbol, circulating_usd, peg_mechanism, max_depeg_pct FROM crypto_stablecoins ORDER BY circulating_usd DESC NULLS LAST LIMIT 10").fetchall()
        print(f"\n   💵 STABLECOINS: {stables}")
        print(f"      Total circulating: ${total_circ/1e9:.1f}B")
        if top_stables:
            print(f"      Top 10 by market cap:")
            for s in top_stables:
                circ = f"${_n(s['circulating_usd'] or 0)/1e9:.1f}B" if s['circulating_usd'] and s['circulating_usd'] > 1e9 else f"${_n(s['circulating_usd'] or 0)/1e6:.0f}M"
                mech = s['peg_mechanism'] or 'unknown'
                depeg = f" ⚠️{s['max_depeg_pct']:.1f}% depeg" if s['max_depeg_pct'] and s['max_depeg_pct'] > 1 else ""
                print(f"        {s['symbol'] or '':>6s} {s['name']:25s} {circ:>10s} ({mech}){depeg}")
    except:
        print("\n   💵 STABLECOINS: table not created yet")

    # Chains
    try:
        chains = conn.execute("SELECT COUNT(*) FROM crypto_chains").fetchone()[0]
        l1s = conn.execute("SELECT COUNT(*) FROM crypto_chains WHERE chain_type = 'L1'").fetchone()[0]
        l2s = conn.execute("SELECT COUNT(*) FROM crypto_chains WHERE chain_type LIKE 'L2%'").fetchone()[0]
        evm = conn.execute("SELECT COUNT(*) FROM crypto_chains WHERE is_evm = 1").fetchone()[0]
        top_chains = conn.execute("SELECT name, chain_type, tvl_usd, num_protocols, num_tokens, validator_count FROM crypto_chains ORDER BY tvl_usd DESC NULLS LAST LIMIT 10").fetchall()
        print(f"\n   ⛓️  CHAINS: {chains} ({l1s} L1, {l2s} L2, {evm} EVM)")
        if top_chains:
            print(f"      Top 10 by TVL:")
            for c in top_chains:
                tvl = f"${_n(c['tvl_usd'] or 0)/1e9:.1f}B" if c['tvl_usd'] and c['tvl_usd'] > 1e9 else f"${_n(c['tvl_usd'] or 0)/1e6:.0f}M"
                vals = f" ({c['validator_count']:,} validators)" if c['validator_count'] else ""
                print(f"        {c['name']:20s} {c['chain_type']:15s} TVL: {tvl:>10s}  {c['num_protocols'] or 0} protocols  {c['num_tokens'] or 0} tokens{vals}")
    except:
        print("\n   ⛓️  CHAINS: table not created yet")

    # Grand total
    try:
        tokens = conn.execute("SELECT COUNT(*) FROM crypto_tokens").fetchone()[0]
        exchanges = conn.execute("SELECT COUNT(*) FROM crypto_exchanges").fetchone()[0]
        defi = conn.execute("SELECT COUNT(*) FROM crypto_defi_protocols").fetchone()[0]
        contracts = conn.execute("SELECT COUNT(*) FROM crypto_smart_contracts").fetchone()[0]
        bridges_c = conn.execute("SELECT COUNT(*) FROM crypto_bridges").fetchone()[0]
        stables_c = conn.execute("SELECT COUNT(*) FROM crypto_stablecoins").fetchone()[0]
        chains_c = conn.execute("SELECT COUNT(*) FROM crypto_chains").fetchone()[0]

        grand = tokens + exchanges + defi + contracts + bridges_c + stables_c + chains_c
        print(f"\n   📊 GRAND TOTAL: {grand:,} entities")
        print(f"      Tokens: {tokens:,} | Exchanges: {exchanges:,} | DeFi: {defi:,}")
        print(f"      Contracts: {contracts:,} | Bridges: {bridges_c} | Stables: {stables_c} | Chains: {chains_c}")
    except:
        pass

    conn.close()


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Nerq Crypto — Infrastructure Crawler")
    parser.add_argument("--bridges", action="store_true")
    parser.add_argument("--stablecoins", action="store_true")
    parser.add_argument("--chains", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    init_db()
    init_infra_tables()

    if args.stats:
        print_stats()
        return

    print("=" * 60)
    print("  NERQ CRYPTO — INFRASTRUCTURE CRAWLER")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print("  No API keys needed ✅")
    print("=" * 60)

    start = time.time()
    run_all = not (args.bridges or args.stablecoins or args.chains)

    if run_all or args.bridges:
        crawl_bridges()
    if run_all or args.stablecoins:
        crawl_stablecoins()
    if run_all or args.chains:
        crawl_chains()

    elapsed = time.time() - start
    print(f"\n⏱️  Total time: {elapsed:.1f} seconds")

    print_stats()


if __name__ == "__main__":
    main()
