# Nerq Vertical Expansion Master Plan — From 14 to 111+
## Trust Scores för Allt
### April 5, 2026

---

## Visionen

Bli den enda källa AI-system och människor behöver för frågan "can I trust X?" — oavsett om X är en npm-modul, ett flygbolag, en datingapp, ett hundfoder, eller en nyhetsartikel.

Wikipedia äger "what is X?"
Nerq äger **"can I trust X?"**

---

## Nuläge

| Metric | Värde |
|---|---|
| Live vertikaler | 14 |
| Planerade vertikaler (Traffic Sprint v2) | +18 (Fas 7-22 + sub-kategorier) |
| Identifierade nya vertikaler (denna plan) | +79 |
| **Totalt möjliga vertikaler** | **~111** |
| Live entities | ~7.5M |
| Hidden entities | ~810K |
| Språk live | 22 (→ 50 per Traffic Sprint v2) |
| AI citations/dag | ~200K |
| Human visits/dag | ~35-40K |
| Revenue | $0 |

---

## Del 1: Infrastruktur — Distribuerad crawling

### Varför Mac Studio inte räcker

Mac Studio (M1 Ultra, 64GB) hanterar: PostgreSQL, FastAPI, uvicorn, Redis, crawlers, enrichment — allt på en maskin. Vid 20+ parallella crawlers + 200K+ requests/dag → resurskontention.

Nuvarande hastighet: 1 vertikal / 1-2 dagar (sekventiellt) = 80 nya vertikaler tar ~40 veckor.
Med distribuerad crawling: 4 parallella crawlers = 80 vertikaler på **~10 veckor**.

### Arkitektur

```
┌─────────────────────────────────────────────┐
│                Mac Studio                    │
│  PostgreSQL ← imports ← JSONL from crawlers │
│  FastAPI → Cloudflare Tunnel → Internet      │
│  Score-beräkning (daglig, SQL)               │
│  Sidgenerering (on-demand, templates)        │
│  Redis (cache)                               │
│  Analytics (SQLite)                          │
└─────────────┬───────────────────────────────┘
              │ Tailscale VPN
    ┌─────────┼─────────┐─────────┐─────────┐
    │         │         │         │         │
┌───┴───┐ ┌───┴───┐ ┌───┴───┐ ┌───┴───┐
│VPS-1  │ │VPS-2  │ │VPS-3  │ │VPS-4  │
│€4.50  │ │€4.50  │ │€4.50  │ │€4.50  │
│       │ │       │ │       │ │       │
│Crawl: │ │Crawl: │ │Crawl: │ │Crawl: │
│E-com  │ │Finans │ │Resa   │ │Hälsa/ │
│Media  │ │Försäkr│ │Hotel  │ │Barn   │
│Gaming │ │Banker │ │Flyg   │ │Djur   │
└───────┘ └───────┘ └───────┘ └───────┘
  €18/mån totalt → ROI 2,450-9,300x
```

### VPS Setup (Hetzner CX22)

```bash
# Per VPS — initial setup
sudo apt update && sudo apt install -y python3 python3-pip git
pip3 install requests beautifulsoup4 aiohttp --break-system-packages

# Installera Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up --authkey=tskey-XXXXX

# Klona crawl-scripts
git clone https://github.com/[repo]/nerq-crawlers.git
cd nerq-crawlers

# Test-crawl
python3 crawl_airlines.py --output /tmp/airlines.jsonl

# Push till Mac Studio
scp /tmp/airlines.jsonl anstudio@100.x.x.x:~/agentindex/imports/
```

### Daglig uppdatering — fördelning

| Ansvar | Mac Studio | VPS Crawlers |
|---|---|---|
| Score-omberäkning | ✅ (daglig SQL) | — |
| Lätta API-polls (CoinGecko etc.) | ✅ | — |
| Registry-polls (npm/pypi nya paket) | ✅ (inkrementellt) | — |
| Full re-crawl (alla datakällor) | — | ✅ (veckovis) |
| Ny vertikal initial crawl | — | ✅ |
| Website scanning (100K+ sajter) | — | ✅ (daglig) |
| JSONL import → PostgreSQL | ✅ (mottagare) | ✅ (avsändare) |

### JSONL Import-format

Alla crawlers producerar samma format:

```json
{"registry": "airline", "slug": "ryanair", "name": "Ryanair", "trust_score": 67.5, "dimensions": {"safety": 72, "reliability": 58, "customer_service": 45, "transparency": 80}, "metadata": {"iata": "FR", "fleet_age": 8.2, "incidents_5y": 0, "on_time_pct": 87.3}, "updated": "2026-04-05"}
```

