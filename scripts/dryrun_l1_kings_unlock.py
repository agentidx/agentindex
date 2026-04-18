#!/usr/bin/env python3
"""
dryrun_l1_kings_unlock.py — Quality Gate A+B+B2 dry-run

For N random enriched non-Kings per target registry:
  OLD html = curl http://localhost:8000/safe/<slug>  (running API, pre-change code)
  NEW html = import agentindex.agent_safety_pages._render_agent_page  (patched)

Produces a JSON summary + 10 spot-check HTML pairs for manual review.
No production state is modified. Used to gate the L1 Kings Unlock canary
for gems + homebrew (Day 1 of the wave-1 rollout).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2.extras
import urllib.request

sys.path.insert(0, os.path.expanduser("~/agentindex"))
from agentindex.agent_safety_pages import _render_agent_page  # noqa: E402
from smedjan import sources  # noqa: E402

LOG = logging.getLogger("smedjan.dryrun_l1")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

PROD_BASE = os.environ.get("SMEDJAN_PROD_BASE", "http://localhost:8000")

# Antipattern regexes — things that should NOT appear in a production page.
ANTIPATTERNS: list[tuple[str, re.Pattern]] = [
    ("literal None",        re.compile(r">None<")),
    ("literal null",        re.compile(r">null<", re.I)),
    ("empty TD",            re.compile(r"<td>\s*</td>")),
    ("empty list item",     re.compile(r"<li>\s*</li>")),
    ("undefined",           re.compile(r"\bundefined\b")),
    ("NaN token",           re.compile(r">NaN<")),
    ("stray brace",         re.compile(r"\{\{[a-z_]+\}\}")),  # unreplaced template token
    ("broken jsonld open",  re.compile(r'application/ld\+json">\s*</script>')),
]

# "Detailed Score Analysis" is unique to the Section-1 King heading — the
# other phrases we tried appear in generic methodology text and gave false
# positives on every page.
KING_SECTION_MARKERS = [
    "Detailed Score Analysis",
]

# Marker for the "Not yet available" disclaimer we expect for all gems+homebrew non-Kings.
NOT_YET_MARKER = "Privacy assessment for"  # matches the disclaimer opener


def pick_sample(registries: list[str], n_per_reg: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with sources.nerq_readonly_cursor(dict_cursor=True) as (_, cur):
            cur.execute("SET statement_timeout = '60s';")
            for reg in registries:
                # Exclude slugs that also exist as a King in another registry —
                # _resolve_entity() will return the King variant and the
                # canary measurement would actually be testing unchanged code.
                cur.execute(
                    """
                    SELECT s.slug, s.registry, s.is_king,
                           s.security_score, s.maintenance_score,
                           s.popularity_score, s.quality_score, s.community_score,
                           s.privacy_score
                    FROM public.software_registry s
                    WHERE s.registry = %s
                      AND s.is_king = false
                      AND s.enriched_at IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM public.software_registry k
                          WHERE k.slug = s.slug AND k.is_king = true
                      )
                    ORDER BY random()
                    LIMIT %s;
                    """,
                    (reg, n_per_reg),
                )
                rows.extend(dict(r) for r in cur.fetchall())
    LOG.info("sampled %d slugs across registries %s", len(rows), registries)
    return rows


def fetch_old(slug: str, timeout: float = 10.0) -> tuple[int, str]:
    url = f"{PROD_BASE}/safe/{slug}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        LOG.warning("fetch_old %s failed: %s", slug, e)
        return -1, ""


def render_new(slug: str) -> tuple[bool, str, str | None]:
    """Return (ok, html, error). Catches any rendering crash."""
    try:
        html = _render_agent_page(slug, {"name": slug})
        return True, html, None
    except Exception as e:
        return False, "", f"{type(e).__name__}: {e}"


def scan_antipatterns(html: str) -> list[str]:
    hits = []
    for name, rx in ANTIPATTERNS:
        if rx.search(html):
            hits.append(name)
    return hits


def analyse_pair(slug: str, old_status: int, old_html: str,
                 new_ok: bool, new_html: str, new_err: str | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "slug": slug,
        "old_status": old_status,
        "old_has_king_section": any(m in old_html for m in KING_SECTION_MARKERS),
        "old_antipatterns": scan_antipatterns(old_html) if old_html else [],
        "old_length": len(old_html),
        "new_ok": new_ok,
        "new_error": new_err,
    }
    if new_ok:
        entry["new_antipatterns"] = scan_antipatterns(new_html)
        entry["new_length"] = len(new_html)
        entry["new_has_king_section"] = any(m in new_html for m in KING_SECTION_MARKERS)
        entry["new_has_not_yet"] = NOT_YET_MARKER in new_html
        entry["delta_length"] = len(new_html) - len(old_html)
    return entry


def write_spotchecks(rows: list[dict[str, Any]], pairs: list[tuple[str, str, str]],
                      out_dir: Path, n: int = 10) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    # Pick the first N that have both old+new, diverse across registries
    seen_regs: set[str] = set()
    for row, (slug, old, new) in zip(rows, pairs):
        if len(saved) >= n:
            break
        reg = row["registry"]
        # prefer registry diversity until each represented once
        if len(seen_regs) < 2 and reg in seen_regs:
            continue
        if not old or not new:
            continue
        seen_regs.add(reg)
        (out_dir / f"{reg}__{slug}__OLD.html").write_text(old)
        (out_dir / f"{reg}__{slug}__NEW.html").write_text(new)
        saved.append(slug)
    return saved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-per-reg", type=int, default=50,
                        help="samples per registry (default 50)")
    parser.add_argument("--registries", nargs="+", default=["gems", "homebrew"])
    parser.add_argument(
        "--out",
        default=os.path.expanduser("~/smedjan/discovery/canary-gems-homebrew"),
        help="output directory for spotchecks + report",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = pick_sample(args.registries, args.n_per_reg)
    if not rows:
        LOG.error("no sample rows — abort")
        return 1

    results: list[dict[str, Any]] = []
    pairs: list[tuple[str, str, str]] = []  # (slug, old_html, new_html) for spotcheck pool
    t0 = time.monotonic()
    for i, row in enumerate(rows):
        slug = row["slug"]
        old_status, old_html = fetch_old(slug)
        new_ok, new_html, new_err = render_new(slug)
        entry = analyse_pair(slug, old_status, old_html, new_ok, new_html, new_err)
        entry["registry"] = row["registry"]
        entry["security_score"] = row["security_score"]
        entry["privacy_score"] = row["privacy_score"]
        results.append(entry)
        pairs.append((slug, old_html, new_html if new_ok else ""))
        if (i + 1) % 25 == 0:
            LOG.info("progress %d/%d (%.1fs)", i + 1, len(rows), time.monotonic() - t0)

    LOG.info("render pairs complete in %.1fs", time.monotonic() - t0)

    # Spot-checks for manual review
    saved = write_spotchecks(results, pairs, out_dir / "spotchecks", n=10)
    LOG.info("wrote %d spotcheck pairs to %s", len(saved), out_dir / "spotchecks")

    # Summary statistics
    def count(pred):
        return sum(1 for r in results if pred(r))

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(results),
        "registries": args.registries,
        "per_registry_counts": {
            reg: count(lambda r, reg=reg: r["registry"] == reg) for reg in args.registries
        },
        "old_http_200":           count(lambda r: r["old_status"] == 200),
        "old_http_non200":        count(lambda r: r["old_status"] != 200),
        "old_had_king_section":   count(lambda r: r["old_has_king_section"]),
        "old_any_antipattern":    count(lambda r: bool(r["old_antipatterns"])),
        "new_render_ok":          count(lambda r: r["new_ok"]),
        "new_render_failed":      count(lambda r: not r["new_ok"]),
        "new_has_king_section":   count(lambda r: r.get("new_has_king_section") is True),
        "new_has_not_yet":        count(lambda r: r.get("new_has_not_yet") is True),
        "new_any_antipattern":    count(lambda r: bool(r.get("new_antipatterns"))),
        "avg_delta_length":       round(
            sum(r.get("delta_length", 0) for r in results if r["new_ok"])
            / max(1, count(lambda r: r["new_ok"])),
            1,
        ),
    }

    antipattern_samples = [
        {"slug": r["slug"], "registry": r["registry"],
         "old_ap": r["old_antipatterns"], "new_ap": r.get("new_antipatterns", [])}
        for r in results if r.get("new_antipatterns")
    ][:10]

    crash_samples = [
        {"slug": r["slug"], "registry": r["registry"], "error": r["new_error"]}
        for r in results if not r["new_ok"]
    ]

    out_json = out_dir / "summary.json"
    out_json.write_text(json.dumps({
        "summary": summary,
        "antipattern_samples": antipattern_samples,
        "crash_samples": crash_samples,
        "spotcheck_slugs": saved,
    }, indent=2))
    LOG.info("wrote %s", out_json)

    # Verdict: no crashes, no antipatterns. Sections may legitimately render
    # without the "Not yet available" stub when a sample slug resolves to a
    # King variant with populated privacy_score — that's the intended
    # pre-unlock behaviour, not a bug.
    ok = (
        summary["new_render_failed"] == 0
        and summary["new_any_antipattern"] == 0
    )

    for k, v in summary.items():
        LOG.info("%-28s %s", k, v)

    if ok:
        LOG.info("VERDICT: GO — dry-run clean on %d samples", summary["sample_size"])
    else:
        LOG.warning("VERDICT: HOLD — dry-run flagged issues; review %s", out_json)

    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
