"""smedjan merge {dry-run|run|status|rollback|skip} CLI."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import classifier, cherry_pick, file_copy, smoke_test, canary, rollback, report, drift_detector


def cmd_dry_run(args: argparse.Namespace) -> int:
    print("=== smedjan merge dry-run ===")
    commits = classifier.fetch_commits()
    classifier.classify_all(commits)
    summary = classifier.summarize(commits)
    print(f"Commits ahead of main: {len(commits)}")
    for k in "ABCDE":
        print(f"  {k}: {len(summary[k])}")
    pickable = summary["A"] + summary["B"]
    print(f"\nWould cherry-pick: {len(pickable)} commits (A+B)")
    for c in pickable[:20]:
        print(f"  {c.short}  {c.subject[:90]}")
    if len(pickable) > 20:
        print(f"  ...{len(pickable)-20} more")

    smedjan_files = file_copy.files_to_sync(commits)
    print(f"\nWould sync smedjan/ files: {len(smedjan_files)}")
    for f in sorted(smedjan_files)[:15]:
        print(f"  {f}")
    if len(smedjan_files) > 15:
        print(f"  ...{len(smedjan_files)-15} more")

    print("\nDrift scan (auto_generate_pages.py + agent_safety_pages.py)...")
    drift = drift_detector.scan_paths([
        "agentindex/auto_generate_pages.py",
        "agentindex/agent_safety_pages.py",
        "agentindex/api/discovery.py",
    ])
    for d in drift:
        print(f"  ⚠ {d.file}: {d.anomaly_type} (factory-only: {','.join(d.factory_only_hashes[:3])})")

    print("\nNo changes made.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    print("=== smedjan merge run ===")
    if not cherry_pick.working_tree_clean():
        print("ERROR: working tree not clean — abort", file=sys.stderr)
        return 1

    run_start = datetime.utcnow()
    tag = rollback.tag_pre_run()
    print(f"Pre-run rollback tag: {tag}")

    commits = classifier.fetch_commits()
    classifier.classify_all(commits)
    summary = classifier.summarize(commits)
    pickable = summary["A"] + summary["B"]
    print(f"Cherry-picking {len(pickable)} commits…")

    cp = cherry_pick.cherry_pick_sequence(pickable, dry_run=args.dry_run)
    print(f"  picked: {len(cp.picked)}, skipped: {len(cp.skipped)}, halted: {cp.halted_at}")

    smedjan_files = file_copy.files_to_sync(pickable)
    fc = file_copy.sync_files(smedjan_files)
    if fc.copied and not args.dry_run:
        h = file_copy.stage_and_commit(
            f"chore(smedjan): daily-merge sync {len(fc.copied)} factory files"
        )
        print(f"  smedjan/ commit: {h or '(none)'}")

    print("Restarting API…")
    smoke_test.restart_api_kickstart()
    smoke_test.wait_for_api_ready(timeout=60)

    print("Running smoke test…")
    smoke = smoke_test.run_smoke_test(seed=42)
    print(f"  {smoke.summary()}, passed={smoke.passed}")

    triggered = False
    if smoke.passed and not args.skip_canary:
        print(f"Canary {args.canary_min} min…")
        canary_result = canary.run_canary(duration_min=args.canary_min)
        if canary_result.triggered:
            triggered = True
            print(f"⚠ Canary triggered rollback: {canary_result.trigger_reason}")
            rollback.rollback_to_tag(tag)
    else:
        canary_result = canary.CanaryResult()
        if not smoke.passed:
            print("⚠ Smoke test failed — rolling back")
            triggered = True
            rollback.rollback_to_tag(tag)

    drift = drift_detector.scan_paths([
        "agentindex/auto_generate_pages.py",
        "agentindex/agent_safety_pages.py",
        "agentindex/api/discovery.py",
        "agentindex/api/main.py",
    ])

    run_end = datetime.utcnow()
    md = report.render_report(
        run_start=run_start, run_end=run_end,
        classified=summary, cp=cp, fc=fc,
        smoke=smoke, canary=canary_result, drift=drift,
        rollback_tag=tag, triggered_rollback=triggered,
    )
    out = report.write_report(run_start.strftime("%Y%m%d"), md)
    print(f"Report: {out}")
    return 0 if not triggered else 2


def cmd_status(args: argparse.Namespace) -> int:
    print("=== smedjan merge status ===")
    commits = classifier.fetch_commits()
    print(f"Commits ahead: {len(commits)}")
    tag = rollback.latest_rollback_tag()
    print(f"Latest rollback tag: {tag or '(none)'}")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    tag = args.tag or rollback.latest_rollback_tag()
    if not tag:
        print("No rollback tag found", file=sys.stderr)
        return 1
    print(f"Rolling back to {tag}…")
    rollback.rollback_to_tag(tag)
    return 0


def cmd_skip(args: argparse.Namespace) -> int:
    """Mark a commit-id as 'do not auto-merge'. Persists to ~/smedjan/config/merge-skip.txt."""
    skip_file = Path.home() / "smedjan/config/merge-skip.txt"
    skip_file.parent.mkdir(parents=True, exist_ok=True)
    existing = skip_file.read_text().splitlines() if skip_file.exists() else []
    if args.task_id not in existing:
        existing.append(args.task_id)
        skip_file.write_text("\n".join(existing) + "\n")
    print(f"Marked {args.task_id} as skip in {skip_file}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="smedjan merge")
    sub = p.add_subparsers(dest="command", required=True)

    p_dry = sub.add_parser("dry-run", help="show plan without executing")
    p_dry.set_defaults(fn=cmd_dry_run)

    p_run = sub.add_parser("run", help="execute merge")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--skip-canary", action="store_true")
    p_run.add_argument("--canary-min", type=int, default=30)
    p_run.set_defaults(fn=cmd_run)

    p_st = sub.add_parser("status", help="latest run + queue state")
    p_st.set_defaults(fn=cmd_status)

    p_rb = sub.add_parser("rollback", help="rollback to last tag")
    p_rb.add_argument("--tag", default=None)
    p_rb.set_defaults(fn=cmd_rollback)

    p_sk = sub.add_parser("skip", help="mark task-id as do-not-auto-merge")
    p_sk.add_argument("task_id")
    p_sk.set_defaults(fn=cmd_skip)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
