"""
Launch Day Coverage
===================
Checks GitHub trending repos tagged with "agent", "mcp", or "ai",
determines if they already have /safe/ pages on nerq.ai, and logs
any new tools that need coverage.

Runs every 6 hours via LaunchAgent.

Usage:
    python -m agentindex.intelligence.launch_day_coverage
"""

import json
import os
import sqlite3
import shutil
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # agentindex repo root
AGENTS_DB = BASE_DIR / "agents.db"
TMP_DB = Path("/tmp/launch_coverage_agents.db")
OUTPUT_PATH = BASE_DIR / "data" / "launch_coverage_gaps.json"
GITHUB_API = "https://api.github.com"

# Keywords to search for in trending/recent repos
KEYWORDS = ["agent", "mcp", "ai-agent", "ai-tool", "llm-agent"]


def get_github_token():
    """Try to get GitHub token from environment."""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def search_github_repos(keyword, token=None):
    """Search GitHub for recently created repos with the given keyword/topic."""
    url = (
        f"{GITHUB_API}/search/repositories"
        f"?q={keyword}+in:topics+created:>2026-03-01"
        f"&sort=stars&order=desc&per_page=20"
    )

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data.get("items", [])
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"[WARN] GitHub rate limited for keyword '{keyword}'")
        else:
            print(f"[WARN] GitHub API error {e.code} for keyword '{keyword}'")
        return []
    except Exception as e:
        print(f"[WARN] GitHub search failed for '{keyword}': {e}")
        return []


def get_existing_agents():
    """Get set of known agent names/repos from our DB."""
    if not AGENTS_DB.exists():
        print(f"[WARN] Agents DB not found: {AGENTS_DB}")
        return set()

    shutil.copy2(AGENTS_DB, TMP_DB)
    conn = sqlite3.connect(str(TMP_DB))
    try:
        # Try to get source_url or name fields
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        known = set()
        if "agents" in tables:
            rows = conn.execute("SELECT name, source_url FROM agents").fetchall()
            for name, url in rows:
                if name:
                    known.add(name.lower())
                if url:
                    # Extract repo path from GitHub URL
                    if "github.com" in (url or ""):
                        parts = url.rstrip("/").split("github.com/")
                        if len(parts) > 1:
                            known.add(parts[1].lower())
        return known
    except Exception as e:
        print(f"[WARN] Error reading agents DB: {e}")
        return set()
    finally:
        conn.close()


def main():
    print(f"=== Launch Day Coverage Check — {datetime.now().isoformat()} ===")

    token = get_github_token()
    if not token:
        print("[INFO] No GITHUB_TOKEN set — will use unauthenticated requests (lower rate limits)")

    existing = get_existing_agents()
    print(f"[INFO] Known agents/repos in DB: {len(existing)}")

    all_repos = {}
    for kw in KEYWORDS:
        repos = search_github_repos(kw, token)
        for repo in repos:
            full_name = repo.get("full_name", "")
            if full_name and full_name not in all_repos:
                all_repos[full_name] = repo
        print(f"[INFO] Keyword '{kw}': found {len(repos)} repos")

    # Find gaps: repos we don't cover yet
    gaps = []
    for full_name, repo in all_repos.items():
        name_lower = full_name.lower()
        repo_name_lower = repo.get("name", "").lower()

        if name_lower not in existing and repo_name_lower not in existing:
            gaps.append({
                "repo": full_name,
                "url": repo.get("html_url", ""),
                "description": (repo.get("description") or "")[:200],
                "stars": repo.get("stargazers_count", 0),
                "created_at": repo.get("created_at", ""),
                "topics": repo.get("topics", []),
            })

    # Sort by stars descending
    gaps.sort(key=lambda x: x["stars"], reverse=True)

    print(f"\n{'='*60}")
    print(f"COVERAGE GAPS: {len(gaps)} new repos need /safe/ pages")
    print(f"{'='*60}")
    for g in gaps[:20]:
        print(f"  * {g['repo']} ({g['stars']} stars)")
        if g["description"]:
            print(f"    {g['description'][:100]}")

    # Save results
    output = {
        "checked_at": datetime.now().isoformat(),
        "total_repos_found": len(all_repos),
        "coverage_gaps": len(gaps),
        "gaps": gaps[:50],  # Top 50
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\n[OK] Saved {len(gaps)} gaps to {OUTPUT_PATH}")

    # Cleanup
    if TMP_DB.exists():
        TMP_DB.unlink()


if __name__ == "__main__":
    main()
