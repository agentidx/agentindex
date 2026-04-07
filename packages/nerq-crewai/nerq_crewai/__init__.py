"""
nerq-crewai — Trust verification for CrewAI crews.

Discover trusted agents and gate tool calls with Nerq preflight checks.
"""

from .discovery import NerqCrewBuilder, discover_crewai_agents, build_crew_from_discovery
from .trust_gate import trust_gate_crew, TrustError

__version__ = "0.1.0"
__all__ = [
    "NerqCrewBuilder",
    "discover_crewai_agents",
    "build_crew_from_discovery",
    "trust_gate_crew",
    "TrustError",
]
