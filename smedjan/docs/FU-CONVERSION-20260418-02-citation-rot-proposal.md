# FU-CONVERSION-20260418-02 — Citation-rot proposal (410 / 404 / 301 on AI-landed paths)

> **Parent audit**: AUDIT-CONVERSION-20260418, Finding 2 (severity `high`).
> **Window audited**: 2026-03-20 → 2026-04-18 (30d), `analytics_mirror.requests` where `visitor_type='ai_mediated'`.
> **Status**: proposal only. No production deploy from this task.
> **Scope of future edits**: `smedjan/` and `agentindex/crypto/templates/` (per task whitelist).
> **Parallel work already shipped** (do not duplicate):
>   - `FU-QUERY-20260418-01` (d394618) — middleware rewrites `/model/<slug>` 404s → 200 noindex stub and enqueues backfill. Fires *before* the LLM-cited 404s show up again.
>   - `FU-QUERY-20260418-02` (01eb4a4) — lazy `/compare/<a>-vs-<b>` fallback, 22% 404 → <5%.
>   - `FU-QUERY-20260418-04` (6969dc0) — `/token/<slug>` 404 backfill loop.
>   - `FU-CITATION-20260418-10` (ee87a6a) — top-30/30 301+410 UUID → slug redirect CSV.

---

## Executive summary

AI-mediated status mix (30d): 200=33,600, 301=1,805, 304=474, 410=368, 404=89, 500=22. **2,284 non-200 hits on 36,423 ai_mediated hits = 6.27%.**

Root cause of the three pathologies:

1. **301 wastage (1,805 hits).** `agentindex/api/discovery.py:543` (`agent_redirect`) dumb-copies the last path segment: `/agent/<uuid>` → `/safe/<uuid>`, and `/safe/<uuid>` 404s. LLM-cited UUIDs never resolve even though **27 of the top 30 UUIDs exist in `entity_lookup` with a live slug**.
2. **410 wastage (368 hits).** `agentindex/seo_pages.py:591` returns `HTMLResponse("", status_code=410)` — zero body, `X-Robots-Tag: noindex`. When this wins route matching against the discovery.py handler, the ChatGPT/Claude reader lands on an empty white page with no CTA, no search, no recovery path. Same `/agent/<uuid>` can appear as 301 (82 hits) and 410 (5 hits) for the same UUID `083f89ad-…` — route ordering is non-deterministic across workers.
3. **404 wastage (89 hits).** Dominated by model slugs LLMs invented or that were retired (`/model/zk-kit-poseidon-cipher`, `/model/jovotech-platform-googleassistant`, `/model/zilliz-milvus-sdk-node`). FU-QUERY-20260418-01 already rewrites these to 200-noindex stubs going forward — residue here is the 30d history.

**Proposed fix shape** (spec; no code in this task):

- **(a) 410 with body.** Replace the empty `HTMLResponse("", 410)` with a rendered template — still 410 semantics, but with a human-readable "this entity is retired" body that carries a ZARQ CTA and a deep-link into `/search?q=<slug>` so the AI reader is not dropped onto a blank page. Deprecate the UUID 410 handler entirely for UUIDs that *do* resolve in `entity_lookup` — those should 301 to the live slug, not 410.
- **(b) 404 rename detection.** Add a `model_rename_map` JSON lookup loaded at startup in the same middleware shipped by FU-QUERY-20260418-01. On 404, consult the map before falling through to the 200-noindex stub — if a rename is found, emit `301 Location: /model/<new_slug>`. Seed the map from the quarterly slug-churn backfill.
- **(c) 301 target preserves hash.** Audit the RedirectResponse in `agent_redirect` to ensure `request.url.fragment` is appended to the target. Current implementation drops the fragment because FastAPI's `RedirectResponse` only copies `path`. Also verify `#<section>` anchor links in `/safe/<slug>` templates match the deep-links LLMs embed.

---

## Top 20 offending paths (30d, `visitor_type='ai_mediated'`, status in 301/404/410)

Ranked by hit-count. `disposition` values:

- `301-to-slug` — rewrite handler to map UUID → `entity_lookup.slug` instead of blind tail-copy.
- `soft-410` — keep 410 but render a body with CTA (spec below). Applies when `entity_lookup.is_active=false` or the UUID is not in entity_lookup at all.
- `301-to-slug-via-410-path` — UUID currently hits the seo_pages 410 branch; route handler should defer to the discovery.py UUID→slug resolver first.
- `accept-as-404` — slug was never in `entity_lookup`, likely LLM hallucination; 200-noindex stub from FU-QUERY-20260418-01 middleware already covers this going forward.
- `301-to-slug-with-rename` — slug exists under a different canonical name; emit 301 via the proposed rename map.

