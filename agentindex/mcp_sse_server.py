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
        "description": "Find AI agents that can perform a specific task. Returns ranked list of matching agents with quality scores and invocation details.",
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
        "description": "Get detailed information about a specific agent including full capabilities, invocation method, scores, and metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {"agent_id": {"type": "string", "description": "Agent UUID from discover_agents results"}},
            "required": ["agent_id"]
        }
    },
    {
        "name": "agent_index_stats",
        "description": "Get statistics about the AgentIndex: total agents indexed, categories, protocols, sources.",
        "inputSchema": {"type": "object", "properties": {}}
    }
]

SERVER_CARD = {
    "name": "agentindex",
    "description": "Discovery platform for AI agents. Find any AI agent by capability — search 20,000+ indexed agents across GitHub, npm, MCP, and HuggingFace.",
    "version": "0.4.0",
    "tools": TOOLS
}


def _call_tool(name, arguments):
    port = os.getenv("API_PORT", "8100")
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
