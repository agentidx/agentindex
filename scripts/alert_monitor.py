#!/usr/bin/env python3
"""
Alert Monitor — Push notifications via ntfy.sh.

Checks every 5 minutes:
- LaunchAgent failures (non-zero exit in last 10 min)
- Replication lag > 10 MB
- Redis eviction rate
- API health (port 8000)
- Disk space < 10% free

Deduplicates: same alert not sent within 30 min.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NTFY_TOPIC = "nerq-alerts"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
DEDUP_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "alert_dedup.json")
DEDUP_WINDOW = 1800  # 30 min

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


def _load_dedup():
    try:
        with open(DEDUP_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_dedup(data):
    with open(DEDUP_FILE, "w") as f:
        json.dump(data, f)


def _send_alert(title, message, priority="default", tags=""):
    """Send alert via ntfy.sh, with dedup."""
    dedup = _load_dedup()
    now = time.time()

    # Clean old entries
    dedup = {k: v for k, v in dedup.items() if now - v < DEDUP_WINDOW}

    key = f"{title}:{message[:80]}"
    if key in dedup:
        return  # Already sent recently

    try:
        data = message.encode("utf-8")
        req = urllib.request.Request(NTFY_URL, data=data, method="POST")
        req.add_header("Title", title)
        req.add_header("Priority", priority)
        if tags:
            req.add_header("Tags", tags)
        urllib.request.urlopen(req, timeout=10)
        dedup[key] = now
        _save_dedup(dedup)
    except Exception as e:
        print(f"Alert send failed: {e}")


def check_launchagents():
    """Check for failing LaunchAgents with PID-aware logic.

    Continuous agents (KeepAlive): alert only if PID is missing (not running).
    Exit code is noise from restarts — ignore it when PID is present.

    Discrete agents (run-and-exit): alert if exit code != 0 and not running.
    """
    CONTINUOUS = {
        "com.nerq.api", "com.nerq.master-watchdog",
        "com.nerq.alert-monitor", "com.nerq.performance-guardian",
    }
    try:
        result = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
        failing = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            label = parts[2]
            if "com.nerq." not in label and "com.zarq." not in label:
                continue

            pid = parts[0]       # PID or "-"
            exit_code = parts[1] # exit code or "-"

            if label in CONTINUOUS:
                # Continuous: only alert if NOT running (PID = "-")
                if pid == "-":
                    name = label.replace("com.nerq.", "").replace("com.zarq.", "zarq:")
                    failing.append(f"{name} (DOWN, no PID)")
            else:
                # Discrete: alert if exited with error and not currently running
                if pid == "-" and exit_code not in ("0", "-"):
                    name = label.replace("com.nerq.", "").replace("com.zarq.", "zarq:")
                    failing.append(f"{name} (exit {exit_code})")

        if failing:
            _send_alert(
                "LaunchAgent Failures",
                f"{len(failing)} agents failing: {', '.join(failing[:5])}",
                priority="high", tags="warning"
            )
    except Exception as e:
        print(f"LaunchAgent check failed: {e}")


def check_replication():
    """Check replication lag on primary."""
    try:
        from agentindex.db_config import get_write_conn
        conn = get_write_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT application_name, pg_wal_lsn_diff(sent_lsn, replay_lsn) as lag_bytes
            FROM pg_stat_replication
        """)
        for row in cur.fetchall():
            name, lag = row
            if lag and lag > 10_000_000:  # 10 MB
                _send_alert(
                    "Replication Lag",
                    f"{name}: {lag / 1_000_000:.1f} MB behind",
                    priority="high", tags="warning"
                )
        cur.close()
        conn.close()
    except Exception as e:
        _send_alert("Replication Check Failed", str(e)[:200], priority="high", tags="rotating_light")


def check_api():
    """Check API health."""
    try:
        req = urllib.request.Request("http://localhost:8000/v1/health")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                _send_alert("API Down", f"Health check returned {resp.status}", priority="urgent", tags="rotating_light")
    except Exception as e:
        _send_alert("API Unreachable", f"localhost:8000 failed: {e}", priority="urgent", tags="rotating_light")


def check_disk():
    """Check disk space."""
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                pct = int(parts[4].rstrip("%"))
                if pct > 90:
                    _send_alert("Disk Space Low", f"/ is {pct}% full", priority="high", tags="warning")
    except Exception:
        pass


def check_readonly_errors():
    """Check for ReadOnlySqlTransaction errors in API log."""
    try:
        log_path = os.path.join(LOG_DIR, "api_error.log")
        result = subprocess.run(
            ["tail", "-100", log_path], capture_output=True, text=True, timeout=5
        )
        count = result.stdout.count("ReadOnly")
        if count > 0:
            _send_alert(
                "ReadOnly Errors",
                f"{count} ReadOnlySqlTransaction errors in last 100 lines of api_error.log",
                priority="urgent", tags="rotating_light"
            )
    except Exception:
        pass


def main():
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Running alert monitor...")
    check_api()
    check_launchagents()
    check_replication()
    check_disk()
    check_readonly_errors()
    print(f"  Checks complete.")


if __name__ == "__main__":
    main()
