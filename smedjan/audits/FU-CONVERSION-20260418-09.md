# FU-CONVERSION-20260418-09 — p95 latency triage, top-20 AI-mediated path patterns

> Follow-up to **AUDIT-CONVERSION-20260418 Finding 9**. No production deploy
> from this task — numbers and recommendations only.

## TL;DR

- The audit brief implied the slow tail is an HTML-size problem. It isn't.
  **Every page probed in the top-20 was ≤180 KB identity / ≤24 KB gzip** —
  well inside a 500 KB budget. The legacy 7.6 MB `/compare/` megapage
  cited in the prior citation audit **no longer exists** (now returns 404
  with `cf-cache-status: HIT`, `age 213s`, served from cache).
- The p95 killer is **origin SSR latency on Cloudflare cache MISS**, not
  payload weight. Representative cold hits: `/org/pyannote` TTFB **70.3 s**
  then 35 ms on HIT; `/mcp/kismet-travel` first hit **502 at 7.8 s** then
  37.1 s MISS on retry; `/model/meta-llama-3-70b-instruct-gguf` 3.7 s MISS
  → 73 ms HIT.
- The *driver* is the long-tail distribution of AI-mediated landings:
  **11,262 of 15,765 unique AI-mediated paths (71.4%) were hit exactly
  once in the 30-day window.** Each new LLM citation lands on a path that
  has never primed the edge cache, so the reader pays the full origin SSR
  cost. First-hit p95 is 11,743 ms; repeat-hit p95 is 11,121 ms — almost
  identical, meaning even repeat readers fall off the edge cache before
  the next citation arrives.
- Therefore the highest-leverage fix is **prewarming + SSR cap + SWR**,
  not HTML trimming. HTML-budget policy is still worth writing down so
  future regressions have a tripwire.

## Sources and method

- Latency: `analytics_mirror.requests` on the Smedjan Postgres replica,
  window `now() - 30d`, filtered to `visitor_type='ai_mediated'` and
  `status<400`, 35,905 rows across 15,765 unique paths.
- Sizing / cache behaviour: `curl` against `https://nerq.ai` over the
  public Cloudflare edge, each path probed twice (cold/warm), capturing
  `cf-cache-status`, `age`, body bytes at `accept-encoding: identity`
  and `accept-encoding: gzip, br`, plus server-timing via `time_starttransfer`.
- Raw probe output: `smedjan/audits/FU-CONVERSION-20260418-09-probes.tsv`.

Path grouping is by pattern (e.g. `/model/{slug}`). Concrete worst-case
exemplars were picked by per-path p95 among paths with ≥5 AI-mediated
hits. See the bottom of this file for grouping SQL.

## Top-20 ai_mediated path patterns by p95 latency

