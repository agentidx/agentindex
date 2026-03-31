"""
ZARQ Forta Integration — Sprint 4
Fetches high-severity alerts from Forta Network and cross-references with ZARQ tokens.
Uses circuit breaker for graceful degradation.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone

import httpx

from agentindex.circuit_breaker import is_available, record_success, record_failure

logger = logging.getLogger("zarq.forta")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto", "crypto_trust.db")
FORTA_GRAPHQL = "https://api.forta.network/graphql"
FORTA_TIMEOUT = 15.0
CIRCUIT_NAME = "forta_api"

# Map of common contract/protocol names to ZARQ token IDs
PROTOCOL_TO_TOKEN = {
    "uniswap": "uniswap",
    "aave": "aave",
    "compound": "compound-governance-token",
    "curve": "curve-dao-token",
    "maker": "maker",
    "lido": "lido-dao",
    "sushiswap": "sushi",
    "synthetix": "havven",
    "chainlink": "chainlink",
    "1inch": "1inch",
    "balancer": "balancer",
    "yearn": "yearn-finance",
    "pancakeswap": "pancakeswap-token",
    "convex": "convex-finance",
    "frax": "frax-share",
    "rocket pool": "rocket-pool",
    "ens": "ethereum-name-service",
    "the graph": "the-graph",
    "gmx": "gmx",
    "dydx": "dydx-chain",
}

# GraphQL query for recent high-severity alerts
ALERTS_QUERY = """
query RecentAlerts($input: AlertsInput!) {
    alerts(input: $input) {
        alerts {
            alertId
            severity
            name
            description
            protocol
            source {
                bot { id name }
            }
            metadata
            createdAt
        }
        pageInfo {
            hasNextPage
        }
    }
}
"""


def _init_forta_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS forta_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id TEXT UNIQUE NOT NULL,
        severity TEXT,
        name TEXT,
        description TEXT,
        protocol TEXT,
        bot_id TEXT,
        bot_name TEXT,
        metadata_json TEXT,
        zarq_token_id TEXT,
        created_at TEXT,
        fetched_at TEXT
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_forta_token ON forta_alerts(zarq_token_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_forta_severity ON forta_alerts(severity)")
    conn.commit()
    conn.close()


_init_forta_table()


def _match_to_zarq_token(protocol: str, name: str, description: str) -> str | None:
    """Try to match a Forta alert to a ZARQ-tracked token."""
    text = f"{protocol or ''} {name or ''} {description or ''}".lower()
    for keyword, token_id in PROTOCOL_TO_TOKEN.items():
        if keyword in text:
            return token_id
    return None


def fetch_forta_alerts(severities: list[str] = None, limit: int = 25) -> list[dict]:
    """
    Fetch recent high-severity alerts from Forta's GraphQL API.
    Cross-references with ZARQ-tracked tokens and stores matches.
    Uses circuit breaker for graceful degradation.

    Returns list of alerts with zarq_token_id if matched.
    """
    if severities is None:
        severities = ["CRITICAL", "HIGH"]

    if not is_available(CIRCUIT_NAME):
        logger.warning("Forta circuit breaker is open, skipping fetch")
        return []

    try:
        variables = {
            "input": {
                "severities": severities,
                "first": limit,
            }
        }

        with httpx.Client(timeout=FORTA_TIMEOUT) as client:
            resp = client.post(
                FORTA_GRAPHQL,
                json={"query": ALERTS_QUERY, "variables": variables},
            )
            resp.raise_for_status()

        data = resp.json()
        record_success(CIRCUIT_NAME)

        alerts_data = data.get("data", {}).get("alerts", {}).get("alerts", [])
        if not alerts_data:
            return []

        conn = sqlite3.connect(DB_PATH)
        results = []

        for a in alerts_data:
            alert_id = a.get("alertId", "")
            protocol = a.get("protocol", "")
            name = a.get("name", "")
            description = a.get("description", "")
            severity = a.get("severity", "")
            source = a.get("source", {}) or {}
            bot = source.get("bot", {}) or {}

            zarq_token = _match_to_zarq_token(protocol, name, description)

            alert = {
                "alert_id": alert_id,
                "severity": severity,
                "name": name,
                "description": description[:500],
                "protocol": protocol,
                "bot_id": bot.get("id", ""),
                "bot_name": bot.get("name", ""),
                "zarq_token_id": zarq_token,
                "created_at": a.get("createdAt", ""),
            }
            results.append(alert)

            # Store in SQLite
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO forta_alerts
                    (alert_id, severity, name, description, protocol, bot_id, bot_name,
                     metadata_json, zarq_token_id, created_at, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    alert_id, severity, name, description[:500], protocol,
                    bot.get("id", ""), bot.get("name", ""),
                    json.dumps(a.get("metadata")) if a.get("metadata") else None,
                    zarq_token, a.get("createdAt", ""),
                    datetime.now(timezone.utc).isoformat(),
                ))
            except Exception:
                pass

        conn.commit()
        conn.close()

        matched = [a for a in results if a["zarq_token_id"]]
        logger.info("Forta: fetched %d alerts, %d matched ZARQ tokens", len(results), len(matched))
        return results

    except httpx.HTTPStatusError as e:
        logger.error("Forta API HTTP error: %d", e.response.status_code)
        record_failure(CIRCUIT_NAME)
        return []
    except httpx.ConnectError:
        logger.error("Forta API connection failed")
        record_failure(CIRCUIT_NAME)
        return []
    except Exception as e:
        logger.error("Forta API error: %s", e)
        record_failure(CIRCUIT_NAME)
        return []


def get_stored_forta_alerts(token_id: str = None, limit: int = 50) -> list[dict]:
    """Get stored Forta alerts from SQLite, optionally filtered by ZARQ token."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if token_id:
        rows = conn.execute(
            "SELECT * FROM forta_alerts WHERE zarq_token_id = ? ORDER BY created_at DESC LIMIT ?",
            (token_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM forta_alerts WHERE zarq_token_id IS NOT NULL ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
