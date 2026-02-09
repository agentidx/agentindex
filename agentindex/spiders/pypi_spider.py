"""
AgentIndex PyPI Spider

Crawls PyPI (Python Package Index) for AI agent packages.
Uses the public JSON API — no authentication needed.
"""

import time
import logging
from datetime import datetime
from typing import Optional
import httpx
from agentindex.db.models import Agent, CrawlJob, get_session
from sqlalchemy import select

logger = logging.getLogger("agentindex.spiders.pypi")

SEARCH_QUERIES = [
    "ai agent",
    "llm agent",
    "mcp server",
    "autonomous agent",
    "langchain agent",
    "crewai",
    "autogen",
    "agent framework",
    "multi agent",
    "agent orchestration",
    "openai agent",
    "anthropic agent",
    "agent tool",
    "agent2agent",
    "chatbot agent",
    "ai assistant",
    "llamaindex",
    "agent sdk",
    "agent workflow",
    "model context protocol",
]

PYPI_SEARCH_URL = "https://pypi.org/search/"
PYPI_JSON_URL = "https://pypi.org/pypi"


class PypiSpider:
    """Crawls PyPI for AI agent packages."""

    def __init__(self):
        self.client = httpx.Client(timeout=30)
        self.session = get_session()

    def crawl(self, max_results_per_query: int = 100) -> dict:
        stats = {"queries_run": 0, "packages_found": 0, "new": 0, "updated": 0, "errors": 0}

        for query in SEARCH_QUERIES:
            try:
                query_stats = self._crawl_query(query, max_results_per_query)
                stats["queries_run"] += 1
                stats["packages_found"] += query_stats["found"]
                stats["new"] += query_stats["new"]

                logger.info(f"PyPI query '{query}': found={query_stats['found']}, new={query_stats['new']}")
                time.sleep(2)

            except Exception as e:
                self.session.rollback()
                logger.error(f"Error crawling PyPI query '{query}': {e}")
                stats["errors"] += 1

        job = CrawlJob(
            source="pypi",
            query="full_crawl",
            status="completed",
            items_found=stats["packages_found"],
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

        logger.info(f"PyPI crawl complete: {stats}")
        return stats

    def _crawl_query(self, query: str, max_results: int) -> dict:
        """
        PyPI doesn't have a great search API. We use the JSON API
        to look up specific packages and the simple search page for discovery.
        Strategy: search for packages, then fetch full details via JSON API.
        """
        stats = {"found": 0, "new": 0}

        # Use PyPI simple search (HTML scraping as fallback)
        # Primary approach: use the XML-RPC or search endpoint
        try:
            response = self.client.get(
                PYPI_SEARCH_URL,
                params={"q": query, "page": 1},
                headers={"Accept": "text/html"},
                follow_redirects=True,
            )

            if response.status_code != 200:
                return stats

            # Extract package names from search results
            # Simple parsing — look for package name patterns
            text = response.text
            package_names = self._extract_package_names(text)

            for name in package_names[:max_results]:
                stats["found"] += 1
                try:
                    result = self._process_package(name)
                    if result == "new":
                        stats["new"] += 1
                except Exception as e:
                    logger.error(f"Error processing PyPI package {name}: {e}")

                time.sleep(0.5)

        except Exception as e:
            logger.error(f"PyPI search error: {e}")

        return stats

    def _extract_package_names(self, html: str) -> list:
        """Extract package names from PyPI search results HTML."""
        names = []
        # Look for package links: /project/PACKAGE_NAME/
        import re
        matches = re.findall(r'/project/([^/]+)/', html)
        seen = set()
        for name in matches:
            if name not in seen and name not in ("", "help", "account"):
                seen.add(name)
                names.append(name)
        return names

    def _process_package(self, name: str) -> str:
        source_url = f"https://pypi.org/project/{name}/"

        existing = self.session.execute(
            select(Agent).where(Agent.source_url == source_url)
        ).scalar_one_or_none()

        if existing:
            return "skipped"

        # Get full package info via JSON API
        package_data = self._get_package_info(name)
        if not package_data:
            return "skipped"

        info = package_data.get("info", {})

        raw_metadata = {
            "description_long": (info.get("description") or "")[:10000],
            "description_short": info.get("summary"),
            "keywords": info.get("keywords"),
            "classifiers": info.get("classifiers", []),
            "homepage": info.get("home_page"),
            "project_urls": info.get("project_urls", {}),
            "requires_python": info.get("requires_python"),
            "version": info.get("version"),
        }

        # Extract keywords as tags
        keywords = info.get("keywords") or ""
        tags = [k.strip() for k in keywords.replace(",", " ").split() if k.strip()]

        # Detect frameworks
        text_blob = " ".join([
            info.get("summary") or "",
            info.get("description") or "",
            keywords,
        ]).lower()

        frameworks = []
        if "langchain" in text_blob: frameworks.append("langchain")
        if "crewai" in text_blob: frameworks.append("crewai")
        if "autogen" in text_blob: frameworks.append("autogen")
        if "openai" in text_blob: frameworks.append("openai")
        if "anthropic" in text_blob: frameworks.append("anthropic")
        if "mcp" in text_blob: frameworks.append("mcp")
        if "llamaindex" in text_blob: frameworks.append("llamaindex")

        protocols = []
        if "mcp" in text_blob: protocols.append("mcp")
        if "a2a" in text_blob: protocols.append("a2a")
        if "rest" in text_blob or "api" in text_blob: protocols.append("rest")

        # Find GitHub repo URL
        github_url = None
        project_urls = info.get("project_urls") or {}
        for key, url in project_urls.items():
            if url and "github.com" in url:
                github_url = url
                break
        if not github_url and info.get("home_page") and "github.com" in (info.get("home_page") or ""):
            github_url = info["home_page"]

        agent = Agent(
            source="pypi",
            source_url=source_url,
            source_id=name,
            name=name,
            description=info.get("summary", ""),
            author=info.get("author") or info.get("maintainer"),
            license=info.get("license"),
            language="Python",
            frameworks=frameworks,
            protocols=protocols,
            invocation={"type": "pip", "install": f"pip install {name}"},
            tags=tags,
            raw_metadata=raw_metadata,
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

    def _get_package_info(self, name: str) -> Optional[dict]:
        try:
            response = self.client.get(f"{PYPI_JSON_URL}/{name}/json")
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    spider = PypiSpider()
    stats = spider.crawl(max_results_per_query=20)
    print(f"Crawl complete: {stats}")
