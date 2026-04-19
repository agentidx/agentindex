#!/usr/bin/env python3
"""ntfy_action_required.py — the ONLY sanctioned ntfy entry point.

Smedjan notification policy (see ~/smedjan/runbooks/notifications.md):
Anders only gets paged when a human decision or intervention is required.
Task lifecycle events, audits, backups, planner ticks, dashboard regens,
heartbeats — all telemetry — belong in the dashboard + logs, NOT in ntfy.

Allowed triggers (everything else is a bug, flagged in code review):

  1. HIGH_RISK_APPROVAL       task_id needs Anders' explicit approve
  2. L1_CANARY_REGRESSION     5xx spike or write-rate drop on L1 canary
  3. WORKER_DEAD_RECLAIM_FAIL worker >10 min silent AND reclaim didn't save it
  4. PAID_API_DETECTED        triple-defense breach (anthropic/openai/paid)
  5. GIT_PUSH_FAILED_3X       structural push failure after 3 retries
  6. INFRA_CRITICAL           disk >90%, DB pool exhausted, API down >10 min
  7. SACRED_BYTE_MUTATION     sacred-byte coverage below floor in deploy
  8. ACTIONABLE_RATIO_LOW     F1/F2/F3 actionable-ratio <10% over 24h

Callers:
    from smedjan.scripts.ntfy_action_required import alert, Trigger
    alert(Trigger.HIGH_RISK_APPROVAL, task_id="T042",
          title="enable payments", reason="risk=high, start-at=TODAY 22:00")

Anything that wants ntfy must go through `alert()`. The legacy
`smedjan.ntfy.push()` still exists but only as the low-level HTTP helper
this module calls; direct callers are lint-forbidden (grep for
`ntfy\\.push\\(` outside this file — should match only trigger helpers).
"""
from __future__ import annotations

import enum
import logging
import os
import sys
import urllib.error
import urllib.request

NTFY_TOPIC = os.environ.get("SMEDJAN_NTFY_TOPIC", "nerq-alerts")
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

log = logging.getLogger("smedjan.ntfy_action_required")


class Trigger(str, enum.Enum):
    HIGH_RISK_APPROVAL = "high_risk_approval"
    L1_CANARY_REGRESSION = "l1_canary_regression"
    WORKER_DEAD_RECLAIM_FAIL = "worker_dead_reclaim_fail"
    PAID_API_DETECTED = "paid_api_detected"
    GIT_PUSH_FAILED_3X = "git_push_failed_3x"
    INFRA_CRITICAL = "infra_critical"
    SACRED_BYTE_MUTATION = "sacred_byte_mutation"
    ACTIONABLE_RATIO_LOW = "actionable_ratio_low"


_PRIORITY = {
    Trigger.HIGH_RISK_APPROVAL: ("high", "warning"),
    Trigger.L1_CANARY_REGRESSION: ("urgent", "rotating_light"),
    Trigger.WORKER_DEAD_RECLAIM_FAIL: ("high", "warning"),
    Trigger.PAID_API_DETECTED: ("urgent", "rotating_light"),
    Trigger.GIT_PUSH_FAILED_3X: ("high", "warning"),
    Trigger.INFRA_CRITICAL: ("urgent", "rotating_light"),
    Trigger.SACRED_BYTE_MUTATION: ("urgent", "rotating_light"),
    Trigger.ACTIONABLE_RATIO_LOW: ("high", "warning"),
}


