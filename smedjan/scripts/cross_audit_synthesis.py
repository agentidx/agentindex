"""cross_audit_synthesis.py — weekly synthesis over the three Nerq audits.

Joins the latest ``query`` / ``citation`` / ``conversion`` audit reports
from ``~/smedjan/audit-reports/`` (one per type, filename pattern
``{YYYY-MM-DD}-{type}.md`` as produced by ``smedjan.audit_scheduler``),
extracts ``## `` findings, clusters them into themes, and flags every
theme that carries findings from **at least two** of the three audits as
an "intersection of concerns".

For each intersection finding the script writes a synthesis markdown
report to ``~/smedjan/audit-reports/{YYYYMMDD}-cross-audit-synthesis.md``
and enqueues an L1-L5 follow-up task on the factory via the
``scripts/smedjan queue add`` CLI — the layer / session-affinity are
chosen by a small theme table so the task routes to the correct stream.

Invocation
----------
    python3 -m smedjan.scripts.cross_audit_synthesis            # weekly run
    python3 -m smedjan.scripts.cross_audit_synthesis --dry-run  # no enqueue
    python3 -m smedjan.scripts.cross_audit_synthesis --self-test

``--self-test`` writes synthetic audit fixtures to a temp dir, runs the
full pipeline against them with ``--dry-run``, and asserts at least one
intersection task would have been enqueued. Used from CI / task-runner
acceptance without touching ``~/smedjan/audit-reports/`` or the smedjan
DB.

Exit codes
----------
    0  synthesis complete (report written; tasks enqueued or dry-run logged)
    1  fewer than 2 audit types present — nothing to intersect
    2  reports directory missing
    3  enqueue CLI returned non-zero for at least one task
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger("smedjan.cross_audit_synthesis")

AUDIT_TYPES = ("query", "citation", "conversion")

DEFAULT_REPORTS_DIR = Path("~/smedjan/audit-reports").expanduser()
DEFAULT_SMEDJAN_CLI = Path("~/agentindex/scripts/smedjan").expanduser()

# Regex for the ``{YYYY-MM-DD}-{type}.md`` pattern from audit_scheduler.
REPORT_NAME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})-(?P<type>query|citation|conversion)\.md$"
)

# Findings are ``## `` level headings inside each audit report. H2s that
# clearly belong to the report's own executive scaffolding (summary /
# table of contents / appendix) should be skipped — they are not
# actionable findings.
FINDING_HEADER_RE = re.compile(r"^##\s+(?!#)(?P<title>.+?)\s*$", re.MULTILINE)
SCAFFOLDING_TITLES = {
    "executive summary", "summary", "table of contents", "toc",
    "appendix", "methodology", "references", "data sources",
}

SEVERITY_RE = re.compile(
    r"\bseverity[:\s]+(?P<sev>low|medium|high|critical)\b", re.IGNORECASE
)
RECOMMENDATION_RE = re.compile(
    r"(?im)^(?:\*\*)?recommendation(?:\*\*)?[:\s]*(?P<body>.+?)(?:\n\n|\Z)",
    re.DOTALL,
)


# ── Theme table ──────────────────────────────────────────────────────────
# Each theme maps to a layer (L1-L5), a worker session_affinity tag
# (a/b/c/d), and a bag of keywords that, if present in a finding's
# title or body, assign the finding to that theme. Themes are ordered —
# the first match wins. Anything unmatched falls to ``_default``.

@dataclass(frozen=True)
class Theme:
    key: str
    layer: str            # "L1".."L5"
    affinity: str         # "a".."d"
    whitelist: tuple[str, ...]
    summary: str
    keywords: tuple[str, ...]


THEMES: tuple[Theme, ...] = (
    Theme(
        key="ctr_titles",
        layer="L1", affinity="a",
        whitelist=("agentindex/agent_safety_pages.py",
                   "agentindex/crypto/templates/"),
        summary="Title / meta / SERP snippet rewrite",
        keywords=(
            "ctr", "click-through", "click through", "title tag",
            "meta description", "snippet", "serp snippet",
        ),
    ),
    Theme(
        key="content_depth",
        layer="L1", affinity="a",
        whitelist=("agentindex/agent_safety_pages.py",
                   "agentindex/crypto/templates/"),
        summary="King-template content depth expansion",
        keywords=(
            "thin content", "content depth", "king", "template depth",
            "5-dim", "five dimension", "jurisdiction",
        ),
    ),
    Theme(
        key="compare_pages",
        layer="L1", affinity="a",
        whitelist=("agentindex/agent_safety_pages.py",
                   "agentindex/crypto/templates/compare/"),
        summary="/compare/ page conversion fix",
        keywords=("compare", "comparison", "versus", " vs "),
    ),
    Theme(
        key="entity_5xx",
        layer="L2", affinity="b",
        whitelist=("agentindex/api/discovery.py", "agentindex/smedjan/"),
        summary="Entity-page 5xx / empty-shell mitigation",
        keywords=(
            "502", "500 error", "5xx", "empty shell", "connection refused",
            "timeout", "entity page error",
        ),
    ),
    Theme(
        key="unrendered_data",
        layer="L2", affinity="b",
        whitelist=("agentindex/agent_safety_pages.py",
                   "agentindex/smedjan/"),
        summary="Surface currently-unrendered DB columns on the page",
        keywords=(
            "unrendered", "not surfaced", "missing from page",
            "external_trust_signals", "dependency_edges", "prediction_signals",
            "block 2a", "block 2b", "block 2c",
        ),
    ),
    Theme(
        key="citation_surface",
        layer="L2", affinity="b",
        whitelist=("agentindex/agent_safety_pages.py",
                   "agentindex/crypto/templates/"),
        summary="Citation surface hardening (sacred bytes / JSON-LD / speakable)",
        keywords=(
            "sacred byte", "json-ld", "json ld", "speakable", "faqpage",
            "citation", "ai citation", "pplx-verdict",
        ),
    ),
    Theme(
        key="ai_demand",
        layer="L3", affinity="c",
        whitelist=("agentindex/smedjan/", "agentindex/analytics.py"),
        summary="AI-demand prioritisation / zero-result queries",
        keywords=(
            "ai demand", "ai-demand", "zero result", "zero-result",
            "zero impression", "demand signal", "preflight",
        ),
    ),
    Theme(
        key="data_moat_endpoint",
        layer="L4", affinity="c",
        whitelist=("agentindex/api/endpoints/", "agentindex/api/discovery.py"),
        summary="Data-moat endpoint gap (new /rating, /trust, /ndd surface)",
        keywords=(
            "endpoint", "api surface", "data moat", "/rating", "/trust",
            "/ndd", "oracle",
        ),
    ),
    Theme(
        key="distribution",
        layer="L5", affinity="d",
        whitelist=("docs/strategy/", "agentindex/smedjan/"),
        summary="Distribution / outreach / placement",
        keywords=(
            "distribution", "outreach", "placement", "backlink",
            "syndication", "referral channel",
        ),
    ),
    Theme(
        key="funnel",
        layer="L5", affinity="d",
        whitelist=("agentindex/agent_safety_pages.py",
                   "agentindex/analytics.py"),
        summary="AI-to-human funnel drop-off fix",
        keywords=(
            "funnel", "drop-off", "dropoff", "bounce", "engagement",
            "session length", "conversion",
        ),
    ),
)

DEFAULT_THEME = Theme(
    key="_default",
    layer="L2", affinity="b",
    whitelist=("agentindex/smedjan/",),
    summary="Cross-cutting concern — refine by layer lead",
    keywords=(),
)


# ── Data types ───────────────────────────────────────────────────────────

@dataclass
class Finding:
    audit_type: str
    title: str
    severity: str
    recommendation: str
    body: str


@dataclass
class Cluster:
    theme: Theme
    findings: list[Finding] = field(default_factory=list)

    @property
    def audit_types(self) -> set[str]:
        return {f.audit_type for f in self.findings}

    @property
    def is_intersection(self) -> bool:
        return len(self.audit_types) >= 2

    @property
    def worst_severity(self) -> str:
        order = ("low", "medium", "high", "critical")
        worst = "low"
        for f in self.findings:
            if order.index(f.severity) > order.index(worst):
                worst = f.severity
        return worst


# ── Report discovery + parsing ───────────────────────────────────────────

def find_latest_reports(reports_dir: Path) -> dict[str, Path]:
    """Return ``{audit_type: path}`` for the newest report per type."""
    if not reports_dir.is_dir():
        return {}
    latest: dict[str, tuple[str, Path]] = {}
    for entry in reports_dir.iterdir():
        if not entry.is_file():
            continue
        m = REPORT_NAME_RE.match(entry.name)
        if not m:
            continue
        date, atype = m.group("date"), m.group("type")
        existing = latest.get(atype)
        if existing is None or date > existing[0]:
            latest[atype] = (date, entry)
    return {atype: p for atype, (_d, p) in latest.items()}


def parse_findings(path: Path, audit_type: str) -> list[Finding]:
    text = path.read_text(encoding="utf-8", errors="replace")
    headers = list(FINDING_HEADER_RE.finditer(text))
    findings: list[Finding] = []
    for idx, m in enumerate(headers):
        title = m.group("title").strip().lstrip("0123456789. ").strip()
        norm = title.lower().strip().rstrip(".").strip()
        if norm in SCAFFOLDING_TITLES:
            continue
        # Body runs from this header to the next (or EOF).
        start = m.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        body = text[start:end].strip()
        sev_m = SEVERITY_RE.search(body)
        severity = sev_m.group("sev").lower() if sev_m else "low"
        rec_m = RECOMMENDATION_RE.search(body)
        recommendation = rec_m.group("body").strip() if rec_m else ""
        findings.append(Finding(
            audit_type=audit_type,
            title=title,
            severity=severity,
            recommendation=recommendation,
            body=body,
        ))
    return findings


# ── Clustering ───────────────────────────────────────────────────────────

def classify(finding: Finding) -> Theme:
    haystack = f"{finding.title}\n{finding.body}".lower()
    for theme in THEMES:
        for kw in theme.keywords:
            if kw in haystack:
                return theme
    return DEFAULT_THEME


def cluster_findings(findings: list[Finding]) -> list[Cluster]:
    by_theme: dict[str, Cluster] = {}
    for f in findings:
        t = classify(f)
        cluster = by_theme.setdefault(t.key, Cluster(theme=t))
        cluster.findings.append(f)
    # Stable ordering: intersection first, then by layer, then by key.
    return sorted(
        by_theme.values(),
        key=lambda c: (not c.is_intersection, c.theme.layer, c.theme.key),
    )


# ── Markdown report ──────────────────────────────────────────────────────

def render_report(
    *,
    today_iso: str,
    sources: dict[str, Path],
    clusters: list[Cluster],
) -> str:
    lines: list[str] = []
    lines.append(f"# Cross-audit synthesis — {today_iso}")
    lines.append("")
    lines.append(
        "Synthesis across the latest `query`, `citation`, and `conversion` "
        "audits. A *cross-cutting concern* is a theme that appears in **≥ 2** "
        "of the three audits — those findings are the most load-bearing and "
        "are enqueued as L1-L5 follow-up tasks."
    )
    lines.append("")
    lines.append("## Source audits")
    for atype in AUDIT_TYPES:
        path = sources.get(atype)
        if path is None:
            lines.append(f"- **{atype}**: _(missing — excluded from synthesis)_")
        else:
            lines.append(f"- **{atype}**: `{path}`")
    lines.append("")

    intersections = [c for c in clusters if c.is_intersection]
    lines.append(
        f"## Intersection findings ({len(intersections)} theme"
        f"{'s' if len(intersections) != 1 else ''})"
    )
    lines.append("")
    if not intersections:
        lines.append("_No theme appeared in ≥ 2 audits — no follow-ups enqueued._")
        lines.append("")
    for c in intersections:
        audit_list = ", ".join(sorted(c.audit_types))
        lines.append(
            f"### {c.theme.key} → {c.theme.layer} (worst severity: "
            f"{c.worst_severity})"
        )
        lines.append("")
        lines.append(
            f"- **Theme summary:** {c.theme.summary}"
        )
        lines.append(f"- **Appears in:** {audit_list}")
        lines.append(f"- **Suggested affinity:** `{c.theme.affinity}`")
        lines.append("- **Source findings:**")
        for f in c.findings:
            rec = (f.recommendation or "").splitlines()[0][:160]
            lines.append(
                f"  - *{f.audit_type}* — **{f.title}** _(severity: "
                f"{f.severity})_"
            )
            if rec:
                lines.append(f"    - recommendation: {rec}")
        lines.append("")

    lines.append("## Single-audit findings (informational)")
    lines.append("")
    singles = [c for c in clusters if not c.is_intersection]
    if not singles:
        lines.append("_All findings cluster into intersection themes._")
        lines.append("")
    for c in singles:
        atype = next(iter(c.audit_types))
        lines.append(
            f"- `{c.theme.key}` ({c.theme.layer}) — {len(c.findings)} finding"
            f"{'s' if len(c.findings) != 1 else ''} from *{atype}* only"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


# ── Task enqueue ─────────────────────────────────────────────────────────

def _build_task_description(
    cluster: Cluster,
    sources: dict[str, Path],
    report_path: Path,
) -> str:
    lines: list[str] = []
    lines.append(
        f"Cross-audit synthesis finding — theme `{cluster.theme.key}` appears "
        f"in {len(cluster.audit_types)} of the 3 Nerq audits "
        f"({', '.join(sorted(cluster.audit_types))})."
    )
    lines.append("")
    lines.append(f"Theme summary: {cluster.theme.summary}")
    lines.append(f"Worst severity across source findings: {cluster.worst_severity}")
    lines.append("")
    lines.append("Source audits:")
    for atype in sorted(cluster.audit_types):
        p = sources.get(atype)
        if p:
            lines.append(f"  - {atype}: {p}")
    lines.append(f"Synthesis report: {report_path}")
    lines.append("")
    lines.append("Source findings:")
    for f in cluster.findings:
        lines.append(f"  - [{f.audit_type}] {f.title} (severity: {f.severity})")
        if f.recommendation:
            first = f.recommendation.splitlines()[0][:240]
            lines.append(f"      recommendation: {first}")
    lines.append("")
    lines.append(
        "Deliverable: one commit on branch smedjan-factory-v0 that advances "
        f"the {cluster.theme.layer} line on this cross-audit theme. Scope "
        "narrowly — the goal is to close the intersection concern, not to "
        "rewrite the layer."
    )
    return "\n".join(lines)


def _task_id(today_compact: str, seq: int) -> str:
    return f"CAS-{today_compact}-{seq:02d}"


def enqueue_cluster(
    cluster: Cluster,
    *,
    task_id: str,
    sources: dict[str, Path],
    report_path: Path,
    cli_path: Path,
    dry_run: bool,
) -> tuple[int, list[str]]:
    description = _build_task_description(cluster, sources, report_path)
    title = (
        f"{cluster.theme.layer} cross-audit: {cluster.theme.summary} "
        f"({'/'.join(sorted(cluster.audit_types))})"
    )[:200]
    acceptance = (
        f"{cluster.theme.layer} action taken that references the source "
        f"audits ({', '.join(sorted(cluster.audit_types))}) and resolves or "
        f"measurably advances theme `{cluster.theme.key}`. Synthesis "
        f"report {report_path.name} links to the completed work."
    )
    cmd = [
        str(cli_path), "queue", "add",
        "--id", task_id,
        "--title", title,
        "--description", description,
        "--acceptance", acceptance,
        "--risk", "low",
        "--priority", "60",
        "--session-group", cluster.theme.layer,
        "--session-affinity", cluster.theme.affinity,
        "--whitelist", ",".join(cluster.theme.whitelist),
    ]
    if dry_run:
        log.info("[dry-run] would enqueue %s (%s)", task_id, cluster.theme.layer)
        return 0, cmd
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log.error(
            "enqueue %s failed (rc=%s): %s",
            task_id, r.returncode, (r.stderr or r.stdout).strip(),
        )
    else:
        log.info("enqueued %s (%s)", task_id, cluster.theme.layer)
    return r.returncode, cmd


# ── Orchestrator ─────────────────────────────────────────────────────────

def synthesise(
    *,
    reports_dir: Path,
    output_path: Path | None,
    cli_path: Path,
    today: datetime,
    dry_run: bool,
) -> int:
    if not reports_dir.exists():
        log.error("reports dir missing: %s", reports_dir)
        return 2
    sources = find_latest_reports(reports_dir)
    if len(sources) < 2:
        log.warning(
            "only %d audit type(s) present (%s) — need ≥ 2 for intersection",
            len(sources), ", ".join(sorted(sources.keys())) or "none",
        )
        return 1

    findings: list[Finding] = []
    for atype, path in sources.items():
        parsed = parse_findings(path, atype)
        log.info("parsed %d findings from %s audit (%s)", len(parsed), atype, path)
        findings.extend(parsed)

    clusters = cluster_findings(findings)
    intersections = [c for c in clusters if c.is_intersection]

    today_iso = today.strftime("%Y-%m-%d")
    today_compact = today.strftime("%Y%m%d")
    if output_path is None:
        output_path = reports_dir / f"{today_compact}-cross-audit-synthesis.md"

    report_md = render_report(
        today_iso=today_iso, sources=sources, clusters=clusters,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_md, encoding="utf-8")
    log.info("wrote synthesis report: %s", output_path)

    if not intersections:
        log.info("no intersection themes — no follow-up tasks enqueued")
        return 0

    failures = 0
    for seq, cluster in enumerate(intersections, start=1):
        task_id = _task_id(today_compact, seq)
        rc, _cmd = enqueue_cluster(
            cluster,
            task_id=task_id,
            sources=sources,
            report_path=output_path,
            cli_path=cli_path,
            dry_run=dry_run,
        )
        if rc != 0:
            failures += 1
    return 3 if failures else 0


# ── Self-test ────────────────────────────────────────────────────────────

_FIXTURES = {
    "query": """# Query Audit — fixture

