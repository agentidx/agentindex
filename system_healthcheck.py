#!/usr/bin/env python3
"""
NERQ System Healthcheck — Runs every 5 min via cron
Checks all components and writes status to SQLite for dashboard display.
Prints warnings to stdout (captured in log).

Checks:
  1. PostgreSQL: connections, long queries, locks, idle-in-transaction
  2. API: port 8000 responding
  3. MCP: port 8300 responding
  4. Process count: exactly 1 of each
  5. Disk space
  6. Redis
  7. Ollama
  8. Parser activity
  9. Agent count trend
"""

import os
import sys
import json
import time
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# Config
DB_PATH = os.path.expanduser("~/agentindex/logs/healthcheck.db")
PSQL = "/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql"
LOG_DIR = os.path.expanduser("~/agentindex/logs")

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} [{level}] {msg}")

def run_cmd(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except:
        return None

def check_port(port, timeout=5):
    r = run_cmd(f"curl -s -m {timeout} -o /dev/null -w '%{{http_code}}' http://localhost:{port}/")
    return r if r else "000"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS healthcheck (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            checks TEXT NOT NULL,
            warnings TEXT,
            errors TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS healthcheck_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL
        )
    """)
    # Keep 7 days of history
    conn.execute("DELETE FROM healthcheck WHERE timestamp < datetime('now', '-7 days')")
    conn.execute("DELETE FROM healthcheck_metrics WHERE timestamp < datetime('now', '-7 days')")
    conn.commit()
    return conn

def run_checks():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    checks = {}
    warnings = []
    errors = []
    metrics = {}

    # ── 1. PostgreSQL ──
    pg_conns = run_cmd(f'{PSQL} -d agentindex -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname=\'agentindex\';"')
    if pg_conns:
        n = int(pg_conns.strip())
        checks["pg_connections"] = n
        metrics["pg_connections"] = n
        if n > 50:
            errors.append(f"PostgreSQL: {n} connections (>50 = danger)")
        elif n > 30:
            warnings.append(f"PostgreSQL: {n} connections (>30 = elevated)")
    else:
        errors.append("PostgreSQL: cannot connect")
        checks["pg_connections"] = -1

    # Long queries
    long_q = run_cmd(f"""{PSQL} -d agentindex -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='agentindex' AND state != 'idle' AND query_start < now() - interval '5 minutes' AND pid != pg_backend_pid();" """)
    if long_q:
        n = int(long_q.strip())
        checks["pg_long_queries"] = n
        metrics["pg_long_queries"] = n
        if n > 0:
            warnings.append(f"PostgreSQL: {n} queries running >5 min")

    # Idle in transaction
    idle_tx = run_cmd(f"""{PSQL} -d agentindex -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='agentindex' AND state = 'idle in transaction' AND query_start < now() - interval '2 minutes';" """)
    if idle_tx:
        n = int(idle_tx.strip())
        checks["pg_idle_tx"] = n
        if n > 2:
            warnings.append(f"PostgreSQL: {n} idle-in-transaction >2 min")

    # Locks
    locks = run_cmd(f"""{PSQL} -d agentindex -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='agentindex' AND wait_event_type = 'Lock';" """)
    if locks:
        n = int(locks.strip())
        checks["pg_locks"] = n
        metrics["pg_locks"] = n
        if n > 3:
            errors.append(f"PostgreSQL: {n} waiting on locks!")
        elif n > 0:
            warnings.append(f"PostgreSQL: {n} waiting on locks")

    # ── 2. Agent count ──
    agent_count = run_cmd(f'{PSQL} -d agentindex -t -c "SELECT count(*) FROM agents WHERE is_active = true;"', timeout=30)
    if agent_count:
        n = int(agent_count.strip())
        checks["active_agents"] = n
        metrics["active_agents"] = n
        if n < 4_000_000:
            errors.append(f"Agent count dropped to {n:,} (<4M = critical)")
        elif n < 4_500_000:
            warnings.append(f"Agent count {n:,} (<4.5M = declining)")

    # ── 3. Ports ──
    api_status = check_port(8000)
    checks["api_port_8000"] = api_status
    if api_status != "200":
        errors.append(f"API port 8000 → {api_status}")

    mcp_status = check_port(8300)
    checks["mcp_port_8300"] = mcp_status
    # MCP returns 404 on / which is OK (it's SSE)
    if mcp_status == "000":
        warnings.append(f"MCP port 8300 not responding")

    # ── 4. Process counts ──
    procs = {
        "api": "discovery:app",
        "orchestrator": "agentindex.run",
        "parser": "run_parser_loop",
        "dashboard": "agentindex.dashboard",
        "mcp_sse": "mcp_sse_server",
        "cloudflared": "cloudflared",
    }
    for name, grep_str in procs.items():
        count = run_cmd(f"ps aux | grep '{grep_str}' | grep -v grep | wc -l")
        n = int(count.strip()) if count else 0
        checks[f"proc_{name}"] = n
        if n == 0:
            errors.append(f"Process {name} is NOT running")
        elif n > 1:
            warnings.append(f"Process {name} has {n} instances (expected 1)")

    # Check parser not suspended
    parser_state = run_cmd("ps aux | grep 'run_parser_loop' | grep -v grep | awk '{print $8}'")
    if parser_state and "T" in parser_state:
        errors.append("Parser is SUSPENDED (state T) — not processing")

    # ── 5. Disk ──
    disk_pct = run_cmd("df -h / | tail -1 | awk '{print $5}' | tr -d '%'")
    if disk_pct:
        n = int(disk_pct)
        checks["disk_pct"] = n
        metrics["disk_pct"] = n
        if n > 90:
            errors.append(f"Disk {n}% full!")
        elif n > 75:
            warnings.append(f"Disk {n}% full")

    # ── 6. Redis ──
    redis_ok = run_cmd("/opt/homebrew/bin/redis-cli ping")
    checks["redis"] = redis_ok
    if redis_ok != "PONG":
        warnings.append("Redis not responding")

    # ── 7. Ollama ──
    ollama = run_cmd("curl -s -m 3 http://localhost:11434/api/tags")
    if ollama:
        try:
            models = len(json.loads(ollama).get("models", []))
            checks["ollama_models"] = models
        except:
            checks["ollama_models"] = 0
            warnings.append("Ollama responded but can't parse models")
    else:
        checks["ollama_models"] = 0
        warnings.append("Ollama not responding")

    # ── 8. Tunnel ──
    tunnel_ok = run_cmd("curl -s -m 10 -o /dev/null -w '%{http_code}' https://nerq.ai/", timeout=15)
    checks["tunnel_nerq_ai"] = tunnel_ok
    if tunnel_ok != "200":
        errors.append(f"nerq.ai not accessible ({tunnel_ok})")

    # ── Verdict ──
    if errors:
        status = "ERROR"
    elif warnings:
        status = "WARNING"
    else:
        status = "HEALTHY"

    return {
        "timestamp": now,
        "status": status,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "metrics": metrics,
    }


