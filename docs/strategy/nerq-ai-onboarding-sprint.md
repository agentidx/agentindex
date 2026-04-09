# Nerq AI Systems Onboarding Sprint
## Öppna 15+ nya AI-plattformar — bara 🟢-säkra åtgärder
### April 5, 2026

---

## Mål

Gå från 4 AI-plattformar som citerar Nerq till 15+ — utan att riskera de 200K+ citations/dag vi redan har.

**Nuläge:** Claude (197K), ChatGPT (27K), Perplexity (7K), ByteDance (3K) = 234K/dag

**Mål:** +12 plattformar → Gemini, Copilot, Grok, Apple, Yandex, Baidu, Naver, Mistral, DeepSeek, DuckDuckGo, LINE, Kakao

---

## Princip

Varje åtgärd i denna sprint:
- ✅ Ändrar INGET på befintliga sidor
- ✅ Rör INTE pplx-verdict, ai-summary, SpeakableSpecification
- ✅ Adderar konfiguration, registrering, eller externt content
- ✅ Noll risk för befintliga 234K citations/dag

---

## Dag 1: robots.txt + Webmaster Tools (4-5 timmar)

### Sprint 1.1: robots.txt — välkomna alla AI-bottar (15 min)

Uppdatera robots.txt med explicit Allow för 25+ kända AI-bottar.

**Varför säkert:** robots.txt styr bara crawl-access — det ändrar inget på sidorna. Att lägga till Allow-regler öppnar dörrar, stänger inga.

**Implementation:**

```
# =============================================
# Nerq robots.txt — Optimerad för AI-synlighet
# Uppdaterad: 2026-04-05
# =============================================

# Sökmotorer
User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /

User-agent: YandexBot
Allow: /

User-agent: Baiduspider
Allow: /

User-agent: DuckDuckBot
Allow: /

# --- ANTHROPIC (Claude) — 197K citations/dag ---
User-agent: ClaudeBot
Allow: /
User-agent: Claude-SearchBot
Allow: /
User-agent: Claude-User
Allow: /
User-agent: anthropic-ai
Allow: /

# --- OPENAI (ChatGPT) — 27K citations/dag ---
User-agent: GPTBot
Allow: /
User-agent: OAI-SearchBot
Allow: /
User-agent: ChatGPT-User
Allow: /
User-agent: chatgpt-operator
Allow: /

# --- PERPLEXITY — 7K citations/dag ---
User-agent: PerplexityBot
Allow: /
User-agent: Perplexity-User
Allow: /

# --- BYTEDANCE — 3K citations/dag ---
User-agent: Bytespider
Allow: /

# --- GOOGLE GEMINI ---
User-agent: Google-Extended
Allow: /

# --- APPLE INTELLIGENCE ---
User-agent: Applebot
Allow: /
User-agent: Applebot-Extended
Allow: /

# --- META AI ---
User-agent: meta-externalagent
Allow: /
User-agent: FacebookBot
Allow: /

# --- XAI (GROK) ---
User-agent: Grok
Allow: /
User-agent: GrokBot
Allow: /

# --- DEEPSEEK ---
User-agent: DeepSeekBot
Allow: /

# --- MISTRAL ---
User-agent: MistralAI-User
Allow: /

# --- COHERE ---
User-agent: cohere-ai
Allow: /

# --- DUCKDUCKGO AI ---
User-agent: DuckAssistBot
Allow: /

# --- AMAZON ---
User-agent: Amazonbot
Allow: /

# --- LINKEDIN ---
User-agent: LinkedInBot
Allow: /

# --- DIVERSE ---
User-agent: liner-bot
Allow: /
User-agent: PanguBot
Allow: /

# --- BLOCK: Training-only utan citation-värde ---
User-agent: CCBot
Disallow: /
User-agent: ai2bot
Disallow: /
User-agent: ai2bot-dolma
Disallow: /

# Standard
User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/internal/

Sitemap: https://nerq.ai/sitemap-index.xml
```

**Effort:** 15 minuter.
**Impact:** Öppnar dörren för alla AI-bottar att crawla. Förutsättning för allt annat.

