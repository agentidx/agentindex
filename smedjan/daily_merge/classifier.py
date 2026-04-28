"""Classify factory-only commits into A/B/C/D/E categories.

A — feat: cherry-pick (production-impactful)
B — fix:  cherry-pick (production-impactful)
C — refactor: cherry-pick after review
D — worker-internal: file-copy if module module-touched, else skip
E — noise: skip permanent (audit-spam, FB-F*, docs, chore)
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class Commit:
    hash: str
    short: str
    subject: str
    files: list[str] = field(default_factory=list)
    category: str = ""
    reason: str = ""

    @property
    def touches_agentindex(self) -> bool:
        return any(
            f.startswith("agentindex/") or f.startswith("static/") or f.startswith("tests/")
            for f in self.files
        )

    @property
    def smedjan_only(self) -> bool:
        return bool(self.files) and all(f.startswith("smedjan/") for f in self.files)


_NOISE_PREFIXES = ("audit(", "audit:", "docs:", "docs(", "chore:", "chore(")
_FB_AUDIT_RE = re.compile(r"\bfb-f[123]-\d+", re.IGNORECASE)
_SMEDJAN_INTERNAL_FILES = (
    "smedjan/planner.py", "smedjan/worker.py", "smedjan/factory_core.py",
    "smedjan/sources.py", "smedjan/config.py", "smedjan/cli.py",
    "smedjan/ntfy.py", "smedjan/backlog_seeder.py",
    "smedjan/fallback_generator.py", "smedjan/yield_estimator.py",
    "smedjan/session_budget.py", "smedjan/emit_evidence.py",
    "smedjan/scripts/", "smedjan/audits/", "smedjan/audit-reports/",
    "smedjan/measurement/", "smedjan/observations/",
    "smedjan/com.nerq.smedjan.",  # plist-files
)


def classify_commit(c: Commit) -> Commit:
    s = c.subject.lower()

    # E: noise
    for p in _NOISE_PREFIXES:
        if c.subject.startswith(p):
            c.category, c.reason = "E", f"prefix:{p.rstrip('(:')}"
            return c
    if _FB_AUDIT_RE.search(s) and "audit" in s:
        c.category, c.reason = "E", "fb-audit"
        return c

    # D: worker-internal — only smedjan files (no agentindex touch)
    if c.smedjan_only:
        c.category, c.reason = "D", "smedjan-only-files"
        return c

    # B: fix
    if c.subject.startswith("fix(") or c.subject.startswith("fix:"):
        c.category, c.reason = "B", "fix-prefix"
        return c

    # C: refactor
    if c.subject.startswith("refactor(") or c.subject.startswith("refactor:"):
        c.category, c.reason = "C", "refactor-prefix"
        return c

    # A: feat
    if c.subject.startswith("feat(") or c.subject.startswith("feat:"):
        c.category, c.reason = "A", "feat-prefix"
        return c

    # Worker-output (smedjan-prefixed) that touches agentindex/ → A or B
    if c.subject.startswith("smedjan ") or c.subject.startswith("smedjan:"):
        if c.touches_agentindex:
            if "fix" in s:
                c.category, c.reason = "B", "smedjan-fix"
            else:
                c.category, c.reason = "A", "smedjan-feat"
            return c
        c.category, c.reason = "D", "smedjan-prefix-no-agentindex"
        return c

    # Anything else touching agentindex/ counts as A
    if c.touches_agentindex:
        c.category, c.reason = "A", "agentindex-touch-fallback"
        return c

    c.category, c.reason = "D", "other"
    return c


def fetch_commits(base_ref: str = "main", head_ref: str = "smedjan-factory-v0") -> list[Commit]:
    """Return all commits in head_ref that are not on base_ref, oldest first."""
    out = subprocess.check_output(
        ["git", "log", "--reverse", f"{base_ref}..{head_ref}", "--pretty=format:%H|%s"],
        text=True,
    )
    commits = []
    for line in out.splitlines():
        if "|" not in line:
            continue
        h, subj = line.split("|", 1)
        files_out = subprocess.check_output(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", h],
            text=True,
        )
        files = [f for f in files_out.strip().splitlines() if f.strip()]
        commits.append(Commit(hash=h, short=h[:7], subject=subj, files=files))
    return commits


def classify_all(commits: Iterable[Commit]) -> list[Commit]:
    return [classify_commit(c) for c in commits]


def summarize(commits: list[Commit]) -> dict:
    """Return {'A': [...], 'B': [...], 'C': [...], 'D': [...], 'E': [...]}."""
    out: dict = {k: [] for k in "ABCDE"}
    for c in commits:
        out[c.category].append(c)
    return out
