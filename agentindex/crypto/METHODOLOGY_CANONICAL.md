# NERQ CRYPTO — METHODOLOGY CANONICAL
## Single Source of Truth — v1.0

**Datum:** 2026-02-27
**Status:** KANONISK — alla andra dokument som avviker härifrån är superseded
**Supersedes:** Master Plan (5-pelare), Sprint Plan v1 (6 signaler), div. ad-hoc-specifikationer

---

## 1. ARKITEKTURÖVERSIKT

Nerq Crypto Risk Intelligence består av **TVÅ komplementära modeller**:

| Modell | Syfte | Output | Uppdateringsfrekvens |
|--------|-------|--------|---------------------|
| **Trust Score** | Relativ kvalitetsbedömning | 0-100 poäng, A+ till F | Vid datainsamling |
| **NDD** (Network Distress Detector) | Distress-detektion & early warning | 0-5 skala, alerts | Dagligen/veckovis |

Dessa är **inte samma modell med olika namn**. De mäter olika saker, använder olika data, och har olika vikter. De samverkar i par-selektion (Trust Score driver relativ ranking, NDD filtrerar bort distress-risk vid shorting).

---

## 2. TRUST SCORE — Relativ Kvalitetsbedömning

### 2.1 Definition

Trust Score bedömer den övergripande tillförlitligheten och kvaliteten hos kryptoentiteter (tokens, exchanges, DeFi-protokoll) baserat på offentligt tillgänglig data.

### 2.2 Fem Dimensioner (Pelare)

| # | Dimension | Vikt | Vad den mäter |
|---|-----------|------|---------------|
| 1 | **Security** | 30% | Audits, hack-historik, kontraktrisk, reserver, ATH-recovery, multi-chain-närvaro |
| 2 | **Compliance** | 25% | Regulatorisk status, social närvaro, kategorisering, supply-transparens |
| 3 | **Maintenance** | 20% | GitHub-aktivitet, volymaktivitet, utvecklingsunderhåll |
| 4 | **Popularity** | 15% | Market cap rank, volym, social following |
| 5 | **Ecosystem** | 10% | Multi-chain-stöd, DeFi-integration, kategoribredd |

### 2.3 Ratingskala

| Betyg | Score | Beskrivning |
|-------|-------|-------------|
| A+ | 90-100 | Exceptionell kvalitet |
| A | 80-89 | Hög kvalitet |
| B+ | 70-79 | Bra kvalitet |
| B | 60-69 | Godkänt |
| C+ | 50-59 | Under genomsnitt |
| C | 40-49 | Svag |
| D+ | 30-39 | Dålig |
| D | 20-29 | Mycket dålig |
| F | 0-19 | Underkänt / Hög risk |

### 2.4 Entitetsspecifik Scoring

Trust Score har separata scoring-funktioner för tokens, exchanges, och DeFi-protokoll. Dimensionerna och vikterna är identiska, men indatavariablerna anpassas:

- **Tokens:** Använder market cap, ATH-recovery, contract verification, GitHub-metriker
- **Exchanges:** Använder CoinGecko trust score, proof of reserves, trading volume
- **DeFi:** Använder TVL, audit-status, hack-historik, chain-deployments

### 2.5 Validering

Retroaktiv analys visar konsistent separation:
- Kollapsade exchanges: genomsnitt 5.0/100 (vs 44.5 plattformssnitt)
- Kollapsade tokens: genomsnitt 30.9/100 (vs 22.8 snitt)
- Alla stora kollapser 2022-2023 scorade under plattformssnittet

**Begränsning:** Valideringen är retroaktiv. Trust Score beräknas på nuvarande data, inte historisk data vid tidpunkten före kollaps (med undantag för ATH-recovery som implicit fångar historiska krascher).

### 2.6 Relation till Moody's-skala

**Beslut (2026-02-27):** Trust Score använder A+ till F-skala, INTE Moody's Aaa-D. Dock finns en intern mappning för par-backtest-systemet som grupperar Trust Score-betyg i Moody's-liknande ratingklasser:

| Ratingklass | Moody's-analog | Trust Score-baserad mappning |
|-------------|---------------|------------------------------|
| IG_HIGH | Aaa-Aa3 | Används i par-selektion |
| IG_MID | A1-A3 | **Bäst fungerande klass för par-alpha** |
| IG_LOW | Baa1-Baa3 | |
| HY_HIGH | Ba1-Ba3 | |
| HY_LOW | B1-B3 | |
| DISTRESS | Caa-D | |

Denna mappning sker i `crypto_rating_history`-tabellen och är separat från Trust Score-betyget.

