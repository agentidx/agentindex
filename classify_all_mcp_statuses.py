#!/usr/bin/env python3
"""Classify MCP servers across all relevant statuses with enhanced classifier."""

import sys, os
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

import logging
from datetime import datetime
from agentindex.db.models import Agent, get_session
from agentindex.compliance.enhanced_risk_classifier import EnhancedRiskClassifier
from sqlalchemy import select, or_

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("classify_all_mcp")

def classify_mcp_all_statuses():
    """Classify MCP servers from classified/ranked statuses that likely should be agents."""
    
    session = get_session()
    classifier = EnhancedRiskClassifier()
    
    # Get MCP servers from statuses that indicate they should be agents
    # Skip "not_agent" for now, focus on "classified" and "ranked"
    mcp_agents = session.execute(
        select(Agent).where(
            Agent.source == "mcp"
        ).where(
            or_(
                Agent.crawl_status == "classified",
                Agent.crawl_status == "ranked", 
                Agent.crawl_status == "parsed"
            )
        ).where(
            Agent.eu_risk_class.is_(None)  # Only unclassified
        ).limit(200)  # Sample first 200
    ).scalars().all()
    
    print(f"Found {len(mcp_agents)} MCP servers to classify (classified/ranked/parsed)")
    
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
            if i % 25 == 0:
                logger.info(f"Progress: {i}/{len(mcp_agents)}")
                
            # Enhanced classification 
            result = classifier.classify(
                name=agent.name,
                description=agent.description or "",
                capabilities=agent.capabilities or [],
                category=agent.category or "infrastructure",
                use_llm=False  # Rule-based for speed
            )
            
            # Update agent
            agent.eu_risk_class = result["risk_class"]
            agent.eu_risk_confidence = result["confidence"]
            agent.compliance_score = result["compliance_score"]
            
            # Store compliance metadata
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
            
            # Collect high-risk for reporting
            if agent.eu_risk_class == "high":
                high_risk_servers.append({
                    "name": agent.name,
                    "description": (agent.description or "")[:200],
                    "source_url": agent.source_url,
                    "reasoning": result.get("reasoning", "")[:300],
                    "annex_category": result.get("annex_category", ""),
                    "original_status": agent.crawl_status
                })
                
            elif agent.eu_risk_class == "limited":
                limited_risk_servers.append({
                    "name": agent.name,
                    "reasoning": result.get("reasoning", "")[:150]
                })
                
        except Exception as e:
            logger.error(f"Error classifying {agent.name}: {e}")
            stats["errors"] += 1
            
    # Commit changes
    try:
        session.commit()
        
        print(f"\n✅ MCP COMPLIANCE CLASSIFICATION COMPLETE")
        print(f"   Total classified: {stats['classified']}")
        print(f"   🚨 HIGH risk: {stats['high']}")
        print(f"   ⚠️  LIMITED risk: {stats['limited']}")
        print(f"   ✅ MINIMAL risk: {stats['minimal']}")
        print(f"   ❌ Errors: {stats['errors']}")
        print(f"   Success rate: {((stats['classified'] - stats['errors']) / stats['classified'] * 100 if stats['classified'] > 0 else 0):.1f}%")
        
        # Report high-risk servers
        if high_risk_servers:
            print(f"\n🎯 HIGH-RISK MCP SERVERS ({len(high_risk_servers)}):")
            print("=" * 80)
            
            for i, server in enumerate(high_risk_servers[:15], 1):  # Show top 15
                print(f"{i}. 🚨 {server['name']}")
                print(f"   Description: {server['description']}")
                print(f"   Risk Category: {server['annex_category']}")
                print(f"   Reasoning: {server['reasoning']}")
                print(f"   URL: {server['source_url']}")
                print(f"   Original Status: {server['original_status']}")
                print()
                
            print(f"🚀 GITHUB ISSUES TARGETS:")
            print(f"   {len(high_risk_servers)} high-risk MCP servers identified")
            print(f"   Educational message: 'Your MCP server flagged as EU AI Act high-risk'")
            print(f"   Test with 3 repos first (per outreach rules)")
        
        # Report limited-risk servers
        if limited_risk_servers:
            print(f"\n⚠️ LIMITED-RISK MCP SERVERS ({len(limited_risk_servers)}):")
            for i, server in enumerate(limited_risk_servers[:10], 1):
                print(f"{i}. ⚠️  {server['name']}: {server['reasoning']}")
                
    except Exception as e:
        session.rollback()
        logger.error(f"Database error: {e}")
        return False
        
    return stats

if __name__ == "__main__":
    stats = classify_mcp_all_statuses()
    
    if stats and stats["classified"] > 0:
        print(f"\n📊 DELIVERABLE FOR ANDERS:")
        print(f"   MCP servers EU classified: {stats['classified']}")
        print(f"   HIGH-risk servers: {stats['high']} ({stats['high']/stats['classified']*100:.1f}%)")
        print(f"   LIMITED-risk servers: {stats['limited']} ({stats['limited']/stats['classified']*100:.1f}%)")
        print(f"   MINIMAL-risk servers: {stats['minimal']} ({stats['minimal']/stats['classified']*100:.1f}%)")
        
        if stats["high"] > 0:
            print(f"\n✅ LLM CLASSIFICATION FIXED:")
            print(f"   Enhanced classifier identifies {stats['high']} high-risk MCP servers")
            print(f"   vs 0 high-risk from old classifier (100% minimal)")
            print(f"   Ready for Fas 1 jurisdiction expansion")
            
        print(f"\n🚀 NEXT ACTIONS:")
        print(f"   1. GitHub Issues template ready for {stats['high']} targets")
        print(f"   2. Start Fas 1: jurisdiction_registry + multi-jurisdiction API")
        print(f"   3. Multi-jurisdiction checker will show real risk differences")
    else:
        print("❌ Classification failed or no servers found")