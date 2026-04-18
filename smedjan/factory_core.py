"""
Factory Core — the DB-backed brains of the Smedjan task queue.

Exposes seven operations used by `cli.py` and `worker.py`:

    resolve_ready_tasks()   — promote pending → queued/needs_approval when
                              deps complete or evidence lands
    claim_next_task()       — SELECT ... FOR UPDATE SKIP LOCKED, honours
                              scheduled_start_at + approval + deps
    mark_done()             — in_progress → done + output_paths + evidence
    mark_blocked()          — any → blocked + reason
    mark_needs_approval()   — any → needs_approval + reason
    approve()               — needs_approval → approved + scheduled_start_at
    record_evidence()       — upsert evidence_signals row

All SQL lives here; no raw SQL outside this module.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg2
import psycopg2.extras

from smedjan.config import (
    AUTO_YES_WHITELIST_PREFIXES,
    FORBIDDEN_PATHS,
    PG_PRIMARY_DSN,
)

log = logging.getLogger("smedjan.factory_core")


# ── Task dataclass ────────────────────────────────────────────────────────

@dataclass
class Task:
    id: str
    title: str
    description: str
    acceptance_criteria: str
    dependencies: list[str]
    risk_level: str
    whitelisted_files: list[str]
    status: str
    claimed_by: str | None
    claimed_at: datetime | None
    done_at: datetime | None
    blocker_reason: str | None
    output_paths: list[str]
    priority: int
    created_at: datetime
    session_group: str | None
    scheduled_start_at: datetime | None
    wait_for_evidence: str | None
    is_fallback: bool
    fallback_category: str | None
    evidence: Any
    notes: str | None

    @classmethod
    def from_row(cls, row: dict) -> "Task":
        return cls(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            acceptance_criteria=row["acceptance_criteria"],
            dependencies=row["dependencies"] or [],
            risk_level=row["risk_level"],
            whitelisted_files=row["whitelisted_files"] or [],
            status=row["status"],
            claimed_by=row["claimed_by"],
            claimed_at=row["claimed_at"],
            done_at=row["done_at"],
            blocker_reason=row["blocker_reason"],
            output_paths=row["output_paths"] or [],
            priority=row["priority"],
            created_at=row["created_at"],
            session_group=row["session_group"],
            scheduled_start_at=row["scheduled_start_at"],
            wait_for_evidence=row["wait_for_evidence"],
            is_fallback=row["is_fallback"],
            fallback_category=row["fallback_category"],
            evidence=row["evidence"],
            notes=row["notes"],
        )


# ── Connection helper ────────────────────────────────────────────────────

def _connect():
    return psycopg2.connect(PG_PRIMARY_DSN)


# ── Auto-yes policy ──────────────────────────────────────────────────────

def _is_whitelisted(path: str) -> bool:
    path = path.strip()
    if not path:
        return False
    for prefix in AUTO_YES_WHITELIST_PREFIXES:
        if path == prefix or path.startswith(prefix):
            return True
    return False


def _touches_forbidden(paths: list[str]) -> list[str]:
    hits: list[str] = []
    for p in paths:
        p_clean = (p or "").strip()
        for forbidden in FORBIDDEN_PATHS:
            if p_clean == forbidden or p_clean.startswith(forbidden):
                hits.append(p_clean)
                break
    return hits


def compute_ready_status(
    risk_level: str,
    whitelisted_files: list[str],
    forbidden_hits: list[str],
) -> str:
    """Given a task whose deps + evidence are resolved, decide whether it can
    skip approval.  Returns the *target* status: 'queued' | 'needs_approval'
    | 'blocked'.
    """
    if forbidden_hits:
        return "blocked"
    if risk_level == "low" and whitelisted_files and all(_is_whitelisted(p) for p in whitelisted_files):
        return "queued"
    return "needs_approval"


# ── Resolve ready tasks ──────────────────────────────────────────────────

def resolve_ready_tasks() -> dict[str, int]:
    """Promote `pending` rows to `queued` / `needs_approval` / `blocked` when
    dependencies are done and evidence signals have landed. Returns a count
    summary keyed by new status.
    """
    counts = {"queued": 0, "needs_approval": 0, "blocked": 0, "pending": 0}
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM smedjan.tasks WHERE status = 'pending' "
            "ORDER BY priority, created_at"
        )
        pending = [Task.from_row(r) for r in cur.fetchall()]

        # Build a snapshot of completed task ids + available signals.
        cur.execute("SELECT id FROM smedjan.tasks WHERE status = 'done'")
        done_ids = {r["id"] for r in cur.fetchall()}
        cur.execute("SELECT name FROM smedjan.evidence_signals")
        signals = {r["name"] for r in cur.fetchall()}

        for t in pending:
            if any(dep not in done_ids for dep in t.dependencies):
                counts["pending"] += 1
                continue
            if t.wait_for_evidence and t.wait_for_evidence not in signals:
                counts["pending"] += 1
                continue

            forbidden_hits = _touches_forbidden(t.whitelisted_files)
            new_status = compute_ready_status(t.risk_level, t.whitelisted_files, forbidden_hits)

            if new_status == "blocked":
                cur.execute(
                    """
                    UPDATE smedjan.tasks
                    SET status = 'blocked',
                        blocker_reason = %s
                    WHERE id = %s AND status = 'pending'
                    """,
                    (f"Whitelist touches forbidden path(s): {forbidden_hits}", t.id),
                )
            else:
                cur.execute(
                    """
                    UPDATE smedjan.tasks SET status = %s
                    WHERE id = %s AND status = 'pending'
                    """,
                    (new_status, t.id),
                )
            counts[new_status] += 1

    log.info("resolve_ready_tasks: %s", counts)
    return counts


# ── Claim next task ──────────────────────────────────────────────────────

CLAIM_SQL = """
WITH cte AS (
    SELECT id
    FROM smedjan.tasks
    WHERE (
          status = 'queued'
          OR (status = 'approved'
              AND (scheduled_start_at IS NULL OR scheduled_start_at <= now()))
      )
      AND NOT is_fallback
    ORDER BY priority, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE smedjan.tasks t
   SET status      = 'in_progress',
       claimed_by  = %s,
       claimed_at  = now()
  FROM cte
 WHERE t.id = cte.id
RETURNING t.*;
"""

CLAIM_FALLBACK_SQL = """
WITH cte AS (
    SELECT id
    FROM smedjan.tasks
    WHERE (
          status = 'queued'
          OR (status = 'approved'
              AND (scheduled_start_at IS NULL OR scheduled_start_at <= now()))
      )
      AND is_fallback
    ORDER BY
        CASE fallback_category
            WHEN 'F1' THEN 1
            WHEN 'F2' THEN 2
            WHEN 'F3' THEN 3
            ELSE 4 END,
        priority, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE smedjan.tasks t
   SET status      = 'in_progress',
       claimed_by  = %s,
       claimed_at  = now()
  FROM cte
 WHERE t.id = cte.id
RETURNING t.*;
"""


def claim_next_task(worker_id: str, *, include_fallback: bool = True) -> Task | None:
    """Atomically claim the highest-priority ready task for `worker_id`.

    Primary queue is tried first; the fallback layer (F1 > F2 > F3) is only
    consulted when the primary queue is empty.
    """
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(CLAIM_SQL, (worker_id,))
        row = cur.fetchone()
        if row is None and include_fallback:
            cur.execute(CLAIM_FALLBACK_SQL, (worker_id,))
            row = cur.fetchone()
    return Task.from_row(row) if row else None


# ── Peek (for `smedjan queue next` — no state change) ────────────────────

PEEK_SQL = """
SELECT * FROM smedjan.tasks
WHERE (
      status = 'queued'
      OR (status = 'approved'
          AND (scheduled_start_at IS NULL OR scheduled_start_at <= now()))
  )
ORDER BY is_fallback,
         CASE fallback_category
             WHEN 'F1' THEN 1
             WHEN 'F2' THEN 2
             WHEN 'F3' THEN 3
             ELSE 0 END,
         priority, created_at
LIMIT 1;
"""


def peek_next_task() -> Task | None:
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(PEEK_SQL)
        row = cur.fetchone()
    return Task.from_row(row) if row else None


# ── Terminal transitions ─────────────────────────────────────────────────

def mark_done(task_id: str, output_paths: list[str], evidence: dict | None, notes: str | None) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE smedjan.tasks
               SET status       = 'done',
                   done_at      = now(),
                   output_paths = %s,
                   evidence     = %s,
                   notes        = %s
             WHERE id = %s
            """,
            (output_paths, json.dumps(evidence) if evidence else None, notes, task_id),
        )


def mark_blocked(task_id: str, reason: str) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE smedjan.tasks
               SET status = 'blocked',
                   blocker_reason = %s
             WHERE id = %s
            """,
            (reason, task_id),
        )


def mark_needs_approval(task_id: str, reason: str) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE smedjan.tasks
               SET status = 'needs_approval',
                   blocker_reason = %s
             WHERE id = %s
            """,
            (reason, task_id),
        )


