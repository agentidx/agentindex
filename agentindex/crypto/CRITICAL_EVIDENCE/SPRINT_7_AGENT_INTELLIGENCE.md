# SPRINT 7: Agent Intelligence System
## Autonomt AI-agent riskanalyssystem — Dokumentation
### Datum: 2026-03-04 | Status: LIVE

---

## VAD SYSTEMET GÖR

Sprint 7 bygger världens första system som korskopplar **47,119 indexerade AI-agenter** med **institutionell kryptoriskdata** för att svara på frågor ingen annan kan besvara:

- Vilka AI-agenter sitter i tokens som är på väg att krascha?
- Hur mycket kapital kontrolleras av AI-agenter på varje blockchain?
- Vilka chains är mest sårbara om AI-agenter lämnar koordinerat?

---

## SYSTEMARKITEKTUR

### Filer

| Fil | Syfte |
|-----|-------|
| `wallet_behavior.py` | Etherscan V2 API-analys av wallet-beteende. Beräknar P(AI-agent) confidence 0–1 via 7 heuristiker. |
| `agent_activity_index.py` | Aggregerar agent-koncentration per token/protokoll/chain. Beräknar "X% av TVL kontrolleras av AI-agenter". |
| `agent_wow_analysis.py` | **Kärnan.** Korskopplar agenter med risk_signals + crash_predictions. Beräknar WOW 1/2/3/5. |
| `weekly_discovery_report.py` | Genererar HTML+JSON-rapport varje måndag 06:00. |
| `agent_intelligence_scheduler.py` | Kör alla analyser autonomt på schema. |
| `crypto_agents_api.py` | 14 endpoints under `/v1/agents/`. |

### Databastabeller (crypto_trust.db)

| Tabell | Innehåll |
|--------|----------|
| `agent_crypto_profile` | 47,119 AI-agenter från 6 källor |
| `agent_crypto_relations` | 93,786 agent↔token/chain/protokoll-kopplingar |
| `wallet_behavior` | Etherscan-analys per creator wallet |
| `agent_activity_index` | AI-koncentration per entity |
| `agent_risk_exposure` | **Kärntabell.** Agent + riskdata + crash_prob |
| `chain_concentration_risk` | Koncentrationsrisk per blockchain |
| `agent_protocol_snapshot` | Daglig snapshot för exodus-backtest (startar 2026-03-04) |

---

## WOW-ANALYSER

### WOW 1: AI-agent Riskexponering
**Vad:** Kopplar agent_crypto_profile.token_symbol → nerq_risk_signals.risk_level  
**Resultat 2026-03-04:**
- 12 agenter i CRITICAL tokens — $344.7M market cap
- 19 agenter i WARNING tokens — $172.8M market cap
- 26 agenter i WATCH tokens — $1,960.2M market cap
- 23 agenter i SAFE tokens — $0.3M market cap

**API:** `GET /v1/agents/risk-exposure?risk_level=CRITICAL`

### WOW 2: AI-agent Kraschexponering
**Vad:** Kopplar agent-exponering mot crash_model_v3_predictions (crash_prob_v3 > 0.5)  
**Resultat 2026-03-04:**
- 31 agenter med crash_prob > 50%
- **$517.4M i AI-agent kapital i hög kraschrisk**
- Snitt crash_prob: 40.9% för matchade agenter

**API:** `GET /v1/agents/risk-exposure?high_crash_risk=true`

### WOW 3: Structural Collapse-exponering
**Vad:** Identifierar AI-agenter exponerade mot tokens med structural_weakness=3 — ZARQs 100% recall early warning signal  
**Resultat 2026-03-04:**
- **12 agenter i Structural Collapse-tokens**
- **$344.7M exponerat kapital**
- Toppfynd: `pippin` (Virtuals) — $344.6M market cap, PIPPIN token, 90% kraschsannolikhet

**API:** `GET /v1/agents/structural-collapse`

### WOW 4: Agent Exodus Index (under uppbyggnad)
**Vad:** Mäter om AI-agenter lämnar ett protokoll INNAN TVL kraschar  
**Status:** Dagliga snapshots startar 2026-03-04. Backtest möjligt efter 90 dagars data (Q3 2026).  
**Hypotes:** Agent-utflöde är leading indicator för TVL-kollaps — "smarta pengar"-signal  
**API:** `GET /v1/agents/exodus-snapshot`

