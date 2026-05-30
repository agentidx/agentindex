#!/usr/bin/env python3
"""
Infrastructure healthcheck — Postgres reachability surface.

Three layers of probe per configured pool:

1. TCP probe (fast):     can we connect to host:port at all?
2. SELECT 1 probe (4s):  does PG actually execute SQL? Catches the
                          per-query saturation pattern that R-SW (the
                          2026-05-30 software_registry incident) exposed
                          — TCP-only probes returned OK while every
                          actual query was timing out.
3. Trend probe (every Nth pass): records the SELECT 1 latency, alerts
                                  if the rolling median goes above 500 ms.

Failures open a row in zarq.infrastructure_alerts; the next successful
probe of the same kind closes it. The `service` field encodes both pool
name and failure_mode so layers don't shadow each other (a TCP_DOWN alert
and a SLOW_QUERY alert on the same host stay distinct rows).

Schema: zarq.infrastructure_alerts. One OPEN row per (host, port, service)
enforced by a partial unique index — re-probing a still-failing target bumps
last_seen_at + probe_count instead of inserting duplicates.

Exits 0 on every probe pass, success or fail; the LaunchAgent doesn't need to
restart on findings.
"""

import os
import re
import socket
import statistics
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg2
except ImportError:
    sys.stderr.write("psycopg2 not installed in this venv\n")
    sys.exit(2)


PGBOUNCER_INI = os.environ.get(
    "PGBOUNCER_INI", "/opt/homebrew/etc/pgbouncer.ini"
)
ALERT_DSN = os.environ.get(
    "INFRA_ALERT_DSN",
    "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio",
)
PROBE_TIMEOUT = float(os.environ.get("INFRA_PROBE_TIMEOUT", "4"))
SELECT1_TIMEOUT_S = float(os.environ.get("INFRA_SELECT1_TIMEOUT", "3"))
SLOW_TREND_THRESHOLD_MS = float(os.environ.get("INFRA_SLOW_TREND_MS", "500"))
TREND_WINDOW = int(os.environ.get("INFRA_TREND_WINDOW", "10"))
TREND_STATE_FILE = Path(
    os.environ.get("INFRA_TREND_STATE", "/tmp/infra_healthcheck_trend.json")
)


