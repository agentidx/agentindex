"""
emit_evidence.py — F5 autonomy bridge between observation snapshots and the
Smedjan task queue.

Reads the L1 canary observation JSONL log, evaluates green-criteria for each
known evidence signal, and writes a row to ``smedjan.evidence_signals`` via
``factory_core.record_evidence`` when a signal has gone green. After any
successful emission ``factory_core.resolve_ready_tasks`` is invoked so that
tasks with ``wait_for_evidence = <name>`` are promoted out of ``pending``.

Invocation
----------
    python3 -m smedjan.scripts.emit_evidence                    # evaluate all
    python3 -m smedjan.scripts.emit_evidence --dry-run          # no writes
    python3 -m smedjan.scripts.emit_evidence --signal l1_canary_observation_48h

Design notes
------------
* Green criteria live alongside a small ``SignalSpec`` registry so future
  signals are a short additive change, not a refactor.
* ``record_evidence`` already upserts on ``name``, so running this script
  repeatedly is safe — green reports just keep the row fresh.
* All reads go through the observation JSONL (``L1-canary-observations.jsonl``)
  — we do not re-query the analytics mirror here, we trust the observation
  script's output. That keeps the evidence emitter cheap and decoupled.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from smedjan import factory_core, sources  # noqa: F401 — sources kept for future signals

log = logging.getLogger("smedjan.emit_evidence")


# ── Configuration ─────────────────────────────────────────────────────────

# L1 canary deploy T0 — hardcoded per F5 spec. When more canaries land this
# moves into the ``smedjan.tasks`` row (derived from T001.scheduled_start_at).
L1_CANARY_T0 = datetime.fromisoformat("2026-04-18T11:34:18+00:00")

OBS_DIR = Path(os.path.expanduser(
    os.environ.get("SMEDJAN_OBS_DIR", "~/smedjan/observations")
))
OBS_JSONL = OBS_DIR / "L1-canary-observations.jsonl"

# Minimum entries required to prove the 12h cadence actually ran for 48h.
MIN_OBSERVATIONS = 4

# Whole-site 5xx rate must stay strictly below this across every window.
WHOLE_5XX_RATE_MAX = 0.002  # 0.2%


# ── SignalSpec registry ──────────────────────────────────────────────────

@dataclass
class Verdict:
    """Outcome of evaluating one SignalSpec against the observation log."""
    name: str
    green: bool
    reason: str
    payload: dict


@dataclass
class SignalSpec:
    name: str
    # evaluator returns a Verdict; must never raise for "not green yet".
    evaluate: Callable[[], Verdict]


# ── Observation log helpers ──────────────────────────────────────────────

def _load_observations() -> list[dict]:
    """Read every line of ``L1-canary-observations.jsonl`` in order. Each line
    is ``{"ts": "YYYYMMDDTHHMMSSZ", "obs": {...}}``.
    Bad lines are skipped with a warning — a malformed line must not poison a
    green signal evaluation.
    """
    if not OBS_JSONL.exists():
        return []
    rows: list[dict] = []
    for ln in OBS_JSONL.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError as e:
            log.warning("skipping malformed obs line: %s", e)
    return rows


def _parse_ts(ts: str) -> datetime:
    """The observation script writes timestamps as ``20260418T145342Z`` —
    pre-3.11 ISO parsers choke on that, so parse explicitly.
    """
    return datetime.strptime(ts, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


# ── Generic 48h-observation evaluator (shared by canary + wave2) ─────────

def _evaluate_48h_green(
    *,
    signal_name: str,
    t0: datetime,
) -> Verdict:
    """Shared green-gate logic for the 48h observation family.

    Criteria (all must hold):
      1. now - T0 >= 48h.
      2. Observation log has >= MIN_OBSERVATIONS entries *after* T0.
      3. Every post-T0 entry shows canary-cohort 5xx == 0 AND whole-site 5xx
         rate < WHOLE_5XX_RATE_MAX.
      4. The most recent post-T0 entry has non-zero /safe/* activity on the
         canary cohort (12h window) — proves pages are being hit.
    """
    now = datetime.now(timezone.utc)
    hours_since = (now - t0).total_seconds() / 3600.0

    if hours_since < 48.0:
        return Verdict(
            signal_name, False,
            f"only {hours_since:.1f}h since T0 ({t0.isoformat()}); 48h gate not met",
            {},
        )

    rows = _load_observations()
    post_t0 = [r for r in rows if _parse_ts(r["ts"]) >= t0]
    if len(post_t0) < MIN_OBSERVATIONS:
        return Verdict(
            signal_name, False,
            f"only {len(post_t0)} post-T0 observations; need >= {MIN_OBSERVATIONS}",
            {"observations": len(post_t0)},
        )

    # Inspect every window for 5xx breaches.
    violations: list[str] = []
    canary_24h_hits = 0
    latest_12h_hits = 0
    for r in post_t0:
        obs = r["obs"]
        s5 = obs.get("status_5xx", {})
        for w in ("12h", "24h"):
            for reg, counts in s5.get(w, {}).items():
                if counts.get("5xx", 0) > 0:
                    violations.append(f"{r['ts']} {w} {reg} 5xx={counts['5xx']}")
        whole_total = obs.get("whole_12h_total", 0) or 0
        whole_5xx = obs.get("whole_12h_5xx", 0) or 0
        if whole_total > 0:
            rate = whole_5xx / whole_total
            if rate >= WHOLE_5XX_RATE_MAX:
                violations.append(
                    f"{r['ts']} whole-site 5xx rate {rate*100:.3f}% >= 0.2%"
                )

    # Latest-window /safe/* activity proof (canary cohort, 12h window).
    latest = post_t0[-1]["obs"]
    s12 = latest.get("status_5xx", {}).get("12h", {})
    latest_12h_hits = sum((counts.get("total", 0) or 0) for counts in s12.values())

    # Cumulative 24h sample for the payload (informational).
    s24 = latest.get("status_5xx", {}).get("24h", {})
    canary_24h_hits = sum((counts.get("total", 0) or 0) for counts in s24.values())

    if violations:
        return Verdict(
            signal_name, False,
            f"{len(violations)} 5xx violations; first: {violations[0]}",
            {"violations": violations[:10]},
        )

    if latest_12h_hits == 0:
        return Verdict(
            signal_name, False,
            "latest 12h window shows zero canary-cohort /safe/* hits — pages not being exercised",
            {"canary_12h_hits": 0},
        )

    return Verdict(
        signal_name, True,
        f"all {len(post_t0)} windows clean; canary 24h hits={canary_24h_hits}",
        {
            "5xx_48h": 0,
            "observations": len(post_t0),
            "canary_24h_hits": canary_24h_hits,
            "canary_12h_hits": latest_12h_hits,
            "t0": t0.isoformat(),
            "verdict": "green",
        },
    )


# ── Per-signal evaluators ────────────────────────────────────────────────

def _evaluate_l1_canary() -> Verdict:
    return _evaluate_48h_green(
        signal_name="l1_canary_observation_48h",
        t0=L1_CANARY_T0,
    )


def _lookup_t001_scheduled_start() -> datetime | None:
    """Return T001.scheduled_start_at if T001 is done, else None.

    The wave-2 evidence window only opens once T001 has actually shipped,
    because the post-T001 state is what we're observing.
    """
    try:
        with sources.smedjan_db_cursor(dict_cursor=True) as (_, cur):
            cur.execute(
                "SELECT status, scheduled_start_at, done_at "
                "FROM smedjan.tasks WHERE id = 'T001'"
            )
            row = cur.fetchone()
    except Exception as e:  # noqa: BLE001 — smedjan DB outage should not crash us
        log.warning("could not read T001 for wave2 evaluation: %s", e)
        return None
    if not row or row["status"] != "done":
        return None
    # scheduled_start_at first, fall back to done_at if the task was auto-claimed.
    return row["scheduled_start_at"] or row["done_at"]


def _evaluate_l1_wave2() -> Verdict:
    t0 = _lookup_t001_scheduled_start()
    if t0 is None:
        return Verdict(
            "l1_wave2_observation_48h", False,
            "T001 not yet done — wave2 T0 undefined; skipping",
            {},
        )
    return _evaluate_48h_green(
        signal_name="l1_wave2_observation_48h",
        t0=t0,
    )


SIGNAL_SPECS: dict[str, SignalSpec] = {
    "l1_canary_observation_48h": SignalSpec(
        name="l1_canary_observation_48h",
        evaluate=_evaluate_l1_canary,
    ),
    "l1_wave2_observation_48h": SignalSpec(
        name="l1_wave2_observation_48h",
        evaluate=_evaluate_l1_wave2,
    ),
}


# ── Emission ─────────────────────────────────────────────────────────────

def _emit(verdict: Verdict, *, dry_run: bool) -> None:
    if dry_run:
        log.info("[DRY-RUN] would record %s payload=%s", verdict.name, verdict.payload)
        return
    factory_core.record_evidence(
        verdict.name,
        payload=verdict.payload,
        created_by="emit_evidence.auto",
    )
    log.info("recorded evidence signal %s", verdict.name)

    # Promote any pending tasks that were blocked on this signal.
    try:
        summary = factory_core.resolve_ready_tasks()
        log.info("resolve_ready_tasks: %s", summary)
    except Exception as e:  # noqa: BLE001 — never crash the emitter on resolver blip
        log.error("resolve_ready_tasks failed: %s", e)

    # Evidence emission is telemetry: the signal lands in
    # smedjan.evidence_signals and the approve flow promotes dependent
    # tasks. No ntfy — Anders sees the consequence (tasks ready) in the
    # dashboard queue.
    log.info("evidence emission complete: %s (%s)", verdict.name, verdict.reason)


def run(signal: str | None, *, dry_run: bool) -> int:
    names = [signal] if signal else list(SIGNAL_SPECS.keys())
    unknown = [n for n in names if n not in SIGNAL_SPECS]
    if unknown:
        log.error("unknown signal(s): %s", unknown)
        return 2

    exit_code = 0
    for name in names:
        spec = SIGNAL_SPECS[name]
        try:
            verdict = spec.evaluate()
        except Exception as e:  # noqa: BLE001
            log.exception("evaluator crashed for %s: %s", name, e)
            exit_code = 1
            continue
        if verdict.green:
            log.info("%s GREEN: %s", name, verdict.reason)
            _emit(verdict, dry_run=dry_run)
        else:
            log.info("%s NOT green: %s", name, verdict.reason)
    return exit_code


# ── Entry point ──────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="emit_evidence",
        description="Evaluate observation-driven evidence signals and emit when green.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="log what would be recorded; do not write.")
    parser.add_argument("--signal", choices=sorted(SIGNAL_SPECS.keys()),
                        help="evaluate only this signal (default: all).")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="DEBUG-level logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return run(args.signal, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