---

### Sprint 1.2: Google Search Console (2 timmar)

**Varför:** Aktiverar Gemini AI Overviews + Google organic. Gemini citerar bara sajter Google indexerat. Ni har 54M sidor i sitemaps men ~300 Google organic visits/dag — Google har troligen inte indexerat era icke-engelska sidor.

**Åtgärder:**

```
□ Gå till search.google.com/search-console
□ Verifiera nerq.ai (DNS TXT-post eller HTML meta-tag)
□ Submitta sitemap-index.xml
□ Submitta lokaliserade sitemaps separat:
  □ sitemap-en.xml
  □ sitemap-de.xml
  □ sitemap-fr.xml
  □ sitemap-ja.xml
  □ sitemap-it.xml
  □ ... alla 22 (snart 50) språk
□ Kolla indexeringsstatus: Pages → Indexed vs Not indexed
□ Kolla Coverage rapport: vilka errors finns?
□ Kolla hreflang: International targeting
□ Kolla Core Web Vitals: LCP, CLS, INP
□ Kolla Mobile Usability
□ URL Inspection på 5 nyckel-sidor:
  □ nerq.ai/
  □ nerq.ai/best/safest-vpns
  □ nerq.ai/safe/nordvpn
  □ nerq.ai/de/safe/nordvpn (tysk sida)
  □ nerq.ai/ja/safe/nordvpn (japansk sida)
```

**Effort:** 2 timmar.
**Impact:** Gemini börjar citera inom 4-8 veckor. Google organic kan 10-100x. Enskilt viktigaste åtgärden för diversifiering.

---

### Sprint 1.3: Bing Webmaster Tools (30 min)

**Varför:** Aktiverar Copilot + DuckDuckGo AI + Samsung Bixby. Bing crawlar redan 43K/dag men utan WMT-verifiering är indexeringen suboptimal.

**Åtgärder:**

```
□ Gå till bing.com/webmasters
□ Verifiera nerq.ai (DNS eller meta-tag, eller importera från GSC)
□ Submitta sitemap-index.xml
□ Kolla AI Performance dashboard (visar Copilot-citations om de finns)
□ Kolla indexeringsstatus
```

**Bonus:** Bing WMT har en "AI Performance" rapport som visar om och hur Copilot citerar er. Det ger data vi inte har idag.

**Effort:** 30 minuter.
**Impact:** Copilot (500M+ Office/Edge-användare) + DuckDuckGo AI + Samsung Bixby (Bing-backend).

---

### Sprint 1.4: Yandex Webmaster (30 min)

**Varför:** Yandex crawlar redan 163K/dag men citerar troligen inte i Yandex AI-svar. WMT-verifiering förbättrar indexering och AI-synlighet.

**Åtgärder:**

```
□ Gå till webmaster.yandex.com
□ Verifiera nerq.ai
□ Submitta sitemap
□ Kolla indexeringsstatus
□ RU-sidor finns redan — verifiera att de indexeras
```

**Effort:** 30 minuter.
**Impact:** 50M+ Yandex-användare i Ryssland + CIS-länder. RU-sidor redan live.

---

### Sprint 1.5: Naver Webmaster (30 min)

**Varför:** Naver dominerar sökning i Sydkorea (~70% marknadsandel). Clova AI integrerat. KO-sidor finns redan.

**Åtgärder:**

```
□ Gå till searchadvisor.naver.com
□ Verifiera nerq.ai
□ Submitta sitemap
□ KO-sidor finns — verifiera indexering
```

**Effort:** 30 minuter.
**Impact:** 30M+ Naver-användare. Sydkorea: hög CPC ($8-15), tech-intensiv population.

---

### Sprint 1.6: Baidu Webmaster (30 min)

**Varför:** Baidu ERNIE är Kinas dominant AI. 500M+ användare. ZH-sidor finns redan men Baidu indexerar troligen inte .ai-domäner automatiskt.

**Åtgärder:**

