#!/usr/bin/env python3
"""
HuggingFace Massive Search Crawler - 1000+ Terms
LillAnders spec: Systematiskt generera 1000+ söktermer för full coverage
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
import itertools

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [hf-massive] %(message)s")
logger = logging.getLogger("hf_massive")

class HuggingFaceMassiveSearchCrawler:
    def __init__(self):
        self.headers = {
            'User-Agent': 'AgentIndex/1.0 - Massive Search Discovery',
            'Accept': 'application/json'
        }
        
        # Direct PostgreSQL connection
        self.conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex'))
        self.cursor = self.conn.cursor()
        
        # Generate massive search terms
        self.search_terms = self.generate_massive_search_terms()
        
        logger.info(f"🚀 Massive search crawler with {len(self.search_terms):,} search terms")
    
    def generate_massive_search_terms(self):
        """Generate 1000+ systematic search terms."""
        terms = set()
        
        # 1. CORE ML/AI TERMS (100+ terms)
        ml_tasks = [
            'classification', 'detection', 'segmentation', 'generation', 'translation',
            'summarization', 'embedding', 'tokenization', 'preprocessing', 'postprocessing',
            'clustering', 'regression', 'prediction', 'forecasting', 'optimization',
            'reinforcement', 'supervised', 'unsupervised', 'self-supervised', 'semi-supervised',
            'few-shot', 'zero-shot', 'one-shot', 'multi-shot', 'in-context', 'meta-learning',
            'transfer', 'fine-tuning', 'pretraining', 'continual', 'lifelong', 'federated',
            'adversarial', 'generative', 'discriminative', 'autoregressive', 'non-autoregressive',
            'encoder', 'decoder', 'encoder-decoder', 'attention', 'self-attention', 'cross-attention',
            'multi-head', 'transformer', 'lstm', 'gru', 'rnn', 'cnn', 'mlp', 'autoencoder',
            'gan', 'vae', 'diffusion', 'flow', 'normalizing', 'energy', 'score', 'denoising'
        ]
        terms.update(ml_tasks)
        
        # 2. MODEL ARCHITECTURES (200+ terms)
        architectures = [
            # Transformers
            'bert', 'roberta', 'distilbert', 'albert', 'electra', 'deberta', 'bigbird',
            'longformer', 'reformer', 'linformer', 'performer', 'synthesizer', 'funnel',
            'squeezebert', 'mobilebert', 'convbert', 'flaubert', 'camembert', 'umberto',
            
            # Generative models
            'gpt', 'gpt2', 'gpt3', 'gpt4', 'chatgpt', 'instructgpt', 'codegpt', 'webgpt',
            'llama', 'llama2', 'llama3', 'alpaca', 'vicuna', 'guanaco', 'koala', 'dolly',
            'claude', 'anthropic', 'palm', 'bard', 'gemini', 'chinchilla', 'flamingo',
            'galactica', 'bloom', 'opt', 'bigscience', 'ul2', 'flan', 'instruction',
            
            # Coding models  
            'codex', 'copilot', 'codegen', 'incoder', 'codet5', 'codebert', 'graphcodebert',
            'plbart', 'codesearchnet', 'code2code', 'text2code', 'code2text',
            
            # Multimodal
            'clip', 'align', 'dalle', 'dalle2', 'imagen', 'parti', 'flamingo', 'blip',
            'blip2', 'instructblip', 'minigpt', 'llava', 'mplug', 'x-vlm', 'albef',
            'vilt', 'layoutlm', 'structbert', 'dino', 'dinov2', 'mae', 'beit', 'swin',
            
            # Newer architectures
            'mistral', 'mixtral', 'falcon', 'mpt', 'pythia', 'redpajama', 'openchat',
            'starcode', 'starcoder', 'phi', 'phi2', 'phi3', 'gemma', 'gemma2', 'qwen',
            'qwen2', 'yi', 'deepseek', 'internlm', 'baichuan', 'chatglm', 'moss'
        ]
        terms.update(architectures)
        
        # 3. FRAMEWORKS & LIBRARIES (100+ terms)
        frameworks = [
            'transformers', 'diffusers', 'tokenizers', 'datasets', 'accelerate', 'optimum',
            'peft', 'lora', 'qlora', 'adalora', 'ia3', 'prefix', 'prompt', 'adapter',
            'trl', 'rlhf', 'ppo', 'dpo', 'reward', 'sft', 'instruct', 'chat', 'alignment',
            'pytorch', 'tensorflow', 'jax', 'flax', 'keras', 'onnx', 'openvino', 'tensorrt',
            'triton', 'vllm', 'fastapi', 'gradio', 'streamlit', 'chainlit', 'langchain',
            'llamaindex', 'haystack', 'sentence-transformers', 'spacy', 'nltk', 'scikit',
            'pandas', 'numpy', 'matplotlib', 'seaborn', 'plotly', 'wandb', 'tensorboard',
            'mlflow', 'clearml', 'neptune', 'comet', 'docker', 'kubernetes', 'ray'
        ]
        terms.update(frameworks)
        
        # 4. DOMAINS & APPLICATIONS (150+ terms)
        domains = [
            # Medical/Healthcare
            'medical', 'healthcare', 'clinical', 'biomedical', 'genomics', 'proteomics',
            'drug', 'pharmaceutical', 'diagnosis', 'radiology', 'pathology', 'oncology',
            'cardiology', 'neurology', 'mental', 'covid', 'pandemic', 'epidemiology',
            
            # Finance/Business
            'finance', 'financial', 'trading', 'investment', 'risk', 'fraud', 'banking',
            'insurance', 'credit', 'loan', 'market', 'stock', 'crypto', 'blockchain',
            'economics', 'accounting', 'audit', 'compliance', 'kyc', 'aml', 'regtech',
            
            # Legal/Government
            'legal', 'law', 'contract', 'regulation', 'compliance', 'litigation', 'patent',
            'government', 'policy', 'public', 'civic', 'election', 'democracy', 'judiciary',
            
            # Education/Research
            'education', 'educational', 'academic', 'research', 'scientific', 'scholarly',
            'university', 'school', 'student', 'teacher', 'learning', 'pedagogy', 'mooc',
            
            # Technology/Engineering
            'code', 'programming', 'software', 'hardware', 'system', 'network', 'security',
            'cybersecurity', 'devops', 'mlops', 'dataops', 'cloud', 'edge', 'iot', 'robotics',
            'autonomous', 'vehicle', 'automotive', 'manufacturing', 'industrial', 'energy',
            
            # Media/Entertainment
            'media', 'entertainment', 'gaming', 'game', 'music', 'audio', 'video', 'image',
            'photo', 'art', 'creative', 'design', 'fashion', 'sport', 'sports', 'news',
            'journalism', 'social', 'recommendation', 'personalization', 'advertising'
        ]
        terms.update(domains)
        
        # 5. TECHNICAL CONCEPTS (100+ terms)
        technical = [
            'quantization', 'pruning', 'distillation', 'compression', 'optimization',
            'inference', 'serving', 'deployment', 'scalability', 'performance', 'efficiency',
            'latency', 'throughput', 'memory', 'gpu', 'cpu', 'tpu', 'asic', 'fpga',
            'mixed-precision', 'fp16', 'fp32', 'int8', 'int4', 'bfloat16', 'dynamic',
            'static', 'graph', 'eager', 'compilation', 'jit', 'xla', 'mlir', 'openai',
            'anthropic', 'google', 'microsoft', 'meta', 'nvidia', 'intel', 'amd', 'apple'
        ]
        terms.update(technical)
        
        # 6. DATA TYPES & MODALITIES (50+ terms)
        modalities = [
            'text', 'nlp', 'language', 'speech', 'audio', 'voice', 'sound', 'music',
            'image', 'vision', 'photo', 'picture', 'video', 'visual', 'multimodal',
            'tabular', 'structured', 'unstructured', 'time-series', 'temporal', 'spatial',
            'graph', 'knowledge', 'semantic', 'syntactic', 'morphological', 'phonetic'
        ]
        terms.update(modalities)
        
        # 7. LANGUAGES & LOCALES (100+ terms)
        languages = [
            'english', 'chinese', 'spanish', 'french', 'german', 'japanese', 'korean',
            'arabic', 'hindi', 'portuguese', 'russian', 'italian', 'dutch', 'swedish',
            'norwegian', 'danish', 'finnish', 'polish', 'czech', 'hungarian', 'turkish',
            'greek', 'hebrew', 'thai', 'vietnamese', 'indonesian', 'malay', 'filipino',
            'multilingual', 'cross-lingual', 'zero-shot', 'transfer', 'code-switching'
        ]
        terms.update(languages)
        
        # 8. COMBINATIONS (300+ terms) - Most powerful for coverage
        combinations = []
        
        # Domain + Architecture combinations
        key_domains = ['medical', 'finance', 'legal', 'code', 'vision', 'audio']
        key_architectures = ['bert', 'gpt', 'llama', 'clip', 'whisper', 't5']
        for domain, arch in itertools.product(key_domains, key_architectures):
            combinations.append(f"{domain}-{arch}")
            combinations.append(f"{domain} {arch}")
        
        # Task + Model combinations  
        key_tasks = ['classification', 'generation', 'detection', 'translation', 'embedding']
        key_models = ['transformer', 'diffusion', 'gan', 'vae', 'lstm', 'cnn']
        for task, model in itertools.product(key_tasks, key_models):
            combinations.append(f"{task}-{model}")
            combinations.append(f"{task} {model}")
        
        terms.update(combinations)
        
        # 9. SINGLE LETTERS, NUMBERS & SHORT TERMS (for edge cases)
        short_terms = list('abcdefghijklmnopqrstuvwxyz') + [str(i) for i in range(10)]
        short_terms += ['ai', 'ml', 'dl', 'cv', 'nlp', 'asr', 'tts', 'ocr', 'ner', 'pos']
        terms.update(short_terms)
        
        # 10. COMPANY/ORG NAMES (50+ terms)
        orgs = [
            'openai', 'anthropic', 'google', 'microsoft', 'meta', 'nvidia', 'intel', 'amd',
            'apple', 'amazon', 'alibaba', 'baidu', 'tencent', 'huawei', 'samsung', 'ibm',
            'stanford', 'mit', 'berkeley', 'cmu', 'oxford', 'cambridge', 'deepmind',
            'eleutherai', 'bigscience', 'stabilityai', 'runway', 'replicate', 'together'
        ]
        terms.update(orgs)
        
        final_terms = list(terms)
        logger.info(f"Generated {len(final_terms):,} unique search terms")
        return final_terms
    
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
            return models
            
        except Exception as e:
            logger.error(f"Error searching '{query}': {e}")
            return []
    
    def bulk_insert_models(self, models, source_suffix=""):
        """Ultra-fast bulk insert with ON CONFLICT DO NOTHING."""
        if not models:
            return 0
            
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
                    name[:500],
                    (model.get('description') or '')[:2000],
                    author[:255],
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
                
            except Exception as e:
                logger.error(f"Error processing model {model.get('id', 'unknown')}: {e}")
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
    
    def crawl_massive_search(self):
        """Crawl using all search terms - FULL SPEED."""
        logger.info(f"🎯 STARTING MASSIVE SEARCH CRAWL")
        logger.info(f"Target: {len(self.search_terms):,} search terms")
        
        total_processed = 0
        total_inserted = 0
        unique_models = set()
        
        start_time = time.time()
        
        for i, term in enumerate(self.search_terms, 1):
            batch_start = time.time()
            
            try:
                # Search for models
                models = self.search_models(term, limit=50)
                
                if models:
                    # Track unique models
                    term_unique = set(m['id'] for m in models if 'id' in m)
                    new_unique = term_unique - unique_models
                    unique_models.update(term_unique)
                    
                    # Insert models
                    inserted_count = self.bulk_insert_models(models)
                    
                    total_processed += len(models)
                    total_inserted += inserted_count
                    
                    if len(new_unique) > 0:  # Only log if we found new models
                        logger.info(f"[{i:,}/{len(self.search_terms):,}] '{term}': {len(models)} models, {len(new_unique)} new unique, {inserted_count} inserted")
                
                # Progress report every 100 terms
                if i % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = total_processed / elapsed if elapsed > 0 else 0
                    
                    logger.info(f"📊 Progress: {i:,}/{len(self.search_terms):,} terms ({i/len(self.search_terms)*100:.1f}%)")
                    logger.info(f"   {len(unique_models):,} unique models, {total_inserted:,} inserted")
                    logger.info(f"   Rate: {rate:.1f} models/sec, {len(unique_models)/elapsed:.1f} unique/sec")
                
                # Conservative rate limiting for HuggingFace API
                batch_time = time.time() - batch_start
                if batch_time < 2.0:  # Max 0.5 requests/sec (very conservative)
                    time.sleep(2.0 - batch_time)
                    
            except Exception as e:
                logger.error(f"Error processing term '{term}': {e}")
                continue
        
        elapsed_hours = (time.time() - start_time) / 3600
        logger.info(f"🏁 MASSIVE SEARCH CRAWL COMPLETE!")
        logger.info(f"📊 {len(self.search_terms):,} terms → {len(unique_models):,} unique models → {total_inserted:,} inserted in {elapsed_hours:.1f}h")
        logger.info(f"Rate: {total_processed/elapsed_hours:.0f} models/hour, {len(unique_models)/elapsed_hours:.0f} unique/hour")
        
        return {
            'terms_processed': len(self.search_terms),
            'unique_models': len(unique_models),
            'total_inserted': total_inserted,
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

if __name__ == "__main__":
    crawler = HuggingFaceMassiveSearchCrawler()
    result = crawler.crawl_massive_search()
    print(f"Final result: {result}")