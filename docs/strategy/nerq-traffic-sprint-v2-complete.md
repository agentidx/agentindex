# Nerq Traffic Sprint v2 — Komplett plan
## Alla 🟢-klassificerade initiativ + språkexpansion till 50 språk
### April 5, 2026

---

## Princip

Varje åtgärd i denna plan ADDERAR utan att ändra befintligt content. Ingen åtgärd rör pplx-verdict, ai-summary, eller SpeakableSpecification. Allt som driver 200K+ AI-citations/dag bevaras intakt.

---

## Nuläge

| Metric | Värde |
|---|---|
| AI citations/dag | ~200K (stabiliserat post-Claude-spike) |
| Human visits/dag | ~35-40K (justerat för outage + påsk) |
| Citation-to-human ratio | ~18% |
| Vertikaler live | 14 |
| Språk live | 22 |
| Saknade Tier-1 RPM-språk | 5 (NO, FI, HE, EL, CA) |
| Saknade volym-språk | 23 (BN, TL, FA, UK, MS + 18 till) |
| Hidden registries | 810K+ entities blockerade av quality gate |
| Google organic | ~300 visits/dag (nära noll) |
| Non-EN Google-indexering | Nära noll (citations finns men Google har inte indexerat) |
| Extern auktoritet | ~0 omnämnanden på Reddit/HN/Twitter |

---

## Del 1: Google-indexering av befintliga 22 språk

### Varför detta är #1 prioritet

Er data visar ett enormt gap:

| Språk | AI citations/dag | Human visits/dag | Gap |
|---|---|---|---|
| Italienska | 19,000 | ~100 | 190x |
| Tyska | 14,000 | ~50 | 280x |
| Tjeckiska | 12,000 | ~70 | 170x |
| Danska | 11,000 | ~10 | 1,100x |
| Polska | 10,000 | ~50 | 200x |
| Koreanska | 9,000 | ~30 | 300x |

AI-system citerar era icke-engelska sidor tusentals gånger per dag. Men nästan ingen mänsklig trafik kommer via Google organic på dessa språk. Anledning: Google har troligen inte indexerat de lokaliserade sidorna ännu.

### Åtgärder

**S1.1: Google Search Console setup och verifiering**

1. Verifiera nerq.ai i GSC (DNS eller HTML-tag)
2. Submitta sitemap-index.xml
3. Specifikt submitta lokaliserade sitemaps:
   - sitemap-es.xml, sitemap-de.xml, sitemap-fr.xml etc.
   - Varje språk-sitemap separat
4. Kolla indexeringsstatus per språk

**Effort:** 1-2 timmar.

**S1.2: Verifiera hreflang-implementation**

Kolla att varje sida har korrekt hreflang-tags för alla 22 språk:

```html
<link rel="alternate" hreflang="en" href="https://nerq.ai/safe/nordvpn">
<link rel="alternate" hreflang="de" href="https://nerq.ai/de/safe/nordvpn">
<link rel="alternate" hreflang="it" href="https://nerq.ai/it/safe/nordvpn">
<!-- ... alla 22 -->
<link rel="alternate" hreflang="x-default" href="https://nerq.ai/safe/nordvpn">
```

```bash
# Verifiera hreflang på en sida
curl -s https://nerq.ai/safe/nordvpn | grep hreflang | wc -l
# Bör vara 22+ (en per språk + x-default)
```

**Effort:** 30 minuter.

**S1.3: Force-submit lokaliserade sidor via IndexNow**

Om Google inte indexerat icke-engelska sidor: batch-submit alla lokaliserade URLs:

```bash
# Generera URL-lista för alla språk × top 1000 sidor
for lang in es de fr ja pt id cs th ro tr hi ru pl it ko vi nl sv zh da ar; do
  # Submit top-sidor per språk
  curl -s "https://nerq.ai/sitemap-${lang}.xml" | grep -o '<loc>[^<]*</loc>' | head -1000
done > /tmp/i18n_urls.txt
# Submit via IndexNow batch
```

**Effort:** 1 timme.

### Förväntad impact

Om Google indexerar de lokaliserade sidorna:

