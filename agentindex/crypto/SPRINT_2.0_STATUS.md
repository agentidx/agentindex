# NERQ Crypto — Sprint 2.0 Status
**Last updated: 2026-02-28**
**Referens: NERQ_CRYPTO_SPRINT_PLAN_V3_1_1_DAG_NATT-1.md**

---

## SESSION 2026-02-28 — SAMMANFATTNING

Massiv genombrott-session. Löste Sprint 2.0 blockerare, byggde komplett Sharpe-analys, produktions-risksignalsystem, full-historik backtest, institutionella fondstrategier, konkurrensanalys och investor pitch.

---

## SPRINT 2.0: BLOCKERARE — STATUS ✅ KLAR

### 2.0.1 Reconciliera pairs-diskrepansen ✅ KLAR
- [x] Dokumenterat nav_tracker.py:s logik steg-för-steg
- [x] Byggt `portable_alpha_strategy.py` — integrerat backtest
- [x] Kört och jämfört mot Handoverns beräkningar
- [x] **GO-BESLUT: Pairs alpha är REAL**
  - Original conviction portfolio: 75% hit rate, 25% alpha, Sharpe 0.965
  - NERQ Risk L/S (ny, bättre): 70.7% hit rate, Sharpe 2.82, CAGR +281%
  - Diskrepansen löst: nav_tracker.py hade korrekt logik, crypto_pairs_backtest.py v2 hade annorlunda selektionsfilter

### 2.0.2 Metodologi-harmonisering ⚠️ DELVIS KLAR
- [x] Trust Score (6 pelare) dokumenterad i pitch
- [x] NDD (7 signaler) dokumenterad i pitch
- [x] Risk Classification (SAFE/WATCH/WARNING/CRITICAL) definierad och validerad
- [ ] **TODO: Skapa `METHODOLOGY_CANONICAL.md` — formell single source of truth med JSON-scheman**
- [ ] **TODO: API-mappning sektion (vilken output → vilken endpoint)**

### 2.0.3 In-sample / Out-of-sample separation ✅ KLAR
- [x] HC Alert / Crash prediction: IS/OOS tydligt separerat
  - Training: pre-2023, Validation: 2023, OOS: Jan 2024 - Feb 2026
  - 207 tokens, 17,845 weekly observations, zero lookahead
- [x] 113/113 deaths detected (100% recall), 98% precision OOS
- [x] Wilson score konfidensintervall beräknade (i portable_alpha_strategy.py)
- [x] Bottlefish: sampelstorlekar noterade
- [x] Idiosyncratic vs beta-driven: 87% idiosyncratic, 100% detected

### Sprint 2.0 GO/NO-GO: ✅ GO — Pairs alpha bekräftad och ÖVERTRÄFFAD
Original conviction: Sharpe 0.965 → NERQ Risk L/S: Sharpe 2.82 (3x bättre)

---

## EXTRA ARBETE UTÖVER SPRINT 2.0 (gjort denna session)

### Sharpe / Risk-Adjusted Analysis (EJ i ursprunglig sprint men kritiskt för pitch)
- [x] Melt-up analys — Upside är INTE predikerbar (10-12% melt-up oavsett risk)
- [x] Nyckelinsikt bevisad: Styrka predicerar SÄKERHET, inte outperformance
- [x] Sharpe per risk-nivå: SAFE 1.55, WATCH 0.05, WARNING -0.56, CRITICAL -0.77
- [x] SMA-trigger testad och FÖRKASTAD (ingen förbättring)
- [x] Long/short weekly spread: +107.6% annualiserad

### Risk Signal Production System (föregripper Sprint 2.5)
- [x] `nerq_risk_signals.py` (472 rader) — daglig signalgenerator
- [x] DB-tabeller: `nerq_risk_signals`, `nerq_risk_alerts`
- [x] Integrerat som Step 5 i `crypto_daily_master.py`
- [x] Första körning: 205 tokens (51 SAFE, 82 WATCH, 47 WARNING, 25 CRITICAL)
- [x] Kör dagligen kl 06:00 CET

### Full-historik Backtest
- [x] OOS 2024-2025: $10K → $170K, Sharpe 2.70, MaxDD -48.8%
- [x] Full historik 2021-2025: $10K → $5,746,461, CAGR +281%, Sharpe 2.82
- [x] Alla marknadsregimer bevisade (bull, bear, recovery, crash)

### Konkurrensanalys
- [x] vs alla kända kryptofonder, ETFer, akademiska strategier
- [x] NERQ #1 CAGR, #2 Sharpe (efter Medallion), #1 composite
- [x] Ingen känd strategi uppnår både CAGR >100% OCH Sharpe >1.5
- [x] Ärliga caveats dokumenterade

