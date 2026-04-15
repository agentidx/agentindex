"""
Nerq Scout — Agent reputation, reviews, and interaction ledger.
Routes:
  POST /v1/agent/review
  GET  /v1/agent/reputation/{name}
  GET  /v1/agent/ledger/{name}
"""

import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from agentindex.db.models import get_session, get_engine, get_write_session, get_write_engine

router_scout = APIRouter(tags=["scout"])

# ── Create tables at module load ──────────────────────────────────────

def _init_scout_tables():
    engine = get_write_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_reviews (
                id SERIAL PRIMARY KEY,
                reviewer TEXT NOT NULL,
                target TEXT NOT NULL,
                target_agent_id UUID,
                outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure', 'partial')),
                latency_ms INTEGER,
                notes TEXT,
                reviewer_ip TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_reviews_target
            ON agent_reviews(target)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_reviews_created
            ON agent_reviews(created_at)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_reviews_ip
            ON agent_reviews(reviewer_ip, created_at)
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS nerq_scout_log (
                id SERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                agent_name TEXT,
                details JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_scout_log_agent
            ON nerq_scout_log(agent_name)
        """))
        conn.commit()

try:
    _init_scout_tables()
except Exception:
    pass  # Tables will be created on first use if DB isn't ready yet


# ── Shared lookup ─────────────────────────────────────────────────────

def _lookup_best(name: str, session) -> dict | None:
    """Find agent by name using UNION ALL with trgm-compatible LIKE."""
    if not name:
        return None
    row = session.execute(text("""
        SELECT id, name,
               COALESCE(trust_score_v2, trust_score) AS trust_score,
               trust_grade, category, first_indexed, is_verified
        FROM (
            SELECT id, name, trust_score, trust_score_v2, trust_grade, category, first_indexed, is_verified, 1 AS _r
            FROM entity_lookup WHERE name_lower = lower(:name) AND is_active = true
          UNION ALL
            SELECT id, name, trust_score, trust_score_v2, trust_grade, category, first_indexed, is_verified, 2 AS _r
            FROM entity_lookup WHERE name_lower LIKE lower(:suffix) AND is_active = true
          UNION ALL
            SELECT id, name, trust_score, trust_score_v2, trust_grade, category, first_indexed, is_verified, 3 AS _r
            FROM entity_lookup WHERE name_lower LIKE lower(:pattern) AND is_active = true
        ) sub
        ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
        LIMIT 1
    """), {"name": name, "suffix": f"%/{name}", "pattern": f"%{name}%"}).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "name": row[1],
        "trust_score": round(float(row[2]), 1) if row[2] else None,
        "grade": row[3],
        "category": row[4],
        "first_indexed": row[5],
        "verified": bool(row[6]) or (float(row[2]) >= 70 if row[2] else False),
    }


def _calc_review_bonus(session, target_name: str) -> tuple[float, int, int, int]:
    """Calculate review bonus and stats for a target.
    Returns (bonus, total, successes, failures).
    """
    row = session.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE outcome = 'success') AS successes,
            COUNT(*) FILTER (WHERE outcome = 'failure') AS failures
        FROM agent_reviews
        WHERE lower(target) = lower(:target)
    """), {"target": target_name}).fetchone()
    total = row[0] or 0
    successes = row[1] or 0
    failures = row[2] or 0
    bonus = successes * 0.1 - failures * 0.5
    bonus = max(-5.0, min(5.0, bonus))
    return round(bonus, 2), total, successes, failures


# ── Endpoint 1: POST /v1/agent/review ─────────────────────────────────