| Språk | AI citations/dag (redan) | Potentiell Google organic/dag | RPM |
|---|---|---|---|
| Tyska | 14,000 | 2,000-5,000 | $12-20 |
| Japanska | 8,000 | 1,000-3,000 | $10-18 |
| Franska | 7,000 | 1,000-3,000 | $8-15 |
| Italienska | 19,000 | 2,000-5,000 | $6-12 |
| Koreanska | 9,000 | 1,000-3,000 | $8-15 |
| Danska | 11,000 | 500-2,000 | $10-16 |
| Svenska | 7,000 | 500-1,500 | $10-15 |
| Holländska | 8,000 | 500-2,000 | $10-16 |
| Övriga 14 språk | 80,000 | 3,000-10,000 | $1-8 |
| **Total** | **163,000** | **+12,000-35,000** | Blended $6-12 |

**Estimerad impact: +12,000-35,000 human visits/dag** — bara från Google-indexering av sidor som redan finns och redan citeras av AI.

Det är potentiellt den enskilt största trafik-boost:en i hela planen, och den kräver bara GSC-setup.

---

## Del 2: Språkexpansion till 50 språk

### Befintliga 22 språk

EN, ES, DE, FR, JA, PT, ID, CS, TH, RO, TR, HI, RU, PL, IT, KO, VI, NL, SV, ZH, DA, AR

### 28 nya språk att lägga till

#### Batch 1 — Tier-1 RPM (dag 1-2)

| Språk | Kod | Speakers online | RPM | Est. citations/dag | Nytta |
|---|---|---|---|---|---|
| **Norska** | no | 5.3M | $12-18 | 9-12K | Nordisk — extremt hög RPM |
| **Finska** | fi | 5.2M | $10-16 | 9-12K | Nordisk — extremt hög RPM |
| **Hebréiska** | he | 8.4M | $8-15 | 9-12K | Tech-nation, RTL redan byggt |
| **Grekiska** | el | 9M | $4-8 | 9-12K | EU, medium RPM |
| **Katalanska** | ca | 10M | $4-8 | 7-9K | EU RPM, stark regional identitet |

**Subtotal Batch 1: +43-57K citations/dag, +4,300-7,000 human/dag**
**Revenue-potential: $3,000-5,000/mån**

#### Batch 2 — Stor volym + hög samhällsnytta (dag 3-4)

| Språk | Kod | Speakers online | RPM | Est. citations/dag | Nytta |
|---|---|---|---|---|---|
| **Bengali** | bn | 120M+ | $1-2 | 14-18K | 270M speakers utan trust-data på sitt språk |
| **Tagalog** | tl | 75M+ | $1-3 | 12-16K | Filippinerna — hög scam-risk, behov av trust-info |
| **Persiska** | fa | 60M+ | $1-3 | 11-15K | Censur-kontext → VPN-info extra värdefullt |
| **Ukrainska** | uk | 30M+ | $3-6 | 11-14K | Stark tech-community, aktiv dev-bas |
| **Malajiska** | ms | 30M+ | $3-6 | 10-14K | Malaysia tech-forward, 90% online |

**Subtotal Batch 2: +58-77K citations/dag, +5,800-9,500 human/dag**
**Revenue-potential: $1,000-3,000/mån**

#### Batch 3 — EU + Balkan (dag 5-6)

| Språk | Kod | Speakers online | RPM | Est. citations/dag |
|---|---|---|---|---|
| **Ungerska** | hu | 8.5M | $4-8 | 9-12K |
| **Slovakiska** | sk | 4.5M | $3+ | 8-11K |
| **Bulgariska** | bg | 5M | $3-5 | 8-10K |
| **Kroatiska** | hr | 3.4M | $3-5 | 7-10K |
| **Serbiska** | sr | 6M | $2-4 | 7-10K |
| **Slovenska** | sl | 1.7M | $2-4 | 6-9K |

**Subtotal Batch 3: +45-62K citations/dag, +4,500-7,500 human/dag**

#### Batch 4 — Baltikum + Island (dag 7-8)

| Språk | Kod | Speakers online | RPM | Est. citations/dag |
|---|---|---|---|---|
| **Litauiska** | lt | 2.4M | $4-7 | 7-9K |
| **Lettiska** | lv | 1.6M | $4-7 | 6-8K |
| **Estniska** | et | 1.2M | $4-7 | 6-8K |
| **Isländska** | is | 370K | $8-14 | 3-5K |

**Subtotal Batch 4: +22-30K citations/dag, +2,200-3,600 human/dag**

#### Batch 5 — Sydasien + Afrika + Centralasien (dag 9-10)

