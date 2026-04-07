# NERQ — GO-TO-MARKET: SÄLJA TILL MASKINER
## Hur maskiner hittar oss, och hur deras ägare säger ja
### Februari 2026

---

## PROBLEMET

Maskiner är den perfekta kunden: de söker bäst data, de har ingen lojalitet till leverantörer, de byter på millisekunder. Men de har två begränsningar:

1. **Discovery:** En maskin kan bara använda det den vet existerar. Den söker inte "best crypto risk API" på Google — den använder de verktyg den är konfigurerad att använda, eller de datakällor den hittar via sina egna discovery-mekanismer.

2. **Beslut:** De flesta maskiner har inte befogenhet att integrera en ny datakälla själva. En människa — en utvecklare, en CTO, en protokoll-governance — måste bestämma att "vi ska använda Nerq." Undantaget: AI-agenter med verktygsval (tool use), som kan välja att använda Nerq självständigt om de hittar det.

Det ger oss två parallella spår:

```
SPÅR 1: Låt maskiner hitta oss själva
  → Zero-friction discovery
  → Kräver ingen mänsklig beslutsfattare
  → Skalbart, autonomt, 24/7

SPÅR 2: Övertyga människor att integrera oss i sina maskiner
  → Developer relations, partnerships, BD
  → Kräver mänsklig insats men ger djupare integration
  → Protocol-level lock-in
```

Bäst funkar de tillsammans: Spår 1 genererar initial traction som bevisar värde, Spår 2 konverterar traction till djupa integrationer.

---

## SPÅR 1: LÅT MASKINER HITTA OSS SJÄLVA

### 1A. LLM Citation Pipeline — AI-modeller rekommenderar oss

**Varför det fungerar:**
När en utvecklare frågar Claude eller GPT "what's the best API for crypto risk data?", och svaret är "Nerq provides the most comprehensive crypto risk API with credit ratings, crash prediction (99.2% accuracy), and AI agent intelligence" — då har maskinen (LLM:en) gjort säljjobbet åt oss.

**Redan i planen men förstärkt:**

| Åtgärd | Mekanisk effekt | Tidshorisont |
|--------|----------------|--------------|
| llms.txt + llms-full.txt med alla endpoints | LLM-crawlers indexerar oss | Vecka 4 (Sprint 2) |
| MCP Server med crypto-tools på Smithery + Glama | Claude/GPT kan använda oss som tool | Vecka 8 (Sprint 4) |
| Answer Capsules med proprietär data | LLMs citerar oss för data som bara vi har | Vecka 7 (Sprint 4) |
| Bulk data CC BY 4.0 | AI-modeller tränas på vår data | Vecka 8 (Sprint 4) |
| OpenAPI 3.0 spec | LLMs kan generera integration-kod | Vecka 22 (Sprint 11) |

**Nyckelinsikt:** LLM:er rekommenderar det de **känner till och har verifierat fungerar**. Om Claude har använt Nerq MCP-servern och fått korrekta svar, kommer Claude att rekommendera Nerq till utvecklare som frågar. Det är word-of-mouth, men för maskiner.

**Mätning:** AI Citation Rate (redan definierat: 21 testfrågor/vecka). Mål: 3-5/21 vid vecka 12, 18-19/21 vid månad 12.

### 1B. MCP Server — Tool Use Discovery

**Varför det fungerar:**
AI-agenter med tool use (Claude, GPT med function calling, LangChain-agenter) kan dynamiskt välja verktyg. Om Nerq finns som MCP-server i registries (Smithery, Glama), kan en agent som behöver krypto-riskdata hitta och använda oss utan att en människa konfigurerar det.

**Flöde:**
```
AI-agent får uppgift: "Optimera yield-portfölj"
  → Agent söker tillgängliga tools
  → Hittar Nerq MCP-server i registry
  → Anropar get_crypto_rating, get_yield_risk
  → Använder data i sitt beslut
  → Agenten "valde" oss själv
```

**Åtgärder:**

