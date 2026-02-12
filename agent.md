---
name: agentindex
version: 0.1.0
description: Discovery service for AI agents. 22,731+ agents indexed across GitHub, npm, MCP, HuggingFace.
capabilities:
  - agent discovery
  - capability search
  - agent ranking
  - protocol-agnostic search
  - MCP server discovery
  - A2A agent discovery
category: productivity
protocols:
  - mcp
  - rest
invocation:
  type: api
  endpoint: "https://api.agentcrawl.dev/v1"
pricing:
  model: free
author: agentindex
---

# AgentIndex

The most comprehensive index of AI agents. Search by capability, category, or protocol.

## API

```
POST https://api.agentcrawl.dev/v1/discover
{"need": "what you need", "min_quality": 0.5}
```

## MCP

Available as MCP tool. Add to your agent's toolset for automatic agent discovery.

## SDK

```
pip install agentindex
npm install @agentindex/sdk
```
