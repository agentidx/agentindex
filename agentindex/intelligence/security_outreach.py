"""
Security Disclosure Outreach

Opens GitHub issues on high-profile repos (>1 000 stars) where our scans
detected CRITICAL CVEs in their dependency tree.

This is a SECURITY DISCLOSURE tool, not marketing.  Tone is factual,
helpful, and non-promotional.  Every issue links to a full report and
includes opt-out instructions.

Usage:
    python -m agentindex.intelligence.security_outreach --dry-run   # preview (default)
    python -m agentindex.intelligence.security_outreach --live       # open issues
    python -m agentindex.intelligence.security_outreach --live --limit 3

Safety guardrails:
    - Only repos with critical_cves > 0
    - Only repos with github_stars > 1000
    - Max 5 issues per run (override with --limit, hard cap 10)
    - Skips repos where we already opened an issue
    - Skips repos with "nerq-optout" label
    - 30-second delay between live issues
    - All activity logged to security_outreach_log.json

# --------------------------------------------------------------------------
# LaunchAgent (install with launchctl load):
#
# <?xml version="1.0" encoding="UTF-8"?>
# <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
#   "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
# <plist version="1.0">
# <dict>
#   <key>Label</key>
#   <string>com.nerq.security-outreach</string>
#   <key>ProgramArguments</key>
#   <array>
#     <string>/usr/bin/env</string>
#     <string>python3</string>
#     <string>-m</string>
#     <string>agentindex.intelligence.security_outreach</string>
#     <string>--live</string>
#     <string>--limit</string>
#     <string>5</string>
#   </array>
#   <key>WorkingDirectory</key>
#   <string>/Users/anstudio/agentindex</string>
#   <key>StartCalendarInterval</key>
#   <dict>
#     <key>Hour</key>
#     <integer>13</integer>
#     <key>Minute</key>
#     <integer>0</integer>
#   </dict>
#   <key>StandardOutPath</key>
#   <string>/tmp/nerq-security-outreach.log</string>
#   <key>StandardErrorPath</key>
#   <string>/tmp/nerq-security-outreach.err</string>
#   <key>EnvironmentVariables</key>
#   <dict>
#     <key>PATH</key>
#     <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
#   </dict>
# </dict>
# </plist>
# --------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.sql import text

from agentindex.db.models import get_engine

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API = "https://api.github.com"
USER_AGENT = "NerqSecurityDisclosure/1.0"
NERQ_GITHUB_USER = os.getenv("NERQ_GITHUB_USER", "nerq-bot")

LOG_FILE = Path(__file__).parent / "security_outreach_log.json"
HARD_LIMIT = 10          # absolute max issues per run regardless of --limit
DELAY_SECONDS = 30       # pause between live issues
MIN_STARS = 1000          # floor for outreach

logger = logging.getLogger("security_outreach")

# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------


def _gh_request(
    path: str,
    method: str = "GET",
    body: dict | None = None,
) -> tuple[int, Any]:
    """Low-level GitHub API call via urllib.  Returns (status_code, parsed_json | None)."""
    url = f"{GITHUB_API}{path}" if path.startswith("/") else path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if body:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode()) if resp.status != 204 else None
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        try:
            err_body = json.loads(exc.read().decode())
        except Exception:
            err_body = None
        return exc.code, err_body


def _has_existing_issue(owner: str, repo: str) -> bool:
    """Return True if we already opened any issue on this repo."""
    status, data = _gh_request(
        f"/repos/{owner}/{repo}/issues?creator={NERQ_GITHUB_USER}&state=all&per_page=1"
    )
    if status == 200 and isinstance(data, list) and len(data) > 0:
        return True
    return False


def _has_optout_label(owner: str, repo: str) -> bool:
    """Return True if the repo has a 'nerq-optout' label."""
    status, _ = _gh_request(f"/repos/{owner}/{repo}/labels/nerq-optout")
    return status == 200


# ---------------------------------------------------------------------------
# Issue body builder
# ---------------------------------------------------------------------------


def _build_issue(
    repo_full_name: str,
    critical_cves: int,
    high_cves: int,
    top_issues: list[dict],
    project_health_grade: str | None,
    avg_trust_score: float | None,
) -> tuple[str, str]:
    """Return (title, markdown_body) for the disclosure issue."""
    title = f"Security: {critical_cves} known vulnerabilit{'y' if critical_cves == 1 else 'ies'} detected in dependencies"

    # --- CVE table ---
    critical_items = [i for i in top_issues if i.get("severity", "").lower() == "critical"]
    high_items = [i for i in top_issues if i.get("severity", "").lower() == "high"]
    table_items = critical_items + high_items  # critical first

    lines: list[str] = []
    lines.append("## Dependency Vulnerability Report")
    lines.append("")
    lines.append(
        f"An automated security scan identified **{critical_cves} critical** "
        f"and **{high_cves} high**-severity known vulnerabilities in the "
        f"dependency tree of `{repo_full_name}`."
    )
    lines.append("")

    if table_items:
        lines.append("| Package | Installed | CVE | Severity | Fix available |")
        lines.append("|---------|-----------|-----|----------|---------------|")
        for item in table_items:
            pkg = item.get("package", "unknown")
            ver = item.get("version", "?")
            cve = item.get("issue", "N/A")
            sev = item.get("severity", "?").upper()
            fix = item.get("fix", "unknown")
            lines.append(f"| `{pkg}` | `{ver}` | {cve} | **{sev}** | `{fix}` |")
        lines.append("")

    # --- Recommended actions ---
    lines.append("## Recommended actions")
    lines.append("")

    upgradable = [i for i in table_items if i.get("fix") and i["fix"] != "unknown"]
    if upgradable:
        lines.append("```bash")
        for item in upgradable:
            pkg = item["package"]
            fix = item["fix"]
            # Produce a pip command if the fix looks like a version specifier
            if fix.startswith(">=") or fix.startswith("==") or fix.startswith(">"):
                lines.append(f"pip install '{pkg}{fix}'")
            else:
                lines.append(f"pip install '{pkg}>={fix}'")
        lines.append("```")
        lines.append("")

    lines.append(
        "After upgrading, run your test suite to verify nothing breaks.  "
        "If a direct upgrade is not possible, consider pinning a patched "
        "fork or applying a workaround described in the CVE advisory."
    )
    lines.append("")

    # --- Full report link ---
    owner, repo = repo_full_name.split("/", 1)
    lines.append("## Full report")
    lines.append("")
    lines.append(
        f"A detailed breakdown (dependency graph, transitive risks, health grade) "
        f"is available at: **https://nerq.ai/report/{owner}/{repo}**"
    )
    lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append("")
    lines.append(
        "*This issue was opened automatically by "
        "[Nerq Security Scanner](https://nerq.ai), an open dependency-risk "
        "monitoring service.  It is a one-time disclosure and will not be "
        "repeated unless new critical CVEs are detected.*"
    )
    lines.append("")
    lines.append(
        '**Opt-out:** To prevent future disclosures from Nerq, create a label '
        'named `nerq-optout` on this repository, or close this issue with that '
        "label applied."
    )

    body = "\n".join(lines)
    return title, body


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------


def _fetch_qualifying_repos(limit: int) -> list[dict]:
    """Query project_scans for repos meeting disclosure criteria."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT repo_full_name, github_stars, critical_cves, high_cves,
                       top_issues, project_health_grade, avg_trust_score
                FROM project_scans
                WHERE critical_cves > 0 AND github_stars > :min_stars
                ORDER BY github_stars DESC
                LIMIT :lim
            """),
            {"min_stars": MIN_STARS, "lim": limit},
        ).fetchall()

    results = []
    for row in rows:
        top_issues_raw = row[4]  # JSONB — may already be a list or a JSON string
        if isinstance(top_issues_raw, str):
            try:
                top_issues_parsed = json.loads(top_issues_raw)
            except (json.JSONDecodeError, TypeError):
                top_issues_parsed = []
        elif isinstance(top_issues_raw, list):
            top_issues_parsed = top_issues_raw
        else:
            top_issues_parsed = []

        results.append({
            "repo_full_name": row[0],
            "github_stars": row[1],
            "critical_cves": row[2],
            "high_cves": row[3],
            "top_issues": top_issues_parsed,
            "project_health_grade": row[5],
            "avg_trust_score": row[6],
        })

    return results


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _load_log() -> dict:
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"contacted": {}, "runs": []}


def _save_log(log: dict) -> None:
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------


def run(*, live: bool = False, limit: int = 5) -> None:
    limit = min(limit, HARD_LIMIT)
    mode = "live" if live else "dry-run"
    logger.info("Security outreach starting — mode=%s, limit=%d", mode, limit)

    if live and not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN is not set.  Cannot open issues in live mode.")
        sys.exit(1)

    repos = _fetch_qualifying_repos(limit=limit * 3)  # fetch extra to account for skips
    logger.info("Found %d qualifying repos from project_scans", len(repos))

    log = _load_log()
    attempted = 0
    succeeded = 0
    failed = 0

    for repo_info in repos:
        if succeeded >= limit:
            break

        repo = repo_info["repo_full_name"]
        owner, repo_name = repo.split("/", 1)

        # --- Guard: already contacted ---
        if repo in log.get("contacted", {}):
            logger.info("SKIP %s — already contacted", repo)
            continue

        # --- Guard: duplicate check (only in live mode to avoid rate limits) ---
        if live:
            if _has_existing_issue(owner, repo_name):
                logger.info("SKIP %s — existing Nerq issue found", repo)
                continue
            if _has_optout_label(owner, repo_name):
                logger.info("SKIP %s — nerq-optout label present", repo)
                continue

        title, body = _build_issue(
            repo_full_name=repo,
            critical_cves=repo_info["critical_cves"],
            high_cves=repo_info["high_cves"],
            top_issues=repo_info["top_issues"],
            project_health_grade=repo_info.get("project_health_grade"),
            avg_trust_score=repo_info.get("avg_trust_score"),
        )

        attempted += 1

        if not live:
            # ---- Dry-run: print preview ----
            print("=" * 72)
            print(f"REPO:     {repo}")
            print(f"STARS:    {repo_info['github_stars']:,}")
            print(f"CRITICAL: {repo_info['critical_cves']}")
            print(f"HIGH:     {repo_info['high_cves']}")
            print(f"GRADE:    {repo_info.get('project_health_grade', 'N/A')}")
            print("-" * 72)
            print(f"TITLE:    {title}")
            print()
            print(body)
            print("=" * 72)
            print()
            succeeded += 1
            continue

        # ---- Live: open the issue ----
        logger.info("Opening issue on %s ...", repo)
        status, data = _gh_request(
            f"/repos/{owner}/{repo_name}/issues",
            method="POST",
            body={"title": title, "body": body},
        )

        if status in (200, 201) and data:
            issue_url = data.get("html_url", "?")
            logger.info("Opened %s", issue_url)
            log.setdefault("contacted", {})[repo] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "issue_url": issue_url,
                "cves": repo_info["critical_cves"],
            }
            succeeded += 1
        else:
            logger.error("Failed on %s — HTTP %d: %s", repo, status, data)
            failed += 1

        _save_log(log)

        # Delay before next issue
        if succeeded < limit:
            logger.info("Waiting %d seconds before next issue ...", DELAY_SECONDS)
            time.sleep(DELAY_SECONDS)

    # ---- Record the run ----
    log.setdefault("runs", []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
    })
    _save_log(log)

    logger.info(
        "Done — attempted=%d, succeeded=%d, failed=%d",
        attempted, succeeded, failed,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Open security-disclosure issues on repos with critical CVEs"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        dest="live",
        action="store_false",
        default=False,
        help="Preview issues without opening them (default)",
    )
    group.add_argument(
        "--live",
        dest="live",
        action="store_true",
        help="Actually open GitHub issues",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max issues to open per run (default 5, hard cap 10)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run(live=args.live, limit=args.limit)


if __name__ == "__main__":
    main()
