# Nerq Conversion Audit — 2026-04-17

Prepared: 2026-04-17 · Data window: 2026-03-18 → 2026-04-17 (30 days)
Data source: `/Users/anstudio/agentindex/logs/analytics.db` (20,032,594 rows over 30d)
Methodology: UA-regex bot filter + IP+UA+30-min-gap session proxy. No `session_id` column exists in the schema — sessions are reconstructed.

Raw worksheet: `~/smedjan-audit/` (CSV + MD per task). Journal: `~/smedjan-audit/journal-conversion.md`.

---

## Executive Summary

### True daily human visits (after bot filter)

- **Headline number reported by UA-regex-only filter:** 1,272,097 sessions / 30d ≈ **42,400 sessions/day**.
- **This is heavily inflated.** Key contamination sources, visible in the data:
  - `/v1/preflight` (10,985 sessions) — API preflight probes, not humans.
  - `/.well-known/traffic-advice` (913 sessions) — Cloudflare infra.
  - `/badge/*` (~3,400+ sessions) — SVG badge fetches by VSCode Marketplace, Gitee, GitHub READMEs. Not humans.
  - SG desktop (698K sessions, 1.12 PV/session, 89.9% bounce) and VN desktop+mobile (236K sessions, ≥99.9% bounce, median duration **0.0–0.1 sec**) — data-center / residential-proxy traffic that passes UA regex.
- **Realistic hardened estimate (engaged humans):**
  - Google organic referrals: **~260 sessions/day**
  - US mobile deeply-engaged segment: ~170 sessions/day (1452s avg dur, 17.2 PV/session — outlier but strongly human-shaped)
  - "OTHER" (outside top-10 countries) desktop: ~2,500 sessions/day at 1.87 PV/session
  - **Total defensible engaged humans/day: 2,000–4,000** — roughly 1–2% of the UA-regex-filtered number.
- AI-platform referrals (ChatGPT, Claude, Perplexity, Gemini, Copilot, you.com, phind): **54 sessions across 30 days ≈ <2/day.** Despite Nerq's welcome-all-bots stance, AI platforms are not yet driving human referral traffic of any consequence.

### Top 3 traffic leakage points
1. **Zero CTAs on top entry pages.** Sampled 50 top entry pages via curl; **49 of 50 have 0 CTA elements**. The only CTA is a single button on `/crypto`. Visitors land, find no next-step affordance, bounce.
2. **Homepage bounce is 57.9% with no retention capture.** Homepage is #2 entry (4,585 sessions). Top next-clicks are self-refresh (`/`→`/`) and `/v1/trending` (a JSON endpoint). No email capture, no watch-button, no "get a digest" surface.
3. **`/compare/*` category (single largest thematic entry cluster) bounces at 98–100%.** Google brings readers to pairwise comparison pages; pages render but have no onward path that fits reader intent.

### Top 3 quick wins (S-effort, high confidence)
1. **Fix the newsletter send job** — hardcoded to retired `claude-sonnet-4-20250514`, zero sends for 2+ weeks (per CLAUDE.md). 1-line change unblocks the entire retention loop.
2. **Add one email-capture form → `compliance_subscribers`.** Table exists (5 rows today). Even 0.5% capture on 3,000 engaged daily humans = ~15 subs/day = ~450/month.
3. **Add an email modal on `/zarq/doc`.** Only page on the site with <15% bounce (12.2%) and a high onward-click rate (494 of 590 sessions go on to `/zarq/docs`). Users are leaning in — capture them.

### Retention present? **Functionally NO.**

- `compliance_subscribers` table exists but holds only **5 rows total**.
- No `users` / `accounts` / `sessions` / `watchlists` / `favorites` tables anywhere in Postgres.
- Newsletter job exists but broken (retired model hardcoded).
- RSS feeds live at `/feed/*` but only **14 human hits / 30d** on the top feed — invisible to users.
- `user_reviews` = 20 rows all-time. `agent_reviews` = 3. `checker_usage` = 17. These are the only behavioral-retention tables and none is receiving meaningful traffic.
- **Net:** 1.5M UA-regex-filtered human pageviews in 30 days converted into **≤30 retained identities across all mechanisms combined**.

