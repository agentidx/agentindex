"""T351 manual post-fix F3-v3 audit — verify the canary-cohort filter.

Runs the same sampling path the updated F3-v3 template prescribes: resolve
L1B_COMPARE_UNLOCK_REGISTRIES from the running plist, filter the top-demand
slug list against Nerq entity_lookup.source ∈ that canary set, enumerate
pairs across the surviving canary slugs, HEAD /compare/<a>-vs-<b>, keep the
first 50 that return 200.

Writes the sampled URLs + per-pair registry metadata to
~/smedjan/audits/T351-verify-F3v3-canary-filter.sampled_urls.jsonl so the
task-result block can reference it.  The ACCEPTANCE gate: every JSONL row
must carry (registry_a, registry_b) both inside the resolved canary set.
"""
from __future__ import annotations

import glob
import json
import os
import plistlib
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

sys.path.insert(0, "/Users/anstudio/agentindex")

from smedjan import sources  # noqa: E402

TASK_ID = "T351-verify-F3v3-canary-filter"
OUT_JSONL = Path(f"/Users/anstudio/smedjan/audits/{TASK_ID}.sampled_urls.jsonl")
OUT_MD = Path(f"/Users/anstudio/smedjan/audits/{TASK_ID}.md")
PRIOR_GLOB = "/Users/anstudio/smedjan/audits/FB-F3-*.sampled_urls.jsonl"

TARGET_SAMPLE = 50
TOP_SLUGS_PER_REGISTRY = 100
DEMAND_POOL = 3000
MAX_CANDIDATE_PAIRS = 800
MAX_HEAD_PROBES = 400
EXCLUDE_SLUGS = {"test"}
USER_AGENT = f"smedjan-audit/1.0 (+{TASK_ID})"
BASE = "https://nerq.ai"
RANDOM_SEED = 351202604230

PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.nerq.api.plist"
ENV_KEY = "L1B_COMPARE_UNLOCK_REGISTRIES"
FALLBACK_CANARY = "npm,pypi"


def resolve_canary_registries() -> list[str]:
    """Read L1B_COMPARE_UNLOCK_REGISTRIES from the running plist.  Fall back
    to 'npm,pypi' only if the plist read fails — the plist is the source
    of truth so a canary expansion just works without a template edit.
    """
    raw: str | None = None
    try:
        with PLIST_PATH.open("rb") as fh:
            data = plistlib.load(fh)
        env = data.get("EnvironmentVariables") or {}
        raw = env.get(ENV_KEY)
    except Exception as exc:  # noqa: BLE001
        print(f"[{TASK_ID}] plist read failed: {exc}; using fallback", file=sys.stderr)
    if not raw:
        raw = FALLBACK_CANARY
    out = [s.strip().lower() for s in raw.split(",") if s.strip()]
    return out


def load_prior_sampled_urls() -> set[str]:
    cutoff = time.time() - 7 * 86400
    seen: set[str] = set()
    for path in glob.glob(PRIOR_GLOB):
        try:
            if Path(path).stat().st_mtime < cutoff:
                continue
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    url = rec.get("url")
                    if url:
                        seen.add(url)
        except OSError:
            continue
    return seen


def fetch_canary_top_slugs(canary: list[str]) -> dict[str, list[str]]:
    """Top-100 demand slugs per registry, restricted to canary registries."""
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(
            "SELECT slug, score FROM smedjan.ai_demand_scores "
            "WHERE slug IS NOT NULL AND slug <> '' AND score IS NOT NULL "
            "AND slug <> ALL(%s) "
            "ORDER BY score DESC LIMIT %s",
            (list(EXCLUDE_SLUGS), DEMAND_POOL),
        )
        demand = {slug: float(score) for slug, score in cur.fetchall()}
    if not demand:
        return {}

    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT DISTINCT slug, source FROM entity_lookup "
            "WHERE slug = ANY(%s) AND source IS NOT NULL AND source = ANY(%s)",
            (list(demand.keys()), canary),
        )
        pairs = cur.fetchall()

    by_reg: dict[str, list[tuple[str, float]]] = {}
    for slug, source in pairs:
        if slug in EXCLUDE_SLUGS:
            continue
        by_reg.setdefault(source, []).append((slug, demand.get(slug, 0.0)))

    out: dict[str, list[str]] = {}
    for reg, lst in by_reg.items():
        lst.sort(key=lambda x: x[1], reverse=True)
        out[reg] = [s for s, _ in lst[:TOP_SLUGS_PER_REGISTRY]]
    return out


def enumerate_candidate_pairs(
    by_reg: dict[str, list[str]], excluded: set[str]
) -> list[tuple[str, str, str, str]]:
    """Return (url, slug_a, slug_b, pair_type) tuples.  pair_type is
    'intra-<reg>' for same-registry pairs and 'cross-<regA>-<regB>' for
    cross-registry pairs.
    """
    out: dict[str, tuple[str, str, str, str]] = {}
    regs = sorted(by_reg.keys())
    # Intra-registry pairs
    for reg in regs:
        for a, b in combinations(by_reg[reg], 2):
            if a in EXCLUDE_SLUGS or b in EXCLUDE_SLUGS or a == b:
                continue
            x, y = sorted([a, b])
            url = f"{BASE}/compare/{x}-vs-{y}"
            if url in excluded:
                continue
            out.setdefault(url, (url, x, y, f"intra-{reg}"))
    # Cross-registry pairs
    for i, ra in enumerate(regs):
        for rb in regs[i + 1 :]:
            for a in by_reg[ra]:
                for b in by_reg[rb]:
                    if a in EXCLUDE_SLUGS or b in EXCLUDE_SLUGS or a == b:
                        continue
                    x, y = sorted([a, b])
                    url = f"{BASE}/compare/{x}-vs-{y}"
                    if url in excluded:
                        continue
                    tag = "-".join(sorted([ra, rb]))
                    out.setdefault(url, (url, x, y, f"cross-{tag}"))
    pool = list(out.values())
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(pool)
    return pool[:MAX_CANDIDATE_PAIRS]


