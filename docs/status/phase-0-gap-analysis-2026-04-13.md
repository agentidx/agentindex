# Phase 0 Gap Analysis — 2026-04-13

**Status:** Mid-migration checkpoint
**Reviewed against:** `docs/strategy/phase-0-cloud-migration-plan.md` + `docs/adr/ADR-003-cloud-native-expansion-first.md`
**Author:** Chat-Claude audit

## TL;DR

Vi har levererat Phase 0 Week 1 **delvis** och påbörjat Week 2 **delvis**. Mellan de två ligger kritiska DR-kriterier (Backblaze, pgBackRest, restore-verification, Patroni) som **inte är implementerade**. Cutover-kriterierna för Week 2 är heller inte kompletta.

**Rekommendation:** Gör INTE trafik-cutover förrän DR-gap är stängd. Det är hela poängen med ADR-003.

---

## Slutmålet (ordagrant från planen)

> "At the end of week 2, serve 100% of nerq.ai and zarq.ai traffic from Hetzner nodes, with Mac Studio demoted to optional accelerator status, with Buzz running on the Nürnberg node."

> "Adopt a cloud-native architecture with Mac Studio and Mac Mini demoted to optional accelerators."

**Survival target:** System ska överleva permanent förlust av både Mac Studio OCH Mac Mini samtidigt (Stockholm-katastrof).

---

## Week 1 — Done criteria status

| # | Kriterium | Status |
|---|---|---|
| 1 | Nbg CPX41 provisioned, Tailscale, Postgres 16 | ✅ |
| 2 | Hel CPX41 provisioned, samma setup | ✅ |
| 3 | CPX21 worker provisioned | ✅ (100.101.184.47) |
| 4 | Full Postgres dump transferred, row counts match | ✅ (ZARQ Tier A, 3M rader) |
| 5 | Async streaming replication Nbg ↔ Hel | ⚠️ Streaming Mac→Nbg + Mac→Hel, **inte Nbg→Hel** |
| 6 | Backblaze B2 bucket, pgBackRest, first full backup | ❌ **EJ IMPLEMENTERAT** |
| 7 | Restore verification test | ❌ **EJ IMPLEMENTERAT** |
| 8 | Buzz OPERATIONSPLAN updated for migration | ⚠️ Buzz-context-doc updated idag, men OPERATIONSPLAN.md-specifik uppdatering oklar |
| 9 | SSH access till alla tre Hetzner-noder | ✅ |

**Week 1 status: 6/9 klara (67%).** Tre kritiska DR-kriterier saknas.

---

## Week 2 — Done criteria status

