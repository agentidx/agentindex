# Distribution Content - Ready for Launch

## Reddit r/MachineLearning

**Title:** AgentIndex: Semantic Search for 40,000+ AI Agents (REST/MCP/A2A)

**Post:**
Just launched AgentIndex - a discovery platform for AI agents across multiple protocols. Instead of searching GitHub, npm, and PyPI separately, you get semantic search + trust scoring across 40k+ agents.

**The Problem:** Developers spend hours finding the right AI agent. They're scattered across GitHub, npm, PyPI, HuggingFace registries, and MCP servers.

**The Solution:** 
- Unified semantic search across all agent sources
- Trust scoring system (6-component: freshness, stability, popularity, maintenance, security, community)  
- Framework integrations: LangChain, CrewAI, AutoGen, etc.
- API: REST, SDKs (Python/Node), or browser

**Try it:** agentcrawl.dev or `pip install agentcrawl` / `npm install @agentidx/sdk`

---

## Reddit r/LocalLLaMA

**Title:** AgentIndex Uses Local LLMs for 60-80% Cost Optimization (Ollama + Semantic Search)

**Post:**
Built AgentIndex with aggressive local-first optimization: All code generation, data processing, and classification runs on local LLMs (qwen, llama3, codellama). Claude API is reserved for high-complexity reasoning only.

**Why This Matters:**
- $10 USD daily budget for infrastructure
- Smart router: Sends simple tasks to Ollama (ZERO cost), complex tasks to Claude
- Sub-100ms search responses with Redis caching
- Scaling: 40k+ agents without breaking the budget

**Result:** We get production-quality development while staying within strict budget constraints. Local-first isn't just cheaper - it's more sustainable.

**Technical:** If you're running Ollama locally, you can now use it to power agent discovery while respecting local-first principles.

agentcrawl.dev for details

---

## Glama Registry Entry

**Title:** AgentIndex

**Category:** AI Tools, Agent Discovery, Developer Tools

**Short Description (50 words):**
Unified semantic search platform for 40,000+ AI agents from GitHub, npm, PyPI, and MCP registries. Discover the right agent for your project with trust scoring and framework integrations.

**Long Description (300+ words):**

AgentIndex solves a critical problem in the AI ecosystem: **agent discovery at scale**.

**The Problem:**
With thousands of new AI agents being created daily, developers struggle to find the right tool. Agents are scattered across GitHub, npm, PyPI, HuggingFace, and dozens of MCP registries. Building a multi-framework team (LangChain + CrewAI + AutoGen) requires searching multiple databases.

**The Solution:**
AgentIndex provides:

1. **Unified Discovery** - One search across 40,000+ agents from all major sources
2. **Smart Ranking** - Trust scoring (0-100) based on 6 factors: freshness, stability, popularity, maintenance, security, community activity
3. **Framework Integration** - Direct integration with LangChain, CrewAI, and AutoGen
4. **Performance** - Sub-100ms search with Redis caching
5. **Developer-Friendly** - REST API, Python SDK, Node.js SDK, or web interface

**Use Cases:**
- Finding agents for specific tasks (data processing, code generation, reasoning)
- Building AI teams across multiple frameworks
- Quality filtering: Only see high-trust agents
- Cross-protocol discovery: REST agents + MCP servers in one place

**Technology:**
- Semantic search with FAISS vector database
- Real-time crawling from GitHub, npm, PyPI
- A2A protocol support for agent-to-agent discovery
- PostgreSQL for metadata, Redis for caching
- FastAPI backend with sub-100ms response times

**Getting Started:**
- Web: agentcrawl.dev
- Python: `pip install agentcrawl`
- Node.js: `npm install @agentidx/sdk`
- API: api.agentcrawl.dev/docs

---

## PulseMCP Registry Entry

**Server Name:** AgentIndex MCP Server

**Description:**
Semantic search and discovery for 40,000+ AI agents from GitHub, npm, PyPI, HuggingFace, and MCP registries. Provides trust scoring, metadata filtering, and framework integration support.

**Capabilities:**
- Full-text and semantic search across agent database
- Trust scoring (0-100 scale with component breakdown)
- Agent metadata: source, framework support, update frequency, community stats
- MCP server integration discovery
- Framework detection: LangChain, CrewAI, AutoGen, etc.

**Use Case:**
Find production-ready AI agents matching your requirements. Developers can discover agents by capability, framework, trust level, or natural language query.

**Status:** Actively maintained, sub-100ms response times, 40k+ agents indexed

---

## Twitter/X Post Ideas

### Short Form (280 chars)
"40,000+ AI agents. One search. AgentIndex makes agent discovery as easy as Google. Semantic search + trust scoring + framework integrations. Try it: agentcrawl.dev"

### Medium Form
"AgentIndex is live 🚀

Tired of searching GitHub/npm/PyPI separately for AI agents? We indexed 40,000+ agents and built semantic search + trust scoring.

Framework integrations: LangChain, CrewAI, AutoGen
Try it: agentcrawl.dev"