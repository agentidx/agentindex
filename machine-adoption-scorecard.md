# Machine-Adoption Scorecard — March 13, 2026

## Platform Metrics

| Metric | Value |
|--------|-------|
| Total assets indexed | 4,985,188 |
| AI agents & tools | 204,000+ |
| Models & datasets | 4,780,000+ |
| Trust-scored agents | 100,250 |
| Average trust score | 52.4 / 100 |
| MCP agents tracked | 17,528 |
| CVEs tracked | 49 (9 critical, 31 high) |
| Autonomous LaunchAgents | 42 |

## Trust Score Distribution

| Grade | Count |
|-------|-------|
| A (80-89) | 52 |
| B (70-79) | 2,320 |
| C (60-69) | 23,923 |
| D (50-59) | 35,101 |
| F (0-49) | 38,854 |

## API Traffic (All-time from logs)

| Endpoint | Hits |
|----------|------|
| /agent/* pages | 948,602 |
| /v1/preflight | 14,396 |
| /safe/* pages | 6,583 |
| /mcp | 5,565 |
| /badge/* | 2,930 |
| /docs | 1,496 |
| /blog/* | 218 |
| /llms.txt | 68 |
| /feed/* | 41 |

## Machine Discovery Channels

| Channel | Status | Assets |
|---------|--------|--------|
| llms.txt | Live | Machine-readable API description |
| llms-full.txt | Live | Complete API documentation |
| MCP Server | Live | Native agent-to-agent trust verification |
| /agents JSON | Live | Machine-discoverable endpoint directory |
| /health | Live | Health check with capability advertisement |
| /.well-known/security.txt | Live | Security contact |
| /humans.txt | Live | Team and technology info |
| /manifest.json | Live | Progressive web app manifest |
| /ai JSON | Live | AI system metadata |
| /widget.js | Live | Embeddable trust widget |
| RSS feeds (3x) | Live | CVE alerts, trending, trust changes |
| OpenAPI/docs | Live | Interactive API documentation |

## Developer Tools Built

| Tool | Status | Distribution |
|------|--------|-------------|
| nerq CLI v1.1.0 | Built, ready for PyPI | `pip install nerq` |
| GitHub Action | Built, ready for Marketplace | `nerq-ai/trust-check-action@v1` |
| VS Code Extension | Built, ready for Marketplace | `vscode-extension/` |
| Slack Bot | Live | `/integrations/slack` |
| Embeddable Widget | Live | `nerq.ai/widget.js` |
| Trust Badges (SVG) | Live | `nerq.ai/badge/{name}.svg` |

## Framework Integrations Prepared

| Framework | File | Status |
|-----------|------|--------|
| LangChain | `framework-prs/langchain/trust_check.py` | Ready for PR |
| CrewAI | `framework-prs/crewai/nerq_trust.py` | Ready for PR |
| AutoGen | `framework-prs/autogen/nerq_verify.py` | Ready for PR |
| LlamaIndex | `framework-prs/llamaindex/nerq_validator.py` | Ready for PR |
| Semantic Kernel | `framework-prs/semantic-kernel/nerq_trust_plugin.py` | Ready for PR |

## Content Pipeline

| Content | Status |
|---------|--------|
| Auto-generated comparisons | 12 posts (10 auto + 2 editorial) |
| Social scheduler | Live, daily Bluesky posts |
| Dev.to publisher | Built, needs API key |
| Blog posts | 2 editorial posts ready |
| Show HN draft | Ready |
| Reddit posts (3 subs) | Ready |
| Partnership proposals (4) | Ready |

## Automated Systems (42 LaunchAgents)

### Core Infrastructure
- API server (always on)
- Healthcheck + autoheal

### Data Pipeline
- GitHub, npm, PyPI, Docker Hub crawlers
- HuggingFace indexer
- CVE scanner (OSV)
- OpenSSF scorecard crawler
- Trust score computation

### Growth Automation
- Auto-comparisons (weekly)
- Social scheduler (daily)
- Badge PR bot (daily)
- Machine analytics (daily)
- Citation tracker
- Sitemap validator
- IndexNow pinger
- Google Search Console pinger

## Next Steps (Manual Actions)

1. Publish nerq CLI to PyPI
2. Push GitHub Action to marketplace
3. Submit Show HN
4. Submit awesome-list PRs
5. Email partnership proposals
6. Set DEVTO_API_KEY and run publisher
7. Upload HuggingFace dataset
8. Publish VS Code extension
