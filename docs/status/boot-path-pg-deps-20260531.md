# Boot-path PG-dependency inventory — 2026-05-31

> FAS A of the 2026-05-31 recovery plan. Inventory of every code path
> that runs at uvicorn worker boot (module import-time, top-level calls,
> `mount_X()` functions called from `discovery.py`) and could block on
> a saturated PG.

## TL;DR

The boot path is **cleaner than expected**. Module-load `_init_db()`
calls are concentrated in three files (`ab_test.py`, `analytics.py`,
`observability.py`) and all of them target **SQLite** local files, not
Postgres. The only known PG-touching boot-time path was
`agentindex/review_pages.py:_ensure_reviews_table()` — already removed
yesterday in commit `f41eb34`.

What we actually have is **per-request PG saturation amplification**,
not boot-time saturation amplification. The "restart-loop" pattern from
2026-05-31 03:00 onwards is workers dying *mid-request* (not at boot)
because `pool_pre_ping=True` in `db/models.py:252` runs a `SELECT 1` on
every connection checkout and fails when PG is under load.

## Inventory table

| Source | Type | Risk | What it does | Already protected? |
|---|---|---|---|---|
| `agentindex/db/__init__.py:4` | `from db.models import init_db; if __name__ == "__main__": init_db()` | **LOW** | `init_db` only runs in `__main__` — import is a no-op | yes (guard) |
| `agentindex/db/models.py:343` | `if __name__ == "__main__": init_db()` | **LOW** | Same guard | yes |
| `agentindex/db/models.py:252` | `_engine = create_engine(...)` inside `get_engine()` | **LOW** | Lazy: only called on first session checkout | yes (lazy) |
| `agentindex/db/models.py:270` | `_write_engine = create_engine(...)` inside `get_write_engine()` | **LOW** | Lazy | yes |
| `agentindex/db/models.py:323` | `Base.metadata.create_all(engine)` inside `init_db()` | **HIGH if called from boot** | Would run DDL for all 50+ models. Not called from API boot. | yes (function-gated) |
| `agentindex/ab_test.py:107` | `_init_db()` at module top-level | LOW (SQLite) | Creates local `ab_events.db` schema. Imports cost: file IO, no PG. | yes (SQLite) |
| `agentindex/analytics.py:172` | `_init_db()` at module top-level | LOW (SQLite) | Creates `requests` table in local SQLite. | yes (SQLite) |
| `agentindex/observability.py:_init_db` (called from `mount_observability`) | called from `discovery.py:659 mount_observability(app)` | LOW (SQLite) | Creates `api_log` table in local SQLite. | yes (SQLite) |
| `agentindex/federation_api.py:_init_db` | called from `_get_conn()` per-request | LOW (SQLite, lazy) | Idempotent, per-request | yes |
| `agentindex/review_pages.py:_ensure_reviews_table` | **REMOVED 2026-05-30** (`f41eb34`) | was HIGH | Used to run PG DDL on worker boot. Fixed. | yes (deleted) |
| `agentindex/api/api_protection.py:_load_api_keys` (called from `setup_api_protection`) | called from `discovery.py:602` | LOW | Reads env var + optional JSON file. No PG. | yes |
| `agentindex/crypto/zarq_seo_builds.py:_load_slugs` (called from `mount_zarq_seo_builds`) | called from `discovery.py` | LOW | Reads a JSON file. No PG. | yes |
| `agentindex/api/middleware/deprecation_logger.py:__init__` | inside `app.add_middleware(...)` | LOW | Stores DSN string; opens no connections. Per-request opens fresh conns. | yes (deferred I/O) |
| `agentindex/db/models.py:get_engine` — `pool_pre_ping=True` | per-request | **HIGH per-request** | Every checkout runs `SELECT 1` against PgBouncer. Under Nbg saturation this either times out or fails. SQLAlchemy then discards the conn and tries to make a new one. Pile-up causes worker death. | **NO** — this is the actual amplifier |
| `agentindex/api/discovery.py:50+ mount_*` calls | various | mostly LOW | Each mount_X is a pure router-wire-up. Verified by reading the function bodies — no DB queries at import. | yes |

## The actual amplifier: `pool_pre_ping=True`

`agentindex/db/models.py:252-265`:

```python
_engine = create_engine(
    database_url,
    pool_size=2,            # Per worker: 2 base + 3 overflow = 5 max
    max_overflow=3,
    pool_pre_ping=True,     # Validate connections before use
    pool_recycle=300,       # Recycle every 5 min
    pool_timeout=5,         # Fail fast — don't wait 30s for a connection
    echo=False,
)
```

`pool_pre_ping=True` runs `SELECT 1` on every connection checkout to
test whether the connection is still alive. Under normal load this is
a sub-millisecond overhead. Under saturated PG (Nbg at 03:00 today, or
during the R-SW incident yesterday):

