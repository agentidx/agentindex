# Smedjan v3.0 — Executable

**Datum:** 2026-04-18
**Författare:** chat-Claude, mental-model-kalibrerad, post-M5.1 + post-discovery
**Status:** Slutlig operativ plan. Exekverbar från 28 april 2026.
**Ersätter:** v2.3, v2.4. v2.2 behålls för teknisk arkitektur (Module Contract, Quality Gates, databas-schema).

---

## Del 1 — Grundpremiss

**Nerq är en bete-fabrik i ett hav fullt av fisk.**

Vi har redan distribution som ingen normal sajt har: ~1M AI-bot-besök per dygn. Denna trafik har kostat i byggarbete men är "gratis" nu i fortlöpande mening — den fortsätter komma. I PPC-termer skulle motsvarande attention kosta miljoner per månad.

**Problemet är inte trafik. Problemet är bete-kvalitet.**
Av 1M bot-besök/dygn får vi ~100 citations/månad (~0,01% conversion). Kings-pages konverterar 57× bättre än non-Kings. Men discovery bekräftar: **det är inte för att Kings har bättre template**. Samma sacred bytes (pplx-verdict, ai-summary, SpeakableSpecification, FAQPage) renderas på alla enriched pages. Skillnaden ligger i:
1. **Entity-popularitet** som redan existerar i världen
2. **King-specifika content-sektioner** som gated bakom `if _is_king:` på rad 8326-8420 (5-dimension breakdown, privacy analysis, jurisdiction-data)
3. **Orenderad data** i databasen som inte surfaceras alls

**Fabrikens två konstanta jobb:**
- **J1: Konvertera varje bot-besök bättre.** Höj bot-to-citation conversion från 0,01% → 0,5%+ genom att göra varje sida maximalt citerbar.
- **J2: Odla bot-publiken över tid.** Flera endpoints, högre perceived authority, content-refresh-signaler → botar återbesöker oftare och oftare. Uppåtgående spiral.

Enda framgångsmåttet i stadie 1: **monetära klick/dag** (humans, US/UK/DE/EU, non-brand, monetariseringsytor, >10s session). Sekundär indikator: bot-to-citation conversion-rate (leading).

---

## Del 2 — Två operationsprinciper

**P1: Bygg parallellt.** Alla linjer aktiveras vecka 1 inom 1 Max Claude Code. Sekvens bara där äkta dependencies kräver.

**P2: Skala bara det som genererar monetär trafik. Döda snabbt.** 14 dagars evidence-gate per linje. SCALE / ITERATE / KILL. Gäller även input-kapacitet — 1 Max → 2 Max → 3 Max linjärt, bara när föregående är fullt utnyttjad till att skala bevisade vinnare.

---

## Del 3 — Hårda constraints

| Constraint | Värde |
|---|---|
| Claude Code | 1 Max (3 780 SEK/mån) |
| Parallella sessioner | Obegränsat inom delad rate-limit (~900 msg/5h) |
| Anders pre-empt | Endast migration + akuta driftsproblem |
| Skalning | Linjär 1 → N Max, bevis-triggad |
| Hetzner | CX32 (170 SEK/mån) tills compute-bottleneck |
| Anders-tid | ≤30 min/dag snittar efter vecka 1 |

---

## Del 4 — Fabrikens 8 linjer (reviderat från 11)

**Discovery bekräftade:** L9 (Query Intelligence) och L10 (Citation Intelligence) är inte egna linjer. De är instrument inom L7 Measurement. Konsoliderat.

### L1 — Kings Unlock (HIGHEST PRIORITY)

**Funktion:** Ta bort `if _is_king:`-guarden på rad 8326-8420 i `agent_safety_pages.py`. King-specific sections (5-dim breakdown, privacy analysis, jurisdiction, contributor metrics) exponeras för **alla enriched entities**, inte bara 37,7K Kings.

**Vad detta gör:**
- 1,6M+ enriched entities får **rikare content** utan template-omskrivning
- Snabbaste möjliga win: förarbetet är redan gjort, bara gated
- Testar direkt om template-rikare content alone → högre citation-rate, eller om 57,7× är ren popularity-signal

