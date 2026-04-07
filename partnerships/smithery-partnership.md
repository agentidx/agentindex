# Partnership Proposal: Nerq + Smithery

## Overview

Smithery is a fast-growing MCP server registry. Nerq indexes 204,000+ AI agents with trust scores. We propose adding a trust verification layer to Smithery's registry.

## Integration Options

### 1. Trust Score Display
- Show Nerq trust score (0-100) and grade on each server's page
- API call: `GET https://nerq.ai/v1/preflight?target={server_name}`
- Badge embed: `<img src="https://nerq.ai/badge/{name}.svg">`

### 2. Security Alerts
- Surface CVE alerts for MCP servers with known vulnerabilities
- Nerq tracks 259+ CVEs across the AI agent ecosystem
- Alert data via: `GET https://nerq.ai/v1/trust/{agent_id}`

### 3. "Smithery Verified" Program
- Joint trust verification for top MCP servers
- Servers scoring 80+ get verified status
- Quarterly ecosystem trust reports

## Value for Smithery
- Differentiation: first registry with independent trust scores
- User trust: developers see security status before installing
- SEO: co-branded trust content drives organic traffic

## Value for Nerq
- Distribution: reach Smithery's developer audience
- Data: more MCP server coverage in our index
- Credibility: partnership with established registry

## Contact

Anders Nilsson — anders@nerq.ai
https://nerq.ai
