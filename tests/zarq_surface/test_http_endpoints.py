"""HTTP-endpoint surface tests.

For each ZARQ-relevant route discovered in the source:
  1. Skip if the path can't be substituted with synthetic input (multi-param
     routes for which we have no mapping — covered separately).
  2. Skip non-GET methods (POST/PUT/DELETE handled in dedicated write-side
     tests; treating them as smoke targets would either fail spuriously or
     mutate state).
  3. Issue the request against the parameterized target (localhost or
     production). 8s ceiling enforced by the session client.
  4. Classify the outcome per the FailureCategory enum in conftest.
  5. Record pass / fail with raw response excerpt.

Tests are intentionally parametrized one-per-route, not aggregated. That
makes pytest's report a per-route pass/fail surface that's directly usable
as input for phase 3 root-cause categorization.
"""

from __future__ import annotations

import json
import re
import time

import httpx
import pytest

from . import conftest as cf
from .route_discovery import substitute_path_params


# ─── Test-id helpers ───────────────────────────────────────────────────────
def _route_id(route: dict) -> str:
    """Produce a stable, file-safe id used both as pytest parametrize id and
    as the failure-dump filename."""
    fname = route["file"].rsplit("/", 1)[-1].replace(".py", "")
    safe_path = re.sub(r"[^A-Za-z0-9._-]+", "_", route["path"]).strip("_")
    return f"{fname}_L{route['line']}_{route['method']}_{safe_path}"[:120]


# ─── Body inspection ───────────────────────────────────────────────────────
ERROR_BODY_PATTERNS = (
    re.compile(r"<title>[^<]*(error|exception)[^<]*</title>", re.IGNORECASE),
    re.compile(r"\bTraceback \(most recent call last\):", re.IGNORECASE),
    re.compile(r"\bInternal Server Error\b"),
    re.compile(r'\b"detail"\s*:\s*"Internal Server Error"'),
)

DB_TABLE_MISSING_PATTERNS = (
    re.compile(r'relation "([^"]+)" does not exist', re.IGNORECASE),
    re.compile(r"no such table:\s*(\S+)", re.IGNORECASE),
)
DB_COLUMN_MISSING_PATTERNS = (
    re.compile(r'column "([^"]+)" does not exist', re.IGNORECASE),
    re.compile(r"no such column:\s*(\S+)", re.IGNORECASE),
)
CACHE_NOT_BUILT_PATTERNS = (
    re.compile(r"cache.*not.*built|cache.*missing|placeholder.*data", re.IGNORECASE),
)


def classify_response(resp: httpx.Response, body: str, elapsed_ms: float) -> tuple[str, str] | None:
    """Return (category, detail) or None if the response passes."""
    sc = resp.status_code

    # 5xx → server-side crash
    if 500 <= sc < 600:
        # Look for specific DB schema errors before falling back to HTTP_5XX
        for pat in DB_TABLE_MISSING_PATTERNS:
            m = pat.search(body)
            if m:
                return cf.FailureCategory.DB_TABLE_MISSING, f"missing table: {m.group(1)} (status {sc})"
        for pat in DB_COLUMN_MISSING_PATTERNS:
            m = pat.search(body)
            if m:
                return cf.FailureCategory.DB_COLUMN_MISSING, f"missing column: {m.group(1)} (status {sc})"
        return cf.FailureCategory.HTTP_5XX, f"status {sc}"

    # 4xx → only "unexpected" if we believe the route should be public.
    # We treat 401/403 as unexpected here because the suite hits no auth-
    # gated endpoints knowingly. 404 too — every discovered route exists
    # in code, so a 404 means routing is broken (or routed off our hostname).
    if sc in (401, 403):
        return cf.FailureCategory.HTTP_4XX_UNEXPECTED, f"auth-required: status {sc}"
    if sc == 404:
        return cf.FailureCategory.HTTP_4XX_UNEXPECTED, f"unexpected 404 — route exists in code"
    if sc == 405:
        return cf.FailureCategory.HTTP_4XX_UNEXPECTED, f"method not allowed: status {sc}"

    # 2xx/3xx but body looks like an error page
    for pat in ERROR_BODY_PATTERNS:
        if pat.search(body):
            return cf.FailureCategory.EXCEPTION_IN_BODY, f"error pattern in body: {pat.pattern[:60]}"

    # Cache placeholders
    for pat in CACHE_NOT_BUILT_PATTERNS:
        if pat.search(body):
            return cf.FailureCategory.CACHE_NOT_BUILT, f"placeholder in body"

    # Empty body on JSON path
    if "application/json" in resp.headers.get("content-type", ""):
        try:
            data = json.loads(body) if body else None
            if data is None or data == {} or data == []:
                return cf.FailureCategory.EMPTY_RESPONSE, "empty JSON body"
        except json.JSONDecodeError as e:
            return cf.FailureCategory.PARSE_ERROR, f"JSON decode failed: {e}"

    # Empty body on HTML path (zero-byte or under 200 bytes is suspicious),
    # but skip the check for known-tiny endpoints: health probes, SEO
    # verification markers, sitemap robots-style files.
    path = getattr(resp.request, "url", None)
    path_str = str(path.path) if path else ""
    KNOWN_TINY = ("/health", "indexnow.txt", "google", "robots.txt")
    if (
        body
        and len(body.strip()) < 200
        and "html" in resp.headers.get("content-type", "")
        and not any(t in path_str for t in KNOWN_TINY)
    ):
        return cf.FailureCategory.EMPTY_RESPONSE, f"HTML body suspiciously small ({len(body)} bytes)"

    return None


