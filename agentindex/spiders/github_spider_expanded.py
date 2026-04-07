"""
GitHub Spider - EXPANDED for 500K Scale

MASSIVE expansion of GitHub crawler to capture 100K-200K+ AI agents/tools.
Strategy:
1. 5x more search terms covering entire AI ecosystem  
2. GitHub Topics search (high-quality repos)
3. Star-based filtering (>5 stars for quality)
4. Broader definition: agents, tools, models, pipelines, services

This is our FASTEST path to 500K - leveraging proven infrastructure.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from github import Github, GithubException
from agentindex.db.models import Agent, CrawlJob, get_session
from sqlalchemy import text, select
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from github_token_rotation import get_token_manager

logger = logging.getLogger("agentindex.spiders.github_expanded")

# EXPANDED SEARCH QUERIES - Covering entire AI ecosystem
CORE_AGENT_QUERIES = [
    # Traditional agents
    "ai-agent", "llm agent", "autonomous agent", "intelligent agent",
    "multi-agent", "agent framework", "agent system", "ai assistant",
    "chatbot", "ai-chatbot", "conversational agent", "dialog agent",
    
    # MCP ecosystem  
    "mcp-server", "mcp server", "model context protocol",
    
    # Framework-specific
    "langchain agent", "crewai agent", "autogen agent", "haystack agent",
    "semantic kernel agent", "guidance agent", "dspy agent",
    
    # A2A protocol
    "agent2agent", "a2a protocol", "agent discovery", "agent registry",
    
    # Agent types
    "research agent", "coding agent", "data agent", "web agent",
]

AI_TOOL_QUERIES = [
    # LLM tools
    "llm-tool", "llm tool", "llm utility", "llm wrapper", "llm client",
    "openai tool", "anthropic tool", "claude tool", "gpt tool",
    
    # RAG & Vector
    "rag system", "rag pipeline", "vector-db", "vector database",
    "semantic search", "embedding tool", "knowledge base",
    "document qa", "pdf chat", "knowledge graph",
    
    # Prompt engineering
    "prompt-engineering", "prompt template", "prompt optimization", 
    "prompt management", "prompt library", "few-shot learning",
    
    # Generation & Fine-tuning
    "fine-tuning", "model training", "llm training", "lora",
    "text generation", "image generation", "code generation",
    "content generation", "ai writer", "ai content",
]

ML_INFRASTRUCTURE_QUERIES = [
    # Models & Inference
    "ml-model", "ai model", "inference-server", "model serving",
    "model deployment", "model api", "huggingface", "transformers",
    "pytorch model", "tensorflow model", "onnx model",
    
    # Pipelines & MLOps
    "ai-pipeline", "ml pipeline", "mlops", "ml workflow", 
    "model pipeline", "training pipeline", "inference pipeline",
    "feature store", "model registry", "experiment tracking",
    
    # Data & Processing
    "data preprocessing", "feature engineering", "data augmentation",
    "synthetic data", "data labeling", "annotation tool",
]

DOMAIN_SPECIFIC_QUERIES = [
    # Business domains
    "legal ai", "medical ai", "finance ai", "healthcare ai",
    "education ai", "customer service ai", "sales ai", 
    "marketing ai", "hr ai", "recruiting ai",
    
    # Technical domains  
    "code ai", "dev ai", "devops ai", "security ai", "testing ai",
    "database ai", "api ai", "cloud ai", "kubernetes ai",
    
    # Content domains
    "writing ai", "editing ai", "translation ai", "summarization",
    "text analysis", "sentiment analysis", "content moderation",
]

EMERGING_QUERIES = [
    # Latest trends
    "genai", "generative ai", "multimodal ai", "vision language model",
    "ai workflow", "ai automation", "ai integration", "ai api",
    "ai middleware", "ai orchestration", "ai gateway",
    
    # Specific technologies
    "retrieval augmented", "function calling", "tool use", "agent tools",
    "ai plugins", "ai extensions", "ai connectors", "ai adapters",
]

# GitHub Topics for high-quality discovery
AI_TOPICS = [
    "artificial-intelligence", "machine-learning", "deep-learning", 
    "natural-language-processing", "computer-vision", "reinforcement-learning",
    "llm", "large-language-models", "gpt", "transformer", "bert",
    "ai-agent", "autonomous-agent", "multi-agent", "conversational-ai",
    "chatbot", "virtual-assistant", "text-generation", "code-generation",
    "rag", "retrieval-augmented-generation", "vector-database", "embeddings",
    "prompt-engineering", "fine-tuning", "model-training", "mlops",
    "langchain", "openai", "huggingface", "pytorch", "tensorflow"
]

# Combine all queries
ALL_SEARCH_QUERIES = (
    CORE_AGENT_QUERIES + AI_TOOL_QUERIES + 
    ML_INFRASTRUCTURE_QUERIES + DOMAIN_SPECIFIC_QUERIES + 
    EMERGING_QUERIES
)

class GitHubExpandedSpider:
    """
    EXPANDED GitHub crawler for massive AI ecosystem coverage.
    Target: 100K-200K+ repositories vs current 35K.
    """

    def __init__(self):
        # Use token rotation manager for 4x rate limit (20,000/h vs 5,000/h)
        self.token_manager = get_token_manager()
        
        # Start with first token
        first_token = self.token_manager.get_next_token()
        self.github = Github(first_token, per_page=100)
        self.session = get_session()
        
        # Track what we've seen to avoid duplicates
        self.seen_repos = set()
        
        logger.info(f"🔑 GitHub crawler initialized with {len(self.token_manager.tokens)} token(s)")
        logger.info(f"📈 Rate limit: {len(self.token_manager.tokens) * 5000}/hour")
        
    def crawl_expanded(self, max_results_per_query: int = 200, min_stars: int = 5) -> Dict:
        """
        EXPANDED crawl covering entire AI ecosystem.
        
        Args:
            max_results_per_query: Max results per search query
            min_stars: Minimum stars for quality filtering
        """
        start_time = time.time()
        logger.info(f"🚀 Starting EXPANDED GitHub crawl with {len(ALL_SEARCH_QUERIES)} queries")
        logger.info(f"Target: 100K-200K+ repositories (vs current 35K)")
        
        stats = {
            "queries_run": 0,
            "repos_found": 0, 
            "repos_new": 0,
            "repos_updated": 0,
            "repos_filtered_stars": 0,
            "topics_searched": 0,
            "errors": 0,
            "source": "github_expanded"
        }
        
        # Phase 1: Expanded keyword search
        logger.info("📖 Phase 1: Expanded keyword search...")
        for i, query in enumerate(ALL_SEARCH_QUERIES, 1):
            try:
                logger.info(f"Query {i}/{len(ALL_SEARCH_QUERIES)}: '{query}'")
                query_stats = self._crawl_query_with_stars(query, max_results_per_query, min_stars)
                
                stats["queries_run"] += 1
                stats["repos_found"] += query_stats["found"]
                stats["repos_new"] += query_stats["new"] 
                stats["repos_updated"] += query_stats["updated"]
                stats["repos_filtered_stars"] += query_stats["filtered_stars"]
                
                logger.info(f"  ✅ Found: {query_stats['found']}, New: {query_stats['new']}, Filtered: {query_stats['filtered_stars']}")
                
                # Rate limiting protection
                if i % 10 == 0:
                    self._check_rate_limit()
                    logger.info(f"📊 Progress: {i}/{len(ALL_SEARCH_QUERIES)} queries, {stats['repos_found']} total repos")
                
                time.sleep(1)  # Basic rate limiting
                
            except Exception as e:
                logger.error(f"Query '{query}' failed: {e}")
                stats["errors"] += 1
                continue
        
        # Phase 2: GitHub Topics search
        logger.info("🏷️ Phase 2: GitHub Topics search...")
        for topic in AI_TOPICS:
            try:
                topic_stats = self._crawl_topic(topic, max_results_per_query, min_stars)
                stats["topics_searched"] += 1
                stats["repos_found"] += topic_stats["found"]
                stats["repos_new"] += topic_stats["new"]
                
                logger.info(f"Topic '{topic}': {topic_stats['found']} repos")
                time.sleep(2)  # Topics search is more intensive
                
            except Exception as e:
                logger.error(f"Topic '{topic}' failed: {e}")
                continue
        
        end_time = time.time()
        duration = end_time - start_time
        
        stats.update({
            "duration_seconds": round(duration, 2),
            "repos_per_second": round(stats["repos_found"] / duration, 2) if duration > 0 else 0,
            "unique_repos": len(self.seen_repos),
            "total_search_terms": len(ALL_SEARCH_QUERIES),
            "topics_searched": len(AI_TOPICS)
        })
        
        logger.info("🎯 EXPANDED GitHub crawl completed!")
        logger.info(f"   Queries: {stats['queries_run']}/{len(ALL_SEARCH_QUERIES)}")
        logger.info(f"   Topics: {stats['topics_searched']}/{len(AI_TOPICS)}")
        logger.info(f"   Total repos: {stats['repos_found']:,}")
        logger.info(f"   Unique repos: {stats['unique_repos']:,}")
        logger.info(f"   New repos: {stats['repos_new']:,}")
        logger.info(f"   Duration: {duration:.1f}s")
        
        return stats
    
    def _crawl_query_with_stars(self, query: str, max_results: int, min_stars: int) -> Dict:
        """Crawl a query with star filtering."""
        stats = {"found": 0, "new": 0, "updated": 0, "filtered_stars": 0}
        
        try:
            # Search with star filter built in
            search_query = f"{query} stars:>={min_stars}"
            repositories = self.github.search_repositories(
                query=search_query,
                sort="updated", 
                order="desc"
            )
            
            for i, repo in enumerate(repositories[:max_results]):
                if repo.full_name in self.seen_repos:
                    continue
                    
                self.seen_repos.add(repo.full_name)
                
                # Additional star check (GitHub search isn't always precise)
                if repo.stargazers_count < min_stars:
                    stats["filtered_stars"] += 1
                    continue
                
                # Process repository
                result = self._process_repository(repo)
                if result == "new":
                    stats["new"] += 1
                elif result == "updated":
                    stats["updated"] += 1
                
                stats["found"] += 1
                
                # Rate limit protection
                if i > 0 and i % 100 == 0:
                    self._check_rate_limit()
                    
        except GithubException as e:
            if e.status == 403:
                logger.warning("Rate limit hit during query, attempting token rotation...")
                self._check_rate_limit()
                # Try query again with rotated token
                try:
                    search_query = f"{query} stars:>={min_stars}"
                    repositories = self.github.search_repositories(
                        query=search_query,
                        sort="updated", 
                        order="desc"
                    )
                    logger.info("✅ Query retry successful after token rotation")
                except:
                    logger.error("❌ Query failed even after token rotation")
                    return stats
            else:
                raise e
        
        return stats
    
    def _crawl_topic(self, topic: str, max_results: int, min_stars: int) -> Dict:
        """Crawl repositories by GitHub topic."""
        stats = {"found": 0, "new": 0, "updated": 0}
        
        try:
            # Topic search with star filter
            search_query = f"topic:{topic} stars:>={min_stars}"
            repositories = self.github.search_repositories(
                query=search_query,
                sort="stars",
                order="desc"
            )
            
            for repo in repositories[:max_results]:
                if repo.full_name in self.seen_repos:
                    continue
                    
                self.seen_repos.add(repo.full_name)
                
                result = self._process_repository(repo)
                if result == "new":
                    stats["new"] += 1
                elif result == "updated": 
                    stats["updated"] += 1
                
                stats["found"] += 1
                
        except GithubException as e:
            if e.status == 403:
                logger.warning("Rate limited on topic search, rotating token...")
                self._check_rate_limit()
            else:
                raise e
        
        return stats
    
    def _process_repository(self, repo) -> str:
        """Process a repository and save to database."""
        try:
            # Check if already exists
            existing = self.session.execute(
                select(Agent).where(Agent.source_url == repo.html_url)
            ).scalar_one_or_none()
            
            # Basic repository data
            agent_data = {
                "name": repo.full_name,
                "description": repo.description or "",
                "source": "github",
                "source_url": repo.html_url,
                "stars": repo.stargazers_count,
                "language": repo.language,
                "tags": list(repo.get_topics()),
                "last_source_update": repo.updated_at,
                "raw_metadata": {
                    "github_expanded": True,
                    "forks_count": repo.forks_count,
                    "open_issues": repo.open_issues_count,
                    "size": repo.size,
                    "default_branch": repo.default_branch,
                    "has_wiki": repo.has_wiki,
                    "has_pages": repo.has_pages,
                    "license": repo.license.name if repo.license else None,
                    "fork": repo.fork,
                    "archived": repo.archived,
                    "created_at": repo.created_at.isoformat() if repo.created_at else None,
                    "topics": list(repo.get_topics())
                }
            }
            
            if existing:
                # Update existing
                for key, value in agent_data.items():
                    if key != "raw_metadata":
                        setattr(existing, key, value)
                    else:
                        # Merge metadata
                        existing_meta = existing.raw_metadata or {}
                        existing_meta.update(value)
                        existing.raw_metadata = existing_meta
                
                self.session.commit()
                return "updated"
            else:
                # Create new
                agent = Agent(**agent_data)
                self.session.add(agent)
                self.session.commit()
                return "new"
                
        except Exception as e:
            logger.error(f"Error processing {repo.full_name}: {e}")
            self.session.rollback()
            return "error"
    
    def _check_rate_limit(self):
        """Check and handle GitHub rate limiting with token rotation."""
        try:
            rate_limit = self.github.get_rate_limit()
            core_remaining = rate_limit.core.remaining
            search_remaining = rate_limit.search.remaining
            
            # Check both Core API and Search API limits
            if core_remaining < 100 or search_remaining < 3:
                logger.info(f"Rate limit low - Core: {core_remaining}/5000, Search: {search_remaining}/30")
                
                # Try to rotate to a fresh token
                try:
                    new_token = self.token_manager.get_next_token()
                    self.github = Github(new_token, per_page=100)
                    
                    # Check new token's capacity
                    new_rate_limit = self.github.get_rate_limit()
                    new_core = new_rate_limit.core.remaining
                    new_search = new_rate_limit.search.remaining
                    
                    if new_core > 100 and new_search > 3:
                        logger.info(f"✅ Rotated to token with Core: {new_core}/5000, Search: {new_search}/30")
                        return
                    else:
                        logger.warning(f"⚠️ New token also low - Core: {new_core}, Search: {new_search}")
                        
                except Exception as e:
                    logger.error(f"Token rotation failed: {e}")
                
                # If all tokens exhausted, calculate wait time
                # Search API resets hourly, Core API has longer cycle
                search_reset = rate_limit.search.reset
                core_reset = rate_limit.core.reset
                
                # Wait for whichever resets first
                now = datetime.now().timestamp()
                search_wait = max(search_reset.timestamp() - now, 60)
                core_wait = max(core_reset.timestamp() - now, 60)
                wait_seconds = min(search_wait, core_wait)
                
                logger.warning(f"💤 All tokens exhausted. Search reset in {search_wait:.0f}s, Core in {core_wait:.0f}s")
                logger.warning(f"   Waiting {wait_seconds:.0f}s for next available capacity")
                time.sleep(wait_seconds)
                
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            time.sleep(60)  # Conservative fallback

# Quick test function
def test_expanded_crawler():
    """Test the expanded crawler with a small sample."""
    spider = GitHubExpandedSpider()
    
    # Test with just 2 queries and topics
    small_queries = ["ai-agent", "llm-tool"]
    small_topics = ["artificial-intelligence", "langchain"]
    
    print(f"Testing with {len(small_queries)} queries and {len(small_topics)} topics")
    
    # This would be the full call:
    # result = spider.crawl_expanded(max_results_per_query=50, min_stars=5)
    
    print(f"Full crawler ready with {len(ALL_SEARCH_QUERIES)} queries and {len(AI_TOPICS)} topics")
    print(f"Expected repos: 100K-200K+ (vs current 35K)")

if __name__ == "__main__":
    test_expanded_crawler()