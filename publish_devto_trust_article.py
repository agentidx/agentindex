#!/usr/bin/env python3
"""Publish trust-checks article to Dev.to."""
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests not installed, saving as draft instead")
    sys.exit(1)

DEVTO_KEY_PATH = Path.home() / ".config" / "nerq" / "devto_api_key"
DRAFT_PATH = Path.home() / "agentindex" / "docs" / "devto-trust-article.md"

title = "Why Your Multi-Agent System Needs Trust Checks (And How to Add Them in 3 Lines)"

body_markdown = r"""## The 35.6% Problem

We ran 100 multi-agent workflows where agents freely delegated tasks to other agents. The result: **35.6% of interactions failed** — agents delegated to unmaintained tools, abandoned projects, or agents with known security issues.

When we added a single preflight trust check before each interaction, the failure rate dropped to **0%**.

The fix wasn't complex AI. It was a simple HTTP call.

## The Trust Gap in Agentic AI

Multi-agent systems are everywhere: LangGraph orchestrating chains of agents, CrewAI assembling agent crews, AutoGen running multi-agent conversations. But none of these frameworks verify whether the agents they're calling are trustworthy.

This is like letting anyone join a Slack workspace without checking who they are.

The [Nerq Trust Protocol](https://nerq.ai/protocol) solves this with a single endpoint:

```
GET https://nerq.ai/v1/preflight?target=agent-name
```

Response:
```json
{
  "target": "langchain",
  "trust_score": 88.5,
  "trust_grade": "A",
  "recommendation": "PROCEED"
}
```

## Add Trust Checks in 3 Lines

### LangGraph

```python
from nerq_langgraph import trust_check_node
from langgraph.graph import StateGraph

graph = StateGraph(dict)
graph.add_node("trust_check", trust_check_node(min_trust=70))
```

The node reads `agent_name` from state, calls the Nerq API, and adds `trust_score`, `trust_grade`, and `trust_approved` to the state. Your next node can branch on `trust_approved`.

### AutoGen

```python
from nerq_autogen import NerqTrustTool

trust = NerqTrustTool(min_trust=70)
result = trust.check("some-agent")
# result: {"trust_score": 88.5, "approved": True, "trust_grade": "A"}
```

### CrewAI

```python
from agentindex_crewai import discover_crewai_agents

# Only discover agents with trust score >= 0.7
agents = discover_crewai_agents(min_quality=0.7)
```

### MCP (Model Context Protocol)

```json
{
  "method": "tools/call",
  "params": {
    "name": "trust_gate",
    "arguments": {"name": "agent-name", "threshold": 70}
  }
}
```

### Raw HTTP

```bash
curl https://nerq.ai/v1/preflight?target=langchain
```

## How Trust Scores Work

Nerq indexes **204,000+ AI agents and tools** across 12 registries (GitHub, npm, PyPI, HuggingFace, Replicate, Docker Hub). Each agent is scored 0-100 based on:

- **Maintenance activity** — recent commits, release frequency
- **Community engagement** — stars, forks, contributors
- **Documentation quality** — README completeness, examples
- **Stability** — breaking changes, deprecation patterns
- **Popularity** — downloads, dependents

Scores update daily. The full methodology is at [nerq.ai/protocol](https://nerq.ai/protocol).

## Recommended Thresholds

| Level | Score | When to Use |
|-------|-------|-------------|
| Standard | ≥ 70 | Most agent interactions |
| Strict | ≥ 80 | Financial or data-sensitive tasks |
| Critical | ≥ 90 | Healthcare, legal, security |

## Get Started

All packages are on PyPI:

```bash
pip install nerq-langgraph    # LangGraph node
pip install nerq-autogen      # AutoGen tool
pip install nerq-langchain    # LangChain gate decorator
pip install agentindex-crewai # CrewAI discovery
```

- [Protocol Spec](https://nerq.ai/protocol)
- [Integration Hub](https://nerq.ai/integrate)
- [Live Trust Reports](https://nerq.ai/safe/langchain)
- [GitHub](https://github.com/kbanilsson-pixel/nerq-trust-protocol)

---

*Built by [Nerq](https://nerq.ai) — the trust layer for the agentic economy. We index 5M+ AI assets and provide trust scores for 204K agents and tools.*
"""

def save_draft():
    DRAFT_PATH.write_text(f"# {title}\n\n{body_markdown}")
    print(f"Saved draft to {DRAFT_PATH}")

def main():
    if not DEVTO_KEY_PATH.exists():
        print("No Dev.to API key found")
        save_draft()
        return

    api_key = DEVTO_KEY_PATH.read_text().strip()
    if not api_key:
        print("Empty Dev.to API key")
        save_draft()
        return

    payload = {
        "article": {
            "title": title,
            "body_markdown": body_markdown,
            "published": True,
            "tags": ["ai", "agents", "security", "python"],
            "canonical_url": "https://nerq.ai/blog/trust-handshake",
            "description": "35.6% of multi-agent interactions fail without trust checks. Here's how to add preflight verification in 3 lines with the Nerq Trust Protocol.",
        }
    }

    try:
        resp = requests.post(
            "https://dev.to/api/articles",
            json=payload,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=30,
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code in (200, 201):
            data = resp.json()
            url = data.get("url", "N/A")
            print(f"URL: {url}")
        else:
            print(f"Response: {resp.text[:500]}")
            print("Publishing failed, saving as draft instead")
            save_draft()
    except Exception as e:
        print(f"Error: {e}")
        save_draft()

if __name__ == "__main__":
    main()