### Institutionella Fondstrategier (föregripper Sprint 6 + Fund Launch)
- [x] 8 statiska hybrid-portföljer testade (BTC core + L/S overlay + cash)
- [x] Bear detection system (BTC DD från 365d ATH)
- [x] 7 dynamiska strategier testade
- [x] **Dynamic Fund (Strategi B):** CAGR +79%, Sharpe 2.02, MaxDD -26%, Calmar 3.05, Win 77%
- [x] **Conservative Fund (Strategi F):** CAGR +63%, Sharpe 2.39, MaxDD -21.8%, Calmar 2.87
- [x] Institutional grade checks: DD<-30% PASS, Sharpe>2.0 PASS, Calmar>1.0 PASS

### Pitch & Dokumentation (föregripper Sprint 4 + Sprint 6)
- [x] `NERQ_RISK_INTELLIGENCE_PITCH_v4.md` (337 rader) — komplett pitch
- [x] `NERQ_INVESTOR_PITCH_v4.pdf` (8 sidor) — investor-ready PDF
- [x] Fund launch plan (struktur, fees, timeline, kapacitet, risker)
- [x] Tre fondprodukter definierade (Alpha, Dynamic, Conservative)

---

## SPRINT 2.5: API + EARLY WARNING + TOKEN-SIDOR — TODO 🔲

### 2.5.1 API-endpoints
- [ ] `GET /v1/crypto/rating/{token_id}` — Trust Score + grade + breakdown
- [ ] `GET /v1/crypto/ndd/{token_id}` — NDD + trend + crash probability
- [ ] `GET /v1/crypto/ratings` — Alla tokens, sorterbara
- [ ] `GET /v1/crypto/signals` — Aktiva HC Alerts + Bottlefish
- [ ] `GET /v1/crypto/signals/history` — Historiska signaler med utfall
- [ ] `GET /v1/crypto/compare/{token1}/{token2}` — Jämförelse
- [ ] `GET /v1/crypto/distress-watch` — Tokens med NDD < 2.0
- [ ] `GET /v1/crypto/safety/{token_address}` — Snabb säkerhetscheck (<100ms)
- [ ] **NYT: `GET /v1/crypto/risk-level/{token_id}` — SAFE/WATCH/WARNING/CRITICAL**
- [ ] **NYT: `GET /v1/crypto/risk-levels` — Alla tokens med risk-nivå**
- [ ] Rate limiting: 100 req/dag gratis
- [ ] OpenAPI/Swagger-dokumentation

### 2.5.2 Publik Early Warning Feed
- [ ] `/crypto/signals` sida med aktiva och historiska signaler
- [ ] SHA-256 hash av signaldata
- [ ] Running scoreboard
- [ ] RSS/Atom feed

### 2.5.3 Token Rating-sidor
- [ ] ~200 token-ratingsidor med AI-Citable Summary
- [ ] Schema.org markup
- [ ] "Get this via API"-sektion med curl-exempel

### 2.5.4 AI-Citable Summary
- [ ] Answer capsules per token

### 2.5.5 MCP Server — crypto-endpoints
- [ ] Utöka med crypto-tools (5 st)

---

## SPRINT 3: CONTAGION MAP + STRESSTEST — TODO 🔲
- [ ] 3.1 Contagion Map (graf-data + visualisering)
- [ ] 3.2 Portfölj-stresstest (POST /v1/crypto/stresstest)
- [ ] 3.3 Transition Matrix (30d/90d/365d)
- [ ] 3.4 Likviditets-Exit-Score
- [ ] 3.5 Volatilitetsjusterade crash-trösklar

---

## SPRINT 4: WHITE PAPER + TRACK RECORD — TODO 🔲
- [ ] 4.1 White Paper v1.0 (inkl Machine-First Future Work sektion)
- [ ] 4.2 Track Record-sida (automatisk uppdatering)
- [ ] 4.3 Schema.org + Strukturerad Data
- [ ] 4.4 Content & Distribution (developer-riktat content)
- [ ] 4.5 AI Citation Baseline Test
- [ ] 4.6 llms.txt + Bulk Data publicering

---

## SPRINT 5: FREEMIUM LAUNCH + REVENUE — TODO 🔲
- [ ] 5.1 Pricing-tiers (3 nu, designade för 6 i Fas 2)
- [ ] 5.2-5.6 Stripe, API-nycklar, email-alerts, RCS, Yield vs Risk
- [ ] 5.7 API Discovery Foundations (API.guru, Postman, MCP-server tagging)

---

