"""check_endpoint_pct5xx_1h.py — last-1h per-endpoint pct5xx healthcheck.

Context: FU-QUERY-20260427-05 / AUDIT-QUERY-20260427 finding #5. The
`/v1/agent/stats` endpoint had been 100% 5xx for 14 consecutive days
(47/47 hits, 28 humans hit 503) before the regression was caught — the
weekly audit was the only signal, and FU-QUERY-20260418-07's prior
"fix" only changed the status code (500 → 503) without touching the
underlying error rate. The audit was three weeks late by the time it
fired.

This script makes per-endpoint 5xx regressions auditable on an hourly
cadence so a silent re-regression on /v1/agent/stats — or any other
configured path — is caught the same day rather than the next weekly
audit.

Behaviour
---------
* Exits 0 when healthy (``pct5xx < threshold``), when last-1h volume is
  below ``--min-sample`` (avoids flapping on quiet hours), or when the
  mirror is unreachable.
* Exits 1 only when sampled volume meets ``--min-sample`` AND
  ``pct5xx >= threshold``.

Threshold rationale
-------------------
Default ``--threshold-pct=10`` matches the FU-QUERY-20260427-05
acceptance criterion ("alert fires on per-endpoint pct5xx > 10%").
A 1h window will be noisier than the daily one — that's intentional;
a 1h breach is a leading indicator the daily metric is about to
regress, and the audit-loop signal otherwise lags by ~7 days.

Default endpoint list mirrors the audit's "pages-with-human-traffic"
shortlist; new endpoints can be added with ``--path`` (repeatable).

Invocation
----------
    # Default: check /v1/agent/stats (the FU-05 regression endpoint)
    python3 -m smedjan.scripts.check_endpoint_pct5xx_1h

    # Multi-path: check several at once, exit 1 if any breach
    python3 -m smedjan.scripts.check_endpoint_pct5xx_1h \\
        --path /v1/agent/stats \\
        --path /v1/agent/search \\
        --path /v1/preflight

    # Threshold + window + sample-floor overrides
    python3 -m smedjan.scripts.check_endpoint_pct5xx_1h \\
        --threshold-pct 10 --min-sample 5 --window-minutes 60

Wiring (out of scope here):
    A LaunchAgent timer can run this hourly; on exit 1 the caller
    should fan out to ``ntfy_action_required.alert`` rather than
    calling ntfy here, keeping this script side-effect-free.
"""
from __future__ import annotations

import argparse
import sys

from smedjan import sources


DEFAULT_PATHS = ("/v1/agent/stats",)
DEFAULT_THRESHOLD_PCT = 10.0
DEFAULT_MIN_SAMPLE = 5
DEFAULT_WINDOW_MINUTES = 60


def _fetch_window_counts(
    path: str, window_minutes: int
) -> tuple[int, int] | None:
    """Return (total, five_xx) for ``path`` in the trailing window, or
    None if the mirror is unreachable. Uses an exact path match (the
    audit's evidence query also matches exact paths)."""
    try:
        with sources.analytics_mirror_cursor() as (_, cur):
            cur.execute(
                """
                SELECT count(*)                                AS total,
                       count(*) FILTER (WHERE status >= 500)   AS five_xx
                FROM analytics_mirror.requests
                WHERE ts > now() - (%s || ' minutes')::interval
                  AND path = %s
                """,
                (str(window_minutes), path),
            )
            row = cur.fetchone()
        if not row:
            return 0, 0
        return int(row[0]), int(row[1])
    except sources.SourceUnavailable:
        return None


def _check_one(
    path: str,
    window_minutes: int,
    threshold_pct: float,
    min_sample: int,
) -> int:
    """Return 0 (ok / dormant / mirror-down) or 1 (breach) for one path."""
    counts = _fetch_window_counts(path, window_minutes)
    if counts is None:
        print(
            f"[check_endpoint_pct5xx_1h] mirror unavailable path={path} — "
            "exit 0 (advisory)",
            file=sys.stderr,
        )
        return 0

    total, five_xx = counts
    pct = (100.0 * five_xx / total) if total else 0.0
    base = (
        f"path={path} window_min={window_minutes} total={total} "
        f"five_xx={five_xx} pct5xx={pct:.1f} threshold_pct={threshold_pct} "
        f"min_sample={min_sample}"
    )

    if total < min_sample:
        print(f"[check_endpoint_pct5xx_1h] dormant (low sample) {base}")
        return 0

    if pct >= threshold_pct:
        print(
            f"[check_endpoint_pct5xx_1h] WARN per-endpoint pct5xx breach {base} — "
            "investigate handler in agentindex/nerq_api.py / agentindex/api/"
        )
        return 1

    print(f"[check_endpoint_pct5xx_1h] OK {base}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--path", action="append", dest="paths", default=None,
        help=(
            "Path to check (exact match against analytics_mirror.requests.path). "
            "Repeatable. Default: /v1/agent/stats"
        ),
    )
    parser.add_argument(
        "--threshold-pct", type=float, default=DEFAULT_THRESHOLD_PCT,
        help=(
            "Page when pct5xx in window meets/exceeds this percentage "
            f"(default: {DEFAULT_THRESHOLD_PCT})."
        ),
    )
    parser.add_argument(
        "--min-sample", type=int, default=DEFAULT_MIN_SAMPLE,
        help=(
            "Minimum total request count before the threshold check applies "
            f"(default: {DEFAULT_MIN_SAMPLE}). Below this, exit 0."
        ),
    )
    parser.add_argument(
        "--window-minutes", type=int, default=DEFAULT_WINDOW_MINUTES,
        help=f"Rolling window in minutes (default: {DEFAULT_WINDOW_MINUTES}).",
    )
    args = parser.parse_args(argv)

    paths = tuple(args.paths) if args.paths else DEFAULT_PATHS

    # Aggregate exit code: any breach => 1, otherwise 0.
    rc = 0
    for path in paths:
        rc |= _check_one(
            path,
            window_minutes=args.window_minutes,
            threshold_pct=args.threshold_pct,
            min_sample=args.min_sample,
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
