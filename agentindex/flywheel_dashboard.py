"""
Nerq Flywheel Dashboard v3 — Full Pipeline + Machine-First
============================================================
Route: /flywheel?period=24h|7d|30d|all
Measures the complete pipeline: Universe → Captured → Enriched → Pages → Indexed → Cited

Data sources:
  - ~/agentindex/logs/analytics.db (requests + preflight_analytics)
  - PostgreSQL agentindex (software_registry + agents enrichment status)
"""

import html as html_mod
import logging
import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from agentindex.db.models import get_session

logger = logging.getLogger("nerq.flywheel")

ANALYTICS_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "analytics.db")

# Cache per period — file-backed for cross-worker sharing + restart survival
_cache = {}
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "flywheel_cache")
os.makedirs(_CACHE_DIR, exist_ok=True)
_GENERATING = set()  # periods currently being generated in background
CACHE_TTLS = {"24h": 300, "7d": 1800, "30d": 3600, "all": 7200}  # 5min/30min/1h/2h — stale-while-revalidate


def _cache_path(period):
    return os.path.join(_CACHE_DIR, f"nerq_flywheel_{period}.json")


def _read_file_cache(period):
    """Read cached HTML from /tmp file. Returns (html, mtime) or (None, 0)."""
    p = _cache_path(period)
    try:
        st = os.stat(p)
        with open(p, "r") as f:
            return f.read(), st.st_mtime
    except (OSError, IOError):
        return None, 0


def _write_file_cache(period, html):
    """Write HTML to /tmp file atomically."""
    p = _cache_path(period)
    tmp = p + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write(html)
        os.replace(tmp, p)
    except (OSError, IOError) as e:
        logger.warning(f"Failed to write flywheel cache: {e}")

PERIODS = {
    "24h": {"sqlite": "strftime('%Y-%m-%dT%H:%M:%f', 'now', '-24 hours')", "prev_s": "strftime('%Y-%m-%dT%H:%M:%f', 'now', '-48 hours')", "prev_e": "strftime('%Y-%m-%dT%H:%M:%f', 'now', '-24 hours')", "label": "24h", "gran": "%H:00"},
    "7d":  {"sqlite": "strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')",   "prev_s": "strftime('%Y-%m-%dT%H:%M:%f', 'now', '-14 days')",  "prev_e": "strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')",   "label": "7 days", "gran": "%Y-%m-%d"},
    "30d": {"sqlite": "strftime('%Y-%m-%dT%H:%M:%f', 'now', '-30 days')",  "prev_s": "strftime('%Y-%m-%dT%H:%M:%f', 'now', '-60 days')",  "prev_e": "strftime('%Y-%m-%dT%H:%M:%f', 'now', '-30 days')",  "label": "30 days", "gran": "%Y-%m-%d"},
    "all": {"sqlite": "'2026-03-08'",                "prev_s": "'2026-01-01'",                 "prev_e": "'2026-03-08'",                 "label": "all time", "gran": "%Y-%m-%d"},
}

UNIVERSE = {
    "npm": 3_000_000, "pypi": 500_000, "nuget": 400_000, "crates": 150_000,
    "wordpress": 60_000, "vscode": 50_000, "ios": 2_000_000, "android": 3_500_000,
    "steam": 70_000, "go": 150_000, "gems": 170_000, "packagist": 400_000,
    "homebrew": 10_000, "firefox": 35_000, "chrome": 200_000,
    "website": 200_000_000, "vpn": 100, "saas": 10_000, "ai_tool": 5_000,
    "crypto": 20_000, "country": 195, "city": 10_000, "charity": 1_500_000,
    "ingredient": 5_000, "supplement": 90_000, "cosmetic_ingredient": 30_000,
}

PATTERNS_PER_TYPE = {
    "npm": 13, "pypi": 13, "nuget": 13, "crates": 13, "gems": 13, "go": 13, "packagist": 13,
    "wordpress": 12, "vscode": 8, "ios": 18, "android": 18, "steam": 8,
    "firefox": 8, "chrome": 8, "website": 15, "vpn": 17, "homebrew": 10,
    "saas": 15, "ai_tool": 15, "crypto": 10, "country": 36, "city": 36,
    "charity": 15, "ingredient": 15, "supplement": 15, "cosmetic_ingredient": 15,
}

# Vertical grouping for summary
VERTICAL_MAP = {
    "Software": {"npm", "pypi", "nuget", "crates", "go", "packagist", "gems", "homebrew",
                  "wordpress", "chrome", "firefox", "vscode", "ios", "android", "steam", "vpn",
                  "website", "saas", "ai_tool", "crypto"},
    "Travel": {"country", "city"},
    "Charities": {"charity"},
    "Ingredients": {"ingredient"},
    "Supplements": {"supplement"},
    "Cosmetics": {"cosmetic_ingredient"},
}

from agentindex.i18n import LANG_COUNT as LANGS  # was: hardcoded 23


def _esc(s):
    return html_mod.escape(str(s)) if s else ""


def _fmt(n):
    if n is None: return "0"
    n = int(n)
    if n >= 1_000_000_000: return f"{n/1e9:.1f}B"
    if n >= 1_000_000: return f"{n/1e6:.1f}M"
    if n >= 1_000: return f"{n/1e3:.1f}K"
    return str(n)


def _pct(a, b):
    if not b: return "0%"
    return f"{100*a/b:.1f}%"


def _delta(cur, prev):
    if not prev: return "+new" if cur else "—"
    d = ((cur - prev) / prev) * 100
    return f"{'+'if d>=0 else ''}{d:.0f}%"


def _color(pct_val):
    if pct_val >= 90: return "#16a34a"
    if pct_val >= 50: return "#22c55e"
    if pct_val >= 10: return "#f59e0b"
    return "#ef4444"


def _bottleneck(capture_pct, enrich_pct, index_pct):
    if capture_pct < 10: return ("Capture", "#ef4444")
    if enrich_pct < 50: return ("Enrichment", "#f59e0b")
    if index_pct < 1: return ("Indexing", "#3b82f6")
    return ("Scale", "#16a34a")


