"""
ZARQ Observability — Sprint 0, Track E + Sprint 2 Tier Logic
Request logging to SQLite + /internal/metrics endpoint.
Redis-backed tier system for /v1/ endpoints.
"""

import hashlib
import json
import logging
import os
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

DB_PATH = os.path.join(
    os.path.dirname(__file__), "crypto", "zarq_api_log.db"
)
METRICS_TOKEN = os.getenv("ZARQ_METRICS_TOKEN", "zarq-internal-2026")
REDIS_CLI = "/opt/homebrew/bin/redis-cli"

logger = logging.getLogger("zarq.observability")

_buffer = []
_buffer_lock = threading.Lock()
_FLUSH_SIZE = 20
_db_initialized = False

# ─── Tier Definitions ───
TIER_THRESHOLDS = [
    (5000, "blocked"),   # 5000+ → 402
    (2000, "degraded"),  # 2000-5000 → stripped response
    (500,  "signal"),    # 500-2000 → full + headers
    (0,    "open"),      # 0-500 → full response
]

DEGRADED_STRIP_FIELDS = {"crash_probability", "distance_to_default"}

PAYMENT_402 = {
    "error": "daily_limit_exceeded",
    "tier": "blocked",
    "calls_today": 0,
    "daily_limit": 5000,
    "upgrade": {
        "message": "You've exceeded 5,000 calls today. Upgrade for unlimited access.",
        "contact": "hello@zarq.ai",
        "plans": {
            "pro": {"price": "$49/mo", "limit": "unlimited", "features": ["Full response data", "Priority support", "Webhook alerts"]},
            "enterprise": {"price": "Custom", "limit": "unlimited", "features": ["SLA", "Dedicated support", "Custom integrations"]},
        },
    },
}


# ─── Redis helpers ───

def _redis_incr_daily(ip_hash: str) -> int:
    """Increment daily counter in Redis. Returns count. Falls back to 0 on error."""
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"zarq:calls:{ip_hash}:{today}"
        result = subprocess.run(
            [REDIS_CLI, "INCR", key],
            capture_output=True, text=True, timeout=2,
        )
        count = int(result.stdout.strip())
        if count == 1:
            subprocess.run(
                [REDIS_CLI, "EXPIRE", key, "86400"],
                capture_output=True, text=True, timeout=2,
            )
        return count
    except Exception:
        return 0


def _redis_get_daily(ip_hash: str) -> int:
    """Get daily counter from Redis without incrementing."""
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"zarq:calls:{ip_hash}:{today}"
        result = subprocess.run(
            [REDIS_CLI, "GET", key],
            capture_output=True, text=True, timeout=2,
        )
        val = result.stdout.strip()
        return int(val) if val and val != "(nil)" else 0
    except Exception:
        return 0


def _get_tier(calls_today: int) -> str:
    """Determine tier based on daily call count."""
    for threshold, tier_name in TIER_THRESHOLDS:
        if calls_today >= threshold:
            return tier_name
    return "open"


# ─── SQLite logging (unchanged) ───

def _init_db():
    global _db_initialized
    if _db_initialized:
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS api_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        endpoint TEXT,
        method TEXT,
        status_code INTEGER,
        latency_ms REAL,
        ip_hash TEXT,
        tier TEXT DEFAULT 'open',
        user_agent TEXT,
        response_size INTEGER DEFAULT 0
    )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_log_ts ON api_log(timestamp)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_log_endpoint ON api_log(endpoint)"
    )
    conn.commit()
    conn.close()
    _db_initialized = True


