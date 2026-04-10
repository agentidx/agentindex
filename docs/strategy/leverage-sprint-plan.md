# Leverage Sprint — Apple Intelligence, AI-to-Human Tracking, Kings Scaling

**Period:** 5-6 days active work (starting 2026-04-10), then background batches running into Phase 0
**Sequence position:** **Before** Phase 0 cloud migration. Leverage Sprint runs first, then Phase 0, then Phase 1-4.
**Parent strategy:** ADR-003 cloud-native expansion-first architecture
**Sequence revision:** ADR-003 Addendum #3 (formalizes leverage-before-Phase 0)
**Companion:** `docs/strategy/phase-0-cloud-migration-plan.md` (still the authoritative Phase 0-4 plan, just starts ~1 week later than originally scheduled)

---

## Overview

This sprint executes three high-leverage changes that multiply the value of work already done, without requiring new verticals, new languages, or cloud infrastructure. Each change has a specific hypothesis about where untapped upside exists in the current system.

Sprint starts **2026-04-10**, the day after the strategic planning session of 2026-04-09. Mac Mini was connected to Mac Studio the same day and stands idle — this sprint is the first productive use of that capacity.

The sprint is named "Leverage" because the common form across all three tracks is the pattern identified in previous aha-moments: unlock value that already exists rather than build new things. It deliberately runs before Phase 0 cloud migration because momentum during active development is a primary value, and pausing for infrastructure work has a larger opportunity cost than the risk reduction Phase 0 provides on any given week.

**Zero marginal cost.** All LLM work in this sprint executes via Claude Code on Mac Studio and Mac Mini, which does not consume Anthropic API billing. Infrastructure is already paid for. The only investment is calendar time and Anders's review attention.

### The three tracks

| Track | Name | Hypothesis | Estimated upside |
|---|---|---|---|
| **A1** | Apple Intelligence optimization | Applebot is 37% of bot traffic (513K/day per 2026-04-09 baseline) but zero Apple-specific optimization has been done. An early rider on Siri/Safari/Spotlight AI rollout. | 15-40K additional human visits/day if Apple Intelligence begins citing Nerq. |
| **A2** | AI-to-human conversion tracking | Current AI → human conversion rate is unknown. Cannot optimize what cannot be measured. Prerequisite for hook-based CTR optimization in later phases. | No direct traffic. Enables 2-4x future optimization. |
| **A3** | Kings scaling 27K → 500K | Kings (pages with 5 JSON-LD + FAQ + nerq:answer + rich structure) have a demonstrated positive feedback loop with Claude citations. Currently only 0.5% of entities are Kings. | 2-5x Claude citation volume from the Kings cohort, compounding over time. |

### Why now (not after Phase 0)

**Mac Mini is idle capacity already paid for.** It was connected to Mac Studio on 2026-04-09 and has not yet run productive work. Deferring its first use by two weeks wastes ~14 days of free compute that is already sitting in the room.

**Mac Studio's acute risks are mitigated.** The autoheal restart loop was fixed on 2026-04-09 morning. The remaining risk is hardware failure at 2-5% probability per week. Paying two weeks of momentum to reduce a 2-5% weekly risk is a poor trade for a solo bootstrapper optimizing for every day of growth.

**Momentum compounds; pauses don't.** Expansion-plan growth (7K → 43K human visits/day from February to April) came from running hard, not from pausing for infrastructure. Two weeks of pause can cost more in delayed trigger-timing than Phase 0 saves in risk reduction.

**Leverage Sprint improves Phase 0 when it arrives.** A2 tracking establishes a baseline Phase 0 can verify against. A3 proves our ability to run batch operations on 500K+ entities — exactly the muscle needed for Phase 0's Postgres transfer. A1 Apple optimization is defensible improvements that carry over cleanly.

**For a solo bootstrapper with a long time horizon, momentum first is the correct operating model.** The alternative is appropriate for VC-funded startups optimizing for survival until the next funding round.

---

## Prerequisites

Simplified compared to the original post-Phase 0 version:

- [ ] Mac Studio healthy (uptime stable, no active autoheal incidents)
- [ ] Mac Mini connected and reachable from Mac Studio via Tailscale (confirmed 2026-04-09)
- [ ] Postgres replication Mac Studio → Mac Mini live (confirmed in baseline: walsender streaming to 100.115.230.106)
- [ ] Claude Code installed and working on both Mac Studio and Mac Mini
- [ ] Working tree clean and pushed on main branch (verify: `cd ~/agentindex && git status && git log --oneline -3`)
- [ ] Baseline capture from 2026-04-09 intact at `~/nerq-baselines/2026-04-09-pre-migration/`
- [ ] Backup taken immediately before starting (see Safety section below)

**Not required:**
- Phase 0 cloud migration (this sprint runs before it)
- Hetzner servers provisioned (not needed for this sprint)
- `stale_score_detector` fix (needed for A3 measurement later, but can be done during the sprint not before)
- Freshness SLA dashboard (same — can be built during or after)

---

## Safety: backup before starting

Before any write operations begin, take a complete backup so that if Mac Studio fails during Leverage Sprint, recovery is possible without data loss. This is non-negotiable.

### Backup procedure

Run this on Mac Studio before Day 1 work starts:

```
bash << 'EOF'
BACKUP_DIR="$HOME/nerq-backups/2026-04-10-pre-leverage-sprint"
mkdir -p "$BACKUP_DIR"
cd "$BACKUP_DIR"

echo "=== Leverage Sprint pre-start backup ==="
date

# 1. Postgres full dump
echo ""
echo "--- Postgres dump (this takes ~15-30 min for 89GB) ---"
PG="/opt/homebrew/Cellar/postgresql@16/16.11_1/bin"
time $PG/pg_dump -U anstudio -Fc -f agentindex.dump agentindex
ls -lh agentindex.dump

# 2. SQLite snapshots
echo ""
echo "--- SQLite copies ---"
cp ~/agentindex/logs/analytics.db analytics.db
cp ~/agentindex/agentindex/crypto/crypto_trust.db crypto_trust_crypto.db
cp ~/agentindex/data/crypto_trust.db crypto_trust_data.db
ls -lh *.db

# 3. Sacred HTML refresh
echo ""
echo "--- Sacred HTML snapshots ---"
mkdir -p sacred
for url in \
  "https://nerq.ai/safe/nordvpn" \
  "https://nerq.ai/safe/bitwarden" \
  "https://nerq.ai/safe/express" \
  "https://nerq.ai/de/safe/nordvpn" \
  "https://nerq.ai/ja/safe/nordvpn" \
  "https://nerq.ai/no/safe/nordvpn" \
  "https://nerq.ai/best/safest-vpns" \
  "https://nerq.ai/best/safest-password-managers" \
  "https://nerq.ai/" \
  "https://zarq.ai/"; do
  slug=$(echo "$url" | sed 's|https://||;s|/|_|g')
  curl -s "$url" > "sacred/$slug.html"
  size=$(wc -c < "sacred/$slug.html")
  echo "  $url: $size bytes"
done

# 4. Git state
echo ""
echo "--- Git state ---"
cd ~/agentindex
git log --oneline -5 > "$BACKUP_DIR/git-head.txt"
git status > "$BACKUP_DIR/git-status.txt"
cat "$BACKUP_DIR/git-head.txt"

# 5. Total size
echo ""
echo "--- Backup size ---"
du -sh "$BACKUP_DIR"
EOF
```

**Do not proceed with Day 1 work until backup is verified.** The size should be ~90 GB (dominated by Postgres dump). If it is much smaller, something failed.

### Why this specific backup

- **Postgres full dump** = restorable to any fresh Postgres instance. Includes all 89 GB including `agent_jurisdiction_status`, `entity_lookup`, `agents`, and all Kings metadata.
- **SQLite copies** = analytics and crypto data. These do not replicate via Postgres WAL, so explicit copies are needed.
- **Sacred HTML refresh** = current production output for byte-drift comparison. If A3 Kings upgrades drift sacred elements, this is the reference point for rollback.
- **Git state** = code baseline. Git is already on GitHub (6448583 on main), so this is just a record of where we were.

### If backup fails

