"""
Docker Hub Spider for AI Agents & Containers
Priority A source: 50,000+ potential AI containers
"""

import requests
import time
import logging
from datetime import datetime
import traceback
from agentindex.db.models import Agent, get_session
from agentindex.db.models import safe_commit
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s [docker] %(message)s")
logger = logging.getLogger("docker_hub_crawler")

class DockerHubCrawler:
    """Crawl Docker Hub for AI-related containers."""
    
    def __init__(self):
        self.base_url = "https://registry.hub.docker.com/v2"
        self.session = get_session()
        self.headers = {
            'User-Agent': 'AgentIndex/1.0 (https://agentcrawl.dev)'
        }
        
    def search_containers(self, query: str, page_size: int = 100) -> list:
        """Search Docker Hub for containers matching query."""
        containers = []
        page = 1
        
        while True:
            url = f"{self.base_url}/search/repositories/"
            params = {
                'query': query,  # Docker Hub API uses 'query' not 'q'
                'page': page,
                'page_size': page_size
            }
            
            try:
                response = requests.get(url, params=params, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                results = data.get('results', [])
                if not results:
                    break
                    
                containers.extend(results)
                logger.info(f"Page {page}: {len(results)} containers for '{query}'")
                
                if len(results) < page_size:  # Last page
                    break
                    
                page += 1
                time.sleep(1)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Error searching Docker Hub page {page}: {e}")
                break
                
        return containers
    
    def container_to_agent(self, container: dict) -> dict:
        """Convert Docker Hub container to Agent format."""
        repo_name = container.get('repo_name', '')
        # Docker Hub API doesn't separate user/name in search results
        full_name = repo_name
        
        # Extract user and name from repo_name
        if '/' in repo_name:
            user, name = repo_name.split('/', 1)
        else:
            user = 'library'  # Official images
            name = repo_name
        
        return {
            'source': 'docker_hub',
            'source_url': f"https://hub.docker.com/r/{full_name}" if user != 'library' else f"https://hub.docker.com/_/{name}",
            'source_id': full_name,
            'name': name,
            'description': container.get('short_description', '') or '',
            'author': user if user != 'library' else 'Docker Official',
            'stars': container.get('star_count', 0),
            'downloads': container.get('pull_count', 0),
            'last_source_update': None,  # Not available in search API
            'tags': self._extract_tags(container),
            'protocols': ['docker'],
            'invocation': {
                'type': 'docker',
                'install': f'docker pull {full_name}',
                'run': f'docker run {full_name}',
                'protocol': 'docker'
            },
            'pricing': {'model': 'free'},
            'raw_metadata': container,
            'first_indexed': datetime.utcnow(),
            'last_crawled': datetime.utcnow(),
            'crawl_status': 'indexed',
            # EU compliance defaults (will be analyzed later by compliance scanner)
            'eu_risk_class': None,
            'eu_risk_confidence': None,
            'compliance_score': None,
            'last_compliance_check': None
        }
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse Docker Hub date string."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return None
            
    def _extract_tags(self, container: dict) -> list:
        """Extract tags from container metadata."""
        tags = []
        description = (container.get('short_description', '') + ' ' + 
                      container.get('repo_name', '')).lower()
        
        # Common AI/agent terms
        ai_terms = ['ai', 'agent', 'llm', 'ml', 'neural', 'model', 'inference', 
                   'chatbot', 'assistant', 'automation', 'langchain', 'ollama']
        
        for term in ai_terms:
            if term in description:
                tags.append(term)
                
        return tags[:5]  # Limit tags
    
    def crawl_ai_containers(self):
        """Main crawling method for AI containers."""
        queries = [
            'ai agent',
            'llm',
            'machine learning',
            'chatbot', 
            'ai assistant',
            'ollama',
            'langchain',
            'inference server',
            'model serving',
            'autonomous agent'
        ]
        
        total_new = 0
        total_updated = 0
        
        for query in queries:
            logger.info(f"🔍 Searching Docker Hub for: {query}")
            containers = self.search_containers(query)
            
            new_count = 0
            updated_count = 0
            
            for container in containers:
                try:
                    agent_data = self.container_to_agent(container)
                    
                    # Check if exists
                    existing = self.session.query(Agent).filter_by(
                        source='docker_hub',
                        source_id=agent_data['source_id']
                    ).first()
                    
                    if existing:
                        # Update existing
                        existing.last_crawled = datetime.now()
                        existing.stars = agent_data['stars']
                        existing.downloads = agent_data['downloads']
                        existing.last_source_update = agent_data['last_source_update']
                        updated_count += 1
                    else:
                        # Create new agent
                        agent = Agent(**agent_data)
                        agent.id = uuid.uuid4()
                        self.session.add(agent)
                        new_count += 1
                    
                    # ROBUST: Individual commit per agent
                    try:
                        self.session.commit()
                    except Exception as commit_error:
                        logger.error(f"Commit error for container {container.get('repo_name', 'unknown')}: {commit_error}")
                        self.session.rollback()
                        # Get fresh session like fixed parser
                        self.session.close()
                        self.session = get_session()
                        continue
                        
                    if (new_count + updated_count) % 100 == 0:
                        logger.info(f"Progress: {new_count} new, {updated_count} updated")
                        
                except Exception as e:
                    logger.error(f"Error processing container {container.get('repo_name', 'unknown')}: {e}")
                    # Continue to next container - don't crash whole crawl
                    continue
            
            safe_commit(self.session)
            logger.info(f"Query '{query}' complete: {new_count} new, {updated_count} updated")
            total_new += new_count
            total_updated += updated_count
        
        logger.info(f"🐳 Docker Hub crawl complete: {total_new} new agents, {total_updated} updated")
        return {'new': total_new, 'updated': total_updated}

if __name__ == "__main__":
    crawler = DockerHubCrawler()
    result = crawler.crawl_ai_containers()
    print(f"Docker Hub crawl result: {result}")