1. Request lands → checkout connection
2. `pool_pre_ping` SELECT 1 → blocks (PG queue full)
3. PgBouncer `query_wait_timeout=30s` cancels → conn discarded
4. SQLAlchemy creates new connection → same fate
5. After `pool_timeout=5s`, `QueuePool exhausted` exception → request fails
6. Middleware (BaseHTTPMiddleware) has the request body in an anyio
   memory stream → cleanup fires → `anyio.WouldBlock`
7. Worker dies, uvicorn restart, repeat per request

This matches the traceback we see in `api_error.log`. It's not a
boot-time failure — every WORKER STAYS UP until it gets its first
request, then dies on the connection-acquisition fail.

## Why the smoke test sees 0/23

The smoke test (`/Users/anstudio/agentindex-factory/smedjan/daily_merge/smoke_test.py`)
hits 8 base + 5 localized + 10 sacred-bytes URLs:

```
/safe/react, /compare/react-vs-vue, /rating/react.json,
/signals/react.json, /dependencies/react.json, /dimensions/react.json,
/model/react, /v1/agent/stats
/sv/safe/numpy, /de/safe/lodash, /es/safe/express, /ja/safe/django,
/ru/safe/flask
(+ 10 sacred-byte fingerprints in /safe/<slug> bodies)
```

ALL of these hit Postgres via SQLAlchemy on the read engine. Each one
triggers `pool_pre_ping`. If Nbg is saturated, all 23 fail
simultaneously → 0/23 → daily-merge rollback fires.

The smoke is correctly detecting per-request PG-failure, mis-labelled
as "boot-path" by the daily-merge's "Restart → Smoke" sequence.

## Fix candidates (FAS C decision input)

For the per-request amplifier in `db/models.py`:

### Option 1: Disable `pool_pre_ping`, rely on retry-on-failure

```python
pool_pre_ping=False,
```

Pro: 0-overhead checkout, no avalanche when PG is slow.
Con: Stale connections in the pool will cause first-request-after-pause
to fail with a real error rather than auto-retry. Need explicit
retry-on-OperationalError in the calling code.

### Option 2: Bound the `pool_pre_ping` itself with `connect_args.options`

PgBouncer transaction-mode rejects `options=`, so this only works for
direct-PG connections (which we don't use in the API). Won't work here.

### Option 3: Replace `pool_pre_ping` with a separate health-checked connection class

SQLAlchemy `Connection.execute(text("SELECT 1"))` with `SET LOCAL
statement_timeout = '500ms'` in a custom `PoolEvents.checkout` handler.
Higher complexity but precise control.

### Option 4: Aggressive `pool_recycle` + no pre_ping

```python
pool_pre_ping=False,
pool_recycle=60,    # Recycle every minute (was 300s)
```

Tradeoff: more conn creation overhead, fewer stale-conn moments. Cheap
to try.

### Option 5: Larger `pool_timeout` with explicit short statement timeout per query

```python
pool_pre_ping=False,
pool_timeout=2,     # Fail very fast on pool exhaustion
```

Plus a startup-time `SET LOCAL statement_timeout` on every session.

## Recommended ordering

1. **STEP A** — Try Option 4 first (smallest blast radius, just config).
   Run the smoke after the change. If smoke 23/23, we're done.

2. **STEP B** — If 4 isn't enough, add explicit retry-on-OperationalError
   middleware that returns 503 fast instead of crashing the worker.

3. **STEP C** — If still failing, the issue isn't pool config; it's
   actual PG slow-query saturation that needs query-level fixes
   (similar to yesterday's R-SW STEP 2).

## Why this wasn't found yesterday

Yesterday's R-SW work fixed:
- The boot-time DDL amplifier (STEP 1: `_ensure_reviews_table` removed)
- The slow query (STEP 2: text_pattern_ops index on software_registry)
- The healthcheck blind spot (STEP 3: SELECT 1 + slow-trend)

But **didn't touch the `pool_pre_ping` per-request connection-validation
behavior**. Under normal load it's invisible. Under any PG slowness it
amplifies the slowness into worker death.

The R-SW STEP 2 index removed *the specific 65-second query* that was
saturating Nbg. Anything else that pressures Nbg (other slow queries,
cron load, disk pressure on Hetzner) re-triggers the amplifier through
`pool_pre_ping` on the next request.

## Out of scope for this inventory

- Wallpaper-shifting non-PG code paths (HTTP retries, Cloudflare-edge
  caching, etc.).
- The Smedjan-canary alerting that should have caught this — separate
  FAS B work.
- Actually fixing `pool_pre_ping` — FAS C decision.
