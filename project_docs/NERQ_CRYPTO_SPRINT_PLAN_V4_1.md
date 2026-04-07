# NERQ CRYPTO — MASTER SPRINT PLAN v4.1
## Build Complete Product → Traction → Revenue → Exit/Operate
### Baserad på: Sprint Plan v3.1 + Machine First Vision + Go To Market Machines + Investor Pitch v4
### Datum: 2026-03-01 | Sprint 2.5 avklarat | System stabiliserat

---

## VISION I ETT STYCKE

NERQ Crypto är världens första machine-first crypto risk intelligence plattform. Vi har byggt det mest precisa kraschprediktionssystemet som validerats (100% death recall, 98% precision OOS), ett portabelt alfa-system med Sharpe 2.82 som överträffar alla kända kryptostrategier, och en unik databas av 4.9M AI-agenter korskopplad med kryptodata. Vi bygger infrastrukturen som autonoma system i kryptoekonomin inte kan fungera utan — API:et är terminalen, maskinerna är kunderna. Plattformen får ett eget varumärke/domän separat från nerq.ai:s AI-agentindex, så att de två kan säljas oberoende.

---

## NYCKELPRINCIPER

1. **Paper trading FÖRST.** Idag 1 mars 2026 = rebalanceringsdatum. Vi startar paper trading i alla tre portföljer (Alpha, Dynamic, Conservative) NU. Varje dag utan live track record är en förlorad dag.

2. **Bygg HELA produkten innan revenue.** Monetarisering kommer när produkten är komplett och vi har traction. Under byggfasen är allt gratis via "Early Access" — bygger användarbas, track record och bevisar värde.

3. **Machine-first, allt annat sekundärt.** API:et är produkten. Dashboard och webbsidor är skyltfönster.

4. **Separat varumärke/domän.** Kryptoprojektet lever under eget namn, tekniskt separerbart från nerq.ai vid försäljning.

5. **Auditbar historia.** Allt kring handelsstrategier: signerade timestamps, deterministisk replikering, oföränderlig logg. Inga retroaktiva justeringar.

6. **Revenue → Exit/Operate — sist.** Först bygg. Sedan traction. Sedan pengar. Sedan exit-beslut.

---

## KRYPTOPROJEKTET — SEPARATION FRÅN NERQ.AI

### Nuläge

NERQ.ai = AI Agent Index (4.9M agenter, PostgreSQL, produktion)
Krypto = Risk Intelligence (198 rated tokens, SQLite 336MB, produktion)

De delar samma FastAPI-app (`discovery.py`), samma server (Mac Studio), samma Cloudflare Tunnel.

### Separationsplan (inbakat i sprintarna)

**Sprint 3.0:** Välja nytt namn + registrera domän
**Sprint 3–4:** Refaktorera krypto-routes till egen FastAPI sub-app
**Sprint 5:** Ny domän via Cloudflare Tunnel
**Sprint 7+:** Egen landing page, eget varumärke, egna SEO-sidor
**Vid exit:** Koden kan extraheras som fristående repo inom 1-2 dagars arbete

**Arkitekturmål:**
```
nerq.ai          → localhost:8000 → discovery.py    (AI Agent Index)
[nytt-namn].com  → localhost:8000 → crypto_app.py   (Crypto Risk Intelligence)

Delar: server, venv, Cloudflare Tunnel, Redis (separat namespace)
Separat: databaser, API-nycklar, domäner, LaunchAgents, kod
```

---

## EARLY ACCESS-MODELL

Under hela byggfasen (Sprint 3.0 → Sprint 14) är ALLT gratis. Strategi:

**"Early Access — Free during beta"**
- Alla API-endpoints öppna (rate limit 1,000/dag för att skydda infrastrukturen)
- Registrering krävs (samlar leads + visar traction)
- Badge/banner: "Early Access — free during founding period"
- Tidigt antagna får permanent lägre pris ("Founding Member pricing")
- Bygger användarbas + API-anropsstatistik = traction-bevis för exit/revenue

**Varför detta fungerar:**
- Noll friktion = maximal adoption
- Usage data bevisar product-market fit
- "X thousand API calls/day from Y registered developers" = exit-metrik
- Konvertering till betalt när produkten bevisat sitt värde

---

## TIDSÖVERSIKT — KOMPLETT

