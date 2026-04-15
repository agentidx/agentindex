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

# ── Configuration ──────────────────────────────────────────
PRIMARY_HOST = os.environ.get("NERQ_PG_PRIMARY", "100.119.193.70")
PRIMARY_PORT = int(os.environ.get("NERQ_PG_PRIMARY_PORT", "5432"))
REPLICA_HOST = os.environ.get("NERQ_PG_REPLICA", "localhost")
DB_NAME = os.environ.get("NERQ_DB_NAME", "agentindex")
DB_USER = os.environ.get("NERQ_DB_USER", "anstudio")


def get_write_dsn(fmt="sqlalchemy"):
    """DSN for the primary (writes). Always TCP to Nbg."""
    if fmt == "psycopg2":
        return f"host={PRIMARY_HOST} port={PRIMARY_PORT} dbname={DB_NAME} user={DB_USER}"
    return f"postgresql://{DB_USER}@{PRIMARY_HOST}:{PRIMARY_PORT}/{DB_NAME}"


def get_read_dsn(fmt="sqlalchemy"):
    """DSN for the replica (reads). Local socket when possible."""
    if fmt == "psycopg2":
        if REPLICA_HOST == "localhost":
            return f"dbname={DB_NAME} user={DB_USER}"
        return f"host={REPLICA_HOST} dbname={DB_NAME} user={DB_USER}"
    return f"postgresql://{DB_USER}@{REPLICA_HOST}/{DB_NAME}"


def get_write_conn():
    """Raw psycopg2 connection to primary."""
    import psycopg2
    return psycopg2.connect(
        host=PRIMARY_HOST, port=PRIMARY_PORT,
        dbname=DB_NAME, user=DB_USER,
    )


def get_read_conn():
    """Raw psycopg2 connection to local replica."""
    import psycopg2
    if REPLICA_HOST == "localhost":
        return psycopg2.connect(dbname=DB_NAME, user=DB_USER)
    return psycopg2.connect(host=REPLICA_HOST, dbname=DB_NAME, user=DB_USER)
