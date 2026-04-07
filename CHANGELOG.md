# Changelog

All notable changes to AgentIndex will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GitHub repository documentation and contribution guidelines
- Enhanced README with comprehensive examples and use cases
- Community support channels (Discord, GitHub Discussions)

## [0.3.0] - 2026-02-15

### Added
- **Semantic Search**: FAISS + sentence-transformers implementation
  - 384-dimensional embeddings using all-MiniLM-L6-v2
  - Sub-100ms search performance across 40k+ agents
  - Intent-based queries vs keyword matching
- **Trust Scoring System**: 6-component production readiness assessment
  - Maintenance activity scoring (25% weight)
  - Community adoption metrics (20% weight)  
  - Documentation quality analysis (15% weight)
  - Code stability indicators (15% weight)
  - Security practices evaluation (15% weight)
  - Performance characteristics (10% weight)
- **Cross-Platform Indexing**: 
  - GitHub repositories (32k+ agents)
  - npm packages (3.6k+ agents)
  - PyPI packages (2.4k+ agents)
  - HuggingFace models (1.4k+ agents)
  - MCP servers (450+ agents)

### Changed
- Discovery API now returns semantic relevance scores
- Agent metadata enriched with trust scoring data
- Response times improved to sub-100ms average

### Performance
- Semantic index build time: 27.2 seconds for 24k agents
- Search latency: <100ms P95, <50ms P50
- Index memory usage: ~2GB for full dataset
- Concurrent search capacity: 1000+ requests/second

## [0.2.1] - 2026-02-10

### Fixed
- Database connection pooling for high-load scenarios
- Memory leaks in long-running crawler processes
- Trust score calculation edge cases for new agents

### Security
- API key validation strengthened
- Rate limiting implemented across all endpoints
- Input sanitization for search queries

## [0.2.0] - 2026-02-05

### Added
- **REST API v1**: Production-ready discovery endpoints
  - `/v1/search` - Semantic agent search
  - `/v1/agents/{id}` - Agent details and metadata
  - `/v1/health` - System status and performance
- **Framework Integration APIs**:
  - LangChain retriever integration
  - CrewAI discovery and crew building
  - AutoGen group chat support
- **Real-time Monitoring**:
  - API performance metrics
  - System health dashboards
  - Automated alerting
- **Developer SDKs**:
  - Python package: `agentindex-langchain`
  - Node.js package: `@agentidx/langchain`

### Changed
- Migrated from SQLite to PostgreSQL for production scale
- Improved error handling and logging across services
- Enhanced API documentation with interactive examples

## [0.1.2] - 2026-01-25

### Added
- Automated crawler system for continuous agent discovery
- Classification pipeline using local LLM (qwen2.5-coder:7b)
- Database schema for agent metadata and relationships

### Fixed
- Crawler rate limiting to respect source API limits
- Data consistency issues in multi-threaded processing
- Classification accuracy for edge-case agent types

## [0.1.1] - 2026-01-20

### Added
- Basic web interface for agent browsing
- Agent detail pages with metadata display
- Category-based filtering and navigation

### Changed
- Improved landing page performance and SEO
- Enhanced mobile responsiveness
- Better error messages and user feedback

## [0.1.0] - 2026-01-15

### Added
- **Initial Release**: AgentIndex MVP launched
- Core agent indexing from GitHub repositories
- Basic search functionality (keyword-based)
- Web interface for agent discovery
- Foundation database schema and models
- Initial agent classification system

### Core Features
- Agent discovery across GitHub
- Basic metadata extraction and storage
- Simple web interface for browsing
- RESTful API for programmatic access
- Docker containerization for deployment

### Performance Baseline
- 10k+ agents indexed in initial release
- ~500ms average search response time
- Basic relevance ranking algorithm
- Single-server deployment capability

---

## Version History Summary

| Version | Date | Agents | Key Feature | Performance |
|---------|------|---------|-------------|-------------|
| 0.3.0 | 2026-02-15 | 40k+ | Semantic Search | <100ms |
| 0.2.0 | 2026-02-05 | 25k+ | Production API | <200ms |
| 0.1.0 | 2026-01-15 | 10k+ | MVP Launch | <500ms |

## Upcoming Releases

### [0.4.0] - Planned 2026-02-25
- **Agent-to-Agent Protocol (A2A)**: Machine communication standards
- **Advanced Filtering**: Resource requirements, deployment complexity
- **Performance Optimization**: FAISS GPU acceleration, query optimization
- **Enterprise Features**: Team management, usage analytics, SLA monitoring

### [0.5.0] - Planned 2026-03-10  
- **Framework Partnerships**: Official integrations with major AI frameworks
- **Quality Assurance**: Automated testing pipeline for indexed agents
- **Developer Tools**: IDE extensions, CLI tools, CI/CD integrations
- **Community Features**: Agent reviews, ratings, usage statistics

### Long-term Roadmap
- **Multi-language Support**: Non-English agent discovery
- **Federated Search**: Cross-registry protocol standards
- **AI-powered Curation**: Automated quality assessment and recommendations
- **Enterprise Deployment**: On-premises and private cloud options

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:
- Reporting bugs and requesting features
- Development setup and testing
- Code style and review process
- Community guidelines

## Support

- **Documentation**: [agentcrawl.dev/docs](https://agentcrawl.dev/docs)
- **API Reference**: [api.agentcrawl.dev/docs](https://api.agentcrawl.dev/docs)
- **Community**: [Discord](https://discord.gg/agentindex)
- **Issues**: [GitHub Issues](https://github.com/agentidx/agentindex/issues)