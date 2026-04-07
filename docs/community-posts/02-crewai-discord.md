# CrewAI Discord Post

**Channel:** #showcase or #general

**Body:**

Hey everyone — just released `nerq-crewai`, a trust verification package for CrewAI.

When you're assembling a crew, you might want to verify that the tools and agents you're connecting are actually maintained, secure, and compliant. We index 204K agents & tools and score them across security, compliance, maintenance, popularity, and ecosystem factors.

**Install:**

```
pip install nerq-crewai
```

**Trust-gate your crew — all tool calls verified:**

```python
from crewai import Agent, Crew, Task
from nerq_crewai import trust_gate_crew

researcher = Agent(role="Researcher", goal="Find data", ...)
writer = Agent(role="Writer", goal="Write report", ...)

crew = Crew(agents=[researcher, writer], tasks=[...])

# Add trust verification — tools with trust < 60 are blocked
trust_gate_crew(crew, min_trust=60)
result = crew.kickoff()
```

**Discover trusted agents for your crew:**

```python
from nerq_crewai import NerqCrewBuilder

builder = NerqCrewBuilder()
agents = builder.discover_agents(
    capabilities=["code review", "security"],
    min_trust_score=75
)
```

Also useful:
- `nerq.ai/v1/agent/kya/{name}` — full due diligence report
- `nerq.ai/mcp-servers` — 25K MCP servers with trust scores
- `nerq.ai/badge/{name}` — SVG trust badge for your README

Free API, no auth, 5000 req/day. Docs: nerq.ai/integrate/crewai

Would love to hear what trust signals matter most for your crews.
