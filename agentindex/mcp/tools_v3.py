"""MCP tool definitions for tools 21–30 (Nerq MCP server v2).

Each entry in :data:`TOOLS` is a JSON-schema tool definition; each key in
:data:`TOOL_HANDLERS` is a synchronous handler that takes the tool's
``arguments`` dict and returns a JSON-serialisable dict.

The handlers read exclusively from the Nerq read-only replica via
``smedjan.sources.nerq_readonly_cursor`` and never write. ``trust_changes``
and ``software_registry`` are the two source tables.

Schema version: ``nerq-mcp-tools/v3.0`` — tools 21..30 added on top of
the stable v2 tool set (``check_compliance``, ``discover_agents``,
``get_agent_details``, ``compliance_summary``, ``nerq_stats``). No
existing tool shape is modified.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger("nerq.mcp.tools_v3")

SCHEMA_VERSION = "nerq-mcp-tools/v3.0"

DIMENSION_COLUMNS: dict[str, str] = {
    "security": "security_score",
    "maintenance": "maintenance_score",
    "popularity": "popularity_score",
    "community": "community_score",
    "quality": "quality_score",
    "privacy": "privacy_score",
    "transparency": "transparency_score",
    "reliability": "reliability_score",
    "openssf": "openssf_score",
}

CORE_DIMENSIONS: tuple[str, ...] = (
    "security",
    "maintenance",
    "popularity",
    "community",
    "quality",
)

EXTENDED_DIMENSIONS: tuple[str, ...] = (
    "privacy",
    "transparency",
    "reliability",
)


# ── helpers ─────────────────────────────────────────────────────────

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


def _int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(value)


def _dimension_payload(row: dict[str, Any], keys: Iterable[str]) -> dict[str, Optional[float]]:
    out: dict[str, Optional[float]] = {}
    for key in keys:
        col = DIMENSION_COLUMNS[key]
        out[key] = _float_or_none(row.get(col))
    return out


def _card(row: dict[str, Any]) -> dict[str, Any]:
    """Compact package card used by list-style tools."""
    return {
        "slug": row.get("slug"),
        "registry": row.get("registry"),
        "name": row.get("name") or row.get("slug"),
        "trust_score": _float_or_none(row.get("trust_score")),
        "trust_grade": row.get("trust_grade"),
        "deprecated": bool(row["deprecated"]) if row.get("deprecated") is not None else None,
        "last_updated_at": _iso(row.get("enriched_at") or row.get("last_updated") or row.get("last_commit")),
    }


def _read_cursor():
    """Return an async-context manager yielding (conn, dict-cursor).

    We resolve the import lazily so importing this module in an
    environment without smedjan (tests, schema validation) does not
    fail.
    """
    from smedjan import sources
    return sources.nerq_readonly_cursor(dict_cursor=True)


# ── 21. get_rating ──────────────────────────────────────────────────

def _get_rating(args: dict[str, Any]) -> dict[str, Any]:
    slug = (args.get("slug") or "").strip().lower()
    if not slug:
        return {"error": "missing_slug"}
    registry = (args.get("registry") or "").strip().lower() or None

    sql = """
        SELECT slug, registry, name, trust_score, trust_grade,
               security_score, maintenance_score, popularity_score,
               community_score, quality_score,
               enriched_at, last_updated, last_commit,
               homepage_url, repository_url, deprecated
        FROM software_registry
        WHERE slug = %s
          {clause}
        ORDER BY trust_score DESC NULLS LAST, enriched_at DESC NULLS LAST
        LIMIT 1
    """
    params: list[Any] = [slug]
    if registry:
        sql = sql.format(clause="AND registry = %s")
        params.append(registry)
    else:
        sql = sql.format(clause="")

    with _read_cursor() as (_, cur):
        cur.execute(sql, params)
        row = cur.fetchone()

    if not row:
        return {"error": "slug_not_found", "slug": slug, "registry": registry}

    row = dict(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "slug": row["slug"],
        "registry": row["registry"],
        "name": row.get("name") or row["slug"],
        "last_updated_at": _iso(row.get("enriched_at") or row.get("last_updated") or row.get("last_commit")),
        "rating": {
            "trust_score": _float_or_none(row.get("trust_score")),
            "trust_grade": row.get("trust_grade"),
            "dimensions": _dimension_payload(row, CORE_DIMENSIONS),
            "best_rating": 100,
            "worst_rating": 0,
            "rating_scheme": "nerq-trust-v1",
        },
        "homepage_url": row.get("homepage_url"),
        "repository_url": row.get("repository_url"),
    }


# ── 22. get_signals ─────────────────────────────────────────────────

def _get_signals(args: dict[str, Any]) -> dict[str, Any]:
    slug = (args.get("slug") or "").strip().lower()
    if not slug:
        return {"error": "missing_slug"}
    registry = (args.get("registry") or "").strip().lower() or None

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
               enriched_at, last_updated, last_commit, last_release_date
        FROM software_registry
        WHERE slug = %s
          {clause}
        ORDER BY trust_score DESC NULLS LAST, enriched_at DESC NULLS LAST
        LIMIT 1
    """
    params: list[Any] = [slug]
    if registry:
        sql = sql.format(clause="AND registry = %s")
        params.append(registry)
    else:
        sql = sql.format(clause="")

    with _read_cursor() as (_, cur):
        cur.execute(sql, params)
        row = cur.fetchone()

    if not row:
        return {"error": "slug_not_found", "slug": slug, "registry": registry}

    row = dict(row)
    all_dims = list(CORE_DIMENSIONS) + list(EXTENDED_DIMENSIONS)
    return {
        "schema_version": SCHEMA_VERSION,
        "slug": row["slug"],
        "registry": row["registry"],
        "name": row.get("name") or row["slug"],
        "last_updated_at": _iso(row.get("enriched_at") or row.get("last_updated") or row.get("last_commit")),
        "trust_score": _float_or_none(row.get("trust_score")),
        "trust_grade": row.get("trust_grade"),
        "dimensions": _dimension_payload(row, all_dims),
        "openssf_scorecard": _float_or_none(row.get("openssf_score")),
        "security": {
            "cve_count": _int_or_none(row.get("cve_count")) or 0,
            "cve_critical": _int_or_none(row.get("cve_critical")) or 0,
            "has_independent_audit": bool(row["has_independent_audit"]) if row.get("has_independent_audit") is not None else None,
            "has_soc2": bool(row["has_soc2"]) if row.get("has_soc2") is not None else None,
            "has_iso27001": bool(row["has_iso27001"]) if row.get("has_iso27001") is not None else None,
        },
        "activity": {
            "stars": _int_or_none(row.get("stars")) or 0,
            "forks": _int_or_none(row.get("forks")) or 0,
            "open_issues": _int_or_none(row.get("open_issues")) or 0,
            "contributors": _int_or_none(row.get("contributors")) or 0,
            "maintainer_count": _int_or_none(row.get("maintainer_count")) or 0,
            "release_count": _int_or_none(row.get("release_count")) or 0,
            "last_commit": _iso(row.get("last_commit")),
            "last_release_date": _iso(row.get("last_release_date")),
        },
        "lifecycle": {
            "deprecated": bool(row["deprecated"]) if row.get("deprecated") is not None else None,
            "has_types": row.get("has_types"),
            "jurisdiction": row.get("jurisdiction"),
        },
    }


