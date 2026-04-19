"""L4 endpoint: /signals/{slug}.json

Strict-JSON trust-signals rollup for a Nerq-tracked software package.
Schema is documented in ~/smedjan/docs/L4-signals-schema.md (kept in
lockstep with this module).

Mounted from agentindex/api/discovery.py. Reads through
`smedjan.sources.nerq_readonly_cursor`; never writes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Response

logger = logging.getLogger("agentindex.api.endpoints.signals")

router = APIRouter(tags=["L4"])

SCHEMA_VERSION = "L4-signals/v1"
LLMS_TXT_URL = "https://nerq.ai/llms.txt"
CANONICAL_BASE = "https://nerq.ai/signals"

_REGISTRY_URL_PATTERNS: dict[str, str] = {
    "npm": "https://www.npmjs.com/package/{slug}",
    "pypi": "https://pypi.org/project/{slug}/",
    "gems": "https://rubygems.org/gems/{slug}",
    "rubygems": "https://rubygems.org/gems/{slug}",
    "homebrew": "https://formulae.brew.sh/formula/{slug}",
    "crates": "https://crates.io/crates/{slug}",
    "cargo": "https://crates.io/crates/{slug}",
    "nuget": "https://www.nuget.org/packages/{slug}",
    "go": "https://pkg.go.dev/{slug}",
    "packagist": "https://packagist.org/packages/{slug}",
    "hex": "https://hex.pm/packages/{slug}",
    "cocoapods": "https://cocoapods.org/pods/{slug}",
    "pub": "https://pub.dev/packages/{slug}",
    "conda": "https://anaconda.org/conda-forge/{slug}",
}

_DIMENSION_COLUMNS: tuple[str, ...] = (
    "security_score",
    "maintenance_score",
    "popularity_score",
    "community_score",
    "quality_score",
    "privacy_score",
    "transparency_score",
    "reliability_score",
)


def _registry_url(registry: Optional[str], slug: str) -> Optional[str]:
    if not registry:
        return None
    pattern = _REGISTRY_URL_PATTERNS.get(registry.lower())
    return pattern.format(slug=slug) if pattern else None


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return None


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fetch_row(slug: str, registry: Optional[str]) -> Optional[dict[str, Any]]:
    from smedjan import sources

    sql = """
        SELECT slug, registry, name,
               trust_score, trust_grade,
               security_score, maintenance_score, popularity_score,
               community_score, quality_score, openssf_score,
               privacy_score, transparency_score, reliability_score,
               cve_count, cve_critical,
               stars, forks, open_issues, contributors,
               maintainer_count, release_count,
               deprecated, has_types,
               has_independent_audit, has_soc2, has_iso27001,
               jurisdiction,
               enriched_at, last_updated, last_commit, last_release_date,
               homepage_url, repository_url,
               data_sources
        FROM software_registry
        WHERE slug = %s
        {registry_clause}
        ORDER BY trust_score DESC NULLS LAST, enriched_at DESC NULLS LAST
        LIMIT 1
    """
    params: list[Any] = [slug]
    if registry:
        sql = sql.format(registry_clause="AND registry = %s")
        params.append(registry)
    else:
        sql = sql.format(registry_clause="")

    try:
        with sources.nerq_readonly_cursor(dict_cursor=True) as (_, cur):
            cur.execute(sql, params)
            row = cur.fetchone()
    except sources.SourceUnavailable as exc:
        logger.warning("Nerq RO unavailable for /signals/%s: %s", slug, exc)
        raise HTTPException(status_code=503, detail="upstream_unavailable") from exc
    return dict(row) if row else None


def _dimensions(row: dict[str, Any]) -> dict[str, Optional[float]]:
    return {
        col.removesuffix("_score"): _float_or_none(row.get(col))
        for col in _DIMENSION_COLUMNS
    }


def _data_sources(row: dict[str, Any]) -> list[str]:
    raw = row.get("data_sources")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    if isinstance(raw, dict):
        return sorted(str(k) for k in raw.keys())
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if isinstance(parsed, list):
            return [str(x) for x in parsed if x]
        if isinstance(parsed, dict):
            return sorted(str(k) for k in parsed.keys())
    return []


@router.get(
    "/signals/{slug}.json",
    summary="External trust-signal rollup for a tracked package (L4)",
    response_class=Response,
)
def signals_json(
    slug: str,
    response: Response,
    registry: Optional[str] = Query(
        None,
        description="Disambiguate when the slug exists in multiple registries.",
        max_length=32,
    ),
):
    if not slug or len(slug) > 200:
        raise HTTPException(status_code=400, detail="invalid_slug")

    row = _fetch_row(slug.lower(), registry.lower() if registry else None)
    if row is None:
        raise HTTPException(status_code=404, detail="slug_not_found")

    last_updated_at = _to_iso(
        row.get("enriched_at") or row.get("last_updated") or row.get("last_commit")
    )

    external_trust_signals = {
        "trust_score": _float_or_none(row.get("trust_score")),
        "trust_grade": row.get("trust_grade"),
        "dimensions": _dimensions(row),
        "openssf_scorecard": _float_or_none(row.get("openssf_score")),
        "security": {
            "cve_count": _int_or_none(row.get("cve_count")) or 0,
            "cve_critical": _int_or_none(row.get("cve_critical")) or 0,
            "has_independent_audit": bool(row.get("has_independent_audit"))
            if row.get("has_independent_audit") is not None
            else None,
            "has_soc2": bool(row.get("has_soc2"))
            if row.get("has_soc2") is not None
            else None,
            "has_iso27001": bool(row.get("has_iso27001"))
            if row.get("has_iso27001") is not None
            else None,
        },
        "activity": {
            "stars": _int_or_none(row.get("stars")) or 0,
            "forks": _int_or_none(row.get("forks")) or 0,
            "open_issues": _int_or_none(row.get("open_issues")) or 0,
            "contributors": _int_or_none(row.get("contributors")) or 0,
            "maintainer_count": _int_or_none(row.get("maintainer_count")) or 0,
            "release_count": _int_or_none(row.get("release_count")) or 0,
            "last_commit": _to_iso(row.get("last_commit")),
            "last_release_date": _to_iso(row.get("last_release_date")),
        },
        "lifecycle": {
            "deprecated": bool(row.get("deprecated"))
            if row.get("deprecated") is not None
            else None,
            "has_types": row.get("has_types"),
            "jurisdiction": row.get("jurisdiction"),
        },
        "data_sources": _data_sources(row),
    }

    payload: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "@id": f"{CANONICAL_BASE}/{row['slug']}.json",
        "schema_version": SCHEMA_VERSION,
        "slug": row["slug"],
        "registry": row["registry"],
        "name": row.get("name") or row["slug"],
        "last_updated_at": last_updated_at,
        "external_trust_signals": external_trust_signals,
        "registry_url": _registry_url(row.get("registry"), row["slug"]),
        "homepage_url": row.get("homepage_url"),
        "repository_url": row.get("repository_url"),
        "sameAs": [],
        "data_source": "nerq.software_registry",
        "llms_txt": LLMS_TXT_URL,
    }

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=86400, immutable",
            "nerq:data": f'<{LLMS_TXT_URL}>; rel="describedby"',
            "Vary": "Accept",
            "X-Schema-Version": SCHEMA_VERSION,
        },
    )
