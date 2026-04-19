"""/hacked/{slug} — breach-history renderer.

Background
----------
`AUDIT-QUERY-20260418` finding #3 found 7,462 requests / 7 days hitting
`/hacked/<slug>` with 100 % 404 (the pattern had no route at all). About
3 % of hits were AI bots (Claude, ChatGPT) actively trying to cite the
URL; ~13 % were human. Option A of `FU-QUERY-20260418-03` was to ship a
renderer so the path serves 200 instead of 404.

The task brief named "entity_lookup breach-incident fields" as the data
source. `public.entity_lookup` has no breach columns (verified
2026-04-19); the actual breach data lives in `public.breach_history`
(962 rows, populated from HaveIBeenPwned and similar sources) plus
CVE counts on `public.software_registry`. This module joins those two
and falls back to a "no confirmed breach on record" page when neither
has a matching row — always HTTP 200, always with JSON-LD structured
data and a canonical link to `/was-<slug>-hacked`.

Mounted from `agentindex/api/discovery.py`. Read-only; never writes.
"""
from __future__ import annotations

import html as html_mod
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

logger = logging.getLogger("agentindex.api.endpoints.hacked")

router = APIRouter(tags=["hacked"])

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year
MY = date.today().strftime("%B %Y")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,199}$")


def _esc(t: Any) -> str:
    return html_mod.escape(str(t)) if t is not None else ""


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _fetch_breach(slug: str) -> list[dict[str, Any]]:
    from smedjan import sources

    sql = """
        SELECT entity_slug, entity_name, breach_date, severity,
               records_exposed, data_types, description, source
        FROM breach_history
        WHERE entity_slug = %s
        ORDER BY breach_date DESC NULLS LAST
        LIMIT 10
    """
    try:
        with sources.nerq_readonly_cursor(dict_cursor=True) as (_, cur):
            cur.execute(sql, [slug])
            return [dict(r) for r in cur.fetchall()]
    except sources.SourceUnavailable as exc:
        logger.warning("Nerq RO unavailable (breach_history) for /hacked/%s: %s", slug, exc)
        raise HTTPException(status_code=503, detail="upstream_unavailable") from exc


def _fetch_registry(slug: str) -> Optional[dict[str, Any]]:
    from smedjan import sources

    sql = """
        SELECT slug, registry, name, trust_score, trust_grade,
               cve_count, cve_critical, security_score,
               homepage_url, repository_url, enriched_at
        FROM software_registry
        WHERE slug = %s
        ORDER BY trust_score DESC NULLS LAST, enriched_at DESC NULLS LAST
        LIMIT 1
    """
    try:
        with sources.nerq_readonly_cursor(dict_cursor=True) as (_, cur):
            cur.execute(sql, [slug])
            row = cur.fetchone()
    except sources.SourceUnavailable as exc:
        logger.warning("Nerq RO unavailable (software_registry) for /hacked/%s: %s", slug, exc)
        raise HTTPException(status_code=503, detail="upstream_unavailable") from exc
    return dict(row) if row else None


def _pretty_name(slug: str, reg: Optional[dict[str, Any]], breaches: list[dict[str, Any]]) -> str:
    if breaches and breaches[0].get("entity_name"):
        return breaches[0]["entity_name"]
    if reg and reg.get("name"):
        return reg["name"]
    return slug.replace("-", " ").title()


