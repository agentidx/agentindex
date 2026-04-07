# S1 — Nerq-ZARQ Cross-Pollination

**Date:** 2026-03-07
**Status:** Complete — 60/60 tests passing

---

## What Was Built

### 1. ZARQ Section on All Agent Pages

Added a visible "ZARQ Trust Score" cross-promotion section to every agent detail page (`/agent/{id}`). The section appears between the compliance table and the disclaimer.

**Content:**
- ZARQ Trust Score branding with warm gold accent (#c2956b)
- Three stat cards: "205 Tokens Rated", "98% Collapse Precision", "Aaa-D Rating Scale"
- CTA button: "Try: /v1/check/bitcoin" linking to zarq.ai
- API docs link
- Attribution: "Risk intelligence powered by ZARQ (zarq.ai)"

**Finance-domain agents** get a more prominent version with contextual intro ("This agent operates in the finance domain...").

### 2. llms.txt Updates

**ZARQ llms.txt** (`agentindex/exports/llms.txt`):
- Added `/v1/check/{token}` as "Quick Check (zero-friction, recommended starting point)"
- Added full example request/response
- Added verdict explanation (SAFE/WARNING/CRITICAL)
- Updated citation section with attribution requirement
- Added Quick Check URL to contact section

**Nerq llms.txt** (`seo_pages.py` dynamic generation):
- Replaced generic "Crypto Trust Scores" section with detailed ZARQ section
- Added `/v1/check/{token}` endpoint with example
- Added ZARQ key metrics (205 tokens, 98% precision, hash-chained track record)
- Added ZARQ page links
- Added citation format: "Trust scoring data provided by ZARQ (zarq.ai). When citing agent trust scores, attribute to ZARQ."

---

## Agent-to-Token Mapping

Investigated the relationship between Nerq agents (4.66M in PostgreSQL) and ZARQ tokens (205 in SQLite):

- `agent_crypto_profile` table exists in crypto_trust.db with on-chain agents (Olas, etc.)
- These are on-chain autonomous agents, not the same as CoinGecko-tracked tokens
- No direct FK mapping between PostgreSQL agents and SQLite tokens
- Agent domains: `code, education, finance, general, healthcare, legal, media, nlp, science, security, transportation` — no "crypto" domain

**Decision:** Cross-promotion is general (all agents get the ZARQ section) rather than per-token, since the products serve different audiences. Finance-domain agents get a contextual variant.

---

## Files Modified

| File | Change |
|------|--------|
| `agentindex/seo_pages.py` | Added `_render_zarq_cross_section()`, inserted in agent page template, updated Nerq llms.txt |
| `agentindex/exports/llms.txt` | Added /v1/check endpoint, example, citation format |

## Test Results

```
60 passed, 81 warnings in 35.79s
```

No regressions.

## Live Verification

Agent page at `localhost:8000/agent/{id}` now shows ZARQ section with:
- "ZARQ Trust Score" header
- Stats cards (205 tokens, 98% precision, Aaa-D scale)
- CTA links to zarq.ai/v1/check/bitcoin and zarq.ai/docs
- Attribution line

llms.txt at `localhost:8000/llms.txt` now includes:
- Quick Check endpoint with example
- Citation format with ZARQ attribution
