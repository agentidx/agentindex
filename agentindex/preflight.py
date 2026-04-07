"""
Preflight Trust Check — Agent-to-agent trust verification
Route: GET /v1/preflight?target=...&caller=...
       POST /v1/preflight/batch — batch check up to 50 agents
Zero auth, 1-hour HTTP cache, 5-min internal cache per caller+target pair.
"""
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from agentindex.db.models import get_session

MISSING_LOG = Path(__file__).parent.parent / "data" / "missing_targets.json"


def _log_missing_target(target, user_agent=""):
    """Log a missed preflight target for future page creation."""
    try:
        data = json.loads(MISSING_LOG.read_text()) if MISSING_LOG.exists() else {}
        key = target.lower().strip()
        if key in data:
            data[key]["count"] += 1
            data[key]["last_seen"] = datetime.utcnow().isoformat()
        else:
            data[key] = {"count": 1, "first_seen": datetime.utcnow().isoformat(),
                        "last_seen": datetime.utcnow().isoformat(), "user_agent": user_agent[:100]}
        # Keep only top 1000 by count
        if len(data) > 1200:
            sorted_items = sorted(data.items(), key=lambda x: x[1]["count"], reverse=True)[:1000]
            data = dict(sorted_items)
        MISSING_LOG.write_text(json.dumps(data, indent=2))
    except Exception:
        pass  # Never fail on logging

router_preflight = APIRouter(tags=["preflight"])

_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "crypto", "crypto_trust.db")

# In-memory cache per worker: (target, caller) → (result, timestamp)
_cache: dict = {}
_CACHE_TTL = 300  # 5 minutes

# Redis cross-worker cache for preflight results
_REDIS_PREFLIGHT_TTL = 120  # 2 minutes in Redis
_redis_pf = None
def _get_redis_pf():
    global _redis_pf
    if _redis_pf is None:
        try:
            import redis
            _redis_pf = redis.Redis(host='localhost', port=6379, db=1, socket_timeout=0.1)
            _redis_pf.ping()
        except Exception:
            _redis_pf = False
    return _redis_pf if _redis_pf else None

# Trust floor for well-known packages whose DB scores are unrealistically low.
# Key: lowercase query name or substring match. Value: minimum trust score.
_TRUST_FLOOR = {
    "openai": 85,
    "anthropic": 85,
    "cursor": 82,
    "tensorflow": 88,
    "pytorch": 88,
    "huggingface": 85,
    "transformers": 87,
    "numpy": 90,
    "pandas": 90,
    "scikit-learn": 88,
    "react": 90,
    "next.js": 88,
    "nextjs": 88,
    "vercel": 85,
    "stripe": 88,
    "fastapi": 86,
    "flask": 85,
    "django": 88,
    "express": 86,
}

_GRADE_MAP = [(90, "A+"), (80, "A"), (70, "B+"), (60, "B"), (50, "C"), (40, "D"), (0, "F")]


def _apply_trust_floor(query: str, trust: float, t: dict) -> tuple[float, dict]:
    """Apply minimum trust score for well-known packages."""
    q = query.lower().strip()
    floor = _TRUST_FLOOR.get(q)
    if floor and trust < floor:
        trust = float(floor)
        grade = next(g for threshold, g in _GRADE_MAP if trust >= threshold)
        t = dict(t)
        t["trust_score"] = trust
        t["grade"] = grade
    return trust, t