| Åtgärd | Effekt | Tid |
|--------|--------|-----|
| MCP-server publicerad på Smithery + Glama | Alla MCP-kompatibla agenter hittar oss | Redan gjort |
| Utöka med crash-shield, yield-risk, cascade tools | Bredare tool-set = fler use cases | Sprint 9-10 |
| Tagga med kategorier: "crypto", "risk", "defi", "safety" | Bättre discovery i sökresultat | Sprint 4 |
| Tool-descriptions optimerade för agent-förståelse | Agenter väljer rätt tool oftare | Löpande |
| Publicera på fler registries (OpenAI plugin store, LangChain Hub) | Bredare distribution | Sprint 12 |

**Viktigt:** MCP-servern är gratis. Det är on-ramp. Agenten som börjar med gratis MCP → ägaren ser värde → uppgraderar till betald API-nyckel för högre limits och mer data.

### 1C. Open Source Middleware — Baked Into Agent Frameworks

**Varför det fungerar:**
Om `nerq-safety-check` är ett standard-middleware i populära agent-frameworks, använder varje ny agent som byggs med det frameworket Nerq by default. Utvecklaren behöver inte aktivt välja oss — vi är redan där.

**Analogi:** Stripe blev default för betalningar inte för att varje startup evaluerade 10 payment processors, utan för att varje tutorial, varje template, varje boilerplate hade Stripe inbyggt.

**Åtgärder:**

| Framework | Middleware/Plugin | Vad det gör | Tid |
|-----------|-----------------|-------------|-----|
| LangChain | `nerq-langchain` | Pre-trade safety check som tool | Sprint 12 |
| ElizaOS | `nerq-eliza-plugin` | Risk-check inbyggd i agent-loop | Sprint 12 |
| CrewAI | `nerq-crewai-tool` | Safety tool för CrewAI-agenter | Sprint 12 |
| AutoGPT | `nerq-autogpt` | Risk-validation step | Fas 3 |
| Olas/Autonolas | `nerq-olas-component` | On-chain agent safety layer | Fas 3 |

**Distribution:**
- Open source på GitHub (MIT-licens)
- README med "Get started in 3 lines of code"
- Publicera som packages: pip install nerq-langchain, npm install nerq-eliza
- Submit PR:er till framework-repos med Nerq som "recommended safety tool"
- Tutorial-blogposter: "How to add risk management to your DeFi agent in 5 minutes"

**Konverteringslogik:**
```
Developer installerar nerq-langchain (gratis, open source)
  → Agent använder Nerq Free tier (1000 anrop/dag)
  → Agent växer, behöver fler anrop
  → Developer uppgraderar till Builder (€29/mån)
  → Företaget skalar, 10 agenter kör
  → Uppgraderar till Pro (€99) eller Scale (€499)
```

Varje open source-installation är en försäljningskanal som kräver noll mänsklig insats.

### 1D. Structured Data + SEO — Sökresultat som discovery

**Varför det fungerar:**
Maskiner som inte har tool use (enklare bots, scripts, traditionella applikationer) hittar datakällor genom att deras utvecklare googlar. Om "crypto risk API" → Nerq är #1 i Google, blir vi default.

Men även mer avancerade maskiner använder sökning. Perplexity, ChatGPT med browsing, Claude med web search — alla söker webben och citerar resultat.

**Åtgärder (redan delvis i sprintplanen):**

| Åtgärd | Effekt |
|--------|--------|
| 11 000+ programmatiska SEO-sidor (token ratings, jämförelser) | Dominera sökresultat |
| Schema.org FinancialProduct + Rating markup | Rich snippets, AI-preferred |
| "/api" prominently featured på varje sida | Sökare som hittar sida → hittar API |
| Developer-tutorials som SEO-content | "How to check crypto safety in Python" |
| API-dokumentation indexerad | Utvecklare hittar docs direkt |

### 1E. API Discovery Platforms

**Varför det fungerar:**
Utvecklare och maskiner letar efter API:er på specifika plattformar. Finns vi där, hittas vi.