def _get_data(period_key):
    """Gather all data from both SQLite analytics and PostgreSQL."""
    p = PERIODS.get(period_key, PERIODS["24h"])
    since, prev_s, prev_e, gran = p["sqlite"], p["prev_s"], p["prev_e"], p["gran"]
    data = {}

    # ── SQLite analytics ──
    conn = sqlite3.connect(ANALYTICS_DB, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # AI citations (200 only, excluding preflight and GPTBot indexing)
    r = conn.execute(f"SELECT COUNT(*) as c FROM requests WHERE ts>{since} AND is_ai_bot=1 AND status=200 AND path NOT LIKE '/v1/preflight%' AND user_agent NOT LIKE '%GPTBot%'").fetchone()
    data["ai_total"] = r["c"] or 0
    r2 = conn.execute(f"SELECT COUNT(*) as c FROM requests WHERE ts>{prev_s} AND ts<{prev_e} AND is_ai_bot=1 AND status=200 AND path NOT LIKE '/v1/preflight%' AND user_agent NOT LIKE '%GPTBot%'").fetchone()
    data["ai_prev"] = r2["c"] or 0

    # AI Indexing (GPTBot only, 200)
    ri = conn.execute(f"SELECT COUNT(*) as c FROM requests WHERE ts>{since} AND is_ai_bot=1 AND status=200 AND path NOT LIKE '/v1/preflight%' AND user_agent LIKE '%GPTBot%'").fetchone()
    data["ai_index_total"] = ri["c"] or 0
    ri2 = conn.execute(f"SELECT COUNT(*) as c FROM requests WHERE ts>{prev_s} AND ts<{prev_e} AND is_ai_bot=1 AND status=200 AND path NOT LIKE '/v1/preflight%' AND user_agent LIKE '%GPTBot%'").fetchone()
    data["ai_index_prev"] = ri2["c"] or 0

    # By bot (citations only — exclude GPTBot)
    rows = conn.execute(f"SELECT bot_name, COUNT(*) as c FROM requests WHERE ts>{since} AND is_ai_bot=1 AND status=200 AND path NOT LIKE '/v1/preflight%' AND user_agent NOT LIKE '%GPTBot%' GROUP BY 1 ORDER BY 2 DESC LIMIT 6").fetchall()
    data["ai_bots"] = [(r["bot_name"], r["c"]) for r in rows]

    # Preflight (AI bots only — Meta/Amazon/Google are not AI citations)
    _AI_PF = "('ChatGPT','Claude','Perplexity','ByteDance')"
    pf = conn.execute(f"SELECT COUNT(*) as c, COUNT(DISTINCT target) as t FROM preflight_analytics WHERE ts>{since} AND bot_name IN {_AI_PF}").fetchone()
    data["pf_total"] = pf["c"] or 0
    data["pf_targets"] = pf["t"] or 0
    pf2 = conn.execute(f"SELECT COUNT(*) as c FROM preflight_analytics WHERE ts>{prev_s} AND ts<{prev_e} AND bot_name IN {_AI_PF}").fetchone()
    data["pf_prev"] = pf2["c"] or 0
    data["pf_bots"] = [(r["bot_name"] or "?", r["c"]) for r in conn.execute(f"SELECT bot_name,COUNT(*) as c FROM preflight_analytics WHERE ts>{since} AND bot_name IN {_AI_PF} GROUP BY 1 ORDER BY 2 DESC LIMIT 4").fetchall()]
    # Non-AI preflight count (Meta, Amazon, Google, etc.)
    pf_nonai = conn.execute(f"SELECT COUNT(*) as c FROM preflight_analytics WHERE ts>{since} AND (bot_name NOT IN {_AI_PF} OR bot_name IS NULL)").fetchone()
    data["pf_nonai_total"] = pf_nonai["c"] or 0

    # Total AI Usage = citations + preflight
    data["ai_usage_total"] = data["ai_total"] + data["pf_total"]
    data["ai_usage_prev"] = data["ai_prev"] + data["pf_prev"]

    # Total Crawling (separate Meta, Amazon, other bots)
    cr = conn.execute(f"""SELECT
        SUM(CASE WHEN is_ai_bot=1 AND status=200 AND user_agent NOT LIKE '%GPTBot%' AND path NOT LIKE '/v1/preflight%' THEN 1 ELSE 0 END) as ai_cite,
        SUM(CASE WHEN is_ai_bot=1 AND status=200 AND user_agent LIKE '%GPTBot%' AND path NOT LIKE '/v1/preflight%' THEN 1 ELSE 0 END) as ai_index,
        SUM(CASE WHEN is_ai_bot=0 AND bot_name IN ('Google','Bing','Yandex','Apple','DuckDuck') AND status=200 THEN 1 ELSE 0 END) as search,
        SUM(CASE WHEN bot_name = 'Meta' AND status=200 THEN 1 ELSE 0 END) as meta,
        SUM(CASE WHEN bot_name = 'Amazon' AND status=200 THEN 1 ELSE 0 END) as amazon,
        SUM(CASE WHEN is_bot=1 AND is_ai_bot=0 AND bot_name NOT IN ('Google','Bing','Yandex','Apple','DuckDuck','Meta','Amazon') AND status=200 THEN 1 ELSE 0 END) as other_bots,
        COUNT(*) as all_bots
    FROM requests WHERE ts>{since} AND is_bot=1""").fetchone()
    data["crawl_ai_cite"] = cr["ai_cite"] or 0
    data["crawl_ai_index"] = cr["ai_index"] or 0
    data["crawl_search"] = cr["search"] or 0
    data["crawl_meta"] = cr["meta"] or 0
    data["crawl_amazon"] = cr["amazon"] or 0
    data["crawl_other_bots"] = cr["other_bots"] or 0
    data["crawl_total"] = cr["all_bots"] or 0
    cr2 = conn.execute(f"SELECT COUNT(*) as c FROM requests WHERE ts>{prev_s} AND ts<{prev_e} AND is_bot=1").fetchone()
    data["crawl_prev"] = cr2["c"] or 0

    # Total traffic
    t = conn.execute(f"SELECT COUNT(*) as total, SUM(CASE WHEN is_bot=1 THEN 1 ELSE 0 END) as bots, SUM(CASE WHEN is_bot=0 THEN 1 ELSE 0 END) as humans, COUNT(DISTINCT ip) as ips FROM requests WHERE ts>{since}").fetchone()
    data["total"] = t["total"] or 0; data["bots"] = t["bots"] or 0; data["humans"] = t["humans"] or 0; data["ips"] = t["ips"] or 0

    # Citation quality: endpoint × bot (status=200, separates GPTBot)
    pat_sql = f"""SELECT
        CASE WHEN path LIKE '/v1/preflight%' THEN '/v1/preflight'
             WHEN path LIKE '/is-%-safe%' THEN '/is-*-safe'
             WHEN path LIKE '/safe/%' THEN '/safe/*'
             WHEN path LIKE '/alternatives/%' THEN '/alternatives/*'
             WHEN path LIKE '/compare/%' THEN '/compare/*'
             WHEN path LIKE '/privacy/%' THEN '/privacy/*'
             WHEN path LIKE '/review/%' THEN '/review/*'
             WHEN path LIKE '/model/%' THEN '/model/*'
             WHEN path LIKE '/token/%' THEN '/token/*'
             WHEN path='/' THEN 'homepage'
             WHEN path LIKE '/crypto%' OR path LIKE '/zarq%' THEN 'ZARQ'
             ELSE 'other' END as pat,
        CASE WHEN user_agent LIKE '%GPTBot%' THEN 'GPTBot (Index)'
             WHEN bot_name LIKE '%Claude%' THEN 'Claude'
             WHEN bot_name LIKE '%ChatGPT%' OR bot_name LIKE '%OpenAI%' THEN 'ChatGPT'
             WHEN bot_name LIKE '%Perplexity%' THEN 'Perplexity' ELSE 'Other' END as bot,
        COUNT(*) as c
    FROM requests WHERE ts>{since} AND is_ai_bot=1 AND status=200 GROUP BY 1,2"""
    patterns = {}
    for r in conn.execute(pat_sql).fetchall():
        pat = r["pat"]
        if pat not in patterns: patterns[pat] = {"Claude": 0, "ChatGPT": 0, "Perplexity": 0, "GPTBot (Index)": 0, "Other": 0, "total": 0}
        patterns[pat][r["bot"]] = r["c"]; patterns[pat]["total"] += r["c"]
    data["patterns"] = dict(sorted(patterns.items(), key=lambda x: x[1]["total"], reverse=True))

    # Crawl efficiency
    eff_sql = f"""SELECT bot_name, COUNT(*) as total,
        SUM(CASE WHEN status=200 THEN 1 ELSE 0 END) as ok,
        SUM(CASE WHEN status=404 THEN 1 ELSE 0 END) as nf,
        SUM(CASE WHEN status=429 THEN 1 ELSE 0 END) as rl
    FROM requests WHERE ts>{since} AND is_bot=1
    AND bot_name IN ('Claude','ChatGPT','Google','Bing','Perplexity','Meta','Yandex','ByteDance')
    GROUP BY 1 ORDER BY 2 DESC"""
    data["efficiency"] = [dict(r) for r in conn.execute(eff_sql).fetchall()]

    # Demand without supply (AI 404s)
    dem_sql = f"""SELECT path, bot_name, COUNT(*) as c FROM requests
    WHERE ts>{since} AND is_ai_bot=1 AND status=404
    AND path NOT LIKE '/static/%' AND path NOT LIKE '/favicon%' AND path NOT LIKE '/.%'
    GROUP BY 1,2 ORDER BY 3 DESC LIMIT 20"""
    data["demand_404"] = [(r["path"], r["bot_name"], r["c"]) for r in conn.execute(dem_sql).fetchall()]

    # Trend (for Chart.js)
    # For 24h: rolling 24h grouped by actual datetime hour, chronological order
    # For other periods: same as before but with per-bot prev data
    _bot_cols = """
        SUM(CASE WHEN bot_name LIKE '%Claude%' AND status=200 AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END) as claude,
        SUM(CASE WHEN (bot_name LIKE '%ChatGPT%' OR bot_name LIKE '%OpenAI%') AND status=200 AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END) as chatgpt,
        SUM(CASE WHEN bot_name LIKE '%Perplexity%' AND status=200 AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END) as perplexity,
        SUM(CASE WHEN (bot_name LIKE '%Byte%' OR bot_name LIKE '%bytespider%') AND status=200 AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END) as bytedance,
        SUM(CASE WHEN is_ai_bot=1 AND status=200 AND user_agent NOT LIKE '%GPTBot%' AND path NOT LIKE '/v1/preflight%' THEN 1 ELSE 0 END) as citations,
        0 as preflight"""  # preflight approximated as 0 in trend; shown separately from preflight_analytics

    if period_key == "24h":
        # Two separate queries — current 24h and previous 24h.
        # Each groups into exactly 24 hour-of-day buckets using strftime('%H').
        # Same filter as boxes: is_ai_bot=1 AND status=200.
        _cur_hourly = conn.execute("""
            SELECT strftime('%H', ts) as h,
                SUM(CASE WHEN bot_name LIKE '%Claude%' AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN (bot_name LIKE '%ChatGPT%' OR bot_name LIKE '%OpenAI%') AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN bot_name LIKE '%Perplexity%' AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN (bot_name LIKE '%Byte%' OR bot_name LIKE '%bytespider%') AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END),
                COUNT(CASE WHEN user_agent NOT LIKE '%GPTBot%' AND path NOT LIKE '/v1/preflight%' THEN 1 END), 0
            FROM requests
            WHERE ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-24 hours') AND is_ai_bot=1 AND status=200
            GROUP BY h
        """).fetchall()
        _prev_hourly = conn.execute("""
            SELECT strftime('%H', ts) as h,
                SUM(CASE WHEN bot_name LIKE '%Claude%' AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN (bot_name LIKE '%ChatGPT%' OR bot_name LIKE '%OpenAI%') AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN bot_name LIKE '%Perplexity%' AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END),
                SUM(CASE WHEN (bot_name LIKE '%Byte%' OR bot_name LIKE '%bytespider%') AND user_agent NOT LIKE '%GPTBot%' THEN 1 ELSE 0 END),
                COUNT(CASE WHEN user_agent NOT LIKE '%GPTBot%' AND path NOT LIKE '/v1/preflight%' THEN 1 END), 0
            FROM requests
            WHERE ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-48 hours') AND ts < strftime('%Y-%m-%dT%H:%M:%f', 'now', '-24 hours')
                AND is_ai_bot=1 AND status=200
            GROUP BY h
        """).fetchall()

        _cur_by_h = {r[0]: tuple(v or 0 for v in r[1:]) for r in _cur_hourly}
        _prev_by_h = {r[0]: tuple(v or 0 for v in r[1:]) for r in _prev_hourly}

        # Build 24 slots in rolling order: oldest hour first, current hour last
        # Current hour (UTC) from SQLite
        _cur_h = int(conn.execute("SELECT strftime('%H', 'now')").fetchone()[0])
        _hours_ordered = [(_cur_h - 23 + i) % 24 for i in range(24)]

        _trend_labels = []
        _trend_cur = []
        _trend_prev = []
        _zero = (0, 0, 0, 0, 0, 0)
        for h in _hours_ordered:
            hkey = f"{h:02d}"
            _trend_labels.append(str(h))
            _trend_cur.append(_cur_by_h.get(hkey, _zero))
            _trend_prev.append(_prev_by_h.get(hkey, _zero))

        # columns per tuple: claude, chatgpt, perplexity, bytedance, citations, preflight
        data["trend"] = [(_trend_labels[i],) + _trend_cur[i] for i in range(24)]
        data["prev_trend_list"] = list(_trend_prev)
    else:
        trend_sql = f"""SELECT strftime('{gran}', ts) as bucket, {_bot_cols}
        FROM requests WHERE ts>{since} AND (is_ai_bot=1 OR path LIKE '/v1/preflight%')
        GROUP BY 1 ORDER BY 1"""
        prev_trend_sql = f"""SELECT strftime('{gran}', ts) as bucket, {_bot_cols}
        FROM requests WHERE ts>{prev_s} AND ts<{prev_e} AND (is_ai_bot=1 OR path LIKE '/v1/preflight%')
        GROUP BY 1 ORDER BY 1"""
        _cur_rows = conn.execute(trend_sql).fetchall()
        _prev_rows = conn.execute(prev_trend_sql).fetchall()
        data["trend"] = [(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in _cur_rows]
        data["prev_trend_list"] = [(r[1], r[2], r[3], r[4], r[5], r[6]) for r in _prev_rows]

    # Status codes
    data["status"] = [(r[0], r[1]) for r in conn.execute(f"SELECT status, COUNT(*) FROM requests WHERE ts>{since} GROUP BY 1 ORDER BY 2 DESC LIMIT 6").fetchall()]

    conn.close()

    # ── PostgreSQL: enrichment pipeline ──
    try:
        session = get_session()
        rows = session.execute(text("""
            SELECT registry, COUNT(*) as total,
                   COUNT(enriched_at) as enriched,
                   COUNT(CASE WHEN trust_score >= 30 AND description IS NOT NULL AND LENGTH(description) > 20 THEN 1 END) as indexable,
                   COUNT(CASE WHEN security_score IS NOT NULL THEN 1 END) as has_dims,
                   COUNT(CASE WHEN cve_count>0 THEN 1 END) as has_cves,
                   COUNT(CASE WHEN description IS NOT NULL AND description!='' THEN 1 END) as has_desc,
                   ROUND(AVG(CASE WHEN enriched_at IS NOT NULL THEN trust_score END)::numeric, 1) as avg_score
            FROM software_registry GROUP BY registry ORDER BY COUNT(*) DESC
        """)).fetchall()
        data["pipeline"] = [dict(zip(["reg","total","enriched","indexable","has_dims","has_cves","has_desc","avg"], r)) for r in rows]

        # agents count
        ac = session.execute(text("SELECT COUNT(*) FROM entity_lookup WHERE is_active=true")).scalar()
        data["agents_count"] = ac or 0

        # Kings data
        king_rows = session.execute(text("""
            SELECT registry,
                COUNT(*) FILTER (WHERE is_king) as kings,
                COUNT(*) FILTER (WHERE is_king AND enriched_at IS NOT NULL) as kings_enriched,
                COUNT(*) FILTER (WHERE is_king AND trust_score >= 30 AND description IS NOT NULL AND length(description) > 5) as kings_indexable
            FROM software_registry
            GROUP BY registry
            HAVING COUNT(*) FILTER (WHERE is_king) > 0
            ORDER BY COUNT(*) FILTER (WHERE is_king) DESC
        """)).fetchall()
        data["kings"] = [dict(zip(["reg", "kings", "kings_enriched", "kings_indexable"], r)) for r in king_rows]
        data["kings_total"] = sum(r[1] for r in king_rows)
        data["kings_enriched"] = sum(r[2] for r in king_rows)
        data["kings_indexable"] = sum(r[3] for r in king_rows)

        session.close()
    except Exception as e:
        logger.warning(f"PG error: {e}")
        data["pipeline"] = []
        data["agents_count"] = 0

    # Enrichment processes
    try:
        result = subprocess.run(["pgrep", "-fa", "enrichment"], capture_output=True, text=True, timeout=3)
        data["enrichment_procs"] = len([l for l in result.stdout.strip().split("\n") if l.strip()])
    except Exception:
        data["enrichment_procs"] = 0

    # ── Infrastructure metrics ──
    try:
        load_out = subprocess.run(["sysctl", "-n", "vm.loadavg"], capture_output=True, text=True, timeout=3)
        data["load_avg"] = float(load_out.stdout.strip().split()[1]) if load_out.stdout.strip() else 0
    except Exception:
        data["load_avg"] = 0
    try:
        df_out = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=3)
        data["disk_pct"] = int(df_out.stdout.strip().split("\n")[1].split()[4].rstrip("%"))
    except Exception:
        data["disk_pct"] = 0
    try:
        _s2 = get_session()
        data["pg_connections"] = _s2.execute(text("SELECT COUNT(*) FROM pg_stat_activity")).scalar() or 0
        _s2.close()
    except Exception:
        data["pg_connections"] = 0
    # Redis page cache stats
    data["cache_stats"] = None
    try:
        import redis as _redis
        _rc = _redis.Redis(host='localhost', port=6379, db=1, socket_timeout=0.1)
        _info = _rc.info("stats")
        _hits = _info.get("keyspace_hits", 0)
        _misses = _info.get("keyspace_misses", 0)
        _total = _hits + _misses
        data["cache_stats"] = {
            "hit_rate": round(100 * _hits / _total, 1) if _total > 0 else 0,
            "hits": _hits, "misses": _misses,
            "pages": _rc.dbsize(),
            "memory": _rc.info("memory").get("used_memory_human", "?"),
        }
    except Exception:
        pass
    # Request volume from SQLite
    try:
        _conn2 = sqlite3.connect(ANALYTICS_DB, timeout=30, check_same_thread=False)
        data["requests_total"] = _conn2.execute(f"SELECT COUNT(*) FROM requests WHERE ts>{since}").fetchone()[0]
        _conn2.close()
    except Exception:
        data["requests_total"] = 0

    # Indexation KPI (from CSV log)
    data["idx_kpi"] = []
    try:
        import csv
        _kpi_path = Path(__file__).parent.parent / "logs" / "indexation_kpi.csv"
        if _kpi_path.exists():
            with open(_kpi_path) as f:
                data["idx_kpi"] = list(csv.DictReader(f))
    except Exception:
        pass

    # AI Market Share (only if real data exists)
    data["ai_share"] = None
    try:
        _share_path = Path(__file__).parent.parent / "data" / "ai_market_share.json"
        if _share_path.exists():
            with open(_share_path) as f:
                _share = json.load(f)
            _platforms = _share.get("platforms", {})
            _total_visits = sum((p.get("monthly_visits_M") or 0) for p in _platforms.values())
            if _total_visits > 0 and _share.get("updated"):
                # Compute global share per platform
                _global = {n: round(100 * (p.get("monthly_visits_M") or 0) / _total_visits, 1) for n, p in _platforms.items()}
                # Our share from current period bot data
                _our_bots = {b: c for b, c in data.get("ai_bots", [])}
                _our_total = sum(_our_bots.values()) or 1
                _our = {}
                for name in _platforms:
                    matched = sum(c for b, c in _our_bots.items() if name.lower() in b.lower())
                    _our[name] = round(100 * matched / _our_total, 1)
                # Build index
                _rows = []
                for name in _platforms:
                    g = _global.get(name, 0)
                    o = _our.get(name, 0)
                    idx = round(100 * o / g) if g > 0 else 0
                    _rows.append({"platform": name, "our": o, "global": g, "index": idx})
                data["ai_share"] = {
                    "updated": _share.get("updated"),
                    "source": _share.get("source", ""),
                    "platforms": sorted(_rows, key=lambda x: x["index"], reverse=True),
                }
    except Exception:
        pass

    # ── Funnel metrics ──
    data["funnel"] = {}
    try:
        _pipe = data.get("pipeline", [])
        _total_entities = sum(e["total"] for e in _pipe)
        _enriched_total = sum(e["enriched"] for e in _pipe)
        _indexable_total = sum(e.get("indexable", 0) for e in _pipe)

        # ── Potential = indexable entities × patterns × languages ──
        _potential_en = sum(e.get("indexable", 0) * PATTERNS_PER_TYPE.get(e["reg"], 13) for e in _pipe)
        _potential_all = _potential_en * LANGS
        data["funnel"]["entities"] = _total_entities
        data["funnel"]["enriched"] = _enriched_total
        data["funnel"]["indexable"] = _indexable_total
        data["funnel"]["potential_pages"] = _potential_all

        # ── Live = EN core patterns + localized (2 URLs per entity × 21 langs) ──
        _core_patterns = _potential_en  # EN: indexable × patterns
        _core_estimate = _core_patterns + 75000  # + compare/alt/guide/model/best
        _LANG_PATTERNS = 2  # /{lang}/safe/{slug} + /{lang}/{localized-slug}
        _lang_urls = _indexable_total * _LANG_PATTERNS * (LANGS - 1)
        _live_in_sitemaps = _core_estimate + _lang_urls
        data["funnel"]["live_pages"] = _live_in_sitemaps
        data["funnel"]["core_en"] = _core_estimate
        data["funnel"]["lang_urls"] = _lang_urls

        # ── Submitted to IndexNow = tracked from state file ──
        _submitted = 0
        try:
            _state_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                        "agentindex", "auto_indexnow_state.json")
            if os.path.exists(_state_path):
                import json as _json_f
                _st = _json_f.load(open(_state_path))
                _submitted = len(_st.get("nerq_urls", [])) + len(_st.get("zarq_urls", []))
        except Exception:
            pass
        data["funnel"]["submitted"] = _submitted if _submitted > 0 else _live_in_sitemaps

        # ── Crawled: unique paths, at least once, by any bot (all time + period) ──
        _fconn = sqlite3.connect(ANALYTICS_DB, timeout=30)
        _crawled_alltime = _fconn.execute("SELECT COUNT(DISTINCT path) FROM requests WHERE is_bot=1 AND status=200").fetchone()[0]
        _crawled_period = _fconn.execute(f"SELECT COUNT(DISTINCT path) FROM requests WHERE is_bot=1 AND status=200 AND ts>{since}").fetchone()[0]

        # ── AI cited: unique pages + total hits (period, citations only — no GPTBot/preflight) ──
        _cited_period = _fconn.execute(f"SELECT COUNT(DISTINCT path) FROM requests WHERE is_ai_bot=1 AND status=200 AND user_agent NOT LIKE '%GPTBot%' AND path NOT LIKE '/v1/preflight%' AND ts>{since}").fetchone()[0]
        _cited_total_period = _fconn.execute(f"SELECT COUNT(*) FROM requests WHERE is_ai_bot=1 AND status=200 AND user_agent NOT LIKE '%GPTBot%' AND path NOT LIKE '/v1/preflight%' AND ts>{since}").fetchone()[0]

        # Per-segment yield: by registry (extract from path)
        _seg_rows = _fconn.execute(f"""
            SELECT
                CASE
                    WHEN path LIKE '/safe/npm-%' OR path LIKE '/is-npm-%' THEN 'npm'
                    WHEN path LIKE '/safe/pypi-%' OR path LIKE '/is-pypi-%' THEN 'pypi'
                    WHEN path LIKE '/token/%' THEN 'crypto'
                    WHEN path LIKE '/model/%' OR path LIKE '/dataset/%' THEN 'huggingface'
                    WHEN path LIKE '/%/safe/%' THEN 'localized'
                    WHEN path LIKE '/safe/%' THEN 'safe_en'
                    WHEN path LIKE '/is-%' THEN 'pattern_en'
                    WHEN path LIKE '/compare/%' THEN 'compare'
                    WHEN path LIKE '/alternatives/%' THEN 'alternatives'
                    WHEN path LIKE '/best/%' THEN 'best'
                    ELSE 'other'
                END as segment,
                COUNT(DISTINCT path) as unique_pages,
                COUNT(*) as total_hits,
                SUM(CASE WHEN is_ai_bot=1 THEN 1 ELSE 0 END) as ai_hits
            FROM requests WHERE ts>{since} AND is_bot=1 AND status=200
            GROUP BY segment ORDER BY ai_hits DESC
        """).fetchall()
        data["funnel"]["segments"] = [{"seg": r[0], "pages": r[1], "hits": r[2], "ai": r[3]} for r in _seg_rows]

        # Per-language yield
        _lang_yield = _fconn.execute(f"""
            SELECT
                CASE
                    WHEN path LIKE '/es/%' THEN 'es' WHEN path LIKE '/de/%' THEN 'de'
                    WHEN path LIKE '/fr/%' THEN 'fr' WHEN path LIKE '/ja/%' THEN 'ja'
                    WHEN path LIKE '/pt/%' THEN 'pt' ELSE 'en'
                END as lang,
                COUNT(DISTINCT path) as crawled_pages,
                SUM(CASE WHEN is_ai_bot=1 THEN 1 ELSE 0 END) as ai_citations
            FROM requests WHERE ts>{since} AND is_bot=1 AND status=200
            GROUP BY lang ORDER BY ai_citations DESC
        """).fetchall()
        data["funnel"]["lang_yield"] = [{"lang": r[0], "crawled": r[1], "ai": r[2]} for r in _lang_yield]

        _fconn.close()
        data["funnel"]["crawled_alltime"] = _crawled_alltime
        data["funnel"]["crawled_period"] = _crawled_period
        data["funnel"]["cited_pages"] = _cited_period
        data["funnel"]["cited_total"] = _cited_total_period
    except Exception as _fe:
        logger.warning(f"Funnel data error: {_fe}")
        data["funnel"] = {"potential_pages": 0, "live_pages": 0, "submitted": 0, "crawled_alltime": 0, "crawled_period": 0, "cited_pages": 0, "cited_total": 0, "segments": [], "lang_yield": []}

    # ── Daily crawl trend (for Growth Engine companion chart) ──
    data["daily_crawls"] = []
    try:
        _cconn = sqlite3.connect(ANALYTICS_DB, timeout=30)
        _crawl_rows = _cconn.execute("""
            SELECT DATE(ts) as dt,
                SUM(CASE WHEN is_ai_bot=1 AND status=200 AND user_agent NOT LIKE '%GPTBot%' AND path NOT LIKE '/v1/preflight%' THEN 1 ELSE 0 END) as ai_cite,
                SUM(CASE WHEN is_ai_bot=1 AND status=200 AND user_agent LIKE '%GPTBot%' AND path NOT LIKE '/v1/preflight%' THEN 1 ELSE 0 END) as ai_index,
                SUM(CASE WHEN is_ai_bot=0 AND bot_name IN ('Google','Bing','Yandex','Apple','DuckDuck') AND status=200 THEN 1 ELSE 0 END) as search,
                SUM(CASE WHEN bot_name = 'Meta' AND status=200 THEN 1 ELSE 0 END) as meta,
                SUM(CASE WHEN bot_name = 'Amazon' AND status=200 THEN 1 ELSE 0 END) as amazon,
                SUM(CASE WHEN is_bot=1 AND status=200 THEN 1 ELSE 0 END) as total
            FROM requests
            GROUP BY dt ORDER BY dt
        """).fetchall()
        data["daily_crawls"] = [{"dt": r[0], "ai_cite": r[1], "ai_index": r[2], "search": r[3], "meta": r[4], "amazon": r[5], "total": r[6]} for r in _crawl_rows]
        _cconn.close()
    except Exception as _ce:
        logger.warning(f"Daily crawl query failed: {_ce}")

    # Language rollout data
    data["lang_rollout"] = []
    try:
        _lconn = sqlite3.connect(ANALYTICS_DB, timeout=30)
        _lang_rows = _lconn.execute(f"""
            SELECT
                CASE
                    WHEN path LIKE '/es/%' THEN 'es' WHEN path LIKE '/de/%' THEN 'de'
                    WHEN path LIKE '/fr/%' THEN 'fr' WHEN path LIKE '/ja/%' THEN 'ja'
                    WHEN path LIKE '/pt/%' THEN 'pt' WHEN path LIKE '/sv/%' THEN 'sv'
                    WHEN path LIKE '/zh/%' THEN 'zh' WHEN path LIKE '/ko/%' THEN 'ko'
                    WHEN path LIKE '/it/%' THEN 'it' WHEN path LIKE '/ar/%' THEN 'ar'
                    WHEN path LIKE '/tr/%' THEN 'tr' WHEN path LIKE '/nl/%' THEN 'nl'
                    WHEN path LIKE '/pl/%' THEN 'pl' WHEN path LIKE '/hi/%' THEN 'hi'
                    WHEN path LIKE '/vi/%' THEN 'vi' WHEN path LIKE '/id/%' THEN 'id'
                    WHEN path LIKE '/th/%' THEN 'th' WHEN path LIKE '/ru/%' THEN 'ru'
                    WHEN path LIKE '/cs/%' THEN 'cs' WHEN path LIKE '/da/%' THEN 'da'
                    WHEN path LIKE '/ro/%' THEN 'ro'
                    ELSE 'en'
                END as lang,
                COUNT(*) as total,
                SUM(CASE WHEN is_ai_bot = 1 AND status = 200 AND user_agent NOT LIKE '%GPTBot%' AND path NOT LIKE '/v1/preflight%' THEN 1 ELSE 0 END) as ai_citations,
                SUM(CASE WHEN is_ai_bot = 1 AND status = 200 THEN 1 ELSE 0 END) as ai_crawls,
                SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) as human
            FROM requests WHERE ts>{since}
            GROUP BY lang ORDER BY ai_crawls DESC
        """).fetchall()
        data["lang_rollout"] = [{"lang": r[0], "total": r[1], "citations": r[2], "crawls": r[3], "human": r[4]} for r in _lang_rows]
        _lconn.close()
    except Exception as _lr_err:
        import logging as _lr_log
        _lr_log.getLogger("flywheel").error(f"lang_rollout query failed: {_lr_err}")

    # Applebot totals (M4b Step 6): Apple is classified as search bot
    # (is_ai_bot=0, bot_name='Apple') so it's not in the trend tuple.
    # Separate queries for current and previous period.
    try:
        _apple_conn = sqlite3.connect(ANALYTICS_DB, timeout=30, check_same_thread=False)
        _r_ac = _apple_conn.execute(
            f"SELECT COUNT(*) FROM requests WHERE ts>{since} AND bot_name='Apple'"
        ).fetchone()
        data["apple_t"] = _r_ac[0] if _r_ac else 0
        _r_ap = _apple_conn.execute(
            f"SELECT COUNT(*) FROM requests WHERE ts>{prev_s} AND ts<{prev_e} AND bot_name='Apple'"
        ).fetchone()
        data["apple_prev_t"] = _r_ap[0] if _r_ap else 0
        _apple_conn.close()
    except Exception as _ap_err:
        import logging as _ap_log
        _ap_log.getLogger("flywheel").error(f"applebot query failed: {_ap_err}")
        data["apple_t"] = 0
        data["apple_prev_t"] = 0

    return data