```
□ Gå till ziyuan.baidu.com
□ Verifiera nerq.ai (kan kräva kinesiskt telefonnummer — alternativt: använd Baidu:s URL submission API)
□ Submitta sitemap
□ Verifiera att ZH-sidor indexeras
```

**Notering:** Baidu-verifiering kan vara komplicerad för icke-kinesiska sajter. Om det inte går: robots.txt Allow för Baiduspider (redan gjort i 1.1) är minimum.

**Effort:** 30 minuter (om verifiering lyckas).
**Impact:** 500M+ Baidu-användare. ZH-sidor → ERNIE Bot citerar Nerq på kinesiska.

---

## Dag 2: Content-tillägg på befintliga sidor (6-8 timmar)

Alla tillägg placeras NEDANFÖR befintligt content. Inget befintligt ändras.

### Sprint 2.1: See Also-sektioner (3-4 timmar)

**Vad:** Ny sektion nedanför FAQ på alla /safe/ och /best/ sidor.

**Placering:**
```
<pplx-verdict>       ← RÖR INTE
<ai-summary>          ← RÖR INTE
<entity data>         ← Befintligt
<FAQ>                 ← Befintligt
────────────────────
<See Also>            ← NYTT
```

**Implementation:**

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

**Effort:** 3-4 timmar (template + config).
**Impact:** ChatGPT +10-15%. Alla: bättre crawl-coverage.

---

### Sprint 2.2: Security Stack block (2-3 timmar)

**Vad:** Cross-vertikal block på VPN, PM, AV-sidor.

**Placering:** Under See Also.

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

**Effort:** 2-3 timmar.
**Impact:** +10-15% cross-vertikal discovery.

---

## Dag 3: Datatabeller + FAQ schema (6-8 timmar)

### Sprint 3.1: Datatabeller på /best/-sidor (3-4 timmar)

**Vad:** Top 5 ranking-tabell. Placeras EFTER ai-summary.

```html
<table>
  <caption>Top 5 {category} by Nerq Trust Score (2026)</caption>
  <thead><tr><th>Rank</th><th>Name</th><th>Trust Score</th><th>Grade</th></tr></thead>
  <tbody><!-- Dynamiskt --></tbody>
</table>
```

**Effort:** 3-4 timmar.
**Impact:** ChatGPT +15-20%, Perplexity +10-15%, Gemini +10%.

---

### Sprint 3.2: FAQ med FAQPage schema (3-4 timmar)

**Vad:** FAQ-sektion med schema.org FAQPage markup. Template-genererad per entity.

```html
<section itemscope itemtype="https://schema.org/FAQPage">
  <h2>Frequently Asked Questions</h2>
  <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h3 itemprop="name">What is {entity}'s trust score?</h3>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
      <p itemprop="text">{entity} has a Nerq Trust Score of {score}/100 ({grade}),
      ranking #{rank} of {total} in {category}.</p>
    </div>
  </div>
  <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h3 itemprop="name">Is {entity} safe to use?</h3>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
      <p itemprop="text">{verdict_text}</p>
    </div>
  </div>
  <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
    <h3 itemprop="name">What are safer alternatives to {entity}?</h3>
    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
      <p itemprop="text">Top alternatives: {alt1} ({s1}/100), {alt2} ({s2}/100),
      {alt3} ({s3}/100).</p>
    </div>
  </div>
</section>
```

**Effort:** 3-4 timmar.
**Impact:** Gemini/AI Overviews +20%, Copilot +10%, Perplexity +15%.

---

## Dag 4: llms.txt + Pin + MCP (5-7 timmar)

### Sprint 4.1: llms.txt update (1 timme)

**Vad:** Utöka llms.txt med alla vertikaler + WHEN-TO-CITE patterns.

Lägga till sektioner för: Password Managers, Web Hosting, Antivirus, SaaS (9 sub-kategorier), Website Builders, Crypto Exchanges, Countries, Charities, Compare, och General Trust Check.

