"""
Badge PR Bot — Daily 11:00
============================
Automatically submits PRs to high-trust GitHub repos adding Nerq trust badges.
Max 10 PRs per run. Tracks submissions to avoid re-PRing.

Usage:
    python -m agentindex.badge_pr_bot
"""

import json
import logging
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy.sql import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [badge-pr-bot] %(message)s")
logger = logging.getLogger("badge-pr-bot")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
LOG_FILE = Path(__file__).parent.parent / "badge_pr_log.json"
MAX_PRS = 10


def _headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "NerqBadgePRBot/1.0",
    }


def _load_log():
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text())
        except Exception:
            pass
    return {"submitted": [], "rejected": [], "skipped": []}


def _save_log(log):
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))


def _extract_owner_repo(agent_name, source_url=None):
    if source_url:
        m = re.search(r"github\.com/([^/]+)/([^/\s?#]+)", source_url)
        if m:
            return m.group(1), m.group(2).rstrip(".git")
    if "/" in agent_name:
        parts = agent_name.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
    return None, None


def _check_readme_has_badge(owner, repo):
    """Check if README already has a Nerq badge."""
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/readme",
            headers=_headers(), timeout=15
        )
        if resp.status_code != 200:
            return True  # Skip if can't read
        import base64
        content = base64.b64decode(resp.json().get("content", "")).decode("utf-8", errors="ignore")
        return "nerq.ai" in content.lower() or "nerq trust" in content.lower()
    except Exception:
        return True


def _fork_repo(owner, repo):
    """Fork a repo. Returns fork owner or None."""
    try:
        resp = requests.post(
            f"https://api.github.com/repos/{owner}/{repo}/forks",
            headers=_headers(), timeout=30
        )
        if resp.status_code in (200, 202):
            return resp.json().get("owner", {}).get("login")
        elif resp.status_code == 422:
            # Already forked
            return None  # Will use existing fork
        return None
    except Exception:
        return None


def _create_pr(owner, repo, agent_name, score, grade):
    """Create a badge PR using GitHub API (without cloning)."""
    slug = agent_name.lower().replace("/", "").replace(" ", "-")
    badge_md = f"[![Nerq Trust Score](https://nerq.ai/badge/{slug}.svg)](https://nerq.ai/safe/{slug})"

    # Get the README
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/readme",
            headers=_headers(), timeout=15
        )
        if resp.status_code == 404:
            logger.info(f"  SKIP {owner}/{repo}: README not found (404)")
            return None
        if resp.status_code != 200:
            logger.info(f"  SKIP {owner}/{repo}: README fetch returned {resp.status_code}")
            return None

        readme_data = resp.json()
        import base64
        content = base64.b64decode(readme_data.get("content", "")).decode("utf-8")
        sha = readme_data.get("sha", "")
        path = readme_data.get("path", "README.md")

        # Insert badge after first heading
        lines = content.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("#"):
                insert_idx = i + 1
                break

        lines.insert(insert_idx, "")
        lines.insert(insert_idx + 1, badge_md)
        lines.insert(insert_idx + 2, "")
        new_content = "\n".join(lines)

        # Create a new branch
        branch_name = f"nerq-trust-badge-{int(time.time())}"

        # Get default branch SHA
        repo_resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=_headers(), timeout=15
        )
        default_branch = repo_resp.json().get("default_branch", "main")

        ref_resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{default_branch}",
            headers=_headers(), timeout=15
        )
        base_sha = ref_resp.json().get("object", {}).get("sha", "")

        # Create branch
        requests.post(
            f"https://api.github.com/repos/{owner}/{repo}/git/refs",
            headers=_headers(), timeout=15,
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha}
        )

        # Update file on new branch
        update_resp = requests.put(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(), timeout=15,
            json={
                "message": f"Add Nerq Trust Score badge ({grade} {score}/100)",
                "content": base64.b64encode(new_content.encode()).decode(),
                "sha": sha,
                "branch": branch_name,
            }
        )
        if update_resp.status_code not in (200, 201):
            logger.warning(f"Failed to update README for {owner}/{repo}: {update_resp.status_code} {update_resp.text[:100]}")
            return None

        # Create PR
        pr_body = f"""This repo has been independently analyzed by [Nerq](https://nerq.ai) and received a trust score of **{score}/100 ({grade})**.

This badge shows visitors that {repo} is a trusted, well-maintained project. The badge updates automatically as the score changes.

**What Nerq checks:**
- Security vulnerabilities (CVEs)
- License compliance
- Maintenance activity
- Community signals
- Dependency health

[View full trust report &rarr;](https://nerq.ai/safe/{slug})

---
*To remove, simply close this PR. No further PRs will be sent.*"""

        pr_resp = requests.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls",
            headers=_headers(), timeout=15,
            json={
                "title": f"Add Nerq Trust Score badge ({grade} {score}/100)",
                "body": pr_body,
                "head": branch_name,
                "base": default_branch,
            }
        )

        if pr_resp.status_code in (200, 201):
            pr_url = pr_resp.json().get("html_url", "")
            logger.info(f"  PR created: {pr_url}")
            return pr_url
        else:
            logger.warning(f"PR creation failed: {pr_resp.status_code} {pr_resp.text[:200]}")
            return None

    except Exception as e:
        logger.error(f"Error creating PR for {owner}/{repo}: {e}")
        return None


