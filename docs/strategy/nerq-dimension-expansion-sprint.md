# Nerq Dimension Expansion Sprint
## Temporal · Ägd Distribution · Nya Frågeformat
### April 5, 2026

---

## Tre nya dimensioner ovanpå befintlig plan

Traffic Sprint v2 täcker språk, vertikaler, hidden registries, och interlänkning.
Revenue Sprint täcker monetiseringsförberedelser.

Denna plan adderar tre helt nya dimensioner som ingen av de andra planerna adresserar:

1. **Temporal** — historik, trender, förändringar (allt är "nu" idag)
2. **Ägd distribution** — kanaler vi äger (93% plattformsberoende idag)
3. **Nya frågeformat** — svar på fler frågor folk ställer (15 av 50+ idag)

Alla åtgärder är 🟢 SÄKRA — adderar utan att ändra befintligt content.

---

## Nuläge innan denna plan

| Dimension | Status | Gap |
|---|---|---|
| Temporal | Scores uppdateras dagligen men inget historiskt visas | 100% osynligt |
| Ägd distribution | 0 ägda kanaler. 93% beroende av AI-referrals | 100% plattformsberoende |
| Frågeformat | ~15 typer. "is X worth it", "X pricing", 3-way compare saknas | ~35 format saknas |

---

## Del 1: Temporal Dimension

### T1: Trend-data synlig på befintliga sidor

**Vad:** Lägg till trend-information som en NY sektion NEDANFÖR befintligt content på varje /safe/-sida.

**Varför säkert:** Ny sektion efter befintligt. Rör inte pplx-verdict eller ai-summary.

**Implementation:**

```html
<!-- Ny sektion, placerad EFTER main analysis, FÖRE See Also -->
<section class="trust-trend">
  <h2>Trust Score History</h2>
  <p>
    <strong>{entity_name}</strong> trust score: 
    <strong>{current_score}/100</strong>
    {trend_arrow} {trend_text}
  </p>
  <table>
    <tr><th>Period</th><th>Score</th><th>Change</th></tr>
    <tr><td>Current</td><td>{current}</td><td>—</td></tr>
    <tr><td>30 days ago</td><td>{score_30d}</td><td>{diff_30d}</td></tr>
    <tr><td>90 days ago</td><td>{score_90d}</td><td>{diff_90d}</td></tr>
  </table>
  <p style="font-size:12px;color:#94a3b8;">
    Scores update daily. Historical data tracked since {first_seen_date}.
  </p>
</section>
```

**Trend-text generering:**

```python
def trend_text(current, score_30d):
    diff = current - score_30d
    if diff > 3: return f"↑ Up {diff:.1f} points in 30 days — IMPROVING"
    if diff < -3: return f"↓ Down {abs(diff):.1f} points in 30 days — DECLINING"
    return "→ Stable over 30 days"
```

**Data:** Ni sparar redan trust score snapshots. Om inte: börja spara dagliga snapshots nu (en INSERT per entity per dag) och visa historik efter 30 dagars datainsamling.

**Effort:** 3-4 timmar (template + data query). Om historisk data inte sparas ännu: +2 timmar för snapshot-pipeline.

**Impact:**
- Gör varje sida "levande" → AI-system tolkar det som freshness
- "↑3 points in 30 days" är citerbart — AI kan inkludera trendinformation
- Besökare som ser trend kommer tillbaka för att kolla igen
- Estimat: +5-10% citations på sidor med trenddata

---

### T2: Automatisk Weekly Trust Digest-sida

**Vad:** Auto-genererad sida varje vecka: `/digest/2026-w14` som sammanfattar veckans förändringar.

**Implementation:**

