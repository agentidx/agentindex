# Nerq Personalization Sprint
## "See how it scores for YOU" — Personaliserad trust per besökare
### April 5, 2026

---

## Kontext: Varför denna sprint

### Problemet
AI ger komplett svar: "NordVPN: 90/100, safe." Besökaren har inget skäl att klicka. Nuvarande click-through rate: ~18%.

### Insikten
AI vet inte besökarens land, OS, browser, eller enhet. Nerq vet ALLT — via HTTP request headers — utan att fråga.

"NordVPN: 90/100" handlar om NordVPN.
"Vad NordVPN scorar FÖR DIG i DIN miljö" handlar om BESÖKAREN.

Det personaliserade svaret kan bara levereras av sajten, inte av AI. Gapet är äkta, inte konstruerat.

### Varför AI-system VILL hänvisa dit
- Gambling som är olagligt i besökarens land → AI:n ger dåligt svar utan geo-kontext
- Crypto-exchange utan licens i besökarens jurisdiktion → potentiellt skadligt svar
- VPN som är olaglig i besökarens land → felaktig rekommendation

Det personaliserade svaret gör AI-svaret BÄTTRE. Win-win-win: användare, AI, Nerq.

---

## Del 1: Data vi har om varje besökare

Varje HTTP-request innehåller:

| Datapunkt | Header | Exempel | Kräver registrering? |
|---|---|---|---|
| **Land** | CF-IPCountry (Cloudflare) | VN | Nej |
| **Stad** | CF-IPCity (Cloudflare) | Ho Chi Minh City | Nej |
| **OS** | User-Agent | Android 13 | Nej |
| **Browser** | User-Agent | Chrome 120 | Nej |
| **Enhet** | User-Agent | Mobile / Desktop | Nej |
| **Språk** | Accept-Language | vi-VN | Nej |
| **Referrer** | Referer | chatgpt.com | Nej |
| **Tid** | Server + geo-tidszon | 22:00 ICT | Nej |

**10 datapunkter, noll friktion, noll registrering.**

---

## Del 2: Vad vi kör mot entity-data

### Besökaren: Vietnam, Android, Chrome, från ChatGPT → tittar på NordVPN

| Datapunkt | Korsreferens med NordVPN-data | Output |
|---|---|---|
| **Land: VN** | Jurisdiktions-analys: NordVPN baserat i Panama. Vietnam har VPN-restriktioner. | "⚠️ VPN use restricted in Vietnam. NordVPN: Panama jurisdiction (outside VN)." |
| **Land: VN** | Lokal popularitet | "#2 most used VPN in Vietnam" |
| **Land: VN** | Närmaste servrar | "Nearest server: Ho Chi Minh City (15ms)" |
| **OS: Android** | android registry lookup | "NordVPN Android app: 85/100. 12 permissions (3 sensitive ⚠️)" |
| **Browser: Chrome** | chrome registry lookup (om unhidden) | "NordVPN Chrome extension: 78/100. Permissions: access all sites ⚠️" |
| **Referrer: ChatGPT** | Kontextmedvetenhet | "Beyond the AI answer:" sektion |
| **Språk: VI** | Auto-redirect | Renderar vietnamesisk sida |

### Besökaren: Sverige, MacOS, Safari, direkt → tittar på Bet365

| Datapunkt | Korsreferens med Bet365-data | Output |
|---|---|---|
| **Land: SE** | Licensstatus per land: Bet365 har svensk licens via Spelinspektionen | "✅ Licensed in Sweden (Spelinspektionen). Legal to use." |
| **OS: MacOS** | Desktop-app tillgänglighet | "No desktop app. Web-based only." |
| **Browser: Safari** | Safari-kompatibilitet | "Full Safari compatibility ✅" |
| **Land: SE** | Lokala alternativ | "Swedish-licensed alternatives: Unibet (84/100), Betsson (81/100)" |

### Besökaren: Tyskland, iPhone, Safari, från Perplexity → tittar på Binance

