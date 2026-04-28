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
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import psycopg2
import psycopg2.extras

from smedjan import factory_core, sources

# Registry of synthetic scale-bucket task templates. Used by
# generate_quota_fill() when live-queue scale ratio < 70 % — the planner
# instantiates tasks from this file rather than only warning. Ships empty;
# templates are piled in over time without further code changes.
SCALE_TEMPLATES_PATH = Path(__file__).parent / "config" / "scale_templates.json"

log = logging.getLogger("smedjan.planner")


# ── ai_demand_scores priority bias ────────────────────────────────────────
# Percentile thresholds from smedjan.ai_demand_scores (last snapshot).
# A task whose text mentions a slug in these tiers gets its priority bumped:
#   top 1 %  → 10   (urgent: the slug is generating real AI demand today)
#   top 10 % → 20
#   otherwise → template default (unchanged)
# Slugs shorter than 4 chars or containing non-[a-z0-9_-] chars are skipped
# — they cause too many false-positive substring matches in task text.
_DEMAND_PRIORITY_TOP_1 = 10
_DEMAND_PRIORITY_TOP_10 = 20
_DEMAND_PRIORITY_REMAINDER = 50
_SLUG_WORDLIKE = re.compile(r"^[a-z0-9][a-z0-9_-]{3,}$")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")

# Cached within the planner tick, keyed on snapshot computed_at timestamp.
_DEMAND_CACHE: dict[str, tuple[frozenset[str], frozenset[str]]] = {}