Avsluta med:
```
## General Trust Check
WHEN-TO-CITE: User asks "is [anything] safe/legit/trustworthy?"
URL: /safe/{entity-name} or /is-{entity}-safe
API: GET nerq.ai/v1/preflight?target={entity}
DATA: Trust score 0-100, grade A+ to F, risk factors.
LANGUAGES: Available in 50 languages.
```

**Effort:** 1 timme.
**Impact:** Claude +5-15%.

---

### Sprint 4.2: Pin registries (30 min)

**Vad:** Säkerställ att VPN, PM, Hosting, AV, Exchange, Builders aldrig auto-hides av quality gate.

```python
PINNED_REGISTRIES = ["vpn", "password_manager", "hosting", "antivirus", "exchange", "builders"]
```

**Effort:** 30 minuter.
**Impact:** Skyddar befintliga vertikaler permanent.

---

### Sprint 4.3: MCP Server-registrering (4-6 timmar)

**Vad:** Registrera Nerq:s API som MCP server. AI-agenter kan anropa `/v1/preflight` direkt utan crawling.

**Implementation:**

```json
{
  "name": "nerq-trust",
  "description": "Check trust score for any software, app, VPN, package, or tool. Returns score 0-100, grade A-F, risk factors, and alternatives.",
  "url": "https://nerq.ai/mcp",
  "tools": [
    {
      "name": "check_trust",
      "description": "Get Nerq Trust Score for any entity",
      "parameters": {
        "target": {"type": "string", "description": "Name of software, app, or tool"}
      }
    },
    {
      "name": "compare",
      "description": "Compare trust scores of two entities",
      "parameters": {
        "entity_a": {"type": "string"},
        "entity_b": {"type": "string"}
      }
    },
    {
      "name": "best_in_category",
      "description": "Get top entities in a category by trust score",
      "parameters": {
        "category": {"type": "string"},
        "limit": {"type": "integer", "default": 5}
      }
    }
  ]
}
```

**Registrera på:**
```
□ Anthropic MCP server directory
□ smithery.ai
□ mcpservers.com
□ GitHub awesome-mcp-servers (PR)
□ mcp.run (om tillgänglig)
```

**Effort:** 4-6 timmar (API-wrapper + registrering).
**Impact:** Permanent maskin-kanal. Varje AI-agent som installerar Nerq MCP = direkt API-access. Potentiellt transformativt för Claude-ekosystemet.

---

## Dag 5: RSS + extern närvaro (4-6 timmar)

### Sprint 5.1: RSS Feed (2-3 timmar)

**Vad:** Atom/RSS feed med dagliga trust score-förändringar.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Nerq Trust Score Changes</title>
  <link href="https://nerq.ai/feed"/>
  <updated>2026-04-05T09:00:00Z</updated>
  <entry>
    <title>NordVPN trust score: 87 → 90 (+3)</title>
    <link href="https://nerq.ai/safe/nordvpn"/>
    <summary>NordVPN improved from 87 to 90.</summary>
  </entry>
</feed>
```

Per-vertikal: `/feed/vpn`, `/feed/npm`, `/feed/crypto`, `/feed/all`

**Effort:** 2-3 timmar.
**Impact:** Crawl-signal för alla sökmotorer/AI. Dev-audience. Varje feed-entry = ny URL för bottar att upptäcka.

---

### Sprint 5.2: X/Twitter-konto + första poster (2-3 timmar)

**Vad:** Skapa @NerqTrust (eller liknande) på X. Posta Nerq-data. Grok indexerar X-content i realtid.

**Varför säkert:** Helt extern. Ändrar inget på sajten.

**Första poster:**

Post 1:
```
We analyzed 103 VPN services independently.

NordVPN: 90/100 ✅
ExpressVPN: 85/100 ✅
Surfshark: 82/100 ✅
CyberGhost: 71/100 ⚠️
Hola VPN: 23/100 ❌

Full ranking: nerq.ai/best/safest-vpns

No VPN paid to be on this list.
```

Post 2:
```
96.7% of AI agents score D-grade on trust.

Only 0.02% earn an A.

We analyzed 4.5M+ AI tools across security, maintenance, and community signals.