def _render(period_key, data):
    p = PERIODS[period_key]
    label = p["label"]

    # Period buttons
    btns = "".join(
        f'<a href="/flywheel?period={k}" style="padding:6px 14px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;text-decoration:none;'
        f'{"background:#0f172a;color:#fff;font-weight:600" if k==period_key else "background:#f8fafc;color:#64748b"}">{v["label"]}</a>'
        for k, v in PERIODS.items()
    )

    # Total entities
    total_sr = sum(e["total"] for e in data["pipeline"])
    total_enriched = sum(e["enriched"] for e in data["pipeline"])
    total_entities = total_sr + data["agents_count"]

    # ── Cards ──
    usage_d = _delta(data["ai_usage_total"], data["ai_usage_prev"])
    ai_d = _delta(data["ai_total"], data["ai_prev"])
    pf_d = _delta(data["pf_total"], data["pf_prev"])
    crawl_d = _delta(data["crawl_total"], data["crawl_prev"])
    enr_pct = f"{100*total_enriched/max(total_sr,1):.1f}%"
    ai_break = "".join(f'<div style="font-size:12px;color:#64748b">{_esc(b)}: {_fmt(c)}</div>' for b, c in data["ai_bots"][:4])
    pf_break = "".join(f'<div style="font-size:12px;color:#64748b">{_esc(b)}: {_fmt(c)}</div>' for b, c in data["pf_bots"][:3])

    def _card(title, value, delta, sub1="", sub2="", primary=False):
        border = "border:2px solid #2563eb" if primary else "border:1px solid #e2e8f0"
        bg = "background:#eff6ff" if primary else ""
        size = "32px" if primary else "28px"
        return f'''<div style="{border};border-radius:10px;padding:18px;{bg}">
<div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">{title}</div>
<div style="font-size:{size};font-weight:700">{value}</div>
<div style="font-size:13px;color:{'#16a34a' if '+' in delta else '#ef4444'}">{delta} vs prev</div>
{f'<div style="font-size:12px;color:#64748b">{sub1}</div>' if sub1 else ''}
{f'<div style="font-size:12px;color:#64748b">{sub2}</div>' if sub2 else ''}
</div>'''

    idx_d = _delta(data["ai_index_total"], data["ai_index_prev"])

    cards = f"""<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:20px 0">
{_card("Total AI Usage", _fmt(data["ai_usage_total"]), usage_d,
       f"Citations: {_fmt(data['ai_total'])} · Preflight: {_fmt(data['pf_total'])}", primary=True)}
{_card("AI Citations", _fmt(data["ai_total"]), ai_d, ai_break)}
{_card("AI Indexing", _fmt(data["ai_index_total"]), idx_d, "GPTBot (building index)")}
{_card("Preflight API", _fmt(data["pf_total"]), pf_d, pf_break, f"Non-AI preflight: {_fmt(data['pf_nonai_total'])}")}
</div>
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:0 0 20px">
{_card("Total Crawling", _fmt(data["crawl_total"]), crawl_d,
       f"AI Cite: {_fmt(data['crawl_ai_cite'])} · AI Index: {_fmt(data['crawl_ai_index'])} · Search: {_fmt(data['crawl_search'])}",
       f"Meta: {_fmt(data['crawl_meta'])} · Amazon: {_fmt(data['crawl_amazon'])} · Other: {_fmt(data['crawl_other_bots'])}")}
{_card("Answer Depth", enr_pct, f"{_fmt(total_enriched)} enriched",
       f"of {_fmt(total_sr)} entities", f"{data['enrichment_procs']} pipelines")}
{_card("Coverage", _fmt(total_entities), f"{len(data.get('pipeline',[]))} registries · {sum(1 for v,regs in VERTICAL_MAP.items() if any(r['reg'] in regs for r in data.get('pipeline',[]))) } verticals",
       f"{_fmt(data['total'])} requests · {_fmt(data['ips'])} IPs")}
</div>
<div style="display:flex;gap:24px;margin:0 0 16px;font-size:13px;color:#64748b;padding:10px 14px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0">
<span>Total requests: <b style="color:#0f172a">{_fmt(data['total'])}</b></span>
<span>Bots: <b style="color:#0f172a">{_fmt(data['bots'])}</b> ({100*data['bots']//max(data['total'],1)}%)</span>
<span>Humans: <b style="color:#0f172a">{_fmt(data['humans'])}</b> ({100*data['humans']//max(data['total'],1)}%)</span>
<span>Unique IPs: <b style="color:#0f172a">{_fmt(data['ips'])}</b></span>
</div>"""

    # ── Status codes bar ──
    status_bar = '<div style="display:flex;gap:16px;margin:8px 0;font-size:13px">'
    for code, cnt in data["status"][:5]:
        cl = "#16a34a" if code == 200 else "#f59e0b" if code == 429 else "#ef4444" if code >= 500 else "#64748b"
        status_bar += f'<span style="color:{cl}">{code}: {_fmt(cnt)}</span>'
    status_bar += '</div>'

    # ── Master Pipeline Table ──
    pipe_rows = ""
    for e in data["pipeline"]:
        reg = e["reg"]
        univ = UNIVERSE.get(reg, 0)
        in_db = e["total"]
        enriched = e["enriched"]
        indexable = e.get("indexable", 0)
        cap_pct = (100 * in_db / univ) if univ else 0
        enr_pct_val = (100 * enriched / in_db) if in_db else 0
        pats = PATTERNS_PER_TYPE.get(reg, 10)
        pages = indexable * pats * LANGS if indexable > 0 else 0
        bn_label, bn_color = _bottleneck(cap_pct, enr_pct_val, 0.01)  # index% placeholder

        pipe_rows += f"""<tr>
<td style="font-weight:500">{_esc(reg)}</td>
<td style="text-align:right;color:#94a3b8">{_fmt(univ)}</td>
<td style="text-align:right">{_fmt(in_db)}</td>
<td style="text-align:right;color:{_color(cap_pct)}">{cap_pct:.1f}%</td>
<td style="text-align:right">{_fmt(enriched)}</td>
<td style="text-align:right;color:{_color(enr_pct_val)}">{enr_pct_val:.1f}%</td>
<td style="text-align:right;color:#64748b">{_fmt(pages)}</td>
<td style="text-align:right">{e["avg"] or "—"}</td>
<td><span style="padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:{bn_color}20;color:{bn_color}">{bn_label}</span></td>
</tr>"""

    pipeline_table = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 12px">Master Pipeline — Universe to Citation</h2>
