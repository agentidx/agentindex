"""
nerq — Trust verification for AI agents.

Usage:
    import nerq

    # Check trust
    result = nerq.preflight("langchain")
    print(result["target_trust"])  # 87.6

    # Find best tool for a task
    tool = nerq.resolve("search github repos")
    print(tool["name"])  # github/github-mcp-server

    # Search agents
    agents = nerq.search("code review", min_trust=70)
"""

__version__ = "1.3.0"

from nerq.resolve import resolve
from nerq.preflight import preflight
from nerq.search import search
