#!/usr/bin/env python3
"""
F3-v3 smoke executor — FB-F3-20260423-smoke.

Executes the F3-v3 template body against production /compare/ pages,
writing ~/smedjan/audits/FB-F3-20260423-smoke.{md,sampled_urls.jsonl}.

Serves two purposes at once:
  1. Dry-run required by task F3-v3-post-L1b (acceptance: "dry-run
     against 50 /compare/ pages shows the new audit surfaces PASS/FAIL
     per criterion").
  2. Smoke FB-F3 task proving the rewritten template body is
     materialisable and executable end-to-end.

Run: /Users/anstudio/agentindex/venv/bin/python3 \
     /Users/anstudio/agentindex-factory/smedjan/audits/FB-F3-20260423-smoke.py
"""
from __future__ import annotations

import json
import logging
import os
import plistlib
import random
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

# Source the .env so we inherit NERQ_RO_PW etc.
_ENV_PATH = Path.home() / "smedjan" / "config" / ".env"
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# psycopg2 lives in /Users/anstudio/agentindex/venv
sys.path.insert(0, "/Users/anstudio/agentindex-factory")
import psycopg2  # noqa: E402

TASK_ID = "FB-F3-20260423-smoke"
OUT_DIR = Path.home() / "smedjan" / "audits"
AUDIT_MD = OUT_DIR / f"{TASK_ID}.md"
AUDIT_JSONL = OUT_DIR / f"{TASK_ID}.sampled_urls.jsonl"
COMPARISON_PAIRS_JSON = Path("/Users/anstudio/agentindex/agentindex/comparison_pairs.json")
NERQ_API_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.nerq.api.plist"
NERQ_BASE = "https://nerq.ai"
USER_AGENT = "SmedjanAudit/F3-v3"
N_ENRICHED = 40
N_FAILSAFE = 10
N_TOTAL = 50  # pad failsafe up to here if enriched cohort is narrow
BAND_ENRICHED = (1500, 2400)
BAND_FAILSAFE_MAX = 1500

log = logging.getLogger("f3v3.smoke")


# ── Step 1: read L1B_COMPARE_UNLOCK_REGISTRIES ─────────────────────────────

def unlocked_registries() -> list[str]:
    env = os.environ.get("L1B_COMPARE_UNLOCK_REGISTRIES")
    if env:
        return [r.strip() for r in env.split(",") if r.strip()]
    if NERQ_API_PLIST.exists():
        try:
            data = plistlib.loads(NERQ_API_PLIST.read_bytes())
            vars_ = data.get("EnvironmentVariables") or {}
            val = vars_.get("L1B_COMPARE_UNLOCK_REGISTRIES")
            if val:
                return [r.strip() for r in val.split(",") if r.strip()]
        except Exception as exc:  # noqa: BLE001
            log.warning("plistlib failed: %s", exc)
    return ["npm", "pypi"]  # post-L1b canary default


# ── Step 2: load comparison_pairs universe ─────────────────────────────────

def load_comparison_pairs() -> list[dict[str, str]]:
    if not COMPARISON_PAIRS_JSON.exists():
        log.warning("comparison_pairs.json not found at %s", COMPARISON_PAIRS_JSON)
        return []
    try:
        pairs = json.loads(COMPARISON_PAIRS_JSON.read_text())
        return [p for p in pairs if isinstance(p, dict) and "slug" in p]
    except Exception as exc:  # noqa: BLE001
        log.warning("comparison_pairs.json unparseable: %s", exc)
        return []


# ── Step 3: look up enrichment + registry for slug halves ──────────────────

_SLUG_SPLIT_RX = re.compile(r"^(.+)-vs-(.+)$")
_NON_ALPHANUM_RX = re.compile(r"[^a-z0-9-]+")


def split_compare_slug(compare_slug: str) -> tuple[str, str] | None:
    m = _SLUG_SPLIT_RX.match(compare_slug.lower())
    if not m:
        return None
    return m.group(1), m.group(2)


def normalize_slug(raw: str) -> str:
    # Mirrors agentindex.agent_compare_pages._make_slug loosely — lowercase,
    # replace / with -, strip other non-[a-z0-9-]. Keeps the audit aligned
    # with the generator's actual slug space.
    s = raw.lower().replace("/", "-")
    s = _NON_ALPHANUM_RX.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def nerq_ro_conn():
    return psycopg2.connect(
        user="smedjan_readonly",
        dbname="agentindex",
        password=os.environ["NERQ_RO_PW"],
    )


