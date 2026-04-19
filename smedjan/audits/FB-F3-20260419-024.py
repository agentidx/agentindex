"""Quality audit of 50 existing /compare/<a>-vs-<b> pages (FB-F3-20260419-024).

Replaces the coverage-proposal pattern used by prior F3 audits (which always
emitted 100% 'skip' because top-demand pairs already ship). Instead this task
grades the HTML of existing pages to surface structural regressions.

Sampling pool is built by:
  1. Top 100 demand slugs per Nerq registry (smedjan.ai_demand_scores joined
     to entity_lookup.source, excluding 'test').
  2. All intra-registry pairs of those slugs, collapsed across registries.
  3. Randomised, then HEAD-probed; first 50 that return 200 are retained.
  4. Prior-7-day sampled URLs (FB-F3-*.sampled_urls.jsonl) are excluded.

For each sampled page curl the full HTML and extract:
  has_king_sections, has_pplx_verdict, has_ai_summary, has_faq_jsonld,
  word_count, number_tokens, data_density, last_enriched_at, staleness_days.

Outputs:
  ~/smedjan/audits/FB-F3-20260419-024.md
  ~/smedjan/audits/FB-F3-20260419-024.sampled_urls.jsonl
"""
from __future__ import annotations

import glob
import json
import random
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

sys.path.insert(0, "/Users/anstudio/agentindex")

from smedjan import sources  # noqa: E402

AUDIT_ID = "FB-F3-20260419-024"
AUDIT_DIR = Path("/Users/anstudio/smedjan/audits")
OUT_MD = AUDIT_DIR / f"{AUDIT_ID}.md"
OUT_JSONL = AUDIT_DIR / f"{AUDIT_ID}.sampled_urls.jsonl"
PRIOR_JSONL_GLOB = str(AUDIT_DIR / "FB-F3-*.sampled_urls.jsonl")

TOP_SLUGS_PER_REGISTRY = 100
TARGET_SAMPLE = 50
HEAD_PROBE_CAP = 400  # never probe more than this many candidates
EXCLUDE_SLUGS = {"test"}
USER_AGENT = f"smedjan-audit/1.0 (+{AUDIT_ID})"
RANDOM_SEED = 20260419024

# Escalation thresholds
MIN_WORD_COUNT = 200
MIN_DATA_DENSITY = 2.0
MAX_STALENESS_DAYS = 60


def load_prior_sampled_urls() -> set[str]:
    urls: set[str] = set()
    now = datetime.now(timezone.utc).timestamp()
    seven_days = 7 * 86400
    for path in glob.glob(PRIOR_JSONL_GLOB):
        try:
            mtime = Path(path).stat().st_mtime
        except OSError:
            continue
        if now - mtime > seven_days:
            continue
        try:
            for line in Path(path).read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                u = obj.get("url")
                if isinstance(u, str):
                    urls.add(u)
        except OSError:
            continue
    return urls


def fetch_top_slugs_per_registry() -> dict[str, list[str]]:
    # pull top demand slugs — we over-fetch to give the per-registry filter
    # plenty of candidates
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(
            "SELECT slug, score FROM smedjan.ai_demand_scores "
            "WHERE slug IS NOT NULL AND slug <> '' AND score IS NOT NULL "
            "AND slug <> ALL(%s) "
            "ORDER BY score DESC LIMIT %s",
            (list(EXCLUDE_SLUGS), 20000),
        )
        demand = {slug: float(score) for slug, score in cur.fetchall()}
    if not demand:
        return {}
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT DISTINCT slug, source FROM entity_lookup "
            "WHERE slug = ANY(%s) AND source IS NOT NULL",
            (list(demand.keys()),),
        )
        rows = cur.fetchall()
    per_reg: dict[str, list[tuple[str, float]]] = {}
    for slug, source in rows:
        per_reg.setdefault(source, []).append((slug, demand[slug]))
    out: dict[str, list[str]] = {}
    for reg, lst in per_reg.items():
        lst.sort(key=lambda x: x[1], reverse=True)
        out[reg] = [s for s, _ in lst[:TOP_SLUGS_PER_REGISTRY]]
    return out


