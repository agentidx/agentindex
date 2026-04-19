# agentindex.mcp — CHANGELOG

Change history for the Nerq MCP stdio/SSE tool pack. Existing v2 tool
schemas (`check_compliance`, `discover_agents`, `get_agent_details`,
`compliance_summary`, `nerq_stats`) remain byte-for-byte stable across
all releases documented here — every change is additive.

## [tools_v3.0] — 2026-04-19 (T214)

### Added — 10 new MCP tools (21..30)

All handlers read exclusively from the Nerq read-only replica via
`smedjan.sources.nerq_readonly_cursor`; no writes, no paid-API calls.

| # | Tool | Source | Required args |
|---|---|---|---|
| 21 | `get_rating` | `software_registry` (5 foundational dimensions) | `slug` |
| 22 | `get_signals` | `software_registry` (8 dimensions + CVE + audits + activity) | `slug` |
| 23 | `get_dependencies` | `software_registry.dependencies_count` + dormant-heuristic | `slug` |
| 24 | `compare_packages` | `software_registry` IN-query across 2–10 slugs | `slugs[]` |
| 25 | `find_similar` | `software_registry`, ranked by `|Δtrust_score|` within same registry | `slug` |
| 26 | `get_verticals` | Static `agentindex.ab_test.VERTICALS` + `quality_gate_state.json` counts | — |
| 27 | `list_by_registry` | `software_registry`, `ORDER BY trust_score DESC` | `registry` |
| 28 | `get_alternatives` | `software_registry`, higher `trust_score`, non-deprecated | `slug` |
| 29 | `get_trust_history` | `trust_changes` (old/new/change/reason per day) | `slug` |
| 30 | `search_by_dimension` | `software_registry`, filter + sort by one of 9 `*_score` cols | `dimension` |

### Schema stability

- `tools/list` now returns 15 tools (5 v2 + 10 v3). Client-side union
  merges cleanly; no v2 schema field was renamed, removed, or re-typed.
- Every v3 response carries `"schema_version": "nerq-mcp-tools/v3.0"`
  so clients can gate on structural changes.
- Every v3 tool returns a JSON-serialisable dict; error paths surface
  `{"error": "<reason>", …}` rather than raising (the v2 server wraps
  exceptions into `isError: true`).

### Validation

- Schema self-check: `TOOLS`/`TOOL_HANDLERS` name sets are asserted
  equal at import time; the module raises at load if they drift.
- Smoke-tested against the local Nerq RO replica on 2026-04-19 for:
  `react@npm`, `requests@pypi`, `mobylette@npm` (trust-history case),
  plus unknown-slug and invalid-dimension error paths. All 10 tools
  returned valid JSON under the `tools/call` JSON-RPC envelope.

### Wiring

- `agentindex.mcp_server_v2` imports `TOOLS` and `TOOL_HANDLERS` from
  `agentindex.mcp` and appends them to its existing registries at
  module load. The v3 import is wrapped in a try/except so a future
  schema bug cannot brick the v2 server.
