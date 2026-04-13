# Phase 0 Day 5 — DR Backup: Backblaze B2 + Restore Verification

Date: 2026-04-13
Status: COMPLETE — first backup uploaded, WAL archiving active, restore verified

## B2 Bucket

| Property | Value |
|---|---|
| Bucket | nerq-pgbackrest-2026 |
| ID | 743ac078b5888a5093d80812 |
| Region | EU-Central (s3.eu-central-003.backblazeb2.com) |
| Visibility | allPrivate |
| Auth | Master key (bucket-only key rotation deferred) |

## First Full Backup

| Metric | Value |
|---|---|
| Method | pg_dump --format=custom --compress=zstd:3 |
| Source | Nbg replica (127.0.0.1:5432, streaming from Mac Studio) |
| Dump size | 4.1 GB |
| Dump time | 4m48s |
| Upload time | 21s |
| Database size | ~91 GB uncompressed |
| Compression ratio | 22:1 |

## WAL Archiving

Configured via pgBackRest `archive_mode = always` on the Nbg replica.
The standby archives each replayed WAL segment to B2.

```
archived_count: 7+
last_archived_wal: 00000001000002E0000000A1
last_archived_time: 2026-04-13 09:44
```

WAL segments visible in B2: `backup/archive/agentindex/16-1/`

## Restore Verification Test

**Full restore to throwaway Postgres instance on Nbg, port 5433.**

| Table | Restored | Live replica | Match |
|---|---:|---:|:---:|
| agents | 5,033,771 | 5,033,771 | ✅ |
| zarq.crypto_ndd_alerts | 1,532,199 | 1,532,199 | ✅ |
| zarq.crypto_price_history | 1,125,978 | 1,125,978 | ✅ |
| zarq.crypto_ndd_daily | 235,821 | 235,821 | ✅ |
| zarq.vitality_scores | 15,149 | 15,149 | ✅ |
| zarq.nerq_risk_signals | 6,560 | 6,560 | ✅ |
| zarq.crypto_rating_daily | 3,743 | 3,743 | ✅ |

**7/7 tables match exactly. 0 errors in pg_restore.**

Restore time: 34m30s (dominated by index creation on 5M agents table).
Throwaway instance cleaned up immediately after verification.

## Cron Schedule

```
/etc/cron.d/pgbackup-nerq on Nbg:
- Sunday 02:00 UTC: Full pg_dump → B2 (all schemas)
- Mon-Sat 03:00 UTC: zarq schema only → B2 (daily differential)
- WAL archiving: continuous via pgBackRest archive_command
```

## pgBackRest Standby Limitation

pgBackRest's `backup` command requires a connection to the primary
PostgreSQL server. Since Mac Studio's Postgres doesn't accept TCP
connections from Nbg (only /tmp unix socket), pgBackRest backup cannot
run from the standby.

**Workaround:** Using `pg_dump` (which works on read-only replicas)
for scheduled backups. pgBackRest is used ONLY for WAL archiving
(`archive_command`), which works on standbys with `archive_mode = always`.

**Future:** When the primary moves to Nbg (Patroni failover), pgBackRest
full/differential backup will work natively.

## Postgres Standby Config Changes (Nbg)

Added to `/etc/postgresql/16/main/conf.d/pgbackrest.conf`:
```
archive_mode = always
archive_command = 'pgbackrest --stanza=agentindex archive-push %p'
hot_standby_feedback = on
max_standby_streaming_delay = 300s
```

## Monthly Cost Estimate

| Component | Monthly |
|---|---|
| B2 storage: 4.1 GB full + 6 × ~200 MB daily + WAL | ~$0.03 |
| B2 transactions (Class B reads, Class A writes) | ~$0.01 |
| B2 egress (restore test only) | $0.00 |
| **Total** | **~$0.04/month** |

## Rollback

```bash
# Disable WAL archiving
ssh nerq-nbg "sudo rm /etc/postgresql/16/main/conf.d/pgbackrest.conf && sudo systemctl restart postgresql@16-main"

# Remove cron
ssh nerq-nbg "sudo rm /etc/cron.d/pgbackup-nerq"

# Delete bucket (after emptying)
b2 bucket delete nerq-pgbackrest-2026
```

## Gap Analysis — Week 1 DR Criteria After Day 5

| # | Kriterium | Before | After |
|---|---|---|---|
| 6 | Backblaze B2 bucket, backup, first full | ❌ | ✅ |
| 7 | Restore verification test | ❌ | ✅ |
| 11 | WAL archiving schedule | ❌ | ✅ |

**Week 1 DR status: 9/9 (100%)** — all criteria met.