def _get_compatibility(agent_name):
    """Get compatibility data from SQLite for preflight enrichment."""
    try:
        if not os.path.exists(_SQLITE_PATH):
            return {}
        conn = sqlite3.connect(_SQLITE_PATH)
        try:
            # Frameworks
            fws = conn.execute(
                "SELECT framework FROM agent_frameworks WHERE agent_name = ? OR agent_name LIKE ?",
                (agent_name, f"%{agent_name}%")
            ).fetchall()
            frameworks = list(set(r[0] for r in fws))

            # MCP compatible clients
            clients = conn.execute(
                "SELECT client FROM mcp_compatibility WHERE server_name = ? OR server_name LIKE ?",
                (agent_name, f"%{agent_name}%")
            ).fetchall()
            mcp_clients = list(set(r[0] for r in clients))

            # Deps + vulnerability count
            deps = conn.execute(
                "SELECT COUNT(*) FROM agent_dependencies WHERE agent_name = ? OR agent_name LIKE ?",
                (agent_name, f"%{agent_name}%")
            ).fetchone()
            dep_count = deps[0] if deps else 0

            vuln = conn.execute(
                "SELECT COUNT(DISTINCT ad.dependency_name) FROM agent_dependencies ad "
                "INNER JOIN agent_vulnerabilities av ON ad.dependency_name = av.agent_name "
                "WHERE ad.agent_name = ? OR ad.agent_name LIKE ?",
                (agent_name, f"%{agent_name}%")
            ).fetchone()
            vuln_count = vuln[0] if vuln else 0

            # Detect language
            reg = conn.execute(
                "SELECT DISTINCT registry FROM agent_dependencies WHERE agent_name = ? OR agent_name LIKE ? LIMIT 2",
                (agent_name, f"%{agent_name}%")
            ).fetchall()
            registries = set(r[0] for r in reg)
            language = "python" if "pypi" in registries else "javascript" if "npm" in registries else None
            if "pypi" in registries and "npm" in registries:
                language = "python+javascript"

            health = "GOOD" if vuln_count == 0 else "CAUTION" if vuln_count <= 2 else "POOR"

            result = {}
            if frameworks:
                result["frameworks"] = frameworks
            if language:
                result["language"] = language
            if mcp_clients:
                result["mcp_compatible_clients"] = mcp_clients
            if dep_count > 0:
                result["dependency_health"] = health
                result["vulnerable_deps"] = vuln_count
            return result
        finally:
            conn.close()
    except Exception:
        return {}


def _row_to_dict(row) -> dict:
    """Convert a DB row to agent dict."""
    last_commit_days = None
    if row[9]:
        try:
            delta = datetime.now(timezone.utc) - row[9].replace(tzinfo=timezone.utc if row[9].tzinfo is None else row[9].tzinfo)
            last_commit_days = delta.days
        except Exception:
            pass
    return {
        "id": row[0],
        "name": row[1],
        "trust_score": round(float(row[2]), 1) if row[2] else None,
        "grade": row[3],
        "category": row[4],
        "source": row[5],
        "last_updated": row[6].isoformat() if row[6] else None,
        "verified": bool(row[7]) or (float(row[2]) >= 70 if row[2] else False),
        "stars": row[8],
        "last_commit_days_ago": last_commit_days,
    }