def _verdict(breaches: list[dict[str, Any]], reg: Optional[dict[str, Any]]) -> tuple[str, str, str]:
    if breaches:
        worst = max(breaches, key=lambda b: {"critical": 3, "high": 2, "medium": 1, "low": 0}.get((b.get("severity") or "").lower(), 0))
        exposed = sum((b.get("records_exposed") or 0) for b in breaches)
        sev = (worst.get("severity") or "unknown").title()
        headline = f"{len(breaches)} Confirmed Breach{'es' if len(breaches) != 1 else ''}"
        detail = (
            f"{len(breaches)} breach record(s) on file. Worst severity: {sev}. "
            f"{exposed:,} records exposed across disclosed incidents."
            if exposed
            else f"{len(breaches)} breach record(s) on file. Worst severity: {sev}."
        )
        return headline, detail, "#dc2626"
    cve = (reg or {}).get("cve_count") or 0
    crit = (reg or {}).get("cve_critical") or 0
    if cve > 10:
        return (
            "Multiple Reported Vulnerabilities",
            f"{cve} publicly disclosed CVE entries ({crit} critical). No confirmed breach on record, but known vulnerabilities exist.",
            "#dc2626",
        )
    if cve > 0:
        return (
            f"{cve} Known Vulnerabilit{'ies' if cve != 1 else 'y'}",
            f"{cve} publicly disclosed CVE entr{'ies' if cve != 1 else 'y'}. No confirmed breach on record.",
            "#ca8a04",
        )
    return (
        "No Confirmed Breach on Record",
        "No breach entries found in Nerq's monitored sources (HaveIBeenPwned, NVD, GitHub Security Advisories, OSV.dev).",
        "#16a34a",
    )