| Datapunkt | Korsreferens med Binance-data | Output |
|---|---|---|
| **Land: DE** | Regulering: BaFin-status, EU-restriktioner | "⚠️ Binance: restricted in Germany since 2024. Licensed alternatives: Kraken, Bitstamp." |
| **OS: iOS** | ios registry lookup | "Binance iOS app: 79/100. Region-restricted features apply." |
| **Land: DE** | GDPR-compliance | "Data processing: non-EU jurisdiction ⚠️" |

---

## Del 3: Vilka vertikaler kan personaliseras?

### STARK personalisering (3+ datapunkter = genuint annorlunda svar)

| # | Vertikal | Land | OS | Browser | Enhet | Nyckel-personalisering |
|---|---|---|---|---|---|---|
| 1 | **VPN** | ✅ | ✅ | ✅ | ✅ | Legalitet, servrar, app-score, extension-score |
| 2 | **Antivirus** | ✅ | ✅ | ✅ | ✅ | Helt olika produkter per OS |
| 3 | **Password Managers** | ✅ | ✅ | ✅ | ✅ | Extension-score per browser |
| 4 | **Android apps** | ✅ | ✅ | — | ✅ | Bara relevant om Android |
| 5 | **iOS apps** | ✅ | ✅ | — | ✅ | Bara relevant om iOS |
| 6 | **Chrome extensions** | ✅ | — | ✅ | ✅ | Bara relevant om Chrome |
| 7 | **Firefox extensions** | ✅ | — | ✅ | ✅ | Bara relevant om Firefox |
| 8 | **Gambling/betting** | ✅✅ | ✅ | — | ✅ | Licensstatus PER LAND — kritiskt |
| 9 | **Crypto exchanges** | ✅✅ | ✅ | — | ✅ | Regulering per land — avgörande |
| 10 | **Neobanker** | ✅✅ | ✅ | — | ✅ | Licens, tillgänglighet per land |
| 11 | **Datingappar** | ✅ | ✅ | — | ✅ | Tillgänglighet, lokala alternativ |
| 12 | **Streaming** | ✅ | ✅ | — | ✅ | Content varierar per land |
| 13 | **Matleverans** | ✅ | ✅ | — | ✅ | Tillgänglighet per stad |
| 14 | **Taxi/ride-hailing** | ✅ | ✅ | — | ✅ | Tillgänglighet per stad |
| 15 | **Online apotek** | ✅✅ | — | — | — | Regulering per land |
| 16 | **Teleoperatörer** | ✅✅ | — | — | ✅ | 100% land-specifikt |
| 17 | **Energibolag** | ✅✅ | — | — | — | 100% land-specifikt |
| 18 | **Försäkring** | ✅✅ | — | — | — | 100% land-specifikt |
| 19 | **Banker** | ✅✅ | ✅ | — | ✅ | Land-specifikt + app-score |
| 20 | **Flygbolag** | ✅ | — | — | ✅ | Rutter från besökarens land |
| 21 | **Hotell** | ✅ | — | — | ✅ | Priser i lokal valuta |
| 22 | **Resebyråer** | ✅ | — | — | — | Opererar i besökarens land? |
| 23 | **SaaS** | ✅ | ✅ | ✅ | ✅ | GDPR-relevans, app/extension |
| 24 | **Web hosting** | ✅ | — | — | — | Serverplats nära besökaren |
| 25 | **Website builders** | ✅ | — | — | — | Regionala priser |

**25 vertikaler. Troligen 60-70% av all trafik.**

### MEDIUM personalisering (1-2 datapunkter)

~25 vertikaler: npm, pypi, crates, go (OS → installationsinfo), countries (visum från besökarens land), universitet (antagningskrav per land), leksaker/djurmat/barnprodukter (recalls per region), bilsäkerhet (EuroNCAP vs NHTSA per geo), smart home (iOS → HomeKit, Android → Google Home).

### SVAG/INGEN personalisering

~50 vertikaler: mestadels teknik-specifika (API trust, DNS, CDN), nischade (esports, fraktbolag), eller sådana där geo/OS inte ger meningsfullt annorlunda svar.

