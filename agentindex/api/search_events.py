"""Search event logger — records every /search query so the Smedjan
weekly query-audit can answer "top search queries" and "top zero-result
queries". Writes to a dedicated `search_events` table in the same
`logs/analytics.db` SQLite file used by AnalyticsMiddleware; the table is
exported nightly by `scripts/smedjan-analytics-export.sh` and mirrored
to `analytics_mirror.search_events` on the smedjan Postgres.

Source: AUDIT-QUERY-20260418 finding #8 / FU-QUERY-20260418-08.
"""
from __future__ import annotations

import os
import sqlite3
import logging
from datetime import datetime

log = logging.getLogger("agentindex.search_events")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "analytics.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS search_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    q            TEXT NOT NULL,
    q_normalized TEXT,
    result_count INTEGER NOT NULL DEFAULT 0,
    duration_ms  REAL,
    ip           TEXT,
    user_agent   TEXT,
    referrer     TEXT,
    bot_name     TEXT,
    is_bot       INTEGER NOT NULL DEFAULT 0,
    is_ai_bot    INTEGER NOT NULL DEFAULT 0,
    visitor_type TEXT,
    country      TEXT,
    source       TEXT
);
CREATE INDEX IF NOT EXISTS idx_se_ts ON search_events(ts);
CREATE INDEX IF NOT EXISTS idx_se_q_norm ON search_events(q_normalized);
CREATE INDEX IF NOT EXISTS idx_se_zero ON search_events(result_count) WHERE result_count=0;
CREATE INDEX IF NOT EXISTS idx_se_visitor_ts ON search_events(visitor_type, ts);
"""

_initialised = False


def _ensure_schema(conn: sqlite3.Connection) -> None:
    global _initialised
    if _initialised:
        return
    conn.executescript(_SCHEMA)
    conn.commit()
    _initialised = True


def _normalize(q: str) -> str:
    return " ".join((q or "").lower().split())[:200]


def log_search_event(
    *,
    q: str,
    result_count: int,
    duration_ms: float | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    referrer: str | None = None,
    country: str | None = None,
    source: str = "/search",
) -> None:
    """Best-effort write of one search event. Never raises."""
    q = (q or "").strip()
    if not q:
        return
    try:
        from agentindex.analytics import _detect_bot, classify_ai_source
    except Exception:
        _detect_bot = None
        classify_ai_source = None

    try:
        if _detect_bot is not None:
            is_bot, is_ai_bot, bot_name, _ = _detect_bot(user_agent or "", ip or "")
        else:
            is_bot, is_ai_bot, bot_name = False, False, None

        visitor_type = None
        if classify_ai_source is not None:
            try:
                ref_domain = ""
                if referrer:
                    from urllib.parse import urlparse
                    ref_domain = urlparse(referrer).netloc.replace("www.", "")
                _ai_source, visitor_type = classify_ai_source(referrer, ref_domain, user_agent)
            except Exception:
                visitor_type = None
        if not visitor_type:
            visitor_type = "bot" if is_bot else "human"

        conn = sqlite3.connect(DB_PATH)
        try:
            _ensure_schema(conn)
            conn.execute(
                """INSERT INTO search_events
                   (ts, q, q_normalized, result_count, duration_ms, ip, user_agent,
                    referrer, bot_name, is_bot, is_ai_bot, visitor_type, country, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    datetime.utcnow().isoformat(),
                    q[:500],
                    _normalize(q),
                    int(result_count or 0),
                    float(duration_ms) if duration_ms is not None else None,
                    ip,
                    (user_agent or "")[:500],
                    (referrer or "")[:500],
                    bot_name,
                    int(bool(is_bot)),
                    int(bool(is_ai_bot)),
                    visitor_type,
                    country,
                    source,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        log.debug("search_events log failed: %s", exc)