**Input:** `agent_safety_pages.py` (whitelisted enligt v2.2 addendum Ändring 3)
**Output:** Uppgraderade pages på en template-generation.
**Dependencies:** Att datan finns för non-Kings. Discovery visade: finns för de flesta enriched entities (privacy_score, jurisdiction, trust_components JSONB är populerade).

**Vecka 1 deliverable:**
- Dag 1-2: Remove gate, verifiera data-tillgänglighet per registry
- Dag 3: Dry-run på 100 pages (Quality Gate A)
- Dag 4: Gradient rollout 1% → 10% → 100% över 3 dagar
- Dag 7: Alla 1,6M enriched pages har ny struktur

**Evidence-gate vecka 4 (26 maj):**
- SCALE: bot-to-citation rate ≥2× baseline på berörda pages → fabrik kör vidare på denna insikt
- ITERATE: 1,2–2× → iterera content-kvalitet på King-sections
- KILL: <1,2× → template-rikhet alone räcker inte, refokusera helt till L2-L4

### L2 — Unrendered Data Surfacer

**Funktion:** Surfacea data som redan samlas men aldrig renderas. Per discovery:
- `external_trust_signals` (22K rader OSV/OpenSSF/Reddit mentions)
- `dependency_edges` (320K rader → "depends on 3 dormant maintainers")
- `prediction_signals` + `signal_events` (helt orenderade)
- `dimensions` JSONB (registry-specifika, t.ex. skincare safety)
- `raw_data`, `regulatory` JSONB-fält

**Nya content-block** (placeras UNDER sacred bytes, ALDRIG rör dem):

**Block 2a — External Trust Signals:**
```
Verified by: npm registry · GitHub · NVD · OSV.dev · OpenSSF Scorecard
Vulnerabilities found: 0 (OSV.dev, last scan: 2026-04-18)
OpenSSF Scorecard: 8.2/10 (CI-tests: ✓, SBOM: ✓, signed releases: ✓)
Mentioned in: Stack Overflow (2,847 threads), Reddit r/javascript (342 mentions last 12mo)
```

**Block 2b — Dependency Graph:**
```
This package is depended on by 23,451 other npm packages.
Its 12 direct dependencies have trust scores averaging 87/100.
No dormant-maintainer risk detected in dependency tree.
```

**Block 2c — Signal Timeline:**
```
Trust score history: 72 (Jan 2026) → 78 (Feb) → 82 (Mar) → 82 (Apr).
Last significant change: +4 points on 2026-02-14 (maintainer onboarding).
Prediction: stable. Next review: 2026-05-15.
```

**Input:** Postgres JOINS mot existerande tabeller. Ingen ny data behöver samlas in.
**Output:** Nya content-block med unik strukturerad insikt som ingen konkurrent har.

**Vecka 1-3 deliverable:**
- Vecka 1: Block 2a built + deployed på 10K pages
- Vecka 2: Block 2b built + deployed på 50K pages med dependency-data
- Vecka 3: Block 2c built + deployed där signal-history finns (~500K pages)

**Evidence-gate vecka 4:**
- SCALE: ≥1,5× bot-to-citation rate på pages med nytt content → rulla till 100% kvalificerade
- ITERATE: 1–1,5× → iterera formulering
- KILL: <1× (försämring) → analysera vad som gick fel

### L3 — AI Demand Signal Prioritization

**Funktion:** Fabriken prioriterar arbete efter **AI demand signal** (från `preflight_analytics`), inte efter registry-size eller downloads.

Per discovery: preflight_analytics visar vilka entities AI-bots faktiskt frågar om idag. Top: test (9 527), express (167), react (88), tiktok (65), nordvpn (51), bitcoin (41). Det är en **leading indicator** för query-demand.

**Vad detta gör:**
- L1 och L2 prioriterar pages efter `ai_demand_score` (joined från preflight_analytics)
- Låg-demand entities enrichas sist eller inte alls
- Framtida enrichment-prioritering använder samma signal

