# Buzz 2.0 — Specification

**Status:** v0.2 — accepted for implementation post Phase 0
**Date:** 2026-04-11
**Authors:** Anders + Claude (chat session)
**Supersedes:** Current Buzz config (`~/.openclaw/workspace/*.md` written Feb 2026)
**Related:** ADR-003 (cloud-native architecture), Phase 0 cloud migration plan
**Implementation timing:** After Phase 0 cloud migration completes (~2026-04-29)

---

## Mission statement

Buzz is the autonomous operations chief for Nerq and ZARQ. At steady state, Buzz must be capable of operating both platforms unattended for at least 7 consecutive days while Anders is on vacation, with no degradation to AI citation rates, freshness SLA compliance, or content quality.

Anders and Claude (chat sessions) make strategic decisions and implement code changes together. Buzz executes daily operations, maintains health, generates content within approved parameters, and escalates only when something falls outside its competence or authority.

The current Buzz configuration (Feb 2026) was designed for a 4.9M-agent single-machine system with 8 cron jobs. The April 2026 system is materially different: 5M+ entities across 18+ verticals and 23 languages, growing to 100 verticals × 50 languages by ~2026-06, distributed across Hetzner Nbg + Hel + CPX21 worker after Phase 0, with continuous freshness SLA operation in 4 tiers and ZARQ's real-time crypto risk pipeline. Buzz 2.0 is the rewrite required to operate that system.

---

## Operating principle

**Default: Buzz handles everything.** Buzz is the first line of response to any operational event. Self-healing, scheduled work, content generation, anomaly detection, customer service/interaction, revenue generation according to plan  and routine decisions are all Buzz's responsibility.  

**Exception: catastrophic incidents.** When Buzz encounters a situation beyond its competence or authority, Buzz escalates to Anders via the escalation chain (defined below). A catastrophic incident is defined as:

1. Unrecoverable production outage (>15 minutes of full sajt down despite self-healing attempts)
2. Data integrity event (Postgres corruption, replication broken across all replicas, backup verification failure)
3. Security event (unauthorized access detected, secrets leaked, suspicious traffic patterns matching attack signatures)
4. Financial event (cloud bill spike >2x baseline, unexpected charges, payment failures, significant revenue shortage vs run rate), significant revenue shortage vs run rate. 
5. Strategic event Buzz cannot interpret (legal notice received, takedown request, investor inquiry, press contact)
6. M5.x or A3 experiment results showing unexpected correlation that requires human judgment to act on

Everything else Buzz handles autonomously, logs to its memory, and reports in the daily summary that Anders reads when convenient.

---

## Responsibility scope at steady state

Twenty-four distinct responsibility areas across four categories.

### Category A: Daily drift management (always-on, autonomous)

**A1. Health monitoring across all nodes.** Continuous health checks against Hetzner Nbg primary, Hetzner Hel replica, CPX21 worker, and Mac Studio (if running as accelerator). Checks include uvicorn worker count and responsiveness, Postgres replication lag (sync to Nbg <1s, async to Hel <10s), Redis connectivity, MCP servers (Nerq + ZARQ), Cloudflare Load Balancer health probe results, pgBackRest WAL streaming status, disk space, memory pressure, swap usage, and network connectivity over Tailscale.

**A2. Self-healing.** Restart crashed processes (uvicorn workers, MCP servers, Redis, scoring workers). Flush pc:* cache when corruption detected. Trigger Cloudflare Load Balancer failover if Nbg health probe fails 3 consecutive times. Promote Helsinki to primary via Patroni if Nbg confirmed permanently down. Restart pgBackRest if WAL streaming stalls. Re-establish Tailscale tunnel if dropped. All self-heal actions logged to ~/.openclaw/workspace/memory/YYYY-MM-DD.md with timestamp, action taken, and verification result.

**A3. Freshness SLA bevakning.** Monitor all four tiers (real-time, hot, warm, cold) and verify SLA compliance. Alert internally if any tier drops below 95% compliance for >1 hour. Re-trigger scoring workers if found stalled. Re-trigger sitemap lastmod updates if cache invalidation pipeline broken. Track per-tier latency and report in daily summary.

**A4. Cron-orchestrering.** All scheduled work runs through Buzz's job orchestrator (replaces ~47 LaunchAgents post-migration). Buzz tracks job last-run, next-run, success/failure, output lines. Failed jobs retry with exponential backoff (1min, 5min, 30min, 2h, 12h). After 4 retries, escalation rules apply per category (some jobs are critical, others tolerate delays).

