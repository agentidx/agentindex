"""
Enhanced CrewAI crew building with integrated trust gating.
"""

from typing import List, Dict, Any, Optional
from crewai import Agent, Crew, Task
from .discovery import NerqCrewBuilder
from .trust_gate import trust_gate_crew


class EnhancedCrewBuilder(NerqCrewBuilder):
    """Enhanced crew builder with hierarchical crews and automatic trust gating."""

    def build_trusted_crew(
        self,
        task_description: str,
        roles: List[str],
        min_trust_score: int = 80,
        gate_min_trust: float = 60,
        caller: Optional[str] = None,
    ) -> Optional[Crew]:
        """Build a crew and automatically apply trust gating to all tool calls.

        Args:
            task_description: What the crew should accomplish.
            roles: List of role names to discover agents for.
            min_trust_score: Minimum trust score for agent discovery.
            gate_min_trust: Minimum trust score for runtime tool gating.
            caller: Optional caller name for interaction risk.

        Returns:
            A trust-gated Crew, or None if no agents found.
        """
        crew = self.build_crew(task_description, roles, min_trust_score)
        if crew is None:
            return None
        return trust_gate_crew(crew, min_trust=gate_min_trust, caller=caller)

    def build_hierarchical_crew(
        self,
        project: str,
        team_lead_role: str,
        specialist_roles: List[str],
        min_trust_score: int = 85,
    ) -> Optional[Crew]:
        """Build a hierarchical crew with a team lead and specialists."""

        lead_agents = self.discover_agents(
            [f"{project} {team_lead_role} lead"], min_trust_score, 1
        )
        if not lead_agents:
            return None

        lead_agent = Agent(
            role=f"Team Lead - {team_lead_role}",
            goal=f"Lead the team to successfully complete: {project}",
            backstory=(
                f"Experienced team lead with "
                f"{lead_agents[0].get('trust_score', 0)}/100 trust score"
            ),
            verbose=True,
            allow_delegation=True,
            max_execution_time=300,
        )

        specialist_agents = [lead_agent]

        for role in specialist_roles:
            agents = self.discover_agents(
                [f"{project} {role} specialist"], min_trust_score, 1
            )
            if agents:
                specialist = Agent(
                    role=f"{role} Specialist",
                    goal=f"Provide expert {role} services for: {project}",
                    backstory=(
                        f"Specialist with "
                        f"{agents[0].get('trust_score', 0)}/100 trust score"
                    ),
                    verbose=True,
                    allow_delegation=False,
                )
                specialist_agents.append(specialist)

        lead_task = Task(
            description=f"Coordinate team to complete: {project}",
            agent=lead_agent,
        )

        crew = Crew(
            agents=specialist_agents,
            tasks=[lead_task],
            verbose=True,
            process="hierarchical",
            manager_llm="gpt-4",
        )

        return crew

    def optimize_crew_for_budget(
        self,
        task: str,
        max_agents: int,
        min_trust_score: int = 70,
    ) -> Optional[Crew]:
        """Build cost-optimized crew within agent limit."""

        all_agents = self.discover_agents([task], min_trust_score, max_results=50)

        if len(all_agents) <= max_agents:
            roles = [f"agent_{i + 1}" for i in range(len(all_agents))]
            return self.build_crew(task, roles, min_trust_score)

        top_agents = sorted(
            all_agents, key=lambda a: a.get("trust_score", 0), reverse=True
        )[:max_agents]

        crew_agents = []
        for i, agent_data in enumerate(top_agents):
            agent = Agent(
                role=f"Specialist {i + 1}",
                goal=f"Contribute expertise to: {task}",
                backstory=(
                    f"High-performance agent "
                    f"(Trust Score: {agent_data.get('trust_score', 0)}/100)"
                ),
                verbose=True,
            )
            crew_agents.append(agent)

        main_task = Task(description=task, agent=crew_agents[0])

        return Crew(
            agents=crew_agents,
            tasks=[main_task],
            verbose=True,
        )