---

## 3. NDD — Network Distress Detector

### 3.1 Definition

NDD mäter finansiell distress-risk i realtid. Skala 0-5 där 5 = helt säker, 0 = omedelbar kollapsrisk.

### 3.2 Sju Signaler

| # | Signal | Vikt | Vad den mäter | Notation |
|---|--------|------|---------------|----------|
| S1 | **Liquidity Depth** | 10% | Omsättning, volymtrend, volymstabilitet | Liq |
| S2 | **Holder Concentration** | 5% | Whale-aktivitet, Gini-koefficient, aktivitetsspridning | Hold |
| S3 | **Ecosystem Resilience** | 30% | Drawdown, volatilitet, momentum, acceleration, streak | Res |
| S4 | **Fundamental Activity** | 10% | Volymtrend, panic detection, pris/volym-divergens | Fund |
| S5 | **Contagion Exposure** | 25% | Korrelation med BTC, downside beta | Cont |
| S6 | **Structural Risk** | 5% | Flash crash-frekvens, spread, token-ålder | Str |
| S7 | **Relative Weakness** | 15% | Token-prestation relativt BTC (7d/14d/30d) | Rel |

### 3.3 Viktjustering (v3.1)

Vikterna fastställdes genom signalkorrelationsanalys mot historiska krascher:
- S1 (Liquidity) minskad 20%→10%: kontraproduktiv — volymen ÖKAR ofta vid krascher
- S2 (Holders) minskad 15%→5%: kontraproduktiv
- S5 (Contagion) ökad 10%→25%: starkaste prediktorn (-1.14 diff crash vs stable)
- S7 (Relative Weakness) NY signal 15%: fångar snabb relativ underprestation

**⛔ FRUSNA:** Dessa vikter och trösklar modifieras EJ utan ny backtest-validering.

### 3.4 Override-regler (Frusna)

| Villkor | Åtgärd |
|---------|--------|
| 1 signal < 0.5 | Cap NDD vid 1.0 |
| 2+ signaler < 1.5 | Cap NDD vid 1.5 |
| 3+ signaler < 2.0 | Cap NDD vid 1.5 |
| Stablecoin med NDD < 2.0 | Golv vid 2.0 |

### 3.5 Alert-nivåer (Frusna)

| Nivå | Tröskel | Tröskel (Top 50) |
|------|---------|-------------------|
| SAFE | NDD ≥ 4.0 | NDD ≥ 4.0 |
| WATCH | NDD ≥ 3.0 | NDD ≥ 3.0 |
| WARNING | NDD ≥ 2.0 | NDD ≥ 1.5 |
| DISTRESS | NDD ≥ 1.0 | NDD ≥ 1.0 |
| CRITICAL | NDD < 1.0 | NDD < 1.0 |

### 3.6 NDD Trend-kategorisering

| Trend | NDD-förändring (4 veckor) |
|-------|---------------------------|
| FREEFALL | < -1.0 |
| FALLING | -1.0 till -0.5 |
| SLIDING | -0.5 till -0.2 |
| STABLE | -0.2 till +0.2 |
| IMPROVING | > +0.2 |

### 3.7 Datakällor

NDD beräknas via två paths:
- **OHLCV path:** Tokens med ≥60 dagars prishistorik (~210 tokens). Använder exakt v3.1-signalberäkning.
- **Snapshot path:** Tokens med enbart daglig snapshot-data (~18,000 tokens). Approximerar signalerna med samma scoring-kurvor men reducerad datatillgång.

---

## 4. HC ALERT — High Conviction Alert

### 4.1 Definition

HC Alert triggas när en token visar ihållande distress med accelererande försämring.

### 4.2 Triggerkriteria

BÅDA villkoren måste vara uppfyllda:
1. **Streak ≥ 3 veckor** i WARNING, DISTRESS, eller CRITICAL
2. **NDD-förändring (4 veckor) ≤ -1.0** (FREEFALL-trend)

### 4.3 Validering

- Precision: 78% (av alla HC Alerts ledde 78% till signifikant prisfall)
- False positive rate: 5%
- Sampelstorlek: n=275 signaler
- Tidsperiod: 2017-2026

**⛔ VIKTIGT — IS/OOS-separation:**

| Period | Status | Anmärkning |
|--------|--------|------------|
| 2017-2023 | In-sample | Vikter kalibrerades på denna data |
| 2024-2026 | Out-of-sample | **EJ SEPARAT RAPPORTERAD** |

