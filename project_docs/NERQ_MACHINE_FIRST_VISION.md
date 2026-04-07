# NERQ — THE MACHINE TERMINAL
## API:et är Terminalen. Maskinerna är Kunderna.
### Alternativ Strategisk Vision — Februari 2026

---

## DEN CENTRALA INSIKTEN

Bloomberg byggde en terminal för människor i finansindustrin och hittade den produkt de inte kunde vara utan. Sedan dess har varje fintech-bolag försökt kopiera den modellen: bygg ett snyggt gränssnitt, sälj det till människor vid skärmar.

Men kryptomarknadens framtid sitter inte vid skärmar.

Framtidens största konsumenter av finansiell kryptodata är **maskiner** — AI-agenter, smarta kontrakt, oracles, trading bots, DeFi-protokoll, wallet-applikationer, aggregatorer. De fattar beslut 24/7, de gör det i millisekunder, och de behöver riskdata vid varje beslut.

En Bloomberg-terminal är ett gränssnitt för mänskliga ögon.
Ett API är ett gränssnitt för maskiner.

**Nerq bygger inte en terminal. Nerq bygger terminalen för maskiner — det API som autonoma system i kryptoekonomin inte kan fungera utan.**

---

## VARFÖR MASKINER ÄR DEN OSSERVADE MARKNADEN

### Siffrorna talar

Från vår egen analys av kryptomarknaden:

| Konsument | Queries/dag (nu, lågpunkt) | Queries/dag (bull peak 2028) |
|-----------|---------------------------|------------------------------|
| Människor (sök + webb) | 5.6M | 35M |
| Maskiner (API-anrop) | ~300M | ~2.5B |
| **Ratio maskin:människa** | **54:1** | **71:1** |

Maskiner konsumerar redan 54 gånger mer kryptodata än människor. Vid peak blir det 71 gånger mer. Och det är idag — innan autonoma AI-agenter verkligen har exploderat.

### Vem är maskinerna?

| Maskin-typ | Vad den behöver | Anrop/dag nu | Anrop/dag peak |
|------------|----------------|-------------|----------------|
| **DeFi-protokoll** (Aave, Compound) | Collateral-risk vid varje låneposition | 10-50M | 50-200M |
| **Wallets** (MetaMask 30M+, Phantom 5M+) | Risk-badge per token vid varje vy | 50-200M | 200-800M |
| **AI trading-agenter** | Validera motpart/token pre-trade | 5-50M | 100-500M |
| **Trading bots** | Filtrera scam-tokens | 20-100M | 100-500M |
| **Aggregatorer** (1inch, Jupiter) | Filtrera honeypots vid routing | 10-50M | 50-200M |
| **Oracles** (Chainlink, Pyth) | Trust-signal i prisflöden | 10-50M | 50-200M |
| **Portfolio trackers** (Zapper, DeBank) | Risk per holding | 5-20M | 20-100M |
| **Compliance-verktyg** | MiCA/AML-rapportering | 1-5M | 5-20M |
| **Exchanges** | Listing-beslut, auto-screening | 1-5M | 5-20M |

### Vad som serveras idag — och vad som saknas

| Datatyp | Finns API idag? | Leverantör | Vad saknas |
|---------|-----------------|-----------|------------|
| Prisdata | ✅ | CoinGecko, CMC, Kaiko | Commodifierad, alla har den |
| TVL | ✅ | DeFi Llama | Finns, gratis |
| Honeypot-check | ✅ | GoPlus | Binärt (ja/nej), ingen djup |
| Wallet labels | ✅ | Nansen, Arkham | Dyrt, fokus människor inte agenter |
| **Holistisk kreditrating** | ❌ | Ingen | **Nerq** |
| **Distance to Distress** | ❌ | Ingen | **Nerq** |
| **Kraschprediktion** | ❌ | Ingen | **Nerq** |
| **Cascade-propagering** | ❌ | Ingen | **Nerq** |
| **AI-agent-identifiering** | ❌ | Ingen | **Nerq** |
| **Agent ↔ token ↔ chain ↔ risk graf** | ❌ | Ingen | **Nerq** |
| **Yield Trap-detektion** | ❌ | Ingen | **Nerq** |
| **Portföljspecifik kraschvarning** | ❌ | Ingen | **Nerq** |

**Slutsats: Det som maskiner behöver mest — riskdata — är det som minst existerar som API idag.**

---

## PRODUKTEN: API-FIRST, ALLT ANNAT ÄR SEKUNDÄRT

### Arkitekturprincip

```
PRIMÄR PRODUKT:        Nerq Risk API
                       ↓
KONSUMENTER:           Maskiner (agenter, protokoll, wallets, bots, oracles)
                       ↓
SEKUNDÄRT:             Dashboard (showcase för människor)
                       Webb/SEO (trafik + AI-citering)
                       MCP Server (LLM-integration)
```

Dashboarden är inte produkten. Dashboarden är ett **skyltfönster** — den visar vad API:et kan göra, den driver trafik och trovärdighet, men den är inte det som genererar revenue i skala.

