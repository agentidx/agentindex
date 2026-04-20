# Write-Path Audit — One-Shot Seeders Using get_session() for Writes

## Datum: 2026-04-20

## Bakgrund

Under DD-implementation steg 2f upptäcktes att `calculate_scores.py` hade
silent-failat i 1 månad — UPDATEs skrevs till read-replica via `get_session()`
istället för Nbg primary via `get_write_session()`. Alla 2.5M scores var stale.

En audit genomfördes av alla `agentindex/crawlers/*.py` och andra moduler som
gör UPDATEs/INSERTs via SQLAlchemy sessions.

## Fixade i denna sprint

| Fil | LaunchAgent | Problem | Fix |
|-----|-------------|---------|-----|
| `crawlers/calculate_scores.py` | `com.nerq.daily-scores` | 0/2.5M scores uppdaterade sedan mars | Split read/write sessions |
| `crawlers/npm_enrichment.py` | (anropas av andra) | 4 UPDATEs via get_session() | Split read/write sessions |
| `crawlers/trust_score_v3.py` | `com.nerq.trust-score-v3` (NY) | Hade ingen scheduler, kört manuellt 1 gång | Schemalagd 09:00 UTC dagligen |

## Redan korrekta (uses get_write_dsn/get_write_session)

| Fil | Metod |
|-----|-------|
| `crawlers/npm_bulk_enricher.py` | `get_write_dsn()` via psycopg2 |
| `crawlers/npm_downloads_crawler.py` | `get_write_dsn()` via psycopg2 |
| `stale_score_detector.py` | `get_write_session()` |
| `crawlers/trust_score_v3.py` | `get_write_dsn()` via psycopg2 |

## Skriver till SQLite (ej påverkade)

| Fil | Destination |
|-----|-------------|
| `crawlers/openssf_scorecard.py` | `crypto_trust.db` |
| `crawlers/snyk_crossref.py` | `crypto_trust.db` |

## One-shot seeders — DO NOT RUN WITHOUT AUDIT

58 filer i `agentindex/crawlers/` och andra moduler använder `get_session()`
för writes men saknar aktiv scheduling. Om de körs manuellt idag → UPDATEs
går till read-replica → silent failure.

### Kategori A: Seeders — ska aldrig köras igen (setup-only)

- `crawlers/ai_tool_seeds.py` — initial AI tool seeding
- `crawlers/ai_tool_seeds_v2.py` — v2 seeding
- `crawlers/website_seeds.py` — website trust seed data
- `crawlers/website_seeds_extended.py` — extended website seeds
- `crawlers/website_tranco_seeder.py` — Tranco top-1M seeder
- `crawlers/city_seeds.py` — city/location seed data
- `crawlers/saas_seeds.py` — SaaS product seeds
- `crawlers/saas_seeds_v2.py` — SaaS v2 seeds
- `crawlers/chrome_seeds.py` — Chrome extension seeds
- `crawlers/charity_seeds.py` — charity/nonprofit seeds
- `crawlers/bulk_supplement_cosmetic_seeds.py` — supplement seeds
- `crawlers/food_cosmetics_seeds.py` — food/cosmetics seeds
- `crawlers/android_seeds_extended.py` — Android app seeds

### Kategori B: Manuella verktyg som kan behövas — BÖR FIXAS

- `crawlers/npm_enrichment.py` — **FIXAD 2026-04-20**
- `crawlers/cve_enrichment.py` — CVE data enrichment (1 UPDATE)
- `crawlers/ios_itunes_enrichment.py` — iTunes enrichment (4 UPDATEs)
- `crawlers/wordpress_king_enricher.py` — WordPress king data (3 UPDATEs)
- `crawlers/pypi_enrichment.py` — PyPI enrichment (4 UPDATEs)
- `crawlers/framework_detector.py` — framework detection (2 UPDATEs)
- `crawlers/compatibility_matrix.py` — compat matrix (2 UPDATEs)
- `crawlers/dependency_graph.py` — dependency graph (3 UPDATEs)
- `crawlers/rate_limit_mapper.py` — rate limit mapping (3 UPDATEs)
- `crawlers/mcp_compatibility_scanner.py` — MCP scanner (2 UPDATEs)
- `crawlers/pricing_crawler.py` — pricing data (3 UPDATEs)
- `intelligence/daily_snapshot.py` — daily snapshots (8 UPDATEs)
- `intelligence/trend_detector.py` — trend detection (5 UPDATEs)
- `intelligence/predictive/predictions.py` — predictions (2 UPDATEs)
- `intelligence/batch_scanner.py` — batch scanner (2 UPDATEs)
- `data_exports.py` — data exports (5 UPDATEs)
- `federation_api.py` — federation API (2 UPDATEs)
- `compliance/compliance_api.py` — compliance (4 UPDATEs)
- `analytics.py` — analytics writes (2 UPDATEs)

