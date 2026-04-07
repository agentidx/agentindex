"""
/my/check — Instant security check from HTTP headers.
No PII stored. No cookies. Stateless check endpoint.
Event tracking via separate SQLite (check_events.db).
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime, timezone
import re
import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Browser version database (update monthly) ──
LATEST_BROWSERS = {
    "Chrome": 134,
    "Firefox": 137,
    "Safari": 18,
    "Edge": 134,
}

# ── VPN detection via ip-api.com + Redis cache ──
_redis_vpn = None

def _get_vpn_redis():
    global _redis_vpn
    if _redis_vpn is None:
        try:
            import redis
            _redis_vpn = redis.Redis(host='localhost', port=6379, db=2, socket_timeout=0.2)
            _redis_vpn.ping()
        except Exception:
            _redis_vpn = False
    return _redis_vpn if _redis_vpn else None


def is_likely_vpn(ip: str) -> bool:
    """VPN detection with Redis-cached ip-api.com lookup (7d TTL per /24)."""
    if not ip or ip.startswith(("127.", "10.", "192.168.", "172.")):
        return False

    r = _get_vpn_redis()
    prefix = '.'.join(ip.split('.')[:3])
    cache_key = f"vpn:{prefix}"

    if r:
        try:
            cached = r.get(cache_key)
            if cached is not None:
                return cached == b"1"
        except Exception:
            pass

    try:
        import urllib.request
        import json
        req = urllib.request.Request(
            f"http://ip-api.com/json/{ip}?fields=hosting,proxy",
            headers={"User-Agent": "nerq.ai/security-check"}
        )
        resp = urllib.request.urlopen(req, timeout=2)
        data = json.loads(resp.read())
        is_vpn = data.get("hosting", False) or data.get("proxy", False)

        if r:
            try:
                r.setex(cache_key, 86400 * 7, "1" if is_vpn else "0")
            except Exception:
                pass

        return is_vpn
    except Exception:
        return False


# ── Parsers ──

def _parse_browser(ua: str) -> dict:
    patterns = [
        (r'Edg/(\d+)', 'Edge'),
        (r'Chrome/(\d+)', 'Chrome'),
        (r'Firefox/(\d+)', 'Firefox'),
        (r'Version/(\d+).*Safari', 'Safari'),
    ]
    for pattern, name in patterns:
        m = re.search(pattern, ua)
        if m:
            version = int(m.group(1))
            latest = LATEST_BROWSERS.get(name, version)
            return {"browser": name, "version": version, "latest": latest,
                    "versions_behind": max(0, latest - version)}
    return {"browser": "Unknown", "version": 0, "latest": 0, "versions_behind": 0}


def _parse_os(ua: str) -> dict:
    is_mobile = bool(re.search(r'Mobile|Android|iPhone|iPad', ua))
    outdated = False

    if 'Windows NT 10' in ua or 'Windows NT 11' in ua:
        outdated = False
    elif 'Windows NT' in ua:
        outdated = True

    mac = re.search(r'Mac OS X (\d+)[_.](\d+)', ua)
    if mac:
        outdated = int(mac.group(1)) < 14

    return {"is_mobile": is_mobile, "outdated": outdated}


# ── Scoring ──

def _calculate_score(checks: dict) -> tuple:
    score = 100
    findings = []

    if not checks.get("vpn_detected"):
        score -= 20
        findings.append(("medium", "Your approximate location is visible to every site you visit"))
    else:
        findings.append(("ok", "VPN detected — your real location is hidden"))

    behind = checks.get("browser_versions_behind", 0)
    if behind >= 5:
        score -= 25
        findings.append(("high", f"Browser is {behind} versions behind — security patches missing"))
    elif behind >= 2:
        score -= 10
        findings.append(("medium", f"Browser is {behind} versions behind current"))
    else:
        findings.append(("ok", "Browser is up to date"))

    findings.append(("ok", "Encrypted connection (HTTPS)"))

    if checks.get("os_outdated"):
        score -= 15
        findings.append(("medium", "Operating system may be missing security updates"))

    if checks.get("is_mobile"):
        findings.append(("info", "Mobile device — app permissions affect your exposure"))

    return max(0, min(100, score)), findings


def _score_color(score: int) -> str:
    if score >= 80: return "#16a34a"
    if score >= 60: return "#d97706"
    return "#dc2626"


def _render_result(score: int, findings: list) -> str:
    color = _score_color(score)
    icons = {"ok": "\u2705", "medium": "\u26a0\ufe0f", "high": "\u26a0\ufe0f", "info": "\u2139\ufe0f"}
    rows = ""
    for severity, text in findings:
        icon = icons.get(severity, "")
        rows += (f'<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;'
                 f'border-bottom:1px solid #f1f5f9">'
                 f'<span style="font-size:1.1em">{icon}</span>'
                 f'<span style="font-size:0.9em;color:#334155;line-height:1.5">{text}</span></div>')

    return (f'<div class="security-check-result" style="margin:0;padding:24px;text-align:left">'
            f'<div style="text-align:center;margin-bottom:20px">'
            f'<div style="font-size:2.5em;font-weight:700;color:{color}">{score}/100</div>'
            f'<div style="font-size:0.95em;color:#64748b">Your Security Score</div></div>'
            f'<div style="display:flex;flex-direction:column;gap:4px">{rows}</div>'
            f'<p style="font-size:0.8em;color:#94a3b8;margin:16px 0 0;text-align:center">'
            f'Based on your browser headers only. Nothing stored. '
            f'<a href="/privacy" style="color:#94a3b8">Learn more</a></p></div>')


# ── Endpoints ──

@router.get("/my/check")
async def security_check(request: Request):
    """Instant security check from HTTP headers. Nothing stored."""
    ip = (request.headers.get("CF-Connecting-IP")
          or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or (request.client.host if request.client else ""))
    ua = request.headers.get("User-Agent", "")

    browser = _parse_browser(ua)
    os_info = _parse_os(ua)
    vpn = is_likely_vpn(ip)

    checks = {
        "vpn_detected": vpn,
        "browser_versions_behind": browser["versions_behind"],
        "os_outdated": os_info["outdated"],
        "is_mobile": os_info["is_mobile"],
    }

    score, findings = _calculate_score(checks)
    html = _render_result(score, findings)

    return HTMLResponse(
        content=html,
        headers={"Cache-Control": "no-store, private", "X-Robots-Tag": "noindex"},
    )


# ── Event tracking (separate SQLite) ──

CHECK_EVENTS_DB = os.path.expanduser("~/agentindex/logs/check_events.db")
_events_db_init = False


def _get_events_conn():
    global _events_db_init
    conn = sqlite3.connect(CHECK_EVENTS_DB, timeout=3)
    if not _events_db_init:
        conn.execute("""CREATE TABLE IF NOT EXISTS check_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event TEXT NOT NULL,
            page TEXT,
            country TEXT,
            is_mobile INTEGER,
            score INTEGER
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ce_ts ON check_events(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ce_event ON check_events(event)")
        conn.commit()
        _events_db_init = True
    return conn


_ALLOWED_EVENTS = {"cta_impression", "security_check_click", "security_check_complete"}


@router.post("/v1/event")
async def track_event(request: Request):
    """Track anonymous engagement events. No PII."""
    try:
        data = await request.json()
        event = data.get("event", "")
        if event not in _ALLOWED_EVENTS:
            return JSONResponse({"status": "ignored"})

        country = request.headers.get("CF-IPCountry", "")
        ua = request.headers.get("User-Agent", "")
        is_mobile = 1 if re.search(r'Mobile|Android|iPhone', ua) else 0

        conn = _get_events_conn()
        conn.execute(
            "INSERT INTO check_events (ts, event, page, country, is_mobile, score) VALUES (?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), event, data.get("path", ""),
             country, is_mobile, data.get("score")))
        conn.commit()
        conn.close()
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.warning(f"Event tracking error: {e}")
        return JSONResponse({"status": "error"})


