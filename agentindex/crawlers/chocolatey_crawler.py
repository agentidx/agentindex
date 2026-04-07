#!/usr/bin/env python3
"""Chocolatey (Windows) Crawler. OData API with XML response."""
import json, logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text
import xml.etree.ElementTree as ET

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("chocolatey_crawler")

API = "https://community.chocolatey.org/api/v2/Packages()"
NS = {"d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
      "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
      "a": "http://www.w3.org/2005/Atom"}


def crawl(limit=5000):
    logger.info(f"Chocolatey crawl (limit={limit})")
    session = get_session()
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='chocolatey'")).fetchall()
    seen = {r[0] for r in rows}
    logger.info(f"  Already have {len(seen)} Chocolatey packages")

    total = 0; new = 0; skip = 0
    while total < limit:
        try:
            url = f"https://community.chocolatey.org/api/v2/Packages()?$filter=IsLatestVersion&$orderby=DownloadCount%20desc&$top=100&$skip={skip}"
            r = http.get(url,
                        headers={"User-Agent": "Mozilla/5.0",
                                "Accept": "application/atom+xml"},
                        timeout=20, allow_redirects=True)
            if r.status_code != 200:
                logger.warning(f"API error: {r.status_code}"); break
        except Exception as e:
            logger.warning(f"Request error: {e}"); break

        try:
            root = ET.fromstring(r.text)
            entries = root.findall(".//a:entry", NS)
            if not entries: break
        except Exception as e:
            logger.warning(f"XML parse error: {e}"); break

        for entry in entries:
            props = entry.find(".//m:properties", NS)
            if props is None: continue

            pkg_id = _get_prop(props, "Id")
            if not pkg_id: continue
            slug = pkg_id.lower().replace(".", "-")
            if slug in seen: total += 1; continue
            seen.add(slug)

            dl = int(_get_prop(props, "DownloadCount") or 0)
            ver = _get_prop(props, "Version") or ""
            desc = (_get_prop(props, "Description") or "")[:500]
            authors = _get_prop(props, "Authors") or ""
            title = _get_prop(props, "Title") or pkg_id
            license_url = _get_prop(props, "LicenseUrl") or ""
            project_url = _get_prop(props, "ProjectUrl") or ""
            tags = _get_prop(props, "Tags") or ""

            e = {"name": title, "slug": slug, "registry": "chocolatey",
                "version": ver, "description": desc,
                "author": authors[:100], "license": license_url[:100],
                "downloads": dl, "stars": 0, "last_updated": None,
                "repository_url": project_url[:200], "homepage_url": f"https://community.chocolatey.org/packages/{pkg_id}",
                "dependencies_count": 0,
                "raw_data": json.dumps({"tags": tags[:200]})}
            e["trust_score"], e["trust_grade"] = calculate_trust(e)

            try:
                session.execute(text("""INSERT INTO software_registry
                    (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                     repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                    VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                     :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                    ON CONFLICT (registry,slug) DO NOTHING
                """), e)
                new += 1
            except Exception:
                session.rollback()
            total += 1

        if total % 500 == 0:
            session.commit()
            logger.info(f"  {total} processed, {new} new")
        skip += 100; time.sleep(1)

    session.commit(); session.close()
    logger.info(f"Chocolatey complete: {total} processed, {new} NEW")
    return new


def _get_prop(props, name):
    ns = "http://schemas.microsoft.com/ado/2007/08/dataservices"
    el = props.find(f"{{{ns}}}{name}")
    return el.text if el is not None and el.text else ""


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 5000)