def resolve_slug_sources(slugs: set[str], canary: list[str]) -> dict[str, str]:
    """Look up entity_lookup.source for each slug so we can stamp
    (registry_a, registry_b) on every sampled row.  A slug can live in
    multiple registries (e.g. 'react' exists in both npm and github); we
    always prefer the canary registry membership when resolving because
    that is why the slug landed in the sample pool.
    """
    if not slugs:
        return {}
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT DISTINCT slug, source FROM entity_lookup "
            "WHERE slug = ANY(%s) AND source IS NOT NULL",
            (list(slugs),),
        )
        rows = cur.fetchall()
    canary_set = set(canary)
    by_slug: dict[str, list[str]] = {}
    for slug, source in rows:
        by_slug.setdefault(slug, []).append(source)
    out: dict[str, str] = {}
    for slug, sources_list in by_slug.items():
        canary_hits = [s for s in sources_list if s in canary_set]
        if canary_hits:
            out[slug] = canary_hits[0]
        else:
            out[slug] = sources_list[0]
    return out


def curl_head(url: str) -> str:
    try:
        out = subprocess.run(
            [
                "curl", "-s", "-I",
                "-o", "/dev/null",
                "-w", "%{http_code}",
                "--max-time", "15",
                "-A", USER_AGENT,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return out.stdout.strip() or "000"
    except Exception:
        return "000"


def main() -> int:
    canary = resolve_canary_registries()
    print(f"[{TASK_ID}] canary_registries = {canary}")

    excluded = load_prior_sampled_urls()
    print(f"[{TASK_ID}] prior-7d exclusion size = {len(excluded)}")

    by_reg = fetch_canary_top_slugs(canary)
    print(f"[{TASK_ID}] canary registries with slugs: {sorted(by_reg.keys())}")
    for reg, slugs in sorted(by_reg.items()):
        print(f"[{TASK_ID}]   {reg}: {len(slugs)} slugs")

    if any(reg not in canary for reg in by_reg):
        print(f"[{TASK_ID}] FATAL: sampler produced non-canary registry", file=sys.stderr)
        return 2

    candidates = enumerate_candidate_pairs(by_reg, excluded)
    print(f"[{TASK_ID}] candidate pairs after dedup/exclusion: {len(candidates)}")

    all_slugs: set[str] = set()
    for _url, a, b, _tag in candidates:
        all_slugs.add(a)
        all_slugs.add(b)
    slug_to_source = resolve_slug_sources(all_slugs, canary)

    rows: list[dict] = []
    probes = 0
    for url, a, b, pair_type in candidates:
        if len(rows) >= TARGET_SAMPLE or probes >= MAX_HEAD_PROBES:
            break
        probes += 1
        status = curl_head(url)
        if status != "200":
            continue
        registry_a = slug_to_source.get(a, "<unknown>")
        registry_b = slug_to_source.get(b, "<unknown>")
        rows.append({
            "url": url,
            "slug_a": a,
            "slug_b": b,
            "registry_a": registry_a,
            "registry_b": registry_b,
            "pair_type": pair_type,
            "canary_registries": canary,
            "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    in_cohort = sum(
        1 for r in rows
        if r["registry_a"] in canary and r["registry_b"] in canary
    )
    out_of_cohort = [r for r in rows if r["registry_a"] not in canary or r["registry_b"] not in canary]

    with OUT_MD.open("w") as fh:
        fh.write(f"# {TASK_ID} — F3-v3 canary-filter verification\n\n")
        fh.write(f"- canary_registries: **{canary}**\n")
        fh.write(f"- pages_audited (HTTP 200): **{len(rows)} / {TARGET_SAMPLE}**\n")
        fh.write(f"- HEAD probes used: **{probes} / {MAX_HEAD_PROBES}**\n")
        fh.write(f"- in_canary_cohort: **{in_cohort} / {len(rows)}**\n")
        fh.write(f"- out_of_cohort leaks: **{len(out_of_cohort)}**\n\n")
        fh.write("## Sampled URLs\n\n")
        fh.write("| url | registry_a | registry_b | pair_type |\n")
        fh.write("|-----|------------|------------|-----------|\n")
        for r in rows:
            fh.write(f"| {r['url']} | {r['registry_a']} | {r['registry_b']} | {r['pair_type']} |\n")

    print(f"[{TASK_ID}] wrote {len(rows)} rows to {OUT_JSONL}")
    print(f"[{TASK_ID}] in_cohort={in_cohort}/{len(rows)}, leaks={len(out_of_cohort)}")
    if out_of_cohort:
        print(f"[{TASK_ID}] FAIL: cohort leak detected", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