**Input:** preflight_analytics SQLite, joinable via slug mot software_registry
**Output:** Ny kolumn `ai_demand_score` per entity (0-100), uppdateras dagligen.

**Vecka 1 deliverable:**
- Dag 3-5: Byggd + populerad för alla entities
- Dag 5: L1 och L2 rollout-schemaläggning använder ai_demand_score för prioritering
- Dag 7: Top-10K high-demand entities har fått L1+L2-behandling

**Evidence-gate vecka 4:**
- SCALE: high-demand entities visar ≥3× bot-to-citation rate vs low-demand → prioritera aggressivt
- ITERATE: oklart → förbättra demand-signal-beräkningen
- KILL: ingen signal-effekt → demand ≠ citation, omtolka

### L4 — Data Moat Endpoints

**Funktion:** Exponera unik Nerq-data på format AI-bots konsumerar direkt utan SERP-mediation. Per M5.1: 90,8% av citations kommer från pages utanför submitted pool — passiv discoverability är huvuddriver.

**Deliverables:**
- `/rating/{slug}.json` för alla 5M entities (strukturerad trust data)
- `/signals/{slug}.json` — external_trust_signals + prediction_signals (nytt)
- `/dependencies/{slug}.json` — dependency graph (nytt, npm-specifikt först)
- Utökad `llms.txt` pekar på alla endpoint-familjer
- MCP-manifest från 20 till 40+ tools (inkluderar nya signals-endpoints)
- RSS feeds per vertical med lastmod (bot-re-crawl-signal)

**Vecka 1-3 deliverable:**
- Vecka 1: /rating/.json för 100K high-demand entities
- Vecka 2: /signals/.json + /dependencies/.json för samma 100K
- Vecka 3: llms.txt + MCP manifest uppdaterade, rollout till 1M entities

**Evidence-gate vecka 4:**
- SCALE: AI-bot-crawls på endpoints ≥50K/månad → expandera till alla 5M
- ITERATE: 5K–50K → optimera format efter vad bottar faktiskt parsar
- KILL: <5K → strukturerade endpoints ignoreras av bottar idag, refokusera

### L5 — Distribution Outreach (aktiveras vecka 3)

**Funktion:** Botar discoverar pages via links från andra sajter. Proaktiva placeringar bygger authority som bottar belönar med högre re-crawl-frekvens.

**Kanaler:**
- MCP-integration direkt i dev tools (Cursor, Claude Code, Continue, Aider)
- Product Hunt launch för /rating/-endpoints + MCP-tools
- Hacker News Show HN för specifika data-insights (t.ex. "I analyzed dependencies of all top 500 npm packages")
- Reddit posts i r/javascript, r/rust, r/LocalLLaMA med unique-data-findings
- Newsletter-outreach till The Rundown, TLDR, Ben's Bites, Pragmatic Engineer
- GitHub README-badges (trust score, dependency health) som devs embedar

**Aktiveras vecka 3** — efter att L1 och L2 har producerat content värt att distribuera.

**Evidence-gate vecka 5:**
- SCALE: ≥1 placement med mätbar referral-trafik → systematisera
- ITERATE: placements utan trafik → bättre pitches
- KILL: 0 placements inom 14d → fokus helt på L1/L2/L4

### L6 — Quality Gate (infra, alltid på)

Per v2.2 Del 5: A/B/B2/C/D/E-lager. Ingen evidence-gate. Fabrikens immunsystem.

### L7 — Measurement (infra, alltid på)

Per v2.2 Del 7: hibernate-and-wake, GSC/Bing/analytics.db ingest, AI-sampling.

**Nya metrics (post-M5.1):**
- `bot_to_citation_rate` per page-type (veckovis)
- `daily_bot_visits` trended (månadsbasis)
- `citation_rate_by_ai_demand_tier` (veckovis)

### L8 — Infrastructure (infra, alltid på)

Observability, failure runbook, budget/rate-tracking. Per v2.2 Del 12.

