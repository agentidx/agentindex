"""
Smedjan data-source abstraction.

Every script that touches a database goes through one of these helpers.
Hardcoded DSNs in downstream code are a bug.

    get_smedjan_db()       — writes to the smedjan DB (on smedjan.nbg1 via
                             Tailscale from Mac Studio, or localhost on the
                             smedjan host itself, depending on config.toml)
    get_nerq_readonly()    — reads against the Nerq replica — local on Mac
                             Studio, anderss-mac-studio via Tailscale from
                             smedjan. When Nerq migrates off Mac Studio,
                             only config.toml changes.
    get_analytics_mirror() — reads analytics_mirror.* — lives in the same
                             physical DB as smedjan.*, so it is a cheap
                             cross-schema join away.

Errors from unreachable sources are raised as `SourceUnavailable`; callers
catch that and mark their task blocked instead of crashing the worker
(see M13 resilience).
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

import psycopg2
import psycopg2.extras

from smedjan import config

log = logging.getLogger("smedjan.sources")


class SourceUnavailable(RuntimeError):
    """Raised when a configured source cannot be reached."""


def _connect(dsn: str | None, name: str):
    if not dsn:
        raise SourceUnavailable(f"{name}: no DSN configured (check config.toml)")
    try:
        return psycopg2.connect(dsn, connect_timeout=10)
    except psycopg2.OperationalError as e:
        raise SourceUnavailable(f"{name}: {e}") from e


def get_smedjan_db():
    """Read/write Postgres connection to the smedjan DB."""
    return _connect(config.SMEDJAN_DB_DSN, "smedjan_db")


def get_nerq_readonly():
    """Read-only Postgres connection to the Nerq source.

    The returned connection is set to `default_transaction_read_only = on`
    so a buggy write attempt fails fast rather than silently succeeding
    in some future host-swap edge case.
    """
    conn = _connect(config.NERQ_RO_DSN, "nerq_readonly_source")
    with conn.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
    return conn


def get_analytics_mirror():
    """Read-only-ish connection into the analytics_mirror schema of the
    smedjan DB. Sets search_path so unqualified references resolve against
    analytics_mirror first, falling back to smedjan then public.
    """
    conn = _connect(config.ANALYTICS_MIRROR_DSN, "analytics_mirror")
    with conn.cursor() as cur:
        cur.execute(
            "SET search_path = %s, smedjan, public",
            (config.ANALYTICS_MIRROR_SCHEMA,),
        )
    return conn


@contextmanager
def smedjan_db_cursor(dict_cursor: bool = False) -> Iterator:
    """Yield a (connection, cursor) pair. Commits on clean exit."""
    conn = get_smedjan_db()
    try:
        kwargs = {"cursor_factory": psycopg2.extras.RealDictCursor} if dict_cursor else {}
        with conn.cursor(**kwargs) as cur:
            yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def nerq_readonly_cursor(dict_cursor: bool = False) -> Iterator:
    conn = get_nerq_readonly()
    try:
        kwargs = {"cursor_factory": psycopg2.extras.RealDictCursor} if dict_cursor else {}
        with conn.cursor(**kwargs) as cur:
            yield conn, cur
    finally:
        conn.close()


@contextmanager
def analytics_mirror_cursor(dict_cursor: bool = False) -> Iterator:
    conn = get_analytics_mirror()
    try:
        kwargs = {"cursor_factory": psycopg2.extras.RealDictCursor} if dict_cursor else {}
        with conn.cursor(**kwargs) as cur:
            yield conn, cur
    finally:
        conn.close()


def mirror_freshness_hours() -> float | None:
    """How many hours old is the analytics_mirror data? None if unreadable.
    Used by M13 resilience checks — mirror older than 48h triggers alert.
    """
    try:
        with analytics_mirror_cursor() as (_, cur):
            cur.execute(
                "SELECT EXTRACT(EPOCH FROM (now() - min(synced_at))) / 3600.0 "
                "FROM analytics_mirror._sync_state"
            )
            row = cur.fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except SourceUnavailable:
        return None
