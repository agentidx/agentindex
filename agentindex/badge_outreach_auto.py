#!/usr/bin/env python3
"""
Nerq Trust Badge — Automated GitHub Issue Outreach

Opens personalized GitHub Issues offering repos their Nerq trust badge.
Each accepted badge = a dofollow backlink from a relevant repo.

Usage:
    python badge_outreach_auto.py --dry-run     # Preview issues (default)
    python badge_outreach_auto.py --live         # Actually open issues
    python badge_outreach_auto.py --live --limit 5  # Open max 5 issues
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [badge-outreach] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("badge_outreach")

SCRIPT_DIR = Path(__file__).parent
TARGETS_FILE = SCRIPT_DIR / "badge_outreach_targets.json"
LOG_FILE = SCRIPT_DIR / "badge_outreach_log.json"
MAX_ISSUES_PER_RUN = 10
DELAY_BETWEEN_ISSUES = 30  # seconds


def load_targets():
    with open(TARGETS_FILE) as f:
        return json.load(f)


def load_log():
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            return json.load(f)
    return {"contacted": {}, "runs": []}


def save_log(log_data):
    with open(LOG_FILE, "w") as f:
        json.dump(log_data, f, indent=2)


def grade(score):
    if score >= 90:
        return "A+"
    if score >= 85:
        return "A"
    if score >= 80:
        return "A-"
    if score >= 75:
        return "B+"
    if score >= 70:
        return "B"
    return "C"


def build_signals_text(target):
    """Build a human-readable summary of the top trust signals with real scores."""
    signals = target.get("trust_signals", [])
    if not signals:
        return "active maintenance and strong community engagement"

    label_map = {
        "activity": "development activity",
        "recency": "update recency",
        "community": "community engagement",
        "documentation": "documentation quality",
        "stability": "codebase stability",
        "popularity": "popularity",
    }

    # Parse signal strings ("activity: 100/100") into (label, score) pairs
    parsed = []
    for s in signals:
        key = s.split(":")[0].strip()
        val = float(s.split(":")[1].strip().replace("/100", ""))
        nice = label_map.get(key, key)
        parsed.append((nice, val))

    # Take top 3 by score (already sorted from DB, but be safe)
    parsed.sort(key=lambda x: x[1], reverse=True)
    top = parsed[:3]

    parts = [f"{name} {score:.0f}/100" for name, score in top]

    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{parts[0]}, {parts[1]}, and {parts[2]}"


def build_issue(target):
    """Build issue title and body for a target repo."""
    name = target["name"]
    score = target["trust_score"]
    slug = target["repo_slug"]
    g = grade(score)
    verified = " — Nerq Verified ✓" if score >= 70 else ""
    signals_text = build_signals_text(target)

    title = f"{name} has a Nerq Trust Score of {score}/100 — verified badge available"

    category = target.get("category") or "general"
    category_line = f"({name} is indexed in the **{category}** category on Nerq.)"

    body = f"""Hi! 👋

**{name}** has been evaluated by [Nerq](https://nerq.ai), the AI Asset Search Engine indexing 5M+ AI assets, and received a trust score of **{score}/100 ({g})**{verified}.

You can add a trust badge to your README:

```markdown
[![Nerq Trust Score](https://nerq.ai/badge/{slug})](https://nerq.ai/safe/{slug})
```

This shows users your agent's trust rating at a glance. The badge updates automatically as your score changes.

**See your full trust report:** https://nerq.ai/safe/{slug}

The score is based on {signals_text}. {category_line}

No action needed if you're not interested. Just thought you'd like to know!

— [Nerq](https://nerq.ai) (nerq.ai)"""

    return title, body


def open_github_issue(repo_slug, title, body, token):
    """Open a GitHub issue via the API. Returns issue URL or raises."""
    import urllib.request

    url = f"https://api.github.com/repos/{repo_slug}/issues"
    payload = json.dumps({"title": title, "body": body}).encode()

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "NerqBadgeOutreach/1.0")
    req.add_header("Content-Type", "application/json")

    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode())
    return data.get("html_url", "")


def main():
    parser = argparse.ArgumentParser(description="Nerq badge outreach via GitHub Issues")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="Preview only (default)")
    mode.add_argument("--live", action="store_true", help="Actually open GitHub issues")
    parser.add_argument("--limit", type=int, default=MAX_ISSUES_PER_RUN, help=f"Max issues per run (default {MAX_ISSUES_PER_RUN})")
    args = parser.parse_args()

    is_live = args.live
    limit = min(args.limit, MAX_ISSUES_PER_RUN)

    if is_live:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            log.error("GITHUB_TOKEN environment variable required for --live mode")
            sys.exit(1)
    else:
        token = None

    targets = load_targets()
    outreach_log = load_log()
    contacted = outreach_log["contacted"]

    # Filter out already-contacted and blocklisted repos
    blocklist = set(outreach_log.get("blocklist", []))
    pending = [t for t in targets if t["repo_slug"] not in contacted and t["repo_slug"] not in blocklist]
    log.info(f"Targets: {len(targets)} total, {len(contacted)} contacted, {len(blocklist)} blocklisted, {len(pending)} pending")

    if not pending:
        log.info("No pending targets. Done.")
        return

    batch = pending[:limit]
    run_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if is_live else "dry-run",
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
    }

    for i, target in enumerate(batch):
        slug = target["repo_slug"]
        title, body = build_issue(target)

        if not is_live:
            print(f"\n{'='*72}")
            print(f"[DRY RUN {i+1}/{len(batch)}] {slug}")
            print(f"  Stars: {target['stars']}  Score: {target['trust_score']}  Category: {target['category']}")
            print(f"  Title: {title}")
            print(f"  Body:\n")
            for line in body.split("\n"):
                print(f"    {line}")
            print(f"{'='*72}")
            continue

        # Live mode
        run_record["attempted"] += 1
        try:
            log.info(f"[{i+1}/{len(batch)}] Opening issue on {slug}...")
            issue_url = open_github_issue(slug, title, body, token)
            log.info(f"  ✓ Created: {issue_url}")

            contacted[slug] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "issue_url": issue_url,
                "trust_score": target["trust_score"],
                "stars": target["stars"],
            }
            run_record["succeeded"] += 1
            save_log(outreach_log)

        except Exception as e:
            log.error(f"  ✗ Failed on {slug}: {e}")
            run_record["failed"] += 1
            contacted[slug] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
            }
            save_log(outreach_log)

        # Rate limit delay (skip after last issue)
        if i < len(batch) - 1:
            log.info(f"  Waiting {DELAY_BETWEEN_ISSUES}s before next issue...")
            time.sleep(DELAY_BETWEEN_ISSUES)

    if is_live:
        outreach_log["runs"].append(run_record)
        save_log(outreach_log)
        log.info(f"Run complete: {run_record['succeeded']} created, {run_record['failed']} failed")
    else:
        log.info(f"Dry run complete. Previewed {len(batch)} issues. Use --live to send.")


if __name__ == "__main__":
    main()
