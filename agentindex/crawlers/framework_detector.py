"""
Framework Detector — Sundays 05:00
====================================
Scans top 5,000 agents' GitHub repos for framework dependencies.
Detects: langchain, crewai, autogen, llamaindex, openai, anthropic, etc.
Stores results in agent_frameworks table (SQLite).

Usage:
    python -m agentindex.crawlers.framework_detector
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
    format="%(asctime)s %(levelname)s [framework-detector] %(message)s",
)
logger = logging.getLogger("framework-detector")

SQLITE_DB = Path(__file__).parent.parent / "crypto" / "crypto_trust.db"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or ""

# Load from .env if not in environment
if not GITHUB_TOKEN:
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GITHUB_TOKEN="):
                GITHUB_TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

# Known frameworks to detect
PYTHON_FRAMEWORKS = {
    "langchain": "langchain",
    "langchain-core": "langchain",
    "langchain-community": "langchain",
    "langgraph": "langgraph",
    "crewai": "crewai",
    "crew-ai": "crewai",
    "pyautogen": "autogen",
    "autogen": "autogen",
    "llama-index": "llamaindex",
    "llama_index": "llamaindex",
    "llamaindex": "llamaindex",
    "semantic-kernel": "semantic-kernel",
    "haystack-ai": "haystack",
    "farm-haystack": "haystack",
    "dspy-ai": "dspy",
    "dspy": "dspy",
    "pydantic-ai": "pydantic-ai",
    "smolagents": "smolagents",
    "taskweaver": "taskweaver",
    "camel-ai": "camel-ai",
    "openai": "openai",
    "anthropic": "anthropic",
    "google-generativeai": "google-genai",
    "google-genai": "google-genai",
    "groq": "groq",
    "mistralai": "mistral",
    "ollama": "ollama",
    "cohere": "cohere",
    "transformers": "transformers",
    "torch": "pytorch",
    "tensorflow": "tensorflow",
}

JS_FRAMEWORKS = {
    "langchain": "langchain",
    "@langchain/core": "langchain",
    "@langchain/community": "langchain",
    "@langchain/openai": "langchain",
    "ai": "vercel-ai",
    "@ai-sdk/openai": "vercel-ai",
    "@ai-sdk/anthropic": "vercel-ai",
    "mastra": "mastra",
    "@mastra/core": "mastra",
    "@e2b/sdk": "e2b",
    "e2b": "e2b",
    "openai": "openai",
    "@anthropic-ai/sdk": "anthropic",
    "@google/generative-ai": "google-genai",
    "groq-sdk": "groq",
    "@mistralai/mistralai": "mistral",
    "ollama": "ollama",
    "cohere-ai": "cohere",
    "@modelcontextprotocol/sdk": "mcp-sdk",
}

MAX_AGENTS = 5000
RATE_DELAY = 0.8  # seconds between GitHub API calls


def _init_db():
    """Create agent_frameworks table if not exists."""
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_frameworks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT,
            agent_name TEXT NOT NULL,
            framework TEXT NOT NULL,
            version TEXT,
            source TEXT NOT NULL,
            confidence TEXT NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_af_name ON agent_frameworks(agent_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_af_framework ON agent_frameworks(framework)")
    conn.commit()
    conn.close()


def _get_top_agents():
    """Get top agents with GitHub source URLs."""
    from agentindex.db.models import get_session
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT id, name, source_url, source
            FROM entity_lookup
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


def _parse_github_url(source_url):
    """Extract owner/repo from GitHub URL."""
    if not source_url:
        return None
    m = re.search(r'github\.com/([^/]+/[^/]+)', source_url)
    if m:
        repo = m.group(1).rstrip("/").split("#")[0].split("?")[0]
        # Remove .git suffix
        if repo.endswith(".git"):
            repo = repo[:-4]
        return repo
    return None


def _fetch_file(client, repo, filepath):
    """Fetch a file from GitHub API. Returns content or None."""
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


def _detect_from_package_json(content):
    """Detect JS frameworks from package.json."""
    found = []
    try:
        pkg = json.loads(content)
        all_deps = {}
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            all_deps.update(pkg.get(key, {}))
        for dep_name, version in all_deps.items():
            canonical = JS_FRAMEWORKS.get(dep_name)
            if canonical:
                found.append({
                    "framework": canonical,
                    "version": str(version),
                    "source": "package.json",
                    "confidence": "direct_dependency",
                })
    except (json.JSONDecodeError, TypeError):
        pass
    return found


def _detect_from_python_deps(content, source_file):
    """Detect Python frameworks from requirements.txt, pyproject.toml, setup.py."""
    found = []
    # Extract package names
    lines = content.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Extract package name (before version specifier)
        pkg = re.split(r'[>=<!\[\];,\s]', line)[0].strip().lower()
        canonical = PYTHON_FRAMEWORKS.get(pkg)
        if canonical:
            # Try to extract version
            version_match = re.search(r'[>=<~!]+\s*([0-9][0-9a-z.*]*)', line)
            version = version_match.group(1) if version_match else None
            found.append({
                "framework": canonical,
                "version": version,
                "source": source_file,
                "confidence": "direct_dependency",
            })
    return found


def _detect_from_readme(content):
    """Detect framework mentions in README."""
    found = []
    content_lower = content.lower()
    all_frameworks = set(PYTHON_FRAMEWORKS.values()) | set(JS_FRAMEWORKS.values())
    for fw in all_frameworks:
        # Match the framework name as a word
        if re.search(r'\b' + re.escape(fw) + r'\b', content_lower):
            found.append({
                "framework": fw,
                "version": None,
                "source": "readme",
                "confidence": "mentioned",
            })
    return found


def scan_agent(client, agent, conn):
    """Scan one agent's GitHub repo for frameworks."""
    repo = _parse_github_url(agent.get("source_url"))
    if not repo:
        return 0

    agent_id = str(agent["id"])
    agent_name = agent["name"]

    # Check if already scanned recently (within 7 days)
    existing = conn.execute(
        "SELECT COUNT(*) FROM agent_frameworks WHERE agent_name = ? AND fetched_at > datetime('now', '-7 days')",
        (agent_name,)
    ).fetchone()
    if existing and existing[0] > 0:
        return 0

    # Clear old entries
    conn.execute("DELETE FROM agent_frameworks WHERE agent_name = ?", (agent_name,))

    all_found = []

    # Try package.json
    content = _fetch_file(client, repo, "package.json")
    if content:
        all_found.extend(_detect_from_package_json(content))
    time.sleep(RATE_DELAY)

    # Try requirements.txt
    content = _fetch_file(client, repo, "requirements.txt")
    if content:
        all_found.extend(_detect_from_python_deps(content, "requirements.txt"))
    time.sleep(RATE_DELAY)

    # Try pyproject.toml
    content = _fetch_file(client, repo, "pyproject.toml")
    if content:
        all_found.extend(_detect_from_python_deps(content, "pyproject.toml"))
    time.sleep(RATE_DELAY)

    # Try README.md (only if we haven't found direct deps)
    if not all_found:
        content = _fetch_file(client, repo, "README.md")
        if content:
            all_found.extend(_detect_from_readme(content[:10000]))  # First 10K chars
        time.sleep(RATE_DELAY)

    # Deduplicate by framework name, prefer direct_dependency over mentioned
    seen = {}
    for item in all_found:
        fw = item["framework"]
        if fw not in seen or item["confidence"] == "direct_dependency":
            seen[fw] = item

    # Insert into DB
    for fw, item in seen.items():
        conn.execute(
            "INSERT INTO agent_frameworks (agent_id, agent_name, framework, version, source, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, agent_name, item["framework"], item["version"], item["source"], item["confidence"])
        )

    if seen:
        conn.commit()

    return len(seen)


