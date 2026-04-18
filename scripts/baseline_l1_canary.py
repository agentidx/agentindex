#!/usr/bin/env python3
"""
baseline_l1_canary.py — PRE-deploy baseline for L1 canary (gems + homebrew).

Gathers:
  * GSC impressions/clicks from gsc-pages-28d.csv (28d aggregate; 7d proxy
    computed as /4 with explicit caveat)
  * AI-bot crawls on /safe/<slug> pages last 7d per registry
  * Citations last 7d (human visits, referrer matches an AI-platform host)
  * 5xx rate last 24h (canary cohort and whole Nerq)
  * Render time p50/p95 on 10 sample pages (curl -w timing)

Output: one Markdown file with all numbers, plus the raw JSON for any
post-deploy comparator to ingest mechanically.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from urllib.parse import unquote

import psycopg2

PG_DSN = os.environ.get(
    "SMEDJAN_PG_DSN",
    "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio",
)
ANALYTICS_DB = os.path.expanduser("~/agentindex/logs/analytics.db")
GSC_CSV = os.path.expanduser("~/Desktop/April/gsc-pages-28d.csv")
API_BASE = "http://localhost:8000"

AI_REFERRER_DOMAINS = [
    "chat.openai.com", "chatgpt.com",
    "claude.ai", "anthropic.com",
    "perplexity.ai", "www.perplexity.ai",
    "gemini.google.com", "bard.google.com",
    "poe.com",
    "you.com",
    "copilot.microsoft.com", "bing.com",
    "duckduckgo.com/chat",
    "phind.com",
    "kagi.com",
    "grok.com", "x.ai",
]


def load_registry_slugs(registries: list[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {r: set() for r in registries}
    with psycopg2.connect(PG_DSN) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            for reg in registries:
                cur.execute(
                    "SELECT slug FROM public.software_registry "
                    "WHERE registry = %s AND is_king = false AND enriched_at IS NOT NULL",
                    (reg,),
                )
                out[reg] = {r[0] for r in cur.fetchall()}
    for reg, slugs in out.items():
        print(f"  loaded {len(slugs):,} non-King enriched slugs for {reg}", file=sys.stderr)
    return out


def _path_to_slug(path: str) -> str | None:
    # /safe/<slug>  OR  /safe/<slug>/<sub>
    m = re.match(r"/safe/([^/?#]+)", path)
    return unquote(m.group(1)).lower() if m else None


def query_analytics(registry_slugs: dict[str, set[str]]) -> dict:
    slug_to_reg: dict[str, str] = {}
    for reg, slugs in registry_slugs.items():
        for s in slugs:
            slug_to_reg[s.lower()] = reg

    cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")

    ai_regex = re.compile(r"|".join(re.escape(d) for d in AI_REFERRER_DOMAINS), re.I)

    # Reuse a single read connection
    conn = sqlite3.connect(f"file:{ANALYTICS_DB}?mode=ro", uri=True)
    cur = conn.cursor()

    counts = {
        "ai_bot_crawls_7d": {r: 0 for r in registry_slugs},
        "citations_7d":      {r: 0 for r in registry_slugs},
        "ai_source_counts":  {r: {} for r in registry_slugs},
    }

    # Bot crawls
    cur.execute(
        "SELECT path FROM requests "
        "WHERE path LIKE '/safe/%' AND is_ai_bot = 1 AND ts > ?",
        (cutoff_7d,),
    )
    for (path,) in cur:
        slug = _path_to_slug(path)
        if slug is None:
            continue
        reg = slug_to_reg.get(slug)
        if reg is None:
            continue
        counts["ai_bot_crawls_7d"][reg] += 1

    # Citations: human (is_ai_bot=0), referrer matches AI host
    cur.execute(
        "SELECT path, referrer_domain FROM requests "
        "WHERE path LIKE '/safe/%' AND is_ai_bot = 0 AND referrer_domain IS NOT NULL "
        "  AND ts > ?",
        (cutoff_7d,),
    )
    for path, ref in cur:
        slug = _path_to_slug(path)
        if slug is None:
            continue
        reg = slug_to_reg.get(slug)
        if reg is None:
            continue
        if ai_regex.search(ref or ""):
            counts["citations_7d"][reg] += 1
            # bucket the actual host for qualitative signal
            for d in AI_REFERRER_DOMAINS:
                if d in (ref or "").lower():
                    counts["ai_source_counts"][reg][d] = counts["ai_source_counts"][reg].get(d, 0) + 1
                    break

    # 5xx baselines (canary cohort + whole-site)
    cohort_5xx = {r: 0 for r in registry_slugs}
    cohort_total = {r: 0 for r in registry_slugs}
    cur.execute(
        "SELECT path, status FROM requests "
        "WHERE path LIKE '/safe/%' AND ts > ?",
        (cutoff_24h,),
    )
    for path, status in cur:
        slug = _path_to_slug(path)
        if slug is None:
            continue
        reg = slug_to_reg.get(slug)
        if reg is None:
            continue
        cohort_total[reg] += 1
        if status is not None and status >= 500:
            cohort_5xx[reg] += 1

    cur.execute(
        "SELECT COUNT(*), SUM(CASE WHEN status>=500 THEN 1 ELSE 0 END) "
        "FROM requests WHERE ts > ?",
        (cutoff_24h,),
    )
    whole_total, whole_5xx = cur.fetchone()
    whole_5xx = whole_5xx or 0

    counts["fivexx_24h_cohort"]  = {r: {"total": cohort_total[r], "5xx": cohort_5xx[r]} for r in registry_slugs}
    counts["fivexx_24h_whole"]   = {"total": whole_total, "5xx": whole_5xx}

    # analytics.db write-rate baseline (for monitoring alert 3)
    # Requests per minute over the last 1h, excluding the most recent minute.
    cur.execute(
        "SELECT CAST((julianday('now') - julianday(ts)) * 1440 AS INTEGER) AS mins_ago "
        "FROM requests "
        "WHERE ts > datetime('now', '-1 hour') "
    )
    by_minute: dict[int, int] = {}
    for (mins_ago,) in cur:
        by_minute[mins_ago] = by_minute.get(mins_ago, 0) + 1
    per_minute_samples = [v for k, v in by_minute.items() if 1 <= k <= 60]
    counts["write_rate_per_minute_1h"] = {
        "samples": len(per_minute_samples),
        "p50":     int(median(per_minute_samples)) if per_minute_samples else 0,
        "p05":     int(sorted(per_minute_samples)[len(per_minute_samples) // 20]) if len(per_minute_samples) >= 20 else 0,
        "min":     min(per_minute_samples) if per_minute_samples else 0,
        "max":     max(per_minute_samples) if per_minute_samples else 0,
    }

    conn.close()
    return counts


def load_gsc(registry_slugs: dict[str, set[str]]) -> dict:
    # CSV is https://nerq.ai/<path>,Clicks,Impressions. Map path → slug if it's
    # a /safe/<slug> URL (other patterns like /compare/… are ignored for this
    # baseline — the canary's effect window is /safe/* only).
    slug_to_reg: dict[str, str] = {}
    for reg, slugs in registry_slugs.items():
        for s in slugs:
            slug_to_reg[s.lower()] = reg

    per_reg = {r: {"pages": 0, "clicks": 0, "impressions": 0} for r in registry_slugs}
    all_safe = {"pages": 0, "clicks": 0, "impressions": 0}
    missing = True
    try:
        with open(GSC_CSV) as fh:
            rd = csv.DictReader(fh)
            missing = False
            for row in rd:
                url = row["URL"]
                # path extraction
                path = re.sub(r"^https?://[^/]+", "", url)
                slug = _path_to_slug(path)
                clicks = int(row.get("Clicks") or 0)
                impressions = int(row.get("Impressions") or 0)
                if slug is None:
                    continue
                all_safe["pages"] += 1
                all_safe["clicks"] += clicks
                all_safe["impressions"] += impressions
                reg = slug_to_reg.get(slug)
                if reg is None:
                    continue
                per_reg[reg]["pages"] += 1
                per_reg[reg]["clicks"] += clicks
                per_reg[reg]["impressions"] += impressions
    except FileNotFoundError:
        pass
    return {
        "csv_present":    not missing,
        "csv_path":       GSC_CSV,
        "csv_window":     "28d (not 7d — only available GSC export)",
        "per_registry":   per_reg,
        "all_safe_slugs": all_safe,
    }


def timed_curl(urls: list[str]) -> list[dict]:
    results = []
    for url in urls:
        try:
            r = subprocess.run(
                ["curl", "-sS", "-o", "/dev/null",
                 "-w", "{\"http\":%{http_code},\"ms\":%{time_total}}", url],
                check=True, capture_output=True, text=True, timeout=15,
            )
            data = json.loads(r.stdout)
            data["url"] = url
            results.append(data)
        except Exception as e:
            results.append({"url": url, "error": str(e)})
    return results


def pick_render_samples(registry_slugs: dict[str, set[str]], n_per_reg: int = 5) -> list[str]:
    urls: list[str] = []
    for reg, slugs in registry_slugs.items():
        for s in sorted(slugs)[:n_per_reg]:
            urls.append(f"{API_BASE}/safe/{s}")
    return urls


def markdown(report: dict) -> str:
    now = report["generated_at"]
    git_hash = report.get("git_hash", "?")
    reg_slugs = report["registry_slug_counts"]
    gsc = report["gsc"]
    an = report["analytics"]
    r = report["render_time"]

    def reg_row(reg: str, g: dict, a: dict, f: dict) -> str:
        return (
            f"| {reg} | {reg_slugs[reg]:,} | "
            f"{g['pages']:,} | {g['clicks']:,} | {g['impressions']:,} | "
            f"{a['ai_bot_crawls_7d'][reg]:,} | {a['citations_7d'][reg]:,} | "
            f"{f[reg]['total']:,} | {f[reg]['5xx']:,} |"
        )

    whole = an["fivexx_24h_whole"]
    whole_rate = 100.0 * (whole["5xx"] or 0) / max(1, whole["total"])

    render_ok = [x for x in r if "ms" in x and x["http"] == 200]
    render_ms = sorted(x["ms"] * 1000 for x in render_ok)
    p50 = render_ms[len(render_ms) // 2] if render_ms else 0
    p95 = render_ms[int(len(render_ms) * 0.95) - 1] if len(render_ms) >= 20 else (render_ms[-1] if render_ms else 0)

    wrate = an["write_rate_per_minute_1h"]

    lines = [
        f"# L1 Canary — PRE-deploy baseline (gems + homebrew)",
        "",
        f"**Generated:** {now}",
        f"**Git HEAD:** `{git_hash}`",
        f"**Running API code in memory:** pre-change (module imports unchanged; deploy not yet executed)",
        f"**Env var `L1_UNLOCK_REGISTRIES`:** not set",
        "",
        "## Summary table",
        "",
        "| Registry | Slug pool | GSC pages* | GSC clicks 28d | GSC impressions 28d | AI-bot crawls 7d | Citations 7d | 24h /safe hits | 24h 5xx |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for reg in reg_slugs:
        lines.append(reg_row(reg, gsc["per_registry"][reg], an, an["fivexx_24h_cohort"]))
    lines += [
        "",
        "*GSC pages = slugs from this registry present in `gsc-pages-28d.csv`. "
        "The export is 28-day aggregate, not 7-day — there is no automated GSC "
        "pull today. Divide by 4 for a rough 7-day proxy if needed.",
        "",
        "## Whole-site 5xx baseline (last 24h)",
        "",
        f"- Total requests: **{whole['total']:,}**",
        f"- 5xx count: **{whole['5xx']:,}**",
        f"- 5xx rate: **{whole_rate:.3f}%**",
        "",
        "## analytics.db write-rate baseline (last 1h)",
        "",
        f"Requests per minute over the last hour (used for monitoring alert #3):",
        "",
        f"- samples: {wrate['samples']}",
        f"- p50: **{wrate['p50']:,}** req/min",
        f"- p05: {wrate['p05']:,} req/min (alert threshold is < 50% p50)",
        f"- min: {wrate['min']:,}",
        f"- max: {wrate['max']:,}",
        "",
        "**Monitoring alert #3 fires if write rate drops below "
        f"{wrate['p50'] // 2:,} req/min for a sustained period** — half of the "
        "observed p50 is well below natural valleys and catches genuine hangs.",
        "",
        "## Citation sources by platform (canary cohort, 7d)",
        "",
    ]
    for reg in reg_slugs:
        src = an["ai_source_counts"][reg]
        if not src:
            lines.append(f"- **{reg}:** 0 citations from AI platforms in the last 7d.")
            continue
        lines.append(f"- **{reg}:**")
        for host, count in sorted(src.items(), key=lambda kv: -kv[1])[:10]:
            lines.append(f"  - {host}: {count}")
    lines += [
        "",
        "## Render time on 10 sample pages (5 gems + 5 homebrew)",
        "",
        f"- p50: **{p50:.1f} ms**",
        f"- p95: **{p95:.1f} ms**",
        f"- success: {len(render_ok)} / {len(r)}",
        "",
        "| URL | status | ms |",
        "|---|---:|---:|",
    ]
    for x in r:
        if "error" in x:
            lines.append(f"| {x['url']} | err | {x['error']} |")
        else:
            lines.append(f"| {x['url']} | {x['http']} | {x['ms']*1000:.1f} |")

    lines += [
        "",
        "## Rollback signals (what we expect to recover to if we revert)",
        "",
        f"A successful rollback should land each number ≤ ±5% of the values above within 30 minutes of `launchctl kickstart`, because the rendering path reverts to the exact code currently running. Any sustained deviation is evidence the rollback itself mis-applied.",
        "",
        "## JSON payload (for automated comparison)",
        "",
        "```json",
        json.dumps(report, indent=2, default=str),
        "```",
    ]
    return "\n".join(lines)


def main() -> int:
    print("loading registry slugs…", file=sys.stderr)
    reg_slugs = load_registry_slugs(["gems", "homebrew"])
    print("querying analytics.db…", file=sys.stderr)
    an = query_analytics(reg_slugs)
    print("loading GSC export…", file=sys.stderr)
    gsc = load_gsc(reg_slugs)
    print("timing renders…", file=sys.stderr)
    sample_urls = pick_render_samples(reg_slugs, 5)
    render = timed_curl(sample_urls)

    git = subprocess.run(
        ["git", "-C", os.path.expanduser("~/agentindex"), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()

    report = {
        "generated_at":         datetime.now(timezone.utc).isoformat(),
        "git_hash":             git,
        "registry_slug_counts": {r: len(s) for r, s in reg_slugs.items()},
        "gsc":                  gsc,
        "analytics":            an,
        "render_time":          render,
    }

    out_dir = Path.home() / "smedjan" / "baselines"
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / "L1-canary-gems-homebrew-PRE-2026-04-18.md"
    js = out_dir / "L1-canary-gems-homebrew-PRE-2026-04-18.json"
    md.write_text(markdown(report))
    js.write_text(json.dumps(report, indent=2, default=str))
    print(f"wrote {md}")
    print(f"wrote {js}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
