#!/usr/bin/env python3
"""
ZARQ-specific Healthchecks — Sprint 0, Track B
Extends system_healthcheck.py with crypto risk pipeline checks.

Checks:
  1. NDD pipeline staleness (nerq_risk_signals last update)
  2. Trust Score age (crypto_rating_daily most recent date)
  3. API responsiveness (localhost:8000/v1/health within 2s)
  4. Observability DB activity (zarq_api_log.db mod time < 10 min)
  5. Circuit breaker status (external API health)

Can be run standalone or imported by system_healthcheck.py.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

CRYPTO_DB = os.path.expanduser(
    "~/agentindex/agentindex/crypto/crypto_trust.db"
)
OBS_DB = os.path.expanduser(
    "~/agentindex/agentindex/crypto/zarq_api_log.db"
)
HC_DB = os.path.expanduser("~/agentindex/logs/healthcheck.db")


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} [ZARQ/{level}] {msg}")


def run_checks():
    checks = {}
    warnings = []
    errors = []
    metrics = {}

    # ── 1. NDD pipeline staleness ──
    try:
        conn = sqlite3.connect(CRYPTO_DB)
        row = conn.execute(
            "SELECT MAX(signal_date) FROM nerq_risk_signals"
        ).fetchone()
        conn.close()
        if row and row[0]:
            last_signal = row[0]
            checks["ndd_last_signal_date"] = last_signal
            age_days = (
                datetime.now() - datetime.strptime(last_signal, "%Y-%m-%d")
            ).days
            metrics["ndd_signal_age_days"] = age_days
            if age_days > 3:
                errors.append(
                    f"NDD pipeline stale: last signal {last_signal} ({age_days}d ago)"
                )
            elif age_days > 1:
                warnings.append(
                    f"NDD pipeline: last signal {last_signal} ({age_days}d ago)"
                )
        else:
            errors.append("NDD pipeline: no signals found in nerq_risk_signals")
            checks["ndd_last_signal_date"] = None
    except Exception as e:
        errors.append(f"NDD pipeline check failed: {e}")
        checks["ndd_last_signal_date"] = "error"

    # ── 2. Trust Score age ──
    try:
        conn = sqlite3.connect(CRYPTO_DB)
        row = conn.execute(
            "SELECT MAX(run_date) FROM crypto_rating_daily"
        ).fetchone()
        conn.close()
        if row and row[0]:
            last_rating = row[0]
            checks["trust_score_last_date"] = last_rating
            age_days = (
                datetime.now() - datetime.strptime(last_rating, "%Y-%m-%d")
            ).days
            metrics["trust_score_age_days"] = age_days
            if age_days > 3:
                errors.append(
                    f"Trust Scores stale: last run {last_rating} ({age_days}d ago)"
                )
            elif age_days > 1:
                warnings.append(
                    f"Trust Scores: last run {last_rating} ({age_days}d ago)"
                )
        else:
            errors.append("Trust Scores: no data in crypto_rating_daily")
            checks["trust_score_last_date"] = None
    except Exception as e:
        errors.append(f"Trust Score check failed: {e}")
        checks["trust_score_last_date"] = "error"

    # ── 3. API responsiveness (<2s) ──
    try:
        start = time.time()
        r = subprocess.run(
            ["curl", "-s", "-m", "2", "http://localhost:8000/v1/health"],
            capture_output=True, text=True, timeout=5,
        )
        latency_ms = round((time.time() - start) * 1000)
        metrics["api_health_latency_ms"] = latency_ms

        if r.returncode != 0:
            errors.append("API /v1/health: request failed (timeout or connection refused)")
            checks["api_health"] = "timeout"
        else:
            data = json.loads(r.stdout)
            status = data.get("status", "unknown")
            checks["api_health"] = status
            checks["api_health_latency_ms"] = latency_ms
            if status != "ok":
                warnings.append(f"API /v1/health returned status={status}")
            if latency_ms > 2000:
                warnings.append(f"API /v1/health slow: {latency_ms}ms (>2s)")
    except subprocess.TimeoutExpired:
        errors.append("API /v1/health: timed out after 2s")
        checks["api_health"] = "timeout"
    except Exception as e:
        errors.append(f"API health check failed: {e}")
        checks["api_health"] = "error"

    # ── 4. Observability DB activity ──
    try:
        if os.path.exists(OBS_DB):
            mod_time = os.path.getmtime(OBS_DB)
            age_min = (time.time() - mod_time) / 60
            metrics["obs_db_age_minutes"] = round(age_min, 1)
            checks["obs_db_active"] = age_min < 10

            if age_min > 10:
                warnings.append(
                    f"Observability DB not written in {age_min:.0f} min (>10 min)"
                )
        else:
            warnings.append("Observability DB not found (zarq_api_log.db)")
            checks["obs_db_active"] = False
    except Exception as e:
        warnings.append(f"Observability DB check failed: {e}")
        checks["obs_db_active"] = False

    # ── 5. Circuit breaker status ──
    try:
        sys.path.insert(0, os.path.expanduser("~/agentindex"))
        from agentindex.circuit_breaker import get_circuit_status

        cb_status = get_circuit_status()
        checks["circuit_breakers"] = cb_status
        for name, state in cb_status.items():
            if state["state"] == "open" and not state["available"]:
                warnings.append(
                    f"Circuit breaker {name}: OPEN "
                    f"({state['consecutive_failures']} failures, "
                    f"backoff {state['backoff_seconds']}s)"
                )
    except ImportError:
        checks["circuit_breakers"] = {}
    except Exception as e:
        checks["circuit_breakers"] = {"error": str(e)}

    # ── Verdict ──
    if errors:
        status = "ERROR"
    elif warnings:
        status = "WARNING"
    else:
        status = "HEALTHY"

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "metrics": metrics,
    }


def save_results(results):
    """Save ZARQ healthcheck results to the shared healthcheck.db."""
    os.makedirs(os.path.dirname(HC_DB), exist_ok=True)
    conn = sqlite3.connect(HC_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS zarq_healthcheck (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            checks TEXT NOT NULL,
            warnings TEXT,
            errors TEXT
        )
    """)
    conn.execute(
        "DELETE FROM zarq_healthcheck WHERE timestamp < datetime('now', '-7 days')"
    )
    conn.execute(
        "INSERT INTO zarq_healthcheck (timestamp, status, checks, warnings, errors) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            results["timestamp"],
            results["status"],
            json.dumps(results["checks"]),
            json.dumps(results["warnings"]),
            json.dumps(results["errors"]),
        ),
    )
    # Also save metrics to shared metrics table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS healthcheck_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL
        )
    """)
    for metric, value in results["metrics"].items():
        conn.execute(
            "INSERT INTO healthcheck_metrics (timestamp, metric, value) VALUES (?, ?, ?)",
            (results["timestamp"], f"zarq.{metric}", value),
        )
    conn.commit()
    conn.close()


def main():
    results = run_checks()

    log(f"Status: {results['status']}")
    for w in results["warnings"]:
        log(w, "WARN")
    for e in results["errors"]:
        log(e, "ERROR")
    log(f"Checks: {json.dumps(results['checks'], default=str)}")

    save_results(results)

    if results["errors"]:
        sys.exit(2)
    elif results["warnings"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
