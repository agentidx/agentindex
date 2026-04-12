# Incident Report: AI Bot Dropoff 2026-04-12

## Summary

Anders noticed significantly reduced AI bot traffic (Claude, ChatGPT, Meta) on 2026-04-12 morning. Investigation identified root cause as external: Cloudflare Workers AI incident affecting multiple AI bot operators.

## Timeline

- 2026-04-11 21:52 UTC — Cloudflare Workers AI Gemma 4 model unhealthy incident starts
- 2026-04-11 22:20 CEST — Meta crawl rate begins dropping (1127 to 580)
- 2026-04-12 00:40 CEST — ChatGPT crawl rate drops (1037 to 384 to 5)
- 2026-04-12 02:00 UTC (04:00 CEST) — Cloudflare incident resolved
- 2026-04-12 04:40 CEST — Claude crawl rate drops (1094 to 65)
- 2026-04-12 09:50 CEST — Claude begins recovery
- 2026-04-12 10:30 CEST — Claude fully recovered to ~6700/h
- 2026-04-12 11:00 CEST — ChatGPT still at ~50/h (slow recovery)
- 2026-04-12 11:00 CEST — Meta still at ~18-4000/h (slow recovery)

## Data

AI bot traffic per hour (Claude example):
- Normal baseline: ~6500/h
- Drop 05:00-09:40: ~300-950/h (85-95% reduction)
- Recovery 10:00+: ~6700/h

## Diagnosis steps

1. Compared to same period previous Sunday (2026-04-05)
   Result: Previous Sunday had 5000-6000/h for Claude and ChatGPT same hours
   Conclusion: Not a normal Sunday pattern
2. Checked our response times to bots
   Result: ChatGPT got 104ms avg, all 200 OK codes
   Conclusion: Not our fault, we were serving correctly
3. Checked robots.txt
   Result: No changes, all bots allowed
   Conclusion: Not a configuration issue
4. Checked Cloudflare status page
   Result: Workers AI Gemma 4 model unhealthy incident 21:52-02:00 UTC
   Conclusion: Matches our timeline

## Root cause

Cloudflare Workers AI infrastructure incident. When Workers AI was unhealthy, multiple AI bot operators experienced reduced crawl throughput through Cloudflare edge. Possible mechanisms:
- Shared infrastructure between Workers AI and bot detection/routing
- WAF rules using AI models temporarily blocked traffic
- Cascading failures in CF internal services

## What we did

Nothing required. All our systems are healthy. Bots are recovering organically as Cloudflare and bot operator cooldowns normalize.

## What we should remember

Before assuming external bot traffic changes are our fault, check Cloudflare status first. Compare against same time period previous week to distinguish patterns from anomalies.