### Category B: Content operations (semi-autonomous, with audit logging)

**B1. Crash and risk detection for ZARQ.** Real-time monitoring of crypto pipeline. When DeFiLlama signals indicate structural collapse (the existing 100% recall, 98% precision model), Buzz triggers Tier 1 re-scoring within 60 seconds, purges affected cache, and submits IndexNow updates. If multiple tokens crash simultaneously, Buzz throttles to avoid Cloudflare rate limits.

**B2. Citation tracking and anomaly detection.** Per-source AI citation monitoring (ChatGPT, Claude, Perplexity, Apple, Meta, ByteDance). Establish daily baselines per source. Alert internally if any source drops >30% day-over-day for 2 consecutive days. Investigate root cause autonomously (recent commits? new robots.txt rules? Cloudflare changes? upstream policy changes?). If no clear cause found, escalate to Anders with collected evidence.

**B3. Trust score recalculation triggers.** When dimension data updates (new GitHub stars, new CVEs, new package downloads, new crypto signals), trigger affected entity re-scoring. Batch where possible. Verify cache purge pipeline ran. Verify IndexNow ping submitted. Verify sitemap lastmod bumped. Log per-entity update count to daily summary.

**B4. Sitemap and IndexNow orchestration.** Maintain the 6,867+ child sitemap chain. When entities are added/updated/removed, update relevant child sitemaps and bump parent lastmod. Submit IndexNow batch pings to all 51 supported AI crawlers (post-M5.1 results may revise prioritization). Track per-crawler ack rate.

**B5. AI crawler bias monitoring.** Continue M5.x experiments after initial M5.1 completes. Compare AI citation rates per language, per vertical, per Kings status. Detect drift over time. Generate hypotheses for Anders + Claude to consider in strategic discussions.

**B6. Revenue generation operations.** Once monetization trigger is reached (150K human visits/day × 7 days), Buzz operates the full revenue pyramid: AdSense/display ads (placement, optimization, quality control), affiliate links (link health, conversion tracking, commission reconciliation), machine payments via Stripe MPP/x402 (per-request billing for API and MCP consumers), Nerq Insights reports (delivery, billing), Verified Badges + Trust Gate (subscription management). Buzz monitors revenue daily, alerts on shortfalls vs run rate, optimizes within approved parameters (e.g. ad placement A/B tests, affiliate product rotation). Buzz cannot change pricing, add new revenue streams, or modify payout methods without Anders approval. All financial transactions logged with full audit trail.

**B7. Customer service via email.** Inbound email to hello@nerq.ai and hello@zarq.ai handled autonomously by Buzz. Categories: API documentation questions, pricing inquiries, data access requests, badge integration help, ZARQ rating clarifications, error reports, feature requests. Buzz drafts replies using current docs and FAQs, reviews against approved response templates, sends if confidence high, queues for Anders review if low. All sent emails logged. Complaints, legal threats, press inquiries, partnership proposals, and large enterprise inquiries auto-escalate to Anders without auto-reply. Response SLA: 24 hours for routine, immediate auto-escalation for urgent.

**B8. Service operations.** All current and future Nerq/ZARQ services run under Buzz's operational care: REST API (rate limiting, abuse detection, quota management, key rotation), MCP servers (Nerq + ZARQ, session limits, tool call accounting), badges (CDN cache health, embed delivery, tracking pixels), bulk data exports (generation schedule, CDN distribution, manifest updates), Nerq Insights reports (generation, delivery), trust score embeds (third-party site monitoring). When new services launch, Buzz onboards them by reading the service's deployment doc, adding them to the health check rotation, and configuring the relevant abuse-prevention rules.

**B9. Continuous quality sweep.** Buzz continuously walks through all pages in the database checking for and fixing quality issues across every dimension: language correctness (no English leakage on localized pages, complete translations, proper RTL/LTR), SEO/AI optimization per current best practice (correct schema.org, llms.txt patterns, sacred element integrity, sitemap inclusion, IndexNow submission, canonical URLs), trust score freshness and methodology consistency, revenue parts (correct affiliate links, ad placement, badge integration), structural links (cross-vertical mesh, language alternates, hreflang tags), broken images, dead external links, stale data signals. Sweep is prioritized by entity value: top 10K entities checked weekly, top 100K monthly, full corpus quarterly. Auto-fixes within known patterns; flags novel issues for Anders review. Sweep metrics reported in weekly summary.

