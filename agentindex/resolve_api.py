"""
/v1/resolve — Task-to-Tool Resolution Engine

Given a task description, finds the best AI agent or MCP server
from 200K+ indexed assets. Returns trust-verified recommendation
with install instructions.

The brain behind nerq-gateway.
"""

import hashlib
import json
import logging
import math
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from agentindex.db.models import get_session

logger = logging.getLogger("nerq.resolve")

router_resolve = APIRouter()

# ── Capability Mapping ──────────────────────────────────────────

CAPABILITY_MAP = {
    # Source control
    "github": "source_control", "gitlab": "source_control", "git": "source_control",
    "repository": "source_control", "repo": "source_control", "commit": "source_control",
    "pull request": "source_control", "pr review": "source_control", "branch": "source_control",
    # Database
    "database": "database", "sql": "database", "postgres": "database", "postgresql": "database",
    "mysql": "database", "sqlite": "database", "mongodb": "database", "redis": "database",
    "query": "database", "table": "database", "schema": "database", "supabase": "database",
    # Web search
    "search": "web_search", "web": "web_search", "browse": "web_search", "google": "web_search",
    "scrape": "web_search", "crawl": "web_search", "fetch url": "web_search",
    # Filesystem
    "file": "filesystem", "read file": "filesystem", "write file": "filesystem",
    "directory": "filesystem", "folder": "filesystem", "path": "filesystem", "disk": "filesystem",
    # Code
    "code": "coding", "review": "coding", "debug": "coding", "refactor": "coding",
    "test": "coding", "lint": "coding", "compile": "coding", "build": "coding",
    "programming": "coding", "develop": "coding",
    # Communication
    "email": "communication", "slack": "communication", "discord": "communication",
    "message": "communication", "chat": "communication", "notify": "communication",
    "calendar": "communication", "schedule": "communication", "teams": "communication",
    # Data/Analytics
    "data": "data_analytics", "analytics": "data_analytics", "csv": "data_analytics",
    "excel": "data_analytics", "spreadsheet": "data_analytics", "chart": "data_analytics",
    "visualization": "data_analytics", "dashboard": "data_analytics", "pandas": "data_analytics",
    # AI/ML
    "model": "ai_ml", "train": "ai_ml", "inference": "ai_ml", "embedding": "ai_ml",
    "vector": "ai_ml", "llm": "ai_ml", "prompt": "ai_ml", "fine-tune": "ai_ml",
    # Security
    "security": "security", "vulnerability": "security", "cve": "security",
    "scan": "security", "audit": "security", "pentest": "security",
    # Cloud/Infrastructure
    "aws": "cloud", "azure": "cloud", "gcp": "cloud", "docker": "cloud",
    "kubernetes": "cloud", "deploy": "cloud", "server": "cloud", "cloud": "cloud",
    "terraform": "cloud", "vercel": "cloud", "netlify": "cloud",
    # Image/Media
    "image": "media", "photo": "media", "video": "media", "audio": "media",
    "screenshot": "media", "pdf": "media", "document": "media", "ocr": "media",
    # API/Integration
    "api": "integration", "webhook": "integration", "rest": "integration",
    "graphql": "integration", "soap": "integration", "zapier": "integration",
    # Monitoring
    "monitor": "monitoring", "alert": "monitoring", "log": "monitoring",
    "metric": "monitoring", "uptime": "monitoring", "observability": "monitoring",
    # Crypto/Finance
    "crypto": "finance", "token": "finance", "defi": "finance", "blockchain": "finance",
    "trading": "finance", "price": "finance", "wallet": "finance", "bitcoin": "finance",
    "ethereum": "finance",
    # Productivity
    "notion": "productivity", "todoist": "productivity", "trello": "productivity",
    "jira": "productivity", "asana": "productivity", "linear": "productivity",
    "project management": "productivity", "task": "productivity",
    # Design
    "figma": "design", "design": "design", "ui": "design", "ux": "design",
    "wireframe": "design", "prototype": "design",
    # DevOps
    "ci/cd": "devops", "pipeline": "devops", "jenkins": "devops",
    "github actions": "devops", "ansible": "devops",
    # Maps/Location
    "map": "location", "location": "location", "geocode": "location",
    "directions": "location", "gps": "location", "weather": "location",
}