### Kärnprodukten: Nerq Risk API

#### Endpoint-struktur

**Lager 1: Grunddata (tillgänglig för alla, inklusive gratis)**

```
GET /v1/rating/{entity_type}/{id}
  → Credit Rating (Aaa-D), score, breakdown, confidence

GET /v1/ndd/{entity_type}/{id}
  → Distance to Distress (0-5), trend (7d/30d/90d), signals

GET /v1/safety/{token_address}
  → Snabb säkerhetscheck: honeypot, mint, owner, LP, deployer
  → Response <100ms — optimerat för pre-trade validation

GET /v1/ratings
  → Bulk ratings, filtrerbar på chain/type/rating/NDD

GET /v1/compare/{id1}/{id2}
  → Jämförelse mellan två entiteter
```

**Lager 2: Intelligence (betalande kunder)**

```
GET /v1/crash/signals
  → Aktiva kraschsignaler, alla 5 typer
  → Severity, confidence, historisk precision

GET /v1/crash/signal/{signal_id}
  → Detaljerad signal med exponeringskedja

GET /v1/cascade/simulate
  ?trigger={entity_id}&scenario={type}&severity={pct}
  → Propagerad risk genom hela grafen
  → Alla påverkade entiteter med exponeringsgrad
  → <500ms response (graf i minne)

GET /v1/agents/crypto/{agent_id}
  → AI-agentens krypto-profil: chains, tokens, protokoll, volym, score

GET /v1/agents/in/{entity_type}/{entity_id}
  → Alla AI-agenter som opererar med denna token/protokoll/chain
  → Aggregerad agent-risk per entitet

GET /v1/agents/new
  ?period=7d&chain=base&min_tvl=1000000&audited=true
  → Nya AI-agenter, filtrerbar

GET /v1/yield/risk/{protocol}/{pool}
  → Yield Risk Score, Yield Trap-flaggor, sustainability-analys

GET /v1/yield/traps
  → Alla aktiva Yield Traps globalt
```

**Lager 3: Portfolio Intelligence (premium)**

```
POST /v1/portfolio/analyze
  Body: {wallet_address} eller {positions: [...]}
  → Komplett portföljanalys:
    - Direkt risk per position
    - Indirekt exponering via agenter
    - Yield-risk (alla 3 nivåer)
    - Aktiva kraschsignaler som berör portföljen
    - Cascade-simulering: "vad händer vid scenario X"
    - Aggregate portfolio score

POST /v1/portfolio/crash-shield
  Body: {wallet_address, alert_config}
  → Aktivera Personal Crash Shield
  → Webhook-push vid risk-event som berör portföljen
  → Exponeringskedja: trigger → mellanled → holding
  → Severity + historisk precision per signaltyp

GET /v1/portfolio/{wallet}/yield-risk
  → Komplett yield-riskanalys:
    - Nivå 1: direkta yield-positioner
    - Nivå 2: indirekt via token-beroenden
    - Nivå 3: dold exponering via AI-agenter i samma pooler
    - Yield Risk Score per position
    - Yield Trap-flaggor
```

**Lager 4: Realtids-feeds (enterprise)**

```
WebSocket /v1/stream/signals
  → Realtidsström av alla kraschsignaler
  → Filtrerbar per chain/severity/type

WebSocket /v1/stream/agents
  → Realtidsström av agent-aktivitet
  → Nya agenter, volymförändringar, anomalier

POST /v1/webhooks/subscribe
  Body: {events: [...], filters: {...}, callback_url: "..."}
  → Push-notifikationer vid definierade events

GET /v1/bulk/ratings.jsonl.gz
  → Daglig bulk-export av alla ratings
  → För offline-analys, modellträning
```

#### Designprinciper för maskin-konsumtion

| Princip | Implementation |
|---------|---------------|
| **Latency** | <100ms för safety-check, <500ms för cascade | 
| **Uptime** | 99.9% SLA (Cloudflare + redundant backend) |
| **Format** | JSON, strikt schema, versionerat (v1/v2) |
| **Idempotent** | Samma fråga = samma svar (cachebar) |
| **Batch-stöd** | POST med array av entities → batch-response |
| **Streaming** | WebSocket för realtidsdata |
| **Self-describing** | OpenAPI 3.0 spec, maskinläsbar |
| **Auth** | API-nyckel i header, enkel onboarding |

#### Varför varje maskin-typ behöver Nerq

**DeFi-protokoll (Aave, Compound, etc.):**
```
Scenario: Ny token föreslås som collateral
Idag: Manuell governance-vote, veckor av diskussion
Med Nerq: GET /v1/rating/token/0x... → "Rating: Ba2, NDD: 2.1,
  Agent concentration: 34% (3 agents, avg score 5.2),
  Yield trap flags: RECURSIVE_LENDING"
→ Automatiserat collateral-beslut med risk-data
```