**ÅTGÄRD KRÄVS:** Dela upp n=275 i IS/OOS och rapportera separat med Wilson score konfidensintervall. Nuvarande "78% precision" är meningslös för due diligence utan denna separation.

### 4.4 Crash Probability-tabell

Kalibrerad på 393 crash cycles. Lookup: (trend, alert_level) → P(crash >30% inom 90d).

| Trend | WARNING | DISTRESS | WATCH | SAFE |
|-------|---------|----------|-------|------|
| FREEFALL | 43% | 34% | 28% | — |
| FALLING | 37% | 30% | 25% | — |
| SLIDING | 33% | 28% | 20% | — |
| STABLE | 33% | 30% | 18% | 3% |
| IMPROVING | 20% | 18% | 12% | 2% |

**Notering:** Tabellen specificerar ej om den är kalibrerad in-sample eller validerad OOS. Antal observationer per cell ej rapporterat. **Åtgärd krävs.**

---

## 5. BOTTLEFISH — Recovery Signal

### 5.1 Definition

Bottlefish identifierar tokens som kraschat ≥70% från peak men visar stark recovery (bounce from trough).

### 5.2 Signalnivåer

| Signal | Bounce (90d) | Max Rank | Min Trust Score | Validerad Win Rate | n |
|--------|-------------|----------|-----------------|-------------------|---|
| STRONG_BUY | ≥ 150% | ≤ 100 | ≥ 60 | 80% | **10** |
| BUY | ≥ 200% | ≤ 200 | — | 72% | **18** |
| SPECULATIVE | ≥ 150% | ≤ 500 | ≥ 50 | 64% | **34** |
| AVOID | Crash ≥70%, bounce <50% | — | — | — | — |

### 5.3 Begränsningar (KRITISKA)

- **STRONG_BUY n=10:** Otillräckligt för statistisk signifikans. Bör kommuniceras som "preliminär signal" i all extern kommunikation.
- **BUY n=18:** Tidig indikation, ej robust. Wilson 95%-KI för 72% win rate med n=18: [47%, 90%].
- **SPECULATIVE n=34:** Begränsad statistisk signifikans.
- **IS/OOS-separation ej specificerad.**

---

## 6. PORTABLE ALPHA — Par-strategi

### 6.1 Arkitektur

Portable Alpha-strategin kombinerar:
1. **Trust Score-baserad par-selektion** — long top-quartile, short bottom-quartile inom samma ratingklass
2. **NDD-baserad distress-filtrering** — short inte tokens med NDD < 1.5
3. **Bear market detection** — skip när BTC monthly return < -15%
4. **Kapitalallokering** — allokera mellan pairs-portfölj och cash/BTC

### 6.2 Implementationsdetaljer (från nav_tracker.py)

- **Universum:** ~85 MAJOR tokens, exklusive stablecoins
- **Ratingklass:** Enbart IG_MID (A1-A3)
- **Par-selektion:** Top-5 per månad baserat på conviction score (40% spread + 60% NDD-differential)
- **Max per token:** 2 par
- **Holding period:** 90 dagar
- **Return cap:** ±100% per leg
- **Bear detection:** BTC monthly return < -15% → skip

### 6.3 Varianter

| Variant | Pairs/Cash | Risk Score |
|---------|-----------|------------|
| Conservative | 80% cash / 20% pairs | 5/5 |
| Growth | 60% cash / 40% pairs | 3/5 |
| Aggressive | 40% cash / 60% pairs | 1/5 |

### 6.4 Backtest-status

**⛔ VILLKORAT — Reconciliering pågår (Sprint 2.0)**

| Mätpunkt | nav_tracker.py | crypto_pairs_backtest v2 (OOS, alla klasser) | crypto_pairs_backtest v2 (OOS, IG_MID only) |
|----------|---------------|---------------------------------------------|----------------------------------------------|
| Par | 5/månad | 9,148 totalt | 5,160 |
| Hit Rate | ~84% (uppskattning) | 59.0% | 64.2% |
| Avg Alpha | ~19.8%/mo (compoundad) | 4.42%/kvartal | 10.55%/kvartal |
| Median Alpha | — | 8.45% | 14.45% |
| Sharpe | — | 0.14 (vs BTC 0.94) | Ej separat beräknad |
| MaxDD | — | 32,632% (kumulativ) | Ej separat beräknad |

**Rotorsaker till diskrepansen:**
1. nav_tracker.py kör enbart IG_MID (cherry-picked bästa klassen)
2. nav_tracker.py har conviction top-5 selektion (ovaliderad)
3. nav_tracker.py skippar bear markets
4. nav_tracker.py capar returns vid ±100% vs ±200%
5. nav_tracker.py compoundar; backtestet rapporterar raw alpha per par