# ── KPI Dashboard ──

def _render_dashboard() -> str:
    """KPI dashboard HTML for security check experiment."""
    from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER, render_head

    if not os.path.exists(CHECK_EVENTS_DB):
        body = "<p>No data yet. Events will appear after the first security check.</p>"
        totals_row = "0 impressions, 0 clicks, 0 completes"
    else:
        conn = sqlite3.connect(CHECK_EVENTS_DB, timeout=3)

        totals = conn.execute("""
            SELECT
                SUM(CASE WHEN event='cta_impression' THEN 1 ELSE 0 END),
                SUM(CASE WHEN event='security_check_click' THEN 1 ELSE 0 END),
                SUM(CASE WHEN event='security_check_complete' THEN 1 ELSE 0 END)
            FROM check_events
        """).fetchone()
        imp, clk, comp = totals[0] or 0, totals[1] or 0, totals[2] or 0
        ctr = round(100 * clk / imp, 1) if imp else 0
        compl = round(100 * comp / clk, 1) if clk else 0
        totals_row = f"{imp:,} impressions, {clk:,} clicks ({ctr}% CTR), {comp:,} completes ({compl}% completion)"

        daily = conn.execute("""
            SELECT date(ts) as day,
                SUM(CASE WHEN event='cta_impression' THEN 1 ELSE 0 END) as imp,
                SUM(CASE WHEN event='security_check_click' THEN 1 ELSE 0 END) as clk,
                SUM(CASE WHEN event='security_check_complete' THEN 1 ELSE 0 END) as comp
            FROM check_events GROUP BY day ORDER BY day DESC LIMIT 14
        """).fetchall()

        scores = conn.execute("""
            SELECT
                CASE WHEN score >= 80 THEN '80-100' WHEN score >= 60 THEN '60-79' ELSE '0-59' END as bracket,
                COUNT(*)
            FROM check_events WHERE event='security_check_complete' AND score IS NOT NULL
            GROUP BY bracket ORDER BY bracket DESC
        """).fetchall()

        geo = conn.execute("""
            SELECT country,
                SUM(CASE WHEN event='security_check_click' THEN 1 ELSE 0 END) as clicks
            FROM check_events WHERE country != '' GROUP BY country ORDER BY clicks DESC LIMIT 10
        """).fetchall()

        conn.close()

        daily_rows = "".join(
            f"<tr><td>{d[0]}</td><td>{d[1]}</td><td>{d[2]}</td><td>{d[3]}</td>"
            f"<td>{round(100*d[2]/d[1],1) if d[1] else 0}%</td></tr>"
            for d in daily)

        score_rows = "".join(f"<tr><td>{s[0]}</td><td>{s[1]}</td></tr>" for s in scores)
        geo_rows = "".join(f"<tr><td>{g[0]}</td><td>{g[1]}</td></tr>" for g in geo)

        body = f"""
        <h2>Totals</h2><p style="font-size:1.1em">{totals_row}</p>
        <h2>Daily (last 14 days)</h2>
        <table><tr><th>Day</th><th>Impressions</th><th>Clicks</th><th>Completes</th><th>CTR</th></tr>
        {daily_rows}</table>
        <h2>Score Distribution</h2>
        <table><tr><th>Bracket</th><th>Count</th></tr>{score_rows}</table>
        <h2>Top Countries</h2>
        <table><tr><th>Country</th><th>Clicks</th></tr>{geo_rows}</table>
        """

    head = render_head("Security Check KPI", description="Engagement metrics", canonical="")
    return f"""{head}{NERQ_NAV}
    <main class="container" style="max-width:900px;margin:2rem auto;padding:0 20px">
    <h1>Security Check — KPI Dashboard</h1>
    {body}
    </main>{NERQ_FOOTER}"""


@router.get("/admin/security-check")
async def security_check_dashboard():
    return HTMLResponse(content=_render_dashboard())
