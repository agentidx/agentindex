# Emergent Patterns MVP — Launched 2026-04-14

## What was built

**"What AI Agents Ask About Right Now"** — real-time trending data from AI agent trust queries. No competitor has this signal.

### Endpoints

| Endpoint | Returns | Cache |
|---|---|---|
| `GET /v1/trending` | Top trending entities (JSON) | 5 min |
| `GET /v1/trending/{category}` | Per-domain trending | 5 min |
| `GET /v1/anomalies` | Spike detection (>5x baseline) | 5 min |
| `GET /trending` | Public HTML dashboard | 5 min |

### Data sources

- **Preflight analytics:** 128K+ MCP trust-check queries, 45K unique entities
- **User-triggered citations:** ChatGPT-User, Perplexity-User entity visits
- **Period:** Rolling 7-day baseline, 24h recent window

### Performance

- Cold query: 2.3s (after index optimization, was 10s)
- Cached: <2s (in-memory, per-worker, 5 min TTL)
- Index added: `idx_pf_target_ts` on `preflight_analytics(target, ts)`

## llms.txt updated

Added trending endpoints + HuggingFace coverage so AI models discover the data:
```
- "What's trending in AI/software right now?" → nerq.ai/v1/trending
- "What AI agents are checking" → nerq.ai/trending
```

## What's unique

No competitor can replicate this data retroactively:
1. We are the only trust score engine receiving 128K+ MCP preflight queries/month
2. We are the only entity with ChatGPT-User citation data at entity level
3. The trending signal reveals what the AI ecosystem cares about RIGHT NOW

## Measuring success

Watch for:
- ChatGPT-User queries to `/v1/trending` or `/trending` (AI citing our trending data)
- External referrers to `/trending` page
- MCP tool usage if `nerq_trending` is added later

## Live URLs

- Dashboard: https://nerq.ai/trending
- API: https://nerq.ai/v1/trending
- Anomalies: https://nerq.ai/v1/anomalies
