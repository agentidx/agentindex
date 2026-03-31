"""
ZARQ Operations Dashboard — Single-page ops dashboard for founder monitoring.
Route: /zarq/dashboard
Auth: Bearer ZARQ_METRICS_TOKEN
"""

import glob
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("zarq.dashboard")

METRICS_TOKEN = os.getenv("ZARQ_METRICS_TOKEN", "zarq-internal-2026")
CRYPTO_DB = os.path.join(os.path.dirname(__file__), "crypto", "crypto_trust.db")
API_LOG_DB = os.path.join(os.path.dirname(__file__), "crypto", "zarq_api_log.db")
TASKS_DIR = os.path.join(os.path.dirname(__file__), "..", "tasks")
REDIS_CLI = "/opt/homebrew/bin/redis-cli"

router_dashboard = APIRouter(tags=["dashboard"])


def _check_auth(request: Request) -> bool:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.query_params.get("token", "")
    return token == METRICS_TOKEN


def _redis_ping() -> bool:
    try:
        r = subprocess.run([REDIS_CLI, "PING"], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() == "PONG"
    except Exception:
        return False


def _pg_status() -> dict:
    try:
        from agentindex.db.models import get_session
        s = get_session()
        from sqlalchemy import text
        row = s.execute(text("SELECT COUNT(*) FROM agents")).scalar()
        s.close()
        return {"status": "ok", "agents": row}
    except Exception as e:
        return {"status": "error", "error": str(e)[:100]}


def _launchagent_status(label: str) -> str:
    try:
        r = subprocess.run(["launchctl", "list", label], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if '"PID"' in line or "PID" in line:
                    return "running"
            return "loaded"
        return "not loaded"
    except Exception:
        return "unknown"


def _circuit_breaker_states() -> dict:
    try:
        from agentindex.circuit_breaker import _circuits
        return {name: {"state": c["state"], "failures": c["consecutive_failures"],
                       "total_failures": c["total_failures"]}
                for name, c in _circuits.items()}
    except Exception:
        return {}


def _disk_usage() -> dict:
    total, used, free = shutil.disk_usage("/")
    return {
        "total_gb": round(total / (1024**3), 1),
        "used_gb": round(used / (1024**3), 1),
        "free_gb": round(free / (1024**3), 1),
        "used_pct": round(used / total * 100, 1),
    }


def _api_traffic() -> dict:
    try:
        conn = sqlite3.connect(API_LOG_DB)
        conn.row_factory = sqlite3.Row
        from datetime import timedelta
        now_dt = datetime.now(timezone.utc)
        cutoff_24h = (now_dt - timedelta(hours=24)).isoformat()
        cutoff_1h = (now_dt - timedelta(hours=1)).isoformat()
        cutoff_10m = (now_dt - timedelta(minutes=10)).isoformat()

        r24 = conn.execute("SELECT COUNT(*) FROM api_log WHERE timestamp >= ?", [cutoff_24h]).fetchone()[0]
        r1 = conn.execute("SELECT COUNT(*) FROM api_log WHERE timestamp >= ?", [cutoff_1h]).fetchone()[0]
        uips = conn.execute("SELECT COUNT(DISTINCT ip_hash) FROM api_log WHERE timestamp >= ?", [cutoff_24h]).fetchone()[0]

        latencies = [r[0] for r in conn.execute(
            "SELECT latency_ms FROM api_log WHERE timestamp >= ? AND endpoint LIKE '/v1/%' ORDER BY latency_ms", [cutoff_10m]).fetchall()]
        p50 = latencies[len(latencies)//2] if latencies else 0
        p95 = latencies[int(len(latencies)*0.95)] if latencies else 0

        top_eps = conn.execute("""SELECT endpoint, COUNT(*) as cnt FROM api_log
            WHERE id > (SELECT MAX(id) - 100000 FROM api_log) GROUP BY endpoint ORDER BY cnt DESC LIMIT 10""").fetchall()

        tiers = conn.execute("""SELECT tier, COUNT(*) as cnt FROM api_log
            WHERE id > (SELECT MAX(id) - 100000 FROM api_log) GROUP BY tier ORDER BY cnt DESC""").fetchall()

        # Hourly histogram (last 24h)
        hourly = conn.execute("""SELECT strftime('%H', timestamp) as hr, COUNT(*) as cnt
            FROM api_log WHERE id > (SELECT MAX(id) - 100000 FROM api_log)
            GROUP BY hr ORDER BY hr""").fetchall()

        # Error rate
        errors = conn.execute("SELECT COUNT(*) FROM api_log WHERE timestamp >= ? AND status_code >= 400", [cutoff_24h]).fetchone()[0]

        conn.close()
        return {
            "requests_24h": r24, "requests_1h": r1, "unique_ips_24h": uips,
            "p50_ms": round(p50, 1), "p95_ms": round(p95, 1),
            "top_endpoints": [{"endpoint": r[0], "count": r[1]} for r in top_eps],
            "tier_distribution": {r[0]: r[1] for r in tiers},
            "hourly": {r[0]: r[1] for r in hourly},
            "error_rate": round(errors / r24 * 100, 1) if r24 > 0 else 0,
        }
    except Exception as e:
        return {"error": str(e)[:200]}


def _classify_ua(ua: str) -> str:
    if not ua:
        return "Unknown"
    ul = ua.lower()
    if any(x in ul for x in ['claude', 'anthropic']):
        return "AI Bot"
    if any(x in ul for x in ['chatgpt', 'gptbot', 'openai']):
        return "AI Bot"
    if 'perplexity' in ul:
        return "AI Bot"
    if any(x in ul for x in ['googlebot', 'google-inspection', 'google-extended', 'apis-google']):
        return "Search Bot"
    if any(x in ul for x in ['bingbot', 'yandex', 'duckduckbot']):
        return "Search Bot"
    if any(x in ul for x in ['semrush', 'ahrefs', 'bytespider', 'petalbot', 'dotbot', 'mj12bot']):
        return "SEO Bot"
    if any(x in ul for x in ['meta-externalagent', 'facebookexternalhit', 'twitterbot', 'linkedinbot', 'discordbot']):
        return "Social Bot"
    if any(x in ul for x in ['langchain', 'crewai', 'elizaos', 'solana-agent']):
        return "Agent Framework"
    if any(x in ul for x in ['uptimerobot', 'pingdom', 'betteruptime', 'datadog']):
        return "Monitoring"
    if any(x in ul for x in ['zgrab', 'censys', 'shodan', 'nuclei', 'nikto']):
        return "Scanner"
    if any(x in ul for x in ['python-requests', 'python-httpx', 'python-urllib', 'aiohttp']):
        return "API Client"
    if any(x in ul for x in ['axios', 'node-fetch', 'got/', 'undici']):
        return "API Client"
    if any(x in ul for x in ['curl', 'httpx', 'postman', 'insomnia']):
        return "API Client"
    if any(x in ul for x in ['go-http-client', 'okhttp', 'reqwest']):
        return "API Client"
    if 'testclient' in ul:
        return "Test Suite"
    if any(x in ul for x in ['chrome/', 'firefox/', 'safari/', 'edge/']):
        return "Human Browser"
    if 'mozilla' in ul:
        return "Human Browser"
    return "Unknown"


def _user_intelligence() -> dict:
    try:
        conn = sqlite3.connect(API_LOG_DB)
        conn.row_factory = sqlite3.Row
        from datetime import timedelta as _td2
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        # Use ID-based cutoffs for speed (avoids full table scan)
        _max_id = conn.execute("SELECT MAX(id) FROM api_log").fetchone()[0] or 0
        _cutoff_24h = str(max(0, _max_id - 200000))
        _cutoff_7d = str(max(0, _max_id - 1200000))

        # User type breakdown (last 24h)
        all_uas = conn.execute("""
            SELECT user_agent, COUNT(*) as cnt FROM api_log
            WHERE id > (SELECT MAX(id) - 100000 FROM api_log)
            GROUP BY user_agent
        """).fetchall()
        type_counts = {}
        for row in all_uas:
            cls = _classify_ua(row[0] or "")
            type_counts[cls] = type_counts.get(cls, 0) + row[1]

        # AI bot breakdown
        ai_bots = {}
        for row in all_uas:
            ua = (row[0] or "").lower()
            if 'claude' in ua or 'anthropic' in ua:
                ai_bots["Claude"] = ai_bots.get("Claude", 0) + row[1]
            elif 'chatgpt' in ua or 'gptbot' in ua or 'openai' in ua:
                ai_bots["ChatGPT"] = ai_bots.get("ChatGPT", 0) + row[1]
            elif 'perplexity' in ua:
                ai_bots["Perplexity"] = ai_bots.get("Perplexity", 0) + row[1]
            elif 'googlebot' in ua:
                ai_bots["Google"] = ai_bots.get("Google", 0) + row[1]
            elif 'bingbot' in ua:
                ai_bots["Bing"] = ai_bots.get("Bing", 0) + row[1]

        # Top 10 active users (by ip_hash, last 24h) — single query, no N+1
        top_users = conn.execute("""
            SELECT ip_hash, COUNT(*) as cnt,
                   MAX(timestamp) as last_seen,
                   COUNT(DISTINCT endpoint) as unique_eps,
                   MAX(user_agent) as ua
            FROM api_log
            WHERE id > (SELECT MAX(id) - 100000 FROM api_log)
            GROUP BY ip_hash ORDER BY cnt DESC LIMIT 10
        """).fetchall()
        users = []
        for u in top_users:
            users.append({
                "ip": u[0], "requests": u[1], "last_seen": u[2][:19],
                "unique_endpoints": u[3],
                "type": _classify_ua(u[4] or ""),
                "top_endpoint": "",
            })

        # Token check activity
        token_checks = conn.execute("""
            SELECT endpoint, COUNT(*) as cnt, COUNT(DISTINCT ip_hash) as ips
            FROM api_log WHERE endpoint LIKE '/v1/check/%'
            AND endpoint NOT LIKE '%zzz%' AND endpoint NOT LIKE '%nonexist%' AND endpoint NOT LIKE '%fake%'
            AND id > ?
            GROUP BY endpoint ORDER BY cnt DESC
        """, [_cutoff_7d]).fetchall()
        tokens_checked = [{
            "token": r[0].replace("/v1/check/", ""),
            "calls": r[1], "unique_ips": r[2]
        } for r in token_checks]

        total_checks = conn.execute("""
            SELECT COUNT(*) FROM api_log WHERE endpoint LIKE '/v1/check/%'
            AND endpoint NOT LIKE '%zzz%' AND id > ?
        """, [_cutoff_7d]).fetchone()[0]

        # Active API Integrations — real non-bot, non-browser, non-internal callers
        # Require ≥3 calls to /v1/* from same IP in 7 days
        # _cutoff_7d already set as ID-based cutoff above

        # Build bot UA exclusion clause
        _bot_pats = [
            "facebookexternalhit", "meta-externalagent", "meta-webindexer",
            "googlebot", "google-extended", "apis-google", "google-inspection",
            "bingbot", "bytespider", "claudebot", "anthropic",
            "chatgpt-user", "gptbot", "openai", "perplexitybot", "perplexity",
            "ahrefsbot", "semrushbot", "mj12bot", "petalbot", "dotbot",
            "yandex", "duckduckbot", "twitterbot", "linkedinbot", "discordbot",
            "slackbot", "whatsapp", "zgrab", "censys", "shodan", "nuclei",
            "nikto", "uptimerobot", "pingdom", "betteruptime", "datadog",
            "testclient", "nexus 5x",
            # Browsers (not API integrations)
            "mozilla/", "chrome/", "firefox/", "safari/", "edge/",
        ]
        _bot_sql = " AND ".join(f"LOWER(user_agent) NOT LIKE '%{p}%'" for p in _bot_pats)

        active_integrations = conn.execute(f"""
            SELECT ip_hash, COUNT(*) as cnt, COUNT(DISTINCT endpoint) as eps,
                   MIN(timestamp) as first, MAX(timestamp) as last,
                   MAX(user_agent) as ua,
                   SUM(CASE WHEN endpoint = '/zarq/dashboard/data' THEN 1 ELSE 0 END) as dash_cnt
            FROM api_log
            WHERE id > ?
            AND endpoint LIKE '/v1/%'
            AND {_bot_sql}
            GROUP BY ip_hash HAVING cnt >= 3
            ORDER BY cnt DESC
        """, [_cutoff_7d]).fetchall()
        integration_list = []
        for r in active_integrations:
            if r[6] > r[1] * 0.5:
                continue
            if r[0] in INTERNAL_IPS:
                continue
            integration_list.append({
                "ip": r[0], "calls": r[1], "endpoints": r[2],
                "type": _classify_ua(r[5] or ""),
                "first": r[3][:19], "last": r[4][:19],
            })

        # AI Bot Coverage — unique pages crawled by AI bots in 7 days
        ai_coverage = conn.execute("""
            SELECT COUNT(DISTINCT endpoint) FROM api_log
            WHERE id > ?
            AND (LOWER(user_agent) LIKE '%chatgpt%'
                 OR LOWER(user_agent) LIKE '%gptbot%'
                 OR LOWER(user_agent) LIKE '%openai%'
                 OR LOWER(user_agent) LIKE '%claudebot%'
                 OR LOWER(user_agent) LIKE '%anthropic%'
                 OR LOWER(user_agent) LIKE '%perplexity%')
        """, [_cutoff_7d]).fetchone()[0]

        # New vs returning (today)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_ips = conn.execute("""
            SELECT COUNT(DISTINCT ip_hash) FROM api_log
            WHERE date(timestamp) = ?
        """, [today]).fetchone()[0]
        returning_ips = conn.execute("""
            SELECT COUNT(DISTINCT a.ip_hash) FROM api_log a
            WHERE date(a.timestamp) = ?
            AND EXISTS (SELECT 1 FROM api_log b WHERE b.ip_hash = a.ip_hash AND date(b.timestamp) < ?)
        """, [today, today]).fetchone()[0]
        new_ips = today_ips - returning_ips

        conn.close()
        return {
            "user_types": type_counts,
            "ai_bots": ai_bots,
            "top_users": users,
            "token_checks": {"total": total_checks, "unique_tokens": len(tokens_checked), "tokens": tokens_checked},
            "active_integrations": integration_list,
            "ai_bot_coverage_7d": ai_coverage,
            "new_vs_returning": {"new_today": new_ips, "returning_today": returning_ips, "total_today": today_ips},
        }
    except Exception as e:
        return {"error": str(e)[:200]}


INTERNAL_IPS = {"12ca17b49af22894", "846488f1dc5c07b4"}  # 127.0.0.1 + testclient

# Bot user agents to exclude from "real usage" counts
BOT_UA_PATTERNS = [
    "facebookexternalhit", "meta-externalagent",
    "googlebot", "google-extended", "apis-google", "google-inspection",
    "bingbot", "bytespider",
    "claudebot", "anthropic",
    "chatgpt-user", "gptbot", "openai",
    "perplexitybot", "perplexity",
    "ahrefsbot", "semrushbot", "mj12bot",
    "petalbot", "dotbot", "yandex", "duckduckbot",
    "twitterbot", "linkedinbot", "discordbot", "slackbot", "whatsapp",
    "zgrab", "censys", "shodan", "nuclei", "nikto",
    "uptimerobot", "pingdom", "betteruptime", "datadog",
    "testclient",
    "nexus 5x",  # Googlebot mobile disguised UA
]

# Endpoints that indicate scanner/attacker (not real usage)
SCANNER_ENDPOINTS = [
    "wp-includes", "wp-admin", "wp-login", "wlwmanifest",
    "setup-config", ".env", ".git", "xmlrpc",
]


def _get_excluded_ips(conn, now: str) -> set:
    """Build the full set of IPs to exclude from adoption metrics."""
    excluded = set(INTERNAL_IPS)

    # IPs that accessed internal/admin endpoints (that's us)
    internal_rows = conn.execute("""
        SELECT DISTINCT ip_hash FROM api_log
        WHERE endpoint IN ('/zarq/dashboard', '/zarq/dashboard/data', '/internal/metrics')
    """).fetchall()
    for r in internal_rows:
        excluded.add(r[0])

    # IPs with >1000 calls in any single day (scanner/bot)
    _exc_max_id = conn.execute("SELECT MAX(id) FROM api_log").fetchone()[0] or 0
    _exc_cutoff_7d = max(0, _exc_max_id - 1200000)
    heavy_rows = conn.execute("""
        SELECT ip_hash FROM api_log
        WHERE id > ?
        GROUP BY ip_hash, date(timestamp)
        HAVING COUNT(*) > 1000
    """, [_exc_cutoff_7d]).fetchall()
    for r in heavy_rows:
        excluded.add(r[0])

    # IPs that probed scanner/WordPress endpoints (attacker, not user)
    scanner_clauses = " OR ".join(
        f"endpoint LIKE '%{p}%'" for p in SCANNER_ENDPOINTS
    )
    scanner_rows = conn.execute(f"""
        SELECT DISTINCT ip_hash FROM api_log
        WHERE {scanner_clauses}
    """).fetchall()
    for r in scanner_rows:
        excluded.add(r[0])

    return excluded


def _is_bot_ua(ua: str) -> bool:
    if not ua:
        return True
    ul = ua.lower()
    return any(p in ul for p in BOT_UA_PATTERNS)


def _adoption_triggers() -> dict:
    try:
        conn = sqlite3.connect(API_LOG_DB)
        from datetime import timedelta as _td3
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        today = now_dt.strftime("%Y-%m-%d")
        # Use ID-based cutoffs (much faster than timestamp scan on 4.4M rows)
        _max_id = conn.execute("SELECT MAX(id) FROM api_log").fetchone()[0] or 0
        _id_24h = max(0, _max_id - 200000)   # ~200K rows ≈ 24h+ buffer
        _id_7d = max(0, _max_id - 1200000)    # ~1.2M rows ≈ 7d+ buffer
        _at_cutoff_24h = str(_id_24h)  # Used as id > cutoff now
        _at_cutoff_7d = str(_id_7d)

        # Build exclusion set
        excluded = _get_excluded_ips(conn, now)
        if not excluded:
            excluded = {"__none__"}
        ph = ",".join("?" * len(excluded))
        ex_list = list(excluded)

        # Build bot UA filter SQL
        bot_clauses = " AND ".join(
            f"LOWER(user_agent) NOT LIKE '%{p}%'" for p in BOT_UA_PATTERNS
        )

        # --- RAW counts (before filtering) ---
        raw_24h = conn.execute("""
            SELECT COUNT(*) FROM api_log
            WHERE endpoint LIKE '/v1/check/%'
            AND endpoint NOT LIKE '%zzz%' AND endpoint NOT LIKE '%nonexist%' AND endpoint NOT LIKE '%fake%'
            AND id > ?
        """, [_at_cutoff_24h]).fetchone()[0]

        raw_7d = conn.execute("""
            SELECT COUNT(*) FROM api_log
            WHERE endpoint LIKE '/v1/check/%'
            AND endpoint NOT LIKE '%zzz%' AND endpoint NOT LIKE '%nonexist%' AND endpoint NOT LIKE '%fake%'
            AND id > ?
        """, [_at_cutoff_7d]).fetchone()[0]

        # --- FILTERED counts (real external human/agent usage) ---
        check_24h = conn.execute(f"""
            SELECT COUNT(*) FROM api_log
            WHERE endpoint LIKE '/v1/check/%'
            AND endpoint NOT LIKE '%zzz%' AND endpoint NOT LIKE '%nonexist%' AND endpoint NOT LIKE '%fake%'
            AND ip_hash NOT IN ({ph})
            AND {bot_clauses}
            AND id > ?
        """, ex_list + [_at_cutoff_24h]).fetchone()[0]

        check_7d = conn.execute(f"""
            SELECT COUNT(*) FROM api_log
            WHERE endpoint LIKE '/v1/check/%'
            AND endpoint NOT LIKE '%zzz%' AND endpoint NOT LIKE '%nonexist%' AND endpoint NOT LIKE '%fake%'
            AND ip_hash NOT IN ({ph})
            AND {bot_clauses}
            AND id > ?
        """, ex_list + [_at_cutoff_7d]).fetchone()[0]

        # Unique HUMAN IPs checking tokens (7d)
        human_check_ips = conn.execute(f"""
            SELECT COUNT(DISTINCT ip_hash) FROM api_log
            WHERE endpoint LIKE '/v1/check/%'
            AND endpoint NOT LIKE '%zzz%' AND endpoint NOT LIKE '%nonexist%' AND endpoint NOT LIKE '%fake%'
            AND ip_hash NOT IN ({ph})
            AND {bot_clauses}
            AND id > ?
        """, ex_list + [_at_cutoff_7d]).fetchone()[0]

        # Recurring integrations: IPs with ≥10 calls in 7d, after ALL filtering
        # Also exclude dashboard pollers (>50% calls to /zarq/dashboard/data)
        recurring_rows_raw = conn.execute(f"""
            SELECT ip_hash, COUNT(*) as cnt,
                   SUM(CASE WHEN endpoint = '/zarq/dashboard/data' THEN 1 ELSE 0 END) as dash_cnt
            FROM api_log
            WHERE id > ?
            AND ip_hash NOT IN ({ph})
            AND {bot_clauses}
            GROUP BY ip_hash HAVING cnt >= 10
        """, [_at_cutoff_7d] + ex_list).fetchall()
        recurring_rows = [rr for rr in recurring_rows_raw if rr[2] <= rr[1] * 0.5]
        recurring_count = len(recurring_rows)

        # AI bot crawls today (separate — this is informational, not filtered)
        ai_rows = conn.execute("""
            SELECT user_agent, COUNT(*) as cnt FROM api_log
            WHERE date(timestamp) = ?
            GROUP BY user_agent
        """, [today]).fetchall()
        ai_bots = {"Claude": 0, "ChatGPT": 0, "Perplexity": 0, "Google": 0}
        for row in ai_rows:
            ua = (row[0] or "").lower()
            if "claude" in ua or "anthropic" in ua:
                ai_bots["Claude"] += row[1]
            elif "chatgpt" in ua or "gptbot" in ua or "openai" in ua:
                ai_bots["ChatGPT"] += row[1]
            elif "perplexity" in ua:
                ai_bots["Perplexity"] += row[1]
            elif "googlebot" in ua or "google-extended" in ua:
                ai_bots["Google"] += row[1]

        # Days since launch (2026-03-08 = day 1)
        from datetime import date as _date
        launch = _date(2026, 3, 8)
        days_live = max(1, (datetime.now(timezone.utc).date() - launch).days + 1)

        conn.close()

        # Auto-calculated decisions based on FILTERED data only
        # Don't evaluate until the time period has passed
        if days_live >= 7:
            week1_verdict = "signal" if (check_7d > 0 and human_check_ips > 0) else "no_signal"
        else:
            week1_verdict = "collecting"

        if days_live >= 14:
            week2_signal = recurring_count >= 3
            week2_verdict = "wedge_working" if week2_signal else ("pivot" if recurring_count <= 1 else "building")
        else:
            week2_verdict = "collecting"

        # Evaluation dates
        week1_eval = (launch + __import__('datetime').timedelta(days=6)).isoformat()
        week2_eval = (launch + __import__('datetime').timedelta(days=13)).isoformat()

        return {
            "raw_check_24h": raw_24h,
            "raw_check_7d": raw_7d,
            "check_24h": check_24h,
            "check_7d": check_7d,
            "human_check_ips_7d": human_check_ips,
            "recurring_count": recurring_count,
            "excluded_ips_count": len(excluded),
            "ai_bots_today": ai_bots,
            "days_live": days_live,
            "week1_verdict": week1_verdict,
            "week1_eval_date": week1_eval,
            "week2_verdict": week2_verdict,
            "week2_eval_date": week2_eval,
            "registrations": {
                "smithery": {"status": "live", "url": "https://smithery.ai/server/agentidx/zarq-risk"},
                "glama": {"status": "pending", "submitted": "2026-03-08"},
                "langchain_forum": {"status": "posted"},
            },
        }
    except Exception as e:
        return {"error": str(e)[:200]}


def _crypto_intelligence() -> dict:
    try:
        conn = sqlite3.connect(CRYPTO_DB)
        conn.row_factory = sqlite3.Row

        total_tokens = conn.execute("SELECT COUNT(DISTINCT token_id) FROM crypto_rating_daily").fetchone()[0]
        latest_rating_date = conn.execute("SELECT MAX(run_date) FROM crypto_rating_daily").fetchone()[0]
        latest_signal_date = conn.execute("SELECT MAX(signal_date) FROM nerq_risk_signals").fetchone()[0]
        latest_date = latest_rating_date  # For rating queries below

        # Rating distribution
        ratings = conn.execute("""SELECT rating, COUNT(*) as cnt FROM crypto_rating_daily
            WHERE run_date = ? GROUP BY rating ORDER BY cnt DESC""", [latest_date]).fetchall()

        # Warnings/Critical
        warnings = conn.execute("""SELECT COUNT(*) FROM nerq_risk_signals
            WHERE signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)
            AND risk_level = 'WARNING'""").fetchone()[0]
        criticals = conn.execute("""SELECT COUNT(*) FROM nerq_risk_signals
            WHERE signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)
            AND risk_level = 'CRITICAL'""").fetchone()[0]

        # Crash shield saves
        try:
            saves = conn.execute("SELECT COUNT(*) FROM crash_shield_saves").fetchone()[0]
            top_save = conn.execute("SELECT drop_percent FROM crash_shield_saves ORDER BY drop_percent DESC LIMIT 1").fetchone()
            max_drop = top_save[0] if top_save else 0
        except Exception:
            saves, max_drop = 0, 0

        # Paper trading NAVs — read from nerq_portfolio_v4
        try:
            navs = {}
            for p in ["CONSERVATIVE", "GROWTH"]:
                row = conn.execute("""SELECT nav, btc_nav FROM nerq_portfolio_v4
                    WHERE variant = ? ORDER BY run_date DESC, month DESC LIMIT 1""", [p]).fetchone()
                if row:
                    navs[p] = round(row[0], 4)
                    navs[p + "_vs_BTC"] = round(row[0] / row[1], 4) if row[1] else None
        except Exception:
            navs = {}

        # Trust score distribution
        trust_dist = conn.execute("""SELECT
            SUM(CASE WHEN score >= 80 THEN 1 ELSE 0 END) as aaa_aa,
            SUM(CASE WHEN score >= 60 AND score < 80 THEN 1 ELSE 0 END) as a_baa,
            SUM(CASE WHEN score >= 40 AND score < 60 THEN 1 ELSE 0 END) as ba_b,
            SUM(CASE WHEN score < 40 THEN 1 ELSE 0 END) as caa_d
            FROM crypto_rating_daily WHERE run_date = ?""", [latest_date]).fetchone()

        conn.close()
        return {
            "total_tokens": total_tokens,
            "latest_date": latest_signal_date or latest_date,
            "latest_rating_date": latest_rating_date,
            "ratings": {r[0]: r[1] for r in ratings},
            "warnings": warnings, "criticals": criticals,
            "crash_shield_saves": saves, "max_save_drop": max_drop,
            "paper_trading_nav": navs,
            "trust_distribution": {
                "investment_grade": (trust_dist[0] or 0) + (trust_dist[1] or 0),
                "speculative": (trust_dist[2] or 0) + (trust_dist[3] or 0),
            } if trust_dist else {},
        }
    except Exception as e:
        return {"error": str(e)[:200]}


_agent_index_cache: dict = {"data": None, "ts": 0}

def _agent_index() -> dict:
    import time as _t
    if _agent_index_cache["data"] and (_t.time() - _agent_index_cache["ts"]) < 300:
        return _agent_index_cache["data"]
    try:
        from agentindex.db.models import get_session
        from sqlalchemy import text
        from datetime import timedelta
        s = get_session()
        total = int(s.execute(text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'agents'")).scalar() or 0)
        # Use TABLESAMPLE for new_24h estimate instead of scanning 5M+ rows
        new_24h = s.execute(
            text("SELECT COUNT(*) FROM agents TABLESAMPLE SYSTEM(0.1) WHERE first_indexed > :d"),
            {"d": datetime.now(timezone.utc) - timedelta(hours=24)}
        ).scalar() or 0
        new_24h = int(new_24h * 1000)  # Scale up from 0.1% sample
        trust_scored = total

        # Category distribution (top 8) — uses index on category
        cats = s.execute(text("""SELECT category, COUNT(*) as cnt FROM agents
            WHERE category IS NOT NULL GROUP BY category ORDER BY cnt DESC LIMIT 8""")).fetchall()

        s.close()
        result = {
            "total_agents": total, "new_24h": new_24h,
            "trust_scored": trust_scored,
            "categories": {r[0]: r[1] for r in cats},
        }
        _agent_index_cache["data"] = result
        _agent_index_cache["ts"] = _t.time()
        return result
    except Exception as e:
        return {"error": str(e)[:200]}


def _scout_data() -> dict:
    """Get Nerq Scout status for ops dashboard."""
    try:
        from agentindex.db.models import get_session
        from sqlalchemy import text as _text
        import json as _json
        session = get_session()

        evaluated_total = session.execute(_text(
            "SELECT COUNT(*) FROM nerq_scout_log WHERE event_type = 'scout_evaluate'"
        )).scalar() or 0

        featured_total = session.execute(_text(
            "SELECT COUNT(DISTINCT agent_name) FROM nerq_scout_log WHERE event_type = 'scout_evaluate'"
        )).scalar() or 0

        claimed = session.execute(_text(
            "SELECT COUNT(*) FROM nerq_scout_log WHERE event_type = 'claim_submit'"
        )).scalar() or 0

        last_run_row = session.execute(_text(
            "SELECT MAX(created_at) FROM nerq_scout_log WHERE event_type = 'scout_evaluate'"
        )).scalar()
        last_run = last_run_row.isoformat() if last_run_row else None

        # Next run: cron at 04, 10, 16, 22 UTC
        next_run = None
        if last_run_row:
            from datetime import timedelta
            now = datetime.now(timezone.utc)
            for offset in range(2):
                for h in [4, 10, 16, 22]:
                    candidate = now.replace(hour=h, minute=0, second=0, microsecond=0) + timedelta(days=offset)
                    if candidate > now:
                        next_run = candidate.isoformat()
                        break
                if next_run:
                    break

        # Blog posts
        reports_dir = os.path.join(os.path.dirname(__file__), "..", "docs", "auto-reports")
        blog_count = len(glob.glob(os.path.join(reports_dir, "*.md")))

        devto_count = blog_count
        bluesky_count = 0
        try:
            bsky_path = os.path.expanduser("~/.config/nerq/bluesky_handle")
            if os.path.exists(bsky_path):
                bluesky_count = session.execute(_text(
                    "SELECT COUNT(DISTINCT DATE(created_at)) FROM nerq_scout_log WHERE event_type = 'scout_evaluate'"
                )).scalar() or 0
        except Exception:
            pass

        # Last 5 evaluated
        last_5_rows = session.execute(_text("""
            SELECT agent_name, details, created_at
            FROM nerq_scout_log
            WHERE event_type = 'scout_evaluate' AND agent_name IS NOT NULL
            ORDER BY created_at DESC LIMIT 5
        """)).fetchall()
        last_5 = []
        for r in last_5_rows:
            details = r[1] if isinstance(r[1], dict) else (_json.loads(r[1]) if r[1] else {})
            last_5.append({
                "name": r[0],
                "trust_score": details.get("trust_score"),
                "grade": details.get("grade"),
                "evaluated_at": r[2].isoformat() if r[2] else None,
            })

        session.close()
        return {
            "evaluated_total": evaluated_total,
            "featured_total": featured_total,
            "claimed": claimed,
            "last_run": last_run,
            "next_run": next_run,
            "blog_posts": blog_count,
            "devto_articles": devto_count,
            "bluesky_posts": bluesky_count,
            "last_5_evaluated": last_5,
        }
    except Exception as e:
        logger.error(f"scout data error: {e}")
        return {"evaluated_total": 0}


def _sprint_progress() -> dict:
    result = {"queue": [], "done": [], "failed": []}
    for folder in ["queue", "done", "failed"]:
        d = os.path.join(TASKS_DIR, folder)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".md"):
                    result[folder].append(f.replace(".md", ""))
    return result


# ─── API Data Endpoint ───

import time as _dash_time
import asyncio as _dash_asyncio
import threading as _dash_threading
_DASHBOARD_TTL = 300  # 5min — after this, trigger background refresh
_DASHBOARD_STALE_TTL = 3600  # 1h — serve stale data up to this age
_DASHBOARD_CACHE_FILE = "/tmp/zarq_dashboard_cache.json"
_DASHBOARD_REFRESH_LOCK = _dash_threading.Lock()
_DASHBOARD_REFRESHING = False

def _read_file_cache(allow_stale=False):
    """Read cached dashboard data from file (works across workers).
    With allow_stale=True, returns data up to _DASHBOARD_STALE_TTL old."""
    try:
        import os
        if not os.path.exists(_DASHBOARD_CACHE_FILE):
            return None, None
        age = _dash_time.time() - os.path.getmtime(_DASHBOARD_CACHE_FILE)
        max_age = _DASHBOARD_STALE_TTL if allow_stale else _DASHBOARD_TTL
        if age > max_age:
            return None, None
        with open(_DASHBOARD_CACHE_FILE) as f:
            return json.load(f), age
    except Exception:
        return None, None

def _write_file_cache(data):
    """Write dashboard data to file cache."""
    try:
        with open(_DASHBOARD_CACHE_FILE + ".tmp", "w") as f:
            json.dump(data, f)
        import os
        os.replace(_DASHBOARD_CACHE_FILE + ".tmp", _DASHBOARD_CACHE_FILE)
    except Exception:
        pass

def _background_refresh():
    """Refresh cache in background thread. Non-blocking."""
    global _DASHBOARD_REFRESHING
    if not _DASHBOARD_REFRESH_LOCK.acquire(blocking=False):
        return  # Another thread is already refreshing
    try:
        _DASHBOARD_REFRESHING = True
        data = _build_dashboard_data()
        _write_file_cache(data)
    except Exception:
        pass
    finally:
        _DASHBOARD_REFRESHING = False
        _DASHBOARD_REFRESH_LOCK.release()

def _build_dashboard_data():
    """Build all dashboard data (synchronous, runs in thread)."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "adoption_triggers": _adoption_triggers(),
        "system_health": {
            "launchagents": {
                "nerq_api": _launchagent_status("com.nerq.api"),
                "zarq_mcp": _launchagent_status("com.zarq.mcp-sse"),
                "nerq_mcp": _launchagent_status("com.agentindex.mcp-sse"),
            },
            "redis": _redis_ping(),
            "postgresql": _pg_status(),
            "circuit_breakers": _circuit_breaker_states(),
            "disk": _disk_usage(),
        },
        "api_traffic": _api_traffic(),
        "user_intelligence": _user_intelligence(),
        "crypto": _crypto_intelligence(),
        "agents": _agent_index(),
        "scout": _scout_data(),
        "sprints": _sprint_progress(),
    }

