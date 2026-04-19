# F01 — ZARQ Trust-Score block on top-5 AI-landing surfaces

> **Task**: FU-CONVERSION-20260418-01 (follow-up to AUDIT-CONVERSION-20260418, Finding 1)
> **Status**: proposal only — no production deploy from this ticket
> **Branch**: `smedjan-factory-v0`
> **Baseline snapshot**: `smedjan/baselines/FU-CONVERSION-01-zarq-crosslink-baseline-2026-04-19.json`

## 1. Problem

Over the 30d window ending 2026-04-18 the mirror shows **1 of 36,331** AI-mediated
sessions (0.003%) reached any `/zarq/*` path, across only **3 of 1,480** unique
AI-mediated IPs (0.20%). ZARQ is the monetizable surface; Nerq is the cited one.
Every AI-cited dataset/model/safe/profile/agent page today renders a Trust Score
*value* but gives the reader no signpost to the trust methodology or to the
crypto side of the product. The bridge is missing.

## 2. Baseline (captured 2026-04-19)

Source: `analytics_mirror.requests` on `smedjan.nbg1`, latest row 2026-04-18T14:24:41Z
(lag ≈ 20h; run-not-blocked per freshness rubric). Full JSON snapshot in
`baselines/FU-CONVERSION-01-zarq-crosslink-baseline-2026-04-19.json`.

| Metric | Value |
|---|---:|
| ai_mediated total sessions (30d) | 36,331 |
| ai_mediated unique IPs (30d) | 1,480 |
| ai_mediated hits to `/zarq/*` | **1** |
| ai_mediated unique IPs to `/zarq/*` | **3** |

Surface landing volume (ai_mediated, status<400, GET, 30d):

| Surface | Hits | Uniq IPs | Renderer |
|---|---:|---:|---|
| `/dataset/*` | 7,074 | 1,189 | `agentindex/seo_asset_pages.py::_render_dataset_page` |
| `/model/*`   | 4,227 |   949 | `agentindex/seo_dynamic.py::_render_model_page` |
| `/profile/*` | 4,071 | 1,068 | `agentindex/demand_pages.py` (`/profile/{slug}`) |
| `/safe/*`    | 3,917 | 1,088 | `agentindex/agent_safety_pages.py::mount_agent_safety_pages` |
| `/agent/*`   | 2,548 |   916 | 301 → `/safe/{slug}` (`agentindex/api/discovery.py:543`) |

`/agent/*` inherits the fix automatically from `/safe/*`.

## 3. Design

A single shared HTML component — the **ZARQ trust-provenance block** — rendered
on all five surfaces near the existing Trust Score card. Same markup, same CSS,
same crosslink targets everywhere so we can measure one change, not five.

Three constraints shape the design:

1. **Cheap to parse for LLMs.** ChatGPT/Claude already cite Nerq Trust Scores
   — we want the next citation to include the ZARQ methodology link inline.
   Plain `<a href="/zarq/docs">` with descriptive anchor text, no JS.
2. **Non-destructive.** Slots below the trust_card / score_grid and above
   `<h2>Details</h2>`. Doesn't reflow the existing layout.
3. **One source of truth.** Defined once as a shared template/helper, included
   by five renderers. Variant label comes from a request-level A/B hash so
   AI-bot UAs are handled the same as humans (they cache either way).

### 3.1 Variant A — control (no change)

Current markup. Keeps the existing `trust_card` / `score_grid` block exactly as
rendered today.

### 3.2 Variant B — treatment (ZARQ trust-provenance block)

Rendered immediately after the existing score grid:

```html
<aside class="zarq-trust-block" aria-label="Trust Score provenance"
       data-experiment="fu-conv-01" data-variant="B"
       style="margin:16px 0;padding:16px;border:1px solid #e5e7eb;border-left:3px solid var(--warm,#c2956b);background:#fafafa">
  <div style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#6b7280;margin-bottom:6px">
    Trust Score provenance
  </div>
  <p style="font-size:14px;line-height:1.55;margin:0 0 10px;color:#374151">
    This <strong>{score:.0f}/100</strong> Trust Score is computed by the
    <strong>ZARQ trust engine</strong> — the same independent, hash-chained
    methodology Nerq applies to {entity_label}s and ZARQ applies to crypto
    tokens &amp; DeFi protocols.
  </p>
  <div style="font-size:13px;line-height:1.6">
    <a href="/zarq/docs" style="color:var(--warm,#0d9488);font-weight:600">
      How the Trust Score is calculated &rarr;
    </a>
    &nbsp;·&nbsp;
    <a href="/zarq" style="color:var(--warm,#0d9488)">
      Apply the same methodology to crypto
    </a>
  </div>
</aside>
```

Fields:

- `{score:.0f}` — the Trust Score the page already renders.
- `{entity_label}` — surface-specific noun: `"AI model"`, `"dataset"`,
  `"AI agent"`, `"AI tool"`, `"agent profile"`.

Why two links, not one:

- `/zarq/docs` = methodology (what a skeptical citation-follower wants).
- `/zarq` = product landing (what the AI-to-ZARQ funnel actually monetizes).

We bias the visual weight to `/zarq/docs` because AI-referred readers are
evaluators, not shoppers. The secondary `/zarq` link exists to capture the
small tail that *is* shopping.

### 3.3 Before / after — illustrative, `/model/{slug}`

Today the template emits (roughly):

