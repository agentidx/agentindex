"""L4 endpoint: /dependencies/{slug}.json

Strict-JSON dependency-graph view of a Nerq-tracked package. Schema is
documented in ~/smedjan/docs/L4-dependencies-schema.md (kept in lockstep
with this module).

Mounted from agentindex/api/discovery.py. Reads through
`smedjan.sources.nerq_readonly_cursor`; never writes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Response

logger = logging.getLogger("agentindex.api.endpoints.dependencies")

router = APIRouter(tags=["L4"])

SCHEMA_VERSION = "L4-dependencies/v1"
DORMANT_THRESHOLD_DAYS = 365
LLMS_TXT_URL = "https://nerq.ai/llms.txt"
CANONICAL_BASE = "https://nerq.ai/dependencies"

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


def _newest(*candidates: Any) -> Optional[datetime]:
    parsed = [v for v in candidates if isinstance(v, datetime)]
    if not parsed:
        return None
    normalised = [
        v if v.tzinfo else v.replace(tzinfo=timezone.utc) for v in parsed
    ]
    return max(normalised)


def _dormant(
    deprecated: Optional[bool],
    last_commit: Any,
    last_release_date: Any,
    last_updated: Any,
) -> tuple[bool, Optional[str]]:
    if deprecated:
        return True, "deprecated"
    newest = _newest(last_commit, last_release_date, last_updated)
    if newest is None:
        return True, "no_signal"
    age_days = (datetime.now(timezone.utc) - newest).days
    if age_days > DORMANT_THRESHOLD_DAYS:
        if last_release_date and not last_commit:
            return True, f"no_release_in_{age_days}d"
        return True, f"no_commit_in_{age_days}d"
    return False, None


def _fetch_row(slug: str, registry: Optional[str]) -> Optional[dict[str, Any]]:
    from smedjan import sources

    sql = """
        SELECT slug, registry, name,
               dependencies_count, deprecated,
               enriched_at, last_updated, last_commit, last_release_date,
               homepage_url, repository_url,
               trust_score
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
        logger.warning("Nerq RO unavailable for /dependencies/%s: %s", slug, exc)
        raise HTTPException(status_code=503, detail="upstream_unavailable") from exc
    return dict(row) if row else None


@router.get(
    "/dependencies/{slug}.json",
    summary="Dependency-graph view of a tracked package (L4)",
    response_class=Response,
)
def dependencies_json(
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

    direct_count = int(row.get("dependencies_count") or 0)
    dormant, dormant_reason = _dormant(
        row.get("deprecated"),
        row.get("last_commit"),
        row.get("last_release_date"),
        row.get("last_updated"),
    )
    last_updated_at = _to_iso(
        row.get("enriched_at") or row.get("last_updated") or row.get("last_commit")
    )

    payload: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "@id": f"{CANONICAL_BASE}/{row['slug']}.json",
        "schema_version": SCHEMA_VERSION,
        "slug": row["slug"],
        "registry": row["registry"],
        "name": row.get("name") or row["slug"],
        "last_updated_at": last_updated_at,
        "dependencies": {
            "direct_count": direct_count,
            "transitive_count": None,
            "transitive_known": False,
            "dormant": dormant,
            "dormant_reason": dormant_reason,
            "dormant_threshold_days": DORMANT_THRESHOLD_DAYS,
        },
        "registry_url": _registry_url(row.get("registry"), row["slug"]),
        "homepage_url": row.get("homepage_url"),
        "repository_url": row.get("repository_url"),
        "sameAs": [],
        "data_source": "nerq.software_registry",
        "llms_txt": LLMS_TXT_URL,
    }

    import json

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
