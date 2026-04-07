# Nerq + ZARQ — SEO Traffic Capture Sprint Plan v1

**Datum:** 2026-03-11  
**Kodnamn:** Operation Programmatic SEO  
**Mål:** Generera 800+ indexerbara sidor som fångar existerande söktrafik + automatisera white-hat backlink-generering  
**Tidsram:** 10 arbetsdagar  
**Förutsättning:** Sprint Plan v4 pausad. Inga nya endpoints — vi wrapprar befintlig data.

---

## STRATEGISK GRUND

### Varför detta fungerar
Zapier genererar 16M organiska besök/månad från 25,000+ programmatiska landningssidor. Canva har 190,000+ indexerade sidor. Wise har 8.5M sidor. Mönstret: en template + en databas = massiv long-tail-trafik.

ZARQ har 205 tokens med djup data. Nerq har 204K agenter med trust scores. Datan finns — det saknas bara sidorna.

### Realistisk trafikprognos (12 månader)
- **Månad 1-3:** Indexering, minimal trafik. ~100 besök/dag.
- **Månad 3-6:** Long-tail börjar ranka. ~500-2,000 besök/dag.
- **Månad 6-12:** Med backlinks, 2,000-5,000 besök/dag.
- **Totalt år 1:** 20K-90K organiska besök/månad (från dagens ~200/månad).

### Programmatic SEO — Kritiska regler
1. **Varje sida MÅSTE ha unik, värdefull data** — inte bara token-namn i en template.
2. **Hub-and-spoke arkitektur** — kategorisidor (hub) länka till individuella sidor (spokes).
3. **JSON-LD structured data på varje sida** — för Google rich results + AI-citering.
4. **Intern länkning** — varje sida länka till 10-20 relaterade sidor.
5. **Stegvis utrullning** — inte 800 sidor dag 1. Batch om 50-100, verifiera indexering.
6. **Unik content per sida** — dynamisk data (scores, signaler, historik) + genererad analys-text.

---

## DAG 1-2: ZARQ Token Safety Pages (205 sidor)

### Z1.0 — Template: zarq.ai/token/[slug]
**Sökord som fångas:** "is [token] safe", "is [token] legit", "[token] risk", "[token] scam"

**Template-komponenter:**
- H1: "[Token Name] Risk Assessment — Trust Score [Aaa-D]"
- Hero: Trust Score badge (stor, visuell), crash probability gauge, rating
- Sektion 1: "Is [Token] Safe?" — 2-3 meningar dynamiskt genererade baserat på signalerna
- Sektion 2: "Risk Signals" — 7 Distance-to-Default signaler med förklaring
- Sektion 3: "Crash Probability" — historisk graf + nuvarande värde
- Sektion 4: "Structural Analysis" — om token har Structural Collapse/Stress warning
- Sektion 5: "Compare" — länkar till 3-5 liknande tokens (intern länkning)
- FAQ schema (JSON-LD): "Is [token] a good investment?", "What is [token]'s risk rating?", "Will [token] crash?"
- Sidebar: Relaterade tokens, "Most at risk right now" lista

**Datakälla:** `/v1/check/{token}` endpoint — redan byggt, redan live.

**Uppgifter:**
- [ ] Z1.0a: Skapa Jinja2-template (~/agentindex/agentindex/crypto/templates/token_page.html)
- [ ] Z1.0b: Route i discovery.py: `GET /token/{slug}` → rendera template med data från crypto_trust.db
- [ ] Z1.0c: JSON-LD structured data (FAQPage schema + Product schema med aggregateRating)
- [ ] Z1.0d: Generera slug-lista från alla 205 tokens
- [ ] Z1.0e: Testa 5 tokens manuellt, verifiera rendering

### Z1.1 — Hub-sida: zarq.ai/tokens
**Sökord:** "crypto risk ratings", "token safety ratings", "crypto trust scores"

- Tabell med alla 205 tokens sorterbara på Trust Score, crash probability, rating
- Filterbar: "Show only Structural Stress", "Show only Aaa-rated"
- Länka till varje individuell token-sida

**Uppgifter:**
- [ ] Z1.1a: Template tokens_index.html
- [ ] Z1.1b: Route `/tokens` med sortering/filtrering
- [ ] Z1.1c: JSON-LD ItemList schema

---

## DAG 2-3: ZARQ Crash Watch + Yield Risk (2 sidor + data-driven)

### Z2.0 — zarq.ai/crash-watch
**Sökord:** "crypto crash prediction", "which crypto will crash", "crypto crash warning"

