#!/usr/bin/env python3
"""
ZARQ CRYPTO API v2 — Sprint 3.2 Endpoints
============================================
New API endpoints for Contagion Map, Stresstest, and Transition Matrix.
Add to existing crypto_api.py router or mount separately.

New Endpoints:
  GET  /v1/crypto/contagion/{token_id}         — Token contagion profile
  GET  /v1/crypto/contagion/scores/all          — All contagion scores
  GET  /v1/crypto/contagion/scenario/{id}       — Run scenario
  GET  /v1/crypto/contagion/scenarios            — List scenarios
  GET  /v1/crypto/contagion/network              — D3.js network graph
  GET  /v1/crypto/contagion/case-studies         — Historical case studies
  POST /v1/crypto/stresstest                     — Run portfolio stresstest
  GET  /v1/crypto/stresstest/scenarios           — List stress scenarios
  GET  /v1/crypto/stresstest/portfolios          — List predefined portfolios
  GET  /v1/crypto/transition-matrix/{period}     — Transition matrix
  GET  /v1/crypto/transition/{token_id}          — Token transition history
  GET  /v1/crypto/exit-score/{token_id}          — Liquidity exit score
  GET  /v1/crypto/crash-thresholds/{token_id}    — Vol-adjusted thresholds

Usage:
  from crypto_api_v2 import router as v2_router
  app.include_router(v2_router)

Author: ZARQ
Version: 2.0
Sprint: 3.2
"""

import os
import json
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Import engines
from agentindex.crypto.contagion_map import ContagionMap
from agentindex.crypto.stresstest_engine import StresstestEngine
from agentindex.crypto.transition_matrix import TransitionEngine

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")

router = APIRouter(prefix="/v1/crypto", tags=["crypto-v3"])
router_v3 = router  # alias for discovery.py

# Singleton instances (lazy init)
_contagion: Optional[ContagionMap] = None
_stresstest: Optional[StresstestEngine] = None
_transition: Optional[TransitionEngine] = None


def get_contagion() -> ContagionMap:
    global _contagion
    if _contagion is None:
        _contagion = ContagionMap(DB_PATH)
    return _contagion


def get_stresstest() -> StresstestEngine:
    global _stresstest
    if _stresstest is None:
        _stresstest = StresstestEngine(DB_PATH)
    return _stresstest


def get_transition() -> TransitionEngine:
    global _transition
    if _transition is None:
        _transition = TransitionEngine(DB_PATH)
    return _transition


# ══════════════════════════════════════════════════════════════════════════════
# CONTAGION MAP ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/contagion/scores/all")
def get_all_contagion_scores_endpoint():
    """Get contagion scores for all rated tokens, sorted by highest risk."""
    cm = get_contagion()
    return cm.get_all_contagion_scores()


@router.get("/contagion/scenarios")
def list_contagion_scenarios_endpoint():
    """List all available contagion scenarios."""
    cm = get_contagion()
    return cm.get_available_scenarios()


@router.get("/contagion/network")
def get_contagion_network_endpoint():
    """Get D3.js network graph."""
    cm = get_contagion()
    return cm.export_network_graph()


@router.get("/contagion/case-studies")
def get_case_studies_endpoint():
    """Historical case studies."""
    cm = get_contagion()
    return cm.get_case_studies()


@router.get("/contagion/scenario/{scenario_id}")
def run_contagion_scenario_endpoint(scenario_id: str):
    """Run a contagion scenario."""
    cm = get_contagion()
    result = cm.run_scenario(scenario_id)
    if "error" in result:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/contagion/{token_id}")
