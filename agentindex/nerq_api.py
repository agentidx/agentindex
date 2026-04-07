"""
Nerq Product APIs — Sprint N0
==============================
Tasks 1-3: Benchmark, Search, Stats endpoints for Nerq.
All zero auth, generous rate limits.

Endpoints:
  GET /v1/agent/benchmark/{category}    — Top 20 agents by trust_score
  GET /v1/agent/benchmark/categories    — All categories with counts
  GET /v1/agent/search                  — Fulltext search with filters
  GET /v1/agent/stats                   — Ecosystem stats (cached 1h)

Usage in discovery.py:
    from agentindex.nerq_api import router_nerq
    app.include_router(router_nerq)
"""

import hashlib
import logging
import time as _time
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from agentindex.db.models import get_session

logger = logging.getLogger("nerq.api")

router_nerq = APIRouter(tags=["nerq"])

# ── Caches ──────────────────────────────────────────────────
_stats_cache = {"data": None, "ts": 0}
_STATS_TTL = 3600  # 1 hour

_categories_cache = {"data": None, "ts": 0}
_CATEGORIES_TTL = 3600

_benchmark_cache: dict = {}  # category -> (data, ts, total)
_BENCHMARK_TTL = 600  # 10 min

_search_cache: dict = {}  # hash -> (data, ts)
_SEARCH_TTL = 300  # 5 min
_SEARCH_CACHE_MAX = 200

# Common filter for actual agents (not HF models/datasets)
_ACTUAL_AGENTS = "agent_type IN ('agent', 'mcp_server', 'tool')"


# ══════════════════════════════════════════════════════════════
# TASK 1: Agent Benchmarking API
# ══════════════════════════════════════════════════════════════

@router_nerq.get("/v1/agent/benchmark/categories")
def benchmark_categories(response: Response):
    """All categories with agent counts and average trust scores."""
    now = _time.time()
    if _categories_cache["data"] and (now - _categories_cache["ts"]) < _CATEGORIES_TTL:
        response.headers["X-Cache"] = "HIT"
        return _categories_cache["data"]

    session = get_session()
    try:
        # Use category directly — skip expensive COALESCE with domains[1]
        rows = session.execute(text(f"""
            SELECT
                COALESCE(category, 'uncategorized') as cat,
                COUNT(*) as cnt,
                ROUND(AVG(trust_score_v2)::numeric, 1) as avg_trust
            FROM entity_lookup
            WHERE is_active = true AND {_ACTUAL_AGENTS}
            GROUP BY cat
            HAVING COUNT(*) >= 3
            ORDER BY cnt DESC
        """)).fetchall()

        result = [
            {"category": r[0], "count": r[1], "avg_trust_score": float(r[2]) if r[2] else None}
            for r in rows
        ]
        _categories_cache["data"] = result
        _categories_cache["ts"] = now
        response.headers["X-Cache"] = "MISS"
        response.headers["Cache-Control"] = "public, max-age=3600"
        return result
    except Exception as e:
        logger.error(f"benchmark_categories error: {e}")
        return JSONResponse(status_code=503, content={"error": "Database unavailable"})
    finally:
        session.close()


@router_nerq.get("/v1/agent/benchmark/{category}")
def benchmark_category(category: str, response: Response):
    """Top 20 agents in a category ranked by trust_score."""
    now = _time.time()
    cache_key = category.lower().strip()
    cached = _benchmark_cache.get(cache_key)
    if cached and (now - cached[1]) < _BENCHMARK_TTL:
        response.headers["X-Cache"] = "HIT"
        response.headers["X-Total-In-Category"] = str(cached[2])
        return cached[0]

    session = get_session()
    try:
        cat_filter = "LOWER(category) = :cat"

        # Top 20 — fast index scan, no window function
        rows = session.execute(text(f"""
            SELECT
                name,
                trust_score_v2 as trust_score,
                compliance_score,
                CASE
                    WHEN trust_score_v2 >= 60 THEN 'TRUSTED'
                    WHEN trust_score_v2 >= 35 THEN 'CAUTION'
                    ELSE 'UNTRUSTED'
                END as risk_level,
                EXTRACT(DAY FROM NOW() - first_indexed)::int as days_indexed,
                source as platform,
                source_url,
                stars
            FROM entity_lookup
            WHERE is_active = true AND {_ACTUAL_AGENTS}
              AND {cat_filter}
            ORDER BY trust_score_v2 DESC NULLS LAST
            LIMIT 20
        """), {"cat": cache_key}).fetchall()

        if not rows:
            return JSONResponse(status_code=404, content={
                "error": "Category not found",
                "hint": "Use GET /v1/agent/benchmark/categories for valid categories",
            })

        # Approximate total from categories cache if available
        total = 0
        if _categories_cache["data"]:
            for c in _categories_cache["data"]:
                if c["category"] == cache_key:
                    total = c["count"]
                    break
        if not total:
            # Fallback: count from DB (slower but only on first cold hit)
            total = session.execute(text(f"""
                SELECT COUNT(*) FROM entity_lookup
                WHERE is_active = true AND {_ACTUAL_AGENTS} AND {cat_filter}
            """), {"cat": cache_key}).scalar() or 0

        result = [
            {
                "agent_name": r[0],
                "trust_score": round(float(r[1]), 1) if r[1] else None,
                "compliance_score": round(float(r[2]), 1) if r[2] else None,
                "risk_level": r[3] if r[1] else "UNKNOWN",
                "days_indexed": r[4],
                "platform": r[5],
                "source": r[6],
                "github_stars": r[7],
            }
            for r in rows
        ]

        _benchmark_cache[cache_key] = (result, now, total)
        response.headers["X-Cache"] = "MISS"
        response.headers["X-Total-In-Category"] = str(total)
        response.headers["Cache-Control"] = "public, max-age=600"
        return result
    except Exception as e:
        logger.error(f"benchmark_category error: {e}")
        return JSONResponse(status_code=503, content={"error": "Database unavailable"})
    finally:
        session.close()


