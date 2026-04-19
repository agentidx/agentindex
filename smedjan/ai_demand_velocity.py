"""
ai_demand_velocity.py — Smedjan L3 surge detector (T131).

For each slug with ≥ MIN_HISTORY snapshots in smedjan.ai_demand_history,
compute the mean and stddev of the previous N-1 snapshots and flag slugs
whose newest score exceeds `mean + 3 * stddev`. Each flagged slug gets a
`surge-investigation-<slug>` task enqueued via smedjan.cli.cmd_add.

Invoked as the trailing step of scripts/compute_ai_demand_score.py so the
surge check always sees the freshest snapshot. Runs under the same
com.nerq.smedjan.ai_demand LaunchAgent (macOS-equivalent of the
"smedjan-ai-demand systemd service" referenced in T131).
"""
from __future__ import annotations

import logging
import math
import re
from argparse import Namespace

import psycopg2

from smedjan import sources
from smedjan.cli import cmd_add

log = logging.getLogger("smedjan.ai_demand_velocity")

WINDOW_SNAPSHOTS = 7          # last N snapshots per slug
MIN_HISTORY = 4               # need ≥ this many historical points (excluding today)
SIGMA_THRESHOLD = 3.0
TASK_PRIORITY = 15
TASK_RISK = "low"
TASK_SESSION_GROUP = "d"


def _slug_for_task_id(slug: str) -> str:
    """Reduce an arbitrary slug to a safe fragment for a task id.

    Task ids are opaque text but we keep them shell-friendly and bounded.
    """
    safe = re.sub(r"[^a-z0-9._-]+", "-", slug.lower()).strip("-")
    return safe[:60] or "unknown"


def load_recent_history(window: int = WINDOW_SNAPSHOTS) -> dict[str, list[tuple]]:
    """Return {slug: [(computed_at, score), ...]} newest-first, max `window`."""
    sql = """
    SELECT slug, computed_at, score
    FROM (
        SELECT slug,
               computed_at,
               score,
               row_number() OVER (PARTITION BY slug ORDER BY computed_at DESC) AS rn
        FROM smedjan.ai_demand_history
    ) s
    WHERE rn <= %s
    ORDER BY slug, computed_at DESC;
    """
    out: dict[str, list[tuple]] = {}
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(sql, (window,))
        for slug, ts, score in cur.fetchall():
            out.setdefault(slug, []).append((ts, float(score)))
    return out


def detect_surges(history: dict[str, list[tuple]]) -> list[dict]:
    """Apply a mean + Nσ test over prior snapshots; return surge records."""
    surges: list[dict] = []
    for slug, snapshots in history.items():
        if len(snapshots) < MIN_HISTORY + 1:
            continue
        today_ts, today_score = snapshots[0]
        prior = [score for _ts, score in snapshots[1:]]
        n = len(prior)
        mean = sum(prior) / n
        var = sum((x - mean) ** 2 for x in prior) / n
        stddev = math.sqrt(var)
        # Guard against zero-variance baselines — require a real jump too.
        if stddev == 0.0:
            continue
        z = (today_score - mean) / stddev
        if z >= SIGMA_THRESHOLD:
            surges.append({
                "slug": slug,
                "today_score": today_score,
                "today_ts": today_ts,
                "mean": mean,
                "stddev": stddev,
                "z": z,
                "window": len(snapshots),
            })
    surges.sort(key=lambda r: r["z"], reverse=True)
    return surges


def enqueue_surge_task(surge: dict) -> tuple[str, bool]:
    """Enqueue a surge-investigation task. Returns (task_id, created)."""
    slug = surge["slug"]
    task_id = f"surge-investigation-{_slug_for_task_id(slug)}"
    title = f"Investigate ai_demand surge on '{slug}' (z={surge['z']:.2f}σ)"
    description = (
        f"ai_demand_score for slug '{slug}' jumped to {surge['today_score']:.2f} "
        f"on {surge['today_ts'].isoformat()}, vs a prior-{surge['window']-1}-snapshot "
        f"mean of {surge['mean']:.2f} (σ={surge['stddev']:.2f}, z={surge['z']:.2f}). "
        "Investigate whether this is genuine AI interest (create compare/alt page, "
        "llms.txt entry, sameAs Wikidata) or a bot/scraper anomaly (ignore + silence)."
    )
    acceptance = (
        "Root cause identified (real demand vs bot noise); if real, a L2/L4 task "
        "queued to productise the demand; if noise, source logged and ignored."
    )
    ns = Namespace(
        id=task_id,
        title=title,
        description=description,
        acceptance=acceptance,
        risk=TASK_RISK,
        deps="",
        whitelist="",
        priority=TASK_PRIORITY,
        session_group=TASK_SESSION_GROUP,
        wait_for_evidence=None,
        fallback=None,
    )
    try:
        cmd_add(ns)
        return task_id, True
    except psycopg2.errors.UniqueViolation:
        log.info("surge task %s already exists — skipping", task_id)
        return task_id, False


def run() -> int:
    """Main entrypoint. Logs result and returns the number of new surge tasks."""
    history = load_recent_history()
    if not history:
        log.info("no ai_demand_history rows — velocity check skipped")
        return 0
    log.info("loaded history for %d slugs", len(history))
    surges = detect_surges(history)
    if not surges:
        log.info("no surges in window (≥ %.1fσ over last %d snapshots)",
                 SIGMA_THRESHOLD, WINDOW_SNAPSHOTS)
        return 0
    log.info("detected %d surge(s); enqueueing investigation tasks", len(surges))
    created = 0
    for surge in surges:
        task_id, was_new = enqueue_surge_task(surge)
        if was_new:
            created += 1
            log.info("enqueued %s (z=%.2fσ, score=%.2f)",
                     task_id, surge["z"], surge["today_score"])
    log.info("ai_demand_velocity done — %d new surge task(s)", created)
    return created


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(0 if run() >= 0 else 1)
