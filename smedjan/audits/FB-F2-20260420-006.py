"""FB-F2-20260420-006: freshness-refresh prep.

Determine top-5 software_registry registries by ai_demand_scores coverage,
then emit 200 oldest enriched rows in those registries.

Join is cross-DB (software_registry on Nerq RO, ai_demand_scores on
smedjan) so it is assembled in Python.
"""
from __future__ import annotations

import csv
import json
import os
import sys

from smedjan import sources

OUT_PATH = os.path.expanduser("~/smedjan/audits/FB-F2-20260420-006.csv")


def main() -> int:
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute("SELECT slug, score FROM smedjan.ai_demand_scores")
        ads_rows = cur.fetchall()
    ads_by_slug = {slug: score for slug, score in ads_rows}
    slugs = list(ads_by_slug.keys())

    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            """
            SELECT registry, COUNT(*) AS n
            FROM software_registry
            WHERE slug = ANY(%s)
            GROUP BY registry
            ORDER BY n DESC
            LIMIT 5
            """,
            (slugs,),
        )
        top_rows = cur.fetchall()
        top5 = [r[0] for r in top_rows]
        coverage = {r[0]: int(r[1]) for r in top_rows}

        cur.execute(
            """
            SELECT slug, registry, enriched_at
            FROM software_registry
            WHERE registry = ANY(%s)
            ORDER BY registry ASC, enriched_at ASC
            LIMIT 200
            """,
            (top5,),
        )
        rows = cur.fetchall()

    with open(OUT_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["slug", "registry", "enriched_at", "ai_demand_score"])
        for slug, registry, enriched_at in rows:
            score = ads_by_slug.get(slug)
            w.writerow([
                slug,
                registry,
                enriched_at.isoformat() if enriched_at else "",
                "" if score is None else score,
            ])

    evidence = {
        "row_count": len(rows),
        "top5_registries": top5,
        "top5_coverage": coverage,
        "ai_demand_scores_slug_count": len(slugs),
        "output_path": OUT_PATH,
    }
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