@router_dashboard.get("/zarq/dashboard/data")
async def dashboard_data(request: Request):
    if not _check_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Stale-while-revalidate: always serve cached data, refresh in background
    cached, age = _read_file_cache(allow_stale=True)
    if cached:
        if age is not None and age > _DASHBOARD_TTL:
            # Stale — trigger background refresh, serve stale immediately
            _dash_threading.Thread(target=_background_refresh, daemon=True).start()
        return JSONResponse(cached)

    # No cache at all — must build synchronously (cold start only)
    data = await _dash_asyncio.to_thread(_build_dashboard_data)
    _write_file_cache(data)
    return JSONResponse(data)


# ─── HTML Dashboard ───

@router_dashboard.get("/zarq/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    if not _check_auth(request):
        return HTMLResponse("<h1>401 Unauthorized</h1><p>Pass Bearer token or ?token=...</p>", status_code=401)
    return HTMLResponse(_render_dashboard_html())


def _render_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZARQ Operations Dashboard</title>
<meta name="robots" content="noindex, nofollow">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
    --warm: #c2956b;
    --warm-light: #f5ebe0;
    --warm-dark: #a07a52;
    --bg: #fafaf8;
    --card-bg: #ffffff;
    --text: #1a1a1a;
    --text-secondary: #6b7280;
    --border: #e5e7eb;
    --green: #059669;
    --green-light: #d1fae5;
    --red: #dc2626;
    --red-light: #fee2e2;
    --yellow: #d97706;
    --yellow-light: #fef3c7;
    --blue: #2563eb;
    --blue-light: #dbeafe;
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
    font-family: 'DM Sans', -apple-system, sans-serif;
    background: var(--bg); color: var(--text);
    line-height: 1.5;
}
.header {
    background: #fff; border-bottom: 1px solid var(--border);
    padding: 16px 32px; display: flex; align-items: center;
    justify-content: space-between; position: sticky; top: 0; z-index: 10;
}
.header h1 {
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 1.4rem; font-weight: 400;
}
.header h1 span { color: var(--warm); }
.header-right { display: flex; align-items: center; gap: 16px; font-size: 0.85rem; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.status-dot.ok { background: var(--green); }
.status-dot.warn { background: var(--yellow); }
.status-dot.error { background: var(--red); }
#last-update { color: var(--text-secondary); }

.grid {
    display: grid; gap: 20px; padding: 24px 32px;
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
}
.card {
    background: var(--card-bg); border: 1px solid var(--border);
    border-radius: 12px; overflow: hidden;
}
.card-header {
    padding: 16px 20px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
}
.card-header h2 {
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 1.1rem; font-weight: 400;
}
.card-body { padding: 16px 20px; }
.card.wide { grid-column: span 2; }

.kpi-row { display: flex; gap: 16px; flex-wrap: wrap; padding: 12px 32px 0; }
.kpi {
    flex: 1; min-width: 160px; background: var(--card-bg);
    border: 1px solid var(--border); border-radius: 10px;
    padding: 16px 20px; text-align: center;
}
.kpi-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.8rem; font-weight: 600; color: var(--warm);
}
.kpi-label { font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px; }

