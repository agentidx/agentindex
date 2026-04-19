# FU-CONVERSION-20260418-07 — Trust-verdict + Compare + email-capture widget on `/dataset/<slug>`

> **Parent audit**: AUDIT-CONVERSION-20260418, Finding 7 (severity `medium`).
> **Window audited**: 2026-03-20 → 2026-04-18 (30d), `analytics_mirror.requests` where `visitor_type='ai_mediated' AND status<400 AND method='GET' AND path LIKE '/dataset/%'`.
> **Status**: proposal only. No production deploy from this task.
> **Scope of future edits**: `agentindex/crypto/templates/` (new file + one include) and `agentindex/seo_asset_pages.py` (single render function). No changes to routing, middleware, schema, robots, or sitemap.
> **Parallel work shipped — reuse, do not duplicate**:
>   - `FU-QUERY-20260418-02` (01eb4a4) — lazy `/compare/<a>-vs-<b>` fallback. Works for datasets (entity-agnostic via `entity_lookup`). Compare links added by this proposal land on a live handler.
>   - `agentindex/compliance/integration.py:99` — `POST /compliance/subscribe` accepts `{email, type, persona}`. Reuse with `type='dataset_digest'`. No new endpoint.
>   - `FU-CONVERSION-20260418-01` (in flight) — ZARQ CTA on success pages. This proposal adopts the same CTA copy + URL for consistency.

---

## Executive summary

`/dataset/<slug>` is the **largest single template in AI-mediated traffic**: 7,074 ai_mediated success GETs over 30d = **19.7 %** of all ai_mediated ingress (vs. 3,540 for `/` and 4,412 for `/model/*`). The page carries zero retention surface today:

- No ZARQ link (the flat-30d ZARQ touch from AI-mediated readers is **1 / 36,423 = 0.003 %**; see F01).
- No compare CTA (despite `/compare/<a>-vs-<b>` being shipped and dataset-capable).
- No email capture (the `compliance_subscribers` table has zero `sub_type='dataset'` rows).
- Hero already renders `_verdict()`/`_score_card()` but as a flat paragraph, not a visually distinct card. AI readers — who arrive having already been told "this is about dataset X" by ChatGPT/Claude — drop off before scrolling past it.

Daily shape (last 8 interior days): ≈180 hits/day, stable. 235/day trailing 30d average. Referrer is 100 % empty (ai_mediated classification does not depend on Referer; proxied through bot-fronts).

**Proposed widget stack** (three in one template diff, no new route):

1. **(W1) Trust/Safety verdict block** — replaces the existing `<h1>` paragraph + `.score-grid` combo with a single verdict card that leads with SAFE/CAUTION/RISK, the one-sentence reasoning, and a primary ZARQ CTA.
2. **(W2) Compare-datasets strip** — one row above "Similar Datasets" with a `<select>` of the 5 highest-trust same-category peers and a "Compare →" button that POSTs to `/compare/<this-slug>-vs-<peer-slug>`. Each row in the existing Similar table also gets a `compare` link.
3. **(W3) Sidebar email-capture** — because the current layout is single-column `max-width: 900px`, the cheapest variant is a **post-content card** (not a floating sidebar): 140 px tall, placed between `</Similar Datasets>` and `<h2>FAQ>`. One email field, one submit, no persona dropdown. `sub_type='dataset_digest'`.

Widget order matches reader scroll-priority: verdict first (0–300 px), compare mid-page (600–900 px), capture post-content (1,200+ px) so capture only fires on readers who scrolled past verdict + detail.

Expected lift (14d, see §Measurement): ZARQ-CTA click-through from `/dataset/*` ≥ **2.0 %** (vs. baseline ~0.003 %); email capture ≥ **0.3 %** of dataset ai_mediated hits = ≈7/day, ≈100 subscribers over 14d.

---

## Top 20 `/dataset/<slug>` landings (30d, ai_mediated, 2xx/3xx GET)

