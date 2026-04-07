"""
Docker Hub Spider

Crawls AI/ML containers from Docker Hub registry.
Focuses on containers tagged with ai, ml, pytorch, tensorflow, etc.

API: https://hub.docker.com/v2/repositories/
Rate limit: ~100 req/min
"""

import logging
import asyncio
import aiohttp
import time
from typing import Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger("agentindex.spiders.dockerhub")

class DockerHubSpider:
    """Docker Hub AI/ML container crawler."""
    
    def __init__(self):
        self.base_url = "https://hub.docker.com/v2"
        self.session = None
        self.rate_limit_delay = 0.6  # ~100 requests/min
        
        # AI/ML related tags and keywords
        self.ai_ml_tags = [
            "ai", "ml", "machine-learning", "deep-learning", 
            "pytorch", "tensorflow", "keras", "sklearn",
            "transformers", "langchain", "openai", "huggingface",
            "jupyter", "numpy", "pandas", "opencv",
            "cuda", "gpu", "nvidia", "ai-tools"
        ]
        
        # Popular AI/ML organizations to prioritize
        self.priority_orgs = [
            "tensorflow", "pytorch", "jupyter", "nvidia", 
            "huggingface", "openai", "langchain-ai",
            "microsoft", "google", "amazon", "apache"
        ]
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={'User-Agent': 'AgentIndex-Crawler/1.0'}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def search_repositories(self, query: str, page_size: int = 25, max_pages: int = 10) -> List[Dict]:
        """Search Docker Hub repositories by query."""
        repositories = []
        
        for page in range(1, max_pages + 1):
            url = f"{self.base_url}/repositories/library/?page={page}&page_size={page_size}&q={quote(query)}"
            
            try:
                await asyncio.sleep(self.rate_limit_delay)
                
                async with self.session.get(url) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch page {page} for query '{query}': {response.status}")
                        continue
                    
                    data = await response.json()
                    results = data.get('results', [])
                    
                    if not results:
                        logger.info(f"No more results for query '{query}' at page {page}")
                        break
                    
                    repositories.extend(results)
                    logger.info(f"Query '{query}' page {page}: {len(results)} repositories")
                    
            except Exception as e:
                logger.error(f"Error fetching page {page} for query '{query}': {e}")
                continue
        
        return repositories
    
    async def get_repository_details(self, repo_name: str) -> Optional[Dict]:
        """Get detailed information about a specific repository."""
        url = f"{self.base_url}/repositories/{repo_name}/"
        
        try:
            await asyncio.sleep(self.rate_limit_delay)
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch details for {repo_name}: {response.status}")
                    return None
                
                return await response.json()
                
        except Exception as e:
            logger.error(f"Error fetching details for {repo_name}: {e}")
            return None
    
    async def get_repository_tags(self, repo_name: str, limit: int = 10) -> List[Dict]:
        """Get tags/versions for a repository."""
        url = f"{self.base_url}/repositories/{repo_name}/tags/?page_size={limit}"
        
        try:
            await asyncio.sleep(self.rate_limit_delay)
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    return []
                
                data = await response.json()
                return data.get('results', [])
                
        except Exception as e:
            logger.error(f"Error fetching tags for {repo_name}: {e}")
            return []
    
    def extract_agent_data(self, repo_data: Dict, tags: List[Dict]) -> Dict:
        """Extract agent data from repository information."""
        
        # Extract key information
        name = repo_data.get('name', '')
        namespace = repo_data.get('namespace', '')
        full_name = f"{namespace}/{name}" if namespace else name
        
        description = repo_data.get('description', '') or repo_data.get('short_description', '')
        
        # Get latest tag info
        latest_tag = None
        if tags:
            # Find 'latest' tag or use first tag
            latest_tag = next((tag for tag in tags if tag.get('name') == 'latest'), tags[0])
        
        # Calculate relevance score based on various factors
        relevance_score = self._calculate_relevance(repo_data, description)
        
        return {
            'name': full_name,
            'description': description,
            'source': 'dockerhub',
            'source_url': f"https://hub.docker.com/r/{full_name}",
            'stars': repo_data.get('star_count', 0),
            'pulls': repo_data.get('pull_count', 0),
            'last_updated': repo_data.get('last_updated'),
            'is_official': repo_data.get('is_official', False),
            'is_automated': repo_data.get('is_automated', False),
            'category': self._detect_category(description, name),
            'relevance_score': relevance_score,
            'raw_metadata': {
                'repo_data': repo_data,
                'tags': tags[:3] if tags else [],  # Keep top 3 tags
                'docker_hub': True
            }
        }
    
    def _calculate_relevance(self, repo_data: Dict, description: str) -> float:
        """Calculate how relevant this container is as an AI agent/tool."""
        score = 0.0
        
        # Base score from pull count (logarithmic scaling)
        pulls = repo_data.get('pull_count', 0)
        if pulls > 0:
            score += min(3.0, pulls / 100000)  # Max 3 points for popularity
        
        # Star count bonus
        stars = repo_data.get('star_count', 0)
        score += min(2.0, stars / 100)  # Max 2 points for stars
        
        # Official image bonus
        if repo_data.get('is_official', False):
            score += 1.0
        
        # AI/ML keyword matching in description
        text_content = f"{description} {repo_data.get('name', '')}".lower()
        ai_keywords = ['ai', 'machine learning', 'deep learning', 'neural', 'model', 
                       'pytorch', 'tensorflow', 'transformers', 'langchain', 'llm']
        
        keyword_matches = sum(1 for keyword in ai_keywords if keyword in text_content)
        score += min(3.0, keyword_matches * 0.5)  # Max 3 points for keyword relevance
        
        return round(score, 2)
    
    def _detect_category(self, description: str, name: str) -> str:
        """Detect the category of AI container based on description."""
        text = f"{description} {name}".lower()
        
        if any(word in text for word in ['jupyter', 'notebook', 'lab']):
            return 'development_environment'
        elif any(word in text for word in ['pytorch', 'tensorflow', 'keras', 'training']):
            return 'ml_framework'
        elif any(word in text for word in ['api', 'server', 'service', 'endpoint']):
            return 'ai_service'
        elif any(word in text for word in ['gpu', 'cuda', 'nvidia']):
            return 'gpu_computing'
        elif any(word in text for word in ['langchain', 'llm', 'chat', 'assistant']):
            return 'ai_agent'
        else:
            return 'ai_tool'
    
    async def crawl(self, max_results_per_query: int = 100) -> Dict:
        """Main crawl method."""
        start_time = time.time()
        logger.info("Starting Docker Hub crawl for AI/ML containers")
        
        async with self:
            all_repositories = []
            processed_repos = set()  # Avoid duplicates
            
            # Search by AI/ML tags
            for tag in self.ai_ml_tags:
                logger.info(f"Searching for tag: {tag}")
                
                repos = await self.search_repositories(
                    query=tag,
                    max_pages=max_results_per_query // 25
                )
                
                for repo in repos:
                    repo_name = repo.get('name', '')
                    namespace = repo.get('namespace', '')
                    full_name = f"{namespace}/{repo_name}" if namespace else repo_name
                    
                    if full_name not in processed_repos:
                        processed_repos.add(full_name)
                        all_repositories.append(repo)
                
                logger.info(f"Tag '{tag}': Found {len(repos)} repositories")
            
            # Get detailed information and tags for each repository
            detailed_repositories = []
            
            for repo in all_repositories[:max_results_per_query * len(self.ai_ml_tags)]:
                repo_name = repo.get('name', '')
                namespace = repo.get('namespace', '')
                full_name = f"{namespace}/{repo_name}" if namespace else repo_name
                
                # Get detailed repo info
                details = await self.get_repository_details(full_name)
                if not details:
                    continue
                
                # Get tags
                tags = await self.get_repository_tags(full_name, limit=5)
                
                # Extract agent data
                agent_data = self.extract_agent_data(details, tags)
                
                # Filter out very low relevance containers
                if agent_data['relevance_score'] >= 0.5:
                    detailed_repositories.append(agent_data)
                
                if len(detailed_repositories) % 50 == 0:
                    logger.info(f"Processed {len(detailed_repositories)} relevant containers...")
        
        end_time = time.time()
        duration = end_time - start_time
        
        stats = {
            'source': 'dockerhub',
            'total_found': len(detailed_repositories),
            'duration_seconds': round(duration, 2),
            'avg_per_second': round(len(detailed_repositories) / duration, 2) if duration > 0 else 0,
            'repositories': detailed_repositories
        }
        
        logger.info(f"Docker Hub crawl completed: {len(detailed_repositories)} AI/ML containers in {duration:.1f}s")
        
        return stats

# Test function
async def test_dockerhub_spider():
    """Test the Docker Hub spider with a small sample."""
    spider = DockerHubSpider()
    
    async with spider:
        # Test search
        results = await spider.search_repositories("pytorch", max_pages=2)
        print(f"Found {len(results)} PyTorch repositories")
        
        if results:
            # Test details
            first_repo = results[0]
            repo_name = first_repo.get('name', '')
            namespace = first_repo.get('namespace', '')
            full_name = f"{namespace}/{repo_name}" if namespace else repo_name
            
            details = await spider.get_repository_details(full_name)
            tags = await spider.get_repository_tags(full_name)
            
            agent_data = spider.extract_agent_data(details, tags)
            print(f"Sample agent data: {agent_data}")

if __name__ == "__main__":
    asyncio.run(test_dockerhub_spider())