"""FU-CITATION-20260418-10 — redirect-plan for top 30 301 + top 30 410 paths
on visitor_type='ai_mediated' (30d).

Parent audit: AUDIT-CITATION-20260418, Finding 10 (medium).

Pulls the top-30 paths in each of status∈{301,410} for ai_mediated visits over
the last 30 days, joins to Nerq RO `entity_lookup` so /agent/{uuid} resolves
to its current slug, and emits a redirect proposal per row.

The current /agent/{path:path} handler in agentindex/api/discovery.py dumbly
copies the last path segment into /safe/{segment} — for UUID paths this yields
/safe/<uuid>, a non-resolving URL. The proposal is to redirect each stale
UUID to /safe/{current_slug} (the resolved slug from entity_lookup) and to
upgrade the 410 rows to the same 301 target when the underlying entity is
still active.

No code is changed; the deliverable is a CSV at
~/smedjan/audit-reports/2026-04-18-citation-redirect-plan.csv.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import defaultdict

from smedjan import sources

OUT_PATH = os.path.expanduser(
    "~/smedjan/audit-reports/2026-04-18-citation-redirect-plan.csv"
)

UUID_PATH_RE = re.compile(r"^/agent/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")

# crawl_status values that indicate the entity is properly resolvable
LIVE_CRAWL_STATES = {"indexed", "ranked", "parsed", "classified"}


def main() -> int:
    with sources.analytics_mirror_cursor() as (_, cur):
        cur.execute(
            """
            WITH ranked AS (
                SELECT path, status, count(*) AS hits,
                       row_number() OVER (PARTITION BY status ORDER BY count(*) DESC) AS rn
                FROM analytics_mirror.requests
                WHERE ts >= now() - interval '30 days'
                  AND visitor_type = 'ai_mediated'
                  AND status IN (301, 410)
                GROUP BY path, status
            )
            SELECT path, status, hits FROM ranked
            WHERE rn <= 30
            ORDER BY status ASC, hits DESC
            """
        )
        top = cur.fetchall()
        paths = [r[0] for r in top]

        cur.execute(
            """
            SELECT path, coalesce(nullif(ai_source, ''), '(none)') AS src, count(*)
            FROM analytics_mirror.requests
            WHERE ts >= now() - interval '30 days'
              AND visitor_type = 'ai_mediated'
              AND path = ANY(%s)
            GROUP BY 1, 2
            """,
            (paths,),
        )
        src_rows = cur.fetchall()

    src_by_path: dict[str, dict[str, int]] = defaultdict(dict)
    for p, s, c in src_rows:
        src_by_path[p][s] = int(c)

    uuids = []
    for p, _s, _h in top:
        m = UUID_PATH_RE.match(p)
        if m:
            uuids.append(m.group(1))

    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            """
            SELECT id::text, slug, name, source, is_active, crawl_status, trust_grade
            FROM entity_lookup
            WHERE id::text = ANY(%s)
            """,
            (uuids,),
        )
        rows = cur.fetchall()
    lookup = {r[0]: r for r in rows}

    def dominant_llm(path: str) -> str:
        srcs = src_by_path.get(path, {})
        if not srcs:
            return "(unattributed)"
        total = sum(srcs.values())
        dom_key, dom_n = max(srcs.items(), key=lambda kv: kv[1])
        share = dom_n / total if total else 0.0
        if dom_key == "(none)":
            return f"unattributed ({dom_n}/{total})"
        return f"{dom_key} ({dom_n}/{total}, {share:.0%})"

    def propose(path: str, status: int) -> tuple[str, str]:
        m = UUID_PATH_RE.match(path)
        if not m:
            return ("/", "non-/agent path; keep current behavior, hand-review")
        uuid = m.group(1)
        entry = lookup.get(uuid)
        if entry is None:
            return (
                "410 (keep)",
                "UUID not found in entity_lookup; tombstone appropriate — "
                "LLM has a cached UUID for a long-deleted entity",
            )
        _id, slug, _name, source, is_active, crawl_status, trust_grade = entry
        live = bool(is_active) and (crawl_status in LIVE_CRAWL_STATES)
        tg = trust_grade or "?"
        safe_target = f"/safe/{slug}"
        if status == 301 and live:
            return (
                f"301 → {safe_target}",
                f"current handler redirects /agent/{{last_segment}} → /safe/{{last_segment}}, so /safe/{uuid} (non-resolving). "
                f"Entity still live (source={source}, crawl_status={crawl_status}, grade={tg}); "
                f"fix handler to map UUID → slug so LLM lands on the real page.",
            )
        if status == 301 and not live:
            return (
                "410 (downgrade from 301)",
                f"entity resolved (source={source}) but not live (is_active={is_active}, crawl_status={crawl_status}); "
                f"stop 301-ing to /safe/{uuid} (which also 404s); return 410 Gone to stop the LLM "
                f"re-fetching a dead record.",
            )
        if status == 410 and live:
            return (
                f"301 → {safe_target}",
                f"entity still live (source={source}, crawl_status={crawl_status}, grade={tg}); "
                f"410 discards crawl/citation equity — upgrade to 301 toward current slug.",
            )
        # status == 410 and not live
        return (
            "410 (keep)",
            f"entity resolved but not live (is_active={is_active}, crawl_status={crawl_status}); "
            f"410 is the correct signal.",
        )

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "path",
            "status",
            "hits_30d",
            "likely_source_llm",
            "proposed_target",
            "rationale",
        ])
        for path, status, hits in top:
            target, rationale = propose(path, status)
            w.writerow([path, status, hits, dominant_llm(path), target, rationale])

    # Summary for task evidence
    bucket_counts = defaultdict(int)
    target_counts = defaultdict(int)
    for path, status, _hits in top:
        bucket_counts[status] += 1
        target, _r = propose(path, status)
        # Coarse-bucket the proposal
        if target.startswith("301 "):
            target_counts[(status, "fix_to_slug_301")] += 1
        elif target.startswith("410 (downgrade"):
            target_counts[(status, "downgrade_to_410")] += 1
        elif target.startswith("410 (keep"):
            target_counts[(status, "keep_410")] += 1
        else:
            target_counts[(status, "hand_review")] += 1

    evidence = {
        "output_path": OUT_PATH,
        "rows_written": len(top),
        "bucket_counts": dict(bucket_counts),
        "proposals": {f"{s}:{k}": v for (s, k), v in target_counts.items()},
        "uuid_resolved": len(lookup),
        "uuid_in_topset": len(uuids),
    }
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
