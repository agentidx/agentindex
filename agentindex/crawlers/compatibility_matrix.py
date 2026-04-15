"""
Compatibility Matrix Generator — Sundays 07:00
=================================================
Reads from agent_frameworks, mcp_compatibility, and agent_shared_deps
to generate a unified compatibility matrix and framework stats.

Usage:
    python -m agentindex.crawlers.compatibility_matrix
"""

import json
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy.sql import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [compat-matrix] %(message)s",
)
logger = logging.getLogger("compat-matrix")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"


def _init_db():
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS compatibility_matrix (
            agent_a TEXT NOT NULL,
            agent_b TEXT NOT NULL,
            compatibility_score REAL NOT NULL,
            compatibility_type TEXT NOT NULL,
            evidence TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (agent_a, agent_b, compatibility_type)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cm_a ON compatibility_matrix(agent_a)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cm_b ON compatibility_matrix(agent_b)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS framework_stats (
            framework TEXT PRIMARY KEY,
            agent_count INTEGER NOT NULL DEFAULT 0,
            avg_trust_score REAL,
            total_npm_downloads INTEGER DEFAULT 0,
            top_agent TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _build_same_framework_pairs(conn):
    """Build compatibility entries for agents sharing the same framework."""
    logger.info("Building same-framework compatibility pairs...")

    # Group agents by framework
    rows = conn.execute(
        "SELECT agent_name, framework FROM agent_frameworks"
    ).fetchall()

    framework_agents = defaultdict(list)
    for name, fw in rows:
        framework_agents[fw].append(name)

    count = 0
    now = datetime.now().isoformat()

    for fw, agents in framework_agents.items():
        if len(agents) < 2:
            continue
        # Only generate pairs for top 50 agents per framework to keep manageable
        agents = agents[:50]
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                a, b = sorted([agents[i], agents[j]])
                from agentindex.crypto.dual_write import dual_execute
                dual_execute(conn,
                    "INSERT OR REPLACE INTO compatibility_matrix "
                    "(agent_a, agent_b, compatibility_score, compatibility_type, evidence, updated_at) "
                    "VALUES (?, ?, ?, 'same_framework', ?, ?)",
                    (a, b, 70.0, json.dumps({"framework": fw}), now)
                )
                count += 1

    conn.commit()
    logger.info(f"  Same-framework pairs: {count}")
    return count


def _build_shared_dep_pairs(conn):
    """Copy shared dependency data into compatibility matrix."""
    logger.info("Building shared-dependency compatibility pairs...")

    rows = conn.execute(
        "SELECT agent_a, agent_b, shared_count, shared_packages FROM agent_shared_deps"
    ).fetchall()

    count = 0
    now = datetime.now().isoformat()

    for a, b, shared_count, packages in rows:
        a_sorted, b_sorted = sorted([a, b])
        # Score based on shared count: 30 base + scale up to 70 max
        score = min(30 + shared_count * 2, 100)
        from agentindex.crypto.dual_write import dual_execute
        dual_execute(conn,
            "INSERT OR REPLACE INTO compatibility_matrix "
            "(agent_a, agent_b, compatibility_score, compatibility_type, evidence, updated_at) "
            "VALUES (?, ?, ?, 'shared_dependencies', ?, ?)",
            (a_sorted, b_sorted, score, json.dumps({"shared_count": shared_count, "packages": packages}), now)
        )
        count += 1

    conn.commit()
    logger.info(f"  Shared-dependency pairs: {count}")
    return count


def _build_mcp_pairs(conn):
    """Build MCP client-server compatibility entries."""
    logger.info("Building MCP client-server compatibility pairs...")

    rows = conn.execute(
        "SELECT server_name, client, confidence FROM mcp_compatibility"
    ).fetchall()

    count = 0
    now = datetime.now().isoformat()

    for server, client, confidence in rows:
        score = {"explicit": 90, "config_example": 85, "inferred": 60}.get(confidence, 50)
        a, b = sorted([server, f"client:{client}"])
        from agentindex.crypto.dual_write import dual_execute
        dual_execute(conn,
            "INSERT OR REPLACE INTO compatibility_matrix "
            "(agent_a, agent_b, compatibility_score, compatibility_type, evidence, updated_at) "
            "VALUES (?, ?, ?, 'mcp_client_server', ?, ?)",
            (a, b, score, json.dumps({"client": client, "confidence": confidence}), now)
        )
        count += 1

    conn.commit()
    logger.info(f"  MCP client-server pairs: {count}")
    return count


def _compute_framework_stats(conn):
    """Compute aggregate stats per framework."""
    logger.info("Computing framework stats...")

    from agentindex.db.models import get_session
    session = get_session()

    # Get framework -> agent list
    fw_rows = conn.execute(
        "SELECT framework, agent_name FROM agent_frameworks"
    ).fetchall()

    fw_agents = defaultdict(list)
    for fw, name in fw_rows:
        fw_agents[fw].append(name)

    now = datetime.now().isoformat()
    conn.execute("DELETE FROM framework_stats")

    for fw, agents in fw_agents.items():
        # Get trust scores and downloads from PG
        names_str = ",".join(f"'{n}'" for n in agents[:200])  # Cap for query length
        try:
            stats = session.execute(text(f"""
                SELECT AVG(COALESCE(trust_score_v2, trust_score)) as avg_ts,
                       MAX(name) FILTER (WHERE COALESCE(trust_score_v2, trust_score) = (
                           SELECT MAX(COALESCE(trust_score_v2, trust_score))
                           FROM entity_lookup WHERE name IN ({names_str}) AND is_active = true
                       )) as top_agent
                FROM entity_lookup
                WHERE name IN ({names_str}) AND is_active = true
            """)).fetchone()
            avg_ts = round(float(stats[0]), 1) if stats and stats[0] else 0
            top_agent = stats[1] if stats else agents[0]
        except Exception:
            avg_ts = 0
            top_agent = agents[0] if agents else ""

        # Get npm downloads from SQLite
        total_dl = 0
        for name in agents[:200]:
            dl_row = conn.execute(
                "SELECT weekly_downloads FROM package_downloads WHERE package_name = ? OR agent_id = ?", (name, name)
            ).fetchone()
            if dl_row and dl_row[0]:
                total_dl += dl_row[0]

        conn.execute(
            "INSERT OR REPLACE INTO framework_stats "
            "(framework, agent_count, avg_trust_score, total_npm_downloads, top_agent, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fw, len(agents), avg_ts, total_dl, top_agent, now)
        )

    conn.commit()
    session.close()
    logger.info(f"  Framework stats computed: {len(fw_agents)} frameworks")
    return len(fw_agents)


def main():
    logger.info("=" * 60)
    logger.info("Compatibility Matrix Generator — starting")
    logger.info("=" * 60)

    _init_db()
    conn = sqlite3.connect(str(SQLITE_DB))

    # Clear old matrix
    from agentindex.crypto.dual_write import dual_delete
    dual_delete(conn, "DELETE FROM compatibility_matrix")
    conn.commit()

    fw_pairs = _build_same_framework_pairs(conn)
    dep_pairs = _build_shared_dep_pairs(conn)
    mcp_pairs = _build_mcp_pairs(conn)
    fw_count = _compute_framework_stats(conn)

    total = conn.execute("SELECT COUNT(*) FROM compatibility_matrix").fetchone()[0]

    conn.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Compatibility Matrix Generator — COMPLETE")
    logger.info(f"  Total matrix entries: {total}")
    logger.info(f"    Same-framework: {fw_pairs}")
    logger.info(f"    Shared dependencies: {dep_pairs}")
    logger.info(f"    MCP client-server: {mcp_pairs}")
    logger.info(f"  Framework stats: {fw_count} frameworks")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