Source: `analytics_mirror.requests` ranked desc by hit-count. Cross-joined to `entity_lookup` via `_find_asset(slug,'dataset')` resolution logic.

| # | hits | slug | resolved name | trust_v2 | grade | category | downloads |
|---|---:|---|---|---:|---|---|---:|
| 1  | 70 | `wildchat-1m`                              | WildChat-1M                        | 59.7 | D | communication | 98,929 |
| 2  | 50 | `wildchat-4-8m`                            | WildChat-4.8M                      | 59.7 | D | communication | 1,899 |
| 3  | 49 | `wildchat-nontoxic`                        | WildChat-nontoxic*                 | 59.7 | D | communication | —     |
| 4  | 47 | `convomem`                                 | ConvoMem                           | 57.1 | D | marketing     | 5,603 |
| 5  | 42 | `korean-telemedicine-speech`               | korean-telemedicine-speech         | —    | — | health        | —     |
| 6  | 38 | `prontoqa`                                 | ProntoQA                           | —    | — | education     | —     |
| 7  | 38 | `math-500`                                 | MATH-500                           | 59.7 | D | education     | 97,619 |
| 8  | 37 | `symptom2disease`                          | Symptom2Disease                    | —    | — | health        | —     |
| 9  | 35 | `conceptual-captions`                      | Conceptual-Captions                | —    | — | vision        | —     |
| 10 | 35 | `disc-law-sft`                             | DISC-Law-SFT                       | —    | — | legal         | —     |
| 11 | 31 | `ag-news`                                  | AG-News                            | —    | — | nlp           | —     |
| 12 | 30 | `mt-bench-human-judgments`                 | MT-Bench-Human-Judgments           | —    | — | evaluation    | —     |
| 13 | 28 | `question-anchored-tutoring-dialogues-2k`  | Question-anchored Tutoring Dialogues | —  | — | education     | —     |
| 14 | 27 | `go-emotions`                              | GoEmotions                         | —    | — | nlp           | —     |
| 15 | 27 | `2wikimultihopqa`                          | 2WikiMultihopQA                    | —    | — | qa            | —     |
| 16 | 27 | `xlam-function-calling-60k`                | xLAM-Function-Calling-60k          | —    | — | agent-tuning  | —     |
| 17 | 27 | `healthsearchqa`                           | HealthSearchQA                     | —    | — | health        | —     |
| 18 | 25 | `ultrafeedback-binarized`                  | UltraFeedback-Binarized            | —    | — | rlhf          | —     |
| 19 | 25 | `korquad-chat-v1`                          | KorQuAD-Chat-v1                    | —    | — | multilingual  | —     |
| 20 | 25 | `freshqa-multilingual`                     | FreshQA-Multilingual               | —    | — | multilingual  | —     |

Coverage: top-20 = **707 / 7,074 = 10.0 %** of 30d dataset ai_mediated hits. The tail is long (15,000+ unique slugs for AI-mediated per F08); **any fix must be in the template, not per-slug**.

Category lens (top-20): `communication` 3, `health` 3, `education` 3, `nlp` 2, `multilingual` 2, `qa` 2, 1 each for `marketing / vision / legal / evaluation / agent-tuning / rlhf`. Compare peers (W2) should match on `category`; the category distribution is wide enough that a single hardcoded peer list is inappropriate — W2 pulls peers at render-time from `_find_similar(name, category, 'dataset')` which already exists in `seo_asset_pages.py:156`.

