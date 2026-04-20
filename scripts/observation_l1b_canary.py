#!/usr/bin/env python3
"""
observation_l1b_canary.py — 12h observation snapshot for the L1b /compare/ canary.

Writes one Markdown report per invocation and appends a structured JSONL
entry to ``~/smedjan/observations/L1b-canary-observations.jsonl``. The
emit_evidence evaluator reads that JSONL and emits l1b_canary_48h_green
once 48h of clean post-T0 observations are in the log.

Scope
-----
The canary pairs are the 100 /compare/<slug> pages that the deploy script
pre-selected (both slugs enriched in npm or pypi). For each 12h/24h/7d
window we record:
  * total /compare/<canary_slug> requests
  * 5xx count on those requests, bucketed by (registry_a, registry_b)
  * AI-bot crawl count
  * citation count (human visits with AI-platform referrer)
  * whole-site 12h total + 5xx (sanity context)

JSONL row shape matches the L1 /safe/ canary so _evaluate_48h_green in
emit_evidence can reuse its green-gate logic without special-casing:
  {"ts": "20260420T130000Z",
   "obs": {"status_5xx": {"12h": {"npm": {"total": N, "5xx": n}, "pypi": {...}},
                          "24h": {...}},
           "whole_12h_total": N, "whole_12h_5xx": n, ...}}

We bucket /compare/ pairs by the registry that covers BOTH slugs
(or "cross" if they differ). npm/npm pairs land under "npm", pypi/pypi
under "pypi", mixed under "cross".
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smedjan import sources  # noqa: E402

PAIRS_JSON = os.path.expanduser(
    os.environ.get(
        "SMEDJAN_L1B_PAIRS_JSON",
        "~/smedjan/baselines/L1b-canary-pairs-npm-pypi-2026-04-20.json",
    )
)
REPORT_DIR = Path(os.path.expanduser(
    os.environ.get("SMEDJAN_OBS_DIR", "~/smedjan/observations")
))
COHORT_REGS = ["npm", "pypi", "cross"]

AI_REFERRER_HOSTS = [
    "chat.openai.com", "chatgpt.com", "claude.ai", "anthropic.com",
    "perplexity.ai", "www.perplexity.ai", "gemini.google.com", "bard.google.com",
    "poe.com", "you.com", "copilot.microsoft.com", "bing.com",
    "duckduckgo.com", "phind.com", "kagi.com", "grok.com", "x.ai",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("smedjan.observation.l1b")


def _compare_slug(path: str) -> str | None:
    m = re.match(r"/compare/([^/?#]+)", path)
    return unquote(m.group(1)).lower() if m else None


def load_cohort() -> dict[str, str]:
    """Return {pair_slug → cohort_key in {'npm','pypi','cross'}}."""
    data = json.loads(Path(PAIRS_JSON).read_text())
    cohort: dict[str, str] = {}
    for p in data["sample"]:
        ra, rb = p["registry_a"], p["registry_b"]
        if ra == rb:
            cohort[p["slug"].lower()] = ra  # "npm" or "pypi"
        else:
            cohort[p["slug"].lower()] = "cross"
    return cohort


def gather(cohort: dict[str, str]) -> dict:
    now = datetime.now(timezone.utc)
    t_7d = now - timedelta(days=7)
    t_24h = now - timedelta(hours=24)
    t_12h = now - timedelta(hours=12)

    windows = {"7d": t_7d, "24h": t_24h, "12h": t_12h}
    ai_bot = {w: {r: 0 for r in COHORT_REGS} for w in windows}
    citations = {w: {r: 0 for r in COHORT_REGS} for w in windows}
    status_5xx = {w: {r: {"total": 0, "5xx": 0} for r in COHORT_REGS} for w in windows}

    ai_rx = re.compile("|".join(re.escape(h) for h in AI_REFERRER_HOSTS), re.I)

    with sources.analytics_mirror_cursor() as (_, cur):
        cur.execute("SET statement_timeout = '120s'")
        cur.execute(
            "SELECT ts, path, status, is_ai_bot, referrer_domain "
            "FROM requests WHERE path LIKE '/compare/%%' AND ts > %s",
            (t_7d,),
        )
        for ts, path, status, is_ai_bot, ref in cur:
            slug = _compare_slug(path)
            if slug is None:
                continue
            reg = cohort.get(slug)
            if reg is None:
                continue
            for w, cutoff in windows.items():
                if ts <= cutoff:
                    continue
                if is_ai_bot == 1:
                    ai_bot[w][reg] += 1
                elif ref and ai_rx.search(ref):
                    citations[w][reg] += 1
                if w in ("24h", "12h"):
                    status_5xx[w][reg]["total"] += 1
                    if status is not None and status >= 500:
                        status_5xx[w][reg]["5xx"] += 1

        # Whole-site 12h (same caveats as L1 observation — mirror is
        # filtered). Used by emit_evidence to gate the 0.2% whole-site
        # 5xx rate check.
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
        "cohort_size":     len(cohort),
    }


def render(obs: dict) -> str:
    now = datetime.now(timezone.utc)
    deploy_t = datetime.fromisoformat("2026-04-20T12:09:21+00:00")
    hours_in = (now - deploy_t).total_seconds() / 3600

    s5 = obs["status_5xx"]
    ai = obs["ai_bot"]
    ci = obs["citations"]
    whole_rate = 100.0 * obs["whole_12h_5xx"] / max(1, obs["whole_12h_total"])

    lines = [
        f"# L1b /compare/ canary — observation T+{hours_in:.1f}h",
        "",
        f"**Generated:** {now.isoformat()}",
        f"**Deploy T0:** {deploy_t.isoformat()}",
        f"**Canary cohort:** {obs['cohort_size']} pairs (npm ∪ pypi, strict template-match)",
        f"**Env:** L1B_COMPARE_UNLOCK_REGISTRIES=npm,pypi",
        "",
        "## 5xx observed — canary cohort (/compare/<canary_slug>)",
        "",
        "| Window | npm total | npm 5xx | pypi total | pypi 5xx | cross total | cross 5xx |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for w in ("12h", "24h"):
        n = s5[w]["npm"]; p = s5[w]["pypi"]; c = s5[w]["cross"]
        lines.append(
            f"| {w} | {n['total']:,} | {n['5xx']} | "
            f"{p['total']:,} | {p['5xx']} | "
            f"{c['total']:,} | {c['5xx']} |"
        )
    lines += [
        "",
        "## Whole-site 5xx (12h context)",
        "",
        f"- Total requests: {obs['whole_12h_total']:,}",
        f"- 5xx count: {obs['whole_12h_5xx']}",
        f"- 5xx rate: {whole_rate:.4f}%",
        "",
        "## AI-bot crawls + citations — canary cohort",
        "",
        "| Window | npm bots | pypi bots | cross bots | npm cites | pypi cites | cross cites |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for w in ("12h", "24h", "7d"):
        lines.append(
            f"| {w} | {ai[w]['npm']:,} | {ai[w]['pypi']:,} | {ai[w]['cross']:,} "
            f"| {ci[w]['npm']:,} | {ci[w]['pypi']:,} | {ci[w]['cross']:,} |"
        )
    lines += [
        "",
        "## Green criteria (48h gate)",
        "",
        "- every post-T0 observation window must show 0 canary-cohort 5xx",
        "- whole-site 12h 5xx rate must stay below 0.2% in every window",
        "- latest 12h window must show non-zero /compare/ canary traffic",
        "- >= 4 observation rows in the post-T0 JSONL (proves 12h cadence ran)",
        "",
        "See `smedjan/scripts/emit_evidence.py::_evaluate_48h_green` for the",
        "exact gate logic. When all conditions hold at T+48h, the next",
        "`python -m smedjan.scripts.emit_evidence --signal l1b_canary_48h_green`",
        "emits the signal and auto-unpauses the F3 audit category.",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="gather + render; skip JSONL append")
    args = ap.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    cohort = load_cohort()
    log.info("loaded %d canary pairs from %s", len(cohort), PAIRS_JSON)

    obs = gather(cohort)
    md = render(obs)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = REPORT_DIR / f"L1b-canary-obs-{ts}.md"
    md_path.write_text(md)
    log.info("wrote %s (%d bytes)", md_path, md_path.stat().st_size)

    if not args.dry_run:
        jsonl = REPORT_DIR / "L1b-canary-observations.jsonl"
        with jsonl.open("a") as fh:
            fh.write(json.dumps({"ts": ts, "obs": obs}, default=str) + "\n")
        log.info("appended observation row to %s", jsonl.name)

        # After writing the latest observation, ask emit_evidence to
        # re-evaluate. Before T+48h this is a no-op that prints "NOT green
        # ... 48h gate not met". At the first tick past T+48h with clean
        # windows it auto-emits l1b_canary_48h_green and the F3 pause
        # flag is cleared on the next factory_core.resolve tick.
        try:
            from smedjan.scripts import emit_evidence as _ee
            _ee.run(signal="l1b_canary_48h_green", dry_run=False)
        except Exception as e:  # noqa: BLE001 — observer must never fail because of the emitter
            log.warning("emit_evidence chain skipped: %s", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
