# `migrations/public/` — versioned migrations for the `public` schema

Mirrors `migrations/zarq/` but for tables outside the `zarq.` schema.

Same conventions apply (see `migrations/zarq/README.md`):

- Naming: `YYYYMMDD-NN-<short-description>.sql`
- Idempotent (`IF NOT EXISTS` / `pg_catalog` guards for non-idempotent DDL)
- One `BEGIN; … COMMIT;` per file unless the change can't transact (e.g.
  `CREATE INDEX CONCURRENTLY`)
- DOWN script in a trailing comment

Manual apply:

```bash
psql "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio" \
    -v ON_ERROR_STOP=1 \
    -f migrations/public/<file>.sql
```

The same `*.sql` ignore + `!migrations/**/*.sql` whitelist in `.gitignore`
covers this directory automatically.