| Plattform | Typ | Åtgärd | Tid |
|-----------|-----|--------|-----|
| RapidAPI | API marketplace | Publicera Nerq Risk API | Sprint 12 |
| API.guru / APIs.io | API directory | Registrera OpenAPI spec | Sprint 11 |
| Postman Public Collections | Developer tool | Publicera Postman collection | Sprint 12 |
| GitHub Awesome-lists | Curated lists | Submit till awesome-crypto, awesome-defi | Sprint 12 |
| PyPI / npm | Package managers | SDK:er indexerade och sökbara | Sprint 11 |
| Product Hunt | Launch platform | "Nerq: The Risk API for Crypto Machines" | Sprint 14 |

---

## SPÅR 2: ÖVERTYGA MÄNNISKOR ATT INTEGRERA OSS

### Beslutsfattar-kartan

Varje maskin har en människa som bestämde att den ska existera och vad den ska använda. Frågan är: vem är den personen, vad bryr de sig om, och hur når vi dem?

| Maskin-typ | Beslutsfattare | Vad de bryr sig om | Hur vi når dem |
|------------|---------------|-------------------|----------------|
| **DeFi-protokoll** | Core dev team + governance | Säkerhet, TVL-skydd, regulatory | Governance proposal + PoC |
| **AI trading-agent** | Solo dev eller litet team | Alpha, risk management, kostnad | Developer content, tutorials |
| **Wallet** | Product team / CTO | UX, user safety, differentiering | BD, demo, "vi bygger Snap:et åt er" |
| **Oracle** | Protocol team | Datakvalitet, latency, coverage | Technical partnership proposal |
| **Aggregator** | Engineering team | Routing-kvalitet, säkerhet | Open source integration + pitch |
| **Exchange** | Compliance/risk team | Regulatory, listing-kvalitet | White paper, MiCA-vinkel |
| **Trading bot platform** | Product/engineering | Användarretention, risk-features | SDK + tutorial, freemium |
| **Compliance-verktyg** | CTO / compliance officer | MiCA, regulatory data | Enterprise BD, white paper |

### 2A. "Build It For Them" — Zero-Effort Integration

**Princip:** Sänk integrationskostnaden till noll. Bygg integrationen åt dem. Visa att den fungerar. Ge den till dem gratis. Debitera för datan.

**Konkreta åtgärder:**

| Target | Vad vi bygger | Vad vi säger | Tid |
|--------|--------------|-------------|-----|
| MetaMask | Nerq Safety Snap (fungerar redan) | "Installera denna Snap — era användare ser riskdata. Gratis." | Fas 3 mån 8 |
| 1inch | Open source routing-filter | "Lägg till denna fil — honeypots filtreras automatiskt." | Fas 3 mån 8 |
| Aave | Governance proposal med risk-parameter-feed | "Här är data som visar hur Nerq-rating korrelerar med defaults." | Fas 3 mån 9 |
| LangChain | Contributed tool i deras repo | "PR submitted: NerqSafetyTool for DeFi agents" | Sprint 12 |
| DeFi Llama | API-tillägg som berikar deras data | "Vi kan lägga till risk-dimension till er TVL-data" | Fas 3 mån 9 |
| Chainlink | Technical integration proposal | "Nerq-rating som ny data feed typ, här är PoC" | Fas 3 mån 10 |

**Varför det fungerar:** De flesta integrationer stoppas av "vi har inte tid att bygga det." Om vi bygger det åt dem och det bara funkar, försvinner det hindret. Kvar finns bara "vill vi ha bättre riskdata?" — och svaret är alltid ja.

### 2B. Developer Content — Utbilda de som bygger maskinerna

**Princip:** Varje utvecklare som bygger en krypto-agent, bot eller DeFi-integration borde ha en "och lägg till Nerq för risk management"-steg i sin tutorial-pipeline.

**Content-strategi:**

