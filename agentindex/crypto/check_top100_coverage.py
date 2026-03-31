#!/usr/bin/env python3
"""Check if top 100 tokens by market cap are covered in our ecosystem analysis."""

import sqlite3
import json
import os

DB = os.path.expanduser("~/agentindex/agentindex/data/crypto_trust.db")

def main():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row

    # ── 1. Top 100 tokens by market cap ──
    top100 = conn.execute("""
        SELECT id, symbol, name, market_cap_usd, platforms, trust_score
        FROM crypto_tokens 
        WHERE market_cap_usd IS NOT NULL 
        ORDER BY market_cap_usd DESC 
        LIMIT 100
    """).fetchall()

    # ── 2. Check which are in ecosystem analysis ──
    eco_ids = {r[0] for r in conn.execute("SELECT DISTINCT token_id FROM crypto_token_ecosystem").fetchall()}

    # All platform keys we map to chains
    PLATFORM_TO_CHAIN = {
        "ethereum": "ethereum", "binance-smart-chain": "binance-smart-chain",
        "solana": "solana", "tron": "tron", "cardano": "cardano",
        "avalanche": "avalanche", "polkadot": "polkadot",
        "polygon-pos": "polygon", "arbitrum-one": "arbitrum",
        "optimistic-ethereum": "optimism", "base": "base",
        "near-protocol": "near", "sui": "sui", "aptos": "aptos",
        "fantom": "fantom", "cosmos": "cosmos", "algorand": "algorand",
        "cronos": "cronos", "mantle": "mantle", "linea": "linea", "zksync": "zksync",
    }

    print("=" * 110)
    print("  TOP 100 TOKENS BY MARKET CAP — ECOSYSTEM COVERAGE CHECK")
    print("=" * 110)
    print(f"\n  Tokens in ecosystem analysis: {len(eco_ids)}")
    print()

    print(f"  {'#':>3} {'Symbol':<10} {'Name':<28} {'MCap':>14} {'Trust':>5} {'Chains':>6} {'Status'}")
    print("  " + "─" * 100)

    covered = 0
    missing_no_platforms = []
    missing_untracked = []

    for i, row in enumerate(top100, 1):
        tid = row["id"]
        sym = row["symbol"]
        name = row["name"] or ""
        mcap = row["market_cap_usd"] or 0
        trust = row["trust_score"] or 0
        platforms_raw = row["platforms"]

        try:
            p = json.loads(platforms_raw) if platforms_raw else {}
        except:
            p = {}

        chain_count = len(p)
        in_eco = tid in eco_ids

        mcap_str = f"${mcap/1e9:.1f}B" if mcap >= 1e9 else f"${mcap/1e6:.0f}M"

        if in_eco:
            covered += 1
            flag = "✅"
        elif chain_count == 0:
            missing_no_platforms.append((sym, name, mcap, tid))
            flag = "⚠️  NO CHAINS (L1 native?)"
        else:
            chain_names = list(p.keys())
            tracked = [c for c in chain_names if c in PLATFORM_TO_CHAIN]
            untracked = [c for c in chain_names if c not in PLATFORM_TO_CHAIN]
            missing_untracked.append((sym, name, mcap, chain_names, untracked))
            if untracked:
                flag = f"❌ untracked: {','.join(untracked[:3])}"
            else:
                flag = f"❌ on tracked chains but missing?? {','.join(tracked[:3])}"

        print(f"  {i:>3} {sym.upper():<10} {name[:27]:<28} {mcap_str:>14} {trust:>5} {chain_count:>6} {flag}")

    # ── Summary ──
    print(f"\n{'=' * 110}")
    print(f"  SUMMARY")
    print(f"{'=' * 110}")
    print(f"  ✅ In ecosystem analysis: {covered}/100 ({covered}%)")
    print(f"  ⚠️  No platform data (L1 natives): {len(missing_no_platforms)}")
    print(f"  ❌ Has platforms but missing: {len(missing_untracked)}")

    if missing_no_platforms:
        print(f"\n  ── TOKENS WITH NO PLATFORM DATA (likely L1 natives we should add) ──")
        total_missing = 0
        for sym, name, mcap, tid in missing_no_platforms:
            mcap_str = f"${mcap/1e9:.1f}B" if mcap >= 1e9 else f"${mcap/1e6:.0f}M"
            total_missing += mcap
            print(f"     {sym.upper():<10} {name[:30]:<30} {mcap_str:>14}  id: {tid}")
        print(f"     TOTAL MISSING MCAP: ${total_missing/1e9:.1f}B")

    if missing_untracked:
        untracked_platforms = {}
        for sym, name, mcap, chains, untracked in missing_untracked:
            for c in untracked:
                untracked_platforms.setdefault(c, []).append((sym, name, mcap))

        if untracked_platforms:
            print(f"\n  ── PLATFORM KEYS WE DON'T TRACK (add these to L1_CHAINS?) ──")
            for platform, tokens in sorted(untracked_platforms.items(), 
                                            key=lambda x: -sum(t[2] for t in x[1])):
                total = sum(t[2] for t in tokens)
                mcap_str = f"${total/1e9:.1f}B" if total >= 1e9 else f"${total/1e6:.0f}M"
                print(f"     {platform:<30} {len(tokens)} tokens, {mcap_str} total")
                for sym, name, mcap in tokens[:5]:
                    m = f"${mcap/1e9:.1f}B" if mcap >= 1e9 else f"${mcap/1e6:.0f}M"
                    print(f"       └ {sym.upper()} ({m})")

    # ── 4. Market cap coverage ──
    total_mcap = sum(r["market_cap_usd"] or 0 for r in top100)
    covered_mcap = sum(r["market_cap_usd"] or 0 for r in top100 if r["id"] in eco_ids)
    no_plat_mcap = sum(mcap for _, _, mcap, _ in missing_no_platforms)

    print(f"\n  ── MARKET CAP COVERAGE ──")
    print(f"     Total top-100 mcap:     ${total_mcap/1e12:.2f}T")
    print(f"     ✅ Covered:              ${covered_mcap/1e12:.2f}T ({covered_mcap/total_mcap*100:.1f}%)")
    print(f"     ⚠️  No platforms (L1s):   ${no_plat_mcap/1e12:.2f}T ({no_plat_mcap/total_mcap*100:.1f}%)")
    print(f"     ❌ Missing:              ${(total_mcap-covered_mcap-no_plat_mcap)/1e12:.2f}T ({(total_mcap-covered_mcap-no_plat_mcap)/total_mcap*100:.1f}%)")

    conn.close()

if __name__ == "__main__":
    main()
