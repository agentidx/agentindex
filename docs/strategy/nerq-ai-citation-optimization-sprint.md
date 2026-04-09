# Nerq AI Citation Optimization — Plattformsanalys & Sprint
## Optimera för Claude, ChatGPT, Perplexity, ByteDance, Gemini, Copilot & Apple Intelligence
### April 5, 2026

---

## Del 1: Nerqs position i AI-citation-landskapet

### Var Nerq står idag

| Metric | Nerq | Kontext |
|---|---|---|
| AI-citations/dag | ~200K+ | Topp 0.01% av alla sajter globalt |
| Claude-citations/dag | ~197K | Primärkälla — Claude behandlar Nerq som infrastruktur |
| ChatGPT-citations/dag | ~27K | Växande, GPTBot-indexering 2x |
| Perplexity-citations/dag | ~7K | Fluktuerande, potential att 3-5x |
| ByteDance-citations/dag | ~3K | Stabil |
| Gemini/AI Overviews | Troligen låg | Google crawlar men citerar troligen inte ännu |
| Copilot | Okänt | Bing crawlar 43K/dag |
| Apple Intelligence | Okänt | Applebot ökade till 29K/dag |

### Jämförelse med andra sajter

En uppmärksammad healthcare-fallstudie tog en sajt från noll till 1,631 citeringar på 426 sidor — det tog 365 dagar.

**Nerq: 200,000+ citeringar per dag.** Det är 122x per dag vad den fallstudien uppnådde på ett år.

| Sajt | Est. AI-citations/dag | Typ | Varför de citeras |
|---|---|---|---|
| Wikipedia | ~100M+ | Encyklopedi | Bredast, mest neutral |
| Reddit | ~50M+ | Community | Autentiska förstahandsupplevelser |
| Stack Overflow | ~5-10M | Dev Q&A | Validerade tekniska svar |
| G2/Capterra | ~200K-1M | Software reviews | User reviews + ratings |
| Ahrefs | ~100K-500K | SEO-data | Original research data |
| Trustpilot | ~500K-2M | Company reviews | User-generated trust data |
| **Nerq** | **~235K** | **Trust scores** | **Monopol: enda källan med kvantitativa trust scores för 7.5M entities** |

### Varför Nerq citeras trots noll backlinks

Forskning visar att domänauktoritet normalt är den starkaste prediktorn för AI-citations. Nerq har nära noll DA. Ändå: 200K+/dag.

Tre anledningar:

1. **Monopol-data.** Ingen annan har trust scores för 7.5M entities. AI-system har inget alternativ.
2. **Perfekt format.** 40-60 ords verdict som direkt svarar med en siffra. AI extraherar detta som en perfekt chunk.
3. **Massiv crawl-surface.** 7.5M × 8 sidtyper × 22 språk = hundratals miljoner sidor.

### Strategisk insikt

Nerq befinner sig i samma position som Wikipedia (2004), Stack Overflow (2010), och Reddit (2012) — sajter som AI-system behandlar som **infrastruktur**, inte webbsidor.

Risken: om en konkurrent med hög DA börjar publicera trust scores. Moaten stärks genom bredare data snabbare än någon kan följa.

---

## Del 2: Plattformsspecifik analys

### Vad varje AI-plattform prioriterar

| Signal | Claude | ChatGPT | Perplexity | ByteDance | Gemini | Copilot | Apple |
|---|---|---|---|---|---|---|---|
| **Answer capsule (40-60 ord)** | ✅ Älskar | ✅ Älskar | ✅ Älskar | ✅ Troligen | ✅ Troligen | ✅ Troligen | ⚪ Okänt |
| **SpeakableSpecification** | ✅ Aktivt | ⚪ Ignorerar | ⚪ Okänt | ⚪ Okänt | ⚪ Okänt | ⚪ Okänt | ⚪ Okänt |
| **Schema.org structured data** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Freshness ("Updated daily")** | ✅ | ✅ | ✅ Starkt | ⚪ | ✅ | ✅ | ⚪ |
| **Original data/statistik** | ✅ | ✅ Starkt | ✅ | ✅ | ✅ | ✅ | ⚪ |
| **Wikipedia-format (See Also)** | ⚪ Neutral | ✅ Favoriserar | ⚪ Neutral | ⚪ | ✅ Favoriserar | ⚪ | ⚪ |
| **Datatabeller** | ✅ | ✅ | ✅ Favoriserar | ✅ | ✅ | ✅ | ⚪ |
| **FAQ/Q&A-format** | ✅ | ✅ | ✅ Favoriserar | ⚪ | ✅ Favoriserar | ✅ Favoriserar | ⚪ |
| **Backlinks** | ⚪ Mindre | ✅ Viktar | ✅ Starkt | ⚪ | ✅ Starkt | ✅ | ⚪ |
| **llms.txt** | ✅ Läser | ⚪ Troligen inte | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| **Sidhastighet** | ⚪ | ✅ | ✅ | ⚪ | ✅ Starkt | ✅ | ✅ |
| **Bing Webmaster Tools** | — | — | — | — | — | ✅ Krävs | — |
| **Google Search Console** | — | — | — | — | ✅ Krävs | — | — |