- Live-dashboard med tokens som närmar sig Structural Collapse
- Sorterat: mest sannolikt att krascha först
- Historisk träffsäkerhet: länk till track-record repo
- "Crash Watch" uppdateras dagligen via befintlig cron

**Uppgifter:**
- [ ] Z2.0a: Template crash_watch.html
- [ ] Z2.0b: Route `/crash-watch` med data från strukturell filtrering
- [ ] Z2.0c: JSON-LD (WebPage + DataFeed schema)

### Z2.1 — zarq.ai/yield-risk
**Sökord:** "defi yield risk", "safe defi yields", "high APY scam"

- Yield-möjligheter color-coded av risk (grön/gul/röd)
- Data från Yield Risk Engine (455K+ DeFiLlama datapoints)
- Divergence-varningar synliga

**Uppgifter:**
- [ ] Z2.1a: Template yield_risk.html
- [ ] Z2.1b: Route `/yield-risk`

---

## DAG 3-4: ZARQ Content Hub + Comparison Pages

### Z3.0 — zarq.ai/learn (5 guider)
**Sökord:** "how to check if crypto is safe", "DYOR checklist", "crypto due diligence"

Guider (Jinja2-templates, inte statisk HTML):
1. "How to Check If a Cryptocurrency Is Safe (2026 Guide)"
2. "DeFi Risk Checklist: 7 Signals That Matter"
3. "Understanding Crash Probability: A Beginner's Guide"
4. "What Is Distance-to-Default? Crypto Risk Explained"
5. "Crypto Trust Scores: How ZARQ Rates 205 Tokens"

Varje guide länka inline till relevanta token-sidor + live API-data.

**Uppgifter:**
- [ ] Z3.0a: Template learn_article.html
- [ ] Z3.0b: Route `/learn/{slug}`
- [ ] Z3.0c: Hub-sida `/learn`
- [ ] Z3.0d: Skriv 5 guider (markdown → renderade i template)
- [ ] Z3.0e: HowTo + Article JSON-LD schema

### Z3.1 — Comparison Pages (20 sidor)
**Sökord:** "ZARQ vs Token Sniffer", "ZARQ vs SupraFin", "[token A] vs [token B] risk"

Två typer:
- **Tool comparison:** ZARQ vs Token Sniffer, ZARQ vs RugCheck, ZARQ vs GoPlus, ZARQ vs SupraFin (4 sidor)
- **Token comparison:** Top 16 token-par baserat på kategori ("solana vs ethereum risk", "bnb vs avalanche safety") (16 sidor)

**Uppgifter:**
- [ ] Z3.1a: Template comparison.html (re-use befintlig comparison template från Sprint 5)
- [ ] Z3.1b: Generera 20 comparison-routes
- [ ] Z3.1c: JSON-LD ComparisonPage schema

---

## DAG 4-5: NERQ Agent Safety Pages (500 sidor)

### N1.0 — Template: nerq.ai/safe/[agent-slug]
**Sökord:** "is [agent] safe", "can I trust [agent]", "[agent] review", "[agent] security"

**BLUE OCEAN — nästan noll konkurrens.**

**Template-komponenter:**
- H1: "Is [Agent Name] Safe? — Trust Score [X/100]"
- Hero: Trust Score badge, Verified/Unverified status, kategori
- Sektion 1: "Safety Assessment" — dynamisk text baserat på trust score
- Sektion 2: "Trust Signals" — vad som bidrar till scoren
- Sektion 3: "Registry Sources" — var agenten hittades (GitHub, npm, PyPI, etc.)
- Sektion 4: "Alternatives" — liknande agenter med högre trust (intern länkning)
- FAQ schema: "Is [agent] safe to use?", "What is [agent]'s trust rating?"
- Badge embed-kod (för agent-ägare att lägga på sin repo)

**Datakälla:** `/v1/agent/kya/{name}` + `/v1/agent/reputation/{name}` — redan byggt.

**Prioritering:** Topp 500 agenter baserat på:
1. Agents med flest externa sökningar (GitHub stars som proxy)
2. Alla Nerq Verified (18K+, men börja med topp 500)
3. Populära namn: cursor, claude-code, devin, langraph, crewai, autogen, etc.

**Uppgifter:**
- [ ] N1.0a: Skapa template safe_agent.html
- [ ] N1.0b: Route `/safe/{slug}` i discovery.py
- [ ] N1.0c: JSON-LD FAQPage + SoftwareApplication schema
- [ ] N1.0d: Generera slug-lista: top 500 agenter sorterade efter trust + popularitet
- [ ] N1.0e: Testa 10 agenter manuellt