| # | hits | status | path | live `entity_lookup` resolution | disposition | notes |
|---|---:|---:|---|---|---|---|
| 1  | 82 | 301 | `/agent/083f89ad-…` | `slug=roviqa-vit-roberta-image-captioning` (active, parsed, HF author2, grade D) | `301-to-slug` | top offender; 82 wasted hits. |
| 2  | 13 | 410 | `/agent/29669332-…` | `slug=-k-phoen-backstage-plugin-confluence` (active, indexed, npm_full) | `301-to-slug-via-410-path` | currently blank 410. |
| 3  | 13 | 404 | `/model/zk-kit-poseidon-cipher` | not in `entity_lookup` | `accept-as-404` | FU-QUERY-20260418-01 middleware now serves 200-noindex stub. |
| 4  | 13 | 301 | `/agent/bccd76c8-…` | `slug=pi0-7` (active, indexed, HF) | `301-to-slug` | |
| 5  | 9  | 301 | `/agent/92d4182b-…` | `slug=-pocket-portfolio-universal-csv-importer` (active, indexed, npm_full) | `301-to-slug` | |
| 6  | 9  | 301 | `/agent/8328115d-…` | `slug=agentharbor-autonomous-data-exploration` (active, ranked, HF space) | `301-to-slug` | |
| 7  | 8  | 301 | `/agent/025612fa-…` | `slug=airi` (active, ranked, github, **grade B-**) | `301-to-slug` | grade-B entity — highest-value hop to recover. |
| 8  | 6  | 404 | `/model/jovotech-platform-googleassistant` | not in `entity_lookup` | `accept-as-404` | LLM-hallucinated slug. |
| 9  | 6  | 301 | `/agent/acefcd4e-…` | `slug=velnari` (active, indexed, HF) | `301-to-slug` | |
| 10 | 6  | 301 | `/agent/8f603b24-…` | `slug=abhigyanpatwari-gitnexus` (active, ranked, github, **grade B**) | `301-to-slug` | |
| 11 | 5  | 301 | `/agent/c2958d5c-…` | `slug=dovren` (active, indexed, HF dataset) | `301-to-slug` | |
| 12 | 5  | 301 | `/agent/e14ce38f-…` | `slug=nivra-ai-agent` (active, parsed, HF space) | `301-to-slug` | |
| 13 | 5  | 301 | `/agent/edeaaa87-…` | `slug=opencloud` (active, indexed, HF dataset) | `301-to-slug` | |
| 14 | 5  | 410 | `/agent/083f89ad-…` | same as row 1 (`roviqa-vit-roberta-image-captioning`, active) | `301-to-slug-via-410-path` | **route-order flap**: same UUID returns 301 (82x) and 410 (5x). See §Issue below. |
| 15 | 5  | 410 | `/agent/317c09b6-…` | `slug=qwen3-32b-cevum` (active, indexed, HF) | `301-to-slug-via-410-path` | |
| 16 | 5  | 410 | `/agent/c5411541-…` | `slug=xmm-codex-bmad-skills` (active, classified, github) | `301-to-slug-via-410-path` | |
| 17 | 4  | 410 | `/agent/f427a53a-…` | `slug=base-chatbt` (active, indexed, docker_hub) | `301-to-slug-via-410-path` | |
| 18 | 4  | 404 | `/model/zilliz-milvus-sdk-node` | not in `entity_lookup` | `accept-as-404` | but confirm no rename in Milvus repo before settling. |
| 19 | 4  | 301 | `/agent/1bf8bc4a-…` | `slug=vae-burgers-norevin` (active, indexed, HF author2) | `301-to-slug` | |
| 20 | 4  | 410 | `/agent/7d6f78dd-…` | `slug=avrik` (**is_active=false**, crawl_status=not_agent, HF) | `soft-410` | genuine retirement — serve body with ZARQ CTA, keep 410 semantics. |

Coverage note: rows 1–20 account for **208 / 2,284 = 9.1%** of the 30d ai_mediated non-200 volume. The pattern generalises — fixing the handler in place (row 1–2, 4–7, 9–17, 19 = 17 rows) recovers roughly **2/3 of the 1,805 301s** and **~80% of the 368 410s**, because the same blind-tail-copy bug is producing ~100 more tail paths with ≤3 hits each. Do not ship a per-path rewrite map; ship the handler change.