# ── Approval ─────────────────────────────────────────────────────────────

class ApprovalError(ValueError):
    """Raised by `approve()` when input violates the approval policy."""


def approve(task_id: str, *, approver: str, start_at: datetime | None = None) -> Task:
    """needs_approval → approved. For risk=high, start_at is required."""
    with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM smedjan.tasks WHERE id = %s FOR UPDATE", (task_id,))
        row = cur.fetchone()
        if row is None:
            raise ApprovalError(f"task {task_id} not found")
        if row["status"] != "needs_approval":
            raise ApprovalError(
                f"task {task_id} is {row['status']}, only needs_approval can be approved"
            )
        if row["risk_level"] == "high" and start_at is None:
            raise ApprovalError(
                f"task {task_id} is risk=high — --start-at is required"
            )
        cur.execute(
            """
            UPDATE smedjan.tasks
               SET status            = 'approved',
                   approved_by       = %s,
                   approved_at       = now(),
                   scheduled_start_at= %s,
                   blocker_reason    = NULL
             WHERE id = %s
             RETURNING *
            """,
            (approver, start_at, task_id),
        )
        return Task.from_row(cur.fetchone())


# ── Evidence signals ─────────────────────────────────────────────────────

def record_evidence(name: str, payload: dict | None = None, created_by: str | None = None) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO smedjan.evidence_signals (name, payload, created_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO UPDATE
              SET payload      = EXCLUDED.payload,
                  created_by   = EXCLUDED.created_by,
                  available_at = now()
            """,
            (name, json.dumps(payload) if payload else None, created_by),
        )


# ── Worker heartbeat ─────────────────────────────────────────────────────

def heartbeat(worker_id: str, current_task: str | None, note: str | None = None) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO smedjan.worker_heartbeats (worker_id, last_seen_at, current_task, note)
            VALUES (%s, now(), %s, %s)
            ON CONFLICT (worker_id) DO UPDATE
              SET last_seen_at = EXCLUDED.last_seen_at,
                  current_task = EXCLUDED.current_task,
                  note         = EXCLUDED.note
            """,
            (worker_id, current_task, note),
        )


