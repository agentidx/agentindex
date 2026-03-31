#!/usr/bin/env python3
"""
NERQ L1 ECOSYSTEM ANALYZER v3
==============================
v2 → v3 changes:
  BUGFIXES:
  1. ETH/SOL crash scenario now finds chains via L1_CHAINS (not token_chains)
  2. BNB-on-Ethereum filtered: L1 tokens excluded from OTHER chain's "native"
  3. ZEC + more tokens added to KNOWN_OVERRIDES
  4. Bitcoin added as ecosystem

  NEW INSIGHTS:
  9.  Innovation Moat Score — unique tech, market niche, defensibility
  10. Cycle-Adjusted Context — bear market, maturity normalization
  11. Risk/Reward Score — combines fragility with growth potential
  12. Final Investment Signal Matrix

Usage:
    python3 l1_ecosystem_analyzer_v3.py --all
    python3 l1_ecosystem_analyzer_v3.py --insights
    python3 l1_ecosystem_analyzer_v3.py --reward
    python3 l1_ecosystem_analyzer_v3.py --scenarios
    python3 l1_ecosystem_analyzer_v3.py --save
"""

import sqlite3, json, os, sys, math
from datetime import datetime, timezone
from collections import Counter, defaultdict

DB_PATH = os.path.expanduser("~/agentindex/agentindex/data/crypto_trust.db")

L1_CHAINS = {
    "bitcoin": {"token_id": "bitcoin", "symbol": "BTC", "type": "L1", "platform_keys": [], "launch_year": 2009, "ath_mcap": 2100e9},
    "ethereum": {"token_id": "ethereum", "symbol": "ETH", "type": "L1", "platform_keys": ["ethereum"], "launch_year": 2015, "ath_mcap": 580e9},
    "binance-smart-chain": {"token_id": "binancecoin", "symbol": "BNB", "type": "L1", "platform_keys": ["binance-smart-chain"], "launch_year": 2020, "ath_mcap": 100e9},
    "solana": {"token_id": "solana", "symbol": "SOL", "type": "L1", "platform_keys": ["solana"], "launch_year": 2020, "ath_mcap": 120e9},
    "tron": {"token_id": "tron", "symbol": "TRX", "type": "L1", "platform_keys": ["tron"], "launch_year": 2017, "ath_mcap": 18e9},
    "cardano": {"token_id": "cardano", "symbol": "ADA", "type": "L1", "platform_keys": ["cardano"], "launch_year": 2017, "ath_mcap": 95e9},
    "avalanche": {"token_id": "avalanche-2", "symbol": "AVAX", "type": "L1", "platform_keys": ["avalanche"], "launch_year": 2020, "ath_mcap": 42e9},
    "polkadot": {"token_id": "polkadot", "symbol": "DOT", "type": "L1", "platform_keys": ["polkadot"], "launch_year": 2020, "ath_mcap": 55e9},
    "polygon": {"token_id": "matic-network", "symbol": "POL", "type": "L2", "platform_keys": ["polygon-pos"], "launch_year": 2020, "ath_mcap": 20e9},
    "arbitrum": {"token_id": "arbitrum", "symbol": "ARB", "type": "L2", "platform_keys": ["arbitrum-one"], "launch_year": 2023, "ath_mcap": 4e9},
    "optimism": {"token_id": "optimism", "symbol": "OP", "type": "L2", "platform_keys": ["optimistic-ethereum"], "launch_year": 2022, "ath_mcap": 5e9},
    "base": {"token_id": None, "symbol": "BASE", "type": "L2", "platform_keys": ["base"], "launch_year": 2023, "ath_mcap": 0},
    "near": {"token_id": "near", "symbol": "NEAR", "type": "L1", "platform_keys": ["near-protocol"], "launch_year": 2020, "ath_mcap": 13e9},
    "sui": {"token_id": "sui", "symbol": "SUI", "type": "L1", "platform_keys": ["sui"], "launch_year": 2023, "ath_mcap": 16e9},
    "aptos": {"token_id": "aptos", "symbol": "APT", "type": "L1", "platform_keys": ["aptos"], "launch_year": 2022, "ath_mcap": 8e9},
    "fantom": {"token_id": "fantom", "symbol": "FTM", "type": "L1", "platform_keys": ["fantom"], "launch_year": 2019, "ath_mcap": 8e9},
    "cosmos": {"token_id": "cosmos", "symbol": "ATOM", "type": "L1", "platform_keys": ["cosmos"], "launch_year": 2019, "ath_mcap": 15e9},
    "algorand": {"token_id": "algorand", "symbol": "ALGO", "type": "L1", "platform_keys": ["algorand"], "launch_year": 2019, "ath_mcap": 11e9},
    "cronos": {"token_id": "crypto-com-chain", "symbol": "CRO", "type": "L1", "platform_keys": ["cronos"], "launch_year": 2021, "ath_mcap": 22e9},
    "mantle": {"token_id": "mantle", "symbol": "MNT", "type": "L2", "platform_keys": ["mantle"], "launch_year": 2023, "ath_mcap": 4e9},
    "linea": {"token_id": None, "symbol": "LINEA", "type": "L2", "platform_keys": ["linea"], "launch_year": 2023, "ath_mcap": 0},
    "zksync": {"token_id": "zksync", "symbol": "ZK", "type": "L2", "platform_keys": ["zksync"], "launch_year": 2023, "ath_mcap": 1e9},
}

