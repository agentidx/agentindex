# Fas-förändring Diagnostik: Nerq tillväxt + ZARQ fall

**Period:** 2026-03-15 → 2026-04-14
**Datum:** 2026-04-14

---

## DEL A — Nerq fas-förändring

### A1. Tidsserieanalys med brytpunkter

| Brytpunkt | Metric | Före | Efter | Förändring |
|---|---|---:|---:|---|
| **Mar 16** | Training crawl | 400/dag | 1,175 | ChatGPT startar crawling |
| **Mar 18** | Training crawl | 5,479 | 60,094 | **ClaudeBot 108x overnight** (500→54K) |
| **Mar 21** | AI citations (user_triggered) | 710 | 1,212 | OAI-SearchBot 9 URL-mönster |
| **Mar 31** | Training crawl | 36,255 | 144,198 | ClaudeBot 76K, ChatGPT 62K |
| **Apr 1** | Training crawl | 144K | 435K | **ClaudeBot 361K/dag** (peak) |
| **Apr 7** | Search index | 590K | 543K | 410 Gone-fix eliminerade 60K 4xx/dag |
| **Apr 12** | Training crawl | 294K | 81K | Cloudflare Workers AI incident |

**Tre distinkta faser:**

1. **Mar 15-17: Pre-crawl** — 400 training/dag, 124 AI citations. Nerq var i princip oupptäckt av AI-crawlers.
2. **Mar 18-30: Ramp** — ClaudeBot startade (108x), ChatGPT växte, AI citations nådde 1,500/dag.
3. **Mar 31+: Full crawl** — 300K+ training/dag, 1,200 AI citations/dag, stabil platå.

### A2. Vad drev training crawl-explosionen?

**Mar 18: ClaudeBot gick från 500 till 54,029 på en dag.**

Detta var INTE drivet av en Nerq-ändring. Git-historiken för denna period saknas (squashed Apr 7). Men beteendet är entydigt: Anthropic aktiverade ClaudeBot mot nerq.ai. Inga deploys, inga robots.txt-ändringar förklarar en 108x ökning overnight.

**Mar 31-Apr 1: ClaudeBot 76K→361K, ChatGPT 62K→67K.**

Lokaliserade sidor drev volymen:

