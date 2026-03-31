#!/usr/bin/env python3
"""
Weekly Vitality Report (C3)
============================
Runs Tuesdays at 07:00 via LaunchAgent com.zarq.vitality-report.
Compares this week's Vitality Scores against last week's, generates
a markdown report, publishes to Dev.to and saves for blog.

Usage:
    python vitality_weekly_report.py              # Dry run (default)
    python vitality_weekly_report.py --publish     # Publish to Dev.to + blog

Exit 0 on success.
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LOG_PATH = "/tmp/vitality-report.log"
SCRIPT_DIR = Path(__file__).parent
STATE_PATH = SCRIPT_DIR / "vitality_weekly_state.json"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "auto-reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

RISK_DB = str(SCRIPT_DIR / "crypto" / "crypto_trust.db")
DEVTO_KEY_PATH = Path.home() / ".config" / "nerq" / "devto_api_key"

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("vitality-report")


def load_current_scores() -> dict:
    """Load current vitality scores from DB."""
    conn = sqlite3.connect(RISK_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT token_id, symbol, name, vitality_score, vitality_grade,
               ecosystem_gravity, capital_commitment, coordination_efficiency,
               stress_resilience, organic_momentum, trust_score, trust_rating,
               confidence
        FROM vitality_scores
        ORDER BY vitality_score DESC
    """).fetchall()
    conn.close()
    return {r["token_id"]: dict(r) for r in rows}


def load_previous_scores() -> dict:
    """Load last week's scores from state file."""
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_current_as_previous(scores: dict):
    """Save current scores as the baseline for next week."""
    compact = {
        tid: {
            "vitality_score": v["vitality_score"],
            "vitality_grade": v["vitality_grade"],
            "symbol": v.get("symbol"),
            "name": v.get("name"),
        }
        for tid, v in scores.items()
    }
    with open(STATE_PATH, "w") as f:
        json.dump(compact, f)


def generate_report(current: dict, previous: dict) -> tuple[str, str]:
    """Generate the weekly vitality report. Returns (title, body_markdown)."""
    now = datetime.now(timezone.utc)
    week_str = now.strftime("%B %d, %Y")
    date_slug = now.strftime("%Y-%m-%d")

    all_scores = sorted(current.values(), key=lambda x: x["vitality_score"], reverse=True)

    # Top 10 overall
    top_10 = all_scores[:10]

    # Grade distribution
    grades = {}
    for s in all_scores:
        g = s["vitality_grade"]
        grades[g] = grades.get(g, 0) + 1

    # Movers (compared to last week)
    movers = []
    grade_changes = []
    if previous:
        for tid, curr in current.items():
            prev = previous.get(tid)
            if not prev:
                continue
            delta = curr["vitality_score"] - prev["vitality_score"]
            if abs(delta) > 2:
                movers.append({
                    "token_id": tid,
                    "symbol": curr.get("symbol") or tid,
                    "name": curr.get("name") or tid,
                    "prev": prev["vitality_score"],
                    "curr": curr["vitality_score"],
                    "delta": delta,
                    "grade": curr["vitality_grade"],
                })
            # Grade changes
            prev_grade = prev.get("vitality_grade")
            curr_grade = curr.get("vitality_grade")
            if prev_grade and curr_grade and prev_grade != curr_grade:
                grade_changes.append({
                    "token_id": tid,
                    "symbol": curr.get("symbol") or tid,
                    "name": curr.get("name") or tid,
                    "prev_grade": prev_grade,
                    "curr_grade": curr_grade,
                    "score": curr["vitality_score"],
                })

    movers_up = sorted([m for m in movers if m["delta"] > 0], key=lambda x: x["delta"], reverse=True)[:5]
    movers_down = sorted([m for m in movers if m["delta"] < 0], key=lambda x: x["delta"])[:5]

    # Build markdown
    title = f"ZARQ Vitality Report — Week of {week_str}"

    md = f"# {title}\n\n"
    md += f"*Published {now.strftime('%Y-%m-%d')} by [ZARQ](https://zarq.ai) — Independent Crypto Risk Intelligence*\n\n"
    md += f"This week's Vitality Score update covers **{len(all_scores):,}** tokens across 5 dimensions: "
    md += "Ecosystem Gravity, Capital Commitment, Coordination Efficiency, Stress Resilience, and Organic Momentum.\n\n"

    # Top 10
    md += "## Top 10 by Vitality Score\n\n"
    md += "| Rank | Token | Vitality | Grade | Trust Rating | Confidence |\n"
    md += "|------|-------|----------|-------|-------------|------------|\n"
    for i, s in enumerate(top_10, 1):
        name = (s.get("name") or s["token_id"])[:25]
        trust = s.get("trust_rating") or "—"
        md += f"| {i} | [{name}](https://zarq.ai/token/{s['token_id']}) | {s['vitality_score']:.1f} | {s['vitality_grade']} | {trust} | {s['confidence']}% |\n"

    # Grade distribution
    md += "\n## Grade Distribution\n\n"
    md += "| Grade | Count | % |\n"
    md += "|-------|-------|---|\n"
    for g in ["S", "A", "B", "C", "D", "F"]:
        count = grades.get(g, 0)
        pct = count / len(all_scores) * 100 if all_scores else 0
        md += f"| {g} | {count:,} | {pct:.1f}% |\n"

    # Movers
    if movers_up:
        md += "\n## Biggest Movers Up\n\n"
        md += "| Token | Change | Score | Grade |\n"
        md += "|-------|--------|-------|-------|\n"
        for m in movers_up:
            md += f"| [{m['name'][:25]}](https://zarq.ai/token/{m['token_id']}) | +{m['delta']:.1f} ({m['prev']:.1f} → {m['curr']:.1f}) | {m['curr']:.1f} | {m['grade']} |\n"

    if movers_down:
        md += "\n## Biggest Movers Down\n\n"
        md += "| Token | Change | Score | Grade |\n"
        md += "|-------|--------|-------|-------|\n"
        for m in movers_down:
            md += f"| [{m['name'][:25]}](https://zarq.ai/token/{m['token_id']}) | {m['delta']:.1f} ({m['prev']:.1f} → {m['curr']:.1f}) | {m['curr']:.1f} | {m['grade']} |\n"

    # Grade changes
    if grade_changes:
        upgrades = [g for g in grade_changes if g["curr_grade"] < g["prev_grade"]]  # A < B alphabetically = upgrade
        downgrades = [g for g in grade_changes if g["curr_grade"] > g["prev_grade"]]

        if upgrades:
            md += "\n## Grade Upgrades\n\n"
            for g in upgrades[:10]:
                md += f"- **{g['name']}**: {g['prev_grade']} → {g['curr_grade']} (score: {g['score']:.1f})\n"

        if downgrades:
            md += "\n## Grade Downgrades\n\n"
            for g in downgrades[:10]:
                md += f"- **{g['name']}**: {g['prev_grade']} → {g['curr_grade']} (score: {g['score']:.1f})\n"

    if not previous:
        md += "\n## Note\n\n"
        md += "This is the first weekly report. Mover analysis will be available starting next week.\n"

    # Footer
    md += "\n---\n\n"
    md += "**Methodology**: [zarq.ai/vitality/methodology](https://zarq.ai/vitality/methodology) | "
    md += "**Full Rankings**: [zarq.ai/vitality](https://zarq.ai/vitality) | "
    md += "**Backtest Results**: [zarq.ai/vitality/backtest](https://zarq.ai/vitality/backtest)\n\n"
    md += "*The Vitality Score measures ecosystem quality and crash resistance. "
    md += "Tokens with high Vitality Scores lost 44% less during the July 2025 — February 2026 drawdown (p < 0.001).*\n"

    return title, md


