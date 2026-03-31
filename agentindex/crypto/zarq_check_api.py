"""
ZARQ Check API — Sprint 1
Zero-friction token risk check: GET /v1/check/{token}
No auth, no API key, no signup.
"""

import os
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db")

router_check = APIRouter(tags=["check"])
router_vitality = APIRouter(tags=["vitality"])


@router_check.get("/v1/check/")
@router_check.get("/v1/check")
def check_no_token():
    """Catch /v1/check/ without a token — return usage hint."""
    return JSONResponse(status_code=400, content={
        "error": "Missing token. Usage: GET /v1/check/{token_id}",
        "example": "/v1/check/bitcoin",
        "docs": "https://zarq.ai/zarq/docs",
    })


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _token_count(conn):
    """Count of tokens with risk signals on the latest signal date."""
    row = conn.execute(
        "SELECT COUNT(DISTINCT token_id) as n FROM nerq_risk_signals "
        "WHERE signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)"
    ).fetchone()
    return row["n"] if row else 0


def _verdict(risk_level: str) -> str:
    """Map internal risk_level to a user-facing verdict."""
    if risk_level == "CRITICAL":
        return "CRITICAL"
    if risk_level == "WARNING":
        return "WARNING"
    # WATCH and SAFE both map to SAFE
    return "SAFE"


