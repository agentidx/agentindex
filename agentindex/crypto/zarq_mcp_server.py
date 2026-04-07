#!/usr/bin/env python3
"""
ZARQ Crypto Risk Intelligence — MCP Server
============================================
Exposes ZARQ's crypto risk tools via the Model Context Protocol (MCP).
Designed for registration on Smithery and Glama registries.

Tools:
  1. crypto_safety_check    — Quick pre-trade safety validation (<100ms)
  2. crypto_rating           — Full Trust Score with 5-pillar breakdown
  3. crypto_dtd              — Distance-to-Default with 7 signals
  4. crypto_signals          — Active Structural Collapse/Stress signals
  5. crypto_compare          — Head-to-head token comparison
  6. crypto_distress_watch   — All tokens with DtD < 2.0
  7. crypto_alerts            — Structural collapse/stress warnings
  8. crypto_ratings_bulk     — Bulk ratings for multiple tokens

Usage:
  python zarq_mcp_server.py                    # stdio transport (default)
  python zarq_mcp_server.py --transport sse    # SSE transport for web

Requirements:
  pip install mcp httpx

Registry tags: crypto, risk, defi, safety, trust-score, crash-prediction, distance-to-default, ratings
"""

import json
import asyncio
import argparse
import httpx
from typing import Any

# ─── MCP SDK Import ───
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp")
    print("Falling back to standalone HTTP mode.")
    Server = None

# ─── Configuration ───
ZARQ_API_BASE = "https://zarq.ai"
ZARQ_API_TIMEOUT = 10.0

# ─── API Client ───
async def zarq_api(path: str, params: dict = None) -> dict:
    """Call ZARQ API endpoint and return JSON response."""
    async with httpx.AsyncClient(timeout=ZARQ_API_TIMEOUT) as client:
        url = f"{ZARQ_API_BASE}{path}"
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


