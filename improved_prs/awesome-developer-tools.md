# PR: awesome-developer-tools

**Target Repository:** cjbarber/ToolsOfTheTrade OR stackshareio/awesome-stacks
**Category:** APIs and Data Services
**Success Probability:** HIGH (technical audience, API-focused)

## Improved Entry

```markdown
### APIs and Data Services

* [AgentIndex API](https://api.agentcrawl.dev) - REST API for finding AI agents across GitHub, npm, PyPI, HuggingFace. 40k+ agents indexed, semantic search, trust scoring. Python/Node.js SDKs available.
```

## PR Description

**What**: AgentIndex API - technical solution for AI agent discovery across multiple package registries and repositories.

**Why this belongs in developer tools**:
- Solves common developer problem: finding compatible AI agents/packages
- API-first architecture with comprehensive documentation
- Production-ready performance: sub-100ms search response times
- Technical integration: Python (`pip install agentindex-langchain`) and Node.js SDKs
- Measurable scale: 40,000+ agents indexed, 23,000+ actively maintained

**Technical specifications**:
- REST API with OpenAPI documentation
- Semantic search using sentence transformers + FAISS
- Trust scoring algorithm based on maintenance, adoption, stability
- Cross-platform indexing: GitHub, npm, PyPI, HuggingFace, MCP registries
- Rate limiting: 1000 requests/month free tier

**Developer adoption indicators**:
- API documentation: https://api.agentcrawl.dev/docs
- GitHub integration examples and usage patterns
- Framework-specific packages for popular AI/ML frameworks
- Production deployment guides and best practices

**Links**:
- API: https://api.agentcrawl.dev
- Documentation: https://api.agentcrawl.dev/docs  
- Python package: https://pypi.org/project/agentindex-langchain/
- Integration guide: https://agentcrawl.dev/blog/how-to-find-ai-agents-guide.html

This is a technical tool for developers, not a consumer platform. The API-first approach and comprehensive documentation make it suitable for integration into developer workflows and CI/CD pipelines.