"""
AgentIndex GitHub Spider

Crawls GitHub for AI agent repositories. This is our primary source
of agent discovery — GitHub hosts the majority of open source agents.

Strategy:
1. Search GitHub API for repos matching agent-related keywords
2. Download README, package.json, skill.md, agent.md
3. Queue results for parsing

Rate limits: GitHub API allows 5,000 requests/hour with token.
Each search returns 30 results per page, max 1,000 results per query.
We use many specific queries to maximize coverage.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from github import Github, GithubException
from agentindex.db.models import Agent, CrawlJob, get_session
from sqlalchemy import text, select

logger = logging.getLogger("agentindex.spiders.github")

# Search queries designed to find AI agents across the ecosystem
SEARCH_QUERIES = [
    # Core — high-yield, sorted=updated catches new repos
    "ai-agent",
    "llm agent",
    "autonomous agent",
    "mcp-server",
    "mcp server",
    "model context protocol",
    "langchain agent",
    "crewai agent",
    "autogen agent",
    "multi-agent system",
    "agent framework python",

    # A2A ecosystem
    "agent2agent",
    "a2a protocol",
    "agent discovery",

    # Discovery targets
    "agent.md",
    "agent registry",
]


class GitHubSpider:
    """
    Crawls GitHub repositories for AI agents.
    """

    def __init__(self):
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN environment variable required")
        self.github = Github(token, per_page=100)
        self.session = get_session()

    def crawl(self, max_results_per_query: int = 500) -> dict:
        """
        Run a full crawl cycle across all search queries.
        Returns stats about what was found.
        """
        stats = {
            "queries_run": 0,
            "repos_found": 0,
            "repos_new": 0,
            "repos_updated": 0,
            "errors": 0,
        }

        for query in SEARCH_QUERIES:
            try:
                query_stats = self._crawl_query(query, max_results_per_query)
                stats["queries_run"] += 1
                stats["repos_found"] += query_stats["found"]
                stats["repos_new"] += query_stats["new"]
                stats["repos_updated"] += query_stats["updated"]

                # Log progress
                logger.info(
                    f"Query '{query}': found={query_stats['found']}, "
                    f"new={query_stats['new']}, updated={query_stats['updated']}"
                )

                # Respect rate limits — small pause between queries
                time.sleep(2)

            except GithubException as e:
                if e.status == 403:
                    # Rate limited — wait and retry
                    reset_time = self.github.rate_limiting_resettime
                    wait_seconds = max(reset_time - time.time(), 60)
                    logger.warning(f"Rate limited. Waiting {wait_seconds:.0f}s")
                    time.sleep(wait_seconds)
                    stats["errors"] += 1
                else:
                    logger.error(f"GitHub error for query '{query}': {e}")
                    stats["errors"] += 1

            except Exception as e:
                try:
                    self.session.rollback()
                except Exception:
                    self.session = get_session()
                    self.session.rollback()
                logger.error(f"Error crawling query '{query}': {e}")
                stats["errors"] += 1

        # Log crawl job
        job = CrawlJob(
            source="github",
            query="full_crawl",
            status="completed",
            items_found=stats["repos_found"],
            items_new=stats["repos_new"],
            items_updated=stats["repos_updated"],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        self.session.add(job)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            self.session = get_session()

        logger.info(f"GitHub crawl complete: {stats}")
        return stats

    def _crawl_query(self, query: str, max_results: int) -> dict:
        """Crawl a single search query."""
        stats = {"found": 0, "new": 0, "updated": 0}

        # Search for repositories
        results = self.github.search_repositories(
            query=query,
            sort="updated",
            order="desc",
        )

        for i, repo in enumerate(results):
            if i >= max_results:
                break

            stats["found"] += 1

            try:
                result = self._process_repo(repo)
                if result == "new":
                    stats["new"] += 1
                elif result == "updated":
                    stats["updated"] += 1
            except Exception as e:
                logger.error(f"Error processing repo {repo.full_name}: {e}")

            # Small pause to be respectful
            if i % 50 == 0 and i > 0:
                time.sleep(1)

        return stats

    def _process_repo(self, repo) -> str:
        """
        Process a single GitHub repository.
        Returns 'new', 'updated', or 'skipped'.
        """
        source_url = repo.html_url

        # Check if already indexed
        existing = self.session.execute(
            select(Agent).where(Agent.source_url == source_url)
        ).scalar_one_or_none()

        if existing:
            # Update if repo has been modified since last crawl
            if repo.updated_at and existing.last_crawled:
                if str(repo.updated_at) > str(existing.last_crawled):
                    self._update_agent(existing, repo)
                    return "updated"
            return "skipped"

        # New agent — extract data and store
        agent = self._create_agent(repo)
        if agent:
            self.session.add(agent)
            try:
                self.session.commit()
            except Exception:
                self.session.rollback()
                self.session = get_session()
            return "new"

        return "skipped"

    def _create_agent(self, repo) -> Optional[Agent]:
        """Create a new Agent record from a GitHub repo."""

        # Read README
        readme_content = self._get_file_content(repo, "README.md")
        if not readme_content:
            readme_content = self._get_file_content(repo, "readme.md")

        # Read special files
        skill_md = self._get_file_content(repo, "skill.md")
        agent_md = self._get_file_content(repo, "agent.md")
        package_json = self._get_file_content(repo, "package.json")
        pyproject = self._get_file_content(repo, "pyproject.toml")
        setup_py = self._get_file_content(repo, "setup.py")

        # Build raw metadata for later parsing by AI
        raw_metadata = {
            "readme": readme_content[:10000] if readme_content else None,
            "skill_md": skill_md[:5000] if skill_md else None,
            "agent_md": agent_md[:5000] if agent_md else None,
            "package_json": package_json[:3000] if package_json else None,
            "pyproject": pyproject[:3000] if pyproject else None,
            "topics": repo.topics if hasattr(repo, 'topics') else [],
            "language": repo.language,
            "description": repo.description,
            "full_name": repo.full_name,
        }

        # Skip repos with no useful content
        if not readme_content and not skill_md and not agent_md:
            if not repo.description:
                return None

        # Detect frameworks from topics and files
        frameworks = self._detect_frameworks(repo, raw_metadata)

        # Detect protocols
        protocols = self._detect_protocols(raw_metadata)

        # Determine invocation method
        invocation = self._detect_invocation(raw_metadata)

        agent = Agent(
            source="github",
            source_url=repo.html_url,
            source_id=repo.full_name,
            name=repo.name,
            description=repo.description or "",
            author=repo.owner.login if repo.owner else None,
            license=repo.license.spdx_id if repo.license else None,
            language=repo.language,
            stars=repo.stargazers_count,
            forks=repo.forks_count,
            last_source_update=repo.updated_at,
            frameworks=frameworks,
            protocols=protocols,
            invocation=invocation,
            tags=repo.topics if hasattr(repo, 'topics') else [],
            raw_metadata=raw_metadata,
            crawl_status="indexed",  # needs parsing by AI next
            first_indexed=datetime.utcnow(),
            last_crawled=datetime.utcnow(),
        )

        return agent

    def _update_agent(self, agent: Agent, repo):
        """Update an existing agent with fresh data from GitHub."""
        agent.stars = repo.stargazers_count
        agent.forks = repo.forks_count
        agent.last_source_update = repo.updated_at
        agent.last_crawled = datetime.utcnow()

        if hasattr(repo, 'topics'):
            agent.tags = repo.topics

        # Re-read README for re-parsing
        readme_content = self._get_file_content(repo, "README.md")
        if readme_content:
            agent.raw_metadata = {
                **agent.raw_metadata,
                "readme": readme_content[:10000],
            }
            agent.crawl_status = "indexed"  # re-parse needed

        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            self.session = get_session()

    def _get_file_content(self, repo, path: str) -> Optional[str]:
        """Safely get file content from a repo."""
        try:
            content = repo.get_contents(path)
            if content.size > 100000:  # skip very large files
                return None
            return content.decoded_content.decode("utf-8", errors="ignore")
        except Exception:
            return None

    def _detect_frameworks(self, repo, metadata: dict) -> list:
        """Detect which AI frameworks this agent uses."""
        frameworks = []
        text_to_check = " ".join([
            metadata.get("readme") or "",
            metadata.get("package_json") or "",
            metadata.get("pyproject") or "",
            " ".join(metadata.get("topics") or []),
        ]).lower()

        framework_keywords = {
            "langchain": ["langchain"],
            "crewai": ["crewai", "crew-ai"],
            "autogen": ["autogen", "auto-gen"],
            "llamaindex": ["llamaindex", "llama-index", "llama_index"],
            "semantic-kernel": ["semantic-kernel", "semantic_kernel"],
            "openai": ["openai", "gpt-4", "gpt4"],
            "anthropic": ["anthropic", "claude"],
            "mcp": ["model-context-protocol", "mcp-server", "mcp_server"],
            "a2a": ["agent2agent", "a2a-protocol"],
            "ollama": ["ollama"],
            "huggingface": ["huggingface", "transformers"],
        }

        for framework, keywords in framework_keywords.items():
            if any(kw in text_to_check for kw in keywords):
                frameworks.append(framework)

        return frameworks

    def _detect_protocols(self, metadata: dict) -> list:
        """Detect which agent protocols are supported."""
        protocols = []
        text_to_check = " ".join([
            metadata.get("readme") or "",
            metadata.get("skill_md") or "",
            metadata.get("agent_md") or "",
        ]).lower()

        if "mcp" in text_to_check or metadata.get("skill_md"):
            protocols.append("mcp")
        if "a2a" in text_to_check or "agent2agent" in text_to_check:
            protocols.append("a2a")
        if "rest" in text_to_check or "api" in text_to_check:
            protocols.append("rest")
        if "grpc" in text_to_check:
            protocols.append("grpc")
        if "websocket" in text_to_check:
            protocols.append("websocket")

        return protocols

    def _detect_invocation(self, metadata: dict) -> dict:
        """Detect how to invoke this agent."""
        invocation = {"type": "github"}

        # Check for npm package
        if metadata.get("package_json"):
            invocation["type"] = "npm"
            try:
                import json
                pkg = json.loads(metadata["package_json"])
                invocation["install"] = f"npm install {pkg.get('name', '')}"
            except Exception:
                pass

        # Check for pip package
        if metadata.get("pyproject") or metadata.get("setup_py"):
            invocation["type"] = "pip"

        # Check for MCP
        if metadata.get("skill_md") or "mcp" in " ".join(metadata.get("topics") or []):
            invocation["type"] = "mcp"

        # Check for Docker
        text = (metadata.get("readme") or "").lower()
        if "docker" in text and ("docker-compose" in text or "dockerfile" in text):
            invocation["docker"] = True

        return invocation

    def get_remaining_rate_limit(self) -> dict:
        """Check GitHub API rate limit status."""
        rate = self.github.get_rate_limit()
        return {
            "remaining": rate.core.remaining,
            "limit": rate.core.limit,
            "resets_at": rate.core.reset.isoformat(),
        }


if __name__ == "__main__":
    """Run GitHub spider standalone for testing."""
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    spider = GitHubSpider()
    print(f"Rate limit: {spider.get_remaining_rate_limit()}")
    stats = spider.crawl(max_results_per_query=100)  # limited for testing
    print(f"Crawl complete: {stats}")
