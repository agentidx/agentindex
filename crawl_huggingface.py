#!/usr/bin/env python3
"""
HuggingFace Crawler - Models, Datasets, Spaces
Priority source: 500,000+ models för 1M agent goal
API: https://huggingface.co/api/models
"""

import requests
import time
import logging
import os
from datetime import datetime, timedelta
from agentindex.db.models import Agent, get_session
import uuid
import traceback
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [huggingface] %(message)s")
logger = logging.getLogger("huggingface_crawler")

class HuggingFaceCrawler:
    """Crawl HuggingFace for models, datasets, and spaces."""
    
    def __init__(self):
        self.session = get_session()
        self.headers = {
            'User-Agent': 'AgentIndex/1.0 (https://agentcrawl.dev)',
            'Accept': 'application/json'
        }
        
        # API endpoints
        self.models_url = "https://huggingface.co/api/models"
        self.datasets_url = "https://huggingface.co/api/datasets" 
        self.spaces_url = "https://huggingface.co/api/spaces"
        
        logger.info("🤗 HuggingFace crawler initialized")
    
    def test_api_access(self) -> bool:
        """Test HuggingFace API access."""
        try:
            response = requests.get(self.models_url, headers=self.headers, params={'limit': 1})
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ API access OK - Found {len(data)} models in test")
                return True
            else:
                logger.error(f"❌ API access failed - HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ API test error: {e}")
            return False
    
    def get_models_page(self, offset: int = 0, limit: int = 100, sort: str = "downloads") -> list:
        """Get a page of models from HuggingFace."""
        params = {
            'limit': limit,
            'offset': offset,
            'sort': sort
        }
        
        try:
            response = requests.get(self.models_url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching models page (offset={offset}): {e}")
            return []
    
    def get_datasets_page(self, offset: int = 0, limit: int = 100) -> list:
        """Get a page of datasets from HuggingFace."""
        params = {
            'limit': limit,
            'offset': offset,
            'sort': 'downloads'
        }
        
        try:
            response = requests.get(self.datasets_url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching datasets page (offset={offset}): {e}")
            return []
    
    def get_spaces_page(self, offset: int = 0, limit: int = 100) -> list:
        """Get a page of spaces from HuggingFace."""
        params = {
            'limit': limit,
            'offset': offset,
            'sort': 'downloads'
        }
        
        try:
            response = requests.get(self.spaces_url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching spaces page (offset={offset}): {e}")
            return []
    
    def model_to_agent(self, model: dict, item_type: str = "model") -> dict:
        """Convert HuggingFace model/dataset/space to Agent format."""
        model_id = model.get('id', model.get('modelId', ''))
        author = ""
        name = model_id
        
        # Parse author/name from model ID
        if '/' in model_id:
            parts = model_id.split('/', 1)
            author = parts[0]
            name = parts[1]
        
        # Determine source type
        if item_type == "dataset":
            source = "huggingface_dataset"
            source_url = f"https://huggingface.co/datasets/{model_id}"
        elif item_type == "space":
            source = "huggingface_space"
            source_url = f"https://huggingface.co/spaces/{model_id}"
        else:
            source = "huggingface_model"
            source_url = f"https://huggingface.co/{model_id}"
        
        # Extract description and tags
        description = model.get('description', '')
        if not description:
            # Build description from tags and pipeline_tag
            pipeline_tag = model.get('pipeline_tag', '')
            tags = model.get('tags', [])
            if pipeline_tag:
                description = f"{pipeline_tag.replace('-', ' ').title()} model"
            elif tags:
                description = f"Model with tags: {', '.join(tags[:3])}"
        
        return {
            'source': source,
            'source_url': source_url,
            'source_id': model_id,
            'name': name,
            'description': description,
            'author': author,
            'stars': model.get('likes', 0),
            'downloads': model.get('downloads', 0),
            'last_source_update': self._parse_date(model.get('lastModified', model.get('createdAt'))),
            'tags': self._extract_tags(model),
            'protocols': ['huggingface_api', 'rest'],
            'invocation': {
                'type': 'api',
                'endpoint': f'https://api-inference.huggingface.co/models/{model_id}',
                'protocol': 'rest',
                'method': 'POST',
                'docs': source_url
            },
            'pricing': {
                'model': 'free_tier_available',
                'currency': 'USD',
                'note': 'Free inference API + paid plans'
            },
            'raw_metadata': {
                'huggingface_data': model,
                'pipeline_tag': model.get('pipeline_tag'),
                'library_name': model.get('library_name'),
                'task': model.get('pipeline_tag', 'unknown'),
                'downloads_score': model.get('downloadsScore', 0)
            },
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
        """Parse HuggingFace date string."""
        if not date_str:
            return None
        try:
            # Handle both formats: 2026-02-16T04:55:12.000Z and ISO format
            if date_str.endswith('Z'):
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                return datetime.fromisoformat(date_str)
        except:
            return None
    
    def _extract_tags(self, model: dict) -> list:
        """Extract tags from HuggingFace model metadata."""
        tags = []
        
        # Get tags from model
        model_tags = model.get('tags', [])
        pipeline_tag = model.get('pipeline_tag', '')
        library_name = model.get('library_name', '')
        
        # Add pipeline tag
        if pipeline_tag:
            tags.append(pipeline_tag)
        
        # Add library name
        if library_name:
            tags.append(library_name)
        
        # Add some model tags (limit to avoid too many)
        for tag in model_tags[:3]:
            if tag not in tags and len(tag) > 2:  # Skip very short tags
                tags.append(tag)
                
        return tags[:5]  # Limit total tags
    
    def crawl_batch(self, batch_size: int = 1000, item_types: list = ["model"]) -> dict:
        """Crawl a batch of items (for testing)."""
        logger.info(f"🚀 Starting HuggingFace batch crawl ({batch_size} items, types: {item_types})")
        
        if not self.test_api_access():
            return {'success': False, 'error': 'API access failed'}
        
        stats = {
            'items_found': 0,
            'items_new': 0,
            'items_updated': 0,
            'errors': 0,
            'success': True,
            'by_type': {}
        }
        
        items_per_type = batch_size // len(item_types)
        
        for item_type in item_types:
            logger.info(f"📦 Processing {item_type}s...")
            type_stats = {'found': 0, 'new': 0, 'updated': 0, 'errors': 0}
            
            offset = 0
            items_processed = 0
            
            while items_processed < items_per_type:
                # Get appropriate page based on type
                if item_type == "dataset":
                    items = self.get_datasets_page(offset, min(100, items_per_type - items_processed))
                elif item_type == "space":
                    items = self.get_spaces_page(offset, min(100, items_per_type - items_processed))
                else:  # model
                    items = self.get_models_page(offset, min(100, items_per_type - items_processed))
                
                if not items:
                    logger.info(f"No more {item_type}s to process")
                    break
                
                logger.info(f"Processing {len(items)} {item_type}s (offset={offset})...")
                
                # Process each item
                for item in items:
                    try:
                        agent_data = self.model_to_agent(item, item_type)
                        
                        # Check if exists
                        existing = self.session.query(Agent).filter_by(
                            source=agent_data['source'],
                            source_id=agent_data['source_id']
                        ).first()
                        
                        if existing:
                            # Update existing
                            existing.last_crawled = datetime.now()
                            existing.stars = agent_data['stars']
                            existing.downloads = agent_data['downloads']
                            existing.last_source_update = agent_data['last_source_update']
                            type_stats['updated'] += 1
                        else:
                            # Create new agent
                            agent = Agent(**agent_data)
                            agent.id = uuid.uuid4()
                            self.session.add(agent)
                            type_stats['new'] += 1
                        
                        # Individual commit per agent (robust error handling)
                        try:
                            self.session.commit()
                        except Exception as commit_error:
                            logger.error(f"Commit error for {item_type} {item.get('id', 'unknown')}: {commit_error}")
                            self.session.rollback()
                            self.session.close()
                            self.session = get_session()
                            type_stats['errors'] += 1
                            continue
                        
                        type_stats['found'] += 1
                        items_processed += 1
                        
                        if items_processed % 50 == 0:
                            logger.info(f"Progress: {items_processed}/{items_per_type} {item_type}s processed")
                            
                    except Exception as e:
                        logger.error(f"Error processing {item_type} {item.get('id', 'unknown')}: {e}")
                        type_stats['errors'] += 1
                        continue
                
                offset += len(items)
                time.sleep(1)  # Rate limiting
            
            # Update overall stats
            stats['items_found'] += type_stats['found']
            stats['items_new'] += type_stats['new'] 
            stats['items_updated'] += type_stats['updated']
            stats['errors'] += type_stats['errors']
            stats['by_type'][item_type] = type_stats
            
            logger.info(f"✅ {item_type.title()}s complete: {type_stats['new']} new, {type_stats['updated']} updated")
        
        logger.info(f"🎯 Batch crawl complete:")
        logger.info(f"   Total found: {stats['items_found']:,}")
        logger.info(f"   New items: {stats['items_new']:,}")
        logger.info(f"   Updated: {stats['items_updated']:,}")
        logger.info(f"   Errors: {stats['errors']:,}")
        
        return stats
    
    def crawl_all_items(self, sustained_rate_limit: int = 10000, item_types: list = ["model", "dataset", "space"]) -> dict:
        """Crawl all HuggingFace items with sustained rate limiting."""
        logger.info(f"🚀 Starting FULL HuggingFace crawl")
        logger.info(f"   Types: {item_types}")
        logger.info(f"   Sustained rate: {sustained_rate_limit}/day")
        
        if not self.test_api_access():
            return {'success': False, 'error': 'API access failed'}
        
        stats = {
            'items_found': 0,
            'items_new': 0,
            'items_updated': 0,
            'errors': 0,
            'success': True,
            'by_type': {},
            'pages_processed': 0
        }
        
        daily_count = 0
        start_time = time.time()
        
        for item_type in item_types:
            logger.info(f"🔄 Starting full crawl of {item_type}s...")
            type_stats = {'found': 0, 'new': 0, 'updated': 0, 'errors': 0}
            
            offset = 0
            consecutive_empty_pages = 0
            max_empty_pages = 5
            
            while consecutive_empty_pages < max_empty_pages:
                # Rate limiting - don't exceed daily limit
                if daily_count >= sustained_rate_limit:
                    elapsed_hours = (time.time() - start_time) / 3600
                    if elapsed_hours < 24:
                        wait_time = (24 - elapsed_hours) * 3600
                        logger.info(f"Daily rate limit reached ({sustained_rate_limit}), waiting {wait_time/3600:.1f}h")
                        time.sleep(wait_time)
                    daily_count = 0
                    start_time = time.time()
                
                # Get page based on type
                if item_type == "dataset":
                    items = self.get_datasets_page(offset, 100)
                elif item_type == "space":
                    items = self.get_spaces_page(offset, 100)
                else:  # model
                    items = self.get_models_page(offset, 100)
                
                if not items or len(items) == 0:
                    consecutive_empty_pages += 1
                    logger.info(f"Empty page for {item_type}s (offset={offset}), consecutive: {consecutive_empty_pages}")
                    offset += 100  # Continue anyway
                    time.sleep(2)
                    continue
                
                consecutive_empty_pages = 0  # Reset counter
                stats['pages_processed'] += 1
                
                logger.info(f"📄 {item_type.title()} page (offset={offset}): {len(items)} items")
                
                # Process items on page
                for item in items:
                    try:
                        agent_data = self.model_to_agent(item, item_type)
                        
                        # Check if exists
                        existing = self.session.query(Agent).filter_by(
                            source=agent_data['source'],
                            source_id=agent_data['source_id']
                        ).first()
                        
                        if existing:
                            existing.last_crawled = datetime.now()
                            existing.stars = agent_data['stars']
                            existing.downloads = agent_data['downloads']
                            existing.last_source_update = agent_data['last_source_update']
                            type_stats['updated'] += 1
                        else:
                            agent = Agent(**agent_data)
                            agent.id = uuid.uuid4()
                            self.session.add(agent)
                            type_stats['new'] += 1
                        
                        # Individual commit per agent
                        try:
                            self.session.commit()
                        except Exception as commit_error:
                            logger.error(f"Commit error for {item_type} {item.get('id', 'unknown')}: {commit_error}")
                            self.session.rollback()
                            self.session.close()
                            self.session = get_session()
                            type_stats['errors'] += 1
                            continue
                        
                        type_stats['found'] += 1
                        daily_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing {item_type} {item.get('id', 'unknown')}: {e}")
                        type_stats['errors'] += 1
                        continue
                
                # Progress report
                if stats['pages_processed'] % 50 == 0:
                    logger.info(f"📊 Progress: {stats['pages_processed']} pages, {type_stats['found']:,} {item_type}s, {type_stats['new']:,} new")
                
                offset += len(items)
                time.sleep(2)  # Conservative rate limiting
            
            # Update overall stats
            stats['items_found'] += type_stats['found']
            stats['items_new'] += type_stats['new']
            stats['items_updated'] += type_stats['updated']
            stats['errors'] += type_stats['errors']
            stats['by_type'][item_type] = type_stats
            
            logger.info(f"✅ {item_type.title()}s crawl complete:")
            logger.info(f"   Found: {type_stats['found']:,}")
            logger.info(f"   New: {type_stats['new']:,}")
            logger.info(f"   Updated: {type_stats['updated']:,}")
            logger.info(f"   Errors: {type_stats['errors']:,}")
        
        logger.info(f"🏆 FULL HuggingFace crawl complete!")
        logger.info(f"   Total pages: {stats['pages_processed']}")
        logger.info(f"   Total items found: {stats['items_found']:,}")
        logger.info(f"   New items: {stats['items_new']:,}")
        logger.info(f"   Updated: {stats['items_updated']:,}")
        logger.info(f"   Errors: {stats['errors']:,}")
        
        return stats

if __name__ == "__main__":
    crawler = HuggingFaceCrawler()
    
    # Test batch first (100 models only)
    print("🧪 Running test batch (100 models)...")
    result = crawler.crawl_batch(100, ["model"])
    print(f"Test result: {result}")
    
    if result['success'] and result['items_new'] > 0:
        print(f"\n✅ Success! Added {result['items_new']} new HuggingFace models")
        print("Ready to scale up to full crawl...")
    else:
        print(f"\n⚠️ Test issues - check logs before scaling up")