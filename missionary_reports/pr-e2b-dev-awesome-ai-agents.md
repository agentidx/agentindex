# PR for e2b-dev/awesome-ai-agents

**Title:** Add AgentIndex - AI agent discovery platform

## AgentIndex

**Discovery platform for AI agents.** Find any AI agent by capability - search 23,080+ indexed agents across 4 sources.

- **API:** https://api.agentcrawl.dev
- **MCP Server:** [Smithery](https://smithery.ai/server/agentidx/agentcrawl)
- **SDK:** `pip install agentcrawl` | `npm install @agentidx/sdk`
- **GitHub:** https://github.com/agentidx/agentindex

### What it does
AgentIndex crawls and indexes all publicly available AI agents (GitHub, npm, MCP, HuggingFace) so that agents can automatically discover and hire other agents.

### Categories
coding, devops, infrastructure, finance, communication, research, agent framework, data, security, AI assistant

### Usage
```python
from agentcrawl import discover
agents = discover('code review', min_quality=0.7)
```
