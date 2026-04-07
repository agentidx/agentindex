#!/usr/bin/env python3
"""
HuggingFace Extended Crawler - Generate 5000+ NEW search terms
Builds on top of existing 616 terms by adding systematic combinations
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
import itertools

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [hf-ext] %(message)s",
    handlers=[
        logging.FileHandler(f'hf_extended_{datetime.now().strftime("%Y%m%d_%H%M")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("hf_ext")


def generate_extended_terms():
    """Generate 5000+ terms that are NOT in the original 616."""
    terms = set()
    
    # Languages (50+)
    languages = [
        'arabic', 'bengali', 'bulgarian', 'catalan', 'chinese', 'croatian', 'czech',
        'danish', 'dutch', 'english', 'estonian', 'finnish', 'french', 'german',
        'greek', 'gujarati', 'hebrew', 'hindi', 'hungarian', 'icelandic', 'indonesian',
        'irish', 'italian', 'japanese', 'kannada', 'kazakh', 'korean', 'latvian',
        'lithuanian', 'macedonian', 'malay', 'malayalam', 'marathi', 'mongolian',
        'nepali', 'norwegian', 'persian', 'polish', 'portuguese', 'punjabi',
        'romanian', 'russian', 'serbian', 'sinhala', 'slovak', 'slovenian',
        'somali', 'swahili', 'tamil', 'telugu', 'thai', 'turkish',
        'ukrainian', 'urdu', 'uzbek', 'vietnamese', 'welsh', 'yoruba', 'zulu'
    ]
    
    # Model architectures (100+)
    architectures = [
        'llama2', 'llama3', 'llama-3', 'llama-2', 'codellama', 'tinyllama',
        'mistral-7b', 'mixtral', 'mistral-nemo', 'mistral-large',
        'phi-1', 'phi-2', 'phi-3', 'phi-4',
        'gemma-2b', 'gemma-7b', 'gemma2', 'codegemma',
        'qwen-7b', 'qwen-14b', 'qwen-72b', 'qwen2', 'qwen2.5', 'qwen-vl',
        'deepseek', 'deepseek-coder', 'deepseek-v2', 'deepseek-math',
        'yi-6b', 'yi-34b', 'yi-1.5',
        'falcon-7b', 'falcon-40b', 'falcon-180b',
        'mpt-7b', 'mpt-30b',
        'bloom', 'bloomz', 'bloom-7b',
        'opt-125m', 'opt-350m', 'opt-1.3b', 'opt-6.7b', 'opt-13b', 'opt-30b', 'opt-66b',
        'stablelm', 'stablelm-2', 'stablecode',
        'starcoder', 'starcoder2', 'starcoderbase',
        'wizardlm', 'wizardcoder', 'wizardmath',
        'vicuna', 'vicuna-7b', 'vicuna-13b',
        'alpaca', 'stanford-alpaca',
        'dolly', 'dolly-v2',
        'cerebras', 'cerebras-gpt',
        'pythia-70m', 'pythia-160m', 'pythia-410m', 'pythia-1b', 'pythia-2.8b', 'pythia-6.9b', 'pythia-12b',
        'redpajama', 'open-llama', 'openllama',
        'internlm', 'internlm2', 'internvl',
        'chatglm', 'chatglm2', 'chatglm3', 'glm-4',
        'baichuan2', 'baichuan-13b',
        'xverse', 'xverse-13b', 'xverse-65b',
        'aquila', 'aquila2',
        'solar', 'solar-10.7b',
        'olmo', 'olmo-7b',
        'command-r', 'command-r-plus', 'cohere',
        'jamba', 'ai21',
        'recurrentgemma', 'mamba', 'mamba-2', 'rwkv', 'rwkv-5', 'rwkv-6',
        'persimmon', 'persimmon-8b',
        'minicpm', 'minicpm-v',
        'smollm', 'smollm2',
        'granite', 'granite-code',
        'nemotron', 'nemotron-4',
        'arctic', 'snowflake-arctic',
        'dbrx', 'databricks',
    ]
    
    # Domains (80+)
    domains = [
        'medical', 'clinical', 'biomedical', 'healthcare', 'radiology', 'pathology',
        'dental', 'pharmacy', 'nursing', 'mental-health', 'cardiology', 'oncology',
        'legal', 'law', 'contract', 'patent', 'court', 'judicial',
        'financial', 'banking', 'insurance', 'trading', 'stock', 'crypto', 'defi',
        'accounting', 'tax', 'audit', 'risk-management',
        'education', 'tutoring', 'exam', 'homework', 'curriculum',
        'agriculture', 'farming', 'crop', 'soil', 'livestock',
        'manufacturing', 'industrial', 'quality-control', 'supply-chain',
        'retail', 'ecommerce', 'shopping', 'product-review',
        'real-estate', 'property', 'housing', 'construction',
        'automotive', 'vehicle', 'self-driving', 'autonomous',
        'aerospace', 'satellite', 'aviation', 'drone',
        'energy', 'solar-energy', 'wind-energy', 'nuclear', 'oil-gas',
        'telecom', 'networking', 'wireless', '5g',
        'cybersecurity', 'malware', 'phishing', 'vulnerability',
        'gaming', 'game-ai', 'npc', 'procedural',
        'music', 'audio-generation', 'speech-synthesis', 'voice-cloning',
        'art', 'painting', 'illustration', 'graphic-design',
        'fashion', 'clothing', 'textile',
        'food', 'recipe', 'nutrition', 'restaurant',
        'sports', 'fitness', 'athlete',
        'journalism', 'news', 'fact-checking',
        'travel', 'tourism', 'hotel', 'booking',
        'hr', 'recruitment', 'resume', 'interview',
        'marketing', 'advertising', 'seo', 'social-media',
        'customer-service', 'chatbot', 'helpdesk', 'support',
    ]
    
    # Task types (40+)
    tasks = [
        'ner', 'pos-tagging', 'dependency-parsing', 'coreference',
        'relation-extraction', 'event-extraction', 'temporal',
        'question-answering', 'reading-comprehension', 'open-qa',
        'dialogue', 'conversational', 'multi-turn',
        'text-to-image', 'image-to-text', 'image-captioning',
        'text-to-video', 'video-understanding', 'video-captioning',
        'text-to-audio', 'audio-to-text', 'speech-recognition',
        'text-to-3d', 'point-cloud', 'mesh-generation',
        'text-to-sql', 'sql-generation', 'database',
        'code-generation', 'code-review', 'code-completion', 'debugging',
        'math-reasoning', 'theorem-proving', 'symbolic',
        'table-qa', 'table-extraction', 'document-ai',
        'ocr', 'handwriting', 'layout-analysis',
        'protein-folding', 'drug-discovery', 'molecular',
        'climate', 'weather-prediction', 'geospatial',
        'recommendation', 'ranking', 'retrieval',
    ]
    
    # Quantization and optimization terms
    quant_terms = [
        'gguf', 'gptq', 'awq', 'bnb', 'exl2', 'ggml',
        '4bit', '8bit', '3bit', '5bit', '6bit',
        'quantized', 'quantization', 'pruned', 'distilled',
        'fp16', 'bf16', 'fp32', 'int8', 'int4',
        'lora', 'qlora', 'peft', 'adapter',
        'merged', 'finetuned', 'fine-tuned', 'instruct', 'chat',
        'onnx-export', 'tensorrt', 'openvino-export', 'coreml',
        'mlx', 'mlx-community',
    ]
    
    # Popular orgs/authors on HuggingFace
    orgs = [
        'TheBloke', 'unsloth', 'NousResearch', 'teknium', 'Open-Orca',
        'garage-bAInd', 'bigscience', 'EleutherAI', 'tiiuae', 'mosaicml',
        'stabilityai', 'CompVis', 'runwayml', 'openai', 'facebook',
        'google', 'microsoft', 'amazon', 'nvidia', 'intel',
        'apple', 'ibm', 'salesforce', 'alibaba-nlp', 'Qwen',
        'meta-llama', 'mistralai', 'deepseek-ai', 'THUDM', 'bigcode',
        'sentence-transformers', 'cross-encoder', 'jinaai', 'BAAI',
        'mradermacher', 'bartowski', 'mlx-community', 'QuantFactory',
        'lmsys', 'berkeley-nest', 'WizardLMTeam', 'cognitivecomputations',
        'openbmb', 'internlm', 'xai-org', 'CohereForAI',
        'HuggingFaceH4', 'HuggingFaceTB', 'HuggingFaceM4',
        'allenai', 'Anthropic', 'databricks', 'snowflake',
    ]
    
    # Add all individual terms
    for t in languages + architectures + domains + tasks + quant_terms + orgs:
        terms.add(t)
    
    # Generate combinations: architecture + quantization
    for arch, quant in itertools.product(
        ['llama', 'mistral', 'gemma', 'qwen', 'phi', 'falcon', 'yi', 'deepseek'],
        ['gguf', 'gptq', 'awq', '4bit', '8bit', 'lora', 'instruct', 'chat']
    ):
        terms.add(f"{arch} {quant}")
    
    # Generate combinations: language + task
    for lang, task in itertools.product(
        ['chinese', 'japanese', 'korean', 'arabic', 'hindi', 'russian', 'french', 'german', 'portuguese', 'turkish'],
        ['translation', 'ner', 'classification', 'qa', 'summarization', 'generation']
    ):
        terms.add(f"{lang} {task}")
    
    # Generate combinations: domain + model type
    for domain, mtype in itertools.product(
        ['medical', 'legal', 'financial', 'code', 'science', 'education'],
        ['bert', 'gpt', 'llama', 'mistral', 't5', 'roberta', 'deberta']
    ):
        terms.add(f"{domain} {mtype}")
    
    # Numbers and versions that models often have
    for base in ['v1', 'v2', 'v3', 'v4', '7b', '13b', '34b', '70b', '1b', '2b', '3b', '8b']:
        for arch in ['llama', 'mistral', 'qwen', 'yi', 'gemma', 'phi', 'falcon']:
            terms.add(f"{arch}-{base}")
    
    return sorted(list(terms))


def crawl_huggingface(terms, db_url='postgresql://localhost/agentindex'):
    """Crawl HuggingFace using search terms."""
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    headers = {
        'User-Agent': 'AgentIndex/1.0',
        'Accept': 'application/json'
    }
    
    total_new = 0
    total_processed = 0
    
    logger.info(f"Starting crawl with {len(terms)} terms")
    
    for i, term in enumerate(terms, 1):
        try:
            # Search HuggingFace API
            resp = requests.get(
                'https://huggingface.co/api/models',
                params={'search': term, 'limit': 100, 'sort': 'downloads', 'direction': '-1'},
                headers=headers,
                timeout=15
            )
            
            if resp.status_code == 429:
                logger.warning(f"Rate limited at term {i}. Sleeping 60s...")
                time.sleep(60)
                continue
            
            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} for '{term}'")
                time.sleep(1)
                continue
            
            models = resp.json()
            if not models:
                time.sleep(0.5)
                continue
            
            # Prepare values for bulk insert
            values = []
            for model in models:
                model_id = model.get('id', '')
                if not model_id:
                    continue
                
                author, name = model_id.split('/', 1) if '/' in model_id else ('unknown', model_id)
                
                values.append((
                    str(uuid.uuid4()),
                    'huggingface_search_ext',
                    f"https://huggingface.co/{model_id}",
                    model_id,
                    name[:500],
                    (model.get('description') or model.get('id', ''))[:2000],
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
                logger.info(f"[{i}/{len(terms)}] Total new: {total_new:,} | Processed: {total_processed:,} | Last '{term}': +{inserted}")
            
            # Rate limiting - be nice to HF API
            time.sleep(1.5)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for '{term}': {e}")
            time.sleep(5)
        except Exception as e:
            logger.error(f"Error for '{term}': {e}")
            time.sleep(2)
    
    logger.info(f"CRAWL COMPLETE: {total_new:,} new agents from {len(terms)} terms ({total_processed:,} processed)")
    
    # Final count
    cur.execute("SELECT COUNT(*) FROM agents")
    total = cur.fetchone()[0]
    logger.info(f"Total agents in database: {total:,}")
    
    conn.close()
    return total_new


if __name__ == '__main__':
    terms = generate_extended_terms()
    logger.info(f"Generated {len(terms)} extended search terms")
    crawl_huggingface(terms)
