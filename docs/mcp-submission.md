# Nerq MCP Server — Registry Submissions

## Server Info

- **Name**: nerq
- **Description**: Trust scores for software, AI tools, and MCP servers. Check if any package, app, extension, or MCP server is safe before installing.
- **SSE Endpoint**: https://mcp.nerq.ai/sse
- **npx**: `npx nerq-gateway`
- **Website**: https://nerq.ai
- **API**: https://nerq.ai/v1/preflight?target={name}
- **Categories**: security, trust, safety, developer-tools
- **Author**: Nerq Trust Intelligence

## Tools Provided

1. **preflight** — Check trust score for any software entity
   - Input: `{ "target": "express" }`
   - Output: `{ "trust_score": 86, "grade": "A", "risk_level": "low", "safe": true }`

2. **compare** — Compare two entities side-by-side
   - Input: `{ "a": "express", "b": "fastify" }`

3. **alternatives** — Find safer alternatives
   - Input: `{ "tool": "express" }`

## Coverage

- 1.8M+ software entities across 20 registries
- npm, PyPI, Crates, NuGet, Go, Gems, Packagist, Homebrew
- Chrome extensions, Firefox add-ons, VS Code extensions
- WordPress plugins, iOS apps, Android apps, Steam games
- Websites, VPNs, SaaS platforms, AI tools, crypto tokens
- 26,706 MCP servers with trust scores

## Registries to Submit To

1. **Smithery** — https://smithery.ai (LIVE)
2. **Glama** — https://glama.ai (PENDING — Frank offered help)
3. **awesome-mcp-servers** — PR #2922 (PENDING)
4. **mcpt (Mintlify)** — https://mcpt.mintlify.com
5. **OpenTools** — https://opentools.ai
6. **mcp.so** — https://mcp.so
7. **MCP Hub** — https://mcphub.io
8. **PulseMCP** — https://pulsemcp.com