@router_scout.post("/v1/agent/review")
async def post_review(request: Request):
    """Submit a peer review for an agent."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})

    reviewer = (body.get("reviewer") or "").strip()
    target = (body.get("target") or "").strip()
    outcome = (body.get("outcome") or "").strip()
    latency_ms = body.get("latency_ms")
    notes = body.get("notes")

    if not reviewer or not target:
        return JSONResponse(status_code=400, content={
            "error": "Missing required fields: reviewer, target"
        })
    if outcome not in ("success", "failure", "partial"):
        return JSONResponse(status_code=400, content={
            "error": "outcome must be one of: success, failure, partial"
        })

    client_ip = request.client.host if request.client else "unknown"

    session = get_write_session()
    try:
        # Rate limit: 100 reviews per IP per 24h
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        rate_row = session.execute(text("""
            SELECT COUNT(*) FROM agent_reviews
            WHERE reviewer_ip = :ip AND created_at >= :cutoff
        """), {"ip": client_ip, "cutoff": cutoff}).fetchone()
        if rate_row and rate_row[0] >= 100:
            return JSONResponse(status_code=429, content={
                "error": "Rate limit exceeded",
                "detail": "Maximum 100 reviews per 24 hours per IP.",
            })

        # Look up target agent
        agent = _lookup_best(target, session)
        target_trust_before = agent["trust_score"] if agent else None
        target_agent_id = agent["id"] if agent else None
        resolved_name = agent["name"] if agent else target

        # Insert review
        session.execute(text("""
            INSERT INTO agent_reviews
                (reviewer, target, target_agent_id, outcome, latency_ms, notes, reviewer_ip)
            VALUES
                (:reviewer, :target, :agent_id, :outcome, :latency_ms, :notes, :ip)
        """), {
            "reviewer": reviewer,
            "target": resolved_name,
            "agent_id": target_agent_id,
            "outcome": outcome,
            "latency_ms": latency_ms,
            "notes": notes,
            "ip": client_ip,
        })

        # Calculate review bonus after insert
        bonus, total, successes, failures = _calc_review_bonus(session, resolved_name)
        success_rate = round(successes / total, 3) if total > 0 else 0.0

        # Log to scout log
        session.execute(text("""
            INSERT INTO nerq_scout_log (event_type, agent_name, details)
            VALUES ('review', :name, :details)
        """), {
            "name": resolved_name,
            "details": json.dumps({
                "reviewer": reviewer,
                "outcome": outcome,
                "latency_ms": latency_ms,
                "review_bonus": bonus,
                "total_reviews": total,
            }),
        })

        session.commit()

        return {
            "recorded": True,
            "target": resolved_name,
            "target_trust_before": target_trust_before,
            "review_bonus": bonus,
            "total_reviews": total,
            "success_rate": success_rate,
        }
    except Exception as e:
        session.rollback()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        session.close()


# ── Endpoint 2: GET /v1/agent/reputation/{name} ──────────────────────

@router_scout.get("/v1/agent/reputation/{name:path}")
def get_reputation(name: str):
    """Get agent reputation: static trust + review bonus + rank."""
    session = get_write_session()
    try:
        agent = _lookup_best(name, session)
        if not agent:
            return JSONResponse(status_code=404, content={
                "error": "Agent not found",
                "detail": f"No active agent matching '{name}'.",
            })

        static_trust = agent["trust_score"]
        bonus, total, successes, failures = _calc_review_bonus(session, agent["name"])
        success_rate = round(successes / total, 3) if total > 0 else 0.0

        effective_trust = round(static_trust + bonus, 1) if static_trust is not None else None

        # Days active
        first_indexed = agent.get("first_indexed")
        days_active = None
        if first_indexed:
            try:
                fi = datetime.fromisoformat(str(first_indexed))
                days_active = max(1, (datetime.now(timezone.utc) - fi.replace(tzinfo=timezone.utc)).days)
            except Exception:
                pass

        # Rank in category
        rank_in_category = None
        category = agent.get("category")
        if category and static_trust is not None:
            rank_row = session.execute(text("""
                SELECT COUNT(*) FROM entity_lookup
                WHERE category = :cat
                  AND COALESCE(trust_score_v2, trust_score) > :score
                  AND is_active = true
            """), {"cat": category, "score": static_trust}).fetchone()
            rank_in_category = (rank_row[0] + 1) if rank_row else None

        return {
            "name": agent["name"],
            "trust_score": effective_trust,
            "static_trust": static_trust,
            "review_bonus": bonus,
            "total_reviews": total,
            "success_rate": success_rate,
            "days_active": days_active,
            "verified": effective_trust is not None and effective_trust >= 70,
            "rank_in_category": rank_in_category,
            "category": category,
            "badge_url": f"https://nerq.ai/badge/{agent['name']}",
        }
    finally:
        session.close()


# ── Endpoint 3: GET /v1/agent/ledger/{name} ──────────────────────────

@router_scout.get("/v1/agent/ledger/{name:path}")
def get_ledger(name: str, days: int = Query(30, ge=1, le=365)):
    """Agent interaction ledger: reviews received, given, and recent activity."""
    session = get_write_session()
    try:
        agent = _lookup_best(name, session)
        if not agent:
            return JSONResponse(status_code=404, content={
                "error": "Agent not found",
                "detail": f"No active agent matching '{name}'.",
            })

        resolved = agent["name"]
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Reviews received
        recv_row = session.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE outcome = 'success') AS successes,
                COUNT(*) FILTER (WHERE outcome = 'failure') AS failures
            FROM agent_reviews
            WHERE lower(target) = lower(:name) AND created_at >= :cutoff
        """), {"name": resolved, "cutoff": cutoff}).fetchone()
        reviews_received = recv_row[0] or 0
        successes = recv_row[1] or 0
        failures = recv_row[2] or 0

        # Reviews given
        given_row = session.execute(text("""
            SELECT COUNT(*) FROM agent_reviews
            WHERE lower(reviewer) = lower(:name) AND created_at >= :cutoff
        """), {"name": resolved, "cutoff": cutoff}).fetchone()
        reviews_given = given_row[0] or 0

        success_rate = round(successes / reviews_received, 3) if reviews_received > 0 else 0.0
        failure_rate = round(failures / reviews_received, 3) if reviews_received > 0 else 0.0

        # Trust trend (static for now — no historical trust snapshots)
        trust_trend = "stable"

        # Recent interactions: last 10 reviews received
        recent_rows = session.execute(text("""
            SELECT reviewer, outcome, latency_ms, created_at
            FROM agent_reviews
            WHERE lower(target) = lower(:name)
            ORDER BY created_at DESC
            LIMIT 10
        """), {"name": resolved}).fetchall()

        recent_interactions = [
            {
                "reviewer": r[0],
                "outcome": r[1],
                "latency_ms": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
            }
            for r in recent_rows
        ]

        return {
            "name": resolved,
            "period_days": days,
            "reviews_received": reviews_received,
            "reviews_given": reviews_given,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "trust_score": agent["trust_score"],
            "trust_trend": trust_trend,
            "recent_interactions": recent_interactions,
        }
    finally:
        session.close()


