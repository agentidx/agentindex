"""
Autonomous PR Bot — submits PRs to awesome-lists via GitHub API.
"""

import os
import time
import base64
import logging
import json
import httpx

logger = logging.getLogger("agentindex.pr_bot")

# Target repos and entries
PR_TARGETS = {
    "e2b-dev/awesome-ai-agents": {
        "section": "## Open Source",
        "entry": "- [AgentIndex](https://github.com/agentidx/agentindex) - Discovery service for AI agents. Indexes 36,000+ agents from GitHub, npm, PyPI, HuggingFace, and MCP registries. Supports A2A protocol and semantic search.",
    },
    "kyrolabs/awesome-langchain": {
        "section": "## Other",
        "entry": "- [AgentIndex](https://github.com/agentidx/agentindex) - AI agent discovery service. Find any agent by capability via REST API, A2A protocol, or MCP. 36,000+ agents indexed.",
    },
    "punkpeye/awesome-mcp-servers": {
        "section": "## Search",
        "entry": "- [AgentIndex](https://github.com/agentidx/agentindex) <a href='https://smithery.ai/server/agentidx/agentcrawl'><img alt='Smithery' src='https://smithery.ai/badge/agentidx/agentcrawl'></a> - Discovery service for 36,000+ AI agents. MCP server, REST API, and A2A protocol support.",
    },
}

STATE_FILE = os.path.expanduser("~/agentindex/pr_bot_state.json")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"submitted": [], "failed": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def check_rate_limit(headers):
    """Return remaining core API calls."""
    try:
        resp = httpx.get("https://api.github.com/rate_limit", headers=headers, timeout=10)
        if resp.status_code == 200:
            remaining = resp.json()["resources"]["core"]["remaining"]
            return remaining
    except Exception:
        pass
    return 0


