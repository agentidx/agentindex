# Sprint 3.0 Session 2 Handover — 2026-03-01

## KOMPLETT IDAG
- Paper trading live (3 portföljer, SHA-256, daily NAV automation)
- 5 paper trading API-endpoints
- zarq.ai registrerad, Cloudflare Tunnel konfigurerad
- Host-baserad routing (ZarqRouter middleware)
- zarq.ai landing page (ZARQ designspråk)
- zarq.ai/track-record (backtest-data från DB)
- zarq.ai/paper-trading (redesignad i ZARQ-design)
- NDD → DtD (Distance-to-Default) rebrand på alla ZARQ-sidor
- Redis autoheal-bugg fixad (.strip())
- Brand architecture-analys (project_docs)

## NÄSTA SESSION: Skriv om crypto_seo_pages.py
### Vad
Omskrivning av 5 render-funktioner i ZARQ designspråk:
1. `_render_crypto_landing` → /crypto
2. `_render_token_page` → /crypto/token/{id}
3. `_render_exchange_page` → /crypto/exchange/{id}
4. `_render_defi_page` → /crypto/defi/{id}
5. `_render_best_page` → /best/crypto-tokens etc

### Design
- Samma designspråk som zarq_landing.html, zarq_track_record.html, zarq_paper_trading.html
- Ljus bakgrund (--white: #fafaf9)
- Instrument Serif + IBM Plex Mono + system sans
- Warm accent (#c2956b)
- ZARQ branding, zarq.ai URLs
- ZARQ nav (Ratings, Track Record, Paper Trading, API)
- NDD → DtD överallt

### Filer
- `/agentindex/agentindex/crypto/crypto_seo_pages.py` — 1035 rader, ska skrivas om
- Referens-design: templates/zarq_landing.html, zarq_track_record.html, paper_trading.html
- Host-aware: sidor ska visa ZARQ på zarq.ai, NERQ på nerq.ai (eller bara ZARQ överallt)

### Ta bort efter omskrivning
- ZarqRebrand middleware (~/agentindex/agentindex/api/zarq_rebrand.py) — inte längre nödvändig
- Ta bort `app.add_middleware(ZarqRebrand)` från discovery.py

### Också kvar
- Token-sidor ska länkas från zarq.ai landing page
- API docs-sida (snygg, inte rå JSON)
- Sprint 3.1 planering