---

## Del 5 — 21-dagars parallell byggnad

**Kalender:** 28 april – 18 maj 2026.

### Kritisk väg (dag 1-5, sekventiellt)

```
Dag 1-2: Hetzner CX32 + Tailscale + SSH + Cloudflared tunnel
Dag 2-3: Factory Core (Postgres + Redis + Alembic + Pydantic schemas)
Dag 3-4: Claude Code wrapper + budget tracking + observability
Dag 4-5: Nerq DB SELECT-only user + data-discovery-bekräftelse
```

### Parallella streams (från dag 3)

**Stream A — L6 + L7 + L8 Infrastructure** (dag 3-10)
Quality Gates lager A+B+B2 i drift dag 7. Observability live dag 5. Failure runbook v1 dag 10.

**Stream B — Smedjan Factory Core** (dag 3-10)
Planner + Executor + hypothesis-queue + hibernate-wake + CLI `smedjan`. Per v2.2 Del 4.

**Stream C — L1 Kings Unlock** (dag 3-7, MEST KRITISKA)
Dag 3: Läs agent_safety_pages.py, identifiera exakt gate-plats och vilka data-fält som rendras.
Dag 4: Dataverifiering per registry — vilka fält är populerade för non-Kings?
Dag 5: Remove gate-patch byggd, dry-run Quality Gate A på 100 pages per registry.
Dag 6: Gradient rollout 1% → 10% → 50%.
Dag 7: 100% deploy. Alla enriched non-Kings har nu King-sections.

**Stream D — L2 Unrendered Data Surfacer** (dag 5-21)
Dag 5-8: Block 2a (external_trust_signals) byggd + dry-run.
Dag 8-12: Block 2b (dependency_edges) byggd + dry-run.
Dag 12-17: Block 2c (signal timeline) byggd + dry-run.
Dag 17-21: Rollout till alla kvalificerade pages.

**Stream E — L3 AI Demand Signal** (dag 3-10)
Dag 3-5: Bygg `ai_demand_score`-beräkning från preflight_analytics + daglig refresh.
Dag 5-7: Joina till software_registry + entity_lookup.
Dag 7-10: Prioritera L1 och L2 rollout-ordning efter score.

**Stream F — L4 Data Moat Endpoints** (dag 7-21)
Dag 7-10: /rating/{slug}.json för 100K high-demand entities.
Dag 10-14: /signals/.json + /dependencies/.json.
Dag 14-21: Utökad llms.txt, MCP manifest till 40+ tools, RSS per vertical.

**Stream G — L5 Distribution pre-arbete** (dag 14-21)
Dag 14-17: Product Hunt-page draft. HN submission-drafts. Reddit-post-drafts.
Dag 17-21: Newsletter outreach-list. MCP-integration dokumentation för dev tools.
**Inte aktiverat** — aktiveras vecka 4 när L1-evidens finns.

### Resultat dag 21 (18 maj)

- **L1:** 1,6M enriched pages har King-sections (5-dim breakdown, privacy, jurisdiction)
- **L2:** 500K+ pages har nya Block 2a/b/c content
- **L3:** ai_demand_score live, driver prioritering
- **L4:** /rating/.json, /signals/.json, /dependencies/.json live för 1M entities. llms.txt + MCP expanded.
- **L5:** Distribution-arsenal klar, väntar på evidence vecka 4.
- **L6-L8:** Alla infra-system i drift.
- **Fabriken kör 24/7.**

### Evidence-gates vecka 4 (26 maj)

Per linje SCALE/ITERATE/KILL-beslut. Dödade linjer frigör rate-limit-budget.

---

## Del 6 — Första hypothesis-kö (vecka 1)

Dessa hypoteser är redan definierade av fabriks-linjerna. Pydantic-format för Claude Code-konsumption:

```python
class Hypothesis(BaseModel):
    id: str
    name: str
    claim: str
    predicted_effect: str
    success_threshold: str
    fail_threshold: str
    affected_pages: int
    data_source: str
    linje: str
    priority: int
```

