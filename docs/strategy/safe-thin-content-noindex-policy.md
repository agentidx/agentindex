# Safe/<slug> Thin-Content Noindex Policy — Design

> **Status**: design — **not** implemented. Needs Anders sign-off before a
> separate L-task ships the renderer changes. This task (A4-design-thin-
> content-noindex-policy) is read-only; no production rendering or sitemap
> behaviour is changed by writing this doc.
>
> **Driver audit**: `~/smedjan/audits/A4-20260419T093126Z.md`
> (duplicate_page_detection). ~13,650 indexable `/safe/<slug>` pages are
> ≥95% identical by raw-HTML 6-gram Jaccard; ~47,275 share a near-identical
> template body. Root cause is the `erc8004` source (34,434 slugs, 56.3%
> of the /safe/ universe) which carries no substantive metadata, plus
> three secondary sparse-metadata sources (`pulsemcp`, `mcp_registry`,
> `agentverse`).

---

## 1. Threshold rule (the "thin-content" predicate)

A `/safe/<slug>` page is considered **thin** — and therefore a candidate
for noindex + hub-collapse — if **all** of the following hold at render
time:

```
thin(slug) :=
     source IN {erc8004, pulsemcp, agentverse, mcp_registry}
 AND (stars IS NULL OR stars < 1)
 AND is_verified = false
 AND no CVE record is attached (cve_count = 0 / absent)
 AND website_cache text is absent or < 400 chars of visible body
 AND trust_grade IN {C-, C, C+}     -- i.e. no reviewer-assigned lift
```

Notes on each clause:

- **Source gate** is the primary filter. The A4 audit confirms that every
  strict raw-duplicate cluster of size ≥ 3 in the 600-slug sample is
  dominated by these four sources. The `github` source is intentionally
  **excluded** from the thin-content rule even for stars < 1, because a
  `github`-sourced page has a real upstream README and repo metadata the
  renderer can pull in. We can revisit a `github <1 star` pass in a
  follow-up if the initial cohort doesn't move the quality signal.
- **Star clause** keeps legit sparse-source entities (e.g. a `pulsemcp`
  server with a hand-curated description and ≥1 star) out of the cohort.
- **Verified clause** is a safety net: any human-curated entry, even on
  a thin source, is indexable.
- **CVE clause** is load-bearing: a page with an actual CVE *is* unique
  content and must never be de-indexed, even if every other field is
  bare. A CVE is the highest-signal attribute the `/safe/` template can
  carry.
- **Website-cache clause** protects `/safe/` pages that happen to have
  a substantive fetched description from being lumped in with empty
  templates.
- **Trust-grade clause** is a cheap proxy for "the renderer added no
  qualitative lift." Any B-or-better entry is treated as
  not-thin regardless of source.

### Escape hatch

The policy MUST ship behind a config file
(`agentindex/config/thin_content_sources.json` or equivalent) so that
the thin-source list and star/grade thresholds can be re-tuned without
a deploy. This is non-negotiable — the rule will be wrong about some
tail of the catalog and we need a fast revert path.

---

## 2. Slug counts per source (the affected population)

Computed from `agentindex/agent_safety_slugs.json` (61,132 slugs,
snapshot 2026-04-19).

### 2a. Universe by source

| source           |   slugs | % of universe | metadata richness |
| ---------------- | ------: | ------------: | ----------------- |
| `erc8004`        |  34,434 |        56.3 % | **none** (auto-registered) |
| `github`         |  17,306 |        28.3 % | variable (README + stars) |
| `pulsemcp`       |   4,964 |         8.1 % | sparse |
| `mcp_registry`   |   2,489 |         4.1 % | sparse |
| `agentverse`     |   1,121 |         1.8 % | sparse |
| `lobehub`        |     275 |         0.4 % | curated |
| `mcp`            |     271 |         0.4 % | sparse |
| everything else  |     272 |         0.4 % | varies |
| **total**        |  61,132 |       100.0 % |                   |

### 2b. Cohort hit by the threshold rule (stars<1 AND unverified)

