"""Shared fixtures + helpers for the ZARQ surface test suite.

The suite is intentionally data-driven: routes are *discovered* by grepping
the codebase at session start (route_discovery.py) rather than maintained as
a static list. That keeps the suite from drifting away from the code.

Two targets are tested per session, parameterized at the test level:
  - localhost   : direct hit at http://localhost:8000 / :8001
  - production  : through Cloudflare at https://zarq.ai / https://mcp.zarq.ai

Failures are written to docs/status/zarq_test_failures_20260530/<test-id>.txt
by the pytest_runtest_makereport hook below, so each failure has a raw
artifact even after the run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator

import httpx
import pytest


# ─── Paths and constants ───────────────────────────────────────────────────
REPO_ROOT = Path("/Users/anstudio/agentindex")
SUITE_DIR = REPO_ROOT / "tests" / "zarq_surface"
FAILURES_DIR = REPO_ROOT / "docs" / "status" / "zarq_test_failures_20260530"
FAILURES_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_TIMEOUT_S = 8.0     # Per the spec: 8s ceiling. Beyond → TIMEOUT.
SLOW_THRESHOLD_S = 2.0      # Sorted separately in the final report.

PRODUCTION_BASE = "https://zarq.ai"
PRODUCTION_API_BASE = "https://api.zarq.ai"
PRODUCTION_MCP_BASE = "https://mcp.zarq.ai"

LOCAL_BASE = "http://localhost:8000"
LOCAL_MCP_BASE = "http://localhost:8001"


# ─── Failure classification ─────────────────────────────────────────────────
class FailureCategory:
    HTTP_5XX             = "HTTP_5XX"
    HTTP_4XX_UNEXPECTED  = "HTTP_4XX_unexpected"
    TIMEOUT              = "TIMEOUT"
    EMPTY_RESPONSE       = "EMPTY_RESPONSE"
    STALE_DATA           = "STALE_DATA"
    PARSE_ERROR          = "PARSE_ERROR"
    EXCEPTION_IN_BODY    = "EXCEPTION_IN_BODY"
    DB_TABLE_MISSING     = "DB_TABLE_MISSING"
    DB_COLUMN_MISSING    = "DB_COLUMN_MISSING"
    CACHE_NOT_BUILT      = "CACHE_NOT_BUILT"
    WRITE_FAILED         = "WRITE_FAILED"
    CLOUDFLARED_GAP      = "CLOUDFLARED_GAP"
    SKIP_FLAKY           = "SKIP_FLAKY"          # opt-in skip; documented
    NETWORK_ERROR        = "NETWORK_ERROR"       # DNS, conn refused, TLS


@dataclass
class FailureRecord:
    test_id: str
    target: str
    category: str
    detail: str
    method: str = ""
    path: str = ""
    status_code: int | None = None
    elapsed_ms: float = 0.0
    body_excerpt: str = ""
    pg_pool: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# In-memory accumulator. Written to JSON in pytest_sessionfinish.
_FAILURES: list[FailureRecord] = []
_PASSES: list[dict] = []      # tracks elapsed for performance reporting
_SKIPS:  list[dict] = []


def record_failure(rec: FailureRecord) -> None:
    _FAILURES.append(rec)
    # Also persist raw response per spec section E.
    txt_path = FAILURES_DIR / f"{rec.test_id.replace('/', '_')}.txt"
    with txt_path.open("w") as fh:
        fh.write(f"# Test: {rec.test_id}\n")
        fh.write(f"# Target: {rec.target}\n")
        fh.write(f"# Category: {rec.category}\n")
        fh.write(f"# {rec.method} {rec.path}\n")
        fh.write(f"# status={rec.status_code} elapsed={rec.elapsed_ms:.1f}ms pool={rec.pg_pool}\n")
        fh.write(f"# detail: {rec.detail}\n")
        fh.write(f"\n--- response excerpt ---\n")
        fh.write(rec.body_excerpt)


def record_pass(test_id: str, target: str, elapsed_ms: float, path: str = "") -> None:
    _PASSES.append({"test_id": test_id, "target": target, "elapsed_ms": elapsed_ms, "path": path})


def record_skip(test_id: str, target: str, reason: str) -> None:
    _SKIPS.append({"test_id": test_id, "target": target, "reason": reason})


# ─── Target parametrization ────────────────────────────────────────────────
TARGETS = ("localhost", "production")


@pytest.fixture(params=TARGETS, ids=TARGETS)
def target(request) -> str:
    """The current test target — either `localhost` or `production`."""
    return request.param


@pytest.fixture
def base_url(target: str) -> str:
    return LOCAL_BASE if target == "localhost" else PRODUCTION_BASE


@pytest.fixture
def api_base_url(target: str) -> str:
    """Use api.zarq.ai for production (some routes use the API subdomain)."""
    return LOCAL_BASE if target == "localhost" else PRODUCTION_API_BASE


@pytest.fixture
def mcp_base_url(target: str) -> str:
    return LOCAL_MCP_BASE if target == "localhost" else PRODUCTION_MCP_BASE


@pytest.fixture(scope="session")
def http_client() -> Iterator[httpx.Client]:
    """A reusable httpx.Client. follow_redirects=True so we exercise the real
    landing-page flow (zarq.ai/ may redirect to /crypto)."""
    with httpx.Client(
        timeout=REQUEST_TIMEOUT_S,
        follow_redirects=True,
        headers={"User-Agent": "zarq-surface-tests/1.0 (suite=tests/zarq_surface)"},
        verify=True,
    ) as client:
        yield client


# ─── Synthetic input set ───────────────────────────────────────────────────
@pytest.fixture(scope="session")
def synthetic_inputs() -> dict:
    """Synthetic substitutions for path-parameterized routes. The 4 token IDs
    were chosen to span SAFE / WARNING / unknown-but-listed: bitcoin and
    ethereum should always be present in zarq.crypto_rating_daily; siren is
    a known-distressed entry (per the 2026-05-29 NDD output); nonexist-1
    deliberately doesn't exist, so a well-behaved endpoint returns a clean
    404 with an explanatory body rather than a 500."""
    fixtures_path = SUITE_DIR / "fixtures" / "synthetic_requests.json"
    if fixtures_path.exists():
        with fixtures_path.open() as fh:
            return json.load(fh)
    # Defaults (also written to the JSON for transparency)
    return {
        "tokens": ["bitcoin", "ethereum"],
        "distressed_token": "siren",
        "missing_token": "nonexist-token-xyz",
        "agents": ["autogpt", "crewai"],
        "categories": ["vpn", "npm", "password_manager"],
    }


# ─── DB connection (Nbg primary; read-only fixtures) ───────────────────────
@pytest.fixture(scope="session")
def pg_conn():
    """Read-only psycopg2 connection to Nbg primary. Used by freshness tests.

    No application code or schemas are touched; queries are SELECTs only.
    The connection is opened once per session and shared.
    """
    import psycopg2
    dsn = os.environ.get(
        "ZARQ_TEST_PG_DSN",
        "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio",
    )
    try:
        conn = psycopg2.connect(dsn, connect_timeout=4)
        conn.autocommit = True
    except Exception as e:
        pytest.skip(f"Nbg PG not reachable: {e}")
    yield conn
    conn.close()


# ─── Per-table freshness thresholds ────────────────────────────────────────
@pytest.fixture(scope="session")
def freshness_thresholds() -> dict:
    """Map zarq.<table> -> (timestamp_column, max_age_hours).

    Calibrated to the actual pipeline cadence: NDD runs daily ~04:00,
    risk_signals same, price_history backfills 2 days each run. A value of
    None means "no automated freshness check" (table is reference data).
    """
    return {
        "crypto_ndd_daily":       ("run_date::timestamp",                  36),
        "crypto_ndd_alerts":      ("alert_date::timestamp",                36),
        "nerq_risk_signals":      ("signal_date::timestamp",               36),
        "crypto_price_history":   ("date::timestamp",                      36),
        "crypto_rating_daily":    ("run_date::timestamp",                  36),
        "crypto_pipeline_runs":   ("started_at::timestamp",                36),
        "external_trust_signals": ("fetched_at",                           72),
        "vitality_scores":        (None,                                   None),   # reference
        "defi_yields":            (None,                                   None),
        "chain_dex_volumes":      (None,                                   None),
        "agent_dashboard":        (None,                                   None),
        "compatibility_matrix":   (None,                                   None),
        "infrastructure_alerts":  ("last_seen_at",                         24),     # we set this up today
        "dual_write_failures":    (None,                                   None),   # OK if empty
    }


# ─── Known-stale agents (for STALE_DATA suppression) ───────────────────────
@pytest.fixture(scope="session")
def known_stale_agent_tables() -> dict:
    """Tables whose dead-or-broken LaunchAgents already know-about. Stale-data
    failures touching these get tagged `known_caused_by_dead_agent` so phase 3
    can root-cause to the agent fix, not the endpoint.

    Per ZARQ inventory section A.7 (commit e19437b):
      com.nerq.zarq-cache      (exit=2) — /tmp/zarq_dashboard_cache.json
      com.nerq.dashboard-data  (exit=1) — dashboard data refresh
      com.nerq.dex-volumes     (exit=1) — chain_dex_volumes
      com.nerq.stale-scores    (exit=1) — stale-score detector
      com.nerq.trust-score-v3  (exit=1) — trust score v3 recompute
    """
    return {
        "chain_dex_volumes":     "com.nerq.dex-volumes (exit=1)",
        "/tmp/zarq_dashboard_cache.json": "com.nerq.zarq-cache (exit=2)",
    }


# ─── Route discovery ────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def discovered_routes() -> list[dict]:
    """Grep ZARQ-relevant FastAPI route declarations from the live source.

    Output: list of dicts with keys file, line, method, path, decorator_object.
    Path parameters are left unresolved; tests that need concrete URLs use
    the `synthetic_inputs` substitution map.
    """
    from .route_discovery import discover_zarq_routes
    return discover_zarq_routes(REPO_ROOT / "agentindex")


# ─── Pytest hooks: failure capture + final report dump ─────────────────────
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    # The individual tests are expected to call record_failure() themselves
    # when they classify a failure. We don't double-record here; this hook is
    # only used to surface uncaught exceptions (i.e. test bugs).
    if report.failed and report.when == "call":
        # Heuristic: if no FailureRecord was added during this test, the test
        # crashed unexpectedly. Add a synthetic record so we don't lose it.
        nodeid = report.nodeid
        if not any(f.test_id == nodeid for f in _FAILURES):
            _FAILURES.append(FailureRecord(
                test_id=nodeid,
                target="unknown",
                category="EXCEPTION_IN_BODY",
                detail=f"Uncaught test exception: {str(call.excinfo)[:500]}",
            ))


def pytest_sessionfinish(session, exitstatus):
    """Persist the run summary as JSON next to the report directory."""
    summary = {
        "exit_status": int(exitstatus),
        "n_failures": len(_FAILURES),
        "n_passes": len(_PASSES),
        "n_skips": len(_SKIPS),
        "failures": [f.to_dict() for f in _FAILURES],
        "passes_slow": sorted(
            [p for p in _PASSES if p["elapsed_ms"] > SLOW_THRESHOLD_S * 1000],
            key=lambda x: -x["elapsed_ms"],
        ),
        "skips": _SKIPS,
    }
    out = REPO_ROOT / "docs" / "status" / "zarq_surface_test_run.json"
    with out.open("w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    print(f"\n[zarq_surface] wrote run summary -> {out}", file=sys.stderr)


def pytest_addoption(parser):
    parser.addoption(
        "--zarq-target",
        default=None,
        help="Override target parametrization. Pass 'localhost' or 'production' to run only one.",
    )


def pytest_generate_tests(metafunc):
    # If --zarq-target was passed, narrow the parametrization.
    override = metafunc.config.getoption("--zarq-target")
    if override and "target" in metafunc.fixturenames:
        metafunc.parametrize("target", [override], ids=[override])
