# Session Handoff — 2026-04-13 Evening

## Kontext

2026-04-13: Fullständig trafikrevision från rådata (17.3M rader, 30 dagar). Avslöjade att dashboards överrapporterat human-traffic 3-30x (Singapore bot-farm + distribuerade crawlers med Chrome-UAs passerade bot-detection). Identifierade ChatGPT-User som verklig citation-metric (~1,700/dag, växt från 61/dag den 14 mars). 21 mars-spike förklarad: 9 nya URL-mönster (alternatives, who-owns, was-hacked, etc.) → OAI-SearchBot indexerade → ChatGPT-User hoppade 647→1,198/dag samma dag.

Klassificerade 8 saknade user-triggered AI-bots i analytics.py (Perplexity-User, DuckAssistBot, YouBot, Manus, Mistral, Doubao, Google-Read-Aloud, AnthropicSearchEval). Lade till bot_purpose-taxonomi (training/user_triggered/search_index/internal) med 30-dagars backfill.

Multi-bot landscape-analys visade 95.8% koncentration på ChatGPT för user-triggered queries. Apple indexerar alla 23 språk jämnt (86.8% lokaliserat). YouBot växer 225%/vecka.

## Deployade piloter (aktiva mätfönster)

### Pilot 1: Query-form-expansion (/was-X-hacked)

- **URL:** /was-X-hacked, 100 entities × 23 språk = 2,300 URLs
- **Deploy:** 2026-04-13, IndexNow submission HTTP 200
- **Baseline:** 0 ChatGPT-User-träffar pre-deploy, 9 OAI-SearchBot
- **Mätstart:** när OAI-SearchBot börjar indexera nya URLs
- **Beslutsregel** (7d efter OAI-SearchBot pickup):
  - \>50 ChatGPT-User → skala 5-7 URL-former
  - 20-50 → undersök
  - <20 → mekaniken inte reproducerbar
- **Kod:** `pattern_routes.py` `_hacked_page()` (enhanced med CVE-data, Article+FAQPage schema, pplx-verdict)
- **Dokumentation:** `docs/status/query-form-pilot.md`

### Pilot 2: Freshness-pipeline

- **Omfattning:** top 10K entities, daglig score-delta-detektion
- **Deploy:** 2026-04-13, baseline-snapshot sparat (9,993 entities)
- **Schema:** LaunchAgent `com.nerq.freshness-daily`, 08:30 CEST
- **Trigger:** score-delta ≥0.1 ELLER CVE-count ändrat
- **IndexNow:** selective push (endast ändrade entities, inte 10K blint)
- **Beslutsregel** (4 veckor):
  - Perplexity-User lift >1.5x på regenererade vs stale → skala 50K
  - Annars undersök
- **Kod:** `scripts/freshness_pipeline.py`, `scripts/freshness_measure.py`
- **Snapshot:** `data/freshness-snapshots/scores-latest.json`
- **Log:** `logs/freshness-regenerated.jsonl` (vilka entities regenererades vilken dag)

### M5.1 Kings-experiment (pågår sedan 2026-04-11)

- **Status:** AKTIV — samlar data
- **Slutdatum:** 2026-04-18 (7d) eller 2026-04-25 (14d om svag signal)
- **Påverkan av trafikfall:** Cloudflare-incident reducerade absoluta volymer men påverkar Kings och non-Kings lika → jämförelsen fortfarande giltig
- **Pre-registrerade trösklar:** <1.5x → Kings=bias, 1.5-3x → partiellt stödd, >3x → stödd
- **Dokumentation:** `docs/status/leverage-sprint-day-3-m5-experiment.md`
- **⚠️ RÖR INTE** `auto_indexnow.py` — experimentet pågår

## Daglig koll

```bash
# Pilot 1: /was-X-hacked — bot activity per dag
sqlite3 ~/agentindex/logs/analytics.db "
  SELECT date(ts), bot_name, COUNT(*)
  FROM requests
  WHERE path LIKE '/was-%-hacked' AND ts >= '2026-04-13'
  GROUP BY date(ts), bot_name ORDER BY date(ts)"

# Pilot 2: Freshness pipeline — kördes den?
tail -5 ~/agentindex/logs/freshness-daily.log

# M5.1: Kings experiment — AI citation volume
sqlite3 ~/agentindex/logs/analytics.db "
  SELECT date(ts), COUNT(*) FROM requests
  WHERE is_ai_bot=1 AND status=200 AND ts >= '2026-04-11'
  GROUP BY date(ts) ORDER BY 1"

# ClaudeBot recovery
sqlite3 ~/agentindex/logs/analytics.db "
  SELECT date(ts), COUNT(*) FROM requests
  WHERE bot_name='Claude' AND ts >= date('now', '-7 days')
  GROUP BY date(ts) ORDER BY 1"
```

