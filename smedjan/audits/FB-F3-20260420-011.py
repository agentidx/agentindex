"""HTML-level quality audit of 50 existing /compare/ pages (FB-F3-20260420-011).

Samples 50 random existing /compare/<a>-vs-<b> URLs that return HTTP 200,
pulls full HTML, and grades each page on the 'king sections' + sacred bytes.

Outputs:
  ~/smedjan/audits/FB-F3-20260420-011.md
  ~/smedjan/audits/FB-F3-20260420-011.sampled_urls.jsonl
"""
from __future__ import annotations

import glob
import json
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

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    BeautifulSoup = None  # type: ignore

TASK_ID = "FB-F3-20260420-011"
OUT_MD = Path(f"/Users/anstudio/smedjan/audits/{TASK_ID}.md")
OUT_JSONL = Path(f"/Users/anstudio/smedjan/audits/{TASK_ID}.sampled_urls.jsonl")
PRIOR_GLOB = "/Users/anstudio/smedjan/audits/FB-F3-*.sampled_urls.jsonl"

TARGET_SAMPLE = 50
TOP_SLUGS_PER_REGISTRY = 100
MAX_CANDIDATE_PAIRS = 800
MAX_HEAD_PROBES = 300
EXCLUDE_SLUGS = {"test"}
USER_AGENT = f"smedjan-audit/1.0 (+{TASK_ID})"
BASE = "https://nerq.ai"
RANDOM_SEED = 20260420011

WORD_COUNT_MIN = 200
DATA_DENSITY_MIN = 2.0
STALENESS_MAX_DAYS = 60


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


def fetch_top_slugs_per_registry() -> dict[str, list[str]]:
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(
            "SELECT slug, score FROM smedjan.ai_demand_scores "
            "WHERE slug IS NOT NULL AND slug <> '' AND score IS NOT NULL "
            "AND slug <> ALL(%s) "
            "ORDER BY score DESC LIMIT %s",
            (list(EXCLUDE_SLUGS), 3000),
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
) -> list[str]:
    urls: set[str] = set()
    for _reg, slugs in by_reg.items():
        for a, b in combinations(slugs, 2):
            if a in EXCLUDE_SLUGS or b in EXCLUDE_SLUGS:
                continue
            x, y = sorted([a, b])
            url = f"{BASE}/compare/{x}-vs-{y}"
            if url in excluded:
                continue
            urls.add(url)
    pool = list(urls)
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(pool)
    return pool[:MAX_CANDIDATE_PAIRS]


def curl_status(url: str) -> str:
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


