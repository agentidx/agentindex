#!/usr/bin/env python3
"""
Expanded Badge Outreach Discovery (C1)
========================================
Runs weekly on Sundays at 09:00 via LaunchAgent com.nerq.badge-discovery.
Discovers new GitHub repos matching AI agent/MCP keywords, cross-references
against our Postgres agent database and existing outreach targets/log,
then adds qualifying repos to badge_outreach_targets.json.

Exit 0 on success.
"""

import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LOG_PATH = "/tmp/badge-discovery.log"
SCRIPT_DIR = Path(__file__).parent
TARGETS_FILE = SCRIPT_DIR / "badge_outreach_targets.json"
LOG_FILE = SCRIPT_DIR / "badge_outreach_log.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("badge-discovery")

# Load env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API = "https://api.github.com"
SEARCH_QUERIES = [
    "mcp-server",
    "ai-agent",
    "langchain",
    "crewai",
    "autogen",
]
MIN_STARS = 50
LOOKBACK_DAYS = 30
MAX_RESULTS_PER_QUERY = 100  # GitHub search max per page


def github_get(url: str, params: dict | None = None) -> dict | None:
    """Make an authenticated GitHub API GET request."""
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN not set")
        return None

    if params:
        query_str = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query_str}"

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "NerqBadgeDiscovery/1.0")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            # Check rate limit
            remaining = resp.headers.get("X-RateLimit-Remaining", "?")
            logger.debug("Rate limit remaining: %s", remaining)
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            logger.warning("GitHub API rate limited. Remaining: %s",
                           e.headers.get("X-RateLimit-Remaining", "?"))
        else:
            logger.warning("GitHub API error %d: %s", e.code, e.reason)
        return None
    except Exception as e:
        logger.warning("GitHub API call failed: %s", e)
        return None


