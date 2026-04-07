#!/usr/bin/env python3
"""
Replicate.com Crawler - FIXED VERSION
KORREKT API endpoint: https://api.replicate.com/v1/models
"""

import requests
import time
import logging
import os
from datetime import datetime, timedelta
from agentindex.db.models import Agent, get_session
import uuid
import traceback

logging.basicConfig(level=logging.INFO, format="%(asctime)s [replicate] %(message)s")
logger = logging.getLogger("replicate_crawler_fixed")

class ReplicateFixedCrawler:
    """Fixed Replicate crawler with correct API endpoint and auth."""
    
    def __init__(self):
        # CORRECT API base URL
        self.base_url = "https://api.replicate.com/v1"
        self.session = get_session()
        
        # Try to get API key from environment
        self.api_key = os.getenv('REPLICATE_API_TOKEN') or os.getenv('REPLICATE_API_KEY')
        
        # Headers with auth if available
        self.headers = {
            'User-Agent': 'AgentIndex/1.0 (https://agentcrawl.dev)',
            'Accept': 'application/json'
        }
        
        if self.api_key:
            self.headers['Authorization'] = f'Bearer {self.api_key}'
            logger.info("✅ API key loaded from environment")
        else:
            logger.warning("⚠️ No REPLICATE_API_TOKEN found - will try public endpoints")
            
    def test_api_access(self) -> bool:
        """Test if we can access Replicate API."""
        url = f"{self.base_url}/models"
        
        try:
            response = requests.get(url, headers=self.headers, params={'limit': 1})
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ API access OK - Found {len(data.get('results', []))} models in test")
                return True
            elif response.status_code == 401:
                logger.error("❌ API authentication failed - need valid REPLICATE_API_TOKEN")
                logger.error(f"Response: {response.text}")
                return False
            else:
                logger.error(f"❌ API access failed - HTTP {response.status_code}")
                logger.error(f"Response: {response.text[:200]}")
                return False
                
        except Exception as e:
            logger.error(f"❌ API test error: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def get_models_page(self, cursor: str = None, limit: int = 20) -> dict:
        """Get a page of models from Replicate API."""
        url = f"{self.base_url}/models"
        params = {'limit': limit}
        
        if cursor:
            params['cursor'] = cursor
            
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching models page: {e}")
            return None
    
    def model_to_agent(self, model: dict) -> dict:
        """Convert Replicate model to Agent format."""
        # Extract model details
        owner = model.get('owner', '')
        name = model.get('name', '')
        full_name = f"{owner}/{name}"
        
        return {
            'source': 'replicate',
            'source_url': model.get('url', f'https://replicate.com/{full_name}'),
            'source_id': full_name,
            'name': name,
            'description': model.get('description', ''),
            'author': owner,
            'stars': 0,  # Replicate doesn't expose star count via API
            'downloads': model.get('run_count', 0),
            'last_source_update': self._parse_date(model.get('latest_version', {}).get('created_at')),
            'tags': self._extract_tags(model),
            'protocols': ['replicate_api', 'rest'],
            'invocation': {
                'type': 'api',
                'endpoint': f'https://api.replicate.com/v1/models/{full_name}/predictions',
                'protocol': 'rest',
                'method': 'POST',
                'docs': f'https://replicate.com/{full_name}'
            },
            'pricing': {
                'model': 'pay_per_use',
                'currency': 'USD'
            },
            'raw_metadata': model,
            'first_indexed': datetime.now(),
            'last_crawled': datetime.now(),
            'crawl_status': 'indexed',
            # EU compliance defaults
            'eu_risk_class': None,
            'eu_risk_confidence': None,
            'compliance_score': None,
            'last_compliance_check': None
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
        description = (model.get('description', '') + ' ' + 
                      model.get('name', '')).lower()
        
        # Common AI model terms
        ai_terms = ['image', 'text', 'video', 'audio', 'diffusion', 'generation', 
                   'llm', 'classification', 'detection', 'segmentation', 'upscaling']
        
        for term in ai_terms:
            if term in description:
                tags.append(term)
                
        return tags[:5]  # Limit tags
    
    def crawl_batch(self, batch_size: int = 100) -> dict:
        """Crawl a batch of models (for testing)."""
        logger.info(f"🚀 Starting Replicate batch crawl ({batch_size} models)")
        
        if not self.test_api_access():
            return {'success': False, 'error': 'API access failed'}
        
        stats = {
            'models_found': 0,
            'models_new': 0,
            'models_updated': 0,
            'errors': 0,
            'success': True
        }
        
        cursor = None
        total_processed = 0
        
        while total_processed < batch_size:
            # Get page of models
            page_data = self.get_models_page(cursor, min(20, batch_size - total_processed))
            
            if not page_data:
                logger.error("Failed to get models page")
                stats['errors'] += 1
                break
                
            models = page_data.get('results', [])
            if not models:
                logger.info("No more models to process")
                break
            
            logger.info(f"Processing page with {len(models)} models...")
            
            # Process each model in batch
            for model in models:
                try:
                    agent_data = self.model_to_agent(model)
                    
                    # Check if exists
                    existing = self.session.query(Agent).filter_by(
                        source='replicate',
                        source_id=agent_data['source_id']
                    ).first()
                    
                    if existing:
                        # Update existing
                        existing.last_crawled = datetime.now()
                        existing.downloads = agent_data['downloads']
                        existing.last_source_update = agent_data['last_source_update']
                        stats['models_updated'] += 1
                    else:
                        # Create new agent
                        agent = Agent(**agent_data)
                        agent.id = uuid.uuid4()
                        self.session.add(agent)
                        stats['models_new'] += 1
                    
                    # Individual commit per agent (robust error handling)
                    try:
                        self.session.commit()
                    except Exception as commit_error:
                        logger.error(f"Commit error for model {model.get('name', 'unknown')}: {commit_error}")
                        self.session.rollback()
                        self.session.close()
                        self.session = get_session()
                        stats['errors'] += 1
                        continue
                    
                    stats['models_found'] += 1
                    total_processed += 1
                    
                    if total_processed % 10 == 0:
                        logger.info(f"Progress: {total_processed}/{batch_size} models processed")
                        
                except Exception as e:
                    logger.error(f"Error processing model {model.get('name', 'unknown')}: {e}")
                    stats['errors'] += 1
                    continue
            
            # Get next page cursor
            cursor = page_data.get('next')
            if not cursor:
                logger.info("No more pages available")
                break
                
            time.sleep(1)  # Rate limiting
        
        logger.info(f"🎯 Batch crawl complete: {stats['models_new']} new, {stats['models_updated']} updated, {stats['errors']} errors")
        return stats
    
    def crawl_all_models(self, sustained_rate_limit: int = 5000) -> dict:
        """Crawl all Replicate models with sustained rate limiting."""
        logger.info(f"🚀 Starting FULL Replicate crawl (sustained rate: {sustained_rate_limit}/day)")
        
        if not self.test_api_access():
            return {'success': False, 'error': 'API access failed'}
        
        stats = {
            'models_found': 0,
            'models_new': 0,
            'models_updated': 0,
            'errors': 0,
            'success': True,
            'pages_processed': 0
        }
        
        cursor = None
        daily_count = 0
        start_time = time.time()
        
        while True:
            # Rate limiting - don't exceed daily limit
            if daily_count >= sustained_rate_limit:
                elapsed_hours = (time.time() - start_time) / 3600
                if elapsed_hours < 24:
                    wait_time = (24 - elapsed_hours) * 3600
                    logger.info(f"Daily rate limit reached ({sustained_rate_limit}), waiting {wait_time/3600:.1f}h")
                    time.sleep(wait_time)
                daily_count = 0
                start_time = time.time()
            
            # Get page of models  
            page_data = self.get_models_page(cursor, 20)
            
            if not page_data:
                logger.error("Failed to get models page")
                stats['errors'] += 1
                break
                
            models = page_data.get('results', [])
            if not models:
                logger.info("✅ All models processed!")
                break
            
            stats['pages_processed'] += 1
            logger.info(f"📄 Page {stats['pages_processed']}: {len(models)} models")
            
            # Process models on page
            for model in models:
                try:
                    agent_data = self.model_to_agent(model)
                    
                    # Check if exists
                    existing = self.session.query(Agent).filter_by(
                        source='replicate',
                        source_id=agent_data['source_id']
                    ).first()
                    
                    if existing:
                        existing.last_crawled = datetime.now()
                        existing.downloads = agent_data['downloads']
                        existing.last_source_update = agent_data['last_source_update']
                        stats['models_updated'] += 1
                    else:
                        agent = Agent(**agent_data)
                        agent.id = uuid.uuid4()
                        self.session.add(agent)
                        stats['models_new'] += 1
                    
                    # Individual commit per agent
                    try:
                        self.session.commit()
                    except Exception as commit_error:
                        logger.error(f"Commit error for model {model.get('name', 'unknown')}: {commit_error}")
                        self.session.rollback()
                        self.session.close()
                        self.session = get_session()
                        stats['errors'] += 1
                        continue
                    
                    stats['models_found'] += 1
                    daily_count += 1
                    
                except Exception as e:
                    logger.error(f"Error processing model {model.get('name', 'unknown')}: {e}")
                    stats['errors'] += 1
                    continue
            
            # Progress report
            if stats['pages_processed'] % 10 == 0:
                logger.info(f"📊 Progress: {stats['pages_processed']} pages, {stats['models_found']} models, {stats['models_new']} new")
            
            # Get next page
            cursor = page_data.get('next')
            if not cursor:
                logger.info("✅ All pages processed!")
                break
                
            time.sleep(2)  # Conservative rate limiting
        
        logger.info(f"🏆 FULL crawl complete!")
        logger.info(f"   Pages: {stats['pages_processed']}")
        logger.info(f"   Models found: {stats['models_found']:,}")
        logger.info(f"   New models: {stats['models_new']:,}")
        logger.info(f"   Updated: {stats['models_updated']:,}")
        logger.info(f"   Errors: {stats['errors']:,}")
        
        return stats

if __name__ == "__main__":
    crawler = ReplicateFixedCrawler()
    
    # Test batch first
    print("🧪 Running test batch (100 models)...")
    result = crawler.crawl_batch(100)
    print(f"Test result: {result}")