# ─── Tool Definitions ───
TOOLS = [
    Tool(
        name="crypto_safety_check",
        description=(
            "Quick pre-trade safety check for a crypto token. Returns risk level, "
            "trust grade, DtD score, alert status, crash probability, and any active flags. "
            "Optimized for <100ms response. Use before any crypto trade or investment decision. "
            "Example: crypto_safety_check(token_id='bitcoin')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token_id": {
                    "type": "string",
                    "description": "Token identifier (e.g., 'bitcoin', 'ethereum', 'solana', 'cardano'). Use lowercase CoinGecko-style IDs."
                }
            },
            "required": ["token_id"]
        }
    ),
    Tool(
        name="crypto_rating",
        description=(
            "Get the full ZARQ Trust Score for a crypto token. Returns overall score (0-100), "
            "letter grade (A+ to F), and breakdown across 5 pillars: Security (30%), "
            "Compliance (25%), Maintenance (20%), Popularity (15%), Ecosystem (10%). "
            "198 tokens rated. Example: crypto_rating(token_id='ethereum')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token_id": {
                    "type": "string",
                    "description": "Token identifier (e.g., 'bitcoin', 'ethereum'). Use lowercase CoinGecko-style IDs."
                }
            },
            "required": ["token_id"]
        }
    ),
    Tool(
        name="crypto_dtd",
        description=(
            "Get the Distance-to-Default (DtD) score for a crypto token. DtD measures "
            "distance-to-default on a 0-5 scale (5=healthy, 0=imminent collapse). Returns "
            "7 signal scores (Liquidity, Holders, Resilience, Fundamental, Contagion, "
            "Structural, Relative Weakness), trend classification (FREEFALL/FALLING/SLIDING/"
            "STABLE/IMPROVING), crash probability, and Structural Collapse status. "
            "Example: crypto_ndd(token_id='solana')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token_id": {
                    "type": "string",
                    "description": "Token identifier (e.g., 'solana'). Use lowercase CoinGecko-style IDs."
                }
            },
            "required": ["token_id"]
        }
    ),
    Tool(
        name="crypto_signals",
        description=(
            "Get all active crypto risk signals: Structural Collapse and Structural Stress alerts "
            "and recovery recovery signals. Each signal includes token, DtD score, trend, "
            "crash probability, streak duration, SHA-256 hash, and timestamp. Also returns "
            "a running scoreboard with precision metrics. Use to monitor the crypto market "
            "for emerging risks. Example: crypto_signals()"
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    Tool(
        name="crypto_compare",
        description=(
            "Compare two crypto tokens head-to-head. Returns Trust Score, NDD, risk level, "
            "and key differences for both tokens. Useful for relative value analysis or "
            "deciding between two investments. "
            "Example: crypto_compare(token_a='bitcoin', token_b='ethereum')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token_a": {
                    "type": "string",
                    "description": "First token identifier"
                },
                "token_b": {
                    "type": "string",
                    "description": "Second token identifier"
                }
            },
            "required": ["token_a", "token_b"]
        }
    ),
    Tool(
        name="crypto_distress_watch",
        description=(
            "Get all tokens currently showing distress (DtD < 2.0). Returns a watchlist "
            "of tokens with elevated crash risk, sorted by DtD score ascending (most "
            "distressed first). Use to identify tokens to avoid or potentially short. "
            "Example: crypto_distress_watch()"
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    Tool(
        name="crypto_alerts",
        description=(
            "Get all active ZARQ structural warnings. Two levels: STRUCTURAL COLLAPSE "
            "(≥3 weakness signals, historically 98% lost >50% value) and STRUCTURAL STRESS "
            "(≥2 weakness signals, requires monitoring). Out-of-sample validated: 113/113 "
            "token deaths detected with 98% precision. "
            "Example: crypto_alerts(level='CRITICAL') or crypto_alerts()"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "description": "Filter by alert level: 'CRITICAL' (structural collapse) or 'WARNING' (structural stress). Omit for all.",
                    "enum": ["CRITICAL", "WARNING"]
                }
            },
            "required": []
        }
    ),
    Tool(
        name="crypto_ratings_bulk",
        description=(
            "Get Trust Score ratings for all 205 rated tokens in bulk. Returns token_id, "
            "name, symbol, trust_score, trust_grade, and risk_level for each. "
            "Useful for screening, portfolio construction, or building filtered lists. "
            "Example: crypto_ratings_bulk()"
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    Tool(
        name="check_token_risk",
        description=(
            "Zero-friction risk check for any crypto token. Returns verdict (SAFE/WARNING/CRITICAL), "
            "trust score (0-100), Moody's-style rating (Aaa-D), distance-to-default, crash probability, "
            "structural weakness flag, current price, and risk level. No auth needed. "
            "Recommended starting point for any token risk query. 205 tokens covered. "
            "Example: check_token_risk(token='bitcoin')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token identifier (e.g., 'bitcoin', 'ethereum', 'solana'). Use lowercase CoinGecko-style IDs."
                }
            },
            "required": ["token"]
        }
    ),
    Tool(
        name="get_risk_signals",
        description=(
            "Get all tokens with active ZARQ warnings. Returns the full list of 205 monitored "
            "tokens with their risk level (SAFE/WATCH/WARNING/CRITICAL), trust score, "
            "structural weakness count, and NDD score. Filter to see only tokens with active "
            "warnings or structural collapse alerts. "
            "Example: get_risk_signals() or get_risk_signals(level='CRITICAL')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "description": "Filter by risk level: 'CRITICAL', 'WARNING', 'WATCH', or 'SAFE'. Omit for all.",
                    "enum": ["CRITICAL", "WARNING", "WATCH", "SAFE"]
                }
            },
            "required": []
        }
    ),
    Tool(
        name="get_trust_score",
        description=(
            "Get just the ZARQ Trust Score for a token. Returns the score (0-100), "
            "Moody's-style grade (Aaa through D), and risk level. Lightweight alternative "
            "to check_token_risk when you only need the score. "
            "Example: get_trust_score(token='ethereum')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token identifier (e.g., 'bitcoin', 'ethereum'). Use lowercase CoinGecko-style IDs."
                }
            },
            "required": ["token"]
        }
    ),
    Tool(
        name="kya_check_agent",
        description=(
            "Know Your Agent — Due diligence check for any AI agent. Returns trust score, "
            "compliance score, risk level (TRUSTED/CAUTION/UNTRUSTED), days active, and "
            "a human-readable verdict. Covers 204K indexed agents & tools across GitHub, npm, PyPI, "
            "and more. If the agent handles crypto, includes ZARQ risk data. "
            "Example: kya_check_agent(agent='autogpt')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Agent name or UUID to check (e.g., 'autogpt', 'crewai', or a UUID)"
                }
            },
            "required": ["agent"]
        }
    ),
    Tool(
        name="get_signal_feed",
        description=(
            "The ZARQ Signal — Live crypto risk intelligence feed. Returns all current risk "
            "signals sorted by severity (CRITICAL first), daily summary with warning counts, "
            "new signals in last 24h, and resolved signals. 205 tokens monitored daily. "
            "Example: get_signal_feed()"
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        }
    ),
    # ─── Vitality Score Tools ───
    Tool(
        name="vitality_check",
        description=(
            "Get the ZARQ Vitality Score for a crypto token — ecosystem health assessment "
            "across 5 dimensions: Ecosystem Gravity (protocol density, TVL, stablecoins), "
            "Capital Commitment (TVL retention, yield density), Coordination Efficiency "
            "(category diversity, audit coverage), Stress Resilience (NDD stability, crash "
            "probability, drawdown), and Organic Momentum (TVL/price/rating trends). "
            "Score 0-100, grades S/A/B/C/D/F. 15,000+ tokens scored. "
            "Example: vitality_check(token='ethereum')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token identifier (e.g., 'ethereum', 'solana'). Use lowercase CoinGecko-style IDs."
                }
            },
            "required": ["token"]
        }
    ),
    Tool(
        name="vitality_compare",
        description=(
            "Compare Vitality Scores of two crypto tokens side-by-side. Returns scores, "
            "grades, all 5 dimension breakdowns, and which token is stronger in each area. "
            "Use for ecosystem quality comparison. "
            "Example: vitality_compare(token_a='ethereum', token_b='solana')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token_a": {"type": "string", "description": "First token identifier"},
                "token_b": {"type": "string", "description": "Second token identifier"}
            },
            "required": ["token_a", "token_b"]
        }
    ),
    # ─── Nerq Agent Tools (Sprint N0) ───
    Tool(
        name="find_best_agent",
        description=(
            "Find the top 5 best AI agents in a category that meet a minimum trust score. "
            "Returns agents ranked by trust score with compliance data. "
            "Categories: coding, security, finance, data, devops, marketing, legal, research, etc. "
            "Example: find_best_agent(category='coding', min_trust_score=60)"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category to search"},
                "min_trust_score": {"type": "number", "description": "Min trust score 0-100", "default": 50}
            },
            "required": ["category"]
        }
    ),
    Tool(
        name="agent_benchmark",
        description=(
            "Get the benchmark leaderboard for an AI agent category — top 20 agents ranked by "
            "trust score with compliance, risk level, stars, and platform. "
            "Example: agent_benchmark(category='security')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category to benchmark"}
            },
            "required": ["category"]
        }
    ),
    Tool(
        name="get_agent_stats",
        description=(
            "Get full Nerq ecosystem statistics: 5M+ AI assets broken down by type "
            "(agents, tools, MCP servers, models, datasets), categories, frameworks, "
            "languages, trust distribution, and recent growth. "
            "Example: get_agent_stats()"
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        }
    ),
    # ─── Universal Tools (works for ALL entity types) ───
    Tool(
        name="preflight_check",
        description=(
            "Preflight safety check for ANY software entity — apps, VPNs, npm packages, "
            "Python packages, Chrome extensions, WordPress plugins, websites, games, and more. "
            "Returns trust score (0-100), grade (A+ to F), recommendation (PROCEED/CAUTION/BLOCK), "
            "security details, and alternatives. Works for 7.5M+ entities across 26 registries. "
            "Use when user asks 'is X safe?', 'should I install X?', 'is X trustworthy?'. "
            "Example: preflight_check(target='nordvpn')"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Entity name — e.g. 'nordvpn', 'express', 'react', 'tiktok', 'bitwarden'"}
            },
            "required": ["target"]
        }
    ),
    Tool(
        name="best_in_category",
        description=(
            "Get the top-rated entities in a category by Nerq Trust Score. "
            "Works for software categories (npm, pypi, vpn, password_manager, antivirus, "
            "hosting, website_builder, saas, crypto, chrome, firefox, wordpress, ios, android, steam) "
            "and more. Returns ranked list with scores, grades, and descriptions. "
            "Example: best_in_category(category='vpn', limit=5)"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Registry/category name — e.g. 'vpn', 'npm', 'password_manager', 'antivirus'"},
                "limit": {"type": "integer", "description": "Number of results (default 10, max 20)", "default": 10}
            },
            "required": ["category"]
        }
    ),
]


