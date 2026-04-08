"""
Returning Visitor Banner Middleware
===================================
Injects a dismissable banner for returning visitors on key pages.
Criteria: >= 5 visits across >= 3 distinct days in last 14 days.
"""

import hashlib
import sqlite3
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

ANALYTICS_DB = "/Users/anstudio/agentindex/logs/analytics.db"

# Pages to show banner on
BANNER_PAGES = {"/crypto", "/briefing", "/vitality"}

# Pages where already-converted users land (skip banner)
SKIP_PAGES = {"/start", "/zarq/docs", "/nerq/docs"}

# Known bot user-agent fragments
BOT_FRAGMENTS = ("bot", "spider", "crawl", "chatgpt", "claude", "perplexity", "gpt", "slurp")

# In-memory dismissed IPs: ip_hash -> dismiss_timestamp
_dismissed: dict[str, float] = {}
_DISMISS_TTL = 86400  # 24 hours

# Cache for IP visit checks: ip_hash -> (is_returning, check_time)
_visit_cache: dict[str, tuple[bool, float]] = {}
_VISIT_CACHE_TTL = 600  # 10 minutes

BANNER_HTML = """
<div id="zarq-return-banner" style="position:fixed;bottom:0;left:0;right:0;z-index:9999;
  background:linear-gradient(135deg,#1a1a2e,#16213e);color:#e0e0e0;padding:14px 20px;
  font-family:system-ui,-apple-system,sans-serif;font-size:14px;display:flex;
  align-items:center;justify-content:center;gap:16px;box-shadow:0 -2px 12px rgba(0,0,0,0.3)">
  <span style="color:#c2956b;font-weight:600">You check ZARQ risk signals regularly</span>
  <span>&mdash; want automated alerts? Get API access in 60 seconds</span>
  <a href="/start" style="background:#c2956b;color:#1a1a2e;padding:6px 18px;
    font-weight:700;text-decoration:none;white-space:nowrap;font-size:13px">Get Started</a>
  <button onclick="this.parentElement.remove();fetch('?dismiss_banner=1',{method:'HEAD'})"
    style="background:none;border:none;color:#6b7280;cursor:pointer;font-size:18px;
    padding:0 4px;line-height:1" aria-label="Dismiss">&times;</button>
</div>
"""


def _ip_hash(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _is_bot(ua: str) -> bool:
    ua_lower = ua.lower()
    return any(f in ua_lower for f in BOT_FRAGMENTS)


def _get_raw_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _is_returning_visitor(raw_ip: str) -> bool:
    """Check analytics.db for returning visitor criteria."""
    now = time.time()

    # Check cache
    if raw_ip in _visit_cache:
        cached, ts = _visit_cache[raw_ip]
        if now - ts < _VISIT_CACHE_TTL:
            return cached

    result = False
    try:
        conn = sqlite3.connect(ANALYTICS_DB, timeout=2)
        row = conn.execute("""
            SELECT COUNT(*) as visits, COUNT(DISTINCT date(ts)) as days
            FROM requests
            WHERE ip = ? AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-14 days') AND is_bot = 0
        """, (raw_ip,)).fetchone()
        conn.close()
        if row and row[0] >= 5 and row[1] >= 3:
            result = True
    except Exception:
        pass

    _visit_cache[raw_ip] = (result, now)

    # Evict old cache entries
    if len(_visit_cache) > 5000:
        _visit_cache.clear()

    return result


def _is_dismissed(ip_hash: str) -> bool:
    if ip_hash in _dismissed:
        if time.time() - _dismissed[ip_hash] < _DISMISS_TTL:
            return True
        del _dismissed[ip_hash]
    return False


class ReturningVisitorBanner(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"

        # Handle dismiss
        if request.query_params.get("dismiss_banner") == "1":
            iph = _ip_hash(request)
            _dismissed[iph] = time.time()
            return await call_next(request)

        # ── Pre-flight checks BEFORE call_next ──
        # Determine if we need to inject the banner. If not, pass through
        # without touching body_iterator (avoids BaseHTTPMiddleware body bug).
        should_inject = False
        if path in BANNER_PAGES and path not in SKIP_PAGES:
            ua = request.headers.get("user-agent", "")
            if not _is_bot(ua):
                iph = _ip_hash(request)
                if not _is_dismissed(iph):
                    raw_ip = _get_raw_ip(request)
                    if _is_returning_visitor(raw_ip):
                        should_inject = True

        response = await call_next(request)

        if not should_inject:
            return response

        ct = response.headers.get("content-type", "")
        if "text/html" not in ct:
            return response

        # Inject banner before </body>
        try:
            body = b""
            async for chunk in response.body_iterator:
                if isinstance(chunk, str):
                    chunk = chunk.encode()
                body += chunk

            if not body:
                return response

            body_str = body.decode("utf-8", errors="replace")
            if "</body>" in body_str:
                body_str = body_str.replace("</body>", BANNER_HTML + "</body>")

            return Response(
                content=body_str,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        except Exception:
            return response
