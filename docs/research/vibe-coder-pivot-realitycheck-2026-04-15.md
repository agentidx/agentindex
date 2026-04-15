# Vibe-Coder Security Pivot — Reality Check

**Date:** 2026-04-15
**Purpose:** Factual inventory of data, traffic, capacity, and gaps. No recommendations.
**Method:** Direct DB queries, log analysis, API testing, code audit.

---

## DEL 1: Datakvalitet och täckning

### 1.1 npm-täckning

| Metric | Count | % of total |
|--------|-------|-----------|
| Total npm packages | 528,326 | 100% |
| Has trust_score | 528,306 | 99.996% |
| Has trust_grade | 528,306 | 99.996% |
| Has downloads > 0 | 91,747 | 17.4% |
| Has stars > 0 | **457** | **0.09%** |
| Has enriched_at | 528,301 | 99.995% |
| Has dependency edges | 20,001 | 3.8% |
| Has CVE data | **0** | **0%** |
| Has contributor metrics | ~5,055 (all registries) | <1% |

**Top 10K by downloads:** 100% have trust_score, trust_grade, and downloads. Full coverage where it matters most.

**Critical data gaps:**
- **Stars: nearly empty.** Only 457 of 528K packages have stars. Top packages (uuid, minimatch, glob) all show 0 stars despite being massively popular. Stars are not being collected from GitHub for npm packages.
- **CVE data: completely absent for npm.** The `cve_count` column exists on `software_registry` but is 0 for all npm packages. The `agent_vulnerabilities` SQLite table has only 49 records total (across all registries). CVE enrichment via OSV.dev goes into `external_trust_signals` (22,817 records) but is not surfaced per-package as queryable CVE counts.
- **Dependency graph: 3.8% coverage.** 20,001 packages have edges (320,278 total edges). Collection started April 14, still running. At 1 req/s, full 528K coverage takes ~6 days.

### 1.2 Trust score quality

**Algorithm (compute_trust_score.py — 5 dimensions):**

| Dimension | Weight | Inputs |
|-----------|--------|--------|
| Security | 30% | License type, README keywords (security, testing), risky capabilities (shell, fs_write, network, creds), registry verification |
| Compliance | 25% | compliance_score bucket mapping |
| Maintenance | 20% | last_source_update recency (14d→98, 30d→92, ..., >365d→15). Contributor metrics adjustment ±15 pts |
| Popularity | 15% | stars, downloads, forks — tiered buckets |
| Ecosystem | 10% | capabilities, agent_type, category, invocation, author count |

**Score distribution for npm:**

| Range | Count | % |
|-------|-------|---|
| 90-100 | 5 | 0.001% |
| 70-89 | 22,784 | 4.3% |
| 50-69 | 86,695 | 16.4% |
| 30-49 | 418,793 | **79.3%** |
| 0-29 | 29 | 0.006% |

**The distribution is heavily compressed into 30-49.** This means 79% of npm packages are effectively indistinguishable by score. Root cause: stars (0 for 99.9%), CVE data (0 for 100%), and downloads (0 for 82.6%) — the three strongest differentiators — are mostly empty. Without these signals, nearly all packages get the same base score from metadata alone.

**Update frequency:** Scores are batch-recomputed. No real-time recalculation on query. Enrichment dates (`enriched_at`) range from March-April 2026.

**Deterministic:** Yes. Same inputs → same score. No ML or probabilistic components.

**Manual validation:** None. Fully automated.

### 1.3 Hallucination detection

| Capability | Status |
|------------|--------|
| Packages that no longer exist on npm | **Unknown.** We don't verify continued existence after initial crawl. A package could be unpublished and we'd still serve its old score. |
| Typosquat detection | **Not implemented.** No name-similarity analysis, no Levenshtein distance checks, no "did you mean?" suggestions. |
| Query for unknown package | Returns structured JSON with `interaction_risk: "UNKNOWN"`, `recommendation: "UNKNOWN"`, all fields null. HTTP 200, ~300ms. Clean degradation but no "this package doesn't exist on npm" signal. |
| Detect hallucinated package name | **Partially possible.** We could check if a queried name exists in our 528K npm index. If not, and it also doesn't exist on npm registry, it's likely hallucinated. But we don't do this check today — we just return UNKNOWN. |