def _lookup_best(name: str, session) -> dict | None:
    """Find entity by name across software_registry AND agents.

    Resolution order:
    0. software_registry — exact name match (consumer apps with downloads)
    1. software_registry — exact name match (dev packages)
    2. _SLUG_OVERRIDES for canonical name mapping (agents)
    3. agents — exact name match
    4. agents — suffix/fuzzy match
    """
    if not name:
        return None

    session.execute(text("SET LOCAL statement_timeout = '3s'"))
    session.execute(text("SET LOCAL work_mem = '2MB'"))
    nl = name.lower().strip()

    # 0. software_registry: exact name match, prefer consumer registries with downloads
    def _sr_to_preflight(row, slug):
        """Convert software_registry row to preflight-compatible dict."""
        r = dict(row._mapping)
        return {
            "id": "sr-" + slug,
            "name": r["name"],
            "trust_score": round(float(r.get("trust_score") or 50), 1),
            "grade": r.get("trust_grade") or "D",
            "category": r.get("category") or r.get("source"),
            "source": r.get("source") or r.get("category"),
            "last_updated": None,
            "verified": (r.get("trust_score") or 0) >= 70,
            "stars": r.get("stars") or 0,
            "last_commit_days_ago": None,
        }

    # Consumer product overrides for well-known apps
    _CO = {
        "tiktok": ("android", "TikTok%"), "whatsapp": ("android", "WhatsApp Messenger"),
        "signal": ("android", "Signal Private Messenger"), "instagram": ("android", "Instagram"),
        "facebook": ("android", "Facebook"), "snapchat": ("android", "Snapchat"),
        "youtube": ("android", "YouTube"), "spotify": ("android", "Spotify%"),
        "telegram": ("android", "Telegram"), "discord": ("android", "Discord%"),
        "reddit": ("android", "Reddit"), "uber": ("android", "Uber%"),
        "amazon": ("android", "Amazon%Shopping%"), "zoom": ("android", "Zoom%"),
        "minecraft": ("android", "Minecraft%"), "roblox": ("android", "Roblox"),
        "nordvpn": ("vpn", "NordVPN"), "expressvpn": ("vpn", "ExpressVPN"),
        "mullvad": ("vpn", "Mullvad VPN"), "protonvpn": ("vpn", "ProtonVPN"),
        "notion": ("android", "Notion%"), "dropbox": ("android", "Dropbox%"),
        "slack": ("android", "Slack%"), "pinterest": ("android", "Pinterest"),
        "netflix": ("android", "Netflix"), "twitch": ("android", "Twitch%"),
        "paypal": ("android", "PayPal%"), "duolingo": ("android", "Duolingo%"),
    }
    # Try both raw and normalized (no hyphens/spaces)
    nl_norm = nl.replace("-", "").replace("_", "").replace(" ", "")
    co = _CO.get(nl) or _CO.get(nl_norm)
    if co:
        cr = session.execute(text("""
            SELECT name, trust_score, trust_grade, registry as category, registry as source, downloads as stars
            FROM software_registry WHERE registry = :reg AND lower(name) LIKE lower(:pat)
            ORDER BY downloads DESC NULLS LAST LIMIT 1
        """), {"reg": co[0], "pat": co[1]}).fetchone()
        if cr:
            return _sr_to_preflight(cr, nl)

    # EXACT name match in consumer registries (android/ios/vpn) — try both raw and normalized
    for _try_name in [nl, nl_norm]:
        sr_consumer = session.execute(text("""
            SELECT name, trust_score, trust_grade,
                   registry as category, registry as source,
                   downloads as stars
            FROM software_registry
            WHERE (lower(name) = :name OR lower(replace(replace(name, ' ', ''), '-', '')) = :norm)
            AND registry IN ('android','ios','vpn')
            AND COALESCE(downloads, 0) > 100
            ORDER BY downloads DESC NULLS LAST LIMIT 1
        """), {"name": _try_name, "norm": _try_name.replace("-", "").replace(" ", "")}).fetchone()
        if sr_consumer:
            return _sr_to_preflight(sr_consumer, nl)
        if _try_name == nl_norm:
            break

    # Exact name across ALL registries — prioritize npm/pypi over wordpress/steam
    sr_all = session.execute(text("""
        SELECT name, trust_score, trust_grade,
               registry as category, registry as source,
               downloads as stars
        FROM software_registry
        WHERE lower(name) = :name
        ORDER BY
            CASE registry
                WHEN 'npm' THEN 1 WHEN 'pypi' THEN 2 WHEN 'crates' THEN 3
                WHEN 'go' THEN 4 WHEN 'nuget' THEN 5 WHEN 'gems' THEN 6
                WHEN 'packagist' THEN 7 WHEN 'homebrew' THEN 8
                WHEN 'vscode' THEN 9 WHEN 'wordpress' THEN 10
                WHEN 'steam' THEN 11 WHEN 'firefox' THEN 12
                ELSE 20
            END,
            COALESCE(downloads, 0) DESC NULLS LAST
        LIMIT 1
    """), {"name": nl}).fetchone()
    if sr_all:
        return _sr_to_preflight(sr_all, nl)

    # Fuzzy: name STARTS WITH slug, consumer registries ONLY, high downloads
    sr_fuzzy = session.execute(text("""
        SELECT name, trust_score, trust_grade,
               registry as category, registry as source,
               downloads as stars
        FROM software_registry
        WHERE lower(name) LIKE :starts
        AND registry IN ('android','ios','vpn')
        AND COALESCE(downloads, 0) > 1000000
        ORDER BY downloads DESC NULLS LAST LIMIT 1
    """), {"starts": nl + "%"}).fetchone()
    if sr_fuzzy:
        return _sr_to_preflight(sr_fuzzy, nl)

    # Use slug overrides for well-known agents
    from agentindex.agent_safety_pages import _SLUG_OVERRIDES
    canonical = _SLUG_OVERRIDES.get(name.lower())
    if canonical:
        # Try exact match with canonical name first
        row = session.execute(text("""
            SELECT id::text, name, COALESCE(trust_score_v2, trust_score) AS trust_score,
                   trust_grade, category, source, updated_at, is_verified,
                   stars, updated_at
            FROM entity_lookup
            WHERE name_lower = lower(:name) AND is_active = true
            ORDER BY COALESCE(stars, 0) DESC, COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
            LIMIT 1
        """), {"name": canonical}).fetchone()
        if row:
            return _row_to_dict(row)
        # Also try slug-style matching for canonical name
        canonical_lower = canonical.lower()
        row = session.execute(text("""
            SELECT id::text, name, COALESCE(trust_score_v2, trust_score) AS trust_score,
                   trust_grade, category, source, updated_at, is_verified,
                   stars, updated_at
            FROM entity_lookup
            WHERE (name_lower LIKE lower(:suffix) OR name_lower LIKE lower(:pattern))
                  AND is_active = true
            ORDER BY COALESCE(stars, 0) DESC, COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
            LIMIT 1
        """), {"suffix": f"%/{canonical_lower}", "pattern": f"%{canonical_lower}%"}).fetchone()
        if row:
            return _row_to_dict(row)

    # Standard lookup: exact and suffix matches share rank 1 (org/name is canonical),
    # fuzzy matches are rank 2. Within each rank, prefer higher stars.
    row = session.execute(text("""
        SELECT id::text, name, COALESCE(trust_score_v2, trust_score) AS trust_score,
               trust_grade, category, source, updated_at, is_verified,
               stars, updated_at
        FROM (
            SELECT id, name, trust_score, trust_score_v2, trust_grade, category, source,
                   updated_at, is_verified, stars, 1 AS _r
            FROM entity_lookup WHERE name_lower = lower(:name) AND is_active = true
          UNION ALL
            SELECT id, name, trust_score, trust_score_v2, trust_grade, category, source,
                   updated_at, is_verified, stars, 1 AS _r
            FROM entity_lookup WHERE name_lower LIKE lower(:suffix) AND is_active = true
          UNION ALL
            SELECT id, name, trust_score, trust_score_v2, trust_grade, category, source,
                   updated_at, is_verified, stars, 2 AS _r
            FROM entity_lookup WHERE name_lower LIKE lower(:pattern) AND is_active = true
        ) sub
        ORDER BY _r ASC, COALESCE(stars, 0) DESC, COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
        LIMIT 1
    """), {"name": name, "suffix": f"%/{name}", "pattern": f"%{name}%"}).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def _slug_from_name(name: str, source: str | None) -> str:
    """Build details URL slug from agent name."""
    slug = name.lower().replace("/", "").replace(" ", "-")
    if source and "github" in source:
        return f"/safe/{name}"
    return f"/safe/{slug}"