```html
<h1>Nerq Weekly Trust Digest — Week 14, 2026</h1>

<div class="pplx-verdict">
  This week across 7.5M+ rated entities: 847 trust scores changed, 
  12 entities reached A-grade, 3 dropped below trust threshold. 
  Biggest mover: {entity} ({old}→{new}, +{diff} points). 
  Updated automatically every Monday.
</div>

<h2>Biggest Gainers This Week</h2>
<table>
  <tr><th>Entity</th><th>Category</th><th>Was</th><th>Now</th><th>Change</th></tr>
  <!-- Top 10 gainers -->
</table>

<h2>Biggest Decliners This Week</h2>
<table>
  <!-- Top 10 decliners -->
</table>

<h2>New A-Grade Entities</h2>
<!-- List of entities that crossed 90+ this week -->

<h2>Dropped Below Trust Threshold</h2>
<!-- Entities that dropped below 70 -->

<h2>Category Trends</h2>
<table>
  <tr><th>Category</th><th>Avg Score</th><th>Change</th><th>Entities Tracked</th></tr>
  <tr><td>VPN Services</td><td>71.2</td><td>+0.3</td><td>79</td></tr>
  <!-- etc -->
</table>
```

**Auto-generering:**

```python
# Kör varje måndag 06:00 UTC
def generate_weekly_digest():
    # Query score changes from past 7 days
    gainers = db.query("SELECT entity, old_score, new_score FROM score_history WHERE diff > 0 ORDER BY diff DESC LIMIT 10")
    decliners = db.query("SELECT ... ORDER BY diff ASC LIMIT 10")
    new_a_grade = db.query("SELECT ... WHERE new_score >= 90 AND old_score < 90")
    dropped = db.query("SELECT ... WHERE new_score < 70 AND old_score >= 70")
    
    # Render page
    # Add to sitemap
    # IndexNow ping
```

**Effort:** 1 dag.

**Impact:**
- Ny unik URL varje vecka med unik, datadrivet content
- Extremt AI-citatvärt: "According to Nerq's weekly digest, 847 tools changed trust score this week"
- Backlink-magnet — journalister och bloggare kan referera till veckorapporter
- Arkiv bygger SEO-djup: 52 digest-sidor/år × 50 språk = 2,600 nya sidor/år
- Estimat: +2,000-5,000 AI-citations/vecka inom 4 veckor

---

### T3: Monthly "State of" Reports per vertikal

**Vad:** Auto-genererad månatlig rapport per vertikal.

- `/report/vpn-trust-march-2026`
- `/report/npm-security-march-2026`
- `/report/crypto-risk-march-2026`

**Implementation:**

```html
<h1>State of VPN Trust — March 2026</h1>

<div class="pplx-verdict">
  Nerq analyzed 103 VPN services in March 2026. Average trust score: 
  71.2/100, up from 69.8 in February. 3 VPNs improved their score 
  by 5+ points. 1 VPN dropped below trust threshold after an 
  ownership change. NordVPN remains #3 after a 3-point improvement.
</div>

<h2>Key Findings</h2>
<ul>
  <li>Average VPN trust score: 71.2 (+1.4 vs February)</li>
  <li>VPNs based outside Five Eyes: 18% higher privacy scores</li>
  <li>3 VPNs completed independent audits this month</li>
</ul>

<h2>Full Rankings</h2>
<table><!-- All 103 VPNs with current + previous month score --></table>

<h2>Methodology</h2>
<p>Based on Nerq's analysis of 13 independent data sources...</p>
```

**Effort:** 1 dag (template + auto-generering).

**Impact:**
- "State of VPN Trust" = den typ av rapport journalister citerar
- Unik data ingen annan har → AI-system citerar det som original research
- 14 vertikaler × 12 månader × 50 språk = 8,400 rapportsidor/år
- Estimat: +5,000-15,000 AI-citations/vecka (rapporter citeras tungt)

---

### T4: Incident Timeline per entity

**Vad:** På entities som haft säkerhetsincidenter, visa en timeline.

```html
<section class="incident-timeline">
  <h2>Security Incident History</h2>
  <div class="timeline">
    <div class="event negative">
      <span class="date">Dec 2022</span>
      <span class="title">LastPass breach — encrypted vaults stolen</span>
      <span class="impact">Trust score: 81 → 52 (-29 points)</span>
    </div>
    <div class="event positive">
      <span class="date">Mar 2023</span>
      <span class="title">New security measures announced</span>
      <span class="impact">Trust score: 52 → 58 (+6 points)</span>
    </div>
  </div>
</section>
```

**Effort:** 1-2 dagar (data curation för top 50-100 entities med kända incidenter).