INNOVATION_MOATS = {
    "bitcoin":              {"tech": 95, "niche": 100, "network": 100, "defense": 100, "note": "Digital gold. PoW. 21M cap. Lindy. ETF. Never hacked."},
    "ethereum":             {"tech": 80, "niche": 90,  "network": 95,  "defense": 90,  "note": "Settlement layer. EVM standard. Most devs/TVL. Rollup roadmap."},
    "solana":               {"tech": 75, "niche": 80,  "network": 70,  "defense": 55,  "note": "Consumer crypto. PoH. Low fees. Firedancer. Meme/payments."},
    "binance-smart-chain":  {"tech": 30, "niche": 70,  "network": 65,  "defense": 40,  "note": "Binance captive chain. Cheap retail DeFi. Regulatory risk."},
    "tron":                 {"tech": 25, "niche": 85,  "network": 60,  "defense": 50,  "note": "USDT highway. Most stablecoin volume. Remittances Asia/EM."},
    "cardano":              {"tech": 65, "niche": 40,  "network": 35,  "defense": 30,  "note": "Academic. Haskell/Plutus. Peer-reviewed. Slow to ship."},
    "avalanche":            {"tech": 70, "niche": 55,  "network": 45,  "defense": 50,  "note": "Subnets. App-specific chains. Enterprise + gaming."},
    "polkadot":             {"tech": 70, "niche": 45,  "network": 30,  "defense": 40,  "note": "Parachains. Shared security. Losing to Cosmos SDK."},
    "polygon":              {"tech": 50, "niche": 55,  "network": 50,  "defense": 45,  "note": "Enterprise (Starbucks, Nike). CDK. Identity crisis."},
    "arbitrum":             {"tech": 55, "niche": 75,  "network": 70,  "defense": 50,  "note": "Largest L2 by TVL. DeFi powerhouse. Orbit chains."},
    "optimism":             {"tech": 60, "niche": 65,  "network": 65,  "defense": 65,  "note": "OP Stack platform. Base/Worldcoin use it. Superchain."},
    "base":                 {"tech": 40, "niche": 80,  "network": 75,  "defense": 70,  "note": "Coinbase L2. 100M+ user funnel. Distribution moat."},
    "near":                 {"tech": 70, "niche": 60,  "network": 40,  "defense": 45,  "note": "Chain abstraction + AI. Nightshade sharding. Good UX."},
    "sui":                  {"tech": 80, "niche": 65,  "network": 55,  "defense": 60,  "note": "Move language. Object model. Parallel exec. Ex-Meta."},
    "aptos":                {"tech": 75, "niche": 45,  "network": 30,  "defense": 35,  "note": "Move sibling to Sui. Block-STM. Losing dev race."},
    "fantom":               {"tech": 55, "niche": 30,  "network": 20,  "defense": 20,  "note": "Sonic upgrade revival. Andre Cronje key-man risk."},
    "cosmos":               {"tech": 80, "niche": 70,  "network": 60,  "defense": 65,  "note": "IBC protocol. Sovereign chains. dYdX/Osmosis. ATOM value accrual weak."},
    "algorand":             {"tech": 60, "niche": 40,  "network": 20,  "defense": 25,  "note": "MIT pedigree. Pure PoS. FIFA. Failed adoption."},
    "cronos":               {"tech": 25, "niche": 50,  "network": 35,  "defense": 30,  "note": "Crypto.com chain. Captive users. Limited innovation."},
    "mantle":               {"tech": 35, "niche": 45,  "network": 25,  "defense": 25,  "note": "BitDAO treasury. Small ecosystem. Needs unique niche."},
    "linea":                {"tech": 50, "niche": 40,  "network": 25,  "defense": 35,  "note": "Consensys zkEVM. MetaMask distribution potential."},
    "zksync":               {"tech": 75, "niche": 55,  "network": 30,  "defense": 50,  "note": "ZK pioneer. Native AA. Airdrop controversy hurt."},
}

