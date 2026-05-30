"""Cloudflared-vs-localhost diff tests.

Per the inventory section B (commit e19437b), every cloudflared hostname
should route to a listening port and that port should serve at least one
matching route. This test compares a small fixed-set of canonical endpoints
across localhost and production. Endpoints where production != localhost
get tagged `CLOUDFLARED_GAP`, isolating ingress / Cloudflare-edge issues
from app-layer issues.

This is intentionally narrower than test_http_endpoints (which already runs
against both targets). Here we look only at well-known reference URLs:
  - /health on each origin
  - the bare root on each hostname
  - one ZARQ-API canonical path
  - one MCP path
"""

from __future__ import annotations

import time

import httpx
import pytest

from . import conftest as cf


# Canonical reference points. Each tuple is (label, localhost_url, prod_url,
# expected_status). Cloudflared-gap tests don't substitute path params.
CANONICAL_REFERENCE_POINTS = [
    ("api_health",       "http://localhost:8000/health",         "https://nerq.ai/health",         200),
    ("zarq_root",        "http://localhost:8000/",               "https://zarq.ai/",               200),
    ("zarq_crypto_root", "http://localhost:8000/crypto",         "https://zarq.ai/crypto",         200),
    ("zarq_tokens",      "http://localhost:8000/tokens",         "https://zarq.ai/tokens",         200),
    ("zarq_vitality",    "http://localhost:8000/vitality",       "https://zarq.ai/vitality",       200),
    ("zarq_yield",       "http://localhost:8000/yield",          "https://zarq.ai/yield",          200),
    ("zarq_cascade",     "http://localhost:8000/cascade-risk",   "https://zarq.ai/cascade-risk",   200),
    ("mcp_health",       "http://localhost:8001/health",         "https://mcp.zarq.ai/health",     200),
    ("api_rating_btc",   "http://localhost:8000/rating/bitcoin", "https://api.zarq.ai/rating/bitcoin", 200),
]


@pytest.mark.parametrize(
    "label,local_url,prod_url,expected_status",
    CANONICAL_REFERENCE_POINTS,
    ids=[c[0] for c in CANONICAL_REFERENCE_POINTS],
)
def test_cloudflared_parity(label, local_url, prod_url, expected_status, http_client, request):
    """For each reference point, hit both origins and compare statuses."""
    test_id = request.node.nodeid

    def _probe(url):
        t0 = time.time()
        try:
            r = http_client.get(url)
            return r.status_code, r.text[:600], (time.time() - t0) * 1000, None
        except httpx.TimeoutException:
            return None, "", (time.time() - t0) * 1000, "TIMEOUT"
        except httpx.RequestError as e:
            return None, "", (time.time() - t0) * 1000, f"NETWORK: {type(e).__name__}: {e}"

    local_sc, local_body, local_ms, local_err = _probe(local_url)
    prod_sc,  prod_body,  prod_ms,  prod_err  = _probe(prod_url)

    # Construct comparison verdict
    detail = (
        f"local={local_sc or local_err} ({local_ms:.0f}ms) "
        f"prod={prod_sc or prod_err} ({prod_ms:.0f}ms)"
    )

    if local_sc == expected_status and prod_sc != expected_status:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target="diff", category=cf.FailureCategory.CLOUDFLARED_GAP,
            detail=f"local OK but prod failed; {detail}",
            method="GET", path=local_url,
            status_code=prod_sc, elapsed_ms=prod_ms,
            body_excerpt=prod_body[:1500],
            extra={"local_status": local_sc, "prod_status": prod_sc, "local_url": local_url, "prod_url": prod_url},
        ))
        pytest.fail(f"CLOUDFLARED_GAP {label}: {detail}")

    if local_sc != expected_status:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target="localhost", category=cf.FailureCategory.HTTP_4XX_UNEXPECTED if (local_sc and 400 <= local_sc < 500) else cf.FailureCategory.HTTP_5XX if (local_sc and 500 <= local_sc < 600) else cf.FailureCategory.NETWORK_ERROR,
            detail=f"local does not return expected {expected_status}; {detail}",
            method="GET", path=local_url, status_code=local_sc,
            elapsed_ms=local_ms, body_excerpt=local_body[:1500],
        ))
        pytest.fail(f"LOCAL_FAIL {label}: {detail}")

    cf.record_pass(test_id, "diff", max(local_ms, prod_ms), path=label)
