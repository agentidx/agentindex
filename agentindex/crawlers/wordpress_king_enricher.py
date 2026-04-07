#!/usr/bin/env python3
"""WordPress King Enricher — re-enriches top 5000 WP plugins from wordpress.org API,
flags top 500 as Kings with recalculated trust scores."""
import json, logging, sys, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("wordpress_king_enricher")

API = "https://api.wordpress.org/plugins/info/1.2/"

FIELDS = {
    "request[fields][active_installs]": "true",
    "request[fields][downloaded]": "true",
    "request[fields][tested]": "true",
    "request[fields][requires]": "true",
    "request[fields][rating]": "true",
    "request[fields][ratings]": "true",
    "request[fields][last_updated]": "true",
}


def calc_trust_score(plugin: dict, rank: int) -> tuple[float, str]:
    """Calculate trust score from WP API fields.
    Factors: active_installs, rating, tested compatibility, last_updated recency.
    """
    score = 0.0
    installs = plugin.get("active_installs") or 0
    rating = plugin.get("rating") or 0        # 0-100 scale
    num_ratings = plugin.get("num_ratings") or 0
    tested = plugin.get("tested") or ""
    last_updated = plugin.get("last_updated") or ""

    # Active installs (max 35)
    if installs >= 5_000_000:
        score += 35
    elif installs >= 1_000_000:
        score += 30
    elif installs >= 100_000:
        score += 25
    elif installs >= 10_000:
        score += 20
    elif installs >= 1_000:
        score += 14
    elif installs > 0:
        score += 7

    # Rating quality (max 25)
    if rating >= 90 and num_ratings >= 100:
        score += 25
    elif rating >= 80 and num_ratings >= 50:
        score += 22
    elif rating >= 70 and num_ratings >= 20:
        score += 17
    elif rating >= 60 and num_ratings >= 10:
        score += 12
    elif rating > 0:
        score += 6

    # Tested compatibility (max 15)
    if tested:
        try:
            major = float(tested.split(".")[0])
            if major >= 6:
                score += 15
            elif major >= 5:
                score += 10
            else:
                score += 5
        except (ValueError, IndexError):
            score += 5

    # Recency of last update (max 20)
    if last_updated:
        try:
            lu = datetime.strptime(last_updated[:10], "%Y-%m-%d")
            days = (datetime.now() - lu).days
            if days < 30:
                score += 20
            elif days < 90:
                score += 17
            elif days < 180:
                score += 12
            elif days < 365:
                score += 8
            elif days < 730:
                score += 4
        except (ValueError, TypeError):
            score += 3

    # Base metadata bonus
    score += 5

    score = max(0.0, min(100.0, score))

    if score >= 90:
        grade = "A+"
    elif score >= 80:
        grade = "A"
    elif score >= 70:
        grade = "B+"
    elif score >= 60:
        grade = "B"
    elif score >= 50:
        grade = "C+"
    elif score >= 40:
        grade = "C"
    else:
        grade = "D"

    return round(score, 1), grade


def fetch_page(page: int) -> dict | None:
    """Fetch a single page from wordpress.org plugins API."""
    params = {
        "action": "query_plugins",
        "request[page]": page,
        "request[per_page]": 100,
        "request[browse]": "popular",
        **FIELDS,
    }
    try:
        r = requests.get(API, params=params, timeout=30)
        if r.status_code != 200:
            logger.warning(f"Page {page}: HTTP {r.status_code}")
            return None
        return r.json()
    except Exception as e:
        logger.warning(f"Page {page}: {e}")
        return None