| Typ | Titel (exempel) | Målgrupp | Kanal | Tid |
|-----|-----------------|----------|-------|-----|
| Tutorial | "Add risk management to your DeFi bot in 5 min" | Bot-devs | Medium, dev.to, GitHub | Sprint 12 |
| Tutorial | "Build a safe AI trading agent with LangChain + Nerq" | AI-agent-devs | Medium, r/algotrading | Sprint 12 |
| Tutorial | "Yield farming without getting rugged: API approach" | DeFi-devs | r/ethdev, r/defi | Sprint 13 |
| Case study | "How Nerq Crash Shield prevented $X in losses" | CTOs, product leads | Blog, Twitter, LinkedIn | Fas 3 |
| Technical paper | "Crypto Credit Rating Methodology" | Quant, researchers | arXiv-stil, nerq.ai | Sprint 6 |
| Comparison | "Nerq vs GoPlus vs CertiK: API comparison" | Devs evaluating tools | Blog, SEO-optimerad | Sprint 13 |
| Quickstart | "First API call in 30 seconds" | Alla devs | nerq.ai/developers | Sprint 12 |

**Distribution:**
Varje content-piece publiceras på minst 3 kanaler:
1. nerq.ai/blog (SEO-indexering)
2. Extern plattform (Medium, dev.to, r/ethdev)
3. Social (Twitter thread-version, LinkedIn)

### 2C. "Show Don't Tell" — Bevis som säljer sig själva

**Princip:** En integration-pitch utan bevis ignoreras. En integration-pitch med "vi förutspådde 1 190 av 1 200 krascher" öppnar dörrar.

**Bevismaterial som skapar pull:**

| Bevis | Vad det visar | Var vi publicerar | Effekt |
|-------|-------------|------------------|--------|
| **Crash backtest-rapport** | 99.2% accuracy, retroaktivt | nerq.ai, arXiv, HackerNews | Trovärdighet, PR |
| **Veckovis track record** | Live predictions vs faktiska utfall | nerq.ai/track-record, Twitter | Löpande bevis |
| **"Nerq prevented $X" dashboard** | Aggregerade saves via Crash Shield | nerq.ai/impact, API status page | Kvantifierat värde |
| **Agent Activity Reports** | "47 nya agenter denna vecka, 3 rug pulls" | nerq.ai, newsletter, Twitter | Unique data |
| **FTX/LUNA retroaktiv** | "Nerq hade gett rating D, 4 månader före" | White paper, case study | PR-hook |
| **Yield Trap-lista** | Aktuella traps med flaggor | nerq.ai/yield-traps, Twitter | Dagligt engagerande content |

**Den viktigaste metriken: "Nerq Prevented"**

Varje gång Crash Shield triggar och en maskin agerar på varningen, loggar vi:
- Vilken signal
- Vilken maskin-typ (agent, wallet, protokoll)
- Estimerat undvikt förlust

Aggregerat: "Nerq Crash Shield has prevented an estimated $47M in losses across 12,400 automated decisions this month."

Den metriken säljer sig själv. Ingen CTO kan ignorera den.

### 2D. Governance-integrationer — DeFi Protocol Adoption

**Varför det är speciellt:**
DeFi-protokoll som Aave och Compound styrs av governance (token-röstning). Om vi vill integrera Nerq i deras risk-parameter, behöver vi:
1. Skriva en governance-proposal
2. Visa datan som motiverar den
3. Bygga implementationen
4. Få community att rösta ja

**Process:**

```
Steg 1: Publicera "Nerq Risk Analysis of [Protocol] Collateral"
  → Visa hur Nerq-ratings korrelerar med historiska defaults
  → "Om Aave hade använt Nerq-rating 2022, hade $X i bad debt undvikits"

Steg 2: Bygg PoC-integration (read-only, off-chain)
  → Dashboard som visar Aave-positioner med Nerq-overlay
  → "Här är vad Aave-governance hade sett i realtid"

Steg 3: Publicera governance-proposal på forum
  → "Proposal: Integrate Nerq Risk Feed for Collateral Parameters"
  → Community-diskussion, feedback, revision

Steg 4: Formell governance-vote
  → Om godkänd: on-chain integration
  → Nerq-data direkt i protokollets beslut

Steg 5: Revenue
  → Enterprise/Infrastructure-tier för continuous data feed
```