def save_results(conn, results):
    conn.execute(
        "INSERT INTO healthcheck (timestamp, status, checks, warnings, errors) VALUES (?, ?, ?, ?, ?)",
        (results["timestamp"], results["status"],
         json.dumps(results["checks"]),
         json.dumps(results["warnings"]),
         json.dumps(results["errors"]))
    )
    for metric, value in results["metrics"].items():
        conn.execute(
            "INSERT INTO healthcheck_metrics (timestamp, metric, value) VALUES (?, ?, ?)",
            (results["timestamp"], metric, value)
        )
    conn.commit()


def run_zarq_checks():
    """Run ZARQ-specific healthchecks (pipeline staleness, trust score age, etc.)."""
    try:
        from zarq_healthcheck import run_checks as zarq_run, save_results as zarq_save
        zarq_results = zarq_run()
        zarq_save(zarq_results)
        for w in zarq_results["warnings"]:
            log(f"[ZARQ] {w}", "WARN")
        for e in zarq_results["errors"]:
            log(f"[ZARQ] {e}", "ERROR")
        return zarq_results
    except Exception as e:
        log(f"ZARQ healthcheck failed: {e}", "ERROR")
        return None


def main():
    conn = init_db()
    results = run_checks()

    # Run ZARQ-specific checks
    zarq_results = run_zarq_checks()
    if zarq_results:
        # Merge ZARQ warnings/errors into main result
        results["warnings"].extend(f"[ZARQ] {w}" for w in zarq_results.get("warnings", []))
        results["errors"].extend(f"[ZARQ] {e}" for e in zarq_results.get("errors", []))
        # Update status if ZARQ has issues
        if zarq_results.get("errors"):
            results["status"] = "ERROR"
        elif zarq_results.get("warnings") and results["status"] == "HEALTHY":
            results["status"] = "WARNING"

    # Print to stdout (goes to log)
    log(f"Status: {results['status']}")
    for w in results["warnings"]:
        log(w, "WARN")
    for e in results["errors"]:
        log(e, "ERROR")
    log(f"Checks: {json.dumps(results['checks'])}")

    save_results(conn, results)
    conn.close()

    # Exit code for monitoring
    if results["errors"]:
        sys.exit(2)
    elif results["warnings"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
