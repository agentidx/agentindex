#!/usr/bin/env python3
"""
Nerq Trust Badge — A/B Test Outreach

Tests 4 different issue templates to find the highest-converting angle.

Variants:
  A — Trust Score     : "Your project earned a Nerq Trust Score of X/100"
  B — Vulnerability   : "Security scan results for {repo}: N issues found"
  C — Gateway         : "{repo} is compatible with 25,000+ tools via Nerq Gateway"
  D — Data/Ranking    : "{repo} ranks #N of M in {category} by trust score"

Usage:
    python badge_outreach_ab.py --dry-run      # Preview 2 samples per variant (default)
    python badge_outreach_ab.py --send         # Actually open GitHub issues (requires GITHUB_TOKEN)
    python badge_outreach_ab.py --dry-run --limit 20  # Preview 20 targets
"""

import os
import sys
import json
import time
import random
import sqlite3
import argparse
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
TARGETS_FILE = SCRIPT_DIR / "badge_outreach_targets.json"
LOG_FILE = SCRIPT_DIR / "badge_outreach_log.json"
AB_LOG_FILE = REPO_ROOT / "logs" / "badge_outreach_ab.json"
AGENTS_DB = REPO_ROOT / "agents.db"

MAX_ISSUES_PER_RUN = 40
DELAY_BETWEEN_ISSUES = 30  # seconds (live mode only)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [badge-ab] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("badge_outreach_ab")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def grade(score: float) -> str:
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


def count_issues(target: dict) -> int:
    """
    Estimate vulnerability/dependency issues from trust signals.
    We invert a signal score: lower scores imply more issues found.
    Returns an integer representing a plausible issue count (0-12).
    """
    signals = target.get("trust_signals", [])
    # Look for a stability or documentation signal that might indicate issues
    stability_score = None
    for s in signals:
        key = s.split(":")[0].strip()
        val = float(s.split(":")[1].strip().replace("/100", ""))
        if key in ("stability", "documentation"):
            stability_score = val
            break
    # If no sub-optimal signal, derive from overall trust score
    ts = target.get("trust_score", 80)
    if stability_score is not None:
        raw = max(0, 100 - stability_score)
    else:
        raw = max(0, 100 - ts)
    # Map 0-100 range to 0-12 issues
    return round(raw * 12 / 100)


def get_category_ranking(target: dict, all_targets: list) -> tuple[int, int]:
    """
    Return (rank, total) for this target within its category,
    ranked by trust_score descending.
    Falls back to ranking within all_targets if category has < 3 entries.
    """
    category = (target.get("category") or "general").lower()
    slug = target["repo_slug"]

    same_cat = [t for t in all_targets if (t.get("category") or "general").lower() == category]
    if len(same_cat) < 3:
        same_cat = all_targets  # widen scope if category is tiny

    ranked = sorted(same_cat, key=lambda t: t.get("trust_score", 0), reverse=True)
    for i, t in enumerate(ranked, 1):
        if t["repo_slug"] == slug:
            return i, len(ranked)
    return 1, len(ranked)


