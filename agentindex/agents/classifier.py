"""
AgentIndex Classifier (Klassificerare)

Takes parsed agents and performs deeper analysis:
- Validates capabilities against actual code/docs
- Detects duplicates across sources
- Assesses trust and security signals
- Refines category and capability tags

Designed to use 72B model for best quality, but falls back
gracefully to 7B if the large model isn't available.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from ollama import Client
from agentindex.db.models import Agent, get_session
from sqlalchemy import select, func, text
import os

logger = logging.getLogger("agentindex.classifier")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL_LARGE = os.getenv("OLLAMA_MODEL_LARGE", "qwen2.5:7b")

CLASSIFY_PROMPT = """You are an expert AI agent evaluator. Analyze this agent deeply.

Agent name: {name}
Source: {source}
Category (from parser): {category}
Capabilities (from parser): {capabilities}
Description: {description}
Author: {author}
Stars: {stars}
Frameworks: {frameworks}
Protocols: {protocols}
Language: {language}
Last updated: {last_updated}

README excerpt:
{readme}

Respond with ONLY valid JSON:
{{
  "category_refined": "best category from: coding, research, content, legal, data, finance, marketing, design, devops, security, education, health, communication, productivity, infrastructure, other",
  "capabilities_refined": ["list", "of", "validated", "specific", "capabilities"],
  "tags_refined": ["specific", "searchable", "tags"],
  "trust_signals": {{
    "has_tests": true/false,
    "has_ci": true/false,
    "has_license": true/false,
    "has_examples": true/false,
    "active_maintenance": true/false,
    "clear_documentation": true/false,
    "known_author": true/false
  }},
  "security_assessment": {{
    "score": 0.0 to 1.0,
    "concerns": ["list any security concerns"],
    "requires_api_keys": true/false,
    "data_access_level": "none|read|write|admin"
  }},
  "duplicate_risk": {{
    "is_fork_or_clone": true/false,
    "similar_to": "name of similar agent if any, or null"
  }},
  "quality_override": null or 0.0-1.0,
  "recommendation": "index|deprioritize|remove"
}}

Be strict. Only validate capabilities that the README actually supports.
Remove vague capabilities. Be specific.
"""

DEDUP_PROMPT = """Compare these two agents and determine if they are duplicates.

Agent A:
- Name: {name_a}
- Source: {source_a}
- Description: {desc_a}
- Capabilities: {caps_a}
- Author: {author_a}

Agent B:
- Name: {name_b}
- Source: {source_b}
- Description: {desc_b}
- Capabilities: {caps_b}
- Author: {author_b}

