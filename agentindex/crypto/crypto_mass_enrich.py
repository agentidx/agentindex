"""
Nerq Crypto — Mass Token Enrichment
Hämtar kontraktsadresser för ALLA tokens från CoinGecko (1 API call)
och berikar vår DB. Sen kör Etherscan-verifiering på alla EVM-kedjor.

Usage:
    python3 crypto_mass_enrich.py                    # Full enrichment
    python3 crypto_mass_enrich.py --platforms-only    # Only fetch platforms
    python3 crypto_mass_enrich.py --verify            # Only verify contracts
    python3 crypto_mass_enrich.py --verify --limit 2000  # Verify top 2000
    python3 crypto_mass_enrich.py --stats             # Show stats
"""

import argparse
import json
import os
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

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"
DELAY_ETHERSCAN = 0.22  # 5 calls/sec

# EVM chains supported by Etherscan V2
EVM_CHAINS = {
    "ethereum": 1,
    "binance-smart-chain": 56,
    "polygon-pos": 137,
    "arbitrum-one": 42161,
    "optimistic-ethereum": 10,
    "avalanche": 43114,
    "base": 8453,
    "fantom": 250,
    "cronos": 25,
    "linea": 59144,
    "blast": 81457,
    "zksync": 324,
    "scroll": 534352,
    "mantle": 5000,
    "xdai": 100,  # Gnosis
    "sonic": 146,
    "fraxtal": 252,
    "mode": 34443,
    "celo": 42220,
}


# ══════════════════════════════════════════════════════════════════
# STEP 1: Fetch all platforms from CoinGecko (1 API call)
# ══════════════════════════════════════════════════════════════════

def fetch_all_platforms():
    """Fetch platforms for ALL tokens from CoinGecko coins/list. ONE call."""
    print("\n🌐 FETCHING ALL TOKEN PLATFORMS (1 API call)")

    resp = requests.get(
        "https://api.coingecko.com/api/v3/coins/list",
        params={"include_platform": "true"},
        headers={"User-Agent": "Nerq/1.0 (https://nerq.ai)"},
        timeout=60
    )

    if resp.status_code != 200:
        print(f"❌ Failed: HTTP {resp.status_code}")
        return []

    data = resp.json()
    print(f"   Received {len(data):,} tokens from CoinGecko\n")
    return data


