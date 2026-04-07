# Nerq Sprint N0 — Product Foundation

## Status: DONE

## Tasks

### TASK 1: Agent Benchmarking API
- [x] `GET /v1/agent/benchmark/{category}` — Top 20 agents ranked by trust_score
- [x] `GET /v1/agent/benchmark/categories` — All categories with counts
- [x] Response includes: agent_name, trust_score, compliance_score, risk_level, days_indexed, platform, source, github_stars
- [x] X-Total-In-Category header
- [x] Uses domains[1] as fallback category
- [x] 10-min cache per category

### TASK 2: Agent Search API
- [x] `GET /v1/agent/search?q=...&domain=...&type=...&min_trust=...&limit=20&offset=0`
- [x] Fulltext search on name + description
- [x] Filters: domain, agent_type, min trust_score
- [x] Pagination: limit/offset with total count

### TASK 3: Agent Stats API
- [x] `GET /v1/agent/stats`
- [x] All fields: total_assets, total_agents, total_tools, total_mcp_servers, total_models, total_datasets, total_spaces
- [x] categories, frameworks, languages, trust_distribution
- [x] new_24h, new_7d, average_trust_score
- [x] Cached 1 hour

### TASK 4: MCP Tools
- [x] `find_best_agent(category, min_trust_score=50)` — top 5 via search API
- [x] `agent_benchmark(category)` — benchmark for a category
- [x] `get_agent_stats()` — ecosystem stats
- [x] Updated mcp_sse_server.py (SSE transport)
- [x] Updated zarq_mcp_server.py (stdio + streamable HTTP)
- [x] Server card version bumped to 0.5.0

### TASK 5: /nerq/docs page
- [x] Served at nerq.ai/nerq/docs
- [x] Documents: KYA, benchmark, search, stats, discover, MCP
- [x] Curl examples for each endpoint
- [x] Tech blue design palette (#2563eb, Inter font)
- [x] Cross-link to zarq.ai/zarq/docs for crypto
- [x] Cross-links to KYA, benchmarking

### TASK 6: KYA redirect
- [x] zarq.ai/zarq/kya → 301 redirect to nerq.ai/kya
- [x] zarq.ai/zarq/kya/{path} → 301 redirect to nerq.ai/kya/{path}

### TASK 7: Backup script
- [x] Created ~/agentindex/scripts/backup-to-disk.sh
- [x] Takes mount point as argument
- [x] Backs up: SQLite DBs, pg_dump compressed, code tar, LaunchAgents, docs
- [x] Shows progress and final size
- [x] Executable

## Files Created
- `agentindex/nerq_api.py` — Tasks 1-3 (benchmark, search, stats)
- `agentindex/nerq_docs.py` — Task 5 (docs page)
- `scripts/backup-to-disk.sh` — Task 7 (backup script)

## Files Modified
- `agentindex/api/discovery.py` — Mounted nerq_api, nerq_docs, KYA redirects
- `agentindex/mcp_sse_server.py` — Added 3 Nerq MCP tools, updated server card
- `agentindex/crypto/zarq_mcp_server.py` — Added 3 Nerq MCP tools + handlers

## Result

All 7 tasks implemented, tested locally and via tunnel. All endpoints return 200 OK.

### Test Results
- `GET /v1/agent/stats` — 200 OK, 4.9M total assets, 66K agents, 60K tools, 17K MCP servers
- `GET /v1/agent/benchmark/categories` — 200 OK, 50+ categories with counts and avg trust
- `GET /v1/agent/benchmark/coding` — 200 OK, X-Total-In-Category: 10939, top 20 agents
- `GET /v1/agent/search?q=code+review&min_trust=50` — 200 OK, fulltext + filters + pagination
- `GET /nerq/docs` — 200 OK, tech blue page with all endpoint docs
- `GET /zarq/kya` — 301 → nerq.ai/kya
- `GET /zarq/kya/langchain` — 301 → nerq.ai/kya/langchain
- `scripts/backup-to-disk.sh` — executable, tested structure
- MCP tools: find_best_agent, agent_benchmark, get_agent_stats added to both servers
- Server card bumped to v0.5.0

### Route ordering fix
The nerq router is mounted before `/v1/agent/{agent_id}` to prevent `/v1/agent/stats` from matching the UUID path param.