## CTR collapse on top-5 positions
severity: high

93% of queries where nerq.ai ranks pos <5 get zero clicks.
**Recommendation:** rewrite titles / meta descriptions on top-impression
pages to match query intent.

## Compare pages rank but don't click
severity: medium

7,095 /compare/ pages in GSC; only 255 earned ≥1 click.
**Recommendation:** upgrade /compare/ templates with content depth.

## Intent gap owned by incumbents
severity: high

Target queries return nerq.ai nowhere in top 10.
**Recommendation:** data-moat endpoint for /rating to outflank incumbents.
""",
    "citation": """# Citation Audit — fixture

## AI citation surface missing speakable
severity: high

External LLMs cite fragments without JSON-LD speakable hints.
**Recommendation:** reinforce sacred bytes on entity pages.

## CTR collapse on cited pages
severity: medium

Cited pages see impressions but no clicks — title snippet mismatch.
**Recommendation:** rewrite titles on cited entity pages.

## Unrendered trust score not carried
severity: medium

LLMs cite page but cannot quote Trust Score — not surfaced in body text.
**Recommendation:** surface Block 2a external_trust_signals.
""",
    "conversion": """# Conversion Audit — fixture

## AI-referral funnel drops on compare pages
severity: high

Visitors arriving via AI citation on /compare/ bounce at 92%.
**Recommendation:** /compare/ conversion fix with trust-score CTA.

