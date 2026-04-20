"""L4 endpoint: /prediction/{slug}.json

Strict-JSON forward-looking demand view for a Nerq-tracked package.
Exposes the current smedjan `ai_demand_score` and its 30-day velocity
(both absolute delta and percentage), plus a 3σ surge flag aligned with
T131's surge detector. Schema is documented in
~/smedjan/docs/L4-prediction-schema.md (kept in lockstep with this
module).

Slug resolution mirrors the sibling L4 endpoints (/signals, /dependencies):
the slug is looked up in the Nerq `software_registry` read-replica so that
all three endpoints share the same slug space. The ai_demand overlay is
read from the smedjan factory DB and is optional — a tracked package that
has never been measured returns a 200 with nulls in the `ai_demand`
block, matching the "null = unknown, not zero" convention from T141.

Mounted from agentindex/api/discovery.py. Read-only; never writes.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Response

logger = logging.getLogger("agentindex.api.endpoints.prediction")

router = APIRouter(tags=["L4"])

SCHEMA_VERSION = "L4-prediction/v1"
LLMS_TXT_URL = "https://nerq.ai/llms.txt"
CANONICAL_BASE = "https://nerq.ai/prediction"

VELOCITY_WINDOW_DAYS = 30
SURGE_WINDOW_SNAPSHOTS = 7
SURGE_MIN_HISTORY = 4
SURGE_SIGMA_THRESHOLD = 3.0

# T220: in-process response cache and pooled smedjan connection.
# Baseline profiling on 2026-04-20 showed ~560 ms per cold call, almost
# entirely spent opening a fresh Tailscale-side smedjan connection
# (~290 ms) and issuing three sequential queries (~230 ms). Cloudflare
# caches every response for 24h (Cache-Control immutable, see response
# headers), so origin QPS is low and a single persistent connection
# behind a pool is sufficient.
_CACHE_TTL_SECONDS = 300
_CACHE_MAX_ENTRIES = 4096
_cache_lock = threading.Lock()
_response_cache: "OrderedDict[tuple[str, Optional[str]], tuple[float, bytes]]" = OrderedDict()

_smedjan_pool_lock = threading.Lock()
_smedjan_pool: Any = None  # psycopg2.pool.ThreadedConnectionPool or False (disabled)


def _cache_get(key: tuple[str, Optional[str]]) -> Optional[bytes]:
    now = time.monotonic()
    with _cache_lock:
        entry = _response_cache.get(key)
        if entry is None:
            return None
        ts, body = entry
        if now - ts > _CACHE_TTL_SECONDS:
            _response_cache.pop(key, None)
            return None
        _response_cache.move_to_end(key)
        return body


def _cache_put(key: tuple[str, Optional[str]], body: bytes) -> None:
    with _cache_lock:
        _response_cache[key] = (time.monotonic(), body)
        _response_cache.move_to_end(key)
        while len(_response_cache) > _CACHE_MAX_ENTRIES:
            _response_cache.popitem(last=False)

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


def _fetch_registry_row(
    slug: str, registry: Optional[str]
) -> Optional[dict[str, Any]]:
    from smedjan import sources

    sql = """
        SELECT slug, registry, name,
               enriched_at, last_updated, last_commit,
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
        logger.warning("Nerq RO unavailable for /prediction/%s: %s", slug, exc)
        raise HTTPException(status_code=503, detail="upstream_unavailable") from exc
    return dict(row) if row else None


def _get_smedjan_pool():
    """Lazily build a thread-safe connection pool to the smedjan DB.

    Returns None (and memoises the decision via the sentinel False) when
    no DSN is configured or the pool cannot be built, so repeated callers
    fall through to the graceful "source_available: false" path without
    re-attempting the connect on every request.
    """
    global _smedjan_pool
    if _smedjan_pool is False:
        return None
    if _smedjan_pool is not None:
        return _smedjan_pool
    with _smedjan_pool_lock:
        if _smedjan_pool is False:
            return None
        if _smedjan_pool is not None:
            return _smedjan_pool
        try:
            import psycopg2
            from psycopg2.pool import ThreadedConnectionPool
            from smedjan import config
        except Exception as exc:  # pragma: no cover - dep missing in tests
            logger.info("smedjan pool init skipped: %s", exc)
            _smedjan_pool = False
            return None
        dsn = getattr(config, "SMEDJAN_DB_DSN", None)
        if not dsn:
            _smedjan_pool = False
            return None
        try:
            _smedjan_pool = ThreadedConnectionPool(
                minconn=1, maxconn=4, dsn=dsn, connect_timeout=10
            )
        except psycopg2.OperationalError as exc:
            logger.warning("smedjan pool init failed: %s", exc)
            _smedjan_pool = False
            return None
    return _smedjan_pool


