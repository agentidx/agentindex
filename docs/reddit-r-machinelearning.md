# Reddit Post Draft — r/MachineLearning

**Subreddit:** r/MachineLearning
**Flair:** [Project]

**Title:** We scanned 204K AI agents for vulnerabilities. 75% are D-grade. Here's the data.

**Body:**

We built Nerq (nerq.ai) — a trust scoring engine that indexes 204K AI agents, tools, and MCP servers from 12 registries (GitHub, npm, PyPI, HuggingFace, Docker Hub, Smithery, etc.).

Each agent gets a 0-100 trust score based on 5 pillars: Security (CVEs), License Compliance, Maintenance Activity, Popularity, and Ecosystem Health.

**Key findings from indexing 204K agents:**

- 75% score below 60 (D-grade or worse)
- Only 18K agents (8.8%) meet the "verified" threshold of 70+
- 49 known CVEs detected across indexed agents
- 35% have no license file at all
- Average time since last update: 127 days

**The Ecosystem Trust Index** currently sits at 64.11/100 — meaning the average agent you'd pick at random has mediocre trust.

**What we built with this data:**

1. **Preflight API** — check any agent's trust score in one call: `curl nerq.ai/v1/preflight?target=langchain`
2. **Resolve API** — find the best tool for any task, trust-verified: `curl nerq.ai/v1/resolve?task=code+review`
3. **agent-security** — scan your requirements.txt for trust issues: `pip install agent-security && agent-security scan requirements.txt`

Free, open API. No auth required.

Interesting aside: ChatGPT's crawler discovered our API via .well-known/agent.json and now makes ~1,400 trust checks/day autonomously.

Paper on methodology: nerq.ai/methodology

---

**Posting instructions:**
1. Post to r/MachineLearning with [Project] flair
2. Best time: Monday-Wednesday, 10am-1pm ET
3. Engage with comments for first 2 hours