Se `BLOCKER_1_RECONCILIATION_ANALYSIS.md` för fullständig analys.

### 6.5 Kommunikationsregel

**Tills portable_alpha_strategy.py har körts med korrekt IS/OOS-separation:**
- INGA specifika avkastningssiffror i extern kommunikation
- IG_MID OOS-data (64.2% hit rate, +10.55% alpha) kan refereras MED caveats
- "$10K → $16M" är FÖRBJUDET i all kommunikation

---

## 7. API-MAPPNING — Modell-output till Endpoint

Varje modell-beräkning mappas till en API-endpoint med definierat JSON-schema.

### 7.1 Trust Score → `GET /v1/crypto/rating/{token_id}`

```json
{
  "data": {
    "token_id": "bitcoin",
    "symbol": "BTC",
    "trust_score": 87.3,
    "trust_grade": "A",
    "pillars": {
      "security": { "score": 92.0, "weight": 0.30 },
      "compliance": { "score": 85.5, "weight": 0.25 },
      "maintenance": { "score": 88.0, "weight": 0.20 },
      "popularity": { "score": 95.0, "weight": 0.15 },
      "ecosystem": { "score": 78.0, "weight": 0.10 }
    },
    "scored_at": "2026-02-28T06:00:00Z"
  },
  "meta": { "version": "v1", "cache_ttl": 3600 }
}
```

### 7.2 NDD → `GET /v1/crypto/ndd/{token_id}`

```json
{
  "data": {
    "token_id": "golem",
    "symbol": "GLM",
    "ndd": 1.50,
    "alert_level": "DISTRESS",
    "ndd_trend": "FREEFALL",
    "ndd_change_4w": -1.35,
    "crash_probability_30pct": 0.34,
    "crash_probability_50pct": 0.13,
    "signals": {
      "liquidity": { "value": 2.1, "weight": 0.10 },
      "holders": { "value": 3.0, "weight": 0.05 },
      "resilience": { "value": 0.8, "weight": 0.30 },
      "fundamental": { "value": 2.5, "weight": 0.10 },
      "contagion": { "value": 1.2, "weight": 0.25 },
      "structural": { "value": 3.5, "weight": 0.05 },
      "relative_weakness": { "value": 0.9, "weight": 0.15 }
    },
    "hc_alert": true,
    "hc_streak_weeks": 4,
    "override_triggered": true,
    "calculated_at": "2026-02-28T06:00:00Z"
  },
  "meta": { "version": "v1", "cache_ttl": 300 }
}
```

### 7.3 HC Alert Events → `GET /v1/crypto/signals`

```json
{
  "data": {
    "active_signals": [
      {
        "type": "HC_ALERT",
        "token_id": "golem",
        "symbol": "GLM",
        "ndd": 1.50,
        "trend": "FREEFALL",
        "crash_probability": 0.34,
        "streak_weeks": 4,
        "triggered_at": "2026-02-21T06:00:00Z",
        "sha256_hash": "a1b2c3d4...",
        "status": "ACTIVE"
      }
    ],
    "scoreboard": {
      "total_live_signals": 12,
      "confirmed_correct": 8,
      "false_positive": 2,
      "pending": 2,
      "precision_live": 0.80
    }
  }
}
```

### 7.4 Safety Check → `GET /v1/crypto/safety/{token_id}`

Lightweight, <100ms, optimerad för pre-trade validation av AI-agenter.

```json
{
  "data": {
    "token_id": "bitcoin",
    "safe": true,
    "risk_level": "LOW",
    "trust_grade": "A",
    "ndd": 4.2,
    "alert_level": "SAFE",
    "hc_alert": false,
    "crash_probability": 0.03,
    "flags": []
  },
  "meta": { "version": "v1", "response_ms": 12 }
}
```

Negativt exempel (hög risk):
```json
{
  "data": {
    "token_id": "golem",
    "safe": false,
    "risk_level": "HIGH",
    "trust_grade": "C",
    "ndd": 1.50,
    "alert_level": "DISTRESS",
    "hc_alert": true,
    "crash_probability": 0.34,
    "flags": ["HC_ALERT_ACTIVE", "FREEFALL_TREND", "LOW_LIQUIDITY"]
  },
  "meta": { "version": "v1", "response_ms": 8 }
}
```

### 7.5 Endpoint-modell-mappning (komplett)

