# Kings Definition

**Audited:** 2026-04-10 by Claude Code (Leverage Sprint Day 1 A3 audit)
**Status:** Read-only audit, no code changes made

## Classification function

There is **no single centralized classification function**. King status (`is_king = true`) is set per-registry by individual seed/crawler scripts at insert time. Each registry has its own threshold:

| Registry | Classification rule | File | Line |
|----------|-------------------|------|------|
| android | `installs > 10_000_000 or king_count < 5000` | `agentindex/crawlers/android_play_crawler.py` | 129 |
| wordpress | `global_rank <= 500` | `agentindex/crawlers/wordpress_king_enricher.py` | 173 |
| ai_tool | All seeded entities set `is_king = true` | `agentindex/crawlers/ai_tool_seeds.py` | 486 |
| chrome | All seeded entities set `is_king = true` | `agentindex/crawlers/chrome_seeds.py` | 1672 |
| saas | All seeded entities set `is_king = true` | `agentindex/crawlers/saas_seeds.py` | 1100 |
| city | Tourist cities (~200) set `is_king = True` | `agentindex/crawlers/city_seeds.py` | 60, 1637-1640 |
| country | All 158 countries set `is_king = True` | `agentindex/crawlers/city_seeds.py` | (via same seed) |
| ingredient/supplement/cosmetic | Per-entity flag in seed tuples | `agentindex/crawlers/food_cosmetics_seeds.py` | 41, 371, 417, 519 |
| android (extended) | Top 1000 entries get `is_king = True` | `agentindex/crawlers/android_seeds_extended.py` | 38 |

**Summary:** There is no centralized "king gate" function. King status is a boolean column in `software_registry` set at data ingestion time per registry rules. Once set, it is not re-evaluated except by the crawler re-running.

## Hypothesis verification status

**Critical note added 2026-04-10 after initial audit:**

The Kings architecture was built on the hypothesis that King pages receive more AI citations than non-King pages. This hypothesis has never been measured in the Nerq codebase.

Evidence:

1. flywheel_dashboard.py (lines 350-365, 955-991) contains a Kings section but the queries count Kings by quantity only: total, enriched by timestamp, indexable, percentage of indexable pool. There is no query that joins Kings against the requests table to measure AI bot crawl rates or AI-attributed human visits per Kings vs non-Kings page.

2. The dashboard's own text reads: "Kings = high-yield entities enriched with priority. Yield measurement available after 3-5 days of AI re-crawling." This is an aspirational note, not a recorded measurement. No follow-up query or panel was ever built to fulfil it.

3. agentindex/intelligence/citation_tracker.py (192 lines) contains zero references to is_king, kings, or any Kings-related filtering. Citation tracking and Kings status are completely separate code paths.

4. No document in docs/ claims a measured correlation. The hypothesis was recorded in strategy documents as if verified but was in fact an untested assumption.

**Implication for future work:** ADR-003 Addendum #4 restructures the Leverage Sprint A3 track to measure this hypothesis before scaling. A3-Measure builds the correlation panel that should have existed from the start. A3-Scale executes only if A3-Measure confirms the hypothesis. The 500K Kings target is retained as the ambition but gated on measurement per Addendum #4.

**See:** docs/adr/ADR-003-addendum-4-leverage-sprint-pivot.md for the full decision framework.

## Required components

### JSON-LD blocks

King pages receive one **additional** JSON-LD block beyond what non-King pages get. Non-King pages already include WebPage, FAQPage, BreadcrumbList, and SoftwareApplication JSON-LD.

**King-specific addition — ItemList for Trust Score Breakdown:**
- File: `agent_safety_pages.py`, lines 8984-8995
- Schema type: `@type: "ItemList"`
- Content: Lists all 5 trust dimensions (Security, Privacy, Reliability, Transparency, Maintenance) with their scores
- Only rendered when `_is_king` is true (line 8995: `if _is_king else ""`)

**Standard JSON-LD (all pages, not King-specific):**
- `WebPage` + `SpeakableSpecification` — line 7983-7988
- `FAQPage` — line 9003 (`{{ faq_jsonld }}`)
- `BreadcrumbList` — line 9004 (`{{ breadcrumb_jsonld }}`)
- `SoftwareApplication` (or MobileApplication, etc.) with `AggregateRating` + `Review` — lines 9005-9032

### FAQ requirements

FAQs are **not King-specific** — ALL entity pages get 5 FAQ questions. Kings do not get additional FAQs.

- File: `agent_safety_pages.py`, lines 7853-7891
- Always 5 questions (Q1: "Is X safe?", Q2: "What is trust score?", Q3: alternatives, Q4: registry-specific, Q5: registry-specific)
- FAQs are localized via `_t()` for all 23 languages
- Template: `agentindex/templates/agent_safety_page.html`, line 155 (`{{ faq_section_html }}`)