### Issue uncovered by this triage — route-ordering flap for `/agent/<uuid>`

Two handlers claim `/agent/...`:

- `agentindex/api/discovery.py:543` — `@app.get("/agent/{path:path}")` → 301 to `/safe/<last-segment>`.
- `agentindex/seo_pages.py:588` — `@app.get("/agent/{agent_id}")` → empty 410.

Which handler wins depends on registration order, and `083f89ad-…` in the 30d data produces **both 82 301s and 5 410s**. Any production fix MUST delete or restrict one of these handlers so the behaviour is deterministic. Recommended: remove `seo_pages.py:588` (the empty-410 short-circuit), and make `discovery.py:543` UUID-aware (resolve via `entity_lookup`; on miss, return the `soft-410` render).

---

## (a) Soft-410 retired-entity body — template spec

File (future): `agentindex/crypto/templates/retired_entity.html` (whitelisted). Rendered by the UUID handler when `entity_lookup.is_active=false` or the UUID is unknown.

Required fields in context:
- `uuid` — the path UUID, for audit.
- `slug_guess` — nearest-match slug from `entity_lookup` (via trigram or ts_rank against `name_lower`), may be null.
- `canonical_search_url` — `/search?q=<slug_guess or uuid>`.
- `zarq_cta_url` — `/zarq/doc` (primary CTA per Finding 1 recommendation).

Response: `HTTP 410 Gone`, `X-Robots-Tag: noindex, follow`, `Cache-Control: public, max-age=3600`, body ≥ 2KB (the empty-body 410 is why LLM readers perceive this as a dead click).

Above-the-fold content blocks:

1. One-line headline: "This entity has been retired from Nerq."
2. One paragraph explanation: why (schema change, source de-listed, `is_active=false`), what we still know, when it was last indexed (`updated_at` from `entity_lookup` if available).
3. Primary CTA: **"Get a Trust Score on the current catalog"** → `/zarq/doc` (matches Finding 1 lever).
4. Secondary CTA: **"Search similar entities"** → `canonical_search_url`.
5. Nearest-neighbour tile (3 slugs) pulled from `entity_lookup` via the same category + top `trust_score_v2`.
6. JSON-LD `WebPage` with `isAccessibleForFree: true` and a `SpeakableSpecification` hook so ChatGPT/Claude can re-cite the retirement notice rather than the dead UUID.

Not included: no search box (the global header already carries it; avoid duplicate search input on a 410 page), no email-capture (FU-CONVERSION-20260418-03 owns retention surfaces).

---

## (b) 404 rename detection — design note

The 404 404s on `/model/<slug>` are now served as 200-noindex stubs by the middleware in FU-QUERY-20260418-01. This proposal adds a **rename map** consulted before the 200-stub branch:

```
~/agentindex/data/model_rename_map.json       # {old_slug: new_slug, ...}
```

- Populated by a weekly job (new follow-up, `FU-CONVERSION-20260418-02b` if needed) that diffs `entity_lookup.slug` values week-over-week and emits rename candidates where source URL, author, and name similarity all hold.
- Middleware path: on 404 at `/model/<slug>`, `if slug in rename_map: return 301 → /model/<rename_map[slug]>`; else fall through to the existing stub.
- Safety: rename map is read-only from the middleware's perspective; writes go through the weekly job only. No LLM-driven renames.

For the 3 model slugs in the top-20 (`zk-kit-poseidon-cipher`, `jovotech-platform-googleassistant`, `zilliz-milvus-sdk-node`), spot-checks show no current canonical slug in `entity_lookup`; dispositions remain `accept-as-404`.

---

## (c) 301 target preserves scroll/hash — audit finding

