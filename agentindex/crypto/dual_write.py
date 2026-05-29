"""
Dual-write helper: SQLite → PostgreSQL (zarq schema) mirroring.

Phase 0 Day 3: Every SQLite write to Tier A tables is mirrored to
PostgreSQL zarq.* tables. Postgres failures are logged but never block
SQLite writes.

Enable:  export ZARQ_DUAL_WRITE=1
Disable: unset ZARQ_DUAL_WRITE  (or set to anything other than "1")

Failures go to two places: the local file log AND zarq.dual_write_failures
(best-effort — if PG itself is down, only the file log captures it). This
exists so silent dual-write breakage stops being invisible.
"""

import logging
import os
import re
import threading

# Importing db_config registers numpy → psycopg2 adapters globally (idempotent).
# Without this, np.float64 values get str()-formatted into SQL as "np.float64(…)"
# and Postgres rejects with 'schema "np" does not exist'.
from agentindex import db_config  # noqa: F401

_ENABLED = os.environ.get("ZARQ_DUAL_WRITE") == "1"

# ── Logging ──────────────────────────────────────────────────
_log = logging.getLogger("zarq.dual_write")
_log_handler = None

def _setup_logging():
    global _log_handler
    if _log_handler:
        return
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    _log_handler = logging.FileHandler(os.path.join(log_dir, "dual_write_errors.log"))
    _log_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _log.addHandler(_log_handler)
    _log.setLevel(logging.INFO)


# ── PostgreSQL connection pool (lazy) ────────────────────────
_pool = None
_pool_lock = threading.Lock()

def _default_write_dsn():
    from agentindex.db_config import get_write_dsn
    return get_write_dsn(fmt="psycopg2")

PG_DSN = os.environ.get("ZARQ_PG_DSN") or _default_write_dsn()

def _get_pg_conn():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                import psycopg2.pool
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2, maxconn=10, dsn=PG_DSN
                )
    return _pool.getconn()

def _put_pg_conn(conn):
    if _pool and conn:
        try:
            _pool.putconn(conn)
        except Exception:
            pass


def _record_failure(table, op, error_msg, pg_sql, row_count=None):
    """Log to file AND best-effort INSERT into zarq.dual_write_failures.

    The PG insert opens a fresh short-lived connection (not from the pool),
    so it works even when the pool's connections are in an aborted state.
    Silently swallows secondary failures — file log is the floor.
    """
    _log.error("%s %s%s | %s | %s",
               op, table,
               f" ({row_count} rows)" if row_count is not None else "",
               error_msg, (pg_sql or "")[:200])
    try:
        import psycopg2
        with psycopg2.connect(PG_DSN) as fconn:
            with fconn.cursor() as fcur:
                fcur.execute(
                    "INSERT INTO zarq.dual_write_failures "
                    "(table_name, op, row_count, error_msg, sql_excerpt) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (table, op, row_count, str(error_msg)[:2000],
                     (pg_sql or "")[:300])
                )
    except Exception:
        # PG genuinely unreachable; file log already has it.
        pass


# ── Table metadata ───────────────────────────────────────────
# Primary key columns per Tier A table (from zarq-tier-a-postgres.sql)
PK_MAP = {
    "nerq_risk_signals":      ("token_id", "signal_date"),
    "crypto_ndd_alerts":      ("id",),
    "crypto_price_history":   ("token_id", "date"),
    "external_trust_signals": ("agent_name", "source", "signal_name"),
    "compatibility_matrix":   ("agent_a", "agent_b", "compatibility_type"),
    "chain_dex_volumes":      ("chain",),
    "crypto_pipeline_runs":   ("id",),
    "agent_dashboard":        ("agent_name",),
    "crypto_ndd_daily":       ("id",),
    "crypto_rating_daily":    ("id",),
    "vitality_scores":        ("token_id",),
    "defi_yields":            ("pool_id",),
}

# Tables with autoincrement id — use DO NOTHING on conflict
# external_trust_signals uses composite unique (agent_name, source, signal_name)
# and wants UPDATE-on-conflict semantics, so it is NOT in this set.
_AUTOINCREMENT = {"crypto_ndd_alerts",
                  "crypto_pipeline_runs", "crypto_ndd_daily", "crypto_rating_daily"}

