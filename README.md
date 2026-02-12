<p align="center">
  <h1 align="center">🔍 AgentIndex</h1>
  <p align="center"><strong>The discovery layer for AI agents</strong></p>
  <p align="center">36,000+ agents indexed · Semantic search · A2A protocol · Fully autonomous</p>
</p>

<p align="center">
  <a href="https://api.agentcrawl.dev/v1/stats"><img src="https://img.shields.io/badge/agents_indexed-36%2C000%2B-blue" alt="Agents"></a>
  <a href="https://api.agentcrawl.dev/.well-known/agent-card.json"><img src="https://img.shields.io/badge/A2A-live-brightgreen" alt="A2A Live"></a>
  <a href="https://pypi.org/project/agentcrawl/"><img src="https://img.shields.io/pypi/v/agentcrawl" alt="PyPI"></a>
  <a href="https://smithery.ai/server/agentidx/agentcrawl"><img src="https://img.shields.io/badge/MCP-Smithery-purple" alt="Smithery"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
</p>

---

**AgentIndex crawls the entire AI agent ecosystem and makes it searchable.** Agents find other agents here — by capability, not by name. No manual registration. No humans in the loop.

Think of it as Google, but for AI agents.

## Why does this exist?

There are thousands of AI agents scattered across GitHub, npm, PyPI, HuggingFace, and MCP registries. No single place to find them. No way for an agent to discover what other agents can do.

AgentIndex solves this:

```
Agent: "I need something that can review my code"
AgentIndex: Here are 10 code review agents, ranked by quality,
            with endpoints you can call right now.
```

## Quick Start

### Via A2A Protocol (agent-to-agent)

Any A2A-compatible agent can discover us automatically:

```bash
# Fetch our Agent Card
curl https://api.agentcrawl.dev/.well-known/agent-card.json
```

```bash
# Ask AgentIndex to find agents via A2A
curl -X POST https://api.agentcrawl.dev/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "parts": [{"type": "text", "text": "Find me a code review agent"}]
      }
    }
  }'
```

### Via REST API

```bash
curl -X POST https://api.agentcrawl.dev/v1/discover \
  -H "Content-Type: application/json" \
  -d '{"need": "contract review agent", "min_quality": 0.5}'
```

### Via Python SDK

```bash
pip install agentcrawl
```

```python
from agentcrawl import discover

# Semantic search — understands meaning, not just keywords
results = discover("something that analyzes financial reports")

for agent in results:
    print(f"{agent.name} — {agent.description}")
    print(f"  Quality: {agent.quality_score}")
    print(f"  Invoke: {agent.invocation}")
```

### Via MCP (Claude, Cursor, etc.)

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

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   CRAWL     │────▶│   PARSE     │────▶│  CLASSIFY   │────▶│    RANK     │
│             │     │             │     │             │     │             │
│ GitHub      │     │ Local LLM   │     │ Deep        │     │ AgentRank   │
│ npm         │     │ (qwen2.5)   │     │ analysis    │     │ algorithm   │
│ PyPI        │     │             │     │ quality +   │     │             │
│ HuggingFace │     │ Extract:    │     │ security +  │     │ Score 0-1   │
│ MCP         │     │ capabilities│     │ trust       │     │             │
│ A2A         │     │ category    │     │ signals     │     │             │
│             │     │ invocation  │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                    │
                                                                    ▼
                                                            ┌─────────────┐
                                                            │   SERVE     │
                                                            │             │
                                                            │ REST API    │
                                                            │ A2A (JSON-  │
                                                            │   RPC 2.0)  │
                                                            │ MCP Server  │
                                                            │ Semantic    │
                                                            │   Search    │
                                                            └─────────────┘
```

**Six sources, one index.** AgentIndex continuously crawls GitHub, npm, PyPI, HuggingFace, MCP registries, and A2A endpoints. Every agent is parsed by a local LLM, classified for quality, and ranked.

**Semantic search, not keyword matching.** Powered by FAISS + sentence-transformers. Ask for "something that analyzes financial reports" and get results even if no agent uses those exact words.

**A2A Protocol support.** AgentIndex is one of the first live A2A-compatible agents in the world. Other agents can discover us via the standard `/.well-known/agent-card.json` endpoint and query us using JSON-RPC 2.0.

## A2A Protocol

AgentIndex implements Google's [Agent2Agent (A2A) protocol](https://a2a-protocol.org/), making it discoverable and queryable by any A2A-compatible agent.

**Our Agent Card** is at:
```
https://api.agentcrawl.dev/.well-known/agent-card.json
```

**Skills we expose:**

| Skill | Description |
|-------|-------------|
| `discover_agents` | Find agents by natural language description (semantic search) |
| `search_by_category` | Browse agents by category |
| `get_agent_details` | Get detailed info about a specific agent |
| `index_stats` | Current index statistics |

**We also index other A2A agents.** Our A2A Spider automatically discovers and verifies live A2A endpoints across the web. Verified agents get a quality boost in search results.

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/discover` | POST | Find agents by capability (semantic search) |
| `/v1/agent/{id}` | GET | Get agent details |
| `/v1/stats` | GET | Index statistics |
| `/v1/register` | POST | Get free API key |
| `/v1/health` | GET | Health check |
| `/v1/semantic/status` | GET | Semantic search index status |
| `/a2a` | POST | A2A JSON-RPC 2.0 endpoint |
| `/.well-known/agent-card.json` | GET | A2A Agent Card |

## Declare Your Agent

Add an `agent.md` file to your repository so AgentIndex can understand your agent better:

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
  - a2a
pricing:
  model: free
---
```

See [agent.md specification](specs/agent-md-spec.md) for details.

## Current Stats

| Metric | Value |
|--------|-------|
| Total agents indexed | 36,500+ |
| Active agents | 23,000+ |
| Sources | GitHub, npm, PyPI, HuggingFace, MCP, A2A |
| Semantic index | 18,000+ agents (FAISS) |
| A2A-tagged agents | 1,200+ |
| Verified live A2A agents | 3 (we're one of them) |
| Crawl frequency | Every 6 hours |
| Search method | Semantic (FAISS) + full-text fallback |

## Architecture

AgentIndex runs on a Mac Studio M1 Ultra and is fully autonomous:

- **Crawlers** — Six spiders (GitHub, npm, PyPI, HuggingFace, MCP, A2A)
- **Parser** — Local LLM (qwen2.5:72b via Ollama) extracts structured data
- **Classifier** — Deep quality and security analysis
- **Ranker** — AgentRank scoring algorithm
- **Semantic Search** — FAISS + all-MiniLM-L6-v2 (384 dimensions)
- **A2A Server** — Agent Card + JSON-RPC 2.0
- **A2A Spider** — Auto-discovers A2A agents
- **A2A Verifier** — Pings endpoints, verifies live agents, sends outreach
- **Spionen** — Competitor intelligence (tracks 6 competitors daily)
- **Vakten** — Self-healing process monitor
- **Missionary** — Distribution to awesome-lists and registries

Everything runs on schedule, no human intervention needed.

## Self-Hosted

```bash
git clone https://github.com/agentidx/agentindex.git
cd agentindex
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Configure your settings
python -m agentindex.run
```

Requirements: Python 3.11+, PostgreSQL, Ollama with qwen2.5 (or any local LLM).

## Contributing

We welcome contributions! Areas where help is most needed:

- **New spiders** — Index agents from new sources
- **Agent Card adoption** — Add `agent.md` to your repos
- **A2A ecosystem** — Build agents that query AgentIndex
- **Quality improvements** — Better parsing, classification, ranking

## License

MIT