def _flush_buffer():
    with _buffer_lock:
        if not _buffer:
            return
        batch = list(_buffer)
        _buffer.clear()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.executemany(
            """INSERT INTO api_log
               (timestamp, endpoint, method, status_code, latency_ms,
                ip_hash, tier, user_agent, response_size)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            batch,
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _log_request(row):
    with _buffer_lock:
        _buffer.append(row)
        should_flush = len(_buffer) >= _FLUSH_SIZE
    if should_flush:
        _flush_buffer()


def _strip_degraded_fields(body: bytes) -> bytes:
    """Remove crash_probability and distance_to_default from JSON response."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body

    def _strip(obj):
        if isinstance(obj, dict):
            return {k: _strip(v) for k, v in obj.items() if k not in DEGRADED_STRIP_FIELDS}
        if isinstance(obj, list):
            return [_strip(item) for item in obj]
        return obj

    stripped = _strip(data)
    if isinstance(stripped, dict):
        stripped["_degraded"] = True
        stripped["_upgrade"] = "5000 calls/day for full data — hello@zarq.ai"
    return json.dumps(stripped).encode()


# ─── Middleware ───

class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        is_v1 = request.url.path.startswith("/v1/")
        is_health = request.url.path in ("/v1/health", "/health")
        # Skip logging for internal/admin endpoints that inflate P95
        _skip_log = request.url.path in ("/zarq/dashboard/data", "/zarq/dashboard", "/internal/metrics")

        ip = (request.client.host if request.client else "unknown")
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]

        # Bot rate limiting on /agent/ pages — prevent PG pool exhaustion from crawlers
        if request.url.path.startswith("/agent/"):
            ua = (request.headers.get("user-agent") or "").lower()
            is_bot = any(b in ua for b in ("googlebot", "bingbot", "meta-external", "facebookexternalhit",
                                            "bytespider", "ahrefsbot", "semrushbot", "dotbot", "petalbot"))
            if is_bot:
                # Track bot requests per second using a simple in-memory counter
                _now = time.time()
                _bot_key = f"bot:{ip_hash}"
                _bot_window = getattr(self, '_bot_windows', {})
                if not hasattr(self, '_bot_windows'):
                    self._bot_windows = _bot_window
                _prev = _bot_window.get(_bot_key, (0, 0))  # (count, window_start)
                if _now - _prev[1] > 10:  # 10-second window
                    _bot_window[_bot_key] = (1, _now)
                else:
                    _bot_window[_bot_key] = (_prev[0] + 1, _prev[1])
                    if _prev[0] + 1 > 20:  # >20 requests per 10s = too fast
                        return JSONResponse(
                            status_code=429,
                            content={"error": "Too many requests", "retry_after": 30},
                            headers={"Retry-After": "30"},
                        )

        # Check if request uses internal API key (bypass Redis tier check)
        _internal_key = os.getenv("NERQ_INTERNAL_API_KEY", "nerq-internal-2026")
        _req_key = (request.headers.get("X-API-Key") or
                    request.query_params.get("api_key") or
                    (request.headers.get("Authorization", "")[7:]
                     if request.headers.get("Authorization", "").startswith("Bearer ") else ""))
        _is_internal = _req_key == _internal_key

        # Tier check before processing (only for /v1/ non-health)
        if is_v1 and not is_health and not _is_internal:
            calls_today = _redis_incr_daily(ip_hash)
            tier = _get_tier(calls_today)

            # 402 — blocked
            if tier == "blocked":
                payload = {**PAYMENT_402, "calls_today": calls_today}
                return JSONResponse(status_code=402, content=payload, headers={
                    "X-Calls-Today": str(calls_today),
                    "X-Daily-Limit": "5000",
                    "X-Tier": tier,
                    "X-Powered-By": "ZARQ (zarq.ai)",
                })
        else:
            calls_today = 0
            tier = "open"

        start = time.time()
        response = await call_next(request)
        latency_ms = round((time.time() - start) * 1000, 1)

        ua = (request.headers.get("user-agent") or "")[:200]
        tier_header = response.headers.get("X-Nerq-Tier")
        log_tier = tier_header if tier_header else tier

        content_length = response.headers.get("content-length")
        response_size = int(content_length) if content_length else 0

        row = (
            datetime.now(timezone.utc).isoformat(),
            request.url.path,
            request.method,
            response.status_code,
            latency_ms,
            ip_hash,
            log_tier,
            ua,
            response_size,
        )
        if not _skip_log:
            _log_request(row)

        # Add headers on all /v1/ endpoints (including health)
        if is_v1:
            response.headers["X-Calls-Today"] = str(calls_today)
            response.headers["X-Daily-Limit"] = "5000"
            response.headers["X-Tier"] = tier
            response.headers["X-Powered-By"] = "ZARQ (zarq.ai)"

            # Degraded tier: strip sensitive fields from response body
            if tier == "degraded" and not is_health and response.status_code == 200:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk if isinstance(chunk, bytes) else chunk.encode()
                stripped = _strip_degraded_fields(body)
                return Response(
                    content=stripped,
                    status_code=200,
                    headers=dict(response.headers),
                    media_type="application/json",
                )

        return response


def _get_metrics():
    """Query the log DB for metrics."""
    _flush_buffer()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    from datetime import timedelta
    now_dt = datetime.now(timezone.utc)
    now_utc = now_dt.isoformat()
    cutoff_24h = (now_dt - timedelta(hours=24)).isoformat()
    cutoff_1h = (now_dt - timedelta(hours=1)).isoformat()
    cutoff_10m = (now_dt - timedelta(minutes=10)).isoformat()

    # requests last 24h / 1h
    r24 = conn.execute(
        "SELECT COUNT(*) FROM api_log WHERE timestamp >= ?",
        [cutoff_24h],
    ).fetchone()[0]
    r1 = conn.execute(
        "SELECT COUNT(*) FROM api_log WHERE timestamp >= ?",
        [cutoff_1h],
    ).fetchone()[0]

    # unique IPs last 24h
    uips = conn.execute(
        "SELECT COUNT(DISTINCT ip_hash) FROM api_log WHERE timestamp >= ?",
        [cutoff_24h],
    ).fetchone()[0]

    # latency percentiles (last 10 min, /v1/ API endpoints only — excludes slow agent pages)
    latencies = [
        row[0]
        for row in conn.execute(
            "SELECT latency_ms FROM api_log WHERE timestamp >= ? AND endpoint LIKE '/v1/%' ORDER BY latency_ms",
            [cutoff_10m],
        ).fetchall()
    ]
    if latencies:
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
    else:
        p50, p95 = 0, 0

    # top 10 endpoints
    top_eps = conn.execute(
        """SELECT endpoint, COUNT(*) as cnt FROM api_log
           WHERE timestamp >= ?
           GROUP BY endpoint ORDER BY cnt DESC LIMIT 10""",
        [cutoff_24h],
    ).fetchall()

    # tier distribution
    tiers = conn.execute(
        """SELECT tier, COUNT(*) as cnt FROM api_log
           WHERE timestamp >= ?
           GROUP BY tier ORDER BY cnt DESC""",
        [cutoff_24h],
    ).fetchall()

    conn.close()

    return {
        "requests_last_24h": r24,
        "requests_last_1h": r1,
        "unique_ips_last_24h": uips,
        "p50_latency_ms": round(p50, 1),
        "p95_latency_ms": round(p95, 1),
        "top_10_endpoints": [
            {"endpoint": r[0], "count": r[1]} for r in top_eps
        ],
        "tier_distribution": {r[0]: r[1] for r in tiers},
    }


def mount_observability(app):
    """Initialize DB, add middleware, register /internal/metrics."""
    _init_db()
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/internal/metrics")
    async def internal_metrics(request: Request):
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if token != METRICS_TOKEN:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return JSONResponse(content=_get_metrics())
