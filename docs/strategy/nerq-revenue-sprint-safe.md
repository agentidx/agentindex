# Nerq Revenue Sprint — Säkra förberedelser
## Bara 🟢-klassificerade initiativ som inte riskerar befintlig trafik
### April 4, 2026

---

## Princip

Denna plan förbereder monetisering utan att aktivera den. Ingen ad-kod läggs på sajten. Inga affiliate-länkar visas. Allt handlar om att signera avtal, bygga infrastruktur, och ha en switch redo att slå på den dag trafiktiggern nåtts.

**Monetiseringstrigger:** 150,000 human visits/dag, 7 dagar i sträck (inget dygn under 130,000).

**Estimerad timing:** September-december 2026 (beroende på Claude-spike-stabilisering och Google organic-tillväxt).

**Mål vid trigger:** $50K+/mån i AdSense + affiliate.

---

## Nuläge

| Metric | Värde |
|---|---|
| Human visits/dag | 35-40K |
| Monetisering aktiv | $0 — ingenting implementerat |
| Affiliate-avtal signerade | 0 |
| AdSense-status | Ej ansökt |
| Revenue vid nuvarande trafik (om monetiserat) | ~$10-15K/mån |
| Revenue vid trigger (150K/dag) | ~$50-58K/mån |

---

## Sprint R1: Ansök ad-nätverk

### Vad
Ansök till AdSense och Mediavine. Ansökan ändrar ingenting på sajten — det är bara en applikation.

### Varför säkert
Att ansöka ≠ att visa ads. Godkännande tar 1-4 veckor. Under den tiden ändras inget. Ads aktiveras INTE förrän ni väljer det.

### Åtgärder

**Google AdSense:**
1. Gå till adsense.google.com
2. Registrera nerq.ai
3. Lägg till verifierings-snippet i `<head>` (detta ÄR en sajt-ändring, men det är en osynlig meta-tag som inte påverkar content eller AI-bottar)
4. Vänta på godkännande (1-4 veckor)
5. AKTIVERA INTE auto-ads — bara konto-godkännande

**Mediavine:**
- Kräver 50K sessions/senaste 30 dagarna — ni har det
- Ansök på mediavine.com/apply
- Mediavine har RPM 2-3x AdSense för Tier-1-trafik
- Godkännande tar 2-4 veckor
- Om godkänd → bättre alternativ till AdSense

### Effort
1 timme totalt.

### Lead time
1-4 veckor för godkännande. Starta nu.

---

## Sprint R2: Signera affiliate-avtal

### Vad
Ansök till affiliate-program. Avtal signeras men INGA länkar placeras på sajten.

### Varför säkert
Att ha ett affiliate-avtal ändrar ingenting på sajten. Det är ett juridiskt avtal med en partner. Affiliate-länkar implementeras först vid trigger.

### Program att ansöka till, i prioritetsordning

**Tier 1 — Högst revenue-potential med befintlig trafik:**

| Program | Payout | Varför prioritera | Ansök |
|---|---|---|---|
| **Binance affiliate** | $10-100/signup (tiered) | 24K /token/ visits/vecka. Störst outnyttjad potential. | binance.com/affiliate |
| **Coinbase affiliate** | $10/verified signup | Trovärdigt varumärke, hög konvertering i US | coinbase.com/affiliates |
| **Bybit affiliate** | $20-50/active trader | Stor i Asien (matchar VN-trafik) | bybit.com/affiliates |
| **NordVPN affiliate** | 40-100% initial + 30% recurring | VPN-sidor redan live, 79 entities | nordvpn.com/affiliate |
| **ExpressVPN affiliate** | $5-13/signup | Komplement till NordVPN | expressvpn.com/affiliate |

**Tier 2 — Hög payout per conversion:**

| Program | Payout | Varför | Ansök |
|---|---|---|---|
| **WP Engine affiliate** | $100-290/signup | Hosting-vertikal live, 51 entities | wpengine.com/partners |
| **Cloudways affiliate** | $125/signup | Alternativ hosting-affiliate | cloudways.com/affiliate |
| **SiteGround affiliate** | $50/signup | Budget-hosting-alternativ | siteground.com/affiliates |
| **1Password affiliate** | $20 + 25% recurring | PM-vertikal live, 55 entities | 1password.com/affiliate |
| **Shopify affiliate** | $150/signup | Website builders-vertikal live | shopify.com/affiliates |

**Tier 3 — SaaS recurring (compound over time):**

