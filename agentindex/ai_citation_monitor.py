#!/usr/bin/env python3
"""
AI Citation Monitor (E4) — System 12
======================================
Runs daily at 08:00. Tracks which AI bots (GPTBot, PerplexityBot, ClaudeBot,
Anthropic, etc.) are crawling which pages as a proxy for AI citation.

Queries analytics.db for is_ai_bot=1 requests, groups by bot and path,
tracks 20 key pages, generates daily/weekly reports.

Usage:
    python ai_citation_monitor.py           # Daily run
    python ai_citation_monitor.py --weekly  # Force weekly report

Exit 0 on success.
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LOG_PATH = "/tmp/ai-citation-monitor.log"
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent

ANALYTICS_DB = str(PROJECT_ROOT / "logs" / "analytics.db")
STATE_PATH = PROJECT_ROOT / "ai_citations_state.json"
LOG_FILE_PATH = PROJECT_ROOT / "ai_citations_log.json"
REPORTS_DIR = PROJECT_ROOT / "docs" / "auto-reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ai-citation-monitor")

# 20 key pages we care about being cited by AI bots
KEY_PAGES = [
    "/token/bitcoin",
    "/token/ethereum",
    "/token/solana",
    "/token/cardano",
    "/token/polkadot",
    "/crash-watch",
    "/vitality",
    "/vitality/methodology",
    "/safe/cursor",
    "/safe/devin",
    "/safe/copilot",
    "/safe/chatgpt",
    "/mcp/top",
    "/compare/zarq-vs-certik",
    "/compare/zarq-vs-token-sniffer",
    "/scan",
    "/api",
    "/kya",
    "/",
    "/about",
    "/methodology",
]


def get_db_connection():
    """Open analytics.db read-only."""
    if not os.path.exists(ANALYTICS_DB):
        logger.error("analytics.db not found at %s", ANALYTICS_DB)
        sys.exit(1)
    conn = sqlite3.connect(f"file:{ANALYTICS_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def query_ai_bot_hits(conn, since_iso: str, until_iso: str | None = None) -> list[dict]:
    """Return all AI bot requests in the given time range."""
    sql = """
        SELECT ts, path, bot_name, user_agent, status
        FROM requests
        WHERE is_ai_bot = 1
          AND ts >= ?
    """
    params = [since_iso]
    if until_iso:
        sql += " AND ts < ?"
        params.append(until_iso)
    sql += " ORDER BY ts DESC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def group_by_bot(hits: list[dict]) -> dict[str, int]:
    """Count hits per bot_name."""
    counts: dict[str, int] = {}
    for h in hits:
        bot = h.get("bot_name") or "unknown"
        counts[bot] = counts.get(bot, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def group_by_path(hits: list[dict]) -> dict[str, int]:
    """Count hits per path."""
    counts: dict[str, int] = {}
    for h in hits:
        path = h.get("path") or "/"
        counts[path] = counts.get(path, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def group_by_bot_and_path(hits: list[dict]) -> dict[str, dict[str, int]]:
    """Nested grouping: bot -> path -> count."""
    result: dict[str, dict[str, int]] = {}
    for h in hits:
        bot = h.get("bot_name") or "unknown"
        path = h.get("path") or "/"
        if bot not in result:
            result[bot] = {}
        result[bot][path] = result[bot].get(path, 0) + 1
    return result


def find_new_pages(current_paths: set[str], previous_paths: set[str]) -> list[str]:
    """Pages crawled by AI bots for the first time."""
    return sorted(current_paths - previous_paths)


def key_page_hits(hits: list[dict]) -> dict[str, int]:
    """Count hits for the 20 key pages only."""
    counts = {p: 0 for p in KEY_PAGES}
    for h in hits:
        path = h.get("path") or "/"
        if path in counts:
            counts[path] += 1
    return {k: v for k, v in sorted(counts.items(), key=lambda x: -x[1]) if v > 0}


def load_state() -> dict:
    """Load previous state from disk."""
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not load state file, starting fresh")
    return {}


def save_state(state: dict):
    """Save state to disk."""
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))
    logger.info("State saved to %s", STATE_PATH)


def append_log_entry(entry: dict):
    """Append a daily entry to ai_citations_log.json."""
    entries = []
    if LOG_FILE_PATH.exists():
        try:
            entries = json.loads(LOG_FILE_PATH.read_text())
            if not isinstance(entries, list):
                entries = []
        except (json.JSONDecodeError, OSError):
            entries = []
    entries.append(entry)
    # Keep last 90 days max
    if len(entries) > 90:
        entries = entries[-90:]
    LOG_FILE_PATH.write_text(json.dumps(entries, indent=2, default=str))
    logger.info("Log entry appended to %s (%d total entries)", LOG_FILE_PATH, len(entries))


def generate_daily_report(
    today_str: str,
    today_hits: list[dict],
    yesterday_hits: list[dict],
    week_hits: list[dict],
) -> str:
    """Generate a daily summary string for logging."""
    today_total = len(today_hits)
    yesterday_total = len(yesterday_hits)
    week_avg = len(week_hits) / 7.0 if week_hits else 0

    lines = [
        f"=== AI Citation Monitor — Daily Report {today_str} ===",
        "",
        f"Total AI bot hits today:     {today_total}",
        f"Total AI bot hits yesterday: {yesterday_total}",
        f"7-day average:               {week_avg:.1f}",
        "",
    ]

    # Change indicator
    if yesterday_total > 0:
        pct = ((today_total - yesterday_total) / yesterday_total) * 100
        direction = "UP" if pct > 0 else ("DOWN" if pct < 0 else "FLAT")
        lines.append(f"Day-over-day: {direction} {abs(pct):.1f}%")
    else:
        lines.append("Day-over-day: no yesterday data")
    lines.append("")

    # Bot breakdown
    bot_counts = group_by_bot(today_hits)
    lines.append("--- Bot Breakdown (today) ---")
    if bot_counts:
        for bot, count in list(bot_counts.items())[:15]:
            lines.append(f"  {bot:<30s} {count:>5d} hits")
    else:
        lines.append("  (no AI bot hits today)")
    lines.append("")

    # Top 20 pages by AI bot hits (today)
    path_counts = group_by_path(today_hits)
    lines.append("--- Top 20 Pages by AI Bot Hits (today) ---")
    for path, count in list(path_counts.items())[:20]:
        marker = " *KEY*" if path in KEY_PAGES else ""
        lines.append(f"  {path:<50s} {count:>5d}{marker}")
    lines.append("")

    # Key page coverage
    kp = key_page_hits(today_hits)
    lines.append("--- Key Page Coverage (today) ---")
    if kp:
        for path, count in kp.items():
            lines.append(f"  {path:<50s} {count:>5d}")
    else:
        lines.append("  (no key pages hit today)")
    covered = sum(1 for p in KEY_PAGES if any(h.get("path") == p for h in today_hits))
    lines.append(f"  Coverage: {covered}/{len(KEY_PAGES)} key pages hit by AI bots")
    lines.append("")

    return "\n".join(lines)


def generate_weekly_report(
    week_start: str,
    week_end: str,
    week_hits: list[dict],
    log_entries: list[dict],
) -> str:
    """Generate a markdown weekly report."""
    total = len(week_hits)
    bot_counts = group_by_bot(week_hits)
    path_counts = group_by_path(week_hits)
    kp = key_page_hits(week_hits)
    bot_path = group_by_bot_and_path(week_hits)

    md = [
        f"# AI Citation Monitor — Weekly Report",
        f"**Period:** {week_start} to {week_end}",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Summary",
        f"- **Total AI bot hits this week:** {total}",
        f"- **Daily average:** {total / 7.0:.1f}",
        f"- **Unique bots:** {len(bot_counts)}",
        f"- **Unique pages crawled:** {len(path_counts)}",
        f"- **Key pages covered:** {len(kp)}/{len(KEY_PAGES)}",
        "",
        "## Bot Breakdown",
        "| Bot | Hits | % of Total |",
        "|-----|------|-----------|",
    ]
    for bot, count in bot_counts.items():
        pct = (count / total * 100) if total > 0 else 0
        md.append(f"| {bot} | {count} | {pct:.1f}% |")

    md += [
        "",
        "## Top 30 Pages by AI Bot Hits",
        "| Page | Hits | Key Page |",
        "|------|------|----------|",
    ]
    for path, count in list(path_counts.items())[:30]:
        is_key = "Yes" if path in KEY_PAGES else ""
        md.append(f"| {path} | {count} | {is_key} |")

    md += [
        "",
        "## Key Page Detail",
        "| Page | Total Hits | Bots |",
        "|------|-----------|------|",
    ]
    for page in KEY_PAGES:
        count = sum(1 for h in week_hits if h.get("path") == page)
        bots_for_page = set(
            h.get("bot_name", "unknown") for h in week_hits if h.get("path") == page
        )
        bots_str = ", ".join(sorted(bots_for_page)) if bots_for_page else "-"
        md.append(f"| {page} | {count} | {bots_str} |")

    md += [
        "",
        "## Daily Trend",
        "| Date | Hits |",
        "|------|------|",
    ]
    # Use log entries for daily trend
    recent = [e for e in log_entries if e.get("date", "") >= week_start]
    for entry in recent:
        md.append(f"| {entry.get('date', '?')} | {entry.get('today_total', 0)} |")

    md += [
        "",
        "## Bot × Page Matrix (top bots × key pages)",
        "",
    ]
    top_bots = list(bot_counts.keys())[:5]
    if top_bots:
        header = "| Page | " + " | ".join(top_bots) + " |"
        sep = "|------|" + "|".join(["------"] * len(top_bots)) + "|"
        md.append(header)
        md.append(sep)
        for page in KEY_PAGES:
            row = f"| {page} |"
            for bot in top_bots:
                c = bot_path.get(bot, {}).get(page, 0)
                row += f" {c if c else '-'} |"
            md.append(row)

    md += ["", "---", "*Generated by AI Citation Monitor (System 12, E4)*"]
    return "\n".join(md)


def main():
    t0 = time.time()
    parser = argparse.ArgumentParser(description="AI Citation Monitor (E4)")
    parser.add_argument("--weekly", action="store_true", help="Force weekly report generation")
    args = parser.parse_args()

    logger.info("AI Citation Monitor starting")

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=7)

    today_start_iso = today_start.isoformat()
    yesterday_start_iso = yesterday_start.isoformat()
    today_end_iso = today_start.isoformat()  # yesterday ends at today start
    week_start_iso = week_start.isoformat()

    conn = get_db_connection()

    # Query hits for today, yesterday, and last 7 days
    logger.info("Querying AI bot hits from analytics.db")
    today_hits = query_ai_bot_hits(conn, today_start_iso)
    yesterday_hits = query_ai_bot_hits(conn, yesterday_start_iso, today_start_iso)
    week_hits = query_ai_bot_hits(conn, week_start_iso)

    logger.info(
        "Hits — today: %d, yesterday: %d, last 7 days: %d",
        len(today_hits), len(yesterday_hits), len(week_hits),
    )

    # Load previous state for new-page detection
    prev_state = load_state()
    prev_all_paths = set(prev_state.get("all_paths_seen", []))
    current_paths = set(h.get("path", "/") for h in week_hits)
    new_pages = find_new_pages(current_paths, prev_all_paths)
    if new_pages:
        logger.info("New pages crawled by AI bots for first time: %s", new_pages)

    # Generate and log daily report
    report = generate_daily_report(today_str, today_hits, yesterday_hits, week_hits)
    for line in report.split("\n"):
        logger.info(line)

    # Build daily log entry
    bot_counts = group_by_bot(today_hits)
    path_counts = group_by_path(today_hits)
    kp = key_page_hits(today_hits)
    covered = sum(1 for p in KEY_PAGES if any(h.get("path") == p for h in today_hits))

    log_entry = {
        "date": today_str,
        "timestamp": now.isoformat(),
        "today_total": len(today_hits),
        "yesterday_total": len(yesterday_hits),
        "week_total": len(week_hits),
        "week_avg": round(len(week_hits) / 7.0, 1),
        "bot_breakdown": bot_counts,
        "top_pages": dict(list(path_counts.items())[:20]),
        "key_page_hits": kp,
        "key_page_coverage": f"{covered}/{len(KEY_PAGES)}",
        "new_pages_first_time": new_pages,
    }
    append_log_entry(log_entry)

    # Update state
    all_paths_seen = sorted(prev_all_paths | current_paths)
    new_state = {
        "last_run": now.isoformat(),
        "last_date": today_str,
        "today_total": len(today_hits),
        "bot_breakdown": bot_counts,
        "top_pages": dict(list(path_counts.items())[:20]),
        "all_paths_seen": all_paths_seen,
    }
    save_state(new_state)

    # Weekly report on Sundays or if --weekly flag
    is_sunday = now.weekday() == 6
    if is_sunday or args.weekly:
        logger.info("Generating weekly report")
        # Load log for trend data
        log_entries = []
        if LOG_FILE_PATH.exists():
            try:
                log_entries = json.loads(LOG_FILE_PATH.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        weekly_md = generate_weekly_report(
            week_start.strftime("%Y-%m-%d"),
            today_str,
            week_hits,
            log_entries,
        )
        report_filename = f"ai_citations_weekly-{today_str}.md"
        report_path = REPORTS_DIR / report_filename
        report_path.write_text(weekly_md)
        logger.info("Weekly report saved to %s", report_path)

    conn.close()

    elapsed = time.time() - t0
    logger.info(
        "AI Citation Monitor complete in %.1fs — "
        "today=%d hits, yesterday=%d, 7d-avg=%.1f, key-coverage=%d/%d, new-pages=%d",
        elapsed,
        len(today_hits),
        len(yesterday_hits),
        len(week_hits) / 7.0,
        covered,
        len(KEY_PAGES),
        len(new_pages),
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