**AI trading-agent:**
```
Scenario: Agent ska swappa 100K USDC → Token X
Idag: Kollar pris, kanske honeypot-check (GoPlus)
Med Nerq: GET /v1/safety/0x... → 12ms response
  "Rating: Caa1, NDD: 0.8, DISTRESS WARNING,
  Crash signal: Death Spiral (confidence 87%),
  Deployer: 3 previous rugs, Agent activity:
  2 agents pulling liquidity last 4h"
→ Agent avbryter trade. Sparade 100K.
```

**Wallet (MetaMask, Phantom):**
```
Scenario: Användare ska interagera med DeFi-protokoll
Idag: Ingen risk-information visas
Med Nerq: GET /v1/rating/protocol/aave-v3-arbitrum
  → Risk badge: "A2 — Low Risk. 12 AI agents active,
  all audited. No active crash signals."
  Eller: "Caa1 — High Risk. Yield Trap detected.
  Unaudited AI agent controls 22% of pool."
→ Användare ser risk INNAN de signerar transaktionen
```

**Oracle (Chainlink, Pyth):**
```
Scenario: Prisorakel levererar data för token
Idag: Pris levereras utan riskkontext
Med Nerq: GET /v1/ndd/token/{id} → NDD som tilläggssignal
  → Protokoll som konsumerar oraklet kan vikta pris
  mot risk: "Priset säger $1.00 men NDD säger 0.3 —
  denna stablecoin är i fara"
→ Trust-signal som komplement till prisdata
```

**Aggregator (1inch, Jupiter):**
```
Scenario: Routa swap genom bästa likviditetsväg
Idag: Optimerar pris och slippage, ignorerar risk
Med Nerq: Batch GET /v1/safety/ för alla pooler i route
  → Filtrera bort pools med Yield Trap, high agent
  concentration, eller active crash signals
→ Säkrare routing, premium feature
```

---

## REVENUE-MODELL: PAY PER DECISION

### Grundprincip

Bloomberg tar $25 000/år per terminal = per människa.
Nerq tar en bråkdel per API-anrop = per maskinbeslut.

Men: en människa fattar kanske 50 beslut per dag.
En maskin fattar 50 000 beslut per dag.

$25 000 / 365 dagar / 50 beslut = $1.37 per mänskligt beslut
€0.001 per maskinbeslut × 50 000/dag = €50/dag = €18 250/år per maskin

**Samma intäkt per kund. Oändligt fler kunder.**

### Tier-struktur

| Tier | Pris | Anrop/dag | Latency SLA | Funktioner | Målgrupp |
|------|------|----------|-------------|-----------|----------|
| **Open** | €0 | 1 000 | Best effort | Lager 1 (ratings, NDD, safety) | Hobby-devs, AI-träning, SEO-trafik |
| **Builder** | €29/mån | 10 000 | <200ms | Lager 1 + 2 (crash signals, agents) | Indie-devs, små bots |
| **Pro** | €99/mån | 100 000 | <100ms | Lager 1-3 (portfolio, crash shield) | Trading-agenter, portfolio tools |
| **Scale** | €499/mån | 1 000 000 | <100ms | Alla lager + WebSocket streams | DeFi-protokoll, aggregatorer |
| **Enterprise** | €2K-10K/mån | Unlimited | <50ms + SLA | Alla + white-label + raw data + dedikerad | Exchanges, wallets, oracles |
| **Infrastructure** | €10K-50K/mån | Unlimited | <20ms + SLA | Direkt integration i protokoll/oracle | Chainlink, Aave, MetaMask |

### Overage-pricing

Utöver inkluderade anrop: €0.001-0.01 per anrop beroende på endpoint-komplexitet.

| Endpoint-typ | Pris per extra anrop |
|-------------|---------------------|
| Safety check (enkel) | €0.001 |
| Rating/NDD | €0.002 |
| Agent lookup | €0.003 |
| Cascade simulation | €0.01 |
| Portfolio analysis | €0.01 |

### Revenue-projektion: Machine-First

**Konservativ (lågpunkt → tidig återhämtning):**

| Tidpunkt | Open | Builder | Pro | Scale | Enterprise | Infra | MRR | ARR |
|----------|------|---------|-----|-------|-----------|-------|-----|-----|
| Månad 4 | 500 | 50 | 10 | 0 | 0 | 0 | €2.4K | €29K |
| Månad 7 | 2K | 200 | 50 | 5 | 2 | 0 | €15K | €177K |
| Månad 12 | 10K | 800 | 200 | 30 | 8 | 1 | €72K | €864K |
| Månad 18 | 30K | 3K | 800 | 100 | 25 | 3 | €262K | €3.1M |
| Månad 24 | 100K | 10K | 3K | 300 | 60 | 8 | €875K | €10.5M |

**Bull-scenario (2027-2028):**

| Tidpunkt | Open | Builder | Pro | Scale | Enterprise | Infra | MRR | ARR |
|----------|------|---------|-----|-------|-----------|-------|-----|-----|
| Månad 24 | 300K | 30K | 10K | 800 | 150 | 15 | €2.8M | €34M |
| Månad 36 | 500K | 50K | 25K | 2K | 300 | 30 | €7.5M | €90M |

