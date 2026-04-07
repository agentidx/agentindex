#!/usr/bin/env python3
"""
Run GitHub Expanded Crawler - Live Execution

Executes the massive GitHub expansion with full monitoring and reporting.
"""

import os
import sys
import time
from datetime import datetime

# Add project path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agentindex.spiders.github_spider_expanded import GitHubExpandedSpider
from agentindex.db.models import Agent, get_session
from sqlalchemy import func, select

def run_github_expansion():
    """Run GitHub expanded crawler with full monitoring."""
    
    print("🚀 GITHUB EXPANDED CRAWL - LIVE EXECUTION")
    print("=" * 60)
    print(f"Start time: {datetime.now().isoformat()}")
    
    # Get baseline
    session = get_session()
    baseline_count = session.execute(select(func.count(Agent.id))).scalar()
    github_baseline = session.execute(select(func.count(Agent.id)).where(Agent.source == 'github')).scalar()
    session.close()
    
    print(f"📊 BASELINE:")
    print(f"   Total agents: {baseline_count:,}")
    print(f"   GitHub agents: {github_baseline:,}")
    print(f"   Target: +50K-100K GitHub agents")
    
    # Initialize crawler
    spider = GitHubExpandedSpider()
    
    # Run expanded crawl with limited scope first (test run)
    print(f"\n🔄 Starting GitHub expansion...")
    print(f"   Queries: 137 search terms + 32 GitHub topics")
    print(f"   Quality filter: >5 stars")
    print(f"   Deduplication: Active")
    
    try:
        start_time = time.time()
        
        # Run with conservative limits for initial test
        result = spider.crawl_expanded(
            max_results_per_query=100,  # Conservative start
            min_stars=5
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Get new counts
        session = get_session()
        new_total_count = session.execute(select(func.count(Agent.id))).scalar()
        new_github_count = session.execute(select(func.count(Agent.id)).where(Agent.source == 'github')).scalar()
        session.close()
        
        # Calculate actual additions
        total_added = new_total_count - baseline_count
        github_added = new_github_count - github_baseline
        
        print(f"\n🎯 GITHUB EXPANSION RESULTS:")
        print(f"=" * 60)
        print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
        print(f"Queries processed: {result.get('queries_run', 0)}/{137}")
        print(f"Topics processed: {result.get('topics_searched', 0)}/{32}")
        print(f"")
        print(f"📊 AGENT COUNTS:")
        print(f"   Before: {baseline_count:,} total ({github_baseline:,} GitHub)")
        print(f"   After:  {new_total_count:,} total ({new_github_count:,} GitHub)")
        print(f"   Added:  +{total_added:,} total (+{github_added:,} GitHub)")
        print(f"")
        print(f"📈 PERFORMANCE:")
        print(f"   Repos found: {result.get('repos_found', 0):,}")
        print(f"   New repos: {result.get('repos_new', 0):,}")
        print(f"   Updated repos: {result.get('repos_updated', 0):,}")
        print(f"   Unique repos seen: {result.get('unique_repos', 0):,}")
        print(f"   Stars filtered: {result.get('repos_filtered_stars', 0):,}")
        print(f"   Rate: {result.get('repos_per_second', 0):.1f} repos/second")
        print(f"")
        print(f"❌ ERRORS:")
        print(f"   Error count: {result.get('errors', 0)}")
        
        if result.get('errors', 0) > 0:
            print(f"   Error rate: {(result['errors'] / result['queries_run'] * 100):.1f}%")
        
        # Success assessment
        success_rate = (result.get('repos_new', 0) / max(result.get('repos_found', 1), 1)) * 100
        print(f"")
        print(f"✅ SUCCESS METRICS:")
        print(f"   New agent rate: {success_rate:.1f}%")
        print(f"   Deduplication: {result.get('repos_found', 0) - result.get('repos_new', 0):,} duplicates avoided")
        
        # Projection
        if github_added > 0:
            queries_remaining = 137 - result.get('queries_run', 0)
            projected_total = github_added * (137 / max(result.get('queries_run', 1), 1))
            print(f"")
            print(f"🎯 PROJECTION:")
            print(f"   Queries remaining: {queries_remaining}")
            print(f"   Projected total GitHub agents: {github_baseline + int(projected_total):,}")
            print(f"   Projected addition: +{int(projected_total):,} agents")
        
        return {
            'success': True,
            'baseline': baseline_count,
            'new_total': new_total_count,
            'agents_added': total_added,
            'github_added': github_added,
            'duration': duration,
            'result': result
        }
        
    except Exception as e:
        print(f"\n❌ GITHUB EXPANSION ERROR:")
        print(f"   Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'success': False,
            'error': str(e),
            'baseline': baseline_count
        }

if __name__ == "__main__":
    result = run_github_expansion()
    
    if result['success']:
        print(f"\n🏆 GITHUB EXPANSION COMPLETED SUCCESSFULLY")
        print(f"Added {result['agents_added']:,} new agents in {result['duration']:.1f}s")
    else:
        print(f"\n💥 GITHUB EXPANSION FAILED")
        print(f"Error: {result['error']}")