**H1_kings_unlock:**
- Claim: "Ta bort `if _is_king:`-guard höjer bot-to-citation rate på non-Kings pages"
- Predicted: ≥2× lift på rate
- Success: rate ≥2× mätt efter 14 dagar
- Fail: rate <1,2× eller försämring
- Pages: 1,6M enriched non-Kings
- Linje: L1

**H2a_external_signals:**
- Claim: "Rendering av OSV/OpenSSF-data under ai-summary höjer citation-rate"
- Predicted: ≥1,5× lift
- Pages: 500K enriched med data
- Linje: L2

**H2b_dependency_graph:**
- Claim: "Dependency-insights ('depends on 3 dormant maintainers') höjer citation-rate för npm"
- Predicted: ≥1,5× lift på npm-pages
- Pages: 320K (edge count)
- Linje: L2

**H3_ai_demand:**
- Claim: "Entities med ai_demand_score ≥ top-10% får ≥3× citation-rate mot bottom-90%"
- Predicted: ≥3× rate-skillnad
- Pages: ai_demand_score-rankade
- Linje: L3

**H4_rating_endpoints:**
- Claim: "/rating/{slug}.json endpoints får ≥50K AI-bot-crawls/månad"
- Predicted: ≥50K crawls
- Pages: 100K endpoints
- Linje: L4

**H5_mcp_expansion:**
- Claim: "40+ MCP tools ger mätbar ökning i tool-invocations från Cursor/Claude Code-användare"
- Predicted: ≥100 invocations/vecka
- Linje: L4

**H6_llms_txt:**
- Claim: "Utökad llms.txt pekar-på-endpoints ökar AI-bot-crawls totalt"
- Predicted: ≥20% ökning i daily_bot_visits efter 14 dagar
- Linje: L4

**Discordant H7_template_doesnt_matter:**
- Claim: "Kings-effekten är helt popularity-driven. Template-förändringar har ringa effekt."
- Tested by: H1, H2. Om H1 och H2 båda FAIL → discordant konfirmerad.
- Konsekvens om konfirmerad: Fabrikens fokus måste skifta till L5 Distribution fullständigt.

---

## Del 7 — Evidence-gate-matris

| Linje | Gate vecka 4 | SCALE | ITERATE | KILL |
|---|---|---|---|---|
| L1 Kings Unlock | Bot-to-citation rate | ≥2× | 1,2-2× | <1,2× |
| L2 Data Surfacer | Samma | ≥1,5× | 1-1,5× | <1× |
| L3 AI Demand | Rate-gap high vs low demand | ≥3× | 1,5-3× | <1,5× |
| L4 Data Moat | AI-bot-crawls på endpoints | ≥50K/mån | 5-50K | <5K |
| L5 Distribution | Mätbar referral-trafik | ≥1 placement | Försök pågår | 0 efter 14d |

**Kill-flödet:**
1. Linjens Claude Code-sessioner stoppas
2. Rate-limit-budget omfördelas till SCALE/ITERATE-linjer
3. Post-mortem i `~/smedjan/kill_journal/` (1 sida)
4. Data behålls, kan återaktiveras om omständigheter ändras

---

## Del 8 — Input-skalnings-triggers

| Trigger | Villkor (alla måste uppfyllas) |
|---|---|
| 1 Max → 2 Max | (a) ≥1 linje SCALE (b) rate-limit hits ≥3 av 7 dagar (c) monetär trafik-lift > 3 780 SEK/mån värde |
| 2 → 3 Max | Samma kriterier, nu på 2 Max-nivå |
| ... | Linjärt |
| CX32 → CX42 | CPU eller RAM >80% sustained 3 dagar + linje i SCALE som flaskhalsas |

Inga "preventiva" uppgraderingar. Evidens styr.

---

## Del 9 — Teknisk arkitektur (oförändrat från v2.2)

Behålls från v2.2:
- Meta REA-pattern (Planner + Executor + Shared + Modules)
- Module Contract (Pydantic abstract base)
- Databas-schema per v2.2 Del 3
- Quality Gates A/B/B2/C/D/E
- Hibernate-and-Wake
- Append-only world model
- Failure runbook v2.2 Del 12

