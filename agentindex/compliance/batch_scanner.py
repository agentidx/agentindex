"""
Batch Compliance Scanner

Runs through all indexed agents and classifies them under EU AI Act.
Designed to run as a scheduled job (add to run.py scheduler).

First run: keyword-only (fast, covers all 40K+)
Subsequent: LLM for high/unacceptable hits (accurate, slower)
"""

import logging
import time
from datetime import datetime
from sqlalchemy import text
from agentindex.db.models import get_session
from agentindex.compliance.risk_classifier import RiskClassifier

logger = logging.getLogger("openclaw.batch_scanner")


def scan_all_agents(batch_size=500, use_llm=False):
    """
    Scan all agents that haven't been compliance-checked yet.
    
    Phase 1 (use_llm=False): Fast keyword scan, ~40K agents in minutes
    Phase 2 (use_llm=True): LLM refinement for non-minimal results
    """
    session = get_session()
    classifier = RiskClassifier()
    
    stats = {"total": 0, "minimal": 0, "limited": 0, "high": 0, "unacceptable": 0, "errors": 0}
    
    try:
        # capabilities not in entity_lookup; use agents with guard
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        # Get unchecked agents
        if use_llm:
            # Phase 2: only re-check non-minimal agents with LLM
            query = text("""
                SELECT id, name, description, capabilities, category
                FROM agents
                WHERE eu_risk_class IS NOT NULL AND eu_risk_class != 'minimal'
                AND (last_compliance_check IS NULL OR last_compliance_check < NOW() - interval '30 days')
                ORDER BY stars DESC NULLS LAST
                LIMIT :limit
            """)
        else:
            # Phase 1: all unchecked agents
            query = text("""
                SELECT id, name, description, capabilities, category
                FROM agents
                WHERE eu_risk_class IS NULL AND is_active = TRUE
                ORDER BY stars DESC NULLS LAST
                LIMIT :limit
            """)
        
        rows = session.execute(query, {"limit": batch_size}).mappings().fetchall()
        total = len(rows)
        logger.info(f"Scanning {total} agents (LLM={'ON' if use_llm else 'OFF'})")
        
        for i, agent in enumerate(rows):
            try:
                result = classifier.classify(
                    name=agent["name"] or "",
                    description=agent["description"] or "",
                    capabilities=agent["capabilities"],
                    category=agent["category"],
                    use_llm=use_llm
                )
                
                # Update agent record
                session.execute(text("""
                    UPDATE agents SET 
                        eu_risk_class = :risk,
                        eu_risk_confidence = :conf,
                        compliance_score = :score,
                        last_compliance_check = NOW()
                    WHERE id = :id
                """), {
                    "risk": result["risk_class"],
                    "conf": result["confidence"],
                    "score": result["compliance_score"],
                    "id": agent["id"]
                })
                
                stats[result["risk_class"]] = stats.get(result["risk_class"], 0) + 1
                stats["total"] += 1
                
                # Commit every 100
                if stats["total"] % 100 == 0:
                    session.commit()
                    logger.info(f"  Progress: {stats['total']}/{total} | "
                               f"H:{stats['high']} L:{stats['limited']} M:{stats['minimal']}")
                    
            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"Error classifying {agent['name']}: {e}")
                continue
        
        session.commit()
        logger.info(f"Scan complete: {stats}")
        return stats
        
    finally:
        session.close()


def run_compliance_scan():
    """Entry point for scheduler integration."""
    logger.info("Starting compliance scan (Phase 1: keyword)...")
    stats = scan_all_agents(batch_size=5000, use_llm=False)
    
    # If we found high-risk agents, refine with LLM
    if stats.get("high", 0) > 0 or stats.get("unacceptable", 0) > 0:
        logger.info(f"Found {stats.get('high', 0)} high-risk + {stats.get('unacceptable', 0)} unacceptable. Running LLM refinement...")
        time.sleep(5)  # Brief pause before LLM load
        stats_llm = scan_all_agents(batch_size=100, use_llm=True)
        logger.info(f"LLM refinement complete: {stats_llm}")
    
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_compliance_scan()