| source           |  total  | stars<1 AND unverified | % of that source | % of universe |
| ---------------- | ------: | ---------------------: | ---------------: | ------------: |
| `erc8004`        |  34,434 |             **34,234** |           99.4 % |        56.0 % |
| `pulsemcp`       |   4,964 |              **1,894** |           38.2 % |         3.1 % |
| `mcp_registry`   |   2,489 |              **2,487** |           99.9 % |         4.1 % |
| `agentverse`     |   1,121 |              **1,121** |          100.0 % |         1.8 % |
| **subtotal**     |  43,008 |             **39,736** |           92.4 % |       **65.0 %** |

After further narrowing by trust_grade ∈ {C-,C,C+} (B-and-up entries
on these sources are promoted by an earlier reviewer pass and should
remain indexable):

| source           | thin-rule cohort (est.) |
| ---------------- | ----------------------: |
| `erc8004`        |               ~33,700   |
| `pulsemcp`       |                ~1,800   |
| `mcp_registry`   |                ~2,400   |
| `agentverse`     |                ~1,100   |
| **total thin**   |              **~39,000** |

This is consistent with the A4 template-level ceiling of ~47,275 (which
was computed on the 600-slug sample and included some `github <5` stars);
the ~39K figure here is the conservative erc8004+mcp+agentverse tranche.

### 2c. Projected index impact

- **Today (all 61,132 indexable, ~14K Google-deduped)**:
  Google indexes ≈47K, de-indexes ≈14K silently, and the entire
  `/safe/` directory inherits a thin-content quality signal that
  suppresses rank for the real pages (`langchain`, `openai`, the
  top-stars GitHub cohort).
- **After policy ships at 39K noindex**:
  Google indexes ≈22K high-quality `/safe/` pages plus the hub page
  (see §3). Rank uplift expected on the remaining 22K because the
  site-level thin-content signal is removed.
- **Crawl-budget recovery**: Googlebot fetches ≈150K `/safe/` URLs/month
  (ratio inferred from the AI-bot log in the 2026-04-17 citation audit).
  Removing 39K URLs from the sitemap + adding `noindex` on the pages
  themselves should cut `/safe/` crawl volume ≈50% and free that budget
  for new comparison/vertical pages.

---

## 3. Recommendation: **noindex + hub-collapse, not one or the other**

Two mechanisms are on the table. I recommend shipping **both**, in
that order, rather than picking between them.

### 3a. Mechanism A — per-slug `noindex`

- Add `<meta name="robots" content="noindex,follow">` to the rendered
  `/safe/<slug>` page when `thin(slug)` evaluates true.
- Remove those slugs from `sitemap.xml`.
- Keep the URL 200-responding. Keep the canonical tag. Keep the page
  body — the page is still reachable via direct link, API, or bot
  crawl.
- `follow` (not `nofollow`) is deliberate: we still want link equity
  to flow from e.g. a glyph-XXXX page to the eventual hub.

### 3b. Mechanism B — parallel hub pages

Create one *indexable* hub per thin source:

- `/safe/erc8004` — registry summary: count, aggregate trust-grade
  distribution, top 20 highest-scoring entries, methodology link,
  list of top 5 CVE-bearing entries (if any), "browse all 34K"
  programmatic catalog link.
- `/safe/pulsemcp`, `/safe/mcp-registry`, `/safe/agentverse` — same
  template.

The hubs are where the crawl and rank signal concentrates. Each thin
per-slug page gets an in-body "See the {source} registry overview →"
link that pushes the reader toward the hub. The hubs themselves are
substantive content (aggregate stats, real rankings, real CVE
surfaces) so they carry their own quality signal rather than
re-templating the thin bodies.

### 3c. Why both — and the rationale against "welcome all traffic"

CLAUDE.md §5: *"Welcome all traffic. Do not propose blocking or
rate-limiting crawlers without explicit user reconsideration. The
default answer is always 'let them in.'"*

This policy **does not block any traffic**, and that is the specific
point I want on record before we ship:

1. **Crawlers still get a 200 response** on every per-slug thin page.
   `noindex` is a ranking signal to search engines, not a gate. Bots
   fetch, parse, and (if they want) cite the content. AI crawlers
   (GPTBot, ClaudeBot, PerplexityBot) mostly ignore `noindex` entirely
   — they will keep ingesting these pages.