| # | Pattern | Hits/30d | p50 (ms) | p95 (ms) | p99 (ms) | Worst concrete path (p95) |
|---|---|---:|---:|---:|---:|---|
| 1 | `/__other__/org/*` | 223 | 3,314 | **27,500** | 44,641 | `/org/pyannote` (43.6 s) |
| 2 | `/__other__/mcp/*` | 523 | 92 | **25,023** | 45,222 | `/mcp/kismet-travel` (32.5 s) |
| 3 | `/is-{lib}-safe` (aggregate) | ~200 | 41 | **22,115** | 27,564 | `/is-windscribe-safe` (26.0 s) |
| 4 | `/profile/{slug}` | 4,071 | 1,438 | **15,614** | 36,193 | `/profile/arabold-docs-mcp-server` (30.4 s) |
| 5 | `/compare/{single}` | 2,321 | 118 | **14,970** | 46,217 | `/compare/comfy-org-comfyui-vs-n8n-io-n8n` (37.2 s) |
| 6 | `/model/{slug}` | 4,234 | 509 | **14,414** | 35,674 | `/model/h3-proxy` (33.1 s) |
| 7 | `/cs/*` (Czech) | 46 | 484 | **14,059** | 22,335 | — |
| 8 | `/package/{slug}` | 1,190 | 96 | **12,739** | 32,251 | `/package/rockset-openai` (33.8 s) |
| 9 | `/npm/{slug}` | 108 | 7 | **12,474** | 21,843 | — |
| 10 | `/alternatives/*` | 52 | 1,016 | **11,041** | 16,146 | `/alternatives/deepset-ai-haystack` (11.1 s) |
| 11 | `/dataset/{slug}` | 7,074 | 202 | **10,953** | 31,046 | `/dataset/xlam-function-calling-60k` (41.6 s) |
| 12 | `/pypi` | 34 | 105 | **10,916** | 19,265 | — |
| 13 | `/safe/{slug}` | 3,940 | 154 | **10,395** | 31,032 | — |
| 14 | `/container/{slug}` | 480 | 947 | **10,270** | 35,437 | `/container/lmdeploy` (29.0 s) |
| 15 | `/crypto/{slug}` | 1,506 | 17 | **9,982** | 38,293 | `/crypto/exchange/bingx` (50.2 s) |
| 16 | `/kya/*` | 24 | 5 | **9,898** | 17,853 | — |
| 17 | `/ar/*` (Arabic) | 36 | 120 | **9,876** | 25,209 | — |
| 18 | `/answers` | 56 | 38 | **8,733** | 17,583 | — |
| 19 | `/agent/{uuid}` | 2,551 | 4 | **7,710** | 22,449 | `/agent/025612fa-…` (21.2 s) |
| 20 | `/tokens` | 50 | 83 | **7,541** | 54,669 | — |

