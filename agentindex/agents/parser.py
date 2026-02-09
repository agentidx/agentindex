"""
AgentIndex Parser

Takes raw crawled data and uses the local 7B model to extract
structured agent profiles. This is where unstructured README text
becomes structured, searchable agent capabilities.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from ollama import Client
from agentindex.db.models import Agent, get_session
from sqlalchemy import select
import os

logger = logging.getLogger("agentindex.parser")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL_SMALL", "qwen2.5:7b")

PARSE_PROMPT = """Classify this software. Is it an AI agent, AI tool, MCP server, agent framework, or agent platform? Respond ONLY with JSON.

An "agent" includes: autonomous agents, AI assistants, MCP servers, agent frameworks, agent platforms, AI tools that can be invoked programmatically, and LLM-based automation tools.

Name: {name}
Description: {description}
README: {readme}

JSON:
{{
  "is_agent": true/false,
  "category": "coding|research|content|legal|data|finance|marketing|design|devops|security|education|health|communication|productivity|infrastructure|other",
  "capabilities": ["cap1", "cap2", "cap3"],
  "description_short": "one sentence"
}}"""


class Parser:
    """
    Parses raw crawled data into structured agent profiles using local LLM.
    """

    def __init__(self):
        self.client = Client(host=OLLAMA_BASE_URL)
        self.session = get_session()

    def parse_pending(self, batch_size: int = 50) -> dict:
        """
        Parse all agents with crawl_status='indexed' (not yet parsed).
        """
        stats = {"parsed": 0, "skipped": 0, "errors": 0}

        agents = self.session.execute(
            select(Agent)
            .where(Agent.crawl_status == "indexed").order_by(Agent.stars.desc().nullslast())
            .order_by(Agent.stars.desc())  # prioritize popular repos
            .limit(batch_size)
        ).scalars().all()

        for agent in agents:
            try:
                result = self._parse_agent(agent)
                if result:
                    stats["parsed"] += 1
                else:
                    stats["skipped"] += 1
                try:
                    self.session.commit()
                except Exception:
                    self.session.rollback()
                    self.session = get_session()
            except Exception as e:
                logger.error(f"Error parsing agent {agent.name}: {e}")
                stats["errors"] += 1

        self.session.commit()
        logger.info(f"Parse batch complete: {stats}")
        return stats

    def _parse_agent(self, agent: Agent) -> bool:
        """Parse a single agent using local LLM."""
        metadata = agent.raw_metadata or {}

        # Build prompt
        prompt = PARSE_PROMPT.format(
            name=agent.name,
            description=agent.description or "N/A",
            topics=", ".join(agent.tags or []),
            language=agent.language or "N/A",
            readme=(metadata.get("readme") or "N/A")[:500],
            skill_md=(metadata.get("skill_md") or "N/A")[:500],
            agent_md=(metadata.get("agent_md") or "N/A")[:500],
        )

        # Call local LLM
        try:
            response = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},  # low temperature for structured output
            )
        except Exception as e:
            logger.error(f"Ollama error for {agent.name}: {e}")
            return False

        # Parse response
        text = response["message"]["content"].strip()
        parsed = self._extract_json(text)
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed else None

        if not parsed:
            logger.warning(f"Could not parse LLM response for {agent.name}")
            agent.crawl_status = "parse_failed"
            return False

        # Check if this is actually an agent
        if not parsed.get("is_agent", False):
            agent.is_active = False
            agent.crawl_status = "not_agent"
            return False

        # confidence check removed - classifier handles this

        # Update agent with parsed data
        agent.capabilities = parsed.get("capabilities", [])
        agent.category = parsed.get("category", "other")
        agent.description = parsed.get("description_short", agent.description)

        pricing_model = parsed.get("pricing_model", "unknown")
        agent.pricing = {"model": pricing_model}

        # Initial quality scoring based on available signals
        agent.documentation_score = self._score_documentation(agent)
        agent.activity_score = self._score_activity(agent)
        agent.popularity_score = self._score_popularity(agent)
        agent.capability_depth_score = self._score_capability_depth(parsed)

        # Overall quality score (simple weighted average for now)
        agent.quality_score = (
            agent.documentation_score * 0.2 +
            agent.activity_score * 0.25 +
            agent.popularity_score * 0.2 +
            agent.capability_depth_score * 0.2 +
            0.5 * 0.15  # default confidence
        )

        agent.crawl_status = "parsed"
        return True

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from LLM response, handling common issues."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        if "```json" in text:
            try:
                json_str = text.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str)
            except (IndexError, json.JSONDecodeError):
                pass

        if "```" in text:
            try:
                json_str = text.split("```")[1].split("```")[0].strip()
                return json.loads(json_str)
            except (IndexError, json.JSONDecodeError):
                pass

        # Try finding JSON object in text
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            pass

        return None

    def _score_documentation(self, agent: Agent) -> float:
        """Score documentation quality 0.0-1.0."""
        score = 0.0
        metadata = agent.raw_metadata or {}

        readme = metadata.get("readme") or ""
        if len(readme) > 500:
            score += 0.3
        if len(readme) > 2000:
            score += 0.2
        if "## " in readme or "### " in readme:  # has headers
            score += 0.1
        if "install" in readme.lower():
            score += 0.1
        if "example" in readme.lower() or "usage" in readme.lower():
            score += 0.1
        if metadata.get("skill_md") or metadata.get("agent_md"):
            score += 0.2

        return min(score, 1.0)

    def _score_activity(self, agent: Agent) -> float:
        """Score maintenance/activity level 0.0-1.0."""
        if not agent.last_source_update:
            return 0.0

        days_since_update = (datetime.utcnow() - agent.last_source_update).days

        if days_since_update < 7:
            return 1.0
        elif days_since_update < 30:
            return 0.8
        elif days_since_update < 90:
            return 0.6
        elif days_since_update < 180:
            return 0.4
        elif days_since_update < 365:
            return 0.2
        else:
            return 0.1

    def _score_popularity(self, agent: Agent) -> float:
        """Score popularity 0.0-1.0."""
        stars = agent.stars or 0

        if stars >= 1000:
            return 1.0
        elif stars >= 500:
            return 0.9
        elif stars >= 100:
            return 0.7
        elif stars >= 50:
            return 0.5
        elif stars >= 10:
            return 0.3
        elif stars >= 1:
            return 0.1
        else:
            return 0.0

    def _score_capability_depth(self, parsed: dict) -> float:
        """Score how specialized this agent is."""
        capabilities = parsed.get("capabilities", [])

        if len(capabilities) >= 5:
            return 0.8
        elif len(capabilities) >= 3:
            return 0.6
        elif len(capabilities) >= 1:
            return 0.4
        else:
            return 0.1


if __name__ == "__main__":
    """Run parser standalone for testing."""
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    parser = Parser()
    stats = parser.parse_pending(batch_size=10)
    print(f"Parse complete: {stats}")