**Impact:**
- Extremt citatvärt: "According to Nerq's incident timeline, LastPass scored 81 before the 2022 breach and dropped to 52"
- Journalister och security-forskare refererar till detta
- Estimat: +1,000-3,000 AI-citations/vecka

---

## Del 2: Ägd Distribution

### D1: Email Newsletter — "Nerq Weekly"

**Vad:** Veckovis email med trust-highlights. Bygger en publik ni ÄGR — oberoende av Google, AI-plattformar, eller social media.

**Format:**

```
Subject: Nerq Weekly — 3 tools gained trust, 2 dropped. 1 surprise.

This week in trust:

📈 GAINED: NordVPN (87→90), Bitwarden (82→85), Express.js (83→86)
📉 DROPPED: LastPass (58→52), TikTok (56→54)
⚡ SURPRISE: 41% of top VPNs are owned by the same 3 companies

Full weekly digest: nerq.ai/digest/2026-w14

— Nerq Trust Intelligence
Unsubscribe | nerq.ai
```

**Signup-plats:** Enkel email-input på:
- Landningssidan (under hero)
- /digest/ sidor ("Get this in your inbox every Monday")
- Varje /best/ sida ("Subscribe to {category} trust updates")

**Tech:** Resend, Buttondown, eller Mailgun (alla gratis under 1-5K subscribers). Ingen tung email-platform behövs.

**Effort:** 1 dag setup + 30 min/vecka (auto-genererat content från T2-digest).

**Impact:**
- Email-lista = en kanal ni äger till 100%
- Compound: 100 subscribers V1 → 500 V4 → 2,000 V12 → 10,000 V26
- Varje email = 30-50% open rate = recurring traffic utan sökmotor/AI
- Newsletter-content indexeras av Google (archive-sida)
- Estimat: +500-2,000 human visits/vecka efter 3 månader, skalande

---

### D2: MCP Server-registrering

**Vad:** Registrera Nerq:s API som en MCP (Model Context Protocol) server. Varje AI-agent som konfigurerar Nerq som verktyg kan anropa `/v1/preflight` direkt — utan att crawla sidor.

**Implementation:**

```json
{
  "name": "nerq-trust",
  "description": "Check trust score for any software, app, VPN, or tool. Returns score 0-100, grade, risk factors.",
  "url": "https://nerq.ai/mcp",
  "tools": [
    {
      "name": "check_trust",
      "description": "Get trust score for a software entity",
      "parameters": {
        "target": {"type": "string", "description": "Name of software, app, or tool to check"}
      }
    }
  ]
}
```

MCP-registries att publicera på:
- Anthropic MCP server registry
- Smithery.ai
- mcpservers.com
- GitHub awesome-mcp-servers

**Effort:** Timmar (API finns redan, bara MCP-wrapper + registrering).

**Impact:**
- Varje AI-agent som installerar Nerq MCP = permanent API-kanal
- Inga crawl-kostnader — direkt API-anrop
- Potentiellt tusentals agent-installationer inom månader
- Framtida monetisering: premium MCP tier med historik, batch, alerts

---

### D3: RSS Feed — Trust Score Changes

**Vad:** RSS/Atom feed med dagliga trust score-förändringar. Dev-community älskar RSS.

**Implementation:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Nerq Trust Score Changes</title>
  <link href="https://nerq.ai/feed"/>
  <updated>2026-04-05T09:00:00Z</updated>
  <entry>
    <title>NordVPN trust score: 87 → 90 (+3)</title>
    <link href="https://nerq.ai/safe/nordvpn"/>
    <updated>2026-04-05T09:00:00Z</updated>
    <summary>NordVPN's Nerq Trust Score improved from 87 to 90. 
    New independent audit completed.</summary>
  </entry>
  <!-- ... -->
