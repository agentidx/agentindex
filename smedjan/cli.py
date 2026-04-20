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
    smedjan queue evidence list                           # list recorded signals
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
    if args.name == "list":
        return cmd_evidence_list(args)
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


def cmd_evidence_list(_args: argparse.Namespace) -> int:
    with _conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT name, available_at, payload "
            "FROM smedjan.evidence_signals "
            "ORDER BY available_at DESC, name"
        )
        rows = cur.fetchall()
    if not rows:
        print("(no evidence signals)")
        return 0
    print(f"{'name':40s} {'available_at':26s} payload")
    print("-" * 110)
    for r in rows:
        name = (r["name"] or "")[:40]
        avail = r["available_at"].isoformat(timespec="seconds") if r["available_at"] else ""
        if r["payload"] is None:
            payload_summary = "-"
        else:
            payload_summary = json.dumps(r["payload"], separators=(",", ":"), default=str)
            if len(payload_summary) > 60:
                payload_summary = payload_summary[:57] + "..."
        print(f"{name:40s} {avail:26s} {payload_summary}")
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

def _claims_since(ts):
    """Count session_budget stamps strictly after ts. No stamps file = 0."""
    if ts is None:
        return 0
    try:
        sys.path.insert(0, "/Users/anstudio/smedjan/scripts")
        import session_budget as _sb  # type: ignore[import-not-found]
        stamps = _sb._read_locked()
        return sum(1 for s in stamps if s > ts)
    except Exception:  # noqa: BLE001
        return 0


def cmd_budget_show(_args: argparse.Namespace) -> int:
    from smedjan import budget_config as bc
    cfg = bc.load()
    n = _claims_since(cfg.last_observed_at)
    _cfg, alloc = bc.allocation(claims_since_sync=n)
    d = bc.as_dict(_cfg, alloc)
    d["claims_since_sync"] = n
    # Two-pane output: TOML-facing config + derived allocation
    print(json.dumps(d, indent=2))
    if alloc.stale_sync:
        print("WARNING: sync is stale (> 6h). Run `smedjan budget sync --weekly-used N`.",
              file=sys.stderr)
    return 0


def cmd_budget_sync(args: argparse.Namespace) -> int:
    from smedjan import budget_config as bc
    cfg = bc.update_sync(args.weekly_used)
    print(f"synced: last_observed_weekly_used={cfg.last_observed_weekly_used} "
          f"at={cfg.last_observed_at.isoformat(timespec='minutes')}")
    return 0


def cmd_budget_share(args: argparse.Namespace) -> int:
    from smedjan import budget_config as bc
    cfg = bc.update_share(args.share_pct)
    print(f"share set: smedjan_share_of_remaining={cfg.smedjan_share_of_remaining}%")
    return 0


# ── backlog subcommand handlers ──────────────────────────────────────

def _backlog_paths():
    from pathlib import Path as _P
    return (
        _P.home() / "smedjan" / "config" / "backlog.yaml",
        _P.home() / "smedjan" / "config" / "backlog_seeder_paused.flag",
        _P.home() / "smedjan" / "worker-logs" / "last-backlog-seed.state",
    )


def cmd_backlog_show(_args: argparse.Namespace) -> int:
    from smedjan import backlog_seeder
    loaded = backlog_seeder._load_yaml()
    if loaded is None:
        print("backlog.yaml not loaded — see log for reason", file=sys.stderr)
        return 2
    thresh, entries = loaded
    yaml_path, flag_path, _ = _backlog_paths()
    print(f"# backlog.yaml — {yaml_path}")
    print(f"# threshold: min_primary={thresh.min_primary} "
          f"max_per_cycle={thresh.max_per_cycle} "
          f"min_interval={thresh.min_interval_min}m")
    print(f"# paused: {flag_path.exists()}")
    print(f"# total items: {len(entries)}")
    print()
    for i, e in enumerate(entries[:10], 1):
        affinity = e.session_affinity or "-"
        print(f"{i:2d}. {e.id:<8} [{e.risk_level}/{e.strategic_class:<15} aff={affinity}] {e.title[:70]}")
    if len(entries) > 10:
        print(f"    … and {len(entries) - 10} more")
    return 0