table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
table th { text-align: left; color: var(--text-secondary); font-weight: 500; padding: 8px 12px; border-bottom: 1px solid var(--border); }
table td { padding: 8px 12px; border-bottom: 1px solid #f3f4f6; }
table td:last-child { font-family: 'JetBrains Mono', monospace; text-align: right; }

.pill {
    display: inline-block; padding: 2px 10px; border-radius: 20px;
    font-size: 0.75rem; font-weight: 600;
}
.pill-green { background: var(--green-light); color: var(--green); }
.pill-red { background: var(--red-light); color: var(--red); }
.pill-yellow { background: var(--yellow-light); color: var(--yellow); }
.pill-blue { background: var(--blue-light); color: var(--blue); }

.bar-chart { display: flex; align-items: flex-end; gap: 3px; height: 80px; margin-top: 12px; }
.bar-chart .bar {
    flex: 1; background: var(--warm); border-radius: 3px 3px 0 0;
    min-height: 2px; position: relative;
}
.bar-chart .bar:hover { background: var(--warm-dark); }
.bar-chart .bar-label {
    position: absolute; bottom: -18px; left: 50%; transform: translateX(-50%);
    font-size: 0.6rem; color: var(--text-secondary);
}

.metric-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f3f4f6; }
.metric-row:last-child { border: none; }
.metric-label { color: var(--text-secondary); font-size: 0.85rem; }
.metric-value { font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 0.85rem; }