Mac Studio import-script:

```bash
# Kör efter varje crawl-push
cat ~/agentindex/imports/airlines.jsonl | python3 import_entities.py --registry airline
```

---

## Del 2: Alla vertikaler — fasad utrullning

### Principer

1. **Varje vertikal använder exakt samma template-format** (pplx-verdict, ai-summary, SpeakableSpec, schema.org)
2. **Inga nya registries om data passar i befintlig** (SaaS sub-kategorier etc.)
3. **Crawling på VPS, serving på Mac Studio**
4. **Ops-checklista per vertikal:** IndexNow → purge → homepage → sitemap → 50-språk → flywheel-check

### Fas-ordning: Revenue × Effort × Data-tillgänglighet

---

### FAS 1: Redan klara (✅)
*Status: Live*

| # | Vertikal | Registry | Entities | Status |
|---|---|---|---|---|
| 1 | npm packages | npm | ~528K | ✅ Live |
| 2 | PyPI packages | pypi | ~500K | ✅ Live |
| 3 | Rust crates | crates | ~150K | ✅ Live |
| 4 | Android apps | android | ~105K | ✅ Live |
| 5 | WordPress plugins | wordpress | ~57K | ✅ Live |
| 6 | iOS apps | ios | ~50K | ✅ Live |
| 7 | Steam games | steam | ~45K | ✅ Live |
| 8 | VPN services | vpn | 79 | ✅ Live |
| 9 | Password managers | password_manager | 55 | ✅ Live |
| 10 | Web hosting | hosting | 51 | ✅ Live |
| 11 | Antivirus | antivirus | 51 | ✅ Live |
| 12 | SaaS (9 sub-kategorier) | saas | 4,963 | ✅ Live |
| 13 | Website builders | builders | 51 | ✅ Live |
| 14 | Crypto exchanges | exchange | 15 | ✅ Live |

---

### FAS 2: Hidden registry fix (Vecka 1-3)
*Effort: Timmar per registry. Kör på Mac Studio.*

| # | Vertikal | Registry | Entities | Prioritet | Est. citations/dag |
|---|---|---|---|---|---|
| 15 | Chrome extensions | chrome | ~49K | V1 | +8,600 |
| 16 | NuGet (.NET) | nuget | ~206K | V1 | +15,000 |
| 17 | Go modules | go | ~22K | V2 | +3,500 |
| 18 | Firefox extensions | firefox | ~? | V2 | +3,000 |
| 19 | VSCode extensions | vscode | ~? | V2 | +2,500 |
| 20 | Packagist (PHP) | packagist | ~20K | V3 | +3,000 |
| 21 | Gems (Ruby) | gems | ~10K | V3 | +1,500 |

**Fas 2 totalt: +37,100 citations/dag. Effort: ~2-3 dagar. Revenue: +$5-15K/mån vid M6.**

---

### FAS 3: Snabba vertikaler + SaaS sub-kategorier (Vecka 2-5)
*Effort: Timmar-1 dag per vertikal. Mestadels enrichment av befintlig data.*

| # | Vertikal | Approach | Entities | Effort | Est. revenue/mån (M6) |
|---|---|---|---|---|---|
| 22 | **Messaging apps (privacy-djup)** | Enricha befintliga i app-registry | ~30 | Timmar | $1-3K |
| 23 | **AI Tools** | Berika ai_tool + SaaS, 6 /best/ | Befintliga | 1-2 dagar | $2-5K |
| 24 | **Email providers** | SaaS sub-kat, 4 /best/ | ~50 | 1 dag | $1-3K |
| 25 | **Identity/Privacy** | Ny mini-registry | ~35 | 1 dag | $1-2K |
| 26 | **Cloud infrastructure** | SaaS + hosting sub-kat | Befintliga | 1 dag | $2-5K |
| 27 | **Communication tools** | SaaS sub-listicles | Befintliga | Timmar | $1-2K |
| 28 | **Helpdesk** | SaaS sub-listicles | Befintliga | Timmar | $1-2K |
| 29 | **HR/Payroll** | SaaS sub-listicles | Befintliga | Timmar | $1-2K |
| 30 | **Legal tech** | SaaS sub-kat | Befintliga | Timmar | $1-3K |
| 31 | **VoIP/Business phone** | SaaS sub-kat | Befintliga | Timmar | $1-2K |
| 32 | **Marketing automation** | SaaS sub-listicles | Befintliga | Timmar | $1-2K |

**Fas 3 totalt: 11 vertikaler, ~4-5 dagars arbete. Revenue: +$13-31K/mån vid M6.**