def _reset_smedjan_pool() -> None:
    """Drop the current pool so the next request rebuilds it.

    Called when a pooled connection has gone stale (peer reset, Tailscale
    flap). The cost is one fresh connect; the alternative is poisoning
    every subsequent request with the same dead conn.
    """
    global _smedjan_pool
    with _smedjan_pool_lock:
        pool = _smedjan_pool
        _smedjan_pool = None
        if pool and pool is not False:
            try:
                pool.closeall()
            except Exception:
                pass


def _fetch_ai_demand(slug: str) -> dict[str, Any]:
    """Return current score + 30d velocity + surge stats for a slug.

    Missing data yields nulls rather than raising — the endpoint degrades
    gracefully for packages not yet measured or when the smedjan factory
    DB is unreachable (the /prediction contract still holds for the
    slug-metadata half sourced from Nerq).
    """
    import psycopg2
    import psycopg2.extras

    out: dict[str, Any] = {
        "score": None,
        "score_computed_at": None,
        "last_30d_queries": None,
        "velocity_30d": None,
        "velocity_30d_pct": None,
        "velocity_window_start": None,
        "velocity_window_end": None,
        "velocity_samples": 0,
        "surge": None,
        "surge_sigma": None,
        "source_available": False,
    }

    pool = _get_smedjan_pool()
    if pool is None:
        return out

    cutoff = datetime.now(timezone.utc) - timedelta(days=VELOCITY_WINDOW_DAYS)
    # Single round-trip: score row + recent snapshots (union of top-N for
    # surge and last-30d for velocity). A `kind` discriminator lets the
    # caller partition rows without issuing two statements. Column types
    # are left uncast so psycopg2's text-mode decode of `real` matches
    # the pre-T220 behaviour (no float4->float8 precision noise).
    sql = """
        SELECT 'score' AS kind,
               s.computed_at AS ts,
               s.score AS score,
               s.last_30d_queries AS q
        FROM smedjan.ai_demand_scores s
        WHERE s.slug = %(slug)s
        UNION ALL
        SELECT 'hist' AS kind,
               h.computed_at AS ts,
               h.score AS score,
               NULL::int AS q
        FROM smedjan.ai_demand_history h
        WHERE h.slug = %(slug)s
          AND (
            h.computed_at >= %(cutoff)s
            OR h.computed_at IN (
              SELECT computed_at FROM smedjan.ai_demand_history
              WHERE slug = %(slug)s
              ORDER BY computed_at DESC
              LIMIT %(surge)s
            )
          )
    """
    params = {
        "slug": slug,
        "cutoff": cutoff,
        "surge": SURGE_WINDOW_SNAPSHOTS,
    }

    conn = None
    broken = False
    try:
        conn = pool.getconn()
        try:
            conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        except (psycopg2.InterfaceError, psycopg2.OperationalError):
            broken = True
            raise
    except psycopg2.OperationalError as exc:
        logger.info("Smedjan DB unavailable for /prediction/%s: %s", slug, exc)
        return out
    except psycopg2.InterfaceError as exc:
        logger.info("Smedjan DB interface error for /prediction/%s: %s", slug, exc)
        return out
    finally:
        if conn is not None:
            try:
                pool.putconn(conn, close=broken)
            except Exception:
                pass
            if broken:
                _reset_smedjan_pool()

    score_row: Optional[dict[str, Any]] = None
    hist_rows: list[tuple[Any, float]] = []
    for r in rows:
        if r["kind"] == "score":
            score_row = r
        else:
            hist_rows.append((r["ts"], float(r["score"])))

    hist_rows.sort(key=lambda x: x[0], reverse=True)
    history = hist_rows[:SURGE_WINDOW_SNAPSHOTS]
    window = [(ts, sc) for ts, sc in hist_rows if ts >= cutoff]
    window.sort(key=lambda x: x[0])

    out["source_available"] = True

    if score_row is not None:
        out["score"] = _float_or_none(score_row.get("score"))
        out["last_30d_queries"] = (
            int(score_row["q"]) if score_row.get("q") is not None else None
        )
        out["score_computed_at"] = _to_iso(score_row.get("ts"))

    if window:
        first_ts, first_score = window[0]
        last_ts, last_score = window[-1]
        out["velocity_window_start"] = _to_iso(first_ts)
        out["velocity_window_end"] = _to_iso(last_ts)
        out["velocity_samples"] = len(window)
        if len(window) >= 2:
            out["velocity_30d"] = round(last_score - first_score, 4)
            if first_score > 0:
                out["velocity_30d_pct"] = round(
                    (last_score - first_score) / first_score * 100.0, 4
                )

    if len(history) >= SURGE_MIN_HISTORY + 1:
        _today_ts, today_score = history[0]
        prior = [s for _, s in history[1:]]
        n = len(prior)
        mean = sum(prior) / n
        var = sum((x - mean) ** 2 for x in prior) / n
        stddev = math.sqrt(var)
        if stddev > 0.0:
            sigma = (today_score - mean) / stddev
            out["surge_sigma"] = round(sigma, 4)
            out["surge"] = sigma >= SURGE_SIGMA_THRESHOLD
        else:
            out["surge_sigma"] = None
            out["surge"] = today_score > mean

    return out