<div style="overflow-x:auto"><table><thead><tr>
<th>Category</th><th style="text-align:right">Universe</th><th style="text-align:right">In DB</th>
<th style="text-align:right">Capture%</th><th style="text-align:right">Enriched</th>
<th style="text-align:right">Enrich%</th><th style="text-align:right">Pages*</th>
<th style="text-align:right">Avg Score</th><th>Bottleneck</th>
</tr></thead><tbody>{pipe_rows}</tbody></table></div>
<p style="font-size:11px;color:#94a3b8;margin-top:4px">* Pages = indexable (score≥30 + desc) × patterns × {LANGS} languages</p>"""

    # ── Citation Quality ──
    cit_rows = ""
    for pat, info in list(data["patterns"].items())[:12]:
        cit_rows += f'<tr><td style="font-family:ui-monospace,monospace;font-size:12px">{_esc(pat)}</td>'
        cit_rows += f'<td style="text-align:right">{_fmt(info.get("Claude",0))}</td>'
        cit_rows += f'<td style="text-align:right">{_fmt(info.get("ChatGPT",0))}</td>'
        cit_rows += f'<td style="text-align:right">{_fmt(info.get("Perplexity",0))}</td>'
        cit_rows += f'<td style="text-align:right;font-weight:600">{_fmt(info["total"])}</td></tr>'

    citation_table = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 12px">Citation Quality — by Endpoint</h2>
<table><thead><tr><th>Endpoint</th><th style="text-align:right">Claude</th><th style="text-align:right">ChatGPT</th>
<th style="text-align:right">Perplexity</th><th style="text-align:right">Total</th></tr></thead><tbody>{cit_rows}</tbody></table>"""

    # ── Crawl Efficiency ──
    eff_rows = ""
    for e in data["efficiency"][:8]:
        total = e["total"]; ok = e["ok"]
        eff = 100 * ok / max(total, 1)
        ec = "#16a34a" if eff > 90 else "#f59e0b" if eff > 70 else "#ef4444"
        eff_rows += f'<tr><td>{_esc(e["bot_name"])}</td><td style="text-align:right">{_fmt(total)}</td>'
        eff_rows += f'<td style="text-align:right">{_fmt(ok)}</td><td style="text-align:right">{_fmt(e["nf"])}</td>'
        eff_rows += f'<td style="text-align:right">{_fmt(e["rl"])}</td>'
        eff_rows += f'<td style="text-align:right;font-weight:600;color:{ec}">{eff:.1f}%</td></tr>'

    efficiency_table = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 12px">Crawl Budget Efficiency</h2>
