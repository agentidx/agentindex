"""
MCP Compatibility Scanner — Sundays 05:30
============================================
Scans MCP servers for client compatibility (Claude, Cursor, etc.).
Checks README, package files, and config examples.

Usage:
    python -m agentindex.crawlers.mcp_compatibility_scanner
"""

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy.sql import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [mcp-compat] %(message)s",
)
logger = logging.getLogger("mcp-compat")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or ""

if not GITHUB_TOKEN:
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GITHUB_TOKEN="):
                GITHUB_TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

# MCP client detection patterns
CLIENT_PATTERNS = {
    "claude": [
        r'claude_desktop_config\.json',
        r'claude[\s_-]?desktop',
        r'\bclaude\b.*\bconfig',
        r'anthropic.*desktop',
        r'Claude\s+Desktop',
    ],
    "cursor": [
        r'\bcursor\b.*\bmcp\b',
        r'cursor[\s_-]?settings',
        r'\.cursor/',
        r'Cursor\s+IDE',
        r'cursor.*config',
    ],
    "windsurf": [
        r'\bwindsurf\b',
        r'codeium.*windsurf',
    ],
    "cody": [
        r'\bcody\b.*\bmcp\b',
        r'sourcegraph.*cody',
    ],
    "continue": [
        r'\bcontinue\b.*\bmcp\b',
        r'continue\.dev',
        r'\.continue/',
    ],
    "cline": [
        r'\bcline\b.*\bmcp\b',
        r'cline.*settings',
    ],
    "zed": [
        r'\bzed\b.*\bmcp\b',
        r'zed.*settings',
    ],
    "vscode": [
        r'\bvs\s*code\b.*\bmcp\b',
        r'vscode.*mcp',
        r'\.vscode/',
    ],
    "chatgpt": [
        r'\bchatgpt\b.*\bmcp\b',
        r'openai.*mcp',
    ],
}

RATE_DELAY = 0.8


def _init_db():
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mcp_compatibility (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mcp_server_id TEXT,
            server_name TEXT NOT NULL,
            client TEXT NOT NULL,
            confidence TEXT NOT NULL,
            sdk_version TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_compat_name ON mcp_compatibility(server_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_compat_client ON mcp_compatibility(client)")
    conn.commit()
    conn.close()


def _get_mcp_servers():
    from agentindex.db.models import get_session
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT id, name, source_url
            FROM entity_lookup
            WHERE is_active = true
              AND agent_type = 'mcp_server'
              AND source_url IS NOT NULL
              AND source_url LIKE '%github.com%'
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST, stars DESC NULLS LAST
            LIMIT 5000
        """)).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        session.close()


def _parse_github_url(url):
    if not url:
        return None
    m = re.search(r'github\.com/([^/]+/[^/]+)', url)
    if m:
        repo = m.group(1).rstrip("/").split("#")[0].split("?")[0]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return repo
    return None


def _fetch_file(client, repo, filepath):
    url = f"https://api.github.com/repos/{repo}/contents/{filepath}"
    headers = {"Accept": "application/vnd.github.v3.raw"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    try:
        resp = client.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


def _detect_clients_from_readme(content):
    """Detect MCP client compatibility from README content."""
    results = {}
    content_lower = content.lower()

    for client_name, patterns in CLIENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, content_lower):
                # Determine confidence
                # Config example = higher confidence
                if "config" in pattern or "settings" in pattern or "desktop_config" in pattern:
                    confidence = "config_example"
                else:
                    confidence = "explicit"
                if client_name not in results or confidence == "config_example":
                    results[client_name] = confidence
                break

    return results


def _detect_sdk_version(content):
    """Extract MCP SDK version from package.json."""
    try:
        pkg = json.loads(content)
        all_deps = {}
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            all_deps.update(pkg.get(key, {}))
        for dep in ("@modelcontextprotocol/sdk", "@modelcontextprotocol/server-stdio", "mcp"):
            if dep in all_deps:
                return str(all_deps[dep])
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def scan_server(http_client, server, conn):
    """Scan one MCP server for client compatibility."""
    repo = _parse_github_url(server.get("source_url"))
    if not repo:
        return 0

    server_id = str(server["id"])
    server_name = server["name"]

    # Check if already scanned recently
    existing = conn.execute(
        "SELECT COUNT(*) FROM mcp_compatibility WHERE server_name = ? AND fetched_at > datetime('now', '-7 days')",
        (server_name,)
    ).fetchone()
    if existing and existing[0] > 0:
        return 0

    conn.execute("DELETE FROM mcp_compatibility WHERE server_name = ?", (server_name,))

    clients_found = {}
    sdk_version = None

    # Check README
    readme = _fetch_file(http_client, repo, "README.md")
    if readme:
        clients_found.update(_detect_clients_from_readme(readme[:15000]))
    time.sleep(RATE_DELAY)

    # Check package.json for SDK version
    pkg = _fetch_file(http_client, repo, "package.json")
    if pkg:
        sdk_version = _detect_sdk_version(pkg)
        # If uses MCP SDK, it's compatible with all standard clients
        if sdk_version and not clients_found:
            for client_name in ("claude", "cursor", "windsurf", "continue", "cline", "vscode"):
                clients_found[client_name] = "inferred"
    time.sleep(RATE_DELAY)

    # Check pyproject.toml for Python MCP SDK
    if not sdk_version:
        pyproject = _fetch_file(http_client, repo, "pyproject.toml")
        if pyproject and "mcp" in pyproject.lower():
            sdk_version = "python-mcp"
            if not clients_found:
                for client_name in ("claude", "cursor", "continue", "cline"):
                    clients_found[client_name] = "inferred"
        time.sleep(RATE_DELAY)

    # Insert results
    for client_name, confidence in clients_found.items():
        conn.execute(
            "INSERT INTO mcp_compatibility (mcp_server_id, server_name, client, confidence, sdk_version) "
            "VALUES (?, ?, ?, ?, ?)",
            (server_id, server_name, client_name, confidence, sdk_version)
        )

    if clients_found:
        conn.commit()

    return len(clients_found)


def main():
    logger.info("=" * 60)
    logger.info("MCP Compatibility Scanner — starting")
    logger.info("=" * 60)

    if not GITHUB_TOKEN:
        logger.error("No GITHUB_TOKEN found.")
        return

    _init_db()
    servers = _get_mcp_servers()
    logger.info(f"Found {len(servers)} MCP servers with GitHub repos")

    conn = sqlite3.connect(str(SQLITE_DB))
    total_scanned = 0
    total_mappings = 0
    client_counts = {}

    with httpx.Client(timeout=20) as client:
        for i, server in enumerate(servers):
            try:
                count = scan_server(client, server, conn)
                total_scanned += 1
                total_mappings += count
                if count > 0:
                    rows = conn.execute(
                        "SELECT client FROM mcp_compatibility WHERE server_name = ?",
                        (server["name"],)
                    ).fetchall()
                    for r in rows:
                        client_counts[r[0]] = client_counts.get(r[0], 0) + 1
            except Exception as e:
                logger.error(f"Error scanning {server['name']}: {e}")

            if (i + 1) % 100 == 0:
                logger.info(f"  Progress: {i + 1}/{len(servers)}, {total_mappings} mappings")

    conn.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("MCP Compatibility Scanner — COMPLETE")
    logger.info(f"  Servers scanned: {total_scanned}")
    logger.info(f"  Compatibility mappings: {total_mappings}")
    logger.info(f"  Client distribution:")
    for cl, count in sorted(client_counts.items(), key=lambda x: -x[1]):
        logger.info(f"    {cl}: {count}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
