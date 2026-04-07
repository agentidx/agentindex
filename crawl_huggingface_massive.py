#!/usr/bin/env python3
"""
HuggingFace Massive Crawler - Fixed Pagination Strategy  
Anders requirement: 1000+ new models per hour

Strategy: Use different API approaches and filters to get NEW models
"""

import requests
import time
import logging
from datetime import datetime, timedelta
from agentindex.db.models import Agent, get_db_session
import uuid
import traceback
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [hf-massive] %(message)s")
logger = logging.getLogger("hf_massive")

class HuggingFaceMassiveCrawler:
    def __init__(self):
        self.headers = {
            'User-Agent': 'AgentIndex/1.0 - Massive Discovery',
            'Accept': 'application/json'
        }
        
        # Multiple search strategies to bypass API limitations
        self.search_strategies = [
            # No sort, no filters - get chronological
            {'params': {'limit': 100}, 'name': 'chronological'},
            
            # Filter by specific tasks
            {'params': {'limit': 100, 'filter': 'text-generation'}, 'name': 'text-generation'}, 
            {'params': {'limit': 100, 'filter': 'image-classification'}, 'name': 'image-classification'},
            {'params': {'limit': 100, 'filter': 'question-answering'}, 'name': 'question-answering'},
            {'params': {'limit': 100, 'filter': 'conversational'}, 'name': 'conversational'},
            
            # Search by popular libraries
            {'params': {'limit': 100, 'library': 'transformers'}, 'name': 'transformers'},
            {'params': {'limit': 100, 'library': 'diffusers'}, 'name': 'diffusers'},
            {'params': {'limit': 100, 'library': 'sentence-transformers'}, 'name': 'sentence-transformers'},
        ]
        
        logger.info(f"🚀 Massive crawler initialized with {len(self.search_strategies)} strategies")
    
    def get_models_batch(self, strategy, start_offset=0, batch_size=100):
        """Get models using a specific strategy and offset."""
        url = "https://huggingface.co/api/models"
        params = strategy['params'].copy()
        params['offset'] = start_offset
        params['limit'] = batch_size
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            models = response.json()
            
            logger.info(f"{strategy['name']} offset {start_offset}: {len(models)} models")
            return models
            
        except Exception as e:
            logger.error(f"Error fetching {strategy['name']} batch: {e}")
            return []
    
    def model_to_agent(self, model):
        """Convert HuggingFace model to Agent format."""
        model_id = model.get('id', '')
        if '/' in model_id:
            author, name = model_id.split('/', 1)
        else:
            author, name = 'unknown', model_id
            
        # Use multiple potential source names to avoid conflicts
        source_variants = ['huggingface_new', 'huggingface_massive', 'huggingface_fresh']
        
        return {
            'source': 'huggingface_new',  # Different source to avoid conflicts
            'source_url': f"https://huggingface.co/{model_id}",
            'source_id': model_id,
            'name': name,
            'description': model.get('description', ''),
            'author': author,
            'stars': model.get('likes', 0),
            'downloads': model.get('downloads', 0),
            'tags': model.get('tags', [])[:8],
            'protocols': ['huggingface_api', 'transformers'],
            'raw_metadata': model,
            'first_indexed': datetime.now(),
            'last_crawled': datetime.now(),
            'crawl_status': 'indexed'
        }
    
    def crawl_strategy(self, strategy, max_models=1000):
        """Crawl using one strategy."""
        logger.info(f"🔍 Starting strategy: {strategy['name']} (max {max_models} models)")
        
        new_count = 0
        updated_count = 0
        processed_count = 0
        offset = 0
        batch_size = 100
        
        while processed_count < max_models:
            models = self.get_models_batch(strategy, offset, batch_size)
            
            if not models:
                logger.info(f"No more models for strategy {strategy['name']}")
                break
            
            for model in models:
                if processed_count >= max_models:
                    break
                    
                try:
                    with get_db_session() as session:
                        model_id = model.get('id', '')
                        if not model_id:
                            continue
                            
                        # Check if exists with ANY huggingface source variant
                        existing = session.query(Agent).filter(
                            Agent.source_url == f"https://huggingface.co/{model_id}"
                        ).first()
                        
                        if existing:
                            # Update existing 
                            existing.last_crawled = datetime.now()
                            existing.downloads = model.get('downloads', 0)
                            existing.stars = model.get('likes', 0)
                            updated_count += 1
                        else:
                            # Create new agent
                            agent_data = self.model_to_agent(model)
                            agent = Agent(**agent_data)
                            agent.id = uuid.uuid4()
                            session.add(agent)
                            new_count += 1
                        
                        processed_count += 1
                        
                        if processed_count % 100 == 0:
                            logger.info(f"Strategy {strategy['name']}: {processed_count} processed, {new_count} new, {updated_count} updated")
                            
                except Exception as e:
                    logger.error(f"Error processing model {model.get('id', 'unknown')}: {e}")
                    continue
            
            offset += batch_size
            time.sleep(0.5)  # Rate limiting
            
        logger.info(f"✅ Strategy {strategy['name']} complete: {new_count} new, {updated_count} updated")
        return {'new': new_count, 'updated': updated_count, 'processed': processed_count}
    
    def crawl_massive(self, models_per_strategy=500):
        """Run all strategies to get massive model coverage."""
        logger.info(f"🚀 STARTING MASSIVE HUGGINGFACE CRAWL")
        logger.info(f"Target: {models_per_strategy} models per strategy × {len(self.search_strategies)} strategies")
        
        total_new = 0
        total_updated = 0
        total_processed = 0
        
        for i, strategy in enumerate(self.search_strategies, 1):
            logger.info(f"📊 Strategy {i}/{len(self.search_strategies)}: {strategy['name']}")
            
            try:
                result = self.crawl_strategy(strategy, models_per_strategy)
                total_new += result['new']
                total_updated += result['updated'] 
                total_processed += result['processed']
                
                logger.info(f"Strategy {i} complete: +{result['new']} new models")
                
                # Brief pause between strategies
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Strategy {strategy['name']} failed: {e}")
                continue
        
        logger.info(f"🎯 MASSIVE CRAWL COMPLETE!")
        logger.info(f"📊 TOTAL RESULTS:")
        logger.info(f"  New models: {total_new}")
        logger.info(f"  Updated models: {total_updated}")
        logger.info(f"  Total processed: {total_processed}")
        
        return {
            'new': total_new,
            'updated': total_updated, 
            'processed': total_processed
        }

if __name__ == "__main__":
    crawler = HuggingFaceMassiveCrawler()
    result = crawler.crawl_massive(models_per_strategy=200)  # Start with 200 per strategy
    print(f"Massive crawl results: {result}")