#!/usr/bin/env python3
"""
Remaining GitHub Expansion - 117 Queries
Continue where we left off: queries 21-137 + all 32 topics
"""

import os
import sys
import time
from datetime import datetime

# Add project path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agentindex.spiders.github_spider_expanded import GitHubExpandedSpider, ALL_SEARCH_QUERIES, AI_TOPICS

def run_remaining_expansion():
    """Run remaining GitHub expansion: queries 21-137 + topics."""
    
    print("🚀 REMAINING GITHUB EXPANSION - 117 QUERIES")
    print("=" * 60)
    print(f"Start time: {datetime.now().isoformat()}")
    
    spider = GitHubExpandedSpider()
    
    # Skip first 20 queries (already done)
    remaining_queries = ALL_SEARCH_QUERIES[20:]  # Queries 21-137
    all_topics = AI_TOPICS  # All 32 topics
    
    print(f"🎯 SCOPE:")
    print(f"   Remaining search queries: {len(remaining_queries)}")
    print(f"   GitHub topics: {len(all_topics)}")
    print(f"   Total operations: {len(remaining_queries) + len(all_topics)}")
    print(f"   Expected new agents: 30,000-50,000")
    
    total_stats = {
        "repos_found": 0,
        "repos_new": 0,
        "queries_run": 0,
        "topics_searched": 0,
        "errors": 0
    }
    
    # Phase 1: Remaining queries (21-137)
    print(f"\n🔍 Phase 1: Remaining search queries ({len(remaining_queries)} terms)")
    
    for i, query in enumerate(remaining_queries, 21):  # Start from 21
        try:
            print(f"Query {i}/137: '{query}'")
            
            # Use smart query with rotation
            query_stats = spider._crawl_query_with_stars(
                query=query,
                max_results=200,  # Higher per query since we have time
                min_stars=3      # Lower threshold for more coverage
            )
            
            total_stats["queries_run"] += 1
            total_stats["repos_found"] += query_stats["found"]
            total_stats["repos_new"] += query_stats["new"]
            
            print(f"   ✅ Found: {query_stats['found']}, New: {query_stats['new']}")
            
            # Smart rate limiting with token rotation
            if i % 5 == 0:
                spider._check_rate_limit()
                print(f"   📊 Progress: {total_stats['repos_found']:,} total repos, {total_stats['repos_new']:,} new")
            
            time.sleep(3)  # Conservative spacing for search API
            
        except Exception as e:
            print(f"   ❌ Query failed: {e}")
            total_stats["errors"] += 1
            time.sleep(10)  # More backoff on errors
    
    # Phase 2: All GitHub Topics  
    print(f"\n🏷️ Phase 2: GitHub Topics ({len(all_topics)} topics)")
    
    for topic in all_topics:
        try:
            print(f"Topic: '{topic}'")
            
            topic_stats = spider._crawl_topic(topic, 150, 3)
            total_stats["topics_searched"] += 1
            total_stats["repos_found"] += topic_stats["found"]
            total_stats["repos_new"] += topic_stats["new"]
            
            print(f"   ✅ Found: {topic_stats['found']}, New: {topic_stats['new']}")
            time.sleep(5)  # Topics are more intensive
            
        except Exception as e:
            print(f"   ❌ Topic failed: {e}")
            continue
    
    print(f"\n🎯 REMAINING EXPANSION COMPLETED:")
    print(f"=" * 60)
    print(f"Search queries processed: {total_stats['queries_run']}/{len(remaining_queries)}")
    print(f"Topics processed: {total_stats['topics_searched']}/{len(all_topics)}")  
    print(f"Total repos discovered: {total_stats['repos_found']:,}")
    print(f"NEW AGENTS ADDED: {total_stats['repos_new']:,}")
    print(f"Errors: {total_stats['errors']}")
    
    if total_stats['repos_new'] > 20000:
        print(f"\n🏆 SUCCESS! Added {total_stats['repos_new']:,} GitHub agents")
        print(f"Combined with previous 20 queries: ~50K total GitHub expansion")
    else:
        print(f"\n📊 Added {total_stats['repos_new']:,} new agents")
    
    return total_stats

if __name__ == "__main__":
    result = run_remaining_expansion()