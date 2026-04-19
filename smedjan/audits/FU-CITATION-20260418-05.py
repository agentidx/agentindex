"""FU-CITATION-20260418-05 — Top-500 AI-bot 4xx/5xx triage CSV.

Parent audit: AUDIT-CITATION-20260418, Finding 5 (medium).
8.8% of AI-bot crawls hit 4xx/5xx (465,042/month). This task enumerates
the top-500 AI-bot 4xx/5xx paths (30d window) and classifies each as
one of:

    ship-real                    — build the page/endpoint; the LLM is
                                   asking for something we should answer.
    ship-deterministic-200-stub  — return a deterministic 200 JSON/HTML
                                   body so the LLM learns the shape.
    301-to-hub                   — redirect to an existing hub/slug that
                                   carries the citation equity.
    accept-as-404                — correct signal; no action (e.g. random
                                   crawler probes, adversarial paths).
    accept-as-410                — resource intentionally gone; keep it.
    investigate-5xx              — server error needing code-side triage.

Classification is rule-based with entity_lookup confirmation for
/safe/, /token/, /model/, /agent/ UUID paths (live → 301 to resolved
slug; dead → accept-as-404/410).

Deliverable is a CSV at
~/smedjan/audit-reports/2026-04-18-citation-4xx-triage.csv with columns
(path, status, hits_30d, decision, rationale). Coverage = top 500.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter

from smedjan import sources

OUT_PATH = os.path.expanduser(
    "~/smedjan/audit-reports/2026-04-18-citation-4xx-triage.csv"
)
TOP_N = 500

UUID_RE = re.compile(r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
LIVE_CRAWL_STATES = {"indexed", "ranked", "parsed", "classified"}

# Routes that have been shipped as of 2026-04-18 (commit 693e156):
#   /homebrew hub, /scan → /risk-scanner, /v1/crypto/<slug>/test
# So historical 404s in the 30d window are already resolved for these.
SHIPPED_AFTER_WINDOW = {
    "/homebrew": "/homebrew hub shipped 2026-04-18 (commit 693e156); historical 404s stop at ship date.",
    "/scan": "/scan → /risk-scanner redirect shipped 2026-04-18 (commit 693e156).",
}


def _last_segment(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


def _entity_ids_from(paths: list[str]) -> tuple[list[str], list[str]]:
    """Return (slugs_or_uuids_to_look_up, matching_paths) for entity-prefix paths."""
    needles: list[str] = []
    for p in paths:
        # /agent/<uuid>
        if p.startswith("/agent/"):
            seg = _last_segment(p)
            if UUID_RE.match(seg):
                needles.append(seg)
                continue
        # /safe/<slug>, /token/<slug>, /model/<slug>
        for prefix in ("/safe/", "/token/", "/model/"):
            if p.startswith(prefix):
                # Only the direct /prefix/<slug> (not sub-pages like /safe/<slug>/privacy)
                rest = p[len(prefix):]
                if rest and "/" not in rest:
                    needles.append(rest)
                break
    # Dedup while preserving order
    seen = set()
    out = []
    for n in needles:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out, paths


def classify(
    path: str,
    status: int,
    entity_by_id: dict[str, tuple],
    entity_by_slug: dict[str, tuple],
) -> tuple[str, str]:
    """Return (decision, rationale) for a single (path, status)."""
    if path in SHIPPED_AFTER_WINDOW:
        return ("ship-real", SHIPPED_AFTER_WINDOW[path])

    # 5xx — always investigate, not triage
    if status >= 500:
        return (
            "investigate-5xx",
            f"{status} indicates a server error, not a shape mismatch; "
            "route exists but is failing — needs code-side root-cause.",
        )

    # 422 on /v1/preflight — request shape validation is working as intended
    if status == 422 and path.startswith("/v1/preflight"):
        return (
            "accept-as-404",
            "422 on /v1/preflight is a malformed payload response, not a missing resource; "
            "schema validation is behaving correctly — no action.",
        )

    # /agent/<uuid> — already covered by FU-CITATION-20260418-10 redirect plan
    if path.startswith("/agent/"):
        seg = _last_segment(path)
        if UUID_RE.match(seg):
            entry = entity_by_id.get(seg)
            if entry is None:
                return (
                    "accept-as-410",
                    "UUID not found in entity_lookup; long-deleted entity — 410 is the correct tombstone.",
                )
            _id, slug, _name, source, is_active, crawl_status, trust_grade = entry
            live = bool(is_active) and (crawl_status in LIVE_CRAWL_STATES)
            if live:
                return (
                    "301-to-hub",
                    f"301 → /safe/{slug} (entity live, source={source}, grade={trust_grade or '?'}); "
                    "fix handler to map UUID → current slug (see FU-CITATION-20260418-10).",
                )
            return (
                "accept-as-410",
                f"entity resolved but not live (is_active={is_active}, crawl_status={crawl_status}); "
                "410 is the correct signal.",
            )
        # /agent/<slug> non-UUID (rare)
        return (
            "301-to-hub",
            "legacy /agent/<slug> path; handler copies last segment to /safe/<segment> — "
            "confirm the resulting /safe/<slug> resolves and redirect directly.",
        )

    # /v1/crypto/compare/<A>/<B> — the strategic one
    if path.startswith("/v1/crypto/compare/"):
        return (
            "ship-deterministic-200-stub",
            "LLM-shaped pair-comparison probe; return deterministic 200 JSON "
            "with methodology even for unknown pairs so bots learn endpoint "
            "shape (Finding 5/7 recommendation).",
        )

    # /v1/crypto/ndd/<slug> or other /v1/crypto/*
    if path.startswith("/v1/crypto/"):
        return (
            "ship-deterministic-200-stub",
            "Under-covered rating endpoint; return deterministic 200 JSON stub "
            "with a Trust Verdict scaffold so endpoint shape is learnable.",
        )

    # /v1/preflight (non-422 — 404 is odd but possible on variant spellings)
    if path.startswith("/v1/preflight"):
        return (
            "ship-real",
            "preflight is the 85% of API-family AI traffic (Finding 7); any 4xx here is a "
            "route-matching bug — normalize and return a valid preflight response.",
        )

    # /best/<slug> — /best/ family (F5 recommendation: aggregator or 301 to hub)
    if path.startswith("/best/"):
        slug = path[len("/best/"):]
        if not slug or slug in {"other", "research", "translation", "health"}:
            # Generic buckets — 301 to search or /compare index
            return (
                "301-to-hub",
                f"/best/{slug} is a generic bucket label with no entity inventory; "
                "301 → /search?q=best+<slug> or the closest /mcp/ hub; do not build a dedicated page.",
            )
        return (
            "ship-real",
            "/best/<topic> is an intent-shaped query LLMs are training to produce; "
            "ship an aggregator page per Intervention 5 or 301 to closest /mcp/ hub.",
        )

    # /compare/<a>-vs-<b> — pairwise comparison
    if path.startswith("/compare/"):
        # Most are long-tail one-sided pairs we will never have both sides of
        return (
            "301-to-hub",
            "Long-tail /compare/<a>-vs-<b> 404s are one-sided-pair probes; "
            "redirect to /compare index (or /safe/<a> when the lhs resolves) rather than leave 404.",
        )

    # /alternatives(/...)? — user-intent alternatives query
    if path == "/alternatives" or path.startswith("/alternatives/"):
        return (
            "301-to-hub",
            "/alternatives is intent-shaped; 301 → /compare or /mcp index. If traffic sustains, "
            "ship a dedicated alternatives-hub with top-100 per category.",
        )

    # /token/<slug> — crypto token slug
    if path.startswith("/token/"):
        rest = path[len("/token/"):]
        if rest and "/" not in rest:
            # Slug lookup
            ent = entity_by_slug.get(rest)
            if ent:
                _id, slug, _name, source, is_active, crawl_status, trust_grade = ent
                if bool(is_active) and (crawl_status in LIVE_CRAWL_STATES):
                    return (
                        "ship-real",
                        f"entity_lookup has {rest} live (source={source}, grade={trust_grade or '?'}); "
                        "route should resolve — template/handler bug, not a missing resource.",
                    )
            return (
                "accept-as-404",
                "token slug not in entity_lookup; LLM hallucinated the coin or we never indexed it — 404 is correct.",
            )
        return (
            "accept-as-404",
            "malformed /token/ path (sub-segments or empty slug); 404 is correct.",
        )

    # /model/<slug>
    if path.startswith("/model/"):
        rest = path[len("/model/"):]
        if rest and "/" not in rest:
            ent = entity_by_slug.get(rest)
            if ent:
                _id, slug, _name, source, is_active, crawl_status, trust_grade = ent
                if bool(is_active) and (crawl_status in LIVE_CRAWL_STATES):
                    return (
                        "ship-real",
                        f"entity_lookup has {rest} live (source={source}, grade={trust_grade or '?'}); "
                        "model route should resolve — template/handler bug.",
                    )
            return (
                "accept-as-404",
                "model slug not in entity_lookup; hallucinated or never indexed — 404 is correct.",
            )
        return ("accept-as-404", "malformed /model/ path; 404 is correct.")

    # /safe/<slug> — the primary entity template
    if path.startswith("/safe/"):
        rest = path[len("/safe/"):]
        if rest and "/" not in rest:
            ent = entity_by_slug.get(rest)
            if ent:
                _id, slug, _name, source, is_active, crawl_status, trust_grade = ent
                if bool(is_active) and (crawl_status in LIVE_CRAWL_STATES):
                    return (
                        "ship-real",
                        f"entity_lookup has {rest} live (source={source}, grade={trust_grade or '?'}); "
                        "/safe/ 404 is a renderer/template regression — code-side fix.",
                    )
                return (
                    "accept-as-410",
                    f"entity resolved but not live (is_active={bool(is_active)}, crawl_status={crawl_status}); "
                    "404 → upgrade to 410 to stop re-fetches.",
                )
            return (
                "accept-as-404",
                "slug not in entity_lookup; 404 is correct.",
            )
        return (
            "accept-as-404",
            "unrecognised /safe/ sub-path shape; 404 is correct.",
        )

    # /compliance/<topic>
    if path.startswith("/compliance/"):
        return (
            "ship-real",
            "regulatory/compliance queries (e.g. /compliance/mica) are high-value LLM intent; "
            "ship a short canonical page or 301 to the ZARQ compliance explainer.",
        )

    # /review/<slug>
    if path.startswith("/review/"):
        return (
            "301-to-hub",
            "/review/<slug> probes; redirect to /safe/<slug> when the entity resolves, "
            "else 301 to /compare or category hub.",
        )

    # /vpn, /container, /improve — category-intent slugs
    if path in {"/vpn", "/container", "/improve"}:
        return (
            "301-to-hub",
            "single-word category intent; 301 → /mcp/ or /best/<topic> hub.",
        )

    # Anything starting with /is-..-safe (trust-verdict probe shape)
    if path.startswith("/is-") and path.endswith("-safe"):
        return (
            "ship-deterministic-200-stub",
            "LLM is constructing 'is-X-safe' URL shape — exactly the trust-verdict intent we want. "
            "Ship deterministic 200 stub resolving to nearest /safe/<slug> or a 'we don't rate X' verdict.",
        )

    # Known bot probe noise (vendor scanners)
    if re.search(r"(\.php|\.asp|wp-admin|wp-login|\.env|\.git)", path, re.I):
        return (
            "accept-as-404",
            "adversarial/legacy scanner probe; 404 is the correct signal.",
        )

    # Empty / root-ish
    if path in {"", "/"}:
        return (
            "investigate-5xx",
            "root returning 4xx is anomalous — investigate referrer.",
        )

    return (
        "accept-as-404",
        "unclassified long-tail path; 404 is correct absent a clear citation-equity case.",
    )


def main() -> int:
    # 1. Pull top-500 (path,status) pairs.
    with sources.analytics_mirror_cursor() as (_, cur):
        cur.execute(
            """
            WITH ranked AS (
                SELECT path, status, count(*) AS hits,
                       row_number() OVER (ORDER BY count(*) DESC, path ASC) AS rn
                  FROM analytics_mirror.requests
                 WHERE ts >= now() - interval '30 days'
                   AND is_ai_bot = 1
                   AND status >= 400
                 GROUP BY path, status
            )
            SELECT path, status, hits FROM ranked
            WHERE rn <= %s
            ORDER BY hits DESC, path ASC
            """,
            (TOP_N,),
        )
        rows = cur.fetchall()
    top = [(p, int(s), int(h)) for (p, s, h) in rows]

    # 2. Collect entity IDs / slugs that need entity_lookup resolution.
    slugs_to_check: list[str] = []
    uuids_to_check: list[str] = []
    for p, _s, _h in top:
        if p.startswith("/agent/"):
            seg = _last_segment(p)
            if UUID_RE.match(seg):
                uuids_to_check.append(seg)
        for prefix in ("/safe/", "/token/", "/model/"):
            if p.startswith(prefix):
                rest = p[len(prefix):]
                if rest and "/" not in rest:
                    slugs_to_check.append(rest)
                break
    uuids_to_check = list(dict.fromkeys(uuids_to_check))
    slugs_to_check = list(dict.fromkeys(slugs_to_check))

    entity_by_id: dict[str, tuple] = {}
    entity_by_slug: dict[str, tuple] = {}
    with sources.nerq_readonly_cursor() as (_, cur):
        if uuids_to_check:
            cur.execute(
                """
                SELECT id::text, slug, name, source, is_active, crawl_status, trust_grade
                  FROM entity_lookup
                 WHERE id::text = ANY(%s)
                """,
                (uuids_to_check,),
            )
            for row in cur.fetchall():
                entity_by_id[row[0]] = row
        if slugs_to_check:
            cur.execute(
                """
                SELECT id::text, slug, name, source, is_active, crawl_status, trust_grade
                  FROM entity_lookup
                 WHERE slug = ANY(%s)
                """,
                (slugs_to_check,),
            )
            for row in cur.fetchall():
                entity_by_slug[row[1]] = row

    # 3. Classify + write CSV.
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    decision_counts: Counter[str] = Counter()
    hits_by_decision: Counter[str] = Counter()
    with open(OUT_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "status", "hits_30d", "decision", "rationale"])
        for path, status, hits in top:
            decision, rationale = classify(path, status, entity_by_id, entity_by_slug)
            decision_counts[decision] += 1
            hits_by_decision[decision] += hits
            w.writerow([path, status, hits, decision, rationale])

    evidence = {
        "output_path": OUT_PATH,
        "rows_written": len(top),
        "top_hits": top[0][2] if top else 0,
        "cutoff_hits": top[-1][2] if top else 0,
        "uuids_resolved": f"{len(entity_by_id)}/{len(uuids_to_check)}",
        "slugs_resolved": f"{len(entity_by_slug)}/{len(slugs_to_check)}",
        "decision_path_counts": dict(decision_counts),
        "decision_hit_counts": dict(hits_by_decision),
    }
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