---

## Del 4: Implementation

### Arkitektur

```
Besökare klickar nerq.ai/safe/nordvpn
         │
         ▼
FastAPI tar emot request
         │
         ├── Extrahera visitor_context från headers
         │   (land, OS, browser, enhet, referrer, språk)
         │
         ├── Bot-check: är det en AI-bot?
         │   ├── JA → rendera standard-sida (ingen personalisering)
         │   └── NEJ → fortsätt
         │
         ├── Hämta entity-data (NordVPN, vpn registry)
         │
         ├── Korsreferera:
         │   ├── Geo: jurisdiktion, legalitet, lokala alternativ
         │   ├── OS: app i android/ios registry
         │   ├── Browser: extension i chrome/firefox registry
         │   └── Referrer: "beyond AI" sektion om från AI
         │
         ├── Rendera standard-sida (pplx-verdict + ai-summary + data)
         │   PLUS
         └── Rendera "For You" sektion (dynamisk, server-side)
```

### Python implementation

```python
from fastapi import Request

# ============================================
# STEG 1: Extrahera besökarkontext
# ============================================

AI_BOT_PATTERNS = [
    "ClaudeBot", "Claude-SearchBot", "Claude-User",
    "GPTBot", "OAI-SearchBot", "ChatGPT-User",
    "PerplexityBot", "Perplexity-User",
    "Bytespider", "Googlebot", "Bingbot",
    "Applebot", "meta-externalagent",
    "GrokBot", "DeepSeekBot", "MistralAI-User",
]

def get_visitor_context(request: Request) -> dict | None:
    ua = request.headers.get("user-agent", "")
    
    # Bot-detection
    if any(b.lower() in ua.lower() for b in AI_BOT_PATTERNS):
        return None
    
    country = request.headers.get("cf-ipcountry", "")
    city = request.headers.get("cf-ipcity", "")
    
    # OS detection
    if "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"
    elif "Android" in ua:
        os_name = "Android"
    elif "Macintosh" in ua:
        os_name = "macOS"
    elif "Windows" in ua:
        os_name = "Windows"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = None
    
    # Browser detection
    if "Firefox" in ua:
        browser = "Firefox"
    elif "Edg" in ua:
        browser = "Edge"
    elif "Safari" in ua and "Chrome" not in ua:
        browser = "Safari"
    elif "Chrome" in ua:
        browser = "Chrome"
    else:
        browser = None
    
    # Referrer
    referrer = request.headers.get("referer", "")
    ai_sources = ["chatgpt.com", "chat.openai.com", "perplexity.ai",
                  "claude.ai", "gemini.google.com", "copilot.microsoft.com"]
    from_ai = any(x in referrer for x in ai_sources)
    
    # Språk
    accept_lang = request.headers.get("accept-language", "en")
    lang = accept_lang.split(",")[0].split("-")[0]
    
    return {
        "country": country,
        "city": city,
        "os": os_name,
        "browser": browser,
        "is_mobile": "Mobile" in ua or "Android" in ua,
        "from_ai": from_ai,
        "language": lang,
    }


# ============================================
# STEG 2: Generera "For You" sektion
# ============================================

def generate_for_you(entity, registry, visitor, db) -> str:
    if visitor is None:
        return ""  # Bot — ingen personalisering
    
    sections = []
    country = visitor["country"]
    os_name = visitor["os"]
    browser = visitor["browser"]
    
    # --- GEO-SEKTION ---
    if country:
        geo = generate_geo_section(entity, registry, country, db)
        if geo:
            sections.append(geo)
    
    # --- ENHETS-SEKTION ---
    if os_name in ("Android", "iOS"):
        app_reg = "android" if os_name == "Android" else "ios"
        app = db.find_entity_in_registry(entity.name, app_reg)
        if app:
            sections.append(generate_app_section(app, os_name))
    
    # --- BROWSER-SEKTION ---
    if browser in ("Chrome", "Firefox"):
        ext_reg = "chrome" if browser == "Chrome" else "firefox"
        ext = db.find_entity_in_registry(entity.name, ext_reg)
        if ext:
            sections.append(generate_extension_section(ext, browser))
    
    # --- CROSS-REGISTRY ---
    related = db.find_across_registries(entity.name)
    if len(related) > 1:
        sections.append(generate_cross_registry(related, entity.name))
    
    # --- AI-REFERRAL ---
    if visitor["from_ai"]:
        sections.append(generate_beyond_ai(entity, country))
    
    if not sections:
        return ""
    
    return render_template("for_you.html", 
                          entity=entity, 
                          sections=sections,
                          visitor=visitor)


# ============================================
# STEG 3: Geo-specifika funktioner
# ============================================

def generate_geo_section(entity, registry, country, db) -> dict | None:
    
    # VPN: legalitet + jurisdiktion + servrar
    if registry == "vpn":
        legal_status = get_vpn_legality(country)
        jurisdiction = entity.metadata.get("jurisdiction", "Unknown")
        servers = get_nearest_servers(entity, country)
        local_rank = get_local_popularity(entity, country, registry)
        return {
            "type": "geo",
            "title": f"In {country_name(country)}",
            "items": [
                {"label": "Legal status", "value": legal_status, 
                 "icon": "✅" if legal_status == "Legal" else "⚠️"},
                {"label": "Jurisdiction", "value": jurisdiction},
                {"label": "Nearest server", "value": servers},
                {"label": "Local popularity", "value": f"#{local_rank}"},
            ]
        }
    
    # Gambling: licensstatus per land
    elif registry == "gambling":
        license = get_gambling_license(entity, country)
        return {
            "type": "geo",
            "title": f"In {country_name(country)}",
            "items": [
                {"label": "Licensed", "value": license["status"],
                 "icon": "✅" if license["licensed"] else "❌"},
                {"label": "Regulator", "value": license.get("regulator", "None")},
                {"label": "Legal to use", "value": license["legal_status"]},
            ]
        }
    
    # Crypto: regulering per land
    elif registry == "exchange":
        reg = get_crypto_regulation(entity, country)
        return {
            "type": "geo",
            "title": f"In {country_name(country)}",
            "items": [
                {"label": "Regulated", "value": reg["status"]},
                {"label": "Restrictions", "value": reg.get("restrictions", "None")},
                {"label": "Alternative", "value": reg.get("local_alt", "—")},
            ]
        }
    
    # Generisk: tillgänglighet
    else:
        available = check_availability(entity, country)
        if available is not None:
            return {
                "type": "geo",
                "title": f"In {country_name(country)}",
                "items": [
                    {"label": "Available", "value": "Yes" if available else "No",
                     "icon": "✅" if available else "❌"},
                ]
            }
    
    return None


# ============================================
# STEG 4: "Beyond the AI Answer"
# ============================================

def generate_beyond_ai(entity, country) -> dict:
    """Visa info som AI-svaret troligen inte innehöll."""
    items = []
    
    # Ägarskap
    owner = entity.metadata.get("parent_company")
    siblings = entity.metadata.get("sibling_products", [])
    if owner:
        items.append({
            "label": "Owned by",
            "value": f"{owner}" + (f" (also owns {', '.join(siblings[:3])})" if siblings else "")
        })
    
    # Trend
    trend = get_trust_trend(entity, days=30)
    if trend and abs(trend) > 1:
        direction = "↑" if trend > 0 else "↓"
        items.append({
            "label": "Trust trend (30 days)",
            "value": f"{direction} {abs(trend):.1f} points"
        })
    
    # Geo-specifik risk som AI troligen missade
    geo_risk = get_geo_specific_risk(entity, country)
    if geo_risk:
        items.append({
            "label": f"Risk in {country_name(country)}",
            "value": geo_risk
        })
    
    if not items:
        return None
    
    return {
        "type": "beyond_ai",
        "title": "Beyond the AI Answer",
        "subtitle": "What the AI likely didn't mention:",
        "items": items
    }
```

