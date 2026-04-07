#!/usr/bin/env python3
"""
HuggingFace Spaces + Datasets Crawler
Spaces: 300K+ interactive demos and apps
Datasets: 200K+ datasets
Both are separate API endpoints from /api/models
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
    format="%(asctime)s [hf-spaces-ds] %(message)s",
    handlers=[
        logging.FileHandler(f'hf_spaces_datasets_{datetime.now().strftime("%Y%m%d_%H%M")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("hf_spaces_ds")

DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')
HEADERS = {'User-Agent': 'AgentIndex/1.0', 'Accept': 'application/json'}


def generate_search_terms():
    """Generate diverse search terms for spaces and datasets."""
    terms = set()
    
    # Broad terms
    broad = [
        'agent', 'chatbot', 'assistant', 'demo', 'playground', 'app', 'tool',
        'llm', 'gpt', 'llama', 'mistral', 'gemma', 'qwen', 'phi', 'falcon',
        'stable-diffusion', 'diffusion', 'image', 'text', 'audio', 'video', 'speech',
        'classification', 'detection', 'segmentation', 'generation', 'translation',
        'summarization', 'question-answering', 'embedding', 'ner', 'ocr',
        'gradio', 'streamlit', 'docker', 'static',
        'medical', 'legal', 'financial', 'code', 'math', 'science', 'education',
        'chinese', 'japanese', 'korean', 'arabic', 'hindi', 'french', 'german', 'spanish',
        'bert', 'roberta', 't5', 'whisper', 'clip', 'vit', 'sam',
        'fine-tune', 'train', 'evaluate', 'benchmark', 'leaderboard',
        'rag', 'retrieval', 'search', 'recommendation',
        'protein', 'drug', 'molecular', 'genomics', 'climate', 'satellite',
        'music', 'art', 'creative', 'story', 'poem', 'writing',
        'robot', 'autonomous', 'simulation', 'game', 'control',
        'privacy', 'security', 'safety', 'alignment', 'bias', 'fairness',
        'dataset', 'corpus', 'benchmark', 'collection', 'annotation',
        'instruct', 'chat', 'conversation', 'dialogue', 'multi-turn',
        'multimodal', 'vision-language', 'text-to-image', 'image-to-text',
        'tts', 'asr', 'voice', 'speaker', 'emotion',
        'table', 'chart', 'graph', 'visualization', 'dashboard',
        'api', 'inference', 'serve', 'deploy', 'pipeline',
        'lora', 'adapter', 'peft', 'gguf', 'quantized',
        'langchain', 'llamaindex', 'autogen', 'crewai', 'semantic-kernel',
        'mcp', 'function-calling', 'tool-use', 'plugin',
        'sentiment', 'topic', 'keyword', 'entity', 'relation',
        'pdf', 'document', 'invoice', 'receipt', 'form',
        'face', 'pose', 'gesture', 'action', 'tracking',
        '3d', 'point-cloud', 'mesh', 'nerf', 'gaussian',
        'weather', 'forecast', 'geospatial', 'map', 'location',
        'recipe', 'food', 'fashion', 'furniture', 'architecture',
        'news', 'social-media', 'twitter', 'reddit', 'wikipedia',
    ]
    
    # Popular orgs that have lots of spaces
    orgs = [
        'huggingface', 'gradio', 'stabilityai', 'openai', 'google', 'microsoft',
        'facebook', 'nvidia', 'salesforce', 'alibaba', 'tencent', 'baidu',
        'deepseek-ai', 'Qwen', 'mistralai', 'meta-llama', 'bigscience',
        'EleutherAI', 'allenai', 'lmsys', 'THUDM', 'internlm',
    ]
    
    terms.update(broad)
    terms.update(orgs)
    
    return sorted(list(terms))


def crawl_endpoint(endpoint_type, terms):
    """Crawl either spaces or datasets."""
    
    if endpoint_type == 'spaces':
        api_url = 'https://huggingface.co/api/spaces'
        source_name = 'huggingface_space_v2'
        url_prefix = 'https://huggingface.co/spaces/'
    else:
        api_url = 'https://huggingface.co/api/datasets'
        source_name = 'huggingface_dataset_v2'
        url_prefix = 'https://huggingface.co/datasets/'
    
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    total_new = 0
    total_processed = 0
    
    logger.info(f"Starting {endpoint_type} crawl with {len(terms)} terms")
    
    for i, term in enumerate(terms, 1):
        try:
            resp = requests.get(
                api_url,
                params={'search': term, 'limit': 100, 'sort': 'likes', 'direction': '-1'},
                headers=HEADERS,
                timeout=15
            )
            
            if resp.status_code == 429:
                logger.warning(f"Rate limited. Sleeping 60s...")
                time.sleep(60)
                continue
            
            if resp.status_code != 200:
                time.sleep(1)
                continue
            
            items = resp.json()
            if not items:
                time.sleep(0.5)
                continue
            
            values = []
            for item in items:
                item_id = item.get('id', '')
                if not item_id:
                    continue
                author, name = item_id.split('/', 1) if '/' in item_id else ('unknown', item_id)
                
                values.append((
                    str(uuid.uuid4()),
                    source_name,
                    f"{url_prefix}{item_id}",
                    item_id,
                    name[:500],
                    (item.get('description') or item.get('cardData', {}).get('description', '') if isinstance(item.get('cardData'), dict) else item.get('id', ''))[:2000],
                    author[:255],
                    item.get('likes', 0),
                    item.get('downloads', 0) if 'downloads' in item else 0,
                    (item.get('tags') or [])[:10],
                    ['huggingface_api'],
                    json.dumps(item),
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
                    inserted = cur.rowcount
                    total_new += inserted
                    total_processed += len(values)
                except Exception as e:
                    logger.error(f"Insert error: {e}")
                    conn.rollback()
                    inserted = 0
            else:
                inserted = 0
            
            if i % 50 == 0 or inserted > 10:
                logger.info(f"[{endpoint_type}] [{i}/{len(terms)}] Total new: {total_new:,} | Processed: {total_processed:,} | Last '{term}': +{inserted}")
            
            time.sleep(1.5)
            
        except Exception as e:
            logger.error(f"Error for '{term}': {e}")
            time.sleep(2)
    
    cur.execute("SELECT COUNT(*) FROM agents")
    db_total = cur.fetchone()[0]
    logger.info(f"{endpoint_type.upper()} COMPLETE: {total_new:,} new from {len(terms)} terms | DB total: {db_total:,}")
    conn.close()
    return total_new


def main():
    terms = generate_search_terms()
    logger.info(f"Generated {len(terms)} search terms")
    
    # Crawl spaces first, then datasets
    spaces_new = crawl_endpoint('spaces', terms)
    logger.info(f"Spaces done: +{spaces_new:,}")
    
    datasets_new = crawl_endpoint('datasets', terms)
    logger.info(f"Datasets done: +{datasets_new:,}")
    
    logger.info(f"TOTAL NEW: {spaces_new + datasets_new:,}")


if __name__ == '__main__':
    main()