# Tables that are Tier A (only mirror these)
TIER_A_TABLES = set(PK_MAP.keys())

# ── SQL translation ──────────────────────────────────────────
_RE_INSERT_OR_REPLACE = re.compile(
    r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)
_RE_INSERT = re.compile(
    r"INSERT\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)
_RE_NAMED_PARAM = re.compile(r":(\w+)")
_RE_DELETE = re.compile(
    r"DELETE\s+FROM\s+(\w+)",
    re.IGNORECASE,
)


def _translate_sql(sql, named_params=False):
    """Translate SQLite SQL to PostgreSQL zarq.* equivalent.

    Returns (pg_sql, table_name) or (None, None) if not translatable.
    If named_params=True, converts :name → %(name)s instead of ? → %s.
    """
    sql_stripped = sql.strip()

    # DELETE FROM table
    m = _RE_DELETE.match(sql_stripped)
    if m:
        table = m.group(1)
        if table not in TIER_A_TABLES:
            return None, None
        pg_sql = sql_stripped.replace(table, f"zarq.{table}", 1)
        pg_sql = pg_sql.replace("?", "%s")
        return pg_sql, table

    # INSERT OR REPLACE INTO table (cols) VALUES (?)
    m = _RE_INSERT_OR_REPLACE.search(sql_stripped)
    if m:
        table = m.group(1)
        if table not in TIER_A_TABLES:
            return None, None
        cols_str = m.group(2)
        vals_str = m.group(3)
        cols = [c.strip() for c in cols_str.split(",")]
        pk_cols = PK_MAP.get(table, ())

        # Build ON CONFLICT clause
        if table in _AUTOINCREMENT:
            conflict = f"ON CONFLICT ({', '.join(pk_cols)}) DO NOTHING"
        else:
            update_cols = [c for c in cols if c not in pk_cols]
            if update_cols:
                sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
                conflict = f"ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET {sets}"
            else:
                conflict = f"ON CONFLICT ({', '.join(pk_cols)}) DO NOTHING"

        if named_params:
            pg_vals = re.sub(r":(\w+)", r"%(\1)s", vals_str)
        else:
            pg_vals = vals_str.replace("?", "%s")
        pg_sql = f"INSERT INTO zarq.{table} ({cols_str}) VALUES ({pg_vals}) {conflict}"
        return pg_sql, table

    # INSERT INTO table (...) VALUES (...) ON CONFLICT ... (already has conflict)
    if re.search(r"ON\s+CONFLICT", sql_stripped, re.IGNORECASE):
        m2 = re.search(r"INSERT\s+INTO\s+(\w+)", sql_stripped, re.IGNORECASE)
        if m2:
            table = m2.group(1)
            if table not in TIER_A_TABLES:
                return None, None
            pg_sql = re.sub(r"\b" + table + r"\b", f"zarq.{table}",
                            sql_stripped, count=1)
            pg_sql = pg_sql.replace("?", "%s")
            # Postgres uses EXCLUDED (uppercase ok), same as SQLite's excluded
            return pg_sql, table

    # Plain INSERT INTO table (cols) VALUES (?)
    m = _RE_INSERT.search(sql_stripped)
    if m:
        table = m.group(1)
        if table not in TIER_A_TABLES:
            return None, None
        cols_str = m.group(2)
        vals_str = m.group(3)
        pk_cols = PK_MAP.get(table, ())

        if table in _AUTOINCREMENT and pk_cols:
            conflict = f"ON CONFLICT ({', '.join(pk_cols)}) DO NOTHING"
        elif pk_cols:
            cols = [c.strip() for c in cols_str.split(",")]
            update_cols = [c for c in cols if c not in pk_cols]
            if update_cols:
                sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
                conflict = f"ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET {sets}"
            else:
                conflict = f"ON CONFLICT ({', '.join(pk_cols)}) DO NOTHING"
        else:
            conflict = ""

        pg_vals = vals_str.replace("?", "%s")
        pg_sql = f"INSERT INTO zarq.{table} ({cols_str}) VALUES ({pg_vals})"
        if conflict:
            pg_sql += f" {conflict}"
        return pg_sql, table

    return None, None


# ── Public API ───────────────────────────────────────────────

def dual_execute(sqlite_conn, sql, params=None):
    """Execute SQL against SQLite, then mirror to Postgres.

    SQLite execute runs first and raises normally on error.
    Postgres errors are logged but never raised.
    """
    # 1. SQLite — always runs
    sqlite_conn.execute(sql, params or ())

    # 2. Postgres mirror
    if not _ENABLED:
        return
    _setup_logging()

    pg_sql, table = _translate_sql(sql)
    if pg_sql is None:
        return

    pg_conn = None
    try:
        pg_conn = _get_pg_conn()
        cur = pg_conn.cursor()
        cur.execute(pg_sql, params or ())
        pg_conn.commit()
        cur.close()
    except Exception as e:
        _record_failure(table, "EXECUTE", e, pg_sql)
        if pg_conn:
            try:
                pg_conn.rollback()
            except Exception:
                pass
    finally:
        _put_pg_conn(pg_conn)


def dual_executemany(sqlite_conn, sql, rows):
    """Execute SQL with many rows against SQLite, then mirror to Postgres.

    SQLite executemany runs first and raises normally on error.
    Postgres errors are logged but never raised.
    """
    # 1. SQLite — always runs
    sqlite_conn.executemany(sql, rows)

    # 2. Postgres mirror
    if not _ENABLED:
        return
    _setup_logging()

    pg_sql, table = _translate_sql(sql)
    if pg_sql is None:
        return

    pg_conn = None
    try:
        pg_conn = _get_pg_conn()
        cur = pg_conn.cursor()
        # psycopg2 doesn't have executemany with good perf; use execute_batch
        import psycopg2.extras
        psycopg2.extras.execute_batch(cur, pg_sql, rows, page_size=500)
        pg_conn.commit()
        cur.close()
    except Exception as e:
        _record_failure(table, "EXECUTEMANY", e, pg_sql, row_count=len(rows))
        if pg_conn:
            try:
                pg_conn.rollback()
            except Exception:
                pass
    finally:
        _put_pg_conn(pg_conn)


def dual_executemany_named(sqlite_conn, sql, rows):
    """Like dual_executemany but for SQL with :name style params and dict rows."""
    # 1. SQLite
    sqlite_conn.executemany(sql, rows)

    # 2. Postgres mirror
    if not _ENABLED:
        return
    _setup_logging()

    pg_sql, table = _translate_sql(sql, named_params=True)
    if pg_sql is None:
        return

    pg_conn = None
    try:
        pg_conn = _get_pg_conn()
        cur = pg_conn.cursor()
        import psycopg2.extras
        psycopg2.extras.execute_batch(cur, pg_sql, rows, page_size=500)
        pg_conn.commit()
        cur.close()
    except Exception as e:
        _record_failure(table, "EXECUTEMANY_NAMED", e, pg_sql, row_count=len(rows))
        if pg_conn:
            try:
                pg_conn.rollback()
            except Exception:
                pass
    finally:
        _put_pg_conn(pg_conn)


def dual_delete(sqlite_conn, sql, params=None):
    """Execute DELETE against SQLite, then mirror to Postgres."""
    # 1. SQLite
    sqlite_conn.execute(sql, params or ())

    # 2. Postgres mirror
    if not _ENABLED:
        return
    _setup_logging()

    pg_sql, table = _translate_sql(sql)
    if pg_sql is None:
        return

    pg_conn = None
    try:
        pg_conn = _get_pg_conn()
        cur = pg_conn.cursor()
        cur.execute(pg_sql, params or ())
        pg_conn.commit()
        cur.close()
    except Exception as e:
        _record_failure(table, "DELETE", e, pg_sql)
        if pg_conn:
            try:
                pg_conn.rollback()
            except Exception:
                pass
    finally:
        _put_pg_conn(pg_conn)


def is_enabled():
    """Check if dual-write is active."""
    return _ENABLED


def reload_flag():
    """Re-read the environment variable (e.g. after os.environ change)."""
    global _ENABLED
    _ENABLED = os.environ.get("ZARQ_DUAL_WRITE") == "1"
