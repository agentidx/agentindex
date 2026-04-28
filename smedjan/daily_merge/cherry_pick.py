"""Cherry-pick A/B commits from factory-v0 → main, skip on conflict.

Each conflict is logged with reason. Caller decides whether to halt or
continue with --skip.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
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