KNOWN_OVERRIDES = {
    "chainlink": "oracle", "band-protocol": "oracle", "api3": "oracle",
    "pyth-network": "oracle", "uma": "oracle", "tellor": "oracle", "dia-data": "oracle",
    "uniswap": "dex", "sushiswap": "dex", "pancakeswap-token": "dex",
    "curve-dao-token": "dex", "balancer": "dex", "1inch": "dex",
    "jupiter-exchange-solana": "dex", "raydium": "dex", "orca": "dex",
    "aerodrome-finance": "dex", "velodrome-finance": "dex", "trader-joe": "dex", "dydx-chain": "dex",
    "aave": "lending", "compound-governance-token": "lending",
    "maker": "lending", "morpho": "lending", "venus": "lending",
    "lido-dao": "liquid_staking", "rocket-pool": "liquid_staking", "jito-governance-token": "liquid_staking",
    "ethereum": "l1", "solana": "l1", "binancecoin": "l1", "cardano": "l1",
    "avalanche-2": "l1", "polkadot": "l1", "tron": "l1", "near": "l1",
    "sui": "l1", "aptos": "l1", "cosmos": "l1", "fantom": "l1",
    "algorand": "l1", "bitcoin": "l1", "bitcoin-cash": "l1", "litecoin": "l1",
    "arbitrum": "l2", "optimism": "l2", "mantle": "l2",
    "zksync": "l2", "matic-network": "l2", "starknet": "l2",
    "zcash": "privacy", "monero": "privacy", "dash": "privacy",
    "filecoin": "infrastructure", "render-token": "infrastructure",
}

L1_TOKEN_IDS = set(info["token_id"] for info in L1_CHAINS.values() if info["token_id"])

def classify_token(token_id, categories_json):
    if token_id in KNOWN_OVERRIDES: return KNOWN_OVERRIDES[token_id]
    if not categories_json: return "other"
    try:
        cats = json.loads(categories_json) if isinstance(categories_json, str) else []
        cs = " ".join(cats).lower()
    except: return "other"
    if any(x in cs for x in ["stablecoin"]): return "stablecoin"
    if "oracle" in cs: return "oracle"
    if any(x in cs for x in ["decentralized exchange", "dex", "amm"]): return "dex"
    if any(x in cs for x in ["lending", "borrowing"]): return "lending"
    if any(x in cs for x in ["liquid staking", "restaking"]): return "liquid_staking"
    if any(x in cs for x in ["yield aggregator", "yield farming"]): return "yield"
    if any(x in cs for x in ["bridge", "cross-chain"]): return "bridge"
    if any(x in cs for x in ["layer 2", "l2", "rollup", "zero knowledge"]): return "l2"
    if any(x in cs for x in ["layer 1", "l1", "smart contract platform"]): return "l1"
    if any(x in cs for x in ["meme", "dog-themed", "cat-themed", "pepe"]): return "meme"
    if any(x in cs for x in ["defi", "decentralized finance"]): return "defi"
    if any(x in cs for x in ["nft", "metaverse", "gaming", "play-to-earn"]): return "nft_gaming"
    if any(x in cs for x in ["governance", "dao"]): return "governance"
    if any(x in cs for x in ["privacy"]): return "privacy"
    if any(x in cs for x in ["wrapped", "bridged"]): return "wrapped"
    if any(x in cs for x in ["real world asset", "rwa", "tokenized"]): return "rwa"
    if any(x in cs for x in ["artificial intelligence", " ai "]): return "ai"
    if any(x in cs for x in ["storage", "computing", "data"]): return "infrastructure"
    return "other"

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def fmt(val):
    if val >= 1e9: return f"${val/1e9:.1f}B"
    elif val >= 1e6: return f"${val/1e6:.0f}M"
    elif val >= 1e3: return f"${val/1e3:.0f}K"
    return f"${val:.0f}"

def gini(values):
    if not values or len(values) < 2: return 0
    sv = sorted(values); n = len(sv); total = sum(sv)
    if total == 0: return 0
    gs = sum((2*(i+1)-n-1)*v for i,v in enumerate(sv))
    return gs / (n * total)

