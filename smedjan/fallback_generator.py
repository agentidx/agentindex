"""
Smedjan fallback-task generator (F3 of the autonomy rollout).

Keeps the Smedjan fallback queue primed so the worker always has something
low-priority to do when the primary queue is empty.

Policy
------
For each fallback category (F1, F2, F3):

1. Count live fallback tasks — `status IN ('pending','queued','approved',
   'in_progress') AND is_fallback = true AND fallback_category = <cat>`.
2. If that count is < TARGET_PER_CATEGORY (10), insert as many new tasks
   as needed to top the category up to TARGET_PER_CATEGORY.
3. Each generated task gets id `FB-{cat}-{YYYYMMDD}-{NNN}` where NNN is a
   3-digit per-day per-category counter (starts after the largest NNN
   already present in smedjan.tasks for that (cat, date)).
4. After inserting, call `factory_core.resolve_ready_tasks()` so the
   low-risk + whitelisted rows flip pending -> queued immediately and
   become claimable by the worker.

Invariants kept by this module
------------------------------
- All DB access goes through `smedjan.sources.get_smedjan_db()` — no
  hard-coded DSN (see sources.py contract).
- Tasks inserted with priority=10, risk_level='low', is_fallback=true,
  whitelisted_files=['smedjan/audits/'] so `compute_ready_status()` in
  factory_core auto-yes's them.
- Dependencies=[] and wait_for_evidence=NULL so `resolve_ready_tasks`
  promotes them on the same run.
- ON CONFLICT (id) DO NOTHING keeps the run idempotent in the (unlikely)
  case of an id collision.

Entrypoint
----------
Run as `python3 -m smedjan.fallback_generator`. Designed for the systemd
timer `smedjan-fallback-generator.timer` (every 6h).
"""
from __future__ import annotations

import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2.extras

from smedjan import factory_core
from smedjan.sources import get_smedjan_db

log = logging.getLogger("smedjan.fallback_generator")


TARGET_PER_CATEGORY = 10
LIVE_STATUSES = ("pending", "queued", "approved", "in_progress")
CATEGORIES = ("F1", "F2", "F3")


# ── Per-category task template ────────────────────────────────────────────
#
# Each template is SELF-CONTAINED: the worker feeds `description` straight
# into `claude -p`, so it must carry every instruction the agent needs.
# `{date}` and `{task_id}` are substituted at generation time so each task
# writes to a unique output path.

