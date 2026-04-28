"""Tag-based rollback for daily-merge runs."""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

MAIN_REPO = Path("/Users/anstudio/agentindex")


def tag_pre_run(label_date: str | None = None) -> str:
    """Tag main HEAD as `daily-merge-rollback-YYYYMMDD`. Returns tag name."""
    d = label_date or date.today().strftime("%Y%m%d")
    tag = f"daily-merge-rollback-{d}"
    subprocess.run(
        ["git", "-C", str(MAIN_REPO), "tag", "-f", tag, "main"],
        check=True, capture_output=True,
    )
    return tag


def rollback_to_tag(tag: str) -> None:
    """Hard reset main → tag, restart API."""
    subprocess.run(
        ["git", "-C", str(MAIN_REPO), "reset", "--hard", tag],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["launchctl", "kickstart", "-k", "gui/501/com.nerq.api"],
        check=False, capture_output=True,
    )


def latest_rollback_tag() -> str | None:
    """Return today's rollback-tag or most recent if today's missing."""
    out = subprocess.check_output(
        ["git", "-C", str(MAIN_REPO), "tag", "--list", "daily-merge-rollback-*",
         "--sort=-creatordate"],
        text=True,
    )
    tags = [t for t in out.splitlines() if t.strip()]
    return tags[0] if tags else None


def cleanup_old_tags(keep_days: int = 7) -> list[str]:
    """Delete daily-merge-rollback-* tags older than keep_days."""
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=keep_days)
    out = subprocess.check_output(
        ["git", "-C", str(MAIN_REPO), "tag", "--list", "daily-merge-rollback-*"],
        text=True,
    )
    deleted = []
    for tag in out.splitlines():
        tag = tag.strip()
        if not tag:
            continue
        ymd = tag.replace("daily-merge-rollback-", "")
        try:
            dt = datetime.strptime(ymd, "%Y%m%d")
        except ValueError:
            continue
        if dt < cutoff:
            subprocess.run(
                ["git", "-C", str(MAIN_REPO), "tag", "-d", tag],
                check=False, capture_output=True,
            )
            deleted.append(tag)
    return deleted