# ── Scout Status + Findings (for MCP tools + dashboard) ──────────────

@router_scout.get("/v1/scout/status")
def scout_status():
    """Scout status: agents evaluated, featured, claimed."""
    session = get_write_session()
    try:
        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)

        evaluated_24h = session.execute(text("""
            SELECT COUNT(*) FROM nerq_scout_log
            WHERE event_type = 'scout_evaluate' AND created_at >= :cutoff
        """), {"cutoff": day_ago}).scalar() or 0

        evaluated_total = session.execute(text("""
            SELECT COUNT(*) FROM nerq_scout_log
            WHERE event_type = 'scout_evaluate'
        """)).scalar() or 0

        featured_7d = session.execute(text("""
            SELECT COUNT(DISTINCT agent_name) FROM nerq_scout_log
            WHERE event_type = 'scout_evaluate' AND created_at >= :cutoff
        """), {"cutoff": week_ago}).scalar() or 0

        claimed = session.execute(text("""
            SELECT COUNT(*) FROM nerq_scout_log
            WHERE event_type = 'claim_submit'
        """)).scalar() or 0

        reviews_total = session.execute(text("""
            SELECT COUNT(*) FROM agent_reviews
        """)).scalar() or 0

        return {
            "scout_status": "active",
            "evaluated_24h": evaluated_24h,
            "evaluated_total": evaluated_total,
            "featured_7d": featured_7d,
            "claimed": claimed,
            "reviews_total": reviews_total,
            "updated_at": now.isoformat(),
        }
    finally:
        session.close()


@router_scout.get("/v1/scout/findings")
def scout_findings(limit: int = Query(10, ge=1, le=50)):
    """Latest top agents discovered by Scout."""
    session = get_write_session()
    try:
        rows = session.execute(text("""
            SELECT agent_name, details, created_at
            FROM nerq_scout_log
            WHERE event_type = 'scout_evaluate'
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()

        findings = []
        for r in rows:
            details = r[1] if isinstance(r[1], dict) else json.loads(r[1]) if r[1] else {}
            findings.append({
                "name": r[0],
                "trust_score": details.get("trust_score"),
                "grade": details.get("grade"),
                "category": details.get("category"),
                "source_url": details.get("source_url"),
                "discovered_at": r[2].isoformat() if r[2] else None,
            })

        return {"findings": findings, "total": len(findings)}
    finally:
        session.close()
