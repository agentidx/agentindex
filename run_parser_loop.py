"""Standalone parser loop with MCP Compliance classification - strategic advantage."""
import time, logging, os, sys
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [parser] %(message)s")
logger = logging.getLogger("parser_loop")

from agentindex.agents.parser import Parser
from agentindex.agents.mcp_compliance import McpComplianceClassifier

compliance_classifier = McpComplianceClassifier()

while True:
    try:
        p = Parser()
        stats = p.parse_pending(batch_size=20)
        logger.info(f"Parse batch: {stats}")
        
        # Run MCP compliance classification after parsing
        if stats["parsed"] > 0:
            comp_stats = compliance_classifier.classify_all_mcp(batch_size=10)
            logger.info(f"MCP Comply: {comp_stats['processed']} classified - "
                       f"High: {comp_stats['high_risk']}, Med: {comp_stats['medium_risk']}, Low: {comp_stats['low_risk']}")
        
        if stats["parsed"] == 0 and stats["skipped"] == 0 and stats["errors"] == 0:
            logger.info("Nothing to parse, sleeping 60s")
            time.sleep(60)
        else:
            time.sleep(5)
    except Exception as e:
        logger.error(f"Parser error: {e}")
        time.sleep(30)
