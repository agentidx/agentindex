# Show HN: Preflight trust checks for AI agent-to-agent interactions

As agents start transacting with each other (Stripe Tempo, Sui a402, etc.), they need a way to verify trust before interacting. We built a preflight API:

```
curl "https://nerq.ai/v1/preflight?target=langchain&caller=my-agent"
```

Returns trust score (0-100), grade, recommendation (PROCEED/CAUTION/DENY), known CVEs, license info, and safer alternatives. One call, <100ms.

We index 204K+ agents from GitHub, npm, PyPI, HuggingFace, and MCP registries. Trust Score v2 weights:

- Code Quality 25% — description completeness, naming, capabilities
- Community 25% — stars, npm/PyPI downloads, forks
- Compliance 20% — license classification (PERMISSIVE/COPYLEFT/VIRAL), EU AI Act risk class
- Operational Health 15% — update recency, maintenance activity
- Security 15% — CVE count and severity from GitHub Advisory Database

Batch endpoint for checking up to 50 agents at once:

```
curl -X POST https://nerq.ai/v1/preflight/batch \
  -H "Content-Type: application/json" \
  -d '{"targets": ["langchain", "crewai", "autogen"]}'
```

Commerce verification for transaction gating:

```
curl -X POST https://nerq.ai/v1/commerce/verify \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "buyer", "counterparty_id": "seller", "transaction_type": "payment", "amount_range": "high"}'
```

Python SDK: `pip install nerq`

```python
from nerq import NerqClient
client = NerqClient()
r = client.preflight("langchain")
if r.is_safe():
    use_agent()
```

Free, no auth required, no rate limit on preflight. We also expose an MCP server so Claude/ChatGPT can check agent trust mid-conversation.

Some things we found indexing 204K agents:
- ~70% are thin wrappers over ChatGPT/Claude with minimal error handling
- Only 15% have proper license files
- 2.3% have known CVEs — including some of the most popular ones
- npm agents average 3x more weekly downloads than PyPI equivalents

Try it: https://nerq.ai
API docs: https://nerq.ai/nerq/docs
Trust methodology: https://nerq.ai/protocol
Live oracle status: https://nerq.ai/oracle

How do you handle trust in agent-to-agent workflows? Curious what approaches others are taking.

---

## Posting checklist

- [ ] Verify nerq.ai loads in <1s
- [ ] Test preflight API: `curl "https://nerq.ai/v1/preflight?target=langchain"` returns <200ms
- [ ] Test batch endpoint works
- [ ] Test commerce endpoint works
- [ ] /oracle page shows live stats
- [ ] /popular page loads with top 50
- [ ] /badges page works
- [ ] SDK installable: `pip install nerq`
- [ ] Swagger UI at /docs loads

## Best posting times
- Tuesday-Thursday, 8-10 AM Pacific
- Avoid Friday afternoon, weekends

## Prepared responses

**"How is this different from X?"**
Most agent directories are discovery-only. We're focused on the trust verification step — the preflight check before interaction. Think credit check, not phone book.

**"What about false positives?"**
Trust Score v2 is conservative — it flags more than it should rather than less. The CAUTION tier exists for agents that need human review. We're transparent about the methodology at nerq.ai/protocol.

**"How do you handle typosquatting?"**
We index from authoritative sources (official registries, verified repos). Name similarity scoring is on the roadmap but not shipped yet — honest about limitations.

**"Why not just check GitHub stars?"**
Stars are one of 15+ signals. An agent with 10K stars but 3 unpatched CRITICAL CVEs should get flagged. Security dimension is independent of popularity.
