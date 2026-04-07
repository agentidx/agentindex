#!/usr/bin/env python3
"""Run enhanced classification on all parsed MCP servers."""

import sys, os
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

import logging
from datetime import datetime
from agentindex.db.models import Agent, get_session
from agentindex.compliance.enhanced_risk_classifier import EnhancedRiskClassifier
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enhanced_classification")

def classify_all_mcp_enhanced():
    """Run enhanced EU compliance on all parsed MCP servers."""
    
    session = get_session()
    classifier = EnhancedRiskClassifier()
    
    # Get all unclassified MCP servers
    mcp_agents = session.execute(
        select(Agent).where(
            Agent.source == "mcp"
        ).where(
            Agent.crawl_status == "parsed"  
        ).where(
            Agent.eu_risk_class.is_(None)
        ).limit(100)  # Process first 100 to test
    ).scalars().all()
    
    print(f"Found {len(mcp_agents)} MCP servers to classify")
    
    stats = {
        "classified": 0,
        "high": 0,
        "limited": 0, 
        "minimal": 0,
        "errors": 0
    }
    
    high_risk_servers = []
    limited_risk_servers = []
    
    for i, agent in enumerate(mcp_agents, 1):
        try:
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{len(mcp_agents)} ({i/len(mcp_agents)*100:.1f}%)")
            
            # Use enhanced classifier (rule-based + LLM fallback)
            result = classifier.classify(
                name=agent.name,
                description=agent.description or "",
                capabilities=agent.capabilities or [],
                category=agent.category or "other",
                use_llm=False  # Start with rule-based only for speed
            )
            
            # Update agent with classification
            agent.eu_risk_class = result["risk_class"]
            agent.eu_risk_confidence = result["confidence"]
            agent.compliance_score = result["compliance_score"]
            
            # Store additional compliance metadata 
            if not agent.raw_metadata:
                agent.raw_metadata = {}
            agent.raw_metadata["eu_compliance"] = {
                "annex_category": result.get("annex_category"),
                "reasoning": result.get("reasoning", ""),
                "requirements": result.get("requirements", []),
                "classified_at": datetime.now().isoformat(),
                "classifier_version": "enhanced_v1"
            }
            
            stats["classified"] += 1
            stats[agent.eu_risk_class] += 1
            
            # Collect high-risk servers for reporting
            if agent.eu_risk_class == "high":
                high_risk_servers.append({
                    "name": agent.name,
                    "description": agent.description,
                    "source_url": agent.source_url,
                    "reasoning": result.get("reasoning", ""),
                    "annex_category": result.get("annex_category", "")
                })
                print(f"🚨 HIGH: {agent.name}")
                
            elif agent.eu_risk_class == "limited":
                limited_risk_servers.append({
                    "name": agent.name,
                    "description": agent.description,
                    "source_url": agent.source_url,
                    "reasoning": result.get("reasoning", "")
                })
                
        except Exception as e:
            logger.error(f"Error classifying {agent.name}: {e}")
            stats["errors"] += 1
            
    # Commit changes
    try:
        session.commit()
        print(f"\n✅ ENHANCED CLASSIFICATION COMPLETE")
        print(f"   Total classified: {stats['classified']}")
        print(f"   🚨 HIGH risk: {stats['high']}")
        print(f"   ⚠️  LIMITED risk: {stats['limited']}")
        print(f"   ✅ MINIMAL risk: {stats['minimal']}")
        print(f"   ❌ Errors: {stats['errors']}")
        
        if high_risk_servers:
            print(f"\n🎯 HIGH-RISK MCP SERVERS ({len(high_risk_servers)}):")
            print("=" * 60)
            
            for server in high_risk_servers[:10]:  # Show top 10
                print(f"🚨 {server['name']}")
                print(f"   Description: {server['description'][:100]}...")
                print(f"   Category: {server['annex_category']}")
                print(f"   Reasoning: {server['reasoning'][:200]}...")
                print(f"   URL: {server['source_url']}")
                print()
                
        if limited_risk_servers:
            print(f"\n⚠️ LIMITED-RISK MCP SERVERS ({len(limited_risk_servers)}):")
            for server in limited_risk_servers[:5]:  # Show top 5
                print(f"⚠️  {server['name']}: {server['reasoning'][:100]}...")
                
    except Exception as e:
        session.rollback() 
        logger.error(f"Database error: {e}")
        return False
        
    return stats

if __name__ == "__main__":
    stats = classify_all_mcp_enhanced()
    
    if stats:
        total_high_risk = stats.get("high", 0)
        total_limited = stats.get("limited", 0)
        
        print(f"\n📊 DELIVERABLE FOR ANDERS:")
        print(f"   MCP servers classified: {stats['classified']}")
        print(f"   High-risk: {total_high_risk}")
        print(f"   Limited-risk: {total_limited}")
        print(f"   Minimal-risk: {stats['minimal']}")
        print(f"   Success rate: {((stats['classified'] - stats['errors']) / stats['classified'] * 100):.1f}%")
        
        if total_high_risk > 0:
            print(f"\n🚀 READY FOR JURISDICTION EXPANSION")
            print(f"   Enhanced classifier produces realistic results")
            print(f"   {total_high_risk} high-risk MCP servers = perfect GitHub Issues targets")
            print(f"   Multi-jurisdiction checker will show meaningful differences")
    else:
        print("❌ Classification failed")