.task-list { list-style: none; }
.task-list li { padding: 4px 0; font-size: 0.85rem; font-family: 'JetBrains Mono', monospace; }
.task-list li::before { margin-right: 6px; }
.task-list.queue li::before { content: "○"; color: var(--yellow); }
.task-list.done li::before { content: "●"; color: var(--green); }
.task-list.failed li::before { content: "✕"; color: var(--red); }

.service-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.service-item {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 12px; background: #f9fafb; border-radius: 8px;
    font-size: 0.85rem;
}
.loading { text-align: center; padding: 40px; color: var(--text-secondary); }

@media (max-width: 800px) {
    .grid { grid-template-columns: 1fr; padding: 16px; }
    .card.wide { grid-column: span 1; }
    .kpi-row { padding: 12px 16px 0; }
    .header { padding: 12px 16px; }
}
</style>
</head>
<body>
<div class="header">
    <h1><span>ZARQ</span> Operations Dashboard</h1>
    <div class="header-right">
        <span id="overall-status"><span class="status-dot ok"></span> All systems</span>
        <span id="last-update">Loading...</span>
    </div>
</div>

<div class="kpi-row" id="kpi-row">
    <div class="kpi"><div class="kpi-value" id="kpi-tokens">—</div><div class="kpi-label">Tokens Rated</div></div>
    <div class="kpi"><div class="kpi-value" id="kpi-agents">—</div><div class="kpi-label">AI Assets</div></div>
    <div class="kpi"><div class="kpi-value" id="kpi-requests">—</div><div class="kpi-label">Requests (24h)</div></div>
    <div class="kpi"><div class="kpi-value" id="kpi-saves">—</div><div class="kpi-label">Crash Shield Saves</div></div>
    <div class="kpi"><div class="kpi-value" id="kpi-latency">—</div><div class="kpi-label">P50 Latency</div></div>