**Plus overage-revenue vid peak:**
Om 1 000 Scale-kunder gör i snitt 2M anrop/dag (1M over limit):
1 000 × 1M × €0.002 = €2M/dag = €60M/månad overage

Overage-revenue kan vid peak överstiga subscription-revenue. Det är API-ekonomins kraft.

### Jämförelse med Terminal-modellen (dokument A)

| Metrik | Terminal-modell (dok A) | Machine-First (detta dok) |
|--------|------------------------|--------------------------|
| Primär produkt | Dashboard + API | API (dashboard = showcase) |
| Primär kund | Människor (traders, analytiker) | Maskiner (agenter, protokoll, wallets) |
| Pricing | Per användare/månad | Per anrop + subscription |
| Revenue vid lågpunkt | Låg (få människor bryr sig) | Medium (maskiner kör alltid) |
| Revenue vid bull peak | Hög (5-8x trafik) | Mycket hög (maskinvolym exploderar) |
| Skalbarhet | Linjär (fler användare) | Exponentiell (fler maskiner × fler beslut) |
| Churn-risk | Hög (människor slutar vid bear) | Låg (maskiner stängs inte av vid bear) |
| Build-kostnad dashboard | Hög (4 sprints, UX-design) | Låg (enkel showcase) |
| Build-kostnad API | Medium | Medium (samma endpoints) |
| Moat | UX + data | Data + nätverkseffekt (fler konsumenter → mer data) |

**Nyckelinsikt: Machine-first har lägre churn.** Människor slutar titta på kryptodashboards i bear markets. Maskiner stängs inte av. En DeFi-agent som kör yield-strategier behöver Nerq-data oavsett om BTC är $100K eller $30K. API-revenue är mer stabil över cykler.

---

## NÄTVERKSEFFEKTEN: VARFÖR API-FIRST VINNER

### Flywheel

```
Fler maskiner konsumerar API
  → Mer data om hur maskiner använder kryptomarknaden
  → Bättre agent-identifiering (vi ser vilka som querier oss)
  → Bättre riskmodeller (vi ser vad maskiner bryr sig om)
  → Bättre produkt
  → Fler maskiner konsumerar API
```

Varje API-konsument gör Nerq bättre. Varje query är en datapunkt. Om 10 000 AI-agenter kollar risk före varje trade, vet vi:
- Vilka tokens som är mest efterfrågade av agenter
- Vilka protokoll agenter undviker (och varför — vår risk data flaggade dem)
- Hur agenter reagerar på kraschsignaler
- Mönster i agent-beteende som förutspår marknadsrörelser

Denna meta-data är i sig en produkt. "Nerq Agent Activity Index" — en aggregerad signal baserad på vad 10 000 AI-agenter gör just nu. Det är alfa.

### Protocol-level integration = ultimat stickiness

Om Nerq-data integreras direkt i ett DeFi-protokolls smarta kontrakt (via oracle), kan det inte tas bort utan governance-vote. Det är stickier än någon dashboard.

Exempel:
```solidity
// Aave risk parameter (hypotetiskt)
function getCollateralFactor(address token) {
    uint256 nerqRating = INerqOracle(nerqOracle).getRating(token);
    if (nerqRating < 300) return 0; // Ingen collateral under Caa
    if (nerqRating < 500) return 5000; // 50% LTV för Ba
    return 7500; // 75% LTV för A och högre
}
```

När Nerq-rating är hårdkodad i smarta kontrakt som hanterar miljarder i TVL — det är en Bloomberg-terminal som inte kan stängas av.

---

## CRASH SHIELD SOM API-PRODUKT

### Varför Crash Shield är ännu kraftfullare i machine-first-modellen

I terminal-modellen (dokument A) är Crash Shield en feature i dashboarden — en människa ser varningen och agerar manuellt.

I machine-first-modellen är Crash Shield **automatiskt integrerad i varje maskins beslutsfattande**:

```
AI-agent vill göra trade
  → GET /v1/safety/{token} + /v1/crash/signals
  → Crash Shield: "Active Death Spiral signal on token's
     underlying protocol (confidence 91%). Your current
     exposure: 34% via 2 hops. Historical accuracy of
     this signal type: 99.2% (1190/1200)"
  → Agent avbryter trade automatiskt
  → Ingen människa behövde ingripa
```

**Varje API-anrop som innehåller en aktiv kraschvarning = bevis på värde.**

"Nerq Crash Shield prevented 847 automated trades worth $12.4M in the last 24 hours based on signals with 99.2% historical accuracy."

Det är den typen av metrik som säljer enterprise-kontrakt.

### Personal Crash Shield via API

Samma funktion som i dashboarden, men som API-endpoint:

```
POST /v1/portfolio/crash-shield
Body: {
  wallet: "0x...",
  alert_config: {
    min_severity: "MEDIUM",
    min_exposure_pct: 5,
    webhook_url: "https://my-agent.com/alerts",
    include_chain: true  // visa hela exponeringskedjan
  }
}

→ Webhook push vid risk-event:
{
  severity: "HIGH",
  signal: "death_spiral",
  signal_confidence: 0.91,
  signal_historical_accuracy: 0.992,
  trigger_entity: {type: "protocol", id: "terra-luna", name: "Terra"},
  your_exposure: {
    total_pct: 34.2,
    paths: [
      {
        holding: "UST", portfolio_pct: 12,
        hops: 0, exposure_type: "direct"
      },
      {
        holding: "AVAX", portfolio_pct: 22.2,
        hops: 2,
        path: "AVAX → Benqi (30% collateral in UST) → Terra",
        exposure_type: "indirect_via_protocol"
      }
    ]
  },
  recommended_action: "reduce_exposure",
  affected_yield_positions: [
    {
      protocol: "Benqi",
      pool: "AVAX-lending",
      current_apy: 8.2,
      yield_risk_score: 2.1,
      flags: ["RECURSIVE_LENDING", "DEPEG_DEPENDENT"]
    }
  ]
}
```

**En AI-agent som tar emot denna webhook kan automatiskt:**
1. Stoppa alla nya transaktioner mot berörda protokoll
2. Påbörja ordnad exit från riskfyllda positioner
3. Flytta till säkrare tillgångar
4. Rapportera till sin ägare

Allt utan mänsklig inblandning. Det är Crash Shield för maskiner.

---

## DEFI YIELD RISK SOM API-PRODUKT

### Yield Intelligence för maskiner

Yield-farming-agenter är en av de största konsumentgrupperna. De behöver:

```
GET /v1/yield/risk/{protocol}/{pool}
→ {
  yield_risk_score: 3.2,     // 1-10
  sustainability: 0.35,       // organic yield ratio
  concentration: 0.72,        // whale/agent concentration
  agent_dependency: 0.45,     // % of pool controlled by AI agents
  mechanism_risk: 0.68,       // recursive loops, depeg exposure
  protocol_rating: "Ba1",     // underlying protocol quality
  flags: ["YIELD_TRAP", "AGENT_CONCENTRATED", "EMISSIONS_DRIVEN"],
  agents_in_pool: [
    {id: "olas-agent-847", score: 7.2, tvl_pct: 12, audited: true},
    {id: "unknown-agent-3", score: 2.1, tvl_pct: 8, audited: false}
  ],
  crash_signals_affecting: [
    {signal: "market_fragility", severity: "LOW", confidence: 0.34}
  ]
}
```

**Use case:** En yield-farming-agent som optimerar avkastning kan nu:
1. Filtrera bort alla pooler med Yield Trap-flaggor
2. Vikta allokering baserat på yield_risk_score
3. Undvika pooler med hög agent-koncentration (risk för synkron exit)
4. Automatiskt rebalansera bort från pooler med aktiva kraschsignaler
5. Rapportera yield-risk till portfolio Crash Shield

### Yield Trap Alert Stream

```
WebSocket /v1/stream/yield-traps
→ Realtidsström av nya och eskalerande Yield Traps
→ Agent kan reagera inom sekunder efter att signal triggas
```

---

## DEN UNIKA DATAN: VARFÖR BARA NERQ KAN GÖRA DETTA

### Agent Intelligence — moaten som förstärker allt

I terminal-modellen (dokument A) är agent-datan ett lager ovanpå ratings. I machine-first-modellen är agent-datan **fundamental infrastruktur som genomsyrar varje endpoint**.

Varje API-response är rikare för att vi har agent-data:

| Endpoint | Utan agent-data | Med Nerqs agent-data |
|----------|----------------|---------------------|
| Rating | Score baserad på on-chain-metriker | + "34% av TVL kontrolleras av agenter med snitt-score 5.2" |
| Safety check | Honeypot ja/nej | + "Deployer är en känd agent-factory med 3 rug pulls" |
| NDD | Distance to Distress | + "5 agenter drar sig ur detta protokoll senaste 24h" |
| Crash signal | Signal baserad på pris/volume | + "12 AI-agenter har börjat flytta kapital — de vet något" |
| Yield risk | APY sustainability | + "60% av pool-volymen drivs av 3 agenter som kan exit synkront" |
| Cascade sim | Propagering genom tokens/protokoll | + "Agent C kontrollerar $40M över 3 protokoll — alla påverkas" |

**Utan agent-data är Nerq en bättre CoinGecko. Med agent-data är Nerq en ny kategori som ingen kan replikera utan att först bygga en databas av 4.9M agenter.**

### Vad vi ser som ingen annan ser

```
"Meta-signal": Nerqs egna API-kunder (AI-agenter) ger oss data

Agent A querier /v1/safety/ för Token X → 500 gånger senaste timmen
Agent B querier /v1/safety/ för Token X → 300 gånger
Agent C querier /v1/cascade/ med Token X som trigger → 50 gånger

SIGNAL: 3 agenter undersöker Token X intensivt.
→ Något håller på att hända.
→ Nerq publicerar: "Elevated agent attention on Token X"
→ Denna meta-signal blir i sig en produkt.
```