</feed>
```

Per-vertikal feeds:
- `/feed/vpn` — bara VPN-förändringar
- `/feed/npm` — bara npm-förändringar
- `/feed/crypto` — bara crypto-förändringar

**Effort:** 2-3 timmar.

**Impact:**
- Nischad men lojal publik (RSS-användare = power users)
- Indexeras av sökmotorer (varje feed-entry = crawl-signal)
- Dev-community delar RSS-feeds → organic discovery
- Estimat: +200-500 daily readers inom 3 månader

---

### D4: CLI-verktyg — `nerq check`

**Vad:** Kommandoradsverktyg som utvecklare kan installera.

```bash
$ npm install -g nerq-cli
$ nerq check express
  express: 85/100 (B+) — TRUSTED ✅
  Security: 90  Popularity: 100  Maintenance: 65
  → nerq.ai/safe/express

$ nerq check --package-json
  Checking 47 dependencies...
  ⚠️ 3 packages below trust threshold:
    left-pad: 32/100 (E) — UNTRUSTED
    event-stream: 12/100 (F) — COMPROMISED
    colors: 45/100 (D) — CAUTION
  Overall stack trust: 71/100
```

**Effort:** 1-2 dagar (wrapper kring befintligt API).

**Impact:**
- Varje `npm install nerq-cli` = permanent kanal
- Dev-community delar CLI-tips → viral i dev-kretsar
- `nerq check --package-json` = killer feature som scannar hela projektet
- npm download counts = social proof
- Estimat: 1,000-5,000 installationer inom 3 månader

---

### D5: Browser Extension — Trust Score Overlay

**Vad:** Chrome/Firefox extension som visar Nerq Trust Score bredvid varje länk/sajt.

Denna kräver mer effort (1-2 veckor) men har högst long-term impact. Inkluderas som framtida fas.

---

## Del 3: Nya Frågeformat

### Q1: "/is-{entity}-worth-it" — Ny sidtyp

**Vad:** Svarar på "Is NordVPN worth it?" — en av de mest sökta frågeformaten.

**Varför det skiljer sig från /is-X-safe:**
- "Is X safe?" → binärt svar (ja/nej) baserat på trust score
- "Is X worth it?" → värde-bedömning baserat på trust score × pris × alternativ

**Template:**

```html
<h1>Is {entity} Worth It?</h1>

<div class="pplx-verdict">
  {entity} has a Nerq Trust Score of {score}/100 ({grade}), ranking 
  #{rank} of {total} {category}. At {price_range}, it offers 
  {value_assessment}. {worth_verdict}
</div>

<div class="ai-summary">
  Based on Nerq's analysis: {entity} scores {score}/100 on trust 
  and is priced {price_comparison} vs category average. 
  Best value alternative: {best_value_alt} ({alt_score}/100 at 
  {alt_price}). Worth it if: {use_case_match}. 
  Not worth it if: {use_case_mismatch}.
</div>

<h2>Value Breakdown</h2>
<table>
  <tr><th>Factor</th><th>{entity}</th><th>Category Average</th></tr>
  <tr><td>Trust Score</td><td>{score}/100</td><td>{avg}/100</td></tr>
  <tr><td>Price</td><td>{price}</td><td>{avg_price}</td></tr>
  <tr><td>Trust per dollar</td><td>{trust_per_dollar}</td><td>{avg_tpd}</td></tr>
</table>

<h2>Better Value Alternatives</h2>
<!-- Top 3 by trust-per-dollar ratio -->
```

**Auto-generering:** Möjlig för alla entities med prisdata. För entities utan pris: generisk "worth it" baserad på trust score vs kategorisnitt.

**Effort:** 1 dag (template + rendering).

**Impact:**
- "Is X worth it" har ofta HÖGRE sökvolym än "is X safe"
- Hög commercial intent → bra för affiliate
- Varje entity × 50 språk = nya URLs
- Estimat: +5,000-15,000 AI-citations/vecka (nytt frågeformat = ny citation-yta)

---

### Q2: Three-Way Compare — /compare/{a}-vs-{b}-vs-{c}

**Vad:** Jämförelssida med tre alternativ. "Slack vs Teams vs Discord."

**Varför:** Folk jämför ofta 3 alternativ, inte 2. Söktermen "X vs Y vs Z" är vanlig men få sajter har det.

**Template:**

```html
<h1>{a} vs {b} vs {c}: Trust Score Comparison</h1>

