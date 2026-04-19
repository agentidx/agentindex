# Nerq / ZARQ — Query Audit 2026-04-17

Autonomous audit executed by Claude Code. Data sources: GSC (Google Search Console) 90d for `https://nerq.ai/` and `sc-domain:zarq.ai`, Bing Webmaster API (GetQueryStats / GetPageStats / GetRankAndTrafficStats / GetCrawlStats), Postgres (`entity_lookup`, `agents`), SQLite `analytics.db`, live page fetches, and 100 WebSearches against incumbent SERPs.

Output artefacts in `~/smedjan-audit/`: `gsc_data.db`, `bing_data.db`, `query_classification.csv`, `high_opportunity.csv`, `low_ctr.csv`, `zero_impression_pages.{csv,md}`, `dead_content.csv`, `intent_gap.md`, `competitor_landscape.md`, `journal-query.md`.

---

## Executive Summary

**Indexation is not the problem. CTR and content depth are.**

| Metric | nerq.ai | zarq.ai |
| --- | --- | --- |
| Pages indexed (Bing) | **14.6M** | 74K |
| Bing crawl errors (90d) | **227,221** | 857 |
| GSC pages seen (top 25K, 90d) | 25,000 | 10,581 |
| GSC pages with ≥1 click (90d) | **979 (3.9%)** | 188 (1.8%) |
| GSC queries (unique, 90d) | 8,024 | 2,054 |
| GSC queries with ≥1 click | **171 (2.1%)** | (heavy branded skew) |
| GSC total impressions (90d) | 46,206 | 23,706 |
| GSC total clicks (90d) | **231** | 783 |
| GSC overall CTR | **0.50%** | 3.30% |
| Queries ranking pos <5 | 515 | 136 |
| … of those, with 0 clicks | **480 (93%)** | 125 (92%) |
| Pages with ≥100 impressions & 0 clicks | 119 | (not computed) |
| Intent gap (100 non-branded queries, top-10 presence) | **4%** | 0% |

**Why it is invisible (ranked):**
1. **CTR collapse at visible positions.** 93% of queries where nerq.ai ranks top-5 got *zero* clicks in 90 days. Titles / metas fail to convert — page ranks, user doesn't pick it.
2. **Entity-detail pages serve 5xx errors.** A random sample of 100 nerq.ai entity pages showed **20% returning HTTP 502/500/connection-refused**. Those pages cannot convert impressions into clicks because they either time out or show empty shells.
3. **Comparison/`/compare/` pages rank but don't click.** 7,095 `/compare/` pages in GSC; only 255 (3.6%) earned ≥1 click. Compare pages dominate top-impression lists (top 20 impression leaders are almost all "X vs Y") but almost none convert.
4. **Core positioning intents are owned by incumbents.** 96/100 target queries return nerq.ai nowhere in top 10. "Trust score for AI agents", "AI tool trust rating", "best MCP servers", "crypto trust score" — all owned by credo.ai, collibra.com, glama.ai, mcpservers.org, Chainalysis, TRM Labs. Nerq isn't competing; it isn't on the field.

**Wins so far (keep doing):**
- `/compare/` pattern does rank (pos 3-6 on niche pairs like "tavily vs searxng", "openclaw vs openhands"). The *URL pattern* works; the *titles* and *content depth* fail.
- `/safe/npm` ranks #3 for "npm package trust rating" — prototype of a winning hub pattern.
- Brand term "zarq ai" gets 648/1,494 clicks — brand awareness is forming.

**Dead ends (stop pursuing):**
- `/agent/<uuid>` URL pattern: 50 pages in GSC after 4.98M-row agent index, 2 clicks total. UUID slugs cannot rank.
- `/a-scam/` prefix: 6 pages in GSC, 0 clicks. Either the name is indexable dead-weight or these pages are being deboosted.
- Random-string Bing impressions ("woalskdl", "knllll", "xxxxx3") — these are crawler noise on generated pages, not intent. Zero strategic value.

---

## 1. Query classification

Source: union of GSC queries (10,078 unique) and Bing query stats (485 rows), deduped.

| Intent | Count | % |
| --- | --- | --- |
| other | 9,305 | 88.3% |
| versus (X vs Y) | 674 | 6.4% |
| trust_check (is X legit/safe) | 354 | 3.4% |
| best_for (best/top X for…) | 87 | 0.8% |
| alternative (X alternatives) | 66 | 0.6% |
| definition (what is X) | 46 | 0.4% |
| tutorial (how to X) | 1 | 0.0% |

