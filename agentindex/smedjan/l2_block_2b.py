"""L2 Block 2b — dependency graph block (T005, registry-allowlist gate).

Renders a ``Dependency Graph`` panel inside ``king_sections`` on the
``/safe/{slug}`` page, ABOVE the Block 2a "External Trust Signals"
section (which itself sits above "Detailed Score Analysis"). Gated on
``L2_BLOCK_2B_REGISTRIES`` using the same fail-closed allowlist
semantics as the L1 canary playbook / Block 2a registry gate.

Why a second Block 2b module
----------------------------
``smedjan/renderers/block_2b.py`` (T112) surfaces raw dependency-edge
features — direct deps, 2-hop transitive, cycle flag — inside an HTML
comment (shadow mode). This new module supersedes that surface for
live rendering: it instead leans on Nerq-exclusive reverse-dependency
counts, the read-only ``trust_score`` join on
``public.software_registry``, and ``deprecated`` / ``last_commit`` /
``last_release_date`` to detect dormant upstreams. The T112 module is
still used for shadow-mode audits; the two paths are deliberately
independent so the T112 auditor can continue to run unchanged.

Data sources (Nerq read-only replica)
-------------------------------------
- ``public.dependency_edges`` — npm-only today, ~886K rows covering
  ~60K distinct from-entities. Used for both the forward edges
  (``entity_from = slug``) and the reverse-dep count
  (``entity_to = slug``). Excludes ``dependency_type = 'dev'`` for both
  directions — runtime dependencies are the citable surface; dev-only
  relationships over-state coupling.
- ``public.software_registry`` — joined on
  ``(slug, registry='npm')`` to pick up ``trust_score`` for the
  avg-dep-trust prose and ``deprecated`` / ``last_commit`` /
  ``last_release_date`` for the dormant-upstream warning.

The block is fail-closed: any unexpected error returns ``None`` so the
safety page renders unchanged. The caller additionally short-circuits
when the slug's registry is not on the ``L2_BLOCK_2B_REGISTRIES``
allowlist.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("agentindex.smedjan.l2_block_2b")

DORMANT_THRESHOLD_DAYS = 365


def _fetch_dependency_graph(slug: str) -> Optional[dict]:
    """Return a dict with dependency-graph surface fields for ``slug``.

    Returns ``None`` when the entity has no forward edges AND no reverse
    edges (nothing citable to render), when the replica is unreachable,
    or when any unexpected error occurs. The caller must therefore
    treat ``None`` as "do not render".

    ``COLLATE "C"`` is applied on equality because the Nerq replica has
    an ICU collation drift that silently returns zero rows for
    byte-identical strings — the same workaround the T112 renderer and
    the T004 Block 2a helper use.

    Shape of the returned dict::

        {
            "reverse_count":     int,      # packages that depend on slug
            "direct_count":      int,      # non-dev forward edges
            "dev_count":         int,      # dev-only forward edges
            "avg_dep_trust":     float|None,  # mean trust_score of direct deps
            "deps_with_trust":   int,      # sample size behind avg_dep_trust
            "dormant":           bool,
            "dormant_reason":    str|None, # e.g. "deprecated", "no_release_in_456d"
        }
    """
    try:
        from smedjan import sources  # lazy: keep factory deps off import path
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("l2_block_2b: sources import failed: %s", exc)
        return None

    try:
        with sources.nerq_readonly_cursor() as (_, cur):
            cur.execute(
                "SELECT COUNT(*) FROM public.dependency_edges "
                "WHERE entity_to COLLATE \"C\" = %s "
                "AND registry = 'npm' AND dependency_type <> 'dev'",
                (slug,),
            )
            reverse_count = int(cur.fetchone()[0] or 0)

            cur.execute(
                "SELECT entity_to, dependency_type "
                "FROM public.dependency_edges "
                "WHERE entity_from COLLATE \"C\" = %s "
                "AND registry = 'npm'",
                (slug,),
            )
            edges = cur.fetchall()
            direct = [r[0] for r in edges if r[1] != "dev"]
            dev = [r[0] for r in edges if r[1] == "dev"]

            if not direct and not dev and reverse_count == 0:
                return None

            avg_trust: Optional[float] = None
            deps_with_trust = 0
            if direct:
                cur.execute(
                    "SELECT AVG(trust_score), COUNT(*) "
                    "FROM public.software_registry "
                    "WHERE registry = 'npm' "
                    "AND slug COLLATE \"C\" = ANY(%s) "
                    "AND trust_score IS NOT NULL",
                    (direct,),
                )
                row = cur.fetchone()
                if row and row[1]:
                    avg_trust = float(row[0])
                    deps_with_trust = int(row[1])

            cur.execute(
                "SELECT deprecated, last_commit, last_release_date, last_updated "
                "FROM public.software_registry "
                "WHERE registry = 'npm' AND slug COLLATE \"C\" = %s "
                "LIMIT 1",
                (slug,),
            )
            meta_row = cur.fetchone()

    except Exception as exc:  # SourceUnavailable or psycopg.Error
        log.warning("l2_block_2b: fetch failed for %s: %s", slug, exc)
        return None

    dormant, dormant_reason = _classify_dormant(meta_row)

    return {
        "reverse_count": reverse_count,
        "direct_count": len(direct),
        "dev_count": len(dev),
        "avg_dep_trust": avg_trust,
        "deps_with_trust": deps_with_trust,
        "dormant": dormant,
        "dormant_reason": dormant_reason,
    }


def _classify_dormant(meta_row) -> tuple[bool, Optional[str]]:
    """Translate the upstream freshness tuple into (dormant, reason).

    Mirrors the heuristic documented in
    ``smedjan/docs/L4-dependencies-schema.md`` so the prose on this
    block and the JSON on ``/dependencies/{slug}.json`` agree.
    """
    if meta_row is None:
        return (False, None)
    deprecated, last_commit, last_release, last_updated = meta_row
    if deprecated:
        return (True, "deprecated")
    candidates = [c for c in (last_commit, last_release, last_updated) if c is not None]
    if not candidates:
        return (False, None)  # prefer silent over a noisy "no_signal"
    newest = max(candidates)
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - newest).days
    if age_days > DORMANT_THRESHOLD_DAYS:
        return (True, f"no_release_in_{age_days}d")
    return (False, None)


def _format_dormant_warning(data: dict) -> str:
    if not data["dormant"]:
        return ""
    reason = data["dormant_reason"] or "dormant"
    if reason == "deprecated":
        tail = "the upstream package is marked deprecated."
    elif reason.startswith("no_release_in_"):
        days = reason.removeprefix("no_release_in_").rstrip("d")
        tail = f"no commit, release, or update seen in {days} days."
    else:
        tail = reason
    return (
        f'<li><strong>Dormant upstream:</strong> heads up — {tail}</li>'
    )


def render_dependency_graph_html(slug: str) -> Optional[str]:
    """Return the Block 2b HTML snippet for ``slug`` or ``None`` if empty.

    The output is a single ``<div class="section">…</div>`` modelled on
    the T004 Block 2a block so it inherits the surrounding CSS without
    new styles. It contains none of the sacred tokens
    (``pplx-verdict``, ``ai-summary``, ``SpeakableSpecification``,
    ``FAQPage``) — the caller may therefore splice it directly into
    ``king_sections`` above Block 2a without touching any GEO-critical
    markup.
    """
    data = _fetch_dependency_graph(slug)
    if data is None:
        return None

    lines: list[str] = []
    if data["reverse_count"] > 0:
        lines.append(
            f'<li><strong>Depended on by:</strong> '
            f'{data["reverse_count"]:,} other npm packages.</li>'
        )

    if data["direct_count"] > 0:
        if data["avg_dep_trust"] is not None:
            lines.append(
                f'<li><strong>Direct dependencies:</strong> '
                f'{data["direct_count"]:,} '
                f'(+{data["dev_count"]:,} dev). Their trust scores '
                f'average {data["avg_dep_trust"]:.0f}/100 across '
                f'{data["deps_with_trust"]:,} scored deps.</li>'
            )
        else:
            lines.append(
                f'<li><strong>Direct dependencies:</strong> '
                f'{data["direct_count"]:,} '
                f'(+{data["dev_count"]:,} dev). Trust-score averages '
                f'not yet available for this slug\'s deps.</li>'
            )

    warning = _format_dormant_warning(data)
    if warning:
        lines.append(warning)

    if not lines:
        return None

    s_slug = html.escape(slug)
    return (
        f'<div class="section block-2b-kings" data-block="2b-kings" data-slug="{s_slug}">'
        '<h2 class="section-title">Dependency Graph</h2>'
        '<p style="font-size:14px;color:#64748b;margin:0 0 8px">'
        "Runtime dependency coupling, derived from Nerq's open-source "
        "package graph. npm scope."
        "</p>"
        '<ul style="font-size:15px;line-height:1.7;color:#374151;margin:0;padding-left:20px">'
        + "".join(lines)
        + "</ul></div>"
    )
