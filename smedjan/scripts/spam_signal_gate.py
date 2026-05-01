"""spam_signal_gate.py — refuse to publish audits that smell like Google spam.

Background (FAS 9 of the 2026-04-30 spam-signal sprint): Google's HCU
algorithmic action triggered on Nerq because Smedjan + the renderer were
broadcasting freshness lies. After fixing the runtime renderers (sitemap
lastmod, JSON-LD dateModified, Last-Modified headers, soft-404), we also
need a gate on the audit pipeline so a future regression can't ship the
same kind of pattern.

Checks (each emits a non-zero exit if it fires):

  1. Empty body — header-only CSV (nothing actionable, soft-404 risk).
  2. Bulk-today dates — every date column row equals today's UTC date
     (= "every entity touched today" lie under HCU).
  3. Repeated identical row — > 50% of body rows are byte-identical
     (looks like template spam).
  4. Disallowed phrases — common LLM-tells like "as an AI language model"
     or "I cannot" leaking into published artefacts.

This is intentionally a thin, local-only check meant to be wired into
the audit emitters or a pre-commit hook. It does not replace
output_quality_monitor.py, which checks downstream actionability.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import re
import sys
from pathlib import Path
from typing import Iterable


_DISALLOWED_PHRASES = (
    "as an ai language model",
    "i cannot fulfil",
    "i cannot fulfill",
    "i'm sorry, but i can",
    "as a large language model",
    "i don't have access",
    "<<insert ",
    "{{ name }}",  # untouched template placeholder leaking into output
)

_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}|\s|$)")


def _today_iso() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%d")


def _read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _date_columns(header: Iterable[str]) -> list[int]:
    """Heuristic: column names containing 'date', 'updated', 'enriched',
    or '_at' are treated as date-bearing for the bulk-today check.
    """
    keys = ("date", "updated", "enriched", "_at", "lastmod", "modified", "published")
    out = []
    for i, h in enumerate(header):
        hl = (h or "").lower()
        if any(k in hl for k in keys):
            out.append(i)
    return out


def check(path: Path) -> list[str]:
    """Run all spam-signal checks against an audit CSV.

    Returns a list of human-readable failure messages. Empty list = pass.
    """
    failures: list[str] = []
    if not path.exists():
        return [f"missing file: {path}"]
    if path.stat().st_size == 0:
        return [f"empty file (0 bytes): {path}"]

    header, body = _read_rows(path)
    if not header:
        return [f"no header row: {path}"]
    if not body:
        failures.append(f"header-only / no body rows: {path}")
        return failures  # nothing else to check

    today = _today_iso()
    date_cols = _date_columns(header)
    if date_cols:
        # Take the first detected date column and check whether all
        # populated values are today. (Multiple cols = noisy; one is enough.)
        first = date_cols[0]
        populated = [r[first] for r in body if first < len(r) and r[first]]
        if populated and all(_DATE_LIKE.match(v or "") and v.startswith(today) for v in populated):
            failures.append(
                f"bulk-today date in column '{header[first]}' "
                f"({len(populated)} rows all = {today})"
            )

    # Identical-row check
    canon = ["\x1f".join(r) for r in body]
    if canon:
        most_common = max(set(canon), key=canon.count)
        ratio = canon.count(most_common) / len(canon)
        if ratio > 0.5 and len(body) >= 4:
            failures.append(
                f"{ratio:.0%} of body rows ({canon.count(most_common)}/{len(canon)}) are byte-identical"
            )

    # Disallowed phrases
    blob = "\n".join("\x1f".join(r) for r in [header] + body).lower()
    for phrase in _DISALLOWED_PHRASES:
        if phrase in blob:
            failures.append(f"disallowed phrase present: {phrase!r}")

    return failures


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Refuse to publish spam-shaped audit CSVs.")
    p.add_argument("paths", nargs="+", help="audit CSV files to check")
    p.add_argument("--quiet", action="store_true", help="only print on failure")
    args = p.parse_args(argv)

    bad = 0
    for raw in args.paths:
        path = Path(raw).expanduser().resolve()
        fails = check(path)
        if fails:
            bad += 1
            sys.stderr.write(f"FAIL {path}\n")
            for f in fails:
                sys.stderr.write(f"  - {f}\n")
        elif not args.quiet:
            sys.stdout.write(f"OK   {path}\n")
    return 1 if bad else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
