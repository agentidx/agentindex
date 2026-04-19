"""
Smedjan CLI — single entry point used by the `smedjan` shell wrapper.

Subcommands
-----------
    smedjan queue add --id T003 --title "..." --description "..." \
                      --acceptance "..." [--risk low|medium|high] \
                      [--deps T001,T002] [--whitelist path1,path2] \
                      [--priority 100] [--session-group L2] \
                      [--wait-for-evidence name] \
                      [--fallback F1|F2|F3]
    smedjan queue list [--status STATUS] [--registry REG]
    smedjan queue show TASK_ID
    smedjan queue approve TASK_ID [--start-at "YYYY-MM-DD HH:MM"]
    smedjan queue block TASK_ID --reason "..."
    smedjan queue next
    smedjan queue resolve           # promote pending rows
    smedjan queue evidence NAME [--payload '{"k":"v"}']  # record evidence
    smedjan queue heartbeats
    smedjan queue stats             # aggregate counts + durations + blockers
    smedjan rollback L1 [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from smedjan import factory_core
from smedjan.config import PG_PRIMARY_DSN


# ── rollback constants ───────────────────────────────────────────────────

NERQ_API_PLIST = os.path.expanduser("~/Library/LaunchAgents/com.nerq.api.plist")
NERQ_API_LABEL = "com.nerq.api"
L1_UNLOCK_KEY  = "L1_UNLOCK_REGISTRIES"
PLISTBUDDY     = "/usr/libexec/PlistBuddy"


# ── helpers ──────────────────────────────────────────────────────────────

def _conn():
    return psycopg2.connect(PG_PRIMARY_DSN)


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _parse_start_at(value: str | None) -> datetime | None:
    if not value:
        return None
    # Accept "YYYY-MM-DD HH:MM", ISO, or "YYYY-MM-DD". Local time → UTC.
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.astimezone()   # attach local tz
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"cannot parse --start-at {value!r}")


def _fmt_task_row(r: dict) -> str:
    tid = r["id"]
    status = r["status"]
    risk = r["risk_level"]
    title = (r["title"] or "")[:60]
    fb = r["fallback_category"] or ""
    deps = ",".join(r["dependencies"] or []) or "-"
    wait = r["wait_for_evidence"] or ""
    sched = r["scheduled_start_at"].isoformat(timespec="minutes") if r["scheduled_start_at"] else ""
    return f"{tid:6s} {status:15s} {risk:6s} {fb:3s} {deps:20s} {wait:22s} {sched:18s} {title}"


# ── subcommand handlers ──────────────────────────────────────────────────

def cmd_add(args: argparse.Namespace) -> int:
    deps    = _parse_csv(args.deps)
    wl      = _parse_csv(args.whitelist)

    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO smedjan.tasks
                (id, title, description, acceptance_criteria,
                 dependencies, risk_level, whitelisted_files,
                 priority, session_group, session_affinity,
                 wait_for_evidence,
                 is_fallback, fallback_category, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            """,
            (
                args.id, args.title, args.description, args.acceptance,
                deps, args.risk, wl,
                args.priority, args.session_group, args.session_affinity,
                args.wait_for_evidence,
                bool(args.fallback), args.fallback,
            ),
        )
    promoted = factory_core.resolve_ready_tasks()
    print(f"added {args.id} (pending) — resolver: {promoted}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    clauses, params = [], []
    if args.status:
        clauses.append("status = %s")
        params.append(args.status)
    if args.fallback_only:
        clauses.append("is_fallback = true")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT * FROM smedjan.tasks {where} "
            "ORDER BY priority, created_at",
            params,
        )
        rows = cur.fetchall()

    if not rows:
        print("(no tasks)")
        return 0
    print(f"{'id':6s} {'status':15s} {'risk':6s} {'fb':3s} {'deps':20s} {'evidence':22s} {'start_at':18s} title")
    print("-" * 140)
    for r in rows:
        print(_fmt_task_row(r))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    with _conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM smedjan.tasks WHERE id = %s", (args.id,))
        r = cur.fetchone()
    if r is None:
        print(f"task {args.id} not found", file=sys.stderr)
        return 1
    r_copy = dict(r)
    for k, v in r_copy.items():
        if isinstance(v, datetime):
            r_copy[k] = v.isoformat()
    print(json.dumps(r_copy, indent=2, default=str))
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    try:
        t = factory_core.approve(
            args.id,
            approver=os.environ.get("USER", "anders"),
            start_at=_parse_start_at(args.start_at),
            defer_until_dep_done=args.defer_until_dep_done,
        )
    except factory_core.ApprovalError as e:
        print(f"approve failed: {e}", file=sys.stderr)
        return 2
    if t.status == "pending" and t.deferred_start_at is not None:
        print(f"deferred {t.id} — will auto-promote to approved @ "
              f"{t.deferred_start_at.isoformat()} when deps clear")
    else:
        extra = f" (start_at={t.scheduled_start_at.isoformat()})" if t.scheduled_start_at else ""
        print(f"approved {t.id} — status={t.status}{extra}")
    return 0