### nerq:answer requirements

The `nerq:answer` meta tag is present on **ALL** entity pages, not King-specific.

- File: `agent_safety_pages.py`, lines 7628-7634
- Template: `agentindex/templates/agent_safety_page.html`, line 29 (`<meta name="nerq:answer" content="{{ nerq_answer }}">`)
- Content: `"{verdict_prefix} {display_name} is a {entity_word} with a Nerq Trust Score of {score}/100 ({grade}). {verified_status}."`
- No explicit length constraint in code, but the format produces ~100-150 chars

### Minimum content length

There is **no explicit minimum content length check** for King status. Kings are identified by the `is_king` boolean at crawl time, not by content completeness.

However, King pages generate significantly more content than non-King pages because the `king_sections` block (lines 8325-8479) adds 5 extra sections:

1. **Detailed Score Analysis** — 5-dimension breakdown table (lines 8346-8366)
2. **Privacy Analysis** — registry-specific privacy deep dive (lines 8368-8419)
3. **Security Assessment** — registry-specific security analysis (lines 8421-8455)
4. **Cross-product trust map** — same entity across registries (lines 8457-8467)
5. **Methodology** — scoring methodology with dimension weights (lines 8469-8479)

Additionally, `_get_deep_analysis()` (line 8996) can inject further sections from `deep_analysis.py` for top entities.

### Sacred elements

These are present on **ALL** entity pages, not King-specific:

- **pplx-verdict** — `agent_safety_page.html`, line 74. CSS class: `pplx-verdict`. Always rendered.
- **ai-summary** — `agent_safety_page.html`, line 92. CSS class: `ai-summary`. Always rendered.
- **SpeakableSpecification** — `agent_safety_pages.py`, line 7988. CSS selectors: `.pplx-verdict`, `.ai-summary`, `.verdict`. Inside `WebPage` JSON-LD. Always rendered.

King status does **not** gate these elements. They exist on every `/safe/` page regardless of `is_king`.

## Current count

**Query run:** 2026-04-10

```sql
SELECT COUNT(*) FROM software_registry WHERE is_king = true;
```

**Result: 37,688 Kings**

### Breakdown by registry

| Registry | King count |
|----------|-----------|
| android | 13,050 |
| website | 10,879 |
| ios | 5,427 |
| saas | 2,806 |
| ai_tool | 787 |
| npm | 501 |
| steam | 500 |
| wordpress | 500 |
| charity | 493 |
| chrome | 472 |
| pypi | 300 |
| vscode | 200 |
| nuget | 200 |
| firefox | 200 |
| crypto | 196 |
| city | 185 |
| country | 158 |
| supplement | 137 |
| packagist | 100 |
| crates | 100 |
| go | 100 |
| gems | 100 |
| homebrew | 80 |
| vpn | 79 |
| cosmetic_ingredient | 73 |
| ingredient | 65 |

**Note on original audit:** The first version of this document truncated the registry table at 20 rows without disclosing the truncation. The full table has 26 rows covering all Kings-bearing registries. Sum of the 26 rows equals 37,688 which matches the total count.

### Enrichment depth

- Kings with `king_version > 0`: **7,246** (19% of all Kings)
- Kings with `dimensions` populated: **275** (0.7% — very few have full dimension data)

## Sample Kings (5)

| Entity | URL | Registry | Trust Score | Why King |
|--------|-----|----------|-------------|----------|
| ProtonVPN | nerq.ai/safe/protonvpn | vpn | 95 (A+) | VPN seed entity, curated |
| NordVPN | nerq.ai/safe/nordvpn | vpn | 90 (A+) | VPN seed entity, curated |
| webpack | nerq.ai/safe/webpack | npm | 89.8 (A) | Top npm package by popularity |
| @testing-library/react | nerq.ai/safe/testing-library-react | npm | 90.5 (A+) | High trust score npm package |
| IVPN | nerq.ai/safe/ivpn | vpn | 93 (A+) | VPN seed entity, curated |

## King candidates just below threshold (5)

These are entities with `is_king = false` but high trust scores (65-75) that could be promoted:

| Entity | URL | Registry | Trust Score | What's missing |
|--------|-----|----------|-------------|----------------|
| assemblyai | nerq.ai/safe/assemblyai | pypi | 75 (B+) | `is_king = false` — not in top pypi seed set |
| cashews | nerq.ai/safe/cashews | pypi | 75 (B+) | `is_king = false` — not in top pypi seed set |
| @nocobase/logger | nerq.ai/safe/nocobase-logger | npm | 75 (B+) | `is_king = false` — not in top npm seed set |
| @vue/cli-plugin-pwa | nerq.ai/safe/vue-cli-plugin-pwa | npm | 75 (B+) | `is_king = false` — not in top npm seed set |
| aiosonic | nerq.ai/safe/aiosonic | pypi | 75 (B+) | `is_king = false` — not in top pypi seed set |

