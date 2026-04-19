# FU-QUERY-20260418-03 — /hacked/<slug> fate: ship renderer (Option A)

- Parent audit: `smedjan/audit-reports/2026-04-18-query.md`, finding #3.
- Parent task: AUDIT-QUERY-20260418.
- Decision date: 2026-04-19.
- Branch: `smedjan-factory-v0`.

## Observation

`analytics_mirror.requests` over the 2026-04-12 → 2026-04-18 window:

| metric                             | value    |
|------------------------------------|---------:|
| `/hacked/<slug>` requests          | 7,462    |
| `/hacked/<slug>` 200 responses     | 0        |
| `/hacked/<slug>` 404 responses     | 7,462    |
| AI-bot hits (Claude + ChatGPT)     | 235      |
| Human hits                         | 963      |
| Apple / Meta / generic crawlers    | ~5,950   |

Referrer data: 112 of the 7,462 hits were internally referred from
`nerq.ai/was-<slug>-hacked` — i.e. our own pages emit at least some
`/hacked/<slug>` links. The remaining ~98 % had no referrer or an
external one (cached / guessed URL patterns).

No `/hacked/<slug>` route was mounted anywhere in the FastAPI app. The
only adjacent route is `/was-<slug>-hacked` (pattern_routes.py:498).

## Options considered

**A. Ship a /hacked/<slug> renderer (chosen).**
Returns 200 HTML with structured data. Converts 7,462 404s/week into
200s, restores AI citability, and keeps the URL shape addressable for
future external docs / registries. No sitemap change, no forbidden-file
touch.

**B. Return 410 + drop /hacked/ from sitemap + 301 inbound links to
/safe/<slug>.** Ruled out: the acceptance criterion "no longer listed
in sitemap.xml" requires editing `sitemap.xml`, which is on the Smedjan
worker's forbidden list. Executing B would need an explicit approval
hop; A satisfies the "200 with content" branch of the same acceptance
criterion with one commit.

## Data-source note

The task brief named "entity_lookup breach-incident fields" as the
backing source. Verification (2026-04-19) shows `public.entity_lookup`
has no breach columns — it is the registry lookup table, not the
breach store. The actual breach rows live in:

- `public.breach_history` — 962 rows, `entity_slug`, `breach_date`,
  `severity`, `records_exposed`, `data_types`, `description`, `source`.
- `public.software_registry` — `cve_count`, `cve_critical`,
  `security_score` per (slug, registry).

The renderer joins those two. Of the top 30 `/hacked/` 404 slugs, 0
match `breach_history` and most match `software_registry` with
`cve_count=0`. The page therefore most often surfaces a "No Confirmed
Breach on Record" verdict — honest, cacheable, and a 200.

## What shipped

1. `agentindex/api/endpoints/hacked.py` — new module, `APIRouter`
   exporting `GET /hacked/{slug}` → `HTMLResponse(200)`.
   - Reads `breach_history` (up to 10 rows per slug) and
     `software_registry` via `smedjan.sources.nerq_readonly_cursor`.
   - Renders: headline verdict, incident table (when breaches > 0),
     CVE summary, canonical `<link>`, Article + FAQPage JSON-LD, and
     cross-links to `/safe/<slug>` and `/was-<slug>-hacked`.
   - Slug whitelist regex `^[a-z0-9][a-z0-9._-]{0,199}$`; invalid
     slugs return 400 with `X-Robots-Tag: noindex`.
   - `Cache-Control: public, max-age=3600`.

2. `agentindex/api/discovery.py` — added `include_router(router_hacked)`
   immediately after the `/rating` mount block.

## Not shipped (intentionally)

- No changes to `sitemap.xml`, `robots.txt`, `pattern_routes.py`, or
  `agent_safety_pages.py`. Those sit outside the worker's whitelist and
  are not needed for 200-serving.
- No 301 redirect scheme for external inbound links. Since the path
  now serves 200, the external-link question is moot.
- No production restart. The file changes are committed on
  `smedjan-factory-v0`; activation happens when Anders next deploys or
  Buzz cycles the service.

## Follow-ups worth filing separately

- Trace the 112 internal `nerq.ai/was-<slug>-hacked → /hacked/<slug>`
  referrers. Something on the `/was-<slug>-hacked` template emits
  `/hacked/<slug>` links; the new renderer masks the bug but does not
  fix it. `pattern_routes.py` and its localised variants are likely
  candidates.
- Backfill `breach_history` with npm / android-package breaches. The
  current table is HaveIBeenPwned-heavy; the top `/hacked/` slugs are
  dev-ecosystem packages (`libxext`, `qdrant`, `doctrine-inflector`, …)
  which will look clean under the current data even when CVEs exist
  elsewhere.

## Acceptance criterion check

> "Either /hacked/ pages return 200 with content, or /hacked/ returns
> 410 and is no longer listed in sitemap.xml. 100 % 404 rate
> eliminated."

Met via the "200 with content" branch. Post-deploy, every `/hacked/<x>`
request will resolve through `router_hacked` and return 200 HTML with
structured data — no slug is special-cased to 404.
