"""
AgentIndex LangChain Integration
Discover and retrieve agents using semantic search
"""

from .retriever import AgentIndexRetriever
from .utils import find_agents_for_task, get_top_agents

__version__ = "1.0.0"
__all__ = ["AgentIndexRetriever", "find_agents_for_task", "get_top_agents"]