### N1.1 — Hub-sida: nerq.ai/safe
**Sökord:** "AI agent safety check", "trusted AI agents", "safe AI tools"

- Sökbar lista med agenter + trust scores
- Filter: kategori, verified only, minimum trust score
- "Most trusted" ranking

**Uppgifter:**
- [ ] N1.1a: Template safe_index.html
- [ ] N1.1b: Route `/safe`

---

## DAG 5-6: NERQ Comparison Pages (100 sidor)

### N2.0 — nerq.ai/compare/[agent-a]-vs-[agent-b]
**Sökord:** "cursor vs claude code", "langraph vs crewai", "devin vs github copilot"

**Template-komponenter:**
- H1: "[Agent A] vs [Agent B]: Trust Score Comparison"
- Side-by-side: Trust score, kategori, registries, verified status, styrkor/svagheter
- Rekommendation baserat på data
- "See also" — relaterade jämförelser (intern länkning)

**100 jämförelsepar att generera:**
- AI Coding Agents (20 par): cursor/claude-code, cursor/devin, devin/copilot, etc.
- AI Agent Frameworks (20 par): langraph/crewai, autogen/langraph, etc.
- MCP Servers (20 par): populäraste par
- General AI Tools (20 par): baserat på kategori-matchning
- Cross-category (20 par): intressanta jämförelser

**Uppgifter:**
- [ ] N2.0a: Template compare_agents.html
- [ ] N2.0b: Script: generera 100 bästa jämförelsepar från agent-data
- [ ] N2.0c: Route `/compare/{slug-a}-vs-{slug-b}`
- [ ] N2.0d: JSON-LD ComparisonPage schema
- [ ] N2.0e: Hub-sida `/compare` med alla jämförelser kategoriserade

---

## DAG 6-7: NERQ MCP Server Trust Pages (500 sidor)

### N3.0 — nerq.ai/mcp/[server-slug]
**Sökord:** "best MCP server for [use case]", "[MCP server name] review"

**Angle: inte "ännu en directory" utan "MCP servers RATED by trust."**

- H1: "[Server Name] MCP Server — Trust Score [X/100]"
- Trust badge, tools lista, installation-instruktioner
- "Safer alternatives" för low-trust servers
- Intern länkning till relaterade MCP servers

**Uppgifter:**
- [ ] N3.0a: Template mcp_server.html
- [ ] N3.0b: Route `/mcp/{slug}`
- [ ] N3.0c: Hub-sida `/mcp` (alla MCP servers, sorterbara)
- [ ] N3.0d: JSON-LD SoftwareApplication schema

---

## DAG 7-8: BACKLINK AUTOMATION (White Hat)

### B1.0 — Automatiserad Backlink-strategi

**Princip:** Vi bygger system som genererar backlinks organiskt och automatiserat, utan att bryta Googles riktlinjer. Nyckeln: vi producerar unik data som andra VILL citera.

### B1.1 — Citerbar Data (Linkable Assets)
**Mest effektiva white-hat strategin 2026: original data som andra citerar.**

ZARQ och Nerq producerar redan unik data som ingen annan har:
- "205 tokens rated with 100% structural collapse recall"
- "204K agents indexed across 12 registries"
- "35.6% failure rate without trust checks (p < 0.00000001)"

**Automatisering:**
- [ ] B1.1a: Skapa `/stats/embed` endpoint — renderar shareable stats-cards (SVG/PNG)
- [ ] B1.1b: Skapa `/api/widget` — embeddable trust-badge-widget för tredjepartssajter
- [ ] B1.1c: Veckovis auto-genererad "State of Crypto Risk" one-pager (markdown → dev.to + blogg)
- [ ] B1.1d: Veckovis "State of AI Agents" one-pager med trenddata

### B1.2 — Badge Outreach Automation
**Redan påbörjat (50 repos, 8 manuella issues), men kan automatiseras.**

Script som:
1. Querypooar GitHub API för repos med "agent", "mcp-server", "langchain" i description
2. Filtrerar: >50 stars, har README.md, ingen existerande trust badge
3. Genererar personaliserad GitHub Issue: "Your agent [name] has a Trust Score of [X] on Nerq"
4. Inkluderar badge markdown: `![Trust Score](https://nerq.ai/badge/[name])`
5. Rate-limitad: max 10 issues/dag (white hat, inte spam)