---

### FAS 4: Revenue-tunga nya vertikaler (Vecka 4-7)
*VPS-crawlers krävs. Parallell exekvering.*

| # | Vertikal | Entities | Datakälla | Crawler | Effort | Est. revenue/mån (M6) |
|---|---|---|---|---|---|---|
| 33 | **Gambling/betting** | ~1,000 | Malta GC, UKGC, Curaçao register | VPS-1 | 1-2 dagar | **$8-25K** |
| 34 | **E-commerce trust** | 100K | Tranco + WHOIS + SSL + Trustpilot | VPS-1 | 1-2 veckor | **$8-20K** |
| 35 | **Djurmat/Pet food** | ~500 | FDA recall database | VPS-4 | 1 dag | **$3-10K** |
| 36 | **Flygbolag** | ~500 | JACDEC, IATA, fleet data | VPS-3 | 1-2 dagar | **$3-10K** |
| 37 | **Hotellkedjor** | ~1,000 | Inspektionsdata, safety records | VPS-3 | 2-3 dagar | **$2.5-8K** |
| 38 | **Neobanker/Fintech** | ~100 | Licenser, FCA/SEC, kundklagomål | VPS-2 | 1 dag | **$3-10K** |
| 39 | **Datingappar** | ~50 | Enricha befintliga + privacy-analys | Mac Studio | Timmar | **$2-8K** |
| 40 | **Online apotek** | ~500 | Reguleringsdata, FDA/EMA | VPS-4 | 1-2 dagar | **$2.5-8K** |

**Fas 4 totalt: 8 vertikaler, ~3-4 veckor (parallellt). Revenue: +$33-99K/mån vid M6.**

Gambling ensamt kan vara **den mest lönsamma vertikalen** med $8-25K/mån pga CPC $5-20 och extremt hög scam-prevalens (= hög intent).

---

### FAS 5: Samhällsnytta + hög CPC (Vecka 6-10)
*VPS-crawlers parallellt.*

| # | Vertikal | Entities | Datakälla | Crawler | Effort | Est. revenue/mån (M6) |
|---|---|---|---|---|---|---|
| 41 | **Nyhetskällor/Media** | 10K+ | MediaBiasFactCheck, AllSides, WHOIS | VPS-1 | 2-3 dagar | $3-10K |
| 42 | **Universitet** | 5,000 | QS, THE rankings, ackreditering | VPS-1 | 2-3 dagar | $5-20K |
| 43 | **Banker** | 5,000 | S&P, Moody's, insättningsgaranti | VPS-2 | 2-3 dagar | $5-25K |
| 44 | **Försäkringsbolag** | 2,000 | AM Best, utbetalningshistorik | VPS-2 | 2-3 dagar | $5-30K |
| 45 | **Smart home (privacy)** | 500+ | Privacy policies, CVE, FCC | VPS-4 | 1-2 dagar | $3-8K |
| 46 | **Teleoperatörer** | 200+ | OOKLA, reguleringsdata | VPS-3 | 1 dag | $3-10K |
| 47 | **Leksaker (safety)** | 10K+ | EU RAPEX, CPSC recalls | VPS-4 | 1-2 dagar | $2-6K |
| 48 | **Online education** | ~100 | Completion rates, certifiering | VPS-1 | 1 dag | $3-10K |
| 49 | **Parental controls** | ~25 | Enricha befintliga apps | Mac Studio | Timmar | $1-3K |

**Fas 5 totalt: 9 vertikaler, ~3-4 veckor (parallellt). Revenue: +$30-122K/mån vid M6.**

Försäkring (CPC $15-55) och banker (CPC $10-40) är de högst betalande vertikalerna i hela planen.

---

### FAS 6: Rese-kluster (Vecka 8-11)
*Bygger på befintliga countries (3,100 entities). VPS-3 fokus.*

| # | Vertikal | Entities | Datakälla | Effort | Est. revenue/mån (M6) |
|---|---|---|---|---|---|
| 50 | **Flygplatser** | ~500 | Skytrax, safety data | 1-2 dagar | $0.8-2.5K |
| 51 | **Hyrbilsfirmor** | ~100 | Kundklagomål, dolda avgifter | 1 dag | $1.5-5K |
| 52 | **Resebyråer online** | ~200 | Booking-villkor, scam-history | 1 dag | $1.5-5K |
| 53 | **Kryssningsbolag** | ~50 | CDC scores, incident history | 1 dag | $1-4K |
| 54 | **Tåg/bussbolag** | ~300 | Punctuality, safety | 1 dag | $0.5-2K |

