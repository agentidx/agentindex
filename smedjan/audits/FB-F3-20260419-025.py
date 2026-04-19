"""HTML-level quality audit of EXISTING /compare/ pages (FB-F3-20260419-025).

Pivot from prior F3 audits which always returned 100% 'skip' because the
top-demand pairs already ship. This task instead grades 50 already-shipping
/compare/<a>-vs-<b> pages on whether they still carry the king sections,
the sacred bytes (pplx-verdict + ai-summary classes, in any tag),
the FAQ JSON-LD, and on body-text density.

Outputs:
  /Users/anstudio/smedjan/audits/FB-F3-20260419-025.md
  /Users/anstudio/smedjan/audits/FB-F3-20260419-025.sampled_urls.jsonl
"""
from __future__ import annotations

import json
import random
import re
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from itertools import combinations
from pathlib import Path

sys.path.insert(0, "/Users/anstudio/agentindex")

from smedjan import sources  # noqa: E402

AUDITS_DIR = Path("/Users/anstudio/smedjan/audits")
OUT_MD = AUDITS_DIR / "FB-F3-20260419-025.md"
OUT_JSONL = AUDITS_DIR / "FB-F3-20260419-025.sampled_urls.jsonl"

TOP_SLUGS_FETCH = 4000
TOP_SLUGS_PER_REGISTRY = 100
TARGET_SAMPLE = 50
CANDIDATE_POOL_SIZE = 220  # HEAD probes; need ~50 200s
EXCLUDE_SLUGS = {"test"}
USER_AGENT = "smedjan-audit/1.0 (+FB-F3-20260419-025)"
DEDUPE_WINDOW_DAYS = 7
NOW = datetime(2026, 4, 19, tzinfo=timezone.utc)
RANDOM_SEED = 20260419025


# ---------- sampling ----------

def fetch_demand_scores(limit: int) -> dict[str, float]:
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(
            "SELECT slug, score FROM smedjan.ai_demand_scores "
            "WHERE slug IS NOT NULL AND slug <> '' AND score IS NOT NULL "
            "AND slug <> ALL(%s) "
            "ORDER BY score DESC LIMIT %s",
            (list(EXCLUDE_SLUGS), limit),
        )
        return {slug: float(score) for slug, score in cur.fetchall()}


