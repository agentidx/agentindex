"""
zarq_batch_api.py — ZARQ Batch Endpoints
Sprint 10: Production-grade batch processing

POST /v1/crypto/ratings/batch   — up to 100 tokens → ratings
POST /v1/crypto/ndd/batch       — up to 100 tokens → NDD scores
POST /v1/crypto/safety/batch    — up to 100 token addresses → safety checks

Additive only — mounts alongside existing crypto_api_v2 routes.
Does NOT modify any existing nerq.ai routes.
"""

import time
import sqlite3
import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Response, HTTPException
from pydantic import BaseModel, Field

# ── Config ────────────────────────────────────────────────────────────────────
import os
DB_PATH = os.path.expanduser("~/agentindex/agentindex/crypto/crypto_trust.db")
BATCH_LIMIT = 100

router_batch = APIRouter(prefix="/v1/crypto", tags=["Batch"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def latest_run_date(conn, table="crypto_rating_daily"):
    row = conn.execute(f"SELECT MAX(run_date) as d FROM {table}").fetchone()
    return row["d"] if row else None

def parse_json_field(value):
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}

def wrap_response(data, meta=None):
    base_meta = {"version": "1.0", "response_ms": 0}
    if meta:
        base_meta.update(meta)
    return {"data": data, "meta": base_meta}

def add_cache(response: Response, seconds: int):
    response.headers["Cache-Control"] = f"public, max-age={seconds}"
    response.headers["X-Cache-TTL"] = str(seconds)


# ── Request / Response Models ─────────────────────────────────────────────────

class BatchRatingRequest(BaseModel):
    token_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=BATCH_LIMIT,
        description="List of token IDs (e.g. ['bitcoin', 'ethereum']). Max 100.",
        example=["bitcoin", "ethereum", "solana"]
    )

class BatchNDDRequest(BaseModel):
    token_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=BATCH_LIMIT,
        description="List of token IDs. Max 100.",
        example=["bitcoin", "ethereum"]
    )

class BatchSafetyRequest(BaseModel):
    token_addresses: List[str] = Field(
        ...,
        min_items=1,
        max_items=BATCH_LIMIT,
        description="List of token contract addresses or IDs. Max 100.",
        example=["0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"]
    )


# ── POST /v1/crypto/ratings/batch ─────────────────────────────────────────────

@router_batch.post("/ratings/batch", summary="Batch Trust Score ratings (max 100 tokens)")
def batch_ratings(req: BatchRatingRequest, response: Response):
    """
    Fetch Trust Score ratings for up to 100 tokens in a single request.
    Returns results dict keyed by token_id. Missing tokens listed in `not_found`.
    Optimized with a single SQL IN query — no N+1.
    """
    t0 = time.time()
    token_ids = [t.lower().strip() for t in req.token_ids][:BATCH_LIMIT]

    if not token_ids:
        raise HTTPException(status_code=400, detail="token_ids must not be empty")

    conn = get_db()
    run_date = latest_run_date(conn)

    placeholders = ",".join("?" * len(token_ids))

    if run_date:
        rows = conn.execute(f"""
            SELECT token_id, symbol, name, market_cap_rank, rating, score,
                   pillar_1, pillar_2, pillar_3, pillar_4, pillar_5,
                   breakdown, price_usd, market_cap, volume_24h,
                   price_change_24h, price_change_7d, price_change_30d,
                   run_date, calculated_at
            FROM crypto_rating_daily
            WHERE token_id IN ({placeholders}) AND run_date = ?
        """, (*token_ids, run_date)).fetchall()
    else:
        # Fallback to history
        rows = conn.execute(f"""
            SELECT token_id, '' as symbol, '' as name, 0 as market_cap_rank,
                   rating, score, pillar_1, pillar_2, pillar_3, pillar_4, pillar_5,
                   breakdown, 0 as price_usd, 0 as market_cap, 0 as volume_24h,
                   0 as price_change_24h, 0 as price_change_7d, 0 as price_change_30d,
                   year_month as run_date, calculated_at
            FROM crypto_rating_history
            WHERE token_id IN ({placeholders})
            GROUP BY token_id
            HAVING run_date = MAX(run_date)
        """, token_ids).fetchall()

    conn.close()

    results = {}
    for row in rows:
        data = dict(row)
        breakdown = parse_json_field(data.pop("breakdown", None))
        data["breakdown"] = breakdown
        data["pillars"] = {
            "security":   data.pop("pillar_1", None),
            "compliance": data.pop("pillar_2", None),
            "maintenance":data.pop("pillar_3", None),
            "popularity": data.pop("pillar_4", None),
            "ecosystem":  data.pop("pillar_5", None),
        }
        tid = data["token_id"]
        score = data.get("score", 0) or 0
        data["summary"] = (
            f"According to ZARQ's Crypto Trust Score, {tid} is rated "
            f"{data.get('rating')} with a composite score of {score:.1f}/100 "
            f"as of {data.get('run_date')}."
        )
        results[tid] = data

    found = set(results.keys())
    not_found = [t for t in token_ids if t not in found]

    elapsed_ms = round((time.time() - t0) * 1000, 1)
    add_cache(response, 300)

    return wrap_response(
        {"results": results, "not_found": not_found},
        {
            "run_date": run_date,
            "requested": len(token_ids),
            "found": len(found),
            "not_found_count": len(not_found),
            "response_ms": elapsed_ms,
        }
    )


