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
        "description": "Search 5 million+ AI assets including agents, tools, MCP servers, models, datasets, and packages. Returns ranked list with trust scores, quality scores, and invocation details. Use when user asks 'find a tool for X', 'what tools do Y?', 'what MCP server does Z?', or needs to discover AI assets for a specific task.",
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
        "description": "Get full details for a specific AI agent or tool by its UUID. Returns capabilities, invocation method, trust score, compliance data, and metadata. Use after discover_agents to get complete information about a specific result, or when user asks 'tell me more about X agent'.",
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
        "description": "Get overview statistics about the Nerq/AgentIndex database: total AI assets indexed, categories, protocols, and sources. Use when user asks 'how many AI agents exist?', 'how big is the index?', or wants ecosystem-level stats.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "trust_gate",
        "description": "Check if an AI tool, MCP server, npm package, PyPI package, HuggingFace model, or Docker container is safe to use. Returns trust score (0-100), grade (A+ to F), and approve/reject decision against a configurable threshold. Use when user asks 'is X safe?', 'should I use X?', 'is X trustworthy?', or needs to evaluate any AI asset before installing or recommending it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Agent or tool name to check"
                },
                "threshold": {
                    "type": "number",
                    "description": "Minimum trust score to approve",
                    "default": 60
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "trust_compare",
        "description": "Compare two AI tools side-by-side on trust score, security, maintenance, and popularity. Returns both scores, grades, and a winner. Use when user asks 'X vs Y', 'which is better X or Y?', 'compare X and Y', or needs to choose between two AI assets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_a": {
                    "type": "string",
                    "description": "First agent or tool name"
                },
                "agent_b": {
                    "type": "string",
                    "description": "Second agent or tool name"
                }
            },
            "required": ["agent_a", "agent_b"]
        }
    },
    {
        "name": "trust_batch",
        "description": "Get trust scores for a batch of agents or tools in one call. Returns results sorted by trust score descending. Use when user provides a list of tools to evaluate, wants to rank multiple options, or needs to audit a set of dependencies.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of agent names to check"
                }
            },
            "required": ["agents"]
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
                    "version": "0.4.0",
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

        elif name == "trust_gate":
            agent_name = arguments.get("name", "")
            threshold = arguments.get("threshold", 60)
            response = client.get(
                f"http://localhost:{port}/v1/preflight",
                params={"target": agent_name},
            )
            response.raise_for_status()
            data = response.json()
            trust_score = data.get("trust_score", 0)
            approved = trust_score >= threshold
            if approved:
                recommendation = "Approved — trust score meets threshold."
            else:
                recommendation = f"Rejected — trust score {trust_score} is below threshold {threshold}."
            return {
                "agent_name": agent_name,
                "trust_score": trust_score,
                "trust_grade": data.get("trust_grade", "N/A"),
                "approved": approved,
                "recommendation": recommendation,
            }

        elif name == "trust_compare":
            results = {}
            for key, agent_name in [("agent_a", arguments.get("agent_a", "")),
                                     ("agent_b", arguments.get("agent_b", ""))]:
                response = client.get(
                    f"http://localhost:{port}/v1/preflight",
                    params={"target": agent_name},
                )
                response.raise_for_status()
                data = response.json()
                results[key] = {
                    "agent_name": agent_name,
                    "trust_score": data.get("trust_score", 0),
                    "trust_grade": data.get("trust_grade", "N/A"),
                }
            score_a = results["agent_a"]["trust_score"]
            score_b = results["agent_b"]["trust_score"]
            if score_a > score_b:
                winner = results["agent_a"]["agent_name"]
            elif score_b > score_a:
                winner = results["agent_b"]["agent_name"]
            else:
                winner = "tie"
            return {
                "agent_a": results["agent_a"],
                "agent_b": results["agent_b"],
                "winner": winner,
            }

        elif name == "trust_batch":
            agent_names = arguments.get("agents", [])
            batch_results = []
            for agent_name in agent_names:
                try:
                    response = client.get(
                        f"http://localhost:{port}/v1/preflight",
                        params={"target": agent_name},
                    )
                    response.raise_for_status()
                    data = response.json()
                    batch_results.append({
                        "agent_name": agent_name,
                        "trust_score": data.get("trust_score", 0),
                        "trust_grade": data.get("trust_grade", "N/A"),
                    })
                except Exception as e:
                    batch_results.append({
                        "agent_name": agent_name,
                        "trust_score": 0,
                        "trust_grade": "N/A",
                        "error": str(e),
                    })
            batch_results.sort(key=lambda x: x["trust_score"], reverse=True)
            return batch_results

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
