# nerq-crewai

**Trust verification for CrewAI crews**

[![Nerq Badge](https://nerq.ai/badge/crewai)](https://nerq.ai/integrate/crewai)

Discover trusted AI agents and gate every tool call with [Nerq](https://nerq.ai) preflight trust checks before your CrewAI crew executes.

## Install

```bash
pip install nerq-crewai
```

## Quick start

```python
from nerq_crewai import NerqCrewBuilder, trust_gate_crew

# 1. Discover and build a crew from trusted agents
builder = NerqCrewBuilder(api_key="your-key")
crew = builder.build_crew(
    task_description="Analyze competitor pricing",
    roles=["researcher", "analyst", "writer"],
    min_trust_score=80,
)

# 2. Gate all tool calls with Nerq trust verification
crew = trust_gate_crew(crew, min_trust=60)

# 3. Run — any untrusted tool call raises TrustError
result = crew.kickoff()
```

## Trust gate behaviour

Before every tool invocation, `trust_gate_crew` checks the tool against the Nerq preflight API:

| Recommendation | Trust score | Action |
|---|---|---|
| **PROCEED** | >= 70 | Silent pass-through |
| **CAUTION** | 40 - 69 | Logs warning, proceeds |
| **DENY** | < 40 | Raises `TrustError` |
| **UNKNOWN** | n/a | Logs warning, proceeds |

Any tool whose trust score falls below `min_trust` also raises `TrustError`.

## Discover trusted tools

```python
from nerq_crewai import NerqCrewBuilder

builder = NerqCrewBuilder()
tools = builder.discover_trusted_tools("code-generation", min_trust=70)
for t in tools:
    print(f"{t['name']}  trust={t['trust_score']}")
```

## Convenience functions

```python
from nerq_crewai import discover_crewai_agents, build_crew_from_discovery

# Find agents for a capability
agents = discover_crewai_agents("web scraping", min_trust_score=75)

# One-liner crew
crew = build_crew_from_discovery(
    task="Summarize top 10 AI news stories",
    roles=["researcher", "writer"],
)
```

## Links

- Documentation: [nerq.ai/integrate/crewai](https://nerq.ai/integrate/crewai)
- API reference: [nerq.ai/docs](https://nerq.ai/docs)
- Source: [github.com/nerq-ai/nerq-crewai](https://github.com/nerq-ai/nerq-crewai)