def enrich(pages: int = 50):
    """Fetch top 5000 WP plugins (50 pages x 100), enrich & flag kings."""
    logger.info(f"WordPress King Enricher: fetching {pages} pages ({pages * 100} plugins)")
    session = get_session()
    total_updated = 0
    total_inserted = 0
    global_rank = 0

    for page_num in range(1, pages + 1):
        data = fetch_page(page_num)
        if not data:
            logger.warning(f"Stopping at page {page_num} (no data)")
            break

        plugins = data.get("plugins", [])
        if not plugins:
            logger.info(f"No plugins on page {page_num}, done.")
            break

        for p in plugins:
            global_rank += 1
            slug = p.get("slug", "")
            if not slug:
                continue

            name = (p.get("name") or "").strip()
            desc = (p.get("short_description") or "")[:500]
            author_raw = (p.get("author") or "")
            # Strip HTML from author field
            import re
            author = re.sub(r"<[^>]+>", "", author_raw).strip()[:200]
            version = p.get("version") or ""
            downloads = p.get("downloaded") or 0
            installs = p.get("active_installs") or 0
            is_king = global_rank <= 500

            score, grade = calc_trust_score(p, global_rank)

            # Popularity score: normalize installs to 0-100
            if installs >= 5_000_000:
                pop = 95
            elif installs >= 1_000_000:
                pop = 85
            elif installs >= 100_000:
                pop = 70
            elif installs >= 10_000:
                pop = 55
            elif installs >= 1_000:
                pop = 40
            else:
                pop = 20

            raw = json.dumps({
                "active_installs": installs,
                "rating": p.get("rating"),
                "num_ratings": p.get("num_ratings"),
                "tested": p.get("tested"),
                "requires": p.get("requires"),
                "last_updated": p.get("last_updated"),
                "rank": global_rank,
            })

            # Try UPDATE first
            try:
                result = session.execute(text("""
                    UPDATE software_registry SET
                        description = COALESCE(NULLIF(:desc, ''), description),
                        author = COALESCE(NULLIF(:auth, ''), author),
                        downloads = GREATEST(COALESCE(downloads, 0), :dl),
                        version = :ver,
                        trust_score = :score,
                        trust_grade = :grade,
                        popularity_score = :pop,
                        is_king = CASE WHEN :is_king THEN true ELSE is_king END,
                        enriched_at = NOW(),
                        raw_data = CAST(:raw AS jsonb)
                    WHERE registry = 'wordpress' AND slug = :slug
                """), {
                    "desc": desc, "auth": author, "dl": downloads,
                    "ver": version, "score": score, "grade": grade,
                    "pop": pop, "is_king": is_king, "slug": slug,
                    "raw": raw,
                })

                if result.rowcount == 0:
                    # INSERT new entry
                    session.execute(text("""
                        INSERT INTO software_registry
                            (name, slug, registry, description, author, downloads,
                             version, trust_score, trust_grade, popularity_score,
                             is_king, enriched_at, created_at, raw_data,
                             homepage_url)
                        VALUES
                            (:name, :slug, 'wordpress', :desc, :auth, :dl,
                             :ver, :score, :grade, :pop,
                             :is_king, NOW(), NOW(), CAST(:raw AS jsonb),
                             :homepage)
                    """), {
                        "name": name, "slug": slug, "desc": desc,
                        "auth": author, "dl": downloads, "ver": version,
                        "score": score, "grade": grade, "pop": pop,
                        "is_king": is_king, "raw": raw,
                        "homepage": f"https://wordpress.org/plugins/{slug}/",
                    })
                    total_inserted += 1
                else:
                    total_updated += 1

            except Exception as e:
                logger.warning(f"#{global_rank} {slug}: {e}")
                session.rollback()

        session.commit()
        logger.info(f"  Page {page_num}/{pages} done — rank {global_rank} "
                     f"(updated={total_updated}, inserted={total_inserted})")
        time.sleep(1)  # Rate limit: 1 req/sec

    session.commit()
    session.close()
    logger.info(f"WordPress King Enricher complete: "
                f"{total_updated} updated, {total_inserted} inserted, "
                f"{global_rank} total processed, top 500 flagged as kings")
    return total_updated + total_inserted


if __name__ == "__main__":
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    enrich(pages)