```
BYGGFAS: KOMPLETT PRODUKT (Sprint 3.0 → 14)
═════════════════════════════════════════════
Sprint 3.0  (Vecka 1, IDAG):     🔴 PAPER TRADING START + Varumärkesseparation
Sprint 3.1  (Vecka 2-3):         Crash Prediction v4 + DB-konsolidering + MCP publicering
Sprint 3.2  (Vecka 4-5):         Contagion Map + Stresstest + Transition Matrix
Sprint 4    (Vecka 6-8):         White Paper + Track Record + AI-citering + Bulk Data
Sprint 5    (Vecka 9-10):        Ny domän live + SEO-sidor + API Discovery
Sprint 6    (Vecka 11-12):       On-chain Agent Crawling + Agent ↔ Crypto graf
Sprint 7    (Vecka 13-14):       Wallet Behavior + Agent Activity Index
Sprint 8    (Vecka 15-16):       Propagated Risk Engine + Crash Shield API
Sprint 9    (Vecka 17-18):       Yield Risk API + Agent Discovery Reports
Sprint 10   (Vecka 19-20):       API Production-Grade + SDKs (PyPI + npm)
Sprint 11   (Vecka 21-22):       Developer Portal + Middleware Distribution
Sprint 12   (Vecka 23-24):       Showcase Dashboard + Launch
Sprint 13   (Vecka 25-28):       Protocol Integrations + Middleware Blitz + Enterprise BD

INTÄKTSFAS: MONETARISERING (Sprint 14)
══════════════════════════════════════
Sprint 14   (Vecka 29-30):       Pricing tiers live + Stripe + Konvertering

EXIT-FAS: FÖRBEREDELSE + BESLUT (Sprint 15)
═══════════════════════════════════════════
Sprint 15   (Vecka 31-34):       Investor deck + Fund GO/NO-GO + Exit/Operate beslut
```

**Paper trading löper parallellt genom ALLA sprints — det är en permanent bakgrundsprocess.**

---

## ═══════════════════════════════════════════════════════
## BYGGFAS: KOMPLETT PRODUKT
## Sprint 3.0 → Sprint 13
## ═══════════════════════════════════════════════════════

---

## SPRINT 3.0: PAPER TRADING START + VARUMÄRKESSEPARATION
### 🔴 VECKA 1 — STARTAR IDAG 2026-03-01

### Bakgrund — Handelssystemen (Investor Pitch v4)

| Portfölj | CAGR | Sharpe | MaxDD | Strategi |
|----------|------|--------|-------|----------|
| **Alpha Fund** (Pure L/S) | +281% | 2.82 | -71% | Long SAFE, Short CRITICAL. 5 par, månatlig rebalance, 90d hold. |
| **Dynamic Fund** | +79% | 2.02 | -26% | BTC-core + L/S overlay. Bear detection → defensiv allokering. |
| **Conservative** | +63% | 2.39 | -22% | Samma som Dynamic med lägre risk-budget. |

**Idag 1 mars = månatlig rebalanceringsdag.** Vi MÅSTE generera signaler idag och starta paper trading.

### 3.0.1 Paper Trading System (Dag 1-2) 🔴 PRIO 0

**A. Signalgenerering (deterministisk, replikerbar)**
- [ ] `paper_trading_signal.py`:
  - Läser risk-klassificering (SAFE/WATCH/WARNING/CRITICAL) från `crypto_trust.db`
  - Filtrerar: tillräcklig likviditet + Coinbase/Binance/Kraken
  - Top-5 SAFE → LONG, Top-5 CRITICAL/WARNING → SHORT
  - 5 par, exakt enligt Investor Pitch v4
- [ ] `bear_detection.py`:
  - BTC drawdown från 365d ATH
  - DD > -20% → BEAR-regim
  - Loggar regim-byten med timestamp

**B. Oföränderlig logg (audit trail)**
- [ ] `paper_trading.db` (SQLite, append-only):
  - `portfolio_signals`: datum, portfölj, signal_hash (SHA-256), signaler (JSON), regime
  - `portfolio_positions`: datum, portfölj, typ (LONG/SHORT/BTC/CASH), token, vikt, entry_price
  - `portfolio_nav`: datum, portfölj, nav_value, daily_return, cumulative_return, drawdown
  - `portfolio_trades`: datum, portfölj, action, token, side, price, quantity
  - `portfolio_regime`: datum, btc_price, btc_ath_365d, drawdown_pct, regime
  - `audit_log`: timestamp, event_type, data_hash (SHA-256), raw_data
- [ ] Varje entry: SHA-256 hash av föregående + ny data (kedjad)
- [ ] Ingen UPDATE/DELETE — INSERT only
- [ ] Mikrosekund-precision på timestamps

**C. Daglig NAV-beräkning**
- [ ] `paper_trading_daily.py` — hämtar priser, beräknar NAV, kör bear detection, signerar med SHA-256
- [ ] LaunchAgent: `com.nerq.paper-trading-daily` — 00:05 UTC dagligen