Note: "Candidates" is a misnomer here. These entities are not candidates being evaluated — they simply have `is_king = false` because their registry's crawler didn't flag them. There is no automatic promotion mechanism.

## Degraded Kings

### By the numbers

- Kings with no description or description < 10 chars: **225**
- Kings with trust_score < 30: **28**
- Kings with NULL trust_score: **0**

### Degradation detection tooling

**No dedicated tooling exists** for detecting degraded Kings.

- `stale_score_detector` (`agentindex/stale_score_detector.py`) exists but is **currently broken** (OPERATIONSPLAN.md documents it as "schema drift, needs LEFT JOIN agents for trust_calculated_at"). It also checks freshness, not content degradation.
- `king_refresh.sh` (`scripts/king_refresh.sh`) runs weekly (Sunday 04:00 via `com.nerq.king-refresh` LaunchAgent) but only bumps `enriched_at` timestamps and flushes Redis cache — it does NOT check for missing content, broken JSON-LD, or other degradation.
- There is no tool that validates King pages have all 5 king_sections, valid JSON-LD, or minimum content length.

## Open questions

1. **Is there a correlation analysis** between `is_king = true` and Claude/GPT citation rates? The hypothesis is stated in the task description but no code was found that measures this. Is the correlation documented anywhere?

2. **Why are 30,442 Kings (81%) still at `king_version = 0`?** Only 7,246 have `king_version > 0`. What process bumps `king_version` and what does it represent?

3. **Should there be a centralized King gate function?** Currently each crawler decides independently. A centralized `promote_to_king(entity, registry)` function with explicit rules would make the system auditable.

4. **The 225 Kings with no/short description** — should they lose King status? They get the extra king_sections template but with empty/degraded content, which could hurt citation quality.

5. **Country Kings all have score 48.2** — is this a scoring bug? All 158 countries show identical trust scores, which makes the 5-dimension breakdown table meaningless.

6. **`dimensions` column is only populated for 275 of 37,688 Kings** — the "Detailed Score Analysis" section (king_sections #1) falls back to estimated scores for 99.3% of Kings. Is this expected?

7. **What is the relationship between `is_king` and `deep_analysis.py`?** The `_get_deep_analysis()` function is called for ALL entity pages (line 8996), not just Kings. Does it produce output only for Kings, or is it independent?

8. **VPN, password_manager, antivirus, hosting, website_builder, crypto registries** — these are in PINNED_REGISTRIES but have 0 Kings listed in the breakdown. Are their Kings stored under different registry names, or do these verticals not use the King system?

## Appendix: grep results

### Core King rendering (agent_safety_pages.py)
```
8325:    # ── King-specific sections (only for is_king=true entities) ──
8326:    king_sections = ""
8327:    _is_king = agent.get("is_king", False)
8328:    if _is_king:
8346:        # 1. Detailed Score Analysis (5 dimensions from DB)
8368:        # 2. Privacy Analysis
8415:        king_sections += ... (privacy section)
8421:        # 3. Security Assessment
8451:        king_sections += ... (security section)
8457:        # 4. Cross-product trust map
8463:        king_sections += ... (cross-product)
8469:        # 5. Methodology
8473:        king_sections += ... (methodology)
8983:        "{{ king_sections }}": king_sections,
8984-8995:  "{{ king_jsonld_block }}": ItemList JSON-LD (if _is_king)
```

### Template placement (agent_safety_page.html)
```
29:  <meta name="nerq:answer" content="{{ nerq_answer }}">  (all pages)
39:  {{ king_jsonld_block }}  (King only)
74:  <p class="pplx-verdict">...</p>  (all pages)
92:  <p class="ai-summary">...</p>  (all pages)
153: {{ king_sections }}  (King only)
```

### King-setting crawlers
```
android_play_crawler.py:129    is_king = installs > 10_000_000 or king_count < 5000
wordpress_king_enricher.py:173 is_king = global_rank <= 500
ai_tool_seeds.py:486           is_king = true (all seeded)
chrome_seeds.py:1672           is_king = true (all seeded)
saas_seeds.py:1100             is_king = true (all seeded)
city_seeds.py:60               Tourist cities: is_king=True
food_cosmetics_seeds.py:41     Per-item flag in seed data
android_seeds_extended.py:38   Top 1000: is_king=True
```

### Weekly refresh
```
scripts/king_refresh.sh        Bumps enriched_at for all Kings (Sunday 04:00)
                               Does NOT validate content completeness
```
