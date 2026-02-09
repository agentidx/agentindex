# AgentIndex

The most comprehensive index of AI agents. Machine-first discovery.

## What is this?

AgentIndex crawls and indexes AI agents from across the ecosystem — GitHub, npm, PyPI, HuggingFace, MCP registries — and makes them discoverable via API.

Agents query AgentIndex to find other agents by capability. No humans required.

## Quick Start

### API

```bash
curl -X POST https://api.agentindex.dev/v1/discover \
  -H "Content-Type: application/json" \
  -d '{"need": "contract review", "min_quality": 0.5}'
```

### Python

```bash
pip install agentindex
```

```python
from agentindex import discover

results = discover("data analysis", protocols=["mcp"])
```

### JavaScript

```bash
npm install @agentindex/sdk
```

```javascript
const { discover } = require("@agentindex/sdk");
const results = await discover("code review", { minQuality: 0.7 });
```

### MCP Tool

Add AgentIndex to your MCP config:

```json
{
  "agentindex": {
    "command": "python",
    "args": ["-m", "agentindex.mcp_server"]
  }
}
```

## How It Works

1. **Crawl** — Spiders continuously index agents from GitHub, npm, PyPI, HuggingFace, MCP registries
2. **Parse** — Local LLM extracts capabilities, categories, and invocation methods
3. **Classify** — Deep analysis validates quality, security, and trust signals
4. **Rank** — AgentRank algorithm scores agents nightly
5. **Serve** — Discovery API returns best matches for any query

## agent.md

Publish an `agent.md` file in your repository to declare your agent's capabilities:

```yaml
---
name: your-agent
version: 1.0.0
description: What your agent does
capabilities:
  - specific thing it can do
  - another thing
category: coding
invocation:
  type: mcp
  install: "npm install your-agent"
protocols:
  - mcp
pricing:
  model: free
---
```

See [agent.md specification](specs/agent-md-spec.md) for full details.

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/discover` | POST | Find agents by capability |
| `/v1/agent/{id}` | GET | Get agent details |
| `/v1/stats` | GET | Index statistics |
| `/v1/register` | POST | Get free API key |
| `/v1/health` | GET | Health check |

## License

MIT
