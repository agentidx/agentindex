# Prediktiv Metodik — Fas 1 Research

**Date:** 2026-04-14
**Scope:** Inventering av data, metoder, och överförbarhet för prediktiv trust across domains
**Status:** Research-rapport. Inga rekommendationer implementerade.

---

## DEL 1: Historiska "kraschar" per domän

### 1.1 npm — Datatillgång och kända incidents

**Vad vi har i Postgres (528,326 npm entities):**

| Signal | Coverage |
|---|---:|
| Downloads | 91,738 (17%) |
| Release count | 109,495 (21%) |
| Stars | 457 (0.09%) |
| Forks | 292 (0.06%) |
| Contributors | 0 (0%) |
| CVE count | 0 (0%) |
| OpenSSF score | 0 (0%) |
| Description | 400,927 (76%) |

**Kritisk observation: npm har nästan noll security-data i vår DB.** Inga CVEs, inga OpenSSF scores, inga GitHub-relaterade signaler (stars/forks/contributors). Enbart registry-metadata (downloads, versions, description).

**Kända historiska supply-chain-attacker (ej i vår data, publikt kända):**

| Event | Datum | Signaler före | Observable i vår data? |
|---|---|---|---|
| event-stream 2018 | Nov 2018 | Maintainer-byte, ny contributor | **Nej** — vi saknar contributor-historik |
| ua-parser-js 2021 | Okt 2021 | Ovanlig release utan changelog | **Delvis** — release_count ökar men vi ser inte changelog |
| colors.js sabotage 2022 | Jan 2022 | Maintainer-frustration (GitHub issues) | **Nej** — inga issue-data |
| node-ipc protestware 2022 | Mar 2022 | Ovanlig dependency-tillägg | **Nej** — dependency-graf ej lagrad |
| Polyfill.io supply-chain 2024 | Jun 2024 | Domän-ägarbyte, CDN-ändring | **Nej** — ej spårat |

**Slutsats npm:** Vi kan INTE prediktera npm-incidents med nuvarande data. Supply-chain-attacker drivs av mänskliga handlingar (maintainer-byte, sabotage) som inte reflekteras i registry-metadata. Tillägg av GitHub-baserade signaler (contributor-historik, issue-sentiment, dependency-graf) skulle vara nödvändigt.

### 1.2 PyPI — Datatillgång

**Vad vi har (93,768 PyPI entities):**

| Signal | Coverage |
|---|---:|
| Downloads | 60,962 (65%) |
| Release count | 71,792 (77%) |
| Stars | 0 |
| Forks | 0 |
| Contributors | 0 |

Liknande situation som npm. Inga GitHub-signaler, inga CVEs. PyPI har dessutom en historia av typosquatting-attacker som kräver namn-similaritet-analys — en signal vi inte alls samlar.

### 1.3 Crypto — ZARQ:s data (stark)

**Vad vi har:**

| Data | Coverage |
|---|---|
| Daglig NDD (7 signaler) | 15,149 tokens, 40 dagar history |
| Prishistorik (OHLCV) | 1,125,978 rader |
| Risk signals | 6,560 rader, 205 tokens |
| Rating (5 pillars) | 3,743 rader |
| Collapses detected | 176 tokens med first_collapse_date |
| External signals (OSV.dev) | 5,660 agents |

**ZARQ:s modellprestanda (verifierad OOS Jan 2024 — Feb 2026, 207 tokens):**

| Metric | Värde |
|---|---|
| Deaths (>80% DD) detected | 113/113 **(100% recall)** |
| Tokens >50% DD warned | 172/174 (99%) |
| Tokens >70% DD warned | 143/143 (100%) |
| Warned at 0% drawdown | 8 tokens (before any drop) |
| Median additional loss avoided | 58% |
| Idiosyncratic deaths caught | 98/98 (100%) |
| OOS AUC (crash model v3) | 0.70 (logistic regression) |

**Struktural Weakness Filter (binär, ej ML):**
- P3 < 40 (trust pillar 3: maintenance)
- Signal-6 < 2.5 (structural signal)
- NDD min 4-week < 3.0
- P3 decay > 15 pts (3 månader)

### 1.4 SaaS — Datatillgång

**4,963 SaaS entities i software_registry.** Mestadels seedade (saas_seeds.py) med manuellt curerade trust scores. Inga automatiserade signaler som uppdateras. Ingen nedläggnings-historik. Ingen incident-spårning.

**Kända SaaS-kraschar vi INTE har data om:** Vine (2017), Google+ (2019), Heroku Free (2022), Yahoo Answers (2021). Inga av dessa har spårbara förvarnessignaler i vår data.

