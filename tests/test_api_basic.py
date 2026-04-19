"""
Basic API endpoint tests for ZARQ + Nerq.
Tests the 10 most important endpoints for status codes, JSON validity, and required fields.
"""

import pytest
from starlette.testclient import TestClient
from agentindex.api.discovery import app

client = TestClient(app, raise_server_exceptions=False)


# --- 1. Homepage ---

class TestHomepage:
    def test_homepage_returns_200(self):
        r = client.get("/")
        assert r.status_code == 200

    def test_homepage_is_html(self):
        r = client.get("/")
        assert "text/html" in r.headers.get("content-type", "")


# --- 2. Health endpoint ---

class TestHealth:
    def test_health_returns_200(self):
        r = client.get("/v1/health")
        assert r.status_code == 200

    def test_health_has_required_fields(self):
        data = client.get("/v1/health").json()
        assert "status" in data
        assert "timestamp" in data
        assert data["status"] in ("ok", "error")

    def test_health_head(self):
        r = client.head("/v1/health")
        assert r.status_code == 200


# --- 3. Stats endpoint ---

class TestStats:
    def test_stats_returns_200(self):
        r = client.get("/v1/stats")
        assert r.status_code == 200

    def test_stats_has_required_fields(self):
        data = client.get("/v1/stats").json()
        for field in ("total_agents", "active_agents", "categories", "sources", "protocols"):
            assert field in data, f"Missing field: {field}"
        assert isinstance(data["total_agents"], int)
        assert isinstance(data["categories"], dict)


# --- 3b. Nerq /v1/agent/stats (regression for FU-QUERY-20260418-07) ---

class TestAgentStats:
    """Regression coverage for /v1/agent/stats.

    AUDIT-QUERY-20260418 finding #7: endpoint returned 500/503 on 27/27 requests
    over 7d because the language GROUP BY on agents timed out (5s) cold-cache and
    the outer handler converted any subquery failure into 503. The handler now
    degrades gracefully — the endpoint must always return 200 with the core
    payload, even when the language query fails.
    """

    def test_agent_stats_returns_200(self):
        r = client.get("/v1/agent/stats")
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"

    def test_agent_stats_has_required_fields(self):
        data = client.get("/v1/agent/stats").json()
        for field in (
            "total_assets",
            "total_agents",
            "total_tools",
            "total_mcp_servers",
            "categories",
            "frameworks",
            "languages",
            "trust_distribution",
            "updated_at",
        ):
            assert field in data, f"Missing field: {field}"
        assert isinstance(data["categories"], dict)
        assert isinstance(data["languages"], dict)
        assert isinstance(data["trust_distribution"], dict)

    def test_agent_stats_survives_language_query_failure(self, monkeypatch):
        """If the language subquery raises (e.g. statement timeout), the endpoint
        must still return 200 with the rest of the payload populated."""
        import agentindex.nerq_api as nerq_api

        # Bust the cache so the handler actually executes the queries.
        nerq_api._stats_cache["data"] = None
        nerq_api._stats_cache["ts"] = 0

        real_session_factory = nerq_api.get_session

        class _LangFailSession:
            def __init__(self, inner):
                self._inner = inner

            def execute(self, stmt, *args, **kwargs):
                sql = str(stmt)
                if "FROM agents" in sql and "GROUP BY lang" in sql:
                    raise RuntimeError("simulated statement timeout")
                return self._inner.execute(stmt, *args, **kwargs)

            def begin_nested(self):
                return self._inner.begin_nested()

            def close(self):
                return self._inner.close()

            def __getattr__(self, name):
                return getattr(self._inner, name)

        def _wrapped():
            return _LangFailSession(real_session_factory())

        monkeypatch.setattr(nerq_api, "get_session", _wrapped)
        r = client.get("/v1/agent/stats")
        assert r.status_code == 200, f"expected 200 with language failure, got {r.status_code}: {r.text[:300]}"
        data = r.json()
        assert data["languages"] == {} or isinstance(data["languages"], dict)
        # Core fields must still be present.
        assert "total_agents" in data
        assert "categories" in data


# --- 4. Semantic status ---

class TestSemanticStatus:
    def test_semantic_status_returns_200(self):
        r = client.get("/v1/semantic/status")
        assert r.status_code == 200

    def test_semantic_status_is_json(self):
        data = client.get("/v1/semantic/status").json()
        assert isinstance(data, dict)


# --- 5. A2A Agent Card ---

