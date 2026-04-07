# Nerq Agent Trust Protocol v1.0

**Version:** 1.0
**Status:** Draft
**Date:** 2026-03-12
**Authors:** ZARQ Intelligence AB

## Abstract

A lightweight HTTP protocol for AI agents to verify the trustworthiness of other agents before interaction. Designed for the agentic economy where autonomous agents must make trust decisions in real time.

## 1. Overview

The agentic economy is accelerating: Stripe launched agent-to-agent payments, stablecoin settlement hit $110T annualized, and frameworks like LangGraph and CrewAI enable multi-agent systems by default. But there is no standard way for agents to verify each other.

The cost of operating without trust verification:
- **35.6% failure rate** in agent interactions without trust checks (0% with checks, N=100, p<0.00000001)
- **60%** of organizations report they don't fully trust their AI agents (Deloitte 2025)
- **40%+** of agentic AI projects may be canceled by 2028 due to missing risk controls (Gartner)

The Nerq Trust Protocol provides a simple, stateless HTTP interface for agents to query trust scores before interacting with other agents.

## 2. Trust Query

### Request

```
GET /v1/preflight?target={agent_name}&caller={caller_name}
Host: nerq.ai
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `target` | Yes | Name or identifier of the agent to check |
| `caller` | No | Name of the requesting agent (for audit logging and bidirectional trust) |

### Response

```json
{
  "target": "langchain",
  "target_trust": 88.5,
  "target_grade": "A",
  "target_verified": true,
  "target_category": "Framework",
  "target_source": "github",
  "target_last_updated": "2026-03-12T00:00:00+00:00",
  "caller": "my-agent",
  "caller_trust": 72.0,
  "caller_grade": "B+",
  "caller_verified": true,
  "interaction_risk": "LOW",
  "recommendation": "PROCEED",
  "compliance_flags": [],
  "checked_at": "2026-03-12T10:30:00+00:00"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `target` | string | Agent name queried |
| `target_trust` | number \| null | Trust score 0-100, null if agent not found |
| `target_grade` | string \| null | Letter grade (A+, A, B+, B, C, D, F) |
| `target_verified` | boolean \| null | Whether the agent meets verification threshold (trust >= 70) |
| `target_category` | string \| null | Agent category |
| `target_source` | string \| null | Registry source (github, npm, pypi, huggingface) |
| `target_last_updated` | string \| null | ISO 8601 timestamp of last index update |
| `caller` | string \| null | Caller agent name (echoed back) |
| `caller_trust` | number \| null | Caller's trust score (bidirectional trust) |
| `caller_grade` | string \| null | Caller's letter grade |
| `caller_verified` | boolean \| null | Whether caller meets verification threshold |
| `interaction_risk` | string | One of: LOW, MEDIUM, HIGH, UNKNOWN |
| `recommendation` | string | One of: PROCEED, CAUTION, DENY, UNKNOWN |
| `compliance_flags` | array | List of compliance warnings (see Section 2.1) |
| `checked_at` | string | ISO 8601 timestamp of this check |

### 2.1 Compliance Flags

| Flag | Condition |
|------|-----------|
| `TARGET_LOW_TRUST` | Target trust score < 40 |
| `CALLER_LOW_TRUST` | Caller trust score < 40 |
| `TARGET_NOT_VERIFIED` | Target trust score < 70 |

### Status Codes

| Code | Meaning |
|------|---------|
| 200 | Query executed (check `target_trust` for null = not found) |
| 422 | Missing required `target` parameter |
| 429 | Rate limited (retry after header) |
| 500 | Internal error |

Note: A 200 response with `target_trust: null` and `recommendation: "UNKNOWN"` indicates the agent was not found in the index. The protocol does not use 404 for unknown agents — the response always contains a full recommendation envelope.

### Recommendation Logic

| Condition | Recommendation |
|-----------|---------------|
| target_trust >= 70 AND (caller_trust is null OR caller_trust >= 40) | PROCEED |
| target_trust >= 40 AND not meeting PROCEED criteria | CAUTION |
| target_trust < 40 | DENY |
| target_trust is null | UNKNOWN |

### Interaction Risk Logic

| Condition | Risk Level |
|-----------|-----------|
| target_trust >= 70 AND (caller_trust is null OR caller_trust >= 50) | LOW |
| target_trust >= 40 | MEDIUM |
| target_trust < 40 | HIGH |
| target_trust is null | UNKNOWN |

## 3. Trust Gate

A Trust Gate is a threshold-based binary decision point. Implementations SHOULD support configurable thresholds.

### Recommended Thresholds

| Level | Threshold | Use Case |
|-------|-----------|----------|
| Standard | 70 | General-purpose agent interactions |
| Strict | 80 | Financial transactions, data access |
| Critical | 90 | Healthcare, legal, security operations |

### Decision Flow

```
1. Agent A wants to interact with Agent B
2. Agent A calls GET /v1/preflight?target=B&caller=A
3. If target_trust >= threshold: APPROVE
4. If target_trust < threshold: REJECT
5. If target_trust is null (UNKNOWN): REJECT (fail-closed)
```

## 4. Batch Query

For checking multiple agents in a single call.

### Request

```
POST /v1/preflight/batch
Content-Type: application/json

{
  "targets": ["langchain", "crewai", "unknown-agent"],
  "caller": "orchestrator-agent",
  "threshold": 70
}
```

### Response

```json
{
  "results": [
    {"target": "langchain", "target_trust": 88.5, "target_grade": "A", "recommendation": "PROCEED", "approved": true},
    {"target": "crewai", "target_trust": 82.0, "target_grade": "A-", "recommendation": "PROCEED", "approved": true},
    {"target": "unknown-agent", "target_trust": null, "target_grade": null, "recommendation": "UNKNOWN", "approved": false}
  ],
  "summary": {"total": 3, "approved": 2, "rejected": 1},
  "checked_at": "2026-03-12T10:30:00+00:00"
}
```

## 5. Caching

Implementations SHOULD cache trust query results.

| Parameter | Recommended Value |
|-----------|-------------------|
| TTL | 300 seconds (5 minutes) — matches server-side cache |
| Cache key | `nerq:preflight:{target}:{caller}` |
| Invalidation | On TTL expiry only |
| Stale-while-revalidate | 60 seconds |
| Max cache entries | 10,000 (server evicts all on overflow) |

Trust scores are recomputed daily. The server maintains a 5-minute in-memory cache keyed on (target, caller). Client-side caching with a 1-hour TTL is acceptable for most use cases.

## 6. Integration Patterns

### LangGraph Node

```python
from nerq_langgraph import trust_check_node
graph.add_node("trust_check", trust_check_node(min_trust=70))
```

### CrewAI Tool

```python
from agentindex_crewai import discover_crewai_agents
agents = discover_crewai_agents(min_quality=0.7)
```

### AutoGen Tool

```python
from nerq_autogen import NerqTrustTool
trust = NerqTrustTool(min_trust=70)
result = trust.check("agent-name")
```

### MCP Tool

```json
{"method": "tools/call", "params": {"name": "trust_gate", "arguments": {"name": "agent-name", "threshold": 70}}}
```

### Raw HTTP

```bash
curl https://nerq.ai/v1/preflight?target=langchain&caller=my-agent
```

## 7. A2A Trust Handshake

When using the [Agent-to-Agent Protocol](https://google.github.io/A2A/), agents SHOULD perform a trust check before initiating a task.

### Flow

```
1. Agent A discovers Agent B via /.well-known/agent.json
2. Agent A calls Nerq: GET /v1/preflight?target=B&caller=A
3. If recommendation is PROCEED: Agent A sends JSON-RPC task to Agent B
4. If recommendation is DENY or UNKNOWN: Agent A logs rejection, finds alternative
5. If recommendation is CAUTION: Agent A proceeds with enhanced monitoring
```

### Agent Card Extension

Agents MAY include their Nerq trust score in their agent.json:

```json
{
  "name": "my-agent",
  "trust": {
    "provider": "nerq.ai",
    "score_url": "https://nerq.ai/v1/preflight?target=my-agent",
    "badge_url": "https://nerq.ai/badge/my-agent"
  }
}
```

## Appendix A: Full Response Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["target", "recommendation", "interaction_risk", "checked_at"],
  "properties": {
    "target": {"type": "string"},
    "target_trust": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
    "target_grade": {"type": ["string", "null"]},
    "target_verified": {"type": ["boolean", "null"]},
    "target_category": {"type": ["string", "null"]},
    "target_source": {"type": ["string", "null"]},
    "target_last_updated": {"type": ["string", "null"], "format": "date-time"},
    "caller": {"type": ["string", "null"]},
    "caller_trust": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
    "caller_grade": {"type": ["string", "null"]},
    "caller_verified": {"type": ["boolean", "null"]},
    "interaction_risk": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "UNKNOWN"]},
    "recommendation": {"type": "string", "enum": ["PROCEED", "CAUTION", "DENY", "UNKNOWN"]},
    "compliance_flags": {
      "type": "array",
      "items": {"type": "string", "enum": ["TARGET_LOW_TRUST", "CALLER_LOW_TRUST", "TARGET_NOT_VERIFIED"]}
    },
    "checked_at": {"type": "string", "format": "date-time"}
  }
}
```

## Appendix B: Example Implementations

### Python (requests)

```python
import requests

