#!/usr/bin/env python3
"""
HuggingFace Chronological Crawler - ALL Models Strategy
Anders spec: Hela katalogen kronologiskt, ON CONFLICT DO NOTHING, 500K models på 48h

Strategy:
- GET https://huggingface.co/api/models?limit=100&sort=_id&direction=1&offset=N
- Kronologisk ordning (äldst först) 
- ALLA models, ingen filtrering
- Snabb insert med ON CONFLICT DO NOTHING
"""

import requests
import time
import logging
from datetime import datetime
import uuid
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [hf-chrono] %(message)s")
logger = logging.getLogger("hf_chrono")

class HuggingFaceChronologicalCrawler:
    def __init__(self, start_offset=0, end_offset=500000):
        self.headers = {
            'User-Agent': 'AgentIndex/1.0 - Chronological Discovery',
            'Accept': 'application/json'
        }
        
        self.start_offset = start_offset
        self.end_offset = end_offset
        self.batch_size = 100
        
        # Direct PostgreSQL connection for speed
        self.conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex'))
        self.cursor = self.conn.cursor()
        
        logger.info(f"🚀 Chronological crawler: offset {start_offset}-{end_offset}")
    
    def get_models_batch(self, offset):
        """Get models batch chronologically."""
        url = "https://huggingface.co/api/models"
        params = {
            'limit': self.batch_size,
            'sort': '_id',       # Chronological by creation
            'direction': 1,      # Ascending (oldest first)  
            'offset': offset
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            models = response.json()
            
            logger.debug(f"Offset {offset}: {len(models)} models")
            return models
            
        except Exception as e:
            logger.error(f"Error fetching offset {offset}: {e}")
            return []
    
    def fast_insert_models(self, models):
        """Fast bulk insert with ON CONFLICT DO NOTHING."""
        if not models:
            return 0
            
        insert_sql = """
        INSERT INTO agents (
            id, source, source_url, source_id, name, description, author,
            stars, downloads, tags, protocols, raw_metadata,
            first_indexed, last_crawled, is_active, crawl_status
        ) VALUES %s
        ON CONFLICT (source_url) DO NOTHING;
        """
        
        values = []
        for model in models:
            try:
                model_id = model.get('id', '')
                if not model_id:
                    continue
                    
                # Quick data extraction  
                author, name = model_id.split('/', 1) if '/' in model_id else ('unknown', model_id)
                
                values.append((
                    str(uuid.uuid4()),
                    'huggingface_chrono',
                    f"https://huggingface.co/{model_id}",
                    model_id,
                    name[:500],  # Truncate if needed
                    (model.get('description') or '')[:2000],  # Truncate description
                    author[:255],
                    model.get('likes', 0),
                    model.get('downloads', 0),
                    model.get('tags', [])[:10],  # Limit tags
                    ['huggingface_api'],
                    psycopg2.extras.Json(model),
                    datetime.now(),
                    datetime.now(),
                    True,
                    'indexed'
                ))
                
            except Exception as e:
                logger.error(f"Error processing model {model.get('id', 'unknown')}: {e}")
                continue
        
        if not values:
            return 0
            
        try:
            # Use psycopg2 execute_values for bulk insert
            psycopg2.extras.execute_values(
                self.cursor, insert_sql, values, template=None, page_size=100
            )
            self.conn.commit()
            
            # Return actual inserted count (approximate)
            return len(values)
            
        except Exception as e:
            logger.error(f"Bulk insert error: {e}")
            self.conn.rollback()
            return 0
    
    def crawl_chronological(self):
        """Crawl all models chronologically in range."""
        logger.info(f"🎯 STARTING CHRONOLOGICAL CRAWL: {self.start_offset} → {self.end_offset}")
        
        total_processed = 0
        total_inserted = 0
        current_offset = self.start_offset
        consecutive_empty = 0
        
        start_time = time.time()
        
        while current_offset < self.end_offset and consecutive_empty < 5:
            batch_start = time.time()
            
            # Get batch
            models = self.get_models_batch(current_offset)
            
            if not models:
                consecutive_empty += 1
                logger.warning(f"Empty batch at offset {current_offset} (consecutive: {consecutive_empty})")
                current_offset += self.batch_size
                time.sleep(2)
                continue
            
            consecutive_empty = 0
            
            # Fast insert
            inserted_count = self.fast_insert_models(models)
            
            total_processed += len(models)
            total_inserted += inserted_count
            
            batch_time = time.time() - batch_start
            
            # Progress report every 1000 models
            if total_processed % 1000 == 0:
                elapsed = time.time() - start_time
                rate = total_processed / elapsed if elapsed > 0 else 0
                eta = (self.end_offset - current_offset) / rate / 3600 if rate > 0 else 0
                
                logger.info(f"Progress: offset {current_offset}, processed {total_processed}, inserted {total_inserted}")
                logger.info(f"Rate: {rate:.1f} models/sec, ETA: {eta:.1f}h")
            
            current_offset += self.batch_size
            
            # Rate limiting  
            if batch_time < 0.5:
                time.sleep(0.5 - batch_time)
        
        elapsed_hours = (time.time() - start_time) / 3600
        logger.info(f"🏁 CHRONOLOGICAL CRAWL COMPLETE!")
        logger.info(f"📊 Range {self.start_offset}-{current_offset}: {total_inserted} new models in {elapsed_hours:.1f}h")
        
        return {
            'processed': total_processed,
            'inserted': total_inserted,
            'final_offset': current_offset,
            'hours': elapsed_hours
        }
    
    def __del__(self):
        """Cleanup database connection."""
        if hasattr(self, 'cursor'):
            self.cursor.close()
        if hasattr(self, 'conn'):
            self.conn.close()

def run_parallel_crawler(worker_id, start_offset, end_offset):
    """Run crawler for specific range - for parallel execution."""
    logger.info(f"🔄 Worker {worker_id} starting: {start_offset} → {end_offset}")
    
    crawler = HuggingFaceChronologicalCrawler(start_offset, end_offset)
    result = crawler.crawl_chronological()
    
    logger.info(f"✅ Worker {worker_id} complete: {result['inserted']} inserted")
    return result

if __name__ == "__main__":
    # Single worker for testing - parallel execution done via separate processes
    crawler = HuggingFaceChronologicalCrawler(0, 50000)  # First 50K for testing
    result = crawler.crawl_chronological()
    print(f"Chronological crawl result: {result}")