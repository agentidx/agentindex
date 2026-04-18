"""
Smedjan worker loop — Phase-A STUB.

Phase A ships the skeleton only: the claim-side SQL + subprocess-shaped
invocation + heartbeat + log format + ntfy hooks. `claude` is NOT actually
invoked until Phase B (after 2026-04-20 13:34 local, once the L1 canary
observation window closes and Anders approves activation).

Why a stub now? So the factory_core / CLI / schema / seed-tasks can land
on `smedjan-factory-v0` and get reviewed without touching production
state. The LaunchAgent plist is also prepared but intentionally NOT loaded.

Activation (Phase B):
    1. Anders reviews commits on `smedjan-factory-v0`, merges to main
    2. Remove the `--dry-run` default or set SMEDJAN_WORKER_DRY_RUN=0
    3. `launchctl load -w ~/Library/LaunchAgents/com.nerq.smedjan.worker.plist`
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from smedjan import factory_core, ntfy
from smedjan.config import (
    CLAUDE_CLI,
    CLAUDE_MODEL,
    WORKER_CLAIM_TTL_MINUTES,
    WORKER_DRY_RUN_DEFAULT,
    WORKER_IDLE_SLEEP_SECONDS,
    WORKER_LOGDIR,
    WORKER_MAX_TASK_SECONDS,
)

WORKER_ID = os.environ.get("SMEDJAN_WORKER_ID", f"{socket.gethostname()}:{os.getpid()}")


# ── logging ──────────────────────────────────────────────────────────────

def _logger() -> logging.Logger:
    WORKER_LOGDIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    path = WORKER_LOGDIR / f"{day}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(path)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root = logging.getLogger("smedjan.worker")
    root.setLevel(logging.INFO)
    # Avoid duplicate handlers on module reload.
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(path) for h in root.handlers):
        root.addHandler(fh)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers):
        root.addHandler(sh)
    return root


LOG = _logger()


# ── prompt assembly ──────────────────────────────────────────────────────

def build_prompt(task: factory_core.Task) -> str:
    """Compose the self-contained prompt handed to `claude` per task.

    Per the task-description contract, the task row itself must carry every
    piece of context the invocation needs (no implicit dependency on prior
    session state). This function just wraps the row in the structured-
    output protocol Anders chose: ---TASK_RESULT---/---END_TASK_RESULT---.
    """
    wl = ", ".join(task.whitelisted_files) if task.whitelisted_files else "(none declared)"
    deps = ", ".join(task.dependencies) if task.dependencies else "(none)"
    return f"""\
You are Smedjan factory worker, executing one queued task.

Task id       : {task.id}
Title         : {task.title}
Risk          : {task.risk_level}
Dependencies  : {deps}
Whitelisted   : {wl}
Session group : {task.session_group or '(none)'}

─── Description ───
{task.description}

─── Acceptance criteria ───
{task.acceptance_criteria}

─── Rules ───
- Only modify files listed under "Whitelisted" above, or paths clearly
  implied by the description. Any attempt to modify files on the forbidden
  list (api/main.py, alembic/, robots.txt, sitemap.xml, CLAUDE.md) must
  abort with STATUS: blocked.
- Paid APIs are forbidden (no Anthropic API direct, no OpenAI, no paid
  search). Use the Max-subscription Claude environment you are running in.
- When work is complete (or you need to pause), emit a *single* result
  block at the end of your final message:

    ---TASK_RESULT---
    STATUS: done|blocked|needs_approval
    OUTPUT_PATHS: <comma-separated paths you wrote/modified>
    EVIDENCE: <JSON with metrics, counts, commit SHAs — omit if nothing>
    NOTES: <1-3 sentences summarising what you did>
    ---END_TASK_RESULT---

- STATUS=blocked if you hit a forbidden file, a missing dep, or a required
  external signal not yet available. STATUS=needs_approval if the work
  exceeded the risk envelope (e.g. you discovered the task actually has
  production-deploy semantics). STATUS=done only when every acceptance
  criterion above is verifiably met.