def run(max_prs=MAX_PRS):
    """Run badge PR bot."""
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN not set. Cannot create PRs.")
        return {"prs_created": 0, "skipped": 0, "errors": 0, "total_submitted_all_time": 0, "reason": "no token"}

    log = _load_log()
    already_done = set(log.get("submitted", []) + log.get("rejected", []) + log.get("skipped", []))

    from agentindex.db.models import get_session
    session = get_session()

    try:
        rows = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as ts, trust_grade, source_url
            FROM entity_lookup
            WHERE is_active = true
              AND COALESCE(trust_score_v2, trust_score) >= 80
              AND (source = 'github' OR source_url LIKE '%github.com%')
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC
            LIMIT 500
        """)).fetchall()
    finally:
        session.close()

    logger.info(f"Found {len(rows)} candidates (score >= 80 with GitHub)")

    prs_created = 0
    skipped = 0
    errors = 0

    for r in rows:
        if prs_created >= max_prs:
            break

        d = dict(r._mapping)
        agent_name = d["name"]
        owner, repo = _extract_owner_repo(agent_name, d.get("source_url"))

        if not owner or not repo:
            continue

        repo_key = f"{owner}/{repo}"
        if repo_key in already_done:
            continue

        # Check if already has badge
        if _check_readme_has_badge(owner, repo):
            log["skipped"].append(repo_key)
            skipped += 1
            continue

        score = round(float(d["ts"]))
        grade = d["trust_grade"] or "B"

        pr_url = _create_pr(owner, repo, agent_name, score, grade)
        if pr_url:
            log["submitted"].append(repo_key)
            prs_created += 1
            logger.info(f"  [{prs_created}/{max_prs}] PR: {repo_key} ({grade} {score})")
        else:
            log["rejected"].append(repo_key)
            errors += 1

        time.sleep(2)  # Rate limit

    _save_log(log)

    return {
        "prs_created": prs_created,
        "skipped": skipped,
        "errors": errors,
        "total_submitted_all_time": len(log.get("submitted", [])),
    }


def dry_run(limit=20):
    """Show candidate repos without making any GitHub API calls (except token validation)."""
    from agentindex.db.models import get_session
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as ts, trust_grade, source_url, stars
            FROM entity_lookup
            WHERE is_active = true
              AND COALESCE(trust_score_v2, trust_score) >= 80
              AND (source = 'github' OR source_url LIKE '%github.com%')
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC
            LIMIT :lim
        """), {"lim": limit * 5}).fetchall()  # fetch extra to account for skips
    finally:
        session.close()

    log = _load_log()
    already_done = set(log.get("submitted", []) + log.get("rejected", []) + log.get("skipped", []))

    # Validate token
    token_ok = False
    if GITHUB_TOKEN:
        try:
            r = requests.get("https://api.github.com/user", headers=_headers(), timeout=10)
            if r.status_code == 200:
                token_ok = True
                print(f"GitHub token: valid (user: {r.json().get('login', '?')})")
            else:
                print(f"GitHub token: INVALID ({r.status_code})")
        except Exception as e:
            print(f"GitHub token: ERROR ({e})")
    else:
        print("GitHub token: NOT SET")

    print(f"\nCandidates (score >= 80, GitHub source):")
    print(f"{'#':<4} {'Owner/Repo':<40} {'Stars':>8} {'Score':>6} {'Grade':>6} {'Status':<15}")
    print("-" * 85)

    shown = 0
    for r in rows:
        if shown >= limit:
            break
        d = dict(r._mapping)
        owner, repo = _extract_owner_repo(d["name"], d.get("source_url"))
        if not owner or not repo:
            continue
        repo_key = f"{owner}/{repo}"
        stars = d.get("stars") or 0
        score = round(float(d["ts"]))
        grade = d["trust_grade"] or "?"

        if repo_key in already_done:
            status = "already done"
        else:
            status = "eligible"

        shown += 1
        print(f"{shown:<4} {repo_key:<40} {stars:>8,} {score:>6} {grade:>6} {status:<15}")

    print(f"\nTotal in DB: {len(rows)} | Already done: {len(already_done)} | Shown: {shown}")
    print(f"Log file: {LOG_FILE}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Nerq Badge PR Bot")
    parser.add_argument("--dry-run", action="store_true", help="List targets without creating PRs")
    parser.add_argument("--limit", type=int, default=10, help="Max PRs to create (default 10)")
    args = parser.parse_args()

    if args.dry_run:
        dry_run(limit=args.limit)
        return

    logger.info("=" * 60)
    logger.info("Badge PR Bot — starting")
    logger.info("=" * 60)

    result = run(max_prs=args.limit)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Badge PR Bot — COMPLETE")
    logger.info(f"  PRs created: {result['prs_created']}")
    logger.info(f"  Skipped: {result['skipped']}")
    logger.info(f"  Errors: {result['errors']}")
    logger.info(f"  Total submitted (all time): {result['total_submitted_all_time']}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
