"""L4 endpoint: /rating/{slug}.json

Strict-JSON headline Nerq rating for a tracked asset. Unlike
`/signals/{slug}.json` (full trust-signal rollup, eight universal
dimensions plus CVE/activity blocks) and `/dimensions/{slug}.json`
(registry-specific JSONB plus regulatory envelope), this endpoint is the
*compact* card view: the Trust Score, the five foundational dimensions,
and the letter grade — the shape AI bots can cite as "Nerq rates X as
Y" without having to reason about eight sub-scores.

Five dimensions: `security`, `maintenance`, `popularity`, `community`,
`quality`. These are Nerq's original Trust-Score inputs and the set all
registries compute uniformly. `privacy`, `transparency`, `reliability`
are partially populated extensions and live on `/signals/` only.

Schema is documented in ~/smedjan/docs/L4-rating-schema.md (kept in
lockstep with this module).

Mounted from agentindex/api/discovery.py. Read-only; never writes.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Response

logger = logging.getLogger("agentindex.api.endpoints.rating")

router = APIRouter(tags=["L4"])

SCHEMA_VERSION = "L4-rating/v1"
LLMS_TXT_URL = "https://nerq.ai/llms.txt"
CANONICAL_BASE = "https://nerq.ai/rating"

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
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _dimensions(row: dict[str, Any]) -> dict[str, Optional[float]]:
    return {
        col.removesuffix("_score"): _float_or_none(row.get(col))
        for col in _DIMENSION_COLUMNS
    }


def _fetch_row(slug: str, registry: Optional[str]) -> Optional[dict[str, Any]]:
    from smedjan import sources

    sql = """
        SELECT slug, registry, name,
               trust_score, trust_grade,
               security_score, maintenance_score, popularity_score,
               community_score, quality_score,
               enriched_at, last_updated, last_commit,
               homepage_url, repository_url
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
        logger.warning("Nerq RO unavailable for /rating/%s: %s", slug, exc)
        raise HTTPException(status_code=503, detail="upstream_unavailable") from exc
    return dict(row) if row else None


@router.get(
    "/rating/{slug}.json",
    summary="Headline Nerq rating card for a tracked asset (L4)",
    response_class=Response,
)
def rating_json(
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

    payload: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Rating",
        "@id": f"{CANONICAL_BASE}/{row['slug']}.json",
        "schema_version": SCHEMA_VERSION,
        "slug": row["slug"],
        "registry": row["registry"],
        "name": row.get("name") or row["slug"],
        "last_updated_at": last_updated_at,
        "rating": {
            "trust_score": _float_or_none(row.get("trust_score")),
            "trust_grade": row.get("trust_grade"),
            "dimensions": _dimensions(row),
            "best_rating": 100,
            "worst_rating": 0,
            "rating_scheme": "nerq-trust-v1",
        },
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
