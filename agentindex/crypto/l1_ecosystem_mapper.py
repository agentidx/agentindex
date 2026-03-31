#!/usr/bin/env python3
"""
NERQ L1 ECOSYSTEM MAPPER
========================
Maps every token to its parent L1 blockchain(s).
Calculates ecosystem concentration, vulnerability, and cross-chain dependencies.

Usage:
    python3 l1_ecosystem_mapper.py           # Full analysis
    python3 l1_ecosystem_mapper.py --json    # Export as JSON
    python3 l1_ecosystem_mapper.py --save    # Save ecosystem tables to DB

Output:
    - Per-L1 ecosystem tree (which tokens live on which chain)
    - Concentration metrics (top1/5/10 dominance)
    - Vulnerability score per ecosystem
    - Cross-chain "bridge tokens" that connect ecosystems
    - Single-chain tokens (most vulnerable to L1 failure)
"""

import sqlite3
import json
import os
import sys
from datetime import datetime, timezone

DB_PATH = os.path.expanduser("~/agentindex/agentindex/data/crypto_trust.db")

# L1/L2 CHAIN DEFINITIONS
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


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def classify_token(categories_json):
    if not categories_json:
        return "other"
    try:
        cats = json.loads(categories_json) if isinstance(categories_json, str) else []
        cat_str = " ".join(cats).lower()
    except:
        return "other"
    if any(x in cat_str for x in ["stablecoin", "stable"]):
        return "stablecoin"
    if any(x in cat_str for x in ["meme", "dog ", "cat ", "pepe", "shib"]):
        return "meme"
    if any(x in cat_str for x in ["defi", "lending", "dex", "yield", "amm", "liquid staking"]):
        return "defi"
    if any(x in cat_str for x in ["layer 2", "l2", "rollup", "zero knowledge", "oracle", "data", "storage"]):
        return "infrastructure"
    if any(x in cat_str for x in ["nft", "metaverse", "gaming", "play-to-earn"]):
        return "nft_gaming"
    if any(x in cat_str for x in ["governance", "dao"]):
        return "governance"
    if any(x in cat_str for x in ["wrapped", "bridged"]):
        return "wrapped"
    return "other"


def calc_ecosystem_vulnerability(eco):
    score = 0
    tokens = eco["tokens"]
    total_mcap = eco["total_mcap"]
    if not tokens or total_mcap == 0:
        return 50

    # Top concentration: more distributed = more attack surface
    if eco["top1_pct"] > 80: score += 5
    elif eco["top1_pct"] > 50: score += 10
    else: score += 15

    # Stablecoin dependency
    stable_pct = eco["category_mcap"].get("stablecoin", 0) / total_mcap * 100
    if stable_pct > 30: score += 20
    elif stable_pct > 15: score += 12
    elif stable_pct > 5: score += 6

    # Single-chain lock-in
    if eco["single_chain_pct"] > 60: score += 15
    elif eco["single_chain_pct"] > 40: score += 10
    elif eco["single_chain_pct"] > 20: score += 5

    # Meme exposure
    meme_pct = eco["category_mcap"].get("meme", 0) / total_mcap * 100
    if meme_pct > 20: score += 10
    elif meme_pct > 5: score += 5

    # Low average trust
    if eco["avg_trust"] < 40: score += 15
    elif eco["avg_trust"] < 55: score += 10
    elif eco["avg_trust"] < 70: score += 5

    # Low trust token count
    low_pct = eco["low_trust_count"] / len(tokens) * 100 if tokens else 0
    if low_pct > 30: score += 10
    elif low_pct > 15: score += 5

    # DeFi complexity
    defi_count = eco["category_count"].get("defi", 0)
    if defi_count > 50: score += 10
    elif defi_count > 20: score += 6
    elif defi_count > 5: score += 3

    return min(100, score)


