#!/usr/bin/env python3
"""
Hourly Monitoring for Expansion Crawlers

Monitors expansion progress and reports totals.
To be run every hour during the expansion period.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agentindex.db.models import Agent, get_session
from sqlalchemy import func, select, text

def get_expansion_report():
    """Generate comprehensive expansion report."""
    
    session = get_session()
    
    # Baseline and current totals
    BASELINE = 43865  # Starting point
    current_total = session.execute(select(func.count(Agent.id))).scalar()
    total_added = current_total - BASELINE
    
    print("🚀 AGENTINDEX EXPANSION - HOURLY REPORT")
    print("=" * 60)
    print(f"Report time: {datetime.now().isoformat()}")
    print(f"Baseline: {BASELINE:,} agents")
    print(f"Current: {current_total:,} agents")
    print(f"Added: +{total_added:,} agents ({(total_added/BASELINE)*100:.1f}% growth)")
    
    # By source breakdown
    by_source = session.execute(
        select(Agent.source, func.count(Agent.id)).
        group_by(Agent.source).
        order_by(func.count(Agent.id).desc())
    ).fetchall()
    
    print(f"\n📊 BY SOURCE:")
    for source, count in by_source:
        percentage = (count / current_total) * 100
        print(f"   {source}: {count:,} ({percentage:.1f}%)")
    
    # Expansion-specific sources
    github_total = next((count for source, count in by_source if source == 'github'), 0)
    hf_model_total = next((count for source, count in by_source if source == 'huggingface_model'), 0)
    hf_space_total = next((count for source, count in by_source if source == 'huggingface_space'), 0)
    hf_dataset_total = next((count for source, count in by_source if source == 'huggingface_dataset'), 0)
    
    # Calculate expansion multipliers
    github_baseline = 35790
    hf_baseline = 1519
    
    github_growth = github_total / github_baseline if github_baseline > 0 else 1
    hf_growth = (hf_model_total + hf_space_total + hf_dataset_total) / hf_baseline if hf_baseline > 0 else 1
    
    print(f"\n🎯 EXPANSION ANALYSIS:")
    print(f"   GitHub: {github_total:,} (was {github_baseline:,}) → {github_growth:.2f}x")
    print(f"   HuggingFace: {hf_model_total + hf_space_total + hf_dataset_total:,} (was {hf_baseline:,}) → {hf_growth:.2f}x")
    print(f"   Overall: {current_total:,} (was {BASELINE:,}) → {(current_total/BASELINE):.2f}x")
    
    # Recent activity (last hour)
    hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_agents = session.execute(
        select(Agent.source, func.count(Agent.id)).
        where(Agent.first_indexed >= hour_ago).
        group_by(Agent.source).
        order_by(func.count(Agent.id).desc())
    ).fetchall()
    
    print(f"\n⏱️ LAST HOUR ACTIVITY:")
    recent_total = 0
    for source, count in recent_agents:
        recent_total += count
        print(f"   {source}: +{count:,}")
    
    if recent_total > 0:
        print(f"   TOTAL: +{recent_total:,} agents/hour")
        print(f"   Rate: {recent_total/60:.1f} agents/minute")
    
    # Compliance classification status
    pending_classification = session.execute(
        select(func.count(Agent.id)).
        where(Agent.crawl_status == 'indexed')
    ).scalar()
    
    classified_agents = session.execute(
        select(func.count(Agent.id)).
        where(Agent.crawl_status == 'classified')
    ).scalar()
    
    print(f"\n🔍 COMPLIANCE CLASSIFICATION:")
    print(f"   Pending: {pending_classification:,} agents")
    print(f"   Classified: {classified_agents:,} agents")
    
    if current_total > 0:
        classification_progress = (classified_agents / current_total) * 100
        print(f"   Progress: {classification_progress:.1f}% classified")
    
    # Crawler status
    print(f"\n🕷️ CRAWLER STATUS:")
    
    # Check if GitHub expansion is still running
    import subprocess
    try:
        github_proc = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        github_running = 'run_github_expansion.py' in github_proc.stdout
        print(f"   GitHub expansion: {'🔄 RUNNING' if github_running else '✅ COMPLETED'}")
    except:
        print(f"   GitHub expansion: ❓ UNKNOWN")
    
    # Parser status
    try:
        parser_proc = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        parser_running = 'run_parser_loop.py' in parser_proc.stdout
        print(f"   Compliance parser: {'🔄 RUNNING' if parser_running else '❌ STOPPED'}")
    except:
        print(f"   Compliance parser: ❓ UNKNOWN")
    
    # Projections
    print(f"\n🎯 PROJECTIONS TO 500K:")
    remaining = 500000 - current_total
    
    if recent_total > 0:
        hours_to_500k = remaining / recent_total
        eta = datetime.now() + timedelta(hours=hours_to_500k)
        print(f"   Remaining: {remaining:,} agents")
        print(f"   At current rate: {hours_to_500k:.1f} hours")
        print(f"   ETA: {eta.strftime('%Y-%m-%d %H:%M')}")
    else:
        print(f"   Remaining: {remaining:,} agents")
        print(f"   ETA: Calculating...")
    
    session.close()
    
    return {
        'baseline': BASELINE,
        'current': current_total,
        'added': total_added,
        'github_total': github_total,
        'hf_total': hf_model_total + hf_space_total + hf_dataset_total,
        'pending_classification': pending_classification,
        'recent_hour': recent_total,
        'remaining_to_500k': remaining
    }

if __name__ == "__main__":
    report = get_expansion_report()
    
    print(f"\n🏆 SUMMARY:")
    print(f"   Baseline → Current: {report['baseline']:,} → {report['current']:,}")
    print(f"   Growth: +{report['added']:,} agents")
    print(f"   Last hour: +{report['recent_hour']:,} agents")
    print(f"   To 500K: {report['remaining_to_500k']:,} remaining")