# `migrations/zarq/` — versioned Postgres migrations for the `zarq` schema

## Naming convention

`YYYYMMDD-NN-<short-description>.sql`

- `YYYYMMDD` — the date the migration was first written (not when it was applied)
- `NN` — two-digit ordinal within that day (`01`, `02`, …)
- `<short-description>` — kebab-case verb-object (`add-rating-export-table`, not `stuff-i-did`)

Examples:
- `20260530-01-identity-defaults-and-failure-tables.sql`
- `20260612-02-add-yield-curve-cache.sql`

## Rules

1. **Every schema change MUST be a migration file in git, applied second.**
   No more direct `psql ... <<SQL>` edits against a primary. The 2026-05-30
   incident (see `docs/adr/ADR-003a-current-db-topology.md`, decision log)
   was rooted in 25 days of un-versioned ops changes.
2. **Migrations are idempotent.** Every statement must be safe to run
   against a database where it has already been applied. Use:
   - `CREATE TABLE IF NOT EXISTS` (not bare `CREATE TABLE`)
   - `CREATE INDEX IF NOT EXISTS`
   - `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
   - For non-idempotent DDL (`ALTER TABLE … ADD GENERATED AS IDENTITY`,
     `ADD CONSTRAINT`, etc.), wrap in a `DO $$ BEGIN IF NOT EXISTS (…) …`
     block that checks the relevant `pg_catalog` view first.
3. **Each file is one `BEGIN; … COMMIT;` transaction** unless the change
   genuinely cannot run inside one (e.g. `CREATE INDEX CONCURRENTLY`).
4. **Header comment** at the top of every file:
   ```sql
   -- <ISO date> <one-line purpose>
   -- Context: <link to ADR / commit / incident if applicable>
   -- Idempotent: yes
   ```
5. **DOWN script as a trailing comment block.** Not auto-runnable, but
   present so a human reviewing can revert. If the migration is one-way
   (e.g. data backfill), say so explicitly.

## Running a migration manually

```bash
psql "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio" \
    -v ON_ERROR_STOP=1 \
    -f migrations/zarq/20260530-01-identity-defaults-and-failure-tables.sql
```

`ON_ERROR_STOP=1` is mandatory — without it, `psql` continues past failures
and the transaction can end up half-applied.

## Verifying idempotency

A migration is verified idempotent when:

1. It applies cleanly against an empty schema (after `zarq-tier-a-postgres.sql`).
2. It applies cleanly against a schema where it has already been applied —
   every statement is a no-op, no rows changed, no warnings.

Test before committing:

```bash
# Run twice. Second run must complete without errors.
psql … -v ON_ERROR_STOP=1 -f migrations/zarq/your-file.sql
psql … -v ON_ERROR_STOP=1 -f migrations/zarq/your-file.sql
```

## Relationship to `docs/migrations/zarq-tier-a-postgres.sql`

`docs/migrations/zarq-tier-a-postgres.sql` is the historical baseline
schema dump from 2026-04-12. Treat it as the starting point a fresh
Postgres would receive before any of the files in this directory.
Going forward, additive changes live here, not there.

## Why we are not using Alembic / Flyway / Sqitch

For the current scope (one developer, a few tables per migration, no
production multi-tenancy), a directory of dated SQL files plus discipline
is simpler than installing a tool. If the team grows or schemas start
changing daily, revisit.
