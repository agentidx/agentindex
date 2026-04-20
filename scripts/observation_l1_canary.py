#!/usr/bin/env python3
"""
observation_l1_canary.py — 12-hour observation snapshot for the L1 canary.

Compares current state against the PRE-deploy baseline and writes a
Markdown report per run, with a cumulative JSON log so successive reports
can show trend lines.

Triggers via LaunchAgent every 12h for the first 48h post-deploy.

With `--wave-comparator` an extra section is appended comparing Wave 1
(gems+homebrew), Wave 2 (npm+pypi+crates) and Wave 3 (remaining registries)
for AI-bot crawls, citations, and 24h 5xx — intended for every-other-tick
(24h cadence) use from the smedjan-l1-observation systemd service. Without
the flag the script produces byte-identical output to its pre-flag form.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smedjan import sources  # noqa: E402

# The baseline JSON is optional at runtime — the smedjan host may not have
# it mounted. If missing, render a report without the "vs baseline" column.
BASELINE_JSON = os.path.expanduser(
    os.environ.get(
        "SMEDJAN_BASELINE_JSON",
        "~/smedjan/baselines/L1-canary-gems-homebrew-PRE-2026-04-18.json",
    )
)
REPORT_DIR    = Path(os.path.expanduser(
    os.environ.get("SMEDJAN_OBS_DIR", "~/smedjan/observations")
))
CANARY_REGS   = ["gems", "homebrew"]
NTFY_TOPIC    = os.environ.get("SMEDJAN_NTFY_TOPIC", "nerq-alerts")

# Wave definitions for --wave-comparator. Wave 3 is resolved at runtime
# as "all enriched non-king registries not in Wave 1 or Wave 2", so it
# tracks the L1 rollout frontier as new registries get enriched.
WAVE_1_REGS = ["gems", "homebrew"]
WAVE_2_REGS = ["npm", "pypi", "crates"]

AI_REFERRER_HOSTS = [
    "chat.openai.com", "chatgpt.com", "claude.ai", "anthropic.com",
    "perplexity.ai", "www.perplexity.ai", "gemini.google.com", "bard.google.com",
    "poe.com", "you.com", "copilot.microsoft.com", "bing.com",
    "duckduckgo.com", "phind.com", "kagi.com", "grok.com", "x.ai",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smedjan.observation")


def load_canary_slugs() -> dict[str, set[str]]:
    out = {r: set() for r in CANARY_REGS}
    with sources.nerq_readonly_cursor() as (_, cur):
        for reg in CANARY_REGS:
            cur.execute(
                "SELECT slug FROM public.software_registry "
                "WHERE registry = %s AND is_king = false AND enriched_at IS NOT NULL",
                (reg,),
            )
            out[reg] = {r[0].lower() for r in cur.fetchall()}
    return out


def path_slug(path: str) -> str | None:
    m = re.match(r"/safe/([^/?#]+)", path)
    return unquote(m.group(1)).lower() if m else None


def gather(reg_slugs: dict[str, set[str]]) -> dict:
    slug_to_reg: dict[str, str] = {}
    for reg, slugs in reg_slugs.items():
        for s in slugs:
            slug_to_reg[s] = reg

    ai_rx = re.compile("|".join(re.escape(h) for h in AI_REFERRER_HOSTS), re.I)
    now = datetime.now(timezone.utc)
    t_7d  = now - timedelta(days=7)
    t_24h = now - timedelta(hours=24)
    t_12h = now - timedelta(hours=12)

    windows = {"7d": t_7d, "24h": t_24h, "12h": t_12h}
    ai_bot = {w: {r: 0 for r in CANARY_REGS} for w in windows}
    citations = {w: {r: 0 for r in CANARY_REGS} for w in windows}
    status_5xx = {w: {r: {"total": 0, "5xx": 0} for r in CANARY_REGS} for w in windows}
    ai_source_12h = {r: {} for r in CANARY_REGS}

    with sources.analytics_mirror_cursor() as (_, cur):
        cur.execute("SET statement_timeout = '120s'")
        # One scan of the last 7d window covering everything is cheaper
        # than 3 separate queries.
        cur.execute(
            "SELECT ts, path, status, is_ai_bot, referrer_domain "
            "FROM requests WHERE path LIKE '/safe/%%' AND ts > %s",
            (t_7d,),
        )
        for ts, path, status, is_ai_bot, ref in cur:
            slug = path_slug(path)
            if slug is None:
                continue
            reg = slug_to_reg.get(slug)
            if reg is None:
                continue
            for w, cutoff in windows.items():
                if ts > cutoff:
                    if is_ai_bot == 1:
                        ai_bot[w][reg] += 1
                    elif ref and ai_rx.search(ref):
                        citations[w][reg] += 1
                    if w in ("24h", "12h"):
                        status_5xx[w][reg]["total"] += 1
                        if status is not None and status >= 500:
                            status_5xx[w][reg]["5xx"] += 1
                    if w == "12h" and is_ai_bot == 0 and ref and ai_rx.search(ref):
                        for h in AI_REFERRER_HOSTS:
                            if h in ref.lower():
                                ai_source_12h[reg][h] = ai_source_12h[reg].get(h, 0) + 1
                                break

        # Whole-site 5xx last 12h (for context). The mirror only holds
        # filtered rows (is_ai_bot=1 OR /safe/* / /compare/* / /best/* /
        # /alternatives/* OR status>=400), so "whole-site" here really
        # means "filtered subset" — good enough for 5xx sanity, not for a
        # true denominator. See analytics_mirror filter for exact scope.
        cur.execute(
            "SELECT COUNT(*), SUM(CASE WHEN status>=500 THEN 1 ELSE 0 END) "
            "FROM requests WHERE ts > %s", (t_12h,),
        )
        whole_total, whole_5xx = cur.fetchone()

    return {
        "ai_bot":          ai_bot,
        "citations":       citations,
        "status_5xx":      status_5xx,
        "whole_12h_total": whole_total or 0,
        "whole_12h_5xx":   int(whole_5xx or 0),
        "ai_source_12h":   ai_source_12h,
    }


def render(baseline: dict, obs: dict) -> str:
    now = datetime.now(timezone.utc)
    deploy_t = datetime.fromisoformat("2026-04-18T11:34:18+00:00")
    hours_in = (now - deploy_t).total_seconds() / 3600

    ai_bot = obs["ai_bot"]
    citations = obs["citations"]
    s5xx = obs["status_5xx"]

    # Baseline (per PRE-deploy snapshot)
    bl_ai_7d = baseline["analytics"]["ai_bot_crawls_7d"]       # dict by reg
    bl_cit_7d = baseline["analytics"]["citations_7d"]
    bl_cohort = baseline["analytics"]["fivexx_24h_cohort"]     # {reg: {total,5xx}}
    bl_whole  = baseline["analytics"]["fivexx_24h_whole"]

    lines = [
        f"# L1 Canary — Observation T+{hours_in:.1f}h",
        "",
        f"**Generated:** {now.isoformat()}",
        f"**Deploy T0:** {deploy_t.isoformat()}",
        f"**Canary registries:** {', '.join(CANARY_REGS)}",
        f"**Rollback runbook:** `~/smedjan/runbooks/L1-rollback.md`",
        "",
        "## AI-bot crawls — canary cohort",
        "",
        "| Window | gems | homebrew | total |",
        "|---|---:|---:|---:|",
    ]
    for w in ("12h", "24h", "7d"):
        g, hb = ai_bot[w]["gems"], ai_bot[w]["homebrew"]
        lines.append(f"| {w} | {g:,} | {hb:,} | {g+hb:,} |")

    lines += [
        "",
        f"Baseline (PRE, 7d): gems={bl_ai_7d['gems']:,} / homebrew={bl_ai_7d['homebrew']:,}",
        "",
        "## Citations (human visits with AI-platform referrer) — canary cohort",
        "",
        "| Window | gems | homebrew | total |",
        "|---|---:|---:|---:|",
    ]
    for w in ("12h", "24h", "7d"):
        g, hb = citations[w]["gems"], citations[w]["homebrew"]
        lines.append(f"| {w} | {g:,} | {hb:,} | {g+hb:,} |")

    lines += [
        "",
        f"Baseline (PRE, 7d): gems={bl_cit_7d['gems']} / homebrew={bl_cit_7d['homebrew']}",
        "",
        "## 5xx observed — canary cohort",
        "",
        "| Window | gems total | gems 5xx | homebrew total | homebrew 5xx |",
        "|---|---:|---:|---:|---:|",
    ]
    for w in ("12h", "24h"):
        g = s5xx[w]["gems"]
        hb = s5xx[w]["homebrew"]
        lines.append(f"| {w} | {g['total']:,} | {g['5xx']} | {hb['total']:,} | {hb['5xx']} |")

    lines += [
        "",
        f"Baseline (PRE, 24h): gems={bl_cohort['gems']['5xx']}/{bl_cohort['gems']['total']} / "
        f"homebrew={bl_cohort['homebrew']['5xx']}/{bl_cohort['homebrew']['total']}",
        "",
        "## Whole-site 5xx (12h context)",
        "",
        f"- Total requests: {obs['whole_12h_total']:,}",
        f"- 5xx count: {obs['whole_12h_5xx']}",
        f"- 5xx rate: {100.0 * obs['whole_12h_5xx'] / max(1, obs['whole_12h_total']):.4f}%",
        f"- PRE-baseline (24h): {bl_whole['5xx']}/{bl_whole['total']:,} = "
        f"{100.0 * bl_whole['5xx'] / max(1, bl_whole['total']):.4f}%",
        "",
        "## Citation sources (12h, canary cohort)",
        "",
    ]
    for reg, src in obs["ai_source_12h"].items():
        if not src:
            lines.append(f"- **{reg}:** no AI-platform citations in the last 12h.")
            continue
        lines.append(f"- **{reg}:**")
        for host, n in sorted(src.items(), key=lambda kv: -kv[1])[:10]:
            lines.append(f"  - {host}: {n}")

    lines += [
        "",
        "## Trend vs baseline",
        "",
        f"- gems AI-bot crawls, 7d now vs 7d baseline: {ai_bot['7d']['gems']:,} vs {bl_ai_7d['gems']:,}",
        f"- homebrew AI-bot crawls, 7d now vs 7d baseline: {ai_bot['7d']['homebrew']:,} vs {bl_ai_7d['homebrew']:,}",
        f"- Combined citations, 7d now vs 7d baseline: {citations['7d']['gems']+citations['7d']['homebrew']:,} "
        f"vs {bl_cit_7d['gems']+bl_cit_7d['homebrew']}",
        "",
        "Note: trend interpretation is weak before T+48h because the 7d window overlaps the pre-deploy period. T+48h onward the window is a clean post-deploy measurement.",
    ]
    return "\n".join(lines)


def _discover_wave_regs() -> dict[str, list[str]]:
    """Cheap query: list every enriched non-king registry (DISTINCT across
    a 4.9M-row table is still fast because registry is indexed)."""
    wave_regs: dict[str, list[str]] = {"wave1": list(WAVE_1_REGS), "wave2": list(WAVE_2_REGS), "wave3": []}
    known = set(WAVE_1_REGS) | set(WAVE_2_REGS)
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT DISTINCT registry FROM public.software_registry "
            "WHERE is_king = false AND enriched_at IS NOT NULL"
        )
        all_regs = [r[0] for r in cur.fetchall()]
    wave_regs["wave3"] = sorted(r for r in all_regs if r not in known)
    return wave_regs


def _resolve_slug_waves(seen_slugs: set[str], wave_regs: dict[str, list[str]]) -> dict[str, str]:
    """Map each seen slug → wave. Only queries for slugs that actually
    appeared in the request scan, so the Postgres load is bounded by
    analytics_mirror hits (thousands) rather than by the full enriched
    corpus (millions)."""
    if not seen_slugs:
        return {}
    reg_to_wave: dict[str, str] = {}
    for r in WAVE_1_REGS:
        reg_to_wave[r] = "wave1"
    for r in WAVE_2_REGS:
        reg_to_wave[r] = "wave2"
    for r in wave_regs["wave3"]:
        reg_to_wave[r] = "wave3"

    slug_rows: list[tuple[str, str]] = []
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute("SET statement_timeout = '60s'")
        cur.execute(
            "SELECT lower(slug), registry FROM public.software_registry "
            "WHERE is_king = false AND enriched_at IS NOT NULL "
            "AND registry = ANY(%s) AND lower(slug) = ANY(%s)",
            (list(reg_to_wave.keys()), list(seen_slugs)),
        )
        slug_rows = cur.fetchall()

    # Assign each slug to its lowest (earliest) wave — keeps Wave 1
    # counts aligned with the canary "Trend vs baseline" section.
    wave_rank = {"wave1": 0, "wave2": 1, "wave3": 2}
    slug_to_wave: dict[str, str] = {}
    for slug, reg in slug_rows:
        w = reg_to_wave[reg]
        prev = slug_to_wave.get(slug)
        if prev is None or wave_rank[w] < wave_rank[prev]:
            slug_to_wave[slug] = w
    return slug_to_wave


def gather_waves() -> tuple[dict[str, dict[str, int]], dict[str, list[str]]]:
    """Single 7d/24h scan of /safe/* producing per-wave pivot metrics.

    Returns (pivot, wave_regs). The scan is done first, then seen slugs
    are resolved to waves in a second pass so Postgres isn't asked to
    enumerate millions of slugs we'll never see traffic for.
    """
    ai_rx = re.compile("|".join(re.escape(h) for h in AI_REFERRER_HOSTS), re.I)
    now = datetime.now(timezone.utc)
    t_7d = now - timedelta(days=7)
    t_24h = now - timedelta(hours=24)
    waves = ("wave1", "wave2", "wave3")
    pivot = {
        w: {"ai_bot_crawls_7d": 0, "citations_7d": 0,
            "fivexx_24h_total": 0, "fivexx_24h_count": 0}
        for w in waves
    }

    rows: list[tuple] = []
    seen_slugs: set[str] = set()
    with sources.analytics_mirror_cursor() as (_, cur):
        cur.execute("SET statement_timeout = '180s'")
        cur.execute(
            "SELECT ts, path, status, is_ai_bot, referrer_domain "
            "FROM requests WHERE path LIKE '/safe/%%' AND ts > %s",
            (t_7d,),
        )
        for ts, path, status, is_ai_bot, ref in cur:
            slug = path_slug(path)
            if slug is None:
                continue
            seen_slugs.add(slug)
            rows.append((ts, slug, status, is_ai_bot, ref))

    wave_regs = _discover_wave_regs()
    slug_to_wave = _resolve_slug_waves(seen_slugs, wave_regs)

    for ts, slug, status, is_ai_bot, ref in rows:
        w = slug_to_wave.get(slug)
        if w is None:
            continue
        if is_ai_bot == 1:
            pivot[w]["ai_bot_crawls_7d"] += 1
        elif ref and ai_rx.search(ref):
            pivot[w]["citations_7d"] += 1
        if ts > t_24h:
            pivot[w]["fivexx_24h_total"] += 1
            if status is not None and status >= 500:
                pivot[w]["fivexx_24h_count"] += 1
    return pivot, wave_regs


def render_wave_comparator(wave_regs: dict[str, list[str]], pivot: dict[str, dict[str, int]]) -> str:
    labels = {
        "wave1": f"Wave 1 ({'+'.join(wave_regs['wave1'])})",
        "wave2": f"Wave 2 ({'+'.join(wave_regs['wave2'])})",
        "wave3": f"Wave 3 (remaining, {len(wave_regs['wave3'])} registries)",
    }
    lines = [
        "",
        "## Wave comparator (6h run)",
        "",
        "| Cohort | AI-bot crawls 7d | Citations 7d | 5xx 24h total | 5xx 24h count |",
        "|---|---:|---:|---:|---:|",
    ]
    for w in ("wave1", "wave2", "wave3"):
        p = pivot[w]
        lines.append(
            f"| {labels[w]} | {p['ai_bot_crawls_7d']:,} | {p['citations_7d']:,} | "
            f"{p['fivexx_24h_total']:,} | {p['fivexx_24h_count']:,} |"
        )
    lines += [
        "",
        f"Wave 3 registries: {', '.join(wave_regs['wave3']) if wave_regs['wave3'] else '(none enriched yet)'}",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--wave-comparator",
        action="store_true",
        help="Append a Wave 1/2/3 pivot section to the report (24h cadence).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        baseline = json.loads(Path(BASELINE_JSON).read_text())
    except FileNotFoundError:
        log.error("baseline missing at %s — re-run scripts/baseline_l1_canary.py first", BASELINE_JSON)
        return 1

    reg_slugs = load_canary_slugs()
    obs = gather(reg_slugs)
    md = render(baseline, obs)

    if args.wave_comparator:
        wave_pivot, wave_regs = gather_waves()
        md = md + "\n" + render_wave_comparator(wave_regs, wave_pivot)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = REPORT_DIR / f"L1-canary-obs-{ts}.md"
    md_path.write_text(md)
    log.info("wrote %s (%d bytes)", md_path, md_path.stat().st_size)

    # Append to cumulative JSON log
    jsonl = REPORT_DIR / "L1-canary-observations.jsonl"
    with jsonl.open("a") as fh:
        fh.write(json.dumps({"ts": ts, "obs": obs}, default=str) + "\n")

    # 12h canary observations are telemetry: the Markdown report lands in
    # ~/smedjan/observations/ and the JSONL feeds the health dashboard.
    # Regression alerts (5xx spike, write-rate drop) fire from
    # canary_monitor_l1.py, which IS action-required. This report is not.
    log.info("canary observation written: %s", md_path.name)

    # After writing the latest observation, ask emit_evidence to
    # re-evaluate l1_canary_observation_48h. Before T+48h the evaluator
    # is a no-op that logs "NOT green ... gate not met"; at the first
    # tick past T+48h with a clean window it auto-emits and downstream
    # resolve_ready_tasks promotes dependents. L1b has the same hook —
    # see observation_l1b_canary.py; this one was missing, which is why
    # no l1_canary_observation_48h signal reached smedjan.evidence_signals
    # despite L1 Wave 1 passing the 48h green gate on 2026-04-19.
    try:
        from smedjan.scripts import emit_evidence as _ee
        _ee.run(signal="l1_canary_observation_48h", dry_run=False)
    except Exception as e:  # noqa: BLE001 — observer must not fail on emitter
        log.warning("emit_evidence chain skipped: %s", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