| Program | Payout | Varför | Ansök |
|---|---|---|---|
| **PartnerStack** | Access till 200+ SaaS-program | Ett avtal → hundratals affiliate-program | partnerstack.com |
| **Semrush affiliate** | $200/sale, $10/trial | Hög enstaka-payout | semrush.com/affiliate |
| **HubSpot affiliate** | 30% recurring 12 mån | Recurring compound | hubspot.com/affiliate |
| **NordPass affiliate** | $20/signup | Cross-sell från NordVPN | nordpass.com/affiliate |

### Process per ansökan
1. Skapa affiliate-konto
2. Ansök med nerq.ai som sajt
3. Beskriv: "Independent trust score platform with 7.5M+ rated entities"
4. Vänta på godkännande (1-14 dagar)
5. Spara affiliate-ID och tracking-URL
6. IMPLEMENTERA INTE på sajten ännu

### Effort
4-6 timmar totalt (15-20 min per ansökan, ~15 program).

### Lead time
1-2 veckor för godkännande. Starta nu.

---

## Sprint R3: Bygg feature flag-infrastruktur

### Vad
Skapa en config-flagga `MONETIZATION_ACTIVE = False` som styr om affiliate-CTAs och ad-slots renderas.

### Varför säkert
En variabel i config-filen. När False → inget renderas. Sajten ser identisk ut som idag. Inga HTML-ändringar, inga nya element, ingen synlig skillnad.

### Implementation

I config (t.ex. `nerq_config.py` eller var konfigurationen lever):

```python
# Monetisering — slå på FÖRST när trigger nåtts
MONETIZATION_ACTIVE = False

# Trigger: 150K human visits/dag × 7 dagar i sträck
# Kolla med: SELECT DATE(ts), SUM(CASE WHEN is_bot=0 THEN 1 END) 
#   FROM requests WHERE ts > datetime('now','-7 days') 
#   GROUP BY DATE(ts) HAVING SUM(...)>=130000;
# Om 7 rader → sätt MONETIZATION_ACTIVE = True

# Sub-flaggor (för granulär kontroll)
SHOW_DISPLAY_ADS = False      # AdSense/Mediavine
SHOW_AFFILIATE_CTAS = False   # Affiliate-knappar
SHOW_SPONSORED = False        # Sponsored placements
```

I templates (förbered men visa inte):

```python
if MONETIZATION_ACTIVE and SHOW_AFFILIATE_CTAS:
    # Render affiliate CTA nedanför main content
    affiliate_html = render_affiliate_cta(entity, registry)
else:
    affiliate_html = ""
```

### Effort
2-3 timmar.

---

## Sprint R4: Förbered affiliate-CTA templates

### Vad
Designa och koda affiliate-CTA-blocken som ska visas när flaggan slås på. Koda dem nu, visa dem aldrig (feature flag = False).

### Varför säkert
Koden finns i templates men renderas inte. `MONETIZATION_ACTIVE = False` → noll HTML-output. AI-bottar och besökare ser ingenting nytt.

### CTA-design

**Princip:** Affiliate-CTAs placeras ALLTID:
- EFTER pplx-verdict, ai-summary, main analysis
- I en separat, tydligt avgränsad sektion
- Med "Where to get it" eller "Try it" framing
- ALDRIG blandade med trust-data eller scores
- Med disclosure: "Nerq may earn a commission"

**Per vertikal:**

VPN-sidor:
```html
{% if MONETIZATION_ACTIVE and SHOW_AFFILIATE_CTAS %}
<section class="cta-section" style="margin:24px 0; padding:16px 20px; border:1px solid #e2e8f0; border-radius:10px; background:#fafafa;">
  <p style="font-size:14px; font-weight:600; margin-bottom:10px;">Try {{entity_name}}</p>
  <a href="{{affiliate_url}}" rel="sponsored nofollow" target="_blank"
     style="display:inline-block; padding:10px 20px; background:#2563eb; color:#fff; 
            border-radius:8px; text-decoration:none; font-size:14px;">
    Visit {{entity_name}} →
  </a>
  <p style="font-size:11px; color:#94a3b8; margin-top:8px;">
    Nerq may earn a commission. This does not influence our trust scores.
  </p>
</section>
{% endif %}
```

