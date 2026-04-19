"""L4 endpoint: /dimensions/{slug}.json

Strict-JSON view of the per-registry dimensional scoring for a
Nerq-tracked asset. Unlike `/signals/{slug}.json` (which exposes the
eight universal dimensions that Nerq computes uniformly across all
registries), this endpoint surfaces the *registry-specific* JSONB
dimensions stored in `software_registry.dimensions` — e.g. `skin_safety`
for cosmetic ingredients, `allergen_risk` for food ingredients — along
with the `regulatory` JSONB envelope. Keys are normalised to
lower_snake_case so consumers can rely on a stable shape regardless of
upstream enrichment-time naming drift.

Schema is documented in ~/smedjan/docs/L4-dimensions-schema.md (kept in
lockstep with this module).

Mounted from agentindex/api/discovery.py. Read-only; never writes.
"""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Response

logger = logging.getLogger("agentindex.api.endpoints.dimensions")

router = APIRouter(tags=["L4"])

SCHEMA_VERSION = "L4-dimensions/v1"
LLMS_TXT_URL = "https://nerq.ai/llms.txt"
CANONICAL_BASE = "https://nerq.ai/dimensions"

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

_UNIVERSAL_DIMENSION_COLUMNS: tuple[str, ...] = (
    "security_score",
    "maintenance_score",
    "popularity_score",
    "community_score",
    "quality_score",
    "privacy_score",
    "transparency_score",
    "reliability_score",
)

_KEY_NORMALISE_RE = re.compile(r"[^a-z0-9]+")


def _normalise_key(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    s = _KEY_NORMALISE_RE.sub("_", s).strip("_")
    return s or None


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


def _parse_jsonb(value: Any) -> Optional[dict[str, Any]]:
    """Accept dict, JSON string, or None; reject anything else."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _normalise_dimensions_jsonb(raw: Any) -> dict[str, Any]:
    """Normalise the `dimensions` JSONB envelope.

    Keys are lower_snake_cased. Numeric-looking values are coerced to
    float for consistency with the universal dimension block; everything
    else is passed through verbatim (so string enums like "low"/"high"
    survive). Duplicate keys after normalisation keep the first value.
    """
    parsed = _parse_jsonb(raw)
    if not parsed:
        return {}
    out: dict[str, Any] = {}
    for k, v in parsed.items():
        nk = _normalise_key(k)
        if nk is None or nk in out:
            continue
        if isinstance(v, bool):
            out[nk] = v
        elif isinstance(v, (int, float)):
            out[nk] = _float_or_none(v)
        elif isinstance(v, str):
            maybe_num = _float_or_none(v)
            out[nk] = maybe_num if maybe_num is not None else v
        else:
            out[nk] = v
    return out


def _normalise_regulatory_jsonb(raw: Any) -> dict[str, Any]:
    """Normalise the `regulatory` JSONB envelope.

    Keys are lower_snake_cased; values pass through untouched so string
    enums ("Restricted", "Approved") and booleans round-trip unchanged.
    """
    parsed = _parse_jsonb(raw)
    if not parsed:
        return {}
    out: dict[str, Any] = {}
    for k, v in parsed.items():
        nk = _normalise_key(k)
        if nk is None or nk in out:
            continue
        out[nk] = v
    return out


def _universal_dimensions(row: dict[str, Any]) -> dict[str, Optional[float]]:
    return {
        col.removesuffix("_score"): _float_or_none(row.get(col))
        for col in _UNIVERSAL_DIMENSION_COLUMNS
    }


def _fetch_row(slug: str, registry: Optional[str]) -> Optional[dict[str, Any]]:
    from smedjan import sources

    sql = """
        SELECT slug, registry, name,
               trust_score, trust_grade,
               security_score, maintenance_score, popularity_score,
               community_score, quality_score,
               privacy_score, transparency_score, reliability_score,
               dimensions, regulatory,
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
        logger.warning("Nerq RO unavailable for /dimensions/%s: %s", slug, exc)
        raise HTTPException(status_code=503, detail="upstream_unavailable") from exc
    return dict(row) if row else None


@router.get(
    "/dimensions/{slug}.json",
    summary="Registry-specific dimensional scoring for a tracked asset (L4)",
    response_class=Response,
)
def dimensions_json(
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

    registry_specific = _normalise_dimensions_jsonb(row.get("dimensions"))
    regulatory = _normalise_regulatory_jsonb(row.get("regulatory"))
    universal = _universal_dimensions(row)

    payload: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "@id": f"{CANONICAL_BASE}/{row['slug']}.json",
        "schema_version": SCHEMA_VERSION,
        "slug": row["slug"],
        "registry": row["registry"],
        "name": row.get("name") or row["slug"],
        "last_updated_at": last_updated_at,
        "dimensions": {
            "registry_specific": registry_specific,
            "registry_specific_keys": sorted(registry_specific.keys()),
            "registry_specific_available": bool(registry_specific),
            "universal": universal,
            "regulatory": regulatory,
            "trust_score": _float_or_none(row.get("trust_score")),
            "trust_grade": row.get("trust_grade"),
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