# ── Structured output parsing ────────────────────────────────────────────

_BLOCK_RX = re.compile(
    r"---TASK_RESULT---\s*\n(?P<body>.*?)\n---END_TASK_RESULT---",
    re.DOTALL,
)


class ResultParseError(ValueError):
    """Raised when the Claude CLI output does not contain a parseable
    ---TASK_RESULT--- block."""


def parse_task_result(stdout: str) -> dict[str, Any]:
    """Extract status / output_paths / evidence / notes from a Claude CLI run.
    The block is delimited by ---TASK_RESULT--- / ---END_TASK_RESULT---.

    A minimal result looks like:

        ---TASK_RESULT---
        STATUS: done
        OUTPUT_PATHS: smedjan/docs/monetization-tiers.md, smedjan/seeds/v2.sql
        EVIDENCE: {"rows_inserted": 128}
        NOTES: Tiering applied to 128 path patterns.
        ---END_TASK_RESULT---
    """
    m = _BLOCK_RX.search(stdout)
    if not m:
        raise ResultParseError("no ---TASK_RESULT--- block in stdout")
    body = m.group("body")

    out: dict[str, Any] = {"status": None, "output_paths": [], "evidence": None, "notes": None}
    # Known-key line parser. Keeps us resilient to trailing whitespace.
    for line in body.splitlines():
        key, _, val = line.partition(":")
        key = key.strip().upper()
        val = val.strip()
        if key == "STATUS":
            out["status"] = val.lower()
        elif key == "OUTPUT_PATHS":
            out["output_paths"] = [p.strip() for p in val.split(",") if p.strip()] if val else []
        elif key == "EVIDENCE":
            if val:
                try:
                    out["evidence"] = json.loads(val)
                except Exception:  # noqa: BLE001 — tolerate malformed JSON
                    out["evidence"] = {"_raw": val}
        elif key == "NOTES":
            out["notes"] = val

    if out["status"] not in {"done", "blocked", "needs_approval"}:
        raise ResultParseError(f"STATUS missing or invalid in block: {out['status']!r}")
    return out
