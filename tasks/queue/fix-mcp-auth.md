# Fix MCP Auth Wall — Smithery Cannot Scan mcp.zarq.ai/sse

**Date:** 2026-03-08
**Status:** Investigation Complete — Action Required (Anders)

---

## Problem

Smithery reports an "authorization wall" when trying to scan `mcp.zarq.ai/sse`. This blocks MCP server registration on Smithery.

## Investigation Findings

### 1. MCP Server Code — No Auth Middleware

Grepped `mcp_sse_server.py` and `mcp_sse_server_v2.py` for auth/bearer/token patterns. **No access control middleware found.** The server accepts all connections without authentication.

### 2. Cloudflare Tunnel Config — Clean

`~/.cloudflared/config.yml` routes:
- `mcp.zarq.ai` → `localhost:8001` (no Access policies)
- No `access` or `originRequest` blocks on the MCP ingress rule

### 3. Local Testing — All 200

| Test | Result |
|------|--------|
| `GET /health` | 200 — `{"status":"ok","server":"zarq-crypto","version":"1.1.0"}` |
| `GET /sse` | 200 — SSE stream: `event: endpoint\ndata: /messages?session_id=...` |
| `GET /sse` (UA: Smithery) | 200 |
| `GET /sse` (UA: Bot) | 200 |
| `GET /sse` (empty UA) | 200 |
| `POST /sse` | 405 (expected — SSE is GET-only) |
| `GET /mcp` | 406 (no Streamable HTTP transport) |
| `POST /messages` (no session_id) | 400 — `"session_id is required"` |

### 4. Root Cause Hypotheses (ranked by likelihood)

**A. Cloudflare WAF / Bot Management (MOST LIKELY)**
Cloudflare may be blocking Smithery's scanner at the edge before traffic reaches the tunnel. This would not be visible in tunnel config — it's configured in the Cloudflare Zero Trust dashboard or DNS-level WAF rules. Smithery's scanner likely triggers bot detection.

**B. Protocol Mismatch**
Smithery may expect the newer **MCP Streamable HTTP** transport (single `/mcp` endpoint, bidirectional HTTP) rather than the legacy **SSE transport** (`/sse` + `/messages`). Our `/mcp` endpoint returns 406. If Smithery tries `/mcp` first and gets 406, it may report this as an "auth wall."

**C. Session Handshake Failure**
The SSE transport requires a two-step flow:
1. `GET /sse` → receive `session_id` in SSE event
2. `POST /messages?session_id=<id>` → send requests

If Smithery's scanner doesn't complete step 1 before attempting step 2, it gets a 400 error.

## Required Actions (Anders)

### Immediate — Check Cloudflare Dashboard
1. Log into [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)
2. Go to **Access → Applications** — check if `mcp.zarq.ai` has an Access policy
3. Go to **WAF → Security Rules** — check if bot management or rate limiting blocks Smithery
4. Go to **Security → Bots** — check if Bot Fight Mode is enabled for the zone
5. If any rules block legitimate bots, add an exception for Smithery's IP range or user agent

### If Cloudflare Is Clean — Check Protocol
1. Ask Smithery support which transport they expect (SSE vs Streamable HTTP)
2. If they need Streamable HTTP at `/mcp`, we need to add that transport to our MCP server
3. Smithery docs may specify the expected endpoint format

### Workaround — Manual Registration
If scanning remains blocked, Smithery allows manual server registration:
- URL: `https://mcp.zarq.ai/sse`
- Transport: SSE
- See `docs/manual-registration-guide.md` for step-by-step

## Files Relevant
- `agentindex/mcp_sse_server.py` — current MCP server (port 8001)
- `~/.cloudflared/config.yml` — tunnel routing
- `docs/manual-registration-guide.md` — manual registration steps