Respond with ONLY valid JSON:
{{
  "is_duplicate": true/false,
  "confidence": 0.0 to 1.0,
  "relationship": "identical|fork|wrapper|related|different",
  "keep": "a" or "b" or "both",
  "reason": "brief explanation"
}}
"""


class Classifier:
    """
    Deep analysis of parsed agents using larger LLM model.
    Falls back to small model if large isn't available.
    """

    def __init__(self):
        self.client = Client(host=OLLAMA_BASE_URL)
        self.session = get_session()
        self.model = self._select_model()

    def _select_model(self) -> str:
        """Use model from env config. No auto-detection."""
        model = OLLAMA_MODEL_LARGE
        logger.info(f"Using model from config: {model}")
        return model

    def classify_pending(self, batch_size: int = 20) -> dict:
        """Classify agents that have been parsed but not yet classified."""
        stats = {"classified": 0, "deprioritized": 0, "removed": 0, "errors": 0}

        agents = self.session.execute(
            select(Agent)
            .where(Agent.crawl_status == "parsed")
            .order_by(Agent.quality_score.desc())
            .limit(batch_size)
        ).scalars().all()

        for agent in agents:
            try:
                result = self._classify_agent(agent)
                if result == "classified":
                    stats["classified"] += 1
                elif result == "deprioritized":
                    stats["deprioritized"] += 1
                elif result == "removed":
                    stats["removed"] += 1
            except Exception as e:
                logger.error(f"Error classifying {agent.name}: {e}")
                stats["errors"] += 1

        self.session.commit()
        logger.info(f"Classification batch complete: {stats}")
        return stats

    def _classify_agent(self, agent: Agent) -> str:
        """Classify a single agent."""
        metadata = agent.raw_metadata or {}

        prompt = CLASSIFY_PROMPT.format(
            name=agent.name,
            source=agent.source,
            category=agent.category or "unknown",
            capabilities=json.dumps(agent.capabilities or []),
            description=agent.description or "N/A",
            author=agent.author or "unknown",
            stars=agent.stars or 0,
            frameworks=", ".join(agent.frameworks or []),
            protocols=", ".join(agent.protocols or []),
            language=agent.language or "unknown",
            last_updated=agent.last_source_update.isoformat() if agent.last_source_update else "unknown",
            readme=(metadata.get("readme") or "N/A")[:3000],
        )

        try:
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
        except Exception as e:
            logger.error(f"Ollama error for {agent.name}: {e}")
            return "error"

        text = response["message"]["content"].strip()
        parsed = self._extract_json(text)

        if not parsed:
            logger.warning(f"Could not parse classifier response for {agent.name}")
            return "error"

        recommendation = parsed.get("recommendation", "index")

        if recommendation == "remove":
            agent.is_active = False
            agent.crawl_status = "removed"
            return "removed"

        if recommendation == "deprioritize":
            agent.quality_score = max(agent.quality_score * 0.5, 0.05)
            agent.crawl_status = "classified"
            return "deprioritized"

        # Apply refined data
        if parsed.get("category_refined"):
            agent.category = parsed["category_refined"]

        if parsed.get("capabilities_refined"):
            agent.capabilities = parsed["capabilities_refined"]

        if parsed.get("tags_refined"):
            agent.tags = list(set((agent.tags or []) + parsed["tags_refined"]))

        # Security score
        security = parsed.get("security_assessment", {})
        agent.security_score = security.get("score", agent.security_score)

        # Trust-based quality adjustment
        trust = parsed.get("trust_signals", {})
        trust_score = sum([
            0.15 if trust.get("has_tests") else 0,
            0.1 if trust.get("has_ci") else 0,
            0.1 if trust.get("has_license") else 0,
            0.15 if trust.get("has_examples") else 0,
            0.2 if trust.get("active_maintenance") else 0,
            0.15 if trust.get("clear_documentation") else 0,
            0.15 if trust.get("known_author") else 0,
        ])

        # Quality override from classifier
        quality_override = parsed.get("quality_override")
        if quality_override is not None:
            agent.quality_score = quality_override
        else:
            # Blend trust score into existing quality
            agent.quality_score = (agent.quality_score * 0.6) + (trust_score * 0.4)

        # Store classification metadata
        agent.raw_metadata = {
            **(agent.raw_metadata or {}),
            "classification": {
                "trust_signals": trust,
                "security": security,
                "duplicate_risk": parsed.get("duplicate_risk", {}),
                "classified_at": datetime.utcnow().isoformat(),
                "model_used": self.model,
            }
        }

        agent.crawl_status = "classified"
        return "classified"

    def deduplicate(self, batch_size: int = 50) -> dict:
        """Find and handle duplicate agents across sources."""
        stats = {"checked": 0, "duplicates_found": 0, "merged": 0}

        # Find agents with similar names
        agents = self.session.execute(
            select(Agent)
            .where(Agent.is_active == True)
            .order_by(Agent.quality_score.desc())
            .limit(500)
        ).scalars().all()

        # Group by normalized name
        name_groups = {}
        for agent in agents:
            normalized = agent.name.lower().replace("-", "").replace("_", "").replace(" ", "")
            if normalized not in name_groups:
                name_groups[normalized] = []
            name_groups[normalized].append(agent)

        # Check groups with multiple entries
        for name, group in name_groups.items():
            if len(group) < 2:
                continue

            stats["checked"] += 1

            # Compare each pair
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if stats["checked"] >= batch_size:
                        break

                    a, b = group[i], group[j]

                    # Quick check: same author = likely duplicate
                    if a.author and b.author and a.author.lower() == b.author.lower():
                        if a.source != b.source:
                            # Same project, different sources — keep highest quality
                            if a.quality_score >= b.quality_score:
                                b.is_active = False
                                b.crawl_status = "duplicate"
                            else:
                                a.is_active = False
                                a.crawl_status = "duplicate"
                            stats["duplicates_found"] += 1
                            stats["merged"] += 1
                            continue

                    # Use LLM for ambiguous cases (expensive, use sparingly)
                    if self._should_llm_dedup(a, b):
                        is_dup = self._llm_dedup_check(a, b)
                        if is_dup:
                            # Keep the one with higher quality
                            if a.quality_score >= b.quality_score:
                                b.is_active = False
                                b.crawl_status = "duplicate"
                            else:
                                a.is_active = False
                                a.crawl_status = "duplicate"
                            stats["duplicates_found"] += 1
                            stats["merged"] += 1

        self.session.commit()
        logger.info(f"Deduplication complete: {stats}")
        return stats

    def _should_llm_dedup(self, a: Agent, b: Agent) -> bool:
        """Decide if two agents need LLM-based dedup check."""
        # Same name, different source — worth checking
        if a.name.lower() == b.name.lower() and a.source != b.source:
            return True
        # Very similar descriptions
        if a.description and b.description:
            a_words = set(a.description.lower().split())
            b_words = set(b.description.lower().split())
            if len(a_words & b_words) > len(a_words | b_words) * 0.7:
                return True
        return False

    def _llm_dedup_check(self, a: Agent, b: Agent) -> bool:
        """Use LLM to check if two agents are duplicates."""
        prompt = DEDUP_PROMPT.format(
            name_a=a.name, source_a=a.source,
            desc_a=a.description or "N/A",
            caps_a=json.dumps(a.capabilities or []),
            author_a=a.author or "unknown",
            name_b=b.name, source_b=b.source,
            desc_b=b.description or "N/A",
            caps_b=json.dumps(b.capabilities or []),
            author_b=b.author or "unknown",
        )

        try:
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
            text = response["message"]["content"].strip()
            parsed = self._extract_json(text)
            if parsed and parsed.get("is_duplicate") and parsed.get("confidence", 0) > 0.7:
                return True
        except Exception as e:
            logger.error(f"Dedup LLM error: {e}")

        return False

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from LLM response."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        if "```json" in text:
            try:
                return json.loads(text.split("```json")[1].split("```")[0].strip())
            except (IndexError, json.JSONDecodeError):
                pass
        if "```" in text:
            try:
                return json.loads(text.split("```")[1].split("```")[0].strip())
            except (IndexError, json.JSONDecodeError):
                pass
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            pass
        return None


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    classifier = Classifier()
    stats = classifier.classify_pending(batch_size=5)
    print(f"Classification: {stats}")
    dedup = classifier.deduplicate(batch_size=10)
    print(f"Dedup: {dedup}")
