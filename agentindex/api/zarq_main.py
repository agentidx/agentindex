"""
ZARQ standalone FastAPI entry-point.

Used by the dedicated zarq-hel-1 host (Sprint 3, 2026-05-07). Mounts only the
ZARQ-relevant routers and pages from agentindex.crypto.* + the top-level
zarq_dashboard / zarq_docs modules.

Skips:
  * Nerq routers (badge, multi_jurisdiction, github_app, rating-aggregator, etc.)
  * Nerq middleware (BotRateLimitMiddleware, PageCacheMiddleware,
    ReturningVisitorBanner, OldDomainRedirect, AnalyticsMiddleware)
  * Nerq sitemap generator (zarq_machine_discovery)
  * Nerq blog publisher (auto_publisher)

The Mac-hosted agentindex.api.discovery:app continues to serve nerq.ai +
zarq.ai during the dual-running period (Sprints 3-6). Cutover (Sprint 6)
flips zarq.ai DNS to zarq-hel-1; Sprint 7 removes ZARQ routes from
discovery.py once stable.

Run: uvicorn agentindex.api.zarq_main:app --host 127.0.0.1 --port 8000 --workers 4
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

logger = logging.getLogger("zarq")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [zarq] %(message)s")

app = FastAPI(
    title="ZARQ",
    description="Crypto risk intelligence API — Trust Scores, NDD distress signals, crash prediction, contagion analysis.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "service": "zarq", "version": "0.1.0"}


# ── ZARQ host-router middleware ────────────────────────────────────
# Filters requests on Host header. zarq.ai → ZARQ landing/dashboard,
# everything else → passes through to the routers below.
from agentindex.api.zarq_router import ZarqRouter
app.add_middleware(ZarqRouter)


# ── SEO + page mounts ──────────────────────────────────────────────
# Each mount_*-function registers its own @app.get handlers.
def _safe_mount(label: str, fn):
    try:
        fn(app)
        logger.info(f"mounted: {label}")
    except Exception as e:
        logger.warning(f"mount failed: {label} ({e})")


from agentindex.crypto.crypto_seo_pages import (
    mount_crypto_pages,
    mount_paper_trading_page,
    mount_agent_intelligence_page,
    mount_methodology_page,
    mount_vitality_methodology_page,
    mount_sitemap_pages,
    mount_track_record_page,
    mount_api_docs_page,
    mount_alerts_page,
    mount_whitepaper_page,
    mount_compare_pages,
)

_safe_mount("crypto_pages", mount_crypto_pages)
_safe_mount("paper_trading_page", mount_paper_trading_page)
_safe_mount("agent_intelligence_page", mount_agent_intelligence_page)
_safe_mount("methodology_page", mount_methodology_page)
_safe_mount("vitality_methodology_page", mount_vitality_methodology_page)
_safe_mount("sitemap_pages", mount_sitemap_pages)
_safe_mount("track_record_page", mount_track_record_page)
_safe_mount("api_docs_page", mount_api_docs_page)
_safe_mount("alerts_page", mount_alerts_page)
_safe_mount("whitepaper_page", mount_whitepaper_page)
_safe_mount("compare_pages", mount_compare_pages)

from agentindex.crypto.zarq_cascade_page import mount_cascade_page
_safe_mount("cascade_page", mount_cascade_page)

from agentindex.crypto.zarq_yield_page import mount_yield_page
_safe_mount("yield_page", mount_yield_page)

from agentindex.crypto.zarq_batch_api import mount_batch_api
_safe_mount("batch_api", mount_batch_api)

from agentindex.crypto.zarq_websocket_webhooks import mount_websocket_webhooks
_safe_mount("websocket_webhooks", mount_websocket_webhooks)

from agentindex.crypto.zarq_compare_pages import mount_zarq_compare_hub
_safe_mount("zarq_compare_hub", mount_zarq_compare_hub)

# NOTE: zarq_machine_discovery.mount_machine_discovery is INTENTIONALLY skipped.
# It generates sitemaps for nerq.ai (entity_lookup / software_registry / agents
# JOINs) and is a Nerq feature. ZARQ doesn't need it.


# ── API routers ────────────────────────────────────────────────────
def _safe_include(label: str, mod_path: str, attr: str):
    try:
        mod = __import__(mod_path, fromlist=[attr])
        app.include_router(getattr(mod, attr))
        logger.info(f"included: {label}")
    except Exception as e:
        logger.warning(f"include failed: {label} ({e})")


_safe_include("crypto_agents (router_agents)", "agentindex.crypto.crypto_agents_api", "router_agents")
_safe_include("zarq_check (router_check)", "agentindex.crypto.zarq_check_api", "router_check")
_safe_include("zarq_check (router_vitality)", "agentindex.crypto.zarq_check_api", "router_vitality")
_safe_include("zarq_scan (router_scan)", "agentindex.crypto.zarq_scan", "router_scan")
_safe_include("zarq_save_simulator (router_save_sim)", "agentindex.crypto.zarq_save_simulator", "router_save_sim")
_safe_include("crash_shield (router_crash_shield)", "agentindex.crash_shield", "router_crash_shield")
_safe_include("zarq_dashboard (router_dashboard)", "agentindex.zarq_dashboard", "router_dashboard")
_safe_include("zarq_docs (router_docs)", "agentindex.zarq_docs", "router_docs")
_safe_include("crypto_api_v2 (router_v1)", "agentindex.crypto.crypto_api_v2", "router_v1")
_safe_include("crypto_api_v3 (router_v3)", "agentindex.crypto.crypto_api_v3", "router_v3")


# Mount scan page (must come AFTER /scan-redirect handler in discovery.py;
# we don't need the redirect on zarq.ai-only host).
from agentindex.crypto.zarq_scan import mount_scan_page
_safe_mount("scan_page", mount_scan_page)


logger.info("ZARQ standalone app ready")
