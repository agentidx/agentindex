#!/usr/bin/env python3
"""
HuggingFace Extended Crawler - Wave 2
More terms: author names, model sizes, dataset names, paper names
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
    format="%(asctime)s [hf-w2] %(message)s",
    handlers=[
        logging.FileHandler(f'hf_wave2_{datetime.now().strftime("%Y%m%d_%H%M")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("hf_w2")


def generate_wave2_terms():
    terms = set()
    
    # Model size variations
    sizes = ['tiny', 'small', 'mini', 'base', 'medium', 'large', 'xl', 'xxl', '1b', '2b', '3b', '7b', '8b', '13b', '14b', '34b', '70b', '72b', '110b', '180b', '405b']
    
    # More architectures and their variants
    arch_bases = [
        'bert', 'roberta', 'deberta', 'albert', 'electra', 'xlnet', 'xlm',
        'distilbert', 'distilroberta', 'distilgpt2', 'minilm',
        't5', 'flan-t5', 'mt5', 'byt5', 'longt5', 'ul2', 'flan-ul2',
        'bart', 'mbart', 'pegasus', 'led', 'bigbird',
        'gpt2', 'gpt-neo', 'gpt-neox', 'gpt-j', 'cerebras-gpt',
        'clip', 'blip', 'blip2', 'siglip', 'evaclip',
        'vit', 'deit', 'beit', 'swin', 'convnext', 'dinov2', 'sam',
        'whisper', 'wav2vec', 'hubert', 'speecht5', 'bark', 'seamless',
        'stable-diffusion', 'sdxl', 'sd-turbo', 'playground', 'kandinsky',
        'controlnet', 'ip-adapter', 'lcm', 'turbo', 'lightning',
        'flux', 'pixart', 'dalle', 'midjourney',
        'llava', 'llava-next', 'cogvlm', 'fuyu', 'idefics', 'paligemma',
        'whisper-large', 'whisper-medium', 'whisper-small', 'whisper-tiny',
        'musicgen', 'audiogen', 'encodec',
        'nllb', 'madlad', 'seamless-m4t',
        'segment-anything', 'grounding-dino', 'yolov8', 'yolov9', 'yolov10', 'detr', 'rtdetr',
        'codegen', 'codegen2', 'santacoder', 'incoder', 'replit-code',
        'biogpt', 'biobert', 'pubmedbert', 'scibert', 'matbert',
        'finbert', 'secbert', 'legalbert',
        'codebert', 'graphcodebert', 'unixcoder',
        'layoutlm', 'layoutlmv2', 'layoutlmv3', 'donut', 'nougat',
        'tapas', 'turl', 'tabert',
        'esm', 'esm2', 'esmfold', 'progen', 'protgpt2',
    ]
    
    # More orgs
    orgs = [
        'mistral-community', 'DiscoResearch', 'upstage', 'kaist-ai',
        'MBZUAI', 'TencentARC', 'Phind', 'Nexusflow', 'abacusai',
        'zero-one-ai', 'togethercomputer', 'Writer', 'Reka',
        'amazon-science', 'aws-neuron', 'aws', 'azure',
        'VMware', 'SAP', 'Oracle', 'Accenture',
        'h2oai', 'lightning-ai', 'wandb', 'comet-ml',
        'argilla', 'snorkel', 'labelstudio', 'prodigy',
        'speechbrain', 'pyannote', 'coqui', 'suno',
        'timm', 'torchvision', 'ultralytics',
        'diffusers', 'peft', 'trl', 'accelerate',
        'langchain', 'llamaindex', 'haystack', 'ragas',
        'gradio', 'streamlit', 'chainlit',
        'AutoGPTQ', 'turboderp', 'exllamav2', 'oobabooga',
        'llm-jp', 'rinna', 'line-corporation', 'cyberagent',
        'yandex', 'sberbank-ai', 'ai-forever',
        'bigscience-workshop', 'aleph-alpha',
        'FlagAlpha', 'FlagAI', 'zhipuai', 'modelscope',
        'Deci', 'NeuralMagic', 'SparseML',
        'OFA-Sys', 'X-PLUG', 'DAMO-NLP-SG',
        'naver', 'kakao', 'ncsoft',
        'bharatgov', 'ai4bharat',
        'AfricaNLP', 'masakhane',
    ]
    
    # Dataset-related terms
    datasets = [
        'pile', 'red-pajama', 'slimpajama', 'refinedweb', 'falcon-refinedweb',
        'openwebtext', 'c4', 'mc4', 'oscar', 'cc100',
        'squad', 'squad2', 'natural-questions', 'triviaqa', 'hotpotqa',
        'mmlu', 'hellaswag', 'winogrande', 'arc-challenge', 'truthfulqa',
        'gsm8k', 'math', 'competition-math', 'minerva',
        'humaneval', 'mbpp', 'apps', 'codex',
        'alpaca-data', 'sharegpt', 'ultrachat', 'openchat', 'openhermes',
        'orca', 'dolphin', 'platypus', 'slimorca',
        'coco', 'imagenet', 'laion', 'laion-5b', 'coyo',
        'librispeech', 'common-voice', 'voxpopuli', 'fleurs',
        'wmt', 'opus', 'europarl', 'ted-talks',
        'conll', 'ontonotes', 'ace', 'tacred',
        'glue', 'superglue', 'xnli', 'paws',
        'imdb', 'sst2', 'yelp', 'amazon-reviews',
        'pubmed', 'mimic', 'chest-xray', 'isic',
    ]
    
    # Technique/method terms
    techniques = [
        'rag', 'retrieval-augmented', 'retrieval augmented generation',
        'dpo', 'rlhf', 'rlaif', 'ppo', 'reward-model',
        'kto', 'orpo', 'simpo', 'spin',
        'mixture-of-experts', 'moe', 'sparse-moe',
        'speculative-decoding', 'medusa', 'eagle',
        'flash-attention', 'ring-attention', 'paged-attention',
        'rope', 'alibi', 'yarn', 'longrope',
        'multimodal', 'vision-language', 'audio-visual',
        'chain-of-thought', 'tree-of-thought', 'self-consistency',
        'function-calling', 'tool-use', 'tool-calling',
        'agentic', 'agent', 'multi-agent', 'swarm',
        'embedding', 'reranker', 'cross-encoder', 'bi-encoder',
        'contrastive', 'triplet', 'siamese',
        'knowledge-distillation', 'model-compression', 'pruning',
        'continual-learning', 'incremental', 'lifelong',
        'federated', 'privacy-preserving', 'differential-privacy',
        'watermark', 'fingerprint', 'detection',
        'alignment', 'safety', 'guardrails', 'moderation',
        'structured-output', 'json-mode', 'grammar',
        'long-context', 'infinite-context', '128k', '1m-context',
    ]
    
    # Hardware/deployment terms  
    deployment = [
        'onnx-runtime', 'tensorrt-llm', 'vllm', 'tgi',
        'llamacpp', 'llama-cpp', 'ctransformers', 'exllama',
        'triton', 'fastertransformer',
        'cuda', 'rocm', 'metal', 'vulkan',
        'edge-ai', 'mobile', 'android', 'ios', 'wasm',
        'raspberry-pi', 'jetson', 'coral', 'arduino',
        'serverless', 'lambda', 'cloud-function',
        'kubernetes', 'docker', 'container',
        'api', 'rest-api', 'grpc', 'websocket',
        'benchmark', 'evaluation', 'leaderboard', 'arena',
    ]
    
    # Add all individual terms
    for t in arch_bases + orgs + datasets + techniques + deployment:
        terms.add(t)
    
    # Architecture + size combinations
    for arch in ['llama', 'mistral', 'qwen', 'gemma', 'phi', 'falcon', 'yi', 'deepseek', 'solar', 'olmo', 'mamba', 'rwkv', 'internlm', 'chatglm', 'baichuan', 'stablelm', 'opt', 'bloom', 'mpt']:
        for size in sizes:
            terms.add(f"{arch} {size}")
            terms.add(f"{arch}-{size}")
    
    # Architecture + technique
    for arch in ['bert', 'gpt2', 't5', 'llama', 'mistral', 'roberta', 'deberta', 'clip', 'vit', 'whisper']:
        for tech in ['finetuned', 'gguf', 'quantized', 'distilled', 'pruned', 'lora', 'merged', 'onnx', 'coreml', 'mlx', 'openvino', 'tensorrt']:
            terms.add(f"{arch} {tech}")
    
    # Language + architecture
    for lang in ['chinese', 'japanese', 'korean', 'arabic', 'hindi', 'russian', 'french', 'german', 'portuguese', 'turkish', 'vietnamese', 'thai', 'indonesian', 'polish', 'dutch', 'italian', 'persian', 'hebrew', 'bengali', 'urdu', 'swahili', 'tamil', 'telugu', 'malay']:
        for arch in ['bert', 'gpt', 'llama', 't5', 'roberta', 'whisper', 'wav2vec', 'clip']:
            terms.add(f"{lang} {arch}")
    
    # Domain + task
    for domain in ['medical', 'legal', 'financial', 'scientific', 'educational', 'industrial', 'agricultural', 'military', 'government']:
        for task in ['ner', 'qa', 'classification', 'summarization', 'translation', 'generation', 'detection', 'extraction', 'segmentation', 'embedding']:
            terms.add(f"{domain} {task}")
    
    # Number strings that models use
    for n in ['0.5b', '1.1b', '1.3b', '1.5b', '2.7b', '3.8b', '4.5b', '6.7b', '6.9b', '7.1b', '9b', '10b', '11b', '20b', '22b', '27b', '30b', '33b', '40b', '65b', '104b', '175b', '236b', '340b', '540b']:
        terms.add(n)
        for arch in ['llama', 'qwen', 'deepseek', 'yi', 'falcon', 'bloom', 'opt']:
            terms.add(f"{arch} {n}")
    
    # Year-based searches (recent uploads)
    for year in ['2024', '2025', '2026']:
        for topic in ['model', 'agent', 'llm', 'multimodal', 'vision', 'speech', 'embedding']:
            terms.add(f"{topic} {year}")
    
    return sorted(list(terms))


def crawl_huggingface(terms, db_url='postgresql://localhost/agentindex'):
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    headers = {
        'User-Agent': 'AgentIndex/1.0',
        'Accept': 'application/json'
    }
    
    total_new = 0
    total_processed = 0
    
    logger.info(f"Starting wave 2 crawl with {len(terms)} terms")
    
    for i, term in enumerate(terms, 1):
        try:
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
                time.sleep(1)
                continue
            
            models = resp.json()
            if not models:
                time.sleep(0.5)
                continue
            
            values = []
            for model in models:
                model_id = model.get('id', '')
                if not model_id:
                    continue
                author, name = model_id.split('/', 1) if '/' in model_id else ('unknown', model_id)
                values.append((
                    str(uuid.uuid4()),
                    'huggingface_w2',
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
            
            time.sleep(1.5)
            
        except Exception as e:
            logger.error(f"Error for '{term}': {e}")
            time.sleep(2)
    
    logger.info(f"WAVE 2 COMPLETE: {total_new:,} new agents from {len(terms)} terms ({total_processed:,} processed)")
    cur.execute("SELECT COUNT(*) FROM agents")
    total = cur.fetchone()[0]
    logger.info(f"Total agents in database: {total:,}")
    conn.close()
    return total_new


if __name__ == '__main__':
    terms = generate_wave2_terms()
    logger.info(f"Generated {len(terms)} wave 2 search terms")
    crawl_huggingface(terms)