**What's missing for hallucination detection:**
1. Real-time npm registry existence check (simple HTTP HEAD to registry.npmjs.org)
2. Typosquatting similarity scoring against known packages
3. A "this package does not exist" response (vs current UNKNOWN which is ambiguous)

### 1.4 Real-time vs batch

| Pipeline | Update frequency | Latency to new data |
|----------|-----------------|---------------------|
| npm package list | Weekly batch (npm-crawler) | Up to 7 days |
| Downloads counts | Weekly batch | Up to 7 days |
| Trust score computation | On-demand batch | Hours to days |
| CVE enrichment (OSV.dev) | Weekly batch (Wed 05:00) | Up to 7 days |
| Dependency graph | Daily batch (03:00) | Up to 24 hours |
| Contributor metrics | Monthly batch (1st of month) | Up to 30 days |
| Preflight response | **Real-time** (cached 1h) | Stale by up to 1 hour |

**A brand new npm package published today would not appear in our database for up to 7 days.**

**API latency (localhost, /v1/preflight):**

| Metric | Value |
|--------|-------|
| p50 | **20-25ms** |
| p95 | ~200ms |
| Cold first-hit | 2.0-2.3s (DB + cache miss) |
| After warm | <30ms |

---

## DEL 2: AI-coding-relaterad trafik

### 2.1 AI coding client traffic (last 30 days)

| Client | Requests | Platforms |
|--------|----------|-----------|
| Cursor | ~54 | Windows, Mac, Linux (versions 2.5-3.1) |
| Cafecito-Coffeemaker | 31 | Bot/scraper (false positive) |
| Claude Code | ~27 | Versions 2.1.83-2.1.97 |
| Windsurf | ~20 | Versions 1.106-1.108 |
| CodexResearchBot | 3 | Crawler |
| ImaCopilot | 1 | iOS |
| **Total coding tools** | **~105** | |

**Not detected:** Cline, Aider, Cody, Continue, Lovable, Bolt, v0, NxCode, Replit, GitHub Copilot.

**Volume assessment: ~3.5 requests/day from AI coding tools.** This is signal, not volume.

### 2.2 Preflight analytics — coding-related queries

**Total preflight queries (30 days): ~86,000** (~5,500/day avg)

Top coding-related targets:

| Target | Queries |
|--------|---------|
| express | 119 |
| react | 84 |
| numpy | 35 |
| cursor | 29 |
| langchain | 52 |
| langchain-ai/langchain | 124 |
| claude-task-master | 19 |
| openclaw | 19 |
| windsurf | 19 |
| node / node-releases | 15 each |
| preact | 14 |
| typescript-estree | 11 |
| testing-library-react | 11 |

**The "test" target has 7,853 queries** — likely automated health checks, not real usage.

### 2.3 Organic search traffic on safety pages

The real coding traffic comes via organic search, not AI tools:

| Page pattern | Hits (30 days) |
|-------------|----------------|
| /safe/express (all langs) | ~1,500+ |
| /is-express-safe | 158 |
| /is-react-safe | 143 |
| /safe/react (all langs) | ~400+ |
| /safe/preact | 56 |
| /safe/node | 38 |
| /safe/testing-library-react | 85 |
| /safe/react-developer-tools | 35 |

Localized variants (/es/, /de/, /ja/, /fr/, /pt/) are indexed and receiving traffic.

### 2.4 Geographic distribution (AI bot traffic, 7 days)

| Country | Requests | % |
|---------|----------|---|
| US | 915,708 | 60% |
| Unknown | 560,768 | 37% |
| SG | 32,167 | 2% |
| PL, JP, AU, NZ, ES, IN, BR | <1,000 each | <1% |

Note: this is ALL AI bot traffic, not just coding tools.

---

## DEL 3: Konkurrentlandskap

### 3.1 Competitor data in our DB

