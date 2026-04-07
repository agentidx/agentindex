#!/usr/bin/env python3
"""
Multi-Registry Enrichment Pipeline — enriches WordPress, Crates, NuGet, Steam,
iOS, Go, RubyGems, Packagist, Homebrew, VS Code, Firefox, Android.

Run: python3 -m agentindex.crawlers.registry_enrichment <registry> [limit]
Example: python3 -m agentindex.crawlers.registry_enrichment wordpress 50000
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agentindex.db.models import get_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("registry_enrichment")

RATE_LIMITS = {
    "wordpress": 0.1,    # 10 req/s
    "crates": 1.0,       # 1 req/s (strict!)
    "nuget": 0.05,       # 20 req/s
    "steam": 1.5,        # 200/5min = 0.67/s, be safe
    "ios": 3.0,          # 20/min = 0.33/s, be safe
    "go": 0.2,           # 5 req/s
    "gems": 0.1,         # 10 req/s
    "packagist": 0.1,    # 10 req/s
    "homebrew": 0.1,     # 10 req/s
    "vscode": 0.5,       # 2 req/s
    "firefox": 0.5,      # 2 req/s
    "android": 1.0,      # careful with scraping
    "chrome": 0.01,      # no API call — DB only
    "saas": 0.01,        # no API call — DB only
    "ai_tool": 0.01,     # no API call — DB only
    "crypto": 0.01,      # no API call — DB only
}


def enrich_wordpress(session, pkg_id, slug):
    try:
        r = requests.get(f"https://api.wordpress.org/plugins/info/1.2/?action=plugin_information&slug={slug}", timeout=10)
        if r.status_code != 200: return False
        d = r.json()
        if isinstance(d, str) or not d: return False  # "false" for missing plugins
        session.execute(text("""
            UPDATE software_registry SET
                downloads = COALESCE(:dl, downloads),
                description = COALESCE(NULLIF(:desc, ''), description),
                author = COALESCE(NULLIF(:auth, ''), author),
                latest_version = :ver,
                release_count = :rels,
                enriched_at = NOW()
            WHERE id = :id
        """), {
            "id": str(pkg_id), "dl": d.get("active_installs") or d.get("downloaded"),
            "desc": (d.get("short_description") or "")[:500],
            "auth": (d.get("author") or "")[:200],
            "ver": (d.get("version") or "")[:50],
            "rels": len(d.get("versions", {})),
        })
        return True
    except Exception as e:
        log.warning(f"WP {slug}: {e}")
        return False


def enrich_crates(session, pkg_id, name):
    try:
        r = requests.get(f"https://crates.io/api/v1/crates/{name}",
                         headers={"User-Agent": "nerq.ai trust engine"}, timeout=10)
        if r.status_code != 200: return False
        d = r.json().get("crate", {})
        session.execute(text("""
            UPDATE software_registry SET
                downloads = COALESCE(:dl, downloads),
                description = COALESCE(NULLIF(:desc, ''), description),
                repository_url = COALESCE(NULLIF(:repo, ''), repository_url),
                latest_version = :ver,
                enriched_at = NOW()
            WHERE id = :id
        """), {
            "id": str(pkg_id), "dl": d.get("downloads"),
            "desc": (d.get("description") or "")[:500],
            "repo": d.get("repository") or "",
            "ver": (d.get("newest_version") or "")[:50],
        })
        return True
    except Exception as e:
        log.warning(f"Crate {name}: {e}")
        return False


def enrich_nuget(session, pkg_id, name):
    try:
        r = requests.get(f"https://api.nuget.org/v3/registration5-semver1/{name.lower()}/index.json", timeout=10)
        if r.status_code != 200: return False
        d = r.json()
        pages = d.get("items", [])
        total_dl = d.get("totalDownloads") or 0
        latest = ""
        if pages:
            last_page = pages[-1]
            items = last_page.get("items", [])
            if items:
                cat = items[-1].get("catalogEntry", {})
                latest = cat.get("version", "")
        session.execute(text("""
            UPDATE software_registry SET
                downloads = COALESCE(:dl, downloads),
                latest_version = COALESCE(NULLIF(:ver, ''), latest_version),
                enriched_at = NOW()
            WHERE id = :id
        """), {"id": str(pkg_id), "dl": total_dl, "ver": latest[:50]})
        return True
    except Exception as e:
        log.warning(f"NuGet {name}: {e}")
        return False


def enrich_steam(session, pkg_id, name):
    """Steam uses app IDs stored in raw_data or slug."""
    try:
        # Try to get app_id from raw_data
        row = session.execute(text("SELECT raw_data, slug FROM software_registry WHERE id = :id"),
                              {"id": str(pkg_id)}).fetchone()
        raw = row[0] if row else None
        app_id = None
        if isinstance(raw, dict):
            app_id = raw.get("steam_appid") or raw.get("appid")
        if not app_id and row:
            # Try slug as app_id
            try:
                app_id = int(row[1])
            except (ValueError, TypeError):
                pass
        if not app_id:
            session.execute(text("UPDATE software_registry SET enriched_at = NOW() WHERE id = :id"),
                            {"id": str(pkg_id)})
            return True  # Skip, no app_id

        r = requests.get(f"https://store.steampowered.com/api/appdetails?appids={app_id}", timeout=10)
        if r.status_code != 200: return False
        data = r.json().get(str(app_id), {})
        if not data.get("success"): return False
        d = data.get("data", {})
        session.execute(text("""
            UPDATE software_registry SET
                description = COALESCE(NULLIF(:desc, ''), description),
                author = COALESCE(NULLIF(:dev, ''), author),
                enriched_at = NOW()
            WHERE id = :id
        """), {
            "id": str(pkg_id),
            "desc": (d.get("short_description") or "")[:500],
            "dev": ", ".join(d.get("developers", []))[:200],
        })
        return True
    except Exception as e:
        log.warning(f"Steam {name}: {e}")
        return False


def enrich_ios(session, pkg_id, name):
    """iOS uses app IDs or bundle IDs."""
    try:
        row = session.execute(text("SELECT raw_data, slug FROM software_registry WHERE id = :id"),
                              {"id": str(pkg_id)}).fetchone()
        raw = row[0] if row else None
        track_id = None
        if isinstance(raw, dict):
            track_id = raw.get("trackId") or raw.get("id")
        if not track_id:
            session.execute(text("UPDATE software_registry SET enriched_at = NOW() WHERE id = :id"),
                            {"id": str(pkg_id)})
            return True

        r = requests.get(f"https://itunes.apple.com/lookup?id={track_id}", timeout=10)
        if r.status_code != 200: return False
        results = r.json().get("results", [])
        if not results: return False
        d = results[0]
        session.execute(text("""
            UPDATE software_registry SET
                description = COALESCE(NULLIF(:desc, ''), description),
                author = COALESCE(NULLIF(:dev, ''), author),
                enriched_at = NOW()
            WHERE id = :id
        """), {
            "id": str(pkg_id),
            "desc": (d.get("description") or "")[:500],
            "dev": (d.get("sellerName") or d.get("artistName") or "")[:200],
        })
        return True
    except Exception as e:
        log.warning(f"iOS {name}: {e}")
        return False


def enrich_go(session, pkg_id, name):
    try:
        r = requests.get(f"https://proxy.golang.org/{name}/@latest", timeout=10)
        if r.status_code != 200: return False
        d = r.json()
        session.execute(text("""
            UPDATE software_registry SET
                latest_version = COALESCE(NULLIF(:ver, ''), latest_version),
                enriched_at = NOW()
            WHERE id = :id
        """), {"id": str(pkg_id), "ver": (d.get("Version") or "")[:50]})
        return True
    except Exception as e:
        log.warning(f"Go {name}: {e}")
        return False


def enrich_gems(session, pkg_id, name):
    try:
        r = requests.get(f"https://rubygems.org/api/v1/gems/{name}.json", timeout=10)
        if r.status_code != 200: return False
        d = r.json()
        session.execute(text("""
            UPDATE software_registry SET
                downloads = COALESCE(:dl, downloads),
                description = COALESCE(NULLIF(:desc, ''), description),
                author = COALESCE(NULLIF(:auth, ''), author),
                license = COALESCE(NULLIF(:lic, ''), license),
                repository_url = COALESCE(NULLIF(:repo, ''), repository_url),
                latest_version = :ver,
                enriched_at = NOW()
            WHERE id = :id
        """), {
            "id": str(pkg_id), "dl": d.get("downloads"),
            "desc": (d.get("info") or "")[:500],
            "auth": ", ".join(d.get("authors", "").split(", ")[:3])[:200],
            "lic": ", ".join(d.get("licenses") or [])[:100],
            "repo": (d.get("source_code_uri") or d.get("homepage_uri") or "")[:500],
            "ver": (d.get("version") or "")[:50],
        })
        return True
    except Exception as e:
        log.warning(f"Gem {name}: {e}")
        return False


def enrich_packagist(session, pkg_id, name):
    try:
        # Packagist requires vendor/package format
        if "/" not in name:
            session.execute(text("UPDATE software_registry SET enriched_at = NOW() WHERE id = :id"),
                            {"id": str(pkg_id)})
            return True
        r = requests.get(f"https://packagist.org/packages/{name}.json", timeout=10)
        if r.status_code != 200: return False
        pkg = r.json().get("package", {})
        session.execute(text("""
            UPDATE software_registry SET
                downloads = COALESCE(:dl, downloads),
                description = COALESCE(NULLIF(:desc, ''), description),
                repository_url = COALESCE(NULLIF(:repo, ''), repository_url),
                enriched_at = NOW()
            WHERE id = :id
        """), {
            "id": str(pkg_id), "dl": pkg.get("downloads", {}).get("total"),
            "desc": (pkg.get("description") or "")[:500],
            "repo": (pkg.get("repository") or "")[:500],
        })
        return True
    except Exception as e:
        log.warning(f"Packagist {name}: {e}")
        return False


def enrich_homebrew(session, pkg_id, name):
    try:
        r = requests.get(f"https://formulae.brew.sh/api/formula/{name}.json", timeout=10)
        if r.status_code != 200: return False
        d = r.json()
        dl_30 = d.get("analytics", {}).get("install", {}).get("30d", {})
        total_dl = sum(dl_30.values()) if isinstance(dl_30, dict) else 0
        session.execute(text("""
            UPDATE software_registry SET
                downloads = COALESCE(:dl, downloads),
                description = COALESCE(NULLIF(:desc, ''), description),
                license = COALESCE(NULLIF(:lic, ''), license),
                homepage_url = COALESCE(NULLIF(:hp, ''), homepage_url),
                latest_version = COALESCE(NULLIF(:ver, ''), latest_version),
                enriched_at = NOW()
            WHERE id = :id
        """), {
            "id": str(pkg_id), "dl": total_dl,
            "desc": (d.get("desc") or "")[:500],
            "lic": (d.get("license") or "")[:100],
            "hp": (d.get("homepage") or "")[:500],
            "ver": (d.get("versions", {}).get("stable") or "")[:50],
        })
        return True
    except Exception as e:
        log.warning(f"Homebrew {name}: {e}")
        return False


def enrich_firefox(session, pkg_id, slug):
    try:
        r = requests.get(f"https://addons.mozilla.org/api/v5/addons/addon/{slug}/", timeout=10)
        if r.status_code != 200: return False
        d = r.json()
        session.execute(text("""
            UPDATE software_registry SET
                downloads = COALESCE(:dl, downloads),
                description = COALESCE(NULLIF(:desc, ''), description),
                author = COALESCE(NULLIF(:auth, ''), author),
                latest_version = COALESCE(NULLIF(:ver, ''), latest_version),
                enriched_at = NOW()
            WHERE id = :id
        """), {
            "id": str(pkg_id), "dl": d.get("average_daily_users"),
            "desc": (d.get("summary", {}).get("en-US") or "")[:500],
            "auth": ", ".join(a.get("name", "") for a in d.get("authors", []))[:200],
            "ver": (d.get("current_version", {}).get("version") or "")[:50],
        })
        return True
    except Exception as e:
        log.warning(f"Firefox {slug}: {e}")
        return False


# Score calculation (simplified, same for all registries)
def calculate_trust(session, pkg_id, registry):
    row = session.execute(text("""
        SELECT downloads, release_count, license, description, deprecated, cve_count
        FROM software_registry WHERE id = :id
    """), {"id": str(pkg_id)}).fetchone()
    if not row: return

    dl = row[0] or 0
    release_count = row[1] or 0
    license_str = (row[2] or "").upper()
    description = row[3] or ""
    deprecated = row[4]
    cve_count = row[5] or 0

    if deprecated:
        session.execute(text("UPDATE software_registry SET trust_score=10, trust_grade='F' WHERE id=:id"),
                        {"id": str(pkg_id)})
        return

    security = max(5, 90 - min(cve_count * 10, 40))
    maintenance = 50 + min(release_count, 50)
    maintenance = min(100, maintenance)

    popularity = 0
    if dl > 10_000_000: popularity = 100
    elif dl > 1_000_000: popularity = 90
    elif dl > 100_000: popularity = 75
    elif dl > 10_000: popularity = 60
    elif dl > 1_000: popularity = 45
    elif dl > 100: popularity = 30
    elif dl > 0: popularity = 15

    quality = 30
    if license_str and any(k in license_str for k in ["MIT", "BSD", "APACHE", "ISC", "GPL"]):
        quality += 25
    elif license_str:
        quality += 10
    if len(description) > 30: quality += 10
    quality = min(100, quality)

    community = 35
    total = round(security * 0.25 + maintenance * 0.25 + popularity * 0.15 + community * 0.15 + quality * 0.20, 1)

    grade = "A+" if total >= 90 else "A" if total >= 85 else "A-" if total >= 80 else "B+" if total >= 75 else "B" if total >= 70 else "B-" if total >= 65 else "C+" if total >= 60 else "C" if total >= 55 else "C-" if total >= 50 else "D" if total >= 40 else "F"

    session.execute(text("""
        UPDATE software_registry SET trust_score=:s, trust_grade=:g,
            security_score=:sec, maintenance_score=:m, popularity_score=:p, community_score=:c, quality_score=:q
        WHERE id=:id
    """), {"id": str(pkg_id), "s": total, "g": grade,
           "sec": round(security, 1), "m": round(maintenance, 1),
           "p": round(popularity, 1), "c": round(community, 1), "q": round(quality, 1)})


def enrich_vscode(session, pkg_id, name):
    try:
        # VS Code Marketplace API
        r = requests.post(
            "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery",
            json={"filters": [{"criteria": [{"filterType": 7, "value": name}]}], "flags": 914},
            headers={"Content-Type": "application/json", "Accept": "application/json;api-version=6.1-preview.1"},
            timeout=10,
        )
        if r.status_code != 200:
            return False
        results = r.json().get("results", [{}])[0].get("extensions", [])
        if not results:
            session.execute(text("UPDATE software_registry SET enriched_at = NOW() WHERE id = :id"), {"id": str(pkg_id)})
            return True
        ext = results[0]
        stats = {s["statisticName"]: s["value"] for s in ext.get("statistics", [])}
        desc = ext.get("shortDescription") or ""
        author = ext.get("publisher", {}).get("displayName") or ""
        version = ""
        versions = ext.get("versions", [])
        if versions:
            version = versions[0].get("version") or ""
        installs = int(stats.get("install", 0))

        session.execute(text("""
            UPDATE software_registry SET
                downloads = GREATEST(COALESCE(downloads, 0), :dl),
                description = COALESCE(NULLIF(:desc, ''), description),
                author = COALESCE(NULLIF(:auth, ''), author),
                latest_version = COALESCE(NULLIF(:ver, ''), latest_version),
                enriched_at = NOW()
            WHERE id = :id
        """), {
            "id": str(pkg_id), "dl": installs,
            "desc": desc[:500], "auth": author[:200], "ver": version[:50],
        })
        return True
    except Exception as e:
        log.warning(f"VS Code {name}: {e}")
        return False


def enrich_chrome(session, pkg_id, slug):
    """Mark Chrome extension as enriched (no public API — use existing data)."""
    session.execute(text("UPDATE software_registry SET enriched_at = NOW() WHERE id = :id"),
                    {"id": str(pkg_id)})
    return True


def enrich_saas(session, pkg_id, slug):
    """Mark SaaS entry as enriched (no public API — use existing data)."""
    session.execute(text("UPDATE software_registry SET enriched_at = NOW() WHERE id = :id"),
                    {"id": str(pkg_id)})
    return True


def enrich_ai_tool(session, pkg_id, slug):
    """Mark AI tool as enriched (no public API — use existing data)."""
    session.execute(text("UPDATE software_registry SET enriched_at = NOW() WHERE id = :id"),
                    {"id": str(pkg_id)})
    return True


def enrich_crypto(session, pkg_id, slug):
    """Mark crypto entry as enriched (no public API — use existing data)."""
    session.execute(text("UPDATE software_registry SET enriched_at = NOW() WHERE id = :id"),
                    {"id": str(pkg_id)})
    return True


ENRICHERS = {
    "wordpress": enrich_wordpress,
    "crates": enrich_crates,
    "nuget": enrich_nuget,
    "steam": enrich_steam,
    "ios": enrich_ios,
    "go": enrich_go,
    "gems": enrich_gems,
    "packagist": enrich_packagist,
    "homebrew": enrich_homebrew,
    "firefox": enrich_firefox,
    "vscode": enrich_vscode,
    "chrome": enrich_chrome,
    "saas": enrich_saas,
    "ai_tool": enrich_ai_tool,
    "crypto": enrich_crypto,
}


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python -m agentindex.crawlers.registry_enrichment <registry> [limit]")
        print(f"Registries: {', '.join(ENRICHERS.keys())}")
        sys.exit(1)

    registry = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50000

    if registry not in ENRICHERS:
        print(f"Unknown registry: {registry}. Available: {', '.join(ENRICHERS.keys())}")
        sys.exit(1)

    enricher = ENRICHERS[registry]
    rate_limit = RATE_LIMITS.get(registry, 0.5)

    session = get_session()
    try:
        session.execute(text("SET statement_timeout = '10s'"))
        # Use slug for WordPress/Firefox, name for others
        name_col = "slug" if registry in ("wordpress", "firefox") else "name"
        # Two-phase fetch: kings first (few rows, fast), then rest by name (indexed)
        # Avoids expensive ORDER BY sort on 400K+ unenriched rows
        kings = session.execute(text(f"""
            SELECT id, {name_col} FROM software_registry
            WHERE registry = :reg AND enriched_at IS NULL AND is_king = true
            ORDER BY downloads DESC NULLS LAST
            LIMIT :lim
        """), {"reg": registry, "lim": limit}).fetchall()
        remaining = max(0, limit - len(kings))
        rest = []
        if remaining > 0:
            rest = session.execute(text(f"""
                SELECT id, {name_col} FROM software_registry
                WHERE registry = :reg AND enriched_at IS NULL
                    AND (is_king IS NULL OR is_king = false)
                ORDER BY name ASC
                LIMIT :lim
            """), {"reg": registry, "lim": remaining}).fetchall()
        rows = list(kings) + list(rest)
        session.execute(text("SET statement_timeout = '10s'"))

        total = len(rows)
        log.info(f"{registry} enrichment: {total} entries (limit={limit})")

        done = 0
        for i, row in enumerate(rows):
            if enricher(session, row[0], row[1]):
                try:
                    calculate_trust(session, row[0], registry)
                except Exception:
                    pass
                done += 1

            if (i + 1) % 50 == 0:
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                if (i + 1) % 500 == 0:
                    log.info(f"Progress: {done}/{total} ({done * 100 // max(1, total)}%)")

            time.sleep(rate_limit)

        session.commit()
        log.info(f"{registry} enrichment complete: {done}/{total}")
    except Exception as e:
        log.error(f"Fatal: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    main()