### HTML Template

```html
<!-- for_you.html — renderas NEDANFÖR all befintlig content -->
<!-- AI-bottar ser aldrig detta (bot-detection i Python) -->

{% if sections %}
<section class="for-you" style="
  margin: 32px 0; 
  padding: 24px; 
  border: 1px solid #e2e8f0; 
  border-radius: 12px;
  background: linear-gradient(135deg, #f8fafc 0%, #f0f4ff 100%);
">
  <h2 style="font-size: 17px; font-weight: 700; margin-bottom: 16px; color: #1e293b;">
    {{ entity.name }} — For You
  </h2>
  
  {% for section in sections %}
  <div class="fy-section" style="margin-bottom: 16px;">
    
    {% if section.type == "geo" %}
    <h3 style="font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 8px;">
      📍 {{ section.title }}
    </h3>
    {% elif section.type == "app" %}
    <h3 style="font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 8px;">
      📱 On Your {{ visitor.os }}
    </h3>
    {% elif section.type == "extension" %}
    <h3 style="font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 8px;">
      🔌 In Your {{ visitor.browser }}
    </h3>
    {% elif section.type == "beyond_ai" %}
    <h3 style="font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 4px;">
      💡 {{ section.title }}
    </h3>
    <p style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">
      {{ section.subtitle }}
    </p>
    {% elif section.type == "cross_registry" %}
    <h3 style="font-size: 14px; font-weight: 600; color: #475569; margin-bottom: 8px;">
      🔗 Across Platforms
    </h3>
    {% endif %}
    
    <div style="display: grid; gap: 6px;">
      {% for item in section.items %}
      <div style="
        display: flex; 
        justify-content: space-between; 
        padding: 6px 10px; 
        background: white; 
        border-radius: 6px;
        font-size: 13px;
      ">
        <span style="color: #64748b;">{{ item.label }}</span>
        <span style="font-weight: 600; color: #1e293b;">
          {{ item.icon }} {{ item.value }}
        </span>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endfor %}
  
  <p style="font-size: 11px; color: #94a3b8; margin-top: 12px; border-top: 1px solid #e2e8f0; padding-top: 8px;">
    Personalized based on your location and device. 
    Nerq does not store personal data. 
    <a href="/privacy" style="color: #94a3b8;">Privacy policy</a>
  </p>
</section>
{% endif %}
```

