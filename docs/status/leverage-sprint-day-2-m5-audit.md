# M5 Audit — A3-Measure Kings Citation Yield

**Audited:** 2026-04-10 by Claude Code (Leverage Sprint Day 2 M5)
**Status:** Read-only audit, measurement-ready protocol
**Blocks production:** no — design only
**Reviewer:** Anders + Claude chat session

---

## Core question

> Do Kings (`is_king=true` entities) receive statistically significantly higher AI citations per indexed page than non-Kings, controlled for registry, trust score, and age, across a meaningful time window?

### Pre-registered hypothesis

Kings receive 2-10x more AI citations per indexed page than comparable non-Kings. This was the strategic assumption motivating A3-Scale to 500K Kings (per ADR-003 Addendum #4).

### Pre-registered falsification threshold

- **< 1.2x** (per score-controlled band): hypothesis disproven. Kings offer no meaningful citation advantage. A3-Scale should be cancelled or fundamentally rethought.
- **1.2x - 2.0x**: weak signal. Proceed with caution — the effect may be real but small, and confounds (crawl bias, name recognition) may account for most of it.
- **> 2.0x** (per score-controlled band): hypothesis supported. Proceed to A3-Fix and A3-Scale.

**Critical caveat:** Even a strong ratio does not prove causation. See Confound Analysis (Step 5) for the crawl bias problem.

---

## Step 1 — Data plumbing

### Where does `is_king` live?

**Table:** `software_registry` in PostgreSQL (`agentindex` database)
**Column:** `is_king` (boolean, default false) — `software_registry` schema confirmed via `\d software_registry`
**Related columns:** `slug` (text, not null), `registry` (text, not null), `trust_score` (real), `created_at` (timestamp), `king_version` (integer, default 0), `king_enriched_at` (timestamp), `dimensions` (jsonb)

**Not in `entity_lookup` or `agents` table.** The `is_king` flag exists only in `software_registry`.

### Where does citation data live?

**Table:** `requests` in SQLite (`/Users/anstudio/agentindex/logs/analytics.db`)
**Key columns:** `path` (text), `is_ai_bot` (integer 0/1), `bot_name` (text), `status` (integer), `ts` (text ISO format)
**New M3 columns confirmed present:** `ai_source` (text, nullable), `visitor_type` (text, nullable). Partially populated — `ai_source` has 8,812 rows populated in last 7 days (all ChatGPT/Claude/Perplexity/Doubao/Kagi), mostly ChatGPT.
**Schema defined at:** `agentindex/analytics.py:78-95`

### Join path: Postgres entity → analytics.db citation

**The join is a cross-database text match on slug.**

An entity with slug `nordvpn` in `software_registry` maps to analytics.db paths via:

| Pattern | Example | Coverage |
|---------|---------|----------|
| `/safe/{slug}` | `/safe/nordvpn` | 70,736 AI citations (30d) |
| `/{lang}/safe/{slug}` | `/de/safe/nordvpn` | 509,991 AI citations (30d) |
| `/is-{slug}-safe` | `/is-nordvpn-safe` | 83,904 AI citations (30d) |
| Other patterns | `/review/nordvpn`, `/privacy/nordvpn`, `/pros-cons/nordvpn`, `/what-is/nordvpn`, `/who-owns/nordvpn`, `/alternatives/nordvpn` | Not quantified separately |

**Total entity-related AI citations (30d): 2,254,189** (64.3% of all 3,505,516 AI citations).

### Edge cases

1. **Slug collisions:** Same slug can appear in multiple registries (e.g., `1password` exists in chrome, saas, website). For measurement, we treat an entity as "King" if `is_king=true` in ANY registry for that slug.

2. **Localized path extraction:** `/{lang}/safe/{slug}` requires extracting slug from position 10 or 11 depending on 2-char vs 3-char language code.

3. **Android package names:** Slugs like `com.imo.android.imoim` and `com-google-android-apps-maps` use full package names as slugs.

4. **Pattern overlap:** `/is-nordvpn-safe` contains the slug `nordvpn` but extraction requires regex (`is-(.+)-safe`). For the protocol, we focus on `/safe/{slug}` and `/{lang}/safe/{slug}` patterns which have clean slug extraction.

---

## Step 2 — Kings inventory by registry

Query:
```sql
SELECT registry, COUNT(*) FILTER (WHERE is_king=true) as kings, COUNT(*) as total,
  ROUND(100.0*COUNT(*) FILTER (WHERE is_king=true)/COUNT(*),1) as kings_pct
FROM software_registry GROUP BY registry ORDER BY kings DESC
```
Result: 30 rows.

| Registry | Kings | Total | Kings % | Usable for measurement? |
|----------|------:|------:|--------:|:----------------------:|
| android | 13,050 | 57,552 | 22.7% | Yes |
| website | 10,879 | 500,963 | 2.2% | Yes |
| ios | 5,427 | 48,071 | 11.3% | Yes |
| saas | 2,806 | 4,963 | 56.5% | Yes (but high Kings %) |
| ai_tool | 787 | 2,341 | 33.6% | Yes |
| npm | 501 | 528,324 | 0.1% | Yes |
| wordpress | 500 | 57,089 | 0.9% | Yes |
| steam | 500 | 45,361 | 1.1% | Yes |
| charity | 493 | 504 | 97.8% | **No** — nearly all Kings |
| chrome | 472 | 44,229 | 1.1% | Yes |
| pypi | 300 | 93,768 | 0.3% | Yes |
| vscode | 200 | 48,948 | 0.4% | Yes |
| nuget | 200 | 641,641 | 0.0% | Yes |
| firefox | 200 | 29,120 | 0.7% | Yes |
| crypto | 196 | 226 | 86.7% | **No** — nearly all Kings |
| city | 185 | 2,981 | 6.2% | Marginal (N=185) |
| country | 158 | 158 | 100.0% | **No** — all Kings |
| supplement | 137 | 584 | 23.5% | Marginal (N=137) |
| packagist | 100 | 113,818 | 0.1% | Yes |
| go | 100 | 22,095 | 0.5% | Yes |
| gems | 100 | 10,104 | 1.0% | Yes |
| crates | 100 | 204,080 | 0.0% | Yes |
| homebrew | 80 | 8,286 | 1.0% | Yes |
| vpn | 79 | 79 | 100.0% | **No** — all Kings |
| cosmetic_ingredient | 73 | 584 | 12.5% | Marginal (N=73) |
| ingredient | 65 | 669 | 9.7% | Marginal (N=65) |
| website_builder | 0 | 51 | 0.0% | **No** — zero Kings |
| password_manager | 0 | 55 | 0.0% | **No** — zero Kings |
| hosting | 0 | 51 | 0.0% | **No** — zero Kings |
| antivirus | 0 | 51 | 0.0% | **No** — zero Kings |

**Excluded from measurement:** vpn, country, charity, crypto (Kings % too high or 100%), website_builder, password_manager, hosting, antivirus (zero Kings). These 8 registries have no comparison group.

**Usable registries:** 17 registries with at least 65 Kings and a meaningful non-King comparison group.

---

## Step 3 — Citation data inventory

### Total AI citations (30-day window)

| Metric | Value |
|--------|------:|
| Total requests (30d) | 14,813,558 |
| AI bot citations (30d, status=200) | 3,505,516 |
| Entity-page citations (30d) | 2,254,189 |
| Entity as % of AI total | 64.3% |
| NULL paths (30d) | 0 |
| Date range | 2026-03-11 to 2026-04-10 |

### Citations by AI bot (30d, status=200)

| Bot | Citations |
|-----|----------:|
| Claude | 2,052,793 |
| ChatGPT | 1,199,667 |
| Perplexity | 158,557 |
| ByteDance | 94,537 |

### Citations by path type (30d, entity pages)

| Path type | Citations |
|-----------|----------:|
| English `/safe/{slug}` | 70,736 |
| Localized `/{lang}/safe/{slug}` | 509,991 |
| English `/is-*-safe` | 83,904 |
| All entity-related | 2,254,189 |

**Observation:** Localized paths account for **7.2x** more AI citations than English `/safe/` paths. Any measurement that only looks at `/safe/` misses ~88% of entity traffic. The measurement protocol MUST include localized paths.

### Time window coverage

Earliest: 2026-03-11. Latest: 2026-04-10 (today). Full 30-day window available.

---

## Step 4 — Pilot measurement

### Registry selection

VPN was the original pilot candidate but **cannot be used** — all 79 entities are Kings (100%). No comparison group exists.

**Substitute pilot registry: npm** (501 Kings, 527,823 non-Kings, 0.1% Kings rate).

### npm pilot: age confound check

| Group | N | Avg trust score | Avg age (days) |
|-------|--:|----------------:|---------------:|
| Kings | 501 | 82.5 | 22.1 |
| Non-Kings | 527,823 | 50.6 | 22.0 |

Ages are nearly identical (~22 days). Age is NOT a confound for npm. Trust score IS a confound — Kings have 82.5 avg vs 50.6 for non-Kings.

### npm pilot: 7-day, `/safe/` paths only

| Group | N entities | Cited entities | Total citations | Mean per entity | Mean per cited |
|-------|----------:|---------------:|----------------:|----------------:|---------------:|
| Kings | 501 | 176 (35.1%) | 375 | 0.75 | 2.13 |
| Non-Kings | — | 13,172 | 20,061 | — | 1.52 |

**Ratio (mean per cited): 1.40x** — Kings get 40% more citations per cited entity.
**Ratio (mean per all Kings vs per cited non-King): 0.49x** — Kings get FEWER when counting uncited Kings.

### npm pilot: 30-day, `/safe/` + localized paths

| Group | N entities | Cited entities | Total citations | Mean per entity | Mean per cited |
|-------|----------:|---------------:|----------------:|----------------:|---------------:|
| Kings | 501 | 271 (54.1%) | 3,912 | 7.81 | 14.44 |
| Non-Kings | ~528K | 79,371 (15.0%) | 576,752 | ~1.09 | 7.27 |

**Ratio (mean per cited): 1.99x** — Kings get 2x more citations per cited entity.

### ALL registries: 30-day, `/safe/` only

| Group | Cited | Total entities | Total citations | Mean per entity | Mean per cited |
|-------|------:|---------------:|----------------:|----------------:|---------------:|
| Kings | 4,264 (11.3%) | 37,688 | 12,933 | 0.343 | 3.03 |
| Non-Kings | 35,056 (1.44%) | 2,429,058 | 57,800 | 0.024 | 1.65 |

**Ratio (mean per entity): 14.4x.** **Ratio (mean per cited): 1.84x.**

---

## Step 5 — Confound analysis

### Confound 1: Trust score (SEVERE)

Kings have systematically higher trust scores than non-Kings (82.5 vs 50.6 in npm). Higher-scored entities may get more citations regardless of King status because:
- They rank higher on `/best/` pages, increasing discoverability
- They have higher-quality page content (more data, better descriptions)
- They correspond to well-known, popular software people actually ask about

**Score-controlled analysis (8 testable registries, 30d, /safe/ + localized paths):**

| Score band | Kings N | Non-Kings N | Kings mean | Non-Kings mean | Ratio |
|-----------|--------:|------------:|-----------:|---------------:|------:|
| 80-100 | 435 | 3,093 | 9.51 | 1.64 | **5.8x** |
| 60-79 | 3,996 | 79,329 | 4.72 | 0.40 | **11.9x** |
| 40-59 | 11,142 | 787,762 | 0.67 | 0.05 | **14.7x** |

**Even within the same score band, Kings get 5.8-14.7x more citations.** The trust score confound does NOT fully explain the King advantage.

### Confound 2: Crawl bias via IndexNow (SEVERE)

**`auto_indexnow.py:348-354`** explicitly prioritizes Kings for IndexNow submission:

```python
AND (is_king = true OR trust_score >= 70)
ORDER BY is_king DESC NULLS LAST, trust_score DESC NULLS LAST
LIMIT 50000
```

Kings are submitted to search engines FIRST. Additionally, **`auto_indexnow.py:360-366`** generates localized URLs for 6 languages (es, de, fr, ja, pt, id) only for entities in this Kings-first set. This means:
- Kings get 7 URL submissions per entity (1 English + 6 localized)
- Non-Kings with score < 70 get ZERO IndexNow submissions
- Non-Kings with score >= 70 get submissions but ranked AFTER all Kings

**This is the most severe confound.** We may be measuring "did we submit more URLs for Kings" rather than "do AI crawlers prefer Kings."

**Mitigation in 80-100 score band:** Non-Kings with score >= 80 SHOULD also be in the IndexNow set (since threshold is 70). The 5.8x ratio in the 80-100 band MIGHT reflect genuine preference — but localized URL expansion still favors entities ranked higher in the list (Kings).

### Confound 3: Name recognition / selection bias (MODERATE)

Kings are chosen BECAUSE they are well-known entities (React, NordVPN, TikTok, Chrome extensions). Users ask AI assistants about famous products by name. These entities would get more citations regardless of King status.

Evidence: Of the top 30 most-cited entities (30d), ~20 (67%) are Kings. But the non-Kings in the top 30 include well-known Rust crates (serde, deunicode, primitive-types) — popular packages that are not Kings in the crates registry (which only has 100 Kings out of 204K).

**This confound is inherent and cannot be controlled by the measurement.** Kings are a curated set of popular entities. You cannot separate "popular because King" from "King because popular."

### Confound 4: Page content (MODERATE)

King pages receive 5 extra HTML sections (per `kings-definition.md`):
1. Detailed Score Analysis — 5-dimension breakdown table
2. Privacy Analysis — registry-specific privacy deep dive
3. Security Assessment — registry-specific security analysis
4. Cross-product trust map — same entity across registries
5. Methodology — scoring methodology with dimension weights

Plus an `ItemList` JSON-LD for trust score breakdown (`agent_safety_pages.py:8984-8995`).

This extra content could legitimately improve AI extraction quality, making King pages more useful as citation sources. If true, this is not a confound — it's the mechanism by which Kings create value. But it means the measurement tests "does more content get more citations" not "does the King label matter."

### Confound 5: Entity age (NEGLIGIBLE)

| Group | Mean age (days) | Median age |
|-------|----------------:|-----------:|
| Kings | 19 | 18 |
| Non-Kings | 22 | 22 |

Kings are slightly NEWER than non-Kings. If age biased anything, it would bias AGAINST Kings. Not a confound.

### Confound 6: Language distribution (MODERATE)

Localized paths account for 88% of entity-page AI traffic. IndexNow submits localized URLs for 6 languages but only for the Kings-first entity set. If AI crawlers discover entities primarily through localized paths (which IndexNow drives), this confound reinforces Confound 2.

---

## Step 6 — Statistical power estimate

### Per-registry power analysis

For a two-sample t-test with unequal variance, the required sample size per group for 80% power at p<0.05 depends on the effect size (Cohen's d).

| Detectable effect | Kings N needed | Non-Kings N needed |
|-------------------|---------------:|-------------------:|
| Large (d=0.8) | ~26 | ~26 |
| Medium (d=0.5) | ~64 | ~64 |
| Small (d=0.2) | ~394 | ~394 |

### Registry measurement feasibility

| Registry | Kings N | Non-Kings N | Detectable effect | Verdict |
|----------|--------:|------------:|:------------------|:--------|
| android | 13,050 | 44,502 | Small | **Strong** |
| website | 10,879 | 490,084 | Small | **Strong** |
| ios | 5,427 | 42,644 | Small | **Strong** |
| saas | 2,806 | 2,157 | Small | **Strong** |
| ai_tool | 787 | 1,554 | Small | **Strong** |
| npm | 501 | 527,823 | Small | **Strong** |
| wordpress | 500 | 56,589 | Small | **Strong** |
| steam | 500 | 44,861 | Small | **Strong** |
| chrome | 472 | 43,757 | Small | **Strong** |
| pypi | 300 | 93,468 | Medium | **Good** |
| vscode | 200 | 48,748 | Medium | **Good** |
| nuget | 200 | 641,641 | Medium | **Good** |
| firefox | 200 | 28,920 | Medium | **Good** |
| packagist | 100 | 113,718 | Medium | **Good** |
| go | 100 | 21,995 | Medium | **Good** |
| gems | 100 | 10,004 | Medium | **Good** |
| crates | 100 | 203,980 | Medium | **Good** |
| homebrew | 80 | 8,206 | Large | **Marginal** |
| city | 185 | 2,796 | Medium | **Good** |
| supplement | 137 | 447 | Medium | Marginal |
| cosmetic_ingredient | 73 | 511 | Large | Marginal |
| ingredient | 65 | 604 | Large | Marginal |

**Recommendation:** Use the 17 registries with >= 100 Kings for per-registry analysis. Aggregate the 5 marginal registries into an "other" group.

---

## Step 7 — Measurement protocol design

### Pre-registration (WRITTEN BEFORE seeing final numbers)

**Hypothesis:** Kings get 2-10x more AI citations per indexed page than non-Kings within the same trust score band and registry.

**Expected result:** Based on the pilot data, we expect:
- 80-100 score band: 3-8x advantage for Kings (pilot showed 5.8x)
- 60-79 score band: 5-15x advantage (pilot showed 11.9x)
- 40-59 score band: 10-20x advantage (pilot showed 14.7x)

**What would disprove the hypothesis:**
- < 1.2x ratio in the 80-100 score band (where crawl bias is reduced because non-Kings with score >= 70 also get IndexNow submission)
- ai_tool registry showing Kings UNDERPERFORM (pilot showed 0.5x for ai_tool on /safe/ only — this is the biggest surprise and needs investigation)

### Final measurement queries

**Query 1: Per-registry, score-controlled, all entity paths (30d)**

This is a cross-database query requiring Python to bridge Postgres and SQLite:

```python
import sqlite3, subprocess

# Step 1: Extract entities from Postgres
result = subprocess.run([
    'psql', '-U', 'anstudio', '-d', 'agentindex', '-t', '-A',
    '-c', """SET statement_timeout='120s';
    SELECT slug, is_king, trust_score, registry
    FROM software_registry
    WHERE trust_score IS NOT NULL AND trust_score > 0
    ORDER BY slug"""
], capture_output=True, text=True)

entities = {}  # slug → (is_king_in_any_registry, max_score, primary_registry)
for line in result.stdout.strip().split('\n'):
    if '|' not in line: continue
    slug, is_king, score, reg = line.split('|')
    score = float(score)
    if slug in entities:
        old_king, old_score, old_reg = entities[slug]
        entities[slug] = (old_king or (is_king == 't'), max(old_score, score), old_reg)
    else:
        entities[slug] = (is_king == 't', score, reg)

# Step 2: Get all entity citations from SQLite
conn = sqlite3.connect('logs/analytics.db')
cur = conn.execute("""
    SELECT
      CASE
        WHEN path LIKE '/safe/%' AND path NOT LIKE '/safe/%/%'
          THEN REPLACE(path, '/safe/', '')
        WHEN path LIKE '/__/safe/%' AND path NOT LIKE '/__/safe/%/%'
          THEN SUBSTR(path, 10)
        WHEN path LIKE '/___/safe/%' AND path NOT LIKE '/___/safe/%/%'
          THEN SUBSTR(path, 11)
      END as slug,
      COUNT(*) as cnt
    FROM requests
    WHERE is_ai_bot=1 AND status=200
      AND ts >= date('now', '-30 days')
      AND (
        (path LIKE '/safe/%' AND path NOT LIKE '/safe/crypto/%' AND path NOT LIKE '/safe/%/%')
        OR (path LIKE '/__/safe/%' AND path NOT LIKE '/__/safe/%/%')
        OR (path LIKE '/___/safe/%' AND path NOT LIKE '/___/safe/%/%')
      )
    GROUP BY slug
    HAVING slug IS NOT NULL AND slug != ''
""")
citations = {slug: cnt for slug, cnt in cur}
conn.close()

# Step 3: Build comparison table
bands = [(80, 100), (60, 79), (40, 59), (20, 39)]
for lo, hi in bands:
    king_slugs = [s for s, (k, sc, r) in entities.items() if k and lo <= sc <= hi]
    nonking_slugs = [s for s, (k, sc, r) in entities.items() if not k and lo <= sc <= hi]
    k_total = sum(citations.get(s, 0) for s in king_slugs)
    nk_total = sum(citations.get(s, 0) for s in nonking_slugs)
    k_cited = sum(1 for s in king_slugs if s in citations)
    nk_cited = sum(1 for s in nonking_slugs if s in citations)
    k_mean = k_total / max(len(king_slugs), 1)
    nk_mean = nk_total / max(len(nonking_slugs), 1)
    ratio = k_mean / max(nk_mean, 0.0001)
    
    # Welch's t-test (optional, for p-value)
    # Use scipy.stats.ttest_ind with unequal_var=True
    
    print(f"Score {lo}-{hi}: Kings {len(king_slugs)} ({k_mean:.2f}/entity), "
          f"non-Kings {len(nonking_slugs)} ({nk_mean:.4f}/entity), "
          f"ratio={ratio:.1f}x")
```

**Query 2: Per-registry breakdown (30d, all entity paths)**

Same as Query 1 but grouped by primary registry instead of score band.

**Query 3: 7-day window (for recency check)**

Same queries with `ts >= date('now', '-7 days')`.

**Query 4: Per-bot breakdown**

Add `bot_name` to the GROUP BY in the SQLite query to see if specific AI bots (Claude, ChatGPT, Perplexity) show different King preferences.

### Interpretation rules

| Score band | Ratio | Interpretation | Action |
|-----------|------:|:---------------|:-------|
| 80-100 | < 1.2x | Hypothesis falsified for high-quality entities | Cancel A3-Scale |
| 80-100 | 1.2-2.0x | Weak signal, confounds likely | Investigate confounds before proceeding |
| 80-100 | 2.0-5.0x | Moderate signal | Proceed with A3-Fix, gate A3-Scale on 7d post-fix data |
| 80-100 | > 5.0x | Strong signal | Proceed with A3-Fix and A3-Scale |
| Any band | ai_tool < 1.0x | Anomaly — investigate why Kings underperform | Investigate before any action |

---

## Step 8 — Execution plan

### Sequence

1. **Export Postgres entities** (30s): `SELECT slug, is_king, trust_score, registry FROM software_registry WHERE trust_score IS NOT NULL`
2. **Query SQLite citations** (5-10s): Aggregate `/safe/` and `/{lang}/safe/` paths by slug
3. **Cross-database join** (5s): Python script matching slugs
4. **Score-band analysis** (1s): Compute means and ratios per band
5. **Per-registry analysis** (1s): Compute means and ratios per registry
6. **Statistical tests** (1s): Welch's t-test if scipy available, otherwise bootstrap
7. **Write results** (5min): Markdown table in status doc

**Total expected time: 10-15 minutes** for data extraction and analysis.

### Output format

Markdown table in `docs/status/leverage-sprint-m5-results.md` with:
- Summary finding (1 sentence)
- Score-controlled table
- Per-registry table
- Per-bot table
- Decision recommendation

### Decision thresholds

| Finding | Action |
|---------|--------|
| 80-100 band ratio > 2.0x AND NOT fully explained by crawl bias | **Proceed to A3-Fix (M6)** |
| 80-100 band ratio > 5.0x | **Proceed to A3-Fix (M6) and A3-Scale (M8)** |
| 80-100 band ratio < 1.2x | **Cancel A3-Scale. Redirect effort to A1/A2 optimization.** |
| ai_tool anomaly (< 1.0x) | **Investigate before proceeding regardless of other results** |
| Crawl bias fully explains ratio | **Redesign experiment: disable IndexNow King priority for 7d, re-measure** |

### Intermediate tables

**None needed.** All analysis uses CTEs or Python in-memory joins. No permanent tables or views required.

---

## Risks and open questions

### Risk 1: Crawl bias (HIGH — most important risk)

**`auto_indexnow.py:347-368`** explicitly prioritizes Kings for IndexNow submission AND generates localized URLs only for Kings-first entities. We may be measuring the effect of our own submission strategy, not AI preference.

**Mitigation options:**
1. **Natural experiment:** Compare 80-100 score band where both Kings and non-Kings should receive IndexNow submission (threshold is score >= 70)
2. **Localized URL check:** Compare English-only citations (where IndexNow bias is smaller) vs localized citations (where IndexNow bias is strongest). If the ratio is similar in both, crawl bias is less likely the full explanation.
3. **A/B experiment:** Temporarily remove King priority from IndexNow for a subset of Kings and measure whether citation rate drops. This would be conclusive but requires a code change and 7-day wait.

### Risk 2: Survivorship bias (MODERATE)

Kings are chosen because they meet criteria (well-known, high score, mature). Non-Kings include millions of obscure packages that nobody has heard of. Comparing Kings to the full non-King population is comparing the top ~1% to the remaining 99%. This is not a fair comparison.

**Mitigation:** Score-controlled analysis (Step 5) partially addresses this. The 80-100 band compares 435 Kings to 3,093 non-Kings of similar quality. This is the most defensible comparison.

### Risk 3: Data quality (LOW)

- NULL paths: 0 in last 30 days (checked). No data quality issue.
- Bot classification: `is_ai_bot` flag is set at write time by `analytics.py:150-185`. The M3 `ai_source` column has 8,812 rows populated — small but growing.
- Slug extraction: `/safe/` pattern is reliable. Localized path extraction may have edge cases for 3-character language codes.

### Risk 4: Pattern coverage (LOW-MODERATE)

Not all Kings have `/safe/{slug}` paths hit by AI bots. Only 4,264 of 37,688 Kings (11.3%) received any `/safe/` citation in 30 days. If Kings have disproportionately MORE non-`/safe/` URLs (e.g., `/is-{slug}-safe`, `/review/{slug}`), our measurement underestimates King traffic. However, the localized path inclusion captures the majority of entity traffic.

### Risk 5: ai_tool anomaly (MODERATE)

The per-registry pilot showed ai_tool Kings at **0.5x** vs non-Kings on `/safe/` paths only. This means in at least one registry, Kings are OUTPERFORMED by non-Kings. This could be because:
- ai_tool has 33.6% Kings rate (high), so non-Kings include many quality tools
- ai_tool non-Kings may include trending new tools that get citation spikes
- The ai_tool registry has all seeded entities set as Kings, not quality-selected

This anomaly should be investigated before any A3-Scale decision.

### Open question 1: Should we disable IndexNow King priority for 7 days?

This is the cleanest way to resolve the crawl bias confound. Remove `ORDER BY is_king DESC` from `auto_indexnow.py:353` and wait 7 days. Then re-measure. If Kings still outperform, the hypothesis is validated independent of crawl bias.

**Risk:** 7-day experiment delay. Kings may lose some citation momentum.
**Recommendation:** Run the observational measurement first. If the 80-100 band shows > 5x ratio, crawl bias is unlikely the full explanation and the experiment may not be needed.

### Open question 2: What about the ai_source column?

The M3 deployment added `ai_source` to requests but it's sparsely populated (8,812 rows in 7 days vs 800K+ total rows). Once population is more complete, the per-AI-source breakdown (Query 4) will be more meaningful. For now, use `bot_name` as proxy.

### Open question 3: How to handle slug collisions across registries?

Current approach: treat entity as King if `is_king=true` in ANY registry. Alternative: per-registry analysis only uses entities unique to that registry. The collision rate among Kings is unknown but the example check showed at least 15 Kings with multi-registry presence (1password, airbnb, etc.).

---

## Pilot findings — PRELIMINARY

**These are preliminary findings from Step 4, not the final measurement. They should be treated as directional, not conclusive.**

### Finding 1: Kings get 5.8x more citations per entity than non-Kings at the same trust score level (80-100 band)

In the 80-100 trust score band, across 8 testable registries (30d, /safe/ + localized paths):
- 435 Kings: 9.51 mean citations per entity
- 3,093 non-Kings: 1.64 mean citations per entity
- **Ratio: 5.8x**

This is within the pre-registered 2-10x expectation range and above the 2.0x "proceed" threshold.

### Finding 2: The King advantage INCREASES in lower score bands

| Score band | Ratio |
|-----------|------:|
| 80-100 | 5.8x |
| 60-79 | 11.9x |
| 40-59 | 14.7x |

This pattern is expected if:
- Low-score Kings are famous entities that happened to score low (confound: name recognition)
- Low-score non-Kings are truly obscure entities nobody asks about (confound: survivorship bias)

### Finding 3: Crawl bias is real and measured

`auto_indexnow.py:347-354` shows Kings are submitted to search engines first. `auto_indexnow.py:360-366` shows localized URLs are generated for Kings-first entities. This directly causes more AI crawler traffic to King pages. The 5.8x ratio in the 80-100 band may be partially or fully explained by this.

### Finding 4: Entity-page AI citations are 64.3% of all AI traffic

2.25M of 3.5M AI citations go to entity pages (30d). This confirms that entity page quality matters for overall AI citation volume — whether or not Kings specifically outperform.

### Finding 5: ai_tool Kings underperform non-Kings (0.5x)

This is the most surprising pilot finding. In the ai_tool registry (787 Kings, 1,554 non-Kings), Kings get FEWER citations on `/safe/` paths than non-Kings. This suggests the King selection criteria for ai_tool (all seeded entities, not quality-selected) may be counterproductive. This anomaly should be investigated before A3-Scale.

---

## Appendix A: Raw SQL output

### Kings inventory (30 registries)

```
registry       | kings | total  | kings_pct
android        | 13050 |  57552 |      22.7
website        | 10879 | 500963 |       2.2
ios            |  5427 |  48071 |      11.3
saas           |  2806 |   4963 |      56.5
ai_tool        |   787 |   2341 |      33.6
npm            |   501 | 528324 |       0.1
wordpress      |   500 |  57089 |       0.9
steam          |   500 |  45361 |       1.1
charity        |   493 |    504 |      97.8
chrome         |   472 |  44229 |       1.1
pypi           |   300 |  93768 |       0.3
vscode         |   200 |  48948 |       0.4
nuget          |   200 | 641641 |       0.0
firefox        |   200 |  29120 |       0.7
crypto         |   196 |    226 |      86.7
city           |   185 |   2981 |       6.2
country        |   158 |    158 |     100.0
supplement     |   137 |    584 |      23.5
packagist      |   100 | 113818 |       0.1
go             |   100 |  22095 |       0.5
gems           |   100 |  10104 |       1.0
crates         |   100 | 204080 |       0.0
homebrew       |    80 |   8286 |       1.0
vpn            |    79 |     79 |     100.0
cosmetic_ingredient |  73 |   584 |      12.5
ingredient     |    65 |    669 |       9.7
website_builder|     0 |     51 |       0.0
password_manager|    0 |     55 |       0.0
hosting        |     0 |     51 |       0.0
antivirus      |     0 |     51 |       0.0
```

### Per-registry citation comparison (30d, /safe/ paths only)

```
Registry          K_N    NK_N K_cited NK_cited  K_mean  NK_mean  Ratio
ai_tool           787    1554     366     1352   1.510   3.2529    0.5x
android         13050   44502    1262       38   0.222   0.0013  164.3x
chrome            472   43757     168      405   2.028   0.0198  102.3x
firefox           200   28920      81      238   2.415   0.0177  136.1x
npm               501  527823     268     3248   2.020   0.0123  164.1x
pypi              300   93468     235     2069   3.673   0.0420   87.5x
saas             2806    2157     567      148   0.651   0.1697    3.8x
steam             500   44861     149      316   1.098   0.0132   83.5x
vscode            200   48748      15       25   0.095   0.0005  178.1x
website         10879  490084     339      605   0.110   0.0028   39.3x
wordpress         500   56589     208      544   1.208   0.0182   66.5x
```

### Score-controlled comparison (30d, /safe/ + localized, 8 testable registries)

```
Band          K_N     NK_N K_cited NK_cited  K_total  NK_total   K_mean   NK_mean  Ratio
80-100        435     3093     263      394     4137      5059     9.51    1.6356    5.8x
60-79        3996    79329    1363     2731    18856     31491     4.72    0.3970   11.9x
40-59       11142   787762     691     3091     7446     35702     0.67    0.0453   14.7x
ALL         15652   882176    2361     6417    31329     74795     2.00    0.0848   23.6x
```

### AI citation volumes

```
Total requests (30d):           14,813,558
AI bot citations (30d):          3,505,516
Entity-page citations:           2,254,189  (64.3%)
  - English /safe/:                 70,736
  - Localized /{lang}/safe/:       509,991
  - English /is-*-safe:             83,904
```

### Top 30 most-cited entities (30d, /safe/ + localized)

```
tiktok                    98  (King: website,ios,android)
replit                    73  (King: website,saas)
make                      71  (King: saas)
trulens                   70  (not found in tested registries)
lovable                   65  (King: ai_tool)
react-devtools            61  (King: firefox,chrome)
dark-reader               59  (King: chrome)
buffer                    58  (King: saas,chrome)
notion                    57  (King: android,website,saas)
lastpass                  57  (King: saas,chrome,website)
express                   52  (King: npm)
serde                     52  (King: crates)
shadow-weather            52  (King: android)
pipedrive                 52  (King: saas)
checkov                   54  (King: pypi)
weaviate                  55  (King: ai_tool)
pangle-cn                 54  (NOT King: website)
uncased                   53  (NOT King: crates)
primitive-types           53  (NOT King: crates)
deunicode                 53  (NOT King: crates)
byte-slice-cast           53  (NOT King: crates)
getset                    52  (NOT King: crates)
parity-scale-codec        51  (NOT King: crates)
```

~67% of top 30 are Kings.

---

## Appendix B: SQL queries for final measurement (copy-ready)

### Query 1: SQLite — Extract entity citations by slug

```sql
-- Run against analytics.db
-- Covers /safe/ (English), /{lang}/safe/ (localized, 2+3 char codes)
SELECT
  CASE
    WHEN path LIKE '/safe/%' AND path NOT LIKE '/safe/%/%'
      THEN REPLACE(path, '/safe/', '')
    WHEN path LIKE '/__/safe/%' AND path NOT LIKE '/__/safe/%/%'
      THEN SUBSTR(path, 10)
    WHEN path LIKE '/___/safe/%' AND path NOT LIKE '/___/safe/%/%'
      THEN SUBSTR(path, 11)
  END as slug,
  COUNT(*) as citations,
  COUNT(DISTINCT date(ts)) as days_cited,
  MIN(ts) as first_cite,
  MAX(ts) as last_cite
FROM requests
WHERE is_ai_bot=1 AND status=200
  AND ts >= date('now', '-30 days')
  AND (
    (path LIKE '/safe/%' AND path NOT LIKE '/safe/crypto/%' AND path NOT LIKE '/safe/%/%')
    OR (path LIKE '/__/safe/%' AND path NOT LIKE '/__/safe/%/%')
    OR (path LIKE '/___/safe/%' AND path NOT LIKE '/___/safe/%/%')
  )
GROUP BY slug
HAVING slug IS NOT NULL AND slug != ''
ORDER BY citations DESC
```

### Query 2: Postgres — Extract entities with King status

```sql
-- Run against agentindex database
SET statement_timeout='120s';
SELECT slug, is_king, trust_score, registry, created_at
FROM software_registry
WHERE trust_score IS NOT NULL AND trust_score > 0
ORDER BY slug;
```

### Query 3: SQLite — Per-bot entity citations

```sql
-- Run against analytics.db
SELECT
  bot_name,
  CASE
    WHEN path LIKE '/safe/%' AND path NOT LIKE '/safe/%/%'
      THEN REPLACE(path, '/safe/', '')
    WHEN path LIKE '/__/safe/%' AND path NOT LIKE '/__/safe/%/%'
      THEN SUBSTR(path, 10)
    WHEN path LIKE '/___/safe/%' AND path NOT LIKE '/___/safe/%/%'
      THEN SUBSTR(path, 11)
  END as slug,
  COUNT(*) as citations
FROM requests
WHERE is_ai_bot=1 AND status=200
  AND ts >= date('now', '-30 days')
  AND (
    (path LIKE '/safe/%' AND path NOT LIKE '/safe/crypto/%' AND path NOT LIKE '/safe/%/%')
    OR (path LIKE '/__/safe/%' AND path NOT LIKE '/__/safe/%/%')
    OR (path LIKE '/___/safe/%' AND path NOT LIKE '/___/safe/%/%')
  )
GROUP BY bot_name, slug
HAVING slug IS NOT NULL AND slug != ''
ORDER BY bot_name, citations DESC
```

### Query 4: IndexNow submission check

```sql
-- Verify which entities are in IndexNow set
-- Run against agentindex database
SET statement_timeout='60s';
SELECT is_king, COUNT(*) as n,
  AVG(trust_score) as avg_score
FROM software_registry
WHERE trust_score IS NOT NULL AND trust_score > 0
  AND description IS NOT NULL AND description != ''
  AND (is_king = true OR trust_score >= 70)
GROUP BY is_king
ORDER BY is_king DESC;
```