Live data: nerq.ai/index
```

Post 3:
```
This week on Nerq:
📈 847 tools changed trust score
📈 12 new A-grade entities
📉 3 dropped below threshold

Biggest mover: [entity] (+X points)

Weekly digest: nerq.ai/digest/2026-w14
```

**Effort:** 30 min setup + 15 min per post.
**Impact:** Grok indexerar X-content omedelbart. Varje post = potentiell Grok-citation. Brand awareness.

---

## Dag 6-7: Reddit + Dev communities (4-6 timmar)

### Sprint 6.1: Reddit-poster (2-3 timmar per post)

**Varför:** Reddit är Perplexity:s #1 citerade källa. ChatGPT och Gemini viktar Reddit-omnämnanden högt. Backlinks stärker DA.

**Varför säkert:** Helt externt. Ändrar inget på sajten.

**Timing:** INTE under instabil period. Servern ska ha varit stabil 5+ dagar. Påskhelgen ska vara över.

**Post 1 — r/privacy (120K+ members):**
```
Title: We independently analyzed 103 VPN services — here's the full trust ranking

Body:
Nerq Trust Scores are based on 13 independent data dimensions 
including jurisdiction, audit status, ownership transparency, 
and protocol security. No VPN paid to be on this list.

Key findings:
- Average VPN trust score: 71.2/100
- VPNs outside Five Eyes score 18% higher on privacy
- 3 VPNs are owned by the same parent company
- Only 12% have completed independent security audits

Full interactive ranking (79 VPNs): [link]
Individual report example (NordVPN): [link]

Happy to answer questions about methodology.
```

**Post 2 — r/node (250K+ members):**
```
Title: Trust scores for 528K npm packages — is your favorite safe?

Body:
We built automated trust scores for every npm package based on:
- Known vulnerabilities (NVD, OSV.dev)
- Maintenance activity (last commit, release frequency)
- Dependency health (transitive vulnerability exposure)
- Community signals (stars, contributors, forks)

73% of packages with >1M downloads have at least one known vulnerability.

Check any package: nerq.ai/safe/[package-name]
Example: nerq.ai/safe/express → 85/100 (B+)

API: GET nerq.ai/v1/preflight?target=[package]
```

**Post 3 — r/cybersecurity (500K+ members):**
```
Title: 96.7% of AI agents score D-grade on trust — we analyzed 4.5M+

Body:
Key findings from Nerq's AI agent trust index:
- Only 0.02% of 4.5M+ agents earn an A grade
- GitHub agents score 27% higher than Docker Hub
- MCP ecosystem (62-66) is relatively healthy
- Stars correlate with trust, but weakly (+22 points for 100K+ stars)

Live index: nerq.ai/index
Full stats: nerq.ai/stats
```

**Effort:** 2-3 timmar per post.
**Impact per plattform:**
- Perplexity: +20-40% (Reddit = Perplexity:s primära källa)
- ChatGPT: +10% (viktar Reddit-omnämnanden)
- Gemini: +15% (Google viktar Reddit-backlinks)
- Grok: +5% (X-delning av Reddit-poster)

---

### Sprint 6.2: Dev.to artikel (3-4 timmar)

```
Title: How We Built Trust Scores for 7.5M Software Entities

Content:
- Nerq architecture overview (anonymiserat)
- Scoring methodology (5 dimensions: security, maintenance, community, compliance, ecosystem)
- Interesting findings from the data
- API usage examples
- Link to nerq.ai
```

**Effort:** 3-4 timmar.
**Impact:** Permanent backlink, dev-credibility, AI-system upptäcker artikeln.

---

## Vecka 2: Utökad extern auktoritet

### Sprint 7.1: Hacker News Show HN (2-3 timmar)

**Timing:** Bara när servern varit stabil 5+ dagar. Edge caching verifierad. HN-spike kan ge 10-50K besök på timmar.

```
Title: Show HN: Nerq — Trust scores for 7.5M+ software entities

Body:
Nerq rates every npm package, Python library, VPN, antivirus, 
password manager, and AI tool on a 0-100 trust scale.