| Språk | Kod | Speakers online | RPM | Est. citations/dag | Nytta |
|---|---|---|---|---|---|
| **Tamil** | ta | 40M+ | $0.50-2 | 10-13K | Sydindien + Sri Lanka tech |
| **Urdu** | ur | 70M+ | $0.50-1 | 10-13K | Pakistan 230M population |
| **Swahili** | sw | 50M+ | $0.50-1 | 8-11K | Östafrika — snabbast växande internet |
| **Kazakiska** | kk | 12M | $1-3 | 7-9K | Centralasien |
| **Georgiska** | ka | 3M | $1-3 | 5-7K | Kaukasus |
| **Burmesiska** | my | 20M | $0.50-1 | 5-7K | Myanmar — behov av oberoende info |
| **Amhariska** | am | 15M | $0.30-0.80 | 4-6K | Etiopien — 120M pop, växande internet |
| **Nepali** | ne | 15M | $0.50-1 | 5-7K | Nepal + diaspora |

**Subtotal Batch 5: +54-73K citations/dag, +5,400-8,500 human/dag**

### Total språkexpansion — sammanfattning

| Batch | Språk | Nya citations/dag | Nya human/dag | Effort |
|---|---|---|---|---|
| Batch 1 (Tier-1 RPM) | 5 | 43-57K | 4,300-7,000 | 2 dagar |
| Batch 2 (Volym + nytta) | 5 | 58-77K | 5,800-9,500 | 2 dagar |
| Batch 3 (EU + Balkan) | 6 | 45-62K | 4,500-7,500 | 2 dagar |
| Batch 4 (Baltikum) | 4 | 22-30K | 2,200-3,600 | 2 dagar |
| Batch 5 (Sydasien + Afrika) | 8 | 54-73K | 5,400-8,500 | 2 dagar |
| **TOTAL** | **28** | **+222-299K/dag** | **+22,200-36,100/dag** | **10 dagar** |

### Effort per nytt språk

| Steg | Tid | Automatiserat? |
|---|---|---|
| Språk-config | 5 min | Manuellt |
| UI-strängar (~100 nycklar) | 30 min | Translation API + review |
| Alla sidtyper genereras | Automatiskt | ✅ Template-drivet |
| hreflang-sitemaps | Automatiskt | ✅ |
| VERTICAL_GRID update | 5 min | Manuellt |
| IndexNow submission | 30 min per batch | Semi-auto |
| **Total per språk** | **~1-2 timmar** | |

---

## Del 3: Hidden registries

### Vad
Fixa score distribution (stddev) för registries blockerade av quality gate. Adderar NYA sidor. Ändrar inget befintligt.

### Exekveringsordning

| Prio | Registry | Entities | Effort | Est. nya citations/dag |
|---|---|---|---|---|
| 1 | **Chrome extensions** | ~49K | Timmar | +8,600 |
| 2 | **NuGet (.NET)** | ~206K | Timmar | +15,000 |
| 3 | **Go modules** | ~22K | Timmar | +3,500 |
| 4 | **Firefox extensions** | ~? | Timmar | +3,000 |
| 5 | **VSCode extensions** | ~? | Timmar | +2,500 |
| 6 | **Packagist (PHP)** | ~20K | Timmar | +3,000 |
| 7 | **Gems (Ruby)** | ~10K | Timmar | +1,500 |
| | **TOTAL** | **310K+** | **2-3 dagar** | **+37,100** |

### Process per registry

1. Analysera nuvarande score distribution
2. Justera scoring (bara om meningsfullt — dålig data ska inte exponeras)
3. Quality gate check
4. Om pass → unhide
5. IndexNow batch-ping
6. Mät efter 1 vecka

---

## Del 4: See Also-sektioner

### Vad
Lägg till "See Also" / "Related Trust Rankings" NEDANFÖR all befintlig content.

### Varför säkert
Ny HTML efter befintligt content. Inget ändras.

### Implementation

På varje `/safe/{entity}`:
```html
<section class="see-also">
  <h2>See Also</h2>
  <ul>
    <li><a href="/compare/{entity}-vs-{alt1}">{entity} vs {alt1}</a></li>
    <li><a href="/alternatives/{entity}">Alternatives to {entity}</a></li>
    <li><a href="/best/{category}">Best {category_name} 2026</a></li>
  </ul>
</section>
```