# ─── Tool Handlers ───
async def handle_tool(name: str, arguments: dict) -> str:
    """Route tool calls to ZARQ API endpoints."""
    try:
        if name == "crypto_safety_check":
            token_id = arguments["token_id"]
            data = await zarq_api(f"/v1/crypto/safety/{token_id}")
            return json.dumps(data, indent=2)

        elif name == "crypto_rating":
            token_id = arguments["token_id"]
            data = await zarq_api(f"/v1/crypto/rating/{token_id}")
            return json.dumps(data, indent=2)

        elif name == "crypto_dtd":
            token_id = arguments["token_id"]
            data = await zarq_api(f"/v1/crypto/ndd/{token_id}")
            return json.dumps(data, indent=2)

        elif name == "crypto_signals":
            data = await zarq_api("/v1/crypto/signals")
            return json.dumps(data, indent=2)

        elif name == "crypto_compare":
            token_a = arguments["token_a"]
            token_b = arguments["token_b"]
            data = await zarq_api(f"/v1/crypto/compare/{token_a}/{token_b}")
            return json.dumps(data, indent=2)

        elif name == "crypto_distress_watch":
            data = await zarq_api("/v1/crypto/distress-watch")
            return json.dumps(data, indent=2)

        elif name == "crypto_alerts":
            params = {}
            if "level" in arguments:
                params["level"] = arguments["level"]
            data = await zarq_api("/v1/crypto/alerts", params=params)
            return json.dumps(data, indent=2)

        elif name == "crypto_ratings_bulk":
            data = await zarq_api("/v1/crypto/ratings")
            return json.dumps(data, indent=2)

        elif name == "check_token_risk":
            token = arguments["token"]
            data = await zarq_api(f"/v1/check/{token}")
            return json.dumps(data, indent=2)

        elif name == "get_risk_signals":
            params = {}
            if "level" in arguments:
                params["risk_level"] = arguments["level"]
            data = await zarq_api("/v1/crypto/signals", params=params)
            return json.dumps(data, indent=2)

        elif name == "get_trust_score":
            token = arguments["token"]
            data = await zarq_api(f"/v1/check/{token}")
            # Return only score-related fields
            if isinstance(data, dict) and "trust_score" in data:
                return json.dumps({
                    "token": data.get("token"),
                    "trust_score": data.get("trust_score"),
                    "rating": data.get("rating"),
                    "risk_level": data.get("risk_level"),
                    "verdict": data.get("verdict"),
                }, indent=2)
            return json.dumps(data, indent=2)

        elif name == "kya_check_agent":
            agent = arguments["agent"]
            data = await zarq_api(f"/v1/agent/kya/{agent}")
            return json.dumps(data, indent=2)

        elif name == "get_signal_feed":
            data = await zarq_api("/v1/signal/feed")
            return json.dumps(data, indent=2)

        elif name == "vitality_check":
            token = arguments["token"]
            data = await zarq_api(f"/v1/vitality/{token}")
            return json.dumps(data, indent=2)

        elif name == "vitality_compare":
            token_a = arguments["token_a"]
            token_b = arguments["token_b"]
            data = await zarq_api(f"/v1/vitality/{token_a}/compare/{token_b}")
            return json.dumps(data, indent=2)

        elif name == "find_best_agent":
            cat = arguments.get("category", "")
            min_trust = arguments.get("min_trust_score", 50)
            data = await zarq_api("/v1/agent/search", params={
                "domain": cat, "min_trust": min_trust, "limit": 5
            })
            return json.dumps(data, indent=2)

        elif name == "agent_benchmark":
            cat = arguments.get("category", "")
            data = await zarq_api(f"/v1/agent/benchmark/{cat}")
            return json.dumps(data, indent=2)

        elif name == "get_agent_stats":
            data = await zarq_api("/v1/agent/stats")
            return json.dumps(data, indent=2)

        elif name == "preflight_check":
            target = arguments["target"]
            data = await zarq_api("/v1/preflight", params={"target": target})
            return json.dumps(data, indent=2)

        elif name == "best_in_category":
            category = arguments["category"]
            limit = min(arguments.get("limit", 10), 20)
            # Query software_registry directly for the category
            try:
                from agentindex.db.models import get_session
                from sqlalchemy import text
                _s = get_session()
                rows = _s.execute(text("""
                    SELECT name, slug, trust_score, trust_grade, description
                    FROM software_registry
                    WHERE registry = :reg AND trust_score IS NOT NULL AND trust_score > 30
                      AND description IS NOT NULL
                    ORDER BY trust_score DESC LIMIT :lim
                """), {"reg": category, "lim": limit}).fetchall()
                _s.close()
                results = [{"rank": i+1, "name": r[0], "slug": r[1], "trust_score": round(r[2], 1),
                           "grade": r[3], "description": (r[4] or "")[:200],
                           "url": f"https://nerq.ai/safe/{r[1]}"}
                          for i, r in enumerate(rows)]
                return json.dumps({"category": category, "count": len(results), "entities": results}, indent=2)
            except Exception as e:
                return json.dumps({"error": f"Database query failed: {str(e)}"})

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except httpx.HTTPStatusError as e:
        return json.dumps({
            "error": f"ZARQ API returned {e.response.status_code}",
            "detail": e.response.text[:500]
        })
    except httpx.ConnectError:
        return json.dumps({"error": "Could not connect to ZARQ API at zarq.ai"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── MCP Server Setup ───
def create_server() -> "Server":
    """Create and configure the MCP server."""
    server = Server("zarq-crypto")

    @server.list_tools()
    async def list_tools():
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list:
        result = await handle_tool(name, arguments)
        return [TextContent(type="text", text=result)]

    return server


async def run_stdio():
    """Run server with stdio transport (default for MCP)."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        from mcp.server import InitializationOptions
        from mcp.server.models import ServerCapabilities
        init_options = InitializationOptions(
            server_name="zarq-crypto",
            server_version="1.2.0",
            capabilities=ServerCapabilities(tools={})
        )
        await server.run(read_stream, write_stream, init_options)


async def run_sse(host: str = "0.0.0.0", port: int = 8001):
    """Run server with Streamable HTTP + SSE transport."""
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from mcp.server.sse import SseServerTransport
    from mcp.server import InitializationOptions
    from mcp.server.models import ServerCapabilities
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    import contextlib
    import uvicorn

    server = create_server()
    init_options = InitializationOptions(
        server_name="zarq-crypto",
        server_version="1.2.0",
        capabilities=ServerCapabilities(tools={})
    )

    # --- Streamable HTTP via SessionManager ---
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=True,
    )

    async def handle_mcp(request):
        await session_manager.handle_request(request.scope, request.receive, request._send)

    # --- Legacy SSE transport ---
    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], init_options)

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    # --- Utility endpoints ---
    async def handle_server_card(request):
        return JSONResponse({
            "serverInfo": {
                "name": "zarq-crypto",
                "version": "1.2.0",
            },
            "display_name": "ZARQ Crypto Risk Intelligence",
            "description": "Independent crypto risk intelligence: Trust Score ratings (Aaa-D) for 205 tokens, Distance-to-Default (DtD) with 7 signals, structural collapse warnings (100% recall, 98% precision OOS), crash probability, and zero-friction risk checks. Free API, no auth required.",
            "author": "ZARQ",
            "homepage": "https://zarq.ai",
            "authentication": {"required": False},
            "transport": {
                "type": "streamable-http",
                "url": "https://mcp.zarq.ai/mcp",
            },
            "tools": [
                {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                for t in TOOLS
            ],
            "tags": ["crypto", "risk", "defi", "safety", "trust-score", "crash-prediction", "distance-to-default", "ratings", "blockchain", "token-analysis"],
        })

    async def handle_health(request):
        return JSONResponse({"status": "ok", "server": "zarq-crypto", "version": "1.2.0"})

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            yield

    app = Starlette(
        routes=[
            Route("/.well-known/mcp/server-card.json", handle_server_card),
            Route("/health", handle_health),
            Route("/mcp", handle_mcp, methods=["GET", "POST", "DELETE"]),
            Route("/sse", handle_sse),
            Route("/messages", handle_messages, methods=["POST"]),
        ],
        lifespan=lifespan,
    )

    config = uvicorn.Config(app, host=host, port=port)
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


# ─── Smithery Configuration ───
SMITHERY_CONFIG = {
    "name": "zarq-crypto",
    "display_name": "ZARQ Crypto Risk Intelligence",
    "description": (
        "Independent crypto risk intelligence: Trust Score ratings (Aaa-D) for 205 tokens, "
        "Distance-to-Default (DtD) with 7 signals, structural collapse warnings "
        "(100% recall, 98% precision OOS), crash probability, and zero-friction risk checks. "
        "Free API, no auth required. Source: zarq.ai"
    ),
    "version": "1.2.0",
    "author": "ZARQ",
    "homepage": "https://zarq.ai",
    "tags": [
        "crypto", "risk", "defi", "safety", "trust-score",
        "crash-prediction", "distance-to-default", "ratings", "blockchain",
        "token-analysis", "portfolio-risk", "early-warning"
    ],
    "tools": len(TOOLS),
    "transport": ["stdio", "sse"],
    "license": "MIT"
}


# ─── Entry Point ───
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ZARQ Crypto MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio",
                        help="Transport type (default: stdio)")
    parser.add_argument("--port", type=int, default=8001,
                        help="Port for SSE transport (default: 8001)")
    parser.add_argument("--config", action="store_true",
                        help="Print Smithery configuration JSON")
    args = parser.parse_args()

    if args.config:
        print(json.dumps(SMITHERY_CONFIG, indent=2))
    elif args.transport == "sse":
        asyncio.run(run_sse(port=args.port))
    else:
        asyncio.run(run_stdio())
