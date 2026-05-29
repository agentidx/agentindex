"""
Single source of truth for all database connections.

Write path → Nbg primary (TCP over Tailscale)
Read path  → local replica (Unix socket when available)

Environment variables (one knob per concern):
  NERQ_PG_PRIMARY       Primary host (default: 100.119.193.70)
  NERQ_PG_PRIMARY_PORT  Primary port (default: 5432)
  NERQ_PG_REPLICA       Replica host (default: localhost)
  NERQ_DB_NAME          Database name (default: agentindex)
  NERQ_DB_USER          Database user (default: anstudio)

Backwards-compatible: if DATABASE_URL is set, it overrides the read path.
If ZARQ_PG_DSN is set, it overrides the write path for dual-write.

Usage:
  from agentindex.db_config import get_write_dsn, get_read_dsn
  from agentindex.db_config import get_write_conn, get_read_conn
"""

import os


# ── psycopg2 numpy adapters ──────────────────────────────────
# Scripts compute stats with numpy and pass np.float64/np.int64 directly into
# INSERT params. psycopg2 has no built-in adapter for numpy scalars and falls
# back to str(x) → SQL gets literal "np.float64(...)", which Postgres parses as
# a schema reference and fails with "schema 'np' does not exist". Registering
# here means every importer of db_config gets adapters before opening a conn.
def _register_numpy_adapters():
    try:
        import numpy as np
        from psycopg2.extensions import AsIs, register_adapter
    except Exception:
        return
    register_adapter(np.bool_, lambda x: AsIs('TRUE' if bool(x) else 'FALSE'))
    for _t in (np.float16, np.float32, np.float64):
        register_adapter(_t, lambda x: AsIs(repr(float(x))))
    for _t in (np.int8, np.int16, np.int32, np.int64,
               np.uint8, np.uint16, np.uint32, np.uint64):
        register_adapter(_t, lambda x: AsIs(repr(int(x))))


_register_numpy_adapters()


# ── Configuration ──────────────────────────────────────────
# PgBouncer on localhost:6432 routes to the right backend:
#   agentindex_write → Nbg primary (TCP)
#   agentindex_read  → local replica (socket)
# Direct connections bypass PgBouncer (for scripts, pg_dump, etc.)
PGBOUNCER_HOST = os.environ.get("NERQ_PGBOUNCER_HOST", "127.0.0.1")
PGBOUNCER_PORT = int(os.environ.get("NERQ_PGBOUNCER_PORT", "6432"))
PRIMARY_HOST = os.environ.get("NERQ_PG_PRIMARY", "100.119.193.70")
PRIMARY_PORT = int(os.environ.get("NERQ_PG_PRIMARY_PORT", "5432"))
REPLICA_HOST = os.environ.get("NERQ_PG_REPLICA", "localhost")
DB_NAME = os.environ.get("NERQ_DB_NAME", "agentindex")
DB_USER = os.environ.get("NERQ_DB_USER", "anstudio")
USE_PGBOUNCER = os.environ.get("NERQ_USE_PGBOUNCER", "1") == "1"


def get_write_dsn(fmt="sqlalchemy"):
    """DSN for the primary (writes). Via PgBouncer when available."""
    if USE_PGBOUNCER:
        if fmt == "psycopg2":
            return f"host={PGBOUNCER_HOST} port={PGBOUNCER_PORT} dbname=agentindex_write user={DB_USER}"
        return f"postgresql://{DB_USER}@{PGBOUNCER_HOST}:{PGBOUNCER_PORT}/agentindex_write"
    if fmt == "psycopg2":
        return f"host={PRIMARY_HOST} port={PRIMARY_PORT} dbname={DB_NAME} user={DB_USER}"
    return f"postgresql://{DB_USER}@{PRIMARY_HOST}:{PRIMARY_PORT}/{DB_NAME}"


def get_read_dsn(fmt="sqlalchemy"):
    """DSN for the replica (reads). Via PgBouncer when available."""
    if USE_PGBOUNCER:
        if fmt == "psycopg2":
            return f"host={PGBOUNCER_HOST} port={PGBOUNCER_PORT} dbname=agentindex_read user={DB_USER}"
        return f"postgresql://{DB_USER}@{PGBOUNCER_HOST}:{PGBOUNCER_PORT}/agentindex_read"
    if fmt == "psycopg2":
        if REPLICA_HOST == "localhost":
            return f"dbname={DB_NAME} user={DB_USER}"
        return f"host={REPLICA_HOST} dbname={DB_NAME} user={DB_USER}"
    return f"postgresql://{DB_USER}@{REPLICA_HOST}/{DB_NAME}"


def get_write_conn():
    """Raw psycopg2 connection to primary (via PgBouncer)."""
    import psycopg2
    if USE_PGBOUNCER:
        return psycopg2.connect(
            host=PGBOUNCER_HOST, port=PGBOUNCER_PORT,
            dbname="agentindex_write", user=DB_USER,
        )
    return psycopg2.connect(
        host=PRIMARY_HOST, port=PRIMARY_PORT,
        dbname=DB_NAME, user=DB_USER,
    )


def get_read_conn():
    """Raw psycopg2 connection to local replica (via PgBouncer)."""
    import psycopg2
    if USE_PGBOUNCER:
        return psycopg2.connect(
            host=PGBOUNCER_HOST, port=PGBOUNCER_PORT,
            dbname="agentindex_read", user=DB_USER,
        )
    if REPLICA_HOST == "localhost":
        return psycopg2.connect(dbname=DB_NAME, user=DB_USER)
    return psycopg2.connect(host=REPLICA_HOST, dbname=DB_NAME, user=DB_USER)
