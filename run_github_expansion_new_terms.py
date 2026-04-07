#!/usr/bin/env python3
"""
GitHub Agent Discovery - New Search Terms Expansion
Anders nya söktermer för att bredda GitHub agent-indexering
"""

import time
import logging
from agentindex.spiders.github_spider_expanded import GitHubSpiderExpanded
from github_token_rotation import GitHubTokenRotation

logging.basicConfig(level=logging.INFO, format="%(asctime)s [github-expansion] %(message)s")
logger = logging.getLogger("github_expansion")

def main():
    """Run new GitHub search terms expansion."""
    
    # Anders nya söktermer för PRIORITET 3
    new_search_terms = [
        # LLM & Function Calling
        "LLM tool use",
        "function calling agent", 
        "AI assistant framework",
        
        # Framework-specific
        "langchain agent",
        "autogen agent", 
        "crewai",
        
        # MCP Protocol
        "MCP server",
        "MCP client",
        
        # Workflow & Orchestration  
        "prompt chaining",
        "AI workflow automation",
        "LLM orchestration",
        
        # Language-specific frameworks
        "agent framework python",
        "agent framework typescript"
    ]
    
    logger.info(f"🔍 Starting GitHub expansion with {len(new_search_terms)} new search terms")
    
    # Initialize token rotation and spider
    token_rotation = GitHubTokenRotation()
    spider = GitHubSpiderExpanded()
    
    total_new = 0
    results_by_term = {}
    
    for i, term in enumerate(new_search_terms, 1):
        logger.info(f"📡 [{i}/{len(new_search_terms)}] Searching: '{term}'")
        
        try:
            # Get current token
            current_token = token_rotation.get_current_token()
            spider.github_token = current_token
            
            # Search for repositories
            term_results = spider.search_repositories(
                query=term,
                max_results=100  # Per term limit
            )
            
            new_agents = term_results.get('new', 0)
            total_new += new_agents
            results_by_term[term] = {
                'new': new_agents,
                'updated': term_results.get('updated', 0),
                'total': term_results.get('total', 0)
            }
            
            logger.info(f"✅ '{term}': {new_agents} new agents")
            
            # Rate limiting - wait between searches
            time.sleep(15)  # 15 seconds between terms
            
            # Rotate token every 3 searches (conservative rate limiting)
            if i % 3 == 0:
                token_rotation.rotate_token()
                logger.info("🔄 Token rotated")
                time.sleep(30)  # Extra pause after rotation
            
        except Exception as e:
            logger.error(f"❌ Error searching '{term}': {e}")
            results_by_term[term] = {'error': str(e)}
            time.sleep(30)  # Longer pause on error
            continue
    
    # Final report
    logger.info(f"🎯 GitHub expansion complete!")
    logger.info(f"📊 Total new agents: {total_new}")
    logger.info(f"📈 Results by search term:")
    
    for term, result in results_by_term.items():
        if 'error' in result:
            logger.info(f"  ❌ {term}: {result['error']}")
        else:
            logger.info(f"  ✅ {term}: {result['new']} new, {result['updated']} updated")
    
    return {
        'total_new': total_new,
        'by_term': results_by_term,
        'terms_searched': len(new_search_terms)
    }

if __name__ == "__main__":
    result = main()
    print(f"\n🚀 GitHub New Terms Results:")
    print(f"Total new agents: {result['total_new']}")
    print(f"Search terms completed: {result['terms_searched']}")