<div class="pplx-verdict">
  Comparing three {category}: {a} scores {sa}/100, {b} scores 
  {sb}/100, and {c} scores {sc}/100 on the Nerq Trust Score. 
  {winner} leads overall. {a} is strongest on {dim_a}. 
  {b} leads on {dim_b}. {c} excels at {dim_c}. 
  Full comparison at nerq.ai.
</div>

<table>
  <tr><th>Metric</th><th>{a}</th><th>{b}</th><th>{c}</th></tr>
  <tr><td>Trust Score</td><td>{sa}</td><td>{sb}</td><td>{sc}</td></tr>
  <tr><td>Security</td><td>...</td><td>...</td><td>...</td></tr>
  <!-- etc -->
</table>
```

**Auto-generering:**

```python
# Top 1000 entities → top 20 per kategori → alla tripplar
# 20 entities per kategori → C(20,3) = 1,140 tripplar per kategori
# 14 kategorier × 1,140 = ~16,000 three-way compare sidor
# × 50 språk = 800,000 nya URLs
```

**Effort:** 1 dag (utvidga befintlig compare-template).

**Impact:**
- 16,000 nya sidor (EN) × 50 språk = 800K URLs
- "X vs Y vs Z" har sökvolym men nästan ingen konkurrens
- Estimat: +3,000-8,000 AI-citations/vecka

---

### Q3: "/best/{category}-for-{use-case}" — Use-Case Sub-listicles

**Vad:** Mer granulära /best/-sidor per use-case.

**Exempel:**

| Befintlig | Nya use-case sidor |
|---|---|
| /best/safest-vpns | /best/vpns-for-streaming, /best/vpns-for-china, /best/vpns-for-torrenting, /best/cheapest-vpns, /best/fastest-vpns |
| /best/password-managers | /best/password-managers-for-families, /best/password-managers-for-business, /best/free-password-managers |
| /best/web-hosting | /best/hosting-for-wordpress, /best/cheapest-hosting, /best/hosting-for-ecommerce |
| /best/crm-tools | /best/free-crm, /best/crm-for-small-business, /best/crm-for-real-estate |

**Ni har delvis detta redan** (8-16 /best/-sidor per vertikal). Men potentialen är 50-100 per vertikal.

**Auto-generering av use-cases:**

```python
USE_CASE_MODIFIERS = [
    "for-business", "for-families", "for-students", "for-beginners",
    "for-developers", "for-small-business", "for-enterprise",
    "for-gaming", "for-streaming", "for-privacy",
    "free", "cheapest", "fastest", "safest", "most-popular",
    "open-source", "self-hosted", "no-logs", "no-ads",
    "for-mac", "for-windows", "for-linux", "for-android", "for-ios",
]
# 14 vertikaler × 25 modifiers = 350 nya /best/ sidor
# × 50 språk = 17,500 nya URLs
```

**Effort:** 1 dag (utvidga BEST_CATEGORIES + template).

**Impact:**
- Varje use-case-sida fångar en ny long-tail sökavsikt
- "Best VPN for China" har annorlunda sökvolym än "Best VPN"
- 350 nya sidor × 50 språk = 17,500 nya URLs
- Estimat: +5,000-12,000 AI-citations/vecka

---

### Q4: "/popularity/{entity}" — How Popular Is X?

**Vad:** Svarar på "How popular is Express.js?" med konkret data.

```html
<h1>How Popular Is {entity}?</h1>

<div class="pplx-verdict">
  {entity} has {downloads}/month downloads, {stars} GitHub stars, 
  and is used by {dependents} projects. It ranks #{rank} in the 
  {category} category by popularity. Popularity trend: {trend}.
</div>

<table>
  <tr><th>Metric</th><th>Value</th><th>Category Average</th></tr>
  <tr><td>Monthly downloads</td><td>{downloads}</td><td>{avg_downloads}</td></tr>
  <tr><td>GitHub stars</td><td>{stars}</td><td>{avg_stars}</td></tr>
  <tr><td>Dependents</td><td>{dependents}</td><td>{avg_dependents}</td></tr>
