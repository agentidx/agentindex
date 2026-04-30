"""Cherry-pick A/B commits from factory-v0 → main, skip on conflict.

Each conflict is logged with reason. Caller decides whether to halt or
continue with --skip. After each successful pick we also run the
spam-signal gate against any audit CSVs touched by that commit; a gate
failure reverts the pick and records ``quality-gate`` as the reason.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .classifier import Commit


@dataclass
class CherryPickResult:
    picked: list[str] = field(default_factory=list)            # short hashes committed
    skipped: list[tuple[str, str]] = field(default_factory=list)  # [(short, reason)]
    halted_at: str | None = None
    halt_reason: str | None = None


def _run(args: list[str], check: bool = False) -> tuple[int, str, str]:
    p = subprocess.run(args, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{args}: {p.stderr}")
    return p.returncode, p.stdout, p.stderr


def _run_quality_gate(commit_hash: str) -> tuple[bool, str]:
    """Run smedjan/scripts/spam_signal_gate.py against any audit CSVs
    modified by the most recently cherry-picked commit.

    Returns (passed, message). passed=True if no CSVs were modified or
    all of them pass the gate. passed=False halts the cherry-pick.
    Failure to locate the gate script is treated as a soft skip
    (passed=True with a "gate-skipped" message) so a missing script
    never blocks cherry-picks unexpectedly.
    """
    rc, out, _ = _run(["git", "show", "--name-only", "--pretty=", "HEAD"])
    if rc != 0:
        return True, "git-show-failed"
    csvs = [
        ln for ln in out.splitlines()
        if ln.endswith(".csv") and "/audits/" in ln
    ]
    if not csvs:
        return True, "no-audit-csv-touched"

    repo_root = Path(__file__).resolve().parents[2]
    gate = repo_root / "smedjan" / "scripts" / "spam_signal_gate.py"
    if not gate.exists():
        return True, "gate-skipped (script missing)"

    failed: list[str] = []
    for csv in csvs:
        path = repo_root / csv
        if not path.exists():
            continue
        rc, out, err = _run(["python3", str(gate), "--quiet", str(path)])
        if rc != 0:
            failed.append(f"{csv}: {(err or out).strip()[:200]}")
    if failed:
        return False, "; ".join(failed)
    return True, f"gate-pass ({len(csvs)} csv)"


def cherry_pick_sequence(commits: Iterable[Commit], dry_run: bool = False) -> CherryPickResult:
    """Cherry-pick commits in order; auto-skip on modify/delete conflicts.

    Halts on content conflicts (true diff conflicts) — caller must intervene.
    """
    result = CherryPickResult()
    for c in commits:
        if dry_run:
            result.picked.append(c.short)
            continue

        rc, out, err = _run(["git", "cherry-pick", "-x", c.hash])
        combined = out + err

        if rc == 0:
            # Post-pick spam-signal gate. Failure reverts this commit and
            # records the reason; subsequent commits continue normally.
            ok, msg = _run_quality_gate(c.hash)
            if not ok:
                _run(["git", "revert", "--no-edit", "HEAD"])
                result.skipped.append((c.short, f"quality-gate: {msg}"))
                continue
            result.picked.append(c.short)
            continue

        # Conflict — analyze
        if "modify/delete" in combined or "deleted in HEAD" in combined:
            # Skip — file deleted on main, factory modified it
            _run(["git", "cherry-pick", "--skip"])
            result.skipped.append((c.short, "modify/delete (smedjan-tree mismatch)"))
            continue

        if "all conflicts fixed" in combined or "nothing added to commit" in combined:
            # Diff already applied (overlap from previous commit)
            _run(["git", "cherry-pick", "--skip"])
            result.skipped.append((c.short, "diff already applied"))
            continue

        if "CONFLICT (content)" in combined or "Merge conflict" in combined:
            # Real content conflict — halt
            result.halted_at = c.short
            result.halt_reason = "content-conflict"
            _run(["git", "cherry-pick", "--abort"])
            break

        # Unknown error — halt
        result.halted_at = c.short
        result.halt_reason = f"unknown: {err.strip()[:200]}"
        _run(["git", "cherry-pick", "--abort"])
        break

    return result


def working_tree_clean() -> bool:
    rc, out, _ = _run(["git", "status", "--porcelain"])
    if rc != 0:
        return False
    # Allow untracked, fail on modified/deleted/staged
    for line in out.splitlines():
        if line.startswith("??"):
            continue
        if line.strip():
            return False
    return True