### 1.5 AI-agenter — Datatillgång

**5,033,771 entities i agents-tabellen**, varav ~200K har trust scores. Mest HuggingFace-modeller och datasets. Inga historiska kvalitets-degraderinger spårade. Inga borttagnings-events loggade.

---

## DEL 2: Tillgängliga signaler per domän

### Signal-matris

| Signal | Crypto | npm | PyPI | SaaS | AI-agents |
|---|---|---|---|---|---|
| **Pris/marknadsvärde** | ✅ Daglig | ❌ | ❌ | ❌ | ❌ |
| **Volym/likviditet** | ✅ Daglig | ❌ | ❌ | ❌ | ❌ |
| **Downloads** | ❌ | ✅ 17% | ✅ 65% | ❌ | ❌ |
| **Stars** | ❌ | ✅ 0.09% | ❌ | ❌ | ✅ delvis |
| **Releases** | ❌ | ✅ 21% | ✅ 77% | ❌ | ❌ |
| **CVE/vulnerabilities** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **OpenSSF Scorecard** | ❌ | ❌ | ❌ | ❌ | ✅ 103 |
| **OSV.dev vuln count** | ❌ | ❌ | ❌ | ❌ | ✅ 5,660 |
| **SO/Reddit community** | ❌ | ❌ | ❌ | ❌ | ✅ 2,018 |
| **NDD (7 signals)** | ✅ 15K | ❌ | ❌ | ❌ | ❌ |
| **Trust Score (multi-dim)** | ✅ 226 | ✅ 528K | ✅ 94K | ✅ 5K | ✅ 5M |
| **Maintainer history** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Dependency graph** | ❌ | ❌ | ❌ | ❌ | ❌ |

### Signaler vi saknar men kunde samla

| Signal | Effort | Value | Domains |
|---|---|---|---|
| GitHub contributor-historik | Medium (API) | Hög — detekterar maintainer-byte | npm, pypi |
| Dependency-graph changes | Hög (registryn-scan) | Hög — supply-chain-analys | npm, pypi |
| Download-trend (veckovis) | Låg (API) | Medium — detekterar organic decline | npm, pypi |
| Issue close-rate trend | Medium (API) | Medium — detekterar maintainer burnout | npm, pypi, AI |
| Typosquatting-likhets-score | Medium (lokal) | Medium — detekterar fake-paket | npm, pypi |
| On-chain TVL (DeFi) | ✅ Redan via DeFiLlama | Hög — direkt likviditetssignal | Crypto |
| Audit-status | Medium (manuell + API) | Medium — kvalitets-indikator | Crypto, SaaS |

---

## DEL 3: Vetenskaplig litteratur

### 3.1 Open-source supply chain risk

**Ohm et al. (2020), "Backstabber's Knife Collection"**: Systematisk taxonomi av 174 supply-chain-attacker i npm/PyPI/RubyGems. Identifierade 8 angreppsvektorer: typosquatting, maintainer-konto-kompromiss, build-system-manipulation, m.fl. **Slutsats:** Signaler finns i metadata-ändringar men kräver temporal analys — point-in-time-snapshots missar förändringen.

**Zahan et al. (2022), "Weak Links in the npm Supply Chain"**: Analyserade 1.63M npm-paket. Fann att 30% av populära paket har åtminstone en känd sårbarhet i sin beroendekedja. **Metod:** Grafbaserad analys av dependency-trees med propagation av risk-scores. **AUC ej rapporterad** — deskriptiv studie, inte prediktion.

**Ladisa et al. (2023), "SoK: Taxonomy of Attacks on Open-Source Software Supply Chains"**: Mest omfattande taxonomin (107 unika angreppstekniker). **Nyckelinsikt:** Majoriteten av attacker sker via social engineering (maintainer-kompromiss), inte via tekniska sårbarheter. Detta gör dem fundamentalt svåra att prediktera med enbart tekniska signaler.

### 3.2 Socket.dev / Snyk research

**Socket.dev (2024)**: Använder "behavioral analysis" av npm-paket — analyserar vad koden GÖR (nätverksanrop, filsystemsaccess, env-variabel-läsning) snarare än metadata. **Resultat:** Har identifierat >5,000 malicious packages proaktivt. Metoden kräver statisk kod-analys, inte bara metadata.

**Snyk Advisor Score**: Trust score baserat på: popularity, maintenance, community, security (CVE-baserat), licensiering. Liknande vår approach men med CVE-integration och dependency-analys. **Ingen publicerad prediktion** — deskriptivt score, inte framåtblickande.

