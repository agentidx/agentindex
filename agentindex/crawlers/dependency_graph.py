"""
Dependency Graph Builder — Sundays 06:00
==========================================
Parses full dependency lists from agents' package files.
Cross-references with CVE data and calculates shared dependencies between agents.

Usage:
    python -m agentindex.crawlers.dependency_graph
"""

import json
import logging
import os
import re
import sqlite3
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy.sql import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [dep-graph] %(message)s",
)
logger = logging.getLogger("dep-graph")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or ""

if not GITHUB_TOKEN:
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GITHUB_TOKEN="):
                GITHUB_TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

MAX_AGENTS = 5000
RATE_DELAY = 0.8
SHARED_DEP_THRESHOLD = 5


def _init_db():
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT,
            agent_name TEXT NOT NULL,
            dependency_name TEXT NOT NULL,
            dependency_version TEXT,
            registry TEXT NOT NULL,
            is_direct BOOLEAN DEFAULT 1,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ad_name ON agent_dependencies(agent_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ad_dep ON agent_dependencies(dependency_name)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_shared_deps (
            agent_a TEXT NOT NULL,
            agent_b TEXT NOT NULL,
            shared_count INTEGER NOT NULL,
            shared_packages TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (agent_a, agent_b)
        )
    """)
    conn.commit()
    conn.close()


def _get_top_agents():
    from agentindex.db.models import get_session
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT id, name, source_url
            FROM agents
            WHERE is_active = true
              AND source_url IS NOT NULL
              AND source_url LIKE '%github.com%'
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC, stars DESC NULLS LAST
            LIMIT :lim
        """), {"lim": MAX_AGENTS}).fetchall()
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


def _parse_package_json(content):
    """Parse npm dependencies from package.json."""
    deps = []
    try:
        pkg = json.loads(content)
        for dep_name, version in pkg.get("dependencies", {}).items():
            deps.append({"name": dep_name, "version": str(version), "registry": "npm", "is_direct": True})
        for dep_name, version in pkg.get("devDependencies", {}).items():
            deps.append({"name": dep_name, "version": str(version), "registry": "npm", "is_direct": True})
    except (json.JSONDecodeError, TypeError):
        pass
    return deps


def _parse_requirements_txt(content):
    """Parse Python dependencies from requirements.txt."""
    deps = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        pkg = re.split(r'[>=<!\[\];,\s]', line)[0].strip().lower()
        if pkg and len(pkg) > 1:
            version_match = re.search(r'[>=<~!]+\s*([0-9][0-9a-z.*]*)', line)
            version = version_match.group(1) if version_match else None
            deps.append({"name": pkg, "version": version, "registry": "pypi", "is_direct": True})
    return deps


def _parse_pyproject_toml(content):
    """Parse Python dependencies from pyproject.toml (simple extraction)."""
    deps = []
    in_deps = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped in ("[project.dependencies]", "dependencies = [") or "dependencies" in stripped and "[" in stripped:
            in_deps = True
            continue
        if in_deps:
            if stripped.startswith("[") and "dependencies" not in stripped:
                in_deps = False
                continue
            if stripped == "]":
                in_deps = False
                continue
            # Extract package name from quoted strings
            m = re.match(r'["\']([a-zA-Z0-9_-]+)', stripped)
            if m:
                pkg = m.group(1).lower()
                version_match = re.search(r'[>=<~!]+\s*([0-9][0-9a-z.*]*)', stripped)
                version = version_match.group(1) if version_match else None
                deps.append({"name": pkg, "version": version, "registry": "pypi", "is_direct": True})
    return deps


def scan_agent(http_client, agent, conn):
    """Scan one agent's dependencies."""
    repo = _parse_github_url(agent.get("source_url"))
    if not repo:
        return 0

    agent_id = str(agent["id"])
    agent_name = agent["name"]

    # Skip if recently scanned
    existing = conn.execute(
        "SELECT COUNT(*) FROM agent_dependencies WHERE agent_name = ? AND fetched_at > datetime('now', '-7 days')",
        (agent_name,)
    ).fetchone()
    if existing and existing[0] > 0:
        return 0

    conn.execute("DELETE FROM agent_dependencies WHERE agent_name = ?", (agent_name,))

    all_deps = []

    # Try package.json
    content = _fetch_file(http_client, repo, "package.json")
    if content:
        all_deps.extend(_parse_package_json(content))
    time.sleep(RATE_DELAY)

    # Try requirements.txt
    content = _fetch_file(http_client, repo, "requirements.txt")
    if content:
        all_deps.extend(_parse_requirements_txt(content))
    time.sleep(RATE_DELAY)

    # Try pyproject.toml
    if not any(d["registry"] == "pypi" for d in all_deps):
        content = _fetch_file(http_client, repo, "pyproject.toml")
        if content:
            all_deps.extend(_parse_pyproject_toml(content))
        time.sleep(RATE_DELAY)

    # Deduplicate
    seen = set()
    unique_deps = []
    for d in all_deps:
        key = (d["name"], d["registry"])
        if key not in seen:
            seen.add(key)
            unique_deps.append(d)

    # Insert
    for d in unique_deps:
        conn.execute(
            "INSERT INTO agent_dependencies (agent_id, agent_name, dependency_name, dependency_version, registry, is_direct) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, agent_name, d["name"], d["version"], d["registry"], d["is_direct"])
        )

    if unique_deps:
        conn.commit()

    return len(unique_deps)


