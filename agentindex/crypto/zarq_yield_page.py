"""
Sprint 9: Yield Risk Page + API Router mount
Monteras i discovery.py med:

    from agentindex.crypto.zarq_yield_page import mount_yield_page
    mount_yield_page(app)

Routes:
    /yield-risk           → HTML page
    /yield                → redirect → /yield-risk
    /v1/yield/*           → API endpoints (via yield_risk_api.py router)
"""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

from agentindex.crypto.yield_risk_api import router_yield

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "zarq_yield_template.html"


def mount_yield_page(app: FastAPI):
    """Mount yield risk page + API router onto the FastAPI app."""

    # Mount API router
    app.include_router(router_yield)

    @app.get("/yield-risk", response_class=HTMLResponse, include_in_schema=False)
    async def yield_risk_page():
        try:
            from agentindex.crypto.zarq_content_pages import _render_yield_risk
            return HTMLResponse(content=_render_yield_risk())
        except Exception as e:
            if TEMPLATE_PATH.exists():
                return HTMLResponse(content=TEMPLATE_PATH.read_text())
            return HTMLResponse(content=_fallback_html(), status_code=200)

    @app.get("/yield", response_class=RedirectResponse, include_in_schema=False)
    async def yield_redirect():
        return RedirectResponse(url="/yield-risk", status_code=301)

    @app.get("/yield-traps", response_class=RedirectResponse, include_in_schema=False)
    async def yield_traps_redirect():
        return RedirectResponse(url="/yield-risk", status_code=301)


def _fallback_html():
    return """<!DOCTYPE html><html><body>
    <h1>ZARQ Yield Risk</h1>
    <p>Template not found. Place zarq_yield_template.html in agentindex/templates/</p>
    </body></html>"""