# ── POST /v1/crypto/ndd/batch ─────────────────────────────────────────────────

@router_batch.post("/ndd/batch", summary="Batch NDD distress scores (max 100 tokens)")
def batch_ndd(req: BatchNDDRequest, response: Response):
    """
    Fetch NDD (Distance-to-Default) distress scores for up to 100 tokens.
    Single SQL IN query. Returns results keyed by token_id.
    """
    t0 = time.time()
    token_ids = [t.lower().strip() for t in req.token_ids][:BATCH_LIMIT]

    conn = get_db()
    placeholders = ",".join("?" * len(token_ids))

    rows = conn.execute(f"""
        SELECT n.token_id, n.ndd_score, n.ndd_tier, n.distance_to_default,
               n.volatility_30d, n.crash_probability, n.structural_alert,
               n.calculated_at,
               r.rating, r.score as trust_score
        FROM nerq_risk_signals n
        LEFT JOIN (
            SELECT token_id, rating, score,
                   ROW_NUMBER() OVER (PARTITION BY token_id ORDER BY run_date DESC) as rn
            FROM crypto_rating_daily
        ) r ON r.token_id = n.token_id AND r.rn = 1
        WHERE n.token_id IN ({placeholders})
        GROUP BY n.token_id
        HAVING n.calculated_at = MAX(n.calculated_at)
    """, token_ids).fetchall()

    conn.close()

    results = {}
    for row in rows:
        data = dict(row)
        tid = data["token_id"]
        ndd = data.get("ndd_score") or 0
        tier = data.get("ndd_tier", "UNKNOWN")
        data["summary"] = (
            f"{tid} has an NDD score of {ndd:.2f} ({tier} tier). "
            f"Crash probability: {(data.get('crash_probability') or 0)*100:.1f}%."
        )
        results[tid] = data

    found = set(results.keys())
    not_found = [t for t in token_ids if t not in found]
    elapsed_ms = round((time.time() - t0) * 1000, 1)

    add_cache(response, 180)

    return wrap_response(
        {"results": results, "not_found": not_found},
        {
            "requested": len(token_ids),
            "found": len(found),
            "not_found_count": len(not_found),
            "response_ms": elapsed_ms,
        }
    )


# ── POST /v1/crypto/safety/batch ──────────────────────────────────────────────

@router_batch.post("/safety/batch", summary="Batch pre-trade safety checks (max 100 tokens)")
def batch_safety(req: BatchSafetyRequest, response: Response):
    """
    Pre-trade safety check for up to 100 token addresses/IDs.
    Returns SAFE / CAUTION / UNSAFE verdict per token.
    Designed for AI agents and trading bots doing multi-token screening.
    """
    t0 = time.time()
    addresses = [a.lower().strip() for a in req.token_addresses][:BATCH_LIMIT]

    conn = get_db()
    placeholders = ",".join("?" * len(addresses))
    run_date = latest_run_date(conn)

    rows = conn.execute(f"""
        SELECT token_id, symbol, rating, score,
               price_change_24h, price_change_7d, volume_24h
        FROM crypto_rating_daily
        WHERE (token_id IN ({placeholders}) OR symbol IN ({placeholders}))
          AND run_date = ?
        GROUP BY token_id
    """, (*addresses, *addresses, run_date)).fetchall() if run_date else []

    conn.close()

    results = {}
    for row in rows:
        data = dict(row)
        tid = data["token_id"]
        rating = data.get("rating", "UNKNOWN")
        score = data.get("score") or 0

        if rating in ("SAFE", "WATCH"):
            verdict = "SAFE"
        elif rating in ("WARNING",):
            verdict = "CAUTION"
        elif rating in ("CRITICAL",):
            verdict = "UNSAFE"
        else:
            verdict = "UNKNOWN"

        results[tid] = {
            "token_id": tid,
            "symbol": data.get("symbol"),
            "verdict": verdict,
            "rating": rating,
            "trust_score": score,
            "price_change_24h": data.get("price_change_24h"),
            "price_change_7d": data.get("price_change_7d"),
            "volume_24h": data.get("volume_24h"),
            "recommendation": (
                "Proceed with standard risk management." if verdict == "SAFE"
                else "Reduce position size. Elevated risk signals detected." if verdict == "CAUTION"
                else "Do not trade. Critical risk signals active." if verdict == "UNSAFE"
                else "Insufficient data. Treat as high risk."
            )
        }

    found = set(results.keys())
    not_found = [a for a in addresses if a not in found]
    elapsed_ms = round((time.time() - t0) * 1000, 1)

    add_cache(response, 60)

    return wrap_response(
        {"results": results, "not_found": not_found},
        {
            "run_date": run_date,
            "requested": len(addresses),
            "found": len(found),
            "not_found_count": len(not_found),
            "response_ms": elapsed_ms,
        }
    )


# ── Mount helper ──────────────────────────────────────────────────────────────

def mount_batch_api(app):
    app.include_router(router_batch)
