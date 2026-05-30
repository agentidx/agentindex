"""Auth-gated endpoint tests (key-gated; skipped if no test API key set).

Tests the `/internal/*` and `/zarq/dashboard*` endpoints that the default
surface suite (`test_http_endpoints.py`) skips via `_OUT_OF_SCOPE_PREFIXES`.

Key source order:
  1. `ZARQ_TEST_API_KEY` env var, if set in the running shell.
  2. `~/agentindex/secrets/.env.test` (gitignored), if present.
  3. Skip the entire module.

The whole module is skipped — not individual tests — so a missing key
doesn't produce noise in pytest output. The skip reason is explicit so
you know how to enable.

See `docs/tracking/test-api-key-isolation.md` for the current
("re-using NERQ_DASHBOARD_KEY default") vs intended ("distinct test key
with multi-key acceptance in reach_dashboard.py") state.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from . import conftest as cf


# ─── Key resolution ───────────────────────────────────────────────────────
def _load_env_var(name: str) -> str | None:
    """Look up `name` first in os.environ, then in ~/agentindex/secrets/.env.test.
    """
    val = os.environ.get(name)
    if val:
        return val
    env_path = Path("/Users/anstudio/agentindex/secrets/.env.test")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(name + "="):
                value = line.split("=", 1)[1].strip().strip("\"'")
                if value:
                    return value
    return None


_TEST_KEY = _load_env_var("ZARQ_TEST_API_KEY")
_METRICS_TOKEN = _load_env_var("ZARQ_TEST_METRICS_TOKEN")
if not _TEST_KEY:
    pytest.skip(
        "ZARQ_TEST_API_KEY not set and ~/agentindex/secrets/.env.test missing or empty. "
        "Auth tests skipped. See docs/tracking/test-api-key-isolation.md.",
        allow_module_level=True,
    )


# ─── Test cases ────────────────────────────────────────────────────────────
# (label, path, auth_scheme). Two auth schemes:
#   "internal_key"   → ?key=<NERQ_DASHBOARD_KEY>  (reach_dashboard.py)
#   "metrics_token"  → ?token=<ZARQ_METRICS_TOKEN> (zarq_dashboard.py)
AUTH_PATHS = [
    ("internal_reach_html",       "/internal/reach",       "internal_key"),
    ("internal_reach_json",       "/internal/reach.json",  "internal_key"),
    ("internal_yield_html",       "/internal/yield",       "internal_key"),
    ("zarq_dashboard_root",       "/zarq/dashboard",       "metrics_token"),
    ("zarq_dashboard_data",       "/zarq/dashboard/data",  "metrics_token"),
]


@pytest.mark.parametrize(
    "label,path,auth_scheme",
    AUTH_PATHS,
    ids=[c[0] for c in AUTH_PATHS],
)
def test_auth_endpoint_with_key(label, path, auth_scheme, target, http_client, base_url, request):
    """Auth-gated path with key should NOT return 401/403 unauthorized."""
    test_id = request.node.nodeid
    if auth_scheme == "internal_key":
        url = f"{base_url}{path}?key={_TEST_KEY}"
    elif auth_scheme == "metrics_token":
        if not _METRICS_TOKEN:
            pytest.skip(f"ZARQ_TEST_METRICS_TOKEN not configured; cannot test {path}")
        url = f"{base_url}{path}?token={_METRICS_TOKEN}"
    else:
        pytest.fail(f"unknown auth_scheme: {auth_scheme}")

    t0 = time.time()
    try:
        resp = http_client.get(url)
    except Exception as e:
        elapsed_ms = (time.time() - t0) * 1000
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.NETWORK_ERROR,
            detail=f"{type(e).__name__}: {e}",
            method="GET", path=path, elapsed_ms=elapsed_ms,
            extra={"url": url.replace(_TEST_KEY, "<redacted>")},
        ))
        pytest.fail(f"NETWORK_ERROR {label}")

    elapsed_ms = (time.time() - t0) * 1000
    body = resp.text[:1500]

    # 401/403 with the key set = either wrong key OR the gate doesn't accept it.
    # Either way it's a real failure of this test.
    if resp.status_code in (401, 403):
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target,
            category=cf.FailureCategory.HTTP_4XX_UNEXPECTED,
            detail=f"auth path {path} rejected the test key: status {resp.status_code}",
            method="GET", path=path, status_code=resp.status_code,
            elapsed_ms=elapsed_ms, body_excerpt=body,
            extra={"hint": "key may be wrong; see docs/tracking/test-api-key-isolation.md"},
        ))
        pytest.fail(f"AUTH_REJECTED {label}: status {resp.status_code}")

    if 500 <= resp.status_code < 600:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.HTTP_5XX,
            detail=f"auth path {path} 5xx: {resp.status_code}",
            method="GET", path=path, status_code=resp.status_code,
            elapsed_ms=elapsed_ms, body_excerpt=body,
        ))
        pytest.fail(f"HTTP_5XX {label}")

    if resp.status_code != 200:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.HTTP_4XX_UNEXPECTED,
            detail=f"auth path {path} unexpected status {resp.status_code}",
            method="GET", path=path, status_code=resp.status_code,
            elapsed_ms=elapsed_ms, body_excerpt=body,
        ))
        pytest.fail(f"HTTP_{resp.status_code} {label}")

    if len(body) < 100:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.EMPTY_RESPONSE,
            detail=f"auth path {path} body <100 bytes: {len(body)}",
            method="GET", path=path, status_code=resp.status_code,
            elapsed_ms=elapsed_ms, body_excerpt=body,
        ))
        pytest.fail(f"EMPTY {label}")

    cf.record_pass(test_id, target, elapsed_ms, path=path)


def test_auth_endpoint_without_key_rejects(http_client, base_url, request):
    """Sanity: without the key, /internal/reach should return 401/403, not 200."""
    test_id = request.node.nodeid
    url = f"{base_url}/internal/reach"
    resp = http_client.get(url)
    if resp.status_code == 200:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target="localhost", category=cf.FailureCategory.HTTP_4XX_UNEXPECTED,
            detail=f"/internal/reach without key returned 200 — auth gate may be open",
            method="GET", path="/internal/reach", status_code=200,
            body_excerpt=resp.text[:600],
        ))
        pytest.fail("auth_gate_open_without_key")
    assert resp.status_code in (401, 403, 404), (
        f"expected auth rejection (401/403/404) without key, got {resp.status_code}"
    )
