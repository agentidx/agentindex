# NERQ PROJECT DOCS — Läs detta vid varje ny chatt-session
## Senast uppdaterad: 2026-03-01

> **Instruktion till Claude:** Läs ALLTID denna fil + SYSTEM_ARCHITECTURE.md + senaste HANDOVER först.

---

## FILÖVERSIKT

| Fil | Vad | Läs när |
|-----|-----|---------|
| `SYSTEM_ARCHITECTURE.md` | Full systemöversikt, databaser, processer, farliga operationer | **ALLTID FÖRST** |
| `HANDOVER_2026-03-01.md` | Status efter Sprint 2.5, kända issues, nästa steg | **ALLTID** |
| `NERQ_CRYPTO_SPRINT_PLAN_V4_1.md` | **MASTER SPRINT PLAN** — hela vägen från paper trading till exit | **ALLTID** |
| `NERQ_INVESTOR_PITCH_v4.pdf` | Investor pitch med alla siffror, portföljregler, track record | Vid arbete med paper trading, fund, pitch |
| `NERQ_MACHINE_FIRST_VISION.md` | Machine-first strategi, API-lager, revenue-modell, exit-story | Vid arbete med API, machine-first features |
| `NERQ_GO_TO_MARKET_MACHINES.md` | GTM-strategi: spår 1 (maskiner) + spår 2 (människor), funnel | Vid arbete med distribution, launch, BD |
| `NERQ_Friends_Family_Pitch_March_2026.pdf` | F&F pitch — ren, datadriven, 8 sidor | Referens vid pitch-arbete |

## NULÄGE (2026-03-01)

- **Sprint 2.5 KLAR.** 12 API-endpoints, Early Warning Feed, Token-sidor, MCP-tools.
- **Sprint 3.0 NÄSTA.** Paper trading start (🔴 PRIO 0) + varumärkesseparation.
- **System stabiliserat.** Buzz autoheal kör var 5 min. PostgreSQL timeouts satta.
- **Paper trading:** INTE startat ännu — ska startas i Sprint 3.0.

## KRITISKA REGLER

1. **ALDRIG ALTER TABLE på `agents`** utan statement_timeout (15GB, 4.9M rader)
2. **psql path:** `/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql`
3. **Heredoc-format** för alla terminalmkommandon
4. **Två separata DB-system:** PostgreSQL (agenter) + SQLite (krypto) — oberoende
5. **Mac Studio i Italien** — inte en cloud server

## AKTIV SPRINT

Se `NERQ_CRYPTO_SPRINT_PLAN_V4_1.md` för komplett plan. Nästa sprint: **3.0 — Paper Trading Start.**
