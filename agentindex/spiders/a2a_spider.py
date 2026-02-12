"""
AgentIndex A2A Spider

Discovers and indexes A2A-compatible agents via:
1. KNOWN — curated list of live A2A endpoints
2. GITHUB — repos that implement A2A (code search)
3. DISCOVERED — re-check previously found endpoints

Fast and focused. No README URL scraping.
"""

import os
import re
import json
import time
import logging
import hashlib
from datetime import datetime
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from agentindex.db.models import Agent, CrawlJob, get_session, safe_commit

logger = logging.getLogger("agentindex.spiders.a2a")

KNOWN_A2A_ENDPOINTS = [
    # Add real A2A endpoints as they go live
    "https://api.agentcrawl.dev",  # Us!
]

A2A_GITHUB_QUERIES = [
    "agent-card.json well-known",
    "a2a protocol AgentCard python",
    "A2AStarletteApplication",
    "agent2agent server AgentSkill",
    "fasta2a to_a2a",
    ".well-known/agent.json agentcard",
]

DISCOVERED_FILE = os.path.expanduser("~/agentindex/a2a_discovered_endpoints.json")
REQUEST_TIMEOUT = 8.0
MAX_REPOS_PER_QUERY = 10


def _load_discovered():
    if os.path.exists(DISCOVERED_FILE):
        try:
            with open(DISCOVERED_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"endpoints": [], "last_crawl": None}


def _save_discovered(data):
    with open(DISCOVERED_FILE, "w") as f:
        json.dump(data, f, indent=2)


