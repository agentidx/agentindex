# Reddit r/langchain Post

**Title:** We index 204K AI agents and 25K MCP servers with trust scores — free API for agent-to-agent trust checks

**Body:**

We've been building an index of the AI agent ecosystem. Currently tracking 5M+ AI assets:
- 204K agents & tools
- 25K MCP servers
- 4.7M models & datasets

Each gets a trust score (0–100) based on security, compliance, maintenance, popularity, and ecosystem signals. Think of it as a credit score for AI tools.

**Why this matters for LangChain devs:**

When your agent dynamically selects tools or communicates with other agents, you have no way to know if that tool is abandoned, has known vulnerabilities, or violates regulations in your jurisdiction. We built a preflight check:

```
GET https://nerq.ai/v1/preflight?target=some-tool&caller=my-agent
→ {"recommendation": "PROCEED", "target_trust": 72, ...}
```

**Other endpoints (all free, no auth):**
- `/v1/agent/kya/{name}` — Know Your Agent due diligence
- `/v1/agent/search?q=...&min_trust=50` — search with trust filters
- `/v1/agent/benchmark/{category}` — top 20 in each category
- `/badge/{name}` — SVG trust badge for READMEs

We also have a crypto risk API (ZARQ) that does Moody's-style ratings for 15K tokens. Just shipped a Vitality Score with backtested crash prediction (p < 0.001).

nerq.ai — search and explore
nerq.ai/nerq/docs — API docs

Happy to answer questions. What would make this more useful for your projects?