def curl_html(url: str) -> str:
    try:
        out = subprocess.run(
            [
                "curl", "-s",
                "--max-time", "20",
                "-A", USER_AGENT,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=25,
        )
        return out.stdout or ""
    except Exception:
        return ""


FIVE_DIMS = ("Security", "Maintenance", "Popularity", "Quality", "Community")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
SLUGS_FROM_URL = re.compile(r"/compare/([^/]+?)-vs-([^/?#]+)")


def slugs_from_url(url: str) -> tuple[str, str] | None:
    m = SLUGS_FROM_URL.search(url)
    if not m:
        return None
    return m.group(1), m.group(2)


def detect_king_sections(html: str, body_text: str) -> bool:
    if re.search(r"Detailed\s+Score\s+Analysis", html, re.IGNORECASE):
        return True
    if BeautifulSoup is None:
        return False
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        row_texts: list[str] = []
        for tr in table.find_all("tr"):
            first = tr.find(["td", "th"])
            if first:
                row_texts.append(first.get_text(" ", strip=True))
        joined = " | ".join(row_texts)
        if all(dim in joined for dim in FIVE_DIMS):
            return True
    return False


def detect_pplx_verdict(html: str) -> bool:
    if BeautifulSoup is None:
        return bool(re.search(r"<\w+[^>]*class=\"[^\"]*pplx-verdict", html))
    soup = BeautifulSoup(html, "html.parser")
    return soup.find(class_="pplx-verdict") is not None


def detect_ai_summary(html: str) -> bool:
    if BeautifulSoup is None:
        return bool(re.search(r"<\w+[^>]*class=\"[^\"]*ai-summary", html))
    soup = BeautifulSoup(html, "html.parser")
    return soup.find(class_="ai-summary") is not None


def detect_faq_jsonld(html: str) -> bool:
    if BeautifulSoup is None:
        for m in re.finditer(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        ):
            try:
                data = json.loads(m.group(1).strip())
            except Exception:
                continue
            if _has_faqpage(data):
                return True
        return False
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        if _has_faqpage(data):
            return True
    return False


def _has_faqpage(data) -> bool:
    if isinstance(data, dict):
        t = data.get("@type")
        if t == "FAQPage" or (isinstance(t, list) and "FAQPage" in t):
            return True
        return any(_has_faqpage(v) for v in data.values())
    if isinstance(data, list):
        return any(_has_faqpage(v) for v in data)
    return False


def extract_body_text(html: str) -> str:
    if BeautifulSoup is None:
        stripped = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        stripped = re.sub(r"<style[^>]*>.*?</style>", " ", stripped, flags=re.DOTALL | re.IGNORECASE)
        return re.sub(r"<[^>]+>", " ", stripped)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    body = soup.body or soup
    return body.get_text(" ", strip=True)


def word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z'_-]*\b", text))


def number_count(text: str) -> int:
    return len(NUM_RE.findall(text))


def fetch_enriched_at_map(all_slugs: list[str]) -> dict[str, datetime | None]:
    if not all_slugs:
        return {}
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT slug, max(enriched_at) AS enriched_at "
            "FROM software_registry WHERE slug = ANY(%s) "
            "GROUP BY slug",
            (all_slugs,),
        )
        return {slug: enriched for slug, enriched in cur.fetchall()}


def staleness(enriched: datetime | None, now: datetime) -> int | None:
    if enriched is None:
        return None
    ref = enriched
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return (now - ref).days


def audit_one(url: str, enriched_map: dict[str, datetime | None], now: datetime) -> dict:
    html = curl_html(url)
    body_text = extract_body_text(html)
    wc = word_count(body_text)
    nc = number_count(body_text)
    density = (nc / wc * 1000.0) if wc > 0 else 0.0

    slugs = slugs_from_url(url) or ("", "")
    enriched_candidates = [enriched_map.get(s) for s in slugs if s]
    enriched_candidates = [e for e in enriched_candidates if e is not None]
    last_enriched = max(enriched_candidates) if enriched_candidates else None
    stale_days = staleness(last_enriched, now)

    return {
        "url": url,
        "has_king_sections": detect_king_sections(html, body_text),
        "has_pplx_verdict": detect_pplx_verdict(html),
        "has_ai_summary": detect_ai_summary(html),
        "has_faq_jsonld": detect_faq_jsonld(html),
        "word_count": wc,
        "number_tokens": nc,
        "data_density": round(density, 2),
        "last_enriched_at": last_enriched.astimezone(timezone.utc).isoformat()
        if last_enriched
        else None,
        "staleness_days": stale_days,
    }


def is_escalated(row: dict) -> bool:
    if not row["has_king_sections"]:
        return True
    if not row["has_pplx_verdict"]:
        return True
    if not row["has_ai_summary"]:
        return True
    if not row["has_faq_jsonld"]:
        return True
    if row["word_count"] < WORD_COUNT_MIN:
        return True
    if row["data_density"] < DATA_DENSITY_MIN:
        return True
    if row["staleness_days"] is not None and row["staleness_days"] > STALENESS_MAX_DAYS:
        return True
    return False


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    frac = k - lo
    return float(xs[lo] + (xs[hi] - xs[lo]) * frac)