<table><thead><tr><th>Bot</th><th style="text-align:right">Total</th><th style="text-align:right">200</th>
<th style="text-align:right">404</th><th style="text-align:right">429</th><th style="text-align:right">Efficiency</th></tr></thead><tbody>{eff_rows}</tbody></table>"""

    # ── Demand 404 ──
    dem_rows = ""
    seen = set()
    for path, bot, cnt in data["demand_404"][:15]:
        if path in seen: continue
        seen.add(path)
        dem_rows += f'<tr><td style="font-family:ui-monospace,monospace;font-size:12px">{_esc(path[:60])}</td><td>{_esc(bot)}</td><td style="text-align:right">{cnt}</td></tr>'
    demand_table = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 12px">Demand Without Supply (AI 404s)</h2>
<table><thead><tr><th>Path</th><th>Bot</th><th style="text-align:right">Requests</th></tr></thead>
<tbody>{dem_rows or '<tr><td colspan="3" style="color:#94a3b8">None</td></tr>'}</tbody></table>"""

    # ── Chart.js trend ──
    # tuple: (label, claude, chatgpt, perplexity, bytedance, citations, preflight)
    labels = [t[0] for t in data["trend"]]
    claude_d = [t[1] for t in data["trend"]]
    chatgpt_d = [t[2] for t in data["trend"]]
    perplexity_d = [t[3] for t in data["trend"]]
    bytedance_d = [t[4] for t in data["trend"]]
    citations_d = [t[5] for t in data["trend"]]
    preflight_d = [t[6] for t in data["trend"]]
    total_usage_d = [c + p for c, p in zip(citations_d, preflight_d)]

    # Previous period: align by position
    _prev_list = data.get("prev_trend_list", [])
    _zero = (0, 0, 0, 0, 0, 0)
    _prev_padded = (_prev_list + [_zero] * len(labels))[:len(labels)]
    prev_usage_d = [p[4] + p[5] for p in _prev_padded]  # citations + preflight
    prev_claude_t = sum(p[0] for p in _prev_list)
    prev_chatgpt_t = sum(p[1] for p in _prev_list)
    prev_perplexity_t = sum(p[2] for p in _prev_list)
    prev_bytedance_t = sum(p[3] for p in _prev_list)
    prev_preflight_t = sum(p[5] for p in _prev_list)

    # Add preflight from separate table to match box totals
    _pf_cur = data.get("pf_total", 0)
    _pf_prev = data.get("pf_prev", 0)
    _cur_total = sum(total_usage_d) + _pf_cur
    _prev_total = sum(prev_usage_d) + _pf_prev
    _change_pct = round(100 * (_cur_total - _prev_total) / max(_prev_total, 1)) if _prev_total else 0
    _change_cls = "color:#16a34a" if _change_pct > 0 else "color:#dc2626" if _change_pct < 0 else "color:#64748b"
    _change_sign = "+" if _change_pct > 0 else ""

    _claude_t = sum(claude_d)
    _chatgpt_t = sum(chatgpt_d)
    _perplexity_t = sum(perplexity_d)
    _bytedance_t = sum(bytedance_d)
    _preflight_t = _pf_cur
    _apple_t = data.get("apple_t", 0)
    prev_apple_t = data.get("apple_prev_t", 0)

    def _bot_delta(cur, prev):
        if not prev: return '<span style="color:#16a34a">new</span>' if cur else ""
        d = round(100 * (cur - prev) / prev)
        c = "#16a34a" if d > 0 else "#dc2626" if d < 0 else "#64748b"
        s = "+" if d > 0 else ""
        return f'<span style="color:{c};font-weight:500">{s}{d}%</span>'

    chart_html = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 8px">AI Usage Trend</h2>