# ── 23. get_dependencies ────────────────────────────────────────────

_DORMANT_THRESHOLD_DAYS = 365


def _dormant(row: dict[str, Any]) -> tuple[bool, Optional[str]]:
    if row.get("deprecated"):
        return True, "deprecated"
    candidates = [row.get("last_commit"), row.get("last_release_date"), row.get("last_updated")]
    parsed = [c for c in candidates if isinstance(c, datetime)]
    if not parsed:
        return True, "no_signal"
    normalised = [v if v.tzinfo else v.replace(tzinfo=timezone.utc) for v in parsed]
    newest = max(normalised)
    age_days = (datetime.now(timezone.utc) - newest).days
    if age_days > _DORMANT_THRESHOLD_DAYS:
        return True, f"no_commit_in_{age_days}d"
    return False, None


def _get_dependencies(args: dict[str, Any]) -> dict[str, Any]:
    slug = (args.get("slug") or "").strip().lower()
    if not slug:
        return {"error": "missing_slug"}
    registry = (args.get("registry") or "").strip().lower() or None

    sql = """
        SELECT slug, registry, name,
               dependencies_count, deprecated,
               enriched_at, last_updated, last_commit, last_release_date,
               trust_score
        FROM software_registry
        WHERE slug = %s
          {clause}
        ORDER BY trust_score DESC NULLS LAST, enriched_at DESC NULLS LAST
        LIMIT 1
    """
    params: list[Any] = [slug]
    if registry:
        sql = sql.format(clause="AND registry = %s")
        params.append(registry)
    else:
        sql = sql.format(clause="")

    with _read_cursor() as (_, cur):
        cur.execute(sql, params)
        row = cur.fetchone()

    if not row:
        return {"error": "slug_not_found", "slug": slug, "registry": registry}

    row = dict(row)
    dormant, reason = _dormant(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "slug": row["slug"],
        "registry": row["registry"],
        "name": row.get("name") or row["slug"],
        "last_updated_at": _iso(row.get("enriched_at") or row.get("last_updated") or row.get("last_commit")),
        "dependencies": {
            "direct_count": int(row.get("dependencies_count") or 0),
            "transitive_count": None,
            "transitive_known": False,
            "dormant": dormant,
            "dormant_reason": reason,
            "dormant_threshold_days": _DORMANT_THRESHOLD_DAYS,
        },
    }


