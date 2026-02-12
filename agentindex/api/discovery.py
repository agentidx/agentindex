"""
AgentIndex Discovery API

The core product: agents query this API to find other agents.
Machine-first. No UI. Pure protocol.
"""

import time
import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text, or_, and_
from agentindex.db.models import Agent, DiscoveryLog, SystemStatus, get_session
from agentindex.api.keys import register_key, validate_key, ApiKey
from agentindex.api.a2a import get_agent_card, handle_a2a_request
import os
import uuid

# Semantic search (FAISS + sentence-transformers)
try:
    from agentindex.api.semantic import get_semantic_search
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False

logger = logging.getLogger("agentindex.api")

app = FastAPI(
    title="AgentIndex",
    description="Discovery service for AI agents. Machine-first API.",
    version="0.1.0",
    docs_url=None,     # No swagger UI — this is for machines
    redoc_url=None,
)

# Rate limiting state (in-memory, simple)
rate_limit_store: dict = {}
RATE_LIMIT_PER_HOUR = int(os.getenv("API_RATE_LIMIT_PER_HOUR", "100"))
MAX_RESULTS = int(os.getenv("API_RESULTS_PER_REQUEST", "10"))


# --- Models ---

class DiscoverRequest(BaseModel):
    """What an agent sends to find other agents."""
    need: str = Field(..., description="Natural language description of what you need")
    category: Optional[str] = Field(None, description="Filter by category")
    protocols: Optional[list[str]] = Field(None, description="Required protocols (mcp, a2a, rest)")
    min_quality: Optional[float] = Field(0.0, description="Minimum quality score 0.0-1.0")
    max_results: Optional[int] = Field(10, description="Max results (capped at 10)")

class DiscoverResponse(BaseModel):
    """What we return."""
    results: list[dict]
    total_matching: int
    index_size: int
    protocol: str = "agentindex/v1"

class AgentDetailResponse(BaseModel):
    """Detailed info about a single agent."""
    agent: dict

class StatsResponse(BaseModel):
    """System statistics."""
    total_agents: int
    active_agents: int
    categories: dict
    sources: dict
    protocols: dict
    last_crawl: Optional[str]


# --- Rate Limiting ---

def check_rate_limit(request: Request):
    """Simple IP-based rate limiting."""
    client_ip = request.client.host
    now = time.time()
    hour_ago = now - 3600

    # Clean old entries
    if client_ip in rate_limit_store:
        rate_limit_store[client_ip] = [
            t for t in rate_limit_store[client_ip] if t > hour_ago
        ]
    else:
        rate_limit_store[client_ip] = []

    # Check limit
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "limit": RATE_LIMIT_PER_HOUR,
                "retry_after_seconds": 3600,
            }
        )

    rate_limit_store[client_ip].append(now)


# --- Endpoints ---