---

## 1. Traffic Baseline

Detailed daily table: `~/smedjan-audit/traffic_baseline.csv` / `.md`.

30-day rollup (UA-regex filtered, `is_human(user_agent)=1`, `status<400`, `GET` only):

| Metric | Value |
|---|---:|
| Unique IPs | 443,628 |
| Sessions | 1,272,097 |
| Pageviews | 1,457,205 (approx; per daily rollup sum) |
| Avg PV/session | 1.15 |
| Avg bounce | ~95% |
| Avg session duration | 40–90 seconds |

Daily trajectory (sample rows):

| Day | UniqueIPs | Sessions | PV/Session | Bounce% |
|---|---:|---:|---:|---:|
| 2026-03-18 | 5,357 | 5,874 | 7.29 | 94.4 |
| 2026-04-01 | 37,044 | 38,203 | 1.04 | 98.9 |
| 2026-04-10 | 44,673 | 73,296 | 1.12 | 94.8 |
| 2026-04-16 | 40,198 | 193,578 | 1.14 | 88.6 |
| 2026-04-17 | 8,426 (partial day) | 72,328 | 1.16 | 86.9 |

The rising session counts from 2026-04-06 onward, with `returning_ip_sessions` growing from 5K/day to 156K/day by 2026-04-16, are **not human-growth signals**. The IP base did not scale proportionally. This is repeat scripted traffic (residential/cloud proxies hitting the same URLs) that evades the UA-regex filter.

### Top-10 country/region breakdown

| Rank | Country | Sessions (30d) |
|---:|---|---:|
| 1 | SG | 698,341 |
| 2 | VN | 236,725 |
| 3 | (no country) | 80,455 |
| 4 | US | 70,847 |
| 5 | CN | 23,714 |
| 6 | BR | 13,836 |
| 7 | HK | 13,234 |
| 8 | IQ | 10,249 |
| 9 | BD | 8,028 |
| 10 | MX | 7,351 |

SG + VN alone account for **73.5%** of all sessions, with bounce ≥90% and session durations ≤0.1s on VN — this is a clear datacenter fingerprint that survived UA filtering because the residential-proxy networks rotate legitimate browser UA strings. True engaged human traffic is substantially in the "OTHER" (rank 11+ countries) and US mobile buckets.

---

## 2. Entry Pages — where humans land

Full CSV: `~/smedjan-audit/entry_pages.csv`.

Top 15 entry pages after UA filter (but before removing machine endpoints):

| # | Path | Sessions | Bounce% | Top referrer | Class |
|---:|---|---:|---:|---|---|
| 1 | `/v1/preflight` | 10,985 | 87.4 | (direct) | machine-endpoint ← should remove |
| 2 | `/` | 4,585 | 57.9 | (direct) + google.com 1,087 | best human entry |
| 3 | `/badge/olasunkanmi-SE/codebuddy` | 1,219 | 94.3 | VSCode Marketplace | machine-endpoint |
| 4 | `/.well-known/traffic-advice` | 913 | 99.1 | CF infra | machine-endpoint |
| 5 | `/badge/RTGS2017/NagaAgent` | 686 | 91.7 | | machine-endpoint |
| 6 | `/badge/MGdaasLab/WHartTest` | 667 | 90.7 | gitee.com | machine-endpoint |
| 7 | **`/zarq/doc`** | 590 | **12.2** | (direct) | **high-engagement — the site's only success** |
| 8 | `/kya` | 376 | 96.0 | | mid |
| 11 | `/v1/trending` | 159 | 78.0 | nerq.ai (self) | API endpoint called by homepage JS |
| 12–20 | `/compare/*` pages | 90–160 each | 93.9–100.0 | google.com or (direct) | Google-crawled, bouncing hard |