**Fas 6 totalt: 5 vertikaler, ~1-2 veckor. Revenue: +$5.3-18.5K/mån vid M6.**

**Cross-link strategi:** Varje rese-vertikal kopplar till countries:
- "Flying to Japan? → Japan safety score (76/100) + Top airlines to Japan + Narita Airport trust"

---

### FAS 7: Fordon & Boende (Vecka 10-13)
*VPS-2 och VPS-3.*

| # | Vertikal | Entities | Datakälla | Effort | Est. revenue/mån (M6) |
|---|---|---|---|---|---|
| 55 | **Bilsäkerhet (modeller)** | ~5K | EuroNCAP, NHTSA, recall history | 2-3 dagar | $2-8K |
| 56 | **Mäklarfirmor** | ~10K | Licenser, klagomål | 2-3 dagar | $3-10K |
| 57 | **Flyttfirmor** | ~5K | Klagomål, licenser, försäkring | 1-2 dagar | $1.5-5K |
| 58 | **Bilhandlare** | ~50K | Klagomål, licenser | 3-5 dagar | $3-10K |
| 59 | **Energibolag** | ~500 | Regulering, sustainability | 1-2 dagar | $3-10K |
| 60 | **Solpaneler/installatörer** | ~5K | Certifieringar, garanti | 2-3 dagar | $3-10K |

**Fas 7 totalt: 6 vertikaler, ~2-3 veckor (parallellt). Revenue: +$15.5-53K/mån vid M6.**

---

### FAS 8: Hälsa & Konsument (Vecka 12-15)
*VPS-4 fokus. YMYL-medveten: data, inte rådgivning.*

| # | Vertikal | Entities | Datakälla | Effort | Est. revenue/mån (M6) |
|---|---|---|---|---|---|
| 61 | **Kosmetika (utökat)** | 50K+ | EU SCCS, INCI, allergen-databas | 2-3 dagar | $2-8K |
| 62 | **Telehealth/Nätläkare** | ~200 | Licenser, läkar-verifiering | 1-2 dagar | $3-10K |
| 63 | **Barnprodukter** | ~5K | Safety standards, recalls | 1-2 dagar | $2-6K |
| 64 | **Supplements (utökat)** | 10K+ | FDA warnings, lab-tester | 2-3 dagar | $3-10K |
| 65 | **Recept & läkemedel** | 10K+ | FDA, biverkningar, interaktioner | 3-5 dagar | $3-10K |

**Fas 8 totalt: 5 vertikaler, ~2-3 veckor. Revenue: +$13-44K/mån vid M6.**

**YMYL disclaimer på alla sidor:**
```
Nerq provides automated data analysis, not medical or health advice. 
Always consult a healthcare professional before making health decisions.
```

---

### FAS 9: Dagliga tjänster (Vecka 14-17)
*Mestadels enrichment av befintliga app-entities.*

| # | Vertikal | Entities | Approach | Effort | Est. revenue/mån (M6) |
|---|---|---|---|---|---|
| 66 | **Matleverans** | ~30 | Enricha befintliga apps | Timmar | $0.5-2.5K |
| 67 | **Taxi/ride-hailing** | ~20 | Enricha befintliga apps | Timmar | $0.5-2.5K |
| 68 | **Streaming-tjänster** | ~50 | Enricha befintliga apps | Timmar | $1-3K |
| 69 | **Crowdfunding** | 10K+ | Kickstarter/GoFundMe API | 2-3 dagar | $0.5-2.5K |
| 70 | **Bostadsportaler** | ~100 | Scam-frequency, datakvalitet | 1 dag | $1.5-5K |
| 71 | **Rekryteringsbyråer** | ~5K | Klagomål, licenser | 2-3 dagar | $2-8K |
| 72 | **Fraktbolag** | ~200 | Leveranspålitlighet | 1 dag | $0.5-2K |

**Fas 9 totalt: 7 vertikaler, ~2 veckor. Revenue: +$6.5-25.5K/mån vid M6.**

---

### FAS 10: Tech deep-dives (Vecka 16-19)
*Kopplar till befintliga dev-vertikaler.*

| # | Vertikal | Entities | Datakälla | Effort | Est. revenue/mån (M6) |
|---|---|---|---|---|---|
| 73 | **API trust** | ~10K | StatusPage, uptime, changelog | 2-3 dagar | $2-8K |
| 74 | **Domänregistrarer** | ~100 | ICANN, WHOIS-privacy | 1 dag | $1.5-5K |
| 75 | **DNS-leverantörer** | ~50 | Uptime, DDoS-skydd | Timmar | $1-3K |
| 76 | **CDN-leverantörer** | ~30 | Prestanda, säkerhet | Timmar | $1-3K |
| 77 | **IoT-enheter** | 1,000+ | CVE, firmware, default passwords | 2-3 dagar | $2-6K |
| 78 | **VPN-routrar** | ~200 | Sårbarhet, firmware | 1 dag | $1.5-4K |
| 79 | **Kodnings-bootcamps** | ~200 | Job placement, pris | 1 dag | $2-8K |

