"""
Sprint 9: Yield Risk API Router
Monteras i discovery.py

Endpoints:
  GET /v1/yield/risk/{protocol}/{pool}   — Yield Risk Score för specifik pool
  GET /v1/yield/traps                    — Alla Yield Traps globalt
  GET /v1/yield/overview                 — Global yield market overview
  GET /v1/yield/protocol/{protocol}      — Alla pooler för ett protokoll
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import time

from agentindex.crypto.yield_risk_engine import (
    get_yield_risk,
    get_yield_traps,
    get_yield_overview,
)
import os
import sqlite3

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)).replace("/agentindex-factory/", "/agentindex/"),
    "crypto_trust.db",
)

router_yield = APIRouter(prefix="/v1/yield", tags=["Yield Risk"])


# ── GET /v1/yield/risk/{protocol}/{pool} ─────────────────────────────────────

@router_yield.get("/risk/{protocol}/{pool}")
async def yield_risk_endpoint(
    protocol: str,
    pool: str,
):
    """
    Yield Risk Score for a specific pool.

    - **protocol**: Protocol name (e.g. "aave-v3", "lido", "uniswap-v3")
    - **pool**: Pool ID (UUID from DeFiLlama) or symbol (e.g. "USDC-ETH")

    Returns yield_risk_score (0-100), yield_risk_tier, is_yield_trap flag,
    and component breakdown.
    """
    t0 = time.time()
    result = get_yield_risk(protocol, pool)
    result["response_ms"] = round((time.time() - t0) * 1000, 1)

    if not result.get("found"):
        raise HTTPException(
            status_code=404,
            detail=f"Pool not found. Use /v1/yield/protocol/{protocol} to see available pools."
        )
    return result


# ── GET /v1/yield/traps ──────────────────────────────────────────────────────

@router_yield.get("/traps")
async def yield_traps_endpoint(
    min_apy: float = Query(50.0, description="Minimum APY threshold (default 50%)"),
    chain: Optional[str] = Query(None, description="Filter by chain (e.g. 'Ethereum', 'Solana')"),
    limit: int = Query(50, ge=1, le=200, description="Max results per category"),
    include_stablecoins: bool = Query(False, description="Include stablecoin pools"),
):
    """
    Detect all Yield Traps globally.

    A Yield Trap is identified when ANY of:
    - APY > 500% with >80% reward-token dependency (unsustainable emissions)
    - Protocol token rated CRITICAL/WARNING + APY > 100%
    - IL risk flagged + APY < 10% (poor risk/reward)
    - TVL < $100K + APY > 50% (rug risk)
    - Reward ratio > 90% + APY > 50%

    Returns trap list, high-risk list, chain breakdown, and tier distribution.
    """
    t0 = time.time()
    result = get_yield_traps(
        min_apy=min_apy,
        chain=chain,
        limit=limit,
        include_stablecoins=include_stablecoins,
    )
    result["response_ms"] = round((time.time() - t0) * 1000, 1)
    return result


# ── GET /v1/yield/overview ───────────────────────────────────────────────────

@router_yield.get("/overview")
async def yield_overview_endpoint():
    """
    Global yield market overview.

    Returns aggregate stats: total pools, TVL, APY distribution,
    top TVL pools, and chain breakdown.
    """
    t0 = time.time()
    result = get_yield_overview()
    result["response_ms"] = round((time.time() - t0) * 1000, 1)
    return result


# ── GET /v1/yield/protocol/{protocol} ───────────────────────────────────────

@router_yield.get("/protocol/{protocol}")
async def yield_protocol_endpoint(
    protocol: str,
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("tvl", description="Sort by: tvl, apy, risk"),
):
    """
    All yield pools for a specific protocol, enriched with Yield Risk Scores.
    """
    t0 = time.time()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT * FROM defi_yields
            WHERE LOWER(project) = LOWER(?)
            ORDER BY tvl_usd DESC NULLS LAST
            LIMIT ?
        """, (protocol, limit * 2)).fetchall()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"Protocol '{protocol}' not found in yield database."
            )

        from agentindex.crypto.yield_risk_engine import (
            compute_yield_risk_score, _get_protocol_risk
        )

        risk_level, crash_prob = _get_protocol_risk(conn, protocol)

        pools = []
        for row in rows:
            scoring = compute_yield_risk_score(
                apy=row["apy"] or 0,
                apy_base=row["apy_base"] or 0,
                apy_reward=row["apy_reward"] or 0,
                tvl_usd=row["tvl_usd"],
                il_risk=row["il_risk"] or "no",
                stablecoin=row["stablecoin"] or 0,
                risk_level=risk_level,
                crash_prob=crash_prob,
            )
            pools.append({
                "pool_id": row["pool_id"],
                "chain": row["chain"],
                "symbol": row["symbol"],
                "tvl_usd": row["tvl_usd"],
                "apy": row["apy"],
                "apy_base": row["apy_base"] or 0,
                "apy_reward": row["apy_reward"] or 0,
                "il_risk": row["il_risk"],
                "stablecoin": bool(row["stablecoin"]),
                **scoring,
            })

        # Sort
        if sort_by == "apy":
            pools.sort(key=lambda x: x["apy"] or 0, reverse=True)
        elif sort_by == "risk":
            pools.sort(key=lambda x: x["yield_risk_score"], reverse=True)
        else:
            pools.sort(key=lambda x: x["tvl_usd"] or 0, reverse=True)

        trap_count = sum(1 for p in pools if p["is_yield_trap"])
        avg_risk = round(sum(p["yield_risk_score"] for p in pools) / len(pools), 1) if pools else 0

        return {
            "protocol": protocol,
            "protocol_risk_level": risk_level,
            "protocol_crash_prob": round(crash_prob, 3) if crash_prob else None,
            "total_pools": len(pools),
            "yield_traps": trap_count,
            "avg_yield_risk_score": avg_risk,
            "pools": pools[:limit],
            "response_ms": round((time.time() - t0) * 1000, 1),
            "zarq_url": "https://zarq.ai/yield-risk",
        }
    finally:
        conn.close()
