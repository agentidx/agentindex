"""Standalone parser loop - runs independently from main orchestrator."""
import time, logging, os, sys
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [parser] %(message)s")
logger = logging.getLogger("parser_loop")

from agentindex.agents.parser import Parser

while True:
    try:
        p = Parser()
        stats = p.parse_pending(batch_size=20)
        logger.info(f"Batch done: {stats}")
        if stats["parsed"] == 0 and stats["skipped"] == 0 and stats["errors"] == 0:
            logger.info("Nothing to parse, sleeping 60s")
            time.sleep(60)
        else:
            time.sleep(5)
    except Exception as e:
        logger.error(f"Parser error: {e}")
        time.sleep(30)