# Reverse map: capability → search keywords for DB matching
CAPABILITY_SEARCH_TERMS = {
    "source_control": ["github", "git", "gitlab", "repository", "commit", "pull request"],
    "database": ["database", "sql", "postgres", "mysql", "mongodb", "redis", "supabase", "query"],
    "web_search": ["search", "web", "browse", "scrape", "crawl", "fetch", "browser"],
    "filesystem": ["file", "filesystem", "directory", "read", "write"],
    "coding": ["code", "review", "debug", "lint", "test", "refactor", "ide", "editor"],
    "communication": ["email", "slack", "discord", "message", "chat", "calendar", "teams"],
    "data_analytics": ["data", "analytics", "csv", "excel", "chart", "visualization", "pandas"],
    "ai_ml": ["model", "embedding", "vector", "llm", "inference", "ai", "machine learning"],
    "security": ["security", "vulnerability", "cve", "scan", "audit", "pentest"],
    "cloud": ["aws", "azure", "gcp", "docker", "kubernetes", "deploy", "cloud", "terraform"],
    "media": ["image", "photo", "video", "audio", "screenshot", "pdf", "ocr", "document"],
    "integration": ["api", "webhook", "rest", "graphql", "integration", "connect"],
    "monitoring": ["monitor", "alert", "log", "metric", "uptime", "observability"],
    "finance": ["crypto", "token", "defi", "blockchain", "trading", "price", "wallet", "finance"],
    "productivity": ["notion", "todoist", "trello", "jira", "asana", "linear", "project", "task"],
    "design": ["figma", "design", "ui", "ux", "wireframe", "prototype"],
    "devops": ["ci", "cd", "pipeline", "jenkins", "deploy", "ansible", "devops"],
    "location": ["map", "location", "geocode", "weather", "directions"],
}

# Known best tools for common queries — these get a +30 ranking bonus
KNOWN_BEST = {
    "github": "github-mcp-server",
    "postgres": "postgres-mcp-server",
    "postgresql": "postgres-mcp-server",
    "mysql": "mysql-mcp-server",
    "sqlite": "sqlite-mcp-server",
    "slack": "slack-mcp-server",
    "filesystem": "filesystem-mcp-server",
    "code review": "swe-agent",
    "web search": "brave-search-mcp",
    "browser": "puppeteer-mcp-server",
    "brave": "brave-search-mcp",
    "puppeteer": "puppeteer-mcp-server",
    "docker": "docker-mcp",
    "redis": "redis-mcp-server",
    "mongodb": "mongodb-mcp-server",
    "supabase": "supabase-mcp-server",
    "notion": "notion-mcp-server",
    "linear": "linear-mcp-server",
    "stripe": "stripe-mcp-server",
    "sentry": "sentry-mcp-server",
    "firecrawl": "firecrawl-mcp-server",
    "cloudflare": "cloudflare-mcp-server",
    "database": "db connector",
    "sql": "db connector",
    "csv": "csv",
    "spreadsheet": "csv",
}


def _parse_capabilities(task: str) -> list[str]:
    """Extract capability categories from a task description."""
    task_lower = task.lower()
    caps = set()
    # Check multi-word phrases first, then single words
    for keyword, cap in sorted(CAPABILITY_MAP.items(), key=lambda x: -len(x[0])):
        if keyword in task_lower:
            caps.add(cap)
    return list(caps)


