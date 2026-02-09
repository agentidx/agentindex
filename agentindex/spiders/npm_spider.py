"""
AgentIndex npm Spider

Crawls the npm registry for AI agent packages.
npm has a public API that requires no authentication.
"""

import time
import logging
from datetime import datetime
from typing import Optional
import httpx
from agentindex.db.models import Agent, CrawlJob, get_session
from sqlalchemy import select

logger = logging.getLogger("agentindex.spiders.npm")

# Search queries for finding agent packages on npm
SEARCH_QUERIES = [
    "ai-agent",
    "llm-agent",
    "mcp-server",
    "model-context-protocol",
    "autonomous-agent",
    "agent-framework",
    "langchain-agent",
    "openai-agent",
    "anthropic-agent",
    "ai-assistant",
    "agent2agent",
    "a2a-protocol",
    "ai-tool",
    "agent-tool",
    "crewai",
    "autogen",
    "multi-agent",
    "agent-orchestration",
    "chatbot-agent",
    "agent-sdk",
]

NPM_SEARCH_URL = "https://registry.npmjs.org/-/v1/search"
NPM_PACKAGE_URL = "https://registry.npmjs.org"


class NpmSpider:
    """Crawls npm registry for AI agent packages."""

    def __init__(self):
        self.client = httpx.Client(timeout=30)
        self.session = get_session()

    def crawl(self, max_results_per_query: int = 250) -> dict:
        stats = {"queries_run": 0, "packages_found": 0, "new": 0, "updated": 0, "errors": 0}

        for query in SEARCH_QUERIES:
            try:
                query_stats = self._crawl_query(query, max_results_per_query)
                stats["queries_run"] += 1
                stats["packages_found"] += query_stats["found"]
                stats["new"] += query_stats["new"]
                stats["updated"] += query_stats["updated"]

                logger.info(f"npm query '{query}': found={query_stats['found']}, new={query_stats['new']}")
                time.sleep(1)  # respectful pause

            except Exception as e:
                self.session.rollback()
                logger.error(f"Error crawling npm query '{query}': {e}")
                stats["errors"] += 1

        job = CrawlJob(
            source="npm",
            query="full_crawl",
            status="completed",
            items_found=stats["packages_found"],
            items_new=stats["new"],
            items_updated=stats["updated"],
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

        logger.info(f"npm crawl complete: {stats}")
        return stats

    def _crawl_query(self, query: str, max_results: int) -> dict:
        stats = {"found": 0, "new": 0, "updated": 0}
        offset = 0
        page_size = 250  # npm max

        while offset < max_results:
            response = self.client.get(
                NPM_SEARCH_URL,
                params={
                    "text": query,
                    "size": min(page_size, max_results - offset),
                    "from": offset,
                }
            )

            if response.status_code != 200:
                logger.warning(f"npm search returned {response.status_code}")
                break

            data = response.json()
            objects = data.get("objects", [])

            if not objects:
                break

            for obj in objects:
                stats["found"] += 1
                try:
                    result = self._process_package(obj)
                    if result == "new":
                        stats["new"] += 1
                    elif result == "updated":
                        stats["updated"] += 1
                except Exception as e:
                    logger.error(f"Error processing npm package: {e}")

            offset += len(objects)

            if len(objects) < page_size:
                break

        return stats

    def _process_package(self, obj: dict) -> str:
        package = obj.get("package", {})
        name = package.get("name", "")
        source_url = f"https://www.npmjs.com/package/{name}"

        existing = self.session.execute(
            select(Agent).where(Agent.source_url == source_url)
        ).scalar_one_or_none()

        if existing:
            return "skipped"

        # Get full package details
        readme = self._get_readme(name)

        # Extract metadata
        links = package.get("links", {})
        publisher = package.get("publisher", {})

        raw_metadata = {
            "readme": readme[:10000] if readme else None,
            "description": package.get("description"),
            "keywords": package.get("keywords", []),
            "version": package.get("version"),
            "homepage": links.get("homepage"),
            "repository": links.get("repository"),
            "npm_url": links.get("npm"),
        }

        # Detect frameworks and protocols
        text_blob = " ".join([
            package.get("description") or "",
            " ".join(package.get("keywords") or []),
            readme[:3000] if readme else "",
        ]).lower()

        frameworks = []
        if "langchain" in text_blob: frameworks.append("langchain")
        if "crewai" in text_blob: frameworks.append("crewai")
        if "openai" in text_blob: frameworks.append("openai")
        if "anthropic" in text_blob: frameworks.append("anthropic")
        if "mcp" in text_blob or "model-context-protocol" in text_blob: frameworks.append("mcp")

        protocols = []
        if "mcp" in text_blob: protocols.append("mcp")
        if "a2a" in text_blob or "agent2agent" in text_blob: protocols.append("a2a")
        if "rest" in text_blob or "api" in text_blob: protocols.append("rest")

        agent = Agent(
            source="npm",
            source_url=source_url,
            source_id=name,
            name=name,
            description=package.get("description", ""),
            author=publisher.get("username"),
            language="JavaScript",
            frameworks=frameworks,
            protocols=protocols,
            invocation={"type": "npm", "install": f"npm install {name}"},
            tags=package.get("keywords", []),
            raw_metadata=raw_metadata,
            crawl_status="indexed",
            first_indexed=datetime.utcnow(),
            last_crawled=datetime.utcnow(),
        )

        # Try to get download count as popularity signal
        downloads = self._get_weekly_downloads(name)
        if downloads:
            agent.downloads = downloads

        self.session.add(agent)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            from agentindex.db.models import get_session
            self.session = get_session()
        return "new"

    def _get_readme(self, package_name: str) -> Optional[str]:
        try:
            response = self.client.get(f"{NPM_PACKAGE_URL}/{package_name}")
            if response.status_code == 200:
                data = response.json()
                return data.get("readme", "")
        except Exception:
            pass
        return None

    def _get_weekly_downloads(self, package_name: str) -> Optional[int]:
        try:
            response = self.client.get(
                f"https://api.npmjs.org/downloads/point/last-week/{package_name}"
            )
            if response.status_code == 200:
                return response.json().get("downloads", 0)
        except Exception:
            pass
        return None


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    spider = NpmSpider()
    stats = spider.crawl(max_results_per_query=50)
    print(f"Crawl complete: {stats}")
