#!/usr/bin/env python3
"""
dryrun_l2_block_2c.py — L2 Block 2c dry-run harness.

Two implementations share the task number:

* **T114** (shadow-mode AI-demand-timeline renderer) lives in
  ``smedjan/renderers/block_2c.py`` and renders a current-score /
  7d-delta / 30d-delta / 3σ-surge snippet inside an HTML comment.
* **T006** (king-section trust-score signal timeline) lives in
  ``agentindex/smedjan/l2_block_2c.py`` and renders a prose
  "Trust score history … / Last significant change …" snippet gated by
  ``L2_BLOCK_2C_REGISTRIES``.

This harness exercises **both** so the T114 shadow stream keeps its
regression checks and the T006 path has its 100-slug acceptance
evidence.

Sacred tokens that must NEVER appear in either rendered block (those
belong to GEO/SEO-critical markup elsewhere on the page):

    pplx-verdict
    ai-summary
    SpeakableSpecification
    FAQPage

Usage (from repo root, so both ``smedjan.*`` and
``agentindex.smedjan.*`` imports resolve):

    python3 scripts/dryrun_l2_block_2c.py            # default N=100
    python3 scripts/dryrun_l2_block_2c.py --limit 25 # smaller sample

The report is written to
``~/smedjan/audit-reports/l2-block-2c-dryrun-<UTC timestamp>.json``
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
from smedjan.renderers.block_2c import render_block_2c_html  # noqa: E402

SACRED_TOKENS = (
    "pplx-verdict",
    "ai-summary",
    "SpeakableSpecification",
    "FAQPage",
)

# The five registries with the highest trust-score-event coverage, per
# the 2026-04-19 `public.signal_events` survey. Sampling inside this
# allowlist maximises the odds of hitting the ≥3-events path (229 of
# 256 eligible rows sit in exactly 3 events) without biasing toward a
# single registry.
CANARY_REGISTRIES = ("crates", "npm", "pypi", "homebrew", "gems")


def _pick_top_slugs(limit: int) -> list[tuple[str, str]]:
    """Return up to ``limit`` ``(slug, registry)`` pairs that have at
    least three trust-score events in the canary registries AND a
    non-null ``trust_score`` in ``public.software_registry``. When the
    strict-eligible pool is short, widen to ≥2 events, then ≥1, so the
    100-sample harness always has material to work with.
    """
    with sources.nerq_readonly_cursor() as (_, cur):
        out: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for min_events in (3, 2, 1):
            cur.execute(
                "WITH per_ent AS ( "
                "  SELECT entity_id, registry, COUNT(*) AS c "
                "  FROM public.signal_events "
                "  WHERE signal_type IN ('trust_drop_10plus','trust_gain_10plus') "
                "    AND registry = ANY(%s) "
                "  GROUP BY entity_id, registry "
                "  HAVING COUNT(*) >= %s "
                ") "
                "SELECT e.entity_id, e.registry "
                "FROM per_ent e "
                "JOIN public.software_registry sr "
                "  ON sr.slug COLLATE \"C\" = e.entity_id COLLATE \"C\" "
                "  AND sr.registry COLLATE \"C\" = e.registry COLLATE \"C\" "
                "WHERE sr.trust_score IS NOT NULL "
                "ORDER BY e.c DESC, e.entity_id ASC "
                "LIMIT %s",
                (list(CANARY_REGISTRIES), min_events, limit * 2),
            )
            for row in cur.fetchall():
                key = (row[0], row[1])
                if key in seen:
                    continue
                seen.add(key)
                out.append(key)
                if len(out) >= limit:
                    return out
        return out


def _wrap(raw: str | None, mode: str) -> str:
    if raw is None:
        return ""
    if mode == "off":
        return ""
    if mode == "shadow":
        safe = raw.replace("--", "- -")
        return f"<!-- L2_BLOCK_2C_SHADOW\n{safe}\n-->"
    return raw  # live


def _audit_sacred(s: str) -> list[str]:
    return [tok for tok in SACRED_TOKENS if tok in s]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    # Exercise the T006 registry-gated path end-to-end by flipping the
    # env var in-process before importing the renderer wrapper. The
    # module-level allowlist in ``agent_safety_pages`` is rebuilt on
    # every call, so this just re-confirms the live branch is wired.
    os.environ["L2_BLOCK_2C_REGISTRIES"] = ",".join(CANARY_REGISTRIES)

    from agentindex.smedjan.l2_block_2c import render_signal_timeline_html  # noqa: E402
    from agentindex.agent_safety_pages import _l2_block_2c_registry_html  # noqa: E402

    pairs = _pick_top_slugs(args.limit)
    if not pairs:
        print("no candidate slugs found (no trust-score events in canary regs)")
        return 1

    per_slug = []
    n_t114_rendered = 0
    n_t006_rendered = 0
    n_crashes = 0
    sacred_hits: list[dict] = []

    for slug, registry in pairs:
        # T114 shadow-mode stub (keyed off slug only; registry is not
        # part of the AI-demand-timeline lookup).
        try:
            raw_t114 = render_block_2c_html(slug)
        except Exception as exc:
            n_crashes += 1
            per_slug.append({"slug": slug, "registry": registry, "crash": f"T114: {exc!r}"})
            continue

        off_out = _wrap(raw_t114, "off")
        shadow_out = _wrap(raw_t114, "shadow")
        live_out = _wrap(raw_t114, "live")

        if raw_t114 is not None:
            n_t114_rendered += 1

        for mode_name, payload in (
            ("off", off_out),
            ("shadow", shadow_out),
            ("live", live_out),
        ):
            hits = _audit_sacred(payload)
            if hits:
                sacred_hits.append({"impl": "T114", "slug": slug, "mode": mode_name, "tokens": hits})

        # T006 king-section trust-score block (direct render + full
        # gated wrapper so we cover both the helper and the dispatcher).
        try:
            raw_t006 = render_signal_timeline_html(slug, registry)
            gated = _l2_block_2c_registry_html(slug, registry)
        except Exception as exc:
            n_crashes += 1
            per_slug.append({"slug": slug, "registry": registry, "crash": f"T006: {exc!r}"})
            continue

        if raw_t006 is not None:
            n_t006_rendered += 1

        for variant, payload in (
            ("direct", raw_t006 or ""),
            ("gated", gated),
        ):
            hits = _audit_sacred(payload)
            if hits:
                sacred_hits.append({"impl": "T006", "slug": slug, "variant": variant, "tokens": hits})

        # Gated output should exactly equal the direct render when the
        # allowlist names the slug's registry. Any divergence is an
        # antipattern — callers would silently drop content.
        gate_divergence = None
        if (raw_t006 or "") != gated:
            gate_divergence = {
                "direct_bytes": len(raw_t006 or ""),
                "gated_bytes": len(gated),
            }

        per_slug.append({
            "slug": slug,
            "registry": registry,
            "t114_rendered": raw_t114 is not None,
            "t006_rendered": raw_t006 is not None,
            "t006_gated_bytes": len(gated),
            "t114_bytes_live": len(live_out),
            "gate_divergence": gate_divergence,
        })

    report = {
        "task": "T006",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(pairs),
        "canary_registries": list(CANARY_REGISTRIES),
        "t114_rendered": n_t114_rendered,
        "t006_rendered": n_t006_rendered,
        "crashes": n_crashes,
        "sacred_token_hits": sacred_hits,
        "sacred_tokens_checked": list(SACRED_TOKENS),
        "per_slug": per_slug,
    }

    out_dir = Path.home() / "smedjan" / "audit-reports"
    if not out_dir.is_dir():
        out_dir = Path("/tmp")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"l2-block-2c-dryrun-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))

    divergence_count = sum(1 for row in per_slug if row.get("gate_divergence"))

    print(f"task            : T006 L2 Block 2c dry-run (T114 + T006 impls)")
    print(f"sample          : {len(pairs)} (slug, registry) pairs, top-5 canary regs")
    print(f"t114 rendered   : {n_t114_rendered}")
    print(f"t006 rendered   : {n_t006_rendered}")
    print(f"crashes         : {n_crashes}")
    print(f"sacred hits     : {len(sacred_hits)}")
    print(f"gate divergence : {divergence_count}")
    print(f"report          : {out_path}")

    if n_crashes or sacred_hits or divergence_count:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