Crypto-sidor:
```html
{% if MONETIZATION_ACTIVE and SHOW_AFFILIATE_CTAS %}
<section class="cta-section" style="...">
  <p style="font-size:14px; font-weight:600; margin-bottom:10px;">Trade this token</p>
  <div style="display:flex; gap:8px; flex-wrap:wrap;">
    <a href="{{binance_url}}" rel="sponsored nofollow" target="_blank" class="cta-btn">Binance</a>
    <a href="{{coinbase_url}}" rel="sponsored nofollow" target="_blank" class="cta-btn">Coinbase</a>
  </div>
  <p style="font-size:11px; color:#94a3b8; margin-top:8px;">
    Nerq may earn a commission. Trust scores are independent.
  </p>
</section>
{% endif %}
```

### Affiliate URL-routing

```python
AFFILIATE_URLS = {
    "nordvpn": "https://go.nordvpn.net/aff_c?aff_id=XXXXX",
    "expressvpn": "https://www.expressvpn.com/a/XXXXX",
    "binance": "https://accounts.binance.com/register?ref=XXXXX",
    "coinbase": "https://www.coinbase.com/join/XXXXX",
    "wpengine": "https://shareasale.com/r.cfm?b=XXXXX",
    "1password": "https://1password.com/?a=XXXXX",
    "shopify": "https://www.shopify.com/?ref=XXXXX",
    # ... etc
}
```

### Effort
1 dag (design + kodning av templates för alla vertikaler).

---

## Sprint R5: Förbered geo-baserad monetisering

### Vad
Designa logiken för att visa olika monetisering beroende på besökarens land. Koda men aktivera inte.

### Varför säkert
Logiken körs bara om MONETIZATION_ACTIVE = True. Innan dess → inget händer.

### Geo-strategi

```python
def get_monetization_tier(country_code: str) -> str:
    """Bestäm monetiseringsnivå baserat på land."""
    TIER_1 = {"US", "CA", "GB", "AU", "DE", "FR", "SE", "DK", "NL", "NO", "FI", "JP", "KR", "SG", "CH", "AT", "IE", "NZ"}
    TIER_2 = {"IT", "ES", "PL", "CZ", "PT", "BE", "HK", "TW", "IL"}
    TIER_3 = {"VN", "TH", "ID", "BD", "PK", "IQ", "EG", "MX", "BR", "CO", "AR", "VE", "IN", "PH", "NG"}
    
    if country_code in TIER_1:
        return "premium"     # Display ads (Mediavine) + affiliate CTAs
    elif country_code in TIER_2:
        return "standard"    # AdSense + affiliate CTAs
    elif country_code in TIER_3:
        return "affiliate_only"  # Bara affiliate CTAs, inga display ads (RPM < $1)
    else:
        return "standard"
```

**Varför:** 43% av trafiken är Vietnam med RPM < $1.50. Att visa display ads till Vietnam-besökare ger centöres men laddar tunga ad-scripts som saktar ner sidan. Bättre att skippa ads helt och bara visa affiliate-CTAs (som betalar per conversion oberoende av geo).

### Bot-detection

```python
def is_ai_bot(user_agent: str) -> bool:
    """AI-bottar ska ALDRIG se ads eller affiliate-CTAs."""
    bot_patterns = ["GPTBot", "ClaudeBot", "PerplexityBot", "ChatGPT", 
                    "Bytespider", "Google-Extended", "Googlebot"]
    return any(p.lower() in user_agent.lower() for p in bot_patterns)

# I rendering:
if MONETIZATION_ACTIVE and not is_ai_bot(request.user_agent):
    # Visa monetisering
else:
    # Ren sida utan ads/affiliate
```

**Kritiskt:** AI-bottar ser ALDRIG ads eller affiliate-CTAs. De ser en ren, snabb, content-fokuserad sida. Det bevarar citation-kvaliteten.

### Effort
3-4 timmar.

---

## Sprint R6: Förbered ad-slot templates

### Vad
Designa var display ads ska placeras — men implementera INTE ad-script. Bara reservera utrymme i templates med feature flag.

### Varför säkert
Feature flag = False → inget renderas. Ingen ad-kod laddas. Sidan är identisk.

### Ad-placering

```python
{% if MONETIZATION_ACTIVE and SHOW_DISPLAY_ADS and not is_ai_bot %}
  {% if monetization_tier == "premium" %}
    <!-- Mediavine ad slot -->
    <div class="ad-slot" id="ad-below-analysis" 
         style="margin:24px 0; min-height:250px; text-align:center;">
      <!-- Mediavine script injiceras här vid aktivering -->
    </div>
  {% elif monetization_tier == "standard" %}
    <!-- AdSense ad slot -->
    <div class="ad-slot" id="ad-below-analysis">
      <!-- AdSense auto-ad eller manuell placering -->
    </div>
  {% endif %}
{% endif %}
```

