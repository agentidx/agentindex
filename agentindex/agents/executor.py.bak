"""
Action Executor

Runs approved actions from the action queue.
Called periodically by the orchestrator.
"""

import logging
import os
import re
import httpx

from agentindex.agents.action_queue import (
    get_approved_actions, mark_executed, ActionLevel
)

logger = logging.getLogger("agentindex.executor")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


class Executor:
    def __init__(self):
        self.client = httpx.Client(timeout=30)
        self.github_headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }

    def run_approved(self) -> dict:
        """Execute all approved actions."""
        approved = get_approved_actions()
        stats = {"executed": 0, "failed": 0}

        for action in approved:
            try:
                result = self._execute(action)
                mark_executed(action["id"], result=result or "success")
                stats["executed"] += 1
                logger.info(f"Executed: {action['title']} -> {result}")
            except Exception as e:
                mark_executed(action["id"], result=f"error: {e}")
                stats["failed"] += 1
                logger.error(f"Failed: {action['title']} -> {e}")

        return stats

    def _execute(self, action: dict) -> str:
        """Route action to appropriate handler."""
        handlers = {
            "update_agent_md": self._update_agent_md,
            "add_search_term": self._add_search_term,
            "submit_pr": self._submit_pr,
            "register_registry": self._register_registry,
            "add_awesome_list": self._add_awesome_list,
            "spy_implement_feature": self._spy_implement_feature,
            "new_competitor": self._acknowledge,
            "spy_new_competitor": self._acknowledge,
            "spy_improve_visibility": self._acknowledge,
            "spy_competitor_active": self._acknowledge,
            "spy_daily_summary": self._acknowledge,
            "spy_a2a_outreach": self._acknowledge,
            "spy_feature_done": self._acknowledge,
            "spy_feature_reminder": self._acknowledge,
            "endpoint_down": self._acknowledge,
        }

        handler = handlers.get(action["type"])
        if handler:
            return handler(action["details"])
        return f"no handler for {action['type']}"

    def _update_agent_md(self, details: dict) -> str:
        agent_md = os.path.expanduser("~/agentindex/agent.md")
        if not os.path.exists(agent_md):
            return "agent.md not found"
        with open(agent_md) as f:
            content = f.read()
        total = details.get("total", 0)
        if total:
            content = re.sub(
                r'description:.*',
                f'description: Discovery service for AI agents. {total:,}+ agents indexed.',
                content, count=1
            )
            with open(agent_md, "w") as f:
                f.write(content)
        return f"updated with {total:,} agents"

    def _add_search_term(self, details: dict) -> str:
        term = details.get("term", "")
        if not term:
            return "no term provided"
        # For now, just log it — manual addition to spider
        logger.info(f"New search term suggested: {term}")
        return f"logged term: {term}"

    def _submit_pr(self, details: dict) -> str:
        """Submit PR via pr_bot."""
        from agentindex.agents.pr_bot import submit_prs
        result = submit_prs()
        return f"PR bot: {result}"

    def _register_registry(self, details: dict) -> str:
        """Auto-register on MCP registries where possible."""
        registry = details.get("registry", details.get("name", ""))
        url = details.get("url", "")
        
        # Registries that accept GitHub-based submissions
        github_registries = {
            "mcphub": "mcphub-io/mcphub",
            "glama": None,
            "pulsemcp": None,
            "mcp.run": None,
            "composio": None,
        }
        
        repo = github_registries.get(registry)
        if repo:
            # Submit via GitHub Issue
            try:
                token = os.getenv("GITHUB_TOKEN")
                headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
                resp = self.client.post(
                    f"https://api.github.com/repos/{repo}/issues",
                    headers=headers,
                    json={
                        "title": "Add AgentIndex - AI agent discovery MCP server",
                        "body": (
                            "**Name:** AgentIndex\n"
                            "**URL:** https://github.com/agentidx/agentindex\n"
                            "**Smithery:** https://smithery.ai/server/agentidx/agentcrawl\n"
                            "**Description:** Discovery service for 36,000+ AI agents. "
                            "Find agents by capability via MCP, REST API, or A2A protocol.\n\n"
                            "**Install:** `pip install agentcrawl`\n"
                            "**PyPI:** https://pypi.org/project/agentcrawl/"
                        ),
                        "labels": ["submission"],
                    },
                    timeout=15,
                )
                if resp.status_code == 201:
                    return f"Issue created on {repo}: {resp.json()['html_url']}"
                return f"Issue failed on {repo}: {resp.status_code}"
            except Exception as e:
                return f"Issue failed: {e}"
        
        return f"Registry {registry} ({url}) requires manual submission — no API available"

    def _add_awesome_list(self, details: dict) -> str:
        """Track awesome list and submit PR if not already submitted."""
        from agentindex.agents.pr_bot import submit_prs
        result = submit_prs()
        return f"Awesome list PR bot: {result}"


    def _acknowledge(self, details: dict) -> str:
        """Acknowledge notify-only actions — no execution needed."""
        return "acknowledged"

    def _spy_implement_feature(self, details: dict) -> str:
        """Log approved feature implementation to prioritized backlog."""
        feature = details.get("feature", "unknown")
        backlog_path = os.path.expanduser("~/agentindex/spionen_backlog.json")
        import json
        from datetime import datetime
        backlog = []
        if os.path.exists(backlog_path):
            try:
                with open(backlog_path) as f:
                    backlog = json.load(f)
            except Exception:
                pass
        # Check for duplicates
        if not any(b["feature"] == feature for b in backlog):
            backlog.append({
                "feature": feature,
                "approved_at": datetime.utcnow().isoformat(),
                "approach": details.get("approach", ""),
                "effort": details.get("effort", ""),
                "impact": details.get("impact", ""),
                "competitor": details.get("competitor", ""),
                "status": "approved",
            })
            with open(backlog_path, "w") as f:
                json.dump(backlog, f, indent=2)
            logger.info(f"Feature added to backlog: {feature}")
        return f"Feature '{feature}' added to implementation backlog"


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    executor = Executor()
    stats = executor.run_approved()
    print(f"Executed: {stats}")
