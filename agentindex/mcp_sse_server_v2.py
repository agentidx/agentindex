"""
Nerq MCP Server v2 — SSE Transport
AI Agent Discovery & Compliance as a Service

5M+ AI assets | 52 jurisdictions | Security + Compliance scoring

SSE endpoint: https://mcp.nerq.ai/sse
"""

import json
import os
import logging
import asyncio
import uuid

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
import uvicorn

logger = logging.getLogger("nerq.mcp.sse")

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"

sessions: dict[str, asyncio.Queue] = {}

# ============================================================
# DATABASE ACCESS
# ============================================================

def _get_db():
    import psycopg2
    DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')
    return psycopg2.connect(DB_URL)

def _query(sql, params=None, fetchone=False):
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    cols = [d[0] for d in cur.description]
    if fetchone:
        row = cur.fetchone()
        conn.close()
        return dict(zip(cols, row)) if row else None
    rows = cur.fetchall()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

# ============================================================
# TOOL DEFINITIONS (v2 — optimized for AI agents)
# ============================================================

TOOLS = [
    {
        "name": "search_agents",
        "description": (
            "Search 5 million+ AI assets including agents, tools, MCP servers, models, datasets, "
            "and packages. Accepts natural language queries like 'database MCP server' or specific "
            "names like 'LangChain'. Returns ranked results with trust scores, compliance data, "
            "and source info. Use when user asks 'find a tool for X', 'what tools do Y?', "
            "'what MCP server does Z?', 'search for X', or needs to discover AI assets for a "
            "specific task. Use recommend_agent instead if the user wants a specific recommendation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query — agent name, capability, or natural language need"},
                "type": {"type": "string", "description": "Filter by agent type", "enum": ["mcp_server", "huggingface_model", "npm_package", "pypi_package", "github_repo"]},
                "category": {"type": "string", "description": "Filter by category", "enum": ["coding", "research", "content", "legal", "data", "finance", "marketing", "design", "devops", "security", "education", "health", "communication", "productivity", "infrastructure"]},
                "limit": {"type": "integer", "description": "Max results (default 10, max 50)", "default": 10}
            },
            "required": ["query"]
        }
    },
    {
        "name": "recommend_agent",
        "description": (
            "Recommend the BEST AI agent or MCP server for a specific need, filtered by safety and "
            "compliance. Returns ranked results with ready-to-use install instructions for Claude Desktop, "
            "Cursor, and VS Code. Use when user asks 'what is the best MCP server for X?', "
            "'recommend a safe agent for Y', 'suggest a tool for Z', or 'which agent should I use for W?'. "
            "Prefer this over search_agents when the user wants a curated, safety-filtered recommendation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "need": {"type": "string", "description": "What the user needs — e.g. 'database access for postgresql'"},
                "type": {"type": "string", "description": "Preferred type", "enum": ["mcp_server", "huggingface_model", "npm_package", "pypi_package", "github_repo"]},
                "safe_only": {"type": "boolean", "description": "Only return agents with minimal/limited risk (default true)", "default": True},
                "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5}
            },
            "required": ["need"]
        }
    },
    {
        "name": "check_compliance",
        "description": (
            "Check if an AI tool, MCP server, npm package, PyPI package, HuggingFace model, or Docker "
            "container is safe, compliant, or trustworthy. Returns trust score, risk assessment, and "
            "compliance data across 52 global jurisdictions including EU AI Act, Colorado AI Act, "
            "California SB53, and UK AI regulation. Use when user asks 'is X safe?', 'is X trustworthy?', "
            "'is X EU compliant?', 'can I use X in production?', 'should I install X?', or needs to "
            "evaluate any AI asset before installing or recommending it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Agent name or search term"},
                "jurisdictions": {"type": "array", "items": {"type": "string"}, "description": "Specific jurisdictions to check (e.g. ['eu_ai_act']). If omitted, returns all 52."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "compare_agents",
        "description": (
            "Compare two or more AI tools side-by-side on trust score, security, compliance, "
            "popularity, and maintenance. Returns scores for each and a verdict on the winner. "
            "Use when user asks 'X vs Y', 'which is better X or Y?', 'compare X and Y', "
            "'compare X vs Y vs Z', or needs to choose between multiple AI assets."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agents": {"type": "array", "items": {"type": "string"}, "description": "List of agent names to compare (2-5)", "minItems": 2, "maxItems": 5}
            },
            "required": ["agents"]
        }
    },
    {
        "name": "nerq_stats",
        "description": "Get overview statistics about Nerq's database: total AI assets indexed (5M+), jurisdictions covered (52), risk distribution, and source breakdown. Use when user asks 'how many AI agents exist?', 'how big is the Nerq database?', 'what does Nerq index?', or wants ecosystem-level stats for reports or analysis.",
        "inputSchema": {"type": "object", "properties": {}}
    }
]

