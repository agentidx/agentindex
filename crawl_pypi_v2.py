#!/usr/bin/env python3
"""PyPI crawler v2 - uses known package prefixes and PyPI JSON API"""
import requests, time, logging, uuid, psycopg2, psycopg2.extras, json, os, xmlrpc.client
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [pypi2] %(message)s",
    handlers=[logging.FileHandler(f'pypi_v2_{datetime.now().strftime("%Y%m%d_%H%M")}.log'), logging.StreamHandler()])
logger = logging.getLogger("pypi2")
DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')
HEADERS = {'User-Agent': 'AgentIndex/1.0'}

def get_all_packages_xmlrpc():
    """Get all package names via XML-RPC, then filter for AI-related"""
    logger.info("Fetching all PyPI package names via XML-RPC...")
    client = xmlrpc.client.ServerProxy('https://pypi.org/pypi')
    all_names = client.list_packages()
    logger.info(f"Total PyPI packages: {len(all_names):,}")
    
    AI_KEYWORDS = ['ai', 'ml', 'llm', 'gpt', 'bert', 'neural', 'deep-learn', 'machine-learn',
        'nlp', 'torch', 'tensor', 'keras', 'sklearn', 'huggingface', 'transformers',
        'langchain', 'openai', 'anthropic', 'claude', 'gemini', 'mistral', 'llama',
        'chatbot', 'agent', 'embedding', 'vector', 'rag', 'diffusion', 'stable-diffusion',
        'whisper', 'tts', 'speech', 'ocr', 'vision', 'detection', 'recognition',
        'autogpt', 'crewai', 'autogen', 'mcp', 'copilot', 'assistant',
        'inference', 'model-serving', 'mlops', 'fine-tun', 'lora', 'quantiz',
        'prompt', 'guardrail', 'alignment', 'safety', 'moderation',
        'forecast', 'anomaly', 'recommend', 'classify', 'cluster', 'regress',
        'robotics', 'autonomous', 'drone', 'self-driv',
        'biomedical', 'clinical', 'drug-discov', 'medical-ai',
        'knowledge-graph', 'reasoning', 'planning', 'workflow', 'automat',
        'genai', 'generative', 'text-gen', 'image-gen', 'code-gen',
        'summariz', 'translat', 'question-answer', 'sentiment',
        'semantic', 'search', 'retriev', 'document-ai', 'data-extract']
    
    filtered = []
    for name in all_names:
        lower = name.lower().replace('_', '-')
        if any(kw in lower for kw in AI_KEYWORDS):
            filtered.append(name)
    
    logger.info(f"AI-related packages: {len(filtered):,}")
    return filtered

def get_package_info(name):
    try:
        r = requests.get(f'https://pypi.org/pypi/{name}/json', headers=HEADERS, timeout=10)
        if r.status_code == 200:
            info = r.json().get('info', {})
            return {
                'source_url': f'https://pypi.org/project/{name}/',
                'source_id': name,
                'name': name,
                'description': (info.get('summary') or '')[:2000],
                'author': info.get('author') or info.get('maintainer') or 'unknown',
                'tags': [k.strip() for k in (info.get('keywords') or '').split(',') if k.strip()][:10],
                'version': info.get('version', ''),
            }
        time.sleep(0.2)
    except Exception as e:
        if '429' in str(e): time.sleep(10)
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
    names = get_all_packages_xmlrpc()
    total_new = 0
    batch = []
    
    for i, name in enumerate(names):
        info = get_package_info(name)
        if info:
            batch.append(info)
        
        if len(batch) >= 200 or i == len(names) - 1:
            n = insert(batch)
            total_new += n
            logger.info(f"Progress: {i+1}/{len(names)} | Batch: {len(batch)} | New: {n} | Total new: {total_new}")
            batch = []
        
        if (i + 1) % 50 == 0:
            time.sleep(1)
    
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM agents")
    logger.info(f"DONE: {total_new} new | DB: {cur.fetchone()[0]:,}")
    conn.close()

if __name__ == '__main__':
    main()