Sanity anchors (same window): all-ai_mediated, status<400 → **p50 = 249 ms,
p95 = 11,468 ms, n = 35,905** (matches the audit's 249 / 11,514 / 2,352).

## Size and cache-behaviour measurements

Each path was probed twice against the CF edge with `accept-encoding: identity`
and then once more with `gzip, br` to get transfer size.

| Pattern | Exemplar path | Status | Identity (B) | Gzip (B) | Cold CF | Cold TTFB | Warm CF | Warm TTFB | `cache-control` |
|---|---|---|---:|---:|---|---:|---|---:|---|
| `/org/*` | `/org/pyannote` | 200 | 18,799 | 5,120 | MISS | **70.310 s** | HIT (age 37) | 0.039 s | `max-age=14400, s-maxage=86400, swr=86400` |
| `/mcp/*` | `/mcp/kismet-travel` | 502→200 | 23,236 | — | MISS | **37.132 s** | — | — | (502 first, then 200) |
| `/is-{lib}-safe` | `/is-entityframework-safe` | 200 | 35,158 | — | MISS | 0.723 s | HIT | 0.035 s | as above |
| `/profile/{slug}` | `/profile/openai` | 200 | 17,453 | — | MISS | 2.289 s | HIT (age 1) | 0.114 s | as above |
| `/compare/{single}` | `/compare/openclaw-openclaw-vs-openhands-openhands` | 200 | 28,552 | 7,568 | HIT (age 1,799) | 0.035 s | HIT | 0.035 s | `s-maxage=86400, swr=86400` |
| `/model/{slug}` | `/model/meta-llama-3-70b-instruct-gguf` | 200 | 16,504 | 4,969 | MISS | 3.695 s | HIT | 0.073 s | as above |
| `/cs/` | `/cs/` | 200 | 37,185 | — | HIT (age 36,488) | 0.038 s | HIT | 0.039 s | as above |
| `/package/{slug}` | `/package/langgenius-dify` | 200 | 17,044 | — | MISS | 3.545 s | HIT | 0.033 s | as above |
| `/npm/{slug}` | `/npm/axios` | 200 | 15,880 | — | MISS | 4.309 s | HIT | 0.035 s | as above |
| `/alternatives/*` | `/alternatives/deepset-ai-haystack` | 200 | 16,008 | — | MISS | 3.041 s | HIT | 0.033 s | as above |
| `/dataset/{slug}` | `/dataset/squad` | 200 | 20,126 | — | MISS | **6.919 s** | HIT | 0.048 s | as above |
| `/pypi` | `/pypi` | 200 | 19,754 | — | HIT (age 36,524) | 0.041 s | HIT | 0.038 s | as above |
| `/safe/{slug}` | `/safe/numpy` | 200 | 41,501 | 10,388 | MISS | 0.112 s | HIT | 0.038 s | as above |
| `/container/{slug}` | `/container/lmdeploy` | 200 | 21,174 | — | MISS | 1.330 s | HIT | 0.039 s | as above |
| `/crypto/{slug}` | `/crypto/exchange/bingx` | 200 | 16,188 | — | MISS | 0.067 s | HIT | 0.124 s | as above |
| `/kya/` | `/kya/` | 200 | 19,106 | — | MISS | 2.163 s | HIT | 0.034 s | as above |
| `/ar/` | `/ar/` | 200 | 39,750 | — | HIT (age 36,496) | 0.036 s | HIT | 0.050 s | as above |
| `/answers` | `/answers` | 200 | 27,125 | — | MISS | 0.095 s | HIT | 0.039 s | as above |
| `/agent/{uuid}` | `/agent/083f89ad-…` | 301 | 0 | — | MISS | 1.817 s | HIT | 0.030 s | `max-age=14400` |
| `/tokens` | `/tokens` | 200 | **179,359** | 23,641 | HIT (age 36,542) | 0.037 s | HIT | 0.117 s | as above |
| *(canary)* | `/compare/` | **404** | 11,522 | — | HIT (age 213) | 0.034 s | HIT | 0.033 s | as above |

Observations:

1. **All HTML bodies are under 180 KB identity.** The prior "7.6 MB
   `/compare/` index" canary has been retired (404 with cached `age 213s`).
   A 500 KB HTML budget is therefore headroom, not a fix — the largest
   live page is `/tokens` at 179 KB, 3× smaller than the proposed limit.
2. **Gzip compresses ~4×** (e.g. 179 KB → 24 KB; 41 KB → 10 KB), so over
   the wire no page exceeds 24 KB. Transfer time is not the bottleneck.
3. **Cache-control is already correct** on every product route:
   `public, max-age=14400, s-maxage=86400, stale-while-revalidate=86400`,
   plus a separate `cdn-cache-control` for CF. Cache headers are not
   broken.
4. **The only structural cache miss is the breadth of the catalog.** With
   ~5 M entities and a finite CF edge, popular long-tail paths drop out
   of cache between visits. The 30-day data shows 71.4 % of AI-landed
   paths are hit exactly once — a single LLM citation, then nothing —
   guaranteeing a cold SSR for every new reader.
5. **Origin SSR is slow on miss, not uniformly slow.** Fast MISS
   examples (`/safe/numpy` 112 ms, `/crypto/exchange/bingx` 67 ms,
   `/answers` 95 ms) prove origin can be quick when the query path is
   well-indexed. The pathological misses (`/org/pyannote` 70 s;
   `/dataset/squad` 6.9 s; `/model/...` 3.7 s) indicate specific DB
   query plans or upstream API calls that need attention per-surface.
6. **`/mcp/*` returns 502 on first hit** — Cloudflare gives up on the
   origin before SSR completes, then the CF retry succeeds as MISS in
   37 s. That 502 is almost certainly counted as a "bounce" by any
   downstream measurement. Origin timeout on this surface needs
   lifting or the surface needs pre-rendering.

## Recommendations, per pattern

Ordered by **(AI-mediated hits) × (p95 − 500 ms SLO deficit)** — the
biggest reader-seconds saved per fix.

| # | Pattern | Dominant cause | Proposed fix | Effort |
|---|---|---|---|---|
| 1 | `/dataset/{slug}` (7,074 hits × 10.5 s tail) | Slow SSR on cache miss (MISS 6.9 s); long tail | **Prewarm top-5k AI-landed dataset paths post-deploy**; profile DB query plan (`dataset_page()` SSR); consider a 2 s origin cap that falls back to a skeleton | M |
| 2 | `/model/{slug}` (4,234 × 13.9 s) | MISS 3.7 s; long tail | Same as above; prewarm top-5k | M |
| 3 | `/profile/{slug}` (4,071 × 15.1 s) | MISS 2.3 s; some 30 s outliers | Prewarm; audit `/profile/openai-openai-agents-python`-class outliers for a runaway join | M |
| 4 | `/safe/{slug}` (3,940 × 9.9 s) | Long tail; origin actually fast | Just prewarm; no code change | S |
| 5 | `/agent/{uuid}` (2,551 × 7.7 s) | 301 redirect latency is counted | Overlap with **FU-CITATION-20260418-10**; replace 301 on retired UUIDs with 410 + soft body already planned there | S (done elsewhere) |
| 6 | `/compare/{single}` (2,321 × 15.0 s) | MISS 3-10 s SSR (two entities per render) | Nightly job to precompute top 2k compare pairs from AI-mediated log into CF cache | M |
| 7 | `/crypto/{slug}` (1,506 × 10.0 s) | MISS fast origin but long-tail cold; p95 driven by a handful of 50 s outliers (`exchange/bingx`) | Prewarm listed tokens/exchanges (~200 pages); investigate the `exchange/bingx` outlier (oracle-fetch?) | S |
| 8 | `/package/{slug}` (1,190 × 12.7 s) | MISS 3.5 s | Prewarm; profile SSR | M |
| 9 | `/mcp/*` (523 × 25.0 s) | **Cold 502, then 37 s MISS** — origin timing out | Lift origin timeout for `/mcp/*`; consider static prerender for all known MCP tools (there are ~44 per the T009 manifest, so pre-render is trivial) | **High-ROI S** |
| 10 | `/container/{slug}` (480 × 10.3 s) | MISS 1.3 s; handful of 29 s outliers | Prewarm; profile outlier | S |
| 11 | `/org/*` (223 × 27.5 s) | **70 s SSR on miss** | Origin profile required (this is not a public-product surface; check whether it is being served at all); lift SSR cap or materialise | M |
| 12 | `/is-{lib}-safe` (~200 × 22.1 s) | ~60–80 such pages total; slow cold MISS | **Static-generate** all `/is-*-safe` into a single CF-cacheable JSON blob at deploy; the set is small | **High-ROI S** |
| 13 | `/npm/{slug}` (108 × 12.5 s) | MISS 4.3 s | Prewarm; SSR profile | M |
| 14 | `/answers` (56 × 8.7 s) | Origin fast; p95 is EU network latency | Not a Nerq fix; keep cached | none |
| 15 | `/alternatives/*` (52 × 11.0 s) | MISS 3.0 s | Prewarm | S |
| 16 | `/tokens` (50 × 7.5 s) | **179 KB HTML — largest live page**; origin fast once cached | **Split into `/tokens` (summary, ≤20 KB) + `/tokens/all?page=N` (paginated detail)**; cap the summary at 50 KB as a standing rule | M |
| 17 | `/cs/`, `/ar/`, `/pypi`, `/kya/` indexes | Long cache TTL already doing its job (`age` > 36 000 s); p95 driven by the handful of prior misses | Add to the prewarm list; no further work | S |

## HTML budget proposal (policy, not a fix)

Codify a standing limit so the next "let's add another 800 KB of JSON-LD"
PR trips a check rather than shipping silently:

- **Hard budget:** 500 KB identity / 120 KB gzip for any SSR page served
  to human traffic. Exceeded → CI check fails.
- **Soft budget:** 120 KB identity / 30 KB gzip. Exceeded → PR label
  `needs-page-weight-review`, human signoff required.
- **Current worst-case page:** `/tokens` at 179 KB identity / 24 KB gzip
  — already over the soft budget, under the hard budget. Split as
  described in row 16.
- **Implementation sketch:** add a `pytest` fixture that renders each
  template against fixture data and asserts `len(html)` is under
  soft/hard thresholds. Integrate with the weekly L6 canary run.

## SSR caching rules proposal

The cache-control headers are already correct. The missing pieces:

1. **Deploy-time prewarm.** After every release, issue GET requests
   (from localhost, bypassing CF, then re-fetch through CF to populate
   the edge) for the top 2,000 AI-mediated paths of the previous 30 days,
   sourced from `analytics_mirror.requests` (`visitor_type='ai_mediated'`,
   group by path, order by count desc, limit 2000). Cold SSR then
   happens once per release on the origin, not once per AI-referred
   reader.
2. **Origin SSR cap = 3 s, return skeleton on timeout.** Add a
   `ThreadPoolExecutor`-wrapped render with a 3 s budget; if the SSR
   can't complete in time, serve a minimal `{title, ZARQ verdict,
   "full details loading" JS hydrate}` skeleton and let the client
   finish. Kills the 30 s / 70 s tail. Requires careful rollout
   because template coverage is wide — scope as a follow-up ticket.
3. **Verify Cloudflare SWR is actually honored.** `stale-while-revalidate=86400`
   is in the header, but SWR on CF requires *Tiered Cache + explicit
   SWR enabled on the zone*. Confirm via `cf-cache-status: STALE`
   appearing in logs on re-fetch (none of the 44 probes in this audit
   showed STATUS=STALE, suggesting SWR may not currently be active).
4. **Pre-render small, finite surfaces.** `/is-{lib}-safe` (≤100
   pages), `/mcp/*` (≤44 from the T009 manifest), language-index
   pages (`/cs/`, `/ar/`, …) — all can be fully static-generated at
   deploy time and uploaded as immutable objects. Zero SSR cost,
   zero cache-miss risk. Highest ROI of anything in this document.

## Things explicitly **not** proposed

- No HTML-trimming rollout. The data doesn't support it as a fix for F9.
- No cache-header changes. They're already right.
- No change to `/compare/` (the former 7.6 MB index). It is already
  retired; verify the retirement was deliberate and the sitemap no
  longer lists it.
- No origin-code changes in this task — this is design-and-propose per
  the task's stated scope.

## Appendix — grouping SQL (reproducible)

```sql
WITH ai AS (
  SELECT
    CASE
      WHEN path ~ '^/agent/[0-9a-f-]{36}' THEN '/agent/{uuid}'
      WHEN path ~ '^/compare/[^/]+/[^/]+'  THEN '/compare/{a}/{b}'
      WHEN path = '/compare/' OR path = '/compare' THEN '/compare/'
      WHEN path ~ '^/compare/'             THEN '/compare/{single}'
      WHEN path ~ '^/profile/'             THEN '/profile/{slug}'
      WHEN path ~ '^/model/'               THEN '/model/{slug}'
      WHEN path ~ '^/dataset/'             THEN '/dataset/{slug}'
      WHEN path ~ '^/safe/'                THEN '/safe/{slug}'
      WHEN path ~ '^/package/'             THEN '/package/{slug}'
      WHEN path ~ '^/container/'           THEN '/container/{slug}'
      WHEN path ~ '^/crypto/'              THEN '/crypto/{slug}'
      WHEN path ~ '^/npm/'                 THEN '/npm/{slug}'
      WHEN path ~ '^/zarq/'                THEN '/zarq/*'
      WHEN path ~ '^/docs/'                THEN '/docs/*'
      WHEN path ~ '^/tag/'                 THEN '/tag/{slug}'
      WHEN path ~ '^/category/'            THEN '/category/{slug}'
      WHEN path ~ '^/best/'                THEN '/best/*'
      WHEN path ~ '^/api/'                 THEN '/api/*'
      WHEN path = '/' THEN '/'
      WHEN path = '/tokens' THEN '/tokens'
      ELSE '/__other__:' || regexp_replace(path, '(^/[^/?]+).*', '\1')
    END AS pattern,
    duration_ms
  FROM analytics_mirror.requests
  WHERE ts >= now() - interval '30 days'
    AND visitor_type='ai_mediated' AND status<400
    AND duration_ms IS NOT NULL
)
SELECT pattern,
       count(*)                                                              AS n,
       round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY duration_ms)::numeric,1) AS p50,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)::numeric,1) AS p95,
       round(percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms)::numeric,1) AS p99
  FROM ai
 GROUP BY pattern
 HAVING count(*) >= 20
 ORDER BY p95 DESC
 LIMIT 25;
```