Stop. Diagnose. Do not start any write work. If Postgres dump fails repeatedly, that is itself a signal that Mac Studio is unhealthy and Phase 0 should be accelerated instead of Leverage Sprint.

---

## Track A1 — Apple Intelligence Optimization

**Duration:** 1-2 days
**Owner:** Claude Code on Mac Studio executes
**Blocking?** No — independent of A2 and A3

### Hypothesis

Applebot is already 37% of bot traffic with 513K requests/day per the 2026-04-09 baseline. No Apple-specific optimization has been done. Apple Intelligence (Siri, Safari, Spotlight) is rolling out across 1.5 billion devices and its citation patterns are still being established. Early optimization may establish Nerq as a preferred source in a way that is harder to displace later.

### Deliverables

1. **robots.txt verification** — Applebot and Applebot-Extended explicitly allowed with no conflicting rules. Currently believed to be allowed (part of "welcome all traffic" policy) but never explicitly verified for Apple-specific directives.

2. **Apple-specific meta tags** on entity pages and /best/ pages:
   - `apple-mobile-web-app-capable`
   - `apple-mobile-web-app-status-bar-style`
   - `apple-mobile-web-app-title`
   - `apple-touch-icon` (multiple sizes: 120, 152, 167, 180)
   - `format-detection` (disable phone auto-link where appropriate)

3. **Open Graph image optimization for iMessage link previews.** When users share Nerq links on iMessage, the preview should display the trust score prominently. This is a subtle virality vector — people share "is X safe?" checks with friends.
   - Auto-generated OG image per entity showing trust score, name, category
   - Size: 1200×630, with Apple-optimized variant 1200×900
   - Cached in Cloudflare for long TTL
   - Generated on-demand, not pre-rendered (same pattern as ADR-003 render-on-demand)

4. **Schema.org SoftwareApplication enhancement.** Apple extracts this for Siri knowledge graph:
   - `applicationCategory` (explicit per vertical)
   - `operatingSystem` where known
   - `softwareVersion` where known
   - `offers` block (even for free software)
   - `aggregateRating` populated from trust score

5. **Performance verification for Applebot.** Apple ranks heavily on TTFB:
   - Measure TTFB from 5 geographic locations for entity pages
   - Cache headers explicit and friendly (`max-age`, `s-maxage`)
   - Verify no unnecessary redirects
   - Verify compression (gzip/brotli) enabled
   - **Note:** Mac Studio's current TTFB may be above Apple's preferred threshold. Document the number as-is. Phase 0 cloud migration will improve it further; for this sprint, we improve what we can improve now (headers, compression, redirects) and live with the rest.

6. **Apple News RSS feed investigation.** Apple News is a separate index that Siri uses. Investigation task:
   - Research if Nerq qualifies as a publisher
   - If yes: create `/feeds/weekly-trust-updates.rss` and submit
   - If no (likely — Apple News has strict publisher requirements): document why and move on

7. **Applebot analytics dashboard.** Track Applebot separately from other bots:
   - Daily request volume
   - Top requested paths
   - Change in crawl frequency week-over-week
   - Safari referrer patterns (if any appear — Safari can send referer headers)

### Done criteria

- [ ] robots.txt reviewed, Applebot/Applebot-Extended confirmed allowed with no exclusions
- [ ] Apple meta tags deployed on all entity page templates
- [ ] OG image generation live for all entity pages, cached in Cloudflare
- [ ] Schema.org SoftwareApplication enhanced with Apple-extracted fields
- [ ] TTFB measurement documented for 5 geographic locations
- [ ] Apple News RSS feed either submitted or explicitly documented as not applicable
- [ ] Applebot analytics dashboard live, showing baseline + 7-day trend
- [ ] Retrospective note: what changed, what did not, and plan to monitor Applebot behavior over the next 4 weeks

### Success indicators (measured 4 weeks after sprint)

- Applebot request volume increases materially (baseline: 513K/day, target: >600K/day)
- Safari referrer patterns appear in analytics (indicating Siri-triggered human visits)
- If Apple News RSS was submitted: subscribers > 0 within 2 weeks

None of these are guaranteed. Apple Intelligence is a black box. This track is a calibrated bet, not a certainty.

### Risks

- **Apple Intelligence is opaque.** We may do everything right and see no lift for months. Worst case: the effort is wasted but the improvements are also defensible.
- **OG image generation at scale.** 5M unique OG images generated naively would consume significant compute. Mitigation: generate on-demand with aggressive Cloudflare caching, not pre-render.
- **Schema.org changes can affect existing AI citations.** Any change to structured data risks breaking sacred elements. Golden file tests must pass before and after — non-negotiable.

### Rollback

- All meta tags are additive. Revert commits to remove them.
- OG image generation can be disabled with a feature flag.
- Schema.org changes are in code — revert commit.
- No database changes in this track, so no data rollback needed.

---

## Track A2 — AI-to-Human Conversion Tracking

**Duration:** 1-2 days
**Owner:** Claude Code on Mac Studio executes
**Blocking?** No — independent of A1 and A3

### Hypothesis

Current AI-to-human conversion rate is unknown. Baseline shows 515K daily AI citation requests and 43K daily human visits. If we assume 20% of human traffic comes from AI citations (rest from search), that is ~8.6K humans from ~515K AI requests = ~1.7% conversion. Doubling this via hook optimization would add 8-9K humans/day for free. But we cannot verify this hypothesis or optimize hooks without measurement.

### Deliverables

1. **Referrer pattern matching** for AI sources:
   - `claude.ai` → Claude
   - `chat.openai.com`, `chatgpt.com` → ChatGPT
   - `perplexity.ai` → Perplexity
   - `copilot.microsoft.com`, `bing.com/chat` → Copilot
   - `gemini.google.com` → Gemini
   - `grok.x.ai`, `x.com/i/grok` → Grok
   - `duckduckgo.com` (with AI parameter patterns) → DuckAssist
   - `kagi.com` → Kagi
   - Accept that some AI products strip referers — track what we can

2. **User-Agent pattern matching** for AI-browsing clients:
   - `ChatGPT-User` (the in-product browser)
   - `Claude-User` (Claude browsing tool when used)
   - `Perplexity-User`
   - These appear as "humans" in bot detection but should be tracked as a third category "AI-mediated humans"

3. **Database schema additions** in `analytics.db`:
   - New column `requests.ai_source` (nullable)
   - New column `requests.visitor_type` — one of `bot`, `human`, `ai_mediated`
   - Backfill from existing data where possible (referer field may already be captured)
   - Index on `(ai_source, ts)` for dashboard queries

4. **Attribution logic.** A visit counts as "AI-attributed" if ANY of:
   - Referer matches AI domain patterns
   - User-Agent matches AI-User patterns
   - Within 5 minutes of a known AI bot crawl of the same URL (timing correlation, weaker signal)

5. **Dashboard additions:**
   - AI-to-human conversion rate (overall + per AI source)
   - Top URLs by AI-attributed visits (which pages convert best)
   - Language breakdown
   - Vertical breakdown
   - Time-of-day patterns
   - Weekly trend

6. **Baseline measurement.** Run the new tracking for 7 days after deployment. Document the baseline conversion rate as the reference point. Commit to `docs/metrics/ai-to-human-baseline-2026-04-17.md` (or later date when 7-day window closes).

7. **Export API for A/B testing.** Simple endpoint returning conversion data for future hook-variant tests.

### Done criteria

- [ ] Referrer and UA pattern matching deployed in request logging path
- [ ] Database schema migrated, new columns populated for new requests
- [ ] Historical backfill complete (as much as possible given existing data)
- [ ] Dashboard panels live and populated
- [ ] Retrospective note: initial 1-2 day conversion rate per AI source (the 7-day baseline completes later)
- [ ] Export API returns correctly formatted data

### Success indicators

- Dashboard shows conversion data that looks plausible (not zero, not implausibly high)
- At least 5 AI sources are identifiable in the data
- Baseline is different from zero — we are getting AI-attributed humans today, just not measuring them

### Risks

- **Referrers stripped by AI products.** We will undercount. Mitigation: document this explicitly in the baseline so future measurements are comparable to the same flawed methodology.
- **User-Agent patterns change.** Mitigation: log unknown patterns for manual review, add to list as they appear.
- **Backfill may be incomplete.** If old logs don't store referer consistently, historical analysis is limited. Goal is forward-looking measurement.

