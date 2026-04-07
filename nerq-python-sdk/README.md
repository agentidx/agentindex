# nerq

Python SDK for the [Nerq Trust API](https://nerq.ai) — preflight trust checks for AI agents and MCP servers.

Nerq indexes 204K+ AI agents from GitHub, npm, PyPI, HuggingFace, and MCP registries with Trust Scores (0-100) based on code quality, community adoption, compliance, operational health, and security (CVE data).

## Install

```bash
pip install nerq
```

## Quick Start

```python
from nerq import NerqClient

client = NerqClient()

# Preflight trust check
result = client.preflight("langchain-ai/langchain")
print(result.trust_score)       # 82.4
print(result.trust_grade)       # B+
print(result.recommendation)    # PROCEED
print(result.cve_count)         # 0
```

## Preflight Check

Verify an agent's trustworthiness before using it:

```python
r = client.preflight("some-unknown-agent")

if r.is_safe():
    # Trust score >= 60, no critical CVEs
    use_agent()
elif r.should_deny():
    # Trust score < 30 or critical issues
    print(f"Denied: {r.trust_grade}")
    print(f"Try instead: {r.alternatives}")
else:
    # CAUTION — review before proceeding
    print(f"Score: {r.trust_score}, CVEs: {r.cve_count}")
```

## Batch Preflight

Check up to 50 agents in one request:

```python
batch = client.preflight_batch(["langchain", "crewai", "autogen", "phidata"])

for name, r in batch.items():
    print(f"{name}: {r.trust_grade} ({r.recommendation})")

# Filter results
safe = batch.safe_agents()      # ["langchain", "crewai"]
denied = batch.denied_agents()  # []
print(f"Not found: {batch.not_found}")
```

## Search Agents

```python
agents = client.search("code review tools", limit=10)
for a in agents:
    print(f"{a.name} — {a.trust_score} ({a.source})")
```

## Commerce Trust Gate

Verify trust before agent-to-agent transactions:

```python
verdict = client.commerce_verify(
    agent_id="my-payment-agent",
    counterparty_id="seller-agent",
    transaction_type="payment",
    amount_range="high",
)

if verdict.is_approved():
    proceed_with_transaction()
elif verdict.needs_review():
    flag_for_human_review()
```

## API Key (Optional)

Free tier: 100 requests/hour, no key required.

```python
# For higher rate limits
client = NerqClient(api_key="your_api_key")
```

Get an API key at [nerq.ai/start](https://nerq.ai/start).

## Trust Score Components

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Code Quality | 25% | Description, capabilities, naming |
| Community | 25% | Stars, downloads, forks |
| Compliance | 20% | License, EU AI Act risk class |
| Operational Health | 15% | Update recency, activity |
| Security | 15% | CVE count, severity |

## Links

- [Nerq](https://nerq.ai) — Search 204K+ AI agents
- [API Docs](https://nerq.ai/nerq/docs) — Full API documentation
- [Trust Protocol](https://nerq.ai/protocol) — How trust scores work