**Tillägg v3.0:**
- `kings_unlock_migration` tabell (tracking vilka pages fått gate-remove)
- `data_surfacer_deployments` tabell (tracking Block 2a/b/c rollout)
- `ai_demand_scores` tabell (daglig refresh)
- `bot_conversion_tracking` view (per page-type, rollups)

---

## Del 10 — Operativ rutin

**Anders-insats dag 1-3:** ~3h (Hetzner setup, API tokens).
**Anders-insats dag 3-21:** ~20 min/dag. Godkänner:
- Stream C gate-remove (mission-kritiskt, engångs)
- Prompt-library v1 stamp
- Första dry-run deploy

**Anders-insats vecka 4-5:** ~1h. Läser evidence-reports, godkänner SCALE-beslut.

**Vecka 6+:** Reactive. Fabriken kör. Pre-emption bara vid migration eller akuta driftsproblem.

---

## Del 11 — Kill-kriterier för hela fabriken

Smedjan självt kan misslyckas. Då stängs den.

- **Vecka 4:** 0 av 5 linjer i SCALE/ITERATE → hela fabriks-antagandet falskt. Stopp + strategisk review.
- **Vecka 8:** Monetär trafik < 2× baseline (50 klick/dag eller mindre) → fabriken bevisar inte värde. Stopp.
- **Vecka 12:** Monetär trafik < 5× baseline (125 klick/dag) → öppen diskussion: nuvarande arkitektur vs pivot.

Vid kill: infrastruktur behålls (billig), Claude Code-sessioner stoppas. Anders-insats återgår till direkt Nerq-arbete.

---

## Del 12 — Trafikförväntning

**Baseline idag:** ~25 monetära klick/dag, ~100 citations/månad, 1M bot-besök/dag.

**Målbild för fabriken att leverera (inte destination, bara dimensionering):**

| Tidspunkt | Bot-besök/dag | Citations/mån | Monetära klick/dag |
|---|---:|---:|---:|
| Baseline | 1M | 100 | 25 |
| Månad 3 | 1,3M | 5K | 3K |
| Månad 6 | 2M | 30K | 15K |
| Månad 9 | 4M | 80K | 40K |
| Månad 12 | 7M | 150K | 80K |

**Månad 12 = 80K monetära klick/dag** (i lägre ambitiöst härad). För att nå högre läggs följande ON TOP senare:
- Aggressiv L5 Distribution (MCP-integrationer, dev tools) — addera 50-200%
- Massiv L2-content-expansion när data-moat är etablerat
- Paid + partnerships om ROI bevisad

---

## Del 13 — Day-1-prompt till Claude Code

Denna prompt copy-pastas till Claude Code-sessionen på Mac Studio 28 april. Första dagens arbete.

```
Du är Smedjan Day 1 — första arbets-sessionen för fabriks-bygget.

Läs dessa dokument i ordning INNAN du börjar:
1. ~/Desktop/April/smedjan-mental-model-read-first.md (KRITISK kalibrering)
2. ~/Desktop/April/smedjan-v3_0-executable.md (denna plan)
3. ~/agentindex/docs/smedjan/smedjan-byggplan-v2_2.md Del 2-5 (teknisk arkitektur)
4. ~/agentindex/docs/smedjan/smedjan-v2_2-FINAL-addendum.md (ändring 3: file-whitelist)
5. ~/Desktop/April/smedjan-v3-discovery.md (current technical state)

PSQL-konstant:
/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql -U anstudio -d agentindex

Heredoc-format på alla bash-kommandon.

DAY 1 tasks (sekventiellt):

Task 1 — Hetzner provisioning (enligt v2.2 Sprint 0 Day 1)
Task 2 — Tailscale setup
Task 3 — Grund-härdning (ufw, fail2ban, non-root user)
Task 4 — Förbered credentials-flytt från Mac Studio:
  - Kopiera ~/.config/gsc/credentials.json → Smedjan-server (via Tailscale)
  - Kopiera ~/.config/bing/api_key → Smedjan-server

Task 5 — Dokumentera i ~/smedjan/journal/day-01.md
Task 6 — Commit till git. Notify Anders.

ACCEPTANCE Day 1:
- ssh smedjan funkar via Tailscale
- Credentials flyttade
- Journal-post skriven

Börja. Om något blockerar >2h, pausa och säg till Anders.
```