**Reading:** Versus + trust_check + alternative = 10.4% of queries, but probably >30% of strategic click potential. Tutorial and definition are essentially missing — Nerq has no long-form explainer content that Google indexes as informational intent. This is a content-planning gap, not a technical one.

CSV: `~/smedjan-audit/query_classification.csv`.

---

## 2. High-opportunity queries

Pulled from GSC `gsc_queries` (both properties), bucketed:

| Bucket | Definition | Qualifying | In CSV |
| --- | --- | --- | --- |
| **Type A** | pos 11–30, impressions ≥ 50 | 43 | 43 |
| **Type B** | impressions ≥ 100, clicks < 5 | 92 | 92 |
| **Type C** | pos 4–10, CTR < 2% | **4,710** | 500 (top by impressions) |

Potential clicks if pos=1 calculated using CTR curve (pos1=27.6%, pos2=15.8%, pos3=11.0%).

**Headline finding:** Type C is the giant — 4,710 queries where nerq already ranks 4–10 but CTR is below 2%. If the top 500 Type-C queries moved to pos 1, naive CTR-curve estimate suggests ~13,000 extra clicks in 90d (vs current 231 total). The ceiling isn't rank — it's *CTR on existing rank*.

Top Type-B (pages Google is actively testing but no one picks):
- `julia vs langchain` — 225 imp, pos 3.6, **0 clicks**
- `scikit-learn vs airflow` — 220 imp, pos 3.9, **0 clicks**
- `playwright vs supabase` — 210 imp, pos 3.3, **0 clicks**
- `ansible vs tensorflow` — 209 imp, pos 2.0, **0 clicks**
- `tensorflow vs ansible` — 205 imp, pos 2.2, **0 clicks**
- `airflow vs keras` — 202 imp, pos 1.7, **0 clicks**

These are page-content or title/meta failures. Google trusts the URL enough to rank pos 2–4 repeatedly; users see the title and scroll past.

CSV: `~/smedjan-audit/high_opportunity.csv`.

---

## 3. Low-CTR queries (ranking but not clicking)

Filter: pos 1–10, impressions ≥ 50, CTR < 1%. 113 queries qualified.

Representative offenders (all top-5, all ≥100 impressions, all 0 or 1 click):
- `alternatives to scikit-learn` — 1,388 imp, pos 11.4, 0 clicks (page `/alternatives/scikit-learn-scikit-learn`)
- `huihui-qwen3-next-80b-a3b-instruct-abliterated-nvfp4` — 1,224 imp, 0 clicks
- `gemma-3-4b-it-heretic-uncensored-abliterated-extreme-gguf` — 1,129 imp, 1 click

Pattern: **pages ranking well for their exact slug have 0 CTR**. This is either (a) SERP cannibalization by Hugging Face/official source, (b) title tag that doesn't differentiate Nerq's value, or (c) meta description that reads as a programmatic template.

CSV: `~/smedjan-audit/low_ctr.csv`.

---

## 4. Zero-impression pages

Random 500-entity sample from `entity_lookup` (is_active=true, slug not null). 499/500 missing from GSC top-25K. Curled 100 at `/model/<slug>` or `/a-scam/<slug>`.

| HTTP status | Count | Note |
| --- | --- | --- |
| 200 | 80 | Page served |
| 502 | 14 | Bad Gateway |
| 500 | 1 | Internal Server Error |
| 000 | 5 | Connection refused / timeout |

**20% serve errors.** Of the 80 that returned 200, content fields were always populated (title, meta, h1 all 0 missing on the 200 subset — the 20 "empty" are exactly the 20 errors).

**Reading:** The nerq.ai publishing layer has an availability problem on the long tail. ~1M/5M pages could silently be 5xx'ing — Google drops those from the index, which is consistent with GSC showing only 25K pages when Bing sees 14.6M. Bing's 227,221 crawl errors over 90d corroborates.

Details: `~/smedjan-audit/zero_impression_pages.csv` + `.md`.

---

## 5. Dead content

24,214 of 25,000 GSC pages for nerq.ai (**96.9%**) have <1 click OR <3 impressions over 90 days — effectively dead weight in terms of SEO value.

Faded-organic analysis against `analytics.db` was not possible: analytics.db only holds ~30 days (2026-03-18 → 2026-04-17), so there is no 60–180d comparison window available. 635,284 human requests in that 30-day window.

Pattern of dead content (sample):
- `/agent/<uuid>` — 50/4.98M agents in GSC, effectively 0% discoverable
- `/a-scam/<slug>` — 6 pages in GSC, 0 clicks
- Low-trust model slugs (fine-tune forks with no external interest)

CSV: `~/smedjan-audit/dead_content.csv` (top 2,000).

---

## 6. Intent gap