def _recommendation(target_trust, caller_trust):
    """Compute interaction recommendation."""
    if target_trust is None:
        return "UNKNOWN"
    if target_trust < 40:
        return "DENY"
    if target_trust >= 70 and (caller_trust is None or caller_trust >= 40):
        return "PROCEED"
    return "CAUTION"


def _interaction_risk(target_trust, caller_trust):
    """Compute interaction risk level."""
    if target_trust is None:
        return "UNKNOWN"
    if target_trust >= 70 and (caller_trust is None or caller_trust >= 50):
        return "LOW"
    if target_trust >= 40:
        return "MEDIUM"
    return "HIGH"


def _compliance_flags(target_trust, caller_trust):
    """Generate compliance flags."""
    flags = []
    if target_trust is not None and target_trust < 40:
        flags.append("TARGET_LOW_TRUST")
    if caller_trust is not None and caller_trust < 40:
        flags.append("CALLER_LOW_TRUST")
    if target_trust is not None and target_trust < 70:
        flags.append("TARGET_NOT_VERIFIED")
    return flags


def _get_enrichment(agent_id: str) -> dict:
    """Get CVE, download, and license data from SQLite."""
    result = {"security": {}, "popularity": {}, "activity": {}}
    try:
        conn = sqlite3.connect(_SQLITE_PATH, timeout=2)
        conn.row_factory = sqlite3.Row
        # CVEs
        cve_row = conn.execute("""
            SELECT COUNT(*) as cnt,
                   MAX(severity) as max_sev,
                   MAX(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as has_active
            FROM agent_vulnerabilities WHERE agent_id = ?
        """, (agent_id,)).fetchone()
        if cve_row and cve_row["cnt"] > 0:
            result["security"] = {
                "known_cves": cve_row["cnt"],
                "max_severity": cve_row["max_sev"],
                "has_active_advisory": bool(cve_row["has_active"]),
            }
        else:
            result["security"] = {"known_cves": 0, "max_severity": None, "has_active_advisory": False}

        # License
        lic = conn.execute("SELECT license_spdx, license_category FROM agent_licenses WHERE agent_id = ?", (agent_id,)).fetchone()
        if lic:
            result["security"]["license"] = lic["license_spdx"]
            result["security"]["license_category"] = lic["license_category"]

        # Downloads
        npm = conn.execute("SELECT weekly_downloads FROM package_downloads WHERE agent_id = ? AND registry = 'npm'", (agent_id,)).fetchone()
        pypi = conn.execute("SELECT weekly_downloads FROM package_downloads WHERE agent_id = ? AND registry = 'pypi'", (agent_id,)).fetchone()
        result["popularity"] = {
            "npm_weekly_downloads": npm["weekly_downloads"] if npm else None,
            "pypi_weekly_downloads": pypi["weekly_downloads"] if pypi else None,
        }
        conn.close()
    except Exception:
        pass
    return result


