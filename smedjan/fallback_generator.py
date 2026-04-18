"""
Smedjan fallback-task generator (F3 of the autonomy rollout).

Keeps the Smedjan fallback queue primed so the worker always has something
low-priority to do when the primary queue is empty.

Policy
------
For each fallback category (F1, F2, F3):

1. Count live fallback tasks — `status IN ('pending','queued','approved',
   'in_progress') AND is_fallback = true AND fallback_category = <cat>`.
2. If that count is < TARGET_PER_CATEGORY (10), insert as many new tasks
   as needed to top the category up to TARGET_PER_CATEGORY.
3. Each generated task gets id `FB-{cat}-{YYYYMMDD}-{NNN}` where NNN is a
   3-digit per-day per-category counter (starts after the largest NNN
   already present in smedjan.tasks for that (cat, date)).
4. After inserting, call `factory_core.resolve_ready_tasks()` so the
   low-risk + whitelisted rows flip pending -> queued immediately and
   become claimable by the worker.

Invariants kept by this module
------------------------------
- All DB access goes through `smedjan.sources.get_smedjan_db()` — no
  hard-coded DSN (see sources.py contract).
- Tasks inserted with priority=10, risk_level='low', is_fallback=true,
  whitelisted_files=['smedjan/audits/'] so `compute_ready_status()` in
  factory_core auto-yes's them.
- Dependencies=[] and wait_for_evidence=NULL so `resolve_ready_tasks`
  promotes them on the same run.
- ON CONFLICT (id) DO NOTHING keeps the run idempotent in the (unlikely)
  case of an id collision.

Entrypoint
----------
Run as `python3 -m smedjan.fallback_generator`. Designed for the systemd
timer `smedjan-fallback-generator.timer` (every 6h).
"""
from __future__ import annotations

import logging
import re
import sys
from datetime import datetime, timezone

import psycopg2.extras

from smedjan import factory_core
from smedjan.sources import get_smedjan_db

log = logging.getLogger("smedjan.fallback_generator")


TARGET_PER_CATEGORY = 10
LIVE_STATUSES = ("pending", "queued", "approved", "in_progress")
CATEGORIES = ("F1", "F2", "F3")


# ── Per-category task template ────────────────────────────────────────────
#
# Each template is SELF-CONTAINED: the worker feeds `description` straight
# into `claude -p`, so it must carry every instruction the agent needs.
# `{date}` and `{task_id}` are substituted at generation time so each task
# writes to a unique output path.

