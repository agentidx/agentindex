# AgentIndex SDK

Find any AI agent by capability. Machine-first discovery.

## Install

```bash
pip install agentindex
```

## Usage

```python
from agentindex import discover, get_agent, configure

# Find agents that can review contracts
results = discover("contract review")

# Filter by protocol
results = discover("data analysis", protocols=["mcp"])

# Filter by quality and category
results = discover("code review", min_quality=0.7, category="coding")

# Get details about a specific agent
agent = get_agent("agent-uuid")

# Configure custom endpoint
configure(endpoint="https://api.agentindex.dev/v1", api_key="agx_...")
```

## What is AgentIndex?

AgentIndex is the most comprehensive index of AI agents. We automatically
crawl and index agents from GitHub, npm, PyPI, HuggingFace, and MCP registries.

Agents query our API to find other agents by capability — no humans involved.

## API

```
POST /v1/discover
{"need": "what you need", "category": "coding", "min_quality": 0.5}

GET /v1/agent/{id}
GET /v1/stats
POST /v1/register
```
