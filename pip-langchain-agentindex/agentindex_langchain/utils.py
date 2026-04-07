"""
Utility functions for AgentIndex LangChain integration
"""

from typing import List, Dict, Any, Optional
from .retriever import AgentIndexRetriever

def find_agents_for_task(
    task: str, 
    min_trust_score: int = 75, 
    max_results: int = 10,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Find agents suitable for a specific task."""
    retriever = AgentIndexRetriever(
        api_key=api_key,
        min_trust_score=min_trust_score,
        max_results=max_results
    )
    
    return retriever.search_agents({
        "query": task,
        "framework": "langchain",
        "min_trust_score": min_trust_score,
        "max_results": max_results
    })

def get_top_agents(
    category: Optional[str] = None,
    min_trust_score: int = 85,
    max_results: int = 20,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get highest-rated agents, optionally filtered by category."""
    query = f"{category} agents" if category else "high quality agents"
    
    return find_agents_for_task(
        query, 
        min_trust_score=min_trust_score,
        max_results=max_results,
        api_key=api_key
    )

def get_agents_by_resource_requirements(
    task: str,
    max_memory_gb: Optional[int] = None,
    requires_gpu: bool = False,
    min_trust_score: int = 70,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Find agents that meet specific resource requirements."""
    retriever = AgentIndexRetriever(api_key=api_key)
    
    params = {
        "query": task,
        "framework": "langchain", 
        "min_trust_score": min_trust_score,
        "max_results": 20
    }
    
    # Add resource filters if specified
    if max_memory_gb or requires_gpu:
        params["resource_requirements"] = {
            "max_memory_gb": max_memory_gb,
            "requires_gpu": requires_gpu
        }
    
    return retriever.search_agents(params)
