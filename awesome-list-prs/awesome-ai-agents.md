# PR: awesome-ai-agents

**Target repo**: `e2b-dev/awesome-ai-agents`

**Section**: Tools & Infrastructure

**Entry to add**:

```markdown
- [Nerq](https://nerq.ai) - AI agent trust verification database. Trust scores for 204,000+ agents across 6 dimensions. Free API, GitHub Action, and CLI. [API Docs](https://nerq.ai/docs)
```

**PR Title**: Add Nerq — AI agent trust verification database

**PR Body**:
Adding Nerq (nerq.ai), an independent trust and compliance database for AI agents.

- Indexes 204,000+ AI agents and tools from GitHub, npm, PyPI, HuggingFace
- Trust Score (0-100) across 6 dimensions: Code Quality, Community, Compliance, Operational Health, Security, External Validation
- Free API: `GET /v1/preflight?target={agent_name}`
- GitHub Action for CI/CD trust gates
- CLI tool: `pip install nerq`
- MCP server for agent-to-agent trust verification
