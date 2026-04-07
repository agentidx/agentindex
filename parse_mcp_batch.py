#!/usr/bin/env python3
"""
Parse reclassified MCP servers in batches.
"""

import sys
import os
sys.path.insert(0, os.path.expanduser("~/agentindex"))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

import logging
import time
from agentindex.agents.parser import Parser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_parse")

def parse_mcp_servers():
    """Parse MCP servers in controlled batches."""
    
    parser = Parser()
    total_parsed = 0
    
    for batch in range(20):  # Max 20 batches
        logger.info(f"Running batch {batch + 1}/20...")
        
        stats = parser.parse_pending(batch_size=25)  # Smaller batches for MCP focus
        
        if stats["parsed"] == 0 and stats["skipped"] == 0:
            logger.info("No more agents to parse")
            break
            
        total_parsed += stats["parsed"]
        logger.info(f"Batch {batch + 1}: {stats}")
        logger.info(f"Total parsed so far: {total_parsed}")
        
        if stats["parsed"] == 0:
            break
            
        time.sleep(2)  # Brief pause between batches
    
    print(f"\n✅ Parsing complete: {total_parsed} agents parsed")
    return total_parsed

if __name__ == "__main__":
    parsed = parse_mcp_servers()
    if parsed > 0:
        print(f"Next: Run EU compliance classification on {parsed} new agents")
    else:
        print("No agents were parsed")