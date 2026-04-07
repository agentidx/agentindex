# Show HN Draft — Final Version

**Title:** Show HN: One MCP server that gives your AI agent access to 25,000 tools

**URL:** https://nerq.ai/gateway

**Text:**

We built nerq-gateway — an MCP server that acts as a gateway to 25,000+ other MCP servers.

Instead of configuring each MCP server manually in Claude/Cursor, you add one line:

    "nerq": {"command": "npx", "args": ["-y", "nerq-gateway"]}

Then ask your AI for anything — "search my GitHub repos", "query my database", "send a Slack message" — and the gateway finds, trust-verifies, and connects the right MCP server automatically.

Under the hood it uses our trust scoring engine (nerq.ai) which indexes 204K AI agents from 12 registries and scores them on security (CVEs), licenses, maintenance, and compatibility. Every tool recommendation is trust-verified before use.

Interesting finding: ChatGPT's crawler discovered our trust API on its own via .well-known/agent.json and now makes ~1,400 trust checks/day — doing "comparison shopping" across groups of agents before recommending them.

Free, open API, no auth:

    curl https://nerq.ai/v1/resolve?task=search+github
    npx nerq-mcp-hub search "database"
    pip install agent-security && agent-security scan requirements.txt

Built by one person using Claude Code. 42 autonomous systems run the pipeline 24/7.

Happy to answer questions about the architecture, trust scoring methodology, or AI bot behavior patterns.

---

**Posting instructions:**
1. Go to https://news.ycombinator.com/submit
2. Title: "Show HN: One MCP server that gives your AI agent access to 25,000 tools"
3. URL: https://nerq.ai/gateway
4. Text: (copy from above, HN doesn't support markdown so plain text)
5. Best time: Tuesday or Wednesday, 9-10am ET
