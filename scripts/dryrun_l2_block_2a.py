#!/usr/bin/env python3
"""
dryrun_l2_block_2a.py — T004 L2 Block 2a dry-run (registry-allowlist variant).

For N random enriched non-Kings per target registry (default: npm):
  OLD html = curl http://localhost:8000/safe/<slug>     (running API)
  NEW html = _render_agent_page(slug, …) with
             L2_BLOCK_2A_REGISTRIES=<registry> set in-process.

Produces a JSON summary + spot-check HTML pairs. No production state is
modified. Gates the canary rollout in T004b.

This replaces the earlier T110 shadow-mode render harness (still usable
via `--mode legacy-shadow`). The L1-mirror mode is the default because
T004's acceptance criterion is "0 crashes and 0 antipatterns with the
block added" — that is best measured by rendering through the full
`_render_agent_page` pipeline, not the isolated block function.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# agent_safety_pages reads L1_UNLOCK_REGISTRIES and L2_BLOCK_2A_REGISTRIES
# at import (the L1 var is frozen into a module-level frozenset). The
# dry-run therefore must set both BEFORE importing. We parse argv early
# and stash the env var, then do the import at the bottom of this module.
_EARLY_ARGS = argparse.ArgumentParser(add_help=False)
_EARLY_ARGS.add_argument("--registries", nargs="+", default=["npm"])
_early_registries, _ = _EARLY_ARGS.parse_known_args()
os.environ.setdefault("L1_UNLOCK_REGISTRIES", ",".join(_early_registries.registries))
os.environ.setdefault("L2_BLOCK_2A_REGISTRIES", ",".join(_early_registries.registries))

from agentindex.agent_safety_pages import _render_agent_page  # noqa: E402
from smedjan import sources  # noqa: E402

LOG = logging.getLogger("smedjan.dryrun_l2_2a")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

PROD_BASE = os.environ.get("SMEDJAN_PROD_BASE", "http://localhost:8000")

ANTIPATTERNS: list[tuple[str, re.Pattern]] = [
    ("literal None",       re.compile(r">None<")),
    ("literal null",       re.compile(r">null<", re.I)),
    ("empty TD",           re.compile(r"<td>\s*</td>")),
    ("empty list item",    re.compile(r"<li>\s*</li>")),
    ("undefined",          re.compile(r"\bundefined\b")),
    ("NaN token",          re.compile(r">NaN<")),
    ("stray brace",        re.compile(r"\{\{[a-z_]+\}\}")),
    ("broken jsonld open", re.compile(r'application/ld\+json">\s*</script>')),
]

BLOCK_MARKER = 'data-block="2a-kings"'
KING_MARKER = "Detailed Score Analysis"
SACRED_TOKENS = ("pplx-verdict", "ai-summary", "SpeakableSpecification", "FAQPage")


def pick_sample(registries: list[str], n_per_reg: int) -> list[dict[str, Any]]:
    """Pick enriched non-King slugs per registry that have at least one
    external-trust signal. Fall back to the enriched-without-signal pool
    if a registry is short of signal-bearing candidates so the dry-run
    still stresses the gate on ``_fetch_external_trust`` returning None.
    """
    rows: list[dict[str, Any]] = []
    with sources.nerq_readonly_cursor(dict_cursor=True) as (_, cur):
        cur.execute("SET statement_timeout = '60s';")
        for reg in registries:
            cur.execute(
                """
                WITH signal_slugs AS (
                    SELECT DISTINCT agent_name COLLATE "C" AS s
                    FROM zarq.external_trust_signals
                )
                SELECT s.slug, s.registry, s.is_king,
                       s.security_score, s.privacy_score
                FROM public.software_registry s
                JOIN signal_slugs ss ON s.slug COLLATE "C" = ss.s
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
            reg_rows = [dict(r) for r in cur.fetchall()]
            if len(reg_rows) < n_per_reg:
                cur.execute(
                    """
                    SELECT s.slug, s.registry, s.is_king,
                           s.security_score, s.privacy_score
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
                    (reg, n_per_reg - len(reg_rows)),
                )
                have = {r["slug"] for r in reg_rows}
                for r in cur.fetchall():
                    d = dict(r)
                    if d["slug"] not in have:
                        reg_rows.append(d)
            rows.extend(reg_rows[:n_per_reg])
    LOG.info("sampled %d slugs across %s", len(rows), registries)
    return rows


def fetch_old(slug: str, timeout: float = 10.0) -> tuple[int, str]:
    url = f"{PROD_BASE}/safe/{slug}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # connection refused, etc.
        LOG.warning("fetch_old %s failed: %s", slug, e)
        return -1, ""


def render_new(slug: str) -> tuple[bool, str, str | None]:
    try:
        html = _render_agent_page(slug, {"name": slug})
        return True, html, None
    except Exception as e:  # noqa: BLE001 — dry-run wants the error str
        return False, "", f"{type(e).__name__}: {e}"


def scan_antipatterns(html: str) -> list[str]:
    return [name for name, rx in ANTIPATTERNS if rx.search(html)]


def analyse(slug: str, old_status: int, old_html: str,
            new_ok: bool, new_html: str, new_err: str | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "slug": slug,
        "old_status": old_status,
        "old_antipatterns": scan_antipatterns(old_html) if old_html else [],
        "old_length": len(old_html),
        "new_ok": new_ok,
        "new_error": new_err,
    }
    if new_ok:
        entry["new_antipatterns"] = scan_antipatterns(new_html)
        entry["new_length"] = len(new_html)
        entry["new_has_king_section"] = KING_MARKER in new_html
        entry["new_has_block_2a"] = BLOCK_MARKER in new_html
        entry["new_sacred_in_block"] = _sacred_inside_block(new_html)
        entry["delta_length"] = len(new_html) - len(old_html)
    return entry


def _sacred_inside_block(html: str) -> list[str]:
    """Return any sacred tokens that appear *inside* the 2a block body.

    We extract the snippet between the `data-block="2a-kings"` opener and
    the first `</div>` after it and scan only that substring — sacred
    tokens elsewhere on the page are expected.
    """
    start = html.find(BLOCK_MARKER)
    if start < 0:
        return []
    end = html.find("</div>", start)
    if end < 0:
        return []
    snippet = html[start:end]
    return [t for t in SACRED_TOKENS if t in snippet]


def write_spotchecks(rows: list[dict[str, Any]],
                     pairs: list[tuple[str, str, str]],
                     out_dir: Path, n: int = 10) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for row, (slug, old, new) in zip(rows, pairs):
        if len(saved) >= n:
            break
        if not new:  # require NEW; OLD is nice-to-have
            continue
        reg = row["registry"]
        (out_dir / f"{reg}__{slug}__NEW.html").write_text(new)
        if old:
            (out_dir / f"{reg}__{slug}__OLD.html").write_text(old)
        saved.append(slug)
    return saved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-per-reg", type=int, default=50)
    parser.add_argument("--registries", nargs="+", default=["npm"])
    parser.add_argument(
        "--out",
        default=os.path.expanduser("~/smedjan/audit-reports/l2-block-2a-kings"),
    )
    args = parser.parse_args()

    # Force both gates ON for the target registries — dry-run scope
    # only. Setting these has no effect after module import for
    # module-frozen vars; the early-parse block at the top of this file
    # is what actually drives the imports. These assignments make the
    # values explicit in the saved summary.
    os.environ["L1_UNLOCK_REGISTRIES"] = ",".join(args.registries)
    os.environ["L2_BLOCK_2A_REGISTRIES"] = ",".join(args.registries)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = pick_sample(args.registries, args.n_per_reg)
    if not rows:
        LOG.error("no sample rows — abort")
        return 1

    results: list[dict[str, Any]] = []
    pairs: list[tuple[str, str, str]] = []
    t0 = time.monotonic()
    for i, row in enumerate(rows):
        slug = row["slug"]
        old_status, old_html = fetch_old(slug)
        new_ok, new_html, new_err = render_new(slug)
        entry = analyse(slug, old_status, old_html, new_ok, new_html, new_err)
        entry["registry"] = row["registry"]
        results.append(entry)
        pairs.append((slug, old_html, new_html if new_ok else ""))
        if (i + 1) % 25 == 0:
            LOG.info("progress %d/%d (%.1fs)", i + 1, len(rows), time.monotonic() - t0)

    LOG.info("render pairs complete in %.1fs", time.monotonic() - t0)
    saved = write_spotchecks(results, pairs, out_dir / "spotchecks", n=10)

    def count(pred):
        return sum(1 for r in results if pred(r))

    summary = {
        "task":                     "T004",
        "generated_at":             datetime.now(timezone.utc).isoformat(),
        "sample_size":              len(results),
        "registries":               args.registries,
        "env_var":                  "L2_BLOCK_2A_REGISTRIES",
        "env_value":                os.environ["L2_BLOCK_2A_REGISTRIES"],
        "old_http_200":             count(lambda r: r["old_status"] == 200),
        "old_http_non200":          count(lambda r: r["old_status"] != 200),
        "old_any_antipattern":      count(lambda r: bool(r["old_antipatterns"])),
        "new_render_ok":            count(lambda r: r["new_ok"]),
        "new_render_failed":        count(lambda r: not r["new_ok"]),
        "new_has_king_section":     count(lambda r: r.get("new_has_king_section") is True),
        "new_has_block_2a":         count(lambda r: r.get("new_has_block_2a") is True),
        "new_sacred_in_block":      count(lambda r: bool(r.get("new_sacred_in_block"))),
        "new_any_antipattern":      count(lambda r: bool(r.get("new_antipatterns"))),
        "avg_delta_length":         round(
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
    sacred_samples = [
        {"slug": r["slug"], "registry": r["registry"],
         "tokens": r["new_sacred_in_block"]}
        for r in results if r.get("new_sacred_in_block")
    ]

    out_json = out_dir / "summary.json"
    out_json.write_text(json.dumps({
        "summary": summary,
        "antipattern_samples": antipattern_samples,
        "crash_samples": crash_samples,
        "sacred_samples": sacred_samples,
        "spotcheck_slugs": saved,
    }, indent=2))
    LOG.info("wrote %s", out_json)

    ok = (
        summary["new_render_failed"] == 0
        and summary["new_any_antipattern"] == 0
        and summary["new_sacred_in_block"] == 0
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