### Rollback

- Schema changes are additive. Columns can be dropped without affecting production.
- Dashboard panels are read-only. Revert commits to remove.
- No risk to serving traffic.

---

## Track A3 — Kings Scaling 27K → 500K

**Duration:** 2-3 days active work on Mac Studio + Mac Mini, then background batches continuing for 25-50 days
**Owner:** Claude Code on Mac Studio (top 100K entities) + Claude Code on Mac Mini (long tail 400K)
**Blocking?** Partial dependency on A1 if A1 adds schema.org fields to the King template

### Hypothesis

Historical learning documented in previous session: "King-quality → Claude citations → higher trust → more citations. Positive feedback loop." Kings are currently ~27K entities of 5M total = 0.5%. Scaling to 500K (10%) should produce a material lift in Claude citations, and the lift should compound as Claude's ranking reinforces.

### Deliverables

1. **Kings audit.** Inventory what defines a King today:
   - Which JSON-LD blocks are required? (Product, Review, AggregateRating, FAQPage, SpeakableSpecification?)
   - What is the FAQ minimum? (number of questions, language coverage)
   - What is `nerq:answer`? Where does it live in the HTML?
   - What is the minimum content length?
   - What is the current automated check that classifies an entity as King vs non-King?
   - Are there Kings that have degraded (missing one of the elements)? Repair first.
   - Output: `docs/architecture/kings-definition.md`

2. **King candidate identification.** Rank entities by a composite score:
   - Analytics traffic (humans + AI bots, 30-day window)
   - Entity popularity (stars, downloads, usage — varies per registry)
   - Category balance (ensure verticals are represented)
   - Language coverage potential
   - Output: ranked list of top 500K candidates committed to `docs/metrics/kings-candidates-2026-04-10.csv`

3. **Enrichment pipeline.** A new script or extension of existing enrichment:
   - Reads target entity from Postgres
   - Generates missing JSON-LD blocks from existing data
   - Generates FAQ via Claude Code (on Mac Studio for top 100K, on Mac Mini for long tail)
   - Generates `nerq:answer` blocks
   - Validates output against King definition
   - Marks entity as King in database
   - **Migration-safe:** writes via transactions, each batch commits atomically. A pg_dump during Phase 0 will produce a consistent snapshot even if A3 is running.

4. **Quality gate.** Automated checks that fail the upgrade if:
   - Any JSON-LD block is invalid Schema.org
   - FAQ has fewer than 5 questions
   - FAQ questions are templated/duplicated (looks generic)
   - `nerq:answer` exceeds 150 words (should be concise)
   - Sacred elements (pplx-verdict, ai-summary) are missing or corrupted
   - The upgrade would introduce sacred bytes drift

5. **Execution environment:** Claude Code on both machines in parallel:
   - **Mac Studio:** top 100K entities by traffic + popularity (highest quality, benefits from best model)
   - **Mac Mini:** long tail 400K entities (same pipeline, reads from local Postgres replica, writes back to primary)
   - Coordination via work-log file `~/agentindex/work-logs/leverage-a3-progress.jsonl`
   - Each machine appends to the log when it claims a batch and when it completes
   - If both machines race on the same entity, second write is idempotent — no harm

6. **Rollout strategy:** Batch of 10K entities per day per machine (20K/day total), with monitoring:
   - Claude citation rate per batch (before/after comparison, measured weekly)
   - Sacred bytes drift = 0 check after each batch
   - If citation rate drops after any batch: pause, diagnose, resume
   - If sacred bytes drift appears: immediate rollback of that batch
   - **Phase 0 coordination:** A3 pauses during pg_dump (~30 min) and cutover window (~24h), resumes after

7. **Measurement:** A/B-style comparison:
   - Before scaling: baseline Claude citation rate per Kings vs non-Kings
   - After scaling: same measurement
   - Track over 4 weeks post-sprint
   - Document in `docs/metrics/kings-scaling-results-YYYY-MM-DD.md`

### Done criteria (active sprint phase)

- [ ] Kings definition documented in `docs/architecture/kings-definition.md`
- [ ] Candidate list generated (ranked, 500K entries) and committed
- [ ] Enrichment pipeline tested on 100 entities, 100% passing quality gate
- [ ] First batch of 10K deployed on Mac Studio, quality gate passing, sacred bytes drift = 0
- [ ] First batch of 10K deployed on Mac Mini, quality gate passing (validates Mac Mini can handle production load)
- [ ] Claude citation rate measured for batch 1 (establishes improvement metric)
- [ ] Work-log coordination file format documented
- [ ] Retrospective note: any issues with parallel execution, any quality issues, measured lift

### Done criteria (background phase, weeks following)

- [ ] 500K total Kings deployed across both machines
- [ ] Sacred bytes drift = 0 throughout
- [ ] Claude citation rate for new Kings > non-Kings cohort by 4 weeks in

### Success indicators

- Sacred bytes drift = 0 throughout all batches (non-negotiable)
- Quality gate rejection rate < 5%
- Claude citation rate for newly-promoted Kings > non-Kings within 2 weeks of promotion
- Total Claude citation rate lift visible in dashboard 4 weeks after sprint start

### Risks

- **LLM-generated FAQ quality.** If Claude Code generates generic or wrong FAQs, they hurt rather than help. Mitigation: strict quality gate, manual sample review, ability to roll back a batch.
- **Claude Code throughput.** 500K entities across two machines = 250K per machine. At 10K/day per machine that is 25 calendar days. Mitigation: sprint success criterion is batch 1 validated + rollout in progress, not all 500K completed. Long tail continues in background.
- **Mac Mini stability under first real load.** Mac Mini has not run production work yet. Mitigation: start with 1000 entities, scale up only after 24-hour stability confirmed.
- **Feedback loop assumption may be wrong.** Kings learning was observed at 27K scale. Scaling to 500K might flatten or invert the effect. Mitigation: measure per batch and stop if effect doesn't appear.
- **Postgres write load under Phase 0 preparation.** Mitigation: pause during pg_dump window, resume after. Batch size 10K keeps individual transactions small.
- **Mac Studio hardware failure during sprint.** Would lose in-progress Kings work. Mitigation: backup before starting (see Safety section), all original entity data remains intact — only the Kings-promotion metadata would be lost.

### Rollback

- Each batch is reversible. Revert the `is_king` flag in the database for that batch.
- Original entity data is untouched — only the Kings-specific fields are added.
- Sacred elements are never modified during King promotion.
- If a batch introduces sacred bytes drift: immediate revert of that batch and investigation before continuing.

---

## Parallelism and scheduling

| Day | Date | A1 Apple | A2 Tracking | A3 Kings (Mac Studio) | A3 Kings (Mac Mini) |
|---|---|---|---|---|---|
| 0 | Apr 10 morning | — | — | Pre-sprint backup (~30-45 min) | Verify Claude Code works, Postgres replica reachable |
| 1 | Apr 10 afternoon | robots + meta tags research | Schema design | Audit + candidate list generation | Idle, awaiting work queue |
| 2 | Apr 11 | Schema.org + OG images design | Deployment + backfill | Pipeline build + test 100 entities | Mirror pipeline, test 100 entities |
| 3 | Apr 12 | Apple News + performance + dashboard | Dashboard + baseline starts | Batch 1 (10K) + measurement | Batch 1 (10K) + stability check |
| 4 | Apr 13 | Retrospective | (baseline collection continues) | Batch 2-3 (20K more) | Batch 2-5 (40K more) |
| 5 | Apr 14 | — | Retrospective | Batch 4-6 (30K more) | Batch 6-10 (50K more) + retrospective |
| 6 | Apr 15 | — | — | Background: Hand-off to Phase 0 prep, pause rules engage | Background: continue batches |

**Active sprint elapsed time: 5-6 days.** A3 continues in background for ~25 days after active sprint ends, running on Mac Mini primarily with Mac Studio supporting when not needed for other work.

### Machine division of labor

**Mac Studio handles:**
- All A1 deliverables (they require production code deploy)
- All A2 deliverables (they require schema changes to analytics.db on Mac Studio)
- A3 Kings batches for top 100K entities (benefits from highest-quality model)
- Production serving (unchanged)

