#!/usr/bin/env python3
"""
CI Gap Finder — Identify popular AI repos lacking security CI
=============================================================
Queries the agents database for high-star repos that have no evidence
of automated security scanning (GitHub Actions for security, Dependabot,
CodeQL, etc.).  A repo is flagged when its security_score is below 0.1,
which indicates no detectable security CI configuration.

Outputs:
  - docs/vulnerability-data/ci-gaps.json   (structured data)
  - docs/auto-reports/2026-03-14-ci-gaps.md (human-readable report)

Usage:
    python -m agentindex.intelligence.ci_gap_finder
    python -m agentindex.intelligence.ci_gap_finder --top 500
    python -m agentindex.intelligence.ci_gap_finder --security-threshold 0.15
"""

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.sql import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [ci-gap-finder] %(message)s",
)
log = logging.getLogger("ci-gap-finder")

REPORTS_DIR = Path(__file__).parent.parent.parent / "docs" / "auto-reports"
DATA_DIR = Path(__file__).parent.parent.parent / "docs" / "vulnerability-data"

SECURITY_THRESHOLD = 0.1
CODE_QUALITY_THRESHOLD = 0.2
TOP_N = 500
REPORT_TOP = 50

STAR_RANGES = [
    (100_000, ">100K"),
    (50_000, ">50K"),
    (10_000, ">10K"),
    (1_000, ">1K"),
    (0, "<1K"),
]


# ── Database query ──────────────────────────────────────────────────