def publish_to_devto(title: str, body: str, date_str: str) -> str | None:
    """Publish to Dev.to as a draft."""
    if not DEVTO_KEY_PATH.exists():
        logger.info("No Dev.to API key — skipping publish")
        return None

    api_key = DEVTO_KEY_PATH.read_text().strip()
    if not api_key:
        logger.info("Empty Dev.to API key — skipping")
        return None

    body += f"\n\n---\n*Originally published on [zarq.ai](https://zarq.ai/report/vitality-weekly-{date_str})*"

    payload = json.dumps({
        "article": {
            "title": title,
            "body_markdown": body,
            "published": False,
            "tags": ["crypto", "defi", "blockchain", "data"],
            "series": "ZARQ Vitality Report",
            "canonical_url": f"https://zarq.ai/report/vitality-weekly-{date_str}",
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://dev.to/api/articles",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            url = result.get("url", "")
            logger.info("Dev.to draft created: %s", url)
            return url
    except Exception as e:
        logger.warning("Dev.to publish failed: %s", e)
        return None


def main():
    parser = argparse.ArgumentParser(description="ZARQ Weekly Vitality Report")
    parser.add_argument("--publish", action="store_true", help="Publish to Dev.to + save (default: dry run)")
    args = parser.parse_args()

    t0 = time.time()
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    is_dry_run = not args.publish

    logger.info("=" * 60)
    logger.info("Vitality Weekly Report started at %s (%s)", now.isoformat(),
                "DRY RUN" if is_dry_run else "PUBLISH")

    # Load data
    current = load_current_scores()
    previous = load_previous_scores()
    logger.info("Current scores: %d, Previous scores: %d", len(current), len(previous))

    # Generate report
    title, body = generate_report(current, previous)
    logger.info("Report generated: %s", title)

    if is_dry_run:
        print("\n" + "=" * 72)
        print(f"[DRY RUN] {title}")
        print("=" * 72)
        print(body)
        print("=" * 72)
        logger.info("Dry run — not publishing or saving state")
    else:
        # Save report
        md_path = REPORTS_DIR / f"vitality-weekly-{date_str}.md"
        md_path.write_text(body, encoding="utf-8")
        logger.info("Saved report: %s", md_path)

        # Publish to Dev.to
        devto_url = publish_to_devto(title, body, date_str)

        # Save current scores as baseline for next week
        save_current_as_previous(current)
        logger.info("Saved current scores as next week's baseline")

    elapsed = time.time() - t0
    logger.info("-" * 60)
    logger.info("VITALITY REPORT COMPLETE")
    logger.info("  Tokens covered:    %d", len(current))
    logger.info("  Elapsed:           %.1fs", elapsed)
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