_TEMPLATES: dict[str, dict[str, str]] = {
    "F1": {
        "title": "F1 quality_audit: random /safe/* antipattern spot-check",
        "description": (
            "Fallback-generated quality audit. FIRST, load the antipattern "
            "ruleset from ~/smedjan/config/f1_antipatterns.json — it is a "
            "JSON object with a 'regex_patterns' list (each item has name, "
            "regex, description) and a 'structural_checks' list (jsonld "
            "presence + json.loads validity). Do NOT hardcode the patterns — "
            "the JSON is the source of truth so future tasks can extend it "
            "without a code change. If the JSON is missing or unparseable, "
            "return STATUS: blocked with a note.\n\n"
            "Then curl 100 random enriched /safe/<slug> pages on "
            "https://nerq.ai (pick slugs via SELECT slug FROM "
            "software_registry WHERE enriched_at IS NOT NULL ORDER BY "
            "random() LIMIT 100 on the Nerq read-only source; sources.py -> "
            "get_nerq_readonly()). For each page, apply every regex in "
            "regex_patterns against the rendered HTML and run each "
            "structural_check (at least one <script "
            "type=\"application/ld+json\"> present AND every such block "
            "parses with json.loads). Write findings to "
            "~/smedjan/audits/{task_id}.md with a table of (pattern_name, "
            "count, sample_slugs[:3]) covering every pattern loaded (even "
            "ones with count=0). If any single pattern affects more than 5 "
            "pages, return STATUS: needs_approval in the task-result block "
            "with the finding description — Anders picks the fix task. "
            "Otherwise STATUS: done with EVIDENCE "
            "{\"pages_checked\": 100, \"patterns_loaded\": <int>, "
            "\"findings\": <count of patterns with count>0>}."
        ),
        "acceptance_criteria": (
            "File ~/smedjan/audits/{task_id}.md exists and is non-empty. "
            "It contains a table (markdown pipes) summarising the 100-sample "
            "scan with one row per pattern loaded from "
            "~/smedjan/config/f1_antipatterns.json. EVIDENCE block reports "
            "pages_checked=100 and patterns_loaded=<int>. Any antipattern "
            "with count > 5 escalates via STATUS: needs_approval rather than "
            "done."
        ),
    },
    "F2": {
        "title": "F2 freshness_refresh: 200 oldest top-5-registry enriched entries",
        "description": (
            "Fallback-generated freshness prep. Read-only on Nerq, write-only "
            "on Smedjan queue. Two outputs: (1) CSV audit trail, (2) five "
            "follow-up 'refresh-slug' queue tasks that a future enricher "
            "consumes.\n\n"
            "STEP 1 — CSV. Against the Nerq read-only source "
            "(sources.get_nerq_readonly()), determine the top-5 registries "
            "by ai_demand_score coverage (join smedjan.ai_demand_scores -> "
            "software_registry, count rows per registry, take the 5 "
            "largest). Then run: SELECT slug, registry, enriched_at FROM "
            "software_registry WHERE registry IN (<top5>) ORDER BY "
            "registry, enriched_at ASC LIMIT 200. Write the result to "
            "~/smedjan/audits/{task_id}.csv with header "
            "'slug,registry,enriched_at,ai_demand_score'. Sort is "
            "(registry ASC, enriched_at ASC).\n\n"
            "STEP 2 — emit 5 refresh-slug queue tasks. Pick the first 5 "
            "rows of the CSV (the single oldest enriched slug across the "
            "five registries, so each refresh task targets a distinct, "
            "maximally-stale slug). For each picked row N in 1..5, run "
            "~/agentindex/scripts/smedjan queue add with the following "
            "flags (NO direct SQL inserts — use the CLI only):\n"
            "  --id refresh-slug-{task_id}-N   (N = 1..5, zero-padded not required)\n"
            "  --title 'Refresh enrichment for <registry>/<slug>'\n"
            "  --description <instruction to re-run the enricher for that "
            "    single (registry, slug) pair and update software_registry."
            "    enriched_at; the future enricher consumes the CSV row "
            "    at ~/smedjan/audits/{task_id}.csv line N+1 as input>\n"
            "  --acceptance <criteria stating enriched_at for that slug is "
            "    advanced past the value captured in the parent F2 CSV>\n"
            "  --risk low\n"
            "  --priority 40\n"
            "  --session-affinity d\n"
            "  --whitelist smedjan/enricher/,smedjan/audits/\n"
            "Record each resulting task id in the EVIDENCE block.\n\n"
            "No enricher call is made HERE — this F2 run just writes the "
            "CSV and queues follow-up work. A later refresh-slug task "
            "(consumed by the d-affinity worker) does the real enrichment."
        ),
        "acceptance_criteria": (
            "File ~/smedjan/audits/{task_id}.csv exists with exactly 201 "
            "lines (1 header + 200 data rows). Rows sorted by (registry, "
            "enriched_at ASC). In addition, 5 new 'refresh-slug-{task_id}-N' "
            "rows (N=1..5) exist in smedjan.tasks, each with risk_level=low, "
            "priority=40, session_affinity='d'. EVIDENCE reports "
            "row_count=200, the five registries picked, and the five "
            "refresh-slug task ids created."
        ),
    },
    "F3": {
        # Reformulated 2026-04-19: prior "coverage check" spec produced 100%
        # "skip" output because the top-25-demand pairs in each registry
        # already have /compare/ pages. Quality-audit the existing pages
        # instead — the output is useful signal, not a tautology.
        # Extended 2026-04-19 (FU-CITATION-20260418-03): seed half the
        # sample pool from the trust-score × crawl-coverage bottom decile
        # so the audit surfaces high-trust-but-invisible slugs via /compare/.
        "title": "F3 compare_quality_audit: HTML-level audit of 50 existing /compare/ pages",
        "description": (
            "Fallback-generated quality audit of EXISTING /compare/ pages. "
            "No coverage/creation proposals — those always produced 100% "
            "'skip' output because top-demand pairs already ship. This task "
            "instead grades the pages that already exist, with half the "
            "sample drawn from high-trust / low-crawl-coverage slugs so we "
            "close the F3 audit-finding gap (FU-CITATION-20260418-03).\n\n"
            "Sampling — build the 50-URL pool in two halves:\n"
            "  HALF A (25 URLs, trust-seeded): read the bottom decile of "
            "     smedjan.trust_score_crawl_coverage_30d (via "
            "     sources.smedjan_db_cursor()):\n"
            "         SELECT slug FROM smedjan.trust_score_crawl_coverage_30d\n"
            "          WHERE coverage_gap_rank <= (\n"
            "              SELECT GREATEST(1, count(*)/10)\n"
            "                FROM smedjan.trust_score_crawl_coverage_30d)\n"
            "          ORDER BY coverage_gap_rank ASC;\n"
            "     For each decile slug, pair it with a randomly-picked "
            "     top-100-demand slug from the same registry (via "
            "     smedjan.ai_demand_scores -> software_registry on Nerq). "
            "     HEAD /compare/<decile-slug>-vs-<demand-slug> on "
            "     https://nerq.ai; keep the first 25 that return 200. If "
            "     fewer than 25 /compare/ pages already exist for decile "
            "     pairs, fall back to the next-lowest decile rank until you "
            "     hit 25 or exhaust the view; record any shortfall in "
            "     EVIDENCE.trust_seeded_shortfall.\n"
            "  HALF B (25 URLs, demand-seeded): the existing behaviour. "
            "     Select 25 random EXISTING /compare/<a>-vs-<b> URLs from "
            "     public.comparisons OR by sampling pairs that returned "
            "     HTTP 200 on a quick pre-check. If comparisons is "
            "     unavailable, fall back to: pair top-100 demand slugs per "
            "     registry, curl /compare/<a>-vs-<b> HEAD, keep the first "
            "     25 that return 200.\n"
            "  Dedup / filters applied to the union:\n"
            "  1. Avoid duplicates within the last 7 days — read prior "
            "     audit JSONL files under ~/smedjan/audits/ with glob "
            "     'FB-F3-*.sampled_urls.jsonl', collect their sampled URLs, "
            "     and exclude those from the current sample pool.\n"
            "  2. Dedup the two halves against each other (same URL in A "
            "     and B counts once; backfill the free slot from the "
            "     opposing pool).\n"
            "  3. ALWAYS exclude slug 'test' (noise).\n\n"
            "For each sampled URL, curl the full HTML from https://nerq.ai "
            "and extract:\n"
            "  - has_king_sections: bool  — is the 5-dim Detailed-Score-"
            "    Analysis table present? (look for the heading 'Detailed "
            "    Score Analysis' or a table with rows 'Security / "
            "    Maintenance / Popularity / Quality / Community')\n"
            "  - has_pplx_verdict:  bool  — <p class=\"pplx-verdict\">\n"
            "  - has_ai_summary:    bool  — <p class=\"ai-summary\">\n"
            "  - has_faq_jsonld:    bool  — a <script type=\"application/"
            "    ld+json\"> block whose json.loads() yields '@type':'FAQPage'\n"
            "  - word_count:        int   — text-only words in the <body>\n"
            "  - number_tokens:     int   — integer + decimal tokens in the body\n"
            "  - data_density:      float — number_tokens per 1000 words\n"
            "  - last_enriched_at:  iso   — max(enriched_at) across slug_a + "
            "    slug_b from software_registry\n"
            "  - staleness_days:    int   — days since last_enriched_at\n\n"
            "Write two files:\n"
            "  - ~/smedjan/audits/{task_id}.md: findings-table with one row "
            "    per sampled URL (include a 'seed' column: A=trust, "
            "    B=demand), plus a leading summary section with counts "
            "    (pages missing king_sections, missing sacred bytes, word "
            "    count distribution [p25/p50/p75], data_density p50, "
            "    staleness p50 and count(staleness > 30d)) broken down by "
            "    seed so we can tell whether trust-seeded /compare/ pages "
            "    underperform demand-seeded ones. Include an 'Escalation "
            "    list' section listing the URLs that fail any of: missing "
            "    king_sections, missing pplx-verdict, missing ai-summary, "
            "    missing FAQ JSON-LD, word_count < 200, data_density < 2, "
            "    staleness > 60d.\n"
            "  - ~/smedjan/audits/{task_id}.sampled_urls.jsonl: one JSON "
            "    object per line with {url, seed ('A'|'B'), "
            "    has_king_sections, has_pplx_verdict, has_ai_summary, "
            "    has_faq_jsonld, word_count, number_tokens, data_density, "
            "    last_enriched_at, staleness_days, coverage_gap_rank "
            "    (null for seed='B')}.\n\n"
            "STATUS: done if the audit file + JSONL are written with 50 rows "
            "each and at least one of the findings is reported. STATUS: "
            "needs_approval if > 20 of 50 pages are on the escalation list "
            "— that is a systemic regression worth human review."
        ),
        "acceptance_criteria": (
            "Two files exist: ~/smedjan/audits/{task_id}.md and "
            "~/smedjan/audits/{task_id}.sampled_urls.jsonl. The JSONL has "
            "exactly 50 lines, with a 'seed' field on every row and at "
            "least one row where seed='A' (trust-seeded, from "
            "smedjan.trust_score_crawl_coverage_30d). The markdown has a "
            "summary section + findings-table + escalation-list section. "
            "No sampled URL appears in the last 7 days of prior F3 audit "
            "JSONL files. Slug 'test' appears in neither file. EVIDENCE "
            "reports pages_audited=50, escalation_count=<int>, "
            "p50_data_density, p50_staleness_days, "
            "trust_seeded_count (count of seed='A' rows), and "
            "trust_seeded_shortfall (int, 0 if HALF A filled)."
        ),
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────

_ID_RX = re.compile(r"^FB-(F[123])-(\d{8})-(\d{3})$")


def _current_counts(cur) -> dict[str, int]:
    # `status` is the smedjan.task_status enum; `fallback_category` is text.
    # Cast status::text so we can compare against a plain text[] array
    # without having to know the enum's fully-qualified type name.
    cur.execute(
        """
        SELECT fallback_category, count(*)
        FROM smedjan.tasks
        WHERE is_fallback = true
          AND status::text = ANY(%s)
          AND fallback_category = ANY(%s)
        GROUP BY fallback_category
        """,
        (list(LIVE_STATUSES), list(CATEGORIES)),
    )
    out = {c: 0 for c in CATEGORIES}
    for cat, n in cur.fetchall():
        out[cat] = int(n)
    return out


def _max_counter_today(cur, cat: str, date_str: str) -> int:
    """Largest NNN already present among FB-{cat}-{date}-NNN ids. 0 if none."""
    cur.execute(
        """
        SELECT id FROM smedjan.tasks
        WHERE id LIKE %s
        """,
        (f"FB-{cat}-{date_str}-%",),
    )
    mx = 0
    for (task_id,) in cur.fetchall():
        m = _ID_RX.match(task_id)
        if m and m.group(1) == cat and m.group(2) == date_str:
            mx = max(mx, int(m.group(3)))
    return mx


def _substitute(text: str, task_id: str, date_str: str) -> str:
    """Light-weight placeholder substitution that does NOT use str.format —
    template bodies contain JSON literals with braces (e.g. {"k": "v"})
    which str.format would choke on.
    """
    return (
        text
        .replace("{task_id}", task_id)
        .replace("{date}", date_str)
    )


def _build_task(cat: str, task_id: str, date_str: str) -> dict:
    tpl = _TEMPLATES[cat]
    return {
        "id": task_id,
        "title": f"{tpl['title']} ({date_str} {task_id[-3:]})",
        "description": _substitute(tpl["description"], task_id, date_str),
        "acceptance_criteria": _substitute(tpl["acceptance_criteria"], task_id, date_str),
        "dependencies": [],
        "risk_level": "low",
        "whitelisted_files": ["smedjan/audits/"],
        "priority": 10,
        "is_fallback": True,
        "fallback_category": cat,
        "status": "pending",
    }


def _insert_task(cur, t: dict) -> bool:
    cur.execute(
        """
        INSERT INTO smedjan.tasks (
            id, title, description, acceptance_criteria,
            dependencies, risk_level, whitelisted_files, priority,
            is_fallback, fallback_category, status
        ) VALUES (
            %(id)s, %(title)s, %(description)s, %(acceptance_criteria)s,
            %(dependencies)s, %(risk_level)s, %(whitelisted_files)s, %(priority)s,
            %(is_fallback)s, %(fallback_category)s, %(status)s
        )
        ON CONFLICT (id) DO NOTHING
        """,
        t,
    )
    return cur.rowcount == 1


# ── Pause flags ──────────────────────────────────────────────────────────

# Per-category pause: if `~/smedjan/config/<cat_lower>_paused.flag` exists
# the generator skips that category. Used when an existing run is waiting
# on an upstream deploy (F3 paused until L1b live — every new F3 audit
# would re-discover the same compare-page regression, wasting worker time
# and Anders' attention). Unpause by deleting the flag; the evidence-
# emitter will do that automatically when "l1b_canary_48h_green" signals
# arrive (see smedjan/scripts/emit_evidence.py).
_PAUSE_FLAG_DIR = Path.home() / "smedjan" / "config"


def _is_paused(cat: str) -> bool:
    try:
        return (_PAUSE_FLAG_DIR / f"{cat.lower()}_paused.flag").exists()
    except Exception:  # noqa: BLE001 — filesystem blip = assume not paused
        return False


# ── Main entrypoint ───────────────────────────────────────────────────────

def generate() -> dict[str, int]:
    """Top each fallback category up to TARGET_PER_CATEGORY. Returns the
    per-category count of tasks inserted in this run.
    """
    generated: dict[str, int] = {c: 0 for c in CATEGORIES}
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    conn = get_smedjan_db()
    try:
        with conn.cursor() as cur:
            counts = _current_counts(cur)
            log.info("live fallback counts: %s (target %d)", counts, TARGET_PER_CATEGORY)

            for cat in CATEGORIES:
                if _is_paused(cat):
                    log.info("category %s paused via %s_paused.flag — skipping",
                             cat, cat.lower())
                    continue
                shortfall = TARGET_PER_CATEGORY - counts.get(cat, 0)
                if shortfall <= 0:
                    continue
                counter = _max_counter_today(cur, cat, date_str)
                for _ in range(shortfall):
                    counter += 1
                    task_id = f"FB-{cat}-{date_str}-{counter:03d}"
                    task = _build_task(cat, task_id, date_str)
                    if _insert_task(cur, task):
                        generated[cat] += 1
                    # If insert conflicted (already exists) just move on to
                    # next counter — loop bound ensures we still try the
                    # full shortfall count.
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Promote freshly-inserted pending rows to queued (auto-yes because
    # risk=low + whitelist is under smedjan/audits/).
    resolve_summary = factory_core.resolve_ready_tasks()
    log.info("resolve_ready_tasks summary: %s", resolve_summary)

    return generated


def _print_summary(generated: dict[str, int]) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total = sum(generated.values())
    print(f"[{now}] fallback_generator: generated {total} task(s)")
    for cat in CATEGORIES:
        print(f"  {cat}: +{generated[cat]}")

    # Re-query post-state so the log tells you whether the target is met.
    conn = get_smedjan_db()
    try:
        with conn.cursor() as cur:
            post = _current_counts(cur)
    finally:
        conn.close()
    print(f"[{now}] post-run live counts: {post} (target {TARGET_PER_CATEGORY})")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    try:
        generated = generate()
    except Exception as e:  # noqa: BLE001 — top-level guard for systemd
        log.exception("fallback_generator failed: %s", e)
        return 1
    _print_summary(generated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
