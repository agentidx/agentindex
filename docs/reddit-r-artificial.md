# Reddit Post Draft — r/artificial

**Subreddit:** r/artificial or r/AItools

**Title:** We built a "Google for AI agents" — finds the best tool for any task in milliseconds

**Body:**

We built Nerq (nerq.ai) — a search engine for AI agents that indexes 204K+ agents, tools, and MCP servers.

The key feature is the **Resolve API**: describe what you need in plain English, and it returns the best trust-verified tool with install instructions.

```
curl "https://nerq.ai/v1/resolve?task=search+github+repos"
# Returns: github/github-mcp-server (Trust: 83, Grade: A)
# With: install instructions, alternatives, trust breakdown
```

**Why this matters:** AI agents are increasingly autonomous. They discover and use tools without human oversight. Without trust verification, an agent might use an abandoned tool with known CVEs, or a tool with an incompatible license.

Nerq scores every agent on:
- Security (known CVEs)
- License compliance
- Maintenance activity
- Popularity & community
- Ecosystem compatibility

**Try it:**
- Search: nerq.ai/discover
- Trust check: `curl nerq.ai/v1/preflight?target=langchain`
- Find tools: `curl nerq.ai/v1/resolve?task=code+review`
- Scan deps: `pip install agent-security && agent-security scan requirements.txt`

Free API, no auth. Built by one person + Claude Code.

---

**Posting instructions:**
1. Post to r/artificial (or r/AItools if r/artificial doesn't allow projects)
2. Best time: Tuesday-Thursday
3. Cross-post to r/AItools if separate sub
