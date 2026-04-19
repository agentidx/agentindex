"""FB-F1-20260419-022: random /safe/* antipattern spot-check.

Pull 100 random enriched slugs from Nerq RO software_registry, curl the
corresponding https://nerq.ai/safe/<slug> pages, and scan the rendered
HTML for antipatterns:

  - literal 'None' in body text
  - literal 'null' in body text
  - empty <td></td> cells
  - missing JSON-LD script tag
  - JSON-LD block that fails json.loads

Writes findings table to ~/smedjan/audits/FB-F1-20260419-022.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from collections import defaultdict

from smedjan import sources

OUT_PATH = os.path.expanduser("~/smedjan/audits/FB-F1-20260419-022.md")
BASE_URL = "https://nerq.ai/safe/"
SAMPLE_SIZE = 100
TIMEOUT = 15

JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
EMPTY_TD_RE = re.compile(r"<td>\s*</td>", re.IGNORECASE)
BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "smedjan-audit/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def pick_slugs() -> list[str]:
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            """
            SELECT slug
            FROM software_registry
            WHERE enriched_at IS NOT NULL
            ORDER BY random()
            LIMIT %s
            """,
            (SAMPLE_SIZE,),
        )
        return [r[0] for r in cur.fetchall()]


def scan(html: str) -> dict[str, bool]:
    findings: dict[str, bool] = {
        "literal_None_in_body": False,
        "literal_null_in_body": False,
        "empty_td_cell": False,
        "missing_jsonld": False,
        "broken_jsonld": False,
    }

    body_match = BODY_RE.search(html)
    body = body_match.group(1) if body_match else html
    body_text = TAG_RE.sub(" ", body)

    if re.search(r"\bNone\b", body_text):
        findings["literal_None_in_body"] = True
    if re.search(r"\bnull\b", body_text):
        findings["literal_null_in_body"] = True
    if EMPTY_TD_RE.search(html):
        findings["empty_td_cell"] = True

    jsonld_blocks = JSONLD_RE.findall(html)
    if not jsonld_blocks:
        findings["missing_jsonld"] = True
    else:
        for block in jsonld_blocks:
            try:
                json.loads(block.strip())
            except (json.JSONDecodeError, ValueError):
                findings["broken_jsonld"] = True
                break

    return findings


def main() -> int:
    t0 = time.time()
    slugs = pick_slugs()
    if len(slugs) < SAMPLE_SIZE:
        print(f"ERROR: only got {len(slugs)} slugs from Nerq RO", file=sys.stderr)
        return 1

    status_dist: dict[int, int] = defaultdict(int)
    fetch_errors = 0
    finding_counts: dict[str, int] = defaultdict(int)
    finding_samples: dict[str, list[str]] = defaultdict(list)

    for slug in slugs:
        status, html = fetch(BASE_URL + slug)
        status_dist[status] += 1
        if status != 200 or not html:
            fetch_errors += 1
            continue
        f = scan(html)
        for name, hit in f.items():
            if hit:
                finding_counts[name] += 1
                if len(finding_samples[name]) < 3:
                    finding_samples[name].append(slug)

    elapsed = time.time() - t0

    order = [
        "literal_None_in_body",
        "literal_null_in_body",
        "empty_td_cell",
        "missing_jsonld",
        "broken_jsonld",
    ]

    lines: list[str] = []
    lines.append(f"# FB-F1-20260419-022 \u2014 /safe/* antipattern spot-check")
    lines.append("")
    lines.append(f"- Pages checked: **{SAMPLE_SIZE}**")
    lines.append(
        "- Source: `SELECT slug FROM software_registry WHERE enriched_at IS NOT NULL "
        "ORDER BY random() LIMIT 100` (Nerq RO)"
    )
    lines.append(f"- Target: `{BASE_URL}<slug>`")
    lines.append(f"- Elapsed: {elapsed:.1f}s")
    status_str = " ".join(f"{k}={v}" for k, v in sorted(status_dist.items()))
    lines.append(f"- HTTP status distribution: {status_str}")
    lines.append(f"- Fetch errors: {fetch_errors}")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines.append("| Finding | Count | Sample slugs |")
    lines.append("|---|---:|---|")
    for name in order:
        count = finding_counts[name]
        samples = ", ".join(finding_samples[name]) if finding_samples[name] else "\u2014"
        lines.append(f"| {name} | {count} | {samples} |")
    lines.append("")

    over_threshold = [(n, finding_counts[n]) for n in order if finding_counts[n] > 5]
    lines.append("## Escalation")
    lines.append("")
    if over_threshold:
        lines.append(
            "Antipattern(s) exceeded the > 5 page threshold; escalating via "
            "`STATUS: needs_approval`:"
        )
        for n, c in over_threshold:
            lines.append(f"- **{n}**: {c} pages")
    else:
        lines.append(
            "No antipattern exceeded the > 5 page threshold; no escalation required."
        )
    lines.append("")

    with open(OUT_PATH, "w") as f:
        f.write("\n".join(lines))

    total_findings = sum(finding_counts.values())
    evidence = {
        "pages_checked": SAMPLE_SIZE,
        "fetch_errors": fetch_errors,
        "status_distribution": dict(status_dist),
        "findings": total_findings,
        "finding_counts": {n: finding_counts[n] for n in order},
        "over_threshold": {n: c for n, c in over_threshold},
        "output_path": OUT_PATH,
        "elapsed_seconds": round(elapsed, 2),
    }
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