# ══════════════════════════════════════════════════════════════
# TASK 2: Agent Search API
# ══════════════════════════════════════════════════════════════

@router_nerq.get("/v1/agent/search")
def agent_search(
    response: Response,
    q: str = Query(None, description="Search query (fulltext on name)"),
    domain: str = Query(None, description="Filter by domain"),
    type: str = Query(None, description="Filter by agent_type: agent, mcp_server, tool"),
    min_trust: float = Query(0, description="Minimum trust score (0-100)"),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Fulltext search on agent name with filters and pagination."""
    if not q and not domain and not type:
        return JSONResponse(status_code=400, content={
            "error": "Provide at least one of: q, domain, type",
        })

    # Check search cache
    now = _time.time()
    cache_key = hashlib.md5(f"{q}:{domain}:{type}:{min_trust}:{limit}:{offset}".encode()).hexdigest()
    cached = _search_cache.get(cache_key)
    if cached and (now - cached[1]) < _SEARCH_TTL:
        response.headers["X-Cache"] = "HIT"
        return cached[0]

    session = get_session()
    try:
        conditions = [f"is_active = true AND {_ACTUAL_AGENTS}"]
        params: dict = {"lim": limit, "off": offset}

        if q:
            conditions.append(
                "to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, '')) "
                "@@ plainto_tsquery('english', :q)"
            )
            params["q"] = q

        if domain:
            conditions.append("LOWER(category) = :domain")
            params["domain"] = domain.lower()

        if type:
            conditions.append("agent_type = :atype")
            params["atype"] = type

        if min_trust > 0:
            conditions.append("trust_score_v2 >= :min_trust")
            params["min_trust"] = min_trust

        where = " AND ".join(conditions)

        # Fetch results (fast — uses index scan + LIMIT)
        rows = session.execute(text(f"""
            SELECT
                name, agent_type, source, source_url,
                trust_score_v2 as trust_score,
                category
            FROM entity_lookup
            WHERE {where}
            ORDER BY trust_score_v2 DESC NULLS LAST
            LIMIT :lim OFFSET :off
        """), params).fetchall()

        results = [
            {
                "name": r[0],
                "agent_type": r[1],
                "source": r[2],
                "source_url": r[3],
                "trust_score": round(float(r[4]), 1) if r[4] else None,
                "category": r[5],
            }
            for r in rows
        ]

        # Estimate total without expensive COUNT(*)
        if len(rows) < limit:
            total = offset + len(rows)
        else:
            # Use EXPLAIN estimate for total (instant, ~90% accurate)
            try:
                plan = session.execute(
                    text(f"EXPLAIN (FORMAT JSON) SELECT 1 FROM entity_lookup WHERE {where}"), params
                ).scalar()
                import json as _json
                total = int(_json.loads(plan)[0]["Plan"]["Plan Rows"])
            except Exception:
                total = offset + limit + 1  # indicate "more available"

        result = {
            "results": results,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

        # Cache search result
        if len(_search_cache) > _SEARCH_CACHE_MAX:
            # Evict oldest entries
            oldest = sorted(_search_cache.items(), key=lambda x: x[1][1])[:50]
            for k, _ in oldest:
                _search_cache.pop(k, None)
        _search_cache[cache_key] = (result, now)

        response.headers["X-Cache"] = "MISS"
        response.headers["Cache-Control"] = "public, max-age=300"
        return result
    except Exception as e:
        logger.error(f"agent_search error: {e}")
        return JSONResponse(status_code=503, content={"error": "Database unavailable"})
    finally:
        session.close()


# ══════════════════════════════════════════════════════════════
# TASK 3: Agent Stats API
# ══════════════════════════════════════════════════════════════

@router_nerq.get("/v1/agent/stats")
def agent_stats(response: Response):
    """Ecosystem stats: counts by type, category, framework, trust distribution."""
    now = _time.time()
    if _stats_cache["data"] and (now - _stats_cache["ts"]) < _STATS_TTL:
        response.headers["X-Cache"] = "HIT"
        return _stats_cache["data"]

    session = get_session()
    try:
        # Total AI assets (PG estimate — instant)
        total_assets = session.execute(
            text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'agents'")
        ).scalar() or 0
        total_assets = max(total_assets, 0)

        # Single-pass: type counts + trust distribution + avg trust for actual agents
        # This replaces 4 separate full-table scans with 1
        combined = session.execute(text("""
            SELECT
                SUM(CASE WHEN agent_type = 'agent' THEN 1 ELSE 0 END) as agents,
                SUM(CASE WHEN agent_type = 'tool' THEN 1 ELSE 0 END) as tools,
                SUM(CASE WHEN agent_type = 'mcp_server' THEN 1 ELSE 0 END) as mcp_servers,
                SUM(CASE WHEN agent_type = 'model' THEN 1 ELSE 0 END) as models,
                SUM(CASE WHEN agent_type = 'dataset' THEN 1 ELSE 0 END) as datasets,
                SUM(CASE WHEN agent_type = 'space' THEN 1 ELSE 0 END) as spaces,
                SUM(CASE WHEN agent_type IN ('agent','mcp_server','tool')
                          AND trust_score_v2 >= 60 THEN 1 ELSE 0 END) as trusted,
                SUM(CASE WHEN agent_type IN ('agent','mcp_server','tool')
                          AND trust_score_v2 >= 35 AND trust_score_v2 < 60 THEN 1 ELSE 0 END) as caution,
                SUM(CASE WHEN agent_type IN ('agent','mcp_server','tool')
                          AND trust_score_v2 < 35 AND trust_score_v2 IS NOT NULL THEN 1 ELSE 0 END) as untrusted,
                ROUND(AVG(CASE WHEN agent_type IN ('agent','mcp_server','tool')
                               AND trust_score_v2 IS NOT NULL
                          THEN trust_score_v2 END)::numeric, 1) as avg_trust
            FROM entity_lookup
            WHERE is_active = true
        """)).fetchone()

        # Category distribution (actual agents only)
        cat_rows = session.execute(text(f"""
            SELECT COALESCE(category, 'uncategorized') as cat, COUNT(*)
            FROM entity_lookup
            WHERE is_active = true AND {_ACTUAL_AGENTS}
            GROUP BY cat ORDER BY COUNT(*) DESC LIMIT 50
        """)).fetchall()
        categories = {r[0]: r[1] for r in cat_rows}

        # Framework distribution — entity_lookup has frameworks column
        fw_rows = session.execute(text(f"""
            SELECT fw, COUNT(*) as cnt
            FROM (SELECT unnest(frameworks) as fw FROM entity_lookup
                  WHERE frameworks IS NOT NULL AND is_active = true
                  AND {_ACTUAL_AGENTS}
                  LIMIT 50000) sub
            GROUP BY fw ORDER BY cnt DESC LIMIT 30
        """)).fetchall()
        frameworks = {r[0]: r[1] for r in fw_rows}

        # Language distribution — language not in entity_lookup; use agents with guards
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        lang_rows = session.execute(text(f"""
            SELECT COALESCE(language, 'unknown') as lang, COUNT(*)
            FROM agents
            WHERE is_active = true AND {_ACTUAL_AGENTS}
            GROUP BY lang ORDER BY COUNT(*) DESC LIMIT 20
        """)).fetchall()
        languages = {r[0]: r[1] for r in lang_rows}

        # New agents (24h / 7d) — TABLESAMPLE for speed
        cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        new_24h = session.execute(
            text("SELECT COUNT(*) FROM entity_lookup TABLESAMPLE SYSTEM(0.1) WHERE first_indexed > :d"),
            {"d": cutoff_24h}
        ).scalar() or 0
        new_24h = int(new_24h * 1000)

        new_7d = session.execute(
            text("SELECT COUNT(*) FROM entity_lookup TABLESAMPLE SYSTEM(1) WHERE first_indexed > :d"),
            {"d": cutoff_7d}
        ).scalar() or 0
        new_7d = int(new_7d * 100)

        result = {
            "total_assets": total_assets,
            "total_agents": combined[0] or 0,
            "total_tools": combined[1] or 0,
            "total_mcp_servers": combined[2] or 0,
            "total_models": combined[3] or 0,
            "total_datasets": combined[4] or 0,
            "total_spaces": combined[5] or 0,
            "categories": categories,
            "frameworks": frameworks,
            "languages": languages,
            "trust_distribution": {
                "TRUSTED": combined[6] or 0,
                "CAUTION": combined[7] or 0,
                "UNTRUSTED": combined[8] or 0,
            },
            "new_24h": new_24h,
            "new_7d": new_7d,
            "average_trust_score": float(combined[9]) if combined[9] else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        _stats_cache["data"] = result
        _stats_cache["ts"] = now
        response.headers["X-Cache"] = "MISS"
        response.headers["Cache-Control"] = "public, max-age=3600"
        return result
    except Exception as e:
        logger.error(f"agent_stats error: {e}")
        return JSONResponse(status_code=503, content={"error": "Database unavailable"})
    finally:
        session.close()