## Filer skapade idag

| Fil | Typ |
|---|---|
| `docs/status/total-traffic-analysis-2026-04-13.md` | Fullständig trafikrevision |
| `docs/status/user-triggered-bot-inventory-2026-04-13.md` | 8 nya bots identifierade |
| `docs/status/ai-bots-classification-fix-2026-04-13.md` | bot_purpose-taxonomi |
| `docs/status/chatgpt-user-pattern-and-growth-2026-04-13.md` | ChatGPT-User mönsteranalys |
| `docs/status/oai-searchbot-spike-analysis-2026-03-21.md` | 21 mars spike root-cause |
| `docs/status/multi-bot-landscape-analysis-2026-04-13.md` | Cross-plattform-analys |
| `docs/status/claudebot-specific-diff-2026-04-13.md` | ClaudeBot drop = extern orsak |
| `docs/status/claudebot-ua-audit-2026-04-13.md` | UA-variant audit |
| `docs/status/brave-search-audit-2026-04-13.md` | Brave: minimal indexering |
| `docs/status/traffic-drop-analysis-2026-04-13.md` | Cloudflare-incident analys |
| `docs/status/query-form-pilot.md` | /was-X-hacked pilot tracking |
| `docs/status/phase-0-day-5-dr-backup.md` | pgBackRest + PITR verifierat |
| `scripts/freshness_pipeline.py` | Stage 1+4 daglig pipeline |
| `scripts/freshness_measure.py` | Veckovis lift-mätning |
| `agentindex/analytics.py` | 8 nya UAs + bot_purpose-taxonomi |
| `agentindex/pattern_routes.py` | Enhanced /was-X-hacked med CVE-data |

## Centrala insikter (bekräftat via data 2026-04-13)

- **Training crawl (ClaudeBot, GPTBot) ≠ user-triggered citation (ChatGPT-User)** — oberoende pipelines, noll korrelation per URL
- **/best/-rankings: 0.006% av ChatGPT-User-trafik** — deprioriterad
- **ChatGPT-User dominerar: 95.8% av user-triggered.** Koncentrationsrisk.
- **Applebot 293K/dag, 86.8% lokaliserat** — asymmetrisk position inför Apple Intelligence launch (våren 2026)
- **Perplexity-gap: 178K indexering / 7 user-triggered = 25,000:1 ratio** — största optimeringspotentialen
- **Claude-User: 2/dag**, ClaudeBot-värde okänt (gap att stänga senare)

## Inte gjort, deprioriterat

- Multi-URL-form-expansion (väntar på pilot-resultat)
- Perplexity-specifik AEO (pplx-verdict-block, author schema) — prio efter pilotresultat
- Off-domain seeding (Reddit, YouTube, Wikipedia) — senare fas
- ClaudeBot-värde-verifiering (korrelation training → citation) — gap

## Öppna gap

1. **ClaudeBot-värde:** driver 140K/dag något mätbart eller ren training? Vid ~25% baseline pga extern orsak. Maila claudebot@anthropic.com om inte recoverat 16 april.
2. **Manuell citation-verifiering:** syns Nerq i faktiska AI-svar? Ej testat.
3. **Är Nerq:s trust scores konkurrenskraftiga** vs befintliga sajter per entity? (data-djup-jämförelse ej gjord)
4. **Human-traffic-överskattning** — behöver cookie/JS-based bot-detection. Monetization-triggern (150K/dag) är inte nära — realistiskt ~1,400-5,700 faktiska humans/dag.
5. **Phase 0 infra** — pgBackRest PITR verifierat, Hetzner-noder redo för DNS/tunnel-cutover (Day 5+).

## Vision (bekräftad 2026-04-13)

Trust scores som universal mätbarhet. Domain-specifika metoder, kvantifierbar fakta som input. Digital = start, alla domäner = mål. AI som primär distributionskanal. Maskin-först-arkitektur.