| Competitor | Sources indexed | Trust score range | Downloads (npm) |
|-----------|----------------|-------------------|-----------------|
| Snyk | npm, vscode, mcp, github, pulsemcp | 59.5-80.8 | 2.3M (snyk), 393K (vscode ext), 2.5M (@snyk/github-codeowners) |
| Socket | npm, crates, mcp | 48.2-77.2 | 50K (socket), 21K (@socketsecurity/cli) |
| Sonatype | mcp, pulsemcp | 65 | — |
| Aikido | pypi, pulsemcp | 59.8 | — |
| ToolHive | mcp_registry | — | — |
| AgentAudit | npm, github | — | 5K |
| AgentScore | github, pulsemcp | 57.8 | — |

**We have data on all named competitors.** Snyk is the most deeply indexed with 30+ sub-packages.

**Grading anomaly:** Snyk's MCP entry gets grade E despite being a major security vendor. Our scoring doesn't account for established vendor reputation when the entry has few downloads/stars in our data.

### 3.2 Search query analysis

**We don't have data on:**
- Whether users search for "snyk alternative" or "socket vs nerq"
- Our organic ranking on vibe-coder security terms
- External search engine positioning

**What we know from logs:** No competitor comparison queries visible in preflight analytics (nobody queries "snyk" or "socket" via our API).

---

## DEL 4: Teknisk realism

### 4.1 Performance

| Metric | Value |
|--------|-------|
| API throughput (16 workers) | ~50-100 req/s estimated (not load-tested) |
| Preflight p50 latency | 20-25ms (warm) |
| Preflight cold hit | 2.0-2.3s |
| Redis cache hit rate | **0.81%** (functionally broken) |
| Cloudflare rate limit | 5,000 req/day per IP (x-daily-limit header) |

**If 100x traffic on trust endpoints:** Redis cache is the first bottleneck (0.81% hit rate = every request hits Postgres). With 16 workers and pool_size=5, we'd saturate at ~80 concurrent DB connections. The fix path: Redis eviction policy tuning + larger maxmemory + cache-warming for top packages.

### 4.2 Real-time integration feasibility

| Question | Answer |
|----------|--------|
| Can we deliver trust score for npm on <500ms? | **Yes.** p50 is 20-25ms. p95 ~200ms. |
| Can we guarantee <200ms? | **Only for warm cache.** Cold hits take 2+ seconds. Need cache pre-warming for top 10K packages. |
| What's needed for install-guard? | A CLI that calls `/v1/preflight?target={package}` before `npm install`. The API exists. The CLI doesn't. |
| Latency bottlenecks | 1) Redis 0.81% hit rate. 2) Cold DB queries on first hit. 3) No edge caching for API responses (Cloudflare cf-cache-status: DYNAMIC). |

### 4.3 Blocking technical gaps for MVP

| Gap | Severity | Description |
|-----|----------|-------------|
| **CVE data empty for npm** | BLOCKING | Trust scores can't differentiate security risk without CVE data. `cve_count` is 0 for all 528K packages. OSV.dev enrichment exists but doesn't populate the per-package field. |
| **Stars data empty** | HIGH | 99.9% of npm packages have 0 stars. Scores compress into 30-49 band. Can't rank quality. |
| **No hallucination detection** | HIGH | Can't tell "this package was hallucinated by AI" vs "this package exists but we don't have data." |
| **No CLI/IDE plugin** | HIGH | The API works but there's no install-guard CLI. Developers can't use this at `npm install` time without building it. |
| **No typosquat detection** | MEDIUM | Can't warn about `expres` vs `express` or `reakt` vs `react`. |
| **Redis cache broken** | MEDIUM | 0.81% hit rate makes cold traffic expensive. Fixable with config changes. |
| **7-day data lag** | MEDIUM | New npm packages take up to 7 days to appear. Hallucinated/malicious packages won't be caught in the critical first hours. |

---

## DEL 5: Befintliga tillgångar

### 5.1 What already works for vibe-coders

