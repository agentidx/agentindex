# MCP Server Registration Guide — ZARQ Crypto Risk Intelligence

## Server Details

- **Name:** zarq-crypto
- **Version:** 1.1.0
- **Public SSE URL:** `https://mcp.zarq.ai/sse`
- **Streamable HTTP URL:** `https://mcp.zarq.ai/mcp`
- **Health Check:** `https://mcp.zarq.ai/health`
- **Server Card:** `https://mcp.zarq.ai/.well-known/mcp/server-card.json`

## Tools Exposed (11)

| Tool | Description |
|------|-------------|
| `check_token_risk` | Zero-friction risk check. Returns verdict, trust score, crash probability |
| `get_trust_score` | Trust Score only: score (0-100), rating (Aaa-D), verdict |
| `get_risk_signals` | All tokens with active warnings, filterable by level |
| `crypto_safety_check` | Pre-trade safety check (<100ms) |
| `crypto_rating` | Full Trust Score with 5-pillar breakdown |
| `crypto_dtd` | Distance-to-Default with 7 signals |
| `crypto_signals` | Active trading signals and alerts |
| `crypto_compare` | Head-to-head token comparison |
| `crypto_distress_watch` | All tokens with DtD < 2.0 |
| `crypto_alerts` | Structural Collapse and Stress alerts |
| `crypto_ratings_bulk` | All 205 token ratings in bulk |

## Smithery Registration

**URL:** https://smithery.ai/server/new

**Required info:**
- Server name: `zarq-crypto`
- Display name: ZARQ Crypto Risk Intelligence
- Description: Independent crypto risk intelligence: Trust Score ratings (Aaa-D) for 205 tokens, Distance-to-Default (DtD) with 7 signals, structural collapse warnings (100% recall, 98% precision OOS), crash probability, and zero-friction risk checks. Free API, no auth required.
- SSE URL: `https://mcp.zarq.ai/sse`
- Homepage: `https://zarq.ai`
- Tags: crypto, risk, defi, safety, trust-score, crash-prediction, distance-to-default, ratings, blockchain, token-analysis

**Smithery config block** (already in zarq_mcp_server.py as `SMITHERY_CONFIG`):
```json
{
  "name": "zarq-crypto",
  "display_name": "ZARQ Crypto Risk Intelligence",
  "version": "1.1.0",
  "author": "ZARQ",
  "homepage": "https://zarq.ai",
  "tools": 11
}
```

## Glama Registration

**URL:** https://glama.ai/mcp/servers/submit

**Required info:**
- MCP Server URL: `https://mcp.zarq.ai/sse`
- Name: ZARQ Crypto Risk Intelligence
- Description: (same as above)
- Category: Finance / Crypto
- Auth: None (free, no auth required)
- Rate limit: 500 calls/day per IP

## Manifest / Server Card Schema

The server exposes `/.well-known/mcp/server-card.json`:

```json
{
  "name": "zarq-crypto",
  "display_name": "ZARQ Crypto Risk Intelligence",
  "description": "...",
  "version": "1.1.0",
  "author": "ZARQ",
  "homepage": "https://zarq.ai",
  "transport": ["sse", "streamable-http"],
  "sse_url": "https://mcp.zarq.ai/sse",
  "streamable_http_url": "https://mcp.zarq.ai/mcp",
  "tools": ["check_token_risk", "get_risk_signals", "get_trust_score", ...],
  "tags": ["crypto", "risk", ...]
}
```

## Cloudflare Configuration

The MCP server is publicly reachable via Cloudflare Tunnel:

- **Tunnel ID:** a17d8bfb-9596-4700-848a-df481dc171ad
- **Public hostname:** `mcp.zarq.ai`
- **Origin:** `http://localhost:8001`
- **Transport:** The tunnel forwards HTTPS traffic to the local Starlette/Uvicorn server on port 8001

No additional Cloudflare config is needed — the tunnel is already active and routing correctly. Both SSE and Streamable HTTP transports work through the tunnel.

To verify:
```bash
curl https://mcp.zarq.ai/health
# → {"status":"ok","server":"zarq-crypto","version":"1.1.0"}
```

## Claude Desktop Configuration

To use this MCP server in Claude Desktop, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "zarq-crypto": {
      "url": "https://mcp.zarq.ai/sse"
    }
  }
}
```

## Testing

```bash
# Initialize session
curl -X POST https://mcp.zarq.ai/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'

# List tools
curl -X POST https://mcp.zarq.ai/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

# Call check_token_risk
curl -X POST https://mcp.zarq.ai/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"check_token_risk","arguments":{"token":"bitcoin"}}}'
```