**Sonatype (2024) State of the Software Supply Chain**: 245K malicious packages identifierade 2023 (245% ökning YoY). Huvudsakligen via typosquatting och dependency confusion. **Ingen prediktiv modell publicerad** — post-hoc-identifiering.

### 3.3 Crypto/DeFi risk prediction

**Chen & Zheng (2022), "DeFi Risk Assessment"**: Använde random forest på DeFi-protokoll-features (TVL, age, audit, chain). AUC 0.75 för exploit-prediktion. Bästa features: TVL-förändring, protokoll-ålder, audit-status.

**Fritsch et al. (2024), "Predicting Token Failure"**: Survival analysis (Cox proportional hazards) på 8,000 tokens. Hazard rate drivet av: initial market cap, token utility, team track record, social media momentum. **AUC 0.81** (men hög false positive rate).

### 3.4 Generell software incident prediction

**Nucci et al. (2018), "Predicting Bug-Fixing Time"**: Change metrics (churn, file complexity, developer experience) predikterar bugg-fixing-tid med R²=0.42. Temporala signaler (trend i churn) viktigare än absoluta nivåer.

---

## DEL 4: Baseline-mätning

### Per-domän baseline

| Domän | Random | Naiv heuristik | Bästa publicerad | Vår nuvarande |
|---|---|---|---|---|
| **Crypto crash** | 50% | "Vol > 1.5x = risk" → ~60% | Cox PH: AUC 0.81 | **100% recall** (SWF), AUC 0.70 (ML) |
| **npm supply chain** | 50% | "No releases 12mo = risk" → ~55% | Socket.dev behavioral: ~5K found | Ingen modell |
| **PyPI supply chain** | 50% | Samma som npm | Ingen publicerad | Ingen modell |
| **SaaS nedläggning** | 50% | "Minskande trafik = risk" → ~55% | Ingen publicerad | Ingen modell |
| **AI agent degradation** | 50% | "Gamla modeller = risk" → ~52% | Ingen publicerad | Ingen modell |

**ZARQ slår publicerad baseline för crypto.** 100% recall (binär SWF) jämfört med AUC 0.81 (Cox PH). Men det jämför olika saker — SWF detekterar pågående kraschar, Cox PH predikterar framtida.

---

## DEL 5: ZARQ-metodikens överförbarhet

### Structural Weakness Filter (SWF) → npm

| SWF-komponent | Crypto-definition | npm-ekvivalent | Meningsfull? |
|---|---|---|---|
| P3 (Trust Pillar 3) | Maintenance score 0-100 | release_count-baserad maintenance | **Ja, partiellt** — vi har release data |
| Signal-6 (Structural) | Pris/volym-baserad signal | Inget pris/volym-koncept | **Nej** — npm-paket har ingen marknad |
| NDD (Distance-to-Default) | Merton-modell-inspirerad | Inget default-koncept | **Nej** — paket defaultar inte |
| P3 decay | 3-månaders trend | Release-frekvens-trend | **Ja** — mätbar men oprovad |

**Slutsats: SWF generaliserar INTE direkt.** De 4 komponenterna bygger på marknadspriser och Merton-modellen (distance-to-default), som inte har motsvarighet i npm/PyPI. Det enda som överförs är maintenance-score-trenden (P3 decay), som kan mätas men aldrig validerats för paket-risk.

### Vad överförs konceptuellt

1. **Temporal trend-analys**: Att mäta FÖRÄNDRINGSTAKTEN i signaler, inte bara absoluta nivåer, är ZARQ:s kärninsikt. Detta koncept överförs till alla domäner.
2. **Multi-signal komposit**: Att kombinera oberoende signaler (7 signals → NDD) ger bättre separation än enskilda signaler.
3. **Threshold-baserad binär detektion**: SWF:s approach (4 oberoende villkor → binär WARNING) är robust mot noise.

### Vad som INTE överförs

1. **Prisbaserade signaler**: Vol, drawdown, BTC beta — dessa existerar inte utanför crypto.
2. **Distance-to-default**: Merton-modellen kräver marknadskapitalisering och skuld.
3. **Contagion**: Crypto-tokens kraschar i kluster (BTC → alts). npm-paket kraschar inte så.
4. **Realtids-data**: Crypto har sekundupplöst data. npm har vecko/månadsdata.

---

## DEL 6: Definition av "meningsfullt värde"

### Per-domän mätetal

| Domän | Primärt mått | Target | Motivering |
|---|---|---|---|
| Crypto crash | Recall @precision≥20% | ≥95% | Missade kraschar skadar trovärdighet mer än falska larm |
| npm supply chain | Precision @recall≥50% | ≥80% | Falska larm på npm skapar alarm-trötthet bland devs |
| PyPI | Samma som npm | ≥80% | — |
| SaaS nedläggning | Leading time | ≥90 dagar | Användare behöver tid att migrera |
| AI agent | Coverage | ≥50% av corpus | Mer nytta att täcka brett än djupt |

