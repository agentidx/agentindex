#!/usr/bin/env python3
"""
HuggingFace Author-Based Crawler
Strategy: Get list of authors from existing DB + API, then fetch ALL models per author.
This bypasses the search 100-result limit entirely.
"""

import requests
import time
import logging
import uuid
import psycopg2
import psycopg2.extras
import json
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [hf-authors] %(message)s",
    handlers=[
        logging.FileHandler(f'hf_authors_{datetime.now().strftime("%Y%m%d_%H%M")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("hf_authors")

DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')
HEADERS = {'User-Agent': 'AgentIndex/1.0', 'Accept': 'application/json'}


def get_known_authors():
    """Get all unique authors we already have in the database."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT author FROM agents WHERE source LIKE 'huggingface%' AND author IS NOT NULL AND author != 'unknown'")
    authors = set(r[0] for r in cur.fetchall())
    conn.close()
    logger.info(f"Found {len(authors)} known authors in database")
    return authors


def discover_new_authors():
    """Discover prolific authors via API searches."""
    authors = set()
    
    # Search for popular terms and collect author names
    discovery_terms = [
        'model', 'bert', 'gpt', 'llama', 'mistral', 'transformer', 'diffusion',
        'lora', 'gguf', 'chat', 'instruct', 'fine-tuned', 'quantized',
        'classification', 'generation', 'embedding', 'translation', 'detection',
        'whisper', 'clip', 'vit', 'stable-diffusion', 'controlnet',
        'chinese', 'japanese', 'korean', 'arabic', 'hindi', 'french', 'german',
        'medical', 'legal', 'financial', 'code', 'math', 'science',
    ]
    
    for term in discovery_terms:
        try:
            resp = requests.get(
                'https://huggingface.co/api/models',
                params={'search': term, 'limit': 100, 'sort': 'downloads', 'direction': '-1'},
                headers=HEADERS,
                timeout=15
            )
            if resp.status_code == 200:
                for model in resp.json():
                    model_id = model.get('id', '')
                    if '/' in model_id:
                        authors.add(model_id.split('/')[0])
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Discovery error for '{term}': {e}")
    
    logger.info(f"Discovered {len(authors)} authors from API searches")
    return authors


def fetch_author_models(author, cur, conn):
    """Fetch ALL models from a specific author. Returns count of new models inserted."""
    total_new = 0
    page = 0
    
    while True:
        try:
            # HuggingFace allows filtering by author
            resp = requests.get(
                'https://huggingface.co/api/models',
                params={'author': author, 'limit': 100},
                headers=HEADERS,
                timeout=15
            )
            
            if resp.status_code == 429:
                time.sleep(60)
                continue
            
            if resp.status_code != 200:
                break
            
            models = resp.json()
            if not models:
                break
            
            values = []
            for model in models:
                model_id = model.get('id', '')
                if not model_id:
                    continue
                a, name = model_id.split('/', 1) if '/' in model_id else ('unknown', model_id)
                values.append((
                    str(uuid.uuid4()),
                    'huggingface_author',
                    f"https://huggingface.co/{model_id}",
                    model_id,
                    name[:500],
                    (model.get('description') or model.get('id', ''))[:2000],
                    a[:255],
                    model.get('likes', 0),
                    model.get('downloads', 0),
                    (model.get('tags') or [])[:10],
                    ['huggingface_api'],
                    json.dumps(model),
                    datetime.now(),
                    datetime.now(),
                    True,
                    'indexed'
                ))
            
            if values:
                try:
                    psycopg2.extras.execute_values(
                        cur,
                        """INSERT INTO agents (
                            id, source, source_url, source_id, name, description, author,
                            stars, downloads, tags, protocols, raw_metadata,
                            first_indexed, last_crawled, is_active, crawl_status
                        ) VALUES %s
                        ON CONFLICT (source_url) DO NOTHING""",
                        values,
                        page_size=100
                    )
                    conn.commit()
                    total_new += cur.rowcount
                except Exception as e:
                    logger.error(f"Insert error for author {author}: {e}")
                    conn.rollback()
            
            # If we got less than 100, we've reached the end
            if len(models) < 100:
                break
            
            page += 1
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error fetching author {author}: {e}")
            break
    
    return total_new


def main():
    # Collect all authors
    known = get_known_authors()
    discovered = discover_new_authors()
    all_authors = sorted(known | discovered)
    
    logger.info(f"Total unique authors to crawl: {len(all_authors)}")
    
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    total_new = 0
    
    for i, author in enumerate(all_authors, 1):
        new = fetch_author_models(author, cur, conn)
        total_new += new
        
        if i % 50 == 0 or new > 10:
            cur.execute("SELECT COUNT(*) FROM agents")
            db_total = cur.fetchone()[0]
            logger.info(f"[{i}/{len(all_authors)}] Author '{author}': +{new} | Session new: {total_new:,} | DB total: {db_total:,}")
        
        time.sleep(1)
    
    cur.execute("SELECT COUNT(*) FROM agents")
    db_total = cur.fetchone()[0]
    logger.info(f"AUTHOR CRAWL COMPLETE: {total_new:,} new agents from {len(all_authors)} authors")
    logger.info(f"Total agents in database: {db_total:,}")
    
    conn.close()


if __name__ == '__main__':
    main()
