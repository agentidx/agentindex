#!/usr/bin/env python3
"""
Replicate Crawler with Persistent Cursor - FIXED
LillAnders spec: Använd cursor-pagination korrekt, spara position mellan runs
"""

import requests
import time
import logging
from datetime import datetime
import uuid
import psycopg2
import psycopg2.extras
import json
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [replicate-fix] %(message)s")
logger = logging.getLogger("replicate_fix")

class ReplicateCursorCrawler:
    def __init__(self):
        self.base_url = "https://api.replicate.com/v1"
        
        # Get API token
        self.api_token = os.getenv('REPLICATE_API_TOKEN')
        if not self.api_token:
            raise ValueError("REPLICATE_API_TOKEN environment variable is required")
            
        self.headers = {
            'User-Agent': 'AgentIndex/1.0 - Cursor-Based Discovery',
            'Authorization': f'Bearer {self.api_token}'
        }
        
        # Direct PostgreSQL connection
        self.conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex'))
        self.cursor = self.conn.cursor()
        
        # Cursor state file
        self.cursor_file = "replicate_cursor_state.json"
        
        logger.info(f"🚀 Replicate cursor crawler initialized")
    
    def load_cursor_state(self):
        """Load saved cursor state."""
        try:
            if os.path.exists(self.cursor_file):
                with open(self.cursor_file, 'r') as f:
                    state = json.load(f)
                    logger.info(f"📍 Loaded cursor state: page {state.get('page', 'unknown')}")
                    return state
        except Exception as e:
            logger.error(f"Error loading cursor state: {e}")
        
        # Default state (start from beginning)
        return {'next_url': None, 'page': 1, 'total_processed': 0}
    
    def save_cursor_state(self, state):
        """Save current cursor state."""
        try:
            with open(self.cursor_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"💾 Saved cursor state: page {state['page']}")
        except Exception as e:
            logger.error(f"Error saving cursor state: {e}")
    
    def get_models_page(self, next_url=None):
        """Get one page of models from Replicate API."""
        if next_url:
            url = next_url
        else:
            url = f"{self.base_url}/models"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching models page: {e}")
            return None
    
    def bulk_insert_models(self, models):
        """Ultra-fast bulk insert with ON CONFLICT DO NOTHING."""
        if not models:
            return 0
            
        values = []
        for model in models:
            try:
                owner = model.get('owner', '') or 'unknown'
                name = model.get('name', '') or 'unnamed'
                
                if not name or not owner:
                    continue
                    
                full_name = f"{owner}/{name}"
                
                values.append((
                    str(uuid.uuid4()),
                    'replicate_cursor',
                    f"https://replicate.com/{full_name}",
                    full_name,
                    name[:500],
                    (model.get('description') or '')[:2000],
                    owner[:255],
                    0,  # Likes (not available in base API)
                    model.get('run_count', 0),
                    self._extract_tags(model)[:10],
                    ['replicate_api', 'rest'],
                    json.dumps(model),
                    datetime.now(),
                    datetime.now(),
                    True,
                    'indexed'
                ))
                
            except Exception as e:
                logger.error(f"Error processing model {model.get('name', 'unknown')}: {e}")
                continue
        
        if not values:
            return 0
            
        try:
            insert_sql = """
            INSERT INTO agents (
                id, source, source_url, source_id, name, description, author,
                stars, downloads, tags, protocols, raw_metadata,
                first_indexed, last_crawled, is_active, crawl_status
            ) VALUES %s
            ON CONFLICT (source_url) DO NOTHING;
            """
            
            psycopg2.extras.execute_values(
                self.cursor, insert_sql, values, template=None, page_size=100
            )
            self.conn.commit()
            
            return self.cursor.rowcount
            
        except Exception as e:
            logger.error(f"Bulk insert error: {e}")
            self.conn.rollback()
            return 0
    
    def _extract_tags(self, model):
        """Extract tags from model metadata."""
        tags = ['replicate']
        
        description = (model.get('description', '') + ' ' + model.get('name', '')).lower()
        
        # Model type detection
        if any(term in description for term in ['text', 'language', 'gpt', 'llm', 'chat']):
            tags.append('text-generation')
        if any(term in description for term in ['image', 'visual', 'diffusion', 'dalle', 'stable']):
            tags.append('image-generation')
        if any(term in description for term in ['audio', 'speech', 'sound', 'music', 'voice']):
            tags.append('audio')
        if any(term in description for term in ['video', 'animation', 'motion']):
            tags.append('video')
        if any(term in description for term in ['agent', 'assistant', 'bot']):
            tags.append('agent')
        if model.get('github_url'):
            tags.append('open-source')
            
        return tags
    
    def crawl_with_cursor(self, max_pages=None):
        """Crawl all models using cursor pagination - continues from last position."""
        logger.info(f"🎯 STARTING CURSOR-BASED CRAWL")
        
        # Load saved state
        state = self.load_cursor_state()
        
        total_processed = state.get('total_processed', 0)
        total_inserted = 0
        start_page = state.get('page', 1)
        current_page = start_page
        next_url = state.get('next_url')
        
        start_time = time.time()
        
        logger.info(f"🔄 Resuming from page {start_page}, processed: {total_processed:,}")
        
        while True:
            # Check page limit
            if max_pages and (current_page - start_page + 1) > max_pages:
                logger.info(f"Reached page limit: {max_pages}")
                break
            
            # Fetch page
            logger.info(f"🔄 Fetching page {current_page}...")
            data = self.get_models_page(next_url)
            
            if not data:
                logger.error(f"Failed to fetch page {current_page}")
                break
                
            models = data.get('results', [])
            if not models:
                logger.info(f"No more models on page {current_page}")
                break
            
            # Process models
            inserted_count = self.bulk_insert_models(models)
            
            total_processed += len(models)
            total_inserted += inserted_count
            
            logger.info(f"Page {current_page}: {len(models)} models → {inserted_count} inserted")
            
            # Save state after each page
            next_url = data.get('next')
            state = {
                'next_url': next_url,
                'page': current_page + 1,
                'total_processed': total_processed,
                'last_update': datetime.now().isoformat()
            }
            self.save_cursor_state(state)
            
            # Check if we've reached the end
            if not next_url:
                logger.info(f"📍 Reached end of Replicate catalog at page {current_page}")
                break
            
            current_page += 1
            
            # Progress report every 10 pages
            if current_page % 10 == 0:
                elapsed = time.time() - start_time
                rate = total_processed / elapsed if elapsed > 0 else 0
                logger.info(f"📊 Progress: Page {current_page}, {total_processed:,} processed, {total_inserted:,} inserted")
                logger.info(f"   Rate: {rate:.1f} models/sec")
            
            # Rate limiting (respectful)
            time.sleep(0.5)
        
        elapsed_hours = (time.time() - start_time) / 3600
        hit_rate = (total_inserted / len(models) * 100) if models else 0
        
        logger.info(f"🏁 CURSOR CRAWL COMPLETE!")
        logger.info(f"📊 Pages {start_page}-{current_page} → {total_processed:,} processed → {total_inserted:,} inserted in {elapsed_hours:.2f}h")
        logger.info(f"Hit rate: {hit_rate:.1f}% | Rate: {total_processed/elapsed_hours:.0f}/hour")
        
        # Reset cursor state if we finished completely
        if not next_url:
            state = {'next_url': None, 'page': 1, 'total_processed': 0}
            self.save_cursor_state(state)
            logger.info("🔄 Cursor state reset - next run will start from beginning")
        
        return {
            'pages_crawled': current_page - start_page + 1,
            'total_processed': total_processed,
            'total_inserted': total_inserted,
            'hit_rate': hit_rate,
            'hours': elapsed_hours,
            'finished': not next_url
        }
    
    def reset_cursor(self):
        """Reset cursor to start from beginning."""
        state = {'next_url': None, 'page': 1, 'total_processed': 0}
        self.save_cursor_state(state)
        logger.info("🔄 Cursor reset to beginning")
    
    def __del__(self):
        """Cleanup database connection."""
        try:
            if hasattr(self, 'cursor'):
                self.cursor.close()
            if hasattr(self, 'conn'):
                self.conn.close()
        except:
            pass

if __name__ == "__main__":
    import sys
    
    crawler = ReplicateCursorCrawler()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--reset':
        crawler.reset_cursor()
        print("Cursor reset to beginning")
    else:
        # Run continuous crawl (or specify max pages)
        max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else None
        result = crawler.crawl_with_cursor(max_pages=max_pages)
        print(f"Crawl result: {result}")