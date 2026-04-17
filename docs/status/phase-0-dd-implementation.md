# Phase 0 DD-Implementation Status

## Steg 1: statement_timeout 5s → 30s (2026-04-17)

### Rotorsak
`statement_timeout` var satt på DATABASE-nivå (`ALTER DATABASE agentindex SET statement_timeout = '5s'`), inte server-nivå. Database-level override tar företräde över postgresql.conf/auto.conf.

### Fix
`ALTER DATABASE agentindex SET statement_timeout = '30s'` på Nbg primary (repliceras automatiskt).
Also: Patroni DCS config + ALTER SYSTEM på alla 3 noder som backup.

### Status: KLAR
Alla 3 noder visar `SHOW statement_timeout = 30s`.

---

## Steg 2b-fix: pgBackRest timeline switch (2026-04-17)

### Rotorsak
pgBackRest på Nbg pekade på `pg1-host=100.90.152.88` (Mac Studio, gammal primary). Efter Day 6c switch (Apr 14) är Nbg primary. Config uppdaterades aldrig → archive_command failar tyst → 4,894 WAL-filer (77 GB) ackumulerade sedan Apr 13.

### Fix
- Removed `pg1-host` and `pg1-host-user` from `/etc/pgbackrest/pgbackrest.conf`
- Updated `pg1-path` to `/var/lib/postgresql/16/main` (Nbg local)
- `pgbackrest stanza-upgrade` → timeline 2 aktiv
- PG archiver startade automatiskt efter config-fix

### Status vid commit
- Archiver: ~1 fil/s, ~4,856 filer kvar (~80 min)
- Replication: OK (2 streaming replicas, 23 KB lag)
- API: opåverkat
- Disk Nbg: 108 GB ledigt (WAL cleanas efter archiving klar)
- Config backup: `/etc/pgbackrest/pgbackrest.conf.bak.20260417`

### Uppföljning (kör efter ~80 min)
```bash
bash scripts/check_pgwal_cleanup.sh
```
Förväntade resultat:
- `.ready` count = 0
- `pg_wal` < 5 GB
- Disk > 175 GB ledigt

Sedan: `CHECKPOINT` på Nbg → WAL cleanup → disk frigjord → table swap möjlig.

---

## Steg 2b: agent_jurisdiction_status table swap
**Status:** BLOCKERAD — väntar på WAL cleanup (108 GB ledigt, behöver 114 GB)
**Estimated unblock:** ~80 min efter archiver klar + CHECKPOINT → ~185 GB ledigt
