"""
MCP Compliance Classifier

Analyzes MCP servers for compliance risks:
- Financial data handling (SOX, PCI-DSS, banking regulations)
- Personal data processing (GDPR, CCPA, HIPAA)  
- Corporate data access (M365, Slack, etc.)

This is our strategic advantage: we're first to tell MCP builders about compliance risks.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from ollama import Client
from agentindex.db.models import Agent, get_session
from sqlalchemy import select, update, and_, or_, text
import os

logger = logging.getLogger("agentindex.mcp_compliance")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL_LARGE", "qwen2.5:7b")

# Financial data patterns
FINANCIAL_KEYWORDS = [
    "stock", "forex", "trading", "market", "ticker", "financial", "bank", "payment", 
    "crypto", "bitcoin", "ethereum", "portfolio", "investment", "finance", "trading",
    "sec", "nasdaq", "bloomberg", "yahoo finance", "alpha vantage"
]

# Personal data patterns
PERSONAL_DATA_KEYWORDS = [
    "email", "contact", "calendar", "personal", "user data", "profile", "identity",
    "health", "medical", "patient", "gdpr", "ccpa", "pii", "privacy"
]

# Corporate data access
CORPORATE_KEYWORDS = [
    "microsoft 365", "m365", "office 365", "outlook", "teams", "sharepoint", 
    "onedrive", "slack", "google workspace", "gsuite", "salesforce", "crm"
]

COMPLIANCE_PROMPT = """Analyze this MCP server for compliance risks. Focus on data handling and regulatory requirements.

Name: {name}
Description: {description}  
README: {readme}
Tags: {tags}

Based on functionality, classify compliance risk level:

HIGH RISK:
- Handles financial data (stock prices, trading, payments, banking)
- Processes personal/health data (GDPR/HIPAA scope)
- Accesses corporate systems (M365, Slack, CRM)

MEDIUM RISK: 
- Business tools that might handle sensitive data
- API integrations with potential data exposure

LOW RISK:
- Development tools, code utilities
- Read-only public data access
- Simple computational tasks

