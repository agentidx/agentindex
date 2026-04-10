# M5 Audit Verification Notes — Critical Discrepancies Found

**Written:** 2026-04-10 by Claude chat session during M5 audit review
**Purpose:** Document discrepancies between Claude Code's M5 audit findings and spot-check verification
**Status:** Audit findings are DISPUTED. Do not base strategic decisions on the audit summary without re-measurement.
**Blocks:** ADR-005 Kings hypothesis decision must wait for corrected measurement

---

## Summary

Claude Code produced a 766-line M5 audit at docs/status/leverage-sprint-day-2-m5-audit.md. The audit's key findings claimed Kings get 5.8x more AI citations than non-Kings and that ai_tool is a natural experiment showing Kings underperform. Spot-check verification via psycopg2 directly against the agentindex Postgres database revealed that two of five key findings are either incorrect or materially misleading.

The core problem: the audit's strongest claim (5.8x ratio) comes from a single registry (npm). It is not a score-controlled comparison across multiple registries as the audit summary implies.

---

## Verified findings from the audit

### Finding 2 CONFIRMED — Crawl bias is real and structural (stronger than audit stated)

Audit claim: auto_indexnow.py:347-354 prioritizes Kings with ORDER BY is_king DESC.

The actual code at auto_indexnow.py:
- WHERE clause: (is_king = true OR trust_score >= 70) — admits Kings unconditionally
- ORDER BY is_king DESC NULLS LAST, trust_score DESC NULLS LAST — protects Kings from cutoff
- LIMIT 50000 — Kings always fit, low-scored non-Kings cut off
- Followed by 6-language multiplier loop for [es, de, fr, ja, pt, id]

The crawl bias is structural on two dimensions:
1. WHERE clause admits Kings unconditionally regardless of trust_score
2. ORDER BY protects all Kings from LIMIT cutoff
3. 6-language loop multiplies their IndexNow submission count by 6x on a Kings-dominated slug list

Implication: Kings are structurally guaranteed more IndexNow submissions than non-Kings. The 5.8x citation ratio could be entirely explained by "we submitted Kings more URLs" rather than "AI crawlers prefer Kings."

This finding is confirmed and is the single most important crawl-bias evidence.

---

## Disputed findings from the audit

### Finding 3 INCORRECT — ai_tool is NOT 100% Kings

Audit claim: "In the one registry where Kings are least quality-selected (all seeded entities get is_king=true), Kings get fewer citations."

Verification query:
SELECT is_king, COUNT(*) FROM software_registry WHERE registry='ai_tool' GROUP BY is_king;

Actual result:
- is_king=False: 1,554 (66%)
- is_king=True:    787 (34%)

ai_tool is 34% Kings and 66% non-Kings — not "all seeded entities get is_king=true" as the audit claimed. There is clear selection (only 1/3 are Kings), so the "natural experiment where selection is random" framing is factually wrong.

The underlying observation that ai_tool Kings might get fewer citations per page than non-Kings is NOT verified by this audit — we never looked at actual citations for ai_tool specifically. The interpretation chain depended on a false premise about selection.

What we still do not know about ai_tool: whether ai_tool Kings actually get fewer citations per page than non-Kings. The pilot measurement would need to re-run specifically on this registry before concluding anything about selection quality.

### Finding 1 MATERIALLY INCORRECT — "5.8x score-controlled" is a single-registry observation

Audit claim: "Kings get 5.8x more AI citations than non-Kings in the same 80-100 trust score band (30d, /safe/ + localized paths, 435 Kings vs 3,093 non-Kings)."

Verification query for registries with entities in the 80-100 trust score band:
SELECT registry, COUNT(*) FILTER (WHERE is_king=true) as kings, COUNT(*) FILTER (WHERE is_king=false OR is_king IS NULL) as non_kings FROM software_registry WHERE trust_score BETWEEN 80 AND 100 GROUP BY registry;

Actual result:
- npm:  400 kings, 3110 non_kings
- pypi:  35 kings,    0 non_kings
- vpn:   17 kings,    0 non_kings

Only three registries have any entities in the 80-100 band. Of those, only one (npm) has both Kings and non-Kings present.

Balanced analysis (Kings>=10 AND non_kings>=10): 1 registry total (npm).

