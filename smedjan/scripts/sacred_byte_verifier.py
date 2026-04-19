"""sacred_byte_verifier.py — periodic SEO/GEO-byte coverage check for /safe/*.

Every enriched ``/safe/{slug}`` page is required to ship four "sacred bytes"
that downstream LLM crawlers, voice assistants, and search engines depend on:

  * ``<p class="pplx-verdict">``     — Perplexity-style one-sentence verdict.
  * ``<p class="ai-summary">``       — short LLM-targetted summary paragraph.
  * ``schema.org SpeakableSpecification`` JSON-LD (voice/audio surface hint).
  * ``schema.org FAQPage``           JSON-LD (rich-result eligibility).

If a templating change drops one of these from a non-trivial slice of pages
the loss is silent — pages still return 200 — but ranking/citation slowly
craters. This verifier samples 500 random enriched slugs every 6h, fetches
the live HTML, counts coverage per byte, writes a markdown audit, and — when
any byte falls below 99 % coverage — pushes an ntfy alert and enqueues a
``sacred-byte-regression`` task with the full per-page breakdown so a human
can investigate which template path stopped emitting the byte.

Invocation
----------
    python3 -m smedjan.scripts.sacred_byte_verifier              # live
    python3 -m smedjan.scripts.sacred_byte_verifier --dry-run    # no alert/enqueue
    python3 -m smedjan.scripts.sacred_byte_verifier --base-url http://localhost:8000
    python3 -m smedjan.scripts.sacred_byte_verifier --sample-size 100 --verbose

Sources
-------
* Slug pool: ``public.software_registry`` on the Nerq read-only replica,
  filtered to ``enriched_at IS NOT NULL`` (the placeholder template that
  serves "Not Yet Analyzed" pages — which legitimately lacks the bytes —
  is therefore excluded from the sample).
* HTTP target: ``--base-url`` (default ``https://nerq.ai``). On the smedjan
  host the timer hits the public URL — that is the surface real crawlers see.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from smedjan import ntfy, sources

log = logging.getLogger("smedjan.sacred_byte_verifier")

DEFAULT_BASE_URL    = "https://nerq.ai"
DEFAULT_SAMPLE_SIZE = 500
DEFAULT_CONCURRENCY = 16
DEFAULT_TIMEOUT_S   = 15
COVERAGE_FLOOR      = 0.99   # below this, alert + enqueue regression

# Substrings (not regex) — fast `in` membership beats compiled patterns when
# we don't need capture groups. The strings are intentionally narrow so a
# stray `pplx-verdict-foo` class or a comment doesn't false-positive.
SACRED_BYTES: dict[str, tuple[str, ...]] = {
    # Either single- or double-quoted form is accepted — Jinja escapes vary.
    "pplx_verdict":            ('class="pplx-verdict"', "class='pplx-verdict'"),
    "ai_summary":              ('class="ai-summary"',   "class='ai-summary'"),
    # SpeakableSpecification is a stable schema.org type identifier.
    "speakable_specification": ('SpeakableSpecification',),
    # FAQPage may appear with or without space after the colon depending on
    # whether json.dumps was called with separators= or not.
    "faq_page":                ('"@type":"FAQPage"', '"@type": "FAQPage"'),
}

REPORT_DIR    = Path(os.path.expanduser("~/smedjan/audits"))
SMEDJAN_CLI   = "/Users/anstudio/agentindex/scripts/smedjan"
USER_AGENT    = "smedjan-sacred-byte-verifier/1.0 (+https://nerq.ai/contact)"


# ── Data classes ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PageResult:
    slug: str
    url: str
    status: int            # 0 == fetch failed (network error / timeout)
    error: str | None
    present: dict[str, bool]   # byte_name -> True iff present


# ── Slug sampling ───────────────────────────────────────────────────────

def sample_slugs(n: int) -> list[str]:
    """Return up to ``n`` random enriched slugs.

    Uses ``ORDER BY random() LIMIT n`` — fine at this sample size; the
    table has ~2.5M enriched rows and the query plan is a sequential scan
    capped by LIMIT.
    """
    with sources.nerq_readonly_cursor() as (_, cur):
        cur.execute(
            "SELECT slug FROM public.software_registry "
            "WHERE enriched_at IS NOT NULL "
            "ORDER BY random() LIMIT %s",
            (n,),
        )
        return [r[0] for r in cur.fetchall()]


# ── Fetch + check ───────────────────────────────────────────────────────

def _check_bytes(html: str) -> dict[str, bool]:
    """Return ``{byte_name: present?}`` for the four sacred bytes."""
    return {
        name: any(needle in html for needle in needles)
        for name, needles in SACRED_BYTES.items()
    }


def _fetch_one(slug: str, base_url: str, timeout: int) -> PageResult:
    # Slugs are stored verbatim; some carry non-ASCII (é, ü, …) which must
    # be percent-encoded before hitting urllib's ASCII-only header path.
    url = f"{base_url.rstrip('/')}/safe/{urllib.parse.quote(slug, safe='')}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # Read the body anyway — a 4xx/5xx with the right template *could*
        # still ship the bytes; we want to know about that.
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return PageResult(
            slug=slug, url=url, status=e.code, error=f"http {e.code}",
            present=_check_bytes(body),
        )
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return PageResult(
            slug=slug, url=url, status=0, error=str(e)[:120],
            present={k: False for k in SACRED_BYTES},
        )
    return PageResult(
        slug=slug, url=url, status=status, error=None,
        present=_check_bytes(body),
    )


def fetch_all(
    slugs: list[str], *, base_url: str, concurrency: int, timeout: int
) -> list[PageResult]:
    results: list[PageResult] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_fetch_one, s, base_url, timeout): s for s in slugs}
        for i, fut in enumerate(as_completed(futures), start=1):
            results.append(fut.result())
            if i % 50 == 0:
                log.info("fetched %d / %d", i, len(slugs))
    return results


# ── Coverage + report ───────────────────────────────────────────────────

def coverage(results: list[PageResult]) -> dict[str, float]:
    """Coverage per byte over the *fetched* sample (network failures count
    as failures — a page we couldn't reach can't be serving the bytes)."""
    n = len(results) or 1
    return {
        name: sum(1 for r in results if r.present.get(name)) / n
        for name in SACRED_BYTES
    }


def write_report(
    results: list[PageResult],
    cov: dict[str, float],
    *,
    base_url: str,
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    now      = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fetched  = len(results)
    failed   = sum(1 for r in results if r.status == 0)
    non_2xx  = sum(1 for r in results if r.status and not (200 <= r.status < 300))

    lines: list[str] = [
        "# sacred_byte_verifier — audit report",
        "",
        f"- Generated (UTC): {now}",
        f"- Base URL: `{base_url}`",
        f"- Sample size: **{fetched}**",
        f"- Network failures: {failed}",
        f"- Non-2xx HTTP responses: {non_2xx}",
        f"- Coverage floor: {COVERAGE_FLOOR * 100:.0f}%",
        "",
        "## Coverage per sacred byte",
        "",
        "| Byte | Coverage | Pass? |",
        "|------|----------|-------|",
    ]
    for name in sorted(SACRED_BYTES):
        c = cov.get(name, 0.0)
        ok = "yes" if c >= COVERAGE_FLOOR else "**NO**"
        lines.append(f"| `{name}` | {c * 100:.2f}% | {ok} |")

    # Per-page failures: only show pages missing ≥ 1 byte. Cap the table
    # at 200 rows so a catastrophic regression doesn't produce a 500 KB
    # markdown file. The full breakdown lives in the enqueued task body.
    failures = [
        r for r in results
        if not all(r.present.get(b) for b in SACRED_BYTES)
    ]
    lines += ["", f"## Pages missing ≥ 1 byte ({len(failures)})", ""]
    if failures:
        lines += ["| Slug | Status | Missing | Error |",
                  "|------|--------|---------|-------|"]
        for r in failures[:200]:
            missing = ",".join(b for b in sorted(SACRED_BYTES) if not r.present.get(b))
            err = (r.error or "").replace("|", "\\|")
            lines.append(f"| `{r.slug}` | {r.status} | {missing} | {err} |")
        if len(failures) > 200:
            lines.append(f"| ... | | | (truncated; {len(failures) - 200} more) |")
    else:
        lines.append("(none)")
    lines.append("")
    out_path.write_text("\n".join(lines))


# ── Regression follow-up ────────────────────────────────────────────────

def _regression_payload(results: list[PageResult]) -> str:
    """Compact JSON breakdown of every page missing at least one byte.

    Embedded in the enqueued task description so the responder doesn't
    have to re-run the verifier just to see *which* pages broke.
    """
    failures = []
    for r in results:
        miss = [b for b in sorted(SACRED_BYTES) if not r.present.get(b)]
        if not miss:
            continue
        failures.append({
            "slug": r.slug,
            "status": r.status,
            "missing": miss,
            "error": r.error,
        })
    return json.dumps({"failures": failures}, ensure_ascii=False)


def enqueue_regression(
    results: list[PageResult],
    cov: dict[str, float],
    *,
    base_url: str,
    report_path: Path,
) -> str | None:
    """Idempotent per-6h-window: ``sacred-byte-regression-<YYYYMMDDHH>``.

    Re-running the verifier inside the same 6h window won't enqueue a
    duplicate. If the regression spans windows it will get a fresh task
    each window — which is correct: each window is a fresh data point.
    """
    bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    tid    = f"sacred-byte-regression-{bucket}"

    show = subprocess.run(
        [SMEDJAN_CLI, "queue", "show", tid],
        capture_output=True, text=True, check=False,
    )
    if show.returncode == 0:
        log.info("regression task %s already exists; skipping enqueue", tid)
        return None

    breakdown_json = _regression_payload(results)
    cov_str = ", ".join(f"{name}={cov[name]*100:.2f}%" for name in sorted(SACRED_BYTES))

    title = f"Sacred-byte regression: {bucket}"
    description = (
        f"sacred_byte_verifier sampled {len(results)} enriched /safe/* pages "
        f"against {base_url} and observed coverage below the {COVERAGE_FLOOR*100:.0f}% "
        f"floor: {cov_str}. Audit report: {report_path}. "
        f"Per-page failure breakdown (JSON): {breakdown_json}"
    )
    acceptance = (
        "Identify the template path that stopped emitting the missing byte(s), "
        "patch it, redeploy, and re-run the verifier — coverage must be back "
        f">= {COVERAGE_FLOOR*100:.0f}% across all four bytes."
    )
    cmd = [
        SMEDJAN_CLI, "queue", "add",
        "--id", tid,
        "--title", title,
        "--description", description,
        "--acceptance", acceptance,
        "--risk", "high",
        "--whitelist", "agentindex/agent_safety_pages.py",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode == 0:
        log.info("enqueued %s", tid)
        return tid
    log.error("queue add failed for %s (rc=%d): %s",
              tid, res.returncode, (res.stderr or "").strip()[:300])
    return None


# ── Entry point ─────────────────────────────────────────────────────────

def run(
    *,
    base_url: str,
    sample_size: int,
    concurrency: int,
    timeout: int,
    dry_run: bool,
    report_path: Path,
) -> int:
    log.info("sampling %d enriched slugs from Nerq RO replica", sample_size)
    slugs = sample_slugs(sample_size)
    log.info("sampled %d slugs; fetching from %s (concurrency=%d, timeout=%ds)",
             len(slugs), base_url, concurrency, timeout)

    results = fetch_all(slugs, base_url=base_url, concurrency=concurrency, timeout=timeout)
    cov = coverage(results)
    log.info("coverage: %s",
             ", ".join(f"{n}={cov[n]*100:.2f}%" for n in sorted(SACRED_BYTES)))

    write_report(results, cov, base_url=base_url, out_path=report_path)
    log.info("report written: %s", report_path)

    breached = [n for n, c in cov.items() if c < COVERAGE_FLOOR]
    if not breached:
        log.info("all bytes >= %.0f%% — nothing to do", COVERAGE_FLOOR * 100)
        return 0

    summary = ", ".join(f"{n}={cov[n]*100:.2f}%" for n in breached)
    log.warning("coverage breach: %s", summary)

    if dry_run:
        log.info("[DRY-RUN] would ntfy + enqueue regression task")
        return 0

    ntfy.push(
        title="[SMEDJAN] sacred-byte regression",
        body=f"{len(breached)} byte(s) below {COVERAGE_FLOOR*100:.0f}%: {summary}. Report: {report_path}",
        priority="high",
        tags="rotating_light",
    )
    enqueue_regression(results, cov, base_url=base_url, report_path=report_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sacred_byte_verifier",
        description="Sample enriched /safe/* pages and verify SEO/GEO sacred bytes.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"target host (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE,
                        help=f"slugs to sample (default: {DEFAULT_SAMPLE_SIZE})")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help=f"parallel fetches (default: {DEFAULT_CONCURRENCY})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                        help=f"per-request timeout seconds (default: {DEFAULT_TIMEOUT_S})")
    parser.add_argument("--dry-run", action="store_true",
                        help="check + report; do NOT ntfy or enqueue.")
    parser.add_argument("--report",
                        type=Path,
                        default=None,
                        help="explicit report path (default: ~/smedjan/audits/sacred_byte_<ts>.md)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="DEBUG-level logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    report_path = args.report or (
        REPORT_DIR / f"sacred_byte_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.md"
    )

    try:
        return run(
            base_url=args.base_url,
            sample_size=args.sample_size,
            concurrency=args.concurrency,
            timeout=args.timeout,
            dry_run=args.dry_run,
            report_path=report_path,
        )
    except sources.SourceUnavailable as e:
        log.error("Nerq RO replica unavailable: %s", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