def lookup_enrichment_bulk(slugs: list[str]) -> dict[str, dict[str, Any]]:
    if not slugs:
        return {}
    with nerq_ro_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT slug, registry, enriched_at,
                   security_score, maintenance_score, popularity_score,
                   quality_score, community_score
              FROM software_registry
             WHERE slug = ANY(%s)
            """,
            (slugs,),
        )
        rows: dict[str, dict[str, Any]] = {}
        for r in cur.fetchall():
            slug = r[0]
            existing = rows.get(slug)
            row = {
                "registry": r[1],
                "enriched_at": r[2],
                "sec": r[3],
                "mnt": r[4],
                "pop": r[5],
                "qty": r[6],
                "com": r[7],
                "full_enriched": all(v is not None for v in r[2:8]),
            }
            # Prefer a fully-enriched row when duplicates exist across registries.
            if existing is None or (row["full_enriched"] and not existing.get("full_enriched")):
                rows[slug] = row
    return rows


# ── Step 4: HEAD 200 filter ────────────────────────────────────────────────

def head_200(slug_compare: str) -> bool:
    url = f"{NERQ_BASE}/compare/{slug_compare}"
    try:
        r = subprocess.run(
            [
                "curl", "-s", "-I", "-m", "8",
                "-A", USER_AGENT,
                "-o", "/dev/null",
                "-w", "%{http_code}",
                url,
            ],
            capture_output=True, text=True, timeout=12,
        )
        return r.stdout.strip() == "200"
    except Exception:  # noqa: BLE001
        return False


# ── Step 5: curl + extract fields ──────────────────────────────────────────

_PPLX_ATTR_RX = re.compile(
    r'<[^>]*class\s*=\s*"[^"]*\bpplx-verdict\b[^"]*"[^>]*>',
    re.IGNORECASE,
)
_PPLX_SACRED_RX = re.compile(
    r'<[^>]*data-sacred\s*=\s*"pplx-verdict"[^>]*>|'
    r'<[^>]*class\s*=\s*"[^"]*\bpplx-verdict\b[^"]*"[^>]*data-sacred\s*=\s*"pplx-verdict"',
    re.IGNORECASE,
)
_AI_SUMMARY_RX = re.compile(r'class\s*=\s*"[^"]*\bai-summary\b[^"]*"', re.IGNORECASE)
_KING_TBL_RX = re.compile(r'<table[^>]*class\s*=\s*"[^"]*\bking-sections?\b[^"]*"', re.IGNORECASE)
_KING_SEC_RX = re.compile(r'<section[^>]*class\s*=\s*"[^"]*\bking-sections?\b[^"]*"', re.IGNORECASE)
_JSONLD_RX = re.compile(
    r'<script[^>]*type\s*=\s*"application/ld\+json"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_EXPECTED_DIMS = ["security", "maintenance", "popularity", "quality", "community"]


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self.text_parts.append(data)


def word_count(html: str) -> int:
    ext = _TextExtractor()
    try:
        ext.feed(html)
    except Exception:  # noqa: BLE001
        pass
    text = " ".join(ext.text_parts)
    return len([w for w in text.split() if w])


def has_faq_jsonld(html: str) -> bool:
    for m in _JSONLD_RX.finditer(html):
        body = m.group(1).strip()
        try:
            obj = json.loads(body)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict) and obj.get("@type") == "FAQPage":
            return True
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and item.get("@type") == "FAQPage":
                    return True
    return False


class _KingTableInspector(HTMLParser):
    """Parses the FIRST <table class="king-section*"> and records row/col shape."""

    def __init__(self):
        super().__init__()
        self.found = False
        self.in_target = False
        self.in_thead = False
        self.in_tbody = False
        self.in_tr = False
        self.in_cell = False
        self._current_cell_text: list[str] = []
        self.thead_cells = 0
        self.tbody_rows: list[list[str]] = []
        self._current_row_cells: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self.found and not self.in_target:
            return
        attrs_d = dict(attrs)
        if tag == "table" and not self.in_target:
            cls = attrs_d.get("class", "")
            if re.search(r"\bking-sections?\b", cls, re.IGNORECASE):
                self.found = True
                self.in_target = True
                return
        if not self.in_target:
            return
        if tag == "thead":
            self.in_thead = True
        elif tag == "tbody":
            self.in_tbody = True
        elif tag == "tr":
            self.in_tr = True
            self._current_row_cells = []
        elif tag in ("th", "td"):
            self.in_cell = True
            self._current_cell_text = []

    def handle_endtag(self, tag):
        if not self.in_target:
            return
        if tag == "table":
            self.in_target = False
            return
        if tag == "thead":
            self.in_thead = False
        elif tag == "tbody":
            self.in_tbody = False
        elif tag == "tr":
            if self.in_tbody:
                self.tbody_rows.append(self._current_row_cells)
            self.in_tr = False
        elif tag in ("th", "td"):
            text = " ".join(self._current_cell_text).strip()
            if self.in_thead and self.in_tr:
                self.thead_cells += 1
            elif self.in_tbody and self.in_tr:
                self._current_row_cells.append(text)
            self.in_cell = False

    def handle_data(self, data):
        if self.in_cell and self.in_target:
            self._current_cell_text.append(data)


def analyze_king_table(html: str) -> tuple[bool, bool, bool]:
    """Return (has_king_table, king_rows_ok, king_cols_ok)."""
    has_table = bool(_KING_TBL_RX.search(html)) or bool(_KING_SEC_RX.search(html))
    if not has_table:
        return False, False, False
    insp = _KingTableInspector()
    try:
        insp.feed(html)
    except Exception:  # noqa: BLE001
        pass
    if not insp.found:
        # class matched regex but parser missed it (e.g. <section> form). Soft-accept
        # has_king_table=True but the shape check is not possible; assume cols_ok.
        return True, False, False
    labels = [(row[0].strip().lower() if row else "") for row in insp.tbody_rows]
    rows_ok = (
        len(insp.tbody_rows) == 5
        and all(any(d in lab for d in [exp]) for exp, lab in zip(_EXPECTED_DIMS, labels))
    )
    cols_ok = (
        insp.thead_cells >= 3
        and all(len(r) >= 3 for r in insp.tbody_rows)
    )
    return True, rows_ok, cols_ok


def fetch(url: str) -> str | None:
    try:
        r = subprocess.run(
            ["curl", "-sL", "-m", "15", "-A", USER_AGENT, url],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode != 0:
            return None
        return r.stdout
    except Exception:  # noqa: BLE001
        return None


def audit_url(compare_slug: str, bucket: str, enrichment_a: dict | None, enrichment_b: dict | None) -> dict:
    url = f"{NERQ_BASE}/compare/{compare_slug}"
    html = fetch(url) or ""
    wc = word_count(html)
    has_king, rows_ok, cols_ok = analyze_king_table(html)
    has_pplx = bool(_PPLX_ATTR_RX.search(html))
    pplx_sacred = has_pplx and bool(_PPLX_SACRED_RX.search(html))
    has_ai_sum = bool(_AI_SUMMARY_RX.search(html))
    has_faq = has_faq_jsonld(html)

    if bucket == "enriched":
        wc_in_band = BAND_ENRICHED[0] <= wc <= BAND_ENRICHED[1]
        crit_a = has_king and rows_ok and cols_ok
        crit_b = has_pplx
    else:
        wc_in_band = wc < BAND_FAILSAFE_MAX
        crit_a = not has_king
        crit_b = not has_pplx
    crit_c = has_ai_sum and has_faq
    crit_d = wc_in_band
    page_pass = crit_a and crit_b and crit_c and crit_d

    return {
        "url": url,
        "compare_slug": compare_slug,
        "bucket": bucket,
        "registry_a": (enrichment_a or {}).get("registry"),
        "registry_b": (enrichment_b or {}).get("registry"),
        "has_king_table": has_king,
        "king_rows_ok": rows_ok,
        "king_cols_ok": cols_ok,
        "has_pplx_verdict": has_pplx,
        "pplx_data_sacred": pplx_sacred,
        "has_ai_summary": has_ai_sum,
        "has_faq_jsonld": has_faq,
        "word_count": wc,
        "word_count_in_band": wc_in_band,
        "crit_a_king": crit_a,
        "crit_b_pplx": crit_b,
        "crit_c_sacred": crit_c,
        "crit_d_words": crit_d,
        "page_pass": page_pass,
    }


# ── Step 6: 7-day dedup against prior F3 JSONLs ────────────────────────────

def prior_week_urls() -> set[str]:
    cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
    seen: set[str] = set()
    for p in OUT_DIR.glob("FB-F3-*.sampled_urls.jsonl"):
        try:
            if p.stat().st_mtime < cutoff:
                continue
            for line in p.read_text().splitlines():
                try:
                    obj = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                u = obj.get("url")
                if isinstance(u, str):
                    seen.add(u)
        except Exception:  # noqa: BLE001
            continue
    return seen


# ── Step 7: build the sample ───────────────────────────────────────────────

def build_sample(unlocked: list[str]) -> tuple[list[dict], list[dict], int]:
    pairs = load_comparison_pairs()
    if not pairs:
        log.error("no comparison_pairs available — abort")
        return [], [], 0
    random.seed(42)
    random.shuffle(pairs)

    excluded_urls = prior_week_urls()
    log.info("excluding %d URLs from prior-week F3 audits", len(excluded_urls))

    # Extract all slug halves needing enrichment lookup. For each pair we try
    # up to four candidate slugs per half: normalized full form, short form
    # (after slash), raw-lower, and the compare-slug halve. This compensates
    # for the known /compare/ generator slug-drift (`author/tool` collapses
    # into `authortool` instead of `author-tool`).
    slug_halves: set[str] = set()
    pair_candidates: dict[str, tuple[list[str], list[str]]] = {}

    def _candidates(raw: str, halve_form: str) -> list[str]:
        out: list[str] = []
        if raw:
            out.append(normalize_slug(raw))
            if "/" in raw:
                out.append(normalize_slug(raw.split("/", 1)[1]))
            out.append(raw.lower())
        out.append(halve_form)
        seen, uniq = set(), []
        for s in out:
            if s and s not in seen:
                seen.add(s)
                uniq.append(s)
        return uniq

    for p in pairs:
        compare_slug = p["slug"]
        if compare_slug == "test" or "-vs-test" in compare_slug or compare_slug.startswith("test-vs-"):
            continue
        halves = split_compare_slug(compare_slug)
        if not halves:
            continue
        a_raw = p.get("agent_a") or halves[0]
        b_raw = p.get("agent_b") or halves[1]
        a_cands = _candidates(a_raw, halves[0])
        b_cands = _candidates(b_raw, halves[1])
        pair_candidates[compare_slug] = (a_cands, b_cands)
        slug_halves.update(a_cands)
        slug_halves.update(b_cands)

    log.info("looking up enrichment for %d distinct slugs", len(slug_halves))
    enrichment = lookup_enrichment_bulk(sorted(slug_halves))
    log.info("enrichment rows returned: %d", len(enrichment))

    def get_enrich(candidates: list[str]) -> dict | None:
        # Prefer a fully-enriched row if any candidate yields one.
        best: dict | None = None
        for c in candidates:
            row = enrichment.get(c)
            if not row:
                continue
            if row.get("full_enriched"):
                return row
            if best is None:
                best = row
        return best

    enriched: list[dict] = []
    failsafe: list[dict] = []

    # Two-pass strategy — first collect enriched candidates (or exhaust the
    # universe), then pad with failsafe so the combined total is 50. This
    # avoids the failsafe bucket filling up early while enriched keeps
    # arriving in later iterations of the shuffled list.

    triaged: list[tuple[str, dict | None, dict | None, bool]] = []
    for p in pairs:
        compare_slug = p["slug"]
        if compare_slug == "test":
            continue
        if compare_slug not in pair_candidates:
            continue
        url = f"{NERQ_BASE}/compare/{compare_slug}"
        if url in excluded_urls:
            continue
        a_cands, b_cands = pair_candidates[compare_slug]
        ea = get_enrich(a_cands)
        eb = get_enrich(b_cands)
        a_full = bool(ea and ea.get("full_enriched") and ea.get("registry") in unlocked)
        b_full = bool(eb and eb.get("full_enriched") and eb.get("registry") in unlocked)
        triaged.append((compare_slug, ea, eb, a_full and b_full))

    # Pass 1 — enriched.
    for compare_slug, ea, eb, is_enriched in triaged:
        if len(enriched) >= N_ENRICHED:
            break
        if not is_enriched:
            continue
        if head_200(compare_slug):
            enriched.append({"compare_slug": compare_slug, "enrichment_a": ea, "enrichment_b": eb})

    # Pass 2 — failsafe, padded so combined == N_TOTAL.
    target_failsafe = max(N_FAILSAFE, N_TOTAL - len(enriched))
    for compare_slug, ea, eb, is_enriched in triaged:
        if len(failsafe) >= target_failsafe:
            break
        if is_enriched:
            continue
        if head_200(compare_slug):
            failsafe.append({"compare_slug": compare_slug, "enrichment_a": ea, "enrichment_b": eb})

    shortfall = max(0, N_ENRICHED - len(enriched))
    log.info(
        "sample built — enriched=%d (target %d, shortfall=%d), failsafe=%d (total=%d)",
        len(enriched), N_ENRICHED, shortfall, len(failsafe),
        len(enriched) + len(failsafe),
    )
    return enriched, failsafe, shortfall


# ── Step 8: summarise + write md + jsonl ───────────────────────────────────

def _dist(values: list[int]) -> tuple[int, int, int]:
    if not values:
        return 0, 0, 0
    s = sorted(values)
    return (
        s[max(0, int(0.25 * (len(s) - 1)))],
        s[max(0, int(0.50 * (len(s) - 1)))],
        s[max(0, int(0.75 * (len(s) - 1)))],
    )


def write_artifacts(results: list[dict], enriched_shortfall: int, unlocked: list[str]) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with AUDIT_JSONL.open("w") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")

    enriched = [r for r in results if r["bucket"] == "enriched"]
    failsafe = [r for r in results if r["bucket"] == "failsafe"]

    def pass_rate(rows: list[dict]) -> float:
        if not rows:
            return 0.0
        return round(sum(1 for r in rows if r["page_pass"]) / len(rows), 3)

    def crit_counts(rows: list[dict], key: str) -> int:
        return sum(1 for r in rows if r[key])

    evidence: dict[str, Any] = {
        "pages_audited": len(results),
        "enriched_count": len(enriched),
        "enriched_shortfall": enriched_shortfall,
        "failsafe_count": len(failsafe),
        "enriched_pass_rate": pass_rate(enriched),
        "failsafe_pass_rate": pass_rate(failsafe),
        "crit_a_enriched": crit_counts(enriched, "crit_a_king"),
        "crit_b_enriched": crit_counts(enriched, "crit_b_pplx"),
        "crit_c_enriched": crit_counts(enriched, "crit_c_sacred"),
        "crit_d_enriched": crit_counts(enriched, "crit_d_words"),
        "crit_a_failsafe": crit_counts(failsafe, "crit_a_king"),
        "crit_b_failsafe": crit_counts(failsafe, "crit_b_pplx"),
        "crit_c_failsafe": crit_counts(failsafe, "crit_c_sacred"),
        "crit_d_failsafe": crit_counts(failsafe, "crit_d_words"),
        "pplx_data_sacred_count": sum(1 for r in enriched if r["pplx_data_sacred"]),
        "unlocked_registries": unlocked,
    }

    wc_e = [r["word_count"] for r in enriched]
    wc_f = [r["word_count"] for r in failsafe]
    p25_e, p50_e, p75_e = _dist(wc_e)
    p25_f, p50_f, p75_f = _dist(wc_f)

    lines: list[str] = []
    lines.append(f"# F3-v3 post-L1b audit — {TASK_ID}")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append(f"Unlocked registries: {', '.join(unlocked) or '(none)'}")
    lines.append(f"Pages audited: {evidence['pages_audited']}  "
                 f"(enriched={evidence['enriched_count']}/40, "
                 f"failsafe={evidence['failsafe_count']}/10, "
                 f"enriched_shortfall={evidence['enriched_shortfall']})")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- enriched_pass_rate: **{evidence['enriched_pass_rate']}**  "
                 f"— failsafe_pass_rate: **{evidence['failsafe_pass_rate']}**")
    lines.append(f"- pplx_data_sacred on enriched pages: "
                 f"{evidence['pplx_data_sacred_count']} / {evidence['enriched_count']} "
                 "(observation; not PASS gate in F3-v3)")
    lines.append("")
    lines.append("### Per-criterion pass counts")
    lines.append("")
    lines.append("| criterion | enriched | failsafe |")
    lines.append("|---|---:|---:|")
    lines.append(f"| crit_a (king-sections) | {evidence['crit_a_enriched']}/{len(enriched)} | {evidence['crit_a_failsafe']}/{len(failsafe)} |")
    lines.append(f"| crit_b (pplx-verdict)  | {evidence['crit_b_enriched']}/{len(enriched)} | {evidence['crit_b_failsafe']}/{len(failsafe)} |")
    lines.append(f"| crit_c (sacred bytes)  | {evidence['crit_c_enriched']}/{len(enriched)} | {evidence['crit_c_failsafe']}/{len(failsafe)} |")
    lines.append(f"| crit_d (word_count band) | {evidence['crit_d_enriched']}/{len(enriched)} | {evidence['crit_d_failsafe']}/{len(failsafe)} |")
    lines.append("")
    lines.append("### Word-count distribution")
    lines.append("")
    lines.append("| bucket | p25 | p50 | p75 |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| enriched | {p25_e} | {p50_e} | {p75_e} |")
    lines.append(f"| failsafe | {p25_f} | {p50_f} | {p75_f} |")
    lines.append("")
    lines.append("## Findings table")
    lines.append("")
    lines.append("| url | bucket | crit_a | crit_b | crit_c | crit_d | pass | wc | reg_a/b | pplx-sacred |")
    lines.append("|---|---|:-:|:-:|:-:|:-:|:-:|---:|---|:-:|")
    for r in results:
        reg = f"{r['registry_a'] or '?'}/{r['registry_b'] or '?'}"
        lines.append(
            f"| {r['compare_slug']} | {r['bucket']} "
            f"| {'PASS' if r['crit_a_king'] else 'FAIL'} "
            f"| {'PASS' if r['crit_b_pplx'] else 'FAIL'} "
            f"| {'PASS' if r['crit_c_sacred'] else 'FAIL'} "
            f"| {'PASS' if r['crit_d_words'] else 'FAIL'} "
            f"| {'PASS' if r['page_pass'] else 'FAIL'} "
            f"| {r['word_count']} | {reg} "
            f"| {'yes' if r['pplx_data_sacred'] else 'no'} |"
        )
    lines.append("")
    lines.append("## Escalation list (page_pass=FAIL)")
    lines.append("")
    esc_enriched = [r for r in enriched if not r["page_pass"]]
    esc_failsafe = [r for r in failsafe if not r["page_pass"]]
    lines.append(f"### Enriched — {len(esc_enriched)}")
    for r in esc_enriched:
        fails = [k for k in ("crit_a_king", "crit_b_pplx", "crit_c_sacred", "crit_d_words") if not r[k]]
        lines.append(f"- {r['url']}  fails: {','.join(fails)}  wc={r['word_count']}")
    lines.append("")
    lines.append(f"### Failsafe — {len(esc_failsafe)}")
    for r in esc_failsafe:
        fails = [k for k in ("crit_a_king", "crit_b_pplx", "crit_c_sacred", "crit_d_words") if not r[k]]
        lines.append(f"- {r['url']}  fails: {','.join(fails)}  wc={r['word_count']}")
    lines.append("")
    lines.append("## EVIDENCE")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(evidence, indent=2, default=str))
    lines.append("```")

    AUDIT_MD.write_text("\n".join(lines) + "\n")
    return evidence


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    unlocked = unlocked_registries()
    log.info("unlocked registries = %s", unlocked)

    enriched_candidates, failsafe_candidates, shortfall = build_sample(unlocked)
    if not enriched_candidates and not failsafe_candidates:
        log.error("empty sample — aborting")
        return 1

    results: list[dict] = []
    log.info("auditing %d enriched + %d failsafe URLs",
             len(enriched_candidates), len(failsafe_candidates))
    for row in enriched_candidates:
        results.append(audit_url(row["compare_slug"], "enriched",
                                  row["enrichment_a"], row["enrichment_b"]))
    for row in failsafe_candidates:
        results.append(audit_url(row["compare_slug"], "failsafe",
                                  row["enrichment_a"], row["enrichment_b"]))

    evidence = write_artifacts(results, shortfall, unlocked)
    log.info("wrote %s", AUDIT_MD)
    log.info("wrote %s", AUDIT_JSONL)
    log.info("evidence: %s", json.dumps(evidence, default=str))

    # Acceptance-mirror STATUS: done only if every criterion count is reported
    # and the audit surfaced PASS/FAIL per criterion across both buckets.
    status = "done"
    if evidence["crit_c_enriched"] < evidence["enriched_count"] or \
       evidence["crit_c_failsafe"] < evidence["failsafe_count"]:
        status = "needs_approval"
    if evidence["enriched_pass_rate"] < 0.80 and evidence["enriched_count"] > 0:
        status = "needs_approval"
    if evidence["failsafe_pass_rate"] < 0.90 and evidence["failsafe_count"] > 0:
        status = "needs_approval"
    log.info("smoke STATUS: %s", status)
    print(f"STATUS: {status}")
    print(f"OUTPUT_PATHS: {AUDIT_MD}, {AUDIT_JSONL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