**Varje badge = en dofollow backlink från en relevant repo.**

**Uppgifter:**
- [ ] B1.2a: Script `badge_outreach_auto.py`
- [ ] B1.2b: GitHub Issue template (personaliserad per agent)
- [ ] B1.2c: LaunchAgent: kör dagligen, 10 issues/dag
- [ ] B1.2d: Tracking: logga alla öppnade issues + responses

### B1.3 — Broken Link Reclamation (Automatiserad)
**Hitta döda länkar på crypto/AI-sajter och erbjud ZARQ/Nerq som ersättning.**

Script som:
1. Crawlar topp 50 crypto-bloggar och AI-tool-listor
2. Hittar 404-länkar (broken links)
3. Matchar: pekar den döda länken mot något ZARQ/Nerq kan ersätta?
4. Auto-genererar outreach-mail (sparas som draft, manuellt godkänd)

**Uppgifter:**
- [ ] B1.3a: Script `broken_link_finder.py` (requests + beautifulsoup)
- [ ] B1.3b: Matching-logik mot våra sidor
- [ ] B1.3c: Mail-template för outreach

### B1.4 — Dev.to + Community Seeding (Redan delvis igång)
**Scout publicerar redan automatiskt på Dev.to och Bluesky.**

Utöka:
- [ ] B1.4a: Varje Scout-rapport inkluderar 2-3 länkar tillbaka till nerq.ai/safe/[agent]
- [ ] B1.4b: Varje vecko-rapport inkluderar link till zarq.ai/crash-watch
- [ ] B1.4c: Reddit auto-monitor: bevaka r/cryptocurrency, r/defi, r/artificial — flagga posts där ZARQ/Nerq data är relevant (manuell reply, inte auto-post)
- [ ] B1.4d: LangChain Forum: publicera integration guide (redan accepterad)

### B1.5 — HARO / Journalistplattformar
**2026: Plattformar som Connectively, Qwoted, Featured.com, SourceBottle.**

- [ ] B1.5a: Registrera ZARQ/Nerq på Connectively (HARO-efterträdare)
- [ ] B1.5b: Registrera på Qwoted (expert-plattform)
- [ ] B1.5c: Skapa presskit: zarq.ai/press med stats, logotyper, citat, founder bio
- [ ] B1.5d: Auto-monitor: RSS-feed av relevanta journalist-queries

### B1.6 — Podcast/Guest Post Pipeline
**Lägre prioritet men hög impact per länk.**

- [ ] B1.6a: Lista 20 crypto/AI-podcasts som tar gäster
- [ ] B1.6b: Pitchmall: "Moody's for the Machine Economy"
- [ ] B1.6c: Lista 10 sajter med "write for us" i crypto/AI-nischen
- [ ] B1.6d: Guest post-pitchmall med datavinkel

---

## DAG 8-9: TEKNISK SEO + INDEXERING

### T1.0 — Sitemap Management
- [ ] T1.0a: Ny sitemap: `/sitemap-tokens.xml` (205 URLs)
- [ ] T1.0b: Ny sitemap: `/sitemap-safe.xml` (500 URLs)
- [ ] T1.0c: Ny sitemap: `/sitemap-compare.xml` (100 URLs)
- [ ] T1.0d: Ny sitemap: `/sitemap-mcp.xml` (500 URLs)
- [ ] T1.0e: Ny sitemap: `/sitemap-learn.xml` (5 URLs)
- [ ] T1.0f: Uppdatera sitemap index: `/sitemap.xml`
- [ ] T1.0g: Submit alla sitemaps via Google Search Console

### T1.1 — robots.txt Optimization
- [ ] T1.1a: Tillåt alla nya URL-patterns
- [ ] T1.1b: Verifiera AI-bot access (redan i llms.txt)

### T1.2 — Intern Länkning
- [ ] T1.2a: Varje token-sida → 5 liknande tokens + hub
- [ ] T1.2b: Varje agent-safe-sida → 5 liknande agents + hub
- [ ] T1.2c: Varje comparison → relaterade comparisons + båda agent-sidor
- [ ] T1.2d: Alla hubs (tokens, /safe, /compare, /mcp) korslänka varandra
- [ ] T1.2e: Befintliga sidor (dashboard, reports) länka till nya sidor