The 5.8x ratio is a single-registry observation about npm, not a cross-registry score-controlled comparison. The audit's aggregate numbers (435 Kings vs 3,093 non-Kings) align almost exactly with the npm-only numbers (400 vs 3,110), confirming that npm is driving the entire signal.

This fundamentally changes the interpretation. A 5.8x ratio in a single registry, with known structural crawl bias favoring Kings, and no comparable control registries, is NOT sufficient evidence to conclude Kings are a generally useful category. It is a very small slice of data, conflated with submission bias.

---

## What we actually know after verification

1. Crawl bias is confirmed and structural (auto_indexnow.py multiply-submits Kings via LIMIT protection + 6-language loop)
2. The 5.8x ratio applies only to npm, not to "Kings vs non-Kings across registries"
3. ai_tool Kings/non-Kings performance is unknown (the audit's analysis was based on a false premise about selection)
4. Four registries (vpn, country, charity, crypto) have 100% or near-100% Kings — not useable for comparative measurement
5. Four registries have zero Kings — cannot test the hypothesis at all
6. Only npm has balanced Kings and non-Kings in any meaningful trust score band

---

## What we do not know

1. Is the npm 5.8x ratio explained by submission bias or crawler preference?
   Answer requires a controlled experiment: remove Kings prioritization from auto_indexnow.py for 7-14 days and re-measure.

2. Does the Kings effect hold in any registry besides npm?
   Answer requires finding or constructing balanced cohorts in additional registries — only one exists today.

3. Is "Kings" as a concept capturing "selection quality" rather than a distinct high-yield category?
   Answer requires measuring within-registry variance across trust score deciles, not comparing Kings vs non-Kings at the same trust score.

4. What is the actual citation count distribution for Kings vs non-Kings in ai_tool registry specifically?
   Answer requires direct query against analytics.db with the correct slug to path mapping.

---

## Recommendations for next session

### Immediate (next M5 session, ~2 hours)

1. Re-run pilot measurement with corrected understanding — restrict to npm-only first, acknowledge single-registry limitation
2. Add ai_tool measurement — actually query ai_tool citation distribution, don't infer from selection theory
3. Document structural crawl bias in ADR-005-kings-hypothesis-disputed.md — draft the decision framework but do not conclude yet
4. Calculate posterior with crawl bias as a prior — even 5.8x observed ratio has a much lower "true effect" after accounting for 6x multi-language submission bias

### Medium-term (M5 + M6 interaction, 1-2 days)

5. Design the submission-bias removal experiment — draft exact code change to auto_indexnow.py to remove Kings prioritization, plan 7-day measurement window
6. Decision framework: if npm ratio drops to below 2x after removing bias, Kings concept is mostly submission bias; if ratio stays above 4x, Kings concept is real but needs better cross-registry validation

### Long-term (before any M6-M8 decisions)

7. Do not proceed with M6 (A3-Fix of 225 broken Kings) on the basis of 5.8x ratio alone — those fixes are still worthwhile for quality reasons, but frame the justification as "fix broken content" not "protect high-yield category"
8. Do not proceed with M8 (Scale Kings to 500K) until submission bias is controlled and cross-registry validation exists

---

## Meta-observation

Claude Code's audit was large (766 lines) and confident but contained fundamental errors that only became visible through direct database verification. Two of five key findings were wrong. This is exactly the type of error that pre-registration and spot-check verification are designed to catch.

The cost of not catching these errors would have been:
- ADR-005 written with incorrect premises
- M6 (Fix) justified by false evidence
- M7 (Gate) designed around a concept that may not generalize
- M8 (Scale) committing significant work to scale a category whose value is unproven

The cost of catching them:
- 30 minutes of verification queries
- One additional audit file
- Delayed strategic decision by one session

Clear win for verification.

---

## Day 2 M5 status: stopped for fresh focus tomorrow

Day 2 has been ~5.5 hours of concentrated work across M3 + M4a + M4b (7 of 8 steps) + M5 audit. Strategic decisions about Kings hypothesis require fresh cognitive state, not end-of-day exhaustion. Stopping here is the correct call.

Next session start: read this file first, then re-examine the M5 audit with corrected understanding, then design the controlled experiment for npm submission bias.