</div>

<div class="grid">
    <!-- Adoption Triggers -->
    <div class="card wide" style="border:2px solid var(--warm)">
        <div class="card-header" style="background:linear-gradient(135deg,var(--warm-light),#fff)"><h2>Adoption Triggers — Next Action Decision</h2><span class="pill" id="adoption-pill">Loading</span></div>
        <div class="card-body" id="adoption-body"><div class="loading">Loading...</div></div>
    </div>

    <!-- System Health -->
    <div class="card">
        <div class="card-header"><h2>System Health</h2><span class="pill pill-green" id="health-pill">OK</span></div>
        <div class="card-body" id="health-body"><div class="loading">Loading...</div></div>
    </div>

    <!-- API Traffic -->
    <div class="card">
        <div class="card-header"><h2>API Traffic (24h)</h2></div>
        <div class="card-body" id="traffic-body"><div class="loading">Loading...</div></div>
    </div>

    <!-- Risk Intelligence -->
    <div class="card">
        <div class="card-header"><h2>ZARQ Risk Intelligence</h2></div>
        <div class="card-body" id="crypto-body"><div class="loading">Loading...</div></div>
    </div>

    <!-- Agent Index -->
    <div class="card">
        <div class="card-header"><h2>Nerq Agent Index</h2></div>
        <div class="card-body" id="agents-body"><div class="loading">Loading...</div></div>
    </div>

    <!-- Top Endpoints -->
    <div class="card wide">
        <div class="card-header"><h2>Top Endpoints & Tier Distribution</h2></div>
        <div class="card-body" id="endpoints-body"><div class="loading">Loading...</div></div>
    </div>

    <!-- User Intelligence -->
    <div class="card wide">
        <div class="card-header"><h2>User Intelligence</h2></div>
        <div class="card-body" id="users-body"><div class="loading">Loading...</div></div>
    </div>

    <!-- Token Check Activity -->
    <div class="card">
        <div class="card-header"><h2>Token Check Activity</h2></div>
        <div class="card-body" id="token-checks-body"><div class="loading">Loading...</div></div>
    </div>

    <!-- Active API Integrations + AI Bot Coverage -->
    <div class="card">
        <div class="card-header"><h2>Active API Integrations</h2><span class="pill pill-warm" id="integration-count">0</span></div>
        <div class="card-body" id="integration-body"><div class="loading">Loading...</div></div>
    </div>

    <!-- Nerq Scout -->
    <div class="card">
        <div class="card-header"><h2>Nerq Scout</h2><span class="pill pill-warm" id="scout-pill">—</span></div>
        <div class="card-body" id="scout-body"><div class="loading">Loading...</div></div>
    </div>

    <!-- Sprint Progress -->
    <div class="card">
        <div class="card-header"><h2>Sprint Progress</h2></div>
        <div class="card-body" id="sprints-body"><div class="loading">Loading...</div></div>
    </div>

    <!-- Paper Trading -->
    <div class="card">
        <div class="card-header"><h2>Paper Trading NAVs</h2></div>
        <div class="card-body" id="paper-body"><div class="loading">Loading...</div></div>
    </div>
