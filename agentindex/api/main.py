"""Aggregated FastAPI app for the `agentindex.api.endpoints.*` surface.

Mounts the individual L4 endpoint routers (`/rating/{slug}.json` from
`endpoints.rating`, `/signals/{slug}.json` from `endpoints.signals`).
Tests and future modular deploys import `app` from here; the production
tree still serves everything through `agentindex.api.discovery` for now,
which pulls these same routers.
"""
from __future__ import annotations

from fastapi import FastAPI

from agentindex.api.endpoints.rating import router as rating_router
from agentindex.api.endpoints.signals import router as signals_router

app = FastAPI(
    title="Nerq L4 endpoints",
    description="Machine-readable JSON views for AI consumers.",
    openapi_url="/v1/openapi.json",
    docs_url=None,
    redoc_url=None,
)
app.include_router(rating_router)
app.include_router(signals_router)
