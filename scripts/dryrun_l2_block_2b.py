#!/usr/bin/env python3
"""
dryrun_l2_block_2b.py — L2 Block 2b dry-run harness.

Two harnesses live in this file, selected by `--mode`:

  --mode combined   (default, T112 + T005)
      For the top-N (default 100) slugs by ai_demand_score that also
      have at least one npm dependency edge, render BOTH the T112
      shadow-mode stub (``smedjan/renderers/block_2b.py``) and the T005
      king-section trust-score block
      (``agentindex/smedjan/l2_block_2b.py``). Audits each output for
      sacred GEO/SEO tokens and verifies the registry-allowlist gate
      does not silently drop content.

  --mode standalone (T301 / T112 L2_BLOCK_2B_MODE variant)
      Builds a top-N (default 1000) population of slugs by
      ai_demand_score that also have at least one npm dependency edge,
      then renders a top-K (default 100) sample of that population
      through ``render_block_2b_html`` in off / shadow / live and
      audits each output for the four sacred GEO-critical tokens
      (pplx-verdict, ai-summary, SpeakableSpecification, FAQPage).
      Mirrors the T300 standalone harness for Block 2a.

Sacred tokens that must NEVER appear in either rendered block (those
belong to GEO/SEO-critical markup elsewhere on the page):

    pplx-verdict
    ai-summary
    SpeakableSpecification
    FAQPage

Usage (from repo root, so both ``smedjan.*`` and
``agentindex.smedjan.*`` imports resolve):

    python3 scripts/dryrun_l2_block_2b.py                   # combined, N=100
    python3 scripts/dryrun_l2_block_2b.py --limit 25        # combined, N=25
    python3 scripts/dryrun_l2_block_2b.py --mode standalone # T301: 1K pop, 100 sample
    python3 scripts/dryrun_l2_block_2b.py --mode standalone --population 1000 --limit 100

Reports are written to:

    combined   → ~/smedjan/audit-reports/l2-block-2b-dryrun-<UTC>.json
    standalone → ~/smedjan/audit-reports/l2-block-2b-standalone/l2-block-2b-standalone-<UTC>.json

A short summary is echoed to stdout in both cases.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from smedjan import sources  # noqa: E402
from smedjan.renderers.block_2b import render_block_2b_html  # noqa: E402

SACRED_TOKENS = (
    "pplx-verdict",
    "ai-summary",
    "SpeakableSpecification",
    "FAQPage",
)


def _pick_top_slugs(limit: int) -> list[str]:
    """Top slugs by `ai_demand_score` that also have at least one npm
    dependency edge. Falls back to top-by-edge-count npm entities when
    the ai_demand × npm overlap is shorter than `limit` — the dry-run
    is about block validation, not demand ranking, so we widen the pool
    rather than return a short sample.
    """
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(
            "SELECT slug FROM smedjan.ai_demand_scores "
            "ORDER BY score DESC LIMIT %s",
            (max(limit * 20, 2000),),
        )
        candidates = [r[0] for r in cur.fetchall()]
    with_edges: list[str] = []
    if candidates:
        with sources.nerq_readonly_cursor() as (_, cur):
            # COLLATE "C" works around an ICU collation drift on Nerq RO
            # where default equality returns zero rows for byte-identical
            # strings.
            cur.execute(
                "SELECT DISTINCT entity_from FROM public.dependency_edges "
                "WHERE entity_from COLLATE \"C\" = ANY(%s) "
                "AND registry = 'npm'",
                (candidates,),
            )
            hit = {r[0] for r in cur.fetchall()}
        with_edges = [s for s in candidates if s in hit]
    if len(with_edges) >= limit:
        return with_edges[:limit]

    needed = limit - len(with_edges)
    have = set(with_edges)
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT entity_from, COUNT(*) AS c FROM public.dependency_edges "
            "WHERE registry = 'npm' GROUP BY entity_from "
            "ORDER BY c DESC LIMIT %s",
            (limit * 3,),
        )
        for row in cur.fetchall():
            if needed <= 0:
                break
            s = row[0]
            if s not in have:
                with_edges.append(s)
                have.add(s)
                needed -= 1
    return with_edges[:limit]


def _wrap(raw: str | None, mode: str) -> str:
    """Mirror agent_safety_pages._l2_block_2b_html exactly."""
    if raw is None:
        return ""
    if mode == "off":
        return ""
    if mode == "shadow":
        safe = raw.replace("--", "- -")
        return f"<!-- L2_BLOCK_2B_SHADOW\n{safe}\n-->"
    return raw  # live


def _audit_sacred(s: str) -> list[str]:
    return [tok for tok in SACRED_TOKENS if tok in s]


def run_combined(limit: int) -> int:
    """T112 + T005 combined harness. Renders both the shadow-mode stub
    and the king-section trust-score block for the same sample.
    """
    # Exercise the T005 registry-gated path end-to-end by flipping the
    # env var in-process before importing the renderer wrapper. The
    # module-level allowlist in ``agent_safety_pages`` is rebuilt on
    # every call, so this just re-confirms the live branch is wired.
    os.environ["L2_BLOCK_2B_REGISTRIES"] = "npm"

    from agentindex.smedjan.l2_block_2b import render_dependency_graph_html  # noqa: E402
    from agentindex.agent_safety_pages import _l2_block_2b_registry_html  # noqa: E402

    slugs = _pick_top_slugs(limit)
    if not slugs:
        print("no candidate slugs found (no ai_demand × dependency_edges overlap)")
        return 1

    per_slug = []
    n_t112_rendered = 0
    n_t005_rendered = 0
    n_crashes = 0
    sacred_hits: list[dict] = []

    for slug in slugs:
        # T112 shadow-mode stub
        try:
            raw_t112 = render_block_2b_html(slug)
        except Exception as exc:
            n_crashes += 1
            per_slug.append({"slug": slug, "crash": f"T112: {exc!r}"})
            continue

        off_out = _wrap(raw_t112, "off")
        shadow_out = _wrap(raw_t112, "shadow")
        live_out = _wrap(raw_t112, "live")

        if raw_t112 is not None:
            n_t112_rendered += 1

        for mode_name, payload in (
            ("off", off_out),
            ("shadow", shadow_out),
            ("live", live_out),
        ):
            hits = _audit_sacred(payload)
            if hits:
                sacred_hits.append({"impl": "T112", "slug": slug, "mode": mode_name, "tokens": hits})

        # T005 king-section trust-score block (direct render + full
        # gated wrapper so we cover both the helper and the dispatcher).
        try:
            raw_t005 = render_dependency_graph_html(slug)
            gated = _l2_block_2b_registry_html(slug, "npm")
        except Exception as exc:
            n_crashes += 1
            per_slug.append({"slug": slug, "crash": f"T005: {exc!r}"})
            continue

        if raw_t005 is not None:
            n_t005_rendered += 1

        for variant, payload in (
            ("direct", raw_t005 or ""),
            ("gated", gated),
        ):
            hits = _audit_sacred(payload)
            if hits:
                sacred_hits.append({"impl": "T005", "slug": slug, "variant": variant, "tokens": hits})

        # Gated output should exactly equal the direct render when the
        # allowlist names the slug's registry. Any divergence is an
        # antipattern — callers would silently drop content.
        gate_divergence = None
        if (raw_t005 or "") != gated:
            gate_divergence = {
                "direct_bytes": len(raw_t005 or ""),
                "gated_bytes": len(gated),
            }

        per_slug.append({
            "slug": slug,
            "t112_rendered": raw_t112 is not None,
            "t005_rendered": raw_t005 is not None,
            "t005_gated_bytes": len(gated),
            "t112_bytes_live": len(live_out),
            "gate_divergence": gate_divergence,
        })

    report = {
        "task": "T005",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(slugs),
        "t112_rendered": n_t112_rendered,
        "t005_rendered": n_t005_rendered,
        "crashes": n_crashes,
        "sacred_token_hits": sacred_hits,
        "sacred_tokens_checked": list(SACRED_TOKENS),
        "per_slug": per_slug,
    }

    out_dir = Path.home() / "smedjan" / "audit-reports"
    if not out_dir.is_dir():
        out_dir = Path("/tmp")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"l2-block-2b-dryrun-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2))

    divergence_count = sum(1 for row in per_slug if row.get("gate_divergence"))

    print(f"task            : T005 L2 Block 2b dry-run (T112 + T005 impls)")
    print(f"sample          : {len(slugs)} slugs (top by ai_demand_score, npm-filtered)")
    print(f"t112 rendered   : {n_t112_rendered}")
    print(f"t005 rendered   : {n_t005_rendered}")
    print(f"crashes         : {n_crashes}")
    print(f"sacred hits     : {len(sacred_hits)}")
    print(f"gate divergence : {divergence_count}")
    print(f"report          : {out_path}")

    if n_crashes or sacred_hits or divergence_count:
        return 2
    return 0


def run_standalone(population_size: int, sample_size: int, out_dir: Path) -> int:
    """T301 / T112 standalone harness.

    Builds a top-`population_size` enriched-slug population (ranked by
    ai_demand_score, filtered to those with ≥1 npm dependency edge),
    then renders the first `sample_size` slugs through block_2b in
    off / shadow / live and audits each output for sacred tokens.
    """
    population = _pick_top_slugs(population_size)
    if not population:
        print("no candidate slugs found (no ai_demand × dependency_edges overlap)")
        return 1

    sample = population[:sample_size]

    per_slug: list[dict] = []
    n_none = 0
    n_rendered = 0
    sacred_hits: list[dict] = []

    for slug in sample:
        raw = render_block_2b_html(slug)
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
            "bytes_off": len(off_out),
            "bytes_shadow": len(shadow_out),
            "bytes_live": len(live_out),
            "shadow_minus_live_bytes": len(shadow_out) - len(live_out),
        })

    report = {
        "task":                  "T301",
        "harness":               "standalone (L2_BLOCK_2B_MODE)",
        "generated_at":          datetime.now(timezone.utc).isoformat(),
        "population_target":     population_size,
        "population_actual":     len(population),
        "sample_size":           len(sample),
        "rendered":              n_rendered,
        "empty_or_no_data":      n_none,
        "sacred_token_hits":     sacred_hits,
        "sacred_tokens_checked": list(SACRED_TOKENS),
        "per_slug":              per_slug,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"l2-block-2b-standalone-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2))

    print(f"task            : T301 L2 Block 2b standalone (L2_BLOCK_2B_MODE)")
    print(f"population      : {len(population)} / {population_size} target")
    print(f"sample          : {len(sample)} slugs")
    print(f"rendered        : {n_rendered}")
    print(f"empty / no-data : {n_none}")
    print(f"sacred hits     : {len(sacred_hits)}")
    print(f"report          : {out_path}")

    if sacred_hits:
        print("VERDICT: HOLD — sacred token leaked into block body")
        return 2
    print(f"VERDICT: GO — 0 sacred_token_hits across {len(sample)}-slug sample")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mode",
        choices=("combined", "standalone"),
        default="combined",
        help="combined = T112+T005 paired harness (default); "
             "standalone = T301 L2_BLOCK_2B_MODE off/shadow/live audit.",
    )
    ap.add_argument(
        "--limit", type=int, default=100,
        help="Sample size. Combined mode: number of slugs rendered. "
             "Standalone mode: top-K of the --population pool to render.",
    )
    ap.add_argument(
        "--population", type=int, default=1000,
        help="Standalone mode only: size of the top-N enriched-slug "
             "population from which --limit is sampled (default 1000).",
    )
    ap.add_argument(
        "--out",
        default=os.path.expanduser("~/smedjan/audit-reports/l2-block-2b-standalone"),
        help="Standalone mode only: output directory (default "
             "~/smedjan/audit-reports/l2-block-2b-standalone).",
    )
    args = ap.parse_args()

    if args.mode == "standalone":
        return run_standalone(args.population, args.limit, Path(args.out))
    return run_combined(args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