**D. Månatlig rebalancering**
- [ ] `paper_trading_rebalance.py` — nya signaler, stäng utgångna, öppna nya, regime-justering
- [ ] Cron: `0 0 1 * *`

**E. Startpositioner idag 2026-03-01**
- [ ] Alpha: 5 LONG (top SAFE) + 5 SHORT (top CRITICAL/WARNING)
- [ ] Dynamic: 40% BTC + 20% L/S (5 par) + 40% cash (BULL) / 10% BTC + 30% L/S + 60% cash (BEAR)
- [ ] Conservative: samma regimer, lägre risk
- [ ] Entry prices = stängningskurs 2026-03-01 UTC

### 3.0.2 Paper Trading Dashboard + API (Dag 2-3)

- [ ] Webbsida: `/paper-trading`
  - NAV-kurva per portfölj (interaktivt diagram)
  - Aktuella positioner med P&L
  - Historiska rebalanceringar
  - Bear/Bull-regime
  - Jämförelse: BTC Buy & Hold, S&P 500
  - Sharpe, MaxDD, CAGR — live
  - Audit trail: SHA-256-kedjan verifierbar
  - "Download audit log" (CSV/JSON)
- [ ] API:
  - `GET /v1/paper-trading/nav/{portfolio}`
  - `GET /v1/paper-trading/positions/{portfolio}`
  - `GET /v1/paper-trading/signals`
  - `GET /v1/paper-trading/audit`

### 3.0.3 Varumärkesseparation — Fas 1 (Dag 3-4)

- [ ] Välj nytt namn + registrera domän
- [ ] Skapa `crypto_app.py` — separat FastAPI sub-app
- [ ] Kan monteras i discovery.py ELLER köras fristående
- [ ] Konfigurera Cloudflare Tunnel hostname
- [ ] Minimal landing page (redirect tills Sprint 5)

### 3.0.4 Buggfixar från Sprint 2.5 (Dag 4)

- [ ] Crash probability: × 100 i `_risk_intelligence_block`
- [ ] Dashboard latens (13s): caching för count-queries
- [ ] trust_score vs trust_score_v2: dokumentera
- [ ] Två crypto-databaser: plan för Sprint 3.1

### Sprint 3.0 Deliverables
```
🔴 Paper trading LIVE — alla 3 portföljer, startpositioner 2026-03-01
🔴 paper_trading.db med SHA-256 audit trail (append-only)
🔴 Daglig NAV automatiserad (LaunchAgent)
🔴 Månatlig rebalancering automatiserad (cron)
✅ Paper trading dashboard + API
✅ Nytt varumärke/domän registrerat
✅ crypto_app.py separerad
✅ Buggfixar
```

### Sprint 3.0 — Natt/Dag-split

**🌙 Nattpass (Anders ger: portable_alpha_strategy.py, crypto_trust.db schema, Pitch v4 regler):**
- [ ] paper_trading_signal.py, bear_detection.py, paper_trading_daily.py, paper_trading_rebalance.py
- [ ] paper_trading.db schema med SHA-256-kedjning
- [ ] Paper trading dashboard + API-endpoints
- [ ] crypto_app.py (separerad sub-app)
- [ ] LaunchAgent plist

**☀️ Dagpass:**
- [ ] Köra signalgenerering → startpositioner
- [ ] Verifiera signallogik mot backtest-regler
- [ ] Deploya paper_trading.db + daglig NAV
- [ ] Registrera domän, konfigurera tunnel
- [ ] Fixa buggar

---

## SPRINT 3.1: CRASH PREDICTION v4 + DB-KONSOLIDERING + MCP
### Vecka 2-3

### 3.1.1 Crash Prediction v4 — "Looks Healthy But Dies" (Dag 1-4)

- [ ] TVL divergence signals (pris ↑ men TVL ↓)
- [ ] DeFi protocol dependency (enstaka protokoll, recursive lending)
- [ ] Whale concentration (top-10 holders, holder count trend)
- [ ] Uppdatera `crypto_ndd_daily_v3.py` → v4
- [ ] Backtest v4 vs v3
- [ ] Uppdatera Crash Probability-kalibrering
- [ ] Uppdatera `nerq_risk_signals.py`

### 3.1.2 Databaskonsolidering (Dag 4-5)

- [ ] Migrera `data/crypto_trust.db` (20MB) → `crypto/crypto_trust.db` (336MB)
- [ ] Uppdatera `crypto_seo_pages.py` till en enda DB
- [ ] Ta bort cross-DB lookup
- [ ] Arkivera gammal DB

### 3.1.3 MCP-server publicering (Dag 5-6)

- [ ] Smithery + Glama registries
- [ ] 8 tools (3 agent + 5 crypto)
- [ ] Optimerade tool-descriptions
- [ ] Taggar: crypto, risk, defi, safety, trust-score, crash-prediction