SERVER_INFO = {
    "name": "nerq",
    "version": "2.0.0",
    "description": "Nerq — The AI Asset Search Engine. 5M+ AI assets indexed & trust scored across 52 global jurisdictions."
}

# ============================================================
# TOOL IMPLEMENTATIONS
# ============================================================

def _search_agents(args):
    query = args.get("query", "")
    agent_type = args.get("type")
    category = args.get("category")
    limit = min(args.get("limit", 10), 50)

    conditions = ["(name ILIKE %s OR description ILIKE %s)"]
    params = [f"%{query}%", f"%{query}%"]

    if agent_type:
        conditions.append("agent_type = %s")
        params.append(agent_type)
    if category:
        conditions.append("category = %s")
        params.append(category)

    where = " AND ".join(conditions)
    params.append(limit)

    agents = _query(f"""
        SELECT id, name, description, agent_type, risk_class, domains,
               compliance_score, source, source_url, stars, downloads,
               trust_score_v2, trust_grade, trust_risk_level
        FROM agents
        WHERE {where} AND is_active = true
        ORDER BY trust_score_v2 DESC NULLS LAST, stars DESC NULLS LAST
        LIMIT %s
    """, params)

    return {
        "total_results": len(agents),
        "database_size": "5M+ AI assets",
        "agents": [{
            "name": a['name'],
            "type": a['agent_type'],
            "description": (a['description'] or '')[:200],
            "trust_score": a.get('trust_score_v2'),
            "trust_grade": a.get('trust_grade'),
            "compliance_score": a['compliance_score'],
            "risk_class": a['risk_class'],
            "stars": a['stars'],
            "source": a['source'],
            "url": f"https://nerq.ai/agent/{a['id']}",
            "source_url": a['source_url']
        } for a in agents]
    }


def _recommend_agent(args):
    need = args.get("need", "")
    agent_type = args.get("type")
    safe_only = args.get("safe_only", True)
    limit = min(args.get("limit", 5), 20)

    conditions = ["(name ILIKE %s OR description ILIKE %s)"]
    params = [f"%{need}%", f"%{need}%"]

    if agent_type:
        conditions.append("agent_type = %s")
        params.append(agent_type)
    if safe_only:
        conditions.append("risk_class IN ('minimal', 'limited')")

    where = " AND ".join(conditions)
    params.append(limit)

    agents = _query(f"""
        SELECT id, name, description, agent_type, risk_class, domains,
               compliance_score, source, source_url, stars, downloads,
               trust_score_v2, trust_grade
        FROM agents
        WHERE {where} AND is_active = true
        ORDER BY trust_score_v2 DESC NULLS LAST, stars DESC NULLS LAST
        LIMIT %s
    """, params)

    if not agents:
        return {
            "recommendation": f"No safe agents found for '{need}'. Try broader search terms.",
            "suggestions": ["Try search_agents with safe_only=false", "Try different keywords"],
            "agents": []
        }

    top = agents[0]
    total_found = len(agents)
    
    trust_text = f"Trust Score {top.get('trust_grade', '?')} ({top.get('trust_score_v2', '?')}/100)" if top.get('trust_score_v2') else f"compliance score {top['compliance_score']}/100"
    return {
        "recommendation": f"{top['name']} is the highest-rated option for '{need}' with {trust_text} and {top['stars'] or 0} stars. Classified as {top['risk_class']} risk across 52 jurisdictions.",
        "total_found": total_found,
        "agents": [{
            "name": a['name'],
            "type": a['agent_type'],
            "description": (a['description'] or '')[:200],
            "compliance_score": a['compliance_score'],
            "risk_class": a['risk_class'],
            "stars": a['stars'],
            "source": a['source'],
            "url": f"https://nerq.ai/agent/{a['id']}",
            "source_url": a['source_url']
        } for a in agents]
    }


