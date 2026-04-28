"""IndexNow-trigger för URL-impacting commits i Modell 3 daily-merge.

Körs efter cherry-pick + file-copy + smoke-test (innan canary). Triggar
auto_indexnow.py med cap 30K om någon picked commit rör URL-genererande
filer. Best-effort: IndexNow-fail blockar inte canary/run.

Daily-budget: kombination med 07:00 daily-jobb ger max ~230K/dygn vid
hög aktivitet. Den här triggern är capped vid 30K per run.
"""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .classifier import Commit


AUTO_INDEXNOW_BIN = Path("/Users/anstudio/agentindex/agentindex/auto_indexnow.py")
PYTHON = Path("/Users/anstudio/agentindex/venv/bin/python3")
LOG_DIR = Path("/Users/anstudio/smedjan/measurement")

# File patterns where a change implies new/changed URLs that need IndexNow ping.
_URL_IMPACT_PATTERNS = (
    re.compile(r"^agentindex/auto_generate_pages\.py$"),
    re.compile(r"^agentindex/api/main\.py$"),
    re.compile(r"^agentindex/api/discovery\.py$"),
    re.compile(r"^agentindex/api/endpoints/[^/]+\.py$"),
    re.compile(r"^agentindex/agent_safety_pages\.py$"),
    re.compile(r"^agentindex/seo_(programmatic|asset_pages|pages)\.py$"),
    re.compile(r".*sitemap.*\.(py|xml)$"),
    re.compile(r"^agentindex/agent_safety_slugs\.json$"),
    re.compile(r"^agentindex/mcp_server_slugs\.json$"),
    re.compile(r"^agentindex/crypto/token_slugs\.json$"),
)


@dataclass
class IndexNowResult:
    triggered: bool = False
    reason: str = ""           # Why triggered (or "no-match", "skipped-budget")
    matching_files: list[str] = field(default_factory=list)
    matching_commits: list[str] = field(default_factory=list)
    submitted: int = 0
    success: int = 0
    failed: int = 0
    elapsed_s: float = 0.0
    log_path: str = ""
    error: str = ""


def has_url_impact(commit_files: list[str]) -> list[str]:
    """Return the subset of files that match URL-impact patterns."""
    matches = []
    for f in commit_files:
        if any(p.match(f) for p in _URL_IMPACT_PATTERNS):
            matches.append(f)
    return matches


def collect_url_impact(commits: list[Commit]) -> tuple[list[str], list[str]]:
    """Across all picked commits, gather (matching_files, matching_short_hashes)."""
    files: set[str] = set()
    commits_with_impact: list[str] = []
    for c in commits:
        m = has_url_impact(c.files)
        if m:
            files.update(m)
            commits_with_impact.append(c.short)
    return sorted(files), commits_with_impact


def trigger_indexnow(picked_commits: list[Commit],
                     max_urls: int = 30000,
                     date_str: str | None = None) -> IndexNowResult:
    """Best-effort IndexNow-push if any picked commit has URL-impact.

    Logs to ~/smedjan/measurement/indexnow-post-merge-YYYYMMDD.log.
    Never raises — caller can ignore failures (canary makes the real call).
    """
    res = IndexNowResult()
    if not picked_commits:
        res.reason = "no-picked-commits"
        return res

    matching_files, matching_short = collect_url_impact(picked_commits)
    if not matching_files:
        res.reason = "no-url-impact"
        return res

    res.matching_files = matching_files
    res.matching_commits = matching_short

    # Build log path.
    if date_str is None:
        date_str = time.strftime("%Y%m%d")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"indexnow-post-merge-{date_str}.log"
    res.log_path = str(log_path)

    if not AUTO_INDEXNOW_BIN.exists():
        res.error = f"auto_indexnow.py not found at {AUTO_INDEXNOW_BIN}"
        return res

    t0 = time.time()
    try:
        # Run the existing auto_indexnow.py with --max-urls cap. Capture stdout
        # for parse + write the full transcript to log_path.
        proc = subprocess.run(
            [str(PYTHON), str(AUTO_INDEXNOW_BIN), f"--max-urls={max_urls}"],
            capture_output=True, text=True, timeout=900,  # 15 min hard cap
        )
        log_path.write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
        res.elapsed_s = time.time() - t0

        # Parse "URLs submitted: N (zarq=…, nerq=…)" + Success/Failed counts
        for line in proc.stdout.splitlines():
            line = line.strip()
            if "URLs submitted:" in line:
                m = re.search(r"URLs submitted:\s*(\d+)", line)
                if m:
                    res.submitted = int(m.group(1))
            if "Success:" in line:
                m = re.search(r"Success:\s*(\d+)", line)
                if m:
                    res.success = int(m.group(1))
            if "Failed:" in line:
                m = re.search(r"Failed:\s*(\d+)", line)
                if m:
                    res.failed = int(m.group(1))

        if proc.returncode != 0:
            res.error = f"exit={proc.returncode}; see {log_path}"
        res.triggered = True
        res.reason = f"url-impact: {len(matching_files)} files in {len(matching_short)} commits"
    except subprocess.TimeoutExpired:
        res.error = "timeout 900s"
        res.elapsed_s = 900.0
    except Exception as e:
        res.error = f"exception: {e!s}"
        res.elapsed_s = time.time() - t0

    return res