def main():
    save_to_db = "--save" in sys.argv
    export_json = "--json" in sys.argv
    conn = get_db()

    tokens = [dict(r) for r in conn.execute("""
        SELECT id, name, symbol, market_cap_usd, market_cap_rank,
               categories, platforms, trust_score, trust_grade,
               current_price_usd, total_volume_24h_usd
        FROM crypto_tokens WHERE market_cap_usd IS NOT NULL
        ORDER BY market_cap_usd DESC
    """).fetchall()]
    print(f"Total tokens with market cap: {len(tokens)}")

    # Map tokens → ecosystems
    ecosystem_map = {}
    token_chains = {}
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
                    ecosystem_map.setdefault(chain_name, []).append(t)
                    token_chains.setdefault(t["id"], set()).add(chain_name)

    # L1 native tokens
    l1_token_data = {}
    for chain_name, info in L1_CHAINS.items():
        if info["token_id"]:
            for t in tokens:
                if t["id"] == info["token_id"]:
                    l1_token_data[chain_name] = t
                    break

    # Build ecosystem analysis
    ecosystems = {}
    for chain_name in sorted(ecosystem_map.keys(),
                              key=lambda c: sum(t.get("market_cap_usd", 0) or 0 for t in ecosystem_map[c]),
                              reverse=True):
        ct = ecosystem_map[chain_name]
        total_mcap = sum(t.get("market_cap_usd", 0) or 0 for t in ct)
        total_vol = sum(t.get("total_volume_24h_usd", 0) or 0 for t in ct)

        cat_count, cat_mcap = {}, {}
        for t in ct:
            c = classify_token(t.get("categories"))
            cat_count[c] = cat_count.get(c, 0) + 1
            cat_mcap[c] = cat_mcap.get(c, 0) + (t.get("market_cap_usd", 0) or 0)

        scores = [t["trust_score"] for t in ct if t.get("trust_score")]
        avg_trust = sum(scores) / len(scores) if scores else 0
        min_trust = min(scores) if scores else 0
        low_trust = sum(1 for s in scores if s < 40)

        single = sum(1 for t in ct if len(token_chains.get(t["id"], set())) == 1)
        single_pct = single / len(ct) * 100 if ct else 0

        st = sorted(ct, key=lambda x: x.get("market_cap_usd", 0) or 0, reverse=True)
        top1_pct = (st[0].get("market_cap_usd", 0) or 0) / total_mcap * 100 if total_mcap else 0
        top5_pct = sum(t.get("market_cap_usd", 0) or 0 for t in st[:5]) / total_mcap * 100 if total_mcap else 0
        top10_pct = sum(t.get("market_cap_usd", 0) or 0 for t in st[:10]) / total_mcap * 100 if total_mcap else 0

        l1 = l1_token_data.get(chain_name, {})
        l1_mcap = l1.get("market_cap_usd", 0) or 0

        eco = {
            "chain": chain_name, "symbol": L1_CHAINS[chain_name]["symbol"],
            "type": L1_CHAINS[chain_name]["type"],
            "l1_mcap": l1_mcap, "l1_trust": l1.get("trust_score", "N/A"),
            "l1_grade": l1.get("trust_grade", "N/A"),
            "token_count": len(ct), "total_mcap": total_mcap, "total_vol_24h": total_vol,
            "eco_l1_ratio": total_mcap / l1_mcap if l1_mcap else 0,
            "top1_pct": top1_pct, "top1_token": st[0]["symbol"].upper() if st else "?",
            "top5_pct": top5_pct, "top10_pct": top10_pct,
            "category_count": cat_count, "category_mcap": cat_mcap,
            "avg_trust": avg_trust, "min_trust": min_trust, "low_trust_count": low_trust,
            "single_chain_count": single, "single_chain_pct": single_pct,
            "tokens": st,
        }
        eco["vulnerability_score"] = calc_ecosystem_vulnerability(eco)
        ecosystems[chain_name] = eco

    # ═══════ PRINT ECOSYSTEM TREES ═══════
    print(f"\n{'═' * 95}")
    print("  L1 ECOSYSTEM MAP — Full Token Tree per Blockchain")
    print(f"{'═' * 95}")

    for chain_name, eco in sorted(ecosystems.items(), key=lambda x: x[1]["total_mcap"], reverse=True):
        vuln = eco["vulnerability_score"]
        vuln_bar = "\U0001f534" if vuln >= 60 else "\U0001f7e1" if vuln >= 40 else "\U0001f7e2"
        print(f"\n{'─' * 95}")
        print(f"  {chain_name.upper()} ({eco['symbol']}) — {eco['type']}")
        print(f"  L1 Token:      ${eco['l1_mcap']/1e9:.1f}B mcap | Trust: {eco['l1_trust']} ({eco['l1_grade']})")
        print(f"  Ecosystem:     {eco['token_count']} tokens | ${eco['total_mcap']/1e9:.1f}B total")
        print(f"  Eco/L1 ratio:  {eco['eco_l1_ratio']:.1f}x")
        print(f"  Concentration: Top1={eco['top1_pct']:.0f}% ({eco['top1_token']}) | Top5={eco['top5_pct']:.0f}% | Top10={eco['top10_pct']:.0f}%")
        print(f"  Trust:         Avg={eco['avg_trust']:.0f} | Min={eco['min_trust']:.0f} | Low(<40): {eco['low_trust_count']}")
        print(f"  Single-chain:  {eco['single_chain_count']}/{eco['token_count']} ({eco['single_chain_pct']:.0f}%)")
        print(f"  Vulnerability: {vuln_bar} {vuln}/100")

        cats = eco["category_mcap"]
        total = eco["total_mcap"]
        cat_str = " | ".join(f"{k}: ${v/1e9:.1f}B ({v/total*100:.0f}%)" for k, v in sorted(cats.items(), key=lambda x: -x[1]) if v > 0)
        print(f"  Categories:    {cat_str}")

        for i, t in enumerate(eco["tokens"][:20]):
            mcap = t.get("market_cap_usd", 0) or 0
            score = t.get("trust_score", "?")
            grade = t.get("trust_grade", "?")
            rank = t.get("market_cap_rank", "?")
            cat = classify_token(t.get("categories"))
            chains = token_chains.get(t["id"], set())
            ctag = "ONLY-HERE" if len(chains) == 1 else f"{len(chains)}-chains"
            c = "|" if i < min(len(eco["tokens"]), 20) - 1 else "`"
            print(f"     {c}-- #{str(rank):>5s} {t['symbol'].upper():8s} ${mcap/1e9:>8.2f}B  Trust:{str(score):>5s} ({str(grade):>2s})  {cat:14s}  {ctag}")
        if len(eco["tokens"]) > 20:
            print(f"     `-- ... +{len(eco['tokens']) - 20} more")

    # ═══════ VULNERABILITY RANKING ═══════
    print(f"\n\n{'═' * 95}")
    print("  ECOSYSTEM VULNERABILITY RANKING (higher = more systemic risk)")
    print(f"{'═' * 95}\n")
    for eco in sorted(ecosystems.values(), key=lambda x: x["vulnerability_score"], reverse=True):
        v = eco["vulnerability_score"]
        bar = "#" * (v // 2) + "." * (50 - v // 2)
        emoji = "!!" if v >= 60 else "! " if v >= 40 else "ok"
        risks = []
        sp = eco["category_mcap"].get("stablecoin", 0) / eco["total_mcap"] * 100 if eco["total_mcap"] else 0
        mp = eco["category_mcap"].get("meme", 0) / eco["total_mcap"] * 100 if eco["total_mcap"] else 0
        if sp > 20: risks.append(f"stable={sp:.0f}%")
        if mp > 10: risks.append(f"meme={mp:.0f}%")
        if eco["single_chain_pct"] > 50: risks.append(f"locked={eco['single_chain_pct']:.0f}%")
        if eco["avg_trust"] < 50: risks.append(f"trust={eco['avg_trust']:.0f}")
        print(f"  [{emoji}] {eco['chain'].upper():25s} {eco['symbol']:5s}  {bar}  {v:3d}/100  [{', '.join(risks) or 'balanced'}]")

    # ═══════ CROSS-CHAIN TOKENS ═══════
    print(f"\n\n{'═' * 95}")
    print("  CROSS-CHAIN TOKENS — Systemic Connectors (4+ chains)")
    print(f"{'═' * 95}\n")
    multi = [(tid, chs) for tid, chs in token_chains.items() if len(chs) >= 4]
    multi.sort(key=lambda x: len(x[1]), reverse=True)
    for tid, chs in multi[:40]:
        for t in tokens:
            if t["id"] == tid:
                mcap = t.get("market_cap_usd", 0) or 0
                cat = classify_token(t.get("categories"))
                print(f"  {t['symbol'].upper():8s} ${mcap/1e9:>8.2f}B  Trust:{str(t.get('trust_score','?')):>5s}  {cat:12s}  [{len(chs)} chains] {', '.join(sorted(chs))}")
                break

    # ═══════ SCENARIO ANALYSIS ═══════
    print(f"\n\n{'═' * 95}")
    print("  SCENARIO: What happens if an L1 goes down?")
    print(f"{'═' * 95}")
    for chain_name, eco in sorted(ecosystems.items(), key=lambda x: x[1]["total_mcap"], reverse=True)[:8]:
        locked, escapable = [], []
        for t in eco["tokens"]:
            mcap = t.get("market_cap_usd", 0) or 0
            if len(token_chains.get(t["id"], set())) == 1:
                locked.append((t, mcap))
            else:
                escapable.append((t, mcap))
        locked_mcap = sum(m for _, m in locked)
        print(f"\n  >> {chain_name.upper()} ({eco['symbol']}) FAILURE")
        print(f"     Ecosystem: ${eco['total_mcap']/1e9:.1f}B | Locked tokens: ${locked_mcap/1e9:.1f}B ({len(locked)} tokens)")
        print(f"     Multi-chain (can survive): ${sum(m for _,m in escapable)/1e9:.1f}B ({len(escapable)} tokens)")
        locked.sort(key=lambda x: x[1], reverse=True)
        for t, m in locked[:5]:
            if m > 1e6:
                print(f"     LOCKED: {t['symbol'].upper():8s} ${m/1e9:.2f}B — total loss")
        sl = sum(m for t, m in locked if classify_token(t.get("categories")) == "stablecoin")
        dl = sum(m for t, m in locked if classify_token(t.get("categories")) == "defi")
        if sl > 0: print(f"     Stablecoin destruction: ${sl/1e9:.2f}B -> depeg cascade")
        if dl > 0: print(f"     DeFi protocol loss: ${dl/1e9:.2f}B -> TVL cascade")

    # ═══════ SAVE TO DB ═══════
    if save_to_db:
        print(f"\n  Saving to database...")
        conn.execute("""CREATE TABLE IF NOT EXISTS crypto_l1_ecosystems (
            chain TEXT PRIMARY KEY, symbol TEXT, chain_type TEXT,
            l1_mcap REAL, l1_trust_score REAL, token_count INTEGER,
            total_mcap REAL, total_vol_24h REAL, eco_l1_ratio REAL,
            top1_pct REAL, top1_token TEXT, top5_pct REAL, top10_pct REAL,
            stablecoin_mcap REAL, defi_mcap REAL, meme_mcap REAL,
            avg_trust REAL, min_trust REAL, low_trust_count INTEGER,
            single_chain_count INTEGER, single_chain_pct REAL,
            vulnerability_score INTEGER, crawled_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS crypto_token_ecosystem (
            token_id TEXT, chain TEXT, is_single_chain INTEGER,
            category TEXT, crawled_at TEXT, PRIMARY KEY (token_id, chain))""")
        now = datetime.now(timezone.utc).isoformat()
        for cn, e in ecosystems.items():
            conn.execute("INSERT OR REPLACE INTO crypto_l1_ecosystems VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                cn, e["symbol"], e["type"], e["l1_mcap"],
                e["l1_trust"] if isinstance(e["l1_trust"], (int, float)) else None,
                e["token_count"], e["total_mcap"], e["total_vol_24h"],
                e["eco_l1_ratio"], e["top1_pct"], e["top1_token"],
                e["top5_pct"], e["top10_pct"],
                e["category_mcap"].get("stablecoin", 0),
                e["category_mcap"].get("defi", 0),
                e["category_mcap"].get("meme", 0),
                e["avg_trust"], e["min_trust"], e["low_trust_count"],
                e["single_chain_count"], e["single_chain_pct"],
                e["vulnerability_score"], now))
            for t in e["tokens"]:
                chains = token_chains.get(t["id"], set())
                conn.execute("INSERT OR REPLACE INTO crypto_token_ecosystem VALUES (?,?,?,?,?)",
                    (t["id"], cn, 1 if len(chains) == 1 else 0, classify_token(t.get("categories")), now))
        conn.commit()
        print(f"  Saved {len(ecosystems)} ecosystems + token mappings")

    conn.close()
    print(f"\nDone! {sum(len(e['tokens']) for e in ecosystems.values())} token-chain mappings across {len(ecosystems)} ecosystems")


if __name__ == "__main__":
    main()
