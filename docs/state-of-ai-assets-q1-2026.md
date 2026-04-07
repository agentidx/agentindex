# State of AI Assets — Q1 2026

*The first comprehensive census of the AI agent ecosystem*

Published 2026-03-09 · Data from [nerq.ai](https://nerq.ai) · [Live API](https://nerq.ai/v1/agent/stats)

---

## 1. Executive Summary

| Metric | Value |
| --- | --- |
| Total AI assets indexed | 4,919,620 |
| Agents, tools & MCP servers | 143,642 |
| MCP servers | 17,468 |
| Average trust score | 65.5/100 |
| High trust (70+) | 12.9% |
| Frameworks tracked | 11 |

Nerq has indexed **4,919,620 AI assets** from 6 registries, making it the largest open census of the AI agent ecosystem. Of these, **143,642** are agents, tools, and MCP servers — the executable components that power the emerging agentic economy.

Every asset receives a **Trust Score** (0–100) based on security, maintenance, popularity, documentation, and ecosystem signals. The average trust score across all agents and tools is **65.5/100**.

---

## 2. The AI Asset Landscape

The 4.9M indexed assets break down into:

| Type | Count | Share |
| --- | --- | --- |
| Models | 2,558,512 | 52.0% |
| Spaces / Apps | 1,019,967 | 20.7% |
| Datasets | 794,754 | 16.2% |
| Agents | 66,092 | 1.3% |
| Tools | 60,082 | 1.2% |
| MCP Servers | 17,468 | 0.4% |
| **Total** | **4,919,620** | **100%** |

Agents, tools, and MCP servers — the *actionable* components — represent 2.9% of all assets:

- **Agents**: 66,092 (46.0%)
- **Tools**: 60,082 (41.8%)
- **MCP Servers**: 17,468 (12.2%)

---

## 3. What Agents Do — Category Distribution

Top 20 categories among 143,642 agents and tools (excluding uncategorized):

| Category | Count |
| --- | --- |
| coding | 10,939 |
| infrastructure | 3,552 |
| devops | 3,524 |
| communication | 2,955 |
| AI tool | 2,262 |
| finance | 2,132 |
| research | 1,909 |
| other | 1,789 |
| content | 1,277 |
| marketing | 1,253 |
| data | 1,199 |
| security | 1,160 |
| health | 791 |
| education | 751 |
| productivity | 718 |
| design | 513 |
| legal | 326 |
| AI assistant | 851 |
| automation | 102 |
| agent framework | 79 |

**Coding** dominates with 10,939 agents — reflecting the developer-tool origin of the agent ecosystem. **Infrastructure** and **DevOps** follow, showing agents are increasingly used for operational automation.

---

## 4. How They're Built — Frameworks & Languages

### Framework Distribution

| Framework | Count |
| --- | --- |
| Anthropic | 7,072 |
| OpenAI | 5,927 |
| LangChain | 2,546 |
| MCP | 1,932 |
| Ollama | 1,785 |
| HuggingFace | 1,126 |
| AutoGen | 1,065 |
| CrewAI | 780 |
| LlamaIndex | 424 |
| A2A | 168 |
| Semantic Kernel | 162 |

**Anthropic** and **OpenAI** SDKs lead, followed by **LangChain** as the dominant orchestration framework. **MCP** (Model Context Protocol) already ranks 4th with 1,932 agents — a strong signal of protocol adoption.

### Language Distribution

| Language | Count |
| --- | --- |
| Python | 13,946 |
| TypeScript | 5,915 |
| JavaScript | 2,306 |
| Jupyter Notebook | 1,160 |
| Shell | 932 |
| Go | 842 |
| HTML | 783 |
| Rust | 657 |
| C# | 375 |
| Java | 311 |

**Python** accounts for 51.5% of agents with known languages. **TypeScript** is the clear second at 21.8% — driven by MCP server development and npm packages.

---

## 5. Where They Come From — Source Registries

| Source | Count | Share |
| --- | --- | --- |
| HuggingFace | 51,064 | 35.5% |
| GitHub | 30,792 | 21.4% |
| npm | 30,769 | 21.4% |
| PyPI | 24,827 | 17.3% |
| MCP registries | 2,048 | 1.4% |
| Other | 3,142 | 2.2% |

---

## 6. Trust & Quality

Every agent and tool receives a **Nerq Trust Score** (0–100) computed from five pillars:

- **Security** (30%) — known vulnerabilities, dependency audit, code patterns
- **Maintenance** (25%) — commit recency, release frequency, issue response time
- **Popularity** (20%) — stars, downloads, forks, community size
- **Documentation** (15%) — README quality, API docs, examples
- **Ecosystem** (10%) — protocol support, integrations, interoperability

### Trust Distribution

| Level | Score Range | Count | Share |
| --- | --- | --- | --- |
| 🟢 HIGH | 70–100 | 18,473 | 12.9% |
| 🟡 MEDIUM | 40–69 | 125,155 | 87.1% |
| 🔴 LOW | 0–39 | 14 | 0.0% |
| **Average** | | **65.5/100** | |

---

## 7. Top 20 Most Trusted Agents

| # | Name | Type | Score | Grade | Source | Stars |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | williamzujkowski/strudel-mcp-server | MCP | 92.9 | A+ | GitHub | 158 |
| 2 | SWE-agent/SWE-agent | agent | 92.5 | A+ | GitHub | 18,516 |
| 3 | microsoft/qlib | agent | 92.4 | A+ | GitHub | 37,615 |
| 4 | nanoclaw | agent | 92.1 | A+ | GitHub | 7,735 |
| 5 | FunnyWolf/agentic-soc-platform | agent | 91.3 | A+ | GitHub | 579 |
| 6 | laravel/boost | MCP | 91.2 | A+ | GitHub | 3,275 |
| 7 | ccmanager | agent | 90.9 | A+ | GitHub | 831 |
| 8 | harbor | MCP | 90.5 | A+ | GitHub | 2,424 |
| 9 | microsoft/azure-devops-mcp | agent | 90.3 | A+ | GitHub | 1,291 |
| 10 | opal | agent | 90.2 | A+ | GitHub | 5,422 |
| 11 | raptor | agent | 90.2 | A+ | GitHub | 1,095 |
| 12 | vfarcic/dot-ai | agent | 90.2 | A+ | GitHub | 294 |
| 13 | GoogleCloudPlatform/agent-starter-pack | agent | 90.1 | A+ | GitHub | 5,761 |
| 14 | laravel/mcp | MCP | 90.0 | A+ | GitHub | 679 |
| 15 | agentgateway/agentgateway | agent | 89.8 | A | GitHub | 1,777 |
| 16 | QwenLM/qwen-code | agent | 89.7 | A | GitHub | 20,060 |
| 17 | GreyDGL/PentestGPT | agent | 89.7 | A | GitHub | 11,700 |
| 18 | RooCodeInc/Roo-Code | agent | 89.5 | A | GitHub | 22,330 |
| 19 | PromptX | agent | 89.5 | A | GitHub | 3,570 |
| 20 | ruler | agent | 89.5 | A | GitHub | 2,452 |

---

## 8. Top 20 MCP Servers

| # | Name | Score | Grade | Source | Stars |
| --- | --- | --- | --- | --- | --- |
| 1 | williamzujkowski/strudel-mcp-server | 92.9 | A+ | GitHub | 158 |
| 2 | laravel/boost | 91.2 | A+ | GitHub | 3,275 |
| 3 | harbor | 90.5 | A+ | GitHub | 2,424 |
| 4 | laravel/mcp | 90.0 | A+ | GitHub | 679 |
| 5 | a11ymcp | 89.3 | A | GitHub | 72 |
| 6 | CursorTouch/Windows-MCP | 89.0 | A | GitHub | 4,390 |
| 7 | Ansvar-Systems/EU_compliance_MCP | 88.8 | A | GitHub | 45 |
| 8 | mcp-docs-service | 88.4 | A | GitHub | 53 |
| 9 | 54yyyu/zotero-mcp | 88.1 | A | GitHub | 1,461 |
| 10 | tavily-ai/tavily-mcp | 88.1 | A | GitHub | 1,218 |
| 11 | cyproxio/mcp-for-security | 88.1 | A | GitHub | 553 |
| 12 | minecraft-mcp-server | 87.8 | A | GitHub | 467 |
| 13 | spences10/mcp-omnisearch | 87.8 | A | GitHub | 271 |
| 14 | photoshop-python-api-mcp-server | 87.8 | A | GitHub | 162 |
| 15 | Teradata/teradata-mcp-server | 87.5 | A | GitHub | 40 |
| 16 | enuno/unifi-mcp-server | 87.2 | A | GitHub | 42 |
| 17 | rohitg00/awesome-devops-mcp-servers | 86.7 | A | GitHub | 942 |
| 18 | FradSer/mcp-server-apple-events | 86.6 | A | GitHub | 33 |
| 19 | aegis-mcp | 86.6 | A | GitHub | — |
| 20 | export-assist-mcp | 86.6 | A | GitHub | — |

---

## 9. Growth Trends

Nerq's initial bulk index was completed in February 2026. The index is continuously updated as new agents are published to npm, PyPI, GitHub, HuggingFace, Docker Hub, and MCP registries.

New assets are discovered daily through automated crawling of all six registries.

---

## 10. Methodology

Nerq indexes AI assets from six registries: **GitHub**, **npm**, **PyPI**, **HuggingFace**, **Docker Hub**, and **MCP registries**. Assets are classified by type (agent, tool, MCP server, model, dataset, space) using keyword analysis and metadata inspection.

Trust Scores are computed using a weighted composite of security, maintenance, popularity, documentation, and ecosystem signals. Scores are updated on a rolling basis as new data becomes available.

All data is available via the [Nerq API](https://nerq.ai/nerq/docs) and can be queried programmatically.

---

## 11. About Nerq

**Nerq** is the AI asset search engine — the largest open index of AI agents, tools, and MCP servers. Built for the agentic economy, Nerq provides trust scoring, compliance classification, and discovery APIs that help developers and organizations find, evaluate, and integrate AI assets safely.

- [nerq.ai](https://nerq.ai) — search the index
- [API documentation](https://nerq.ai/nerq/docs)
- [KYA — Know Your Agent](https://nerq.ai/kya) — due diligence reports
- [Live statistics](https://nerq.ai/stats)
- [MCP server directory](https://nerq.ai/mcp-servers)

---

*Data sourced from nerq.ai on 2026-03-09. Live data: [nerq.ai/v1/agent/stats](https://nerq.ai/v1/agent/stats)*