Vi vet inte bara vad som händer on-chain. Vi vet vad maskinerna **tänker** händer, för de frågar oss.

---

## SPRINTPLAN: MACHINE-FIRST

### Vad som ändras vs Terminal-planen (dokument A)

| Fas | Terminal-plan (dok A) | Machine-First (detta) |
|-----|----------------------|----------------------|
| Fas 0 (v1-12) | Identisk | Identisk — datagrunden |
| Fas 1 (v13-20) | Identisk | Identisk — agent intelligence |
| Fas 2 (v21-28) | 4 sprints på dashboard-UI | **2 sprints API-polish + 1 sprint showcase + 1 sprint monetarisering** |
| Fas 3 (v29-40) | Distribution till människor | **Distribution till maskiner (protokoll, wallets, oracles)** |

### Fas 2 omdefinierad: API som produkt (Vecka 21-28)

#### Sprint 11: API Production-Grade (Vecka 21-22)

**Dag 1-2: Performance-optimering**
- [ ] Alla Lager 1-endpoints <100ms (caching, indexering)
- [ ] Cascade-simulering <500ms (graf pre-loaded i minne)
- [ ] Batch-endpoints: skicka 100 tokens, få 100 ratings
- [ ] Connection pooling, rate limiting, graceful degradation

**Dag 3-4: OpenAPI spec + SDK:er**
- [ ] Komplett OpenAPI 3.0-specifikation
- [ ] Auto-genererad Python SDK (publicera på PyPI)
- [ ] Auto-genererad JavaScript SDK (publicera på npm)
- [ ] curl-exempel för varje endpoint
- [ ] Interaktiv API-explorer på nerq.ai/api

**Dag 5-7: WebSocket streams + Webhooks**
- [ ] WebSocket: /v1/stream/signals (kraschsignaler i realtid)
- [ ] WebSocket: /v1/stream/agents (agent-aktivitet)
- [ ] WebSocket: /v1/stream/yield-traps (yield trap-alerts)
- [ ] Webhook-system: registrera callback → få push
- [ ] Crash Shield webhook med komplett exponeringskedja
- [ ] Retry-logik, dead letter queue, delivery confirmation

**Sprint 11 Deliverables:**
```
Production-grade API med <100ms latency
OpenAPI 3.0 spec
Python + JavaScript SDK:er (PyPI + npm)
WebSocket streams (3 kanaler)
Webhook-system med Crash Shield integration
```

#### Sprint 12: Developer Experience + Onboarding (Vecka 23-24)

**Dag 1-3: Developer portal**
- [ ] nerq.ai/developers — komplett developer hub
- [ ] Quick-start guide: "Get your first rating in 30 seconds"
- [ ] Tutorials: "Integrate Nerq in your trading bot" (Python + JS)
- [ ] Tutorial: "Add Crash Shield to your DeFi agent"
- [ ] Tutorial: "Yield risk analysis for your protocol"
- [ ] API status page (uptime, latency metrics)
- [ ] Changelog / versioning

**Dag 4-5: Self-serve API-nyckel-system**
- [ ] Registrering → API-nyckel på 30 sekunder
- [ ] Dashboard: usage, billing, limits
- [ ] Stripe-integration för betalande tiers
- [ ] Auto-upgrade-förslag vid limit

**Dag 6-7: Integration templates**
- [ ] Template: "Nerq + Langchain trading agent"
- [ ] Template: "Nerq safety check i MetaMask Snap"
- [ ] Template: "Nerq yield risk i Aave governance proposal"
- [ ] Template: "Nerq Crash Shield webhook handler"
- [ ] GitHub-repo med alla templates (open source)

**Sprint 12 Deliverables:**
```
Developer portal med tutorials
Self-serve API-nyckel + billing
4+ integration templates (open source)
API status page
```

#### Sprint 13: Showcase Dashboard (Vecka 25-26)

**Skillnad vs Terminal-planen:** Dashboarden är enklare. Den visar vad API:et kan göra, den driver SEO och trovärdighet, men den är inte kärnan.

- [ ] Enkel single-page dashboard: nerq.ai/dashboard
- [ ] Ratings-oversikt med sökbar tabell
- [ ] Kraschsignaler live (visar det maskiner ser via API)
- [ ] Agent activity feed (visar nya agenter, volymförändringar)
- [ ] Yield Trap-lista
- [ ] Portfolio-input: klistra in wallet → se analys
- [ ] Cascade-simulator: välj scenario → se resultat
- [ ] Varje vy har "Get this via API" med curl-exempel

**Syfte:** Varje människa som besöker dashboarden ser hur kraftfull datan är och tänker "jag vill ha detta i min bot/protokoll/wallet."

#### Sprint 14: Monetarisering + Launch (Vecka 27-28)