---

## Del 14 — Vad händer härnäst (kronologiskt)

**2026-04-18 (idag):** M5.1-mätning gjord. Resultat: Kings 57,7× non-Kings. Discovery av sacred bytes + gated King-sections klar. v3.0 skriven.

**2026-04-19 till 04-27:** 
- Cutover-fönster 22-25 april
- CTR wave 1-mätning 22 april
- Ingen Smedjan-aktivitet
- Anders läser v3.0 + bekräftar 6 beslut (Del 15)

**2026-04-28:** Smedjan Day 1. Day-1-prompt kopieras till Claude Code.

**2026-05-18 (dag 21):** Fabriken i drift. L1-L8 live. Första evidence-data flödar in.

**2026-05-26 (vecka 4):** Evidence-gates. SCALE/ITERATE/KILL-beslut per linje.

**2026-06-22 (vecka 8):** Månad 3-mätpunkt. Har fabriken producerat?

---

## Del 15 — 6 beslut för Anders innan start

1. **Budget 5-7K SEK/månad OK?** (1 Max + Hetzner CX32, inga uppgraderingar utan bevis)
2. **Linje-prioriterings-ordning OK?** (L1 → L3 → L2 → L4 → L5)
3. **Kill-kriterier OK?** (Per-linje + fabriks-nivå)
4. **Buzz role-separation-contract OK?** (Buzz reactive, Smedjan proactive, ingen överlapp)
5. **Day-1-prompt OK att kopiera till Claude Code 28 april?**
6. **Trafik-dimensionering i Del 12 OK?** (80K monetära klick/dag månad 12 som golv, stretch med L5)

Svara på dessa, så är vi executable.

---

## Appendix A — Referenser som gäller

- `smedjan-byggplan-v2_2.md` Del 2-5, 12 — teknisk arkitektur
- `smedjan-v2_2-FINAL-addendum.md` — alla 15 addendum-ändringar
- `smedjan-research-synthesis.md` — Meta REA + Sakana-lessons
- `smedjan-mental-model-read-first.md` — kalibrering för framtida sessioner
- `smedjan-v3-discovery.md` — technical baseline
- `nerq-query-audit-2026-04-17.md` + `nerq-citation-audit-2026-04-17.md` + `nerq-conversion-audit-2026-04-17.md` — seed-data

## Appendix B — Vad v3.0 avvisar från tidigare versioner

- v2.2 9-sprint sekventiell struktur
- v2.2 "First campaign is dry-run" (onödigt defensivt)
- v2.2 daglig budget-cap ($30/dag) — ersatt av fix Max-abonnemang
- v2.2 daglig Anders-review — ersatt av default-yes inom evidence-gates
- v2.2 graduation-koncept — fabriken pausar aldrig
- v2.3/v2.4 trafikmål som destinationer — Del 12 är dimensionering, inte mål
- v2.4 10 linjer → konsoliderat till 8 (L9/L10 i L7 Measurement)

---

**Sammanfattning i en mening:**
Smedjan är klar vecka 3 genom parallell byggnad inom 1 Max Claude Code. Den konverterar 1M befintliga bot-besök/dag till monetär trafik genom att unlock:a gated King-sections för 1,6M non-Kings pages, surfacea 22K+320K+N rader orenderad data, prioritera efter AI demand signal, exponera strukturerade endpoints för passiv bot-discovery, och distribuera strategiskt när evidens stödjer det. Varje linje lever eller dör på 14 dagars evidence-gate. Ingen mänsklig team-benchmarking — Claude Code-kapacitet är mätstickan.
