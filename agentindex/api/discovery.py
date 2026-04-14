"""
AgentIndex Discovery API

The core product: agents query this API to find other agents.
Machine-first. No UI. Pure protocol.
"""

import time
import logging
from datetime import datetime, date
import time as _time

# Stats cache
_stats_cache = {"data": None, "ts": 0}
_STATS_TTL = 3600  # 1 hour — stats queries are expensive on 5M+ rows
_health_cache = {"data": None, "ts": 0}
_HEALTH_TTL = 60
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import pathlib
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text, or_, and_
from agentindex.db.models import Agent, DiscoveryLog, SystemStatus, get_session
from agentindex.api.keys import register_key, validate_key, ApiKey
from agentindex.api.a2a import get_agent_card, handle_a2a_request
from agentindex.api.api_protection import setup_api_protection
import os
import uuid
import redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
import json
import gzip
import hashlib

# Semantic search (FAISS + sentence-transformers)
try:
    from agentindex.api.semantic import get_semantic_search
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False

logger = logging.getLogger("agentindex.api")

# Redis setup — connection pool with auto-reconnect + exponential backoff
_REDIS_RETRY = Retry(ExponentialBackoff(cap=30, base=0.5), retries=5)

_REDIS_POOL = redis.ConnectionPool(
    host='127.0.0.1',
    port=6379,
    db=0,
    max_connections=20,
    socket_timeout=5,
    socket_connect_timeout=5,
    retry_on_timeout=True,
    retry=_REDIS_RETRY,
    health_check_interval=30,
)

redis_client = redis.Redis(connection_pool=_REDIS_POOL)
try:
    redis_client.ping()
    CACHE_AVAILABLE = True
    logger.info("Redis cache connected (pool, max=20, retry=5)")
except Exception as e:
    CACHE_AVAILABLE = True  # Pool will auto-reconnect — don't permanently disable
    logger.warning(f"Redis not available at startup (will auto-reconnect): {e}")

app = FastAPI(
    title="ZARQ & Nerq",
    description="ZARQ: Crypto risk intelligence API — Trust Scores, NDD distress signals, crash prediction, contagion analysis. Nerq: The AI Asset Search Engine — 5M+ AI assets indexed & trust scored across 52 jurisdictions.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=None,  # Disabled: custom /openapi.json with A/B variant below
)

# ── Custom 404 page ──
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(404)
@app.exception_handler(StarletteHTTPException)
async def custom_404(request: Request, exc):
    if hasattr(exc, 'status_code') and exc.status_code != 404:
        return HTMLResponse(str(exc.detail), status_code=exc.status_code)
    from agentindex.nerq_design import nerq_head, NERQ_FOOTER
    _h = nerq_head("Page Not Found — Nerq", "The page you're looking for doesn't exist.", "https://nerq.ai/")
    return HTMLResponse(f"""{_h}
<main class="container" style="padding:60px 20px;text-align:center">
<h1 style="font-size:3rem;color:#e2e8f0">404</h1>
<p style="font-size:18px;color:#64748b;margin:12px 0 24px">This page doesn't exist.</p>
<form action="/search" method="get" style="margin:20px auto;max-width:400px"><input type="text" name="q" placeholder="Search Nerq..." style="width:100%;padding:12px;font-size:16px;border:2px solid #e2e8f0;border-radius:8px"></form>
<div style="margin-top:24px"><a href="/" style="margin:0 12px">Home</a><a href="/best" style="margin:0 12px">Rankings</a><a href="/safe" style="margin:0 12px">Safety Reports</a></div>
</main>{NERQ_FOOTER}</body></html>""", status_code=404)

# ── Bot rate limiter (Meta crawlers hitting 287 req/sec) ──────────
from collections import defaultdict as _rl_dd
_bot_request_counts: dict[str, list[float]] = _rl_dd(list)
_BOT_RATE_LIMITS = {
    "meta-externalagent": 1,   # max 1 req/sec (was 287, then 2)
    "meta-webindexer": 1,
    "semrushbot": 3,
    "mj12bot": 3,
    "dataforseobot": 2,
    "amazonbot": 3,
    "yandexbot": 3,
}

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

_blocked_ips_cache = {"data": {}, "ts": 0}
_BLOCK_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "blocked_ips.json")

import json as _json_mod

class BotRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Fix HEAD→404: convert HEAD to GET internally so routes match
        # (StaticFiles mount catches HEAD for non-existent files)
        is_head = request.method == "HEAD"
        if is_head:
            request.scope["method"] = "GET"

        # Check blocked IPs (refresh cache every 30s)
        now = time.time()
        if now - _blocked_ips_cache["ts"] > 30:
            try:
                if os.path.exists(_BLOCK_FILE):
                    with open(_BLOCK_FILE) as f:
                        _blocked_ips_cache["data"] = _json_mod.load(f)
                    _blocked_ips_cache["ts"] = now
            except Exception:
                pass

        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
        # Never block search engine IPs (Google, Bing) even if they're in the block list
        _SAFE_PREFIXES = ("66.249.", "64.233.", "72.14.", "74.125.", "209.85.", "216.239.",
                          "40.77.", "52.167.", "207.46.", "157.55.", "13.66.", "13.67.",
                          "199.16.156.", "199.16.157.",  # Twitter
                          "17.0.",  # Apple
                          )
        if client_ip in _blocked_ips_cache["data"] and not client_ip.startswith(_SAFE_PREFIXES):
            info = _blocked_ips_cache["data"][client_ip]
            if now < info.get("expires", 0):
                return StarletteResponse(content="Blocked", status_code=429, headers={"Retry-After": "3600"})

        # Bot rate limiting by user-agent
        ua = (request.headers.get("user-agent") or "").lower()
        # NEVER rate-limit search engines or AI bots
        _SAFE_UA = ("googlebot", "bingbot", "msnbot", "adidxbot", "bingpreview",
                     "claudebot", "claude-web", "anthropic",
                     "chatgpt-user", "oai-searchbot", "gptbot",
                     "perplexitybot", "yandexbot", "baiduspider", "duckduckbot",
                     "applebot", "slurp", "bytespider", "bytedance",
                     "facebot", "facebookexternalhit",
                     "meta-externalagent", "meta-externalfetcher", "meta-webindexer",
                     "twitterbot", "linkedinbot")
        if any(s in ua for s in _SAFE_UA) or client_ip.startswith(_SAFE_PREFIXES):
            return await call_next(request)
        for bot_sig, max_rps in _BOT_RATE_LIMITS.items():
            if bot_sig in ua:
                timestamps = _bot_request_counts[bot_sig]
                cutoff = now - 1.0
                while timestamps and timestamps[0] < cutoff:
                    timestamps.pop(0)
                if len(timestamps) >= max_rps:
                    return StarletteResponse(
                        content="Rate limited. Please respect Crawl-delay in robots.txt.",
                        status_code=429,
                        headers={"Retry-After": "10"}
                    )
                timestamps.append(now)
                break
        response = await call_next(request)
        # For HEAD requests, keep status/headers but strip body
        if is_head and hasattr(response, 'body'):
            response.body = b""
        return response

app.add_middleware(BotRateLimitMiddleware)


# ── Page Cache Middleware (Redis) ──────────────────────────
# Caches GET responses for cacheable paths. API/dashboard excluded.
class PageCacheMiddleware(BaseHTTPMiddleware):
    _NO_CACHE = ("/v1/", "/flywheel", "/dashboard", "/admin", "/ab-", "/openapi",
                  "/robots.txt", "/llms.txt", "/sitemap", "/internal/", "/my/",
                  "/citation-dashboard")
    _TTL = 14400  # 4 hours — pages rarely change, enrichment flushes cache
    _pool = None
    _backoff = 0
    _last_fail = 0.0

    @classmethod
    def _get_redis(cls):
        """Redis with exponential backoff — never permanently disabled."""
        import time as _t
        now = _t.time()

        # Respect backoff period
        if cls._backoff > 0 and now - cls._last_fail < cls._backoff:
            return None

        try:
            if cls._pool is None:
                cls._pool = redis.ConnectionPool(
                    host='127.0.0.1', port=6379, db=1,
                    max_connections=10,
                    socket_timeout=0.5,
                    socket_connect_timeout=0.5,
                    retry_on_timeout=True,
                    retry=_REDIS_RETRY,
                    health_check_interval=30,
                )
            r = redis.Redis(connection_pool=cls._pool)
            r.ping()
            cls._backoff = 0  # Reset on success
            return r
        except Exception:
            cls._last_fail = now
            cls._backoff = min((cls._backoff or 2.5) * 2, 300)  # 5s→10s→...max 5min
            return None

    async def dispatch(self, request: Request, call_next):
        if request.method not in ("GET", "HEAD"):
            return await call_next(request)

        path = request.url.path

        # Skip non-cacheable
        if any(path.startswith(p) for p in self._NO_CACHE):
            return await call_next(request)
        # Skip paths with functional query params (search, API); ignore tracking params
        if request.url.query:
            _func_params = {k for k in request.query_params if k not in (
                "ref", "utm_source", "utm_medium", "utm_campaign", "utm_content",
                "utm_term", "fbclid", "gclid", "msclkid", "twclid", "dclid",
            )}
            if _func_params:
                return await call_next(request)

        r = self._get_redis()
        if not r:
            return await call_next(request)

        cache_key = f"pc:{path}"

        # Path-aware CDN TTLs — scores change daily, not hourly
        if path.startswith(("/safe/", "/is-", "/review/", "/privacy/", "/who-owns/",
                            "/pros-cons/", "/what-is/", "/badge/", "/mcp/")):
            _smaxage = 86400   # 24h — entity pages
        elif path.startswith(("/best/", "/alternatives/", "/compare/", "/guide/")):
            _smaxage = 86400   # 24h — ranking pages
        elif path.startswith(("/sitemap",)):
            _smaxage = 86400   # 24h — sitemaps
        elif path == "/":
            _smaxage = 3600    # 1h — homepage
        else:
            _smaxage = 43200   # 12h — everything else
        # NOTE (M4b Step 7): Cloudflare Browser Cache TTL override
        # rewrites max-age=300 to max-age=14400 (4h) at the edge.
        # The 300 value here is effectively dead code for responses
        # served via Cloudflare. To change browser cache time, update
        # the Browser Cache TTL setting in Cloudflare dashboard, not
        # this line. See docs/status/leverage-sprint-day-2-m4b-audit.md
        # Step 7 for investigation details.
        _cc = f"public, max-age=300, s-maxage={_smaxage}, stale-while-revalidate=86400"
        _cdn_cc = f"public, max-age={_smaxage}, stale-while-revalidate=86400"

        try:
            cached = r.get(cache_key)
            if cached:
                # ETag: content-hash based. Applebot and other crawlers
                # can send If-None-Match to skip re-download on cache hit.
                _etag = f'"{hashlib.md5(cached).hexdigest()}"'
                _client_etag = request.headers.get("if-none-match", "")
                if _client_etag == _etag:
                    return StarletteResponse(
                        content=b"",
                        status_code=304,
                        headers={
                            "ETag": _etag,
                            "Cache-Control": _cc,
                            "CDN-Cache-Control": _cdn_cc,
                        }
                    )
                return StarletteResponse(
                    content=cached,
                    media_type="text/html; charset=utf-8",
                    headers={
                        "X-Cache": "HIT",
                        "ETag": _etag,
                        "Cache-Control": _cc,
                        "CDN-Cache-Control": _cdn_cc,
                    }
                )
        except Exception:
            return await call_next(request)

        response = await call_next(request)

        if response.status_code == 200 and hasattr(response, 'body_iterator'):
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            try:
                if len(body) < 200_000:  # Don't cache huge pages
                    r.setex(cache_key, self._TTL, body)
            except Exception:
                pass
            # ETag from content hash for MISS response
            _etag = f'"{hashlib.md5(body).hexdigest()}"'
            return StarletteResponse(
                content=body,
                status_code=200,
                media_type=response.media_type or "text/html; charset=utf-8",
                headers={
                    "X-Cache": "MISS",
                    "ETag": _etag,
                    "Cache-Control": _cc,
                    "CDN-Cache-Control": _cdn_cc,
                }
            )

        return response


