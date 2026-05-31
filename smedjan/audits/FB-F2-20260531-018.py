#!/usr/bin/env python3
"""FB-F2-20260531-018  freshness_refresh prep (read-only, no enricher).

Determine the top-5 registries by ai_demand_score coverage
(join smedjan.ai_demand_scores -> software_registry on (slug, registry),
count rows per registry, take the 5 largest), then dump the 200 oldest
enriched software_registry entries within those registries, left-joining
the ai_demand_score (blank where absent).

Output: ~/smedjan/audits/FB-F2-20260531-018.csv
Header: slug,registry,enriched_at,ai_demand_score
Sort:   registry ASC, enriched_at ASC (slug ASC as deterministic tiebreaker).
"""
import csv
import json
import os
from collections import Counter

from smedjan import sources

OUT = os.path.expanduser("~/smedjan/audits/FB-F2-20260531-018.csv")


def main():
    # 1) ai_demand_score lookup keyed by (slug, registry)
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute("SELECT slug, registry, ai_demand_score FROM smedjan.ai_demand_scores")
        ads_rows = cur.fetchall()
    score_lookup = {(s, r): v for s, r, v in ads_rows}

    # software_registry keys, to count the join coverage per registry
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute("SELECT slug, registry FROM software_registry")
        sr_keys = set((r[0], r[1]) for r in cur.fetchall())

    # 2) top-5 registries by ai_demand_score coverage (join count per registry)
    join_cnt = Counter()
    for s, r, _ in ads_rows:
        if (s, r) in sr_keys:
            join_cnt[r] += 1
    top5 = [reg for reg, _ in join_cnt.most_common(5)]

    # 3) 200 oldest enriched entries within the top-5 registries
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            """
            SELECT slug, registry, enriched_at
            FROM software_registry
            WHERE registry = ANY(%s)
            ORDER BY registry ASC, enriched_at ASC, slug ASC
            LIMIT 200
            """,
            (top5,),
        )
        rows = cur.fetchall()

    # 4) write CSV, left-joining ai_demand_score (blank where absent)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["slug", "registry", "enriched_at", "ai_demand_score"])
        for slug, registry, enriched_at in rows:
            score = score_lookup.get((slug, registry))
            ea = enriched_at.isoformat() if enriched_at is not None else ""
            w.writerow([slug, registry, ea, "" if score is None else score])

    evidence = {
        "row_count": len(rows),
        "registries_picked": top5,
        "join_count_per_registry": join_cnt.most_common(),
        "ads_total": len(ads_rows),
        "output": OUT,
    }
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
