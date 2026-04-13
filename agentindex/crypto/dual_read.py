"""
Dual-read helper: PostgreSQL (zarq schema) ← SQLite fallback.

Phase 0 Day 4.5: Read-path counterpart to dual_write.py.
When ZARQ_READ_POSTGRES=1, reads from zarq.* in PostgreSQL.
Otherwise reads from SQLite crypto_trust.db (unchanged behavior).

The Postgres path wraps psycopg2 to behave like sqlite3.connect() — same
execute/fetchone/fetchall interface, dict-like row access.
"""

import os
import re
import sqlite3
import threading

_ENABLED = os.environ.get("ZARQ_READ_POSTGRES") == "1"

# Tier A tables — only these get the zarq. prefix
_TIER_A = {
    "nerq_risk_signals", "crypto_ndd_alerts", "crypto_price_history",
    "external_trust_signals", "compatibility_matrix", "chain_dex_volumes",
    "crypto_pipeline_runs", "agent_dashboard", "crypto_ndd_daily",
    "crypto_rating_daily", "vitality_scores", "defi_yields",
}

# Table name pattern for prefix injection
_TABLE_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _TIER_A) + r")\b"
)

# ── Postgres connection pool (shared with dual_write if loaded) ──
_pool = None
_pool_lock = threading.Lock()
PG_DSN = os.environ.get(
    "DATABASE_URL",
    "host=/tmp port=5432 dbname=agentindex user=anstudio"
)


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                import psycopg2.pool
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2, maxconn=10, dsn=PG_DSN
                )
    return _pool


def _translate_sql(sql):
    """Add zarq. prefix to Tier A tables and convert ? → %s."""
    pg_sql = _TABLE_RE.sub(r"zarq.\1", sql)
    pg_sql = pg_sql.replace("?", "%s")
    return pg_sql


class _PgRow(dict):
    """Dict subclass that also supports integer index access like sqlite3.Row."""
    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = values
        self._columns = columns

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)

    def keys(self):
        return self._columns


class _PgCursorResult:
    """Wraps a psycopg2 cursor's result to match sqlite3 cursor interface."""
    def __init__(self, cursor):
        self._cur = cursor
        self._columns = [desc[0] for desc in cursor.description] if cursor.description else []

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            self._cur.close()
            return None
        return _PgRow(self._columns, row)

    def fetchall(self):
        rows = self._cur.fetchall()
        result = [_PgRow(self._columns, r) for r in rows]
        self._cur.close()
        return result

    def __iter__(self):
        for row in self._cur:
            yield _PgRow(self._columns, row)


class _PgConnectionWrapper:
    """Wraps a psycopg2 connection to behave like sqlite3.connect().

    Translates SQL (? → %s, table → zarq.table) and returns
    dict-like rows compatible with sqlite3.Row.
    """
    def __init__(self, pool):
        self._pool = pool
        self._conn = pool.getconn()
        self._conn.autocommit = True  # read-only, no transactions needed

    def execute(self, sql, params=None):
        pg_sql = _translate_sql(sql)
        cur = self._conn.cursor()
        cur.execute(pg_sql, params or ())
        return _PgCursorResult(cur)

    def executemany(self, sql, rows):
        pg_sql = _translate_sql(sql)
        cur = self._conn.cursor()
        cur.executemany(pg_sql, rows)
        return _PgCursorResult(cur)

    def close(self):
        if self._conn:
            try:
                self._pool.putconn(self._conn)
            except Exception:
                pass
            self._conn = None

    def commit(self):
        pass  # read-only, no-op

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, value):
        pass  # ignore — our wrapper always returns dict-like rows


# ── Public API ───────────────────────────────────────────────

def get_crypto_db(sqlite_path=None):
    """Get a database connection for reading ZARQ/crypto data.

    When ZARQ_READ_POSTGRES=1: returns a Postgres wrapper.
    Otherwise: returns a sqlite3 connection to crypto_trust.db.
    """
    if _ENABLED:
        pool = _get_pool()
        return _PgConnectionWrapper(pool)

    # Default: SQLite
    if sqlite_path is None:
        sqlite_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "crypto_trust.db"
        )
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def is_enabled():
    return _ENABLED


def reload_flag():
    global _ENABLED
    _ENABLED = os.environ.get("ZARQ_READ_POSTGRES") == "1"