| Asset | Status | Relevance |
|-------|--------|-----------|
| `/v1/preflight?target={name}` | **Live, <30ms warm** | Core API for trust checks. Returns score, grade, risk, recommendation. |
| `/v1/preflight/batch` | **Live** | Check 50 packages at once (lockfile scan). |
| `/safe/{slug}` pages | **Live, 23 languages** | Human-readable trust reports. SEO traffic already coming. |
| `/was-{slug}-hacked` | **Live** | Security incident lookup. |
| MCP tools (5 tools) | **Live** | `check_compliance`, `discover_agents`, `compare_agents`, `recommend_agent` (with `safe_only` flag). |
| `llms.txt` | **Live** | AI models discover our endpoints. |
| `/v1/trending` | **Live** | "What AI agents are checking right now." |
| Trust score engine | **Live, 5M+ entities** | 5-dimension scoring across 35 sources. |
| Dependency graph | **20K packages** | Growing. 320K edges. |
| Contributor metrics | **5K packages** | Dormant/single-maintainer/team classification. |
| 528K npm packages indexed | **Metadata complete** | Names, descriptions, versions, downloads (partial), licenses. |

### 5.2 Readiness assessment

| Component | Readiness | What exists | What's missing |
|-----------|-----------|-------------|----------------|
| Package trust API | **80%** | Fast, structured, cached. Works for all 528K npm + 94K pypi + 204K crates. | CVE data empty, stars missing, cache broken. |
| Safety pages (SEO) | **90%** | 23 languages, structured data, already ranking for "is X safe." | No vibe-coder-specific messaging. |
| MCP integration | **70%** | 5 tools live, SSE + stdio. AI agents can query trust. | No "check my lockfile" tool, no hallucination check. |
| Hallucination detection | **0%** | Not attempted. | Need registry existence check, typosquat scoring, "does not exist" response. |
| Install-guard CLI | **0%** | No CLI exists. | Need: `npx nerq-check`, wraps preflight API, pre-install hook. |
| CVE per-package data | **10%** | OSV.dev enrichment pipeline exists but data isn't surfaced per-package. | Need: populate `cve_count`/`cve_critical` on `software_registry` from OSV batch results. |
| Dependency risk scoring | **20%** | Graph exists (20K packages). Contributor metrics exist (5K). | Need: transitive risk propagation, "this package depends on 3 dormant maintainers" signal. |
| Real-time new-package detection | **0%** | Batch only (7-day lag). | Need: webhook or polling for npm registry changes. |
| Typosquat detection | **0%** | Not attempted. | Need: name similarity against known packages on query. |

---

## DEL 6: Osäkerheter och begränsningar

### Things we don't know

1. **Actual CVE coverage potential.** OSV.dev has CVE data. Our enrichment pipeline runs weekly. We don't know how many of our 528K npm packages have known CVEs in OSV.dev — we haven't measured the join.

2. **Competitive positioning.** We don't have data on what Google ranks us for. We don't know if "is express safe" queries find us or Snyk/Socket first.

3. **Demand validation.** 105 AI coding tool requests/month is signal but not proof. We don't know if vibe-coders would actually use a trust-check tool if it existed.

4. **Scale readiness.** We haven't load-tested. The 50-100 req/s estimate is theoretical. Redis 0.81% hit rate would make any traffic spike hit Postgres hard.

5. **Latency under load.** p50=25ms is great at current traffic. We don't know p50 at 10x or 100x traffic.

### Things that are better than expected

1. **API already works** at the right latency (<30ms warm) for an install-guard use case.
2. **528K npm packages fully indexed** with trust scores — comparable to Socket's coverage.
3. **Batch API exists** — checking an entire lockfile (50 deps) is a single HTTP call.
4. **23-language safety pages** already ranking in search for "is X safe" queries.
5. **MCP tools are live** — AI coding agents can already query trust scores today.

### Things that are worse than expected

1. **CVE data is zero for npm.** This is the single biggest data gap. A security product without vulnerability data is fundamentally incomplete.
2. **Stars data nearly zero.** This cripples score differentiation — 79% of packages get the same score.
3. **Redis cache is non-functional.** 0.81% hit rate. We're not getting any caching benefit.
4. **No hallucination detection at all.** Not even a "package exists" check.
5. **7-day data lag** means we can't catch supply-chain attacks in the critical first hours/days.

---

*End of reality check. No recommendations included — this is input for strategic decision-making.*
