#!/usr/bin/env python3
"""
HuggingFace Chronological Massive Crawler - FIXED
LillAnders spec: 500K models på 48h genom kronologisk crawling

Strategy: 
- Kronologisk hämtning: sort=_id&direction=1&offset=N
- ALLA models - inget filtering 
- ON CONFLICT DO NOTHING för hastighet
- Parallell batch-support
"""

import requests
import time
import logging
from datetime import datetime
import uuid
import psycopg2
import psycopg2.extras  # Explicit import
import json
from dotenv import load_dotenv
import os
import sys

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [hf-chrono] %(message)s")
logger = logging.getLogger("hf_chrono")

class HuggingFaceChronologicalCrawler:
    def __init__(self, batch_id="main", offset_start=0, offset_end=500000):
        self.batch_id = batch_id
        self.offset_start = offset_start
        self.offset_end = offset_end
        
        self.headers = {
            'User-Agent': 'AgentIndex/1.0 - Chronological Discovery',
            'Accept': 'application/json'
        }
        
        # Direct PostgreSQL connection for speed
        try:
            self.conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex'))
            self.cursor = self.conn.cursor()
            logger.info(f"🚀 Batch {self.batch_id}: Connected to PostgreSQL")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
        
        logger.info(f"🎯 Batch {self.batch_id}: Offset {offset_start}-{offset_end}")
    
    def fetch_models_chronological(self, offset, limit=100):
        """Fetch models in chronological order (oldest first)."""
        url = "https://huggingface.co/api/models"
        params = {
            'limit': limit,
            'sort': '_id',
            'direction': '1',  # Ascending (oldest first)
            'offset': offset
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            models = response.json()
            
            logger.debug(f"Batch {self.batch_id}: Offset {offset} → {len(models)} models")
            return models
            
        except Exception as e:
            logger.error(f"Batch {self.batch_id}: Error at offset {offset}: {e}")
            return []
    
    def bulk_insert_models(self, models):
        """Ultra-fast bulk insert with ON CONFLICT DO NOTHING."""
        if not models:
            return 0
            
        # Build values for bulk insert
        values = []
        for model in models:
            try:
                model_id = model.get('id', '')
                if not model_id:
                    continue
                    
                # Quick data extraction (no filtering - ALL models)
                author, name = model_id.split('/', 1) if '/' in model_id else ('unknown', model_id)
                
                values.append((
                    str(uuid.uuid4()),
                    'huggingface_chronological',
                    f"https://huggingface.co/{model_id}",
                    model_id,
                    name[:500],  # Truncate for safety
                    (model.get('description') or '')[:2000],  # Truncate
                    author[:255],
                    model.get('likes', 0),
                    model.get('downloads', 0),
                    (model.get('tags') or [])[:10],  # Limit tags
                    ['huggingface_api'],
                    json.dumps(model),  # Store as JSON string
                    datetime.now(),
                    datetime.now(),
                    True,
                    'indexed'
                ))
                
            except Exception as e:
                logger.error(f"Batch {self.batch_id}: Error processing model {model.get('id', 'unknown')}: {e}")
                continue
        
        if not values:
            return 0
            
        try:
            # Use execute_values for fastest bulk insert
            insert_sql = """
            INSERT INTO agents (
                id, source, source_url, source_id, name, description, author,
                stars, downloads, tags, protocols, raw_metadata,
                first_indexed, last_crawled, is_active, crawl_status
            ) VALUES %s
            ON CONFLICT (source_url) DO NOTHING;
            """
            
            psycopg2.extras.execute_values(
                self.cursor, insert_sql, values, 
                template=None, page_size=100
            )
            self.conn.commit()
            
            # Get actual inserted count by checking cursor.rowcount
            inserted_count = self.cursor.rowcount
            logger.debug(f"Batch {self.batch_id}: {len(values)} processed → {inserted_count} inserted")
            
            return inserted_count
            
        except Exception as e:
            logger.error(f"Batch {self.batch_id}: Bulk insert error: {e}")
            self.conn.rollback()
            return 0
    
    def crawl_chronological_range(self, batch_size=100):
        """Crawl chronological range for this batch."""
        logger.info(f"🎯 STARTING CHRONOLOGICAL CRAWL - Batch {self.batch_id}")
        logger.info(f"Range: {self.offset_start:,} - {self.offset_end:,} (target: {self.offset_end - self.offset_start:,} models)")
        
        total_processed = 0
        total_inserted = 0
        start_time = time.time()
        
        current_offset = self.offset_start
        consecutive_empty = 0
        
        while current_offset < self.offset_end:
            batch_start = time.time()
            
            try:
                # Fetch batch
                models = self.fetch_models_chronological(current_offset, batch_size)
                
                if not models:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        logger.info(f"Batch {self.batch_id}: 3 consecutive empty responses at offset {current_offset:,}. Stopping.")
                        break
                    current_offset += batch_size
                    continue
                
                consecutive_empty = 0  # Reset counter
                
                # Insert batch
                inserted_count = self.bulk_insert_models(models)
                
                total_processed += len(models)
                total_inserted += inserted_count
                
                # Progress logging
                if current_offset % 1000 == 0:  # Every 1K offsets
                    elapsed = time.time() - start_time
                    rate = total_processed / elapsed if elapsed > 0 else 0
                    
                    logger.info(f"Batch {self.batch_id}: Offset {current_offset:,} | "
                              f"Processed: {total_processed:,} | Inserted: {total_inserted:,} | "
                              f"Rate: {rate:.1f}/sec | Hit rate: {(total_inserted/total_processed*100):.1f}%")
                
                current_offset += batch_size
                
                # Rate limiting (respectful to HuggingFace)
                batch_time = time.time() - batch_start
                if batch_time < 0.2:  # Max 5 requests/sec
                    time.sleep(0.2 - batch_time)
                    
            except Exception as e:
                logger.error(f"Batch {self.batch_id}: Error at offset {current_offset}: {e}")
                current_offset += batch_size
                continue
        
        elapsed_hours = (time.time() - start_time) / 3600
        final_hit_rate = (total_inserted / total_processed * 100) if total_processed > 0 else 0
        
        logger.info(f"🏁 BATCH {self.batch_id} COMPLETE!")
        logger.info(f"📊 Range {self.offset_start:,}-{current_offset:,} → "
                   f"{total_processed:,} processed → {total_inserted:,} inserted "
                   f"in {elapsed_hours:.2f}h")
        logger.info(f"Hit rate: {final_hit_rate:.1f}% | Rate: {total_processed/elapsed_hours/3600:.0f}/sec")
        
        return {
            'batch_id': self.batch_id,
            'offset_start': self.offset_start,
            'offset_end': current_offset,
            'processed': total_processed,
            'inserted': total_inserted,
            'hit_rate': final_hit_rate,
            'hours': elapsed_hours
        }
    
    def __del__(self):
        """Cleanup database connection."""
        try:
            if hasattr(self, 'cursor'):
                self.cursor.close()
            if hasattr(self, 'conn'):
                self.conn.close()
        except:
            pass

def main():
    if len(sys.argv) > 1:
        # Run specific batch: python script.py batch1 0 125000
        batch_id = sys.argv[1]
        offset_start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        offset_end = int(sys.argv[3]) if len(sys.argv) > 3 else 125000
    else:
        # Default single batch
        batch_id = "test"
        offset_start = 0
        offset_end = 1000  # Small test
    
    crawler = HuggingFaceChronologicalCrawler(batch_id, offset_start, offset_end)
    result = crawler.crawl_chronological_range()
    print(f"Final result: {result}")

if __name__ == "__main__":
    main()