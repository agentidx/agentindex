#!/usr/bin/env python3
"""
Migration script: Build initial missionary_state.json from existing data.
"""

import json
import os
from datetime import datetime

BASE = os.path.expanduser("~/agentindex")

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            print(f"  Warning: Could not load {path}: {e}")
    return []

def main():
    print("=== Missionary State Migration ===\n")

    queue = load_json(os.path.join(BASE, "action_queue.json"))
    history = load_json(os.path.join(BASE, "action_history.json"))
    pr_state = load_json(os.path.join(BASE, "pr_bot_state.json"))
    if isinstance(pr_state, dict):
        pr_state_repos = pr_state
    else:
        pr_state_repos = {}

    all_actions = queue + history
    print(f"  Queue: {len(queue)} actions")
    print(f"  History: {len(history)} actions")
    print(f"  PR bot state: {len(pr_state_repos)} repos\n")

    awesome_lists = {
        "punkpeye/awesome-mcp-servers": {"name": "Awesome MCP Servers", "stars": 30000, "pr_status": "submitted"},
        "e2b-dev/awesome-ai-agents": {"name": "Awesome AI Agents", "stars": 10000, "pr_status": "submitted"},
        "kyrolabs/awesome-langchain": {"name": "Awesome LangChain", "stars": 7000, "pr_status": "blocked"},
        "f/awesome-chatgpt-prompts": {"name": "Awesome ChatGPT Prompts", "stars": 100000, "pr_status": "not_relevant"},
        "Shubhamsaboo/awesome-llm-apps": {"name": "Awesome LLM Apps", "stars": 5000, "pr_status": "not_submitted"},
        "filipecalegario/awesome-generative-ai": {"name": "Awesome Generative AI", "stars": 5000, "pr_status": "not_submitted"},
        "aimerou/awesome-ai-papers": {"name": "Awesome AI Papers", "stars": 3000, "pr_status": "not_relevant"},
        "mahseema/awesome-ai-tools": {"name": "Awesome AI Tools", "stars": 3000, "pr_status": "not_submitted"},
        "appcypher/awesome-mcp-servers": {"name": "Awesome MCP Servers (appcypher)", "stars": 5100, "pr_status": "submitted"},
        "kaushikb11/awesome-llm-agents": {"name": "Awesome LLM Agents", "stars": 1300, "pr_status": "submitted"},
        "Arindam200/awesome-ai-apps": {"name": "Awesome AI Apps", "stars": 8900, "pr_status": "submitted"},
        "sickn33/antigravity-awesome-skills": {"name": "Antigravity Awesome Skills", "stars": 8700, "pr_status": "submitted"},
    }

    for a in all_actions:
        if a.get("type") == "add_awesome_list" and a.get("status") in ("executed", "approved", "done"):
            repo = a.get("details", {}).get("repo", "")
            if repo and repo not in awesome_lists:
                awesome_lists[repo] = {
                    "name": a.get("details", {}).get("name", repo.split("/")[-1]),
                    "stars": a.get("details", {}).get("stars", 0),
                    "pr_status": "not_submitted",
                    "tracked_at": a.get("created", ""),
                }
                print(f"  + Awesome list from history: {repo}")

    for repo, info in pr_state_repos.items():
        if repo in awesome_lists:
            if info.get("pr_url") or info.get("status") in ("submitted", "merged", "open"):
                awesome_lists[repo]["pr_status"] = "submitted"

    registries = {
        "smithery": {"name": "Smithery", "url": "https://smithery.ai/server/agentidx/agentcrawl", "status": "listed"},
        "mcphub": {"name": "MCP Hub", "url": "https://mcphub.io", "status": "not_registered"},
        "glama": {"name": "Glama", "url": "https://glama.ai/mcp/servers", "status": "not_registered"},
        "pulsemcp": {"name": "PulseMCP", "url": "https://pulsemcp.com", "status": "not_registered"},
        "mcp.run": {"name": "mcp.run", "url": "https://mcp.run", "status": "not_registered"},
        "composio": {"name": "Composio MCP", "url": "https://composio.dev/mcp", "status": "not_registered"},
    }

    for a in all_actions:
        if a.get("type") == "register_registry" and a.get("status") in ("executed",):
            name = a.get("details", {}).get("name", "")
            key = name.lower().replace(" ", "")
            if key in registries:
                result = a.get("result", "")
                if "Issue created" in result:
                    registries[key]["status"] = "pending"
                    print(f"  + Registry from history: {key} -> pending")

    terms_suggested = []
    for a in all_actions:
        if a.get("type") == "add_search_term":
            term = a.get("details", {}).get("term", "")
            if term and term not in terms_suggested:
                terms_suggested.append(term)

    competitors_seen = []
    for a in all_actions:
        if a.get("type") in ("new_competitor", "spy_new_competitor"):
            url = a.get("details", {}).get("url", "")
            if "github.com/" in url:
                repo = "/".join(url.replace("https://github.com/", "").split("/")[:2])
                if repo not in competitors_seen:
                    competitors_seen.append(repo)

    state = {
        "awesome_lists": awesome_lists,
        "registries": registries,
        "discovered_channels": {},
        "search_terms_suggested": terms_suggested,
        "competitors_seen": competitors_seen,
        "endpoints_alerted": {},
        "last_run": None,
        "migrated_at": datetime.utcnow().isoformat(),
        "migrated_from": {
            "queue_size": len(queue),
            "history_size": len(history),
            "pr_state_size": len(pr_state_repos),
        },
    }

    state_path = os.path.join(BASE, "missionary_state.json")
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2, default=str)

    print(f"\n=== State saved to {state_path} ===")
    print(f"  Awesome lists: {len(awesome_lists)}")
    print(f"  Registries: {len(registries)}")
    print(f"  Search terms already suggested: {len(terms_suggested)}")
    print(f"  Competitors already seen: {len(competitors_seen)}")

    stale_count = 0
    cleaned_queue = []
    for a in queue:
        if a.get("status") == "pending" and a.get("level") in ("auto", "notify"):
            created = a.get("created", "")
            if created and created < (datetime.utcnow().replace(hour=0, minute=0, second=0)).isoformat():
                stale_count += 1
                continue
        cleaned_queue.append(a)

    if stale_count > 0:
        queue_path = os.path.join(BASE, "action_queue.json")
        with open(queue_path, "w") as f:
            json.dump(cleaned_queue, f, indent=2, default=str)
        print(f"  Cleaned {stale_count} stale auto/notify actions from queue")

if __name__ == "__main__":
    main()
