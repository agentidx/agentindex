#!/usr/bin/env python3
"""Website Trust Crawler — Tranco Top 10K with SSL + header checks."""
import csv, io, json, logging, re, socket, ssl, sys, time
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("website_crawler")

TRANCO_URL = "https://tranco-list.eu/top-1m.csv.zip"


def _check_ssl(domain):
    """Check SSL certificate validity and issuer."""
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
            s.settimeout(5)
            s.connect((domain, 443))
            cert = s.getpeercert()
            issuer = dict(x[0] for x in cert.get("issuer", []))
            return True, issuer.get("organizationName", "Unknown")
    except Exception:
        return False, ""


def _check_headers(domain):
    """Check HTTP security headers via HEAD request."""
    result = {"hsts": False, "csp": False, "xframe": False, "server": ""}
    try:
        r = http.head(f"https://{domain}", timeout=5, allow_redirects=True,
                     headers={"User-Agent": "Nerq Trust Crawler (nerq.ai)"})
        h = r.headers
        result["hsts"] = "strict-transport-security" in {k.lower() for k in h}
        result["csp"] = "content-security-policy" in {k.lower() for k in h}
        result["xframe"] = "x-frame-options" in {k.lower() for k in h}
        result["server"] = h.get("server", "")[:50]
    except Exception:
        pass
    return result


def crawl(limit=10000):
    logger.info(f"Website crawl (limit={limit})")

    # Download Tranco list
    logger.info("Downloading Tranco list...")
    try:
        r = http.get(TRANCO_URL, timeout=60, allow_redirects=True)
        if r.status_code != 200:
            logger.error(f"Tranco download failed: {r.status_code}"); return 0
        # Handle zip file
        if TRANCO_URL.endswith(".zip") or r.headers.get("content-type","").startswith("application/zip"):
            import zipfile, io
            z = zipfile.ZipFile(io.BytesIO(r.content))
            csv_name = z.namelist()[0]
            lines = z.read(csv_name).decode("utf-8").strip().split("\n")
        else:
            lines = r.text.strip().split("\n")
        logger.info(f"  Got {len(lines)} domains from Tranco")
    except Exception as e:
        logger.error(f"Tranco download error: {e}"); return 0

    # Parse CSV: rank,domain
    domains = []
    for line in lines[:limit]:
        parts = line.strip().split(",")
        if len(parts) >= 2:
            domains.append((int(parts[0]), parts[1].strip()))

    session = get_session()
    # Load existing
    rows = session.execute(text("SELECT domain FROM website_cache")).fetchall()
    seen = {r[0] for r in rows}
    logger.info(f"  Already have {len(seen)} websites cached")

    # Load entity mappings
    entity_map = {}
    try:
        erows = session.execute(text("SELECT entity_slug, website FROM entity_ratings WHERE website IS NOT NULL")).fetchall()
        for er in erows:
            if er[1]:
                entity_map[er[1].lower().replace("www.", "")] = er[0]
    except Exception:
        pass

    total = 0; new = 0
    for rank, domain in domains:
        if domain in seen:
            total += 1; continue

        # SSL check
        ssl_valid, ssl_issuer = _check_ssl(domain)

        # Header check
        headers = _check_headers(domain)

        # Trust score calculation
        score = 0
        if rank <= 100: score += 25
        elif rank <= 1000: score += 20
        elif rank <= 10000: score += 15
        elif rank <= 100000: score += 10
        else: score += 5

        if ssl_valid: score += 15
        if headers["hsts"]: score += 10
        if headers["csp"]: score += 10
        if headers["xframe"]: score += 5

        # Entity bonus
        entity_id = entity_map.get(domain.replace("www.", ""))
        if entity_id: score += 15

        score += 10  # Base (in Tranco = real website)
        score = max(0, min(100, score))
        grade = "A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 70 else "C" if score >= 60 else "D"

        factors = {"rank": rank, "ssl": ssl_valid, "ssl_issuer": ssl_issuer,
                  "hsts": headers["hsts"], "csp": headers["csp"],
                  "xframe": headers["xframe"], "server": headers["server"]}

        try:
            session.execute(text("""INSERT INTO website_cache
                (domain, trust_score, trust_grade, tranco_rank, ssl_valid, ssl_issuer,
                 has_hsts, entity_id, factors)
                VALUES (:domain, :score, :grade, :rank, :ssl, :issuer, :hsts, :eid, CAST(:factors AS jsonb))
                ON CONFLICT (domain) DO UPDATE SET trust_score=EXCLUDED.trust_score, cached_at=NOW()
            """), {"domain": domain, "score": round(score, 1), "grade": grade,
                  "rank": rank, "ssl": ssl_valid, "issuer": ssl_issuer[:100],
                  "hsts": headers["hsts"], "eid": entity_id,
                  "factors": json.dumps(factors)})
            new += 1; seen.add(domain)
        except Exception:
            session.rollback()
        total += 1

        if new % 200 == 0:
            session.commit()
            logger.info(f"  {total} processed, {new} new (rank #{rank})")
        time.sleep(0.2)  # 5 req/sec

    session.commit(); session.close()
    logger.info(f"Website crawl complete: {total} processed, {new} NEW")
    return new


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 5000)