| # | Kriterium | Status |
|---|---|---|
| 1 | FastAPI app deployed på båda Hetzner-noder | ✅ |
| 2 | Cloudflare Load Balancer health checks | ❌ **EJ SETUP** |
| 3 | nerq.ai+zarq.ai 100% från Hetzner 24+ timmar | ❌ (0% — all trafik på Mac Studio) |
| 4 | AI citation rate inom Day 1 baseline | ⏸️ (kan inte mätas utan #3) |
| 5 | Sacred bytes drift = 0 | ✅ (3/3/3 matchar) |
| 6 | Cloudflare Tunnel decommissioned | ❌ |
| 7 | Patroni konfigurerat + failover-drill | ❌ **EJ IMPLEMENTERAT** |
| 8 | Buzz primary på Nbg | ❌ (kör fortfarande på Mac Studio) |
| 9 | SQLite analytics rsync var 10:e min | ❌ **EJ IMPLEMENTERAT** |
| 10 | Freshness SLA dashboard live | ❌ **EJ IMPLEMENTERAT** |
| 11 | pgBackRest schedule (WAL hourly, full nightly) | ❌ |
| 12 | Phase 0 retrospective | ❌ (skrivs när allt klart) |

**Week 2 status: 1/12 klara (8%).**

---

## Vad vi FAKTISKT byggde utöver planen (Day 3-4.7)

Detta var INTE i Phase 0-planen men är värdefulla byggstenar:

- ✅ `dual_write.py` — SQLite → Postgres mirror (10 LaunchAgents aktiva)
- ✅ `dual_read.py` — Postgres read-path för Hetzner-noder
- ✅ 14 systemd hardening-direktiv
- ✅ 8,022 gap-rader backfill → full data-paritet

Varför är dessa värdefulla? De möjliggör **gradvis cutover** istället för big-bang. Planen förutsatte big-bang (Week 2 Day 7: "flip to 100%"), men med dual-write kan vi köra båda parallellt och validera.

---

## Kritiska gap

### 1. Ingen DR → systemet överlever INTE planens survival target

Om Mac Studio går ner just nu:
- ✅ Hetzner-noderna har data (Postgres replicas)
- ❌ Men om Nbg Postgres kraschar finns ingen B2-backup att restore från
- ❌ Ingen restore-verification har gjorts — vi VET inte om backuper är användbara

### 2. Ingen automatisk failover

Planen säger "30-60 sekunder automatic failover". Vi har:
- Manuell SSH + systemctl-kommandon
- Ingen Patroni
- Ingen Cloudflare Load Balancer med health checks

### 3. Cloudflare Tunnel är fortfarande SPOF

All trafik går genom EN tunnel från Mac Studio. Om Mac Studio (eller tunneln) dör → downtime tills manuell ingripande.

### 4. Buzz kör fortfarande på Mac Studio

Om Mac Studio dör stannar Buzz → autonomous operations stannar → signals ingestion stannar → scores blir stale.

---

## Rekommenderad Day 5+ sekvens

Förslag på ordning som stänger Week 1-gap FÖRST, sedan Week 2:

### Day 5 — DR-grunden
- Backblaze B2 bucket
- pgBackRest på Nbg (hourly WAL + nightly full)
- Restore verification mot throwaway Postgres
- Säkrar planens survival target

### Day 6 — Patroni + Nbg↔Hel replication
- Konfigurera Nbg↔Hel streaming (idag är det Mac→båda, inte Nbg→Hel)
- Installera Patroni
- Manual failover-drill: kill Nbg postgres, verifiera Hel tar över

### Day 7 — Cloudflare Load Balancer + health checks
- Sätt upp LB med Nbg + Hel origins (via named tunnels per nod eller direct IP)
- Health checks var 30:e sekund
- Ännu 100% Mac Studio — bara LB-infra

### Day 8 — Canary cutover (25%)
- Dra 25% trafik till Hetzner
- 2-4 timmar observation
- Verifiera AI citations, sacred bytes, latens

### Day 9 — 50%, 100%
- 50% (morgon) → 100% (eftermiddag) om allt grönt
- Mac Studio hot fallback i 7+ dagar
- Phase 0 retrospective efter 24h vid 100%

### Day 10+ — Cleanup
- Buzz migreras till Nbg
- SQLite analytics rsync (10-min cadence)
- Freshness SLA dashboard
- Cloudflare Tunnel decommission (efter 7 dagar)
- Worker-roll-out på CPX22

---

## Risker om vi kör cutover utan DR

1. **Enda kopian i Hetzner-region.** Om Nbg Postgres kraschar innan B2 är uppe → total dataförlust för allt skrivet sedan migration.
2. **Ingen restore-verification = backup kan vara ovärd.** Backuper som aldrig har testats = inte backuper.
3. **Hel är replica, inte primary.** Om Nbg primary dör måste vi promota Hel manuellt (utan Patroni). Downtime under manuell promotion.
4. **ADR-003 survival target brutet.** "System must survive permanent loss of both Stockholm machines" — det är inte sant idag om något händer Nbg samtidigt.

---

## Rekommendation

**Day 5 = Backblaze + pgBackRest + restore-verification.** Detta är 3-4 timmars arbete och stänger det största hålet i planen.

Det är inte glamoröst. Men det är precis det ADR-003 säger är skillnaden mellan "har Hetzner-servrar" och "har produktionsklar cloud-arkitektur".

---

**Slutet på gap-analys.**
