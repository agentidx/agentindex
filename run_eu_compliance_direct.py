#!/usr/bin/env python3
"""
Run EU compliance classification on MCP servers using DIRECT classifier.
Uses existing RiskClassifier (no API calls needed).
"""

import sys
import os
sys.path.insert(0, os.path.expanduser("~/agentindex"))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

import logging
from datetime import datetime
from agentindex.db.models import Agent, get_session
from agentindex.compliance.risk_classifier import RiskClassifier
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eu_compliance_direct")

def classify_mcp_agents():
    """Run EU compliance on parsed MCP servers using direct classifier."""
    
    session = get_session()
    classifier = RiskClassifier()
    
    # Find parsed MCP servers without EU classification
    mcp_agents = session.execute(
        select(Agent).where(
            Agent.source == "mcp"
        ).where(
            Agent.crawl_status == "parsed"  
        ).where(
            Agent.eu_risk_class.is_(None)  # No EU classification yet
        ).limit(50)  # Process first 50 with LLM
    ).scalars().all()
    
    print(f"Found {len(mcp_agents)} parsed MCP servers needing EU compliance")
    
    stats = {
        "classified": 0,
        "minimal": 0, 
        "limited": 0,
        "high": 0,
        "unacceptable": 0,
        "errors": 0
    }
    
    high_risk_agents = []
    
    for i, agent in enumerate(mcp_agents, 1):
        try:
            logger.info(f"Classifying {i}/{len(mcp_agents)}: {agent.name}")
            
            # Use LLM classifier for accurate MCP risk assessment
            result = classifier.classify(
                name=agent.name,
                description=agent.description or "",
                capabilities=agent.capabilities or [],
                category=agent.category or "other", 
                source_url=agent.source_url,
                use_llm=True  # LLM needed for MCP servers - keywords miss data handling
            )
            
            # Update agent with classification results
            agent.eu_risk_class = result["risk_class"]
            agent.eu_risk_confidence = result["confidence"] 
            agent.compliance_score = result["compliance_score"]
            
            # Store additional compliance metadata
            if not agent.raw_metadata:
                agent.raw_metadata = {}
            agent.raw_metadata["eu_compliance"] = {
                "annex_category": result.get("annex_category"),
                "annex_subcategory": result.get("annex_subcategory"),
                "requirements": result.get("requirements", []),
                "reasoning": result.get("reasoning", ""),
                "classified_at": datetime.now().isoformat()
            }
            
            stats["classified"] += 1
            stats[agent.eu_risk_class] += 1
            
            # Track high-risk agents for reporting
            if agent.eu_risk_class in ["high", "unacceptable"]:
                high_risk_agents.append({
                    "name": agent.name,
                    "description": agent.description,
                    "risk_class": agent.eu_risk_class,
                    "source_url": agent.source_url,
                    "reasoning": result.get("reasoning", ""),
                    "category": result.get("annex_category", ""),
                    "requirements": result.get("requirements", [])
                })
                print(f"🚨 {agent.eu_risk_class.upper()}: {agent.name}")
                
        except Exception as e:
            logger.error(f"Error classifying {agent.name}: {e}")
            stats["errors"] += 1
            
    # Commit all changes
    try:
        session.commit()
        print(f"\n✅ EU Compliance Classification Complete:")
        print(f"   Total classified: {stats['classified']}")
        print(f"   🚨 UNACCEPTABLE: {stats['unacceptable']}")
        print(f"   🔴 HIGH risk: {stats['high']}")  
        print(f"   🟡 LIMITED risk: {stats['limited']}")
        print(f"   ✅ MINIMAL risk: {stats['minimal']}")
        print(f"   ❌ Errors: {stats['errors']}")
        
        # Report high-risk MCP servers
        if high_risk_agents:
            print(f"\n🎯 HIGH-RISK MCP SERVERS ({len(high_risk_agents)}):")
            print("=" * 60)
            
            for agent in high_risk_agents[:10]:  # Show top 10
                print(f"• {agent['name']} ({agent['risk_class'].upper()})")
                print(f"  Description: {agent['description'][:120]}...")
                print(f"  Category: {agent['category']}")
                print(f"  Reasoning: {agent['reasoning'][:150]}...")
                print(f"  URL: {agent['source_url']}")
                print()
                
            print("🎯 OUTREACH OPPORTUNITY:")
            print(f"   • {len(high_risk_agents)} MCP builders need compliance guidance")
            print(f"   • These are PERFECT targets for educational GitHub issues")
            print(f"   • Message: 'Your MCP server was classified as {high_risk_agents[0]['risk_class']}-risk under EU AI Act'")
            
    except Exception as e:
        session.rollback()
        logger.error(f"Database commit error: {e}")
        return False
        
    return stats

if __name__ == "__main__":
    from datetime import datetime
    
    stats = classify_mcp_agents()
    if stats and (stats["high"] > 0 or stats["unacceptable"] > 0):
        total_high_risk = stats["high"] + stats["unacceptable"]
        print(f"\n🚀 NEXT STEPS:")
        print(f"   1. Prepare GitHub Issues for {total_high_risk} high-risk MCP repos")
        print(f"   2. Test with 3 repos first (per Anders rules)")
        print(f"   3. Educational approach: 'Free compliance report available'")
    else:
        print("No high-risk MCP servers found in this batch")