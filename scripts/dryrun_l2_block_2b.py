#!/usr/bin/env python3
"""
dryrun_l2_block_2b.py — L2 Block 2b dry-run harness.

Two implementations share the task number:

* **T112** (shadow-mode dependency-edges stub) lives in
  ``smedjan/renderers/block_2b.py`` and renders direct / transitive /
  cycle features inside an HTML comment.
* **T005** (king-section trust-score block) lives in
  ``agentindex/smedjan/l2_block_2b.py`` and renders a prose
  "Depended on by N — avg dep trust M/100 — dormant?" snippet gated by
  ``L2_BLOCK_2B_REGISTRIES``.

This harness exercises **both** so the T112 shadow stream keeps its
regression tests and the T005 path has its 100-slug acceptance
evidence.

Sacred tokens that must NEVER appear in either rendered block (those
belong to GEO/SEO-critical markup elsewhere on the page):

    pplx-verdict
    ai-summary
    SpeakableSpecification
    FAQPage

Usage (from repo root, so both ``smedjan.*`` and
``agentindex.smedjan.*`` imports resolve):

    python3 scripts/dryrun_l2_block_2b.py            # default N=100
    python3 scripts/dryrun_l2_block_2b.py --limit 25 # smaller sample

The report is written to
``~/smedjan/audit-reports/l2-block-2b-dryrun-<UTC timestamp>.json``
when that directory exists, otherwise to ``/tmp/``. A short summary is
echoed to stdout.
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    # Exercise the T005 registry-gated path end-to-end by flipping the
    # env var in-process before importing the renderer wrapper. The
    # module-level allowlist in ``agent_safety_pages`` is rebuilt on
    # every call, so this just re-confirms the live branch is wired.
    os.environ["L2_BLOCK_2B_REGISTRIES"] = "npm"

    from agentindex.smedjan.l2_block_2b import render_dependency_graph_html  # noqa: E402
    from agentindex.agent_safety_pages import _l2_block_2b_registry_html  # noqa: E402

    slugs = _pick_top_slugs(args.limit)
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


if __name__ == "__main__":
    raise SystemExit(main())