<div style="display:flex;gap:16px;align-items:center;margin-bottom:10px;font-size:13px">
<span style="color:#2563eb;font-weight:600"><span style="display:inline-block;width:16px;height:2px;background:#2563eb;vertical-align:middle;margin-right:5px"></span>Last 24h: {_fmt(_cur_total)}</span>
<span style="color:#94a3b8"><span style="display:inline-block;width:16px;border-top:2px dashed #b4b2a9;vertical-align:middle;margin-right:5px"></span>Previous 24h: {_fmt(_prev_total)}</span>
<span style="font-weight:600;{_change_cls}">{_change_sign}{_change_pct}%</span>
</div>
<canvas id="trendChart" height="200"></canvas>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{
    labels: {labels},
    datasets: [
      {{label:'Last 24h', data:{total_usage_d}, borderColor:'#2563eb', borderWidth:2, fill:false, tension:0.3, pointRadius:2, pointBackgroundColor:'#2563eb'}},
      {{label:'Previous 24h', data:{prev_usage_d}, borderColor:'rgba(148,163,184,0.5)', borderWidth:1, borderDash:[5,3], fill:false, tension:0.3, pointRadius:0}}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{legend: {{display:false}}}},
    scales: {{y: {{beginAtZero:true, grid:{{color:'#f1f5f9'}}, ticks:{{font:{{size:11}}}}}}, x: {{grid:{{display:false}}, ticks:{{font:{{size:11}}}}}}}}
  }}
}});
</script>
<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;padding:10px 14px;background:#f8fafc;border-radius:8px;font-size:13px;color:#374151">
<span>ChatGPT: <b>{_fmt(_chatgpt_t)}</b> {_bot_delta(_chatgpt_t, prev_chatgpt_t)}</span>
<span style="color:#e2e8f0">&middot;</span>
<span>Claude: <b>{_fmt(_claude_t)}</b> {_bot_delta(_claude_t, prev_claude_t)}</span>
<span style="color:#e2e8f0">&middot;</span>
<span>ByteDance: <b>{_fmt(_bytedance_t)}</b> {_bot_delta(_bytedance_t, prev_bytedance_t)}</span>
<span style="color:#e2e8f0">&middot;</span>
<span>Perplexity: <b>{_fmt(_perplexity_t)}</b> {_bot_delta(_perplexity_t, prev_perplexity_t)}</span>
<span style="color:#e2e8f0">&middot;</span>
<span>Apple: <b>{_fmt(_apple_t)}</b> {_bot_delta(_apple_t, prev_apple_t)}</span>
</div>"""

    # ── Conversion Funnel ──
    _f = data.get("funnel", {})
    _f_potential = _f.get("potential_pages", 0)
    _f_live = _f.get("live_pages", 0)
    _f_sub = _f.get("submitted", 0)
    _f_crawled = _f.get("crawled_alltime", 0)
    _f_cited = _f.get("cited_pages", 0)
    _f_cited_total = _f.get("cited_total", 0)

    def _funnel_bar(label, value, pct_of_prev, max_log_val, color, detail=""):
        import math
        w = min(100, max(8, int(math.log10(value + 1) / math.log10(max_log_val + 1) * 100))) if value > 0 else 2
        pct_txt = f"{pct_of_prev:.1f}%" if pct_of_prev is not None else ""
        return f'''<div style="margin:10px 0">
<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:3px">
<span style="font-size:13px;font-weight:600;color:#374151">{label}</span>
<span style="font-size:13px;color:#64748b">{_fmt(value)}{f" ({pct_txt} conv.)" if pct_txt else ""}</span>
</div>
<div style="background:#f1f5f9;border-radius:4px;height:28px;position:relative">
<div style="width:{w}%;background:{color};height:100%;border-radius:4px;display:flex;align-items:center;padding:0 8px">
<span style="font-size:11px;color:#fff;font-weight:600;white-space:nowrap">{_fmt(value)}</span>
</div>
</div>
{f'<div style="font-size:11px;color:#94a3b8;margin-top:2px">{detail}</div>' if detail else ''}
</div>'''

    _max_log = _f_potential or _f_live or 1
    _live_pct = 100 * _f_live / max(_f_potential, 1)
    _sub_pct = 100 * _f_sub / max(_f_live, 1)
    _crawl_pct = 100 * _f_crawled / max(_f_sub, 1) if _f_sub > 0 else 100 * _f_crawled / max(_f_live, 1)
    _cite_pct = 100 * _f_cited / max(_f_crawled, 1)
    _yield_pct = 100 * _f_cited_total / max(_f_crawled, 1) if _f_crawled else 0

    # Biggest gap
    _gaps = [
        ("Potential → Live", _f_potential - _f_live, _live_pct),
        ("Live → Submitted", _f_live - _f_sub, _sub_pct),
        ("Submitted → Crawled", max(0, _f_sub - _f_crawled), _crawl_pct),
        ("Crawled → Cited", _f_crawled - _f_cited, _cite_pct),
    ]
    _biggest_gap = max(_gaps, key=lambda x: x[1])

    # Per-segment yield table
    _seg_rows_html = ""
    for s in _f.get("segments", [])[:10]:
        _yield = f"{100*s['ai']/max(s['hits'],1):.1f}%" if s['hits'] else "0%"
        _seg_rows_html += f'<tr><td>{_esc(s["seg"])}</td><td style="text-align:right">{_fmt(s["pages"])}</td><td style="text-align:right">{_fmt(s["hits"])}</td><td style="text-align:right">{_fmt(s["ai"])}</td><td style="text-align:right">{_yield}</td></tr>'

    # Per-language yield table
    _lang_yield_html = ""
    for ly in _f.get("lang_yield", [])[:8]:
        _ly_yield = f"{100*ly['ai']/max(ly['crawled'],1):.1f}%" if ly['crawled'] else "0%"
        _lang_yield_html += f'<tr><td>{_esc(ly["lang"])}</td><td style="text-align:right">{_fmt(ly["crawled"])}</td><td style="text-align:right">{_fmt(ly["ai"])}</td><td style="text-align:right">{_ly_yield}</td></tr>'

        _f_indexable = _f.get("indexable", 0)
    _f_core_en = _f.get("core_en", 0)
    _f_lang_urls = _f.get("lang_urls", 0)
    funnel_section = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 8px">Conversion Funnel</h2>
<p style="font-size:12px;color:#64748b;margin-bottom:12px">Log-scale bars. {_fmt(_f_indexable)} indexable of {_fmt(_f.get('entities', 0))} total entities across {len(data.get('pipeline',[]))} registries.</p>
{_funnel_bar("Potential Pages", _f_potential, None, _max_log, "#94a3b8", f"{_fmt(_f_indexable)} indexable entities × patterns × {LANGS} languages")}
{_funnel_bar("Live (in sitemaps)", _f_live, _live_pct, _max_log, "#3b82f6", f"EN: {_fmt(_f_core_en)} core + Lang: {_fmt(_f_lang_urls)} ({LANGS-1} langs × 2 patterns/entity)")}
{_funnel_bar("Submitted (IndexNow)", _f_sub, _sub_pct, _max_log, "#6366f1", f"Accepted by IndexNow — {_pct(_f_sub, _f_live)} of live pages")}
{_funnel_bar("Crawled (unique pages, all-time)", _f_crawled, _crawl_pct, _max_log, "#8b5cf6", f"{_fmt(_f.get('crawled_period',0))} new in current period")}
{_funnel_bar(f"Cited by AI ({label})", _f_cited, _cite_pct, _max_log, "#16a34a", f"{_fmt(_f_cited_total)} total AI hits · {_yield_pct:.1f}% yield")}
<div style="background:#fef9c3;border-left:4px solid #f59e0b;padding:10px 14px;border-radius:4px;margin:12px 0;font-size:13px;color:#854d0e">
<b>Biggest gap:</b> {_biggest_gap[0]} — {_fmt(int(_biggest_gap[1]))} pages not yet converted ({_biggest_gap[2]:.1f}% conversion rate)
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">
<div>
<h3 style="font-size:14px;font-weight:600;margin:0 0 6px">Per-Segment Yield</h3>
<table><thead><tr><th>Segment</th><th style="text-align:right">Pages</th><th style="text-align:right">Hits</th><th style="text-align:right">AI</th><th style="text-align:right">Yield</th></tr></thead>
<tbody>{_seg_rows_html}</tbody></table>
</div>
<div>
<h3 style="font-size:14px;font-weight:600;margin:0 0 6px">Per-Language Yield</h3>
<table><thead><tr><th>Lang</th><th style="text-align:right">Crawled</th><th style="text-align:right">AI</th><th style="text-align:right">Yield</th></tr></thead>
<tbody>{_lang_yield_html}</tbody></table>
</div>
</div>"""

    # ── Enrichment Pipeline Status ──
    enr_rows = ""
    for e in data["pipeline"]:
        total = e["total"]; enriched = e["enriched"]
        pct = f"{100*enriched/max(total,1):.1f}%"
        if enriched >= total * 0.99 and total > 0:
            status = '<span style="color:#16a34a">✓ Complete</span>'
        elif enriched > 0:
            status = '<span style="color:#3b82f6">▶ In progress</span>'
        else:
            status = '<span style="color:#94a3b8">⏸ Queued</span>'
        enr_rows += f'<tr><td>{_esc(e["reg"])}</td><td style="text-align:right">{_fmt(total)}</td><td style="text-align:right">{_fmt(enriched)}</td><td style="text-align:right">{pct}</td><td>{status}</td></tr>'

    enrichment_section = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 12px">Enrichment Pipeline Status</h2>