@router_check.get("/v1/check/{token}")
def check_token(token: str, response: Response):
    """
    Zero-friction token risk check.
    Returns trust score, distance-to-default, crash probability, and verdict.
    """
    conn = _get_db()

    # Get latest signal date
    sd_row = conn.execute(
        "SELECT MAX(signal_date) as d FROM nerq_risk_signals"
    ).fetchone()
    signal_date = sd_row["d"] if sd_row else None

    if not signal_date:
        conn.close()
        return JSONResponse(
            status_code=503,
            content={"error": "Risk pipeline unavailable", "detail": "No signal data found"},
        )

    # Main join query (CTE avoids correlated subquery on crash_model)
    row = conn.execute(
        """
        WITH max_crash AS (
            SELECT token_id, MAX(date) as max_date
            FROM crash_model_v3_predictions
            GROUP BY token_id
        )
        SELECT
            s.token_id,
            s.risk_level,
            s.trust_score,
            s.ndd_current,
            s.structural_weakness,
            r.score   AS rating_score,
            r.rating  AS rating_grade,
            r.name,
            n.symbol,
            n.price_usd,
            r.market_cap,
            c.crash_prob_v3
        FROM nerq_risk_signals s
        LEFT JOIN crypto_rating_daily r
            ON s.token_id = r.token_id
            AND r.run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
        LEFT JOIN crypto_ndd_daily n
            ON s.token_id = n.token_id
            AND n.run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)
        LEFT JOIN max_crash mc ON s.token_id = mc.token_id
        LEFT JOIN crash_model_v3_predictions c
            ON s.token_id = c.token_id AND c.date = mc.max_date
        WHERE s.token_id = ? AND s.signal_date = ?
        """,
        (token, signal_date),
    ).fetchone()

    if not row:
        count = _token_count(conn)
        conn.close()
        return JSONResponse(
            status_code=404,
            content={
                "error": "Token not found",
                "detail": f"'{token}' is not tracked. Use CoinGecko token IDs (e.g. 'bitcoin', 'ethereum').",
                "available_tokens": count,
                "docs": "https://zarq.ai/docs",
            },
        )

    # Also fetch vitality score
    vit_row = conn.execute(
        "SELECT vitality_score, ecosystem_gravity, capital_commitment, "
        "coordination_efficiency, stress_resilience, organic_momentum, confidence "
        "FROM vitality_scores WHERE token_id = ?",
        (token,),
    ).fetchone()

    conn.close()

    risk_level = row["risk_level"] or "WATCH"
    trust_score = row["trust_score"] or row["rating_score"]
    ndd = row["ndd_current"]
    crash_prob = row["crash_prob_v3"]
    sw = row["structural_weakness"] or 0

    result = {
        "token": row["token_id"],
        "name": row["name"] or row["token_id"].replace("-", " ").title(),
        "symbol": (row["symbol"] or "").upper(),
        "verdict": _verdict(risk_level),
        "trust_score": round(float(trust_score), 2) if trust_score else None,
        "rating": row["rating_grade"],
        "distance_to_default": round(float(ndd), 2) if ndd else None,
        "structural_weakness": sw >= 2,
        "risk_level": risk_level,
        "crash_probability": round(float(crash_prob), 4) if crash_prob else None,
        "vitality_score": round(float(vit_row["vitality_score"]), 1) if vit_row and vit_row["vitality_score"] else None,
        "price_usd": row["price_usd"],
        "market_cap": row["market_cap"],
        "signal_date": signal_date,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    response.headers["Cache-Control"] = "public, max-age=300"
    return result


# ── Vitality Score API ──

def _vitality_grade(score):
    if score is None: return "NR"
    if score >= 85: return "S"
    if score >= 70: return "A"
    if score >= 55: return "B"
    if score >= 40: return "C"
    if score >= 25: return "D"
    return "F"


def _vitality_interpretation(score, grade):
    if grade == "S": return "Thriving ecosystem with exceptional coordination and resilience"
    if grade == "A": return "Strong ecosystem with robust infrastructure and capital commitment"
    if grade == "B": return "Developing ecosystem with solid fundamentals"
    if grade == "C": return "Emerging ecosystem, moderate infrastructure maturity"
    if grade == "D": return "Weak ecosystem with limited infrastructure and capital"
    return "Minimal ecosystem presence"


@router_vitality.get("/v1/vitality/{token}")
def get_vitality(token: str, response: Response):
    """Vitality Score for a single token — ecosystem health assessment."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM vitality_scores WHERE token_id = ?", (token,)
    ).fetchone()

    if not row:
        conn.close()
        return JSONResponse(status_code=404, content={
            "error": "Token not found",
            "detail": f"No Vitality Score for '{token}'. Use CoinGecko token IDs.",
        })

    conn.close()

    vs = row["vitality_score"]
    grade = _vitality_grade(vs)

    result = {
        "token": row["token_id"],
        "name": row["name"] or row["token_id"].replace("-", " ").title(),
        "symbol": (row["symbol"] or "").upper(),
        "vitality_score": round(float(vs), 1) if vs else None,
        "grade": grade,
        "dimensions": {
            "ecosystem_gravity": round(float(row["ecosystem_gravity"]), 1) if row["ecosystem_gravity"] else None,
            "capital_commitment": round(float(row["capital_commitment"]), 1) if row["capital_commitment"] else None,
            "coordination_efficiency": round(float(row["coordination_efficiency"]), 1) if row["coordination_efficiency"] else None,
            "stress_resilience": round(float(row["stress_resilience"]), 1) if row["stress_resilience"] else None,
            "organic_momentum": round(float(row["organic_momentum"]), 1) if row["organic_momentum"] else None,
        },
        "confidence": row["confidence"],
        "trust_score": round(float(row["trust_score"]), 2) if row["trust_score"] else None,
        "trust_rating": row["trust_rating"],
        "interpretation": _vitality_interpretation(vs, grade),
        "calculated_at": row["computed_at"],
    }

    response.headers["Cache-Control"] = "public, max-age=300"
    return result


@router_vitality.get("/v1/vitality/{token_a}/compare/{token_b}")
def compare_vitality(token_a: str, token_b: str, response: Response):
    """Side-by-side Vitality Score comparison."""
    conn = _get_db()
    rows = {}
    for tid in (token_a, token_b):
        r = conn.execute("SELECT * FROM vitality_scores WHERE token_id = ?", (tid,)).fetchone()
        if not r:
            conn.close()
            return JSONResponse(status_code=404, content={
                "error": f"Token '{tid}' not found in Vitality Scores"
            })
        rows[tid] = r
    conn.close()

    def _token_data(r):
        vs = r["vitality_score"]
        grade = _vitality_grade(vs)
        return {
            "token": r["token_id"],
            "name": r["name"] or r["token_id"].replace("-", " ").title(),
            "vitality_score": round(float(vs), 1) if vs else None,
            "grade": grade,
            "dimensions": {
                "ecosystem_gravity": round(float(r["ecosystem_gravity"]), 1) if r["ecosystem_gravity"] else None,
                "capital_commitment": round(float(r["capital_commitment"]), 1) if r["capital_commitment"] else None,
                "coordination_efficiency": round(float(r["coordination_efficiency"]), 1) if r["coordination_efficiency"] else None,
                "stress_resilience": round(float(r["stress_resilience"]), 1) if r["stress_resilience"] else None,
                "organic_momentum": round(float(r["organic_momentum"]), 1) if r["organic_momentum"] else None,
            },
            "confidence": r["confidence"],
            "trust_score": round(float(r["trust_score"]), 2) if r["trust_score"] else None,
        }

    a = _token_data(rows[token_a])
    b = _token_data(rows[token_b])

    # Determine which token is stronger per dimension
    advantages = {"a": [], "b": []}
    for dim in ["ecosystem_gravity", "capital_commitment", "coordination_efficiency",
                 "stress_resilience", "organic_momentum"]:
        va = a["dimensions"].get(dim)
        vb = b["dimensions"].get(dim)
        if va is not None and vb is not None:
            if va > vb:
                advantages["a"].append(dim)
            elif vb > va:
                advantages["b"].append(dim)

    result = {
        "token_a": a,
        "token_b": b,
        "winner": token_a if (a["vitality_score"] or 0) >= (b["vitality_score"] or 0) else token_b,
        "spread": round(abs((a["vitality_score"] or 0) - (b["vitality_score"] or 0)), 1),
        "advantages": {
            token_a: advantages["a"],
            token_b: advantages["b"],
        },
    }

    response.headers["Cache-Control"] = "public, max-age=300"
    return result
