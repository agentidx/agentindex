#!/usr/bin/env python3
"""
Reclassify MCP servers from "not_agent" to "indexed" so they can be re-parsed.
MCP servers should ALWAYS be agents by definition.
"""

import sys
import os
sys.path.insert(0, os.path.expanduser("~/agentindex"))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

import logging
from agentindex.db.models import Agent, get_session
from sqlalchemy import select, update

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_reclassify")

def reclassify_mcp_servers():
    """Reclassify MCP servers from not_agent to indexed for re-parsing."""
    
    session = get_session()
    
    # Find MCP servers marked as "not_agent"
    mcp_not_agents = session.execute(
        select(Agent).where(
            Agent.source == "mcp"
        ).where(
            Agent.crawl_status == "not_agent"
        )
    ).scalars().all()
    
    print(f"Found {len(mcp_not_agents)} MCP servers marked as 'not_agent'")
    
    # Reclassify them to "indexed" for re-parsing
    reclassified = 0
    for agent in mcp_not_agents:
        # Check if it's really an MCP server
        text_content = f"{agent.name} {agent.description or ''} {' '.join(agent.tags or [])}"
        is_mcp = ("mcp" in text_content.lower() or 
                  "model context protocol" in text_content.lower() or
                  agent.source == "mcp")
        
        if is_mcp:
            agent.crawl_status = "indexed"
            reclassified += 1
            if reclassified <= 10:  # Log first 10
                logger.info(f"Reclassifying: {agent.name}")
    
    try:
        session.commit()
        print(f"✅ Successfully reclassified {reclassified} MCP servers to 'indexed'")
    except Exception as e:
        session.rollback()
        print(f"❌ Error during reclassification: {e}")
        return False
    
    return reclassified

if __name__ == "__main__":
    reclassified = reclassify_mcp_servers()
    if reclassified:
        print(f"\nNext: Run parser to re-parse {reclassified} MCP servers as agents")
    else:
        print("No MCP servers reclassified")