def main():
    logger.info("=" * 60)
    logger.info("Framework Detector — starting")
    logger.info("=" * 60)

    if not GITHUB_TOKEN:
        logger.error("No GITHUB_TOKEN found. Set it in .env or environment.")
        return

    _init_db()
    agents = _get_top_agents()
    logger.info(f"Found {len(agents)} agents with GitHub repos")

    conn = sqlite3.connect(str(SQLITE_DB))
    total_scanned = 0
    total_frameworks = 0
    framework_counts = {}

    with httpx.Client(timeout=20) as client:
        for i, agent in enumerate(agents):
            try:
                count = scan_agent(client, agent, conn)
                total_scanned += 1
                total_frameworks += count
                if count > 0:
                    # Track framework distribution
                    rows = conn.execute(
                        "SELECT framework FROM agent_frameworks WHERE agent_name = ?",
                        (agent["name"],)
                    ).fetchall()
                    for r in rows:
                        framework_counts[r[0]] = framework_counts.get(r[0], 0) + 1
            except Exception as e:
                logger.error(f"Error scanning {agent['name']}: {e}")

            if (i + 1) % 100 == 0:
                logger.info(f"  Progress: {i + 1}/{len(agents)} scanned, {total_frameworks} frameworks detected")

    conn.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Framework Detector — COMPLETE")
    logger.info(f"  Agents scanned: {total_scanned}")
    logger.info(f"  Frameworks detected: {total_frameworks}")
    logger.info(f"  Distribution:")
    for fw, count in sorted(framework_counts.items(), key=lambda x: -x[1])[:20]:
        logger.info(f"    {fw}: {count}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