def cmd_backlog_status(_args: argparse.Namespace) -> int:
    from datetime import datetime, timedelta, timezone
    from smedjan import backlog_seeder
    _, flag, state = _backlog_paths()
    paused = flag.exists()
    last = backlog_seeder._read_last_seed_at()
    loaded = backlog_seeder._load_yaml()
    thresh = loaded[0] if loaded else None

    # Primary queue count
    with factory_core._connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM smedjan.tasks "
            "WHERE is_fallback=FALSE AND status IN ('queued','approved')"
        )
        primary = cur.fetchone()[0]

    now = datetime.now(timezone.utc)
    next_eligible = None
    if last and thresh:
        next_eligible = last + timedelta(minutes=thresh.min_interval_min)

    print(f"backlog seeder: {'PAUSED' if paused else 'active'}")
    print(f"  flag: {flag}")
    print(f"  primary queue (queued+approved, non-fallback): {primary}")
    if thresh:
        print(f"  seed threshold: primary < {thresh.min_primary}")
        print(f"  max per cycle: {thresh.max_per_cycle}")
    print(f"  last seed: {last.isoformat() if last else '(never)'}")
    if next_eligible:
        delta = (next_eligible - now).total_seconds()
        if delta > 0:
            print(f"  next check eligible in {int(delta / 60)}m{int(delta % 60)}s")
        else:
            print(f"  next check: now (interval elapsed)")
    return 0


def cmd_backlog_pause(_args: argparse.Namespace) -> int:
    _, flag, _ = _backlog_paths()
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.touch()
    print(f"paused: {flag}")
    return 0


def cmd_backlog_resume(_args: argparse.Namespace) -> int:
    _, flag, _ = _backlog_paths()
    if flag.exists():
        flag.unlink()
        print(f"resumed: removed {flag}")
    else:
        print("already active (flag not present)")
    return 0


def cmd_backlog_dry_run(_args: argparse.Namespace) -> int:
    from smedjan import backlog_seeder
    summary = backlog_seeder.run(dry_run=True)
    print(json.dumps(summary, indent=2))
    return 0


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

    ev = qsub.add_parser("evidence", help="record or list evidence signals")
    ev.add_argument("name", help="evidence name to record; pass 'list' to list all signals")
    ev.add_argument("--payload", default=None, help='JSON blob (record mode only)')
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

    # ── budget subcommand ────────────────────────────────────────────
    bud = sub.add_parser("budget", help="weekly Max-budget allocation")
    budsub = bud.add_subparsers(dest="sub", required=True)

    bud_show = budsub.add_parser("show", help="show current allocation + burn")
    bud_show.set_defaults(fn=cmd_budget_show)

    bud_sync = budsub.add_parser("sync", help="record a Max-dashboard observation")
    bud_sync.add_argument("--weekly-used", type=int, required=True,
                          help="percent of Max weekly cap used (0-100)")
    bud_sync.set_defaults(fn=cmd_budget_sync)

    bud_share = budsub.add_parser("share", help="set Smedjan share of remaining")
    bud_share.add_argument("--set", type=int, required=True, dest="share_pct",
                           help="percent of remaining allocated to Smedjan (0-100)")
    bud_share.set_defaults(fn=cmd_budget_share)

    # ── backlog subcommand ───────────────────────────────────────────
    bk = sub.add_parser("backlog", help="autonomous backlog seeder")
    bksub = bk.add_subparsers(dest="sub", required=True)

    bksub.add_parser("show", help="print backlog.yaml top-10 + flags") \
         .set_defaults(fn=cmd_backlog_show)
    bksub.add_parser("status", help="seeder state: primary queue, last seed, next check") \
         .set_defaults(fn=cmd_backlog_status)
    bksub.add_parser("pause", help="create backlog_seeder_paused.flag") \
         .set_defaults(fn=cmd_backlog_pause)
    bksub.add_parser("resume", help="remove backlog_seeder_paused.flag") \
         .set_defaults(fn=cmd_backlog_resume)
    bk_dry = bksub.add_parser("dry-run", help="report what would be seeded, no writes")
    bk_dry.set_defaults(fn=cmd_backlog_dry_run)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