</div>

<script>
const TOKEN = new URLSearchParams(window.location.search).get('token') || '';

async function fetchData() {
    try {
        const r = await fetch('/zarq/dashboard/data?token=' + TOKEN);
        if (!r.ok) return;
        const d = await r.json();
        render(d);
    } catch(e) {
        console.error('Dashboard fetch failed:', e);
    }
}

function fmt(n) {
    if (n === null || n === undefined) return '—';
    if (n >= 1e6) return (n/1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n/1e3).toFixed(1) + 'K';
    return n.toLocaleString();
}

function pill(status) {
    const cls = status === 'running' || status === 'ok' ? 'pill-green' :
                status === 'error' || status === 'not loaded' ? 'pill-red' : 'pill-yellow';
    return `<span class="pill ${cls}">${status}</span>`;
}

function render(d) {
    // Last update
    document.getElementById('last-update').textContent = 'Updated: ' + new Date(d.generated_at).toLocaleTimeString();

    // KPIs
    document.getElementById('kpi-tokens').textContent = fmt(d.crypto?.total_tokens);
    document.getElementById('kpi-agents').textContent = fmt(d.agents?.total_agents);
    document.getElementById('kpi-requests').textContent = fmt(d.api_traffic?.requests_24h);
    document.getElementById('kpi-saves').textContent = fmt(d.crypto?.crash_shield_saves);
    document.getElementById('kpi-latency').textContent = (d.api_traffic?.p50_ms || 0) + 'ms';

    // Adoption Triggers
    const at = d.adoption_triggers || {};
    if (!at.error) {
        const rc = at.recurring_count || 0;
        const c24 = at.check_24h || 0;
        const c7d = at.check_7d || 0;
        const ips = at.human_check_ips_7d || 0;
        const bots = at.ai_bots_today || {};
        const days = at.days_live || 1;
        const regs = at.registrations || {};
        const raw24 = at.raw_check_24h || 0;
        const raw7d = at.raw_check_7d || 0;

        // Status icon helper
        function sig(val, t1, t2) {
            if (val >= t2) return '<span style="color:var(--green)">&#x1F7E2;</span>';
            if (val >= t1) return '<span style="color:var(--yellow)">&#x1F7E1;</span>';
            return '<span style="color:var(--red)">&#x1F534;</span>';
        }

        // Overall pill
        const apill = document.getElementById('adoption-pill');
        if (c7d > 0 && rc >= 1) { apill.className = 'pill pill-green'; apill.textContent = 'TRACTION'; }
        else if (c7d > 0) { apill.className = 'pill pill-yellow'; apill.textContent = 'EARLY SIGNAL'; }
        else { apill.className = 'pill pill-red'; apill.textContent = 'NO SIGNAL YET'; }

        let ahtml = '';

        // Day counter
        ahtml += '<div style="text-align:center;padding:4px 0 12px;font-size:0.8rem;color:var(--text-secondary)">Day <strong style="color:var(--warm);font-size:1.1rem">' + days + '</strong> since launch (2026-03-08) &mdash; Filtering out ' + (at.excluded_ips_count||0) + ' internal/bot IPs</div>';

        ahtml += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">';

        // Left: Targets table
        ahtml += '<div>';
        ahtml += '<strong style="font-size:0.8rem;color:var(--text-secondary)">Real External Usage (bots + internal filtered out)</strong>';
        ahtml += '<table style="margin-top:8px"><thead><tr><th>Metric</th><th>Now</th><th>Week 1</th><th>Week 2</th><th></th></tr></thead><tbody>';
        ahtml += `<tr><td style="font-size:0.8rem">External /v1/check (24h)</td><td style="font-weight:700;color:${c24>0?'var(--green)':'var(--red)'}">${c24}</td><td style="color:var(--text-secondary)">≥1</td><td style="color:var(--text-secondary)">≥10</td><td>${sig(c24,1,10)}</td></tr>`;
        ahtml += `<tr><td style="font-size:0.8rem">Unique human IPs (7d)</td><td style="font-weight:700;color:${ips>0?'var(--green)':'var(--red)'}">${ips}</td><td style="color:var(--text-secondary)">≥1</td><td style="color:var(--text-secondary)">≥3</td><td>${sig(ips,1,3)}</td></tr>`;
        ahtml += `<tr><td style="font-size:0.8rem">Recurring (≥10 calls/7d)</td><td style="font-weight:700;color:${rc>0?'var(--green)':'var(--red)'}">${rc}</td><td style="color:var(--text-secondary)">≥1</td><td style="color:var(--text-secondary)">≥3</td><td>${sig(rc,1,3)}</td></tr>`;
        ahtml += '</tbody></table>';

        // Raw vs filtered note
        ahtml += `<div style="margin-top:10px;padding:8px 12px;background:#f9fafb;border-radius:6px;font-size:0.75rem;color:var(--text-secondary)">Raw /v1/check: <strong>${raw24}</strong> (24h) / <strong>${raw7d}</strong> (7d) &mdash; After filtering bots+internal: <strong style="color:${c24>0?'var(--green)':'var(--red)'}"> ${c24}</strong> / <strong style="color:${c7d>0?'var(--green)':'var(--red)'}"> ${c7d}</strong></div>`;

        // AI bots (informational)
        const botParts = Object.entries(bots).filter(([_,v])=>v>0).map(([k,v])=>`${k}: ${v}`).join(' &middot; ');
        ahtml += `<div style="margin-top:10px"><strong style="font-size:0.75rem;color:var(--text-secondary)">AI Bot Crawls Today:</strong> <span style="font-size:0.8rem">${botParts || 'None'}</span></div>`;
        ahtml += '</div>';

        // Right: Registrations + Decisions
        ahtml += '<div>';
        ahtml += '<strong style="font-size:0.8rem;color:var(--text-secondary)">Distribution Status</strong>';

        for (const [name, info] of Object.entries(regs)) {
            const label = name.replace(/_/g, ' ');
            if (info.status === 'live') {
                ahtml += `<div class="metric-row"><span class="metric-label">${label}</span><span class="metric-value"><span class="pill pill-green">LIVE</span> <a href="${info.url}" target="_blank" style="font-size:0.75rem;color:var(--blue)">link</a></span></div>`;
            } else if (info.status === 'pending') {
                ahtml += `<div class="metric-row"><span class="metric-label">${label}</span><span class="metric-value"><span class="pill pill-yellow">PENDING</span></span></div>`;
            } else {
                ahtml += `<div class="metric-row"><span class="metric-label">${label}</span><span class="metric-value"><span class="pill pill-blue">${info.status.toUpperCase()}</span></span></div>`;
            }
        }

        // 1 Week Decision
        if (at.week1_verdict === 'collecting') {
            ahtml += '<div style="margin-top:16px;padding:12px;border-radius:8px;background:#f0f0f0;color:#666">';
            ahtml += '<strong style="font-size:0.8rem">1 Week Decision</strong><br>';
            ahtml += '<span style="font-size:0.85rem">⏳ Collecting data — evaluation: ' + at.week1_eval_date + '</span>';
        } else {
            ahtml += '<div style="margin-top:16px;padding:12px;border-radius:8px;background:' + (at.week1_verdict==='signal'?'var(--green-light)':'var(--red-light)') + '">';
            ahtml += '<strong style="font-size:0.8rem">1 Week Decision</strong><br>';
            if (at.week1_verdict === 'signal') {
                ahtml += '<span style="font-size:0.85rem">Signal detected — continue building S5</span>';
            } else {
                ahtml += '<span style="font-size:0.85rem">No external usage yet — shift to direct outreach</span>';
            }
        }
        ahtml += '</div>';

        // 2 Week Decision
        if (at.week2_verdict === 'collecting') {
            ahtml += '<div style="margin-top:8px;padding:12px;border-radius:8px;background:#f0f0f0;color:#666">';
            ahtml += '<strong style="font-size:0.8rem">2 Week Decision</strong><br>';
            ahtml += '<span style="font-size:0.85rem">⏳ Collecting data — evaluation: ' + at.week2_eval_date + '</span>';
        } else {
            ahtml += '<div style="margin-top:8px;padding:12px;border-radius:8px;background:' + (at.week2_verdict==='wedge_working'?'var(--green-light)':at.week2_verdict==='building'?'var(--yellow-light)':'var(--red-light)') + '">';
            ahtml += '<strong style="font-size:0.8rem">2 Week Decision</strong><br>';
            if (at.week2_verdict === 'wedge_working') {
                ahtml += '<span style="font-size:0.85rem">Wedge working — proceed to Fas 2</span>';
            } else if (at.week2_verdict === 'building') {
                ahtml += '<span style="font-size:0.85rem">Some traction — keep distributing</span>';
            } else {
                ahtml += '<span style="font-size:0.85rem">Pivot distribution — find 1 builder, onboard manually</span>';
            }
        }
        ahtml += '</div>';

        ahtml += '</div></div>';
        document.getElementById('adoption-body').innerHTML = ahtml;
    }

    // Overall status
    const h = d.system_health;
    const allOk = h.redis && h.postgresql?.status === 'ok' &&
        h.launchagents?.nerq_api === 'running';
    const statusEl = document.getElementById('overall-status');
    const hpill = document.getElementById('health-pill');
    if (allOk) {
        statusEl.innerHTML = '<span class="status-dot ok"></span> All systems operational';
        hpill.className = 'pill pill-green'; hpill.textContent = 'OK';
    } else {
        statusEl.innerHTML = '<span class="status-dot warn"></span> Issues detected';
        hpill.className = 'pill pill-yellow'; hpill.textContent = 'WARN';
    }

    // System Health
    let hhtml = '<div class="service-grid">';
    for (const [name, status] of Object.entries(h.launchagents || {})) {
        hhtml += `<div class="service-item">${pill(status)} ${name.replace(/_/g, ' ')}</div>`;
    }
    hhtml += `<div class="service-item">${pill(h.redis ? 'ok' : 'error')} Redis</div>`;
    hhtml += `<div class="service-item">${pill(h.postgresql?.status || 'error')} PostgreSQL</div>`;
    hhtml += '</div>';

    // Circuit breakers
    const cbs = h.circuit_breakers || {};
    if (Object.keys(cbs).length > 0) {
        hhtml += '<div style="margin-top:12px"><strong style="font-size:0.85rem">Circuit Breakers</strong>';
        for (const [name, cb] of Object.entries(cbs)) {
            hhtml += `<div class="metric-row"><span class="metric-label">${name}</span><span class="metric-value">${pill(cb.state === 'closed' ? 'ok' : 'error')} ${cb.failures} failures</span></div>`;
        }
        hhtml += '</div>';
    }

    // Disk
    if (h.disk) {
        hhtml += `<div class="metric-row" style="margin-top:8px"><span class="metric-label">Disk</span><span class="metric-value">${h.disk.used_gb}/${h.disk.total_gb} GB (${h.disk.used_pct}%)</span></div>`;
    }
    document.getElementById('health-body').innerHTML = hhtml;

    // API Traffic
    const t = d.api_traffic || {};
    let thtml = '';
    thtml += `<div class="metric-row"><span class="metric-label">Requests (1h)</span><span class="metric-value">${fmt(t.requests_1h)}</span></div>`;
    thtml += `<div class="metric-row"><span class="metric-label">Requests (24h)</span><span class="metric-value">${fmt(t.requests_24h)}</span></div>`;
    thtml += `<div class="metric-row"><span class="metric-label">Unique IPs (24h)</span><span class="metric-value">${fmt(t.unique_ips_24h)}</span></div>`;
    thtml += `<div class="metric-row"><span class="metric-label">P50 / P95 Latency</span><span class="metric-value">${t.p50_ms}ms / ${t.p95_ms}ms</span></div>`;
    thtml += `<div class="metric-row"><span class="metric-label">Error Rate</span><span class="metric-value">${t.error_rate || 0}%</span></div>`;

    // Hourly chart
    if (t.hourly && Object.keys(t.hourly).length > 0) {
        const maxH = Math.max(...Object.values(t.hourly), 1);
        thtml += '<div class="bar-chart">';
        for (let i = 0; i < 24; i++) {
            const hr = String(i).padStart(2, '0');
            const v = t.hourly[hr] || 0;
            const pct = Math.max((v / maxH) * 100, 2);
            thtml += `<div class="bar" style="height:${pct}%" title="${hr}:00 — ${v} requests"><span class="bar-label">${i%6===0?hr:''}</span></div>`;
        }
        thtml += '</div>';
    }
    document.getElementById('traffic-body').innerHTML = thtml;

    // Crypto
    const c = d.crypto || {};
    let chtml = '';
    chtml += `<div class="metric-row"><span class="metric-label">Tokens Rated</span><span class="metric-value">${c.total_tokens || 0}</span></div>`;
    chtml += `<div class="metric-row"><span class="metric-label">Latest Run</span><span class="metric-value">${c.latest_date || '—'}</span></div>`;
    chtml += `<div class="metric-row"><span class="metric-label">Active Warnings</span><span class="metric-value" style="color:var(--yellow)">${c.warnings || 0}</span></div>`;
    chtml += `<div class="metric-row"><span class="metric-label">Critical Alerts</span><span class="metric-value" style="color:var(--red)">${c.criticals || 0}</span></div>`;
    chtml += `<div class="metric-row"><span class="metric-label">Crash Shield Saves</span><span class="metric-value">${c.crash_shield_saves || 0}</span></div>`;
    chtml += `<div class="metric-row"><span class="metric-label">Max Save (drop)</span><span class="metric-value" style="color:var(--red)">-${c.max_save_drop || 0}%</span></div>`;

    if (c.trust_distribution) {
        const ig = c.trust_distribution.investment_grade || 0;
        const sp = c.trust_distribution.speculative || 0;
        chtml += `<div class="metric-row"><span class="metric-label">Investment Grade</span><span class="metric-value" style="color:var(--green)">${ig}</span></div>`;
        chtml += `<div class="metric-row"><span class="metric-label">Speculative</span><span class="metric-value" style="color:var(--yellow)">${sp}</span></div>`;
    }
    document.getElementById('crypto-body').innerHTML = chtml;

    // Agents
    const a = d.agents || {};
    let ahtml = '';
    ahtml += `<div class="metric-row"><span class="metric-label">Total Agents</span><span class="metric-value">${fmt(a.total_agents)}</span></div>`;
    ahtml += `<div class="metric-row"><span class="metric-label">New (24h)</span><span class="metric-value">${fmt(a.new_24h)}</span></div>`;
    ahtml += `<div class="metric-row"><span class="metric-label">Trust Scored</span><span class="metric-value">${fmt(a.trust_scored)}</span></div>`;
    if (a.categories) {
        ahtml += '<div style="margin-top:8px"><strong style="font-size:0.8rem;color:var(--text-secondary)">Top Categories</strong>';
        for (const [cat, cnt] of Object.entries(a.categories)) {
            ahtml += `<div class="metric-row"><span class="metric-label">${cat}</span><span class="metric-value">${fmt(cnt)}</span></div>`;
        }
        ahtml += '</div>';
    }
    document.getElementById('agents-body').innerHTML = ahtml;

    // Top Endpoints & Tiers
    let ehtml = '<div style="display:flex;gap:24px;flex-wrap:wrap">';
    ehtml += '<div style="flex:2;min-width:250px"><table><thead><tr><th>Endpoint</th><th>Count</th></tr></thead><tbody>';
    for (const ep of (t.top_endpoints || [])) {
        ehtml += `<tr><td>${ep.endpoint}</td><td>${fmt(ep.count)}</td></tr>`;
    }
    ehtml += '</tbody></table></div>';
    ehtml += '<div style="flex:1;min-width:150px"><table><thead><tr><th>Tier</th><th>Count</th></tr></thead><tbody>';
    for (const [tier, cnt] of Object.entries(t.tier_distribution || {})) {
        ehtml += `<tr><td>${pill(tier === 'open' || tier === 'signal' ? 'ok' : tier === 'degraded' ? 'warn' : 'error')} ${tier}</td><td>${fmt(cnt)}</td></tr>`;
    }
    ehtml += '</tbody></table></div></div>';
    document.getElementById('endpoints-body').innerHTML = ehtml;

    // Scout
    const sc = d.scout || {};
    document.getElementById('scout-pill').textContent = fmt(sc.evaluated_total || 0) + ' evaluated';
    let schtml = '';
    const scLastRun = sc.last_run ? new Date(sc.last_run).toLocaleString() : '—';
    const scNextRun = sc.next_run ? new Date(sc.next_run).toLocaleString() : '—';
    schtml += `<div class="metric-row"><span class="metric-label">Last run</span><span class="metric-value">${scLastRun}</span></div>`;
    schtml += `<div class="metric-row"><span class="metric-label">Next run</span><span class="metric-value">${scNextRun}</span></div>`;
    schtml += `<div class="metric-row"><span class="metric-label">Agents evaluated (total)</span><span class="metric-value" style="font-weight:700">${fmt(sc.evaluated_total||0)}</span></div>`;
    schtml += `<div class="metric-row"><span class="metric-label">Agents featured (total)</span><span class="metric-value">${fmt(sc.featured_total||0)}</span></div>`;
    schtml += `<div class="metric-row"><span class="metric-label">Blog posts published</span><span class="metric-value">${fmt(sc.blog_posts||0)}</span></div>`;
    schtml += `<div class="metric-row"><span class="metric-label">Bluesky posts</span><span class="metric-value">${fmt(sc.bluesky_posts||0)}</span></div>`;
    schtml += `<div class="metric-row"><span class="metric-label">Dev.to articles</span><span class="metric-value">${fmt(sc.devto_articles||0)}</span></div>`;
    schtml += `<div class="metric-row"><span class="metric-label">Badge claims</span><span class="metric-value">${fmt(sc.claimed||0)}</span></div>`;
    if (sc.last_5_evaluated && sc.last_5_evaluated.length) {
        schtml += '<table style="margin-top:12px"><thead><tr><th>Agent</th><th>Score</th><th>Grade</th></tr></thead><tbody>';
        for (const a of sc.last_5_evaluated) {
            const score = a.trust_score ? a.trust_score.toFixed(1) : '—';
            const grade = a.grade || '—';
            const gcls = a.trust_score >= 70 ? 'pill-green' : a.trust_score >= 40 ? 'pill-yellow' : 'pill-red';
            schtml += `<tr><td>${a.name}</td><td>${score}</td><td><span class="pill ${gcls}">${grade}</span></td></tr>`;
        }
        schtml += '</tbody></table>';
    }
    document.getElementById('scout-body').innerHTML = schtml;

    // Sprints
    const sp = d.sprints || {};
    let shtml = '';
    shtml += `<div class="metric-row"><span class="metric-label">Queue</span><span class="metric-value">${(sp.queue||[]).length}</span></div>`;
    shtml += `<div class="metric-row"><span class="metric-label">Done</span><span class="metric-value" style="color:var(--green)">${(sp.done||[]).length}</span></div>`;
    shtml += `<div class="metric-row"><span class="metric-label">Failed</span><span class="metric-value" style="color:var(--red)">${(sp.failed||[]).length}</span></div>`;
    if ((sp.queue||[]).length) {
        shtml += '<ul class="task-list queue" style="margin-top:8px">';
        for (const t of sp.queue.slice(0, 8)) shtml += `<li>${t}</li>`;
        if (sp.queue.length > 8) shtml += `<li style="color:var(--text-secondary)">+${sp.queue.length-8} more</li>`;
        shtml += '</ul>';
    }
    if ((sp.failed||[]).length) {
        shtml += '<ul class="task-list failed" style="margin-top:6px">';
        for (const t of sp.failed) shtml += `<li>${t}</li>`;
        shtml += '</ul>';
    }
    document.getElementById('sprints-body').innerHTML = shtml;

    // Paper Trading
    const navs = c.paper_trading_nav || {};
    let phtml = '';
    for (const [portfolio, nav] of Object.entries(navs)) {
        const color = nav && nav > 100 ? 'var(--green)' : nav && nav < 100 ? 'var(--red)' : 'var(--text)';
        phtml += `<div class="metric-row"><span class="metric-label">${portfolio}</span><span class="metric-value" style="color:${color}">${nav !== null ? nav.toFixed(2) : '—'}</span></div>`;
    }
    if (!phtml) phtml = '<div class="metric-row"><span class="metric-label">No NAV data</span><span class="metric-value">—</span></div>';
    document.getElementById('paper-body').innerHTML = phtml;

    // User Intelligence
    const ui = d.user_intelligence || {};
    let uhtml = '<div style="display:flex;gap:24px;flex-wrap:wrap">';

    // User type breakdown (left)
    uhtml += '<div style="flex:1;min-width:200px">';
    uhtml += '<strong style="font-size:0.8rem;color:var(--text-secondary)">User Types (24h)</strong>';
    const typeColors = {'AI Bot':'var(--blue)','Human Browser':'var(--green)','API Client':'var(--warm)','Search Bot':'var(--yellow)','Social Bot':'#a855f7','SEO Bot':'#6366f1','Agent Framework':'var(--green)','Scanner':'var(--red)','Monitoring':'#64748b','Test Suite':'#94a3b8','Unknown':'#cbd5e1'};
    for (const [type, cnt] of Object.entries(ui.user_types || {}).sort((a,b) => b[1]-a[1])) {
        const color = typeColors[type] || 'var(--text-secondary)';
        uhtml += `<div class="metric-row"><span class="metric-label" style="color:${color}">${type}</span><span class="metric-value">${fmt(cnt)}</span></div>`;
    }
    uhtml += '</div>';

    // AI bot breakdown + new vs returning (right)
    uhtml += '<div style="flex:1;min-width:200px">';
    uhtml += '<strong style="font-size:0.8rem;color:var(--text-secondary)">AI Bot Breakdown</strong>';
    const botColors = {'Claude':'#d97706','ChatGPT':'#10b981','Perplexity':'#6366f1','Google':'#2563eb','Bing':'#0ea5e9'};
    for (const [bot, cnt] of Object.entries(ui.ai_bots || {}).sort((a,b) => b[1]-a[1])) {
        uhtml += `<div class="metric-row"><span class="metric-label" style="color:${botColors[bot]||'var(--text)'}">${bot}</span><span class="metric-value">${cnt}</span></div>`;
    }
    if (!Object.keys(ui.ai_bots||{}).length) uhtml += '<div class="metric-row"><span class="metric-label">No AI bots detected</span></div>';
    const nvr = ui.new_vs_returning || {};
    uhtml += `<div style="margin-top:12px"><strong style="font-size:0.8rem;color:var(--text-secondary)">New vs Returning</strong></div>`;
    uhtml += `<div class="metric-row"><span class="metric-label">New IPs today</span><span class="metric-value" style="color:var(--green)">${nvr.new_today||0}</span></div>`;
    uhtml += `<div class="metric-row"><span class="metric-label">Returning IPs</span><span class="metric-value">${nvr.returning_today||0}</span></div>`;
    uhtml += '</div></div>';

    // Top 10 active users table
    if ((ui.top_users||[]).length) {
        uhtml += '<table style="margin-top:16px"><thead><tr><th>IP Hash</th><th>Type</th><th>Top Endpoint</th><th>Reqs</th></tr></thead><tbody>';
        for (const u of ui.top_users) {
            const typePill = u.type === 'Human Browser' ? 'pill-green' : u.type === 'AI Bot' || u.type === 'Agent Framework' ? 'pill-blue' : u.type === 'Social Bot' ? 'pill-yellow' : '';
            uhtml += `<tr><td style="font-family:JetBrains Mono,monospace;font-size:0.75rem">${u.ip.slice(0,12)}...</td><td><span class="pill ${typePill}">${u.type}</span></td><td style="font-size:0.8rem">${u.top_endpoint}</td><td>${fmt(u.requests)}</td></tr>`;
        }
        uhtml += '</tbody></table>';
    }
    document.getElementById('users-body').innerHTML = uhtml;

    // Token Check Activity
    const tc = ui.token_checks || {};
    let tchtml = '';
    tchtml += `<div class="metric-row"><span class="metric-label">Total checks (7d)</span><span class="metric-value">${tc.total||0}</span></div>`;
    tchtml += `<div class="metric-row"><span class="metric-label">Unique tokens</span><span class="metric-value">${tc.unique_tokens||0}</span></div>`;
    if ((tc.tokens||[]).length) {
        tchtml += '<table style="margin-top:8px"><thead><tr><th>Token</th><th>Checks</th><th>IPs</th></tr></thead><tbody>';
        for (const tk of tc.tokens) {
            tchtml += `<tr><td>${tk.token}</td><td>${tk.calls}</td><td>${tk.unique_ips}</td></tr>`;
        }
        tchtml += '</tbody></table>';
    } else {
        tchtml += '<div style="color:var(--text-secondary);font-size:0.85rem;margin-top:8px">No token checks in last 7 days</div>';
    }
    document.getElementById('token-checks-body').innerHTML = tchtml;

    // Active API Integrations + AI Bot Coverage
    const ai_cov = ui.ai_bot_coverage_7d || 0;
    const ri = ui.active_integrations || [];
    document.getElementById('integration-count').textContent = ri.length;
    let rihtml = `<div style="display:flex;gap:2rem;margin-bottom:12px;font-size:0.85rem">
        <div><span style="font-weight:600">${ri.length}</span> active API integrations <span style="color:var(--text-secondary)">(non-bot IPs with ≥3 calls to /v1/* in 7d)</span></div>
        <div><span style="font-weight:600">${fmt(ai_cov)}</span> pages indexed by AI systems <span style="color:var(--text-secondary)">(7d)</span></div>
    </div>`;
    if (ri.length) {
        rihtml += '<table><thead><tr><th>IP</th><th>Type</th><th>Calls</th><th>Endpoints</th><th>Last Seen</th></tr></thead><tbody>';
        for (const r of ri) {
            rihtml += `<tr><td style="font-family:JetBrains Mono,monospace;font-size:0.75rem">${r.ip.slice(0,12)}...</td><td><span class="pill">${r.type}</span></td><td>${r.calls}</td><td>${r.endpoints}</td><td style="font-size:0.8rem">${r.last.slice(5)}</td></tr>`;
        }
        rihtml += '</tbody></table>';
    }
    document.getElementById('integration-body').innerHTML = rihtml;
}

// Initial load + auto-refresh
fetchData();
setInterval(fetchData, 60000);
</script>
</body>
</html>"""
