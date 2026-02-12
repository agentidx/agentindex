"""
AgentIndex A2A Protocol Support

Implements Google's Agent2Agent (A2A) protocol v0.2+:
- Agent Card at /.well-known/agent-card.json
- JSON-RPC 2.0 endpoints for message/send
- Task lifecycle management
- SSE streaming support

AgentIndex acts as an A2A Server that other agents can discover and query.
Skills: discover_agents, search_by_category, get_agent_details
"""

import logging
import os
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("agentindex.a2a")

# =================================================================
# Agent Card — our A2A identity
# =================================================================

def get_agent_card(base_url: str = None) -> dict:
    """Generate our A2A Agent Card."""
    if not base_url:
        base_url = os.getenv("API_PUBLIC_ENDPOINT", "https://api.agentcrawl.dev")

    return {
        "name": "AgentIndex",
        "description": (
            "Discovery service for AI agents. Query AgentIndex to find agents "
            "by capability, category, or natural language description. "
            "Indexes 36,000+ agents from GitHub, npm, PyPI, HuggingFace, and MCP registries."
        ),
        "url": f"{base_url}/a2a",
        "version": "0.3.0",
        "documentationUrl": "https://github.com/agentidx/agentindex",
        "provider": {
            "organization": "AgentIndex",
            "url": "https://agentcrawl.dev"
        },
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "authentication": {
            "schemes": ["none"],
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["application/json", "text/plain"],
        "skills": [
            {
                "id": "discover_agents",
                "name": "Discover Agents",
                "description": (
                    "Find AI agents by natural language description. Uses semantic search "
                    "(FAISS + sentence-transformers) to match agents by meaning, not just keywords. "
                    "Returns agent name, description, capabilities, invocation details, and quality score."
                ),
                "tags": ["discovery", "search", "agents", "AI", "MCP", "semantic"],
                "examples": [
                    "Find me a code review agent",
                    "I need an agent for financial data analysis",
                    "Search for MCP servers that handle security scanning",
                    "What agents can help with document summarization?",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
            {
                "id": "search_by_category",
                "name": "Search by Category",
                "description": (
                    "Browse agents by category. Available categories include: coding, devops, "
                    "finance, infrastructure, communication, research, data, security, "
                    "agent framework, agent platform, and more."
                ),
                "tags": ["category", "browse", "filter"],
                "examples": [
                    "Show me all coding agents",
                    "List finance agents",
                    "What security agents are available?",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
            {
                "id": "get_agent_details",
                "name": "Get Agent Details",
                "description": "Get detailed information about a specific agent by its ID.",
                "tags": ["details", "lookup", "agent"],
                "examples": [
                    "Get details for agent 51606d0a-1664-47b3-bd6a-3469a91b1de3",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
            {
                "id": "index_stats",
                "name": "Index Statistics",
                "description": "Get current statistics about the AgentIndex: total agents, categories, sources, protocols.",
                "tags": ["stats", "status", "info"],
                "examples": [
                    "How many agents are indexed?",
                    "What are the index statistics?",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
        ],
    }


# =================================================================
# JSON-RPC 2.0 Handler
# =================================================================

# In-memory task store (lightweight, no external deps)
_tasks: dict = {}


def _make_jsonrpc_response(id: str, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _make_jsonrpc_error(id: str, code: int, message: str, data: dict = None) -> dict:
    error = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": id, "error": error}


def _extract_text_from_message(params: dict) -> str:
    """Extract plain text from A2A message params."""
    message = params.get("message", {})

    # Handle string message directly
    if isinstance(message, str):
        return message

    # Handle message object with parts
    parts = message.get("parts", [])
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            return part.get("text", "")
        elif isinstance(part, str):
            return part

    # Fallback: check for direct text field
    if "text" in message:
        return message["text"]

    # Fallback: check params directly
    if "text" in params:
        return params["text"]

    return ""


def _classify_intent(text: str) -> tuple[str, dict]:
    """Classify user intent into skill + parameters."""
    text_lower = text.lower().strip()

    # Stats intent
    if any(kw in text_lower for kw in ["stats", "statistics", "how many", "index size", "status"]):
        return "index_stats", {}

    # Agent detail by UUID
    import re
    uuid_match = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', text_lower)
    if uuid_match:
        return "get_agent_details", {"agent_id": uuid_match.group()}

    # Category search
    categories = [
        "coding", "devops", "finance", "infrastructure", "communication",
        "research", "data", "security", "agent framework", "agent platform",
        "content", "legal", "healthcare", "education", "marketing",
    ]
    for cat in categories:
        if cat in text_lower and any(kw in text_lower for kw in ["list", "show", "browse", "all", f"{cat} agents"]):
            return "search_by_category", {"category": cat}

    # Default: semantic discover
    return "discover_agents", {"need": text}


def _execute_skill(skill_id: str, params: dict) -> dict:
    """Execute a skill and return results."""
    from agentindex.db.models import Agent, get_session
    from sqlalchemy import select, func

    session = get_session()

    try:
        if skill_id == "index_stats":
            total = session.execute(
                select(func.count(Agent.id))
            ).scalar() or 0
            active = session.execute(
                select(func.count(Agent.id)).where(Agent.is_active == True)
            ).scalar() or 0
            cat_rows = session.execute(
                select(Agent.category, func.count(Agent.id))
                .where(Agent.is_active == True)
                .group_by(Agent.category)
                .order_by(func.count(Agent.id).desc())
                .limit(15)
            ).all()
            categories = {row[0] or "unknown": row[1] for row in cat_rows}
            return {
                "total_agents": total,
                "active_agents": active,
                "top_categories": categories,
                "sources": ["github", "npm", "pypi", "huggingface", "mcp"],
                "semantic_search": True,
                "a2a_support": True,
            }

        elif skill_id == "get_agent_details":
            agent_id = params.get("agent_id")
            try:
                uid = uuid.UUID(agent_id)
            except (ValueError, TypeError):
                return {"error": "Invalid agent ID format"}
            agent = session.execute(
                select(Agent).where(Agent.id == uid, Agent.is_active == True)
            ).scalar_one_or_none()
            if not agent:
                return {"error": "Agent not found"}
            return {"agent": agent.to_detail_response()}

        elif skill_id == "search_by_category":
            category = params.get("category", "")
            agents = session.execute(
                select(Agent).where(
                    Agent.is_active == True,
                    Agent.category == category,
                    Agent.crawl_status.in_(["parsed", "classified", "ranked"]),
                ).order_by(Agent.quality_score.desc()).limit(10)
            ).scalars().all()
            return {
                "category": category,
                "count": len(agents),
                "agents": [a.to_discovery_response() for a in agents],
            }

        elif skill_id == "discover_agents":
            need = params.get("need", "")
            # Use semantic search
            try:
                from agentindex.api.semantic import get_semantic_search
                sem = get_semantic_search()
                if sem.index is not None and sem.index_size > 0:
                    sem_results = sem.search(need, top_k=50)
                    if sem_results:
                        candidate_ids = [r["agent_id"] for r in sem_results]
                        sem_scores = {r["agent_id"]: r["score"] for r in sem_results}
                        agents = session.execute(
                            select(Agent).where(
                                Agent.id.in_([uuid.UUID(aid) for aid in candidate_ids]),
                                Agent.is_active == True,
                                Agent.crawl_status.in_(["parsed", "classified", "ranked"]),
                            )
                        ).scalars().all()
                        agents_by_id = {str(a.id): a for a in agents}
                        scored = []
                        for aid in candidate_ids:
                            agent = agents_by_id.get(aid)
                            if agent:
                                combined = 0.7 * sem_scores[aid] + 0.3 * (agent.quality_score or 0.0)
                                scored.append((combined, agent))
                        scored.sort(key=lambda x: x[0], reverse=True)
                        results = [a.to_discovery_response() for _, a in scored[:10]]
                        return {
                            "query": need,
                            "search_method": "semantic",
                            "count": len(results),
                            "agents": results,
                        }
            except Exception as e:
                logger.error(f"Semantic search in A2A failed: {e}")

            # Fallback: FTS
            from sqlalchemy.sql import text as sql_text
            agents = session.execute(
                select(Agent).where(
                    Agent.is_active == True,
                    Agent.crawl_status.in_(["parsed", "classified", "ranked"]),
                    sql_text(
                        "to_tsvector('english', coalesce(name, '') || ' ' || "
                        "coalesce(description, '') || ' ' || "
                        "coalesce(category, '')) @@ plainto_tsquery('english', :search)"
                    ).bindparams(search=need)
                ).order_by(Agent.quality_score.desc()).limit(10)
            ).scalars().all()
            return {
                "query": need,
                "search_method": "fts",
                "count": len(agents),
                "agents": [a.to_discovery_response() for a in agents],
            }

        return {"error": f"Unknown skill: {skill_id}"}

    finally:
        session.close()


async def handle_a2a_request(request: Request) -> JSONResponse:
    """
    Handle A2A JSON-RPC 2.0 requests.

    Supported methods:
    - message/send: Send a message, get immediate response
    - tasks/get: Get task status by ID
    - tasks/cancel: Cancel a task
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            _make_jsonrpc_error(None, -32700, "Parse error"),
            status_code=200
        )

    req_id = body.get("id", str(uuid.uuid4()))
    method = body.get("method", "")
    params = body.get("params", {})

    logger.info(f"A2A request: method={method}, id={req_id}")

    if method == "message/send":
        return await _handle_message_send(req_id, params)
    elif method == "tasks/get":
        return _handle_tasks_get(req_id, params)
    elif method == "tasks/cancel":
        return _handle_tasks_cancel(req_id, params)
    else:
        return JSONResponse(
            _make_jsonrpc_error(req_id, -32601, f"Method not found: {method}"),
            status_code=200
        )


async def _handle_message_send(req_id: str, params: dict) -> JSONResponse:
    """Handle message/send — the core A2A interaction."""
    start_time = time.time()

    # Extract text from message
    text = _extract_text_from_message(params)
    if not text:
        return JSONResponse(
            _make_jsonrpc_error(req_id, -32602, "No text content in message"),
            status_code=200
        )

    # Classify intent
    skill_id, skill_params = _classify_intent(text)
    logger.info(f"A2A intent: skill={skill_id}, text='{text[:100]}'")

    # Execute skill
    result = _execute_skill(skill_id, skill_params)

    response_time = int((time.time() - start_time) * 1000)

    # Build A2A response with task + artifact
    task_id = str(uuid.uuid4())
    context_id = params.get("contextId", str(uuid.uuid4()))
    message_id = str(uuid.uuid4())

    # Build response parts
    parts = []
    if "error" in result:
        parts.append({"type": "text", "text": result["error"]})
    else:
        # Text summary
        if skill_id == "discover_agents":
            count = result.get("count", 0)
            query = result.get("query", "")
            method = result.get("search_method", "unknown")
            summary = f"Found {count} agents matching '{query}' (via {method} search)."
            if count > 0:
                top = result["agents"][0]
                summary += f" Top result: {top['name']} — {top.get('description', '')[:100]}"
            parts.append({"type": "text", "text": summary})
        elif skill_id == "index_stats":
            s = result
            parts.append({"type": "text", "text": (
                f"AgentIndex has {s['total_agents']} total agents ({s['active_agents']} active). "
                f"Sources: {', '.join(s['sources'])}. Semantic search: enabled. A2A: enabled."
            )})
        elif skill_id == "search_by_category":
            parts.append({"type": "text", "text": (
                f"Found {result['count']} agents in category '{result['category']}'."
            )})
        elif skill_id == "get_agent_details":
            agent = result.get("agent", {})
            parts.append({"type": "text", "text": (
                f"Agent: {agent.get('name', 'unknown')} — {agent.get('description', '')[:200]}"
            )})

        # JSON data artifact
        parts.append({"type": "data", "data": result})

    # Build task object
    task = {
        "id": task_id,
        "contextId": context_id,
        "status": {"state": "completed"},
        "artifacts": [
            {
                "artifactId": str(uuid.uuid4()),
                "parts": parts,
            }
        ],
        "metadata": {
            "responseTimeMs": response_time,
            "skill": skill_id,
        }
    }

    # Store task
    _tasks[task_id] = task

    # Log
    from agentindex.db.models import DiscoveryLog, get_session
    try:
        session = get_session()
        log_entry = DiscoveryLog(
            query={"a2a": True, "method": "message/send", "skill": skill_id, "text": text[:500]},
            results_count=result.get("count", 0) if isinstance(result, dict) else 0,
            response_time_ms=response_time,
        )
        session.add(log_entry)
        session.commit()
        session.close()
    except Exception:
        pass

    return JSONResponse(
        _make_jsonrpc_response(req_id, task),
        status_code=200
    )


def _handle_tasks_get(req_id: str, params: dict) -> JSONResponse:
    """Handle tasks/get — retrieve task by ID."""
    task_id = params.get("id", "")
    task = _tasks.get(task_id)
    if not task:
        return JSONResponse(
            _make_jsonrpc_error(req_id, -32001, "Task not found", {"taskId": task_id}),
            status_code=200
        )
    return JSONResponse(
        _make_jsonrpc_response(req_id, task),
        status_code=200
    )


def _handle_tasks_cancel(req_id: str, params: dict) -> JSONResponse:
    """Handle tasks/cancel — cancel a task (all our tasks complete immediately)."""
    task_id = params.get("id", "")
    task = _tasks.get(task_id)
    if not task:
        return JSONResponse(
            _make_jsonrpc_error(req_id, -32001, "Task not found", {"taskId": task_id}),
            status_code=200
        )
    task["status"]["state"] = "canceled"
    return JSONResponse(
        _make_jsonrpc_response(req_id, task),
        status_code=200
    )
