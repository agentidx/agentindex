#!/usr/bin/env python3
"""
FB-F2-20260530-018 — freshness-refresh prep (read-only).

ai_demand_scores lives on the smedjan factory DB; software_registry lives
on the Nerq RO replica. They join on `slug`, so the join is assembled in
Python rather than in a single SQL statement.

  1. top-5 registries by ai_demand_score coverage
     (count software_registry rows whose slug is present in
      ai_demand_scores, grouped by registry, take the 5 largest)
  2. the 200 oldest enriched rows across those registries,
     ordered (registry ASC, enriched_at ASC).

No enricher call — a later non-fallback task consumes the CSV.

Output: ~/smedjan/audits/FB-F2-20260530-018.csv
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/agentindex"))

from smedjan import sources

OUT = os.path.expanduser("~/smedjan/audits/FB-F2-20260530-018.csv")
OUT_HEADER = ["slug", "registry", "enriched_at", "ai_demand_score"]


def main():
    # ai_demand_scores (smedjan factory DB): slug -> score
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute("SELECT slug, score FROM smedjan.ai_demand_scores")
        score_by_slug = {slug: score for slug, score in cur.fetchall()}
    slugs = list(score_by_slug.keys())

    with sources.nerq_readonly_cursor() as (_, cur):
        # top-5 registries by ai_demand_score coverage
        cur.execute(
            """
            SELECT registry, COUNT(*) AS n
            FROM software_registry
            WHERE slug = ANY(%s) AND registry IS NOT NULL
            GROUP BY registry
            ORDER BY n DESC, registry ASC
            LIMIT 5
            """,
            (slugs,),
        )
        top5_rows = cur.fetchall()
        top5 = [r[0] for r in top5_rows]

        # 200 oldest enriched rows across those registries
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

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(OUT_HEADER)
        for slug, registry, enriched_at in rows:
            score = score_by_slug.get(slug)
            w.writerow([
                slug,
                registry,
                enriched_at.isoformat() if enriched_at else "",
                "" if score is None else score,
            ])

    evidence = {
        "row_count": len(rows),
        "top5_registries": [{"registry": r[0], "count": int(r[1])} for r in top5_rows],
        "ai_demand_scores_slug_count": len(slugs),
        "output_path": OUT,
    }
    with open("/tmp/ev018.json", "w") as f:
        json.dump(evidence, f, indent=2)
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