### Placeringsregler (icke-förhandlingsbara)

| Plats | Tillåtet? | Varför |
|---|---|---|
| Före pplx-verdict | ❌ ALDRIG | Bryter AI-citation-flow |
| Inuti pplx-verdict | ❌ ALDRIG | Förstör capsule-integritet |
| Inuti ai-summary | ❌ ALDRIG | Förstör capsule-integritet |
| Mellan verdict och entity-data | ❌ ALDRIG | AI-bottar kan tolka som content |
| **Efter main analysis** | ✅ | Första tillåtna plats |
| **Mellan sektioner** | ✅ | In-content ad (1 max per sida) |
| **Före footer** | ✅ | Sidans botten |
| **Sidebar (desktop)** | ✅ | Om layout stöder det |

**Max ads per sida: 2** (1 in-content + 1 bottom). Inte fler — det skadar UX och page speed.

### Effort
2-3 timmar.

---

## Sprint R7: Bygg monetiserings-dashboard

### Vad
Skapa en enkel dashboard som visar estimerad revenue baserat på faktisk trafik, som om monetisering var aktiv.

### Varför säkert
Ren analytik. Ändrar inget på sajten.

### Implementation

```sql
-- Daglig estimerad revenue (shadow-beräkning)
SELECT 
  DATE(ts) as day,
  
  -- AdSense estimate
  SUM(CASE 
    WHEN is_bot = 0 AND country IN ('US','CA','GB','AU') THEN 0.020  -- $20 RPM
    WHEN is_bot = 0 AND country IN ('DE','FR','SE','DK','NL','JP','KR') THEN 0.012  -- $12 RPM
    WHEN is_bot = 0 AND country IN ('IT','ES','PL','CZ','PT') THEN 0.006  -- $6 RPM
    WHEN is_bot = 0 AND country IN ('VN','TH','ID','BD','PK','IQ') THEN 0.001  -- $1 RPM
    WHEN is_bot = 0 THEN 0.004  -- $4 RPM default
    ELSE 0
  END) as est_adsense_usd,
  
  -- Affiliate estimate (konservativt)
  SUM(CASE 
    WHEN is_bot = 0 AND path LIKE '/token/%' THEN 0.005  -- $5 per 1K token visits
    WHEN is_bot = 0 AND path LIKE '%vpn%' THEN 0.008  -- $8 per 1K VPN visits
    WHEN is_bot = 0 AND path LIKE '/best/%' THEN 0.010  -- $10 per 1K best visits
    WHEN is_bot = 0 AND path LIKE '/compare/%' THEN 0.006  -- $6 per 1K compare visits
    WHEN is_bot = 0 AND path LIKE '/alternatives/%' THEN 0.007  -- $7 per 1K alt visits
    WHEN is_bot = 0 THEN 0.002  -- $2 per 1K other visits
    ELSE 0
  END) as est_affiliate_usd,
  
  SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) as humans

FROM requests
WHERE ts > datetime('now', '-30 days') AND status = 200
GROUP BY DATE(ts)
ORDER BY day;
```

Kör dagligen. Visar: "Om monetisering var aktiv idag hade ni tjänat $X."

Det hjälper er se:
1. Exakt när trigger nås
2. Vilka dagar/vertikaler genererar mest estimerad revenue
3. Hur geo-mixen påverkar blended RPM

### Effort
1-2 timmar.

---

## Sprint R8: Förbered trigger-monitoring

### Vad
Automatisk kontroll av monetiseringstrigger. Daglig rapport: "X av 7 dagar uppnådda."

### Implementation

```bash
#!/bin/bash
# trigger_check.sh — kör dagligen via cron
sqlite3 ~/agentindex/logs/analytics.db << 'QUERY'
.mode column
.headers on
SELECT 
  DATE(ts) as day,
  SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) as humans,
  CASE WHEN SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) >= 130000 
    THEN '✅ PASS' ELSE '❌ BELOW' END as status
FROM requests
WHERE ts > datetime('now', '-7 days') AND status = 200
GROUP BY DATE(ts)
ORDER BY day;
QUERY

echo ""
echo "Qualifying days (>=130K):"
sqlite3 ~/agentindex/logs/analytics.db "
SELECT COUNT(*) as qualifying_days FROM (
  SELECT DATE(ts), SUM(CASE WHEN is_bot=0 THEN 1 END) as h
  FROM requests WHERE ts > datetime('now','-7 days') AND status=200
  GROUP BY DATE(ts) HAVING h >= 130000
);"
echo "Need: 7 qualifying days to trigger monetization"
```