def search_github_repos() -> list[dict]:
    """Search GitHub for repos matching our target keywords."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    all_repos = {}

    for query in SEARCH_QUERIES:
        # Search in description, stars >= MIN_STARS, pushed in last 30 days
        q = f"{query} in:description stars:>={MIN_STARS} pushed:>={cutoff}"
        logger.info("Searching: %s", q)

        data = github_get(f"{GITHUB_API}/search/repositories", {
            "q": urllib.request.quote(q),
            "sort": "stars",
            "order": "desc",
            "per_page": str(MAX_RESULTS_PER_QUERY),
        })

        if not data or "items" not in data:
            logger.warning("No results for query: %s", query)
            continue

        items = data["items"]
        logger.info("  Found %d repos (total_count=%d)", len(items), data.get("total_count", 0))

        for item in items:
            full_name = item.get("full_name", "")
            if full_name and full_name not in all_repos:
                all_repos[full_name] = {
                    "full_name": full_name,
                    "name": item.get("name", ""),
                    "description": item.get("description", ""),
                    "stars": item.get("stargazers_count", 0),
                    "language": item.get("language"),
                    "url": item.get("html_url", ""),
                    "owner": item.get("owner", {}).get("login", ""),
                    "updated_at": item.get("updated_at"),
                    "created_at": item.get("created_at"),
                    "topics": item.get("topics", []),
                }

        # Rate limit: 1 second between searches (10 req/min for search API)
        time.sleep(1.5)

    logger.info("Total unique repos found: %d", len(all_repos))
    return list(all_repos.values())


def cross_reference_agents(repos: list[dict]) -> list[dict]:
    """Cross-reference discovered repos against our Postgres agent database.
    Only return repos that we have indexed with trust_score >= 70.
    Uses psycopg2 directly (no SQLAlchemy dependency)."""
    import psycopg2

    db_url = os.getenv("DATABASE_URL", "postgresql://localhost/agentindex")
    try:
        conn = psycopg2.connect(db_url)
        conn.set_session(readonly=True)
        cur = conn.cursor()
    except Exception as e:
        logger.warning("Cannot connect to Postgres: %s. Skipping DB filter.", e)
        return repos

    qualified = []
    for repo in repos:
        full_name = repo["full_name"]

        try:
            cur.execute("""
                SELECT id::text, name, trust_score, trust_explanation, category,
                       activity_score, security_score, popularity_score, documentation_score
                FROM agents
                WHERE source_url ILIKE %s
                  AND trust_score >= 70
                  AND is_active = true
                LIMIT 1
            """, (f"%{full_name}%",))

            row = cur.fetchone()
            if row:
                agent_id, name, trust_score, trust_expl, category, \
                    activity, security, popularity, documentation = row

                repo["agent_id"] = agent_id
                repo["trust_score"] = trust_score
                repo["trust_explanation"] = trust_expl
                repo["category"] = category or "general"
                repo["agent_name"] = name

                signals = []
                if activity:
                    signals.append(f"activity: {activity * 100:.0f}/100")
                if security:
                    signals.append(f"recency: {security * 100:.0f}/100")
                if popularity:
                    signals.append(f"community: {popularity * 100:.0f}/100")
                if documentation:
                    signals.append(f"documentation: {documentation * 100:.0f}/100")
                repo["trust_signals"] = signals

                qualified.append(repo)

        except Exception as e:
            logger.debug("DB query error for %s: %s", full_name, e)

    try:
        cur.close()
        conn.close()
    except Exception:
        pass

    logger.info("Qualified repos (in DB, trust >= 70): %d / %d", len(qualified), len(repos))
    return qualified


def load_existing() -> tuple[list[dict], dict]:
    """Load existing targets and outreach log."""
    targets = []
    if TARGETS_FILE.exists():
        try:
            with open(TARGETS_FILE) as f:
                targets = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    log_data = {"contacted": {}, "runs": []}
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE) as f:
                log_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    return targets, log_data


def main():
    t0 = time.time()
    now = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("Badge Outreach Discovery started at %s", now.isoformat())

    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN not set in environment")
        return 1

    # Load existing data
    existing_targets, outreach_log = load_existing()
    existing_slugs = {t.get("repo_slug", "") for t in existing_targets}
    contacted_slugs = set(outreach_log.get("contacted", {}).keys())
    skip_slugs = existing_slugs | contacted_slugs
    logger.info("Existing targets: %d, Contacted: %d, Skip set: %d",
                len(existing_targets), len(contacted_slugs), len(skip_slugs))

    # Search GitHub
    repos = search_github_repos()

    # Filter already known
    new_repos = [r for r in repos if r["full_name"] not in skip_slugs]
    logger.info("After filtering already-known: %d new repos", len(new_repos))

    if not new_repos:
        logger.info("No new repos to process")
        elapsed = time.time() - t0
        logger.info("Elapsed: %.1fs", elapsed)
        return 0

    # Cross-reference against our agent database
    qualified = cross_reference_agents(new_repos)

    # Convert to target format (matching badge_outreach_auto.py expectations)
    new_targets = []
    for repo in qualified:
        target = {
            "name": repo.get("agent_name") or repo["full_name"],
            "github_url": repo["url"],
            "repo_slug": repo["full_name"],
            "trust_score": repo.get("trust_score", 70),
            "stars": repo["stars"],
            "category": repo.get("category") or "general",
            "author": repo["owner"],
            "badge_url": f"https://nerq.ai/badge/{repo['full_name']}",
            "safe_url": f"https://nerq.ai/kya/{repo['full_name']}",
            "trust_signals": repo.get("trust_signals", []),
            "trust_explanation": repo.get("trust_explanation", ""),
            "discovered_at": now.isoformat(),
            "discovery_source": "github_search",
        }
        new_targets.append(target)

    # Add to existing targets
    if new_targets:
        existing_targets.extend(new_targets)
        with open(TARGETS_FILE, "w") as f:
            json.dump(existing_targets, f, indent=2)
        logger.info("Added %d new targets. Total targets now: %d", len(new_targets), len(existing_targets))
    else:
        logger.info("No new qualifying targets found")

    elapsed = time.time() - t0
    logger.info("-" * 60)
    logger.info("BADGE DISCOVERY COMPLETE")
    logger.info("  GitHub repos found: %d", len(repos))
    logger.info("  New (not seen):     %d", len(new_repos))
    logger.info("  Qualified (DB+70):  %d", len(qualified))
    logger.info("  Added to targets:   %d", len(new_targets))
    logger.info("  Total targets:      %d", len(existing_targets))
    logger.info("  Elapsed:            %.1fs", elapsed)
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
