import os, re, sys, json, time, html
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

sys.path.insert(0, "/Users/anstudio/agentindex")
from smedjan import sources

TASK_ID = "FB-F1-20260419-015"
BASE = "https://nerq.ai/safe/"
UA = f"smedjan-fb-f1-015/1.0 (+https://nerq.ai)"

with sources.nerq_readonly_cursor() as (_, cur):
    cur.execute(
        "SELECT slug FROM software_registry "
        "WHERE enriched_at IS NOT NULL "
        "ORDER BY random() LIMIT 100"
    )
    slugs = [r[0] for r in cur.fetchall()]

assert len(slugs) == 100, f"got {len(slugs)} slugs, expected 100"

JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
EMPTY_TD_RE = re.compile(r"<td[^>]*>\s*</td>", re.IGNORECASE)

def fetch(slug):
    url = BASE + quote(slug, safe="")
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    try:
        with urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="replace")
            return slug, r.status, body, None
    except HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return slug, e.code, body, None
    except (URLError, TimeoutError) as e:
        return slug, 0, "", str(e)
    except Exception as e:
        return slug, 0, "", repr(e)

def visible_body(html_text):
    body = re.sub(r"<script\b[^>]*>.*?</script>", " ", html_text,
                  flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<style\b[^>]*>.*?</style>", " ", body,
                  flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.DOTALL)
    body = re.sub(r"<[^>]+>", " ", body)
    return html.unescape(body)

WORD_NONE = re.compile(r"\bNone\b")
WORD_NULL = re.compile(r"\bnull\b")

findings = {
    "http_non_200": [],
    "fetch_error":  [],
    "literal_None_in_visible_text": [],
    "literal_null_in_visible_text": [],
    "empty_td_cell": [],
    "missing_jsonld": [],
    "broken_jsonld": [],
}
status_dist = {}

t0 = time.time()
with ThreadPoolExecutor(max_workers=12) as ex:
    futs = [ex.submit(fetch, s) for s in slugs]
    for f in as_completed(futs):
        slug, status, body, err = f.result()
        status_dist[status] = status_dist.get(status, 0) + 1
        if err:
            findings["fetch_error"].append(slug)
            continue
        if status != 200:
            findings["http_non_200"].append(slug)
            continue

        text = visible_body(body)
        if WORD_NONE.search(text):
            findings["literal_None_in_visible_text"].append(slug)
        if WORD_NULL.search(text):
            findings["literal_null_in_visible_text"].append(slug)
        if EMPTY_TD_RE.search(body):
            findings["empty_td_cell"].append(slug)

        blocks = JSONLD_RE.findall(body)
        if not blocks:
            findings["missing_jsonld"].append(slug)
        else:
            broke = False
            for b in blocks:
                try:
                    json.loads(b.strip())
                except Exception:
                    broke = True
                    break
            if broke:
                findings["broken_jsonld"].append(slug)

elapsed = time.time() - t0

out_path = f"/Users/anstudio/smedjan/audits/{TASK_ID}.md"
lines = []
lines.append(f"# {TASK_ID} — /safe/* antipattern spot-check")
lines.append("")
lines.append(f"- Pages checked: **{len(slugs)}**")
lines.append("- Source: `SELECT slug FROM software_registry WHERE enriched_at IS NOT NULL ORDER BY random() LIMIT 100` (Nerq RO)")
lines.append("- Target: `https://nerq.ai/safe/<slug>` (slugs percent-encoded before fetch)")
lines.append(f"- Elapsed: {elapsed:.2f}s")
lines.append("- HTTP status distribution: " + ", ".join(f"{k}={v}" for k, v in sorted(status_dist.items())))
lines.append(f"- Fetch errors: {len(findings['fetch_error'])}")
lines.append("")
lines.append("## Findings")
lines.append("")
lines.append("| Finding | Count | Sample slugs |")
lines.append("|---|---:|---|")
for k, v in findings.items():
    samples = ", ".join(v[:3]) if v else "—"
    lines.append(f"| {k} | {len(v)} | {samples} |")
lines.append("")

over = {k: len(v) for k, v in findings.items() if len(v) > 5}
lines.append("## Escalation")
lines.append("")
if over:
    lines.append("Antipatterns exceeding the > 5 page threshold:")
    for k, n in over.items():
        lines.append(f"- **{k}**: {n} pages")
    lines.append("")
    lines.append("STATUS: needs_approval — Anders to pick the fix task.")
else:
    lines.append("No antipattern exceeded the > 5 page threshold; no escalation required.")
lines.append("")

with open(out_path, "w") as f:
    f.write("\n".join(lines))

summary = {
    "pages_checked": len(slugs),
    "findings": sum(len(v) for v in findings.values()),
    "over_threshold": over,
    "status_dist": status_dist,
    "elapsed_s": round(elapsed, 2),
    "out_path": out_path,
}
print("SUMMARY:" + json.dumps(summary))
