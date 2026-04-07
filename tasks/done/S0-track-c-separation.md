# S0 Track C — ZARQ/Nerq Separation (Preparation)

**Date:** 2026-03-07
**Status:** Complete — documentation only, no code changes

---

## Deliverable

Created `docs/service-boundaries.md` — the authoritative map for splitting the monolith.

---

## Key Findings

### Route count by product

| Product | API endpoints | SEO/HTML pages | Total |
|---------|--------------|----------------|-------|
| ZARQ | 44 | 34 | 78 |
| Nerq | 9 + 14 agents + 14 compliance | 16 | 53 |
| Shared | 3 | 0 | 3 |

### Database separation is already clean

- **ZARQ** uses SQLite exclusively (`crypto_trust.db`, 379MB, 39 tables)
- **Nerq** uses PostgreSQL exclusively (`agentindex` database, 13 tables)
- No cross-product database queries exist
- No `zarq.*` PostgreSQL schema exists or is needed

### What ZarqRouter actually does

`zarq_router.py` is a middleware (not a FastAPI Router). It only handles host-based routing for `zarq.ai`:
- Serves the landing page template for `zarq.ai/`
- Passes all `/v1/*`, `/crypto/*`, `/paper-trading/*`, `/admin/*` through
- Does NOT separate code paths — both products share one FastAPI app and one process

### External API dependencies

| ZARQ | Nerq |
|------|------|
| CoinGecko (prices, metadata) | GitHub API (repo crawling) |
| DeFiLlama (TVL, yields) | npm/PyPI/HuggingFace/DockerHub |
| DexScreener (DEX data) | |
| Etherscan (on-chain) | |

### Recommended separation order (Phase 2)

1. Create `agentindex/api/zarq_api.py` — consolidate all ZARQ router imports
2. Create `agentindex/api/nerq_api.py` — move Nerq routes from discovery.py
3. Reduce discovery.py to a thin shell mounting both routers + shared middleware
4. Future: separate processes with independent scaling

---

## Files created

| File | Description |
|------|-------------|
| `docs/service-boundaries.md` | Full route map, DB tables, templates, external deps, migration plan |

## Tests

29/29 passed (no code changes were made, documentation only).
