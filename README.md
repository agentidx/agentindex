<p align="center">
  <h1 align="center">🔍 AgentIndex</h1>
  <p align="center"><strong>Find any AI agent, instantly.</strong></p>
</p>

<p align="center">
  <a href="https://api.agentcrawl.dev/v1/stats"><img src="https://img.shields.io/badge/agents-36%2C000%2B-blue" alt="Agents"></a>
  <a href="https://api.agentcrawl.dev/.well-known/agent-card.json"><img src="https://img.shields.io/badge/A2A-live-brightgreen" alt="A2A"></a>
  <a href="https://pypi.org/project/agentcrawl/"><img src="https://img.shields.io/pypi/v/agentcrawl" alt="PyPI"></a>
  <a href="https://smithery.ai/server/agentidx/agentcrawl"><img src="https://img.shields.io/badge/MCP-Smithery-purple" alt="Smithery"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
</p>

---

AgentIndex indexes 36,000+ AI agents from across the ecosystem. Describe what you need, get back agents you can call — ranked by quality, with invocation details.

## A2A Protocol
```bash
cat > ~/agentindex/README.md << 'EOF'
<p align="center">
  <h1 align="center">🔍 AgentIndex</h1>
  <p align="center"><strong>Find any AI agent, instantly.</strong></p>
</p>

<p align="center">
  <a href="https://api.agentcrawl.dev/v1/stats"><img src="https://img.shields.io/badge/agents-36%2C000%2B-blue" alt="Agents"></a>
  <a href="https://api.agentcrawl.dev/.well-known/agent-card.json"><img src="https://img.shields.io/badge/A2A-live-brightgreen" alt="A2A"></a>
  <a href="https://pypi.org/project/agentcrawl/"><img src="https://img.shields.io/pypi/v/agentcrawl" alt="PyPI"></a>
  <a href="https://smithery.ai/server/agentidx/agentcrawl"><img src="https://img.shields.io/badge/MCP-Smithery-purple" alt="Smithery"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
</p>

---

AgentIndex indexes 36,000+ AI agents from across the ecosystem. Describe what you need, get back agents you can call — ranked by quality, with invocation details.

## A2A Protocol
```bash
curl https://api.agentcrawl.dev/.well-known/agent-card.json
```
```bash
curl -X POST https://api.agentcrawl.dev/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", "id": "1", "method": "message/send",
    "params": {"message": {"parts": [{"type": "text", "text": "Find a code review agent"}]}}
  }'
```

## REST API
```bash
curl -X POST https://api.agentcrawl.dev/v1/discover \
  -H "Content-Type: application/json" \
  -d '{"need": "financial data analysis", "min_quality": 0.5}'
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/discover` | POST | Find agents by capability |
| `/v1/agent/{id}` | GET | Agent details |
| `/v1/stats` | GET | Index statistics |
| `/a2a` | POST | A2A JSON-RPC 2.0 |
| `/.well-known/agent-card.json` | GET | A2A Agent Card |

## Python
```bash
pip install agentcrawl
```
```python
from agentcrawl import discover

results = discover("something that analyzes financial reports")
for agent in results:
    print(f"{agent.name} — {agent.quality_score}")
```

## MCP
```json
{
  "agentindex": {
    "command": "python",
    "args": ["-m", "agentindex.mcp_server"]
  }
}
```

Or via [Smithery](https://smithery.ai/server/agentidx/agentcrawl):
```bash
npx @smithery/cli install agentidx/agentcrawl
```

## List Your Agent

Add `agent.md` to your repo:
```yaml
---
name: your-agent
description: What your agent does
capabilities: [thing-1, thing-2]
category: coding
protocols: [mcp, a2a]
invocation:
  type: mcp
  install: "npm install your-agent"
---
```

## License

MIT
