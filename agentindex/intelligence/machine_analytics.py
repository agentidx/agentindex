"""
Machine Analytics
=================
Tracks machine adoption funnel: discovery → first-call → repeat-use → integration.
Analyzes which discovery channels drive the most machine traffic.

Usage:
    python -m agentindex.intelligence.machine_analytics
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [machine-analytics] %(message)s")
logger = logging.getLogger("machine-analytics")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "crypto", "crypto_trust.db")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "machine_analytics_report.json")


def _ensure_tables(conn):
    """Create analytics tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS machine_access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            path TEXT,
            user_agent TEXT,
            referer TEXT,
            ip_hash TEXT,
            is_machine INTEGER DEFAULT 0,
            channel TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS machine_analytics_daily (
            date TEXT,
            channel TEXT,
            total_requests INTEGER DEFAULT 0,
            unique_agents INTEGER DEFAULT 0,
            api_calls INTEGER DEFAULT 0,
            llms_txt_hits INTEGER DEFAULT 0,
            preflight_calls INTEGER DEFAULT 0,
            mcp_calls INTEGER DEFAULT 0,
            PRIMARY KEY (date, channel)
        )
    """)
    conn.commit()


MACHINE_UA_PATTERNS = [
    "chatgpt", "gpt", "openai", "claude", "anthropic", "perplexity",
    "bingbot", "googlebot", "yandexbot", "baiduspider",
    "python-requests", "httpx", "aiohttp", "node-fetch", "axios",
    "curl", "wget", "go-http", "java/", "okhttp",
    "langchain", "crewai", "autogen", "llama", "huggingface",
    "mcp-client", "nerq-cli", "NerqTrustCheck",
]

DISCOVERY_CHANNELS = {
    "llms.txt": ["llms.txt", "llms-full.txt"],
    "mcp": ["/mcp", "mcp-server"],
    "api_docs": ["/docs", "/openapi", "/.well-known"],
    "widget": ["/widget"],
    "preflight": ["/v1/preflight", "/v1/trust"],
    "feed": ["/feed/", ".xml", "atom"],
    "badge": ["/badge/", "/api/v1/badge"],
    "search": ["/v1/search", "/v1/agents"],
    "blog": ["/blog/"],
    "honeypot": ["/agents", "/health", "/manifest.json", "/humans.txt", "/security.txt"],
}


def classify_channel(path: str) -> str:
    """Classify a request path into a discovery channel."""
    path_lower = path.lower()
    for channel, patterns in DISCOVERY_CHANNELS.items():
        for pattern in patterns:
            if pattern in path_lower:
                return channel
    return "other"


def is_machine_request(user_agent: str) -> bool:
    """Determine if a request is from a machine/AI system."""
    if not user_agent:
        return False
    ua_lower = user_agent.lower()
    for pattern in MACHINE_UA_PATTERNS:
        if pattern in ua_lower:
            return True
    return False


def generate_funnel_report(conn) -> dict:
    """Generate machine adoption funnel metrics."""
    now = datetime.utcnow()
    periods = {
        "24h": (now - timedelta(hours=24)).isoformat(),
        "7d": (now - timedelta(days=7)).isoformat(),
        "30d": (now - timedelta(days=30)).isoformat(),
    }

    report = {"generated_at": now.isoformat(), "funnel": {}, "channels": {}, "top_machine_agents": []}

    for period_name, since in periods.items():
        try:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(DISTINCT ip_hash) as unique_visitors,
                    SUM(CASE WHEN is_machine = 1 THEN 1 ELSE 0 END) as machine_requests,
                    SUM(CASE WHEN path LIKE '%/v1/preflight%' THEN 1 ELSE 0 END) as preflight_calls,
                    SUM(CASE WHEN path LIKE '%llms.txt%' THEN 1 ELSE 0 END) as llms_hits
                FROM machine_access_log
                WHERE timestamp >= ?
            """, (since,)).fetchone()

            report["funnel"][period_name] = {
                "total_requests": row[0] or 0,
                "unique_visitors": row[1] or 0,
                "machine_requests": row[2] or 0,
                "preflight_calls": row[3] or 0,
                "llms_txt_hits": row[4] or 0,
                "machine_pct": round((row[2] or 0) / max(row[0] or 1, 1) * 100, 1),
            }
        except Exception as e:
            logger.warning(f"Funnel query failed for {period_name}: {e}")
            report["funnel"][period_name] = {"error": str(e)}

    # Channel effectiveness
    try:
        rows = conn.execute("""
            SELECT channel, COUNT(*) as hits, COUNT(DISTINCT ip_hash) as unique_agents
            FROM machine_access_log
            WHERE is_machine = 1 AND timestamp >= ?
            GROUP BY channel
            ORDER BY hits DESC
        """, (periods["30d"],)).fetchall()
        report["channels"] = {r[0]: {"hits": r[1], "unique_agents": r[2]} for r in rows}
    except Exception as e:
        logger.warning(f"Channel query failed: {e}")

    # Top machine user agents
    try:
        rows = conn.execute("""
            SELECT user_agent, COUNT(*) as hits
            FROM machine_access_log
            WHERE is_machine = 1 AND timestamp >= ?
            GROUP BY user_agent
            ORDER BY hits DESC
            LIMIT 20
        """, (periods["30d"],)).fetchall()
        report["top_machine_agents"] = [{"user_agent": r[0], "hits": r[1]} for r in rows]
    except Exception as e:
        logger.warning(f"Top agents query failed: {e}")

    return report


def run():
    """Generate and save machine analytics report."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    _ensure_tables(conn)

    report = generate_funnel_report(conn)
    conn.close()

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Report saved to {REPORT_PATH}")

    # Print summary
    for period, data in report.get("funnel", {}).items():
        if "error" not in data:
            logger.info(f"  {period}: {data['total_requests']} total, {data['machine_requests']} machine ({data['machine_pct']}%), {data['preflight_calls']} preflight calls")

    return report


def main():
    logger.info("Machine Analytics — starting")
    report = run()
    logger.info(f"Done. Channels tracked: {len(report.get('channels', {}))}")


if __name__ == "__main__":
    main()
