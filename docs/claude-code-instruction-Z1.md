# Claude Code Instruktion — Z1.0: ZARQ Token Safety Pages

## Kontext

Du arbetar i ~/agentindex/ — en FastAPI-app (discovery.py) som serverar zarq.ai och nerq.ai via Cloudflare Tunnel. Backend: Python/FastAPI, templates: Jinja2, databas: SQLite (~/agentindex/agentindex/crypto/crypto_trust.db), CSS/design: se ~/agentindex/agentindex/nerq_design.py för Nerq-sidor och ~/agentindex/agentindex/crypto/templates/ för ZARQ-sidor.

ZARQ:s befintliga tema: DM Serif Display för headings, JetBrains Mono för data, warm palette (#F5F0EB bakgrund, #2C2C2C text, #C85A3A accent). Se befintliga templates i ~/agentindex/agentindex/crypto/templates/ för exakt styling (zarq_dashboard.html är referens).

API-endpoint `/v1/check/{token}` returnerar redan all data vi behöver. Kolla dess response-format i discovery.py.

## Mål

Skapa 205 SEO-optimerade token-sidor på zarq.ai/token/{slug} som fångar "is [token] safe" söktrafik. Varje sida visar ZARQ:s befintliga data i ett format optimerat för Google-indexering och AI-citering.

## Steg-för-steg

### 1. Förstå befintlig data

Läs discovery.py och hitta `/v1/check/{token}` endpointen. Notera exakt vilka fält som returneras (trust score, rating, crash probability, signals, distance-to-default, etc). Läs också crypto_trust.db schema — kolla tabellerna med `sqlite3 ~/agentindex/agentindex/crypto/crypto_trust.db ".tables"` och `.schema` för de relevanta tabellerna.

### 2. Generera token-lista

Skapa en lista med alla tokens som har ratings i databasen. Spara som ~/agentindex/agentindex/crypto/token_slugs.json — en lista med objekt: `{"slug": "bitcoin", "symbol": "BTC", "name": "Bitcoin"}`. Slugs ska vara lowercase, bindestreck istället för mellanslag.

### 3. Skapa Jinja2-template

Skapa ~/agentindex/agentindex/crypto/templates/token_page.html:

**Struktur:**
- HTML head med title: "[Token Name] Risk Assessment — ZARQ Trust Score [Rating]" och meta description: "Is [token] safe? ZARQ rates [token] [rating] with [crash_prob]% crash probability. See 7 risk signals, distance-to-default analysis, and structural warnings."
- Open Graph tags (og:title, og:description, og:type=article)
- JSON-LD structured data (se nedan)
- Hero-sektion: Stort Trust Score badge (visuellt, rating som Aaa/Baa/etc), crash probability gauge
- H1: "Is [Token Name] Safe? — Trust Score: [Rating]"
- Sektion "Risk Assessment": 2-3 dynamiska meningar baserade på rating-nivå och signaler. Exemepel: om rating >= Baa: "ZARQ rates [token] as investment grade with moderate risk." Om rating < Caa: "[Token] shows significant structural weakness."
- Sektion "7 Risk Signals": Visa alla Distance-to-Default signaler med förklaring och aktuellt värde per signal. Varje signal som en rad med namn, värde, och en kort förklaring.
- Sektion "Crash Probability": Nuvarande crash probability med visuell gauge/bar
- Sektion "Structural Analysis": Visa om tokenen har Structural Collapse eller Structural Stress warning
- Sektion "Compare": Länka till 3-5 tokens i samma rating-kategori (intern länkning)
- FAQ-sektion: 3 frågor med svar (H2 + p-taggar, INTE accordion/JS)
- Footer med länk till /tokens hub och API endpoint

**JSON-LD (i <script type="application/ld+json">):**
```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "Is [Token] safe to invest in?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "ZARQ rates [Token] [Rating] with a crash probability of [X]%. [dynamisk text baserat på rating]"
      }
    },
    {
      "@type": "Question",
      "name": "What is [Token]'s risk rating?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "[Token] has a ZARQ Trust Score of [Rating], based on 7 quantitative risk signals including distance-to-default analysis."
      }
    },
    {
      "@type": "Question",
      "name": "Will [Token] crash?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "ZARQ's crash model estimates [Token]'s crash probability at [X]%. [Om structural warning finns, nämn det]"
      }
    }
  ]
}
```

Lägg också till en separat WebPage schema:
```json
{
  "@context": "https://schema.org",
  "@type": "WebPage",
  "name": "[Token] Risk Assessment",
  "description": "...",
  "publisher": {
    "@type": "Organization",
    "name": "ZARQ",
    "url": "https://zarq.ai"
  },
  "dateModified": "[dagens datum]"
}
```

**Styling:** Använd exakt samma design-system som befintliga ZARQ-sidor (se zarq_dashboard.html och zarq_cascade.html). DM Serif Display headings, JetBrains Mono för data, warm palette. Ren server-side HTML + CSS, inget JavaScript-framework. Mobile responsive.

### 4. Skapa hub-sida

Skapa ~/agentindex/agentindex/crypto/templates/tokens_index.html:
- H1: "Crypto Risk Ratings — 205 Tokens Rated by ZARQ"
- Sökbar/filtrerbar tabell med alla tokens: namn, symbol, rating, crash probability, strukturell status
- Varje rad länkar till /token/{slug}
- JSON-LD ItemList schema
- Sorterbar via JavaScript (enkel client-side sort, inga dependencies)

### 5. Lägg till routes i discovery.py

Lägg till i discovery.py (hitta rätt ställe bland befintliga routes):

```python
@app.get("/token/{slug}", response_class=HTMLResponse)
async def token_page(slug: str, request: Request):
    # Hämta token-data från crypto_trust.db
    # Hämta liknande tokens för "Compare" sektionen
    # Rendera template
    ...

@app.get("/tokens", response_class=HTMLResponse)
async def tokens_index(request: Request):
    # Hämta alla tokens med ratings
    # Rendera hub-template
    ...
```

**Viktigt:**
- Använd samma mönster som befintliga HTML-routes i discovery.py
- Kolla host-header för att skilja zarq.ai vs nerq.ai requests (befintligt mönster i koden)
- SQLite-queryn ska vara effektiv — en query för all data, inte ett API-anrop per token

### 6. Skapa sitemap

Skapa/uppdatera sitemap för tokens:
- Ny fil eller uppdatera befintlig sitemap-generering
- Alla 205 /token/{slug} URLs + /tokens hub
- `<lastmod>` med dagens datum
- `<changefreq>weekly</changefreq>`
- `<priority>0.8</priority>` för individuella sidor, `1.0` för hub

### 7. Intern länkning

Uppdatera befintliga sidor att länka till de nya:
- ZARQ dashboard (zarq_dashboard.html): lägg till "Token Ratings" länk i navigationen
- ZARQ cascade/crash-sidor: länka till relevanta token-sidor

### 8. Testa

- Starta servern: `cd ~/agentindex && python -m agentindex.api.discovery`
- Testa en token-sida: `curl -H "Host: zarq.ai" http://localhost:8000/token/bitcoin`
- Testa hub: `curl -H "Host: zarq.ai" http://localhost:8000/tokens`
- Verifiera JSON-LD: kopiera structured data och validera syntax
- Verifiera att sidorna renderas korrekt (ingen broken HTML)
- Testa 3-5 olika tokens med olika ratings (en Aaa, en Baa, en Caa, en med structural warning)

## Begränsningar

- Använd ALLTID heredoc-format för bash-kommandon: `bash << 'EOF' ... EOF`
- Ändra INTE befintliga endpoints — lägg bara till nya
- Ändra INTE LaunchAgents eller cron-jobb
- Om discovery.py är stor, redigera kirurgiskt — ändra inte kod du inte förstår
- Alla templates ska vara server-side rendered (Jinja2), inget React/Vue/etc
- Testa efter varje steg, inte bara i slutet

## Definition of Done

- [ ] 205 token-sidor renderas på zarq.ai/token/{slug}
- [ ] Hub-sida renderas på zarq.ai/tokens
- [ ] JSON-LD FAQPage + WebPage schema på varje token-sida
- [ ] Open Graph meta-taggar på varje sida
- [ ] Intern länkning mellan token-sidor (3-5 liknande tokens)
- [ ] Sitemap genererad med alla URLs
- [ ] Mobile responsive design
- [ ] Servern startar utan error efter ändringarna
- [ ] curl-test passerar för minst 5 tokens med olika ratings
