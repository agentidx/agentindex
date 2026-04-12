# Phase 0 Day 2 — Streaming Replication ACTIVE

Date: 2026-04-12 (Sunday afternoon/evening)
Status: COMPLETE — Mac Studio primary → nerq-nbg-1 streaming replica verified end-to-end

## Accomplishments

### Streaming replication active

- Client: 100.119.193.70 (nerq-nbg-1)
- State: streaming
- Sync: async
- Lag: 47 KB (<1 second)
- Slot: nerq_nbg_replica (active, PID 84875)
- Method: physical streaming via pg_basebackup + WAL streaming

### Verification done

- pg_is_in_recovery() = true on nerq-nbg-1
- Test row written on Mac Studio appeared on nerq-nbg-1 within 3 seconds
- User creation on Mac Studio replicated to nerq-nbg-1

### pg_basebackup timing

- Start: 2026-04-12 11:21 CEST
- End:   2026-04-12 16:39 CEST
- Duration: 5h 18min (94 GB at ~5 MB/s rate-limited)
- No production disruption during transfer

### Configuration

On Mac Studio (primary):
- pg_hba.conf: host replication nbg_repl 100.119.193.70/32 scram-sha-256
- pg_hba.conf: host replication nbg_repl 100.79.171.54/32 scram-sha-256
- wal_keep_size = 1GB
- Mac Mini replicator rule temporarily disabled (noise reduction)

On nerq-nbg-1 (replica):
- postgresql.auto.conf configured by --write-recovery-conf:
  * primary_conninfo with host=100.90.152.88 user=nbg_repl
  * primary_slot_name = nerq_nbg_replica
- standby.signal present
- Postgres started via systemd, runs under postgres OS user

## What is NOT yet done (Day 3+)

- Helsinki (nerq-hel-1) replica — async cascading from Nbg or from Mac Studio
- ZARQ Tier A migration — apply DDL + data load against replicated Postgres
- App deployment on Nbg + Hel — Nerq/ZARQ uvicorn workers
- Cloudflare Load Balancer setup
- Cutover (traffic from Mac Studio to Hetzner)

## Issues parked

- Mac Mini replica broken, emits log noise every 5s. Fix: physical access
  to Mac Mini, update .pgpass with current nbg_repl password.
- Nbg Postgres has no local postgres OS user that can authenticate
  (basebackup copied Mac Studios user-setup). Not a problem for replication
  but complicates local admin access on Nbg. Solution: use a TCP connection
  as anstudio, or recreate local admin setup with known password.
- shared_buffers = 8GB on Nbg (inherited from Mac Studio config) is 50%
  of 16GB RAM. Rule of thumb is 25%. Not urgent but can be tuned later.

## Production state throughout

- Nerq + ZARQ served 200 OK throughout 5h basebackup
- Sacred bytes 2/2/1 preserved
- Some ZARQ latency spikes during basebackup, but within tolerance
- M5.1 experiment continued unaffected

## Lessons learned

1. --max-rate flag on pg_basebackup works exactly as advertised
2. Rate-limited basebackup over Tailscale is production-safe
3. pg_basebackup is the correct tool for initial replica setup, not psql CLI
4. When debugging auth errors, always check log on server side for precise
   reason (pg_hba line matched, pass fail, etc)
