"""
AgentIndex CrewAI Integration
Discover and build crews with agents from AgentIndex
"""

from .discovery import discover_crewai_agents, build_crew_from_discovery
from .crew_builder import AgentIndexCrewBuilder

__version__ = "1.0.0"
__all__ = ["discover_crewai_agents", "build_crew_from_discovery", "AgentIndexCrewBuilder"]
