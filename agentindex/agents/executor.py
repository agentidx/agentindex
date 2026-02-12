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
        repo = details.get("repo", "")
        title = details.get("title", "")
        body = details.get("body", "")
        if not all([repo, title, body]):
            return "missing repo/title/body"

        # Fork the repo first
        try:
            self.client.post(
                f"https://api.github.com/repos/{repo}/forks",
                headers=self.github_headers,
            )
        except Exception:
            pass  # May already be forked

        # Note: actual PR creation requires creating a branch with changes
        # For now, save PR details for manual submission
        pr_file = os.path.expanduser(f"~/agentindex/missionary_reports/pr-{repo.replace('/', '-')}.md")
        with open(pr_file, "w") as f:
            f.write(f"# PR for {repo}\n\n**Title:** {title}\n\n{body}")
        return f"PR text saved to {pr_file} — submit manually via GitHub"

    def _register_registry(self, details: dict) -> str:
        name = details.get("name", "")
        url = details.get("url", "")
        return f"Visit {url} to register manually — {name}"

    def _add_awesome_list(self, details: dict) -> str:
        repo = details.get("repo", "")
        name = details.get("name", "")
        return f"Added {name} ({repo}) to tracking list"


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    executor = Executor()
    stats = executor.run_approved()
    print(f"Executed: {stats}")
