# Smithery Server Card

**Date:** 2026-03-08
**Status:** Complete

---

## What Was Done

Updated the existing `/.well-known/mcp/server-card.json` route in `agentindex/crypto/zarq_mcp_server.py` to follow the MCP server-card spec:

### Changes
- Added `serverInfo` object with `name` and `version` (required by spec)
- Added `authentication: { required: false }`
- Changed `transport` from array of strings to object: `{ type: "streamable-http", url: "https://mcp.zarq.ai/mcp" }`
- Changed `tools` from list of names to full tool definitions with `name`, `description`, and `inputSchema`

### File Modified
- `agentindex/crypto/zarq_mcp_server.py` — `handle_server_card()` function

### Service Restart
- `launchctl stop/start com.zarq.mcp-sse`

## Verification

```
$ curl https://mcp.zarq.ai/.well-known/mcp/server-card.json

serverInfo: {name: zarq-crypto, version: 1.1.0}
transport: {type: streamable-http, url: https://mcp.zarq.ai/mcp}
authentication: {required: false}
tools: 11 (with full schemas)
```

## Ready for Smithery
Smithery should now be able to discover and scan the server via:
1. `GET https://mcp.zarq.ai/.well-known/mcp/server-card.json` — server metadata + 11 tools with schemas
2. `POST https://mcp.zarq.ai/mcp` — Streamable HTTP transport (with `Accept: application/json`)
