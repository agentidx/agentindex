# FU-CONVERSION-20260418-08 — Crawled-but-uncited high-trust page prioritization

> Follow-up to **AUDIT-CONVERSION-20260418 Finding 8** (medium).
> Design deliverable only — no production deploy from this task.

## TL;DR

- Candidate universe (30d, status<400 GET): **97,089** AI-bot-crawled
  entity-shaped paths (`/safe/<slug>`, `/agent/<slug>`, `/model/<slug>`,
  `/dataset/<slug>`, `/profile/<slug>`); **15,760** unique AI-mediated-
  cited paths across all templates; **86,416** entity-shaped paths are
  crawled but never cited in the window.
- Filtering that set to entities with `entity_lookup.trust_grade IN ('A','A+')`
  yields **917** path rows across **373** A/A+ slugs (of 781 A/A+ total,
  so ~48% of top-trust entities are in the uncited-bot-crawl set — the
  other half is the **FU-CITATION-20260418-03** universe, i.e. never
  crawled at all, which is disjoint by construction).
- Top-100 carry **630 bot hits / 30d** in aggregate.  Hypothesised
  14-day citation lift from JSON-LD `SpeakableSpecification` + a
  one-sentence trust verdict:
    - parity model (systemwide 0.713% crawl→cite rate): **~2 AI-med
      visits / 14d across the 100 pages**
    - boosted model (2.5× — structured-data + A-tier branding uplift):
      **~5 AI-med visits / 14d across the 100 pages**
- Template split in the top-100: **93 `/safe/<slug>`**, **7 `/profile/<slug>`**.
  Grade split: **88 A, 12 A+**.  No `/model/`, `/dataset/`, or `/agent/`
  entries made the cut — their A/A+ slugs either already get ai_mediated
  traffic (cited, excluded here) or the bot isn't crawling them at all
  (FU-CITATION-20260418-03).
- Absolute lift is small because the page-level bot volume is small
  (top row = 21 hits / 30d). The value is **directional**: these are
  the 100 pages where a single cheap template change is most likely to
  produce the *first* AI-mediated citation in the window and get a
  confirmed signal on the shim's elasticity. Treat as an A/B tripwire,
  not a revenue lever.

## Source and method

Script: `smedjan/audits/FU-CONVERSION-20260418-08.py`.
Output: `~/smedjan/audit-reports/2026-04-18-conversion-uncited-high-trust.csv`.

Joins:
- `analytics_mirror.requests` — cited path set (`visitor_type='ai_mediated'`,
  status<400, GET, 30d) and bot-crawled entity-path set
  (`is_ai_bot=1`, status<400, GET, 30d, prefix filter).
- Left-anti-join bot-crawled minus cited, dedupe to slug via last-segment
  extraction, then inner-join to Nerq RO
  `entity_lookup` on `slug` filtered to `trust_grade IN ('A','A+')`.

## Verdict-sentence template

Single canonical form (one sentence, ≤160 chars for meta-description reuse):

```
ZARQ rates {name} at Trust Grade {trust_grade} ({trust_score_v2}/100) —
an A-tier {category} asset on {source}; see /zarq for methodology.
```

Example rows:
- `/safe/microsoft-qlib` → `ZARQ rates microsoft/qlib at Trust Grade A+
  (91/100) — an A-tier finance asset on github; see /zarq for methodology.`
- `/safe/vercel-workflow` → `ZARQ rates vercel/workflow at Trust Grade A+
  (91/100) — an A-tier devops asset on github; see /zarq for methodology.`
- `/profile/langchain-ai-langchain` → `ZARQ rates langchain-ai/langchain
  at Trust Grade A (86/100) — an A-tier coding asset on github; see /zarq
  for methodology.`

A single injection shim on the template layer (`/safe/<slug>`, `/profile/<slug>`)
can render this for any slug where `entity_lookup.trust_grade IN ('A','A+')`;
for lower grades, the sentence is still template-stable but reads as
"Trust Grade B" etc. — useful downstream for grades beyond the A-tier
scope of this task.

## Proposed JSON-LD `SpeakableSpecification` block

