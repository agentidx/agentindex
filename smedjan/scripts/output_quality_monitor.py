"""output_quality_monitor.py — daily actionable-ratio alert for fallback runs.

For each fallback category (F1 / F2 / F3), looks at tasks that finished
``status='done'`` in the last 7 days and measures the fraction that
produced an *actionable* artefact:

    F1  any antipattern in the findings table has count > 0
    F2  the CSV has at least one data row (header + >= 1 row)
    F3  the escalation list was non-empty (new format: ``escalation_count``
        summary line; fallback: count rows under the 'Escalation list' heading)

If any category's ratio drops below ``THRESHOLD`` (default 10%), an ntfy
notification fires with the category name, ratio, and completed-task count.

Meant to be driven by ``output-quality-monitor.timer`` at 05:00
Europe/Stockholm daily. A ``--dry-run`` flag runs the same computation
without pushing ntfy — useful for one-off audit and for the systemd
``ExecStartPre`` smoke check.
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from pathlib import Path

from smedjan import config, ntfy, sources

log = logging.getLogger("smedjan.output_quality_monitor")

THRESHOLD = 0.10
LOOKBACK_DAYS = 7
CATEGORIES = ("F1", "F2", "F3")
AUDITS_DIR = config.SMEDJAN_ROOT / "audits"


def _fetch_completed_tasks(cur) -> dict[str, list[str]]:
    """Return {category: [task_id, ...]} for fallback tasks done in the
    last LOOKBACK_DAYS days.
    """
    cur.execute(
        """
        SELECT fallback_category, id
          FROM smedjan.tasks
         WHERE is_fallback = true
           AND status::text = 'done'
           AND done_at >= now() - %s::interval
           AND fallback_category = ANY(%s)
        """,
        (f"{LOOKBACK_DAYS} days", list(CATEGORIES)),
    )
    out: dict[str, list[str]] = {c: [] for c in CATEGORIES}
    for cat, task_id in cur.fetchall():
        if cat in out:
            out[cat].append(task_id)
    return out


# ── per-category actionable predicates ───────────────────────────────────

_F1_ROW_RE = re.compile(r"^\|\s*[^|]+\|\s*(\d+)\s*\|")


def _f1_actionable(task_id: str) -> bool | None:
    """True if the F1 audit has any finding with count > 0. None = no parseable
    audit found (counted as non-actionable in the ratio, but tracked)."""
    path = AUDITS_DIR / f"{task_id}.md"
    if not path.is_file():
        return None
    try:
        in_findings = False
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("## findings"):
                in_findings = True
                continue
            if in_findings and stripped.startswith("## "):
                break
            if not in_findings:
                continue
            m = _F1_ROW_RE.match(stripped)
            if m and int(m.group(1)) > 0:
                return True
        return False
    except OSError as exc:
        log.warning("F1 %s: could not read %s: %s", task_id, path, exc)
        return None


def _f2_actionable(task_id: str) -> bool | None:
    """True if the F2 CSV has at least one data row beyond the header."""
    path = AUDITS_DIR / f"{task_id}.csv"
    if not path.is_file():
        return None
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(fh)
            rows = 0
            for i, _ in enumerate(reader):
                rows = i + 1
                if rows >= 2:  # header + at least one data row
                    return True
            return False
    except OSError as exc:
        log.warning("F2 %s: could not read %s: %s", task_id, path, exc)
        return None


_F3_COUNT_RE = re.compile(r"escalation_count:\s*\*?\*?(\d+)")


def _f3_actionable(task_id: str) -> bool | None:
    """True if the F3 audit reports a non-empty escalation list.

    Prefers the explicit ``escalation_count: **N**`` summary line; falls
    back to counting list items (``- /compare/...``) under an ``## Escalation``
    (or ``## Escalation list``) heading for older formats.
    """
    path = AUDITS_DIR / f"{task_id}.md"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("F3 %s: could not read %s: %s", task_id, path, exc)
        return None

    m = _F3_COUNT_RE.search(text)
    if m:
        return int(m.group(1)) > 0

    in_esc = False
    items = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## escalation"):
            in_esc = True
            continue
        if in_esc and stripped.startswith("## "):
            break
        if in_esc and stripped.startswith(("- ", "* ", "1.", "|")):
            items += 1
    return items > 0


_PREDICATES = {
    "F1": _f1_actionable,
    "F2": _f2_actionable,
    "F3": _f3_actionable,
}


# ── ratio computation + alerting ─────────────────────────────────────────


def _compute_ratios(tasks_by_cat: dict[str, list[str]]) -> dict[str, dict]:
    """For each category return {completed, actionable, missing, ratio}.

    ``ratio = actionable / completed``. Missing audits are counted as
    non-actionable (they contribute to ``completed`` but not ``actionable``).
    """
    out: dict[str, dict] = {}
    for cat, ids in tasks_by_cat.items():
        pred = _PREDICATES[cat]
        completed = len(ids)
        actionable = 0
        missing = 0
        for tid in ids:
            result = pred(tid)
            if result is True:
                actionable += 1
            elif result is None:
                missing += 1
        ratio = (actionable / completed) if completed else 0.0
        out[cat] = {
            "completed": completed,
            "actionable": actionable,
            "missing": missing,
            "ratio": ratio,
        }
    return out


def _alert_if_below(results: dict[str, dict], *, dry_run: bool) -> list[str]:
    """Push one ntfy message per below-threshold category. Returns the list
    of category names that fired."""
    fired: list[str] = []
    for cat, stats in results.items():
        if stats["completed"] == 0:
            continue
        if stats["ratio"] < THRESHOLD:
            fired.append(cat)
            title = f"[SMEDJAN] {cat} actionable-ratio low"
            body = (
                f"{cat}: {stats['actionable']}/{stats['completed']} "
                f"actionable ({stats['ratio']*100:.1f}% < {THRESHOLD*100:.0f}%) "
                f"over last {LOOKBACK_DAYS}d. "
                f"Missing audits: {stats['missing']}."
            )
            if dry_run:
                log.info("DRY-RUN would push ntfy: %s — %s", title, body)
            else:
                ntfy.push(title, body, priority="high", tags="warning")
    return fired


def run(*, dry_run: bool = False) -> int:
    try:
        with sources.smedjan_db_cursor() as (_, cur):
            tasks = _fetch_completed_tasks(cur)
    except sources.SourceUnavailable as exc:
        log.error("smedjan DB unreachable: %s", exc)
        return 2

    results = _compute_ratios(tasks)
    for cat in CATEGORIES:
        s = results[cat]
        log.info(
            "%s: %d/%d actionable (%.1f%%) missing=%d",
            cat, s["actionable"], s["completed"],
            s["ratio"] * 100, s["missing"],
        )

    fired = _alert_if_below(results, dry_run=dry_run)
    if fired:
        log.warning("below-threshold categories: %s", ", ".join(fired))
    else:
        log.info("all categories at or above %.0f%% threshold", THRESHOLD * 100)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Smedjan fallback output-quality actionable-ratio monitor",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="compute and log ratios, but do not push ntfy",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