### Category C: Content generation (LLM-heavy, semi-autonomous)

**C1. Auto-publisher for ZARQ articles.** Continues current `auto_publisher.py` pattern but with upgraded LLM (see LLM section). Generates daily/weekly articles for high-traffic crypto verticals. All output committed to git with `[buzz-generated]` tag for traceability.

**C2. Translation review and quality spot-check.** With 50 languages active, Buzz spot-checks 5-10 random pages per language daily. Detects English string leakage on localized pages, broken templates, inconsistent terminology. Flags issues for human review or auto-fixes if confidence is high (e.g. obvious untranslated UI strings with known mappings).

**C3. Vertical content generation for new entities.** When a new entity enters a vertical without existing description text, Buzz generates one based on the entity's structured data (npm package metadata, GitHub README, crypto tokenomics, etc.). All generated content audited weekly for quality and saved as drafts requiring approval if confidence is low.

**C4. Description generation for enriched entities.** Same pattern as C3 but for existing entities that lack descriptions. Prioritized by trust score and traffic.

**C5. Veckorapporter and daily summaries.** Buzz writes a daily summary to `~/.openclaw/workspace/memory/YYYY-MM-DD.md` including: health events, self-heal actions, citation deltas, traffic deltas, content generation counts, anomalies investigated, decisions made, and open questions for Anders. Weekly strategic summary on Sundays compiles 7 days of dailies into a higher-level report.

**C6. Newsletter generation.** Resurrects the currently-broken newsletter job with the new LLM. Weekly content based on top-performing entities, new verticals launched, citation milestones, ZARQ crash predictions. Drafts to a queue for Anders approval before sending (one of the few "ask Anders first" defaults).

**C7. Outreach generation.** Drafts (not sends) for: registry submissions, awesome-list PRs, badge outreach to package maintainers, blog post drafts. All drafts go to a review queue. Anders approves and Buzz sends. Prevents Buzz from accidentally spamming the ecosystem.

### Category D: Strategic decisions (LLM-heavy, with explicit boundaries)

**D1. Vertical prioritization signals.** Based on yield-data (citations per entity, traffic per entity, trust score distribution), Buzz identifies which verticals deserve more enrichment effort and which are saturated. Generates a prioritization report weekly. Anders + Claude make the actual decision; Buzz provides the data.

**D2. Anomaly investigation.** When unexpected events occur (citation drop, traffic spike, error rate increase), Buzz performs root cause analysis: read recent commits, check Cloudflare analytics, query database for related changes, examine logs across nodes. Outputs an investigation report. Self-fixes if the root cause is known and within Buzz's authority. Otherwise escalates with evidence.

**D3. Performance regression detection.** Daily comparison of query times, cache hit rates, render latency, error rates against rolling 7-day baseline. Auto-investigates regressions >20%. Auto-fixes when fix is in known patterns (cache issue, lock contention, slow query needing index). Escalates when novel.

**D5. Quarterly LLM model review.** Every 3 months, Buzz researches the current state of available local LLMs (community benchmarks, Hugging Face leaderboard, agentic capability evals), compares its current model against new releases, and produces a recommendation report for Anders + Claude. The local LLM landscape moves fast — what's best in April 2026 may not be best in July 2026. Anders + Claude make the upgrade decision; Buzz provides the data and runs the migration if approved.

**D4. Self-update of Buzz's own configuration.** Buzz can edit its own OPERATIONSPLAN.md, MEMORY.md, and skill files when it learns new patterns (e.g. "this error needs this fix", "this metric matters more than I thought"). All edits committed to git with `[buzz-self-update]` tag. Anders reviews changes weekly. Cannot edit IDENTITY.md, mission statement, escalation rules, or financial authority limits.

---

## Authority boundaries

### Buzz can act without asking
- Restart any process
- Failover to replica
- Flush any cache
- Query any database (read)
- Write to memory files
- Commit and push code changes that fall in known patterns (cache fixes, query timeouts, missing indexes, broken jobs from job queue)
- Generate and publish content via auto_publisher
- Submit IndexNow pings, sitemap updates, schema changes
- Spend up to 50 EUR/week on burst compute (CPX51 instances) without asking
- Trigger M5.x experiment phases that are pre-approved
- Send Discord notifications, write to internal logs, draft outreach for review

