#!/usr/bin/env python3
"""Classify ALL MCP servers regardless of status with enhanced classifier."""

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
logger = logging.getLogger("classify_all_mcp_complete")

def classify_all_mcp_servers():
    """Classify ALL MCP servers regardless of current status."""
    
    session = get_session()
    classifier = EnhancedRiskClassifier()
    
    # Get ALL MCP servers that don't have EU classification yet
    all_mcp = session.execute(
        select(Agent).where(
            Agent.source == "mcp"
        ).where(
            Agent.eu_risk_class.is_(None)  # Only unclassified
        ).order_by(Agent.stars.desc())  # Process popular ones first
    ).scalars().all()
    
    print(f"Found {len(all_mcp)} MCP servers to classify (ALL statuses)")
    
    # Break down by status for reporting
    status_breakdown = {}
    for agent in all_mcp:
        status = agent.crawl_status
        status_breakdown[status] = status_breakdown.get(status, 0) + 1
        
    print("Status breakdown:")
    for status, count in sorted(status_breakdown.items()):
        print(f"  {status}: {count}")
    
    stats = {
        "classified": 0,
        "high": 0,
        "limited": 0,
        "minimal": 0,
        "errors": 0
    }
    
    high_risk_servers = []
    limited_risk_servers = []
    
    batch_size = 100
    total_batches = (len(all_mcp) + batch_size - 1) // batch_size
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min((batch_num + 1) * batch_size, len(all_mcp))
        batch = all_mcp[start_idx:end_idx]
        
        logger.info(f"Processing batch {batch_num + 1}/{total_batches} ({len(batch)} servers)")
        
        for i, agent in enumerate(batch, 1):
            try:
                # Enhanced classification (rule-based for speed)
                result = classifier.classify(
                    name=agent.name,
                    description=agent.description or "",
                    capabilities=agent.capabilities or [],
                    category=agent.category or "infrastructure",
                    use_llm=False  # Rule-based for speed across all servers
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
                    "classifier_version": "enhanced_v1",
                    "original_status": agent.crawl_status
                }
                
                stats["classified"] += 1
                stats[agent.eu_risk_class] += 1
                
                # Collect high-risk servers
                if agent.eu_risk_class == "high":
                    high_risk_servers.append({
                        "name": agent.name,
                        "description": (agent.description or "")[:150],
                        "source_url": agent.source_url,
                        "reasoning": result.get("reasoning", "")[:200],
                        "annex_category": result.get("annex_category", ""),
                        "stars": agent.stars or 0,
                        "original_status": agent.crawl_status
                    })
                    
                elif agent.eu_risk_class == "limited":
                    limited_risk_servers.append({
                        "name": agent.name,
                        "reasoning": result.get("reasoning", "")[:100],
                        "stars": agent.stars or 0
                    })
                    
            except Exception as e:
                logger.error(f"Error classifying {agent.name}: {e}")
                stats["errors"] += 1
        
        # Commit batch
        try:
            session.commit()
            logger.info(f"Batch {batch_num + 1} committed: +{len(batch)} classified")
        except Exception as e:
            session.rollback()
            logger.error(f"Batch {batch_num + 1} commit failed: {e}")
            stats["errors"] += len(batch)
            continue
    
    # Final summary
    print(f"\n✅ COMPLETE MCP CLASSIFICATION FINISHED")
    print(f"   Total MCP servers classified: {stats['classified']}")
    print(f"   🚨 HIGH risk: {stats['high']} ({stats['high']/stats['classified']*100 if stats['classified'] > 0 else 0:.1f}%)")
    print(f"   ⚠️  LIMITED risk: {stats['limited']} ({stats['limited']/stats['classified']*100 if stats['classified'] > 0 else 0:.1f}%)")
    print(f"   ✅ MINIMAL risk: {stats['minimal']} ({stats['minimal']/stats['classified']*100 if stats['classified'] > 0 else 0:.1f}%)")
    print(f"   ❌ Errors: {stats['errors']}")
    print(f"   Success rate: {((stats['classified'] - stats['errors']) / stats['classified'] * 100 if stats['classified'] > 0 else 0):.1f}%")
    
    # Top high-risk servers by popularity
    if high_risk_servers:
        high_risk_servers.sort(key=lambda x: x['stars'], reverse=True)
        print(f"\n🎯 TOP 10 HIGH-RISK MCP SERVERS (by stars):")
        print("=" * 80)
        
        for i, server in enumerate(high_risk_servers[:10], 1):
            print(f"{i}. 🚨 {server['name']} (⭐{server['stars']})")
            print(f"   {server['description']}")
            print(f"   Risk: {server['annex_category']} | Status: {server['original_status']}")
            print(f"   Reasoning: {server['reasoning']}")
            print(f"   URL: {server['source_url']}")
            print()
    
    # Limited-risk summary
    if limited_risk_servers:
        limited_risk_servers.sort(key=lambda x: x['stars'], reverse=True)
        print(f"\n⚠️ TOP 5 LIMITED-RISK MCP SERVERS:")
        for i, server in enumerate(limited_risk_servers[:5], 1):
            print(f"{i}. ⚠️  {server['name']} (⭐{server['stars']}): {server['reasoning']}")
    
    return stats

if __name__ == "__main__":
    stats = classify_all_mcp_servers()
    
    if stats and stats["classified"] > 0:
        print(f"\n📊 FINAL DELIVERABLE FOR ANDERS:")
        print(f"   TOTAL MCP servers classified: {stats['classified']}")
        print(f"   HIGH-risk: {stats['high']} servers")
        print(f"   LIMITED-risk: {stats['limited']} servers") 
        print(f"   MINIMAL-risk: {stats['minimal']} servers")
        print(f"   Error rate: {stats['errors']/stats['classified']*100 if stats['classified'] > 0 else 0:.1f}%")
        
        print(f"\n✅ READY FOR FAS 1:")
        print(f"   Enhanced classifier complete on all MCP servers")
        print(f"   Solid data foundation: {stats['high']} high-risk targets")
        print(f"   Next: jurisdiction_registry + multi-jurisdiction API")
    else:
        print("❌ Classification failed")