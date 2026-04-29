"""
Sprint 9 Extension: Yield Portfolio Analyzer
POST /v1/yield/portfolio/analyze

Input:
  [{"pool_id": "xxx", "amount_usd": 5000}, ...]

Output:
  - Total portfölj-risk score (viktad)
  - Koncentrationsrisk (chain/protokoll)
  - Korrelationsrisk (delade reward-tokens)
  - Per-pool breakdown med WOW-insikter
  - Exit-prioritering
  - Projected yield om reward-emissionen slutar
"""

import os
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime, timezone

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)).replace("/agentindex-factory/", "/agentindex/"),
    "crypto_trust.db",
)


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def analyze_yield_portfolio(holdings: List[Dict]) -> dict:
    """
    holdings: [{"pool_id": str, "amount_usd": float}, ...]
    """
    if not holdings:
        return {"error": "No holdings provided"}

    conn = _get_db()
    try:
        from agentindex.crypto.yield_risk_engine import compute_yield_risk_score, _get_protocol_risk
        from agentindex.crypto.yield_divergence_engine import compute_divergence_signals, get_pool_history

        total_usd = sum(h.get("amount_usd", 0) for h in holdings)
        if total_usd <= 0:
            return {"error": "Total portfolio value is 0"}

        pool_results = []
        chain_exposure = {}
        protocol_exposure = {}
        reward_token_pools = {}  # reward_token → [pool_ids]

        for holding in holdings:
            pool_id = holding.get("pool_id")
            amount_usd = holding.get("amount_usd", 0)
            weight = amount_usd / total_usd

            # Hämta pool-data
            pool = conn.execute("SELECT * FROM defi_yields WHERE pool_id = ?", (pool_id,)).fetchone()
            if not pool:
                pool_results.append({
                    "pool_id": pool_id,
                    "error": "Pool not found",
                    "amount_usd": amount_usd,
                    "weight": round(weight, 3),
                })
                continue

            # Risk score
            risk_level, crash_prob = _get_protocol_risk(conn, pool["project"])
            risk_scoring = compute_yield_risk_score(
                apy=pool["apy"] or 0, apy_base=pool["apy_base"] or 0,
                apy_reward=pool["apy_reward"] or 0, tvl_usd=pool["tvl_usd"],
                il_risk=pool["il_risk"] or "no", stablecoin=pool["stablecoin"] or 0,
                risk_level=risk_level, crash_prob=crash_prob,
            )

            # Divergens-signaler (om historik finns)
            history = get_pool_history(conn, pool_id, days=30)
            divergence = compute_divergence_signals(pool_id, history) if len(history) >= 7 else None

            # Projected yield (base only, om reward försvinner)
            base_apy = pool["apy_base"] or 0
            reward_apy = pool["apy_reward"] or 0
            projected_yield_base_only = base_apy * amount_usd / 100 / 365  # daglig USD

            # Koncentration tracking
            chain = pool["chain"] or "Unknown"
            protocol = pool["project"] or "Unknown"
            chain_exposure[chain] = chain_exposure.get(chain, 0) + weight
            protocol_exposure[protocol] = protocol_exposure.get(protocol, 0) + weight

            pool_result = {
                "pool_id": pool_id,
                "protocol": pool["project"],
                "chain": pool["chain"],
                "symbol": pool["symbol"],
                "amount_usd": amount_usd,
                "weight": round(weight, 3),
                "apy": pool["apy"],
                "apy_base": base_apy,
                "apy_reward": reward_apy,
                "reward_ratio": round(reward_apy / pool["apy"], 3) if (pool["apy"] or 0) > 0 else 0,
                "annual_yield_usd": round(pool["apy"] * amount_usd / 100, 0),
                "annual_yield_base_only_usd": round(base_apy * amount_usd / 100, 0),
                "il_risk": pool["il_risk"],
                "protocol_risk_level": risk_level,
                **risk_scoring,
                "wow_score": divergence["wow_score"] if divergence else None,
                "wow_text": divergence["wow_text"] if divergence else None,
                "has_historical_data": len(history) >= 7,
            }
            pool_results.append(pool_result)

        # ── Portfolio-level metrics ───────────────────────────────────────────

        valid_pools = [p for p in pool_results if "error" not in p]

        # Viktad risk score
        weighted_risk = sum(p["yield_risk_score"] * p["weight"] for p in valid_pools)

        # Total annual yield
        total_annual_yield = sum(p.get("annual_yield_usd", 0) for p in valid_pools)
        total_annual_yield_base = sum(p.get("annual_yield_base_only_usd", 0) for p in valid_pools)

        # Yield tap risk: vad händer om all reward-emission slutar?
        yield_at_risk_usd = total_annual_yield - total_annual_yield_base
        yield_at_risk_pct = (yield_at_risk_usd / total_annual_yield * 100) if total_annual_yield > 0 else 0

        # Koncentrationsrisk
        max_chain_exposure = max(chain_exposure.values()) if chain_exposure else 0
        max_protocol_exposure = max(protocol_exposure.values()) if protocol_exposure else 0
        concentration_risk = round((max_chain_exposure * 0.5 + max_protocol_exposure * 0.5) * 100)

        # Trap exposure
        trap_pools = [p for p in valid_pools if p.get("is_yield_trap")]
        trap_exposure_usd = sum(p["amount_usd"] for p in trap_pools)
        trap_exposure_pct = (trap_exposure_usd / total_usd * 100) if total_usd > 0 else 0

        # WOW alerts (pooler med aktiva divergens-signaler)
        wow_alerts = [
            {"pool_id": p["pool_id"], "protocol": p["protocol"], "symbol": p["symbol"],
             "amount_usd": p["amount_usd"], "wow_score": p["wow_score"], "wow_text": p["wow_text"]}
            for p in valid_pools if p.get("wow_score") and p["wow_score"] >= 40 and p.get("wow_text")
        ]
        wow_alerts.sort(key=lambda x: x["wow_score"], reverse=True)

        # Exit-prioritering (sorterat på risk score × weight)
        exit_priority = sorted(
            valid_pools,
            key=lambda p: p["yield_risk_score"] * p["weight"],
            reverse=True
        )

        # Risk tier för portföljen
        if weighted_risk >= 70: portfolio_tier = "EXTREME"
        elif weighted_risk >= 50: portfolio_tier = "HIGH"
        elif weighted_risk >= 30: portfolio_tier = "MEDIUM"
        elif weighted_risk >= 15: portfolio_tier = "LOW"
        else: portfolio_tier = "SAFE"

        # Tier distribution
        tier_dist = {"EXTREME": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "SAFE": 0}
        for p in valid_pools:
            tier_dist[p["yield_risk_tier"]] = tier_dist.get(p["yield_risk_tier"], 0) + 1

        return {
            "portfolio_summary": {
                "total_usd": round(total_usd, 0),
                "total_pools": len(holdings),
                "valid_pools": len(valid_pools),
                "weighted_risk_score": round(weighted_risk, 1),
                "portfolio_risk_tier": portfolio_tier,
                "tier_distribution": tier_dist,
            },
            "yield_analysis": {
                "total_annual_yield_usd": round(total_annual_yield, 0),
                "total_annual_yield_base_usd": round(total_annual_yield_base, 0),
                "yield_at_risk_usd": round(yield_at_risk_usd, 0),
                "yield_at_risk_pct": round(yield_at_risk_pct, 1),
                "note": f"${round(yield_at_risk_usd):,}/år i yield försvinner om reward-emissioner slutar",
            },
            "risk_analysis": {
                "trap_pools": len(trap_pools),
                "trap_exposure_usd": round(trap_exposure_usd, 0),
                "trap_exposure_pct": round(trap_exposure_pct, 1),
                "concentration_risk": concentration_risk,
                "top_chain_exposure": sorted(chain_exposure.items(), key=lambda x: x[1], reverse=True)[:5],
                "top_protocol_exposure": sorted(protocol_exposure.items(), key=lambda x: x[1], reverse=True)[:5],
            },
            "wow_alerts": wow_alerts,
            "exit_priority": [
                {
                    "rank": i + 1,
                    "pool_id": p["pool_id"],
                    "protocol": p["protocol"],
                    "symbol": p["symbol"],
                    "chain": p["chain"],
                    "amount_usd": p["amount_usd"],
                    "yield_risk_score": p["yield_risk_score"],
                    "yield_risk_tier": p["yield_risk_tier"],
                    "is_yield_trap": p["is_yield_trap"],
                    "reason": p.get("wow_text") or f"Risk score {p['yield_risk_score']}/100",
                }
                for i, p in enumerate(exit_priority[:10])
            ],
            "pool_breakdown": pool_results,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "zarq_url": "https://zarq.ai/yield-risk",
        }
    finally:
        conn.close()
