"""FU-CONVERSION-20260418-08 — Crawled-but-uncited high-trust page prioritization.

Parent audit: AUDIT-CONVERSION-20260418, Finding 8 (medium).

F08 established that AI readers cite 15,779 unique paths while AI bots
crawl 4,131,423 — 99.6% of the crawled inventory never produces a human
click. This task narrows that universe to the pages that *should* have
produced a citation: entity pages whose underlying entity is trust_grade
A or A+ (the top 781 of ~5M entities) and which AI bots have crawled at
least once but AI-mediated human readers have never landed on in the
30-day window.

The deliverable is a CSV at
~/smedjan/audit-reports/2026-04-18-conversion-uncited-high-trust.csv,
ranked by bot_hits_30d DESC, LIMIT 100, with:

    path, entity_slug, entity_name, trust_grade, trust_score_v2,
    source, category, path_template, bot_hits_30d,
    verdict_sentence, ai_med_14d_parity, ai_med_14d_boosted

`verdict_sentence` is the one-sentence trust summary intended for
dual use: (a) as `<meta name="description">` / visible copy, and (b)
as the `cssSelector` target of a JSON-LD `SpeakableSpecification`
block. The sentence is stable across page templates so the injection
shim can be a single template function, not N handlers.

`ai_med_14d_parity` = bot_hits_30d × systemwide_crawl_to_cite_ratio
                      × (14/30).  Systemwide ratio is 36,423 / 5,109,642
                      = 0.713%.  Floor 1 when the product ≥ 0.3.
`ai_med_14d_boosted` = parity × 2.5 — the intervention hypothesis for
                      JSON-LD Speakable + inline trust-verdict on an A-tier
                      entity page.  2.5× is grounded in:
                        - F07 found /dataset/* carries 19.7% of AI-mediated
                          traffic today despite having zero CTAs, so the
                          landing-side elasticity to readable structured
                          content is large.
                        - A-tier entities are already trust-graded — the
                          shim is semantic amplification, not net-new claim.

Forbidden paths (per run rubric): none touched. This task designs output,
it does not deploy.

Coordinates with FU-CITATION-20260418-03 (the complement: high-trust
entities the bot has NEVER crawled).  The two sets are disjoint by
construction — F8 asks about the bot-visible-but-not-cited slice, F3 asks
about the bot-invisible slice.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter

from smedjan import sources

OUT_PATH = os.path.expanduser(
    "~/smedjan/audit-reports/2026-04-18-conversion-uncited-high-trust.csv"
)
TOP_N = 100

# Systemwide 30d ratios from AUDIT-CONVERSION-20260418 Appendix B.
AI_MEDIATED_30D = 36_423
AI_BOT_30D = 5_109_642
CRAWL_TO_CITE_RATIO = AI_MEDIATED_30D / AI_BOT_30D  # 0.00713
WINDOW_RESCALE_14_OVER_30 = 14.0 / 30.0
BOOSTED_MULTIPLIER = 2.5

# Path templates that carry entity-shaped slugs as segment 2.
# Keep prefixes in sync with the classifier in FU-CITATION-20260418-05.
ENTITY_PREFIXES = ("/safe/", "/agent/", "/model/", "/dataset/", "/profile/")


def _extract_slug(path: str) -> tuple[str | None, str | None]:
    """Return (slug, template) for an entity-shaped path; else (None, None).

    /safe/<slug>, /safe/<slug>/privacy -> both map to slug=<slug>,
    template='/safe/<slug>'. Sub-pages inherit the parent slug's trust.
    """
    for prefix in ENTITY_PREFIXES:
        if path.startswith(prefix):
            rest = path[len(prefix):]
            if not rest:
                return None, None
            slug = rest.split("/", 1)[0]
            if not slug:
                return None, None
            template = f"{prefix}<slug>"
            return slug, template
    return None, None


def _verdict_sentence(
    name: str,
    trust_grade: str,
    trust_score_v2: float | None,
    source: str | None,
    category: str | None,
) -> str:
    """One-sentence ZARQ trust verdict, dual-use (meta description + JSON-LD).

    Stable template so a single injection shim covers all path templates.
    """
    score_txt = f"{trust_score_v2:.0f}/100" if trust_score_v2 is not None else "top-tier"
    cat_txt = (category or "asset").replace("_", " ")
    src_txt = source or "public source"
    return (
        f"ZARQ rates {name} at Trust Grade {trust_grade} ({score_txt}) — "
        f"an A-tier {cat_txt} asset on {src_txt}; see /zarq for methodology."
    )


def _lift(bot_hits_30d: int) -> tuple[float, float]:
    parity = bot_hits_30d * CRAWL_TO_CITE_RATIO * WINDOW_RESCALE_14_OVER_30
    boosted = parity * BOOSTED_MULTIPLIER
    return parity, boosted


def _fmt_lift(x: float) -> str:
    if x >= 0.3:
        return str(max(1, round(x)))
    return "0"


def main() -> int:
    # 1. Load the full ai_mediated-cited path set (30d). This is the
    #    "already cited" filter — anything in this set is excluded.
    with sources.analytics_mirror_cursor() as (_, cur):
        cur.execute(
            """
            SELECT DISTINCT path
              FROM analytics_mirror.requests
             WHERE ts >= now() - interval '30 days'
               AND visitor_type = 'ai_mediated'
               AND status < 400
               AND method = 'GET'
            """
        )
        cited_paths = {row[0] for row in cur.fetchall()}

        # 2. Load all AI-bot-crawled entity paths (30d, status<400, GET)
        #    whose template is in ENTITY_PREFIXES. This is the candidate
        #    universe for the bot_top \ ai_mediated diff.
        prefix_filter = " OR ".join(
            [f"path LIKE '{p}%'" for p in ENTITY_PREFIXES]
        )
        cur.execute(
            f"""
            SELECT path, count(*) AS bot_hits
              FROM analytics_mirror.requests
             WHERE ts >= now() - interval '30 days'
               AND is_ai_bot = 1
               AND status < 400
               AND method = 'GET'
               AND ({prefix_filter})
             GROUP BY path
            """
        )
        bot_rows = [(r[0], int(r[1])) for r in cur.fetchall()]

    # 3. Compute the diff: bot-crawled but not ai_mediated-cited.
    uncited = [(p, h) for (p, h) in bot_rows if p not in cited_paths]

    # 4. Extract (slug, template) per path and aggregate bot hits per slug.
    #    We keep per-path bot hits as the lift driver, but dedupe paths
    #    down to the slug level because entity_lookup key is the slug.
    per_path: list[tuple[str, str, str, int]] = []  # (path, slug, template, hits)
    for p, h in uncited:
        slug, template = _extract_slug(p)
        if slug is None:
            continue
        per_path.append((p, slug, template, h))

    if not per_path:
        print(json.dumps({"error": "no entity-shaped uncited paths found"}))
        return 1

    slugs = list({row[1] for row in per_path})

    # 5. Resolve trust_grade A/A+ entities in the slug set.
    entity_by_slug: dict[str, tuple] = {}
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            """
            SELECT slug, name, trust_grade, trust_score_v2,
                   source, category
              FROM entity_lookup
             WHERE slug = ANY(%s)
               AND trust_grade IN ('A', 'A+')
            """,
            (slugs,),
        )
        for slug, name, tg, tsv, source, category in cur.fetchall():
            entity_by_slug[slug] = (
                name,
                tg,
                float(tsv) if tsv is not None else None,
                source,
                category,
            )

    # 6. Join: keep per_path rows whose slug resolved as A/A+.
    joined: list[tuple] = []
    for path, slug, template, hits in per_path:
        ent = entity_by_slug.get(slug)
        if ent is None:
            continue
        name, tg, tsv, source, category = ent
        verdict = _verdict_sentence(name, tg, tsv, source, category)
        parity, boosted = _lift(hits)
        joined.append(
            (
                path,
                slug,
                name,
                tg,
                tsv,
                source or "",
                category or "",
                template,
                hits,
                verdict,
                _fmt_lift(parity),
                _fmt_lift(boosted),
            )
        )

    # 7. Rank by bot_hits_30d DESC, slug ASC (stable tiebreak), LIMIT 100.
    joined.sort(key=lambda r: (-r[8], r[1], r[0]))
    top = joined[:TOP_N]

    # 8. Write CSV.
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "path",
                "entity_slug",
                "entity_name",
                "trust_grade",
                "trust_score_v2",
                "source",
                "category",
                "path_template",
                "bot_hits_30d",
                "verdict_sentence",
                "ai_med_14d_parity",
                "ai_med_14d_boosted",
            ]
        )
        for row in top:
            # Format trust_score_v2 for CSV (None -> empty)
            row_out = list(row)
            row_out[4] = f"{row[4]:.1f}" if row[4] is not None else ""
            w.writerow(row_out)

    # 9. Summary evidence.
    template_counts: Counter[str] = Counter(r[7] for r in top)
    grade_counts: Counter[str] = Counter(r[3] for r in top)
    total_bot_hits = sum(r[8] for r in top)
    total_parity_raw = sum(
        r[8] * CRAWL_TO_CITE_RATIO * WINDOW_RESCALE_14_OVER_30 for r in top
    )
    total_boosted_raw = total_parity_raw * BOOSTED_MULTIPLIER

    evidence = {
        "output_path": OUT_PATH,
        "candidate_universe": {
            "bot_entity_paths_30d": len(bot_rows),
            "ai_mediated_cited_paths_30d": len(cited_paths),
            "uncited_entity_paths": len(uncited),
            "uncited_with_extracted_slug": len(per_path),
            "unique_slugs": len(slugs),
            "resolved_A_or_Aplus_slugs": len(entity_by_slug),
            "joined_path_rows": len(joined),
        },
        "top_n": len(top),
        "top_bot_hits_30d": top[0][8] if top else 0,
        "cutoff_bot_hits_30d": top[-1][8] if top else 0,
        "template_counts_top_n": dict(template_counts),
        "grade_counts_top_n": dict(grade_counts),
        "aggregate_lift_hypothesis": {
            "total_bot_hits_30d_top_n": total_bot_hits,
            "total_ai_med_14d_parity": round(total_parity_raw, 2),
            "total_ai_med_14d_boosted": round(total_boosted_raw, 2),
            "systemwide_crawl_to_cite_ratio": round(CRAWL_TO_CITE_RATIO, 5),
            "boosted_multiplier": BOOSTED_MULTIPLIER,
        },
    }
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