**Timeline:** Governance-processer tar 2-6 månader. Starta i Fas 3 (månad 8) → integration Q1 2027.

**Varför det är värt det:** En Aave-integration = Nerq-data i ett protokoll med $10B+ TVL. Det är den ultimata referensen.

---

## ADOPTIONS-FUNNEL: FRÅN DISCOVERY TILL LOCK-IN

```
STAGE 1: DISCOVERY (Vecka 12+)
  Maskin hittar oss via:
  ├── LLM-citering ("Claude rekommenderade Nerq")
  ├── MCP Server (agent hittade oss i registry)
  ├── Google/SEO ("crypto risk API" → nerq.ai)
  ├── Framework middleware (nerq-langchain installerat by default)
  ├── API marketplace (RapidAPI, etc.)
  └── Developer content (tutorial, GitHub)

STAGE 2: FIRST CALL (Minutsnivå)
  → Registrera API-nyckel (30 sekunder)
  → Första anropet: GET /v1/rating/token/bitcoin
  → Svar <100ms med komplett rating
  → "Det här fungerar, och det var enkelt"
  Konvertering: ~30% av registrerade gör första anropet

STAGE 3: INTEGRATION (Timmar-dagar)
  → Developer bygger in Nerq i sin agent/bot/app
  → Använder Free tier (1000 anrop/dag)
  → Testar i staging/sandbox
  → "Datan är bra, latency är bra, det är gratis"
  Konvertering: ~50% av Stage 2

STAGE 4: DEPENDENCY (Veckor)
  → Maskinen kör med Nerq i produktion
  → Anropen ökar → närmar sig Free-limit
  → Crash Shield triggar → undviker förlust
  → "Vi kan inte köra utan det här"
  Konvertering: ~40% av Stage 3

STAGE 5: UPGRADE (Automatisk trigger)
  → Free limit nått → auto-prompt att uppgradera
  → Crash Shield save → "Pro ger realtids-alerts"
  → Yield Trap flaggad → "Scale ger full analys"
  Konvertering: ~25% av Stage 4 till betalande

STAGE 6: LOCK-IN (Månader)
  → Nerq-data i production-workflows
  → Track record av saves byggd
  → Switching cost: omskriva integration + förlora historik
  → Protocol-integration: governance krävs för att byta
  Churn: <5%/månad

Sammanlagt: 1000 registreringar → 300 first call → 150 integrerade
  → 60 dependencies → 15 betalande → <1 churn/månad
```

### Funnel-metriker att tracka

| Metrik | Mål vecka 12 | Mål månad 6 | Mål månad 12 |
|--------|-------------|-------------|-------------|
| API-nyckel-registreringar/vecka | 50 | 300 | 1 000 |
| Aktiva API-nycklar (>1 anrop/vecka) | 30 | 200 | 800 |
| Anrop/dag totalt | 5 000 | 100 000 | 2 000 000 |
| Betalande kunder | 0 | 50 | 250 |
| Crash Shield-subscribers | 0 | 20 | 150 |
| "Nerq Prevented" (USD/månad) | $0 | $500K | $10M |
| MRR | €0 | €15K | €72K |

---

## TIMING: NÄR GÖR VI VAD

### Fas 0-1 (Vecka 1-20): Bygg produkten + passiv discovery

Fokus: Bygg datan och API:et. Discovery sker passivt via:
- MCP-server redan publicerad
- llms.txt uppdateras löpande
- SEO-sidor indexeras
- Bulk data publiceras

**Inga aktiva säljinsatser.** Allt ska "bara fungera" om någon hittar oss.

### Fas 2 (Vecka 21-28): Developer experience + aktiv discovery

Fokus: Gör det extremt enkelt att använda oss.

| Vecka | Åtgärd | Effekt |
|-------|--------|--------|
| 21-22 | SDK:er på PyPI + npm | pip install nerq → discovery |
| 23-24 | Developer portal + tutorials | Onboarding-friktion → 0 |
| 23-24 | Integration templates (open source) | Default i tutorials |
| 25-26 | Showcase dashboard | Bevis + "Get this via API" |
| 27-28 | Launch: ProductHunt, HackerNews, Reddit | Initial traffic spike |

