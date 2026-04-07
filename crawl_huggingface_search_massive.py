#!/usr/bin/env python3
"""
HuggingFace Search-Based Massive Crawler
Anders requirement: 500K models på 48h genom att använda search API

Strategy: 
- Använd HF search API med hundratals olika queries
- Search API fungerar medan offset inte gör det  
- Bred coverage genom systematiska söktermer
- ON CONFLICT DO NOTHING för snabbhet
"""

import requests
import time
import logging
from datetime import datetime
import uuid
import psycopg2
from dotenv import load_dotenv
import os
import string
import itertools

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [hf-search] %(message)s")
logger = logging.getLogger("hf_search")

class HuggingFaceSearchMassiveCrawler:
    def __init__(self):
        self.headers = {
            'User-Agent': 'AgentIndex/1.0 - Search-Based Discovery',
            'Accept': 'application/json'
        }
        
        # Direct PostgreSQL connection for speed
        self.conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex'))
        self.cursor = self.conn.cursor()
        
        # Generate comprehensive search terms
        self.search_terms = self.generate_search_terms()
        
        logger.info(f"🚀 Search-based crawler with {len(self.search_terms)} search terms")
    
    def generate_search_terms(self):
        """Generate comprehensive list of search terms."""
        terms = []
        
        # Core AI/ML terms
        core_terms = [
            'bert', 'gpt', 'llama', 'mistral', 'claude', 'gemini', 'qwen', 'phi',
            'transformer', 'attention', 'embedding', 'tokenizer', 'decoder', 'encoder',
            'diffusion', 'stable', 'flux', 'vae', 'unet', 'controlnet', 'lora',
            'vision', 'clip', 'dino', 'sam', 'yolo', 'rcnn', 'detection', 'segmentation',
            'audio', 'speech', 'whisper', 'wav2vec', 'music', 'sound', 'tts',
            'classification', 'regression', 'clustering', 'reinforcement', 'supervised',
            'generation', 'completion', 'summarization', 'translation', 'qa',
            'pytorch', 'tensorflow', 'jax', 'onnx', 'openvino', 'tensorrt',
            'huggingface', 'transformers', 'diffusers', 'datasets', 'tokenizers',
            'fine-tuned', 'pretrained', 'checkpoint', 'weights', 'model',
            'agent', 'assistant', 'chatbot', 'conversational', 'dialogue',
            'multimodal', 'cross-modal', 'zero-shot', 'few-shot', 'in-context'
        ]
        terms.extend(core_terms)
        
        # Programming languages
        languages = [
            'python', 'javascript', 'java', 'cpp', 'rust', 'go', 'swift', 'kotlin',
            'typescript', 'scala', 'ruby', 'php', 'csharp', 'sql', 'html', 'css'
        ]
        terms.extend(languages)
        
        # Specific model names/families
        model_families = [
            'albert', 'roberta', 'deberta', 'electra', 'distilbert', 'xlnet',
            'gpt2', 'gpt3', 'gpt4', 'llama2', 'llama3', 'vicuna', 'alpaca',
            'falcon', 'mpt', 'bloom', 'opt', 't5', 'ul2', 'palm', 'chinchilla',
            'dalle', 'midjourney', 'imagen', 'parti', 'flamingo', 'blip'
        ]
        terms.extend(model_families)
        
        # Domains/applications
        domains = [
            'medical', 'legal', 'finance', 'code', 'math', 'science', 'news',
            'social', 'gaming', 'education', 'business', 'research', 'academic',
            'clinical', 'biomedical', 'genomics', 'chemistry', 'physics'
        ]
        terms.extend(domains)
        
        # Single letters and short terms (to catch everything)
        single_chars = list(string.ascii_lowercase) + list(string.digits)
        terms.extend(single_chars)
        
        # Two-letter combinations (most common)
        common_pairs = ['ai', 'ml', 'dl', 'cv', 'nlp', 'nn', 'lr', 'rf', 'dt', 'sv']
        terms.extend(common_pairs)
        
        # Three-letter combinations (tech abbreviations)
        tech_abbrevs = [
            'api', 'sdk', 'cli', 'gui', 'sql', 'orm', 'jwt', 'xml', 'csv', 'pdf',
            'gpu', 'cpu', 'ram', 'ssd', 'hdd', 'usb', 'led', 'lcd', 'app', 'web'
        ]
        terms.extend(tech_abbrevs)
        
        return list(set(terms))  # Remove duplicates
    
    def search_models(self, query, limit=50):
        """Search for models using HuggingFace search API."""
        url = "https://huggingface.co/api/models"
        params = {
            'search': query,
            'limit': limit
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            models = response.json()
            
            logger.debug(f"Query '{query}': {len(models)} models")
            return models
            
        except Exception as e:
            logger.error(f"Error searching '{query}': {e}")
            return []
    
    def fast_insert_models(self, models, source_suffix=""):
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
                    f'huggingface_search{source_suffix}',
                    f"https://huggingface.co/{model_id}",
                    model_id,
                    name[:500],  # Truncate if needed
                    (model.get('description') or '')[:2000],  # Truncate description
                    author[:255],
                    model.get('likes', 0),
                    model.get('downloads', 0),
                    (model.get('tags') or [])[:10],  # Limit tags
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
            
            return len(values)
            
        except Exception as e:
            logger.error(f"Bulk insert error: {e}")
            self.conn.rollback()
            return 0
    
    def crawl_search_massive(self, max_terms=None):
        """Crawl using all search terms."""
        logger.info(f"🎯 STARTING MASSIVE SEARCH CRAWL")
        
        terms_to_use = self.search_terms[:max_terms] if max_terms else self.search_terms
        logger.info(f"Using {len(terms_to_use)} search terms")
        
        total_processed = 0
        total_inserted = 0
        unique_models = set()
        
        start_time = time.time()
        
        for i, term in enumerate(terms_to_use, 1):
            batch_start = time.time()
            
            try:
                # Search for models
                models = self.search_models(term, limit=50)
                
                if models:
                    # Track unique models
                    term_unique = set(m['id'] for m in models)
                    new_unique = term_unique - unique_models
                    unique_models.update(term_unique)
                    
                    # Insert models
                    inserted_count = self.fast_insert_models(models)
                    
                    total_processed += len(models)
                    total_inserted += inserted_count
                    
                    logger.info(f"[{i}/{len(terms_to_use)}] '{term}': {len(models)} models, {len(new_unique)} new unique, {inserted_count} inserted")
                else:
                    logger.debug(f"[{i}/{len(terms_to_use)}] '{term}': No results")
                
                # Progress report every 50 terms
                if i % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = total_processed / elapsed if elapsed > 0 else 0
                    
                    logger.info(f"📊 Progress: {i} terms, {len(unique_models)} unique models, {total_inserted} inserted")
                    logger.info(f"Rate: {rate:.1f} models/sec, Unique rate: {len(unique_models)/elapsed:.1f}/sec")
                
                # Rate limiting
                batch_time = time.time() - batch_start
                if batch_time < 0.3:
                    time.sleep(0.3 - batch_time)
                    
            except Exception as e:
                logger.error(f"Error processing term '{term}': {e}")
                continue
        
        elapsed_hours = (time.time() - start_time) / 3600
        logger.info(f"🏁 SEARCH CRAWL COMPLETE!")
        logger.info(f"📊 {len(terms_to_use)} terms → {len(unique_models)} unique models → {total_inserted} inserted in {elapsed_hours:.1f}h")
        
        return {
            'terms_processed': len(terms_to_use),
            'unique_models': len(unique_models),
            'total_inserted': total_inserted,
            'hours': elapsed_hours
        }
    
    def __del__(self):
        """Cleanup database connection."""
        if hasattr(self, 'cursor'):
            self.cursor.close()
        if hasattr(self, 'conn'):
            self.conn.close()

if __name__ == "__main__":
    # Test run with limited terms
    crawler = HuggingFaceSearchMassiveCrawler()
    result = crawler.crawl_search_massive(max_terms=100)  # Test with first 100 terms
    print(f"Search crawl result: {result}")