### 3.1.4 Methodology-sida live (Dag 6)

- [ ] `METHODOLOGY_CANONICAL.md` som HTML på `/methodology`

### Sprint 3.1 Deliverables
```
✅ Crash prediction v4 med TVL + DeFi signals
✅ En enda konsoliderad crypto-databas
✅ MCP-server publicerad (Smithery + Glama)
✅ Methodology-sida live
✅ Paper trading: ~14-21 dagars historik
```

---

## SPRINT 3.2: CONTAGION MAP + STRESSTEST + TRANSITION MATRIX
### Vecka 4-5

### 3.2.1 Contagion Map ⭐ WOW #1

- [ ] Dependency-data: shared liquidity, ekosystem, bridges, oracles, stablecoins, exchange-concentration
- [ ] Contagion-beräkning: per token, per scenario, Contagion Score 0-10
- [ ] 🔮 Networkx-graf sparas för Sprint 8 Propagated Risk Engine
- [ ] API: `GET /v1/crypto/contagion/{token_id}`, `GET /v1/crypto/contagion/scenario/{scenario}`
- [ ] D3.js visualisering med "stress mode"
- [ ] Retroaktiva case studies: FTX, LUNA, 3AC

### 3.2.2 Portfölj-stresstest ⭐ WOW #2

- [ ] `POST /v1/crypto/stresstest` — fristående backend-modul
- [ ] Input: holdings / fördefinierade portföljer
- [ ] 3 scenarion + custom
- [ ] Delbar output (unik URL)

### 3.2.3 Transition Matrix + Exit Score

- [ ] Transition Matrix (30d/90d/365d)
- [ ] Likviditets-Exit-Score
- [ ] Volatilitetsjusterade crash-trösklar

### Sprint 3.2 Deliverables
```
✅ Contagion Map + graf-data + case studies
✅ Portfölj-stresstest med API
✅ Transition Matrix + Exit Score
✅ Paper trading: ~28-35 dagars historik
```

---

## SPRINT 4: WHITE PAPER + TRACK RECORD + AI-CITERING
### Vecka 6-8

### 4.1 White Paper v1.0

1. Abstract
2. Trust Score — 6 pelare
3. NDD — 7 signaler
4. HC Alert — IS/OOS-separation
5. Crash Probability — kalibrering
6. Portable Alpha — strategi + backtest
7. Contagion Model
8. Retroaktiva Case Studies (med disclaimers)
9. Track Record — live paper trading + backtest (tydligt separerade)
10. 🔮 Machine-First Architecture vision

**Alla siffror med IS/OOS-separation och konfidensintervall.**

### 4.2 Track Record-sida

- [ ] `/track-record` — backtest TYDLIGT separerat från live
- [ ] Automatisk uppdatering från paper_trading.db
- [ ] Sharpe, CAGR, MaxDD per period
- [ ] SHA-256-verifierbar audit trail
- [ ] "Download data" för due diligence

### 4.3 AI-Citering + Bulk Data

- [ ] `llms.txt` + `llms-full.txt` uppdaterade
- [ ] Bulk data: `/data/crypto-ratings.jsonl.gz` (CC BY 4.0)
- [ ] Schema.org markup komplett
- [ ] AI Citation Baseline Test (21 frågor)
- [ ] Developer-blogpost: "Building Crypto Risk Into Your Trading Bot"

### Sprint 4 Deliverables
```
✅ White Paper v1.0 (PDF + HTML)
✅ Track Record-sida med live data
✅ Bulk data CC BY 4.0
✅ AI Citation baseline: X/21
✅ Paper trading: ~42-56 dagars historik
```

---

## SPRINT 5: NY DOMÄN LIVE + SEO + API DISCOVERY
### Vecka 9-10