def build_candidate_pool(
    per_reg: dict[str, list[str]], exclude_urls: set[str]
) -> list[tuple[str, str, str]]:
    """Return a shuffled list of (registry, slug_a, slug_b) candidates."""
    seen: dict[tuple[str, str], str] = {}
    for reg, slugs in per_reg.items():
        for a, b in combinations(slugs, 2):
            x, y = sorted([a, b])
            key = (x, y)
            if key in seen:
                continue
            url = f"https://nerq.ai/compare/{x}-vs-{y}"
            if url in exclude_urls:
                continue
            seen[key] = reg
    pool = [(reg, x, y) for (x, y), reg in seen.items()]
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(pool)
    return pool


def curl_head(url: str) -> str:
    try:
        out = subprocess.run(
            [
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "-I",
                "--max-time",
                "15",
                "-A",
                USER_AGENT,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return out.stdout.strip() or "000"
    except Exception:
        return "000"


def curl_body(url: str) -> str | None:
    try:
        out = subprocess.run(
            [
                "curl",
                "-s",
                "--max-time",
                "25",
                "-A",
                USER_AGENT,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return out.stdout
    except Exception:
        return None


# --- HTML extractors ---------------------------------------------------------
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_BODY_RE = re.compile(r"<body\b[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_KING_ROW_LABELS = ("Security", "Maintenance", "Popularity", "Quality", "Community")


def _body_text(html: str) -> str:
    m = _BODY_RE.search(html)
    body = m.group(1) if m else html
    body = _SCRIPT_RE.sub(" ", body)
    body = _STYLE_RE.sub(" ", body)
    body = _TAG_RE.sub(" ", body)
    # collapse whitespace
    return re.sub(r"\s+", " ", body).strip()


def _has_king_sections(html: str) -> bool:
    if "Detailed Score Analysis" in html:
        return True
    # otherwise look for all five canonical row labels inside a <table> block
    for table_match in re.finditer(
        r"<table\b[^>]*>(.*?)</table>", html, re.IGNORECASE | re.DOTALL
    ):
        block = table_match.group(1)
        if all(label in block for label in _KING_ROW_LABELS):
            return True
    return False


def _has_faq_jsonld(html: str) -> bool:
    for m in _JSONLD_RE.finditer(html):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if isinstance(obj, dict) and obj.get("@type") == "FAQPage":
                return True
    return False


def extract_features(html: str) -> dict:
    text = _body_text(html)
    words = _WORD_RE.findall(text)
    numbers = _NUM_RE.findall(text)
    wc = len(words)
    nc = len(numbers)
    density = (nc / wc * 1000.0) if wc else 0.0
    return {
        "has_king_sections": _has_king_sections(html),
        "has_pplx_verdict": '<p class="pplx-verdict"' in html,
        "has_ai_summary": '<p class="ai-summary"' in html,
        "has_faq_jsonld": _has_faq_jsonld(html),
        "word_count": wc,
        "number_tokens": nc,
        "data_density": round(density, 2),
    }


def fetch_enrichment_map(slugs: set[str]) -> dict[str, datetime]:
    if not slugs:
        return {}
    out: dict[str, datetime] = {}
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT slug, MAX(enriched_at) FROM software_registry "
            "WHERE slug = ANY(%s) AND enriched_at IS NOT NULL "
            "GROUP BY slug",
            (list(slugs),),
        )
        for slug, ts in cur.fetchall():
            if ts is not None:
                out[slug] = ts
    return out


def iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat()


# --- main --------------------------------------------------------------------


def main() -> int:
    prior = load_prior_sampled_urls()
    per_reg = fetch_top_slugs_per_registry()
    if not per_reg:
        print("no registry data", file=sys.stderr)
        return 1
    pool = build_candidate_pool(per_reg, prior)
    if len(pool) < TARGET_SAMPLE:
        print(f"candidate pool too small: {len(pool)}", file=sys.stderr)
        return 1

    probe_budget = min(HEAD_PROBE_CAP, len(pool))
    hits: list[tuple[str, str, str]] = []
    probed = 0
    for reg, a, b in pool[:probe_budget]:
        if len(hits) >= TARGET_SAMPLE:
            break
        url = f"https://nerq.ai/compare/{a}-vs-{b}"
        probed += 1
        if curl_head(url) == "200":
            hits.append((reg, a, b))
    if len(hits) < TARGET_SAMPLE:
        print(
            f"only {len(hits)}/{TARGET_SAMPLE} hits after {probed} probes",
            file=sys.stderr,
        )
        return 1

    # Fetch enrichment once for all slugs touched
    all_slugs: set[str] = set()
    for _, a, b in hits:
        all_slugs.add(a)
        all_slugs.add(b)
    enrich = fetch_enrichment_map(all_slugs)
    now = datetime.now(timezone.utc)

    rows: list[dict] = []
    for reg, a, b in hits:
        url = f"https://nerq.ai/compare/{a}-vs-{b}"
        html = curl_body(url) or ""
        feats = extract_features(html)
        ts_a = enrich.get(a)
        ts_b = enrich.get(b)
        last_ts = None
        if ts_a and ts_b:
            last_ts = max(ts_a, ts_b)
        else:
            last_ts = ts_a or ts_b
        if last_ts is not None and last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        staleness = (
            int((now - last_ts).total_seconds() // 86400)
            if last_ts is not None
            else None
        )
        rows.append(
            {
                "url": url,
                "registry": reg,
                "slug_a": a,
                "slug_b": b,
                **feats,
                "last_enriched_at": iso(last_ts),
                "staleness_days": staleness,
            }
        )

    # --- JSONL output (schema exactly as specified in the task) --------------
    jsonl_lines = []
    for r in rows:
        jsonl_lines.append(
            json.dumps(
                {
                    "url": r["url"],
                    "has_king_sections": r["has_king_sections"],
                    "has_pplx_verdict": r["has_pplx_verdict"],
                    "has_ai_summary": r["has_ai_summary"],
                    "has_faq_jsonld": r["has_faq_jsonld"],
                    "word_count": r["word_count"],
                    "number_tokens": r["number_tokens"],
                    "data_density": r["data_density"],
                    "last_enriched_at": r["last_enriched_at"],
                    "staleness_days": r["staleness_days"],
                }
            )
        )
    OUT_JSONL.write_text("\n".join(jsonl_lines) + "\n")

    # --- summary stats -------------------------------------------------------
    wcs = [r["word_count"] for r in rows]
    densities = [r["data_density"] for r in rows]
    stales = [r["staleness_days"] for r in rows if r["staleness_days"] is not None]

    def q(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        v = sorted(values)
        k = max(0, min(len(v) - 1, int(round((len(v) - 1) * pct))))
        return float(v[k])

    p25_wc = q(wcs, 0.25)
    p50_wc = q(wcs, 0.50)
    p75_wc = q(wcs, 0.75)
    p50_density = q(densities, 0.50)
    p50_stale = q([float(s) for s in stales], 0.50) if stales else 0.0
    very_stale = sum(1 for s in stales if s > 30)
    missing_king = sum(1 for r in rows if not r["has_king_sections"])
    missing_pplx = sum(1 for r in rows if not r["has_pplx_verdict"])
    missing_ai_summary = sum(1 for r in rows if not r["has_ai_summary"])
    missing_faq = sum(1 for r in rows if not r["has_faq_jsonld"])

    def on_escalation(r: dict) -> list[str]:
        reasons: list[str] = []
        if not r["has_king_sections"]:
            reasons.append("no_king")
        if not r["has_pplx_verdict"]:
            reasons.append("no_pplx")
        if not r["has_ai_summary"]:
            reasons.append("no_ai_summary")
        if not r["has_faq_jsonld"]:
            reasons.append("no_faq")
        if r["word_count"] < MIN_WORD_COUNT:
            reasons.append(f"wc<{MIN_WORD_COUNT}")
        if r["data_density"] < MIN_DATA_DENSITY:
            reasons.append(f"density<{MIN_DATA_DENSITY}")
        if (
            r["staleness_days"] is not None
            and r["staleness_days"] > MAX_STALENESS_DAYS
        ):
            reasons.append(f"stale>{MAX_STALENESS_DAYS}d")
        return reasons

    escalation = [(r, on_escalation(r)) for r in rows]
    escalation_hits = [e for e in escalation if e[1]]
    escalation_count = len(escalation_hits)

    # --- markdown output -----------------------------------------------------
    lines: list[str] = []
    lines.append(f"# {AUDIT_ID} /compare/ quality audit (50 existing pages)")
    lines.append("")
    lines.append(
        "HTML-level audit of 50 randomly-sampled EXISTING /compare/ pages on "
        "nerq.ai. Previous F3 audits produced 100% 'skip' output because the "
        "top-demand pairs already ship — this task instead grades those pages "
        "against the sacred-bytes checklist (king-sections table, "
        "`<p class=\"pplx-verdict\">`, `<p class=\"ai-summary\">`, FAQPage "
        "JSON-LD) and measures body depth via word count and numeric-token "
        "density. Enrichment age is taken as `max(enriched_at)` over the two "
        "slugs from `software_registry`."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- pages_audited: **{len(rows)}**")
    lines.append(
        f"- missing king-sections: **{missing_king}** / {len(rows)}"
    )
    lines.append(
        f"- missing `<p class=\"pplx-verdict\">`: **{missing_pplx}** / {len(rows)}"
    )
    lines.append(
        f"- missing `<p class=\"ai-summary\">`: **{missing_ai_summary}** / {len(rows)}"
    )
    lines.append(
        f"- missing FAQPage JSON-LD: **{missing_faq}** / {len(rows)}"
    )
    lines.append(
        f"- word_count p25/p50/p75: **{int(p25_wc)} / {int(p50_wc)} / {int(p75_wc)}**"
    )
    lines.append(f"- data_density p50 (numbers per 1k words): **{p50_density:.2f}**")
    lines.append(
        f"- staleness_days p50: **{int(p50_stale)}** "
        f"(pages with staleness > 30d: **{very_stale}**)"
    )
    lines.append(f"- escalation_count: **{escalation_count}** / {len(rows)}")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines.append(
        "| url | king | pplx | ai_sum | faq | words | nums | density | stale_d |"
    )
    lines.append(
        "|-----|:----:|:----:|:------:|:---:|------:|-----:|--------:|--------:|"
    )

    def b(x: bool) -> str:
        return "Y" if x else "N"

    for r in rows:
        stale_s = (
            str(r["staleness_days"]) if r["staleness_days"] is not None else "n/a"
        )
        lines.append(
            f"| `{r['url']}` "
            f"| {b(r['has_king_sections'])} "
            f"| {b(r['has_pplx_verdict'])} "
            f"| {b(r['has_ai_summary'])} "
            f"| {b(r['has_faq_jsonld'])} "
            f"| {r['word_count']} "
            f"| {r['number_tokens']} "
            f"| {r['data_density']:.2f} "
            f"| {stale_s} |"
        )

    lines.append("")
    lines.append("## Escalation list")
    lines.append("")
    lines.append(
        "Pages that fail at least one of: missing king-sections, missing "
        "`<p class=\"pplx-verdict\">`, missing `<p class=\"ai-summary\">`, "
        f"missing FAQ JSON-LD, word_count < {MIN_WORD_COUNT}, "
        f"data_density < {MIN_DATA_DENSITY}, staleness > {MAX_STALENESS_DAYS}d."
    )
    lines.append("")
    if escalation_hits:
        lines.append("| url | reasons |")
        lines.append("|-----|---------|")
        for r, reasons in escalation_hits:
            lines.append(f"| `{r['url']}` | {', '.join(reasons)} |")
    else:
        lines.append("_None — all 50 sampled pages pass every gate._")
    lines.append("")

    OUT_MD.write_text("\n".join(lines))

    evidence = {
        "pages_audited": len(rows),
        "escalation_count": escalation_count,
        "p50_data_density": p50_density,
        "p50_staleness_days": int(p50_stale) if stales else None,
        "missing_king_sections": missing_king,
        "missing_pplx_verdict": missing_pplx,
        "missing_ai_summary": missing_ai_summary,
        "missing_faq_jsonld": missing_faq,
        "word_count_p25": int(p25_wc),
        "word_count_p50": int(p50_wc),
        "word_count_p75": int(p75_wc),
        "probed": probed,
        "candidate_pool_size": len(pool),
        "outputs": [str(OUT_MD), str(OUT_JSONL)],
    }
    print(json.dumps(evidence))
    return 0


if __name__ == "__main__":
    sys.exit(main())