def compute_shared_deps(conn):
    """Compute shared dependency counts between agent pairs."""
    logger.info("Computing shared dependencies...")

    conn.execute("DELETE FROM agent_shared_deps")

    # Get all agent->deps mappings
    rows = conn.execute(
        "SELECT agent_name, dependency_name FROM agent_dependencies"
    ).fetchall()

    agent_deps = defaultdict(set)
    for name, dep in rows:
        agent_deps[name].add(dep)

    agents = list(agent_deps.keys())
    pairs_inserted = 0

    # Only compare agents that share at least SHARED_DEP_THRESHOLD deps
    # Build inverted index: dep -> set of agents
    dep_agents = defaultdict(set)
    for agent, deps in agent_deps.items():
        for dep in deps:
            dep_agents[dep].add(agent)

    # Find candidate pairs
    pair_shared = defaultdict(set)
    for dep, agents_with_dep in dep_agents.items():
        agents_list = sorted(agents_with_dep)
        for i in range(len(agents_list)):
            for j in range(i + 1, min(i + 50, len(agents_list))):  # Cap comparisons
                pair_shared[(agents_list[i], agents_list[j])].add(dep)

    # Insert pairs above threshold
    for (a, b), shared in pair_shared.items():
        if len(shared) >= SHARED_DEP_THRESHOLD:
            shared_list = sorted(shared)[:20]  # Cap stored packages
            conn.execute(
                "INSERT OR REPLACE INTO agent_shared_deps (agent_a, agent_b, shared_count, shared_packages, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (a, b, len(shared), json.dumps(shared_list), datetime.now().isoformat())
            )
            pairs_inserted += 1

    conn.commit()
    logger.info(f"  Shared dependency pairs (>={SHARED_DEP_THRESHOLD}): {pairs_inserted}")
    return pairs_inserted


def check_vulnerable_deps(conn):
    """Cross-reference dependencies with CVE data."""
    vuln_count = conn.execute("""
        SELECT COUNT(DISTINCT ad.dependency_name)
        FROM agent_dependencies ad
        INNER JOIN agent_vulnerabilities av ON ad.dependency_name = av.agent_name
    """).fetchone()[0]

    affected_agents = conn.execute("""
        SELECT COUNT(DISTINCT ad.agent_name)
        FROM agent_dependencies ad
        INNER JOIN agent_vulnerabilities av ON ad.dependency_name = av.agent_name
    """).fetchone()[0]

    logger.info(f"  Vulnerable dependencies: {vuln_count}")
    logger.info(f"  Agents with vulnerable deps: {affected_agents}")
    return vuln_count, affected_agents


def main():
    logger.info("=" * 60)
    logger.info("Dependency Graph Builder — starting")
    logger.info("=" * 60)

    if not GITHUB_TOKEN:
        logger.error("No GITHUB_TOKEN found.")
        return

    _init_db()
    agents = _get_top_agents()
    logger.info(f"Found {len(agents)} agents with GitHub repos")

    conn = sqlite3.connect(str(SQLITE_DB))
    total_scanned = 0
    total_deps = 0

    with httpx.Client(timeout=20) as client:
        for i, agent in enumerate(agents):
            try:
                count = scan_agent(client, agent, conn)
                total_scanned += 1
                total_deps += count
            except Exception as e:
                logger.error(f"Error scanning {agent['name']}: {e}")

            if (i + 1) % 100 == 0:
                logger.info(f"  Progress: {i + 1}/{len(agents)}, {total_deps} deps")

    # Compute shared dependencies
    pairs = compute_shared_deps(conn)

    # Check vulnerable deps
    vuln_deps, vuln_agents = check_vulnerable_deps(conn)

    # Top shared pairs
    top_pairs = conn.execute(
        "SELECT agent_a, agent_b, shared_count FROM agent_shared_deps ORDER BY shared_count DESC LIMIT 10"
    ).fetchall()

    conn.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Dependency Graph Builder — COMPLETE")
    logger.info(f"  Agents scanned: {total_scanned}")
    logger.info(f"  Total dependencies: {total_deps}")
    logger.info(f"  Shared dep pairs: {pairs}")
    logger.info(f"  Vulnerable deps: {vuln_deps}")
    logger.info(f"  Agents with vulnerable deps: {vuln_agents}")
    if top_pairs:
        logger.info(f"  Top shared dependency pairs:")
        for a, b, count in top_pairs:
            logger.info(f"    {a} <-> {b}: {count} shared")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
