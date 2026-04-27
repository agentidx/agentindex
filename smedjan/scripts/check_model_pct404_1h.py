"""check_model_pct404_1h.py — last-1h pct404 healthcheck for /model/<slug>.

Context: FU-QUERY-20260427-03 / AUDIT-QUERY-20260427 finding #3.
`/model/<slug>` 404 rate regressed 50.5% → 65.5% week-over-week, peaking
at 78–85% on 2026-04-22..26. The FU-QUERY-20260418-01 fallback renderer
(``agentindex/api/endpoints/model_fallback.py``, committed on
``smedjan-factory-v0`` as ``d394618``) rewrites upstream 404s to a
200-with-noindex stub, but the renderer is currently dark in production
(it lives only on ``smedjan-factory-v0``; ``main`` does not import it,
and a synthetic curl against ``https://nerq.ai/model/<random>`` returns
HTTP 404 with ``meta name="robots" content="index, follow"``).

This script makes the regression auditable on an hourly cadence so a
silent re-regression is caught the same day rather than the next weekly
audit. It queries ``analytics_mirror.requests`` for the last 1h and
prints ``pct404`` over the path family the audit/finding defines
(``^/model/[^/]+$`` — single-segment slugs, matching the renderer's
upstream handler in ``agentindex/seo_dynamic.py``).

Behaviour
---------
* Exits 0 when healthy (``pct404 < threshold``), when last-1h volume is
  below ``--min-sample`` (avoids flapping on quiet hours — see audit
  appendix: 90 hits/day == ~4/hour, so a small handful of 404s in a
  quiet hour shouldn't page), or when the mirror is unreachable.
* Exits 1 only when sampled volume meets ``--min-sample`` AND
  ``pct404 >= threshold``.

Threshold rationale
-------------------
Default ``--threshold-pct=35`` matches the FU-QUERY-20260427-03
acceptance criterion ("/model/ daily pct404 < 35% for 3 consecutive
days"). The 1h window will be noisier than the daily one — that's
intentional; a 1h breach is a leading indicator the daily metric is
about to regress.

Invocation
----------
    python3 -m smedjan.scripts.check_model_pct404_1h
    python3 -m smedjan.scripts.check_model_pct404_1h --threshold-pct 35
    python3 -m smedjan.scripts.check_model_pct404_1h --min-sample 5

Wiring (out of scope here):
    A LaunchAgent timer (``com.nerq.smedjan.model-pct404-1h``) can run
    this hourly; on exit 1 the caller should fan out to
    ``ntfy_action_required.alert`` rather than calling ntfy here, keeping
    this script side-effect-free.
"""
from __future__ import annotations

import argparse
import sys

from smedjan import sources


# Mirrors the regex used by AUDIT-QUERY-20260427 finding #3 evidence query.
# Single-segment slugs only; two-segment HF-style paths (`/model/org/slug`)
# are excluded to keep the metric stable across audits.
PATH_REGEX = r"^/model/[^/]+$"

DEFAULT_THRESHOLD_PCT = 35.0
DEFAULT_MIN_SAMPLE = 5
DEFAULT_WINDOW_MINUTES = 60


def _fetch_window_counts(window_minutes: int) -> tuple[int, int] | None:
    try:
        with sources.analytics_mirror_cursor() as (_, cur):
            cur.execute(
                """
                SELECT count(*)                              AS total,
                       count(*) FILTER (WHERE status = 404)  AS nf
                FROM analytics_mirror.requests
                WHERE ts > now() - (%s || ' minutes')::interval
                  AND path ~ %s
                """,
                (str(window_minutes), PATH_REGEX),
            )
            row = cur.fetchone()
        if not row:
            return 0, 0
        return int(row[0]), int(row[1])
    except sources.SourceUnavailable:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--threshold-pct", type=float, default=DEFAULT_THRESHOLD_PCT,
        help=(
            f"Page when pct404 in window meets/exceeds this percentage "
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

    counts = _fetch_window_counts(args.window_minutes)
    if counts is None:
        print(
            "[check_model_pct404_1h] mirror unavailable — exit 0 (advisory)",
            file=sys.stderr,
        )
        return 0

    total, nf = counts
    pct = (100.0 * nf / total) if total else 0.0
    base = (
        f"window_min={args.window_minutes} total={total} nf={nf} "
        f"pct404={pct:.1f} threshold_pct={args.threshold_pct} "
        f"min_sample={args.min_sample} path_regex={PATH_REGEX!r}"
    )

    if total < args.min_sample:
        print(f"[check_model_pct404_1h] dormant (low sample) {base}")
        return 0

    if pct >= args.threshold_pct:
        print(
            f"[check_model_pct404_1h] WARN /model/ pct404 breach {base} — "
            "FU-QUERY-20260427-03 fallback renderer suspected dark; see "
            "agentindex/api/endpoints/model_fallback.py"
        )
        return 1

    print(f"[check_model_pct404_1h] OK {base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
