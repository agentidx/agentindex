# AutoGen GitHub Discussion

**Title:** Trust verification layer for multi-agent systems — free API for agent-to-agent preflight checks

**Category:** Show and Tell

**Body:**

When building multi-agent systems with AutoGen, agents frequently need to interact with external tools, APIs, and other agents. But there's no standard way to assess whether those external components are trustworthy, maintained, or compliant.

We built Nerq — an index of 204K AI agents and tools with trust scores (0–100). The key endpoint for multi-agent systems:

```python
import requests

def preflight_check(target: str, caller: str) -> dict:
    """Check trust before agent-to-agent interaction."""
    resp = requests.get("https://nerq.ai/v1/preflight", params={
        "target": target,
        "caller": caller
    })
    return resp.json()
    # Returns: {"recommendation": "PROCEED"|"CAUTION"|"DENY",
    #           "target_trust": 72, "caller_trust": 85, ...}
```

**Use cases for AutoGen:**
- Gate tool selection: only allow tools with trust >= 50
- Pre-flight check before agent-to-agent communication
- Compliance verification across 52 jurisdictions
- Know Your Agent (KYA) due diligence reports

**Other endpoints:**
- `GET /v1/agent/kya/{name}` — full agent profile with risk assessment
- `GET /v1/agent/search?q=...&min_trust=50` — search with trust filters
- `POST /compliance/check` — check regulatory compliance (EU AI Act, US state laws, etc.)
- `GET /badge/{name}` — SVG trust badge for READMEs

All free, no auth required. 5M+ AI assets indexed total.

We also have a crypto risk API (ZARQ) for agents operating in DeFi — Moody's-style ratings for 15K tokens.

nerq.ai — search and explore
nerq.ai/nerq/docs — API documentation

Would love to hear how the AutoGen community thinks about trust in multi-agent systems.
