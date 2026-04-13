# OAI-SearchBot Spike Analysis — Mar 21, 2026

**Question:** What triggered OAI-SearchBot to index 2,120 pages on Mar 21, causing ChatGPT-User to jump from 647 to 1,198/day overnight?

---

## 1. Exact Timeline (hourly)

| Phase | Period | OAI-SearchBot rate | Event |
|---|---|---:|---|
| Baseline | Mar 19-20 | ~26/h (620/day) | Normal indexing |
| First surge | **Mar 21 02:00-04:00** | 68-84/h (3x) | OAI-SearchBot starts exploring new URL patterns |
| Main burst | **Mar 21 07:00-09:00** | 149-262/h (10x) | Systematic crawl of entity URL patterns |
| Sustained | Mar 21 10:00-23:00 | 41-108/h (2-4x) | Continues exploring |
| **Mega spike** | **Mar 22 08:00** | **1,443/h** (55x!) | Massive batch indexing |
| High plateau | Mar 22 09:00-23:00 | 92-372/h | Crawls /alternatives/*, /predict/*, /guide/* etc. |
| Settling | Mar 23+ | ~160/h | New higher baseline |

**Total Mar 21-22:** ~7,757 OAI-SearchBot requests (vs ~1,238 in same period Mar 19-20 = **6.3x increase**)

## 2. What Was Indexed During the Spike

### BEFORE spike (Mar 14-20): narrow focus

| Pattern | Count | % |
|---|---:|---:|
| `/token/*` (crypto) | 651 | **28%** |
| `/is-*-safe` | 341 | 15% |
| `/compare/*` | 323 | 14% |
| `/safe/*` | 254 | 11% |
| misc | 674 | 29% |

### DURING spike (Mar 21-22): massive breadth expansion

| Pattern | Count | % | vs pre-spike |
|---|---:|---:|---:|
| `/is-*-safe` | 698 | 9% | 2x |
| `/safe/*` | 506 | 7% | 2x |
| `/dataset/*` | 358 | 5% | **40x** |
| localized (/{lang}/*) | 348 | 5% | **12x** |
| `/alternatives/*` | 339 | 4% | **NEW** |
| `/profile/*` | 296 | 4% | **12x** |
| `/compare/*` | 153 | 2% | 0.5x |
| `/predict/*` | 147 | 2% | **NEW** |
| `/guide/*` | 89 | 1% | **NEW** |
| `/badge/*` | 42 | 1% | **NEW** |
| `/who-owns/*` | 34 | <1% | **NEW** |
| `/was-*-hacked` | 35 | <1% | **NEW** |
| `/does-*-sell` | 35 | <1% | **NEW** |
| `/review/*` | 35 | <1% | **NEW** |
| `/privacy/*` | 33 | <1% | **NEW** |
| `/pros-cons/*` | 34 | <1% | **NEW** |

**OAI-SearchBot discovered 9 entirely new URL pattern families** during the spike. Pre-spike, it only knew about `/safe/*`, `/is-*-safe`, `/token/*`, `/compare/*`. During the spike, it systematically indexed `/alternatives/*`, `/predict/*`, `/guide/*`, `/badge/*`, `/who-owns/*`, `/was-*-hacked`, `/does-*-sell-your-data`, `/review/*`, `/privacy/*`, `/pros-cons/*`.

For each entity (e.g. "trulens"), OAI-SearchBot crawled:
- `/safe/trulens` + `/who-owns/trulens` + `/was-trulens-hacked` + `/review/trulens` + `/privacy/trulens` + `/pros-cons/trulens` + `/does-trulens-sell-your-data` + `/alternatives/trulens` + `/predict/trulens` + `/guide/trulens` + `/badge/trulens`

This is **11 URLs per entity** vs 1-2 before. An entity that was indexed once is now indexed 11 times.

## 3. What Happened on OUR Side (Mar 14-20)

### Git history

Commits from this period were squashed into bulk imports on April 7. No specific commit can be identified.

### IndexNow logs

IndexNow log starts April 3 — no data for the Mar 14-20 period.

### What can be inferred

The 9 new URL patterns (`/alternatives/*`, `/predict/*`, `/guide/*`, etc.) were deployed before Mar 21. OAI-SearchBot discovered them either via:

1. **Sitemap inclusion** — these patterns were added to the sitemap
2. **Internal linking** — entity pages started linking to `/alternatives/X`, `/who-owns/X` etc.
3. **OAI-SearchBot following links** — once it found one `/alternatives/` page, it discovered the pattern and crawled systematically

The most likely trigger was **sitemap expansion + internal linking**: the entity pages (which OAI-SearchBot was already crawling at `/safe/*`) added internal links to the new URL patterns. OAI-SearchBot followed these links and discovered an entire family of question-shaped URLs.

### HuggingFace entity expansion

The `/dataset/*` and `/profile/*` patterns had 40x and 12x increases respectively. This coincides with Nerq's HuggingFace entity expansion which happened in this period. New entities (models, datasets, profiles) were added, and each one generated the full URL pattern family.

## 4. Have We Done Anything Similar Since?

### Comparable events post-spike

| Date | Change | OAI-SearchBot response |
|---|---|---|
| Mar 21-22 | 9 new URL patterns discovered | **6.3x spike → permanent 3x higher baseline** |
| Apr 10 | Apple meta tags + Schema.org enhancements | No OAI-SearchBot impact visible |
| Apr 10 | ETag support added | No impact |
| Apr 11 | M5.1 IndexNow randomization | No OAI-SearchBot impact (different bot) |

**Nothing since Mar 21 has triggered a comparable OAI-SearchBot response.** The reason: there haven't been new URL pattern families. We've been optimizing existing patterns (meta tags, Schema.org, caching) rather than creating new question-shaped URL families.

## 5. Hypothesis + Replication Plan

### Hypothesis (high confidence)

**OAI-SearchBot's Mar 21 spike was triggered by discovering new question-shaped URL patterns via internal linking from already-indexed entity pages.**

Evidence:
1. 9 entirely new URL pattern families appeared in the spike data
2. The patterns answer natural questions: "who owns X?", "was X hacked?", "does X sell your data?"
3. OAI-SearchBot crawled these patterns systematically (same entity across all patterns)
4. ChatGPT-User jumped the same day — indexed question URLs immediately surfaced as answers

**ChatGPT Search is specifically tuned to surface pages that answer questions.** Our question-shaped URLs (`/is-X-safe`, `/who-owns/X`, `/was-X-hacked`) are structurally optimized for this.

### Replication plan

To trigger another spike, create a new family of question-shaped URLs:

**Candidate patterns (not yet deployed):**

| Pattern | Question answered | Entities |
|---|---|---|
| `/how-secure-is/{slug}` | "How secure is X?" | All entities |
| `/can-i-trust/{slug}` | "Can I trust X?" | All entities |
| `/should-i-use/{slug}` | "Should I use X?" | All entities |
| `/is-{slug}-open-source` | "Is X open source?" | All entities |
| `/is-{slug}-free` | "Is X free?" | All entities |
| `/{slug}-vs-{slug2}-security` | "X vs Y security comparison" | Top 1000 pairs |
| `/how-does-{slug}-compare` | "How does X compare?" | All entities |

**Implementation:**
1. Create route handlers for 2-3 new patterns
2. Add internal links from existing `/safe/` pages
3. Submit to sitemap
4. Run IndexNow
5. Monitor OAI-SearchBot response over 7 days

### Risks

1. **Google may see thin content** — each new pattern must have unique, valuable content, not just URL reshuffling. If `/how-secure-is/X` shows the same content as `/safe/X`, Google may demote both.

2. **Diminishing returns** — the first 9 patterns may have captured most question types. Additional patterns may have lower marginal value.

3. **Content cannibalization** — too many URLs per entity may dilute PageRank internally.

### Recommended first test

Deploy `/can-i-trust/{slug}` with unique content (emphasizing trust signals differently from `/safe/`). Add internal links from `/safe/` pages. Run IndexNow. Measure OAI-SearchBot indexing rate and ChatGPT-User impact over 14 days.

**Expected outcome:** 1.3-2x increase in ChatGPT-User traffic if the pattern gains OAI-SearchBot coverage. Less than the original 27x spike since the initial discovery effect is a one-time event.