app.add_middleware(PageCacheMiddleware)


# A/B variant openapi.json
@app.get("/openapi.json", include_in_schema=False)
def ab_openapi_json(request: Request):
    import copy
    from fastapi.openapi.utils import get_openapi
    if not hasattr(app, "_cached_openapi"):
        app._cached_openapi = get_openapi(
            title=app.title, version=app.version, description=app.description,
            routes=app.routes,
        )
    schema = copy.deepcopy(app._cached_openapi)
    host = request.headers.get("host", "")
    forced = request.query_params.get("variant", "").upper()
    if forced in ("A", "B", "C", "D"):
        from agentindex.ab_test import get_agent_description
        schema["info"]["description"] = get_agent_description(forced)
    else:
        from agentindex.ab_test import get_variant, get_agent_description, _get_ip
        ip = _get_ip(request)
        variant = get_variant(ip)
        schema["info"]["description"] = get_agent_description(variant)
    if "nerq" in host:
        schema["info"]["title"] = "Nerq — Is It Safe? API"
    return schema

# Rate limiting state (in-memory, simple)
rate_limit_store: dict = {}
RATE_LIMIT_PER_HOUR = int(os.getenv("API_RATE_LIMIT_PER_HOUR", "100"))
MAX_RESULTS = int(os.getenv("API_RESULTS_PER_REQUEST", "10"))

# --- Models ---

class DiscoverRequest(BaseModel):
    """What an agent sends to find other agents."""
    need: str = Field(..., description="Natural language description of what you need")
    category: Optional[str] = Field(None, description="Filter by category")
    protocols: Optional[list[str]] = Field(None, description="Required protocols (mcp, a2a, rest)")
    min_quality: Optional[float] = Field(0.0, description="Minimum trust score 0-100")
    max_results: Optional[int] = Field(10, description="Max results (capped at 10)")

class DiscoverResponse(BaseModel):
    """What we return."""
    results: list[dict]
    total_matching: int
    index_size: int
    protocol: str = "agentindex/v1"

class AgentDetailResponse(BaseModel):
    """Detailed info about a single agent."""
    agent: dict

class StatsResponse(BaseModel):
    """System statistics."""
    total_agents: int
    active_agents: int
    categories: dict
    sources: dict
    protocols: dict
    last_crawl: Optional[str]


# --- Rate Limiting ---

def check_rate_limit(request: Request):
    """Simple IP-based rate limiting. Safe bots (Google, Bing, AI bots) are exempt."""
    # Skip rate limiting for search engines and AI bots
    ua = (request.headers.get("user-agent") or "").lower()
    _SAFE_UA_RL = ("googlebot", "bingbot", "msnbot", "adidxbot", "bingpreview",
                   "claudebot", "claude-web", "anthropic",
                   "chatgpt-user", "oai-searchbot", "gptbot",
                   "perplexitybot", "yandexbot", "baiduspider", "duckduckbot",
                   "applebot", "slurp", "bytespider", "bytedance",
                   "facebot", "facebookexternalhit",
                   "meta-externalagent", "meta-externalfetcher", "meta-webindexer",
                   "twitterbot", "linkedinbot")
    _SAFE_IP_RL = ("66.249.", "64.233.", "72.14.", "74.125.", "209.85.", "216.239.",
                   "40.77.", "52.167.", "207.46.", "157.55.", "13.66.", "13.67.")
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    if any(s in ua for s in _SAFE_UA_RL) or client_ip.startswith(_SAFE_IP_RL):
        return  # Safe bot — no rate limit

    now = time.time()
    hour_ago = now - 3600

    # Clean old entries
    if client_ip in rate_limit_store:
        rate_limit_store[client_ip] = [
            t for t in rate_limit_store[client_ip] if t > hour_ago
        ]
    else:
        rate_limit_store[client_ip] = []

    # Check limit
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "limit": RATE_LIMIT_PER_HOUR,
                "retry_after_seconds": 3600,
            }
        )

    rate_limit_store[client_ip].append(now)


# --- Endpoints ---

@app.get("/search", response_class=HTMLResponse)
async def search_page(q: str = ""):
    """HTML search results page."""
    from agentindex.nerq_design import nerq_head, NERQ_FOOTER
    import html as _h
    if not q or len(q) < 2:
        _head = nerq_head("Search — Nerq", "Search 2.5M+ software packages, apps, and tools for trust scores.", "https://nerq.ai/search")
        return HTMLResponse(f"""{_head}
<main class="container" style="padding:40px 20px"><h1>Search Nerq</h1>
<form action="/search" method="get" style="margin:20px 0"><input type="text" name="q" placeholder="Search: express, NordVPN, TikTok..." style="width:100%;max-width:500px;padding:12px;font-size:16px;border:2px solid #e2e8f0;border-radius:8px" autofocus></form>
<p style="color:#64748b">Search 2.5M+ entities across npm, PyPI, Chrome, WordPress, and 11 more registries.</p>
</main>{NERQ_FOOTER}</body></html>""")

    session = get_session()
    try:
        session.execute(text("SET LOCAL statement_timeout = '3s'"))
        rows = session.execute(text("""
            SELECT name, slug, registry, trust_score, trust_grade, LEFT(description, 120) as desc
            FROM software_registry
            WHERE (lower(name) LIKE lower(:pat) OR lower(slug) LIKE lower(:pat))
              AND trust_score IS NOT NULL AND trust_score >= 30
            ORDER BY trust_score DESC LIMIT 30
        """), {"pat": f"%{q}%"}).fetchall()
    finally:
        session.close()

    results_html = ""
    for r in rows:
        _s = f"{r[3]:.0f}" if r[3] else "?"
        results_html += f'<div style="padding:12px 0;border-bottom:1px solid #f1f5f9"><a href="/safe/{_h.escape(r[1])}" style="font-size:16px;font-weight:600">{_h.escape(r[0])}</a> <span style="color:#64748b;font-size:13px">{_h.escape(r[2] or "")}</span> <span style="font-weight:600;color:#0d9488">{_s}/100</span> <span style="font-size:12px;padding:2px 6px;background:#f0fdf4;border-radius:4px">{_h.escape(r[4] or "")}</span><div style="font-size:14px;color:#64748b;margin-top:4px">{_h.escape(r[5] or "")}</div></div>'

    _head = nerq_head(f'Search "{_h.escape(q)}" — Nerq', f"Search results for {q} — trust scores and safety analysis.", f"https://nerq.ai/search?q={_h.escape(q)}")
    return HTMLResponse(f"""{_head}
<main class="container" style="padding:20px">
<form action="/search" method="get" style="margin:12px 0"><input type="text" name="q" value="{_h.escape(q)}" style="width:100%;max-width:500px;padding:12px;font-size:16px;border:2px solid #e2e8f0;border-radius:8px"></form>
<p style="color:#64748b;margin-bottom:16px">{len(rows)} results for "{_h.escape(q)}"</p>
{results_html}
{f'<p style="margin-top:20px;color:#94a3b8">Showing top {len(rows)} results by trust score.</p>' if rows else '<p>No results found. Try a different search term.</p>'}
</main>{NERQ_FOOTER}</body></html>""")

@app.get("/contact", response_class=HTMLResponse)
async def contact_page():
    from agentindex.nerq_design import nerq_head, NERQ_FOOTER
    _head = nerq_head("Contact — Nerq", "Contact Nerq for questions about trust scores, API access, or partnerships.", "https://nerq.ai/contact")
    return HTMLResponse(f"""{_head}
<main class="container" style="padding:40px 20px;max-width:640px">
<h1>Contact Nerq</h1>
<table style="margin:20px 0">
<tr><td style="color:#64748b;width:140px">Email</td><td><a href="mailto:anders@nerq.ai">anders@nerq.ai</a></td></tr>
<tr><td style="color:#64748b">Founded by</td><td>Anders Nilsson</td></tr>
<tr><td style="color:#64748b">Location</td><td>Sweden</td></tr>
<tr><td style="color:#64748b">API docs</td><td><a href="/nerq/docs">nerq.ai/nerq/docs</a></td></tr>
</table>
<p style="font-size:14px;color:#64748b">For API questions, badge partnerships, or data inquiries — email is the fastest way to reach us.</p>
</main>{NERQ_FOOTER}</body></html>""")

@app.get("/v1/pool-status")
def pool_status():
    """Connection pool diagnostics — instant, no DB query."""
    try:
        from agentindex.db.models import get_engine
        _e = get_engine()
        _p = _e.pool
        return {
            "pool_size": _p.size(),
            "checked_out": _p.checkedout(),
            "overflow": _p.overflow(),
            "checkedin": _p.checkedin(),
            "pool_timeout": 5,
            "pool_recycle": 300,
        }
    except Exception as e:
        return {"error": str(e)}

# ── 301 Redirect /agent/ → /safe/ (was 410 — redirect preserves crawl budget) ──
@app.get("/agent/{path:path}")
async def agent_redirect(path: str):
    # Strip any UUID-like paths, keep just the last segment as slug
    slug = path.rstrip("/").split("/")[-1] if "/" in path else path
    from starlette.responses import RedirectResponse
    return RedirectResponse(url=f"/safe/{slug}", status_code=301)

# Sprint N0: Nerq Product APIs — MUST be mounted before /v1/agent/{agent_id}
from agentindex.nerq_api import router_nerq
app.include_router(router_nerq)

# Weekly Signal + Verified — must be before /v1/agent/{agent_id} catch-all
from agentindex.weekly_signal import router_weekly
app.include_router(router_weekly)
from agentindex.verified_api import router_verified
app.include_router(router_verified)

# GitHub App webhook
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "nerq-github-app"))
from github_app import router as github_app_router
app.include_router(github_app_router)

from starlette.middleware.base import BaseHTTPMiddleware
from agentindex.analytics import AnalyticsMiddleware, render_dashboard
from starlette.responses import RedirectResponse as _RR

# === ZARQ.AI ROUTING ===
from agentindex.api.zarq_router import ZarqRouter