# ─── Pytest test ────────────────────────────────────────────────────────────
def _testable_routes(routes: list[dict], synthetic: dict) -> list[dict]:
    """Filter discovered routes to a deduplicated, testable set.

    De-dup by (method, path) — many routes are duplicated across files.
    Keep only GET (other methods → dedicated write-side test).
    """
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for r in routes:
        if r["method"] != "GET":
            continue
        key = (r["method"], r["path"])
        if key in seen:
            continue
        seen.add(key)
        # Reject routes that need params we don't have a substitution for
        if substitute_path_params(r["path"], synthetic) is None:
            continue
        out.append(r)
    return out


# Build the parametrized list once at import time so pytest's --collect-only
# shows real test ids.
def _build_param_args():
    from pathlib import Path
    from .route_discovery import discover_zarq_routes
    routes = discover_zarq_routes(Path("/Users/anstudio/agentindex/agentindex"))
    try:
        with open(cf.SUITE_DIR / "fixtures" / "synthetic_requests.json") as fh:
            synthetic = json.load(fh)
    except Exception:
        synthetic = {"tokens": ["bitcoin", "ethereum"], "agents": ["autogpt"], "categories": ["vpn"]}
    testable = _testable_routes(routes, synthetic)
    return [pytest.param(r, id=_route_id(r)) for r in testable], synthetic


_PARAMS, _SYNTHETIC = _build_param_args()


# Paths we explicitly do NOT test (auth-gated or otherwise out of scope).
# Returns 403 by design — not a failure of the ZARQ public surface.
_OUT_OF_SCOPE_PREFIXES = (
    "/internal/",       # API-key gated admin endpoints
    "/admin/",          # admin-only paths
)


@pytest.mark.parametrize("route", _PARAMS)
def test_endpoint(route, target, http_client, base_url, api_base_url, request):
    """One smoke test per (route, target)."""
    test_id = request.node.nodeid
    concrete = substitute_path_params(route["path"], _SYNTHETIC)
    if any(concrete.startswith(p) for p in _OUT_OF_SCOPE_PREFIXES):
        cf.record_skip(test_id, target, f"out-of-scope prefix: {concrete.split('/', 2)[1]}")
        pytest.skip(f"out-of-scope (auth-gated): {concrete}")
    # Prefer api.zarq.ai for /api/* and /v1/* on production; landing pages on zarq.ai.
    # Locally there's only :8000 either way.
    if target == "production" and (concrete.startswith("/api/") or concrete.startswith("/v1/")):
        url = api_base_url + concrete
    else:
        url = base_url + concrete

    t0 = time.time()
    try:
        resp = http_client.get(url)
    except httpx.TimeoutException:
        elapsed = (time.time() - t0) * 1000
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.TIMEOUT,
            detail=f"client timeout after {elapsed:.0f}ms",
            method="GET", path=route["path"], status_code=None, elapsed_ms=elapsed,
            body_excerpt="", pg_pool="",
            extra={"url": url, "source_file": route["file"], "source_line": route["line"]},
        ))
        pytest.fail(f"TIMEOUT {url}")
    except httpx.RequestError as e:
        elapsed = (time.time() - t0) * 1000
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.NETWORK_ERROR,
            detail=f"{type(e).__name__}: {e}",
            method="GET", path=route["path"], status_code=None, elapsed_ms=elapsed,
            body_excerpt="", pg_pool="",
            extra={"url": url, "source_file": route["file"], "source_line": route["line"]},
        ))
        pytest.fail(f"NETWORK_ERROR {url}: {e}")

    elapsed = (time.time() - t0) * 1000
    body = resp.text[:4000]
    failure = classify_response(resp, body, elapsed)
    if failure is not None:
        category, detail = failure
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=category, detail=detail,
            method="GET", path=route["path"], status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body[:1500], pg_pool="",
            extra={"url": url, "source_file": route["file"], "source_line": route["line"]},
        ))
        pytest.fail(f"{category} {url}: {detail}")

    cf.record_pass(test_id, target, elapsed, path=route["path"])
