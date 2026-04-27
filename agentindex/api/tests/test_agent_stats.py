"""Integration tests for GET /v1/agent/stats.

Background
----------
AUDIT-QUERY-20260427 finding 5 reported the endpoint had been 100% 5xx for
14 consecutive days (47 hits, 28 humans hit 503). FU-QUERY-20260418-07
shipped a fix on smedjan-factory-v0 that

  * isolates the slow language GROUP BY in a SAVEPOINT with its own
    statement_timeout (so a timeout there no longer aborts the outer txn),
    and
  * adds a stale-while-error fallback on the outer handler so a fresh DB
    failure serves the last good payload instead of a hard 503.

These tests pin both behaviours so a future refactor that re-collapses
the savepoint (or removes the stale-while-error branch) trips CI rather
than silently re-regressing in production.

They are *integration* tests in the sense that the route is exercised
through FastAPI's TestClient against the real router. The DB itself is
substituted by patching ``agentindex.nerq_api.get_session`` to a fake
session — keeps the test hermetic and runnable without Postgres in CI,
while still going through the full FastAPI request pipeline (router,
response, JSON encoding, headers).
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Fixtures ────────────────────────────────────────────────


REQUIRED_FIELDS = (
    "total_assets",
    "total_agents",
    "total_tools",
    "total_mcp_servers",
    "total_models",
    "total_datasets",
    "total_spaces",
    "categories",
    "frameworks",
    "languages",
    "trust_distribution",
    "new_24h",
    "new_7d",
    "updated_at",
)


@pytest.fixture
def fresh_router():
    """Reload the nerq_api module so module-level caches start empty.

    The endpoint memoizes its payload in ``_stats_cache`` for an hour, so
    test isolation requires a clean slate.
    """
    import importlib

    import agentindex.nerq_api as nerq_api

    importlib.reload(nerq_api)
    yield nerq_api
    # Clear cache on the way out so subsequent test files start clean.
    nerq_api._stats_cache["data"] = None
    nerq_api._stats_cache["ts"] = 0


def _build_client(nerq_api) -> TestClient:
    app = FastAPI()
    app.include_router(nerq_api.router_nerq)
    return TestClient(app, raise_server_exceptions=False)


class _FakeRow(tuple):
    """Tuple that also supports ``.scalar()``-style first-element access."""


class _FakeResult:
    """Stand-in for SQLAlchemy ``Result`` that supports the methods agent_stats uses."""

    def __init__(self, rows: list[Any] | None = None, scalar_value: Any = 0):
        self._rows = rows or []
        self._scalar = scalar_value

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._scalar


class FakeSession:
    """Minimal SQLAlchemy session double — ``execute`` is dispatched by SQL substring.

    ``responses`` is an ordered list of ``(needle, factory)`` pairs; the
    first needle that appears in the SQL text wins. ``factory`` is either
    a ``_FakeResult`` or a callable returning one (or raising). This lets
    a single test patch one specific sub-query while letting the rest
    succeed.
    """

    def __init__(self, responses: list[tuple[str, Any]]):
        self.responses = responses
        self.calls: list[str] = []

    def execute(self, sql, params=None):
        sql_text = str(sql)
        self.calls.append(sql_text)
        for needle, factory in self.responses:
            if needle in sql_text:
                if callable(factory):
                    result = factory()
                else:
                    result = factory
                if isinstance(result, Exception):
                    raise result
                return result
        return _FakeResult([])

    @contextmanager
    def begin_nested(self):
        # Mirror SQLAlchemy's nested-transaction context: on exception the
        # block is rolled back but the outer txn keeps going. agent_stats
        # relies on this for the language-query SAVEPOINT.
        try:
            yield self
        except Exception:
            raise

    def rollback(self):
        pass

    def close(self):
        pass


def _happy_responses() -> list[tuple[str, Any]]:
    """Canned successful results for every sub-query agent_stats issues."""

    combined_row = (
        100,    # agents
        50,     # tools
        25,     # mcp_servers
        4_000_000,  # models
        700_000,    # datasets
        10_000,     # spaces
        60,     # trusted
        30,     # caution
        10,     # untrusted
        72.5,   # avg_trust
    )
    return [
        ("pg_class", _FakeResult(scalar_value=4_900_000)),
        ("SUM(CASE WHEN agent_type", _FakeResult(rows=[combined_row])),
        ("GROUP BY cat", _FakeResult(rows=[("agent-framework", 25), ("dev-tool", 18)])),
        ("unnest(frameworks)", _FakeResult(rows=[("langchain", 40), ("crewai", 12)])),
        ("SET LOCAL work_mem", _FakeResult()),
        ("SET LOCAL statement_timeout", _FakeResult()),
        ("GROUP BY lang", _FakeResult(rows=[("Python", 80), ("TypeScript", 30)])),
        ("TABLESAMPLE SYSTEM(0.1)", _FakeResult(scalar_value=2)),
        ("TABLESAMPLE SYSTEM(1)", _FakeResult(scalar_value=15)),
    ]


# ── Tests ───────────────────────────────────────────────────


class TestAgentStatsHappyPath:
    """Endpoint must return 200 with the documented schema. Pins the
    primary regression: 100% 5xx caught by AUDIT-QUERY-20260427 #5."""

    def test_returns_200_not_503(self, fresh_router):
        session = FakeSession(_happy_responses())
        with patch.object(fresh_router, "get_session", return_value=session):
            client = _build_client(fresh_router)
            r = client.get("/v1/agent/stats")
        assert r.status_code == 200, f"endpoint regressed to {r.status_code}: {r.text[:300]}"

    def test_response_has_all_required_fields(self, fresh_router):
        session = FakeSession(_happy_responses())
        with patch.object(fresh_router, "get_session", return_value=session):
            client = _build_client(fresh_router)
            data = client.get("/v1/agent/stats").json()
        for field in REQUIRED_FIELDS:
            assert field in data, f"missing required field: {field}"
        assert isinstance(data["categories"], dict)
        assert isinstance(data["frameworks"], dict)
        assert isinstance(data["languages"], dict)
        assert set(data["trust_distribution"]) == {"TRUSTED", "CAUTION", "UNTRUSTED"}

    def test_second_call_is_cache_hit(self, fresh_router):
        session = FakeSession(_happy_responses())
        with patch.object(fresh_router, "get_session", return_value=session):
            client = _build_client(fresh_router)
            r1 = client.get("/v1/agent/stats")
            r2 = client.get("/v1/agent/stats")
        assert r1.headers.get("X-Cache") == "MISS"
        assert r2.headers.get("X-Cache") == "HIT"