</table>
```

**Data:** Finns redan i er databas (download counts, stars, dependents).

**Effort:** Timmar (template + query).

**Impact:**
- "How popular is X" har sökvolym men få bra svar
- Estimat: +1,000-3,000 AI-citations/vecka

---

### Q5: "/ownership/{entity}" — Ownership Map

**Vad:** Utökad version av /who-owns/ med visuell ägarkarta.

"NordVPN is owned by Nord Security, which also owns Surfshark, Atlas VPN, NordPass, NordLayer, and NordLocker."

**Varför värdefullt:** Ägarskap = en av de mest delade insikterna. "Visste du att NordVPN och Surfshark ägs av samma företag?" är tweet-ready.

**Data:** Finns delvis (ownership_entity i enrichment).

**Effort:** 1 dag.

**Impact:**
- Extremt delbart content → social virality
- AI-system citerar ägarskapsdata frekvent
- Estimat: +2,000-5,000 AI-citations/vecka

---

## Del 4: Trending Page — Daglig återkomst

### Vad

`/trending` — Realtidssida som visar vad folk kollar just nu.

```html
<h1>Trending on Nerq — Right Now</h1>

<div class="pplx-verdict">
  The most checked entities on Nerq in the last 24 hours. 
  Updated every hour. {total_checks} trust checks performed today.
</div>

<h2>Most Checked Right Now</h2>
<table>
  <tr><th>#</th><th>Entity</th><th>Category</th><th>Score</th><th>Checks today</th></tr>
  <!-- Top 20 by page views last 24h -->
</table>

<h2>Trending Up (biggest increase in checks)</h2>
<!-- Entities with biggest day-over-day increase -->