class A2ASpider:

    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.stats = {"endpoints_checked": 0, "cards_found": 0, "agents_created": 0, "agents_updated": 0, "repos_indexed": 0, "errors": 0}
        self.discovered = _load_discovered()
        self._failed_domains = set()

    def crawl(self) -> dict:
        logger.info("=" * 50)
        logger.info("A2A Spider starting...")
        logger.info("=" * 50)

        session = get_session()
        job = CrawlJob(source="a2a", query="a2a-agent-cards", status="running", started_at=datetime.utcnow())
        session.add(job)
        safe_commit(session)

        try:
            # Phase 1: Check known + discovered endpoints for live Agent Cards
            logger.info("Phase 1: Checking known A2A endpoints...")
            all_endpoints = KNOWN_A2A_ENDPOINTS + [e["url"] for e in self.discovered.get("endpoints", [])]
            for url in set(all_endpoints):
                self._try_fetch_agent_card(url, session, source="known")

            # Phase 2: Search GitHub for A2A repos
            logger.info("Phase 2: Searching GitHub for A2A repos...")
            self._search_github_repos(session)

            self.discovered["last_crawl"] = datetime.utcnow().isoformat()
            _save_discovered(self.discovered)

            job.status = "completed"
            job.items_found = self.stats["cards_found"] + self.stats["repos_indexed"]
            job.items_new = self.stats["agents_created"]
            job.items_updated = self.stats["agents_updated"]
            job.completed_at = datetime.utcnow()
            safe_commit(session)

        except Exception as e:
            logger.error(f"A2A crawl failed: {e}")
            job.status = "failed"
            job.error_message = str(e)[:500]
            safe_commit(session)
        finally:
            session.close()

        logger.info(f"A2A Spider complete: {self.stats}")
        return self.stats

    # =================================================================
    # Phase 1: Fetch live Agent Cards
    # =================================================================

    def _try_fetch_agent_card(self, base_url: str, session, source: str = "unknown"):
        """Try to fetch Agent Card from well-known paths."""
        domain = urlparse(base_url).netloc.lower()
        if domain in self._failed_domains:
            return

        for path in ["/.well-known/agent-card.json", "/.well-known/agent.json"]:
            url = base_url.rstrip("/") + path
            self.stats["endpoints_checked"] += 1
            try:
                resp = httpx.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
                if resp.status_code == 200:
                    card = resp.json()
                    if self._is_valid_card(card):
                        logger.info(f"  ✓ Agent Card: {card.get('name', '?')} at {url}")
                        self.stats["cards_found"] += 1
                        self._index_agent_card(card, base_url, url, session, source)
                        # Save to discovered
                        existing_urls = [e["url"] for e in self.discovered.get("endpoints", [])]
                        if base_url not in existing_urls:
                            self.discovered.setdefault("endpoints", []).append({
                                "url": base_url,
                                "name": card.get("name", "?"),
                                "found_at": datetime.utcnow().isoformat(),
                                "source": source,
                            })
                        return
            except Exception:
                pass

        self._failed_domains.add(domain)

    def _is_valid_card(self, card) -> bool:
        return isinstance(card, dict) and "name" in card and any(k in card for k in ["skills", "capabilities", "url", "version"])

    def _index_agent_card(self, card, base_url, card_url, session, source):
        """Create or update Agent from Agent Card."""
        existing = session.execute(select(Agent).where(Agent.source_url == card_url)).scalar_one_or_none()

        skills = card.get("skills", [])
        capabilities = [s.get("name", s.get("id", "")) for s in skills if isinstance(s, dict)]
        tags = list(set(["a2a", "agent2agent", "live-agent"] + [t for s in skills if isinstance(s, dict) for t in s.get("tags", [])]))[:20]
        provider = card.get("provider", {})
        author = provider.get("organization", "") if isinstance(provider, dict) else ""
        invocation = {
            "type": "a2a",
            "endpoint": card.get("url", base_url),
            "protocol": "a2a",
            "agent_card_url": card_url,
        }
        if card.get("authentication"):
            invocation["authentication"] = card["authentication"]

        if existing:
            existing.name = card.get("name", existing.name)
            existing.description = card.get("description", existing.description)
            existing.capabilities = capabilities or existing.capabilities
            existing.tags = tags
            existing.invocation = invocation
            existing.protocols = list(set((existing.protocols or []) + ["a2a"]))
            existing.last_crawled = datetime.utcnow()
            existing.raw_metadata = {**(existing.raw_metadata or {}), "agent_card": card, "a2a_source": source}
            safe_commit(session)
            self.stats["agents_updated"] += 1
        else:
            agent = Agent(
                source="a2a", source_url=card_url,
                source_id=hashlib.md5(card_url.encode()).hexdigest()[:16],
                name=card.get("name", "Unknown A2A Agent"),
                description=card.get("description", ""),
                author=author, capabilities=capabilities,
                category="agent platform", tags=tags,
                invocation=invocation, protocols=["a2a"],
                quality_score=0.5, crawl_status="indexed",
                last_crawled=datetime.utcnow(),
                raw_metadata={"agent_card": card, "a2a_source": source, "skills_count": len(skills)},
            )
            session.add(agent)
            safe_commit(session)
            self.stats["agents_created"] += 1

    # =================================================================
    # Phase 2: GitHub search — index repos that implement A2A
    # =================================================================

    def _search_github_repos(self, session):
        if not self.github_token:
            logger.warning("No GitHub token, skipping")
            return

        headers = {"Authorization": f"token {self.github_token}"}
        seen_repos = set()

        for query in A2A_GITHUB_QUERIES:
            try:
                resp = httpx.get(
                    "https://api.github.com/search/code",
                    params={"q": query, "per_page": MAX_REPOS_PER_QUERY},
                    headers=headers, timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code == 403:
                    logger.warning("GitHub rate limit, stopping search")
                    break
                if resp.status_code != 200:
                    continue

                items = resp.json().get("items", [])
                logger.info(f"  GitHub '{query}': {len(items)} results")

                for item in items:
                    full_name = item.get("repository", {}).get("full_name", "")
                    if not full_name or full_name in seen_repos:
                        continue
                    seen_repos.add(full_name)
                    self._index_a2a_repo(full_name, headers, session)

                time.sleep(2)  # Respect search rate limit

            except Exception as e:
                logger.error(f"GitHub search error '{query}': {e}")
                self.stats["errors"] += 1

    def _index_a2a_repo(self, full_name: str, headers: dict, session):
        """Index a GitHub repo as A2A-capable agent."""
        source_url = f"https://github.com/{full_name}"
        existing = session.execute(select(Agent).where(Agent.source_url == source_url)).scalar_one_or_none()

        if existing:
            if existing.protocols and "a2a" not in existing.protocols:
                existing.protocols = list(set(existing.protocols + ["a2a"]))
                existing.last_crawled = datetime.utcnow()
                safe_commit(session)
                self.stats["agents_updated"] += 1
            return

        try:
            resp = httpx.get(f"https://api.github.com/repos/{full_name}", headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return
            repo = resp.json()

            # Skip forks and very small repos
            if repo.get("fork", False) or repo.get("size", 0) < 5:
                return

            agent = Agent(
                source="github", source_url=source_url, source_id=full_name,
                name=repo.get("name", full_name.split("/")[-1]),
                description=(repo.get("description") or "")[:500] or f"A2A-compatible agent: {full_name}",
                author=repo.get("owner", {}).get("login", ""),
                license=repo.get("license", {}).get("spdx_id") if repo.get("license") else None,
                stars=repo.get("stargazers_count", 0),
                forks=repo.get("forks_count", 0),
                language=repo.get("language"),
                protocols=["a2a"], tags=["a2a", "agent2agent"],
                crawl_status="indexed", last_crawled=datetime.utcnow(),
                raw_metadata={"a2a_source": True, "topics": repo.get("topics", [])},
            )
            session.add(agent)
            safe_commit(session)
            self.stats["repos_indexed"] += 1
            logger.info(f"  Indexed: {full_name} ({repo.get('stargazers_count', 0)}★)")

        except Exception as e:
            logger.debug(f"Error indexing {full_name}: {e}")
            self.stats["errors"] += 1


def run_a2a_crawl() -> dict:
    spider = A2ASpider()
    return spider.crawl()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    from dotenv import load_dotenv
    load_dotenv(os.path.expanduser("~/agentindex/.env"))
    stats = run_a2a_crawl()
    print(f"\nStats: {json.dumps(stats, indent=2)}")