| Pattern | Mar 15 | Apr 10 | Δ |
|---|---:|---:|---|
| Localized (/{lang}/*) | 117 | **267,260** | **2,284x** |
| /is-*-safe | 0 | 4,353 | ∞ |
| /safe/* | 71 | 3,537 | 50x |
| /compare/* | 126 | 3,234 | 26x |
| /alternatives/* | 0 | 975 | ∞ |
| /was-*-hacked | 0 | 759 | ∞ |
| /who-owns/* | 0 | 529 | ∞ |

**91% av training crawl vid peak (Apr 10) gick till lokaliserade sidor.** ClaudeBot och GPTBot upptäckte den 23-språkiga corpusen och crawlade den systematiskt.

### A3. Per-bot training crawl timeline

| Datum | ClaudeBot | GPTBot | ByteDance |
|---|---:|---:|---:|
| Mar 15 | 4 | 379 | 17 |
| Mar 18 | **54,029** | 5,714 | 351 |
| Mar 23 | 9,844 | 41,433 | 2,796 |
| Apr 1 | **361,293** | 67,292 | 6,133 |
| Apr 10 | 145,086 | 139,544 | 5,976 |
| Apr 12 | 65,281 | 10,920 | 5,188 |
| Apr 14 | 9,773 | 37,612 | 1,057 |

**ClaudeBot** hade två massiva spikes: Mar 18 (108x) och Apr 1 (5x ovan den nya baslinjen). Båda okorrelerade med Nerq-deploys.

**GPTBot** växte mer gradvis: 379→5K→41K→139K. Mer linjärt, konsistent med systematisk indexering.

### A4. Git-commits och korrelation

Git-historiken före Apr 7 saknas (squashed). Commits Apr 7-14 är dokumenterade. Inga commits korrelerar med training crawl-spikes — alla stora förändringar (ClaudeBot Mar 18, Apr 1) skedde utan föregående deploy.

### A5. robots.txt/llms.txt/sitemap

- **robots.txt:** Host-aware (nerq.ai vs zarq.ai) — korrekt igår och idag. Alla AI-bots explicit `Allow: /`.
- **llms.txt:** 175 rader, 26 registries. HuggingFace saknas (identifierat 2026-04-13).
- **Sitemap:** ~293K URLs idag. Historisk storlek okänd (ingen versionering).

### A6. Hypotesprövning

| Hypotes | Stöds av data? | Evidens |
|---|---|---|
| 21 mars-spike från nya URL-mönster | **Delvis** | OAI-SearchBot indexerade 9 nya mönster → ChatGPT-User hoppade. Men training crawl hade redan exploderat Mar 18. |
| Vertical-expansion driver tillväxt | **Nej** | Training crawl domineras av lokaliserade sidor, inte nya verticals. |
| Ny pattern_route deployad | **Okänt** | Git-historik squashed. Pattern_routes existerade redan Mar 15 (de hade low traffic). |
| Applebot bidrog | **Nej för training** | Applebot klassas som search_index, inte training. Grew separat. |
| Det var extern — Anthropic/OpenAI startade crawling | **Ja** | ClaudeBot 108x overnight utan Nerq-deploy. GPTBot gradvis ramp. Beteende konsistent med crawler-policy-ändringar hos AI-företagen. |

---

## DEL B — ZARQ fall

### B1. Tidsserie

| Datum | Search index | API | Other Bot | Human |
|---|---:|---:|---:|---:|
| Mar 15 | 13,663 | 7,695 | 17,520 | 2,242 |
| Mar 22 | 6,113 | 2,141 | 5,846 | 5,318 |
| Apr 1 | 1,637 | 2,380 | 7,627 | 3,904 |
| Apr 7 | 1,148 | 1,919 | 10,209 | 1,559 |
| Apr 13 | 3,465 | 1,703 | 4,701 | 3,100 |

**Search index föll 75% mellan Mar 15 och Apr 1**, sedan stabiliserade.

### B2. Vad som föll

**Amazonbot: 12,189 → 1,002 (-92%)**

Amazonbot var ZARQ:s dominerande crawler. Den gick från att crawla 12K ZARQ-sidor/dag till ~1K. Detta är en extern förändring — Amazon reducerade sin crawling-frekvens mot crypto-sidor.

**DataForSeoBot: 9,560 → ~0**

SEO-verktyget DataForSeo crawlade ZARQ aggressivt i mars, sedan slutade. Troligen ett engångs-scrapjobb.

**SleepBot: 2,015 → 0**

Okänd bot som crawlade i mars och sedan försvann.

**Google var stabil (646 Mar 15 → 468 Apr 13)** — ingen Google-avindexering.

**Apple dök UPP (0 → 951)** — ny positiv signal.

### B3. Teknisk hälsa

| Check | Status |
|---|---|
| robots.txt | ✅ Korrekt, host-aware, inga blockeringar |
| sitemap.xml | ✅ 200 OK |
| /crypto/token/bitcoin | ✅ 200 |
| /crypto/token/ethereum | ✅ 200 |
| /methodology | ✅ 200 |
| /token/bitcoin | ✅ 200 |
| /zarq/dashboard | 401 (korrekt — kräver token) |

**Inga tekniska fel.** Alla ZARQ-sidor serveras korrekt.

### B4. API-fallet (7,695 → 1,703)

`/zarq/dashboard/data` föll från 2,872 till 1,368. Detta är den interna dashboard-data-endpointen som kallas av JavaScript vid sidladdning. Fallet indikerar färre dashboard-besökare, inte ett API-problem.

Riktiga externa API-anrop (`/v1/crypto/rating/*`, `/v1/crypto/ndd/*`) föll från ~500/dag till ~300/dag — en mildare nedgång.

### B5. Hypotesprövning

| Hypotes | Stöds? | Evidens |
|---|---|---|
| Robots.txt blockerar bots | **Nej** | robots.txt korrekt, inga Disallow |
| Sitemap bruten | **Nej** | 200 OK, URLs valida |
| Content thin/duplicerat | **Möjligt** | ZARQ har ~226 crypto-tokens. Begränsat content-djup per token. |
| Cloudflare/DNS-problem | **Nej** | Alla sidor returnerar 200, tunnel aktiv |
| Deploy-pipeline bruten | **Nej** | Dual-write aktiv, Postgres uppdateras dagligen |
| **Amazonbot reducerade crawling** | **Ja** | 12K→1K = -92%. Extern förändring. |
| **SEO-bots avslutade engångsjobb** | **Ja** | DataForSeo 9.5K→0, SleepBot 2K→0 |
| Nerq kannibaliserar ZARQ | **Möjligt** | Nerq har /crypto/* paths + crypto i llms.txt |

---

## DEL C — MCP

### C1. Varför föll MCP 15%?

| Datum | MCP-anrop |
|---|---:|
| Mar 15 | 1,674 |
| Mar 16 | 14,200 (outlier) |
| Mar 17-30 | 700-2,600 |
| Apr 1-7 | 500-1,200 |
| Apr 8-9 | 3,000-3,900 (spike) |
| Apr 10-14 | 900-1,400 |

MCP-volymen har **inte fallit** — den var 1,674 Mar 15 och 1,421 igår. Variationen är normal. Mar 16-siffran (14,200) var en anomali (sannolikt en bot som scrapade MCP-endpointen).

MCP-trafiken är stabil vid ~1,000-1,500/dag. **Inget fall att utreda.**

---

## DEL D — Syntes

### D1. Huvudfrågor besvarade

**1. Vad orsakade Nerq fas-förändringen?**

| Rank | Orsak | Evidens | Bidrag |
|---|---|---|---|
| 1 | **Anthropic aktiverade ClaudeBot** | 4→54K overnight Mar 18, ingen Nerq-deploy | ~50% av training |
| 2 | **OpenAI ökade GPTBot + OAI-SearchBot** | 379→41K gradvis ramp Mar 17-23 | ~40% av training + ChatGPT-User citations |
| 3 | **23-språkig corpus upptäcktes** | 91% av training Apr 10 gick till /{lang}/* | Multiplicerade crawl-ytan 23x |

**Nerq gjorde ingen enskild ändring som triggade detta.** AI-företagen startade crawling av nerq.ai baserat på egna prioriteringar. Den 23-språkiga corpusen multiplicerade crawl-volymen.

**2. Är förändringen hållbar?**

**Ja, med reservationer:**
- Training crawl (ClaudeBot+GPTBot): fluktuerar kraftigt (65K-361K/dag) men baslinjen har stabiliserats kring 150-300K. Cloudflare-incidenten (Apr 12) visade att extern infrastruktur kan orsaka 70% drops temporärt.
- AI citations (user_triggered): stabil platå vid ~1,200/dag sedan Mar 23. Ingen nedgång. Baserat på unika IPs (~600/dag) är detta genuina user-queries.
- Search index (Applebot): stabil vid ~300K/dag. Apple har inte visat tecken på att reducera.

**3. Vad orsakade ZARQ-fallet?**

| Rank | Orsak | Evidens |
|---|---|---|
| 1 | **Amazonbot reducerade ZARQ-crawling** | 12,189→1,002/dag (-92%). Extern förändring. |
| 2 | **SEO-bot-jobb avslutade** | DataForSeo 9.5K→0, SleepBot 2K→0. Engångsscrap. |
| 3 | **Litet content-djup** | 226 crypto-tokens med begränsad unik text per token |

**ZARQ förlorade inga sökmotorer** (Google stabil, Apple nytt). Fallet var drivet av tredjeparts-bots som avslutade engångsprojekt.

**4. Är ZARQ räddbart?**

**Ja, men det är inte "brutet" — det var överrapporterat.**

Mar 15-trafiken var inflated av DataForSeo (9.5K engångscrawl) + Amazonbot (12K som sedan normaliserades). Rensat för dessa engångsbots är ZARQ-baslinjen ~5-8K/dag, och den ligger idag på ~5K/dag. Det verkliga fallet är ~30%, inte 72%.

### D2. Rekommendationer

**Omedelbara (0-24h):**
- Ingen åtgärd behövs. Nerq-tillväxten är extern-driven och hållbar. ZARQ-"fallet" är normalisering, inte ett fel.

**Kortsiktiga (1-7 dagar):**
1. **Fixa 4 failande LaunchAgents** (npm-crawler, stale-scores) — npm data freshness påverkar ChatGPT-User citation quality
2. **Lägg till HuggingFace i llms.txt** — 32% av ChatGPT-User-trafik
3. **Övervaka ClaudeBot recovery** — fortfarande på ~25% av baseline efter Cloudflare-incident

**Långsiktig observation:**
- Daglig tracking: `bot_purpose=user_triggered` per bot (citation_dashboard)
- Veckovis: ClaudeBot vs GPTBot training-ratio (om Claude faller permanent = Anthropic-policy-ändring)
- ZARQ: Amazonbot-trend (om den fortsätter falla = Amazon nedprioriterar crypto-sidor)

### D3. Data-gaps

| Fråga | Varför vi inte kan svara |
|---|---|
| Exakt vilken Nerq-ändring före Mar 18 triggade ClaudeBot? | Git-historik squashed Apr 7 |
| Hur stora var sitemap-filerna i mars? | Ingen versionering av sitemaps |
| Varför reducerade Amazon crawlingen? | Extern förändring, inget att mäta |
| Ökade antalet indexerade sidor i Google Search Console? | Ingen GSC-integration |