def _check_compliance(args):
    query = args.get("query", "")
    jurisdictions = args.get("jurisdictions")

    agent = _query(
        """SELECT id, name, description, agent_type, risk_class, domains,
                  compliance_score, eu_risk_class
           FROM agents
           WHERE id::text = %s OR name ILIKE %s OR name ILIKE %s
           LIMIT 1""",
        (query, query, f"%{query}%"),
        fetchone=True
    )

    if not agent:
        return {"error": f"Agent not found: {query}", "suggestion": "Try search_agents to find the correct name"}

    j_sql = """
        SELECT ajs.jurisdiction_id, ajs.status, ajs.risk_level,
               ajs.triggered_criteria, ajs.compliance_notes
        FROM agent_jurisdiction_status ajs
        WHERE ajs.agent_id = %s
    """
    j_params = [agent['id']]

    if jurisdictions:
        j_sql += " AND ajs.jurisdiction_id = ANY(%s)"
        j_params.append(jurisdictions)

    j_sql += " ORDER BY ajs.risk_level DESC"
    statuses = _query(j_sql, j_params)

    high = sum(1 for j in statuses if j['risk_level'] in ('high', 'unacceptable'))
    limited = sum(1 for j in statuses if j['risk_level'] == 'limited')
    minimal = sum(1 for j in statuses if j['risk_level'] == 'minimal')

    summary_text = f"{agent['name']} has a compliance score of {agent['compliance_score']}/100 across {len(statuses)} jurisdictions. "
    if high > 0:
        summary_text += f"Flagged as high/unacceptable risk in {high} jurisdictions. "
    else:
        summary_text += f"No high-risk flags. "
    summary_text += f"Classified as {agent['risk_class']} risk overall."

    return {
        "summary": summary_text,
        "agent": {
            "name": agent['name'],
            "type": agent['agent_type'],
            "compliance_score": agent['compliance_score'],
            "risk_class": agent['risk_class'],
            "url": f"https://nerq.ai/agent/{agent['id']}"
        },
        "risk_breakdown": {"high": high, "limited": limited, "minimal": minimal},
        "jurisdictions": [{
            "id": j['jurisdiction_id'],
            "risk_level": j['risk_level'],
            "status": j['status'],
            "notes": j['compliance_notes']
        } for j in statuses[:20]]  # Limit to avoid huge responses
    }


def _compare_agents(args):
    agent_names = args.get("agents", [])
    results = []

    for name in agent_names[:5]:
        agent = _query(
            """SELECT id, name, agent_type, risk_class, compliance_score,
                      stars, downloads, source
               FROM agents
               WHERE name ILIKE %s OR name ILIKE %s
               LIMIT 1""",
            (name, f"%{name}%"),
            fetchone=True
        )
        if agent:
            results.append({
                "name": agent['name'],
                "type": agent['agent_type'],
                "compliance_score": agent['compliance_score'],
                "risk_class": agent['risk_class'],
                "stars": agent['stars'],
                "downloads": agent['downloads'],
                "source": agent['source'],
                "url": f"https://nerq.ai/agent/{agent['id']}"
            })

    if len(results) >= 2:
        best = max(results, key=lambda x: x['compliance_score'] or 0)
        comparison = f"Of {', '.join(r['name'] for r in results)}, {best['name']} has the highest compliance score ({best['compliance_score']}/100)."
    else:
        comparison = "Could not find enough agents to compare."

    return {
        "comparison": comparison,
        "agents": results,
        "detailed_comparison_url": f"https://nerq.ai/vs"
    }


