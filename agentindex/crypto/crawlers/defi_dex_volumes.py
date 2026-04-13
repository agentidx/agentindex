#!/usr/bin/env python3
"""Crawl DeFiLlama DEX volumes and fees per chain.

Stores results in chain_dex_volumes table in crypto_trust.db.
Free API, no auth needed, rate limit 1 req/s.
"""
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

DB_PATH = Path(__file__).resolve().parent.parent / "crypto_trust.db"

DEXS_URL = "https://api.llama.fi/overview/dexs?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true"
FEES_URL = "https://api.llama.fi/overview/fees?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true"

# Map DeFiLlama chain names to our CHAIN_NORM canonical names
CHAIN_MAP = {
    "Binance": "BSC",
    "Avalanche": "Avalanche",
    "Polygon": "Polygon",
    "Arbitrum": "Arbitrum",
    "Optimism": "Optimism",
    "Fantom": "Fantom",
    "Solana": "Solana",
    "Ethereum": "Ethereum",
    "Base": "Base",
    "Sui": "Sui",
    "Ton": "TON",
    "TON": "TON",
    "Tron": "Tron",
    "Cronos": "Cronos",
    "Gnosis": "Gnosis",
    "Celo": "Celo",
    "Moonbeam": "Moonbeam",
    "Moonriver": "Moonriver",
    "Harmony": "Harmony",
    "Klaytn": "Klaytn",
    "Aurora": "Aurora",
    "Near": "Near",
    "Cosmos": "Cosmos",
    "Osmosis": "Osmosis",
    "Cardano": "Cardano",
    "Aptos": "Aptos",
    "Sei": "Sei",
    "Linea": "Linea",
    "Scroll": "Scroll",
    "zkSync Era": "zkSync Era",
    "Mantle": "Mantle",
    "Blast": "Blast",
    "Manta": "Manta",
    "Starknet": "Starknet",
    "Polkadot": "Polkadot",
    "Injective": "Injective",
    "Pulsechain": "Pulsechain",
    "Metis": "Metis",
    "Mode": "Mode",
    "Merlin": "Merlin",
    "Berachain": "Berachain",
}


def _init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chain_dex_volumes (
            chain TEXT PRIMARY KEY,
            daily_volume REAL,
            weekly_volume REAL,
            monthly_volume REAL,
            daily_fees REAL,
            fetched_at TEXT
        )
    """)
    conn.commit()


def _aggregate_chain_volumes(protocols: list) -> dict:
    """Aggregate DEX volumes per chain from protocol-level data."""
    chain_vols = {}  # chain -> {daily, weekly, monthly}

    for proto in protocols:
        chains = proto.get("chains", [])
        breakdown = proto.get("chainBreakdown", {}) or {}
        total_daily = proto.get("total24h") or 0
        total_weekly = proto.get("total7d") or 0
        total_monthly = proto.get("total30d") or 0

        if breakdown:
            for chain_name, chain_data in breakdown.items():
                canon = CHAIN_MAP.get(chain_name, chain_name)
                if canon not in chain_vols:
                    chain_vols[canon] = {"daily": 0, "weekly": 0, "monthly": 0}
                chain_vols[canon]["daily"] += (chain_data.get("total24h") or 0)
                chain_vols[canon]["weekly"] += (chain_data.get("total7d") or 0)
                chain_vols[canon]["monthly"] += (chain_data.get("total30d") or 0)
        elif len(chains) == 1:
            # Single-chain protocol, assign all volume to that chain
            chain_name = chains[0]
            canon = CHAIN_MAP.get(chain_name, chain_name)
            if canon not in chain_vols:
                chain_vols[canon] = {"daily": 0, "weekly": 0, "monthly": 0}
            chain_vols[canon]["daily"] += total_daily
            chain_vols[canon]["weekly"] += total_weekly
            chain_vols[canon]["monthly"] += total_monthly

    return chain_vols


def _aggregate_chain_fees(protocols: list) -> dict:
    """Aggregate fees per chain from protocol-level data."""
    chain_fees = {}  # chain -> daily_fees

    for proto in protocols:
        chains = proto.get("chains", [])
        breakdown = proto.get("chainBreakdown", {}) or {}
        total_daily = proto.get("total24h") or 0

        if breakdown:
            for chain_name, chain_data in breakdown.items():
                canon = CHAIN_MAP.get(chain_name, chain_name)
                chain_fees[canon] = chain_fees.get(canon, 0) + (chain_data.get("total24h") or 0)
        elif len(chains) == 1:
            canon = CHAIN_MAP.get(chains[0], chains[0])
            chain_fees[canon] = chain_fees.get(canon, 0) + total_daily

    return chain_fees


def crawl_dex_volumes():
    """Fetch DEX volumes and fees from DeFiLlama, store in DB."""
    print(f"[{datetime.now():%H:%M:%S}] Fetching DEX volumes...")
    resp = requests.get(DEXS_URL, timeout=30)
    resp.raise_for_status()
    dex_data = resp.json()
    protocols = dex_data.get("protocols", [])
    print(f"  Got {len(protocols)} DEX protocols")

    chain_vols = _aggregate_chain_volumes(protocols)
    print(f"  Aggregated volumes for {len(chain_vols)} chains")

    time.sleep(1)  # Rate limit

    print(f"[{datetime.now():%H:%M:%S}] Fetching fees...")
    resp = requests.get(FEES_URL, timeout=30)
    resp.raise_for_status()
    fees_data = resp.json()
    fee_protocols = fees_data.get("protocols", [])
    print(f"  Got {len(fee_protocols)} fee protocols")

    chain_fees = _aggregate_chain_fees(fee_protocols)
    print(f"  Aggregated fees for {len(chain_fees)} chains")

    # Merge and store
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(DB_PATH))
    _init_db(conn)

    all_chains = set(chain_vols.keys()) | set(chain_fees.keys())
    rows = []
    for chain in sorted(all_chains):
        v = chain_vols.get(chain, {})
        rows.append((
            chain,
            v.get("daily", 0),
            v.get("weekly", 0),
            v.get("monthly", 0),
            chain_fees.get(chain, 0),
            now,
        ))

    from agentindex.crypto.dual_write import dual_executemany
    dual_executemany(conn, """
        INSERT OR REPLACE INTO chain_dex_volumes
        (chain, daily_volume, weekly_volume, monthly_volume, daily_fees, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()

    # Report top chains
    print(f"\n  Stored {len(rows)} chains. Top 15 by daily volume:")
    rows_sorted = sorted(rows, key=lambda r: r[1], reverse=True)
    for r in rows_sorted[:15]:
        print(f"    {r[0]:20s}  ${r[1]/1e6:>10.1f}M daily  ${r[3]/1e6:>8.1f}M weekly  fees ${r[4]/1e6:>6.1f}M")

    conn.close()
    return len(rows)


if __name__ == "__main__":
    crawl_dex_volumes()