`agentindex/api/discovery.py:548` returns `RedirectResponse(url=f"/safe/{slug}", status_code=301)`. Starlette's `RedirectResponse` constructs `Location: /safe/<slug>` with no fragment. If the LLM cites `/agent/<uuid>#methodology`, the fragment is dropped on the 301. Fix (when handler is rewritten): pass `request.url.fragment` through — `target = f"/safe/{slug}" + (f"#{request.url.fragment}" if request.url.fragment else "")`. Note: fragments don't appear in access logs (they're client-side), so we cannot measure directly. This is a correctness fix, not a metric-moving fix.

Verify templates `/safe/<slug>` expose stable `id=` anchors matching the `#section` patterns ChatGPT/Claude embed. Known anchors in `safe_page.html` today: `#trust-score`, `#methodology`, `#risk-flags`, `#compliance`. No mismatch found in a 5-sample walk-through of top LLM-cited anchors; carry-forward confirmation is part of the fix task.

---

## 14-day measurement query

Monitor daily post-deploy. The 14d denominator is `ai_mediated hits` (rolling daily), because the *rate* matters more than the absolute count — ingestion is flat per Finding 11.

```sql
-- File: can be saved as smedjan/audits/FU-CONVERSION-20260418-02-measure.sql
-- Run via: smedjan sources.analytics_mirror_cursor()
WITH daily AS (
  SELECT date_trunc('day', ts)::date AS d,
         count(*) FILTER (WHERE status = 200)                                   AS ok_200,
         count(*) FILTER (WHERE status IN (301, 304))                           AS redir_3xx,
         count(*) FILTER (WHERE status = 410)                                   AS gone_410,
         count(*) FILTER (WHERE status = 404)                                   AS miss_404,
         count(*) FILTER (WHERE status >= 500)                                  AS err_5xx,
         count(*)                                                               AS total
    FROM analytics_mirror.requests
   WHERE ts >= now() - interval '14 days'
     AND visitor_type = 'ai_mediated'
   GROUP BY 1
)
SELECT d,
       total,
       ok_200,
       redir_3xx,
       gone_410,
       miss_404,
       err_5xx,
       round(100.0 * (total - ok_200)::numeric / nullif(total, 0), 2) AS pct_non_200,
       round(100.0 * gone_410::numeric            / nullif(total, 0), 2) AS pct_410,
       round(100.0 * miss_404::numeric            / nullif(total, 0), 2) AS pct_404,
       round(100.0 * redir_3xx::numeric           / nullif(total, 0), 2) AS pct_3xx
  FROM daily
 ORDER BY d;
```

**Baseline (this audit, 30d pre-fix):**

| metric | value |
|---|---:|
| `pct_non_200` | 6.27 % |
| `pct_3xx` | 6.26 % (301+304) |
| `pct_410` | 1.01 % |
| `pct_404` | 0.24 % |

**Target thresholds (14d post-deploy):**

- `pct_non_200` → **< 2.0 %** (stretch: < 1.0 %).
- `pct_3xx` → < 1.5 % (only "legitimate" canonical redirects like trailing-slash normalisation should remain; UUID 301s should have flat-lined).
- `pct_410` → < 0.2 % (only `soft-410` rendered bodies remain; empty-410 UUID leaks eliminated).
- `pct_404` → ≤ baseline (already absorbed by FU-QUERY-20260418-01).

Alert condition (inject as a smedjan audit gate once deploy lands): `pct_non_200 > 3.5` on any single day post-deploy triggers rollback investigation.

Auxiliary query — top residual offenders (sanity check for unexpected tail):

```sql
SELECT path, status, count(*) AS hits
  FROM analytics_mirror.requests
 WHERE ts >= now() - interval '14 days'
   AND visitor_type = 'ai_mediated'
   AND status IN (301, 404, 410, 500)
 GROUP BY 1, 2
 ORDER BY hits DESC
 LIMIT 25;
```

---

## Out of scope / deferred

- `compliance_subscribers` capture on retired-entity page — owned by FU-CONVERSION-20260418-03 (retention).
- ZARQ CTA placement on `/dataset/*`, `/safe/*` success pages — owned by FU-CONVERSION-20260418-01.
- `/safe/<slug>` 500s (22 hits; e.g. `/safe/pipedrive`, `/safe/notion`) — separate follow-up, would be `FU-QUERY-20260418-*`; flagged here but not part of citation-rot.
- Classifier gaps (Claude undercounted per Finding 5) — FU-CONVERSION-20260418-05.

## References

- Parent audit: `~/smedjan/audit-reports/2026-04-18-conversion.md` §Finding 2.
- Related CSV (top 30/30 301+410 with UUID→slug resolution): `~/smedjan/audit-reports/2026-04-18-citation-redirect-plan.csv` (60 rows).
- Related CSV (broader 4xx triage): `~/smedjan/audit-reports/2026-04-18-citation-4xx-triage.csv` (500 rows).
- Current handler (to be replaced): `agentindex/api/discovery.py:543–548`.
- Current 410 short-circuit (to be removed): `agentindex/seo_pages.py:588–591`.
- Model-404 middleware (already deployed, extend in (b)): `agentindex/api/endpoints/model_fallback.py`.