class OldDomainRedirect(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        host = request.headers.get("host", "")
        if "agentcrawl.dev" in host:
            target = f"https://nerq.ai{request.url.path}"
            if request.url.query:
                target += f"?{request.url.query}"
            return _RR(url=target, status_code=301)
        return await call_next(request)



from agentindex.returning_banner import ReturningVisitorBanner
app.add_middleware(ReturningVisitorBanner)
app.add_middleware(OldDomainRedirect)
app.add_middleware(ZarqRouter)
app.add_middleware(AnalyticsMiddleware)
setup_api_protection(app)

# CORS: use a simple after-response hook to avoid BaseHTTPMiddleware body conflicts
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        from starlette.responses import Response as StarletteResponse
        return StarletteResponse(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-Source, Authorization, Cache-Control",
                "Access-Control-Max-Age": "86400",
            },
        )
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Source, Authorization"
    # BaseHTTPMiddleware wraps response bodies in streaming iterators,
    # making the original Content-Length stale. Remove it so the response
    # uses chunked transfer encoding instead (fixes Cloudflare 520 errors).
    if "content-length" in response.headers:
        del response.headers["content-length"]
    # ── Cache-Control for Cloudflare edge caching ──
    if request.method == "GET" and request.url.path.startswith("/static/") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    if request.method == "GET" and "cache-control" not in response.headers:
        path = request.url.path
        ct = response.headers.get("content-type", "")
        if "text/html" in ct:
            if path == "/":
                response.headers["Cache-Control"] = "public, s-maxage=3600, max-age=300, stale-while-revalidate=86400"
                response.headers["CDN-Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
            elif path.startswith(("/safe/", "/is-", "/review/", "/privacy/", "/who-owns/",
                                  "/pros-cons/", "/what-is/", "/badge/", "/mcp/",
                                  "/best/", "/alternatives/", "/compare/", "/guide/",
                                  "/apps", "/npm", "/pypi", "/crates", "/nuget",
                                  "/extensions", "/vpns", "/games", "/websites",
                                  "/wordpress-plugins", "/guides", "/check-website",
                                  "/kya", "/crypto")):
                response.headers["Cache-Control"] = "public, s-maxage=86400, max-age=300, stale-while-revalidate=86400"
                response.headers["CDN-Cache-Control"] = "public, max-age=86400, stale-while-revalidate=86400"
            elif path.startswith(("/search", "/discover")):
                response.headers["Cache-Control"] = "no-cache"
        elif "application/json" in ct and path.startswith("/v1/"):
            if path.startswith("/v1/preflight"):
                response.headers["Cache-Control"] = "public, s-maxage=3600, max-age=0"
                response.headers["CDN-Cache-Control"] = "public, max-age=3600"
            else:
                response.headers["Cache-Control"] = "public, s-maxage=300, max-age=0"
                response.headers["CDN-Cache-Control"] = "public, max-age=300"
    return response

# Sprint 0 Track E: Observability
from agentindex.observability import mount_observability
mount_observability(app)

from agentindex.reach_dashboard import mount_reach_dashboard
mount_reach_dashboard(app)

@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy():
    from agentindex.pages_i18n import render_privacy
    return render_privacy("en")

@app.get("/terms", response_class=HTMLResponse)
def terms_page():
    from agentindex.pages_i18n import render_terms
    return render_terms("en")


@app.get("/health-disclaimer", response_class=HTMLResponse)
def health_disclaimer():
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Health, Nutrition &amp; Cosmetic Safety Disclaimer — Nerq</title>
<meta name="description" content="Nerq health disclaimer. Information on food additives, supplements, and cosmetic ingredients is for educational purposes only. Not medical advice.">
<link rel="canonical" href="https://nerq.ai/health-disclaimer">
<style>body{font-family:-apple-system,system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 20px;color:#1f2937;line-height:1.7}
h1{font-size:24px}h2{font-size:18px;margin-top:28px;color:#0f172a}a{color:#3b82f6}ul{margin:8px 0 16px 20px}
.notice{background:#fff8e1;border-left:4px solid #ff9800;padding:16px;margin:20px 0;border-radius:4px;font-size:15px}</style></head><body>
<p><a href="/">← Nerq</a></p>
<h1>Health, Nutrition &amp; Cosmetic Safety Information Disclaimer</h1>
<p><em>Last updated: March 24, 2026</em></p>

<div class="notice"><strong>All information on this website is provided for educational and informational purposes only.</strong> Nothing on this website constitutes medical advice, diagnosis, treatment, nutritional counseling, or a recommendation to use or avoid any substance.</div>

<h2>General Information</h2>
<p>Nerq provides trust scores and safety analysis for food additives, dietary supplements, cosmetic ingredients, and other products. This information is compiled from publicly available sources including government regulatory agencies, peer-reviewed scientific literature, and official databases.</p>

<h2>No Doctor-Patient Relationship</h2>
<p>Use of this website does not create a doctor-patient, therapist-patient, or any other professional healthcare relationship. Trust scores are algorithmic assessments based on publicly available data and should not be interpreted as clinical evaluations.</p>

<h2>Consult a Professional</h2>
<ul>
<li><strong>Food ingredients:</strong> Consult a registered dietitian, nutritionist, or physician</li>
<li><strong>Dietary supplements:</strong> Consult your physician or pharmacist, especially regarding drug interactions and dosages</li>
<li><strong>Cosmetic ingredients:</strong> Consult a board-certified dermatologist, especially with skin conditions or during pregnancy</li>
</ul>
<p><strong>Never disregard professional medical advice or delay seeking it because of information on this website.</strong></p>

<h2>About Our Trust Scores</h2>
<p>Nerq Trust Scores aggregate data from: FDA (GRAS, food additive status), EFSA (scientific opinions), EU CosIng database, EWG (ingredient hazard data), NIH Office of Dietary Supplements, WHO/IARC (carcinogenicity classifications), and peer-reviewed journals.</p>
<p>A high score does not guarantee safety for all people in all circumstances. A low score does not necessarily mean a substance is dangerous. Scores reflect the weight of available evidence and regulatory status as of the date indicated.</p>

<h2>Dietary Supplements</h2>
<p><strong>Dietary supplements are not approved by the FDA to diagnose, treat, cure, or prevent any disease.</strong> Supplements can interact with medications, may have side effects, and are not appropriate for all individuals.</p>

<h2>Cosmetic Ingredients</h2>
<p>Individual skin reactions vary significantly. Concentrations, formulations, pH levels, and ingredient combinations all affect safety. Patch testing is recommended before using new active ingredients.</p>

<h2>Regulatory Jurisdictions</h2>
<p>Regulatory status varies between jurisdictions. A substance approved by the FDA may be banned by EFSA and vice versa. Always check regulations applicable to your location.</p>

<h2>Limitation of Liability</h2>
<p>To the fullest extent permitted by law, Nerq shall not be liable for any damages arising from use of or reliance on information on this website, including damages from dietary decisions, supplement use, or skincare routines.</p>

<h2>Not an Endorsement</h2>
<p>Mention of any product, brand, or substance does not constitute an endorsement. Nerq does not sell, manufacture, or distribute any food products, supplements, or cosmetics.</p>

<p style="margin-top:32px;color:#6b7280;font-size:14px"><a href="/">Back to Nerq</a> · <a href="/privacy">Privacy Policy</a></p>
</body></html>"""


@app.get("/v1/health")
@app.head("/v1/health")
@app.get("/health")
def health():
    """Health check — pool-independent, never blocks on DB."""
    # Always respond instantly with cached data
    if _health_cache["data"] and (_time.time() - _health_cache["ts"]) < _HEALTH_TTL:
        return _health_cache["data"]

    # Try DB with a VERY short timeout and its own connection (not from pool)
    _agents = _health_cache.get("data", {}).get("agents", 0) if _health_cache.get("data") else 0
    try:
        import psycopg2
        _db_url = os.environ.get("DATABASE_URL", "postgresql://localhost/agentindex")
        _conn = psycopg2.connect(_db_url, connect_timeout=2, options="-c statement_timeout=1000")
        _cur = _conn.cursor()
        _cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'agents'")
        _agents = max(_cur.fetchone()[0] or 0, 0)
        _cur.close()
        _conn.close()
        _db_status = "ok"
    except Exception:
        _db_status = "degraded"

    result = {
        "status": _db_status,
        "timestamp": datetime.utcnow().isoformat(),
        "agents": _agents,
        "active_agents": _agents,
    }
    _health_cache["data"] = result
    _health_cache["ts"] = _time.time()
    return result


class RegisterRequest(BaseModel):
    agent_name: Optional[str] = None
    agent_url: Optional[str] = None
    contact: Optional[str] = None

@app.post("/v1/register")
def register(req: RegisterRequest):
    """
    Register for a free API key. Self-service, no approval needed.
    Returns key once — store it securely.
    """
    result = register_key(
        agent_name=req.agent_name,
        agent_url=req.agent_url,
        contact=req.contact,
    )
    return result


# Cache functions
def generate_cache_key(req: DiscoverRequest) -> str:
    """Generate cache key for discovery request"""
    key_data = f"{req.need}:{req.max_results}:{req.category}:{req.min_quality}:{req.protocols}"
    return hashlib.md5(key_data.encode()).hexdigest()

def get_cached_result(cache_key: str) -> Optional[dict]:
    """Get cached discovery result"""
    try:
        cached = redis_client.get(f"discover:{cache_key}")
        if cached:
            return json.loads(gzip.decompress(cached).decode())
    except Exception as e:
        logger.warning(f"Cache get error: {e}")
    return None

def cache_result(cache_key: str, result: dict, ttl: int = 300):
    """Cache discovery result with compression"""
    try:
        compressed = gzip.compress(json.dumps(result).encode())
        redis_client.setex(f"discover:{cache_key}", ttl, compressed)
    except Exception as e:
        logger.warning(f"Cache set error: {e}")


@app.post("/v1/discover", response_model=DiscoverResponse)
def discover(req: DiscoverRequest, request: Request, _=Depends(check_rate_limit)):
    """
    Core discovery endpoint.
    An agent describes what it needs, we return matching agents.
    """
    start_time = time.time()
    
    # Generate cache key for this request
    cache_key = generate_cache_key(req)
    
    # Try cache first
    if CACHE_AVAILABLE:
        cached_result = get_cached_result(cache_key)
        if cached_result:
            cached_result["query_time_ms"] = int((time.time() - start_time) * 1000)
            cached_result["cached"] = True
            return cached_result
    
    session = get_session()
    session.execute(text("SET LOCAL statement_timeout = '3s'"))
    session.execute(text("SET LOCAL work_mem = '2MB'"))

    # Cap max results
    limit = min(req.max_results or 10, MAX_RESULTS)

    # Build query
    # Convert min_quality to trust_score scale (0-100) if provided
    min_trust = (req.min_quality or 0.0)
    if min_trust <= 1.0 and min_trust > 0:
        min_trust = min_trust * 100  # Convert old scale to new scale
    
    query = select(Agent).where(
        Agent.is_active == True,
        Agent.crawl_status.in_(["parsed", "classified", "ranked"])
    )
    
    # Only filter by trust score if we have trust scores
    if min_trust > 0:
        query = query.where(
            text("(trust_score IS NULL OR trust_score >= :min_trust)").bindparams(min_trust=min_trust)
        )

    # Category filter
    if req.category:
        query = query.where(Agent.category == req.category)

    # Protocol filter
    if req.protocols:
        query = query.where(Agent.protocols.overlap(req.protocols))

    # --- Semantic search (primary) ---
    fts_results = []
    search_method = "fts"

    if SEMANTIC_AVAILABLE:
        try:
            sem = get_semantic_search()
            if sem.index is not None and sem.index_size > 0:
                # Get more candidates than needed, then filter
                sem_results = sem.search(req.need, top_k=limit * 5)
                if sem_results:
                    search_method = "semantic"
                    candidate_ids = [r["agent_id"] for r in sem_results]
                    sem_scores = {r["agent_id"]: r["score"] for r in sem_results}

                    # Phase 1: Lightweight scoring (ID + trust_score only — no JSON blobs)
                    _id_uuids = [uuid.UUID(aid) for aid in candidate_ids]
                    _score_rows = session.execute(text("""
                        SELECT id::text, COALESCE(trust_score, 0) as ts, COALESCE(compliance_score, 50) as cs,
                               COALESCE(risk_class, '') as rc
                        FROM entity_lookup WHERE id = ANY(:ids) AND is_active = true
                          AND crawl_status IN ('parsed', 'classified', 'ranked')
                    """), {"ids": _id_uuids}).fetchall()
                    _score_map = {str(r[0]): (r[1], r[2], r[3]) for r in _score_rows}

                    # Score and pick top N
                    scored = []
                    for aid in candidate_ids:
                        if aid in _score_map:
                            ts, cs, rc = _score_map[aid]
                            trust_n = ts / 100.0
                            comp_n = cs / 100.0
                            risk_p = 0.3 if rc in ('high', 'unacceptable') else 0.0
                            combined = 0.5 * sem_scores[aid] + 0.25 * trust_n + 0.25 * comp_n - risk_p
                            scored.append((combined, aid))
                    scored.sort(key=lambda x: x[0], reverse=True)
                    top_ids = [aid for _, aid in scored[:limit]]

                    # Phase 2: Full fetch ONLY for top results (small set)
                    if top_ids:
                        fts_results = session.execute(
                            select(Agent).where(Agent.id.in_([uuid.UUID(a) for a in top_ids]))
                        ).scalars().all()
                        # Re-order to match scoring
                        _id_order = {aid: i for i, aid in enumerate(top_ids)}
                        fts_results.sort(key=lambda a: _id_order.get(str(a.id), 999))
        except Exception as e:
            logger.error(f"Semantic search failed, falling back to FTS: {e}")

    # --- Full-text search (fallback) ---
    if not fts_results:
        search_method = "fts"
        # Phase 1: Get IDs via lightweight FTS (no JSONB columns)
        _fts_ids = session.execute(text("""
            SELECT id FROM agents WHERE is_active = true
              AND crawl_status IN ('parsed', 'classified', 'ranked')
              AND to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, '') || ' ' || coalesce(category, ''))
                  @@ plainto_tsquery('english', :search)
            ORDER BY COALESCE(trust_score, quality_score * 100, 0) DESC
            LIMIT :lim
        """), {"search": req.need, "lim": limit}).fetchall()
        if _fts_ids:
            # Phase 2: Full fetch only for matched IDs
            fts_results = session.execute(
                select(Agent).where(Agent.id.in_([r[0] for r in _fts_ids]))
            ).scalars().all()

        # Broader fallback — two-phase via entity_lookup (2.9GB) instead of agents (17GB)
        if not fts_results:
            session.execute(text("SET LOCAL statement_timeout = '3s'"))
            _search_word = req.need.split()[0] if req.need.split() else req.need
            _broader_sql = """
                SELECT id FROM entity_lookup
                WHERE is_active = true
                  AND crawl_status IN ('parsed', 'classified', 'ranked')
                  AND (name_lower LIKE lower(:pat) OR lower(description) LIKE lower(:pat))
            """
            _params = {"pat": f"%{_search_word}%"}
            if min_trust > 0:
                _broader_sql += " AND (trust_score IS NULL OR trust_score >= :min_trust)"
                _params["min_trust"] = min_trust
            if req.category:
                _broader_sql += " AND category = :cat"
                _params["cat"] = req.category
            _broader_sql += " ORDER BY COALESCE(trust_score_v2, trust_score, 0) DESC LIMIT :lim"
            _params["lim"] = min(limit, 20)
            _broader_ids = session.execute(text(_broader_sql), _params).fetchall()
            if _broader_ids:
                fts_results = session.execute(
                    select(Agent).where(Agent.id.in_([r[0] for r in _broader_ids]))
                ).scalars().all()

    # Count total matching
    total_matching = len(fts_results)

    # Get index size (estimate — avoids full table scan on 4.9M rows)
    index_size = session.execute(
        text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'agents'")
    ).scalar() or 0

    # Build response
    results = [agent.to_discovery_response() for agent in fts_results]

    response_time = int((time.time() - start_time) * 1000)

    # Log discovery request (no identifying info)
    log_entry = DiscoveryLog(
        query={"need": req.need, "category": req.category, "protocols": req.protocols, "search_method": search_method},
        results_count=len(results),
        top_result_id=fts_results[0].id if fts_results else None,
        response_time_ms=response_time,
    )
    session.add(log_entry)
    session.commit()
    session.close()

    response = DiscoverResponse(
        results=results,
        total_matching=total_matching,
        index_size=index_size,
    )
    
    # Cache the result
    if CACHE_AVAILABLE and len(results) > 0:
        cache_result(cache_key, {
            "results": results,
            "total_matching": total_matching,
            "index_size": index_size,
        })
    
    return response


@app.get("/v1/agent/{agent_id}", response_model=AgentDetailResponse)
def get_agent(agent_id: str, request: Request, _=Depends(check_rate_limit)):
    """Get detailed information about a specific agent."""
    session = get_session()
    session.execute(text("SET LOCAL statement_timeout = '3s'"))
    session.execute(text("SET LOCAL work_mem = '2MB'"))

    try:
        uid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID format")

    agent = session.execute(
        select(Agent).where(Agent.id == uid, Agent.is_active == True)
    ).scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    result = agent.to_detail_response()
    session.close()

    return AgentDetailResponse(agent=result)


@app.get("/v1/stats", response_model=StatsResponse)
def stats():
    """Public statistics about the index (cached 5 min)."""
    if _stats_cache["data"] and (_time.time() - _stats_cache["ts"]) < _STATS_TTL:
        return _stats_cache["data"]
    
    session = get_session()

    # Use PG estimates for total counts (instant vs 10s+ COUNT(*))
    total_est = session.execute(
        text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'agents'")
    ).scalar() or 0
    total = max(total_est, 0)
    active = total  # estimate

    # Category distribution — SAMPLED to avoid full table scan on 4.9M rows
    cat_rows = session.execute(
        text("SELECT category, COUNT(*) FROM entity_lookup TABLESAMPLE SYSTEM(1) WHERE is_active = true GROUP BY category")
    ).all()
    # Scale up from 1% sample
    categories = {(row[0] or "unknown"): row[1] * 100 for row in cat_rows}

    # Source distribution — SAMPLED
    src_rows = session.execute(
        text("SELECT source, COUNT(*) FROM entity_lookup TABLESAMPLE SYSTEM(1) GROUP BY source")
    ).all()
    sources = {row[0]: row[1] * 100 for row in src_rows}

    # Protocol distribution — use LIMIT to avoid full table scan on 5M+ rows
    try:
        proto_rows = session.execute(
            text("SELECT proto, COUNT(*) as cnt FROM (SELECT unnest(protocols) as proto FROM entity_lookup WHERE protocols IS NOT NULL AND is_active = true LIMIT 100000) sub GROUP BY proto")
        ).all()
        protocol_counts = {row[0]: row[1] for row in proto_rows}
    except Exception:
        protocol_counts = {}

    session.close()

    result = StatsResponse(
        total_agents=total,
        active_agents=active,
        categories=categories,
        sources=sources,
        protocols=protocol_counts,
        last_crawl=datetime.utcnow().isoformat(),
    )
    _stats_cache["data"] = result
    _stats_cache["ts"] = _time.time()
    return result


# --- MCP-compatible endpoint ---

@app.post("/v1/mcp/discover")
def mcp_discover(request_body: dict, request: Request, _=Depends(check_rate_limit)):
    """
    MCP-compatible discovery endpoint.
    Accepts MCP tool call format and returns results.
    """
    # Extract need from various MCP formats
    need = (
        request_body.get("need") or
        request_body.get("query") or
        request_body.get("input", {}).get("need") or
        request_body.get("arguments", {}).get("need") or
        ""
    )

    if not need:
        raise HTTPException(status_code=400, detail="Missing 'need' parameter")

    # Delegate to main discover
    req = DiscoverRequest(need=need)
    return discover(req, request)


# --- A2A Protocol Endpoints ---

@app.get("/.well-known/agent-card.json")
@app.get("/.well-known/agent.json")
def agent_card(request: Request):
    """A2A Agent Card — discovery endpoint for the A2A protocol."""
    card = get_agent_card()
    # A/B test: vary description
    from agentindex.ab_test import get_variant, get_agent_description, _get_ip, _is_bot, _bot_name, log_ab_event
    ip = _get_ip(request)
    ua = request.headers.get("user-agent", "")
    forced = request.query_params.get("variant", "").upper()
    variant = forced if forced in ("A", "B", "C", "D") else get_variant(ip)
    is_bot = _is_bot(ua)
    log_ab_event(ip, variant, is_bot, _bot_name(ua) if is_bot else None,
                 "page_view", "/.well-known/agent.json", "")
    import copy
    card = copy.deepcopy(card) if isinstance(card, dict) else card
    if isinstance(card, dict):
        card["description"] = get_agent_description(variant)
        card["tagline"] = "Is it safe? — for any AI tool"
    return card


@app.get("/.well-known/ai-card.json")
def ai_card(request: Request):
    """Google Unified AI Card format."""
    from agentindex.ab_test import get_variant, get_agent_description, _get_ip
    ip = _get_ip(request)
    variant = get_variant(ip)
    return {
        "name": "Nerq",
        "description": get_agent_description(variant),
        "url": "https://nerq.ai",
        "version": "0.7.0",
        "provider": {"name": "Nerq", "url": "https://nerq.ai"},
        "capabilities": ["search", "trust_scoring", "preflight_check", "benchmarking", "due_diligence", "crypto_risk"],
        "endpoints": {
            "preflight": {
                "url": "https://nerq.ai/v1/preflight?target={agent_name}",
                "method": "GET",
                "description": "Preflight trust check — verify any agent or MCP server before interaction. Returns trust score, grade, risk level, and recommendation (PROCEED/CAUTION/DENY).",
                "parameters": {
                    "target": {"type": "string", "required": True, "description": "Agent or tool name to check"},
                    "caller": {"type": "string", "required": False, "description": "Calling agent name (optional, for bilateral trust)"},
                },
                "response_fields": ["target_trust", "target_grade", "recommendation", "interaction_risk", "details_url"],
            },
            "search": {
                "url": "https://nerq.ai/v1/agent/search?q={query}",
                "method": "GET",
                "description": "Semantic search across 204K+ agents & tools. Natural language queries matched via FAISS + sentence-transformers.",
            },
            "kya": {
                "url": "https://nerq.ai/v1/agent/kya/{name}",
                "method": "GET",
                "description": "Know Your Agent — full due diligence report on any agent. Includes trust history, capabilities, security audit status.",
            },
            "stats": {
                "url": "https://nerq.ai/v1/agent/stats",
                "method": "GET",
                "description": "Aggregate statistics: total agents indexed, category breakdown, trust distribution.",
            },
            "benchmark": {
                "url": "https://nerq.ai/v1/agent/benchmark/{category}",
                "method": "GET",
                "description": "Agent benchmarks per category: coding, security, finance, devops, etc.",
            },
            "badge": {
                "url": "https://nerq.ai/badge/{name}",
                "method": "GET",
                "description": "Trust badge SVG for any agent. Embed in READMEs and docs.",
            },
        },
        "authentication": {
            "type": "none",
            "note": "All endpoints are free and require no authentication. No API key needed.",
        },
        "rate_limits": {
            "default": "100 requests/hour per IP (free tier, no auth required)",
            "preflight": "No rate limit — designed for high-frequency agent-to-agent checks",
        },
        "trust_methodology": "https://nerq.ai/protocol",
        "documentation": "https://nerq.ai/nerq/docs",
        "openapi_spec": "https://nerq.ai/openapi.json",
        "llms_txt": "https://nerq.ai/llms.txt",
        "mcp_endpoint": "https://nerq.ai/mcp/sse",
        "a2a_endpoint": "https://nerq.ai/a2a",
        "contact": "api@zarq.ai",
    }


@app.get("/.well-known/mcp.json")
def mcp_card():
    """MCP Server Card for machine discovery."""
    from agentindex.mcp_sse_server import SERVER_CARD
    card = dict(SERVER_CARD)
    card["url"] = "https://nerq.ai/mcp/sse"
    card["documentation"] = "https://nerq.ai/nerq/docs#mcp"
    card["provider"] = {"name": "Nerq", "url": "https://nerq.ai"}
    return card


@app.get("/.well-known/ai-plugin.json")
async def ai_plugin_json():
    """OpenAI ChatGPT Plugin manifest."""
    return {
        "schema_version": "v1",
        "name_for_human": "Nerq Trust Check",
        "name_for_model": "nerq_trust",
        "description_for_human": "Is it safe? Trust scores for 7.5M+ apps, packages, extensions, websites, countries, and AI tools.",
        "description_for_model": "When a user asks if ANY software, app, package, extension, website, VPN, game, or country is safe, trustworthy, legit, or a scam, use this plugin. Works for: mobile apps (iOS/Android), npm/PyPI/Crates packages, Chrome/Firefox extensions, WordPress plugins, websites, VPN services, Steam games, AI tools, crypto tokens, and travel destinations. 7.5M+ entities across 26 registries. Returns trust_score (0-100), grade, verdict, and alternatives. Also handles: privacy analysis, kids safety, spyware checks, alternatives, comparisons.",
        "auth": {"type": "none"},
        "api": {"type": "openapi", "url": "https://nerq.ai/openapi-plugin.json"},
        "logo_url": "https://nerq.ai/static/nerq-logo-512.png",
        "contact_email": "anders@nerq.ai",
        "legal_info_url": "https://nerq.ai/privacy",
    }

@app.get("/openapi-plugin.json")
async def openapi_plugin_spec():
    """OpenAPI spec tailored for ChatGPT plugin consumption."""
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Nerq — Is It Safe?",
            "description": "Trust and safety intelligence for AI tools. Check any tool's trust score, CVEs, license, and safer alternatives. 5M+ assets indexed.",
            "version": "1.0.0"
        },
        "servers": [{"url": "https://nerq.ai"}],
        "paths": {
            "/v1/preflight": {
                "get": {
                    "operationId": "checkTrust",
                    "summary": "Check if an AI tool is safe. Returns trust score, grade, CVEs, license.",
                    "description": "Use when user asks 'is X safe?', 'should I use X?', 'is X trustworthy?'. Works for any AI tool, npm package, PyPI package, HuggingFace model, MCP server, or Docker container.",
                    "parameters": [{
                        "name": "target",
                        "in": "query",
                        "required": True,
                        "description": "Tool name, package name, or model identifier. Examples: 'langchain', 'cursor', 'meta-llama/Llama-3', 'postgres-mcp-server'",
                        "schema": {"type": "string"}
                    }],
                    "responses": {"200": {"description": "Trust check result with score, grade, CVEs, and recommendation"}}
                }
            },
            "/v1/best": {
                "get": {
                    "operationId": "getBestTools",
                    "summary": "Get the best/safest tools in a category, ranked by trust score.",
                    "description": "Use when user asks 'best X tools', 'safest X', 'what should I use for X?'",
                    "parameters": [
                        {"name": "category", "in": "query", "required": True,
                         "description": "Category name. Examples: 'agent-frameworks', 'mcp-servers', 'vector-databases', 'coding', 'security'",
                         "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "default": 10}}
                    ],
                    "responses": {"200": {"description": "Ranked list of tools with trust scores"}}
                }
            },
            "/v1/alternatives": {
                "get": {
                    "operationId": "getAlternatives",
                    "summary": "Find alternatives to any tool, ranked by trust score.",
                    "description": "Use when user asks 'alternatives to X', 'what can I use instead of X?'",
                    "parameters": [
                        {"name": "tool", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "default": 10}}
                    ],
                    "responses": {"200": {"description": "Original tool info plus ranked alternatives"}}
                }
            },
            "/v1/intelligence/predict/{tool}": {
                "get": {
                    "operationId": "getPrediction",
                    "summary": "Get adoption trajectory, fragility risk, and AI recommendation probability.",
                    "description": "Use when user asks 'will X survive?', 'is X growing or dying?', 'should I adopt X?'",
                    "parameters": [{"name": "tool", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Prediction with adoption phase, fragility, survival probability"}}
                }
            }
        }
    }


@app.post("/a2a")
async def a2a_endpoint(request: Request):
    """A2A JSON-RPC 2.0 endpoint for agent-to-agent communication."""
    return await handle_a2a_request(request)


@app.get("/v1/semantic/status")
def semantic_status():
    """Semantic search index status."""
    if SEMANTIC_AVAILABLE:
        sem = get_semantic_search()
        return sem.get_status()
    return {"status": "not_available"}



# === OpenClaw Compliance Layer ===
try:
    from agentindex.compliance.integration import mount_compliance
    mount_compliance(app)
    from agentindex.compliance.badge_api import router as badge_router
    app.include_router(badge_router)
    # Multi-jurisdiction API
    from agentindex.api.multi_jurisdiction import router as multi_jurisdiction_router
    app.include_router(multi_jurisdiction_router)
except Exception as e:
    import logging
    logging.getLogger("agentindex").warning(f"Compliance layer not loaded: {e}")
# === SEO Agent Pages ===
from agentindex.crypto.crypto_seo_pages import mount_crypto_pages
mount_crypto_pages(app)


# Sprint 3.0: Paper Trading Dashboard
from agentindex.crypto.crypto_seo_pages import mount_paper_trading_page, mount_agent_intelligence_page
mount_paper_trading_page(app)
mount_agent_intelligence_page(app)
from agentindex.crypto.zarq_cascade_page import mount_cascade_page
mount_cascade_page(app)

from agentindex.crypto.zarq_yield_page import mount_yield_page
mount_yield_page(app)

from agentindex.crypto.zarq_batch_api import mount_batch_api
mount_batch_api(app)
from agentindex.crypto.zarq_websocket_webhooks import mount_websocket_webhooks
mount_websocket_webhooks(app)
from agentindex.crypto.crypto_seo_pages import mount_methodology_page
mount_methodology_page(app)
from agentindex.crypto.crypto_seo_pages import mount_vitality_methodology_page
mount_vitality_methodology_page(app)
from agentindex.crypto.crypto_seo_pages import mount_sitemap_pages
mount_sitemap_pages(app)


# Sprint 3.0: Track Record Page
from agentindex.crypto.crypto_seo_pages import mount_track_record_page
mount_track_record_page(app)

from agentindex.crypto.crypto_seo_pages import mount_api_docs_page
mount_api_docs_page(app)

from agentindex.crypto.crypto_seo_pages import mount_alerts_page
mount_alerts_page(app)

# Machine-first discovery (robots.txt, llms.txt, ai-plugin.json)
from agentindex.crypto.zarq_machine_discovery import mount_machine_discovery
mount_machine_discovery(app)

from agentindex.crypto.crypto_seo_pages import mount_whitepaper_page
mount_whitepaper_page(app)
from agentindex.crypto.zarq_compare_pages import mount_zarq_compare_hub
mount_zarq_compare_hub(app)
from agentindex.crypto.crypto_seo_pages import mount_compare_pages
mount_compare_pages(app)
# Sprint 6: Agent crawling API endpoints
try:
    from agentindex.crypto.crypto_agents_api import router_agents
    app.include_router(router_agents)
    print("Sprint 6 agent endpoints loaded OK")
except Exception as e:
    print(f"Sprint 6 agent endpoints not loaded: {e}")

# Sprint 1: Zero-friction check endpoint
from agentindex.crypto.zarq_check_api import router_check, router_vitality
app.include_router(router_check)
app.include_router(router_vitality)

# Token scanner
from agentindex.crypto.zarq_scan import router_scan, mount_scan_page
app.include_router(router_scan)
mount_scan_page(app)

# Sprint 2: Save Simulator
from agentindex.crypto.zarq_save_simulator import router_save_sim
app.include_router(router_save_sim)

# Sprint 4: Crash Shield
from agentindex.crash_shield import router_crash_shield
app.include_router(router_crash_shield)

# ZARQ Operations Dashboard
from agentindex.zarq_dashboard import router_dashboard
app.include_router(router_dashboard)

# ZARQ API Documentation
from agentindex.zarq_docs import router_docs
app.include_router(router_docs)

@app.get("/zarq/doc")
async def zarq_doc_redirect():
    return _RR(url="/zarq/docs", status_code=301)

# Redirect common bot-probed pages to root (reduces 404 error rate)
@app.get("/favicon.ico")
async def favicon():
    from starlette.responses import Response as _Resp
    return _Resp(status_code=204)  # No content

# Press pages (host-aware: zarq.ai vs nerq.ai)
from agentindex.crypto.zarq_press_page import mount_press_pages
mount_press_pages(app)

# Redirect common 404 content gaps
app.add_api_route("/api", lambda: _RR(url="/nerq/docs", status_code=301), methods=["GET"])
app.add_api_route("/docs", lambda: _RR(url="/nerq/docs", status_code=301), methods=["GET"])
app.add_api_route("/ratings", lambda: _RR(url="/", status_code=301), methods=["GET"])
app.add_api_route("/protocol)", lambda: _RR(url="/protocol", status_code=301), methods=["GET"])
app.add_api_route("/protocol).", lambda: _RR(url="/protocol", status_code=301), methods=["GET"])

from agentindex.about_page import mount_about_page
mount_about_page(app)

from agentindex.flywheel_dashboard import mount_flywheel
mount_flywheel(app)

from agentindex.analytics_dashboard import mount_analytics_dashboard
mount_analytics_dashboard(app)

from agentindex.analytics_weekly import mount_analytics_weekly
mount_analytics_weekly(app)

from agentindex.citation_dashboard import mount_citation_dashboard
mount_citation_dashboard(app)

from agentindex.trust_score_page import mount_trust_score_page
mount_trust_score_page(app)

for _bot_path in ["/about-us", "/contact", "/contact-us", "/team", "/company", "/leadership"]:
    app.add_api_route(_bot_path, lambda: _RR(url="/about", status_code=301), methods=["GET"])

# RSS feed (must be before probe routes)
from agentindex.rss_feed import router_rss
app.include_router(router_rss)

# Return 204 for common bot probes that generate 404s (feeds, rss, wordpress, well-known)
def _no_content_204():
    from starlette.responses import Response as _Resp
    return _Resp(status_code=204)

for _probe_path in [
    "/feed", "/feed/", "/rss", "/rss/",
    "/blog/feed/", "/blog/rss/",
    "/feed/posts/default", "/articles/feed",
    "/xmlrpc.php", "/.well-known/traffic-advice",
]:
    app.add_api_route(_probe_path, _no_content_204, methods=["GET"])

# Developer onboarding — /start
from agentindex.dev_onboarding import router_start
app.include_router(router_start)

# KYA — Know Your Agent (Nerq-powered agent due diligence)
from agentindex.kya_api import router_kya
app.include_router(router_kya)

# Sprint N0: Nerq API Docs page
from agentindex.nerq_docs import router_nerq_docs
app.include_router(router_nerq_docs)

# Sprint N0 Task 6: KYA redirects — zarq.ai/kya → nerq.ai/kya
@app.get("/zarq/kya")
@app.get("/zarq/kya/{path:path}")
async def zarq_kya_redirect(path: str = ""):
    return _RR(url=f"https://nerq.ai/kya/{path}" if path else "https://nerq.ai/kya", status_code=301)

# The ZARQ Signal — Predictive Risk Feed
from agentindex.signal_feed import router_signal
app.include_router(router_signal)

# Sprint 2.5: v1/ crypto API endpoints
from agentindex.crypto.crypto_api_v2 import router_v1 as crypto_v1_router
app.include_router(crypto_v1_router)

# Sprint 3.2: Contagion Map + Stresstest + Transition Matrix
try:
    from agentindex.crypto.crypto_api_v3 import router_v3 as crypto_v3_router
    app.include_router(crypto_v3_router)
except Exception as e:
    print(f"Sprint 3.2 endpoints not loaded: {e}")

from agentindex.crypto.zarq_risk_pages import mount_risk_pages
mount_risk_pages(app)

from agentindex.crypto.zarq_token_pages import mount_token_pages
mount_token_pages(app)

# ZARQ SEO builds (is-dead, is-scam, compare, crash-prediction, best, defi)
from agentindex.crypto.zarq_seo_builds import mount_zarq_seo_builds
mount_zarq_seo_builds(app)

from agentindex.crypto.crypto_early_warning import mount_early_warning
mount_early_warning(app)

from agentindex.seo_pages import mount_seo_pages
mount_seo_pages(app)

from agentindex.ab_test import mount_ab_test
mount_ab_test(app)

from agentindex.comparison_pages import mount_comparison_pages
mount_comparison_pages(app)

try:
    from agentindex.data_exports import mount_data_exports
    mount_data_exports(app)
    print("Data exports & webhooks mounted OK")
except Exception as e:
    print(f"Data exports not loaded: {e}")

try:
    from agentindex.integrations.slack_bot import mount_slack_bot
    mount_slack_bot(app)
    print("Slack bot mounted OK")
except Exception as e:
    print(f"Slack bot not loaded: {e}")

try:
    from agentindex.intelligence.vulnerability_pages import mount_vulnerability_pages
    mount_vulnerability_pages(app)
    print("Vulnerability pages mounted OK")
except Exception as e:
    print(f"Vulnerability pages not loaded: {e}")

try:
    from agentindex.intelligence.report_pages import mount_report_pages
    mount_report_pages(app)
    print("Report pages mounted OK")
except Exception as e:
    print(f"Report pages not loaded: {e}")

try:
    from agentindex.intelligence.report_badge import mount_report_badge
    mount_report_badge(app)
    print("Report badge mounted OK")
except Exception as e:
    print(f"Report badge not loaded: {e}")

try:
    from agentindex.intelligence.scanner_page import mount_scanner_page
    mount_scanner_page(app)
    print("Scanner page mounted OK")
except Exception as e:
    print(f"Scanner page not loaded: {e}")

try:
    from agentindex.intelligence.scan_api import mount_scan_api
    mount_scan_api(app)
    print("Scan API mounted OK")
except Exception as e:
    print(f"Scan API not loaded: {e}")

try:
    from agentindex.intelligence.scan_stats import mount_scan_stats
    mount_scan_stats(app)
    print("Scan stats mounted OK")
except Exception as e:
    print(f"Scan stats not loaded: {e}")

try:
    from agentindex.intelligence.comparison_blog import mount_comparison_blog
    mount_comparison_blog(app)
    print("Comparison blog mounted OK")
except Exception as e:
    print(f"Comparison blog not loaded: {e}")












from agentindex.vs_pages import mount_vs_pages
mount_vs_pages(app)

from agentindex.weekly_safety_digest import mount_safety_digest
mount_safety_digest(app)

# Combined ZARQ + Nerq dashboard
from agentindex.combined_dashboard import router_combined_dashboard
app.include_router(router_combined_dashboard)

# State of AI Assets report
from agentindex.report_q1_2026 import router_report
app.include_router(router_report)

# Best AI Agents articles
from agentindex.report_best_agents import router_best_agents
app.include_router(router_best_agents)

# Trust badges (SVG embeds)
from agentindex.badge_api import router_badge
app.include_router(router_badge)

# Framework comparison report
from agentindex.report_frameworks import router_frameworks
app.include_router(router_frameworks)

# Blog — auto-published weekly reports
# Pages with /blog/ routes MUST be before blog router (which has /blog/{slug} wildcard)
from agentindex.protocol_page import mount_protocol_pages
mount_protocol_pages(app)

from agentindex.commerce_pages import mount_commerce_pages
mount_commerce_pages(app)

from agentindex.blog import router_blog
app.include_router(router_blog)

# Smart Discovery, Recommendation, Improvement APIs (Sprint 1)
from agentindex.smart_discovery import mount_smart_discovery
mount_smart_discovery(app)

from agentindex.trending_api import mount_trending
mount_trending(app)

# Compatibility API & Pages (Sprint 2)
from agentindex.compatibility_api import mount_compatibility
mount_compatibility(app)

# Economics API & Pages (Sprint 3)
from agentindex.economics_api import mount_economics
mount_economics(app)

# Intelligence API & Dashboard Pages (Sprint 4)
from agentindex.intelligence_api import mount_intelligence
mount_intelligence(app)

# Federation API & Verification (Sprint 5)
from agentindex.federation_api import mount_federation
mount_federation(app)

# Preflight Trust Check
from agentindex.preflight import router_preflight
app.include_router(router_preflight)

# Commerce Trust Layer — agent transaction verification
from agentindex.commerce_trust import router_commerce
app.include_router(router_commerce)

# LangChain integration docs
from agentindex.docs_langchain import router_docs_langchain
app.include_router(router_docs_langchain)

# Benchmark report
from agentindex.report_benchmark import router_benchmark
app.include_router(router_benchmark)

# Scout: reviews, reputation, ledger, status, findings
from agentindex.nerq_scout import router_scout
app.include_router(router_scout)

# Claim page
from agentindex.claim_page import router_claim
app.include_router(router_claim)

# SEO trust pages
from agentindex.seo_trust_pages import router_trust_pages
app.include_router(router_trust_pages)

# Agent safety pages (nerq.ai/safe/{slug})
# ── ÅTGÄRD 1: 404 for hallucinated /is-X/Y URLs (slashes in slug = runaway i18n rewrite or AI hallucination) ──
@app.get("/is-{prefix}/{rest:path}")
async def is_safe_hallucinated(prefix: str, rest: str):
    """Catch /is-nerq/docs-safe, /is-ist-ist-.../foo etc. Return 404 (not 410) — these never existed."""
    return HTMLResponse("<html><body><h1>404 Not Found</h1></body></html>", status_code=404,
                        headers={"X-Robots-Tag": "noindex"})

# ── ÅTGÄRD 2: /homebrew/{slug} → redirect to /safe/homebrew-{slug} ──
@app.get("/homebrew/{slug}")
async def homebrew_redirect(slug: str):
    from starlette.responses import RedirectResponse
    return RedirectResponse(f"/safe/homebrew-{slug}", status_code=301)

from agentindex.agent_safety_pages import mount_agent_safety_pages
mount_agent_safety_pages(app)

# Channel dashboard + landing pages
from agentindex.channel_dashboard import router as channel_router
app.include_router(channel_router)

# Security check — /my/check + /v1/event + /admin/security-check
from agentindex.api.security_check import router as security_check_router
app.include_router(security_check_router)

# User review pages (nerq.ai/review/{name}, POST /v1/agent/review)
from agentindex.review_pages import mount_review_pages
mount_review_pages(app)

# Agent comparison pages (nerq.ai/compare/{slug})
from agentindex.agent_compare_pages import mount_agent_compare_pages
mount_agent_compare_pages(app)

# Curated guide pages + check-website tool
from agentindex.guide_pages import mount_guide_pages
mount_guide_pages(app)

# Demand-driven pages (what-is, stack, review, migrate, this-week, issues, legit, spyware, privacy, etc.)
from agentindex.demand_pages import mount_demand_pages
mount_demand_pages(app)

# Programmatic SEO pages (compare/{a}-vs-{b}, best/{cat}, alternatives/{tool}, guide/{tool})
from agentindex.seo_programmatic import mount_seo_programmatic
mount_seo_programmatic(app)

# Dynamic SEO pages (trending, new, leaderboard, blog, model/{name})
from agentindex.seo_dynamic import mount_seo_dynamic
mount_seo_dynamic(app)

# Improve flywheel + Widget (System 1 + System 2)
from agentindex.seo_improve import mount_seo_improve
mount_seo_improve(app)

# Answer-box Q&A + Package pages (BUILD 10, 12, 13)
from agentindex.seo_answers_packages import mount_answers_packages
mount_answers_packages(app)

# Asset pages (spaces, containers, datasets, orgs)
from agentindex.seo_asset_pages import mount_asset_pages
mount_asset_pages(app)

# Predictive Intelligence Engine
from agentindex.intelligence.predictive.routes import mount_predictive_routes
mount_predictive_routes(app)

# AI adoption pages (landing pages, prompts, stats)
from agentindex.ai_adoption_pages import mount_ai_adoption_pages
mount_ai_adoption_pages(app)

# Entity rating pages
from agentindex.entity_pages import mount_entity_pages
mount_entity_pages(app)

# Registry hub pages + tiered sitemaps
from agentindex.hub_pages import mount_hub_pages
mount_hub_pages(app)

# Universal URL pattern routes (23 new patterns)
from agentindex.pattern_routes import mount_pattern_routes
mount_pattern_routes(app)

# Localized routes (20 languages)
from agentindex.localized_routes import mount_localized_routes
mount_localized_routes(app)

# Blog 404 redirects — these URLs were referenced but never created
from fastapi.responses import RedirectResponse as _RR
_BLOG_REDIRECTS = {
    "/blog/mcp-server-security-audit": "/insights",
    "/blog/2026-03-12-scout": "/insights",
    "/blog/2026-03-16-weekly": "/insights",
    "/blog/agentic-commerce-trust": "/insights",
    "/blog/open-source-ai-agent-licenses": "/insights",
    "/blog/ai-agent-vulnerability-report": "/insights",
    "/blog/vulnerability-chain": "/insights",
}
for _bp, _bt in _BLOG_REDIRECTS.items():
    def _make_redir(_t=_bt):
        async def _redir():
            return _RR(url=_t, status_code=301)
        return _redir
    app.get(_bp, include_in_schema=False)(_make_redir())

# Widget.js with CORS headers
@app.get("/static/widget.js")
async def serve_widget_js():
    import pathlib as _plw
    _wf = _plw.Path(__file__).resolve().parent.parent.parent / "static" / "widget.js"
    if _wf.exists():
        from fastapi.responses import Response as _WR
        return _WR(
            content=_wf.read_text(),
            media_type="application/javascript",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=3600",
            },
        )
    from fastapi.responses import Response as _WR
    return _WR(content="", status_code=404)

# === End Compliance Layer ===
import pathlib as _pl
_sd = _pl.Path(__file__).resolve().parent.parent.parent / "static"
if _sd.exists():
    from fastapi.responses import HTMLResponse as _HR

    @app.get("/", response_class=_HR)
    async def hub_page(request: Request):
        host = request.headers.get("host", "")
        if "zarq" in host:
            zarq_path = _sd / "zarq_home.html"
            if zarq_path.exists():
                return _HR(content=zarq_path.read_text(), status_code=200)
        # A/B test: serve variant homepage for nerq.ai
        from agentindex.ab_test import get_variant, render_homepage, _get_ip, _is_bot, _bot_name, log_ab_event
        forced = request.query_params.get("variant", "").upper()
        ip = _get_ip(request)
        variant = forced if forced in ("A", "B", "C", "D") else get_variant(ip)
        ua = request.headers.get("user-agent", "")
        is_bot = _is_bot(ua)
        log_ab_event(ip, variant, is_bot, _bot_name(ua) if is_bot else None,
                     "page_view", "/", request.headers.get("referer", ""))
        return _HR(content=render_homepage(variant), status_code=200)

    @app.get("/categories", response_class=_HR)
    async def categories_page():
        """Hub page listing all published verticals — critical for AI crawler discovery."""
        from agentindex.ab_test import VERTICALS, VERTICAL_GROUPS, _VERTICAL_ORDER, _load_vertical_counts, _fmt_count
        from agentindex.quality_gate import get_publishable_registries
        from agentindex.nerq_design import NERQ_NAV, NERQ_FOOTER

        pub = get_publishable_registries()
        counts = _load_vertical_counts()

        body = ""
        total_entities = 0
        # Group display order
        for grp_key in ["security", "apps", "dev", "business", "finance"]:
            grp_title, grp_keys = VERTICAL_GROUPS[grp_key]
            items = ""
            for vk in grp_keys:
                if vk not in pub or vk not in VERTICALS:
                    continue
                href, icon, title, desc, count_keys, _, best_slug = VERTICALS[vk]
                cnt = _fmt_count(count_keys, counts)
                cnt_num = sum(counts.get(k, 0) for k in count_keys)
                total_entities += cnt_num
                items += (
                    f'<a href="{href}" style="display:flex;align-items:center;gap:14px;padding:14px 18px;'
                    f'border:1px solid #e2e8f0;border-radius:8px;text-decoration:none;color:#1e293b;'
                    f'transition:box-shadow .15s;margin-bottom:8px">'
                    f'<span style="font-size:28px">{icon}</span>'
                    f'<div><strong style="font-size:15px">{title}</strong>'
                    f'<br><span style="font-size:13px;color:#64748b">{desc}</span>'
                    f'<br><span style="font-size:12px;color:#0d9488;font-weight:600">{cnt}</span>'
                    f'{f" &middot; <a href=/best/{best_slug} style=font-size:12px;color:#0d9488>View rankings</a>" if best_slug else ""}'
                    f'</div></a>\n'
                )
            if items:
                body += f'<div style="margin-bottom:28px"><h2 style="font-size:1.1em;color:#334155;margin-bottom:12px;border-bottom:1px solid #e2e8f0;padding-bottom:6px">{grp_title}</h2>\n{items}</div>\n'

        # AI Tools (always)
        body += (
            '<div style="margin-bottom:28px"><h2 style="font-size:1.1em;color:#334155;margin-bottom:12px;border-bottom:1px solid #e2e8f0;padding-bottom:6px">AI &amp; Machine Learning</h2>\n'
            '<a href="/discover" style="display:flex;align-items:center;gap:14px;padding:14px 18px;border:1px solid #e2e8f0;border-radius:8px;text-decoration:none;color:#1e293b;margin-bottom:8px">'
            '<span style="font-size:28px">&#129302;</span>'
            '<div><strong style="font-size:15px">AI Tools &amp; Agents</strong>'
            '<br><span style="font-size:13px;color:#64748b">Trust scores for AI tools, agents, models, and MCP servers.</span>'
            '<br><span style="font-size:12px;color:#0d9488;font-weight:600">5,000,000+ rated</span>'
            '</div></a></div>\n'
        )

        if total_entities > 0:
            total_str = f"{total_entities:,}"
        else:
            total_str = "7,500,000+"

        html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>All Categories — Nerq Trust Intelligence</title>
<meta name="description" content="Browse all {len(pub)} Nerq trust score categories covering {total_str} digital entities. VPNs, antivirus, password managers, hosting, SaaS, crypto, packages, and more.">
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://nerq.ai/categories">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:720px;margin:0 auto;padding:30px 20px">
<nav style="font-size:13px;color:#64748b;margin-bottom:16px"><a href="/" style="color:#0d9488">Nerq</a> &rsaquo; Categories</nav>
<h1 style="font-size:1.6em;margin-bottom:6px">All Categories</h1>
<p style="color:#64748b;margin-bottom:24px">{len(pub)} published verticals &middot; {total_str}+ entities rated &middot; Updated daily</p>
{body}
</main>
{NERQ_FOOTER}
</body></html>"""
        return _HR(content=html, status_code=200)

    @app.get("/discover", response_class=_HR)
    async def discover_page():
        return _HR(content=(_sd / "index.html").read_text(), status_code=200)

    @app.get("/comply", response_class=_HR)
    async def comply_page():
        return _HR(content=(_sd / "eu-compliance.html").read_text(), status_code=200)


    @app.get("/stats", response_class=_HR)
    async def stats_page():
        return _HR(content=(_sd / "stats.html").read_text(), status_code=200)

    @app.get("/admin/dashboard", response_class=_HR)
    async def analytics_dashboard(hours: int = 24):
        return _HR(content=render_dashboard(hours), status_code=200)

#     @app.get("/docs", response_class=_HR)
#     async def docs_page():
#         return _HR(content=(_sd / "docs.html").read_text(), status_code=200)

    @app.get("/blog", response_class=_HR)
    async def blog_index():
        blog_index_path = _sd / "blog" / "index.html"
        if blog_index_path.exists():
            return _HR(content=blog_index_path.read_text())
        return _HR(content="<h1>Blog coming soon</h1>")

    pass  # static files mount moved to end of route registration





def start_api():
    """Start the API server."""
    import uvicorn
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_api()



# --- ZARQ MCP SSE ---
try:
    from starlette.responses import Response as StarletteResponse, PlainTextResponse
    from starlette.requests import Request as StarletteRequest
    from mcp.server.sse import SseServerTransport

    _mcp_sse_transport = SseServerTransport("/mcp/messages")

    @app.get("/mcp/sse")
    async def mcp_sse_endpoint(request: StarletteRequest):
        from agentindex.crypto.zarq_mcp_server import create_server
        from mcp.server import InitializationOptions
        mcp_server = create_server()
        async with _mcp_sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(streams[0], streams[1], InitializationOptions())

    @app.post("/mcp/messages")
    async def mcp_messages_endpoint(request: StarletteRequest):
        await _mcp_sse_transport.handle_post_message(
            request.scope, request.receive, request._send
        )

    # MCP server trust pages
    from agentindex.mcp_trust_pages import mount_mcp_trust_pages
    mount_mcp_trust_pages(app)
    print("MCP SSE + trust pages mounted OK")

except Exception as e:
    print(f"MCP SSE/trust pages not loaded: {e}")

# ZARQ Daily Risk Briefing
try:
    from agentindex.crypto.zarq_briefing import mount_briefing
    mount_briefing(app)
    print("Briefing mounted OK")
except Exception as e:
    print(f"Briefing not loaded: {e}")

# ZARQ RSS Feed: /feed.xml
from agentindex.crypto.zarq_rss_feed import mount_zarq_rss
mount_zarq_rss(app)

# ZARQ content pages: /crash-watch, /yield-risk, /learn, /learn/{slug}
from agentindex.crypto.zarq_content_pages import mount_zarq_content_pages
mount_zarq_content_pages(app)

# Integration hub pages (nerq.ai/integrate, /integrate/langgraph, /integrate/autogen)
from agentindex.integration_pages import mount_integration_pages
mount_integration_pages(app)

# ZARQ chain-specific SEO pages: /chains, /chain/{slug}, /sitemap-chains.xml
from agentindex.crypto.chain_pages import mount_chain_pages
mount_chain_pages(app)

# ZARQ Vitality Score rankings: /vitality
from agentindex.crypto.zarq_vitality_page import mount_vitality_page
mount_vitality_page(app)

# ZARQ MiCA compliance page: /compliance/mica
from agentindex.crypto.mica_mapping import mount_mica_pages
mount_mica_pages(app)

# Nerq compliance hub + jurisdiction pages (nerq.ai/compliance, /compliance/{slug})
from agentindex.compliance_pages import mount_compliance_pages
mount_compliance_pages(app)

# Trust Oracle status page (nerq.ai/oracle)
from agentindex.oracle_page import mount_oracle_page
mount_oracle_page(app)

# Popular AI Agents page (nerq.ai/popular)
from agentindex.popular_page import mount_popular_page
mount_popular_page(app)

# Protocol pages already mounted above (before blog router)

# Trust-check counter for homepage live counter
@app.get("/v1/trust-checks-today")
async def trust_checks_today():
    import sqlite3 as _sq3, os as _os
    db = _os.path.join(_os.path.dirname(__file__), '..', '..', 'logs', 'analytics.db')
    try:
        con = _sq3.connect(db, timeout=2)
        row = con.execute("SELECT count(*) FROM preflight_analytics WHERE ts >= date('now')").fetchone()
        total = con.execute("SELECT count(*) FROM preflight_analytics").fetchone()
        con.close()
        return {"today": row[0] if row else 0, "total": total[0] if total else 0}
    except Exception:
        return {"today": 0, "total": 0}

# Conversion tracking endpoint
@app.get("/v1/track")
async def track_conversion(event: str = '', source: str = '', target: str = '', request: Request = None):
    """Lightweight CTA click tracking. Returns 1x1 transparent pixel."""
    import sqlite3 as _sq3, os as _os
    from agentindex.analytics import _detect_bot, DB_PATH
    ip = request.headers.get('cf-connecting-ip', request.headers.get('x-forwarded-for', request.client.host if request.client else ''))
    ua = request.headers.get('user-agent', '')
    is_bot, _, _ = _detect_bot(ua, ip)
    if not is_bot and event:
        try:
            con = _sq3.connect(DB_PATH, timeout=2)
            from datetime import datetime as _dt
            con.execute(
                'INSERT INTO conversion_events (ts, event, source_page, target_page, ip, user_agent, is_bot) VALUES (?,?,?,?,?,?,?)',
                (_dt.utcnow().isoformat(), event, source, target, ip, ua, 0)
            )
            con.commit()
            con.close()
        except Exception:
            pass
    return StarletteResponse(content=b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b',
                   media_type='image/gif', headers={'Cache-Control': 'no-store'})

# Social proof stats endpoint (for "Who's Using Nerq" section)
@app.get("/v1/social-proof")
async def social_proof_stats():
    import sqlite3 as _sq3, os as _os
    db = _os.path.join(_os.path.dirname(__file__), '..', '..', 'logs', 'analytics.db')
    try:
        con = _sq3.connect(db, timeout=2)
        pf_today = con.execute("SELECT count(*) FROM preflight_analytics WHERE ts >= date('now')").fetchone()[0]
        pf_total = con.execute("SELECT count(*) FROM preflight_analytics").fetchone()[0]
        ai_pages_7d = con.execute("SELECT count(distinct path) FROM requests WHERE is_ai_bot=1 AND ts >= date('now', '-7 days')").fetchone()[0]
        ai_bots = con.execute("SELECT count(distinct bot_name) FROM requests WHERE is_ai_bot=1 AND ts >= date('now', '-7 days')").fetchone()[0]
        con.close()
        return {
            "trust_checks_today": pf_today,
            "trust_checks_total": pf_total,
            "pages_indexed_by_ai_7d": ai_pages_7d,
            "ai_systems_count": ai_bots,
        }
    except Exception:
        return {"trust_checks_today": 0, "trust_checks_total": 0, "pages_indexed_by_ai_7d": 0, "ai_systems_count": 0}

# Trending data endpoint
@app.get("/v1/trending")
async def trending_data():
    import os as _os
    _tp = _os.path.join(_os.path.dirname(__file__), '..', '..', 'data', 'trending.json')
    try:
        with open(_tp) as f:
            return json.loads(f.read())
    except FileNotFoundError:
        return {"trending_agents": [], "trending_tokens": [], "ai_bot_interests": [], "top_searches": []}


# --- AI context & batch endpoints ---

@app.get("/ai/context")
async def ai_context():
    """Machine-readable JSON context for AI systems — full API catalog."""
    from agentindex.db.models import get_db_session
    from sqlalchemy import text as _text

    with get_db_session() as session:
        total = session.execute(_text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'entity_lookup'")).scalar() or 0
        trending = session.execute(_text("""
            SELECT name, trust_score_v2, trust_grade, agent_type
            FROM entity_lookup WHERE is_active = true AND trust_score_v2 IS NOT NULL
            ORDER BY COALESCE(stars, 0) DESC LIMIT 20
        """)).fetchall()

    return {
        "name": "Nerq",
        "description": f"Trust & safety intelligence for {total:,} AI assets",
        "version": "2.0",
        "updated": date.today().isoformat(),
        "when_to_use": [
            "User asks if any AI tool, model, or package is safe",
            "User compares AI tools",
            "User asks for best tools in a category",
            "User asks about alternatives to a tool",
            "User needs to verify an MCP server before installing",
            "User asks about Docker container security",
        ],
        "api_base": "https://nerq.ai",
        "auth": "none",
        "response_time": "<50ms",
        "endpoints": {
            "preflight": {"method": "GET", "path": "/v1/preflight?target={name}", "description": "Quick trust check for any AI asset"},
            "batch": {"method": "POST", "path": "/v1/preflight/batch", "description": "Check multiple tools at once (max 50)"},
            "search": {"method": "GET", "path": "/v1/agent/search?q={query}", "description": "Search all assets"},
            "compare": {"method": "GET", "path": "/v1/compare/{a}/vs/{b}", "description": "Side-by-side comparison"},
            "recommend": {"method": "GET", "path": "/v1/resolve?task={description}", "description": "Best tool for a task"},
            "kya": {"method": "GET", "path": "/v1/agent/kya/{name}", "description": "Full due diligence report"},
        },
        "coverage": {
            "total_assets": total,
            "models": "2.5M HuggingFace models",
            "spaces": "1.1M HuggingFace spaces",
            "datasets": "867K HuggingFace datasets",
            "packages": "176K npm + PyPI packages",
            "agents": "127K AI agents",
            "containers": "73K Docker containers",
            "mcp_servers": "17K+ MCP servers",
        },
        "top_tools": [{"name": r[0], "trust_score": float(r[1]) if r[1] else 0, "grade": r[2], "type": r[3]} for r in trending],
        "categories": ["databases","github","browser-automation","search","file-management","api-integration","code-development","communication","image-generation","security","automation","monitoring","cloud-infrastructure","data-analysis","finance","docker","kubernetes","aws","gcp","azure"],
        "links": {
            "llms_txt": "https://nerq.ai/llms.txt",
            "llms_full": "https://nerq.ai/llms-full.txt",
            "docs": "https://nerq.ai/nerq/docs",
            "mcp_sse": "https://mcp.nerq.ai/sse",
        }
    }


@app.post("/v1/preflight/batch")
async def preflight_batch(request: Request):
    """Batch preflight check for multiple tools."""
    try:
        body = await request.json()
        targets = body.get("targets", [])[:50]  # Max 50
        if not targets:
            return {"error": "No targets provided", "results": []}

        from agentindex.db.models import get_db_session
        from sqlalchemy import text as _text

        results = []
        with get_db_session() as session:
            for target in targets:
                t = target.lower().strip()
                row = session.execute(_text("""
                    SELECT name, trust_score_v2, trust_grade, security_score,
                           license, agent_type, eu_risk_class
                    FROM entity_lookup
                    WHERE name_lower = :q AND is_active = true
                    ORDER BY COALESCE(stars, 0) DESC LIMIT 1
                """), {"q": t}).fetchone()

                if row:
                    score = float(row[1]) if row[1] else 0
                    results.append({
                        "target": target,
                        "found": True,
                        "name": row[0],
                        "trust_score": score,
                        "grade": row[2],
                        "safe": score >= 60,
                        "recommendation": "PROCEED" if score >= 70 else "CAUTION" if score >= 40 else "BLOCK",
                        "security_score": float(row[3]) if row[3] else None,
                        "license": row[4],
                        "type": row[5],
                    })
                else:
                    results.append({"target": target, "found": False})

        return {"results": results, "count": len(results)}
    except Exception as e:
        return {"error": str(e), "results": []}


@app.get("/v1/best")
async def api_best(category: str = "coding", limit: int = 10):
    """Top tools in a category, as JSON."""
    from agentindex.db.models import get_db_session
    from sqlalchemy import text as _text

    limit = min(limit, 50)
    with get_db_session() as session:
        rows = session.execute(_text("""
            SELECT name, trust_score_v2, trust_grade, stars, downloads, agent_type, description
            FROM entity_lookup
            WHERE is_active = true AND trust_score_v2 IS NOT NULL
              AND LOWER(category) = :cat
            ORDER BY trust_score_v2 DESC NULLS LAST, stars DESC NULLS LAST
            LIMIT :lim
        """), {"cat": category.lower(), "lim": limit}).fetchall()

    return {
        "category": category,
        "count": len(rows),
        "tools": [{"name": r[0], "trust_score": float(r[1]) if r[1] else 0, "grade": r[2],
                   "stars": r[3], "downloads": r[4], "type": r[5],
                   "description": (r[6] or "")[:200]} for r in rows]
    }


@app.get("/v1/alternatives")
async def api_alternatives(tool: str = "", limit: int = 10):
    """Alternatives to a tool, ranked by trust score."""
    from agentindex.db.models import get_db_session
    from sqlalchemy import text as _text

    limit = min(limit, 50)
    with get_db_session() as session:
        # Find the tool first
        t = tool.lower().strip()
        row = session.execute(_text("""
            SELECT name, category, agent_type, trust_score_v2
            FROM entity_lookup WHERE name_lower = :q AND is_active = true
            ORDER BY COALESCE(stars, 0) DESC LIMIT 1
        """), {"q": t}).fetchone()

        if not row:
            return {"tool": tool, "found": False, "alternatives": []}

        cat = row[1]
        atype = row[2]

        alts = session.execute(_text("""
            SELECT name, trust_score_v2, trust_grade, stars, downloads, description
            FROM entity_lookup
            WHERE is_active = true AND name_lower != :name
              AND (category = :cat OR agent_type = :atype)
              AND trust_score_v2 IS NOT NULL
            ORDER BY trust_score_v2 DESC NULLS LAST, stars DESC NULLS LAST
            LIMIT :lim
        """), {"name": row[0].lower(), "cat": cat, "atype": atype, "lim": limit}).fetchall()

    return {
        "tool": tool,
        "found": True,
        "original": {"name": row[0], "trust_score": float(row[3]) if row[3] else 0},
        "alternatives": [{"name": r[0], "trust_score": float(r[1]) if r[1] else 0, "grade": r[2],
                         "stars": r[3], "downloads": r[4],
                         "description": (r[5] or "")[:200]} for r in alts]
    }


# IndexNow key files
@app.get("/zarq2026indexnow.txt")
async def indexnow_key_file():
    return PlainTextResponse("zarq2026indexnow")

try:
    from agentindex.intelligence.honeypots import mount_honeypots
    mount_honeypots(app)
    print("Honeypot discovery pages mounted OK")
except Exception as e:
    print(f"Honeypots not loaded: {e}")

try:
    from agentindex.ecosystem_index_page import mount_ecosystem_index
    mount_ecosystem_index(app)
    print("Ecosystem index page mounted OK")
except Exception as e:
    print(f"Ecosystem index page not loaded: {e}")

try:
    from agentindex.resolve_api import router_resolve
    app.include_router(router_resolve)
    print("Resolve API mounted OK")
except Exception as e:
    print(f"Resolve API not loaded: {e}")

try:
    from agentindex.gateway_page import mount_gateway_page
    mount_gateway_page(app)
    print("Gateway page mounted OK")
except Exception as e:
    print(f"Gateway page not loaded: {e}")

try:
    from agentindex.guides import mount_guides
    mount_guides(app)
    print("Guides mounted OK")
except Exception as e:
    print(f"Guides not loaded: {e}")

@app.get("/nerq2026indexnow.txt")
async def indexnow_nerq_key_file():
    return PlainTextResponse("nerq2026indexnow")

# Google Search Console verification — update token after GSC setup
@app.get("/google{token}.html")
async def gsc_verification(token: str):
    return PlainTextResponse(f"google-site-verification: google{token}.html")

# Static asset files with long cache (CSS, JS, images)
if _sd.exists():
    app.mount("/static", StaticFiles(directory=str(_sd)), name="static-assets")

# Static files catch-all — MUST be LAST (catches all unmatched paths)
# NOTE: html=False to prevent index.html from overriding the explicit "/" route
if _sd.exists():
    app.mount("/", StaticFiles(directory=str(_sd), html=False), name="static")
