# Show HN: Nerq Trust Protocol – How AI agents verify each other before interaction

We built an open protocol for AI agents to check each other's trustworthiness before interacting. It's a single HTTP endpoint that returns a trust score, grade, and go/no-go recommendation.

**Why this matters:** We tested 100 multi-agent workflows — 35.6% of interactions failed when agents operated without trust checks. With preflight verification, the failure rate dropped to 0%. Meanwhile, 60% of organizations say they don't fully trust their AI agents (Deloitte), and Gartner predicts 40%+ of agentic AI projects will be canceled by 2028 due to missing risk controls. There's no standard way for agents to verify each other.

**How it works:** Any agent calls `GET https://nerq.ai/v1/preflight?target=agent-name` and gets back a trust score (0-100), grade (A+ to F), and recommendation (PROCEED/CAUTION/DENY). Integration is 3 lines in any framework:

```python
# LangGraph
from nerq_langgraph import trust_check_node
graph.add_node("trust_check", trust_check_node(min_trust=70))

# AutoGen
from nerq_autogen import NerqTrustTool
trust = NerqTrustTool(min_trust=70)

# Raw HTTP
curl https://nerq.ai/v1/preflight?target=langchain
```

We index 204K AI agents and tools across 12 registries (GitHub, npm, PyPI, HuggingFace, Replicate, Docker Hub) and score them on maintenance activity, community engagement, documentation quality, and stability. Scores update daily.

**Links:**
- Protocol spec: https://nerq.ai/protocol
- Integration hub: https://nerq.ai/integrate (LangGraph, AutoGen, CrewAI, MCP packages on PyPI)
- Live trust reports: https://nerq.ai/safe/langchain
- GitHub: https://github.com/kbanilsson-pixel/nerq-trust-protocol
- MCP server: 6 tools including trust_gate, trust_compare, trust_batch

Built by a solo founder. Feedback welcome — especially on threshold recommendations and caching strategy.