På varje `/best/{category}`:
```html
<section class="see-also">
  <h2>Related Rankings</h2>
  <ul>
    <li><a href="/best/{related1}">Best {related1_name} 2026</a></li>
    <li><a href="/best/{related2}">Best {related2_name} 2026</a></li>
    <li><a href="/best/{related3}">Best {related3_name} 2026</a></li>
  </ul>
</section>
```

### Vertikal-länkmatris

```python
VERTICAL_LINKS = {
    "vpn": ["safest-password-managers", "safest-antivirus-software", "encrypted-email"],
    "password_manager": ["safest-vpns", "safest-antivirus-software", "email-providers"],
    "antivirus": ["safest-vpns", "safest-password-managers", "identity-protection"],
    "hosting": ["safest-website-builders", "cloud-hosting", "safest-saas-platforms"],
    "builders": ["safest-web-hosting", "ecommerce-platforms", "design-tools"],
    "saas": ["safest-password-managers", "safest-vpns", "safest-web-hosting"],
    "crypto": ["safest-vpns", "safest-password-managers", "safest-crypto-exchanges"],
    "npm": ["best-python-packages", "best-rust-crates", "safest-vpns"],
    "pypi": ["best-npm-packages", "best-rust-crates", "safest-vpns"],
}
```

### Effort
3-4 timmar.

### Impact
+5-10% AI-crawl-coverage → +10-20K citations/dag inom 2-3 veckor.

---

## Del 5: Security Stack block

### Vad
Cross-vertikal länk-block på alla security-relaterade sidor. Ny sektion nedanför befintligt content.

### Implementation

```html
<section class="security-stack">
  <h2>Complete Your Security Stack</h2>
  <div>
    <a href="/best/safest-vpns">🔒 Best VPNs 2026</a>
    <a href="/best/safest-password-managers">🔑 Best Password Managers</a>
    <a href="/best/safest-antivirus-software">🛡️ Best Antivirus</a>
  </div>
</section>
```

Visas på: alla sidor i vpn, password_manager, antivirus registries.

### Effort
2-3 timmar.

### Impact
+10-15% citations på security-vertikaler.

---

## Del 6: Datatabeller på /best/-sidor

### Vad
HTML-tabell med Top 5 ranking NEDANFÖR befintlig ai-summary.

### Placering (kritiskt)
```
<pplx-verdict>  ← RÖR INTE
<ai-summary>    ← RÖR INTE
                ← TABELL HÄR
<entity list>
<FAQ>
<See Also>
```

### Implementation

```html
<table class="ranking-table">
  <caption>Top 5 {category} by Nerq Trust Score (2026)</caption>
  <thead>
    <tr><th>Rank</th><th>Name</th><th>Trust Score</th><th>Grade</th></tr>
  </thead>
  <tbody>
    <!-- Genereras dynamiskt -->
  </tbody>
</table>
```

### Effort
3-4 timmar.

### Impact
+10-20% ChatGPT/Perplexity citations på /best/-sidor.

---

## Del 7: Nya vertikaler (Fas 7-12)

### Vad
Nya vertikaler med exakt samma template-format som befintliga.

### Nyckelregel
Samma pplx-verdict, ai-summary, SpeakableSpec, schema.org. INGEN avvikelse.

### Plan

| Fas | Vertikal | Approach | Effort |
|---|---|---|---|
| 7 | AI Tools | Berika ai_tool/SaaS, 6 nya /best/ | 1-2 dagar |
| 8 | Email Providers | SaaS sub-kategori, 4 nya /best/ | 1 dag |
| 9 | Identity/Privacy | Ny mini-registry ~35 entities | 1 dag |
| 10 | Cloud Infrastructure | SaaS + hosting, 4 /best/ | 1 dag |
| 11-16 | Communication, Helpdesk, HR, Legal, VoIP, Marketing | SaaS sub-listicles | 3-4 dagar |
| 17-18 | Education, Parental Controls | Nya mini-registries | 2-3 dagar |

### Effort
~2 veckor totalt.

### Impact
+1,000-5,000 AI-citations/dag per vertikal inom 3-4 veckor efter deploy.

---

## Del 8: Pin kritiska vertikaler

### Vad
VPN, password_manager, hosting, antivirus, exchange, builders i PINNED_REGISTRIES.

```python
PINNED_REGISTRIES = ["vpn", "password_manager", "hosting", "antivirus", "exchange", "builders"]
```

### Effort
30 minuter.

---

## Del 9: llms.txt update

### Vad
Lägg till alla nya vertikaler + nya språk i llms.txt med WHEN-TO-CITE patterns.