def main():
    run_all = "--all" in sys.argv
    run_insights = "--insights" in sys.argv or run_all
    run_reward = "--reward" in sys.argv or run_all
    run_scenarios = "--scenarios" in sys.argv or run_all
    save = "--save" in sys.argv
    if not any([run_all, run_insights, run_reward, run_scenarios, save]):
        run_insights = True; run_reward = True

    conn = get_db()
    tokens = [dict(r) for r in conn.execute("""
        SELECT id, name, symbol, market_cap_usd, market_cap_rank,
               categories, platforms, trust_score, trust_grade,
               current_price_usd, total_volume_24h_usd,
               circulating_supply, total_supply, max_supply,
               has_audit, is_verified, github_stars, github_contributors, twitter_followers
        FROM crypto_tokens WHERE market_cap_usd IS NOT NULL ORDER BY market_cap_usd DESC
    """).fetchall()]

    defi_protocols = {}
    try:
        for r in conn.execute("SELECT name, tvl_usd, category, chains FROM crypto_defi_protocols"):
            defi_protocols[r[0].lower()] = dict(r)
    except: pass

    dex_pools_by_chain = defaultdict(list)
    try:
        for r in conn.execute("SELECT chain, dex, tvl_usd FROM crypto_dex_pools WHERE tvl_usd > 0"):
            dex_pools_by_chain[r[0].lower()].append(dict(r))
    except: pass

    print(f"📊 Loaded: {len(tokens)} tokens, {len(defi_protocols)} DeFi protocols, "
          f"{sum(len(v) for v in dex_pools_by_chain.values())} DEX pools")

    # Map tokens to ecosystems
    ecosystem_map = defaultdict(list)
    token_chains = defaultdict(set)
    for t in tokens:
        if not t["platforms"]: continue
        try: platforms = json.loads(t["platforms"]) if isinstance(t["platforms"], str) else {}
        except: continue
        for cn, ci in L1_CHAINS.items():
            for pk in ci["platform_keys"]:
                if pk in platforms and platforms[pk]:
                    ecosystem_map[cn].append(t)
                    token_chains[t["id"]].add(cn)

    # Build ecosystem analysis
    ecosystems = {}
    for cn in L1_CHAINS:
        ct = ecosystem_map.get(cn, [])
        ci = L1_CHAINS[cn]
        native_tokens, shared_tokens = [], []
        for t in ct:
            t["_cat"] = classify_token(t["id"], t.get("categories"))
            is_single = len(token_chains.get(t["id"], set())) == 1
            is_foreign_l1 = t["id"] in L1_TOKEN_IDS and t["id"] != ci.get("token_id")
            (native_tokens if is_single and not is_foreign_l1 else shared_tokens).append(t)

        nm = sum(t.get("market_cap_usd",0) or 0 for t in native_tokens)
        sm = sum(t.get("market_cap_usd",0) or 0 for t in shared_tokens)
        tm = nm + sm

        nc = defaultdict(lambda: {"count":0,"mcap":0,"tokens":[]})
        for t in native_tokens:
            nc[t["_cat"]]["count"]+=1; nc[t["_cat"]]["mcap"]+=t.get("market_cap_usd",0) or 0; nc[t["_cat"]]["tokens"].append(t)

        scores = [t["trust_score"] for t in ct if t.get("trust_score")]
        ns = [t["trust_score"] for t in native_tokens if t.get("trust_score")]
        wg = [t for t in ct if t.get("github_stars") and t["github_stars"]>0]

        l1t = next((t for t in tokens if t["id"]==ci.get("token_id")), None)
        l1m = l1t.get("market_cap_usd",0) or 0 if l1t else 0
        sn = sorted(native_tokens, key=lambda x: x.get("market_cap_usd",0) or 0, reverse=True)

        ecosystems[cn] = {
            "chain": cn, "symbol": ci["symbol"], "type": ci["type"],
            "l1_mcap": l1m, "l1_trust": l1t.get("trust_score") if l1t else None,
            "launch_year": ci.get("launch_year",2020), "age": 2026-ci.get("launch_year",2020),
            "ath_mcap": ci.get("ath_mcap",0) or 0,
            "ath_dd": ((ci.get("ath_mcap",0)-l1m)/ci["ath_mcap"]*100) if ci.get("ath_mcap") else 0,
            "total_tokens": len(ct), "native_count": len(native_tokens), "shared_count": len(shared_tokens),
            "total_mcap": tm, "native_mcap": nm, "shared_mcap": sm,
            "native_pct": nm/tm*100 if tm else 0,
            "native_cats": dict(nc),
            "avg_trust": sum(scores)/len(scores) if scores else 0,
            "native_avg_trust": sum(ns)/len(ns) if ns else 0,
            "low_trust": sum(1 for s in scores if s<40),
            "audited_pct": sum(1 for t in ct if t.get("has_audit"))/len(ct)*100 if ct else 0,
            "gh_projects": len(wg),
            "gh_stars": sum(t["github_stars"] for t in wg),
            "gh_contribs": sum(t.get("github_contributors",0) or 0 for t in wg),
            "gini": gini([t.get("market_cap_usd",0) or 0 for t in native_tokens if t.get("market_cap_usd")]),
            "top1_pct": (sn[0].get("market_cap_usd",0) or 0)/nm*100 if nm and sn else 0,
            "stable_dep": sum(t.get("market_cap_usd",0) or 0 for t in ct if t["_cat"]=="stablecoin")/tm*100 if tm else 0,
            "defi_count": len([t for t in ct if t["_cat"] in ["dex","lending","liquid_staking","yield","defi","bridge"]]),
            "tokens_sorted": sorted(ct, key=lambda x: x.get("market_cap_usd",0) or 0, reverse=True),
            "native_sorted": sn,
            "shared_sorted": sorted(shared_tokens, key=lambda x: x.get("market_cap_usd",0) or 0, reverse=True),
        }

    # ═══════════════════════════════════════════════════════════
    # INSIGHTS 1-8
    # ═══════════════════════════════════════════════════════════
    if run_insights:
        print(f"\n{'═'*100}")
        print("  📊 INSIGHT 1: TRUE ECOSYSTEM SIZE — Native vs Bridged (v3: L1 cross-chain fix)")
        print(f"{'═'*100}\n")
        for eco in sorted(ecosystems.values(), key=lambda x: x["native_mcap"], reverse=True):
            if eco["chain"]=="bitcoin" or eco["native_mcap"]<1e4: continue
            nb = min(40, int(eco["native_mcap"]/5e9))
            sb = min(40, int(eco["shared_mcap"]/5e9))
            print(f"  {eco['chain'].upper():25s} ({eco['symbol']:5s})")
            print(f"    Native: {fmt(eco['native_mcap']):>10s}  {'█'*nb}")
            print(f"    Shared: {fmt(eco['shared_mcap']):>10s}  {'░'*sb}")
            print(f"    {eco['native_count']} native / {eco['shared_count']} shared = {eco['native_pct']:.0f}% native\n")

        print(f"\n{'═'*100}")
        print("  🧬 INSIGHT 2: ECOSYSTEM DNA — Native tokens only")
        print(f"{'═'*100}\n")
        for eco in sorted(ecosystems.values(), key=lambda x: x["native_mcap"], reverse=True)[:12]:
            if eco["native_mcap"]<1e6 or eco["chain"]=="bitcoin": continue
            print(f"  {eco['chain'].upper()} ({eco['symbol']}) — {fmt(eco['native_mcap'])}")
            for cat,d in sorted(eco["native_cats"].items(), key=lambda x:-x[1]["mcap"]):
                if d["mcap"]<1e4: continue
                p = d["mcap"]/eco["native_mcap"]*100 if eco["native_mcap"] else 0
                best = max(d["tokens"], key=lambda x: x.get("market_cap_usd",0) or 0) if d["tokens"] else None
                tp = f"(top: {best['symbol'].upper()} {fmt(best.get('market_cap_usd',0) or 0)})" if best else ""
                print(f"    {cat:16s} {p:5.1f}%  {'█'*max(1,int(p/3)):20s}  {d['count']:>3} tokens  {fmt(d['mcap']):>10s}  {tp}")
            print()

        print(f"\n{'═'*100}")
        print("  👨‍💻 INSIGHT 5: DEVELOPMENT HEALTH")
        print(f"{'═'*100}\n")
        for eco in sorted(ecosystems.values(), key=lambda x: x["gh_contribs"], reverse=True)[:15]:
            if eco["gh_projects"]==0: continue
            h = "🟢" if eco["gh_contribs"]>500 else "🟡" if eco["gh_contribs"]>100 else "🔴"
            print(f"  {h} {eco['chain'].upper():25s}  {eco['gh_projects']:>4} projects  "
                  f"{eco['gh_stars']:>6} ⭐  {eco['gh_contribs']:>5} contributors  Audited: {eco['audited_pct']:.0f}%")

    # ═══════════════════════════════════════════════════════════
    # NEW: INSIGHTS 9-12 REWARD + CYCLE
    # ═══════════════════════════════════════════════════════════
    if run_reward:
        print(f"\n\n{'═'*100}")
        print("  🏰 INSIGHT 9: INNOVATION MOAT — What makes each chain defensible?")
        print(f"{'═'*100}\n")
        print(f"  {'CHAIN':<22s} {'TECH':>6s} {'NICHE':>7s} {'NETWRK':>8s} {'DEFENS':>8s} {'MOAT':>6s}  NARRATIVE")
        print(f"  {'─'*110}")
        moat_scores = {}
        for cn, m in sorted(INNOVATION_MOATS.items(), key=lambda x: sum(x[1][k] for k in ["tech","niche","network","defense"])/4, reverse=True):
            avg = (m["tech"]+m["niche"]+m["network"]+m["defense"])/4
            moat_scores[cn] = avg
            e = "🟢" if avg>70 else "🟡" if avg>45 else "🔴"
            print(f"  {e} {cn.upper()[:20]:<20s} {m['tech']:>5} {m['niche']:>6} {m['network']:>7} {m['defense']:>7} {avg:>5.0f}  {m['note'][:65]}")

        print(f"\n\n{'═'*100}")
        print("  📉 INSIGHT 10: CYCLE CONTEXT — Bear Market Adjustment")
        print(f"  BTC from $109K ATH. Altcoins -41% from Dec 2024. VC -50-60% from peak.")
        print(f"{'═'*100}\n")
        print(f"  {'CHAIN':<22s} {'L1 MCAP':>10s} {'ATH MCAP':>10s} {'DRAWDOWN':>10s} {'AGE':>5s} {'MATURITY'}")
        print(f"  {'─'*80}")
        for eco in sorted(ecosystems.values(), key=lambda x: x["l1_mcap"], reverse=True):
            if not eco["ath_mcap"]: continue
            a = eco["age"]
            mat = "🏛️  Established" if a>=10 else "🌳 Maturing" if a>=5 else "🌱 Growing" if a>=3 else "🌰 Seedling"
            e = "🟢" if eco["ath_dd"]<50 else "🟡" if eco["ath_dd"]<75 else "🔴"
            print(f"  {e} {eco['chain'].upper()[:20]:<20s} {fmt(eco['l1_mcap']):>10s} {fmt(eco['ath_mcap']):>10s} {eco['ath_dd']:>8.0f}%  {a:>3}yr  {mat}")

        print(f"\n  📊 Bear Market Context:")
        print(f"     • Altcoin mcap $950B = -41% from Dec 2024. BTC from $109K peak.")
        print(f"     • VC funding -50-60% from 2021-22 peak cycle")
        print(f"     • Dev counts DROP 25-40% in bear, then SURGE in recovery")
        print(f"     • Electric Capital: 'Every cycle = step function increase in devs'")
        print(f"     • KEY: chains keeping devs NOW win next cycle")

        print(f"\n\n{'═'*100}")
        print("  ⚖️  INSIGHT 11: RISK/REWARD SCORE")
        print(f"  Risk = Fragility × Dependency   Reward = Moat × Drawdown × Dev Activity")
        print(f"{'═'*100}\n")
        print(f"  {'CHAIN':<22s} {'RISK':>6s} {'REWARD':>8s} {'R/R':>5s} {'MOAT':>6s} {'DD%':>6s} {'AGE':>5s}  VERDICT")
        print(f"  {'─'*100}")

        rr_results = []
        for cn, eco in ecosystems.items():
            m = INNOVATION_MOATS.get(cn)
            if not m: continue
            moat_avg = moat_scores.get(cn, 0)

            # RISK
            ic = set(t["_cat"] for t in eco.get("native_sorted",[]))
            im = sum(25 for n in ["dex","lending","stablecoin","oracle"] if n not in ic)
            risk = (min(100,eco["stable_dep"])*0.20 +
                    (eco["low_trust"]/eco["total_tokens"]*100 if eco["total_tokens"] else 50)*0.15 +
                    (100-eco["audited_pct"])*0.15 +
                    (eco["top1_pct"] or 50)*0.15 + im*0.15 +
                    (100-eco["avg_trust"])*0.10 +
                    (0 if eco["gh_contribs"]>200 else 50)*0.10)
            if cn=="bitcoin": risk = 15

            # REWARD
            dd = min(100, eco["ath_dd"]) if eco["ath_mcap"] else 50
            ab = max(0, 100-eco["age"]*10)
            ds = min(100, eco["gh_contribs"]/5)
            reward = moat_avg*0.40 + dd*0.25 + ds*0.15 + ab*0.10 + min(100,eco["native_count"]/20)*0.10

            rr = reward / max(risk, 1)
            if rr>2.0: v = "🌟 STRONG BUY signal"
            elif rr>1.5: v = "✅ Favorable R/R"
            elif rr>1.0: v = "🟡 Neutral"
            elif rr>0.7: v = "⚠️  Risk > Reward"
            else: v = "🔴 Avoid"
            rr_results.append((cn, eco, risk, reward, rr, moat_avg, eco["ath_dd"], eco["age"], v))

        for cn, eco, ri, re, rr, ma, dd, age, v in sorted(rr_results, key=lambda x:-x[4]):
            e = "🟢" if rr>1.5 else "🟡" if rr>1.0 else "🔴"
            print(f"  {e} {cn.upper()[:20]:<20s} {ri:>5.0f} {re:>7.0f} {rr:>5.1f}x {ma:>5.0f} {dd:>5.0f}% {age:>4}yr  {v}")

        print(f"\n\n{'═'*100}")
        print("  🎯 INSIGHT 12: INVESTMENT SIGNAL MATRIX")
        print(f"{'═'*100}\n")
        hi = [(c,e,ri,re,rr,m,d,a,v) for c,e,ri,re,rr,m,d,a,v in rr_results if rr>1.5]
        md = [(c,e,ri,re,rr,m,d,a,v) for c,e,ri,re,rr,m,d,a,v in rr_results if 1.0<rr<=1.5]
        lo = [(c,e,ri,re,rr,m,d,a,v) for c,e,ri,re,rr,m,d,a,v in rr_results if rr<=1.0]

        print("  🌟 HIGH CONVICTION (R/R > 1.5x)")
        for c,e,ri,re,rr,m,d,a,v in sorted(hi, key=lambda x:-x[4]):
            n = INNOVATION_MOATS.get(c,{}).get("note","")[:80]
            print(f"     {c.upper():20s} R/R: {rr:.1f}x  Moat: {m:.0f}  Drawdown: {d:.0f}%")
            print(f"       └ {n}")

        print(f"\n  🟡 WATCHLIST (R/R 1.0-1.5x)")
        for c,e,ri,re,rr,m,d,a,v in sorted(md, key=lambda x:-x[4]):
            print(f"     {c.upper():20s} R/R: {rr:.1f}x  Moat: {m:.0f}  Drawdown: {d:.0f}%")

        print(f"\n  🔴 CAUTION (R/R < 1.0x)")
        for c,e,ri,re,rr,m,d,a,v in sorted(lo, key=lambda x:-x[4]):
            print(f"     {c.upper():20s} R/R: {rr:.1f}x  Moat: {m:.0f}  Drawdown: {d:.0f}%")

        print(f"\n  ⚠️  NOT financial advice. Bear market = opportunity but timing uncertain. DYOR.")

    # ═══════════════════════════════════════════════════════════
    # SCENARIOS — v3: Fixed L1 crash
    # ═══════════════════════════════════════════════════════════
    if run_scenarios:
        print(f"\n\n{'═'*100}")
        print("  🔥 SCENARIO ENGINE (v3: fixed L1 crash)")
        print(f"{'═'*100}")
        scenarios = [
            {"name":"USDC -10%","tid":"usd-coin","shock":-10,"type":"depeg"},
            {"name":"USDT -5%","tid":"tether","shock":-5,"type":"depeg"},
            {"name":"ETH -40%","tid":"ethereum","shock":-40,"type":"crash"},
            {"name":"SOL -50%","tid":"solana","shock":-50,"type":"crash"},
            {"name":"Chainlink failure","tid":"chainlink","shock":-30,"type":"infra"},
        ]
        for sc in scenarios:
            print(f"\n  {'─'*90}\n  💥 {sc['name']}\n  {'─'*90}")
            tgt = next((t for t in tokens if t["id"]==sc["tid"]), None)
            if not tgt: print("    Not found"); continue
            tm = tgt.get("market_cap_usd",0) or 0
            loss = abs(tm*sc["shock"]/100)
            print(f"    Direct loss: {fmt(loss)}")

            if sc["type"]=="crash":
                cc = next((cn for cn,ci in L1_CHAINS.items() if ci.get("token_id")==sc["tid"]), None)
                if cc and cc in ecosystems:
                    eco = ecosystems[cc]
                    el = eco["native_mcap"]*abs(sc["shock"])/100*0.7
                    print(f"    Chain: {cc.upper()} → {eco['native_count']} native tokens, {fmt(eco['native_mcap'])} native mcap")
                    print(f"    Est ecosystem loss (70% corr): {fmt(el)}")
                    print(f"    DeFi protocols affected: {eco['defi_count']}")
                    if cc=="ethereum":
                        print(f"    L2 CASCADE:")
                        for l2 in ["arbitrum","optimism","base","polygon","zksync","linea","mantle"]:
                            if l2 in ecosystems:
                                print(f"      {l2.upper():20s} → {ecosystems[l2]['native_count']} tokens, {fmt(ecosystems[l2]['native_mcap'])}")
            elif sc["type"]=="depeg":
                ac = token_chains.get(sc["tid"], set())
                print(f"    Chains: {len(ac)} — {', '.join(sorted(ac))}")
                for ch in sorted(ac):
                    eco = ecosystems.get(ch)
                    if not eco: continue
                    dr = [t for t in eco["tokens_sorted"] if t["_cat"] in ["lending","dex","defi","yield","liquid_staking"] and t["id"]!=sc["tid"]]
                    dm = sum(t.get("market_cap_usd",0) or 0 for t in dr)
                    if dm>1e6: print(f"      {ch.upper():20s} → {len(dr)} DeFi, est loss: {fmt(dm*abs(sc['shock'])/100*0.5)}")
            elif sc["type"]=="infra":
                ac = token_chains.get(sc["tid"], set())
                print(f"    Chains: {len(ac)}")
                for ch in sorted(ac):
                    eco = ecosystems.get(ch)
                    if not eco: continue
                    od = [t for t in eco["tokens_sorted"] if t["_cat"] in ["lending","dex","liquid_staking","yield"]]
                    if od:
                        print(f"      {ch.upper():20s} → {len(od)} protocols, {fmt(sum(t.get('market_cap_usd',0) or 0 for t in od))} at risk")

    # ═══════════════════════════════════════════════════════════
    # SAVE TO DB
    # ═══════════════════════════════════════════════════════════
    if save:
        print(f"\n\n{'═'*100}\n  💾 SAVING TO DATABASE...\n{'═'*100}")
        conn.execute("DROP TABLE IF EXISTS crypto_ecosystem_analysis")
        conn.execute("""CREATE TABLE crypto_ecosystem_analysis (
            chain TEXT PRIMARY KEY, symbol TEXT, chain_type TEXT,
            l1_mcap REAL, l1_trust_score REAL, launch_year INT, age_years INT,
            ath_mcap REAL, ath_drawdown_pct REAL,
            total_tokens INT, native_tokens INT, shared_tokens INT,
            total_mcap REAL, native_mcap REAL, shared_mcap REAL, native_pct REAL,
            avg_trust REAL, native_avg_trust REAL, low_trust_count INT, audited_pct REAL,
            github_projects INT, total_stars INT, total_contributors INT, mcap_gini REAL,
            stablecoin_dependency REAL, defi_count INT,
            moat_score REAL, risk_score REAL, reward_score REAL, rr_ratio REAL,
            categories_json TEXT, crawled_at TEXT
        )""")
        conn.execute("DROP TABLE IF EXISTS crypto_token_ecosystem_v2")
        conn.execute("""CREATE TABLE crypto_token_ecosystem_v2 (
            token_id TEXT, chain TEXT, is_native INT, category TEXT,
            market_cap_usd REAL, trust_score REAL, crawled_at TEXT,
            PRIMARY KEY (token_id, chain)
        )""")
        now = datetime.now(timezone.utc).isoformat()
        for cn, eco in ecosystems.items():
            ma = moat_scores.get(cn, 0) if 'moat_scores' in dir() else (
                sum(INNOVATION_MOATS.get(cn,{}).get(k,0) for k in ["tech","niche","network","defense"])/4
                if cn in INNOVATION_MOATS else 0)
            ic = set(t["_cat"] for t in eco.get("native_sorted",[]))
            im = sum(25 for n in ["dex","lending","stablecoin","oracle"] if n not in ic)
            risk = (min(100,eco["stable_dep"])*0.20+(eco["low_trust"]/eco["total_tokens"]*100 if eco["total_tokens"] else 50)*0.15+
                    (100-eco["audited_pct"])*0.15+(eco["top1_pct"] or 50)*0.15+im*0.15+(100-eco["avg_trust"])*0.10+
                    (0 if eco["gh_contribs"]>200 else 50)*0.10)
            if cn=="bitcoin": risk=15
            dd = min(100,eco["ath_dd"]) if eco["ath_mcap"] else 50
            reward = ma*0.40+dd*0.25+min(100,eco["gh_contribs"]/5)*0.15+max(0,100-eco["age"]*10)*0.10+min(100,eco["native_count"]/20)*0.10
            rr = reward/max(risk,1)
            cj = json.dumps({k:{"count":v["count"],"mcap":v["mcap"]} for k,v in eco["native_cats"].items()})
            conn.execute("INSERT OR REPLACE INTO crypto_ecosystem_analysis VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cn,eco["symbol"],eco["type"],eco["l1_mcap"],eco["l1_trust"],
                 eco["launch_year"],eco["age"],eco["ath_mcap"],eco["ath_dd"],
                 eco["total_tokens"],eco["native_count"],eco["shared_count"],
                 eco["total_mcap"],eco["native_mcap"],eco["shared_mcap"],eco["native_pct"],
                 eco["avg_trust"],eco["native_avg_trust"],eco["low_trust"],eco["audited_pct"],
                 eco["gh_projects"],eco["gh_stars"],eco["gh_contribs"],eco["gini"],
                 eco["stable_dep"],eco["defi_count"],ma,risk,reward,rr,cj,now))
            for t in eco["tokens_sorted"]:
                isn = 1 if len(token_chains.get(t["id"],set()))==1 else 0
                conn.execute("INSERT OR REPLACE INTO crypto_token_ecosystem_v2 VALUES (?,?,?,?,?,?,?)",
                    (t["id"],cn,isn,t.get("_cat","other"),t.get("market_cap_usd"),t.get("trust_score"),now))
        conn.commit()
        te = conn.execute("SELECT COUNT(*) FROM crypto_ecosystem_analysis").fetchone()[0]
        tm = conn.execute("SELECT COUNT(*) FROM crypto_token_ecosystem_v2").fetchone()[0]
        print(f"  ✅ Saved {te} ecosystems + {tm} token mappings")
        print(f"     New: moat_score, risk_score, reward_score, rr_ratio, launch_year, ath_drawdown_pct")

    conn.close()
    print(f"\n✅ v3 Analysis complete!")

if __name__ == "__main__":
    main()
