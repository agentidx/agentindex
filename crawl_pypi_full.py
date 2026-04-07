#!/usr/bin/env python3
"""Full PyPI crawler - searches for AI/ML/agent packages"""
import requests, time, logging, uuid, psycopg2, psycopg2.extras, json, os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [pypi] %(message)s",
    handlers=[logging.FileHandler(f'pypi_full_{datetime.now().strftime("%Y%m%d_%H%M")}.log'), logging.StreamHandler()])
logger = logging.getLogger("pypi")
DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')
HEADERS = {'User-Agent': 'AgentIndex/1.0', 'Accept': 'application/json'}

SEARCH_TERMS = [
    'ai agent', 'ai assistant', 'llm', 'langchain', 'openai', 'anthropic', 'chatbot',
    'machine learning', 'deep learning', 'neural network', 'transformer', 'bert', 'gpt',
    'nlp', 'natural language', 'text generation', 'sentiment analysis', 'ner',
    'computer vision', 'image classification', 'object detection', 'face recognition',
    'speech recognition', 'text to speech', 'voice', 'whisper', 'tts',
    'reinforcement learning', 'stable diffusion', 'diffusion', 'generative ai',
    'embedding', 'vector', 'rag', 'retrieval augmented', 'semantic search',
    'pytorch', 'tensorflow', 'keras', 'scikit-learn', 'huggingface', 'transformers',
    'autogpt', 'autonomous agent', 'multi agent', 'crewai', 'autogen',
    'mcp server', 'model context protocol', 'tool calling', 'function calling',
    'prompt engineering', 'fine tuning', 'lora', 'qlora', 'quantization',
    'chatgpt', 'claude', 'gemini', 'mistral', 'llama', 'falcon', 'phi',
    'recommendation', 'anomaly detection', 'fraud detection', 'forecasting',
    'robotics', 'autonomous', 'self driving', 'drone',
    'medical ai', 'biomedical', 'drug discovery', 'clinical',
    'ai safety', 'alignment', 'guardrails', 'content moderation',
    'ocr', 'document ai', 'pdf extraction', 'table extraction',
    'knowledge graph', 'ontology', 'reasoning', 'planning',
    'data pipeline', 'mlops', 'model serving', 'inference',
    'ai api', 'ai sdk', 'ai toolkit', 'ai framework', 'ai platform',
    'copilot', 'code generation', 'code assistant',
    'image generation', 'text to image', 'video generation',
    'audio generation', 'music generation',
    'translation', 'summarization', 'question answering',
    'classification', 'clustering', 'regression', 'prediction',
    'chatbot framework', 'conversational ai', 'dialog system',
    'web scraping ai', 'data extraction', 'automation',
    'workflow automation', 'rpa', 'process automation',
    'ai compliance', 'ai governance', 'model monitoring',
]

def search_pypi(query, page=1):
    """Search PyPI using the simple search or XML-RPC"""
    results = []
    try:
        r = requests.get(f'https://pypi.org/search/', params={'q': query, 'page': page}, headers={**HEADERS, 'Accept': 'text/html'}, timeout=15)
        if r.status_code == 200:
            import re
            # Parse package names from search results HTML
            names = re.findall(r'<a class="package-snippet" href="/project/([^/]+)/">', r.text)
            for name in names:
                results.append(name)
        elif r.status_code == 429:
            logger.warning(f"Rate limited on search '{query}'")
            time.sleep(30)
    except Exception as e:
        logger.error(f"Search error '{query}': {e}")
    return results

def get_package_info(name):
    """Get package details from PyPI JSON API"""
    try:
        r = requests.get(f'https://pypi.org/pypi/{name}/json', headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            info = data.get('info', {})
            return {
                'source_url': info.get('project_url') or info.get('package_url') or f'https://pypi.org/project/{name}/',
                'source_id': name,
                'name': name,
                'description': (info.get('summary') or info.get('description', ''))[:2000],
                'author': info.get('author') or info.get('maintainer') or 'unknown',
                'tags': [k for k in (info.get('keywords') or '').split(',') if k.strip()][:10],
                'downloads': 0,
                'version': info.get('version', ''),
                'license': info.get('license', ''),
                'home_page': info.get('home_page', ''),
            }
    except Exception as e:
        logger.error(f"Info error '{name}': {e}")
    return None

def insert(agents):
    if not agents: return 0
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    seen = set()
    vals = []
    for a in agents:
        u = a['source_url']
        if u in seen: continue
        seen.add(u)
        vals.append((str(uuid.uuid4()), 'pypi_full', u, a.get('source_id', u), a.get('name', '')[:500],
            a.get('description', '')[:2000], a.get('author', 'unknown')[:255], 0, a.get('downloads', 0),
            a.get('tags', [])[:10], [], json.dumps(a), datetime.now(), datetime.now(), True, 'indexed'))
    n = 0
    if vals:
        try:
            psycopg2.extras.execute_values(cur,
                "INSERT INTO agents (id,source,source_url,source_id,name,description,author,stars,downloads,tags,protocols,raw_metadata,first_indexed,last_crawled,is_active,crawl_status) VALUES %s ON CONFLICT (source_url) DO NOTHING",
                vals, page_size=500)
            conn.commit()
            n = cur.rowcount
        except Exception as e:
            logger.error(f"Insert: {e}")
            conn.rollback()
    conn.close()
    return n

def main():
    total_new = 0
    all_packages = set()
    
    for i, term in enumerate(SEARCH_TERMS):
        for page in range(1, 6):  # 5 pages per term
            names = search_pypi(term, page)
            if not names:
                break
            all_packages.update(names)
            time.sleep(1)  # Be polite
        
        # Every 10 terms, fetch details and insert
        if (i + 1) % 10 == 0 or i == len(SEARCH_TERMS) - 1:
            agents = []
            for name in list(all_packages):
                info = get_package_info(name)
                if info:
                    agents.append(info)
                time.sleep(0.3)
            n = insert(agents)
            total_new += n
            logger.info(f"Terms {i+1}/{len(SEARCH_TERMS)} | Packages found: {len(all_packages)} | Batch new: {n} | Total new: {total_new}")
            all_packages.clear()
    
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM agents")
    logger.info(f"DONE: {total_new} new | DB: {cur.fetchone()[0]:,}")
    conn.close()

if __name__ == '__main__':
    main()