```html
<h1>{name}</h1>
<p class="desc">{desc_text}</p>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin:16px 0">
  …Trust Score / Grade / Stars / Downloads cards…
</div>
<h2>Details</h2>
…
```

After (treatment variant B):

```html
<h1>{name}</h1>
<p class="desc">{desc_text}</p>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin:16px 0">
  …Trust Score / Grade / Stars / Downloads cards…
</div>
<!-- BEGIN fu-conv-01 ZARQ trust-provenance block (variant B only) -->
<aside class="zarq-trust-block" …>…see §3.2…</aside>
<!-- END fu-conv-01 -->
<h2>Details</h2>
…
```

The same insertion point applies to `_render_dataset_page` (after
`score_grid`), `demand_pages.py /profile/{slug}` (after the existing trust
card), and `agent_safety_pages.py` (after the verdict card).

### 3.4 Shared component

Proposed new file (not yet wired in): `agentindex/crypto/templates/zarq_trust_block.html`
storing the raw HTML template, plus a small Python helper in (new)
`agentindex/crypto/zarq_trust_block.py` exposing:

```python
def render_zarq_trust_block(score: float | None, entity_label: str, variant: str) -> str:
    if variant != "B" or score is None:
        return ""
    # f-string the template with safe defaults; return empty on missing score
```

No existing file is modified by this ticket. Integration in the five
renderers is scoped to a follow-up (see §6).

## 4. A/B split

- **Unit**: request. Hash `(client_ip, path)` → bucket; stable for a given IP
  over the 14d window so a returning reader sees the same variant.
- **Split**: 50 / 50.
- **Eligibility**: only GETs with `status < 400` on the five surfaces. Bots
  that look at `robots.txt` still get variants — we want AI crawlers to
  recrawl pages with the new link so the methodology URL enters the LLM
  citation corpus faster.
- **Kill-switch**: ENV var `FU_CONV_01_FORCE=A` forces control globally
  without a deploy.
- **Assignment logged** via `X-Exp-Variant` response header (`A` or `B`) so
  analytics_mirror pickup is trivial — header already flows through the
  tunnel to the mirror's request log.

## 5. Measurement plan (14-day readout)

**Primary KPI**: distinct ai_mediated IPs reaching `/zarq/*` in 14d window.

- Baseline (30d-normalized to 14d): ≈ **1.4 IPs**.
- Target: **≥ 30 IPs** (≈ 1% of ai_mediated IPs on treated surfaces).
- Read split by variant using the `X-Exp-Variant` column the mirror already
  captures; compare B vs A.

**Secondary KPIs** (directional, not gating):

1. `/zarq/docs` ai_mediated hits — 14d, split by variant.
2. Click-through proxy: ai_mediated sessions that hit a top-5 surface AND
   later hit `/zarq/*` within 24h, by variant.
3. Recrawl uptake: AI-bot (not ai_mediated) unique paths that fetched any
   of the 5 surfaces in the 14d window — proxy for whether ChatGPT/Claude
   refresh the citation index after the DOM change.

**Readout SQL** (template — mirror uses `analytics_mirror.requests`; variant
column = the header the middleware writes):

```sql
-- Primary KPI by variant (14d post-deploy)
WITH seen AS (
  SELECT DISTINCT ip,
         COALESCE(exp_variant, 'A') AS variant
    FROM analytics_mirror.requests
   WHERE ts BETWEEN :deploy_ts AND :deploy_ts + interval '14 days'
     AND visitor_type = 'ai_mediated'
     AND path ~ '^/(dataset|model|safe|profile|agent)/'
)
SELECT variant,
       count(DISTINCT r.ip) AS ips_reaching_zarq
  FROM analytics_mirror.requests r
  JOIN seen USING (ip)
 WHERE r.ts BETWEEN :deploy_ts AND :deploy_ts + interval '14 days'
   AND r.path LIKE '/zarq%'
 GROUP BY 1;
```

If `exp_variant` is not present on the mirror at deploy time, fall back to
writing a dedicated `analytics_mirror.experiment_assignments` row per
request (the mirror worker already tails Caddy access logs and can pick up
one additional header with no schema migration — see
`analytics-mirror/tail.py` path extension).

## 6. Deploy plan (for a *later* ticket)

This ticket ends at "proposal + baseline". The production deploy is a
separate follow-up — FU-CONVERSION-20260418-01b — and will require:

1. Create `agentindex/crypto/templates/zarq_trust_block.html` + helper.
2. Patch five renderer sites with a single `+ _render_zarq_trust_block(...)`
   concat in each. No schema / route / sitemap changes.
3. Add the A/B assigner middleware writing `X-Exp-Variant`.
4. 48h canary on `/dataset/*` only; abort if LCP on synthetic run regresses
   > 50ms or if ai_mediated 5xx rate on treated paths exceeds A by > 0.1pp.
5. Readout at D14; decision gate ≥ 30 distinct ai_mediated IPs → ZARQ in
   variant B (doubling the target vs. A, not just vs. historical).

## 7. Non-goals / boundaries

- **Not touched**: `robots.txt`, `sitemap.xml`, `agentindex/api/main.py`,
  `alembic/`, `.env` files, `docs/buzz-context.md`, `CLAUDE.md`.
- **Not shipping**: the block itself. This ticket produces design + baseline
  only; the shared component, the middleware and the five call-site patches
  ship under FU-CONVERSION-20260418-01b.
- **Not blocking expansion-first**: the proposal adds ~420 bytes of HTML per
  page; it does not introduce a dependency or a scheduled job.