# ─────────────────────────────────────────────────────────────
# Parse pgbouncer.ini → list of (service, host, port)
# ─────────────────────────────────────────────────────────────
def parse_pgbouncer_targets(ini_path):
    """Return [(service_name, host, port), …] from the [databases] block.

    pgbouncer.ini uses INI sections with k=v lines whose value is a
    space-separated parameter list. We pull the host= and port= tokens; if a
    pool line omits them, it implies the local Unix socket (skip).
    """
    if not os.path.exists(ini_path):
        return []
    targets = []
    in_db = False
    with open(ini_path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith(";") or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                in_db = (line == "[databases]")
                continue
            if not in_db or "=" not in line:
                continue
            name, _, rhs = line.partition("=")
            name = name.strip()
            host_m = re.search(r"host=([^\s]+)", rhs)
            if not host_m:
                # Unix socket pool — nothing to probe at TCP level
                continue
            port_m = re.search(r"port=(\d+)", rhs)
            host = host_m.group(1)
            port = int(port_m.group(1)) if port_m else 5432
            targets.append((name, host, port))
    return targets


# ─────────────────────────────────────────────────────────────
# Probe one host:port
# ─────────────────────────────────────────────────────────────
def probe(host, port, timeout=PROBE_TIMEOUT):
    """TCP-only probe. Returns (ok: bool, error_msg: str)."""
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except OSError as e:
        elapsed = time.time() - t0
        return False, f"{type(e).__name__}: {e} (after {elapsed:.2f}s)"


def probe_select1(host, port, dbname, user, timeout=SELECT1_TIMEOUT_S):
    """Open a short-lived connection, SET statement_timeout, run SELECT 1.

    Returns (ok, error_msg, elapsed_ms, failure_mode). failure_mode is one
    of: '' (ok), 'SLOW_QUERY' (statement timeout), 'AUTH', 'SQL_ERROR',
    'CONN_ERROR'.
    """
    timeout_ms = int(timeout * 1000)
    t0 = time.time()
    try:
        conn = psycopg2.connect(
            host=host, port=port, dbname=dbname, user=user,
            connect_timeout=max(2, int(timeout))
        )
    except psycopg2.OperationalError as e:
        elapsed_ms = (time.time() - t0) * 1000
        msg = str(e).strip()
        mode = "AUTH" if "authentication" in msg.lower() else "CONN_ERROR"
        return False, msg[:300], elapsed_ms, mode

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
                cur.execute("SELECT 1")
                cur.fetchone()
    except psycopg2.errors.QueryCanceled as e:
        elapsed_ms = (time.time() - t0) * 1000
        return False, f"statement_timeout {timeout_ms}ms exceeded", elapsed_ms, "SLOW_QUERY"
    except Exception as e:
        elapsed_ms = (time.time() - t0) * 1000
        return False, f"{type(e).__name__}: {e}", elapsed_ms, "SQL_ERROR"
    finally:
        try:
            conn.close()
        except Exception:
            pass
    elapsed_ms = (time.time() - t0) * 1000
    return True, "", elapsed_ms, ""


# ─── Latency-trend state (persisted to /tmp) ────────────────────────────
def _load_trend_state() -> dict:
    if not TREND_STATE_FILE.exists():
        return {}
    try:
        import json
        return json.loads(TREND_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_trend_state(state: dict) -> None:
    import json
    try:
        TREND_STATE_FILE.write_text(json.dumps(state, indent=2))
    except OSError:
        pass


def update_trend(state: dict, host: str, port: int, elapsed_ms: float) -> float | None:
    """Push a sample into the rolling window for (host, port). Return the
    new median if we have at least TREND_WINDOW samples, else None.
    """
    key = f"{host}:{port}"
    samples = state.setdefault(key, [])
    samples.append(round(elapsed_ms, 1))
    if len(samples) > TREND_WINDOW:
        del samples[: len(samples) - TREND_WINDOW]
    if len(samples) < TREND_WINDOW:
        return None
    return statistics.median(samples)


# ─────────────────────────────────────────────────────────────
# Alert state transitions
# ─────────────────────────────────────────────────────────────
def open_or_bump_alert(cur, host, port, service, error_msg):
    """Open a new alert row, or bump last_seen_at + probe_count on the existing one."""
    cur.execute(
        """
        INSERT INTO zarq.infrastructure_alerts
            (host, port, service, severity, error_msg, last_seen_at, probe_count)
        VALUES (%s, %s, %s, 'critical', %s, now(), 1)
        ON CONFLICT (host, port, service) WHERE resolved_at IS NULL DO UPDATE
        SET last_seen_at = now(),
            probe_count  = zarq.infrastructure_alerts.probe_count + 1,
            error_msg    = EXCLUDED.error_msg
        RETURNING id, probe_count
        """,
        (host, port, service, error_msg),
    )
    return cur.fetchone()


def resolve_alert(cur, host, port, _service):
    """Mark every OPEN alert for this host:port as resolved.

    Resolve by (host, port), not (host, port, service) — if a pool was renamed
    in the ini, the old alert otherwise lingers forever after the host comes
    back. Returns list of (id, service, probe_count, open_duration).
    """
    cur.execute(
        """
        UPDATE zarq.infrastructure_alerts
        SET resolved_at = now()
        WHERE host=%s AND port=%s AND resolved_at IS NULL
        RETURNING id, service, probe_count, (now() - occurred_at)::text
        """,
        (host, port),
    )
    return cur.fetchall()


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def parse_target_db_user(rhs: str) -> tuple[str | None, str | None]:
    """Extract dbname=… and user=… from a pgbouncer.ini RHS string."""
    db_m = re.search(r"dbname=([^\s]+)", rhs)
    user_m = re.search(r"user=([^\s]+)", rhs)
    return (db_m.group(1) if db_m else None,
            user_m.group(1) if user_m else None)


def main():
    targets = parse_pgbouncer_targets(PGBOUNCER_INI)
    if not targets:
        print(f"[{datetime.now(timezone.utc).isoformat()}] no TCP targets in {PGBOUNCER_INI}", flush=True)
        return 0

    # Re-read the ini to extract dbname+user per pool for SELECT 1.
    # Cheap to re-parse — sub-millisecond at this file size.
    pool_db_user: dict[str, tuple[str | None, str | None]] = {}
    try:
        in_db = False
        for raw in Path(PGBOUNCER_INI).read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith((";", "#")):
                continue
            if line.startswith("[") and line.endswith("]"):
                in_db = (line == "[databases]")
                continue
            if not in_db or "=" not in line:
                continue
            name, _, rhs = line.partition("=")
            pool_db_user[name.strip()] = parse_target_db_user(rhs)
    except OSError:
        pass

    # Dedup TCP targets so the same host:port doesn't get probed twice
    by_endpoint = {}
    for service, host, port in targets:
        by_endpoint.setdefault((host, port), []).append(service)

    conn = psycopg2.connect(ALERT_DSN)
    conn.autocommit = False
    cur = conn.cursor()
    results = []
    trend_state = _load_trend_state()

    for (host, port), services in by_endpoint.items():
        service_name = ",".join(sorted(services))
        # ── Layer 1: TCP probe ────────────────────────────────────────
        tcp_svc = f"{service_name}|TCP_DOWN"
        ok_tcp, err_tcp = probe(host, port)
        if ok_tcp:
            closed = resolve_alert(cur, host, port, tcp_svc)
            for _id, svc, probes, dur in closed:
                results.append(f"RESOLVED {host}:{port} ({svc}) after {probes} probes / {dur}")
        else:
            row = open_or_bump_alert(cur, host, port, tcp_svc, err_tcp)
            tag = "OPENED" if row[1] == 1 else f"ONGOING #{row[1]}"
            results.append(f"{tag:9s} {host}:{port} ({tcp_svc}) — {err_tcp}")
            # If TCP is down, don't try the deeper probes — they'd just
            # add the same signal with extra noise.
            continue

        # ── Layer 2: SELECT 1 probe ──────────────────────────────────
        # Use the first service's pool's db+user, falling back to the
        # alert-DSN credentials if we couldn't parse a (db, user) for the
        # pool. agentindex is the canonical app DB; everything routes
        # through it.
        db_user = pool_db_user.get(services[0], (None, None))
        dbname = db_user[0] or "agentindex"
        user = db_user[1] or "anstudio"
        ok_sql, err_sql, elapsed_ms, failure_mode = probe_select1(
            host, port, dbname, user, timeout=SELECT1_TIMEOUT_S
        )
        sql_svc = f"{service_name}|{failure_mode or 'OK'}"
        if ok_sql:
            # Resolve any prior SLOW_QUERY / SQL_ERROR / AUTH / CONN_ERROR rows.
            for mode in ("SLOW_QUERY", "SQL_ERROR", "AUTH", "CONN_ERROR"):
                closed = resolve_alert(cur, host, port, f"{service_name}|{mode}")
                for _id, svc, probes, dur in closed:
                    results.append(f"RESOLVED {host}:{port} ({svc}) after {probes} probes / {dur}")
            results.append(f"ok       {host}:{port} ({service_name})  select1={elapsed_ms:.0f}ms")
        else:
            row = open_or_bump_alert(cur, host, port, sql_svc, err_sql)
            tag = "OPENED" if row[1] == 1 else f"ONGOING #{row[1]}"
            results.append(f"{tag:9s} {host}:{port} ({sql_svc}) — {err_sql}")
            continue   # don't push a slow-trend sample on a failing probe

        # ── Layer 3: latency-trend ───────────────────────────────────
        median_ms = update_trend(trend_state, host, port, elapsed_ms)
        trend_svc = f"{service_name}|SLOW_TRENDING"
        if median_ms is None:
            continue   # still warming the window
        if median_ms > SLOW_TREND_THRESHOLD_MS:
            err = f"rolling median {median_ms:.0f}ms over last {TREND_WINDOW} probes > {SLOW_TREND_THRESHOLD_MS:.0f}ms"
            row = open_or_bump_alert(cur, host, port, trend_svc, err)
            tag = "OPENED" if row[1] == 1 else f"ONGOING #{row[1]}"
            results.append(f"{tag:9s} {host}:{port} ({trend_svc}) — {err}")
        else:
            closed = resolve_alert(cur, host, port, trend_svc)
            for _id, svc, probes, dur in closed:
                results.append(f"RESOLVED {host}:{port} ({svc}) after {probes} probes / {dur}")

    _save_trend_state(trend_state)
    conn.commit()
    cur.close()
    conn.close()

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for line in results:
        print(f"[{ts}] {line}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # Healthcheck must never escape unhandled — its job is reporting, not crashing.
        sys.stderr.write(f"infra_healthcheck FAILED: {type(e).__name__}: {e}\n")
        sys.exit(1)