@router_yield.get("/pool/{pool_id}")
async def yield_pool_detail(pool_id: str):
    """
    Full pool-analys: metadata + risk score + historisk APY/TVL + divergens-signaler.
    Används för per-pool detaljsida zarq.ai/yield/pool/{pool_id}.
    """
    import time
    t0 = time.time()
    from agentindex.crypto.yield_divergence_engine import get_pool_full_analysis
    result = get_pool_full_analysis(pool_id)
    result["response_ms"] = round((time.time() - t0) * 1000, 1)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── GET /v1/yield/insights ───────────────────────────────────────────────────

@router_yield.get("/insights")
async def yield_insights_endpoint(
    limit: int = Query(20, ge=1, le=100),
):
    """
    Global WOW-insikter — pooler med starkast divergens-signaler just nu.
    TVL-exodus, APY-spikes, emission-cliffs, reward-kollaps.
    Kräver att yield_history_crawler.py körts minst en gång.
    """
    import time
    t0 = time.time()
    from agentindex.crypto.yield_divergence_engine import get_global_wow_insights
    result = get_global_wow_insights(limit=limit)
    result["response_ms"] = round((time.time() - t0) * 1000, 1)
    return result


# ── POST /v1/yield/portfolio/analyze ────────────────────────────────────────

from pydantic import BaseModel

class PoolHolding(BaseModel):
    pool_id: str
    amount_usd: float

@router_yield.post("/portfolio/analyze")
async def yield_portfolio_analyze(holdings: list[PoolHolding]):
    """
    Portföljanalys för yield-positioner.

    Input: lista av {pool_id, amount_usd}
    Output:
      - Viktad portfölj-riskscore
      - Yield at risk (vad försvinner om reward-emissioner slutar)
      - Trap-exponering
      - Koncentrationsrisk (chain/protokoll)
      - WOW-alerts (aktiva divergens-signaler i din portfölj)
      - Exit-prioritering

    Exempel:
    [
      {"pool_id": "747c1d2a-c668-4682-b9f9-296708a3dd90", "amount_usd": 10000},
      {"pool_id": "46bd2bdf-6d92-4066-b482-e885ee172264", "amount_usd": 5000}
    ]
    """
    import time
    t0 = time.time()
    from agentindex.crypto.yield_portfolio_analyzer import analyze_yield_portfolio
    result = analyze_yield_portfolio([h.dict() for h in holdings])
    result["response_ms"] = round((time.time() - t0) * 1000, 1)
    return result
