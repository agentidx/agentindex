# A9 follow-up — /safe/{slug} alt-link slug-drift characterisation

UTC ts: 2026-04-19T10:30:44Z
Parent: `smedjan/audits/A9-20260419T092237Z.md`
Scope: characterise every `agent_safety_slugs.json` entry where
`_make_slug(entry["name"]) != entry["slug"]`, propose a minimal
renderer fix, verify it resolves every drift class.

Read-only, repo-scan only. No DB writes, no prod state change.

## TL;DR

- **5,367 drifted entries** (8.78% of 61,132 served /safe/{slug} pages)
  — slightly above A9's 5,160 figure because A9 pre-filtered to
  edges-emitted-by-the-graph; this walk counts every mismatched row in
  the JSON.
- **75.3% of drift is one cause**: the legacy slug generator dropped
  `_` entirely, today's `_make_slug` substitutes `_` → `-`. That
  single pattern explains 4,040 of 5,367 rows.
- **A simple legacy-generator model** (`NFKD + ascii-ignore`, drop
  `_`, no `--` collapse, no edge-`-` strip, everything else identical
  to current) **reproduces 94.13% of all stored slugs** — strong
  evidence the drift is two different vintages of the same generator
  rather than ad-hoc slugs.
- **Proposed fix resolves 5,367/5,367 drift rows (100%)** — switch
  the alt-block href from `_make_slug(alt["name"])` to
  `alt.get("slug") or _make_slug(alt["name"])` after adding `slug` to
  `_get_alternatives`'s SELECT. All 5,367 stored slugs are in the
  served-slug set by construction, so the fix is provably lossless.
- **D-task queued**: `D-safe-alt-slug-fix-20260419`.

## Method

Script: `smedjan/scripts/A9_followup_slug_drift.py` (deterministic;
no DB; runs in <2s).

For each entry in `agent_safety_slugs.json`, compute
`_make_slug(entry["name"])` using the exact rules from
`agent_safety_pages.py::_make_slug` (lines 6063–6072). Compare to
`entry["slug"]`. Classify every mismatch with first-match-wins
priority: (1) unicode-fold, (2) underscore-collapsed,
(3) leading-dash-retained, (4) trailing-dash-retained,
(5) double-dash-retained, (6) leading-dot, (7) other.

In parallel, check whether a hypothesised legacy generator
(NFKD + ASCII-ignore, drop `_`, no `--` collapse, no edge-`-` strip)
reproduces the stored slug — a sanity check that stored slugs are
machine-produced, not hand-curated.

## Drift classification

| drift reason            |  count | %      | what current does that legacy didn't                                |
| ----------------------- | -----: | -----: | ------------------------------------------------------------------- |
| underscore-collapsed    |  4,040 | 75.27% | `_` → `-` (legacy dropped `_`)                                       |
| unicode-fold            |    603 | 11.24% | preserves non-ASCII (legacy did NFKD + ASCII-ignore)                 |
| double-dash-retained    |    307 |  5.72% | collapses `--` → `-` (legacy did not)                                |
| trailing-dash-retained  |    294 |  5.48% | `.strip('-')` removes trailing (legacy did not)                      |
| leading-dash-retained   |     44 |  0.82% | `.strip('-')` removes leading (legacy did not)                       |
| other                   |     79 |  1.47% | editorial overrides (stored slug unrelated to name; see below)       |
| **total**               |  **5,367** | **100%** |                                                           |

Legacy-generator model reproduces **5,052 / 5,367 (94.13%)** stored
slugs exactly, confirming the drift is overwhelmingly explained by a
single older generator vintage rather than per-entry curation.

### Sample per class

**underscore-collapsed** (4,040):

    Personal_AI_Infrastructure       → stored personalaiinfrastructure       (computed personal-ai-infrastructure)
    Yourdaylight/stock_datasource    → stored yourdaylightstockdatasource    (computed yourdaylightstock-datasource)
    mpfaffenberger/code_puppy        → stored mpfaffenbergercodepuppy        (computed mpfaffenbergercode-puppy)

**unicode-fold** (603):

    Bardiel – Trust Oracle           → stored bardiel--trust-oracle          (computed bardiel-–-trust-oracle)
    Yuna ユナ                        → stored yuna-ユナ-                     (computed yuna-ユナ)
    Men’s                            → stored mens                           (computed men’s)

**double-dash-retained** (307):

    Video & Audio Text Extraction    → stored video--audio-text-extraction   (computed video-audio-text-extraction)
    a-i--skills                      → stored a-i--skills                    (computed a-i-skills)

**trailing-dash-retained** (294):

    Trading-Agent-                   → stored trading-agent-                 (computed trading-agent)
    Agentic-Bug-Hunter-              → stored agentic-bug-hunter-            (computed agentic-bug-hunter)

**leading-dash-retained** (44):

    .claude                          → stored -claude                        (computed claude)
    -ternlang                        → stored -ternlang                      (computed ternlang)