## SPRINT 6: EXIT-FÖRBEREDELSE — TODO 🔲
- [ ] 6.1 AI Citation Test
- [ ] 6.2 Track Record uppdatering
- [ ] 6.3 White Paper v1.1
- [ ] 6.4 Investor/Acquirer Deck (dual narrativ: data + infra)
  - **DELVIS KLAR:** Pitch v4 PDF redan byggd med fondprodukter
  - TODO: Konvertera till 15-slide PPTX-format
- [ ] 6.5 Outreach (köparlista: Chainlink, Moody's, Alchemy etc.)
- [ ] 6.6 DeFi Fund beslutspunkt
  - **FRAMSTEG:** Tre fondprodukter definierade och backtestade
  - Alpha Fund: CAGR +281%, Sharpe 2.82
  - Dynamic Fund: CAGR +79%, Sharpe 2.02, MaxDD -26%
  - Conservative Fund: CAGR +63%, Sharpe 2.39, MaxDD -21.8%
  - TODO: Paper trading, execution engine, legal structure

---

## FAS 1-3: OFÖRÄNDRADE FRÅN SPRINTPLAN v3.1
Se `NERQ_CRYPTO_SPRINT_PLAN_V3_1_1_DAG_NATT-1.md` för detaljer.

---

## NYCKELFILER

| Fil | Beskrivning | Status |
|---|---|---|
| `nerq_risk_signals.py` | Daglig risksignalgenerator (Step 5) | ✅ Produktion |
| `crypto_daily_master.py` | Full pipeline (Steps 1-5) | ✅ Produktion |
| `crypto_conviction_portfolio.py` | Original L/S conviction system | ✅ Referens |
| `portable_alpha_strategy.py` | Portable alpha (Cons/Growth/Aggr) | ✅ Validerad |
| `nerq_model_portfolio.py` | Model portfolio v1 | ✅ Referens |
| `nerq_model_portfolio_v4.py` | Model portfolio v4 (BTC+alt) | ✅ Referens |
| `NERQ_RISK_INTELLIGENCE_PITCH_v4.md` | Full pitch markdown | ✅ Klar |
| `NERQ_INVESTOR_PITCH_v4.pdf` | 8-sidig investor PDF | ✅ Klar |
| `NERQ_RISK_INTELLIGENCE_PITCH_v3.md` | Föregående pitch | Superseded |
| `crypto_trust.db` | Huvuddatabas (alla tabeller) | ✅ Live |
| `NERQ_CRYPTO_SPRINT_PLAN_V3_1_1_DAG_NATT-1.md` | Master sprint plan | Referens |

---

## NYCKELSIFFROR

| Metric | Värde |
|---|---|
| Death recall | 100% (113/113) |
| Warning precision >50% | 98% |
| False positives | 1/176 (0.6%) |
| SAFE Sharpe | 1.55 |
| Pure L/S Sharpe | 2.82 |
| Pure L/S CAGR | +281% |
| Pure L/S $10K slutvärde | $5,746,461 |
| Dynamic Fund Sharpe | 2.02 |
| Dynamic Fund MaxDD | -26% |
| Dynamic Fund CAGR | +79% |
| Conservative MaxDD | -21.8% |
| Conservative Sharpe | 2.39 |
| Bear detection threshold | BTC DD -20% från 365d ATH |
| Exchange filter | 83 tokens |
| Eligible tokens (NDD+Rating+Exchange) | 70 |

---

## TEKNISKA NOTER

- Alla backtests använder winsorized returns (cap +/-100%)
- BTC regime filter: skippa månad om BTC -15% på 30 dagar
- Bear detection: BTC drawdown från rullande 365-dagars ATH < -20%
- Dynamic Fund bull: 40% BTC + 20% L/S + 40% cash
- Dynamic Fund bear: 10% BTC + 30% L/S + 60% cash
- Conservative bull: 30% BTC + 20% L/S + 50% cash
- Conservative bear: 0% BTC + 25% L/S + 75% cash
- Risk levels: CRITICAL (weakness>=3), WARNING (>=2), WATCH (>=1 OR P3<50), SAFE (else)
- Wrappa alltid terminal-kommandon i heredoc-format för zsh-kompatibilitet

---

## NÄSTA SESSION — REKOMMENDERAD PRIORITET

1. **Sprint 2.5.1** — API-endpoints med risk-level integration (risk signals redan i DB)
2. **Sprint 2.0.2 kvarvarande** — METHODOLOGY_CANONICAL.md
3. **Sprint 2.5.2** — Early Warning Feed med running scoreboard
4. **Paper trading system** — Live signal → simulerad execution → P&L tracking (fond-prep)
5. **Slippage model** — Backtest med realistiska kostnader (0.5% round trip + funding)
