# Maintainer Signal Research — Historical Analysis (Free Sources Only)

**Date:** 2026-04-14
**Method:** GitHub REST API (free, 5000 req/hr), no BigQuery/GCP
**Data:** 11 incident repos, 30 control repos, pre-incident commit history

---

## Executive Summary

**Hypotes:** Maintainer-aktivitet före supply-chain-incidents skiljer sig mätbart från normala paket.

**Resultat: SIGNAL FINNS — men svag och begränsad av sample size.**

Starkaste signaler (pre-incident 6-månaders-fönster):

| Signal | Incident | Control | Ratio | Tolkning |
|---|---:|---:|---:|---|
| Unika authors (6 mån) | **0.8** | **4.3** | **0.19x** | Incident-repos har 5x färre aktiva contributors |
| Nya authors (6 mån) | 0.6 | 3.5 | 0.18x | Incident-repos attraherar inte nya contributors |
| Total contributors | 23 | 50 | 0.46x | Mindre community |
| Commit frequency change | 2.2x | 1.2x | 1.81x | Incident-repos har mer volatil aktivitet |

**Begränsningar:** n=11 incidents (n=6 med >0 pre-incident commits). Kontroll-gruppen är inte perfekt matchad (kontroller tenderar vara större). Ingen p-värdes-beräkning meningsfull vid n=11.

---

## Metod

### Data-källor (alla gratis)

| Källa | Vad | Kostnad |
|---|---|---|
| GitHub REST API | Commit-historik med `until` parameter | Gratis (5000 req/hr) |
| GitHub REST API | Contributor-lista | Gratis |
| Manuellt kuraterad lista | 11 incidents med datum | Gratis |

**Ingen BigQuery/GCP använd.** GitHub REST API:s `commits?until=<date>&since=<date>` returnerar historisk commit-data — detta var nyckeln som möjliggjorde analysen utan betaltjänster.

### Design

**Pre-incident-fönster:** 6 månader FÖRE publikt incident-datum.
**Baseline-fönster:** 6 månader FÖRE pre-incident-fönstret (12-6 mån innan incident).
**Kontroll-referensdatum:** 2024-06-01 (fast datum för alla kontroller).

### Incident-repos med data

| Repo | Incident-typ | Pre-commits | Baseline-commits |
|---|---|---:|---:|
| event-stream | Account transfer | **16** | 0 |
| node-ipc | Protestware | 3 | 50 |
| codecov-bash | CI compromise | 160 | 100 |
| set-value | Vulnerability | 18 | 1 |
| colors.js | Insider sabotage | 0 | 0 |
| coa | Account compromise | 0 | 0 |
| rc | Account compromise | 0 | 0 |
| shell-quote | Vulnerability | 0 | 2 |
| minimist | Vulnerability | 0 | 0 |
| pac-resolver | Vulnerability | 0 | 0 |
| glob-parent | Vulnerability | 0 | 0 |

**6 av 11 incident-repos har 0 commits i båda fönstren** — de var redan inaktiva innan incidenten. Detta ÄR en signal (inaktivitet = risk), men det gör feature-extraction meningslös för dessa.

---

## Resultat

### Features med signal (effect size > 0.3x)

| Feature | Incident (n=11) | Control (n=30) | Ratio | Direction |
|---|---:|---:|---:|---|
| **pre_unique_authors** | **0.82** | **4.30** | **0.19x** | Incident = färre authors |
| **new_authors_in_pre** | 0.64 | 3.47 | 0.18x | Incident = inga nya contributors |
| **total_contributors** | 23.2 | 50.4 | 0.46x | Incident = mindre community |
| **baseline_unique_authors** | 1.55 | 3.07 | 0.50x | Redan färre innan |
| commit_frequency_change | 2.24 | 1.24 | 1.81x | Incident = mer volatil |
| lost_authors_in_pre | 1.09 | 2.23 | 0.49x | Incident = färre att förlora |

### Features UTAN signal

