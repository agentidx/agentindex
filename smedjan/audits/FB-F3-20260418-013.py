"""Generate /compare/ coverage proposals for FB-F3-20260418-013.

Picks the highest-demand slugs (smedjan.ai_demand_scores), maps each slug
to the registries (entity_lookup.source) that carry it, cross-pairs the
top slugs within each registry, ranks pairs by combined demand, and
curls https://nerq.ai/compare/<a>-vs-<b> for the top 50.
"""
from __future__ import annotations

import json
import subprocess
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, "/Users/anstudio/agentindex")

from smedjan import sources  # noqa: E402

OUT = Path("/Users/anstudio/smedjan/audits/FB-F3-20260418-013.md")
TOP_SLUGS_FETCH = 400
TOP_SLUGS_PER_REGISTRY = 12
MAX_PAIRS = 50


def fetch_demand_scores(limit: int) -> dict[str, float]:
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(
            "SELECT slug, score FROM smedjan.ai_demand_scores "
            "WHERE slug IS NOT NULL AND score IS NOT NULL "
            "ORDER BY score DESC LIMIT %s",
            (limit,),
        )
        return {slug: float(score) for slug, score in cur.fetchall()}


def fetch_slug_registries(slugs: list[str]) -> dict[tuple[str, str], None]:
    """Return the distinct (source, slug) combinations that exist in Nerq."""
    pairs: dict[tuple[str, str], None] = {}
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT DISTINCT source, slug FROM entity_lookup "
            "WHERE slug = ANY(%s) AND source IS NOT NULL",
            (slugs,),
        )
        for source, slug in cur.fetchall():
            pairs[(source, slug)] = None
    return pairs


def curl_status(url: str) -> str:
    try:
        out = subprocess.run(
            [
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "--max-time",
                "10",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return out.stdout.strip() or "000"
    except Exception:
        return "000"


def recommend(status: str) -> str:
    if status == "404":
        return "create"
    if status == "200":
        return "skip"
    return "investigate"


def main() -> int:
    demand = fetch_demand_scores(TOP_SLUGS_FETCH)
    if not demand:
        print("no demand scores", file=sys.stderr)
        return 1
    slugs = list(demand.keys())
    combos = fetch_slug_registries(slugs)

    # Group slugs by registry, ranked by demand.
    by_registry: dict[str, list[str]] = {}
    for (source, slug) in combos:
        by_registry.setdefault(source, []).append(slug)
    for source, lst in by_registry.items():
        lst.sort(key=lambda s: demand.get(s, 0.0), reverse=True)
        del lst[TOP_SLUGS_PER_REGISTRY:]

    # Build all within-registry pairs, rank by combined demand.
    all_pairs: list[tuple[float, str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for source, lst in by_registry.items():
        for a, b in combinations(lst, 2):
            x, y = sorted([a, b])
            key = (source, x, y)
            if key in seen:
                continue
            seen.add(key)
            combined = demand.get(x, 0.0) + demand.get(y, 0.0)
            all_pairs.append((combined, source, x, y))
    all_pairs.sort(key=lambda t: (-t[0], t[1], t[2], t[3]))
    top_pairs = all_pairs[:MAX_PAIRS]

    rows: list[tuple[str, str, str, str, str]] = []
    counts = {"200": 0, "404": 0, "other": 0}
    for _, registry, a, b in top_pairs:
        url = f"https://nerq.ai/compare/{a}-vs-{b}"
        status = curl_status(url)
        if status == "200":
            counts["200"] += 1
        elif status == "404":
            counts["404"] += 1
        else:
            counts["other"] += 1
        rows.append((registry, a, b, status, recommend(status)))

    lines = [
        "# FB-F3-20260418-013 /compare/ coverage proposals (top 50 pairs)",
        "",
        "Pairs drawn from the highest-demand slugs within each registry "
        "(smedjan.ai_demand_scores joined to Nerq entity_lookup.source), "
        "cross-paired within the same registry, ranked by combined demand "
        "score, and capped at 50.",
        "",
        "| registry | slug_a | slug_b | http_status | recommendation |",
        "|----------|--------|--------|-------------|----------------|",
    ]
    for registry, a, b, status, rec in rows:
        lines.append(f"| {registry} | {a} | {b} | {status} | {rec} |")
    lines.extend(
        [
            "",
            f"**counts_by_status:** `{json.dumps(counts)}`",
            "",
            "## Observation",
            "",
            "Prior F3 audits noted that `/compare/` returns `200` even for "
            "unknown slugs (catch-all routing), so a bare `200` is not a "
            "reliable coverage signal. Rows recommended `skip` here should be "
            "re-validated against page body for empty-comparison / "
            "entity-not-found states before acting on them.",
            "",
        ]
    )
    OUT.write_text("\n".join(lines))
    print(
        json.dumps(
            {
                "rows": len(rows),
                "counts_by_status": counts,
                "output": str(OUT),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
