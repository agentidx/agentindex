"""HTML template render tests.

The HTTP endpoint tests already exercise Jinja rendering as a side-effect
(a Jinja syntax error surfaces as 5xx with `TemplateSyntaxError` in the
body). This file adds a *focused* render check for the 18 ZARQ templates
identified in inventory section A.4 — we hit one canonical endpoint per
template and look for either the template rendering OR explicit Jinja
error markers in the body. Distinct from test_http_endpoints in that the
intent here is template-specific, so we use a tighter body pattern.
"""

from __future__ import annotations

import re
import time

import httpx
import pytest

from . import conftest as cf


# (template_name, canonical_path_to_render_it). Paths inferred from
# inventory section A.4 + grep of renderer modules.
TEMPLATE_CASES = [
    ("zarq_landing.html",              "/crypto"),
    ("zarq_methodology.html",          "/crypto/methodology"),
    ("zarq_whitepaper.html",           "/crypto/whitepaper"),
    ("zarq_api_docs.html",             "/zarq/doc"),
    ("zarq_cascade_risk.html",         "/cascade-risk"),
    ("zarq_early_warning.html",        "/crypto/early-warning"),
    ("zarq_track_record.html",         "/crypto/track-record"),
    ("zarq_vitality_backtest.html",    "/crypto/vitality-backtest"),
    ("zarq_vitality_methodology.html", "/crypto/vitality-methodology"),
    ("zarq_agent_intelligence.html",   "/crypto/agent-intelligence"),
    ("zarq_recovery.html",             "/crypto/recovery"),
    ("paper_trading.html",             "/crypto/paper-trading"),
    ("token_page.html",                "/token/bitcoin"),
    ("tokens_index.html",              "/tokens"),
    ("crash_watch.html",               "/crash-watch"),
    ("yield_risk.html",                "/yield"),
    ("learn_hub.html",                 "/learn"),
    ("learn_article.html",             "/learn/what-is-zarq"),
]

JINJA_ERROR_PATTERN = re.compile(
    r"(jinja2\.exceptions|TemplateSyntaxError|UndefinedError|TemplateNotFound|TemplateAssertionError)",
    re.IGNORECASE,
)


@pytest.mark.parametrize(
    "template,path",
    TEMPLATE_CASES,
    ids=[c[0] for c in TEMPLATE_CASES],
)
def test_template_renders(template, path, target, base_url, http_client, request):
    test_id = request.node.nodeid
    url = base_url + path

    t0 = time.time()
    try:
        resp = http_client.get(url)
    except httpx.TimeoutException:
        elapsed = (time.time() - t0) * 1000
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.TIMEOUT,
            detail=f"template render timed out",
            method="GET", path=path, elapsed_ms=elapsed,
            extra={"template": template, "url": url},
        ))
        pytest.fail(f"TIMEOUT {template}")
    except httpx.RequestError as e:
        elapsed = (time.time() - t0) * 1000
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.NETWORK_ERROR,
            detail=f"{type(e).__name__}: {e}",
            method="GET", path=path, elapsed_ms=elapsed,
            extra={"template": template, "url": url},
        ))
        pytest.fail(f"NETWORK_ERROR {template}")

    elapsed = (time.time() - t0) * 1000
    body = resp.text[:5000]

    # Jinja errors typically come back as a 500 with a template-traceback in
    # the body; FastAPI also reports 200 + "TemplateNotFound" in some edge
    # cases when the renderer catches.
    if JINJA_ERROR_PATTERN.search(body):
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.EXCEPTION_IN_BODY,
            detail=f"jinja error in body for template {template}",
            method="GET", path=path, status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body,
            extra={"template": template, "url": url},
        ))
        pytest.fail(f"JINJA_ERROR {template}")

    if 500 <= resp.status_code < 600:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.HTTP_5XX,
            detail=f"template path {path} returned {resp.status_code}",
            method="GET", path=path, status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body,
            extra={"template": template, "url": url},
        ))
        pytest.fail(f"HTTP_5XX {template}")

    if resp.status_code == 404:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.HTTP_4XX_UNEXPECTED,
            detail=f"template route 404 — template exists, route may be missing or path wrong: {path}",
            method="GET", path=path, status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body[:1500],
            extra={"template": template, "url": url},
        ))
        pytest.fail(f"HTTP_404 {template}")

    if resp.status_code != 200:
        # 3xx or other 4xx — record and move on
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.HTTP_4XX_UNEXPECTED,
            detail=f"template path {path} returned {resp.status_code}",
            method="GET", path=path, status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body[:1500],
            extra={"template": template, "url": url},
        ))
        pytest.fail(f"HTTP_{resp.status_code} {template}")

    if len(body) < 200:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.EMPTY_RESPONSE,
            detail=f"template rendered to <200 bytes ({len(body)} bytes)",
            method="GET", path=path, status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body,
            extra={"template": template, "url": url},
        ))
        pytest.fail(f"EMPTY {template}")

    cf.record_pass(test_id, target, elapsed, path=path)