---

## Del 5: Vad AI-svaret ska innehålla

### Hook i pplx-verdict (universell — AI-bottar ser detta)

```
{entity} has a Nerq Trust Score of {score}/100 ({grade}), ranking 
#{rank} of {total} {category}. {risk_count} risk factors identified. 
Score varies by location and device — personalized trust analysis 
at nerq.ai/safe/{slug}
```

### Geo-anpassad hook (dynamisk — bara människor ser)

```python
CULTURAL_HOOKS = {
    # Social proof-kulturer (kollektivistiska)
    "social_proof": {
        "countries": ["VN", "TH", "ID", "JP", "KR", "CN", "TW", "SG",
                      "MY", "PH", "BD", "PK", "IN"],
        "template": "Checked {checks:,} times this week. See how {entity} "
                    "scores in {country_name}."
    },
    # Loss aversion-kulturer (individualistiska, västerländska)
    "loss_aversion": {
        "countries": ["US", "CA", "GB", "AU", "NZ", "IE",
                      "SE", "DE", "DK", "NO", "FI", "NL", "CH", "AT"],
        "template": "{risk_count} risk factors may affect you. "
                    "See your personalized analysis."
    },
    # Auktoritets-kulturer
    "authority": {
        "countries": ["BR", "MX", "CO", "AR", "CL", "PE",
                      "SA", "AE", "EG", "IQ", "TR"],
        "template": "Independently analyzed across {dims} trust dimensions. "
                    "See your regional trust report."
    },
}
```

---

## Del 6: Sprint-plan

### Dag 1: Grundinfrastruktur (4-6 timmar)