Go.
"""


# ── subprocess wrapper ───────────────────────────────────────────────────

def invoke_claude(prompt: str, *, dry_run: bool, timeout_seconds: int) -> tuple[int, str, str]:
    """Run `claude` CLI with the prompt on stdin, return (rc, stdout, stderr).

    Phase A (dry_run=True): returns a canned stdout that the parser will
    reject, so no real execution occurs — the loop records the attempt but
    immediately marks the task as needs_approval with reason "dry-run".
    Phase B (dry_run=False): real subprocess.

    We never write the prompt to disk (it may contain file paths that are
    merely internal context); it is piped via stdin.
    """
    if dry_run:
        LOG.info("DRY RUN — would invoke %s with %d-char prompt", CLAUDE_CLI, len(prompt))
        return 0, "DRY_RUN_NO_EXECUTION", ""

    cmd = [CLAUDE_CLI]
    if CLAUDE_MODEL:
        cmd += ["--model", CLAUDE_MODEL]
    LOG.info("invoking: %s (timeout=%ds)", " ".join(cmd), timeout_seconds)
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", f"{CLAUDE_CLI} not found — is the CLI installed?"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout_seconds}s"


# ── main loop ────────────────────────────────────────────────────────────

def _run_once(dry_run: bool) -> bool:
    """Claim + execute one task. Returns True if a task was handled,
    False if the queue was empty."""
    task = factory_core.claim_next_task(WORKER_ID)
    if task is None:
        factory_core.heartbeat(WORKER_ID, None, "idle")
        return False

    factory_core.heartbeat(WORKER_ID, task.id, "running")
    LOG.info("claimed %s (%s) risk=%s", task.id, task.title, task.risk_level)

    prompt = build_prompt(task)
    rc, stdout, stderr = invoke_claude(prompt, dry_run=dry_run, timeout_seconds=WORKER_MAX_TASK_SECONDS)

    # Phase-A dry-run deliberately cannot reach 'done'.
    if dry_run:
        reason = "Phase-A dry-run — worker claimed but execution not activated (Phase B pending)."
        factory_core.mark_needs_approval(task.id, reason)
        ntfy.task_needs_approval(task.id, task.title, reason)
        LOG.info("dry-run mark_needs_approval %s", task.id)
        return True

    # Real-execution path (Phase B).
    if rc != 0:
        msg = f"claude CLI exit {rc}: {stderr[:400]}"
        factory_core.mark_blocked(task.id, msg)
        ntfy.task_blocked(task.id, task.title, msg)
        LOG.error("blocked %s — rc=%d", task.id, rc)
        return True

    try:
        parsed = factory_core.parse_task_result(stdout)
    except factory_core.ResultParseError as e:
        factory_core.mark_blocked(task.id, f"no result block: {e}")
        ntfy.task_blocked(task.id, task.title, f"no result block: {e}")
        LOG.error("blocked %s — parse failed: %s", task.id, e)
        return True

    status = parsed["status"]
    if status == "done":
        factory_core.mark_done(task.id, parsed["output_paths"], parsed["evidence"], parsed["notes"])
        ntfy.task_done(task.id, task.title, parsed["output_paths"])
        LOG.info("done %s — outputs=%s", task.id, parsed["output_paths"])
    elif status == "blocked":
        reason = parsed["notes"] or "worker reported blocked"
        factory_core.mark_blocked(task.id, reason)
        ntfy.task_blocked(task.id, task.title, reason)
        LOG.info("blocked %s — %s", task.id, reason)
    elif status == "needs_approval":
        reason = parsed["notes"] or "worker requested approval"
        factory_core.mark_needs_approval(task.id, reason)
        ntfy.task_needs_approval(task.id, task.title, reason)
        LOG.info("needs_approval %s — %s", task.id, reason)
    return True


def _install_signal_handlers() -> None:
    def _graceful(_signum, _frame):
        LOG.info("signal received — exiting after current iteration")
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("smedjan-worker")
    parser.add_argument("--dry-run", action="store_true", default=WORKER_DRY_RUN_DEFAULT,
                        help="do not invoke claude; mark claimed tasks needs_approval (Phase A default)")
    parser.add_argument("--once", action="store_true",
                        help="handle at most one task then exit (for dev testing)")
    parser.add_argument("--live", action="store_true",
                        help="force dry-run off; requires Phase B activation")
    args = parser.parse_args(argv)

    dry_run = False if args.live else args.dry_run

    _install_signal_handlers()
    ntfy.worker_up(WORKER_ID, None)
    LOG.info("worker %s started (dry_run=%s, claim_ttl=%dm)",
             WORKER_ID, dry_run, WORKER_CLAIM_TTL_MINUTES)

    try:
        while True:
            handled = _run_once(dry_run=dry_run)
            if args.once:
                return 0
            if not handled:
                time.sleep(WORKER_IDLE_SLEEP_SECONDS)
    except SystemExit:
        factory_core.heartbeat(WORKER_ID, None, "exited")
        return 0


if __name__ == "__main__":
    sys.exit(main())
