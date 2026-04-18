"""
Smedjan Planner v1.

Runs every ~4h via systemd timer (smedjan-planner.timer). Three
responsibilities:

    resolve_evidence_gated()   — nudge factory_core.resolve_ready_tasks()
                                  so tasks waiting on evidence_signals
                                  get promoted as soon as a signal lands.
    generate_followup_tasks()  — scan done-tasks from the last 24h and
                                  enqueue canonical follow-ups per a
                                  small rulebook (extensible).
    generate_quota_fill()      — enforce a coarse portfolio ratio on the
                                  live queue (≥70 % scale, ≥20 % iterate,
                                  ≤5 % exploratory, ≥1 discordant), log
                                  warnings when drifts exceed tolerance
                                  so Anders / later Planner iterations
                                  can fix it.

CLI: `python3 -m smedjan.planner run [--dry-run]`.

Planner never writes to Nerq; it writes only to the smedjan DB.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Iterable

import psycopg2
import psycopg2.extras

from smedjan import factory_core, ntfy, sources

log = logging.getLogger("smedjan.planner")


# ── Follow-up rulebook ────────────────────────────────────────────────────
# Maps a completed task-id (or a prefix pattern) to a list of follow-up task
# templates. Templates are only enqueued if no row with the new id already
# exists — idempotent on re-runs.
FOLLOWUP_RULES: list[dict] = [
    {
        "match_id": "T003",
        "followups": [
            {
                "id_suffix": "b",
                "title": "L2 Block 2d registry-specific dimensions (ingredient/supplement/cosmetic)",
                "description": (
                    "Context: T003 produced smedjan.monetization_tiers + "
                    "monetization-tiers.md. For the ingredient / supplement / "
                    "cosmetic_ingredient registries (all T3 but zero duplicate-"
                    "render risk because they already get their own template), "
                    "propose Block 2d content that surfaces software_registry.dimensions "
                    "(skincare_safety, regulatory_status) + .regulatory JSONB.\n\n"
                    "Read-only design task: no code changes. Output a design doc "
                    "at ~/smedjan/docs/L2-block-2d-design.md covering data sources, "
                    "placement (above existing registry templates), and a sample "
                    "block-render for one entity per registry."
                ),
                "acceptance_criteria": (
                    "~/smedjan/docs/L2-block-2d-design.md exists; ≥ 400 words; "
                    "sample render shown for one entity per target registry."
                ),
                "whitelisted_files": ["smedjan/docs/L2-block-2d-design.md"],
                "risk_level": "low",
                "priority": 55,
                "session_group": "L2",
            },
        ],
    },
    # Extend: on T004 done → wave-2 canary for Block 2a (risk=medium); on T007
    # done → wave-2 for /signals/.json + /dependencies/.json; etc. Rules are
    # additive and enqueued only when their parent completes.
]


def _window_iso(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


# ── resolve_evidence_gated ────────────────────────────────────────────────

def resolve_evidence_gated() -> dict[str, int]:
    """Delegate to factory_core.resolve_ready_tasks() which already handles
    dependency + evidence unblocking. Returns the counts dict."""
    counts = factory_core.resolve_ready_tasks()
    log.info("resolve_ready_tasks: %s", counts)
    return counts


# ── generate_followup_tasks ───────────────────────────────────────────────

def _existing_ids() -> set[str]:
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute("SELECT id FROM smedjan.tasks")
        return {r[0] for r in cur.fetchall()}


def generate_followup_tasks(dry_run: bool = False) -> int:
    """Enqueue canonical followups for tasks that completed in the last 24h."""
    inserted = 0
    existing = _existing_ids()

    with sources.smedjan_db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT id, title, done_at FROM smedjan.tasks "
            "WHERE status = 'done' AND done_at > %s "
            "ORDER BY done_at",
            (_window_iso(24),),
        )
        done_rows = cur.fetchall()

    if not done_rows:
        log.info("no done-tasks in last 24h; nothing to follow up")
        return 0

    for row in done_rows:
        parent_id = row["id"]
        for rule in FOLLOWUP_RULES:
            if rule["match_id"] != parent_id:
                continue
            for tmpl in rule["followups"]:
                new_id = f"{parent_id}{tmpl['id_suffix']}"
                if new_id in existing:
                    continue
                if dry_run:
                    log.info("DRY: would enqueue %s (parent %s)", new_id, parent_id)
                    inserted += 1
                    continue
                with sources.smedjan_db_cursor() as (_, icur):
                    icur.execute(
                        """
                        INSERT INTO smedjan.tasks
                            (id, title, description, acceptance_criteria,
                             risk_level, whitelisted_files, priority,
                             session_group, dependencies, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (
                            new_id, tmpl["title"], tmpl["description"],
                            tmpl["acceptance_criteria"], tmpl["risk_level"],
                            tmpl.get("whitelisted_files", []),
                            tmpl.get("priority", 100),
                            tmpl.get("session_group"),
                            [parent_id],
                        ),
                    )
                existing.add(new_id)
                inserted += 1
                log.info("enqueued followup %s (parent %s)", new_id, parent_id)

    if inserted and not dry_run:
        factory_core.resolve_ready_tasks()
    return inserted


