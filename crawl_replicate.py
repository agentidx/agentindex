"""
Replicate.com Spider for AI Models
Priority A source: 30,000+ AI models and inference APIs
"""

import requests
import time
import logging
import os
from datetime import datetime
from agentindex.db.models import Agent, get_session
from agentindex.db.models import safe_commit
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [replicate] %(message)s")
logger = logging.getLogger("replicate_crawler")

class ReplicateCrawler:
    """Crawl Replicate.com for AI models."""
    
    def __init__(self):
        self.base_url = "https://api.replicate.com/v1"
        self.session = get_session()
        
        # Get API token from environment
        self.api_token = os.getenv('REPLICATE_API_TOKEN')
        if not self.api_token:
            raise ValueError("REPLICATE_API_TOKEN environment variable is required")
            
        self.headers = {
            'User-Agent': 'AgentIndex/1.0 (https://agentcrawl.dev)',
            'Authorization': f'Bearer {self.api_token}'
        }
        
    def get_models(self, next_url: str = None) -> dict:
        """Get models from Replicate API."""
        if next_url:
            # Use the full next URL provided by the API
            url = next_url
        else:
            # First request
            url = f"{self.base_url}/models"
            
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching models: {e}")
            return None
    
    def get_model_details(self, owner: str, name: str) -> dict:
        """Get detailed model information."""
        url = f"{self.base_url}/models/{owner}/{name}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching model {owner}/{name}: {e}")
            return None
    
    def model_to_agent(self, model: dict, details: dict = None) -> dict:
        """Convert Replicate model to Agent format."""
        owner = model.get('owner', '') or ''
        name = model.get('name', '') or ''
        
        # Skip models with missing critical data
        if not name or not owner:
            raise ValueError(f"Model missing name or owner: {model}")
            
        full_name = f"{owner}/{name}"
        
        # Use details if available, otherwise base model data
        data = details if details else model
        
        return {
            'source': 'replicate',
            'source_url': f"https://replicate.com/{full_name}",
            'source_id': full_name,
            'name': name,
            'description': data.get('description', ''),
            'author': owner,
            'license': data.get('license'),
            'downloads': data.get('run_count', 0),
            'last_source_update': self._parse_date(data.get('latest_version', {}).get('created_at')),
            'tags': self._extract_tags(data),
            'protocols': ['replicate_api', 'rest'],
            'invocation': {
                'type': 'api',
                'endpoint': f'https://api.replicate.com/v1/models/{full_name}/predictions',
                'protocol': 'rest',
                'method': 'POST'
            },
            'pricing': self._extract_pricing(data),
            'raw_metadata': data,
            'first_indexed': datetime.utcnow(),
            'last_crawled': datetime.utcnow(),
            'crawl_status': 'indexed'
        }
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse Replicate date string."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return None
    
    def _extract_tags(self, model: dict) -> list:
        """Extract tags from model metadata."""
        tags = []
        
        # From description
        description = (model.get('description', '') + ' ' + 
                      model.get('name', '')).lower()
        
        # Model type detection
        if any(term in description for term in ['text', 'language', 'gpt', 'llm']):
            tags.append('text-generation')
        if any(term in description for term in ['image', 'visual', 'diffusion', 'dalle']):
            tags.append('image-generation')
        if any(term in description for term in ['audio', 'speech', 'sound']):
            tags.append('audio')
        if any(term in description for term in ['video', 'animation']):
            tags.append('video')
        if any(term in description for term in ['agent', 'assistant', 'chat']):
            tags.append('agent')
            
        # From GitHub topics if available
        github = model.get('github_url', '')
        if github:
            tags.append('open-source')
            
        return tags[:5]
    
    def _extract_pricing(self, model: dict) -> dict:
        """Extract pricing information."""
        latest_version = model.get('latest_version', {})
        
        if latest_version.get('cog_version'):
            return {'model': 'pay_per_run', 'note': 'Compute usage based'}
        else:
            return {'model': 'free'}
    
    def crawl_models(self, max_models=None):
        """Crawl models from Replicate with optional limit."""
        total_new = 0
        total_updated = 0
        total_processed = 0
        next_url = None
        page = 1
        
        while True:
            # Check if we've reached the limit
            if max_models and total_processed >= max_models:
                logger.info(f"Reached limit of {max_models} models")
                break
            logger.info(f"🔄 Fetching page {page} from Replicate...")
            data = self.get_models(next_url)
            
            if not data or not data.get('results'):
                break
                
            models = data.get('results', [])
            new_count = 0
            updated_count = 0
            
            for model in models:
                try:
                    # Check limit per model
                    if max_models and total_processed >= max_models:
                        break
                        
                    agent_data = self.model_to_agent(model)
                    
                    # Check if exists
                    existing = self.session.query(Agent).filter_by(
                        source='replicate',
                        source_id=agent_data['source_id']
                    ).first()
                    
                    if existing:
                        # Update existing
                        existing.last_crawled = datetime.utcnow()
                        existing.downloads = agent_data['downloads']
                        existing.last_source_update = agent_data['last_source_update']
                        existing.description = agent_data['description']
                        updated_count += 1
                    else:
                        # Create new agent
                        agent = Agent(**agent_data)
                        agent.id = uuid.uuid4()
                        self.session.add(agent)
                        new_count += 1
                    
                    total_processed += 1
                        
                    if (new_count + updated_count) % 50 == 0:
                        safe_commit(self.session)
                        logger.info(f"Page {page} progress: {new_count} new, {updated_count} updated")
                        
                except Exception as e:
                    logger.error(f"Error processing model {model.get('name')}: {e}")
                    continue
            
            safe_commit(self.session)
            logger.info(f"Page {page} complete: {new_count} new, {updated_count} updated")
            
            total_new += new_count
            total_updated += updated_count
            
            # Check for next page
            next_url = data.get('next')
            if not next_url:
                break
                
            page += 1
            time.sleep(1)  # Rate limiting
        
        logger.info(f"🔄 Replicate crawl complete: {total_new} new agents, {total_updated} updated, {total_processed} processed")
        return {'new': total_new, 'updated': total_updated, 'processed': total_processed, 'errors': 0}
    
    def crawl_all_models(self):
        """Crawl all models from Replicate without limit."""
        return self.crawl_models()

if __name__ == "__main__":
    crawler = ReplicateCrawler()
    result = crawler.crawl_all_models()
    print(f"Replicate crawl result: {result}")