### Kategori C: Registry crawlers — körs sällan manuellt

- `crawlers/android_crawler.py` (1 INSERT)
- `crawlers/packagist_crawler.py` (2 INSERTs)
- `crawlers/chrome_crawler.py` (2 INSERTs)
- `crawlers/crates_bulk_loader.py` (2 INSERTs)
- `crawlers/firefox_crawler.py` (2 INSERTs)
- `crawlers/rubygems_crawler.py` (2 INSERTs)
- `crawlers/chocolatey_crawler.py` (1 INSERT)
- `crawlers/crates_crawler.py` (2 INSERTs)
- `crawlers/chrome_crawler_v2.py` (2 INSERTs)
- `crawlers/vscode_crawler.py` (2 INSERTs)
- `crawlers/packagist_bulk_crawler.py` (2 INSERTs)
- `crawlers/wordpress_crawler.py` (2 INSERTs)
- `crawlers/ios_crawler.py` (1 INSERT)
- `crawlers/npm_crawler.py` (2 INSERTs)
- `crawlers/npm_bulk_crawler.py` (1 INSERT)
- `crawlers/website_crawler.py` (2 INSERTs)
- `crawlers/android_play_crawler.py` (2 INSERTs)
- `crawlers/go_crawler.py` (1 INSERT)
- `crawlers/steam_crawler.py` (1 INSERT)
- `crawlers/nuget_catalog_crawler.py` (1 INSERT)
- `crawlers/nuget_crawler.py` (2 INSERTs)
- `crawlers/gems_bulk_crawler.py` (1 INSERT)
- `crawlers/chrome_sitemap_crawler.py` (1 INSERT)
- `crawlers/homebrew_crawler.py` (1 INSERT)
- `crawlers/vpn_loader.py` (2 INSERTs)
- `crawlers/pypi_crawler.py` (2 INSERTs)
- `crawlers/crypto_sync.py` (2 INSERTs)

### Övriga

- `intelligence/predictive/calibration.py` (1 UPDATE)
- `intelligence/verification_program.py` (1 UPDATE)
- `intelligence/polymarket_backtest.py` (1 UPDATE)
- `intelligence/polymarket_backtest_v2.py` (2 UPDATEs)
- `intelligence/polymarket_matcher.py` (2 UPDATEs)
- `intelligence/predictive_content.py` (2 UPDATEs)
- `compliance/batch_scanner.py` (1 UPDATE)
- `nerq_scout.py` — already imports get_write_session (mixed)
- `trust_scoring.py` — already imports get_write_session (mixed)
- `review_pages.py` — write paths already fixed
- `agent_safety_pages.py` — write paths already fixed
- `claim_page.py` — already imports get_write_session
- `ab_test.py` (1 UPDATE)
- `commerce_trust.py` (1 UPDATE)

## Regel

**Alla nya crawlers/scripts MÅSTE använda `get_write_session()` eller
`get_write_dsn()` för UPDATE/INSERT/DELETE operationer.**

`get_session()` returnerar en read-only replica-session och ska INTE
användas för skrivoperationer.

## Framtida arbete

- Kategori B: batch-fix vid nästa tillgängligt fönster (19 filer)
- Kategori C: fix vid behov (27 filer, körs sällan)
- Lägg till linting-regel som flaggar `get_session()` + UPDATE/INSERT i samma fil