# ── generate_quota_fill ───────────────────────────────────────────────────

# Classification by risk level is a coarse proxy for scale/iterate/explore:
#   risk=low  AND not is_fallback → "scale" (confident, ship-it)
#   risk=medium                   → "iterate" (needs human approval; tuning)
#   risk=high                     → "scale" (but gated) — counted as scale
#   is_fallback=true              → "explore" (fallback layer)
# Adjust the map below as Smedjan learns.

def _live_queue_composition() -> dict[str, int]:
    """Count tasks currently in the queue (pending + queued + needs_approval
    + approved) grouped into scale / iterate / explore buckets."""
    out = {"scale": 0, "iterate": 0, "explore": 0, "total": 0, "discordant": 0}
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(
            """
            SELECT risk_level, is_fallback, title, count(*)
            FROM smedjan.tasks
            WHERE status IN ('pending','queued','needs_approval','approved')
            GROUP BY 1, 2, 3
            """
        )
        for risk, is_fb, title, n in cur.fetchall():
            out["total"] += n
            if is_fb:
                out["explore"] += n
            elif risk == "medium":
                out["iterate"] += n
            else:
                out["scale"] += n
            # Soft discordant detector: title mentions "discord" / "contrarian"
            if "discord" in (title or "").lower() or "contrarian" in (title or "").lower():
                out["discordant"] += n
    return out


def generate_quota_fill(dry_run: bool = False) -> dict:
    """Observe and warn. v1 does not auto-create tasks to top-up quota; it
    logs drift so Anders (or a future Planner) can decide. Returns the
    composition + recommendation."""
    comp = _live_queue_composition()
    total = max(1, comp["total"])
    ratios = {
        "scale":   comp["scale"]   / total,
        "iterate": comp["iterate"] / total,
        "explore": comp["explore"] / total,
    }
    warnings: list[str] = []
    if ratios["scale"] < 0.70:
        warnings.append(f"scale={ratios['scale']:.0%} < 70%")
    if ratios["iterate"] < 0.20:
        warnings.append(f"iterate={ratios['iterate']:.0%} < 20%")
    if ratios["explore"] > 0.05:
        warnings.append(f"explore={ratios['explore']:.0%} > 5% (fallback-heavy queue)")
    if comp["discordant"] < 1:
        warnings.append("discordant=0 (need ≥1 contrarian hypothesis)")

    verdict = "ok" if not warnings else "drift"
    log.info("quota composition: %s ratios=%s verdict=%s", comp, {k: f"{v:.0%}" for k, v in ratios.items()}, verdict)
    for w in warnings:
        log.warning("quota warning: %s", w)
    return {"composition": comp, "ratios": ratios, "verdict": verdict, "warnings": warnings}


# ── main ──────────────────────────────────────────────────────────────────

def run(dry_run: bool = False) -> int:
    log.info("planner run start (dry_run=%s)", dry_run)
    resolved = resolve_evidence_gated()
    followups = generate_followup_tasks(dry_run=dry_run)
    quota = generate_quota_fill(dry_run=dry_run)

    # Broadcast a summary only when something non-trivial happened.
    material = followups > 0 or quota["warnings"]
    if material:
        body = (
            f"followups enqueued: {followups}\n"
            f"queue composition: {quota['composition']}\n"
            f"verdict: {quota['verdict']}\n"
            f"warnings: {', '.join(quota['warnings']) or 'none'}"
        )
        ntfy.push("[SMEDJAN] planner run", body, priority="default", tags="compass")

    log.info("planner run done followups=%d resolved=%s quota_verdict=%s",
             followups, resolved, quota["verdict"])
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser("smedjan-planner")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="single planner tick")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(fn=lambda a: run(dry_run=a.dry_run))
    args = p.parse_args(list(argv) if argv is not None else None)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
