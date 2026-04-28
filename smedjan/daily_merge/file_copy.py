"""Sync smedjan/ tree files from factory → main.

Strategy: only copy files that touched by the picked-or-skipped commits,
not the entire tree. First-run will pull in transitive deps the cherry-pick
commits reference (planner.py, sources.py, factory_core.py, etc).
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .classifier import Commit


@dataclass
class FileCopyResult:
    copied: list[str] = field(default_factory=list)
    skipped_no_change: list[str] = field(default_factory=list)
    skipped_missing: list[str] = field(default_factory=list)


FACTORY_REPO = Path("/Users/anstudio/agentindex-factory")
MAIN_REPO = Path("/Users/anstudio/agentindex")


def files_to_sync(commits: list[Commit]) -> set[str]:
    """Collect smedjan/-files touched by any of the input commits."""
    out: set[str] = set()
    for c in commits:
        for f in c.files:
            if f.startswith("smedjan/"):
                out.add(f)
    return out


def sync_file(rel_path: str) -> str:
    """Copy `factory/rel_path` → `main/rel_path`. Return action taken."""
    src = FACTORY_REPO / rel_path
    dst = MAIN_REPO / rel_path

    if not src.exists():
        return "missing"

    if dst.exists() and src.read_bytes() == dst.read_bytes():
        return "no-change"

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return "copied"


def sync_files(rel_paths: set[str]) -> FileCopyResult:
    result = FileCopyResult()
    for p in sorted(rel_paths):
        action = sync_file(p)
        if action == "copied":
            result.copied.append(p)
        elif action == "no-change":
            result.skipped_no_change.append(p)
        elif action == "missing":
            result.skipped_missing.append(p)
    return result


def stage_and_commit(message: str) -> str | None:
    """git add + commit copied files. Returns short hash, or None if nothing changed."""
    subprocess.run(["git", "-C", str(MAIN_REPO), "add", "smedjan/"], check=True)
    rc = subprocess.run(
        ["git", "-C", str(MAIN_REPO), "diff", "--cached", "--quiet"],
        capture_output=True,
    ).returncode
    if rc == 0:
        return None  # nothing staged
    subprocess.run(
        ["git", "-C", str(MAIN_REPO), "commit", "-m", message],
        check=True, capture_output=True,
    )
    out = subprocess.check_output(
        ["git", "-C", str(MAIN_REPO), "rev-parse", "--short", "HEAD"],
        text=True,
    ).strip()
    return out
