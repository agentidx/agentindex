-- Smedjan Phase-A seed tasks.
-- Idempotent: ON CONFLICT DO NOTHING so re-runs are safe during review.
-- T001 / T002 wait for evidence signals that only land post-L1-observation.

-- ── T001 — L1 Wave 2 canary deploy (npm+pypi+crates Kings) ───────────────
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority,
    wait_for_evidence, session_group, status
) VALUES (
    'T001',
    'L1 Wave 2 canary: add npm+pypi+crates to L1_UNLOCK_REGISTRIES',
    $desc$
Context: L1 Kings Unlock canary Day-1 (gems+homebrew) went live
2026-04-18 13:34 local. Evidence signal "l1_canary_observation_48h" marks
that the 48h observation window closed with green signals.

Goal: widen the canary scope to include npm, pypi, and crates. The same
code path (smedjan L1 Kings Unlock, fail-closed allowlist) already
handles these registries — this is a pure config change.

Steps:
 1. Read current L1_UNLOCK_REGISTRIES value from
    ~/Library/LaunchAgents/com.nerq.api.plist.
 2. Confirm it is currently "gems,homebrew" — if not, abort with
    STATUS: blocked and note the unexpected value.
 3. Run a 100-sample dry-run against each of npm, pypi, crates using
    ~/agentindex/scripts/dryrun_l1_kings_unlock.py (no actual code change,
    no plist edit). If any registry shows >0 crashes or antipatterns,
    STATUS: blocked with the registry name and counts.
 4. Update the plist:
        /usr/libexec/PlistBuddy -c \
          "Set :EnvironmentVariables:L1_UNLOCK_REGISTRIES 'gems,homebrew,npm,pypi,crates'" \
          ~/Library/LaunchAgents/com.nerq.api.plist
 5. launchctl unload then launchctl load (kickstart alone does not
    propagate new env vars per 2026-04-18 incident).
 6. Wait 30s; curl /v1/health for HTTP 200.
 7. Run scripts/purge_redis_canary.py with SMEDJAN_CANARY_REGS
    "npm,pypi,crates" to evict stale page-cache entries.
 8. Spot-check 5 slugs per registry with ~/agentindex/scripts/smedjan
    (curl /safe/<slug>, grep "Detailed Score Analysis").
 9. Record observations for the first hour in
    ~/smedjan/observations/L1-wave2-<timestamp>.md.

Forbidden paths: none touched. Whitelist is ops-only (plist + scripts).
$desc$,
    $ac$
Acceptance:
- /usr/libexec/PlistBuddy Print shows L1_UNLOCK_REGISTRIES=
  "gems,homebrew,npm,pypi,crates"
- At least 4 of 5 spot-check slugs per new registry render "Detailed
  Score Analysis"; the remainder resolve out-of-allowlist (documented in
  the observation md).
- No 5xx spike in the first 15 minutes post-kickstart (monitor will
  ntfy otherwise).
