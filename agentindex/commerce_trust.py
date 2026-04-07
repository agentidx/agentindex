"""
Commerce Trust Layer — Verify AI agents before transactions.
POST /v1/commerce/verify
POST /v1/commerce/verify/batch
"""
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("nerq.commerce")

router_commerce = APIRouter(tags=["commerce"])

# Transaction type thresholds (higher = stricter)
TRANSACTION_THRESHOLDS = {
    "purchase": {"low": 60, "medium": 70, "high": 80, "critical": 90},
    "delegation": {"low": 50, "medium": 65, "high": 75, "critical": 85},
    "data_exchange": {"low": 40, "medium": 55, "high": 65, "critical": 80},
    "payment": {"low": 65, "medium": 75, "high": 85, "critical": 95},
}

# In-memory cache (Redis preferred but fallback to dict)
_cache = {}
_CACHE_TTL = 300  # 5 minutes

# Rate limiting
_rate_limits = {}  # ip_hash -> (count, window_start)
RATE_LIMIT = 1000
RATE_WINDOW = 3600


class VerifyRequest(BaseModel):
    agent_id: str = Field(..., description="Name of the agent initiating the transaction")
    transaction_type: str = Field("purchase", description="Type: purchase|delegation|data_exchange|payment")
    counterparty_id: str = Field(..., description="Name of the counterparty agent")
    amount_range: str = Field("medium", description="Risk level: low|medium|high|critical")


class BatchVerifyRequest(BaseModel):
    transactions: list[VerifyRequest]