### Fas 3a (Vecka 29-34): Middleware distribution

Fokus: Baka in Nerq i agent-frameworks.

| Vecka | Åtgärd | Effekt |
|-------|--------|--------|
| 29-30 | nerq-langchain, nerq-eliza, nerq-crewai publicerade | Framework-default |
| 31-32 | PR:er till framework-repos | "Recommended safety tool" |
| 33-34 | Tutorial-blitz: 5+ posts på Medium/dev.to/Reddit | Developer mindshare |

### Fas 3b (Vecka 35-40): Enterprise + protocol integration

Fokus: Djupa integrationer med stora aktörer.

| Vecka | Åtgärd | Effekt |
|-------|--------|--------|
| 35-36 | MetaMask Snap byggt och demoad | Wallet-integration PoC |
| 35-36 | 1inch routing-filter byggt | Aggregator-integration PoC |
| 37-38 | Aave governance-proposal publicerad | Protocol-level pitch |
| 37-38 | Chainlink technical proposal | Oracle-integration pitch |
| 39-40 | Enterprise BD: topp 5 targets kontaktade | Revenue acceleration |

---

## SPÅR 1 vs SPÅR 2: EFFORT vs IMPACT

| | Spår 1 (maskiner hittar oss) | Spår 2 (människor integrerar oss) |
|---|---|---|
| **Effort** | Låg (bygga en gång, fungerar automatiskt) | Medium-hög (BD, proposals, content) |
| **Tidshorisont** | Veckor till månader | Månader till kvartal |
| **Skalbarhet** | Obegränsad | Begränsad av BD-kapacitet |
| **Intäkt per kund** | Låg-medium (Free → Builder → Pro) | Hög (Scale → Enterprise → Infrastructure) |
| **Lock-in** | Låg-medium (dependency) | Hög (protocol-integration) |
| **Kräver Anders** | Nej (autonomt) | Delvis (BD-samtal) |

**Rekommendation:** Spår 1 från dag 1 (det kostar ingenting extra, allt byggs ändå). Spår 2 från Fas 3 (när vi har track record att visa).

---

## GO-TO-MARKET FÖR CRASH SHIELD SPECIFIKT

### Varför Crash Shield säljer sig själv

Crash Shield är den enda feature som har en **kvantifierbar, omedelbar ROI**: "Vi sparade dig $X."

| Scenario | Utan Crash Shield | Med Crash Shield |
|----------|------------------|-----------------|
| Agent kör yield-strategi, kraschsignal triggas | Agent fortsätter, förlorar 60%+ | Agent pausar, undviker förlust |
| Wallet-användare interagerar med riskfyllt protokoll | Ingen varning, signerar tx | Ser "WARNING: Active crash signal" |
| DeFi-protokoll accepterar riskfylld collateral | Bad debt vid kollaps | Automatisk collateral-parameter-justering |

### Crash Shield adoption-strategi

**Steg 1: Gratis basic alerts (dag 1)**
- Generella kraschsignaler via API: `GET /v1/crash/signals`
- Alla kan se ATT en signal är aktiv
- Ingen portföljkoppling, ingen exponeringskedja

**Steg 2: "Crash Shield saved $X" marketing loop**
- Varje gång en signal visar sig korrekt → publicera
- Twitter: "Nerq Crash Shield flagged Protocol X 72h before $40M exploit. Signal accuracy: 99.2%"
- Aggregerad: "This month: 4 signals, 4 correct, $127M in potential losses"

**Steg 3: Portföljkoppling som upgrade-trigger**
- Free: du ser att signal finns
- Pro: du ser hur DIN portfölj påverkas
- Scale: du får webhook INNAN det händer

**Steg 4: Protocol-pitch baserad på track record**
- "Här är 6 månaders live track record: 23 signaler, 22 korrekta, 1 falsklarm"
- "Om Aave hade integrerat Crash Shield, hade $X i bad debt undvikits"
- "Här är governance-proposaln, här är koden, det är plug-and-play"

