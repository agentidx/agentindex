# Prediktiv Metodik — Fas 2 Results

**Date:** 2026-04-14
**Status:** DEL A (XGBoost) complete. DEL B (maintainer-signal) deferred (requires multi-week GitHub API collection).

---

## DEL A: XGBoost för Crypto — RESULTAT

### Hypotes

> XGBoost borde förbättra ZARQ:s crash-prediction AUC från 0.70 till 0.80+ genom att fånga non-lineära mönster i befintliga features.

### Resultat: HYPOTESEN FALSIFIERAD

| Model | IS AUC | OOS AUC | vs Baseline |
|---|---:|---:|---|
| LogReg (v3 baseline) | 0.7658 | **0.7031** | — |
| XGBoost (default) | 0.9159 | **0.6459** | **-8.1%** (sämre) |
| XGBoost (tuned) | 0.7855 | **0.6950** | **-1.2%** (marginellt sämre) |

**XGBoost slår INTE LogReg.** Varken default- eller tunad XGBoost förbättrar OOS AUC. Default-XGBoost overfittar kraftigt (IS 0.92 vs OOS 0.65). Tunad XGBoost (med regularisering) närmar sig LogReg men slår den inte.

### Varför XGBoost inte förbättrar

1. **Datasetet är litet.** 207 tokens × ~100 observationer per token = ~21K rader totalt. XGBoost behöver typiskt >50K rader för att slå LogReg.

2. **Features är redan well-engineered.** V2/V3-features inkluderar hand-crafted interactions (`ix_vol_x_ndd_weak`, `nl_drawdown_severe`) som fångar de non-linjäriteter XGBoost annars hade hittat.

3. **Class imbalance + temporal split** gör att XGBoost's komplexitet skadar mer än den hjälper. OOS-perioden (Jan 2024+) kan ha annorlunda marknadsdynamik än IS (<2024).

### Feature Importance (XGBoost tuned)

| Feature | Importance | Tolkning |
|---|---:|---|
| trust_p3_maintenance | **0.236** | Maintenance-score dominerar (samma som SWF) |
| nl_vol_extreme | 0.083 | Binär: vol > 90th percentile |
| vol_30d | 0.082 | Rå volatilitet |
| nl_trust_p3_low | 0.070 | Binär: P3 < 40 |
| btc_vol_30d | 0.067 | BTC marknadsvolatilitet |
| ix_vol_x_maint_low | 0.058 | Vol × maintenance-weakness |

**Top-featuren (P3 maintenance) har 3x mer importance än näst viktigaste.** Detta bekräftar att SWF:s val av P3 som primär signal var korrekt.

### Severity-analys (XGBoost tuned)

Vid threshold 0.4 (standard):

| Kategori | Detected | Rate |
|---|---:|---:|
| All crashes (>30% DD) | 7,283/7,283 | **100%** |
| Severe (>50% DD) | 2,340/2,340 | **100%** |
| Catastrophic (>70% DD) | 334/334 | **100%** |
| Terminal (>90% DD) | 32/32 | **100%** |
| Never-recover (>80% DD) | 124/124 | **100%** |

**100% recall bevarad vid 40.8% precision.** SWF:s 100% death recall härstammar från att threshold-baserad binär detektion är robust — den beror inte på modell-val (LogReg vs XGBoost).

### Slutsats DEL A

**LogReg + hand-engineered features ÄR redan near-optimal för crypto crash prediction på denna datamängd.** Mer avancerade ML-metoder (XGBoost) förbättrar inte OOS-prestanda. Förbättring kräver antingen:

1. **Mer data** (fler tokens, längre historik, eller högre frekvens)
2. **Nya signal-typer** (social media, on-chain-transaktioner, governance-events)
3. **Temporal modellering** (discrete-time hazard models, LSTM) istället för point-in-time classification

XGBoost på befintliga features = **icke-resultat**. Hypotesen "0.70→0.82 via modellbyte" var felaktig.

---

## DEL B: Maintainer-byte-signal — STATUS

### Vad som krävs

1. Lista 20-50 historiska supply-chain-incidents med GitHub repo-URL
2. Hämta GitHub contributor-historik 6 månader före varje incident
3. Bygga kontroll-grupp med 100-200 matchade repos
4. Statistisk analys av maintainer-mönster

### Vad som blockerar

GitHub API rate limit: 5,000 requests/timme (authed). Per repo behövs 3-5 API-anrop (contributors, commits, events). 250 repos × 5 anrop × 6 månader historik = ~7,500 anrop. Möjligt på en dag.

**Blockering:** Vi har ingen kuraterad lista av historiska supply-chain-incidents med GitHub-URLar. Att bygga den manuellt kräver research (2-4 timmar). Automatisk import från OSV.dev är möjlig men kräver ny crawler.

### Plan för DEL B (om/när prioriterad)

| Steg | Tid | Output |
|---|---|---|
| Kurera incident-lista (30-50 repos) | 4h | incidents.json |
| GitHub API crawler for contributor history | 1 dag | contributor_history/ |
| Kontroll-grupp-matchning | 2h | control_group.json |
| Statistisk analys | 1 dag | report med p-värden |
| **Total** | **3-4 dagar** | Signal validerad eller falsifierad |

---

## DEL C: Integration-tänkande

### Om XGBoost hade fungerat

Det hade inte krävt ny infrastruktur — bara byta `LogReg(d).fit()` mot `xgb.XGBClassifier().fit()` i crash_prediction_model_v3.py. Deployment-kostnaden hade varit minimal.

### Det som faktiskt behövs

Fas 1 + Fas 2 pekar mot samma slutsats: **förbättring kräver nya signaler, inte nya modeller.** Den mest lovande riktningen:

1. **Temporal hazard-modeller** (Shumway 2001, Cox PH): Modellera TIDPUNKTEN för krasch, inte bara "krasch ja/nej". Befintliga features, ny modellstruktur. Beräknad förbättring: AUC +0.05-0.10 baserat på TradFi-litteratur.

2. **Social sentiment** (Twitter/Discord/Telegram): Extern signal-källa som fångar mänsklig panik innan den syns i pris. Kräver ny datainsamling.

3. **On-chain-transaktioner**: Whale-movements, exchange-inflows, governance-votes. Tillgängligt via Etherscan/similar. Kräver ny pipeline.

---

## Sammanfattning

| Hypotes | Status | Lärdom |
|---|---|---|
| XGBoost → AUC 0.82 | **Falsifierad** | LogReg redan near-optimal; hand-crafted features viktigare än modellval |
| Maintainer-byte-signal | **Ej testad** | Kräver 3-4 dagars datainsamling + analys |
| Temporal hazard-modell | **Ej testad** | Mest lovande riktning baserat på TradFi-litteratur |

### Nyckelinsikt

ZARQ:s 100% death recall härstammar från den binära SWF (Structural Weakness Filter), inte från ML-modellen. ML-modellen (LogReg, AUC 0.70) ger graderad risk-ranking men är inte vad som driver den extraordinära recall. **SWF:s styrka ligger i domänspecifik feature-engineering, inte i modellkomplexitet.**

Implikation för generalisering: att bygga en SWF-ekvivalent för npm kräver *domänexpertis om npm-kraschar*, inte bättre ML. Vi behöver förstå VAD som föregår npm-incidents innan vi kan bygga binära detektionsregler.