| Endpoint | Modell | Latency-mål |
|----------|--------|-------------|
| `GET /v1/crypto/rating/{id}` | Trust Score | <200ms |
| `GET /v1/crypto/ndd/{id}` | NDD | <200ms |
| `GET /v1/crypto/ratings` | Trust Score (bulk) | <500ms |
| `GET /v1/crypto/signals` | HC Alert + Bottlefish | <200ms |
| `GET /v1/crypto/signals/history` | HC Alert historik | <500ms |
| `GET /v1/crypto/compare/{a}/{b}` | Trust Score + NDD | <300ms |
| `GET /v1/crypto/distress-watch` | NDD < 2.0 filter | <300ms |
| `GET /v1/crypto/safety/{id}` | TS + NDD + HC (aggregerat) | <100ms |
| `POST /v1/crypto/stresstest` | Stresstest-motor | <1000ms |
| `GET /v1/crypto/contagion/{id}` | Contagion graf | <500ms |
| `GET /v1/crypto/transition-matrix/{level}` | Transition matrix | <200ms |

---

## 8. FRAMTIDA UTÖKNINGAR (Platsreserveringar)

### 8.1 Agent Intelligence Layer (Fas 1, Sprint 7-10)

Korskoppling av AI-agenter med kryptodata:
- `GET /v1/agents/crypto/{agent_id}` — Agentens krypto-profil
- `GET /v1/agents/in/{entity_type}/{entity_id}` — Agenter i en token/protokoll
- `GET /v1/agents/activity/{entity_type}/{entity_id}` — Agent Activity Index
- Agent-koncentration per token som riskfaktor i NDD

### 8.2 Propagated Risk Engine (Fas 1, Sprint 9)

Cascade-simulering genom token-chain-agent-grafen:
- `GET /v1/cascade/simulate` — Simulera kollaps och spridning
- `POST /v1/portfolio/crash-shield` — Registrera för bevakning
- `POST /v1/portfolio/analyze` — Komplett portföljanalys

### 8.3 Yield Risk Intelligence (Fas 1, Sprint 10)

- `GET /v1/yield/risk/{protocol}/{pool}` — Yield Risk Score
- `GET /v1/yield/traps` — Aktiva Yield Traps
- Sustainability-analys, mechanism risk, agent dependency

### 8.4 Machine-First Infrastructure (Fas 2, Sprint 11-14)

- WebSocket streams: `/v1/stream/signals`, `/v1/stream/agents`
- SDKs: Python (PyPI), JavaScript (npm)
- Middleware: nerq-langchain, nerq-eliza, nerq-crewai
- 6-tier pricing: Open → Infrastructure

---

## 9. BEGRÄNSNINGAR

### 7.1 Datahistorik
Kryptomarknaden har ~10 års historia vs tradfi:s 100+. Alla statistiska resultat bör tolkas med denna begränsning.

### 7.2 Sampelstorlekar
- HC Alert precision (n=275): Tillräckligt för statistisk signifikans, MEN IS/OOS-separation krävs
- Bottlefish STRONG_BUY (n=10): EJ statistiskt signifikant
- Crash Probability-tabell: Baserad på 393 crash cycles (ej specificerat per cell)
- OHLCV-path tokens (~210): Begränsat urval av total marknad

### 7.3 Vad modellerna INTE fångar
- Hacks och tekniska exploits
- Regulatoriska överraskningar
- Insider-bedrägerier (FTX-typ)
- Politiska händelser
- Nyckelpers oner som lämnar projekt
- Smart contract-buggar

### 7.4 Execution costs
Pairs backtest inkluderar EJ transaktionskostnader. Estimerad kostnad: 0.5% per trade (entry + exit), dvs 1% round-trip per par.

### 7.5 Concentration risk
nav_tracker.py kör 5 par/månad från ~85 tokens. Hög koncentration i enskilda positioner.

### 7.6 Max Drawdown
Backtestet visar -64.3% max monthly drawdown på enskilda par. Portföljnivå-drawdown beror på allokering.

---

## VERSIONSHISTORIK

| Version | Datum | Ändring |
|---------|-------|---------|
| 1.0 | 2026-02-27 | Initial kanonisk version. Harmoniserar Trust Score (5 pelare), NDD (7 signaler), HC Alert, Bottlefish, Crash Probability, Portable Alpha. |
| 1.1 | 2026-02-28 | Lagt till Sektion 7 (API-mappning med JSON-scheman) och Sektion 8 (Framtida utökningar) per Sprint Plan v3.1-krav. |

---

*Alla andra dokument som avviker från denna specifikation är superseded.*
*Vid konflikt gäller METHODOLOGY_CANONICAL.md.*
