"""
Tests for zarq_healthcheck.py — Sprint 0 Track B.
Tests that the healthcheck runs without crashing and returns expected structure.
"""

import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.expanduser("~/agentindex"))

from zarq_healthcheck import run_checks


class TestZarqHealthcheck:
    def test_run_checks_returns_dict(self):
        results = run_checks()
        assert isinstance(results, dict)

    def test_has_required_keys(self):
        results = run_checks()
        for key in ("timestamp", "status", "checks", "warnings", "errors", "metrics"):
            assert key in results, f"Missing key: {key}"

    def test_status_is_valid(self):
        results = run_checks()
        assert results["status"] in ("HEALTHY", "WARNING", "ERROR")

    def test_checks_has_ndd_field(self):
        results = run_checks()
        assert "ndd_last_signal_date" in results["checks"]

    def test_checks_has_trust_score_field(self):
        results = run_checks()
        assert "trust_score_last_date" in results["checks"]

    def test_checks_has_api_health(self):
        results = run_checks()
        assert "api_health" in results["checks"]

    def test_checks_has_obs_db(self):
        results = run_checks()
        assert "obs_db_active" in results["checks"]

    def test_checks_has_circuit_breakers(self):
        results = run_checks()
        assert "circuit_breakers" in results["checks"]

    def test_warnings_and_errors_are_lists(self):
        results = run_checks()
        assert isinstance(results["warnings"], list)
        assert isinstance(results["errors"], list)

    def test_metrics_are_numeric(self):
        results = run_checks()
        for key, value in results["metrics"].items():
            assert isinstance(value, (int, float)), f"Metric {key} is {type(value)}"
