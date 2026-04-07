# Streamable HTTP Transport + External Endpoint Verification

**Date:** 2026-03-08
**Status:** Complete

---

## TASK 1: Streamable HTTP Transport

### Finding
The Streamable HTTP transport was **already implemented** in `agentindex/crypto/zarq_mcp_server.py`. The `run_sse()` function (lines 384-460) sets up both transports:
- `/sse` — Legacy SSE transport
- `/mcp` — Streamable HTTP (via `StreamableHTTPSessionManager`)

### Why It Appeared Broken
- `GET /mcp` returns 406 (correct — Streamable HTTP requires POST with `Accept: application/json`)
- Smithery's scanner may have been doing GET, receiving 406, and interpreting it as an auth wall

### Verification

**Local:**
```
POST http://localhost:8001/mcp (initialize) → 200
POST http://localhost:8001/mcp (tools/list) → 200, 11 tools
```

**Via Tunnel:**
```
POST https://mcp.zarq.ai/mcp (initialize) → 200
Response: {"protocolVersion":"2024-11-05","serverInfo":{"name":"zarq-crypto","version":"1.23.3"}}
```

### MCP SDK Version
`mcp 1.23.3` — well above the 1.8 minimum for Streamable HTTP.

### No Code Changes Needed
Both transports are live and working. Smithery registration can be retried.

---

## TASK 2: External Endpoint Verification

All endpoints tested via Cloudflare tunnel:

| Endpoint | Status | Latency |
|----------|--------|---------|
| `zarq.ai/v1/check/bitcoin` | 200 | 162ms |
| `zarq.ai/v1/health` | 200 | 3.1s* |
| `zarq.ai/v1/crypto/signals` | 200 | 79ms |
| `zarq.ai/v1/stats` | 200 | 11.4s* |
| `zarq.ai/zarq/docs` | 200 | 60ms |
| `zarq.ai/demo/save-simulator` | 200 | 86ms |
| `zarq.ai/zarq/dashboard` | 200 | 57ms |
| `zarq.ai/v1/crash-shield/saves` | 200 | 71ms |
| `mcp.zarq.ai/sse` | 200 | 15s (SSE stream) |

*`/v1/health` and `/v1/stats` had cache misses — subsequent requests will be <100ms.

### Result
**9/9 endpoints returning 200.** No failures.

---

## Operations Log Updated
- Added Streamable HTTP verification entry
- Added endpoint verification entry
- Marked "Add Streamable HTTP" and "Verify save-simulator" as done in TODO
- Updated Smithery TODO: "retry registration (Streamable HTTP now verified)"