**Mac Mini handles:**
- A3 Kings batches for long tail 400K entities
- Reads from local Postgres replica (no production impact)
- Writes promotion metadata back to Mac Studio primary via Tailscale
- Idle until Day 1 afternoon when first batch starts

**Both machines share:**
- Work-log file at `~/agentindex/work-logs/leverage-a3-progress.jsonl` (synced via git, or rsync, or shared Dropbox-style mount — decide Day 1 based on what is simplest)
- Kings definition document (read-only reference)
- Candidate list CSV (read-only reference)

### Working methodology

1. **Claude Code on Mac Studio** does all A1 + A2 work and top-100K A3 work.
2. **Claude Code on Mac Mini** does long-tail A3 work only.
3. **Anders reviews at checkpoints:** end of Day 1 (candidate list + pipeline test), end of Day 3 (first batch results), end of Day 5 (sprint retrospective).
4. **Daily status:** A short status file committed at end of each day to `docs/status/leverage-sprint-day-N.md` summarizing what was done and any issues.

---

## Coordination with Phase 0 (starting ~2026-04-15)

When Phase 0 cloud migration starts (~Day 6 of this sprint), A3 background batches continue on Mac Mini with these coordination rules:

**During Phase 0 Week 1 (provisioning + Postgres preparation):**
- A3 batches continue at normal pace on Mac Mini
- Mac Studio A3 batches slow down or pause (Mac Studio is now busy with Phase 0 work)

**During pg_dump (estimated 30 min):**
- Both machines pause A3 writes
- Signal: `touch ~/agentindex/work-logs/leverage-a3-pause` on Mac Studio
- Signal to resume: `rm ~/agentindex/work-logs/leverage-a3-pause`

**During Postgres transfer (8-14 hours):**
- A3 paused on both machines
- Mac Mini can do other useful work (audit reports, analytics queries, next-language preparation)

**During cutover (24 hours):**
- A3 fully paused
- Production traffic migrates from Mac Studio to Hetzner
- Sacred bytes drift verified by golden file tests (A3 must pass this test before being allowed to resume)

**After cutover (Hetzner is primary):**
- A3 resumes, now writing to Hetzner Postgres primary via Tailscale
- Work-log picks up from where it left off (entity batches already processed are skipped)
- Background batches continue until 500K target reached

**If Mac Studio is retired/demoted after cutover:**
- Mac Studio A3 batches stop
- Mac Mini continues solo
- Alternatively, Mac Studio can be repurposed as a pure A3 worker for the remaining backlog

---

## Integration with other phases

### This sprint unblocks

- **Phase 2 (50-language sprint):** Language additions benefit from Apple optimization and Kings enrichment applied universally. New languages inherit King-quality structure automatically.
- **Phase 4 (100-vertical sprint):** New verticals built via the new pipeline automatically get King treatment when they hit candidate criteria.
- **Future hook-based optimization:** AI-to-human tracking provides the baseline against which hook variants are measured.

### This sprint is blocked by

- **Mac Studio + Mac Mini being healthy.** Sprint cannot start if either is offline.
- **Backup completion.** Sprint cannot start until backup is verified.

### This sprint does NOT block

- Phase 0 cloud migration (starts ~Day 6 of this sprint in parallel)
- Phase 1-4 (they start after Phase 0)

---

## Total cost estimate

| Track | LLM cost | Infrastructure cost | Human time (Anders) |
|---|---|---|---|
| A1 Apple | $0 (Claude Code on Mac Studio) | $0 | 2-3h review |
| A2 Tracking | $0 (Claude Code on Mac Studio) | $0 | 1-2h review |
| A3 Kings | $0 (Claude Code on Mac Studio + Mac Mini in parallel) | $0 | 3-4h review |
| **Total** | **$0** | **$0** | **~6-9h** |

**Why zero marginal cost:** Claude Code on Mac Studio and Mac Mini does not consume Anthropic API billing per ADR-003 Addendum #2. Infrastructure is sunk cost (both machines are already running). No new provisioning needed.

---

## Success metrics for the full sprint

The sprint is successful if, 4 weeks after active phase completion:

1. **Applebot request volume has increased materially** (baseline 513K/day, target >600K/day)
2. **AI-to-human conversion dashboard shows data** for at least 5 AI sources with plausible rates
3. **50K+ Kings deployed** in active sprint phase, remainder in background (target: 500K within 25-50 days)
4. **Claude citation rate for new Kings measurably higher** than non-Kings cohort
5. **Sacred bytes drift remains zero** throughout all deployments
6. **No regressions** in existing AI citation rates or human traffic
7. **Mac Mini stability confirmed** — ran at least 10 batches without incident
8. **Retrospective document** covering what worked, what did not, what surprised us

If metrics 4 and 8 are met, the Kings hypothesis is validated for future expansion. If 1 is met, the Apple bet pays off. If 2 is met, the baseline is established for future hook optimization.

---

## Rollback procedures

Each track has an independent rollback:

- **A1 Apple rollback:** Revert commits that added meta tags, schema.org fields, and OG image generation. Disable OG image generation via feature flag first (one-line change).
- **A2 Tracking rollback:** Disable new request logging columns (drop from write path). Database columns can remain for historical data.
- **A3 Kings rollback per batch:** `UPDATE entities SET is_king = false WHERE batch_id = N`. Does not affect underlying entity data. Can be done for one batch, multiple batches, or all batches.

**Catastrophic rollback (Mac Studio failure during sprint):**
- Restore from backup taken in Safety section
- Provision Hetzner per ADR-003 Phase 0 as emergency (accelerated)
- Replay A3 batches that were lost from the work-log (entity IDs are recorded)
- Lost work: ~1 day of Kings promotions. Everything else is recoverable.

No change in this sprint requires rolling back a previous phase. All work is additive.

---

## What this sprint is NOT

To keep scope honest:

- **Hook-based CTR optimization itself.** A2 establishes measurement. Actual hook variants are a future sprint.
- **Browser extension, MCP distribution, Grok/X distribution, Google Dataset Search, Wikipedia integration, Worst X content.** All separate future sprints if prioritized later.
- **New vertical or language additions.** Phase 2 and Phase 4 handle those.
- **Cloudflare Workers scripts.** No Worker-level optimization. All changes at origin or edge cache config.
- **Phase 0 cloud migration.** Starts ~Day 6 of this sprint, separately documented.

---

## Day 1 execution guide (2026-04-10 morning)

This section is for the next Claude session and Claude Code on Mac Studio. It is a concrete sequence of what to do Day 1.

### Morning: pre-flight + backup (30-60 min)

1. **Verify system state:**
   ```
   bash << 'EOF'
   cd ~/agentindex
   git status
   git log --oneline -5
   uptime
   df -h /
   EOF
   ```
   - Working tree should be clean or at most have uncommitted doc additions
   - HEAD should be at least 6448583
   - Uptime stable
   - Disk space > 200 GB free (backup needs ~90 GB)

2. **Verify Mac Mini reachable:**
   ```
   bash << 'EOF'
   ping -c 3 100.115.230.106
   # Or via Tailscale hostname if preferred
   EOF
   ```

3. **Verify Claude Code works on Mac Mini:** SSH into Mac Mini (or use its terminal directly), start a Claude Code session, confirm it responds.

4. **Run the pre-sprint backup** from the Safety section above. This is the blocking step. Do not continue until backup is verified.

5. **Take 4 open decisions from ADR-003 addendum:** These are technically Phase 0 decisions but some affect Leverage Sprint A3 quality:
   - **Ollama handling:** If Ollama is used by any enrichment process, know it before A3 starts. If Buzz uses Ollama for decisions, we shouldn't break it. Grep codebase for `ollama` / `11434` references.
   - The other three (ZARQ, Workers Paid, jurisdiction table) can wait — they don't affect Leverage Sprint.

### Afternoon: A3 audit + A1 research + A2 schema (3-4 hours)

Split the afternoon by track:

**A3 audit (1-2 hours):** Claude Code on Mac Studio:
```
Dig into the agentindex codebase to find what currently defines a "King" page. 
Search for "king" or "King" in templates, rendering code, and DB schemas. Find 
the automated check that classifies an entity as King vs non-King. Document 
the complete definition in docs/architecture/kings-definition.md with:
- Required JSON-LD blocks
- FAQ minimum
- nerq:answer requirements
- Minimum content length
- Classification function location (file + line)
- Any existing degraded Kings that need repair
- Sample URLs of current Kings for manual inspection
```

**A1 research (1 hour):** Claude Code on Mac Studio:
```
Research what Apple Intelligence requires for citation. Verify our current 
robots.txt allows Applebot and Applebot-Extended with no exclusions. Check 
what Apple-specific meta tags we currently have (probably none). Sketch the 
deploy plan for tomorrow without actually deploying anything yet. Write 
findings to docs/status/leverage-sprint-day-1-a1-research.md
```

**A2 schema (1 hour):** Claude Code on Mac Studio:
```
Design the AI-to-human tracking schema. Write:
1. The ALTER TABLE statements for analytics.db requests table
2. The referer pattern matching logic
3. The user-agent pattern matching logic
4. A backfill query that can populate historical data
5. The dashboard query shapes

Do not deploy anything. Write the design to docs/status/leverage-sprint-day-1-a2-schema.md
```

### End of Day 1: commit status

Commit all the docs produced during the day:
```
bash << 'EOF'
cd ~/agentindex
git add docs/architecture/kings-definition.md
git add docs/status/leverage-sprint-day-1-*.md
git add docs/metrics/kings-candidates-*.csv  # if generated
git commit -m "leverage sprint day 1: audit + research + schema"
git push origin main
EOF
```

### Day 2 overview (preview for planning)

- A1 meta tags + schema.org enhancement + OG image generator deployment
- A2 schema migration + pattern matching deployment
- A3 pipeline build (test on 100 entities before scaling)
- Evening: first 10K batch on Mac Studio + first 1000 batch on Mac Mini (smaller to validate stability)

Detailed Day 2-6 instructions will be produced by Claude session review at end of Day 1 based on Day 1 results.

---

## Risks that remain

Honest listing of what could still go wrong:

1. **Mac Studio hardware failure during sprint.** 2-5% weekly probability. Loss: sprint work-in-progress. Backup mitigates data loss but not time.

2. **Mac Mini instability under first real load.** We haven't stressed it. Mitigation: start small, scale cautiously.

3. **Kings scaling hypothesis is wrong.** The 27K Kings → disproportionate Claude citations learning might not scale. Mitigation: measure per batch, stop if regression.

4. **Apple Intelligence doesn't bite.** Optimization is a bet, not a certainty.

5. **AI-to-human conversion is already high.** If we are already at 5%+ conversion, doubling is harder and hook optimization has smaller upside than predicted.

These are acceptable risks for the upside. None is existential.

---

*End of Leverage Sprint plan. Sprint starts 2026-04-10.*


---

# Day 2 Execution Notes (recovered from commit cba080c)

These sections were committed in `cba080c` (M5 audit work) and `120b11d` (M4b finalization) during the Day 2 afternoon execution session, but were inadvertently overwritten by the parallel sequence-revision work in commit `b969197`. They are restored here verbatim because they document important verified facts and disputed audit findings that future sessions must see.

**M4b completed in this sprint (2026-04-10):**
- Step 1: _render_localized_page_minimal fallback patch (localized_routes.py)
- Step 2: ab_test.py _HEAD patch (root / + all 4 A/B variants)
- Step 3a: Apple touch-icon generation (120, 152, 167, 180)
- Step 3b: Template sized-icon updates (agent_safety_page.html, homepage_i18n.py)
- Step 5: ETag support in PageCacheMiddleware (discovery.py)
- Step 6: Applebot in bot summary bar (flywheel_dashboard.py)
- Step 7: max-age discrepancy documented (discovery.py comment)
- Step 8: Duplicate index cleanup (DROP INDEX idx_requests_ts, 582 MB recovered)

**M4b deferred to M4c (follow-up milestone):**
- Step 4: OG image generator — on-demand Pillow with Cloudflare caching
  OR fallback plan with 10 static grade PNGs + entity template integration.
  Not generated today because template integration requires grade mapping
  at render time and deserves its own commit cycle.

**M4c — A1 Apple Intelligence visual differentiation and classification.**
Follow-up milestone for work identified during M4b but deferred for
scope and safety. Target: run after M5 (A3-Measure) completes, or
interleaved with Day 3 work.

M4c deliverables:

1. OG image generator. Choose between per-entity dynamic Pillow
   generation (preferred if Mac Studio memory allows) or 10 static
   grade PNGs (safer fallback). Per-entity design is in
   docs/status/leverage-sprint-day-2-m4b-audit.md Step 4. Includes
   route /og/{slug}.png, template updates, Cloudflare 7-day cache,
   memory monitoring.

2. Apple touch-icon size variants as standalone files. Currently
   M4b batch 1 generated 4 PNGs pointing from all templates, but
   nothing special per-context. M4c may want high-res source
   (1024px) pre-generated if we ever need apple-touch-icon-precomposed.

3. Applebot reclassification from search bot to AI Indexing. Currently
   bot_name='Apple' has is_ai_bot=0 (search bot category) which
   excludes it from both AI Citations and AI Indexing dashboard cards.
   Given Applebot powers Apple Intelligence (Siri, Spotlight, Safari
   Suggestions), it should be reclassified as is_ai_bot=1 and added
   to the AI Indexing SQL filter in flywheel_dashboard.py alongside
   GPTBot. Scope: analytics.py bot mapping, backfill of ~1.5M existing
   rows, flywheel_dashboard.py query updates, cache regeneration.
   Risk: retroactive dashboard semantic change, historical charts will
   show different numbers. Priority: lower than M5 but should be
   resolved before any stakeholder reporting.

## M4b Open Questions (carried forward)

1. **Cloudflare Browser Cache TTL (resolved):** Accept as-is. 14400s
   (4h) browser cache is reasonable for a site where trust scores
   change daily. Code's max-age=300 is effectively dead code and is
   now documented as such in discovery.py:263.

2. **OG image fonts:** DM Serif Display and DM Sans not installed.
   M4c decision: download to static/fonts/ for branded cards, or
   use system Helvetica as default.

3. **OG image strategy:** Fallback plan (10 static grade images) is
   safer for Mac Studio memory pressure but less differentiated.
   Per-entity dynamic generation is more valuable for social sharing
   but requires capacity validation. M4c decision.

4. **Applebot classification:** Reclassify as AI Indexing (see M4c
   deliverable 3). Not done in M4b because retroactive dashboard
   semantic change deserves its own commit cycle and deeper audit
   of all is_ai_bot=1 queries in flywheel_dashboard.py.

5. **VACUUM timing:** Not performed. DROP INDEX idx_requests_ts was
   sufficient; SQLite reuses freed pages naturally.

6. **Redis cache flush after deploy:** Performed via Python-based
   iteration (17,062 pc:* keys deleted) — xargs failed on keys with
   quoted characters. Python redis-py library handles binary safely.

**M5 — A3-Measure built on top of A2 infrastructure.**
Extend citation_tracker.py or flywheel_dashboard.py with a Kings vs non-Kings split. Produce query output showing: AI bot crawl rate per page per day for Kings, same for non-Kings, broken down by bot source (ClaudeBot, GPTBot, PerplexityBot, Applebot, others), AI-attributed human visits per Kings vs non-Kings page once A2 is live. The panel or query should produce a simple numerical comparison that can be read at a glance. M5 depends on M3 (A2) being at least partially complete so the ai_source column exists. M5 runs on Mac Studio.

**M6 — A3-Fix runs on Mac Studio while Mac Mini validates in parallel.**
Mac Studio writes repairs to primary Postgres throttled to approximately 100 updates per second to protect serving capacity. Mac Mini reads from replica and fetches production URLs to run an HTML-level validator: does the page render the 5 king_sections correctly, is the ItemList JSON-LD present when is_king is true, is the nerq:answer meta tag populated, are the sacred elements intact. Mac Mini output is a report of Kings that are database-marked as is_king=true but HTML-degraded. Mac Studio fix categories: 225 Kings with broken descriptions, 28 Kings with trust_score below 30 (decision per entity: fix score or demote), country Kings bug (all 158 at 48.2 — investigate and either fix or document as limitation), dimensions column populated where underlying data exists. Deliverable: scripts/validate_kings.py as reproducible validator, a report of fix outcomes, and a count of how many Kings now pass full validation.