def _fetch_top_repos(limit: int) -> list[dict]:
    """Pull top repos from PostgreSQL ordered by star count."""
    from agentindex.db.models import get_session

    session = get_session()
    try:
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        rows = session.execute(
            text("""
                SELECT
                    name, source_url, stars, forks,
                    security_score, quality_score,
                    trust_score, trust_components,
                    category, agent_type,
                    description, author, language,
                    last_source_update, first_indexed
                FROM agents
                WHERE is_active = true
                  AND source = 'github'
                  AND agent_type IN ('agent', 'mcp_server', 'tool')
                  AND stars > 0
                  AND name IS NOT NULL
                ORDER BY stars DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

        results = []
        for r in rows:
            m = dict(r._mapping)
            # Normalise trust_components from JSON string or dict
            tc = m.get("trust_components") or {}
            if isinstance(tc, str):
                try:
                    tc = json.loads(tc)
                except Exception:
                    tc = {}
            m["trust_components"] = tc
            results.append(m)

        log.info("Fetched %d repos from database", len(results))
        return results
    finally:
        session.close()


# ── Analysis ────────────────────────────────────────────────────────


def _extract_security_score(repo: dict) -> float:
    """Return the effective security score for a repo.

    Prefers the trust_components breakdown; falls back to the top-level
    security_score column.
    """
    tc = repo.get("trust_components") or {}

    # trust_components may store security under different keys
    for key in ("security", "security_score", "sec"):
        val = tc.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass

    # Fall back to the column value
    raw = repo.get("security_score")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass

    return 0.0


def _extract_code_quality(repo: dict) -> float:
    """Return the code quality component score."""
    tc = repo.get("trust_components") or {}

    for key in ("code_quality", "quality", "code"):
        val = tc.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass

    raw = repo.get("quality_score")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass

    return 0.0


def _star_bucket(stars: int) -> str:
    for threshold, label in STAR_RANGES:
        if stars >= threshold:
            return label
    return "<1K"


def _repo_slug(source_url: str) -> str:
    """Extract owner/repo from a GitHub URL."""
    if not source_url:
        return ""
    parts = source_url.rstrip("/").split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return source_url


def analyse(repos: list[dict], sec_threshold: float, cq_threshold: float) -> dict:
    """Identify CI gaps and build the report payload."""

    ci_gaps: list[dict] = []
    low_quality: list[dict] = []
    bucket_counts: dict[str, int] = {label: 0 for _, label in STAR_RANGES}
    bucket_totals: dict[str, int] = {label: 0 for _, label in STAR_RANGES}

    for repo in repos:
        stars = repo.get("stars") or 0
        sec = _extract_security_score(repo)
        cq = _extract_code_quality(repo)
        bucket = _star_bucket(stars)
        bucket_totals[bucket] = bucket_totals.get(bucket, 0) + 1

        entry = {
            "name": repo.get("name"),
            "source_url": repo.get("source_url"),
            "slug": _repo_slug(repo.get("source_url", "")),
            "stars": stars,
            "forks": repo.get("forks") or 0,
            "security_score": round(sec, 4),
            "code_quality_score": round(cq, 4),
            "trust_score": repo.get("trust_score"),
            "agent_type": repo.get("agent_type"),
            "category": repo.get("category"),
            "language": repo.get("language"),
            "author": repo.get("author"),
            "description": (repo.get("description") or "")[:200],
        }

        if sec < sec_threshold:
            ci_gaps.append(entry)
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

        if cq < cq_threshold:
            low_quality.append(entry)

    ci_gaps.sort(key=lambda x: x["stars"], reverse=True)
    low_quality.sort(key=lambda x: x["stars"], reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "repos_scanned": len(repos),
            "security_threshold": sec_threshold,
            "code_quality_threshold": cq_threshold,
        },
        "summary": {
            "total_without_security_ci": len(ci_gaps),
            "total_low_code_quality": len(low_quality),
            "pct_without_security_ci": round(
                len(ci_gaps) / max(len(repos), 1) * 100, 1
            ),
            "by_star_range": {
                label: {
                    "missing_security_ci": bucket_counts.get(label, 0),
                    "total": bucket_totals.get(label, 0),
                }
                for _, label in STAR_RANGES
            },
        },
        "ci_gaps": ci_gaps,
        "low_code_quality": low_quality[:REPORT_TOP],
    }


# ── Output ──────────────────────────────────────────────────────────


def _save_json(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info("JSON saved to %s (%d bytes)", path, path.stat().st_size)


def _render_markdown(report: dict, date_str: str) -> str:
    s = report["summary"]
    p = report["parameters"]
    lines = [
        f"# CI Gap Report — {date_str}",
        "",
        "Identifies popular AI agent/tool repos on GitHub that lack automated",
        "security CI (no GitHub Actions security scanning, no Dependabot, no CodeQL).",
        "",
        "## Summary",
        "",
        f"- **Repos scanned:** {p['repos_scanned']}",
        f"- **Without security CI:** {s['total_without_security_ci']} "
        f"({s['pct_without_security_ci']}%)",
        f"- **Low code quality:** {s['total_low_code_quality']}",
        f"- **Security threshold:** < {p['security_threshold']}",
        "",
        "## Breakdown by star range",
        "",
        "| Star range | Missing security CI | Total repos | % missing |",
        "|------------|--------------------:|------------:|----------:|",
    ]

    for _, label in STAR_RANGES:
        bucket = s["by_star_range"].get(label, {})
        missing = bucket.get("missing_security_ci", 0)
        total = bucket.get("total", 0)
        pct = round(missing / max(total, 1) * 100, 1)
        lines.append(f"| {label} | {missing} | {total} | {pct}% |")

    lines += [
        "",
        f"## Top {min(REPORT_TOP, len(report['ci_gaps']))} CI gaps (by stars)",
        "",
        "| # | Repo | Stars | Security | Code Quality | Type | Language |",
        "|---|------|------:|---------:|-------------:|------|----------|",
    ]

    for i, gap in enumerate(report["ci_gaps"][:REPORT_TOP], 1):
        name = gap["name"] or "unknown"
        url = gap["source_url"] or ""
        link = f"[{name}]({url})" if url else name
        lines.append(
            f"| {i} | {link} | {gap['stars']:,} "
            f"| {gap['security_score']:.2f} "
            f"| {gap['code_quality_score']:.2f} "
            f"| {gap['agent_type'] or '-'} "
            f"| {gap['language'] or '-'} |"
        )

    if report.get("low_code_quality"):
        lines += [
            "",
            "## Notable low code-quality repos",
            "",
            "| Repo | Stars | Code Quality | Security | Type |",
            "|------|------:|-------------:|---------:|------|",
        ]
        for gap in report["low_code_quality"][:20]:
            name = gap["name"] or "unknown"
            url = gap["source_url"] or ""
            link = f"[{name}]({url})" if url else name
            lines.append(
                f"| {link} | {gap['stars']:,} "
                f"| {gap['code_quality_score']:.2f} "
                f"| {gap['security_score']:.2f} "
                f"| {gap['agent_type'] or '-'} |"
            )

    lines += [
        "",
        "---",
        f"*Generated {report['generated_at']} by `agentindex.intelligence.ci_gap_finder`*",
        "",
    ]

    return "\n".join(lines)


def _save_markdown(report: dict, path: Path, date_str: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    md = _render_markdown(report, date_str)
    with open(path, "w") as f:
        f.write(md)
    log.info("Markdown saved to %s (%d bytes)", path, path.stat().st_size)


# ── Main ────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Find popular AI repos lacking security CI"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=TOP_N,
        help=f"Number of top repos to scan (default {TOP_N})",
    )
    parser.add_argument(
        "--security-threshold",
        type=float,
        default=SECURITY_THRESHOLD,
        help=f"Security score below which a repo is flagged (default {SECURITY_THRESHOLD})",
    )
    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=CODE_QUALITY_THRESHOLD,
        help=f"Code quality threshold for secondary flag (default {CODE_QUALITY_THRESHOLD})",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Date string for report filename (default today)",
    )
    args = parser.parse_args()

    log.info(
        "CI Gap Finder starting — top %d repos, security < %.2f",
        args.top,
        args.security_threshold,
    )

    repos = _fetch_top_repos(args.top)
    if not repos:
        log.error("No repos returned from database — aborting")
        return

    report = analyse(repos, args.security_threshold, args.quality_threshold)

    json_path = DATA_DIR / "ci-gaps.json"
    md_path = REPORTS_DIR / f"{args.date}-ci-gaps.md"

    _save_json(report, json_path)
    _save_markdown(report, md_path, args.date)

    s = report["summary"]
    log.info(
        "Done. %d/%d repos (%s%%) lack security CI.",
        s["total_without_security_ci"],
        report["parameters"]["repos_scanned"],
        s["pct_without_security_ci"],
    )


if __name__ == "__main__":
    main()
