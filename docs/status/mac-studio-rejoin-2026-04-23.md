# Mac Studio Rejoin — 2026-04-23

## Bakgrund

Primary-restart 06:15 CEST orphaned `mac_studio_slot`. Legacy
non-Patroni configured replica på Mac Studio (primary_conninfo
+ primary_slot_name i postgresql.auto.conf) tappade WAL-streaming.
Mac Studio frystes vid LSN `333/E20000A0`. Datadrift eskalerade
över dagen — nya rader på primary saknades i lokala reads.

## Process

### FAS A — redirect reads till Hel node2
- `pgbouncer.ini`: `agentindex_read` + `agentindex` → `host=100.79.171.54`
- `agentindex/db_config.py`: hardkodade `REPLICA_HOST = "100.79.171.54"`, `USE_PGBOUNCER = False`
- **Nyckel-fynd efter 3 rundor diagnostik**: workers fortsatte träffa localhost:5432 tills
  vi upptäckte att `load_dotenv()` (från `crypto/wallet_behavior.py` et al) injicerade
  `DATABASE_URL=postgresql://localhost/agentindex` i `os.environ`, och
  `db/models.py:get_engine()` läste den FÖRST → bypassade db_config.
  Fix: kommenterade raden i `.env`.

### FAS B — pg_basebackup från primary
- Skapade `mac_studio_slot` på Nbg primary.
- Stoppade lokal postgres, flyttade data-dir till `postgresql@16.bak-20260423-114646`.
- `pg_basebackup -h 100.119.193.70 -U replicator -X stream -P -R -S mac_studio_slot`
- **Första försöket** (62 GB, 74% klart) föll eftersom vi SIGSTOP:ade processen
  under 5xx-burst — primary `wal_sender_timeout` (60s default) avaktiverade sessionen,
  pg_basebackup rensade data-dir vid cleanup.
- **Andra försöket** (62 min totalt) körde utan paus, exit 0, 82 GB.

### FAS C — failback till lokal streaming
- Reverterade `db_config.py` och `pgbouncer.ini` från backups.
- Restartade API. Workers tillbaka på PgBouncer → Unix socket → local replica.

## Resultat

- Mac Studio: streaming replica, timeline 4, <1 MB lag
- Read-path: lokal Unix socket, ~5 ms latens
- Data: fresh (`count WHERE lower(name)='nordvpn'` 0 → 6 rader)
- Regression: **12/12 PASS** (T10 tillbaka grön efter att ha FAIL:at hela morgonen)
- Primary `pg_stat_replication`: node2 + walreceiver båda streaming, lag=168 KB

## Lessons learned

- **pg_basebackup kan INTE pausas med SIGSTOP** längre än primary `wal_sender_timeout`
  (60s default). Under replication: accept eller abort, inte paus.
- `.env`-injicerade env-vars via `load_dotenv()` kan tyst bypassa centraliserad
  db-config. Sub-module imports kör load_dotenv på nivå 2-3 djupt.
  Ska bara sätta saker som är riktigt globala; DATABASE_URL hör inte dit.
- Smedjan worker-last + Hel-latens (~12ms RTT) + `--limit-concurrency 50` saturerar
  API under bot-bursts. Vid cold cache gav reads 1-2 sek. Framtida mitigering:
  `--limit-concurrency 100-200`, eller fler Redis-cachade long-tail-sidor.

## Ändrade filer

```
agentindex/db_config.py         → reverterad, identisk med pre-rejoin
agentindex/api/discovery.py     → temp /v1/db-debug endpoint tillagd+borttagen (netto 0)
.env                            → DATABASE_URL-raden kommenterad (förhindrar bypass)
/opt/homebrew/etc/pgbouncer.ini → reverterad, identisk med pre-rejoin
```

Backups flyttade till `~/Desktop/April/rejoin-backups/`.

## Cleanup kvar (ej akut)

- `/opt/homebrew/var/postgresql@16.bak-20260423-114646` (80 GB frusen data) — kan
  rensas efter ~24h om streaming förblir stabil
- `/opt/homebrew/etc/pgbouncer.ini.bak-pre-mac-decom-20260423-0817` — kan
  behållas som referens
