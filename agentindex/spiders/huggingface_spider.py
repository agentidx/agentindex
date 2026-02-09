"""
AgentIndex HuggingFace Spider

Crawls HuggingFace for AI agent spaces, models, and tools.
Uses the public HuggingFace Hub API — no authentication required for basic access.
"""

import time
import logging
from datetime import datetime
from typing import Optional
import httpx
from agentindex.db.models import Agent, CrawlJob, get_session
from sqlalchemy import select

logger = logging.getLogger("agentindex.spiders.huggingface")

HF_API_URL = "https://huggingface.co/api"

SEARCH_QUERIES = [
    "agent",
    "mcp",
    "autonomous",
    "tool-use",
    "function-calling",
    "assistant",
    "multi-agent",
    "agentic",
]

SPACE_SEARCH_QUERIES = [
    "ai-agent",
    "agent",
    "mcp-server",
    "assistant",
    "autonomous",
    "tool",
]


class HuggingFaceSpider:
    """Crawls HuggingFace for agent-related content."""

    def __init__(self):
        self.client = httpx.Client(timeout=30)
        self.session = get_session()

    def crawl(self, max_results_per_query: int = 200) -> dict:
        stats = {"found": 0, "new": 0, "errors": 0}

        # Crawl models
        for query in SEARCH_QUERIES:
            try:
                result = self._crawl_models(query, max_results_per_query)
                stats["found"] += result["found"]
                stats["new"] += result["new"]
                logger.info(f"HF models query '{query}': found={result['found']}, new={result['new']}")
                time.sleep(1)
            except Exception as e:
                self.session.rollback()
                logger.error(f"HF models error for '{query}': {e}")
                stats["errors"] += 1

        # Crawl spaces
        for query in SPACE_SEARCH_QUERIES:
            try:
                result = self._crawl_spaces(query, max_results_per_query)
                stats["found"] += result["found"]
                stats["new"] += result["new"]
                logger.info(f"HF spaces query '{query}': found={result['found']}, new={result['new']}")
                time.sleep(1)
            except Exception as e:
                logger.error(f"HF spaces error for '{query}': {e}")
                stats["errors"] += 1

        job = CrawlJob(
            source="huggingface",
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

        logger.info(f"HuggingFace crawl complete: {stats}")
        return stats

    def _crawl_models(self, query: str, max_results: int) -> dict:
        stats = {"found": 0, "new": 0}

        response = self.client.get(
            f"{HF_API_URL}/models",
            params={
                "search": query,
                "limit": min(max_results, 100),
                "sort": "downloads",
                "direction": -1,
            }
        )

        if response.status_code != 200:
            return stats

        models = response.json()

        for model in models:
            stats["found"] += 1
            try:
                result = self._process_model(model)
                if result == "new":
                    stats["new"] += 1
            except Exception as e:
                logger.error(f"Error processing HF model {model.get('id')}: {e}")

        return stats

    def _crawl_spaces(self, query: str, max_results: int) -> dict:
        stats = {"found": 0, "new": 0}

        response = self.client.get(
            f"{HF_API_URL}/spaces",
            params={
                "search": query,
                "limit": min(max_results, 100),
                "sort": "likes",
                "direction": -1,
            }
        )

        if response.status_code != 200:
            return stats

        spaces = response.json()

        for space in spaces:
            stats["found"] += 1
            try:
                result = self._process_space(space)
                if result == "new":
                    stats["new"] += 1
            except Exception as e:
                logger.error(f"Error processing HF space {space.get('id')}: {e}")

        return stats

    def _process_model(self, model: dict) -> str:
        model_id = model.get("id", "")
        source_url = f"https://huggingface.co/{model_id}"

        existing = self.session.execute(
            select(Agent).where(Agent.source_url == source_url)
        ).scalar_one_or_none()

        if existing:
            return "skipped"

        tags = model.get("tags", [])

        raw_metadata = {
            "model_id": model_id,
            "pipeline_tag": model.get("pipeline_tag"),
            "tags": tags,
            "downloads": model.get("downloads", 0),
            "likes": model.get("likes", 0),
            "library_name": model.get("library_name"),
            "last_modified": model.get("lastModified"),
        }

        agent = Agent(
            source="huggingface",
            source_url=source_url,
            source_id=model_id,
            name=model_id.split("/")[-1] if "/" in model_id else model_id,
            description=model.get("pipeline_tag", ""),
            author=model_id.split("/")[0] if "/" in model_id else None,
            language="Python",
            downloads=model.get("downloads", 0),
            stars=model.get("likes", 0),
            tags=tags[:20],
            invocation={"type": "huggingface", "model_id": model_id},
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

    def _process_space(self, space: dict) -> str:
        space_id = space.get("id", "")
        source_url = f"https://huggingface.co/spaces/{space_id}"

        existing = self.session.execute(
            select(Agent).where(Agent.source_url == source_url)
        ).scalar_one_or_none()

        if existing:
            return "skipped"

        raw_metadata = {
            "space_id": space_id,
            "sdk": space.get("sdk"),
            "tags": space.get("tags", []),
            "likes": space.get("likes", 0),
            "last_modified": space.get("lastModified"),
            "runtime": space.get("runtime", {}),
        }

        agent = Agent(
            source="huggingface",
            source_url=source_url,
            source_id=space_id,
            name=space_id.split("/")[-1] if "/" in space_id else space_id,
            description="",
            author=space_id.split("/")[0] if "/" in space_id else None,
            language=space.get("sdk", "unknown"),
            stars=space.get("likes", 0),
            tags=space.get("tags", [])[:20],
            invocation={"type": "huggingface_space", "space_id": space_id},
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


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    spider = HuggingFaceSpider()
    stats = spider.crawl(max_results_per_query=20)
    print(f"Crawl complete: {stats}")
