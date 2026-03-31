# 🔍 AgentIndex
> The Google for AI agents - semantic search across 40,000+ agents

[![API Status](https://img.shields.io/badge/API-Live-green)](https://api.agentcrawl.dev)
[![Agents Indexed](https://img.shields.io/badge/Agents-40k+-blue)](https://agentcrawl.dev)
[![Trust Scoring](https://img.shields.io/badge/Trust%20Scoring-Active-purple)](https://agentcrawl.dev/blog/ai-agent-quality-scoring-guide.html)

**Problem:** Finding AI agents across GitHub, npm, PyPI, HuggingFace, MCP is fragmented and painful.

**Solution:** One search API to find them all. Semantic search + trust scoring + cross-platform indexing.

## 🚀 Quick Start

### Python
```python
pip install agentindex-langchain
from agentindex import search

# Semantic search across all platforms
results = search("customer support automation")
for agent in results:
    print(f"{agent.name} (Trust: {agent.trust_score}/100)")
```

### Node.js  
```javascript
npm install @agentidx/langchain
const { search } = require('@agentidx/langchain')

const results = await search('code review agent')
console.log(`Found ${results.length} agents`)
```

### REST API
```bash
curl "https://api.agentcrawl.dev/v1/search" \
  -d '{"query": "data visualization agent", "limit": 10}' \
  -H "Content-Type: application/json"
```

## ✨ Why AgentIndex?

### 🔍 Semantic Search
Understands **intent**, not just keywords. "automate customer emails" finds relevant agents even if they don't mention those exact words.

### 📊 Trust Scoring  
Every agent gets a 0-100 production-readiness score based on:
- Maintenance activity (recent commits, issue responses)
- Community adoption (stars, forks, downloads)
- Documentation quality (setup guides, examples)
- Code stability (error handling, tests, security)

### 🌐 Cross-Platform Coverage
**One API for all agent sources:**
- **GitHub** (32,000+ repositories)
- **npm** (3,600+ packages)
- **PyPI** (2,400+ packages)  
- **HuggingFace** (1,400+ models)
- **MCP Servers** (450+ connectors)

### ⚡ Developer-First
- **Sub-100ms** search response times
- **Comprehensive SDKs** (Python, Node.js)
- **Production-ready** documentation
- **Working examples** that actually work

## 📊 Platform Stats

| Platform | Agents Indexed | Active | Coverage |
|----------|----------------|--------|----------|
| GitHub   | 32,156        | 18,902 | Repositories, Actions |
| npm      | 3,627         | 2,134  | Packages, TypeScript |
| PyPI     | 2,445         | 1,567  | Packages, Wheels |
| HuggingFace | 1,398      | 892    | Models, Datasets |
| MCP      | 456           | 321    | Servers, Clients |
| **Total** | **40,082**   | **23,816** | **All Platforms** |

*Updated daily. Trust-scored for production readiness.*

## 🎯 Use Cases

### Framework Integration
```python
# Find LangChain-compatible agents
agents = search("document analysis", framework="langchain")
compatible = [a for a in agents if a.trust_score > 80]
```

### Production Deployment
```python
# Filter by production readiness
production_ready = search(
    "customer support", 
    min_trust_score=85,
    maintenance_status="active"
)
```

### CI/CD Pipeline Integration
```bash
# Automated agent discovery in CI
agentindex search "security scan" --format=json --min-trust=75 > agents.json
```

## 🔧 Integration Examples

<details>
<summary><strong>LangChain Integration</strong></summary>

```python
from langchain import agents
from agentindex import search, load_agent

# Discover agent
results = search("sql query generation", framework="langchain")
best_agent = max(results, key=lambda x: x.trust_score)

# Load and use
agent = load_agent(best_agent.id)
chain = agents.initialize_agent([agent], llm, agent_type="tool-calling")
```
</details>

<details>
<summary><strong>CrewAI Integration</strong></summary>

```python
from crewai import Agent, Crew
from agentindex import search, get_capabilities

# Find specialized agents
analysts = search("data analysis", capabilities=["pandas", "visualization"])
writers = search("content generation", capabilities=["copywriting"])

# Build crew
crew = Crew(
    agents=[
        Agent(role="Data Analyst", tools=analysts[0].tools),
        Agent(role="Content Writer", tools=writers[0].tools)
    ]
)
```
</details>

<details>
<summary><strong>AutoGen Multi-Agent Setup</strong></summary>

```python
import autogen
from agentindex import search, create_autogen_config

# Discover complementary agents  
code_agents = search("code review", framework="autogen")
test_agents = search("test generation", framework="autogen")

# Auto-configure
config = create_autogen_config([code_agents[0], test_agents[0]])
assistant = autogen.AssistantAgent("code_reviewer", **config)
```
</details>

## 📈 Performance Benchmarks

| Operation | AgentIndex | Manual Search | Improvement |
|-----------|------------|---------------|-------------|
| Find compatible agent | 0.08s | 15-30 min | **1,125x faster** |
| Quality assessment | Instant | 2-5 min | **Trust scoring** |
| Cross-platform search | 1 query | 5 sites | **5x efficiency** |
| Production filtering | Built-in | Manual | **Risk reduction** |

## 🛠️ Advanced Usage

### Filtering & Sorting
```python
# Complex filtering
results = search(
    query="customer support automation",
    frameworks=["langchain", "crewai"],
    min_trust_score=80,
    max_resource_usage="8GB",
    sort_by="trust_score",
    limit=20
)
```

### Batch Operations  
```python
# Process multiple queries
queries = ["email automation", "data analysis", "content generation"]
batch_results = batch_search(queries, parallel=True)
```

### Real-Time Updates
```python
# Subscribe to new agents
from agentindex import AgentStream

stream = AgentStream(categories=["automation", "analysis"])
for new_agent in stream:
    if new_agent.trust_score > 85:
        evaluate_for_production(new_agent)
```

## 🔗 API Reference

### Search Endpoint
```http
POST /v1/search
Content-Type: application/json

{
  "query": "customer support automation",
  "limit": 10,
  "frameworks": ["langchain", "crewai"],
  "min_trust_score": 70
}
```

### Response Format
```json
{
  "results": [
    {
      "id": "agent_123",
      "name": "CustomerSupportAI",
      "description": "Automated customer inquiry handling...",
      "trust_score": 87,
      "framework": "langchain",
      "platform": "github",
      "capabilities": ["nlp", "classification", "response_generation"],
      "resource_requirements": {
        "memory": "4GB",
        "gpu": false
      },
      "installation": "pip install customer-support-ai",
      "documentation_url": "https://github.com/...",
      "last_updated": "2026-02-15T10:30:00Z"
    }
  ],
  "total": 156,
  "search_time_ms": 73
}
```

Full API documentation: **[api.agentcrawl.dev/docs](https://api.agentcrawl.dev/docs)**

## 🏗️ Architecture

AgentIndex operates as a semantic discovery layer over the fragmented AI agent ecosystem:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Developers    │───▶│   AgentIndex     │───▶│  Agent Sources  │
│                 │    │                  │    │                 │
│ • Search once   │    │ • Semantic AI    │    │ • GitHub (32k)  │
│ • Get ranked    │    │ • Trust scoring  │    │ • npm (3.6k)    │
│ • results from  │    │ • Cross-platform │    │ • PyPI (2.4k)   │
│   all platforms │    │ • Sub-100ms      │    │ • HuggingFace   │
└─────────────────┘    └──────────────────┘    │ • MCP Servers   │
                                               └─────────────────┘
```

**Technology Stack:**
- **Search**: FAISS + sentence-transformers (384-dim embeddings)
- **Scoring**: 6-component trust algorithm  
- **API**: FastAPI with Redis caching
- **Data**: PostgreSQL + real-time indexing
- **Infrastructure**: Auto-scaling, 99.9% uptime

## 📚 Learning Resources

- **[Complete Developer Guide](https://agentcrawl.dev/blog/how-to-find-ai-agents-guide.html)** - Agent discovery best practices
- **[Trust Scoring Explained](https://agentcrawl.dev/blog/ai-agent-quality-scoring-guide.html)** - Production readiness evaluation
- **[LangChain Integration](https://agentcrawl.dev/blog/langchain-agent-discovery-2026.html)** - Framework-specific patterns

## 🤝 Contributing

We welcome contributions! AgentIndex is built for the developer community.

**Ways to help:**
- **Report agents we're missing** → [Submit an issue](https://github.com/agentidx/agentindex/issues)
- **Improve trust scoring** → Algorithm suggestions welcome
- **Add framework support** → New integration PRs appreciated  
- **Enhance documentation** → Examples, guides, tutorials

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

## 📄 License

MIT License - Use in your projects, commercial or open source.

## 🌟 Community

- **[Discord](https://discord.gg/agentindex)** - Live help, feature discussions
- **[Twitter](https://twitter.com/agentindex)** - Updates and announcements
- **[Blog](https://agentcrawl.dev/blog/)** - Guides and best practices

---

### Show Your Support ⭐

If AgentIndex helps you find better agents faster, please **star this repository**!

It helps other developers discover the tool and validates our approach to solving agent discovery fragmentation.

**[⭐ Star on GitHub](https://github.com/agentidx/agentindex) • [🚀 Try Live API](https://api.agentcrawl.dev/docs) • [📖 Full Documentation](https://agentcrawl.dev)**