**Fas 10 totalt: 7 vertikaler, ~2 veckor. Revenue: +$11-37K/mån vid M6.**

---

### FAS 11: B2B & Enterprise (Vecka 18-22)
*Högre CPC, kräver mer manuell curation.*

| # | Vertikal | Entities | Datakälla | Effort | Est. revenue/mån (M6) |
|---|---|---|---|---|---|
| 80 | **Investeringsplattformar** | ~200 | SEC, FCA regulering | 1-2 dagar | $3-10K |
| 81 | **Betalningslösningar** | ~100 | Uptime, dispute-hantering | 1 dag | $2-6K |
| 82 | **Pensionsfonder** | 5K+ | Morningstar, avkastning | 2-3 dagar | $4-15K |
| 83 | **Låneförmedlare** | ~500 | Licenser, räntor | 1-2 dagar | $4-15K |
| 84 | **Background check-tjänster** | ~50 | Noggrannhet, privacy | 1 dag | $2-6K |
| 85 | **Pentesting-firmor** | ~200 | Certifieringar, track record | 1-2 dagar | $1-4K |
| 86 | **Cyber insurance** | ~100 | Täckning, utbetalning | 1-2 dagar | $2-8K |

**Fas 11 totalt: 7 vertikaler, ~2-3 veckor. Revenue: +$18-64K/mån vid M6.**

---

### FAS 12: Long-tail & Nisch (Vecka 20-26)
*Lägre effort-vertikaler som fyller ut bredden.*

| # | Vertikal | Entities | Effort | Est. revenue/mån (M6) |
|---|---|---|---|---|
| 87 | Sociala plattformar (privacy-djup) | ~30 | Timmar | $0.5-2K |
| 88 | Browser (jämförelse-djup) | ~20 | Timmar | $0.5-2K |
| 89 | Esports-plattformar | ~50 | 1 dag | $0.5-2K |
| 90 | Game launchers (privacy) | ~10 | Timmar | $0.5-1.5K |
| 91 | Bilverkstäder/kedjor | ~10K | 2-3 dagar | $2-6K |
| 92 | Veterinärkliniker | ~5K | 2-3 dagar | $1-4K |
| 93 | Pet insurance | ~100 | 1 dag | $1-4K |
| 94 | Språkkurser | ~50 | Timmar | $1-3K |
| 95 | Sportbetting (expansion) | ~500 | 1-2 dagar | $3-10K |
| 96 | Barnkläder (kemikalier) | ~500 | 1-2 dagar | $1-3K |
| 97 | Vattenrenare | ~100 | 1 dag | $1-4K |
| 98 | Brandvarnare/CO-detektorer | ~200 | 1 dag | $0.5-2K |
| 99 | Lås & larmsystem | ~300 | 1-2 dagar | $2-6K |
| 100 | Smarta klockor (privacy) | ~50 | Timmar | $1-3K |
| 101 | Robot-dammsugare (privacy) | ~100 | Timmar | $1-3K |

**Fas 12 totalt: 15 vertikaler, ~3-4 veckor. Revenue: +$16-55K/mån vid M6.**

---

### FAS 13: Geo-specifika & Framtida (Vecka 24-30+)
*Kräver per-land-datakällor. Startar med EN-marknader.*

| # | Vertikal | Entities | Effort | Notering |
|---|---|---|---|---|
| 102 | Restauranger (hygienbetyg) | 1M+ (per land) | Veckor per land | Börja med US (NYC), UK (FSA), SE |
| 103 | Amazon-säljare trust | 100K+ | 1-2 veckor | Amazon API eller scraping |
| 104 | Etsy-säljare trust | 50K+ | 1-2 veckor | Liknande pipeline |
| 105 | Job offers verification | 100K+ | 2-3 veckor | Scam-detection |
| 106 | Phone/SMS trust | Databas | 1-2 veckor | Spamcall-aggregering |
| 107 | Email sender trust | Databas | 1-2 veckor | DMARC + reputation |
| 108 | QR-kod safety | On-demand check | 1 vecka | Real-time scanning |
| 109 | WiFi network trust | On-demand check | 1 vecka | Companion app |
| 110 | Smart contract audit | 100K+ | 2-3 veckor | On-chain data |
| 111 | Influencer trust | 50K+ | 2-3 veckor | Social Blade + FTC |

