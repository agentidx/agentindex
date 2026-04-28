# L2 Block 2b — Dependency Graph (king-sections variant)

**Status:** design + shipped under registry allowlist (2026-04-19) | **Owner:** Smedjan factory T005
**Depends on:** T003 (registry tiering / AI-demand scoring), T004 (Block 2a registry-allowlist pattern)
**Scope:** npm only (register-gated via `L2_BLOCK_2B_REGISTRIES`), ~60K distinct from-entities and ~73K distinct to-entities in the underlying edge table.

## Why this block, why npm first

`public.dependency_edges` is Nerq-exclusive data (per the 2026-04-18 Front D
inventory at `~/smedjan/discovery/L2-data-surfacer-inventory.md`). No external
data broker — Libraries.io, ecosyste.ms, Snyk — gives the reverse-dep count
for a named package in a single cacheable HTTP call. Leading our
`/safe/{slug}` king-section prose with `"Depended on by N other npm packages"`
therefore establishes Nerq differentiation *before* the External Trust
Signals block (Block 2a) lists the independent verification sources.

npm is the first and only registry allow-listed today because:

- It is the largest and most-cited package ecosystem by AI-assistant demand
  (see `smedjan.ai_demand_scores`).
- The edges table is 100 % npm at the moment: `registry='npm'` covers
  885,641 rows (387,139 runtime / 498,502 dev) with no parallel registry
  partitions. Adding pypi / crates would require a distinct crawler pass
  tracked separately; widening the allowlist to those registries before
  their data lands would render an empty block, which we treat as a
  correctness bug even though the renderer is fail-closed.

## Data sources (read path)

Two tables on the Nerq read-only replica, joined lazily at request time:

| Field | Source | Reach |
|---|---|---|
| `reverse_count` | `SELECT COUNT(*) FROM public.dependency_edges WHERE entity_to = slug AND registry='npm' AND dependency_type <> 'dev'` | every npm slug with at least one incoming runtime edge (top quartile exceeds 1,000 — `react` is 7,373 reverse edges today, `zod` 5,440) |
| `direct_count`, `dev_count` | same table, `entity_from = slug`, split by `dependency_type = 'dev'` | every npm slug with forward edges |
| `avg_dep_trust`, `deps_with_trust` | `SELECT AVG(trust_score), COUNT(*) FROM public.software_registry WHERE registry='npm' AND slug = ANY(<direct deps>)` | 528,306 npm rows of 528,339 have non-null trust scores — so the join is effectively saturated |
| `dormant`, `dormant_reason` | `deprecated` OR age of `GREATEST(last_commit, last_release_date, last_updated) > 365` on `public.software_registry` | every enriched npm slug |

### Sample query (verified 2026-04-19 against Nerq RO)

```sql
WITH edges AS (
  SELECT entity_to
    FROM public.dependency_edges
   WHERE entity_from COLLATE "C" = 'express'
     AND registry = 'npm'
     AND dependency_type <> 'dev'
)
SELECT
  (SELECT COUNT(*) FROM public.dependency_edges
      WHERE entity_to COLLATE "C" = 'express'
        AND registry = 'npm' AND dependency_type <> 'dev')   AS reverse_count,
  (SELECT COUNT(*) FROM edges)                               AS direct_count,
  (SELECT ROUND(AVG(sr.trust_score)::numeric, 1)
     FROM public.software_registry sr
    WHERE sr.registry = 'npm'
      AND sr.slug COLLATE "C" IN (SELECT entity_to FROM edges)
      AND sr.trust_score IS NOT NULL)                        AS avg_dep_trust,
  (SELECT deprecated
     FROM public.software_registry
    WHERE registry='npm' AND slug COLLATE "C"='express')     AS deprecated,
  (SELECT GREATEST(last_commit, last_release_date, last_updated)
     FROM public.software_registry
    WHERE registry='npm' AND slug COLLATE "C"='express')     AS self_last_active;

 reverse_count | direct_count | avg_dep_trust | deprecated |    self_last_active
---------------+--------------+---------------+------------+-------------------------
          1840 |           28 |          49.2 | f          | 2025-12-01 20:49:43.268
```

`COLLATE "C"` is applied on every equality/`ANY` predicate because the Nerq
replica has an observed ICU collation drift (see
`smedjan/renderers/block_2b.py` and `smedjan/renderers/block_2a.py` for
the same workaround) — default equality silently returned zero rows for
byte-identical slugs during the 2026-04-18 crawl.

## Rendered template

```
This package is depended on by {reverse_count} other npm packages.
Its {direct_count} direct dependencies have trust scores averaging
{avg_dep_trust}/100 across {deps_with_trust} scored deps.
{dormant_warning_if_any}
```

Rendered as a `<div class="section block-2b-kings">` with a `<h2>` and a
three- to four-bullet `<ul>`, mirroring the Block 2a HTML so the
surrounding CSS applies without new rules. None of the sacred tokens
(`pplx-verdict`, `ai-summary`, `SpeakableSpecification`, `FAQPage`) ever
appear inside the block — enforced by the dry-run harness below.

## Gating

- **New env var:** `L2_BLOCK_2B_REGISTRIES` — comma-separated allowlist.
  Same fail-closed semantics as `L1_UNLOCK_REGISTRIES` /
  `L2_BLOCK_2A_REGISTRIES`. Empty / unset ⇒ block disabled. Value
  `npm` ⇒ the initial canary. Value `*` or `all` ⇒ future full rollout.
- **Placement:** inside `king_sections`, ABOVE Block 2a.
  Reverse-dependency counts and trust-score averages are the most
  differentiated (Nerq-exclusive) numbers on the page, so they lead the
  citable prose. Block 2a's External Trust Signals then layer in the
  independent-verification evidence underneath.
- **Old T112 shadow path (`L2_BLOCK_2B_MODE`) is untouched.** T005 is
  additive; operators wouldn't flip both gates on simultaneously, but
  even if they did, the shadow block is an HTML comment and the
  king-section block is visible prose, so they cannot visually collide.

## Fail-closed surface

- Any `SourceUnavailable`, `psycopg2.Error`, or unexpected exception in
  `_fetch_dependency_graph` returns `None` ⇒ nothing rendered.
- Empty result (zero forward edges AND zero reverse edges) returns
  `None` ⇒ nothing rendered — we never emit a "no data" placeholder
  inside a citable block.
- Registry allowlist is re-read from the environment on every call so
  the dry-run harness can flip the env var in-process.

## Validation

- `python3 -m py_compile` passes on `agentindex/smedjan/l2_block_2b.py`,
  `agentindex/agent_safety_pages.py`, and `scripts/dryrun_l2_block_2b.py`.
- `scripts/dryrun_l2_block_2b.py --limit 100` against the Nerq RO replica
  (2026-04-19) produced: 100 T112 rendered / 98 T005 rendered / 0 crashes /
  0 sacred-token hits / 0 gate-divergence cases. The two slugs that did
  not render T005 were outside the forward/reverse edge coverage and the
  helper correctly returned `None`.
- No plist edits, no `launchctl kickstart`, no git push. Rollout remains a
  follow-up task (risk=medium, `needs_approval`).
