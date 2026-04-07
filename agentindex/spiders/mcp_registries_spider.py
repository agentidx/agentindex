"""
MCP Registries Spider

Crawls MCP servers from external registries:
- Smithery.ai MCP registry
- Glama.ai MCP collection

Supplements our existing GitHub MCP crawler with curated registries.
"""

import logging
import asyncio
import aiohttp
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin
import json
from bs4 import BeautifulSoup

logger = logging.getLogger("agentindex.spiders.mcp_registries")

class MCPRegistriesSpider:
    """MCP registries crawler for Smithery.ai and Glama.ai."""
    
    def __init__(self):
        self.session = None
        self.rate_limit_delay = 1.0  # Be respectful
        
        # Registry configurations
        self.registries = {
            'smithery': {
                'base_url': 'https://smithery.ai',
                'api_url': 'https://smithery.ai/api/mcp',
                'web_url': 'https://smithery.ai/mcp',
                'method': 'api_first'  # Try API first, fallback to scraping
            },
            'glama': {
                'base_url': 'https://glama.ai',
                'web_url': 'https://glama.ai/mcp',
                'method': 'scraping'  # Web scraping approach
            }
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'AgentIndex-Crawler/1.0 (Educational Research)',
                'Accept': 'application/json, text/html, */*'
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_page(self, url: str, expect_json: bool = False) -> Optional[Dict]:
        """Fetch a page with rate limiting."""
        try:
            await asyncio.sleep(self.rate_limit_delay)
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch {url}: {response.status}")
                    return None
                
                if expect_json:
                    return await response.json()
                else:
                    text = await response.text()
                    return {'html': text, 'url': url}
                    
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    async def crawl_smithery_api(self) -> List[Dict]:
        """Try to crawl Smithery via API."""
        logger.info("Attempting Smithery API crawl...")
        
        api_endpoints = [
            'https://smithery.ai/api/mcp',
            'https://smithery.ai/api/v1/mcp',
            'https://api.smithery.ai/mcp'
        ]
        
        for endpoint in api_endpoints:
            data = await self.fetch_page(endpoint, expect_json=True)
            if data and isinstance(data, dict):
                # Process API response
                servers = data.get('servers', []) or data.get('data', []) or data.get('results', [])
                if servers:
                    logger.info(f"Smithery API: Found {len(servers)} MCP servers")
                    return self._process_smithery_api_data(servers)
        
        logger.info("Smithery API not accessible, falling back to web scraping")
        return []
    
    async def crawl_smithery_web(self) -> List[Dict]:
        """Crawl Smithery via web scraping."""
        logger.info("Crawling Smithery.ai web interface...")
        
        urls_to_try = [
            'https://smithery.ai/mcp',
            'https://smithery.ai/registry',
            'https://smithery.ai/servers'
        ]
        
        for url in urls_to_try:
            page_data = await self.fetch_page(url, expect_json=False)
            if page_data:
                servers = self._extract_smithery_servers(page_data['html'])
                if servers:
                    logger.info(f"Smithery web: Found {len(servers)} MCP servers")
                    return servers
        
        logger.warning("Could not extract MCP servers from Smithery.ai")
        return []
    
    async def crawl_glama_web(self) -> List[Dict]:
        """Crawl Glama.ai MCP collection."""
        logger.info("Crawling Glama.ai MCP collection...")
        
        urls_to_try = [
            'https://glama.ai/mcp',
            'https://glama.ai/blog/2024/11/25/model-context-protocol-servers-guide',
            'https://glama.ai/mcp-servers'
        ]
        
        for url in urls_to_try:
            page_data = await self.fetch_page(url, expect_json=False)
            if page_data:
                servers = self._extract_glama_servers(page_data['html'])
                if servers:
                    logger.info(f"Glama web: Found {len(servers)} MCP servers")
                    return servers
        
        logger.warning("Could not extract MCP servers from Glama.ai")
        return []
    
    def _process_smithery_api_data(self, servers_data: List) -> List[Dict]:
        """Process Smithery API response data."""
        servers = []
        
        for server in servers_data:
            if not isinstance(server, dict):
                continue
                
            # Extract server information
            name = server.get('name', '') or server.get('title', '')
            description = server.get('description', '') or server.get('summary', '')
            github_url = server.get('github', '') or server.get('repository', '')
            
            if not name:
                continue
            
            server_data = {
                'name': name,
                'description': description,
                'source': 'mcp_registry_smithery',
                'source_url': f"https://smithery.ai/mcp/{name.lower().replace(' ', '-')}",
                'github_url': github_url,
                'registry': 'smithery',
                'category': server.get('category', 'mcp_server'),
                'tags': server.get('tags', []),
                'author': server.get('author', ''),
                'version': server.get('version', ''),
                'install_command': server.get('install', ''),
                'raw_metadata': {
                    'smithery_data': server,
                    'from_api': True
                }
            }
            
            servers.append(server_data)
        
        return servers
    
    def _extract_smithery_servers(self, html_content: str) -> List[Dict]:
        """Extract MCP servers from Smithery HTML."""
        servers = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for server cards or listings
            server_cards = (
                soup.find_all('div', class_=lambda x: x and 'server' in x.lower()) +
                soup.find_all('div', class_=lambda x: x and 'mcp' in x.lower()) +
                soup.find_all('article') +
                soup.find_all('li', class_=lambda x: x and any(term in x.lower() for term in ['server', 'mcp', 'package']))
            )
            
            for card in server_cards:
                # Extract server name
                name_elem = (
                    card.find('h1') or card.find('h2') or card.find('h3') or 
                    card.find('h4') or card.find('h5') or card.find('h6') or
                    card.find(class_=lambda x: x and 'title' in x.lower()) or
                    card.find(class_=lambda x: x and 'name' in x.lower())
                )
                
                if not name_elem:
                    continue
                
                name = name_elem.get_text(strip=True)
                
                # Extract description
                desc_elem = (
                    card.find('p') or 
                    card.find(class_=lambda x: x and 'description' in x.lower()) or
                    card.find(class_=lambda x: x and 'summary' in x.lower())
                )
                description = desc_elem.get_text(strip=True) if desc_elem else ''
                
                # Extract GitHub link
                github_link = card.find('a', href=lambda x: x and 'github.com' in x)
                github_url = github_link['href'] if github_link else ''
                
                # Extract install command
                code_elem = card.find('code') or card.find('pre')
                install_command = code_elem.get_text(strip=True) if code_elem else ''
                
                if name and len(name) > 2:  # Basic validation
                    servers.append({
                        'name': name,
                        'description': description,
                        'source': 'mcp_registry_smithery',
                        'source_url': 'https://smithery.ai/mcp',
                        'github_url': github_url,
                        'registry': 'smithery',
                        'category': 'mcp_server',
                        'install_command': install_command,
                        'raw_metadata': {
                            'from_scraping': True,
                            'smithery': True
                        }
                    })
            
        except Exception as e:
            logger.error(f"Error parsing Smithery HTML: {e}")
        
        return servers
    
    def _extract_glama_servers(self, html_content: str) -> List[Dict]:
        """Extract MCP servers from Glama HTML."""
        servers = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for MCP server mentions in content
            # Glama typically has blog-style content with lists of MCP servers
            
            # Find tables or lists containing MCP servers
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')[1:]  # Skip header
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        name = cells[0].get_text(strip=True)
                        description = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                        
                        # Look for GitHub links in the row
                        github_link = row.find('a', href=lambda x: x and 'github.com' in x)
                        github_url = github_link['href'] if github_link else ''
                        
                        if name and 'mcp' in name.lower() or 'server' in name.lower():
                            servers.append({
                                'name': name,
                                'description': description,
                                'source': 'mcp_registry_glama',
                                'source_url': 'https://glama.ai/mcp',
                                'github_url': github_url,
                                'registry': 'glama',
                                'category': 'mcp_server',
                                'raw_metadata': {
                                    'from_scraping': True,
                                    'glama': True
                                }
                            })
            
            # Also look for list items mentioning MCP servers
            list_items = soup.find_all('li')
            for li in list_items:
                text = li.get_text()
                if 'mcp' in text.lower() and any(term in text.lower() for term in ['server', 'tool', 'agent']):
                    # Extract name (usually first part or in strong/bold tags)
                    strong_elem = li.find('strong') or li.find('b') or li.find('code')
                    name = strong_elem.get_text(strip=True) if strong_elem else text.split('.')[0].strip()
                    
                    # Look for GitHub link
                    github_link = li.find('a', href=lambda x: x and 'github.com' in x)
                    github_url = github_link['href'] if github_link else ''
                    
                    if len(name) > 2 and len(name) < 100:  # Reasonable name length
                        servers.append({
                            'name': name,
                            'description': text[:200],  # First 200 chars as description
                            'source': 'mcp_registry_glama',
                            'source_url': 'https://glama.ai/mcp',
                            'github_url': github_url,
                            'registry': 'glama',
                            'category': 'mcp_server',
                            'raw_metadata': {
                                'from_scraping': True,
                                'glama': True,
                                'full_text': text
                            }
                        })
            
        except Exception as e:
            logger.error(f"Error parsing Glama HTML: {e}")
        
        return servers
    
    def _deduplicate_servers(self, servers: List[Dict]) -> List[Dict]:
        """Remove duplicate servers based on name and GitHub URL."""
        seen = set()
        deduplicated = []
        
        for server in servers:
            # Create a key for deduplication
            name_key = server.get('name', '').lower().strip()
            github_key = server.get('github_url', '').lower().strip()
            
            # Use name and GitHub URL as unique identifier
            unique_key = f"{name_key}::{github_key}"
            
            if unique_key not in seen:
                seen.add(unique_key)
                deduplicated.append(server)
        
        return deduplicated
    
    async def crawl(self) -> Dict:
        """Main crawl method."""
        start_time = time.time()
        logger.info("Starting MCP registries crawl")
        
        async with self:
            all_servers = []
            
            # Crawl Smithery.ai
            logger.info("Crawling Smithery.ai...")
            smithery_api_servers = await self.crawl_smithery_api()
            if not smithery_api_servers:
                smithery_web_servers = await self.crawl_smithery_web()
                all_servers.extend(smithery_web_servers)
            else:
                all_servers.extend(smithery_api_servers)
            
            # Crawl Glama.ai
            logger.info("Crawling Glama.ai...")
            glama_servers = await self.crawl_glama_web()
            all_servers.extend(glama_servers)
            
            # Deduplicate
            unique_servers = self._deduplicate_servers(all_servers)
            
            # Add relevance scoring
            for server in unique_servers:
                server['relevance_score'] = self._calculate_relevance(server)
        
        end_time = time.time()
        duration = end_time - start_time
        
        stats = {
            'source': 'mcp_registries',
            'total_found': len(unique_servers),
            'by_registry': {
                'smithery': len([s for s in unique_servers if s.get('registry') == 'smithery']),
                'glama': len([s for s in unique_servers if s.get('registry') == 'glama'])
            },
            'duration_seconds': round(duration, 2),
            'servers': unique_servers
        }
        
        logger.info(f"MCP registries crawl completed: {len(unique_servers)} servers in {duration:.1f}s")
        
        return stats
    
    def _calculate_relevance(self, server: Dict) -> float:
        """Calculate relevance score for MCP server."""
        score = 2.0  # Base score for being in a curated registry
        
        # GitHub integration bonus
        if server.get('github_url'):
            score += 1.0
        
        # Description quality bonus
        description = server.get('description', '')
        if description and len(description) > 50:
            score += 0.5
        
        # Install command availability bonus
        if server.get('install_command'):
            score += 0.5
        
        # Registry reputation bonus
        if server.get('registry') == 'smithery':
            score += 0.5  # Smithery is more technical/developer focused
        
        return round(score, 2)

# Test function
async def test_mcp_registries_spider():
    """Test the MCP registries spider."""
    spider = MCPRegistriesSpider()
    result = await spider.crawl()
    
    print(f"Total servers found: {result['total_found']}")
    print(f"By registry: {result['by_registry']}")
    
    if result['servers']:
        print("\\nSample servers:")
        for server in result['servers'][:3]:
            print(f"  - {server['name']}: {server['description'][:100]}")

if __name__ == "__main__":
    asyncio.run(test_mcp_registries_spider())