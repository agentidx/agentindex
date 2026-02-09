"""
AgentIndex MCP Registry Spider

Crawls known MCP (Model Context Protocol) registries and server listings.
MCP servers are the most directly relevant agents for our index —
they are tools designed to be discovered and used by other agents.
"""

import time
import logging
from datetime import datetime
from typing import Optional
import httpx
from agentindex.db.models import Agent, CrawlJob, get_session
from sqlalchemy import select

logger = logging.getLogger("agentindex.spiders.mcp")

# Known MCP registries and listing sources
MCP_SOURCES = [
    {
        "name": "mcp-registry-github",
        "type": "github_topic",
        "url": "https://api.github.com/search/repositories?q=topic:mcp-server&sort=updated&per_page=100",
    },
    {
        "name": "mcp-servers-awesome",
        "type": "github_repo",
        "url": "https://api.github.com/repos/punkpeye/awesome-mcp-servers/contents/README.md",
    },
    {
        "name": "mcp-registry-official",
        "type": "github_repo",
        "url": "https://api.github.com/repos/modelcontextprotocol/servers/contents",
    },
]

# Also search for .well-known/agent.json and .well-known/agent-card.json patterns
A2A_DISCOVERY_PATHS = [
    "/.well-known/agent.json",
    "/.well-known/agent-card.json",
]