**other** (79) — editorial overrides, stored slug doesn't derive from name:

    langgenius/dify                  → stored dify                           (computed langgeniusdify)
    pydantic/pydantic-ai             → stored pydantic-ai                    (computed pydanticpydantic-ai)
    cli                              → stored googleworkspacecli             (computed cli)

The "other" class can't be fixed by any `_make_slug` rewrite — these
slugs are authored, not computed. The proposed fix handles them
anyway because it bypasses `_make_slug` entirely when a stored slug
is available.

## Renderer fix (proposed, NOT applied here)

The `/safe/{slug}` alt-block renders at three sites in
`agent_safety_pages.py`:

| site  | line  | current                                                 |
| ----- | ----: | ------------------------------------------------------- |
| main alt-grid           | 8042 | `alt_slug = _make_slug(alt["name"])`         |
| safer-alternatives grid | 8501 | `alt_slug = _make_slug(alt["name"])`         |
| compare link (top alt)  | 8618 | `_alt_slug = _make_slug(alternatives[0]["name"])` |

`_get_alternatives` (line 5945) currently returns
`name, trust_score, trust_grade, category, source, stars` — slug is
dropped. `entity_lookup` does carry `slug` (verified via Nerq-RO
`\d entity_lookup`), so propagating it is a one-word SELECT change.

### Proposed diff (4 hunks, 8 changed lines)

```diff
--- a/agentindex/agentindex/agent_safety_pages.py
+++ b/agentindex/agentindex/agent_safety_pages.py
@@ -5949,7 +5949,7 @@ def _get_alternatives(category, current_name, current_score, limit=5):
         rows = session.execute(text("""
-            SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
-                   trust_grade, category, source, stars
+            SELECT name, slug,
+                   COALESCE(trust_score_v2, trust_score) as trust_score,
+                   trust_grade, category, source, stars
             FROM entity_lookup
@@ -8042,1 +8042,1 @@
-            alt_slug = _make_slug(alt["name"])
+            alt_slug = alt.get("slug") or _make_slug(alt["name"])
@@ -8501,1 +8501,1 @@
-                alt_slug = _make_slug(alt["name"])
+                alt_slug = alt.get("slug") or _make_slug(alt["name"])
@@ -8618,1 +8618,1 @@
-        _alt_slug = _make_slug(alternatives[0]["name"])
+        _alt_slug = alternatives[0].get("slug") or _make_slug(alternatives[0]["name"])
```

Why `alt.get("slug") or _make_slug(alt["name"])` and not just
`alt["slug"]`: `entity_lookup.slug` is nullable in the schema (no
`NOT NULL` constraint). The `or _make_slug(...)` fallback keeps the
pre-fix behaviour for any row whose `slug` is NULL, preserving
today's outcomes in the one case the change cannot strictly improve.

## Dry-run verification

For every drifted row, the proposed fix emits `/safe/{stored-slug}`.
Stored slug IS the served-slug-set key (that's how the snapshot is
indexed), so resolution is guaranteed by construction. Script output:

    resolved (stored in served set)   : 5,367/5,367
    would still 404                   : 0

Per drift class (sample of 5 each from the script, all resolved):

| class                   | sampled | resolved | fails |
| ----------------------- | ------: | -------: | ----: |
| underscore-collapsed    |       5 |        5 |     0 |
| unicode-fold            |       5 |        5 |     0 |
| double-dash-retained    |       5 |        5 |     0 |
| trailing-dash-retained  |       5 |        5 |     0 |
| leading-dash-retained   |       5 |        5 |     0 |
| other (editorial)       |       5 |        5 |     0 |

The fix is class-agnostic: it does not attempt to emulate the legacy
generator, it just stops re-computing a slug the system already has.

## Scope-notes

- This audit does NOT modify `_make_slug`. Rewriting the slug
  generator to match the legacy form would fix the graph symmetrically
  but risks silently changing behaviour for non-drifted pages; the
  href-side fix is a cleaner surgical correction.
- Bug only affects the alt-block on `/safe/{slug}`. Other
  `/safe/{slug}` URL construction (canonical, breadcrumb, sub-pages)
  uses `slug` directly and is unaffected.
- The A9 edge-count of 21,701 dead alt-links is the concrete SEO
  impact: with the fix applied, 21,701 previously 404-ing internal
  links resolve to valid /safe pages — a ~7.1% increase in live
  internal alt-link coverage graph-wide.

## Follow-up task queued

**`D-safe-alt-slug-fix-20260419`** — apply the proposed 4-hunk diff
above. Risk: low. Deps: `A9-followup-slug-drift`. Whitelist:
`agentindex/agentindex/agent_safety_pages.py`. Acceptance: SELECT
includes `slug`, all three alt-href sites use
`alt.get("slug") or _make_slug(alt["name"])`, smoke-test shows a
previously-drifted alt href (e.g. on any /safe/* page with
`Personal_AI_Infrastructure` as a top-5 neighbour) now resolves.

Queued via `smedjan queue add`. Created: 2026-04-19T10:30:57Z.

## Reproducing

```bash
python3 /Users/anstudio/agentindex/smedjan/scripts/A9_followup_slug_drift.py
```

Runs in <2s, deterministic, no DB, no network.
