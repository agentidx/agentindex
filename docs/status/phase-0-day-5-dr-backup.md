# Phase 0 Day 5 — DR Backup: pgBackRest + Backblaze B2 + PITR Verified

Date: 2026-04-13
Status: COMPLETE — pgBackRest full backup + WAL archiving + PITR verified

## B2 Bucket

| Property | Value |
|---|---|
| Bucket | nerq-pgbackrest-2026 |
| ID | 743ac078b5888a5093d80812 |
| Region | EU-Central (s3.eu-central-003.backblazeb2.com) |
| Visibility | allPrivate |
| Auth | Master key (bucket-only key rotation deferred) |

## pgBackRest Full Backup

| Metric | Value |
|---|---|
| Method | pgBackRest full backup (zst:3 compression) |
| Source | Mac Studio primary (Tailscale 100.90.152.88:5432) |
| Backup label | 20260413-110301F |
| Database size | 91 GB |
| Backup size on B2 | 12.5 GB |
| Compression ratio | 7.3:1 |
| Duration | 24m38s |
| WAL range | 00000001000002E0000000B1 → B5 |
| File count | 2,164 |

```
stanza: agentindex
    status: ok
    cipher: none
    db (current)
        wal archive min/max (16): 00000001000002E00000009B/00000001000002E0000000B5
        full backup: 20260413-110301F
            timestamp start/stop: 2026-04-13 11:03:01+02 / 2026-04-13 11:27:38+02
            database size: 91GB, repo1: backup set size: 12.5GB
```

## WAL Archiving

**Dual WAL archiving active:**
- **Mac Studio primary:** `archive_mode = on`, archives via pgBackRest to B2
- **Nbg standby:** `archive_mode = always`, archives replayed WAL to B2

Both sources write to the same B2 bucket (`backup/archive/agentindex/`).

## PITR Verification — PASSED

Point-in-Time Recovery tested by:
1. Inserting `id=1` at `11:28:28` into `dr_pitr_test` table
2. Inserting `id=2` at `11:28:33`
3. Restoring to target time `11:28:30` (between the two inserts)
4. Starting restored instance on port 5434

**Result:**
```
=== RESTORED (port 5434, target time 11:28:30) ===
 id |             ts
----+----------------------------
  1 | 2026-04-13 11:28:28.621288    ← only id=1 (correct!)
(1 row)

=== PRIMARY (port 5432, current) ===
 id |             ts
----+----------------------------
  1 | 2026-04-13 11:28:28.621288
  2 | 2026-04-13 11:28:33.654157    ← id=2 exists
(2 rows)
```

**PITR correctly recovered to a point between the two inserts.** Full PITR capability confirmed.

## Restore Verification (Full) — PASSED

From earlier pg_dump restore test (7/7 tables match):

| Table | Restored | Live | Match |
|---|---:|---:|:---:|
| agents | 5,033,771 | 5,033,771 | ✅ |
| zarq.crypto_ndd_alerts | 1,532,199 | 1,532,199 | ✅ |
| zarq.crypto_price_history | 1,125,978 | 1,125,978 | ✅ |
| zarq.crypto_ndd_daily | 235,821 | 235,821 | ✅ |
| zarq.vitality_scores | 15,149 | 15,149 | ✅ |
| zarq.nerq_risk_signals | 6,560 | 6,560 | ✅ |
| zarq.crypto_rating_daily | 3,743 | 3,743 | ✅ |

## Cron Schedule (Nbg)

```
/etc/cron.d/pgbackup-nerq:
- Sunday 02:00 UTC: pgbackrest --type=full backup
- Mon-Sat 03:00 UTC: pgbackrest --type=diff backup
- WAL archiving: continuous via archive_command on both primary + standby
```

## Infrastructure Changes

### Mac Studio (Primary)
- `listen_addresses`: already included Tailscale IP 100.90.152.88
- `pg_hba.conf`: added trust access for `anstudio` from Nbg (100.119.193.70/32)
- `archive_mode = on` (required Postgres restart)
- `archive_command = 'pgbackrest --stanza=agentindex archive-push %p'`
- pgBackRest 2.58.0 installed via brew
- Config at `/opt/homebrew/etc/pgbackrest/pgbackrest.conf`

### Nbg (Standby)
- pgBackRest config updated: `pg1-host=100.90.152.88` (Mac Studio via Tailscale)
- Cron updated to use pgBackRest (replaces pg_dump)
- `archive_mode = always` + `hot_standby_feedback = on` (kept from earlier)

## Monthly Cost Estimate

| Component | Monthly |
|---|---|
| B2 storage: 12.5 GB full × 2 + 6 daily diffs (~2 GB each) + WAL | ~$0.25 |
| B2 Class A transactions (writes) | ~$0.05 |
| B2 Class B transactions (reads, rare) | ~$0.01 |
| **Total** | **~$0.31/month** |

## Rollback

```bash
# Mac Studio: revert archive_mode
rm /opt/homebrew/var/postgresql@16/conf.d/pgbackrest.conf
/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/pg_ctl -D /opt/homebrew/var/postgresql@16 restart

# Mac Studio: revert pg_hba.conf (remove last 3 lines)
# Mac Studio: revert listen_addresses if changed

# Nbg: remove cron + pgbackrest config
ssh nerq-nbg "sudo rm /etc/cron.d/pgbackup-nerq /etc/pgbackrest/pgbackrest.conf"

# B2: delete bucket (after emptying)
b2 bucket delete nerq-pgbackrest-2026
```

## Gap Analysis — Week 1 DR Criteria

| # | Kriterium | Before Day 5 | After Day 5.1 |
|---|---|---|---|
| 6 | Backblaze B2 + pgBackRest backup | ❌ | ✅ (pgBackRest full) |
| 7 | Restore verification | ❌ | ✅ (PITR verified) |
| 11 | WAL archiving + backup schedule | ❌ | ✅ (cron active) |

**Week 1 DR criteria: 9/9 (100%) — all met with PITR capability.**
