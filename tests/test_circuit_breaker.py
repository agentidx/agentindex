"""
Tests for circuit_breaker.py — Sprint 0 Track B.
"""

import time
from agentindex.circuit_breaker import (
    is_available,
    record_success,
    record_failure,
    get_circuit_status,
    _circuits,
    _FAILURE_THRESHOLD,
)


def _reset():
    _circuits.clear()


class TestCircuitBreaker:
    def setup_method(self):
        _reset()

    def test_starts_available(self):
        assert is_available("coingecko") is True

    def test_stays_available_below_threshold(self):
        for _ in range(_FAILURE_THRESHOLD - 1):
            record_failure("coingecko")
        assert is_available("coingecko") is True

    def test_opens_at_threshold(self):
        for _ in range(_FAILURE_THRESHOLD):
            record_failure("coingecko")
        assert is_available("coingecko") is False

    def test_success_resets_circuit(self):
        for _ in range(_FAILURE_THRESHOLD):
            record_failure("coingecko")
        assert is_available("coingecko") is False
        record_success("coingecko")
        assert is_available("coingecko") is True

    def test_independent_circuits(self):
        for _ in range(_FAILURE_THRESHOLD):
            record_failure("coingecko")
        assert is_available("coingecko") is False
        assert is_available("defillama") is True

    def test_get_circuit_status_returns_all(self):
        record_failure("coingecko")
        record_success("defillama")
        status = get_circuit_status()
        assert "coingecko" in status
        assert "defillama" in status
        assert status["coingecko"]["state"] == "closed"
        assert status["coingecko"]["consecutive_failures"] == 1
        assert status["defillama"]["total_successes"] == 1

    def test_backoff_increases(self):
        # First trip: opens at threshold
        for _ in range(_FAILURE_THRESHOLD):
            record_failure("api_x")
        status1 = get_circuit_status()
        backoff1 = status1["api_x"]["backoff_seconds"]
        assert status1["api_x"]["state"] == "open"

        # Each additional failure while open doubles the backoff
        record_failure("api_x")
        status2 = get_circuit_status()
        backoff2 = status2["api_x"]["backoff_seconds"]
        assert backoff2 > backoff1

    def test_backoff_caps_at_max(self):
        # Force many failures
        for _ in range(100):
            record_failure("api_x")
        status = get_circuit_status()
        assert status["api_x"]["backoff_seconds"] <= 600

    def test_open_circuit_becomes_available_after_backoff(self):
        # Manipulate time by directly setting last_failure_time
        for _ in range(_FAILURE_THRESHOLD):
            record_failure("coingecko")
        assert is_available("coingecko") is False

        # Simulate backoff elapsed
        _circuits["coingecko"]["last_failure_time"] = time.time() - 700
        assert is_available("coingecko") is True

    def test_status_fields(self):
        record_failure("test_api")
        status = get_circuit_status()["test_api"]
        assert "state" in status
        assert "available" in status
        assert "consecutive_failures" in status
        assert "backoff_seconds" in status
        assert "total_failures" in status
        assert "total_successes" in status
