"""
Circuit Breaker for external API calls.
Sprint 0, Track B.

Tracks consecutive failures per API. After 3 failures, backs off exponentially
(30s, 60s, 120s, max 10 min). Logs state changes.
"""

import logging
import time
import threading

logger = logging.getLogger("zarq.circuit_breaker")

_FAILURE_THRESHOLD = 3
_BASE_BACKOFF = 30  # seconds
_MAX_BACKOFF = 600  # 10 minutes

_lock = threading.Lock()
_circuits: dict[str, dict] = {}


def _get_circuit(name: str) -> dict:
    if name not in _circuits:
        _circuits[name] = {
            "state": "closed",  # closed = healthy, open = failing
            "consecutive_failures": 0,
            "last_failure_time": 0,
            "backoff_seconds": _BASE_BACKOFF,
            "total_failures": 0,
            "total_successes": 0,
            "last_state_change": 0,
        }
    return _circuits[name]


def is_available(name: str) -> bool:
    """Check if an API circuit is available (not in backoff)."""
    with _lock:
        circuit = _get_circuit(name)
        if circuit["state"] == "closed":
            return True
        # Check if backoff period has elapsed
        elapsed = time.time() - circuit["last_failure_time"]
        return elapsed >= circuit["backoff_seconds"]


def record_success(name: str):
    """Record a successful API call. Resets the circuit to closed."""
    with _lock:
        circuit = _get_circuit(name)
        circuit["total_successes"] += 1
        if circuit["state"] == "open":
            logger.info(
                "Circuit %s: CLOSED (recovered after %d failures, backoff was %ds)",
                name, circuit["consecutive_failures"], circuit["backoff_seconds"],
            )
            circuit["last_state_change"] = time.time()
        circuit["state"] = "closed"
        circuit["consecutive_failures"] = 0
        circuit["backoff_seconds"] = _BASE_BACKOFF


def record_failure(name: str):
    """Record a failed API call. Opens circuit after threshold."""
    with _lock:
        circuit = _get_circuit(name)
        circuit["consecutive_failures"] += 1
        circuit["total_failures"] += 1
        circuit["last_failure_time"] = time.time()

        if circuit["consecutive_failures"] >= _FAILURE_THRESHOLD:
            if circuit["state"] == "closed":
                logger.warning(
                    "Circuit %s: OPEN after %d consecutive failures, backing off %ds",
                    name, circuit["consecutive_failures"], circuit["backoff_seconds"],
                )
                circuit["last_state_change"] = time.time()
            circuit["state"] = "open"
            # Exponential backoff: double each time, cap at max
            circuit["backoff_seconds"] = min(
                circuit["backoff_seconds"] * 2, _MAX_BACKOFF
            )


def get_circuit_status() -> dict:
    """Return status of all tracked circuits. Used by healthcheck."""
    with _lock:
        result = {}
        for name, circuit in _circuits.items():
            available = True
            if circuit["state"] == "open":
                elapsed = time.time() - circuit["last_failure_time"]
                available = elapsed >= circuit["backoff_seconds"]
            result[name] = {
                "state": circuit["state"],
                "available": available,
                "consecutive_failures": circuit["consecutive_failures"],
                "backoff_seconds": circuit["backoff_seconds"],
                "total_failures": circuit["total_failures"],
                "total_successes": circuit["total_successes"],
            }
        return result