**M7 — A3-Gate central promote_to_king() function.**
Single function with explicit, auditable rules derived from the validator built in M6. Takes an entity ID and a reason string, validates that the entity meets central Kings criteria, either promotes or rejects with a logged reason. Unit tests covering edge cases. Not wired into existing crawlers yet — they continue to use their independent logic. Future sprint will migrate crawlers to the central function. M7 output: the function, its tests, a one-page ADR snippet describing the rules as authoritative source.

**Decision checkpoint (after M5 has collected ~5-7 days of data):**
Review A3-Measure data. If Kings show materially higher AI bot crawl rates or higher AI-attributed human traffic than comparable non-Kings, A3-Scale proceeds. If the data is ambiguous or shows no difference, wait longer — even if it costs coordination overhead with Phase 0. Statistical sufficiency matters more than the schedule. Anders makes this call with data in hand, not Claude Code autonomously.

**M8 — A3-Scale, gated on decision checkpoint.**
If decision is go: Mac Mini takes the A3-Scale worker role. She calls promote_to_king() via Tailscale against primary Postgres in aggressive parallelism. Target: 500K Kings as the original ambition. Rate: start conservative (~5K per day), scale up based on Mac Studio load, Postgres pool health, and Mac Mini's own capacity. Stress test Mac Mini in the process — push until we find her ceiling. This is secondary goal data for Phase 0 planning. Runs in background for weeks, coordinating with Phase 0 cutover (pause during pg_dump, pause during cutover, resume after). If decision is wait or no-go: M8 does not start, sprint ends after M7, resources redirect to deeper A1 or A2 work.


## Track A1 — Apple Intelligence optimization details

**Hypothesis:** Applebot is already 37% of bot traffic per the 2026-04-09 baseline. No Apple-specific optimization has been done. Apple Intelligence is rolling out across ~1.5 billion devices and its citation patterns are still being established. Early optimization may establish Nerq as a preferred source in a way that is harder to displace later.

**Deliverables:**

1. robots.txt verification that Applebot and Applebot-Extended are explicitly allowed with no conflicting rules.

2. Apple-specific meta tags on entity pages and /best/ pages: apple-mobile-web-app-capable, apple-mobile-web-app-status-bar-style, apple-mobile-web-app-title, apple-touch-icon in sizes 120 180 152 167, format-detection.

3. Open Graph image generation for iMessage link previews, on-demand with aggressive Cloudflare caching. Size 1200x630 standard plus 1200x900 Apple-optimized variant. Generated from trust score, entity name, category. Same render-on-demand pattern as ADR-003.

4. Schema.org SoftwareApplication enhancements: applicationCategory explicit per vertical, operatingSystem where known, softwareVersion where known, offers block even for free software, aggregateRating populated from trust score.

5. Performance improvements Applebot responds to: cache headers explicit with max-age and s-maxage, no unnecessary redirects, gzip and brotli compression verified. Mac Studio TTFB may remain above Apple preferred threshold regardless — document the number, accept that Phase 0 cloud migration addresses it further.

6. Apple News RSS feed investigation. Submit to Apple News if Nerq qualifies as publisher. If not (Apple News has strict publisher requirements), document why and move on. Do not fake publisher status.

7. Applebot analytics panel in the existing flywheel or analytics dashboard. Daily request volume, top requested paths, week-over-week crawl frequency change, Safari referrer patterns if any appear.

**Done criteria:** robots.txt verified, meta tags deployed and rendering in production, OG image generation live and Cloudflare-cached, Schema.org enhancements in place without sacred bytes drift, TTFB measurements captured from Mac Studio and Mac Mini as two vantage points, Apple News RSS submitted or documented as inapplicable, analytics panel live with baseline plus 7-day trend.

**Success indicators (measured 4 weeks after sprint):** Applebot request volume increases above baseline 513K per day, Safari referrer patterns appear in human traffic, Apple News subscribers above zero if submitted. None are guaranteed. Apple Intelligence is a black box. This track is a calibrated bet.

**Risks:** Opaque Apple Intelligence means we may do everything right and see nothing for months. Mitigation: improvements are defensible regardless of Apple response. OG image generation at scale could consume compute — mitigation is on-demand with Cloudflare caching, not pre-render. Schema.org changes risk breaking sacred elements — golden file tests must pass before and after.

**Rollback:** All meta tags are additive, revert commits to remove. OG image generation behind a feature flag. Schema.org changes in code, revertible. No database changes.

## Track A2 — AI-to-human conversion tracking details

**Hypothesis:** Current AI-to-human conversion rate is unknown. Baseline shows roughly 515K daily AI citation requests and 43K daily human visits. If 20% of human traffic comes from AI citations (assumption), that is about 8.6K humans from 515K AI requests equal to ~1.7% conversion. Doubling this via hook optimization would add 8-9K humans per day. But we cannot optimize without measurement. A2 also provides the infrastructure that A3-Measure depends on.

**Deliverables:**

1. Referer pattern matching for AI sources: claude.ai to Claude, chat.openai.com and chatgpt.com to ChatGPT, perplexity.ai to Perplexity, copilot.microsoft.com and bing.com/chat to Copilot, gemini.google.com to Gemini, grok.x.ai and x.com/i/grok to Grok, duckduckgo.com with AI parameters to DuckAssist, kagi.com to Kagi. Accept that some AI products strip referers — track what we can.

2. User-Agent pattern matching for AI-browsing clients: ChatGPT-User, Claude-User, Perplexity-User. These appear as humans in bot detection but are tracked as a third category ai_mediated.

3. Database schema additions in analytics.db requests table: ai_source nullable text column, visitor_type text column with constraint of bot, human, or ai_mediated. Index on (ai_source, ts). Backfill from existing data where referer was already captured.

4. Attribution logic. A visit counts as AI-attributed if ANY of: referer matches AI domain patterns, user-agent matches AI-User patterns, or within 5 minutes of a known AI bot crawl of the same URL (timing correlation, weaker signal).

5. Dashboard additions: conversion rate overall and per AI source, top URLs by AI-attributed visits, language breakdown, vertical breakdown, time-of-day patterns, weekly trend.

6. Baseline measurement document written after 7 days of tracking as reference point for future comparison. Committed to docs/metrics/ai-to-human-baseline-2026-04-17.md or similar dated filename.

7. Export API endpoint returning conversion data in a stable format for future A/B testing of hook variants.

**Done criteria:** Pattern matching deployed in request logging path, schema migrated and new columns populated for new requests, backfill complete where possible, dashboard panels live and populated with plausible data for at least 5 AI sources, baseline measurement initiated.

**Success indicators:** Dashboard shows non-zero conversion data that looks plausible, at least 5 AI sources identifiable, baseline differs from zero (we are getting AI-attributed humans, just not measuring them before this track).

**Risks:** AI products strip referers and we will undercount — document methodology so future measurements are comparable to the same flawed methodology. User-Agent patterns change over time — log unknown patterns for manual review. Backfill may be incomplete if old logs do not store referer consistently.

**Rollback:** Schema changes are additive, columns can be dropped without affecting production. Dashboard panels are read-only. No risk to serving traffic.

## Track A3 — Kings in four phases details

Four phases executed in sequence. Each phase has its own deliverables, done criteria, and risks. The sequence is Measure, Fix, Gate, Scale. A3-Scale is gated on A3-Measure results per ADR-003 Addendum #4.

### A3-Measure (highest priority within A3)

**Purpose:** Test the hypothesis that Kings receive more AI citations than non-Kings before investing in scaling.

**Deliverables:** Extension to citation_tracker.py or a new query in flywheel_dashboard.py producing Kings vs non-Kings split of AI bot crawl rate per page per day, broken down by bot source (ClaudeBot, GPTBot, PerplexityBot, Applebot, others), plus AI-attributed human visits per page per day for Kings vs non-Kings once A2 data is flowing. Output is a numerical comparison that Anders and Claude session can read at a glance and judge.

