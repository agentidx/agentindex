# Query-Form Pilot: /was-X-hacked — Replicating Mar 21 Effect

**Started:** 2026-04-13
**Hypothesis:** Creating enriched /was-X-hacked pages and submitting via IndexNow will trigger OAI-SearchBot indexing, which will surface in ChatGPT-User citations.

## Pilot scope

- 100 entities (top ChatGPT-User from 30d /safe/* paths)
- 23 languages each = **2,300 URLs**
- IndexNow submission: 2,300 URLs → HTTP 200 (confirmed)

## What was deployed

Enhanced `/was-X-hacked` pages via `_hacked_page()` in `pattern_routes.py`:
- Direct answer in first 100 words with `pplx-verdict ai-summary` classes
- CVE count + critical CVEs from software_registry
- Security dimension score
- Article + FAQPage dual schema
- "What We Check" section (NVD, GitHub Advisories, OSV.dev)
- Cross-link to `/safe/{slug}`
- All existing template infrastructure (hreflang, NERQ_CSS, NAV, FOOTER)

**NOT a new template.** Uses existing `_head()`, `_foot()`, `_xlinks()`, `_faq()`, `_resolve()` from pattern_routes.py. The `_resolve()` function was enhanced to return `cve_count`, `cve_critical`, `security_score`, `registry`.

## Baseline (pre-deploy, 7-day window)

| Metric | Value |
|---|---:|
| ChatGPT-User hits on /was-*-hacked (these 100 entities) | **0** |
| OAI-SearchBot hits on /was-*-hacked (these 100 entities) | **9** |
| ChatGPT-User hits on /safe/* (same 100 entities, 7d) | ~350 |
| Total ChatGPT-User (all paths, 7d) | ~8,400 |

## Decision rule (pre-registered)

Measurement starts from first OAI-SearchBot pickup of a new enhanced URL.

| Outcome (7d after OAI-SearchBot pickup) | Action |
|---|---|
| >50 ChatGPT-User hits on /was-*-hacked | Scale to 5-7 new URL forms |
| 20-50 hits | Investigate — is content quality the bottleneck? |
| <20 hits | Mechanism not reproducible via new URL forms alone |

## Reference: Mar 21 spike timeline

- OAI-SearchBot indexed 9 new URL patterns
- ChatGPT-User jumped from 647 → 1,198/day SAME DAY
- The 2x jump became permanent plateau

## Daily measurement queries

```sql
-- ChatGPT-User hits on pilot URLs
SELECT date(ts), COUNT(*) FROM requests
WHERE bot_name='ChatGPT' AND bot_purpose='user_triggered'
  AND path LIKE '/was-%-hacked'
  AND ts >= '2026-04-13'
GROUP BY date(ts) ORDER BY 1;

-- OAI-SearchBot indexing of pilot URLs
SELECT date(ts), COUNT(*) FROM requests
WHERE user_agent LIKE '%OAI-SearchBot%'
  AND path LIKE '/was-%-hacked'
  AND ts >= '2026-04-13'
GROUP BY date(ts) ORDER BY 1;

-- Total ChatGPT-User macro trend
SELECT date(ts), COUNT(*) FROM requests
WHERE bot_name='ChatGPT' AND bot_purpose='user_triggered'
  AND ts >= '2026-04-13'
GROUP BY date(ts) ORDER BY 1;
```

## Pilot entities (top 20 by ChatGPT-User 30d volume)

| Slug | /safe/* hits (30d) | CVE count |
|---|---:|---:|
| 083f89ad-... (UUID) | 54 | 0 |
| trulens | 51 | 0 |
| davideaststitch-mcp | 47 | 0 |
| make | 34 | 0 |
| weaviate | 30 | 0 |
| replit | 29 | 0 |
| poe-quora | 27 | 0 |
| expensify | 27 | 0 |
| tiktok | 20 | 0 |
| selvo | 20 | 0 |