_TEMPLATES: dict[str, dict[str, str]] = {
    "F1": {
        "title": "F1 quality_audit: random /safe/* antipattern spot-check",
        "description": (
            "Fallback-generated quality audit. Curl 100 random enriched "
            "/safe/<slug> pages on https://nerq.ai (pick slugs via SELECT slug "
            "FROM software_registry WHERE enriched_at IS NOT NULL ORDER BY "
            "random() LIMIT 100 on the Nerq read-only source; sources.py -> "
            "get_nerq_readonly()). For each page, grep the rendered HTML for "
            "these antipatterns: literal 'None', literal 'null', empty "
            "<td></td> cells, and broken schema.org markup (no valid JSON-LD "
            "script tag, or a JSON-LD block that fails json.loads). Write "
            "findings to ~/smedjan/audits/{task_id}.md with a table of "
            "(finding, count, sample_slugs[:3]). If any single antipattern "
            "affects more than 5 pages, return STATUS: needs_approval in the "
            "task-result block with the finding description — Anders picks "
            "the fix task. Otherwise STATUS: done with EVIDENCE "
            "{\"pages_checked\": 100, \"findings\": <count>}."
        ),
        "acceptance_criteria": (
            "File ~/smedjan/audits/{task_id}.md exists and is non-empty. "
            "It contains a table (markdown pipes) summarising the 100-sample "
            "scan. EVIDENCE block reports pages_checked=100. Any antipattern "
            "with count > 5 escalates via STATUS: needs_approval rather than "
            "done."
        ),
    },
    "F2": {
        "title": "F2 freshness_refresh: 200 oldest top-5-registry enriched entries",
        "description": (
            "Fallback-generated freshness prep. Read-only. Against the Nerq "
            "read-only source (sources.get_nerq_readonly()), determine the "
            "top-5 registries by ai_demand_score coverage (join "
            "smedjan.ai_demand_scores -> software_registry, count rows per "
            "registry, take the 5 largest). Then run: SELECT slug, registry, "
            "enriched_at FROM software_registry WHERE registry IN (<top5>) "
            "ORDER BY registry, enriched_at ASC LIMIT 200. Write the result "
            "to ~/smedjan/audits/{task_id}.csv with header "
            "'slug,registry,enriched_at,ai_demand_score'. Sort is "
            "(registry ASC, enriched_at ASC). No enricher call — this is "
            "prep work only, a later non-fallback task consumes the CSV."
        ),
        "acceptance_criteria": (
            "File ~/smedjan/audits/{task_id}.csv exists with exactly 201 "
            "lines (1 header + 200 data rows). Rows sorted by (registry, "
            "enriched_at ASC). EVIDENCE reports row_count=200 and the five "
            "registries picked."
        ),
    },
    "F3": {
        "title": "F3 internal_linking: /compare/ coverage proposals for 50 top pairs",
        "description": (
            "Fallback-generated linking proposal. Against the Nerq read-only "
            "source, pair the 50 highest-demand slugs within the same "
            "registry using smedjan.ai_demand_scores (top demand per "
            "registry, then cross-pair within each registry — limit total "
            "output to 50 pairs). For each pair (a, b) curl "
            "https://nerq.ai/compare/<a>-vs-<b> and record the HTTP status. "
            "Write proposals to ~/smedjan/audits/{task_id}.md as a markdown "
            "table: registry | slug_a | slug_b | http_status | "
            "recommendation. Recommendation is 'create' if status is 404, "
            "'skip' if 200, 'investigate' otherwise. No page creation — "
            "Anders or a follow-up task materialises the 'create' rows."
        ),
        "acceptance_criteria": (
            "File ~/smedjan/audits/{task_id}.md exists and contains a table "
            "of exactly 50 data rows plus header. recommendation column is "
            "populated for every row. EVIDENCE reports counts_by_status "
            "({\"200\": ..., \"404\": ..., \"other\": ...})."
        ),
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────

_ID_RX = re.compile(r"^FB-(F[123])-(\d{8})-(\d{3})$")


def _current_counts(cur) -> dict[str, int]:
    # `status` is the smedjan.task_status enum; `fallback_category` is text.
    # Cast status::text so we can compare against a plain text[] array
    # without having to know the enum's fully-qualified type name.
    cur.execute(
        """
        SELECT fallback_category, count(*)
        FROM smedjan.tasks
        WHERE is_fallback = true
          AND status::text = ANY(%s)
          AND fallback_category = ANY(%s)
        GROUP BY fallback_category
        """,
        (list(LIVE_STATUSES), list(CATEGORIES)),
    )
    out = {c: 0 for c in CATEGORIES}
    for cat, n in cur.fetchall():
        out[cat] = int(n)
    return out


def _max_counter_today(cur, cat: str, date_str: str) -> int:
    """Largest NNN already present among FB-{cat}-{date}-NNN ids. 0 if none."""
    cur.execute(
        """
        SELECT id FROM smedjan.tasks
        WHERE id LIKE %s
        """,
        (f"FB-{cat}-{date_str}-%",),
    )
    mx = 0
    for (task_id,) in cur.fetchall():
        m = _ID_RX.match(task_id)
        if m and m.group(1) == cat and m.group(2) == date_str:
            mx = max(mx, int(m.group(3)))
    return mx


def _substitute(text: str, task_id: str, date_str: str) -> str:
    """Light-weight placeholder substitution that does NOT use str.format —
    template bodies contain JSON literals with braces (e.g. {"k": "v"})
    which str.format would choke on.
    """
    return (
        text
        .replace("{task_id}", task_id)
        .replace("{date}", date_str)
    )


def _build_task(cat: str, task_id: str, date_str: str) -> dict:
    tpl = _TEMPLATES[cat]
    return {
        "id": task_id,
        "title": f"{tpl['title']} ({date_str} {task_id[-3:]})",
        "description": _substitute(tpl["description"], task_id, date_str),
        "acceptance_criteria": _substitute(tpl["acceptance_criteria"], task_id, date_str),
        "dependencies": [],
        "risk_level": "low",
        "whitelisted_files": ["smedjan/audits/"],
        "priority": 10,
        "is_fallback": True,
        "fallback_category": cat,
        "status": "pending",
    }


def _insert_task(cur, t: dict) -> bool:
    cur.execute(
        """
        INSERT INTO smedjan.tasks (
            id, title, description, acceptance_criteria,
            dependencies, risk_level, whitelisted_files, priority,
            is_fallback, fallback_category, status
        ) VALUES (
            %(id)s, %(title)s, %(description)s, %(acceptance_criteria)s,
            %(dependencies)s, %(risk_level)s, %(whitelisted_files)s, %(priority)s,
            %(is_fallback)s, %(fallback_category)s, %(status)s
        )
        ON CONFLICT (id) DO NOTHING
        """,
        t,
    )
    return cur.rowcount == 1


# ── Main entrypoint ───────────────────────────────────────────────────────

def generate() -> dict[str, int]:
    """Top each fallback category up to TARGET_PER_CATEGORY. Returns the
    per-category count of tasks inserted in this run.
    """
    generated: dict[str, int] = {c: 0 for c in CATEGORIES}
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    conn = get_smedjan_db()
    try:
        with conn.cursor() as cur:
            counts = _current_counts(cur)
            log.info("live fallback counts: %s (target %d)", counts, TARGET_PER_CATEGORY)

            for cat in CATEGORIES:
                shortfall = TARGET_PER_CATEGORY - counts.get(cat, 0)
                if shortfall <= 0:
                    continue
                counter = _max_counter_today(cur, cat, date_str)
                for _ in range(shortfall):
                    counter += 1
                    task_id = f"FB-{cat}-{date_str}-{counter:03d}"
                    task = _build_task(cat, task_id, date_str)
                    if _insert_task(cur, task):
                        generated[cat] += 1
                    # If insert conflicted (already exists) just move on to
                    # next counter — loop bound ensures we still try the
                    # full shortfall count.
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Promote freshly-inserted pending rows to queued (auto-yes because
    # risk=low + whitelist is under smedjan/audits/).
    resolve_summary = factory_core.resolve_ready_tasks()
    log.info("resolve_ready_tasks summary: %s", resolve_summary)

    return generated


def _print_summary(generated: dict[str, int]) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total = sum(generated.values())
    print(f"[{now}] fallback_generator: generated {total} task(s)")
    for cat in CATEGORIES:
        print(f"  {cat}: +{generated[cat]}")

    # Re-query post-state so the log tells you whether the target is met.
    conn = get_smedjan_db()
    try:
        with conn.cursor() as cur:
            post = _current_counts(cur)
    finally:
        conn.close()
    print(f"[{now}] post-run live counts: {post} (target {TARGET_PER_CATEGORY})")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        generated = generate()
    except Exception as e:  # noqa: BLE001 — top-level guard for systemd
        log.exception("fallback_generator failed: %s", e)
        return 1
    _print_summary(generated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
