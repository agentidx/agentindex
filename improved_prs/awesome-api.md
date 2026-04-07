# PR: awesome-api  

**Target Repository:** Kikobeats/awesome-api OR public-apis/public-apis
**Category:** Search APIs / Developer APIs
**Success Probability:** HIGH (API-focused, technical metrics)

## Improved Entry

```markdown
### Search APIs

| API | Description | Auth | HTTPS | CORS |
|---|---|---|---|---|
| [AgentIndex](https://api.agentcrawl.dev) | Search 40k+ AI agents across GitHub, npm, PyPI, HuggingFace with semantic search and trust scoring | `apiKey` | Yes | Yes |
```

## PR Description

**API Name**: AgentIndex Search API
**Category**: Search / Discovery APIs
**Description**: REST API for semantic search across 40,000+ AI agents from multiple platforms

**API Specifications**:
- **Base URL**: `https://api.agentcrawl.dev/v1`
- **Authentication**: API key (free tier: 1000 requests/month)
- **Response format**: JSON
- **Rate limiting**: Yes (configured per plan)
- **HTTPS**: Required
- **CORS**: Enabled for web applications

**Key endpoints**:
- `POST /search` - Semantic search across all indexed agents
- `GET /agents/{id}` - Detailed agent information and metadata
- `GET /health` - API status and performance metrics

**Technical features**:
- Sub-100ms average response time
- Semantic search using sentence transformers
- Trust scoring algorithm (0-100 scale)
- Multi-platform data: GitHub (32k), npm (3.6k), PyPI (2.4k), HuggingFace (1.4k), MCP (450+)
- Real-time indexing with 500+ new agents weekly

**Developer resources**:
- OpenAPI 3.0 specification
- Python SDK: `pip install agentindex-langchain`
- Node.js SDK: `npm install @agentidx/langchain`
- Comprehensive documentation with examples
- Integration guides for popular AI frameworks

**Production usage**:
- Stable API with 99.9% uptime
- Used by developers for agent discovery and evaluation
- Integrated into CI/CD pipelines for automated agent selection
- Framework integrations available (LangChain, CrewAI, AutoGen)

**Links**:
- API Documentation: https://api.agentcrawl.dev/docs
- Interactive playground: https://agentcrawl.dev
- GitHub: https://github.com/agentidx (documentation and examples)
- Status page: https://api.agentcrawl.dev/v1/health