def _build_search_queries(task: str, capabilities: list[str]) -> list[tuple[str, dict]]:
    """Build PostgreSQL search queries — prioritize MCP/tool servers, then broaden."""
    words = re.findall(r'[a-zA-Z0-9_.-]+', task.lower())
    stop = {"the", "a", "an", "is", "are", "for", "to", "in", "on", "with", "and", "or",
            "my", "i", "need", "want", "find", "best", "good", "use", "using", "can", "how",
            "do", "does", "should", "would", "like", "get", "make", "create", "help", "me"}
    keywords = [w for w in words if w not in stop and len(w) > 1]

    if not keywords:
        keywords = ["agent", "tool"]

    _SELECT = """
        SELECT a.name, COALESCE(a.trust_score_v2, a.trust_score) AS trust_score,
               a.trust_grade, a.category, a.source, a.stars, a.downloads,
               a.description, a.source_url, a.last_source_update,
               a.frameworks, a.protocols, a.license, a.pricing, a.is_verified,
               a.author
        FROM agents a
        WHERE a.is_active = true
          AND COALESCE(a.trust_score_v2, a.trust_score) IS NOT NULL
    """
    _ORDER = "ORDER BY COALESCE(a.stars, 0) DESC, COALESCE(a.trust_score_v2, a.trust_score) DESC LIMIT 50"

    queries = []
    params_base = {}

    # Build keyword conditions — ALL keywords must match (AND)
    all_conds = []
    for i, kw in enumerate(keywords[:6]):
        key = f"kw{i}"
        params_base[key] = f"%{kw}%"
        all_conds.append(f"(LOWER(a.name) LIKE :{key} OR LOWER(COALESCE(a.description,'')) LIKE :{key})")
    where_all = " AND ".join(all_conds)

    # Build ANY keyword conditions (OR) for fallback
    where_any = " OR ".join(all_conds)

    # Query 1: MCP servers matching ANY keyword (highest priority — tools are what we want)
    q1 = f"{_SELECT} AND (a.source LIKE '%mcp%' OR a.source = 'pulsemcp' OR LOWER(a.name) LIKE '%mcp%') AND ({where_any}) {_ORDER}"
    queries.append((q1, dict(params_base)))

    # Query 2: Name contains a keyword (exact tool match)
    name_conds = " OR ".join([f"LOWER(a.name) LIKE :{f'kw{i}'}" for i in range(len(keywords[:6]))])
    q2 = f"{_SELECT} AND ({name_conds}) AND COALESCE(a.stars, 0) > 0 {_ORDER}"
    queries.append((q2, dict(params_base)))

    # Query 3: ALL keywords match in name or description (any source)
    q3 = f"{_SELECT} AND ({where_all}) {_ORDER}"
    queries.append((q3, dict(params_base)))

    # Query 4: ANY keyword matches (broadest, fallback)
    q4 = f"{_SELECT} AND ({where_any}) {_ORDER}"
    queries.append((q4, dict(params_base)))

    return queries


def _recency_score(last_update) -> float:
    """Score based on how recently the agent was updated."""
    if not last_update:
        return 20
    try:
        if hasattr(last_update, 'replace'):
            dt = last_update.replace(tzinfo=timezone.utc) if last_update.tzinfo is None else last_update
        else:
            return 20
        days = (datetime.now(timezone.utc) - dt).days
        if days < 7:
            return 100
        if days < 30:
            return 80
        if days < 90:
            return 60
        if days < 180:
            return 40
        return 20
    except Exception:
        return 20


def _capability_match_score(name: str, desc: str, category: str, capabilities: list[str], task_keywords: list[str]) -> float:
    """How well does this agent match the requested capabilities?"""
    text = f"{name} {desc} {category}".lower()
    matches = 0
    total = max(len(task_keywords), 1)
    for kw in task_keywords:
        if kw.lower() in text:
            matches += 1
    return min(100, (matches / total) * 100)


def _popularity_score(stars: int, downloads: int) -> float:
    """Normalized popularity score using log scale."""
    raw = (stars or 0) + (downloads or 0) * 0.1
    if raw <= 0:
        return 0
    return min(100, math.log10(raw + 1) * 20)


def _cost_bonus(pricing) -> float:
    """Score based on cost (higher = cheaper/free)."""
    if not pricing:
        return 80  # Unknown = assume reasonable
    p = str(pricing).lower()
    if "free" in p or "open" in p:
        return 100
    if any(x in p for x in ["$0", "free tier"]):
        return 90
    return 60


def _specificity_score(name: str, desc: str, task_keywords: list[str]) -> float:
    """How specifically does the agent name/description match the task keywords?
    Name matches are worth much more than description matches."""
    name_lower = name.lower()
    desc_lower = (desc or "").lower()
    score = 0
    total = max(len(task_keywords), 1)
    for kw in task_keywords:
        if kw in name_lower:
            score += 2.0  # Name match = strong signal
        elif kw in desc_lower[:200]:  # Early description = moderate signal
            score += 0.5
    return min(100, (score / total) * 50)


def _known_best_bonus(name: str, task: str) -> float:
    """Bonus for agents that are the known-best answer for a task."""
    name_lower = name.lower()
    task_lower = task.lower()
    for trigger, best_name in KNOWN_BEST.items():
        if trigger in task_lower and best_name.lower() in name_lower:
            return 30
    return 0


