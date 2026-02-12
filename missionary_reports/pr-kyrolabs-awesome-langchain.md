# PR for kyrolabs/awesome-langchain

**Title:** Add AgentIndex - agent discovery for LangChain projects

## AgentIndex

Discovery API for finding AI agents by capability. Index of 23,080+ agents.

- **API:** https://api.agentcrawl.dev
- **SDK:** `pip install agentcrawl`
- **MCP Server:** [Smithery](https://smithery.ai/server/agentidx/agentcrawl)
- **GitHub:** https://github.com/agentidx/agentindex

```python
from agentcrawl import discover
agents = discover('data analysis agent', protocols=['rest'])
```
