"""
Smedjan weekly audit scheduler (F4).

Invoked by systemd at each of three weekly slots — Mon / Wed / Fri 04:00
Europe/Stockholm — to enqueue a self-contained audit task. The task itself
is executed later by the Mac Studio worker (claude -p); this module only
schedules it.

Usage
-----
    audit_scheduler.py --type {query|citation|conversion}

Responsibilities
----------------
1. Compute task id `AUDIT-{TYPE}-{YYYYMMDD}` (today, local).
2. INSERT into smedjan.tasks via sources.get_smedjan_db() with a
   self-contained description that references the matching audit doc at
   /home/smedjan/agentindex/docs/strategy/ and names the tables the worker
   should query.
3. Call factory_core.resolve_ready_tasks() so the row is promoted to
   needs_approval / queued / blocked immediately.
4. Print "scheduled {id}" to stdout.

Idempotency
-----------
Task ids embed the date (one run per weekday slot), so re-running on the
same day is a no-op conflict. The scheduler treats a duplicate-key error
as "already scheduled today" and exits 0.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

import psycopg2

from smedjan import factory_core
from smedjan.sources import get_smedjan_db


log = logging.getLogger("smedjan.audit_scheduler")


# ── Audit-type spec ──────────────────────────────────────────────────────

AUDIT_DOC_DIR = "/home/smedjan/agentindex/docs/strategy"
REPORT_DIR = "~/smedjan/audit-reports"

AUDIT_SPECS: dict[str, dict] = {
    "query": {
        "doc": f"{AUDIT_DOC_DIR}/nerq-query-audit-2026-04-17.md",
        "focus": (
            "AI-query hygiene — what prompts agents/humans send at Nerq, "
            "which return weak/empty results, which verticals are "
            "under-served by the current index."
        ),
        "analytics_tables": [
            "analytics_mirror.query_log",
            "analytics_mirror.search_events",
            "analytics_mirror.zero_result_queries",
        ],
        "nerq_ro_tables": [
            "public.agents",
            "public.entity_lookup",
            "public.query_coverage",
        ],
    },
    "citation": {
        "doc": f"{AUDIT_DOC_DIR}/nerq-citation-audit-2026-04-17.md",
        "focus": (
            "AI-citation surface — when external LLMs cite Nerq, which "
            "pages/entities they quote, whether trust scores are carried "
            "across, and which high-value pages are under-cited."
        ),
        "analytics_tables": [
            "analytics_mirror.citation_events",
            "analytics_mirror.ai_referrals",
            "analytics_mirror.page_performance",
        ],
        "nerq_ro_tables": [
            "public.agents",
            "public.entity_lookup",
            "public.nerq_risk_signals",
        ],
    },
    "conversion": {
        "doc": f"{AUDIT_DOC_DIR}/nerq-conversion-audit-2026-04-17.md",
        "focus": (
            "AI-to-human conversion — of visitors who arrived via AI "
            "citation, how many engage with Trust Scores, click through to "
            "ZARQ, or subscribe. Identify top-of-funnel drop-offs."
        ),
        "analytics_tables": [
            "analytics_mirror.session_log",
            "analytics_mirror.conversion_events",
            "analytics_mirror.funnel_steps",
        ],
        "nerq_ro_tables": [
            "public.agents",
            "public.entity_lookup",
            "public.crypto_rating_daily",
        ],
    },
}


# ── Description builder ──────────────────────────────────────────────────

def _build_description(audit_type: str, today_iso: str) -> str:
    spec = AUDIT_SPECS[audit_type]
    analytics_bullets = "\n".join(f"  - {t}" for t in spec["analytics_tables"])
    nerq_bullets = "\n".join(f"  - {t}" for t in spec["nerq_ro_tables"])
    report_path = f"{REPORT_DIR}/{today_iso}-{audit_type}.md"

    return (
        f"Weekly Nerq {audit_type} audit ({today_iso}).\n"
        f"\n"
        f"Focus\n-----\n{spec['focus']}\n"
        f"\n"
        f"Reference document\n------------------\n"
        f"Read the full audit brief at:\n"
        f"  {spec['doc']}\n"
        f"It defines the dimensions, severity rubric, and prior baseline.\n"
        f"\n"
        f"Data sources\n------------\n"
        f"Query analytics_mirror (read-only mirror of Nerq analytics) via\n"
        f"smedjan.sources.get_analytics_mirror(). Relevant tables:\n"
        f"{analytics_bullets}\n"
        f"\n"
        f"Query the Nerq read-only replica via\n"
        f"smedjan.sources.get_nerq_readonly(). Relevant tables:\n"
        f"{nerq_bullets}\n"
        f"\n"
        f"If either source is unreachable (SourceUnavailable), mark the\n"
        f"task blocked with reason and exit — do not invent data.\n"
        f"\n"
        f"Deliverable\n-----------\n"
        f"Write findings to:\n"
        f"  {report_path}\n"
        f"The report MUST contain at least 10 ## findings sections, each\n"
        f"with: title, severity (low|medium|high|critical), evidence\n"
        f"(SQL + numbers), recommendation, suggested follow-up task.\n"
        f"\n"
        f"Follow-up tasks\n---------------\n"
        f"For every finding with severity >= medium, enqueue a follow-up\n"
        f"task using the smedjan CLI, e.g.:\n"
        f"  smedjan queue add \\\n"
        f"    --id FU-{audit_type.upper()}-{today_iso.replace('-', '')}-NN \\\n"
        f"    --title \"...\" --description \"...\" \\\n"
        f"    --acceptance \"...\" --risk low --priority 60\n"
        f"Link each follow-up back to this audit id in its description.\n"
        f"\n"
        f"Forbidden paths (do not touch): agentindex/api/main.py, alembic/,\n"
        f"robots.txt, sitemap.xml, CLAUDE.md.\n"
    )


def _build_acceptance(audit_type: str, today_iso: str) -> str:
    report_path = f"{REPORT_DIR}/{today_iso}-{audit_type}.md"
    return (
        f"Audit report exists at {report_path} with >= 10 ## findings "
        f"sections. Each finding has explicit severity. For every finding "
        f"with severity >= medium, a corresponding FU-{audit_type.upper()}-* "
        f"follow-up task has been added to the smedjan queue."
    )


# ── Insert + resolve ─────────────────────────────────────────────────────

INSERT_SQL = """
INSERT INTO smedjan.tasks
    (id, title, description, acceptance_criteria,
     dependencies, risk_level, whitelisted_files,
     priority, status)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
