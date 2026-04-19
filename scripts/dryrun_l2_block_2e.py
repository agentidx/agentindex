#!/usr/bin/env python3
"""
dryrun_l2_block_2e.py — L2 Block 2e shadow-mode dry-run harness (T118).

Renders the Block 2e snippet for the top N slugs by `ai_demand_score`
(initial scope: top 500; default sample here is 100) in all three modes
(off / shadow / live) and emits a diff report plus a sacred-byte audit.

Sacred tokens that must NEVER appear inside the block (the block lives
below king-sections and above FAQ — it must not echo any of these
GEO-critical markers into its own body):

    pplx-verdict
    ai-summary
    SpeakableSpecification
    FAQPage

Usage (from repo root, so `smedjan.*` imports resolve):

    python3 scripts/dryrun_l2_block_2e.py            # default N=100
    python3 scripts/dryrun_l2_block_2e.py --limit 25 # smaller sample

The report is written to
`~/smedjan/audit-reports/l2-block-2e-dryrun-<UTC timestamp>.json` when
that directory exists, otherwise to `/tmp/`. A short summary is echoed
to stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from smedjan import sources  # noqa: E402
from smedjan.renderers.block_2e import render_block_2e_html  # noqa: E402

SACRED_TOKENS = (
    "pplx-verdict",
    "ai-summary",
    "SpeakableSpecification",
    "FAQPage",
)


def _pick_top_slugs(limit: int) -> list[str]:
    """Top slugs by `ai_demand_score` that also have non-empty
    `dimensions` on Nerq RO. Widens the demand pool until we have
    `limit` candidates with dimensions; falls back to any slugs with
    dimensions (regardless of demand) when the intersection is short —
    the dry-run is about block validation, not demand ranking.
    """
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(
            "SELECT slug FROM smedjan.ai_demand_scores "
            "ORDER BY score DESC LIMIT %s",
            (max(limit * 20, 2000),),
        )
        candidates = [r[0] for r in cur.fetchall()]

    with_dims: list[str] = []
    if candidates:
        with sources.nerq_readonly_cursor() as (_, cur):
            cur.execute(
                "SELECT slug FROM public.software_registry "
                "WHERE slug = ANY(%s) "
                "AND dimensions IS NOT NULL "
                "AND dimensions::text NOT IN ('{}','null')",
                (candidates,),
            )
            hit = {r[0] for r in cur.fetchall()}
        with_dims = [s for s in candidates if s in hit]
    if len(with_dims) >= limit:
        return with_dims[:limit]

    needed = limit - len(with_dims)
    have = set(with_dims)
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT slug FROM public.software_registry "
            "WHERE dimensions IS NOT NULL "
            "AND dimensions::text NOT IN ('{}','null') "
            "ORDER BY slug LIMIT %s",
            (limit * 3,),
        )
        for row in cur.fetchall():
            if needed <= 0:
                break
            s = row[0]
            if s not in have:
                with_dims.append(s)
                have.add(s)
                needed -= 1
    return with_dims[:limit]


def _wrap(raw: str | None, mode: str) -> str:
    if raw is None:
        return ""
    if mode == "off":
        return ""
    if mode == "shadow":
        safe = raw.replace("--", "- -")
        return f"<!-- L2_BLOCK_2E_SHADOW\n{safe}\n-->"
    return raw  # live


def _audit_sacred(s: str) -> list[str]:
    return [tok for tok in SACRED_TOKENS if tok in s]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    slugs = _pick_top_slugs(args.limit)
    if not slugs:
        print("no candidate slugs found (no ai_demand × dimensions overlap, "
              "and no dimensions-bearing slugs on Nerq RO)")
        return 1

    per_slug = []
    n_none = 0
    n_rendered = 0
    sacred_hits: list[dict] = []

    for slug in slugs:
        raw = render_block_2e_html(slug)
        off_out = _wrap(raw, "off")
        shadow_out = _wrap(raw, "shadow")
        live_out = _wrap(raw, "live")

        if raw is None:
            n_none += 1
        else:
            n_rendered += 1

        for mode_name, payload in (
            ("off", off_out),
            ("shadow", shadow_out),
            ("live", live_out),
        ):
            hits = _audit_sacred(payload)
            if hits:
                sacred_hits.append({"slug": slug, "mode": mode_name, "tokens": hits})

        per_slug.append({
            "slug": slug,
            "rendered": raw is not None,
            "bytes_live": len(live_out),
            "bytes_shadow": len(shadow_out),
            "bytes_off": len(off_out),
            "live_shadow_diff_bytes": len(shadow_out) - len(live_out),
        })

    report = {
        "task": "T118",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(slugs),
        "rendered": n_rendered,
        "empty_or_no_data": n_none,
        "sacred_token_hits": sacred_hits,
        "sacred_tokens_checked": list(SACRED_TOKENS),
        "per_slug": per_slug,
    }

    out_dir = Path.home() / "smedjan" / "audit-reports"
    if not out_dir.is_dir():
        out_dir = Path("/tmp")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"l2-block-2e-dryrun-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2))

    print(f"task          : T118 L2 Block 2e dry-run")
    print(f"sample        : {len(slugs)} slugs (top by ai_demand_score, dimensions-filtered)")
    print(f"rendered      : {n_rendered}")
    print(f"no-data       : {n_none}")
    print(f"sacred hits   : {len(sacred_hits)}")
    print(f"report        : {out_path}")

    return 0 if not sacred_hits else 2


if __name__ == "__main__":
    raise SystemExit(main())