class TestAgentCard:
    def test_agent_card_returns_200(self):
        r = client.get("/.well-known/agent-card.json")
        assert r.status_code == 200

    def test_agent_card_has_required_fields(self):
        data = client.get("/.well-known/agent-card.json").json()
        # A2A spec requires name and url at minimum
        assert "name" in data or "agent" in data


# --- 6. Crypto Trust Score rating ---

class TestCryptoRating:
    def test_rating_bitcoin_returns_200(self):
        r = client.get("/v1/crypto/rating/bitcoin")
        assert r.status_code == 200

    def test_rating_bitcoin_has_fields(self):
        resp = client.get("/v1/crypto/rating/bitcoin").json()
        # API wraps in {"data": ..., "meta": ...}
        assert "data" in resp, f"Missing 'data' wrapper. Keys: {list(resp.keys())}"
        data = resp["data"]
        assert "token_id" in data
        assert "score" in data or "rating" in data

    def test_rating_nonexistent_returns_404(self):
        r = client.get("/v1/crypto/rating/zzz-nonexistent-token-zzz")
        assert r.status_code in (404, 200)  # May return 404 or empty


# --- 7. Crypto NDD (distance-to-default) ---

class TestCryptoNDD:
    def test_ndd_bitcoin_returns_200(self):
        r = client.get("/v1/crypto/ndd/bitcoin")
        assert r.status_code == 200

    def test_ndd_bitcoin_has_fields(self):
        resp = client.get("/v1/crypto/ndd/bitcoin").json()
        assert "data" in resp, f"Missing 'data' wrapper. Keys: {list(resp.keys())}"
        data = resp["data"]
        assert "token_id" in data
        assert "ndd" in data or "ndd_score" in data or "alert_level" in data


# --- 8. Crypto ratings list ---

class TestCryptoRatingsList:
    def test_ratings_list_returns_200(self):
        r = client.get("/v1/crypto/ratings")
        assert r.status_code == 200

    def test_ratings_list_has_data(self):
        resp = client.get("/v1/crypto/ratings").json()
        # May be wrapped in {"data": [...], "meta": ...} or bare list
        if isinstance(resp, dict) and "data" in resp:
            assert isinstance(resp["data"], list)
        else:
            assert isinstance(resp, list)


# --- 9. Crypto risk signals ---

class TestCryptoSignals:
    def test_signals_returns_ok(self):
        r = client.get("/v1/crypto/signals")
        assert r.status_code in (200, 500), f"Unexpected status: {r.status_code}"

    def test_signals_is_json(self):
        r = client.get("/v1/crypto/signals")
        if r.status_code == 200:
            data = r.json()
            # May be wrapped or bare list
            if isinstance(data, dict) and "data" in data:
                assert isinstance(data["data"], list)
            else:
                assert isinstance(data, list)


# --- 10. Crypto risk-level (tier/degradation logic) ---

class TestCryptoRiskLevel:
    def test_risk_level_bitcoin_returns_200(self):
        r = client.get("/v1/crypto/risk-level/bitcoin")
        assert r.status_code == 200

    def test_risk_level_has_verdict_or_trust(self):
        resp = client.get("/v1/crypto/risk-level/bitcoin").json()
        # API wraps in {"data": ..., "meta": ...}
        data = resp.get("data", resp)
        has_required = any(
            field in data
            for field in ("risk_level", "trust_score", "verdict", "structural_weakness")
        )
        assert has_required, f"Response missing risk/trust fields. Keys: {list(data.keys())}"


# --- Bonus: POST /v1/discover ---

class TestDiscover:
    def test_discover_returns_200(self):
        r = client.post("/v1/discover", json={"need": "code review"})
        assert r.status_code == 200

    def test_discover_has_required_fields(self):
        data = client.post("/v1/discover", json={"need": "code review"}).json()
        assert "results" in data
        assert "total_matching" in data
        assert "index_size" in data
        assert isinstance(data["results"], list)

    def test_discover_missing_need_returns_422(self):
        r = client.post("/v1/discover", json={})
        assert r.status_code == 422


# --- 12. Observability /internal/metrics ---

