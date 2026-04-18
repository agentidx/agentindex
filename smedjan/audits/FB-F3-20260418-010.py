"""Generate /compare/ coverage proposals for FB-F3-20260418-010.

Same shape as FB-F3-20260418-018: pulls highest-demand slugs from
smedjan.ai_demand_scores, maps each slug to the Nerq registries
(entity_lookup.source) that carry it, cross-pairs the top slugs
within each registry, ranks pairs by combined demand, collapses
duplicate slug-pairs across registries by retaining the registry
with the highest combined score, then curls
https://nerq.ai/compare/<a>-vs-<b> for the top 50.

Output: /Users/anstudio/smedjan/audits/FB-F3-20260418-010.md
"""
from __future__ import annotations

import json
import subprocess
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, "/Users/anstudio/agentindex")

from smedjan import sources  # noqa: E402

OUT = Path("/Users/anstudio/smedjan/audits/FB-F3-20260418-010.md")
TOP_SLUGS_FETCH = 2000
TOP_SLUGS_PER_REGISTRY = 25
MAX_PAIRS = 50
EXCLUDE_SLUGS = {"test"}  # scraping artefact flagged in prior F3 audits
USER_AGENT = "smedjan-audit/1.0 (+FB-F3-20260418-010)"


def fetch_demand_scores(limit: int) -> dict[str, float]:
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(
            "SELECT slug, score FROM smedjan.ai_demand_scores "
            "WHERE slug IS NOT NULL AND slug <> '' AND score IS NOT NULL "
            "AND slug <> ALL(%s) "
            "ORDER BY score DESC LIMIT %s",
            (list(EXCLUDE_SLUGS), limit),
        )
        return {slug: float(score) for slug, score in cur.fetchall()}


def fetch_slug_registries(slugs: list[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT DISTINCT slug, source FROM entity_lookup "
            "WHERE slug = ANY(%s) AND source IS NOT NULL",
            (slugs,),
        )
        for slug, source in cur.fetchall():
            out.setdefault(slug, set()).add(source)
    return out


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
                "20",
                "-A",
                USER_AGENT,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=25,
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
    reg_map = fetch_slug_registries(list(demand.keys()))

    by_registry: dict[str, list[tuple[str, float]]] = {}
    for slug, registries in reg_map.items():
        for r in registries:
            by_registry.setdefault(r, []).append((slug, demand[slug]))
    for r in by_registry:
        by_registry[r].sort(key=lambda x: x[1], reverse=True)
        del by_registry[r][TOP_SLUGS_PER_REGISTRY:]

    best: dict[tuple[str, str], tuple[float, str]] = {}
    for r, lst in by_registry.items():
        for (a, sa), (b, sb) in combinations(lst, 2):
            x, y = sorted([a, b])
            combined = sa + sb
            prev = best.get((x, y))
            if prev is None or combined > prev[0]:
                best[(x, y)] = (combined, r)

    ranked = sorted(
        ((combined, registry, a, b) for (a, b), (combined, registry) in best.items()),
        key=lambda t: (-t[0], t[1], t[2], t[3]),
    )
    top_pairs = ranked[:MAX_PAIRS]

    rows: list[tuple[str, str, str, str, str]] = []
    counts = {"200": 0, "404": 0, "other": 0}
    for _, registry, a, b in top_pairs:
        status = curl_status(f"https://nerq.ai/compare/{a}-vs-{b}")
        if status == "200":
            counts["200"] += 1
        elif status == "404":
            counts["404"] += 1
        else:
            counts["other"] += 1
        rows.append((registry, a, b, status, recommend(status)))

    lines = [
        "# FB-F3-20260418-010 /compare/ coverage proposals (top 50 pairs)",
        "",
        "Pairs drawn from the highest-demand slugs within each registry "
        "(smedjan.ai_demand_scores joined to Nerq entity_lookup.source). "
        f"Top {TOP_SLUGS_PER_REGISTRY} slugs per registry are cross-paired, "
        "every intra-registry pair is scored by combined demand, duplicates "
        "across registries are collapsed to the highest-combined-score "
        "registry, then the top 50 pairs overall are retained. Slug `test` "
        "is excluded (known scraping artefact).",
        "",
        "For each pair the audit runs `curl https://nerq.ai/compare/<a>-vs-<b>` "
        f"(User-Agent `{USER_AGENT.split()[0]}`, 20 s timeout, follow-redirects "
        "off) and records the HTTP status. Recommendation rule: `create` if "
        "404, `skip` if 200, `investigate` otherwise. No pages are created by "
        "this task — a follow-up materialises any `create` rows.",
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
            "## Notes",
            "",
            "Consistent with prior F3 audits: Nerq's `/compare/` route appears "
            "to serve a lightweight stub for pairs without a materialised "
            "analysis, so `200` alone is not conclusive evidence the page has "
            "real content. A body-inspection follow-up (e.g. detect "
            "`Not Yet Analyzed` markers) would split `skip` into `skip-real` "
            "vs `skip-stub`. Any `404` rows surface as genuine `create` "
            "candidates.",
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