### Effort
30 minuter.

---

## Tidslinje

| Vecka | Sprint | Effort | Resultat |
|---|---|---|---|
| **V1** | R1: Ansök AdSense + Mediavine | 1h | Ansökningar inskickade |
| **V1** | R2: Signera affiliate-avtal (Tier 1) | 2-3h | 5 affiliate-ansökningar |
| **V1** | R3: Feature flag | 2-3h | MONETIZATION_ACTIVE i config |
| **V1** | R7: Shadow revenue dashboard | 1-2h | Daglig revenue-estimering |
| **V1** | R8: Trigger monitoring | 30min | Daglig trigger-check |
| **V2** | R2: Signera affiliate-avtal (Tier 2+3) | 2-3h | 10+ affiliate-ansökningar |
| **V2** | R4: Affiliate-CTA templates | 1 dag | Templates kodade (ej synliga) |
| **V3** | R5: Geo-monetisering logik | 3-4h | Tier-baserad routing kodad |
| **V3** | R6: Ad-slot templates | 2-3h | Ad-platser reserverade (ej synliga) |

**Total effort: ~4-5 dagar utspritt över 3 veckor.**

---

## Vad som händer vid trigger

Den dag 150K human visits/dag nåtts 7 dagar i sträck:

### Dag 1: Aktivera steg för steg

```python
# Steg 1: Bara affiliate-CTAs (lägst risk)
MONETIZATION_ACTIVE = True
SHOW_AFFILIATE_CTAS = True
SHOW_DISPLAY_ADS = False
SHOW_SPONSORED = False
```

Mät i 3 dagar:
- Har AI-citations påverkats? (Borde inte — bot-detection skyddar)
- Funkar affiliate-tracking? (Klick registreras?)
- Är affiliate-CTAs synliga och klickbara?

### Dag 4: Lägg till display ads

```python
SHOW_DISPLAY_ADS = True  # Bara för Tier-1 och Tier-2 länder
```

Mät i 3 dagar:
- Page speed påverkad? (Jämför LCP före/efter)
- AI-citations påverkade?
- Ad-revenue matchar estimat?

### Dag 7: Full monetisering

```python
SHOW_SPONSORED = True  # Om sponsor-avtal finns
```

### Dag 14: Optimera

- Justera ad-placering baserat på data
- A/B-testa affiliate-CTA-copy
- Justera geo-tiers baserat på faktisk RPM

---

## Estimerad revenue vid trigger

| Stream | Dag 1-3 (affiliate only) | Dag 4-6 (+ display) | Dag 7+ (full) |
|---|---|---|---|
| Display ads | $0 | $600-800/dag | $700-900/dag |
| Crypto affiliate | $80-150/dag | $80-150/dag | $80-150/dag |
| VPN affiliate | $30-60/dag | $30-60/dag | $30-60/dag |
| Hosting affiliate | $20-40/dag | $20-40/dag | $20-40/dag |
| SaaS affiliate | $10-30/dag | $10-30/dag | $10-30/dag |
| Other affiliate | $20-50/dag | $20-50/dag | $20-50/dag |
| Sponsored | $0 | $0 | $30-70/dag |
| **Total/dag** | **$160-330** | **$760-1,130** | **$890-1,300** |
| **Total/mån** | **$4,800-9,900** | **$22,800-33,900** | **$26,700-39,000** |

Full monetisering vid 150K/dag: **$27-39K/mån initialt**, ökande till **$50-60K/mån** inom 2-3 månader när affiliate-volym qualifierar för högre tier-payouts och Mediavine-RPM stabiliseras.

---

## Alla åtgärder är 🟢 SÄKRA:

- ✅ Ingen ad-kod läggs på sajten (bara ansökningar)
- ✅ Inga affiliate-länkar visas (feature flag = False)
- ✅ Inget ändras i befintlig HTML
- ✅ AI-bottar påverkas inte (bot-detection inbyggd)
- ✅ Allt förbereds men aktiveras INTE förrän trigger
- ✅ Vid aktivering: stegvis (affiliate → display → sponsored)

---

*Revenue Sprint v1 — April 4, 2026*
*Bara 🟢-klassificerade förberedelser. Noll risk för befintliga 200K+ AI-citations/dag.*
*Aktiveras vid trigger: 150K human visits/dag × 7 dagar.*