### T1.3 — Stegvis Indexering
- [ ] T1.3a: Dag 1: Publicera 50 token-sidor, verifiera i GSC
- [ ] T1.3b: Dag 2: Publicera resterande 155 token-sidor
- [ ] T1.3c: Dag 3: Publicera 100 agent-safe-sidor
- [ ] T1.3d: Dag 4-5: Resterande 400 agent-safe + comparisons
- [ ] T1.3e: Dag 6-7: MCP-sidor
- [ ] T1.3f: Google Indexing API: ping för varje ny batch

### T1.4 — Performance
- [ ] T1.4a: Server-side caching för alla template-sidor (1h TTL)
- [ ] T1.4b: Verifiera P50 latency hålls under 50ms med nya sidor
- [ ] T1.4c: Cloudflare page rules för caching av statiska delar

---

## DAG 9-10: MÄTNING + LAUNCH

### M1.0 — Tracking
- [ ] M1.0a: Google Search Console: verifiera indexering per batch
- [ ] M1.0b: Dashboard-utökning: "Organic pages indexed" counter
- [ ] M1.0c: Dashboard: "Backlinks generated this week" (badge issues öppnade + svar)
- [ ] M1.0d: Dashboard: "Top ranking pages" (manuell check veckovis)

### M1.1 — Launch-sekvens
1. Token-sidor live → submit sitemap → vänta 24h
2. Agent-safe-sidor live → submit → vänta 24h
3. Comparison-sidor + MCP-sidor → submit
4. Backlink-automation igång (badge outreach 10/dag)
5. Scout-rapporter uppdaterade med länkar till nya sidor
6. Dev.to-artiklar med data-citat och länkar

### M1.2 — Veckovis Review (ongoing)
- [ ] Indexeringsgrad (mål: 80%+ inom 2 veckor)
- [ ] Organisk trafik per sid-typ
- [ ] Backlinks genererade
- [ ] Ranking-positioner för target keywords (stickprov)

---

## SIDORÄKNING

| Kategori | Antal sidor | Primärt sökord-kluster |
|---|---|---|
| ZARQ Token Safety | 205 | "is [token] safe" |
| ZARQ Token Hub | 1 | "crypto risk ratings" |
| ZARQ Crash Watch | 1 | "crypto crash prediction" |
| ZARQ Yield Risk | 1 | "defi yield risk" |
| ZARQ Learn Hub + Guider | 6 | "crypto due diligence" |
| ZARQ Comparisons | 20 | "[token] vs [token] risk" |
| Nerq Agent Safety | 500 | "is [agent] safe" |
| Nerq Agent Safety Hub | 1 | "trusted AI agents" |
| Nerq Comparisons | 100 | "[agent] vs [agent]" |
| Nerq Compare Hub | 1 | "AI agent comparison" |
| Nerq MCP Trust | 500 | "best MCP servers" |
| Nerq MCP Hub | 1 | "MCP server directory" |
| **TOTALT** | **~1,337 sidor** | |

---

## BACKLINK-PROGNOS

| Metod | Tidsram | Förväntade links/månad | Kvalitet |
|---|---|---|---|
| Badge outreach (auto) | Vecka 2+ | 20-50 | Hög (dofollow från relevanta repos) |
| Citerbar data (rapporter) | Vecka 3+ | 5-15 | Mycket hög (editorial) |
| Broken link reclamation | Vecka 3+ | 3-10 | Hög |
| Dev.to + community | Löpande | 10-20 | Medium (nofollow men brand exposure) |
| HARO / journalistplattformar | Månad 2+ | 2-5 | Mycket hög (news sites DA 70+) |
| Guest posts / podcasts | Månad 2+ | 2-4 | Mycket hög |
| **Totalt estimerat** | **Steady state** | **~40-100 links/mån** | |

---

## RISKER

1. **Google ser programmatiska sidor som thin content** → Mitigation: varje sida har unik dynamisk data, inte bara template-swap.
2. **Badge outreach uppfattas som spam** → Mitigation: max 10/dag, personaliserat, genuint värde (trust score).
3. **Server-load med 1,337 nya sidor** → Mitigation: server-side cache, Cloudflare.
4. **Indexering tar lång tid** → Mitigation: Google Indexing API, stegvis utrullning, sitemap-submit.

---

## STARTORDNING (imorgon)

1. **Z1.0** — Token safety template (det som har störst volym)
2. **N1.0** — Agent safety template (blått hav, noll konkurrens)
3. **B1.2** — Badge outreach automation (backlinks börjar genereras direkt)
4. Resten i tur och ordning

---

*Fil: ~/agentindex/docs/SEO_Traffic_Sprint_v1.md*
*Nästa handover ska inkludera denna sprint.*
