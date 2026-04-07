#!/usr/bin/env python3
"""PyPI crawler v3 - uses Simple API to list all packages, filters for AI-related"""
import requests, time, logging, uuid, psycopg2, psycopg2.extras, json, os, re
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [pypi3] %(message)s",
    handlers=[logging.FileHandler(f'pypi_v3_{datetime.now().strftime("%Y%m%d_%H%M")}.log'), logging.StreamHandler()])
logger = logging.getLogger("pypi3")
DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')

AI_KEYWORDS = ['ai', 'ml', 'llm', 'gpt', 'bert', 'neural', 'deep-learn', 'deeplearn', 'machine-learn',
    'machinelearn', 'nlp', 'torch', 'tensor', 'keras', 'sklearn', 'huggingface', 'transformers',
    'langchain', 'openai', 'anthropic', 'claude', 'gemini', 'mistral', 'llama',
    'chatbot', 'agent', 'embedding', 'vector', 'rag', 'diffusion',
    'whisper', 'tts', 'speech', 'ocr', 'vision', 'detect', 'recogni',
    'autogpt', 'crewai', 'autogen', 'mcp-', 'copilot', 'assistant',
    'inference', 'mlops', 'fine-tun', 'finetun', 'lora', 'quantiz',
    'prompt', 'guardrail', 'safety', 'moderat',
    'forecast', 'anomaly', 'recommend', 'classif', 'cluster',
    'robot', 'autonomous', 'drone', 'biomedic', 'clinical',
    'genai', 'generative', 'text-gen', 'image-gen', 'code-gen',
    'summariz', 'translat', 'sentiment', 'semantic', 'retriev']

def get_all_package_names():
    logger.info("Fetching all PyPI package names via Simple API...")
    r = requests.get('https://pypi.org/simple/', headers={'Accept': 'application/vnd.pypi.simple.v1+json'}, timeout=60)
    if r.status_code == 200:
        data = r.json()
        names = [p['name'] for p in data.get('projects', [])]
        logger.info(f"Total PyPI packages: {len(names):,}")
        return names
    logger.error(f"Simple API failed: {r.status_code}")
    return []

def filter_ai_packages(names):
    filtered = []
    for name in names:
        lower = name.lower().replace('_', '-')
        if any(kw in lower for kw in AI_KEYWORDS):
            filtered.append(name)
    logger.info(f"AI-related packages: {len(filtered):,}")
    return filtered

def get_package_info(name):
    try:
        r = requests.get(f'https://pypi.org/pypi/{name}/json', headers={'User-Agent': 'AgentIndex/1.0'}, timeout=10)
        if r.status_code == 200:
            info = r.json().get('info', {})
            return {
                'source_url': f'https://pypi.org/project/{name}/',
                'source_id': name,
                'name': name,
                'description': (info.get('summary') or '')[:2000],
                'author': info.get('author') or info.get('maintainer') or 'unknown',
                'tags': [k.strip() for k in (info.get('keywords') or '').split(',') if k.strip()][:10],
            }
    except: pass
    return None

def insert(agents):
    if not agents: return 0
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    vals = []
    seen = set()
    for a in agents:
        u = a['source_url']
        if u in seen: continue
        seen.add(u)
        vals.append((str(uuid.uuid4()), 'pypi_full', u, a['source_id'], a['name'][:500],
            a.get('description','')[:2000], a.get('author','unknown')[:255], 0, 0,
            a.get('tags',[])[:10], [], json.dumps(a), datetime.now(), datetime.now(), True, 'indexed'))
    n = 0
    if vals:
        try:
            psycopg2.extras.execute_values(cur,
                "INSERT INTO agents (id,source,source_url,source_id,name,description,author,stars,downloads,tags,protocols,raw_metadata,first_indexed,last_crawled,is_active,crawl_status) VALUES %s ON CONFLICT (source_url) DO NOTHING",
                vals, page_size=500)
            conn.commit(); n = cur.rowcount
        except Exception as e: logger.error(f"Insert: {e}"); conn.rollback()
    conn.close()
    return n

def main():
    all_names = get_all_package_names()
    if not all_names:
        logger.error("Could not fetch package list")
        return
    names = filter_ai_packages(all_names)
    total_new = 0
    batch = []
    for i, name in enumerate(names):
        info = get_package_info(name)
        if info: batch.append(info)
        if len(batch) >= 200 or i == len(names) - 1:
            n = insert(batch)
            total_new += n
            logger.info(f"Progress: {i+1}/{len(names)} | Batch: {len(batch)} | New: {n} | Total new: {total_new}")
            batch = []
        if (i + 1) % 20 == 0: time.sleep(0.5)
    
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM agents")
    logger.info(f"DONE: {total_new} new | DB: {cur.fetchone()[0]:,}")
    conn.close()

if __name__ == '__main__':
    main()
