# M5.1 Experiment — Kings Crawl Bias Removal

**Started:** 2026-04-11 (Day 3 of Leverage Sprint)
**Status:** ACTIVE — collecting data
**Owner:** Anders + Claude chat session
**Reverse plan:** see below
**End date:** 2026-04-18 (7 days) or 2026-04-25 (14 days) depending on signal strength
**Location of patch:** agentindex/auto_indexnow.py lines ~340-365
**Documentation:** This file + ADR-005-draft (after experiment ends)

## Pre-registration

This is a controlled experiment to test whether the Kings hypothesis (Kings get higher AI citation yield per indexed page) is real, or whether it is fully or partially explained by submission bias from auto_indexnow.py prioritizing Kings in IndexNow submissions.

The hypothesis being tested:

> H0 (null): Kings receive AI citations at the same rate per indexed page as non-Kings, controlled for trust_score. Any observed difference comes from submission bias (we submit Kings more aggressively).
>
> H1 (alternative): Kings receive AI citations at a higher rate per indexed page than non-Kings even when submission rates are equalized. The Kings concept captures something real about AI crawler preferences.

**Decision rule (pre-registered before looking at results):**

- If, after 7 days, the citation rate for Kings (sampled randomly) is **less than 1.5x** the rate for non-Kings (also sampled randomly), the Kings hypothesis is **rejected** as a primary signal. Kings concept is mostly submission bias.
- If the ratio is **between 1.5x and 3x**, the Kings hypothesis is **partially supported** but the original 5.8x claim from M5 audit was inflated by submission bias.
- If the ratio is **3x or higher**, the Kings hypothesis is **supported** even after controlling for submission bias.

These thresholds are set BEFORE collecting any post-experiment data. Do not adjust them after seeing results.

## What was changed

The Kings prioritization in `auto_indexnow.py` lines ~340-365 was replaced with random sampling from a broader pool. The old SQL is preserved in code comments for reverse.

**Original SQL (active 2026-04-09 through 2026-04-10):**
```sql
SELECT slug FROM software_registry
WHERE trust_score IS NOT NULL AND trust_score > 0
  AND description IS NOT NULL AND description != ''
  AND (is_king = true OR trust_score >= 70)
ORDER BY is_king DESC NULLS LAST, trust_score DESC NULLS LAST
LIMIT 50000
```

**Experiment SQL (active 2026-04-11 onwards):**
```sql
SELECT slug FROM software_registry
WHERE trust_score IS NOT NULL AND trust_score >= 50
  AND description IS NOT NULL AND description != ''
ORDER BY RANDOM()
LIMIT 50000
```

**Differences:**
- `trust_score >= 50` instead of `>= 70` — broader pool (1,153,342 entities vs 62,719)
- Removed `is_king = true OR` — Kings no longer privileged
- `ORDER BY RANDOM()` instead of `ORDER BY is_king DESC` — random sampling
- `LIMIT 50000` unchanged — same submission volume

## Pool composition after change

Verified via direct psycopg2 query 2026-04-11 ~07:30 CEST:

| Metric | Pre-experiment | Experiment |
|---|---|---|
| Total eligible | 62,719 | 1,153,342 |
| Kings in pool | ~37,688 (60%) | 18,110 (1.6%) |
| Non-Kings in pool | ~25,031 (40%) | 1,135,232 (98.4%) |
| Expected Kings in 50K sample | ~50,000 (100%) | ~785 (1.6%) |
| Expected non-Kings in 50K sample | ~0 (0%) | ~49,214 (98.4%) |

The expected King/non-King split in the random sample exactly matches their natural prevalence in the trust_score >= 50 pool. This is what makes the experiment a fair test.

## Submission volume preserved

The LIMIT 50000 cap is unchanged. Multi-language loop (es, de, fr, ja, pt, id) is unchanged. Total submitted URL count per day will remain at ~300,000 candidates → ~60,000-70,000 actual submissions after dedupe (same as 2026-04-11 morning run).

## What we measure

Two questions to answer:

**Q1 — Citation rate per page (primary):**
For Kings sampled in the experiment vs non-Kings sampled in the experiment, how many AI citations does each entity receive on average over the 7-day window?

**Measurement query (run after 7 days):**
```sql
WITH submitted_in_experiment AS (
    SELECT DISTINCT slug
    FROM indexnow_submit_tracking.tracked_urls
    WHERE submitted_at >= '2026-04-11 07:00'
      AND submitted_at < '2026-04-18 07:00'
      AND url LIKE 'https://nerq.ai/%/safe/%'
)
-- Join with Postgres for is_king status
-- Join with analytics.db for AI citation count per slug
```

