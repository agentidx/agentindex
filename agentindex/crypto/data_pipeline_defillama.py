#!/usr/bin/env python3
"""
NERQ DATA PIPELINE — DeFiLlama Enrichment
============================================
Fetches data that can catch "looks healthy but dies" tokens:

1. TVL HISTORY per protocol (daily, historical)
   - TVL crash 2-4 weeks before price crash is the #1 signal
   - Maps protocols to their tokens

2. STABLECOIN FLOWS per chain
   - Capital fleeing a chain = early warning for all tokens on it

3. PROTOCOL DETAILS
   - Audits, category, forked_from, listed_at
   - Unaudited protocols die more often

All via DeFiLlama (free, no API key, generous rate limits).
Rate limit: ~500 req/min. We add 0.15s delay to be safe.

Target: enrich crash model features for the 210 tokens we track.
"""

import sqlite3
import os
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "crypto_trust.db")
DATA_DB_PATH = os.path.join(SCRIPT_DIR, "..", "data", "crypto_trust.db")
DELAY = 0.15  # seconds between requests


def fetch_json(url, retries=3):
    """Fetch JSON with retries."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'NERQ-Pipeline/1.0'})
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited
                wait = 5 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            elif e.code == 404:
                return None
            else:
                print(f"    HTTP {e.code} for {url}")
                time.sleep(2)
        except Exception as e:
            print(f"    Error: {e}")
            time.sleep(2)
    return None


def setup_tables(conn):
    """Create tables for DeFiLlama data."""

    conn.execute("""
        CREATE TABLE IF NOT EXISTS defi_tvl_history (
            protocol_id TEXT NOT NULL,
            date TEXT NOT NULL,
            tvl_usd REAL,
            PRIMARY KEY (protocol_id, date)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS defi_protocol_tokens (
            protocol_id TEXT NOT NULL,
            token_id TEXT,
            symbol TEXT,
            name TEXT,
            category TEXT,
            chains TEXT,
            audit_count INTEGER,
            forked_from TEXT,
            listed_at TEXT,
            url TEXT,
            tvl_latest REAL,
            crawled_at TEXT,
            PRIMARY KEY (protocol_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS defi_stablecoin_flows (
            chain TEXT NOT NULL,
            date TEXT NOT NULL,
            total_circulating REAL,
            total_unreliable REAL,
            PRIMARY KEY (chain, date)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS defi_yields (
            pool_id TEXT NOT NULL,
            chain TEXT,
            project TEXT,
            symbol TEXT,
            tvl_usd REAL,
            apy REAL,
            apy_base REAL,
            apy_reward REAL,
            il_risk TEXT,
            stablecoin INTEGER,
            crawled_at TEXT,
            PRIMARY KEY (pool_id)
        )
    """)

    conn.commit()


def get_tracked_tokens(conn):
    """Get tokens we track in NDD (the ones we predict crashes for)."""
    rows = conn.execute("""
        SELECT DISTINCT token_id FROM crypto_ndd_history
    """).fetchall()
    return [r[0] for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Protocol list + token mapping
# ══════════════════════════════════════════════════════════════════════════════

def fetch_protocols(conn):
    """Fetch all protocols from DeFiLlama and map to our tokens."""
    print("\n  STEP 1: Fetching protocol list...")

    data = fetch_json("https://api.llama.fi/protocols")
    if not data:
        print("    Failed to fetch protocols")
        return {}

    print(f"    {len(data)} protocols fetched")

    # Get our tracked tokens
    tracked = set(get_tracked_tokens(conn))
    print(f"    We track {len(tracked)} tokens")

    # Build mapping: gecko_id → protocol
    token_to_protocol = {}
    protocol_count = 0

    for p in data:
        gecko_id = p.get('gecko_id')
        slug = p.get('slug', '')
        name = p.get('name', '')
        category = p.get('category', '')
        chains = json.dumps(p.get('chains', []))
        audit_links = p.get('audit_links') or []
        audit_count = len(audit_links) if isinstance(audit_links, list) else 0
        forked_from = json.dumps(p.get('forkedFrom')) if isinstance(p.get('forkedFrom'), list) else str(p.get('forkedFrom') or '')
        listed_at = str(p.get('listedAt', ''))
        url = p.get('url', '')
        tvl = p.get('tvl') or 0
        symbol = p.get('symbol', '')

        # Store protocol info
        conn.execute("""
            INSERT OR REPLACE INTO defi_protocol_tokens
            (protocol_id, token_id, symbol, name, category, chains,
             audit_count, forked_from, listed_at, url, tvl_latest, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (slug, gecko_id, symbol, name, category, chains,
              audit_count, forked_from, listed_at, url, tvl,
              datetime.now().isoformat()))
        protocol_count += 1

        if gecko_id and gecko_id in tracked:
            token_to_protocol[gecko_id] = slug

    conn.commit()
    print(f"    Stored {protocol_count} protocols")
    print(f"    Matched {len(token_to_protocol)} of our tokens to protocols")

    # Show matched tokens
    if token_to_protocol:
        print(f"    Examples: {list(token_to_protocol.items())[:10]}")

    return token_to_protocol


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: TVL history for matched protocols
# ══════════════════════════════════════════════════════════════════════════════

def fetch_tvl_history(conn, token_to_protocol):
    """Fetch daily TVL history for protocols linked to our tracked tokens."""
    print(f"\n  STEP 2: Fetching TVL history for {len(token_to_protocol)} protocols...")

    # Also fetch top protocols by TVL (even if not directly matched)
    # because TVL drops in major protocols affect the whole ecosystem
    top_protocols = conn.execute("""
        SELECT protocol_id FROM defi_protocol_tokens
        WHERE tvl_latest > 100000000
        ORDER BY tvl_latest DESC LIMIT 100
    """).fetchall()
    top_slugs = {r[0] for r in top_protocols}

    # Combine: our matched tokens + top 100 by TVL
    all_slugs = set(token_to_protocol.values()) | top_slugs
    print(f"    Total protocols to fetch: {len(all_slugs)}")

    fetched = 0
    failed = 0

    for i, slug in enumerate(sorted(all_slugs)):
        if i % 20 == 0:
            print(f"    [{i}/{len(all_slugs)}] Fetching {slug}...")

        # Check if we already have recent data
        existing = conn.execute("""
            SELECT MAX(date) FROM defi_tvl_history WHERE protocol_id = ?
        """, (slug,)).fetchone()[0]

        if existing and existing >= (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"):
            continue  # already fresh

        data = fetch_json(f"https://api.llama.fi/protocol/{slug}")
        time.sleep(DELAY)

        if not data:
            failed += 1
            continue

        tvl_hist = data.get('tvl', [])
        if not tvl_hist:
            continue

        # Insert TVL history
        batch = []
        for point in tvl_hist:
            ts = point.get('date', 0)
            tvl = point.get('totalLiquidityUSD', 0)
            if ts and tvl is not None:
                d = datetime.fromtimestamp(int(float(ts))).strftime("%Y-%m-%d")
                batch.append((slug, d, tvl))

        if batch:
            conn.executemany("""
                INSERT OR REPLACE INTO defi_tvl_history (protocol_id, date, tvl_usd)
                VALUES (?, ?, ?)
            """, batch)
            conn.commit()
            fetched += 1

    print(f"    Fetched: {fetched} | Skipped (fresh): {len(all_slugs)-fetched-failed} | Failed: {failed}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Stablecoin flows per chain
# ══════════════════════════════════════════════════════════════════════════════

def fetch_stablecoin_flows(conn):
    """Fetch stablecoin circulating supply per chain over time."""
    print(f"\n  STEP 3: Fetching stablecoin flows per chain...")

    # Get list of chains
    chains_data = fetch_json("https://stablecoins.llama.fi/stablecoinchains")
    time.sleep(DELAY)

    if not chains_data:
        print("    Failed to fetch chain list")
        return

    # Sort by total stablecoin mcap, take top 20
    chains_sorted = sorted(chains_data, key=lambda x: x.get('totalCirculatingUSD', {}).get('peggedUSD', 0), reverse=True)
    top_chains = [c['name'] for c in chains_sorted[:20] if 'name' in c]
    print(f"    Top 20 chains by stablecoin supply: {top_chains}")

    for i, chain in enumerate(top_chains):
        print(f"    [{i+1}/{len(top_chains)}] {chain}...")

        data = fetch_json(f"https://stablecoins.llama.fi/stablecoincharts/{chain}?stablecoin=1")
        time.sleep(DELAY)

        if not data:
            continue

        batch = []
        for point in data:
            ts = point.get('date', 0)
            circ = point.get('totalCirculating', {}).get('peggedUSD', 0)
            unreliable = point.get('totalCirculatingUSD', {}).get('peggedUSD', 0)
            if ts:
                d = datetime.fromtimestamp(int(float(ts))).strftime("%Y-%m-%d")
                batch.append((chain, d, circ, unreliable))

        if batch:
            conn.executemany("""
                INSERT OR REPLACE INTO defi_stablecoin_flows
                (chain, date, total_circulating, total_unreliable)
                VALUES (?, ?, ?, ?)
            """, batch)
            conn.commit()

    print(f"    Done")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Yield pools (current snapshot)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_yields(conn):
    """Fetch current yield pools — high yields = high risk."""
    print(f"\n  STEP 4: Fetching yield pools...")

    data = fetch_json("https://yields.llama.fi/pools")
    time.sleep(DELAY)

    if not data or 'data' not in data:
        print("    Failed to fetch yields")
        return

    pools = data['data']
    print(f"    {len(pools)} pools fetched")

    batch = []
    for p in pools:
        pool_id = p.get('pool', '')
        chain = p.get('chain', '')
        project = p.get('project', '')
        symbol = p.get('symbol', '')
        tvl = p.get('tvlUsd', 0)
        apy = p.get('apy', 0)
        apy_base = p.get('apyBase', 0)
        apy_reward = p.get('apyReward', 0)
        il_risk = p.get('ilRisk', '')
        stablecoin = 1 if p.get('stablecoin', False) else 0

        batch.append((pool_id, chain, project, symbol, tvl, apy,
                      apy_base or 0, apy_reward or 0, il_risk or '',
                      stablecoin, datetime.now().isoformat()))

    if batch:
        conn.executemany("""
            INSERT OR REPLACE INTO defi_yields
            (pool_id, chain, project, symbol, tvl_usd, apy,
             apy_base, apy_reward, il_risk, stablecoin, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)
        conn.commit()

    print(f"    Stored {len(batch)} yield pools")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Summary & what we got
# ══════════════════════════════════════════════════════════════════════════════

def summarize(conn):
    """Print summary of what we collected."""
    print(f"\n  {'═'*70}")
    print(f"  DATA COLLECTION SUMMARY")
    print(f"  {'═'*70}")

    for table in ['defi_tvl_history', 'defi_protocol_tokens', 'defi_stablecoin_flows', 'defi_yields']:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {cnt} rows")

    # TVL history coverage
    tvl_protocols = conn.execute("SELECT COUNT(DISTINCT protocol_id) FROM defi_tvl_history").fetchone()[0]
    tvl_dates = conn.execute("SELECT MIN(date), MAX(date) FROM defi_tvl_history").fetchone()
    print(f"\n  TVL history: {tvl_protocols} protocols, {tvl_dates[0]} to {tvl_dates[1]}")

    # How many of our NDD tokens have TVL data?
    matched = conn.execute("""
        SELECT COUNT(DISTINCT dpt.token_id)
        FROM defi_protocol_tokens dpt
        JOIN crypto_ndd_history ndd ON ndd.token_id = dpt.token_id
        WHERE dpt.token_id IS NOT NULL
    """).fetchone()[0]
    total_ndd = conn.execute("SELECT COUNT(DISTINCT token_id) FROM crypto_ndd_history").fetchone()[0]
    print(f"  NDD tokens with protocol match: {matched} / {total_ndd}")

    # Audit distribution
    audited = conn.execute("SELECT COUNT(*) FROM defi_protocol_tokens WHERE audit_count > 0").fetchone()[0]
    unaudited = conn.execute("SELECT COUNT(*) FROM defi_protocol_tokens WHERE audit_count = 0").fetchone()[0]
    print(f"  Audited protocols: {audited} | Unaudited: {unaudited}")

    # Stablecoin chains
    sc_chains = conn.execute("SELECT COUNT(DISTINCT chain) FROM defi_stablecoin_flows").fetchone()[0]
    sc_dates = conn.execute("SELECT MIN(date), MAX(date) FROM defi_stablecoin_flows").fetchone()
    if sc_dates[0]:
        print(f"  Stablecoin flows: {sc_chains} chains, {sc_dates[0]} to {sc_dates[1]}")

    # Yield pools
    yield_cnt = conn.execute("SELECT COUNT(*) FROM defi_yields").fetchone()[0]
    high_yield = conn.execute("SELECT COUNT(*) FROM defi_yields WHERE apy > 100").fetchone()[0]
    print(f"  Yield pools: {yield_cnt} total, {high_yield} with APY > 100%")

    # Show some matched token examples with TVL
    print(f"\n  EXAMPLE: Tokens with TVL history")
    examples = conn.execute("""
        SELECT dpt.token_id, dpt.name, dpt.category, dpt.audit_count, dpt.tvl_latest,
               COUNT(tvl.date) as tvl_days
        FROM defi_protocol_tokens dpt
        JOIN defi_tvl_history tvl ON tvl.protocol_id = dpt.protocol_id
        WHERE dpt.token_id IN (SELECT DISTINCT token_id FROM crypto_ndd_history)
        GROUP BY dpt.token_id
        ORDER BY dpt.tvl_latest DESC
        LIMIT 15
    """).fetchall()

    print(f"  {'Token':<25} {'Category':<15} {'Audits':>7} {'TVL':>15} {'Days':>6}")
    print(f"  {'─'*70}")
    for tok, name, cat, aud, tvl, days in examples:
        tvl_str = f"${tvl/1e9:.1f}B" if tvl > 1e9 else f"${tvl/1e6:.0f}M" if tvl > 1e6 else f"${tvl:.0f}"
        print(f"  {(tok or '?')[:25]:<25} {(cat or '?')[:15]:<15} {aud or 0:>7} {tvl_str:>15} {days:>6}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("="*80)
    print("  NERQ DATA PIPELINE — DeFiLlama Enrichment")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    conn = sqlite3.connect(DB_PATH)
    setup_tables(conn)

    # Step 1: Protocol list + token mapping
    token_to_protocol = fetch_protocols(conn)

    # Step 2: TVL history
    fetch_tvl_history(conn, token_to_protocol)

    # Step 3: Stablecoin flows
    fetch_stablecoin_flows(conn)

    # Step 4: Yields
    fetch_yields(conn)

    # Summary
    summarize(conn)

    conn.close()
    print(f"\n  Pipeline complete.")


if __name__ == "__main__":
    main()