**Methodology note:** The comparison must be per page, not total. Kings are a small percentage of total indexable pages, so total counts favor non-Kings trivially. The measurement is about yield per page. Kings versus a matched sample of non-Kings in the same registries and trust score ranges would be ideal if feasible.

**Done criteria:** Measurement query or panel is live and producing data. Data is collected for at least 5-7 days before any scaling decision. The measurement is reproducible on demand.

**Decision trigger:** After 5-7 days of collected data, review. If Kings show materially higher AI bot crawls or higher AI-attributed traffic per page than non-Kings, A3-Scale gets go-ahead. If the data is tight, ambiguous, or shows no difference, wait for more data even if it costs Phase 0 coordination overhead. Statistical sufficiency matters more than schedule.

### A3-Fix

**Purpose:** Repair the 37,688 existing Kings to meet defined quality before any scaling. Fixing is worthwhile independent of the hypothesis because it improves content quality universally.

**Deliverables:**

1. Zero Kings with NULL, empty, or sub-10-character descriptions. Currently 225. Repair the description or demote to non-King if the underlying data is truly missing.

2. Zero Kings with trust_score below 30. Currently 28. Either fix the score via re-scoring or demote. Per-entity decision.

3. Country Kings scoring bug investigation. All 158 countries share trust_score 48.2 which is almost certainly a bug. Either fix the scoring function or document as known limitation and demote countries from King status until fixable.

4. Dimensions column populated for as many Kings as possible. Currently only 275 of 37,688 (0.7%). If the underlying dimension data exists elsewhere in the database, populate. If it does not exist for certain registries, accept lower coverage and document which registries cannot be fully populated.

5. scripts/validate_kings.py as reproducible validator that checks each King against the full quality bar and reports failures by category. Can be run ad hoc after the sprint and during Phase 0 to verify no regressions.

6. HTML-level validation report from Mac Mini listing Kings that are database-marked is_king=true but whose rendered HTML is missing king_sections, the ItemList JSON-LD, the nerq:answer meta tag, or sacred elements.

**Done criteria:** All four numeric targets hit (or documented as unachievable with reason). Validator script committed and run successfully against full Kings set. HTML-level report reviewed, any HTML-level failures fixed.

**Throttling:** All writes to primary Postgres throttled to approximately 100 row updates per second to protect serving capacity. If A3-Fix takes 6 hours instead of 1 hour because of throttling, that is the correct trade.

**Compute split:** Mac Studio writes fixes. Mac Mini reads from replica and fetches production URLs to run validator in parallel. Mac Mini does not write to primary during A3-Fix.

### A3-Gate

**Purpose:** Build the central promote_to_king function that replaces scattered per-crawler logic. Future promotions go through this function. Existing crawlers are not migrated in this sprint — that is a follow-up task.

**Deliverables:**

1. promote_to_king(entity_id, reason) function that validates entity against central Kings criteria (derived from A3-Fix validator) and either promotes or rejects with logged reason.

2. Unit tests covering edge cases: already-King entity, entity missing required fields, entity with borderline trust score, entity in registry with special rules.

3. Documentation snippet added to docs/architecture/kings-definition.md or a new docs/architecture/kings-gate.md describing the rules as authoritative source.

4. Audit log table or extension to existing logs recording every promotion and rejection decision with timestamp and reason string.

**Done criteria:** Function committed with tests passing. Documentation reflects the rules. Dry-run test against a sample of existing Kings verifies the function would accept most and identifies any it would reject (informative audit).

**Not in scope for this sprint:** Migrating existing crawlers to use promote_to_king. They keep their independent logic. Only new promotions via A3-Scale use the function.

### A3-Scale (gated, conditional on A3-Measure decision checkpoint)

**Purpose:** If A3-Measure validates the hypothesis, systematically scale Kings toward the 500K ambition using the A3-Gate function. Mac Mini is the primary worker for this phase.

**Deliverables (only if decision checkpoint is go):**

1. Candidate selection query that ranks non-King entities by a composite score across analytics traffic, entity popularity, category coverage, and language potential. Output: ranked list of candidates committed to docs/metrics/kings-candidates-YYYY-MM-DD.csv.

2. Mac Mini worker script that reads candidates, calls promote_to_king via Tailscale against Mac Studio primary, logs results. Respects a work-log file to enable pause and resume. Coordinates with Phase 0 via pause signals.

3. Monitoring: Claude citation rate per batch measured via A3-Measure panel. Sacred bytes drift = 0 check after every batch via golden file tests. Mac Studio Postgres pool health monitored — if pool exhaustion approaches, throttle Mac Mini worker.

4. Stress test data: Mac Mini CPU, RAM, network, and Postgres client connection observations documented as secondary output. This data feeds Phase 0 planning about Mac Mini's capacity in its future role.

**Rate:** Start conservative at about 5K promotions per day. Scale up based on Mac Studio load and Mac Mini ceiling. No hard upper bound on parallelism from Mac Mini — we are explicitly trying to find her ceiling.

**Pause rules:** Mac Mini worker pauses during Phase 0 pg_dump (estimated 30 minutes), during Postgres transfer (estimated 8-14 hours), during cutover (estimated 24 hours). Resumes after each phase from the work-log position.

**Target:** 500K Kings as the original ambition. Reaching 500K is not the sprint success criterion — running the scaling with measurement oversight is.

**Done criteria (active sprint phase):** Candidate list generated, Mac Mini worker deployed and running, first 10K promotions completed with zero sacred bytes drift, A3-Measure data updated to show post-scaling effect, Mac Mini capacity observations logged.

**Done criteria (background phase after active sprint ends):** Scaling continues into Phase 0 background with pause coordination. Reaches 500K when it reaches it, or stops earlier if A3-Measure data shows the effect reversing or flattening.

## Compute allocation

**Mac Studio (primary, production server, write authority):**

- All A1 Apple deliverables (production code deploy)
- All A2 deliverables (schema migration on analytics.db, which lives only on Mac Studio)
- A3-Measure query development and deployment (reads analytics.db + Postgres, writes to dashboard)
- A3-Fix writes to primary Postgres, throttled to ~100 updates per second
- A3-Gate function development and testing
- Serving production traffic (unchanged)
- Buzz running in her degraded state (unchanged, do not touch)

**Mac Mini (replica, aggressive utilization, read-heavy first then write-worker for A3-Scale):**

Phase 1 (during A3-Measure and A3-Fix):
- HTML-level validator running against production URLs for every Kings entity
- TTFB measurements for A1 against 10K entity URLs as second vantage point
- A2 backfill queries reading from analytics.db if replication exists, otherwise standby
- Stress test: push her hard, record CPU, RAM, network, disk, Postgres client load, find the ceiling

Phase 2 (during A3-Scale, gated on measurement checkpoint):
- Primary A3-Scale worker. Calls promote_to_king() via Tailscale against Mac Studio primary.
- Aggressive parallelism — as many concurrent promotions as she can handle without saturating Mac Studio Postgres pool.
- Continues stress test observations — this data informs Phase 0 planning.

Mac Mini does NOT: run the A3-Gate function definition, promote Kings using logic other than calling the central function, modify OPERATIONSPLAN.md, touch Buzz, serve production traffic.

**Why asymmetric:** Mac Studio is load-sensitive (serving production, 95% RAM pressure, running Buzz). Mac Mini has no other responsibilities. We push Mac Mini hard to learn her ceiling and to use capacity that would otherwise sit idle. We protect Mac Studio carefully.

## Coordination with Phase 0

Phase 0 cloud migration starts approximately 2026-04-15, which is during or after the active phase of Leverage Sprint depending on Anders's pace. Coordination rules:

**Before Phase 0 starts:** Leverage Sprint A1, A2, A3-Measure, A3-Fix, A3-Gate are active on Mac Studio and Mac Mini without Phase 0 interference.

**During Phase 0 provisioning (Week 1 of Phase 0):** Mac Studio is busy with Hetzner provisioning and Postgres preparation. Mac Studio Leverage Sprint work slows or pauses. Mac Mini continues.

**During pg_dump (estimated 30 minutes):** Both machines pause writes to primary Postgres. Mac Mini A3-Scale worker pauses via work-log pause signal. Mac Studio A3-Fix pauses.