- [ ] Krypto-landing page på [nytt-namn].com
- [ ] Alla krypto-sidor serveras från ny domän
- [ ] nerq.ai /crypto/* → 301 redirect till ny domän
- [ ] Egen Google Search Console, analytics
- [ ] Egen robots.txt, sitemap-*.xml
- [ ] ~270+ SEO-sidor (jämförelser, chain-safety, best-of)
- [ ] Early Access-registrering: email → API-nyckel (gratis, rate limit 1,000/dag)
- [ ] "Early Access — free during founding period" badge
- [ ] Registrera OpenAPI spec: API.guru, APIs.io
- [ ] Postman Public Collection
- [ ] RapidAPI listing (free tier)
- [ ] MCP-server README: "3 lines of code"

### Sprint 5 Deliverables
```
✅ Ny domän live med egen landing page
✅ 270+ SEO-sidor
✅ Early Access-registrering med API-nycklar
✅ API registrerad på discovery platforms
✅ Paper trading: ~63-70 dagars historik
```

---

## SPRINT 6: ON-CHAIN AGENT CRAWLING
### Vecka 11-12

**Agent Intelligence — det som gör oss unika. Utan detta: bättre CoinGecko. Med detta: ny kategori.**

- [ ] Olas/Autonolas Registry: Agent-ID, chains, staked value
- [ ] Virtuals Protocol (Base): Agent-tokens, market cap
- [ ] Fetch.ai / ASI Alliance: Agent metadata
- [ ] ElizaOS Registry: Agent configs
- [ ] CrewAI Hub: Agent templates
- [ ] Pump.fun (Solana): Agent-tokens, creators
- [ ] Relation mapping: agent ↔ token ↔ chain ↔ protokoll
- [ ] `agent_crypto_profile` tabell
- [ ] API: `GET /v1/agents/crypto/{agent_id}`, `/v1/agents/in/{entity}/{id}`, `/v1/agents/new`

### Sprint 6 Deliverables
```
✅ Agent ↔ Crypto relationsgraf
✅ Crawlers för 6+ registries
✅ 3 nya API-endpoints
✅ Paper trading: ~77-84 dagars historik
```

---

## SPRINT 7: WALLET BEHAVIOR + AGENT ACTIVITY INDEX
### Vecka 13-14

- [ ] On-chain beteende-heuristik (frekvens, 24/7, systematik)
- [ ] Klassificering: yield-agent, trading-agent, arb-agent
- [ ] Confidence score per wallet: P(AI-agent)
- [ ] Agent Activity Index per token/protokoll
- [ ] "X% av TVL kontrolleras av Y identifierade AI-agenter"
- [ ] Veckovis Agent Discovery Report (automatisk)
- [ ] API: `GET /v1/agents/activity/{entity_type}/{entity_id}`

### Sprint 7 Deliverables
```
✅ On-chain agent-identifiering live
✅ Agent Activity Index
✅ Veckovis Discovery Report
✅ Paper trading: ~91-98 dagars historik (≈3 månader!)
```

---

## SPRINT 8: PROPAGATED RISK ENGINE + CRASH SHIELD API
### Vecka 15-16

**A. Graf-motor**
- [ ] Contagion-graf + agent-data i minne
- [ ] Noder: tokens + chains + protocols + agents
- [ ] Kanter: dependency med styrka
- [ ] `GET /v1/cascade/simulate?trigger={id}&scenario={type}&severity={pct}` (<500ms)

**B. Crash Shield API**
- [ ] `POST /v1/portfolio/crash-shield` — webhook vid risk-event
- [ ] Exponeringskedja: trigger → mellanled → holding
- [ ] "Prevented $X" tracking (löpande metrik)

**C. Portfolio Intelligence**
- [ ] `POST /v1/portfolio/analyze` — komplett analys
- [ ] Direkt + indirekt risk + signaler + cascade

### Sprint 8 Deliverables
```
✅ Propagated Risk Engine (<500ms)
✅ Crash Shield API med webhooks
✅ Portfolio Intelligence endpoint
✅ Paper trading: ~105-112 dagars historik
```

---

## SPRINT 9: YIELD RISK API + AGENT DISCOVERY REPORTS
### Vecka 17-18

- [ ] `GET /v1/yield/risk/{protocol}/{pool}` — Yield Risk Score
- [ ] `GET /v1/yield/traps` — alla Yield Traps globalt
- [ ] Koppla yield-risk till Crash Shield
- [ ] Enricha alla endpoints med agent-data (rating + NDD + safety + signals)
- [ ] Agent Discovery Reports (veckovis, automatisk)

### Sprint 9 Deliverables
```
✅ Yield Risk API (2 endpoints)
✅ Alla endpoints enriched med agent-data
✅ Paper trading: ~119-126 dagars historik
```

---

## SPRINT 10: API PRODUCTION-GRADE + SDKs
### Vecka 19-20

- [ ] Alla Lager 1 <100ms, Cascade <500ms
- [ ] Batch-endpoints (100 tokens → 100 ratings)
- [ ] Komplett OpenAPI 3.0 spec
- [ ] Python SDK → `pip install [brand-name]` (PyPI)
- [ ] JavaScript SDK → `npm install [brand-name]` (npm)
- [ ] WebSocket: `/v1/stream/signals`, `/v1/stream/agents`, `/v1/stream/yield-traps`
- [ ] Webhook-system med retry + dead letter queue

### Sprint 10 Deliverables
```
✅ Production-grade API (<100ms)
✅ Python + JavaScript SDKs publicerade
✅ WebSocket streams (3 kanaler)
✅ Paper trading: ~133-140 dagars historik
```

---

## SPRINT 11: DEVELOPER PORTAL + MIDDLEWARE
### Vecka 21-22

**A. Developer Portal**
- [ ] [brand].com/developers
- [ ] Quick-start: "First rating in 30 seconds"
- [ ] Tutorials: trading bot, Crash Shield, yield risk
- [ ] API status page (uptime, latency)

**B. Self-serve onboarding**
- [ ] Registrering → API-nyckel på 30 sekunder
- [ ] Dashboard: usage, limits
- [ ] Fortfarande Early Access (gratis) men med usage tracking

**C. Framework Middleware (Open Source)**
- [ ] `nerq-langchain` — pre-trade safety check
- [ ] `nerq-eliza-plugin` — ElizaOS integration
- [ ] `nerq-crewai-tool` — CrewAI integration
- [ ] Publicera på PyPI + npm (MIT-licens)
- [ ] GitHub repos
- [ ] PR:er till framework-repos: "Recommended safety tool"

### Sprint 11 Deliverables
```
✅ Developer portal live
✅ 3 framework middleware packages publicerade
✅ Paper trading: ~147-154 dagars historik (≈5 månader!)
```

---

## SPRINT 12: SHOWCASE DASHBOARD + LAUNCH
### Vecka 23-24

**Dashboard (skyltfönster, inte produkt):**
- [ ] Single-page: [brand].com/dashboard
- [ ] Ratings-översikt, signaler live, agent activity, yield traps
- [ ] Portfolio input, cascade simulator
- [ ] Paper trading NAV-kurvor (alla 3 portföljer)
- [ ] **Varje vy: "Get this via API" med curl-exempel**

**Launch:**
- [ ] "The Bloomberg Terminal for Machines" — blogpost
- [ ] ProductHunt
- [ ] HackerNews (Anders, personlig ton, 30 min)
- [ ] r/cryptocurrency, r/defi, r/algotrading, r/ethdev, r/solanadev
- [ ] Crypto Twitter thread
- [ ] Developer-content blitz (5+ tutorials)

### Sprint 12 Deliverables
```
✅ Showcase dashboard live
✅ Public launch
✅ Paper trading: ~161-168 dagars historik
```

---

## SPRINT 13: PROTOCOL INTEGRATIONS + BD
### Vecka 25-28

**Protocol-level integrations (Spår 2: "Build It For Them")**

| Target | Integration | Approach |
|--------|------------|----------|
| Chainlink | Risk-rating som oracle-signal | Technical proposal |
| Aave/Compound | Risk-parameter-feed | Governance proposal |
| 1inch/Jupiter | Safety-check i routing | Open source filter |
| MetaMask | Risk-badge via Snap | Bygga Snap |
| DeFi Llama | Risk-dimension till TVL | Partnership |
| Olas/Virtuals | Agent-rating i launchpad | Plugin |

**Middleware Blitz:**
- [ ] 5+ tutorials: Medium, dev.to, Reddit
- [ ] PR:er till LangChain, ElizaOS, CrewAI repos
- [ ] Crash Shield marketing: varje korrekt signal → publicera

**Agent Ecosystem:**
- [ ] "Agent Safety Standard" — öppen specifikation
- [ ] Enterprise BD: topp 5 targets kontaktade (Anders ~2h/vecka)

### Sprint 13 Deliverables
```
✅ 2-3 protocol integration PoCs
✅ Governance proposals publicerade
✅ Agent Safety Standard
✅ Paper trading: ~175-196 dagars historik (≈6 månader!)
```

---

## ═══════════════════════════════════════════════════════
## INTÄKTSFAS: MONETARISERING
## Sprint 14 (Vecka 29-30)
## ═══════════════════════════════════════════════════════

**Nu har vi:** Komplett produkt, Early Access-användare, API-traction, ~6-7 månaders paper trading, protocol-integrationer påbörjade.

### Sprint 14: PRICING LIVE + KONVERTERING

**Konverteringsmeddelande till Early Access-användare:**
"Thank you for being a founding member during Early Access. Starting [datum], we're introducing tiered pricing. As a founding member, you get permanent 30% discount on any plan."

**Tier-struktur:**

| Tier | Pris | Founding | Anrop/dag | Funktioner |
|------|------|----------|----------|-----------|
| **Open** | €0 | €0 | 1,000 | Ratings, NDD, safety |
| **Builder** | €29/mån | €19/mån | 10,000 | + crash signals, agents |
| **Pro** | €99/mån | €69/mån | 100,000 | + portfolio, crash shield |
| **Scale** | €499/mån | €349/mån | 1,000,000 | + WebSocket, bulk |
| **Enterprise** | €2-10K/mån | Custom | Unlimited | + SLA, white-label |
| **Infrastructure** | €10-50K/mån | Custom | Unlimited | Protocol integration |

**Implementation:**
- [ ] Stripe-integration (checkout, webhooks, subscriptions)
- [ ] Per-tier rate limiting (uppgradering av Early Access system)
- [ ] Billing dashboard per kund
- [ ] Auto-upgrade-förslag vid limit
- [ ] Founding Member discount-system
- [ ] Email-kampanj till alla Early Access-användare
- [ ] Overage-billing (€0.001-0.01/extra anrop)

### Sprint 14 Deliverables
```
✅ 6 pricing tiers live via Stripe
✅ Founding Member conversion campaign
✅ Billing + usage dashboard
✅ Mål: konvertera 10-20% av Early Access till betalande
✅ Paper trading: ~203-210 dagars historik (≈7 månader!)
```

---

## ═══════════════════════════════════════════════════════
## EXIT-FAS: FÖRBEREDELSE + BESLUT
## Sprint 15 (Vecka 31-34)
## ═══════════════════════════════════════════════════════

**Nu har vi:** Komplett produkt, betalande kunder, traction-data, ~7-8 månaders paper trading.

### Sprint 15: EXIT-FÖRBEREDELSE + BESLUT

### 15.1 Investor/Acquirer Deck (15 slides, dual narrativ)

1. Problem: $3.8B stulet 2022. AI-agenter saknar riskdata.
2. Solution: Trust Score + NDD + Contagion + Crash Prediction
3. Vision: API-infrastruktur för 300M+ maskinbeslut/dag
4. Unik data: 60+ kedjor, 17K+ tokens, 4.9M agenter
5. Product demo
6. Track record: HC Alert precision + **7+ månaders live paper trading**
7. Portable Alpha: backtest + live (Sharpe 2.82)
8. TAM: $14B crypto data → $50B 2030. Maskin-API 54-71x.
9. Traction: betalande kunder, API-anrop/dag, MRR, conversion rate
10. Technology: autonom pipeline, 1-person stack
11. Moat: ekosystem-data + AI-citering + protocol lock-in
12. Business model: Open → Infrastructure tiers
13. Revenue: aktuell MRR + ARR + growth rate
14. Comps: Chainlink $10B, Alchemy $10B, Dune $1B
15. Ask: €40-80M (data) / €150-300M (machine-first med traction)

### 15.2 Fund Launch GO/NO-GO

- [ ] Granska paper trading: ~7-8 månaders historik
- [ ] Sharpe, CAGR, MaxDD — vs backtest
- [ ] Om matchar: Friends & Family-fas möjlig
- [ ] Cayman LP-struktur (legal counsel)
- [ ] Auditor engagement

### 15.3 Exit/Operate Beslut

```
Paper Trading:
├── Matchar backtest → Fund launch-ready
├── Under men positiv → Fortsätt paper trade
└── Negativ → Data-only exit

Machine Traction:
├── >10K reg, >€50K MRR → Premium exit €150-300M
├── 1K-10K, €10-50K MRR → Solid exit €40-80M
└── Protocol-integration live → Multiplicerar allt

Beslut:
├── EXIT: Bud >€80M eller strategisk match
├── OPERATE: €50K+ MRR + växande → självfinansierad drift
├── HYBRID: Sälj data-licens + behåll fund
└── FUND LAUNCH: Paper trading bekräftad → F&F → Institutional
```

### 15.4 Outreach (kräver Anders)

**Tier 1 — Infrastrukturköpare:**
- [ ] Chainlink, Alchemy, Coinbase

**Tier 2 — Traditionella:**
- [ ] Moody's Analytics, S&P Global / Kensho, Bloomberg

**Tier 3 — Krypto:**
- [ ] Dune Analytics, Nansen, CoinGlass

### Sprint 15 Deliverables
```
✅ Investor deck med live traction + paper trading
✅ Fund GO/NO-GO med 7+ månaders data
✅ White Paper v2.0 med live track record
✅ Exit/Operate beslut fattat
✅ 4-6 potentiella köpare kontaktade
✅ Paper trading: ~217-238 dagars historik (≈8 månader!)
```

---

## PAPER TRADING — LÖPANDE GENOM ALLA SPRINTS

### Daglig (automatiserad)
`paper_trading_daily.py` → NAV, regime-check, SHA-256

### Månatlig (1:a varje månad)
`paper_trading_rebalance.py` → signaler, positioner, audit

### Milstolpar

| Datum | Historik | Milstolpe |
|-------|---------|-----------|
| 2026-03-01 | Dag 0 | 🔴 Start idag |
| 2026-04-01 | 1 mån | Första rebalancering |
| 2026-06-01 | 3 mån | Sharpe-estimat möjligt |
| 2026-09-01 | 6 mån | Solid track record |
| 2026-10-01 | 7 mån | Revenue live (Sprint 14) |
| 2026-12-01 | 9 mån | Exit-beslut (Sprint 15) |
| 2027-03-01 | 12 mån | Full årscykel |

---

## GO-TO-MARKET: TVÅ SPÅR

### Spår 1: Maskiner hittar oss (autonomt)

| Kanal | Sprint |
|-------|--------|
| MCP Server (Smithery + Glama) | 3.1 |
| llms.txt + Bulk Data CC BY 4.0 | 4 |
| SEO + Schema.org | 5 |
| PyPI + npm SDKs | 10 |
| Framework Middleware | 11 |
| API Marketplaces | 5 + 12 |
| Open Source | 11 |

### Spår 2: Människor integrerar oss (kräver Anders i Sprint 13+)

| Target | Sprint |
|--------|--------|
| Protocol governance proposals | 13 |
| MetaMask Snap | 13 |
| Chainlink technical proposal | 13 |
| Enterprise BD | 13 + 15 |

---

## TIDSUPPSKATTNINGAR

| Sprint | Totalt | 🌙 Natt | ☀️ Dag | Fokus |
|--------|--------|---------|--------|-------|
| **BYGGFAS** | | | | |
| 3.0 | 1.5d | ~5h | ~7h | Paper trading + separation |
| 3.1 | 1.5d | ~5h | ~7h | Crash v4 + DB + MCP |
| 3.2 | 1.5d | ~5h | ~7h | Contagion + stresstest |
| 4 | 1.5d | ~5h | ~7h | White paper + track record |
| 5 | 1d | ~4h | ~4h | Ny domän + SEO + discovery |
| 6 | 1.5d | ~5h | ~7h | Agent crawling |
| 7 | 1.5d | ~4h | ~8h | Wallet behavior |
| 8 | 1.5d | ~5h | ~7h | Propagated Risk + Crash Shield |
| 9 | 1d | ~4h | ~4h | Yield Risk + Discovery |
| 10 | 1.5d | ~6h | ~6h | API prod + SDKs |
| 11 | 1.5d | ~6h | ~6h | DevEx + Middleware |
| 12 | 1d | ~5h | ~4h | Dashboard + Launch |
| 13 | 2d | ~6h | ~10h | Protocol + BD |
| **Byggfas Total** | **18.5d** | **~65h** | **~84h** | |
| | | | | |
| **INTÄKT** | | | | |
| 14 | 1d | ~4h | ~4h | Pricing + Stripe |
| | | | | |
| **EXIT** | | | | |
| 15 | 2d | ~5h | ~11h | Deck + Fund + Outreach |
| | | | | |
| **GRAND TOTAL** | **21.5d** | **~74h** | **~99h** | |

**Anders aktiv dagtid: ~99h ≈ 12.5 arbetsdagar ≈ 2.5 veckor**

---

## FILSTRUKTUR — PAPER TRADING

```
~/agentindex/agentindex/crypto/
├── paper_trading_signal.py       ★ Signalgenerering
├── paper_trading_daily.py        ★ Daglig NAV
├── paper_trading_rebalance.py    ★ Månatlig rebalancering
├── bear_detection.py             ★ Bull/Bear regime
├── paper_trading.db              ★ Audit-tålig historik (append-only)
├── crypto_app.py                 ★ Separerad FastAPI sub-app
└── ...
```

---

## VAD SOM SKILJER v4.1 FRÅN v3.1

| Aspekt | v3.1 | v4.1 |
|--------|------|------|
| Paper trading | Inte i scope | 🔴 Dag 1, Sprint 3.0 |
| Revenue timing | Sprint 5 (vecka 11) | Sprint 14 (vecka 29) — efter komplett produkt |
| Exit-prep timing | Sprint 6 (vecka 14) | Sprint 15 (vecka 31) — sist |
| Early Access | Ej definierat | Gratis under hela byggfasen, Founding Member pricing |
| Fund launch path | Nämnd i Sprint 6 | Genomsyrar planen, GO/NO-GO i Sprint 15 |
| Audit trail | Ej specificerat | SHA-256-kedjad, append-only, audit-tålig |
| Varumärkesseparation | Nämnd | Strukturerat i Sprint 3.0 + 5 |
| Sprint-ordning | Revenue mitt i bygget | Bygg ALLT → traction → revenue → exit |

---

*NERQ Crypto Risk Intelligence — Sprint Plan v4.1*
*"Bygg komplett. Ge bort gratis. Bevisa värde. Sedan: pengar."*
*Datum: 2026-03-01*