- [ ] Tier-system live med Stripe
- [ ] Overage-billing implementerad
- [ ] Usage analytics per kund
- [ ] Free → Builder upgrade-flow optimerad
- [ ] Enterprise-kontaktformulär
- [ ] Launch-kommunikation:
  - [ ] "Nerq Risk API: The Bloomberg Terminal for Machines" — blog post
  - [ ] Producthunt launch
  - [ ] HackerNews: "We built a risk API that 99.2% accurately predicts crypto crashes"
  - [ ] r/cryptocurrency, r/defi, r/algotrading
  - [ ] Crypto Twitter thread
  - [ ] Dev-fokuserade communities: r/ethdev, r/solanadev

### Fas 3 omdefinierad: Distribution till maskiner (Vecka 29-40)

#### Månad 8-9: Protocol-level integrationer

| Target | Integration | Värde för dem | Nerq revenue |
|--------|------------|--------------|-------------|
| **Chainlink** | Nerq-rating som tilläggssignal i oracle-feed | Trust-layer ovanpå prisdata | Infrastructure-tier |
| **Aave/Compound** | Risk-parameter-feed för collateral-beslut | Automatiserad riskhantering | Scale/Enterprise-tier |
| **1inch/Jupiter** | Safety-check i routing-algoritm | Filtrerar honeypots, reducerar förluster | Scale-tier |
| **MetaMask** | Risk-badge via Snap | Användare ser risk pre-signering | Infrastructure-tier |
| **DeFi Llama** | Nerq-rating som tilläggsdimension | Berikar deras data | Partnership/free |
| **Olas/Virtuals** | Agent-rating i launchpad | Kvalitetssignal för agent-investerare | Scale-tier |

**Approach:** Bygg integrationen själva som open-source plugin/snap. Visa att den fungerar. Kontakta teamet med: "Vi har byggt detta, det fungerar redan, vill ni ha det?"

#### Månad 10-11: Agent ecosystem adoption

- [ ] Publish "Nerq Agent Safety Standard" — öppen specifikation
- [ ] Föreslå: varje agent-framework (ElizaOS, CrewAI, LangChain) bör inkludera Nerq safety-check som default middleware
- [ ] Bygg middleware-paket:
  - `nerq-langchain` — pre-trade safety check
  - `nerq-eliza` — plugin för ElizaOS-agenter
  - `nerq-crewai` — tool för CrewAI-agenter
- [ ] Mål: Nerq safety-check som "seatbelt for AI agents"

#### Månad 12: Exit-förberedelse

Samma som Terminal-planen, men exit-story förändras:

**Inte:** "Vi har en fin dashboard med X användare"
**Utan:** "Vi har Y maskiner som gör Z miljoner beslut per dag baserat på vår data. Varje gång en autonom agent gör en trade i DeFi, frågar den oss först. Vi är infrastruktur."

---

## EXIT-STORY: INFRASTRUKTUR > APPLIKATION

### Varför machine-first ger högre valuation

| Faktor | Terminal (applikation) | Machine-First (infrastruktur) |
|--------|----------------------|------------------------------|
| Revenue-typ | SaaS subscription | API consumption (usage-based) |
| Typisk multiple | 15-30x ARR | 30-60x ARR (infra-premium) |
| Churn | Hög i bear markets | Låg (maskiner kör alltid) |
| Moat | UX + data | Data + nätverkseffekt + protocol lock-in |
| Skalbarhet | Fler användare | Fler maskiner × fler beslut/maskin |
| Jämförbar | CoinGecko ($500M) | Chainlink ($10B+ mcap), Alchemy ($10B val) |

**Infrastructure-bolag värderas högre.** Chainlink levererar prisdata som oracle — marknadsvärde $10B+. Alchemy levererar node-access som API — valuation $10B. De bygger inte dashboards. De bygger infrastruktur som andra bygger ovanpå.

Nerq som API-infrastruktur för riskdata jämförs med Chainlink/Alchemy, inte med CoinGecko/DeFi Llama.

### Uppdaterade potentiella köpare

| Köpare | Varför machine-first-Nerq | Kan betala | Premium vs terminal |
|--------|--------------------------|------------|---------------------|
| **Chainlink** | Risk-oracle komplement till prisdata | €200M-1B | Mycket högre — direkt fit |
| **Alchemy** | Risk-layer ovanpå node-access | €200M-500M | Högre — samma kundtyp |
| **Coinbase** | Infra-play: risk-API för hela ekosystemet | €300M-1B | Högre |
| **Moody's / S&P** | API-baserad krypto-riskdata för institutioner | €200M-2B | Samma |
| **Bloomberg** | Kryptodata-pipeline för terminalen | €100-500M | Samma |
| **Circle** | Risk-infrastruktur för USDC-ekosystemet | €200M-500M | Högre |
| **Fireblocks** | Risk-API integrerad i custody-plattform | €100-500M | Högre |

### Värderingslogik