<table><thead><tr><th>Registry</th><th style="text-align:right">Total</th><th style="text-align:right">Enriched</th>
<th style="text-align:right">%</th><th>Status</th></tr></thead><tbody>{enr_rows}</tbody></table>
<p style="font-size:12px;color:#64748b;margin-top:8px">{data["enrichment_procs"]} enrichment processes running. Master watchdog active.</p>"""

    # ── Infrastructure section ──
    _load = data.get("load_avg", 0)
    _disk = data.get("disk_pct", 0)
    _pg = data.get("pg_connections", 0)
    _reqs = data.get("requests_total", 0)
    _headroom = round(5_000_000 / max(_reqs, 1), 1) if _reqs else 99

    def _infra_bar(val, warn, danger, unit="", invert=False):
        if invert:
            c = "#dc2626" if val > danger else "#f59e0b" if val > warn else "#16a34a"
        else:
            c = "#16a34a" if val <= warn else "#f59e0b" if val <= danger else "#dc2626"
        pct = min(100, int(val * 100 / max(danger * 1.2, 1)))
        return f'<div style="display:flex;align-items:center;gap:8px"><div style="flex:1;background:#f1f5f9;border-radius:4px;height:8px"><div style="width:{pct}%;background:{c};height:8px;border-radius:4px"></div></div><span style="font-size:13px;font-weight:600;color:{c};min-width:60px;text-align:right">{val}{unit}</span></div>'

    # ── Growth Engine (Indexation → Citations) ──
    _kpi = data.get("idx_kpi", [])
    # ── Kings section ──
    kings_section = ""
    _kd = data.get("kings", [])
    _kt = data.get("kings_total", 0)
    _ke = data.get("kings_enriched", 0)
    _ki = data.get("kings_indexable", 0)
    if _kt > 0:
        _king_rows = ""
        for k in _kd:
            _king_rows += f'<tr><td>{_esc(k["reg"])}</td><td style="text-align:right">{k["kings"]}</td><td style="text-align:right">{k["kings_enriched"]}</td><td style="text-align:right">{k["kings_indexable"]}</td></tr>'

        _king_pages = _ki * 80
        _total_indexable = sum(e["enriched"] for e in data.get("pipeline", []))
        _std_pages = max((_total_indexable - _ki) * 80, 1)

        kings_section = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 12px">Kings (High-Yield Entities)</h2>
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px;flex:1;min-width:120px">
<div style="font-size:11px;color:#64748b">Total Kings</div>
<div style="font-size:22px;font-weight:700">{_fmt(_kt)}</div>
</div>
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px;flex:1;min-width:120px">
<div style="font-size:11px;color:#64748b">Kings Enriched</div>
<div style="font-size:22px;font-weight:700">{_fmt(_ke)}</div>
</div>
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px;flex:1;min-width:120px">
<div style="font-size:11px;color:#64748b">King Pages</div>
<div style="font-size:22px;font-weight:700">{_fmt(_king_pages)}</div>
</div>
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px;flex:1;min-width:120px">
<div style="font-size:11px;color:#64748b">Kings % of Indexable</div>
<div style="font-size:22px;font-weight:700">{round(100 * _ki / max(_total_indexable, 1), 1)}%</div>
</div>
</div>
<table><thead><tr><th>Registry</th><th style="text-align:right">Kings</th><th style="text-align:right">Enriched</th><th style="text-align:right">Indexable</th></tr></thead>
<tbody>{_king_rows}</tbody></table>
<p style="font-size:12px;color:#64748b;margin-top:8px">Kings = high-yield entities enriched with priority. Yield measurement available after 3-5 days of AI re-crawling.</p>"""

    growth_section = ""
    if _kpi and len(_kpi) >= 2:
        _latest = _kpi[-1]
        _enriched = int(_latest.get("enriched", 0))
        _pages = int(_latest.get("indexable_pages", 0))
        _cit = int(_latest.get("ai_citations_24h", 0))
        _cpk = float(_latest.get("citations_per_1k_pages", 0))
        _new = int(_latest.get("new_enriched_24h", 0))

        # Trend data for dual-axis chart
        _kpi_dates = [r.get("date", "")[-5:] for r in _kpi[-14:]]  # Last 14 days
        _kpi_pages = [round(int(r.get("indexable_pages", 0)) / 1_000_000, 1) for r in _kpi[-14:]]
        _kpi_cit = [int(r.get("ai_citations_24h", 0)) for r in _kpi[-14:]]
        _kpi_cpk = [float(r.get("citations_per_1k_pages", 0)) for r in _kpi[-14:]]

        # CPK trend direction
        if len(_kpi_cpk) >= 3:
            _cpk_recent = sum(_kpi_cpk[-3:]) / 3
            _cpk_older = sum(_kpi_cpk[-6:-3]) / 3 if len(_kpi_cpk) >= 6 else _cpk_recent
            _cpk_trend = "rising" if _cpk_recent > _cpk_older * 1.1 else "falling" if _cpk_recent < _cpk_older * 0.9 else "stable"
            _cpk_color = "#16a34a" if _cpk_trend == "rising" else "#dc2626" if _cpk_trend == "falling" else "#64748b"
        else:
            _cpk_trend = "new"
            _cpk_color = "#64748b"

        growth_section = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 12px">Growth Engine</h2>
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px;flex:1;min-width:140px">
<div style="font-size:11px;color:#64748b">Enriched</div>
<div style="font-size:22px;font-weight:700">{_fmt(_enriched)}</div>
<div style="font-size:11px;color:#64748b">+{_fmt(_new)} today</div>
</div>
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px;flex:1;min-width:140px">
<div style="font-size:11px;color:#64748b">Indexable Pages</div>
<div style="font-size:22px;font-weight:700">{_fmt(_pages)}</div>
</div>
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px;flex:1;min-width:140px">
<div style="font-size:11px;color:#64748b">Citations/day</div>
<div style="font-size:22px;font-weight:700">{_fmt(_cit)}</div>
</div>
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px;flex:1;min-width:140px">
<div style="font-size:11px;color:#64748b">Yield (per 1K pages)</div>
<div style="font-size:22px;font-weight:700;color:{_cpk_color}">{_cpk:.2f}</div>
<div style="font-size:11px;color:{_cpk_color}">{_cpk_trend}</div>
</div>
</div>
<div style="font-size:12px;color:#64748b;margin-bottom:8px">Enriched → Indexable Pages → AI Citations. Yield = citations per 1K indexable pages per day.</div>
<canvas id="growthChart" height="180"></canvas>
<script>
new Chart(document.getElementById('growthChart'), {{
  type: 'line',
  data: {{
    labels: {_kpi_dates},
    datasets: [
      {{label:'Indexable Pages (M)', data:{_kpi_pages}, borderColor:'#2563eb', borderWidth:2, fill:false, tension:0.3, pointRadius:2, yAxisID:'y'}},
      {{label:'AI Citations/day', data:{_kpi_cit}, borderColor:'#16a34a', borderWidth:2, fill:false, tension:0.3, pointRadius:2, yAxisID:'y1'}}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{legend: {{position:'top', labels: {{font: {{size:11}}}}}}}},
    scales: {{
      y: {{type:'linear', position:'left', beginAtZero:true, title: {{display:true, text:'Pages (M)'}}, grid:{{color:'#f1f5f9'}}}},
      y1: {{type:'linear', position:'right', beginAtZero:true, title: {{display:true, text:'Citations/day'}}, grid:{{drawOnChartArea:false}}}},
      x: {{grid:{{display:false}}}}
    }}
  }}
}});
</script>"""

    # ── Crawl Trend chart (companion to Growth Engine) ──
    _dc = data.get("daily_crawls", [])
    crawl_trend_section = ""
    if _dc and len(_dc) >= 3:
        # Last 21 days
        _dc_recent = _dc[-21:]
        _dc_labels = [r["dt"][-5:] for r in _dc_recent]  # MM-DD
        _dc_ai_cite = [r.get("ai_cite", r.get("ai", 0)) for r in _dc_recent]
        _dc_ai_index = [r.get("ai_index", 0) for r in _dc_recent]
        _dc_search = [r["search"] for r in _dc_recent]
        _dc_meta = [r.get("meta", r.get("other", r.get("social", 0))) for r in _dc_recent]
        _dc_amazon = [r.get("amazon", 0) for r in _dc_recent]
        _dc_total = [r["total"] for r in _dc_recent]
        _dc_ai_cite_sum = sum(_dc_ai_cite[-7:])
        _dc_ai_index_sum = sum(_dc_ai_index[-7:])
        _dc_search_sum = sum(_dc_search[-7:])
        _dc_meta_sum = sum(_dc_meta[-7:])
        _dc_amazon_sum = sum(_dc_amazon[-7:])
        _dc_total_sum = sum(_dc_total[-7:])
        crawl_trend_section = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 8px">Crawl Trend — Daily Bot Requests (200 OK)</h2>
<div style="display:flex;gap:16px;margin-bottom:8px;font-size:12px;color:#64748b;flex-wrap:wrap">
<span><span style="display:inline-block;width:12px;height:3px;background:#8b5cf6;vertical-align:middle;margin-right:4px"></span>AI Citations: <b>{_fmt(_dc_ai_cite_sum)}</b>/7d</span>
<span><span style="display:inline-block;width:12px;height:3px;background:#10a37f;vertical-align:middle;margin-right:4px"></span>AI Indexing: <b>{_fmt(_dc_ai_index_sum)}</b>/7d</span>
<span><span style="display:inline-block;width:12px;height:3px;background:#f59e0b;vertical-align:middle;margin-right:4px"></span>Search: <b>{_fmt(_dc_search_sum)}</b>/7d</span>
<span><span style="display:inline-block;width:12px;height:3px;background:#1877f2;vertical-align:middle;margin-right:4px"></span>Meta: <b>{_fmt(_dc_meta_sum)}</b>/7d</span>
<span><span style="display:inline-block;width:12px;height:3px;background:#ff9900;vertical-align:middle;margin-right:4px"></span>Amazon: <b>{_fmt(_dc_amazon_sum)}</b>/7d</span>
<span><span style="display:inline-block;width:12px;height:3px;background:#94a3b8;vertical-align:middle;margin-right:4px"></span>All bots: <b>{_fmt(_dc_total_sum)}</b>/7d</span>
</div>
<canvas id="crawlChart" height="160"></canvas>
<script>
new Chart(document.getElementById('crawlChart'), {{
  type: 'line',
  data: {{
    labels: {_dc_labels},
    datasets: [
      {{label:'All Bots', data:{_dc_total}, borderColor:'rgba(148,163,184,0.5)', borderWidth:1.5, fill:true, backgroundColor:'rgba(148,163,184,0.06)', tension:0.3, pointRadius:0, yAxisID:'y'}},
      {{label:'Meta', data:{_dc_meta}, borderColor:'#1877f2', borderWidth:2, fill:false, tension:0.3, pointRadius:2, yAxisID:'y'}},
      {{label:'Amazon', data:{_dc_amazon}, borderColor:'#ff9900', borderWidth:1.5, borderDash:[4,3], fill:false, tension:0.3, pointRadius:1, yAxisID:'y'}},
      {{label:'Search Engines', data:{_dc_search}, borderColor:'#f59e0b', borderWidth:2, fill:false, tension:0.3, pointRadius:2, yAxisID:'y'}},
      {{label:'AI Indexing (GPTBot)', data:{_dc_ai_index}, borderColor:'#10a37f', borderWidth:1.5, borderDash:[4,3], fill:false, tension:0.3, pointRadius:1, yAxisID:'y'}},
      {{label:'AI Citations', data:{_dc_ai_cite}, borderColor:'#8b5cf6', borderWidth:2, fill:false, tension:0.3, pointRadius:2, yAxisID:'y'}}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{legend: {{position:'top', labels: {{font: {{size:11}}}}}}}},
    scales: {{
      y: {{type:'linear', position:'left', beginAtZero:true, title: {{display:true, text:'Requests/day'}}, grid:{{color:'#f1f5f9'}}}},
      x: {{grid:{{display:false}}}}
    }}
  }}
}});
</script>"""

    # ── Language Rollout section ──
    # Dynamic: all 22 languages have sitemaps. Estimate URLs from enriched entity count.
    _lang_q = sum(e["enriched"] for e in data.get("pipeline", []))
    _LANG_SITEMAPS = {l: (max(1, _lang_q // 10000), _lang_q) for l in ["en", "es", "de", "fr", "ja", "pt", "id", "cs", "th", "ro", "tr", "hi", "ru", "pl", "it", "ko", "vi", "nl", "sv", "zh", "da", "ar"]}
    _LANG_NAMES = {"en":"English","es":"Spanish","de":"German","fr":"French","ja":"Japanese",
                   "ko":"Korean","zh":"Chinese","ar":"Arabic","pt":"Portuguese","it":"Italian",
                   "sv":"Swedish","nl":"Dutch","pl":"Polish","tr":"Turkish","ru":"Russian",
                   "hi":"Hindi","vi":"Vietnamese","th":"Thai","id":"Indonesian","da":"Danish",
                   "cs":"Czech","ro":"Romanian"}
    _lr = data.get("lang_rollout", [])
    _lr_map = {r["lang"]: r for r in _lr}
    _all_langs = list(dict.fromkeys([r["lang"] for r in _lr] + list(_LANG_NAMES.keys())))
    _lr_rows = ""
    _total_crawls = sum(r.get("crawls", 0) for r in _lr)
    _total_citations = sum(r.get("citations", 0) for r in _lr)
    _live_count = sum(1 for l in _all_langs if _LANG_SITEMAPS.get(l) and _lr_map.get(l, {}).get("crawls", 0) > 100)
    _submitted_urls = sum(u for _, u in _LANG_SITEMAPS.values())
    for lang in _all_langs:
        r = _lr_map.get(lang, {})
        sm = _LANG_SITEMAPS.get(lang)
        crawls = r.get("crawls", 0)
        cit = r.get("citations", 0)
        human = r.get("human", 0)
        sm_count = sm[0] if sm else 0
        sm_urls = sm[1] if sm else 0
        if sm and crawls > 100:
            status = '<span style="color:#16a34a">✓ Live</span>'
        elif sm:
            status = '<span style="color:#2563eb">✓ Submitted</span>'
        elif crawls > 100:
            status = '<span style="color:#d97706">⟳ Crawling</span>'
        else:
            status = '<span style="color:#94a3b8">Planned</span>'
        _lr_rows += f'<tr><td><strong>{lang}</strong> {_LANG_NAMES.get(lang,"")}</td><td style="text-align:right">{sm_count}</td><td style="text-align:right">{_fmt(sm_urls)}</td><td style="text-align:right">{_fmt(crawls)}</td><td style="text-align:right">{_fmt(cit)}</td><td style="text-align:right">{_fmt(human)}</td><td>{status}</td></tr>'

    lang_section = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 12px">Language Rollout — Submitted → Crawled → Cited</h2>
<div style="display:flex;gap:24px;margin:8px 0 14px;font-size:13px;color:#64748b">
<span>Languages Live: <strong style="color:#0f172a">{_live_count}</strong></span>
<span>Submitted URLs: <strong style="color:#0f172a">{_fmt(_submitted_urls)}</strong></span>
<span>AI Crawls (all langs): <strong style="color:#0f172a">{_fmt(_total_crawls)}/day</strong></span>
<span>Citations (all langs): <strong style="color:#0f172a">{_fmt(_total_citations)}/day</strong></span>
</div>
<table style="width:100%;border-collapse:collapse;font-size:13px">
<tr style="border-bottom:2px solid #e2e8f0"><th style="text-align:left;padding:6px 8px;color:#64748b">Language</th><th style="text-align:right;padding:6px 8px;color:#64748b">Sitemaps</th><th style="text-align:right;padding:6px 8px;color:#64748b">URLs</th><th style="text-align:right;padding:6px 8px;color:#64748b">AI Crawls</th><th style="text-align:right;padding:6px 8px;color:#64748b">Citations</th><th style="text-align:right;padding:6px 8px;color:#64748b">Human</th><th style="padding:6px 8px;color:#64748b">Status</th></tr>
{_lr_rows}
</table>"""

    infra_section = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 12px">Infrastructure</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px">
<div style="font-size:12px;color:#64748b;margin-bottom:6px">Requests ({PERIODS[period_key]["label"]})</div>
{_infra_bar(_reqs, 2000000, 5000000)}
<div style="font-size:11px;color:#94a3b8;margin-top:4px">{_headroom}x headroom to 5M limit (CF edge)</div>
</div>
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px">
<div style="font-size:12px;color:#64748b;margin-bottom:6px">System Load</div>
{_infra_bar(_load, 8, 15)}
<div style="font-size:11px;color:#94a3b8;margin-top:4px">8 cores available</div>
</div>
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px">
<div style="font-size:12px;color:#64748b;margin-bottom:6px">PostgreSQL Connections</div>
{_infra_bar(_pg, 60, 80)}
<div style="font-size:11px;color:#94a3b8;margin-top:4px">Max 100 (default)</div>
</div>
<div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px">
<div style="font-size:12px;color:#64748b;margin-bottom:6px">Disk Usage</div>
{_infra_bar(_disk, 70, 85, unit="%")}
</div>
</div>"""

    _cs = data.get("cache_stats")
    if _cs:
        _hr = _cs["hit_rate"]
        _hr_color = "#16a34a" if _hr >= 50 else "#f59e0b" if _hr >= 20 else "#dc2626"
        infra_section += f"""
<div style="margin-top:12px;border:1px solid #e2e8f0;border-radius:8px;padding:14px;display:flex;gap:24px;align-items:center">
<div><span style="font-size:12px;color:#64748b">Page Cache</span><br><span style="font-size:20px;font-weight:700;color:{_hr_color}">{_hr}%</span> <span style="font-size:12px;color:#64748b">hit rate</span></div>
<div style="font-size:12px;color:#64748b">{_fmt(_cs['pages'])} pages &middot; {_cs['memory']} memory &middot; {_fmt(_cs['hits'])} hits / {_fmt(_cs['misses'])} misses</div>
</div>"""

    infra_section += """
<div style="margin-top:12px;padding:12px;background:#f8fafc;border-radius:8px;font-size:12px;color:#64748b">
<b>Scaling triggers:</b>
&gt;500K req/day → page cache (DONE) &middot;
Cloudflare edge cache (DONE) &middot;
&gt;2M req/day → migrate to VPS (€18/mo) &middot;
&gt;5M req/day → dedicated server &middot;
&gt;15M req/day → Cloudflare Workers
</div>"""

    # ── AI Market Share (conditional — only if real data) ──
    ai_share_section = ""
    _share_data = data.get("ai_share")
    if _share_data:
        _share_rows = ""
        for p in _share_data["platforms"]:
            idx = p["index"]
            if idx > 120: _idx_cls = "color:#16a34a"; _idx_label = "strong"
            elif idx >= 80: _idx_cls = "color:#64748b"; _idx_label = "at market"
            elif idx >= 40: _idx_cls = "color:#f59e0b"; _idx_label = "under"
            else: _idx_cls = "color:#dc2626"; _idx_label = "missing"
            _share_rows += f'<tr><td>{_esc(p["platform"])}</td><td style="text-align:right">{p["our"]}%</td><td style="text-align:right">{p["global"]}%</td><td style="text-align:right;{_idx_cls};font-weight:600">{idx}</td><td style="{_idx_cls};font-size:12px">{_idx_label}</td></tr>'
        ai_share_section = f"""<h2 style="font-size:16px;font-weight:600;margin:32px 0 12px">AI Market Share Index</h2>
<table><thead><tr><th>Platform</th><th style="text-align:right">Our Share</th><th style="text-align:right">Global Share</th><th style="text-align:right">Index</th><th>Status</th></tr></thead>
<tbody>{_share_rows}</tbody></table>
<p style="font-size:11px;color:#94a3b8;margin-top:6px">Source: {_esc(_share_data.get('source',''))} · Updated: {_esc(_share_data.get('updated',''))} · Index = (our share / global share) × 100</p>"""

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nerq Flywheel — Machine-First Pipeline Dashboard</title>
<meta name="robots" content="noindex, nofollow">
<link rel="stylesheet" href="/static/nerq.css?v=13">
<style>body{{background:#fff}}table{{font-size:13px}}th{{font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:#64748b}}td{{padding:6px 10px}}</style>
</head><body>
<nav class="nav"><div class="nav-inner">
<a href="/" class="nav-logo">Nerq<span>Flywheel</span></a>
<div class="nav-links"><a href="/">Home</a><a href="/admin/dashboard">Analytics</a><a href="/ab-results">A/B</a><a href="/nerq/docs">API</a></div>
</div></nav>
<main class="container" style="max-width:1100px;padding:20px">
<h1 style="font-size:20px;font-weight:700;margin-bottom:4px">Machine-First Flywheel Dashboard</h1>
<p style="font-size:13px;color:#64748b;margin-bottom:12px">Full pipeline: Universe → Captured → Enriched → Pages → Indexed → Cited. Period: <b>{label}</b></p>
<div style="display:flex;gap:8px;margin-bottom:16px">{btns}</div>
{status_bar}
{cards}
{chart_html}
{funnel_section}
{pipeline_table}
{citation_table}
{efficiency_table}
{demand_table}
{enrichment_section}
{kings_section}
{growth_section}
{crawl_trend_section}
{lang_section}
{infra_section}
{ai_share_section}
<p style="font-size:11px;color:#94a3b8;margin-top:32px">Cached {CACHE_TTLS.get(period_key,300)//60}min. Updated: {datetime.now().strftime('%H:%M')}.</p>
</main></body></html>"""


def _loading_page(period):
    """Lightweight loading page with auto-refresh — returned instantly on cold start."""
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Flywheel — Loading...</title>
<meta http-equiv="refresh" content="5;url=/flywheel?period={_esc(period)}">
<style>
body{{background:#0f172a;color:#e2e8f0;font-family:'JetBrains Mono',monospace;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.box{{text-align:center}}.spinner{{width:40px;height:40px;border:3px solid #334155;border-top-color:#22d3ee;border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 20px}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
</style></head><body><div class="box"><div class="spinner"></div><h2>Generating dashboard...</h2><p style="color:#94a3b8">First load takes ~30s. This page will auto-refresh.</p></div></body></html>"""


def _generate_in_background(period):
    """Generate flywheel data in a background thread and write to file cache."""
    import threading

    def _worker():
        try:
            logger.info(f"Flywheel background generation started for {period}")
            d = _get_data(period)
            html = _render(period, d)
            _write_file_cache(period, html)
            _cache[f"fw:{period}"] = (html, time.time())
            logger.info(f"Flywheel background generation done for {period} ({len(html)} bytes)")
        except Exception as e:
            logger.error(f"Flywheel background generation failed for {period}: {e}", exc_info=True)
        finally:
            _GENERATING.discard(period)

    _GENERATING.add(period)
    t = threading.Thread(target=_worker, daemon=True, name=f"flywheel-{period}")
    t.start()


def mount_flywheel(app):
    @app.get("/flywheel", response_class=HTMLResponse)
    async def flywheel(period: str = "24h"):
        if period not in PERIODS:
            period = "24h"
        ck = f"fw:{period}"
        ttl = CACHE_TTLS.get(period, 1800)
        now = time.time()

        # 1. Check in-memory cache (fastest, same worker)
        if ck in _cache:
            html, ts = _cache[ck]
            if now - ts < ttl:
                return HTMLResponse(html)

        # 2. Check file cache (cross-worker, survives restart)
        file_html, file_mtime = _read_file_cache(period)
        if file_html and (now - file_mtime) < ttl:
            _cache[ck] = (file_html, file_mtime)
            return HTMLResponse(file_html)

        # 3. Cache is stale or missing — serve stale if available, refresh in background
        if file_html:
            # Stale cache exists — serve it immediately, refresh in background
            _cache[ck] = (file_html, file_mtime)
            if period not in _GENERATING:
                _generate_in_background(period)
            return HTMLResponse(file_html)

        # 4. No cache at all (cold start) — return loading page, generate in background
        if period not in _GENERATING:
            _generate_in_background(period)
        return HTMLResponse(_loading_page(period))

    logger.info("Mounted /flywheel v3 dashboard")
