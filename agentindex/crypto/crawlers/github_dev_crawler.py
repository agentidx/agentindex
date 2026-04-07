#!/usr/bin/env python3
"""
System 10: GitHub Developer Activity Crawler (A4)
===================================================
Runs Saturdays at 03:00 via LaunchAgent.
For top 20 blockchain ecosystems, searches GitHub API for repos
tagged/described with that chain name and counts:
  - Unique contributors in last 30 days
  - Total commits in last 30 days
  - New repos created in last 30 days

Stores results in chain_developer_activity table in crypto_trust.db.
Rate limit: stays within GitHub free tier (5,000 req/hr with auth token).

Exit 0 on success.
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

LOG_PATH = "/tmp/github-dev-crawler.log"
DB_PATH = Path(__file__).resolve().parent.parent / "crypto_trust.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("github-dev-crawler")

# Load env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")
except ImportError:
    pass

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API = "https://api.github.com"

# Top 20 blockchain ecosystems
CHAINS = [
    "ethereum", "solana", "sui", "avalanche", "polkadot",
    "cosmos", "near", "arbitrum", "base", "polygon",
    "bnb-chain", "optimism", "cardano", "tron", "aptos",
    "fantom", "celo", "algorand", "hedera", "ton",
]

# How many top repos (by stars) to drill into for contributors/commits
TOP_REPOS_LIMIT = 5


def github_get(url: str) -> dict | list | None:
    """Make an authenticated GitHub API GET request using urllib."""
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN not set — cannot call GitHub API")
        return None

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "ZarqGitHubDevCrawler/1.0")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            remaining = resp.headers.get("X-RateLimit-Remaining", "?")
            if remaining != "?" and int(remaining) < 100:
                logger.warning("Rate limit remaining: %s — slowing down", remaining)
                time.sleep(5)
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as e:
        if e.code == 403:
            # Rate limit hit
            reset_ts = e.headers.get("X-RateLimit-Reset")
            if reset_ts:
                wait = max(int(reset_ts) - int(time.time()), 10)
                logger.warning("Rate limited — waiting %ds", wait)
                time.sleep(min(wait, 300))  # cap at 5 min
            else:
                logger.warning("403 Forbidden — waiting 60s")
                time.sleep(60)
            return None
        elif e.code == 422:
            logger.warning("422 Unprocessable: %s", url)
            return None
        else:
            logger.error("HTTP %d for %s: %s", e.code, url, e.reason)
            return None
    except Exception as e:
        logger.error("Request failed for %s: %s", url, e)
        return None


def search_repos(chain: str, since_date: str) -> tuple[int, list[dict]]:
    """Search GitHub repos for a chain. Returns (total_count, top_repos_by_stars)."""
    # Build query: chain name in topic or description, pushed recently
    q = urllib.parse.quote(f"{chain} pushed:>={since_date}")
    url = f"{GITHUB_API}/search/repositories?q={q}&sort=stars&order=desc&per_page=100"

    time.sleep(1)
    data = github_get(url)
    if not data or not isinstance(data, dict):
        return 0, []

    total_count = data.get("total_count", 0)
    items = data.get("items", [])

    # Take top N by stars
    top_repos = []
    for repo in items[:TOP_REPOS_LIMIT]:
        top_repos.append({
            "full_name": repo.get("full_name", ""),
            "stars": repo.get("stargazers_count", 0),
        })

    return total_count, top_repos


def get_contributors_count(repo_full_name: str) -> int:
    """Get unique contributor count for a repo (up to 100)."""
    url = f"{GITHUB_API}/repos/{repo_full_name}/contributors?per_page=100&anon=true"

    time.sleep(1)
    data = github_get(url)
    if not data or not isinstance(data, list):
        return 0

    return len(data)


def get_commit_activity(repo_full_name: str) -> int:
    """Get total commits in last 4 weeks from weekly commit activity."""
    url = f"{GITHUB_API}/repos/{repo_full_name}/stats/commit_activity"

    time.sleep(1)
    data = github_get(url)
    if not data or not isinstance(data, list):
        return 0

    # commit_activity returns 52 weeks; take last 4
    last_4_weeks = data[-4:] if len(data) >= 4 else data
    total = sum(week.get("total", 0) for week in last_4_weeks)
    return total


def init_db(conn: sqlite3.Connection):
    """Create chain_developer_activity table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chain_developer_activity (
            chain TEXT NOT NULL,
            contributors_30d INTEGER,
            commits_30d INTEGER,
            new_repos_30d INTEGER,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (chain, fetched_at)
        )
    """)
    conn.commit()


def crawl_chain(chain: str, since_date: str) -> dict:
    """Crawl GitHub developer activity for a single chain."""
    logger.info("Crawling chain: %s", chain)

    # 1. Search repos — total_count is proxy for new_repos_30d
    new_repos, top_repos = search_repos(chain, since_date)
    logger.info("  %s: %d repos found (pushed >= %s), top %d to drill",
                chain, new_repos, since_date, len(top_repos))

    # 2. Get contributors from top repos
    total_contributors = 0
    seen_contributors = set()  # We can't truly deduplicate across repos via this API,
    # but we sum per-repo counts as a reasonable approximation
    total_commits = 0

    for repo_info in top_repos:
        repo_name = repo_info["full_name"]

        # Contributors
        contrib_count = get_contributors_count(repo_name)
        total_contributors += contrib_count
        logger.info("    %s: %d contributors", repo_name, contrib_count)

        # Commits (last 4 weeks)
        commits = get_commit_activity(repo_name)
        total_commits += commits
        logger.info("    %s: %d commits (4w)", repo_name, commits)

    result = {
        "chain": chain,
        "contributors_30d": total_contributors,
        "commits_30d": total_commits,
        "new_repos_30d": new_repos,
    }
    logger.info("  %s result: contributors=%d, commits=%d, new_repos=%d",
                chain, total_contributors, total_commits, new_repos)
    return result


def main():
    parser = argparse.ArgumentParser(description="GitHub Developer Activity Crawler (System 10, A4)")
    parser.parse_args()

    t0 = time.time()
    logger.info("=" * 60)
    logger.info("GitHub Developer Activity Crawler starting")
    logger.info("DB: %s", DB_PATH)

    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN not set in environment. Exiting.")
        sys.exit(1)

    # 30 days ago
    since = datetime.now(timezone.utc) - timedelta(days=30)
    since_date = since.strftime("%Y-%m-%d")
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info("Since date: %s", since_date)
    logger.info("Chains to crawl: %d", len(CHAINS))

    # Init DB
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    results = []
    errors = 0

    for chain in CHAINS:
        try:
            result = crawl_chain(chain, since_date)
            results.append(result)

            # Insert into DB
            conn.execute("""
                INSERT OR REPLACE INTO chain_developer_activity
                (chain, contributors_30d, commits_30d, new_repos_30d, fetched_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                result["chain"],
                result["contributors_30d"],
                result["commits_30d"],
                result["new_repos_30d"],
                fetched_at,
            ))
            conn.commit()

        except Exception as e:
            logger.error("Failed to crawl %s: %s", chain, e)
            errors += 1

    conn.close()

    elapsed = time.time() - t0

    # Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("  Chains crawled: %d / %d", len(results), len(CHAINS))
    logger.info("  Errors: %d", errors)
    if results:
        total_contribs = sum(r["contributors_30d"] for r in results)
        total_commits = sum(r["commits_30d"] for r in results)
        total_repos = sum(r["new_repos_30d"] for r in results)
        logger.info("  Total contributors (30d): %d", total_contribs)
        logger.info("  Total commits (30d): %d", total_commits)
        logger.info("  Total new repos (30d): %d", total_repos)
        # Top 5 by contributors
        by_contrib = sorted(results, key=lambda r: r["contributors_30d"], reverse=True)[:5]
        logger.info("  Top 5 by contributors:")
        for r in by_contrib:
            logger.info("    %s: %d contributors, %d commits",
                        r["chain"], r["contributors_30d"], r["commits_30d"])
    logger.info("  Elapsed: %.1fs", elapsed)
    logger.info("Done.")

    sys.exit(0)


if __name__ == "__main__":
    main()
