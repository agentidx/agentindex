"""Fixed parser loop with robust error handling."""
import time, logging, os, sys, traceback
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [parser] %(message)s")
logger = logging.getLogger("parser_loop_fixed")

from agentindex.agents.parser import Parser
from agentindex.agents.mcp_compliance import McpComplianceClassifier

class RobustParser(Parser):
    """Parser med robust error handling för varje agent."""
    
    def parse_pending(self, batch_size: int = 50) -> dict:
        """Parse med individual try/catch för varje agent."""
        stats = {"parsed": 0, "skipped": 0, "errors": 0}

        try:
            agents = self.session.execute(
                select(Agent)
                .where(Agent.crawl_status == "classified").order_by(Agent.stars.desc().nullslast())
                .order_by(Agent.stars.desc())
                .limit(batch_size)
            ).scalars().all()
        except Exception as e:
            logger.error(f"Database query error: {e}")
            logger.error(traceback.format_exc())
            return stats

        for agent in agents:
            try:
                result = self._parse_agent(agent)
                if result:
                    stats["parsed"] += 1
                else:
                    stats["skipped"] += 1
                    
                # Individual commit för varje agent
                try:
                    self.session.commit()
                except Exception as commit_error:
                    logger.error(f"Commit error for agent {agent.name}: {commit_error}")
                    self.session.rollback()
                    self.session = get_session()  # Fresh session
                    stats["errors"] += 1
                    
            except Exception as e:
                logger.error(f"Error parsing agent {agent.name} (id: {agent.id}): {e}")
                logger.error(f"Agent data: source={agent.source}, url={agent.source_url}")
                logger.error(traceback.format_exc())
                stats["errors"] += 1
                
                # Mark agent as failed and continue
                try:
                    agent.crawl_status = "parse_failed"
                    self.session.commit()
                except:
                    self.session.rollback()
                    self.session = get_session()

        # Final commit
        try:
            self.session.commit()
        except Exception as final_error:
            logger.error(f"Final commit error: {final_error}")
            self.session.rollback()

        logger.info(f"Parse batch complete: {stats}")
        return stats

# Fix import issue
from sqlalchemy import select
from agentindex.db.models import Agent, get_session

def main():
    """Main parser loop med robust error handling."""
    compliance_classifier = McpComplianceClassifier()
    
    while True:
        try:
            parser = RobustParser()
            stats = parser.parse_pending(batch_size=20)
            logger.info(f"Parse batch: {stats}")
            
            # Run MCP compliance classification efter parsing
            if stats["parsed"] > 0:
                try:
                    comp_stats = compliance_classifier.classify_all_mcp(batch_size=10)
                    logger.info(f"MCP Comply: {comp_stats['processed']} classified - "
                               f"High: {comp_stats['high_risk']}, Med: {comp_stats['medium_risk']}, Low: {comp_stats['low_risk']}")
                except Exception as comp_error:
                    logger.error(f"MCP compliance error: {comp_error}")
            
            if stats["parsed"] == 0 and stats["skipped"] == 0 and stats["errors"] == 0:
                logger.info("Nothing to parse, sleeping 60s")
                time.sleep(60)
            else:
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"Top-level parser error: {e}")
            logger.error(traceback.format_exc())
            time.sleep(30)  # Längre vila vid kritiska fel

if __name__ == "__main__":
    logger.info("🎯 TARGETING CLASSIFIED QUEUE - Fixed parser with robust error handling")
    main()