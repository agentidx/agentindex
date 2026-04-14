# Temporal History — Status 2026-04-14

## Status: TRE SEPARATA SYSTEM EXISTERAR, ALLA PÅGÅENDE

Det finns ingen enskild "temporal historik-implementation" — tre separata system sparar score-historik, alla skapade vid olika tillfällen:

---

### System 1: `daily_snapshots` (Postgres)

| Metric | Värde |
|---|---:|
| Rader | **28,922,446** |
| Storlek | 6.7 GB |
| Period | 2026-03-19 → 2026-04-14 (27 dagar) |
| Tillväxt | ~1,071K rader/dag |
| LaunchAgent | `com.nerq.signal-warehouse` (04:00 dagligen) |
| Status LaunchAgent | **exit 1** (failar, se nedan) |
| Kod | `intelligence/daily_snapshot.py` |

**Vad sparas:** Per entity per dag: trust_score, trust_grade, downloads, stars, open_issues, last_commit_days, contributors, registry.

**Problem:** LaunchAgent `com.nerq.signal-warehouse` har exit code 1 (failar). Senaste lyckade körning ej verifierad — data finns t.o.m. 2026-04-14 men det kan vara från en annan process eller manuell körning. 

**Tillväxt:** ~1M rader/dag × 30 dagar = 30M rader. Vid denna takt: 365M rader/år = ~80 GB. Partitionering eller retention-policy behövs.

---

### System 2: `trust_score_history` (Postgres)

| Metric | Värde |
|---|---:|
| Rader | **4,808,972** |
| Storlek | 2.2 GB |
| Period | Bara 2026-02-25 (en enda dag) |
| Kolumner | agent_id, snapshot_date, trust_score, grade, risk_level, dimensions (jsonb), peer/category rank |

**Problem:** Data bara från EN dag (25 feb). Ingen återkommande population. Detta verkar vara en engångs-dump som aldrig fick ett cron-jobb.

---

### System 3: Freshness Pipeline Snapshots (JSON)

| Metric | Värde |
|---|---:|
| Filer | 3 (scores-latest.json, scores-2026-04-13.json, scores-2026-04-14.json) |
| Entities per fil | 9,993 |
| Format | JSON dict: slug → {score, grade, cve, registry} |
| LaunchAgent | `com.nerq.freshness-daily` (08:30 dagligen) |
| Status | ✅ Fungerar (skapade April 13 + 14) |

**Vad sparas:** Top 10K entities trust scores per dag. Används av `freshness_pipeline.py` för delta-detektion.

**Begränsning:** Bara top 10K entities (av 2.47M). Bara 2 dagars historik. Arkivformat (JSON-filer) inte querybart utan att ladda i minne.

---

## Sammanfattning

| System | Klar? | Coverage | Tillväxt/dag | Fungerar? |
|---|---|---:|---:|---|
| daily_snapshots | ✅ 27 dagar data | ~1M entities | 1.07M rader | ⚠️ LaunchAgent exit 1 |
| trust_score_history | ❌ 1 dags data | 4.8M entities | 0 | ❌ Aldrig schemalagd |
| freshness snapshots | ✅ 2 dagar | 10K entities | 10K rader | ✅ Fungerar |

## Vad behöver göras

1. **Fixa `com.nerq.signal-warehouse`** (exit 1) — troligen DATABASE_URL pekar på Mac Studio som nu är replica. Byt till Nbg (`100.119.193.70`).

2. **Verifiera att daily_snapshots-data för April 14 faktiskt är komplett** — kolla om alla registries har snapshots idag.

3. **Bestäm retention-policy** — 1M rader/dag = 80 GB/år. Antingen: partitionering, aggregering (vecko-snapshots för >90 dagar), eller radering av old data.

4. **trust_score_history:** Antingen deprecera (daily_snapshots gör samma sak) eller sätt upp daglig population. Undvik dubbel-lagring.