| Metod | Beräkning | Värdering |
|-------|-----------|-----------|
| Revenue multiple (infra) | €3.1M ARR × 40-60x | €124-186M |
| Revenue multiple (bull, infra) | €10.5M ARR × 40-60x | €420-630M |
| API volume valuation | 50M anrop/dag × infrastruktur-premium | €200-500M |
| Comparable: Chainlink | Risk-data oracle, protocol integration | $10B referens |
| Comparable: Alchemy | API infrastructure for crypto | $10B referens |
| Comparable: Kaiko | Data API, 200+ enterprise kunder | $100-500M referens |

**Target: €150-300M vid exit (tidig bull, infrastructure multiple)**
**Stretch: €500M-1B om protocol-level adoption + bull timing**

---

## VAD SOM BYGGER MOATEN STARKARE I MACHINE-FIRST

### 1. Crash Detection (1190/1200) blir API-infrastruktur

I terminal-modellen: en människa ser varningen.
I machine-first: **tusentals maskiner agerar automatiskt på varningen**.

Det betyder:
- Varje korrekt kraschvarning = tusentals bevisade saves
- "Nerq Crash Shield prevented $X in losses today" — daglig metrik
- Maskiner som undvek en krasch tack vare Nerq → aldrig churn
- Track record byggs automatiskt: varje save loggas via API

### 2. Agent-data blir meta-intelligence

Nerqs egna kunder (AI-agenter som querier API:et) genererar signal:
- Vilka tokens undersöker agenter just nu?
- Vilka pooler undviker agenter?
- Vilka kraschsignaler triggar mest agent-reaktion?

→ "Nerq Agent Attention Index" — en ny typ av data som bara vi kan producera.

### 3. Network effect: fler konsumenter → bättre data → fler konsumenter

Varje ny maskin som använder Nerq:
- Ger oss insight i vad maskiner bryr sig om
- Validerar våra modeller (om agenter agerar på våra signals = signals fungerar)
- Skapar lock-in (byter man bort Nerq förlorar man safety-layer)
- Gör oss mer attraktiva för nästa maskin

Bloomberg hade nätverkseffekt via chat (MSG). Nerq har nätverkseffekt via data-loop.

---

## TIDSÖVERSIKT

```
VECKA  1-12  [████████████]  Fas 0: Data-monopol (identisk med dok A)
VECKA 13-14  [██]            Sprint 7: On-chain agent crawling (identisk)
VECKA 15-16  [██]            Sprint 8: Wallet behavior analysis (identisk)
VECKA 17-18  [██]            Sprint 9: Propagated Risk + Crash Shield API
VECKA 19-20  [██]            Sprint 10: Agent Discovery + Reports
VECKA 21-22  [██]            Sprint 11: API Production-Grade + SDKs
VECKA 23-24  [██]            Sprint 12: Developer Experience + Onboarding
VECKA 25-26  [██]            Sprint 13: Showcase Dashboard (enkel)
VECKA 27-28  [██]            Sprint 14: Monetarisering + Launch
VECKA 29-40  [████████████]  Fas 3: Distribution till maskiner
```

**Total tid:** ~40 veckor (identiskt)
**Total arbetsinsats:** ~480h (sparat ~20h på enklare dashboard, +0h på API som redan planeras)
**Kostnad:** ~€35/mån (identiskt)
**Skillnad:** Fas 2 fokus skiftar från dashboard-UI till API-kvalitet, SDKs, developer experience

---

## SAMMANFATTNING: TERMINAL vs MACHINE-FIRST

Dokument A (Terminal-modellen) bygger en Bloomberg-terminal för människor som investerar i krypto. Det fungerar — dashboarden är sticky, Crash Shield konverterar free till Pro, revenue växer med bull market.

Dokument B (detta dokument) bygger **infrastruktur för maskiner som opererar i krypto**. API:et är terminalen. Maskinerna är kunderna.

**Fem saker som gör machine-first till en starkare position:**

1. **Marknaden är 54-71x större.** Maskiner gör redan 300M queries/dag vs 5.6M för människor. Vid peak: 2.5B vs 35M.

2. **Lägre churn.** Människor slutar titta på krypto i bear markets. Maskiner kör dygnet runt. API-revenue är stabilare.

3. **Crash Shield blir kraftfullare.** 1 190/1 200 historiska krascher korrekt → tusentals maskiner agerar automatiskt → "Nerq prevented $X in losses" = daglig, kvantifierbar value-metric.

4. **Infrastruktur-premium på valuation.** Applikationer värderas 15-30x ARR. Infrastruktur värderas 40-60x ARR. Chainlink och Alchemy är $10B-bolag. CoinGecko är $500M.

5. **Protocol lock-in.** När Nerq-rating är integrerad i ett DeFi-protokolls smarta kontrakt, i en wallets UI, i ett oracles data-feed — det går inte att byta ut utan governance-vote. Det är stickier än någon dashboard.

Bloomberg byggde terminalen för människor. Det blev ett $70B-bolag.

Nerq bygger terminalen för maskiner. Marknaden är större, tillväxten är snabbare, och maskinerna sover aldrig.