def fetch_slug_registries(slugs: list[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT DISTINCT slug, source FROM entity_lookup "
            "WHERE slug = ANY(%s) AND source IS NOT NULL",
            (slugs,),
        )
        for slug, source in cur.fetchall():
            out.setdefault(slug, set()).add(source)
    return out


def load_recent_sampled_urls() -> set[str]:
    """Read prior FB-F3-*.sampled_urls.jsonl files newer than 7 days."""
    cutoff = NOW.timestamp() - DEDUPE_WINDOW_DAYS * 86400
    seen: set[str] = set()
    for p in AUDITS_DIR.glob("FB-F3-*.sampled_urls.jsonl"):
        try:
            if p.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        try:
            for line in p.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                url = obj.get("url")
                if isinstance(url, str):
                    seen.add(url)
        except OSError:
            continue
    return seen


def build_candidate_urls(
    by_registry: dict[str, list[tuple[str, float]]],
    excluded_urls: set[str],
    rng: random.Random,
) -> list[str]:
    pairs: set[tuple[str, str]] = set()
    for slugs in by_registry.values():
        names = [s for s, _ in slugs]
        for a, b in combinations(names, 2):
            x, y = sorted([a, b])
            if x == y:
                continue
            pairs.add((x, y))
    candidates = [f"https://nerq.ai/compare/{a}-vs-{b}" for a, b in pairs]
    candidates = [u for u in candidates if u not in excluded_urls]
    rng.shuffle(candidates)
    return candidates[:CANDIDATE_POOL_SIZE]


def head_status(url: str) -> tuple[str, str]:
    try:
        r = subprocess.run(
            [
                "curl",
                "-sI",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
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
        return url, (r.stdout.strip() or "000")
    except Exception:
        return url, "000"


def select_200_urls(candidates: list[str], target: int) -> list[str]:
    """HEAD probe candidates concurrently and return first `target` 200s,
    preserving the candidate ordering so the deterministic shuffle controls
    selection."""
    seen_status: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(head_status, u) for u in candidates]
        for fut in as_completed(futures):
            u, s = fut.result()
            seen_status[u] = s
    out: list[str] = []
    for u in candidates:
        if seen_status.get(u) == "200":
            out.append(u)
            if len(out) >= target:
                break
    return out


# ---------- HTML extraction ----------

CLASS_RE_PPLX = re.compile(r"class\s*=\s*['\"][^'\"]*\bpplx-verdict\b", re.I)
CLASS_RE_AI = re.compile(r"class\s*=\s*['\"][^'\"]*\bai-summary\b", re.I)
DETAILED_HEADING_RE = re.compile(r"Detailed\s+Score\s+Analysis", re.I)
JSONLD_RE = re.compile(
    r"<script[^>]*type\s*=\s*['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
    re.I | re.S,
)
BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.I | re.S)
NUMBER_TOKEN_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
WORD_TOKEN_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
KING_TABLE_KEYS = ("security", "maintenance", "popularity", "quality", "community")


class _BodyTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth_skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._depth_skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._depth_skip > 0:
            self._depth_skip -= 1

    def handle_data(self, data: str) -> None:
        if self._depth_skip == 0 and data.strip():
            self.parts.append(data)


def fetch_html(url: str) -> str | None:
    try:
        r = subprocess.run(
            [
                "curl",
                "-s",
                "-L",
                "--max-time",
                "30",
                "-A",
                USER_AGENT,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=35,
        )
        if r.returncode != 0:
            return None
        return r.stdout
    except Exception:
        return None


def has_king_5dim_table(html: str) -> bool:
    if DETAILED_HEADING_RE.search(html):
        return True
    body_match = BODY_RE.search(html)
    body = body_match.group(1) if body_match else html
    text_lower = re.sub(r"<[^>]+>", " ", body).lower()
    return all(k in text_lower for k in KING_TABLE_KEYS)


def has_faq_jsonld(html: str) -> bool:
    for raw in JSONLD_RE.findall(html):
        try:
            obj = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue

        def _is_faq(o: object) -> bool:
            if isinstance(o, dict):
                t = o.get("@type")
                if t == "FAQPage" or (isinstance(t, list) and "FAQPage" in t):
                    return True
                return any(_is_faq(v) for v in o.values())
            if isinstance(o, list):
                return any(_is_faq(item) for item in o)
            return False

        if _is_faq(obj):
            return True
    return False


def body_text(html: str) -> str:
    body_match = BODY_RE.search(html)
    body = body_match.group(1) if body_match else html
    parser = _BodyTextExtractor()
    try:
        parser.feed(body)
    except Exception:
        pass
    return " ".join(parser.parts)


def extract_signals(url: str, html: str) -> dict:
    text = body_text(html)
    word_count = len(WORD_TOKEN_RE.findall(text))
    number_tokens = len(NUMBER_TOKEN_RE.findall(text))
    density = round((number_tokens / word_count) * 1000, 2) if word_count else 0.0
    return {
        "url": url,
        "has_king_sections": bool(has_king_5dim_table(html)),
        "has_pplx_verdict": bool(CLASS_RE_PPLX.search(html)),
        "has_ai_summary": bool(CLASS_RE_AI.search(html)),
        "has_faq_jsonld": has_faq_jsonld(html),
        "word_count": word_count,
        "number_tokens": number_tokens,
        "data_density": density,
    }


# ---------- enriched_at lookup ----------

def slug_from_url(url: str) -> tuple[str, str]:
    tail = url.rsplit("/compare/", 1)[-1]
    a, _, b = tail.partition("-vs-")
    return a, b


def fetch_enriched_at(slugs: set[str]) -> dict[str, datetime]:
    if not slugs:
        return {}
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT slug, MAX(enriched_at) FROM software_registry "
            "WHERE slug = ANY(%s) GROUP BY slug",
            (list(slugs),),
        )
        rows = cur.fetchall()
    out: dict[str, datetime] = {}
    for slug, ts in rows:
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        out[slug] = ts
    return out


# ---------- escalation logic ----------

def is_escalated(row: dict) -> bool:
    if not row["has_king_sections"]:
        return True
    if not row["has_pplx_verdict"]:
        return True
    if not row["has_ai_summary"]:
        return True
    if not row["has_faq_jsonld"]:
        return True
    if (row.get("word_count") or 0) < 200:
        return True
    if (row.get("data_density") or 0.0) < 2.0:
        return True
    sd = row.get("staleness_days")
    if sd is not None and sd > 60:
        return True
    return False


def fetch_one(url: str) -> dict | None:
    html = fetch_html(url)
    if not html:
        return None
    return extract_signals(url, html)


# ---------- output ----------

def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return float(s[f] + (s[c] - s[f]) * (k - f))


def render_md(rows: list[dict], escalated: list[dict], summary: dict) -> str:
    lines: list[str] = []
    lines.append(
        "# FB-F3-20260419-025 /compare/ HTML-quality audit (50 existing pages)"
    )
    lines.append("")
    lines.append(
        "Pivot from coverage proposals to a quality audit of pages that already "
        "ship. Sampling: top "
        f"{TOP_SLUGS_PER_REGISTRY} demand slugs per Nerq registry are intra-paired, "
        "shuffled (deterministic seed), HEAD-probed against `https://nerq.ai/compare/"
        "<a>-vs-<b>`, and the first 50 returning HTTP 200 are kept. Slug `test` is "
        f"excluded. URLs already sampled in any FB-F3-*.sampled_urls.jsonl from the "
        f"last {DEDUPE_WINDOW_DAYS} days are excluded as well."
    )
    lines.append("")
    lines.append(
        "Selectors note: `pplx-verdict` and `ai-summary` are matched by CSS class on "
        "any element (the live template emits `<div class=\"ai-summary\">`, not "
        "`<p>`). `has_king_sections` is True if the heading 'Detailed Score "
        "Analysis' is present OR the body contains all five dimension labels "
        "(security/maintenance/popularity/quality/community)."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- pages_audited: **{summary['pages_audited']}**")
    lines.append(f"- missing_king_sections: **{summary['missing_king_sections']}**")
    lines.append(
        f"- missing_pplx_verdict: **{summary['missing_pplx_verdict']}**  "
        f"(\"sacred bytes\" check)"
    )
    lines.append(
        f"- missing_ai_summary: **{summary['missing_ai_summary']}**  "
        f"(\"sacred bytes\" check)"
    )
    lines.append(f"- missing_faq_jsonld: **{summary['missing_faq_jsonld']}**")
    lines.append(
        f"- word_count distribution: p25={summary['word_p25']:.0f} "
        f"p50={summary['word_p50']:.0f} p75={summary['word_p75']:.0f}"
    )
    lines.append(
        f"- data_density p50: **{summary['density_p50']:.2f}** "
        f"(numbers per 1000 words; threshold 2.0)"
    )
    lines.append(
        f"- staleness_days p50: **{summary['stale_p50']:.0f}** "
        f"(software_registry.enriched_at), count(staleness > 30d): "
        f"**{summary['stale_over_30']}**"
    )
    lines.append(f"- escalation_count: **{summary['escalation_count']}** / 50")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines.append(
        "| url | king | pplx | ai | faq | words | nums | density | enriched_at | "
        "stale_d |"
    )
    lines.append(
        "|-----|:----:|:----:|:--:|:---:|------:|-----:|--------:|-------------|"
        "--------:|"
    )
    for r in rows:
        en = r.get("last_enriched_at") or ""
        sd = r.get("staleness_days")
        sd_s = "" if sd is None else str(sd)
        lines.append(
            "| {url} | {k} | {p} | {a} | {f} | {w} | {n} | {d:.2f} | {e} | {s} |".format(
                url=r["url"].replace("https://nerq.ai", ""),
                k="Y" if r["has_king_sections"] else "N",
                p="Y" if r["has_pplx_verdict"] else "N",
                a="Y" if r["has_ai_summary"] else "N",
                f="Y" if r["has_faq_jsonld"] else "N",
                w=r["word_count"],
                n=r["number_tokens"],
                d=r["data_density"],
                e=en[:10] if en else "",
                s=sd_s,
            )
        )
    lines.append("")
    lines.append("## Escalation list")
    lines.append("")
    if not escalated:
        lines.append("_No pages tripped any escalation rule._")
    else:
        lines.append(
            "Pages that fail one or more of: missing king_sections, missing "
            "pplx-verdict, missing ai-summary, missing FAQ JSON-LD, word_count<200, "
            "data_density<2, staleness>60d."
        )
        lines.append("")
        lines.append("| url | reasons |")
        lines.append("|-----|---------|")
        for r in escalated:
            reasons: list[str] = []
            if not r["has_king_sections"]:
                reasons.append("no_king")
            if not r["has_pplx_verdict"]:
                reasons.append("no_pplx_verdict")
            if not r["has_ai_summary"]:
                reasons.append("no_ai_summary")
            if not r["has_faq_jsonld"]:
                reasons.append("no_faq_jsonld")
            if (r.get("word_count") or 0) < 200:
                reasons.append(f"low_words({r['word_count']})")
            if (r.get("data_density") or 0.0) < 2.0:
                reasons.append(f"low_density({r['data_density']:.2f})")
            sd = r.get("staleness_days")
            if sd is not None and sd > 60:
                reasons.append(f"stale_{sd}d")
            lines.append(
                f"| {r['url'].replace('https://nerq.ai', '')} | {', '.join(reasons)} |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    rng = random.Random(RANDOM_SEED)

    demand = fetch_demand_scores(TOP_SLUGS_FETCH)
    if not demand:
        print("no demand scores", file=sys.stderr)
        return 1
    reg_map = fetch_slug_registries(list(demand.keys()))

    by_registry: dict[str, list[tuple[str, float]]] = {}
    for slug, registries in reg_map.items():
        for r in registries:
            by_registry.setdefault(r, []).append((slug, demand[slug]))
    for r in by_registry:
        by_registry[r].sort(key=lambda x: x[1], reverse=True)
        del by_registry[r][TOP_SLUGS_PER_REGISTRY:]

    excluded = load_recent_sampled_urls()
    candidates = build_candidate_urls(by_registry, excluded, rng)
    if len(candidates) < TARGET_SAMPLE:
        print(
            f"only {len(candidates)} candidates after dedupe; need {TARGET_SAMPLE}",
            file=sys.stderr,
        )
        return 2

    sampled_urls = select_200_urls(candidates, TARGET_SAMPLE)
    if len(sampled_urls) < TARGET_SAMPLE:
        print(
            f"only {len(sampled_urls)} 200-OK urls in pool of "
            f"{len(candidates)}; widening pool",
            file=sys.stderr,
        )
        # widen: take more candidates
        wider = build_candidate_urls(by_registry, excluded | set(sampled_urls), rng)
        more = select_200_urls(wider, TARGET_SAMPLE - len(sampled_urls))
        sampled_urls.extend(u for u in more if u not in sampled_urls)
        sampled_urls = sampled_urls[:TARGET_SAMPLE]

    if len(sampled_urls) < TARGET_SAMPLE:
        print(
            f"unable to find {TARGET_SAMPLE} 200-OK urls "
            f"(got {len(sampled_urls)})",
            file=sys.stderr,
        )
        return 3

    # fetch HTML in parallel
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_one, u): u for u in sampled_urls}
        for fut in as_completed(futures):
            r = fut.result()
            if r is not None:
                rows.append(r)

    if len(rows) < TARGET_SAMPLE:
        print(
            f"only fetched {len(rows)} HTML pages out of {len(sampled_urls)}",
            file=sys.stderr,
        )
        # try to top up with extra candidates
        extra_urls = [u for u in candidates if u not in {r["url"] for r in rows}][
            : TARGET_SAMPLE * 2
        ]
        with ThreadPoolExecutor(max_workers=8) as pool:
            for fut in as_completed({pool.submit(fetch_one, u): u for u in extra_urls}):
                r = fut.result()
                if r is None:
                    continue
                if r["url"] in {x["url"] for x in rows}:
                    continue
                rows.append(r)
                if len(rows) >= TARGET_SAMPLE:
                    break
        rows = rows[:TARGET_SAMPLE]

    if len(rows) != TARGET_SAMPLE:
        print(f"final row count {len(rows)} != {TARGET_SAMPLE}", file=sys.stderr)
        return 4

    # enriched_at lookup
    all_slugs: set[str] = set()
    for r in rows:
        a, b = slug_from_url(r["url"])
        if a:
            all_slugs.add(a)
        if b:
            all_slugs.add(b)
    en_map = fetch_enriched_at(all_slugs)
    for r in rows:
        a, b = slug_from_url(r["url"])
        ts_candidates = [t for t in (en_map.get(a), en_map.get(b)) if t]
        if ts_candidates:
            t = max(ts_candidates)
            r["last_enriched_at"] = t.isoformat()
            r["staleness_days"] = max(0, int((NOW - t).total_seconds() // 86400))
        else:
            r["last_enriched_at"] = None
            r["staleness_days"] = None

    # stable order — by url
    rows.sort(key=lambda r: r["url"])

    # summary stats
    word_counts = [r["word_count"] for r in rows]
    densities = [r["data_density"] for r in rows]
    stales = [r["staleness_days"] for r in rows if r.get("staleness_days") is not None]
    summary = {
        "pages_audited": len(rows),
        "missing_king_sections": sum(1 for r in rows if not r["has_king_sections"]),
        "missing_pplx_verdict": sum(1 for r in rows if not r["has_pplx_verdict"]),
        "missing_ai_summary": sum(1 for r in rows if not r["has_ai_summary"]),
        "missing_faq_jsonld": sum(1 for r in rows if not r["has_faq_jsonld"]),
        "word_p25": percentile(word_counts, 0.25),
        "word_p50": percentile(word_counts, 0.50),
        "word_p75": percentile(word_counts, 0.75),
        "density_p50": percentile(densities, 0.50),
        "stale_p50": percentile(stales, 0.50) if stales else 0.0,
        "stale_over_30": sum(1 for s in stales if s > 30),
    }
    escalated = [r for r in rows if is_escalated(r)]
    summary["escalation_count"] = len(escalated)

    # write JSONL
    AUDITS_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w") as f:
        for r in rows:
            f.write(
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
                + "\n"
            )

    OUT_MD.write_text(render_md(rows, escalated, summary))

    print(
        json.dumps(
            {
                "pages_audited": summary["pages_audited"],
                "escalation_count": summary["escalation_count"],
                "p50_data_density": round(summary["density_p50"], 2),
                "p50_staleness_days": int(summary["stale_p50"]),
                "missing_king_sections": summary["missing_king_sections"],
                "missing_pplx_verdict": summary["missing_pplx_verdict"],
                "missing_ai_summary": summary["missing_ai_summary"],
                "missing_faq_jsonld": summary["missing_faq_jsonld"],
                "outputs": [str(OUT_MD), str(OUT_JSONL)],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
