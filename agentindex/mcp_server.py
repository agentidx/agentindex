"""
AgentIndex MCP Server

Exposes AgentIndex as an MCP tool that any MCP-compatible agent can use.
Install and run as a standard MCP server.

Usage:
    python -m agentindex.mcp_server

Or in MCP config:
    {
        "agentindex": {
            "command": "python",
            "args": ["-m", "agentindex.mcp_server"]
        }
    }
"""

import json
import sys
import logging
from typing import Any

logger = logging.getLogger("agentindex.mcp_server")

# MCP protocol constants
JSONRPC_VERSION = "2.0"

TOOLS = [
    {
        "name": "discover_agents",
        "description": "Find AI agents that can perform a specific task. Returns ranked list of matching agents with quality scores and invocation details. Use this when you need to find an agent for a specific capability.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "need": {
                    "type": "string",
                    "description": "Natural language description of what you need an agent to do. Be specific about the task."
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter",
                    "enum": ["coding", "research", "content", "legal", "data",
                             "finance", "marketing", "design", "devops", "security",
                             "education", "health", "communication", "productivity",
                             "infrastructure"]
                },
                "protocols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Required protocols: mcp, a2a, rest, grpc"
                },
                "min_quality": {
                    "type": "number",
                    "description": "Minimum quality score 0.0-1.0. Default 0.0.",
                    "default": 0.0
                }
            },
            "required": ["need"]
        }
    },
    {
        "name": "get_agent_details",
        "description": "Get detailed information about a specific agent including full capabilities, invocation method, scores, and metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent UUID from discover_agents results"
                }
            },
            "required": ["agent_id"]
        }
    },
    {
        "name": "agent_index_stats",
        "description": "Get statistics about the AgentIndex: total agents indexed, categories, protocols, sources.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


def handle_request(request: dict) -> dict:
    """Handle an MCP JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "agentindex",
                    "version": "0.3.0",
                },
            },
        }

    elif method == "tools/list":
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = _call_tool(tool_name, arguments)
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            },
        }

    elif method == "notifications/initialized":
        return None  # No response needed for notifications

    else:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def _call_tool(name: str, arguments: dict) -> Any:
    """Execute a tool call against the local API."""
    import httpx
    import os

    port = os.getenv("API_PORT", "8100")
    base_url = f"http://localhost:{port}/v1"

    try:
        client = httpx.Client(timeout=30)

        if name == "discover_agents":
            response = client.post(
                f"{base_url}/discover",
                json={
                    "need": arguments.get("need", ""),
                    "category": arguments.get("category"),
                    "protocols": arguments.get("protocols"),
                    "min_quality": arguments.get("min_quality", 0.0),
                },
            )
            response.raise_for_status()
            return response.json()

        elif name == "get_agent_details":
            agent_id = arguments.get("agent_id", "")
            response = client.get(f"{base_url}/agent/{agent_id}")
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


def main():
    """Run MCP server on stdio."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    logger.info("AgentIndex MCP Server starting...")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            response = handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            error_response = {
                "jsonrpc": JSONRPC_VERSION,
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Error handling request: {e}")


if __name__ == "__main__":
    main()
