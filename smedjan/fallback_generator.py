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

# Per-category overrides. F2 reduced to 1 steady-state (from 10) because
# the brand value of additional F2 audits beyond a single active one is
# minimal — one running audit surfaces the current signal, more just
# pile up. F1 stays at 10 by default but is pause-flagged until signal
# (f1_restore_flag or removal of f1_paused.flag); see _is_paused below.
_TARGET_OVERRIDES = {
    "F2": 5,
}


def _target_for(cat: str) -> int:
    return _TARGET_OVERRIDES.get(cat, TARGET_PER_CATEGORY)
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
        # F3-v3 (post-L1b), 2026-04-23: the prior v2 ("compare_quality_audit")
        # kept rediscovering the same systemic regression — 99.8% of pages
        # missing king-sections and 100% missing pplx-verdict — because those
        # blocks simply were not rendered before T200 (L1b). That made F3
        # a tautology generator; Anders paused it via
        # ~/smedjan/config/f3_paused.flag on 2026-04-20. T200 shipped the
        # /compare/ Kings Unlock on 2026-04-20T12:09Z behind env-gate
        # L1B_COMPARE_UNLOCK_REGISTRIES=npm,pypi and the canary cleared the
        # 48h green gate (~/smedjan/scripts/emit_evidence.py
        # --signal l1b_canary_48h_green), which auto-removed the pause flag
        # + row from smedjan.pause_flags.
        #
        # F3-v3 verifies the OPPOSITE invariant of v2: on pairs where both
        # slugs are fully enriched AND sit in an unlocked registry, the
        # king-sections + pplx-verdict blocks MUST render; on pairs where
        # at least one slug is un-enriched (or the registry isn't in
        # L1B_COMPARE_UNLOCK_REGISTRIES), the fail-safe current template
        # MUST be preserved (no king-sections, no pplx-verdict, sacred
        # bytes still present). This turns the old false-positive firehose
        # into a pair of genuine guardrails.
        "title": "F3-v3 compare_l1b_verification: HTML audit of 50 /compare/ pages (40 enriched + 10 fail-safe)",
        "description": (
            "Fallback-generated post-L1b verification audit of /compare/ "
            "pages. The L1b canary shipped at T200 on 2026-04-20T12:09Z and "
            "cleared its 48h green gate — F3-v3 now verifies that, on "
            "unlocked pairs, the new template actually renders; and on "
            "locked pairs, the fail-safe behaviour is preserved.\n\n"
            "Sampling — build a 50-URL pool in two buckets. 'Unlocked "
            "registries' means the set in the running service's env var "
            "L1B_COMPARE_UNLOCK_REGISTRIES (default npm,pypi; re-read it "
            "from ~/Library/LaunchAgents/com.nerq.api.plist at run-time so "
            "a future canary expansion Just Works without a template edit):\n"
            "  BUCKET-ENRICHED (40 URLs): pairs where BOTH slugs exist in "
            "     public.software_registry (Nerq RO, "
            "     sources.nerq_readonly_cursor()) with enriched_at IS NOT "
            "     NULL AND every one of {security_score, maintenance_score, "
            "     popularity_score, quality_score, community_score} IS NOT "
            "     NULL, AND both slugs sit in an unlocked registry. Cross-"
            "     reference against ~/agentindex/agentindex/comparison_pairs"
            ".json to restrict the pool to pairs the generator actually "
            "     ships (21.4K pairs as of deploy). HEAD /compare/<a>-vs-<b> "
            "     on https://nerq.ai; keep the first 40 that return 200. If "
            "     fewer than 40 candidates qualify (narrow unlock cohort), "
            "     record the shortfall in EVIDENCE.enriched_shortfall and "
            "     carry on with the candidates you have — do NOT pad from "
            "     the locked pool; the two buckets are semantically "
            "     different and must not be mixed.\n"
            "  BUCKET-FAILSAFE (10 URLs minimum, padded up to 50-total): "
            "     pairs from the same comparison_pairs.json universe where "
            "     at least ONE slug fails the enrichment predicate above "
            "     OR sits in a registry outside L1B_COMPARE_UNLOCK_"
            "     REGISTRIES. Pick >=10 at random among those that return "
            "     HTTP 200; if the enriched bucket fell short of 40, keep "
            "     adding failsafe rows until the combined audit size "
            "     reaches 50 — maintains statistical weight even when "
            "     the unlock cohort is narrow (at L1b canary launch only "
            "     ~17 pairs actually qualified in npm,pypi). These verify "
            "     the current (pre-L1b) template is still served on locked "
            "     pairs — the whole point of the env gate is that we can "
            "     ship L1b to two registries without touching the rest.\n"
            "  Dedup / filters applied across both buckets:\n"
            "  1. Exclude slugs seen in the prior 7 days of F3 audit JSONL "
            "     files — glob ~/smedjan/audits/FB-F3-*.sampled_urls.jsonl, "
            "     collect URLs, exclude from both buckets.\n"
            "  2. Dedup between the two buckets (a URL can only belong to "
            "     one; tie-break: keep in ENRICHED).\n"
            "  3. ALWAYS exclude slug 'test' (noise).\n\n"
            "For each sampled URL, curl the full HTML from https://nerq.ai "
            "(User-Agent: 'SmedjanAudit/F3-v3') and extract:\n"
            "  - bucket:            str   — 'enriched' or 'failsafe'\n"
            "  - has_king_table:    bool  — HTML contains '<table "
            "    class=\"king-section\"' (singular — the L1b template emits "
            "    'king-section' without trailing s; future renames should "
            "    update this matcher). For semantic backup also accept "
            "    '<section class=\"king-sections' (skiss form) so we stay "
            "    forward-compatible with a refactor.\n"
            "  - king_rows_ok:      bool  — true iff the first "
            "    king-section table has exactly 5 tbody <tr> rows whose "
            "    first-cell text matches, in order, the dimensions "
            "    Security, Maintenance, Popularity, Quality, Community "
            "    (case-insensitive, whitespace-collapsed). Only checked "
            "    when has_king_table=true; otherwise false.\n"
            "  - king_cols_ok:      bool  — true iff the first "
            "    king-section table's thead has >=3 <th> cells (Dimension, "
            "    slug_a, slug_b) AND every tbody row has >=3 <td> cells. "
            "    Only checked when has_king_table=true.\n"
            "  - has_pplx_verdict:  bool  — HTML contains 'class=\"pplx-"
            "    verdict\"' (attribute order agnostic).\n"
            "  - pplx_data_sacred:  bool  — HTML contains 'data-sacred="
            "    \"pplx-verdict\"' on the same element. RECORDED AS "
            "    OBSERVATION (per-page boolean), NOT a PASS gate yet — "
            "    the L1b canary implementation did not emit data-sacred "
            "    on pplx-verdict (skiss intended, implementation deferred). "
            "    The first F3-v3 run is EXPECTED to show pplx_data_sacred="
            "    false on all enriched pages; if the count remains low "
            "    after 7 days, escalate via STATUS: needs_approval so "
            "    Anders decides whether to patch the template (adds "
            "    ~20 bytes per page) or tighten this spec.\n"
            "  - has_ai_summary:    bool  — HTML contains 'class=\"ai-"
            "    summary\"' (sacred byte — unchanged).\n"
            "  - has_faq_jsonld:    bool  — a <script type=\"application/"
            "    ld+json\"> block whose json.loads() yields "
            "    '@type':'FAQPage' (sacred byte — unchanged).\n"
            "  - word_count:        int   — text-only words in <body> after "
            "    stripping <script> and <style> tags.\n"
            "  - word_count_in_band: bool — for bucket='enriched': "
            "    1500 <= wc <= 2400 (spec target 1500-2000, 20% tolerance "
            "    top-end because the shipped template came in ~2300 mean "
            "    per the post-deploy audit); for bucket='failsafe': "
            "    wc < 1500 (fail-safe template is ~750-900 words).\n"
            "  - registry_a, registry_b: str — registries of each slug "
            "    (null if the slug doesn't resolve in software_registry).\n\n"
            "Per-page PASS/FAIL verdict — one boolean per criterion (a, b, "
            "c, d) and a compound 'page_pass':\n"
            "  bucket='enriched':\n"
            "    crit_a_king = has_king_table AND king_rows_ok AND king_cols_ok\n"
            "    crit_b_pplx = has_pplx_verdict  "
            "      (pplx_data_sacred separately tracked, not gating)\n"
            "    crit_c_sacred = has_ai_summary AND has_faq_jsonld\n"
            "    crit_d_words  = word_count_in_band\n"
            "    page_pass     = crit_a_king AND crit_b_pplx "
            "      AND crit_c_sacred AND crit_d_words\n"
            "  bucket='failsafe':\n"
            "    crit_a_king   = NOT has_king_table\n"
            "    crit_b_pplx   = NOT has_pplx_verdict\n"
            "    crit_c_sacred = has_ai_summary AND has_faq_jsonld\n"
            "    crit_d_words  = word_count_in_band  (i.e. wc < 1500)\n"
            "    page_pass     = crit_a_king AND crit_b_pplx "
            "      AND crit_c_sacred AND crit_d_words\n\n"
            "Write two files:\n"
            "  - ~/smedjan/audits/{task_id}.md: leading summary section with "
            "    per-bucket PASS-rate (enriched_pass_rate, "
            "    failsafe_pass_rate) and per-criterion pass counts "
            "    (crit_a/b/c/d × 2 buckets = 8 numbers). Include a "
            "    'pplx_data_sacred observation' line with the count of "
            "    enriched pages that also carried the sacred attribute. "
            "    Include word-count distribution p25/p50/p75 per bucket. "
            "    Findings table with one row per sampled URL (url, bucket, "
            "    4 crit booleans, page_pass, word_count, registry_a/b, "
            "    pplx_data_sacred). Ends with an 'Escalation list' of URLs "
            "    with page_pass=false, grouped by bucket.\n"
            "  - ~/smedjan/audits/{task_id}.sampled_urls.jsonl: one JSON "
            "    object per line carrying every field above.\n\n"
            "STATUS: done if both files are written with a combined 50 "
            "rows AND EVIDENCE reports every per-criterion count. STATUS: "
            "needs_approval if enriched_pass_rate < 0.80 (and at least 5 "
            "enriched rows exist — below 5 the rate is too noisy to "
            "escalate on) OR failsafe_pass_rate < 0.90 OR any SACRED byte "
            "(crit_c) fails on ANY page — those three thresholds define "
            "'systemic regression worth human review' under the post-L1b "
            "contract."
        ),
        "acceptance_criteria": (
            "Two files exist: ~/smedjan/audits/{task_id}.md and "
            "~/smedjan/audits/{task_id}.sampled_urls.jsonl. The JSONL "
            "combined row count is 50 (enriched + failsafe), with a "
            "'bucket' field on every row taking value 'enriched' or "
            "'failsafe'. Every row carries the four criterion booleans "
            "(crit_a_king, crit_b_pplx, crit_c_sacred, crit_d_words) "
            "and a compound 'page_pass'. The markdown carries a summary "
            "block with per-bucket pass-rates + per-criterion counts, a "
            "findings table, and an escalation-list section. No sampled "
            "URL appears in any prior F3 audit JSONL from the last 7 "
            "days. Slug 'test' appears in neither file. EVIDENCE reports "
            "pages_audited=<int>, enriched_count, enriched_shortfall, "
            "failsafe_count, enriched_pass_rate, failsafe_pass_rate, "
            "per-criterion pass counts (crit_a_enriched, crit_b_enriched, "
            "crit_c_enriched, crit_d_enriched, crit_a_failsafe, "
            "crit_b_failsafe, crit_c_failsafe, crit_d_failsafe), and "
            "pplx_data_sacred_count (observation only)."
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

# Per-category pause. Reads `smedjan.pause_flags` in the shared Postgres
# DB so both Mac-Studio-side workers and the Hetzner-side generator see
# the same state. (Previous file-based implementation lived only on Mac
# Studio's filesystem and silently no-op'd on Hetzner — 10 FB-F3 tasks
# slipped through the overnight 00:00 UTC run on 2026-04-20 because of
# exactly that split-brain.)
#
# Local filesystem flag (~/smedjan/config/<cat>_paused.flag) is kept as
# a compatibility fallback for hosts where the DB table hasn't been
# migrated yet, and as a human-readable signal. DB check takes priority.


def _is_paused(cat: str) -> bool:
    # Primary: shared DB table
    try:
        from smedjan.sources import get_smedjan_db
        conn = get_smedjan_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM smedjan.pause_flags WHERE category = %s",
                    (cat,),
                )
                if cur.fetchone() is not None:
                    return True
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("pause check (DB) failed for %s: %s — falling back to file flag", cat, exc)

    # Fallback: legacy file flag. Only useful when DB is unreachable.
    try:
        return (Path.home() / "smedjan" / "config" / f"{cat.lower()}_paused.flag").exists()
    except Exception:  # noqa: BLE001
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
                target = _target_for(cat)
                shortfall = target - counts.get(cat, 0)
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
