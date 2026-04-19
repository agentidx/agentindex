"""F1 v2 shared runner — /safe/* antipattern spot-check.

Single source of truth for the F1 fallback quality audit. Driven by
`~/smedjan/config/f1_antipatterns.json` (v2). Replaces the per-task
`FB-F1-*.py` copies that drifted in naming + detection.

Outputs
-------
- `~/smedjan/audits/<run-id>.md`          canonical FB-F1 audit table
- `~/smedjan/audits/F1-trend.jsonl`       one JSONL row appended per run

Usage
-----
    python -m scripts.f1_safe_antipattern_check --run-id FB-F1-20260419-031
    # or, for reproducible tests:
    python -m scripts.f1_safe_antipattern_check --run-id FB-F1-TEST-001 \\
        --fixture-file /tmp/f1_fixture.jsonl

Fixture format (one JSON object per line):
    {"slug": "foo/bar", "cohort": "enriched", "status": 502, "html": ""}

When `--fixture-file` is supplied, DB + HTTP are bypassed entirely.

Escalation
----------
Emits `STATUS: needs_approval` in the markdown audit if any of the
multi-trigger thresholds in the config fire:
  * any escalate-severity antipattern rate > antipattern_rate_pct
  * non-200 rate > non_200_rate_pct
  * fetch-error rate > fetch_error_rate_pct
  * elapsed > elapsed_escalate_seconds
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

CONFIG_PATH = os.path.expanduser("~/smedjan/config/f1_antipatterns.json")
AUDITS_DIR = os.path.expanduser("~/smedjan/audits")
TREND_PATH = os.path.join(AUDITS_DIR, "F1-trend.jsonl")
BASE_URL = "https://nerq.ai/safe/"
TIMEOUT = 15


# ── config ────────────────────────────────────────────────────────────


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path) as f:
        cfg = json.load(f)
    if cfg.get("version") != 2:
        raise RuntimeError(
            f"f1_antipatterns.json must be v2 (got {cfg.get('version')!r})"
        )
    for required in ("canonical_finding_order", "sample", "escalation",
                     "regex_patterns", "structural_checks"):
        if required not in cfg:
            raise RuntimeError(f"config missing required field: {required}")
    return cfg


def compile_patterns(cfg: dict) -> list[dict]:
    """Return [{name, severity, regex: compiled}, ...]."""
    out: list[dict] = []
    for p in cfg["regex_patterns"]:
        out.append({
            "name": p["name"],
            "severity": p.get("severity", "escalate"),
            "regex": re.compile(p["regex"], re.IGNORECASE | re.DOTALL),
        })
    return out


# ── fetch ─────────────────────────────────────────────────────────────


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "smedjan-audit/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


# ── slug picker ───────────────────────────────────────────────────────


def pick_slugs(cfg: dict) -> list[tuple[str, str]]:
    """Stratified slug pick — returns [(slug, cohort), ...].

    Cohorts: enriched / unenriched / low_trust. Enforces ≥1 per registry
    in the enriched stratum.
    """
    from smedjan import sources

    sample = cfg["sample"]
    strata = sample["strata"]
    enriched_n = int(strata.get("enriched", 0))
    unenriched_n = int(strata.get("unenriched", 0))
    low_trust_n = int(strata.get("low_trust", 0))
    low_trust_pool = int(sample.get("low_trust_pool_size", 50000))

    picks: list[tuple[str, str]] = []
    seen: set[str] = set()

    with sources.nerq_readonly_cursor() as (_, cur):
        # Enriched: 1 per registry first, then top up with randoms.
        cur.execute(
            """
            SELECT DISTINCT ON (registry) slug
            FROM software_registry
            WHERE enriched_at IS NOT NULL
              AND registry IS NOT NULL
            ORDER BY registry, random()
            """
        )
        per_reg = [r[0] for r in cur.fetchall()]
        if len(per_reg) >= enriched_n:
            per_reg = random.sample(per_reg, enriched_n)
            enriched_slugs = per_reg
        else:
            need = enriched_n - len(per_reg)
            cur.execute(
                """
                SELECT slug FROM software_registry
                WHERE enriched_at IS NOT NULL
                  AND NOT (slug = ANY(%s))
                ORDER BY random()
                LIMIT %s
                """,
                (per_reg, need),
            )
            enriched_slugs = per_reg + [r[0] for r in cur.fetchall()]
        for s in enriched_slugs:
            if s and s not in seen:
                seen.add(s)
                picks.append((s, "enriched"))

        if unenriched_n > 0:
            cur.execute(
                """
                SELECT slug FROM software_registry
                WHERE enriched_at IS NULL
                ORDER BY random()
                LIMIT %s
                """,
                (unenriched_n * 2,),  # over-pick to tolerate dedupe drop
            )
            for row in cur.fetchall():
                if row[0] and row[0] not in seen:
                    seen.add(row[0])
                    picks.append((row[0], "unenriched"))
                    if sum(1 for _, c in picks if c == "unenriched") >= unenriched_n:
                        break

        if low_trust_n > 0:
            cur.execute(
                """
                WITH bottom AS (
                    SELECT slug FROM software_registry
                    WHERE trust_score IS NOT NULL
                    ORDER BY trust_score ASC
                    LIMIT %s
                )
                SELECT slug FROM bottom
                ORDER BY random()
                LIMIT %s
                """,
                (low_trust_pool, low_trust_n * 2),
            )
            for row in cur.fetchall():
                if row[0] and row[0] not in seen:
                    seen.add(row[0])
                    picks.append((row[0], "low_trust"))
                    if sum(1 for _, c in picks if c == "low_trust") >= low_trust_n:
                        break

    return picks


def load_fixture(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rows.append(json.loads(line))
    return rows


# ── scan ──────────────────────────────────────────────────────────────


JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def scan(html: str, compiled: list[dict]) -> dict[str, bool]:
    """Return {finding_name: bool} for one page."""
    found: dict[str, bool] = {}
    for pat in compiled:
        found[pat["name"]] = bool(pat["regex"].search(html))

    jsonld_blocks = JSONLD_RE.findall(html)
    found["missing_jsonld"] = not jsonld_blocks
    broken = False
    for block in jsonld_blocks:
        try:
            json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            broken = True
            break
    found["broken_jsonld"] = broken
    return found


# ── escalation ────────────────────────────────────────────────────────


def evaluate_escalation(
    cfg: dict,
    finding_counts: dict[str, int],
    warning_findings: set[str],
    status_dist: dict[int, int],
    fetch_errors: int,
    effective_sample: int,
    elapsed_seconds: float,
) -> tuple[bool, list[str]]:
    gate = cfg["escalation"]
    reasons: list[str] = []
    if effective_sample <= 0:
        return False, reasons

    non_200 = sum(c for s, c in status_dist.items() if s != 200)
    non_200_pct = 100.0 * non_200 / effective_sample
    fe_pct = 100.0 * fetch_errors / effective_sample

    for name, count in finding_counts.items():
        if name in warning_findings:
            continue
        rate = 100.0 * count / effective_sample
        if rate > gate["antipattern_rate_pct"]:
            reasons.append(
                f"{name} rate {rate:.2f}% > {gate['antipattern_rate_pct']:.2f}%"
            )

    if non_200_pct > gate["non_200_rate_pct"]:
        reasons.append(
            f"non-200 rate {non_200_pct:.2f}% > {gate['non_200_rate_pct']:.2f}%"
        )
    if fe_pct > gate["fetch_error_rate_pct"]:
        reasons.append(
            f"fetch-error rate {fe_pct:.2f}% > {gate['fetch_error_rate_pct']:.2f}%"
        )
    if elapsed_seconds > gate["elapsed_escalate_seconds"]:
        reasons.append(
            f"elapsed {elapsed_seconds:.1f}s > {gate['elapsed_escalate_seconds']}s"
        )

    return bool(reasons), reasons


# ── render ────────────────────────────────────────────────────────────


def _fmt_status_dist(status_dist: dict[int, int]) -> str:
    return " ".join(f"{k}={v}" for k, v in sorted(status_dist.items()))


def render_audit(
    run_id: str,
    cfg: dict,
    sample_target: int,
    effective_sample: int,
    elapsed_seconds: float,
    status_dist: dict[int, int],
    fetch_errors: int,
    cohort_counts: dict[str, int],
    finding_counts: dict[str, int],
    finding_samples: dict[str, list[str]],
    warning_findings: set[str],
    escalate: bool,
    escalation_reasons: list[str],
    slow_run: bool,
) -> str:
    order = cfg["canonical_finding_order"]
    lines: list[str] = []
    lines.append(f"# {run_id} — /safe/* antipattern spot-check (F1 v2)")
    lines.append("")
    lines.append(f"- Pages requested: **{sample_target}**")
    lines.append(f"- Pages checked (effective sample): **{effective_sample}**")
    cohort_str = ", ".join(f"{k}={v}" for k, v in sorted(cohort_counts.items()))
    lines.append(f"- Cohort mix: {cohort_str or '—'}")
    lines.append(f"- Target: `{BASE_URL}<slug>`")
    lines.append(f"- Elapsed: {elapsed_seconds:.1f}s" + (" ⚠ slow_run" if slow_run else ""))
    lines.append(f"- HTTP status distribution: {_fmt_status_dist(status_dist) or '—'}")
    lines.append(f"- Fetch errors: {fetch_errors}")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines.append("| Finding | Severity | Count | Rate | Sample slugs |")
    lines.append("|---|---|---:|---:|---|")
    severity_map = {p["name"]: p.get("severity", "escalate") for p in cfg["regex_patterns"]}
    for check in cfg["structural_checks"]:
        severity_map[check["name"]] = check.get("severity", "escalate")
    for name in order:
        count = finding_counts.get(name, 0)
        rate = (100.0 * count / effective_sample) if effective_sample else 0.0
        samples = finding_samples.get(name) or []
        samples_str = ", ".join(samples) if samples else "—"
        severity = "warn" if name in warning_findings else severity_map.get(name, "escalate")
        lines.append(f"| {name} | {severity} | {count} | {rate:.2f}% | {samples_str} |")
    lines.append("")
    lines.append("## Escalation")
    lines.append("")
    if escalate:
        lines.append("**STATUS: needs_approval** — multi-trigger gate fired:")
        for r in escalation_reasons:
            lines.append(f"- {r}")
    else:
        lines.append("No multi-trigger threshold breached; no escalation required.")
    lines.append("")
    return "\n".join(lines)


def append_trend(trend_path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(trend_path), exist_ok=True)
    with open(trend_path, "a") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")


# ── main ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True,
                        help="FB-F1-YYYYMMDD-NNN run identifier")
    parser.add_argument("--config", default=CONFIG_PATH,
                        help="Path to f1_antipatterns.json (default: ~/smedjan/...)")
    parser.add_argument("--fixture-file",
                        help="JSONL file with {slug,cohort,status,html} rows. "
                             "When set, bypasses DB + HTTP.")
    parser.add_argument("--out-dir", default=AUDITS_DIR,
                        help="Directory to write the audit markdown into.")
    parser.add_argument("--trend-path", default=TREND_PATH,
                        help="Path to append the JSONL trend row to.")
    args = parser.parse_args(argv)

    if not re.match(r"^FB-F1-[A-Z0-9-]+$", args.run_id):
        print(f"ERROR: --run-id must match FB-F1-... (got {args.run_id!r})",
              file=sys.stderr)
        return 2

    cfg = load_config(args.config)
    compiled = compile_patterns(cfg)
    warning_findings = set(cfg.get("warning_findings", []))
    sample_target = int(cfg["sample"]["size"])

    t0 = time.time()

    if args.fixture_file:
        fixture_rows = load_fixture(args.fixture_file)
        work = [(row["slug"], row.get("cohort", "fixture"),
                 int(row.get("status", 0)), row.get("html", ""))
                for row in fixture_rows]
    else:
        picks = pick_slugs(cfg)
        if len(picks) < int(sample_target * 0.5):
            print(f"ERROR: only got {len(picks)} slugs from Nerq RO "
                  f"(target {sample_target})", file=sys.stderr)
            return 1
        work = []
        for slug, cohort in picks:
            status, html = fetch(BASE_URL + slug)
            work.append((slug, cohort, status, html))

    status_dist: dict[int, int] = defaultdict(int)
    fetch_errors = 0
    cohort_counts: dict[str, int] = defaultdict(int)
    finding_counts: dict[str, int] = defaultdict(int)
    finding_samples: dict[str, list[str]] = defaultdict(list)

    for slug, cohort, status, html in work:
        status_dist[status] += 1
        cohort_counts[cohort] += 1
        if status != 200 or not html:
            if status == 0:
                fetch_errors += 1
            continue
        result = scan(html, compiled)
        for name, hit in result.items():
            if hit:
                finding_counts[name] += 1
                if len(finding_samples[name]) < 3:
                    finding_samples[name].append(slug)

    elapsed = time.time() - t0
    effective_sample = len(work)

    escalate, reasons = evaluate_escalation(
        cfg, finding_counts, warning_findings,
        status_dist, fetch_errors, effective_sample, elapsed,
    )
    slow_run = elapsed > cfg["escalation"]["elapsed_warn_seconds"]

    out_path = os.path.join(args.out_dir, f"{args.run_id}.md")
    os.makedirs(args.out_dir, exist_ok=True)
    audit_md = render_audit(
        args.run_id, cfg, sample_target, effective_sample, elapsed,
        dict(status_dist), fetch_errors, dict(cohort_counts),
        dict(finding_counts), dict(finding_samples), warning_findings,
        escalate, reasons, slow_run,
    )
    with open(out_path, "w") as f:
        f.write(audit_md)

    ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    trend_row = {
        "run_id": args.run_id,
        "ts_utc": ts_utc,
        "sample_target": sample_target,
        "effective_sample": effective_sample,
        "elapsed_seconds": round(elapsed, 2),
        "slow_run": slow_run,
        "status_distribution": {str(k): v for k, v in sorted(status_dist.items())},
        "fetch_errors": fetch_errors,
        "cohort_counts": dict(cohort_counts),
        "finding_counts": {n: finding_counts.get(n, 0)
                           for n in cfg["canonical_finding_order"]},
        "escalate": escalate,
        "escalation_reasons": reasons,
        "config_version": cfg["version"],
        "fixture": bool(args.fixture_file),
    }
    append_trend(args.trend_path, trend_row)

    print(json.dumps({
        "run_id": args.run_id,
        "out_path": out_path,
        "trend_path": args.trend_path,
        "escalate": escalate,
        "reasons": reasons,
        "effective_sample": effective_sample,
        "elapsed_seconds": round(elapsed, 2),
        "finding_counts": trend_row["finding_counts"],
        "status_distribution": trend_row["status_distribution"],
        "fetch_errors": fetch_errors,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
