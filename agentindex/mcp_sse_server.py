"""
AgentIndex MCP Server — SSE Transport
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
import httpx

logger = logging.getLogger("agentindex.mcp_sse")

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"

sessions: dict[str, asyncio.Queue] = {}

TOOLS = [
    {
        "name": "discover_agents",
        "description": "Search 5 million+ AI assets including agents, tools, MCP servers, models, datasets, and packages. Returns ranked list with trust scores, quality scores, and invocation details. Use when user asks 'find a tool for X', 'what tools do Y?', 'what MCP server does Z?', or needs to discover AI assets for a specific task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "need": {"type": "string", "description": "Natural language description of what you need an agent to do."},
                "category": {"type": "string", "description": "Optional category filter",
                    "enum": ["coding", "research", "content", "legal", "data", "finance", "marketing",
                             "design", "devops", "security", "education", "health", "communication",
                             "productivity", "infrastructure"]},
                "protocols": {"type": "array", "items": {"type": "string"}, "description": "Required protocols: mcp, a2a, rest, grpc"},
                "min_quality": {"type": "number", "description": "Minimum quality score 0.0-1.0", "default": 0.0}
            },
            "required": ["need"]
        }
    },
    {
        "name": "get_agent_details",
        "description": "Get full details for a specific AI agent or tool by its UUID. Returns capabilities, invocation method, trust score, compliance data, and metadata. Use after discover_agents to get complete information about a specific result, or when user asks 'tell me more about X agent'.",
        "inputSchema": {
            "type": "object",
            "properties": {"agent_id": {"type": "string", "description": "Agent UUID from discover_agents results"}},
            "required": ["agent_id"]
        }
    },
    {
        "name": "agent_index_stats",
        "description": "Get overview statistics about the Nerq/AgentIndex database: total AI assets indexed, categories, protocols, and sources. Use when user asks 'how many AI agents exist?', 'how big is the index?', or wants ecosystem-level stats.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "nerq_crypto_rating",
        "description": "Get Nerq Trust Score credit rating for a cryptocurrency. Returns 0-100 score with Moody's-style grade (Aaa-C) and 5-pillar breakdown. Covers 200+ tokens. Use when user asks 'what is the trust score for Bitcoin?', 'rate ETH', or needs a credit-style rating for any crypto token.",
        "inputSchema": {"type": "object", "properties": {"token_id": {"type": "string", "description": "CoinGecko token ID e.g. bitcoin, ethereum, solana"}}, "required": ["token_id"]}
    },
    {
        "name": "nerq_crypto_ndd",
        "description": "Get Nerq NDD (Nearness to Distress/Default) for a crypto token. Returns 0-5 distress score, 7 risk signals, crash probability, and HC alert status. NDD < 2.0 = high crash risk. 100% recall on crash detection. Use when user asks 'is X about to crash?', 'what is the crash risk for Y?', or needs distress/default analysis for any crypto token.",
        "inputSchema": {"type": "object", "properties": {"token_id": {"type": "string", "description": "CoinGecko token ID"}}, "required": ["token_id"]}
    },
    {
        "name": "nerq_crypto_safety",
        "description": "Quick pre-trade safety check for a crypto token. Returns SAFE/CAUTION/DANGER verdict with risk factors. Designed for AI agents and trading bots. Use when user asks 'is it safe to buy X?', 'should I trade Y?', or needs a quick go/no-go verdict before any crypto transaction.",
        "inputSchema": {"type": "object", "properties": {"token_id": {"type": "string", "description": "Token ID or symbol"}}, "required": ["token_id"]}
    },
    {
        "name": "nerq_crypto_signals",
        "description": "Get active crypto risk warnings from Nerq. Returns all WARNING and CRITICAL tokens with risk distribution across 200+ monitored tokens. Use when user asks 'which tokens are at risk?', 'any crypto warnings right now?', 'what tokens should I avoid?', or needs a market-wide risk dashboard.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "nerq_crypto_compare",
        "description": "Compare two crypto tokens side-by-side on safety: Trust Score, NDD, risk level, and crash probability. Returns verdict on which is safer. Use when user asks 'Bitcoin vs Ethereum safety', 'which is safer X or Y?', 'compare risk of X and Y', or needs to choose the safer token.",
        "inputSchema": {"type": "object", "properties": {"token1": {"type": "string", "description": "First token ID"}, "token2": {"type": "string", "description": "Second token ID"}}, "required": ["token1", "token2"]}
    },

    {
        "name": "find_best_agent",
        "description": "Find the top 5 best AI agents in a category that meet a minimum trust score threshold. Returns ranked agents with trust scores, compliance data, and risk levels. Use when user asks 'what is the best coding agent?', 'top security tools', 'recommend a finance agent', or needs the highest-rated agents in a domain.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category to search (e.g. coding, security, finance, data, devops)"},
                "min_trust_score": {"type": "number", "description": "Minimum trust score 0-100 (default 50)", "default": 50}
            },
            "required": ["category"]
        }
    },
    {
        "name": "agent_benchmark",
        "description": "Get the benchmark leaderboard for a category -- top 20 agents ranked by trust score with compliance data, stars, and platform info. Use when user asks 'show me the leaderboard for X', 'rank all coding agents', 'benchmark security tools', or needs a comprehensive category ranking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category to benchmark (e.g. coding, security, finance)"}
            },
            "required": ["category"]
        }
    },
    {
        "name": "get_agent_stats",
        "description": "Get full Nerq ecosystem statistics: total AI assets (5M+), breakdown by type (agents, tools, MCP servers, models, datasets), categories, frameworks, languages, and trust score distribution. Use when user asks 'how many AI agents are there?', 'what does Nerq index?', or needs ecosystem-level data for reports or analysis.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "preflight_trust_check",
        "description": "Check if an AI tool, MCP server, npm package, PyPI package, HuggingFace model, or Docker container is safe to use. Returns trust score (0-100), grade (A+ to F), risk level, and PROCEED/CAUTION/DENY recommendation. Use when user asks 'is X safe?', 'should I use X?', 'is X trustworthy?', or needs to evaluate any AI asset before installing, recommending, or delegating tasks to it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Agent name to check trust for"},
                "caller": {"type": "string", "description": "Your agent name (optional, for interaction risk calculation)"}
            },
            "required": ["target"]
        }
    },
    {
        "name": "kya_report",
        "description": "Get a full Know Your Agent (KYA) due diligence report for any AI agent or tool. Returns trust score, grade, category, description, stars, source URL, compliance data, and risk assessment across 204K+ indexed agents. Use when user asks 'give me a full report on X', 'due diligence on Y', 'audit Z', or needs comprehensive safety and compliance information before adopting an AI asset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Agent name to look up"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "nerq_scout_status",
        "description": "Get Nerq Scout status: how many agents evaluated, featured, and claimed recently. Use when user asks 'what is Nerq Scout doing?', 'how many agents has Scout evaluated?', or wants to check the discovery pipeline status.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "nerq_scout_findings",
        "description": "Get latest top agents discovered by Nerq Scout -- high-trust agents (85+) with stars, categories, and trust scores. Use when user asks 'what are the best new agents?', 'show me recently discovered tools', 'trending AI agents', or wants to see Scout's latest high-quality findings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10}
            }
        }
    },
]

# Merge in T214 expansion tools defined in agentindex/mcp/tools_v3.py.
# tools_v3 is the single source of truth for the compare_packages /
# find_similar / get_verticals / list_by_registry / get_alternatives /
# get_trust_history / search_by_dimension tools; duplicates by name
# (e.g. get_rating/get_signals/get_dependencies which pre-existed in
# this file) are left untouched so the SSE handler keeps its historical
# wiring.
try:
    from agentindex.mcp.tools_v3 import TOOLS as _V3_TOOLS_EXTRA
    _existing_names = {t["name"] for t in TOOLS}
    for _t in _V3_TOOLS_EXTRA:
        if _t.get("name") and _t["name"] not in _existing_names:
            TOOLS.append(_t)
            _existing_names.add(_t["name"])
except Exception:  # noqa: BLE001 — advertising failure must not break the server
    pass

SERVER_CARD = {
    "name": "agentindex",
    "description": "ZARQ crypto risk intelligence + Nerq AI agent trust verification. 204K agents & tools indexed, 198 tokens rated. Preflight checks, KYA reports, benchmarks. Free API.",
    "version": "1.1.0",
    "tools": TOOLS
}


def _call_tool(name, arguments):
    port = os.getenv("API_PORT", "8000")
    base_url = f"http://localhost:{port}/v1"
    try:
        client = httpx.Client(timeout=30)
        if name == "discover_agents":
            response = client.post(f"{base_url}/discover", json={
                "need": arguments.get("need", ""),
                "category": arguments.get("category"),
                "protocols": arguments.get("protocols"),
                "min_quality": arguments.get("min_quality", 0.0),
            })
            response.raise_for_status()
            return response.json()
        elif name == "get_agent_details":
            response = client.get(f"{base_url}/agent/{arguments.get('agent_id', '')}")
            response.raise_for_status()
            return response.json()
        elif name == "agent_index_stats":
            response = client.get(f"{base_url}/stats")
            response.raise_for_status()
            return response.json()
        elif name in ("nerq_crypto_rating", "nerq_crypto_ndd", "nerq_crypto_safety",
                       "nerq_crypto_signals", "nerq_crypto_compare"):
            # Proxy crypto tools to the main API
            if name == "nerq_crypto_rating":
                response = client.get(f"{base_url}/crypto/rating/{arguments['token_id']}")
            elif name == "nerq_crypto_ndd":
                response = client.get(f"{base_url}/crypto/ndd/{arguments['token_id']}")
            elif name == "nerq_crypto_safety":
                response = client.get(f"{base_url}/check/{arguments['token_id']}")
            elif name == "nerq_crypto_signals":
                response = client.get(f"{base_url}/crypto/signals")
            elif name == "nerq_crypto_compare":
                response = client.get(f"{base_url}/crypto/compare/{arguments['token1']}/{arguments['token2']}")
            response.raise_for_status()
            return response.json()
        elif name == "find_best_agent":
            cat = arguments.get("category", "")
            min_trust = arguments.get("min_trust_score", 50)
            response = client.get(
                f"{base_url}/agent/search",
                params={"domain": cat, "min_trust": min_trust, "limit": 5}
            )
            response.raise_for_status()
            return response.json()
        elif name == "agent_benchmark":
            cat = arguments.get("category", "")
            response = client.get(f"{base_url}/agent/benchmark/{cat}")
            response.raise_for_status()
            return response.json()
        elif name == "get_agent_stats":
            response = client.get(f"{base_url}/agent/stats")
            response.raise_for_status()
            return response.json()
        elif name == "preflight_trust_check":
            params = {"target": arguments.get("target", "")}
            if arguments.get("caller"):
                params["caller"] = arguments["caller"]
            response = client.get(f"{base_url}/preflight", params=params)
            response.raise_for_status()
            return response.json()
        elif name == "kya_report":
            agent_name = arguments.get("name", "")
            response = client.get(f"{base_url}/agent/kya/{agent_name}",
                                  headers={"X-API-Key": "nerq-internal-2026"})
            response.raise_for_status()
            return response.json()
        elif name == "nerq_scout_status":
            response = client.get(f"http://localhost:{port}/v1/scout/status",
                                  headers={"X-API-Key": "nerq-internal-2026"})
            response.raise_for_status()
            return response.json()
        elif name == "nerq_scout_findings":
            limit = arguments.get("limit", 10)
            response = client.get(f"http://localhost:{port}/v1/scout/findings",
                                  params={"limit": limit},
                                  headers={"X-API-Key": "nerq-internal-2026"})
            response.raise_for_status()
            return response.json()
        else:
            return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        return {"error": str(e)}


def handle_jsonrpc(request):
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "agentindex", "version": "0.4.0"},
        }}
    elif method == "tools/list":
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = _call_tool(tool_name, arguments)
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
        }}
    elif method == "notifications/initialized":
        return None
    elif method == "ping":
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {}}
    else:
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}


async def sse_endpoint(request: Request):
    if request.method == "POST":
        try:
            body = await request.json()
            logger.info(f"POST /sse: {body.get('method', 'unknown')}")
            response = handle_jsonrpc(body)
            if response:
                return JSONResponse(response)
            return JSONResponse({"ok": True}, status_code=202)
        except Exception as e:
            logger.error(f"POST /sse error: {e}")
            return JSONResponse({"error": str(e)}, status_code=400)

    session_id = str(uuid.uuid4())
    queue = asyncio.Queue()
    sessions[session_id] = queue
    logger.info(f"SSE session started: {session_id}")

    async def event_generator():
        yield {"event": "endpoint", "data": f"https://mcp.agentcrawl.dev/messages?session_id={session_id}"}
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
            logger.info(f"SSE session ended: {session_id}")

    return EventSourceResponse(event_generator())


async def messages_endpoint(request: Request):
    session_id = request.query_params.get("session_id")
    if not session_id or session_id not in sessions:
        return JSONResponse({"error": "Invalid or expired session_id"}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": JSONRPC_VERSION, "id": None,
                             "error": {"code": -32700, "message": "Parse error"}}, status_code=400)
    logger.info(f"[{session_id[:8]}] {body.get('method', 'unknown')}")
    response = handle_jsonrpc(body)
    if response is not None:
        await sessions[session_id].put(response)
    return JSONResponse({"ok": True}, status_code=202)


async def health_endpoint(request: Request):
    return JSONResponse({"status": "ok", "transport": "sse", "server": "agentindex-mcp"})


async def server_card(request: Request):
    return JSONResponse(SERVER_CARD)


app = Starlette(routes=[
    Route("/sse", sse_endpoint, methods=["GET", "POST"]),
    Route("/messages", messages_endpoint, methods=["POST", "GET"]),
    Route("/health", health_endpoint),
    Route("/.well-known/mcp/server-card.json", server_card),
])


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    port = int(os.getenv("MCP_SSE_PORT", "8300"))
    logger.info(f"AgentIndex MCP SSE Server starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