def build_markdown(rows: list[dict], summary: dict) -> str:
    lines: list[str] = []
    lines.append(f"# {TASK_ID} /compare/ HTML-level quality audit (50 pages)")
    lines.append("")
    lines.append(
        "Samples 50 existing `/compare/<a>-vs-<b>` pages that currently return "
        "HTTP 200 on nerq.ai. Pages are drawn at random from the intra-registry "
        "cross-product of the top-100 demand slugs per registry (`smedjan.ai_demand_scores` "
        "× Nerq `entity_lookup.source`). URLs already audited in the last 7 days of "
        "`FB-F3-*.sampled_urls.jsonl` are excluded; slug `test` is excluded. For "
        "each sampled URL the full HTML is fetched (`curl`, User-Agent "
        f"`{USER_AGENT.split()[0]}`, 20 s timeout) and parsed for the king sections "
        "(Detailed Score Analysis table across Security/Maintenance/Popularity/"
        "Quality/Community) and the sacred-byte markers (`pplx-verdict`, `ai-summary`, "
        "FAQPage JSON-LD). Body text gives word count and the number-token count; "
        "`data_density = number_tokens / words × 1000`. Staleness is days since "
        "`max(enriched_at)` across `software_registry` rows for slug_a + slug_b."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- pages_audited: **{summary['pages_audited']}**")
    lines.append(
        f"- missing_king_sections: **{summary['missing_king']}** / {summary['pages_audited']}"
    )
    lines.append(
        f"- missing_pplx_verdict: **{summary['missing_pplx']}** / {summary['pages_audited']}"
    )
    lines.append(
        f"- missing_ai_summary: **{summary['missing_ai']}** / {summary['pages_audited']}"
    )
    lines.append(
        f"- missing_faq_jsonld: **{summary['missing_faq']}** / {summary['pages_audited']}"
    )
    lines.append(
        f"- word_count p25/p50/p75: **{summary['wc_p25']} / {summary['wc_p50']} / {summary['wc_p75']}**"
    )
    lines.append(f"- data_density p50: **{summary['density_p50']}**")
    lines.append(
        f"- staleness_days p50: **{summary['stale_p50']}** "
        f"(count > 30d: **{summary['stale_gt_30']}** / {summary['pages_audited']})"
    )
    lines.append(f"- escalation_count: **{summary['escalation_count']}**")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines.append(
        "| url | king | pplx | ai_sum | faq | words | nums | density | last_enriched | stale_d |"
    )
    lines.append(
        "|-----|------|------|--------|-----|-------|------|---------|---------------|---------|"
    )
    for r in rows:
        lines.append(
            "| {url} | {k} | {p} | {a} | {f} | {w} | {n} | {d} | {e} | {s} |".format(
                url=r["url"].replace(BASE, ""),
                k="Y" if r["has_king_sections"] else "N",
                p="Y" if r["has_pplx_verdict"] else "N",
                a="Y" if r["has_ai_summary"] else "N",
                f="Y" if r["has_faq_jsonld"] else "N",
                w=r["word_count"],
                n=r["number_tokens"],
                d=f"{r['data_density']:.2f}",
                e=(r["last_enriched_at"] or "—")[:19],
                s=r["staleness_days"] if r["staleness_days"] is not None else "—",
            )
        )
    lines.append("")
    lines.append("## Escalation list")
    lines.append("")
    lines.append(
        "A URL escalates if any of: missing king_sections, missing pplx-verdict, "
        "missing ai-summary, missing FAQPage JSON-LD, word_count < "
        f"{WORD_COUNT_MIN}, data_density < {DATA_DENSITY_MIN}, or "
        f"staleness_days > {STALENESS_MAX_DAYS}."
    )
    lines.append("")
    escalated = [r for r in rows if is_escalated(r)]
    if not escalated:
        lines.append("_No pages escalated._")
    else:
        lines.append("| url | reasons |")
        lines.append("|-----|---------|")
        for r in escalated:
            reasons: list[str] = []
            if not r["has_king_sections"]:
                reasons.append("no_king_sections")
            if not r["has_pplx_verdict"]:
                reasons.append("no_pplx_verdict")
            if not r["has_ai_summary"]:
                reasons.append("no_ai_summary")
            if not r["has_faq_jsonld"]:
                reasons.append("no_faq_jsonld")
            if r["word_count"] < WORD_COUNT_MIN:
                reasons.append(f"word_count={r['word_count']}")
            if r["data_density"] < DATA_DENSITY_MIN:
                reasons.append(f"density={r['data_density']:.2f}")
            if r["staleness_days"] is not None and r["staleness_days"] > STALENESS_MAX_DAYS:
                reasons.append(f"stale={r['staleness_days']}d")
            lines.append(
                f"| {r['url'].replace(BASE, '')} | {', '.join(reasons)} |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    excluded = load_prior_sampled_urls()
    print(f"prior_excluded_urls={len(excluded)}", file=sys.stderr)

    by_reg = fetch_top_slugs_per_registry()
    if not by_reg:
        print("no demand slugs found", file=sys.stderr)
        return 1
    print(
        "registries="
        + json.dumps({r: len(s) for r, s in by_reg.items()}),
        file=sys.stderr,
    )

    candidates = enumerate_candidate_pairs(by_reg, excluded)
    print(f"candidate_pairs={len(candidates)}", file=sys.stderr)
    if len(candidates) < TARGET_SAMPLE:
        print("insufficient candidate pool", file=sys.stderr)
        return 1

    sampled: list[str] = []
    probed = 0
    status_counts = {"200": 0, "404": 0, "other": 0}
    for url in candidates:
        if len(sampled) >= TARGET_SAMPLE:
            break
        if probed >= MAX_HEAD_PROBES:
            break
        probed += 1
        st = curl_status(url)
        if st == "200":
            status_counts["200"] += 1
            sampled.append(url)
        elif st == "404":
            status_counts["404"] += 1
        else:
            status_counts["other"] += 1
    print(
        f"probed={probed} sampled={len(sampled)} status_counts={status_counts}",
        file=sys.stderr,
    )
    if len(sampled) < TARGET_SAMPLE:
        print("could not collect 50 x 200 responders", file=sys.stderr)
        return 1

    all_slugs: set[str] = set()
    for url in sampled:
        s = slugs_from_url(url)
        if s:
            all_slugs.update(s)
    enriched_map = fetch_enriched_at_map(sorted(all_slugs))
    now = datetime.now(timezone.utc)

    rows: list[dict] = []
    for url in sampled:
        row = audit_one(url, enriched_map, now)
        rows.append(row)

    OUT_JSONL.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    )

    wcs = [r["word_count"] for r in rows]
    densities = [r["data_density"] for r in rows]
    stales = [r["staleness_days"] for r in rows if r["staleness_days"] is not None]
    escalation_count = sum(1 for r in rows if is_escalated(r))

    summary = {
        "pages_audited": len(rows),
        "missing_king": sum(1 for r in rows if not r["has_king_sections"]),
        "missing_pplx": sum(1 for r in rows if not r["has_pplx_verdict"]),
        "missing_ai": sum(1 for r in rows if not r["has_ai_summary"]),
        "missing_faq": sum(1 for r in rows if not r["has_faq_jsonld"]),
        "wc_p25": int(percentile(wcs, 0.25) or 0),
        "wc_p50": int(percentile(wcs, 0.50) or 0),
        "wc_p75": int(percentile(wcs, 0.75) or 0),
        "density_p50": round(percentile(densities, 0.50) or 0.0, 2),
        "stale_p50": int(percentile([float(s) for s in stales], 0.50) or 0)
        if stales
        else None,
        "stale_gt_30": sum(1 for s in stales if s > 30),
        "escalation_count": escalation_count,
    }

    OUT_MD.write_text(build_markdown(rows, summary))

    print(
        json.dumps(
            {
                "pages_audited": summary["pages_audited"],
                "escalation_count": summary["escalation_count"],
                "p50_data_density": summary["density_p50"],
                "p50_staleness_days": summary["stale_p50"],
                "status_counts_during_sampling": status_counts,
                "out_md": str(OUT_MD),
                "out_jsonl": str(OUT_JSONL),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
