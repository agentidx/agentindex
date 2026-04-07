"""Debug parser loop för att fånga full SQLAlchemy traceback."""
import time, logging, os, sys, traceback
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [parser] %(message)s")
logger = logging.getLogger("parser_loop_debug")

from agentindex.agents.parser import Parser

def debug_run():
    """Kör parser med full exception tracking."""
    try:
        p = Parser()
        # Samma batch-storlek som production
        stats = p.parse_pending(batch_size=20)  
        logger.info(f"Parse batch: {stats}")
        return stats
    except Exception as e:
        logger.error(f"FULL TRACEBACK:")
        logger.error(traceback.format_exc())
        raise e

if __name__ == "__main__":
    logger.info("🔍 DEBUG PARSER STARTED - Will capture full traceback")
    
    while True:
        try:
            stats = debug_run()
            if stats["parsed"] == 0 and stats["skipped"] == 0 and stats["errors"] == 0:
                logger.info("Nothing to parse, exiting debug run")
                break
            else:
                logger.info("One batch complete, continuing...")
                time.sleep(2)
        except Exception as e:
            logger.error(f"TOP LEVEL ERROR: {e}")
            logger.error("STOPPING DEBUG RUN")
            break