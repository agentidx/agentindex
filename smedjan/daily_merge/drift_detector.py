"""Detect commits that ran in factory but never reached main's git-history.

Example: 6ce9974 (Anders' sync_agent_slugs COALESCE-fix from 2026-04-23) ran
against main-tree's auto_generate_pages.py 2026-04-24 (gave +24K slugs uplift)
but `git log main -- agentindex/auto_generate_pages.py` does not show it.
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass


@dataclass
class DriftFinding:
    file: str
    factory_only_hashes: list[str]
    factory_blob_sha: str
    main_blob_sha: str
    anomaly_type: str  # "blob-match-history-mismatch" | "blob-mismatch-needs-merge"


def _git_log_hashes(ref: str, path: str) -> set[str]:
    try:
        out = subprocess.check_output(
            ["git", "log", "--pretty=format:%h", ref, "--", path],
            text=True, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return set()
    return {h for h in out.splitlines() if h}


def _git_show_blob_sha(ref: str, path: str) -> str:
    try:
        content = subprocess.check_output(
            ["git", "show", f"{ref}:{path}"],
            text=False, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return ""
    return hashlib.sha256(content).hexdigest()[:16]


def detect_drift_for_file(path: str, base_ref: str = "main",
                          head_ref: str = "smedjan-factory-v0") -> DriftFinding | None:
    factory_hashes = _git_log_hashes(head_ref, path)
    main_hashes = _git_log_hashes(base_ref, path)
    only_factory = factory_hashes - main_hashes
    if not only_factory:
        return None

    factory_sha = _git_show_blob_sha(head_ref, path)
    main_sha = _git_show_blob_sha(base_ref, path)

    if factory_sha and main_sha and factory_sha == main_sha:
        anomaly = "blob-match-history-mismatch"
    else:
        anomaly = "blob-mismatch-needs-merge"

    return DriftFinding(
        file=path,
        factory_only_hashes=sorted(only_factory),
        factory_blob_sha=factory_sha,
        main_blob_sha=main_sha,
        anomaly_type=anomaly,
    )


def scan_paths(paths: list[str], base_ref: str = "main",
               head_ref: str = "smedjan-factory-v0") -> list[DriftFinding]:
    findings = []
    for p in paths:
        f = detect_drift_for_file(p, base_ref, head_ref)
        if f is not None:
            findings.append(f)
    return findings