2. **Direct links keep working.** A user who lands on
   `/safe/glyph-7204` from an AI citation, a bookmark, or a Discord
   link gets the same page they get today. No redirect, no 404.
3. **The sitemap removal is a discovery-not-access change.**
   Googlebot will still crawl a page it discovers via internal links
   or backlinks; we are only declining to *actively advertise* these
   URLs for indexing.
4. **The hub pages are a net traffic expansion, not contraction.**
   We are replacing 39K near-identical templated pages in the index
   with one high-quality indexable aggregator per source (+4 new
   indexable URLs that will rank for high-intent aggregate queries
   like "erc8004 agents safety").

Net direction of the change: more total bots served (hubs give them
structured aggregate content they can cite), fewer duplicate pages
wasted in the index, no URLs taken offline. That is philosophically
aligned with the welcome-all-traffic rule.

**What this policy is NOT:**

- **Not a `robots.txt` Disallow.** We are explicitly not touching
  `robots.txt`.
- **Not a 404 / 410.** The URLs continue to resolve.
- **Not a 301 redirect to the hub.** That would break direct links,
  AI citations, and bookmark traffic. Noindex preserves all three.
- **Not a rate-limit on any user-agent.** No change to WAF, no change
  to Cloudflare, no change to bot tolerance.

### 3d. Mechanisms rejected (and why)

| option                                          | rejected because |
| ----------------------------------------------- | ---------------- |
| 404 on thin slugs                               | breaks direct links, bookmarks, AI citations; violates welcome-all-traffic |
| 301 redirect thin → hub                         | loses per-slug citability; opaque to readers landing from AI chat |
| `rel="canonical"` → hub                         | Google ignores canonical when the target body is materially different; this would just silently fail |
| `robots.txt` Disallow `/safe/erc8004-*`         | blocks AI crawlers from reading the page at all — direct conflict with welcome-all-traffic |
| Do nothing                                      | the site-level thin-content quality signal already suppresses the real `/safe/` pages (see A4 §Why this matters) |

---

## 4. Canary rollout plan

### 4a. Canary scope

- **Phase 0** (this doc signed off) — no production change.
- **Phase 1 (canary, <5%)** — apply `thin()` to a **hash-stable 3%
  slice of erc8004 slugs only** (`hash(slug) % 100 < 3` — the same
  hash bucketing used for A/B traffic splits elsewhere in the
  codebase). That is ~1,030 slugs, ≈1.7 % of the /safe/ universe,
  well under the 5% envelope.
- **Phase 2** — full erc8004 cohort (34K) once Phase 1 clears its
  success gates.
- **Phase 3** — add `pulsemcp` + `mcp_registry` + `agentverse`
  (+5.3K slugs).
- **Phase 4** — ship the four hub pages (§3b). Phased after noindex
  so we can measure the hub uplift independently of the noindex
  signal.

Each phase is a separate L-task with its own approval gate. Do not
batch.

### 4b. Observations window

- Phase 1: 14 days. Google typically takes 10–14 days to re-crawl
  and act on a `noindex` signal; any faster evaluation will be
  noise.
- Phase 2: 14 days before Phase 3.
- Phase 3: 21 days before Phase 4 (we want to see the sitemap
  recovery curve).

### 4c. Success metrics (the go/no-go gates)

| metric                                            | signal to look for | source |
| ------------------------------------------------- | ------------------ | ------ |
| GSC "Indexed, not submitted in sitemap" / "Crawled — currently not indexed" bucket for canary cohort | should rise by ~1K over 14 days (these are the noindex-ed pages being seen and dropped); a flat line means the tag isn't being emitted | GSC Coverage report |
| GSC "Submitted and indexed" count, site-wide      | should stay flat or rise (the canary is <2% of URLs; a drop >5% means something unrelated broke) | GSC Coverage |
| Googlebot crawl rate on `/safe/*`                 | should drop ~2% in Phase 1, proportional in later phases | Cloudflare log → `zarq_crawl_events` |
| Non-canary `/safe/*` average GSC impressions      | **primary quality-signal gate**: should rise 5–20% by day 14 as the site-level thin-content drag lifts | GSC Performance |
| AI-bot (GPTBot/ClaudeBot/Perplexity) fetch rate on canary cohort | should stay flat (they ignore noindex) — this is the welcome-all-traffic sanity check | Cloudflare log |
| 404 rate on canary cohort                         | **must be zero**; any 404 means the renderer change went wrong | access log |
| Direct-traffic sessions on canary slugs (non-bot) | should stay flat; a drop means we broke an inbound link path we didn't expect | analytics_mirror |