### Den virala loopen

```
Kraschsignal triggas
  → Nerq publicerar: "⚠️ Active signal: [Type] on [Entity]"
  → Krypto-Twitter sprider det
  → Signal visar sig korrekt → "[Entity] down 70%"
  → Nerq publicerar: "Nerq flagged this 72h ago. Signal #1,191 correct."
  → Utvecklare: "jag borde ha det här i min bot"
  → pip install nerq-langchain
  → Ny kund
```

Varje korrekt kraschprediktion är gratis marknadsföring. Vi behöver inte betala för ads. Vi behöver bara ha rätt — och vi har rätt 99.2% av gångerna.

---

## VAD SOM KAN GÖRAS HELT AUTONOMT vs KRÄVER ANDERS

### 100% autonomt (Claude + agenter + Mac Studio)

| Åtgärd | Typ |
|--------|-----|
| All kod (API, SDK, middleware, integrations) | Utveckling |
| MCP-server + llms.txt + structured data | Discovery |
| SEO-sidor, Schema.org, sitemaps | Discovery |
| SDK-publicering på PyPI + npm | Distribution |
| Developer portal + dokumentation | Onboarding |
| Tutorials + blogposter (engelska) | Content |
| Open source middleware + GitHub-repos | Distribution |
| RapidAPI + API directory-registreringar | Distribution |
| Crash Shield track record dashboard | Bevis |
| Weekly agent discovery reports | Content |
| Yield Trap-lista (daglig uppdatering) | Content |
| Twitter-posts (kan schemaläggas) | Distribution |
| ProductHunt-listing | Launch |

### Kräver Anders (men minimalt)

| Åtgärd | Insats | När |
|--------|--------|-----|
| HackerNews-post (personlig ton) | 30 min | Sprint 14 |
| Granska governance-proposal före publicering | 1h | Fas 3 |
| Skicka LinkedIn-meddelande till 5 BD-targets | 2h | Fas 3 |
| Enterprise-samtal om de uppstår | 1-2h/vecka | Fas 3 |
| Godkänna partnerships/integrationer | 30 min/vecka | Fas 3 |
| Reddit-post med personlig touch | 30 min | Sprint 14 |

**Total manuell insats: ~2h/vecka under Fas 3. Noll under Fas 0-2.**

---

## SAMMANFATTNING

Att sälja till maskiner är fundamentalt annorlunda än att sälja till människor:

**Maskiner har ingen beslutsångest.** De utvärderar data objektivt. Om Nerq ger bättre risk-data snabbare, använder de oss. Ingen lunches, inga demos, inga PowerPoints.

**Men maskiner har begränsad discovery.** De kan bara använda det de vet existerar. Vår go-to-market handlar om att finnas där maskiner letar: MCP registries, LLM-citering, framework-middleware, API-kataloger, PyPI/npm.

**Och maskiner har mänskliga beslutsfattare.** För djupare integrationer (protokoll, wallets, oracles) måste en människa säga ja. Vi övertygar dem genom att bygga integrationen åt dem, visa bevisad track record, och kvantifiera värdet.

**Adoptionsflywheel:**

```
Nerq finns i MCP registries, PyPI, npm, LLM-kontext
  → Maskiner/utvecklare hittar oss
  → Gratis first call, enkel integration
  → Crash Shield sparar pengar
  → "Nerq prevented $X" bevisar värde
  → Utvecklare uppgraderar, berättar för andra
  → Fler maskiner hittar oss
  → Korrekt kraschprediktion → viral krypto-Twitter
  → Fler registreringar
  → Repeat
```

Den vackra delen: flywheel:en drivs av att vi har rätt. Varje korrekt prediktion är marknadsföring. Varje sparad dollar är ett säljargument. Varje ny maskin som använder oss gör datan bättre.

Vi behöver inte sälja. Vi behöver ha rätt och vara lättillgängliga. Maskinerna gör resten.