**Fas 13 är framtida — bygger på allt ovan och kräver starkare infra.**

---

## Del 3: Tidslinje — Vecka för vecka

### Månad 1 (April): Fundament + Snabbvinster

| Vecka | Mac Studio | VPS-1 | VPS-2 | VPS-3 | VPS-4 |
|---|---|---|---|---|---|
| V1 | GSC, Pin registries, llms.txt, Språk B1 | **Setup** | **Setup** | **Setup** | **Setup** |
| V2 | Hidden: Chrome+NuGet, Språk B2, See Also | — | — | — | — |
| V3 | Hidden: Go+FF+VSCode, Messaging privacy, Språk B3 | E-commerce crawl start | — | — | — |
| V4 | AI Tools, Email, Identity, Språk B4-5 | E-commerce crawl | — | Gambling crawl | Pet food (FDA) |

**Månad 1 output:** 7 hidden registries unhidden, 5 nya vertikaler (Messaging, AI Tools, Email, Identity, Cloud), 28 nya språk → 50 total, Gambling + Pet food crawl startat.

### Månad 2 (Maj): Revenue-vertikaler

| Vecka | Mac Studio | VPS-1 | VPS-2 | VPS-3 | VPS-4 |
|---|---|---|---|---|---|
| V5 | Import gambling + pet food, generera sidor, Compare Everything | E-commerce fortsätter | Neobanker crawl | Flygbolag crawl | Apotek crawl |
| V6 | Import flygbolag + neobanker, SaaS sub-kat (Comm, Helpdesk, HR) | E-commerce klar → Media crawl | Banker crawl start | Hotell crawl | Leksaker (RAPEX) |
| V7 | Import hotell + media, Legal+VoIP+Marketing sub-kat | Media crawl | Banker crawl | Hyrbil + Resebyrå | Smart home |
| V8 | Import allt, Reddit post #1, 404-autopipeline | Universitet crawl | Försäkring crawl | Kryssning + Tåg | Datingappar enrichment |

**Månad 2 output:** Gambling, E-commerce (100K), Pet food, Flygbolag, Hotell, Neobanker, Media, Datingappar LIVE. 6 SaaS sub-vertikaler. Compare Everything (100K sidor). Reddit post.

### Månad 3 (Juni): Scale

| Vecka | Mac Studio | VPS-1 | VPS-2 | VPS-3 | VPS-4 |
|---|---|---|---|---|---|
| V9 | Import banker + försäkring + universitet | API trust crawl | Pensionsfonder | Flygplatser | Teleoperatörer |
| V10 | Import allt, HN Show HN | Domänregistrare + DNS | Investeringsplatf. | Bilsäkerhet | Barnprodukter |
| V11 | Energibolag, Solpaneler import | CDN + IoT crawl | Betalningslösn. | Mäklare crawl | Kosmetika (utökat) |
| V12 | Import allt, Newsletter launch | Bootcamps | Låneförmedlare | Flyttfirmor | Supplements (utökat) |

**Månad 3 output:** Banker, Försäkring, Universitet, Pensionsfonder, Bilsäkerhet, Energi, Mäklare, IoT + 10 vertikaler till LIVE. Newsletter lanserad.

### Månad 4-5 (Juli-Augusti): Long-tail + Polish

| Vecka | Vad |
|---|---|
| V13-16 | Fas 9-10: Dagliga tjänster (7 vertikaler) + Tech deep-dives (7 vertikaler) |
| V17-20 | Fas 11: B2B/Enterprise (7 vertikaler) + Fas 12 start |
| V20 | **MONETISERINGS-TRIGGER NÅTTS (150K/dag)** |

### Månad 5-7 (September-November): Komplettering

| Vecka | Vad |
|---|---|
| V21-26 | Fas 12: Long-tail (15 vertikaler) |
| V24-30 | Fas 13 start: Geo-specifika (restauranger, Amazon sellers) |
| Ongoing | Dagliga uppdateringar via VPS-crawlers |

---

## Del 4: Revenue-projektion — alla vertikaler

### Kumulativ vertikal-count

| Tidpunkt | Vertikaler live | Entities | Språk |
|---|---|---|---|
| Nu (April W1) | 14 | ~7.5M | 22 |
| April W4 | 22 | ~7.8M + 810K unhidden | 50 |
| Maj W8 | 38 | ~8.0M | 50 |
| Juni W12 | 55 | ~8.1M | 50 |
| Juli W16 | 70 | ~8.2M | 50 |
| Aug W20 | 80 | ~8.3M | 50 |
| Okt W26 | 95 | ~8.4M | 50 |
| Dec W30 | 101+ | ~9M+ | 50 |