_alt_cache = {}
_ALT_CACHE_TTL = 600  # 10 min


def _get_alternatives(name: str, category: str, trust_score: float, session) -> list:
    """Find 3 similar agents with higher or similar trust scores. Cached 10 min."""
    cache_key = f"{category}:{name}"
    now = time.time()
    if cache_key in _alt_cache:
        val, ts = _alt_cache[cache_key]
        if now - ts < _ALT_CACHE_TTL:
            return val
    try:
        cat = category or ""
        # Try same-category first, sorted by stars (prefer well-known)
        rows = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as ts, source, stars
            FROM entity_lookup
            WHERE is_active = true
            AND name_lower != lower(:name)
            AND category = :category
            AND category IS NOT NULL AND category != ''
            AND COALESCE(trust_score_v2, trust_score) >= 50
            AND COALESCE(stars, 0) > 0
            ORDER BY COALESCE(stars, 0) DESC
            LIMIT 3
        """), {"name": name, "category": cat}).fetchall()

        # Fallback: popular agents across all categories (use direct column, not COALESCE)
        if len(rows) < 3:
            fallback = session.execute(text("""
                SELECT name, trust_score_v2 as ts, source, stars
                FROM entity_lookup
                WHERE is_active = true
                AND name_lower != lower(:name)
                AND trust_score_v2 >= 60
                AND stars >= 100
                ORDER BY stars DESC
                LIMIT :lim
            """), {"name": name, "lim": 3 - len(rows)}).fetchall()
            existing_names = {r[0].lower() for r in rows}
            rows = list(rows) + [r for r in fallback if r[0].lower() not in existing_names]

        result = [
            {"name": r[0], "trust_score": round(float(r[1]), 1) if r[1] else None,
             "url": f"https://nerq.ai/safe/{r[0].lower().replace(' ', '-')}"}
            for r in rows[:3]
        ]
        _alt_cache[cache_key] = (result, time.time())
        return result
    except Exception:
        return []


def _etag(result: dict) -> str:
    """Generate ETag from trust score + grade + recommendation."""
    sig = f"{result.get('target_trust')}:{result.get('target_grade')}:{result.get('recommendation')}"
    return hashlib.md5(sig.encode()).hexdigest()[:16]


@router_preflight.get("/v1/preflight")
def preflight_check(
    request: Request,
    target: str = Query(..., description="Agent name to check"),
    caller: str = Query(None, description="Calling agent name (optional)"),
):
    """Preflight Trust Check — verify agent trust before interaction."""
    t0 = time.time()
    cache_key = (target.lower(), (caller or "").lower())

    # Check in-memory cache (per-worker)
    if cache_key in _cache:
        cached, ts = _cache[cache_key]
        if t0 - ts < _CACHE_TTL:
            resp = dict(cached)
            resp["response_time_ms"] = round((time.time() - t0) * 1000, 1)
            etag = _etag(resp)
            return JSONResponse(
                content=resp,
                headers={
                    "Cache-Control": "public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400",
                    "ETag": f'"{etag}"',
                },
            )

    # Check Redis cross-worker cache
    _rpf = _get_redis_pf()
    if _rpf:
        try:
            _redis_key = f"pf:{target.lower()}:{(caller or '').lower()}"
            _redis_cached = _rpf.get(_redis_key)
            if _redis_cached:
                resp = json.loads(_redis_cached)
                resp["response_time_ms"] = round((time.time() - t0) * 1000, 1)
                # Backfill in-memory cache
                _cache[cache_key] = (resp, t0)
                etag = _etag(resp)
                return JSONResponse(
                    content=resp,
                    headers={
                        "Cache-Control": "public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400",
                        "ETag": f'"{etag}"',
                        "X-Cache": "HIT-REDIS",
                    },
                )
        except Exception:
            pass

    session = get_session()
    try:
        t = _lookup_best(target, session)
        c = _lookup_best(caller, session) if caller else None

        target_trust = t["trust_score"] if t else None
        caller_trust = c["trust_score"] if c else None

        # Log missed targets for future page creation
        if t is None:
            ua = request.headers.get("user-agent", "")
            _log_missing_target(target, ua)

        # Trust floor for well-known packages that are obviously safe
        if t and target_trust is not None:
            target_trust, t = _apply_trust_floor(target, target_trust, t)

        # Enrichment data from SQLite
        enrichment = _get_enrichment(t["id"]) if t else {}
        alternatives = _get_alternatives(t["name"], t["category"], target_trust, session) if t else []
    finally:
        session.close()

    # Economics enrichment
    economics = {}
    if t:
        try:
            conn_econ = sqlite3.connect(_SQLITE_PATH, timeout=2)
            # Pricing model
            pricing_row = conn_econ.execute(
                "SELECT pricing_model, price_monthly FROM agent_pricing WHERE agent_name = ? OR agent_name LIKE ? LIMIT 3",
                (t["name"], f"%{t['name']}%")
            ).fetchall()
            if pricing_row:
                economics["pricing_model"] = pricing_row[0][0]
                economics["free_tier"] = any((r[1] or 0) == 0 for r in pricing_row)
            # Cost estimates
            cost_row = conn_econ.execute(
                "SELECT MIN(estimated_cost_usd), MAX(estimated_cost_usd) FROM agent_cost_estimates "
                "WHERE (agent_name = ? OR agent_name LIKE ?) AND task_type = 'code_review'",
                (t["name"], f"%{t['name']}%")
            ).fetchone()
            if cost_row and cost_row[0] is not None:
                if cost_row[0] == cost_row[1]:
                    economics["estimated_cost_per_task"] = f"${cost_row[0]:.4f}"
                else:
                    economics["estimated_cost_per_task"] = f"${cost_row[0]:.4f}-${cost_row[1]:.4f}"
            # Value score
            if target_trust is not None:
                pm = economics.get("pricing_model")
                if pm == "open_source_free":
                    economics["value_score"] = min(100, int(target_trust))
                elif economics.get("free_tier"):
                    economics["value_score"] = min(100, int(target_trust * 0.95))
                else:
                    economics["value_score"] = min(100, int(target_trust * 0.7))
            # Cheaper alternative
            if target_trust and t.get("category"):
                alt_row = conn_econ.execute(
                    "SELECT ap.agent_name FROM agent_pricing ap "
                    "WHERE ap.pricing_model = 'open_source_free' AND ap.agent_name != ? LIMIT 1",
                    (t["name"],)
                ).fetchone()
                if alt_row:
                    economics["cheaper_alternative"] = {"name": alt_row[0], "cost": "free"}
            conn_econ.close()
        except Exception:
            pass

    result = {
        "target": target,
        "target_trust": target_trust,
        "target_grade": t["grade"] if t else None,
        "target_verified": t["verified"] if t else None,
        "target_category": t["category"] if t else None,
        "target_source": t["source"] if t else None,
        "target_last_updated": t["last_updated"] if t else None,
        "details_url": f"https://nerq.ai{_slug_from_name(t['name'], t['source'])}" if t else None,
        "caller": caller,
        "caller_trust": caller_trust,
        "caller_grade": c["grade"] if c else None,
        "caller_verified": c["verified"] if c else None,
        "interaction_risk": _interaction_risk(target_trust, caller_trust),
        "recommendation": _recommendation(target_trust, caller_trust),
        "compliance_flags": _compliance_flags(target_trust, caller_trust),
        "security": enrichment.get("security", {}),
        "popularity": {
            **(enrichment.get("popularity", {})),
            "github_stars": t["stars"] if t else None,
        },
        "activity": {
            "last_commit_days_ago": t["last_commit_days_ago"] if t else None,
        },
        "alternatives": alternatives,
        "compatibility": _get_compatibility(t["name"] if t else target),
        "economics": economics,
        "verified_by": "nerq.ai",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "response_time_ms": round((time.time() - t0) * 1000, 1),
    }

    # Cache result (in-memory + Redis)
    _cache[cache_key] = (result, time.time())

    # Write-through to Redis for cross-worker sharing
    _rpf2 = _get_redis_pf()
    if _rpf2:
        try:
            _redis_key = f"pf:{target.lower()}:{(caller or '').lower()}"
            _rpf2.setex(_redis_key, _REDIS_PREFLIGHT_TTL, json.dumps(result))
        except Exception:
            pass

    # Evict old entries periodically
    if len(_cache) > 10000:
        _cache.clear()

    etag = _etag(result)
    return JSONResponse(
        content=result,
        headers={
            "Cache-Control": "public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400",
            "ETag": f'"{etag}"',
        },
    )


@router_preflight.post("/v1/preflight/batch")
async def preflight_batch(request: Request):
    """Batch preflight check — up to 50 agents at once."""
    t0 = time.time()
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    targets = body.get("targets", [])
    if not targets or not isinstance(targets, list):
        return JSONResponse(status_code=400, content={"error": "targets must be a non-empty array"})
    if len(targets) > 50:
        return JSONResponse(status_code=400, content={"error": "Max 50 targets per batch"})

    session = get_session()
    results = []
    try:
        for target_name in targets:
            if not isinstance(target_name, str):
                results.append({"target": str(target_name), "error": "invalid target"})
                continue
            t = _lookup_best(target_name, session)
            target_trust = t["trust_score"] if t else None
            enrichment = _get_enrichment(t["id"]) if t else {}

            # Log missed targets in batch too
            if t is None:
                ua = request.headers.get("user-agent", "")
                _log_missing_target(target_name, ua)

            results.append({
                "target": target_name,
                "target_trust": target_trust,
                "target_grade": t["grade"] if t else None,
                "target_verified": t["verified"] if t else None,
                "target_category": t["category"] if t else None,
                "details_url": f"https://nerq.ai{_slug_from_name(t['name'], t['source'])}" if t else None,
                "recommendation": _recommendation(target_trust, None),
                "security": enrichment.get("security", {}),
                "popularity": {
                    **(enrichment.get("popularity", {})),
                    "github_stars": t["stars"] if t else None,
                },
            })
    finally:
        session.close()

    return JSONResponse(content={
        "results": results,
        "count": len(results),
        "verified_by": "nerq.ai",
        "response_time_ms": round((time.time() - t0) * 1000, 1),
    })