- Observation report file written under ~/smedjan/observations/.
$ac$,
    ARRAY[]::text[],
    'high',
    ARRAY[
      '~/Library/LaunchAgents/com.nerq.api.plist',
      'scripts/dryrun_l1_kings_unlock.py',
      'scripts/purge_redis_canary.py'
    ],
    10,                                                 -- high priority
    'l1_canary_observation_48h',
    'l1_rollout',
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- ── T002 — L1 Wave 3 rollout (all remaining non-skip registries) ────────
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority,
    wait_for_evidence, session_group, status
) VALUES (
    'T002',
    'L1 Wave 3 rollout: L1_UNLOCK_REGISTRIES="*" (full non-skip)',
    $desc$
Context: Waves 1 and 2 (gems+homebrew, then +npm+pypi+crates) produced
green observation windows. "*" unlocks every registry except the SKIP
list (city, charity, ingredient, supplement, cosmetic_ingredient, vpn,
country), i.e. ~1.4M additional entities.

Steps:
 1. Confirm T001 is in 'done' state (dep) — factory_core enforces but
    verify via smedjan queue show T001.
 2. Run dryrun_l1_kings_unlock.py against wordpress, chrome, ios,
    android, saas, ai_tool, nuget, steam, packagist, go, gems-alt, vscode,
    firefox, website, crypto — 50 samples each. Halt on any crash or
    antipattern.
 3. Update plist: L1_UNLOCK_REGISTRIES="*"
 4. unload + load API.
 5. purge_redis_canary with SMEDJAN_CANARY_REGS unset (full /safe/*
    scan). 5,000+ keys — proceed slowly (pause 100ms between deletes)
    to avoid wedging Redis. Script already batches at count=500.
 6. 60s smoke: curl 3 samples per registry, verify "Detailed Score
    Analysis" present.

Risk=high: touches ~1.4M production pages. Approval MUST carry a
scheduled_start_at — verified at CLI layer by smedjan queue approve.
$desc$,
    $ac$
Acceptance:
- Plist shows L1_UNLOCK_REGISTRIES="*"
- All 15 smoke registries return "Detailed Score Analysis" in ≥4 of 5
  canary slugs
- Whole-Nerq 5xx rate over the following 30 min stays below 0.2%
  (monitor pages if not — rollback via runbook)
- ~/smedjan/observations/L1-wave3-<timestamp>.md written
$ac$,
    ARRAY['T001']::text[],
    'high',
    ARRAY[
      '~/Library/LaunchAgents/com.nerq.api.plist',
      'scripts/dryrun_l1_kings_unlock.py',
      'scripts/purge_redis_canary.py'
    ],
    10,
    'l1_wave2_observation_48h',
    'l1_rollout',
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- ── T003 — Monetization tier classification ────────────────────────────
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority, status
) VALUES (
    'T003',
    'Monetization tier classification (Traffic x CTR x RPC scaffold)',
    $desc$
Context: Nerq has no affiliate/RPC instrumentation today. Revenue estimation
uses the triad Traffic x CTR x RPC (Keyword Planner CPC proxy for RPC).
This task builds the first component — page-pattern tier classification —
so downstream L2/L4 tasks (T004-T007) can prioritise high-RPC paths.

Goal: Create public.monetization_tiers table and seed it with tier
assignments for all Nerq page patterns across 26 registries.

Steps:
 1. Read software_registry.registry distinct values (Postgres primary
    100.119.193.70; read-only).
 2. Create table in the smedjan schema (do NOT touch public schema):
       CREATE TABLE IF NOT EXISTS smedjan.monetization_tiers (
           path_pattern     text PRIMARY KEY,
           tier             text NOT NULL CHECK (tier IN ('T1','T2','T3')),
           avg_cpc_usd      numeric(6,2),
           rationale        text,
           last_updated     timestamptz NOT NULL DEFAULT now()
       );
 3. Populate rows per the tiering rubric below. CPC_usd is a static
    seed based on Google Keyword Planner categories (no live API call).
    Commit the rubric inline in the rationale column.
 4. Write ~/smedjan/docs/monetization-tiers.md summarising the rubric,
    the seed table shape, and how downstream tasks should join against
    it (software_registry.registry -> path_pattern).

Tiering rubric:
  T1 (>= $5 avg CPC): /safe/<vpn>, /best/vpn, /compare/<vpn>-vs-*,
      /safe/<antivirus>, /safe/<password_manager>, /crypto/token/<slug>
      (where registry in ('vpn','antivirus','password_manager','crypto'))
  T2 ($1-$5 avg CPC): /safe/<saas>, /safe/<ai_tool>, /compare/*-vs-*
      in saas+ai_tool, /alternatives/<saas>, /review/<saas>
  T3 (< $1 avg CPC): /safe/<npm/pypi/crates/go/gems/packagist>,
      /safe/<homebrew>, /safe/<wordpress/chrome/firefox>,
      /safe/<ios/android/steam/website/charity/ingredient/supplement>

Forbidden paths: none. Postgres writes go to smedjan schema only.
$desc$,
    $ac$
Acceptance:
- Table smedjan.monetization_tiers exists with >= 80 rows covering all
  26 registries x at least 3 page patterns each
- No row has NULL rationale
- ~/smedjan/docs/monetization-tiers.md written, ≥ 300 words, includes
  a per-tier summary + example join query against software_registry
- Task result block reports the row count in EVIDENCE
$ac$,
    ARRAY[]::text[],
    'low',
    ARRAY[
      'agentindex/smedjan/',
      'smedjan/docs/monetization-tiers.md'
    ],
    50,
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- ── T004 — L2 Block 2a (external_trust_signals) ─────────────────────────
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority, session_group, status
) VALUES (
    'T004',
    'L2 Block 2a: external trust signals content block',
    $desc$
Context: zarq.external_trust_signals has 22,502 rows covering 7,724
entities with OSV vulnerability data, OpenSSF Scorecard sub-scores, and
community-mention counts (per 2026-04-18 Front D inventory,
~/smedjan/discovery/L2-data-surfacer-inventory.md).

Goal: render Block 2a ("External Trust Signals") inside king_sections
in agent_safety_pages.py. Follow the L1 canary playbook — add a new env
var L2_BLOCK_2A_REGISTRIES (fail-closed empty = disabled). Initial
canary registry: "npm" (highest T3 demand AND highest external_trust
coverage).

Content template (English; translations in a follow-up):
    Verified by: {sources_list}.
    Vulnerabilities found: {osv_count} (OSV.dev, last scan: {scan_date}).
    OpenSSF Scorecard: {score}/10  ({signals_summary}).
    Mentioned in {so_thread_count} Stack Overflow threads and
    {reddit_mention_count} Reddit posts (last 12 months).

Placement: ABOVE existing king_sections's "Detailed Score Analysis".
Never touch pplx-verdict / ai-summary / SpeakableSpecification markup.

Steps:
 1. Read zarq.external_trust_signals schema via psql and document in
    ~/smedjan/docs/L2-block-2a-design.md.
 2. Write a helper _fetch_external_trust(slug) in
    agentindex/smedjan/l2_block_2a.py (new file).
 3. Patch agent_safety_pages.py to import the helper and render the
    block inside the existing `if _render_king_sections:` scope. Gate
    on L2_BLOCK_2A_REGISTRIES allowlist (same semantics as L1).
 4. Write scripts/dryrun_l2_block_2a.py (mirror of
    dryrun_l1_kings_unlock.py) and run it on 50 npm samples.
 5. Pause BEFORE any plist edit / kickstart — this task deploys no
    code path. A follow-up task T004b will handle the canary rollout
    (risk=medium needs_approval).

Forbidden paths: none. agent_safety_pages.py edits are inside the L1
Kings Unlock scope — already whitelisted.
$desc$,
    $ac$
Acceptance:
- New file agentindex/smedjan/l2_block_2a.py exists with docstring
- agent_safety_pages.py patched with new env var + block rendering
  (python -m py_compile passes)
- scripts/dryrun_l2_block_2a.py runs against 50 npm samples, reports 0
  crashes and 0 antipatterns with the block added
- ~/smedjan/docs/L2-block-2a-design.md written (≥ 400 words)
- No plist edits, no kickstart — NEVER exceed the task boundary
$ac$,
    ARRAY['T003']::text[],
    'low',
    ARRAY[
      'agentindex/agent_safety_pages.py',
      'agentindex/smedjan/',
      'smedjan/docs/L2-block-2a-design.md',
      'scripts/dryrun_l2_block_2a.py'
    ],
    40,
    'L2',
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- ── T005 — L2 Block 2b (dependency graph) ───────────────────────────────
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority, session_group, status
) VALUES (
    'T005',
    'L2 Block 2b: dependency graph content block (npm-only initially)',
    $desc$
Context: public.dependency_edges has 746,254 rows covering 49,976 npm
from-entities. Reverse-dependency counts ("N packages depend on this")
are Nerq-exclusive data per 2026-04-18 Front D inventory.

Goal: render Block 2b (""Dependency Graph"") inside king_sections for
npm entities only. Template:
    This package is depended on by {reverse_count} other npm packages.
    Its {direct_count} direct dependencies have trust scores averaging
    {avg_dep_trust}/100.
    {dormant_warning_if_any}

Steps:
 1. SQL: verify dependency_edges row count + sample. Document sample
    query in ~/smedjan/docs/L2-block-2b-design.md.
 2. Add _fetch_dependency_graph(slug) helper in
    agentindex/smedjan/l2_block_2b.py (new file).
 3. Patch agent_safety_pages.py: new env var L2_BLOCK_2B_REGISTRIES
    (fail-closed). Render block ABOVE Block 2a when both present.
 4. scripts/dryrun_l2_block_2b.py against 100 npm samples.
 5. No plist edit / kickstart.
$desc$,
    $ac$
Acceptance: same shape as T004 (file exists, py_compile OK, dry-run 0
crashes / 0 antipatterns on 100 npm samples, design doc ≥ 400 words).
$ac$,
    ARRAY['T003']::text[],
    'low',
    ARRAY[
      'agentindex/agent_safety_pages.py',
      'agentindex/smedjan/',
      'smedjan/docs/L2-block-2b-design.md',
      'scripts/dryrun_l2_block_2b.py'
    ],
    40,
    'L2',
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- ── T006 — L2 Block 2c (signal timeline) ────────────────────────────────
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority, session_group, status
) VALUES (
    'T006',
    'L2 Block 2c: trust-score signal timeline',
    $desc$
Context: public.signal_events carries 24,593 trust-score change records
for 10,173 entities (spans 31 registries). Front D inventory flagged
327 King overlaps — largest of the three L2 blocks.

Goal: render Block 2c ("Signal Timeline") with the last 3 meaningful
score changes per entity. Template:
    Trust score history: {score_1} ({month_1}) -> {score_2} ({month_2})
    -> {score_3} ({month_3}).
    Last significant change: {delta_sign}{delta_abs} points on {date}
    ({reason_if_any}).

Steps:
 1. SQL: verify signal_events sample + write
    ~/smedjan/docs/L2-block-2c-design.md.
 2. Add _fetch_signal_timeline(slug) helper in
    agentindex/smedjan/l2_block_2c.py.
 3. Patch agent_safety_pages.py: new env var L2_BLOCK_2C_REGISTRIES.
    Render below Block 2a, above Detailed Score Analysis.
 4. scripts/dryrun_l2_block_2c.py on 100 samples from top-5 registries
    with timeline coverage.
$desc$,
    $ac$
Acceptance: same shape as T004/T005.
$ac$,
    ARRAY['T003']::text[],
    'low',
    ARRAY[
      'agentindex/agent_safety_pages.py',
      'agentindex/smedjan/',
      'smedjan/docs/L2-block-2c-design.md',
      'scripts/dryrun_l2_block_2c.py'
    ],
    40,
    'L2',
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- ── T007 — L4 /rating/.json endpoint ────────────────────────────────────
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority, status
) VALUES (
    'T007',
    'L4: /rating/{slug}.json endpoint for top-100K demand entities',
    $desc$
Context: L4 Data Moat Endpoints is next after L2 content blocks land.
Expose a strict-JSON endpoint for passive AI-bot discovery — format is
stable machine-readable data, no HTML wrapping.

Goal: a new FastAPI route /rating/{slug}.json that returns:
    {
      "slug": "express",
      "trust_score": 83.4,
      "trust_grade": "A",
      "registry": "npm",
      "last_updated": "2026-04-17T03:00:00Z",
      "dimensions": {"security": 87, "maintenance": 80, ...},
      "data_sources": ["npm registry", "GitHub", "OSV", "OpenSSF"],
      "registry_url": "https://www.npmjs.com/package/express"
    }

Steps:
 1. Create agentindex/api/rating.py (new file) with the route handler.
 2. Mount it in agentindex/api/discovery.py (NOT api/main.py — that is
    forbidden).
 3. Limit initial availability to top-100K entities by ai_demand_score
    (table smedjan.ai_demand_scores already populated). Write a helper
    that caches the lookup in Redis db=1 with TTL 4h, key rating:<slug>.
 4. Add a background pre-warm step (separate LaunchAgent plist — NOT
    loaded in Phase A) that touches all 100K entries nightly.

No touch to robots.txt / sitemap.xml / llms.txt — T008 advertises the
endpoints.
$desc$,
    $ac$
Acceptance:
- /rating/express.json (and 4 other top-demand slugs) returns HTTP 200
  with the schema above
- 404 for slugs outside the top-100K
- Pre-warm LaunchAgent plist exists at
  ~/Library/LaunchAgents/com.nerq.smedjan.rating_prewarm.plist.disabled
  (not loaded)
$ac$,
    ARRAY['T003']::text[],
    'low',
    ARRAY[
      'agentindex/api/rating.py',
      'agentindex/api/discovery.py',
      'Library/LaunchAgents/com.nerq.smedjan.rating_prewarm.plist.disabled'
    ],
    30,
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- ── T008 — Expand llms.txt with rating/signals/dependencies endpoints ───
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority, status
) VALUES (
    'T008',
    'Extend llms.txt with L4 endpoint families',
    $desc$
Goal: advertise /rating/{slug}.json, /signals/{slug}.json, and
/dependencies/{slug}.json to AI crawlers via llms.txt.

llms.txt lives at agentindex/static/llms.txt (confirm via grep). Append
three sections per the existing structure; preserve all current entries.

Risk=medium: llms.txt is AI-bot-facing; incorrect format breaks
discovery for ALL Nerq endpoints, not just the new ones. Validate by
fetching via curl after the change, verify no 5xx, and verify the file
is syntactically a plain-text list (no regressions).
$desc$,
    $ac$
Acceptance:
- llms.txt contains 3 new endpoint-family sections
- curl https://nerq.ai/llms.txt returns HTTP 200 and the new sections
- Old entries preserved verbatim (diff shows additions only)
$ac$,
    ARRAY['T007']::text[],
    'medium',
    ARRAY['agentindex/static/llms.txt'],
    35,
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- ── T009 — MCP manifest expansion (20 -> 40+ tools) ─────────────────────
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority, status
) VALUES (
    'T009',
    'MCP manifest: 20 -> 40+ tools',
    $desc$
Context: Nerq ships an MCP server (agentindex/mcp_*.py). Currently 20
tools advertised per v3.0 plan. Expand to 40+ by adding tools for the
new L4 endpoints (rating / signals / dependencies) plus demand-score
lookups.

Steps:
 1. grep the repo for the MCP manifest source (likely
    agentindex/mcp_trust_pages.py or agentindex/api/mcp_server.py).
 2. Add at least 20 new tool entries. Each tool needs name,
    description, schema, and a handler. Reuse existing handlers where
    possible (e.g. the /rating/ route is one-to-one with a tool).
 3. Update README or docs with the new tool list.
$desc$,
    $ac$
Acceptance:
- MCP manifest lists >= 40 tools
- All new tool handlers return valid JSON on a sample call
- Docs updated under ~/smedjan/docs/mcp-expansion.md
$ac$,
    ARRAY['T007']::text[],
    'low',
    ARRAY[
      'agentindex/mcp_trust_pages.py',
      'agentindex/api/mcp_server.py',
      'smedjan/docs/mcp-expansion.md'
    ],
    45,
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- ── T010 — RSS per vertical ─────────────────────────────────────────────
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority, status
) VALUES (
    'T010',
    'RSS feeds per vertical: /feed/{registry}.xml',
    $desc$
Goal: produce one RSS feed per registry with the 50 most-recently
enriched entities. Feed lastmod gives AI bots a re-crawl signal.

Steps:
 1. Add agentindex/api/rss_feeds.py with a route /feed/{registry}.xml
    that queries public.software_registry ordered by enriched_at DESC
    LIMIT 50.
 2. Mount the route in agentindex/api/discovery.py.
 3. Reuse existing feed patterns if present (grep for existing /feed/).
 4. No llms.txt update in this task (that is T008).
$desc$,
    $ac$
Acceptance:
- curl /feed/npm.xml returns valid RSS 2.0 with 50 items
- All 26 registries reachable
- /feed/does-not-exist.xml returns 404
$ac$,
    ARRAY[]::text[],
    'low',
    ARRAY[
      'agentindex/api/rss_feeds.py',
      'agentindex/api/discovery.py'
    ],
    55,
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- ── Fallback layer (F1/F2/F3) — picked only when primary queue empty ────
-- T015 F1 — quality audit (recurring-template; single-shot in Phase A)
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority,
    is_fallback, fallback_category, status
) VALUES (
    'T015',
    'F1 quality audit: 100 random /safe/* spot-checks',
    $desc$
Fallback layer F1 (highest priority fallback). Runs whenever the primary
queue is empty.

Goal: audit 100 random enriched software_registry entities by curling
/safe/<slug> and checking for:
  - HTTP 200
  - presence of canonical link
  - no literal "None" / "null" in rendered HTML
  - no empty <td></td> cells
  - pplx-verdict + ai-summary still first sacred bytes (schema.org
    SpeakableSpecification references them)

Write findings to ~/smedjan/audits/F1-<date>.md with counts per finding.
If any single finding affects > 5 pages, escalate STATUS: needs_approval
with the finding description (Anders decides on a proper fix task).
$desc$,
    $ac$
Acceptance:
- audit file written with 100-sample results
- zero crashes during curls
- any systemic finding ( > 5 pages ) triggers needs_approval instead of done
$ac$,
    ARRAY[]::text[],
    'low',
    ARRAY['smedjan/audits/'],
    90,
    true, 'F1',
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- T016 F2 — freshness refresh (identify stale entries; no re-crawl)
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority,
    is_fallback, fallback_category, status
) VALUES (
    'T016',
    'F2 freshness: surface 200 oldest-enriched top-demand entities',
    $desc$
Fallback layer F2. For the top-5 registries by ai_demand_score coverage
(npm, pypi, crates, ai_tool, nuget — verify via smedjan.ai_demand_scores
joined to software_registry), pick the 200 rows with the oldest
enriched_at and write the list to ~/smedjan/audits/F2-<date>.csv so a
later enrichment task can prioritise them.

This task does NOT call any enricher — it is read-only prep work.
$desc$,
    $ac$
Acceptance:
- CSV written with 200 rows, columns: slug, registry, enriched_at,
  ai_demand_score
- CSV is sorted by (registry, enriched_at ASC)
$ac$,
    ARRAY[]::text[],
    'low',
    ARRAY['smedjan/audits/'],
    95,
    true, 'F2',
    'pending'
) ON CONFLICT (id) DO NOTHING;

-- T017 F3 — internal linking (find missing /compare/ links)
INSERT INTO smedjan.tasks (
    id, title, description, acceptance_criteria,
    dependencies, risk_level, whitelisted_files, priority,
    is_fallback, fallback_category, status
) VALUES (
    'T017',
    'F3 internal linking: propose /compare/ additions for 50 enriched pairs',
    $desc$
Fallback layer F3 (lowest priority). For the 50 highest-demand entity
pairs in the same registry (joined via ai_demand_scores), check whether
/compare/<a>-vs-<b> currently exists (curl for 200). If not, propose an
addition by writing to ~/smedjan/audits/F3-proposals-<date>.md.

No page creation — this is a proposal list. Anders or a future task
decides which pairs to materialise.
$desc$,
    $ac$
Acceptance:
- Proposals markdown lists 50 candidate pairs with HTTP status of the
  current /compare/<a>-vs-<b> URL
- Recommendation column per pair: 'create' if 404, 'skip' if 200
$ac$,
    ARRAY[]::text[],
    'low',
    ARRAY['smedjan/audits/'],
    99,
    true, 'F3',
    'pending'
) ON CONFLICT (id) DO NOTHING;
