#!/usr/bin/env python3
"""
Run EU compliance classification on newly parsed MCP servers.
Uses EXISTING eu_risk_class system (not new MCP classifier).
"""

import sys
import os
sys.path.insert(0, os.path.expanduser("~/agentindex"))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

import logging
from agentindex.db.models import Agent, get_session
from sqlalchemy import select
import httpx
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eu_compliance")

def classify_eu_risk_mcp():
    """Run EU compliance on parsed MCP servers using existing API."""
    
    session = get_session()
    
    # Find parsed MCP servers without EU classification
    mcp_agents = session.execute(
        select(Agent).where(
            Agent.source == "mcp"
        ).where(
            Agent.crawl_status == "parsed"
        ).where(
            Agent.eu_risk_class.is_(None)  # No EU classification yet
        ).limit(100)  # Process in batches
    ).scalars().all()
    
    print(f"Found {len(mcp_agents)} parsed MCP servers needing EU compliance")
    
    # Use local API for EU classification
    classified = 0
    high_risk = 0
    limited_risk = 0  
    minimal_risk = 0
    errors = 0
    
    for agent in mcp_agents:
        try:
            # Call local EU compliance API
            response = httpx.post(
                "http://localhost:8100/v1/classify/eu", 
                json={
                    "name": agent.name,
                    "description": agent.description or "",
                    "capabilities": agent.capabilities or [],
                    "category": agent.category or "other"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Update agent with EU classification
                agent.eu_risk_class = result.get("risk_class", "minimal")
                agent.eu_risk_confidence = result.get("confidence", 0.5)
                agent.compliance_score = result.get("compliance_score", 95.0)
                
                classified += 1
                
                # Count by risk class
                if agent.eu_risk_class == "high":
                    high_risk += 1
                    logger.info(f"HIGH RISK: {agent.name}")
                elif agent.eu_risk_class == "limited":
                    limited_risk += 1
                    logger.info(f"LIMITED RISK: {agent.name}")
                else:
                    minimal_risk += 1
                
                if classified <= 10:  # Log first 10
                    logger.info(f"Classified {agent.name}: {agent.eu_risk_class}")
                    
            else:
                logger.error(f"API error for {agent.name}: {response.status_code}")
                errors += 1
                
        except Exception as e:
            logger.error(f"Error classifying {agent.name}: {e}")
            errors += 1
            
    try:
        session.commit()
        print(f"✅ EU Compliance complete:")
        print(f"   Classified: {classified}")
        print(f"   🚨 HIGH risk: {high_risk}")  
        print(f"   ⚠️  LIMITED risk: {limited_risk}")
        print(f"   ✅ MINIMAL risk: {minimal_risk}")
        print(f"   ❌ Errors: {errors}")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Database error: {e}")
        return False
    
    return {
        "classified": classified,
        "high": high_risk,
        "limited": limited_risk,
        "minimal": minimal_risk,
        "errors": errors
    }

if __name__ == "__main__":
    # Check if API is running
    try:
        response = httpx.get("http://localhost:8100/v1/health")
        if response.status_code != 200:
            print("❌ AgentIndex API not running. Start with: cd ~/agentindex && python -m agentindex.run")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Cannot connect to AgentIndex API: {e}")
        sys.exit(1)
        
    stats = classify_eu_risk_mcp()
    if stats and stats["high"] > 0:
        print(f"\n🎯 Found {stats['high']} HIGH-RISK MCP servers - perfect targets for outreach!")
    else:
        print("No high-risk MCP servers found")