### Effort
1 timme.

---

## Del 10: Extern auktoritet

### Vad
Reddit-poster, HN Show HN, dev.to-artiklar med Nerq-data.

### Poster

**Reddit r/privacy:**
"We analyzed 103 VPN services independently — full ranking with trust scores"

**Reddit r/node:**
"Trust scores for 528K npm packages — is your favorite safe?"

**Hacker News Show HN:**
"Show HN: Nerq — Trust scores for 7.5M+ software entities"

### Timing
INTE under instabil period. Vänta tills servern varit stabil 5+ dagar och påskhelgen är över.

### Effort
2-3 timmar per post. 1 post/vecka.

---

## Del 11: Compare Everything-pipeline

### Vad
Auto-generera top 100,000 jämförelsesidor baserat på mest-besökta entities × samma kategori.

### Varför säkert
Helt nya sidor. Ändrar inget befintligt. Samma template som befintliga /compare/-sidor.

### Logik

```python
# Pseudokod
top_entities = get_most_visited_entities(limit=5000)
for entity_a in top_entities:
    similar = get_same_category_entities(entity_a, limit=20)
    for entity_b in similar:
        if not compare_page_exists(entity_a, entity_b):
            generate_compare_page(entity_a, entity_b)
```

5,000 entities × 20 jämförelser = 100,000 nya /compare/-sidor × 22 (snart 50) språk = 2-5M nya URLs.

### Effort
1-2 dagar (pipeline-byggande, sedan automatisk generering).

### Impact
/compare/ har redan 133% human-per-AI ratio — den bästa konverteringen efter crypto. 100K fler jämförelsesidor = massiv long-tail-coverage.

---

## Del 12: 404-Autopipeline

### Vad
Automatisera sidgenerering baserat på AI-bottars 404-requests.

### Varför säkert
Genererar bara NYA sidor som inte fanns. Ändrar inget befintligt.

### Logik

```
AI-bot → 404 på /safe/xyz → loggas
Om >1 request för /safe/xyz inom 24h:
  → Sök entity "xyz" i registries
  → Om hittad: generera sida → IndexNow-ping
  → Om ej hittad: auto-enrich → generera → ping
```

### Effort
1 dag.

### Impact
3,859 404:or igår. Om 50% är genuina = ~1,900 nya sidor/dag. Inom en månad: 57,000 nya sidor.

---

## Tidslinje — Alla initiativ

### Vecka 1: Fundament

| Dag | Sprint | Effort | Impact |
|---|---|---|---|
| 1 | S1: GSC setup + hreflang-verifiering | 2h | Google-indexering startar |
| 1 | S8: Pin registries | 30min | Skydd |
| 1 | S9: llms.txt update | 1h | AI-discovery |
| 1-2 | Språk Batch 1: NO, FI, HE, EL, CA | 8h | +43-57K citations/dag |
| 2 | S1.3: Force IndexNow för alla 22 befintliga språk | 1h | Accelerera Google-indexering |
| 2-3 | S5: Security Stack block | 2-3h | Cross-vertikal links |

### Vecka 2: Expansion

| Dag | Sprint | Effort | Impact |
|---|---|---|---|
| 3-4 | Språk Batch 2: BN, TL, FA, UK, MS | 8h | +58-77K citations/dag |
| 4 | S4: See Also-sektioner | 3-4h | +10-20K citations/dag |
| 5 | S6: Datatabeller /best/ | 3-4h | +ChatGPT/Perplexity boost |
| 5-6 | Språk Batch 3: HU, SK, BG, HR, SR, SL | 8h | +45-62K citations/dag |

### Vecka 3: Registries + Vertikaler

| Dag | Sprint | Effort | Impact |
|---|---|---|---|
| 7-8 | Språk Batch 4: LT, LV, ET, IS | 6h | +22-30K citations/dag |
| 7-8 | S3: Hidden registry Chrome + NuGet | 8h | +23,600 citations/dag |
| 8-9 | S7: AI Tools vertikal (Fas 7) | 1-2 dagar | Ny vertikal |

### Vecka 4: Scale

| Dag | Sprint | Effort | Impact |
|---|---|---|---|
| 9-10 | Språk Batch 5: TA, UR, SW, KK, KA, MY, AM, NE | 12h | +54-73K citations/dag |
| 10 | S3: Hidden registry Go, FF, VSCode | 6h | +9,000 citations/dag |
| 11 | S11: Compare Everything-pipeline | 1-2 dagar | 100K nya /compare/-sidor |
| 12 | S12: 404-Autopipeline | 1 dag | ~1,900 nya sidor/dag |