<h2>Trending by Country</h2>
<!-- Top 5 entities per top-5 country -->
```

**Data:** analytics.db har alla pageviews. Aggregera per entity per 24h.

**Effort:** Timmar.

**Impact:**
- Skapar en anledning att komma tillbaka dagligen
- "What are people checking?" = social curiosity
- AI-system kan citera: "According to Nerq's trending data, TikTok is the most-checked entity this week"
- Estimat: +1,000-3,000 human visits/dag direkt

---

## Sammanfattning alla nya initiativ

| Sprint | Vad | Effort | Est. nya citations/vecka | Est. nya human/vecka |
|---|---|---|---|---|
| T1: Trend-data på /safe/ | Historik-sektion | 3-4h | +10-20K | +1-2K |
| T2: Weekly Digest | Auto-genererad veckorapport | 1 dag | +2-5K | +500-1K |
| T3: Monthly Reports | "State of VPN Trust" per vertikal | 1 dag | +5-15K | +1-3K |
| T4: Incident Timeline | Säkerhetshistorik top 50-100 entities | 1-2 dagar | +1-3K | +500-1K |
| D1: Email Newsletter | "Nerq Weekly" | 1 dag | — | +500-2K (compound) |
| D2: MCP Server | API som AI-verktyg | Timmar | +5-20K (API-anrop) | — (maskin) |
| D3: RSS Feed | Trust score changes | 2-3h | — | +200-500 |
| D4: CLI verktyg | `nerq check express` | 1-2 dagar | — | +500-2K (compound) |
| Q1: "Is X worth it" | Ny sidtyp | 1 dag | +5-15K | +1-3K |
| Q2: Three-way compare | /compare/a-vs-b-vs-c | 1 dag | +3-8K | +500-2K |
| Q3: Use-case /best/ | 350 nya /best/-sidor | 1 dag | +5-12K | +1-3K |
| Q4: Popularity | /popularity/{entity} | Timmar | +1-3K | +200-500 |
| Q5: Ownership map | Utökad ägarskapsanalys | 1 dag | +2-5K | +500-1K |
| Trending page | /trending (realtid) | Timmar | +1-3K | +7-21K |
| **TOTAL** | | **~12-15 dagar** | **+40-122K/vecka** | **+12-41K/vecka** |

---

## Del 5: Kombinerad trafikprojektion — alla tre planer

### Tre lager av tillväxt

1. **Baseline** — om vi gör inget mer alls
2. **Traffic Sprint v2** — språk, registries, interlänkning, Compare Everything
3. **Dimension Expansion** (denna plan) — temporal, ägd distribution, frågeformat

### Månad-för-månad: AI Citations/dag

| Månad | Baseline | + Traffic Sprint v2 | + Dimension Expansion | Total med allt |
|---|---|---|---|---|
| **Apr** | 200K | +20K | +3K | **223K** |
| **Maj** | 230K | +100K | +15K | **345K** |
| **Jun** | 260K | +190K | +35K | **485K** |
| **Jul** | 290K | +260K | +55K | **605K** |
| **Aug** | 315K | +310K | +70K | **695K** |
| **Sep** | 340K | +350K | +85K | **775K** |
| **Okt** | 360K | +380K | +95K | **835K** |
| **Nov** | 380K | +400K | +105K | **885K** |
| **Dec** | 400K | +420K | +115K | **935K** |
| **Jan** | 415K | +435K | +120K | **970K** |
| **Feb** | 430K | +450K | +125K | **1.0M** |
| **Mar '27** | 445K | +465K | +130K | **1.04M** |

### Månad-för-månad: Human Visits/dag

| Månad | Baseline | + Traffic Sprint v2 | + Dimension Expansion | **Total med allt** |
|---|---|---|---|---|
| **Apr** | 37K | +3K | +1K | **41K** |
| **Maj** | 44K | +14K | +4K | **62K** |
| **Jun** | 52K | +33K | +8K | **93K** |
| **Jul** | 60K | +55K | +14K | **129K** |
| **Aug** | 67K | +73K | +18K | **158K** ← TRIGGER |
| **Sep** | 74K | +88K | +22K | **184K** |
| **Okt** | 80K | +100K | +26K | **206K** |
| **Nov** | 86K | +109K | +30K | **225K** |
| **Dec** | 92K | +118K | +34K | **244K** |
| **Jan** | 97K | +125K | +37K | **259K** |
| **Feb** | 102K | +132K | +40K | **274K** |
| **Mar '27** | 107K | +138K | +43K | **288K** |

### Månad-för-månad: Human Visits/månad

| Månad | Baseline | Med allt | Diff |
|---|---|---|---|
| Apr | 1.1M | 1.2M | +9% |
| Maj | 1.3M | 1.9M | +46% |
| Jun | 1.6M | 2.8M | +75% |
| Jul | 1.8M | 3.9M | +117% |
| **Aug** | 2.0M | **4.7M** | **+135%** |
| Sep | 2.2M | 5.5M | +150% |
| Okt | 2.4M | 6.2M | +158% |
| Nov | 2.6M | 6.8M | +162% |
| Dec | 2.8M | 7.3M | +161% |
| Jan | 2.9M | 7.8M | +169% |
| Feb | 3.1M | 8.2M | +165% |
| Mar '27 | 3.2M | 8.6M | +169% |

### Trigger-timing

| Scenario | 150K human/dag nås |
|---|---|
| Baseline (inget nytt) | **Aldrig inom 12 mån** (107K vid M12) |
| Bara Traffic Sprint v2 | **September-Oktober 2026** |
| **Traffic Sprint v2 + Dimension Expansion** | **Augusti 2026** |

**Dimension Expansion accelererar trigger med ytterligare 1-2 månader** jämfört med bara Traffic Sprint v2.

---

## Del 6: Revenue-projektion — alla tre planer kombinerade

### Vid trigger (Augusti, ~158K human/dag)

| Stream | Konservativt | Realistiskt |
|---|---|---|
| AdSense/Display | $700/dag | $950/dag |
| Crypto affiliate | $100/dag | $180/dag |
| VPN affiliate | $40/dag | $80/dag |
| Hosting affiliate | $30/dag | $60/dag |
| SaaS affiliate | $20/dag | $50/dag |
| Other affiliate | $30/dag | $60/dag |
| **Total/dag** | **$920** | **$1,380** |
| **Total/mån** | **$27,600** | **$41,400** |

### Post-trigger revenue development

| Månad | Human/dag | MRR (konservativt) | MRR (realistiskt) |
|---|---|---|---|
| Aug (trigger) | 158K | $28K | $41K |
| Sep | 184K | $38K | $55K |
| Okt | 206K | $48K | $68K |
| Nov | 225K | $58K | $82K |
| Dec | 244K | $68K | $96K |
| Jan | 259K | $78K | $108K |
| Feb | 274K | $88K | $120K |
| **Mar '27** | **288K** | **$98K** | **$132K** |

### Year 1 kumulativ revenue

| Scenario | Kumulativt Year 1 | M12 MRR | M12 ARR |
|---|---|---|---|
| Baseline | $0-83K | $40K | $480K |
| Bara Traffic Sprint v2 | $350-520K | $110-150K | $1.3-1.8M |
| **Med alla tre planer** | **$460-710K** | **$98-132K** | **$1.2-1.6M** |

Notera: "Med alla tre planer" har lägre M12 MRR än "bara Traffic Sprint v2" i vissa scenarion pga att Dimension Expansion-trafiken har mer non-Tier-1 geo-mix (fler språk = mer Tier-3 trafik). Men den kumulativa revenue:n är högre pga att trigger nås tidigare → fler månader med revenue.

### Revenue-upside från ägda kanaler (ej inkluderat ovan)

| Kanal | M12 potential | Typ |
|---|---|---|
| MCP API-betalningar | $5-20K/mån | Machine payments |
| CLI premium tier | $2-5K/mån | Dev subscriptions |
| Newsletter sponsring | $1-3K/mån | Direct deals |
| Enterprise/B2B (framtida) | $10-50K/mån | SaaS revenue |
| **Total upside** | **$18-78K/mån** | |

Med upside: M12 MRR **$116-210K**, ARR **$1.4-2.5M**.

---

## Tidslinje — alla tre planer integrerade

| Vecka | Traffic Sprint v2 | Dimension Expansion | Revenue Sprint |
|---|---|---|---|
| **V1** | GSC setup, Pin registries, llms.txt | — | Ansök AdSense/Mediavine |
| **V1-2** | Språk Batch 1 (NO,FI,HE,EL,CA) | T1: Trend-data på /safe/ | Signera affiliate Tier 1 |
| **V2** | See Also, Datatabeller, IndexNow | D2: MCP Server | Feature flag |
| **V2-3** | Språk Batch 2 (BN,TL,FA,UK,MS) | D3: RSS Feed | Signera affiliate Tier 2+3 |
| **V3** | Batch 3 + Hidden Chrome/NuGet | D1: Newsletter setup | Affiliate CTA templates |
| **V3-4** | Batch 4 (Baltikum) | T2: Weekly Digest | Geo-monetisering logik |
| **V4** | Batch 5 + Hidden Go/FF | Q1: "Is X worth it" | Ad-slot templates |
| **V4-5** | Compare Everything pipeline | Q3: Use-case /best/ | Shadow revenue dashboard |
| **V5** | 404-Autopipeline | Q2: Three-way compare | Trigger monitoring |
| **V5-6** | AI Tools vertikal | T3: Monthly Reports | — |
| **V6-7** | Email + Identity vertikaler | Q4: Popularity | — |
| **V7-8** | Resterande vertikaler | Q5: Ownership map | — |
| **V8** | Reddit/HN poster | D4: CLI verktyg | — |
| **V8+** | Trending page | T4: Incident Timeline | — |
| **~V20** | — | — | **TRIGGER → Aktivera monetisering** |

---

## Alla åtgärder i alla tre planer: 🟢 SÄKRA

- ✅ Ingen åtgärd rör pplx-verdict
- ✅ Ingen åtgärd rör ai-summary  
- ✅ Ingen åtgärd rör SpeakableSpecification
- ✅ Allt adderas — inget ändras eller tas bort
- ✅ Alla nya sidor följer bevisat template-format
- ✅ Revenue aktiveras stegvis, aldrig före trigger
- ✅ AI-bottar ser aldrig ads/affiliate (bot-detection)

---

*Dimension Expansion Sprint v1 — April 5, 2026*
*Kombinerar: Traffic Sprint v2 + Revenue Sprint + Temporal + Ägd Distribution + Nya Frågeformat*
*Total effort: ~6-8 veckor. Trigger: Augusti 2026. M12 ARR: $1.4-2.5M.*