def check_trust(target, caller=None, threshold=70):
    params = {"target": target}
    if caller:
        params["caller"] = caller
    r = requests.get("https://nerq.ai/v1/preflight", params=params)
    data = r.json()
    return {
        "approved": data["target_trust"] is not None and data["target_trust"] >= threshold,
        "recommendation": data["recommendation"],
        "risk": data["interaction_risk"],
        "flags": data["compliance_flags"],
    }
```

### JavaScript (fetch)

```javascript
async function checkTrust(target, caller = null, threshold = 70) {
  const params = new URLSearchParams({ target });
  if (caller) params.set("caller", caller);
  const r = await fetch(`https://nerq.ai/v1/preflight?${params}`);
  const data = await r.json();
  return {
    approved: data.target_trust !== null && data.target_trust >= threshold,
    recommendation: data.recommendation,
    risk: data.interaction_risk,
    flags: data.compliance_flags,
  };
}
```

### Go

```go
func checkTrust(target string, threshold float64) (bool, error) {
    resp, err := http.Get("https://nerq.ai/v1/preflight?target=" + url.QueryEscape(target))
    if err != nil {
        return false, err
    }
    defer resp.Body.Close()
    var result map[string]interface{}
    json.NewDecoder(resp.Body).Decode(&result)
    trust, ok := result["target_trust"].(float64)
    if !ok {
        return false, nil // UNKNOWN — fail closed
    }
    return trust >= threshold, nil
}
```

---

*Nerq Agent Trust Protocol v1.0 -- Published by [ZARQ Intelligence AB](https://zarq.ai). Feedback: dev@zarq.ai*
*Index: [nerq.ai](https://nerq.ai) | Protocol: [nerq.ai/protocol](https://nerq.ai/protocol) | Integrations: [nerq.ai/integrate](https://nerq.ai/integrate)*