@app.get("/v1/health")
def health():
    """Health check."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


class RegisterRequest(BaseModel):
    agent_name: Optional[str] = None
    agent_url: Optional[str] = None
    contact: Optional[str] = None

@app.post("/v1/register")
def register(req: RegisterRequest):
    """
    Register for a free API key. Self-service, no approval needed.
    Returns key once — store it securely.
    """
    result = register_key(
        agent_name=req.agent_name,
        agent_url=req.agent_url,
        contact=req.contact,
    )
    return result


@app.post("/v1/discover", response_model=DiscoverResponse)
def discover(req: DiscoverRequest, request: Request, _=Depends(check_rate_limit)):
    """
    Core discovery endpoint.
    An agent describes what it needs, we return matching agents.
    """
    start_time = time.time()
    session = get_session()

    # Cap max results
    limit = min(req.max_results or 10, MAX_RESULTS)

    # Build query
    query = select(Agent).where(
        Agent.is_active == True,
        Agent.crawl_status.in_(["parsed", "classified", "ranked"]),
        Agent.quality_score >= (req.min_quality or 0.0),
    )

    # Category filter
    if req.category:
        query = query.where(Agent.category == req.category)

    # Protocol filter
    if req.protocols:
        query = query.where(Agent.protocols.overlap(req.protocols))

    # --- Semantic search (primary) ---
    fts_results = []
    search_method = "fts"

    if SEMANTIC_AVAILABLE:
        try:
            sem = get_semantic_search()
            if sem.index is not None and sem.index_size > 0:
                # Get more candidates than needed, then filter
                sem_results = sem.search(req.need, top_k=limit * 5)
                if sem_results:
                    search_method = "semantic"
                    candidate_ids = [r["agent_id"] for r in sem_results]
                    sem_scores = {r["agent_id"]: r["score"] for r in sem_results}

                    # Fetch agents by IDs with filters applied
                    sem_query = select(Agent).where(
                        Agent.id.in_([uuid.UUID(aid) for aid in candidate_ids]),
                        Agent.is_active == True,
                        Agent.crawl_status.in_(["parsed", "classified", "ranked"]),
                        Agent.quality_score >= (req.min_quality or 0.0),
                    )
                    if req.category:
                        sem_query = sem_query.where(Agent.category == req.category)
                    if req.protocols:
                        sem_query = sem_query.where(Agent.protocols.overlap(req.protocols))

                    agents_by_id = {
                        str(a.id): a
                        for a in session.execute(sem_query).scalars().all()
                    }

                    # Sort by combined score: 0.7 * semantic + 0.3 * quality
                    scored = []
                    for aid in candidate_ids:
                        agent = agents_by_id.get(aid)
                        if agent:
                            combined = 0.7 * sem_scores[aid] + 0.3 * (agent.quality_score or 0.0)
                            scored.append((combined, agent))
                    scored.sort(key=lambda x: x[0], reverse=True)
                    fts_results = [agent for _, agent in scored[:limit]]
        except Exception as e:
            logger.error(f"Semantic search failed, falling back to FTS: {e}")

    # --- Full-text search (fallback) ---
    if not fts_results:
        search_method = "fts"
        query = query.where(
            text(
                "to_tsvector('english', coalesce(name, '') || ' ' || "
                "coalesce(description, '') || ' ' || "
                "coalesce(category, '')) @@ plainto_tsquery('english', :search)"
            ).bindparams(search=req.need)
        )
        fts_results = session.execute(
            query.order_by(Agent.quality_score.desc()).limit(limit)
        ).scalars().all()

        # Broader fallback
        if not fts_results:
            broader_query = select(Agent).where(
                Agent.is_active == True,
                Agent.crawl_status.in_(["parsed", "classified", "ranked"]),
                Agent.quality_score >= (req.min_quality or 0.0),
            )
            if req.category:
                broader_query = broader_query.where(Agent.category == req.category)
            if req.protocols:
                broader_query = broader_query.where(Agent.protocols.overlap(req.protocols))
            broader_query = broader_query.where(
                text("capabilities::text ILIKE :pattern").bindparams(
                    pattern=f"%{req.need.split()[0] if req.need.split() else req.need}%"
                )
            )
            fts_results = session.execute(
                broader_query.order_by(Agent.quality_score.desc()).limit(limit)
            ).scalars().all()

    # Count total matching
    total_matching = len(fts_results)

    # Get index size
    index_size = session.execute(
        select(func.count(Agent.id)).where(Agent.is_active == True)
    ).scalar() or 0

    # Build response
    results = [agent.to_discovery_response() for agent in fts_results]

    response_time = int((time.time() - start_time) * 1000)

    # Log discovery request (no identifying info)
    log_entry = DiscoveryLog(
        query={"need": req.need, "category": req.category, "protocols": req.protocols, "search_method": search_method},
        results_count=len(results),
        top_result_id=fts_results[0].id if fts_results else None,
        response_time_ms=response_time,
    )
    session.add(log_entry)
    session.commit()
    session.close()

    return DiscoverResponse(
        results=results,
        total_matching=total_matching,
        index_size=index_size,
    )


@app.get("/v1/agent/{agent_id}", response_model=AgentDetailResponse)
def get_agent(agent_id: str, request: Request, _=Depends(check_rate_limit)):
    """Get detailed information about a specific agent."""
    session = get_session()

    try:
        uid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID format")

    agent = session.execute(
        select(Agent).where(Agent.id == uid, Agent.is_active == True)
    ).scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    result = agent.to_detail_response()
    session.close()

    return AgentDetailResponse(agent=result)


@app.get("/v1/stats", response_model=StatsResponse)
def stats():
    """Public statistics about the index."""
    session = get_session()

    total = session.execute(
        select(func.count(Agent.id))
    ).scalar() or 0

    active = session.execute(
        select(func.count(Agent.id)).where(Agent.is_active == True)
    ).scalar() or 0

    # Category distribution
    cat_rows = session.execute(
        select(Agent.category, func.count(Agent.id))
        .where(Agent.is_active == True)
        .group_by(Agent.category)
    ).all()
    categories = {row[0] or "unknown": row[1] for row in cat_rows}

    # Source distribution
    src_rows = session.execute(
        select(Agent.source, func.count(Agent.id))
        .group_by(Agent.source)
    ).all()
    sources = {row[0]: row[1] for row in src_rows}

    # Protocol distribution
    protocol_counts = {}
    agents_with_protocols = session.execute(
        select(Agent.protocols).where(Agent.protocols != None)
    ).scalars().all()
    for protocols in agents_with_protocols:
        if protocols:
            for p in protocols:
                protocol_counts[p] = protocol_counts.get(p, 0) + 1

    session.close()

    return StatsResponse(
        total_agents=total,
        active_agents=active,
        categories=categories,
        sources=sources,
        protocols=protocol_counts,
        last_crawl=datetime.utcnow().isoformat(),
    )


# --- MCP-compatible endpoint ---

@app.post("/v1/mcp/discover")
def mcp_discover(request_body: dict, request: Request, _=Depends(check_rate_limit)):
    """
    MCP-compatible discovery endpoint.
    Accepts MCP tool call format and returns results.
    """
    # Extract need from various MCP formats
    need = (
        request_body.get("need") or
        request_body.get("query") or
        request_body.get("input", {}).get("need") or
        request_body.get("arguments", {}).get("need") or
        ""
    )

    if not need:
        raise HTTPException(status_code=400, detail="Missing 'need' parameter")

    # Delegate to main discover
    req = DiscoverRequest(need=need)
    return discover(req, request)


# --- A2A Protocol Endpoints ---

@app.get("/.well-known/agent-card.json")
@app.get("/.well-known/agent.json")
def agent_card():
    """A2A Agent Card — discovery endpoint for the A2A protocol."""
    return get_agent_card()


@app.post("/a2a")
async def a2a_endpoint(request: Request):
    """A2A JSON-RPC 2.0 endpoint for agent-to-agent communication."""
    return await handle_a2a_request(request)


@app.get("/v1/semantic/status")
def semantic_status():
    """Semantic search index status."""
    if SEMANTIC_AVAILABLE:
        sem = get_semantic_search()
        return sem.get_status()
    return {"status": "not_available"}


def start_api():
    """Start the API server."""
    import uvicorn
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_api()
