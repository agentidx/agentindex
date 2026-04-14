# Transformation Mechanisms Scoping — 2026-04-14

---

## DEL 1: Cascade-modellering

### 1.1 Nuläge — vad vi har

**Dependency-data:**

| Registry | Entities | Has dep count | Avg deps | Full graph? |
|---|---:|---:|---:|---|
| npm | 528,326 | 82,690 (16%) | 6.7 | **Nej** — bara count, ej vilka deps |
| pypi | 93,768 | 58,777 (63%) | 7.8 | **Nej** — bara count |
| crates | 204,080 | 0 | — | Nej |
| go | 22,095 | 0 | — | Nej |

**Vi har dependencies_count men INTE dependency-GRAFEN.** Vi vet att express har 30 dependencies, men inte vilka 30. Utan grafen kan vi inte göra cascade-modellering.

**Crypto cascade — redan byggt:**
- `contagion_engine_v1_1.py` — korrelationsnätverk + tier-baserad stress-propagation
- `propagated_risk_engine.py` — scenario-baserad risk med hop dampening (0.65 per hop)
- 5 fördefinierade scenarier (BTC crash, stablecoin depeg, exchange failure, etc.)

Dessa fungerar för crypto (där "dependency" = priskorrelation). Men konceptet kräver ny implementation för npm/pypi (där dependency = importgraf).

### 1.2 Vad som behövs

**För att bygga npm cascade:**
1. **Dependency-graf-data.** Hämta `package.json` dependencies per paket. npm registry API returnerar detta. ~528K API-anrop (med 5000/hr = 106 timmar = 4.4 dagar). ELLER batch-download av npm registry replika.
2. **Graf-lagring.** ~528K noder, ~3.5M kanter (528K × 6.7 avg deps). Postgres adjacency list eller Neo4j/DGraph.
3. **Propagation-algoritm.** Threshold model: om ett paket med score < 40 har X dependents, propagera risk-signal till dependents. Enklare än PageRank, mer tolkningsbar.

### 1.3 Frågor som kan besvaras

| Fråga | Vem frågar | Idag tillgängligt? |
|---|---|---|
| "Om express har CVE, vilka paket påverkas?" | Developers, security teams | **Nej** (npm audit gör delvis, Socket.dev) |
| "Vilka är bridge-packages?" | Security researchers | **Nej** (publicerade i akademiska papers) |
| "Hur central är mitt paket?" | Maintainers | **Nej** (centrality-metrics inte publika) |
| "Cascade-risk för min dependency-stack" | DevOps, CI/CD | **Delvis** (Snyk, npm audit) |

### 1.4 Implementation-estimat

| Steg | Tid | Blockerar |
|---|---|---|
| npm dependency-graf datainsamling | 5 dagar | npm API rate limits |
| Graf-lagring i Postgres | 1 dag | — |
| Propagation-algoritm | 2 dagar | — |
| API-endpoint `/v1/cascade/{package}` | 1 dag | — |
| **Total MVP** | **~9 dagar** | Data-insamling |

---

## DEL 2: Komposit-insikter

### 2.1 Nuläge — integrerade källor

| Källa | Coverage | Data | Uppdatering |
|---|---:|---|---|
| OSV.dev | 5,660 agents | Vuln count, max severity, exploits | Via snyk_crossref.py, periodisk |
| OpenSSF Scorecard | 103 agents | 14 check-scores (0-10) | Via openssf_scorecard.py, periodisk |
| Reddit | 2,018 agents | Mentions (30d) | Via community_signals.py |
| Stack Overflow | 2,018 agents | Question count | Via community_signals.py |
| Registry metadata | 2.47M entities | Downloads, stars, versions, license | Via crawlers, daglig |

### 2.2 Källor att integrera (gratis, utan API-key)

| Källa | Vad | Effort | Coverage boost |
|---|---|---|---|
| **npm audit data** | Known vulns per package | Medium (npm API) | 528K → CVE-data för npm |
| **PyPI safety DB** | Known malicious packages | Låg (pip-audit API) | 94K → säkerhets-data |
| **GitHub Dependabot alerts** | CVEs i dependencies | Medium (API) | Repos med alerts |
| **npm deprecation** | Deprecated packages | Låg (npm API metadata) | 528K |
| **License compatibility** | SPDX analysis | Låg (lokal beräkning) | Alla med license-fält |

### 2.3 Aggregations-metodik

**Nuvarande approach:** Viktad summa av 5 dimensioner (Security 25%, Maintenance 20%, Popularity 20%, Community 15%, Quality 20%).

**Komposit-förbättring:** Lägg till **External Validation** dimension (redan i trust_score_v3.py men bara för 103 entities):

```
Komposit = base_score × 0.85 + external_validation × 0.15

external_validation = weighted_mean(
    osv_clean_bonus,      # +10 if 0 vulns, -20 if >5
    openssf_score × 10,   # 0-100 scale
    community_momentum,   # SO + Reddit signals
    deprecation_penalty,  # -30 if deprecated
)
```

### 2.4 Unikt värde

**Vad gör kompositen värdefull vs att kolla själv?**
1. **Tidsbesparning:** En developer kollar inte OSV + OpenSSF + npm audit + Reddit för varje paket
2. **Normalisering:** Scores är jämförbara tvärs registries (en npm-A ≈ en pypi-A)
3. **Trend-signal:** Komposit inkluderar temporal förändring som enskilda källor inte visar

**Redan existerande konkurrenter:** Snyk Advisor, Socket.dev score, npm audit. Vår edge: multi-registry coverage (26 registries) och AI-first-distribution (ChatGPT citerar oss).