def _render(slug: str, breaches: list[dict[str, Any]], reg: Optional[dict[str, Any]]) -> str:
    name = _pretty_name(slug, reg, breaches)
    headline, detail, color = _verdict(breaches, reg)
    canonical = f"{SITE}/hacked/{slug}"
    was_hacked_url = f"{SITE}/was-{slug}-hacked"
    safe_url = f"{SITE}/safe/{slug}"

    cve = (reg or {}).get("cve_count") or 0
    cve_crit = (reg or {}).get("cve_critical") or 0
    trust = (reg or {}).get("trust_score")
    grade = (reg or {}).get("trust_grade") or "N/A"
    registry = (reg or {}).get("registry") or ""

    breach_rows = ""
    for b in breaches:
        exp = b.get("records_exposed")
        exp_s = f"{exp:,}" if exp else "—"
        breach_rows += (
            f"<tr><td>{_esc(_iso(b.get('breach_date')) or '—')}</td>"
            f"<td>{_esc((b.get('severity') or '').title() or '—')}</td>"
            f"<td>{exp_s}</td>"
            f"<td>{_esc(b.get('source') or '—')}</td>"
            f"<td>{_esc(b.get('description') or '')}</td></tr>"
        )

    breach_section = (
        f"<h2>Disclosed Breach Incidents</h2>"
        f"<table><thead><tr><th>Date</th><th>Severity</th><th>Records Exposed</th><th>Source</th><th>Notes</th></tr></thead>"
        f"<tbody>{breach_rows}</tbody></table>"
        if breaches
        else ""
    )

    article_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"Has {name} Been Hacked? Breach History {YEAR}",
        "author": {"@type": "Organization", "name": "Nerq"},
        "publisher": {"@type": "Organization", "name": "Nerq", "url": SITE},
        "datePublished": TODAY,
        "dateModified": TODAY,
        "description": detail[:220],
        "mainEntityOfPage": canonical,
    }
    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f"Has {name} been hacked?",
                "acceptedAnswer": {"@type": "Answer", "text": detail},
            },
            {
                "@type": "Question",
                "name": f"How many CVEs does {name} have?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"{cve} CVE entries on record ({cve_crit} critical) as of {MY}.",
                },
            },
            {
                "@type": "Question",
                "name": f"Where does Nerq get {name}'s breach data?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Nerq monitors HaveIBeenPwned, the National Vulnerability Database (NVD), GitHub Security Advisories, and OSV.dev for each tracked entity.",
                },
            },
        ],
    }

    meta = (
        f'<meta name="nerq:type" content="hacked">'
        f'<meta name="nerq:entity" content="{_esc(name)}">'
        f'<meta name="nerq:breach_count" content="{len(breaches)}">'
        f'<meta name="nerq:cve_count" content="{cve}">'
        f'<meta name="nerq:verdict" content="{_esc(headline)}">'
        f'<meta name="nerq:updated" content="{TODAY}">'
    )

    desc = f"Has {name} been hacked? {headline}. {cve} CVEs on record. Breach history and incident analysis. Updated {MY}."[:160]

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Has {_esc(name)} Been Hacked? Breach History {YEAR} | Nerq</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
{meta}
<script type="application/ld+json">{json.dumps(article_ld, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(faq_ld, ensure_ascii=False)}</script>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:780px;margin:0 auto;padding:24px;color:#1e293b;line-height:1.6}}
h1{{font-size:28px;margin:0 0 8px}}
h2{{font-size:20px;margin:28px 0 10px;color:#0f172a}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}}
th,td{{border-bottom:1px solid #e5e7eb;padding:8px 10px;text-align:left;vertical-align:top}}
th{{background:#f8fafc;font-weight:600}}
.verdict{{display:inline-block;padding:10px 18px;font-weight:700;font-size:18px;color:{color};border:2px solid {color};border-radius:8px;margin:0 0 20px}}
.summary{{font-size:16px;padding:16px;background:#f8fafc;border-left:4px solid {color};border-radius:0 8px 8px 0;margin:8px 0 20px}}
a{{color:#0d9488;text-decoration:none}} a:hover{{text-decoration:underline}}
</style>
</head><body>
<h1>Has {_esc(name)} Been Hacked?</h1>
<p class="summary ai-summary"><strong>{_esc(headline)}.</strong> {_esc(detail)} Last checked: {TODAY}.</p>
<div class="verdict">{_esc(headline)}</div>

<h2>Incident Summary</h2>
<table>
<tr><th>Entity</th><td>{_esc(name)}</td></tr>
<tr><th>Slug</th><td>{_esc(slug)}</td></tr>
<tr><th>Confirmed Breaches</th><td>{len(breaches)}</td></tr>
<tr><th>CVE Count</th><td>{cve}{f' ({cve_crit} critical)' if cve_crit else ''}</td></tr>
<tr><th>Trust Score</th><td>{(f'{trust:.0f}/100 ({grade})') if trust is not None else 'Not yet rated'}</td></tr>
<tr><th>Registry</th><td>{_esc(registry) if registry else 'N/A'}</td></tr>
<tr><th>Last Checked</th><td>{TODAY}</td></tr>
</table>

{breach_section}

<h2>Data Sources</h2>
<ul>
<li><strong>HaveIBeenPwned</strong> — consumer-facing breach registry</li>
<li><strong>National Vulnerability Database (NVD)</strong> — CVE entries</li>
<li><strong>GitHub Security Advisories</strong> — open-source alerts</li>
<li><strong>OSV.dev</strong> — Google's open-source vulnerability database</li>
</ul>

<h2>More Context</h2>
<p>See the full trust analysis at <a href="{safe_url}">{_esc(name)} trust score</a>, or the plain-English write-up at <a href="{was_hacked_url}">was {_esc(name)} hacked?</a></p>
<p style="font-size:12px;color:#64748b;margin-top:32px">Updated {MY}. Data from Nerq's monitored sources. This page is machine-generated; report inaccuracies to <a href="mailto:corrections@nerq.ai">corrections@nerq.ai</a>.</p>
</body></html>"""


@router.get(
    "/hacked/{slug}",
    response_class=HTMLResponse,
    summary="Breach-history page for an indexed entity",
)
def hacked_page(slug: str) -> HTMLResponse:
    norm = slug.lower().strip()
    if not _SLUG_RE.match(norm):
        return HTMLResponse(
            "<!DOCTYPE html><html><head><meta name=\"robots\" content=\"noindex\">"
            "<title>Invalid slug — Nerq</title></head>"
            "<body><h1>Invalid slug</h1><p><a href=\"/\">Search Nerq</a></p></body></html>",
            status_code=400,
            headers={"X-Robots-Tag": "noindex"},
        )

    breaches = _fetch_breach(norm)
    registry_row = _fetch_registry(norm)
    body = _render(norm, breaches, registry_row)
    return HTMLResponse(
        content=body,
        status_code=200,
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Schema-Version": "nerq-hacked/v1",
        },
    )
