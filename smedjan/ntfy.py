"""
Low-level ntfy.sh publisher. NO direct callers outside
smedjan/scripts/ntfy_action_required.py (or the Mac-Studio-side shim in
~/smedjan/scripts/). Task lifecycle events (done/claimed/blocked), worker
heartbeats, planner ticks, evidence emission — all telemetry — go to
the dashboard and logs, not here.

Allowed triggers are enumerated in ~/smedjan/runbooks/notifications.md.

This module keeps only:
  * `push(...)`                — raw HTTP helper (used by the wrapper)
  * `task_needs_approval(...)` — risk-gated; fires ntfy ONLY when risk=high,
                                 otherwise logs and returns. Kept so
                                 worker.py has a stable callsite.

Paid APIs are forbidden. Free-tier ntfy only.
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.request

from smedjan.config import NTFY_URL

log = logging.getLogger("smedjan.ntfy")


def push(title: str, body: str, *, priority: str = "default",
         tags: str = "hammer_and_wrench") -> bool:
    """Low-level ntfy POST. Direct callers are deprecated — route
    through smedjan.scripts.ntfy_action_required.alert() instead so the
    trigger-type is known and can override the kill-switch.

    Hard kill-switch: if ~/smedjan/config/ntfy_enabled.flag is missing,
    this call is suppressed (logged + returns True). No trigger context
    here means no override is possible — callers that need guaranteed
    delivery MUST use the action-required wrapper with a Trigger enum.
    """
    try:
        from smedjan.scripts.ntfy_action_required import ntfy_enabled
        if not ntfy_enabled(None):
            log.info("ntfy.push suppressed by kill-switch: %s", title)
            return True
    except Exception as e:  # noqa: BLE001 — wrapper import failure: fail-closed
        log.warning("ntfy.push kill-switch check failed (%s) — suppressing "
                    "to protect Anders from spam", e)
        return True
    try:
        req = urllib.request.Request(
            NTFY_URL,
            data=body.encode("ascii", errors="replace"),
            headers={
                "Title":    title.encode("ascii", errors="replace").decode("ascii"),
                "Priority": priority,
                "Tags":     tags,
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:  # noqa: BLE001
        log.warning("ntfy push failed (%s): %s", title, e)
        return False


def task_needs_approval(task_id: str, title: str, reason: str,
                        *, risk_level: str = "") -> None:
    """Fires ntfy ONLY when risk_level='high'. All other risk levels land
    in needs_approval silently — Anders sees them in the dashboard queue
    and acts on his own cadence. High-risk rows must page because they
    require start-at scheduling and won't proceed without him.
    """
    if risk_level != "high":
        log.info("needs_approval %s risk=%s (no page) — %s",
                 task_id, risk_level or "?", reason)
        return
    body = (
        f"{task_id} {title}\n"
        f"Reason: {reason}\n"
        f"Run: smedjan queue approve {task_id} --start-at <ISO>"
    )
    push(f"[SMEDJAN action-required] {task_id} needs approval (risk=high)",
         body, priority="high", tags="warning")