| Feature | Incident | Control | Ratio | Tolkning |
|---|---:|---:|---:|---|
| original_maintainer_active_pre | 0.18 | 0.17 | 1.09x | Ingen skillnad |
| top_author_pct_pre | 0.36 | 0.35 | 1.02x | Ingen skillnad |
| bus_factor_pct | 0.70 | 0.67 | 1.04x | Ingen skillnad |

**Överraskande: `original_maintainer_disappeared` och `top_author_pct` visar INGEN signal.** Den förväntade "maintainer byttes ut" signalen syns INTE i datan. Anledningen: de flesta incidents (6/11) var i redan-inaktiva repos där maintainern inte var aktiv att börja med.

### event-stream — detaljerad fallstudie

event-stream-incidenten (Nov 2018) visar den starkaste signalen:
- **Pre-incident:** 16 commits, alla av `right9ctrl` (INTE original maintainer `dominictarr`)
- **Baseline:** 0 commits (dormant repo)
- **Signal:** En ny, okänd contributor (`right9ctrl`) tog FULLSTÄNDIGT ägarskap under 6 månader

**Hade vi kunnat detektera det?** Ja — "ny contributor med 100% av commits i en period, på ett tidigare dormant repo" är en stark binär signal. Men det gäller bara 1 av 11 incidents.

---

## Tolkning

### Vad signalen egentligen säger

Den starkaste signalen (`pre_unique_authors = 0.19x`) säger: **repos som drabbas av supply-chain-incidents tenderar att ha mycket få aktiva contributors.** Detta är konsistent med "single-maintainer-risk" hypotesen — paket med lite community-stöd är mer sårbara.

Men detta är INTE en prediktiv signal i praktisk mening:
- Tusentals npm-paket har 0-1 aktiva contributors utan att drabbas av incidents
- Falsk-positiv-rate vid deployment skulle vara >99%
- Signalen säger "detta SKULLE KUNNA drabbas" men inte "detta KOMMER drabbas"

### Skillnad från ZARQ crypto

ZARQ:s SWF fungerar eftersom:
1. Crypto-krascher har KONTINUERLIGA mätbara förvarnare (pris, volym, BTC-korrelation)
2. "Krasch" är entydigt definierad (>30% prisfall)
3. Universe är begränsat (207 tokens med fullständig data)

npm supply-chain-attacker saknar alla tre:
1. Förvarnare är DISKRETA och sällsynta (maintainer-byte = enstaka event, inte trend)
2. "Attack" definieras post-hoc (man vet det bara efter publicering)
3. Universe är enormt (528K paket)

---

## Slutsats

### Kan vi göra rigorös maintainer-signal-analys med gratis källor?

**Delvis ja.** GitHub REST API räcker för att hämta historisk commit-data. Men:

1. **Incident-sample är för litet** (n=11, varav 6 med 0 commits). Behöver 30+ incidents med aktiv pre-incident-historik.
2. **Kontroll-gruppen är inte perfekt matchad.** Kontroller tenderar vara större/mer aktiva.
3. **Signalen som finns (`pre_unique_authors`) är för bred.** Den flaggar alla low-contributor-repos, inte specifikt de som kommer att attackeras.

### Rekommendation

**Stäng inte frågan helt — men nedprioritera.**

Den enda actionable insikten just nu: **inkludera "antal aktiva contributors senaste 6 mån" som en trust-score-dimension.** Detta kräver:
- GitHub API-anrop per entity (1 request per entity, 5000/hr)
- Integration i trust_score_v3.py
- Inte en prediktiv modell — bara en deskriptiv risk-faktor

Att bygga en PREDIKTIV modell (à la ZARQ SWF) för npm supply-chain kräver:
- 30+ incidents med detaljerad pre-incident GitHub-data
- Matchad kontroll-grupp
- Betydligt mer avancerad feature-engineering (code-diff-analys, dependency-graph)
- Detta är ett multi-månaders forskningsprojekt, inte veckor

---

## Data exporterad

| Fil | Innehåll |
|---|---|
| `~/Desktop/April/maintainer-signal-historical.json` | Full feature-data (11 incidents + 30 controls) |
| `~/Desktop/April/maintainer-signal-historical.csv` | Tabular feature-matris |