### Buzz must ask Anders first
- Schema migrations to Postgres
- Changes to trust score algorithm or weights
- Anything that touches sacred elements (pplx-verdict, ai-summary, SpeakableSpecification)
- New language additions (until Phase 1 parameterization is live and validated)
- New vertical additions (until Phase 3 vertical pipeline is live and validated)
- Sending external communication (PRs to other repos, emails to maintainers, social posts)
- Accepting/rejecting M5.x experiment outcomes
- Spending >50 EUR/week on burst compute
- Any contact with legal, financial, press, or investor parties
- Modifications to its own escalation rules or authority boundaries

### Buzz never does (hard limits)
- Delete production data
- Modify or revert other people's commits
- Change DNS, Cloudflare WAF, SSL configuration
- Pay invoices or modify payment methods
- Send messages from Anders's personal accounts
- Execute commands containing rm -rf, dd, mkfs, or destructive SQL (DROP, TRUNCATE) without explicit Anders approval per command
- Disable monitoring, alerting, or escalation paths
- Decrypt secrets and write them to logs

---

## Escalation chain

Buzz has three escalation tiers based on severity.

### Tier 1: Internal log (no human attention needed)
Daily summary, weekly report, routine self-heals, content generation activity, anomalies investigated and resolved. Anders reads these when convenient. Discord channel: `#buzz-log`. Email digest: weekly Sunday morning.

### Tier 2: Discord ping (human attention within hours)
Single Discord message with @Anders mention. Used for: anomalies that Buzz investigated but couldn't auto-resolve, decisions Buzz needs Anders to confirm, unusual traffic patterns, M5.x experiment results requiring human interpretation, content drafts awaiting approval. Buzz waits 4 hours between repeat Discord pings on the same issue. Channel: `#buzz-attention`.

### Tier 3: Catastrophe (immediate human contact required)
**Triggers:** Production down >15 minutes despite self-heal, data integrity event confirmed, security event detected, financial event >2x baseline, Buzz itself failing/crashing repeatedly, M5.x or other experiment producing data that suggests immediate strategic action needed.

**Contact protocol (executes in parallel, not sequential):**
1. **Discord** with @Anders + role mention `@operations-emergency`
2. **Email** to Anders's primary inbox with subject `[BUZZ CATASTROPHE]` and full incident report
3. **SMS** via Twilio to Anders's primary mobile (Sweden +46 number works globally for Anders during travel)
4. **Phone call** via Twilio Voice TTS reading the incident summary, retrying every 5 minutes up to 8 times (40 minutes total)

The phone call uses Twilio's text-to-speech which works through any phone system globally. Buzz constructs a TTS message: "Buzz catastrophe alert. [incident type]. [current status]. Please check Discord or email immediately." Phone call retry stops when Anders acknowledges via Discord, replies to email, or sends specific SMS reply ("ack" or "buzz ack").

**Escalation authority:** Buzz never wakes Anders for non-catastrophic events. The Tier 3 trigger list is intentionally narrow. Buzz errs on the side of self-resolving and waiting until daily summary if uncertain.

---

## LLM requirements analysis

### Workload characterization at steady state

**Daily compute load (estimated):**
- Health checks every 5 min: ~288 inferences/day, each <500 tokens. Light. Could be a much smaller model.
- Self-heal decision making: ~5-20 per day, each ~2K tokens. Medium reasoning.
- Anomaly investigation: ~3-10 per day, each ~10K-30K tokens (reading logs, commits, metrics). Heavy reasoning.
- Daily summary generation: 1 per day, ~30K tokens output. Heavy generation.
- Content generation (auto-publisher): ~5-30 articles/day, each ~3K-8K tokens output. Sustained generation.
- Translation spot-check: 5-10 per language × 50 languages = 250-500 inferences/day, each ~5K tokens. Multilingual capable.
- Description generation: ~50-200 entities/day, each ~1K-2K tokens output. Sustained generation.
- Vertical prioritization analysis: weekly, ~50K tokens of context analysis.
- Newsletter generation: weekly, ~20K tokens output.
- Strategic anomaly investigation: 1-5 per week, each up to 100K tokens of context.

