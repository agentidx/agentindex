#!/usr/bin/env python3
"""
Infrastructure healthcheck — Postgres reachability surface.

Parses the active PgBouncer config to learn which Postgres hosts the system
actually depends on, then probes each :port with a short TCP connect. Failures
open a row in zarq.infrastructure_alerts; the next successful probe closes it.

Why this exists: PgBouncer's agentindex_write pool routed to a host whose PG
port had been closed for 25 days. Nothing alerted. Run this every 5 minutes
via LaunchAgent so the next such silent failure surfaces in minutes, not weeks.

Schema: zarq.infrastructure_alerts. One OPEN row per (host, port, service)
enforced by a partial unique index — re-probing a still-failing target bumps
last_seen_at + probe_count instead of inserting duplicates.

Exits 0 on every probe pass, success or fail; the LaunchAgent doesn't need to
restart on findings.
"""

import os
import re
import socket
import sys
import time
from datetime import datetime, timezone

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
    """Return (ok: bool, error_msg: str)."""
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except OSError as e:
        elapsed = time.time() - t0
        return False, f"{type(e).__name__}: {e} (after {elapsed:.2f}s)"


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
def main():
    targets = parse_pgbouncer_targets(PGBOUNCER_INI)
    if not targets:
        print(f"[{datetime.now(timezone.utc).isoformat()}] no TCP targets in {PGBOUNCER_INI}", flush=True)
        return 0

    # Dedup so the same host:port doesn't get probed twice when two pool names share it
    by_endpoint = {}
    for service, host, port in targets:
        by_endpoint.setdefault((host, port), []).append(service)

    conn = psycopg2.connect(ALERT_DSN)
    conn.autocommit = False
    cur = conn.cursor()
    results = []

    for (host, port), services in by_endpoint.items():
        ok, err = probe(host, port)
        service_name = ",".join(sorted(services))
        if ok:
            closed = resolve_alert(cur, host, port, service_name)
            if closed:
                for _id, svc, probes, dur in closed:
                    results.append(f"RESOLVED {host}:{port} ({svc}) after {probes} probes / {dur}")
            else:
                results.append(f"ok       {host}:{port} ({service_name})")
        else:
            row = open_or_bump_alert(cur, host, port, service_name, err)
            tag = "OPENED" if row[1] == 1 else f"ONGOING #{row[1]}"
            results.append(f"{tag:9s} {host}:{port} ({service_name}) — {err}")

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
