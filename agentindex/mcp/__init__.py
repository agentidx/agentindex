"""Nerq MCP tool extensions.

This package hosts modular MCP tool definitions that extend the Nerq
MCP stdio server (``agentindex.mcp_server_v2``). The v2 server imports
``TOOLS`` and ``TOOL_HANDLERS`` from :mod:`agentindex.mcp.tools_v3` and
appends them to its own registries at process start, so clients see a
single flat tools list.

All tools in this package read through ``smedjan.sources`` (Nerq RO
replica) so they never write and remain safe to expose to any MCP
client.
"""

from agentindex.mcp.tools_v3 import TOOLS, TOOL_HANDLERS

__all__ = ["TOOLS", "TOOL_HANDLERS"]