**Total daily token budget:** Roughly 5-15 million tokens/day input + 2-5 million tokens/day output. This is heavy. Calling a paid API at $3/$15 per million tokens would cost $30-100/day = $900-3000/month, which exceeds the 100 EUR/month infrastructure cap many times over.

**Local LLM is the only path that fits the constraints.**

### Model capability requirements

1. **Long context (essential):** Anomaly investigation reads logs, commits, and metrics simultaneously. Need 64K-128K usable context. Many models claim 128K but degrade beyond 32K. Verified long-context performers preferred.
2. **Tool use / function calling (essential):** Buzz must call shell, SQL, HTTP, file operations through openclaw's tool interface. Native tool calling support (not prompt-engineered) is required.
3. **Reasoning (important):** Anomaly investigation, root cause analysis, vertical prioritization all require multi-step thinking. Models with explicit reasoning modes outperform.
4. **Multilingual (important):** Translation spot-check across 50 languages. Strong non-English performance required, especially for less-represented languages (Hindi, Tamil, Bengali, Vietnamese, Thai).
5. **Code understanding (important):** Many investigations require reading Python, SQL, YAML, JSON. Code-specialized models help here.
6. **Throughput (important):** 5-15M tokens/day input means the model needs to run efficiently. MoE architectures (where only a fraction of parameters activate per token) deliver much better throughput than dense models at the same total size.
7. **Cost: 0 (essential):** Local hosting only.

### Recommended model architecture

**Two-model setup:**

**Primary model: Qwen3-Coder-30B-A3B-Instruct**
- 30.5B total parameters, 3.3B activated per token (MoE)
- Native tool calling, OpenAI-compatible function call schema
- Strong at agentic coding, multi-step tool chains, reasoning over codebase context
- Multilingual via Qwen's broad training corpus
- ~18 GB VRAM Q4 quantized, fits comfortably on Mac Studio M1 Ultra 64GB or a Hetzner CCX23 (16 vCPU dedicated, 32GB RAM, ~50 EUR/month)
- Best community-validated agent model in 2026 per multiple sources
- Used by other openclaw users in production with reported reliability

**Reasoning model: Qwen3 32B (Thinking variant)**
- Dense 32B for complex reasoning when stepping through anomaly investigation or strategic analysis
- Used selectively when the primary model encounters something beyond pattern-matching scope
- Slower but more capable on novel problems
- Optional secondary; Buzz routes most work to primary, escalates to reasoning model only when needed

**Fallback model: keep current qwen3:32b** that's already on Mac Studio for emergency fallback if the primary cluster goes down.

### Why not the alternatives

- **Llama 3.3 70B:** Stronger pure reasoning but 40+ GB VRAM, no tool calling baked in (must prompt-engineer), weaker non-English. Too heavy and not agent-optimized.
- **GLM-4.5-Air / GLM-4.7-Flash:** Excellent agentic model and would be a strong second choice. MoE 106B/12B active. Reasonable to evaluate as alternative to Qwen3-Coder. Smaller community than Qwen for openclaw integration patterns.
- **DeepSeek-R1 32B/70B:** Reasoning specialist but slow first-token, verbose output, not optimized for tool use loops. Better as secondary reasoning model than primary.
- **Kimi-K2.5:** 1T parameters even at 32B active is too much hardware to host on our budget.
- **Qwen2.5-Coder:32B:** What's currently installed for code work. Strong coder but older. Qwen3-Coder is the natural upgrade path.

### Hosting decision

**Where Buzz LLM runs:** Dedicated Hetzner CCX23 (16 dedicated vCPU, 32 GB RAM, Q4 inference) or CCX33 (24 vCPU, 64GB) for headroom on parallel inference. Cost: ~50-80 EUR/month. Lives separate from the serving nodes (Nbg + Hel CPX41) to isolate workload — if Buzz LLM is busy doing anomaly investigation, serving latency is unaffected.

**Buzz instance topology:**
- **Primary Buzz** runs on Hetzner Nbg, talks to LLM on CCX23 over Tailscale
- **Standby Buzz** runs on Mac Studio (after Phase 0, demoted to accelerator), uses local Ollama qwen3:32b as fallback if CCX23 unavailable
- Both Buzz instances coordinate via shared state file in Postgres (which one is active)

This topology means: Hetzner outage → Mac Studio Buzz takes over with weaker but functional LLM. Mac Studio dies → Hetzner Buzz keeps running with full LLM. CCX23 dies → Hetzner Buzz falls back to Mac Studio LLM via Tailscale.

