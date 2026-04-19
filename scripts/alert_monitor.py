#!/usr/bin/env python3
"""
Alert Monitor — system-level infra checks, gated by the Smedjan
action-required policy (~/smedjan/runbooks/notifications.md).

Runs every 5 minutes. Fires ntfy ONLY under trigger #6 (INFRA_CRITICAL):
    * API unreachable (2 consecutive failures)
    * Disk >90% full

Historical checks (LaunchAgent failures, replication lag, ReadOnly
errors) were removed: they were either too noisy (agents flap on
restart, replication blips on snapshots) or did not map to the
8-trigger policy. Noise must go to dashboard + logs, not ntfy.
"""

import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, "/Users/anstudio/agentindex")

from smedjan.scripts import ntfy_action_required as _ar  # noqa: E402

DEDUP_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "logs", "alert_dedup.json")
DEDUP_WINDOW = 14400  # 4 hours — prevent alert storms from flapping agents


def _load_dedup():
    import json
    try:
        with open(DEDUP_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_dedup(data):
    import json
    os.makedirs(os.path.dirname(DEDUP_FILE), exist_ok=True)
    with open(DEDUP_FILE, "w") as f:
        json.dump(data, f)


def _page_infra(key: str, what: str, detail: str) -> None:
    """Dedup + page via the action-required wrapper."""
    dedup = _load_dedup()
    now = time.time()
    dedup = {k: v for k, v in dedup.items() if now - v < DEDUP_WINDOW}
    if key in dedup:
        return
    _ar.infra_critical(what=what, detail=detail)
    dedup[key] = now
    _save_dedup(dedup)


_api_fail_count = 0


def check_api():
    """Page only after 2 consecutive failures to avoid single-probe flaps."""
    global _api_fail_count
    try:
        req = urllib.request.Request("http://localhost:8000/v1/health")
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                _api_fail_count = 0
                return
            _api_fail_count += 1
    except Exception as e:
        _api_fail_count += 1
        if _api_fail_count >= 2:
            _page_infra(
                key="api_unreachable",
                what="Nerq API unreachable",
                detail=f"localhost:8000 failed {_api_fail_count}x: {e}",
            )


def check_disk():
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True,
                                text=True, timeout=5)
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                pct = int(parts[4].rstrip("%"))
                if pct > 90:
                    _page_infra(
                        key="disk_full",
                        what="Disk >90% full",
                        detail=f"/ is {pct}% full",
                    )
    except Exception:
        pass


def main():
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Running alert monitor...")
    check_api()
    check_disk()
    print("  Checks complete.")


if __name__ == "__main__":
    main()