def cmd_block(args: argparse.Namespace) -> int:
    factory_core.mark_blocked(args.id, args.reason)
    print(f"blocked {args.id}")
    return 0


def cmd_next(_args: argparse.Namespace) -> int:
    t = factory_core.peek_next_task()
    if t is None:
        print("(queue empty)")
        return 0
    print(f"{t.id} [{t.status}] risk={t.risk_level} fb={t.fallback_category or '-'} "
          f"priority={t.priority} session_group={t.session_group or '-'}")
    print(f"  title: {t.title}")
    if t.scheduled_start_at:
        print(f"  scheduled_start_at: {t.scheduled_start_at.isoformat()}")
    return 0


def cmd_resolve(_args: argparse.Namespace) -> int:
    counts = factory_core.resolve_ready_tasks()
    print(f"resolver: {counts}")
    return 0


def cmd_evidence(args: argparse.Namespace) -> int:
    payload = None
    if args.payload:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            print(f"--payload is not valid JSON: {e}", file=sys.stderr)
            return 2
    factory_core.record_evidence(args.name, payload=payload, created_by=os.environ.get("USER", "anders"))
    print(f"evidence {args.name} recorded")
    factory_core.resolve_ready_tasks()
    return 0


# ── rollback ─────────────────────────────────────────────────────────────

