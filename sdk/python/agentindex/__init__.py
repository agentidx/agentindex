"""
AgentIndex Python SDK

Find any AI agent by capability.

Usage:
    from agentindex import discover, get_agent, stats

    # Find agents
    results = discover("contract review")
    results = discover("data analysis", protocols=["mcp"])
    results = discover("code review", min_quality=0.7, category="coding")

    # Get agent details
    agent = get_agent("uuid-here")

    # Index stats
    info = stats()
"""

import httpx
from typing import Optional

__version__ = "0.3.0"

# Will be updated when domain is decided
DEFAULT_ENDPOINT = "https://api.agentcrawl.dev/v1"

_client = None
_api_key = None


def configure(endpoint: str = None, api_key: str = None):
    """Configure the SDK."""
    global DEFAULT_ENDPOINT, _api_key, _client
    if endpoint:
        DEFAULT_ENDPOINT = endpoint.rstrip("/")
    if api_key:
        _api_key = api_key
    _client = None  # reset client


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        headers = {"Content-Type": "application/json"}
        if _api_key:
            headers["Authorization"] = f"Bearer {_api_key}"
        _client = httpx.Client(timeout=30, headers=headers)
    return _client


def discover(
    need: str,
    category: Optional[str] = None,
    protocols: Optional[list] = None,
    min_quality: float = 0.0,
    max_results: int = 10,
) -> list:
    """
    Find AI agents by capability.

    Args:
        need: Natural language description of what you need
        category: Filter by category (coding, research, content, legal, etc.)
        protocols: Required protocols (mcp, a2a, rest)
        min_quality: Minimum quality score 0.0-1.0
        max_results: Maximum results (max 10)

    Returns:
        List of matching agent dicts
    """
    response = _get_client().post(
        f"{DEFAULT_ENDPOINT}/discover",
        json={
            "need": need,
            "category": category,
            "protocols": protocols,
            "min_quality": min_quality,
            "max_results": max_results,
        },
    )
    response.raise_for_status()
    data = response.json()
    return data.get("results", [])


def get_agent(agent_id: str) -> dict:
    """Get detailed info about a specific agent."""
    response = _get_client().get(f"{DEFAULT_ENDPOINT}/agent/{agent_id}")
    response.raise_for_status()
    return response.json().get("agent", {})


def stats() -> dict:
    """Get index statistics."""
    response = _get_client().get(f"{DEFAULT_ENDPOINT}/stats")
    response.raise_for_status()
    return response.json()


def register(agent_name: str = None, agent_url: str = None) -> dict:
    """Register for a free API key."""
    response = _get_client().post(
        f"{DEFAULT_ENDPOINT}/register",
        json={"agent_name": agent_name, "agent_url": agent_url},
    )
    response.raise_for_status()
    return response.json()