def enrich_platforms(data):
    """Update all tokens in DB with platform/contract data."""
    print("📝 ENRICHING TOKEN PLATFORMS")

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    updated = 0
    added = 0
    total_contracts = 0

    for token in data:
        token_id = token.get("id")
        if not token_id:
            continue

        platforms = token.get("platforms") or {}
        # Filter out empty values
        platforms = {k: v for k, v in platforms.items() if v}

        if not platforms:
            continue

        total_contracts += len(platforms)

        # Get primary contract (ethereum first, then largest chain)
        primary = platforms.get("ethereum") or platforms.get("binance-smart-chain") or \
                  platforms.get("polygon-pos") or platforms.get("arbitrum-one") or \
                  platforms.get("base") or platforms.get("solana") or \
                  next(iter(platforms.values()), None)

        # Check if token exists
        existing = conn.execute("SELECT id, platforms FROM crypto_tokens WHERE id = ?", (token_id,)).fetchone()

        if existing:
            # Update platforms and contract_address
            conn.execute("""
                UPDATE crypto_tokens SET
                    platforms = ?,
                    contract_address = ?
                WHERE id = ?
            """, (json.dumps(platforms), primary, token_id))
            updated += 1
        else:
            # Insert new token (minimal data — will be enriched by market crawl)
            conn.execute("""
                INSERT OR IGNORE INTO crypto_tokens (
                    id, symbol, name, platforms, contract_address, crawled_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                token_id,
                token.get("symbol", ""),
                token.get("name", ""),
                json.dumps(platforms),
                primary,
                now
            ))
            added += 1

        if (updated + added) % 5000 == 0:
            conn.commit()
            print(f"   💾 {updated:,} updated, {added:,} added...")

    conn.commit()

    # Stats
    total = conn.execute("SELECT COUNT(*) FROM crypto_tokens").fetchone()[0]
    with_platforms = conn.execute(
        "SELECT COUNT(*) FROM crypto_tokens WHERE platforms IS NOT NULL AND platforms != '{}' AND platforms != ''"
    ).fetchone()[0]

    conn.close()

    print(f"\n✅ Platform enrichment complete:")
    print(f"   Updated: {updated:,} tokens")
    print(f"   Added:   {added:,} new tokens")
    print(f"   Total contracts mapped: {total_contracts:,}")
    print(f"   DB total: {total:,} tokens ({with_platforms:,} with contracts)")

    return updated, added


# ══════════════════════════════════════════════════════════════════
# STEP 2: DeFiLlama extra data
# ══════════════════════════════════════════════════════════════════

def enrich_from_defillama():
    """Pull stablecoin data and yield data from DeFiLlama."""
    print("\n📊 ENRICHING FROM DEFILLAMA")

    conn = get_db()

    # Stablecoins
    print("   Fetching stablecoins...")
    resp = requests.get("https://stablecoins.llama.fi/stablecoins?includePrices=true", timeout=30)
    if resp.status_code == 200:
        stables = resp.json().get("peggedAssets", [])
        stable_count = 0
        for s in stables:
            symbol = (s.get("symbol") or "").lower()
            # Find matching token in our DB
            row = conn.execute("SELECT id FROM crypto_tokens WHERE symbol = ?", (symbol,)).fetchone()
            if row:
                # Add stablecoin tag to categories
                existing = conn.execute("SELECT categories FROM crypto_tokens WHERE id = ?", (row["id"],)).fetchone()
                cats = []
                if existing and existing["categories"]:
                    try:
                        cats = json.loads(existing["categories"])
                    except:
                        pass
                if "Stablecoin" not in cats:
                    cats.append("Stablecoin")
                    conn.execute("UPDATE crypto_tokens SET categories = ? WHERE id = ?",
                               (json.dumps(cats), row["id"]))
                    stable_count += 1
        print(f"   ✅ Tagged {stable_count} stablecoins")
    else:
        print(f"   ⚠️ Stablecoins fetch failed: {resp.status_code}")

    # Bridges
    print("   Fetching bridges...")
    resp = requests.get("https://bridges.llama.fi/bridges?includeChains=true", timeout=30)
    if resp.status_code == 200:
        bridges = resp.json().get("bridges", [])
        print(f"   ✅ {len(bridges)} bridges found (for future Bridge Trust Score)")

    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════
# STEP 3: Etherscan contract verification (all EVM chains)
# ══════════════════════════════════════════════════════════════════

def init_contracts_table():
    conn = get_db()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS crypto_smart_contracts (
        address TEXT NOT NULL,
        chain TEXT NOT NULL DEFAULT 'ethereum',
        name TEXT,
        compiler TEXT,
        optimization INTEGER,
        runs INTEGER,
        is_verified INTEGER DEFAULT 0,
        source_code_available INTEGER DEFAULT 0,
        license_type TEXT,
        is_proxy INTEGER DEFAULT 0,
        implementation_address TEXT,
        has_self_destruct INTEGER DEFAULT 0,
        has_delegatecall INTEGER DEFAULT 0,
        creation_date TEXT,
        creation_tx TEXT,
        transaction_count INTEGER,
        token_name TEXT,
        token_symbol TEXT,
        token_decimals INTEGER,
        token_total_supply TEXT,
        trust_score REAL,
        trust_grade TEXT,
        security_score REAL,
        compliance_score REAL,
        maintenance_score REAL,
        popularity_score REAL,
        ecosystem_score REAL,
        crawled_at TEXT NOT NULL,
        scored_at TEXT,
        PRIMARY KEY (address, chain)
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_chain ON crypto_smart_contracts(chain)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_verified ON crypto_smart_contracts(is_verified)")
    conn.commit()
    conn.close()


def verify_contract(address, chainid):
    """Verify a single contract on Etherscan V2."""
    try:
        resp = requests.get(ETHERSCAN_V2_URL, params={
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
            "chainid": str(chainid),
            "apikey": ETHERSCAN_API_KEY,
        }, timeout=15)

        data = resp.json()
        if data.get("status") != "1" or not data.get("result"):
            return None

        contract = data["result"][0]
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
    except Exception as e:
        return None


def mass_verify_contracts(limit=2000):
    """Verify contracts across all EVM chains for top tokens by market cap."""
    print(f"\n🔍 MASS CONTRACT VERIFICATION (limit: {limit})")

    if not ETHERSCAN_API_KEY:
        print("❌ ETHERSCAN_API_KEY not set")
        return 0

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Get tokens with platform data, ordered by market cap
    rows = conn.execute("""
        SELECT id, name, symbol, platforms, market_cap_rank
        FROM crypto_tokens
        WHERE platforms IS NOT NULL AND platforms != '{}' AND platforms != ''
        ORDER BY market_cap_rank ASC NULLS LAST
        LIMIT ?
    """, (limit,)).fetchall()

    print(f"   {len(rows)} tokens to process\n")

    verified_total = 0
    checked = 0
    chains_checked = {}

    for row in rows:
        token = dict(row)
        try:
            platforms = json.loads(token["platforms"])
        except:
            continue

        for chain_name, address in platforms.items():
            if not address or len(address) < 10:
                continue

            chainid = EVM_CHAINS.get(chain_name)
            if not chainid:
                continue  # Skip non-EVM chains (solana etc)

            # Skip already checked
            existing = conn.execute(
                "SELECT address FROM crypto_smart_contracts WHERE address = ? AND chain = ?",
                (address.lower(), chain_name)
            ).fetchone()
            if existing:
                continue

            # Verify
            info = verify_contract(address, chainid)
            time.sleep(DELAY_ETHERSCAN)
            checked += 1

            if info:
                conn.execute("""
                    INSERT OR REPLACE INTO crypto_smart_contracts (
                        address, chain, name, compiler, optimization, runs,
                        is_verified, source_code_available, license_type,
                        is_proxy, implementation_address,
                        has_self_destruct, has_delegatecall,
                        token_name, token_symbol, crawled_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    address.lower(), chain_name,
                    info.get("name", ""), info.get("compiler", ""),
                    info.get("optimization", 0), info.get("runs", 0),
                    info.get("is_verified", 0), info.get("source_code_available", 0),
                    info.get("license_type", ""),
                    info.get("is_proxy", 0), info.get("implementation_address"),
                    info.get("has_self_destruct", 0), info.get("has_delegatecall", 0),
                    token.get("name", ""), token.get("symbol", ""),
                    now
                ))

                if info["is_verified"]:
                    verified_total += 1

                chains_checked[chain_name] = chains_checked.get(chain_name, 0) + 1

            if checked % 100 == 0:
                conn.commit()
                print(f"   💾 Checked {checked}, verified {verified_total}")

            if checked >= limit * 3:  # Safety limit
                break

        if checked >= limit * 3:
            break

    # Update tokens with verification data
    print(f"\n   Enriching tokens with verification data...")
    enriched = 0
    verified_addrs = conn.execute("""
        SELECT address, chain FROM crypto_smart_contracts WHERE is_verified = 1
    """).fetchall()

    for vc in verified_addrs:
        result = conn.execute("""
            UPDATE crypto_tokens SET has_audit = 1
            WHERE platforms LIKE ? AND has_audit = 0
        """, (f"%{vc['address']}%",))
        enriched += result.rowcount

    conn.commit()
    conn.close()

    print(f"\n✅ Mass verification complete:")
    print(f"   Contracts checked:  {checked:,}")
    print(f"   Verified:           {verified_total:,}")
    print(f"   Tokens enriched:    {enriched:,}")
    print(f"\n   By chain:")
    for chain, count in sorted(chains_checked.items(), key=lambda x: -x[1]):
        print(f"     {chain}: {count}")

    return checked


