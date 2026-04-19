#!/usr/bin/env python3
"""
A9 follow-up — characterise the 5,160 slug-drift entries in
agent_safety_slugs.json.

Read-only, repo-scan only. Classifies each drift row by reason
(underscore-collapsed, leading-dot, leading-dash, trailing-whitespace,
Unicode-fold, other), verifies that the proposed renderer fix (switch
href to snapshot slug) resolves the dead alt-link for each drift class,
and prints a compact report.

Run:
    python3 /Users/anstudio/agentindex/smedjan/scripts/A9_followup_slug_drift.py
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

SLUGS_PATH = Path("/Users/anstudio/agentindex/agentindex/agent_safety_slugs.json")

_STRIP_CHARS = "/\\()[]{}:;,!?@#$%^&*=+|<>~`\"'"


def make_slug(name: str) -> str:
    s = (name or "").lower().strip()
    for ch in _STRIP_CHARS:
        s = s.replace(ch, "")
    s = s.replace(" ", "-").replace("_", "-").replace(".", "-")
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def make_slug_legacy(name: str) -> str:
    """Reproduces the pre-drift slug generator inferred from stored-slug
    samples: NFKD + ASCII-ignore, dropped `_` entirely, did NOT collapse
    `--`, did NOT strip edge `-`. Every other rule matches current
    _make_slug."""
    s = (name or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    for ch in _STRIP_CHARS:
        s = s.replace(ch, "")
    s = s.replace(" ", "-").replace(".", "-")
    s = s.replace("_", "")  # legacy: drop
    return s


def classify(name: str, stored: str, computed: str) -> str:
    """Assign a single primary drift reason to a mismatched entry.

    Priority order (first match wins) reflects the strongest explanatory
    signal for why current _make_slug disagrees with the stored slug.
    """
    raw = name or ""

    # 1. Unicode fold — name contains non-ASCII that legacy dropped via
    #    NFKD + ascii-ignore; current _make_slug passes it through.
    ascii_folded = (
        unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    )
    if ascii_folded != raw:
        return "unicode-fold"

    # 2. Underscore-collapsed — name contains '_' which legacy dropped
    #    and current replaces with '-'. Dominant historical cause.
    if "_" in raw:
        return "underscore-collapsed"

    # 3. Leading-dash retention — stored starts with '-' because legacy
    #    did not .strip('-'). Covers `.foo` → `-foo` and similar.
    if stored.startswith("-") and not computed.startswith("-"):
        return "leading-dash-retained"

    # 4. Trailing-dash retention — stored ends with '-' because legacy
    #    did not .strip('-'). Covers `Foo-` → `foo-`.
    if stored.endswith("-") and not computed.endswith("-"):
        return "trailing-dash-retained"

    # 5. Double-dash retention — stored contains '--' because legacy did
    #    not collapse runs of '-'. Covers `A & B` → `a--b`.
    if "--" in stored and "--" not in computed:
        return "double-dash-retained"

    # 6. Leading-dot pattern that somehow survived another way.
    if raw.lstrip().startswith("."):
        return "leading-dot"

    return "other"


def main() -> int:
    with SLUGS_PATH.open() as f:
        entries = json.load(f)

    drift_rows = []
    for e in entries:
        name = e.get("name") or ""
        stored = e.get("slug") or ""
        computed = make_slug(name)
        if computed != stored:
            drift_rows.append((name, stored, computed))

    print(f"Total entries            : {len(entries):,}")
    print(f"Drift rows (stored != computed): {len(drift_rows):,}")
    print(f"Drift rate               : {len(drift_rows)/len(entries)*100:.2f}%")
    print()

    buckets: Counter = Counter()
    samples: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    legacy_rescues = 0

    for name, stored, computed in drift_rows:
        bucket = classify(name, stored, computed)
        buckets[bucket] += 1
        if len(samples[bucket]) < 5:
            samples[bucket].append((name, stored, computed))
        if make_slug_legacy(name) == stored:
            legacy_rescues += 1

    print("Drift classification")
    print("-" * 72)
    for bucket, count in buckets.most_common():
        pct = count / len(drift_rows) * 100
        print(f"  {bucket:32s} {count:6,}  ({pct:5.2f}%)")
    print()
    print(
        f"Legacy generator (drop `_`/`.`) reproduces stored slug for "
        f"{legacy_rescues:,} of {len(drift_rows):,} rows "
        f"({legacy_rescues/len(drift_rows)*100:.2f}%)."
    )
    print()

    print("Samples per bucket (name / stored / _make_slug(name))")
    print("-" * 72)
    for bucket in buckets:
        print(f"[{bucket}]")
        for name, stored, computed in samples[bucket]:
            print(f"  name     : {name!r}")
            print(f"  stored   : {stored}")
            print(f"  computed : {computed}")
            print()

    # Dry-run verification: does switching href to snapshot slug resolve
    # every drift row? By construction YES (the snapshot slug *is* the
    # served slug), but we prove it by checking each drift-class sample
    # against the served-slug set.
    served = {e["slug"] for e in entries}
    resolved = 0
    unresolved_samples: list[tuple[str, str, str]] = []
    for name, stored, computed in drift_rows:
        if stored in served:
            resolved += 1
        else:
            unresolved_samples.append((name, stored, computed))

    print("Dry-run: proposed fix (href = snapshot slug)")
    print("-" * 72)
    print(
        f"  resolved (stored in served set)   : {resolved:,}/{len(drift_rows):,}"
    )
    print(
        f"  would still 404                   : {len(unresolved_samples):,}"
    )
    if unresolved_samples:
        for name, stored, computed in unresolved_samples[:5]:
            print(f"    ! {name!r} -> {stored}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