"""


def schedule_audit(audit_type: str, *, today: datetime | None = None) -> str:
    if audit_type not in AUDIT_SPECS:
        raise ValueError(f"unknown audit type: {audit_type!r}")
    today = today or datetime.now().astimezone()
    today_iso = today.strftime("%Y-%m-%d")
    today_compact = today.strftime("%Y%m%d")
    task_id = f"AUDIT-{audit_type.upper()}-{today_compact}"

    title = f"Weekly {audit_type} audit — {today_iso}"
    description = _build_description(audit_type, today_iso)
    acceptance = _build_acceptance(audit_type, today_iso)
    whitelisted = ["smedjan/audit-reports/", "scripts/smedjan"]
    dependencies: list[str] = []

    conn = get_smedjan_db()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                INSERT_SQL,
                (
                    task_id,
                    title,
                    description,
                    acceptance,
                    dependencies,
                    "medium",
                    whitelisted,
                    40,
                ),
            )
    except psycopg2.errors.UniqueViolation:
        # Already scheduled today — idempotent.
        log.info("audit %s already scheduled today; skipping", task_id)
        return task_id
    finally:
        conn.close()

    factory_core.resolve_ready_tasks()
    return task_id


# ── CLI ──────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Schedule a weekly Nerq audit task.")
    parser.add_argument(
        "--type",
        required=True,
        choices=sorted(AUDIT_SPECS.keys()),
        help="Which audit to schedule.",
    )
    args = parser.parse_args(argv)

    task_id = schedule_audit(args.type)
    print(f"scheduled {task_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