(Exact query design will be finalized at end of experiment based on what tracking data is actually available.)

**Q2 — Total citation distribution (secondary):**
Even if individual page citation rate looks different, total volume of AI citations from the random-sampled cohort vs what we historically saw with Kings-prioritized cohort. This catches whether the experiment is somehow producing fewer total citations (indicating that the random sampling is fundamentally less efficient).

## Risk assessment

**Risk 1: Citation volume crashes during experiment**
**Likelihood:** Low. We are submitting the same volume to the same crawlers; only the slug distribution changes.
**Mitigation:** Monitor `/flywheel?period=24h` daily. If AI citation count drops more than 20% on day 2 or 3, abort the experiment and revert.

**Risk 2: Kings citations drop because Kings stop being submitted**
**Likelihood:** Medium. Kings will only get ~1.6% of submissions instead of ~100%.
**Mitigation:** This is BY DESIGN — the whole point is to see whether Kings still get cited at high rates per indexed page when they're submitted at lower volume. If Kings citation rate drops proportionally to submission rate (1.6%), the Kings hypothesis is real. If Kings citation rate drops faster than submission rate, Kings get cited only because they're submitted.

**Risk 3: Random sampling produces volatile day-to-day data**
**Likelihood:** High over short timeframes.
**Mitigation:** Wait full 7 days before analyzing. Use 7-day rolling averages for comparison, not single-day snapshots.

## How to monitor (daily check during experiment)

```bash
# 1. Verify experiment is still running (not reverted)
grep "M5.1 EXPERIMENT" /tmp/auto-indexnow.log | tail -1

# 2. Daily flywheel check
curl -s "http://localhost:8000/flywheel?period=24h" | grep -oE "AI Citations.{0,100}"

# 3. Quick anomaly check
sqlite3 ~/agentindex/logs/analytics.db "
    SELECT date(ts) as day, COUNT(*)
    FROM requests
    WHERE is_ai_bot=1 AND status=200
      AND ts >= '2026-04-11'
    GROUP BY day ORDER BY day;
"
```

## Reverse plan

If the experiment needs to be aborted (Risk 1 triggered, or other reasons):

```bash
cd ~/agentindex

# Revert auto_indexnow.py to use original Kings SQL
# The original SQL is preserved in code comments at the patch site
# Manual edit or git revert <commit-hash>

git revert <m5.1-commit-hash>  # if no other changes
# OR manually restore SQL from comments
```

Verification after revert:
```bash
grep "is_king = true" agentindex/auto_indexnow.py
# Should return the SELECT block
```

Next morning at 07:00, auto_indexnow.py will run the restored Kings SQL and resume normal operation.

## End of experiment checklist

- [ ] 7 days have passed (or 14 days if signal is weak)
- [ ] Run measurement queries (Q1 and Q2)
- [ ] Document results in `docs/status/leverage-sprint-day-NN-m5.2-results.md`
- [ ] Apply pre-registered decision rule
- [ ] Decide: revert, partial revert, or commit to permanent change
- [ ] Draft `ADR-005-kings-hypothesis-resolution.md` based on findings

## Why this matters

The Kings concept underpins potential M6 (Fix 225 broken Kings), M7 (Quality Gate), and M8 (Scale Kings to 500K). All three milestones cost meaningful work. Before committing that work, we need to know if Kings is a real category or just a self-fulfilling label that ranks itself first in IndexNow submissions.

If the experiment shows Kings is primarily submission bias, M6/M7/M8 must be redesigned around different criteria. If it shows Kings is real, we proceed with the Kings concept but with proper measurement and documentation of the actual effect size (not the inflated 5.8x claim from M5 audit).

The cost of running this experiment is 7 days of sub-optimal IndexNow submissions where some Kings are crowded out by random non-Kings. The cost of NOT running it is potentially weeks of work scaling a category whose value is unproven.

## Coordination notes

**Parallel sessions:** This file should be the canonical reference for M5.1. If a parallel Claude session needs to make changes to auto_indexnow.py during the experiment window, they MUST read this file first and confirm with Anders that the change does not invalidate the experiment.

**End-of-experiment session:** When measuring on 2026-04-18 (or 2026-04-25), start by reading this file and confirming the pre-registered decision rules. Do not adjust thresholds after seeing data.