@router.get(
    "/prediction/{slug}.json",
    summary="Forward-looking ai_demand score + 30d velocity (L4)",
    response_class=Response,
)
def prediction_json(
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

    normalised_slug = slug.lower()
    normalised_registry = registry.lower() if registry else None
    cache_key = (normalised_slug, normalised_registry)

    cached_body = _cache_get(cache_key)
    if cached_body is not None:
        return Response(
            content=cached_body,
            media_type="application/json; charset=utf-8",
            headers={
                "Cache-Control": "public, max-age=86400, immutable",
                "nerq:data": f'<{LLMS_TXT_URL}>; rel="describedby"',
                "Vary": "Accept",
                "X-Schema-Version": SCHEMA_VERSION,
                "X-Cache": "hit",
            },
        )

    row = _fetch_registry_row(normalised_slug, normalised_registry)
    if row is None:
        raise HTTPException(status_code=404, detail="slug_not_found")

    demand = _fetch_ai_demand(row["slug"])

    last_updated_at = demand["score_computed_at"] or _to_iso(
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
        "ai_demand": {
            "score": demand["score"],
            "last_30d_queries": demand["last_30d_queries"],
            "computed_at": demand["score_computed_at"],
            "velocity_30d": demand["velocity_30d"],
            "velocity_30d_pct": demand["velocity_30d_pct"],
            "velocity_window": {
                "days": VELOCITY_WINDOW_DAYS,
                "start": demand["velocity_window_start"],
                "end": demand["velocity_window_end"],
                "samples": demand["velocity_samples"],
            },
            "surge": demand["surge"],
            "surge_sigma": demand["surge_sigma"],
            "surge_threshold_sigma": SURGE_SIGMA_THRESHOLD,
            "source_available": demand["source_available"],
        },
        "registry_url": _registry_url(row.get("registry"), row["slug"]),
        "homepage_url": row.get("homepage_url"),
        "repository_url": row.get("repository_url"),
        "sameAs": [],
        "data_source": "smedjan.ai_demand_scores+ai_demand_history",
        "llms_txt": LLMS_TXT_URL,
    }

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    _cache_put(cache_key, body)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=86400, immutable",
            "nerq:data": f'<{LLMS_TXT_URL}>; rel="describedby"',
            "Vary": "Accept",
            "X-Schema-Version": SCHEMA_VERSION,
            "X-Cache": "miss",
        },
    )