```
□ Implementera get_visitor_context() i FastAPI
□ Bot-detection (AI-bottar → None → ingen personalisering)
□ Verifiera att CF-IPCountry headers levereras korrekt
□ Verifiera User-Agent parsing (OS, browser)
□ Verifiera referrer-detection (chatgpt.com, perplexity.ai etc.)
□ TESTA: AI-bot request → standard-sida (inget nytt)
□ TESTA: Human request → visitor_context dict korrekt
```

**🟢 SÄKER:** Lägger till Python-kod som läser headers. Ändrar inget i rendering ännu.

### Dag 2: Geo-personalisering (4-6 timmar)

```
□ Implementera generate_geo_section() för VPN-vertikalen
  □ VPN legalitet per land (lookup-tabell: ~50 länder)
  □ Jurisdiktions-analys (entity.metadata.jurisdiction)
  □ Närmaste server (om data finns)
  □ Lokal popularitet (analytics-baserad ranking)
□ Implementera generate_geo_section() generisk (tillgänglighet per land)
□ Rendera geo-sektion i for_you.html template
□ TESTA: Vietnam-request → "VPN restricted in Vietnam" visas
□ TESTA: Sweden-request → "Legal in Sweden ✅" visas
□ TESTA: Bot-request → inget nytt visas
```

**🟢 SÄKER:** Ny sektion adderas NEDANFÖR befintligt content. Bottar ser den inte.

### Dag 3: Enhets/browser-personalisering (3-4 timmar)

```
□ Implementera app-lookup: find_entity_in_registry(name, "android"/"ios")
□ Implementera extension-lookup: find_entity_in_registry(name, "chrome"/"firefox")
□ Implementera generate_app_section()
□ Implementera generate_extension_section()
□ Implementera generate_cross_registry()
□ TESTA: Android/Chrome-request → visar app-score + extension-score
□ TESTA: iPhone/Safari-request → visar iOS app-score, ingen extension
□ TESTA: Desktop/Firefox-request → visar Firefox extension om den finns
```

**🟢 SÄKER:** Korsrefererar befintliga registries. Inga nya data behövs.

### Dag 4: "Beyond the AI Answer" + kulturella hooks (3-4 timmar)

```
□ Implementera generate_beyond_ai() (ägarskap, trend, geo-risk)
□ Implementera kulturella hooks (social proof/loss aversion/authority per land)
□ Rendera dynamisk hook-text per CF-IPCountry
□ TESTA: Request med Referer: chatgpt.com → "Beyond the AI Answer" visas
□ TESTA: Vietnam → social proof hook
□ TESTA: USA → loss aversion hook
□ TESTA: Brasilien → authority hook
```

**🟢 SÄKER:** Ny sektion + dynamisk text. Inget befintligt ändras.

### Dag 5: Gambling + Crypto + Banking geo-djup (3-4 timmar)

```
□ Gambling licensstatus per land (Malta GC, UKGC, Spelinspektionen etc.)
  □ Lookup-tabell: ~30 jurisdiktioner
□ Crypto-exchange regulering per land
  □ Lookup-tabell: ~30 länder  
□ Bank-vertikal: land-specifik info
□ TESTA: Bet365 från Sverige → "Licensed ✅ (Spelinspektionen)"
□ TESTA: Bet365 från Japan → "Not licensed ⚠️ in Japan"
□ TESTA: Binance från Tyskland → "Restricted since 2024 ⚠️"
```

**🟢 SÄKER:** Ny data-tabell + ny rendering. Inget befintligt ändras.

### Dag 6: A/B-test setup + mätning (2-3 timmar)

```
□ Logga "for_you_rendered" event i analytics.db
  □ Logga: country, os, browser, from_ai, entity, sections_shown
□ Beräkna CTR:
  □ Baseline (utan For You): senaste 7 dagarna
  □ Med For You: efter deployment
□ SQL för CTR-jämförelse:

SELECT 
  DATE(ts) as day,
  SUM(CASE WHEN is_ai_bot = 1 THEN 1 ELSE 0 END) as citations,
  SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) as humans,
  ROUND(100.0 * SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) / 
    NULLIF(SUM(CASE WHEN is_ai_bot = 1 THEN 1 ELSE 0 END), 0), 1) as ctr
FROM requests
WHERE ts > datetime('now', '-14 days') AND status = 200
GROUP BY DATE(ts);
```