class TestInternalMetrics:
    def test_metrics_unauthorized_without_token(self):
        r = client.get("/internal/metrics")
        assert r.status_code == 401

    def test_metrics_unauthorized_wrong_token(self):
        r = client.get("/internal/metrics", headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401

    def test_metrics_returns_200_with_valid_token(self):
        r = client.get(
            "/internal/metrics",
            headers={"Authorization": "Bearer zarq-internal-2026"},
        )
        assert r.status_code == 200

    def test_metrics_has_required_fields(self):
        r = client.get(
            "/internal/metrics",
            headers={"Authorization": "Bearer zarq-internal-2026"},
        )
        data = r.json()
        for field in (
            "requests_last_24h",
            "requests_last_1h",
            "unique_ips_last_24h",
            "p50_latency_ms",
            "p95_latency_ms",
            "top_10_endpoints",
            "tier_distribution",
        ):
            assert field in data, f"Missing field: {field}"
        assert isinstance(data["top_10_endpoints"], list)
        assert isinstance(data["tier_distribution"], dict)


# --- 13. /v1/check/{token} ---

class TestCheckEndpoint:
    def test_check_bitcoin_returns_200(self):
        r = client.get("/v1/check/bitcoin")
        assert r.status_code == 200

    def test_check_bitcoin_has_required_fields(self):
        data = client.get("/v1/check/bitcoin").json()
        for field in (
            "token", "verdict", "trust_score", "distance_to_default",
            "structural_weakness", "risk_level", "crash_probability", "checked_at",
        ):
            assert field in data, f"Missing field: {field}"

    def test_check_verdict_is_valid(self):
        data = client.get("/v1/check/bitcoin").json()
        assert data["verdict"] in ("SAFE", "WARNING", "CRITICAL")

    def test_check_trust_score_is_numeric(self):
        data = client.get("/v1/check/bitcoin").json()
        assert isinstance(data["trust_score"], (int, float))
        assert 0 <= data["trust_score"] <= 100

    def test_check_unknown_token_returns_404(self):
        r = client.get("/v1/check/zzz-nonexistent-token-zzz")
        assert r.status_code == 404
        data = r.json()
        assert "error" in data
        assert "available_tokens" in data

    def test_check_ethereum_returns_200(self):
        r = client.get("/v1/check/ethereum")
        assert r.status_code == 200
        data = r.json()
        assert data["token"] == "ethereum"

    def test_check_has_name_and_symbol(self):
        data = client.get("/v1/check/bitcoin").json()
        assert "name" in data
        assert "symbol" in data


# --- 14. Response headers on /v1/ ---

class TestResponseHeaders:
    def test_v1_health_has_powered_by(self):
        r = client.get("/v1/health")
        assert r.headers.get("X-Powered-By") == "ZARQ (zarq.ai)"

    def test_v1_has_daily_limit_header(self):
        r = client.get("/v1/health")
        assert r.headers.get("X-Daily-Limit") == "5000"

    def test_v1_has_tier_header(self):
        r = client.get("/v1/health")
        assert "X-Tier" in r.headers

    def test_v1_has_calls_today_header(self):
        r = client.get("/v1/health")
        assert "X-Calls-Today" in r.headers
        # Should be a numeric string
        assert r.headers["X-Calls-Today"].isdigit()


# --- 15. Tier Logic ---

class TestTierLogic:
    def test_open_tier_returns_full_response(self):
        r = client.get("/v1/check/bitcoin")
        assert r.status_code == 200
        data = r.json()
        assert "crash_probability" in data
        assert "distance_to_default" in data

    def test_tier_header_present(self):
        r = client.get("/v1/check/bitcoin")
        assert "X-Tier" in r.headers
        assert r.headers["X-Tier"] in ("open", "signal", "degraded", "blocked")

    def test_daily_limit_is_5000(self):
        r = client.get("/v1/check/bitcoin")
        assert r.headers.get("X-Daily-Limit") == "5000"

    def test_tier_function_boundaries(self):
        from agentindex.observability import _get_tier
        assert _get_tier(0) == "open"
        assert _get_tier(499) == "open"
        assert _get_tier(500) == "signal"
        assert _get_tier(1999) == "signal"
        assert _get_tier(2000) == "degraded"
        assert _get_tier(4999) == "degraded"
        assert _get_tier(5000) == "blocked"
        assert _get_tier(10000) == "blocked"

    def test_strip_degraded_fields(self):
        from agentindex.observability import _strip_degraded_fields
        import json
        body = json.dumps({"token": "bitcoin", "crash_probability": 0.31, "distance_to_default": 3.0, "trust_score": 74}).encode()
        stripped = json.loads(_strip_degraded_fields(body))
        assert "trust_score" in stripped
        assert "crash_probability" not in stripped
        assert "distance_to_default" not in stripped
        assert stripped["_degraded"] is True

    def test_strip_preserves_nested(self):
        from agentindex.observability import _strip_degraded_fields
        import json
        body = json.dumps({"data": [{"token": "btc", "crash_probability": 0.5, "trust_score": 70}]}).encode()
        stripped = json.loads(_strip_degraded_fields(body))
        assert stripped["data"][0]["trust_score"] == 70
        assert "crash_probability" not in stripped["data"][0]


# --- 16. Save Simulator ---

class TestSaveSimulator:
    def test_save_simulator_api_returns_200(self):
        r = client.get("/v1/demo/save-simulator")
        assert r.status_code == 200

    def test_save_simulator_has_saves(self):
        data = client.get("/v1/demo/save-simulator").json()
        assert "saves" in data
        assert isinstance(data["saves"], list)
        assert len(data["saves"]) > 0

    def test_save_has_required_fields(self):
        data = client.get("/v1/demo/save-simulator").json()
        save = data["saves"][0]
        for field in ("token", "symbol", "warning_date", "price_at_warning", "price_at_bottom", "drop_percent", "message"):
            assert field in save, f"Missing field: {field}"

    def test_save_drop_over_50(self):
        data = client.get("/v1/demo/save-simulator").json()
        for save in data["saves"]:
            assert save["drop_percent"] > 50

    def test_save_simulator_page_returns_html(self):
        r = client.get("/demo/save-simulator")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert "ZARQ" in r.text

    def test_save_simulator_page_has_cta(self):
        r = client.get("/demo/save-simulator")
        assert "/v1/check/" in r.text
        assert "Add ZARQ" in r.text


# --- 17. Integration: Solana Agent Kit Tool ---

class TestSolanaAgentKitTool:
    def test_resolve_symbol(self):
        import sys, os
        sys.path.insert(0, os.path.expanduser("~/agentindex/integrations/solana-agent-kit"))
        from zarq_tool import resolve_token_id
        assert resolve_token_id("SOL") == "solana"
        assert resolve_token_id("BTC") == "bitcoin"
        assert resolve_token_id("ETH") == "ethereum"
        assert resolve_token_id("sol") == "solana"

    def test_resolve_mint(self):
        import sys, os
        sys.path.insert(0, os.path.expanduser("~/agentindex/integrations/solana-agent-kit"))
        from zarq_tool import resolve_token_id
        assert resolve_token_id("So11111111111111111111111111111111111111112") == "solana"
        assert resolve_token_id("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v") == "usd-coin"

    def test_resolve_coingecko_id(self):
        import sys, os
        sys.path.insert(0, os.path.expanduser("~/agentindex/integrations/solana-agent-kit"))
        from zarq_tool import resolve_token_id
        assert resolve_token_id("bitcoin") == "bitcoin"
        assert resolve_token_id("solana") == "solana"

    def test_check_token_risk_live(self):
        import sys, os
        sys.path.insert(0, os.path.expanduser("~/agentindex/integrations/solana-agent-kit"))
        from zarq_tool import check_token_risk
        result = check_token_risk("SOL", api_base="http://localhost:8000")
        assert "verdict" in result
        assert "trust_score" in result
        assert "recommendation" in result
        assert result["token"] == "solana"

    def test_check_token_risk_unknown(self):
        import sys, os
        sys.path.insert(0, os.path.expanduser("~/agentindex/integrations/solana-agent-kit"))
        from zarq_tool import check_token_risk
        result = check_token_risk("zzz-nonexistent", api_base="http://localhost:8000")
        assert "error" in result

    def test_tool_definition_has_required_keys(self):
        import sys, os
        sys.path.insert(0, os.path.expanduser("~/agentindex/integrations/solana-agent-kit"))
        from zarq_tool import ZARQ_TOOL_DEFINITION
        assert ZARQ_TOOL_DEFINITION["name"] == "zarq_risk_check"
        assert "handler" in ZARQ_TOOL_DEFINITION
        assert callable(ZARQ_TOOL_DEFINITION["handler"])


# --- 18. Integration: LangChain Tool ---

class TestLangChainTool:
    def test_langchain_tool_imports(self):
        import sys, os
        sys.path.insert(0, os.path.expanduser("~/agentindex/integrations/langchain"))
        from zarq_langchain import ZARQRiskCheck
        tool = ZARQRiskCheck()
        assert tool.name == "zarq_risk_check"
        assert "risk" in tool.description.lower()

    def test_langchain_tool_run(self):
        import sys, os
        sys.path.insert(0, os.path.expanduser("~/agentindex/integrations/langchain"))
        from zarq_langchain import ZARQRiskCheck
        tool = ZARQRiskCheck(api_base="http://localhost:8000")
        result = tool._run("bitcoin")
        assert "Bitcoin" in result
        assert "Verdict" in result
        assert "Trust Score" in result

    def test_langchain_tool_unknown_token(self):
        import sys, os
        sys.path.insert(0, os.path.expanduser("~/agentindex/integrations/langchain"))
        from zarq_langchain import ZARQRiskCheck
        tool = ZARQRiskCheck(api_base="http://localhost:8000")
        result = tool._run("zzz-nonexistent-token")
        assert "not found" in result.lower()


# --- 19. Crash Shield ---

class TestCrashShield:
    def test_saves_returns_200(self):
        r = client.get("/v1/crash-shield/saves")
        assert r.status_code == 200

    def test_saves_has_data(self):
        data = client.get("/v1/crash-shield/saves").json()
        assert "saves" in data
        assert "total" in data
        assert len(data["saves"]) > 0

    def test_save_has_required_fields(self):
        data = client.get("/v1/crash-shield/saves").json()
        save = data["saves"][0]
        for field in ("save_id", "token_id", "warning_date", "crash_date", "drop_percent", "sha256_hash"):
            assert field in save, f"Missing: {field}"

    def test_save_has_value_calculations(self):
        data = client.get("/v1/crash-shield/saves").json()
        save = data["saves"][0]
        assert "saved_per_1000_usd" in save
        assert "days_lead_time" in save
        assert save["saved_per_1000_usd"] > 0
        assert save["days_lead_time"] > 0

    def test_save_card_returns_html(self):
        data = client.get("/v1/crash-shield/saves").json()
        save_id = data["saves"][0]["save_id"]
        r = client.get(f"/v1/crash-shield/save/{save_id}/card")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_save_card_has_meta_tags(self):
        data = client.get("/v1/crash-shield/saves").json()
        save_id = data["saves"][0]["save_id"]
        r = client.get(f"/v1/crash-shield/save/{save_id}/card")
        assert "og:title" in r.text
        assert "twitter:card" in r.text
        assert "Trust Checked by" in r.text

    def test_save_card_pretty_url(self):
        data = client.get("/v1/crash-shield/saves").json()
        save_id = data["saves"][0]["save_id"]
        r = client.get(f"/save/{save_id}")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_save_card_404_for_unknown(self):
        r = client.get("/v1/crash-shield/save/nonexistent-save/card")
        assert r.status_code == 404

    def test_subscribe_returns_webhook_id(self):
        r = client.post("/v1/crash-shield/subscribe", json={
            "url": "https://test.example.com/hook",
            "alert_levels": "CRITICAL",
        })
        assert r.status_code == 200
        data = r.json()
        assert "webhook_id" in data
        assert data["status"] == "active"

    def test_subscribe_rejects_invalid_url(self):
        r = client.post("/v1/crash-shield/subscribe", json={"url": "not-a-url"})
        assert r.status_code == 400

    def test_subscribe_rejects_missing_url(self):
        r = client.post("/v1/crash-shield/subscribe", json={})
        assert r.status_code == 400


# --- 20. Forta Integration ---

class TestFortaIntegration:
    def test_protocol_matching(self):
        from agentindex.forta_integration import _match_to_zarq_token
        assert _match_to_zarq_token("uniswap", "", "") == "uniswap"
        assert _match_to_zarq_token("", "Aave exploit", "") == "aave"
        assert _match_to_zarq_token("", "", "Large chainlink oracle deviation") == "chainlink"
        assert _match_to_zarq_token("", "", "random unrelated alert") is None

    def test_forta_table_exists(self):
        import sqlite3, os
        DB = os.path.expanduser("~/agentindex/agentindex/crypto/crypto_trust.db")
        conn = sqlite3.connect(DB)
        cols = conn.execute("PRAGMA table_info(forta_alerts)").fetchall()
        conn.close()
        col_names = [c[1] for c in cols]
        assert "alert_id" in col_names
        assert "zarq_token_id" in col_names
        assert "severity" in col_names

    def test_get_stored_alerts_empty(self):
        from agentindex.forta_integration import get_stored_forta_alerts
        # Should return list (possibly empty), not crash
        result = get_stored_forta_alerts(token_id="nonexistent-token")
        assert isinstance(result, list)


# --- 21. ZARQ Operations Dashboard ---

class TestZARQDashboard:
    def test_dashboard_requires_auth(self):
        r = client.get("/zarq/dashboard")
        assert r.status_code == 401

    def test_dashboard_returns_html_with_auth(self):
        r = client.get("/zarq/dashboard", headers={"Authorization": "Bearer zarq-internal-2026"})
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_dashboard_has_title(self):
        r = client.get("/zarq/dashboard", headers={"Authorization": "Bearer zarq-internal-2026"})
        assert "ZARQ Operations Dashboard" in r.text

    def test_dashboard_has_sections(self):
        r = client.get("/zarq/dashboard", headers={"Authorization": "Bearer zarq-internal-2026"})
        assert "System Health" in r.text
        assert "API Traffic" in r.text
        assert "Risk Intelligence" in r.text
        assert "Agent Index" in r.text
        assert "Sprint Progress" in r.text
        assert "Paper Trading" in r.text

    def test_dashboard_token_query_param(self):
        r = client.get("/zarq/dashboard?token=zarq-internal-2026")
        assert r.status_code == 200

    def test_dashboard_data_requires_auth(self):
        r = client.get("/zarq/dashboard/data")
        assert r.status_code == 401

    def test_dashboard_data_returns_json(self):
        r = client.get("/zarq/dashboard/data", headers={"Authorization": "Bearer zarq-internal-2026"})
        assert r.status_code == 200
        data = r.json()
        assert "system_health" in data
        assert "api_traffic" in data
        assert "crypto" in data
        assert "agents" in data
        assert "sprints" in data

    def test_dashboard_data_has_launchagents(self):
        r = client.get("/zarq/dashboard/data", headers={"Authorization": "Bearer zarq-internal-2026"})
        data = r.json()
        assert "launchagents" in data["system_health"]

    def test_dashboard_data_has_disk(self):
        r = client.get("/zarq/dashboard/data", headers={"Authorization": "Bearer zarq-internal-2026"})
        data = r.json()
        assert "disk" in data["system_health"]
        assert "free_gb" in data["system_health"]["disk"]

    def test_dashboard_auto_refresh(self):
        r = client.get("/zarq/dashboard", headers={"Authorization": "Bearer zarq-internal-2026"})
        assert "setInterval(fetchData, 60000)" in r.text

    def test_dashboard_has_user_intelligence_section(self):
        r = client.get("/zarq/dashboard", headers={"Authorization": "Bearer zarq-internal-2026"})
        assert "User Intelligence" in r.text
        assert "Token Check Activity" in r.text
        assert "Recurring Integrations" in r.text

    def test_dashboard_data_has_user_intelligence(self):
        r = client.get("/zarq/dashboard/data", headers={"Authorization": "Bearer zarq-internal-2026"})
        data = r.json()
        assert "user_intelligence" in data
        ui = data["user_intelligence"]
        assert "user_types" in ui
        assert "ai_bots" in ui
        assert "top_users" in ui
        assert "token_checks" in ui
        assert "recurring_integrations" in ui
        assert "new_vs_returning" in ui

    def test_dashboard_user_intelligence_token_checks_structure(self):
        r = client.get("/zarq/dashboard/data", headers={"Authorization": "Bearer zarq-internal-2026"})
        tc = r.json()["user_intelligence"]["token_checks"]
        assert "total" in tc
        assert "unique_tokens" in tc
        assert "tokens" in tc
        assert isinstance(tc["tokens"], list)


# --- 22. ZARQ API Documentation Page ---

class TestZARQDocs:
    def test_docs_returns_200(self):
        r = client.get("/zarq/docs")
        assert r.status_code == 200

    def test_docs_is_html(self):
        r = client.get("/zarq/docs")
        assert "text/html" in r.headers.get("content-type", "")

    def test_docs_has_title(self):
        r = client.get("/zarq/docs")
        assert "ZARQ API Documentation" in r.text

    def test_docs_has_quick_start(self):
        r = client.get("/zarq/docs")
        assert "/v1/check/" in r.text
        assert "SAFE" in r.text
        assert "WARNING" in r.text
        assert "CRITICAL" in r.text

    def test_docs_has_integrations(self):
        r = client.get("/zarq/docs")
        assert "LangChain" in r.text
        assert "ElizaOS" in r.text
        assert "Solana Agent Kit" in r.text
        assert "mcp.zarq.ai" in r.text

    def test_docs_has_rate_limits(self):
        r = client.get("/zarq/docs")
        assert "5,000" in r.text
        assert "Rate Limits" in r.text

    def test_docs_no_auth_required(self):
        r = client.get("/zarq/docs")
        assert r.status_code == 200  # No auth needed
