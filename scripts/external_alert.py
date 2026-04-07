#!/usr/bin/env python3
"""
External alert — sends push notification if system is down.
Runs every 5 minutes via cron. Uses ntfy.sh (free, no signup).
Install ntfy app on phone and subscribe to topic "nerq-alerts".
"""
import json
import os
import time
import urllib.request
import urllib.error

STATE_FILE = os.path.expanduser("~/agentindex/logs/alert_state.json")
NTFY_TOPIC = "nerq-alerts"


def _post_ntfy(msg, priority="default", tags="warning"):
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=msg.encode(),
            headers={"Priority": priority, "Tags": tags},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
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
        if consecutive >= 3:
            _post_ntfy(
                f"NERQ RECOVERED after {consecutive} failures ({consecutive * 5}min downtime)",
                priority="default", tags="white_check_mark"
            )
        state["consecutive_fails"] = 0
    else:
        consecutive += 1
        state["consecutive_fails"] = consecutive
        details = f"API={'OK' if api_ok else 'DOWN'}, Redis={'OK' if redis_ok else 'DOWN'}"

        if consecutive == 3:
            _post_ntfy(
                f"NERQ DOWN: {details} ({consecutive * 5}min)",
                priority="urgent", tags="rotating_light"
            )
        elif consecutive > 3 and consecutive % 12 == 0:
            _post_ntfy(
                f"NERQ STILL DOWN: {details} ({consecutive * 5}min)",
                priority="high", tags="warning"
            )

    state["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["api"] = api_ok
    state["redis"] = redis_ok

    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


if __name__ == "__main__":
    check_and_alert()
