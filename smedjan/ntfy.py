"""
Thin ntfy.sh publisher. Deliberately no dependencies beyond stdlib so the
worker can push even when the venv is degraded. Free tier — no paid APIs.
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.request

from smedjan.config import NTFY_URL

log = logging.getLogger("smedjan.ntfy")


def push(title: str, body: str, *, priority: str = "default", tags: str = "hammer_and_wrench") -> bool:
    """Fire-and-forget ntfy message. Returns True on HTTP 200, False otherwise.

    Messages are encoded as ASCII (latin-1 fallback) to avoid the occasional
    UnicodeEncodeError when the body contains stray non-ASCII from Postgres
    notes that came in from a web crawl.
    """
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
    except Exception as e:  # noqa: BLE001 — ntfy failures must never crash callers
        log.warning("ntfy push failed (%s): %s", title, e)
        return False


def task_done(task_id: str, title: str, output_paths: list[str]) -> None:
    body = f"{task_id} {title}\nOutputs: {', '.join(output_paths) if output_paths else '(none)'}"
    push(f"[SMEDJAN] {task_id} done", body, priority="default", tags="white_check_mark")


def task_blocked(task_id: str, title: str, reason: str) -> None:
    body = f"{task_id} {title}\nReason: {reason}"
    push(f"[SMEDJAN] {task_id} BLOCKED", body, priority="high", tags="no_entry")


def task_needs_approval(task_id: str, title: str, reason: str) -> None:
    body = (
        f"{task_id} {title}\n"
        f"Reason: {reason}\n"
        f"Run: smedjan queue approve {task_id}"
    )
    push(f"[SMEDJAN] {task_id} needs approval", body, priority="high", tags="warning")


def worker_up(worker_id: str, current_task: str | None) -> None:
    body = f"Worker {worker_id} live. Current task: {current_task or '(idle)'}"
    push("[SMEDJAN] worker started", body, priority="default", tags="hammer_and_wrench")
