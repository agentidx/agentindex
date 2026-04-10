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
