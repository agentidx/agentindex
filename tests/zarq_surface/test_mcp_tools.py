"""MCP tool surface tests.

The ZARQ MCP server on :8001 (com.zarq.mcp-sse) exposes 19 tools via
JSON-RPC over HTTP/SSE. We hit the POST /mcp endpoint with a tools/call
JSON-RPC envelope and validate that the response is a well-formed result.

The server proxies every tool to localhost:8000/<path>, so failures
here typically mean (a) the main API is down, (b) the proxied path is
broken, or (c) the MCP server itself has a parser issue.

Production tests hit https://mcp.zarq.ai which goes through Cloudflare
to the same :8001 process.
"""

from __future__ import annotations

import json
import time

import httpx
import pytest

from . import conftest as cf


# (tool_name, args_factory) — the args_factory builds args from synthetic_inputs
TOOL_CASES = [
    ("crypto_rating",         lambda s: {"token_id": s["tokens"][0]}),
    ("crypto_dtd",            lambda s: {"token_id": s["tokens"][0]}),
    ("crypto_signals",        lambda s: {}),
    ("crypto_compare",        lambda s: {"token_a": s["tokens"][0], "token_b": s["tokens"][1]}),
    ("crypto_distress_watch", lambda s: {}),
    ("crypto_alerts",         lambda s: {}),
    ("crypto_ratings_bulk",   lambda s: {}),
    ("check_token_risk",      lambda s: {"token": s["tokens"][0]}),
    ("get_risk_signals",      lambda s: {}),
    ("get_trust_score",       lambda s: {"token": s["tokens"][0]}),
    ("kya_check_agent",       lambda s: {"agent": s["agents"][0]}),
    ("get_signal_feed",       lambda s: {}),
    ("vitality_check",        lambda s: {"token": s["tokens"][0]}),
    ("vitality_compare",      lambda s: {"token_a": s["tokens"][0], "token_b": s["tokens"][1]}),
    ("find_best_agent",       lambda s: {"category": "coding", "min_trust_score": 50}),
    ("agent_benchmark",       lambda s: {"category": "security"}),
    ("get_agent_stats",       lambda s: {}),
    ("preflight_check",       lambda s: {"target": s["agents"][0]}),
    ("best_in_category",      lambda s: {"category": s["categories"][0], "limit": 5}),
]


def _build_rpc_envelope(tool: str, args: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": f"surface-test-{tool}",
        "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    }


@pytest.mark.parametrize(
    "tool_name,args_factory",
    TOOL_CASES,
    ids=[t[0] for t in TOOL_CASES],
)
def test_mcp_tool(tool_name, args_factory, target, mcp_base_url, http_client,
                  synthetic_inputs, request):
    """Hit POST /mcp with a tools/call envelope and validate the response."""
    test_id = request.node.nodeid
    args = args_factory(synthetic_inputs)
    envelope = _build_rpc_envelope(tool_name, args)
    url = f"{mcp_base_url}/mcp"

    t0 = time.time()
    try:
        resp = http_client.post(url, json=envelope, headers={"Content-Type": "application/json"})
    except httpx.TimeoutException:
        elapsed = (time.time() - t0) * 1000
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.TIMEOUT,
            detail=f"MCP timeout after {elapsed:.0f}ms",
            method="POST", path=f"/mcp:{tool_name}", elapsed_ms=elapsed,
        ))
        pytest.fail(f"TIMEOUT mcp/{tool_name}")
    except httpx.RequestError as e:
        elapsed = (time.time() - t0) * 1000
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.NETWORK_ERROR,
            detail=f"{type(e).__name__}: {e}",
            method="POST", path=f"/mcp:{tool_name}", elapsed_ms=elapsed,
        ))
        pytest.fail(f"NETWORK_ERROR mcp/{tool_name}: {e}")

    elapsed = (time.time() - t0) * 1000
    body = resp.text[:4000]

    # 5xx → server-side
    if 500 <= resp.status_code < 600:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.HTTP_5XX,
            detail=f"mcp server status {resp.status_code}",
            method="POST", path=f"/mcp:{tool_name}", status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body,
        ))
        pytest.fail(f"HTTP_5XX mcp/{tool_name}")

    # 4xx → unexpected (we believe /mcp is public)
    if resp.status_code == 405 or resp.status_code == 404:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.HTTP_4XX_UNEXPECTED,
            detail=f"mcp endpoint returned {resp.status_code}",
            method="POST", path=f"/mcp:{tool_name}", status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body,
        ))
        pytest.fail(f"HTTP_4XX mcp/{tool_name}")

    if resp.status_code != 200:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.HTTP_4XX_UNEXPECTED,
            detail=f"mcp status {resp.status_code}",
            method="POST", path=f"/mcp:{tool_name}", status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body,
        ))
        pytest.fail(f"HTTP {resp.status_code} mcp/{tool_name}")

    # Validate JSON-RPC envelope
    try:
        data = resp.json()
    except json.JSONDecodeError as e:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.PARSE_ERROR,
            detail=f"mcp body not JSON: {e}",
            method="POST", path=f"/mcp:{tool_name}", status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body,
        ))
        pytest.fail(f"PARSE_ERROR mcp/{tool_name}")

    # JSON-RPC error in envelope
    if "error" in data:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.EXCEPTION_IN_BODY,
            detail=f"jsonrpc error: {str(data['error'])[:200]}",
            method="POST", path=f"/mcp:{tool_name}", status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body,
        ))
        pytest.fail(f"EXCEPTION_IN_BODY mcp/{tool_name}")

    result = data.get("result")
    if not result:
        cf.record_failure(cf.FailureRecord(
            test_id=test_id, target=target, category=cf.FailureCategory.EMPTY_RESPONSE,
            detail="jsonrpc result empty or missing",
            method="POST", path=f"/mcp:{tool_name}", status_code=resp.status_code,
            elapsed_ms=elapsed, body_excerpt=body,
        ))
        pytest.fail(f"EMPTY_RESPONSE mcp/{tool_name}")

    cf.record_pass(test_id, target, elapsed, path=f"/mcp:{tool_name}")
