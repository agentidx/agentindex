#!/usr/bin/env python3
"""Daily A/B test stats summary — writes to logs/ab_daily.log"""

import json
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "ab_events.db")
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "ab_daily.log")


def main():
    if not os.path.exists(DB_PATH):
        print("No AB events database found.")
        return

    conn = sqlite3.connect(DB_PATH, timeout=5)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # Today's stats
    rows = conn.execute("""
        SELECT variant,
               COUNT(*) as total,
               SUM(CASE WHEN event_type='page_view' THEN 1 ELSE 0 END) as views,
               SUM(CASE WHEN event_type='cta_click' THEN 1 ELSE 0 END) as clicks,
               SUM(CASE WHEN event_type='api_call' THEN 1 ELSE 0 END) as api_calls,
               SUM(CASE WHEN is_bot=1 THEN 1 ELSE 0 END) as bot_events
        FROM ab_events
        WHERE date(timestamp) = ?
        GROUP BY variant
        ORDER BY variant
    """, (today,)).fetchall()

    # All-time stats
    all_rows = conn.execute("""
        SELECT variant,
               COUNT(*) as total,
               SUM(CASE WHEN event_type='page_view' THEN 1 ELSE 0 END) as views,
               SUM(CASE WHEN event_type='cta_click' THEN 1 ELSE 0 END) as clicks,
               SUM(CASE WHEN event_type='api_call' THEN 1 ELSE 0 END) as api_calls,
               SUM(CASE WHEN is_bot=1 THEN 1 ELSE 0 END) as bot_events
        FROM ab_events
        GROUP BY variant
        ORDER BY variant
    """).fetchall()

    conn.close()

    lines = [f"\n=== A/B Daily Summary — {today} ==="]
    lines.append(f"{'Var':<4} {'Views':>6} {'Clicks':>7} {'API':>5} {'Bots':>5} {'CTR':>6}")
    lines.append("-" * 40)

    if rows:
        for row in rows:
            variant, total, views, clicks, api_calls, bots = row
            ctr = f"{clicks/views*100:.1f}%" if views > 0 else "0.0%"
            lines.append(f"{variant:<4} {views:>6} {clicks:>7} {api_calls:>5} {bots:>5} {ctr:>6}")
    else:
        lines.append("No events today.")

    lines.append(f"\n--- All-time ---")
    lines.append(f"{'Var':<4} {'Views':>6} {'Clicks':>7} {'API':>5} {'Bots':>5} {'CTR':>6}")
    lines.append("-" * 40)
    for row in all_rows:
        variant, total, views, clicks, api_calls, bots = row
        ctr = f"{clicks/views*100:.1f}%" if views > 0 else "0.0%"
        lines.append(f"{variant:<4} {views:>6} {clicks:>7} {api_calls:>5} {bots:>5} {ctr:>6}")

    report = "\n".join(lines)
    print(report)

    with open(LOG_PATH, "a") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