def _get_ip_hash(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _check_rate_limit(ip_hash: str) -> bool:
    now = time.time()
    if ip_hash in _rate_limits:
        count, window_start = _rate_limits[ip_hash]
        if now - window_start > RATE_WINDOW:
            _rate_limits[ip_hash] = (1, now)
            return True
        if count >= RATE_LIMIT:
            return False
        _rate_limits[ip_hash] = (count + 1, window_start)
    else:
        _rate_limits[ip_hash] = (1, now)
    return True


def _lookup_trust(name: str) -> dict:
    """Look up trust score for an agent. Uses cache."""
    cache_key = f"commerce:{name}"
    now = time.time()

    if cache_key in _cache:
        cached, ts = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return cached

    # Try PostgreSQL lookup
    result = {"name": name, "trust_score": None, "trust_grade": None, "found": False}
    try:
        from agentindex.db.models import get_session
        from sqlalchemy import text
        session = get_session()
        row = session.execute(text(
            "SELECT trust_score_v2, trust_score, category, stars FROM entity_lookup WHERE name = :name LIMIT 1"
        ), {"name": name}).fetchone()
        if row:
            score = row[0] or row[1]
            result = {
                "name": name,
                "trust_score": float(score) if score else None,
                "trust_grade": _score_to_grade(float(score)) if score else None,
                "category": row[2],
                "stars": row[3],
                "found": True,
            }
        session.close()
    except Exception as e:
        logger.warning(f"Trust lookup failed for {name}: {e}")

    _cache[cache_key] = (result, now)
    return result


def _score_to_grade(score: float) -> str:
    if score >= 90: return "A+"
    if score >= 85: return "A"
    if score >= 80: return "A-"
    if score >= 75: return "B+"
    if score >= 70: return "B"
    if score >= 65: return "B-"
    if score >= 60: return "C+"
    if score >= 55: return "C"
    if score >= 50: return "C-"
    if score >= 40: return "D"
    return "F"


def _verify_transaction(req: VerifyRequest) -> dict:
    """Core verification logic."""
    t0 = time.time()

    agent = _lookup_trust(req.agent_id)
    counterparty = _lookup_trust(req.counterparty_id)

    # Get threshold
    tx_type = req.transaction_type if req.transaction_type in TRANSACTION_THRESHOLDS else "purchase"
    amount = req.amount_range if req.amount_range in ("low", "medium", "high", "critical") else "medium"
    threshold = TRANSACTION_THRESHOLDS[tx_type][amount]

    # Build risk factors
    risk_factors = []

    agent_score = agent.get("trust_score")
    cp_score = counterparty.get("trust_score")

    if not agent.get("found"):
        risk_factors.append(f"Agent '{req.agent_id}' not found in trust index")
    if not counterparty.get("found"):
        risk_factors.append(f"Counterparty '{req.counterparty_id}' not found in trust index")

    if agent_score is not None and agent_score < threshold:
        risk_factors.append(f"Agent trust score ({agent_score:.1f}) below threshold ({threshold})")
    if cp_score is not None and cp_score < threshold:
        risk_factors.append(f"Counterparty trust score ({cp_score:.1f}) below threshold ({threshold})")

    if amount in ("high", "critical") and (agent_score is None or cp_score is None):
        risk_factors.append(f"Unverified agent in {amount}-value transaction")

    # Verdict
    if agent_score is None or cp_score is None:
        verdict = "reject" if amount in ("high", "critical") else "review"
    elif agent_score >= threshold and cp_score >= threshold:
        verdict = "approve"
    elif agent_score >= threshold * 0.85 and cp_score >= threshold * 0.85:
        verdict = "review"
    else:
        verdict = "reject"

    # Recommended action
    actions = {
        "approve": "Transaction may proceed. Both parties meet trust requirements.",
        "review": "Manual review recommended before proceeding.",
        "reject": "Transaction should not proceed. Trust requirements not met.",
    }

    elapsed_ms = (time.time() - t0) * 1000

    return {
        "verdict": verdict,
        "agent_trust_score": agent_score,
        "agent_trust_grade": agent.get("trust_grade"),
        "counterparty_trust_score": cp_score,
        "counterparty_trust_grade": counterparty.get("trust_grade"),
        "transaction_type": tx_type,
        "amount_range": amount,
        "threshold_applied": threshold,
        "risk_factors": risk_factors,
        "recommended_action": actions[verdict],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "response_time_ms": round(elapsed_ms, 1),
    }


@router_commerce.post("/v1/commerce/verify")
async def commerce_verify(req: VerifyRequest, request: Request):
    ip_hash = _get_ip_hash(request)
    if not _check_rate_limit(ip_hash):
        return JSONResponse({"error": "Rate limit exceeded (1000/hour)"}, status_code=429)

    result = _verify_transaction(req)

    # Log transaction
    try:
        import uuid as _uuid
        vid = f"txn_{_uuid.uuid4().hex[:12]}"
        result["verification_id"] = vid
        conn = sqlite3.connect(_SQLITE_PATH, timeout=2)
        conn.execute("""
            INSERT INTO commerce_transactions
                (verification_id, buyer, seller, transaction_type, decision,
                 buyer_score, seller_score, risk_factors)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (vid, req.agent_id, req.counterparty_id, req.transaction_type,
              result["verdict"], result.get("agent_trust_score"),
              result.get("counterparty_trust_score"),
              "|".join(result.get("risk_factors", []))))
        conn.commit()
        conn.close()
    except Exception:
        pass

    return JSONResponse(result)


@router_commerce.post("/v1/commerce/verify/batch")
async def commerce_verify_batch(req: BatchVerifyRequest, request: Request):
    ip_hash = _get_ip_hash(request)
    if not _check_rate_limit(ip_hash):
        return JSONResponse({"error": "Rate limit exceeded (1000/hour)"}, status_code=429)

    if len(req.transactions) > 50:
        return JSONResponse({"error": "Maximum 50 transactions per batch"}, status_code=400)

    results = [_verify_transaction(tx) for tx in req.transactions]

    summary = {
        "total": len(results),
        "approved": sum(1 for r in results if r["verdict"] == "approve"),
        "review": sum(1 for r in results if r["verdict"] == "review"),
        "rejected": sum(1 for r in results if r["verdict"] == "reject"),
    }

    return JSONResponse({"results": results, "summary": summary})


# ── Commerce Stats & Transaction Logging ──────────────────────

import os
import sqlite3
import uuid

_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "crypto", "crypto_trust.db")


def _ensure_commerce_tables():
    try:
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS commerce_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                verification_id TEXT UNIQUE,
                buyer TEXT,
                seller TEXT,
                transaction_type TEXT,
                value_usd REAL,
                decision TEXT,
                buyer_score REAL,
                seller_score REAL,
                risk_factors TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_commerce_ts ON commerce_transactions(timestamp)")
        conn.commit()
        conn.close()
    except Exception:
        pass


_ensure_commerce_tables()


@router_commerce.get("/v1/commerce/stats")
async def commerce_stats():
    """Transaction verification statistics."""
    try:
        conn = sqlite3.connect(_SQLITE_PATH, timeout=2)
        conn.row_factory = sqlite3.Row

        total_today = conn.execute(
            "SELECT COUNT(*) FROM commerce_transactions WHERE date(timestamp) = date('now')"
        ).fetchone()[0]
        total_week = conn.execute(
            "SELECT COUNT(*) FROM commerce_transactions WHERE timestamp >= datetime('now', '-7 days')"
        ).fetchone()[0]
        total_month = conn.execute(
            "SELECT COUNT(*) FROM commerce_transactions WHERE timestamp >= datetime('now', '-30 days')"
        ).fetchone()[0]
        total_all = conn.execute("SELECT COUNT(*) FROM commerce_transactions").fetchone()[0]

        decisions = conn.execute("""
            SELECT decision, COUNT(*) as cnt
            FROM commerce_transactions
            WHERE timestamp >= datetime('now', '-30 days')
            GROUP BY decision
        """).fetchall()

        top_pairs = conn.execute("""
            SELECT buyer, seller, COUNT(*) as cnt
            FROM commerce_transactions
            WHERE timestamp >= datetime('now', '-30 days')
            GROUP BY buyer, seller
            ORDER BY cnt DESC LIMIT 10
        """).fetchall()

        conn.close()

        return JSONResponse(content={
            "transactions": {
                "today": total_today,
                "this_week": total_week,
                "this_month": total_month,
                "all_time": total_all,
            },
            "decisions_30d": {r["decision"]: r["cnt"] for r in decisions},
            "top_pairs_30d": [
                {"buyer": r["buyer"], "seller": r["seller"], "count": r["cnt"]}
                for r in top_pairs
            ],
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
