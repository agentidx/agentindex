"""Deprecation-logger middleware.

Records every request that matches one of a configured set of path prefixes
into `zarq.endpoint_usage_audit`. Used to gather 14 days of usage data on
routes flagged as deprecation candidates (per Anders' F.1-F.3 answers in
phase-3 root-cause plan): `/crypto/*` (legacy crypto_api.py),
`/experiments/*` (orphaned experiments_api.py module), and `/action/*`
(admin moderation endpoints from dashboard.py).

Design constraints:

1. **Non-blocking audit writes.** The middleware never delays the response.
   It captures the request data inline (path, method, headers, IP) and
   schedules the PG insert via `asyncio.create_task` so the user request
   completes before the audit row hits disk.

2. **Loud errors, no swallowing.** Audit-write failures are logged at
   ERROR level (not silently dropped). Production traffic continues even
   if the audit DB is down — the request response is never affected.

3. **Sync psycopg2 in a thread pool.** Audit writes use the existing
   sync DSN via `loop.run_in_executor` so we don't add asyncpg as a
   dependency. The thread-pool insert is ~5-15ms; acceptable for
   low-volume deprecated endpoints.

4. **Prefixes configured at mount time.** Middleware takes a list of
   prefixes. Non-matching paths bypass the middleware with zero overhead.

Example mount in `agentindex/api/discovery.py`:

    from agentindex.api.middleware.deprecation_logger import DeprecationLoggerMiddleware
    app.add_middleware(
        DeprecationLoggerMiddleware,
        prefixes=("/crypto/", "/experiments/", "/action/"),
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Iterable

import psycopg2

# db_config registers the numpy adapters globally; safe to import here.
from agentindex import db_config

log = logging.getLogger("deprecation_logger")


def _resolve_dsn() -> str:
    """psycopg2-format DSN for the audit destination.

    Override with ZARQ_AUDIT_DSN env var (useful for tests). Falls back to
    `db_config.get_write_dsn(fmt="psycopg2")` so audit writes go through
    PgBouncer's agentindex_write pool — same path the rest of the app uses.
    """
    return os.environ.get("ZARQ_AUDIT_DSN") or db_config.get_write_dsn(fmt="psycopg2")


def _scope_header(scope: dict, name: str) -> str | None:
    name_bytes = name.lower().encode("latin-1")
    for k, v in scope.get("headers", []) or []:
        if k.lower() == name_bytes:
            try:
                return v.decode("latin-1")
            except UnicodeDecodeError:
                return None
    return None


def _client_ip(scope: dict) -> str | None:
    # X-Forwarded-For wins when behind Cloudflare/proxy.
    xff = _scope_header(scope, "x-forwarded-for")
    if xff:
        # First entry is the original client.
        return xff.split(",", 1)[0].strip()
    real = _scope_header(scope, "x-real-ip")
    if real:
        return real
    client = scope.get("client")
    if client and isinstance(client, (list, tuple)) and client:
        return client[0]
    return None


def _insert_sync(dsn: str, row: tuple) -> None:
    """Open a short-lived connection and insert one audit row.

    Lives outside the class so the thread-pool executor doesn't need to
    serialize `self`. Loud on failure — caller logs.
    """
    with psycopg2.connect(dsn, connect_timeout=4) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO zarq.endpoint_usage_audit
                    (endpoint, method, user_agent, client_ip,
                     response_status, response_time_ms)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                row,
            )


class DeprecationLoggerMiddleware:
    """ASGI middleware that audits requests matching configured prefixes.

    Attach via `app.add_middleware(DeprecationLoggerMiddleware,
    prefixes=("/crypto/", "/experiments/", "/action/"))`.
    """

    def __init__(self, app, prefixes: Iterable[str] = ()):
        self.app = app
        # Normalize: ensure trailing slash so /crypto matches but /crypto-old doesn't.
        self.prefixes = tuple(p if p.endswith("/") else p + "/" for p in prefixes)
        self.dsn = _resolve_dsn()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        # Match path against prefixes; check both `/crypto/foo` (prefix /crypto/)
        # and the bare `/crypto` (without trailing slash).
        bare_match = any(path + "/" == p or path == p[:-1] for p in self.prefixes)
        prefix_match = any(path.startswith(p) for p in self.prefixes)
        if not (bare_match or prefix_match):
            await self.app(scope, receive, send)
            return

        # Capture data inline.
        method = scope.get("method", "GET")
        user_agent = _scope_header(scope, "user-agent")
        client_ip = _client_ip(scope)
        start = time.monotonic()
        status_holder: list[int | None] = [None]

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder[0] = message.get("status")
            await send(message)

        await self.app(scope, receive, send_wrapper)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        row = (path, method, user_agent, client_ip, status_holder[0], elapsed_ms)

        # Schedule non-blocking audit insert.
        asyncio.create_task(self._audit(row))

    async def _audit(self, row: tuple) -> None:
        """Run the sync insert off-loop. Loud on failure; never raises."""
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _insert_sync, self.dsn, row)
        except Exception as exc:
            # Loud: log full error. Production traffic must not be affected
            # by a failing audit write — we swallow here on purpose so the
            # asyncio task doesn't surface an unhandled exception.
            log.error(
                "deprecation_logger audit insert failed: %s | row=%r",
                exc,
                row,
            )