# ══════════════════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════════════════

def print_stats():
    conn = get_db()

    total = conn.execute("SELECT COUNT(*) FROM crypto_tokens").fetchone()[0]
    with_platforms = conn.execute(
        "SELECT COUNT(*) FROM crypto_tokens WHERE platforms IS NOT NULL AND platforms != '{}' AND platforms != ''"
    ).fetchone()[0]
    with_details = conn.execute(
        "SELECT COUNT(*) FROM crypto_tokens WHERE detail_crawled_at IS NOT NULL"
    ).fetchone()[0]
    with_audit = conn.execute(
        "SELECT COUNT(*) FROM crypto_tokens WHERE has_audit = 1"
    ).fetchone()[0]
    scored = conn.execute(
        "SELECT COUNT(*) FROM crypto_tokens WHERE trust_score IS NOT NULL"
    ).fetchone()[0]

    # Contracts
    contracts = conn.execute("SELECT COUNT(*) FROM crypto_smart_contracts").fetchone()[0]
    verified = conn.execute("SELECT COUNT(*) FROM crypto_smart_contracts WHERE is_verified = 1").fetchone()[0]
    proxy = conn.execute("SELECT COUNT(*) FROM crypto_smart_contracts WHERE is_proxy = 1").fetchone()[0]

    # Chains in platforms
    chain_counts = {}
    rows = conn.execute("SELECT platforms FROM crypto_tokens WHERE platforms IS NOT NULL AND platforms != '{}'").fetchall()
    for r in rows:
        try:
            p = json.loads(r[0])
            for c, addr in p.items():
                if addr:
                    chain_counts[c] = chain_counts.get(c, 0) + 1
        except:
            pass

    print(f"\n📊 COMPREHENSIVE DATA STATS")
    print(f"{'='*60}")
    print(f"   TOKENS")
    print(f"   Total:              {total:,}")
    print(f"   With contracts:     {with_platforms:,} ({with_platforms/total*100:.1f}%)")
    print(f"   With CG details:   {with_details:,} ({with_details/total*100:.1f}%)")
    print(f"   With audit/verify:  {with_audit:,} ({with_audit/total*100:.1f}%)")
    print(f"   Scored:             {scored:,}")
    print(f"\n   SMART CONTRACTS")
    print(f"   Total checked:      {contracts:,}")
    print(f"   Verified:           {verified:,} ({verified/contracts*100:.0f}%)" if contracts else "   None checked")
    print(f"   Proxy:              {proxy:,}" if contracts else "")
    print(f"\n   CONTRACT COVERAGE BY CHAIN (top 20):")
    for chain, count in sorted(chain_counts.items(), key=lambda x: -x[1])[:20]:
        evm = "✅ EVM" if chain in EVM_CHAINS else "  non-EVM"
        print(f"     {count:>6} {chain} {evm}")

    # Exchanges + DeFi
    ex_total = conn.execute("SELECT COUNT(*) FROM crypto_exchanges").fetchone()[0]
    defi_total = conn.execute("SELECT COUNT(*) FROM crypto_defi_protocols").fetchone()[0]
    defi_hacked = conn.execute("SELECT COUNT(*) FROM crypto_defi_protocols WHERE hack_history IS NOT NULL").fetchone()[0]

    print(f"\n   EXCHANGES: {ex_total:,}")
    print(f"   DEFI PROTOCOLS: {defi_total:,} ({defi_hacked} with hack history)")

    grand_total = total + ex_total + defi_total + contracts
    print(f"\n   GRAND TOTAL ENTITIES: {grand_total:,}")

    conn.close()


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Nerq Crypto — Mass Token Enrichment")
    parser.add_argument("--platforms-only", action="store_true", help="Only fetch platform data")
    parser.add_argument("--verify", action="store_true", help="Only verify contracts")
    parser.add_argument("--defillama", action="store_true", help="Only DeFiLlama enrichment")
    parser.add_argument("--limit", type=int, default=2000, help="Contract verification limit")
    parser.add_argument("--stats", action="store_true", help="Show stats")
    args = parser.parse_args()

    init_db()
    init_contracts_table()

    if args.stats:
        print_stats()
        return

    print("=" * 60)
    print("  NERQ CRYPTO — MASS TOKEN ENRICHMENT")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    start = time.time()

    if args.verify:
        mass_verify_contracts(limit=args.limit)
    elif args.platforms_only:
        data = fetch_all_platforms()
        if data:
            enrich_platforms(data)
    elif args.defillama:
        enrich_from_defillama()
    else:
        # Full enrichment
        data = fetch_all_platforms()
        if data:
            enrich_platforms(data)
        enrich_from_defillama()
        if ETHERSCAN_API_KEY:
            mass_verify_contracts(limit=args.limit)

    elapsed = time.time() - start
    print(f"\n⏱️  Total time: {elapsed/60:.1f} minutes")

    print_stats()


if __name__ == "__main__":
    main()