JSON response:
{{
  "risk_level": "high|medium|low",
  "compliance_flags": ["gdpr", "hipaa", "sox", "pci-dss", "ccpa"],
  "data_types": ["financial", "personal", "health", "corporate", "public"],
  "reasoning": "Brief explanation of risk assessment",
  "regulations": ["specific regulations that likely apply"]
}}"""


class McpComplianceClassifier:
    """Analyzes MCP servers for compliance risks and regulatory requirements."""

    def __init__(self):
        self.client = Client(host=OLLAMA_BASE_URL)
        self.session = get_session()

    def classify_all_mcp(self, batch_size: int = 20) -> dict:
        """Classify all MCP servers that haven't been compliance-checked."""
        stats = {"processed": 0, "high_risk": 0, "medium_risk": 0, "low_risk": 0, "errors": 0}

        # Get all MCP servers not yet compliance-classified
        self.session.execute(text("SET LOCAL work_mem = '2MB'"))
        self.session.execute(text("SET LOCAL statement_timeout = '30s'"))
        mcp_agents = self.session.execute(
            select(Agent)
            .where(
                and_(
                    or_(Agent.source == "mcp", Agent.protocols.contains("mcp")),
                    Agent.crawl_status == "parsed",  # Only parsed agents
                    ~Agent.raw_metadata.op("->")("compliance_classified").astext.cast(bool)
                )
            )
            .limit(batch_size)
        ).scalars().all()

        for agent in mcp_agents:
            try:
                risk_data = self._classify_mcp_server(agent)
                if risk_data:
                    # Update agent with compliance data
                    self._update_agent_compliance(agent, risk_data)
                    stats["processed"] += 1
                    stats[f"{risk_data['risk_level']}_risk"] += 1
                    
                    logger.info(f"Classified {agent.name}: {risk_data['risk_level']} risk")
                    
                try:
                    self.session.commit()
                except Exception:
                    self.session.rollback()
                    self.session = get_session()
                    
            except Exception as e:
                logger.error(f"Error classifying {agent.name}: {e}")
                stats["errors"] += 1

        logger.info(f"MCP compliance classification complete: {stats}")
        return stats

    def _classify_mcp_server(self, agent: Agent) -> Optional[Dict]:
        """Classify a single MCP server for compliance risks."""
        metadata = agent.raw_metadata or {}

        # Pre-screening with keywords for efficiency
        text_content = f"{agent.name} {agent.description} {' '.join(agent.tags or [])} {metadata.get('readme', '')}"
        text_lower = text_content.lower()

        # Quick keyword-based pre-screening
        has_financial = any(kw in text_lower for kw in FINANCIAL_KEYWORDS)
        has_personal = any(kw in text_lower for kw in PERSONAL_DATA_KEYWORDS)  
        has_corporate = any(kw in text_lower for kw in CORPORATE_KEYWORDS)

        # If no sensitive keywords found, likely low risk
        if not (has_financial or has_personal or has_corporate):
            return {
                "risk_level": "low",
                "compliance_flags": [],
                "data_types": ["public"],
                "reasoning": "No sensitive data handling detected",
                "regulations": []
            }

        # Use LLM for detailed analysis if potential risks detected
        prompt = COMPLIANCE_PROMPT.format(
            name=agent.name,
            description=agent.description or "N/A",
            readme=(metadata.get("readme") or "N/A")[:1000],
            tags=", ".join(agent.tags or [])
        )

        try:
            response = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1}
            )
        except Exception as e:
            logger.error(f"LLM error for {agent.name}: {e}")
            return None

        # Parse LLM response
        text = response["message"]["content"].strip()
        parsed = self._extract_json(text)

        if not parsed:
            logger.warning(f"Could not parse compliance response for {agent.name}")
            return None

        return parsed

    def _update_agent_compliance(self, agent: Agent, risk_data: Dict):
        """Update agent with compliance classification results."""
        if not agent.raw_metadata:
            agent.raw_metadata = {}

        # Add compliance data to metadata
        agent.raw_metadata["compliance_classified"] = True
        agent.raw_metadata["compliance_risk"] = risk_data["risk_level"]
        agent.raw_metadata["compliance_flags"] = risk_data.get("compliance_flags", [])
        agent.raw_metadata["data_types"] = risk_data.get("data_types", [])
        agent.raw_metadata["compliance_reasoning"] = risk_data.get("reasoning", "")
        agent.raw_metadata["applicable_regulations"] = risk_data.get("regulations", [])
        agent.raw_metadata["compliance_checked_at"] = datetime.utcnow().isoformat()

        # Add compliance tags for filtering
        new_tags = agent.tags or []
        new_tags.append(f"compliance-{risk_data['risk_level']}")
        
        for flag in risk_data.get("compliance_flags", []):
            new_tags.append(f"regulation-{flag}")
            
        for data_type in risk_data.get("data_types", []):
            new_tags.append(f"data-{data_type}")

        agent.tags = list(set(new_tags))  # Remove duplicates

        # Update category if financial/health
        if "financial" in risk_data.get("data_types", []):
            agent.category = "finance"
        elif "health" in risk_data.get("data_types", []):
            agent.category = "health"

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from LLM response."""
        import json
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown
        if "```json" in text:
            try:
                json_str = text.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str)
            except (IndexError, json.JSONDecodeError):
                pass

        # Try finding JSON object
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            pass

        return None

    def get_high_risk_summary(self) -> List[Dict]:
        """Get summary of high-risk MCP servers for reporting."""
        self.session.execute(text("SET LOCAL work_mem = '2MB'"))
        self.session.execute(text("SET LOCAL statement_timeout = '30s'"))
        high_risk_agents = self.session.execute(
            select(Agent)
            .where(
                and_(
                    Agent.raw_metadata.op("->")("compliance_risk").astext == "high",
                    or_(Agent.source == "mcp", Agent.protocols.contains("mcp"))
                )
            )
            .order_by(Agent.stars.desc())
        ).scalars().all()

        summary = []
        for agent in high_risk_agents:
            metadata = agent.raw_metadata or {}
            summary.append({
                "name": agent.name,
                "description": agent.description,
                "source_url": agent.source_url,
                "stars": agent.stars,
                "risk_level": metadata.get("compliance_risk"),
                "flags": metadata.get("compliance_flags", []),
                "data_types": metadata.get("data_types", []),
                "reasoning": metadata.get("compliance_reasoning", ""),
                "regulations": metadata.get("applicable_regulations", [])
            })

        return summary


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    classifier = McpComplianceClassifier()
    stats = classifier.classify_all_mcp(batch_size=10)
    print(f"Compliance classification complete: {stats}")

    # Show high-risk summary
    high_risk = classifier.get_high_risk_summary()
    if high_risk:
        print(f"\nFound {len(high_risk)} high-risk MCP servers:")
        for agent in high_risk[:5]:
            print(f"- {agent['name']}: {', '.join(agent['flags'])}")