### WOW 5: Chain Koncentrationsrisk
**Vad:** Rankar blockchains efter AI-agent-koncentration och riskexponering  
**Resultat 2026-03-04:**

| Chain | Agenter | Market Cap | Risk Score |
|-------|---------|------------|------------|
| Fetch | 24,100 | $0M* | 10/10 |
| Base | 19,442 | $1,920M | 10/10 |
| Multi | 1,789 | $15,299M | 2.3/10 |
| Solana | 593 | $90,568M | 0.45/10 |
| Ethereum | 479 | $11,380M | 0.3/10 |

*Fetch: agenter utan registrerat token-värde  
**Nyckelinsikt:** Base är världens mest AI-agent-dominerade blockchain med $1.92B i agent-kontrollerat kapital.

**API:** `GET /v1/agents/chain-concentration-risk`

---

## AUTONOMT SCHEMA

| Process | Schema | LaunchAgent |
|---------|--------|-------------|
| Wallet behavior-analys | Varje måndag 02:00 | `com.zarq.agent-intelligence` |
| Agent Activity Index | Varje måndag 03:00 | `com.zarq.agent-intelligence` |
| WOW-analys (risk/crash/collapse) | Dagligen 04:00 | `com.zarq.agent-intelligence` |
| Protocol snapshot (exodus) | Dagligen 04:05 | `com.zarq.agent-intelligence` |
| Weekly Discovery Report | Varje måndag 06:00 | `com.zarq.weekly-agent-report` |

---

## API-ENDPOINTS (14 totalt under /v1/agents/)

```
GET /v1/agents/crypto/{agent_id}          — Agent-profil
GET /v1/agents/in/{entity_type}/{id}      — Agenter per entity
GET /v1/agents/new                        — Senast crawlade
GET /v1/agents/relations/{agent_id}       — Agent-relationer
GET /v1/agents/graph/{type}/{id}          — Graf-query
GET /v1/agents/activity/{type}/{id}       — Activity Index
GET /v1/agents/activity-overview          — Alla entities
GET /v1/agents/wallet/{address}           — Wallet behavior
GET /v1/agents/ai-identified              — Identifierade AI-agenter
GET /v1/agents/report/latest              — Senaste veckorapport
GET /v1/agents/risk-exposure              — WOW 1/2/3: Riskexponering
GET /v1/agents/structural-collapse        — WOW 3: Collapse-lista
GET /v1/agents/chain-concentration-risk   — WOW 5: Chain-ranking
GET /v1/agents/exodus-snapshot            — Tier 2: Exodus tidsserie
```

---

## DATAKÄLLOR

| Källa | Agenter | Typ |
|-------|---------|-----|
| Fetch.ai / ASI Alliance | 24,100 | AI-agenter on-chain |
| Virtuals Protocol (Base) | 19,905 | AI-agent tokens |
| CoinGecko | 1,789 | Krypto-tokens med AI-koppling |
| Bittensor | 641 | Subnet-agenter |
| Olas/Autonolas | 474 | Ethereum-agenter |
| DexScreener | 210 | Agent-tokens |

---

## MATCHNINGSLOGIK

Risk-kopplingen sker via `token_symbol` (t.ex. "PEPE" → CRITICAL).  
Täckning: 80 av 47,119 agenter matchade (0.2%) — men dessa representerar de största och mest likvida token-exponerade agenterna.  
Förbättring: utöka nerq_risk_signals till fler tokens ökar täckningen direkt.

---

## NÄSTA STEG

1. **Sprint 3.2 Contagion Map** → koppla agent-grafen mot contagion-nätverket → "Om PIPPIN kraschar, vilka andra Virtuals-agenter drabbas?"
2. **Utöka risk_signals** → fler tokens → högre matchningstäckning
3. **Q3 2026** → 90 dagars exodus-snapshot data → backtest Agent Exodus Index
4. **Exit-pitch** → "Vi är de enda som kan säga: $517M AI-agent-kapital har >50% kraschsannolikhet idag"

---

*ZARQ Agent Intelligence — Sprint 7*  
*Data: crypto_trust.db | API: zarq.ai/v1/agents/*
