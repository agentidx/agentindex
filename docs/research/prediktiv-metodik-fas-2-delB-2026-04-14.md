# Prediktiv Metodik Fas 2 DEL B — Maintainer Signal Research

**Date:** 2026-04-14
**Status:** Complete — preliminary findings with significant methodological limitations

---

## Executive Summary

**Hypotes:** Maintainer-aktivitetsförändringar i GitHub-historik är detekterbara före supply-chain-incidents.

**Resultat: INKONKLUSIVT** — data visar starka skillnader mellan incident- och kontroll-repos, men de mäter KONSEKVENSER av incidenter (repos som slutade underhållas EFTER incident) snarare än FÖRVARNARE (signaler FÖRE incident).

**Kritisk begränsning:** 7 av 13 incident-repos är borttagna/privata på GitHub (53%). De som finns kvar (6 repos) har 0 commits senaste 12 månaderna — de är övergivna EFTER incidenten, inte data från FÖRE incidenten. Vi mäter alltså "hur ser ett dött repo ut" istället för "hur ser ett repo ut som är PÅ VÄG att dö."

---

## Metodologi

### Incident-repos (13 valda, 6 tillgängliga)

| Repo | Type | Status |
|---|---|---|
| dominictarr/event-stream | Account transfer | ✅ Data (0 commits 12m) |
| Marak/colors.js | Insider sabotage | ✅ Data (0 commits 12m) |
| RIAEvangelist/node-ipc | Protestware | ✅ Data (0 commits 12m) |
| codecov/codecov-bash | CI compromise | ✅ Data (0 commits 12m) |
| veged/coa | Account compromise | ✅ Data (0 commits 12m) |
| dominictarr/rc | Account compromise | ✅ Data (0 commits 12m) |
| nicsingh/ua-parser-js | Account compromise | ❌ Not found |
| Marak/faker.js | Insider sabotage | ❌ Not found |
| fiber/ctx | PyPI hijack | ❌ Not found |
| nicsingh/vm2 | Vulnerability chain | ❌ Not found |
| nicsingh/polyfill-service | Domain takeover | ❌ Not found |
| nicsingh/lottie-player | Account compromise | ❌ Not found |
| RIAEvangelist/peacenotwar | Protestware | ❌ Not found |

**53% data loss.** Borttagna repos kan inte analyseras retroaktivt.

### Kontroll-repos (33 valda, 31 tillgängliga)

Well-maintained, popular npm packages (Express, React, Vue, Angular, Lodash, etc.). Alla aktiva, inga kända säkerhetsincidenter.

---

## Feature-jämförelse

| Feature | Incident (n=6) | Control (n=31) | Ratio | Tolkning |
|---|---:|---:|---:|---|
| stars | 1,470 | 59,253 | **0.02x** | Incident-repos är 50x mindre populära |
| forks | 146 | 8,885 | **0.02x** | Samma mönster |
| archived | 33% | 0% | **∞** | 1/3 av incident-repos är arkiverade |
| num_contributors | 31 | 50 | 0.63x | Något färre contributors |
| **top_contributor_pct** | **62%** | **39%** | **1.58x** | **Incident-repos har mer koncentrerat ägarskap** |
| bus_factor | 1.67 | 2.23 | 0.75x | Lägre bus factor (fler beroende av 1 person) |
| total_commits_12m | **0** | 73 | **0x** | **Alla incident-repos har 0 commits senaste året** |
| unique_authors_12m | **0** | 15 | **0x** | **Noll aktivitet** |
| commits_per_month | 0 | 36 | 0x | Noll |
| new_author_commit_ratio | 0 | 0.43 | 0x | Inga nya authors (alla döda) |

---

## Kritisk analys

### Vad vi INTE mäter

**Vi mäter post-incident-tillstånd, inte pre-incident-signaler.** Alla 6 incident-repos har 0 commits senaste 12 månaderna. Incidenterna hände 2018-2022 — repos har varit döda i 2-6 år. Datan säger "döda repos har noll aktivitet" (trivialt), inte "repos som snart får en incident visar dessa mönster" (meningsfullt).

### Vad som HADE behövts

1. **Historisk GitHub-data FRÅN TIDEN FÖRE incidenten.** GitHub API returnerar bara NUVARANDE tillstånd. För retroaktiv analys behövs antingen:
   - GitHub Archive (GH Archive) dataset med historiska events
   - Libraries.io dataset med paket-metadata-historik
   - Egen historisk datainsamling (som vi inte hade)

2. **Matchad kontroll-grupp.** Våra kontroller (React, Express, etc.) är 50x större. En fair jämförelse kräver paket av samma storlek/popularitet.

### Den enda potentiellt användbara signalen

**`top_contributor_pct = 62% vs 39%` (1.58x ratio).**

Incident-repos har mer koncentrerat ägarskap — en enda person äger ~62% av commits vs 39% i kontroller. Detta är konsistent med supply-chain-risk-litteraturen: "single-maintainer-risk" är en känd riskfaktor. Men med n=6 är detta inte statistiskt signifikant.

---

## Slutsats

### Hypotesen är VARKEN BEVISAD ELLER FALSIFIERAD

Vi kan inte dra meningsfulla slutsatser om maintainer-signaler som FÖRVARNARE från denna data. Anledningen:

1. **53% av incident-repos saknas** (borttagna/privata)
2. **Kvarvarande repos visar POST-incident-tillstånd** (alla döda i 2-6 år)
3. **Kontroll-gruppen är missmatchad** (50x skillnad i popularitet)
4. **n=6 incident-repos är statistiskt otillräckligt** för modellträning

### Vad som krävs för en rigorös studie

| Krav | Ansats | Effort |
|---|---|---|
| Historisk GitHub-data | GH Archive BigQuery dataset | 1-2 dagar BigQuery |
| Fler incidents | Libraries.io + Sonatype reports | 1-2 dagars research |
| Matchad kontroll-grupp | Propensity-score-matchning | 1 dag |
| Pre-incident-tidsfönster | 6 månader FÖRE varje incident | Kräver historisk data |
| Statistisk power | n≥30 incidents | Kräver bredare definition av "incident" |

**Total: 4-5 dagar ytterligare arbete med tillgång till GH Archive.**

### Implikation för Nerq-strategin

Maintainer-signaler är SANNOLIKT prediktiva (det finns stark teoretisk grund och publicerad litteratur som stöder det), men vi kan inte BEVISA det med de data vi har idag. Den mest lovande vägen:

1. **Använda `top_contributor_pct` som risk-faktor NU** (obs: inte binär signal, utan kontinuerlig risk-dimension). Bus factor / single-maintainer-risk är etablerad i litteraturen.
2. **Investera i GH Archive-baserad studie** om rigorös validering krävs.
3. **Alternativt: fokusera på real-time-detektering** (package-version-diff-analys vid publicering) istället för historisk prediktion.

---

## Data exporterad

| Fil | Innehåll |
|---|---|
| `~/Desktop/April/maintainer-signal-features.csv` | Feature-matris (6 incident + 31 control repos) |
| `data/maintainer-research/maintainer_signal_results.json` | Full resultat med statistik |