def _push(title: str, body: str, priority: str, tags: str) -> bool:
    try:
        req = urllib.request.Request(
            NTFY_URL,
            data=body.encode("ascii", errors="replace"),
            headers={
                "Title": title.encode("ascii", errors="replace").decode("ascii"),
                "Priority": priority,
                "Tags": tags,
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:  # noqa: BLE001 — ntfy must never crash the caller
        log.warning("ntfy push failed (%s): %s", title, exc)
        return False


def alert(trigger: Trigger, *, title: str, body: str) -> bool:
    """Send an action-required ntfy. Returns True on HTTP 200.

    Callers must supply the plain-English `title` and `body` themselves —
    this module enforces *which* triggers are allowed, not the wording.
    """
    if not isinstance(trigger, Trigger):
        raise ValueError(
            f"ntfy_action_required.alert called with non-Trigger: {trigger!r}. "
            "Add a new Trigger enum member or drop to logger.info()."
        )
    priority, tags = _PRIORITY[trigger]
    prefixed = f"[SMEDJAN action-required] {title}"
    return _push(prefixed, body, priority, tags)


# ── Convenience helpers for the 8 triggers ────────────────────────────────

def high_risk_approval(task_id: str, task_title: str, reason: str) -> bool:
    return alert(
        Trigger.HIGH_RISK_APPROVAL,
        title=f"{task_id} needs approval (risk=high)",
        body=(
            f"{task_id} {task_title}\n"
            f"Reason: {reason}\n"
            f"Run: smedjan queue approve {task_id} --start-at <ISO>"
        ),
    )


def l1_canary_regression(metric: str, detail: str) -> bool:
    return alert(
        Trigger.L1_CANARY_REGRESSION,
        title=f"L1 canary regression — {metric}",
        body=detail,
    )


def worker_dead_reclaim_fail(worker_id: str, age_minutes: int, task_id: str | None) -> bool:
    return alert(
        Trigger.WORKER_DEAD_RECLAIM_FAIL,
        title=f"worker {worker_id} dead {age_minutes}m + reclaim failed",
        body=f"worker={worker_id} task={task_id or '—'} age={age_minutes}min — manual intervention",
    )


def paid_api_detected(caller: str, api_name: str, detail: str = "") -> bool:
    return alert(
        Trigger.PAID_API_DETECTED,
        title=f"PAID API detected from {caller} -> {api_name}",
        body=(
            f"Triple-defense breach: {caller} attempted to call {api_name}. "
            f"{detail}\nKill the caller and audit env. Policy: max-sub + free-tier only."
        ),
    )


def git_push_failed_3x(branch: str, last_error: str) -> bool:
    return alert(
        Trigger.GIT_PUSH_FAILED_3X,
        title=f"git push to {branch} failed 3x",
        body=f"branch={branch}\nlast error: {last_error[:400]}",
    )


def infra_critical(what: str, detail: str) -> bool:
    return alert(
        Trigger.INFRA_CRITICAL,
        title=f"infra critical — {what}",
        body=detail,
    )


def sacred_byte_mutation(byte_name: str, coverage_pct: float, report_path: str) -> bool:
    return alert(
        Trigger.SACRED_BYTE_MUTATION,
        title=f"sacred byte {byte_name} breach ({coverage_pct:.1f}%)",
        body=f"coverage={coverage_pct:.2f}%. Report: {report_path}",
    )


def actionable_ratio_low(category: str, ratio_pct: float, lookback_days: int,
                         detail: str = "") -> bool:
    return alert(
        Trigger.ACTIONABLE_RATIO_LOW,
        title=f"{category} actionable-ratio {ratio_pct:.1f}% over {lookback_days}d",
        body=(
            f"{category}: actionable/completed = {ratio_pct:.1f}% "
            f"over last {lookback_days}d (threshold 10%). {detail}"
        ),
    )


if __name__ == "__main__":
    # Minimal CLI — useful for shell scripts and manual smoke-tests.
    # Usage: ntfy_action_required.py <trigger_name> <title> <body>
    if len(sys.argv) != 4:
        print(
            "usage: ntfy_action_required.py <trigger> <title> <body>\n"
            f"triggers: {', '.join(t.value for t in Trigger)}",
            file=sys.stderr,
        )
        sys.exit(2)
    trg = Trigger(sys.argv[1])
    ok = alert(trg, title=sys.argv[2], body=sys.argv[3])
    sys.exit(0 if ok else 1)
