#!/usr/bin/env python3
"""
NERQ L1 ECOSYSTEM ANALYZER v2
==============================
Deep ecosystem analysis with:
1. Fixed token classification (LINK bug etc)
2. Native vs Bridged mcap separation  
3. Ecosystem Health Score (not just vulnerability)
4. Hidden dependency detection
5. Contagion pathways
6. "What-if" scenario engine
7. Portfolio ecosystem exposure calculator
8. Stablecoin concentration risk per chain
9. Single-point-of-failure detection
10. Cross-chain contagion corridors

Usage:
    python3 l1_ecosystem_analyzer_v2.py --all          # Everything
    python3 l1_ecosystem_analyzer_v2.py --insights      # Key insights only
    python3 l1_ecosystem_analyzer_v2.py --scenarios      # What-if scenarios
    python3 l1_ecosystem_analyzer_v2.py --save           # Save all to DB
"""

import sqlite3
import json
import os
import sys
import math
from datetime import datetime, timezone
from collections import Counter, defaultdict

DB_PATH = os.path.expanduser("~/agentindex/agentindex/data/crypto_trust.db")

L1_CHAINS = {
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
}

# ═══════════════════════════════════════════════════════════
# IMPROVED CLASSIFICATION
# ═══════════════════════════════════════════════════════════

# Known tokens that should override category-based classification
KNOWN_OVERRIDES = {
    "chainlink": "oracle",
    "band-protocol": "oracle",
    "api3": "oracle",
    "pyth-network": "oracle",
    "uma": "oracle",
    "tellor": "oracle",
    "dia-data": "oracle",
    "uniswap": "dex",
    "sushiswap": "dex",
    "pancakeswap-token": "dex",
    "curve-dao-token": "dex",
    "balancer": "dex",
    "1inch": "dex",
    "jupiter-exchange-solana": "dex",
    "raydium": "dex",
    "orca": "dex",
    "aerodrome-finance": "dex",
    "velodrome-finance": "dex",
    "aave": "lending",
    "compound-governance-token": "lending",
    "maker": "lending",
    "morpho": "lending",
    "venus": "lending",
    "lido-dao": "liquid_staking",
    "rocket-pool": "liquid_staking",
    "ethereum": "l1",
    "solana": "l1",
    "binancecoin": "l1",
    "cardano": "l1",
    "avalanche-2": "l1",
    "polkadot": "l1",
    "tron": "l1",
    "near": "l1",
    "sui": "l1",
    "aptos": "l1",
    "cosmos": "l1",
    "fantom": "l1",
    "algorand": "l1",
    "arbitrum": "l2",
    "optimism": "l2",
    "mantle": "l2",
    "zksync": "l2",
    "matic-network": "l2",
    "starknet": "l2",
}


def classify_token_v2(token_id, categories_json):
    """Improved classification with overrides and better category matching."""
    # Check overrides first
    if token_id in KNOWN_OVERRIDES:
        return KNOWN_OVERRIDES[token_id]

    if not categories_json:
        return "other"
    try:
        cats = json.loads(categories_json) if isinstance(categories_json, str) else []
        cat_str = " ".join(cats).lower()
    except:
        return "other"

    # Order matters — check specific before generic
    if any(x in cat_str for x in ["stablecoin", "usd stablecoin", "eur stablecoin"]):
        return "stablecoin"
    if any(x in cat_str for x in ["oracle"]):
        return "oracle"
    if any(x in cat_str for x in ["decentralized exchange", "dex", "amm"]):
        return "dex"
    if any(x in cat_str for x in ["lending", "borrowing"]):
        return "lending"
    if any(x in cat_str for x in ["liquid staking", "restaking"]):
        return "liquid_staking"
    if any(x in cat_str for x in ["yield aggregator", "yield farming"]):
        return "yield"
    if any(x in cat_str for x in ["bridge", "cross-chain"]):
        return "bridge"
    if any(x in cat_str for x in ["layer 2", "l2", "rollup", "zero knowledge", "zk"]):
        return "l2"
    if any(x in cat_str for x in ["layer 1", "l1", "smart contract platform"]):
        return "l1"
    # Meme AFTER infrastructure checks so LINK doesn't match
    if any(x in cat_str for x in ["meme", "dog-themed", "cat-themed", "pepe"]):
        return "meme"
    if any(x in cat_str for x in ["defi", "decentralized finance"]):
        return "defi"
    if any(x in cat_str for x in ["nft", "metaverse", "gaming", "play-to-earn"]):
        return "nft_gaming"
    if any(x in cat_str for x in ["governance", "dao"]):
        return "governance"
    if any(x in cat_str for x in ["privacy", "monero", "zcash"]):
        return "privacy"
    if any(x in cat_str for x in ["wrapped", "bridged"]):
        return "wrapped"
    if any(x in cat_str for x in ["real world asset", "rwa", "tokenized"]):
        return "rwa"
    if any(x in cat_str for x in ["artificial intelligence", " ai "]):
        return "ai"
    if any(x in cat_str for x in ["storage", "computing", "data"]):
        return "infrastructure"
    return "other"


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def fmt_b(val):
    """Format billions."""
    if val >= 1e9:
        return f"${val/1e9:.1f}B"
    elif val >= 1e6:
        return f"${val/1e6:.0f}M"
    elif val >= 1e3:
        return f"${val/1e3:.0f}K"
    return f"${val:.0f}"