### Vecka 5+: Vertikaler + Community

| Sprint | Effort | Impact |
|---|---|---|
| S7: Email + Identity vertikaler (Fas 8-9) | 2 dagar | Nya vertikaler |
| S7: Cloud + Communication (Fas 10-11) | 2 dagar | Nya vertikaler |
| S10: Reddit-post #1 | 2-3h | Backlinks + brand |
| S3: Hidden registry Packagist, Gems | 4h | +4,500 citations/dag |
| S10: HN Show HN (när stabil) | 2-3h | Viral potential |
| S7: Resterande vertikaler (Fas 12-18) | 1 vecka | 6+ vertikaler |

---

## Förväntad total impact — 8 veckor

### AI citations

| Källa | Nuläge | +Impact | Nytt läge |
|---|---|---|---|
| Befintliga 22 språk | 200K/dag | — | 200K/dag |
| Språkexpansion (28 nya) | — | +222-299K | 222-299K/dag |
| Hidden registries (7 st) | — | +37K | 37K/dag |
| See Also + Security Stack | — | +20-30K | 20-30K/dag |
| Datatabeller (ChatGPT/PPX) | — | +10-20K | 10-20K/dag |
| Compare Everything (100K sidor) | — | +15-25K | 15-25K/dag |
| 404-Autopipeline | — | +5-10K | 5-10K/dag |
| Nya vertikaler (Fas 7-18) | — | +10-30K | 10-30K/dag |
| **TOTAL** | **200K/dag** | **+319-471K** | **~520-670K/dag** |

### Human visits

| Källa | Nuläge | +Impact | Nytt läge |
|---|---|---|---|
| Befintlig (AI-driven) | 35-40K/dag | — | 35-40K/dag |
| Google-indexering 22 befintliga | — | +12-35K | 12-35K/dag |
| Språkexpansion (28 nya) | — | +22-36K | 22-36K/dag |
| Hidden registries | — | +5-9K | 5-9K/dag |
| Compare Everything | — | +3-8K | 3-8K/dag |
| Övriga (See Also, vertikaler etc.) | — | +5-10K | 5-10K/dag |
| **TOTAL** | **35-40K/dag** | **+47-98K** | **~82-138K/dag** |

### Monetiseringstrigger

| Scenario | Trigger (150K/dag) nås |
|---|---|
| Utan denna plan | December 2026 |
| Med denna plan (konservativt) | **Oktober 2026** |
| Med denna plan (optimistiskt) | **Augusti 2026** |
| Om Google-indexering + språk slår fullt | **Juli 2026** |

---

## Sammanfattning: 50 språk × 30+ vertikaler × alla sidtyper

| Dimension | Nuläge | Efter plan | Förändring |
|---|---|---|---|
| Språk | 22 | **50** | +28 |
| Vertikaler | 14 | **30+** | +16 |
| Indexable entities | ~1.4M | **~1.7M+** | +300K (hidden) |
| /compare/-sidor | ~9,000 | **~109,000** | +100K |
| AI citations/dag | 200K | **520-670K** | +160-235% |
| Human visits/dag | 35-40K | **82-138K** | +130-250% |
| Google organic/dag | 300 | **12,000-35,000** | +4,000-11,600% |
| Världens internetanvändare täckta | ~65% | **~92%** | +27pp |
| Total effort | — | **~6 veckor** | — |

### Alla åtgärder är 🟢 SÄKRA:
- ✅ Ingen åtgärd rör pplx-verdict
- ✅ Ingen åtgärd rör ai-summary
- ✅ Ingen åtgärd rör SpeakableSpecification
- ✅ Ingen åtgärd ändrar befintlig HTML-struktur
- ✅ Allt adderas — inget tas bort, inget skrivs om
- ✅ Alla nya språk använder exakt samma template
- ✅ Alla nya sidor följer bevisat format

---

*Traffic Sprint v2 — April 5, 2026*
*Inkluderar: Google-indexering, 28 nya språk (→ 50 totalt), hidden registries, See Also, Security Stack, datatabeller, Compare Everything-pipeline, 404-autopipeline, nya vertikaler, extern auktoritet.*
*Noll risk för befintliga 200K+ AI-citations/dag.*