**Actual human-page ranking after removing machine endpoints:**
1. `/` (homepage) — 4,585 sessions, 57.9% bounce
2. `/zarq/doc` — 590 sessions, **12.2% bounce** (site's best engagement)
3. `/kya` — 376 sessions, 96% bounce
4. `/safe/mpfaffenberger/code_puppy` — 100 sessions, 70% bounce
5. `/compare/*` cluster — ~1,500 combined sessions, ~96% avg bounce

---

## 3. Exit Pages & Frustration

Full CSV: `~/smedjan-audit/exit_paths.csv`.

**Frustration-flag exits** (median last-hop time <10s AND >50% single-page sessions):

- `/` (homepage) — 3,254 exits, 81.6% single-page
- `/kya` — 386 exits, 93.5% single-page
- `/compare/langgenius-dify-vs-openclaw-openclaw` — 157 exits, 99.4% single-page
- `/compare/open-webui-open-webui-vs-openclaw-openclaw` — 133 exits, 98.5% single-page
- `/badge/*` cluster — all flagged frustrations (but these are machine endpoints)

**Non-frustration exits** (readers stayed, then left — not broken experience):

- `/zarq/docs` — 421 exits, only 12.4% single-page (most arrived from /zarq/doc)
- `/v1/agents/chain-concentration-risk` — 262 exits, 0.8% single-page (API endpoint chain from homepage JS)
- `/gateway` — 221 exits, 685.8s median last-hop time. This is actual engaged reading.

Gateway (685s median read time, 28% single-page) is the second engagement diamond after `/zarq/doc`. Both pages should be email-capture priority targets.

---

## 4. User Flows

Full file: `~/smedjan-audit/user_flows.md`.

**Two classes of flow dominate:**

**Class A — Humans reading Zarq docs (the success flow):**
- `/zarq/doc → /zarq/docs` (356 sessions)
- `/zarq/doc → /zarq/docs → /gateway` (129 sessions)
- This is the only human-engaged multi-hop flow at scale.

**Class B — Homepage JS calling API endpoints (logged as sessions):**
- `/ → /v1/agents/structural-collapse → /v1/agents/chain-concentration-risk → /v1/yield/traps → /v1/yield/insights` and permutations (~600+ combined sessions across flow rows 5–20)
- These are the homepage's embedded dashboard widgets firing XHR calls, logged as if they were page-to-page navigation. **This noise pollutes every top-flow measurement.**

**Class C — Repeat refresh:**
- `/ → /` (459 sessions) and `/ → / → /` (54 sessions) — browsers refreshing the homepage, likely automated.

---

## 5. AI-Referred Traffic

Full file: `~/smedjan-audit/ai_referred_traffic.md`.

| Source | Sessions / 30d | PV/Session | Bounce% | AvgDur(s) |
|---|---:|---:|---:|---:|
| **AI platforms combined** (ChatGPT / Claude / Perplexity / Gemini / you.com / phind / Copilot) | **54** | 3.54 | 68.5 | 82.1 |
| Google organic | 7,809 | 1.48 | 86.7 | 10.1 |
| Bing / MSFT | 580 | 1.56 | 62.9 | 8.3 |
| Direct / no referrer | 1,247,913 | 1.16 | 93.5 | 57.2 |

**Findings:**
- AI-referred sessions are the smallest bucket by 2+ orders of magnitude, but **have the best quality metrics** of any referring channel (3.54 PV/session, 68.5% bounce, 82s avg duration).
- Daily AI sessions trend: 1–6 per day across the 30-day window, with no obvious trend direction.
- Google is the biggest real human-referral source (~260 sessions/day) but with 1.48 PV/session and 10s duration, quality is mediocre.
- The AI-welcoming strategy is producing **crawl traffic** (visible in `requests_daily_new_ai` and the wider bot analytics) but **not human referral traffic**. The two are decoupled: welcoming crawlers does not automatically translate to LLMs surfacing Nerq links in answers that humans then click.

Top 10 AI landing pages in the 54-session sample include `/crypto/*`, `/safe/*`, and homepage — consistent with AI tools surfacing Nerq in response to "is X safe" queries. Small-N but the quality signals are promising.

---

## 6. On-Page Engagement

Full file: `~/smedjan-audit/on_page_engagement.md`.

Sampled 50 of top entry pages via curl. Feature counts:

- **CTA buttons: 0 on 49/50 pages** (only `/crypto` has 1).
- **Internal search input: 0 on 50/50.**
- **Sortable tables: 0 on 50/50.**
- **Related-content sections:** strong on `/compare/*` (13–17 markers per page) — but these pages bounce at 98–100%, so the related links aren't being clicked.
- **Social share buttons: 0 across the sample.**
- **Page size outlier: `/compare` index returns 7,675,791 bytes** (7.6 MB HTML). On mobile this is a >30s render on typical connections. Guaranteed bounce.
- **`/badge/*` pages are ~1.8 KB** of SVG shield markup — correctly tiny for their purpose, confirming these aren't HTML pages humans interact with.

**Correlation signal:** pages with `related ≥ 2` have bounce 94% vs pages with `<2` at 85%. Related-content markers alone don't help when the page has no CTA to anchor intent.

---

## Appendices

- `~/smedjan-audit/traffic_baseline.csv` / `.md` — Daily table, top-10 country.
- `~/smedjan-audit/entry_pages.csv` — Top 50 entries with top-3 referrers, top-3 next-pages, bounce, class.
- `~/smedjan-audit/exit_paths.csv` — Top 30 exits with frustration flag.
- `~/smedjan-audit/user_flows.md` — Top 20 flows.
- `~/smedjan-audit/ai_referred_traffic.md` — AI referer analysis + platform breakdown.
- `~/smedjan-audit/retention_state.md` — Retention infra inventory.
- `~/smedjan-audit/on_page_engagement.md` — 50-page curl sample.
- `~/smedjan-audit/internal_search.md` — `/search` usage.
- `~/smedjan-audit/geo_device.md` — Geo × device split with outliers.
- `~/smedjan-audit/conversion_hypotheses.md` — 10 ranked interventions.

---

## Ranked Interventions — Top 5

(Full list of 10 in `~/smedjan-audit/conversion_hypotheses.md`.)

1. **Fix newsletter send job.** XS effort. Unblocks the retention loop. Known-broken per CLAUDE.md.
2. **Add email-capture form feeding `compliance_subscribers`.** S effort. Table ready. Expected 450+ subs/month at modest capture rate.
3. **Add one CTA block to shared templates (homepage, compare, token, safe, zarq).** M effort. Reverses the "0 CTAs on 49/50 pages" finding. Expected 5–15pp bounce reduction.
4. **Exit-intent / scroll modal on `/zarq/doc` and `/gateway`.** S effort. These are the only two pages where users demonstrably lean in (12% bounce, 685s read time). Highest-probability conversion surface on the site.
5. **Stop classifying `/badge/*`, `/.well-known/*`, `/v1/preflight`, `/v1/trending`, `/v1/agents/*`, `/v1/yield/*` as human sessions.** XS effort in `analytics.py`. No traffic change but every conversion-rate KPI becomes ~2× more honest, making all future A/B readouts trustworthy.

---

## Known Gaps & Caveats

1. **Session proxy is lossy.** IP+UA+30-min-gap over-counts when NAT / shared-proxy collapses many users onto one (IP,UA) tuple (single session = many humans), and under-counts when one human's IP changes mid-session (1 human = multiple sessions). With no first-party cookie/session-id in the schema, this is the best available.
2. **Bot UA regex misses residential-proxy and headless-Chrome traffic** presenting legitimate Mozilla UAs. The SG/VN/CN fingerprint strongly suggests 60–80% of the UA-regex-filtered "human" sessions are still machines. Treat the "engaged human 2–4K/day" figure as the working baseline, not the raw 42K/day.
3. **Homepage XHR widgets are logged as pageviews.** `/v1/agents/*` and `/v1/yield/*` showing up in user flows is the homepage's dashboard firing, not humans navigating. A proper instrumentation fix would tag these as `visitor_type='api_xhr'` in the same hit.
4. **On-page engagement sample is curl-based, not headless-browser rendered.** Pages that rely on JS to inject CTAs may undercount CTA presence in the sample. Manual spot-checks of homepage and `/zarq/doc` confirm the finding directionally — CTAs are thin to absent.
5. **AI-referred sample (54 sessions) is too small for statistical conclusions** beyond the directional quality signal.
6. **Conversion-events table (`conversion_events`) holds 100 rows all-time, all `cta_click`.** The only existing conversion telemetry is a single CTA that's not reaching users.
