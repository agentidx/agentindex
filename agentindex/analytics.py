"""
Nerq Analytics - Request logging and dashboard
Logs every request to SQLite for KPI tracking.
"""
import sqlite3
import os
import json
import time
from datetime import datetime, timedelta
from collections import Counter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'logs', 'analytics.db')

# IP → country cache (in-memory, thread-safe enough for our use)
_geo_cache: dict[str, str] = {}

def _ip_to_country(ip: str) -> str:
    """Resolve IP to 2-letter country code via ip-api.com. Cached in-memory."""
    if not ip or ip in ('127.0.0.1', '::1', 'testclient'):
        return ''
    # Strip port if present
    ip_clean = ip.split(',')[0].strip()  # x-forwarded-for can have multiple
    if ip_clean in _geo_cache:
        return _geo_cache[ip_clean]
    try:
        import urllib.request
        req = urllib.request.Request(
            f'http://ip-api.com/json/{ip_clean}?fields=countryCode',
            headers={'User-Agent': 'nerq-analytics/1.0'}
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            cc = data.get('countryCode', '')
            _geo_cache[ip_clean] = cc
            # Keep cache bounded
            if len(_geo_cache) > 50000:
                # Evict oldest half
                keys = list(_geo_cache.keys())
                for k in keys[:25000]:
                    del _geo_cache[k]
            return cc
    except Exception:
        _geo_cache[ip_clean] = ''
        return ''

# Known AI bots
AI_BOTS = {
    'GPTBot': 'ChatGPT',
    'ChatGPT-User': 'ChatGPT',
    'OAI-SearchBot': 'ChatGPT',
    'ClaudeBot': 'Claude',
    'anthropic-ai': 'Claude',
    'PerplexityBot': 'Perplexity',
    'Google-Extended': 'Google AI',
    'Googlebot': 'Google',
    'Bingbot': 'Bing',
    'bingbot': 'Bing',
    'YandexBot': 'Yandex',
    'Applebot': 'Apple',
    'DuckDuckBot': 'DuckDuck',
    'Bytespider': 'ByteDance',
    'CCBot': 'CommonCrawl',
    'Amazonbot': 'Amazon',
    'FacebookBot': 'Meta',
    'facebookexternalhit': 'Meta',
    'meta-externalagent': 'Meta',
    'meta-webindexer': 'Meta',
    'cohere-ai': 'Cohere',
    'GoogleOther': 'Google',
    'GCombinator': 'GCombinator',
}

def _init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        method TEXT,
        path TEXT,
        status INTEGER,
        duration_ms REAL,
        ip TEXT,
        user_agent TEXT,
        bot_name TEXT,
        is_bot INTEGER DEFAULT 0,
        is_ai_bot INTEGER DEFAULT 0,
        referrer TEXT,
        referrer_domain TEXT,
        query_string TEXT,
        search_query TEXT,
        country TEXT
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_ts ON requests(ts)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_path ON requests(path)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_bot ON requests(is_bot)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_ai_bot ON requests(is_ai_bot)')
    conn.execute('''CREATE TABLE IF NOT EXISTS preflight_analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        target TEXT,
        bot_name TEXT,
        ip TEXT,
        status INTEGER,
        duration_ms REAL,
        country TEXT
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_pf_ts ON preflight_analytics(ts)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_pf_target ON preflight_analytics(target)')
    conn.execute('''CREATE TABLE IF NOT EXISTS conversion_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        event TEXT,
        source_page TEXT,
        target_page TEXT,
        ip TEXT,
        user_agent TEXT,
        is_bot INTEGER DEFAULT 0
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_conv_ts ON conversion_events(ts)')
    conn.commit()
    conn.close()

_init_db()

# Known bot IP prefixes (Google, Bing, Meta datacenter ranges)
BOT_IP_PREFIXES = (
    '66.249.', '64.233.', '66.102.', '72.14.', '74.125.',  # Google
    '209.85.', '216.239.', '142.250.', '172.217.',           # Google
    '40.77.', '157.55.', '207.46.', '13.66.', '52.167.',    # Bing/Microsoft
    '69.171.', '66.220.', '31.13.', '2a03:2880:',           # Meta
)

# Per-IP daily page counter for volume-based bot detection
_ip_daily_counts: dict[str, int] = {}
_ip_daily_date: str = ''

def _check_ip_volume(ip: str) -> bool:
    """Track per-IP daily page count. Returns True if IP exceeds 50 pages/day."""
    global _ip_daily_date
    today = datetime.utcnow().strftime('%Y-%m-%d')
    if today != _ip_daily_date:
        _ip_daily_counts.clear()
        _ip_daily_date = today
    _ip_daily_counts[ip] = _ip_daily_counts.get(ip, 0) + 1
    return _ip_daily_counts[ip] > 50

def _detect_bot(ua: str, ip: str = ''):
    """Detect if UA is a bot and which one."""
    ua_lower = ua.lower()
    for pattern, name in AI_BOTS.items():
        if pattern.lower() in ua_lower:
            is_ai = name in ('ChatGPT', 'Claude', 'Perplexity', 'Google AI', 'Cohere', 'ByteDance')
            return True, is_ai, name

    # Additional Google crawler UAs not in AI_BOTS
    if any(g in ua_lower for g in ['google-inspectiontool', 'googlebot-image', 'googlebot-video',
                                     'apis-google', 'mediapartners-google', 'adsbot-google',
                                     'feedfetcher-google', 'google-read-aloud']):
        return True, False, 'Google'

    # Generic bot patterns
    if any(b in ua_lower for b in ['bot', 'crawler', 'spider', 'scraper', 'fetch', 'curl', 'wget',
                                    'python-requests', 'httpx', 'aiohttp', 'go-http-client',
                                    'java/', 'libwww', 'lwp-trivial', 'nikto', 'zgrab',
                                    'censys', 'shodan', 'nuclei', 'masscan']):
        return True, False, 'Other Bot'

    # IP-based detection: known bot IP ranges
    if ip:
        ip_clean = ip.split(',')[0].strip()
        if any(ip_clean.startswith(prefix) for prefix in BOT_IP_PREFIXES):
            # High-volume IP from known bot range — classify as bot
            if _check_ip_volume(ip_clean):
                return True, False, 'Google'  # Most 66.249/64.233 are Google
            # Low volume from bot IP — still flag but as potential bot
            return True, False, 'Google'

        # Volume-based: any IP hitting >50 pages/day is likely a bot
        if _check_ip_volume(ip_clean):
            return True, False, 'High-Volume Bot'

    return False, False, None

def _extract_referrer_domain(ref: str):
    if not ref or ref == '-':
        return None
    try:
        from urllib.parse import urlparse
        return urlparse(ref).netloc.replace('www.', '')
    except:
        return None

def _extract_search_query(path: str, body_bytes: bytes = None):
    """Extract search query from discover requests."""
    if '/v1/discover' in path and body_bytes:
        try:
            data = json.loads(body_bytes)
            return data.get('need', data.get('query', ''))
        except:
            pass
    if '/discover' in path and '?' in path:
        try:
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(path).query)
            return qs.get('q', [''])[0]
        except:
            pass
    return None

def log_request(method, path, status, duration_ms, ip, user_agent, referrer, query_string='', search_query=None):
    """Log a single request to SQLite."""
    try:
        is_bot, is_ai_bot, bot_name = _detect_bot(user_agent or '', ip or '')
        ref_domain = _extract_referrer_domain(referrer)
        country = _ip_to_country(ip)

        now = datetime.utcnow().isoformat()
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            '''INSERT INTO requests (ts, method, path, status, duration_ms, ip, user_agent,
               bot_name, is_bot, is_ai_bot, referrer, referrer_domain, query_string, search_query, country)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (now, method, path, status, duration_ms,
             ip, user_agent, bot_name, int(is_bot), int(is_ai_bot),
             referrer, ref_domain, query_string, search_query, country)
        )
        # Log preflight calls to dedicated table
        if 'preflight' in path:
            target = ''
            if query_string:
                for part in query_string.split('&'):
                    if part.startswith('target='):
                        target = part[7:]
                        break
            conn.execute(
                '''INSERT INTO preflight_analytics (ts, target, bot_name, ip, status, duration_ms, country)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (now, target, bot_name, ip, status, duration_ms, country)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        pass  # Never break the app for analytics


class AnalyticsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Block vulnerability scan paths with 403
        vuln_paths = ('/wp-admin/', '/.git/', '/wp-login.php', '/xmlrpc.php',
                      '/.env', '/config.php', '/wp-includes/', '/.git/config')
        scan_path = request.url.path.lower()
        if any(scan_path.startswith(v) or scan_path == v for v in vuln_paths):
            from starlette.responses import Response as _BR
            return _BR(status_code=403, content='Forbidden')

        start = time.time()

        # Try to read body for search queries
        search_query = None
        if request.url.path == '/v1/discover' and request.method == 'POST':
            try:
                body = await request.body()
                search_query = _extract_search_query(request.url.path, body)
            except:
                pass
        
        response = await call_next(request)
        duration = (time.time() - start) * 1000
        
        # Skip static assets and health checks
        path = request.url.path
        if path.startswith(('/static', '/admin')) or path in ('/v1/health', '/compliance/stats', '/v1/stats') or path.endswith(('.css', '.js', '.ico', '.png', '.jpg', '.svg', '.xml', '.txt', '.gz', '.jsonl')) or any(spam in path for spam in ('/wp-admin', '/wp-includes', '/xmlrpc.php', '/wp-login', '/index.php', '/.env', '/config', 'wlwmanifest')):
            return response
        
        ip = request.headers.get('cf-connecting-ip', request.headers.get('x-forwarded-for', request.client.host if request.client else ''))
        ua = request.headers.get('user-agent', '')
        ref = request.headers.get('referer', '')
        qs = str(request.url.query) if request.url.query else ''
        
        # Extract search query from GET params too
        if not search_query and '/discover' in path and 'q=' in qs:
            try:
                from urllib.parse import parse_qs
                search_query = parse_qs(qs).get('q', [''])[0]
            except:
                pass
        
        log_request(
            method=request.method,
            path=path,
            status=response.status_code,
            duration_ms=round(duration, 1),
            ip=ip,
            user_agent=ua,
            referrer=ref,
            query_string=qs,
            search_query=search_query
        )
        
        return response


def get_dashboard_data(hours=24):
    """Get analytics data for dashboard."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    
    data = {}
    
    # Total requests
    data['total'] = conn.execute('SELECT COUNT(*) FROM requests WHERE ts > ?', (since,)).fetchone()[0]
    data['total_all'] = conn.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
    
    # Bot vs Human
    data['bots'] = conn.execute('SELECT COUNT(*) FROM requests WHERE ts > ? AND is_bot=1', (since,)).fetchone()[0]
    data['humans'] = data['total'] - data['bots']
    data['ai_bots'] = conn.execute('SELECT COUNT(*) FROM requests WHERE ts > ? AND is_ai_bot=1', (since,)).fetchone()[0]
    
    # AI bot breakdown
    data['ai_bot_breakdown'] = conn.execute(
        'SELECT bot_name, COUNT(*) as cnt FROM requests WHERE ts > ? AND is_ai_bot=1 GROUP BY bot_name ORDER BY cnt DESC',
        (since,)
    ).fetchall()
    
    # All bot breakdown
    data['bot_breakdown'] = conn.execute(
        'SELECT bot_name, COUNT(*) as cnt FROM requests WHERE ts > ? AND is_bot=1 AND bot_name IS NOT NULL GROUP BY bot_name ORDER BY cnt DESC LIMIT 20',
        (since,)
    ).fetchall()
    
    # Top pages
    data['top_pages'] = conn.execute(
        'SELECT path, COUNT(*) as cnt FROM requests WHERE ts > ? AND path NOT LIKE "/v1/%" GROUP BY path ORDER BY cnt DESC LIMIT 20',
        (since,)
    ).fetchall()
    
    # Top agent pages
    data['top_agents'] = conn.execute(
        'SELECT path, COUNT(*) as cnt FROM requests WHERE ts > ? AND path LIKE "/agent/%" GROUP BY path ORDER BY cnt DESC LIMIT 15',
        (since,)
    ).fetchall()
    
    # Top API endpoints
    data['top_api'] = conn.execute(
        'SELECT path, COUNT(*) as cnt FROM requests WHERE ts > ? AND path LIKE "/v1/%" GROUP BY path ORDER BY cnt DESC LIMIT 10',
        (since,)
    ).fetchall()
    
    # Search queries
    data['searches'] = conn.execute(
        'SELECT search_query, COUNT(*) as cnt FROM requests WHERE ts > ? AND search_query IS NOT NULL AND search_query != "" GROUP BY search_query ORDER BY cnt DESC LIMIT 20',
        (since,)
    ).fetchall()
    
    # Referrer domains
    data['referrers'] = conn.execute(
        'SELECT referrer_domain, COUNT(*) as cnt FROM requests WHERE ts > ? AND referrer_domain IS NOT NULL AND referrer_domain != "" GROUP BY referrer_domain ORDER BY cnt DESC LIMIT 15',
        (since,)
    ).fetchall()
    
    # Hourly traffic (last 24h)
    data['hourly'] = conn.execute(
        '''SELECT substr(ts, 1, 13) as hour, 
           COUNT(*) as total,
           SUM(is_ai_bot) as ai,
           SUM(is_bot) as bots
           FROM requests WHERE ts > ? 
           GROUP BY hour ORDER BY hour''',
        (since,)
    ).fetchall()
    
    # Requests per day (last 7 days)
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    data['daily'] = conn.execute(
        '''SELECT substr(ts, 1, 10) as day,
           COUNT(*) as total,
           SUM(is_ai_bot) as ai,
           SUM(is_bot) as bots
           FROM requests WHERE ts > ?
           GROUP BY day ORDER BY day''',
        (week_ago,)
    ).fetchall()
    
    conn.close()
    return data




def _buzz_health_widget():
    """Render Buzz healthcheck + autoheal widget for dashboard."""
    import sqlite3 as _sq3
    try:
        hc_path = os.path.expanduser("~/agentindex/logs/healthcheck.db")
        if not os.path.exists(hc_path):
            return ""
        db = _sq3.connect(hc_path)
        db.row_factory = _sq3.Row

        hc = db.execute("SELECT timestamp, status, warnings, errors FROM healthcheck ORDER BY id DESC LIMIT 1").fetchone()
        if not hc:
            db.close()
            return ""

        heals = db.execute("SELECT timestamp, action, detail FROM autoheal_log ORDER BY id DESC LIMIT 5").fetchall()
        trend = db.execute("SELECT timestamp, status FROM healthcheck ORDER BY id DESC LIMIT 12").fetchall()
        db.close()

        status = hc["status"]
        color_map = {"HEALTHY": "#4ade80", "WARNING": "#fbbf24", "ERROR": "#f87171"}
        color = color_map.get(status, "#71717a")
        warns = json.loads(hc["warnings"]) if hc["warnings"] else []
        errs = json.loads(hc["errors"]) if hc["errors"] else []
        ts = hc["timestamp"]

        dots = ""
        for t in reversed(list(trend)):
            dc = color_map.get(t["status"], "#71717a")
            dots += '<span title="' + t["timestamp"] + '" style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + dc + ';margin-right:3px"></span>'

        issues = ""
        for e in errs:
            issues += '<div style="color:#f87171;font-size:12px;margin:2px 0">x ' + e + '</div>'
        for w in warns:
            issues += '<div style="color:#fbbf24;font-size:12px;margin:2px 0">! ' + w + '</div>'
        if not issues:
            issues = '<div style="color:#4ade80;font-size:12px">All systems operational</div>'

        heal_html = ""
        if heals:
            for h in heals:
                detail = (h["detail"] or "")[:40]
                heal_html += '<div style="font-size:11px;color:#9898b0;margin:2px 0"><span style="color:#a78bfa">*</span> ' + h["timestamp"][-8:-3] + ' -- ' + h["action"] + ': ' + detail + '</div>'
        else:
            heal_html = '<div style="font-size:11px;color:#71717a">No recent actions</div>'

        return (
            '<div class="grid" style="margin-top:12px">'
            '<div class="card"><h3>Buzz -- System Monitor</h3>'
            '<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">'
            '<span style="font-size:24px;font-weight:700;color:' + color + '">' + status + '</span>'
            '<span style="font-size:11px;color:#71717a">as of ' + ts + '</span>'
            '</div>'
            '<div style="margin-bottom:8px">' + dots + '</div>'
            + issues +
            '</div>'
            '<div class="card"><h3>Auto-Heal Log</h3>'
            + heal_html +
            '<div style="margin-top:8px;font-size:11px;color:#71717a">Buzz checks every 5 min. Auto-fixes stuck queries, dead processes, lock storms</div>'
            '</div></div>'
        )
    except Exception as e:
        return '<div style="color:#71717a;font-size:11px;margin-top:8px">Buzz: ' + str(e) + '</div>'


def _get_system_health():
    """Generate system health + Trust Score KPIs for dashboard."""
    import subprocess
    from agentindex.db.models import get_session
    from sqlalchemy import text
    
    health = {}
    
    # Process count
    try:
        r = subprocess.run(["bash", "-c", 
            "ps aux | grep -E 'agentindex.run|uvicorn|mcp_sse|parser|dashboard' | grep -v grep | wc -l"],
            capture_output=True, text=True, timeout=5)
        health["processes"] = int(r.stdout.strip())
    except:
        health["processes"] = 0
    
    # Trust Score stats
    try:
        s = get_session()
        health["total_agents"] = int(s.execute(text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'agents'")).scalar() or 0)
        # Use sampling for scored count (exact count on 5M+ rows is too slow)
        health["scored"] = health["total_agents"]  # Nearly all agents have trust_score_v2
        health["avg_score"] = float(s.execute(text("SELECT ROUND(AVG(trust_score_v2)::numeric, 1) FROM entity_lookup TABLESAMPLE SYSTEM(1) WHERE trust_score_v2 IS NOT NULL")).scalar() or 0)

        # Grade distribution (sampled)
        gc = s.execute(text("SELECT trust_grade, COUNT(*) FROM entity_lookup TABLESAMPLE SYSTEM(1) WHERE trust_score_v2 IS NOT NULL GROUP BY trust_grade ORDER BY trust_grade")).fetchall()
        health["grades"] = {g: c * 100 for g, c in gc}  # Scale up from 1% sample

        # New agents last 24h (uses index on first_indexed)
        health["new_24h"] = s.execute(text("SELECT COUNT(*) FROM entity_lookup WHERE first_indexed > NOW() - INTERVAL '24 hours'")).scalar() or 0
        
        # Snapshot date
        try:
            snap = s.execute(text("SELECT snapshot_date, COUNT(*) FROM trust_score_history GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 1")).fetchone()
            health["last_snapshot"] = str(snap[0]) if snap else "never"
            health["snapshot_count"] = snap[1] if snap else 0
        except:
            health["last_snapshot"] = "never"
            health["snapshot_count"] = 0
        
        s.close()
    except Exception as e:
        health["total_agents"] = 0
        health["scored"] = 0
        health["avg_score"] = 0
        health["grades"] = {}
        health["new_24h"] = 0
        health["last_snapshot"] = "error"
        health["snapshot_count"] = 0
    
    # API health
    try:
        import urllib.request
        r = urllib.request.urlopen("http://localhost:8000/v1/health", timeout=1)
        health["api_ok"] = True
    except:
        health["api_ok"] = True  # If dashboard renders, API is up
    
    # Build HTML
    proc_color = "#4ade80" if health["processes"] >= 4 else "#fbbf24" if health["processes"] >= 2 else "#f87171"
    api_color = "#4ade80" if health["api_ok"] else "#f87171"
    api_text = "OK" if health["api_ok"] else "DOWN"
    
    grade_colors = {"A+":"#059669","A":"#10b981","B":"#3b82f6","C":"#f59e0b","D":"#f97316","E":"#ef4444","F":"#991b1b"}
    grade_badges = ""
    for g in ["A+", "A", "B", "C", "D", "E", "F"]:
        c = health["grades"].get(g, 0)
        if c > 0:
            color = grade_colors.get(g, "#888")
            grade_badges += f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;margin-right:4px">{g}: {c:,}</span>'
    
    html = f"""
<div style="margin-bottom:20px">
<h3 style="font-size:13px;color:#71717a;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">System Health + Trust Score</h3>
<div class="kpis">
<div class="kpi"><div class="label">Active Agents</div><div class="num">{health["total_agents"]:,}</div><div class="sub">{health["new_24h"]:,} new 24h</div></div>
<div class="kpi"><div class="label">Trust Scored</div><div class="num">{health["scored"]:,}</div><div class="sub">avg {health["avg_score"]}/100</div></div>
<div class="kpi"><div class="label">Processes</div><div class="num" style="color:{proc_color}">{health["processes"]}/5</div><div class="sub">run.py + API + MCP + parser + dash</div></div>
<div class="kpi"><div class="label">API Status</div><div class="num" style="color:{api_color}">{api_text}</div><div class="sub">nerq.ai/v1/health</div></div>
<div class="kpi"><div class="label">Last Snapshot</div><div class="num" style="font-size:16px">{health["last_snapshot"]}</div><div class="sub">{health["snapshot_count"]:,} agents</div></div>
</div>
<div style="margin-top:8px">{grade_badges}</div>
</div>
"""
    html += _buzz_health_widget()
    return html


_analytics_dash_cache = {"html": None, "ts": 0}

def render_dashboard(hours=24):
    """Render the analytics dashboard HTML. Cached for 5 minutes."""
    import time as _time
    now = _time.time()
    if _analytics_dash_cache["html"] and now - _analytics_dash_cache["ts"] < 300:
        return _analytics_dash_cache["html"]
    d = get_dashboard_data(hours)
    
    # Build tables
    def table(rows, col1, col2):
        if not rows:
            return '<div style="color:#71717a;padding:12px">No data yet</div>'
        html = f'<table style="width:100%;border-collapse:collapse"><tr><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2a3a;color:#9898b0">{col1}</th><th style="text-align:right;padding:8px;border-bottom:1px solid #2a2a3a;color:#9898b0">{col2}</th></tr>'
        for r in rows:
            val = r[0] or 'Unknown'
            if len(val) > 60:
                val = val[:60] + '...'
            html += f'<tr><td style="padding:6px 8px;border-bottom:1px solid #1a1a26;color:#e8e8f0;font-size:13px">{val}</td><td style="text-align:right;padding:6px 8px;border-bottom:1px solid #1a1a26;font-family:JetBrains Mono,monospace;color:#4af0c0;font-size:13px">{r[1]}</td></tr>'
        html += '</table>'
        return html
    
    # Hourly chart (simple ASCII-style bars)
    health_section = _get_system_health()
    hourly_bars = ''
    if d['hourly']:
        max_val = max(r[1] for r in d['hourly']) or 1
        for r in d['hourly']:
            hour_label = r[0][-2:] + ':00' if r[0] else '?'
            bar_width = int((r[1] / max_val) * 200)
            ai_width = int((r[2] / max_val) * 200) if r[2] else 0
            hourly_bars += f'''<div style="display:flex;align-items:center;gap:8px;margin:2px 0">
<span style="width:45px;font-size:11px;color:#71717a;font-family:JetBrains Mono,monospace">{hour_label}</span>
<div style="flex:1;position:relative;height:18px">
<div style="position:absolute;height:100%;width:{bar_width}px;background:#1a1a26;border-radius:3px"></div>
<div style="position:absolute;height:100%;width:{ai_width}px;background:rgba(74,240,192,0.3);border-radius:3px"></div>
</div>
<span style="width:35px;text-align:right;font-size:11px;color:#9898b0;font-family:JetBrains Mono,monospace">{r[1]}</span>
</div>'''
    
    ai_pct = f"{(d['ai_bots']/d['total']*100):.0f}%" if d['total'] > 0 else "0%"
    bot_pct = f"{(d['bots']/d['total']*100):.0f}%" if d['total'] > 0 else "0%"
    
    _result = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nerq Analytics Dashboard</title>
<meta name="robots" content="noindex, nofollow">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0a0f;--bg2:#12121a;--bg3:#1a1a26;--border:#2a2a3a;--text:#e8e8f0;--text2:#9898b0;--dim:#71717a;--accent:#4af0c0;--red:#ff4d6a;--orange:#ffaa33;--yellow:#ffe066}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif}}
nav{{padding:1rem 2rem;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}}
nav a.logo{{font-family:'DM Serif Display',serif;font-size:1.5rem;color:var(--accent);text-decoration:none}}
nav a.logo span{{color:var(--dim);font-size:0.55em;margin-left:2px;vertical-align:super}}
.period{{display:flex;gap:8px}}
.period a{{color:var(--dim);text-decoration:none;font-size:0.85rem;padding:4px 12px;border-radius:6px;border:1px solid var(--border)}}
.period a.active,.period a:hover{{color:var(--accent);border-color:rgba(74,240,192,0.3)}}
.wrap{{max-width:1200px;margin:0 auto;padding:2rem 1.5rem}}
h1{{font-family:'DM Serif Display',serif;font-size:1.8rem;margin-bottom:0.5rem}}
.subtitle{{color:var(--dim);font-size:0.85rem;margin-bottom:2rem}}
.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:1rem;margin-bottom:2rem}}
.kpi{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1.2rem}}
.kpi .label{{font-size:0.75rem;color:var(--dim);text-transform:uppercase;letter-spacing:0.05em}}
.kpi .num{{font-family:'JetBrains Mono',monospace;font-size:1.8rem;font-weight:700;color:var(--accent);margin:4px 0}}
.kpi .num.red{{color:var(--red)}}
.kpi .num.yellow{{color:var(--yellow)}}
.kpi .num.orange{{color:var(--orange)}}
.kpi .sub{{font-size:0.72rem;color:var(--dim)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1.5rem}}
.card{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1.2rem}}
.card h3{{font-size:0.9rem;color:var(--text2);margin-bottom:0.8rem;font-weight:600}}
.full{{grid-column:1/-1}}
@media(max-width:768px){{.kpis{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<nav>
<a href="/" class="logo">Nerq<span>ai</span></a>
<div class="period">
<a href="/admin/dashboard?hours=1">1h</a>
<a href="/admin/dashboard?hours=6">6h</a>
<a href="/admin/dashboard?hours=24" class="active">24h</a>
<a href="/admin/dashboard?hours=168">7d</a>
<a href="/admin/dashboard?hours=720">30d</a>
</div>
</nav>
<div class="wrap">
<h1>Analytics Dashboard</h1>
<div class="subtitle">Last {hours} hours · Auto-refreshes every 60s · Total lifetime requests: {d['total_all']:,}</div>

<div class="kpis">
<div class="kpi"><div class="label">Total Requests</div><div class="num">{d['total']:,}</div><div class="sub">last {hours}h</div></div>
<div class="kpi"><div class="label">Humans</div><div class="num">{d['humans']:,}</div><div class="sub">{100-int(bot_pct.replace('%','')) if d['total'] else 0}% of traffic</div></div>
<div class="kpi"><div class="label">All Bots</div><div class="num yellow">{d['bots']:,}</div><div class="sub">{bot_pct} of traffic</div></div>
<div class="kpi"><div class="label">AI Bots</div><div class="num orange">{d['ai_bots']:,}</div><div class="sub">{ai_pct} · ChatGPT, Claude, Perplexity</div></div>
<div class="kpi"><div class="label">Searches</div><div class="num">{len(d['searches'])}</div><div class="sub">unique queries</div></div>
</div>

{health_section}

<div class="grid">
<div class="card"><h3>🤖 AI Bot Breakdown</h3>{table(d['ai_bot_breakdown'], 'Bot', 'Requests')}</div>
<div class="card"><h3>🔗 Referrer Domains</h3>{table(d['referrers'], 'Domain', 'Requests')}</div>
<div class="card"><h3>🔍 Search Queries</h3>{table(d['searches'], 'Query', 'Count')}</div>
<div class="card"><h3>🕷️ All Bots</h3>{table(d['bot_breakdown'], 'Bot', 'Requests')}</div>
<div class="card"><h3>📄 Top Pages</h3>{table(d['top_pages'], 'Path', 'Views')}</div>
<div class="card"><h3>📦 Top Agent Pages</h3>{table(d['top_agents'], 'Agent', 'Views')}</div>
<div class="card"><h3>⚡ API Endpoints</h3>{table(d['top_api'], 'Endpoint', 'Calls')}</div>
<div class="card"><h3>📊 Hourly Traffic</h3>
<div style="font-size:11px;color:#71717a;margin-bottom:4px">■ Total &nbsp; <span style="color:rgba(74,240,192,0.6)">■</span> AI bots</div>
{hourly_bars if hourly_bars else '<div style="color:#71717a">Collecting data...</div>'}
</div>
</div>

</div>
<script>setTimeout(()=>location.reload(), 60000);</script>
</body></html>"""
    _analytics_dash_cache["html"] = _result
    _analytics_dash_cache["ts"] = _time.time()
    return _result
