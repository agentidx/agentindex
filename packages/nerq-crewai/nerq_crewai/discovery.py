"""
CrewAI agent discovery using Nerq trust index.
"""

import requests
from typing import List, Dict, Any, Optional
from crewai import Agent, Crew, Task


class NerqCrewBuilder:
    """Build CrewAI crews using Nerq discovery and trust verification."""

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://nerq.ai/v1"):
        self.api_key = api_key
        self.base_url = base_url

    def discover_agents(
        self,
        capabilities: List[str],
        min_trust_score: int = 75,
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """Discover agents suitable for CrewAI based on capabilities."""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            query = " ".join(capabilities) + " crewai compatible"

            response = requests.post(
                f"{self.base_url}/search",
                json={
                    "query": query,
                    "filters": {
                        "framework": "crewai",
                        "min_trust_score": min_trust_score,
                        "max_results": max_results,
                    },
                },
                headers=headers,
                timeout=10,
            )

            response.raise_for_status()
            return response.json().get("agents", [])

        except Exception as e:
            print(f"Agent discovery failed: {e}")
            return []

    def discover_trusted_tools(
        self,
        category: str,
        min_trust: int = 70,
    ) -> List[Dict[str, Any]]:
        """Discover trusted tools in a category via the Nerq benchmark endpoint.

        Args:
            category: Tool category to search (e.g. "code-generation", "web-search").
            min_trust: Minimum trust score to include (default 70).

        Returns:
            List of tool dicts with trust metadata.
        """
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            response = requests.get(
                f"{self.base_url}/agent/benchmark/{category}",
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            tools = response.json().get("agents", [])
            return [t for t in tools if t.get("trust_score", 0) >= min_trust]

        except Exception as e:
            print(f"Tool discovery failed: {e}")
            return []

    def build_crew(
        self,
        task_description: str,
        roles: List[str],
        min_trust_score: int = 80,
    ) -> Optional[Crew]:
        """Build a CrewAI crew for a specific task."""
        try:
            crew_agents = []

            for role in roles:
                query = f"{task_description} {role}"
                agents = self.discover_agents([query], min_trust_score, max_results=3)

                if agents:
                    best_agent = max(agents, key=lambda a: a.get("trust_score", 0))

                    crew_agent = Agent(
                        role=role,
                        goal=f"Execute {role} tasks for: {task_description}",
                        backstory=(
                            f"Expert {role} agent with "
                            f"{best_agent.get('trust_score', 0)}/100 trust score"
                        ),
                        verbose=True,
                        allow_delegation=True,
                    )

                    crew_agent.nerq_id = best_agent["id"]
                    crew_agent.nerq_trust_score = best_agent.get("trust_score", 0)
                    crew_agent.nerq_repository = best_agent.get("repository_url", "")

                    crew_agents.append(crew_agent)

            if not crew_agents:
                print("No suitable agents found for the specified roles")
                return None

            task = Task(
                description=task_description,
                agent=crew_agents[0],
            )

            crew = Crew(
                agents=crew_agents,
                tasks=[task],
                verbose=True,
            )

            return crew

        except Exception as e:
            print(f"Crew building failed: {e}")
            return None

    def get_recommended_crew_composition(
        self,
        project_type: str,
        complexity: str = "medium",
    ) -> Dict[str, List[str]]:
        """Get recommended crew composition for common project types."""

        compositions = {
            "content_creation": {
                "simple": ["writer", "editor"],
                "medium": ["researcher", "writer", "editor"],
                "complex": ["researcher", "writer", "editor", "seo_specialist", "reviewer"],
            },
            "software_development": {
                "simple": ["developer", "tester"],
                "medium": ["analyst", "developer", "tester"],
                "complex": ["analyst", "architect", "developer", "tester", "reviewer", "devops"],
            },
            "data_analysis": {
                "simple": ["analyst", "reporter"],
                "medium": ["data_collector", "analyst", "reporter"],
                "complex": ["data_collector", "data_cleaner", "analyst", "ml_engineer", "reporter"],
            },
            "customer_service": {
                "simple": ["support_agent", "escalation_handler"],
                "medium": ["initial_responder", "support_agent", "escalation_handler"],
                "complex": [
                    "triage_agent",
                    "support_agent",
                    "technical_specialist",
                    "escalation_handler",
                    "feedback_collector",
                ],
            },
        }

        return compositions.get(project_type, {}).get(complexity, ["generalist"])


# Convenience functions


def discover_crewai_agents(
    capability: str,
    min_trust_score: int = 75,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Discover CrewAI-compatible agents for a specific capability."""
    builder = NerqCrewBuilder(api_key=api_key)
    return builder.discover_agents([capability], min_trust_score)


def build_crew_from_discovery(
    task: str,
    roles: List[str],
    min_trust_score: int = 80,
    api_key: Optional[str] = None,
) -> Optional[Crew]:
    """Build a complete crew using Nerq discovery."""
    builder = NerqCrewBuilder(api_key=api_key)
    return builder.build_crew(task, roles, min_trust_score)