---

## Implementation phases

### Phase 0: Spec approval and prerequisites
This document. Anders reviews, edits, approves. Then prerequisites are fulfilled.

### Phase 1: Buzz workspace rewrite
Rewrite all `~/.openclaw/workspace/*.md` files for April 2026 system reality. Update all 5 skill files. Replace cron job specifications. Cannot start until Phase 0 cloud migration completes (so we know the actual production topology to write into the docs).

### Phase 2: LLM provisioning
Provision CCX23, install Ollama, download Qwen3-Coder-30B-A3B-Instruct + Qwen3 32B. Configure Buzz models.json. Test inference speed and quality on representative workload samples.

### Phase 3: Escalation chain setup
- Discord: configure new channels (#buzz-log, #buzz-attention, #buzz-emergency)
- Email: configure SMTP relay (Postmark or Amazon SES, not personal Gmail)
- SMS: Twilio account, buy Swedish number, integrate API, test delivery globally
- Phone: Twilio Voice TTS, test call to Anders's Sweden number from a US-based test
- Acknowledgment system: shared state file Buzz checks for "ack" tokens

### Phase 4: Authority boundaries enforcement
Code-level enforcement of the authority lists. Buzz prompt includes the lists. Tool wrappers reject calls that violate hard limits. Audit log captures every action with category tag.

### Phase 5: Shadow run
Buzz runs in parallel with current operations for 7 days. Buzz makes recommendations but doesn't execute. Compare Buzz recommendations against what Anders/Claude actually do. Calibrate. Fix gaps.

### Phase 6: Limited autonomous run
Buzz executes Category A (daily drift) autonomously. Anders + Claude continue Category B/C/D manually. 7 days. Verify nothing breaks.

### Phase 7: Full autonomous run
Buzz handles all 20 responsibility areas. First 7-day vacation test scheduled with explicit safety net (Anders checks daily, can override anytime).

### Phase 8: Vacation-ready certification
Buzz has run autonomously for 30+ days with no Tier 3 escalations and only acceptable-rate Tier 2 escalations. System is certified vacation-ready.

---

## Success criteria

Buzz 2.0 is successful when:

1. **7-day vacation test passes:** Anders is unreachable for 7 consecutive days. System health, AI citation rates, and freshness SLA compliance remain within normal variance. Zero Tier 3 escalations during the period (if there are Tier 3 events, the test fails and we debug whatever caused them).
2. **Citation rates do not degrade:** AI citations per source remain within 10% of pre-Buzz-2.0 baseline.
3. **Freshness SLA holds:** All 4 tiers maintain >95% compliance throughout vacation period.
4. **Auto-generated content quality:** Spot-audit of Buzz-generated content (auto-publisher articles, descriptions, translations) shows ≥7/10 quality on a 20-sample audit per week.
5. **Self-heal effectiveness:** ≥90% of incidents self-resolved without Tier 2 escalation. Tier 2 escalation rate <5/week. Tier 3 escalation rate 0/month at steady state.
6. **Cost discipline:** Buzz LLM hosting + Twilio + email infrastructure stays within 100 EUR/month (combined with rest of infrastructure).
7. **Audit trail:** Every Buzz action is logged with timestamp, category, decision rationale, and outcome. Anders can review any 24-hour window in <15 minutes.

---

## Resolved questions (v0.2)

1. **Tier 2 channel:** Discord. Confirmed.
2. **Phone retry intensity:** 8 retries × 5 min = 40 minutes total during catastrophe.
3. **Auto-publish for B/C content:** Auto-publish if confidence high, queue if low. Confirmed.
4. **Burst compute limit:** 50 EUR/week to start. Re-evaluated quarterly.
5. **Vacation timing:** No specific vacation planned. Buzz 2.0 is built for future readiness, not for an imminent test. Implementation timeline is therefore flexible.
6. **LLM choice:** Start with Qwen3-Coder-30B-A3B + Qwen3 32B. Quarterly re-evaluation against new releases is now D5 responsibility (see above).
7. **SMS provider:** Twilio confirmed.

## Remaining open questions

None. Spec v0.2 is ready for implementation phase planning when Buzz 2.0 work begins (post Phase 0).

---

*End of Buzz 2.0 Specification.*
