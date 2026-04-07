# LangChain Forum Post

**Title:** Free trust scoring API for LangChain agents — rate 204K AI tools before your agent calls them

**Category:** Show and Tell

**Body:**

We built a trust scoring system that rates 204K AI agents and tools on a 0–100 scale, similar to how Moody's rates bonds. It's designed so LangChain agents can check whether a tool or another agent is trustworthy before interacting with it.

**The problem:** When your LangChain agent calls an external tool or communicates with another agent, there's no standard way to assess risk. Is that MCP server maintained? Does it have known vulnerabilities? Is it compliant with regulations in your jurisdiction?

**What we built:**

- `GET /v1/agent/kya/{name}` — Know Your Agent: returns trust score, risk level, compliance status
- `GET /v1/preflight?target={name}&caller={name}` — Pre-interaction trust check. Returns PROCEED/CAUTION/DENY
- Trust badges for READMEs: `nerq.ai/badge/{name}`

**Example — checking a tool before use:**

```python
import requests

def check_trust(tool_name: str) -> bool:
    resp = requests.get(f"https://nerq.ai/v1/agent/kya/{tool_name}")
    data = resp.json()
    return data.get("trust_score", 0) >= 50

# In your LangChain agent
if check_trust("some-mcp-server"):
    # safe to use
    ...
```

**Stats:** 5M+ AI assets indexed (204K agents & tools, 25K MCP servers, 4.7M models & datasets). 52 jurisdictions for compliance checks. Free API, no auth required.

We also have a crypto risk side (ZARQ) that does Moody's-style ratings for 15,000+ tokens — useful if your agent makes DeFi calls.

API docs: nerq.ai/nerq/docs
Search: nerq.ai/discover

Would love feedback from the LangChain community. What trust signals matter most when your agent is choosing tools?