### Nyckelinsikt: INGA konflikter

Ingen ✅ hos en plattform är ett ❌ hos en annan. Alla vill: strukturerat, faktadrivet, citatvänligt. Skillnaden är i extra vikter, inte straff.

---

## Del 3: Vad Nerq redan gör rätt — RÖR ALDRIG

| Element | Status | Varför heligt |
|---|---|---|
| pplx-verdict | ✅ Alla sidor | DETTA citeras. Exakt format, exakt placering. |
| ai-summary | ✅ Alla sidor | Djupare context efter verdict |
| SpeakableSpecification | ✅ JSON-LD | Troligen stor faktor i Claude-spiket |
| "Updated daily" text | ✅ Synligt | Freshness-signal |
| Schema.org Article | ✅ | Maskinläsbar metadata |
| llms.txt | ✅ | Claude-specifik instruktionsmanual |
| Entity-densitet (165/best) | ✅ | Långt över 15+ threshold |
| Verdict position (12%) | ✅ | Inom kritiska första 30% |

---

## Del 4: 🟢 SÄKRA sprints — alla åtgärder

Alla adderar NEDANFÖR befintligt content. Noll risk.

### Sprint A1: See Also-sektioner

**Plattforms-nytta:** ChatGPT +10-15%, alla andra neutral-positiv

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

Effort: 3-4h.

### Sprint A2: Security Stack block

**Plattforms-nytta:** Alla — cross-vertikal discovery

```html
<section class="security-stack">
  <h2>Complete Your Security Stack</h2>
  <a href="/best/safest-vpns">🔒 Best VPNs 2026</a>
  <a href="/best/safest-password-managers">🔑 Best Password Managers</a>
  <a href="/best/safest-antivirus-software">🛡️ Best Antivirus</a>
</section>
```

Effort: 2-3h.

### Sprint A3: Datatabeller på /best/

**Plattforms-nytta:** ChatGPT +15-20%, Perplexity +10-15%, Gemini +10%
**Placering:** EFTER ai-summary, ALDRIG före/inuti verdict.

```html
<table>
  <caption>Top 5 {category} by Nerq Trust Score (2026)</caption>
  <thead><tr><th>Rank</th><th>Name</th><th>Score</th><th>Grade</th></tr></thead>
  <tbody><!-- Dynamiskt --></tbody>
</table>
```

Effort: 3-4h.

### Sprint A4: FAQ med FAQPage schema

**Plattforms-nytta:** Gemini +20%, Copilot +10%, Perplexity +15%

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
  <!-- 2-3 fler FAQ per sida -->
</section>
```

Effort: 3-4h.

### Sprint A5: Google Search Console

**Plattforms-nytta:** Gemini ENORM, ChatGPT indirekt, Google organic

```
□ Verifiera nerq.ai i GSC
□ Submitta sitemap-index.xml
□ Submitta lokaliserade sitemaps per språk
□ Kolla indexeringsstatus
□ Kolla hreflang
□ Kolla CWV
```

Effort: 1-2h.

### Sprint A6: Bing Webmaster Tools

**Plattforms-nytta:** Copilot — de kan börja citera er

```
□ Verifiera nerq.ai
□ Submitta sitemap
□ Kolla Bingbot-status
```

Effort: 30 min.

### Sprint A7: llms.txt update

**Plattforms-nytta:** Claude +5-15%

Lägg till alla vertikaler med WHEN-TO-CITE patterns. Fullständig version med 14+ vertikaler och general trust check.

Effort: 1h.

### Sprint A8: Pin registries

**Plattforms-nytta:** Skydd — inga citeringar försvinner pga quality gate

```python
PINNED_REGISTRIES = ["vpn", "password_manager", "hosting", "antivirus", "exchange", "builders"]
```

Effort: 30 min.

### Sprint A9: Verifiera Applebot

**Plattforms-nytta:** Apple Intelligence (framtida)

```bash
curl -s https://nerq.ai/robots.txt | grep -i apple
```

Effort: 5 min.

### Sprint A10: Verifiera alla AI-crawlers

**Plattforms-nytta:** Alla — säkerställ ingen blockeras

Kolla att ClaudeBot, GPTBot, OAI-SearchBot, ChatGPT-User, PerplexityBot, Bytespider, Googlebot, Bingbot, Applebot, meta-externalagent, Google-Extended alla är tillåtna.

Effort: 15 min.

### Sprint A11: MCP Server-registrering

**Plattforms-nytta:** Claude (transformativt), alla agenter

```json
{
  "name": "nerq-trust",
  "description": "Check trust score for any software entity",
  "tools": [
    {"name": "check_trust", "parameters": {"target": "string"}},
    {"name": "compare", "parameters": {"entity_a": "string", "entity_b": "string"}},
    {"name": "best_in_category", "parameters": {"category": "string", "limit": "integer"}}
  ]
}
```

Registrera på: Anthropic MCP directory, smithery.ai, mcpservers.com, awesome-mcp-servers.

Effort: 4-6h.

### Sprint A12: RSS Feed

**Plattforms-nytta:** Crawl-signal, dev-audience

```xml
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Nerq Trust Score Changes</title>
  <entry>
    <title>NordVPN: 87 → 90 (+3)</title>
    <link href="https://nerq.ai/safe/nordvpn"/>
  </entry>