class TestAgentStatsResilience:
    """Pins FU-QUERY-20260418-07: a single bad sub-query must not nuke
    the whole endpoint, and a fully bad request must serve stale rather
    than 503 if a prior good payload exists."""

    def test_language_query_timeout_does_not_503(self, fresh_router):
        """The original regression: agents.language GROUP BY hit
        statement_timeout, the outer try/except converted that into a
        hard 503, and 100% of human visitors saw an error."""
        from sqlalchemy.exc import OperationalError

        responses = _happy_responses()
        # Replace the GROUP BY lang factory with one that raises like a
        # Postgres "canceling statement due to statement timeout" would.
        for i, (needle, _) in enumerate(responses):
            if needle == "GROUP BY lang":
                responses[i] = (
                    needle,
                    lambda: (_ for _ in ()).throw(
                        OperationalError("SELECT", {}, Exception("statement timeout"))
                    ),
                )
                break
        session = FakeSession(responses)

        with patch.object(fresh_router, "get_session", return_value=session):
            client = _build_client(fresh_router)
            r = client.get("/v1/agent/stats")

        assert r.status_code == 200, (
            "endpoint regressed: a single failing sub-query produced "
            f"{r.status_code} again. Re-check the language-query SAVEPOINT."
        )
        body = r.json()
        # Languages should be empty (no prior cache to fall back to)
        assert body["languages"] == {}, body["languages"]
        # …but every other field must still be populated.
        for field in REQUIRED_FIELDS:
            assert field in body
        assert body["total_agents"] == 100
        assert body["frameworks"]  # non-empty

    def test_stale_while_error_serves_cached_payload(self, fresh_router):
        """When the *whole* request blows up, return the last-known-good
        payload with X-Cache=STALE rather than 503."""
        # Prime the cache with a good response.
        good_session = FakeSession(_happy_responses())
        with patch.object(fresh_router, "get_session", return_value=good_session):
            client = _build_client(fresh_router)
            r = client.get("/v1/agent/stats")
            assert r.status_code == 200
            assert r.headers.get("X-Cache") == "MISS"

        # Force-expire the cache so the next request actually hits the DB.
        fresh_router._stats_cache["ts"] = 0

        # Next request: blow up on the very first sub-query.
        bad_responses: list[tuple[str, Any]] = [
            ("pg_class", lambda: (_ for _ in ()).throw(RuntimeError("DB down"))),
        ]
        bad_session = FakeSession(bad_responses)
        with patch.object(fresh_router, "get_session", return_value=bad_session):
            r = client.get("/v1/agent/stats")

        assert r.status_code == 200, (
            "stale-while-error fallback regressed: a fresh DB failure with "
            "a cached payload available should serve the cache, not 503."
        )
        assert r.headers.get("X-Cache") == "STALE"
        # Critical fields from the primed payload should still be present.
        body = r.json()
        for field in REQUIRED_FIELDS:
            assert field in body

    def test_no_cache_no_db_returns_503(self, fresh_router):
        """Conversely, if there's no cache *and* the DB is down, the
        endpoint still has to fail loudly so monitoring sees it. The
        per-endpoint pct5xx alert (smedjan/scripts/check_endpoint_pct5xx_1h.py)
        relies on this signal."""
        bad_responses: list[tuple[str, Any]] = [
            ("pg_class", lambda: (_ for _ in ()).throw(RuntimeError("DB down"))),
        ]
        session = FakeSession(bad_responses)
        with patch.object(fresh_router, "get_session", return_value=session):
            client = _build_client(fresh_router)
            r = client.get("/v1/agent/stats")
        assert r.status_code == 503
        assert r.json() == {"error": "Database unavailable"}