class McpSpider:
    """Crawls MCP registries and known server listings."""

    def __init__(self):
        import os
        token = os.getenv("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"
        self.client = httpx.Client(timeout=30, headers=headers)
        self.session = get_session()

    def crawl(self) -> dict:
        stats = {"found": 0, "new": 0, "errors": 0}

        # Crawl GitHub topic: mcp-server
        try:
            result = self._crawl_github_topic()
            stats["found"] += result["found"]
            stats["new"] += result["new"]
            logger.info(f"MCP GitHub topic: found={result['found']}, new={result['new']}")
        except Exception as e:
            self.session.rollback()
            logger.error(f"MCP GitHub topic error: {e}")
            stats["errors"] += 1

        # Crawl official MCP servers repo
        try:
            result = self._crawl_official_servers()
            stats["found"] += result["found"]
            stats["new"] += result["new"]
            logger.info(f"MCP official servers: found={result['found']}, new={result['new']}")
        except Exception as e:
            logger.error(f"MCP official servers error: {e}")
            stats["errors"] += 1

        # Crawl awesome-mcp-servers
        try:
            result = self._crawl_awesome_list()
            stats["found"] += result["found"]
            stats["new"] += result["new"]
            logger.info(f"MCP awesome list: found={result['found']}, new={result['new']}")
        except Exception as e:
            logger.error(f"MCP awesome list error: {e}")
            stats["errors"] += 1

        job = CrawlJob(
            source="mcp",
            query="full_crawl",
            status="completed",
            items_found=stats["found"],
            items_new=stats["new"],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        self.session.add(job)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            from agentindex.db.models import get_session
            self.session = get_session()

        logger.info(f"MCP crawl complete: {stats}")
        return stats

    def _crawl_github_topic(self) -> dict:
        """Crawl repos tagged with mcp-server topic."""
        stats = {"found": 0, "new": 0}

        page = 1
        while page <= 10:  # max 1000 results
            response = self.client.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": "topic:mcp-server",
                    "sort": "updated",
                    "order": "desc",
                    "per_page": 100,
                    "page": page,
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            items = data.get("items", [])

            if not items:
                break

            for repo in items:
                stats["found"] += 1
                result = self._process_github_repo(repo)
                if result == "new":
                    stats["new"] += 1

            page += 1
            time.sleep(2)

        return stats

    def _crawl_official_servers(self) -> dict:
        """Crawl the official modelcontextprotocol/servers repo."""
        stats = {"found": 0, "new": 0}

        response = self.client.get(
            "https://api.github.com/repos/modelcontextprotocol/servers/contents/src"
        )

        if response.status_code != 200:
            return stats

        contents = response.json()

        for item in contents:
            if item.get("type") == "dir":
                stats["found"] += 1
                source_url = f"https://github.com/modelcontextprotocol/servers/tree/main/src/{item['name']}"

                existing = self.session.execute(
                    select(Agent).where(Agent.source_url == source_url)
                ).scalar_one_or_none()

                if not existing:
                    # Get README from subdirectory
                    readme = self._get_subdir_readme(item["name"])

                    agent = Agent(
                        source="mcp",
                        source_url=source_url,
                        source_id=f"mcp-official/{item['name']}",
                        name=item["name"],
                        description=f"Official MCP server: {item['name']}",
                        author="modelcontextprotocol",
                        protocols=["mcp"],
                        invocation={"type": "mcp", "source": "official"},
                        tags=["mcp", "official", "model-context-protocol"],
                        raw_metadata={"readme": readme[:10000] if readme else None, "official": True},
                        crawl_status="indexed",
                        first_indexed=datetime.utcnow(),
                        last_crawled=datetime.utcnow(),
                    )
                    self.session.add(agent)
                    try:
                        self.session.commit()
                    except Exception:
                        self.session.rollback()
                        from agentindex.db.models import get_session
                        self.session = get_session()
                    stats["new"] += 1

        return stats

    def _crawl_awesome_list(self) -> dict:
        """Crawl awesome-mcp-servers for linked repos."""
        stats = {"found": 0, "new": 0}

        response = self.client.get(
            "https://api.github.com/repos/punkpeye/awesome-mcp-servers/contents/README.md"
        )

        if response.status_code != 200:
            return stats

        import base64
        content = base64.b64decode(response.json().get("content", "")).decode("utf-8", errors="ignore")

        # Extract GitHub URLs from the awesome list
        import re
        github_urls = re.findall(r'https://github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+', content)
        seen = set()

        for url in github_urls:
            url = url.rstrip(")")  # clean trailing parens from markdown
            if url in seen:
                continue
            seen.add(url)

            stats["found"] += 1

            existing = self.session.execute(
                select(Agent).where(Agent.source_url == url)
            ).scalar_one_or_none()

            if not existing:
                # Fetch repo info
                parts = url.replace("https://github.com/", "").split("/")
                if len(parts) >= 2:
                    try:
                        repo_response = self.client.get(
                            f"https://api.github.com/repos/{parts[0]}/{parts[1]}"
                        )
                        if repo_response.status_code == 200:
                            repo = repo_response.json()
                            result = self._process_github_repo(repo)
                            if result == "new":
                                stats["new"] += 1
                        time.sleep(0.5)
                    except Exception as e:
                        logger.error(f"Error fetching {url}: {e}")

        return stats

    def _process_github_repo(self, repo: dict) -> str:
        """Process a GitHub repo dict (from API response)."""
        source_url = repo.get("html_url", "")

        existing = self.session.execute(
            select(Agent).where(Agent.source_url == source_url)
        ).scalar_one_or_none()

        if existing:
            return "skipped"

        agent = Agent(
            source="mcp",
            source_url=source_url,
            source_id=repo.get("full_name"),
            name=repo.get("name", ""),
            description=repo.get("description", ""),
            author=repo.get("owner", {}).get("login"),
            language=repo.get("language"),
            stars=repo.get("stargazers_count", 0),
            forks=repo.get("forks_count", 0),
            protocols=["mcp"],
            invocation={"type": "mcp"},
            tags=repo.get("topics", []),
            raw_metadata={
                "full_name": repo.get("full_name"),
                "description": repo.get("description"),
                "topics": repo.get("topics", []),
            },
            crawl_status="indexed",
            first_indexed=datetime.utcnow(),
            last_crawled=datetime.utcnow(),
        )

        self.session.add(agent)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            from agentindex.db.models import get_session
            self.session = get_session()
        return "new"

    def _get_subdir_readme(self, dirname: str) -> Optional[str]:
        try:
            response = self.client.get(
                f"https://api.github.com/repos/modelcontextprotocol/servers/contents/src/{dirname}/README.md"
            )
            if response.status_code == 200:
                import base64
                return base64.b64decode(response.json().get("content", "")).decode("utf-8", errors="ignore")
        except Exception:
            pass
        return None


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    spider = McpSpider()
    stats = spider.crawl()
    print(f"Crawl complete: {stats}")