### 2.5 Implementation-estimat

| Steg | Tid |
|---|---|
| npm audit integration (CVE per package) | 3 dagar |
| Deprecation-flag integration | 1 dag |
| trust_score_v3 activation för alla entities | 2 dagar |
| External validation dimension populated | 2 dagar |
| **Total MVP** | **~8 dagar** |

---

## DEL 3: Emergent mönster-upptäckt

### 3.1 Vilken query-data har vi?

| Dataset | Rows | Unique entities | Period |
|---|---:|---:|---|
| preflight_analytics | 127,901 | 45,638 | 30 dagar |
| requests (user_triggered) | ~35,000 | ~5,000 | 30 dagar |
| requests (search_index) | ~20M | ~500K | 30 dagar |

**Preflight (MCP):** 45,638 unika entities frågade. Top: express (111), react (78), tiktok (62), nordvpn (46), bitcoin (43). Stark signal om vad AI-agenter bryr sig om.

**Geografisk fördelning:** US 69%, SG 11%, FR 3%, RU 2%. Singapore-trafiken är sannolikt Alibaba scraper (klassificerad sedan Apr 12).

### 3.2 Insikter att extrahera

| Insikt | Data-källa | Effort | Värde |
|---|---|---|---|
| **Trending entities (24h/7d)** | preflight + user_triggered | Låg | Hög — visar vad AI-ekosystemet bryr sig om just nu |
| **Query correlations** | preflight co-occurrences | Medium | Medium — "folk som kollar X kollar också Y" |
| **New entity discovery** | preflight for unknown entities | Låg | Medium — visar efterfrågan vi inte täcker |
| **Anomaly detection** | Preflight spike detection | Låg | Hög — kan indikera pågående incident |
| **Geographic interest map** | preflight × country | Låg | Låg-Medium — nisch |

### 3.3 Trending-implementation

**Enklast möjliga MVP:**
```sql
-- Trending entities (24h vs 7d baseline)
SELECT target, 
  COUNT(*) FILTER (WHERE ts >= now() - interval '24h') as last_24h,
  COUNT(*) FILTER (WHERE ts >= now() - interval '7d') / 7.0 as daily_avg_7d,
  COUNT(*) FILTER (WHERE ts >= now() - interval '24h') / 
    NULLIF(COUNT(*) FILTER (WHERE ts >= now() - interval '7d') / 7.0, 0) as trend_ratio
FROM preflight_analytics
WHERE ts >= now() - interval '7d'
GROUP BY target HAVING COUNT(*) >= 5
ORDER BY trend_ratio DESC LIMIT 20;
```

**API endpoint:** `/v1/trending` — returnerar top 20 trending entities.
**MCP tool:** `nerq_trending` — agenter frågar "vad är hett just nu?"

### 3.4 Differentiering

**Befintliga trending-tjänster:** GitHub Trending, npm trending, HackerNews. Ingen av dem visar trending **baserat på AI-agent-queries**. Vår data visar vad AI-ekosystemet (ChatGPT, Claude, Perplexity) bryr sig om — det är unikt.

### 3.5 Implementation-estimat

| Steg | Tid |
|---|---|
| Trending query + API endpoint | 1 dag |
| MCP tool `nerq_trending` | 0.5 dag |
| Dashboard-panel på citation-dashboard | 0.5 dag |
| Anomaly detection (spike alert) | 1 dag |
| **Total MVP** | **~3 dagar** |

---

## DEL 4: Jämförande analys

### 4.1 Rangordning

| Kriterium | Cascade | Komposit | Emergent |
|---|---|---|---|
| **Genomförbarhet (4 veckor)** | ⚠️ 9 dagar + data (tight) | ✅ 8 dagar | ✅ **3 dagar** |
| **Värde för användare** | Hög (unik insight) | Medium (refinement av befintligt) | **Hög** (unik AI-trending) |
| **Unikhet** | Medium (npm audit, Socket finns) | Låg (Snyk Advisor liknande) | **Hög** (ingen annan har AI-query-trending) |
| **Synergi med Nerq** | Hög (förstärker trust score) | Hög (förbättrar befintlig score) | **Hög** (driver trafik + citations) |
| **Datakrav** | ❌ Saknar dependency-graf | ⚠️ Behöver npm audit-integration | ✅ **Data finns redan** |

### 4.2 Rekommendation

**Bygg i denna ordning:**

1. **Emergent mönster först (3 dagar).** Data finns redan. Unikt värde. Trending-API + MCP-tool kan vara live inom veckan. Direkt mätbar via ChatGPT-User-queries (om agenter börjar fråga om trending → bevisar värdet).

2. **Komposit-insikter sedan (8 dagar).** Förbättrar befintlig trust score med extern validering. npm audit-integration ger CVE-data för 528K paket. Synlig förbättring av score-kvalitet.

3. **Cascade sist (9+ dagar).** Kräver dependency-graf som inte finns. Mest arbete, mest data-insamling. Men unikt värde när det är klart — ingen annan visar cascade-risk i realtid tvärs registries.

### 4.3 Kombinations-effekt

**Trending + Cascade:** "express trendar 3x idag — och det har 4,521 downstream dependents. Om express har en CVE → 4,521 paket påverkas."

**Trending + Komposit:** "langchain trendar 5x — och dess komposit-score sjönk från 82 till 74 senaste veckan (ny CVE + maintainer-inaktivitet)."

**Cascade + Komposit:** "paket X har composite score 45 OCH 1,200 dependents. Cascade-risk: HIGH."

Alla tre förstärker varandra. Men bygga i ordning (1→2→3) ger snabbast ROI.