def _load_demand_percentiles() -> tuple[frozenset[str], frozenset[str]]:
    """Return (top_1pct, top_10pct) slug sets from the latest snapshot.

    Caches within the planner tick on the snapshot timestamp, so one planner
    run costs exactly one read of ai_demand_scores even across many callers.
    """
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute("SELECT max(computed_at) FROM smedjan.ai_demand_scores")
        row = cur.fetchone()
    max_ts = row[0] if row else None
    if max_ts is None:
        return frozenset(), frozenset()
    key = max_ts.isoformat()
    cached = _DEMAND_CACHE.get(key)
    if cached is not None:
        return cached
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(
            "SELECT slug FROM smedjan.ai_demand_scores "
            "WHERE computed_at = %s ORDER BY score DESC",
            (max_ts,),
        )
        ordered = [r[0] for r in cur.fetchall() if r[0] and _SLUG_WORDLIKE.match(r[0])]
    n = len(ordered)
    if n == 0:
        _DEMAND_CACHE.clear()
        _DEMAND_CACHE[key] = (frozenset(), frozenset())
        return _DEMAND_CACHE[key]
    top_1 = frozenset(ordered[: max(1, n // 100)])
    top_10 = frozenset(ordered[: max(1, n // 10)])
    _DEMAND_CACHE.clear()
    _DEMAND_CACHE[key] = (top_1, top_10)
    return top_1, top_10


def _match_demand_tier(text: str) -> tuple[int | None, str | None, str | None]:
    """Inspect `text` for any reference to a demand-tier slug.

    Returns (priority, matched_slug, pct_label) where priority is 10/20 for
    top-1/top-10 matches, or (None, None, None) if no tier-relevant slug is
    mentioned. Token membership check is O(tokens) after percentile load.
    """
    if not text:
        return None, None, None
    top_1, top_10 = _load_demand_percentiles()
    if not top_1 and not top_10:
        return None, None, None
    tokens = set(_TOKEN_RE.findall(text.lower()))
    hit = tokens & top_1
    if hit:
        return _DEMAND_PRIORITY_TOP_1, next(iter(hit)), "1"
    hit = tokens & (top_10 - top_1)
    if hit:
        return _DEMAND_PRIORITY_TOP_10, next(iter(hit)), "10"
    return None, None, None


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
                template_priority = tmpl.get("priority", 100)
                combined_text = " ".join(
                    filter(None, [tmpl.get("title"), tmpl.get("description"),
                                  tmpl.get("acceptance_criteria")])
                )
                biased, matched, pct = _match_demand_tier(combined_text)
                effective_priority = template_priority
                if biased is not None and biased < template_priority:
                    log.info(
                        "priority bump: slug=%s pct=%s%% old=%d new=%d (followup=%s)",
                        matched, pct, template_priority, biased, new_id,
                    )
                    effective_priority = biased
                if dry_run:
                    log.info("DRY: would enqueue %s (parent %s) priority=%d",
                             new_id, parent_id, effective_priority)
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
                            effective_priority,
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


def _bump_queue_priorities(dry_run: bool) -> int:
    """Scan active queue; bump priority on tasks that reference a top-tier
    demand slug. Bumps only raise urgency (current_priority > new_priority);
    we never demote a deliberately-chosen priority. Returns bump count.
    """
    with sources.smedjan_db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT id, title, description, acceptance_criteria, priority
            FROM smedjan.tasks
            WHERE status IN ('pending','queued','needs_approval','approved')
            """
        )
        rows = cur.fetchall()

    bumps: list[tuple[str, int, int]] = []
    for row in rows:
        combined = " ".join(
            filter(None, [row["title"], row["description"], row["acceptance_criteria"]])
        )
        biased, matched, pct = _match_demand_tier(combined)
        if biased is None:
            continue
        current = row["priority"]
        if biased >= current:
            continue
        log.info(
            "priority bump: slug=%s pct=%s%% old=%d new=%d (task=%s)",
            matched, pct, current, biased, row["id"],
        )
        bumps.append((row["id"], current, biased))

    if bumps and not dry_run:
        with sources.smedjan_db_cursor() as (_, cur):
            for task_id, _old, new in bumps:
                cur.execute(
                    "UPDATE smedjan.tasks SET priority = %s WHERE id = %s",
                    (new, task_id),
                )
    return len(bumps)


def _load_scale_templates() -> list[dict]:
    """Read scale_templates.json. Returns [] if the file is missing,
    malformed, or contains no templates — callers treat that as 'nothing
    to rebalance with, just warn' rather than a hard error."""
    try:
        raw = SCALE_TEMPLATES_PATH.read_text()
    except FileNotFoundError:
        log.info("scale_templates.json missing at %s — no auto-rebalance", SCALE_TEMPLATES_PATH)
        return []
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("scale_templates.json invalid JSON: %s", exc)
        return []
    templates = doc.get("templates") if isinstance(doc, dict) else None
    if not isinstance(templates, list):
        log.error("scale_templates.json missing top-level list 'templates'")
        return []
    return templates


def _generate_scale_fillers(dry_run: bool) -> int:
    """Instantiate one task per scale_templates.json entry whose synthetic
    id isn't already present. id = id_prefix + UTC date suffix, so a given
    template can top up the queue at most once per UTC day. Returns the
    number of tasks inserted (or would-insert under dry_run)."""
    templates = _load_scale_templates()
    if not templates:
        return 0

    existing = _existing_ids()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    inserted = 0

    for tmpl in templates:
        prefix = tmpl.get("id_prefix")
        title = tmpl.get("title")
        if not prefix or not title:
            log.warning("skipping malformed scale template: %s", tmpl)
            continue
        new_id = f"{prefix}-{today}"
        if new_id in existing:
            continue
        risk = tmpl.get("risk_level", "low")
        if risk != "low":
            log.warning("scale template %s has risk_level=%s; refusing to auto-enqueue", prefix, risk)
            continue
        priority = tmpl.get("priority", 60)
        if dry_run:
            log.info("DRY: would enqueue scale filler %s (priority=%d)", new_id, priority)
            inserted += 1
            existing.add(new_id)
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
                    new_id, title,
                    tmpl.get("description", ""),
                    tmpl.get("acceptance_criteria", ""),
                    risk,
                    tmpl.get("whitelisted_files", []),
                    priority,
                    tmpl.get("session_group"),
                    [],
                ),
            )
        existing.add(new_id)
        inserted += 1
        log.info("enqueued scale filler %s", new_id)

    if inserted and not dry_run:
        factory_core.resolve_ready_tasks()
    return inserted


def generate_quota_fill(dry_run: bool = False) -> dict:
    """Observe, warn, and act. When scale ratio < 70 %, instantiate
    synthetic scale-bucket tasks from smedjan/config/scale_templates.json
    (idempotent per UTC day). Also bumps priority on active-queue tasks
    that reference a top-tier ai_demand_scores slug. Returns the
    composition + recommendation + action counters."""
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

    scale_fillers = 0
    if ratios["scale"] < 0.70:
        scale_fillers = _generate_scale_fillers(dry_run=dry_run)
        log.info("scale-rebalance action: %d filler task(s) %s",
                 scale_fillers, "dry-run" if dry_run else "enqueued")

    demand_bumps = _bump_queue_priorities(dry_run=dry_run)

    return {
        "composition": comp,
        "ratios": ratios,
        "verdict": verdict,
        "warnings": warnings,
        "demand_bumps": demand_bumps,
        "scale_fillers": scale_fillers,
    }


# ── main ──────────────────────────────────────────────────────────────────

def run(dry_run: bool = False) -> int:
    log.info("planner run start (dry_run=%s)", dry_run)
    resolved = resolve_evidence_gated()
    followups = generate_followup_tasks(dry_run=dry_run)
    quota = generate_quota_fill(dry_run=dry_run)

    # Autonomous backlog top-up. Runs last so that resolver + followups
    # get to surface all their work first — we only seed from backlog
    # when the queue is actually below the threshold after the planner
    # has done its usual job. Never crashes the planner on failure.
    backlog_summary: dict = {}
    try:
        from smedjan import backlog_seeder
        backlog_summary = backlog_seeder.run(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        log.warning("backlog seeder failed: %s", exc)
        backlog_summary = {"reason": f"error:{exc}"}

    # Broadcast a summary only when something non-trivial happened.
    # Planner run summary is telemetry — goes to log + dashboard queue.
    # ntfy stays silent on normal operation per the action-required policy.
    log.info(
        "planner run done followups=%d resolved=%s quota_verdict=%s "
        "backlog_seeded=%s warnings=%s",
        followups, resolved, quota["verdict"],
        backlog_summary.get("seeded") or backlog_summary.get("reason"),
        ", ".join(quota["warnings"]) or "none",
    )
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
