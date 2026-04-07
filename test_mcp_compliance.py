#!/usr/bin/env python3
"""
Test MCP Compliance Classifier

Kör compliance-klassificering på befintliga MCP-servrar för att visa strategisk värde.
"""

import sys
import os
sys.path.insert(0, os.path.expanduser("~/agentindex"))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

import logging
from agentindex.agents.mcp_compliance import McpComplianceClassifier
from agentindex.spiders.mcp_spider import McpSpider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_test")

def test_mcp_compliance():
    """Test MCP compliance classification."""
    
    print("🔍 TESTING MCP COMPLIANCE CLASSIFIER")
    print("=" * 50)
    
    # First, run MCP spider to get fresh data
    logger.info("Running MCP spider to get latest data...")
    spider = McpSpider()
    crawl_stats = spider.crawl()
    
    print(f"📊 MCP Crawl Results:")
    print(f"   Found: {crawl_stats['found']} servers")
    print(f"   New: {crawl_stats['new']} servers")
    print(f"   Errors: {crawl_stats['errors']}")
    print()

    # Run compliance classification
    logger.info("Running compliance classification...")
    classifier = McpComplianceClassifier()
    comp_stats = classifier.classify_all_mcp(batch_size=20)
    
    print(f"🎯 COMPLIANCE CLASSIFICATION RESULTS:")
    print(f"   Processed: {comp_stats['processed']} MCP servers")
    print(f"   🚨 HIGH Risk: {comp_stats['high_risk']} servers")
    print(f"   ⚠️  MEDIUM Risk: {comp_stats['medium_risk']} servers")
    print(f"   ✅ LOW Risk: {comp_stats['low_risk']} servers")
    print(f"   ❌ Errors: {comp_stats['errors']}")
    print()

    # Show high-risk summary
    high_risk = classifier.get_high_risk_summary()
    
    if high_risk:
        print(f"🚨 HIGH-RISK MCP SERVERS ({len(high_risk)} found):")
        print("=" * 50)
        
        for i, agent in enumerate(high_risk[:10], 1):  # Show top 10
            print(f"{i}. {agent['name']}")
            print(f"   Description: {agent['description'][:100]}...")
            print(f"   ⭐ Stars: {agent['stars'] or 0}")
            print(f"   🏷️  Data Types: {', '.join(agent['data_types'])}")
            print(f"   📋 Regulations: {', '.join(agent['regulations'])}")
            print(f"   💡 Risk Reason: {agent['reasoning'][:150]}...")
            print(f"   🔗 URL: {agent['source_url']}")
            print()
            
        print("💰 BUSINESS OPPORTUNITY:")
        print(f"   • {len(high_risk)} MCP builders need compliance guidance")
        print(f"   • Financial data handlers: {sum(1 for a in high_risk if 'financial' in a['data_types'])}")
        print(f"   • Personal data processors: {sum(1 for a in high_risk if 'personal' in a['data_types'])}")
        print(f"   • Corporate data accessors: {sum(1 for a in high_risk if 'corporate' in a['data_types'])}")
        print()
        print("🎯 OUTREACH STRATEGY:")
        print("   • Target builders of high-risk MCP servers")
        print("   • Educational approach: 'Did you know your MCP server likely needs compliance review?'")
        print("   • Positioning: First platform to offer MCP compliance analysis")
        
    else:
        print("No high-risk MCP servers found yet. Run more crawls to find them.")

    return comp_stats

if __name__ == "__main__":
    test_mcp_compliance()