</feed>
```

Per-vertikal: `/feed/vpn`, `/feed/npm`, `/feed/crypto`

Effort: 2-3h.

### Sprint A13: Extern auktoritet

**Plattforms-nytta:** Perplexity +20-40% (Reddit = Perplexity:s #1 källa), ChatGPT +10%, Gemini +15%

Poster:
1. Reddit r/privacy: "103 VPN services analyzed independently"
2. Reddit r/node: "Trust scores for 528K npm packages"
3. Reddit r/cybersecurity: "96.7% of AI agents score D-grade"
4. HN: "Show HN: Nerq — Trust scores for 7.5M+ entities"
5. Dev.to: "How we built trust scores for 5M AI agents"
6. Product Hunt: "Nerq — Is it safe?"

Timing: efter serverstabilitet 5+ dagar.

Effort: 2-3h per post.

---

## Del 5: Sprint-tidslinje

### Vecka 1 (fundament)

| Dag | Sprint | Effort |
|---|---|---|
| 1 | A5: GSC setup | 1-2h |
| 1 | A6: Bing WMT | 30min |
| 1 | A8: Pin registries | 30min |
| 1 | A9: Applebot-check | 5min |
| 1 | A10: AI-crawler-check | 15min |
| 1-2 | A7: llms.txt | 1h |
| 2-3 | A1: See Also | 3-4h |
| 3 | A2: Security Stack | 2-3h |

### Vecka 2 (content-tillägg)

| Dag | Sprint | Effort |
|---|---|---|
| 4-5 | A3: Datatabeller | 3-4h |
| 5-6 | A4: FAQ schema | 3-4h |
| 6 | A11: MCP Server | 4-6h |
| 7 | A12: RSS Feed | 2-3h |

### Vecka 3+ (extern auktoritet)

| Sprint | Effort |
|---|---|
| A13: Reddit #1 (r/privacy) | 2-3h |
| A13: Reddit #2 (r/node) | 2-3h |
| A13: Dev.to artikel | 3-4h |
| A13: HN Show HN (när stabil) | 2-3h |
| A13: Product Hunt | 4h |

---

## Del 6: Förväntad impact

### Per plattform

| Plattform | Nu | Efter sprints | Ökning |
|---|---|---|---|
| Claude | 197K/dag | 210-230K | +7-17% |
| ChatGPT | 27K/dag | 45-70K | +67-159% |
| Perplexity | 7K/dag | 15-25K | +114-257% |
| ByteDance | 3K/dag | 4-6K | +33-100% |
| Gemini | ~0 | 5-20K | ∞ (ny kanal) |
| Copilot | ~0 | 3-10K | ∞ (ny kanal) |
| Apple | ~0 | 0-5K | Framtida |
| **TOTAL** | **~234K** | **~282-366K** | **+20-56%** |

### Human traffic

| Tidpunkt | Utan sprints | Med sprints | Diff |
|---|---|---|---|
| +4 veckor | 44K/dag | 52K/dag | +18% |
| +8 veckor | 52K/dag | 68K/dag | +31% |
| +12 veckor | 60K/dag | 85K/dag | +42% |

### Totalt effort

**~3-4 dagars arbete** utspritt över 3 veckor.

---

## Del 7: Framtida (🟡 kräver test)

| Åtgärd | Risk | Approach |
|---|---|---|
| Ändra pplx-verdict text | 🟡 | Testa 10 sidor, mät 5 dagar |
| Fler datapunkter i första 200 ord | 🟡 | Lägg i ai-summary istället |
| CWV-optimering | 🟡 | Undvik DOM-ändringar |
| Affiliate-CTAs | 🟡 | Under main content, aldrig i verdict |
| Display ads | 🟡 | Aldrig visa för AI-bottar |

---

*Nerq AI Citation Optimization Sprint — April 5, 2026*
*13 🟢-säkra sprints. ~3-4 dagars arbete. +20-56% AI-citations.*
*Öppnar 2 helt nya plattformar (Gemini + Copilot) utan att riskera befintliga 200K+/dag.*