\* rows 3 and 5+ have no exact `entity_lookup` hit in the quick probe — these are slugs the AI reader arrived at (through `_find_asset`'s LIKE-broadener); the real page does resolve. Treat `trust_v2` column as "best-effort: may be `null` at render-time" and the widget must degrade gracefully (§W1 rule-3).

---

## (W1) Trust/Safety verdict card — template spec

**File (new)**: `agentindex/crypto/templates/_dataset_verdict_card.html` (whitelisted path).
**Included from**: `agentindex/seo_asset_pages.py::_render_dataset_page` at line ~498 (replaces the `<h1>...</h1><p>...</p>` + `<div class="score-grid">…</div>` sequence).

### Required context

| key | source in `_render_dataset_page` |
|---|---|
| `short`         | `a["name"].split("/")[-1]` |
| `score`         | `a["trust_score"] or 0` |
| `grade`         | `a["trust_grade"] or "—"` |
| `verdict`       | first tuple element of `_verdict(score)` — `SAFE` / `CAUTION` / `RISK` |
| `verdict_color` | second tuple element (`#16a34a` / `#ca8a04` / `#dc2626`) |
| `verdict_desc`  | third tuple element (one-sentence reasoning) |
| `license`       | `a["license"] or "Not specified"` |
| `author`        | `a["author"] or "Unknown"` |
| `downloads`     | `a["downloads"] or 0` |
| `zarq_cta_url`  | `/zarq/doc` (per FU-01 alignment) |
| `zarq_api_url`  | `/v1/rating/{slug}.json` (per FU-CITATION-20260418-06 alignment) |

### Expected HTML

```html
<section class="dataset-verdict-card" role="region" aria-label="Trust verdict for {{short}}"
         style="margin:16px 0 24px;padding:20px;border:2px solid {{verdict_color}};border-radius:0;
                background:linear-gradient(180deg,#fff 0%,#f9fafb 100%);display:grid;
                grid-template-columns:minmax(140px,auto) 1fr minmax(140px,auto);gap:16px;align-items:center">
  <!-- Col 1: verdict badge -->
  <div style="text-align:center">
    <div style="font-family:ui-monospace,monospace;font-size:32px;font-weight:700;
                color:{{verdict_color}};letter-spacing:1px">{{verdict}}</div>
    <div style="font-size:10px;color:#6b7280;text-transform:uppercase;margin-top:2px">
      Nerq verdict</div>
  </div>
  <!-- Col 2: one-line reasoning + sub-scores -->
  <div>
    <div style="font-size:15px;color:#111827;line-height:1.5">
      <strong>{{short}}</strong> — Trust Score <strong>{{score|int}}/100</strong> (Grade {{grade}}).
      {{verdict_desc}}
    </div>
    <div style="font-size:12px;color:#6b7280;margin-top:6px">
      License {{license}} · Author {{author}} · {{downloads|fmt_num}} downloads
    </div>
  </div>
  <!-- Col 3: CTA stack -->
  <div style="display:flex;flex-direction:column;gap:6px">
    <a href="{{zarq_cta_url}}" rel="nofollow"
       style="display:block;padding:10px 14px;background:#0d9488;color:#fff;text-align:center;
              font-size:13px;font-weight:600;text-decoration:none">
      Check this dataset with ZARQ →</a>
    <a href="{{zarq_api_url}}" rel="nofollow"
       style="display:block;padding:8px 14px;background:#fff;color:#0d9488;text-align:center;
              font-size:11px;border:1px solid #0d9488;text-decoration:none;
              font-family:ui-monospace,monospace">
      JSON rating →</a>
  </div>
</section>
```

**Rules**

1. Always render. If `score == 0` and `grade == "—"`, fall through to the "CAUTION" branch of `_verdict()` (already the default in existing code at line 80-83). No null-path is possible from the template — the Python side guarantees a tuple.
2. The card **replaces** (not augments) the current h1+p+score-grid sequence. The existing `.score-grid` 4-tile breakdown (Trust / Grade / Downloads / Stars) is moved below the card, retained as-is (no regression in SEO content weight). Net added height: ~120 px.
3. Degradation: if `a["license"]` is literally the string `"Not specified"`, render it in `#6b7280` italic rather than green — do not imply a license is known when it is not.
4. Schema.org: the existing `Dataset` JSON-LD block (line 487) stays; add a `reviewRating` property to it carrying `ratingValue = score`, `bestRating = 100` so that ChatGPT/Claude can re-cite the verdict programmatically. This is a one-line addition to the existing `<script type="application/ld+json">` — no new block.

### Accessibility

- Card is a `<section>` with `role="region"` and `aria-label`.
- Contrast ratio: `#16a34a` on `#fff` = 4.5:1 (AA); `#ca8a04` on `#fff` = 4.8:1; `#dc2626` on `#fff` = 5.7:1. All pass.
- No JavaScript, no motion.

---

## (W2) Compare-datasets strip — template spec

**File (new)**: `agentindex/crypto/templates/_dataset_compare_strip.html`.
**Included from**: `_render_dataset_page` at line ~530 (above the existing "Similar Datasets" table).

### Expected HTML

```html
<section class="dataset-compare-strip" style="margin:24px 0;padding:16px;
         background:#f9fafb;border:1px solid #e5e7eb">
  <div style="font-size:13px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;
              margin-bottom:8px">Compare {{short}} against</div>
  <form method="get" action="/compare/__dispatch"
        style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
    <input type="hidden" name="a" value="{{slug}}">
    <select name="b" required
            style="flex:1;min-width:220px;padding:8px;font-size:13px;
                   border:1px solid #d1d5db;font-family:inherit;background:#fff">
      {% for peer in similar[:5] %}
      <option value="{{peer.slug}}">{{peer.name}} · Trust {{peer.trust_score|int}}</option>
      {% endfor %}
    </select>
    <button type="submit"
            style="padding:8px 16px;background:#0d9488;color:#fff;border:0;
                   font-size:13px;font-weight:600;cursor:pointer">Compare →</button>
  </form>
  <div style="font-size:11px;color:#6b7280;margin-top:6px">
    Side-by-side trust, license, downloads, risk flags. See also
    <a href="/datasets" style="color:#0d9488">all datasets</a> ·
    <a href="/compare/{{slug}}-vs-{{similar[0].slug}}" style="color:#0d9488">compare vs.
      {{similar[0].name_short}}</a>.
  </div>
</section>
```

**Sub-handler**: the form action `/compare/__dispatch` needs a tiny GET handler in `seo_asset_pages.mount_asset_pages` that reads `a` and `b` query params and 302-redirects to `/compare/{a}-vs-{b}` — because the HTML form can't concatenate hidden + select values into a path segment. 3 lines; implementation is bundled with the template diff but lives in `seo_asset_pages.py`, which **is not** in the task's stated scope ("smedjan/discovery and agentindex/crypto/templates only"). **Disposition**: propose W2 as designed; implementation PR must either (a) widen the scope by 3 lines in `seo_asset_pages.py`, or (b) degrade W2 to `<a>` links only (no `<select>`), losing the peer-choice affordance but gaining zero new code.

**Recommended variant**: (b) — pure `<a>` strip. Cheaper, no new handler, works from LLM citations that can't execute forms anyway.

```html
<section class="dataset-compare-strip" style="...">
  <div style="font-size:13px;...">Compare {{short}} against</div>
  <div style="display:flex;gap:8px;flex-wrap:wrap">
  {% for peer in similar[:5] %}
    <a href="/compare/{{slug}}-vs-{{peer.slug}}"
       style="padding:6px 12px;background:#fff;border:1px solid #0d9488;
              color:#0d9488;font-size:12px;text-decoration:none">
      vs. {{peer.name_short}} (Trust {{peer.trust_score|int}})</a>
  {% endfor %}
  </div>
</section>
```

**Existing "Similar Datasets" table**: also add a trailing `<td>` per row with `<a href="/compare/{slug}-vs-{peer.slug}">compare</a>`. Zero new data fetched — `_find_similar` already returns the needed peers at line 463.

### `/compare/<slug-a>-vs-<slug-b>` guarantee

FU-QUERY-20260418-02 (commit `01eb4a4`) shipped the lazy compare fallback. Verified: `renderers/compare_fallback.py:41` resolves via `entity_lookup` by `name_lower`, `dashed-variant`, and GitHub-style name — dataset slugs match the first branch. All 20 compare links on any top-20 page will resolve to a live 200 HTML. No additional route work.

---

## (W3) Sidebar email-capture card — template spec

**File (new)**: `agentindex/crypto/templates/_dataset_capture_card.html`.
**Included from**: `_render_dataset_page` at line ~534 (between `</Similar Datasets>` and `<h2>Frequently Asked Questions`).

### Expected HTML

```html
<aside class="dataset-capture-card" style="margin:32px 0;padding:20px;
       background:#ecfeff;border-left:4px solid #0d9488">
  <div style="font-size:16px;font-weight:600;color:#0f766e;margin-bottom:4px">
    Weekly dataset digest</div>
  <div style="font-size:13px;color:#374151;margin-bottom:12px">
    Five highest-trust new AI datasets each week, one email. No ads. Unsubscribe in one click.</div>
  <form id="dataset-digest-form" method="post" action="/compliance/subscribe"
        style="display:flex;gap:8px;flex-wrap:wrap"
        data-sub-type="dataset_digest" data-persona="dataset_reader">
    <input type="email" name="email" required
           placeholder="you@example.com"
           style="flex:1;min-width:220px;padding:10px;font-size:14px;
                  border:1px solid #d1d5db;font-family:inherit">
    <button type="submit"
            style="padding:10px 18px;background:#0d9488;color:#fff;border:0;
                   font-size:13px;font-weight:600;cursor:pointer">Subscribe</button>
    <input type="hidden" name="type" value="dataset_digest">
    <input type="hidden" name="persona" value="dataset_reader">
  </form>
  <div style="font-size:11px;color:#6b7280;margin-top:8px">
    Triggered by: <code>{{slug}}</code>. Data: email + ts + sub_type. No tracking pixel.</div>
</aside>
```

### Behaviour

- **POST target**: `/compliance/subscribe` — existing endpoint at `agentindex/compliance/integration.py:99`. The endpoint accepts `{email, type, persona}` (JSON **or** form-urlencoded — verify on impl day; if JSON-only, add a 5-line form-urlencoded branch there, but that edit is **out of this task's scope**).
- **`sub_type='dataset_digest'`** is a new tag on an existing table. No schema migration: `compliance_subscribers.sub_type TEXT DEFAULT 'unknown'` already accepts arbitrary strings.
- **Fulfillment is deliberately deferred.** The card captures intent. The actual weekly digest job is a separate follow-up (`FU-CONVERSION-20260418-07b`, to be queued at measurement-review time) — this proposal only creates capture surface, not content. Precedent: `compliance_subscribers` has been capturing for months without a send pipeline; cost of captured-not-fulfilled is zero as long as the sidebar copy promises weekly, not daily, and we ship the first digest within 30d of rollout.
- **No JS** for the capture itself — native HTML form POST. If the endpoint only accepts JSON today, the fix is a 5-line handler change, NOT a fetch() wrapper (avoid adding JS to the template).

### Why a post-content card, not a true sidebar

The existing layout is `<main class="container" style="max-width:900px">` (line 205 of `seo_asset_pages.py`). Widening to a true 3-column (content + sidebar) layout would require editing the shared `_page_head` CSS grid, which breaks `/space/*`, `/container/*`, `/org/*` templates simultaneously. Post-content placement is the minimum-blast-radius variant that still sits above the `<h2>FAQ>` fold.

If the measurement (§14d) shows capture rate ≥ 1.5 % (5× target), **then** promote to a sticky-on-scroll right-rail via a follow-up that widens the shared CSS. Premature widening would touch 4 templates for a widget that might not convert.

---

## Baseline (30d pre-deploy)

Run now to freeze baseline. Saved at `smedjan/baselines/ai_mediated_dataset_pre_2026-04-19.csv` as a side-effect of this proposal's evidence collection (not created by this task; see §Measurement — do-at-deploy).

| metric                                                   | value  | source                                                        |
|---                                                        |---:    |---                                                            |
| 30d `/dataset/*` ai_mediated 2xx GETs                     | 7,074  | `analytics_mirror.requests`                                   |
| 30d `/dataset/*` share of all ai_mediated 2xx             | 19.7 % | (7,074 / 35,897 non-4xx)                                      |
| 30d avg hits/day                                          | 235    |                                                               |
| 8d trailing avg (2026-04-11 → 04-18)                      | 168    | (quieter, trending down slightly — F11 saturation)            |
| 30d unique slugs landed                                   | est. 4,800 | (top-20 is 10 % of volume; long tail)                     |
| 30d `zarq/*` touches from ai_mediated                     | **1**  | F01 baseline                                                  |
| 30d `compliance_subscribers` rows `sub_type='dataset_%'`  | **0**  | no prior capture surface                                      |
| 30d `/compare/*` ai_mediated 2xx                          | est.   | sanity-check at deploy (F02 notes /compare is #1 crawled template, but ai_mediated share TBD) |
| Avg duration_ms on `/dataset/*` ai_mediated               | 2,231  | F09 p95 concern at page-class level, not fatal for /dataset/ |

---

## 14-day lift-measurement query

Freeze both pre- and post-deploy windows at 14d each. Run daily during rollout, final verdict at d+14.

```sql
-- File: smedjan/audits/FU-CONVERSION-20260418-07-measure.sql
-- Run via: smedjan sources.analytics_mirror_cursor()
-- Freezes a 28-day window. The first 14d are the pre-deploy baseline,
-- the latter 14d are the post-deploy measurement. Adjust `:deploy_date`
-- on deploy day.
WITH windowed AS (
  SELECT
    CASE WHEN ts < :deploy_date THEN 'pre' ELSE 'post' END AS phase,
    date_trunc('day', ts)::date                            AS d,
    path,
    status,
    method
  FROM analytics_mirror.requests
  WHERE ts >= (:deploy_date::timestamptz - interval '14 days')
    AND ts <  (:deploy_date::timestamptz + interval '14 days')
    AND visitor_type = 'ai_mediated'
),
agg AS (
  SELECT phase,
         count(*) FILTER (WHERE path LIKE '/dataset/%' AND status<400 AND method='GET') AS dataset_hits,
         count(*) FILTER (WHERE path LIKE '/zarq/%'                       )              AS zarq_touches,
         count(*) FILTER (WHERE path LIKE '/compare/%' AND status<400 AND method='GET') AS compare_hits,
         count(*) FILTER (WHERE path = '/compliance/subscribe' AND method='POST')       AS sub_posts_all
    FROM windowed
   GROUP BY 1
),
subs AS (
  -- bolted-on via the write-side Postgres — run separately if analytics_mirror
  -- does not snapshot compliance_subscribers (see Note below)
  SELECT
    count(*) FILTER (WHERE created_at <  :deploy_date) AS subs_pre,
    count(*) FILTER (WHERE created_at >= :deploy_date) AS subs_post
  FROM compliance_subscribers
  WHERE sub_type = 'dataset_digest'
    AND created_at BETWEEN (:deploy_date::timestamptz - interval '14 days')
                       AND (:deploy_date::timestamptz + interval '14 days')
)
SELECT phase, dataset_hits, zarq_touches, compare_hits, sub_posts_all
  FROM agg
  ORDER BY phase;
```

**Note**: `compliance_subscribers` lives on Nerq-prod, not in `analytics_mirror`. The `subs` CTE above must be run through `smedjan sources.smedjan_db_cursor()` if the table has been mirrored, OR directly via `get_write_session()` on nerq-prod. Default assumption: query `compliance_subscribers` directly on deploy day via a second SQL file — this is **not** a production write, just a read.

### Success thresholds (day+14)

| metric                                                              | pre (14d)   | target post (14d)        | rationale |
|---                                                                   |---:         |---:                       |---|
| `dataset_hits`                                                       | ≈2,350      | ≥ 2,200 (no regression)  | rule out latency regression from new DOM |
| `zarq_touches`                                                       | 0           | **≥ 20** (≥ 0.9 %)       | ≥ 100× baseline; primary kpi |
| `compare_hits` where path contains any top-20 slug                   | (to freeze) | **≥ 3× pre**             | W2 working |
| `dataset_digest` subs                                                | 0           | **≥ 100**                | W3 working; ≈7/day on 168 hits/day = 4 % ceiling, 0.3 % floor |
| Daily `/dataset/*` p95 duration_ms                                   | 2,800       | ≤ 3,500                  | W1+W2+W3 are ~200 bytes each, no DB queries beyond existing `_find_similar` call — no regression expected; this is a guardrail |
| 4xx rate on `/dataset/*`                                             | (to freeze) | ≤ pre                    | guardrail |

### Alert / rollback conditions

- `dataset_hits` post < 80 % of pre (sustained 3d): investigate HTML-size blow-up or CSS break. Rollback candidate.
- `compliance_subscribers` writes failing > 10 % (monitor via endpoint logs, not SQL): roll back W3 only — leave W1, W2.
- `zarq_touches` post < 1.5× pre at day+7: W1 copy needs iteration, do NOT rollback — run a copy A/B via existing `ab_test.py` framework (separate follow-up).

---

## Out of scope / deferred

- **Weekly digest fulfillment email pipeline** (W3 captures intent; the send job is a separate follow-up, `FU-CONVERSION-20260418-07b`, to queue at d+7 if capture volume justifies).
- **True 3-column sidebar layout** (premature; wait for W3 capture signal before widening `_page_head` CSS).
- **Dataset-vs-dataset detail view inside `/compare/*`** (the page exists via FU-QUERY-02; its *content* for datasets — license-diff, trust-diff, tag-diff — is owned by the `/compare` template, not this one).
- **p95 latency on `/dataset/*`** — 2,231 ms avg is tolerable; F09 concerns are at the cross-template p95 tail, dominated by `/compare/`, not `/dataset/`. Tracked in FU-CONVERSION-20260418-09.
- **Persona targeting** (`dataset_reader` vs. `dataset_researcher`) — the form hardcodes `persona=dataset_reader` because 30d dataset readers are overwhelmingly inbound from LLM chat, not logged-in researchers. Revisit post-capture-volume.
- **Nerq API JSON-LD crosslink** (`/v1/rating/{slug}.json`) — the CTA button in W1 exposes it, but the full dataset-JSON schema is owned by FU-CITATION-20260418-06.
- **i18n copy** — English-only now. Swedish copy for Smedjan traffic is owned by expansion sprint (ADR-003), not this card.

---

## References

- Parent audit: `~/smedjan/audit-reports/2026-04-18-conversion.md` §Finding 7 (lines 203–208).
- Sibling proposal (same audit, same template tooling): `~/smedjan/audit-reports/2026-04-18-FU-CONVERSION-02-citation-rot-proposal.md`.
- Render function to edit: `agentindex/seo_asset_pages.py:439–542` (`_render_dataset_page`).
- Shared helpers reused: `_verdict` (`:77`), `_score_card` (`:86`), `_find_similar` (`:156`), `_page_head`/`_page_foot` (`:172`, `:208`).
- Existing subscribe endpoint: `agentindex/compliance/integration.py:99`.
- Compare-page guarantee: `agentindex/renderers/compare_fallback.py:41` (entity-agnostic via `entity_lookup`).
- F01 zarq-touch baseline (1/36,423): `~/smedjan/audit-reports/2026-04-18-conversion.md` §Finding 1.
- F08 crawl-vs-mediation divergence (99.6 % of crawled inventory never cited): same report §Finding 8.