def _rank_agents(agents: list[dict], capabilities: list[str], task_keywords: list[str],
                 min_trust: float = 0, task: str = "") -> list[dict]:
    """Rank agents by composite score."""
    scored = []
    for a in agents:
        trust = a.get("trust_score") or 0
        if trust < min_trust:
            continue

        cap_match = _capability_match_score(
            a["name"], a.get("description", ""), a.get("category", ""),
            capabilities, task_keywords
        )
        specificity = _specificity_score(a["name"], a.get("description", ""), task_keywords)
        pop = _popularity_score(a.get("stars", 0), a.get("downloads", 0))
        recency = _recency_score(a.get("last_source_update"))
        cost = _cost_bonus(a.get("pricing"))
        known_bonus = _known_best_bonus(a["name"], task)

        # MCP servers get a small bonus — they're directly usable as tools
        source = (a.get("source") or "").lower()
        mcp_bonus = 5 if ("mcp" in source or "pulsemcp" in source or "mcp" in a["name"].lower()) else 0

        composite = (
            trust * 0.30 +
            cap_match * 0.15 +
            specificity * 0.15 +
            pop * 0.15 +
            recency * 0.10 +
            cost * 0.05 +
            mcp_bonus +
            known_bonus
        )
        a["_composite"] = round(composite, 1)
        a["_cap_match"] = round(cap_match, 1)
        a["_specificity"] = round(specificity, 1)
        scored.append(a)

    scored.sort(key=lambda x: x["_composite"], reverse=True)
    return scored


def _install_instructions(agent: dict) -> dict:
    """Generate install instructions based on source and source_url."""
    name = agent.get("name", "")
    source = agent.get("source", "")
    url = agent.get("source_url", "")
    instructions = {}

    # MCP config (for MCP servers)
    if "mcp" in source.lower() or "mcp" in (agent.get("category") or "").lower():
        # Derive package name from source_url or name
        pkg = name.lower().replace(" ", "-").replace("/", "-")
        if url and "npmjs.com" in url:
            pkg = url.split("/package/")[-1] if "/package/" in url else pkg
        elif url and "pypi.org" in url:
            pkg = url.split("/project/")[-1].rstrip("/") if "/project/" in url else pkg

        instructions["mcp_config"] = {
            "mcpServers": {
                pkg: {
                    "command": "npx",
                    "args": ["-y", pkg]
                }
            }
        }

    # npm install
    if "npm" in source.lower():
        pkg = url.split("/package/")[-1] if url and "/package/" in url else name.lower().replace(" ", "-")
        instructions["npm"] = f"npm install {pkg}"

    # pip install
    if "pypi" in source.lower():
        pkg = url.split("/project/")[-1].rstrip("/") if url and "/project/" in url else name.lower().replace(" ", "-")
        instructions["pip"] = f"pip install {pkg}"

    # GitHub
    if "github" in source.lower() or (url and "github.com" in url):
        repo = url if url and "github.com" in url else f"https://github.com/{name}"
        instructions["github"] = repo
        if "/" in name:
            instructions["git_clone"] = f"git clone {repo}"

    # Docker (for docker hub sources)
    if "docker" in source.lower():
        img = name.lower().replace(" ", "-")
        instructions["docker"] = f"docker pull {img}"

    # API URL
    instructions["nerq_api"] = f"https://nerq.ai/v1/preflight?target={name}"

    return instructions


def _format_recommendation(agent: dict) -> dict:
    """Format a single agent recommendation."""
    return {
        "name": agent["name"],
        "trust_score": agent.get("trust_score"),
        "grade": agent.get("trust_grade"),
        "category": agent.get("category"),
        "source": agent.get("source"),
        "stars": agent.get("stars"),
        "description": (agent.get("description") or "")[:300],
        "verified": agent.get("is_verified", False),
        "author": agent.get("author"),
        "license": agent.get("license"),
        "composite_score": agent.get("_composite"),
        "capability_match": agent.get("_cap_match"),
        "details_url": f"https://nerq.ai/safe/{agent['name'].lower().replace(' ', '-')}",
        "install": _install_instructions(agent),
    }


def _format_alternative(agent: dict) -> dict:
    """Format a brief alternative recommendation."""
    return {
        "name": agent["name"],
        "trust_score": agent.get("trust_score"),
        "grade": agent.get("trust_grade"),
        "composite_score": agent.get("_composite"),
        "tradeoff": _tradeoff_description(agent),
        "details_url": f"https://nerq.ai/safe/{agent['name'].lower().replace(' ', '-')}",
    }


