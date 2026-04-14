# npm Dependency Graph Collection — Started 2026-04-14

## What was built

Background batch job that collects dependency edges from the npm registry for all 528K npm packages in our database.

### Architecture

- **Script:** `scripts/collect_npm_dependencies.py`
- **Storage:** PostgreSQL `dependency_edges` table on Nbg (100.119.193.70)
- **Rate limit:** 1 req/s (polite, avoids npm rate limiting)
- **Priority:** Top packages by downloads first
- **LaunchAgent:** `com.nerq.npm-dependency-collector` runs daily at 03:00

### Schema

```sql
dependency_edges (
    id SERIAL PRIMARY KEY,
    entity_from TEXT NOT NULL,      -- source package
    entity_to TEXT NOT NULL,        -- dependency package
    dependency_type TEXT NOT NULL,  -- direct|dev|peer|optional|marker
    version_range TEXT,
    registry TEXT DEFAULT 'npm',
    observed_at TIMESTAMPTZ DEFAULT NOW()
)
-- Unique constraint: (entity_from, entity_to, dependency_type, registry)
```

### Dependency types collected

| Type | npm field | Meaning |
|------|-----------|---------|
| direct | dependencies | Runtime deps |
| dev | devDependencies | Build/test deps |
| peer | peerDependencies | Host-provided deps |
| optional | optionalDependencies | Optional deps |
| marker | (synthetic) | Package has 0 deps (avoids re-processing) |

### Progress tracking

```bash
python3 scripts/collect_npm_dependencies.py --status   # show progress
```

### Timeline

- **Batch 1 (current):** 10,000 top packages, ~2.8 hours at 1 req/s
- **Full coverage:** 528K packages, ~6 days at 1 req/s
- Daily LaunchAgent picks up remaining packages each night

### What this enables

1. **Dependency depth scoring:** How deep is a package in the dependency tree?
2. **Blast radius estimation:** If package X is compromised, how many packages are affected?
3. **Supply chain risk:** Single-maintainer packages that are deeply depended upon
4. **Cross-referencing with trust scores:** Low-trust packages with high dependency counts = high risk

### Test results

Initial test (5 packages): 56 edges, 0 errors, 11.2 avg edges/package.
