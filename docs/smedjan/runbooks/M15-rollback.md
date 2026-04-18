# M15 rollback — restore `smedjan` schema and `public.ai_demand_scores` on Nerq primary

**When to use:** only if something Smedjan-adjacent breaks within the
first few days after the M15 drop (2026-04-18) and the evidence points
to a missing Nerq-primary-side table. In normal hybrid operation this
runbook is **never needed** — smedjan writes live on the Hetzner
`smedjan` host, Nerq primary only serves read-only Nerq data to
`smedjan_readonly`.

## What was dropped

On Nerq primary (`100.119.193.70` / `anderss-mac-studio`, agentindex DB):

```sql
DROP TABLE IF EXISTS public.ai_demand_scores CASCADE;
DROP SCHEMA IF EXISTS smedjan CASCADE;
```

Before the drop the canonical data was captured with:

```bash
pg_dump -h 100.119.193.70 -U anstudio -d agentindex \
        -n smedjan --data-only --column-inserts --no-owner --no-privileges \
        -f /tmp/smedjan-data-migration.sql
```

Row counts at the moment of the dump:

| Table / Object | Rows |
|---|---:|
| `smedjan.tasks` | 13 |
| `smedjan.evidence_signals` | 0 |
| `smedjan.worker_heartbeats` | 2 |
| `public.ai_demand_scores` | 44,328 (stale; fresh copy 43,950 rows already in smedjan DB on Hetzner) |

## Where the backup lives

- **Mac Studio:** `~/smedjan/migration-backups/2026-04-18-pre-drop.sql` (mode 600)
- **smedjan:** `/home/smedjan/smedjan/migration-backups/2026-04-18-pre-drop.sql` (mode 600)

Two copies intentionally — one on each host so a loss of either machine
still leaves us with a restorable dump.

## Restore procedure

The dump is `--data-only --column-inserts`. It assumes the **schema**
already exists. If the drop removed the schema (it did for
`smedjan.*`), recreate it first.

```bash
# 1. Recreate the smedjan schema skeleton on Nerq primary (idempotent).
/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
    -h 100.119.193.70 -U anstudio -d agentindex \
    -f ~/agentindex/smedjan/schema.sql

# 2. Recreate public.ai_demand_scores (schema + indexes).
/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
    -h 100.119.193.70 -U anstudio -d agentindex <<'SQL'
CREATE TABLE IF NOT EXISTS public.ai_demand_scores (
    slug              text PRIMARY KEY,
    score             real NOT NULL,
    last_30d_queries  integer NOT NULL,
    computed_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ai_demand_scores_score ON public.ai_demand_scores (score DESC);
SQL

# 3. Load the data from the backup.
/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
    -h 100.119.193.70 -U anstudio -d agentindex \
    -v ON_ERROR_STOP=1 \
    -f ~/smedjan/migration-backups/2026-04-18-pre-drop.sql

# 4. Re-populate public.ai_demand_scores from the current fresh copy in
#    the smedjan DB (the backup only covers smedjan schema; it does NOT
#    include public.ai_demand_scores). Worth doing only if callers outside
#    this hybrid demand that table back on Nerq primary.
SMEDJAN_APP_PW=$(grep SMEDJAN_APP_PW ~/smedjan/config/.env | cut -d= -f2)
PGPASSWORD=$SMEDJAN_APP_PW /opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
    -h smedjan -U smedjan_app -d smedjan \
    -c "COPY smedjan.ai_demand_scores TO STDOUT" \
  | /opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
    -h 100.119.193.70 -U anstudio -d agentindex \
    -c "COPY public.ai_demand_scores FROM STDIN"
```

### Verify the restore

```bash
/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql \
    -h 100.119.193.70 -U anstudio -d agentindex -c "
SELECT status, count(*) FROM smedjan.tasks GROUP BY status ORDER BY status;
SELECT count(*) FROM smedjan.evidence_signals;
SELECT count(*) FROM smedjan.worker_heartbeats;
SELECT count(*) FROM public.ai_demand_scores;
"
```

Expected: 8 pending + 4 queued + 1 needs_approval for tasks; 0 evidence;
2 heartbeats; ≥ 43,000 ai_demand_scores rows.

## Indicators that **would** warrant rollback

- A previously-unknown Nerq-prod script errors with
  `relation "smedjan.tasks" does not exist` or
  `relation "public.ai_demand_scores" does not exist`.
- Buzz reports a failure referencing `smedjan` schema.
- A recent (< 7 days) ad-hoc query by Anders against Nerq primary
  touched these tables and broke.

If none of these happen within 7 days of the drop, the backup can stay
put — it costs nothing on disk and documents the state at cutover.