def get_token_contagion(token_id: str):
    """
    Get contagion profile for a token.
    Returns dependencies, exposure scores, correlated tokens, and contagion score 0-10.
    """
    cm = get_contagion()
    result = cm.get_token_contagion(token_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# STRESSTEST ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

class StresstestRequest(BaseModel):
    """Request body for portfolio stress test."""
    holdings: Optional[Dict[str, float]] = Field(
        None,
        description='Token holdings as {token_id: weight}. Example: {"bitcoin": 0.5, "ethereum": 0.3, "solana": 0.2}',
        examples=[{"bitcoin": 0.5, "ethereum": 0.3, "solana": 0.2}],
    )
    portfolio_id: Optional[str] = Field(
        None,
        description="Predefined portfolio: alpha_fund, dynamic_fund, conservative_fund, btc_only, top10_equal",
    )
    scenario: str = Field(
        "btc_crash_50pct",
        description="Scenario: btc_crash_50pct, eth_smart_contract_exploit, stablecoin_crisis, regulatory_crackdown",
    )
    portfolio_value_usd: float = Field(100000, description="Total portfolio value in USD")


@router.post("/stresstest")
def run_stresstest(req: StresstestRequest):
    """
    Run a portfolio stress test.
    Provide either holdings (custom portfolio) or portfolio_id (predefined).
    Returns per-token impact, total loss, and risk recommendations.
    """
    engine = get_stresstest()
    result = engine.run_stresstest(
        holdings=req.holdings,
        portfolio_id=req.portfolio_id,
        scenario=req.scenario,
        portfolio_value_usd=req.portfolio_value_usd,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/stresstest/scenarios")
def list_stress_scenarios():
    """List available stress test scenarios."""
    engine = get_stresstest()
    return engine.get_available_scenarios()


@router.get("/stresstest/portfolios")
def list_predefined_portfolios():
    """List predefined portfolios for stress testing."""
    engine = get_stresstest()
    return engine.get_predefined_portfolios()


# ══════════════════════════════════════════════════════════════════════════════
# TRANSITION MATRIX ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/transition-matrix/{period}")
def get_transition_matrix(period: str = "90d"):
    """
    Get rating transition matrix for a period (30d, 90d, 365d).
    Shows probability of rating grade migration.
    """
    if period not in ["30d", "90d", "365d"]:
        raise HTTPException(status_code=400, detail="Period must be 30d, 90d, or 365d")
    te = get_transition()
    result = te.get_transition_matrix(period)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/transition/{token_id}")
def get_token_transitions(token_id: str):
    """Get complete rating transition history for a token."""
    te = get_transition()
    result = te.get_token_transition_history(token_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/exit-score/{token_id}")
def get_exit_score(
    token_id: str,
    position_usd: float = Query(100000, description="Position size in USD"),
):
    """
    Get liquidity exit score (0-100) for a token.
    Estimates slippage, exit time, and difficulty based on volume and market cap.
    """
    te = get_transition()
    result = te.get_exit_score(token_id, position_usd)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/crash-thresholds/{token_id}")
def get_crash_thresholds(token_id: str):
    """
    Get volatility-adjusted crash thresholds for a token.
    What counts as a 'dip', 'correction', or 'crash' depends on the token's historical volatility.
    """
    te = get_transition()
    result = te.get_crash_thresholds(token_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE APP (for testing)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from fastapi import FastAPI
    import uvicorn

    app = FastAPI(
        title="ZARQ Crypto Risk Intelligence API v2",
        description="Contagion Map, Stresstest, Transition Matrix",
        version="2.0",
    )
    app.include_router(router)

    @app.get("/")
    def root():
        return {
            "service": "ZARQ Crypto Risk Intelligence",
            "version": "2.0",
            "sprint": "3.2",
            "endpoints": {
                "contagion": "/v1/crypto/contagion/{token_id}",
                "scenario": "/v1/crypto/contagion/scenario/{scenario_id}",
                "stresstest": "POST /v1/crypto/stresstest",
                "transition_matrix": "/v1/crypto/transition-matrix/{period}",
                "exit_score": "/v1/crypto/exit-score/{token_id}",
                "crash_thresholds": "/v1/crypto/crash-thresholds/{token_id}",
            }
        }

    uvicorn.run(app, host="0.0.0.0", port=8002)

# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 8: PROPAGATED RISK ENGINE + CRASH SHIELD API
# ══════════════════════════════════════════════════════════════════════════════

from agentindex.crypto.propagated_risk_engine import get_engine
from agentindex.crypto.crash_shield_api import get_crash_shield_manager, PortfolioAnalyzer as PortfolioAnalyzerS8
from pydantic import Field as S8Field
from typing import List as S8List, Optional as S8Optional

class HoldingItem(BaseModel):
    token: str = S8Field(..., description="Token symbol e.g. ETH, BTC, PEPE")
    weight: S8Optional[float] = S8Field(None, description="Portfolio weight 0-1")
    value_usd: S8Optional[float] = S8Field(None, description="USD value")

class CrashShieldRequest(BaseModel):
    webhook_url: str = S8Field(..., description="HTTPS URL that receives POST alerts")
    holdings: S8List[HoldingItem]
    portfolio_value_usd: float = S8Field(100_000)
    alert_levels: S8List[str] = S8Field(default=["CRITICAL", "HIGH"])

class PortfolioAnalyzeRequest(BaseModel):
    holdings: S8List[HoldingItem]
    portfolio_value_usd: float = S8Field(100_000)
    include_cascade: bool = S8Field(True)

@router.get("/cascade/simulate")
def simulate_cascade_endpoint(
    trigger: str = Query(..., description="Token symbol, token_id, or chain name"),
    scenario: str = Query("collapse", description="collapse|btc_crash|stablecoin|exchange|custom"),
    severity: float = Query(1.0, ge=0.0, le=1.0),
    max_hops: int = Query(4, ge=1, le=6),
):
    """Simulate a risk cascade from a trigger node."""
    engine = get_engine()
    return engine.simulate_cascade(trigger_id=trigger, scenario=scenario, severity=severity, max_hops=max_hops)

@router.get("/cascade/graph")
def get_cascade_graph(max_nodes: int = Query(200, ge=10, le=500)):
    """Export risk dependency graph (D3.js compatible)."""
    engine = get_engine()
    return engine.export_graph_summary(max_nodes=max_nodes)

@router.get("/cascade/hotspots")
def get_cascade_hotspots(top_n: int = Query(20, ge=5, le=50)):
    """Identify highest systemic risk nodes in the graph."""
    engine = get_engine()
    return engine.get_hotspots(top_n=top_n)

@router.get("/cascade/stats")
def get_cascade_stats():
    """Graph engine stats — nodes, edges, load time."""
    engine = get_engine()
    return engine.get_stats()

@router.post("/portfolio/crash-shield")
def register_crash_shield(req: CrashShieldRequest):
    """Register a webhook for real-time crash alerts on your portfolio."""
    manager = get_crash_shield_manager()
    return manager.register_webhook(
        url=req.webhook_url,
        portfolio=[h.dict() for h in req.holdings],
        alert_levels=req.alert_levels,
        portfolio_value_usd=req.portfolio_value_usd,
    )

@router.get("/portfolio/crash-shield/webhooks")
def list_crash_shield_webhooks():
    """List all active Crash Shield webhook registrations."""
    manager = get_crash_shield_manager()
    return {"webhooks": manager.list_webhooks()}

@router.get("/portfolio/crash-shield/prevented")
def get_prevented_losses():
    """Aggregate Prevented $X metric across all Crash Shield users."""
    manager = get_crash_shield_manager()
    return manager.get_prevented_total()

@router.post("/portfolio/analyze")
def analyze_portfolio(req: PortfolioAnalyzeRequest):
    """Complete portfolio risk analysis — direct + indirect cascade risk."""
    analyzer = PortfolioAnalyzerS8()
    return analyzer.analyze(
        holdings=[h.dict() for h in req.holdings],
        portfolio_value_usd=req.portfolio_value_usd,
        include_cascade=req.include_cascade,
    )
