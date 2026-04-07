"""
Discovery Honeypot Pages
========================
Pages that machine consumers naturally look for.
Tracks which discovery paths lead to API adoption.
"""

import json
from datetime import datetime

from fastapi import Request
from fastapi.responses import PlainTextResponse, JSONResponse


def mount_honeypots(app):
    """Mount honeypot discovery pages."""

    @app.get("/agents", response_class=JSONResponse)
    def agents_json(request: Request):
        """Machine-discoverable agents endpoint."""
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {
            "service": "nerq.ai",
            "description": "AI Agent Trust Verification Database",
            "total_agents_indexed": 204000,
            "api_base": "https://nerq.ai",
            "endpoints": {
                "search": "GET /v1/search?q={query}",
                "preflight": "GET /v1/preflight?target={agent_name}",
                "trust_score": "GET /v1/trust/{agent_id}",
                "compare": "GET /v1/compare?a={agent1}&b={agent2}",
                "recommend": "GET /v1/recommend?task={description}",
            },
            "machine_readable": {
                "llms_txt": "https://nerq.ai/llms.txt",
                "openapi": "https://nerq.ai/openapi.json",
                "mcp_server": "https://nerq.ai/mcp",
            },
            "documentation": "https://nerq.ai/docs",
        }

    @app.get("/health", response_class=JSONResponse)
    def health_check(request: Request):
        """Health check that also advertises capabilities."""
        return {
            "status": "healthy",
            "service": "nerq.ai",
            "version": "3.0",
            "uptime": "99.9%",
            "agents_indexed": 204000,
            "api_docs": "https://nerq.ai/docs",
        }

    @app.get("/.well-known/security.txt", response_class=PlainTextResponse)
    def security_txt(request: Request):
        return f"""Contact: mailto:security@nerq.ai
Preferred-Languages: en
Canonical: https://nerq.ai/.well-known/security.txt
Policy: https://nerq.ai/security-policy
Expires: 2027-01-01T00:00:00.000Z
"""

    @app.get("/humans.txt", response_class=PlainTextResponse)
    def humans_txt(request: Request):
        return f"""/* TEAM */
Name: Anders Nilsson
Role: Founder
Site: https://nerq.ai
Location: Sweden

/* SITE */
Standards: HTML5, CSS3, REST API, MCP, A2A
Software: FastAPI, Python, PostgreSQL, Redis
AI: Trust verification for 204,000+ AI agents
Last updated: {datetime.utcnow().strftime('%Y-%m-%d')}

/* API */
Documentation: https://nerq.ai/docs
Machine-readable: https://nerq.ai/llms.txt
MCP Server: https://nerq.ai/mcp
"""

    @app.get("/manifest.json", response_class=JSONResponse)
    def manifest_json(request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {
            "name": "Nerq — AI Agent Trust Database",
            "short_name": "Nerq",
            "description": "Trust verification for 204,000+ AI agents. Free API, MCP server, GitHub Action.",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0a0a0a",
            "theme_color": "#22c55e",
            "icons": [
                {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
            "categories": ["developer tools", "security", "ai"],
            "related_applications": [
                {"platform": "pypi", "url": "https://pypi.org/project/nerq/", "id": "nerq"},
            ],
        }