---

## Del 7: Vad som INTE ändras

| Element | Status | Varför |
|---|---|---|
| pplx-verdict | ❄️ ORÖRT | AI-bottar citerar detta. En ändring riskerar 200K citations/dag. |
| ai-summary | ❄️ ORÖRT | Djupare context för AI-system. |
| SpeakableSpecification | ❄️ ORÖRT | Troligen faktor i Claude-spiket. |
| Schema.org | ❄️ ORÖRT | Maskinläsbar metadata. |
| "Updated daily" | ❄️ ORÖRT | Freshness-signal. |
| Entity data | ❄️ ORÖRT | Befintlig content. |
| FAQ | ❄️ ORÖRT | Befintlig content. |
| All content OVANFÖR "For You" | ❄️ ORÖRT | Allt som AI ser bevaras intakt. |

**"For You" adderas NEDANFÖR allt ovanstående. AI-bottar ser den ALDRIG (bot-detection). Noll risk.**

---

## Del 8: Estimerad impact

### CTR-förbättring

| Scenario | CTR | Human visits/dag (vid 200K citations) |
|---|---|---|
| Nuvarande (ingen personalisering) | 18% | 36K |
| Med "For You" (konservativt) | 23% | 46K |
| Med "For You" (realistiskt) | 27% | 54K |
| Med "For You" + kulturella hooks (optimistiskt) | 32% | 64K |

### Revenue-impact (vid monetisering)

| CTR | Extra human/dag vs baseline | Extra revenue/mån |
|---|---|---|
| 23% | +10K | +$3-6K |
| 27% | +18K | +$6-10K |
| 32% | +28K | +$10-16K |

### Vid 500K citations/dag (M6)

| CTR | Human/dag | Extra/mån vs 18% |
|---|---|---|
| 27% | 135K | +$16-26K |
| 32% | 160K | +$25-42K |

### Vid 1M citations/dag (M12)

| CTR | Human/dag | Extra/mån vs 18% |
|---|---|---|
| 27% | 270K | +$32-54K |
| 32% | 320K | +$50-84K |

---

## Del 9: Total effort & tidslinje

| Dag | Vad | Effort | Risk |
|---|---|---|---|
| 1 | Grundinfrastruktur (visitor_context, bot-detection) | 4-6h | 🟢 |
| 2 | Geo-personalisering (VPN-vertikal + generisk) | 4-6h | 🟢 |
| 3 | Enhets/browser-personalisering (app + extension lookup) | 3-4h | 🟢 |
| 4 | "Beyond AI" + kulturella hooks | 3-4h | 🟢 |
| 5 | Gambling + Crypto + Banking djup-geo | 3-4h | 🟢 |
| 6 | A/B-test setup + mätning | 2-3h | 🟢 |
| **Total** | | **~20-27 timmar** | **Alla 🟢** |

**~4-5 dagars arbete. Alla åtgärder 🟢 säkra. Potentiell impact: +$10-84K/mån beroende på citation-volym.**

---

## Del 10: Framtida expansion

Efter initial deployment kan personalisering utökas:

| Fas | Vad | Effort |
|---|---|---|
| Fas 2 | Fler vertikaler (alla 25 med stark personalisering) | 1 vecka |
| Fas 3 | Use-case-knappar ("Privacy / Streaming / Gaming") | 2-3 dagar |
| Fas 4 | Stack-check widget ("Enter your tools → stack score") | 2-3 dagar |
| Fas 5 | Returning visitor ("Your stack changed since last visit") | 1 vecka |
| Fas 6 | PDF-export ("Download your personalized trust report") | 2-3 dagar |

---

*Nerq Personalization Sprint — April 5, 2026*
*~4-5 dagars arbete. Alla 🟢 säkra. AI-bottar ser aldrig ändringen.*
*"See how it scores for YOU" — den hook AI inte kan leverera.*
