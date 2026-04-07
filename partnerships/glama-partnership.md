# Partnership Proposal: Nerq + Glama

## The Opportunity

Glama is the leading MCP server registry. Nerq is the largest AI agent trust database. Together, we can add a trust layer to the MCP ecosystem.

## What Nerq Brings

- **Trust Scores** for 204,000+ AI agents and tools, including MCP servers
- **6-dimension scoring**: Code Quality, Community, Compliance, Operational Health, Security, External Validation
- **CVE detection** and vulnerability tracking for AI agents
- **Free API**: `GET /v1/preflight?target={server_name}` — no auth required
- **MCP-native**: We run an MCP server ourselves, so integration is seamless

## Proposed Integration

### Option A: Trust Badge on Glama listings
- Nerq provides an embeddable trust badge for each MCP server
- Badge shows trust score (0-100) and grade (A+ to F)
- Links back to full trust report on nerq.ai
- Implementation: `<img src="https://nerq.ai/badge/{server_name}.svg">`

### Option B: API-level integration
- Glama queries Nerq API when displaying server details
- Show trust score, security warnings, CVE alerts inline
- Response cached for 24h to minimize API calls

### Option C: Co-branded "Verified" program
- Servers scoring 80+ on Nerq get a "Trust Verified" badge on Glama
- Joint marketing: "Glama + Nerq Verified MCP Servers"
- Quarterly trust reports on the MCP ecosystem

## What We Ask

- Link to nerq.ai from Glama's resource pages or docs
- Consider displaying Nerq trust scores on MCP server listings
- Joint blog post announcing the partnership

## Contact

Anders Nilsson — anders@nerq.ai
https://nerq.ai
