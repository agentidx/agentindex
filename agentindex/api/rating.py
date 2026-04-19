"""L4 endpoint: /rating/{slug}.json

Strict-JSON rating view for passive AI-bot discovery. Exposes the
Trust Score, grade, per-dimension sub-scores, and source attribution
for a Nerq-tracked package in a stable machine-readable shape — no
HTML wrapping, no localisation, no UI state.

Availability is gated to the top-100K entities by
`smedjan.ai_demand_scores`. Slugs outside the top-100K return 404 so
the endpoint surface stays aligned with the "demand-weighted data
moat" that the L4 sprint is building — it is intentionally *not* a
trust-score lookup for every package in software_registry.

Responses are cached in Redis db=1 under key `rating:<slug>` with a
4-hour TTL. A nightly pre-warm (disabled LaunchAgent) walks the whole
100K set so AI crawlers hit a warm cache, not the Postgres replica.
Run `python -m agentindex.api.rating --prewarm` to invoke the warmer.

Mounted from agentindex/api/discovery.py. Read-only; never writes.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Response

logger = logging.getLogger("agentindex.api.rating")

router = APIRouter(tags=["L4"])

SCHEMA_VERSION = "L4-rating/v1"
CANONICAL_BASE = "https://nerq.ai/rating"
LLMS_TXT_URL = "https://nerq.ai/llms.txt"

TOP_N_DEMAND = 100_000
CACHE_TTL_SECONDS = 4 * 60 * 60
REDIS_KEY_PREFIX = "rating:"
NEG_CACHE_SENTINEL = "__404__"

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

# Source attribution per registry — stable list consumed by AI bots
# as a provenance marker. Keep in lockstep with seo_pages data_sources.
_REGISTRY_DATA_SOURCES: dict[str, list[str]] = {
    "npm": ["npm registry", "GitHub", "OSV", "OpenSSF"],
    "pypi": ["PyPI", "GitHub", "OSV", "OpenSSF"],
    "gems": ["RubyGems", "GitHub", "OSV", "OpenSSF"],
    "rubygems": ["RubyGems", "GitHub", "OSV", "OpenSSF"],
    "crates": ["crates.io", "GitHub", "OSV", "OpenSSF"],
    "cargo": ["crates.io", "GitHub", "OSV", "OpenSSF"],
    "go": ["pkg.go.dev", "GitHub", "OSV", "OpenSSF"],
    "packagist": ["Packagist", "GitHub", "OSV", "OpenSSF"],
    "nuget": ["NuGet", "GitHub", "OSV", "OpenSSF"],
    "hex": ["Hex.pm", "GitHub", "OSV", "OpenSSF"],
    "cocoapods": ["CocoaPods", "GitHub", "OSV", "OpenSSF"],
    "pub": ["pub.dev", "GitHub", "OSV", "OpenSSF"],
    "homebrew": ["Homebrew", "GitHub", "OSV", "OpenSSF"],
    "conda": ["Anaconda", "GitHub", "OSV", "OpenSSF"],
}
_DEFAULT_DATA_SOURCES = ["GitHub", "OSV", "OpenSSF"]

_UNIVERSAL_DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("security", "security_score"),
    ("maintenance", "maintenance_score"),
    ("popularity", "popularity_score"),
    ("community", "community_score"),
    ("quality", "quality_score"),
    ("privacy", "privacy_score"),
    ("transparency", "transparency_score"),
    ("reliability", "reliability_score"),
)


def _registry_url(registry: Optional[str], slug: str) -> Optional[str]:
    if not registry:
        return None
    pattern = _REGISTRY_URL_PATTERNS.get(registry.lower())
    return pattern.format(slug=slug) if pattern else None


def _data_sources(registry: Optional[str]) -> list[str]:
    if not registry:
        return list(_DEFAULT_DATA_SOURCES)
    return list(_REGISTRY_DATA_SOURCES.get(registry.lower(), _DEFAULT_DATA_SOURCES))


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


def _score_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return int(round(f))


def _score_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 2)


_redis_client: Any = None


def _get_redis():
    """Return a Redis client on db=1 or None when Redis is unreachable.

    Cached across calls; a failed first connection turns the helper
    into a no-op rather than retrying forever on the request path.
    """
    global _redis_client
    if _redis_client is False:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis

        client = redis.Redis(
            host="localhost", port=6379, db=1, socket_timeout=0.2
        )
        client.ping()
        _redis_client = client
        return client
    except Exception as exc:
        logger.info("Redis unavailable for /rating cache: %s", exc)
        _redis_client = False
        return None


def _cache_get(slug: str) -> Optional[str]:
    client = _get_redis()
    if client is None:
        return None
    try:
        raw = client.get(REDIS_KEY_PREFIX + slug)
    except Exception as exc:
        logger.info("Redis GET failed for %s: %s", slug, exc)
        return None
    if raw is None:
        return None
    return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw


def _cache_set(slug: str, body: str) -> None:
    client = _get_redis()
    if client is None:
        return
    try:
        client.set(REDIS_KEY_PREFIX + slug, body, ex=CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.info("Redis SET failed for %s: %s", slug, exc)


def _in_top_demand(slug: str) -> bool:
    """True iff slug is among the top-N by ai_demand_score.

    Uses a single ranked window query against smedjan so the check is
    a boolean, not a rank number we'd have to post-filter in Python.
    Returns False (and logs) if the smedjan factory DB is unreachable
    — the endpoint fails closed rather than leaking all 5M slugs.
    """
    from smedjan import sources

    sql = """
        WITH ranked AS (
            SELECT slug,
                   ROW_NUMBER() OVER (ORDER BY score DESC, slug ASC) AS rnk
            FROM smedjan.ai_demand_scores
        )
        SELECT 1 FROM ranked WHERE slug = %s AND rnk <= %s
    """
    try:
        with sources.smedjan_db_cursor() as (_, cur):
            cur.execute(sql, (slug, TOP_N_DEMAND))
            return cur.fetchone() is not None
    except sources.SourceUnavailable as exc:
        logger.warning("Smedjan DB unavailable for /rating gate: %s", exc)
        return False


def _fetch_registry_row(slug: str) -> Optional[dict[str, Any]]:
    from smedjan import sources

    sql = """
        SELECT slug, registry, name,
               trust_score, trust_grade,
               security_score, maintenance_score, popularity_score,
               community_score, quality_score,
               privacy_score, transparency_score, reliability_score,
               enriched_at, last_updated, last_commit,
               homepage_url, repository_url
        FROM software_registry
        WHERE slug = %s
        ORDER BY trust_score DESC NULLS LAST, enriched_at DESC NULLS LAST
        LIMIT 1
    """
    try:
        with sources.nerq_readonly_cursor(dict_cursor=True) as (_, cur):
            cur.execute(sql, (slug,))
            row = cur.fetchone()
    except sources.SourceUnavailable as exc:
        logger.warning("Nerq RO unavailable for /rating/%s: %s", slug, exc)
        raise HTTPException(status_code=503, detail="upstream_unavailable") from exc
    return dict(row) if row else None


def _build_payload(row: dict[str, Any]) -> dict[str, Any]:
    dimensions = {
        key: _score_int(row.get(col)) for key, col in _UNIVERSAL_DIMENSIONS
    }
    last_updated = _to_iso(
        row.get("enriched_at") or row.get("last_updated") or row.get("last_commit")
    )
    return {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "@id": f"{CANONICAL_BASE}/{row['slug']}.json",
        "schema_version": SCHEMA_VERSION,
        "slug": row["slug"],
        "name": row.get("name") or row["slug"],
        "trust_score": _score_float(row.get("trust_score")),
        "trust_grade": row.get("trust_grade"),
        "registry": row.get("registry"),
        "last_updated": last_updated,
        "dimensions": dimensions,
        "data_sources": _data_sources(row.get("registry")),
        "registry_url": _registry_url(row.get("registry"), row["slug"]),
        "homepage_url": row.get("homepage_url"),
        "repository_url": row.get("repository_url"),
        "data_source": "nerq.software_registry",
        "llms_txt": LLMS_TXT_URL,
    }


def _lookup(slug: str) -> Optional[dict[str, Any]]:
    """Core lookup + Redis caching. Returns payload dict or None (404).

    Cache shape:
      - hit-payload  → serialised JSON string
      - hit-missing  → the NEG_CACHE_SENTINEL string
    Negative caching avoids hammering Postgres for known-unknown slugs.
    """
    cached = _cache_get(slug)
    if cached is not None:
        if cached == NEG_CACHE_SENTINEL:
            return None
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass  # fall through and refresh

    if not _in_top_demand(slug):
        _cache_set(slug, NEG_CACHE_SENTINEL)
        return None

    row = _fetch_registry_row(slug)
    if row is None:
        _cache_set(slug, NEG_CACHE_SENTINEL)
        return None

    payload = _build_payload(row)
    _cache_set(slug, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return payload


@router.get(
    "/rating/{slug}.json",
    summary="Stable rating view for top-demand assets (L4)",
    response_class=Response,
)
def rating_json(slug: str):
    if not slug or len(slug) > 200:
        raise HTTPException(status_code=400, detail="invalid_slug")

    normalised = slug.lower()
    payload = _lookup(normalised)
    if payload is None:
        raise HTTPException(status_code=404, detail="slug_not_found")

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=14400",
            "nerq:data": f'<{LLMS_TXT_URL}>; rel="describedby"',
            "Vary": "Accept",
            "X-Schema-Version": SCHEMA_VERSION,
        },
    )


# ── Pre-warm runner ────────────────────────────────────────────────────
# Invoked by com.nerq.smedjan.rating_prewarm.plist (disabled in Phase A).
# Walks the top-100K slug set and primes Redis so AI crawlers hit warm
# cache. Each slug round-trips the same _lookup path as the endpoint so
# cache keys and payloads stay identical.

def _iter_top_demand_slugs(limit: int = TOP_N_DEMAND):
    from smedjan import sources

    sql = """
        SELECT slug
        FROM smedjan.ai_demand_scores
        ORDER BY score DESC, slug ASC
        LIMIT %s
    """
    with sources.smedjan_db_cursor() as (_, cur):
        cur.execute(sql, (limit,))
        for (slug,) in cur.fetchall():
            yield slug


def _prewarm(limit: int = TOP_N_DEMAND, log_every: int = 1000) -> dict[str, int]:
    client = _get_redis()
    if client is None:
        print("rating_prewarm: Redis unavailable, aborting", file=sys.stderr)
        return {"warmed": 0, "missing": 0, "errors": 1}

    started = time.time()
    warmed = 0
    missing = 0
    errors = 0
    for idx, slug in enumerate(_iter_top_demand_slugs(limit), start=1):
        try:
            payload = _lookup(slug)
            if payload is None:
                missing += 1
            else:
                warmed += 1
        except Exception as exc:
            errors += 1
            logger.warning("prewarm failed for %s: %s", slug, exc)
        if idx % log_every == 0:
            elapsed = time.time() - started
            rate = idx / elapsed if elapsed > 0 else 0.0
            print(
                f"rating_prewarm: {idx} processed "
                f"(warm={warmed} miss={missing} err={errors}) "
                f"[{rate:.1f}/s]",
                flush=True,
            )

    elapsed = time.time() - started
    print(
        f"rating_prewarm: done in {elapsed:.1f}s "
        f"warm={warmed} miss={missing} err={errors}",
        flush=True,
    )
    return {"warmed": warmed, "missing": missing, "errors": errors}


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="L4 /rating pre-warm")
    parser.add_argument("--prewarm", action="store_true", help="Warm Redis cache")
    parser.add_argument(
        "--limit", type=int, default=TOP_N_DEMAND, help="Top-N slugs to warm"
    )
    args = parser.parse_args(argv)
    if not args.prewarm:
        parser.print_help()
        return 2
    result = _prewarm(limit=args.limit)
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(_main())
