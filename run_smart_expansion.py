#!/usr/bin/env python3
"""
Smart GitHub Expansion - Rate Limit Aware

Strategy: 
- Search API: 30/hour per token = 120 total/hour
- Run 100 queries/hour (safe margin)
- Focus on HIGH-VALUE queries first
- Automatic scheduling across hours
"""

import os
import sys
import time
from datetime import datetime

# Add project path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agentindex.spiders.github_spider_expanded import GitHubExpandedSpider, ALL_SEARCH_QUERIES, AI_TOPICS

# PRIORITIZED QUERIES - Most likely to yield high-quality agents
HIGH_VALUE_QUERIES = [
    # Core agent types
    "ai-agent", "llm agent", "autonomous agent", "multi-agent", 
    "langchain agent", "crewai agent", "autogen agent",
    
    # MCP ecosystem (hot right now)
    "mcp-server", "mcp server", "model context protocol",
    
    # Popular frameworks/tools
    "rag system", "vector-db", "semantic search", "ai-tool",
    "openai tool", "claude tool", "gpt tool", "huggingface",
    
    # Business applications
    "ai chatbot", "conversational agent", "ai assistant", "code ai"
]

# MEDIUM VALUE - Good but less specific
MEDIUM_VALUE_QUERIES = [
    "fine-tuning", "prompt-engineering", "text generation", "code generation",
    "ml-model", "ai model", "inference-server", "model serving",
    "ai-pipeline", "ml pipeline", "mlops", "embeddings",
    "legal ai", "medical ai", "finance ai", "customer service ai"
]

def run_smart_expansion():
    """Run smart expansion with rate limit awareness."""
    
    print("🧠 SMART GitHub EXPANSION - Rate Limit Optimized")
    print("=" * 60)
    print(f"Start time: {datetime.now().isoformat()}")
    
    spider = GitHubExpandedSpider()
    
    # Check current rate limit status
    try:
        rate_limit = spider.github.get_rate_limit()
        search_remaining = rate_limit.search.remaining
        search_reset = rate_limit.search.reset
        
        print(f"🚦 RATE LIMIT STATUS:")
        print(f"   Search API: {search_remaining}/30 remaining")
        print(f"   Reset time: {search_reset}")
        
        if search_remaining < 5:
            wait_seconds = (search_reset - datetime.now()).total_seconds() + 60
            print(f"⏳ Low search quota, waiting {wait_seconds:.0f}s for reset...")
            time.sleep(wait_seconds)
            
    except Exception as e:
        print(f"❌ Rate limit check failed: {e}")
        return
    
    # Phase 1: HIGH-VALUE queries (prioritized)
    print(f"\n🎯 Phase 1: HIGH-VALUE queries ({len(HIGH_VALUE_QUERIES)} terms)")
    print(f"Target: 80% search quota for maximum impact")
    
    total_stats = {
        "repos_found": 0,
        "repos_new": 0, 
        "queries_run": 0,
        "errors": 0
    }
    
    max_high_value = min(len(HIGH_VALUE_QUERIES), 24)  # Leave margin for errors
    
    for i, query in enumerate(HIGH_VALUE_QUERIES[:max_high_value], 1):
        try:
            print(f"🔍 Query {i}/{max_high_value}: '{query}'")
            
            # Single query crawl with smart limits
            query_stats = spider._crawl_query_with_stars(
                query=query, 
                max_results=150,  # More per query since we do fewer
                min_stars=3       # Lower threshold for more coverage
            )
            
            total_stats["queries_run"] += 1
            total_stats["repos_found"] += query_stats["found"]
            total_stats["repos_new"] += query_stats["new"]
            
            print(f"   ✅ Found: {query_stats['found']}, New: {query_stats['new']}")
            
            # Smart rate limiting
            if i % 5 == 0:
                spider._check_rate_limit()
                print(f"   📊 Progress: {total_stats['repos_found']:,} total repos, {total_stats['repos_new']:,} new")
            
            time.sleep(3)  # Conservative spacing
            
        except Exception as e:
            print(f"   ❌ Query failed: {e}")
            total_stats["errors"] += 1
            time.sleep(5)  # More backoff on errors
    
    # Final rate limit check
    remaining_quota = 0
    try:
        rate_limit = spider.github.get_rate_limit()
        remaining_quota = rate_limit.search.remaining
        print(f"\n🚦 Remaining search quota: {remaining_quota}/30")
    except:
        pass
    
    # Phase 2: Topics if we have quota left
    if remaining_quota > 3:
        print(f"\n🏷️ Phase 2: GitHub Topics ({min(remaining_quota-1, len(AI_TOPICS))} topics)")
        
        for topic in AI_TOPICS[:remaining_quota-1]:
            try:
                topic_stats = spider._crawl_topic(topic, 100, 3)
                total_stats["repos_found"] += topic_stats["found"]
                total_stats["repos_new"] += topic_stats["new"]
                
                print(f"Topic '{topic}': {topic_stats['found']} repos, {topic_stats['new']} new")
                time.sleep(4)
                
            except Exception as e:
                print(f"Topic '{topic}' failed: {e}")
                break
    else:
        print(f"\n⏭️ Skipping topics - low quota ({remaining_quota})")
    
    print(f"\n🎯 SMART EXPANSION COMPLETED:")
    print(f"=" * 60)
    print(f"Queries processed: {total_stats['queries_run']}")
    print(f"Repos found: {total_stats['repos_found']:,}")
    print(f"New agents: {total_stats['repos_new']:,}")
    print(f"Errors: {total_stats['errors']}")
    
    if total_stats['repos_new'] > 0:
        print(f"\n📈 SUCCESS! Added {total_stats['repos_new']:,} new GitHub agents")
        print(f"Next phase: Schedule MEDIUM_VALUE_QUERIES for next hour")
    else:
        print(f"\n⚠️ No new agents added - check for issues")
    
    return total_stats

if __name__ == "__main__":
    result = run_smart_expansion()