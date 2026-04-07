# Add Nerq — AI Agent Trust & Discovery Platform with 204K+ Agents

**Target Repository**: kyrolabs/awesome-langchain
**Section**: Tools and Utilities

## Pull Request Description:
**What**: Nerq is a trust-scored AI agent discovery platform with semantic search across 204,000+ agents and tools, including extensive LangChain coverage.

**Why this belongs here**:
- Semantic search that understands LangChain concepts and patterns
- Trust Score (0-100) for agent quality assessment with CVE, license, and download enrichment
- Preflight API for agent-to-agent trust verification before interaction
- 5,200+ LangChain-compatible agents indexed with detailed safety profiles

**Links**:
- Platform: https://nerq.ai
- Preflight API: `GET https://nerq.ai/v1/preflight?target=langchain-agent-name`
- Full API docs: https://nerq.ai/docs

**Preflight check example**:
```bash
curl "https://nerq.ai/v1/preflight?target=langchain&caller=my-app"
# Returns: trust_score, grade, recommendation (PROCEED/CAUTION/DENY), CVEs, alternatives
```

## Markdown Entry to Add:
```markdown
- [Nerq](https://nerq.ai) - Trust-scored discovery for 204K+ AI agents including 5,200+ LangChain agents. Preflight API verifies agent safety before interaction.
```

## Expected Impact:
- +50-75 weekly visitors from LangChain developers
- Preflight API adoption for LangChain agent pipelines
- Community validation from framework experts
