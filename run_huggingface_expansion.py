#!/usr/bin/env python3
"""
Run HuggingFace Expanded Crawler - Live Execution

Executes the massive HuggingFace expansion with full monitoring and reporting.
"""

import os
import sys
import time
from datetime import datetime

# Add project path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agentindex.spiders.huggingface_spider_expanded import HuggingFaceExpandedSpider
from agentindex.db.models import Agent, get_session
from sqlalchemy import func, select

def run_huggingface_expansion():
    """Run HuggingFace expanded crawler with full monitoring."""
    
    print("🌌 HUGGINGFACE EXPANDED CRAWL - LIVE EXECUTION")
    print("=" * 60)
    print(f"Start time: {datetime.now().isoformat()}")
    
    # Get baseline
    session = get_session()
    baseline_count = session.execute(select(func.count(Agent.id))).scalar()
    hf_baseline = session.execute(select(func.count(Agent.id)).where(Agent.source.like('huggingface%'))).scalar()
    session.close()
    
    print(f"📊 BASELINE:")
    print(f"   Total agents: {baseline_count:,}")
    print(f"   HuggingFace agents: {hf_baseline:,}")
    print(f"   Target: +15K-30K HuggingFace agents")
    
    # Initialize crawler
    spider = HuggingFaceExpandedSpider()
    
    # Run expanded crawl
    print(f"\n🔄 Starting HuggingFace expansion...")
    print(f"   Model queries: 79 terms")
    print(f"   Space queries: 52 terms") 
    print(f"   Dataset queries: 17 terms")
    print(f"   Priority orgs: 26 organizations")
    print(f"   HF tasks: 15 task categories")
    
    try:
        start_time = time.time()
        
        # Run with conservative limits for initial test
        result = spider.crawl_expanded(max_results_per_query=50)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Get new counts
        session = get_session()
        new_total_count = session.execute(select(func.count(Agent.id))).scalar()
        new_hf_count = session.execute(select(func.count(Agent.id)).where(Agent.source.like('huggingface%'))).scalar()
        session.close()
        
        # Calculate actual additions
        total_added = new_total_count - baseline_count
        hf_added = new_hf_count - hf_baseline
        
        print(f"\n🎯 HUGGINGFACE EXPANSION RESULTS:")
        print(f"=" * 60)
        print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
        print(f"")
        print(f"📊 AGENT COUNTS:")
        print(f"   Before: {baseline_count:,} total ({hf_baseline:,} HuggingFace)")
        print(f"   After:  {new_total_count:,} total ({new_hf_count:,} HuggingFace)")
        print(f"   Added:  +{total_added:,} total (+{hf_added:,} HuggingFace)")
        print(f"")
        print(f"📈 PERFORMANCE:")
        print(f"   Models found: {result.get('models_found', 0):,} ({result.get('models_new', 0):,} new)")
        print(f"   Spaces found: {result.get('spaces_found', 0):,} ({result.get('spaces_new', 0):,} new)")
        print(f"   Datasets found: {result.get('datasets_found', 0):,} ({result.get('datasets_new', 0):,} new)")
        print(f"   Organizations crawled: {result.get('orgs_crawled', 0)}/10")
        print(f"   Tasks crawled: {result.get('tasks_crawled', 0)}/15")
        print(f"   Unique items: {result.get('unique_items', 0):,}")
        print(f"   Rate: {result.get('items_per_second', 0):.1f} items/second")
        print(f"")
        print(f"❌ ERRORS:")
        print(f"   Error count: {result.get('errors', 0)}")
        
        # Success assessment
        total_found = result.get('models_found', 0) + result.get('spaces_found', 0) + result.get('datasets_found', 0)
        total_new = result.get('models_new', 0) + result.get('spaces_new', 0) + result.get('datasets_new', 0)
        
        success_rate = (total_new / max(total_found, 1)) * 100
        print(f"")
        print(f"✅ SUCCESS METRICS:")
        print(f"   New item rate: {success_rate:.1f}%")
        print(f"   Deduplication: {total_found - total_new:,} duplicates avoided")
        
        # Expansion analysis
        expansion_multiplier = new_hf_count / max(hf_baseline, 1)
        print(f"   HuggingFace expansion: {expansion_multiplier:.1f}x")
        
        return {
            'success': True,
            'baseline': baseline_count,
            'new_total': new_total_count,
            'agents_added': total_added,
            'hf_added': hf_added,
            'duration': duration,
            'result': result
        }
        
    except Exception as e:
        print(f"\n❌ HUGGINGFACE EXPANSION ERROR:")
        print(f"   Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'success': False,
            'error': str(e),
            'baseline': baseline_count
        }

if __name__ == "__main__":
    result = run_huggingface_expansion()
    
    if result['success']:
        print(f"\n🏆 HUGGINGFACE EXPANSION COMPLETED SUCCESSFULLY")
        print(f"Added {result['agents_added']:,} new agents in {result['duration']:.1f}s")
    else:
        print(f"\n💥 HUGGINGFACE EXPANSION FAILED")
        print(f"Error: {result['error']}")