100 strategically chosen queries across AI discovery, MCP, trust/safety, package audit, X-vs-Y, crypto/trust, and developer tooling. WebSearched each; checked top 10 for nerq.ai OR zarq.ai.

**4/100 in top 10:**
1. `nerq ai search` — rank 1 (branded)
2. `npm package trust rating` — rank 3 (`/safe/npm`) ← non-branded win
3. `openclaw vs openhands` — rank 6 (`/compare/`)
4. `tavily vs searxng` — rank 4 (`/compare/`)

**0/100 visibility in:**
- MCP directories (15 queries) — owned by glama.ai, mcpmarket, mcpservers.org, mcp.so, pulsemcp
- AI safety / trust scoring (15 queries) — owned by credo.ai, collibra.com, safer-ai.org, futureoflife.org
- Supply-chain / package audit (15 queries, except `/safe/npm`) — owned by snyk.io, jfrog, reversinglabs, OWASP
- Crypto trust (10 queries) — owned by TRM Labs, Chainalysis, Elliptic, CertiK, DefiSafety, CoinGecko

Full per-query breakdown: `~/smedjan-audit/intent_gap.md`.

---

## 7. Competitor landscape (top 20 + 5 deep profiles)

Deep-fetched: credo.ai, glama.ai, mcpservers.org, scoutscore.ai, snyk security DB (mcp.so returned 403).

Cross-cutting patterns seen across every ranking incumbent:

1. **Named trust verdicts** alongside numeric score (A/B/C/F, HIGH/MED/LOW, RECOMMENDED/NOT). Nerq has `trust_grade` internally but doesn't surface it as a semantic label users search for.
2. **Side-by-side comparison UX** with explicit "failed vs passing" examples and named risk flags (e.g. scoutscore's `WALLET_SPAM_FARM`, `HAS_COMPLETE_SCHEMA`). A bare numeric score loses to a labelled one.
3. **10–50 explicit category tags**, not free-text. glama.ai has 50+ category tags and filters; that's the minimum table stakes in MCP discovery SERPs.
4. **Canonical URL patterns with a stable, human-readable ID** (`/vuln/SNYK-JS-…`, `/mcp/servers/<slug>`, `/advisor/<ecosystem>/<package>`). Nerq's `/agent/<uuid>` breaks this convention.
5. **Authority signal on every page** — "3,483 researcher-disclosed vulnerabilities" (Snyk), "12 Forrester perfect scores" (credo.ai), "21,655 servers" (glama). Nerq's equivalent ("4.7M models, 204K agents, hash-chained") needs to appear above the fold on indexable pages, not just the homepage.

Full: `~/smedjan-audit/competitor_landscape.md`.

---

## 8. Five ranked interventions

Ordered by expected ROI × speed. Data source in parens.

### #1 — Fix title/meta templates on `/compare/` and `/model/` pages
- **Hypothesis:** 93% of nerq.ai top-5 queries have zero CTR because titles/metas read as programmatic noise. Fixing templates converts existing rank into clicks without any new content.
- **Scope:** Rewrite title + meta templates for two URL patterns: `/compare/<a>-vs-<b>` and `/model/<slug>`. Add trust-grade + differentiated value prop to title. A/B test 1–2 variants.
- **Effort:** Low (template change in `agentindex/crypto/templates/`; 1 deploy; wait 2 GSC reporting cycles).
- **Expected impact:** Top-500 Type-C queries currently at pos 4–10 with <2% CTR. CTR-curve math suggests 3×–10× click lift on those queries alone — ~700–2,300 extra clicks/90d, without moving rank.
- **Risk:** Low. Title changes are reversible. Worst case: no change.
- **Data source:** `gsc_queries` pos<5 clicks=0 (480 queries nerq, 125 zarq); `high_opportunity.csv` Type C bucket (4,710 queries).

### #2 — Fix 5xx error rate on entity-detail pages
- **Hypothesis:** ~20% of entity pages return 5xx/connection-refused. Google quietly de-indexes those; Bing logs them as crawl errors (227,221 in 90d). Fixing availability unlocks indexation for up to ~1M currently-invisible pages.
- **Scope:** Root-cause the 502s (likely upstream timeout or upstream backend for certain slug classes — needs tracing on the FastAPI app). Add a health-probe + alert on 5xx rate per URL pattern.
- **Effort:** Medium. Requires instrumenting `agentindex.api.discovery` and probably fixing a specific slow database query path.
- **Expected impact:** Indexation ceiling rises from GSC's 25K observed → possibly 100K+ indexed pages within 30 days post-fix. Each indexed page is a lottery ticket for long-tail queries.
- **Risk:** Low–Medium. Don't mask errors with retries; fix the query/backend. Do not change the `/agent/<uuid>` URL pattern in the same change (separate intervention).
- **Data source:** `zero_impression_pages.csv` (20/100 non-200 sample); Bing `bing_crawl_stats` (227,221 errors on nerq.ai).

### #3 — Build an MCP directory hub at `/mcp/`
- **Hypothesis:** 15 tested MCP-intent queries returned nerq.ai 0/10. The `/compare/` and `/safe/npm` wins show Nerq *can* rank when a hub pattern exists. glama.ai (21K servers) and mcpservers.org both rank on "MCP server" intent with well-categorized directories. Nerq has the data (frameworks/protocols fields in `agents` / `entity_lookup`) but no dedicated hub.
- **Scope:** Build `/mcp/` index + `/mcp/servers/<slug>` detail pages + 10–20 category pages (e.g. `/mcp/category/github`, `/mcp/category/database`). Mirror glama's tag taxonomy (Official, Local, Remote, Python, TypeScript, Developer Tools, RAG, Autonomous Agents, …).
- **Effort:** Medium. Data already exists; new templates + routing + sitemap. 1–2 weeks.
- **Expected impact:** Entry into a SERP cluster Nerq currently has **0% visibility** in. Even rank 8–10 on "best MCP servers" would be material — that query cluster is actively growing.
- **Risk:** Low. New pages; doesn't touch existing routing.
- **Data source:** `intent_gap.md` batches (ac, aa); competitor profile of glama.ai in `competitor_landscape.md`.

### #4 — Surface named trust verdicts on every public page
- **Hypothesis:** Every competitor with durable trust-scoring SERP presence (scoutscore, Snyk, glama) pairs numeric scores with semantic labels (HIGH / A–F / RECOMMENDED / `WALLET_SPAM_FARM`). Numeric-only scores don't generate snippet-friendly text and don't match user mental models ("is X safe" → "YES/NO", not "0.73").
- **Scope:** On every `/model/`, `/agent/`, `/compare/` page, render `trust_grade` + `risk_class` + a 1-sentence verdict ("Trust A — production-grade observability"). Put it in the meta description template too. Add structured data (schema.org `Rating`).
- **Effort:** Low–Medium. Data exists (`entity_lookup.trust_grade`, `risk_class`, `trust_components`). Template + schema work.
- **Expected impact:** Lifts CTR (compounds with #1) and opens SERP feature eligibility (rating stars in rich result). Plausible entry into "is X legit/safe" intent (354 existing queries in that cluster).
- **Risk:** Low, provided we don't publish wildly-out-of-date grades. Confirm freshness from `trust_scored_at` before render.
- **Data source:** `competitor_landscape.md` (all five deep profiles); existing `entity_lookup` schema.

### #5 — Ship a ZARQ content layer for crypto-trust intent
- **Hypothesis:** ZARQ's underlying data (crash model v3, distance-to-default, trust scores for 205 tokens) is invisible on the web because it lacks indexable content pages. All 10 tested crypto-trust queries returned 0/10 (Chainalysis, TRM Labs, Elliptic, CertiK own the cluster).
- **Scope:** Build a token-detail page per symbol (`/token/<symbol>`) with trust score, DtD, crash probability, structural-weakness flags, and top peer comparisons. Build a 3–5 page explainer cluster ("what is distance to default", "how crash probability is estimated", "crypto trust score methodology"). Submit sitemap.
- **Effort:** Medium. Content authoring is the gate; templates are easy; data joins from `nerq_risk_signals` are already documented in CLAUDE.md.
- **Expected impact:** ZARQ currently gets 783 clicks mostly from brand searches ("zarq ai"). This intervention opens the non-branded crypto-trust cluster, which is where incumbent CPC is highest. Target: first non-branded ranking within 60 days.
- **Risk:** Medium. Claims made on those pages are load-bearing — they must match the methodology documented in the strategy docs. Legal/compliance review before publishing DtD scores per token.
- **Data source:** `intent_gap_batch_ad.md` (10 crypto queries, 0/10); existing `nerq_risk_signals`, `crash_model_v3_predictions` tables.

---

## Known gaps in this audit

- analytics.db only holds ~30 days of request data (2026-03-18 → present), so the "pages that previously ranked then died" analysis couldn't be done cleanly. Recommend configuring a 180d retention policy if this question matters ongoing.
- Postgres `agents` table COUNT(*) timed out under 5s default statement_timeout; total entity count cited (~5M) comes from `entity_lookup` + CLAUDE.md.
- `mcp.so` returned HTTP 403 to WebFetch (bot protection). Competitor profile for mcp.so is incomplete.
- Intent-gap was 100 queries, not exhaustive — SERP composition changes daily and these are a point-in-time sample from 2026-04-17.
- GSC returns top 25,000 rows per dimension; nerq.ai's real page count on Google is likely higher.
- WebSearch results reflect US-geolocated Google SERPs; international SERPs may differ.

---

## Appendix — Data inventory for follow-on weekly audits (added 2026-04-19)

This baseline audit was sourced from GSC, Bing Webmaster, live curls, and the
local `analytics.db` SQLite. **Subsequent weekly audits run from the Smedjan
factory and read `analytics_mirror` (Postgres on smedjan.nbg1.hetzner) plus
the Nerq read-only replica.** Those sources expose a different schema than
the ones referenced inline in §1–§7. To prevent re-derivation drift in
later audit runs, this appendix records what `analytics_mirror` and the
Nerq RO replica actually contain as of 2026-04-19, and how the brief's
intended dimensions map onto them.

### What `analytics_mirror` contains (Postgres, schema = `analytics_mirror`)

| Table | Rows (2026-04-19) | Purpose |
| --- | ---: | --- |
| `requests` | 7,183,367 | Raw request log: `ts, method, path, status, duration_ms, ip, user_agent, bot_name, is_bot, is_ai_bot, referrer, referrer_domain, query_string, search_query, country, ai_source, visitor_type, bot_purpose`. |
| `requests_daily` | 29,342 | Daily roll-up keyed by `(day, bot_name, is_ai_bot, is_bot, status, is_gptbot, is_preflight, visitor_type, country, lang)` with a `count` column. |
| `preflight_analytics` | 151,655 | AI-bot preflight probes: `ts, target, bot_name, ip, status, duration_ms, country`. |
| `_sync_state` | 3 | Mirror freshness: per-table `row_count, synced_at, source_host, source_hash, notes`. |

Mirror freshness as of 2026-04-19T01:30Z; the syncer publishes a fresh
`_sync_state` row each cycle.

### What `analytics_mirror` does NOT contain

The AUDIT-QUERY-20260418 task description named four tables that **do not
exist in any reachable schema**:

- `analytics_mirror.query_log` — not present
- `analytics_mirror.search_events` — not present
- `analytics_mirror.zero_result_queries` — not present
- `public.query_coverage` (Nerq RO) — not present

`requests.search_query` is populated on **7 of 7,183,367 rows** (≈0%), so
even the existing column is not a usable corpus for "what users typed into
Nerq's search box". `FU-QUERY-20260418-08` tracks the work to instrument
that signal end-to-end.

### What the Nerq RO replica contains

`smedjan_readonly`@`agentindex` exposes the production tables documented in
CLAUDE.md "Database tables" — notably `public.agents`, `public.entity_lookup`,
`public.nerq_risk_signals`, `public.crash_model_v3_predictions`,
`public.crypto_rating_daily`, `public.defi_protocol_tokens`. There is **no
`public.query_coverage`** table; coverage gaps must be derived by joining
`analytics_mirror.requests` (404 paths) against `entity_lookup` (known slugs).

### How the brief's dimensions map onto what we have

| Brief dimension | Where to source it from `analytics_mirror` |
| --- | --- |
| Query classification (§1) | Not directly available — needs GSC/Bing or a future `search_events` table. |
| High-opportunity queries (§2) | Not in mirror — depends on rank data (GSC). |
| Low-CTR queries (§3) | Not in mirror — depends on impressions/clicks (GSC). |
| Zero-impression pages (§4) | Substitute: `requests` paths with status 200 but `count<N` per day. |
| Dead content (§5) | Substitute: `requests_daily` per-path roll-up over a 30/90-day window. |
| Intent gap (§6) | Not in mirror — requires WebSearch sample of competitor SERPs. |
| Path-hygiene (404 distribution) | Native: `requests.status` per `path` regex. This is what the 2026-04-18 weekly audit pivoted to. |
| AI-bot citation damage | Native: `requests` filtered on `is_ai_bot=1` joined to `status=404`. |

### Provisioning vs. amending — current state

- **Provisioning** the four named tables is blocked on `FU-QUERY-20260418-08`
  (instrument the Nerq search endpoint to write `search_events`) and on a
  separate Nerq production change to land `public.query_coverage`. Neither
  is in scope for this follow-up.
- **Amendment** is this appendix. Future weekly audits should treat the
  inventory above as authoritative for `analytics_mirror`/Nerq RO sources
  and only rely on §1–§7 of this brief for the GSC/Bing-derived analysis
  that originally produced the baseline.