**During Postgres transfer (estimated 8-14 hours):** Both machines paused on writes. Mac Mini can continue validator reads and TTFB measurements (read-only). Mac Studio continues serving traffic unchanged.

**During cutover (estimated 24 hours):** Full pause on Leverage Sprint write activity. Sacred bytes drift verification via golden file tests runs on the new Hetzner primary before Mac Mini A3-Scale worker is allowed to resume.

**After cutover (Hetzner is primary):** Mac Mini A3-Scale worker resumes, now writing to Hetzner primary via Tailscale instead of Mac Studio primary. Work-log picks up from last position. Mac Studio can continue as Leverage Sprint accelerator or be repurposed, depending on what Phase 0 decides for its role.

## Success criteria

Sprint is successful if the following hold at end of active phase (regardless of A3-Scale decision):

1. Pre-sprint backup was taken and verified. (Already done on Day 1.)
2. Ollama-Buzz discovery documented and not acted on prematurely. (Already done.)
3. kings-definition.md audit document committed with corrections applied.
4. ADR-003 Addendum #4 committed as authoritative source for A3 structure.
5. A2 AI-to-human conversion tracking deployed, producing data for at least 5 AI sources.
6. A1 Apple optimization deployed: meta tags live, OG image generation active, Schema.org enhanced, analytics panel showing Applebot separately.
7. A3-Measure query or panel built and collecting data.
8. A3-Fix completed or explicitly deferred for specific items with documented reasons. scripts/validate_kings.py committed.
9. A3-Gate promote_to_king() function committed with tests.
10. Mac Mini stress test data collected: observed ceiling for sustained read workload, observed ceiling for any write workload that happens during A3-Scale.
11. Decision checkpoint on A3-Scale reached with explicit documented decision (go, wait, or no-go).
12. Sacred bytes drift = 0 throughout all deployments.
13. No regressions in existing AI citation rates or human traffic.
14. Retrospective document covering what worked, what did not, what surprised us.

If criteria 11 results in go, A3-Scale runs in background and the 500K target is pursued. If criteria 11 results in wait, measurement continues and go decision is deferred. If criteria 11 results in no-go, sprint ends at M7 and resources redirect per ADR-003 Addendum #4.

## Risks

**Top risk: Kings hypothesis might not hold.** A3-Measure exists specifically to test this risk. Cost of discovering "Kings do not outperform non-Kings" is the A3-Measure and A3-Fix investment, which is recoverable regardless (fixes improve quality, measurement infrastructure is reused for hooks).

**Mac Studio hardware failure during sprint.** 2-5% per week. Loss: work in progress. Backup taken on Day 1 mitigates data loss. Time loss is unrecoverable.

**Mac Mini instability under first real load.** She has not run production work. Mitigation: start at moderate load for stress test, scale up gradually, monitor. A crash is acceptable learning — she is not in critical path until A3-Scale.

**Apple Intelligence does not bite.** A1 is a calibrated bet. Mitigation: improvements are defensible regardless of Apple response.

**AI products strip referers.** A2 will undercount. Mitigation: document methodology, compare future measurements to same methodology.

**Postgres autovacuum never ran on large tables.** Statistics are stale. Could cause planner issues. Mitigation: run ANALYZE on agents, entity_lookup, agent_jurisdiction_status at some point during sprint (low priority, not blocking).

## Rollback procedures

Each track has independent rollback:

**A1 rollback:** Revert commits. OG image generation behind feature flag. Schema.org changes in code.

**A2 rollback:** Schema columns can be dropped without affecting production. Dashboard panels are read-only.

**A3-Fix rollback per batch:** Fix scripts should record pre-state for rollback. If a fix introduces problems, revert specific rows.

**A3-Gate rollback:** promote_to_king() function is new code, not wired into existing crawlers. Can be removed without impact.

**A3-Scale rollback per batch:** UPDATE software_registry SET is_king = false WHERE entity_id IN (batch_list). Does not affect underlying entity data.

**Catastrophic rollback (Mac Studio failure during sprint):** Restore from 2026-04-10 backup. Provision Hetzner per ADR-003 Phase 0 as emergency acceleration. Lost work is the sprint deliverables themselves, not underlying data.

## What this sprint is NOT

To keep scope honest:

- Not hook-based CTR optimization. A2 establishes measurement, hook variants are a future sprint.
- Not browser extension, MCP distribution, Grok/X distribution, Google Dataset Search, Wikipedia integration. Those are separate future sprints.
- Not new verticals or language additions. Phase 2 and Phase 4 handle those.
- Not Cloudflare Workers scripts. No Worker-level optimization.
- Not Phase 0 cloud migration. That starts approximately 2026-04-15 separately.
- Not fixing Buzz. Ollama-Buzz decision deferred to Phase 0 window per 2026-04-10 discovery document.
- Not unconditionally scaling Kings to 500K. Scaling is gated on measurement per ADR-003 Addendum #4.

## References

- docs/adr/ADR-003-cloud-native-expansion-first.md
- docs/adr/ADR-003-addendum-baseline-discoveries.md
- docs/adr/ADR-003-addendum-2-claude-code-local.md
- docs/adr/ADR-003-addendum-3-sequence-revision.md
- docs/adr/ADR-003-addendum-4-leverage-sprint-pivot.md (authoritative for A3 structure)
- docs/strategy/phase-0-cloud-migration-plan.md
- docs/architecture/kings-definition.md (with corrections pending in M2)
- docs/status/2026-04-10-ollama-buzz-discovery.md
- docs/buzz-context.md
- docs/session-handoff-2026-04-10-morning.md (now superseded by this file and Addendum #4 for sprint structure)
- ~/nerq-baselines/2026-04-09-pre-migration/
- ~/nerq-backups/2026-04-10-pre-leverage-sprint/

---

*End of Leverage Sprint plan. Rewritten 2026-04-10 after Day 1 audit revealed Kings hypothesis unverified. Sprint is measurement-first, quality-first, scaling-last.*


---



## M5 Audit Status — DISPUTED (2026-04-10 afternoon)

An M5 audit was produced by Claude Code at docs/status/leverage-sprint-day-2-m5-audit.md (766 lines). During review, spot-check verification against the Postgres agentindex database revealed that **two of five key findings contained factual errors**:

1. **Finding 1** (5.8x Kings/non-Kings citation ratio) was claimed as a cross-registry score-controlled comparison. Verification showed the ratio comes from a single registry (npm). Only 1 registry (npm) has balanced Kings and non-Kings in the 80-100 trust score band. Two other registries in that band (pypi, vpn) have zero non-Kings.

2. **Finding 3** (ai_tool Kings underperform due to 100% selection) was based on a false premise. ai_tool is 34% Kings and 66% non-Kings, not "all seeded entities get is_king=true" as the audit claimed.

**Crawl bias finding (Finding 2) was CONFIRMED and is stronger than the audit stated.** auto_indexnow.py structurally protects Kings from LIMIT cutoff AND applies a 6-language multiplier loop to the Kings-dominated slug list. Kings are guaranteed 6x more IndexNow submissions than non-Kings, independent of any "AI preference."

**Do not proceed with M6 (A3-Fix), M7 (A3-Gate), or M8 (A3-Scale) based on the M5 audit summary as originally written.**

The full discrepancy analysis is in docs/status/leverage-sprint-day-2-m5-verification-notes.md. Next M5 session must start by reading that file.

**Revised M5 plan:**
- M5.1: Design controlled experiment (remove Kings prioritization from auto_indexnow.py for 7-14 days)
- M5.2: Collect unbiased citation data
- M5.3: Re-measure with corrected understanding (single-registry limitation acknowledged)
- M5.4: Draft ADR-005 decision framework (do not conclude until unbiased data exists)

**What we know definitively after 2026-04-10 verification:**
- Crawl bias is structural and confirmed (auto_indexnow.py:347-354)
- npm has 400 Kings + 3,110 non-Kings in 80-100 trust score band — only balanced registry
- 4 registries have 100% or near-100% Kings (vpn, country, charity, crypto) — not measurable
- 4 registries have 0 Kings — cannot test hypothesis at all
- The Kings hypothesis may still be directionally correct, but current evidence is insufficient

**Decision deferred:** Kings hypothesis validity. Target resolution: next M5 session with corrected methodology.
