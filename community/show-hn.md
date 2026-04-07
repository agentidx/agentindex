# Show HN: Nerq — Trust scores for 204K AI agents (free API, MCP server, GitHub Action)

**Title**: Show HN: Nerq – Trust scores for 204K AI agents (free API, MCP server, GitHub Action)

**URL**: https://nerq.ai

**Text**:

Hi HN,

I built Nerq (https://nerq.ai) — an independent trust and compliance database for AI agents.

**What it does**: Nerq indexes 204,000+ AI agents and tools from GitHub, npm, PyPI, HuggingFace, and MCP registries. Each gets a Trust Score (0-100) computed across 6 dimensions: Code Quality, Community, Compliance, Operational Health, Security, and External Validation.

**Why**: As AI agents proliferate, teams need a way to verify which ones are safe to use. Is this MCP server maintained? Does this LangChain tool have known CVEs? Is this agent's license compatible with my project?

**How to use it**:

- API (free, no auth): `curl nerq.ai/v1/preflight?target=langchain`
- CLI: `pip install nerq && nerq check crewai`
- GitHub Action: `uses: nerq-ai/trust-check-action@v1`
- MCP Server: native trust verification for agent-to-agent workflows

**Interesting finding**: ChatGPT discovered our API through our `llms.txt` file and now makes 1,400+ trust checks daily — autonomously. No integration was arranged by humans.

**Technical stack**: FastAPI, PostgreSQL (4.98M assets), FAISS semantic search, SQLite for enrichment. Deployed on a Mac Mini with Cloudflare Tunnel.

**What's free**: Everything. The API is keyless. We want trust scores to be infrastructure, not a product.

Open to feedback. What trust signals would you add?
