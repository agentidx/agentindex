#!/usr/bin/env python3
"""
Crawl MCP server registries from multiple sources:
- awesome-mcp-servers GitHub repos
- mcp.so directory
- smithery.ai
- mcpserverfinder.com
- glama.ai/mcp/servers
"""

import requests
import time
import logging
import uuid
import psycopg2
import psycopg2.extras
import json
import re
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [mcp-crawl] %(message)s",
    handlers=[
        logging.FileHandler(f'mcp_crawl_{datetime.now().strftime("%Y%m%d_%H%M")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("mcp_crawl")

DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')
HEADERS = {'User-Agent': 'AgentIndex/1.0', 'Accept': 'application/json'}


def crawl_awesome_mcp_servers():
    """Crawl punkpeye/awesome-mcp-servers and wong2/awesome-mcp-servers from GitHub."""
    agents = []
    repos = [
        'punkpeye/awesome-mcp-servers',
        'wong2/awesome-mcp-servers',
        'appcypher/awesome-mcp-servers',
    ]
    
    for repo in repos:
        try:
            url = f'https://raw.githubusercontent.com/{repo}/main/README.md'
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                url = f'https://raw.githubusercontent.com/{repo}/master/README.md'
                resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Could not fetch {repo}")
                continue
            
            content = resp.text
            # Extract GitHub links
            github_links = re.findall(r'https://github\.com/[\w\-\.]+/[\w\-\.]+', content)
            # Extract npm links
            npm_links = re.findall(r'https://www\.npmjs\.com/package/[\w\-\@\/\.]+', content)
            
            for link in set(github_links):
                # Skip the awesome list itself and non-MCP repos
                if '/awesome-mcp' in link:
                    continue
                parts = link.rstrip('/').split('/')
                if len(parts) >= 5:
                    author = parts[3]
                    name = parts[4]
                    agents.append({
                        'source_url': link,
                        'source_id': f'{author}/{name}',
                        'name': name,
                        'author': author,
                        'description': f'MCP server from {repo}',
                        'tags': ['mcp', 'mcp-server'],
                    })
            
            logger.info(f"Found {len(github_links)} GitHub links in {repo}")
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error crawling {repo}: {e}")
    
    return agents


def crawl_github_mcp_search():
    """Search GitHub for MCP servers."""
    agents = []
    queries = [
        'mcp-server', 'model-context-protocol', 'mcp server',
        'mcp-server-', 'mcp tool server', 'claude mcp',
        'mcp integration', 'mcp plugin', 'mcp connector',
    ]
    
    for query in queries:
        try:
            resp = requests.get(
                'https://api.github.com/search/repositories',
                params={'q': query, 'sort': 'stars', 'per_page': 100},
                headers={**HEADERS, 'Accept': 'application/vnd.github.v3+json'},
                timeout=15
            )
            
            if resp.status_code == 403:
                logger.warning("GitHub rate limited. Sleeping 60s...")
                time.sleep(60)
                continue
            
            if resp.status_code != 200:
                continue
            
            data = resp.json()
            for repo in data.get('items', []):
                agents.append({
                    'source_url': repo['html_url'],
                    'source_id': repo['full_name'],
                    'name': repo['name'],
                    'author': repo['owner']['login'],
                    'description': (repo.get('description') or '')[:2000],
                    'tags': ['mcp', 'mcp-server', 'github'] + (repo.get('topics') or [])[:5],
                    'stars': repo.get('stargazers_count', 0),
                })
            
            logger.info(f"GitHub search '{query}': {len(data.get('items', []))} results")
            time.sleep(2)  # GitHub rate limit
            
        except Exception as e:
            logger.error(f"GitHub search error for '{query}': {e}")
    
    return agents


def crawl_npm_mcp():
    """Search npm for MCP packages."""
    agents = []
    queries = ['mcp-server', 'model-context-protocol', '@mcp/', 'mcp-tool']
    
    for query in queries:
        try:
            resp = requests.get(
                'https://registry.npmjs.org/-/v1/search',
                params={'text': query, 'size': 250},
                headers=HEADERS,
                timeout=15
            )
            
            if resp.status_code != 200:
                continue
            
            data = resp.json()
            for pkg in data.get('objects', []):
                p = pkg.get('package', {})
                name = p.get('name', '')
                agents.append({
                    'source_url': f"https://www.npmjs.com/package/{name}",
                    'source_id': name,
                    'name': name,
                    'author': (p.get('publisher', {}) or {}).get('username', 'unknown'),
                    'description': (p.get('description') or '')[:2000],
                    'tags': ['mcp', 'npm'] + (p.get('keywords') or [])[:5],
                })
            
            logger.info(f"npm search '{query}': {len(data.get('objects', []))} results")
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"npm search error: {e}")
    
    return agents


def insert_agents(agents):
    """Insert agents into database."""
    if not agents:
        return 0
    
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    values = []
    seen_urls = set()
    
    for a in agents:
        url = a['source_url']
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        values.append((
            str(uuid.uuid4()),
            'mcp_registry',
            url,
            a.get('source_id', url),
            a.get('name', '')[:500],
            a.get('description', '')[:2000],
            a.get('author', 'unknown')[:255],
            a.get('stars', 0),
            0,
            a.get('tags', [])[:10],
            ['mcp'],
            json.dumps(a),
            datetime.now(),
            datetime.now(),
            True,
            'indexed'
        ))
    
    total_new = 0
    if values:
        try:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO agents (
                    id, source, source_url, source_id, name, description, author,
                    stars, downloads, tags, protocols, raw_metadata,
                    first_indexed, last_crawled, is_active, crawl_status
                ) VALUES %s ON CONFLICT (source_url) DO NOTHING""",
                values,
                page_size=500
            )
            conn.commit()
            total_new = cur.rowcount
        except Exception as e:
            logger.error(f"Insert error: {e}")
            conn.rollback()
    
    conn.close()
    return total_new


def main():
    total = 0
    
    logger.info("=== Crawling awesome-mcp-servers repos ===")
    awesome = crawl_awesome_mcp_servers()
    n = insert_agents(awesome)
    total += n
    logger.info(f"Awesome lists: {len(awesome)} found, {n} new")
    
    logger.info("=== Crawling GitHub MCP search ===")
    github = crawl_github_mcp_search()
    n = insert_agents(github)
    total += n
    logger.info(f"GitHub search: {len(github)} found, {n} new")
    
    logger.info("=== Crawling npm MCP packages ===")
    npm = crawl_npm_mcp()
    n = insert_agents(npm)
    total += n
    logger.info(f"npm: {len(npm)} found, {n} new")
    
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM agents")
    db_total = cur.fetchone()[0]
    conn.close()
    
    logger.info(f"\nMCP CRAWL COMPLETE: {total} new agents | DB total: {db_total:,}")


if __name__ == '__main__':
    main()
