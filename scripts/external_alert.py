#!/usr/bin/env python3
"""
External alert — sends push notification if Nerq API/Redis is down.
Runs every 5 minutes via cron. Gated by the Smedjan action-required
policy (trigger #6, INFRA_CRITICAL). Only fires after 3 consecutive
failures (15 min sustained) to avoid single-probe flaps.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, "/Users/anstudio/agentindex")

from smedjan.scripts import ntfy_action_required as _ar  # noqa: E402

STATE_FILE = os.path.expanduser("~/agentindex/logs/alert_state.json")


def _page_down(what: str, detail: str) -> None:
    _ar.infra_critical(what=what, detail=detail)


def _page_recovery(detail: str) -> None:
    # Recovery is telemetry, not action-required — log only.
    # (Anders already knows he paid attention; the dashboard shows green.)
    pass


def _check_health():
    """Returns (api_ok, redis_ok)."""
    api_ok = False
    try:
        req = urllib.request.Request("http://localhost:8000/v1/health")
        resp = urllib.request.urlopen(req, timeout=10)
        api_ok = resp.status == 200
    except Exception:
        pass

    redis_ok = False
    try:
        import subprocess
        result = subprocess.run(
            ["/opt/homebrew/bin/redis-cli", "ping"],
            capture_output=True, text=True, timeout=5
        )
        redis_ok = result.stdout.strip() == "PONG"
    except Exception:
        pass

    return api_ok, redis_ok


def check_and_alert():
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                state = json.load(f)
        except Exception:
            state = {}

    api_ok, redis_ok = _check_health()
    consecutive = state.get("consecutive_fails", 0)

    if api_ok and redis_ok:
        # Recovery is silent — green on dashboard is the signal.
        state["consecutive_fails"] = 0
    else:
        consecutive += 1
        state["consecutive_fails"] = consecutive
        details = f"API={'OK' if api_ok else 'DOWN'}, Redis={'OK' if redis_ok else 'DOWN'}"

        # Page at 3rd consecutive fail (15 min sustained), then every
        # hour while still down. All of these are INFRA_CRITICAL #6.
        if consecutive == 3:
            _page_down("Nerq down", f"{details} ({consecutive * 5}min sustained)")
        elif consecutive > 3 and consecutive % 12 == 0:
            _page_down(
                "Nerq still down",
                f"{details} (still down after {consecutive * 5}min)",
            )

    state["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["api"] = api_ok
    state["redis"] = redis_ok

    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


if __name__ == "__main__":
    check_and_alert()