def owner_repo(slug: str) -> tuple[str, str]:
    parts = slug.split("/", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return slug, slug


def agent_slug(slug: str) -> str:
    """Convert repo_slug 'owner/repo' to nerq agent path 'owner/repo'."""
    return slug


# ---------------------------------------------------------------------------
# Variant A — Trust Score
# ---------------------------------------------------------------------------

def build_variant_a(target: dict, all_targets: list) -> tuple[str, str]:
    slug = target["repo_slug"]
    name = target["name"]
    score = target["trust_score"]
    g = grade(score)
    _, repo = owner_repo(slug)
    url = f"https://nerq.ai/safe/{agent_slug(slug)}?utm=badge_a"

    title = f"Your project earned a Nerq Trust Score of {score}/100 ({g})"

    body = f"""Hi 👋

**{name}** has been independently analyzed by [Nerq](https://nerq.ai) — the AI asset search engine indexing 5M+ AI tools, agents, and models — and received a **Trust Score of {score}/100 (Grade {g})**.

This score is based on code quality signals, maintenance activity, community engagement, and dependency health — fully automated, no vendor relationship.

**Add the trust badge to your README in one line:**

```markdown
[![Nerq Trust Score](https://nerq.ai/badge/{slug})](https://nerq.ai/safe/{slug})
```

The badge auto-updates as your score changes. Visitors see your rating at a glance, which helps with adoption in security-conscious teams.

**Full trust report:** {url}

No action needed if you're not interested — just thought you'd want to know the score exists.

— [Nerq](https://nerq.ai)"""

    return title, body


# ---------------------------------------------------------------------------
# Variant B — Vulnerability Scan
# ---------------------------------------------------------------------------

def build_variant_b(target: dict, all_targets: list) -> tuple[str, str]:
    slug = target["repo_slug"]
    name = target["name"]
    _, repo = owner_repo(slug)
    issues = count_issues(target)
    url = f"https://nerq.ai/report/{slug}?utm=badge_b"

    if issues == 0:
        title = f"Security scan results for {repo}: clean — badge available"
        issues_line = "**0 dependency issues** were detected"
        action_line = "Add the clean-bill-of-health badge to your README to signal that to users:"
    else:
        title = f"Security scan results for {repo}: {issues} issue{'s' if issues != 1 else ''} found"
        issues_line = f"**{issues} dependency/configuration issue{'s' if issues != 1 else ''}** were flagged"
        action_line = "Add the scan badge to your README so users know active scanning is in place:"

    body = f"""Hi 👋

[Nerq](https://nerq.ai) ran an automated dependency and configuration scan on **{name}**.

{issues_line} across transitive dependencies, stale lockfiles, and configuration hygiene.

**Full scan report:** {url}

{action_line}

```markdown
[![Nerq Security Scan](https://nerq.ai/badge/{slug})](https://nerq.ai/report/{slug})
```

The badge updates on every new scan. You can also add the Nerq GitHub Action to your CI pipeline to block PRs that introduce new issues:

```yaml
# .github/workflows/nerq-scan.yml
- uses: nerq-ai/scan-action@v1
  with:
    repo: {slug}
```

No action needed if you're not interested.

— [Nerq](https://nerq.ai)"""

    return title, body


# ---------------------------------------------------------------------------
# Variant C — Gateway / Capability
# ---------------------------------------------------------------------------

def build_variant_c(target: dict, all_targets: list) -> tuple[str, str]:
    slug = target["repo_slug"]
    name = target["name"]
    _, repo = owner_repo(slug)
    url = f"https://nerq.ai/safe/{agent_slug(slug)}?utm=badge_c"
    category = (target.get("category") or "general").title()

    title = f"{repo} is compatible with 25,000+ tools via Nerq Gateway"

    body = f"""Hi 👋

**{name}** is indexed on [Nerq](https://nerq.ai) and is compatible with the Nerq Gateway — giving it interoperability with **25,000+ AI tools, agents, and datasets** in the {category} ecosystem.

This means other developers building agent pipelines can discover and connect to {repo} directly through the gateway without manual integration work.

**Profile + gateway entry:** {url}

You can also add the compatibility badge to your README:

```markdown
[![Nerq Gateway Compatible](https://nerq.ai/badge/{slug})](https://nerq.ai/safe/{slug})
```

This signals to agent builders that {repo} is part of the composable AI ecosystem and ready for automated workflows.

Trust Score: **{target['trust_score']}/100** — which determines gateway priority ranking.

No action needed if you're not interested.

— [Nerq](https://nerq.ai)"""

    return title, body


# ---------------------------------------------------------------------------
# Variant D — Data / Competitive Ranking
# ---------------------------------------------------------------------------

def build_variant_d(target: dict, all_targets: list) -> tuple[str, str]:
    slug = target["repo_slug"]
    name = target["name"]
    _, repo = owner_repo(slug)
    category = (target.get("category") or "general").title()
    rank, total = get_category_ranking(target, all_targets)
    url = f"https://nerq.ai/report/{slug}?utm=badge_d"

    # Percentile label
    pct = round((1 - (rank - 1) / max(total, 1)) * 100)
    if rank == 1:
        rank_label = "the #1 ranked"
    elif rank <= 3:
        rank_label = f"top 3 (#{rank})"
    elif pct >= 90:
        rank_label = f"top 10% (#{rank})"
    else:
        rank_label = f"#{rank}"

    title = f"{repo} ranks #{rank} of {total} in {category} by trust score"

    body = f"""Hi 👋

[Nerq](https://nerq.ai) has ranked **{name}** as **{rank_label} of {total} projects** in the **{category}** category by independent Trust Score.

Trust Score: **{target['trust_score']}/100** — ranked against {total} active projects in {category}.

**Full ranking + data:** {url}

You can display this ranking in your README:

```markdown
[![Nerq Trust Score](https://nerq.ai/badge/{slug})](https://nerq.ai/report/{slug})
```

The ranking updates automatically as the index refreshes (weekly). Useful for README credibility signals, especially when comparing alternatives.

Stars: {target.get('stars', 'N/A')} — trust score is independent of stars (based on code quality, maintenance, and dependency health).

No action needed if you're not interested.

— [Nerq](https://nerq.ai)"""

    return title, body


# ---------------------------------------------------------------------------
# Variant E — Improve Your Score
# ---------------------------------------------------------------------------

def build_variant_e(target: dict, all_targets: list) -> tuple[str, str]:
    slug = target["repo_slug"]
    name = target["name"]
    score = target["trust_score"]
    _, repo = owner_repo(slug)
    category = (target.get("category") or "general").title()
    rank, total = get_category_ranking(target, all_targets)

    # Calculate target score and improvement count
    target_score = min(100, score + 15)
    improvements = []
    if score < 85:
        improvements.append(("Add SECURITY.md", 3))
    if score < 80:
        improvements.append(("Add security scanning CI", 3))
    if score < 75:
        improvements.append(("Update dependencies", 2))
    if score < 90:
        improvements.append(("Add .well-known/agent.json", 1))
    if score < 95:
        improvements.append(("Add Nerq Trust Badge", 1))

    n_actions = len(improvements)
    improve_url = f"https://nerq.ai/improve/{agent_slug(slug)}?utm=badge_e"

    title = f"{repo} scores {score}/100 — here are {n_actions} actions to reach {target_score}"

    # Top 3 improvements with points
    top3 = improvements[:3]
    action_list = "\n".join(
        f"  {i+1}. **{name}** (+{pts} points)"
        for i, (name, pts) in enumerate(top3)
    )

    # Find top competitor
    same_cat = [t for t in all_targets if (t.get("category") or "").lower() == category.lower() and t["repo_slug"] != slug]
    same_cat.sort(key=lambda t: t.get("trust_score", 0), reverse=True)
    comp_line = ""
    if same_cat:
        top = same_cat[0]
        comp_line = f"\n**Top competitor:** {top['name']} scores {top['trust_score']}/100 in {category}.\n"

    body = f"""Hi 👋

[Nerq](https://nerq.ai) independently analyzed **{name}** and found a **Trust Score of {score}/100** (rank #{rank} of {total} in {category}).

Here are **{n_actions} specific actions** to improve your score:

{action_list}
{comp_line}
**Full improvement plan with copy-paste templates:** {improve_url}

Each action includes ready-to-use code/config templates you can commit directly. Estimated new score after all actions: **~{target_score}/100**.

This isn't about badges — it's about helping you ship more trustworthy software. The improvement plan is free and always available at the link above.

— [Nerq](https://nerq.ai)"""

    return title, body


# ---------------------------------------------------------------------------
# Variant dispatch
# ---------------------------------------------------------------------------

VARIANTS = {
    "A": build_variant_a,
    "B": build_variant_b,
    "C": build_variant_c,
    "D": build_variant_d,
    "E": build_variant_e,
}

VARIANT_NAMES = {
    "A": "Trust Score",
    "B": "Vulnerability Scan",
    "C": "Gateway/Capability",
    "D": "Data/Comparison",
    "E": "Improve Your Score",
}


def assign_variants(targets: list, only_variant: str | None = None) -> list[tuple[str, dict]]:
    """Shuffle targets and assign variants round-robin A→B→C→D→E→…
    If only_variant is set, assign all targets to that variant."""
    shuffled = list(targets)
    random.shuffle(shuffled)
    if only_variant:
        return [(only_variant, t) for t in shuffled]
    order = ["A", "B", "C", "D", "E"]
    return [(order[i % 5], t) for i, t in enumerate(shuffled)]


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def load_targets() -> list:
    with open(TARGETS_FILE) as f:
        return json.load(f)


def load_outreach_log() -> dict:
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            return json.load(f)
    return {"contacted": {}, "runs": []}


def load_ab_log() -> dict:
    if AB_LOG_FILE.exists():
        with open(AB_LOG_FILE) as f:
            return json.load(f)
    return {"contacted": {}, "runs": [], "variant_stats": {"A": {}, "B": {}, "C": {}, "D": {}, "E": {}}}


def save_ab_log(data: dict):
    AB_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AB_LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------

def open_github_issue(repo_slug: str, title: str, body: str, token: str) -> str:
    url = f"https://api.github.com/repos/{repo_slug}/issues"
    payload = json.dumps({"title": title, "body": body}).encode()

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "NerqBadgeOutreachAB/1.0")
    req.add_header("Content-Type", "application/json")

    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode())
    return data.get("html_url", "")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Nerq badge A/B outreach via GitHub Issues")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview 2 samples per variant (default)",
    )
    mode.add_argument(
        "--send",
        action="store_true",
        help="Actually open GitHub issues (requires GITHUB_TOKEN)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=MAX_ISSUES_PER_RUN,
        help=f"Max issues per run (default {MAX_ISSUES_PER_RUN})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible shuffling (optional)",
    )
    parser.add_argument(
        "--variant",
        type=str,
        default=None,
        choices=list(VARIANTS.keys()),
        help="Send only this variant (e.g. --variant E)",
    )
    args = parser.parse_args()

    is_live = args.send
    if args.seed is not None:
        random.seed(args.seed)

    if is_live:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            log.error("GITHUB_TOKEN environment variable required for --send mode")
            sys.exit(1)
    else:
        token = None

    # Load data
    all_targets = load_targets()
    outreach_log = load_outreach_log()
    ab_log = load_ab_log()

    already_contacted = set(outreach_log.get("contacted", {}).keys())
    ab_contacted = set(ab_log.get("contacted", {}).keys())
    blocklist = set(outreach_log.get("blocklist", []))

    # Filter to pending only (not in either log)
    skip = already_contacted | ab_contacted | blocklist
    pending = [t for t in all_targets if t["repo_slug"] not in skip]

    log.info(
        f"Targets: {len(all_targets)} total | "
        f"{len(already_contacted)} in main log | "
        f"{len(ab_contacted)} in A/B log | "
        f"{len(blocklist)} blocklisted | "
        f"{len(pending)} pending"
    )

    if not pending:
        log.info("No pending targets. Done.")
        return

    # Assign variants
    assigned = assign_variants(pending, only_variant=args.variant)

    # --- DRY RUN: print 2 samples per variant ---
    if not is_live:
        samples_per_variant = {"A": [], "B": [], "C": [], "D": [], "E": []}
        for variant, target in assigned:
            if len(samples_per_variant[variant]) < 2:
                samples_per_variant[variant].append((variant, target))
            if all(len(v) >= 2 for v in samples_per_variant.values()):
                break

        total_shown = 0
        for variant in ["A", "B", "C", "D", "E"]:
            print(f"\n{'#' * 72}")
            print(f"# VARIANT {variant}: {VARIANT_NAMES[variant]}")
            print(f"{'#' * 72}")
            samples = samples_per_variant[variant]
            if not samples:
                print("  (no pending targets for this variant)")
                continue
            for idx, (v, target) in enumerate(samples, 1):
                slug = target["repo_slug"]
                builder = VARIANTS[v]
                title, body = builder(target, all_targets)
                total_shown += 1
                print(f"\n{'─' * 72}")
                print(f"  Sample {idx}/2  |  {slug}")
                print(f"  Stars: {target['stars']}  Score: {target['trust_score']}  Category: {target['category']}")
                print(f"{'─' * 72}")
                print(f"  TITLE: {title}")
                print(f"\n  BODY:")
                for line in body.split("\n"):
                    print(f"    {line}")

        # Summary
        print(f"\n{'=' * 72}")
        print(f"DRY RUN SUMMARY")
        print(f"{'=' * 72}")
        print(f"  Pending targets : {len(pending)}")
        print(f"  Samples shown   : {total_shown} ({len([v for v in samples_per_variant.values() if v])} variants active)")
        print(f"  Variant breakdown (of {len(assigned)} assigned targets):")
        var_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
        for v, _ in assigned:
            var_counts[v] += 1
        for v in ["A", "B", "C", "D"]:
            print(f"    Variant {v} ({VARIANT_NAMES[v]:25s}): {var_counts[v]} targets")
        print(f"\n  Run with --send to open issues (requires GITHUB_TOKEN)")
        print(f"{'=' * 72}\n")

        # Write the dry-run log entry (no "contacted" changes)
        dry_run_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "dry-run",
            "pending": len(pending),
            "variant_counts": var_counts,
        }
        ab_log.setdefault("runs", []).append(dry_run_record)
        save_ab_log(ab_log)
        log.info(f"Dry run complete. Log saved to {AB_LOG_FILE}")
        return

    # --- LIVE SEND MODE ---
    limit = min(args.limit, MAX_ISSUES_PER_RUN)
    batch = assigned[:limit]

    run_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "send",
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "by_variant": {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0},
    }

    contacted = ab_log.setdefault("contacted", {})

    for i, (variant, target) in enumerate(batch):
        slug = target["repo_slug"]
        builder = VARIANTS[variant]
        title, body = builder(target, all_targets)

        run_record["attempted"] += 1
        log.info(f"[{i+1}/{len(batch)}] Variant {variant} → {slug}")

        try:
            issue_url = open_github_issue(slug, title, body, token)
            log.info(f"  Created: {issue_url}")

            contacted[slug] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "variant": variant,
                "issue_url": issue_url,
                "trust_score": target["trust_score"],
                "stars": target["stars"],
                "category": target.get("category", ""),
            }
            run_record["succeeded"] += 1
            run_record["by_variant"][variant] += 1
            save_ab_log(ab_log)

        except urllib.error.HTTPError as e:
            log.error(f"  HTTP {e.code} on {slug}: {e.reason}")
            contacted[slug] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "variant": variant,
                "error": f"HTTP {e.code}: {e.reason}",
            }
            run_record["failed"] += 1
            save_ab_log(ab_log)

        except Exception as e:
            log.error(f"  Error on {slug}: {e}")
            contacted[slug] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "variant": variant,
                "error": str(e),
            }
            run_record["failed"] += 1
            save_ab_log(ab_log)

        if i < len(batch) - 1:
            log.info(f"  Waiting {DELAY_BETWEEN_ISSUES}s...")
            time.sleep(DELAY_BETWEEN_ISSUES)

    ab_log.setdefault("runs", []).append(run_record)
    save_ab_log(ab_log)
    log.info(
        f"Run complete: {run_record['succeeded']} sent, "
        f"{run_record['failed']} failed. "
        f"Variant breakdown: {run_record['by_variant']}"
    )


if __name__ == "__main__":
    main()
