# PgBouncer config change — 2026-04-23

**File (not in git):** `/opt/homebrew/etc/pgbouncer.ini`
**Backup:** `/opt/homebrew/etc/pgbouncer.ini.bak-pre-mac-decom-20260423-0817`

## Change

```diff
-agentindex_read = dbname=agentindex user=anstudio
-agentindex      = dbname=agentindex user=anstudio
+agentindex_read = host=100.79.171.54 port=5432 dbname=agentindex user=anstudio
+agentindex      = host=100.79.171.54 port=5432 dbname=agentindex user=anstudio
```

`agentindex_write` unchanged (still Nbg primary 100.119.193.70).

## Why

Mac Studio local Postgres replica dropped out of Patroni cluster
at 06:15 CEST (primary restart orphaned `mac_studio_slot`). Local
replica was frozen at LSN `333/E20000A0`, serving stale data and
causing `ReadOnlySqlTransaction` for any crawler that went via
the read pool. Redirecting both read aliases to the Hel node2
replica restores consistency.

## Rollback

```bash
cp /opt/homebrew/etc/pgbouncer.ini.bak-pre-mac-decom-20260423-0817 \
   /opt/homebrew/etc/pgbouncer.ini
brew services restart pgbouncer
```
Caveat: rolling back resumes Mac Studio's stale-data read path.
Only do this if the Hel replica is unreachable.

## Full context

See follow-up architecture decision doc (written after
`brew services stop postgresql@16` is approved and executed):
`docs/status/mac-studio-decommission-2026-04-23.md`.
