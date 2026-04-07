# Vertical Roadmap — Data Sources Needed

## Currently Published (6 verticals, pass quality gate)
- **npm** (528K) — downloads via npm API, stars via GitHub
- **pypi** (94K) — downloads via PyPI API, license from metadata
- **android** (58K) — installs from Google Play
- **ios** (48K) — ratings/installs from App Store
- **crypto** (211) — synced from ZARQ crypto_trust.db
- **vpn** (103) — manually enriched, highest quality

## Near-Publishable (need enrichment running, 1-2 weeks)
| Registry | Size | Blocking | Data Source | Effort |
|----------|------|----------|-------------|--------|
| wordpress | 57K | range 9 < 15 | Has downloads+stars already. Needs rescore with wider buckets. | 2 hours |
| steam | 45K | range 13 < 15 | Has players (stars). Needs wider scoring buckets. | 2 hours |
| gems | 10K | stddev 4.9 < 5 | Has downloads+license. Borderline — may pass with enrichment. | 1 day |
| crates | 204K | stddev 4.5, range 10 | Downloads exist (58%). Needs stars from GitHub. | 1 week |
| packagist | 114K | stddev 3.9, range 9 | Downloads+stars exist. Needs wider scoring. | 2 hours |
| website | 501K | stddev 4.6, range 10 | Tranco rank exists. Formula at 70% pop weight. Data-limited. | Done (limited by data distribution) |

## Needs New Enrichment (2-4 weeks)
| Registry | Size | Data Source | API | Rate | Effort |
|----------|------|------------|-----|------|--------|
| nuget | 641K | NuGet Search API (totalDownloads) | azuresearch-usnc.nuget.org | 128/batch | Running (283 done) |
| go | 22K | GitHub API (stars/forks via repo URL) | api.github.com | 5000/hr with token | Running (needs GITHUB_TOKEN) |
| chrome | 44K | Chrome Web Store (user count) | Scrape/unofficial | 1/2s | Running |
| firefox | 29K | AMO API v5 (average_daily_users) | addons.mozilla.org | 1/s | Running |
| vscode | 49K | VS Code Marketplace API | marketplace.visualstudio.com | TBD | Not started |

## Needs External Data Sources (backlog — after revenue sprint)
| Registry | Size | Data Source Needed | Where to Get It | Effort |
|----------|------|-------------------|-----------------|--------|
| country | 158 | Global Peace Index, Numbeo Safety Index, WHO health data | GPI: visionofhumanity.org (annual PDF); Numbeo: API ($) | 1 week |
| city | 3K | Numbeo crime index, Nomad List safety scores | Numbeo API or scrape; nomadlist.com | 1 week |
| charity | 504 | Charity Navigator ratings, GuideStar data | charitynavigator.org API (free tier); guidestar.org | 1 week |
| ingredient | 669 | FDA GRAS status, EU food additive regulations, IARC classifications | FDA open data; EFSA database; IARC monographs | 2 weeks |
| supplement | 584 | ConsumerLab ratings, NIH ODS fact sheets, Labdoor grades | consumerlab.com ($); ods.od.nih.gov (free) | 2 weeks |
| cosmetic_ingredient | 584 | EWG Skin Deep scores, EU CosIng database | ewg.org/skindeep (scrape); ec.europa.eu/growth/cosmetics | 1 week |
| saas | 5K | G2 ratings, Capterra reviews, product features | g2.com API ($); capterra.com | 2 weeks |
| ai_tool | 1.8K | GitHub stars, user reviews, feature comparison | GitHub API + manual curation | 1 week |

## Priority Order for Revenue Sprint
1. Fix near-publishable (wordpress, steam, gems — scoring formula only, 1 day)
2. Wait for enrichment crawlers (nuget, go, chrome, firefox — running, 1-2 weeks)
3. After revenue established: external data sources (country, charity, ingredient — backlog)