def _tradeoff_description(agent: dict) -> str:
    """One-line tradeoff description for an alternative."""
    parts = []
    trust = agent.get("trust_score") or 0
    stars = agent.get("stars") or 0
    if trust >= 80:
        parts.append("high trust")
    elif trust >= 60:
        parts.append("moderate trust")
    else:
        parts.append("lower trust")
    if stars >= 10000:
        parts.append("very popular")
    elif stars >= 1000:
        parts.append("popular")
    elif stars > 0:
        parts.append("growing community")
    source = agent.get("source", "")
    if "mcp" in source:
        parts.append("MCP server")
    return ", ".join(parts) if parts else "alternative option"


@router_resolve.get("/v1/resolve")
async def resolve_get(
    task: str = Query(..., description="What do you need to do?"),
    min_trust: int = Query(60, description="Minimum trust score (0-100)"),
    client: str = Query(None, description="Client environment (claude, cursor, vscode)"),
    framework: str = Query(None, description="Framework requirement (langchain, crewai, etc.)"),
    limit: int = Query(5, description="Max alternatives to return"),
):
    """Resolve a task description to the best tool recommendation."""
    return _resolve(task, min_trust, client, framework, limit)


@router_resolve.post("/v1/resolve")
async def resolve_post(body: dict):
    """Resolve a task description to the best tool recommendation (POST)."""
    return _resolve(
        task=body.get("task", ""),
        min_trust=body.get("min_trust", 60),
        client=body.get("client"),
        framework=body.get("framework"),
        limit=body.get("limit", 5),
    )


def _resolve(task: str, min_trust: int = 60, client: str = None,
             framework: str = None, limit: int = 5):
    t0 = time.time()

    if not task or len(task.strip()) < 2:
        return JSONResponse({"error": "task parameter required"}, status_code=400)

    # Parse capabilities
    capabilities = _parse_capabilities(task)
    task_keywords = [w for w in re.findall(r'[a-zA-Z0-9_.-]+', task.lower())
                     if w not in {"the", "a", "an", "is", "for", "to", "in", "with", "and",
                                  "or", "my", "i", "need", "want", "find", "best", "use",
                                  "can", "how", "do", "get", "make", "help", "me"} and len(w) > 1]

    # Search database — try progressively broader queries
    queries = _build_search_queries(task, capabilities)

    session = get_session()
    rows = []
    try:
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        seen_names = set()
        for query_str, params in queries:
            try:
                batch = session.execute(text(query_str), params).fetchall()
                for r in batch:
                    if r[0] not in seen_names:
                        rows.append(r)
                        seen_names.add(r[0])
                # Stop if we have enough good candidates
                if len(rows) >= 20:
                    break
            except Exception:
                continue
    finally:
        session.close()

    # Convert to dicts
    agents = []
    for r in rows:
        agents.append({
            "name": r[0], "trust_score": float(r[1]) if r[1] else None,
            "trust_grade": r[2], "category": r[3], "source": r[4],
            "stars": r[5], "downloads": r[6], "description": r[7],
            "source_url": r[8], "last_source_update": r[9],
            "frameworks": r[10], "protocols": r[11], "license": r[12],
            "pricing": r[13], "is_verified": r[14], "author": r[15],
        })

    # Filter by framework if specified
    if framework:
        fw_lower = framework.lower()
        framework_filtered = [a for a in agents if fw_lower in str(a.get("frameworks", "") or "").lower()]
        if framework_filtered:
            agents = framework_filtered

    # Rank
    ranked = _rank_agents(agents, capabilities, task_keywords, min_trust, task)

    elapsed = round((time.time() - t0) * 1000, 1)

    if not ranked:
        return {
            "task": task,
            "capabilities_detected": capabilities,
            "recommendation": None,
            "alternatives": [],
            "total_candidates": 0,
            "response_time_ms": elapsed,
        }

    top = ranked[0]
    alts = ranked[1:limit + 1] if len(ranked) > 1 else []

    return {
        "task": task,
        "capabilities_detected": capabilities,
        "recommendation": _format_recommendation(top),
        "alternatives": [_format_alternative(a) for a in alts],
        "total_candidates": len(ranked),
        "response_time_ms": elapsed,
    }