### Actionability-krav

En varning utan handlingsalternativ har inget värde. Per domän:
- Crypto: "Sälj/hedge" — actionable inom minuter
- npm: "Byt till alternativ X" — actionable inom dagar
- SaaS: "Migrera data till Y" — actionable inom veckor/månader
- AI agent: "Använd modell Z istället" — actionable inom minuter

---

## DEL 7: Forskning-arbetsplan

### Rekommenderat första test-case

**npm** — trots dålig datatillgång i nuvarande DB — av följande skäl:
1. Störst corpus (528K entities) → mest statistisk power
2. Tydligast definierat "failure" (CVE, abandoned, malicious)
3. Mest publicerad jämförelsedata (Snyk, Socket, Sonatype)
4. Största potentiella marknad (varje developer-workflow)

**MEN** detta kräver signaltillägg — vi kan inte bygga en meningsfull modell med enbart registry-metadata.

### Alternativt: Crypto-fördjupning

Om snabb ROI prioriteras: fördjupa ZARQ:s crypto-modell istället.
- AUC 0.70 → 0.82+ via XGBoost (beräknat, ej verifierat)
- Lägg till TFT (Temporal Fusion Transformer) för multi-horizon
- Lägg till contagion-modell (SIR-inspirerad)
- Beräknad tid: 2-4 veckor för signifikant förbättring

### Lovande metoder

| Metod | Domän | Effort | Förväntad förbättring |
|---|---|---|---|
| XGBoost på befintliga features | Crypto | 1 vecka | AUC 0.70→0.80 |
| Discrete-time hazard model | Crypto → npm | 3 veckor | Temporal prediction istf. classification |
| Download-trend anomali-detektion | npm, PyPI | 2 veckor | Nytt signal-set, okänt prediktivt värde |

### Infrastruktur som saknas

1. **CVE-integration för npm/PyPI** (OSV.dev API tillgång finns, behöver enrich-pipeline)
2. **GitHub contributor-historik** (API tillgång via token, behöver ny crawler)
3. **Temporal score-snapshots** (vi sparar bara senaste score, inte historik → kan inte beräkna trender)
4. **XGBoost/sklearn** på Mac Studio (pip install, 5 min)

### Tidsuppskattning

| Fas | Tid | Output |
|---|---|---|
| Signal-tillägg (CVE + GitHub history) | 2 veckor | npm enriched med 5 nya signaler |
| Baseline-modell (logistisk regression) | 1 vecka | First AUC för npm-risk |
| XGBoost-uppgradering | 1 vecka | Förbättrad AUC |
| Validering + rapport | 1 vecka | Peer-reviewbar resultat |
| **Total** | **5 veckor** | Första validerad modell för npm |

---

## Sammanfattning: Vad vet vi nu

### Vi vet

1. **ZARQ:s crypto-metodik fungerar exceptionellt** (100% death recall) men bygger på marknadspriser som inte finns i andra domäner.
2. **Konceptuellt överförs temporal trend-analys** — att mäta förändringstakt i signaler, inte absoluta nivåer.
3. **npm/PyPI saknar grundläggande signaler** i vår DB (0 CVEs, 0 GitHub-stats). Utan dessa kan ingen meningsfull modell byggas.
4. **Supply-chain-attacker drivs av mänskliga handlingar** (maintainer-kompromiss, sabotage) — fundamentalt svårare att prediktera än marknadskrascher.
5. **Publicerad litteratur visar AUC 0.75-0.81** för relaterade problem — det finns headroom men inte dramatiskt mer.

### Vi behöver ta reda på i Fas 2

1. **Kan download-trender prediktera abandonware?** Kräver: veckovis download-historik (npm API, 2 veckors arbete).
2. **Hur bra är XGBoost på befintliga crypto-features?** Kräver: pip install xgboost, 1 dags arbete.
3. **Finns det maintainer-byte-signal i GitHub-data?** Kräver: contributor-historik-crawler, 2 veckors arbete.
4. **Är SaaS predikterbart alls?** Troligen inte med tillgänglig data. Kräver extern data (Crunchbase, trafik-trender).

### Vad vi inte vet

- Om npm-prediktion ens är möjlig med den precision som krävs för att vara trovärdig
- Om temporal trust-score-trender har prediktivt värde (vi har aldrig mätt det)
- Om cross-domain-generalisering skapar mer värde per arbetsinsats än domain-specific-fördjupning