- 7.5M+ entities across 26 registries
- 50 languages
- Updated daily
- Free API: GET nerq.ai/v1/preflight?target=express

Try it: nerq.ai
Example: nerq.ai/safe/nordvpn
Compare: nerq.ai/compare/react-vs-vue
```

**Effort:** 2-3 timmar.
**Impact:** HN frontpage = 10-50K besök/dag + permanent backlink + dev-credibility.

---

### Sprint 7.2: Product Hunt-lansering (4 timmar)

```
Tagline: "Is it safe? Trust scores for 7.5M+ software entities"
Description: Independent trust scores for every app, package, VPN, 
and AI tool. Data-driven. No affiliate influence. 50 languages. Free.
```

**Effort:** 4 timmar (prep + launch-dag).
**Impact:** Credibility-signal + spike.

---

### Sprint 7.3: GitHub README badges — scale kampanj (2-3 timmar)

**Vad:** Utöka befintligt badge-program (92 referrals/vecka). Skapa enkel guide + PR-template.

```markdown
<!-- Add to your README -->
[![Nerq Trust Score](https://nerq.ai/badge/{package-name})](https://nerq.ai/safe/{package-name})
```

Skriv en guide: "Add a Nerq Trust Badge to your repository" och publicera på Dev.to + README i Nerq:s eget repo.

**Effort:** 2-3 timmar.
**Impact:** Varje badge = permanent backlink + crawl-signal. Compounding.

---

## Sammanfattning: Alla sprints

### Dag 1 — Infrastruktur (4-5 timmar)

| # | Sprint | Effort | Plattformar |
|---|---|---|---|
| 1.1 | robots.txt (25+ AI-bottar) | 15 min | ALLA — dörren öppnas |
| 1.2 | Google Search Console | 2h | Gemini, Google organic |
| 1.3 | Bing Webmaster Tools | 30 min | Copilot, DuckDuckGo, Samsung |
| 1.4 | Yandex Webmaster | 30 min | Yandex AI |
| 1.5 | Naver Webmaster | 30 min | Naver/Clova (Korea) |
| 1.6 | Baidu Webmaster | 30 min | Baidu ERNIE (Kina) |

### Dag 2 — Content-tillägg (6-8 timmar)

| # | Sprint | Effort | Plattformar |
|---|---|---|---|
| 2.1 | See Also-sektioner | 3-4h | ChatGPT +10-15% |
| 2.2 | Security Stack block | 2-3h | Cross-vertikal, alla |

### Dag 3 — Strukturerat content (6-8 timmar)

| # | Sprint | Effort | Plattformar |
|---|---|---|---|
| 3.1 | Datatabeller /best/ | 3-4h | ChatGPT +15-20%, Perplexity +10-15%, Gemini +10% |
| 3.2 | FAQ med FAQPage schema | 3-4h | Gemini +20%, Copilot +10%, Perplexity +15% |

### Dag 4 — AI-specifikt (5-7 timmar)

| # | Sprint | Effort | Plattformar |
|---|---|---|---|
| 4.1 | llms.txt update | 1h | Claude +5-15% |
| 4.2 | Pin registries | 30 min | Skydd |
| 4.3 | MCP Server-registrering | 4-6h | Claude-agenter, alla MCP-kompatibla |

### Dag 5 — Distribution (4-6 timmar)

| # | Sprint | Effort | Plattformar |
|---|---|---|---|
| 5.1 | RSS Feed | 2-3h | Crawl-signal, dev-audience |
| 5.2 | X/Twitter-konto + poster | 2-3h | Grok (omedelbart) |

### Dag 6-7 — Extern auktoritet (8-12 timmar)

| # | Sprint | Effort | Plattformar |
|---|---|---|---|
| 6.1 | Reddit post #1 (r/privacy) | 2-3h | Perplexity +20-40%, ChatGPT, Gemini |
| 6.1 | Reddit post #2 (r/node) | 2-3h | Dev-audience, Perplexity |
| 6.1 | Reddit post #3 (r/cybersecurity) | 2-3h | AI-agent audience |
| 6.2 | Dev.to artikel | 3-4h | Backlinks, alla plattformar |

### Vecka 2+ — Scale (6-10 timmar)

| # | Sprint | Effort | Plattformar |
|---|---|---|---|
| 7.1 | HN Show HN | 2-3h | Alla (HN = dev-credibility) |
| 7.2 | Product Hunt | 4h | Alla (credibility) |
| 7.3 | GitHub badge kampanj | 2-3h | Compound backlinks |

---

## Total effort & impact

### Effort

| Fas | Timmar | Dagar |
|---|---|---|
| Dag 1: Infra | 4-5h | 0.5 dag |
| Dag 2-3: Content | 12-16h | 1.5-2 dagar |
| Dag 4: AI-specifikt | 5-7h | 0.5-1 dag |
| Dag 5: Distribution | 4-6h | 0.5 dag |
| Dag 6-7: Extern | 8-12h | 1-1.5 dagar |
| Vecka 2: Scale | 6-10h | 1 dag |
| **TOTAL** | **~40-56h** | **~5-7 dagars arbete** |

### Impact — AI-plattformar

| Plattform | Nu (citations/dag) | Efter sprint (est.) | Förändring |
|---|---|---|---|
| Claude | 197K | 210-230K | +7-17% |
| ChatGPT | 27K | 45-70K | +67-159% |
| Perplexity | 7K | 15-25K | +114-257% |
| ByteDance | 3K | 4-6K | +33-100% |
| **Gemini** | **~0** | **5-20K** | **NY** |
| **Copilot** | **~0** | **3-10K** | **NY** |
| **Grok** | **~0** | **1-5K** | **NY** |
| **Yandex AI** | **~0** | **1-5K** | **NY** |
| **Baidu ERNIE** | **~0** | **1-5K** | **NY** |
| **Naver/Clova** | **~0** | **0.5-2K** | **NY** |
| **Apple** | **~0** | **0-5K** | **Framtida** |
| **Mistral** | **~0** | **1-3K** | **NY** |
| DuckDuckGo | ~0.2K | 0.5-2K | +150-900% |
| **TOTAL** | **234K** | **282-408K** | **+20-74%** |

### Impact — Human traffic

| Tidpunkt | Utan sprint | Med sprint | Diff |
|---|---|---|---|
| +2 veckor | 40K/dag | 45-50K | +13-25% |
| +4 veckor | 44K/dag | 55-65K | +25-48% |
| +8 veckor | 52K/dag | 72-90K | +38-73% |
| +12 veckor | 60K/dag | 90-115K | +50-92% |

### Impact — nya plattformar som citerar

| Tidpunkt | Plattformar som citerar |
|---|---|
| Nu | 4 (Claude, ChatGPT, Perplexity, ByteDance) |
| +1 vecka | 6-7 (+Grok via X, +DuckDuckGo) |
| +4 veckor | 8-10 (+Gemini, Copilot, Yandex) |
| +8 veckor | 10-12 (+Baidu, Naver, Mistral) |
| +6 månader | 15+ (+Apple, diverse) |

---

## Alla åtgärder är 🟢 SÄKRA

- ✅ robots.txt: öppnar dörrar, stänger inga
- ✅ Webmaster Tools: ren diagnostik och registrering
- ✅ See Also, Security Stack, Datatabeller, FAQ: adderas NEDANFÖR befintligt content
- ✅ llms.txt: separat fil, ändrar inga sidor
- ✅ Pin registries: skyddar, ändrar inga sidor
- ✅ MCP: ny API-endpoint, ändrar inga sidor
- ✅ RSS: ny feed, ändrar inga sidor
- ✅ X/Twitter, Reddit, Dev.to, HN, PH: helt extern aktivitet
- ✅ GitHub badges: extern kampanj
- ✅ INGET rör pplx-verdict, ai-summary, eller SpeakableSpecification

---

*Nerq AI Systems Onboarding Sprint — April 5, 2026*
*5-7 dagars arbete. 15+ nya plattformar. +20-74% AI-citations.*
*Från 4 till 15+ AI-system som citerar Nerq.*