def submit_prs():
    """Submit PRs to all configured awesome-lists."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN not set")
        return {"submitted": 0, "skipped": 0, "failed": 0}

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Get authenticated user
    try:
        user_resp = httpx.get("https://api.github.com/user", headers=headers, timeout=10)
        gh_user = user_resp.json()["login"]
    except Exception:
        gh_user = "agentidx"
    logger.info(f"GitHub user: {gh_user}")

    # Check rate limit first
    remaining = check_rate_limit(headers)
    if remaining < 50:
        logger.warning(f"GitHub rate limit too low ({remaining}), skipping PR bot")
        return {"submitted": 0, "skipped": len(PR_TARGETS), "failed": 0, "reason": "rate_limit"}

    state = load_state()
    stats = {"submitted": 0, "skipped": 0, "failed": 0}

    for repo, info in PR_TARGETS.items():
        if repo in state["submitted"]:
            logger.info(f"Already submitted PR to {repo}, skipping")
            stats["skipped"] += 1
            continue

        try:
            result = _submit_pr(repo, info, headers, gh_user)
            if result == "created":
                state["submitted"].append(repo)
                stats["submitted"] += 1
            elif result == "exists":
                state["submitted"].append(repo)
                stats["skipped"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            logger.error(f"PR to {repo} failed: {e}")
            stats["failed"] += 1

        time.sleep(3)

    save_state(state)
    return stats


def _submit_pr(repo, info, headers, gh_user="agentidx"):
    """Submit a single PR. Returns 'created', 'exists', or 'failed'."""
    logger.info(f"Processing {repo}...")

    # 1. Check existing PRs
    resp = httpx.get(
        f"https://api.github.com/repos/{repo}/pulls?state=all&per_page=50",
        headers=headers, timeout=15,
    )
    if resp.status_code == 200:
        existing = [p for p in resp.json() if "agentindex" in (p.get("title") or "").lower() or "agentindex" in (p.get("body") or "").lower()]
        if existing:
            logger.info(f"PR already exists for {repo}: {existing[0]['html_url']}")
            return "exists"

    # 2. Fork
    resp = httpx.post(f"https://api.github.com/repos/{repo}/forks", headers=headers, timeout=30)
    if resp.status_code not in (200, 202):
        logger.error(f"Fork failed for {repo}: {resp.status_code}")
        return "failed"
    time.sleep(15)

    # 3. Get fork info
    repo_name = repo.split("/")[-1]
    fork = f"{gh_user}/{repo_name}"
    resp = httpx.get(f"https://api.github.com/repos/{fork}", headers=headers, timeout=15)
    if resp.status_code != 200:
        logger.error(f"Can't access fork {fork}")
        return "failed"
    default_branch = resp.json().get("default_branch", "main")

    # 4. Get README
    resp = httpx.get(f"https://api.github.com/repos/{fork}/contents/README.md", headers=headers, timeout=15)
    if resp.status_code != 200:
        logger.error(f"Can't get README from {fork}")
        return "failed"

    readme_data = resp.json()
    readme_content = base64.b64decode(readme_data["content"]).decode("utf-8")
    sha = readme_data["sha"]

    # 5. Check if already listed
    if "agentindex" in readme_content.lower() or "agentcrawl" in readme_content.lower():
        logger.info(f"Already listed in {repo}")
        return "exists"

    # 6. Insert entry
    section = info["section"]
    entry = info["entry"]
    if section in readme_content:
        idx = readme_content.index(section) + len(section)
        next_nl = readme_content.index("\n", idx)
        new_content = readme_content[:next_nl + 1] + entry + "\n" + readme_content[next_nl + 1:]
    else:
        new_content = readme_content.rstrip() + "\n\n" + entry + "\n"

    # 7. Create branch
    branch = "add-agentindex"
    ref_resp = httpx.get(
        f"https://api.github.com/repos/{fork}/git/ref/heads/{default_branch}",
        headers=headers, timeout=15,
    )
    if ref_resp.status_code != 200:
        return "failed"
    base_sha = ref_resp.json()["object"]["sha"]

    # Delete branch if exists
    httpx.delete(f"https://api.github.com/repos/{fork}/git/refs/heads/{branch}", headers=headers, timeout=10)
    time.sleep(1)

    httpx.post(
        f"https://api.github.com/repos/{fork}/git/refs",
        headers=headers, timeout=15,
        json={"ref": f"refs/heads/{branch}", "sha": base_sha},
    )

    # 8. Update README
    resp = httpx.put(
        f"https://api.github.com/repos/{fork}/contents/README.md",
        headers=headers, timeout=15,
        json={
            "message": "Add AgentIndex - AI agent discovery service",
            "content": base64.b64encode(new_content.encode()).decode(),
            "sha": sha,
            "branch": branch,
        },
    )
    if resp.status_code not in (200, 201):
        logger.error(f"README update failed: {resp.status_code}")
        return "failed"

    # 9. Create PR
    pr_body = (
        "## Add AgentIndex\n\n"
        "[AgentIndex](https://github.com/agentidx/agentindex) is a discovery service for AI agents.\n\n"
        "- **36,000+ agents** indexed from GitHub, npm, PyPI, HuggingFace, and MCP registries\n"
        "- **Semantic search** — find agents by meaning, not just keywords\n"
        "- **A2A protocol** — one of the first live A2A-compatible agents\n"
        "- **REST API + MCP server** — multiple integration options\n\n"
        "Live at: https://api.agentcrawl.dev\n"
    )

    resp = httpx.post(
        f"https://api.github.com/repos/{repo}/pulls",
        headers=headers, timeout=15,
        json={
            "title": "Add AgentIndex - AI agent discovery service (36K+ agents)",
            "body": pr_body,
            "head": f"{gh_user}:{branch}",
            "base": default_branch,
        },
    )
    if resp.status_code == 201:
        pr_url = resp.json()["html_url"]
        logger.info(f"✅ PR created: {pr_url}")
        return "created"
    else:
        logger.error(f"PR creation failed: {resp.status_code} {resp.text[:200]}")
        return "failed"


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.expanduser("~/agentindex/.env"))
    logging.basicConfig(level=logging.INFO)
    result = submit_prs()
    print(f"Result: {result}")