## Zero-result queries indicate demand gap
severity: medium

3% of AI-referred sessions hit zero-result pages.
**Recommendation:** ai-demand prioritisation for missing verticals.

## Endpoint gap for agent-to-agent
severity: high

Stripe Tempo traffic cannot consume a /rating endpoint.
**Recommendation:** data-moat /rating endpoint for agent consumers.
""",
}


def _run_self_test() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with tempfile.TemporaryDirectory(prefix="cas-selftest-") as tmp:
        reports_dir = Path(tmp) / "audit-reports"
        reports_dir.mkdir()
        today = datetime(2026, 4, 19, 12, 0, 0)
        iso = today.strftime("%Y-%m-%d")
        for atype, body in _FIXTURES.items():
            (reports_dir / f"{iso}-{atype}.md").write_text(body, encoding="utf-8")

        # Run fully dry so no CLI / DB is touched.
        rc = synthesise(
            reports_dir=reports_dir,
            output_path=None,
            cli_path=Path("/bin/true"),
            today=today,
            dry_run=True,
        )
        if rc != 0:
            log.error("self-test: synthesise returned %d", rc)
            return 10

        report_path = (
            reports_dir / f"{today.strftime('%Y%m%d')}-cross-audit-synthesis.md"
        )
        if not report_path.exists():
            log.error("self-test: report not written at %s", report_path)
            return 11
        md = report_path.read_text(encoding="utf-8")
        if "Intersection findings" not in md:
            log.error("self-test: report missing 'Intersection findings'")
            return 12
        # Count the synthesised intersection themes by re-running the
        # in-memory pipeline. The fixture is engineered to produce at
        # least two intersection themes (ctr_titles, compare_pages, etc).
        findings: list[Finding] = []
        for atype in _FIXTURES:
            findings.extend(parse_findings(reports_dir / f"{iso}-{atype}.md", atype))
        clusters = cluster_findings(findings)
        intersections = [c for c in clusters if c.is_intersection]
        if not intersections:
            log.error("self-test: no intersection clusters detected")
            return 13
        log.info(
            "self-test OK — %d intersection theme(s), report at %s",
            len(intersections), report_path,
        )
        return 0


# ── CLI ──────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        "cross_audit_synthesis",
        description=__doc__.splitlines()[0] if __doc__ else None,
    )
    p.add_argument(
        "--reports-dir",
        type=lambda s: Path(s).expanduser(),
        default=DEFAULT_REPORTS_DIR,
        help="directory holding the per-audit markdown reports",
    )
    p.add_argument(
        "--output",
        type=lambda s: Path(s).expanduser(),
        default=None,
        help="override output path (default: <reports-dir>/<YYYYMMDD>-cross-audit-synthesis.md)",
    )
    p.add_argument(
        "--cli-path",
        type=lambda s: Path(s).expanduser(),
        default=DEFAULT_SMEDJAN_CLI,
        help="path to scripts/smedjan for queue-add subprocess",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="parse + render report, print the would-be queue-add commands "
             "without actually invoking the CLI",
    )
    p.add_argument(
        "--self-test", action="store_true",
        help="run against synthetic fixtures and verify intersection detection",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.self_test:
        return _run_self_test()
    return synthesise(
        reports_dir=args.reports_dir,
        output_path=args.output,
        cli_path=args.cli_path,
        today=datetime.now().astimezone(),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
