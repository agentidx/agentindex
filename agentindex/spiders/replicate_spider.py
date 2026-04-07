"""
Replicate Models Spider

Crawls AI models from Replicate.com registry.
Focuses on open-source AI models across text, image, audio, video domains.

API: https://replicate.com/api/models
Rate limit: ~60 req/min
"""

import logging
import asyncio
import aiohttp
import time
from typing import Dict, List, Optional

logger = logging.getLogger("agentindex.spiders.replicate")

class ReplicateSpider:
    """Replicate AI models crawler."""
    
    def __init__(self):
        self.base_url = "https://replicate.com/api"
        self.session = None
        self.rate_limit_delay = 1.0  # ~60 requests/min
        
        # Model categories to focus on
        self.priority_categories = [
            "text", "image", "audio", "video", "multimodal",
            "language-model", "image-generation", "speech",
            "computer-vision", "natural-language-processing"
        ]
        
        # Popular model owners to prioritize
        self.priority_owners = [
            "stability-ai", "openai", "meta", "google-deepmind", 
            "anthropic", "huggingface", "microsoft", "mistralai",
            "bytedance", "salesforce", "databricks", "cohere"
        ]
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'AgentIndex-Crawler/1.0',
                'Accept': 'application/json'
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_models_page(self, cursor: Optional[str] = None, limit: int = 20) -> Dict:
        """Get a page of models from Replicate."""
        url = f"{self.base_url}/models"
        params = {'limit': limit}
        if cursor:
            params['cursor'] = cursor
        
        try:
            await asyncio.sleep(self.rate_limit_delay)
            
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch models page: {response.status}")
                    return {}
                
                return await response.json()
                
        except Exception as e:
            logger.error(f"Error fetching models page: {e}")
            return {}
    
    async def search_models(self, query: str, limit: int = 50) -> List[Dict]:
        """Search models by query."""
        url = f"{self.base_url}/models"
        params = {'query': query, 'limit': limit}
        
        try:
            await asyncio.sleep(self.rate_limit_delay)
            
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.warning(f"Failed to search models for '{query}': {response.status}")
                    return []
                
                data = await response.json()
                return data.get('results', [])
                
        except Exception as e:
            logger.error(f"Error searching models for '{query}': {e}")
            return []
    
    async def get_model_details(self, owner: str, name: str) -> Optional[Dict]:
        """Get detailed information about a specific model."""
        url = f"{self.base_url}/models/{owner}/{name}"
        
        try:
            await asyncio.sleep(self.rate_limit_delay)
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch model {owner}/{name}: {response.status}")
                    return None
                
                return await response.json()
                
        except Exception as e:
            logger.error(f"Error fetching model {owner}/{name}: {e}")
            return None
    
    async def get_model_versions(self, owner: str, name: str, limit: int = 5) -> List[Dict]:
        """Get versions for a specific model."""
        url = f"{self.base_url}/models/{owner}/{name}/versions"
        params = {'limit': limit}
        
        try:
            await asyncio.sleep(self.rate_limit_delay)
            
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    return []
                
                data = await response.json()
                return data.get('results', [])
                
        except Exception as e:
            logger.error(f"Error fetching versions for {owner}/{name}: {e}")
            return []
    
    def extract_agent_data(self, model_data: Dict, versions: List[Dict]) -> Dict:
        """Extract agent data from model information."""
        
        # Extract key information
        owner = model_data.get('owner', '')
        name = model_data.get('name', '')
        full_name = f"{owner}/{name}"
        
        description = model_data.get('description', '')
        
        # Get latest version info
        latest_version = versions[0] if versions else {}
        
        # Calculate relevance and popularity
        run_count = model_data.get('run_count', 0)
        github_url = model_data.get('github_url', '')
        
        # Model capabilities and category
        category = self._detect_category(model_data, description)
        capabilities = self._extract_capabilities(model_data, description)
        
        return {
            'name': full_name,
            'description': description,
            'source': 'replicate',
            'source_url': f"https://replicate.com/{owner}/{name}",
            'stars': 0,  # Replicate doesn't have stars, use run_count as popularity
            'run_count': run_count,
            'github_url': github_url,
            'owner': owner,
            'visibility': model_data.get('visibility', 'public'),
            'category': category,
            'capabilities': capabilities,
            'paper_url': model_data.get('paper_url'),
            'license_url': model_data.get('license_url'),
            'created_at': model_data.get('created_at'),
            'updated_at': model_data.get('updated_at'),
            'relevance_score': self._calculate_relevance(model_data, run_count),
            'raw_metadata': {
                'model_data': model_data,
                'latest_version': latest_version,
                'total_versions': len(versions),
                'replicate': True
            }
        }
    
    def _detect_category(self, model_data: Dict, description: str) -> str:
        """Detect the category of AI model based on metadata."""
        
        # Check cover_image_url and description for clues
        text = f"{description} {model_data.get('name', '')}".lower()
        
        if any(word in text for word in ['text', 'language', 'llm', 'chat', 'conversation', 'instruction']):
            return 'language_model'
        elif any(word in text for word in ['image', 'vision', 'visual', 'photo', 'picture', 'generate']):
            if any(word in text for word in ['generate', 'create', 'synthesis', 'diffusion', 'dalle']):
                return 'image_generation'
            else:
                return 'computer_vision'
        elif any(word in text for word in ['audio', 'speech', 'voice', 'sound', 'music']):
            return 'audio_processing'
        elif any(word in text for word in ['video', 'motion', 'animation']):
            return 'video_processing'
        elif any(word in text for word in ['embedding', 'vector', 'similarity']):
            return 'embedding_model'
        elif any(word in text for word in ['code', 'programming', 'coding']):
            return 'code_generation'
        else:
            return 'ai_model'
    
    def _extract_capabilities(self, model_data: Dict, description: str) -> List[str]:
        """Extract capabilities from model description and metadata."""
        capabilities = []
        text = f"{description} {model_data.get('name', '')}".lower()
        
        capability_keywords = {
            'text_generation': ['generate', 'completion', 'writing'],
            'text_analysis': ['analyze', 'sentiment', 'classification'],
            'image_generation': ['generate', 'create', 'synthesis', 'diffusion'],
            'image_analysis': ['detect', 'classify', 'recognize', 'caption'],
            'audio_generation': ['synthesize', 'voice', 'tts'],
            'audio_analysis': ['transcribe', 'stt', 'recognition'],
            'video_generation': ['animate', 'motion'],
            'video_analysis': ['action', 'detection'],
            'question_answering': ['qa', 'question', 'answer'],
            'translation': ['translate', 'multilingual'],
            'summarization': ['summarize', 'summary'],
            'embedding': ['embed', 'vector', 'similarity']
        }
        
        for capability, keywords in capability_keywords.items():
            if any(keyword in text for keyword in keywords):
                capabilities.append(capability)
        
        return capabilities[:5]  # Limit to top 5 capabilities
    
    def _calculate_relevance(self, model_data: Dict, run_count: int) -> float:
        """Calculate how relevant this model is as an AI agent/tool."""
        score = 0.0
        
        # Base score from run count (logarithmic scaling)
        if run_count > 0:
            import math
            score += min(4.0, math.log10(run_count + 1))  # Max 4 points for popularity
        
        # GitHub integration bonus
        if model_data.get('github_url'):
            score += 1.0
        
        # Paper/research bonus
        if model_data.get('paper_url'):
            score += 0.5
        
        # License availability bonus
        if model_data.get('license_url'):
            score += 0.5
        
        # Visibility bonus (public models preferred)
        if model_data.get('visibility') == 'public':
            score += 0.5
        
        # Recent activity bonus
        updated_at = model_data.get('updated_at', '')
        if updated_at and '2024' in updated_at:  # Recent updates
            score += 1.0
        elif updated_at and '2023' in updated_at:
            score += 0.5
        
        return round(score, 2)
    
    async def crawl_all_models(self, max_models: int = 5000) -> List[Dict]:
        """Crawl all models using pagination."""
        all_models = []
        cursor = None
        
        while len(all_models) < max_models:
            logger.info(f"Fetching models page... (collected: {len(all_models)})")
            
            page_data = await self.get_models_page(cursor=cursor, limit=50)
            
            if not page_data:
                break
            
            models = page_data.get('results', [])
            if not models:
                break
            
            all_models.extend(models)
            
            # Check for next page
            next_cursor = page_data.get('next')
            if not next_cursor:
                break
            
            cursor = next_cursor
            
            # Respect rate limits
            await asyncio.sleep(0.5)
        
        return all_models[:max_models]
    
    async def crawl_by_search(self, max_results_per_query: int = 50) -> List[Dict]:
        """Crawl models using search queries."""
        all_models = []
        processed_models = set()
        
        # Search terms for different AI domains
        search_terms = [
            "language model", "text generation", "llm", "chat",
            "image generation", "diffusion", "dalle", "stable diffusion",
            "computer vision", "object detection", "classification",
            "audio generation", "speech synthesis", "tts",
            "video generation", "animation", 
            "embedding", "vector", "similarity",
            "code generation", "programming"
        ]
        
        for term in search_terms:
            logger.info(f"Searching for: {term}")
            
            models = await self.search_models(term, limit=max_results_per_query)
            
            for model in models:
                owner = model.get('owner', '')
                name = model.get('name', '')
                full_name = f"{owner}/{name}"
                
                if full_name not in processed_models:
                    processed_models.add(full_name)
                    all_models.append(model)
            
            logger.info(f"Search '{term}': Found {len(models)} models")
        
        return all_models
    
    async def crawl(self, max_results_total: int = 10000) -> Dict:
        """Main crawl method."""
        start_time = time.time()
        logger.info("Starting Replicate models crawl")
        
        async with self:
            # Try both crawl strategies
            logger.info("Crawling all models via pagination...")
            paginated_models = await self.crawl_all_models(max_models=max_results_total // 2)
            
            logger.info("Crawling models via search...")
            searched_models = await self.crawl_by_search(max_results_per_query=50)
            
            # Combine and deduplicate
            all_models = []
            processed_models = set()
            
            for model in paginated_models + searched_models:
                owner = model.get('owner', '')
                name = model.get('name', '')
                full_name = f"{owner}/{name}"
                
                if full_name not in processed_models:
                    processed_models.add(full_name)
                    all_models.append(model)
            
            # Get detailed information for each model
            detailed_models = []
            
            for model in all_models[:max_results_total]:
                owner = model.get('owner', '')
                name = model.get('name', '')
                
                if not owner or not name:
                    continue
                
                # Get model details and versions
                details = await self.get_model_details(owner, name)
                if not details:
                    continue
                
                versions = await self.get_model_versions(owner, name, limit=3)
                
                # Extract agent data
                agent_data = self.extract_agent_data(details, versions)
                
                # Filter out very low relevance models
                if agent_data['relevance_score'] >= 1.0:
                    detailed_models.append(agent_data)
                
                if len(detailed_models) % 100 == 0:
                    logger.info(f"Processed {len(detailed_models)} relevant models...")
        
        end_time = time.time()
        duration = end_time - start_time
        
        stats = {
            'source': 'replicate',
            'total_found': len(detailed_models),
            'duration_seconds': round(duration, 2),
            'avg_per_second': round(len(detailed_models) / duration, 2) if duration > 0 else 0,
            'models': detailed_models
        }
        
        logger.info(f"Replicate crawl completed: {len(detailed_models)} models in {duration:.1f}s")
        
        return stats

# Test function
async def test_replicate_spider():
    """Test the Replicate spider with a small sample."""
    spider = ReplicateSpider()
    
    async with spider:
        # Test search
        results = await spider.search_models("language model", limit=5)
        print(f"Found {len(results)} language models")
        
        if results:
            # Test details
            first_model = results[0]
            owner = first_model.get('owner', '')
            name = first_model.get('name', '')
            
            details = await spider.get_model_details(owner, name)
            versions = await spider.get_model_versions(owner, name)
            
            agent_data = spider.extract_agent_data(details, versions)
            print(f"Sample agent data: {agent_data}")

if __name__ == "__main__":
    asyncio.run(test_replicate_spider())