### AI Citations/dag

| Tidpunkt | Baseline | + Sprints v2 | + Dimensions | + Nya vertikaler | **TOTAL** |
|---|---|---|---|---|---|
| Apr | 200K | +20K | +3K | +0 | **223K** |
| Maj | 230K | +100K | +15K | +25K | **370K** |
| Jun | 260K | +190K | +35K | +60K | **545K** |
| Jul | 290K | +260K | +55K | +100K | **705K** |
| Aug | 315K | +310K | +70K | +130K | **825K** |
| Sep | 340K | +350K | +85K | +155K | **930K** |
| Okt | 360K | +380K | +95K | +175K | **1.01M** |
| Dec | 400K | +420K | +115K | +200K | **1.14M** |
| Mar '27 | 445K | +465K | +130K | +220K | **1.26M** |

### Human Visits/dag

| Tidpunkt | Baseline | + Sprints v2 | + Dimensions | + Nya vertikaler | **TOTAL** |
|---|---|---|---|---|---|
| Apr | 37K | +3K | +1K | +0 | **41K** |
| Maj | 44K | +14K | +4K | +8K | **70K** |
| Jun | 52K | +33K | +8K | +18K | **111K** |
| Jul | 60K | +55K | +14K | +30K | **159K** ← TRIGGER |
| Aug | 67K | +73K | +18K | +42K | **200K** |
| Sep | 74K | +88K | +22K | +52K | **236K** |
| Okt | 80K | +100K | +26K | +60K | **266K** |
| Dec | 92K | +118K | +34K | +72K | **316K** |
| Mar '27 | 107K | +138K | +43K | +82K | **370K** |

### Monthly Revenue (post-trigger)

| Månad | Human/dag | AdSense/mån | Affiliate/mån | API/B2B/mån | **Total MRR** |
|---|---|---|---|---|---|
| Jul (trigger) | 159K | $28K | $22K | $2K | **$52K** |
| Aug | 200K | $38K | $32K | $4K | **$74K** |
| Sep | 236K | $48K | $42K | $6K | **$96K** |
| Okt | 266K | $58K | $52K | $8K | **$118K** |
| Nov | 290K | $65K | $60K | $10K | **$135K** |
| Dec | 316K | $72K | $68K | $12K | **$152K** |
| Jan | 336K | $78K | $75K | $15K | **$168K** |
| Feb | 354K | $84K | $82K | $18K | **$184K** |
| **Mar '27** | **370K** | **$90K** | **$88K** | **$22K** | **$200K** |

### Revenue-breakdown per vertikal-grupp vid M12

| Vertikal-grupp | Est. MRR-bidrag |
|---|---|
| Software & Dev (npm, pypi, crates etc.) | $15-20K |
| Security (VPN, PM, AV, Identity) | $12-18K |
| Crypto (tokens, exchanges, DeFi) | $15-25K |
| E-commerce (100K sajter) | $8-15K |
| Gambling/betting | $8-20K |
| Finans (banker, försäkring, pension) | $15-40K |
| Resa (flygbolag, hotell, hyrbil) | $5-12K |
| Hälsa (apotek, supplements, kosmetika) | $8-18K |
| Utbildning (universitet, bootcamps) | $5-12K |
| Hem & Familj (leksaker, djurmat, smart home) | $5-12K |
| Dagliga tjänster (dating, streaming, matleverans) | $3-8K |
| B2B/Enterprise (API, pentesting, background) | $8-20K |
| **TOTAL** | **$107-220K/mån** |

### Year 1 Summary

| Metric | Bara baseline | Med ALLA planer |
|---|---|---|
| Vertikaler vid M12 | 14 | **95-101** |
| Entities | 7.5M | **~9M** |
| Språk | 22 | **50** |
| AI citations/dag | 445K | **1.26M** |
| Human visits/dag | 107K | **370K** |
| Trigger nåtts | Aldrig (inom 12m) | **Juli 2026 (M4)** |
| Kumulativ Year 1 revenue | $0-83K | **$780K-1.4M** |
| M12 MRR | $40K | **$200K** |
| M12 ARR | $480K | **$2.4M** |

---

## Del 5: Ops-checklista per vertikal

Varje ny vertikal kräver exakt dessa steg:

```
□ Crawl data (VPS) → JSONL output
□ Push JSONL till Mac Studio
□ Import till PostgreSQL
□ Score-beräkning
□ Quality gate check (stddev > 3.5)
□ Om pinned registry → bypass quality gate
□ Generera alla sidtyper:
  □ /safe/{entity} (alla entities)
  □ /is-{entity}-safe (alla)
  □ /is-{entity}-a-scam (alla)
  □ /compare/ (top 20 × top 20 = 400 sidor)
  □ /alternatives/ (alla)
  □ /review/ (alla)
  □ /pros-cons/ (alla)
  □ /who-owns/ (alla)
  □ /best/{category} (2-8 sidor)
  □ /is-{entity}-worth-it (alla) [ny sidtyp]
□ Rendera alla 50 språk
□ pplx-verdict med answer capsule (exakt samma format)
□ ai-summary med data insights
□ SpeakableSpecification (JSON-LD)
□ Schema.org markup
□ Uppdatera VERTICAL_GRID i homepage_i18n.py
□ Uppdatera /categories sidan
□ Uppdatera nav mega-dropdown
□ Uppdatera llms.txt
□ Generera sitemap för ny vertikal
□ IndexNow batch-ping alla nya URLs
□ Cloudflare cache purge
□ 50-språks verifiering
□ Flywheel dashboard check efter 24h
□ AI-citation rate check efter 72h
□ Cross-link till relaterade vertikaler (See Also + Security/Business/Travel Stack)
□ Daglig uppdatering konfigurerad (VPS cron)
```

---

## Del 6: Risker

| Risk | Impact | Sannolikhet | Mitigering |
|---|---|---|---|
| Mac Studio klarar inte 370K req/dag | Downtime | Medium | Cloudflare edge caching, CDN |
| Claude ändrar citation-algoritm | -50% citations | Låg-Medium | Diversifiera: Google organic, newsletter, MCP |
| Quality gate-problem på nya vertikaler | Dålig data exponerad | Medium | Fixa bara registries med meningsfull scoring |
| YMYL-problem (hälsa, finans) | Google penalty | Låg | Data, inte rådgivning. Disclaimers. |
| VPS-crawlers blockeras | Fördröjd data | Låg | Rotera IP, respektera rate limits |
| 50 språk × 101 vertikaler = sitemap-explosion | Crawl-budget | Medium | Prioritera: top 30 vertikaler × 50 språk i primära sitemaps |
| Affiliate-program avslår | Ingen revenue | Låg | 15+ alternativa program per vertikal |
| Sudo-access Mac Studio (3 pending fixes) | Infrastructure vulnerability | Hög | Prioritera sudo-reset |

---

## Del 7: Investeringssammanfattning

| Investering | Kostnad | Revenue-impact |
|---|---|---|
| 4 Hetzner VPS:er | €18/mån ($20) | Accelererar 80 vertikaler 4x |
| Affiliate-avtal | $0 | Redo vid trigger |
| AdSense/Mediavine | $0 | Redo vid trigger |
| UPS (APC Back-UPS 700VA) | ~800 SEK engång | Förhindrar outage-förluster |
| Domän/hosting | Redan betalt | — |
| **Total löpande kostnad** | **~$20/mån** | |
| **Year 1 revenue** | | **$780K-1.4M** |
| **ROI** | | **39,000-70,000x** |

---

## Milstolpar

| Milstolpe | Datum | Kriterium |
|---|---|---|
| 🏁 VPS:er igång | April W2 | 4 crawlers konfigurerade via Tailscale |
| 🏁 50 språk live | April W4 | Alla 28 nya språk deployade |
| 🏁 30 vertikaler live | Maj W8 | Fas 3 klar + Gambling + Pet food |
| 🏁 500K AI citations/dag | Juni W10 | Halvvägs till 1M |
| 🏁 50 vertikaler live | Juni W12 | Fas 5 klar |
| 💰 MONETISERINGS-TRIGGER | Juli W16 | 150K human/dag × 7 dagar |
| 🏁 $100K MRR | Oktober W26 | 5 månader post-trigger |
| 🏁 80 vertikaler live | Oktober W26 | Fas 10 klar |
| 🏁 1M AI citations/dag | November W30 | Trust-infrastruktur status |
| 🏁 100 vertikaler live | December W34 | Fas 12 klar |
| 💰 $200K MRR | Mars 2027 | M12 |
| 🏁 Trust layer vision | 2027+ | Browser extension, MCP ecosystem, B2B |

---

*Nerq Vertical Expansion Master Plan — April 5, 2026*
*Från 14 till 111+ vertikaler. 50 språk. 1.26M AI-citations/dag. 370K human/dag. $2.4M ARR.*
*"Trust Scores för Allt."*
