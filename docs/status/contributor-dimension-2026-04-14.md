# Contributor Activity Dimension — Deployed 2026-04-14

## What was built

**Active contributors as a descriptive trust score signal.** Based on Fas 2 DEL B research finding that incident repositories have 5x fewer active contributors than healthy controls.

### Data collection

- **Script:** `scripts/collect_contributor_metrics.py`
- **Source:** GitHub REST API (commits + contributors endpoints)
- **Metrics per entity:**
  - `active_contributors_6mo` — unique commit authors in last 6 months
  - `total_contributors` — all-time contributor count
  - `top_contributor_pct` — concentration: % of commits by top contributor
  - `contributor_tier` — classification (see below)
- **Rate:** ~2 API calls per entity, 0.5s delay, ~2500 entities/hr
- **Schedule:** Monthly via `com.nerq.contributor-metrics` LaunchAgent (1st of month, 04:00)
- **Storage:** `contributor_metrics` table in Postgres

### Tier classification

| Tier | Active contributors (6mo) | Meaning |
|------|--------------------------|---------|
| dormant | 0 | No commits in 6 months |
| single-maintainer | 1 | Bus factor = 1 |
| small-team | 2-5 | Limited but active |
| active-community | 6+ | Healthy contributor base |

### Trust score integration

Integrated into the **maintenance dimension** (weight: 20% of total score) as an adjustment of ±15 points maximum:

| Tier | Adjustment | Rationale |
|------|-----------|-----------|
| active-community | +10 | Strong maintenance signal |
| small-team | +5 | Adequate maintenance |
| single-maintainer | -5 | Concentration risk |
| dormant | -15 | No recent activity |

**Conservative by design.** The adjustment is capped at ±15 points on a dimension weighted 20%, meaning the maximum impact on the overall trust score is ±3 points. This prevents mature, stable packages from being unfairly penalized.

### Exposure

1. **Entity pages** (`/safe/{slug}`): Shows contributor count, tier badge (color-coded), total contributors, and concentration metric
2. **Trust Score API** (`/api/v1/trust-score/{id}`): Returns `contributor_metrics` object with all 4 fields
3. **Preflight API** (`/v1/preflight`): Returns `contributor_metrics` nested under `activity` object
4. **MCP tools**: Automatically included via preflight responses

### Initial data (55 entities)

From test batch of top-55 GitHub entities:
- **Active community:** 42 (76%) — avg 46.9 active contributors
- **Dormant:** 6 (11%) — avg 93.4% concentration
- **Small team:** 5 (9%) — avg 2.2 active, 54.4% concentration  
- **Single maintainer:** 2 (4%) — avg 93.0% concentration

### Score impact estimate

With ±15 max on maintenance (20% weight), the maximum overall score change is:
- Best case: +3.0 points (active-community with +10 on maintenance)
- Worst case: -3.0 points (dormant with -15 on maintenance)
- Most entities: no change (no contributor data yet, or within ±1 point)

## What this is NOT

**This is descriptive, not predictive.** The Fas 2 DEL B research showed:

1. Signal exists: incident repos have fewer contributors (5x ratio)
2. Signal is not predictive: >99% false positive rate at deployment scale
3. "Dormant" does not mean "bad" — mature packages (e.g., `is-number`, `inherits`) can be stable without recent commits

The contributor tier is an **observable fact**, not a judgment. Users draw their own conclusions.

## Potential false signals to watch

1. **Mature stable packages** marked dormant — these are fine, the ±15 cap protects them
2. **Monorepo contributors** — GitHub API counts per-repo, not per-package
3. **Bot accounts** inflating contributor counts (Dependabot, Renovate)
4. **Fork-heavy repos** where contributors work on forks, not main repo

## Files modified

- `scripts/collect_contributor_metrics.py` — new data collector
- `compute_trust_score.py` — `score_maintenance()` now accepts contributor data
- `agentindex/seo_pages.py` — entity page + trust API include contributor metrics
- `agentindex/preflight.py` — preflight response includes contributor metrics