# ── 24. compare_packages ────────────────────────────────────────────

def _compare_packages(args: dict[str, Any]) -> dict[str, Any]:
    slugs_raw = args.get("slugs") or []
    if not isinstance(slugs_raw, list) or not slugs_raw:
        return {"error": "missing_slugs"}
    slugs = [str(s).strip().lower() for s in slugs_raw if str(s).strip()][:10]
    if not slugs:
        return {"error": "missing_slugs"}
    registry = (args.get("registry") or "").strip().lower() or None

    sql = """
        SELECT slug, registry, name, trust_score, trust_grade,
               security_score, maintenance_score, popularity_score,
               community_score, quality_score,
               deprecated, enriched_at, last_updated, last_commit
        FROM software_registry
        WHERE slug = ANY(%s)
          {clause}
    """
    params: list[Any] = [slugs]
    if registry:
        sql = sql.format(clause="AND registry = %s")
        params.append(registry)
    else:
        sql = sql.format(clause="")

    with _read_cursor() as (_, cur):
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

    best_per_slug: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r["slug"], r["registry"])
        existing = best_per_slug.get(key)
        if existing is None or (r.get("trust_score") or -1) > (existing.get("trust_score") or -1):
            best_per_slug[key] = r

    packages = []
    for slug in slugs:
        matches = [r for (s, _reg), r in best_per_slug.items() if s == slug]
        if not matches:
            packages.append({"slug": slug, "error": "slug_not_found"})
            continue
        if len(matches) > 1 and not registry:
            matches.sort(key=lambda r: r.get("trust_score") or -1, reverse=True)
        r = matches[0]
        packages.append({
            **_card(r),
            "dimensions": _dimension_payload(r, CORE_DIMENSIONS),
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "count": len(packages),
        "registry": registry,
        "packages": packages,
    }


# ── 25. find_similar ────────────────────────────────────────────────

def _find_similar(args: dict[str, Any]) -> dict[str, Any]:
    slug = (args.get("slug") or "").strip().lower()
    if not slug:
        return {"error": "missing_slug"}
    registry = (args.get("registry") or "").strip().lower() or None
    limit = min(max(int(args.get("limit") or 10), 1), 50)

    find_sql = """
        SELECT slug, registry, trust_score
        FROM software_registry
        WHERE slug = %s
          {clause}
        ORDER BY trust_score DESC NULLS LAST, enriched_at DESC NULLS LAST
        LIMIT 1
    """
    find_params: list[Any] = [slug]
    if registry:
        find_sql = find_sql.format(clause="AND registry = %s")
        find_params.append(registry)
    else:
        find_sql = find_sql.format(clause="")

    with _read_cursor() as (_, cur):
        cur.execute(find_sql, find_params)
        anchor = cur.fetchone()
        if not anchor:
            return {"error": "slug_not_found", "slug": slug, "registry": registry}
        anchor = dict(anchor)

        peer_sql = """
            SELECT slug, registry, name, trust_score, trust_grade,
                   deprecated, enriched_at, last_updated, last_commit
            FROM software_registry
            WHERE registry = %s
              AND slug <> %s
              AND trust_score IS NOT NULL
            ORDER BY ABS(trust_score - %s) ASC,
                     trust_score DESC NULLS LAST
            LIMIT %s
        """
        anchor_score = _float_or_none(anchor.get("trust_score"))
        cur.execute(
            peer_sql,
            [anchor["registry"], anchor["slug"], anchor_score if anchor_score is not None else 0.0, limit],
        )
        rows = [dict(r) for r in cur.fetchall()]

    return {
        "schema_version": SCHEMA_VERSION,
        "anchor": {"slug": anchor["slug"], "registry": anchor["registry"], "trust_score": anchor_score},
        "count": len(rows),
        "results": [_card(r) for r in rows],
    }


# ── 26. get_verticals ───────────────────────────────────────────────

def _get_verticals(args: dict[str, Any]) -> dict[str, Any]:
    from agentindex.ab_test import VERTICALS, VERTICAL_GROUPS, _load_vertical_counts

    counts = _load_vertical_counts()
    verticals = []
    for key, (href, _icon, title, desc, count_keys, group, best_slug) in VERTICALS.items():
        total = sum(counts.get(k, 0) for k in count_keys)
        verticals.append({
            "key": key,
            "title": title.replace("&amp;", "&"),
            "description": desc.replace("&amp;", "&"),
            "group": group,
            "href": href,
            "best_slug": best_slug,
            "registry_keys": list(count_keys),
            "entity_count": total,
        })
    groups = {
        k: {"title": t.replace("&amp;", "&"), "verticals": list(members)}
        for k, (t, members) in VERTICAL_GROUPS.items()
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "count": len(verticals),
        "verticals": verticals,
        "groups": groups,
    }


# ── 27. list_by_registry ────────────────────────────────────────────

def _list_by_registry(args: dict[str, Any]) -> dict[str, Any]:
    registry = (args.get("registry") or "").strip().lower()
    if not registry:
        return {"error": "missing_registry"}
    min_trust = _float_or_none(args.get("min_trust_score"))
    limit = min(max(int(args.get("limit") or 20), 1), 100)
    offset = max(int(args.get("offset") or 0), 0)

    conditions = ["registry = %s", "trust_score IS NOT NULL"]
    params: list[Any] = [registry]
    if min_trust is not None:
        conditions.append("trust_score >= %s")
        params.append(min_trust)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT slug, registry, name, trust_score, trust_grade,
               deprecated, enriched_at, last_updated, last_commit
        FROM software_registry
        WHERE {where}
        ORDER BY trust_score DESC NULLS LAST, enriched_at DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with _read_cursor() as (_, cur):
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

    return {
        "schema_version": SCHEMA_VERSION,
        "registry": registry,
        "min_trust_score": min_trust,
        "limit": limit,
        "offset": offset,
        "count": len(rows),
        "packages": [_card(r) for r in rows],
    }


# ── 28. get_alternatives ────────────────────────────────────────────

def _get_alternatives(args: dict[str, Any]) -> dict[str, Any]:
    slug = (args.get("slug") or "").strip().lower()
    if not slug:
        return {"error": "missing_slug"}
    registry = (args.get("registry") or "").strip().lower() or None
    limit = min(max(int(args.get("limit") or 10), 1), 50)

    find_sql = """
        SELECT slug, registry, trust_score
        FROM software_registry
        WHERE slug = %s
          {clause}
        ORDER BY trust_score DESC NULLS LAST, enriched_at DESC NULLS LAST
        LIMIT 1
    """
    find_params: list[Any] = [slug]
    if registry:
        find_sql = find_sql.format(clause="AND registry = %s")
        find_params.append(registry)
    else:
        find_sql = find_sql.format(clause="")

    with _read_cursor() as (_, cur):
        cur.execute(find_sql, find_params)
        anchor = cur.fetchone()
        if not anchor:
            return {"error": "slug_not_found", "slug": slug, "registry": registry}
        anchor = dict(anchor)

        anchor_score = _float_or_none(anchor.get("trust_score")) or 0.0
        alt_sql = """
            SELECT slug, registry, name, trust_score, trust_grade,
                   deprecated, enriched_at, last_updated, last_commit
            FROM software_registry
            WHERE registry = %s
              AND slug <> %s
              AND trust_score > %s
              AND (deprecated IS NULL OR deprecated = false)
            ORDER BY trust_score DESC NULLS LAST, enriched_at DESC NULLS LAST
            LIMIT %s
        """
        cur.execute(alt_sql, [anchor["registry"], anchor["slug"], anchor_score, limit])
        rows = [dict(r) for r in cur.fetchall()]

    return {
        "schema_version": SCHEMA_VERSION,
        "anchor": {"slug": anchor["slug"], "registry": anchor["registry"], "trust_score": anchor_score},
        "count": len(rows),
        "alternatives": [_card(r) for r in rows],
    }


# ── 29. get_trust_history ───────────────────────────────────────────

def _get_trust_history(args: dict[str, Any]) -> dict[str, Any]:
    slug = (args.get("slug") or "").strip().lower()
    if not slug:
        return {"error": "missing_slug"}
    registry = (args.get("registry") or "").strip().lower() or None
    days = min(max(int(args.get("days") or 365), 1), 3650)
    limit = min(max(int(args.get("limit") or 100), 1), 500)

    conditions = ["entity_id = %s", "date >= (CURRENT_DATE - (%s || ' days')::interval)"]
    params: list[Any] = [slug, str(days)]
    if registry:
        conditions.append("registry = %s")
        params.append(registry)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT date, entity_id, entity_type, registry,
               old_score, new_score, change, reason
        FROM trust_changes
        WHERE {where}
        ORDER BY date DESC, id DESC
        LIMIT %s
    """
    params.append(limit)

    with _read_cursor() as (_, cur):
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

    events = [
        {
            "date": str(r["date"]) if r.get("date") else None,
            "entity_id": r.get("entity_id"),
            "entity_type": r.get("entity_type"),
            "registry": r.get("registry"),
            "old_score": _float_or_none(r.get("old_score")),
            "new_score": _float_or_none(r.get("new_score")),
            "change": _float_or_none(r.get("change")),
            "reason": r.get("reason"),
        }
        for r in rows
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "slug": slug,
        "registry": registry,
        "days": days,
        "count": len(events),
        "events": events,
    }


# ── 30. search_by_dimension ─────────────────────────────────────────

def _search_by_dimension(args: dict[str, Any]) -> dict[str, Any]:
    dimension = (args.get("dimension") or "").strip().lower()
    if dimension not in DIMENSION_COLUMNS:
        return {
            "error": "invalid_dimension",
            "valid_dimensions": sorted(DIMENSION_COLUMNS.keys()),
        }
    col = DIMENSION_COLUMNS[dimension]
    registry = (args.get("registry") or "").strip().lower() or None
    min_score = _float_or_none(args.get("min_score"))
    if min_score is None:
        min_score = 70.0
    limit = min(max(int(args.get("limit") or 20), 1), 100)

    conditions = [f"{col} IS NOT NULL", f"{col} >= %s"]
    params: list[Any] = [min_score]
    if registry:
        conditions.append("registry = %s")
        params.append(registry)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT slug, registry, name, trust_score, trust_grade,
               {col} AS dim_score,
               deprecated, enriched_at, last_updated, last_commit
        FROM software_registry
        WHERE {where}
        ORDER BY {col} DESC NULLS LAST, trust_score DESC NULLS LAST
        LIMIT %s
    """
    params.append(limit)

    with _read_cursor() as (_, cur):
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

    return {
        "schema_version": SCHEMA_VERSION,
        "dimension": dimension,
        "min_score": min_score,
        "registry": registry,
        "count": len(rows),
        "packages": [
            {**_card(r), "dimension_score": _float_or_none(r.get("dim_score"))}
            for r in rows
        ],
    }


# ── schema registry ─────────────────────────────────────────────────

_SLUG_PROP = {
    "type": "string",
    "description": "Package slug (lowercase; must match `software_registry.slug`).",
}
_REGISTRY_PROP = {
    "type": "string",
    "description": "Registry scope (e.g. 'npm', 'pypi', 'crates'). Optional; disambiguates a slug that exists in more than one registry.",
}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_rating",
        "description": (
            "Headline Nerq rating card for a tracked software package. Returns the "
            "Trust Score (0–100), letter grade, and the five foundational dimensions "
            "(security, maintenance, popularity, community, quality). Use when the "
            "user asks 'what is X's Nerq rating?', 'is X trustworthy?', or needs a "
            "compact card view."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"slug": _SLUG_PROP, "registry": _REGISTRY_PROP},
            "required": ["slug"],
        },
    },
    {
        "name": "get_signals",
        "description": (
            "Full trust-signal rollup for a package: eight trust dimensions, OpenSSF "
            "Scorecard, CVE counts, audit flags, activity metrics, and lifecycle "
            "state. Use after get_rating when the user wants the detailed evidence "
            "behind the score or needs CVE/audit/activity data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"slug": _SLUG_PROP, "registry": _REGISTRY_PROP},
            "required": ["slug"],
        },
    },
    {
        "name": "get_dependencies",
        "description": (
            "Dependency-graph view for a package: direct dependency count, dormant "
            "status, and dormant reason (deprecated / no commit in N days). Use when "
            "the user asks 'how many deps does X have?' or 'is X still maintained?'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"slug": _SLUG_PROP, "registry": _REGISTRY_PROP},
            "required": ["slug"],
        },
    },
    {
        "name": "compare_packages",
        "description": (
            "Side-by-side Trust Score and dimension comparison for up to 10 packages. "
            "Use when the user asks 'compare A vs B vs C', 'which of these is most "
            "trustworthy?', or needs a ranked table of alternatives."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slugs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 10,
                    "description": "2–10 package slugs to compare.",
                },
                "registry": _REGISTRY_PROP,
            },
            "required": ["slugs"],
        },
    },
    {
        "name": "find_similar",
        "description": (
            "Find packages with trust scores closest to the anchor package within the "
            "same registry. Returns neighbours by |trust_score − anchor.trust_score|. "
            "Use when the user asks 'what's like X?' or needs peers at a similar "
            "quality tier."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": _SLUG_PROP,
                "registry": _REGISTRY_PROP,
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10, max 50).",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["slug"],
        },
    },
    {
        "name": "get_verticals",
        "description": (
            "List all Nerq-published verticals (npm, pypi, vpn, antivirus, etc.) with "
            "entity counts, display groups, and the canonical 'best_slug' listing for "
            "each. Use when the user asks 'what categories does Nerq cover?' or needs "
            "to route a query to the right vertical."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_by_registry",
        "description": (
            "Top packages in a single registry ranked by Trust Score. Optional "
            "min_trust_score floor and offset for pagination. Use when the user asks "
            "'top npm packages', 'highest-rated pypi libraries', or needs a leaderboard."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "registry": {
                    "type": "string",
                    "description": "Registry key, e.g. 'npm', 'pypi', 'crates', 'homebrew', 'gems'.",
                },
                "min_trust_score": {
                    "type": "number",
                    "description": "Optional trust-score floor (0–100).",
                    "minimum": 0,
                    "maximum": 100,
                },
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "default": 0, "minimum": 0},
            },
            "required": ["registry"],
        },
    },
    {
        "name": "get_alternatives",
        "description": (
            "Higher-rated, non-deprecated packages in the same registry as the anchor. "
            "Use when the user asks 'is there a better alternative to X?', 'replace "
            "deprecated X', or needs safer substitutes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": _SLUG_PROP,
                "registry": _REGISTRY_PROP,
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            },
            "required": ["slug"],
        },
    },
    {
        "name": "get_trust_history",
        "description": (
            "Trust-score change history for a package (old_score, new_score, change, "
            "reason) within a configurable look-back window. Use when the user asks "
            "'has X's score changed?', 'why did X drop?', or needs volatility data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": _SLUG_PROP,
                "registry": _REGISTRY_PROP,
                "days": {
                    "type": "integer",
                    "description": "Look-back window in days (default 365, max 3650).",
                    "default": 365,
                    "minimum": 1,
                    "maximum": 3650,
                },
                "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 500},
            },
            "required": ["slug"],
        },
    },
    {
        "name": "search_by_dimension",
        "description": (
            "Find packages scoring high on a single trust dimension (security, "
            "maintenance, popularity, community, quality, privacy, transparency, "
            "reliability, openssf). Optional registry filter. Use when the user asks "
            "'most secure npm packages', 'best-maintained pypi libraries', etc."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dimension": {
                    "type": "string",
                    "enum": sorted(DIMENSION_COLUMNS.keys()),
                    "description": "Trust dimension to rank by.",
                },
                "registry": _REGISTRY_PROP,
                "min_score": {
                    "type": "number",
                    "description": "Minimum dimension score (default 70).",
                    "minimum": 0,
                    "maximum": 100,
                    "default": 70,
                },
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
            "required": ["dimension"],
        },
    },
]


TOOL_HANDLERS: dict[str, Any] = {
    "get_rating": _get_rating,
    "get_signals": _get_signals,
    "get_dependencies": _get_dependencies,
    "compare_packages": _compare_packages,
    "find_similar": _find_similar,
    "get_verticals": _get_verticals,
    "list_by_registry": _list_by_registry,
    "get_alternatives": _get_alternatives,
    "get_trust_history": _get_trust_history,
    "search_by_dimension": _search_by_dimension,
}


# Sanity check: every schema has a handler and vice versa.
_schema_names = {t["name"] for t in TOOLS}
_handler_names = set(TOOL_HANDLERS.keys())
assert _schema_names == _handler_names, (
    f"schema/handler mismatch: schemas={_schema_names} handlers={_handler_names}"
)
assert len(TOOLS) == 10, f"expected 10 tools, got {len(TOOLS)}"