def _plist_has_l1_unlock() -> bool:
    """True iff :EnvironmentVariables:L1_UNLOCK_REGISTRIES exists in the plist."""
    r = subprocess.run(
        [PLISTBUDDY, "-c", f"Print :EnvironmentVariables:{L1_UNLOCK_KEY}", NERQ_API_PLIST],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def cmd_rollback_l1(args: argparse.Namespace) -> int:
    uid = os.getuid()
    delete_cmd   = [PLISTBUDDY, "-c", f"Delete :EnvironmentVariables:{L1_UNLOCK_KEY}", NERQ_API_PLIST]
    kickstart_cmd = ["launchctl", "kickstart", "-k", f"gui/{uid}/{NERQ_API_LABEL}"]

    if not _plist_has_l1_unlock():
        print(f"{L1_UNLOCK_KEY} not set in {NERQ_API_PLIST} — already rolled back, nothing to do.")
        return 0

    if args.dry_run:
        print("[dry-run] would run:")
        print("  " + " ".join(delete_cmd))
        print("  " + " ".join(kickstart_cmd))
        return 0

    print(f"removing {L1_UNLOCK_KEY} from {NERQ_API_PLIST} …")
    r = subprocess.run(delete_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"PlistBuddy Delete failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return 2

    print(f"kickstarting {NERQ_API_LABEL} …")
    r = subprocess.run(kickstart_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"launchctl kickstart failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return 2

    print(f"rollback L1: done — {L1_UNLOCK_KEY} removed, {NERQ_API_LABEL} kickstarted.")
    return 0


def cmd_stats(_args: argparse.Namespace) -> int:
    with _conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT status::text AS status, COUNT(*) AS n "
            "FROM smedjan.tasks GROUP BY status ORDER BY status"
        )
        by_status = cur.fetchall()

        cur.execute(
            "SELECT COALESCE(session_affinity, '(none)') AS session_affinity, "
            "       COUNT(*) AS n "
            "FROM smedjan.tasks GROUP BY 1 ORDER BY n DESC, 1"
        )
        by_affinity = cur.fetchall()

        cur.execute(
            "SELECT COALESCE(fallback_category, '(none)') AS fallback_category, "
            "       COUNT(*) AS n "
            "FROM smedjan.tasks GROUP BY 1 ORDER BY n DESC, 1"
        )
        by_fallback = cur.fetchall()

        cur.execute(
            """
            SELECT
                COUNT(*)                                                         AS n,
                percentile_cont(0.5)  WITHIN GROUP (ORDER BY duration_seconds)  AS p50,
                percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_seconds)  AS p95
            FROM (
                SELECT EXTRACT(EPOCH FROM (done_at - claimed_at)) AS duration_seconds
                FROM smedjan.tasks
                WHERE status = 'done'
                  AND done_at IS NOT NULL
                  AND claimed_at IS NOT NULL
                  AND done_at >= now() - interval '7 days'
                  AND done_at >= claimed_at
            ) d
            """
        )
        dur = cur.fetchone()

        cur.execute(
            """
            SELECT blocker_reason, COUNT(*) AS n
            FROM smedjan.tasks
            WHERE blocker_reason IS NOT NULL AND blocker_reason <> ''
            GROUP BY blocker_reason
            ORDER BY n DESC, blocker_reason
            LIMIT 3
            """
        )
        top_blockers = cur.fetchall()

    print("── tasks per status ─────────────────────────────────")
    for r in by_status:
        print(f"  {r['status']:16s} {r['n']:>6d}")

    print("\n── tasks per session_affinity ───────────────────────")
    for r in by_affinity:
        print(f"  {r['session_affinity']:16s} {r['n']:>6d}")

    print("\n── tasks per fallback_category ──────────────────────")
    for r in by_fallback:
        print(f"  {r['fallback_category']:16s} {r['n']:>6d}")

    print("\n── task duration (done, last 7d) ────────────────────")
    n = dur["n"] or 0
    if n == 0:
        print("  (no tasks completed in the last 7 days)")
    else:
        p50 = float(dur["p50"]) if dur["p50"] is not None else 0.0
        p95 = float(dur["p95"]) if dur["p95"] is not None else 0.0
        print(f"  sample n         {n:>6d}")
        print(f"  p50              {p50/60:>6.1f} min ({p50:.0f} s)")
        print(f"  p95              {p95/60:>6.1f} min ({p95:.0f} s)")

    print("\n── top 3 blockers ───────────────────────────────────")
    if not top_blockers:
        print("  (no blocker_reason values recorded)")
    else:
        for r in top_blockers:
            reason = (r["blocker_reason"] or "")[:60]
            print(f"  {r['n']:>3d}  {reason}")
    return 0


def cmd_heartbeats(_args: argparse.Namespace) -> int:
    with _conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM smedjan.worker_heartbeats ORDER BY last_seen_at DESC")
        rows = cur.fetchall()
    if not rows:
        print("(no workers have checked in)")
        return 0
    for r in rows:
        print(f"{r['worker_id']:20s} last_seen={r['last_seen_at'].isoformat(timespec='seconds')} "
              f"task={r['current_task'] or '-'} note={r['note'] or '-'}")
    return 0


# ── argparse setup ───────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("smedjan")
    sub = p.add_subparsers(dest="cmd", required=True)

    queue = sub.add_parser("queue", help="queue operations")
    qsub = queue.add_subparsers(dest="sub", required=True)

    add = qsub.add_parser("add", help="insert a task")
    add.add_argument("--id", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--description", required=True)
    add.add_argument("--acceptance", required=True)
    add.add_argument("--risk", choices=("low", "medium", "high"), default="low")
    add.add_argument("--deps", default="")
    add.add_argument("--whitelist", default="")
    add.add_argument("--priority", type=int, default=100)
    add.add_argument("--session-group", default=None, dest="session_group")
    add.add_argument("--session-affinity", default=None, dest="session_affinity",
                     choices=("a", "b", "c", "d"),
                     help="worker routing tag — workers with matching "
                          "SMEDJAN_WORKER_AFFINITY preferentially claim these")
    add.add_argument("--wait-for-evidence", default=None, dest="wait_for_evidence")
    add.add_argument("--fallback", choices=("F1", "F2", "F3"), default=None)
    add.set_defaults(fn=cmd_add)

    lst = qsub.add_parser("list", help="list tasks")
    lst.add_argument("--status", default=None)
    lst.add_argument("--fallback-only", action="store_true")
    lst.set_defaults(fn=cmd_list)

    show = qsub.add_parser("show", help="show task detail (JSON)")
    show.add_argument("id")
    show.set_defaults(fn=cmd_show)

    ap = qsub.add_parser("approve", help="needs_approval → approved")
    ap.add_argument("id")
    ap.add_argument("--start-at", default=None, dest="start_at",
                    help='YYYY-MM-DD HH:MM local time — required for risk=high')
    ap.add_argument("--defer-until-dep-done", action="store_true",
                    dest="defer_until_dep_done",
                    help="task is pending on a dep; stash start_at in "
                         "deferred_start_at and let the resolver promote to "
                         "approved automatically once deps clear")
    ap.set_defaults(fn=cmd_approve)

    blk = qsub.add_parser("block", help="force → blocked")
    blk.add_argument("id")
    blk.add_argument("--reason", required=True)
    blk.set_defaults(fn=cmd_block)

    nxt = qsub.add_parser("next", help="peek the next claimable task (no state change)")
    nxt.set_defaults(fn=cmd_next)

    rslv = qsub.add_parser("resolve", help="promote pending rows whose deps/evidence are ready")
    rslv.set_defaults(fn=cmd_resolve)

    ev = qsub.add_parser("evidence", help="record an evidence signal")
    ev.add_argument("name")
    ev.add_argument("--payload", default=None, help='JSON blob')
    ev.set_defaults(fn=cmd_evidence)

    hb = qsub.add_parser("heartbeats", help="list worker heartbeats")
    hb.set_defaults(fn=cmd_heartbeats)

    st = qsub.add_parser("stats", help="aggregate queue stats")
    st.set_defaults(fn=cmd_stats)

    rb = sub.add_parser("rollback", help="operational rollbacks")
    rbsub = rb.add_subparsers(dest="sub", required=True)

    rb_l1 = rbsub.add_parser(
        "L1",
        help="remove L1_UNLOCK_REGISTRIES from the nerq api plist and kickstart",
    )
    rb_l1.add_argument("--dry-run", action="store_true", dest="dry_run",
                       help="print the plist edit + kickstart without executing")
    rb_l1.set_defaults(fn=cmd_rollback_l1)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