def gini(values):
    """Gini coefficient for concentration."""
    if not values or len(values) < 2:
        return 0
    sorted_v = sorted(values)
    n = len(sorted_v)
    total = sum(sorted_v)
    if total == 0:
        return 0
    cumsum = 0
    gini_sum = 0
    for i, v in enumerate(sorted_v):
        cumsum += v
        gini_sum += (2 * (i + 1) - n - 1) * v
    return gini_sum / (n * total)


def main():
    run_all = "--all" in sys.argv
    run_insights = "--insights" in sys.argv or run_all
    run_scenarios = "--scenarios" in sys.argv or run_all
    save = "--save" in sys.argv
    
    if not any([run_all, run_insights, run_scenarios, save]):
        run_insights = True  # default

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

    # ── Fetch DeFi protocol data if available ──
    defi_protocols = {}
    try:
        for r in conn.execute("SELECT name, tvl_usd, category, chains FROM crypto_defi_protocols"):
            defi_protocols[r[0].lower()] = dict(r)
    except:
        pass

    # ── Fetch DEX pool data if available ──
    dex_pools_by_chain = defaultdict(list)
    try:
        for r in conn.execute("SELECT chain, dex, tvl_usd, token0_symbol, token1_symbol FROM crypto_dex_pools WHERE tvl_usd > 0"):
            dex_pools_by_chain[r[0].lower()].append(dict(r))
    except:
        pass

    print(f"📊 Loaded: {len(tokens)} tokens, {len(defi_protocols)} DeFi protocols, "
          f"{sum(len(v) for v in dex_pools_by_chain.values())} DEX pools")

    # ── Map tokens to ecosystems ──
    ecosystem_map = defaultdict(list)
    token_chains = defaultdict(set)

    for t in tokens:
        if not t["platforms"]:
            continue
        try:
            platforms = json.loads(t["platforms"]) if isinstance(t["platforms"], str) else {}
        except:
            continue
        for chain_name, chain_info in L1_CHAINS.items():
            for pkey in chain_info["platform_keys"]:
                if pkey in platforms and platforms[pkey]:
                    ecosystem_map[chain_name].append(t)
                    token_chains[t["id"]].add(chain_name)

    # ── Build ecosystem analysis ──
    ecosystems = {}

    for chain_name in sorted(ecosystem_map.keys(),
                              key=lambda c: len(ecosystem_map[c]), reverse=True):
        ct = ecosystem_map[chain_name]
        l1_info = L1_CHAINS[chain_name]

        # Separate NATIVE (single-chain) from SHARED (multi-chain)
        native_tokens = []
        shared_tokens = []
        for t in ct:
            cat = classify_token_v2(t["id"], t.get("categories"))
            t["_category"] = cat
            if len(token_chains.get(t["id"], set())) == 1:
                native_tokens.append(t)
            else:
                shared_tokens.append(t)

        native_mcap = sum(t.get("market_cap_usd", 0) or 0 for t in native_tokens)
        shared_mcap = sum(t.get("market_cap_usd", 0) or 0 for t in shared_tokens)
        total_mcap = native_mcap + shared_mcap

        # Category breakdown for NATIVE only (true ecosystem value)
        native_cats = defaultdict(lambda: {"count": 0, "mcap": 0, "tokens": []})
        for t in native_tokens:
            cat = t["_category"]
            mcap = t.get("market_cap_usd", 0) or 0
            native_cats[cat]["count"] += 1
            native_cats[cat]["mcap"] += mcap
            native_cats[cat]["tokens"].append(t)

        # Category breakdown for ALL
        all_cats = defaultdict(lambda: {"count": 0, "mcap": 0})
        for t in ct:
            cat = t["_category"]
            mcap = t.get("market_cap_usd", 0) or 0
            all_cats[cat]["count"] += 1
            all_cats[cat]["mcap"] += mcap

        # Trust score analysis
        scores = [t["trust_score"] for t in ct if t.get("trust_score")]
        native_scores = [t["trust_score"] for t in native_tokens if t.get("trust_score")]

        # Audit coverage
        audited = sum(1 for t in ct if t.get("has_audit"))
        verified = sum(1 for t in ct if t.get("is_verified"))

        # GitHub activity (development health)
        with_github = [t for t in ct if t.get("github_stars") and t["github_stars"] > 0]
        total_stars = sum(t["github_stars"] for t in with_github)
        total_contributors = sum(t.get("github_contributors", 0) or 0 for t in with_github)

        # Market cap distribution (Gini)
        mcap_values = [t.get("market_cap_usd", 0) or 0 for t in native_tokens if t.get("market_cap_usd")]
        mcap_gini = gini(mcap_values) if mcap_values else 0

        # Stablecoin analysis
        stablecoins_here = [t for t in ct if t["_category"] == "stablecoin"]
        native_stables = [t for t in native_tokens if t["_category"] == "stablecoin"]
        stable_mcap_all = sum(t.get("market_cap_usd", 0) or 0 for t in stablecoins_here)
        stable_mcap_native = sum(t.get("market_cap_usd", 0) or 0 for t in native_stables)

        # DeFi infrastructure
        defi_cats = ["dex", "lending", "liquid_staking", "yield", "defi", "bridge"]
        defi_tokens = [t for t in ct if t["_category"] in defi_cats]
        defi_native = [t for t in native_tokens if t["_category"] in defi_cats]

        # L1 native token
        l1_token = None
        for t in tokens:
            if t["id"] == l1_info.get("token_id"):
                l1_token = t
                break
        l1_mcap = l1_token.get("market_cap_usd", 0) or 0 if l1_token else 0

        # Sorted tokens
        sorted_all = sorted(ct, key=lambda x: x.get("market_cap_usd", 0) or 0, reverse=True)
        sorted_native = sorted(native_tokens, key=lambda x: x.get("market_cap_usd", 0) or 0, reverse=True)

        # Concentration
        top1_native_pct = (sorted_native[0].get("market_cap_usd", 0) or 0) / native_mcap * 100 if native_mcap and sorted_native else 0

        ecosystems[chain_name] = {
            "chain": chain_name,
            "symbol": l1_info["symbol"],
            "type": l1_info["type"],
            "l1_mcap": l1_mcap,
            "l1_trust": l1_token.get("trust_score") if l1_token else None,
            "l1_grade": l1_token.get("trust_grade") if l1_token else None,
            # Counts
            "total_tokens": len(ct),
            "native_tokens": len(native_tokens),
            "shared_tokens": len(shared_tokens),
            # Market caps
            "total_mcap": total_mcap,
            "native_mcap": native_mcap,
            "shared_mcap": shared_mcap,
            "native_pct": native_mcap / total_mcap * 100 if total_mcap else 0,
            # Categories
            "native_cats": dict(native_cats),
            "all_cats": dict(all_cats),
            # Trust
            "avg_trust": sum(scores) / len(scores) if scores else 0,
            "native_avg_trust": sum(native_scores) / len(native_scores) if native_scores else 0,
            "low_trust_count": sum(1 for s in scores if s < 40),
            # Audit
            "audited_count": audited,
            "audited_pct": audited / len(ct) * 100 if ct else 0,
            "verified_count": verified,
            # Development
            "github_projects": len(with_github),
            "total_stars": total_stars,
            "total_contributors": total_contributors,
            # Distribution
            "mcap_gini": mcap_gini,
            "top1_native_pct": top1_native_pct,
            # Stablecoins
            "stablecoin_count": len(stablecoins_here),
            "stablecoin_mcap": stable_mcap_all,
            "native_stablecoin_mcap": stable_mcap_native,
            "stablecoin_dependency": stable_mcap_all / total_mcap * 100 if total_mcap else 0,
            # DeFi
            "defi_count": len(defi_tokens),
            "defi_native_count": len(defi_native),
            # Raw
            "tokens_sorted": sorted_all,
            "native_sorted": sorted_native,
            "shared_sorted": sorted(shared_tokens, key=lambda x: x.get("market_cap_usd", 0) or 0, reverse=True),
        }

    # ═══════════════════════════════════════════════════════════
    # INSIGHT 1: TRUE ECOSYSTEM SIZE (Native Only)
    # ═══════════════════════════════════════════════════════════

    if run_insights:
        print(f"\n{'═' * 100}")
        print("  📊 INSIGHT 1: TRUE ECOSYSTEM SIZE — Native vs Bridged")
        print(f"  Separates tokens that ONLY exist on this chain from multi-chain tokens like USDC/USDT")
        print(f"{'═' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: x["native_mcap"], reverse=True):
            native_bar_len = min(40, int(eco["native_mcap"] / 5e9)) if eco["native_mcap"] > 0 else 0
            shared_bar_len = min(40, int(eco["shared_mcap"] / 5e9)) if eco["shared_mcap"] > 0 else 0

            print(f"  {eco['chain'].upper():25s} ({eco['symbol']:5s})")
            print(f"    Native (locked-in):  {fmt_b(eco['native_mcap']):>10s}  {'█' * native_bar_len}")
            print(f"    Shared (multi-chain): {fmt_b(eco['shared_mcap']):>10s}  {'░' * shared_bar_len}")
            print(f"    Tokens: {eco['native_tokens']:>5} native / {eco['shared_tokens']:>5} shared")
            print(f"    True ecosystem = {eco['native_pct']:.0f}% native value")
            print()

        # ═══════════════════════════════════════════════════════════
        # INSIGHT 2: CATEGORY DNA — What each ecosystem is made of
        # ═══════════════════════════════════════════════════════════

        print(f"\n{'═' * 100}")
        print("  🧬 INSIGHT 2: ECOSYSTEM DNA — What each chain is actually made of (native tokens only)")
        print(f"{'═' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: x["native_mcap"], reverse=True)[:12]:
            if eco["native_mcap"] < 1e6:
                continue
            print(f"  {eco['chain'].upper()} ({eco['symbol']}) — Native mcap: {fmt_b(eco['native_mcap'])}")

            cats = eco["native_cats"]
            for cat_name, cat_data in sorted(cats.items(), key=lambda x: -x[1]["mcap"]):
                if cat_data["mcap"] < 1e4:
                    continue
                pct = cat_data["mcap"] / eco["native_mcap"] * 100 if eco["native_mcap"] else 0
                bar = "█" * max(1, int(pct / 3))
                top_token = ""
                if cat_data["tokens"]:
                    best = max(cat_data["tokens"], key=lambda x: x.get("market_cap_usd", 0) or 0)
                    top_token = f"(top: {best['symbol'].upper()} {fmt_b(best.get('market_cap_usd',0) or 0)})"
                print(f"    {cat_name:16s} {pct:5.1f}%  {bar:20s}  {cat_data['count']:>3} tokens  {fmt_b(cat_data['mcap']):>10s}  {top_token}")
            print()

        # ═══════════════════════════════════════════════════════════
        # INSIGHT 3: SINGLE POINTS OF FAILURE
        # ═══════════════════════════════════════════════════════════

        print(f"\n{'═' * 100}")
        print("  ⚠️  INSIGHT 3: SINGLE POINTS OF FAILURE")
        print(f"  Tokens/protocols that are critical infrastructure with no alternatives on-chain")
        print(f"{'═' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: x["native_mcap"], reverse=True)[:10]:
            spofs = []
            native = eco["native_sorted"]

            # Check if there's only 1 DEX, 1 lending protocol, 1 stablecoin, etc
            cat_counts = defaultdict(list)
            for t in native:
                cat_counts[t["_category"]].append(t)

            for cat in ["dex", "lending", "oracle", "stablecoin", "liquid_staking", "bridge"]:
                tokens_in_cat = cat_counts.get(cat, [])
                if len(tokens_in_cat) == 1:
                    t = tokens_in_cat[0]
                    mcap = t.get("market_cap_usd", 0) or 0
                    if mcap > 1e6:  # only meaningful ones
                        spofs.append((cat, t, mcap))
                elif len(tokens_in_cat) == 0 and cat in ["dex", "lending", "stablecoin"]:
                    # No native version at all — dependent on shared
                    shared_in_cat = [t for t in eco["shared_sorted"] if t["_category"] == cat]
                    if shared_in_cat:
                        spofs.append((f"NO NATIVE {cat}", shared_in_cat[0], 0))

            if spofs:
                print(f"  {eco['chain'].upper()} ({eco['symbol']}):")
                for cat, t, mcap in spofs:
                    risk = "🔴" if "NO NATIVE" in cat else "🟡"
                    mcap_str = fmt_b(mcap) if mcap else "dependent on shared"
                    print(f"    {risk} Only {cat}: {t['symbol'].upper()} ({mcap_str})")
                    if "NO NATIVE" in cat:
                        print(f"       → If multi-chain bridges fail, this chain has no {cat.replace('NO NATIVE ', '')}")
                print()

        # ═══════════════════════════════════════════════════════════
        # INSIGHT 4: STABLECOIN CONCENTRATION RISK
        # ═══════════════════════════════════════════════════════════

        print(f"\n{'═' * 100}")
        print("  💰 INSIGHT 4: STABLECOIN CONCENTRATION RISK")
        print(f"  Which stablecoins dominate each chain? What happens if ONE depegs?")
        print(f"{'═' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: x["stablecoin_mcap"], reverse=True)[:12]:
            stables = [t for t in eco["tokens_sorted"] if t["_category"] == "stablecoin"]
            if not stables:
                continue
            total_stable = sum(t.get("market_cap_usd", 0) or 0 for t in stables)
            if total_stable < 1e6:
                continue

            print(f"  {eco['chain'].upper()} ({eco['symbol']}) — {fmt_b(total_stable)} in stablecoins")

            for t in stables[:5]:
                mcap = t.get("market_cap_usd", 0) or 0
                pct = mcap / total_stable * 100 if total_stable else 0
                chains = len(token_chains.get(t["id"], set()))
                risk = "🔴" if pct > 50 else "🟡" if pct > 25 else "🟢"
                print(f"    {risk} {t['symbol'].upper():8s} {fmt_b(mcap):>10s} ({pct:4.1f}%)  on {chains} chains")

            # Depeg impact
            if stables:
                biggest = stables[0]
                biggest_pct = (biggest.get("market_cap_usd", 0) or 0) / total_stable * 100 if total_stable else 0
                if biggest_pct > 50:
                    print(f"    ⚠️  {biggest['symbol'].upper()} depeg impact: {biggest_pct:.0f}% of chain stablecoin value at risk")
                    print(f"       → All DeFi using {biggest['symbol'].upper()} as collateral faces liquidation cascade")
            print()

        # ═══════════════════════════════════════════════════════════
        # INSIGHT 5: DEVELOPMENT HEALTH — Who's actually building?
        # ═══════════════════════════════════════════════════════════

        print(f"\n{'═' * 100}")
        print("  👨‍💻 INSIGHT 5: DEVELOPMENT HEALTH — Active builders per ecosystem")
        print(f"{'═' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: x["total_contributors"], reverse=True)[:12]:
            if eco["github_projects"] == 0:
                continue
            health = "🟢" if eco["total_contributors"] > 500 else "🟡" if eco["total_contributors"] > 100 else "🔴"
            print(f"  {health} {eco['chain'].upper():25s}  {eco['github_projects']:>4} projects  "
                  f"{eco['total_stars']:>6} ⭐  {eco['total_contributors']:>5} contributors  "
                  f"Audited: {eco['audited_pct']:.0f}%")

        # ═══════════════════════════════════════════════════════════
        # INSIGHT 6: CROSS-CHAIN CONTAGION CORRIDORS
        # ═══════════════════════════════════════════════════════════

        print(f"\n\n{'═' * 100}")
        print("  🔗 INSIGHT 6: CROSS-CHAIN CONTAGION CORRIDORS")
        print(f"  Which chain pairs share the most tokens? Failure propagates along these paths.")
        print(f"{'═' * 100}\n")

        # Build chain-pair overlap matrix
        chain_pairs = defaultdict(lambda: {"count": 0, "mcap": 0, "tokens": []})
        for tid, chains in token_chains.items():
            if len(chains) < 2:
                continue
            chains_list = sorted(chains)
            mcap = 0
            for t in tokens:
                if t["id"] == tid:
                    mcap = t.get("market_cap_usd", 0) or 0
                    break
            for i in range(len(chains_list)):
                for j in range(i + 1, len(chains_list)):
                    pair = (chains_list[i], chains_list[j])
                    chain_pairs[pair]["count"] += 1
                    chain_pairs[pair]["mcap"] += mcap
                    chain_pairs[pair]["tokens"].append(tid)

        # Top contagion corridors
        sorted_pairs = sorted(chain_pairs.items(), key=lambda x: x[1]["mcap"], reverse=True)[:20]
        print(f"  {'CHAIN A':25s} ↔ {'CHAIN B':25s}  SHARED TOKENS  SHARED MCAP")
        print(f"  {'─' * 90}")
        for (c1, c2), data in sorted_pairs:
            risk = "🔴" if data["mcap"] > 100e9 else "🟡" if data["mcap"] > 10e9 else "🟢"
            print(f"  {risk} {c1:25s} ↔ {c2:25s}  {data['count']:>5} tokens   {fmt_b(data['mcap']):>10s}")

        # ═══════════════════════════════════════════════════════════
        # INSIGHT 7: "GHOST CHAINS" — Ecosystems with no real activity
        # ═══════════════════════════════════════════════════════════

        print(f"\n\n{'═' * 100}")
        print("  👻 INSIGHT 7: GHOST CHAINS vs THRIVING ECOSYSTEMS")
        print(f"  Chains where most tokens are just bridged copies vs genuine native innovation")
        print(f"{'═' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: x["native_pct"]):
            native_pct = eco["native_pct"]
            label = "👻 GHOST" if native_pct < 5 else "🟡 DEPENDENT" if native_pct < 20 else "🟢 INDEPENDENT" if native_pct < 60 else "💪 SELF-SUFFICIENT"
            print(f"  {label:22s}  {eco['chain'].upper():25s}  "
                  f"Native: {eco['native_tokens']:>5} ({native_pct:4.1f}%)  "
                  f"Native mcap: {fmt_b(eco['native_mcap']):>10s}")

        # ═══════════════════════════════════════════════════════════
        # INSIGHT 8: ECOSYSTEM HEALTH SCORECARD
        # ═══════════════════════════════════════════════════════════

        print(f"\n\n{'═' * 100}")
        print("  📋 INSIGHT 8: ECOSYSTEM HEALTH SCORECARD")
        print(f"  Composite score: Diversity × Trust × Development × Independence × Infrastructure")
        print(f"{'═' * 100}\n")

        header = (f"  {'CHAIN':20s} {'DIVERSITY':>10s} {'TRUST':>8s} {'DEV':>8s} "
                  f"{'INDEPENDENCE':>13s} {'INFRA':>8s} {'HEALTH':>8s}")
        print(header)
        print(f"  {'─' * 90}")

        health_scores = []
        for eco in ecosystems.values():
            # Diversity: how many different categories (of native tokens)
            n_cats = len([c for c, d in eco["native_cats"].items() if d["count"] > 0])
            diversity = min(100, n_cats * 15)  # 7+ categories = 100

            # Trust: avg native trust score (normalized to 0-100)
            trust = eco["native_avg_trust"] if eco["native_avg_trust"] else eco["avg_trust"]

            # Development: contributors + audit coverage
            dev = min(100, eco["total_contributors"] / 10 + eco["audited_pct"])

            # Independence: % native tokens
            independence = eco["native_pct"]

            # Infrastructure: has native DEX, lending, stablecoin, oracle
            infra_cats = set(t["_category"] for t in eco["native_sorted"])
            infra_score = 0
            for needed in ["dex", "lending", "stablecoin", "oracle", "liquid_staking", "bridge"]:
                if needed in infra_cats:
                    infra_score += 17

            # Composite
            health = (diversity * 0.15 + trust * 0.25 + dev * 0.20 +
                      independence * 0.20 + infra_score * 0.20)

            health_scores.append((eco, health, diversity, trust, dev, independence, infra_score))

        for eco, health, div, trust, dev, indep, infra in sorted(health_scores, key=lambda x: -x[1]):
            emoji = "🟢" if health > 50 else "🟡" if health > 30 else "🔴"
            print(f"  {emoji} {eco['chain'].upper():18s} {div:>8.0f}/100 {trust:>6.0f}/100 {dev:>6.0f}/100 "
                  f"{indep:>10.0f}%/100 {infra:>6.0f}/100 {health:>6.0f}/100")

    # ═══════════════════════════════════════════════════════════
    # SCENARIOS
    # ═══════════════════════════════════════════════════════════

    if run_scenarios:
        print(f"\n\n{'═' * 100}")
        print("  🔥 SCENARIO ENGINE — What-If Analysis")
        print(f"{'═' * 100}")

        scenarios = [
            {
                "name": "USDC loses 10% of peg ($1.00 → $0.90)",
                "token_id": "usd-coin",
                "shock_pct": -10,
                "type": "depeg",
            },
            {
                "name": "USDT loses 5% of peg ($1.00 → $0.95)",
                "token_id": "tether",
                "shock_pct": -5,
                "type": "depeg",
            },
            {
                "name": "ETH crashes 40%",
                "token_id": "ethereum",
                "shock_pct": -40,
                "type": "crash",
            },
            {
                "name": "SOL crashes 50%",
                "token_id": "solana",
                "shock_pct": -50,
                "type": "crash",
            },
            {
                "name": "Chainlink oracle failure (all LINK-dependent protocols affected)",
                "token_id": "chainlink",
                "shock_pct": -30,
                "type": "infrastructure_failure",
            },
        ]

        for scenario in scenarios:
            print(f"\n  {'─' * 90}")
            print(f"  💥 SCENARIO: {scenario['name']}")
            print(f"  {'─' * 90}")

            target_id = scenario["token_id"]
            shock = scenario["shock_pct"]

            # Find the token
            target = None
            for t in tokens:
                if t["id"] == target_id:
                    target = t
                    break

            if not target:
                print(f"    Token {target_id} not found")
                continue

            target_mcap = target.get("market_cap_usd", 0) or 0
            direct_loss = abs(target_mcap * shock / 100)

            # Which chains are affected?
            affected_chains = token_chains.get(target_id, set())

            print(f"    Direct impact: {fmt_b(direct_loss)} value destroyed")
            print(f"    Chains affected: {len(affected_chains)} — {', '.join(sorted(affected_chains))}")

            if scenario["type"] == "depeg":
                # Stablecoin depeg affects all protocols using it as collateral
                print(f"\n    FIRST-ORDER EFFECTS:")
                for chain in sorted(affected_chains):
                    eco = ecosystems.get(chain)
                    if not eco:
                        continue
                    # Find tokens in DeFi that likely use this stablecoin
                    defi_at_risk = [t for t in eco["tokens_sorted"]
                                    if t["_category"] in ["lending", "dex", "defi", "yield", "liquid_staking"]
                                    and t["id"] != target_id]
                    defi_mcap = sum(t.get("market_cap_usd", 0) or 0 for t in defi_at_risk)
                    # Estimate: DeFi tokens lose proportionally to stablecoin dependency
                    estimated_defi_loss = defi_mcap * abs(shock) / 100 * 0.5  # 50% of shock propagates
                    if defi_mcap > 1e6:
                        print(f"      {chain.upper():20s} → {len(defi_at_risk)} DeFi protocols at risk, "
                              f"estimated loss: {fmt_b(estimated_defi_loss)}")

                print(f"\n    SECOND-ORDER EFFECTS:")
                print(f"      → DEX pools with {target['symbol'].upper()} pair lose liquidity")
                print(f"      → Lending protocols face liquidation cascades")
                print(f"      → Other stablecoins may lose peg sympathetically (correlation spike)")
                print(f"      → Market-wide panic selling amplifies losses 2-5x")

            elif scenario["type"] == "crash":
                print(f"\n    ECOSYSTEM DESTRUCTION:")
                for chain in sorted(affected_chains):
                    eco = ecosystems.get(chain)
                    if not eco:
                        continue
                    locked_value = eco["native_mcap"]
                    estimated_loss = locked_value * abs(shock) / 100 * 0.7  # 70% correlation
                    if locked_value > 1e6:
                        print(f"      {chain.upper():20s} → Native ecosystem {fmt_b(locked_value)}, "
                              f"estimated loss: {fmt_b(estimated_loss)}")

            elif scenario["type"] == "infrastructure_failure":
                print(f"\n    DEPENDENT PROTOCOLS:")
                # All DeFi protocols that use oracles
                for chain in sorted(affected_chains):
                    eco = ecosystems.get(chain)
                    if not eco:
                        continue
                    oracle_dependent = [t for t in eco["tokens_sorted"]
                                        if t["_category"] in ["lending", "dex", "liquid_staking", "yield"]]
                    if oracle_dependent:
                        total_at_risk = sum(t.get("market_cap_usd", 0) or 0 for t in oracle_dependent)
                        print(f"      {chain.upper():20s} → {len(oracle_dependent)} protocols, "
                              f"{fmt_b(total_at_risk)} at risk of price feed failure")
                        for t in oracle_dependent[:3]:
                            print(f"        └ {t['symbol'].upper()} ({fmt_b(t.get('market_cap_usd',0) or 0)})")

        # ═══════════════════════════════════════════════════════════
        # HIDDEN INSIGHT: Ecosystem Fragility Index
        # ═══════════════════════════════════════════════════════════

        print(f"\n\n{'═' * 100}")
        print("  🔬 ECOSYSTEM FRAGILITY INDEX")
        print(f"  Combines all metrics into a single risk number per chain")
        print(f"{'═' * 100}\n")

        for eco in sorted(ecosystems.values(), key=lambda x: x["native_mcap"], reverse=True)[:12]:
            if eco["native_mcap"] < 1e6:
                continue

            # Fragility factors
            f1_lock_in = eco["native_pct"]  # Higher = more locked in (but also more independent)
            f2_stable_dep = eco["stablecoin_dependency"]
            f3_low_trust = eco["low_trust_count"] / eco["total_tokens"] * 100 if eco["total_tokens"] else 0
            f4_no_audit = 100 - eco["audited_pct"]
            f5_concentration = eco["top1_native_pct"] if eco["top1_native_pct"] else 0
            f6_meme_pct = eco["all_cats"].get("meme", {}).get("mcap", 0) / eco["total_mcap"] * 100 if eco["total_mcap"] else 0

            fragility = (
                f2_stable_dep * 0.25 +
                f3_low_trust * 0.20 +
                f4_no_audit * 0.15 +
                f5_concentration * 0.15 +
                f6_meme_pct * 0.15 +
                (100 - eco["avg_trust"]) * 0.10
            )

            bar = "█" * int(fragility / 2) + "░" * (50 - int(fragility / 2))
            emoji = "🔴" if fragility > 70 else "🟡" if fragility > 50 else "🟢"
            print(f"  {emoji} {eco['chain'].upper():25s} {bar}  {fragility:.0f}/100")
            print(f"      Stable dep: {f2_stable_dep:.0f}%  Low trust: {f3_low_trust:.0f}%  "
                  f"Unaudited: {f4_no_audit:.0f}%  Top1: {f5_concentration:.0f}%  Meme: {f6_meme_pct:.0f}%")

    # ═══════════════════════════════════════════════════════════
    # SAVE TO DB
    # ═══════════════════════════════════════════════════════════

    if save:
        print(f"\n\n{'═' * 100}")
        print("  💾 SAVING TO DATABASE...")
        print(f"{'═' * 100}")

        conn.execute("DROP TABLE IF EXISTS crypto_ecosystem_analysis")
        conn.execute("""CREATE TABLE crypto_ecosystem_analysis (
            chain TEXT PRIMARY KEY,
            symbol TEXT,
            chain_type TEXT,
            l1_mcap REAL,
            l1_trust_score REAL,
            total_tokens INTEGER,
            native_tokens INTEGER,
            shared_tokens INTEGER,
            total_mcap REAL,
            native_mcap REAL,
            shared_mcap REAL,
            native_pct REAL,
            avg_trust REAL,
            native_avg_trust REAL,
            low_trust_count INTEGER,
            audited_pct REAL,
            github_projects INTEGER,
            total_stars INTEGER,
            total_contributors INTEGER,
            mcap_gini REAL,
            stablecoin_count INTEGER,
            stablecoin_mcap REAL,
            native_stablecoin_mcap REAL,
            stablecoin_dependency REAL,
            defi_count INTEGER,
            defi_native_count INTEGER,
            categories_json TEXT,
            crawled_at TEXT
        )""")

        conn.execute("DROP TABLE IF EXISTS crypto_token_ecosystem_v2")
        conn.execute("""CREATE TABLE crypto_token_ecosystem_v2 (
            token_id TEXT,
            chain TEXT,
            is_native INTEGER,
            category TEXT,
            market_cap_usd REAL,
            trust_score REAL,
            crawled_at TEXT,
            PRIMARY KEY (token_id, chain)
        )""")

        now = datetime.now(timezone.utc).isoformat()

        for cn, eco in ecosystems.items():
            cats_json = json.dumps({k: {"count": v["count"], "mcap": v["mcap"]}
                                    for k, v in eco["native_cats"].items()})
            conn.execute("""INSERT OR REPLACE INTO crypto_ecosystem_analysis VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                cn, eco["symbol"], eco["type"], eco["l1_mcap"], eco["l1_trust"],
                eco["total_tokens"], eco["native_tokens"], eco["shared_tokens"],
                eco["total_mcap"], eco["native_mcap"], eco["shared_mcap"], eco["native_pct"],
                eco["avg_trust"], eco["native_avg_trust"], eco["low_trust_count"],
                eco["audited_pct"], eco["github_projects"], eco["total_stars"],
                eco["total_contributors"], eco["mcap_gini"],
                eco["stablecoin_count"], eco["stablecoin_mcap"],
                eco["native_stablecoin_mcap"], eco["stablecoin_dependency"],
                eco["defi_count"], eco["defi_native_count"], cats_json, now))

            for t in eco["tokens_sorted"]:
                is_native = 1 if len(token_chains.get(t["id"], set())) == 1 else 0
                conn.execute("""INSERT OR REPLACE INTO crypto_token_ecosystem_v2 VALUES (?,?,?,?,?,?,?)""", (
                    t["id"], cn, is_native, t.get("_category", "other"),
                    t.get("market_cap_usd"), t.get("trust_score"), now))

        conn.commit()
        total_eco = conn.execute("SELECT COUNT(*) FROM crypto_ecosystem_analysis").fetchone()[0]
        total_map = conn.execute("SELECT COUNT(*) FROM crypto_token_ecosystem_v2").fetchone()[0]
        print(f"  ✅ Saved {total_eco} ecosystem analyses + {total_map} token mappings")

    conn.close()
    print(f"\n✅ Analysis complete!")


if __name__ == "__main__":
    main()
