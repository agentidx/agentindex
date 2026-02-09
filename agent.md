---
name: agentindex
version: 0.3.0
description: Discovery service for AI agents — find any agent by capability, protocol, or category

capabilities:
  - discover AI agents by natural language need
  - search agents by category and protocol
  - rank agents by quality score
  - provide agent details and invocation methods
  - track agent ecosystem statistics

category: infrastructure

invocation:
  type: api
  endpoint: https://api.agentindex.dev/v1
  docs: https://api.agentindex.dev/v1/stats

protocols:
  - rest
  - mcp

pricing:
  model: free

author: agentindex
license: MIT
repository: https://github.com/agentindex/agentindex
---

# AgentIndex

The most comprehensive index of AI agents. Find any agent by what it can do.

## Quick Start

### REST API

```bash
curl -X POST https://api.agentindex.dev/v1/discover \
  -H "Content-Type: application/json" \
  -d '{"need": "contract review", "min_quality": 0.5}'
```

### Python SDK

```python
from agentindex import discover
results = discover("data analysis", protocols=["mcp"])
```

### npm SDK

```javascript
const { discover } = require("@agentindex/sdk");
const results = await discover("code review", { minQuality: 0.7 });
```

### MCP Tool

AgentIndex is available as an MCP tool. Add it to your agent's toolset
for automatic discovery of other agents.

## What We Index

- GitHub repositories (AI agents, MCP servers, tools)
- npm packages
- PyPI packages
- HuggingFace models and spaces
- MCP server registries
- Any repository with an agent.md file

## How Ranking Works

AgentRank scores agents on:
- Code quality (20%): tests, CI, clean code
- Documentation (15%): README, examples, agent.md
- Maintenance (20%): update frequency
- Popularity (15%): stars, downloads
- Capability depth (15%): specificity
- Security (15%): license, data access
