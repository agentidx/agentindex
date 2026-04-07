# Partnership Proposal: Nerq as Trust Layer for the MCP Ecosystem

## Context

The Model Context Protocol (MCP) ecosystem is growing rapidly. As of March 2026, there are 2,000+ MCP servers across registries (Glama, Smithery, mcp.run, npm). But there's no standard way to verify whether an MCP server is trustworthy before connecting to it.

Nerq solves this.

## What Nerq Offers the MCP Ecosystem

### 1. Pre-connection Trust Verification
Before an AI system connects to an MCP server, it can verify trust:
```
GET https://nerq.ai/v1/preflight?target=mcp-server-name
→ { "trust_score": 85, "grade": "A", "recommendation": "SAFE" }
```

### 2. MCP-Native Access
Nerq itself runs as an MCP server — agents can verify other agents using the same protocol:
```json
{ "tool": "check_trust", "arguments": { "agent_name": "target-server" } }
```

### 3. Ecosystem Trust Reports
- Weekly trust reports on the MCP ecosystem
- CVE alerts for MCP servers
- Trending trust score changes

### 4. Trust Badge for Registries
Any MCP registry can embed Nerq trust badges:
```html
<img src="https://nerq.ai/badge/{server}.svg">
```

## Proposed Actions

1. **Registries**: Display Nerq trust scores on server listings
2. **SDK maintainers**: Add optional trust verification before tool execution
3. **MCP spec**: Consider trust verification as a recommended practice
4. **Joint content**: Ecosystem trust reports, best practices guides

## About Nerq

- 204,000+ AI agents and tools indexed
- 4.7M+ models and datasets tracked
- 259+ CVEs monitored
- Free API, no authentication required
- Used by ChatGPT, Perplexity, and other AI systems for agent verification

## Contact

Anders Nilsson — anders@nerq.ai
https://nerq.ai | https://nerq.ai/docs
