"""FU-CITATION-20260422-05: UUID-to-slug 301 inventory.

Linked to AUDIT-CITATION-20260422 / Finding 5. UUID-form paths
(/agent|safe|model/<uuid>) absorb 13.5% of ai_mediated visits but
the redirect coverage is partial — same UUID has been seen returning
200/301/410 depending on slug-handler ordering across the 30d window.

This script builds the inventory CSV the follow-up task requires:

    uuid_path, current_status, target_slug, ai_mediated_30d

…plus a few helper columns (agent_type, entity name, is_active,
proposed_target_url) so the downstream redirect plan is unambiguous.

Sources
-------
- analytics_mirror.requests (smedjan DB, mirror of Nerq prod)
    * 30d ai_mediated counts per path
    * 30d most-recent observed `status` per path = "current_status"
- public.entity_lookup (Nerq RO replica)
    * UUID → (slug, name, agent_type, is_active, trust_score_v2)

Output
------
- smedjan/audit-reports/2026-04-22-FU-CITATION-05-uuid-redirect-inventory.csv

This script does NOT modify Nerq production. The redirect plan that
consumes the CSV is committed alongside the CSV; deployment is
out-of-scope for this task.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import defaultdict

from smedjan import sources

OUT_DIR = os.path.expanduser("~/smedjan/audit-reports")
OUT_PATH = os.path.join(
    OUT_DIR, "2026-04-22-FU-CITATION-05-uuid-redirect-inventory.csv"
)
EVIDENCE_PATH = os.path.join(
    OUT_DIR, "2026-04-22-FU-CITATION-05-uuid-redirect-evidence.json"
)

UUID_RE = re.compile(
    r"^/(agent|safe|model)/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:[/?].*)?$"
)


def fetch_path_inventory():
    """Per UUID-form path: (visits_30d, current_status).

    "current_status" is the status of the most-recent request observed
    for that path within the 30d window. Using most-recent (rather than
    mode) is correct here because the route-registration order changed
    inside the window — older samples are stale, the most recent one
    reflects the route handler currently in production.
    """
    sql = """
    WITH base AS (
        SELECT path, status, ts
          FROM analytics_mirror.requests
         WHERE ts >= now() - interval '30 days'
           AND path ~ '^/(agent|safe|model)/[a-f0-9]{8}-[a-f0-9]{4}-'
    ),
    visits AS (
        SELECT path,
               count(*) FILTER (WHERE visitor_type='ai_mediated') AS ai_mediated_30d,
               count(*)                                            AS total_30d
          FROM analytics_mirror.requests
         WHERE ts >= now() - interval '30 days'
           AND path ~ '^/(agent|safe|model)/[a-f0-9]{8}-[a-f0-9]{4}-'
         GROUP BY path
    ),
    last_status AS (
        SELECT DISTINCT ON (path) path, status
          FROM base
         ORDER BY path, ts DESC
    )
    SELECT v.path,
           ls.status AS current_status,
           v.ai_mediated_30d,
           v.total_30d
      FROM visits v
      JOIN last_status ls USING (path)
     WHERE v.ai_mediated_30d > 0
     ORDER BY v.ai_mediated_30d DESC, v.path;
    """
    with sources.analytics_mirror_cursor() as (_, cur):
        cur.execute(sql)
        return cur.fetchall()


def fetch_uuid_to_entity(uuids):
    """Map list of UUIDs → entity_lookup row (slug, agent_type, name, is_active, trust)."""
    sql = """
    SELECT id::text AS uuid,
           slug,
           name,
           agent_type,
           is_active,
           trust_score_v2,
           trust_grade
      FROM public.entity_lookup
     WHERE id = ANY(%s::uuid[])
    """
    out = {}
    if not uuids:
        return out
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(sql, (list(uuids),))
        for row in cur.fetchall():
            uuid, slug, name, agent_type, is_active, ts, tg = row
            out[uuid] = {
                "slug": slug,
                "name": name,
                "agent_type": agent_type,
                "is_active": is_active,
                "trust_score_v2": float(ts) if ts is not None else None,
                "trust_grade": tg,
            }
    return out


def proposed_target_for(prefix: str, agent_type: str | None, slug: str | None) -> str:
    """Decide the canonical URL for a resolved entity.

    Routing convention (verified against discovery.py & seo_dynamic.py
    on 2026-04-22):
      - All entities have a /safe/<slug> page (renders trust report).
      - Models additionally live at /model/<slug>.
      - /agent/<*> currently 301-redirects to /safe/<*>.

    For citation-rot recovery we standardise on /safe/<slug> as the
    redirect target regardless of original prefix — that page exists
    for every classified entity and consolidates link equity. /model/
    parallel exists but is the ML-discovery surface, not the trust
    surface; LLM citations want the trust page.
    """
    if not slug:
        return ""
    return f"/safe/{slug}"


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    rows = fetch_path_inventory()
    print(f"[1/3] inventory rows: {len(rows)}")

    # Extract UUID per row, dedupe, look up in Nerq RO.
    uuids = set()
    parsed = []
    for path, status, ai_mediated, total in rows:
        m = UUID_RE.match(path)
        if not m:
            continue
        prefix, uuid = m.group(1), m.group(2)
        parsed.append((path, prefix, uuid, status, ai_mediated, total))
        uuids.add(uuid)

    print(f"[2/3] unique UUIDs to resolve: {len(uuids)}")
    entity_by_uuid = fetch_uuid_to_entity(uuids)
    print(f"      resolved in entity_lookup: {len(entity_by_uuid)}")

    # Aggregates for evidence block
    status_hist = defaultdict(int)
    coverage = {"resolved": 0, "unresolved": 0, "inactive": 0}
    visits_with_target = 0
    visits_total = 0

    with open(OUT_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "uuid_path",
            "current_status",
            "target_slug",
            "ai_mediated_30d",
            "total_30d",
            "agent_type",
            "entity_name",
            "is_active",
            "trust_score_v2",
            "proposed_target_url",
            "resolution",
        ])
        for path, prefix, uuid, status, ai_med, total in parsed:
            ent = entity_by_uuid.get(uuid)
            slug = ent["slug"] if ent else ""
            agent_type = ent["agent_type"] if ent else ""
            name = ent["name"] if ent else ""
            is_active = ent["is_active"] if ent else ""
            trust = ent["trust_score_v2"] if ent else ""
            target_url = proposed_target_for(prefix, agent_type, slug) if ent else ""

            if not ent:
                resolution = "unresolved_uuid"
                coverage["unresolved"] += 1
            elif not ent.get("is_active"):
                resolution = "resolved_inactive"
                coverage["inactive"] += 1
                coverage["resolved"] += 1
            else:
                resolution = "resolved_active"
                coverage["resolved"] += 1

            if target_url:
                visits_with_target += ai_med
            visits_total += ai_med

            status_hist[status] += 1

            w.writerow([
                path,
                status,
                slug,
                ai_med,
                total,
                agent_type,
                name,
                is_active,
                "" if trust is None else trust,
                target_url,
                resolution,
            ])

    evidence = {
        "task": "FU-CITATION-20260422-05",
        "csv_path": OUT_PATH,
        "rows": len(parsed),
        "unique_uuids": len(uuids),
        "resolved_entities": len(entity_by_uuid),
        "coverage_breakdown": coverage,
        "current_status_histogram": {str(k): v for k, v in sorted(status_hist.items())},
        "ai_mediated_total_30d": visits_total,
        "ai_mediated_with_proposed_target": visits_with_target,
        "target_coverage_pct": round(
            100.0 * visits_with_target / visits_total, 2
        ) if visits_total else 0.0,
    }
    with open(EVIDENCE_PATH, "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