Intent: make the verdict sentence machine-extractable by voice / answer
engines (ChatGPT voice, Perplexity, Gemini) without changing the page's
HTML structure.  Injection point: `<script type="application/ld+json">`
inside the entity template's existing schema-org block (next to the
current `SoftwareApplication` / `Dataset` / `Organization` type).

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "WebPage",
  "url": "https://nerq.ai/safe/{slug}",
  "name": "{name} — ZARQ Trust Score",
  "description": "{verdict_sentence}",
  "speakable": {
    "@type": "SpeakableSpecification",
    "cssSelector": [".zarq-trust-verdict", "meta[name=description]"]
  },
  "about": {
    "@type": "SoftwareApplication",
    "name": "{name}",
    "applicationCategory": "{category}",
    "aggregateRating": {
      "@type": "AggregateRating",
      "ratingValue": "{trust_score_v2}",
      "bestRating": "100",
      "worstRating": "0",
      "ratingCount": "1",
      "reviewAspect": "Trust Grade {trust_grade}"
    }
  }
}
</script>
```

And the matching DOM target (so `SpeakableSpecification.cssSelector`
resolves to something the crawler can read inline):

```html
<p class="zarq-trust-verdict" data-zarq-grade="{trust_grade}"
   data-zarq-score="{trust_score_v2}">{verdict_sentence}</p>
```

Rendering rule (for the template handler):
- Render the `<p>` and the `<script>` only when
  `entity_lookup.trust_grade IN ('A','A+')`.  Lower grades get the same
  shim *without* JSON-LD speakable — the structured-data marker is the
  specific intervention being measured.
- `aggregateRating` is semantically defensible: ZARQ is the single
  authoritative rater and the score is a composite aggregate; this
  mirrors how Google exposes its own Trust Score pattern (see
  `/zarq/doc` for the methodology link).

## 14-day lift hypothesis (per-row, in CSV)

Per-row columns `ai_med_14d_parity` and `ai_med_14d_boosted` are
computed as:

```
parity  = bot_hits_30d × (36_423 / 5_109_642) × (14 / 30)
boosted = parity × 2.5
```

Formatted to integer with a `max(1, round(x)) if x ≥ 0.3` floor. Most
rows are below that floor individually (21-hit top row → 0.07 parity,
0.18 boosted → rounds to `0`). Aggregate across the 100 rows is the
meaningful number:

| Model | Total AI-med 14d | Implied per-page rate |
|---|---:|---:|
| parity (systemwide 0.713%) | 2.10 | 0.021 / page / 14d |
| boosted (2.5×) | 5.24 | 0.052 / page / 14d |

Which means the correct way to read this task is: **deploy the shim
across all 373 A/A+ slugs (not just top-100), measure the 14d lift in
the ai_mediated-hit count on those specific paths, and compare against
a matched-control bucket of B-tier slugs with the same bot_hits_30d
distribution.** Top-100 is the ranked priority list *within* that full
shim target; the lift signal only shows up at the ≥300-page rollout
scale.

## Coordination with FU-CITATION-20260418-03

FU-CITATION-20260418-03 asks for a "trust-score × crawl-coverage SQL
view" and feeds the **bot-invisible** high-trust slugs into internal-
linking proposals. That set is **disjoint** from this task's output:
- FU-CITATION-03 universe: `trust_grade IN ('A','A+') AND slug NOT IN
  bot-crawled paths`
- FU-CONVERSION-08 (this task): `trust_grade IN ('A','A+') AND slug IN
  bot-crawled paths AND slug NOT IN ai_mediated-cited paths`

Concretely: F3 has **408** A/A+ slugs never bot-crawled (`781 − 373`),
F8 has **373** A/A+ slugs bot-crawled-but-never-cited. Together the
two tasks cover **781 / 781 = 100%** of the A-tier entity universe.
Neither duplicates the other.

The measurement views should be stored co-located in
`smedjan.measurement` so a single dashboard surfaces both buckets with
consistent denominators. That view is scoped to FU-CITATION-03 (parent
task) — this task does not build it.

## Out of scope

- Production deployment. The shim HTML + JSON-LD goes through the
  normal template-change review once the lift hypothesis is validated.
- Expanding to B/B+/C grades. The boosted-multiplier argument is
  grade-specific (A-tier branding is part of the semantic payload);
  applying 2.5× to lower grades would inflate the model.
- AI-mediated landings on `/dataset/<slug>` / `/model/<slug>` / `/agent/<slug>`.
  None of those templates hit the top-100 here — their A/A+ slugs either
  are already cited or are bot-invisible (F3's territory).
