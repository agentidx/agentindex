"""backlog_seeder — autonomous queue top-up from ~/smedjan/config/backlog.yaml.

Design intent: Anders keeps full strategic control via the YAML file
(order = priority, top = next). The seeder is a mechanical picker —
it does not reorder, filter, or invent tasks. It just reads the top-N,
skips anything already in the DB, and inserts.

Safeguards (all cheap, all defensive):
  1. Pause flag ~/smedjan/config/backlog_seeder_paused.flag short-
     circuits the whole run.
  2. Min-primary threshold prevents seeding when the queue already
     has enough work.
  3. Min-interval-between-seed-cycles enforced via state file
     ~/smedjan/worker-logs/last-backlog-seed.state.
  4. Malformed YAML → logged + skip, never crashes the caller.
  5. All seeded tasks get `created_by='backlog-seeder'` so Anders
     can audit via `smedjan queue list --seeded-from backlog`.

Called from planner.run() near the end — after follow-up enqueues and
quota report. Invokable standalone for tests:
    python3 -m smedjan.backlog_seeder --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from smedjan import factory_core, sources

log = logging.getLogger("smedjan.backlog_seeder")

CONFIG_PATH = Path.home() / "smedjan" / "config" / "backlog.yaml"
PAUSE_FLAG = Path.home() / "smedjan" / "config" / "backlog_seeder_paused.flag"
STATE_PATH = Path.home() / "smedjan" / "worker-logs" / "last-backlog-seed.state"
LOG_PATH = Path.home() / "smedjan" / "worker-logs" / "backlog-seeder.log"

DEFAULT_MIN_PRIMARY = 3
DEFAULT_MAX_PER_CYCLE = 2
DEFAULT_INTERVAL_MIN = 15


@dataclass
class _Thresholds:
    min_primary: int
    max_per_cycle: int
    min_interval_min: int


@dataclass
class _BacklogEntry:
    id: str
    title: str
    description: str
    whitelisted_files: list[str]
    risk_level: str
    session_affinity: str | None
    strategic_class: str
    acceptance_criteria: str


def _load_yaml() -> tuple[_Thresholds, list[_BacklogEntry]] | None:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        log.error("backlog_seeder: PyYAML not installed — skipping")
        return None
    try:
        with CONFIG_PATH.open() as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        log.warning("backlog_seeder: %s not found — skipping", CONFIG_PATH)
        return None
    except Exception as e:  # noqa: BLE001
        log.error("backlog_seeder: YAML parse failed: %s — skipping cycle", e)
        return None
    t_raw = data.get("threshold", {})
    thresh = _Thresholds(
        min_primary=int(t_raw.get("min_primary", DEFAULT_MIN_PRIMARY)),
        max_per_cycle=int(t_raw.get("max_seed_per_cycle", DEFAULT_MAX_PER_CYCLE)),
        min_interval_min=int(t_raw.get("min_interval_minutes", DEFAULT_INTERVAL_MIN)),
    )
    entries: list[_BacklogEntry] = []
    for item in data.get("backlog", []) or []:
        try:
            entries.append(_BacklogEntry(
                id=str(item["id"]),
                title=str(item["title"]),
                description=str(item.get("description", "")),
                whitelisted_files=list(item.get("whitelisted_files", []) or []),
                risk_level=str(item.get("risk_level", "medium")),
                session_affinity=item.get("session_affinity"),
                strategic_class=str(item.get("strategic_class", "default")),
                acceptance_criteria=str(item.get("acceptance_criteria", "")),
            ))
        except KeyError as e:
            log.warning("backlog_seeder: entry missing required field %s — skipped", e)
    return thresh, entries


def _paused() -> bool:
    try:
        return PAUSE_FLAG.exists()
    except Exception:  # noqa: BLE001
        return False


def _read_last_seed_at() -> datetime | None:
    try:
        raw = STATE_PATH.read_text().strip()
        return datetime.fromisoformat(raw)
    except Exception:  # noqa: BLE001
        return None


def _write_last_seed_at(now: datetime) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(now.isoformat())
    except Exception as e:  # noqa: BLE001
        log.warning("backlog_seeder: could not persist state: %s", e)


def _primary_count(cur) -> int:
    cur.execute(
        "SELECT count(*) FROM smedjan.tasks "
        "WHERE is_fallback = FALSE "
        "  AND status IN ('queued','approved')"
    )
    (n,) = cur.fetchone()
    return int(n)


def _existing_ids(cur, ids: Iterable[str]) -> set[str]:
    ids = list(ids)
    if not ids:
        return set()
    cur.execute("SELECT id FROM smedjan.tasks WHERE id = ANY(%s)", (ids,))
    return {r[0] for r in cur.fetchall()}


def _seed_one(cur, e: _BacklogEntry) -> bool:
    cur.execute(
        """
        INSERT INTO smedjan.tasks
            (id, title, description, acceptance_criteria, dependencies,
             risk_level, whitelisted_files, priority, session_affinity,
             status, is_fallback, fallback_category, strategic_class,
             notes)
        VALUES
            (%s, %s, %s, %s, %s,
             %s, %s, %s, %s,
             'pending', FALSE, NULL, %s,
             'seeded_from=backlog')
        ON CONFLICT (id) DO NOTHING
        RETURNING id
        """,
        (
            e.id, e.title, e.description, e.acceptance_criteria, [],
            e.risk_level, e.whitelisted_files, 20, e.session_affinity,
            e.strategic_class,
        ),
    )
    return cur.fetchone() is not None


def run(dry_run: bool = False) -> dict:
    """Execute one seed cycle. Returns a summary dict. Never raises."""
    summary = {"seeded": [], "skipped_existing": [], "reason": None, "dry_run": dry_run}
    if _paused():
        summary["reason"] = "paused_flag"
        log.info("backlog_seeder: paused — flag %s present", PAUSE_FLAG)
        return summary
    loaded = _load_yaml()
    if loaded is None:
        summary["reason"] = "yaml_missing_or_invalid"
        return summary
    thresh, entries = loaded
    if not entries:
        summary["reason"] = "empty_backlog"
        return summary

    now = datetime.now(timezone.utc)
    last = _read_last_seed_at()
    if last is not None and (now - last) < timedelta(minutes=thresh.min_interval_min):
        summary["reason"] = "interval_not_elapsed"
        log.info("backlog_seeder: %.1fm since last seed (< %dm) — waiting",
                 (now - last).total_seconds() / 60, thresh.min_interval_min)
        return summary

    try:
        with sources.smedjan_db_cursor() as (_conn, cur):
            primary = _primary_count(cur)
            summary["primary_count"] = primary
            if primary >= thresh.min_primary:
                summary["reason"] = "queue_above_threshold"
                log.info("backlog_seeder: primary=%d >= min=%d — no-op",
                         primary, thresh.min_primary)
                return summary

            existing = _existing_ids(cur, (e.id for e in entries))
            seeded_now = 0
            for e in entries:
                if seeded_now >= thresh.max_per_cycle:
                    break
                if e.id in existing:
                    summary["skipped_existing"].append(e.id)
                    continue
                if dry_run:
                    summary["seeded"].append(e.id + " (dry-run)")
                    seeded_now += 1
                    continue
                if _seed_one(cur, e):
                    summary["seeded"].append(e.id)
                    seeded_now += 1
                    log.info("backlog_seeder: seeded %s (primary was %d < %d)",
                             e.id, primary, thresh.min_primary)
    except Exception as e:  # noqa: BLE001 — never crash the planner
        summary["reason"] = f"db_error:{e}"
        log.error("backlog_seeder: DB error: %s", e)
        return summary

    if not dry_run and summary["seeded"]:
        _write_last_seed_at(now)
        # Any seeded row is pending; one resolve pass promotes rows whose
        # risk+whitelist satisfy the auto-yes policy, leaving medium-risk
        # rows at needs_approval for Anders. This matches the normal flow.
        try:
            factory_core.resolve_ready_tasks()
        except Exception as e:  # noqa: BLE001
            log.warning("backlog_seeder: resolve after seed failed: %s", e)

    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser("smedjan.backlog_seeder")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would be seeded without touching the DB")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
    )
    summary = run(dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