**Rollback trigger** — revert the canary if **any** of:

1. Site-wide "Submitted and indexed" drops >5% over 7 days.
2. Non-canary `/safe/*` impressions fall instead of rising.
3. 404 rate on canary cohort is non-zero.
4. AI-bot fetch rate on canary cohort drops more than 20%.

Revert is trivial: the policy is config-gated (§1 "Escape hatch"), so
rollback is a config flip, not a deploy.

### 4d. Explicit non-goals for the canary

- We are **not** measuring revenue impact. The /safe/ pages do not
  monetize directly today, and the monetization trigger in CLAUDE.md
  (150K human visits/day for 7 days) is nowhere near.
- We are **not** measuring AI-citation rate changes. The 2026-04-17
  citation audit established that /safe/ citations are dominated by
  brand queries, and 39K templated pages contribute ~0 organic
  citations regardless of their index status. If hubs (Phase 4)
  start getting cited, that's upside, not a gate.
- We are **not** touching the `/is-<slug>-safe` alias canonical path
  — A4 confirmed it's handled correctly by the existing canonical
  tag. The `L2_BLOCK_2A` shadow-output divergence flagged in the
  A4 audit §5 is a separate ticket and not a prerequisite for this
  policy.

---

## 5. Implementation notes for the downstream L-task

The L-task that actually ships this will need to:

1. Add a `thin_content.py` helper in `agentindex/agentindex/safety/`
   (or similar) exposing a single `is_thin(entry: dict) -> bool`
   function whose behaviour is driven by
   `agentindex/config/thin_content_sources.json`.
2. Wire it into `_render_agent_page` in `agent_safety_pages.py` —
   when `is_thin(entry)` returns True, the renderer emits the
   `<meta name="robots" content="noindex,follow">` tag. No other
   body change.
3. Wire it into the sitemap generator — filter thin slugs out of
   `sitemap.xml`.
4. Add a telemetry counter (`safe.thin_content.rendered`,
   `safe.thin_content.noindex_applied`) so we can watch the canary
   hit rate without scraping logs.
5. Do **not** touch the alias path in `agent_safety_pages.py:9643`
   in this change. Same policy is applied there via the same
   helper, but that is a separate commit for cleanliness.
6. The hub pages (§3b, Phase 4) live in a separate file
   (`safe_hub_pages.py`) and are explicitly out of scope for the
   noindex L-task.

---

## 6. Open questions for Anders

1. **Do we want the hubs at `/safe/{source}` or `/safe/registry/{source}`?**
   The former is cleaner; the latter keeps the hub namespace
   separate. I lean `/safe/{source}` for link-equity reasons.
2. **Phase 1 cohort size — 3% or 5%?** 5% is ~1,720 slugs, still
   under the envelope; 3% gives a quieter signal. I lean 3% for
   phase 1 and widen to 10% for a phase 1.5 before the full erc8004
   rollout.
3. **Do we want the `/safe/<slug>` page to render a visible
   "see aggregate view" banner for humans who land on a thin slug
   from an AI citation?** Low-risk UX add; out of scope for the
   noindex change itself but worth deciding before Phase 4 so the
   hub launch pairs with a discoverability nudge.

---

## 7. Acceptance-criteria cross-reference

| criterion from task spec                                              | covered in |
| --------------------------------------------------------------------- | ---------- |
| (a) explicit threshold rule                                           | §1         |
| (b) slug-count table per source                                       | §2         |
| (c) noindex-vs-hub recommendation with welcome-all-traffic rationale  | §3         |
| (d) canary rollout plan with success metrics                          | §4         |
| no production code / rendering behaviour changed                      | §5 (this doc is read-only; all code changes are deferred to a separate L-task) |
