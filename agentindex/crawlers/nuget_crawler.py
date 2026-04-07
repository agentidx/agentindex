#!/usr/bin/env python3
"""NuGet v2 — uses diverse queries + dedup for broad coverage."""
import json, logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("nuget_crawler")

QUERIES = [
    "json", "http", "log", "entity", "azure", "aws", "api", "test", "auth", "cache",
    "image", "pdf", "csv", "xml", "mail", "grpc", "swagger", "jwt", "redis", "mongo",
    "sql", "graphql", "aspnet", "blazor", "mvc", "web", "core", "ef", "identity",
    "automapper", "mediatr", "fluent", "serilog", "nlog", "hangfire", "quartz",
    "dapper", "npgsql", "mysql", "sqlite", "cosmos", "elastic", "rabbit", "kafka",
    "signalr", "odata", "rest", "soap", "wsdl", "protobuf", "messagepack",
    "newtonsoft", "system.text", "polly", "refit", "flurl", "httpclient",
    "xunit", "nunit", "moq", "autofac", "ninject", "unity", "castle",
    "benchmark", "bogus", "shouldly", "specflow", "selenium", "playwright",
    "docker", "kubernetes", "terraform", "pulumi", "consul", "vault",
    "opentelemetry", "prometheus", "grafana", "health", "diagnostic",
    "crypto", "security", "certificate", "oauth", "openid", "saml",
    "pdf", "excel", "word", "zip", "barcode", "qrcode",
    "machine-learning", "ml.net", "tensorflow", "onnx", "ai", "cognitive",
]


def crawl(limit=5000):
    logger.info(f"NuGet v2 crawl (limit={limit})")
    session = get_session(); total = 0; new = 0; seen = set()

    # Load existing slugs to skip
    rows = session.execute(text("SELECT slug FROM software_registry WHERE registry='nuget'")).fetchall()
    seen = {r[0] for r in rows}
    logger.info(f"  Already have {len(seen)} NuGet packages")

    for q in QUERIES:
        if total >= limit: break
        for skip in range(0, 1000, 100):  # Up to 1000 results per query
            if total >= limit: break
            try:
                r = http.get("https://azuresearch-usnc.nuget.org/query",
                            params={"q": q, "take": 100, "skip": skip, "prerelease": "false"},
                            timeout=15)
                if r.status_code != 200: break
                data = r.json().get("data", [])
                if not data: break
            except Exception as e:
                logger.warning(f"Query '{q}' skip {skip}: {e}"); break

            batch_new = 0
            for pkg in data:
                pkg_id = pkg.get("id", "")
                if not pkg_id: continue
                slug = pkg_id.lower().replace(".", "-")
                if slug in seen:
                    total += 1; continue
                seen.add(slug)

                authors = pkg.get("authors", [])
                entry = {"name": pkg_id, "slug": slug, "registry": "nuget",
                        "version": (pkg.get("versions", [{}])[-1] or {}).get("version") if pkg.get("versions") else None,
                        "description": (pkg.get("description") or "")[:500],
                        "author": (", ".join(authors) if isinstance(authors, list) else str(authors or ""))[:100],
                        "license": pkg.get("licenseUrl") or "",
                        "downloads": pkg.get("totalDownloads") or 0, "stars": 0,
                        "last_updated": None,
                        "repository_url": pkg.get("projectUrl"),
                        "homepage_url": f"https://www.nuget.org/packages/{pkg_id}",
                        "dependencies_count": 0,
                        "raw_data": json.dumps({"tags": pkg.get("tags", [])[:10], "verified": pkg.get("verified", False)})}
                entry["trust_score"], entry["trust_grade"] = calculate_trust(entry)
                try:
                    session.execute(text("""INSERT INTO software_registry
                        (name,slug,registry,version,description,author,license,downloads,stars,last_updated,
                         repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                        VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                         :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                        ON CONFLICT (registry,slug) DO UPDATE SET downloads=EXCLUDED.downloads,trust_score=EXCLUDED.trust_score,updated_at=NOW()
                    """), entry)
                    batch_new += 1; new += 1
                except Exception as e:
                    session.rollback()
                total += 1

            if total % 500 == 0 and new > 0:
                session.commit()
                logger.info(f"  {total} processed, {new} new (query: {q})")
            time.sleep(0.3)

    session.commit(); session.close()
    logger.info(f"NuGet v2 complete: {total} processed, {new} NEW")
    return new

if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 5000)