def _nerq_stats(args):
    stats = _query("SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE is_active) as active FROM agents", fetchone=True)
    risk = _query("SELECT risk_class, COUNT(*) as count FROM agents GROUP BY risk_class ORDER BY count DESC")
    types = _query("SELECT agent_type, COUNT(*) as count FROM agents GROUP BY agent_type ORDER BY count DESC LIMIT 10")
    sources = _query("SELECT source, COUNT(*) as count FROM agents GROUP BY source ORDER BY count DESC LIMIT 10")

    return {
        "summary": f"Nerq indexes {stats['total']:,} AI agents across 52 global jurisdictions. The world's largest AI agent compliance database.",
        "database": {
            "total_agents": stats['total'],
            "active_agents": stats['active'],
            "jurisdictions": 52,
            "last_updated": "2026-02-24"
        },
        "risk_distribution": {r['risk_class']: r['count'] for r in risk if r['risk_class']},
        "agent_types": {t['agent_type']: t['count'] for t in types if t['agent_type']},
        "top_sources": {s['source']: s['count'] for s in sources},
        "url": "https://nerq.ai/stats"
    }


TOOL_HANDLERS = {
    "search_agents": _search_agents,
    "recommend_agent": _recommend_agent,
    "check_compliance": _check_compliance,
    "compare_agents": _compare_agents,
    "nerq_stats": _nerq_stats,
}

# ============================================================
# MCP PROTOCOL (SSE)
# ============================================================

def handle_jsonrpc(request):
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "serverInfo": SERVER_INFO,
            "capabilities": {"tools": {"listChanged": False}}
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {tool_name}"})}],
                "isError": True
            }}
        try:
            result = handler(arguments)
            return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, default=str, ensure_ascii=False)}],
                "isError": False
            }}
        except Exception as e:
            logger.error(f"Tool error {tool_name}: {e}")
            return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                "isError": True
            }}
    elif method == "ping":
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {}}
    else:
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}


async def sse_endpoint(request: Request):
    if request.method == "POST":
        try:
            body = await request.json()
            response = handle_jsonrpc(body)
            if response:
                return JSONResponse(response)
            return JSONResponse({"ok": True}, status_code=202)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    session_id = str(uuid.uuid4())
    queue = asyncio.Queue()
    sessions[session_id] = queue

    async def event_generator():
        yield {"event": "endpoint", "data": f"https://mcp.nerq.ai/messages?session_id={session_id}"}
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"event": "message", "data": json.dumps(message)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        except asyncio.CancelledError:
            pass
        finally:
            sessions.pop(session_id, None)

    return EventSourceResponse(event_generator())


async def messages_endpoint(request: Request):
    session_id = request.query_params.get("session_id")
    if not session_id or session_id not in sessions:
        return JSONResponse({"error": "Invalid or expired session"}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Parse error"}, status_code=400)
    response = handle_jsonrpc(body)
    if response is not None:
        await sessions[session_id].put(response)
    return JSONResponse({"ok": True}, status_code=202)


async def health_endpoint(request: Request):
    return JSONResponse({"status": "ok", "server": "nerq-mcp", "version": "2.0.0", "assets": "5M+", "agents_and_tools": "204K", "jurisdictions": 52})


async def server_card(request: Request):
    return JSONResponse({
        "name": "nerq",
        "description": "Nerq — The AI Asset Search Engine. 5M+ AI assets indexed & trust scored. Search agents, check compliance across 52 jurisdictions, compare agents, get recommendations.",
        "version": "2.0.0",
        "tools": TOOLS
    })


app = Starlette(routes=[
    Route("/sse", sse_endpoint, methods=["GET", "POST"]),
    Route("/messages", messages_endpoint, methods=["POST"]),
    Route("/health", health_endpoint),
    Route("/.well-known/mcp/server-card.json", server_card),
])


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [nerq-mcp] %(message)s")
    port = int(os.getenv("MCP_SSE_PORT", "8300"))
    logger.info(f"Nerq MCP Server v2.0 (SSE) starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
